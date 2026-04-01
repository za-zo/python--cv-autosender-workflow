import os
from dotenv import load_dotenv

load_dotenv()

# ── Notifications ─────────────────────────────────────────────────────────
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL")

# ── HTML-to-PDF ───────────────────────────────────────────────────────────
HTML2PDF_URL = "https://zazo-html2pdf.onrender.com/v1/generate"

# ── MongoDB ───────────────────────────────────────────────────────────────
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME")

# ── Logging ───────────────────────────────────────────────────────────────
MASK_LOGS = os.getenv("MASK_LOGS", "false").lower() == "true"

# ── Retry defaults ────────────────────────────────────────────────────────
MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 5
