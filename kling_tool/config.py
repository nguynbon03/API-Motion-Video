"""Global configuration and paths — supports env vars for Docker."""

import os
from pathlib import Path

# ── Kling Web ──────────────────────────────────────────────
KLING_WEB_URL = "https://klingai.com"
KLING_APP_URL = "https://app.klingai.com"
KLING_LOGIN_URL = "https://app.klingai.com/login"
KLING_MOTION_URL = "https://app.klingai.com/global/video-motion-control/new"

# ── Local storage (configurable via KLING_DATA_DIR env) ────
DATA_DIR = Path(os.environ.get("KLING_DATA_DIR", str(Path.home() / ".kling_tool")))
DB_PATH = DATA_DIR / "database.db"
SESSIONS_DIR = DATA_DIR / "sessions"
DOWNLOADS_DIR = DATA_DIR / "downloads"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
LOGS_DIR = DATA_DIR / "logs"
INPUTS_DIR = DATA_DIR / "inputs"
IMAGES_DIR = INPUTS_DIR / "images"
VIDEOS_DIR = INPUTS_DIR / "videos"
OUTPUTS_DIR = DATA_DIR / "outputs"
ACCOUNTS_DIR = DATA_DIR / "accounts"

# ── Defaults ───────────────────────────────────────────────
DEFAULT_TIMEOUT = 60_000          # 60s for page loads
UPLOAD_TIMEOUT = 120_000          # 120s for file uploads
GENERATION_TIMEOUT = 600_000      # 10min for video generation
POLL_INTERVAL = 10                # seconds between status checks
MAX_CONCURRENT_PER_ACCOUNT = int(os.environ.get("KLING_MAX_CONCURRENT", "1"))
HEADLESS = os.environ.get("KLING_HEADLESS", "true").lower() == "true"

# ── REST API ───────────────────────────────────────────────
API_HOST = os.environ.get("KLING_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("KLING_PORT", "8686"))


def ensure_dirs():
    """Create all required directories."""
    for d in [DATA_DIR, SESSIONS_DIR, DOWNLOADS_DIR, SCREENSHOTS_DIR,
              LOGS_DIR, IMAGES_DIR, VIDEOS_DIR, OUTPUTS_DIR, ACCOUNTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
