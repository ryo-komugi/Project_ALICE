import sqlite3
from pathlib import Path
import config


def get_db_path() -> Path:
    return getattr(config, "DB_PATH", Path("/data/runtime/copilot/database/conversations.db"))


def _connect_db() -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode and busy timeout."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def initialize_database():
    with _connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        conn.commit()


def save_message(timestamp: str, channel_id: str, user_id: str | None, role: str, content: str):
    try:
        with _connect_db() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    timestamp,
                    channel_id,
                    user_id,
                    role,
                    content
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    channel_id,
                    user_id,
                    role,
                    content,
                ),
            )
            conn.commit()
    except sqlite3.OperationalError:
        # Table might not exist yet; auto-initialize and retry once
        initialize_database()
        with _connect_db() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    timestamp,
                    channel_id,
                    user_id,
                    role,
                    content
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    channel_id,
                    user_id,
                    role,
                    content,
                ),
            )
            conn.commit()


def get_recent_messages(channel_id: str, limit: int = 10):
    try:
        with _connect_db() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE channel_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (channel_id, limit),
            ).fetchall()
        return list(reversed(rows))
    except sqlite3.OperationalError:
        initialize_database()
        return []