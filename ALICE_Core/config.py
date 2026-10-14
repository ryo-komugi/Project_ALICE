import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# =========================
# Project Root & Paths
# =========================
CORE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(CORE_DIR.parent)))

# =========================
# LINE Adapter (Optional External Interface)
# =========================
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
BASE_URL = os.getenv("LINE_API_BASE_URL", "https://api.line.me") + "/v2/bot"
BASE_DATA_URL = os.getenv("LINE_DATA_API_BASE_URL", "https://api-data.line.me") + "/v2/bot"
INVITE_CODE = os.getenv("INVITE_CODE", "")
LINE_ADMIN_USER = os.getenv("LINE_ADMIN_USER", "")
LINE_ENABLED = bool(CHANNEL_SECRET and CHANNEL_ACCESS_TOKEN)

# =========================
# Public URL
# =========================
PUBLIC_URL = os.getenv("PUBLIC_URL", "https://project-alice.net")

# =========================
# Directories
# =========================
DIR_RUNTIME = "/data/runtime"
DATA_DIR = Path(os.getenv("ALICE_DATA_DIR", str(PROJECT_ROOT / "data"))).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = PROJECT_ROOT / DATA_DIR
DIR_LOGS = str(DATA_DIR / "runtime" / "logs")

# Core
DIR_CORE_RUNTIME = f"{DIR_RUNTIME}/core"
DIR_INBOX = f"{DIR_CORE_RUNTIME}/inbox"
DIR_SHARE = f"{DIR_CORE_RUNTIME}/share"
DIR_ARCHIVE = f"{DIR_CORE_RUNTIME}/archive"

# Workspaces (1 Job = 1 Workspace), relative to DATA_DIR.
DIR_WORKSPACES = str(DATA_DIR / "runtime" / "workspaces")

# =========================
# Discord Alert
# =========================
DISCORD_ALERT_WEBHOOK_URL = os.getenv("DISCORD_ALERT_WEBHOOK_URL", "")

# =========================
# Admin Web Authentication
# =========================
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "")

# =========================
# Workflow SLA & Resilience
# =========================
MODULE_TIMEOUT_SEC = int(os.getenv("MODULE_TIMEOUT_SEC", "900"))  # 15分
MODULE_MAX_RETRIES = int(os.getenv("MODULE_MAX_RETRIES", "2"))   # 最大リトライ回数
MODULE_RETRY_BACKOFF_SEC = int(os.getenv("MODULE_RETRY_BACKOFF_SEC", "5")) # リトライ前待機秒数
