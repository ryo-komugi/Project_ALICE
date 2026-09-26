"""
ALICE_Core Portal - Job Management & Step Generation Router.
"""
import sys
import html
import json
import logging
import markdown
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from models.job import Job, JobStatus
from hub.container import core_worker, job_queue, workspace_manager

logger = logging.getLogger("ALICE_Core.Admin.Jobs")

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static" / "admin"

def _get_active_wm():
    adm = sys.modules.get("portal.admin")
    if adm and hasattr(adm, "workspace_manager"):
        return getattr(adm, "workspace_manager")
    return workspace_manager

def _get_active_share_dir():
    adm = sys.modules.get("portal.admin")
    if adm and hasattr(adm, "config") and hasattr(adm.config, "DIR_SHARE"):
        return Path(adm.config.DIR_SHARE)
    return Path(getattr(config, "DIR_SHARE", "/data/share"))

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


@router.get("/api/jobs")
async def list_jobs(limit: int = Query(50, ge=1, le=200)):
    """List recent workspaces with artifact & log metadata."""
    if not _get_active_wm() or not _get_active_wm().base_dir.exists():
        return []

    jobs_list = []
    dirs = [d for d in _get_active_wm().base_dir.iterdir() if d.is_dir() and (d / "job.json").exists()]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    for ws_dir in dirs[:limit]:
        try:
            job = _get_active_wm().load_job(ws_dir)
            
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
    if not _get_active_wm():
        raise HTTPException(status_code=500, detail="WorkspaceManager unavailable")
    success = _get_active_wm().delete_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to delete job {job_id}")
    return {"status": "ok", "deleted_job_id": job_id}


class GenerateStepRequest(BaseModel):
    step: str
    template: str | None = "auto"




# =========================================================================
# Background Step Generation Serial Queue & Worker
# =========================================================================
_step_gen_queue: queue.Queue = queue.Queue()
_step_gen_worker_thread: threading.Thread | None = None


def _step_gen_worker_loop() -> None:
    while True:
        try:
            item = _step_gen_queue.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            job_id, step, template = item
            _execute_step_generation(job_id=job_id, step=step, template=template)
        except Exception as e:
            logger.exception(f"[Admin] Error in step generation worker: {e}")
        finally:
            _step_gen_queue.task_done()


def _start_step_gen_worker() -> None:
    global _step_gen_worker_thread
    if _step_gen_worker_thread is None or not _step_gen_worker_thread.is_alive():
        _step_gen_worker_thread = threading.Thread(target=_step_gen_worker_loop, daemon=True)
        _step_gen_worker_thread.start()
        logger.info("[Admin] Step generation serial worker started.")


_start_step_gen_worker()

