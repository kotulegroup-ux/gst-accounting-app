import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", "gst-accounting-super-secret-key-2026-secure")
APP_TITLE = "GST Accounting & Tax Invoicing System"
