"""ALICE_Search インデクサー

Workspace 内のメタデータ (job.json) および対象成果物 (summary.txt, transcript.txt等) を
SQLite + FTS5 派生インデックスに登録・更新する。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
import sqlite3

from ..config import TARGET_ARTIFACTS
from .schema import get_connection, init_db

logger = logging.getLogger(__name__)


def index_workspace(workspace_dir: Path, conn: sqlite3.Connection) -> bool:
    """単一 Workspace をインデックスに登録・更新 (UPSERT) する

    Args:
        workspace_dir: 対象 Workspace のディレクトリパス
        conn: SQLite 接続

    Returns:
        bool: 成功した場合 True
    """
    workspace_dir = Path(workspace_dir).resolve()
    if not workspace_dir.exists() or not workspace_dir.is_dir():
        logger.error(f"[ALICE_Search] Workspace directory not found: {workspace_dir}")
        return False

    job_json_path = workspace_dir / "job.json"
    if not job_json_path.exists():
        logger.warning(f"[ALICE_Search] job.json not found in {workspace_dir}. Skipping.")
        return False

    try:
        with open(job_json_path, "r", encoding="utf-8") as f:
            job_data = json.load(f)
    except Exception as e:
        logger.error(f"[ALICE_Search] Failed to read job.json at {job_json_path}: {e}")
        return False

    job_id = job_data.get("job_id", workspace_dir.name)
    user_id = job_data.get("user_id", "unknown")
    status = job_data.get("status", "UNKNOWN")
    workflow = json.dumps(job_data.get("workflow", []))
    input_meta = job_data.get("input_metadata", {})
    original_filename = input_meta.get("original_name") if isinstance(input_meta, dict) else None
    created_at = job_data.get("created_at", datetime.now().isoformat())
    completed_at = job_data.get("completed_at")

    # 成果物の存在確認とテキスト読み込み
    artifacts_to_index = []
    has_transcript = 0
    has_summary = 0
    has_minutes = 0

    for module, filenames in TARGET_ARTIFACTS.items():
        module_dir = workspace_dir / module
        for fname in filenames:
            fpath = module_dir / fname
            if fpath.exists() and fpath.is_file():
                if module == "transcript":
                    has_transcript = 1
                elif module == "summary":
                    has_summary = 1
                elif module == "minutes":
                    has_minutes = 1

                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace").strip()
                    if content:
                        rel_path = f"{module}/{fname}"
                        artifacts_to_index.append((job_id, module, fname, rel_path, content))
                except Exception as e:
                    logger.warning(f"[ALICE_Search] Failed to read {fpath}: {e}")

    try:
        with conn:
            # 1. jobs_metadata の UPSERT
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs_metadata (
                    job_id, user_id, status, workflow, original_filename,
                    workspace_path, created_at, completed_at,
                    has_transcript, has_summary, has_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    user_id,
                    status,
                    workflow,
                    original_filename,
                    str(workspace_dir),
                    created_at,
                    completed_at,
                    has_transcript,
                    has_summary,
                    has_minutes,
                ),
            )

            # 2. artifacts_fts の既存レコード削除 & 再挿入
            conn.execute("DELETE FROM artifacts_fts WHERE job_id = ?;", (job_id,))
            if artifacts_to_index:
                conn.executemany(
                    """
                    INSERT INTO artifacts_fts (
                        job_id, module, artifact_name, artifact_rel_path, content
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    artifacts_to_index,
                )

        logger.info(f"[ALICE_Search] Indexed workspace successfully: {job_id} ({len(artifacts_to_index)} artifacts)")
        return True
    except Exception as e:
        logger.error(f"[ALICE_Search] DB error during indexing {job_id}: {e}")
        return False


def reindex_all(workspaces_dir: Path, db_path: Path) -> tuple[int, int]:
    """すべての Workspace を走査し、派生インデックスを完全再構築する

    Args:
        workspaces_dir: Workspaces ルートディレクトリ
        db_path: データベースファイルパス

    Returns:
        tuple[int, int]: (成功件数, 失敗件数)
    """
    workspaces_dir = Path(workspaces_dir).resolve()
    if not workspaces_dir.exists() or not workspaces_dir.is_dir():
        logger.error(f"[ALICE_Search] Workspaces root not found: {workspaces_dir}")
        return (0, 0)

    conn = get_connection(db_path)
    init_db(conn)

    # 派生キャッシュをクリア
    with conn:
        conn.execute("DELETE FROM jobs_metadata;")
        conn.execute("DELETE FROM artifacts_fts;")

    success_count = 0
    failure_count = 0

    # ワークスペースディレクトリをソートして順次処理
    ws_dirs = sorted([d for d in workspaces_dir.iterdir() if d.is_dir() and (d / "job.json").exists()])
    logger.info(f"[ALICE_Search] Starting reindex for {len(ws_dirs)} workspaces...")

    for ws_dir in ws_dirs:
        ok = index_workspace(ws_dir, conn)
        if ok:
            success_count += 1
        else:
            failure_count += 1

    conn.close()
    logger.info(f"[ALICE_Search] Reindex complete. Success: {success_count}, Failed: {failure_count}")
    return (success_count, failure_count)
