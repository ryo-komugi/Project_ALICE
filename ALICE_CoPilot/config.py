import os
from pathlib import Path

COPILOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(COPILOT_DIR.parent)))
DATA_DIR = Path(os.getenv("ALICE_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = PROJECT_ROOT / DATA_DIR
RUNTIME_DIR = DATA_DIR / "runtime"
MEMORY_DIR = DATA_DIR / "memory"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_CONTEXT = int(os.getenv("OLLAMA_CONTEXT", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "24h")

MEMORY_ROOT = MEMORY_DIR / "copilot"

ARCHIVE_ROOT = MEMORY_ROOT / "Archive"
RELATIONS_ROOT = MEMORY_ROOT / "Relations"

DB_PATH = RUNTIME_DIR / "copilot" / "database" / "conversations.db"

OBSIDIAN_ROOT = MEMORY_DIR / "obsidian"

# Owner Identification (Core & Workspaces)
OWNER_CORE_USER_ID = os.getenv("ALICE_OWNER_CORE_USER_ID", "")
OWNER_CORE_USER_IDS = {
    uid.strip()
    for uid in os.getenv("ALICE_OWNER_CORE_USER_IDS", OWNER_CORE_USER_ID).split(",")
    if uid.strip()
}


def is_owner_core_user(user_id: str | None) -> bool:
    """Check if the given Core user_id belongs to the authorized owner."""
    if not user_id:
        return False
    if not OWNER_CORE_USER_IDS:
        # If no owner IDs are configured, allow access
        return True
    return str(user_id) in OWNER_CORE_USER_IDS
