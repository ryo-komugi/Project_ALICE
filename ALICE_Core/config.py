import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# =========================
# LINE
# =========================
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]
CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
BASE_URL = "https://api.line.me/v2/bot"
BASE_DATA_URL = "https://api-data.line.me/v2/bot"

# =========================
# Public URL
# =========================
PUBLIC_URL = os.environ["PUBLIC_URL"]

# =========================
# LINE Authentication
# =========================
INVITE_CODE = os.environ["INVITE_CODE"]
LINE_ADMIN_USER = os.environ["LINE_ADMIN_USER"]

# =========================
# Directories
# =========================
DIR_RUNTIME = "/data/runtime"

# Core
DIR_CORE_RUNTIME = f"{DIR_RUNTIME}/core"
DIR_INBOX = f"{DIR_CORE_RUNTIME}/inbox"
DIR_SHARE = f"{DIR_CORE_RUNTIME}/share"
DIR_ARCHIVE = f"{DIR_CORE_RUNTIME}/archive"

# Workspaces (1 Job = 1 Workspace)
DIR_WORKSPACES = f"{DIR_RUNTIME}/workspaces"

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
