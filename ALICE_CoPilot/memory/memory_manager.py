from memory.memory_classifier import classify_memory
from memory.memory_relation import (
    analyze_memory_relations,
    find_duplicate_memory,
    find_memory_candidates,
    reevaluate_relations_for_memory,
)
from memory.long_term import (create_memory, create_relation, find_memory_by_id)


def process_memory(text: str):

    # 1. Decide whether this should become long-term memory.
    result = classify_memory(text)

    if not result["should_remember"]:
        return {
            "saved": False,
            "result": result,
            "path": None,
            "related": [],
            "relations": [],
        }

    # 2. Find existing candidate memories BEFORE creating.
    candidates = find_memory_candidates(
        title=result["title"],
        content=result["content"],
    )

    # 3. Check whether an equivalent memory already exists.
    # Duplicate detection is the gate for creating a new Memory.
    duplicate_id = find_duplicate_memory(
        title=result["title"],
        content=result["content"],
        candidates=candidates,
    )

    if duplicate_id is not None:
        duplicate_path = find_memory_by_id(duplicate_id)

        return {
            "saved": False,
            "duplicate": True,
            "duplicate_of": duplicate_id,
            "result": result,
            "path": duplicate_path,
            "related": [],
            "relations": [],
        }

    # 4. Create the new immutable Memory.
    path = create_memory(
        memory_type=result["type"],
        title=result["title"],
        content=result["content"],
    )

    # 5. Common relation re-evaluation for the newly created Memory.
    created_relations = reevaluate_relations_for_memory(
        memory_id=path.stem,
        title=result["title"],
        content=result["content"],
        candidates=candidates,
        analyze_fn=analyze_memory_relations,
        create_rel_fn=create_relation,
    )

    related_ids = [
        item["memory_id"]
        for item in created_relations
        if item["relation"] == "related"
    ]

    return {
        "saved": True,
        "result": result,
        "path": path,
        "related": related_ids,
        "relations": created_relations,
    }