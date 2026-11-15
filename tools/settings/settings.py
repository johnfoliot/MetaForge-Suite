# --- START OF FILE settings.py ---
# ======================================================================
# MetaForge Tool Hub: Settings
# Primary Role: Router / Dispatcher
# Physical Location: \tools\settings\settings.py
# v2 (2026-11-15):
#  - Updates: check_updates / dismiss_update / last_update_check
#    (commit_update is gone: it marked the app "updated" without installing).
#  - check_binaries removed: dependency updates are a developer task and
#    ship inside a version update (John, 2026-11-15).
#  - save_env keeps the .env file's comments, blank lines and order.
#  - taxonomy_usage: track counts per genre / sub-genre.
# ======================================================================
import os
import re
import sys
from pathlib import Path

from flask import jsonify, request

from common import config_handler

ENGINE_DIR = Path(__file__).parent / "engines"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import pref_engine
import theme_engine
import taxonomy_engine
import toolbar_engine
import help_engine
import update_engine

ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def run_logic(action, tools_dir, env_path):
    base_dir = Path(tools_dir).parent
    data_dir = config_handler.DATA_DIR

    # A. Preferences (preferences.json)
    if action == "get_prefs":
        return pref_engine.get_prefs()
    if action == "save_prefs":
        return pref_engine.save_prefs()

    # B. Themes
    if action == "get_themes":
        return theme_engine.discover(base_dir)
    # Create a theme (v2, 2026-11-15)
    if action == "theme_template":
        return theme_engine.template()
    if action == "theme_values":
        return theme_engine.values()
    if action == "logo_preview":
        return theme_engine.logo_preview()
    if action == "save_custom_theme":
        return theme_engine.save_custom()
    if action == "delete_custom_theme":
        return theme_engine.delete_custom()

    # C. Genres (taxonomy.json)
    if action == "get_taxonomy":
        return taxonomy_engine.get()
    if action == "save_taxonomy":
        return taxonomy_engine.save()
    if action == "taxonomy_usage":
        return taxonomy_engine.usage()

    # D. Toolbar layout
    if action == "get_discovery":
        return toolbar_engine.discover(tools_dir, data_dir)
    if action == "save_toolbar":
        return toolbar_engine.save(data_dir)

    # E. Configuration (.env)
    if action == "get_env":
        return _handle_env_fetch(env_path)
    if action == "save_env":
        return _handle_env_save(env_path)

    # F. Help
    if action == "get_help_docs":
        return help_engine.aggregate(tools_dir)

    # G. Updates
    if action == "check_updates":
        return update_engine.check_for_updates()
    if action == "dismiss_update":
        return update_engine.dismiss_update()
    if action == "last_update_check":
        return update_engine.last_checked()

    return jsonify({"status": "error", "message": f"Settings doesn't recognise the action '{action}'."}), 400


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return re.sub(r'\\(["\\])', r"\1", v[1:-1])
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1]
    return v


def _handle_env_fetch(env_path):
    env_data = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                k, v = s.split("=", 1)
                env_data[k.strip()] = _unquote(v)
    return jsonify(env_data)


def _handle_env_save(env_path):
    """
    Updates values IN PLACE: comments, blank lines and order are kept; keys
    not already in the file are appended. 1.x rewrote the whole file as bare
    KEY=VALUE lines, losing every comment. A value with a space, # or quote is
    written in double quotes; a newline in a value is refused.
    """
    try:
        changes = request.json or {}
        if not isinstance(changes, dict):
            return jsonify({"status": "error", "message": "The settings weren't in the expected format."}), 400
        for k, v in changes.items():
            if not ENV_KEY.match(str(k)):
                return jsonify({"status": "error", "message": f"“{k}” isn't a valid setting name."}), 400
            if any(ch in str(v) for ch in "\r\n"):
                return jsonify({"status": "error", "message": f"The value for {k} can't contain a line break."}), 400

        def fmt(v):
            v = str(v)
            if v and not re.search(r"[\s#'\"]", v):
                return v
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'

        lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
        remaining = dict(changes)
        out = []
        for line in lines:
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                k = s.split("=", 1)[0].strip()
                if k in remaining:
                    out.append(f"{k}={fmt(remaining.pop(k))}")
                    continue
            out.append(line)
        for k, v in remaining.items():
            out.append(f"{k}={fmt(v)}")

        tmp = env_path.with_name(env_path.name + ".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        tmp.replace(env_path)
        # Tools read these with os.getenv(), loaded once at start-up; update
        # the running app too so a new key works without a restart.
        for k, v in changes.items():
            os.environ[k] = str(v)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"The configuration couldn't be saved: {e}"}), 500

# --- END OF FILE settings.py ---
