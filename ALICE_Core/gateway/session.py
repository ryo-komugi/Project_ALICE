from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import threading

logger = logging.getLogger(__name__)


@dataclass
class Session:
    user_id: str
    state: str = "IDLE"  # IDLE, WAIT_FILE
    workflow: str | None = None
    updated_at: datetime = datetime.now()
    last_file_at: datetime | None = None
    file_count: int = 0


class SessionManager:
    def __init__(self, default_burst_seconds: float = 5.0):
        self.sessions: dict[str, Session] = {}
        self.timers: dict[str, threading.Timer] = {}
        self.lock = threading.Lock()
        self.default_burst_seconds = default_burst_seconds

    def _get_locked(self, user_id: str) -> Session:
        if user_id not in self.sessions:
            self.sessions[user_id] = Session(user_id=user_id)
        return self.sessions[user_id]

    def get(self, user_id: str) -> Session:
        with self.lock:
            return self._get_locked(user_id)

    def _cancel_timer_locked(self, user_id: str):
        if user_id in self.timers:
            try:
                self.timers[user_id].cancel()
            except Exception:
                pass
            del self.timers[user_id]

    def cancel_burst_timer(self, user_id: str):
        with self.lock:
            self._cancel_timer_locked(user_id)

    def set_wait_file(self, user_id: str, workflow: str):
        with self.lock:
            self._cancel_timer_locked(user_id)
            session = self._get_locked(user_id)
            session.state = "WAIT_FILE"
            session.workflow = workflow
            session.updated_at = datetime.now()
            session.last_file_at = None
            session.file_count = 0

    def reset(self, user_id: str):
        with self.lock:
            self._cancel_timer_locked(user_id)
            session = self._get_locked(user_id)
            session.state = "IDLE"
            session.workflow = None
            session.updated_at = datetime.now()
            session.last_file_at = None
            session.file_count = 0

    def can_accept_file(
        self,
        user_id: str,
        burst_seconds: float | None = None,
        wait_timeout_seconds: float = 300.0,
    ) -> bool:
        """
        受信可能かを判定。
        1. WAIT_FILE 状態であること。
        2. すでにファイル受信済み(last_file_atあり)の場合は burst_seconds(デフォルト5秒)以内であること。
        3. まだ1件も受信していない場合は wait_timeout_seconds(デフォルト300秒)以内であること。
        """
        if burst_seconds is None:
            burst_seconds = self.default_burst_seconds

        with self.lock:
            session = self._get_locked(user_id)
            if session.state != "WAIT_FILE":
                return False

            now = datetime.now()
            if session.last_file_at is not None:
                if now - session.last_file_at > timedelta(seconds=burst_seconds):
                    return False
                return True

            if now - session.updated_at > timedelta(seconds=wait_timeout_seconds):
                return False

            return True

    def is_in_burst(self, user_id: str, burst_seconds: float | None = None) -> bool:
        """1件以上のファイル受信後のバースト受付ウィンドウ内かを判定"""
        if burst_seconds is None:
            burst_seconds = self.default_burst_seconds

        with self.lock:
            session = self._get_locked(user_id)
            if session.state != "WAIT_FILE" or session.last_file_at is None:
                return False
            return (datetime.now() - session.last_file_at) <= timedelta(seconds=burst_seconds)

    def touch_file(self, user_id: str):
        with self.lock:
            session = self._get_locked(user_id)
            session.last_file_at = datetime.now()
            session.file_count += 1

    def record_file_received(
        self,
        user_id: str,
        on_burst_end=None,
        burst_seconds: float | None = None,
    ):
        """
        ファイル受信を記録し、バースト受付終了タイマーをスケジュールする。
        追加のファイルが来ないまま burst_seconds が経過したら reset(user_id) し、on_burst_end(user_id) を呼ぶ。
        """
        if burst_seconds is None:
            burst_seconds = self.default_burst_seconds

        with self.lock:
            session = self._get_locked(user_id)
            session.last_file_at = datetime.now()
            session.file_count += 1
            self._cancel_timer_locked(user_id)

            if burst_seconds <= 0:
                self.reset(user_id)
                if on_burst_end:
                    try:
                        on_burst_end(user_id)
                    except Exception as e:
                        logger.warning(f"[SessionManager] on_burst_end callback error: {e}")
                return

            def _expiry():
                logger.info(f"[SessionManager] Burst window ({burst_seconds}s) ended for {user_id}. Resetting session to IDLE.")
                self.reset(user_id)
                if on_burst_end:
                    try:
                        on_burst_end(user_id)
                    except Exception as e:
                        logger.warning(f"[SessionManager] on_burst_end callback error: {e}")

            timer = threading.Timer(burst_seconds, _expiry)
            timer.daemon = True
            self.timers[user_id] = timer
            timer.start()
