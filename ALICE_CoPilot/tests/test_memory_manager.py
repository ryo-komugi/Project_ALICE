from pathlib import Path

from memory.memory_manager import process_memory


def test_duplicate_memory_returns_without_creating_new_memory(
    monkeypatch,
):
    """
    When an equivalent Memory already exists,
    process_memory() must return immediately.

    Relation analysis and new Memory creation must not occur.
    """

    duplicate_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "supersedesテストの方式変更",
        "content": "方式Aを廃止して方式Bへ変更する。",
    }

    candidates = [
        {
            "id": duplicate_id,
            "path": "",
            "content": "方式Aを廃止して方式Bへ変更する。",
            "score": 10,
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: duplicate_id,
    )

    duplicate_path = Path("/data/memory/copilot/decision/existing.md")

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_by_id",
        lambda memory_id: duplicate_path,
    )

    def fail_analyze_memory_relations(*args, **kwargs):
        raise AssertionError(
            "analyze_memory_relations() must not be called "
            "when duplicate_memory is detected."
        )

    def fail_create_memory(*args, **kwargs):
        raise AssertionError(
            "create_memory() must not be called "
            "when duplicate_memory is detected."
        )

    def fail_create_relation(*args, **kwargs):
        raise AssertionError(
            "create_relation() must not be called "
            "when duplicate_memory is detected."
        )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        fail_analyze_memory_relations,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_memory",
        fail_create_memory,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_relation",
        fail_create_relation,
    )

    result = process_memory("方式Aを廃止して方式Bへ変更する。")

    assert result == {
        "saved": False,
        "duplicate": True,
        "duplicate_of": duplicate_id,
        "result": classified_result,
        "path": duplicate_path,
        "related": [],
        "relations": [],
    }


def test_new_memory_is_saved_with_relations(
    monkeypatch,
):
    """
    A genuinely new Memory is saved and the relations
    returned by relation analysis are persisted.
    """

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "テスト方式の決定",
        "content": "方式Bを採用することが決定した。",
    }

    candidates = [
        {
            "id": "existing-memory-id",
            "path": "",
            "content": "方式Aを採用することが決定していた。",
            "score": 10,
        }
    ]

    new_memory_path = Path(
        "/data/memory/copilot/Decisions/"
        "20260815_120000_000000_テスト方式の決定.md"
    )

    relation_path = Path(
        "/data/memory/copilot/Relations/"
        "20260815_120000_000000_テスト方式の決定__related__existing-memory-id.json"
    )

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    relations = [
        {
            "id": "existing-memory-id",
            "relation": "related",
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: relations,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_memory",
        lambda memory_type, title, content: new_memory_path,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_relation",
        lambda from_memory_id, relation, to_memory_id: relation_path,
    )

    result = process_memory(
        "方式Bを採用することが決定した。"
    )

    assert result["saved"] is True
    assert result["result"] == classified_result
    assert result["path"] == new_memory_path
    assert result["related"] == [
        "existing-memory-id"
    ]
    assert result["relations"] == [
        {
            "relation": "related",
            "memory_id": "existing-memory-id",
            "path": relation_path,
        }
    ]


def test_memory_not_worth_remembering_returns_without_processing(
    monkeypatch,
):
    """
    When classify_memory() determines that the input should not
    become long-term memory, process_memory() must return
    immediately without searching, analyzing, or creating anything.
    """

    classified_result = {
        "should_remember": False,
        "type": "context",
        "title": "",
        "content": "",
    }

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    def fail_find_memory_candidates(*args, **kwargs):
        raise AssertionError(
            "find_memory_candidates() must not be called "
            "when should_remember is False."
        )

    def fail_find_duplicate_memory(*args, **kwargs):
        raise AssertionError(
            "find_duplicate_memory() must not be called "
            "when should_remember is False."
        )

    def fail_analyze_memory_relations(*args, **kwargs):
        raise AssertionError(
            "analyze_memory_relations() must not be called "
            "when should_remember is False."
        )

    def fail_create_memory(*args, **kwargs):
        raise AssertionError(
            "create_memory() must not be called "
            "when should_remember is False."
        )

    def fail_create_relation(*args, **kwargs):
        raise AssertionError(
            "create_relation() must not be called "
            "when should_remember is False."
        )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        fail_find_memory_candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        fail_find_duplicate_memory,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        fail_analyze_memory_relations,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_memory",
        fail_create_memory,
    )

    monkeypatch.setattr(
        "memory.memory_manager.create_relation",
        fail_create_relation,
    )

    result = process_memory(
        "これは長期記憶として保存する必要のない情報です。"
    )

    assert result == {
        "saved": False,
        "result": classified_result,
        "path": None,
        "related": [],
        "relations": [],
    }

