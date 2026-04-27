# --- START OF FILE taxonomy_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Taxonomy Logic
# Physical Location: \tools\settings\engines\taxonomy_engine.py
# Build 5.2.9: Hardened persistence and scrubbing.
# ======================================================================
import json
from pathlib import Path
from flask import jsonify, request
from common import config_handler

def get():
    """
    Fetches the current taxonomy from the global data directory.
    """
    taxonomy_path = config_handler.DATA_DIR / "taxonomy.json"
    try:
        if taxonomy_path.exists():
            return jsonify(json.loads(taxonomy_path.read_text(encoding='utf-8')))
        return jsonify({"error": "Taxonomy file missing"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def save():
    """
    Overwrites (scrubs) the taxonomy.json with the provided Hub state.
    """
    taxonomy_path = config_handler.DATA_DIR / "taxonomy.json"
    try:
        new_taxonomy = request.json
        if not isinstance(new_taxonomy, dict):
            return jsonify({"status": "error", "message": "Invalid taxonomy format"}), 400
        
        # Physical Write: Performs a complete overwrite to ensure deleted keys are purged
        taxonomy_path.write_text(json.dumps(new_taxonomy, indent=4), encoding='utf-8')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS TAXONOMY ENGINE END ---
# --- END OF FILE taxonomy_engine.py ---