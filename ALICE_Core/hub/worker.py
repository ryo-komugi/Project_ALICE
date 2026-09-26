from hub.runners import MODULE_RUNNERS
import os
import sys
import logging
import subprocess
import threading
import shutil
import time
from datetime import datetime
from pathlib import Path
from models.job import Job, JobStatus, StepStatus
from core.alert_notifier import send_discord_alert
from hub.queue import JobQueue
from hub.workspace import WorkspaceManager
from publisher.publisher import Publisher
from gateway.sender import MessageSender
import config

logger = logging.getLogger(__name__)

# Core Module Runners Definition is imported from hub.runners (line 1)


class CoreWorker:
    """JobQueue を監視し、Job の workflow に従って各 Module CLI を順次実行・進捗追跡・Publisher 配信する汎用 Worker"""

    def __init__(
        self,
        job_queue: JobQueue,
        workspace_manager: WorkspaceManager,
        publisher: Publisher | None = None,
        module_runners: dict | None = None,
        sender: MessageSender | None = None,
    ):
        self.job_queue = job_queue
        self.workspace_manager = workspace_manager
        self.publisher = publisher or Publisher()
        self.module_runners = module_runners or MODULE_RUNNERS
        self.sender = sender or MessageSender()
        self.current_job: Job | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("[CoreWorker] Worker started")

    def stop(self, wait: bool = True) -> None:
        self._running = False
        if wait and hasattr(self, "_thread") and self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=2.0)

    def _run_loop(self) -> None:
        while self._running:
            job = self.job_queue.pop(block=True, timeout=1.0)
            if job is None:
                continue

            try:
                self.process_job(job)
            except Exception as e:
                logger.exception(f"[CoreWorker] Unexpected error processing {job.job_id}: {e}")
            finally:
                self.job_queue.task_done()

    def process_job(self, job: Job) -> bool:
        logger.info(f"[CoreWorker] Starting job: {job.job_id} with workflow: {job.workflow}")
        self.current_job = job
        try:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now()
            
            # 各ステップの実行履歴（初期状態: PENDING）を構築
            if not job.step_history:
                job.step_history = [
                    {
                        "step": m,
                        "status": StepStatus.PENDING.value,
                        "started_at": None,
                        "completed_at": None,
                        "elapsed_sec": None,
                        "exit_code": None,
                        "error_message": None,
                        "artifacts": [],
                    }
                    for m in job.workflow
                ]
            self.workspace_manager.save_job_json(job)

            # 1. 未知モジュール検証
            for idx, module_name in enumerate(job.workflow):
                if module_name not in self.module_runners:
                    error_msg = f"Unknown module '{module_name}' in workflow {job.workflow}"
                    logger.error(f"[CoreWorker] Validation failed: {error_msg}")
                    job.status = JobStatus.FAILED
                    job.current_step = None
                    job.error_message = error_msg
                    job.error_detail = {
                        "failed_step": module_name,
                        "error_type": "UNKNOWN_MODULE",
                        "exit_code": None,
                        "message": error_msg,
                        "log_file": None,
                        "timestamp": datetime.now().isoformat(),
                    }
                    for step_data in job.step_history:
                        if step_data["step"] == module_name:
                            step_data["status"] = StepStatus.FAILED.value
                            step_data["error_message"] = error_msg
                        elif step_data["status"] == StepStatus.PENDING.value:
                            step_data["status"] = StepStatus.SKIPPED.value

                    self.workspace_manager.save_job_json(job)
                    self._notify_failure(job, f"指定された機能「{module_name}」は存在しません。")
                    return False

            last_module_name = None
            last_artifact_path = None

            # 2. 直列ワークフロー実行
            for idx, module_name in enumerate(job.workflow):
                runner_info = self.module_runners[module_name]
                logger.info(f"[CoreWorker] [{job.job_id}] Executing step '{module_name}'")

                # ステップ開始状態の記録
                job.current_step = module_name
                step_entry = next((s for s in job.step_history if s["step"] == module_name), None)
                t_step_start = time.time()
                started_dt = datetime.now()
                if step_entry:
                    step_entry["status"] = StepStatus.RUNNING.value
                    step_entry["started_at"] = started_dt.isoformat()
                self.workspace_manager.save_job_json(job)

                success, artifact_path, step_artifacts, exit_code, err_msg = self._execute_module(
                    job, module_name, runner_info
                )
                elapsed_sec = round(time.time() - t_step_start, 2)
                completed_dt = datetime.now()

                if step_entry:
                    step_entry["completed_at"] = completed_dt.isoformat()
                    step_entry["elapsed_sec"] = elapsed_sec
                    step_entry["exit_code"] = exit_code
                    step_entry["artifacts"] = [a["name"] for a in step_artifacts]

                if not success:
                    error_msg = f"Step '{module_name}' failed"
                    logger.error(f"[CoreWorker] [{job.job_id}] {error_msg} (exit_code={exit_code}): {err_msg}")
                    job.status = JobStatus.FAILED
                    job.current_step = None
                    job.error_message = error_msg
                    job.error_detail = {
                        "failed_step": module_name,
                        "error_type": "MODULE_EXECUTION_ERROR" if exit_code != 0 else "ARTIFACT_MISSING",
                        "exit_code": exit_code,
                        "message": err_msg or error_msg,
                        "log_file": str(job.logs_dir / f"{module_name}.log"),
                        "timestamp": completed_dt.isoformat(),
                    }
                    if step_entry:
                        step_entry["status"] = StepStatus.FAILED.value
                        step_entry["error_message"] = err_msg or error_msg

                    # 後続ステップを SKIPPED に設定
                    for future_idx in range(idx + 1, len(job.step_history)):
                        job.step_history[future_idx]["status"] = StepStatus.SKIPPED.value

                    self.workspace_manager.save_job_json(job)
                    self._notify_failure(job, f"処理中にエラーが発生しました（ステップ: {module_name}）。")
                    return False

                # ステップ成功
                if step_entry:
                    step_entry["status"] = StepStatus.COMPLETED.value
                
                # 新規成果物をジョブ全体の成果物参照リストへ追加（重複防止）
                existing_names = {a["name"] for a in job.artifacts}
                for art in step_artifacts:
                    if art["name"] not in existing_names:
                        job.artifacts.append(art)
                        existing_names.add(art["name"])

                last_module_name = module_name
                last_artifact_path = artifact_path
                self.workspace_manager.save_job_json(job)

            # 3. 全ステップ完了 -> 最終モジュールのプライマリ成果物を配信
            job.status = JobStatus.COMPLETED
            job.current_step = None
            job.completed_at = datetime.now()
            logger.info(f"[CoreWorker] Job COMPLETED: {job.job_id}")

            if last_artifact_path and last_artifact_path.exists():
                self._publish_result(job, last_artifact_path, last_module_name)
            else:
                logger.warning(f"[CoreWorker] Final artifact not found for publishing: {last_artifact_path}")
                self._notify_failure(job, "成果物の生成に失敗しました。")

            self.workspace_manager.save_job_json(job)

            # 4. [派生キャッシュ更新] ALICE_Search インデックス更新 (成否完全分離)
            try:
                self._update_search_index(job)
            except Exception as e:
                logger.warning(
                    f"[CoreWorker] [{job.job_id}] Unhandled error in search index update (Job status remains COMPLETED): {e}"
                )

            # 5. [ストレージ軽量化] 音声原本の安全な削除・プレースホルダー化 (成否完全分離)
            try:
                self.workspace_manager.cleanup_input_audio(job)
            except Exception as e:
                logger.warning(
                    f"[CoreWorker] [{job.job_id}] Failed to cleanup input audio: {e}"
                )

            return True
        finally:
            self.current_job = None

    def _execute_module(
        self, job: Job, module_name: str, runner_info: dict
    ) -> tuple[bool, Path | None, list[dict], int | None, str | None]:
        """Module CLI を実行し、Artifact Contract に基づく成果物参照を検出する（リトライ＆タイムアウトSLA対応）"""
        python_bin = runner_info["python_bin"]
        cli_path = runner_info["cli_path"]
        module_cwd = runner_info.get("module_cwd")
        artifact_dir = runner_info["artifact_dir"]
        primary_artifact = runner_info["primary_artifact"]
        contract_artifacts = runner_info.get("contract_artifacts", [primary_artifact])

        cmd = [
            python_bin,
            cli_path,
            "--workspace",
            str(job.workspace_dir),
        ]

        log_file = job.logs_dir / f"{module_name}.log"

        # systemd 環境下でも ffmpeg などのシステムコマンドが見つかるよう PATH を補完
        env = os.environ.copy()
        system_paths = ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
        current_path = env.get("PATH", "")
        env["PATH"] = ":".join(system_paths + [current_path])

        timeout_sec = getattr(config, "MODULE_TIMEOUT_SEC", 900)
        max_retries = getattr(config, "MODULE_MAX_RETRIES", 2)
        retry_backoff = getattr(config, "MODULE_RETRY_BACKOFF_SEC", 5)

        expected_primary = job.workspace_dir / artifact_dir / primary_artifact
        last_exit_code = -1
        last_err_msg = None
        collected_artifacts: list[dict] = []

        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.warning(
                    f"[CoreWorker] [{job.job_id}] Step '{module_name}' retry attempt {attempt}/{max_retries} "
                    f"after {retry_backoff}s backoff..."
                )
                time.sleep(retry_backoff)

            try:
                file_mode = "w" if attempt == 0 else "a"
                with open(log_file, file_mode, encoding="utf-8") as lf:
                    if attempt > 0:
                        lf.write(f"\n--- RETRY ATTEMPT {attempt}/{max_retries} ({datetime.now().isoformat()}) ---\n")
                        lf.flush()
                    res = subprocess.run(
                        cmd,
                        cwd=module_cwd,
                        env=env,
                        stdout=lf,
                        stderr=subprocess.STDOUT,
                        check=False,
                        timeout=timeout_sec,
                    )

                collected_artifacts = self._collect_artifacts(
                    job, module_name, artifact_dir, primary_artifact, contract_artifacts
                )

                if res.returncode == 0 and expected_primary.exists():
                    if attempt > 0:
                        logger.info(
                            f"[CoreWorker] Step '{module_name}' SUCCESS on retry attempt {attempt}. "
                            f"Artifact: {expected_primary}"
                        )
                    else:
                        logger.info(f"[CoreWorker] Step '{module_name}' SUCCESS. Artifact: {expected_primary}")
                    return True, expected_primary, collected_artifacts, res.returncode, None
                else:
                    last_exit_code = res.returncode
                    last_err_msg = (
                        f"Process exited with {res.returncode}"
                        if res.returncode != 0
                        else f"Primary artifact '{primary_artifact}' not found"
                    )
                    logger.error(
                        f"[CoreWorker] Step '{module_name}' FAILED (attempt={attempt}/{max_retries}, "
                        f"exit_code={res.returncode}, artifact_exists={expected_primary.exists()}): {last_err_msg}"
                    )

            except subprocess.TimeoutExpired:
                last_exit_code = -1
                last_err_msg = f"Step '{module_name}' timed out after {timeout_sec}s"
                logger.error(
                    f"[CoreWorker] Step '{module_name}' TIMEOUT (attempt={attempt}/{max_retries}): {last_err_msg}"
                )
                try:
                    with open(log_file, "a", encoding="utf-8") as lf:
                        lf.write(f"\n[ERROR] Execution timed out after {timeout_sec} seconds.\n")
                except Exception:
                    pass
            except Exception as e:
                last_exit_code = -1
                last_err_msg = str(e)
                logger.exception(
                    f"[CoreWorker] Exception in step '{module_name}' (attempt={attempt}/{max_retries}): {e}"
                )

        return False, None, collected_artifacts, last_exit_code, last_err_msg

    def _collect_artifacts(
        self,
        job: Job,
        module_name: str,
        artifact_dir: str,
        primary_artifact: str,
        contract_artifacts: list[str],
    ) -> list[dict]:
        """Module の Artifact Contract を最優先にして成果物参照メタデータを確定する（本文は格納しない）"""
        artifacts: list[dict] = []
        target_dir = job.workspace_dir / artifact_dir
        if not target_dir.exists():
            return artifacts

        # 1. Contract Artifacts の検証と登録 (優先)
        registered_files = set()
        for filename in contract_artifacts:
            file_path = target_dir / filename
            if file_path.exists() and file_path.is_file():
                registered_files.add(filename)
                artifacts.append({
                    "name": filename,
                    "path": f"{artifact_dir}/{filename}",
                    "module": module_name,
                    "is_primary": (filename == primary_artifact),
                    "size_bytes": file_path.stat().st_size,
                    "created_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                })

        # 2. プライマリアーティファクトが contract_artifacts に含まれていない場合の補完
        if primary_artifact not in registered_files:
            primary_path = target_dir / primary_artifact
            if primary_path.exists() and primary_path.is_file():
                artifacts.append({
                    "name": primary_artifact,
                    "path": f"{artifact_dir}/{primary_artifact}",
                    "module": module_name,
                    "is_primary": True,
                    "size_bytes": primary_path.stat().st_size,
                    "created_at": datetime.fromtimestamp(primary_path.stat().st_mtime).isoformat(),
                })

        return artifacts

    def _publish_result(self, job: Job, filepath: Path, module_name: str) -> None:
        try:
            publish_filename = f"{job.job_id}_{module_name}_{filepath.name}"
            publish_filepath = filepath.parent / publish_filename
            shutil.copy2(filepath, publish_filepath)

            extra_files = {}
            if module_name == "summary":
                comm_path = filepath.parent / "commentary.txt"
                if not comm_path.exists():
                    comm_path = filepath.parent / "commentary.md"
                if comm_path.exists():
                    comm_publish_filename = f"{job.job_id}_{module_name}_{comm_path.name}"
                    comm_publish_filepath = filepath.parent / comm_publish_filename
                    shutil.copy2(comm_path, comm_publish_filepath)
                    extra_files["commentary"] = str(comm_publish_filepath)

            elif module_name == "minutes":
                # minutes.txt も同時に share 配置用に準備
                txt_path = filepath.parent / "minutes.txt"
                if txt_path.exists():
                    txt_publish_filename = f"{job.job_id}_{module_name}_minutes.txt"
                    txt_publish_filepath = filepath.parent / txt_publish_filename
                    shutil.copy2(txt_path, txt_publish_filepath)
                    share_dst = Path(config.DIR_SHARE) / txt_publish_filename
                    try:
                        shutil.copy2(txt_publish_filepath, share_dst)
                    except Exception as err:
                        logger.warning(f"[CoreWorker] Failed to sync minutes.txt to share: {err}")

                # summary 成果物 (summary / commentary) も合わせて extra_files に格納し DIR_SHARE に同期
                summary_dir = job.workspace_dir / "summary"
                if summary_dir.exists():
                    sum_path = summary_dir / "summary.txt"
                    if not sum_path.exists():
                        sum_path = summary_dir / "summary.md"
                    if sum_path.exists():
                        sum_publish_filename = f"{job.job_id}_summary_{sum_path.name}"
                        sum_publish_filepath = summary_dir / sum_publish_filename
                        shutil.copy2(sum_path, sum_publish_filepath)
                        extra_files["summary"] = str(sum_publish_filepath)

                    # summary.md / summary.txt 両方ある場合は viewer 用に share に配置
                    for ext in [".md", ".txt"]:
                        cand_sum = summary_dir / f"summary{ext}"
                        if cand_sum.exists():
                            cand_pub = summary_dir / f"{job.job_id}_summary_summary{ext}"
                            shutil.copy2(cand_sum, cand_pub)
                            try:
                                shutil.copy2(cand_pub, Path(config.DIR_SHARE) / cand_pub.name)
                            except Exception as err:
                                logger.warning(f"[CoreWorker] Failed to sync summary{ext} to share: {err}")

                    comm_path = summary_dir / "commentary.txt"
                    if not comm_path.exists():
                        comm_path = summary_dir / "commentary.md"
                    if comm_path.exists():
                        comm_publish_filename = f"{job.job_id}_summary_{comm_path.name}"
                        comm_publish_filepath = summary_dir / comm_publish_filename
                        shutil.copy2(comm_path, comm_publish_filepath)
                        extra_files["commentary"] = str(comm_publish_filepath)

                    for ext in [".md", ".txt"]:
                        cand_com = summary_dir / f"commentary{ext}"
                        if cand_com.exists():
                            cand_pub = summary_dir / f"{job.job_id}_summary_commentary{ext}"
                            shutil.copy2(cand_com, cand_pub)
                            try:
                                shutil.copy2(cand_pub, Path(config.DIR_SHARE) / cand_pub.name)
                            except Exception as err:
                                logger.warning(f"[CoreWorker] Failed to sync commentary{ext} to share: {err}")

            logger.info(f"[CoreWorker] Publishing {publish_filepath} to user {job.user_id} (module={module_name}, extra_files={list(extra_files.keys())})")
            self.publisher.publish(str(publish_filepath), job.user_id, module_name=module_name, extra_files=extra_files)
            logger.info(f"[CoreWorker] Successfully published for {job.job_id}")
        except Exception as e:
            logger.error(f"[CoreWorker] Failed to publish for {job.job_id}: {e}")

    def _notify_failure(self, job: Job, message: str) -> None:
        try:
            self.sender.push_text(job.user_id, f"【エラー】\n{message}")
        except Exception as e:
            logger.error(f"[CoreWorker] Failed to send failure notification to {job.user_id}: {e}")

        # 管理者向け Discord アラート送信 (#alerts)
        try:
            err_type = (
                job.error_detail.get("error_type", "JOB_EXECUTION_FAILURE")
                if hasattr(job, "error_detail") and job.error_detail
                else "JOB_EXECUTION_FAILURE"
            )
            err_msg = (
                job.error_detail.get("message", job.error_message or message)
                if hasattr(job, "error_detail") and job.error_detail
                else (job.error_message or message)
            )
            send_discord_alert(job=job, error_type=err_type, message=err_msg, level="ERROR")
        except Exception as e:
            logger.warning(f"[CoreWorker] Failed to dispatch Discord alert: {e}")

    def _update_search_index(self, job: Job) -> None:
        """Job COMPLETED 後に ALICE_Search CLI を呼び出してインデックスを更新する。

        【重要原則】
        - 検索インデックスは派生キャッシュであり、更新失敗によって Job 本体の成否 (COMPLETED) を覆してはならない。
        - Core と Search は直接 import せず、Workspace Driven CLI (subprocess) で疎結合に連携する。
        - 失敗時は WARNING ログを記録し、Job 処理は正常終了とする。
        """
        search_cli = config.PROJECT_ROOT / "ALICE_Search" / "cli.py"
        if not search_cli.exists():
            logger.debug(f"[CoreWorker] ALICE_Search CLI not found at {search_cli}. Skipping search index update.")
            return

        cmd = [
            sys.executable,
            str(search_cli),
            "--index-job",
            str(job.workspace_dir),
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if res.returncode == 0:
                logger.info(f"[CoreWorker] [{job.job_id}] Search index updated successfully.")
            else:
                logger.warning(
                    f"[CoreWorker] [{job.job_id}] Search index update returned non-zero (exit_code={res.returncode}): {res.stderr.strip()}"
                )
        except Exception as e:
            logger.warning(
                f"[CoreWorker] [{job.job_id}] Search index update failed with exception (Job status remains COMPLETED): {e}"
            )

