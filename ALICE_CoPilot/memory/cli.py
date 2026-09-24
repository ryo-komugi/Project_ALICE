import argparse
import json
import re
import sys
from pathlib import Path
from memory.obsidian_export import export_all_memories
import config
from memory.long_term import (
    create_memory,
    create_relation,
    find_memory_by_id,
    load_relations,
    MEMORY_ROOT,
    ARCHIVE_ROOT,
)
from memory.memory_search import search_memories
from memory.memory_relation import reevaluate_relations_for_memory
from memory.memory_cleanup import (
    find_orphan_relations,
    print_orphan_relations,
    execute_clean_orphans,
)
from memory.obsidian_export import sync_obsidian


ALLOWED_TYPES = {"context", "project", "decision", "knowledge", "idea"}

RELATED_LINK_PATTERN = re.compile(r"\[\[([^\[\]]+)\]\]")

# Obsidian concept/page links which are not Memory IDs.
# Keep this list intentionally small: unknown links are reported as
# "Missing Memory IDs" instead of being silently discarded.
NON_MEMORY_LINKS = {
    "Project_ALICE",
    "ALICE_CoPilot",
}


def handle_add(args) -> int:
    memory_type = args.type.lower().strip()
    if memory_type not in ALLOWED_TYPES:
        print(
            f"Error: Invalid memory type '{args.type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
            file=sys.stderr,
        )
        return 1

    title = args.title.strip()
    if not title:
        print("Error: Memory title cannot be empty.", file=sys.stderr)
        return 1

    content = args.content.strip()
    if not content:
        print("Error: Memory content cannot be empty.", file=sys.stderr)
        return 1

    supersedes = args.supersedes or []
    related = args.related or []
    conflicts = args.conflicts or []

    all_relation_specs = (
        [("supersedes", target_id) for target_id in supersedes]
        + [("related", target_id) for target_id in related]
        + [("conflicts", target_id) for target_id in conflicts]
    )

    missing_ids = []
    for rel_type, target_id in all_relation_specs:
        path = find_memory_by_id(target_id, include_archive=True)
        if path is None:
            missing_ids.append((rel_type, target_id))

    if missing_ids:
        print(
            "Error: The following relation target Memory IDs do not exist:",
            file=sys.stderr,
        )
        for rel_type, target_id in missing_ids:
            print(f"  - Relation '{rel_type}' target ID: {target_id}", file=sys.stderr)
        return 1

    path = create_memory(memory_type=memory_type, title=title, content=content)
    memory_id = path.stem

    created_relations = []
    for rel_type, target_id in all_relation_specs:
        rel_path = create_relation(
            from_memory_id=memory_id, relation=rel_type, to_memory_id=target_id
        )
        created_relations.append(
            {
                "relation": rel_type,
                "target_id": target_id,
                "path": str(rel_path),
            }
        )

    try:
        auto_relations = reevaluate_relations_for_memory(
            memory_id=memory_id,
            title=title,
            content=content,
        )
        for r in auto_relations:
            created_relations.append(
                {
                    "relation": r["relation"],
                    "target_id": r["memory_id"],
                    "path": str(r["path"]),
                }
            )
    except Exception as e:
        print(f"[MEMORY CLI ERROR] Auto relation evaluation failed: {e}", file=sys.stderr)

    result = {
        "status": "success",
        "memory_id": memory_id,
        "type": memory_type,
        "title": title,
        "path": str(path),
        "relations": created_relations,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Memory created successfully.")
        print(f"  ID   : {memory_id}")
        print(f"  Type : {memory_type}")
        print(f"  Title: {title}")
        print(f"  Path : {path}")
        if created_relations:
            print("  Relations:")
            for r in created_relations:
                print(f"    - {r['relation']} -> {r['target_id']}")

    return 0


def handle_ingest(args) -> int:
    batch_file = Path(args.file)
    if not batch_file.exists():
        print(f"Error: Batch file '{batch_file}' does not exist.", file=sys.stderr)
        return 1

    try:
        data = json.loads(batch_file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, OSError, json.JSONDecodeError) as e:
        print(f"Error reading or parsing JSON file '{batch_file}': {e}", file=sys.stderr)
        return 1

    if not isinstance(data, list):
        print("Error: Batch file JSON must be an array of objects.", file=sys.stderr)
        return 1

    if not data:
        print("Batch file is empty. Nothing to ingest.")
        return 0

    validation_errors = []

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            validation_errors.append(f"Item #{index}: Must be a JSON object.")
            continue

        item_type = str(item.get("type", "")).lower().strip()
        if item_type not in ALLOWED_TYPES:
            validation_errors.append(
                f"Item #{index}: Invalid type '{item.get('type')}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_TYPES))}"
            )

        title = item.get("title")
        if not title or not isinstance(title, str) or not title.strip():
            validation_errors.append(f"Item #{index}: 'title' must be a non-empty string.")

        content = item.get("content")
        if not content or not isinstance(content, str) or not content.strip():
            validation_errors.append(f"Item #{index}: 'content' must be a non-empty string.")

        for rel_key in ("supersedes", "related", "conflicts"):
            rel_val = item.get(rel_key)
            if rel_val is not None:
                if not isinstance(rel_val, list):
                    validation_errors.append(
                        f"Item #{index}: '{rel_key}' must be an array of Memory ID strings."
                    )
                else:
                    for target_id in rel_val:
                        if not isinstance(target_id, str) or not target_id.strip():
                            validation_errors.append(
                                f"Item #{index}: '{rel_key}' contains invalid ID: {target_id}"
                            )
                        else:
                            if find_memory_by_id(target_id, include_archive=True) is None:
                                validation_errors.append(
                                    f"Item #{index}: Relation '{rel_key}' specifies target ID '{target_id}' which does not exist."
                                )

    if validation_errors:
        print(
            f"Pre-validation failed with {len(validation_errors)} error(s). NO memories were saved:\n",
            file=sys.stderr,
        )
        for err in validation_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    success_records = []
    failed = False
    batch_memory_ids = set()

    for index, item in enumerate(data, start=1):
        item_type = str(item["type"]).lower().strip()
        title = item["title"].strip()
        content = item["content"].strip()

        try:
            path = create_memory(memory_type=item_type, title=title, content=content)
            memory_id = path.stem
            batch_memory_ids.add(memory_id)

            created_rels = []
            for rel_key in ("supersedes", "related", "conflicts"):
                targets = item.get(rel_key, []) or []
                for target_id in targets:
                    rel_path = create_relation(
                        from_memory_id=memory_id, relation=rel_key, to_memory_id=target_id
                    )
                    created_rels.append(
                        {"relation": rel_key, "target_id": target_id, "path": str(rel_path)}
                    )

            try:
                auto_relations = reevaluate_relations_for_memory(
                    memory_id=memory_id,
                    title=title,
                    content=content,
                    exclude_ids=batch_memory_ids,
                )
                for r in auto_relations:
                    created_rels.append(
                        {"relation": r["relation"], "target_id": r["memory_id"], "path": str(r["path"])}
                    )
            except Exception as e:
                print(
                    f"[MEMORY INGEST ERROR] Auto relation evaluation failed for item #{index}: {e}",
                    file=sys.stderr,
                )

            success_records.append(
                {
                    "index": index,
                    "memory_id": memory_id,
                    "title": title,
                    "path": str(path),
                    "relations_count": len(created_rels),
                }
            )
        except Exception as e:
            print(
                f"\n[ERROR] Failed during saving item #{index} ('{title}'): {e}",
                file=sys.stderr,
            )
            print(
                f"Successfully saved {len(success_records)} item(s) before failure:",
                file=sys.stderr,
            )
            for rec in success_records:
                print(
                    f"  - Item #{rec['index']}: ID {rec['memory_id']} ({rec['title']})",
                    file=sys.stderr,
                )
            failed = True
            break

    if failed:
        return 1

    print("=" * 80)
    print("INGEST BATCH SUMMARY")
    print("=" * 80)
    print(f"Total items ingested: {len(success_records)}")
    for rec in success_records:
        print(
            f"  - Item #{rec['index']}: ID {rec['memory_id']} | Title: {rec['title']} "
            f"({rec['relations_count']} relations)"
        )
    print("=" * 80)

    return 0


def handle_search(args) -> int:
    query = args.query.strip()
    if not query:
        print("Error: Search query cannot be empty.", file=sys.stderr)
        return 1

    limit = args.limit
    results = search_memories(query=query, limit=limit)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("=" * 80)
        print(f"MEMORY SEARCH RESULTS (Query: '{query}', Count: {len(results)})")
        print("=" * 80)

        if not results:
            print("No matching memories found.")
            print("=" * 80)
            return 0

        for index, item in enumerate(results, start=1):
            print()
            print(f"[{index}/{len(results)}] ID: {item['id']} (Score: {item['score']})")
            print(f"  Path: {item['path']}")
            print("  Content preview:")
            lines = item["content"].splitlines()
            preview = "\n".join(lines[:6])
            print(f"  {preview}")

        print()
        print("=" * 80)

    return 0


def handle_export_obsidian(args) -> int:
    """
    Export all active Memories to the Obsidian vault.

    The source Memory files and Relation files are never modified.
    """

    print("=" * 80)
    print("EXPORT OBSIDIAN")
    print("=" * 80)

    try:
        exported = export_all_memories()
    except Exception as exc:
        print(f"[ERROR] Obsidian export failed: {exc}", file=sys.stderr)
        print("=" * 80)
        return 1

    print(f"Obsidian root     : {config.OBSIDIAN_ROOT}")
    print(f"Memories exported : {len(exported)}")
    print("Errors            : 0")
    print("=" * 80)

    return 0


def _extract_related_links(text: str) -> list[str]:
    """
    Extract Obsidian [[...]] links from the ## Related section only.

    The Markdown itself is never modified.
    """
    lines = text.splitlines()
    in_related = False
    links = []

    for line in lines:
        if line.startswith("## Related"):
            in_related = True
            continue

        if in_related and line.startswith("## "):
            break

        if not in_related:
            continue

        for match in RELATED_LINK_PATTERN.findall(line):
            # Support standard Obsidian aliases such as [[MemoryID|label]].
            target = match.split("|", 1)[0].strip()
            if target:
                links.append(target)

    return links


def _relation_exists(relations: list[dict], from_id: str, to_id: str) -> bool:
    """Return True when the exact related relation already exists."""
    return any(
        relation.get("from") == from_id
        and relation.get("relation") == "related"
        and relation.get("to") == to_id
        for relation in relations
    )


def handle_migrate_related(args) -> int:
    """
    Migrate explicit Markdown ## Related [[...]] links into Relation JSON.

    Rules:
      - Active Memory is scanned as the source side.
      - Archive Memory is never scanned as the source side.
      - Archive Memory is valid as a target.
      - Only resolvable Memory IDs become Relations.
      - Existing Relations are never duplicated.
      - Markdown files are never modified.
      - No LLM/Ollama is used.
    """
    dry_run = bool(getattr(args, "dry_run", False))

    print("=" * 80)
    print("MIGRATE MARKDOWN RELATED")
    print("=" * 80)

    existing_relations = load_relations()

    markdown_files_scanned = 0
    related_links_found = 0
    relations_already_exist = 0
    relations_created = 0
    relations_would_create = 0
    skipped_non_memory = 0
    missing_memory_ids = 0
    errors = 0

    # Deduplicate within this run as well as against existing JSON.
    seen_pairs = {
        (item.get("from"), item.get("to"))
        for item in existing_relations
        if item.get("relation") == "related"
    }

    for path in sorted(MEMORY_ROOT.rglob("*.md")):
        if not path.is_file():
            continue

        if (
            path.name.startswith(".")
            or ".sync-conflict-" in path.name
            or path.name.endswith(".tmp")
        ):
            continue

        # Archive is never a source of migrated Relations.
        if ARCHIVE_ROOT in path.parents:
            continue

        markdown_files_scanned += 1

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"[ERROR] Failed to read {path}: {exc}", file=sys.stderr)
            errors += 1
            continue

        from_id = path.stem
        links = _extract_related_links(text)
        related_links_found += len(links)

        for target in links:
            if target in NON_MEMORY_LINKS:
                skipped_non_memory += 1
                continue

            target_path = find_memory_by_id(target, include_archive=True)
            if target_path is None:
                missing_memory_ids += 1
                print(f"[MISSING] {from_id} -> [[{target}]]")
                continue

            target_id = target_path.stem
            pair = (from_id, target_id)

            if pair in seen_pairs or _relation_exists(existing_relations, from_id, target_id):
                relations_already_exist += 1
                seen_pairs.add(pair)
                continue

            if dry_run:
                relations_would_create += 1
                seen_pairs.add(pair)
                continue

            try:
                create_relation(
                    from_memory_id=from_id,
                    relation="related",
                    to_memory_id=target_id,
                )
                relations_created += 1
                seen_pairs.add(pair)
            except Exception as exc:
                errors += 1
                print(
                    f"[ERROR] Failed to create relation {from_id} -> {target_id}: {exc}",
                    file=sys.stderr,
                )

    print()
    print(f"Markdown files scanned : {markdown_files_scanned}")
    print(f"Related links found    : {related_links_found}")
    print(f"Relations already exist: {relations_already_exist}")
    print(f"Relations created      : {relations_created}")
    print(f"Relations would create : {relations_would_create}")
    print(f"Skipped non-memory     : {skipped_non_memory}")
    print(f"Missing Memory IDs     : {missing_memory_ids}")
    print(f"Errors                 : {errors}")
    print("=" * 80)

    return 1 if errors else 0


