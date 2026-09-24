"""
ALICE_Core Admin Cockpit Router.
Provides System Metrics (Btop style), Active Queue, Job History,
Artifact Explorer, and System Log Viewer.
"""
import asyncio
import hashlib
import html
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import markdown

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

import config
from core.admin_auth import clear_session_cookie
from core.container import core_worker, job_queue, workspace_manager
from models.job import JobStatus
from core.system_settings import (
    get_system_settings,
    update_system_settings,
    is_maintenance_active,
    get_maintenance_message,
    is_admin_bypass_allowed,
)

logger = logging.getLogger("ALICE_Core.Admin")

# Import telemetry helpers from portal.telemetry (and re-export for backward compatibility)
from portal.telemetry import (
    _get_cpu_temp,
    _get_cpu_usage,
    _get_memory_usage,
    _get_gpu_usage,
    _get_disk_usage,
    _get_service_status,
)

router = APIRouter()

from portal.chat_proxy import router as chat_router
router.include_router(chat_router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "admin"
LOG_DIR = Path(config.DIR_RUNTIME) / "logs"

# Ensure standard system binary paths are present in PATH for systemd environment
for _sys_p in ["/usr/bin", "/bin", "/usr/local/bin"]:
    if _sys_p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{_sys_p}"

NVIDIA_SMI_BIN = shutil.which("nvidia-smi") or "/usr/bin/nvidia-smi"
SYSTEMCTL_BIN = shutil.which("systemctl") or "/usr/bin/systemctl"


# ==========================================
# Metrics Helper Functions (Zero external dependencies)
# ==========================================
def _get_cpu_temp() -> float | None:
    """Read CPU package or thermal zone temperature in Celsius."""
    try:
        for tz in ["thermal_zone3", "thermal_zone1", "thermal_zone2", "thermal_zone0"]:
            p = Path(f"/sys/class/thermal/{tz}")
            if p.exists():
                type_file = p / "type"
                temp_file = p / "temp"
                if type_file.exists() and temp_file.exists():
                    t_type = type_file.read_text().strip().lower()
                    if any(k in t_type for k in ["x86_pkg", "tcpu", "core", "package", "cpu"]):
                        raw = float(temp_file.read_text().strip())
                        return round(raw / 1000.0, 1) if raw > 1000 else round(raw, 1)
    except Exception:
        pass

    try:
        import glob
        for h in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            name_p = Path(h) / "name"
            if name_p.exists() and "coretemp" in name_p.read_text().lower():
                temp_p = Path(h) / "temp1_input"
                if temp_p.exists():
                    raw = float(temp_p.read_text().strip())
                    return round(raw / 1000.0, 1) if raw > 1000 else round(raw, 1)
    except Exception:
        pass
    return None


def _get_cpu_usage() -> dict[str, Any]:
    """Read CPU usage, core count, and package temperature."""
    cores = os.cpu_count() or 1
    cpu_percent = 0.0
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        fields = [float(x) for x in line.split()[1:]]
        idle_time = fields[3] + fields[4]
        total_time = sum(fields)
        with open("/proc/loadavg", "r") as f:
            load_1m = float(f.read().split()[0])
        cpu_percent = min(100.0, round((load_1m / cores) * 100, 1))
    except Exception as e:
        logger.debug(f"[Admin] Failed to read CPU: {e}")

    return {
        "cores": cores,
        "percent": cpu_percent,
        "temp": _get_cpu_temp(),
    }


def _get_memory_usage() -> dict[str, Any]:
    """Read RAM usage from /proc/meminfo."""
    total_kb = 0
    available_kb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    available_kb = int(line.split()[1])
    except Exception as e:
        logger.debug(f"[Admin] Failed to read Mem: {e}")

    used_kb = max(0, total_kb - available_kb)
    percent = round((used_kb / total_kb * 100), 1) if total_kb > 0 else 0.0

    return {
        "total_gb": round(total_kb / (1024 * 1024), 2),
        "used_gb": round(used_kb / (1024 * 1024), 2),
        "percent": percent,
    }


_last_gpu_usage: dict[str, Any] | None = None
_last_gpu_time: float = 0.0


def _get_gpu_usage() -> dict[str, Any]:
    """Query NVIDIA GPU, VRAM usage, core utilization, and temperature via nvidia-smi with 1.0s caching."""
    global _last_gpu_usage, _last_gpu_time
    now = time.time()
    if _last_gpu_usage is not None and (now - _last_gpu_time) < 1.0:
        return _last_gpu_usage

    try:
        cmd = [
            NVIDIA_SMI_BIN,
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, timeout=2.0).decode("utf-8").strip()
        parts = [p.strip() for p in out.split(",")]
        name = parts[0]
        total_mb = float(parts[1])
        used_mb = float(parts[2])
        gpu_util = float(parts[3])
        gpu_temp = float(parts[4]) if len(parts) > 4 else None
        vram_percent = round((used_mb / total_mb) * 100, 1) if total_mb > 0 else 0.0

        res = {
            "available": True,
            "name": name,
            "total_mb": int(total_mb),
            "used_mb": int(used_mb),
            "total_gb": round(total_mb / 1024, 2),
            "used_gb": round(used_mb / 1024, 2),
            "vram_percent": vram_percent,
            "gpu_util_percent": gpu_util,
            "temp": gpu_temp,
        }
        _last_gpu_usage = res
        _last_gpu_time = now
        return res
    except Exception:
        fallback = {
            "available": False,
            "name": "N/A",
            "total_gb": 0,
            "used_gb": 0,
            "vram_percent": 0.0,
            "gpu_util_percent": 0.0,
            "temp": None,
        }
        _last_gpu_usage = fallback
        _last_gpu_time = now
        return fallback


def _get_disk_usage() -> dict[str, Any]:
    """Get disk usage of /data and root / runtimes."""
    drives = []
    # 1. System Root (/)
    try:
        u_root = shutil.disk_usage("/")
        root_tot = round(u_root.total / (1024**3), 2)
        root_used = round(u_root.used / (1024**3), 2)
        root_pct = round((u_root.used / u_root.total) * 100, 1)
        drives.append({
            "mount": "/",
            "name": "System (/)",
            "total_gb": root_tot,
            "used_gb": root_used,
            "percent": root_pct,
        })
    except Exception:
        pass

    # 2. Workspaces (/data)
    data_stat = {"total_gb": 0, "used_gb": 0, "percent": 0.0}
    try:
        u_data = shutil.disk_usage("/data")
        data_tot = round(u_data.total / (1024**3), 2)
        data_used = round(u_data.used / (1024**3), 2)
        data_pct = round((u_data.used / u_data.total) * 100, 1)
        data_stat = {"total_gb": data_tot, "used_gb": data_used, "percent": data_pct}
        drives.append({
            "mount": "/data",
            "name": "Workspaces (/data)",
            "total_gb": data_tot,
            "used_gb": data_used,
            "percent": data_pct,
        })
    except Exception:
        pass

    return {
        "total_gb": data_stat["total_gb"],
        "used_gb": data_stat["used_gb"],
        "percent": data_stat["percent"],
        "drives": drives,
    }


def _get_service_status() -> dict[str, str]:
    """Check systemd service active status with process fallback."""
    services = {
        "core": "alice-core.service",
        "copilot": "alice-copilot.service",
        "ollama": "ollama.service",
    }
    result = {}
    for key, svc in services.items():
        try:
            cmd = [SYSTEMCTL_BIN, "is-active", svc]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            status_text = (res.stdout or res.stderr or "").strip().lower()
            if status_text in ("active", "activating", "reloading"):
                result[key] = "active"
            elif status_text in ("inactive", "deactivating"):
                result[key] = "inactive"
            elif status_text in ("failed",):
                result[key] = "failed"
            else:
                result[key] = status_text or "unknown"
        except Exception:
            result[key] = "unknown"

    # CoPilot 手動稼働プロセス（ALICE_CoPilot/main.py）のフォールバック検知
    if result.get("copilot") != "active":
        try:
            p_check = subprocess.run(["pgrep", "-f", "ALICE_CoPilot/main.py"], capture_output=True, text=True, timeout=1.0)
            if p_check.returncode == 0 and p_check.stdout.strip():
                result["copilot"] = "active"
        except Exception:
            pass

    # LINE Gateway status (Active when Core is active)
    result["line"] = "active" if result.get("core") == "active" else "inactive"

    return result


def _get_user_display_name(user_id: str) -> str:
    """Resolve user_id to display_name from users.db. If not found, return user_id as is."""
    if not user_id:
        return ""
    try:
        from repository.user_repository import UserRepository
        repo = UserRepository()
        u = repo.find(user_id)
        if u and u.display_name:
            return u.display_name
    except Exception:
        pass
    return user_id


def _extract_job_filename(job: Any) -> str:
    """Extract original filename or input file name from job."""
    if not job:
        return "N/A"
    if hasattr(job, "input_metadata") and isinstance(job.input_metadata, dict):
        if job.input_metadata.get("original_name"):
            return str(job.input_metadata["original_name"])
    if hasattr(job, "input_file") and job.input_file:
        return Path(job.input_file).name
    return getattr(job, "original_filename", "") or job.job_id


# ==========================================
# API Endpoints
# ==========================================
@router.get("/api/metrics")
async def get_metrics():
    """Btop-style live telemetry and active queue."""
    current_job = core_worker.current_job if core_worker else None
    queued_jobs = job_queue.get_queued_jobs() if job_queue else []

    active_job_data = None
    if current_job:
        active_job_data = {
            "job_id": current_job.job_id,
            "user_id": current_job.user_id,
            "user_name": _get_user_display_name(current_job.user_id),
            "filename": _extract_job_filename(current_job),
            "current_step": current_job.current_step,
            "workflow": current_job.workflow,
            "created_at": current_job.created_at.isoformat() if current_job.created_at else None,
        }

    queue_list = []
    for j in queued_jobs:
        queue_list.append({
            "job_id": j.job_id,
            "user_id": j.user_id,
            "user_name": _get_user_display_name(j.user_id),
            "filename": _extract_job_filename(j),
            "workflow": j.workflow,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        })

    gpu_data = await asyncio.to_thread(_get_gpu_usage)

    return {
        "timestamp": datetime.now().isoformat(),
        "cpu": _get_cpu_usage(),
        "memory": _get_memory_usage(),
        "gpu": gpu_data,
        "disk": _get_disk_usage(),
        "services": _get_service_status(),
        "active_job": active_job_data,
        "queue_size": len(queue_list),
        "queued_jobs": queue_list,
        "maintenance": {
            "active": is_maintenance_active(),
            "message": get_maintenance_message(),
            "admin_bypass": is_admin_bypass_allowed(),
        },
    }


@router.get("/api/maintenance")
async def get_maintenance_api():
    """Get current system maintenance settings."""
    return get_system_settings()


@router.post("/api/maintenance")
async def update_maintenance_api(request: Request):
    """Update system maintenance settings."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    m_mode = bool(body.get("maintenance_mode", False))
    m_msg = body.get("maintenance_message", "")
    admin_bypass = bool(body.get("admin_bypass", True))

    updated = update_system_settings({
        "maintenance_mode": m_mode,
        "maintenance_message": m_msg,
        "admin_bypass": admin_bypass,
        "updated_at": datetime.now().isoformat(),
        "updated_by": "admin",
    })
    logger.info(f"[Admin] Maintenance mode updated: active={m_mode}, bypass={admin_bypass}")
    return {"status": "ok", "settings": updated}


@router.post("/api/services/{service_name}/restart")
async def restart_service_api(service_name: str):
    """Restart a system daemon (core, copilot, ollama, line)."""
    svc = service_name.lower().strip()
    if svc not in ("core", "copilot", "ollama", "line"):
        raise HTTPException(status_code=400, detail="Invalid service name. Must be core, copilot, ollama, or line")

    if svc in ("core", "line"):
        def _deferred_restart():
            import time
            time.sleep(1.0)
            logger.info("[Admin] Core restart initiated via API, terminating process for systemd respawn...")
            os._exit(0)

        import threading
        threading.Thread(target=_deferred_restart, daemon=True).start()
        return {"status": "restarting", "service": "core", "message": "Coreサービスの再起動を開始しました。約5秒後に自動復帰します。"}

    elif svc == "copilot":
        try:
            res = subprocess.run(["sudo", "-n", SYSTEMCTL_BIN, "restart", "alice-copilot.service"], capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0:
                return {"status": "restarted", "service": "copilot", "message": "CoPilotサービスをsystemctl経由で再起動しました。"}
        except Exception:
            pass

        # Fallback: kill user processes and respawn
        try:
            subprocess.run(["pkill", "-9", "-f", "ALICE_CoPilot/main.py"], capture_output=True, timeout=2.0)
        except Exception:
            pass

        import time
        time.sleep(1.0)
        copilot_python = "/home/takuya/Project_ALICE/myenv/copilot_env/bin/python"
        copilot_main = "/home/takuya/Project_ALICE/ALICE_CoPilot/main.py"
        copilot_dir = "/home/takuya/Project_ALICE/ALICE_CoPilot"
        try:
            log_out = open("/data/runtime/logs/copilot.log", "a", encoding="utf-8")
        except Exception:
            log_out = subprocess.DEVNULL
        subprocess.Popen(
            [copilot_python, copilot_main],
            cwd=copilot_dir,
            stdout=log_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        return {"status": "restarted", "service": "copilot", "message": "CoPilotプロセスを再起動しました。"}

    elif svc == "ollama":
        try:
            res = subprocess.run([SYSTEMCTL_BIN, "--no-ask-password", "restart", "ollama.service"], capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0:
                return {"status": "restarted", "service": "ollama", "message": "Ollamaサービスを再起動しました。"}
        except Exception:
            pass

        # Fallback: Unload models via Ollama API to free VRAM
        try:
            import urllib.request
            import json as json_mod
            req = urllib.request.Request("http://localhost:11434/api/ps")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                ps_data = json_mod.loads(resp.read().decode("utf-8"))
            unloaded = []
            for m in ps_data.get("models", []):
                m_name = m.get("name")
                if m_name:
                    post_data = json_mod.dumps({"model": m_name, "keep_alive": 0}).encode("utf-8")
                    gen_req = urllib.request.Request("http://localhost:11434/api/generate", data=post_data, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(gen_req, timeout=3.0) as r:
                        pass
                    unloaded.append(m_name)
            return {"status": "cleared", "service": "ollama", "message": f"Ollama VRAMメモリを解放しました ({', '.join(unloaded) if unloaded else 'ロード中モデルなし'})。"}
        except Exception as e:
            return {"status": "warning", "service": "ollama", "message": f"Ollamaメモリリフレッシュ: {e}"}


@router.get("/api/system/check-ip")
async def check_system_ip_api(force_alert: bool = Query(False)):
    """Check current external global IP, compare with cached baseline, and optionally force Discord alert."""
    try:
        from core.ip_monitor import check_and_notify_ip_change
        result = check_and_notify_ip_change(force_alert=force_alert)
        return result
    except Exception as e:
        logger.error(f"[Admin] Failed to check system IP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/jobs")
async def list_jobs(limit: int = Query(50, ge=1, le=200)):
    """List recent workspaces with artifact & log metadata."""
    if not workspace_manager or not workspace_manager.base_dir.exists():
        return []

    jobs_list = []
    dirs = [d for d in workspace_manager.base_dir.iterdir() if d.is_dir() and (d / "job.json").exists()]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    for ws_dir in dirs[:limit]:
        try:
            job = workspace_manager.load_job(ws_dir)
            
            # Detect available artifacts
            artifacts = []
            for art_name in ["transcript.txt", "transcript.json", "summary.txt", "summary.md", "commentary.txt", "commentary.md", "minutes.txt", "minutes.md"]:
                for sub in ["transcript", "summary", "minutes"]:
                    p = ws_dir / sub / art_name
                    if p.exists():
                        artifacts.append({
                            "name": art_name,
                            "module": sub,
                            "size": p.stat().st_size,
                            "rel_path": f"{sub}/{art_name}",
                        })
                        break

            # Detect available logs
            logs = []
            logs_dir = ws_dir / "logs"
            if logs_dir.exists():
                for log_file in logs_dir.iterdir():
                    if log_file.is_file() and log_file.name.endswith(".log"):
                        logs.append({
                            "name": log_file.name,
                            "size": log_file.stat().st_size,
                            "rel_path": f"logs/{log_file.name}",
                        })

            jobs_list.append({
                "job_id": job.job_id,
                "user_id": job.user_id,
                "user_name": _get_user_display_name(job.user_id),
                "status": job.status.value,
                "workflow": job.workflow,
                "filename": _extract_job_filename(job),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "current_step": job.current_step,
                "error_message": job.error_message,
                "artifacts": artifacts,
                "logs": logs,
            })
        except Exception as e:
            logger.debug(f"[Admin] Skipping job load error in {ws_dir}: {e}")

    return jobs_list


@router.delete("/api/jobs/{job_id}")
async def delete_job_api(job_id: str):
    """Safely delete a job workspace and reindex ALICE_Search."""
    if not workspace_manager:
        raise HTTPException(status_code=500, detail="WorkspaceManager unavailable")
    success = workspace_manager.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to delete job {job_id}")
    return {"status": "ok", "deleted_job_id": job_id}


@router.get("/api/jobs/{job_id}/artifact")
async def get_job_artifact(job_id: str, path: str = Query(..., description="Relative path within workspace")):
    """Safely fetch text content of a workspace artifact or log."""
    # Prevent directory traversal
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path parameter")

    ws_dir = workspace_manager.base_dir / job_id
    if not ws_dir.exists():
        raise HTTPException(status_code=404, detail="Job workspace not found")

    target_file = (ws_dir / path).resolve()
    # Path traversal validation
    if not str(target_file).startswith(str(ws_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="Artifact file not found")

    try:
        content = target_file.read_text(encoding="utf-8", errors="replace")
        return {
            "job_id": job_id,
            "path": path,
            "filename": target_file.name,
            "size": target_file.stat().st_size,
            "content": content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")


@router.get("/jobs/{job_id}/view", response_class=HTMLResponse)
async def view_job_artifact(job_id: str, path: str = Query(..., description="Relative path in workspace")):
    """Render a clean standalone web view for any workspace artifact or log."""
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path parameter")

    ws_dir = workspace_manager.base_dir / job_id
    if not ws_dir.exists():
        raise HTTPException(status_code=404, detail="Job workspace not found")

    target_file = (ws_dir / path).resolve()
    if not str(target_file).startswith(str(ws_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        raw_content = target_file.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    # Render Markdown if .md, else escape plain text in pre
    if target_file.suffix.lower() == ".md":
        rendered_body = markdown.markdown(
            raw_content,
            extensions=["extra", "nl2br", "sane_lists"]
        )
    else:
        escaped_text = html.escape(raw_content)
        rendered_body = f"<pre class='whitespace-pre-wrap font-mono text-sm leading-relaxed'>{escaped_text}</pre>"

    job = workspace_manager.get_job(job_id)
    original_title = _extract_job_filename(job) if job else job_id

    html_content = f"""<!DOCTYPE html>
<html lang="ja" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>{html.escape(original_title)} | {html.escape(target_file.name)}</title>
  <link rel="icon" type="image/jpeg" href="/static/admin/alice_logo.jpg">
  <link rel="apple-touch-icon" href="/static/admin/alice_logo.jpg">
  <meta name="theme-color" content="#060913">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    body {{
      background-color: #060913;
      color: #e2e8f0;
      font-family: 'BIZ UDPGothic', sans-serif;
    }}
    .glass-card {{
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
  </style>
</head>
<body class="min-h-screen p-4 sm:p-8 flex flex-col items-center">
  <div class="max-w-4xl w-full space-y-6">
    <!-- Header -->
    <header class="glass-card p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xl">
      <div>
        <div class="flex items-center gap-2 mb-1">
          <span class="text-xs font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800 font-semibold">{html.escape(path)}</span>
          <span class="text-xs font-mono text-slate-400">{html.escape(job_id)}</span>
        </div>
        <h1 class="text-lg sm:text-xl font-bold text-white tracking-wide">{html.escape(original_title)}</h1>
      </div>
      <div class="flex items-center gap-2.5 self-end sm:self-center">
        <button onclick="copyContent()" id="copy-btn" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-sky-300 text-xs font-mono border border-slate-700 transition-colors flex items-center gap-1.5">
          <span>📋</span> コピー
        </button>
        <button onclick="window.close()" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono border border-slate-700 transition-colors">
          閉じる
        </button>
      </div>
    </header>

    <!-- Document Content -->
    <main class="glass-card p-6 sm:p-8 rounded-2xl shadow-2xl overflow-x-auto leading-relaxed text-sm text-slate-200" id="doc-content">
      {rendered_body}
    </main>
  </div>

  <div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 bg-sky-600 text-white text-xs font-mono px-4 py-2 rounded-full shadow-lg opacity-0 transition-opacity duration-300 pointer-events-none">
    クリップボードにコピーしました
  </div>

  <script>
    function copyContent() {{
      const text = document.getElementById('doc-content').innerText;
      navigator.clipboard.writeText(text).then(() => {{
        const toast = document.getElementById('toast');
        toast.classList.remove('opacity-0');
        setTimeout(() => toast.classList.add('opacity-0'), 2000);
      }});
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)


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

    if workspace_manager and workspace_manager.base_dir.exists():
        ws_dirs = [d for d in workspace_manager.base_dir.iterdir() if d.is_dir() and (d / "job.json").exists()]
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
        log_path = workspace_manager.base_dir / job_id / "logs" / mod_log
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
# User Directory API Endpoints (users.db)
# ==========================================
@router.get("/api/users")
async def list_users():
    """List all registered users from users.db."""
    try:
        from repository.user_repository import UserRepository
        repo = UserRepository()
        users = repo.get_all()
        return [
            {
                "user_id": u.user_id,
                "display_name": u.display_name,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status)
            }
            for u in users
        ]
    except Exception as e:
        logger.error(f"[Admin] Failed to list users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/users/{user_id}")
async def update_user(user_id: str, data: dict):
    """Update user's display_name and status, sync LINE rich menu."""
    display_name = data.get("display_name", "").strip()
    status_str = data.get("status", "").strip()
    if not display_name or not status_str:
        raise HTTPException(status_code=400, detail="display_name and status are required")

    from auth.user_status import UserStatus
    from repository.user_repository import UserRepository
    from line.richmenu.richmane import RichMenu

    try:
        status_enum = UserStatus(status_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_str}")

    try:
        repo = UserRepository()
        repo.update(user_id, display_name, status_enum)

        # Sync Rich Menu based on new status
        rm = RichMenu()
        if status_enum == UserStatus.REJECTED:
            rm.unlink(user_id)
        elif status_enum == UserStatus.READY:
            rm.switch(user_id, "UserMenu")

        return {"status": "ok", "user_id": user_id, "display_name": display_name, "user_status": status_str}
    except Exception as e:
        logger.error(f"[Admin] Failed to update user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/users/{user_id}")
async def delete_user(user_id: str):
    """Delete user from users.db and unlink rich menu."""
    from repository.user_repository import UserRepository
    from line.richmenu.richmane import RichMenu

    try:
        rm = RichMenu()
        rm.unlink(user_id)
        repo = UserRepository()
        repo.delete(user_id)
        return {"status": "deleted", "user_id": user_id}
    except Exception as e:
        logger.error(f"[Admin] Failed to delete user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# Authentication Endpoints (Logout)
# ==========================================
@router.post("/logout")
@router.get("/logout")
async def logout(request: Request):
    """Clear admin session cookie and redirect to Cloudflare Access logout."""
    response = RedirectResponse(url="/cdn-cgi/access/logout", status_code=303)
    clear_session_cookie(response)
    logger.info("[Admin] Admin session cleared.")
    return response
# ==========================================
# Service Worker & PWA Endpoints
# ==========================================
@router.get("/sw.js", include_in_schema=False)
async def get_service_worker():
    """Serve service worker with Service-Worker-Allowed scope."""
    sw_file = STATIC_DIR / "sw.js"
    if not sw_file.exists():
        raise HTTPException(status_code=404, detail="Service worker not found")
    return FileResponse(
        sw_file,
        media_type="application/javascript",
        headers={
            "Service-Worker-Allowed": "/admin",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/api/client-error", include_in_schema=False)
async def report_client_error(request: Request):
    """Receive and log frontend JavaScript errors from client browsers."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    logger.error(f"[CLIENT_JS_ERROR] {body}")
    return {"status": "logged"}


DASHBOARD_TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "admin_dashboard.html"
if not DASHBOARD_TEMPLATE_PATH.exists():
    DASHBOARD_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "core" / "templates" / "admin_dashboard.html"
_DASHBOARD_HTML_CACHE: str | None = None


def get_dashboard_html() -> str:
    """Read and cache admin cockpit HTML template."""
    global _DASHBOARD_HTML_CACHE
    if _DASHBOARD_HTML_CACHE is None:
        if not DASHBOARD_TEMPLATE_PATH.exists():
            raise FileNotFoundError(f"Admin dashboard template not found at {DASHBOARD_TEMPLATE_PATH}")
        _DASHBOARD_HTML_CACHE = DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8")
    return _DASHBOARD_HTML_CACHE


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.head("", include_in_schema=False)
@router.head("/", include_in_schema=False)
async def get_admin_dashboard():
    """Render full Cyber-Wonderland Cockpit HTML."""
    return HTMLResponse(
        content=get_dashboard_html(),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
