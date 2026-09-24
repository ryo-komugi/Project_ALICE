"""ALICE_Search 設定モジュール"""

import os
from pathlib import Path

# デフォルトパス
DEFAULT_DB_PATH = Path(os.environ.get("ALICE_SEARCH_DB_PATH", "/data/runtime/search/alice_index.db"))
DEFAULT_WORKSPACES_DIR = Path(os.environ.get("ALICE_WORKSPACES_DIR", "/data/runtime/workspaces"))

# 全文検索対象アーティファクトの定義
# 注意:
# - transcript.json は一次構造化データ（正本）として維持し、FTS 全文検索対象には含めない
# - *.log ファイルや中間 JSON は検索対象外
TARGET_ARTIFACTS = {
    "summary": ["summary.txt", "summary.md", "commentary.txt", "commentary.md"],
    "transcript": ["transcript.txt"],
    "minutes": ["minutes.txt", "minutes.md"],
}

# 許可するモジュール名
ALLOWED_MODULES = {"summary", "transcript", "minutes"}
