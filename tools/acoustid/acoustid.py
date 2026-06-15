# --- START OF FILE acoustid.py ---
# ======================================================================
# MetaForge Tool Logic: AcoustID Manager (V.Core - Build 1.0.5)
# Role: Fingerprint submission and resolution.
# Build 1.0.5: Accessibility Hardening (WCAG 2.2) & COGA Linguistic Sync.
# ======================================================================
import json
import subprocess
import requests
import time
from pathlib import Path
from flask import Response, stream_with_context
from common import config_handler, db_engine, tag_engine

# --- [ CONFIGURATION ] ---
DATA_DIR     = config_handler.DATA_DIR / "acoustid"
PENDING_FILE = DATA_DIR / "pending_acoustid.txt"
HISTORY_FILE = DATA_DIR / "submission_history.txt"
API_KEY      = config_handler.ACOUSTID_API_KEY
FPCALC       = config_handler.FPCALC_EXE

def run_logic(action, tools_dir, env_path):
    """
    Universal Dispatcher Entry Point.
    """
    if action == "submit":
        return Response(stream_with_context(submit_fingerprints()), mimetype='text/plain')
    elif action == "resolve":
        return Response(stream_with_context(resolve_ids()), mimetype='text/plain')
    
    return json.dumps({"status": "error", "message": "Unknown action"}), 400

# --- [ CORE OPERATIONS ] ---

def submit_fingerprints():
    """STEP 1: Submit unknown tracks to the AcoustID database."""
    if not PENDING_FILE.exists() or PENDING_FILE.stat().st_size == 0:
        yield f'<span aria-hidden="true">⚠</span> No pending tracks found in data/acoustid/pending_acoustid.txt'
        return

    pending_paths = PENDING_FILE.read_text(encoding='utf-8').splitlines()
    total_tracks = len(pending_paths)
    remaining_pending = []

    yield f'<div class="status-api"><span aria-hidden="true">📨</span> Starting submission of {total_tracks} tracks...</div>'

    with requests.Session() as session:
        for index, path_str in enumerate(pending_paths, 1):
            path = Path(path_str.strip())
            if not path.exists():
                yield f'<div class="status-message"><span aria-hidden="true">🤷🏻</span> [{index}/{total_tracks}] LOST: {path.name}</div>'
                continue

            try:
                # 1. Generate Fingerprint
                result = subprocess.run([str(FPCALC), "-json", str(path)], capture_output=True, text=True)
                fp_data = json.loads(result.stdout)
                
                # 2. API Submission
                params = {
                    "client": API_KEY,
                    "format": "json",
                    "duration": int(fp_data.get('duration', 0)),
                    "fingerprint": fp_data.get('fingerprint'),
                    "meta": "recordings"
                }
                response = session.get("https://api.acoustid.org/v2/lookup", params=params, timeout=15)
                
                if response.status_code == 200:
                    yield f'<div class="status-message"><span aria-hidden="true">✅</span> [{index}/{total_tracks}] SUBMITTED: {path.name}</div>'
                    with open(HISTORY_FILE, 'a', encoding='utf-8') as h:
                        h.write(f"{path}\n")
                else:
                    yield f'<div class="status-message"><span aria-hidden="true">⚠</span> [{index}/{total_tracks}] API REJECTED: {path.name}</div>'
                    remaining_pending.append(path_str)

                time.sleep(1)

            except Exception as e:
                yield f'<div class="status-error"><span aria-hidden="true">🔥</span> [{index}/{total_tracks}] ERROR: {path.name} ({str(e)})</div>'
                remaining_pending.append(path_str)

    PENDING_FILE.write_text("\n".join(remaining_pending), encoding='utf-8')
    
    # TERMINAL WARNING: COGA 4.4.1 Expectations Management
    yield f'''
    <div class="status-ok" style="margin-top:10px; border-top:1px solid var(--bg-accent); padding-top:10px;">
        <span aria-hidden="true">✅</span> Step 1 Sequence Concluded.
        <div style="color:var(--mf-gold); font-size:0.75rem; margin-top:5px; margin-left:20px;">
            <strong>Archival Note:</strong> Verified identity resolution typically takes up to 10 weeks to become public.
        </div>
    </div>'''

def resolve_ids():
    """STEP 2: Resolve previously submitted tracks and finalize library."""
    if not HISTORY_FILE.exists() or HISTORY_FILE.stat().st_size == 0:
        yield f'<span aria-hidden="true">⚠</span> No submission history found.'
        return

    history_paths = HISTORY_FILE.read_text(encoding='utf-8').splitlines()
    total_tracks = len(history_paths)
    remaining_history = []
    resolved_count = 0

    yield f'<div class="status-api"><span aria-hidden="true">✨</span> Auditing {total_tracks} previously submitted tracks...</div>'

    with requests.Session() as session:
        for index, path_str in enumerate(history_paths, 1):
            path = Path(path_str.strip())
            if not path.exists():
                continue

            try:
                result = subprocess.run([str(FPCALC), "-json", str(path)], capture_output=True, text=True)
                fp_data = json.loads(result.stdout)
                params = {
                    "client": API_KEY,
                    "format": "json",
                    "duration": int(fp_data.get('duration', 0)),
                    "fingerprint": fp_data.get('fingerprint'),
                    "meta": "recordings"
                }
                
                res_obj = session.get("https://api.acoustid.org/v2/lookup", params=params, timeout=15)
                res = res_obj.json()

                if res.get('results') and res['results'][0].get('id'):
                    new_aid = res['results'][0]['id']
                    tag_engine.update_tags(path, {'mf_acoustid': new_aid})
                    
                    db_path = str(path).replace('\\', '/')
                    db_engine.execute_query(
                        "UPDATE tracks SET acoustid = ? WHERE file_path = ?", 
                        (new_aid, db_path), 
                        commit=True
                    )
                    
                    yield f'<div class="status-message"><span aria-hidden="true">✨</span> [{index}/{total_tracks}] RESOLVED: {path.name}</div>'
                    resolved_count += 1
                else:
                    remaining_history.append(path_str)
                    if index % 10 == 0:
                        yield f'<div class="status-message" style="color:var(--text-message);"><span aria-hidden="true">🕑</span> [{index}/{total_tracks}] Still pending resolution...</div>'

                time.sleep(1)

            except Exception as e:
                yield f'<div class="status-error"><span aria-hidden="true">🔥</span> [{index}/{total_tracks}] ERROR: {path.name}</div>'
                remaining_history.append(path_str)

    HISTORY_FILE.write_text("\n".join(remaining_history), encoding='utf-8')
    yield f'<div class="status-ok"><span aria-hidden="true">✅</span> Step 2 Sequence Concluded. {resolved_count} tracks finalized.</div>'

# --- ACOUSTID ENGINE END ---
# --- END OF FILE acoustid.py ---