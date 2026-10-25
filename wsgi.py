"""
WSGI adapter for hosting environments like PythonAnywhere or cPanel.
"""
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from a2wsgi import ASGIMiddleware
from app.main import app

application = ASGIMiddleware(app)
