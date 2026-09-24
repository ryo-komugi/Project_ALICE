import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from reviewer.patch_worker import (
    build_patch_prompt,
    enqueue_patch_task,
    init_queue_dirs,
    process_single_task,
)

class TestPatchWorker(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp_dir.name)
        self.inbox_dir = self.base_dir / "inbox"
        self.running_dir = self.base_dir / "running"
        self.completed_dir = self.base_dir / "completed"
        self.failed_dir = self.base_dir / "failed"
        self.logs_dir = self.base_dir / "logs"

        # Patch module queue directories
        self.patchers = [
            patch("reviewer.patch_worker.QUEUE_DIR", self.base_dir),
            patch("reviewer.patch_worker.INBOX_DIR", self.inbox_dir),
            patch("reviewer.patch_worker.RUNNING_DIR", self.running_dir),
            patch("reviewer.patch_worker.COMPLETED_DIR", self.completed_dir),
            patch("reviewer.patch_worker.FAILED_DIR", self.failed_dir),
            patch("reviewer.patch_worker.LOGS_DIR", self.logs_dir),
        ]
        for p in self.patchers:
            p.start()

        init_queue_dirs()

    def tearDown(self):
        for p in reversed(self.patchers):
            p.stop()
        self.tmp_dir.cleanup()

    def test_enqueue_patch_task(self):
        """Verify enqueue_patch_task writes valid JSON task file to inbox."""
        instruction = "Fix calculation logic in calculator.py"
        task_id = enqueue_patch_task(
            instruction=instruction,
            repo="ALICE_CoPilot",
            user_id="test_user",
            source="test_runner",
        )

        self.assertTrue(task_id.startswith("patch_"))
        task_file = self.inbox_dir / f"{task_id}.json"
        self.assertTrue(task_file.exists())

        with open(task_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["task_id"], task_id)
        self.assertEqual(data["instruction"], instruction)
        self.assertEqual(data["repo"], "ALICE_CoPilot")
        self.assertEqual(data["user_id"], "test_user")
        self.assertEqual(data["source"], "test_runner")
        self.assertEqual(data["status"], "queued")

    def test_build_patch_prompt_contains_protocols(self):
        """Verify prompt contains strict protocols: HANDOFF, Memory, pytest, git commit."""
        prompt = build_patch_prompt("タイムアウトSLAを追加", "ALICE_Core")
        self.assertIn("タイムアウトSLAを追加", prompt)
        self.assertIn("ALICE_Core", prompt)
        self.assertIn("HANDOFF.md", prompt)
        self.assertIn("ALICE_Memory", prompt)
        self.assertIn("pytest", prompt)
        self.assertIn("git commit", prompt)

    @patch("reviewer.patch_worker.notify_discord_completion", new_callable=AsyncMock)
    @patch("reviewer.patch_worker.sync_handoff_files")
    @patch("reviewer.patch_worker.run_agy_subprocess", new_callable=AsyncMock)
    def test_process_single_task_success(self, mock_run_agy, mock_sync_handoff, mock_notify):
        """Verify successful task processing moves file to completed directory."""
        task_id = enqueue_patch_task("テスト改修", "ALICE_CoPilot")
        task_file = self.inbox_dir / f"{task_id}.json"

        mock_run_agy.return_value = (0, "改修完了しました。pytest: 100% PASS")

        with patch("subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(stdout="hash111"), # head_before
                MagicMock(stdout="hash222"), # head_after
                MagicMock(stdout="feat: updated patch"), # commit_msg
                MagicMock(stdout="1 file changed"), # commit_diff
            ]
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(process_single_task(task_file, discord_client=MagicMock()))
            loop.close()

        self.assertTrue(success)
        self.assertFalse(task_file.exists())
        completed_file = self.completed_dir / f"{task_id}.json"
        self.assertTrue(completed_file.exists())

        with open(completed_file, "r", encoding="utf-8") as f:
            c_data = json.load(f)
        self.assertEqual(c_data["status"], "completed")
        self.assertTrue(c_data["committed"])
        self.assertEqual(c_data["commit_hash"], "hash222")
        mock_sync_handoff.assert_called_once()
        mock_notify.assert_called_once()

    @patch("reviewer.patch_worker.notify_discord_completion", new_callable=AsyncMock)
    @patch("reviewer.patch_worker.sync_handoff_files")
    @patch("reviewer.patch_worker.run_agy_subprocess", new_callable=AsyncMock)
    def test_process_single_task_failure(self, mock_run_agy, mock_sync_handoff, mock_notify):
        """Verify failed task processing moves file to failed directory."""
        task_id = enqueue_patch_task("失敗テスト", "ALICE_CoPilot")
        task_file = self.inbox_dir / f"{task_id}.json"

        mock_run_agy.return_value = (1, "エラーが発生しました")

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(stdout="hash111")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(process_single_task(task_file, discord_client=MagicMock()))
            loop.close()

        self.assertFalse(success)
        self.assertFalse(task_file.exists())
        failed_file = self.failed_dir / f"{task_id}.json"
        self.assertTrue(failed_file.exists())

        with open(failed_file, "r", encoding="utf-8") as f:
            f_data = json.load(f)
        self.assertEqual(f_data["status"], "failed")
        self.assertFalse(f_data["committed"])
