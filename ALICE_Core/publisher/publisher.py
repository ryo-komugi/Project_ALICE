import logging
from publisher.line_publisher import LinePublisher

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self):
        self.line_publisher = LinePublisher()

    def publish(self, filepath, user_id, module_name: str = "transcript", extra_files: dict[str, str] | None = None) -> None:
        print("publisher")
        logger.info(f"[Publisher] Publish request : {filepath} (module={module_name}, extra_files={list((extra_files or {}).keys())})")

        # Phase1ではLINEのみ
        self.line_publisher.publish(filepath, user_id, module_name=module_name, extra_files=extra_files)