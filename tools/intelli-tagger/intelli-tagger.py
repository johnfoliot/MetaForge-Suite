# --- START OF FILE intelli-tagger.py ---
# ======================================================================
# MetaForge Tool Hub: Intelli-Tagger
# Role: Master Orchestrator for Forensic Analysis & Metadata Mapping.
# Build 4.0.7: 3-Line Forensic Depth | Sonic Texture & Emotional Flavor.
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
    """
    Primary Spoke Dispatcher: Routes UI triggers to specialized engines.
    """
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
    """
    Phase 1 Prep: Ingests existing manifest data if present.
    Target: Eliminates data-entry friction via Forensic Seed recovery.
    """
    try:
        data = request.json
        path_str = data.get('path', '')
        if not path_str:
            return jsonify({"status": "error", "message": "No path provided"})

        target_path = Path(path_str)
        manifest_file = target_path / "manifest.json"
        
        if manifest_file.exists():
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            return jsonify({"status": "success", "manifest": manifest_data})
                
        return jsonify({"status": "success", "manifest": None})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def _orchestrate_tagger_batch(data, env_path):
    """
    The Forensic Pulse: Orchestrates Phases 1 through 7.
    Build 4.0.7: 3-line formatting for maximum forensic density.
    """
    # Dynamic Engine Imports
    import it_context_engine 
    import health_engine
    import scrub_engine
    import ai_engine
    import acoustic_engine
    import id_engine
    import commit_engine

    # 1. SETUP & INITIALIZATION
    root_path = Path(data.get('path'))
    artist = data.get('artist')
    album = data.get('album')
    db_write = data.get('db_write', True)
    mb_ids = data.get('mb_ids', {})
    release_year = data.get('release_year', "Unknown")
    
    yield '<!-- PROGRESS:5:Ingesting Content    -->'
    yield f'<h2 class="it-log-entry it-val-gold"><img src="/ui/images/stamp.png" style="height:14px; width:auto;" alt=""> Beginning Intelli-Tagging: <span style="color:var(--text-output);">{album}</span></h2>'

    # PHASE 1: CONTEXT INGESTION
    yield from it_context_engine.initialize_audit_pair(root_path, data)

    # PHASE 2: HEALTH (The Gatekeeper)
    yield '<!-- PROGRESS:15:Performing Health Check    -->'
    yield from health_engine.check_health(root_path)
    
    if health_engine.has_critical_failures(root_path):
        yield '<div class="it-val-error">🚨 CRITICAL: Persistent bitstream corruption detected.</div>'
        yield '<!-- REDIRECT_REPAIR -->'
        return

    # PHASE 3: THE CLEAN ROOM SCRUB
    yield '<!-- PROGRESS:25:Cleaning Legacy Metadata   -->'
    yield from scrub_engine.scrub_tags(root_path)

    # PHASE 4: AI TAXONOMY MAPPING — Now per-track; called inside the track loop below.
    yield '<div class="it-log-entry it-val-gold" style="margin-top:25px;margin-bottom:15px; border-bottom:1px solid var(--mf-gold); padding-bottom:10px;"><img src="/ui/images/genre.png" style="height:13px; width:auto;" alt=""> Intelli-Tagger AI engines preparing for per-track tagging...</div>'

    # PHASE 5 & 6: ACOUSTIC & IDENTITY FORENSICS
    track_results = []
    files = sorted(list(root_path.glob("*.mp3")))
    total_files = len(files)

    for idx, f_path in enumerate(files, 1):
        progress = int(40 + ((idx / total_files) * 45))
        yield f'<!-- PROGRESS:{progress}:Analyzing and Tagging {idx}/{total_files}    -->'
        yield f'<script>updateProgressBar({progress});</script>'

        # Step A: Acoustic Analysis
        acoustic_data = acoustic_engine.analyze_file(f_path)
        # Serialization Safety: ensure acoustic_data is a valid dict with no Path objects
        if not isinstance(acoustic_data, dict):
            acoustic_data = dict(acoustic_data)
        acoustic_data = {k: str(v) if isinstance(v, Path) else v for k, v in acoustic_data.items()}

        # Step B: Identity Recovery (Build 1.7.2 — pre-flight tag reads before API)
        identity_data = id_engine.get_identity(f_path, artist, acoustic_data['duration'], mb_ids)

        # Step C: AI Taxonomy Mapping (per-track, returns dict directly)
        title = identity_data.get('title', f_path.stem)
        try:
            ai_results = ai_engine.map_track_taxonomy(artist, title, acoustic_data)
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">⚠️ AI mapping failed for {f_path.name}: {str(e)}. Using defaults.</div>'
            ai_results = {"parent": "Unknown", "sub": "Unknown", "mood": "Unknown",
                          "sonic_texture": "Unknown", "emotional_flavor": "Unknown",
                          "country": "Unknown"}

        # Step D: Date Fallback Logic
        ui_date = identity_data.get('original_year', "Unknown")
        if ui_date == "Unknown":
            ui_date = release_year

        # Step E: Combine Forensic Packet — f_path cast to str for JSON serialization safety
        # ai_results already contains merged acoustic data (ai_engine does data.update(acoustic_data))
        combined = {**acoustic_data, **identity_data, **ai_results}
        combined['display_date'] = ui_date
        combined['file_path'] = str(f_path)
        
        track_results.append((f_path, combined))
        
        # Build 4.0.7: Yield the revised 3-line formatted block
        yield _render_deep_view_line(idx, total_files, f_path.name, combined)

    # PHASE 7: THE RELATIONAL & PHYSICAL COMMIT
    yield '<!-- PROGRESS:90:Finalizing Commit -->'
    yield from commit_engine.execute_commit(
        root_path, 
        track_results, 
        db_write=db_write, 
        manifest_seeds=data
    )

    # FINALIZATION
    yield '<!-- PROGRESS:100:Batch Complete -->'
    yield '<div style="margin-top:15px; border-top:1px solid var(--bg-accent); padding-top:10px;"><img src="/ui/images/complete.svg" alt="" aria-hidden="true" style="width:48px; height:48px; float:left; margin-right:8px; margin-top:5px;"><span style="font-size:1rem; font-weight:bold; margin-bottom:1rem;">Congratulations! You have successfully <span style="color:var(--mf-gold);">Intelli-Tagged</span> your files.</span><br>You are also encouraged to add the optional Personnel data (used by the Intelligent Playlist Maker) and an Artist Bio which will be stored in your database and used as part of the Library Viewer.</div>'
    yield '<div style="display:none;" id="it-handoff-trigger">HANDOFF_READY</div>'
    yield '<!-- BATCH_COMPLETE -->'

