"""ALICE_Search 設定モジュール"""

import os
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parent.parent))).expanduser()
DATA_DIR = Path(os.environ.get("ALICE_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = PROJECT_ROOT / DATA_DIR
DEFAULT_WORKSPACES_DIR = DATA_DIR / "runtime" / "workspaces"
DEFAULT_DB_PATH = DATA_DIR / "runtime" / "search" / "alice_index.db"

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
