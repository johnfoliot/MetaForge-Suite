# ======================================================================
# MetaForge Studio: first-run setup (server half of ui/html/setup.html)
# Physical Location: \ui\setup_engine.py
# v2 rebuild (2026-11-17). The 1.x page could never finish: its folder
# picker did nothing, its library scan returned the wrong data, and it
# saved to a route that didn't exist.
# ======================================================================
"""
Three jobs, used by the /setup/* routes in routes.py:

  scan(path)        Looks at the top of the music library and suggests how
                    it is organised (Basic / Standard / Enhanced). Reads a
                    small sample of folders only: never the whole library.
  check_keys(keys)  One tiny, free request to each service, to prove the
                    key works before it is saved (John, 2026-11-17: the
                    three keys are strictly required; a typo should be
                    caught here, not at the first Intelli-Tagger run).
  save(...)         Writes the settings file (.env) and, for an Enhanced
                    library, categories.json. Refuses if MetaForge is
                    already set up, so this can never overwrite settings.
"""
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from common.version import user_agent

AUDIO_EXT = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma",
             ".ape", ".wv", ".aif", ".aiff", ".dsf", ".dff", ".alac"}
# Disc and artwork folders inside an album don't make the library deeper.
_INNER = re.compile(r"^(cd|disc|disk)\s*\d+$|^(art|artwork|scans|covers?)$", re.I)
POLICIES = ("BASIC", "STANDARD", "ENHANCED")
# The app's name and project address only: no personal details go to the services (privacy rule).
USER_AGENT = user_agent()
TIMEOUT = 15


# ---------------------------------------------------------------- scan
def _visible_dirs(folder, limit=None):
    # os.scandir: on Windows the listing already says which entries are
    # folders, so this doesn't touch each one (21 s -> about 1 s on a large
    # library on a USB drive). `limit` stops early inside big folders.
    out = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                n = e.name
                if n.startswith((".", "$")) or n.lower() in ("system volume information", "recycler"):
                    continue
                try:
                    if e.is_dir():
                        out.append(Path(e.path))
                except OSError:
                    continue
                if limit and len(out) >= limit:
                    break
    except OSError:
        pass
    return sorted(out, key=lambda p: p.name.lower())


def _has_audio(folder):
    try:
        with os.scandir(folder) as it:
            return any(os.path.splitext(e.name)[1].lower() in AUDIO_EXT and e.is_file() for e in it)
    except OSError:
        return False


def _audio_depth(folder, depth=0, budget=None):
    """How many folder levels below `folder` the first music files sit
    (0 = in the folder itself). None if none found within 3 levels."""
    budget = budget if budget is not None else [60]
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    if _has_audio(folder):
        return depth
    if depth >= 3:
        return None
    best = None
    for child in _visible_dirs(folder, limit=6):
        d = _audio_depth(child, depth if _INNER.match(child.name) else depth + 1, budget)
        if d is not None and (best is None or d < best):
            best = d
            if best == depth + 1:
                break
    return best


def scan(path):
    root = Path(path or "")
    if not path or not root.is_dir():
        return {"status": "error", "message": "That folder can't be opened. Choose your music library folder again."}
    folders = _visible_dirs(root)
    if not folders:
        return {"status": "error", "message": "That folder has no folders inside it. Choose the top folder of your music library."}
    votes = {}
    for f in folders[:8]:
        d = _audio_depth(f)
        if d is not None:
            votes[d] = votes.get(d, 0) + 1
            if votes[d] >= 3:      # three folders agree: that's the answer
                break
    if not votes:
        return {"status": "error", "message": "No music files were found in the first few folders. Check that this is your music library folder."}
    depth = max(votes, key=lambda d: (votes[d], -d))
    policy = POLICIES[min(depth, 2)]
    return {"status": "ok", "policy": policy, "folders": [f.name for f in folders]}


# ---------------------------------------------------------- key checks
def _check(name, fn):
    try:
        ok, msg = fn()
    except requests.RequestException:
        return {"ok": False, "reason": "network",
                "message": f"{name} couldn't be reached. Check your internet connection and try again."}
    return {"ok": ok, "reason": None if ok else "refused", "message": msg}


