"""
analyzer.py
-----------
ZIP extraction and data parsing. Report HTML is rendered via Flask template (templates/report.html).
No network or server dependencies.

Public API:
    extract_files(zip_path, tmpdir) -> dict
    parse_data(paths)               -> dict
    ts_to_date(ts)                  -> str  (for Jinja2 fmt_date filter)
"""

import os
import json
import zipfile
from datetime import datetime


# ── ZIP extraction ────────────────────────────────────────────────

def extract_files(zip_path: str, tmpdir: str) -> dict:
    needed = {
        "followers": "connections/followers_and_following/followers_1.json",
        "following": "connections/followers_and_following/following.json",
        "pending":   "connections/followers_and_following/pending_follow_requests.json",
    }
    with zipfile.ZipFile(zip_path, "r") as z:
        names_in_zip = z.namelist()
        paths = {}
        for key, path in needed.items():
            if path in names_in_zip:
                z.extract(path, tmpdir)
                paths[key] = os.path.join(tmpdir, path)
            else:
                raise ValueError(f"File not found inside ZIP: {path}")
    return paths


# ── Data parsing ──────────────────────────────────────────────────

def parse_data(paths: dict) -> dict:
    with open(paths["followers"], encoding="utf-8") as f:
        followers_raw  = json.load(f)
    followers_names = set(item["string_list_data"][0]["value"] for item in followers_raw)

    with open(paths["following"], encoding="utf-8") as f:
        following_raw  = json.load(f)
    following_list = [
        (item["title"], item["string_list_data"][0].get("timestamp", 0))
        for item in following_raw["relationships_following"]
    ]

    with open(paths["pending"], encoding="utf-8") as f:
        pending_raw = json.load(f)
    pending_list = [
        (item["string_list_data"][0]["value"], item["string_list_data"][0].get("timestamp", 0))
        for item in pending_raw["relationships_follow_requests_sent"]
    ]

    not_following_back = sorted(
        [(name, ts) for name, ts in following_list if name not in followers_names],
        key=lambda x: x[1],
    )
    return {
        "followers_count":    len(followers_names),
        "following_count":    len(following_list),
        "not_following_back": not_following_back,
        "pending":            sorted(pending_list, key=lambda x: x[1]),
    }


# ── Helpers (used by Flask template filter) ────────────────────────

def ts_to_date(ts) -> str:
    """Format timestamp for display. Used by app.py fmt_date filter."""
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y") if ts else "-"
