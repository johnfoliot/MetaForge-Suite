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
import webbrowser
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
from tools.personnel.personnel import MANUAL_VERIFICATION_TIERS

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

@app.route('/open_mb_seeded_window', methods=['POST'])
def open_mb_seeded_window():
    global api_bridge
    data = request.json or {}
    title = data.get('title', 'MusicBrainz')
    html = data.get('html', '')
    if not html:
        return jsonify({"status": "error", "message": "No seed content provided."}), 400
    api_bridge.open_mb_seeded_window(title, html)
    return jsonify({"status": "success"})

@app.route('/open_mb_relationship_seed_window', methods=['POST'])
def open_mb_relationship_seed_window():
    # MB Submit's release-level relationship automation (John,
    # 2026-07-13) -- see project_mb_contribution_tool memory. Unlike
    # open_mb_seeded_window (a locally-built static HTML page), this
    # needs a genuine top-level navigation to MusicBrainz's own live
    # page, then a one-shot script injection once it loads, so the
    # window is created with url= (real navigation), not html=. No
    # js_api -- there's nothing for the page to call back into
    # MetaForge for, and the crash investigation earlier the same day
    # found js_api unsafe against live third-party pages; musicbrainz.org
    # itself has never shown that issue in this tool's existing
    # open_mb_seeded_window usage, but there's no need to risk it here
    # either when the script has no reason to talk back to Python.
    global api_bridge
    data = request.json or {}
    url = data.get('url')
    script = data.get('script')
    title = data.get('title', 'MusicBrainz')
    if not url or not script:
        return jsonify({"status": "error", "message": "url and script are required."}), 400
    api_bridge.open_mb_relationship_seed_window(title, url, script)
    return jsonify({"status": "success"})

@app.route('/open_verify_window', methods=['POST'])
def open_verify_window():
    # Personnel Scout's "click to verify" flow (John, 2026-07-11) -- see
    # project_mb_contribution_tool memory for why this exists: Gemini's
    # grounding terms don't let MetaForge cite or retain what Google's
    # search surfaced, so a human has to look at the actual source
    # themselves and record their OWN judgment. urls is capped at 3 by
    # ai_engine.py's _credit_candidate_uris.
    global api_bridge
    data = request.json or {}
    urls = [u for u in (data.get('urls') or []) if u]
    title = data.get('title', 'Verify Source')
    if not urls:
        return jsonify({"status": "error", "message": "No candidate URLs provided."}), 400
    api_bridge.open_verify_window(title, urls)
    return jsonify({"status": "success"})

@app.after_request
def _verify_action_cors(response):
    # CORS for the verify window's docked overlay only (John, 2026-07-12,
    # rebuilt after confirming js_api itself -- not page content, not
    # timing -- was crashing the app: live-tested, a window with no
    # js_api stayed stable against the exact same URL that crashed the
    # real verify window with js_api set. pywebview's js_api works by
    # injecting a host-object bridge script into EVERY frame of the
    # loaded page, including third-party iframes on a live external
    # site -- a known-flaky combination on WebView2. The verify window no
    # longer sets js_api at all; its overlay talks to these routes over
    # plain fetch() instead, from whatever third-party origin it's
    # running on (Discogs, Wikipedia, wherever a candidate source lives).
    # `*` is safe here specifically because Flask only binds to
    # 127.0.0.1 -- a remote page can't reach this at all -- and no
    # credentials/cookies are ever sent or read by these routes.
    if request.path.startswith('/verify_action/'):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

def _active_verify_api():
    global api_bridge
    return getattr(api_bridge, '_active_verify_api', None)

@app.route('/verify_action/state', methods=['POST'])
def verify_action_state():
    api = _active_verify_api()
    if api is None:
        return jsonify({"status": "error", "message": "No active verify session."}), 404
    return jsonify(api.get_state())

