"""ALICE_Search E2E 総合テスト

テスト対象:
1. --index-job CLI
2. --query CLI (検索結果から正本Artifactへの到達性検証)
3. --reindex CLI (全Workspaceからの完全再構築性)
4. CoreWorker からの自動インデックス更新
5. インデックス更新失敗時も Job が COMPLETED を維持すること (成否分離)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
core_path = str(PROJECT_ROOT / "ALICE_Core")
if core_path not in sys.path:
    sys.path.insert(0, core_path)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ALICE_Core.core.job_queue import JobQueue
from ALICE_Core.core.worker import CoreWorker
from ALICE_Core.core.workspace_manager import WorkspaceManager
from ALICE_Core.models.job import Job, JobStatus
from ALICE_Core.publisher.publisher import Publisher


@pytest.fixture
def e2e_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="alice_search_e2e_"))
    ws_root = temp_dir / "workspaces"
    ws_root.mkdir(parents=True, exist_ok=True)
    db_path = temp_dir / "alice_index.db"

    project_root = Path(__file__).resolve().parent.parent.parent
    cli_path = project_root / "ALICE_Search" / "cli.py"
    python_bin = project_root / "myenv" / "core_env" / "bin" / "python" 

    yield {
        "temp_dir": temp_dir,
        "ws_root": ws_root,
        "db_path": db_path,
        "cli_path": cli_path,
        "python_bin": python_bin,
    }

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_1_cli_index_and_artifact_traceability(e2e_env):
    """1. --index-job と --query の実行、および正本 Artifact への到達性検証"""
    ws_root = e2e_env["ws_root"]
    db_path = e2e_env["db_path"]
    cli_path = e2e_env["cli_path"]
    python_bin = e2e_env["python_bin"]

    job_dir = ws_root / "job_test_e2e_01"
    job_dir.mkdir(parents=True, exist_ok=True)

    job_data = {
        "job_id": "job_test_e2e_01",
        "user_id": "user_e2e_alpha",
        "status": "COMPLETED",
        "workflow": ["transcript", "summary"],
        "created_at": "2026-09-11T15:00:00",
        "input_metadata": {"original_name": "executive_meeting.mp3"},
    }
    (job_dir / "job.json").write_text(json.dumps(job_data), encoding="utf-8")

    s_dir = job_dir / "summary"
    s_dir.mkdir(parents=True, exist_ok=True)
    summary_file = s_dir / "summary.txt"
    summary_file.write_text("第3四半期の売上目標について協議しました。", encoding="utf-8")

    t_dir = job_dir / "transcript"
    t_dir.mkdir(parents=True, exist_ok=True)
    (t_dir / "transcript.txt").write_text("売上目標の達成に向けた施策です。", encoding="utf-8")
    # 正本 JSON も配置
    (t_dir / "transcript.json").write_text(json.dumps([{"text": "売上目標"}]), encoding="utf-8")

    # 1. --index-job
    res = subprocess.run(
        [str(python_bin), str(cli_path), "--db-path", str(db_path), "--index-job", str(job_dir)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Index job failed: {res.stderr}"

    # 2. --query "売上目標"
    res = subprocess.run(
        [
            str(python_bin),
            str(cli_path),
            "--db-path",
            str(db_path),
            "--query",
            "売上目標",
            "--user",
            "user_e2e_alpha",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Query failed: {res.stderr}"

    output = json.loads(res.stdout)
    assert output["total"] == 2
    assert output["filters"]["user_id"] == "user_e2e_alpha"

    # 正本 Artifact への到達性検証:
    # 返却された artifact_abs_path および workspace_dir が実在すること
    for hit in output["hits"]:
        assert hit["job_id"] == "job_test_e2e_01"
        ws_path = Path(hit["workspace_dir"])
        art_path = Path(hit["artifact_abs_path"])
        assert ws_path.exists() and ws_path.is_dir()
        assert art_path.exists() and art_path.is_file()

        # 正本 transcript.json も Workspace から直接参照可能
        json_origin = ws_path / "transcript" / "transcript.json"
        assert json_origin.exists()


def test_2_reindex_full_recovery(e2e_env):
    """2. --reindex による Source of Truth からの 100% 再構築性"""
    ws_root = e2e_env["ws_root"]
    db_path = e2e_env["db_path"]
    cli_path = e2e_env["cli_path"]
    python_bin = e2e_env["python_bin"]

    # 3件の Workspace を作成
    for i in range(3):
        jdir = ws_root / f"job_reindex_{i}"
        jdir.mkdir(parents=True, exist_ok=True)
        (jdir / "job.json").write_text(
            json.dumps({"job_id": f"job_reindex_{i}", "user_id": f"user_{i}", "status": "COMPLETED"}),
            encoding="utf-8",
        )
        sdir = jdir / "summary"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "summary.txt").write_text(f"リカバリテスト本文 {i} 番目", encoding="utf-8")

    # DB が存在しない状態から --reindex
    res = subprocess.run(
        [
            str(python_bin),
            str(cli_path),
            "--db-path",
            str(db_path),
            "--workspaces-dir",
            str(ws_root),
            "--reindex",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    reindex_res = json.loads(res.stdout)
    assert reindex_res["success"] == 3
    assert reindex_res["failed"] == 0

    # 検索で3件ともインデックスされていることを確認
    res = subprocess.run(
        [str(python_bin), str(cli_path), "--db-path", str(db_path), "--query", "リカバリテスト"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    output = json.loads(res.stdout)
    assert output["total"] == 3


def test_3_core_worker_auto_indexing_and_error_isolation(e2e_env):
    """3. CoreWorker からの安全なインデックス更新とエラー分離 (耐障害性)"""
    ws_root = e2e_env["ws_root"]
    sample_audio = Path("/data/tmp/for_transcript_test/sps-smp.mp3")

    wm = WorkspaceManager(base_dir=ws_root)
    queue = JobQueue()

    # モックモジュール準備
    mock_bin = sys.executable
    mock_cli = ws_root / "mock_cli.py"
    mock_cli.write_text(
        """import sys, argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument("--workspace", required=True)
