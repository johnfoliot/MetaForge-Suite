# ======================================================================
# MetaForge Mini-Engine: Preferences Handler
# Physical Location: \tools\settings\engines\pref_engine.py
# ======================================================================
import json
import os
from pathlib import Path
from flask import jsonify, request

def get_prefs():
    """Fetches user UI preferences from APPDATA."""
    pref_path = Path(os.getenv('APPDATA')) / "MetaForge" / "preferences.json"
    try:
        if pref_path.exists():
            return jsonify(json.loads(pref_path.read_text(encoding='utf-8')))
        # Fallback if file doesn't exist yet
        return jsonify({"theme_file": "default_theme.css"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def save_prefs():
    """Commits user UI preferences to APPDATA."""
    pref_path = Path(os.getenv('APPDATA')) / "MetaForge" / "preferences.json"
    try:
        if not pref_path.parent.exists():
            pref_path.parent.mkdir(parents=True, exist_ok=True)
        
        new_prefs = request.json
        current_prefs = {}
        if pref_path.exists():
            current_prefs = json.loads(pref_path.read_text(encoding='utf-8'))
        
        current_prefs.update(new_prefs)
        pref_path.write_text(json.dumps(current_prefs, indent=4), encoding='utf-8')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- [ END OF PREF_ENGINE.PY ] ---