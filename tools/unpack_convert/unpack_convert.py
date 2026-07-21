# --- START OF FILE unpack_convert.py ---
# ======================================================================
# MetaForge Tool Hub: Unpack & Convert
# Role: Primary tool orchestrator for ingestion and standardization.
# Build 7.9.1: Workflow Handoff Sync (Ready for Tagging Hook).
# Physical Location: \tools\unpack_convert\unpack_convert.py
# ======================================================================
import os
import sys
import re
from pathlib import Path
from flask import Response, stream_with_context, request, jsonify

# --- [ ARCHITECTURAL BOOTSTRAP ] ---
TOOL_ROOT = Path(__file__).parent.resolve()
ENGINES_DIR = TOOL_ROOT / "engines"
if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))

import context_engine
from common import io_bridge

def run_logic(action, tools_dir, env_path):
    """
    Primary Spoke Dispatcher: Routes requests to specialized engines.
    """
    if action == "get_interview_data":
        return context_engine.handle_interview_fetch(env_path)

    if action == "run_unpack":
        data = request.json
        return Response(
            stream_with_context(_orchestrate_workflow(data, env_path)),
            mimetype='text/html'
        )

    # --- [ DISPATCHER: STEP 4 ART ROUTES ] ---
    if action == "get_art_gallery":
        path = request.args.get('path')
        if not path:
            return jsonify([])
        import art_engine
        gallery = art_engine.scan_art_folder(path)
        return jsonify(gallery)

    if action == "finalize_art":
        data = request.json
        if not data or not data.get('path') or not data.get('filename'):
            return jsonify({"status": "error", "message": "Missing required promotion data."})
        import art_engine
        result = art_engine.finalize_cover(data.get('path'), data.get('filename'))
        return jsonify(result)

    return jsonify({"status": "error", "message": f"Action {action} unrecognized."}), 400

