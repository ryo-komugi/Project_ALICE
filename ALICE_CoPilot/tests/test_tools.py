"""
Unit tests for ALICE_CoPilot Tools and Tool Calling Engine.
"""
import asyncio
import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import discord

# Mock discord.Client.run before importing main
discord.Client.run = lambda self, token: None

import main
from tools import TOOLS_SCHEMA, execute_tool, TOOL_FUNCTIONS
from tools.search_tools import search_past_meetings
from tools.system_tools import (
    get_system_status,
    get_recent_jobs,
    update_daily_peaks,
    get_cpu_temp_c,
)


def test_tools_schema_definition():
    assert isinstance(TOOLS_SCHEMA, list)
    assert len(TOOLS_SCHEMA) >= 3

    tool_names = {t["function"]["name"] for t in TOOLS_SCHEMA}
    assert "search_past_meetings" in tool_names
    assert "get_system_status" in tool_names
    assert "get_recent_jobs" in tool_names
    assert "search_project_memory" in tool_names

    for t in TOOLS_SCHEMA:
        assert t["type"] == "function"
        assert "description" in t["function"]
        assert "parameters" in t["function"]


def test_execute_tool_unknown():
    res = asyncio.run(execute_tool("nonexistent_tool_xyz", {}))
    assert "error" in res
    assert "Unknown tool" in res["error"]


def test_get_system_status():
    status = get_system_status()
    assert isinstance(status, dict)
    assert "current" in status
    assert "today_peaks" in status

    cur = status["current"]
    assert "cpu" in cur
    assert "ram" in cur
    assert "storage" in cur
    assert "services" in cur

    peaks = status["today_peaks"]
    assert "date" in peaks
    assert "vram_peak_mb" in peaks


def test_update_daily_peaks(tmp_path, monkeypatch):
    from tools import system_tools
    fake_stats = tmp_path / "system_daily_stats.json"
    monkeypatch.setattr(system_tools, "STATS_PATH", fake_stats)

    gpu = {
        "memory_used_mb": 5000,
        "memory_percent": 30.0,
        "utilization_percent": 25,
        "temperature_c": 45,
    }
    ram = {"used_gb": 4.5}
    peaks = system_tools.update_daily_peaks(gpu=gpu, cpu_temp=42.5, ram=ram)
    assert peaks["vram_peak_mb"] == 5000
    assert peaks["gpu_temp_peak_c"] == 45
    assert peaks["cpu_temp_peak_c"] == 42.5
    assert peaks["ram_peak_gb"] == 4.5

    # Higher peak updates; lower value does not overwrite peak
    gpu2 = {
        "memory_used_mb": 8000,
        "memory_percent": 50.0,
        "utilization_percent": 80,
        "temperature_c": 55,
    }
    peaks2 = system_tools.update_daily_peaks(gpu=gpu2, cpu_temp=40.0, ram=ram)
    assert peaks2["vram_peak_mb"] == 8000
    assert peaks2["gpu_temp_peak_c"] == 55
    assert peaks2["cpu_temp_peak_c"] == 42.5  # Retains higher temp


def test_get_cpu_temp_c_real():
    # If on Linux with coretemp, should return float or None safely
    temp = get_cpu_temp_c()
    if temp is not None:
        assert isinstance(temp, float)
        assert 10.0 <= temp <= 110.0


def test_get_recent_jobs():
    jobs = get_recent_jobs(limit=2)
    assert isinstance(jobs, list)
    for j in jobs:
        assert "job_id" in j
        assert "status" in j


def test_search_past_meetings_empty_query():
    res = asyncio.run(search_past_meetings(""))
    assert res["total"] == 0
    assert "空です" in res["message"]


def test_search_past_meetings_success(monkeypatch):
    from tools import search_tools

    async def fake_execute_search(query, limit=5, user_id=None, module=None):
        return {
            "total": 1,
            "hits": [
                {
                    "job_id": "job_123",
                    "module": "summary",
                    "created_at": "2026-09-13T10:00:00",
                    "snippet": "<b>面談</b>の議事録内容です",
                    "metadata": {"original_filename": "meeting.mp3"},
                }
            ],
        }

    monkeypatch.setattr(search_tools, "execute_search", fake_execute_search)

    res = asyncio.run(search_past_meetings("面談", limit=1))
    assert res["total"] == 1
    assert len(res["results"]) == 1
    r = res["results"][0]
    assert r["title"] == "meeting.mp3"
    assert r["module"] == "summary"
    assert "**面談**の議事録内容です" in r["snippet"]


def test_ask_ollama_with_tools_text_only(monkeypatch):
    """When Ollama returns direct text without tools, it should return content directly."""
    def fake_original_ask_ollama(messages, tools=None):
        return {
            "message": {
                "role": "assistant",
                "content": "こんにちは！調子はいかがですか？",
                "tool_calls": None,
            }
        }

    monkeypatch.setattr(main, "original_ask_ollama", fake_original_ask_ollama)

    messages = [{"role": "user", "content": "こんにちは"}]
    answer = asyncio.run(main.ask_ollama_with_tools(messages))
    assert answer == "こんにちは！調子はいかがですか？"


def test_ask_ollama_with_tools_loop(monkeypatch):
    """When Ollama returns a tool call, it executes the tool and sends result back."""
    call_count = 0

    def fake_original_ask_ollama(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First turn: returns tool call
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "get_system_status",
                                "arguments": {},
                            },
                        }
                    ],
                }
            }
        else:
            # Second turn: after tool result
            assert any(m.get("role") == "tool" for m in messages)
            return {
                "message": {
                    "role": "assistant",
                    "content": "現在のGPU使用率は0%で正常稼働しています。",
                    "tool_calls": None,
                }
            }

    monkeypatch.setattr(main, "original_ask_ollama", fake_original_ask_ollama)

    messages = [{"role": "user", "content": "GPUの負荷どう？"}]
    answer = asyncio.run(main.ask_ollama_with_tools(messages))
    assert call_count == 2
    assert "現在のGPU使用率は0%" in answer



def test_search_project_memory(monkeypatch):
    from tools import search_tools
    import memory.memory_search as memory_search

    # 1. Empty query
    res_empty = asyncio.run(search_tools.search_project_memory(""))
    assert res_empty["total"] == 0
    assert "空です" in res_empty["message"]

    # 2. Query with results
    def fake_search_memories(query, limit=5):
        return [
            {
                "id": "20260915_test_memory",
                "score": 3,
                "content": "# テストMemory\n\nドメイン取得の決定事項です。\n",
            }
        ]

    monkeypatch.setattr(memory_search, "search_memories", fake_search_memories)

    res_match = asyncio.run(search_tools.search_project_memory("ドメイン", limit=2))
    assert res_match["total"] == 1
    assert "results" in res_match
    assert "20260915_test_memory" in res_match["results"][0]["id"]
    assert "ドメイン取得" in res_match["results"][0]["snippet"]
