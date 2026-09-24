import argparse
import json
import shutil
from pathlib import Path

import requests
import config
from memory.memory_search import search_memories
from memory.memory_relation import find_duplicate_memory
from memory.long_term import is_valid_memory_file, is_valid_relation_file, RELATIONS_ROOT


MEMORY_ROOT = config.MEMORY_ROOT
ARCHIVE_ROOT = config.ARCHIVE_ROOT

TYPE_DIRECTORIES = {
    "Context": "context",
    "Projects": "project",
    "Decisions": "decision",
    "Knowledge": "knowledge",
    "Ideas": "idea",
    "Conversations": "conversation",
}


def get_memory_type(path: Path) -> str:
    """
    Return the logical memory type from its parent directory.
    """

    return TYPE_DIRECTORIES.get(path.parent.name, "unknown")


def load_memories() -> list[dict]:
    """
    Load all Markdown memories.
    """

    memories = []

    for path in sorted(MEMORY_ROOT.rglob("*.md")):
        if not is_valid_memory_file(path):
            continue

        if ARCHIVE_ROOT in path.parents:
            continue

        text = path.read_text(encoding="utf-8")

        memory_type = get_memory_type(path)

        memories.append(
            {
                "id": path.stem,
                "path": path,
                "content": text,
                "type": memory_type,
            }
        )

    return memories


def find_duplicate_candidates(memory: dict, limit: int = 10) -> list[dict]:
    """
    Find existing memories that may duplicate the given memory.

    This function never modifies files.
    """

    results = search_memories(
        query=memory["content"],
        limit=limit,
    )

    candidates = []

    for item in results:
        if item["id"] == memory["id"]:
            continue

        candidates.append(item)

    return candidates


def analyze_memory(memory: dict) -> dict:
    """
    Analyze one memory for possible duplication.

    This function never modifies files.
    """

    candidates = find_duplicate_candidates(memory)

    if not candidates:
        return {
            "memory": memory,
            "duplicate_of": None,
            "duplicate": None,
            "candidates": [],
        }

    duplicate_id = find_duplicate_memory(
        title=memory["path"].stem,
        content=memory["content"],
        limit=len(candidates),
        candidates=candidates,
    )

    duplicate_memory = None

    if duplicate_id is not None:
        duplicate_memory = next(
            (
                item
                for item in load_memories()
                if item["id"] == duplicate_id
            ),
            None,
        )

    return {
        "memory": memory,
        "duplicate_of": duplicate_id,
        "duplicate": duplicate_memory,
        "candidates": candidates,
    }


def generate_report() -> list[dict]:
    """
    Analyze all memories and return a read-only report.
    """

    memories = load_memories()

    reports = []

    for index, memory in enumerate(memories, start=1):
        print(
            f"[{index}/{len(memories)}] "
            f"Analyzing: {memory['id']}"
        )
        reports.append(analyze_memory(memory))
    return reports