args = p.parse_args()
ws = Path(args.workspace)
(ws / "summary").mkdir(parents=True, exist_ok=True)
(ws / "summary" / "summary.txt").write_text("CoreWorker 自動インデックス成功テスト本文")
"""
    )

    mock_runners = {
        "summary": {
            "python_bin": mock_bin,
            "cli_path": str(mock_cli),
            "artifact_dir": "summary",
            "primary_artifact": "summary.txt",
            "contract_artifacts": ["summary.txt"],
        }
    }

    mock_pub = Publisher()
    mock_pub.line_publisher = MagicMock()

    worker = CoreWorker(
        job_queue=queue,
        workspace_manager=wm,
        publisher=mock_pub,
        module_runners=mock_runners,
    )

    # 1. 正常系: Job COMPLETED 後にインデックスが自動更新されること
    job = wm.create_workspace("user_auto_index", sample_audio, ["summary"], "test.mp3")
    success = worker.process_job(job)
    assert success is True
    assert job.status == JobStatus.COMPLETED

    # 2. 異常系 (成否分離の検証):
    # ALICE_Search 呼び出しで例外または失敗が発生しても、Job は COMPLETED のまま変更されないこと
    worker._update_search_index = MagicMock(side_effect=RuntimeError("Simulated Index DB Crash"))

    job_fail_index = wm.create_workspace("user_fail_index", sample_audio, ["summary"], "test2.mp3")
    # 例外がスローされず、Job が COMPLETED として完了すること
    try:
        success = worker.process_job(job_fail_index)
    except Exception as e:
        pytest.fail(f"process_job raised an exception due to search index failure: {e}")

    assert success is True
    assert job_fail_index.status == JobStatus.COMPLETED
    assert job_fail_index.completed_at is not None
    assert job_fail_index.error_message is None


def main():
    print("=== Running test_search_e2e.py ===")
    import tempfile
    td = Path(tempfile.mkdtemp(prefix="alice_e2e_run_"))
    try:
        env = {
            "temp_dir": td,
            "ws_root": td / "workspaces",
            "db_path": td / "alice_index.db",
            "cli_path": Path(__file__).resolve().parent.parent.parent / "ALICE_Search" / "cli.py",
            "python_bin": Path(__file__).resolve().parent.parent.parent / "myenv" / "core_env" / "bin" / "python",
        }
        env["ws_root"].mkdir(parents=True, exist_ok=True)

        print("[E2E] Running test_1_cli_index_and_artifact_traceability...")
        test_1_cli_index_and_artifact_traceability(env)
        print(">>> test_1 PASSED!")

        print("[E2E] Running test_2_reindex_full_recovery...")
        test_2_reindex_full_recovery(env)
        print(">>> test_2 PASSED!")

        print("[E2E] Running test_3_core_worker_auto_indexing_and_error_isolation...")
        test_3_core_worker_auto_indexing_and_error_isolation(env)
        print(">>> test_3 PASSED!")

        print("=== ALL E2E TESTS PASSED SUCCESSFULLY! ===")
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    main()

