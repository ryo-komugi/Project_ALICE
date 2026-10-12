import logging
from repository.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UnfollowHandler:
    def __init__(self):
        self.repository = UserRepository()

    def handle(self, event: dict) -> None:
        logger.info("[UnfollowHandler] Unfollow event")
        user_id = event["source"]["userId"]
        self.repository.delete(user_id)
        logger.info(f"[UserRepository] Delete : {user_id}")
