import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest

from services.action_guard import detect_intent, build_system_hint


def test_detect_intent_search():
    intent = detect_intent("先週の面談の議事録を検索して")
    assert intent.is_search_query is True
    assert intent.is_system_query is False

    hint = build_system_hint(intent)
    assert "search_past_meetings" in hint


def test_detect_intent_system():
    intent = detect_intent("サーバーのGPU負荷とVRAM温度を教えて")
    assert intent.is_system_query is True
    assert intent.is_search_query is False

    hint = build_system_hint(intent)
    assert "get_system_status" in hint


def test_detect_intent_memory():
    intent = detect_intent("なぜCloudflare Tunnelを採用したのか設計方針を教えて")
    assert intent.is_memory_query is True

    hint = build_system_hint(intent)
    assert "search_project_memory" in hint


if __name__ == "__main__":
    test_detect_intent_search()
    test_detect_intent_system()
    test_detect_intent_memory()
    print("ALL ACTION GUARD TESTS PASSED!")
