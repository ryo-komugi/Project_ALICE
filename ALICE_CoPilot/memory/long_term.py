from datetime import datetime
import json
import os
import secrets
from pathlib import Path

import config


MEMORY_ROOT = config.MEMORY_ROOT
RELATIONS_ROOT = config.RELATIONS_ROOT
ARCHIVE_ROOT = config.ARCHIVE_ROOT


TYPE_DIRECTORIES = {
    "context": "Context",
    "project": "Projects",
    "decision": "Decisions",
    "knowledge": "Knowledge",
    "idea": "Ideas",
    "conversation": "Conversations",
}


ALLOWED_RELATIONS = {
    "related",
    "supersedes",
    "conflicts",
}


def is_valid_memory_file(path: Path) -> bool:
    """
    Check if a path is a valid Memory Markdown file.
    Excludes Syncthing conflict files and hidden/temp files.
    """
    if not path.is_file():
        return False
    name = path.name
    if name.startswith(".") or ".sync-conflict-" in name or name.endswith(".tmp"):
        return False
    return True


def is_valid_relation_file(path: Path) -> bool:
    """
    Check if a path is a valid Relation JSON file.
    Excludes Syncthing conflict files and hidden/temp files.
    """
    if not path.is_file():
        return False
    name = path.name
    if name.startswith(".") or ".sync-conflict-" in name or name.endswith(".tmp"):
        return False
    return True


