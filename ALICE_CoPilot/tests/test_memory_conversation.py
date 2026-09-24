def test_build_conversation_messages_includes_memory_context(monkeypatch):
    import importlib
    import os

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord

    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main

    importlib.reload(main)

    recent_messages = [
        ("user", "監査ログについて教えて"),
        ("assistant", "確認します。"),
    ]

    memory_context = (
        "[Primary]\n"
        "監査ログはJSON形式で保存する。\n"
    )

    messages = main.build_conversation_messages(
        recent_messages=recent_messages,
        memory_context=memory_context,
    )

    assert messages[0]["role"] == "system"
    assert "ALICE_CoPilotの長期記憶" in messages[0]["content"]
    assert "監査ログはJSON形式で保存する。" in messages[0]["content"]

    assert messages[1:] == [
        {
            "role": "user",
            "content": "監査ログについて教えて",
        },
        {
            "role": "assistant",
            "content": "確認します。",
        },
    ]


def test_build_conversation_messages_without_memory_context_has_no_memory_system_message(
    monkeypatch,
):
    import importlib
    import os

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord

    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main

    importlib.reload(main)

    recent_messages = [
        ("user", "こんにちは"),
        ("assistant", "こんにちは。"),
    ]

    messages = main.build_conversation_messages(
        recent_messages=recent_messages,
        memory_context=None,
    )

    assert messages == [
        {
            "role": "user",
            "content": "こんにちは",
        },
        {
            "role": "assistant",
            "content": "こんにちは。",
        },
    ]


def test_build_conversation_messages_preserves_formatted_memory_context(
    monkeypatch,
):
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord

    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main

    importlib.reload(main)

    memory_context = """[Primary]
- 監査ログ保存方式
  JSON形式で保存する。

[Superseded]
- 旧監査ログ保存方式
  CSV形式で保存する。

[Conflicting]
- 別案
  XML形式で保存する。
"""

    messages = main.build_conversation_messages(
        recent_messages=[
            ("user", "監査ログの保存方式は？"),
        ],
        memory_context=memory_context,
    )

    system_message = messages[0]

    assert system_message["role"] == "system"

    assert "[Primary]" in system_message["content"]
    assert "JSON形式で保存する。" in system_message["content"]

    assert "[Superseded]" in system_message["content"]
    assert "CSV形式で保存する。" in system_message["content"]

    assert "[Conflicting]" in system_message["content"]
    assert "XML形式で保存する。" in system_message["content"]

    assert "Primary Memoryは現在有効な情報として扱ってください。" in system_message["content"]
    assert "Superseded Memoryは過去の情報であり、現在の事実として使用しないでください。" in system_message["content"]
    assert "Conflicting Memoryは現在の事実として採用しないでください。" in system_message["content"]

    assert messages[1] == {
        "role": "user",
        "content": "監査ログの保存方式は？",
    }


def test_memory_context_flows_into_conversation_messages(
    memory_environment,
    monkeypatch,
):
    import importlib

    import discord

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main
    import memory.memory_router
    import memory.memory_search
    import memory.memory_context

    importlib.reload(memory.memory_router)
    importlib.reload(memory.memory_search)
    importlib.reload(memory.memory_context)
    importlib.reload(main)

    from memory.long_term import create_memory

    create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content="監査ログはJSON形式で保存する。",
    )

    prompt = "監査ログの保存方式について教えて"

    memories = main.search_memories(
        query=prompt,
        limit=main.MEMORY_LIMIT,
    )

    assert memories

    memory_context = main.build_memory_context(
        memories=memories,
        query=prompt,
    )

    memory_context_text = main.format_memory_context(memory_context)

    assert memory_context_text
    assert "JSON形式で保存する" in memory_context_text

    messages = main.build_conversation_messages(
        recent_messages=[
            ("user", prompt),
        ],
        memory_context=memory_context_text,
    )

    assert messages[0]["role"] == "system"
    assert "ALICE_CoPilotの長期記憶" in messages[0]["content"]
    assert "JSON形式で保存する" in messages[0]["content"]

    assert messages[-1] == {
        "role": "user",
        "content": prompt,
    }


