import asyncio
import pytest
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from core.admin import (
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
from core.container import workspace_manager


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
