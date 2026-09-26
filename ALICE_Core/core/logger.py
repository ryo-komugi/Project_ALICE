from pathlib import Path
import logging
import shutil
import os
from datetime import datetime, timedelta

LOG_DIR = Path("/data/runtime/logs")
ARCHIVE_DIR = LOG_DIR / "archive"
LOG_FILE = LOG_DIR / "alice.log"


def cleanup_logs(
    archive_dir: Path = ARCHIVE_DIR,
    retention_days: int = 14,
    max_total_bytes: int = 100 * 1024 * 1024,
) -> dict[str, int]:
    """古いログアーカイブおよび不要な空ログを削除し、ディスク使用量を健全に保つ。

    ルール:
    1. サイズが 0 バイトの空ログファイルを削除
    2. 保持期限 (既定 14 日 = 2週間) を超過したファイルを削除
    3. アーカイブ合計容量が上限 (既定 100MB) を超えている場合、古い順に削除

    Returns:
        dict: {"deleted_count": int, "freed_bytes": int, "remaining_count": int}
    """
    if not archive_dir.exists() or not archive_dir.is_dir():
        return {"deleted_count": 0, "freed_bytes": 0, "remaining_count": 0}

    now = datetime.now()
    cutoff_time = now - timedelta(days=retention_days)
    deleted_count = 0
    freed_bytes = 0

    log_files = []
    for p in archive_dir.iterdir():
        if p.is_file() and p.name.endswith(".log"):
            try:
                stat = p.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)
                size = stat.st_size
                log_files.append((p, mtime, size))
            except Exception:
                continue

    remaining = []
    # 1. 0バイトファイル & 保持期限切れ削除
    for path, mtime, size in log_files:
        if size == 0 or mtime < cutoff_time:
            try:
                path.unlink(missing_ok=True)
                deleted_count += 1
                freed_bytes += size
            except Exception as e:
                logging.getLogger(__name__).warning(f"[Logger] Failed to unlink log {path}: {e}")
        else:
            remaining.append((path, mtime, size))

    # 2. 合計容量制限（古い順にソートして上限を超える分を削除）
    remaining.sort(key=lambda x: x[1])  # 古い順
    total_bytes = sum(s for _, _, s in remaining)

    while total_bytes > max_total_bytes and remaining:
        oldest_path, _, oldest_size = remaining.pop(0)
        try:
            oldest_path.unlink(missing_ok=True)
            total_bytes -= oldest_size
            deleted_count += 1
            freed_bytes += oldest_size
        except Exception as e:
            logging.getLogger(__name__).warning(f"[Logger] Failed to purge log for size limit {oldest_path}: {e}")

    return {
        "deleted_count": deleted_count,
        "freed_bytes": freed_bytes,
        "remaining_count": len(remaining),
    }


def purge_old_logs(
    archive_dir: Path = ARCHIVE_DIR,
    retention_days: int = 14,
    max_total_bytes: int = 100 * 1024 * 1024,
) -> int:
    """古いログアーカイブの削除（互換用ラッパー）。削除件数を返す。"""
    res = cleanup_logs(archive_dir, retention_days, max_total_bytes)
    return res["deleted_count"]


def initialize_logger() -> None:
    """
    ALICE_Core共通Logger初期化
    """
    # ディレクトリ作成
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 古いログを退避
    if LOG_FILE.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = ARCHIVE_DIR / f"alice_{timestamp}.log"
        try:
            shutil.move(LOG_FILE, archive_file)
        except Exception:
            pass

    # アーカイブの自動パージ（2週間保持 = 14日超 & 100MB超過制限 & 空ログ削除）
    try:
        cleanup_logs(ARCHIVE_DIR, retention_days=14)
    except Exception as e:
        print(f"[Logger] Failed to purge old logs: {e}")

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Handler初期化
    root_logger.handlers.clear()

    # Console出力
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File出力
    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    for logger_name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
    ):
        logger = logging.getLogger(logger_name)
        logger.handlers = root_logger.handlers
        logger.setLevel(logging.INFO)
        logger.propagate = False