def handle_sync_obsidian(args) -> int:
    """
    Synchronize Source Memory with the Obsidian representation.

    Source Memory is authoritative.

    --dry-run:
        Detect differences only. No files are modified.

    --clean:
        Remove obsolete managed Obsidian files after exporting
        current Source Memories.
    """
    if args.dry_run and args.clean:
        print(
            "Error: --dry-run and --clean cannot be used together.",
            file=sys.stderr,
        )
        return 1

    result = sync_obsidian(
        dry_run=args.dry_run,
        clean=args.clean,
    )

    print("=" * 80)
    print("SYNC OBSIDIAN")
    print("=" * 80)

    print(f"Obsidian root       : {config.OBSIDIAN_ROOT}")
    print(f"Source Memories     : {result['source_count']}")
    print(f"Expected files      : {result['expected_count']}")
    print(f"Managed Obsidian    : {result['existing_managed_count']}")
    print(f"Missing             : {len(result['missing'])}")
    print(f"Obsolete            : {len(result['obsolete'])}")
    print(f"Exported            : {len(result['exported'])}")
    print(f"Deleted             : {len(result['deleted'])}")
    print(f"Errors              : {len(result['errors'])}")

    if result["missing"]:
        print()
        print("Missing files:")
        for path in result["missing"]:
            print(f"  - {path}")

    if result["obsolete"]:
        print()
        print("Obsolete files:")

        for path in result["obsolete"]:
            print(f"  - {path}")

    if result["deleted"]:
        print()
        print("Deleted files:")

        for path in result["deleted"]:
            print(f"  - {path}")

    if result["errors"]:
        print()
        print("Errors:")

        for error in result["errors"]:
            print(
                f"  - {error['operation']}: "
                f"{error.get('path', error.get('source', ''))}"
            )
            print(f"    {error['error']}")

    if args.dry_run:
        print()
        print("DRY-RUN: No files were modified.")

    print("=" * 80)

    return 1 if result["errors"] else 0


