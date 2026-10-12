import config
from repository.user_repository import UserRepository
from auth.user_status import UserStatus


class AuthManager:
    def __init__(self):
        self.repository = UserRepository()

    def verify_invite_code(self, user_id: str, invite_code: str) -> bool:
        if invite_code != config.INVITE_CODE:
            return False

        self.repository.update_status(
            user_id,
            UserStatus.READY
        )
        return True