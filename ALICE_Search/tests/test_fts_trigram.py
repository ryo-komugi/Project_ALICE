"""ALICE_Search FTS5 trigram 網羅的検証テスト

要件検証項目:
1. 日本語検索
2. 2文字以下の検索 (trigram 仕様の補正)
3. 部分一致
4. 英数字
5. 記号を含む文字列 (GPT-4, v1.0 等)
6. 固有名詞 (人名・社名)
7. 技術用語
8. ノイズ / 偽陽性の排除
9. BM25 ランキングスコア
"""

import shutil
import tempfile
from pathlib import Path
import pytest

from ALICE_Search.core.indexer import index_workspace
from ALICE_Search.core.schema import get_connection, init_db
from ALICE_Search.core.searcher import Searcher
from ALICE_Search.models.query import SearchQuery


@pytest.fixture
def test_env():
    """一時ディレクトリとテスト用DB、ダミーWorkspaceを準備するフィクスチャ"""
    temp_dir = Path(tempfile.mkdtemp(prefix="alice_fts_test_"))
    db_path = temp_dir / "test_search.db"
    conn = get_connection(db_path)
    init_db(conn)

    def create_dummy_job(job_id: str, summary_text: str = "", transcript_text: str = "", user_id: str = "user_001"):
        ws_dir = temp_dir / job_id
        ws_dir.mkdir(parents=True, exist_ok=True)

        job_json = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "COMPLETED",
            "workflow": ["transcript", "summary"],
            "created_at": "2026-09-11T12:00:00",
            "input_metadata": {"original_name": f"{job_id}.mp3"},
        }
        import json
        (ws_dir / "job.json").write_text(json.dumps(job_json), encoding="utf-8")

        if summary_text:
            s_dir = ws_dir / "summary"
            s_dir.mkdir(parents=True, exist_ok=True)
            (s_dir / "summary.txt").write_text(summary_text, encoding="utf-8")

        if transcript_text:
            t_dir = ws_dir / "transcript"
            t_dir.mkdir(parents=True, exist_ok=True)
            (t_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")

        index_workspace(ws_dir, conn)
        return ws_dir

    yield {"temp_dir": temp_dir, "db_path": db_path, "conn": conn, "create_job": create_dummy_job}

    conn.close()
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_1_japanese_and_conjugations(test_env):
    """1. 日本語および語尾変化・助詞の検索"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job(
        "job_jp_01",
        summary_text="本日のミーティングでは、プロジェクト方針についてメンバー全員で深く話し合いました。",
    )

    # 活用形の一部「話し合い」や部分「話し合」
    res1 = searcher.search(SearchQuery(query="話し合い"))
    # trigram では「話し合」が含まれていればヒットする
    res2 = searcher.search(SearchQuery(query="話し合いました"))
    assert res2.total >= 1
    assert res2.hits[0].job_id == "job_jp_01"
    assert "<b>話し合いました</b>" in res2.hits[0].snippet


def test_2_short_words_two_chars_or_less(test_env):
    """2. 2文字以下の検索 (trigram 仕様補正の検証)"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job(
        "job_short_01",
        summary_text="来期の予算配分について、AIサーバーの拡充を優先することで合意した。",
        transcript_text="予算の件ですが、1億円の枠を確保しています。",
    )

    # 2文字「予算」
    res_yosan = searcher.search(SearchQuery(query="予算"))
    assert res_yosan.total == 2, f"Expected 2 hits for '予算', got {res_yosan.total}"
    assert all("<b>予算</b>" in h.snippet for h in res_yosan.hits)

    # 2文字「AI」
    res_ai = searcher.search(SearchQuery(query="AI"))
    assert res_ai.total >= 1
    assert any("<b>AI</b>" in h.snippet for h in res_ai.hits)

    # 1文字「円」
    res_yen = searcher.search(SearchQuery(query="円"))
    assert res_yen.total >= 1
    assert any("<b>円</b>" in h.snippet for h in res_yen.hits)


def test_3_substring_matching(test_env):
    """3. 部分一致の検証"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job("job_sub_01", summary_text="クラウドセキュリティのガバナンス体制を強化する。")

    res = searcher.search(SearchQuery(query="セキュリティ"))
    assert res.total == 1
    assert res.hits[0].job_id == "job_sub_01"
    assert "<b>セキュリティ</b>" in res.hits[0].snippet


def test_4_alphanumeric_and_symbols(test_env):
    """4. 英数字および記号を含む文字列 (GPT-4o, v1.0 等)"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job(
        "job_symbol_01",
        summary_text="モデルを GPT-4o にアップグレードし、ALICE v1.0 の安定版をリリースした。",
    )

    # ハイフン付き
    res_gpt = searcher.search(SearchQuery(query="GPT-4o"))
    assert res_gpt.total == 1
    assert res_gpt.hits[0].job_id == "job_symbol_01"

    # ドット付き
    res_v1 = searcher.search(SearchQuery(query="v1.0"))
    assert res_v1.total == 1
    assert res_v1.hits[0].job_id == "job_symbol_01"