def handle_cleanup(args) -> int:
    if args.check_orphans:
        orphans = find_orphan_relations()
        print_orphan_relations(orphans)
        return 0

    if args.clean_orphans:
        orphans = find_orphan_relations()
        execute_clean_orphans(orphans, confirm_yes=args.yes)
        return 0

    orphans = find_orphan_relations()
    print_orphan_relations(orphans)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ALICE_CoPilot Memory Management CLI",
        prog="python -m memory.cli",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # 1. add
    parser_add = subparsers.add_parser("add", help="Add a confirmed single memory directly.")
    parser_add.add_argument(
        "--type",
        "-t",
        required=True,
        help="Memory type (context, project, decision, knowledge, idea)",
    )
    parser_add.add_argument("--title", required=True, help="Memory title")
    parser_add.add_argument("--content", required=True, help="Memory content")
    parser_add.add_argument(
        "--supersedes", action="append", help="Target Memory ID that this memory supersedes"
    )
    parser_add.add_argument(
        "--related", action="append", help="Target Memory ID that this memory is related to"
    )
    parser_add.add_argument(
        "--conflicts", action="append", help="Target Memory ID that this memory conflicts with"
    )
    parser_add.add_argument("--json", action="store_true", help="Output result in JSON format")

    # 2. ingest
    parser_ingest = subparsers.add_parser("ingest", help="Batch ingest memories from JSON file.")
    parser_ingest.add_argument("--file", "-f", required=True, help="Path to batch JSON file")

    # 3. search
    parser_search = subparsers.add_parser("search", help="Search memories.")
    parser_search.add_argument("query", help="Search query keyword(s)")
    parser_search.add_argument(
        "--limit", "-n", type=int, default=10, help="Maximum number of results (default: 10)"
    )
    parser_search.add_argument("--json", action="store_true", help="Output results in JSON format")

    # 4. migrate-related
    parser_migrate_related = subparsers.add_parser(
        "migrate-related",
        help="Migrate Markdown ## Related links into Relation JSON files.",
    )
    parser_migrate_related.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report without creating Relation files.",
    )

    # 5. export-obsidian
    parser_export_obsidian = subparsers.add_parser(
        "export-obsidian",
        help="Export all Memories to the Obsidian vault.",
    )

    # 6. sync-obsidian
    parser_sync_obsidian = subparsers.add_parser(
        "sync-obsidian",
        help="Synchronize Source Memory with the Obsidian vault.",
    )
    parser_sync_obsidian.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect differences without modifying files.",
    )
    parser_sync_obsidian.add_argument(
        "--clean",
        action="store_true",
        help="Delete obsolete managed Obsidian files.",
    )

    # 7. cleanup
    parser_cleanup = subparsers.add_parser(
        "cleanup", help="Inspect and clean orphan relations."
    )
    parser_cleanup.add_argument(
        "--check-orphans", action="store_true", help="Report orphan relations without modifying files."
    )
    parser_cleanup.add_argument(
        "--clean-orphans", action="store_true", help="Delete orphan relation files."
    )
    parser_cleanup.add_argument(
        "-y", "--yes", action="store_true", help="Confirm deletion without interactive prompt."
    )

    args = parser.parse_args()

    if args.command == "add":
        return handle_add(args)
    elif args.command == "ingest":
        return handle_ingest(args)
    elif args.command == "search":
        return handle_search(args)
    elif args.command == "migrate-related":
        return handle_migrate_related(args)
    elif args.command == "export-obsidian":
        return handle_export_obsidian(args)
    elif args.command == "sync-obsidian":
        return handle_sync_obsidian(args)
    elif args.command == "cleanup":
        return handle_cleanup(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())