# --- START OF FILE intelli-tagger.py ---
# ======================================================================
# MetaForge Tool Hub: Intelli-Tagger
# Role: Master Orchestrator for Forensic Analysis & Metadata Mapping.
# Build 4.2.5: Label resolution via MBResolutionEngine
# ======================================================================

import os
import sys
import re
import json
import functools
from pathlib import Path
from flask import Response, stream_with_context, request, jsonify

TOOL_ROOT = Path(__file__).parent.resolve()
PROJECT_ROOT = TOOL_ROOT.parent.parent
ENGINES_DIR = TOOL_ROOT / "engines"

if str(ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINES_DIR))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler, db_engine, tag_engine
import it_context_engine


def _natural_track_sort_key(path):

    match = re.match(r'^0*(\d+)', path.stem)
    number = int(match.group(1)) if match else float('inf')
    return (path.parent.as_posix(), number, path.name)


def run_logic(action, tools_dir, env_path):
    if action == "get_context":
        return _handle_get_context()

    if action == "get_taxonomy":
        return _handle_get_taxonomy()

    if action == "reanalyze_track":
        return _handle_reanalyze_track()

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

        recovered = _recover_legacy_mb_seeds(target_path)
        if recovered:
            return jsonify({"status": "success", "manifest": recovered})

        return jsonify({"status": "success", "manifest": None})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


def _handle_get_taxonomy():

    taxonomy_path = PROJECT_ROOT / "data" / "taxonomy.json"
    try:
        taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        return jsonify({"status": "success", "genres": sorted(taxonomy.keys())})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


