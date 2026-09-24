from memory.memory_manager import process_memory
from memory.memory_search import search_memories


def test_memory_lifecycle_new_memory_can_be_found_by_search(
    memory_environment,
    monkeypatch,
):
    """
    A newly created Memory must become searchable after persistence.
    """

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "ライフサイクル統合テスト",
        "content": (
            "ALICE_CoPilotのMemoryライフサイクル統合テストとして、"
            "方式Bを採用することが決定した。"
        ),
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: [],
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: [],
    )

    result = process_memory(
        "ALICE_CoPilotのMemoryライフサイクル統合テストとして、"
        "方式Bを採用することが決定した。"
    )

    assert result["saved"] is True

    memory_path = result["path"]

    assert memory_path.exists()

    results = search_memories(
        query="ライフサイクル統合テスト",
        limit=10,
    )

    result_ids = [item["id"] for item in results]

    assert memory_path.stem in result_ids


def test_memory_lifecycle_duplicate_input_does_not_create_new_memory(
    memory_environment,
    monkeypatch,
):
    """
    Re-processing an equivalent Memory must detect the existing
    Memory as a duplicate and must not create another Memory.
    """

    text = (
        "ALICE_CoPilotのMemoryライフサイクル統合テストとして、"
        "方式Bを採用することが決定した。"
    )

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "ライフサイクル統合テスト",
        "content": text,
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda value: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: [],
    )

    duplicate_calls = 0
    def mock_duplicate(title, content, candidates):
        nonlocal duplicate_calls
        duplicate_calls += 1
        if duplicate_calls == 1:
            return None
        return candidates[0]["id"] if candidates else "existing_duplicate_id"

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        mock_duplicate,
    )

    # First pass: genuinely create the Memory.
    first_result = process_memory(text)

    assert first_result["saved"] is True

    first_memory_path = first_result["path"]

    assert first_memory_path.exists()

    memory_files_before = list(
        memory_environment.rglob("*.md")
    )

    assert len(memory_files_before) == 1

    # Second pass: the same Memory must be detected as duplicate.
    second_result = process_memory(text)

    assert second_result["saved"] is False
    assert second_result["duplicate"] is True
    assert second_result["duplicate_of"] == first_memory_path.stem
    assert second_result["path"] == first_memory_path

    memory_files_after = list(
        memory_environment.rglob("*.md")
    )

    assert memory_files_after == memory_files_before


def test_memory_lifecycle_new_memory_supersedes_existing_memory(
    memory_environment,
    monkeypatch,
):
    """
    A new Memory must be persisted together with a supersedes Relation.
    The old Memory remains unchanged and becomes Historical through
    the Relation graph.
    """

    from memory.long_term import (
        find_memory_by_id,
        find_superseded_memory_ids,
        load_relations,
    )

    old_memory_path = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_旧方式の決定.md"
    )

    old_memory_path.parent.mkdir(parents=True)

    old_memory_content = (
        "# 旧方式の決定\n\n"
        "方式Aを採用することが決定した。\n"
    )

    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    new_text = (
        "方式Aを廃止し、方式Bへ変更することが決定した。"
    )

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "新方式の決定",
        "content": new_text,
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    # The existing Memory must be found by the real search.
    #
    # The relation analysis itself is deterministic here so that
    # this test focuses on the persistence/lifecycle behavior.
    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: [
            {
                "id": old_memory_id,
                "relation": "supersedes",
            }
        ],
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    # New Memory must be reloadable.
    assert find_memory_by_id(new_memory_id) == new_memory_path

    # Old Memory must remain physically unchanged.
    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content

    # The Relation must be persisted with the correct direction:
    #
    #     new Memory
    #         |
    #     supersedes
    #         ↓
    #     old Memory
    #
    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "supersedes"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    # Historical status is derived from the Relation graph.
    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id in superseded_ids
    assert new_memory_id not in superseded_ids


def test_memory_lifecycle_conflicts_keeps_both_memories_current(
    memory_environment,
    monkeypatch,
):
    """
    A conflicting Memory must be persisted together with a conflicts
    Relation.

    Unlike supersedes, conflicts must not make the existing Memory
    Historical.
    """

    from memory.long_term import (
        find_memory_by_id,
        find_superseded_memory_ids,
        load_relations,
    )

    old_memory_path = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_監査ログ方針.md"
    )

    old_memory_path.parent.mkdir(parents=True)

    old_memory_content = (
        "# 監査ログ方針\n\n"
        "監査ログの保存を必須とする。\n"
    )

    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    new_text = (
        "監査ログの保存を禁止する。"
    )

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "新しい監査ログ方針",
        "content": new_text,
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: [
            {
                "id": old_memory_id,
                "relation": "conflicts",
            }
        ],
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    # New Memory must be reloadable.
    assert find_memory_by_id(new_memory_id) == new_memory_path

    # Old Memory must remain physically unchanged.
    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content

    # The conflicts Relation must be persisted.
    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "conflicts"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    # Unlike supersedes, conflicts does NOT make the old Memory
    # Historical.
    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id not in superseded_ids
    assert new_memory_id not in superseded_ids


def test_memory_lifecycle_related_persists_without_changing_memory_status(
    memory_environment,
    monkeypatch,
):
    """
    A related Memory must be persisted together with a related Relation.

    Unlike supersedes, a related Relation must not make either Memory
    Historical.
    """

    from memory.long_term import (
        find_memory_by_id,
        find_superseded_memory_ids,
        load_relations,
    )

    existing_memory_path = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_既存方針.md"
    )

    existing_memory_path.parent.mkdir(parents=True)

    existing_memory_content = (
        "# 既存方針\n\n"
        "監査ログの保存方式を定義する。\n"
    )

    existing_memory_path.write_text(
        existing_memory_content,
        encoding="utf-8",
    )

    existing_memory_id = existing_memory_path.stem

    new_text = (
        "監査ログの保存方式に関連する補足事項を記録する。"
    )

    classified_result = {
        "should_remember": True,
        "type": "context",
        "title": "監査ログ保存方式の補足",
        "content": new_text,
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: [
            {
                "id": existing_memory_id,
                "relation": "related",
            }
        ],
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != existing_memory_path

    new_memory_id = new_memory_path.stem

    # New Memory must be reloadable.
    assert find_memory_by_id(new_memory_id) == new_memory_path

    # Existing Memory must remain unchanged.
    assert existing_memory_path.exists()
    assert existing_memory_path.read_text(
        encoding="utf-8"
    ) == existing_memory_content

    # The related Relation must be persisted with the correct direction.
    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "related"
        and relation.get("to") == existing_memory_id
    ]

    assert len(matching_relations) == 1

    # related does not make either Memory Historical.
    superseded_ids = find_superseded_memory_ids()

    assert existing_memory_id not in superseded_ids
    assert new_memory_id not in superseded_ids