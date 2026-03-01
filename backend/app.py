#!/usr/bin/env python3
"""
app.py
------
Flask entry point for the Instagram Analyzer.
Run with:  python3 backend/app.py

Routes:
    GET  /           → frontend/index.html  (upload page)
    GET  /guide      → frontend/guide.html  (download guide)
    GET  /progress   → JSON progress state
    POST /analyze    → process ZIP, return results HTML
    POST /api/open   → open profile URLs in the browser
"""

import io
import os
import re
import sys
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

# Allow sibling modules (cookies, instagram_api, analyzer) to be imported
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_BACKEND_DIR, "..", "frontend")
sys.path.insert(0, _BACKEND_DIR)

import cookies
import instagram_api
import analyzer

app = Flask(
    __name__,
    template_folder=os.path.join(_BACKEND_DIR, "templates"),
    static_folder=_FRONTEND_DIR,
    static_url_path="/static",
)

# Production: port from env (e.g. Gunicorn); limit upload size
app.config["PORT"] = int(os.environ.get("PORT", 5000))
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024  # 80 MB


# ── Template filters (for report.html) ─────────────────────────────

@app.template_filter("fmt_num")
def _fmt_num(value):
    return f"{value:,}"


@app.template_filter("fmt_date")
def _fmt_date(ts):
    return analyzer.ts_to_date(ts)


# ── Progress tracking ─────────────────────────────────────────────

_log_lock  = threading.Lock()
_progress  = {"done": 0, "total": 0, "phase": ""}


def _on_progress(phase: str, done: int, total: int) -> None:
    """Called by instagram_api to update UI progress. Thread-safe."""
    with _log_lock:
        _progress["phase"] = phase
        _progress["done"]  = done
        _progress["total"] = total


class _LogCapture(io.TextIOBase):
    """Tees stdout to the terminal (progress is updated via callback, not parsing)."""

    def __init__(self, orig):
        self._orig = orig

    def write(self, s):
        self._orig.write(s)
        self._orig.flush()
        return len(s)

    def flush(self):
        self._orig.flush()


# ── Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(_FRONTEND_DIR, "index.html")


@app.route("/guide")
def guide():
    return send_from_directory(_FRONTEND_DIR, "guide.html")


@app.route("/progress")
def progress():
    with _log_lock:
        return jsonify(_progress)


@app.route("/healthz")
def healthz():
    """Health check for Render / load balancers."""
    return "", 200


@app.route("/analyze", methods=["POST"])
def analyze():
    zip_file = request.files.get("zipfile")
    if not zip_file:
        return Response("No zip file uploaded", status=400, mimetype="text/plain")
    if request.content_length and request.content_length > app.config["MAX_CONTENT_LENGTH"]:
        return Response("File too large", status=413, mimetype="text/plain")

    with _log_lock:
        _progress.update({"done": 0, "total": 0, "phase": "Preparing data..."})

    tmpdir   = tempfile.mkdtemp()
    zip_path = os.path.join(tmpdir, "upload.zip")
    try:
        zip_file.save(zip_path)

        print("📦 ZIP file received — starting analysis...")
        paths = analyzer.extract_files(zip_path, tmpdir)
        data  = analyzer.parse_data(paths)
        print(f"📊 Followers: {data['followers_count']} | Following: {data['following_count']}")

        username      = "user"
        original_name = zip_file.filename or ""
        m = re.search(r"instagram[-_]([a-zA-Z0-9_.]+)[-_]", original_name)
        if m:
            username = m.group(1)

        print("🌐 Initializing Instagram connection...")
        cookies.init_ig_cookies()

        verification_limited = not cookies.has_logged_in_session
        if verification_limited:
            print("   ⚠️  No Instagram session — only profiles that clearly appear unavailable will be removed.")
        pending_n = len(data["pending"])
        nfb_n     = len(data["not_following_back"])
        with _log_lock:
            _progress.update({"done": 0, "total": pending_n + nfb_n, "phase": "Starting verification..."})

        data["pending"],            rl_pending = instagram_api.verify_accounts(
            data["pending"], "pending", require_private=True, progress_callback=_on_progress
        )
        data["not_following_back"], rl_nfb = instagram_api.verify_accounts(
            data["not_following_back"], "not following back", require_private=False, progress_callback=_on_progress
        )

        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
        return render_template(
            "report.html",
            data=data,
            username=username,
            generated_at=generated_at,
            rl_nfb=rl_nfb,
            rl_pending=rl_pending,
            verification_limited=verification_limited,
            port=app.config["PORT"],
        )

    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return Response(
            "Something went wrong. Please try again or use a valid Instagram data export.",
            status=500,
            mimetype="text/plain; charset=utf-8",
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.route("/api/open", methods=["POST", "OPTIONS"])
def open_tabs():
    if request.method == "OPTIONS":
        resp = Response(status=200)
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return resp
    urls = (request.json or {}).get("urls", [])
    if urls:
        cmd = "open" if sys.platform == "darwin" else "xdg-open"
        for url in urls:
            try:
                subprocess.Popen([cmd, url], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    return jsonify({"count": len(urls)})


# ── Main ──────────────────────────────────────────────────────────

def _local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "?"


def main():
    sys.stdout = _LogCapture(sys.__stdout__)

    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    app.config["PORT"] = port

    bind_all = os.environ.get("BIND_ALL", "").strip().lower() in ("1", "true", "yes")
    host = "0.0.0.0" if bind_all else "localhost"

    threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False,
                               use_reloader=False, threaded=True),
        daemon=True,
    ).start()

    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.1)

    url_local = f"http://127.0.0.1:{port}"
    print(f"🌐 Instagram Analyzer running at {url_local}")
    if bind_all:
        url_lan = f"http://{_local_ip()}:{port}"
        print(f"   Simulate Linux server: open from another device (e.g. phone on same Wi‑Fi):")
        print(f"   {url_lan}")
    else:
        subprocess.Popen(["open", url_local])
    print("⌨️  Press Ctrl+C to stop")

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n👋 Server stopped")


if __name__ == "__main__":
    main()
