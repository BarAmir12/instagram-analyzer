"""
instagram_api.py
----------------
Instagram account verification via the internal web API.
Depends on cookies.py for session state (cookies, csrf, ssl_ctx).

Public API:
    verify_accounts(items, label, require_private) -> (list, bool)
"""

import json
import time
import random
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

import cookies as _cookies


# ── Rate-limit flag (reset per verify_accounts call) ─────────────

_rate_limited = threading.Event()


# ── Low-level API helpers ─────────────────────────────────────────

def _search_check(username: str):
    """Fallback search when the profile API is rate-limited."""
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
            return match if match is not None else False
    except Exception:
        return None


def _fetch_user(username: str):
    """Fetch full profile info for a username. Returns user dict, None (deleted), {} (error), or 'RATE_LIMITED'."""
    if _rate_limited.is_set():
        return "RATE_LIMITED"
    time.sleep(random.uniform(0.3, 0.8))
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
            data = json.loads(resp.read())
            return data.get("data", {}).get("user")
    except urllib.error.HTTPError as e:
        if e.code in (401, 429):
            _rate_limited.set()
            return "RATE_LIMITED"
        return None if e.code in (404, 400) else {}
    except Exception:
        return {}


# ── Per-account check functions (used as thread workers) ──────────

def _check_existence(args):
    username, ts = args
    user = _fetch_user(username)
    if user == "RATE_LIMITED":
        result = _search_check(username)
        return (username, ts, result is not False, False)
    if user is None:
        return (username, ts, False, False)
    return (username, ts, True, False)


def _check_pending(args):
    username, ts = args
    user = _fetch_user(username)
    if user == "RATE_LIMITED":
        result = _search_check(username)
        if result is None:
            return (username, ts, True, True)
        if result is False:
            return (username, ts, False, None)
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
