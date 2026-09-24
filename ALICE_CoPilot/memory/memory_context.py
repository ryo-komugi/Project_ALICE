from memory.long_term import (
    find_memory_by_id,
    find_related_memories,
    find_superseded_memories,
    find_superseding_memories,
    find_conflicting_memories,
    find_relations_for_memory,
)
from memory.memory_subject import (
    extract_memory_subject,
    filter_memories_by_subject,
)


def _matches_query_subject(memory: dict, query_subjects: set[str]) -> bool:
    """
    Check whether a Memory belongs to the query subject.

    Memories without an explicit subject identifier are preserved.
    """

    if not query_subjects:
        return True
    memory_subjects = extract_memory_subject(memory.get("content", ""))
    if not memory_subjects:
        return True
    return bool(query_subjects & memory_subjects)


def _load_memory(memory_id: str, include_archive: bool = False) -> dict | None:
    """
    Load a Memory by ID.

    This function never modifies files.
    """

    path = find_memory_by_id(memory_id, include_archive=include_archive)

    if path is None:
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None

    return {
        "id": memory_id,
        "path": str(path),
        "content": content,
    }


def _append_memory(memories: list[dict], memory_id: str, query_subjects: set[str] | None = None, include_archive: bool = False) -> None:
    """
    Append a Memory if it exists, matches the query subject,
    and is not already present.

    Memories without an explicit subject identifier are preserved.
    """

    if not memory_id:
        return

    if any(item["id"] == memory_id for item in memories):
        return

    memory = _load_memory(memory_id, include_archive=include_archive)

    if memory is None:
        return

    if query_subjects is not None:
        if not _matches_query_subject(memory, query_subjects):
            return

    memories.append(memory)


def _memory_timestamp(memory_id: str) -> str:
    """
    Extract the timestamp prefix from a Memory ID.

    Memory ID format:
        YYYYMMDD_HHMMSS_microseconds_Title

    The fixed-width timestamp prefix can be compared
    lexicographically because it follows chronological order.
    """

    if not memory_id:
        return ""
    parts = memory_id.split("_", 3)

    if len(parts) < 3:
        return ""
    return "_".join(parts[:3])


def _deduplicate_context_categories(context: dict) -> None:
    """
    Remove duplicate Memory IDs across Context categories.

    Higher-priority categories take precedence over lower-priority
    categories.

    Priority:
        primary
        related
        superseding
        superseded
        conflicting

    This function only modifies the in-memory context structure.
    It never modifies Memory or Relation files.
    """

    priority = [
        "primary",
        "related",
        "superseding",
        "superseded",
        "conflicting",
    ]

    seen_ids = set()

    for category in priority:
        memories = context.get(category, [])

        filtered = []

        for memory in memories:
            memory_id = memory.get("id")

            if not memory_id:
                continue

            if memory_id in seen_ids:
                continue

            seen_ids.add(memory_id)
            filtered.append(memory)

        context[category] = filtered


