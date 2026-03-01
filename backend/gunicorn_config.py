# Gunicorn config for Render: read PORT from environment (avoids shell $PORT expansion issues)
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
workers = 1
timeout = 300