@app.route('/verify_action/record_verdict', methods=['POST'])
def verify_action_record_verdict():
    api = _active_verify_api()
    if api is None:
        return jsonify({"status": "error", "message": "No active verify session."}), 404
    data = request.json or {}
    return jsonify(api.record_verdict(bool(data.get('verdict')), data.get('tier'), data.get('url')))

@app.route('/verify_action/go_to_index', methods=['POST'])
def verify_action_go_to_index():
    api = _active_verify_api()
    if api is None:
        return jsonify({"status": "error", "message": "No active verify session."}), 404
    data = request.json or {}
    return jsonify(api.go_to_index(int(data.get('index', 0))))

@app.route('/verify_action/submit', methods=['POST'])
def verify_action_submit():
    api = _active_verify_api()
    if api is None:
        return jsonify({"status": "error", "message": "No active verify session."}), 404
    return jsonify(api.submit())

# --- [ ENGINE STARTUP ] ---
routes.initialize_routes(app, lambda: window, TOOLS_DIR, ENV_PATH, None)

def _build_verify_overlay_js(tiers):
    """
    Builds the injected docked control bar for the verify window (John,
    2026-07-11 design, see project_mb_contribution_tool memory). This
    runs via window.evaluate_js() against a LIVE external page loaded by
    direct top-level navigation (create_window(url=...)), never framed --
    so a source site's own X-Frame-Options (confirmed live 2026-07-09 that
    musicbrainz.org sends one) never applies here at all, framing
    restrictions only block <iframe> embedding. evaluate_js runs in the
    browser engine's own privileged script context (same mechanism
    devtools console / Selenium's execute_script use), not a <script> tag
    load, so a source page's Content-Security-Policy doesn't block it
    either.

    Rendered inside a closed shadow root so none of the host page's CSS
    can bleed into the overlay (and vice versa) -- this runs against
    arbitrary third-party pages MetaForge doesn't control the styling of.

    State (which of the up to 3 candidate sources have been marked True/
    False, and which assurance tier each True carries) lives entirely in
    the PYTHON-side VerifyWindowAPI instance, not in this page's own JS --
    navigating between sources via the <> arrows is a real page reload
    (window.load_url), which wipes any JS-held state here. Every render
    re-fetches ground truth via the /verify_action/state route.

    Talks to Flask over plain fetch() to http://127.0.0.1:5000, NOT
    window.pywebview.api (John, 2026-07-12, rebuilt after a live crash --
    see project_mb_contribution_tool memory). pywebview's js_api bridge
    injects into every frame of whatever page is loaded, including this
    one's third-party content -- confirmed live to crash the app
    (WinForms `AccessibilityObject.Bounds` infinite recursion) against a
    real Discogs page, while an otherwise-identical window with no js_api
    stayed stable against the same URL. fetch() to 127.0.0.1 from an
    https:// page is exempt from mixed-content blocking (loopback
    addresses are a documented "potentially trustworthy origin" carve-out
    in the secure-contexts spec, same reason browser devtools/local dev
    tooling can always reach localhost) -- the Flask side allows it via
    CORS on the /verify_action/* routes specifically (see
    _verify_action_cors), not app-wide.
    """
    tiers_json = json.dumps(tiers)
    return f"""
(function() {{
    var TIERS = {tiers_json};
    var existing = document.getElementById('__mf_verify_host__');
    if (existing) existing.remove();

    var host = document.createElement('div');
    host.id = '__mf_verify_host__';
    document.documentElement.appendChild(host);
    var root = host.attachShadow({{mode: 'closed'}});

    root.innerHTML = `
        <style>
            .mf-nav, .mf-bar {{ font-family: Consolas, "Courier New", monospace; box-sizing: border-box; }}
            .mf-nav {{
                position: fixed; top: 12px; right: 12px; z-index: 2147483647;
                background: #141414; border: 1px solid #c9a227; border-radius: 4px;
                color: #eee; padding: 6px 10px; display: flex; align-items: center; gap: 10px;
                font-size: 13px;
            }}
            .mf-nav button {{
                background: #1f1f1f; color: #c9a227; border: 1px solid #c9a227;
                border-radius: 3px; padding: 2px 10px; cursor: pointer; font-size: 14px;
            }}
            .mf-nav button:disabled {{ opacity: 0.35; cursor: default; }}
            .mf-dots {{ display: flex; gap: 4px; }}
            /* Gray = incomplete -- deliberately covers BOTH an unvisited
               source and a True with no tier picked yet (John, 2026-07-11):
               neither has a usable decision recorded, so both read the
               same "still needs attention" way rather than looking done. */
            .mf-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #888; }}
            .mf-dot.true {{ background: #4caf50; }}
            .mf-dot.false {{ background: #e53935; }}
            .mf-dot.current {{ outline: 2px solid #c9a227; outline-offset: 1px; }}
            .mf-bar {{
                position: fixed; left: 0; right: 0; bottom: 0; z-index: 2147483647;
                background: #141414; border-top: 1px solid #c9a227; color: #eee;
                padding: 10px 14px; display: flex; flex-wrap: wrap; align-items: center;
                gap: 10px; font-size: 13px;
            }}
            .mf-bar .mf-label {{ flex: 1 1 260px; }}
            .mf-bar button.mf-tf {{
                background: #1f1f1f; color: #eee; border: 1px solid #666;
                border-radius: 3px; padding: 5px 14px; cursor: pointer; font-size: 13px;
            }}
            .mf-bar button.mf-tf.active-true {{ background: #2e7d32; border-color: #2e7d32; color: #fff; }}
            .mf-bar button.mf-tf.active-false {{ background: #555; border-color: #999; color: #fff; }}
            .mf-bar select {{
                background: #1f1f1f; color: #eee; border: 1px solid #c9a227;
                border-radius: 3px; padding: 5px; font-size: 13px;
            }}
            .mf-bar button.mf-submit {{
                background: #c9a227; color: #141414; border: none; border-radius: 3px;
                padding: 7px 18px; font-weight: bold; cursor: pointer; font-size: 13px;
            }}
            .mf-tier-text {{ font-size: 11px; opacity: 0.75; flex-basis: 100%; }}
            .mf-warn {{ color: #ffb74d; font-size: 12px; flex-basis: 100%; }}
        </style>
        <div class="mf-nav">
            <button id="mf-prev" aria-label="Previous source">&lsaquo;</button>
            <span id="mf-counter">1 / 1</span>
            <div class="mf-dots" id="mf-dots"></div>
            <button id="mf-next" aria-label="Next source">&rsaquo;</button>
        </div>
        <div class="mf-bar">
            <span class="mf-label">I have manually confirmed this fact to be:</span>
            <button id="mf-true" class="mf-tf">True</button>
            <button id="mf-false" class="mf-tf">False</button>
            <select id="mf-tier" aria-label="Assurance level" style="display:none;">
                <option value="">Select assurance level&hellip;</option>
                <option value="explicit">Explicit</option>
                <option value="inferred">Inferred</option>
                <option value="anecdotal">Anecdotal</option>
            </select>
            <span id="mf-tier-text" class="mf-tier-text"></span>
            <button id="mf-submit" class="mf-submit">Submit</button>
            <span id="mf-warn" class="mf-warn" style="display:none;"></span>
        </div>
    `;

    var prevBtn = root.getElementById('mf-prev');
    var nextBtn = root.getElementById('mf-next');
    var counter = root.getElementById('mf-counter');
    var dotsEl = root.getElementById('mf-dots');
    var trueBtn = root.getElementById('mf-true');
    var falseBtn = root.getElementById('mf-false');
    var tierSel = root.getElementById('mf-tier');
    var tierText = root.getElementById('mf-tier-text');
    var submitBtn = root.getElementById('mf-submit');
    var warnEl = root.getElementById('mf-warn');
    var lastState = null;

    function applyState(state) {{
        lastState = state;
        counter.textContent = (state.index + 1) + ' / ' + state.total;
        prevBtn.disabled = state.index <= 0;
        nextBtn.disabled = state.index >= state.total - 1;

        dotsEl.innerHTML = '';
        (state.all_verdicts || []).forEach(function(v, i) {{
            var dot = document.createElement('span');
            var cls = 'mf-dot';
            // True only counts as "done" (green) once it also carries a
            // tier -- a True missing its tier stays the default gray,
            // same as never having been visited at all (both mean
            // nothing usable is recorded yet for this source).
            if (v) {{
                if (v.verdict === true && v.tier) cls += ' true';
                else if (v.verdict === false) cls += ' false';
            }}
            if (i === state.index) cls += ' current';
            dot.className = cls;
            dotsEl.appendChild(dot);
        }});

        var v = state.verdict;
        trueBtn.classList.toggle('active-true', !!(v && v.verdict === true));
        falseBtn.classList.toggle('active-false', !!(v && v.verdict === false));

        if (v && v.verdict === true) {{
            tierSel.style.display = '';
            tierSel.value = v.tier || '';
            if (v.tier && TIERS[v.tier]) {{
                tierText.textContent = TIERS[v.tier].text;
                warnEl.style.display = 'none';
            }} else {{
                tierText.textContent = '';
                warnEl.textContent = 'Select an assurance level for this source before submitting.';
                warnEl.style.display = '';
            }}
        }} else {{
            tierSel.style.display = 'none';
            tierSel.value = '';
            tierText.textContent = '';
            warnEl.style.display = 'none';
        }}
    }}

    // Plain fetch() to our own local Flask server, not window.pywebview.api
    // -- see this function's docstring for why. 127.0.0.1 is exempt from
    // mixed-content blocking even from an https:// page.
    function apiCall(action, body) {{
        return fetch('http://127.0.0.1:5000/verify_action/' + action, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body || {{}})
        }}).then(function(r) {{ return r.json(); }});
    }}

    function refresh() {{
        apiCall('state').then(applyState);
    }}

    // window.location.href here is the page's own RESOLVED, post-redirect
    // URL (John, 2026-07-13) -- not Gemini's opaque grounding-chunk URI
    // that opened this window. Reading it via the page's own navigation
    // state, after a genuine human-driven page load, is a fundamentally
    // different thing than extracting a component of Google's Grounded
    // Result: it's just "what page is this window showing right now",
    // the same fact any browser extension can read. See
    // project_mb_contribution_tool memory for the full reasoning this is
    // built on.
    trueBtn.addEventListener('click', function() {{
        apiCall('record_verdict', {{verdict: true, tier: tierSel.value || null, url: window.location.href}}).then(applyState);
    }});
    falseBtn.addEventListener('click', function() {{
        apiCall('record_verdict', {{verdict: false, tier: null, url: window.location.href}}).then(applyState);
    }});
    tierSel.addEventListener('change', function() {{
        apiCall('record_verdict', {{verdict: true, tier: tierSel.value || null, url: window.location.href}}).then(applyState);
    }});
    prevBtn.addEventListener('click', function() {{
        if (lastState) apiCall('go_to_index', {{index: lastState.index - 1}});
    }});
    nextBtn.addEventListener('click', function() {{
        if (lastState) apiCall('go_to_index', {{index: lastState.index + 1}});
    }});
    submitBtn.addEventListener('click', function() {{
        // Fire-and-forget: a real commit/discard destroys this window;
        // an "incomplete" result navigates to the offending source, which
        // tears down and re-injects this whole overlay via the 'loaded'
        // event anyway -- nothing left to do in THIS page's context either way.
        apiCall('submit');
    }});

    refresh();
}})();
"""


