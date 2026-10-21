"""
ALICE_Core Publisher
成果物の外部通知・配信を管理するプラグイン対応パブリッシャーハブ。
将来の Webhook / メールなど、任意の通知アダプタを外付け可能。
"""
import logging
from typing import Any, Protocol
from pathlib import Path
import config

logger = logging.getLogger(__name__)


class PublisherAdapter(Protocol):
    def publish(
        self,
        filepath: str,
        user_id: str,
        module_name: str = "transcript",
        extra_files: dict[str, str] | None = None,
    ) -> None:
        ...

    def notify_failure(self, user_id: str, message: str) -> bool:
        ...


class DummyLinePublisher:
    """No-op fallback for legacy tests expecting line_publisher"""
    def publish(self, *args, **kwargs):
        pass
    def notify_failure(self, *args, **kwargs):
        return False


class Publisher:
    """成果物およびエラーの外部通知を束ねるパブリッシャーファサード"""

    def __init__(self, adapters: list[Any] | None = None):
        self._line_publisher = DummyLinePublisher()
        self.adapters: list[Any] = adapters if adapters is not None else []

    @property
    def line_publisher(self) -> Any:
        return self._line_publisher

    @line_publisher.setter
    def line_publisher(self, val: Any) -> None:
        self._line_publisher = val
        if val not in self.adapters:
            self.adapters.append(val)

    def register_adapter(self, adapter: Any) -> None:
        """新しい通知アダプタ（Webhook等）を登録"""
        if adapter not in self.adapters:
            self.adapters.append(adapter)

    def publish(
        self,
        filepath: str,
        user_id: str,
        module_name: str = "transcript",
        extra_files: dict[str, str] | None = None,
    ) -> None:
        """登録された全アダプタへ成果物通知を配信"""
        logger.info(
            f"[Publisher] Publish request : {filepath} "
            f"(module={module_name}, user={user_id}, extra_files={list((extra_files or {}).keys())})"
        )
        for adapter in self.adapters:
            try:
                adapter.publish(filepath, user_id, module_name=module_name, extra_files=extra_files)
            except Exception as e:
                logger.error(f"[Publisher] Error publishing via adapter {adapter.__class__.__name__}: {e}")

    def notify_failure(self, job_or_user_id: Any, message: str) -> None:
        """ユーザーへの処理失敗・エラー通知を登録された全アダプタへ配信"""
        user_id = getattr(job_or_user_id, "user_id", str(job_or_user_id))
        for adapter in self.adapters:
            try:
                if hasattr(adapter, "notify_failure"):
                    adapter.notify_failure(user_id, message)
            except Exception as e:
                logger.warning(f"[Publisher] Error notifying failure via adapter {adapter.__class__.__name__}: {e}")
