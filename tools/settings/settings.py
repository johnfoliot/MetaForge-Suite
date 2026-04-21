# ======================================================================
# MetaForge Tool Logic: Settings (V.Core)
# Handles environment management, tool discovery, and help aggregation.
# ======================================================================
import json
from flask import jsonify, request

def run_logic(action, tools_dir, env_path):
    """
    Mandatory entry point for the Universal Dispatcher.
    URL Pattern: /run_tool_logic/settings/<action>
    """
    
    # --- ACTION: FETCH .ENV DATA ---
    if action == "get_env":
        env_data = {}
        if env_path.exists():
            lines = env_path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env_data[k.strip()] = v.strip()
        return jsonify(env_data)

    # --- ACTION: TOOL DISCOVERY (Personalization) ---
    if action == "get_discovery":
        all_tools = []
        for folder in tools_dir.iterdir():
            manifest = folder / "manifest.json"
            if manifest.exists():
                try:
                    with open(manifest, 'r', encoding='utf-8') as f:
                        all_tools.append(json.load(f))
                except Exception as e:
                    print(f"Settings Error: Failed to read manifest in {folder.name}: {e}")
        
        # ADDED: Numerical Sort by 'order' (1-99)
        all_tools.sort(key=lambda x: x.get("order", 99))
        
        # Determine currently enabled IDs from the .env
        enabled_ids = []
        if env_path.exists():
            content = env_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                if line.startswith("ENABLED_TOOLS="):
                    # Extract ids from "id:order,id:order"
                    raw_tools = line.split('=')[1].split(',')
                    enabled_ids = [t.split(':')[0] for t in raw_tools if ':' in t]
        
        return jsonify({"all_tools": all_tools, "enabled_ids": enabled_ids})

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
            
            # Update with new values from the UI
            current_env.update(new_config)
            
            # Write back to file
            output = [f"{k}={v}" for k, v in current_env.items()]
            env_path.write_text("\n".join(output), encoding='utf-8')
            
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": f"Action '{action}' not recognized."}), 400