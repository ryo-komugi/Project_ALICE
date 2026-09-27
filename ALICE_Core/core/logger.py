"""
[Facade / Compatibility Shim]
This module has been relocated to `infrastructure.logger`.
Importing from `core.logger` is maintained for backward compatibility.
"""
from infrastructure.logger import *  # noqa: F401, F403
from infrastructure.logger import (
    initialize_logger,
    cleanup_logs,
    ARCHIVE_DIR,
    LOG_DIR,
    LOG_FILE,
)
