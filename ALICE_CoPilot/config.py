import os
from pathlib import Path

COPILOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(COPILOT_DIR.parent)))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
OLLAMA_CONTEXT = int(os.getenv("OLLAMA_CONTEXT", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "24h")

MEMORY_ROOT = Path(
    os.getenv(
        "ALICE_COPILOT_MEMORY_ROOT",
        "/data/memory/copilot",
    )
)

ARCHIVE_ROOT = MEMORY_ROOT / "Archive"
RELATIONS_ROOT = MEMORY_ROOT / "Relations"

DB_PATH = Path("/data/runtime/copilot/database/conversations.db")

OBSIDIAN_ROOT = Path("/data/memory/obsidian")

# Owner Identification (Core & Workspaces)
OWNER_CORE_USER_ID = os.getenv("ALICE_OWNER_CORE_USER_ID", "U794535d58fb802ac996f4a86ce119ad2")
OWNER_CORE_USER_IDS = {
    uid.strip()
    for uid in os.getenv("ALICE_OWNER_CORE_USER_IDS", OWNER_CORE_USER_ID).split(",")
    if uid.strip()
}


def is_owner_core_user(user_id: str | None) -> bool:
    """Check if the given Core user_id belongs to the authorized owner."""
    if not user_id:
        return False
    return str(user_id) in OWNER_CORE_USER_IDS


# Google Calendar Settings
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "t.a5128128@gmail.com")
GOOGLE_CALENDAR_CREDENTIALS_PATH = Path(
    os.getenv(
        "GOOGLE_CALENDAR_CREDENTIALS_PATH",
        "/data/runtime/calendar/credentials.json",
    )
)

