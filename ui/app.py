# ======================================================================
# MetaForge Studio: Master Server Engine (V.Core)
# File Location: \MetaForge Suite\ui\app.py
# ======================================================================
import os
import sys
import time
from pathlib import Path

# --- [ SECTION 1: THE PATH FIXER ] ---
# Base path is D:\MetaForge Suite\ui
UI_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = UI_DIR.parent.resolve()

# Add root to sys.path so we can see the 'common' and 'ui' folders
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- [ EXTERNAL ROUTE LOADER ] ---
import routes

# --- [ SYSTEM IMPORTS ] ---
import threading
import sqlite3
import webview
import ctypes
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify
from dotenv import load_dotenv

# Import our new central config brain
from common import config_handler

# --- [ SECTION 2: ARCHITECTURAL CONSTANTS ] ---
# We pull these directly from our config_handler to ensure one source of truth
APPDATA_ROOT = config_handler.APPDATA_MF
ENV_PATH     = config_handler.ENV_PATH
DATA_DIR     = config_handler.DATA_DIR
LOGS_DIR     = config_handler.LOGS_DIR
DB_PATH      = config_handler.DB_PATH

# --- [ SECTION 3: BOOTSTRAP THE CONFIG ] ---
# Pathing aligned to D:\MetaForge Suite\
UI_ROOT   = PROJECT_ROOT / "ui"
HTML_DIR  = UI_ROOT / "html"
TOOLS_DIR = PROJECT_ROOT / "tools"

# static_folder is UI_ROOT so we can access /css/ and /js/
app = Flask(__name__, template_folder=str(HTML_DIR), static_folder=str(UI_ROOT), static_url_path='/ui')
window = None 

# --- [ SECTION 4: UTILITY FUNCTIONS ] ---
def is_setup_required():
    return not ENV_PATH.exists()

def set_file_attribute(path, attribute):
    if os.name == 'nt':
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attribute)
        except Exception: pass

def initialize_database():
    # Ensure the AppData folders exist
    APPDATA_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE, artist TEXT, album TEXT, title TEXT, acoustid TEXT)''')
    conn.commit()
    conn.close()
    
# --- TOOL DISCOVERY LOGIC ---
import json

def get_dynamic_toolbar():
    """
    Scans the tools directory for manifest.json files and returns a sorted list
    of enabled/required tools based on the defined 'order' key.
    """
    tools = []
    if not TOOLS_DIR.exists():
        return tools

    for folder in TOOLS_DIR.iterdir():
        if folder.is_dir():
            manifest_path = folder / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Tool must be enabled OR required to appear in the toolbar
                        if data.get("enabled", True) or data.get("required", False):
                            tools.append(data)
                except Exception as e:
                    print(f"MetaForge Error: Failed to parse manifest in {folder.name}: {e}")
    
    # Sort by 'order' key; defaults to 99 to push un-ordered tools to the end
    tools.sort(key=lambda x: x.get("order", 99))
    return tools
# --- TOOL DISCOVERY LOGIC END ---

# --- [ SECTION 5: CORE UI ROUTES ] ---

@app.route('/')
def home():
    """
    Main entry point with Bootstrap Guard and Diagnostic Logging.
    If .env is missing, serves setup.html from the UI/HTML folder.
    """
    if is_setup_required(): 
        # Serve setup.html directly from the localized HTML directory
        return send_from_directory(str(UI_ROOT / "html"), 'setup.html')
        
    # --- LOGIC FOR REGISTERED USERS ---
    toolbar_data = get_dynamic_toolbar()
    
    # DIAGNOSTIC: Print discovery results to terminal
    print(f"DEBUG: Discovery Scan found {len(toolbar_data)} tools.")
    for t in toolbar_data:
        print(f" - Tool: {t.get('id')} (Order: {t.get('order')})")
    
    # Calculate track count for footer diagnostic
    track_count = "0"
    if DB_PATH.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            track_count = f"{conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]:,}"
            conn.close()
        except Exception: 
            track_count = "DB ERROR"
            
    return render_template('index.html', 
                           track_count=track_count, 
                           version_id=time.time(),
                           tools=toolbar_data)

@app.route('/complete_setup', methods=['POST'])
def complete_setup():
    """
    Receives initial configuration and writes the .env file to AppData.
    """
    data = request.json
    lines = [
        f"USER_EMAIL={data['email']}",
        f"LIBRARY_ROOT={data['lib_root']}",
        f"ACOUSTID_KEY={data['acoustid']}",
        f"GEMINI_KEY={data['gemini']}",
        f"ENABLED_TOOLS={data['default_tools']}"
    ]
    
    try:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"ERROR: Failed to write .env: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/tool_asset/<tool_id>/<filename>')
def serve_tool_asset(tool_id, filename):
    """Serves icons and modular tool JS from tool directories."""
    target_dir = TOOLS_DIR / tool_id
    if not target_dir.exists():
        return "Tool Asset Not Found", 404
    return send_from_directory(str(target_dir), filename)

@app.route('/ui/<type>/<path:filename>')
def serve_ui(type, filename):
    """Serves global CSS, JS, and Images from the UI root."""
    response = send_from_directory(str(UI_ROOT / type), filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    """Loads modular tool .mfi templates."""
    clean_id = tool_id.split('?')[0]
    target = TOOLS_DIR / clean_id / f"{clean_id}.mfi"
    if not target.exists():
        return f"Tool '{clean_id}' Not Found", 404
    return target.read_text(encoding='utf-8')

@app.route('/select_folder')
def select_folder():
    """Direct route for the setup.html to access the folder picker."""
    global api_bridge
    path = api_bridge.select_folder()
    return jsonify({"path": path})

# --- [ THE HANDOFF ] ---
routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, set_file_attribute)

# --- [ SECTION 5: CORE UI ROUTES END ] ---

# --- [ SECTION 6: ENGINE STARTUP ] ------------------------------------
class MetaForgeAPI:
    def select_folder(self):
        global window
        if window:
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            return result[0] if result else None
        return None

def run_flask():
    app.run(port=5000, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    initialize_database()
    if ENV_PATH.exists(): 
        load_dotenv(ENV_PATH)
    
    api_bridge = MetaForgeAPI()
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    window = webview.create_window(
        'MetaForge Studio', 
        'http://127.0.0.1:5000', 
        js_api=api_bridge,
        width=1280, 
        height=800,
        maximized=True,
        background_color='#141414'
    )
    
    webview.start()