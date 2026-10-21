"""Anonymous, browser-session scoped APIs for Noel transcription and minutes jobs."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import time
from collections import defaultdict, deque
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.datastructures import UploadFile

import config
from hub.container import core_worker, job_queue, job_service, workspace_manager

logger = logging.getLogger("ALICE_Core.Noel")
router = APIRouter(prefix="/noel/api", tags=["Noel"])

COOKIE_NAME = "__Host-alice_browser_session"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_DURATION_SECONDS = 2 * 60 * 60
MAX_GLOBAL_JOBS = 2
MAX_SESSION_JOBS = 1
RATE_LIMIT = 5
RATE_WINDOW_SECONDS = 15 * 60
_key = (getattr(config, "ADMIN_SECRET_KEY", "") or os.getenv("BROWSER_SESSION_SECRET", "")).encode()
if len(_key) < 32:
    logger.warning("Noel browser session signing key is not configured; using a process-local key")
    _key = secrets.token_bytes(32)
_quota_lock = asyncio.Lock()
_reservations: dict[str, int] = defaultdict(int)
_ip_uploads: dict[str, deque[float]] = defaultdict(deque)


def _https(request: Request) -> bool:
    return request.url.scheme == "https"


def _is_local_request(request: Request) -> bool:
    client_ip = request.client.host if request.client else ""
    return client_ip in ("127.0.0.1", "::1", "localhost")

def _require_https(request: Request) -> None:
    if _is_local_request(request):
        return
    if not _https(request):
        raise HTTPException(status_code=400, detail="HTTPS is required")


def _session_id(request: Request, response: Response | None = None) -> str:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        nonce, signature = token.split(".", 1)
        expected = hmac.new(_key, nonce.encode(), hashlib.sha256).hexdigest()
        valid = bool(re.fullmatch(r"[A-Za-z0-9_-]{40,64}", nonce)) and hmac.compare_digest(signature, expected)
    except ValueError:
        valid = False
        nonce = ""
    if not valid:
        nonce = secrets.token_urlsafe(32)
        signature = hmac.new(_key, nonce.encode(), hashlib.sha256).hexdigest()
        if response is not None:
            response.set_cookie(COOKIE_NAME, f"{nonce}.{signature}", secure=True, httponly=True,
                                samesite="strict", path="/")
    return "browser_" + hashlib.sha256(nonce.encode()).hexdigest()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"


def _browser_jobs():
    jobs = list(job_queue.get_queued_jobs())
    active = core_worker.current_job if core_worker else None
    if active and all(j.job_id != active.job_id for j in jobs):
        jobs.append(active)
    return [j for j in jobs if str(j.user_id).startswith("browser_")]


@router.get("/session")
async def create_browser_session(request: Request, response: Response):
    _require_https(request)
    uid = _session_id(request, response)
    _no_store(response)
    return {"user_id": uid, "authenticated": False}


@router.post("/minutes")
async def submit_minutes(request: Request, response: Response):
    return await _submit_audio_job(request, response, ["transcript", "summary", "minutes"], "minutes")


@router.post("/transcribe")
async def submit_transcription(request: Request, response: Response):
    return await _submit_audio_job(request, response, ["transcript"], "transcript")


async def _submit_audio_job(request: Request, response: Response, workflow: list[str], result_type: str):
    _require_https(request)
    origin = request.headers.get("origin")
    expected_origin = str(request.base_url).rstrip("/")
    if not origin or origin.rstrip("/") != expected_origin:
        raise HTTPException(status_code=403, detail="Origin check failed")
    length = request.headers.get("content-length")
    if not length or not length.isdigit() or int(length) > MAX_UPLOAD_BYTES + 1024 * 1024:
        raise HTTPException(status_code=413, detail="Upload is too large or missing Content-Length")
    uid = _session_id(request)
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    async with _quota_lock:
        entries = _ip_uploads[client_ip]
        while entries and entries[0] <= now - RATE_WINDOW_SECONDS:
            entries.popleft()
        if len(entries) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Upload rate limit exceeded")
        jobs = _browser_jobs()
        if sum(1 for j in jobs if j.user_id == uid) + _reservations[uid] >= MAX_SESSION_JOBS:
            raise HTTPException(status_code=429, detail="A job is already active for this browser session")
        if len(jobs) + sum(_reservations.values()) >= MAX_GLOBAL_JOBS:
            raise HTTPException(status_code=503, detail="Minutes service is busy")
        _reservations[uid] += 1
        entries.append(now)

    temp_path: Path | None = None
    try:
        form = await request.form(max_files=1, max_fields=1, max_part_size=MAX_UPLOAD_BYTES)
        if set(form.keys()) != {"audio"} or not isinstance(form.get("audio"), UploadFile):
            raise HTTPException(status_code=400, detail="Provide exactly one audio file in field 'audio'")
        upload = form["audio"]
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in {".mp3", ".m4a", ".wav"}:
            raise HTTPException(status_code=415, detail="Supported formats are MP3, M4A, and WAV")
        inbox = Path(config.DIR_INBOX)
        inbox.mkdir(parents=True, exist_ok=True)
        temp_path = inbox / f"noel_{secrets.token_hex(16)}{suffix}"
        total = 0
        with temp_path.open("xb") as out:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Upload exceeds 100 MiB")
                out.write(chunk)
        await upload.close()
        if total == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise HTTPException(status_code=503, detail="Audio validation is unavailable")
        try:
            probe = await asyncio.wait_for(asyncio.to_thread(subprocess.run,
                [ffprobe, "-v", "error", "-show_entries", "format=format_name,duration", "-show_entries", "stream=codec_type", "-of", "json", str(temp_path)],
                capture_output=True, text=True, timeout=20, check=True), timeout=22)
            metadata = json.loads(probe.stdout)
            fmt = set(metadata.get("format", {}).get("format_name", "").split(","))
            duration = float(metadata.get("format", {}).get("duration", 0))
            streams = metadata.get("streams", [])
        except Exception:
            raise HTTPException(status_code=415, detail="Invalid or unreadable audio file")
        expected_formats = {".mp3": {"mp3"}, ".m4a": {"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}, ".wav": {"wav"}}
        if len(streams) != 1 or streams[0].get("codec_type") != "audio" or not (fmt & expected_formats[suffix]):
            raise HTTPException(status_code=415, detail="File content does not match the selected audio format")
        if not (0 < duration <= MAX_DURATION_SECONDS):
            raise HTTPException(status_code=413, detail="Audio duration must be at most 2 hours")
        safe_name = f"recording_{secrets.token_hex(8)}{suffix}"
        job = await asyncio.to_thread(job_service.submit_job, uid, temp_path, workflow, safe_name)
        status_url = f"/noel/api/jobs/{quote(job.job_id, safe='')}"
        result_url = f"{status_url}/{result_type}"
        _no_store(response)
        return JSONResponse(status_code=202, content={"job_id": job.job_id, "status_url": status_url,
                              f"{result_type}_url": result_url}, headers={"Cache-Control": "no-store"})
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        async with _quota_lock:
            _reservations[uid] = max(0, _reservations[uid] - 1)


def _owned_job(job_id: str, uid: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    job = workspace_manager.get_job(job_id)
    if not job or not hmac.compare_digest(str(job.user_id), uid):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request))
    progress = {"stage": "処理待ち", "percent": 0}
    progress_path = (job.workspace_dir / "transcript" / "progress.json").resolve()
    if progress_path.is_relative_to(job.workspace_dir.resolve()) and progress_path.is_file():
        try:
            saved = json.loads(progress_path.read_text(encoding="utf-8"))
            stage = saved.get("stage")
            percent = saved.get("percent")
            if isinstance(stage, str) and isinstance(percent, int):
                progress = {"stage": stage[:120], "percent": max(0, min(100, percent))}
        except (OSError, ValueError, TypeError):
            pass
    elif job.status.value == "RUNNING":
        progress = {"stage": "処理を開始しています", "percent": 1}
    elif job.status.value == "COMPLETED":
        progress = {"stage": "完了", "percent": 100}
    _no_store(response)
    return {"job_id": job.job_id, "status": job.status.value, "current_step": job.current_step,
            "progress": progress,
            "error_message": job.error_message if job.status.value == "FAILED" else None,
            "created_at": job.created_at.isoformat() if job.created_at else None}


@router.get("/jobs/{job_id}/minutes")
async def get_minutes(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request))
    path = (job.workspace_dir / "minutes" / "minutes.md").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Minutes are not ready")
    _no_store(response)
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request))
    path = (job.workspace_dir / "transcript" / "transcript.txt").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Transcript is not ready")
    _no_store(response)
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/live-transcript")
async def get_live_transcript(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request))
    path = (job.workspace_dir / "transcript" / "live_transcript.txt").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()):
        raise HTTPException(status_code=404, detail="Transcript not found")
    _no_store(response)
    if not path.is_file():
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})
