# Backward compatibility shim for core.worker -> hub.worker
from hub.worker import CoreWorker
from hub.runners import MODULE_RUNNERS

__all__ = ["CoreWorker", "MODULE_RUNNERS"]
