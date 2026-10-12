import logging
from gateway.handlers.follow import FollowHandler
from gateway.handlers.message import MessageHandler
from gateway.handlers.postback import PostbackHandler
from gateway.handlers.unfollow import UnfollowHandler

logger = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(self):
        self.follow_handler = FollowHandler()
        self.message_handler = MessageHandler()
        self.postback_handler = PostbackHandler()
        self.unfollow_handler = UnfollowHandler()

    def dispatch(self, event: dict) -> None:
        event_type = event.get("type")
        match event_type:
            case "follow":
                self.follow_handler.handle(event)
            case "message":
                self.message_handler.handle(event)
            case "postback":
                self.postback_handler.handle(event)
            case "unfollow":
                self.unfollow_handler.handle(event)
            case _:
                logger.warning(f"Unknown Event : {event_type}")
