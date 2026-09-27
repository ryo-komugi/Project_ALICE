"""
Test Admin Jobs Pagination and X-Total-Count header.
"""
import pytest
from pathlib import Path
from fastapi import Response

from portal.admin import list_jobs
import portal.admin as admin_module
from hub.workspace import WorkspaceManager
from models.job import Job, JobStatus


@pytest.mark.anyio
async def test_list_jobs_pagination_and_total_count(tmp_path, monkeypatch):
    ws_base = tmp_path / "workspaces"
    ws_base.mkdir()

    dummy_wm = WorkspaceManager(base_dir=ws_base)
    monkeypatch.setattr(admin_module, "workspace_manager", dummy_wm)

    for i in range(12):
        job_dir = ws_base / f"job_test_{i:03d}"
        job_dir.mkdir()
        job = Job(
            job_id=f"job_test_{i:03d}",
            user_id="user_pagination_test",
            status=JobStatus.COMPLETED,
            workflow=["transcript"],
            workspace_dir=job_dir,
            input_file=job_dir / "input" / f"audio_{i:03d}.mp3",
        )
        dummy_wm.save_job_json(job)

    # 1. Fetch first page (limit=5, offset=0)
    res_hdr1 = Response()
    jobs1 = await list_jobs(response=res_hdr1, offset=0, limit=5)
    assert res_hdr1.headers.get("X-Total-Count") == "12"
    assert len(jobs1) == 5

    # 2. Fetch second page (limit=5, offset=5)
    res_hdr2 = Response()
    jobs2 = await list_jobs(response=res_hdr2, offset=5, limit=5)
    assert res_hdr2.headers.get("X-Total-Count") == "12"
    assert len(jobs2) == 5
    # Ensure disjoint sets
    ids1 = {j["job_id"] for j in jobs1}
    ids2 = {j["job_id"] for j in jobs2}
    assert len(ids1.intersection(ids2)) == 0

    # 3. Fetch remaining page (limit=5, offset=10)
    res_hdr3 = Response()
    jobs3 = await list_jobs(response=res_hdr3, offset=10, limit=5)
    assert res_hdr3.headers.get("X-Total-Count") == "12"
    assert len(jobs3) == 2

    # 4. Out of bounds offset
    res_hdr4 = Response()
    jobs4 = await list_jobs(response=res_hdr4, offset=20, limit=5)
    assert res_hdr4.headers.get("X-Total-Count") == "12"
    assert len(jobs4) == 0