def select_canonical_memory(group: list[dict]) -> dict | None:
    """
    Select the most appropriate canonical memory from a duplicate group.

    This function uses Ollama for judgment.
    It never modifies any files.
    """

    if not group:
        return None

    if len(group) == 1:
        return {
            "memory": group[0],
            "reason": "Duplicate group contains only one memory.",
            "confidence": "high",
        }

    memory_text = "\n\n".join(
        (
            f"--- Memory {index} ---\n"
            f"ID: {memory['id']}\n"
            f"Type: {memory['type']}\n"
            f"Path: {memory['path']}\n"
            f"Content:\n{memory['content']}"
        )
        for index, memory in enumerate(group, start=1)
    )

    prompt = f"""
以下は、同じ内容を表していると判定された
長期記憶のグループです。

{memory_text}

このグループの中から、
Canonical Memory（代表として扱うべき記憶）を
1件選んでください。

【Canonical Memoryの意味】

Canonical Memoryとは、
この重複グループを代表して参照するのに
最も適切な既存記憶です。

これは「削除してよいMemory」を意味しません。

過去の記録として意味があるMemoryを、
単純に古いという理由だけで選外にしないでください。

【判断基準】

以下を総合的に判断してください。

1. 記憶している事実・決定事項を正確に表している。
2. 記憶単体を読んでも意味が分かる。
3. 将来の検索・参照に適している。
4. 必要な具体性を保持している。
5. 不要な推測や説明が少ない。
6. 同じグループ内の他のMemoryより代表性が高い。
7. 決定事項の場合、何が決定されたのかが明確である。
8. Typeが異なる場合も、内容と役割を考慮して判断する。
9. 単純に「文章が長い」「新しい」「古い」
   という理由だけで選ばない。

【重要】

Canonicalに選ばれなかったMemoryを
削除すべきだとは判断しないでください。

この処理では、
あくまで「代表として最も適切なMemory」を
1件選ぶだけです。

現在の情報と過去の情報に矛盾がある場合は、
無理にCanonicalを決定せず、
confidenceをlowにしてください。

【IDに関する重要なルール】

canonicalに入れるIDは、
候補一覧に記載されているIDを
完全にそのままコピーしてください。

- IDを短縮してはいけません。
- IDの一部だけを返してはいけません。
- IDを変更してはいけません。
- IDを生成してはいけません。
- 候補一覧に存在しないIDを返してはいけません。

confidenceは以下の3種類だけです。

- high
- medium
- low

必ずJSONだけを返してください。

形式:

{{
    "canonical": "候補一覧に存在するMemory ID",
    "reason": "Canonicalと判断した具体的な理由",
    "confidence": "high"
}}

または判断に確信がない場合:

{{
    "canonical": "候補一覧に存在するMemory ID",
    "reason": "判断が難しい理由",
    "confidence": "low"
}}
"""

    response = requests.post(
        config.OLLAMA_URL,
        json={
            "model": config.OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "あなたはALICE_CoPilotの"
                        "Canonical Memory選定エンジンです。"
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "format": "json",
            "think": False,
        },
        timeout=300,
    )

    response.raise_for_status()

    print(
        f"[MEMORY CANONICAL HTTP] "
        f"{response.status_code}"
    )
    print(
        f"[MEMORY CANONICAL RAW] "
        f"{response.text!r}"
    )

    data = response.json()

    try:
        result = json.loads(data["message"]["content"])
    except (json.JSONDecodeError, TypeError) as e:
        print(
            f"[MEMORY CANONICAL ERROR] "
            f"Invalid JSON response: {e}"
        )
        print(
            f"[MEMORY CANONICAL RESPONSE] "
            f"{data['message']['content']!r}"
        )
        return None

    canonical_id = result.get("canonical")
    reason = result.get("reason", "").strip()
    confidence = result.get("confidence", "low")

    if not canonical_id:
        return None

    valid_ids = {
        memory["id"]
        for memory in group
    }

    if canonical_id not in valid_ids:
        print(
            "[MEMORY CANONICAL ERROR] "
            f"Invalid canonical ID: {canonical_id}"
        )
        return None

    if confidence not in {"high", "medium", "low"}:
        confidence = "low"

    canonical_memory = next(
        memory
        for memory in group
        if memory["id"] == canonical_id
    )

    return {
        "memory": canonical_memory,
        "reason": reason,
        "confidence": confidence,
    }


def build_archive_candidates(canonical_groups: list[dict]) -> list[dict]:
    """
    Build archive candidates from analyzed duplicate groups.

    Canonical selection has already been performed by
    analyze_canonical_groups().
    This function never calls the LLM.
    This function never modifies files.
    """

    archive_candidates = []

    for item in canonical_groups:
        group_index = item["group_index"]
        group = item["group"]
        canonical_result = item["canonical"]

        if canonical_result is None:
            continue

        canonical = canonical_result["memory"]
        confidence = canonical_result["confidence"]

        # Canonical selection is not reliable enough.
        if confidence != "high":
            continue

        for memory in group:
            if memory["id"] == canonical["id"]:
                continue

            # Different types require manual review.
            if memory["type"] != canonical["type"]:
                continue

            archive_candidates.append(
                {
                    "group": group_index,
                    "memory": memory,
                    "canonical": canonical,
                    "confidence": confidence,
                    "reason": canonical_result["reason"],
                }
            )
    return archive_candidates


