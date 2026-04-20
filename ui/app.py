# ======================================================================
# 🚀 MetaForge Studio: Master Server Engine (V.Core)
# ======================================================================
import os
import sys
from pathlib import Path

# --- [ SECTION 1: THE PATH FIXER ] ---
BASE_PATH = Path(__file__).parent.resolve()
if str(BASE_PATH) not in sys.path:
    sys.path.append(str(BASE_PATH))

# --- [ EXTERNAL ROUTE LOADER ] ---
import MetaForge_Routes

# --- [ SYSTEM IMPORTS ] ---
import threading
import sqlite3
import webview
import ctypes
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify
from dotenv import load_dotenv
# --- [ SECTION 1: THE PATH FIXER END ] ---

# --- [ SECTION 2: ARCHITECTURAL CONSTANTS ] ---
APPDATA_ROOT = Path(os.environ.get('APPDATA', '')) / "MetaForge"
ENV_PATH     = APPDATA_ROOT / ".env"
DATA_DIR     = APPDATA_ROOT / "data"
LOGS_DIR     = APPDATA_ROOT / "logs"
DB_PATH      = DATA_DIR / "metaforge.db"
# --- [ SECTION 2: ARCHITECTURAL CONSTANTS END ] ---

# --- [ SECTION 3: BOOTSTRAP THE CONFIG ] ---
AUDIO_DIR = BASE_PATH / "audio"
UI_ROOT   = AUDIO_DIR / "ui"
HTML_DIR  = UI_ROOT / "html"
TOOLS_DIR = AUDIO_DIR / "tools"

app = Flask(__name__, template_folder=str(HTML_DIR), static_folder=None)
window = None 
# --- [ SECTION 3: BOOTSTRAP THE CONFIG END ] ---

# --- [ SECTION 4: UTILITY FUNCTIONS ] ---
def is_setup_required():
    return not ENV_PATH.exists()

def set_file_attribute(path, attribute):
    if os.name == 'nt':
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attribute)
        except Exception: pass

def initialize_database():
    for folder in [APPDATA_ROOT, DATA_DIR, LOGS_DIR]:
        folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE, artist TEXT, album TEXT, title TEXT, acoustid TEXT)''')
    conn.commit()
    conn.close()
# --- [ SECTION 4: UTILITY FUNCTIONS END ] ---

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
    return render_template('index.html', track_count=track_count)

@app.route('/ui/<type>/<path:filename>')
def serve_ui(type, filename):
    """Serves CSS and Images from their respective subfolders."""
    response = send_from_directory(str(UI_ROOT / type), filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/metaforge_core.js')
def serve_master_script():
    return send_from_directory(str(HTML_DIR), 'metaforge_core.js', mimetype='text/javascript')

@app.route('/select_folder')
def select_folder():
    """
    Native PyWebView Folder Picker.
    Location-agnostic and does not require tkinter.
    """
    global window
    if window:
        # This opens the standard Windows folder selection dialog
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        # result is a tuple, e.g. ('D:/Music/Incoming',)
        path = result[0] if result else None
        return jsonify({"path": path})
    return jsonify({"path": None})

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    """Simplified Tool Loader: Strips query strings to find the correct .mfi file."""
    # This line is the only change: it ensures 'settings?v=123' becomes 'settings'
    clean_id = tool_id.split('?')[0]
    target = TOOLS_DIR / clean_id / f"{clean_id}.mfi"
    
    if not target.exists():
        return "Tool Not Found", 404
        
    return target.read_text(encoding='utf-8')

# --- [ THE HANDOFF ] ---
MetaForge_Routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, set_file_attribute)
# --- [ SECTION 5: CORE UI ROUTES END ] ---

# --- [ SECTION 6: ENGINE STARTUP ] ------------------------------------
# This class defines the functions available to JavaScript via window.pywebview.api
class MetaForgeAPI:
    def select_folder(self):
        """Standardized bridge call for the Windows Folder Picker."""
        # Access the global window object to trigger the dialog
        global window
        if window:
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            return result[0] if result else None
        return None

def run_flask():
    """Runs the Flask server in a background thread."""
    app.run(port=5000, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    # 1. Restore your original startup sequence
    initialize_database()
    if ENV_PATH.exists(): 
        load_dotenv(ENV_PATH)
    
    # 2. Instantiate the API bridge
    api_bridge = MetaForgeAPI()
    
    # 3. Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # 4. Create the Master Window and bind the JS API
    # CRITICAL: js_api=api_bridge is what enables 'window.pywebview.api'
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
# --- [ SECTION 6: ENGINE STARTUP END ] --------------------------------