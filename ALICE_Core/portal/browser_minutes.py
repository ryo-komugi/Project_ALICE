"""Anonymous, browser-session scoped APIs for Noel transcription and minutes jobs."""
import asyncio
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import shutil
import subprocess
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.datastructures import UploadFile

import config
from hub.container import core_worker, job_queue, job_service, workspace_manager

logger = logging.getLogger("ALICE_Core.Noel")
router = APIRouter(prefix="/noel/api", tags=["Noel"])
kureha_router = APIRouter(prefix="/kureha/api", tags=["Kureha"])

SECURE_COOKIE_NAME = "__Host-alice_browser_session"
HTTP_COOKIE_NAME = "alice_browser_session"
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_FORM_BYTES = 20 * 1024 * 1024
MAX_DURATION_SECONDS = 4 * 60 * 60
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
    client_ip = request.client.host if request.client else ""
    if _is_local_request(request) or config.is_http_allowed_ip(client_ip):
        return
    if not _https(request):
        raise HTTPException(status_code=400, detail="HTTPS is required")


def _cookie_name(request: Request) -> str:
    return SECURE_COOKIE_NAME if _https(request) else HTTP_COOKIE_NAME


def _session_id(request: Request, response: Response | None = None) -> str:
    cookie_name = _cookie_name(request)
    token = request.cookies.get(cookie_name, "")
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
            response.set_cookie(cookie_name, f"{nonce}.{signature}", secure=_https(request), httponly=True,
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
@kureha_router.get("/session")
async def create_browser_session(request: Request, response: Response):
    _require_https(request)
    uid = _session_id(request, response)
    _no_store(response)
    return {"user_id": uid, "authenticated": False}


@router.post("/minutes")
@kureha_router.post("/minutes")
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
    if not length or not length.isdigit() or int(length) > MAX_UPLOAD_BYTES + MAX_FORM_BYTES + 1024 * 1024:
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
    form_temp_path: Path | None = None
    form = None
    try:
        form = await request.form(max_files=2, max_fields=1, max_part_size=MAX_UPLOAD_BYTES)
        audio_uploads = form.getlist("audio")
        form_uploads = form.getlist("minutes_form")
        if (set(form.keys()) not in ({"audio"}, {"audio", "minutes_form"})
                or len(audio_uploads) != 1 or not isinstance(audio_uploads[0], UploadFile)
                or len(form_uploads) > 1):
            raise HTTPException(status_code=400, detail="Provide an audio file and optionally a DOCX form")
        if form_uploads and (result_type != "minutes" or not isinstance(form_uploads[0], UploadFile)):
            raise HTTPException(status_code=400, detail="DOCX forms are only accepted by the minutes endpoint")
        upload = audio_uploads[0]
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
                    raise HTTPException(status_code=413, detail="Upload exceeds 500 MiB")
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
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        has_unsupported_stream = any(stream.get("codec_type") not in {"audio", "data"} for stream in streams)
        if len(audio_streams) != 1 or has_unsupported_stream or not (fmt & expected_formats[suffix]):
            raise HTTPException(status_code=415, detail="File content does not match the selected audio format")
        if not (0 < duration <= MAX_DURATION_SECONDS):
            raise HTTPException(status_code=413, detail="Audio duration must be at most 4 hours")

        attachments = None
        if form_uploads:
            form_upload = form_uploads[0]
            form_suffix = Path(form_upload.filename or "").suffix.lower()
            if form_suffix != ".docx":
                raise HTTPException(status_code=415, detail="The minutes form must be a .docx file")
            form_temp_path = inbox / f"minutes_form_{secrets.token_hex(16)}.docx"
            form_size = 0
            with form_temp_path.open("xb") as out:
                while chunk := await form_upload.read(1024 * 1024):
                    form_size += len(chunk)
                    if form_size > MAX_FORM_BYTES:
                        raise HTTPException(status_code=413, detail="DOCX form exceeds 20 MiB")
                    out.write(chunk)
            await form_upload.close()
            if form_size == 0:
                raise HTTPException(status_code=400, detail="Empty DOCX form")
            try:
                with zipfile.ZipFile(form_temp_path) as archive:
                    members = archive.infolist()
                    names = {item.filename for item in members}
                    if ("[Content_Types].xml" not in names or "word/document.xml" not in names
                            or "word/vbaProject.bin" in names or len(members) > 2000
                            or sum(item.file_size for item in members) > 100 * 1024 * 1024):
                        raise ValueError("Unsupported DOCX structure")
                    if archive.testzip() is not None:
                        raise ValueError("Corrupt DOCX archive")
                    document_xml = ET.fromstring(archive.read("word/document.xml"))
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    paragraphs = ["".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
                                  for paragraph in document_xml.findall(".//w:p", ns)]
                    tags = {tag.strip() for paragraph in paragraphs
                            for tag in re.findall(r"\[([^\[\]\r\n]{1,40})\]", paragraph)}
                    if not tags:
                        raise ValueError("No bracket placeholders found")
                    if not (tags & {"本文", "議事録本文", "会議内容", "議事内容"}):
                        raise ValueError("No body placeholder found")
            except (OSError, zipfile.BadZipFile, ValueError):
                raise HTTPException(status_code=415, detail="Invalid DOCX form, or missing [本文] placeholder")
            attachments = {"minutes_form.docx": (form_temp_path, Path(form_upload.filename or "minutes_form.docx").name)}
        safe_name = f"recording_{secrets.token_hex(8)}{suffix}"
        job = await asyncio.to_thread(job_service.submit_job, uid, temp_path, workflow, safe_name, attachments)
        api_root = "/kureha/api" if request.url.path.startswith("/kureha/api/") else "/noel/api"
        status_url = f"{api_root}/jobs/{quote(job.job_id, safe='')}"
        result_url = f"{status_url}/{result_type}"
        _no_store(response)
        payload = {"job_id": job.job_id, "status_url": status_url, f"{result_type}_url": result_url}
        if attachments:
            payload["minutes_docx_url"] = f"{status_url}/minutes.docx"
        return JSONResponse(status_code=202, content=payload, headers={"Cache-Control": "no-store"})
    finally:
        if form is not None:
            await form.close()
        if temp_path:
            temp_path.unlink(missing_ok=True)
        if form_temp_path:
            form_temp_path.unlink(missing_ok=True)
        async with _quota_lock:
            _reservations[uid] = max(0, _reservations[uid] - 1)


def _owned_job(job_id: str, uid: str, request: Request | None = None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    job = workspace_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if request and _is_local_request(request):
        return job
    if not hmac.compare_digest(str(job.user_id), uid):
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _minutes_docx_filename(job) -> str:
    """Build a safe, stable download name from the title-tag value and job date."""
    title = ""
    analysis_path = job.workspace_dir / "minutes" / "analysis.json"
    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        overview = analysis.get("meeting_overview", {})
        if isinstance(overview, dict):
            title = str(overview.get("title") or "")
    except (OSError, ValueError, TypeError):
        pass

    # Remove path separators, control characters, and characters rejected by
    # common filesystems while retaining readable Unicode titles.
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]+', "_", title)
    title = re.sub(r"\s+", " ", title).strip(" ._")[:100].rstrip(" ._")
    if not title:
        title = "議事録"

    created_at = getattr(job, "completed_at", None) or getattr(job, "created_at", None)
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            created_at = None
    if not isinstance(created_at, datetime):
        created_at = datetime.now()
    return f"{title}_{created_at:%Y%m%d}.docx"


def _job_progress(job) -> dict[str, int | str]:
    """Build a whole-workflow progress estimate and expose its active step."""
    status = job.status.value if hasattr(job.status, "value") else str(job.status)
    if status == "COMPLETED":
        return {"stage": "完了", "percent": 100}
    if status == "FAILED":
        return {"stage": "処理に失敗しました", "percent": 0}

    workflow = list(job.workflow or [])
    if not workflow:
        return {"stage": "処理待ち", "percent": 0}
    current_step = job.current_step
    if not current_step:
        if status == "RUNNING":
            return {"stage": "処理を開始しています", "percent": 1}
        return {"stage": "処理待ち", "percent": 0}

    try:
        step_index = workflow.index(current_step)
    except ValueError:
        return {"stage": "処理中", "percent": 1}

    step_count = len(workflow)
    local_progress = 0.0
    stage = {"summary": "要約を作成中", "minutes": "議事録を作成中"}.get(
        current_step, f"{current_step}を処理中"
    )
    if current_step == "transcript":
        stage = "文字起こしを処理中（進捗は目安）"
        progress_found = False
        progress_path = (job.workspace_dir / "transcript" / "progress.json").resolve()
        try:
            if progress_path.is_relative_to(job.workspace_dir.resolve()) and progress_path.is_file():
                saved = json.loads(progress_path.read_text(encoding="utf-8"))
                saved_stage = saved.get("stage")
                saved_percent = saved.get("percent")
                if isinstance(saved_stage, str):
                    stage = saved_stage[:120]
                if isinstance(saved_percent, int):
                    local_progress = max(0.0, min(1.0, saved_percent / 100))
                    progress_found = True
        except (OSError, ValueError, TypeError):
            pass
        # Transcript reports fixed milestones during audio preparation and then
        # updates per Whisper segment. Estimate elapsed work as well so long
        # preparation phases do not leave the browser bar visually frozen.
        step_history = job.step_history or []
        entry = next((item for item in step_history if item.get("step") == current_step), {})
        started_at = entry.get("started_at")
        try:
            started = datetime.fromisoformat(started_at).timestamp() if isinstance(started_at, str) else time.time()
        except (ValueError, TypeError):
            started = time.time()
        elapsed = max(0.0, time.time() - started)
        estimated_progress = min(0.95, 1 - math.exp(-elapsed / 240.0))
        local_progress = max(local_progress, estimated_progress)
        if not progress_found:
            stage = "文字起こしを処理中（進捗を取得できないため目安表示）"
    else:
        # Summary and minutes CLIs do not currently report internal token-level progress.
        # Estimate a slowly advancing fraction from typical step durations, capped until
        # the worker confirms the step is complete.
        expected_seconds = {"summary": 120.0, "minutes": 90.0}.get(current_step, 120.0)
        step_history = job.step_history or []
        entry = next((item for item in step_history if item.get("step") == current_step), {})
        started_at = entry.get("started_at")
        try:
            started = datetime.fromisoformat(started_at).timestamp() if isinstance(started_at, str) else time.time()
        except (ValueError, TypeError):
            started = time.time()
        elapsed = max(0.0, time.time() - started)
        local_progress = min(0.95, 1 - math.exp(-elapsed / expected_seconds))

    overall = (step_index + local_progress) / step_count
    percent = max(0, min(99, int(overall * 100)))
    return {"stage": stage, "percent": percent}


@router.get("/jobs/{job_id}")
@kureha_router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request), request)
    progress = _job_progress(job)
    _no_store(response)
    return {"job_id": job.job_id, "status": job.status.value, "current_step": job.current_step,
            "progress": progress,
            "error_message": job.error_message if job.status.value == "FAILED" else None,
            "created_at": job.created_at.isoformat() if job.created_at else None}