def _gemini(key):
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     params={"pageSize": 1}, headers={"x-goog-api-key": key, "User-Agent": USER_AGENT},
                     timeout=TIMEOUT)
    if r.status_code == 200:
        return True, "Gemini accepted the key."
    return False, "Google didn't accept this Gemini key. Copy it again from Google AI Studio."


def _discogs(token):
    r = requests.get("https://api.discogs.com/oauth/identity",
                     headers={"Authorization": f"Discogs token={token}", "User-Agent": USER_AGENT},
                     timeout=TIMEOUT)
    if r.status_code == 200:
        return True, "Discogs accepted the token."
    return False, "Discogs didn't accept this token. Copy it again from your Discogs developer settings."


def _acoustid(key):
    # A lookup for a made-up track ID: a working key gets an empty answer,
    # a wrong key gets error 4 ("invalid API key").
    r = requests.get("https://api.acoustid.org/v2/lookup",
                     params={"client": key, "trackid": str(uuid.uuid4()), "format": "json"},
                     headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if data.get("status") == "ok":
        return True, "AcoustID accepted the key."
    if (data.get("error") or {}).get("code") == 4:
        return False, "AcoustID didn't accept this application key. Copy it again from acoustid.org."
    raise requests.RequestException("unexpected answer")


def check_keys(keys):
    return {
        "gemini": _check("Google Gemini", lambda: _gemini(keys["gemini"])),
        "discogs": _check("Discogs", lambda: _discogs(keys["discogs"])),
        "acoustid": _check("AcoustID", lambda: _acoustid(keys["acoustid"])),
    }


# ---------------------------------------------------------------- save
EMAIL_OK = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean(v):
    # One line, no stray spaces from copy-and-paste; nothing that could
    # break the .env format.
    return re.sub(r"[\r\n]", "", str(v or "")).strip()


def save(env_path, appdata_dir, data):
    env_path = Path(env_path)
    if env_path.exists():
        return {"status": "error", "message": "MetaForge is already set up. Change settings in Settings."}, 409

    v = {k: _clean(data.get(k)) for k in ("library", "policy", "email", "gemini", "discogs", "acoustid")}
    problems = {}
    if not v["library"] or not Path(v["library"]).is_dir():
        problems["library"] = "Choose your music library folder."
    if v["policy"] not in POLICIES:
        problems["policy"] = "Choose how your library is organised."
    if not EMAIL_OK.match(v["email"]):
        problems["email"] = "Enter your email address, for example name@example.com."
    for k in ("gemini", "discogs", "acoustid"):
        if not v[k]:
            problems[k] = "This key is required."
    categories = [_clean(c) for c in (data.get("categories") or []) if _clean(c)]
    if v["policy"] == "ENHANCED" and not categories:
        problems["categories"] = "Tick at least one category folder."
    if problems:
        return {"status": "invalid", "problems": problems}, 400

    # Server-side too, so the check can't be skipped.
    checks = check_keys(v)
    if not all(c["ok"] for c in checks.values()):
        return {"status": "keys", "checks": checks}, 400

    appdata_dir = Path(appdata_dir)
    appdata_dir.mkdir(parents=True, exist_ok=True)
    if v["policy"] == "ENHANCED":
        (appdata_dir / "categories.json").write_text(json.dumps({
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "silos": categories,
        }, indent=4), encoding="utf-8")
    # Same keys and order Settings > Configuration & keys shows.
    lines = [
        f"USER_EMAIL={v['email']}",
        f"LIBRARY_ROOT={v['library']}",
        f"ACOUSTID_APPLICATION_KEY={v['acoustid']}",
        "ACOUSTID_USER_KEY=",
        f"GEMINI_KEY={v['gemini']}",
        f"DISCOGS_TOKEN={v['discogs']}",
        f"MF_FILING_POLICY={v['policy']}",
        "MF_UNPACKER_CONSENT=FALSE",
        'MF_UNPACKER_LOCKED_CATEGORY=""',
        'MF_UNPACKER_LOCKED_ARTIST=""',
    ]
    tmp = env_path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(env_path)
    return {"status": "ok", "checks": checks}, 200
# --- END OF FILE setup_engine.py ---
