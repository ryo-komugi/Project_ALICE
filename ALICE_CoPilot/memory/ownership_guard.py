"""
ALICE_CoPilot Memory Ownership & Contamination Guard.
Provides verification to ensure Core Jobs and external memories belong to the authorized owner
before allowing them to be indexed or ingested into CoPilot's Second Brain (Obsidian/Long-Term Memory).
"""
import logging
from typing import Any, Mapping
import config

logger = logging.getLogger("ALICE_CoPilot.OwnershipGuard")


def validate_job_for_memory(job_data: Mapping[str, Any] | Any) -> bool:
    """
    Validate whether a Core Job belongs to the authorized owner and is safe to ingest into Memory.

    Args:
        job_data: Dictionary (e.g. from job.json or Job object) containing at least 'user_id'.

    Returns:
        bool: True if authorized owner, False if non-owner or invalid data.
    """
    if not job_data:
        logger.warning("[OwnershipGuard] Empty job data provided for memory validation.")
        return False

    # Extract user_id from dict-like or object
    if isinstance(job_data, Mapping):
        user_id = job_data.get("user_id")
        job_id = job_data.get("job_id", "unknown")
    else:
        user_id = getattr(job_data, "user_id", None)
        job_id = getattr(job_data, "job_id", "unknown")

    if not user_id:
        logger.warning(f"[OwnershipGuard] Job [{job_id}] has no user_id. Blocked from memory ingestion.")
        return False

    is_owner = config.is_owner_core_user(str(user_id))
    if not is_owner:
        logger.warning(
            f"[OwnershipGuard] Contamination Guard Triggered: Job [{job_id}] belongs to guest user [{user_id}]. "
            f"Blocked from owner second brain / long-term memory."
        )
        return False

    logger.debug(f"[OwnershipGuard] Job [{job_id}] ownership verified for owner [{user_id}].")
    return True
