# --- START OF FILE intelli-tagger.py ---
# ======================================================================
# MetaForge Tool Hub: Intelli-Tagger
# Role: Master Orchestrator for Forensic Analysis & Metadata Mapping.
# Build 4.2.5: Label resolution via MBResolutionEngine
# ======================================================================

import os
import sys
import json
from pathlib import Path
from flask import Response, stream_with_context, request, jsonify

TOOL_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TOOL_ROOT.parent.parent
ENGINES_DIR = TOOL_ROOT / "engines"

if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler
import it_context_engine


def run_logic(action, tools_dir, env_path):
    if action == "get_context":
        return _handle_get_context()

    if action == "run_batch":
        data = request.json
        return Response(
            stream_with_context(_orchestrate_tagger_batch(data, env_path)),
            mimetype='text/html'
        )

    return jsonify({
        "status": "error",
        "message": f"Action {action} unrecognized."
    }), 400


def _handle_get_context():
    try:
        data = request.json
        path_str = data.get('path', '')

        if not path_str:
            return jsonify({"status": "error", "message": "No path provided"})

        target_path = Path(path_str)
        manifest_file = target_path / "manifest.json"

        if manifest_file.exists():
            return jsonify({
                "status": "success",
                "manifest": json.loads(manifest_file.read_text(encoding="utf-8"))
            })

        return jsonify({"status": "success", "manifest": None})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