def test_new_memory_is_persisted_and_reloadable(
    memory_environment,
    monkeypatch,
):
    """
    A genuinely new Memory must be persisted to disk together with
    its Relation, and both must be reloadable from the Memory store.
    """

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "永続化テストの決定",
        "content": "方式Bを採用することが決定した。",
    }

    candidate_id = "existing-memory-id"

    candidates = [
        {
            "id": candidate_id,
            "path": "",
            "content": "方式Aを採用することが決定していた。",
            "score": 10,
        }
    ]

    relations = [
        {
            "id": candidate_id,
            "relation": "related",
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: relations,
    )

    result = process_memory(
        "方式Bを採用することが決定した。"
    )

    assert result["saved"] is True

    memory_path = result["path"]

    assert memory_path.exists()
    assert memory_path.parent.exists()
    assert memory_path.suffix == ".md"

    memory_id = memory_path.stem

    from memory.long_term import find_memory_by_id, load_relations

    reloaded_memory = find_memory_by_id(memory_id)

    assert reloaded_memory == memory_path

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == memory_id
        and relation.get("relation") == "related"
        and relation.get("to") == candidate_id
    ]

    assert len(matching_relations) == 1


def test_duplicate_memory_does_not_persist_new_memory(
    memory_environment,
    monkeypatch,
):
    """
    When an equivalent Memory already exists,
    process_memory() must not create a new Memory or Relation.
    """

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "Duplicate永続化テスト",
        "content": "方式Aを採用することが決定した。",
    }

    existing_memory_path = memory_environment / "decision" / (
        "20260815_120000_000000_既存Memory.md"
    )

    existing_memory_path.parent.mkdir(parents=True)
    existing_memory_path.write_text(
        "# Duplicate永続化テスト\n\n"
        "方式Aを採用することが決定した。\n",
        encoding="utf-8",
    )

    duplicate_id = existing_memory_path.stem

    candidates = [
        {
            "id": duplicate_id,
            "path": str(existing_memory_path),
            "content": "方式Aを採用することが決定した。",
            "score": 10,
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: duplicate_id,
    )

    def fail_analyze_memory_relations(*args, **kwargs):
        raise AssertionError(
            "analyze_memory_relations() must not be called "
            "when a duplicate Memory is detected."
        )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        fail_analyze_memory_relations,
    )

    result = process_memory(
        "方式Aを採用することが決定した。"
    )

    assert result == {
        "saved": False,
        "duplicate": True,
        "duplicate_of": duplicate_id,
        "result": classified_result,
        "path": existing_memory_path,
        "related": [],
        "relations": [],
    }

    memory_files = list(
        memory_environment.rglob("*.md")
    )

    assert memory_files == [
        existing_memory_path
    ]

    relation_files = list(
        (memory_environment / "Relations").glob("*.json")
    )

    assert relation_files == []


