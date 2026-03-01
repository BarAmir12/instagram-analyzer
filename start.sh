#!/usr/bin/env bash
# Render: ensure we bind to 0.0.0.0 and PORT from environment
set -e
cd "$(dirname "$0")/backend"
PORT="${PORT:-10000}"
echo "Starting gunicorn on 0.0.0.0:${PORT}"
exec gunicorn -w 1 --bind "0.0.0.0:${PORT}" --timeout 300 app:app
