from memory.memory_relation import find_memory_candidates


def test_find_memory_candidates_uses_title_and_content_and_preserves_fields(
    monkeypatch,
):
    """
    find_memory_candidates() must search using the combined title/content
    query and preserve the candidate fields required by relation analysis.
    """

    captured = {}

    search_results = [
        {
            "id": "memory-001",
            "path": "/data/memory/copilot/decision/memory-001.md",
            "content": "既存Memoryの内容です。",
            "score": 12,
            "extra": "ignored",
        },
        {
            "id": "memory-002",
            "path": "/data/memory/copilot/project/memory-002.md",
            "content": "別のMemoryの内容です。",
            "score": 8,
        },
    ]

    def fake_search_memories(query, limit):
        captured["query"] = query
        captured["limit"] = limit
        return search_results

    monkeypatch.setattr(
        "memory.memory_relation.search_memories",
        fake_search_memories,
    )

    result = find_memory_candidates(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加情報です。",
        limit=5,
    )

    assert captured == {
        "query": (
            "M3-4-4 の新しい決定\n"
            "M3-4-4 に関する追加情報です。"
        ),
        "limit": 5,
    }

    assert result == [
        {
            "id": "memory-001",
            "path": "/data/memory/copilot/decision/memory-001.md",
            "content": "既存Memoryの内容です。",
            "score": 12,
        },
        {
            "id": "memory-002",
            "path": "/data/memory/copilot/project/memory-002.md",
            "content": "別のMemoryの内容です。",
            "score": 8,
        },
    ]


def test_find_memory_candidates_returns_empty_when_search_returns_nothing(
    monkeypatch,
):
    """
    When search_memories() returns no results,
    find_memory_candidates() must return an empty candidate list.
    """

    def fake_search_memories(query, limit):
        return []

    monkeypatch.setattr(
        "memory.memory_relation.search_memories",
        fake_search_memories,
    )

    result = find_memory_candidates(
        title="存在しないMemory",
        content="検索結果が存在しないケースを確認する。",
        limit=5,
    )

    assert result == []