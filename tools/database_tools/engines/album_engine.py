# --- START OF FILE album_engine.py ---
# ======================================================================
# MetaForge Studio: Album Engine (Master Record Layer)
# Physical Location: \tools\database_tools\engines\album_engine.py
# Build 1.3.5: relation_type derived from ROLE_MAP (aligned with commit_engine.py)
# ======================================================================
import json
import sys
import hashlib
from datetime import datetime
from flask import jsonify, request
from pathlib import Path
from PIL import Image
from common import db_engine, tag_engine, config_handler
from tools.personnel.edge_normalizer import load_config, classify_role
from tools.personnel import edge_store

# Same evidence-collection log commit_engine.py's automatic waterfall
# already writes to (data/musicbrainz/original_year_correction_candidates.jsonl)
# -- a manual "Original Year" edit here is a SEPARATE code path from that
# waterfall (confirmed 2026-07-09: this UPDATE was writing
# orig_year_conf=100/orig_year_source='Manual (User Verified)' straight to
# the DB with no logging at all, meaning John's own verified corrections
# -- arguably the highest-confidence source of all -- were invisible to
# the MB Submit tool). Logging here too, not importing commit_engine.py's
# private helper (that module only sits on sys.path while Intelli-Tagger's
# own run_logic() is executing) -- same small-local-helper pattern already
# used by tools/personnel/personnel.py for its own correction log.
YEAR_CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "original_year_correction_candidates.jsonl"


