# ======================================================================
# MetaForge Studio: Master Server Engine (V.Core - Build 5.5.7)
# File Location: \MetaForge Suite\ui\app.py
# Build 5.5.7: Integrated Silent Sync Update Heartbeat and Payload Lifecycle.
# ======================================================================
import os
import sys
import time
import json
import threading
import sqlite3
import re
import webview
import requests
from pathlib import Path
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, send_file
from dotenv import load_dotenv

# --- [ SECTION 1: THE PATH FIXER ] ---
UI_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = UI_DIR.parent.resolve()

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import routes
from common import config_handler, db_engine
from tools.settings.engines import update_engine

# --- [ SECTION 2: ARCHITECTURAL CONSTANTS ] ---
APPDATA_ROOT    = config_handler.APPDATA_MF
ENV_PATH        = config_handler.ENV_PATH
CATEGORIES_PATH = APPDATA_ROOT / "categories.json"
DATA_DIR        = config_handler.DATA_DIR
LOGS_DIR        = config_handler.LOGS_DIR
DB_PATH         = config_handler.DB_PATH
LAYOUT_PATH     = DATA_DIR / "toolbar_layout.json"

UI_ROOT   = PROJECT_ROOT / "ui"
HTML_DIR  = UI_ROOT / "html"
TOOLS_DIR = PROJECT_ROOT / "tools"

app = Flask(__name__, template_folder=str(HTML_DIR), static_folder=str(UI_ROOT), static_url_path='/ui')
window = None
dashboard_alerts = []

# --- [ SECTION 3: UPDATE HEARTBEAT ] ---
def run_silent_sync():
    """Checks for updates on startup. Required assets are processed immediately."""
    global dashboard_alerts
    print("DEBUG: [Silent Sync] Heartbeat initiated...")
    with app.app_context():
        # Invoke engine logic
        response = update_engine.check_for_updates()
        
        # Unpack response
        data = response.get_json() if hasattr(response, 'get_json') else (response[0] if isinstance(response, tuple) else response)

        if data and isinstance(data, dict):
            print(f"DEBUG: [Silent Sync] Update Available: {data.get('update_available')}")
            
            if data.get("update_available"):
                updates = data.get("updates", [])
                required_updates = [u for u in updates if u.get("priority") == "Required"]
                
                if required_updates:
                    print(f"DEBUG: [Silent Sync] Found {len(required_updates)} required updates. Committing...")
                    commit_payload = {
                        "updates": required_updates,
                        "active_model": data.get("active_model"),
                        "remote_version": data.get("remote_version")
                    }
                    update_engine.commit_update_direct(commit_payload)
                    print("DEBUG: [Silent Sync] Commit successful.")
                
                # Injection for Optional updates
                optional_updates = [u for u in updates if u.get("priority") == "Optional"]
                for opt in optional_updates:
                    dashboard_alerts.append({
                        "id": opt["id"],
                        "title": opt["user_message"]["title"],
                        "body": opt["user_message"]["body"]
                    })
        else:
            print("DEBUG: [Silent Sync] No valid data returned from engine.")

