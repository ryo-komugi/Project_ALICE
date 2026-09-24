import pytest

from memory.memory_manager import process_memory
from memory.long_term import (
    find_memory_by_id,
    find_superseded_memory_ids,
    load_relations,
)


@pytest.mark.integration
def test_memory_lifecycle_with_real_ollama_supersedes_existing_memory(
    memory_environment,
):
    """
    Verify the complete Memory lifecycle using real Ollama:

    existing Memory
        -> new input
        -> classification
        -> candidate search
        -> relation analysis
        -> new Memory persistence
        -> supersedes Relation persistence
        -> old Memory becomes Historical
    """

    old_memory_path = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_通知方式の旧方針.md"
    )

    old_memory_path.parent.mkdir(parents=True)

    old_memory_content = (
        "# 通知方式の旧方針\n\n"
        "通知方式はメールを使用する。\n"
    )

    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    new_text = (
        "通知方式はメールからDiscordへ変更することを決定した。"
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    # New Memory must be reloadable.
    assert find_memory_by_id(new_memory_id) == new_memory_path

    # The old Memory itself must remain physically unchanged.
    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content

    # A supersedes Relation must connect the new Memory to the old one.
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


@pytest.mark.integration
def test_memory_lifecycle_with_real_ollama_conflicts_existing_memory(
    memory_environment,
):
    """
    Verify the complete Memory lifecycle using real Ollama
    for a conflicting Memory.
    """

    old_memory_path = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_監査ログ保存方針.md"
    )

    old_memory_path.parent.mkdir(parents=True)

    old_memory_content = (
        "# 監査ログ保存方針\n\n"
        "監査ログの保存を必須とする。\n"
    )

    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    new_text = (
        "監査ログの保存を禁止するという別の方針を採用する。"
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    assert find_memory_by_id(new_memory_id) == new_memory_path

    # The existing Memory itself must remain unchanged.
    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "conflicts"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    # conflicts must not make either Memory Historical.
    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id not in superseded_ids
    assert new_memory_id not in superseded_ids


@pytest.mark.integration
def test_memory_lifecycle_with_real_ollama_related_existing_memory(
    memory_environment,
):
    """
    Verify the complete Memory lifecycle using real Ollama
    for a related Memory.
    """

    old_memory_path = (
        memory_environment
        / "knowledge"
        / "20260815_120000_000000_監査ログ保存方式.md"
    )

    old_memory_path.parent.mkdir(parents=True)

    old_memory_content = (
        "# 監査ログ保存方式\n\n"
        "監査ログの保存方式を定義する。\n"
    )

    old_memory_path.write_text(
        old_memory_content,
        encoding="utf-8",
    )

    old_memory_id = old_memory_path.stem

    new_text = (
        "監査ログ保存方式に関する検討会議は"
        "2026年8月20日に開催予定である。"
    )

    result = process_memory(new_text)

    assert result["saved"] is True

    new_memory_path = result["path"]

    assert new_memory_path.exists()
    assert new_memory_path != old_memory_path

    new_memory_id = new_memory_path.stem

    assert find_memory_by_id(new_memory_id) == new_memory_path

    # Existing Memory must remain unchanged.
    assert old_memory_path.exists()
    assert old_memory_path.read_text(
        encoding="utf-8"
    ) == old_memory_content

    saved_relations = load_relations()

    matching_relations = [
        relation
        for relation in saved_relations
        if relation.get("from") == new_memory_id
        and relation.get("relation") == "related"
        and relation.get("to") == old_memory_id
    ]

    assert len(matching_relations) == 1

    # related must not make either Memory Historical.
    superseded_ids = find_superseded_memory_ids()

    assert old_memory_id not in superseded_ids
    assert new_memory_id not in superseded_ids