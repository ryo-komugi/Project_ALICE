import json
import pytest


def test_consolidate_pending_messages_passes_previous_assistant_context(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ALICE_CoPilotのメインインターフェースはDiscordにしましょう。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "それでいきましょう。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "process_memory",
        lambda content: {
            "saved": False,
        },
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "ALICE_CoPilotのメインインターフェースはDiscordにしましょう。",
            },
            {
                "role": "user",
                "content": "それでいきましょう。",
            },
        ]
    ]

    assert saved_ids == [2]


def test_consolidate_pending_messages_uses_previous_assistant_for_each_user(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ALICE_CoPilotのメインインターフェースはDiscordにしましょう。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "それでいきましょう。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ではDiscordを採用します。",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "はい、お願いします。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "process_memory",
        lambda content: {
            "saved": False,
        },
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "ALICE_CoPilotのメインインターフェースはDiscordにしましょう。",
            },
            {
                "role": "user",
                "content": "それでいきましょう。",
            },
        ],
        [
            {
                "role": "assistant",
                "content": "ではDiscordを採用します。",
            },
            {
                "role": "user",
                "content": "はい、お願いします。",
            },
        ],
    ]

    assert saved_ids == [4]


def test_consolidate_pending_messages_skips_explicit_memory_request(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ALICEのMemory設計について説明します。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "覚えておいて ALICEのMemoryは既存Memoryを変更しない。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    process_memory_calls = []

    def fake_process_memory(content):
        process_memory_calls.append(content)
        return {
            "saved": True,
        }

    monkeypatch.setattr(
        memory_consolidator,
        "process_memory",
        fake_process_memory,
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    # 明示的な「覚えておいて」は
    # main.pyですでにMemory保存されているため、
    # Extractorを呼ばない。
    assert extracted_conversations == []

    # Consolidatorからprocess_memory()も呼ばない。
    assert process_memory_calls == []

    # Userメッセージ自体は処理済みとして記録する。
    assert saved_ids == [2]


def test_consolidate_pending_messages_respects_limit(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "Discordをメインインターフェースにしましょう。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "それでいきましょう。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ではDiscordを採用します。",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "お願いします。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "process_memory",
        lambda content: {
            "saved": False,
        },
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages(
        limit=1,
    )

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "Discordをメインインターフェースにしましょう。",
            },
            {
                "role": "user",
                "content": "それでいきましょう。",
            },
        ],
    ]

    assert saved_ids == [2]


def test_consolidate_pending_messages_returns_empty_when_no_pending_messages(
    monkeypatch,
):
    from memory import memory_consolidator

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: [],
    )

    save_calls = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: save_calls.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []
    assert save_calls == []


def test_load_last_processed_id_returns_zero_when_state_does_not_exist(
    monkeypatch,
    tmp_path,
):
    from memory import memory_consolidator

    state_path = tmp_path / "consolidation_state.json"

    monkeypatch.setattr(
        memory_consolidator,
        "STATE_PATH",
        state_path,
    )

    assert memory_consolidator.load_last_processed_id() == 0


def test_save_last_processed_id_persists_and_loads_value(
    monkeypatch,
    tmp_path,
):
    from memory import memory_consolidator

    state_path = tmp_path / "consolidation_state.json"

    monkeypatch.setattr(
        memory_consolidator,
        "STATE_PATH",
        state_path,
    )

    memory_consolidator.save_last_processed_id(123)

    assert state_path.exists()

    assert memory_consolidator.load_last_processed_id() == 123


def test_save_last_processed_id_writes_expected_json(
    monkeypatch,
    tmp_path,
):
    import json

    from memory import memory_consolidator

    state_path = tmp_path / "consolidation_state.json"

    monkeypatch.setattr(
        memory_consolidator,
        "STATE_PATH",
        state_path,
    )

    memory_consolidator.save_last_processed_id(123)

    with state_path.open("r", encoding="utf-8") as f:
        state = json.load(f)

    assert state == {
        "last_processed_message_id": 123,
    }