def print_archive_candidates(candidates: list[dict]) -> None:
    """
    Print archive candidates.

    This function never modifies files.
    """

    print()
    print("=" * 80)
    print("MEMORY ARCHIVE CANDIDATES")
    print("=" * 80)

    if not candidates:
        print()
        print("No archive candidates found.")
        print()
        print("No files were modified.")
        return

    for index, candidate in enumerate(candidates, start=1):
        memory = candidate["memory"]
        canonical = candidate["canonical"]

        print()
        print("-" * 80)
        print(f"[ARCHIVE CANDIDATE {index}]")
        print("-" * 80)

        print(f"Group       : {candidate['group']}")
        print()
        print(f"Archive ID  : {memory['id']}")
        print(f"Archive Type: {memory['type']}")
        print(f"Archive Path: {memory['path']}")

        print()
        print(f"Canonical ID  : {canonical['id']}")
        print(f"Canonical Type: {canonical['type']}")
        print(f"Canonical Path: {canonical['path']}")

        print()
        print(f"Confidence: {candidate['confidence']}")
        print(f"Reason    : {candidate['reason']}")

    print()
    print("=" * 80)
    print(f"Archive candidates : {len(candidates)}")
    print("=" * 80)
    print()
    print("No files were modified.")


def execute_archive(candidates: list[dict]) -> None:
    """
    Move approved archive candidates to the Archive directory.

    Only high-confidence, same-type candidates are archived.
    Canonical memories are never moved.

    This function modifies files.
    """

    if not candidates:
        print()
        print("No archive candidates to process.")
        return

    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 80)
    print("MEMORY ARCHIVE EXECUTION")
    print("=" * 80)

    archived_count = 0
    failed_count = 0

    for candidate in candidates:
        memory = candidate["memory"]
        canonical = candidate["canonical"]

        source = Path(memory["path"])
        destination = ARCHIVE_ROOT / source.name

        # Safety checks
        if memory["id"] == canonical["id"]:
            print()
            print(
                f"[SKIP] Canonical memory: "
                f"{memory['id']}"
            )
            continue

        if candidate["confidence"] != "high":
            print()
            print(
                f"[SKIP] Confidence is not high: "
                f"{memory['id']}"
            )
            continue

        if memory["type"] != canonical["type"]:
            print()
            print(
                f"[SKIP] Cross-type memory: "
                f"{memory['id']}"
            )
            continue

        if not source.exists():
            print()
            print(
                f"[FAILED] Source not found: "
                f"{source}"
            )
            failed_count += 1
            continue

        if destination.exists():
            print()
            print(
                f"[SKIP] Archive already exists: "
                f"{destination}"
            )
            continue

        try:
            shutil.move(str(source), str(destination))
            print()
            print("[ARCHIVED]")
            print(f"Memory    : {memory['id']}")
            print(f"Source    : {source}")
            print(f"Destination: {destination}")
            archived_count += 1

        except OSError as e:
            print()
            print("[FAILED]")
            print(f"Memory : {memory['id']}")
            print(f"Error  : {e}")

            failed_count += 1
    print()
    print("=" * 80)
    print("ARCHIVE EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Archived : {archived_count}")
    print(f"Failed   : {failed_count}")
    print("=" * 80)


def print_duplicate_groups(canonical_groups: list[dict]) -> None:
    """
    Print duplicate memory groups and canonical candidates.

    This function never modifies files.
    """

    print()
    print("=" * 80)
    print("MEMORY DUPLICATE GROUPS")
    print("=" * 80)

    for item in canonical_groups:
        index = item["group_index"]
        group = item["group"]
        canonical = item["canonical"]
        print()
        print("-" * 80)
        print(f"[GROUP {index}]")
        print("-" * 80)

        print(f"Members: {len(group)}")

        if canonical is not None:
            canonical_memory = canonical["memory"]

            print()
            print("Canonical Candidate:")
            print(f"  ID         : {canonical_memory['id']}")
            print(f"  Type       : {canonical_memory['type']}")
            print(f"  Path       : {canonical_memory['path']}")
            print(f"  Confidence : {canonical['confidence']}")
            print(f"  Reason     : {canonical['reason']}")

        for memory in group:
            print()
            print(f"ID   : {memory['id']}")
            print(f"Type : {memory['type']}")
            print(f"Path : {memory['path']}")
            print("Title/Content:")
            print(memory["content"])

    print()
    print("=" * 80)
    print(f"Duplicate groups : {len(canonical_groups)}")
    print("=" * 80)
    print()
    print("No files were modified.")


