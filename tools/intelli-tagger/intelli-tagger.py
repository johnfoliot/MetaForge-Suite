# --- START OF FILE intelli-tagger.py ---
# ======================================================================
# MetaForge Tool Hub: Intelli-Tagger
# Role: Master Orchestrator for Forensic Analysis & Metadata Mapping.
# Build 4.1.0: Forensic Packet Integrity Patch with Full UI Restoration.
# Physical Location: \tools\intelli-tagger\intelli-tagger.py
# ======================================================================
import os
import sys
import json
from pathlib import Path
from flask import Response, stream_with_context, request, jsonify

# --- [ ARCHITECTURAL BOOTSTRAP ] ---
TOOL_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TOOL_ROOT.parent.parent 
ENGINES_DIR = TOOL_ROOT / "engines"

if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler

def run_logic(action, tools_dir, env_path):
    if action == "get_context":
        return _handle_get_context()
    if action == "run_batch":
        data = request.json
        return Response(
            stream_with_context(_orchestrate_tagger_batch(data, env_path)),
            mimetype='text/html'
        )
    return jsonify({"status": "error", "message": f"Action {action} unrecognized."}), 400

def _handle_get_context():
    try:
        data = request.json
        path_str = data.get('path', '')
        if not path_str: return jsonify({"status": "error", "message": "No path provided"})
        target_path = Path(path_str)
        manifest_file = target_path / "manifest.json"
        if manifest_file.exists():
            with open(manifest_file, 'r', encoding='utf-8') as f:
                return jsonify({"status": "success", "manifest": json.load(f)})
        return jsonify({"status": "success", "manifest": None})
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

def _orchestrate_tagger_batch(data, env_path):
    import it_context_engine, health_engine, scrub_engine, ai_engine, acoustic_engine, id_engine, commit_engine

    root_path = Path(data.get('path'))
    artist = data.get('artist')
    album = data.get('album')
    db_write = data.get('db_write', True)
    mb_ids = data.get('mb_ids', {})
    release_year = data.get('release_year', "Unknown")
    
    yield ''
    yield f'<h2 class="it-log-entry it-val-gold"><img src="/ui/images/stamp.png" style="height:14px; width:auto;" alt=""> Beginning Intelli-Tagging: <span style="color:var(--text-output);">{album}</span></h2>'
    yield from it_context_engine.initialize_audit_pair(root_path, data)
    yield ''
    yield from health_engine.check_health(root_path)
    
    if health_engine.has_critical_failures(root_path):
        yield '<div class="it-val-error">🚨 CRITICAL: Persistent bitstream corruption detected.</div>'
        return

    yield ''
    yield from scrub_engine.scrub_tags(root_path)
    yield ''
    yield from ai_engine.map_taxonomy(artist, album, env_path)
    ai_results = ai_engine.get_last_result()

    yield ''
    track_map = id_engine.resolve_tracklist(mb_ids.get('album'))

    track_results = []
    files = sorted(list(root_path.glob("*.mp3")))
    total_files = len(files)

    for idx, f_path in enumerate(files, 1):
        progress = int(40 + ((idx / total_files) * 45))
        yield f''
        
        acoustic_data = acoustic_engine.analyze_file(f_path)
        identity_data = id_engine.get_identity(f_path, artist, acoustic_data['duration'], mb_ids, track_map)
        
        ui_date = identity_data.get('original_year', "Unknown")
        if ui_date == "Unknown": ui_date = release_year

        combined = ai_results.copy()
        combined.update(acoustic_data)
        combined.update(identity_data)
        combined['display_date'] = ui_date
        
        track_results.append((f_path, combined))
        yield _render_deep_view_line(idx, total_files, f_path.name, combined)

    yield ''
    yield from commit_engine.execute_commit(root_path, track_results, db_write=db_write, manifest_seeds=data)
    
    yield ''
    yield '<div style="margin-top:15px; font-weight:bold; border-top:1px solid var(--bg-accent); padding-top:10px;"><img src="/ui/images/complete.svg" alt="" aria-hidden="true" style="width:48px; height:48px; float:left; margin-right:8px; margin-top:5px;"><span style="font-size:1rem;">Congratulations! You have successfully <span style="color:var(--mf-gold);">Intelli-Tagged</span> your files.</span><br>You are also encouraged to add the optinoal Personnel data (used by the Intelligent Playlist Maker) and an Artist Bio which will be stored in your database and used as part of the Library Viewer.</div>'
    yield '<div style="display:none;" id="it-handoff-trigger">HANDOFF_READY</div>'
    yield ''

def _render_deep_view_line(idx, total, filename, data):
    idx_str = f"[{str(idx).rjust(len(str(total)))}/{total}]"
    line1 = f'<span class="it-val-gold">{idx_str}</span> <span class="it-val-white">{filename[:30].ljust(30)}</span> | '
    line1 += f'<span class="it-val-gold">Date:</span> <span class="it-val-white">{str(data.get("display_date", "Unknown")).ljust(4)}</span> | '
    line1 += f'<span class="it-val-gold">Genre:</span> <span class="it-val-white">{data.get("parent", "Unknown")[:15].ljust(15)}</span> | '
    line1 += f'<span class="it-val-gold">Sub Genre:</span> <span class="it-val-white">{data.get("sub", "Unknown")[:18].ljust(18)}</span>'
    
    subline = f'<div style="margin-right:10px; text-align:left;">| <span class="it-val-gold">BPM:</span> <span class="it-val-white">{str(data.get("bpm", "0")).ljust(3)}</span> | '
    subline += f'<span class="it-val-gold">Key:</span> <span class="it-val-white">{data.get("key", "??").ljust(5)}</span> | '
    subline += f'<span class="it-val-gold">Intensity:</span> <span class="it-val-white">{str(data.get("intensity", "1")).ljust(2)}</span> | '
    subline += f'<span class="it-val-gold">Mood:</span> <span class="it-val-white">{data.get("mood", "Animated")[:12].ljust(12)}</span> | '
    subline += f'<span class="it-val-gold">MB TrackID:</span> <span class="it-val-white">{str(data.get("mb_track_id", "None"))[:8]}</span> | '
    subline += f'<span class="it-val-gold">AcoustID:</span> <span class="it-val-white">{str(data.get("acoustid", "None"))[:8]}</span></div>'

    return f'<div class="it-log-row"><span class="it-log-line1">{line1}</span><span class="it-log-subline">{subline}</span></div>'

# --- END OF FILE intelli-tagger.py 