def test_consolidate_pending_messages_saves_last_processed_user_id(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "ALICE_CoPilotのメインインターフェースはDiscordです。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "それでいきましょう。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        lambda conversation: [],
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []
    assert saved_ids == [2]


def test_consolidate_pending_messages_does_not_advance_state_when_processing_fails(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "ALICE_CoPilotのインターフェースについて決定した。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    def fail_extract_memories(conversation):
        raise RuntimeError("extract failed")

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fail_extract_memories,
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    with pytest.raises(RuntimeError, match="extract failed"):
        memory_consolidator.consolidate_pending_messages()

    assert saved_ids == []


def test_consolidate_pending_messages_does_not_advance_state_after_partial_failure(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "1つ目の決定事項です。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "2つ目の決定事項です。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "3つ目の決定事項です。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    processed_contents = []

    def fake_extract_memories(conversation):
        content = conversation[-1]["content"]
        processed_contents.append(content)

        if content == "2つ目の決定事項です。":
            raise RuntimeError("second message failed")

        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    with pytest.raises(RuntimeError, match="second message failed"):
        memory_consolidator.consolidate_pending_messages()

    assert processed_contents == [
        "1つ目の決定事項です。",
        "2つ目の決定事項です。",
    ]

    # 途中で失敗したため、処理済みIDは更新しない。
    assert saved_ids == []


def test_get_pending_messages_returns_messages_after_last_processed_id(
    monkeypatch,
):
    from memory import memory_consolidator

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            assert "WHERE id > ?" in query
            assert "ORDER BY id ASC" in query
            assert params == (10,)

            return self

        def fetchall(self):
            return [
                (
                    11,
                    "2026-08-15T10:00:00+09:00",
                    "123",
                    "456",
                    "user",
                    "11番目のメッセージ",
                ),
                (
                    12,
                    "2026-08-15T10:01:00+09:00",
                    "123",
                    "456",
                    "assistant",
                    "12番目のメッセージ",
                ),
            ]

    monkeypatch.setattr(
        memory_consolidator,
        "load_last_processed_id",
        lambda: 10,
    )

    monkeypatch.setattr(
        memory_consolidator.sqlite3,
        "connect",
        lambda path: FakeConnection(),
    )

    messages = memory_consolidator.get_pending_messages()

    assert messages == [
        {
            "id": 11,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "11番目のメッセージ",
        },
        {
            "id": 12,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "12番目のメッセージ",
        },
    ]


def test_get_pending_messages_excludes_last_processed_id(
    monkeypatch,
):
    from memory import memory_consolidator

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params):
            assert "WHERE id > ?" in query
            assert params == (10,)
            return self

        def fetchall(self):
            return [
                (
                    11,
                    "2026-08-15T10:01:00+09:00",
                    "123",
                    "456",
                    "user",
                    "11番目のメッセージ",
                ),
            ]

    monkeypatch.setattr(
        memory_consolidator,
        "load_last_processed_id",
        lambda: 10,
    )

    monkeypatch.setattr(
        memory_consolidator.sqlite3,
        "connect",
        lambda path: FakeConnection(),
    )

    messages = memory_consolidator.get_pending_messages()

    assert all(
        message["id"] > 10
        for message in messages
    )

    assert not any(
        message["id"] == 10
        for message in messages
    )


def test_consolidate_pending_messages_keeps_channels_separate(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "channel-A",
            "user_id": "user-A",
            "role": "assistant",
            "content": "Aチャンネルの直前の回答です。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "channel-B",
            "user_id": "user-B",
            "role": "assistant",
            "content": "Bチャンネルの直前の回答です。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "channel-A",
            "user_id": "user-A",
            "role": "user",
            "content": "Aチャンネルでの質問です。",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "channel-B",
            "user_id": "user-B",
            "role": "user",
            "content": "Bチャンネルでの質問です。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: None,
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "Aチャンネルの直前の回答です。",
            },
            {
                "role": "user",
                "content": "Aチャンネルでの質問です。",
            },
        ],
        [
            {
                "role": "assistant",
                "content": "Bチャンネルの直前の回答です。",
            },
            {
                "role": "user",
                "content": "Bチャンネルでの質問です。",
            },
        ],
    ]


def test_consolidate_pending_messages_allows_user_without_previous_assistant(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "ALICE_CoPilotのMemory設計について決定した。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: None,
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "user",
                "content": "ALICE_CoPilotのMemory設計について決定した。",
            },
        ]
    ]