def test_on_message_passes_memory_context_to_ollama(
    monkeypatch,
):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord

    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main
    importlib.reload(main)

    # --------------------------------------------------
    # Fake Discord objects
    # --------------------------------------------------

    class FakeBotUser:
        id = 999

        def __str__(self):
            return "ALICE_CoPilot"

    class FakeChannel:
        name = "assistant"
        id = 123

        def __init__(self):
            self.sent_messages = []

        async def send(self, content):
            self.sent_messages.append(content)

    class FakeAuthor:
        id = 456

        def __str__(self):
            return "test-user"

    class FakeMessage:
        def __init__(self, bot_user):
            self.author = FakeAuthor()
            self.channel = FakeChannel()
            self.mentions = [bot_user]
            self.content = f"<@{bot_user.id}> 監査ログの保存方式について教えて"

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    main.client = FakeClient()

    message = FakeMessage(bot_user)

    # --------------------------------------------------
    # Mock short-term memory
    # --------------------------------------------------

    saved_messages = []

    def fake_save_message(**kwargs):
        saved_messages.append(kwargs)

    monkeypatch.setattr(
        main,
        "save_message",
        fake_save_message,
    )

    monkeypatch.setattr(
        main,
        "get_recent_messages",
        lambda channel_id, limit: [
            ("user", "以前の質問"),
            ("assistant", "以前の回答"),
        ],
    )

    # --------------------------------------------------
    # Mock Memory Router
    # --------------------------------------------------

    monkeypatch.setattr(
        main,
        "should_use_memory",
        lambda question: True,
    )

    # --------------------------------------------------
    # Mock Memory Search / Context
    # --------------------------------------------------

    search_calls = []

    def fake_search_memories(query, limit):
        search_calls.append(
            {
                "query": query,
                "limit": limit,
            }
        )

        return [
            {
                "id": "memory-001",
                "title": "監査ログ保存方式",
                "content": "監査ログはJSON形式で保存する。",
                "type": "decision",
            }
        ]

    monkeypatch.setattr(
        main,
        "search_memories",
        fake_search_memories,
    )

    context_calls = []

    def fake_build_memory_context(memories, query):
        context_calls.append(
            {
                "memories": memories,
                "query": query,
            }
        )

        return {
            "primary": memories,
            "related": [],
            "superseded": [],
            "superseding": [],
            "conflicting": [],
        }

    monkeypatch.setattr(
        main,
        "build_memory_context",
        fake_build_memory_context,
    )

    monkeypatch.setattr(
        main,
        "format_memory_context",
        lambda context: (
            "[Primary]\n"
            "- 監査ログ保存方式\n"
            "  監査ログはJSON形式で保存する。"
        ),
    )

    # --------------------------------------------------
    # Mock Ollama
    # --------------------------------------------------

    ollama_calls = []

    def fake_ask_ollama(messages):
        ollama_calls.append(messages)

        return "監査ログはJSON形式で保存します。"

    monkeypatch.setattr(
        main,
        "ask_ollama",
        fake_ask_ollama,
    )

    # --------------------------------------------------
    # Mock consolidation
    # --------------------------------------------------

    consolidation_calls = []

    async def fake_run_memory_consolidation():
        consolidation_calls.append(True)

    monkeypatch.setattr(
        main,
        "run_memory_consolidation",
        fake_run_memory_consolidation,
    )

    # --------------------------------------------------
    # Execute
    # --------------------------------------------------

    asyncio.run(main.on_message(message))

    # --------------------------------------------------
    # Verify
    # --------------------------------------------------

    assert search_calls == [
        {
            "query": "監査ログの保存方式について教えて",
            "limit": main.MEMORY_LIMIT,
        }
    ]

    assert len(context_calls) == 1
    assert context_calls[0]["query"] == "監査ログの保存方式について教えて"

    assert len(ollama_calls) == 1

    ollama_messages = ollama_calls[0]

    # Memory context must be the first system message.
    assert ollama_messages[0]["role"] == "system"

    assert "ALICE_CoPilotの長期記憶" in ollama_messages[0]["content"]
    assert "監査ログはJSON形式で保存する。" in ollama_messages[0]["content"]

    # Recent conversation must follow.
    assert ollama_messages[1:] == [
        {
            "role": "user",
            "content": "以前の質問",
        },
        {
            "role": "assistant",
            "content": "以前の回答",
        },
    ]

    # User message and assistant answer should both be saved.
    assert saved_messages[0]["role"] == "user"
    assert saved_messages[0]["content"] == "監査ログの保存方式について教えて"

    assert saved_messages[1]["role"] == "assistant"
    assert saved_messages[1]["content"] == "監査ログはJSON形式で保存します。"

    # Discord response.
    assert message.channel.sent_messages == [
        "監査ログはJSON形式で保存します。"
    ]

    # Consolidation runs after the response.
    assert consolidation_calls == [True]


