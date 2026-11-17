# ======================================================================
# MetaForge Mini-Engine: Preferences Handler
# Physical Location: \tools\settings\engines\pref_engine.py
# v2 (2026-11-17, theme folders): the chosen theme is saved as theme_id
# (its folder name). An older preferences file is carried over once: its
# theme_file_v2 / theme_file ("lavender_lemonade_theme.css") becomes
# theme_id "lavender_lemonade", and the 1.x keys (theme, theme_file,
# theme_file_v2) are removed. The file lives in config_handler.APPDATA_MF,
# so a sandbox test server never touches the real one.
# ======================================================================
import json

from flask import jsonify, request

from common import config_handler

OLD_THEME_KEYS = ("theme", "theme_file", "theme_file_v2")


def _path():
    return config_handler.APPDATA_MF / "preferences.json"


def _write(prefs):
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(prefs, indent=4), encoding="utf-8")
    tmp.replace(path)


def _migrate(prefs):
    """Older theme keys -> theme_id. True if anything changed."""
    if "theme_id" in prefs and not any(k in prefs for k in OLD_THEME_KEYS):
        return False
    if "theme_id" not in prefs:
        old = prefs.get("theme_file_v2") or prefs.get("theme_file") or ""
        prefs["theme_id"] = old.removesuffix("_theme.css") or "default"
    for k in OLD_THEME_KEYS:
        prefs.pop(k, None)
    return True


def get_prefs():
    """Fetches user UI preferences from APPDATA."""
    try:
        path = _path()
        if not path.exists():
            return jsonify({"theme_id": "default"})
        prefs = json.loads(path.read_text(encoding="utf-8"))
        if _migrate(prefs):
            _write(prefs)
        return jsonify(prefs)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def save_prefs():
    """Commits user UI preferences to APPDATA."""
    try:
        path = _path()
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        current.update(request.json or {})
        _migrate(current)
        _write(current)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- [ END OF PREF_ENGINE.PY ] ---