def test_consolidate_pending_messages_ignores_assistant_only_messages(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": None,
            "role": "assistant",
            "content": "ALICE_CoPilotのメインインターフェースはDiscordです。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    def fail_extract_memories(conversation):
        raise AssertionError(
            "extract_memories() must not be called for assistant-only messages"
        )

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fail_extract_memories,
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    # User発言が存在しないため、Consolidation対象はない。
    # したがって処理済みIDも進めない。
    assert saved_ids == []


def test_consolidate_pending_messages_resets_assistant_context_after_explicit_memory_request(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "古い提案です。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "覚えておいて 新しい決定事項です。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "assistant",
            "content": "新しい話題についての回答です。",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "これは新しい話題です。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: None,
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "新しい話題についての回答です。",
            },
            {
                "role": "user",
                "content": "これは新しい話題です。",
            },
        ]
    ]


def test_save_last_processed_id_atomically_replaces_state_file(
    monkeypatch,
    tmp_path,
):
    from memory import memory_consolidator

    state_path = tmp_path / "consolidation_state.json"

    monkeypatch.setattr(
        memory_consolidator,
        "STATE_PATH",
        state_path,
    )

    memory_consolidator.save_last_processed_id(123)

    assert state_path.exists()

    data = json.loads(
        state_path.read_text(encoding="utf-8")
    )

    assert data == {
        "last_processed_message_id": 123,
    }

    tmp_files = list(
        tmp_path.glob(".consolidation_state.json.tmp_*")
    )

    assert tmp_files == []


def test_consolidate_pending_messages_uses_only_previous_assistant_context(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "123",
            "user_id": None,
            "role": "assistant",
            "content": "最初の回答です。",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "最初の質問です。",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "続けて質問します。",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "123",
            "user_id": None,
            "role": "assistant",
            "content": "二回目の回答です。",
        },
        {
            "id": 5,
            "timestamp": "2026-08-15T10:04:00+09:00",
            "channel_id": "123",
            "user_id": "456",
            "role": "user",
            "content": "三回目の質問です。",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    def fake_extract_memories(conversation):
        extracted_conversations.append(conversation)
        return []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        fake_extract_memories,
    )

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: None,
    )

    results = memory_consolidator.consolidate_pending_messages()

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "assistant",
                "content": "最初の回答です。",
            },
            {
                "role": "user",
                "content": "最初の質問です。",
            },
        ],
        [
            {
                "role": "user",
                "content": "続けて質問します。",
            },
        ],
        [
            {
                "role": "assistant",
                "content": "二回目の回答です。",
            },
            {
                "role": "user",
                "content": "三回目の質問です。",
            },
        ],
    ]


def test_consolidate_pending_messages_limit_does_not_skip_interleaved_channels(
    monkeypatch,
):
    from memory import memory_consolidator

    pending_messages = [
        {
            "id": 1,
            "timestamp": "2026-08-15T10:00:00+09:00",
            "channel_id": "A",
            "user_id": "user-a",
            "role": "user",
            "content": "Aの最初の発言",
        },
        {
            "id": 2,
            "timestamp": "2026-08-15T10:01:00+09:00",
            "channel_id": "B",
            "user_id": "user-b",
            "role": "user",
            "content": "Bの最初の発言",
        },
        {
            "id": 3,
            "timestamp": "2026-08-15T10:02:00+09:00",
            "channel_id": "B",
            "user_id": "user-b",
            "role": "user",
            "content": "Bの2回目の発言",
        },
        {
            "id": 4,
            "timestamp": "2026-08-15T10:03:00+09:00",
            "channel_id": "A",
            "user_id": "user-a",
            "role": "user",
            "content": "Aの2回目の発言",
        },
    ]

    monkeypatch.setattr(
        memory_consolidator,
        "get_pending_messages",
        lambda: pending_messages,
    )

    extracted_conversations = []

    monkeypatch.setattr(
        memory_consolidator,
        "extract_memories",
        lambda conversation: (
            extracted_conversations.append(conversation)
            or []
        ),
    )

    saved_ids = []

    monkeypatch.setattr(
        memory_consolidator,
        "save_last_processed_id",
        lambda message_id: saved_ids.append(message_id),
    )

    results = memory_consolidator.consolidate_pending_messages(
        limit=2,
    )

    assert results == []

    assert extracted_conversations == [
        [
            {
                "role": "user",
                "content": "Aの最初の発言",
            }
        ],
        [
            {
                "role": "user",
                "content": "Bの最初の発言",
            }
        ],
    ]

    assert saved_ids == [2]