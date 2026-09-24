"""
Unit tests for ALICE_CoPilot memory ownership & contamination guard.
"""
import pytest
import config
from memory.ownership_guard import validate_job_for_memory


def test_is_owner_core_user():
    owner_id = config.OWNER_CORE_USER_ID
    assert config.is_owner_core_user(owner_id) is True
    assert config.is_owner_core_user("guest_user_123") is False
    assert config.is_owner_core_user("") is False
    assert config.is_owner_core_user(None) is False


def test_validate_job_for_memory_dict_success():
    owner_id = config.OWNER_CORE_USER_ID
    job_data = {
        "job_id": "job_owner_001",
        "user_id": owner_id,
        "status": "COMPLETED",
    }
    assert validate_job_for_memory(job_data) is True


def test_validate_job_for_memory_dict_guest_blocked():
    job_data = {
        "job_id": "job_guest_001",
        "user_id": "U_guest_line_9999",
        "status": "COMPLETED",
    }
    # Guest jobs must be blocked from entering owner memory
    assert validate_job_for_memory(job_data) is False


def test_validate_job_for_memory_missing_or_empty():
    assert validate_job_for_memory({}) is False
    assert validate_job_for_memory({"job_id": "test"}) is False
    assert validate_job_for_memory(None) is False


def test_validate_job_for_memory_object_attributes():
    class DummyJob:
        def __init__(self, job_id, user_id):
            self.job_id = job_id
            self.user_id = user_id

    owner_id = config.OWNER_CORE_USER_ID
    job_owner = DummyJob("job_1", owner_id)
    job_guest = DummyJob("job_2", "guest_555")

    assert validate_job_for_memory(job_owner) is True
    assert validate_job_for_memory(job_guest) is False