def test_supersedes_relation_is_persisted_and_old_memory_becomes_historical(
    memory_environment,
    monkeypatch,
):
    """
    A new Memory that supersedes an existing Memory must persist
    both the new Memory and the supersedes Relation.

    The old Memory itself remains unchanged.
    Its Historical status is derived from the Relation graph.
    """

    old_memory_path = memory_environment / "decision" / (
        "20260815_120000_000000_旧方式の決定.md"
    )

    old_memory_path.parent.mkdir(parents=True)
    old_memory_path.write_text(
        "# 旧方式の決定\n\n"
        "方式Aを採用することが決定した。\n",
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "新方式の決定",
        "content": "方式Aを廃止し、方式Bへ変更することが決定した。",
    }

    candidates = [
        {
            "id": old_memory_id,
            "path": str(old_memory_path),
            "content": "方式Aを採用することが決定した。",
            "score": 10,
        }
    ]

    relations = [
        {
            "id": old_memory_id,
            "relation": "supersedes",
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: relations,
    )

    result = process_memory(
        "方式Aを廃止し、方式Bへ変更することが決定した。"
    )

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    from memory.long_term import (
        find_memory_by_id,
        find_superseded_memory_ids,
        load_relations,
    )

    reloaded_new_memory = find_memory_by_id(new_memory_id)

    assert reloaded_new_memory == new_memory_path

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "supersedes"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id in superseded_ids
    assert new_memory_id not in superseded_ids

    assert old_memory_path.exists()


def test_conflicts_relation_is_persisted_and_old_memory_remains_unchanged(
    memory_environment,
    monkeypatch,
):
    """
    A new Memory that conflicts with an existing Memory must persist
    both the new Memory and the conflicts Relation.

    The existing Memory itself must remain unchanged.
    """

    old_memory_path = memory_environment / "decision" / (
        "20260815_120000_000000_既存方針.md"
    )

    old_memory_path.parent.mkdir(parents=True)
    old_memory_content = (
        "# 既存方針\n\n"
        "監査ログの保存を必須とする。\n"
    )
    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "新しい方針",
        "content": "監査ログの保存を禁止する。",
    }

    candidates = [
        {
            "id": old_memory_id,
            "path": str(old_memory_path),
            "content": "監査ログの保存を必須とする。",
            "score": 10,
        }
    ]

    relations = [
        {
            "id": old_memory_id,
            "relation": "conflicts",
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: relations,
    )

    result = process_memory(
        "監査ログの保存を禁止する。"
    )

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    from memory.long_term import (
        find_memory_by_id,
        load_relations,
    )

    reloaded_new_memory = find_memory_by_id(new_memory_id)

    assert reloaded_new_memory == new_memory_path

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "conflicts"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content


def test_memory_lifecycle_new_then_superseded(
    memory_environment,
    monkeypatch,
):
    """
    A complete Memory lifecycle must work correctly:

        old Memory
            ↓
        new Memory
            ↓
        new --supersedes--> old

    The old Memory remains physically unchanged,
    while its Historical status is derived from the Relation graph.
    """

    from memory.long_term import (
        find_memory_by_id,
        find_superseded_memory_ids,
        load_relations,
    )

    # ---------------------------------------------------------
    # Step 1: Create the initial Memory.
    # ---------------------------------------------------------

    old_memory_path = memory_environment / "decision" / (
        "20260815_120000_000000_旧方式の決定.md"
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

    # ---------------------------------------------------------
    # Step 2: Prepare the new Memory.
    # ---------------------------------------------------------

    classified_result = {
        "should_remember": True,
        "type": "decision",
        "title": "新方式の決定",
        "content": (
            "方式Aを廃止し、方式Bへ変更することが決定した。"
        ),
    }

    candidates = [
        {
            "id": old_memory_id,
            "path": str(old_memory_path),
            "content": "方式Aを採用することが決定した。",
            "score": 10,
        }
    ]

    relations = [
        {
            "id": old_memory_id,
            "relation": "supersedes",
        }
    ]

    monkeypatch.setattr(
        "memory.memory_manager.classify_memory",
        lambda text: classified_result,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_memory_candidates",
        lambda title, content: candidates,
    )

    monkeypatch.setattr(
        "memory.memory_manager.find_duplicate_memory",
        lambda title, content, candidates: None,
    )

    monkeypatch.setattr(
        "memory.memory_manager.analyze_memory_relations",
        lambda title, content, candidates: relations,
    )

    # ---------------------------------------------------------
    # Step 3: Process the new Memory.
    # ---------------------------------------------------------

    result = process_memory(
        "方式Aを廃止し、方式Bへ変更することが決定した。"
    )

    assert result["saved"] is True

    new_memory_path = result["path"]
    new_memory_id = new_memory_path.stem

    # ---------------------------------------------------------
    # Step 4: Both Memories must exist.
    # ---------------------------------------------------------

    assert old_memory_path.exists()
    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    assert find_memory_by_id(old_memory_id) == old_memory_path
    assert find_memory_by_id(new_memory_id) == new_memory_path

    # ---------------------------------------------------------
    # Step 5: The supersedes Relation must exist.
    # ---------------------------------------------------------

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "supersedes"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    # ---------------------------------------------------------
    # Step 6: Historical status must be derived from Relation.
    # ---------------------------------------------------------

    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id in superseded_ids
    assert new_memory_id not in superseded_ids

    # ---------------------------------------------------------
    # Step 7: The old Memory itself must remain unchanged.
    # ---------------------------------------------------------

    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content