def _handle_reanalyze_track():

    import acoustic_engine

    data = request.json
    file_path = (data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({"status": "error", "message": "Missing file_path"}), 400

    f_path = Path(file_path)
    if not f_path.exists():
        return jsonify({"status": "error", "message": "File not found on disk."}), 404

    acoustic_data = acoustic_engine.analyze_file(f_path)
    if not isinstance(acoustic_data, dict):
        acoustic_data = dict(acoustic_data)

    bpm = acoustic_data.get('bpm', 0)
    key_val = acoustic_data.get('key', '??')
    intensity = acoustic_data.get('intensity', 1)
    length = acoustic_data.get('duration', 0)

    db_engine.execute_query(
        "UPDATE tracks SET bpm=?, key_val=?, intensity=?, length=?, last_updated=CURRENT_TIMESTAMP WHERE file_path=?",
        (bpm, key_val, intensity, length, file_path),
        commit=True
    )

    try:
        tag_engine.update_tags(str(f_path), {"bpm": bpm, "key": key_val, "intensity": intensity})
    except Exception as ex:
        print(f"⚠️ Re-analyze tag write failed for {f_path.name}: {ex}")

    return jsonify({"status": "success", "bpm": bpm, "key": key_val, "intensity": intensity})


def _recover_legacy_mb_seeds(target_path):

    mp3_files = sorted(target_path.glob("**/*.mp3"), key=_natural_track_sort_key)
    if not mp3_files:
        return None

    import id_engine
    seeds = id_engine.get_legacy_mb_seeds(mp3_files[0])

    if all(v == "None" for v in seeds.values()):
        return None

    return {
        "mb_artist_id": seeds["mb_artist_id"],
        "mb_album_id": seeds["mb_album_id"],
        "mb_release_group_id": seeds["mb_group_id"],
    }


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
    import year_resolution_engine
    from mb_resolution_engine import MBResolutionEngine

    root_path = Path(data.get('path'))
    artist = data.get('artist')
    album = data.get('album')
    db_write = data.get('db_write', True)
    mb_ids = data.get('mb_ids', {})
    release_year = data.get('release_year', "Unknown")

    forced_parent_genre = (data.get('forced_parent_genre') or '').strip() or None

    mb_track_map_list = data.get('mb_track_map', [])

    mb_track_lookup = {}

    for entry in mb_track_map_list:
        filename = entry.get("filename")
        position = entry.get("position")

        if filename:
            mb_track_lookup[("filename", filename)] = entry

        if position is not None:
            mb_track_lookup[("position", position)] = entry


    mb = MBResolutionEngine()

    release_label = "Unknown"
    release_mbid = mb_ids.get("album", "")

    if release_mbid and release_mbid not in ("None", "Unknown", ""):
        try:
            release_label = mb.get_release_label(release_mbid)
        except Exception:
            release_label = "Unknown"


    group_first_release_date = data.get('mb_release_group_first_date', '')
    group_secondary_types = data.get('mb_release_group_secondary_types', []) or []
    is_compilation = 1 if 'Compilation' in group_secondary_types else 0
    data['is_compilation'] = is_compilation


    year_cache = {}


    mb_personnel_preseed = {}

    yield '<!-- PROGRESS:5:Ingesting Content -->'
    yield f'<h2 class="it-log-entry it-val-gold"><img src="/ui/images/stamp.png" style="height:36px; width:auto; color:var(--mf-gold);" alt=""> Beginning Intelli-Tagging: <span style="color:var(--text-output);">{album}</span></h2>'

    yield from it_context_engine.initialize_audit_pair(root_path, data)

    health_summary = {}

    yield '<!-- PROGRESS:15:Health Check -->'
    yield from health_engine.check_health(root_path, health_summary=health_summary)

    yield '<!-- PROGRESS:25:Scrubbing -->'
    yield from scrub_engine.scrub_tags(root_path)

    yield '<div class="it-log-entry it-val-gold" style="margin-top:25px;"><img src="/ui/images/intelligence.png" style="height:32px; width:auto; margin-bottom:-12px;" alt=""> Intelli-Tagger AI engines determining metadata values...</div>'

    yield '<!-- PROGRESS:35:Preparing Acoustic Analysis -->'

    yield '''
<div id="it-acoustic-wait" class="it-log-entry" role="status" aria-live="polite" style="margin-left:36px; margin-bottom:-10px; color:var(--text-output)">
    ✅ Beginning acoustic analysis of this Album.<br> ⚠️ The first track may take a little longer to appear while initial album identification and forensic tagging get underway...
</div>'''
    yield '<div style="border-top:1px solid var(--mf-gold); margin-top:15px;">&nbsp;</div>'

    files = sorted(list(root_path.glob("**/*.mp3")), key=_natural_track_sort_key)
    total_files = len(files)

    track_results = []
    
    for idx, f_path in enumerate(files, 1):
        progress = int(40 + ((idx / total_files) * 45))
        track_prefix = f'Processing Track {idx}/{total_files}'


        if not f_path.exists():
            yield f'<div class="it-log-entry it-val-red">🔥 MISSING: {f_path.name} was found by the initial scan but is gone from disk. Skipping this track -- investigate immediately, do not re-run this album until the cause is known.</div>'
            continue

        yield f'<!-- PROGRESS:{progress}:{track_prefix} - Analyzing Acoustics -->'

        acoustic_data = acoustic_engine.analyze_file(f_path)

        if not isinstance(acoustic_data, dict):
            acoustic_data = dict(acoustic_data)

        yield f'<!-- PROGRESS:{progress}:{track_prefix} - Determining Genre / Sub Genre, Fingerprinting Track -->'

        fingerprint_data = fingerprint_engine.generate_acoustid(f_path)
        acoustid_value = _extract_acoustid(fingerprint_data)
        acoustid_sibling_ids = fingerprint_data.get("acoustid_recording_ids", [])

        if acoustid_value:
            acoustic_data["acoustid"] = str(acoustid_value)

        filename = f_path.name

        fast_track = mb_track_lookup.get(("filename", filename))

        if not fast_track:
            fast_track = mb_track_lookup.get(("position", idx))

        yield f'<!-- PROGRESS:{progress}:{track_prefix} - Resolving Identity -->'

        if fast_track:

            identity_data = {
                "title": fast_track.get("title", f_path.stem),
                "mb_track_id": fast_track.get("mb_track_id", "None"),
                "mb_recording_id": fast_track.get("mb_recording_id", "None"),
                "mb_work_id": fast_track.get("mb_work_id", "None"),
                "acoustid": acoustic_data.get("acoustid", "None"),
                "original_year": release_year,
                "label": release_label,
                "personnel": [],
                "mb_artist_id": mb_ids.get("artist", "None"),
                "mb_album_id": mb_ids.get("album", "None"),
                "mb_group_id": mb_ids.get("release_group", mb_ids.get("group", "None")),
                # Real per-track performer from the manifest's mb_track_map
                # (populated by musicbrainz_id.py's commit step from MB's own
                # recording-level artist-credit) -- empty for a normal album
                # where every track shares the one artist. See combined["artist"]
                # below, which prefers this over the blanket album-level artist.
                "track_artist": fast_track.get("artist", ""),
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

        yield f'<!-- PROGRESS:{progress}:{track_prefix} - Calculating BPM, Intensity, and Starting Key -->'

        try:
            ai_results = ai_engine.map_track_taxonomy(
                artist,
                title,
                acoustic_data,
                forced_parent_genre=forced_parent_genre
            )

        except Exception:
            ai_results = {
                "parent": "Unknown",
                "sub": "Unknown",
                "mood": "Unknown",
                "sonic_texture": "Unknown",
                "emotional_flavor": "Unknown",
                "country": "Unknown"
            }

        combined = {}
        combined.update(acoustic_data)
        combined.update(identity_data)
        combined.update(ai_results)


        if mb_ids.get("country"):
            combined["country"] = mb_ids["country"]

        yield f'<!-- PROGRESS:{progress}:{track_prefix} - Resolving Original Year -->'

        year_result = year_resolution_engine.resolve_original_year(
            recording_id=combined.get("mb_recording_id"),
            group_id=mb_ids.get("release_group", mb_ids.get("group", "None")),
            group_first_release_date_hint=group_first_release_date,
            artist=artist,
            title=title,
            album=album,
            release_year=release_year,
            track_number=idx,
            total_tracks=total_files,
            is_compilation=is_compilation,
            mb=mb,
            year_cache=year_cache,
            acoustid_recording_ids=acoustid_sibling_ids,
            personnel_preseed=mb_personnel_preseed if db_write else None,
        )
        combined.update(year_result)

        combined["artist"] = combined.get("track_artist") or artist
        combined["release_year"] = release_year

        combined["label"] = release_label

        combined["file_path"] = str(f_path)

        if acoustic_data.get("acoustid"):
            combined["acoustid"] = acoustic_data["acoustid"]

        combined["mb_artist_id"] = mb_ids.get("artist", "None")
        combined["mb_album_id"] = mb_ids.get("album", "None")
        combined["mb_group_id"] = mb_ids.get("release_group", mb_ids.get("group", "None"))

        track_results.append((f_path, combined))

        yield _render_deep_view_line(idx, total_files, f_path.name, combined)


    audit_fn = functools.partial(it_context_engine.update_audit_trail, health_summary=health_summary) if hasattr(it_context_engine, "update_audit_trail") else None

    yield from commit_engine.execute_commit(
        root_path=root_path,
        track_results=track_results,
        db_write=db_write,
        manifest_seeds=data,
        audit_callback=audit_fn
    )


    if db_write:
        _write_personnel_preseed(root_path, mb_personnel_preseed, year_cache.get("discogs_extraartists"))

    yield '<!-- PROGRESS:100:Batch Complete -->'
    yield '<div style="margin-top:15px; border-top:1px solid var(--bg-accent); padding-top:10px;"><img src="/ui/images/complete.svg" alt="" aria-hidden="true" style="width:48px; height:48px; float:left; margin-right:8px; margin-top:5px;"><span style="font-size:1rem; font-weight:bold; margin-bottom:1rem;">Congratulations! You have successfully <span style="color:var(--mf-gold);">Intelli-Tagged</span> your files.</span><br>You are also encouraged to add the optional Personnel data (used by the Intelligent Playlist Maker) and an Artist Bio which will be stored in your database and used as part of the Library Viewer.</div>'

    if db_write:
        yield '<div style="display:none;" id="it-handoff-trigger">HANDOFF_READY</div>'
    yield '<!-- BATCH_COMPLETE -->'


def _write_personnel_preseed(root_path, mb_personnel_preseed, discogs_extraartists):
    """
    Read-modify-write manifest.json (same pattern as musicbrainz_id.py's
    _update_manifest()) to capture two free-riding signals for Personnel
    Engine v2's fast path:
    - mb_artist_rels_by_recording: {recording_id: [raw MB relations]},
      captured from the year waterfall's own per-track Tier-1 MB call
      (widened to inc=artist-rels -- zero extra HTTP cost).
    - discogs_extraartists: {"album": [...], "by_track": {position: [...]}},
      captured from the same Discogs release fetch the year waterfall's
      Tier 3 already makes once per album.
    Both are purely additive to whatever manifest.json already has (MB
    track map, release-group data, etc.) -- never overwrites unrelated
    keys. If Personnel is opened on an album that skipped this step (or
    predates this feature), these keys are simply absent and Personnel
    falls back to fetching fresh itself.
    """

    manifest_path = Path(root_path) / "manifest.json"

    m = {}
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            m = {}

    if mb_personnel_preseed:
        m["mb_artist_rels_by_recording"] = mb_personnel_preseed
    if discogs_extraartists:
        m["discogs_extraartists"] = discogs_extraartists

    try:
        manifest_path.write_text(json.dumps(m, indent=4), encoding="utf-8")
    except Exception as ex:
        print(f"⚠️ Personnel pre-seed manifest write failed: {ex}")


def _render_deep_view_line(idx, total, filename, data):

    idx_str = f"[{str(idx).rjust(len(str(total)))}/{total}]"

    line1 = f'<span class="it-val-gold">{idx_str}</span> <span class="it-val-white">{filename}</span>'

    subline = f'<div style="margin-right:10px; margin-left:-40px!important; text-align:left; margin-top:5px; border-bottom:1px solid var(--mf-gold); padding-bottom:5px; width:100%;">'

    subline += f'| <span class="it-val-gold">Original Date:</span> <span class="it-val-white">{str(data.get("original_year", "Unknown")).ljust(6)}</span> | '
    subline += f'<span class="it-val-gold">Release Date:</span> <span class="it-val-white">{str(data.get("release_year", "Unknown")).ljust(6)}</span> | '
    subline += f'<span class="it-val-gold">Genre:</span> <span class="it-val-white">{data.get("parent", "Unknown")[:13].ljust(13)}</span> | '
    subline += f'<span class="it-val-gold">Sub Genre:</span> <span class="it-val-white">{data.get("sub", "Unknown")[:18].ljust(18)}</span><br>'

    subline += f'| <span class="it-val-gold">BPM:</span> <span class="it-val-white">{str(data.get("bpm", "0")).ljust(3)}</span> | '
    subline += f'<span class="it-val-gold">Key:</span> <span class="it-val-white">{data.get("key", "??").ljust(4)}</span> | '
    subline += f'<span class="it-val-gold">Int.:</span> <span class="it-val-white">{str(data.get("intensity", "1")).ljust(1)}</span> | '
    subline += f'<span class="it-val-gold">Mood:</span> <span class="it-val-white">{data.get("mood", "Unknown")[:12].ljust(12)}</span> | '
    subline += f'<span class="it-val-gold">Sonic Texture:</span> <span class="it-val-white">{data.get("sonic_texture", "Unknown")[:8].ljust(8)}</span> | '
    subline += f'<span class="it-val-gold">Emotional Flavor:</span> <span class="it-val-white">{data.get("emotional_flavor", "Unknown")[:10].ljust(10)}</span><br>'

    subline += f'| <span class="it-val-gold">MB TrackID:</span> <span class="it-val-white">{str(data.get("mb_track_id", "None"))[:37]}</span> | '
    subline += f'<span class="it-val-gold">AcoustID:</span> <span class="it-val-white">{str(data.get("acoustid", "None"))[:37]}</span></div>'

    return f'<div class="it-log-row"><span class="it-log-line1">{line1}</span><span class="it-log-subline">{subline}</span></div>'


# --- END OF FILE intelli-tagger.py ---