from pathlib import Path

import config
from memory.long_term import (
    ARCHIVE_ROOT,
    MEMORY_ROOT,
    find_memory_by_id,
    find_relations_for_memory,
)


OBSIDIAN_ROOT = config.OBSIDIAN_ROOT


TYPE_DIRECTORIES = {
    "Context": "Context",
    "Projects": "Projects",
    "Decisions": "Decisions",
    "Knowledge": "Knowledge",
    "Ideas": "Ideas",
    "Conversations": "Conversations",
}


def _read_memory(path: Path) -> str:
    """
    Read a Memory Markdown file without modifying it.
    """
    return path.read_text(encoding="utf-8")


def _memory_type_directory(memory_path: Path) -> str:
    """
    Return the Obsidian directory corresponding to a Memory directory.

    Unknown directories are exported under the original directory name.
    """
    directory_name = memory_path.parent.name

    return TYPE_DIRECTORIES.get(
        directory_name,
        directory_name,
    )


def _obsidian_memory_path(memory_path: Path) -> Path:
    """
    Return the destination path of a Memory inside the Obsidian vault.

    Active Memories are exported under their Memory type directory.

    Archive Memories are exported directly under Archive/.
    """
    relative_name = memory_path.name

    if ARCHIVE_ROOT in memory_path.parents:
        return OBSIDIAN_ROOT / "Archive" / relative_name

    type_directory = _memory_type_directory(memory_path)

    return OBSIDIAN_ROOT / type_directory / relative_name


def _relation_target_title(memory_id: str) -> str:
    """
    Return the Obsidian link target for a Memory ID.

    The target is the actual Memory filename without the .md extension.
    """
    memory_path = find_memory_by_id(
        memory_id,
        include_archive=True,
    )

    if memory_path is None:
        return memory_id

    return memory_path.stem


def _format_relation_link(memory_id: str) -> str:
    """
    Format a Memory ID as an Obsidian wikilink.
    """
    return f"[[{_relation_target_title(memory_id)}]]"


def _build_relations_section(memory_id: str) -> str:
    """
    Build the Relations section for one Memory.

    Relation direction is preserved:

        Memory
          ├─ Related     -> target
          ├─ Supersedes  -> target
          └─ Conflicts   -> target
    """
    relations = find_relations_for_memory(memory_id)

    related = []
    supersedes = []
    superseded_by = []
    conflicts = []

    for relation in relations:
        relation_type = relation.get("relation")
        from_id = relation.get("from")
        to_id = relation.get("to")

        if not from_id or not to_id:
            continue

        if relation_type == "related":
            if from_id == memory_id:
                related.append(to_id)
            elif to_id == memory_id:
                related.append(from_id)

        elif relation_type == "supersedes":
            if from_id == memory_id:
                supersedes.append(to_id)
            elif to_id == memory_id:
                superseded_by.append(from_id)

        elif relation_type == "conflicts":
            if from_id == memory_id:
                conflicts.append(to_id)
            elif to_id == memory_id:
                conflicts.append(from_id)

    sections = []

    if related:
        sections.append(
            "### Related\n"
            + "\n".join(
                f"- {_format_relation_link(memory_id)}"
                for memory_id in sorted(set(related))
            )
        )

    if supersedes:
        sections.append(
            "### Supersedes\n"
            + "\n".join(
                f"- {_format_relation_link(memory_id)}"
                for memory_id in sorted(set(supersedes))
            )
        )

    if superseded_by:
        sections.append(
            "### Superseded By\n"
            + "\n".join(
                f"- {_format_relation_link(memory_id)}"
                for memory_id in sorted(set(superseded_by))
            )
        )

    if conflicts:
        sections.append(
            "### Conflicts\n"
            + "\n".join(
                f"- {_format_relation_link(memory_id)}"
                for memory_id in sorted(set(conflicts))
            )
        )

    if not sections:
        return ""

    return "## Relations\n\n" + "\n\n".join(sections)


def _build_export_content(memory_path: Path) -> str:
    """
    Build the Obsidian representation of one Memory.

    The original Memory content is preserved.
    Only the Relations section is added.
    """
    memory_id = memory_path.stem

    original_content = _read_memory(memory_path).rstrip()

    relations_section = _build_relations_section(memory_id)

    if not relations_section:
        return original_content + "\n"

    return (
        original_content
        + "\n\n"
        + relations_section
        + "\n"
    )


def export_memory(memory_path: Path) -> Path:
    """
    Export one Memory Markdown file to the Obsidian vault.

    This function:
      - never modifies the source Memory
      - never modifies Relation JSON
      - only writes to OBSIDIAN_ROOT
    """
    if not memory_path.is_file():
        raise FileNotFoundError(
            f"Memory file does not exist: {memory_path}"
        )

    destination = _obsidian_memory_path(memory_path)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = _build_export_content(memory_path)

    destination.write_text(
        content,
        encoding="utf-8",
    )

    return destination


