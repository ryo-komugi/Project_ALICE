import os
import json
import shutil
import tempfile
from pathlib import Path
import pytest
from models.job import Job, JobStatus
from hub.workspace import WorkspaceManager


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)
        wm = WorkspaceManager(base_dir=base_dir)

        # ダミー音声ファイル作成
        src_audio = base_dir / "test_meeting.m4a"
        with open(src_audio, "wb") as f:
            f.write(b"FAKE_AUDIO_DATA_FOR_TESTING" * 100)

        job = wm.create_workspace(
            user_id="test_user",
            src_file=src_audio,
            workflow=["transcript", "summary"],
            original_filename="test_meeting.m4a",
        )
        yield wm, job, base_dir


def test_cleanup_skipped_when_transcript_missing(temp_workspace):
    wm, job, base_dir = temp_workspace
    audio_path = job.workspace_dir / "input" / "test_meeting.m4a"
    assert audio_path.exists()

    # transcript.json が存在しない状態ではクリーンアップがスキップされ、音声は維持される
    result = wm.cleanup_input_audio(job)
    assert result is False
    assert audio_path.exists()
    assert not (job.workspace_dir / "input" / "test_meeting.m4a.txt").exists()


def test_cleanup_success_when_transcript_exists(temp_workspace):
    wm, job, base_dir = temp_workspace
    audio_path = job.workspace_dir / "input" / "test_meeting.m4a"
    assert audio_path.exists()
    original_size = audio_path.stat().st_size

    # Source of Truth (transcript.json) を作成
    transcript_file = job.workspace_dir / "transcript" / "transcript.json"
    with open(transcript_file, "w", encoding="utf-8") as f:
        json.dump({"utterances": [{"speaker": "SPEAKER_00", "text": "こんにちは"}]}, f)

    # クリーンアップ実行
    result = wm.cleanup_input_audio(job)
    assert result is True

    # 元の音声バイナリは削除されている
    assert not audio_path.exists()

    # プレースホルダーテキストが存在し、内容が正しい
    placeholder_file = job.workspace_dir / "input" / "test_meeting.m4a.txt"
    assert placeholder_file.exists()
    content = placeholder_file.read_text(encoding="utf-8")
    assert "[Audio Source Cleared]" in content
    assert "Original Filename: test_meeting.m4a" in content
    assert f"Original Size: {original_size} bytes" in content
    assert "Source of Truth: transcript/transcript.json" in content

    # job.json のメタデータが更新されている
    reloaded_job = wm.load_job(job.workspace_dir)
    assert reloaded_job.input_metadata.get("audio_cleared") is True
    assert "cleared_at" in reloaded_job.input_metadata
