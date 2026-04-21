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

# --- [ SECTION 5: CORE UI ROUTES ] ---
@app.route('/')
def home():
    if is_setup_required(): return render_template('setup.html')
    track_count = "0"
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            track_count = f"{conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]:,}"
            conn.close()
        except: track_count = "DB ERROR"
    
    # ADD time.time() here to create a unique ID every launch
    return render_template('index.html', track_count=track_count, version_id=time.time())

@app.route('/ui/<type>/<path:filename>')
def serve_ui(type, filename):
    """Serves CSS, JS, and Images from their respective subfolders."""
    response = send_from_directory(str(UI_ROOT / type), filename)
    # Disable caching during development so changes show up immediately
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/metaforge_core.js')
def serve_master_script():
    """Legacy helper to find the core JS if the root link fails."""
    return send_from_directory(str(UI_ROOT / "js"), 'metaforge_core.js', mimetype='text/javascript')

@app.route('/select_folder')
def select_folder():
    global window
    if window:
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        path = result[0] if result else None
        return jsonify({"path": path})
    return jsonify({"path": None})

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    """Discovery Engine: Loads tool .mfi files from the tools directory."""
    clean_id = tool_id.split('?')[0]
    target = TOOLS_DIR / clean_id / f"{clean_id}.mfi"
    
    if not target.exists():
        return f"Tool '{clean_id}' Not Found at {target}", 404
        
    return target.read_text(encoding='utf-8')

# --- [ THE HANDOFF ] ---
routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, set_file_attribute)

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