@router.get("/jobs/{job_id}/minutes")
@kureha_router.get("/jobs/{job_id}/minutes")
async def get_minutes(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request), request)
    path = (job.workspace_dir / "minutes" / "minutes.md").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Minutes are not ready")
    _no_store(response)
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/minutes.docx")
@kureha_router.get("/jobs/{job_id}/minutes.docx")
async def get_minutes_docx(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request), request)
    if not (job.workspace_dir / "input" / "minutes_form.docx").is_file():
        raise HTTPException(status_code=404, detail="No DOCX form was uploaded for this job")
    path = (job.workspace_dir / "minutes" / "minutes.docx").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Completed DOCX minutes are not ready")
    _no_store(response)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename=_minutes_docx_filename(job), headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request), request)
    path = (job.workspace_dir / "transcript" / "transcript.txt").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Transcript is not ready")
    _no_store(response)
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/live-transcript")
async def get_live_transcript(job_id: str, request: Request, response: Response):
    _require_https(request)
    job = _owned_job(job_id, _session_id(request), request)
    path = (job.workspace_dir / "transcript" / "live_transcript.txt").resolve()
    if not path.is_relative_to(job.workspace_dir.resolve()):
        raise HTTPException(status_code=404, detail="Transcript not found")
    _no_store(response)
    if not path.is_file():
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return PlainTextResponse(path.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})
