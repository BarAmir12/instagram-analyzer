"""
cookies.py
----------
Instagram session cookie management.
Loads cookies from local cache, Chrome browser, or instagram.com directly.

Exports (used by instagram_api.py):
    ssl_ctx, ig_cookies, ig_csrf
    init_ig_cookies()
"""

import os
import ssl
import sys
import json
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import urllib.request
import urllib.parse
import http.cookiejar
from hashlib import pbkdf2_hmac


# ── Shared SSL context ────────────────────────────────────────────

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

# ── Cookie state ──────────────────────────────────────────────────

ig_cookies: str = ""
ig_csrf:    str = ""

_COOKIE_CACHE = os.path.expanduser("~/.ig_session_cache.json")


# ── Cache helpers ─────────────────────────────────────────────────

def _save_cookie_cache(cookie_dict: dict) -> None:
    try:
        with open(_COOKIE_CACHE, "w") as f:
            json.dump(cookie_dict, f)
        os.chmod(_COOKIE_CACHE, 0o600)
    except Exception:
        pass


def _load_cookie_cache() -> bool:
    global ig_cookies, ig_csrf
    if not os.path.exists(_COOKIE_CACHE):
        return False
    try:
        with open(_COOKIE_CACHE) as f:
            cookie_dict = json.load(f)
        if "sessionid" not in cookie_dict:
            return False
        ig_cookies = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        ig_csrf    = cookie_dict.get("csrftoken", "")
        uid        = cookie_dict.get("ds_user_id", "?")
        print(f"   🍪 Loaded cookies from local cache (user_id={uid})")
        return True
    except Exception:
        return False


# ── Chrome cookie loader ──────────────────────────────────────────

def _load_chrome_cookies() -> bool:
    global ig_cookies, ig_csrf
    if sys.platform != "darwin":
        return False  # Chrome/Keychain loading is macOS-only; on Linux use cache or basic cookies
    try:
        from Crypto.Cipher import AES as _AES
    except ImportError:
        print("   ⚠️  pycryptodome not installed — skipping Chrome cookie read")
        return False
    try:
        print("   🔑 Accessing Mac Keychain (one-time only)...")
        print("      (If a permission dialog appears — click 'Always Allow')")
        pw_result = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage", "-a", "Chrome"],
            capture_output=True, text=True, timeout=60
        )
        if pw_result.returncode != 0 or not pw_result.stdout.strip():
            print("   ⚠️  Could not read Chrome Keychain key")
            return False

        pw  = pw_result.stdout.strip().encode()
        key = pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, dklen=16)

        db_path = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Cookies")
        if not os.path.exists(db_path):
            print("   ⚠️  Chrome Cookies file not found")
            return False

        tmp_db = tempfile.mktemp(suffix=".db")
        shutil.copy2(db_path, tmp_db)
        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%instagram%'"
        ).fetchall()
        conn.close()
        os.unlink(tmp_db)

        def _decrypt(enc: bytes) -> str:
            if enc[:3] != b"v10":
                return enc.decode("utf-8", errors="replace")
            cipher = _AES.new(key, _AES.MODE_CBC, b" " * 16)
            dec    = cipher.decrypt(enc[3:])
            pad    = dec[-1]
            plain  = dec[:-pad] if 1 <= pad <= 16 else dec
            return plain[32:].decode("utf-8", errors="replace")

        cookie_dict: dict[str, str] = {}
        for name, enc in rows:
            cookie_dict[name] = urllib.parse.unquote(_decrypt(enc))

        if "sessionid" not in cookie_dict:
            print("   ⚠️  sessionid not found — is Chrome logged in to Instagram?")
            return False

        ig_cookies = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        ig_csrf    = cookie_dict.get("csrftoken", "")
        uid        = cookie_dict.get("ds_user_id", "?")
        print(f"   🍪 Loaded {len(cookie_dict)} cookies from Chrome (user_id={uid})")
        _save_cookie_cache(cookie_dict)
        return True
    except Exception as e:
        print(f"   ⚠️  Error reading Chrome cookies: {e}")
        return False


# ── Fallback: fetch basic cookies from instagram.com ─────────────

def _fetch_basic_cookies() -> None:
    global ig_cookies, ig_csrf
    print("   🌐 Fetching basic cookies from instagram.com...")
    try:
        jar    = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_ctx),
            urllib.request.HTTPCookieProcessor(jar)
        )
        req = urllib.request.Request(
            "https://www.instagram.com/",
            headers={
                "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        with opener.open(req, timeout=10) as resp:
            resp.read()
        parts      = [f"{c.name}={c.value}" for c in jar]
        ig_cookies = "; ".join(parts)
        for c in jar:
            if c.name == "csrftoken":
                ig_csrf = c.value
                break
        print(f"   🍪 Received {len(parts)} basic cookies")
    except Exception as e:
        print(f"   ⚠️  Failed to fetch cookies: {e}")


# ── Public entry point ────────────────────────────────────────────

def init_ig_cookies() -> None:
    if _load_cookie_cache():
        return
    if _load_chrome_cookies():
        return
    _fetch_basic_cookies()
