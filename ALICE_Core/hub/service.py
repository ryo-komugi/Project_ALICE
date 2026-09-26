import logging
from typing import Any
from pathlib import Path
from models.job import Job
from hub.queue import JobQueue
from hub.workspace import WorkspaceManager
from hub.worker import CoreWorker

logger = logging.getLogger(__name__)


class JobService:
    """Gateway や Portal が Hub の内部構造を直接意識せずに操作するための高レベル Facade サービス"""

    def __init__(
        self,
        job_queue: JobQueue,
        workspace_manager: WorkspaceManager,
        core_worker: CoreWorker,
    ):
        self.job_queue = job_queue
        self.workspace_manager = workspace_manager
        self.core_worker = core_worker

    def submit_job(
        self,
        user_id: str,
        src_file: Path | str,
        workflow: list[str],
        original_filename: str | None = None,
    ) -> Job:
        """ワークスペースを作成し、JobQueue に登録する一連の処理を一括実行"""
        job = self.workspace_manager.create_workspace(
            user_id=user_id,
            src_file=src_file,
            workflow=workflow,
            original_filename=original_filename,
        )
        self.job_queue.push(job)
        logger.info(f"[JobService] Enqueued job: {job.job_id} (workflow={job.workflow}, queue_size={self.job_queue.size()})")
        return job

    def get_queue_status_text(self, user_id: str | None = None) -> str:
        """ユーザー向けキュー状況テキスト（実行中・待機中）を生成"""
        current_job = self.core_worker.current_job if self.core_worker else None
        queued_jobs = self.job_queue.get_queued_jobs()

        lines = ["【キュー状況】"]
        lines.append("  〇 実行中")
        if current_job:
            if not user_id or current_job.user_id == user_id:
                lines.append(f"    ：{current_job.input_file.name}")
            else:
                lines.append("    ：他の処理を実行中")
        else:
            lines.append("    ：なし")

        lines.append("  〇 待機中")
        if not user_id:
            if queued_jobs:
                for j in queued_jobs:
                    lines.append(f"    ：{j.input_file.name}")
            else:
                lines.append("    ：なし")
        else:
            user_jobs_with_pos = [
                (j, idx + 1) for idx, j in enumerate(queued_jobs) if j.user_id == user_id
            ]
            if user_jobs_with_pos:
                for j, pos in user_jobs_with_pos:
                    lines.append(f"    ：{j.input_file.name} (待機 {pos}番目)")
            else:
                total_queued = len(queued_jobs)
                if total_queued > 0:
                    lines.append(f"    ：なし (全体で {total_queued}件待機中)")
                else:
                    lines.append("    ：なし")

        return "\n".join(lines)

    def recover_interrupted_jobs(self) -> tuple[int, int]:
        """再起動時の中断ジョブリカバリ"""
        return self.workspace_manager.recover_interrupted_jobs(self.job_queue)

    def start(self) -> None:
        if self.core_worker:
            self.core_worker.start()

    def stop(self, wait: bool = True) -> None:
        if self.core_worker:
            self.core_worker.stop(wait=wait)