class VerifyWindowAPI:
    """
    Per-session state holder for one verify window (John, 2026-07-11,
    rebuilt 2026-07-12 to drop js_api -- see open_verify_window's
    docstring for why). A fresh instance is created per
    open_verify_window() call and discarded when that window closes --
    never reused across credits. Its methods are now called from the
    /verify_action/* Flask routes (the overlay reaches them via plain
    fetch(), not a pywebview JS bridge) rather than dispatched by
    pywebview directly, but the method bodies/logic are unchanged --
    already covered by the state-machine simulation this class was
    tested with on 2026-07-11 (all-False discard, incomplete-tier block,
    multi-True strongest-tier-wins).

    Verdict state lives here in PYTHON, not in the verify window's own
    page JS, because paging between candidate sources is a real
    window.load_url() navigation, which destroys any DOM/JS state the
    previous page held. Only this object survives across those loads.
    """
    def __init__(self, main_window, urls, tiers, on_close=None):
        self.main_window = main_window
        self.window = None  # set by attach() once create_window() returns
        self.urls = urls
        self.tiers = tiers
        self.verdicts = [None] * len(urls)  # each: {"verdict": bool, "tier": str|None}
        self.current_index = 0
        self._on_close_callback = on_close

    def attach(self, verify_window):
        self.window = verify_window
        verify_window.events.loaded += lambda: self._inject_overlay(verify_window)
        verify_window.events.closed += self._on_closed

    def _inject_overlay(self, verify_window):
        # Defensive: 'loaded' can fire for a page whose window is already
        # being torn down (e.g. the user closed it right after a
        # navigation started) -- a real race confirmed live 2026-07-12,
        # WebView2 threw ObjectDisposedException from inside evaluate_js
        # in exactly this spot. Never let that propagate as an uncaught
        # exception on pywebview's own event thread.
        #
        # The short sleep is a hypothesis, not a confirmed fix (2026-07-12
        # crash investigation, see project_mb_contribution_tool memory):
        # calling evaluate_js the INSTANT 'loaded' fires is the one thing
        # this window does that MB Submit's already-proven second window
        # never does (that window has no js_api and injects nothing) --
        # giving WebView2's own internals a beat to settle after
        # navigation, before this window is the target of any script
        # injection, costs nothing and might avoid whatever race is
        # producing the AccessibilityObject/disposal errors. pywebview's
        # Event fires handlers on their own background thread (see
        # webview/event.py's Event.set()), so this sleep doesn't block
        # the native GUI thread.
        time.sleep(0.4)
        try:
            verify_window.evaluate_js(_build_verify_overlay_js(self.tiers))
        except Exception as ex:
            print(f"⚠️ Verify overlay injection skipped (window likely closing): {ex}")

    def _on_closed(self):
        # Closing the window without ever hitting Submit is a deliberate
        # no-op on the DATA (John's own design: "the end user has to
        # consciously decide to discard") -- no row changes here. But the
        # /verify_action/* routes dispatch to whichever session
        # api_bridge._active_verify_api currently points at (there's only
        # ever one live session), so it still needs clearing on close --
        # otherwise a stray fetch() from an already-closed window's page
        # (or a leftover browser tab) would operate on a dead window
        # object and blow up go_to_index's load_url() call.
        if self._on_close_callback:
            self._on_close_callback()

    def get_state(self):
        return {
            "index": self.current_index,
            "total": len(self.urls),
            "url": self.urls[self.current_index],
            "verdict": self.verdicts[self.current_index],
            "all_verdicts": self.verdicts,
        }

    def record_verdict(self, verdict, tier=None, url=None):
        # url is the page's own RESOLVED location.href at the moment of
        # the click (John, 2026-07-13) -- the real destination page, not
        # Gemini's opaque grounding-chunk redirect URI that opened this
        # window. See submit()'s docstring / project_mb_contribution_tool
        # memory for why that distinction is what makes this citable.
        self.verdicts[self.current_index] = {"verdict": bool(verdict), "tier": tier or None, "url": url or None}
        return self.get_state()

    def go_to_index(self, index):
        if 0 <= index < len(self.urls):
            self.current_index = index
            self.window.load_url(self.urls[index])
        return self.get_state()

    def submit(self):
        # "Strongest tier wins" (John, 2026-07-11): if more than one
        # source resolved True with a different assurance tier picked,
        # the committed confidence reflects the BEST evidence found, not
        # the last one looked at or a forced average.
        trues = [v for v in self.verdicts if v and v.get("verdict")]
        if not trues:
            self._finish({"discarded": True})
            return {"status": "discarded"}

        incomplete_index = next(
            (i for i, v in enumerate(self.verdicts) if v and v.get("verdict") and not v.get("tier")),
            None,
        )
        if incomplete_index is not None:
            self.go_to_index(incomplete_index)
            return {"status": "incomplete", "index": incomplete_index}

        best = max(trues, key=lambda v: self.tiers.get(v["tier"], {}).get("confidence", 0))
        best_tier = best["tier"]
        self._finish({
            "verified": True,
            "verification_tier": best_tier,
            "confidence": self.tiers[best_tier]["confidence"],
            # The resolved URL behind whichever True verdict won the
            # strongest-tier tiebreak -- see record_verdict's docstring.
            "source_url": best.get("url"),
        })
        return {"status": "submitted"}

    def _finish(self, result):
        try:
            self.main_window.evaluate_js(
                "if (window.metaforge && window.metaforge.personnel) "
                f"window.metaforge.personnel.onVerifyModalResult({json.dumps(result)});"
            )
        except Exception as ex:
            print(f"⚠️ Verify modal result callback failed: {ex}")
        try:
            self.window.destroy()
        except Exception:
            pass


