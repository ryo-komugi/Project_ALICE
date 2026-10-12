"""
ALICE_Core GPU Resource Lock Manager.
Provides an exclusive cross-process file lock using fcntl.flock to prevent
concurrent GPU contention (Whisper transcription vs Ollama LLM synthesis vs on-demand steps)
on single-GPU hardware (e.g. RTX 3060 12GB).
"""
import contextlib
import fcntl
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger("ALICE_Core.GPULock")
GPU_LOCK_FILE = Path(os.getenv("ALICE_GPU_LOCK_FILE", "/tmp/alice_gpu.lock"))


@contextlib.contextmanager
def acquire_gpu_lock(timeout: float = 1800.0, step_name: str = "gpu_step"):
    """
    Acquire an exclusive cross-process file lock for GPU usage.
    Ensures that heavy GPU tasks do not collide and trigger CUDA Out Of Memory (OOM).

    Args:
        timeout: Maximum seconds to wait for lock acquisition (default: 30 minutes).
        step_name: Descriptive name of the step requesting the GPU (for logging).
    """
    GPU_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    lock_fd = os.open(str(GPU_LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o666)
    acquired = False

    try:
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                if time.time() - start_time > timeout:
                    raise TimeoutError(
                        f"Timed out waiting for GPU lock for '{step_name}' after {timeout}s"
                    )
                time.sleep(1.0)

        elapsed_wait = round(time.time() - start_time, 2)
        if elapsed_wait > 1.0:
            logger.info(f"[GPULock] Acquired GPU lock for '{step_name}' after {elapsed_wait}s wait.")
        else:
            logger.debug(f"[GPULock] Acquired GPU lock for '{step_name}'.")

        yield
    finally:
        if acquired:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
        try:
            os.close(lock_fd)
        except Exception:
            pass
