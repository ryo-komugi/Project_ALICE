"""
Unit tests for ALICE_CoPilot search_handler.
"""
import asyncio
from unittest.mock import MagicMock
import discord
from search_handler import (
    clean_html_snippet,
    build_search_embed,
    is_search_request,
    execute_search,
)


def test_clean_html_snippet():
    raw = "本件は、語り手（当事者）が過去に経験した<b>司法判断</b>（<b>贈賄</b>・訴訟に関する事件）において、"
    cleaned = clean_html_snippet(raw)
    assert "**司法判断**" in cleaned
    assert "**贈賄**" in cleaned
    assert "<b>" not in cleaned
    assert "</b>" not in cleaned


def test_is_search_request():
    # 1. #search channel (no prefix needed)
    msg_search_ch = MagicMock()
    msg_search_ch.channel.name = "search"
    msg_search_ch.content = "面談"
    msg_search_ch.author.bot = False
    is_s, q = is_search_request(msg_search_ch)
    assert is_s is True
    assert q == "面談"

    # 1-b. bot message in #search channel should be ignored
    msg_bot = MagicMock()
    msg_bot.channel.name = "search"
    msg_bot.content = "検索結果"
    msg_bot.author.bot = True
    is_s, q = is_search_request(msg_bot)
    assert is_s is False

    # 2. Other channel with !search prefix
    msg_general_cmd = MagicMock()
    msg_general_cmd.channel.name = "general"
    msg_general_cmd.content = "!search 司法"
    msg_general_cmd.author.bot = False
    is_s, q = is_search_request(msg_general_cmd)
    assert is_s is True
    assert q == "司法"

    # 3. Other channel with !s prefix
    msg_general_cmd2 = MagicMock()
    msg_general_cmd2.channel.name = "general"
    msg_general_cmd2.content = "!s 予算"
    msg_general_cmd2.author.bot = False
    is_s, q = is_search_request(msg_general_cmd2)
    assert is_s is True
    assert q == "予算"

    # 4. Other channel with Japanese prefix
    msg_general_ja = MagicMock()
    msg_general_ja.channel.name = "general"
    msg_general_ja.content = "検索 面談記録"
    msg_general_ja.author.bot = False
    is_s, q = is_search_request(msg_general_ja)
    assert is_s is True
    assert q == "面談記録"

    # 5. Normal conversation in general channel
    msg_normal = MagicMock()
    msg_normal.channel.name = "general"
    msg_normal.content = "こんにちは、お元気ですか？"
    msg_normal.author.bot = False
    is_s, q = is_search_request(msg_normal)
    assert is_s is False
    assert q == ""


def test_build_search_embed_with_hits():
    mock_result = {
        "total": 1,
        "query": "面談",
        "hits": [
            {
                "job_id": "job_test_001",
                "user_id": "user_1",
                "module": "summary",
                "created_at": "2026-09-11T22:00:00.000",
                "snippet": "<b>面談</b>の議事録です",
                "metadata": {
                    "original_filename": "meeting.mp3",
                },
            }
        ]
    }
    embed = build_search_embed(mock_result, "面談")
    assert "検索結果: 面談" in embed.title
    assert len(embed.fields) == 1
    assert "meeting.mp3" in embed.fields[0].name
    assert "> **面談**の議事録です" in embed.fields[0].value
    # No noisy emojis
    for emoji in ["🔍", "⚠️", "📄", "📅", "📝", "🆔"]:
        assert emoji not in embed.title
        assert emoji not in embed.fields[0].name
        assert emoji not in embed.fields[0].value


def test_build_search_embed_zero_hits():
    mock_result = {"total": 0, "query": "存在しない単語", "hits": []}
    embed = build_search_embed(mock_result, "存在しない単語")
    assert "見つかりませんでした" in embed.description
    assert "🔍" not in embed.title


def test_build_search_embed_error():
    mock_result = {"total": 0, "query": "error_test", "error": "DB connection failed"}
    embed = build_search_embed(mock_result, "error_test")
    assert "検索エラー" in embed.title
    assert "DB connection failed" in embed.description
    assert "⚠️" not in embed.title


def test_execute_search_real_cli():
    # 実機 ALICE_Search CLI の疎通テスト (asyncio.run)
    result = asyncio.run(execute_search("面談", limit=2))
    assert "total" in result
    assert "hits" in result
    assert isinstance(result["hits"], list)


def test_handle_search_message_enforces_owner_core_user_id(monkeypatch):
    """Verify handle_search_message always passes OWNER_CORE_USER_ID to execute_search."""
    from unittest.mock import AsyncMock
    import search_handler
    import config

    called_kwargs = {}

    async def fake_execute_search(query, limit=5, user_id=None, module=None, **kwargs):
        called_kwargs["query"] = query
        called_kwargs["limit"] = limit
        called_kwargs["user_id"] = user_id
        return {"total": 0, "hits": []}

    monkeypatch.setattr(search_handler, "execute_search", fake_execute_search)

    mock_msg = MagicMock(spec=discord.Message)
    mock_msg.channel.name = "search"
    mock_msg.content = "面談"
    mock_msg.author.bot = False
    mock_msg.channel.send = AsyncMock()

    handled = asyncio.run(search_handler.handle_search_message(mock_msg))
    assert handled is True
    assert called_kwargs["query"] == "面談"
    assert called_kwargs["user_id"] == config.OWNER_CORE_USER_ID
    mock_msg.channel.send.assert_awaited_once()


def test_execute_search_owner_isolation_real_cli():
    """Verify real ALICE_Search CLI filters strictly by user_id."""
    import config
    owner_id = config.OWNER_CORE_USER_ID

    # 1. Searching with owner ID should only return hits belonging to the owner
    owner_result = asyncio.run(execute_search("面談", limit=3, user_id=owner_id))
    assert "hits" in owner_result
    for hit in owner_result["hits"]:
        assert hit["user_id"] == owner_id

    # 2. Searching with non-existent guest user ID should return zero hits
    guest_result = asyncio.run(execute_search("面談", limit=3, user_id="guest_nonexistent_9999"))
    assert guest_result["total"] == 0
    assert len(guest_result["hits"]) == 0
