# ======================================================================
# MetaForge Mini-Engine: Settings > About
# Physical Location: \tools\settings\engines\about_engine.py
# ======================================================================
"""
The About page (2026-11-19): MetaForge's own licence, and the licences of
everything it is built on.

One source for each thing:
  tools/settings/about.mfi          the page's wording (John edits it)
  LICENSE                           the GNU GPL, version 3 (project root)
  licenses/components.json          programs, fonts and images (hand-kept)
  licenses/python_libraries.json    Python libraries (dev/build_notices.py)
  licenses/texts/                   the licence texts shown in the dialog

Everything is read from files shipped with MetaForge: no internet needed.
"""
import json
from pathlib import Path

from flask import jsonify, request

from common import config_handler
from common.version import APP_VERSION, PROJECT_URL

LICENCE_DIR = config_handler.PROJECT_ROOT / "licenses"
TEXT_DIR = LICENCE_DIR / "texts"
PAGE = Path(__file__).resolve().parent.parent / "about.mfi"


def _read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def info():
    """Everything the About tab shows."""
    try:
        html = PAGE.read_text(encoding="utf-8")
    except OSError:
        return jsonify({"status": "error", "message": "The About page's text (about.mfi) is missing."}), 500
    parts = _read_json(LICENCE_DIR / "components.json", {})
    libs = _read_json(LICENCE_DIR / "python_libraries.json", {})
    have = {p.name for p in TEXT_DIR.glob("*.txt")} if TEXT_DIR.is_dir() else set()

    def clean(rows):
        # A licence can only be opened if its text is really here.
        return [dict(r, text=r.get("text") if r.get("text") in have else "") for r in rows or []]

    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "project_url": PROJECT_URL,
        "html": html,
        "programs": clean(parts.get("programs")),
        "fonts": clean(parts.get("fonts")),
        "images": clean(parts.get("images")),
        "libraries": libs.get("libraries") or [],
        "libraries_listed_on": libs.get("generated") or "",
    })


def licence_text():
    """One licence text, by file name. Only a file that is actually in
    licenses/texts is served: the name is matched against the folder's own
    listing, never joined into a path."""
    name = (request.args.get("name") or "").strip()
    match = next((p for p in TEXT_DIR.glob("*.txt") if p.name == name), None) if TEXT_DIR.is_dir() else None
    if match is None:
        return jsonify({"status": "error", "message": "That licence text isn't included with MetaForge."}), 404
    try:
        return jsonify({"status": "ok", "name": match.name, "text": match.read_text(encoding="utf-8", errors="replace")})
    except OSError as e:
        return jsonify({"status": "error", "message": f"The licence text couldn't be read ({e})."}), 500
