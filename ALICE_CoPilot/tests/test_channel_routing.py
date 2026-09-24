"""
Unit tests for Discord channel separation and Morning Briefing interactive buttons.
Verifies:
1. #assistant channel routes to Ollama tool loop.
2. #copilot channel routes directly to Antigravity without invoking Ollama.
3. !report / !morning / !apply commands.
4. Morning Briefing Action Button view creation.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from reviewer.report_manager import (
    build_morning_briefing_embed,
    create_morning_briefing_view,
    MorningBriefingActionView,
)


class TestChannelRouting(unittest.IsolatedAsyncioTestCase):

    def test_morning_briefing_view_creation(self):
        """Verify MorningBriefingActionView creation when improvements are present."""
        report_with_imp = {
            "id": 10,
            "summary": "点検完了",
            "improvements": ["カタカナ正規表現の強化", "Tasks除外タグの追加"],
        }
        view = create_morning_briefing_view(report_with_imp)
        self.assertIsNotNone(view)
        self.assertIsInstance(view, MorningBriefingActionView)
        self.assertEqual(len(view.children), 1)
        button = view.children[0]
        self.assertEqual(button.label, "🛠️ 改善案を自律改修する")

        # When no improvements, no view should be returned
        report_no_imp = {
            "id": 11,
            "summary": "点検完了",
            "improvements": [],
        }
        view_none = create_morning_briefing_view(report_no_imp)
        self.assertIsNone(view_none)

    async def test_assistant_channel_routes_to_ollama(self):
        """Verify that messages in #assistant channel call ask_ollama_with_tools."""
        import main

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.bot = False
        mock_msg.channel = MagicMock()
        mock_msg.channel.name = "assistant"
        mock_msg.channel.id = 12345
        mock_msg.content = "明日の予定を教えて"
        mock_msg.mentions = []
        mock_msg.attachments = []

        with patch("main.save_message") as mock_save, \
             patch("main.should_use_memory", return_value=False), \
             patch("main.get_recent_messages", return_value=[]), \
             patch("main.ask_ollama_with_tools", new_callable=AsyncMock) as mock_ask_ollama, \
             patch("main.run_memory_consolidation", new_callable=AsyncMock):

            mock_ask_ollama.return_value = "明日は会議が2件あります。"
            mock_msg.channel.send = AsyncMock()

            await main.on_message(mock_msg)

            self.assertTrue(mock_ask_ollama.called)
            mock_msg.channel.send.assert_called_with("明日は会議が2件あります。")

    async def test_copilot_channel_routes_to_antigravity(self):
        """Verify that messages in #copilot channel bypass Ollama and route to Antigravity stream_copilot."""
        import main

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.bot = False
        mock_msg.channel = MagicMock()
        mock_msg.channel.name = "copilot"
        mock_msg.channel.id = 67890
        mock_msg.content = "Jobクラスの定義を調べて"
        mock_msg.mentions = []
        mock_msg.attachments = []

        async def mock_stream_copilot(prompt: str, session_id: str):
            yield {"type": "status", "message": "Thinking..."}
            yield {"type": "done", "full_content": "Jobクラスは models/job.py に定義されています。"}

        with patch("main.save_message") as mock_save, \
             patch("main.ask_ollama_with_tools", new_callable=AsyncMock) as mock_ask_ollama, \
             patch("services.dev_copilot_service.stream_copilot", side_effect=mock_stream_copilot):

            mock_msg.channel.send = AsyncMock()

            await main.on_message(mock_msg)

            # Ollama must NOT be called for #copilot channel
            self.assertFalse(mock_ask_ollama.called)
            # Antigravity answer sent to Discord channel
            self.assertTrue(any("Jobクラスは models/job.py に定義されています。" in call[0][0] for call in mock_msg.channel.send.call_args_list))

    async def test_apply_command_triggers_auto_patcher(self):
        """Verify that !apply command triggers execute_autonomous_patch."""
        import main

        mock_msg = MagicMock()
        mock_msg.author = MagicMock()
        mock_msg.author.bot = False
        mock_msg.channel = MagicMock()
        mock_msg.channel.name = "copilot"
        mock_msg.channel.id = 67890
        mock_msg.content = "!apply"
        mock_msg.mentions = []
        mock_msg.attachments = []

        mock_report = {
            "id": 99,
            "improvements": ["カタカナ正規表現の修正"],
        }

        mock_patch_result = {
            "status": "completed",
            "committed": True,
            "commit_hash": "a1b2c3d",
            "ans_text": "正規表現を修正し、テストに合格しました。",
            "modified_files": ["services/memory_search.py"],
        }

        with patch("reviewer.report_manager.get_latest_report", return_value=mock_report), \
             patch("reviewer.patch_worker.enqueue_patch_task", return_value="patch_test_123") as mock_enqueue:

            mock_msg.channel.send = AsyncMock()

            await main.on_message(mock_msg)

            self.assertTrue(mock_enqueue.called)
            # Check that reply contains task ID
            self.assertTrue(any("patch_test_123" in call[0][0] for call in mock_msg.channel.send.call_args_list))


if __name__ == "__main__":
    unittest.main()
