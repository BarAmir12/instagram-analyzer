"""
instagram_api.py
----------------
Instagram account verification via the internal web API.
Depends on cookies.py for session state (cookies, csrf, ssl_ctx).

Public API:
    verify_accounts(items, label, require_private) -> (list, bool)
"""

import json
import os
import time
import random
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

import cookies as _cookies

# On Render, Instagram often returns generic page (no profilePage_) for all requests; only remove when page says "unavailable"
_verification_conservative = os.environ.get("RENDER") == "true"


# ── Rate-limit state (reset per verify_accounts call) ────────────

_rate_limited = threading.Event()
_rate_limited_until = 0.0  # time.time() after which we may retry API
_RATE_LIMIT_COOLDOWN = 70   # seconds to wait before retrying API after 429


# ── Low-level API helpers ─────────────────────────────────────────

def _profile_returns_404(username: str) -> bool:
    """HEAD request to profile URL. Returns True if 404 (account does not exist)."""
    url = f"https://www.instagram.com/{username}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html",
    }
    if _cookies.ig_cookies:
        headers["Cookie"] = _cookies.ig_cookies
    try:
        req = urllib.request.Request(url, headers=headers, method="HEAD")
        with urllib.request.urlopen(req, timeout=8, context=_cookies.ssl_ctx) as resp:
            return resp.status == 404
    except urllib.error.HTTPError as e:
        return e.code == 404
    except Exception:
        return False


def _fetch_profile_page(username: str) -> tuple[bool, bool]:
    """
    Fetch profile page HTML. Returns (unavailable, confirms_exists).
    unavailable: True if page says account is deleted/unavailable or 404.
    confirms_exists: True if page contains profilePage_ (real profile).
    No HEAD before GET — HEAD can cause Instagram to return a stub page on the GET.
    """
    url = f"https://www.instagram.com/{username}/"
    # Same headers as direct GET that returns full page (profilePage_)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html",
    }
    if _cookies.ig_cookies:
        headers["Cookie"] = _cookies.ig_cookies

    def _do_fetch():
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=_cookies.ssl_ctx) as resp:
                if resp.status != 200:
                    return (True, False, "")
                html = resp.read().decode("utf-8", errors="ignore")
                unavail = (
                    "Sorry, this page isn't available" in html
                    or "this page isn't available" in html
                    or "page isn't available" in html
                    or "User not found" in html
                    or "The link you followed may be broken" in html
                    or "link you followed may be broken" in html
                )
                confirms = (
                    "profilePage_" in html
                    or "logging_page_id" in html
                    or '"profile_id":' in html
                )
                return (unavail, confirms, html)
        except urllib.error.HTTPError as e:
            return (e.code == 404, False, "")
        except Exception:
            return (False, False, "")

    unavail, confirms, html = _do_fetch()
    for _ in range(2):
        if unavail or confirms:
            break
        time.sleep(random.uniform(1.0, 1.8))
        unavail, confirms, html = _do_fetch()
    return (unavail, confirms)


def _profile_page_unavailable(username: str) -> bool:
    """Fetch profile page; return True if page says account is unavailable (deleted/deactivated)."""
    unavail, _ = _fetch_profile_page(username)
    return unavail


def _profile_page_confirms_exists(username: str) -> bool:
    """Fetch profile page; return True only if page clearly shows a real profile (profilePage_ etc.)."""
    _, confirms = _fetch_profile_page(username)
    return confirms


def _search_check(username: str):
    """Fallback search when the profile API is rate-limited. Returns user dict, False (not found), or None (error)."""
    url = f"https://www.instagram.com/web/search/topsearch/?query={username}&context=blended"
    headers = {
        "User-Agent":  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept":      "*/*",
        "x-ig-app-id": "936619743392459",
    }
    if _cookies.ig_cookies:
        headers["Cookie"] = _cookies.ig_cookies
    if _cookies.ig_csrf:
        headers["X-CSRFToken"] = _cookies.ig_csrf
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=_cookies.ssl_ctx) as resp:
            d     = json.loads(resp.read())
            users = d.get("users", [])
            match = next(
                (u.get("user", {}) for u in users if u.get("user", {}).get("username") == username),
                None,
            )
            if match is None or not _is_valid_user(match, required_username=username):
                return False
            return match
    except Exception:
        return None


def _is_valid_user(user, required_username: str = None) -> bool:
    """True only if we got a real profile: has both pk and username, and optional username match."""
    if not user or not isinstance(user, dict):
        return False
    un = user.get("username")
    pk = user.get("pk")
    if not un or not pk:
        return False
    if isinstance(un, str):
        un = un.strip()
    if not un:
        return False
    if required_username is not None and un.lower() != required_username.lower():
        return False
    return True


def _fetch_user(username: str):
    """Fetch full profile info for a username. Returns user dict, None (deleted/invalid), {} (error), or 'RATE_LIMITED'."""
    if _rate_limited.is_set():
        if time.time() < _rate_limited_until:
            return "RATE_LIMITED"
        _rate_limited.clear()
    time.sleep(random.uniform(1.0, 2.0))
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        "User-Agent":        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept":            "*/*",
        "Accept-Language":   "en-US,en;q=0.9",
        "x-ig-app-id":       "936619743392459",
        "X-Requested-With":  "XMLHttpRequest",
        "Referer":           f"https://www.instagram.com/{username}/",
        "Origin":            "https://www.instagram.com",
    }
    if _cookies.ig_cookies:
        headers["Cookie"] = _cookies.ig_cookies
    if _cookies.ig_csrf:
        headers["X-CSRFToken"] = _cookies.ig_csrf
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12, context=_cookies.ssl_ctx) as resp:
            raw = resp.read()
            data = json.loads(raw)
            user = data.get("data") or {}
            if not isinstance(user, dict):
                return None
            user = user.get("user")
            if not _is_valid_user(user, required_username=username):
                return None
            return user
    except urllib.error.HTTPError as e:
        if e.code in (401, 429):
            globals()["_rate_limited_until"] = time.time() + _RATE_LIMIT_COOLDOWN
            _rate_limited.set()
            return "RATE_LIMITED"
        if e.code in (404, 400):
            return None
        try:
            body = e.read()
            data = json.loads(body)
            if data.get("message") or data.get("user") is None:
                return None
        except Exception:
            pass
        return {}
    except Exception:
        return {}