def export_all_memories() -> list[Path]:
    """
    Export all active and archived Memories to the Obsidian vault.

    Returns:
        List of exported Obsidian Markdown paths.
    """
    if not MEMORY_ROOT.exists():
        return []

    exported = []

    for memory_path in sorted(MEMORY_ROOT.rglob("*.md")):
        if not memory_path.is_file():
            continue

        if memory_path.name.startswith("."):
            continue

        if ".sync-conflict-" in memory_path.name:
            continue

        if memory_path.name.endswith(".tmp"):
            continue

        exported.append(
            export_memory(memory_path)
        )

    return exported


def _is_managed_obsidian_path(path: Path) -> bool:
    """
    Return True when the path is inside an Obsidian directory managed
    by ALICE_CoPilot.

    User-created notes outside these directories are never touched.
    """
    if not path.is_file():
        return False

    if path.suffix.lower() != ".md":
        return False

    if path.name.startswith("."):
        return False

    if ".sync-conflict-" in path.name:
        return False

    if path.name.endswith(".tmp"):
        return False

    try:
        relative = path.relative_to(OBSIDIAN_ROOT)
    except ValueError:
        return False

    if not relative.parts:
        return False

    return relative.parts[0] in {
        "Context",
        "Projects",
        "Decisions",
        "Knowledge",
        "Ideas",
        "Conversations",
        "Archive",
    }


def _collect_source_memory_paths() -> list[Path]:
    """
    Collect all valid source Memory Markdown files.

    The source Memory tree is the authoritative source.
    """
    if not MEMORY_ROOT.exists():
        return []

    memories = []

    for path in sorted(MEMORY_ROOT.rglob("*.md")):
        if not path.is_file():
            continue

        if path.name.startswith("."):
            continue

        if ".sync-conflict-" in path.name:
            continue

        if path.name.endswith(".tmp"):
            continue

        memories.append(path)

    return memories


def _collect_expected_obsidian_paths() -> set[Path]:
    """
    Return the set of Obsidian paths that should exist according to
    the current Source Memory tree.
    """
    return {
        _obsidian_memory_path(memory_path)
        for memory_path in _collect_source_memory_paths()
    }


def _collect_obsolete_obsidian_paths() -> list[Path]:
    """
    Find managed Obsidian Markdown files which no longer correspond
    to a Source Memory.

    Only files in ALICE_CoPilot-managed directories are considered.

    This function never modifies files.
    """
    expected_paths = _collect_expected_obsidian_paths()

    if not OBSIDIAN_ROOT.exists():
        return []

    obsolete = []

    for path in sorted(OBSIDIAN_ROOT.rglob("*.md")):
        if not _is_managed_obsidian_path(path):
            continue

        if path not in expected_paths:
            obsolete.append(path)

    return obsolete


def sync_obsidian(
    dry_run: bool = False,
    clean: bool = False,
) -> dict:
    """
    Synchronize the Obsidian representation with Source Memory.

    Source Memory is authoritative.

    Behavior:

      dry_run=True:
          Detect differences only.
          No files are written or deleted.

      dry_run=False, clean=False:
          Export all Source Memories.
          Report obsolete Obsidian files.
          Do not delete obsolete files.

      dry_run=False, clean=True:
          Export all Source Memories.
          Delete obsolete managed Obsidian files.

    Returns:
        Dictionary containing synchronization results.
    """
    source_memories = _collect_source_memory_paths()

    expected_paths = {
        _obsidian_memory_path(memory_path)
        for memory_path in source_memories
    }

    existing_managed_paths = []

    if OBSIDIAN_ROOT.exists():
        for path in sorted(OBSIDIAN_ROOT.rglob("*.md")):
            if _is_managed_obsidian_path(path):
                existing_managed_paths.append(path)

    existing_set = set(existing_managed_paths)

    missing_paths = sorted(
        expected_paths - existing_set
    )

    obsolete_paths = sorted(
        existing_set - expected_paths
    )

    exported = []
    deleted = []
    errors = []

    if not dry_run:
        for memory_path in source_memories:
            try:
                exported.append(
                    export_memory(memory_path)
                )
            except Exception as exc:
                errors.append(
                    {
                        "operation": "export",
                        "source": str(memory_path),
                        "error": str(exc),
                    }
                )

        if clean:
            for path in obsolete_paths:
                try:
                    path.unlink()
                    deleted.append(path)
                except OSError as exc:
                    errors.append(
                        {
                            "operation": "delete",
                            "path": str(path),
                            "error": str(exc),
                        }
                    )

    return {
        "source_count": len(source_memories),
        "expected_count": len(expected_paths),
        "existing_managed_count": len(existing_managed_paths),
        "missing": missing_paths,
        "obsolete": obsolete_paths,
        "exported": exported,
        "deleted": deleted,
        "errors": errors,
        "dry_run": dry_run,
        "clean": clean,
    }