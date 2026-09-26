"""
ALICE_Core Portal - Administrative Cockpit Router.
Coordinates sub-routers (jobs, logs, users, chat) and provides system controls, metrics, and cockpit UI.
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import config
from portal.auth import clear_session_cookie
from hub.container import core_worker, job_queue, workspace_manager
from core.system_settings import (
    get_system_settings,
    update_system_settings,
    is_maintenance_active,
    get_maintenance_message,
    is_admin_bypass_allowed,
)
from portal.telemetry import (
    _get_cpu_temp,
    _get_cpu_usage,
    _get_memory_usage,
    _get_gpu_usage,
    _get_disk_usage,
    _get_service_status,
)

# Sub-routers
from portal.chat_proxy import router as chat_router
from portal.admin_jobs import router as jobs_router
from portal.admin_logs import router as logs_router
from portal.admin_users import router as users_router

# Direct imports from admin_jobs for monkeypatch compatibility
import portal.admin_jobs as _jobs_mod
from portal.admin_jobs import (
    generate_job_step,
    GenerateStepRequest,
    list_jobs,
    delete_job_api,
    get_job_artifact,
    view_job_artifact,
    _execute_step_generation,
    _start_step_gen_worker,
    _extract_job_filename,
    _get_user_display_name,
)
_step_gen_queue = _jobs_mod._step_gen_queue

# Re-exports from admin_logs
from portal.admin_logs import (
    get_logs_catalog,
    get_system_logs,
    cleanup_logs_api,
)

# Re-exports from admin_users
from portal.admin_users import (
    list_users,
    update_user,
    delete_user,
)

logger = logging.getLogger("ALICE_Core.Admin")

router = APIRouter()

router.include_router(chat_router)
router.include_router(jobs_router)
router.include_router(logs_router)
router.include_router(users_router)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "admin"
SYSTEMCTL_BIN = shutil.which("systemctl") or "/usr/bin/systemctl"


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
        copilot_python = str(config.PROJECT_ROOT / "myenv" / "copilot_env" / "bin" / "python")
        copilot_main = str(config.PROJECT_ROOT / "ALICE_CoPilot" / "main.py")
        copilot_dir = str(config.PROJECT_ROOT / "ALICE_CoPilot")
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