def test_on_message_without_memory_does_not_search_memory(
    monkeypatch,
):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord

    monkeypatch.setattr(
        discord.Client,
        "run",
        lambda self, token: None,
    )

    import main
    importlib.reload(main)

    class FakeBotUser:
        id = 999

    class FakeChannel:
        name = "assistant"
        id = 123

        def __init__(self):
            self.sent_messages = []

        async def send(self, content):
            self.sent_messages.append(content)

    class FakeAuthor:
        id = 456

        def __str__(self):
            return "test-user"

    class FakeMessage:
        def __init__(self, bot_user):
            self.author = FakeAuthor()
            self.channel = FakeChannel()
            self.mentions = [bot_user]
            self.content = (
                f"<@{bot_user.id}> "
                "Pythonのリストとタプルの違いを教えて"
            )

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    main.client = FakeClient()

    message = FakeMessage(bot_user)

    # --------------------------------------------------
    # Short-term memory
    # --------------------------------------------------

    monkeypatch.setattr(
        main,
        "save_message",
        lambda **kwargs: None,
    )

    monkeypatch.setattr(
        main,
        "get_recent_messages",
        lambda channel_id, limit: [
            ("user", "Pythonについて質問"),
        ],
    )

    # --------------------------------------------------
    # Memory Router
    # --------------------------------------------------

    monkeypatch.setattr(
        main,
        "should_use_memory",
        lambda question: False,
    )

    # --------------------------------------------------
    # These must NOT be called.
    # --------------------------------------------------

    def fail_search_memories(*args, **kwargs):
        raise AssertionError(
            "search_memories() must not be called when use_memory=False"
        )

    def fail_build_memory_context(*args, **kwargs):
        raise AssertionError(
            "build_memory_context() must not be called when use_memory=False"
        )

    def fail_format_memory_context(*args, **kwargs):
        raise AssertionError(
            "format_memory_context() must not be called when use_memory=False"
        )

    monkeypatch.setattr(
        main,
        "search_memories",
        fail_search_memories,
    )

    monkeypatch.setattr(
        main,
        "build_memory_context",
        fail_build_memory_context,
    )

    monkeypatch.setattr(
        main,
        "format_memory_context",
        fail_format_memory_context,
    )

    # --------------------------------------------------
    # Ollama
    # --------------------------------------------------

    ollama_calls = []

    def fake_ask_ollama(messages):
        ollama_calls.append(messages)
        return "リストは可変、タプルは基本的に不変です。"

    monkeypatch.setattr(
        main,
        "ask_ollama",
        fake_ask_ollama,
    )

    async def fake_run_memory_consolidation():
        return None

    monkeypatch.setattr(
        main,
        "run_memory_consolidation",
        fake_run_memory_consolidation,
    )

    # --------------------------------------------------
    # Execute
    # --------------------------------------------------

    asyncio.run(main.on_message(message))

    # --------------------------------------------------
    # Verify
    # --------------------------------------------------

    assert len(ollama_calls) == 1

    ollama_messages = ollama_calls[0]

    # Memory system message must not exist.
    assert ollama_messages[0] == {
        "role": "user",
        "content": "Pythonについて質問",
    }

    # No Memory context was inserted.
    assert not any(
        message["role"] == "system"
        and "ALICE_CoPilotの長期記憶" in message["content"]
        for message in ollama_messages
    )

    assert message.channel.sent_messages == [
        "リストは可変、タプルは基本的に不変です。"
    ]


def test_on_message_without_mention_processes_normally(monkeypatch):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord
    monkeypatch.setattr(discord.Client, "run", lambda self, token: None)

    import main
    importlib.reload(main)

    class FakeBotUser:
        id = 999
        def __str__(self):
            return "ALICE_CoPilot"

    class FakeChannel:
        name = "assistant"
        id = 123
        def __init__(self):
            self.sent_messages = []
        async def send(self, content):
            self.sent_messages.append(content)

    class FakeAuthor:
        id = 456
        def __str__(self):
            return "test-user"

    class FakeMessage:
        def __init__(self):
            self.author = FakeAuthor()
            self.channel = FakeChannel()
            self.mentions = []
            self.content = "メンションなしの質問"

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    monkeypatch.setattr(main, "client", FakeClient())

    message = FakeMessage()

    saved_messages = []
    monkeypatch.setattr(main, "save_message", lambda **kwargs: saved_messages.append(kwargs))
    monkeypatch.setattr(main, "get_recent_messages", lambda channel_id, limit: [])
    monkeypatch.setattr(main, "should_use_memory", lambda question: False)
    monkeypatch.setattr(main, "ask_ollama", lambda messages: "メンションなしへの回答")
    monkeypatch.setattr(main, "run_memory_consolidation", lambda: asyncio.sleep(0))

    asyncio.run(main.on_message(message))

    assert len(saved_messages) == 2
    assert saved_messages[0]["role"] == "user"
    assert saved_messages[0]["content"] == "メンションなしの質問"
    assert saved_messages[1]["role"] == "assistant"
    assert saved_messages[1]["content"] == "メンションなしへの回答"
    assert message.channel.sent_messages == ["メンションなしへの回答"]