def build_memory_context(memories: list[dict], query: str = "") -> dict:
    """
    Build a structured Memory Context from search results.

    Search results are treated as candidate Memories.

    If a candidate Memory has been superseded by a newer Memory,
    the newer Memory is resolved as the current Primary Memory.

    Superseding relations are followed until the latest Memory
    is reached. This allows multiple successive updates:

        A --supersedes--> B
        B --supersedes--> C

    to resolve C as the current Memory.

    Older Memories are retained as Superseded history.

    Conflicting Memories are handled separately.

    The function never modifies Memory or Relation files.
    """

    context = {
        "primary": [],
        "related": [],
        "superseded": [],
        "superseding": [],
        "conflicting": [],
    }

    query_subjects = extract_memory_subject(query)

    if query:
        memories = filter_memories_by_subject(
            title="",
            content=query,
            candidates=memories,
        )

    # ---------------------------------------------------------
    # 1. Resolve the latest Memory for each search candidate
    #
    # Example:
    #
    #   ALPHA
    #      ^
    #      | supersedes
    #      |
    #   BETA
    #
    # Search result may contain only ALPHA.
    # In that case BETA must still become Primary.
    # ---------------------------------------------------------

    resolved_primary_ids = set()
    resolved_superseded_ids = set()

    def resolve_latest_memory(memory_id: str) -> tuple[str | None, list[str]]:
        """
        Follow superseding relations until the latest Memory.

        Returns:
            (latest_memory_id, superseded_memory_ids)

        The traversal is cycle-safe.
        """

        if not memory_id:
            return None, []

        current_id = memory_id
        history = []
        visited = set()

        while current_id:
            if current_id in visited:
                return None, history

            visited.add(current_id)

            superseding_ids = find_superseding_memories(current_id)

            if not superseding_ids:
                break

            # Normally there should be one superseding Memory.
            # If multiple exist, use the newest Memory.
            candidates = []

            for candidate_id in superseding_ids:
                candidate = _load_memory(candidate_id)

                if candidate is None:
                    continue

                candidates.append(candidate)

            if not candidates:
                break

            candidates.sort(
                key=lambda item: _memory_timestamp(item["id"]),
                reverse=True,
            )

            next_memory = candidates[0]
            next_id = next_memory["id"]

            history.append(current_id)
            current_id = next_id

        return current_id, history

    # ---------------------------------------------------------
    # 2. Resolve current Primary Memories
    # ---------------------------------------------------------

    for memory in memories:
        memory_id = memory.get("id")

        if not memory_id:
            continue

        latest_id, superseded_history = resolve_latest_memory(memory_id)

        if latest_id is None:
            continue

        latest_memory = _load_memory(latest_id)

        if latest_memory is None:
            continue

        # Respect query subject filtering for the current Memory.
        if not _matches_query_subject(latest_memory, query_subjects):
            continue

        resolved_primary_ids.add(latest_id)

        for old_id in superseded_history:
            resolved_superseded_ids.add(old_id)

        if latest_id not in {
            item["id"]
            for item in context["primary"]
        }:
            context["primary"].append(latest_memory)

    # ---------------------------------------------------------
    # 3. Preserve explicitly searched Memories that were
    #    superseded during resolution.
    # ---------------------------------------------------------

    for memory in memories:
        memory_id = memory.get("id")

        if not memory_id:
            continue

        if memory_id in resolved_primary_ids:
            continue

        if memory_id in resolved_superseded_ids:
            _append_memory(
                context["superseded"],
                memory_id,
                query_subjects=query_subjects,
            )

    # ---------------------------------------------------------
    # 4. Add the complete superseded history for each Primary
    #
    # Example:
    #
    #   C --supersedes--> B
    #   B --supersedes--> A
    #
    # Primary:
    #   C
    #
    # Superseded:
    #   B
    #   A
    # ---------------------------------------------------------

    for primary_memory in list(context["primary"]):
        primary_id = primary_memory.get("id")

        if not primary_id:
            continue

        # Walk backwards through the superseded chain.
        current_id = primary_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)

            superseded_ids = find_superseded_memories(current_id)

            if not superseded_ids:
                break

            for superseded_id in superseded_ids:
                _append_memory(
                    context["superseded"],
                    superseded_id,
                    query_subjects=query_subjects,
                )

                resolved_superseded_ids.add(superseded_id)

            # Continue through the newest superseded Memory if there
            # are multiple candidates.
            candidates = []

            for candidate_id in superseded_ids:
                candidate = _load_memory(candidate_id)

                if candidate is not None:
                    candidates.append(candidate)

            if not candidates:
                break

            candidates.sort(
                key=lambda item: _memory_timestamp(item["id"]),
                reverse=True,
            )

            current_id = candidates[0]["id"]

    # ---------------------------------------------------------
    # 5. Resolve Related / Conflicting relations
    # ---------------------------------------------------------

    for primary_memory in context["primary"]:
        memory_id = primary_memory.get("id")

        if not memory_id:
            continue

        for related_id in find_related_memories(memory_id):
            if related_id in resolved_superseded_ids:
                continue

            _append_memory(
                context["related"],
                related_id,
                query_subjects=query_subjects,
            )

        for conflicting_id in find_conflicting_memories(memory_id):
            if conflicting_id in resolved_superseded_ids:
                continue

            _append_memory(
                context["conflicting"],
                conflicting_id,
                query_subjects=query_subjects,
            )

    # ---------------------------------------------------------
    # 6. Resolve conflicting Memories
    #
    # Conflicts are different from supersedes.
    #
    # Supersedes:
    #   old -> new
    #   old is historical
    #
    # Conflicts:
    #   two Memories cannot both be treated as the same
    #   current fact.
    #
    # For conflicts, the newest Memory remains Primary and
    # older conflicting Memories are preserved as Conflicting.
    # ---------------------------------------------------------

    conflict_candidates = {}

    for primary_memory in list(context["primary"]):
        memory_id = primary_memory.get("id")

        if not memory_id:
            continue

        for conflicting_id in find_conflicting_memories(memory_id):
            conflict_candidates.setdefault(memory_id, set()).add(
                conflicting_id
            )

    for memory_id, related_ids in conflict_candidates.items():
        candidate_ids = {memory_id, *related_ids}

        candidate_memories = []

        for candidate_id in candidate_ids:
            if candidate_id in resolved_superseded_ids:
                continue

            memory = _load_memory(candidate_id)

            if memory is None:
                continue

            if not _matches_query_subject(memory, query_subjects):
                continue

            candidate_memories.append(memory)

        if not candidate_memories:
            continue

        candidate_memories.sort(
            key=lambda item: _memory_timestamp(item["id"]),
            reverse=True,
        )

        current_memory = candidate_memories[0]
        current_id = current_memory["id"]

        # Keep only the newest conflicting Memory as Primary.
        #
        # Older conflicting Memories must not remain Primary.
        # They are preserved in the Conflicting category.

        older_conflicting_ids = {
            memory["id"]
            for memory in candidate_memories[1:]
        }

        context["primary"] = [
            memory
            for memory in context["primary"]
            if memory["id"] not in older_conflicting_ids
        ]

        # Ensure the newest conflicting Memory is Primary.
        if not any(
            memory["id"] == current_id
            for memory in context["primary"]
        ):
            context["primary"].append(current_memory)

        # Preserve older conflicting Memories as Conflicting.
        for old_memory in candidate_memories[1:]:
            _append_memory(
                context["conflicting"],
                old_memory["id"],
                query_subjects=query_subjects,
            )

    # ---------------------------------------------------------
    # 7. Resolve multiple Primary Memories for the same subject
    #
    # A broken/incomplete supersedes chain may leave multiple
    # Primary Memories for the same explicit subject.
    #
    # However, conflicting Memories must NOT be treated as
    # superseded merely because they share the same subject.
    #
    # Therefore:
    #
    #   supersedes relation
    #       -> older Memory becomes Superseded
    #
    #   conflicts relation
    #       -> older Memory becomes Conflicting
    #
    # Only Memories that are not in a conflict relationship
    # are eligible for subject-based Primary resolution.
    # ---------------------------------------------------------

    if query_subjects and len(context["primary"]) > 1:
        subject_primary_groups = {}

        for memory in context["primary"]:
            memory_subjects = extract_memory_subject(
                memory.get("content", "")
            )

            matched_subjects = query_subjects & memory_subjects

            for subject in matched_subjects:
                subject_primary_groups.setdefault(
                    subject,
                    []
                ).append(memory)

        for subject, subject_memories in subject_primary_groups.items():
            if len(subject_memories) <= 1:
                continue

            # -------------------------------------------------
            # Exclude Memories that are explicitly conflicting.
            #
            # A conflict means that both Memories represent
            # mutually incompatible states of the same subject.
            # The older one must remain Conflicting, not
            # Superseded.
            # -------------------------------------------------

            conflict_ids = set()

            subject_memory_ids = {
                memory["id"]
                for memory in subject_memories
            }

            for memory in subject_memories:
                memory_id = memory["id"]

                conflicting_ids = set(
                    find_conflicting_memories(memory_id)
                )

                conflict_ids.update(
                    conflicting_ids & subject_memory_ids
                )

            non_conflicting_memories = [
                memory
                for memory in subject_memories
                if memory["id"] not in conflict_ids
            ]

            # If all candidates are involved in a conflict,
            # do not perform subject-based superseded resolution.
            if len(non_conflicting_memories) <= 1:
                continue

            non_conflicting_memories.sort(
                key=lambda item: _memory_timestamp(item["id"]),
                reverse=True,
            )

            current_memory = non_conflicting_memories[0]
            current_id = current_memory["id"]

            for old_memory in non_conflicting_memories[1:]:
                old_id = old_memory["id"]

                if old_id == current_id:
                    continue

                _append_memory(
                    context["superseded"],
                    old_id,
                    query_subjects=query_subjects,
                )

                resolved_superseded_ids.add(old_id)

                context["primary"] = [
                    memory
                    for memory in context["primary"]
                    if memory["id"] != old_id
                ]

            # -------------------------------------------------
            # Conflicting Memories remain outside Primary.
            # They are explicitly represented as Conflicting.
            # -------------------------------------------------

            for memory in subject_memories:
                memory_id = memory["id"]

                if memory_id not in conflict_ids:
                    continue

                _append_memory(
                    context["conflicting"],
                    memory_id,
                    query_subjects=query_subjects,
                )

                context["primary"] = [
                    primary
                    for primary in context["primary"]
                    if primary["id"] != memory_id
                ]

    # ---------------------------------------------------------
    # 8. Remove duplicate Memories across Context categories
    # ---------------------------------------------------------

    _deduplicate_context_categories(context)

    return context