def print_report(reports: list[dict]) -> None:
    """
    Print detailed duplicate analysis results.

    This function never modifies files.
    """

    print()
    print("=" * 80)
    print("MEMORY CLEANUP REVIEW REPORT")
    print("=" * 80)

    duplicate_count = 0
    review_count = 0

    for report in reports:
        duplicate_id = report["duplicate_of"]

        if duplicate_id is None:
            continue

        duplicate_count += 1

        memory = report["memory"]
        duplicate = report["duplicate"]

        if duplicate is None:
            continue

        duplicate_type = duplicate.get("type", "unknown")

        if memory["type"] == duplicate_type:
            review_status = "SAME TYPE"
        else:
            review_status = "CROSS TYPE - REVIEW REQUIRED"
            review_count += 1

        print()
        print("-" * 80)
        print("[DUPLICATE CANDIDATE]")
        print("-" * 80)

        print(f"Status       : {review_status}")
        print()
        print(f"Memory ID    : {memory['id']}")
        print(f"Memory Type  : {memory['type']}")
        print(f"Memory Path  : {memory['path']}")
        print()
        print("Memory Content:")
        print(memory["content"])

        print()
        print(f"Duplicate ID   : {duplicate['id']}")
        print(f"Duplicate Type : {duplicate_type}")
        print(f"Duplicate Path : {duplicate['path']}")

        print()
        print("Duplicate Content:")
        print(duplicate["content"])

    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Memories analyzed        : {len(reports)}")
    print(f"Duplicate candidates     : {duplicate_count}")
    print(f"Cross-type review needed : {review_count}")
    print("=" * 80)
    print()
    print("No files were modified.")


def build_duplicate_groups(reports: list[dict]) -> list[list[dict]]:
    """
    Build duplicate groups from pairwise duplicate analysis.

    This function never modifies files.
    """

    # Memory ID -> group index
    memory_to_group: dict[str, int] = {}

    groups: list[list[dict]] = []

    for report in reports:
        duplicate_id = report["duplicate_of"]

        if duplicate_id is None:
            continue

        memory = report["memory"]
        memory_id = memory["id"]

        # このペアに含まれる2つのMemory
        pair_ids = {
            memory_id,
            duplicate_id,
        }

        # 既存グループを探す
        existing_groups = {
            memory_to_group[memory_id]
            for memory_id in pair_ids
            if memory_id in memory_to_group
        }

        if not existing_groups:
            # 新しいグループ
            group_index = len(groups)
            groups.append([memory, report["duplicate"]])

            for memory_item in groups[group_index]:
                memory_to_group[memory_item["id"]] = group_index

        else:
            # 既存グループに追加
            group_index = min(existing_groups)

            for memory_item in [memory, report["duplicate"]]:
                if memory_item["id"] not in memory_to_group:
                    groups[group_index].append(memory_item)
                    memory_to_group[memory_item["id"]] = group_index

            # 複数の既存グループを接続する場合は統合
            for other_index in sorted(existing_groups - {group_index}, reverse=True):
                for memory_item in groups[other_index]:
                    if memory_item["id"] not in memory_to_group:
                        groups[group_index].append(memory_item)
                        memory_to_group[memory_item["id"]] = group_index

                groups.pop(other_index)

                # group indexを再構築
                memory_to_group = {}

                for index, group in enumerate(groups):
                    for memory_item in group:
                        memory_to_group[memory_item["id"]] = index

    return groups


def analyze_canonical_groups(groups: list[list[dict]]) -> list[dict]:
    """
    Analyze each duplicate group and select one canonical memory.

    This function performs Canonical selection exactly once per group.
    It does not modify any files.
    """

    results = []

    for index, group in enumerate(groups, start=1):
        canonical = select_canonical_memory(group)
        results.append(
            {
                "group_index": index,
                "group": group,
                "canonical": canonical,
            }
        )
    return results


