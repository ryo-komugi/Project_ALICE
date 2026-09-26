import logging

logger = logging.getLogger(__name__)


class PostbackHandler:
    def handle(self, event: dict) -> None:
        logger.info("Postback Handler")
