# ======================================================================
# MetaForge Tool Logic: Settings (V.Core - Build 3.6.2)
# Handles environment management, tool discovery, and help aggregation.
# ======================================================================
import json
import os
from pathlib import Path
from flask import jsonify, request

def run_logic(action, tools_dir, env_path):
    """
    Mandatory entry point for the Universal Dispatcher.
    Build 3.6.2: Hardened pathing for toolbar_layout discovery.
    """
    # Establish Data Path - Explicit fallback for standalone vs. suite context
    base_dir = Path(tools_dir).parent
    data_dir = base_dir / "data"
    layout_path = data_dir / "toolbar_layout.json"
    
    # Debug print to server console for verify
    if action == "get_discovery":
        print(f"METAFORGE DEBUG: Looking for layout at {layout_path}")

    # --- ACTION: FETCH .ENV DATA ---
    if action == "get_env":
        env_data = {}
        if env_path.exists():
            lines = env_path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    if k.strip() != "ENABLED_TOOLS":
                        env_data[k.strip()] = v.strip()
        return jsonify(env_data)

    # --- ACTION: TOOL DISCOVERY ---
    if action == "get_discovery":
        manifests = {}
        # 1. Aggregate all manifests from the tools directory
        for folder in tools_dir.iterdir():
            manifest_file = folder / "manifest.json"
            if manifest_file.exists():
                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        m = json.load(f)
                        manifests[m['id']] = m
                except Exception as e:
                    print(f"Settings Discovery Error: {e}")
        
        # 2. Load the layout state with error logging
        layout = []
        if layout_path.exists():
            try:
                layout_content = layout_path.read_text(encoding='utf-8')
                layout = json.loads(layout_content)
            except Exception as e:
                print(f"METAFORGE ERROR: Failed to parse toolbar_layout.json: {e}")
                layout = []
        else:
            print(f"METAFORGE ERROR: toolbar_layout.json NOT FOUND at {layout_path}")
        
        return jsonify({"manifests": manifests, "layout": layout})

    # --- ACTION: SAVE TOOLBAR LAYOUT ---
    if action == "save_toolbar":
        try:
            if not data_dir.exists():
                data_dir.mkdir(parents=True, exist_ok=True)
            new_layout = request.json
            layout_path.write_text(json.dumps(new_layout, indent=4), encoding='utf-8')
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: HELP AGGREGATOR ---
    if action == "get_help_docs":
        docs = []
        for folder in tools_dir.iterdir():
            if folder.is_dir():
                help_file = folder / "help.mfi"
                if help_file.exists():
                    name = folder.name
                    manifest = folder / "manifest.json"
                    if manifest.exists():
                        try:
                            with open(manifest, 'r', encoding='utf-8') as f:
                                name = json.load(f).get("name", name)
                        except: pass
                    docs.append({
                        "name": name,
                        "html": help_file.read_text(encoding='utf-8')
                    })
        return jsonify(docs)

    # --- ACTION: SAVE ENVIRONMENT ---
    if action == "save_env":
        try:
            new_config = request.json
            lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []
            current_env = {}
            for line in lines:
                if '=' in line:
                    k, v = line.split('=', 1)
                    current_env[k.strip()] = v.strip()
            current_env.update(new_config)
            current_env.pop("ENABLED_TOOLS", None)
            output = [f"{k}={v}" for k, v in current_env.items()]
            env_path.write_text("\n".join(output), encoding='utf-8')
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": f"Action '{action}' not recognized."}), 400