# ── Per-account check functions (used as thread workers) ──────────

def _check_existence(args):
    """Account exists if profilePage_ in page. Without session: no profilePage_ → REMOVE (except on Render: only remove when unavail)."""
    username, ts = args
    time.sleep(random.uniform(0.2, 0.4))
    unavail, confirms = _fetch_profile_page(username)
    if unavail:
        return (username, ts, False, False)
    if confirms:
        return (username, ts, True, False)
    has_session = getattr(_cookies, "has_logged_in_session", False)
    # On Render (and similar), Instagram returns generic page for everyone without session → don't remove unless unavail
    if not has_session and _verification_conservative:
        return (username, ts, True, False)
    return (username, ts, False, False)


def _check_pending(args):
    username, ts = args
    time.sleep(random.uniform(0.2, 0.4))
    unavail, confirms = _fetch_profile_page(username)
    if unavail:
        return (username, ts, False, None)
    if not getattr(_cookies, "has_logged_in_session", False):
        if _verification_conservative:
            return (username, ts, True, True)
        if not confirms:
            return (username, ts, False, None)
        return (username, ts, True, True)
    user = _fetch_user(username)
    if user == "RATE_LIMITED":
        result = _search_check(username)
        if result is False:
            return (username, ts, False, None)
        if result is None:
            return (username, ts, True, True)
        is_priv = result.get("is_private", True) if isinstance(result, dict) else True
        return (username, ts, True, is_priv)
    if user is None:
        return (username, ts, False, None)
    if user == {}:
        return (username, ts, True, True)
    return (username, ts, True, user.get("is_private", True))


# ── Public entry point ────────────────────────────────────────────

def verify_accounts(
    items: list,
    label: str,
    require_private: bool = False,
    progress_callback=None,
) -> tuple[list, bool]:
    """
    Check each (username, timestamp) pair.
    If require_private=False: removes deleted accounts.
    If require_private=True:  also removes accounts that are no longer private.
    progress_callback(phase, done, total) is called to update UI progress.
    Returns (filtered_list, was_rate_limited).
    """
    total = len(items)
    if total == 0:
        return items, False

    def report(phase: str, done: int, tot: int) -> None:
        if progress_callback:
            progress_callback(phase, done, tot)

    kept            = []
    removed_missing = 0
    removed_public  = 0
    _rate_limited.clear()
    workers = min(total, 5)

    if not require_private:
        phase = "Checking who's not following back..."
        report(phase, 0, total)
        print(f"\n🔍 Checking existence of {total} accounts ({label}) — {workers} threads in parallel...")
        results    = {}
        rate_warned = False
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_check_existence, item): item for item in items}
            done    = 0
            for future in as_completed(futures):
                name, ts, exists, _ = future.result()
                results[(name, ts)] = exists
                done += 1
                report(phase, done, total)
                if _rate_limited.is_set() and not rate_warned:
                    rate_warned = True
                    print(f"\n   ⛔  Instagram is rate-limiting requests (HTTP 401/429) — remaining accounts are kept", flush=True)
                status = "✅" if exists else "❌ not found"
                bar    = "█" * int(done / total * 20) + "░" * (20 - int(done / total * 20))
                print(f"\r   [{bar}] {done}/{total}  {status} @{name:<25}", end="", flush=True)
        print()
        for (n, ts), exists in results.items():
            if exists:
                kept.append((n, ts))
            else:
                removed_missing += 1
    else:
        phase = "Checking pending requests..."
        report(phase, 0, total)
        print(f"\n🔍 Checking {total} pending accounts...")
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_check_pending, item): item for item in items}
            done    = 0
            for future in as_completed(futures):
                name, ts, exists, is_private = future.result()
                results[(name, ts)] = (exists, is_private)
                done += 1
                report(phase, done, total)
                if not exists:
                    status = "❌ not found"
                elif is_private is False:
                    status = "🔓 public (old request)"
                elif is_private is True:
                    status = "✅ private"
                else:
                    status = "✅ (API error — kept)"
                bar = "█" * int(done / total * 20) + "░" * (20 - int(done / total * 20))
                print(f"\r   [{bar}] {done}/{total}  {status} @{name:<25}", end="", flush=True)
        if _rate_limited.is_set():
            print(f"\n   ⛔  Instagram is rate-limiting — some results may be inaccurate", flush=True)
        print()
        for (n, ts), (exists, is_private) in results.items():
            if not exists:
                removed_missing += 1
            elif is_private is False:
                removed_public += 1
            else:
                kept.append((n, ts))

    if removed_missing:
        print(f"   🗑  Removed {removed_missing} accounts that no longer exist")
    if removed_public:
        print(f"   🔓  Removed {removed_public} public accounts (old request)")

    return kept, _rate_limited.is_set()
