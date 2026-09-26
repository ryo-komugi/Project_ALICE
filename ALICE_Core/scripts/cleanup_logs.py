#!/usr/bin/env python3
"""ALICE ログクリーンアップ ユーティリティ CLI

使用法:
  python cleanup_logs.py [--days 14] [--max-mb 100]
"""

import argparse
from pathlib import Path
import sys

# ALICE_Core ディレクトリを path に追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.logger import cleanup_logs, ARCHIVE_DIR


def main():
    parser = argparse.ArgumentParser(description="ALICE ログクリーンアップ ユーティリティ")
    parser.add_argument("--days", type=int, default=14, help="ログ保持日数（既定: 14日 = 2週間）")
    parser.add_argument("--max-mb", type=int, default=100, help="アーカイブ合計容量上限MB（既定: 100MB）")
    args = parser.parse_args()

    print(f"[LogCleanup] Starting log cleanup (Retention: {args.days} days, Max size: {args.max_mb} MB)...")
    res = cleanup_logs(
        archive_dir=ARCHIVE_DIR,
        retention_days=args.days,
        max_total_bytes=args.max_mb * 1024 * 1024,
    )

    freed_kb = res["freed_bytes"] / 1024
    print(f"[LogCleanup] Done.")
    print(f"  Deleted files:   {res['deleted_count']}")
    print(f"  Freed storage:   {freed_kb:.1f} KB ({res['freed_bytes']} bytes)")
    print(f"  Remaining logs:  {res['remaining_count']}")


if __name__ == "__main__":
    main()
