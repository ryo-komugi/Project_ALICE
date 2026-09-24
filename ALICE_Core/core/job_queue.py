# Backward compatibility shim for core.job_queue -> hub.queue
from hub.queue import JobQueue

__all__ = ["JobQueue"]
