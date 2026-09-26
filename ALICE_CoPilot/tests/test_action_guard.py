import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
from pathlib import Path
import pytest

import main

def test_action_guard_suppresses_hallucination(monkeypatch):
    """When LLM tries to claim it added a task without calling any tool, Action Guard must suppress it."""
    call_count = 0

    def fake_original_ask_ollama(messages, tools=None):
        nonlocal call_count
        call_count += 1
        return {
            "message": {
                "role": "assistant",
                "content": "水曜日の業務タスクに「テストタスク」を追加しました。",
                "tool_calls": None,
            }
        }

    monkeypatch.setattr(main, "original_ask_ollama", fake_original_ask_ollama)

    messages = [{"role": "user", "content": "水曜日の業務タスクに「テストタスク」を追加してください"}]
    answer = asyncio.run(main.ask_ollama_with_tools(messages, max_turns=3))

    assert "システム警告" in answer
    assert "操作ツールが実行されなかったため" in answer
    assert "追加しました" not in answer
    assert call_count >= 2
    print("Action Guard hallucination suppression test PASSED!")

def test_action_guard_allows_real_tool(monkeypatch):
    """When LLM calls the real create_todo_task tool, it should allow the completion message."""
    call_count = 0

    def fake_original_ask_ollama(messages, tools=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_task_1",
                            "function": {
                                "name": "create_todo_task",
                                "arguments": {"title": "正規タスク", "due_date": "2026-09-23"},
                            },
                        }
                    ],
                }
            }
        else:
            return {
                "message": {
                    "role": "assistant",
                    "content": "業務タスクに「正規タスク」を登録しました。",
                    "tool_calls": None,
                }
            }

    async def fake_execute_tool(name, args):
        return {"status": "success", "message": "created"}

    monkeypatch.setattr(main, "original_ask_ollama", fake_original_ask_ollama)
    monkeypatch.setattr(main, "execute_tool", fake_execute_tool)

    messages = [{"role": "user", "content": "業務タスクに「正規タスク」を追加して"}]
    answer = asyncio.run(main.ask_ollama_with_tools(messages, max_turns=3))

    assert "登録しました" in answer
    assert "システム警告" not in answer
    print("Action Guard legitimate tool execution test PASSED!")

if __name__ == "__main__":
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    test_action_guard_suppresses_hallucination(mp)
    mp.undo()
    mp = MonkeyPatch()
    test_action_guard_allows_real_tool(mp)
    mp.undo()
    print("ALL ACTION GUARD TESTS PASSED!")
