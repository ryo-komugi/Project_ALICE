"""ALICE_Search 検索実行エンジン

Full Text Query (FTS5 trigram) と Metadata Filters (B-Tree) を
組み合わせたハイブリッド検索を実行し、正本 Artifact への参照を解決する。
"""

import logging
import re
from datetime import datetime
from pathlib import Path
import sqlite3

from ..models.query import SearchQuery
from ..models.result import SearchHit, SearchResult
from .schema import get_connection

logger = logging.getLogger(__name__)


def _generate_snippet(text: str, query: str, max_chars: int = 80) -> str:
    """テキスト中から query の出現箇所を見つけ、前後にハイライト <b>...</b> を付与したスニペットを生成する"""
    if not text or not query:
        return text[:max_chars] if text else ""

    idx = text.lower().find(query.lower())
    if idx == -1:
        snippet = text[:max_chars]
        return snippet + "..." if len(text) > max_chars else snippet

    start = max(0, idx - 20)
    end = min(len(text), idx + len(query) + 40)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""

    match_str = text[idx : idx + len(query)]
    highlighted = f"{prefix}{text[start:idx]}<b>{match_str}</b>{text[idx + len(query):end]}{suffix}"
    return highlighted


class Searcher:
    """ALICE_Search 検索エンジン"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).resolve()

    def search(self, query: SearchQuery) -> SearchResult:
        """SearchQuery に基づいて検索を実行する"""
        if not self.db_path.exists():
            logger.warning(f"[ALICE_Search] Database not found at {self.db_path}")
            return SearchResult(total=0, query=query.query, filters={}, hits=[])

        conn = get_connection(self.db_path)
        try:
            return self._execute_search(conn, query)
        finally:
            conn.close()

    def _execute_search(self, conn: sqlite3.Connection, q: SearchQuery) -> SearchResult:
        raw_query = q.query.strip() if q.query and q.query.strip() else None

        # 1. 検索戦略の決定
        # - 文字列なし: メタデータフィルター検索
        # - 1〜2文字: trigram の MATCH は動かないため、FTS5 の高速 LIKE '%...%' を使用
        # - 3文字以上: FTS5 MATCH (フレーズ検索) を使用し、例外時は LIKE へフォールバック
        use_fts_match = False
        use_like = False
        match_phrase = ""

        if raw_query:
            words = [w.strip() for w in raw_query.split() if w.strip()]
            if not words or any(len(w) < 3 for w in words):
                # 3文字未満の単語を含む場合は LIKE 検索または混合対応
                if len(words) == 1 and len(words[0]) < 3:
                    use_like = True
                else:
                    use_fts_match = True
                    tokens = [f'"{w.replace(chr(34), chr(34)+chr(34))}"' for w in words]
                    match_phrase = " ".join(tokens)
            else:
                use_fts_match = True
                tokens = [f'"{w.replace(chr(34), chr(34)+chr(34))}"' for w in words]
                match_phrase = " ".join(tokens)

        # 2. SQL 句の組み立て
        where_clauses: list[str] = []
        params: list = []

        if use_fts_match:
            where_clauses.append("artifacts_fts MATCH ?")
            params.append(match_phrase)
        elif use_like:
            where_clauses.append("f.content LIKE ?")
            params.append(f"%{raw_query}%")

        # Metadata Filters の付与
        if q.user_id:
            uids = [u.strip() for u in q.user_id.split(",") if u.strip()]
            if len(uids) == 1:
                where_clauses.append("m.user_id = ?")
                params.append(uids[0])
            elif len(uids) > 1:
                placeholders = ",".join("?" for _ in uids)
                where_clauses.append(f"m.user_id IN ({placeholders})")
                params.extend(uids)

        if q.status:
            where_clauses.append("m.status = ?")
            params.append(q.status)

        if q.workflow:
            where_clauses.append("m.workflow LIKE ?")
            params.append(f"%{q.workflow}%")

        modules = q.get_modules()
        if modules:
            placeholders = ",".join("?" for _ in modules)
            where_clauses.append(f"f.module IN ({placeholders})")
            params.extend(modules)

        if q.date_from:
            where_clauses.append("m.created_at >= ?")
            params.append(q.date_from.isoformat())

        if q.date_to:
            where_clauses.append("m.created_at <= ?")
            params.append(q.date_to.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # 3. カウント用クエリ
        if raw_query:
            count_sql = f"""
                SELECT COUNT(*) FROM artifacts_fts f
                JOIN jobs_metadata m ON f.job_id = m.job_id
                WHERE {where_sql}
            """
        else:
            # クエリなしの場合は jobs_metadata または 成果物単位で取得
            count_sql = f"""
                SELECT COUNT(*) FROM artifacts_fts f
                JOIN jobs_metadata m ON f.job_id = m.job_id
                WHERE {where_sql}
            """

        # 4. 検索結果取得用クエリ
        if use_fts_match:
            select_sql = f"""
                SELECT
                    f.job_id,
                    f.module,
                    f.artifact_name,
                    f.artifact_rel_path,
                    snippet(artifacts_fts, 4, '<b>', '</b>', '...', 20) AS snippet,
                    bm25(artifacts_fts) AS rank_score,
                    f.content,
                    m.user_id,
                    m.status,
                    m.workflow,
                    m.original_filename,
                    m.workspace_path,
                    m.created_at
                FROM artifacts_fts f
                JOIN jobs_metadata m ON f.job_id = m.job_id
                WHERE {where_sql}
                ORDER BY rank_score ASC, m.created_at DESC
                LIMIT ? OFFSET ?
            """
        else:
            select_sql = f"""
                SELECT
                    f.job_id,
                    f.module,
                    f.artifact_name,
                    f.artifact_rel_path,
                    f.content,
                    0.0 AS rank_score,
                    m.user_id,
                    m.status,
                    m.workflow,
                    m.original_filename,
                    m.workspace_path,
                    m.created_at
                FROM artifacts_fts f
                JOIN jobs_metadata m ON f.job_id = m.job_id
                WHERE {where_sql}
                ORDER BY m.created_at DESC
                LIMIT ? OFFSET ?
            """

        query_params = list(params)
        query_params.extend([q.limit, q.offset])

        # 実行
        try:
            total = conn.execute(count_sql, params).fetchone()[0]
            cursor = conn.execute(select_sql, query_params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError as e:
            # もし MATCH 構文等でエラーが出た場合は LIKE で再試行（フォールバック）
            if use_fts_match:
                logger.warning(f"[ALICE_Search] FTS MATCH failed ({e}), falling back to LIKE")
                q_copy = SearchQuery(
                    query=raw_query,
                    user_id=q.user_id,
                    date_from=q.date_from,
                    date_to=q.date_to,
                    workflow=q.workflow,
                    status=q.status,
                    module=q.module,
                    limit=q.limit,
                    offset=q.offset,
                )
                # 強制的に 2 文字扱いにして LIKE で検索
                return self._execute_fallback_like(conn, q_copy)
            raise

        hits: list[SearchHit] = []
        for r in rows:
            ws_path = Path(r["workspace_path"])
            rel_path = r["artifact_rel_path"]
            abs_path = ws_path / rel_path

            # スニペット処理
            if use_fts_match and "snippet" in r.keys() and r["snippet"]:
                snippet = r["snippet"]
            else:
                snippet = _generate_snippet(r["content"], raw_query or "")

            meta = {
                "status": r["status"],
                "original_filename": r["original_filename"],
                "workflow": r["workflow"],
            }

            hit = SearchHit(
                job_id=r["job_id"],
                user_id=r["user_id"],
                module=r["module"],
                artifact_name=r["artifact_name"],
                artifact_rel_path=rel_path,
                workspace_dir=str(ws_path),
                artifact_abs_path=str(abs_path),
                snippet=snippet,
                rank_score=float(r["rank_score"]),
                created_at=r["created_at"],
                metadata=meta,
            )
            hits.append(hit)

        applied_filters = {
            k: v
            for k, v in {
                "user_id": q.user_id,
                "workflow": q.workflow,
                "status": q.status,
                "module": modules,
                "date_from": q.date_from.isoformat() if q.date_from else None,
                "date_to": q.date_to.isoformat() if q.date_to else None,
            }.items()
            if v is not None
        }

        return SearchResult(
            total=total,
            query=raw_query,
            filters=applied_filters,
            hits=hits,
        )

    def _execute_fallback_like(self, conn: sqlite3.Connection, q: SearchQuery) -> SearchResult:
        """FTS MATCH 構文例外時の LIKE 検索フォールバック"""
        raw_query = q.query.strip() if q.query else ""
        where_clauses = ["f.content LIKE ?"]
        params = [f"%{raw_query}%"]

        if q.user_id:
            uids = [u.strip() for u in q.user_id.split(",") if u.strip()]
            if len(uids) == 1:
                where_clauses.append("m.user_id = ?")
                params.append(uids[0])
            elif len(uids) > 1:
                placeholders = ",".join("?" for _ in uids)
                where_clauses.append(f"m.user_id IN ({placeholders})")
                params.extend(uids)
        if q.status:
            where_clauses.append("m.status = ?")
            params.append(q.status)
        modules = q.get_modules()
        if modules:
            placeholders = ",".join("?" for _ in modules)
            where_clauses.append(f"f.module IN ({placeholders})")
            params.extend(modules)

        where_sql = " AND ".join(where_clauses)
        count_sql = f"SELECT COUNT(*) FROM artifacts_fts f JOIN jobs_metadata m ON f.job_id = m.job_id WHERE {where_sql}"
        select_sql = f"""
            SELECT
                f.job_id, f.module, f.artifact_name, f.artifact_rel_path, f.content,
                0.0 AS rank_score, m.user_id, m.status, m.workflow, m.original_filename,
                m.workspace_path, m.created_at
            FROM artifacts_fts f
            JOIN jobs_metadata m ON f.job_id = m.job_id
            WHERE {where_sql}
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
        """
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = conn.execute(select_sql, params + [q.limit, q.offset]).fetchall()

        hits = []
        for r in rows:
            ws_path = Path(r["workspace_path"])
            rel_path = r["artifact_rel_path"]
            hits.append(
                SearchHit(
                    job_id=r["job_id"],
                    user_id=r["user_id"],
                    module=r["module"],
                    artifact_name=r["artifact_name"],
                    artifact_rel_path=rel_path,
                    workspace_dir=str(ws_path),
                    artifact_abs_path=str(ws_path / rel_path),
                    snippet=_generate_snippet(r["content"], raw_query),
                    rank_score=0.0,
                    created_at=r["created_at"],
                    metadata={"status": r["status"], "original_filename": r["original_filename"]},
                )
            )
        return SearchResult(total=total, query=raw_query, filters={"fallback": True}, hits=hits)
