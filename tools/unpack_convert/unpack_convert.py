# --- START OF FILE unpack_convert.py ---
# ======================================================================
# MetaForge Tool Hub: Unpack & Convert
# Role: Primary tool orchestrator for ingestion and standardization.
# Build 7.10.0: Audio-Bearing Disc Detection + DSD Engine + Offset Source.
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

# Anything one of the Step 1/Step 2 engines can actually consume. A
# subfolder holding any of these directly is treated as a disc (John's
# decision, 2026-10-01). .7z is deliberately absent -- no engine extracts
# it, so a .7z-only folder would just become an empty "disc" and inflate
# TPOS; janitor_engine preserves and flags it instead.
DISC_SOURCE_EXT = {
    '.mp3', '.flac', '.ape', '.wav', '.m4a', '.wma', '.ogg', '.aiff', '.aif',
    '.wv', '.shn', '.tta', '.dsf', '.dff', '.iso', '.bin', '.zip', '.rar'
}

DISC_PATTERN = re.compile(r'(?:^|[\s\-_])(disc|disk|cd|v\.|vol|volume|part)[\s\-_]*(\d+)', re.I)

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
        return Response(
            stream_with_context(art_engine.finalize_cover_stream(data.get('path'), data.get('filename'))),
            mimetype='text/html'
        )

    if action == "set_locked_category":
        data = request.json or {}
        context_engine.update_locked_category(env_path, data.get('category', ''))
        return jsonify({"status": "success"})

    if action == "set_locked_artist":
        data = request.json or {}
        context_engine.update_locked_artist(env_path, data.get('artist', ''))
        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": f"Action {action} unrecognized."}), 400

