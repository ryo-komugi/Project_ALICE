import sqlite3
from pathlib import Path
import pytest
from ALICE_Search.core.schema import init_db, get_connection
from ALICE_Search.core.searcher import Searcher
from ALICE_Search.models.query import SearchQuery


def test_searcher_multi_user_filter(tmp_path):
    db_path = tmp_path / "test_user_filter.db"
    conn = get_connection(db_path)
    init_db(conn)

    ws_path = str(tmp_path)
    # Insert dummy jobs
    conn.execute(
        """
        INSERT INTO jobs_metadata (job_id, user_id, status, workflow, original_filename, workspace_path, created_at)
        VALUES 
            ('job_owner', 'U_OWNER', 'COMPLETED', '["transcript"]', 'owner_file.mp3', ?, '2026-09-13T10:00:00'),
            ('job_alias', 'U_ALIAS', 'COMPLETED', '["transcript"]', 'alias_file.mp3', ?, '2026-09-13T10:00:00'),
            ('job_guest', 'U_GUEST', 'COMPLETED', '["transcript"]', 'guest_file.mp3', ?, '2026-09-13T10:00:00')
        """,
        (ws_path, ws_path, ws_path),
    )
    # Insert FTS artifacts
    conn.execute(
        """
        INSERT INTO artifacts_fts (job_id, module, artifact_name, artifact_rel_path, content)
        VALUES 
            ('job_owner', 'transcript', 'transcript.txt', 'transcript/transcript.txt', '重要な秘密の計画会議です'),
            ('job_alias', 'transcript', 'transcript.txt', 'transcript/transcript.txt', 'サブ端末からの計画メモです'),
            ('job_guest', 'transcript', 'transcript.txt', 'transcript/transcript.txt', 'ゲストの計画相談です')
        """
    )
    conn.commit()
    conn.close()

    searcher = Searcher(db_path=db_path)

    # 1. Single owner user filter
    res_single = searcher.search(SearchQuery(query="計画", user_id="U_OWNER"))
    assert res_single.total == 1
    assert res_single.hits[0].job_id == "job_owner"

    # 2. Comma-separated multi-user filter (owner + alias)
    res_multi = searcher.search(SearchQuery(query="計画", user_id="U_OWNER, U_ALIAS"))
    assert res_multi.total == 2
    job_ids = {h.job_id for h in res_multi.hits}
    assert job_ids == {"job_owner", "job_alias"}

    # 3. Guest user filter should NOT see owner jobs
    res_guest = searcher.search(SearchQuery(query="計画", user_id="U_GUEST"))
    assert res_guest.total == 1
    assert res_guest.hits[0].job_id == "job_guest"

    # 4. Unknown user returns 0 hits
    res_unknown = searcher.search(SearchQuery(query="計画", user_id="U_UNKNOWN"))
    assert res_unknown.total == 0
