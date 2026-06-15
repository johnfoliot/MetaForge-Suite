# ======================================================================
# MetaForge Mini-Engine: Toolbar Discovery & Persistence
# Physical Location: \tools\settings\engines\toolbar_engine.py
# ======================================================================
import json
from pathlib import Path
from flask import jsonify, request

# --- SETTINGS TOOLBAR ENGINE ---

def discover(tools_dir, data_dir):
    """
    Scans the tools directory to aggregate manifests and loads the layout state.
    """
    manifests = {}
    
    # 1. Pass 1: Scan for all valid manifests in the tools directory
    if tools_dir.exists():
        for folder in tools_dir.iterdir():
            if folder.is_dir():
                manifest_file = folder / "manifest.json"
                if manifest_file.exists():
                    try:
                        with open(manifest_file, 'r', encoding='utf-8') as f:
                            m = json.load(f)
                            # Key by tool ID for the frontend merger
                            if m.get('id'):
                                manifests[m['id']] = m
                    except Exception as e:
                        print(f"Toolbar Engine: Skipping malformed manifest in {folder.name}")

    # 2. Pass 2: Load the user's saved layout/order state
    layout = []
    layout_path = data_dir / "toolbar_layout.json"
    if layout_path.exists():
        try:
            layout = json.loads(layout_path.read_text(encoding='utf-8'))
        except:
            layout = []
            
    return jsonify({
        "manifests": manifests, 
        "layout": layout
    })

def save(data_dir):
    """
    Commits the normalized toolbar sequence to the physical JSON file.
    """
    layout_path = data_dir / "toolbar_layout.json"
    try:
        if not data_dir.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            
        new_layout = request.json
        layout_path.write_text(json.dumps(new_layout, indent=4), encoding='utf-8')
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- SETTINGS TOOLBAR ENGINE END ---