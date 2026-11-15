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
from common.mf_events import event, signal, run_stream   # v2 event stream (Phase 0.3)
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
        # v2: one event stream -> the screen's Activity log (MFEvents) AND
        # the album's MetaForge.log (common/mf_events.run_stream).
        return Response(
            stream_with_context(run_stream(_orchestrate_tagger_batch(data, env_path),
                                           "Intelli-Tagger", log_root=data.get('path'))),
            mimetype='application/x-ndjson'
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

    yield signal("progress", percent=5, label="Reading the album")
    yield event("info", f"Starting: {artist} - {album}", file=str(root_path))

    yield from it_context_engine.initialize_audit_pair(root_path, data)

    health_summary = {}

    yield signal("progress", percent=15, label="Health check")
    yield from health_engine.check_health(root_path, health_summary=health_summary)

    yield signal("progress", percent=25, label="Scrubbing old metadata")
    yield from scrub_engine.scrub_tags(root_path)

    yield event("step", "Step 3: Analysing each track (acoustics, identity, genre, original year)")
    yield signal("progress", percent=35, label="Preparing the acoustic analysis")
    yield event("info", "The first track can take a little longer while the album is identified")

    files = sorted(list(root_path.glob("**/*.mp3")), key=_natural_track_sort_key)
    total_files = len(files)

    track_results = []
    missing_count = 0
    
    for idx, f_path in enumerate(files, 1):
        progress = int(40 + ((idx / total_files) * 45))
        track_prefix = f'Track {idx} of {total_files}'


        if not f_path.exists():
            missing_count += 1
            yield event("error", "File went missing after the first scan. Skipped: investigate before re-running this album", file=f_path.name)
            continue

        yield signal("progress", percent=progress, label=f"{track_prefix}: analysing the acoustics")

        acoustic_data = acoustic_engine.analyze_file(f_path)

        if not isinstance(acoustic_data, dict):
            acoustic_data = dict(acoustic_data)

        yield signal("progress", percent=progress, label=f"{track_prefix}: fingerprinting")

        fingerprint_data = fingerprint_engine.generate_acoustid(f_path)
        acoustid_value = _extract_acoustid(fingerprint_data)
        acoustid_sibling_ids = fingerprint_data.get("acoustid_recording_ids", [])

        if acoustid_value:
            acoustic_data["acoustid"] = str(acoustid_value)

        filename = f_path.name

        fast_track = mb_track_lookup.get(("filename", filename))

        if not fast_track:
            fast_track = mb_track_lookup.get(("position", idx))

        yield signal("progress", percent=progress, label=f"{track_prefix}: identifying the recording")

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


        else:
            identity_data = id_engine.get_identity(
                f_path,
                artist,
                acoustic_data.get('duration', 0),
                mb_ids,
                track_map=mb_track_map_list
            )

        title = identity_data.get("title", f_path.stem)

        yield signal("progress", percent=progress, label=f"{track_prefix}: genre, mood, BPM, key and intensity")

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

        yield signal("progress", percent=progress, label=f"{track_prefix}: finding the original year")

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

        yield _track_event(idx, total_files, f_path.name, combined)


    audit_fn = functools.partial(it_context_engine.update_audit_trail, health_summary=health_summary,
                                 inside_run=True) if hasattr(it_context_engine, "update_audit_trail") else None

    yield signal("progress", percent=90, label="Writing the tags")
    # The MetaForge.log SUMMARY is written by this controller at the very
    # end (below), not by the commit engine mid-run, so the log reads in
    # order: events, then SUMMARY, then the run's "Finished" footer.
    commit = yield from commit_engine.execute_commit(
        root_path=root_path,
        track_results=track_results,
        db_write=db_write,
        manifest_seeds=data,
        audit_callback=None
    )


    commit = commit or {}
    if commit.get("db_ok"):
        _write_personnel_preseed(root_path, mb_personnel_preseed, year_cache.get("discogs_extraartists"))

    yield signal("progress", percent=100, label="Finished")

    # v2: the next steps are only offered after a CLEAN run: every track
    # tagged, nothing went missing, and (when it was switched on) the
    # database was written. 1.x showed "Congratulations" and the Personnel
    # hand-off regardless, even after a database error.
    problems = missing_count + commit.get("failed", 0)
    tagged = commit.get("tagged", 0)
    if problems:
        yield event("warning", f"{problems} track{'s were' if problems != 1 else ' was'}n't fully tagged (listed above in red). "
                               f"Fix {'those' if problems != 1 else 'it'}, then run Intelli-Tagger again")
    elif db_write and not commit.get("db_ok"):
        yield event("warning", "The tags were written, but the MetaForge database wasn't (see the red line above). "
                               "Album Personnel and Bio Builder need the database, so run Intelli-Tagger again once it's fixed")
    else:
        yield event("done", f"{tagged} track{'s' if tagged != 1 else ''} Intelli-Tagged")
        if db_write:
            yield signal("handoff_ready")
        else:
            yield event("info", "Writing to the MetaForge database was switched off, so Album Personnel and Bio Builder "
                                "aren't offered (they read from the database)")

    if callable(audit_fn) and track_results:
        primary = track_results[0][1]
        try:
            audit_fn(root_path=root_path, manifest_seeds=data, track_results=track_results,
                     label=primary.get('label', 'Unknown'), personnel=primary.get('personnel', []),
                     db_write=bool(commit.get("db_ok")), release_year=release_year)
        except Exception as ex:
            yield event("warning", f"The MetaForge.log summary couldn't be written: {ex}")
    yield signal("batch_complete")


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


def _track_event(idx, total, filename, data):
    """
    One "track" event per file (John, 2026-11-13: per-track entries, file
    name as the headline, nothing cut short, IDs kept on screen). The
    screen draws `details` as three labelled lines; `text` carries the same
    values in one line for MetaForge.log. 1.x truncated genre (13 chars),
    sonic texture (8), emotional flavour (10) etc. to fit a space-padded
    monospace grid.
    """
    def val(key, default="Unknown"):
        v = data.get(key, default)
        v = default if v in (None, "", "None") else v
        return str(v)

    # Line layout (John, 2026-11-15): years / genre / acoustic + AI
    # attributes / MusicBrainz track ID / AcoustID, each on its own line.
    details = [
        [["Original year", val("original_year")], ["Release year", val("release_year")]],
        [["Genre", val("parent")], ["Sub-genre", val("sub")]],
        [["BPM", val("bpm", "0")], ["Key", val("key", "??")], ["Intensity", val("intensity", "1")],
         ["Mood", val("mood")], ["Sonic texture", val("sonic_texture")],
         ["Emotional flavour", val("emotional_flavor")]],
        [["MusicBrainz track ID", val("mb_track_id", "None")]],
        [["AcoustID", val("acoustid", "None")]],
    ]
    text = "; ".join(f"{k} {v}" for line in details for k, v in line)
    return event("track", text, file=filename, details=details, position=f"{idx} of {total}")


# --- END OF FILE intelli-tagger.py ---