def _atomic_write_text(filepath: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Atomically write text content to filepath using a temporary file in the same directory.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_name(f".{filepath.name}.tmp_{secrets.token_hex(4)}")
    try:
        tmp_path.write_text(content, encoding=encoding)
        os.replace(str(tmp_path), str(filepath))
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def create_memory(memory_type: str, title: str, content: str) -> Path:
    """
    Create one immutable Markdown memory.

    Args:
        memory_type:
            context / project / decision / knowledge / idea / conversation

        title:
            Human-readable title.

        content:
            Main memory content.

    Returns:
        Path of the created Markdown file.

    The created Memory is immutable.
    This function never modifies an existing Memory.
    """

    memory_type = memory_type.lower().strip()

    if memory_type not in TYPE_DIRECTORIES:
        raise ValueError(
            f"Unknown memory type: {memory_type}. "
            f"Allowed: {', '.join(TYPE_DIRECTORIES)}"
        )

    directory = MEMORY_ROOT / TYPE_DIRECTORIES[memory_type]
    directory.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    rand_suffix = secrets.token_hex(2)
    memory_id = f"{now.strftime('%Y%m%d_%H%M%S_%f')}_{rand_suffix}"

    safe_title = _sanitize_filename(title)

    filename = f"{memory_id}_{safe_title}.md"
    filepath = directory / filename

    markdown = f"""# {title}

{content}
"""

    _atomic_write_text(filepath, markdown, encoding="utf-8")

    return filepath


def _would_create_supersedes_cycle(
    from_memory_id: str,
    to_memory_id: str,
) -> bool:
    """
    Return True when adding:

        from_memory_id -> supersedes -> to_memory_id

    would create a cycle in the existing supersedes graph.
    """

    if from_memory_id == to_memory_id:
        return True

    relations = load_relations()

    supersedes_targets: dict[str, set[str]] = {}

    for relation in relations:
        if relation.get("relation") != "supersedes":
            continue

        source = relation.get("from")
        target = relation.get("to")

        if not source or not target:
            continue

        supersedes_targets.setdefault(source, set()).add(target)

    visited: set[str] = set()
    stack = [to_memory_id]

    while stack:
        current = stack.pop()

        if current == from_memory_id:
            return True

        if current in visited:
            continue

        visited.add(current)
        stack.extend(
            supersedes_targets.get(current, set())
        )

    return False



def create_relation(from_memory_id: str, relation: str, to_memory_id: str) -> Path:
    """
    Create one immutable Relation JSON file.

    Args:
        from_memory_id:
            ID of the Memory from which the relation originates.

        relation:
            related / supersedes / conflicts

        to_memory_id:
            ID of the target Memory.

    Returns:
        Path of the created Relation JSON file.

    Relation direction:

        new Memory
            --supersedes-->
        old Memory

    A Relation is immutable once created.
    This function never modifies an existing Relation.
    """

    relation = relation.lower().strip()

    if relation not in ALLOWED_RELATIONS:
        raise ValueError(
            f"Unknown relation: {relation}. "
            f"Allowed: {', '.join(sorted(ALLOWED_RELATIONS))}"
        )

    if not from_memory_id:
        raise ValueError("from_memory_id is required")

    if not to_memory_id:
        raise ValueError("to_memory_id is required")

    if relation == "supersedes":
        if _would_create_supersedes_cycle(
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
        ):
            raise ValueError(
                "supersedes relation would create a cycle: "
                f"{from_memory_id} -> {to_memory_id}"
            )

    RELATIONS_ROOT.mkdir(parents=True, exist_ok=True)

    now = datetime.now().astimezone()
    rand_suffix = secrets.token_hex(2)
    relation_id = f"{now.strftime('%Y%m%d_%H%M%S_%f')}_{rand_suffix}"

    relation_data = {
        "id": relation_id,
        "from": from_memory_id,
        "relation": relation,
        "to": to_memory_id,
        "created_at": now.isoformat(),
    }

    filepath = RELATIONS_ROOT / f"{relation_id}.json"

    _atomic_write_text(
        filepath,
        json.dumps(relation_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return filepath


def load_relations() -> list[dict]:
    """
    Load all Relation JSON files.

    Returns:
        List of Relation dictionaries.

    This function never modifies files.
    """

    if not RELATIONS_ROOT.exists():
        return []

    relations = []

    for path in sorted(RELATIONS_ROOT.glob("*.json")):
        if not is_valid_relation_file(path):
            continue

        try:
            text = path.read_text(encoding="utf-8")

            relation = json.loads(text)

        except (UnicodeDecodeError, OSError, json.JSONDecodeError):
            continue

        relations.append(relation)

    return relations


def find_superseded_memory_ids() -> set[str]:
    """
    Find all Memory IDs that are targets of a supersedes Relation.

    A Memory is considered historical when another Memory
    supersedes it.

    Relation direction:

        new Memory
            --supersedes-->
        old Memory

    Therefore, the `to` side of a supersedes Relation
    represents a Historical Memory.

    Returns:
        Set of Memory IDs that have been superseded.

    This function never modifies files.
    """

    superseded_ids = set()

    for relation in load_relations():
        if relation.get("relation") != "supersedes":
            continue

        memory_id = relation.get("to")

        if memory_id:
            superseded_ids.add(memory_id)

    return superseded_ids


def find_relations_for_memory(memory_id: str) -> list[dict]:
    """
    Find all Relations involving the specified Memory.

    A Relation is considered relevant when the Memory is
    either the source or target.

    This function never modifies files.
    """

    if not memory_id:
        return []

    return [
        relation
        for relation in load_relations()
        if (
            relation.get("from") == memory_id
            or relation.get("to") == memory_id
        )
    ]


def find_outgoing_relations(memory_id: str) -> list[dict]:
    """
    Find Relations originating from the specified Memory.

    This function never modifies files.
    """

    if not memory_id:
        return []

    return [
        relation
        for relation in load_relations()
        if relation.get("from") == memory_id
    ]


def find_incoming_relations(memory_id: str) -> list[dict]:
    """
    Find Relations pointing to the specified Memory.

    This function never modifies files.
    """

    if not memory_id:
        return []

    return [
        relation
        for relation in load_relations()
        if relation.get("to") == memory_id
    ]


def find_related_memories(memory_id: str) -> list[str]:
    """
    Find Memory IDs related to the specified Memory.

    Related relations are treated as bidirectional for lookup,
    regardless of their stored direction.

    This function never modifies files.
    """

    if not memory_id:
        return []

    related_ids = []

    for relation in load_relations():
        if relation.get("relation") != "related":
            continue

        from_id = relation.get("from")
        to_id = relation.get("to")

        if from_id == memory_id and to_id:
            related_ids.append(to_id)

        elif to_id == memory_id and from_id:
            related_ids.append(from_id)

    return list(dict.fromkeys(related_ids))


def find_superseded_memories(memory_id: str) -> list[str]:
    """
    Find Memory IDs that were superseded by the specified Memory.

    Example:

        B --supersedes--> A

    find_superseded_memories(B)
        -> [A]

    This function never modifies files.
    """

    if not memory_id:
        return []

    return [
        relation["to"]
        for relation in load_relations()
        if (
            relation.get("from") == memory_id
            and relation.get("relation") == "supersedes"
            and relation.get("to")
        )
    ]

def find_superseding_memories(memory_id: str) -> list[str]:
    """
    Find Memory IDs that supersede the specified Memory.

    Example:

        B --supersedes--> A

    find_superseding_memories(A)
        -> [B]

    This function never modifies files.
    """

    if not memory_id:
        return []

    return [
        relation["from"]
        for relation in load_relations()
        if (
            relation.get("to") == memory_id
            and relation.get("relation") == "supersedes"
            and relation.get("from")
        )
    ]


def find_conflicting_memories(memory_id: str) -> list[str]:
    """
    Find Memory IDs that conflict with the specified Memory.

    Conflict relations are treated as bidirectional for lookup,
    regardless of their stored direction.

    This function never modifies files.
    """

    if not memory_id:
        return []

    conflicting_ids = []

    for relation in load_relations():
        if relation.get("relation") != "conflicts":
            continue

        from_id = relation.get("from")
        to_id = relation.get("to")

        if from_id == memory_id and to_id:
            conflicting_ids.append(to_id)

        elif to_id == memory_id and from_id:
            conflicting_ids.append(from_id)

    return list(dict.fromkeys(conflicting_ids))


def find_memory_by_id(memory_id: str, include_archive: bool = False) -> Path | None:
    """
    Find a Memory Markdown file by its unique ID.

    By default, search includes active Memory directories.
    Set include_archive=True to include Archive.

    This function never modifies files.
    """

    if not memory_id:
        return None

    for path in MEMORY_ROOT.rglob("*.md"):
        if not is_valid_memory_file(path):
            continue

        if not include_archive and ARCHIVE_ROOT in path.parents:
            continue

        if path.stem.startswith(memory_id):
            return path

    return None


def _sanitize_filename(value: str) -> str:
    """
    Sanitize a title for use as a filename.
    """

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        value = value.replace(char, "_")

    value = value.strip()

    if not value:
        value = "memory"

    return value