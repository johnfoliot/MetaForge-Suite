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
  tools/<id>/licenses.json          a tool's own third-party parts (optional)
  tools/<id>/licenses/*.txt         licence texts that tool brings (optional)

A tool that brings a third-party program with it (a plug-in such as YouTube
to MP3 and yt-dlp) lists it in its own folder, in the same shape as
components.json. The rows appear on the About page while the tool's folder
is installed and disappear with it: nothing in the suite names the tool.

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


KINDS = ("programs", "fonts", "images")


def _tool_folders():
    """Installed tools: the folders in tools/ that have a manifest."""
    if not config_handler.TOOLS_DIR.is_dir():
        return []
    return sorted(f for f in config_handler.TOOLS_DIR.iterdir() if (f / "manifest.json").is_file())


def _tool_texts(folder):
    d = folder / "licenses"
    return {p.name for p in d.glob("*.txt")} if d.is_dir() else set()


def _tool_parts(have):
    """The rows each installed tool adds, by kind. A row's licence text is
    looked for in the tool's own licenses/ folder first (the row then carries
    'tool', so the dialog knows where to read it), then in the suite's."""
    out = {k: [] for k in KINDS}
    for folder in _tool_folders():
        parts = _read_json(folder / "licenses.json", None)
        if not isinstance(parts, dict):
            continue
        own = _tool_texts(folder)
        for kind in KINDS:
            rows = parts.get(kind)
            for r in rows if isinstance(rows, list) else []:
                if not isinstance(r, dict) or not r.get("name"):
                    continue
                text = r.get("text") or ""
                if text in own:
                    out[kind].append(dict(r, text=text, tool=folder.name))
                else:
                    out[kind].append(dict(r, text=text if text in have else "", tool=""))
    return out


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

    extra = _tool_parts(have)

    return jsonify({
        "status": "ok",
        "version": APP_VERSION,
        "project_url": PROJECT_URL,
        "html": html,
        "programs": clean(parts.get("programs")) + extra["programs"],
        "fonts": clean(parts.get("fonts")) + extra["fonts"],
        "images": clean(parts.get("images")) + extra["images"],
        "libraries": libs.get("libraries") or [],
        "libraries_listed_on": libs.get("generated") or "",
    })


def licence_text():
    """One licence text, by file name (and, for a text a tool brings, that
    tool's folder name). Only a file that is actually in licenses/texts or
    in an installed tool's licenses/ folder is served: both names are matched
    against the folders' own listings, never joined into a path."""
    name = (request.args.get("name") or "").strip()
    tool = (request.args.get("tool") or "").strip()
    if tool:
        folder = next((f for f in _tool_folders() if f.name == tool), None)
        text_dir = folder / "licenses" if folder else None
    else:
        text_dir = TEXT_DIR
    match = next((p for p in text_dir.glob("*.txt") if p.name == name), None) if text_dir and text_dir.is_dir() else None
    if match is None:
        return jsonify({"status": "error", "message": "That licence text isn't included with MetaForge."}), 404
    try:
        return jsonify({"status": "ok", "name": match.name, "text": match.read_text(encoding="utf-8", errors="replace")})
    except OSError as e:
        return jsonify({"status": "error", "message": f"The licence text couldn't be read ({e})."}), 500