def find_orphan_relations() -> list[dict]:
    """
    Find Relation files where either the source ('from') or target ('to') Memory file
    does not exist in active or archived Memory directories.
    """
    if not RELATIONS_ROOT.exists():
        return []

    existing_memory_stems = set()
    for path in MEMORY_ROOT.rglob("*.md"):
        if is_valid_memory_file(path):
            existing_memory_stems.add(path.stem)

    orphans = []
    for path in sorted(RELATIONS_ROOT.glob("*.json")):
        if not is_valid_relation_file(path):
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError, json.JSONDecodeError):
            continue

        from_id = data.get("from")
        to_id = data.get("to")

        from_exists = any(stem.startswith(from_id) for stem in existing_memory_stems) if from_id else False
        to_exists = any(stem.startswith(to_id) for stem in existing_memory_stems) if to_id else False

        if not from_exists or not to_exists:
            orphans.append(
                {
                    "path": path,
                    "data": data,
                    "missing_from": not from_exists,
                    "missing_to": not to_exists,
                }
            )

    return orphans


def print_orphan_relations(orphans: list[dict]) -> None:
    """
    Print detected orphan relations report.
    """
    print()
    print("=" * 80)
    print("ORPHAN RELATIONS REPORT")
    print("=" * 80)

    if not orphans:
        print()
        print("No orphan relations found.")
        print()
        print("=" * 80)
        return

    for index, item in enumerate(orphans, start=1):
        data = item["data"]
        path = item["path"]
        print()
        print(f"[{index}/{len(orphans)}] Relation ID: {data.get('id', path.stem)}")
        print(f"  File     : {path}")
        print(f"  From     : {data.get('from')} {'(MISSING)' if item['missing_from'] else '(OK)'}")
        print(f"  Relation : {data.get('relation')}")
        print(f"  To       : {data.get('to')} {'(MISSING)' if item['missing_to'] else '(OK)'}")

    print()
    print("=" * 80)
    print(f"Total Orphan Relations : {len(orphans)}")
    print("=" * 80)


def execute_clean_orphans(orphans: list[dict], confirm_yes: bool = False) -> None:
    """
    Delete orphan relation files.
    Prompts for interactive confirmation unless confirm_yes is True.
    """
    if not orphans:
        print()
        print("No orphan relations to clean.")
        return

    print_orphan_relations(orphans)

    if not confirm_yes:
        print()
        try:
            response = input(f"Are you sure you want to delete these {len(orphans)} orphan relation file(s)? [y/N]: ").strip().lower()
        except EOFError:
            print("Non-interactive mode detected and --yes flag not provided. Aborting deletion.")
            return

        if response not in ("y", "yes"):
            print("Operation cancelled. No files were deleted.")
            return

    deleted_count = 0
    failed_count = 0

    for item in orphans:
        path = item["path"]
        try:
            path.unlink()
            print(f"[DELETED] {path.name}")
            deleted_count += 1
        except OSError as e:
            print(f"[FAILED] {path.name}: {e}")
            failed_count += 1

    print()
    print("=" * 80)
    print("ORPHAN CLEANUP SUMMARY")
    print("=" * 80)
    print(f"Deleted : {deleted_count}")
    print(f"Failed  : {failed_count}")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze and clean ALICE_CoPilot memories."
    )

    parser.add_argument(
        "--archive",
        action="store_true",
        help="Move approved archive candidates to Archive.",
    )
    parser.add_argument(
        "--check-orphans",
        action="store_true",
        help="Check for orphan relations without making changes.",
    )
    parser.add_argument(
        "--clean-orphans",
        action="store_true",
        help="Delete orphan relations (prompts for confirmation unless --yes is passed).",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Confirm deletion without prompting when using --clean-orphans.",
    )

    args = parser.parse_args()

    if args.check_orphans:
        orphans = find_orphan_relations()
        print_orphan_relations(orphans)
        return

    if args.clean_orphans:
        orphans = find_orphan_relations()
        execute_clean_orphans(orphans, confirm_yes=args.yes)
        return

    reports = generate_report()
    print_report(reports)

    groups = build_duplicate_groups(reports)

    canonical_groups = analyze_canonical_groups(groups)

    print_duplicate_groups(canonical_groups)

    archive_candidates = build_archive_candidates(canonical_groups)

    print_archive_candidates(archive_candidates)

    if args.archive:
        execute_archive(archive_candidates)

if __name__ == "__main__":
    main()