def _natural_sort_key(text):
    """Helper for numerical sorting of directory names."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', str(text))]

def _is_audio_bearing(d_path):
    """True if the folder directly holds anything a Step 1/2 engine consumes."""
    try:
        return any(f.is_file() and f.suffix.lower() in DISC_SOURCE_EXT for f in d_path.iterdir())
    except Exception:
        return False

def _disc_sort_key(d_path):
    """
    Named discs first, in disc-number order ("CD1", "Disc 2", "Vol. 3");
    then any other audio-bearing folders ("Bonus Tracks", "Side A") in
    natural name order. Plain natural sort would put "Bonus" before
    "CD1" and shift every real disc's numbering by one.
    """
    m = DISC_PATTERN.search(d_path.name)
    if m:
        return (0, int(m.group(2)), _natural_sort_key(d_path.name))
    return (1, 0, _natural_sort_key(d_path.name))

def _find_disc_dirs(root):
    """
    Real bug, found in the 2026-10-01 review: disc detection used to be
    name-pattern only. Audio in a subfolder the pattern didn't match
    ("Disk 1", "Side A", "Bonus Tracks") was never sent to any engine,
    then janitor_engine deleted it as legacy cruft. Now any subfolder
    that directly holds consumable source material is a disc; the name
    pattern only decides ordering. Hidden folders (the .mf_zip_/.mf_rar_
    staging dirs, .DS_Store-style junk) and /art are never discs.
    """
    candidates = [
        d for d in root.iterdir()
        if d.is_dir()
        and d.name.lower() != 'art'
        and not d.name.startswith('.')
        and _is_audio_bearing(d)
    ]
    return sorted(candidates, key=_disc_sort_key)

def _orchestrate_workflow(data, env_path):
    """
    Orchestration Engine: Manages the bimodal lifecycle.
    Build 7.9.1: Synchronized 'ready for tagging.' hook for JS hand-off.
    Build 7.10.0: dsf_engine runs after SACD and before CUE in both
    branches -- after SACD so CD-DA/SACD ISO handling is settled first,
    before CUE so a CUE-referenced monolithic DSD is already decoded to
    FLAC when cue_engine looks for its source.
    """
    import cue_engine
    import zip_engine
    import rar_engine
    import sacd_engine
    import dsf_engine
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

    # NOTE: color: doesn't work on <img> for the same reason it never did
    # on the .upk-lock-icon (unpack_convert.mfi) -- an <img src> is an
    # opaque resource, no page CSS reaches inside it, whether the source
    # is a PNG or an SVG. mask-image + background-color is the proven
    # fix already used for this exact file (John's report, 2026-08-13).
    yield f'<div class="status-api" style="font-size:1rem;"><span aria-hidden="true" style="display:inline-block; width:36px; height:36px; vertical-align:middle; background-color:var(--mf-gold); -webkit-mask-image:url(\'/tool_asset/unpack_convert/unpack-convert.svg\'); mask-image:url(\'/tool_asset/unpack_convert/unpack-convert.svg\'); -webkit-mask-size:contain; mask-size:contain; -webkit-mask-repeat:no-repeat; mask-repeat:no-repeat; -webkit-mask-position:center; mask-position:center;"></span> Starting Processing: <span style="color:var(--text-output);">{album_name}</span></div>'

    for msg in zip_engine.extract_zip(root, report_data): yield msg
    for msg in rar_engine.extract_rar(root, report_data): yield msg

    disc_dirs = _find_disc_dirs(root)

    if disc_dirs:
        for d_path in disc_dirs:
            for msg in zip_engine.extract_zip(d_path, report_data): yield msg
            for msg in rar_engine.extract_rar(d_path, report_data): yield msg
            for msg in sacd_engine.process_sacd(d_path, artist, report_data): yield msg
            for msg in dsf_engine.process_dsf(d_path, artist, report_data): yield msg
            for msg in cue_engine.split_cue(d_path, artist, report_data): yield msg
    else:
        for msg in sacd_engine.process_sacd(root, artist, report_data): yield msg
        for msg in dsf_engine.process_dsf(root, artist, report_data): yield msg
        for msg in cue_engine.split_cue(root, artist, report_data): yield msg

    if not report_data.get('extraction_occurred', False):
        yield '<div class="status-api" style="margin-top:5px; padding-top:5px;"><span aria-hidden="true" style="font-size:32px; margin-bottom:-16px; margin-right:-8px;">📦</span> Step 1: Inspecting Original Audio Source. <br><span style="margin-left:45px; color:var(--text-output)">No archive bundles found. Unpacking not required.</span></div>'
        yield "<!-- PROGRESS:1:1:1 -->"

    # 3. STEP 2: BITSTREAM & METADATA
    if disc_dirs:
        total_discs = len(disc_dirs)
        # A lone audio-bearing subfolder (e.g. the user picked the parent
        # of the real album folder) is a single disc, not a 1-disc box
        # set -- no 1xx filing prefix, no TPOS "1/1".
        is_multidisc = total_discs > 1
        linear_offset = 0
        if is_multidisc:
            yield f'<div class="status-message" style="margin-left:50px; margin-top:5px; display:flex; align-items:center; gap:8px;"><img src="/ui/images/multi-disc.svg" alt="" aria-hidden="true" style="margin-left:3px; height:32px; width:auto;"> Box Set Detected: <strong>{total_discs} volume(s)</strong> found.</div>'

        for d_idx, d_path in enumerate(disc_dirs, 1):
            for msg in bitstream_engine.process_targets(d_path, artist, album_name, category, report_data,
                                                       disc_num=d_idx,
                                                       total_discs=total_discs,
                                                       offset=linear_offset,
                                                       is_multidisc=is_multidisc,
                                                       do_norm=do_norm):
                yield msg

            # Offset source (Build 7.10.0): the disc's own track count as
            # recorded by bitstream_engine from its deduplicated target
            # list -- NOT a count of whatever audio files remain on disk,
            # which also counted preserved failures and skipped duplicates.
            linear_offset += report_data.get('disc_track_counts', {}).get(d_idx, 0)
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
        yield f'<div class="status-api" style="margin-top:5px; padding-top:10px;"><span aria-hidden="true" style="font-size:36px!important;">🖼️</span> Step 4: Album Cover Selection: Local artwork not found.</div>'
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
