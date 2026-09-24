"""
Tests for Assistant and Dev CoPilot services and internal API server.
"""
import asyncio
import pytest
from services.assistant_service import stream_assistant
from services.dev_copilot_service import ANTIGRAVITY_STATE, stream_copilot


@pytest.mark.anyio
async def test_assistant_stream_yields_events():
    """Verify assistant service yields SSE events."""
    events = []
    # Test with simple message
    async for ev in stream_assistant("テストこんにちは", session_id="test_assistant"):
        events.append(ev)

    assert len(events) > 0
    event_types = [e["type"] for e in events]
    assert "status" in event_types
    assert "done" in event_types or "delta" in event_types


@pytest.mark.anyio
async def test_dev_copilot_stream_lightweight():
    """Verify dev copilot yields immediate response for general question."""
    events = []
    async for ev in stream_copilot("Pythonのlistの長さを取得する関数は？", session_id="test_copilot"):
        events.append(ev)

    assert len(events) > 0
    event_types = [e["type"] for e in events]
    assert "status" in event_types
    assert "done" in event_types or "delta" in event_types


def test_clean_llm_response():
    from services.assistant_service import clean_llm_response
    t1 = "thought\n<channel|>恐れ入ります、確認いたしました。"
    assert clean_llm_response(t1) == "恐れ入ります、確認いたしました。"

    t2 = "<thought>Thinking about answer</thought>了解しました。"
    assert clean_llm_response(t2) == "了解しました。"

    t3 = "thought\n予定を検索します。"
    assert clean_llm_response(t3) == "予定を検索します。"


def test_antigravity_model_switching_and_quotas():
    from services.antigravity_manager import (
        load_antigravity_settings,
        update_selected_model,
        increment_quota_usage,
    )
    # Switch to Pro
    s_pro = update_selected_model("Gemini 3.8 Pro")
    assert s_pro["selected_model"] == "Gemini 3.8 Pro"
    assert isinstance(s_pro["five_hour_limit"]["used_percent"], int)
    assert isinstance(s_pro["weekly_limit"]["used_percent"], int)

    # Switch to Claude
    s_claude = update_selected_model("Claude 3.5 Sonnet")
    assert s_claude["selected_model"] == "Claude 3.5 Sonnet"
    assert isinstance(s_claude["five_hour_limit"]["used_percent"], int)

    # Switch to Local
    s_local = update_selected_model("gemma4:12b (Local Ollama)")
    assert s_local["selected_model"] == "gemma4:12b (Local Ollama)"
    assert s_local["five_hour_limit"]["used_percent"] == 0

    # Switch to Flash
    s_flash = update_selected_model("Gemini 3.8 Flash (High)")
    assert s_flash["selected_model"] == "Gemini 3.8 Flash (High)"
    assert isinstance(s_flash["five_hour_limit"]["used_percent"], int)

