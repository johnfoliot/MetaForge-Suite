# ======================================================================
# MetaForge Studio: Master Server Engine (V.Core)
# File Location: \MetaForge Suite\ui\app.py
# ======================================================================
import os
import sys
import time
import json
import threading
import sqlite3
import webview
import ctypes
from pathlib import Path
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify
from dotenv import load_dotenv

# --- [ SECTION 1: THE PATH FIXER ] ---
UI_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = UI_DIR.parent.resolve()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import routes
from common import config_handler

# --- [ SECTION 2: ARCHITECTURAL CONSTANTS ] ---
APPDATA_ROOT = config_handler.APPDATA_MF
ENV_PATH     = config_handler.ENV_PATH
DATA_DIR     = config_handler.DATA_DIR
LOGS_DIR     = config_handler.LOGS_DIR
DB_PATH      = config_handler.DB_PATH
LAYOUT_PATH  = DATA_DIR / "toolbar_layout.json"

# --- [ SECTION 3: BOOTSTRAP THE CONFIG ] ---
UI_ROOT   = PROJECT_ROOT / "ui"
HTML_DIR  = UI_ROOT / "html"
TOOLS_DIR = PROJECT_ROOT / "tools"

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
    """Beta 1 Database Schema Provisioning."""
    APPDATA_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library_artist (
            mf_artist_id TEXT PRIMARY KEY,
            artist_name TEXT NOT NULL,
            country TEXT, biography TEXT, bio_updated_at TEXT, last_updated TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library_master (
            mf_id TEXT PRIMARY KEY,
            mf_artist_id TEXT, artist_name TEXT, 
            album_title TEXT NOT NULL, mb_album_id TEXT, 
            original_year TEXT, label TEXT, personnel TEXT, 
            is_compilation INTEGER, last_updated TEXT, date_audit_status INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            file_path TEXT PRIMARY KEY, mf_id TEXT, mf_artist_id TEXT, 
            mb_artist_id TEXT, mb_track_id TEXT, acoustid TEXT, 
            title TEXT, genre TEXT, sub_genre TEXT, original_year TEXT, 
            bpm INTEGER, key_val TEXT, mood TEXT, intensity INTEGER, 
            is_remediated INTEGER, last_updated TEXT, mb_work_id TEXT, 
            orig_year_conf INTEGER, orig_year_source TEXT, leak_flag INTEGER
        )
    """)
    conn.commit()
    conn.close()

# --- [ SECTION 5: TOOL DISCOVERY LOGIC ] ---
def get_dynamic_toolbar():
    """
    Implements the Dual-Pass Discovery Protocol.
    Merges manifest data with the layout state from the data directory.
    """
    discovered_tools = {}
    
    # Pass 1: Scan manifests
    if TOOLS_DIR.exists():
        for folder in TOOLS_DIR.iterdir():
            manifest_path = folder / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        m = json.load(f)
                        discovered_tools[m['id']] = m
                except Exception as e:
                    print(f"Discovery Error in {folder.name}: {e}")

    # Pass 2: Load or Generate Layout State
    layout_state = []
    if LAYOUT_PATH.exists():
        try:
            with open(LAYOUT_PATH, 'r', encoding='utf-8') as f:
                layout_state = json.load(f)
        except: layout_state = []

    # Safeguard & Initial Order Strategy
    if not layout_state:
        # Initial factory order
        initial_order = [
            "dashboard", "unpack_convert", "intelli-tagger", "musicbrainz_id", 
            "acoustid", "biography", "database_tools", "playlist_generator", 
            "repair", "youtube_mp3", "music-sharing", "settings"
        ]
        layout_state = [{"id": tid, "visible": True} for tid in initial_order if tid in discovered_tools]
        # Ensure any missing tools found in scan are appended
        for tid in discovered_tools:
            if not any(entry['id'] == tid for entry in layout_state):
                layout_state.append({"id": tid, "visible": True})
        
        with open(LAYOUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(layout_state, f, indent=4)

    # Synthesis & Security Enforcement
    final_toolbar = []
    for entry in layout_state:
        tid = entry['id']
        if tid in discovered_tools:
            tool_data = discovered_tools[tid]
            
            # Security Rule: Dashboard and Settings are immutable
            if tid in ["dashboard", "settings"]:
                tool_data['visible'] = True
            else:
                tool_data['visible'] = entry.get('visible', True)
            
            if tool_data['visible'] or tool_data.get('required'):
                final_toolbar.append(tool_data)
                
    return final_toolbar

# --- [ SECTION 6: CORE UI ROUTES ] ---
@app.route('/')
def home():
    if is_setup_required(): 
        return send_from_directory(str(UI_ROOT / "html"), 'setup.html')
        
    toolbar_data = get_dynamic_toolbar()
    track_count = "0"
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            track_count = f"{conn.execute('SELECT COUNT(*) FROM tracks').fetchone()[0]:,}"
            conn.close()
        except: track_count = "DB ERROR"
            
    return render_template('index.html', track_count=track_count, version_id=time.time(), tools=toolbar_data)

@app.route('/complete_setup', methods=['POST'])
def complete_setup():
    data = request.json
    lines = [
        f"USER_EMAIL={data['email']}",
        f"LIBRARY_ROOT={data['lib_root']}",
        f"ACOUSTID_KEY={data['acoustid']}",
        f"GEMINI_KEY={data['gemini']}",
        f"DISCOGS_TOKEN={data.get('discogs', '')}"
    ]
    try:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ENV_PATH, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        initialize_database()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/tool_asset/<tool_id>/<filename>')
def serve_tool_asset(tool_id, filename):
    return send_from_directory(str(TOOLS_DIR / tool_id), filename)

@app.route('/ui/<type>/<path:filename>')
def serve_ui(type, filename):
    return send_from_directory(str(UI_ROOT / type), filename)

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    clean_id = tool_id.split('?')[0]
    return (TOOLS_DIR / clean_id / f"{clean_id}.mfi").read_text(encoding='utf-8')

@app.route('/select_folder')
def select_folder():
    global api_bridge
    return jsonify({"path": api_bridge.select_folder()})

routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, set_file_attribute)

# --- [ SECTION 7: ENGINE STARTUP ] ---
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
    if ENV_PATH.exists(): load_dotenv(ENV_PATH)
    api_bridge = MetaForgeAPI()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    window = webview.create_window('MetaForge Studio', 'http://127.0.0.1:5000', js_api=api_bridge, width=1280, height=800, maximized=True, background_color='#141414')
    webview.start()