# --- START OF FILE update_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Update Check
# Physical Location: \tools\settings\engines\update_engine.py
# v2 (2026-11-15) rewrite. 1.x problems fixed:
#  - It crashed on every check ("System config mismatch": it relied on a
#    config_handler.UPDATE_MANIFEST that doesn't exist).
#  - The "installed version" was a JSON file the screen overwrote when you
#    clicked View details OR Dismiss, so the app could claim to be updated
#    with nothing installed. The version is now common/version.APP_VERSION.
#  - "Newer" was "different" (string inequality); now a real version order.
#  - HTTPS certificate checks were switched off and the remote text was put
#    into the page as HTML; now verified HTTPS, plain text, GitHub-only links.
# What an update does (John, 2026-11-15): announce it and link to the GitHub
# release page; you download it yourself. An installer comes later.
# ======================================================================
import json
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from flask import jsonify, request

from common import config_handler
from common.version import APP_VERSION, is_newer, parse_version, user_agent

REMOTE_URL = "https://raw.githubusercontent.com/johnfoliot/MetaForge-Suite/main/deploy/updates.json"
ALLOWED_LINK_HOSTS = {"github.com", "www.github.com"}

# TEST MODE (developers only): if this file exists, it's read INSTEAD of
# GitHub, and the screen says so. dev/use_update_test.py switches between
# the ready-made scenarios in dev/update_tests/. It lives in the build
# folder's dev/ (never in data/, which the 1.x build shares).
TEST_FILE = config_handler.PROJECT_ROOT / "dev" / "update_test.json"


def _prefs_path():
    return config_handler.APPDATA_MF / "preferences.json" if hasattr(config_handler, "APPDATA_MF") \
        else Path.home() / "AppData" / "Roaming" / "MetaForge" / "preferences.json"


def _read_prefs():
    try:
        return json.loads(_prefs_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_prefs(changes):
    p = _prefs_path()
    prefs = _read_prefs()
    prefs.update(changes)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(prefs, indent=4), encoding="utf-8")


def _fetch_remote():
    """Returns (data, source_label). Verified HTTPS (the default context)."""
    if TEST_FILE.exists():
        return json.loads(TEST_FILE.read_text(encoding="utf-8-sig")), f"TEST FILE {TEST_FILE}"
    req = urllib.request.Request(f"{REMOTE_URL}?t={int(time.time())}", headers={"User-Agent": user_agent()})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8-sig")), "GitHub"


def _normalise(remote):
    """
    Current format (schema 3):
      {"schema_version": 3, "latest_version": "2.0.1", "released": "2026-12-01",
       "priority": "optional" | "required", "title": "...", "notes": "plain text",
       "url": "https://github.com/johnfoliot/MetaForge-Suite/releases/tag/v2.0.1"}
    The 1.x-era file on GitHub (schema 2: manifest_metadata.installed_version)
    is still understood: its version is treated as the latest published one.
    """
    if "latest_version" in remote:
        return remote
    meta = remote.get("manifest_metadata") or {}
    return {"latest_version": meta.get("installed_version"), "title": "", "notes": "", "url": "", "priority": "optional"}


def _safe_link(url):
    try:
        u = urlparse(url or "")
        return url if u.scheme == "https" and u.hostname in ALLOWED_LINK_HOSTS else ""
    except Exception:
        return ""


def check_for_updates():
    now = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    try:
        remote, source = _fetch_remote()
    except Exception as e:
        return jsonify({"status": "error", "current_version": APP_VERSION,
                        "message": f"Couldn't reach the update information ({e.__class__.__name__}). "
                                   "Check the internet connection and try again."})
    info = _normalise(remote)
    latest = info.get("latest_version")
    if parse_version(latest) is None:
        return jsonify({"status": "error", "current_version": APP_VERSION,
                        "message": "The update information couldn't be read (no valid version number in it)."})

    prefs = _read_prefs()
    _write_prefs({"last_update_check": now})
    newer = is_newer(latest, APP_VERSION)
    required = (info.get("priority") or "").lower() == "required"
    dismissed = newer and not required and prefs.get("dismissed_update_version") == latest

    return jsonify({
        "status": "update_available" if newer and not dismissed else "up_to_date",
        "current_version": APP_VERSION,
        "latest_version": latest,
        "dismissed_version": latest if dismissed else None,
        "priority": "required" if required else "optional",
        "title": str(info.get("title") or f"MetaForge Studio {latest}"),
        "notes": str(info.get("notes") or ""),
        "released": str(info.get("released") or ""),
        "url": _safe_link(info.get("url")),
        "last_checked": now,
        "test_mode": source.startswith("TEST"),
        "source": source,
    })


def dismiss_update():
    """'Don't tell me about this version again.' Never touches the app's version."""
    version = (request.json or {}).get("version")
    if parse_version(version) is None:
        return jsonify({"status": "error", "message": "No valid version to dismiss."}), 400
    _write_prefs({"dismissed_update_version": version})
    return jsonify({"status": "success"})


def last_checked():
    return jsonify({"current_version": APP_VERSION, "last_checked": _read_prefs().get("last_update_check"),
                    "test_mode": TEST_FILE.exists()})

# --- END OF FILE update_engine.py ---
