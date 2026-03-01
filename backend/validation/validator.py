"""
validator.py
-----------
ZIP structure and size validation. Returns (True, None) or (False, list of error messages).
"""

import os
import zipfile

REQUIRED_TOP_DIR = "connections"
REQUIRED_SUBDIR = "connections/followers_and_following"
REQUIRED_FILES = [
    "connections/followers_and_following/followers_1.json",
    "connections/followers_and_following/following.json",
    "connections/followers_and_following/pending_follow_requests.json",
]


def _normalize(name: str) -> str:
    return name.lstrip("/").replace("\\", "/")


def _top_level_dirs(names: list[str]) -> set[str]:
    out = set()
    for n in names:
        n = _normalize(n)
        if not n or n == ".":
            continue
        parts = n.split("/")
        if parts[0]:
            out.add(parts[0])
    return out


def _files_in_subdir(names: list[str], subdir: str) -> list[str]:
    subdir = _normalize(subdir).rstrip("/") + "/"
    out = []
    for n in names:
        n = _normalize(n)
        if n.startswith(subdir) and "/" in n[len(subdir):]:
            continue
        if n.startswith(subdir) and not n.endswith("/"):
            out.append(n)
    return out


def _has_non_json_in_subdir(names: list[str], subdir: str) -> list[str]:
    bad = []
    for n in _files_in_subdir(names, subdir):
        if not n.lower().endswith(".json"):
            bad.append(n.split("/")[-1])
    return bad


def validate_zip(zip_path: str, max_bytes: int) -> tuple[bool, list[str] | None]:
    """
    Validate ZIP path. Returns (True, None) if valid, else (False, list of error strings).
    Does not raise; catches exceptions and returns them as error messages.
    """
    errors: list[str] = []

    try:
        if not os.path.isfile(zip_path):
            return False, ["File not found or not a file."]

        size = os.path.getsize(zip_path)
        if size > max_bytes:
            mb = max_bytes / (1024 * 1024)
            errors.append(f"File size ({size / (1024*1024):.1f} MB) exceeds the maximum allowed ({mb:.0f} MB). Request a smaller date range in Instagram.")

        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        return False, ["File is not a valid ZIP archive."]
    except Exception as e:
        return False, [f"Could not read file: {e!s}"]

    if errors:
        return False, errors

    normalized = [_normalize(n) for n in names]
    top_dirs = _top_level_dirs(normalized)

    if top_dirs != {REQUIRED_TOP_DIR}:
        if not top_dirs:
            errors.append("ZIP has no folders — use an export that includes 'connections'.")
        elif REQUIRED_TOP_DIR not in top_dirs:
            errors.append("ZIP is missing the 'connections' folder.")
        else:
            extra = top_dirs - {REQUIRED_TOP_DIR}
            n_extra = len(extra)
            errors.append(
                f"The tool needs only the 'Connections' (followers and following) data. "
                f"Your ZIP has {n_extra} other folder{'s' if n_extra != 1 else ''} too."
            )

    allowed_prefix = REQUIRED_SUBDIR + "/"
    for n in normalized:
        if n.endswith("/") or n == REQUIRED_TOP_DIR or n == REQUIRED_SUBDIR:
            continue
        if n.startswith(REQUIRED_TOP_DIR + "/") and not n.startswith(allowed_prefix):
            errors.append(
                "The tool needs only 'Connections' → 'followers and following'. "
                "Your export includes other Connection types (e.g. contacts)."
            )
            break

    non_json = _has_non_json_in_subdir(normalized, REQUIRED_SUBDIR)
    if non_json:
        errors.append(
            "The tool reads JSON only. Your file has HTML. "
            "You must choose JSON as the format when creating the export (Step 5: date range and format)."
        )

    missing = [req.split("/")[-1] for req in REQUIRED_FILES if not any(_normalize(n) == req for n in names)]
    if missing:
        errors.append(f"Required file(s) missing: {', '.join(missing)}. Usually caused by wrong format (need JSON) or wrong selection (need only Connections).")

    if errors:
        errors.append(
            "→ What to do: In the Instagram export — Step 4 (Customize): uncheck all options, leave only 'Followers and following' selected. "
            "Step 5: choose JSON format, then Export."
        )

    if errors:
        return False, errors
    return True, None