class MetaForgeAPI:
    def open_external_url(self, url):
        # Fixes a real bug (John, 2026-07-13): plain <a target="_blank">
        # links don't reliably open anything from inside a pywebview
        # window -- there's no real "new tab" to open one into, and
        # pywebview doesn't automatically hand external navigation off to
        # the OS's default browser. webbrowser.open() does that
        # explicitly. Only http(s) URLs are allowed -- this is called
        # from the main window's own js_api bridge, reachable by any JS
        # running there, so it's worth being deliberate about what it can
        # launch rather than passing an arbitrary string straight through.
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            webbrowser.open(url)
            return True
        return False

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
    def open_mb_seeded_window(self, title, html):
        # A genuine second top-level window ("pseudo-tab"), not an
        # <iframe> -- musicbrainz.org sends X-Frame-Options: DENY /
        # frame-ancestors 'none' (confirmed live 2026-07-09), which blocks
        # framing entirely but has no bearing on a separate top-level
        # window. Matches the main window's own 1280x800 sizing (John's
        # own stated minimum was 1240px to avoid horizontal scroll on MB's
        # pages) so both windows feel like one consistent app. Shares the
        # main window's persistent webview profile (private_mode=False +
        # storage_path set once in webview.start() below) so a MusicBrainz
        # login only has to happen once, ever -- confirmed live via a real
        # login + app-restart test, not assumed.
        webview.create_window(title, html=html, width=1280, height=800)

    def open_mb_relationship_seed_window(self, title, url, script):
        # Real navigation (url=), not html= -- the injected script needs
        # to run against MusicBrainz's own live page, not a locally-built
        # one. No js_api: the script only reads/writes the page's own DOM
        # and shows alert() for its own status; nothing needs to call
        # back into Python. events.loaded triggers the one-shot injection
        # once the real page has actually finished loading.
        # background_color='#ffffff', not MetaForge's usual '#141414' --
        # confirmed live 2026-07-17 (verify window, same pattern) that a
        # dark window background_color shows through as an ugly dark
        # striped artifact on any region of a loaded third-party page
        # that doesn't explicitly set its own background (falling back to
        # the browser-default white the page's own author assumed, not
        # this window's dark base). '#141414' is correct for windows
        # loading MetaForge's OWN html (matches the app's real background,
        # see open_verify_window/the main window below) -- wrong for a
        # window loading a real external page MetaForge doesn't control
        # the CSS of, where matching ordinary browser convention (white)
        # is the safer default.
        seed_window = webview.create_window(title, url=url, width=1280, height=900, background_color='#ffffff')
        seed_window.events.loaded += lambda: seed_window.evaluate_js(script)

    def open_verify_window(self, title, urls):
        # Genuine second top-level window loaded by direct navigation
        # (url=..., not html=...) -- see _build_verify_overlay_js's
        # docstring for why that sidesteps X-Frame-Options entirely.
        #
        # Deliberately NO js_api here (John, 2026-07-12, rebuilt after a
        # real crash investigation -- see project_mb_contribution_tool
        # memory for the full diagnostic trail). Confirmed live: a window
        # with js_api set crashed the whole app against a real Discogs
        # page (and a second, different site) with a WinForms
        # `AccessibilityObject.Bounds` infinite-recursion error; an
        # otherwise-identical window with js_api removed stayed stable
        # against the same URL. js_api works by injecting pywebview's
        # bridge script into every frame of the loaded page -- fine for
        # MB Submit's own locally-built HTML, unsafe for a live
        # third-party page whose frames MetaForge doesn't control. The
        # overlay now talks to this app over plain fetch() to the
        # /verify_action/* routes instead (CORS-enabled there, see
        # _verify_action_cors) -- same docked-bar-in-one-window UX, safer
        # transport underneath.
        #
        # verify_api is stored on self so it isn't garbage-collected
        # while its window is open.
        global window
        verify_api = VerifyWindowAPI(
            window, urls, MANUAL_VERIFICATION_TIERS,
            on_close=lambda: setattr(self, '_active_verify_api', None),
        )
        # background_color='#ffffff', not MetaForge's usual '#141414' --
        # confirmed live 2026-07-17: a dark window background_color shows
        # through as an ugly dark striped artifact on any region of a
        # loaded third-party page that doesn't explicitly set its own
        # background (falling back to the browser-default white the
        # page's own author assumed, not this window's dark base). See
        # the identical fix + fuller explanation on
        # open_mb_relationship_seed_window's window a few lines up --
        # same root cause, same fix, both windows load real external
        # pages MetaForge doesn't control the CSS of.
        verify_window = webview.create_window(
            title, url=urls[0], width=1280, height=800,
            background_color='#ffffff',
        )
        verify_api.attach(verify_window)
        self._active_verify_api = verify_api

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
    # private_mode defaults to True (incognito-style, wiped every launch) --
    # confirmed live 2026-07-09 this was silently discarding a MusicBrainz
    # login on every app restart. storage_path makes this a real persistent
    # profile, same as any normal browser, harmless for the main window
    # (a local Flask UI with no real login state of its own) and required
    # for the MB Submit tool's pseudo-tab window to only need login once.
    #
    # debug=True (John, 2026-07-13) -- restores Ctrl+F/Ctrl+P/F5/zoom
    # browser accelerator keys on every window (WebView2 bundles them
    # all under one setting, AreBrowserAcceleratorKeysEnabled, which
    # pywebview's edgechromium backend ties directly to this debug flag --
    # confirmed by reading webview/platforms/edgechromium.py, not
    # guessed). John specifically wanted Ctrl+F back in the verify
    # window, to search a candidate source page for a name. Accepted
    # trade-off: Ctrl+R/F5 can now reload any window, including this
    # main one, discarding whatever's staged in it. OPEN_DEVTOOLS_IN_DEBUG
    # is explicitly disabled below so debug mode doesn't also pop a
    # DevTools pane open on every window load -- F12 still opens it
    # on demand, it just isn't forced.
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
    webview.start(debug=True, private_mode=False, storage_path=str(APPDATA_ROOT / "webview_profile"))