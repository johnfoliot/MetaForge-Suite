# --- START OF FILE settings.py ---
# ======================================================================
# MetaForge Tool Hub: Settings (V.Core - Build 5.3.4)
# Primary Role: Router / Dispatcher (Directive IV.3)
# Physical Location: \tools\settings\settings.py
# Build 5.3.4: Registered update_engine Spoke for Gatekeeper protocol.
# ======================================================================
import sys
import json
from pathlib import Path
from flask import jsonify, request
from common import config_handler

# --- 1. ENGINE REGISTRATION (Directive IV.3) ---
# Dynamically add the local engines directory to sys.path
ENGINE_DIR = Path(__file__).parent / "engines"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

# Import Spoke Engines
import pref_engine
import theme_engine
import taxonomy_engine
import audit_engine
import toolbar_engine
import help_engine
import update_engine  # New Spoke for Update Gatekeeper

def run_logic(action, tools_dir, env_path):
    """
    Universal Dispatcher: Routes incoming actions to specialized spokes.
    """
    # Standard Pathing Context
    base_dir = Path(tools_dir).parent
    data_dir = config_handler.DATA_DIR

    # --- [ DISPATCHER ] ---

    # A. UI Preferences (preferences.json)
    if action == "get_prefs":
        return pref_engine.get_prefs()
    if action == "save_prefs":
        return pref_engine.save_prefs()

    # B. Theme Discovery
    if action == "get_themes":
        return theme_engine.discover(base_dir)

    # C. Taxonomy Management (taxonomy.json)
    if action == "get_taxonomy":
        return taxonomy_engine.get()
    if action == "save_taxonomy":
        return taxonomy_engine.save()

    # D. Dependency Audits (Binaries)
    if action == "check_binaries":
        return audit_engine.run(base_dir)

    # E. Toolbar Discovery & Layout (toolbar_layout.json)
    if action == "get_discovery":
        return toolbar_engine.discover(tools_dir, data_dir)
    if action == "save_toolbar":
        return toolbar_engine.save(data_dir)

    # F. Environment Configuration (.env)
    if action == "get_env":
        return _handle_env_fetch(env_path)
    if action == "save_env":
        return _handle_env_save(env_path)

    # G. Help Documentation Aggregation
    if action == "get_help_docs":
        return help_engine.aggregate(tools_dir)

    # H. Update Gatekeeper (GitHub Manifest Comparison)
    if action == "check_updates":
        return update_engine.check_for_updates()

    return jsonify({"status": "error", "message": f"Action '{action}' unrecognized by Settings Hub."}), 400

# --- INTERNAL HELPERS (Transitionary) ---

def _handle_env_fetch(env_path):
    env_data = {}
    if env_path.exists():
        lines = env_path.read_text(encoding='utf-8').splitlines()
        for line in lines:
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env_data[k.strip()] = v.strip()
    return jsonify(env_data)

def _handle_env_save(env_path):
    try:
        new_config = request.json
        current_env = {}
        if env_path.exists():
            lines = env_path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                if '=' in line:
                    k, v = line.split('=', 1)
                    current_env[k.strip()] = v.strip()
        current_env.update(new_config)
        output = [f"{k}={v}" for k, v in current_env.items()]
        env_path.write_text("\n".join(output), encoding='utf-8')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS HUB END ---
# --- END OF FILE settings.py ---