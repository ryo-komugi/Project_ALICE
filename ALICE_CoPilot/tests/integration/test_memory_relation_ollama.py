import pytest

from memory.memory_relation import analyze_memory_relations


@pytest.mark.integration
def test_analyze_memory_relations_with_real_ollama_returns_supersedes():
    """
    Verify that the real Ollama model recognizes an explicit
    update as a supersedes relation.
    """

    old_memory_id = (
        "20260815_120000_000000_通知方式の旧方針"
    )

    candidates = [
        {
            "id": old_memory_id,
            "path": "",
            "content": (
                "# 通知方式の旧方針\n\n"
                "通知方式はメールを使用する。"
            ),
            "score": 10,
        }
    ]

    relations = analyze_memory_relations(
        title="通知方式の新方針",
        content="通知方式をDiscordに変更する。",
        candidates=candidates,
    )

    assert isinstance(relations, list)

    assert relations == [
        {
            "id": old_memory_id,
            "relation": "supersedes",
        }
    ]


@pytest.mark.integration
def test_analyze_memory_relations_with_real_ollama_returns_conflicts():
    """
    Verify that the real Ollama model recognizes an incompatible
    statement without an explicit update as a conflicts relation.
    """

    old_memory_id = (
        "20260815_120000_000000_監査ログ保存の旧方針"
    )

    candidates = [
        {
            "id": old_memory_id,
            "path": "",
            "content": (
                "# 監査ログ保存の旧方針\n\n"
                "監査ログの保存を必須とする。"
            ),
            "score": 10,
        }
    ]

    relations = analyze_memory_relations(
        title="監査ログ保存に関する別方針",
        content="監査ログの保存を禁止する。",
        candidates=candidates,
    )

    assert isinstance(relations, list)

    assert relations == [
        {
            "id": old_memory_id,
            "relation": "conflicts",
        }
    ]


@pytest.mark.integration
def test_analyze_memory_relations_with_real_ollama_returns_related():
    """
    Verify that the real Ollama model recognizes directly related
    information that is neither an update nor a conflict.
    """

    old_memory_id = (
        "20260815_120000_000000_監査ログ保存方式"
    )

    candidates = [
        {
            "id": old_memory_id,
            "path": "",
            "content": (
                "# 監査ログ保存方式\n\n"
                "監査ログの保存方式を定義する。"
            ),
            "score": 10,
        }
    ]

    relations = analyze_memory_relations(
        title="監査ログ保存方式の補足",
        content="監査ログ保存方式に関する補足情報を記録する。",
        candidates=candidates,
    )

    assert isinstance(relations, list)

    assert relations == [
        {
            "id": old_memory_id,
            "relation": "related",
        }
    ]