"""
ALICE_Core Portal - User Directory & Access Management Router.
"""
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger("ALICE_Core.Admin.Users")

router = APIRouter()

# User Directory API Endpoints (users.db)
# ==========================================
@router.get("/api/users")
async def list_users():
    """List all registered users from users.db."""
    try:
        from repository.user_repository import UserRepository
        repo = UserRepository()
        users = repo.get_all()
        return [
            {
                "user_id": u.user_id,
                "display_name": u.display_name,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status)
            }
            for u in users
        ]
    except Exception as e:
        logger.error(f"[Admin] Failed to list users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/users/{user_id}")
async def update_user(user_id: str, data: dict):
    """Update user's display_name and status, sync LINE rich menu."""
    display_name = data.get("display_name", "").strip()
    status_str = data.get("status", "").strip()
    if not display_name or not status_str:
        raise HTTPException(status_code=400, detail="display_name and status are required")

    from auth.user_status import UserStatus
    from repository.user_repository import UserRepository
    from gateway.richmenu.richmane import RichMenu

    try:
        status_enum = UserStatus(status_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_str}")

    try:
        repo = UserRepository()
        repo.update(user_id, display_name, status_enum)

        # Sync Rich Menu based on new status
        rm = RichMenu()
        if status_enum == UserStatus.REJECTED:
            rm.unlink(user_id)
        elif status_enum == UserStatus.READY:
            rm.switch(user_id, "UserMenu")

        return {"status": "ok", "user_id": user_id, "display_name": display_name, "user_status": status_str}
    except Exception as e:
        logger.error(f"[Admin] Failed to update user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/users/{user_id}")
async def delete_user(user_id: str):
    """Delete user from users.db and unlink rich menu."""
    from repository.user_repository import UserRepository
    from gateway.richmenu.richmane import RichMenu

    try:
        rm = RichMenu()
        rm.unlink(user_id)
        repo = UserRepository()
        repo.delete(user_id)
        return {"status": "deleted", "user_id": user_id}
    except Exception as e:
        logger.error(f"[Admin] Failed to delete user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================