import queue
from models.job import Job, JobStatus


class JobQueue:
    """Core が一元管理するインメモリ FIFO キュー"""

    def __init__(self):
        self._queue: queue.Queue[Job] = queue.Queue()

    def push(self, job: Job) -> None:
        job.status = JobStatus.QUEUED
        self._queue.put(job)

    def pop(self, block: bool = True, timeout: float | None = None) -> Job | None:
        try:
            return self._queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def task_done(self) -> None:
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()

    def size(self) -> int:
        return self._queue.qsize()

    def get_queued_jobs(self) -> list[Job]:
        return list(self._queue.queue)

