# ======================================================================
# MetaForge Tool Logic: Settings (V.Core - Build 5.1.2)
# Handles environment, discovery, taxonomy, and Full-Palette Parsing.
# Build 5.1.2: Hardened regex for modular CSS silos.
# ======================================================================
import json
import os
import re
import subprocess
from pathlib import Path
from flask import jsonify, request

def run_logic(action, tools_dir, env_path):
    """
    Mandatory entry point for the Universal Dispatcher.
    """
    
    # --- SETTINGS TOOL LOGIC ---

    # 1. Path Anchoring
    base_dir = Path(tools_dir).parent
    data_dir = base_dir / "data"
    bin_dir  = base_dir / "bin"
    css_dir  = base_dir / "ui" / "css"
    
    layout_path = data_dir / "toolbar_layout.json"
    taxonomy_path = data_dir / "taxonomy.json"
    pref_path = Path(os.getenv('APPDATA')) / "MetaForge" / "preferences.json"

    # --- ACTION: FETCH UI PREFERENCES ---
    if action == "get_prefs":
        try:
            if pref_path.exists():
                return jsonify(json.loads(pref_path.read_text(encoding='utf-8')))
            return jsonify({"theme_file": "default_theme.css"}) 
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: SAVE UI PREFERENCES ---
    if action == "save_prefs":
        try:
            if not pref_path.parent.exists():
                pref_path.parent.mkdir(parents=True, exist_ok=True)
            new_prefs = request.json
            current_prefs = json.loads(pref_path.read_text(encoding='utf-8')) if pref_path.exists() else {}
            current_prefs.update(new_prefs)
            pref_path.write_text(json.dumps(current_prefs, indent=4), encoding='utf-8')
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: THEME DISCOVERY (FULL PALETTE) ---
    if action == "get_themes":
        try:
            themes = []
            # Standard MetaForge variable set
            varnames = [
                '--bg-main', '--bg-accent', '--bg-stage', '--mf-gold', 
                '--text-output', '--text-message', '--status-success', 
                '--status-error', '--input-foreground', '--input-background'
            ]
            
            if css_dir.exists():
                for f in css_dir.glob("*_theme.css"):
                    content = f.read_text(encoding='utf-8')
                    palette = {}
                    
                    for var in varnames:
                        # Extract hex codes accurately from the modular files
                        match = re.search(rf'{var}:\s*(#[0-9a-fA-F]+)', content)
                        palette[var] = match.group(1) if match else "#333"

                    label = f.name.replace("_theme.css", "").replace("_", " ").title()
                    themes.append({
                        "file": f.name,
                        "name": label,
                        "palette": palette
                    })
            return jsonify(sorted(themes, key=lambda x: x['name']))
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: TAXONOMY HANDLER ---
    if action == "get_taxonomy":
        try:
            if taxonomy_path.exists(): return jsonify(json.loads(taxonomy_path.read_text(encoding='utf-8')))
            return jsonify({"error": "Taxonomy file missing"}), 404
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    if action == "save_taxonomy":
        try:
            new_taxonomy = request.json
            taxonomy_path.write_text(json.dumps(new_taxonomy, indent=2), encoding='utf-8')
            return jsonify({"status": "success"})
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    # --- ACTION: DEPENDENCY AUDIT ---
    if action == "check_binaries":
        audit_results = []
        targets = {"yt-dlp.exe": "--version", "ffmpeg.exe": "-version", "fpcalc.exe": "-version", "mp3val.exe": "-h", "sqlite3.exe": "--version"}
        for exe, flag in targets.items():
            exe_path = bin_dir / exe
            version_str = "Missing"; status = "error"
            if exe_path.exists():
                try:
                    res = subprocess.run([str(exe_path), flag], capture_output=True, text=True, timeout=5)
                    raw = res.stdout.strip()
                    if exe == "ffmpeg.exe": version_str = raw.split('version ')[1].split(' ')[0]
                    elif exe == "mp3val.exe": version_str = raw.split(' ')[1] if len(raw.split(' ')) > 1 else "Found"
                    elif exe == "sqlite3.exe": version_str = raw.split(' ')[0]
                    else: version_str = raw.split('\n')[0]
                    status = "ok"
                except: version_str = "Parse Error"
            audit_results.append({"name": exe, "version": version_str, "status": status})
        return jsonify(audit_results)

    # --- ACTION: TOOL DISCOVERY ---
    if action == "get_discovery":
        manifests = {}
        for folder in tools_dir.iterdir():
            if folder.is_dir():
                m_file = folder / "manifest.json"
                if m_file.exists():
                    try:
                        with open(m_file, 'r', encoding='utf-8') as f:
                            m = json.load(f)
                            if m.get('id'): manifests[m['id']] = m
                    except: pass
        layout = []
        if layout_path.exists():
            try: layout = json.loads(layout_path.read_text(encoding='utf-8'))
            except: layout = []
        return jsonify({"manifests": manifests, "layout": layout})

    if action == "save_toolbar":
        try:
            if not data_dir.exists(): data_dir.mkdir(parents=True, exist_ok=True)
            layout_path.write_text(json.dumps(request.json, indent=4), encoding='utf-8')
            return jsonify({"status": "success"})
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    if action == "get_env":
        env_data = {}
        if env_path.exists():
            lines = env_path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env_data[k.strip()] = v.strip()
        return jsonify(env_data)

    if action == "save_env":
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
        except Exception as e: return jsonify({"status": "error", "message": str(e)}), 500

    if action == "get_help_docs":
        docs = []
        for folder in tools_dir.iterdir():
            if folder.is_dir():
                h_file = folder / "help.mfi"
                if h_file.exists():
                    name = folder.name
                    m_file = folder / "manifest.json"
                    if m_file.exists():
                        try:
                            with open(m_file, 'r', encoding='utf-8') as f:
                                name = json.load(f).get("name", name)
                        except: pass
                    docs.append({"name": name, "html": h_file.read_text(encoding='utf-8')})
        return jsonify(docs)

    return jsonify({"status": "error", "message": f"Action '{action}' not recognized."}), 400

# --- SETTINGS TOOL LOGIC END ---