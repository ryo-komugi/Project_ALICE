"""
Full E2E Pipeline Integration Test for Official Minutes (ALICE_Minutes).
Workflow: ["transcript", "minutes"]
"""
import sys
import os
import json
import time
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

CORE_ROOT = Path(__file__).resolve().parent.parent
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from core.logger import initialize_logger
from hub.workspace import WorkspaceManager
from hub.queue import JobQueue
from hub.worker import CoreWorker
from models.job import JobStatus

initialize_logger()


def main():
    print("=" * 60)
    print("=== ALICE Minutes Full Pipeline E2E Test ===")
    print("=" * 60)

    # 1. 音声の準備 (69秒の日本語音声)
    src_audio = Path("/data/tmp/for_transcript_test/sps-smp.mp3")
    if not src_audio.exists():
        print(f"[ERROR] Source audio not found: {src_audio}")
        sys.exit(1)

    print(f"[*] Target Audio: {src_audio.name} ({src_audio.stat().st_size / 1024:.1f} KB)")

    # 2. Workspace と Job の作成
    wm = WorkspaceManager(base_dir="/data/runtime/workspaces")
    queue = JobQueue()
    published_events = []

    mock_publisher = MagicMock()
    def fake_publish(path, uid, module_name="minutes"):
        print(f"[MockPublisher] Published {path} to {uid} (module={module_name})")
        published_events.append({"path": str(path), "uid": uid, "module": module_name})
    mock_publisher.publish = fake_publish

    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_publisher,
    )

    test_user_id = "user_minutes_e2e_v10"
    job = wm.create_workspace(
        user_id=test_user_id,
        src_file=src_audio,
        workflow=["transcript", "minutes"],
        original_filename="sps-smp.mp3",
    )
    print(f"[*] Created Test Job: {job.job_id}")
    print(f"[*] Workspace: {job.workspace_dir}")
    print(f"[*] Workflow: {job.workflow}")

    # 3. パイプライン実行 (Transcript -> Minutes -> Publisher -> Search -> Audio Cleanup)
    start_time = time.time()
    print("\n[*] Starting CoreWorker.process_job (Transcript -> Minutes -> Publish -> Search -> Cleanup)...")
    success = worker.process_job(job)
    elapsed = time.time() - start_time
    print(f"[*] Process finished in {elapsed:.1f}s (Success={success})")

    # 4. 検証
    reloaded_job = wm.load_job(job.workspace_dir)
    print(f"\n[*] Final Job Status: {reloaded_job.status.value}")

    assert success is True, "Worker process_job failed!"
    assert reloaded_job.status == JobStatus.COMPLETED, f"Expected COMPLETED, got {reloaded_job.status}"

    # Source of Truth (Transcript)
    transcript_json = job.workspace_dir / "transcript" / "transcript.json"
    assert transcript_json.exists(), "Source of truth transcript.json missing!"
    print(f"[+] Source of Truth confirmed: {transcript_json.name} ({transcript_json.stat().st_size} bytes)")

    # Minutes Artifacts
    minutes_dir = job.workspace_dir / "minutes"
    minutes_txt = minutes_dir / "minutes.txt"
    minutes_md = minutes_dir / "minutes.md"
    analysis_json = minutes_dir / "analysis.json"
    metadata_json = minutes_dir / "metadata.json"

    assert minutes_txt.exists(), "minutes.txt missing!"
    assert minutes_md.exists(), "minutes.md missing!"
    assert analysis_json.exists(), "analysis.json missing!"
    assert metadata_json.exists(), "metadata.json missing!"

    print(f"[+] Minutes Primary Artifact confirmed: minutes.txt ({minutes_txt.stat().st_size} bytes)")
    print(f"[+] Minutes Markdown confirmed: minutes.md ({minutes_md.stat().st_size} bytes)")
    print(f"[+] Minutes Analysis JSON confirmed: analysis.json ({analysis_json.stat().st_size} bytes)")

    # Publisher Verification
    assert len(published_events) == 1, f"Expected 1 publish event, got {len(published_events)}"
    assert published_events[0]["module"] == "minutes", f"Expected module 'minutes', got {published_events[0]['module']}"
    assert "minutes_minutes.txt" in published_events[0]["path"] or "minutes.txt" in published_events[0]["path"]
    print(f"[+] Publisher delivery confirmed: {published_events[0]}")

    # Audio Cleanup Verification
    original_audio_path = job.workspace_dir / "input" / "sps-smp.mp3"
    placeholder_path = job.workspace_dir / "input" / "sps-smp.mp3.txt"

    assert not original_audio_path.exists(), "Original audio binary still exists! Should have been cleaned up."
    print(f"[+] Audio binary successfully deleted from input directory!")

    assert placeholder_path.exists(), "Audio placeholder txt missing!"
    placeholder_text = placeholder_path.read_text(encoding="utf-8")
    assert "[Audio Source Cleared]" in placeholder_text
    print(f"[+] Audio placeholder confirmed:\n{placeholder_text.strip()}")

    assert reloaded_job.input_metadata.get("audio_cleared") is True, "job.json metadata audio_cleared not True"
    print(f"[+] job.json input_metadata.audio_cleared: True")

    # 5. ALICE_Search Verification
    search_cli = (Path(__file__).resolve().parent.parent.parent / "ALICE_Search" / "cli.py")
    # 検索してみる（議事録の中の単語、あるいはユーザー名で検索）
    res = subprocess.run(
        [sys.executable, str(search_cli), "--query", "会議", "--user", test_user_id, "--limit", "5"],
        capture_output=True,
        text=True,
    )
    print(f"\n[*] Search CLI output (query='会議'):\n{res.stdout}")
    # ジョブが検索可能か、あるいは--userフィルタでヒットするか
    res_user = subprocess.run(
        [sys.executable, str(search_cli), "--query", "音声", "--user", test_user_id, "--limit", "5"],
        capture_output=True,
        text=True,
    )
    print(f"[*] Search CLI output (query='音声'):\n{res_user.stdout}")

    # 6. 生成された議事録のプレビュー表示
    print("\n" + "-" * 40)
    print("【生成された議事録テキスト (minutes.txt プレビュー)】")
    print("-" * 40)
    print(minutes_txt.read_text(encoding="utf-8")[:600] + "...")
    print("-" * 40)

    print("\n" + "=" * 60)
    print("=== MINUTES FULL PIPELINE E2E TEST PASSED! ===")
    print("=" * 60)


if __name__ == "__main__":
    main()
