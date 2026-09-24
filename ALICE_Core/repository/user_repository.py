import sqlite3
import logging

from auth.user import User
from auth.user_status import UserStatus

logger = logging.getLogger(__name__)

class UserRepository:

    def __init__(self):
        self.connection = sqlite3.connect(
            "database/users.db",
            timeout=10.0,
            check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL;")
        self.connection.execute("PRAGMA busy_timeout = 5000;")
        self.connection.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """)
        self.connection.commit()

    def find(self, user_id: str) -> User | None:
        logger.info(f"[UserRepository] Find : {user_id}")
        cursor = self.connection.execute(
            """
            SELECT user_id, display_name, status
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        row = cursor.fetchone()

        if row is None:
            logger.info("[UserRepository] User not found")
            return None
        else:
            logger.info(f"[UserRepository] Found : {row['status']}")

        return User(
            user_id=row["user_id"],
            display_name=row["display_name"],
            status=UserStatus(row["status"])
        )

    def get_all(self) -> list[User]:
        cursor = self.connection.execute(
            """
            SELECT user_id, display_name, status
            FROM users
            ORDER BY rowid ASC
            """
        )
        rows = cursor.fetchall()
        users = []
        for row in rows:
            try:
                st = UserStatus(row["status"])
            except ValueError:
                st = UserStatus.WAIT_INVITE_CODE
            users.append(User(
                user_id=row["user_id"],
                display_name=row["display_name"],
                status=st
            ))
        return users

    def create(self, user: User) -> None:
        self.connection.execute(
            """
            INSERT INTO users(user_id, display_name, status)
            VALUES (?, ?, ?)
            """,
            (
                user.user_id,
                user.display_name,
                user.status.value
            )
        )
        self.connection.commit()

    def update(self, user_id: str, display_name: str, status: UserStatus) -> None:
        logger.info(f"[UserRepository] Update user : {user_id} -> {display_name}, {status.value}")
        self.connection.execute(
            """
            UPDATE users
            SET display_name = ?, status = ?
            WHERE user_id = ?
            """,
            (
                display_name,
                status.value,
                user_id
            )
        )
        self.connection.commit()

    def update_status(self, user_id: str, status: UserStatus) -> None:
        logger.info(f"[UserRepository] Update status : {user_id} -> {status.value}")
        self.connection.execute(
            """
            UPDATE users
            SET status = ?
            WHERE user_id = ?
            """,
            (
                status.value,
                user_id
            )
        )
        self.connection.commit()

    def delete(self, user_id: str) -> None:
        logger.info(f"[UserRepository] Delete user : {user_id}")
        self.connection.execute(
            """
            DELETE FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )
        self.connection.commit()
