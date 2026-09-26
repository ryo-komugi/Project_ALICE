"""
ALICE_Core Portal - System Log Viewer Endpoints.
"""
import sys
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

import config
from hub.container import workspace_manager

logger = logging.getLogger("ALICE_Core.Admin.Logs")

router = APIRouter()

LOG_DIR = Path(config.DIR_RUNTIME) / "logs"

def _get_active_wm():
    adm = sys.modules.get("portal.admin")
    if adm and hasattr(adm, "workspace_manager"):
        return getattr(adm, "workspace_manager")
    return workspace_manager

@router.get("/api/logs/catalog")
async def get_logs_catalog():
    """種類（Core / Transcript / Summary / Minute）ごとに分類されたログ一覧カタログを返す"""
    archive_dir = LOG_DIR / "archive"

    # 1. Core ログ
    core_logs = []
    if (LOG_DIR / "alice.log").exists():
        stat = (LOG_DIR / "alice.log").stat()
        core_logs.append({
            "id": "alice.log",
            "name": f"alice.log (最新稼働 / {round(stat.st_size/1024, 1)} KB)",
            "size": stat.st_size,
            "type": "active",
        })
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("alice_*.log"), reverse=True):
            if f.is_file():
                stat = f.stat()
                core_logs.append({
                    "id": f.name,
                    "name": f"{f.name} ({round(stat.st_size/1024, 1)} KB)",
                    "size": stat.st_size,
                    "type": "archive",
                })

    # 2. Workspaces から各モジュールログ（transcript, summary, minutes）を収集
    transcript_logs = []
    summary_logs = []
    minutes_logs = []

    if _get_active_wm() and _get_active_wm().base_dir.exists():
        ws_dirs = [d for d in _get_active_wm().base_dir.iterdir() if d.is_dir() and (d / "job.json").exists()]
        ws_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

        for ws in ws_dirs:
            job_name = ws.name
            friendly_name = job_name
            try:
                job_data = json.loads((ws / "job.json").read_text(encoding="utf-8"))
                original_name = job_data.get("input_metadata", {}).get("original_name")
                created_date = job_data.get("created_at", "")[:10]
                if original_name:
                    friendly_name = f"[{created_date}] {original_name}"
            except Exception:
                pass

            # transcript
            t_log = ws / "logs" / "transcript.log"
            if t_log.exists() and t_log.is_file():
                transcript_logs.append({
                    "id": f"job:{ws.name}:transcript.log",
                    "name": f"{friendly_name} (transcript.log)",
                    "size": t_log.stat().st_size,
                    "type": "job",
                })

            # summary
            s_log = ws / "logs" / "summary.log"
            if s_log.exists() and s_log.is_file():
                summary_logs.append({
                    "id": f"job:{ws.name}:summary.log",
                    "name": f"{friendly_name} (summary.log)",
                    "size": s_log.stat().st_size,
                    "type": "job",
                })

            # minutes
            m_log = ws / "logs" / "minutes.log"
            if m_log.exists() and m_log.is_file():
                minutes_logs.append({
                    "id": f"job:{ws.name}:minutes.log",
                    "name": f"{friendly_name} (minutes.log)",
                    "size": m_log.stat().st_size,
                    "type": "job",
                })

    # アーカイブ内の過去の transcript ログも追加
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("transcript_*.log"), reverse=True):
            if f.is_file():
                stat = f.stat()
                transcript_logs.append({
                    "id": f.name,
                    "name": f"{f.name} (過去アーカイブ / {round(stat.st_size/1024, 1)} KB)",
                    "size": stat.st_size,
                    "type": "archive",
                })

    return {
        "core": core_logs,
        "transcript": transcript_logs,
        "summary": summary_logs,
        "minutes": minutes_logs,
    }


@router.get("/api/logs")
async def get_system_logs(
    file: str = Query("alice.log"),
    tail: int = Query(300, ge=10, le=1000),
    level: str = Query("ALL"),
):
    """Fetch system logs or job module logs with filtering."""
    if ".." in file or "\\" in file:
        raise HTTPException(status_code=400, detail="Invalid log filename")

    file_label = file

    if file.startswith("job:"):
        parts = file.split(":")
        if len(parts) != 3 or not workspace_manager:
            raise HTTPException(status_code=400, detail="Invalid job log reference")
        _, job_id, mod_log = parts
        if ".." in job_id or "/" in job_id or ".." in mod_log or "/" in mod_log:
            raise HTTPException(status_code=400, detail="Invalid path in job log")
        log_path = _get_active_wm().base_dir / job_id / "logs" / mod_log
        file_label = f"{job_id}/{mod_log}"
    elif file == "alice.log":
        log_path = LOG_DIR / "alice.log"
    else:
        log_path = LOG_DIR / "archive" / file

    if not log_path.exists() or not log_path.is_file():
        return {
            "file": file,
            "file_label": file_label,
            "lines": [f"[Log file not found: {file_label}]"],
            "total_lines": 0,
        }

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        # Filtering by log level
        if level in ("ERROR", "WARN", "WARNING", "INFO"):
            filter_tag = f"[{level}"
            all_lines = [l for l in all_lines if filter_tag in l]

        selected_lines = all_lines[-tail:]
        archive_dir = LOG_DIR / "archive"
        archives = [p.name for p in sorted(archive_dir.glob("*.log"), reverse=True)] if archive_dir.exists() else []
        return {
            "file": file,
            "file_label": file_label,
            "lines": [l.rstrip() for l in selected_lines],
            "total_lines": len(all_lines),
            "archives": archives,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {e}")


@router.post("/api/logs/cleanup")
async def cleanup_logs_api(days: int = Query(14, ge=1, le=90)):
    """Clean up old archive logs and empty log files (default 14 days)."""
    try:
        from core.logger import cleanup_logs, ARCHIVE_DIR
        res = cleanup_logs(archive_dir=ARCHIVE_DIR, retention_days=days)
        return {
            "status": "ok",
            "retention_days": days,
            "deleted_count": res["deleted_count"],
            "freed_bytes": res["freed_bytes"],
            "remaining_count": res["remaining_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log cleanup failed: {e}")


# ==========================================
# WebUI Cockpit HTML (Responsive Glassmorphism)
# ==========================================
# ==========================================