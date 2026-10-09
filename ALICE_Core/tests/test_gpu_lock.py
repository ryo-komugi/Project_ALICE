"""
Unit test for ALICE_Core GPU Resource Lock Manager.
Validates cross-thread/cross-process exclusion and timeout behavior.
"""
import threading
import time
import pytest
from hub.gpu_lock import acquire_gpu_lock


def test_gpu_lock_basic_acquisition():
    """Verify standard acquisition and release."""
    with acquire_gpu_lock(timeout=2.0, step_name="test_basic"):
        assert True


def test_gpu_lock_exclusion_and_timeout():
    """Verify that a second concurrent acquisition blocks and times out if held."""
    lock_acquired = threading.Event()
    release_signal = threading.Event()

    def hold_lock():
        with acquire_gpu_lock(timeout=5.0, step_name="thread_holder"):
            lock_acquired.set()
            release_signal.wait(timeout=3.0)

    t = threading.Thread(target=hold_lock, daemon=True)
    t.start()

    assert lock_acquired.wait(timeout=2.0)

    # Attempt to acquire lock while held with short timeout -> should raise TimeoutError
    with pytest.raises(TimeoutError):
        with acquire_gpu_lock(timeout=0.5, step_name="thread_blocked"):
            pass

    # Release first lock
    release_signal.set()
    t.join(timeout=2.0)

    # Now acquisition should succeed
    with acquire_gpu_lock(timeout=2.0, step_name="thread_after_release"):
        assert True