def _render_deep_view_line(idx, total, filename, data):
    """
    Build 4.0.7: Formats track feedback into a 3-line forensic block.
    Line 1: filename | Date | Genre | Sub Genre
    Line 2: BPM | Key | Intensity | Mood | Sonic Texture | Emotional Flavor
    Line 3: MB TrackID | AcoustID
    """
    idx_str = f"[{str(idx).rjust(len(str(total)))}/{total}]"

    # Line 1: Primary Identity & Taxonomy Mapping
    line1 = f'<span class="it-val-gold">{idx_str}</span> <span class="it-val-white">{filename[:30].ljust(30)}</span> | '
    line1 += f'<span class="it-val-gold">Date:</span> <span class="it-val-white">{str(data.get("display_date", "Unknown")).ljust(4)}</span> | '
    line1 += f'<span class="it-val-gold">Genre:</span> <span class="it-val-white">{data.get("parent", "Unknown")[:13].ljust(13)}</span> | '
    line1 += f'<span class="it-val-gold">Sub Genre:</span> <span class="it-val-white">{data.get("sub", "Unknown")[:18].ljust(18)}</span>'

    # Line 2: Acoustic Forensics & AI Descriptors
    subline = f'<div style="margin-right:10px; text-align:left; margin-top:5px; border-bottom:1px solid var(--mf-gold); padding-bottom:5px; width:100%;">| <span class="it-val-gold">BPM:</span> <span class="it-val-white">{str(data.get("bpm", "0")).ljust(3)}</span> | '
    subline += f'<span class="it-val-gold">Key:</span> <span class="it-val-white">{data.get("key", "??").ljust(4)}</span> | '
    subline += f'<span class="it-val-gold">Int.:</span> <span class="it-val-white">{str(data.get("intensity", "1")).ljust(1)}</span> | '
    subline += f'<span class="it-val-gold">Mood:</span> <span class="it-val-white">{data.get("mood", "Unknown")[:8].ljust(8)}</span> | '
    subline += f'<span class="it-val-gold">Sonic Texture:</span> <span class="it-val-white">{data.get("sonic_texture", "Unknown")[:8].ljust(8)}</span> | '
    subline += f'<span class="it-val-gold">Emotional Flavor:</span> <span class="it-val-white">{data.get("emotional_flavor", "Unknown")[:10].ljust(10)}</span><br>'

    # Line 3: Public Identity IDs
    subline += f'| <span class="it-val-gold">MB TrackID:</span> <span class="it-val-white">{str(data.get("mb_track_id", "None"))[:37]}</span> | '
    subline += f'<span class="it-val-gold">AcoustID:</span> <span class="it-val-white">{str(data.get("acoustid", "None"))[:37]}</span></div>'
    
    # Wrap in structural div classes defined in mfi
    html = f'<div class="it-log-row">'
    html += f'<span class="it-log-line1">{line1}</span>'
    html += f'<span class="it-log-subline">{subline}</span>'
    html += '</div>'

    return html

# --- END OF FILE intelli-tagger.py ---