# --- [ SECTION 4: UTILITY FUNCTIONS ] ---
def initialize_database():
    APPDATA_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS library_artist (
            mf_artist_id TEXT PRIMARY KEY, artist_name TEXT NOT NULL, 
            country TEXT, biography TEXT, photo_path TEXT,
            bio_updated_at TEXT, last_updated TEXT, mb_artist_id TEXT
        )
    """)
    try: cursor.execute("SELECT photo_path FROM library_artist LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE library_artist ADD COLUMN photo_path TEXT")

    cursor.execute("CREATE TABLE IF NOT EXISTS library_master (mf_id TEXT PRIMARY KEY, mf_artist_id TEXT, artist_name TEXT, album_title TEXT NOT NULL, mb_album_id TEXT, original_year TEXT, label TEXT, is_compilation INTEGER, last_updated TEXT, date_audit_status INTEGER)")
    # `personnel` was a legacy flat text field, write-only from initial commit --
    # real personnel data has always lived in the `edges` table, and nothing in
    # the app ever reads this column back. Drop it from any existing database
    # that still has it (safe: SQLite 3.35+ supports DROP COLUMN on a plain,
    # unconstrained column; no-ops harmlessly on a fresh install that never had it).
    try:
        cursor.execute("SELECT personnel FROM library_master LIMIT 1")
        cursor.execute("ALTER TABLE library_master DROP COLUMN personnel")
    except sqlite3.OperationalError:
        pass
    cursor.execute("CREATE TABLE IF NOT EXISTS tracks (file_path TEXT PRIMARY KEY, mf_id TEXT, mf_artist_id TEXT, mb_artist_id TEXT, mb_track_id TEXT, acoustid TEXT, title TEXT, genre TEXT, sub_genre TEXT, original_year TEXT, bpm INTEGER, key_val TEXT, mood TEXT, intensity INTEGER, is_remediated INTEGER, last_updated TEXT, mb_work_id TEXT, orig_year_conf INTEGER, orig_year_source TEXT, leak_flag INTEGER)")
    for col_name, col_type in [
        ("mb_recording_id", "TEXT"),
        ("length", "INTEGER"),
        ("sonic_texture", "TEXT"),
        ("emotional_flavor", "TEXT"),
    ]:
        try:
            cursor.execute(f"SELECT {col_name} FROM tracks LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE tracks ADD COLUMN {col_name} {col_type}")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
            target_type TEXT NOT NULL, target_id TEXT NOT NULL, relation_type TEXT NOT NULL,
            role TEXT, weight REAL DEFAULT 1.0, confidence REAL, source_system TEXT,
            provenance TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # evidence_scope/evidence_detail (album/track scoping for personnel credits)
    # previously only existed on John's live DB because a one-off script was run
    # against it by hand -- a fresh install's CREATE TABLE above never had them,
    # so every edge_normalizer-based personnel commit would crash with "no such
    # column". Same ALTER-TABLE-if-missing pattern as the tracks columns above.
    for col_name, col_type in [
        ("evidence_scope", "TEXT"),
        ("evidence_detail", "TEXT"),
    ]:
        try:
            cursor.execute(f"SELECT {col_name} FROM edges LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE edges ADD COLUMN {col_name} {col_type}")
    conn.commit()
    conn.close()

def get_dynamic_toolbar():
    discovered_tools = {}
    if TOOLS_DIR.exists():
        for folder in TOOLS_DIR.iterdir():
            manifest_path = folder / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        m = json.load(f); discovered_tools[m['id']] = m
                except: pass
    layout_state =[]
    if LAYOUT_PATH.exists():
        try:
            with open(LAYOUT_PATH, 'r', encoding='utf-8') as f: layout_state = json.load(f)
        except: layout_state = []
    final_toolbar =[]
    for entry in layout_state:
        tid = entry['id']
        if tid in discovered_tools:
            tool_data = discovered_tools[tid]
            tool_data['visible'] = True if tid in ["dashboard", "settings"] else entry.get('visible', True)
            if tool_data['visible']: final_toolbar.append(tool_data)
    return final_toolbar

# --- [ SECTION 5: CORE UI ROUTES ] ---
@app.route('/')
def home():
    if not ENV_PATH.exists(): return render_template('setup.html')
    try:
        conn = sqlite3.connect(str(DB_PATH))
        track_count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        conn.close()
    except sqlite3.Error:
        track_count = "0"
    return render_template('index.html', track_count=track_count, version_id=time.time(),
                           tools=get_dynamic_toolbar(), alerts=dashboard_alerts)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(str(UI_ROOT / "images"), 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/common/<path:filename>')
def serve_common(filename):
    return send_from_directory(str(PROJECT_ROOT / "common"), filename)

@app.route('/tool_asset/<tool_id>/<path:filename>')
def serve_tool_asset(tool_id, filename):
    return send_from_directory(str(TOOLS_DIR / tool_id), filename)

@app.route('/data/fonts/<path:filename>')
def serve_custom_fonts(filename):
    return send_from_directory(str(DATA_DIR / "fonts"), filename)

@app.route('/ui/<type>/<path:filename>')
def serve_ui(type, filename):
    return send_from_directory(str(UI_ROOT / type), filename)

# --- [ FORENSIC MEDIA BRIDGES ] ---
@app.route('/ui/covers/<mf_id>.jpg')
def serve_album_cover(mf_id):
    res = db_engine.execute_query("SELECT file_path FROM tracks WHERE mf_id = ? LIMIT 1", (mf_id,))
    if res:
        track_path = Path(res[0]['file_path'])
        album_dir = track_path.parent
        cover_path = album_dir / "folder.jpg"
        if cover_path.exists():
            return send_from_directory(str(album_dir), "folder.jpg")
    return send_from_directory(str(UI_ROOT / "images"), "no-cover.png")

@app.route('/ui/artist_photo/<md5_hash>')
def serve_artist_photo(md5_hash):
    if len(md5_hash) == 32 and re.match(r'^[a-fA-F0-9]+$', md5_hash):
        photos_directory = PROJECT_ROOT / "photos"
        for ext in ['.png', '.jpg']:
            hashed_filename = f"{md5_hash}{ext}"
            if (photos_directory / hashed_filename).exists():
                return send_from_directory(str(photos_directory), hashed_filename)
    res = db_engine.execute_query("SELECT photo_path FROM library_artist WHERE mf_artist_id = ?", (md5_hash,))
    if res and res[0]['photo_path']:
        raw_path = res[0]['photo_path'].replace('"', '').strip()
        p = Path(raw_path)
        if p.exists():
            ext = p.suffix.lower()
            mtype = 'image/png' if ext == '.png' else 'image/jpeg'
            return send_file(str(p), mimetype=mtype)
    return send_from_directory(str(UI_ROOT / "images"), "no-photo.png")

@app.route('/get_tool/<tool_id>')
def get_tool(tool_id):
    clean_id = tool_id.split('?')[0]
    return (TOOLS_DIR / clean_id / f"{clean_id}.mfi").read_text(encoding='utf-8')

# --- [ GLOBAL PICKER PRIMITIVES ] ---
@app.route('/select_folder')
def select_folder():
    global api_bridge
    path = api_bridge.select_folder()
    return jsonify({"path": path})

@app.route('/select_file')
def select_file():
    global api_bridge
    path = api_bridge.select_file()
    return jsonify({"path": path})

# --- [ ENGINE STARTUP ] ---
routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, None)

class MetaForgeAPI:
    def select_folder(self):
        global window
        if window:
            res = window.create_file_dialog(webview.FOLDER_DIALOG)
            return res[0] if res and isinstance(res, tuple) else res
        return None
    def select_file(self):
        global window
        if window:
            res = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=('Image Files (*.jpg;*.jpeg;*.png)', 'All files (*.*)'))
            return res[0] if res and isinstance(res, tuple) else res
        return None

def run_flask():
    app.run(port=5000, debug=False, use_reloader=False, threaded=True)

@app.route('/scan_library', methods=['GET'])
def scan_library_route():
    path = request.args.get('path')
    if not path: return jsonify({"status": "error", "message": "No path provided"}), 400
    from common import io_bridge
    targets = io_bridge.get_audio_targets(path, recursive=True)
    return jsonify({"status": "success", "count": len(targets), "files": [str(t) for t in targets]})

if __name__ == '__main__':
    initialize_database()
    if ENV_PATH.exists(): load_dotenv(ENV_PATH)
    
    # Trigger Silent Sync
    threading.Thread(target=run_silent_sync, daemon=True).start()
    
    api_bridge = MetaForgeAPI()
    threading.Thread(target=run_flask, daemon=True).start()
    
    window = webview.create_window('MetaForge Studio', 'http://127.0.0.1:5000', js_api=api_bridge, width=1280, height=800, maximized=True, background_color='#141414')
    webview.start()