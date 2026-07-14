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
# Bounded retry/backoff for AcoustID 429 responses -- added 2026-07-14
# ahead of a real 7,700+ track bulk run, where hitting a rate limit
# somewhere in the middle was a real, not hypothetical, risk.
MAX_RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BASE_DELAY  = 2  # seconds; doubles each retry, capped below
# Real bug fixed here 2026-07-13, found live: this was
# `config_handler.ACOUSTID_API_KEY` with no `()` -- assigning the
# function OBJECT itself, not its return value. requests would have
# serialized that as the literal string "<function ACOUSTID_API_KEY at
# 0x...>" for the "client" parameter on every lookup/submit call this
# tool ever made, regardless of whatever key was actually in .env.
# Confirmed live: type(API_KEY) was <class 'function'> before this fix.
API_KEY      = config_handler.ACOUSTID_APPLICATION_KEY()
# Only needed for real submissions (the "user" parameter) -- lookups
# never use this. Not yet wired into submit_fingerprints() itself; that
# function still needs its own fix (wrong endpoint entirely -- see
# project memory) before this constant does anything useful.
USER_KEY     = config_handler.ACOUSTID_USER_KEY()
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

def _lookup_track_metadata(path):
    """
    Best-effort track metadata (title/artist/album/year/MB recording ID)
    to enrich an AcoustID submission -- every field AcoustID's submit API
    accepts here is optional, so a lookup failure must never block the
    actual fingerprint submission, just make it plainer. Joins `tracks`
    to `library_master` since artist/album live on the album row, not
    the track row.
    """
    try:
        db_path = str(path).replace('\\', '/')
        rows = db_engine.execute_query(
            "SELECT t.title, t.mb_recording_id, t.original_year, "
            "       lm.artist_name, lm.album_title "
            "FROM tracks t LEFT JOIN library_master lm ON t.mf_id = lm.mf_id "
            "WHERE t.file_path = ?",
            (db_path,)
        )
        return rows[0] if rows else {}
    except Exception:
        return {}


