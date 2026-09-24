import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import config
from hub.worker import CoreWorker
from models.job import Job, JobStatus

class TestWorkerResilience(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp_dir.name)
        self.workspace_dir = self.base_dir / "workspaces" / "job_test_001"
        self.logs_dir = self.workspace_dir / "logs"
        self.artifact_dir = self.workspace_dir / "transcript"
        
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        self.job = Job(
            job_id="job_test_001",
            user_id="user_1",
            input_file=self.workspace_dir / "input.m4a",
            workspace_dir=self.workspace_dir,
            status=JobStatus.RUNNING,
            current_step="transcript",
        )

        self.worker = CoreWorker(
            job_queue=MagicMock(),
            workspace_manager=MagicMock(),
        )
        self.runner_info = {
            "python_bin": sys.executable,
            "cli_path": "fake_cli.py",
            "module_cwd": str(self.base_dir),
            "artifact_dir": "transcript",
            "primary_artifact": "transcript.json",
            "contract_artifacts": ["transcript.json"],
        }

    def tearDown(self):
        self.tmp_dir.cleanup()

    @patch("subprocess.run")
    def test_execute_module_success_first_attempt(self, mock_run):
        """1回目で成功する場合の挙動"""
        primary_file = self.artifact_dir / "transcript.json"
        primary_file.write_text("{}", encoding="utf-8")

        mock_run.return_value = MagicMock(returncode=0)

        success, path, artifacts, code, err = self.worker._execute_module(
            self.job, "transcript", self.runner_info
        )

        self.assertTrue(success)
        self.assertEqual(path, primary_file)
        self.assertEqual(code, 0)
        self.assertIsNone(err)
        self.assertEqual(mock_run.call_count, 1)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_execute_module_retry_success(self, mock_run, mock_sleep):
        """1回目失敗、2回目成功のリトライ挙動"""
        primary_file = self.artifact_dir / "transcript.json"

        def side_effect(*args, **kwargs):
            if mock_run.call_count == 1:
                return MagicMock(returncode=1)
            primary_file.write_text("{}", encoding="utf-8")
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        with patch.object(config, "MODULE_MAX_RETRIES", 2), \
             patch.object(config, "MODULE_RETRY_BACKOFF_SEC", 1):
            success, path, artifacts, code, err = self.worker._execute_module(
                self.job, "transcript", self.runner_info
            )

        self.assertTrue(success)
        self.assertEqual(path, primary_file)
        self.assertEqual(code, 0)
        self.assertIsNone(err)
        self.assertEqual(mock_run.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_execute_module_retry_exhausted(self, mock_run, mock_sleep):
        """全リトライ上限を超過して失敗する場合"""
        mock_run.return_value = MagicMock(returncode=1)

        with patch.object(config, "MODULE_MAX_RETRIES", 2), \
             patch.object(config, "MODULE_RETRY_BACKOFF_SEC", 1):
            success, path, artifacts, code, err = self.worker._execute_module(
                self.job, "transcript", self.runner_info
            )

        self.assertFalse(success)
        self.assertIsNone(path)
        self.assertEqual(code, 1)
        self.assertIn("Process exited with 1", err)
        self.assertEqual(mock_run.call_count, 3) # 初回 + 2回リトライ = 3回
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_execute_module_timeout(self, mock_run, mock_sleep):
        """タイムアウト発生時のハンドリング"""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="fake", timeout=10)

        with patch.object(config, "MODULE_MAX_RETRIES", 1), \
             patch.object(config, "MODULE_TIMEOUT_SEC", 10), \
             patch.object(config, "MODULE_RETRY_BACKOFF_SEC", 1):
            success, path, artifacts, code, err = self.worker._execute_module(
                self.job, "transcript", self.runner_info
            )

        self.assertFalse(success)
        self.assertIsNone(path)
        self.assertEqual(code, -1)
        self.assertIn("timed out after 10s", err)
        self.assertEqual(mock_run.call_count, 2) # 初回 + 1回リトライ = 2回