def _log_manual_year_correction(mf_id, file_path, artist, album, title,
                                 mb_recording_id, current_release_year, proposed_original_year):
    """Appends one JSONL entry to YEAR_CANDIDATE_LOG, same schema
    commit_engine.py's automatic waterfall writes -- musicbrainz_submit.py's
    existing dedup-by-latest-timestamp logic picks this up for free, so a
    manual correction automatically supersedes an older programmatic guess
    for the same recording with zero changes needed on the consuming side.
    Never raises -- a logging failure must never break a real album save."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "mf_id": mf_id, "file_path": file_path,
        "artist": artist, "album": album, "title": title,
        "mb_recording_id": mb_recording_id,
        "current_release_year": current_release_year,
        "proposed_original_year": proposed_original_year,
        "orig_year_conf": 100, "orig_year_source": "Manual (User Verified)",
        "evidence": None,
    }
    try:
        YEAR_CANDIDATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(YEAR_CANDIDATE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as ex:
        print(f"⚠️ Manual year correction candidate log write failed: {ex}")

def handle(action):
    if action == "search_album": return _search_album()
    if action == "get_album_details": return _get_album_details()
    if action == "save_album": return _save_album()
    return jsonify({"status": "error", "message": "Action unknown"}), 404

def _search_album():
    query = request.args.get('album', '').strip()
    res = db_engine.execute_query(
        "SELECT * FROM library_master WHERE album_title LIKE ?",
        (f"%{query}%",)
    )
    if not res:
        return jsonify({"status": "error", "message": "Album not found."}), 404
    return _get_album_details_by_id(res[0]['mf_id'])

def _get_album_details():
    mf_id = request.args.get('mf_id')
    return _get_album_details_by_id(mf_id)

def _get_album_details_by_id(mf_id):
    if not mf_id:
        return jsonify({"status": "error", "message": "Missing required mf_id property."}), 400

    res = db_engine.execute_query("SELECT * FROM library_master WHERE mf_id = ?", (mf_id,))
    if not res:
        return jsonify({"status": "error", "message": "ID not found."}), 404

    album = dict(res[0])
    album['last_updated'] = album.get('last_updated', 'MM-DD-YYYY')

    clean_mf_id = str(mf_id).strip()

    tracks = db_engine.execute_query(
        "SELECT * FROM tracks WHERE LOWER(TRIM(mf_id)) = LOWER(TRIM(?)) ORDER BY file_path ASC",
        (clean_mf_id,)
    )

    if not tracks and album.get('mf_artist_id'):
        clean_artist_id = str(album['mf_artist_id']).strip()
        tracks = db_engine.execute_query(
            "SELECT * FROM tracks WHERE LOWER(TRIM(mf_artist_id)) = LOWER(TRIM(?)) ORDER BY file_path ASC",
            (clean_artist_id,)
        )

    # Real bug found live 2026-07-17: every track's displayed "artist" was
    # hardcoded to the ALBUM-level library_master.artist_name below, which
    # is correct for a normal single-artist album but wrong for a Various
    # Artists compilation, where every track has its own real performer
    # (tracks.mf_artist_id, populated per-track by commit_engine.py). One
    # batch lookup here, not N+1 -- resolves each track's own artist name,
    # falling back to the album-level name only if a track somehow has no
    # library_artist row of its own.
    distinct_artist_ids = {dict(t).get('mf_artist_id') for t in tracks} if tracks else set()
    distinct_artist_ids.discard(None)
    distinct_artist_ids.discard('')

    track_artist_names = {}
    if distinct_artist_ids:
        placeholders = ','.join('?' for _ in distinct_artist_ids)
        artist_rows = db_engine.execute_query(
            f"SELECT mf_artist_id, artist_name FROM library_artist WHERE mf_artist_id IN ({placeholders})",
            tuple(distinct_artist_ids)
        )
        track_artist_names = {r['mf_artist_id']: r['artist_name'] for r in artist_rows} if artist_rows else {}

    album['tracks'] = []
    if tracks:
        for t in tracks:
            track_dict = dict(t)

            raw_title = track_dict.get('title') or track_dict.get('track_title') or track_dict.get('name') or ""
            db_title = str(raw_title).strip()

            display_title = db_title if db_title else (Path(track_dict['file_path']).parent.stem if track_dict.get('file_path') else "Unknown Track")
            if not db_title and track_dict.get('file_path'):
                display_title = Path(track_dict['file_path']).stem

            track_artist = track_artist_names.get(track_dict.get('mf_artist_id')) or album.get('artist_name', '')

            album['tracks'].append({
                "file_path": track_dict.get('file_path', ''),
                "title": display_title,
                "artist": track_artist,
                "original_year": track_dict.get('original_year', ''),
                "orig_year_conf": track_dict.get('orig_year_conf', 0),
                "orig_year_source": track_dict.get('orig_year_source', '')
            })

    if album['tracks']:
        meta_probe = db_engine.execute_query(
            "SELECT genre, sub_genre FROM tracks WHERE LOWER(TRIM(mf_id)) = LOWER(TRIM(?)) AND genre IS NOT NULL LIMIT 1",
            (clean_mf_id,)
        )
        if meta_probe:
            album['genre'] = meta_probe[0]['genre']
            album['sub_genre'] = meta_probe[0]['sub_genre']

    if 'genre' not in album: album['genre'] = ''
    if 'sub_genre' not in album: album['sub_genre'] = ''

    country_code = ""
    if album['tracks']:
        for t in album['tracks']:
            if t.get('file_path'):
                try:
                    track_dir = Path(t['file_path']).parent
                    manifest_path = track_dir / "manifest.json"
                    if manifest_path.exists():
                        m_data = json.loads(manifest_path.read_text(encoding='utf-8'))
                        country_code = m_data.get('mb_release_country', '').strip()
                        if country_code:
                            break
                except Exception:
                    pass
    album['country'] = country_code

    edges = db_engine.execute_query(
        "SELECT e.id, e.role, a.artist_name as name FROM edges e "
        "JOIN library_artist a ON e.target_id = a.mf_artist_id "
        "WHERE LOWER(TRIM(e.source_id)) = LOWER(TRIM(?)) AND e.source_type = 'album'",
        (clean_mf_id,)
    )
    album['personnel'] = [dict(e) for e in edges] if edges else []

    return jsonify({"status": "success", "album": album})

def _save_album():
    data = request.json
    mf_id = data['mf_id']
    tracks = data.get('tracks', [])
    personnel = data.get('personnel', [])

    clean_mf_id = str(mf_id).strip()

    old_tracks = db_engine.execute_query(
        "SELECT file_path, title, original_year, mb_recording_id FROM tracks WHERE LOWER(TRIM(mf_id)) = LOWER(TRIM(?))",
        (clean_mf_id,)
    )
    old_titles_map = {t['file_path']: t['title'] for t in old_tracks} if old_tracks else {}
    old_years_map = {t['file_path']: t['original_year'] for t in old_tracks} if old_tracks else {}
    old_recording_ids_map = {t['file_path']: t['mb_recording_id'] for t in old_tracks} if old_tracks else {}

    # Replace the album's folder.jpg with the newly browsed cover, if one
    # was staged. serve_album_cover() (ui/app.py) always reads folder.jpg
    # from the album's own directory, not a dedicated covers folder.
    cover_path = data.get('cover_path')
    if cover_path and old_tracks:
        album_dir = Path(old_tracks[0]['file_path']).parent
        try:
            img = Image.open(cover_path).convert("RGB")
            img.save(str(album_dir / "folder.jpg"), "JPEG", quality=90)
        except Exception as ex:
            print(f"⚠️ Cover image save failed: {ex}")

    db_engine.execute_query(
        "UPDATE library_master SET album_title=?, artist_name=?, original_year=?, label=?, last_updated=CURRENT_TIMESTAMP WHERE mf_id=?",
        (data['title'], data['artist'], data['year'], data['label'], mf_id),
        commit=True
    )

    for t in tracks:
        f_path_str = t.get('file_path')
        if not f_path_str: continue

        new_title = t['title'].strip()

        # Real bug found live 2026-07-17: the per-track "artist" field the
        # UI already collects (album_editor.js's .track-artist input) was
        # never actually persisted -- this UPDATE didn't touch it at all,
        # so editing a track's artist silently did nothing. Same identity
        # hash convention as commit_engine.py's _hash_artist() and this
        # file's own personnel-edge sync just below. Falls back to the
        # album's own artist when a track's field was left blank.
        track_artist_name = (t.get('artist') or data['artist']).strip()
        track_mf_artist_id = hashlib.sha256(track_artist_name.lower().encode('utf-8')).hexdigest()

        db_engine.execute_query(
            "INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (track_mf_artist_id, track_artist_name),
            commit=True
        )

        db_engine.execute_query(
            "UPDATE tracks SET title=?, genre=?, sub_genre=?, mf_artist_id=?, last_updated=CURRENT_TIMESTAMP WHERE file_path=? AND LOWER(TRIM(mf_id))=LOWER(TRIM(?))",
            (new_title, data['genre'], data['sub_genre'], track_mf_artist_id, f_path_str, clean_mf_id),
            commit=True
        )

        p_file = Path(f_path_str)
        if p_file.exists():
            if f_path_str not in old_titles_map or old_titles_map[f_path_str] != new_title:
                try:
                    tag_engine.update_tags(str(p_file), {"title": new_title})
                except Exception as ex:
                    print(f"⚠️ Centralized tag_engine update_tags failed for {p_file.name}: {ex}")

        new_year = (t.get('original_year') or '').strip()
        if new_year and f_path_str in old_years_map and str(old_years_map[f_path_str]) != new_year:
            db_engine.execute_query(
                "UPDATE tracks SET original_year=?, orig_year_conf=100, "
                "orig_year_source='Manual (User Verified)', leak_flag=0, "
                "last_updated=CURRENT_TIMESTAMP WHERE file_path=? AND LOWER(TRIM(mf_id))=LOWER(TRIM(?))",
                (new_year, f_path_str, clean_mf_id),
                commit=True
            )
            if p_file.exists():
                try:
                    tag_engine.update_tags(str(p_file), {"original_year": new_year})
                except Exception as ex:
                    print(f"⚠️ original_year tag update failed for {p_file.name}: {ex}")

            # Only loggable if this track has a real MB recording MBID --
            # without one there's no MusicBrainz page for a future
            # submission to target anyway.
            mb_recording_id = old_recording_ids_map.get(f_path_str)
            if mb_recording_id:
                _log_manual_year_correction(
                    clean_mf_id, f_path_str, data['artist'], data['title'], new_title,
                    mb_recording_id, old_years_map[f_path_str], new_year,
                )

    # Personnel sync -- targeted per-row update/insert/delete, NOT a blanket
    # delete-all-then-reinsert-all. The old approach wiped every edge for
    # the album on every save (even an unrelated cover-art fix), relabeling
    # every row's provenance to "MetaForge" and losing confidence/
    # evidence_scope/evidence_detail regardless of source -- it also
    # bypassed edge_normalizer's classify_role() in favor of a separate,
    # narrower ROLE_MAP. Only rows the user actually added, edited, or
    # removed in the UI are touched now; everything else (e.g. MB/Discogs-
    # sourced edges the user never looked at) is left completely alone.
    existing_edges = db_engine.execute_query(
        "SELECT id, target_id, role FROM edges WHERE LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND source_type='album'",
        (clean_mf_id,)
    )
    existing_by_id = {e['id']: e for e in existing_edges} if existing_edges else {}

    role_config = load_config()
    kept_edge_ids = set()

    for p in personnel:
        if not p.get('name') or not p.get('role'): continue
        role = p['role'].strip()
        edge_id = p.get('id')
        tid = hashlib.sha256(p['name'].lower().encode('utf-8')).hexdigest()

        db_engine.execute_query(
            "INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (tid, p['name']),
            commit=True
        )

        existing = existing_by_id.get(edge_id) if edge_id else None

        if existing:
            kept_edge_ids.add(edge_id)
            # Unchanged row -- leave it, and its original provenance/
            # confidence/evidence_scope, completely untouched.
            if existing['target_id'] == tid and existing['role'] == role:
                continue
            relation_type, confidence = classify_role(role, role_config)
            edge_store.update_edge_by_id(
                edge_id, target_id=tid, relation_type=relation_type,
                role=role, confidence=confidence, provenance="MetaForge (Manual)"
            )
        else:
            # New row added in the UI -- upsert (not a blind insert), so a
            # manually-typed credit that happens to match one MB/Discogs
            # already resolved merges into it instead of duplicating.
            relation_type, confidence = classify_role(role, role_config)
            edge_store.upsert_edge(
                source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
                relation_type=relation_type, role=role,
                confidence=confidence, provenance="MetaForge (Manual)"
            )

    # Rows that existed before but weren't in this submission were removed
    # by the user (the "x" button) -- delete exactly those, nothing else.
    removed_edge_ids = set(existing_by_id) - kept_edge_ids
    removed_artist_ids = set()
    for eid in removed_edge_ids:
        removed_artist_ids.add(existing_by_id[eid]['target_id'])
        edge_store.delete_edge(eid)

    for r_id in removed_artist_ids:
        remainder = db_engine.execute_query("SELECT 1 FROM edges WHERE target_id=? LIMIT 1", (r_id,))
        if not remainder:
            db_engine.execute_query("DELETE FROM library_artist WHERE mf_artist_id=?", (r_id,), commit=True)

    return jsonify({"status": "success"})

# --- END OF FILE album_engine.py ---