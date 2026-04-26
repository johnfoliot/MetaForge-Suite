# ======================================================================
# MetaForge Mini-Engine: Documentation Aggregator
# Physical Location: \tools\settings\engines\help_engine.py
# ======================================================================
import json
from pathlib import Path
from flask import jsonify

# --- SETTINGS HELP ENGINE ---

def aggregate(tools_dir):
    """
    Scans for help.mfi fragments across all tool directories.
    """
    docs = []
    
    if not tools_dir.exists():
        return jsonify([])

    for folder in tools_dir.iterdir():
        if folder.is_dir():
            help_file = folder / "help.mfi"
            
            # If the tool has a help fragment, ingest it
            if help_file.exists():
                name = folder.name # Fallback name
                manifest = folder / "manifest.json"
                
                # Attempt to get the professional name from the manifest
                if manifest.exists():
                    try:
                        with open(manifest, 'r', encoding='utf-8') as f:
                            m_data = json.load(f)
                            name = m_data.get("name", name)
                    except:
                        pass
                
                try:
                    docs.append({
                        "name": name,
                        "html": help_file.read_text(encoding='utf-8')
                    })
                except Exception as e:
                    print(f"Help Engine: Failed to read {help_file.name} in {folder.name}")

    # Return the collection, sorted by tool name
    return jsonify(sorted(docs, key=lambda x: x['name']))

# --- SETTINGS HELP ENGINE END ---