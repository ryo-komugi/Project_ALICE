import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from models.job import Job, JobStatus
from core.alert_notifier import send_discord_alert

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """1 Job = 1 Workspace のディレクトリ構造・ライフサイクル・追跡を管理する"""

    def __init__(self, base_dir: str | Path = "/data/runtime/workspaces"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(
        self,
        user_id: str,
        src_file: Path | str,
        workflow: list[str] | None = None,
        original_filename: str | None = None,
    ) -> Job:
        src_path = Path(src_file)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_stem = Path(original_filename).stem if original_filename else src_path.stem
        job_id = f"job_{timestamp}_{target_stem}"
        workspace_dir = self.base_dir / job_id

        # ディレクトリ作成
        (workspace_dir / "input").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "transcript").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "minutes").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "summary").mkdir(parents=True, exist_ok=True)
        (workspace_dir / "logs").mkdir(parents=True, exist_ok=True)

        # 受信データを input/ に配置
        dst_name = original_filename or src_path.name
        dst_input = workspace_dir / "input" / dst_name
        shutil.copy2(src_path, dst_input)

        # 受信メタデータの記録
        input_metadata = {
            "original_name": dst_name,
            "size_bytes": dst_input.stat().st_size if dst_input.exists() else 0,
            "received_at": datetime.now().isoformat(),
        }

        job = Job(
            job_id=job_id,
            user_id=user_id,
            input_file=dst_input,
            workspace_dir=workspace_dir,
            status=JobStatus.CREATED,
            workflow=workflow or ["transcript"],
            input_metadata=input_metadata,
        )

        self.save_job_json(job)
        return job

    def save_job_json(self, job: Job) -> None:
        """job.json をアトミック（一時ファイル書き込み後に置換）に保存する"""
        job.updated_at = datetime.now()
        job_json_path = job.workspace_dir / "job.json"
        tmp_path = job.workspace_dir / "job.json.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(job.to_dict(), f, ensure_ascii=False, indent=2)
        tmp_path.replace(job_json_path)

    def load_job(self, workspace_dir: Path | str) -> Job:
        """指定 Workspace の job.json を読み込み Job オブジェクトを復元する"""
        ws_path = Path(workspace_dir)
        job_json_path = ws_path / "job.json"
        if not job_json_path.exists():
            raise FileNotFoundError(f"job.json not found in {ws_path}")

        with open(job_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return Job.from_dict(data)

    def get_job(self, job_id: str) -> Job | None:
        """job_id から該当 Workspace の Job を取得する"""
        workspace_dir = self.base_dir / job_id
        job_json_path = workspace_dir / "job.json"
        if not job_json_path.exists():
            return None

        try:
            return self.load_job(workspace_dir)
        except Exception as e:
            logger.error(f"[WorkspaceManager] Failed to load job {job_id}: {e}")
            return None

    def list_jobs(self, limit: int = 50, user_id: str | None = None) -> list[Job]:
        """Workspace ディレクトリ群を走査し、作成日時降順で Job 一覧を返す"""
        jobs: list[Job] = []
        if not self.base_dir.exists():
            return jobs

        for ws_dir in self.base_dir.iterdir():
            if not ws_dir.is_dir():
                continue
            job_json = ws_dir / "job.json"
            if not job_json.exists():
                continue

            try:
                job = self.load_job(ws_dir)
                if user_id and job.user_id != user_id:
                    continue
                jobs.append(job)
            except Exception as e:
                logger.warning(f"[WorkspaceManager] Skipping corrupted job at {ws_dir}: {e}")

        # 作成日時降順（最新順）にソート
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def recover_interrupted_jobs(self, job_queue) -> tuple[int, int]:
        """サーバー起動時に未完了のまま残ったジョブを検出し、安全に復旧する。

        - RUNNING のままスタックしたジョブ:
          再起動により強制中断されたと判定し、FAILED (RESTART_ABORTED) として安全にクローズ。
        - QUEUED または CREATED のジョブ:
          待機中に再起動されたと判定し、job_queue に再投入して実行を継続。

        Returns:
            tuple[int, int]: (aborted_count, requeued_count)
        """
        if not self.base_dir.exists():
            return (0, 0)

        aborted_count = 0
        requeued_count = 0

        # 作成日時昇順（古い順）に処理してキューの順序を維持
        all_jobs = []
        for ws_dir in self.base_dir.iterdir():
            if not ws_dir.is_dir() or not (ws_dir / "job.json").exists():
                continue
            try:
                job = self.load_job(ws_dir)
                all_jobs.append(job)
            except Exception as e:
                logger.warning(f"[WorkspaceManager] Skipping corrupted job during recovery: {ws_dir} ({e})")

        all_jobs.sort(key=lambda j: j.created_at)

        for job in all_jobs:
            if job.status == JobStatus.RUNNING:
                logger.warning(
                    f"[WorkspaceManager] Recovering interrupted RUNNING job {job.job_id} -> Marking as FAILED (RESTART_ABORTED)"
                )
                job.status = JobStatus.FAILED
                job.error_message = "サーバー再起動により処理が中断されました (RESTART_ABORTED)"
                job.error_detail = {
                    "failed_step": job.current_step or "unknown",
                    "error_type": "SERVER_RESTART_ABORTED",
                    "timestamp": datetime.now().isoformat(),
                }
                job.current_step = None
                job.completed_at = datetime.now()
                self.save_job_json(job)
                aborted_count += 1
                try:
                    send_discord_alert(
                        job=job,
                        error_type="SERVER_RESTART_ABORTED",
                        message=job.error_message or "サーバー再起動により中断されました",
                        level="WARN",
                    )
                except Exception as e:
                    logger.warning(f"[WorkspaceManager] Failed to send restart abort alert: {e}")

            elif job.status in (JobStatus.QUEUED, JobStatus.CREATED):
                logger.info(f"[WorkspaceManager] Requeuing interrupted job {job.job_id} into JobQueue")
                job_queue.push(job)
                requeued_count += 1

        if aborted_count > 0 or requeued_count > 0:
            logger.info(
                f"[WorkspaceManager] Startup recovery completed: {aborted_count} aborted, {requeued_count} requeued."
            )

        return (aborted_count, requeued_count)

    def cleanup_input_audio(self, job: Job) -> bool:
        """Job COMPLETED 後に input/ 配下の音声原本を安全に削除・プレースホルダー化してストレージを軽量化する。

        【安全原則】
        - 正本 (transcript/transcript.json) が存在し、サイズが正常であることを確認してから削除する。
        - 削除前にファイル名・サイズ・日時を job.json の input_metadata に確実に残す。
        - input/ 配下にプレースホルダーテキスト ([Audio Source Cleared]) を作成して記録を保持する。
        """
        input_dir = job.workspace_dir / "input"
        if not input_dir.exists():
            return False

        # 安全チェック: transcript.json (Source of Truth) の存在・正常性
        transcript_json = job.workspace_dir / "transcript" / "transcript.json"
        if not transcript_json.exists() or transcript_json.stat().st_size == 0:
            logger.warning(
                f"[WorkspaceManager] [{job.job_id}] Skipping audio cleanup: Source of Truth (transcript.json) not found or empty."
            )
            return False

        audio_extensions = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".opus", ".webm", ".mp4"}
        cleaned_any = False

        for file_path in input_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() in audio_extensions:
                file_name = file_path.name
                file_size = file_path.stat().st_size

                # プレースホルダーテキストの生成
                placeholder_path = input_dir / f"{file_name}.txt"
                placeholder_content = (
                    f"[Audio Source Cleared]\n"
                    f"Original Filename: {file_name}\n"
                    f"Original Size: {file_size} bytes\n"
                    f"Cleared At: {datetime.now().isoformat()}\n"
                    f"Source of Truth: transcript/transcript.json\n"
                )
                try:
                    with open(placeholder_path, "w", encoding="utf-8") as pf:
                        pf.write(placeholder_content)

                    file_path.unlink()
                    logger.info(
                        f"[WorkspaceManager] [{job.job_id}] Cleared audio binary {file_name} ({file_size} bytes) -> Created {placeholder_path.name}"
                    )
                    cleaned_any = True
                except Exception as e:
                    logger.error(
                        f"[WorkspaceManager] [{job.job_id}] Failed to clear audio binary {file_name}: {e}"
                    )

        if cleaned_any:
            if not job.input_metadata:
                job.input_metadata = {}
            job.input_metadata["audio_cleared"] = True
            job.input_metadata["cleared_at"] = datetime.now().isoformat()
            self.save_job_json(job)

        return cleaned_any

    def delete_job(self, job_id: str) -> bool:
        """指定された job_id の Workspace ディレクトリを安全に削除し、ALICE_Search インデックスの再構築をトリガーする"""
        if ".." in job_id or "/" in job_id or "\\" in job_id:
            logger.warning(f"[WorkspaceManager] Security warning: Invalid job_id: {job_id}")
            return False

        workspace_dir = self.base_dir / job_id
        if not workspace_dir.exists() or not workspace_dir.is_dir():
            logger.warning(f"[WorkspaceManager] Cannot delete non-existent workspace: {workspace_dir}")
            return False

        try:
            shutil.rmtree(workspace_dir)
            logger.info(f"[WorkspaceManager] Successfully deleted job workspace: {job_id}")

            # ALICE_Search インデックスの再構築
            try:
                search_cli = Path("/home/takuya/Project_ALICE/ALICE_Search/cli.py")
                if search_cli.exists():
                    import subprocess
                    subprocess.run(["python3", str(search_cli), "--reindex"], timeout=10, capture_output=True)
            except Exception as se:
                logger.warning(f"[WorkspaceManager] Search reindex warning after deleting {job_id}: {se}")

            return True
        except Exception as e:
            logger.error(f"[WorkspaceManager] Failed to delete job workspace {job_id}: {e}")
            return False
