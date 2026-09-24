import pytest

from memory.memory_classifier import classify_memory


@pytest.mark.integration
def test_classify_memory_with_real_ollama():
    """
    Verify that the configured Ollama model produces a valid
    ALICE Memory classification result.
    """

    text = (
        "ALICE_CoPilotのMemory設計では、"
        "既存Memory自体は変更せず、"
        "新しいMemory側にRelationを保存して履歴を管理する。"
    )

    result = classify_memory(text)

    assert isinstance(result, dict)

    assert result["should_remember"] is True

    assert result["type"] in {
        "context",
        "project",
        "decision",
        "knowledge",
        "idea",
    }

    assert isinstance(result["title"], str)
    assert result["title"].strip()

    assert isinstance(result["content"], str)
    assert result["content"].strip()

    assert isinstance(result["related"], list)


from memory.memory_manager import process_memory
from memory.memory_search import search_memories


@pytest.mark.integration
def test_process_memory_with_real_ollama_persists_and_is_searchable(
    memory_environment,
):
    """
    Verify the real Ollama classification can flow through
    process_memory() into persistent Memory storage and become
    searchable.
    """

    text = (
        "ALICE_CoPilotの統合テストとして、"
        "Memoryは既存Memoryを変更せず、"
        "新しいMemoryとRelationを保存する方式を採用することを決定した。"
    )

    result = process_memory(text)

    assert result["saved"] is True

    memory_path = result["path"]

    assert memory_path.exists()
    assert memory_path.suffix == ".md"

    results = search_memories(
        query="ALICE_CoPilot Memory Relation",
        limit=10,
    )

    result_ids = [
        item["id"]
        for item in results
    ]

    assert memory_path.stem in result_ids