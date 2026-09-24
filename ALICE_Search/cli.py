#!/usr/bin/env python3
"""ALICE_Search CLI エントリーポイント

Workspace Driven CLI 原則に基づき、引数経由でインデックス登録・検索・再構築を行う。
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# パス解決: スクリプト自身のあるディレクトリを sys.path に追加
CLI_DIR = Path(__file__).resolve().parent
if str(CLI_DIR.parent) not in sys.path:
    sys.path.insert(0, str(CLI_DIR.parent))

from ALICE_Search.config import DEFAULT_DB_PATH, DEFAULT_WORKSPACES_DIR
from ALICE_Search.core.indexer import index_workspace, reindex_all
from ALICE_Search.core.schema import get_connection, init_db
from ALICE_Search.core.searcher import Searcher
from ALICE_Search.models.query import SearchQuery

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ALICE_Search] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ALICE_Search")


def parse_args():
    parser = argparse.ArgumentParser(
        description="ALICE Knowledge & Search CLI v1.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  1. 単一ジョブのインデックス登録:
     python cli.py --index-job /data/runtime/workspaces/job_xxx

  2. 全文検索実行 (--query に統一):
     python cli.py --query "来期予算" --limit 5
     python cli.py --query "進捗" --user "user_123" --module "summary"

  3. 全体再インデックス:
     python cli.py --reindex
        """,
    )

    # 実行モード（いずれか1つ、または query）
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--index-job",
        type=str,
        metavar="WORKSPACE_DIR",
        help="指定された Workspace ディレクトリをインデックスに登録/更新する",
    )
    mode_group.add_argument(
        "--query",
        type=str,
        nargs="?",
        const="",
        metavar="TEXT",
        help="全文検索を実行する (キーワード検索)",
    )
    mode_group.add_argument(
        "--reindex",
        action="store_true",
        help="すべての Workspace から派生インデックスを完全再構築する",
    )

    # 検索フィルタ・オプション
    parser.add_argument("--user", type=str, help="ユーザーIDによる絞り込み")
    parser.add_argument("--module", type=str, help="モジュールによる絞り込み (summary, transcript 等)")
    parser.add_argument("--status", type=str, help="ステータスによる絞り込み (COMPLETED, FAILED 等)")
    parser.add_argument("--limit", type=int, default=10, help="取得最大件数 (既定: 10)")
    parser.add_argument("--offset", type=int, default=0, help="取得オフセット (既定: 0)")

    # パス指定オプション
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"インデックスDBのパス (既定: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--workspaces-dir",
        type=str,
        default=str(DEFAULT_WORKSPACES_DIR),
        help=f"Workspaces ルートディレクトリ (既定: {DEFAULT_WORKSPACES_DIR})",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db_path).resolve()

    # モード 1: 単一 Workspace のインデックス更新
    if args.index_job:
        ws_dir = Path(args.index_job).resolve()
        if not ws_dir.exists():
            logger.error(f"Workspace directory not found: {ws_dir}")
            sys.exit(1)

        conn = get_connection(db_path)
        init_db(conn)
        try:
            ok = index_workspace(ws_dir, conn)
            if ok:
                logger.info(f"Successfully indexed: {ws_dir.name}")
                sys.exit(0)
            else:
                logger.error(f"Failed to index workspace: {ws_dir.name}")
                sys.exit(1)
        finally:
            conn.close()

    # モード 2: 全体再インデックス
    elif args.reindex:
        ws_root = Path(args.workspaces_dir).resolve()
        logger.info(f"Rebuilding search index from {ws_root} into {db_path}...")
        success, failed = reindex_all(ws_root, db_path)
        print(json.dumps({"reindex": "completed", "success": success, "failed": failed}, indent=2, ensure_ascii=False))
        sys.exit(0)

    # モード 3: 検索実行 (--query)
    elif args.query is not None:
        searcher = Searcher(db_path=db_path)
        q = SearchQuery(
            query=args.query if args.query != "" else None,
            user_id=args.user,
            module=args.module,
            status=args.status,
            limit=args.limit,
            offset=args.offset,
        )
        res = searcher.search(q)
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        sys.exit(0)


if __name__ == "__main__":
    main()
