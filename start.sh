#!/usr/bin/env bash
# Render: use gunicorn_config.py so PORT is read from env by Python (avoids $PORT expansion issues)
set -e
cd "$(dirname "$0")/backend"
echo "Starting gunicorn (bind from gunicorn_config.py)"
exec gunicorn app:app -c gunicorn_config.py