def test_on_message_ignores_alice_own_message(monkeypatch):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord
    monkeypatch.setattr(discord.Client, "run", lambda self, token: None)

    import main
    importlib.reload(main)

    class FakeBotUser:
        id = 999
        def __str__(self):
            return "ALICE_CoPilot"

    class FakeChannel:
        name = "assistant"
        id = 123
        def __init__(self):
            self.sent_messages = []
        async def send(self, content):
            self.sent_messages.append(content)

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    monkeypatch.setattr(main, "client", FakeClient())

    class FakeMessage:
        def __init__(self):
            self.author = bot_user  # ALICE自身の投稿
            self.channel = FakeChannel()
            self.mentions = []
            self.content = "ALICE自身の投稿"

    message = FakeMessage()

    saved_messages = []
    monkeypatch.setattr(main, "save_message", lambda **kwargs: saved_messages.append(kwargs))
    monkeypatch.setattr(main, "ask_ollama", lambda messages: "不適切な応答")

    asyncio.run(main.on_message(message))

    assert len(saved_messages) == 0
    assert len(message.channel.sent_messages) == 0


def test_on_message_ignores_other_channel(monkeypatch):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord
    monkeypatch.setattr(discord.Client, "run", lambda self, token: None)

    import main
    importlib.reload(main)

    class FakeBotUser:
        id = 999
        def __str__(self):
            return "ALICE_CoPilot"

    class FakeChannel:
        name = "general"  # copilot以外のチャンネル
        id = 123
        def __init__(self):
            self.sent_messages = []
        async def send(self, content):
            self.sent_messages.append(content)

    class FakeAuthor:
        id = 456
        def __str__(self):
            return "test-user"

    class FakeMessage:
        def __init__(self):
            self.author = FakeAuthor()
            self.channel = FakeChannel()
            self.mentions = []
            self.content = "別チャンネルでの質問"

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    monkeypatch.setattr(main, "client", FakeClient())

    message = FakeMessage()

    saved_messages = []
    monkeypatch.setattr(main, "save_message", lambda **kwargs: saved_messages.append(kwargs))
    monkeypatch.setattr(main, "ask_ollama", lambda messages: "不適切な応答")

    asyncio.run(main.on_message(message))

    assert len(saved_messages) == 0
    assert len(message.channel.sent_messages) == 0


def test_on_message_with_mention_cleans_prompt(monkeypatch):
    import asyncio
    import importlib

    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")

    import discord
    monkeypatch.setattr(discord.Client, "run", lambda self, token: None)

    import main
    importlib.reload(main)

    class FakeBotUser:
        id = 999
        def __str__(self):
            return "ALICE_CoPilot"

    class FakeChannel:
        name = "assistant"
        id = 123
        def __init__(self):
            self.sent_messages = []
        async def send(self, content):
            self.sent_messages.append(content)

    class FakeAuthor:
        id = 456
        def __str__(self):
            return "test-user"

    bot_user = FakeBotUser()

    class FakeClient:
        user = bot_user

    monkeypatch.setattr(main, "client", FakeClient())

    class FakeMessage:
        def __init__(self):
            self.author = FakeAuthor()
            self.channel = FakeChannel()
            self.mentions = [bot_user]
            self.content = f"<@{bot_user.id}> メンション付き質問"

    message = FakeMessage()

    saved_messages = []
    monkeypatch.setattr(main, "save_message", lambda **kwargs: saved_messages.append(kwargs))
    monkeypatch.setattr(main, "get_recent_messages", lambda channel_id, limit: [])
    monkeypatch.setattr(main, "should_use_memory", lambda question: False)
    monkeypatch.setattr(main, "ask_ollama", lambda messages: "メンション付きへの回答")
    monkeypatch.setattr(main, "run_memory_consolidation", lambda: asyncio.sleep(0))

    asyncio.run(main.on_message(message))

    assert len(saved_messages) == 2
    assert saved_messages[0]["role"] == "user"
    assert saved_messages[0]["content"] == "メンション付き質問"  # メンション表記が除去されている
    assert saved_messages[1]["role"] == "assistant"
    assert saved_messages[1]["content"] == "メンション付きへの回答"
    assert message.channel.sent_messages == ["メンション付きへの回答"]