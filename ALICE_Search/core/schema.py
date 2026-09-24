"""ALICE_Search データベーススキーマ定義

SQLite (B-Tree) と FTS5 (trigram 転置インデックス) を用いた派生キャッシュ設計。
"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- 1. Job メタデータテーブル (B-Tree 属性検索用)
CREATE TABLE IF NOT EXISTS jobs_metadata (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL,
    workflow TEXT NOT NULL,
    original_filename TEXT,
    workspace_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    has_transcript INTEGER DEFAULT 0,
    has_summary INTEGER DEFAULT 0,
    has_minutes INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs_metadata(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs_metadata(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs_metadata(status);

-- 2. 成果物全文検索仮想テーブル (FTS5 trigram)
-- content のみを trigram トークナイズ対象とし、参照用メタ列は UNINDEXED とする
CREATE VIRTUAL TABLE IF NOT EXISTS artifacts_fts USING fts5(
    job_id UNINDEXED,
    module UNINDEXED,
    artifact_name UNINDEXED,
    artifact_rel_path UNINDEXED,
    content,
    tokenize = 'trigram'
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """SQLite データベース接続を取得し、WAL モードと外部キー制約を有効化する"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """スキーマを適用してテーブルとインデックスを作成する"""
    conn.executescript(SCHEMA_SQL)
    conn.commit()