def _natural_sort_key(text):
    """Helper for numerical sorting of directory names."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def _orchestrate_workflow(data, env_path):
    """
    Orchestration Engine: Manages the bimodal lifecycle.
    Build 7.9.1: Synchronized 'ready for tagging.' hook for JS hand-off.
    """
    import cue_engine
    import zip_engine
    import rar_engine
    import bitstream_engine
    import janitor_engine
    import art_engine

    # 1. INITIALIZATION
    root = Path(data.get('path'))
    artist = data.get('artist')
    album_name = data.get('album')
    do_norm = data.get('normalization', False)
    library_type = context_engine.get_policy(env_path)
    
    category = data.get('category')
    if library_type != "ENHANCED":
        category = None 

    report_data = {
        "phase": "Unpack & Convert",
        "extraction": {"source": "None", "count": 0},
        "conversion": [],
        "deletions": [],
        "artwork": [],
        "final_track_count": 0
    }

    if data.get('remember'):
        context_engine.update_consent_status(env_path, "TRUE")

    yield f'<div class="status-api" style="font-size:1rem;"><span aria-hidden="true">🔓</span> Starting Processing: <span style="color:var(--text-output);">{album_name}</span></div>'

    # 2. STEP 1: EXTRACTION & DISCOVERY
    # Root-level archives first -- a single monolithic ZIP/RAR for the whole
    # box set gets extracted and hoisted here (zip_engine/rar_engine already
    # preserve any Disc N subfolders found inside it).
    for msg in zip_engine.extract_zip(root, report_data): yield msg
    for msg in rar_engine.extract_rar(root, report_data): yield msg

    # Disc detection -- computed ONCE, here, after root-level extraction (so
    # it sees Disc N folders whether they arrived pre-split on disk or were
    # just hoisted out of a root-level archive). Step 2 below reuses this
    # same disc_dirs list rather than recomputing it, so the two steps can
    # never disagree about what counts as a disc.
    # [\s\-_]* between the keyword and the number (not \s*) -- the naming
    # convention is immaterial (John, 2026-07-08): "CD 1", "CD1", "CD-1",
    # "CD_1", "Disc_2", "Vol-3" all need to resolve to the same disc
    # number. Verified: the space/no-separator forms already matched,
    # but hyphen/underscore variants ("CD-1", "Disc_1") did not.
    disc_pattern = re.compile(r'(?:^|[\s\-_])(disc|cd|v\.|vol|volume|part)[\s\-_]*(\d+)', re.I)
    sub_dirs = sorted([d for d in root.iterdir() if d.is_dir() and d.name.lower() != 'art'], key=lambda x: _natural_sort_key(x.name))
    disc_dirs = [d for d in sub_dirs if disc_pattern.search(d.name)]

    # Real bug, found live 2026-07-20 (John's multi-disc box set report):
    # this step used to glob only root for .zip/.cue/.rar, so a box set
    # whose per-disc CUE/archive files live inside "Disc 1"/"Disc 2"
    # subfolders was invisible here -- it printed "No archive bundles
    # found" and skipped splitting entirely for BOTH discs, while Step 2
    # (disc-aware) ran anyway and converted each disc's one unsplit source
    # file as if it were a single track. Now each disc directory is
    # checked in its own right for nested archives/CUEs.
    if disc_dirs:
        for d_path in disc_dirs:
            for msg in zip_engine.extract_zip(d_path, report_data): yield msg
            for msg in rar_engine.extract_rar(d_path, report_data): yield msg
            for msg in cue_engine.split_cue(d_path, artist, report_data): yield msg
    else:
        for msg in cue_engine.split_cue(root, artist, report_data): yield msg

    if not report_data.get('extraction_occurred', False):
        yield '<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:5px;"><span aria-hidden="true">📦</span> Step 1: Inspecting Original Audio Source. <br><span style="margin-left:25px; color:var(--text-output)">No archive bundles found. Unpacking not required.</span></div>'
        yield "<!-- PROGRESS:1:1:1 -->"

    # 3. STEP 2: BITSTREAM & METADATA
    if disc_dirs:
        total_discs = len(disc_dirs)
        linear_offset = 0
        yield f'<div class="status-message" style="margin-left:1.5rem; margin-top:5px; display:flex; align-items:center; gap:8px;"><img src="/ui/images/multi-disc.svg" alt="" aria-hidden="true" style="margin-left:3px; height:20px; width:auto;"> Box Set Detected: <strong>{total_discs} volume(s)</strong> found.</div>'
        
        for d_idx, d_path in enumerate(disc_dirs, 1):
            for msg in bitstream_engine.process_targets(d_path, artist, album_name, category, report_data, 
                                                       disc_num=d_idx, 
                                                       total_discs=total_discs, 
                                                       offset=linear_offset, 
                                                       is_multidisc=True,
                                                       do_norm=do_norm):
                yield msg
            
            audio_exts = {'.mp3', '.flac', '.wav', '.ape', '.m4a', '.ogg'}
            linear_offset += len([f for f in d_path.iterdir() if f.suffix.lower() in audio_exts])
    else:
        for msg in bitstream_engine.process_targets(root, artist, album_name, category, report_data, 
                                                   disc_num=1, 
                                                   total_discs=1, 
                                                   offset=0, 
                                                   is_multidisc=False,
                                                   do_norm=do_norm):
            yield msg

    # 4. STEP 3: JANITORIAL PHASE
    yield from janitor_engine.execute_cleanup(root, report_data)

    # 5. STEP 4: SIGNAL ART SELECTION OR ACTIVATE CLOUD FALLBACK
    if report_data.get('artwork') and len(report_data['artwork']) > 0:
        # JS picks this up and shows the gallery
        yield "<!-- ART_READY -->"
    else:
        yield f'<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:10px;"><span aria-hidden="true">🖼️</span> Step 4: Album Cover Selection: Local artwork not found.</div>'
        yield f'<div class="status-message" style="color:var(--text-output); margin-left:1rem; margin-left:15px;"><img src="/ui/images/cloud.png" style="height:14px; width:auto;" alt=""> Querying Discogs Archive for {album_name}...</div>'
        
        cloud_res = art_engine.trigger_discogs_fetch(root, artist, album_name)
        
        if cloud_res['status'] == 'success':
            # Build 7.9.1: Inclusion of "ready for tagging." ensures injectHandoffButton triggers in JS
            yield f'''
            <div class="status-success" style="margin-top:10px; font-size:.8rem; overflow:hidden;">
                <div>
                    Cloud Recovery Successful: Archival cover fetched from <strong>{cloud_res['source']}</strong>.<br>
                    <span style="color:var(--text-message); font-size:0.7rem;">{cloud_res['embedded_count']} files updated with archival artwork ({cloud_res['dims']}).</span><br>
                    <span style="color:var(--mf-gold); font-weight:bold;">{album_name}</span> is now prepped and ready for tagging.
                </div>
            </div>'''
        else:
            # Build 7.9.1: Inclusion of "ready for tagging." ensures injectHandoffButton triggers in JS
            yield f'''
            <div class="status-success" style="margin-top:10px; font-size:.8rem; overflow:hidden;">
                <div>
                    Processing Complete: <span style="color:var(--mf-gold); font-weight:bold;">{album_name}</span> is now prepped and ready for tagging.<br>
                    <span style="color:var(--status-error); font-size:0.7rem;">(Note: No artwork identified locally or in cloud archives)</span>
                </div>
            </div>'''

    # 6. FINALIZATION & FORENSIC AUDIT
    final_audio_list = io_bridge.get_audio_targets(root, recursive=True)
    report_data["final_track_count"] = len(final_audio_list)
    
    context_engine.write_audit_log(root, report_data)
    
    manifest_category = category if category else "None Provided"
    context_engine.generate_manifest(
        root, 
        artist, 
        album_name, 
        manifest_category, 
        library_type, 
        track_count=report_data["final_track_count"]
    )

# --- END OF FILE unpack_convert.py ---