def _extract_acoustid(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in ["acoustid", "acoustid_id", "id"]:
                return v

            found = _extract_acoustid(v)
            if found:
                return found

    if isinstance(obj, list):
        for item in obj:
            found = _extract_acoustid(item)
            if found:
                return found

    return None


def _orchestrate_tagger_batch(data, env_path):

    import health_engine
    import scrub_engine
    import ai_engine
    import acoustic_engine
    import id_engine
    import commit_engine
    import fingerprint_engine
    from mb_resolution_engine import MBResolutionEngine

    root_path = Path(data.get('path'))
    artist = data.get('artist')
    album = data.get('album')
    db_write = data.get('db_write', True)
    mb_ids = data.get('mb_ids', {})
    release_year = data.get('release_year', "Unknown")

    mb_track_map_list = data.get('mb_track_map', [])

    mb_track_lookup = {}

    for entry in mb_track_map_list:
        filename = entry.get("filename")
        position = entry.get("position")

        if filename:
            mb_track_lookup[("filename", filename)] = entry

        if position is not None:
            mb_track_lookup[("position", position)] = entry

    # ----------------------------------------------------------
    # RELEASE LABEL — fetched once here; label is release-level,
    # not track-level, so a single call covers the whole batch.
    # ----------------------------------------------------------
    release_label = "Unknown"
    release_mbid = mb_ids.get("album", "")

    if release_mbid and release_mbid not in ("None", "Unknown", ""):
        try:
            mb = MBResolutionEngine()
            release_label = mb.get_release_label(release_mbid)
        except Exception:
            release_label = "Unknown"

    yield '<!-- PROGRESS:5:Ingesting Content -->'
    yield f'<h2 class="it-log-entry it-val-gold"><img src="/ui/images/stamp.png" style="height:14px; width:auto; color:var(--mf-gold);" alt=""> Beginning Intelli-Tagging: <span style="color:var(--text-output);">{album}</span></h2>'

    yield from it_context_engine.initialize_audit_pair(root_path, data)

    yield '<!-- PROGRESS:15:Health Check -->'
    yield from health_engine.check_health(root_path)

    if health_engine.has_critical_failures(root_path):
        yield '<div>CRITICAL FAILURE</div>'
        return

    yield '<!-- PROGRESS:25:Scrubbing -->'
    yield from scrub_engine.scrub_tags(root_path)

    yield '<div class="it-log-entry it-val-gold" style="margin-top:25px;"><img src="/ui/images/genre.png" style="height:13px; width:auto; margin-bottom:-2px;" alt=""> Intelli-Tagger AI engines preparing for per-track tagging...</div>'

    # =========================================================
    # ACOUSTIC WAIT INDICATOR
    # Removal is handled by intelli-tagger.js when the first
    # it-log-row chunk arrives in the stream reader.
    # Scoped keyframe — no external CSS dependencies.
    # =========================================================
    yield '''<style>
@keyframes mf-wait-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
}
#it-acoustic-wait {
    animation: mf-wait-pulse 1.8s ease-in-out infinite;
    color: var(--mf-gold);
    padding: 6px 0;
    font-size: 0.7rem;
}
</style>
<div id="it-acoustic-wait" class="it-log-entry" role="status" aria-live="polite" style="margin-left:14px;margin-bottom:-10px; color:var(--text-output)">
    <img src="/ui/images/fingerprint.png" alt="" style="height:14px; width:auto; margin-bottom:-2px;"> Acoustic fingerprinting in progress - analysing all tracks, please wait...
</div>'''
    yield '<div style="border-top:1px solid var(--mf-gold); margin-top:15px;">&nbsp;</div>'
    files = sorted(list(root_path.glob("*.mp3")))
    total_files = len(files)

    track_results = []
    
    for idx, f_path in enumerate(files, 1):
        progress = int(40 + ((idx / total_files) * 45))
        yield f'<!-- PROGRESS:{progress}:Tagging Track {idx}/{total_files} -->'

        acoustic_data = acoustic_engine.analyze_file(f_path)

        if not isinstance(acoustic_data, dict):
            acoustic_data = dict(acoustic_data)

        fingerprint_data = fingerprint_engine.generate_acoustid(f_path)
        acoustid_value = _extract_acoustid(fingerprint_data)

        if acoustid_value:
            acoustic_data["acoustid"] = str(acoustid_value)

        filename = f_path.name

        fast_track = mb_track_lookup.get(("filename", filename))

        if not fast_track:
            fast_track = mb_track_lookup.get(("position", idx))

        if fast_track:

            identity_data = {
                "title": fast_track.get("title", f_path.stem),
                "mb_track_id": fast_track.get("mb_track_id", "None"),
                "mb_recording_id": fast_track.get("mb_recording_id", "None"),
                "acoustid": acoustic_data.get("acoustid", "None"),
                "original_year": release_year,
                "label": release_label,
                "personnel": [],
                "mb_artist_id": mb_ids.get("artist", "None"),
                "mb_album_id": mb_ids.get("album", "None"),
                "mb_group_id": mb_ids.get("release_group", "None"),
            }

            yield (
                f'<!-- FAST_PATH:{filename}:'
                f'{fast_track.get("mb_track_id", "None")}:'
                f'{fast_track.get("mb_work_id", "None")} -->'
            )

        else:
            identity_data = id_engine.get_identity(
                f_path,
                artist,
                acoustic_data.get('duration', 0),
                mb_ids,
                track_map=mb_track_map_list
            )

        title = identity_data.get("title", f_path.stem)

        try:
            ai_results = ai_engine.map_track_taxonomy(
                artist,
                title,
                acoustic_data
            )

        except Exception:
            ai_results = {
                "parent": "Unknown",
                "sub": "Unknown",
                "mood": "Unknown",
                "sonic_texture": "Unknown",
                "emotional_flavor": "Unknown"
            }

        combined = {}
        combined.update(acoustic_data)
        combined.update(identity_data)
        combined.update(ai_results)

        combined["original_year"] = release_year
        combined["display_date"] = release_year
        combined["label"] = release_label

        combined["file_path"] = str(f_path)

        if acoustic_data.get("acoustid"):
            combined["acoustid"] = acoustic_data["acoustid"]

        combined["mb_artist_id"] = mb_ids.get("artist", "None")
        combined["mb_album_id"] = mb_ids.get("album", "None")
        combined["mb_group_id"] = mb_ids.get("release_group", "None")

        track_results.append((f_path, combined))

        yield _render_deep_view_line(idx, total_files, f_path.name, combined)

    audit_fn = getattr(it_context_engine, "update_audit_trail", None)

    yield from commit_engine.execute_commit(
        root_path=root_path,
        track_results=track_results,
        db_write=db_write,
        manifest_seeds=data,
        audit_callback=audit_fn
    )

    yield '<!-- PROGRESS:100:Batch Complete -->'
    yield '<div style="margin-top:15px; border-top:1px solid var(--bg-accent); padding-top:10px;"><img src="/ui/images/complete.svg" alt="" aria-hidden="true" style="width:48px; height:48px; float:left; margin-right:8px; margin-top:5px;"><span style="font-size:1rem; font-weight:bold; margin-bottom:1rem;">Congratulations! You have successfully <span style="color:var(--mf-gold);">Intelli-Tagged</span> your files.</span><br>You are also encouraged to add the optional Personnel data (used by the Intelligent Playlist Maker) and an Artist Bio which will be stored in your database and used as part of the Library Viewer.</div>'
    yield '<div style="display:none;" id="it-handoff-trigger">HANDOFF_READY</div>'
    yield '<!-- BATCH_COMPLETE -->'


def _render_deep_view_line(idx, total, filename, data):

    idx_str = f"[{str(idx).rjust(len(str(total)))}/{total}]"

    line1 = f'<span class="it-val-gold">{idx_str}</span> <span class="it-val-white">{filename[:30].ljust(30)}</span> | '
    line1 += f'<span class="it-val-gold">Date:</span> <span class="it-val-white">{str(data.get("display_date", "Unknown")).ljust(4)}</span> | '
    line1 += f'<span class="it-val-gold">Genre:</span> <span class="it-val-white">{data.get("parent", "Unknown")[:13].ljust(13)}</span> | '
    line1 += f'<span class="it-val-gold">Sub Genre:</span> <span class="it-val-white">{data.get("sub", "Unknown")[:18].ljust(18)}</span>'

    subline = f'<div style="margin-right:10px; margin-left:-40px!important; text-align:left; margin-top:5px; border-bottom:1px solid var(--mf-gold); padding-bottom:5px; width:100%;">| '
    subline += f'<span class="it-val-gold">BPM:</span> <span class="it-val-white">{str(data.get("bpm", "0")).ljust(3)}</span> | '
    subline += f'<span class="it-val-gold">Key:</span> <span class="it-val-white">{data.get("key", "??").ljust(4)}</span> | '
    subline += f'<span class="it-val-gold">Int.:</span> <span class="it-val-white">{str(data.get("intensity", "1")).ljust(1)}</span> | '
    subline += f'<span class="it-val-gold">Mood:</span> <span class="it-val-white">{data.get("mood", "Unknown")[:12].ljust(12)}</span> | '
    subline += f'<span class="it-val-gold">Sonic Texture:</span> <span class="it-val-white">{data.get("sonic_texture", "Unknown")[:8].ljust(8)}</span> | '
    subline += f'<span class="it-val-gold">Emotional Flavor:</span> <span class="it-val-white">{data.get("emotional_flavor", "Unknown")[:10].ljust(10)}</span><br>'

    subline += f'| <span class="it-val-gold">MB TrackID:</span> <span class="it-val-white">{str(data.get("mb_track_id", "None"))[:37]}</span> | '
    subline += f'<span class="it-val-gold">AcoustID:</span> <span class="it-val-white">{str(data.get("acoustid", "None"))[:37]}</span></div>'

    return f'<div class="it-log-row"><span class="it-log-line1">{line1}</span><span class="it-log-subline">{subline}</span></div>'


# --- END OF FILE intelli-tagger.py ---