#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_ROOT="${DB_BACKUP_DIR:-$PROJECT_ROOT/archive/database_backups}"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
DEST_DIR="$BACKUP_ROOT/$TIMESTAMP"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required to create consistent SQLite backups." >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

python3 - "$PROJECT_ROOT" "$DEST_DIR" <<'PY'
import sqlite3
import sys
from pathlib import Path

project_root = Path(sys.argv[1]).resolve()
dest_root = Path(sys.argv[2]).resolve()
excluded_dirs = {".git", "myenv", "archive", "__pycache__"}

sources = []
for path in project_root.rglob("*.db"):
    relative = path.relative_to(project_root)
    if any(part in excluded_dirs for part in relative.parts):
        continue
    if ".aider.tags.cache.v4" in relative.parts:
        continue
    if not path.is_file():
        continue
    sources.append(path)

if not sources:
    print("No database files found to back up.")
    raise SystemExit(0)

for source in sorted(sources):
    relative = source.relative_to(project_root)
    target = dest_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(target) as backup_db:
                source_db.backup(backup_db)
    except sqlite3.Error as exc:
        print(f"Failed to back up {relative}: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Backed up: {relative} -> {target}")

print(f"Backup complete: {dest_root}")
PY