def format_memory_context(context: dict) -> str:
    """
    Format structured Memory Context for LLM input.

    Relation direction is explicitly included so that the LLM
    can distinguish the semantic meaning of each relationship.

    The function never modifies Memory or Relation files.
    """

    sections = []

    primary = context.get("primary", [])
    related = context.get("related", [])
    superseded = context.get("superseded", [])
    superseding = context.get("superseding", [])
    conflicting = context.get("conflicting", [])

    if primary:
        parts = ["【Primary Memory】"]

        for memory in primary:
            parts.append(
                f"ID: {memory['id']}\n\n"
                f"{memory['content']}"
            )

        sections.append("\n\n".join(parts))

    if related:
        parts = ["【Related Memory】"]

        for memory in related:
            parts.append(
                f"ID: {memory['id']}\n"
                f"Relation: related\n\n"
                f"{memory['content']}"
            )

        sections.append("\n\n".join(parts))

    if superseded:
        parts = ["【Superseded Memory】"]

        for memory in superseded:
            memory_id = memory["id"]

            relations = find_relations_for_memory(memory_id)

            direction_lines = []

            for relation in relations:
                if (
                    relation.get("relation") == "supersedes"
                    and relation.get("to") == memory_id
                ):
                    direction_lines.append(
                        f"{relation['from']} "
                        f"--supersedes--> "
                        f"{relation['to']}"
                    )

            relation_text = "\n".join(direction_lines)

            entry = (
                f"ID: {memory_id}\n"
                f"Relation: superseded"
            )

            if relation_text:
                entry += (
                    f"\nDirection: {relation_text}"
                )

            entry += f"\n\n{memory['content']}"

            parts.append(entry)

        sections.append("\n\n".join(parts))

    if superseding:
        parts = ["【Superseding Memory】"]

        for memory in superseding:
            memory_id = memory["id"]

            relations = find_relations_for_memory(memory_id)

            direction_lines = []

            for relation in relations:
                if (
                    relation.get("relation") == "supersedes"
                    and relation.get("from") == memory_id
                ):
                    direction_lines.append(
                        f"{relation['from']} "
                        f"--supersedes--> "
                        f"{relation['to']}"
                    )

            relation_text = "\n".join(direction_lines)

            entry = (
                f"ID: {memory_id}\n"
                f"Relation: superseding"
            )

            if relation_text:
                entry += (
                    f"\nDirection: {relation_text}"
                )

            entry += f"\n\n{memory['content']}"

            parts.append(entry)

        sections.append("\n\n".join(parts))

    if conflicting:
        parts = ["【Conflicting Memory】"]

        for memory in conflicting:
            memory_id = memory["id"]

            relations = find_relations_for_memory(memory_id)

            direction_lines = []

            for relation in relations:
                if relation.get("relation") == "conflicts":
                    direction_lines.append(
                        f"{relation['from']} "
                        f"--conflicts--> "
                        f"{relation['to']}"
                    )

            relation_text = "\n".join(direction_lines)

            entry = (
                f"ID: {memory_id}\n"
                f"Relation: conflicts"
            )

            if relation_text:
                entry += (
                    f"\nDirection: {relation_text}"
                )

            entry += f"\n\n{memory['content']}"

            parts.append(entry)

        sections.append("\n\n".join(parts))

    return "\n\n\n".join(sections)