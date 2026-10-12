import asyncio
import pytest
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from portal.admin import (
    generate_job_step,
    GenerateStepRequest,

    get_admin_dashboard,
    get_metrics,
    list_jobs,
    get_job_artifact,
    view_job_artifact,
    get_system_logs,
    _get_cpu_usage,
    _get_memory_usage,
    _get_gpu_usage,
    _get_disk_usage,
    _get_service_status,
)
from hub.container import workspace_manager


@pytest.mark.anyio
async def test_admin_dashboard_html():
    """Verify admin HTML dashboard loads successfully."""
    response = await get_admin_dashboard()
    assert isinstance(response, HTMLResponse)
    assert response.status_code == 200
    html = response.body.decode("utf-8")
    assert "Project_Alice" in html or "ALICE" in html
    assert "Management Cockpit" in html
    assert "Telemetry" in html or "TELEMETRY" in html
    assert "/static/admin/alice_logo.jpg" in html
    assert "/static/admin/alice_banner.jpg" in html
    assert "/static/admin/manifest.json" in html
    assert "apple-mobile-web-app-capable" in html
    assert "apple-touch-icon" in html
    assert "apple-touch-startup-image" in html
    assert "/static/admin/alice_splash.jpg" in html
    assert "alice-splash-screen" in html
    assert "theme-color" in html


@pytest.mark.anyio
async def test_admin_metrics_api():
    """Verify live metrics API returns system stats."""
    data = await get_metrics()
    assert isinstance(data, dict)
    assert "timestamp" in data
    assert "cpu" in data
    assert "memory" in data
    assert "gpu" in data
    assert "disk" in data
    assert "services" in data
    assert "queue_size" in data
    assert isinstance(data["queued_jobs"], list)

    # Verify telemetry types
    assert isinstance(data["cpu"]["cores"], int)
    assert isinstance(data["cpu"]["percent"], (int, float))
    assert isinstance(data["memory"]["total_gb"], (int, float))
    assert isinstance(data["disk"]["percent"], (int, float))
    assert "core" in data["services"]


@pytest.mark.anyio
async def test_admin_jobs_api():
    """Verify job listing API."""
    data = await list_jobs(limit=10)
    assert isinstance(data, list)
    if data:
        job_info = data[0]
        assert "job_id" in job_info
        assert "status" in job_info
        assert "artifacts" in job_info
        assert "logs" in job_info


@pytest.mark.anyio
async def test_admin_logs_api():
    """Verify system logs API and traversal rejection."""
    data = await get_system_logs(file="alice.log", tail=50)
    assert isinstance(data, dict)
    assert "lines" in data
    assert "file" in data
    assert "archives" in data

    # Directory traversal check
    with pytest.raises(HTTPException) as exc_info:
        await get_system_logs(file="../../etc/passwd")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info2:
        await get_system_logs(file="sub\\test.log")
    assert exc_info2.value.status_code == 400


@pytest.mark.anyio
async def test_admin_artifact_security():
    """Verify artifact download endpoint rejects path traversal."""
    with pytest.raises(HTTPException) as exc_1:
        await get_job_artifact(job_id="test-job", path="../secret.txt")
    assert exc_1.value.status_code == 400

    with pytest.raises(HTTPException) as exc_2:
        await get_job_artifact(job_id="test-job", path="/etc/shadow")
    assert exc_2.value.status_code == 400

    with pytest.raises(HTTPException) as exc_3:
        await get_job_artifact(job_id="test-job", path="..\\secret.txt")
    assert exc_3.value.status_code == 400

    # Non-existent job
    with pytest.raises(HTTPException) as exc_4:
        await get_job_artifact(job_id="non-existent-random-job-xyz", path="transcript/transcript.txt")
    assert exc_4.value.status_code == 404

    # Standalone Web View Traversal Security
    with pytest.raises(HTTPException) as exc_view_1:
        await view_job_artifact(job_id="test-job", path="../secret.txt")
    assert exc_view_1.value.status_code == 400

    with pytest.raises(HTTPException) as exc_view_2:
        await view_job_artifact(job_id="non-existent-random-job-xyz", path="transcript/transcript.txt")
    assert exc_view_2.value.status_code == 404


def test_system_telemetry_helpers():
    """Verify internal metrics helper functions execute safely without crashing."""
    cpu = _get_cpu_usage()
    assert cpu["cores"] >= 1

    mem = _get_memory_usage()
    assert mem["total_gb"] >= 0

    gpu = _get_gpu_usage()
    assert "available" in gpu

    disk = _get_disk_usage()
    assert disk["total_gb"] >= 0

    services = _get_service_status()
    assert "core" in services


