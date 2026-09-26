import logging
from gateway.sender import MessageSender
from repository.user_repository import UserRepository
from auth.user import User
from auth.user_status import UserStatus
from gateway.profile import ProfileManager

logger = logging.getLogger(__name__)


class FollowHandler:
    logger.info("[FollowHandler] Follow event received")

    def __init__(self):
        self.sender = MessageSender()
        self.repository = UserRepository()
        self.profile_manager = ProfileManager()

    def handle(self, event: dict) -> None:
        logger.info("Follow Handler")
        user_id = event["source"]["userId"]
        reply_token = event["replyToken"]

        user = self.repository.find(user_id)
        profile = self.profile_manager.get_profile(user_id)
        logger.info(f"[FollowHandler] Find user : {user_id}")

        if user is None:
            self.repository.create(
                User(
                    user_id=user_id,
                    display_name=profile.display_name,
                    status=UserStatus.WAIT_INVITE_CODE
                )
            )
            logger.info(f"[FollowHandler] Find user : {user_id}")

        from core.system_settings import is_maintenance_active, get_maintenance_message
        if is_maintenance_active():
            self.sender.reply_text(
                reply_token,
                f"こちらはProject_ALICEの入力UIです。\n\n【お知らせ】\n{get_maintenance_message()}\n\n※メンテナンス終了後に【招待コード】を入力してください。"
            )
            return

        self.sender.reply_text(
            reply_token,
            "こちらはProject_ALICEの入力UIです。\n利用するためには【招待コード】を入力してください。"
        )