def _collect_and_publish_artifacts(job, module_name: str, ws_dir: Path, share_dir: Path) -> list[dict]:
    target_dir = ws_dir / module_name
    new_artifacts = []
    if target_dir.exists():
        for f in target_dir.iterdir():
            if f.is_file() and not f.name.startswith("."):
                rel_p = f"{module_name}/{f.name}"
                if not any(a.get("path") == rel_p for a in (job.artifacts or [])):
                    is_pri = (f.name == f"{module_name}.md" or f.name == f"{module_name}.txt")
                    art_entry = {
                        "name": f.name,
                        "path": rel_p,
                        "module": module_name,
                        "is_primary": is_pri,
                        "size_bytes": f.stat().st_size,
                        "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    }
                    new_artifacts.append(art_entry)

    if job.artifacts is None:
        job.artifacts = []
    job.artifacts.extend(new_artifacts)

    # DIR_SHARE へコピー (LINE通知は送らない)
    if module_name == "minutes":
        for ext in [".md", ".txt"]:
            src = ws_dir / "minutes" / f"minutes{ext}"
            if src.exists():
                pub_name = f"{job.job_id}_minutes_minutes{ext}"
                try:
                    shutil.copy2(src, ws_dir / "minutes" / pub_name)
                    shutil.copy2(src, share_dir / pub_name)
                except Exception as err:
                    logger.warning(f"[Admin] Failed to copy {pub_name} to share: {err}")
    elif module_name == "summary":
        for base in ["summary", "commentary"]:
            for ext in [".md", ".txt"]:
                src = ws_dir / "summary" / f"{base}{ext}"
                if src.exists():
                    pub_name = f"{job.job_id}_summary_{base}{ext}"
                    try:
                        shutil.copy2(src, ws_dir / "summary" / pub_name)
                        shutil.copy2(src, share_dir / pub_name)
                    except Exception as err:
                        logger.warning(f"[Admin] Failed to copy {pub_name} to share: {err}")
    return new_artifacts


def _execute_step_generation(job_id: str, step: str, template: str = "auto") -> None:
    logger.info(f"[Admin] Starting background generation for job={job_id}, step={step}, template={template}")
    job = _get_active_wm().get_job(job_id)
    if not job:
        logger.error(f"[Admin] Job {job_id} not found for generation")
        return

    ws_dir = job.workspace_dir
    logs_dir = ws_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    python_bin = config.PROJECT_ROOT / "myenv" / "core_env" / "bin" / "python"
    share_dir = Path(config.DIR_SHARE)
    share_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(config.PROJECT_ROOT)

    try:
        # =========================================================================
        # 1. 議事録要求時、先行する要約(summary)が無ければまず要約を自動生成する
        # =========================================================================
        if step == "minutes" and not (ws_dir / "summary" / "summary.md").exists():
            logger.info(f"[Admin] Job {job_id} has no summary. Executing ALICE_Summary first...")
            job.status = JobStatus.RUNNING
            job.current_step = "generating_summary"
            _get_active_wm().save_job_json(job)

            sum_cli = config.PROJECT_ROOT / "ALICE_Summary" / "cli.py"
            sum_cwd = config.PROJECT_ROOT / "ALICE_Summary"
            sum_log = logs_dir / "summary_add.log"
            sum_cmd = [str(python_bin), str(sum_cli), "--workspace", str(ws_dir), "--type", "auto"]
            sum_start = time.time()

            with open(sum_log, "w", encoding="utf-8") as lf:
                res_sum = subprocess.run(
                    sum_cmd, cwd=str(sum_cwd), env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=600, check=False
                )
            sum_elapsed = round(time.time() - sum_start, 2)

            job = _get_active_wm().get_job(job_id)
            if not job or res_sum.returncode != 0:
                logger.error(f"[Admin] Prior summary generation failed (exit_code={res_sum.returncode if res_sum else 'None'})")
                if job:
                    job.status = JobStatus.COMPLETED
                    job.current_step = None
                    job.error_message = f"議事録作成前の要約生成に失敗しました（ログ: logs/{sum_log.name}）"
                    _get_active_wm().save_job_json(job)
                return

            new_sum_artifacts = _collect_and_publish_artifacts(job, "summary", ws_dir, share_dir)
            if "summary" not in job.workflow:
                job.workflow.append("summary")
            if job.step_history is None:
                job.step_history = []
            job.step_history.append({
                "step": "summary",
                "status": "COMPLETED",
                "started_at": datetime.fromtimestamp(sum_start).isoformat(),
                "completed_at": datetime.now().isoformat(),
                "elapsed_sec": sum_elapsed,
                "exit_code": 0,
                "error_message": None,
                "artifacts": [a["name"] for a in new_sum_artifacts],
            })
            _get_active_wm().save_job_json(job)

        # =========================================================================
        # 2. 本ステップ（minutes または summary）の実行
        # =========================================================================
        job = _get_active_wm().get_job(job_id)
        if not job:
            return

        job.status = JobStatus.RUNNING
        job.current_step = f"generating_{step}"
        _get_active_wm().save_job_json(job)

        start_time = time.time()
        log_file_path = logs_dir / f"{step}_add.log"

        if step == "minutes":
            cli_path = config.PROJECT_ROOT / "ALICE_Minutes" / "cli.py"
            cwd = config.PROJECT_ROOT / "ALICE_Minutes"

            resolved_template = template or "auto"
            if resolved_template == "auto":
                resolved_template = "standard"
                summary_analysis_path = ws_dir / "summary" / "analysis.json"
                summary_meta_path = ws_dir / "summary" / "metadata.json"
                conv_type = None
                if summary_meta_path.exists():
                    try:
                        with open(summary_meta_path, "r", encoding="utf-8") as f:
                            conv_type = json.load(f).get("conversation_type")
                    except Exception:
                        pass
                if not conv_type and summary_analysis_path.exists():
                    try:
                        with open(summary_analysis_path, "r", encoding="utf-8") as f:
                            conv_type = json.load(f).get("metadata", {}).get("conversation_type")
                    except Exception:
                        pass

                if conv_type:
                    conv_type_lower = str(conv_type).lower()
                    if "interview" in conv_type_lower or "面談" in conv_type_lower or "1on1" in conv_type_lower:
                        resolved_template = "interview"
                    elif "consultation" in conv_type_lower or "相談" in conv_type_lower:
                        resolved_template = "consultation"
                    elif "executive" in conv_type_lower or "役員" in conv_type_lower:
                        resolved_template = "executive"

            cmd = [str(python_bin), str(cli_path), "--workspace", str(ws_dir), "--template", resolved_template]
        elif step == "summary":
            cli_path = config.PROJECT_ROOT / "ALICE_Summary" / "cli.py"
            cwd = config.PROJECT_ROOT / "ALICE_Summary"
            cmd = [str(python_bin), str(cli_path), "--workspace", str(ws_dir), "--type", "auto"]
        else:
            return

        logger.info(f"[Admin] Executing command: {' '.join(cmd)}")
        with open(log_file_path, "w", encoding="utf-8") as log_f:
            res = subprocess.run(
                cmd, cwd=str(cwd), env=env, stdout=log_f, stderr=subprocess.STDOUT, timeout=600, check=False
            )

        elapsed = round(time.time() - start_time, 2)
        job = _get_active_wm().get_job(job_id)
        if not job:
            return

        if res.returncode == 0:
            logger.info(f"[Admin] Successfully generated {step} for job {job_id} in {elapsed}s")
            new_artifacts = _collect_and_publish_artifacts(job, step, ws_dir, share_dir)

            if step not in job.workflow:
                job.workflow.append(step)
            if job.step_history is None:
                job.step_history = []
            job.step_history.append({
                "step": step,
                "status": "COMPLETED",
                "started_at": datetime.fromtimestamp(start_time).isoformat(),
                "completed_at": datetime.now().isoformat(),
                "elapsed_sec": elapsed,
                "exit_code": 0,
                "error_message": None,
                "artifacts": [a["name"] for a in new_artifacts],
            })
            job.status = JobStatus.COMPLETED
            job.current_step = None
            _get_active_wm().save_job_json(job)

            # 検索インデックス更新
            try:
                core_worker._update_search_index(job)
            except Exception as e:
                logger.warning(f"[Admin] Failed to update search index for {job_id}: {e}")

        else:
            logger.error(f"[Admin] Generation of {step} failed with exit_code {res.returncode}")
            job.status = JobStatus.COMPLETED
            job.current_step = None
            job.error_message = f"{step}の追加生成に失敗しました（ログ: logs/{log_file_path.name}）"
            _get_active_wm().save_job_json(job)

    except Exception as e:
        logger.exception(f"[Admin] Exception during {step} generation for {job_id}: {e}")
        try:
            job = _get_active_wm().get_job(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.current_step = None
                job.error_message = f"{step}の生成中にエラーが発生しました: {e}"
                _get_active_wm().save_job_json(job)
        except Exception:
            pass

@router.post("/api/jobs/{job_id}/generate-step")
async def generate_job_step(
    job_id: str,
    payload: GenerateStepRequest,
):
    """未生成の成果物（議事録または要約）を既存ワークスペースに対して追加生成する（安全な直列キュー実行）。"""
    if not _get_active_wm():
        raise HTTPException(status_code=500, detail="WorkspaceManager unavailable")

    job = _get_active_wm().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    step = payload.step.lower().strip()
    if step not in ["minutes", "summary"]:
        raise HTTPException(status_code=400, detail="許可されていないステップです (minutes または summary を指定してください)")

    # 二重実行・待機中チェック
    if job.current_step and (job.current_step.startswith("generating_") or job.current_step.startswith("queued_")):
        raise HTTPException(status_code=400, detail="このジョブは現在追加生成の処理中または待機中です。完了までお待ちください")

    # 前提成果物チェック（transcript.json または transcript.txt が必要）
    ws_dir = job.workspace_dir
    transcript_json = ws_dir / "transcript" / "transcript.json"
    transcript_txt = ws_dir / "transcript" / "transcript.txt"
    if not transcript_json.exists() and not transcript_txt.exists():
        raise HTTPException(status_code=400, detail="文字起こしデータ（transcript）が存在しないため、追加生成できません")

    # 既生成チェック（上書きしない）
    if step == "minutes":
        primary = ws_dir / "minutes" / "minutes.md"
        if primary.exists():
            raise HTTPException(status_code=400, detail="議事録はすでに生成されています")
    elif step == "summary":
        primary = ws_dir / "summary" / "summary.md"
        if primary.exists():
            raise HTTPException(status_code=400, detail="要約はすでに生成されています")

    # ステータスを QUEUED / queued_step に更新してキューに登録
    job.status = JobStatus.QUEUED
    job.current_step = f"queued_{step}"
    _get_active_wm().save_job_json(job)

    _start_step_gen_worker()
    q = getattr(sys.modules.get("portal.admin"), "_step_gen_queue", _step_gen_queue)
    q.put((job.job_id, step, payload.template or "auto"))

    return {
        "status": "queued",
        "job_id": job.job_id,
        "step": step,
        "message": f"{step}の追加生成をキューに登録しました。順次安全に処理されます。"
    }


@router.get("/api/jobs/{job_id}/artifact")
async def get_job_artifact(job_id: str, path: str = Query(..., description="Relative path within workspace")):
    """Safely fetch text content of a workspace artifact or log."""
    # Prevent directory traversal
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path parameter")

    ws_dir = _get_active_wm().base_dir / job_id
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

    ws_dir = _get_active_wm().base_dir / job_id
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

    job = _get_active_wm().get_job(job_id)
    original_title = _extract_job_filename(job) if job else job_id

    tpl_path = Path(__file__).resolve().parent / "templates" / "artifact_viewer.html"
    tpl = tpl_path.read_text(encoding="utf-8")
    html_content = tpl.format(
        page_title=f"{html.escape(original_title)} | {html.escape(target_file.name)}",
        path=html.escape(path),
        job_id=html.escape(job_id),
        original_title=html.escape(original_title),
        rendered_body=rendered_body
    )
    return HTMLResponse(content=html_content, status_code=200)