@pytest.mark.anyio
async def test_generate_job_step_validations(tmp_path, monkeypatch):
    """Verify validation logic in generate-step API."""
    from fastapi import BackgroundTasks
    from models.job import Job, JobStatus
    from hub.workspace import WorkspaceManager

    from unittest.mock import MagicMock
    # Set up mock workspace manager
    dummy_wm = WorkspaceManager(base_dir=tmp_path)
    monkeypatch.setattr("portal.admin.workspace_manager", dummy_wm)
    monkeypatch.setattr("portal.admin._start_step_gen_worker", lambda: None)
    monkeypatch.setattr("portal.admin._step_gen_queue", MagicMock())

    # 1. Non-existent job -> 404
    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_404:
        await generate_job_step(
            job_id="non-existent-job",
            payload=GenerateStepRequest(step="minutes"),
            )
    assert exc_404.value.status_code == 404

    # Create dummy job without transcript
    job = Job(
        job_id="job_test_001",
        user_id="U_test",
        workspace_dir=tmp_path / "job_test_001",
        workflow=["transcript"],
        input_file=tmp_path / "job_test_001" / "input" / "audio.m4a"
    )
    job.workspace_dir.mkdir(parents=True, exist_ok=True)
    dummy_wm.save_job_json(job)

    # 2. Invalid step -> 400
    with pytest.raises(HTTPException) as exc_bad_step:
        await generate_job_step(
            job_id="job_test_001",
            payload=GenerateStepRequest(step="invalid_step"),
            )
    assert exc_bad_step.value.status_code == 400

    # 3. Missing transcript -> 400
    with pytest.raises(HTTPException) as exc_no_trans:
        await generate_job_step(
            job_id="job_test_001",
            payload=GenerateStepRequest(step="minutes"),
            )
    assert exc_no_trans.value.status_code == 400
    assert "transcript" in exc_no_trans.value.detail

    # Add mock transcript
    trans_dir = job.workspace_dir / "transcript"
    trans_dir.mkdir(parents=True, exist_ok=True)
    (trans_dir / "transcript.json").write_text("[]", encoding="utf-8")

    # 4. Success case -> status=started, current_step updated
    res = await generate_job_step(
        job_id="job_test_001",
        payload=GenerateStepRequest(step="minutes", template="auto"),
        )
    assert res["status"] == "queued"
    assert res["step"] == "minutes"

    # Reload job to check current_step
    reloaded_job = dummy_wm.get_job("job_test_001")
    assert reloaded_job.current_step in ("queued_minutes", "generating_minutes")

    # 5. Already running or generating -> 400
    with pytest.raises(HTTPException) as exc_running:
        await generate_job_step(
            job_id="job_test_001",
            payload=GenerateStepRequest(step="minutes"),
            )
    assert exc_running.value.status_code == 400

    # Reset current_step and simulate existing minutes
    reloaded_job.current_step = None
    min_dir = job.workspace_dir / "minutes"
    min_dir.mkdir(parents=True, exist_ok=True)
    (min_dir / "minutes.md").write_text("# Minutes", encoding="utf-8")
    dummy_wm.save_job_json(reloaded_job)

    # 6. Already generated minutes -> 400 (no duplicate overwrite)
    with pytest.raises(HTTPException) as exc_already_exists:
        await generate_job_step(
            job_id="job_test_001",
            payload=GenerateStepRequest(step="minutes"),
            )
    assert exc_already_exists.value.status_code == 400
    assert "議事録はすでに生成されています" in exc_already_exists.value.detail


@pytest.mark.anyio
async def test_execute_step_generation_flow(tmp_path, monkeypatch):
    """Verify _execute_step_generation successfully copies artifacts, updates workflow and index."""
    import subprocess
    from portal.admin import _execute_step_generation
    from hub.workspace import WorkspaceManager
    from models.job import Job
    import config

    # Mock Workspace & Share directories
    dummy_wm = WorkspaceManager(base_dir=tmp_path / "workspaces")
    dummy_share = tmp_path / "share"
    dummy_share.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("portal.admin.workspace_manager", dummy_wm)
    monkeypatch.setattr("portal.admin.config.DIR_SHARE", str(dummy_share))

    # Mock subprocess.run to simulate successful Minutes CLI execution
    job_id = "job_test_flow_001"
    ws_dir = dummy_wm.base_dir / job_id
    ws_dir.mkdir(parents=True, exist_ok=True)

    job = Job(
        job_id=job_id,
        user_id="U_flow",
        workspace_dir=ws_dir,
        workflow=["transcript", "summary"],
        input_file=ws_dir / "input" / "audio.m4a"
    )
    dummy_wm.save_job_json(job)

    def mock_subprocess_run(cmd, *args, **kwargs):
        # Create dummy minutes files
        min_dir = ws_dir / "minutes"
        min_dir.mkdir(parents=True, exist_ok=True)
        (min_dir / "minutes.md").write_text("# Test Minutes Content", encoding="utf-8")
        (min_dir / "minutes.txt").write_text("Test Minutes Plain", encoding="utf-8")
        (min_dir / "analysis.json").write_text("{}", encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", mock_subprocess_run)

    # Execute generation
    _execute_step_generation(job_id=job_id, step="minutes", template="auto")

    # Verify updated job
    updated_job = dummy_wm.get_job(job_id)
    assert "minutes" in updated_job.workflow
    assert updated_job.current_step is None
    assert any(a["name"] == "minutes.md" for a in updated_job.artifacts)
    assert any(h["step"] == "minutes" and h["status"] == "COMPLETED" for h in updated_job.step_history)

    # Verify files in DIR_SHARE
    published_md = dummy_share / f"{job_id}_minutes_minutes.md"
    published_txt = dummy_share / f"{job_id}_minutes_minutes.txt"
    assert published_md.exists()
    assert published_txt.exists()
    assert published_md.read_text(encoding="utf-8") == "# Test Minutes Content"