def submit_fingerprints():
    """STEP 1: Submit unknown tracks to the AcoustID database.

    Rebuilt 2026-07-13 -- this previously called /v2/lookup (a read-only
    endpoint) and reported "SUBMITTED" whenever that merely returned
    HTTP 200, regardless of whether anything was actually contributed.
    Nothing had ever been genuinely submitted to AcoustID through this
    tool. Real submission needs the /v2/submit endpoint, POST, BOTH the
    application key (client) and a separate personal user key (user)
    together -- AcoustID rejects a submission missing either -- and
    AcoustID's own index-suffixed batch convention (duration.0/
    fingerprint.0/etc.), always index 0 here since this still submits
    one track per request, matching the existing per-track loop/progress
    reporting rather than batching many tracks into one call.
    """
    if not API_KEY or not USER_KEY:
        missing = [name for name, val in (("ACOUSTID_APPLICATION_KEY", API_KEY), ("ACOUSTID_USER_KEY", USER_KEY)) if not val]
        yield (f'<div class="status-error"><span aria-hidden="true">🔥</span> '
               f'Missing {" and ".join(missing)} -- add {"it" if len(missing) == 1 else "them"} in Settings before submitting.</div>')
        return

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
                # Real bug fixed 2026-07-14, found live: this used to just
                # `continue` without re-queuing, so a track moved/renamed
                # after being queued vanished from pending_acoustid.txt for
                # good instead of waiting to be found again. Now stays
                # queued like every other failure branch below.
                yield f'<div class="status-message"><span aria-hidden="true">🤷🏻</span> [{index}/{total_tracks}] LOST: {path.name}</div>'
                remaining_pending.append(path_str)
                continue

            try:
                # 1. Generate Fingerprint
                result = subprocess.run([str(FPCALC), "-json", str(path)], capture_output=True, text=True)
                fp_data = json.loads(result.stdout)
                fingerprint = fp_data.get('fingerprint')
                duration = fp_data.get('duration')

                if not fingerprint or duration is None:
                    yield f'<div class="status-message"><span aria-hidden="true">⚠</span> [{index}/{total_tracks}] NO FINGERPRINT: {path.name}</div>'
                    remaining_pending.append(path_str)
                    continue

                # 2. Real AcoustID submission
                meta = _lookup_track_metadata(path)
                params = {
                    "client": API_KEY,
                    "user": USER_KEY,
                    "format": "json",
                    "duration.0": int(round(float(duration))),
                    "fingerprint.0": fingerprint,
                }
                if meta.get("title"):
                    params["track.0"] = meta["title"]
                if meta.get("artist_name"):
                    params["artist.0"] = meta["artist_name"]
                if meta.get("album_title"):
                    params["album.0"] = meta["album_title"]
                if meta.get("original_year"):
                    params["year.0"] = meta["original_year"]
                if meta.get("mb_recording_id"):
                    params["mbid.0"] = meta["mb_recording_id"]

                response, rate_limited = None, False
                delay = RATE_LIMIT_BASE_DELAY
                for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
                    response = session.post("https://api.acoustid.org/v2/submit", data=params, timeout=15)
                    if response.status_code != 429:
                        break
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else delay
                    rate_limited = True
                    if attempt < MAX_RATE_LIMIT_RETRIES:
                        yield (f'<div class="status-message" style="color:var(--mf-gold);"><span aria-hidden="true">⏳</span> '
                               f'[{index}/{total_tracks}] Rate-limited, waiting {wait:.0f}s (retry {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})...</div>')
                        time.sleep(wait)
                        delay = min(delay * 2, 60)

                if rate_limited and response.status_code == 429:
                    yield (f'<div class="status-message"><span aria-hidden="true">⚠</span> '
                           f'[{index}/{total_tracks}] STILL RATE LIMITED after {MAX_RATE_LIMIT_RETRIES} retries: {path.name} -- will retry next run</div>')
                    remaining_pending.append(path_str)
                    time.sleep(1)
                    continue

                data = response.json()

                if data.get("status") == "ok":
                    submissions = data.get("submissions") or []
                    sub_status = submissions[0].get("status") if submissions else "pending"
                    yield f'<div class="status-message"><span aria-hidden="true">✅</span> [{index}/{total_tracks}] SUBMITTED ({sub_status}): {path.name}</div>'
                    with open(HISTORY_FILE, 'a', encoding='utf-8') as h:
                        h.write(f"{path}\n")
                else:
                    err = data.get("error", {})
                    yield (f'<div class="status-message"><span aria-hidden="true">⚠</span> '
                           f'[{index}/{total_tracks}] API REJECTED: {path.name} (code {err.get("code")}: {err.get("message")})</div>')
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
                # Same silent-drop bug as submit_fingerprints() -- was
                # falling out of submission_history.txt for good instead of
                # staying queued for a later resolution attempt.
                remaining_history.append(path_str)
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
                
                res_obj, rate_limited = None, False
                delay = RATE_LIMIT_BASE_DELAY
                for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
                    res_obj = session.get("https://api.acoustid.org/v2/lookup", params=params, timeout=15)
                    if res_obj.status_code != 429:
                        break
                    retry_after = res_obj.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.replace('.', '', 1).isdigit() else delay
                    rate_limited = True
                    if attempt < MAX_RATE_LIMIT_RETRIES:
                        yield (f'<div class="status-message" style="color:var(--mf-gold);"><span aria-hidden="true">⏳</span> '
                               f'[{index}/{total_tracks}] Rate-limited, waiting {wait:.0f}s (retry {attempt + 1}/{MAX_RATE_LIMIT_RETRIES})...</div>')
                        time.sleep(wait)
                        delay = min(delay * 2, 60)

                if rate_limited and res_obj.status_code == 429:
                    yield (f'<div class="status-message"><span aria-hidden="true">⚠</span> '
                           f'[{index}/{total_tracks}] STILL RATE LIMITED after {MAX_RATE_LIMIT_RETRIES} retries: {path.name} -- will retry next run</div>')
                    remaining_history.append(path_str)
                    time.sleep(1)
                    continue

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