def test_5_proper_nouns(test_env):
    """5. 固有名詞 (人名・企業名)"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job("job_noun_01", transcript_text="田中さんと佐藤さんが新体制のリーダーに就任しました。")

    res_tanaka = searcher.search(SearchQuery(query="田中"))
    assert res_tanaka.total == 1
    assert "<b>田中</b>" in res_tanaka.hits[0].snippet

    res_sato = searcher.search(SearchQuery(query="佐藤"))
    assert res_sato.total == 1
    assert "<b>佐藤</b>" in res_sato.hits[0].snippet


def test_6_technical_terms(test_env):
    """6. 技術用語"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job("job_tech_01", summary_text="SQLite の FTS5 転置インデックスを用いた全文検索アーキテクチャ。")

    res = searcher.search(SearchQuery(query="転置インデックス"))
    assert res.total == 1
    assert "<b>転置インデックス</b>" in res.hits[0].snippet


def test_7_precision_and_noise_exclusion(test_env):
    """7. ノイズ・偽陽性の排除 (存在しない単語は 0 件)"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    create_job("job_clean_01", summary_text="通常の社内定例ミーティングの記録です。")

    res = searcher.search(SearchQuery(query="量子コンピュータ宇宙船"))
    assert res.total == 0
    assert len(res.hits) == 0


def test_8_bm25_ranking(test_env):
    """8. BM25 ランキングスコア (キーワード出現頻度・適合度の順序)"""
    create_job = test_env["create_job"]
    searcher = Searcher(db_path=test_env["db_path"])

    # キーワードが複数回登場するドキュメント
    create_job(
        "job_high_freq",
        summary_text="データベースの設計。データベースのチューニングとデータベースのバックアップについて協議。",
    )
    # キーワードが1回だけ登場するドキュメント
    create_job(
        "job_low_freq",
        summary_text="新機能のUI改善案について議論。なおデータベースの確認も行った。",
    )

    res = searcher.search(SearchQuery(query="データベース"))
    assert res.total == 2
    # 出現頻度が高い job_high_freq が先頭に来る (BM25 スコアがより負に大きい)
    assert res.hits[0].job_id == "job_high_freq"
    assert res.hits[1].job_id == "job_low_freq"
    assert res.hits[0].rank_score < res.hits[1].rank_score


def main():
    print("=== Running test_fts_trigram.py ===")
    temp_dir = Path(tempfile.mkdtemp(prefix="alice_fts_run_"))
    try:
        db_path = temp_dir / "test_search.db"
        conn = get_connection(db_path)
        init_db(conn)

        def create_dummy_job(job_id: str, summary_text: str = "", transcript_text: str = "", user_id: str = "user_001"):
            ws_dir = temp_dir / job_id
            ws_dir.mkdir(parents=True, exist_ok=True)
            job_json = {
                "job_id": job_id,
                "user_id": user_id,
                "status": "COMPLETED",
                "workflow": ["transcript", "summary"],
                "created_at": "2026-09-11T12:00:00",
                "input_metadata": {"original_name": f"{job_id}.mp3"},
            }
            import json
            (ws_dir / "job.json").write_text(json.dumps(job_json), encoding="utf-8")
            if summary_text:
                s_dir = ws_dir / "summary"
                s_dir.mkdir(parents=True, exist_ok=True)
                (s_dir / "summary.txt").write_text(summary_text, encoding="utf-8")
            if transcript_text:
                t_dir = ws_dir / "transcript"
                t_dir.mkdir(parents=True, exist_ok=True)
                (t_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")
            index_workspace(ws_dir, conn)
            return ws_dir

        env = {"temp_dir": temp_dir, "db_path": db_path, "conn": conn, "create_job": create_dummy_job}

        tests = [
            ("test_1_japanese_and_conjugations", test_1_japanese_and_conjugations),
            ("test_2_short_words_two_chars_or_less", test_2_short_words_two_chars_or_less),
            ("test_3_substring_matching", test_3_substring_matching),
            ("test_4_alphanumeric_and_symbols", test_4_alphanumeric_and_symbols),
            ("test_5_proper_nouns", test_5_proper_nouns),
            ("test_6_technical_terms", test_6_technical_terms),
            ("test_7_precision_and_noise_exclusion", test_7_precision_and_noise_exclusion),
            ("test_8_bm25_ranking", test_8_bm25_ranking),
        ]

        for name, fn in tests:
            print(f"[FTS] Running {name}...")
            fn(env)
            print(f">>> {name} PASSED!")

        conn.close()
        print("=== ALL FTS TRIGRAM TESTS PASSED SUCCESSFULLY! ===")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

