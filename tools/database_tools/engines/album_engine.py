# --- START OF FILE album_engine.py ---
# ======================================================================
# MetaForge Studio: Album Engine (Master Record Layer)
# Physical Location: \tools\database_tools\engines\album_engine.py
# Build 1.3.5: relation_type derived from ROLE_MAP (aligned with commit_engine.py)
# ======================================================================
import json
import re
import sys
import hashlib
from datetime import datetime
from flask import jsonify, request
from pathlib import Path
from PIL import Image
from common import db_engine, tag_engine, config_handler
from tools.personnel.edge_normalizer import load_config, classify_role, hash_artist_identity, is_junk_role, is_junk_name, apply_role_alias
from tools.personnel import edge_store
from tools.database_tools.engines import identity_ops

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
    if action == "get_track_detail": return _get_track_detail()
    if action == "save_track_detail": return _save_track_detail()
    return jsonify({"status": "error", "message": "Action unknown"}), 404

def _search_album():
    # Real bug, found live 2026-07-29 (John's report): this used to jump
    # straight into whichever album SQLite returned first for a substring
    # match (no ORDER BY = effectively insertion order) -- silently wrong
    # whenever a title/keyword matched more than one album, with no
    # indication anything had been guessed at all. Now mirrors
    # identity_engine.py's _search_artist_logic pattern: a single
    # unambiguous match still loads directly, but more than one match
    # returns a "multiple" candidate list (alphabetical, both title and
    # artist so same-titled albums by different artists are distinguishable)
    # instead of guessing.
    query = request.args.get('album', '').strip()
    res = db_engine.execute_query(
        "SELECT * FROM library_master WHERE album_title LIKE ? ORDER BY album_title COLLATE NOCASE",
        (f"%{query}%",)
    )
    if not res:
        return jsonify({"status": "error", "message": "Album not found."}), 404

    # Real bug, found live 2026-07-29 (John's report): SQL LIKE '%query%'
    # matches ANYWHERE in the title, including mid-word -- searching "In"
    # matched "Before The Ra-IN", "S-IN-ging", etc. Trailing-space
    # workarounds ("In ") didn't help either since query is already
    # .strip()'d above before it ever reaches the LIKE clause. Re-filtering
    # here with a case-insensitive whole-word regex keeps the cheap SQL
    # LIKE as a fast pre-filter (still needed so this doesn't scan every
    # row in Python) while only keeping rows where the query is actually
    # its own word -- "In" now matches "In Concert" / "Living In America"
    # but not "Rain" or "Singing".
    word_pattern = re.compile(r'\b' + re.escape(query) + r'\b', re.IGNORECASE)
    res = [row for row in res if word_pattern.search(row['album_title'] or '')]
    if not res:
        return jsonify({"status": "error", "message": "Album not found."}), 404

    if len(res) > 1:
        candidates = [
            {"mf_id": row['mf_id'], "album_title": row['album_title'], "artist_name": row['artist_name']}
            for row in res
        ]
        return jsonify({"status": "multiple", "candidates": candidates})

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

    # (v2: an album with no tracks of its own used to show the artist's
    # tracks from OTHER albums here, and saving then edited those.)

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

    combos = db_engine.execute_query(
        "SELECT DISTINCT COALESCE(genre, '') AS genre, COALESCE(sub_genre, '') AS sub_genre FROM tracks WHERE mf_id = ?",
        (clean_mf_id,)
    ) or []
    album['genre_mixed'] = len(combos) > 1
    if len(combos) == 1:
        album['genre'] = combos[0]['genre']
        album['sub_genre'] = combos[0]['sub_genre']

    if 'genre' not in album: album['genre'] = ''
    if 'sub_genre' not in album: album['sub_genre'] = ''

    # The ARTIST's home country (library_artist.country), not any one
    # release's distribution country -- this used to read mb_release_
    # country live off the album folder's manifest.json, which is a
    # different concept entirely (see edge_normalizer/intelli-tagger's
    # 2026-08-01 country pipeline) and had no write path at all in
    # _save_album below, so editing this field here silently did
    # nothing. John's report, 2026-08-05.
    country_code = ""
    if album.get('mf_artist_id'):
        artist_row = db_engine.execute_query(
            "SELECT country FROM library_artist WHERE mf_artist_id = ?", (album['mf_artist_id'],)
        )
        if artist_row and artist_row[0]['country']:
            country_code = artist_row[0]['country']
    album['country'] = country_code

    edges = db_engine.execute_query(
        "SELECT e.id, e.role, e.evidence_detail, a.artist_name as name FROM edges e "
        "JOIN library_artist a ON e.target_id = a.mf_artist_id "
        "WHERE LOWER(TRIM(e.source_id)) = LOWER(TRIM(?)) AND e.source_type = 'album'",
        (clean_mf_id,)
    )
    album['personnel'] = [dict(e) for e in edges] if edges else []

    return jsonify({"status": "success", "album": album})

def _taxonomy():
    path = config_handler.DATA_DIR / "taxonomy.json"
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def _tag(file_path, values, problems):
    """Writes tags, collecting (not raising) failures: never-abort."""
    if not Path(file_path).exists():
        problems.append(f"Tags not written, file not found: {file_path}")
        return
    ok, msg = tag_engine.update_tags(file_path, values)
    if not ok:
        problems.append(f"Tags not written to {file_path}: {msg}")


def _save_album():
    # v2 (2026-11-15, John: "yes to tags, rename carries through"). A new
    # album artist or title re-keys the album (mf_id is a hash of both) via
    # identity_ops, after a preview the user confirms; year and label now
    # reach the TYER/TPUB tags; genre is written only when the user chose
    # one (it used to flatten every track's genre on every save: 873 of
    # 1,364 albums have tracks with different genres).
    data = request.json or {}
    mf_id = str(data.get('mf_id') or '').strip()
    found = db_engine.execute_query("SELECT * FROM library_master WHERE mf_id = ?", (mf_id,))
    if not found:
        return jsonify({"status": "error", "message": "This album is no longer in the database."}), 404
    row = found[0]
    title = (data.get('title') or '').strip()
    artist = (data.get('artist') or '').strip()
    if not title or not artist:
        return jsonify({"status": "error", "message": "The album needs a title and an artist."}), 400

    genre_changed = bool(data.get('genre_changed'))
    genre = (data.get('genre') or '').strip()
    sub_genre = (data.get('sub_genre') or '').strip()
    if genre_changed:
        taxonomy = _taxonomy()
        if genre and taxonomy and genre not in taxonomy:
            return jsonify({"status": "error", "message": f"{genre} isn't in the genre list."}), 400
        if genre and sub_genre and sub_genre not in taxonomy.get(genre, []):
            return jsonify({"status": "error", "message": f"{sub_genre} isn't a sub-genre of {genre}."}), 400

    problems = []
    if title != row['album_title'] or artist != row['artist_name']:
        if not data.get('confirmed'):
            prev = identity_ops.run("album_edit", mf_id=mf_id, artist=artist, title=title)
            return jsonify({"status": "confirm", "summary": prev["summary"], "notes": prev["notes"]})
        res = identity_ops.run("album_edit", apply=True, label=f"album {title}", mf_id=mf_id, artist=artist, title=title)
        mf_id = res["album_ids"].get(mf_id, mf_id)
        problems += res["problems"]

    tracks = data.get('tracks', [])
    personnel = data.get('personnel', [])
    clean_mf_id = mf_id

    old_tracks = db_engine.execute_query(
        "SELECT file_path, title, original_year, mb_recording_id, mf_artist_id FROM tracks WHERE mf_id = ?",
        (clean_mf_id,)
    ) or []
    compilation_row = db_engine.execute_query(
        "SELECT is_compilation FROM library_master WHERE mf_id = ?", (mf_id,)
    )
    # A single-artist album has one artist, the album's; per-track artists
    # exist only on compilations (2026-08-01 "Green Onions" report: tracks
    # used to re-fragment under a second identity on every save).
    is_compilation = bool(compilation_row and compilation_row[0]['is_compilation'])
    old_titles_map = {t['file_path']: t['title'] for t in old_tracks}
    old_years_map = {t['file_path']: t['original_year'] for t in old_tracks}
    old_recording_ids_map = {t['file_path']: t['mb_recording_id'] for t in old_tracks}
    old_artist_map = {t['file_path']: t['mf_artist_id'] for t in old_tracks}

    # Replace the album's folder.jpg with the newly browsed cover, if one
    # was staged. serve_album_cover() (ui/app.py) reads folder.jpg from the
    # album's own folder.
    cover_path = data.get('cover_path')
    if cover_path and old_tracks:
        album_dir = Path(old_tracks[0]['file_path']).parent
        try:
            img = Image.open(cover_path).convert("RGB")
            img.save(str(album_dir / "folder.jpg"), "JPEG", quality=90)
        except Exception as ex:
            problems.append(f"The cover image couldn't be saved: {ex}")

    year = str(data.get('year') or '').strip()
    label = (data.get('label') or '').strip()
    album_tags = {}
    if year != str(row['original_year'] or ''):
        album_tags['year'] = year
    if label != (row['label'] or ''):
        album_tags['label'] = label
    db_engine.execute_query(
        "UPDATE library_master SET original_year=?, label=?, last_updated=CURRENT_TIMESTAMP WHERE mf_id=?",
        (year, label, mf_id), commit=True
    )
    if genre_changed:
        db_engine.execute_query(
            "UPDATE tracks SET genre=?, sub_genre=?, last_updated=CURRENT_TIMESTAMP WHERE mf_id=?",
            (genre, sub_genre, mf_id), commit=True
        )
        album_tags['genre'] = genre
        album_tags['sub_genre'] = sub_genre
    if album_tags:
        for t in old_tracks:
            _tag(t['file_path'], album_tags, problems)

    # Country means the ARTIST's home country (library_artist.country). An
    # empty field means "not reviewed", not "clear it".
    country_val = (data.get('country') or '').strip()
    if country_val:
        db_engine.execute_query(
            "UPDATE library_artist SET country=?, last_updated=CURRENT_TIMESTAMP WHERE mf_artist_id=?",
            (country_val, hash_artist_identity(artist)), commit=True
        )

    for t in tracks:
        f_path_str = t.get('file_path')
        if not f_path_str or f_path_str not in old_titles_map:
            continue
        new_title = (t.get('title') or '').strip()
        track_tags = {}

        track_artist_name = artist if not is_compilation else ((t.get('artist') or '').strip() or artist)
        track_mf_artist_id = hash_artist_identity(track_artist_name)
        if track_mf_artist_id != old_artist_map.get(f_path_str):
            db_engine.execute_query(
                "INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (track_mf_artist_id, track_artist_name), commit=True
            )
            db_engine.execute_query(
                "UPDATE tracks SET mf_artist_id=?, last_updated=CURRENT_TIMESTAMP WHERE file_path=?",
                (track_mf_artist_id, f_path_str), commit=True
            )
            track_tags['artist'] = track_artist_name

        if new_title and old_titles_map[f_path_str] != new_title:
            db_engine.execute_query(
                "UPDATE tracks SET title=?, last_updated=CURRENT_TIMESTAMP WHERE file_path=?",
                (new_title, f_path_str), commit=True
            )
            track_tags['title'] = new_title

        new_year = (t.get('original_year') or '').strip()
        if new_year and str(old_years_map[f_path_str] or '') != new_year:
            db_engine.execute_query(
                "UPDATE tracks SET original_year=?, orig_year_conf=100, "
                "orig_year_source='Manual (User Verified)', leak_flag=0, "
                "last_updated=CURRENT_TIMESTAMP WHERE file_path=?",
                (new_year, f_path_str), commit=True
            )
            track_tags['original_year'] = new_year
            # Only loggable with a real MB recording MBID: without one
            # there's no MusicBrainz page to submit to.
            mb_recording_id = old_recording_ids_map.get(f_path_str)
            if mb_recording_id:
                _log_manual_year_correction(
                    clean_mf_id, f_path_str, artist, title, new_title,
                    mb_recording_id, old_years_map[f_path_str], new_year,
                )
        if track_tags:
            _tag(f_path_str, track_tags, problems)

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
        "SELECT id, target_id, role, evidence_detail FROM edges WHERE LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND source_type='album'",
        (clean_mf_id,)
    )
    existing_by_id = {e['id']: e for e in existing_edges} if existing_edges else {}

    role_config = load_config()
    kept_edge_ids = set()

    for p in personnel:
        if not p.get('name') or not p.get('role'): continue
        role = p['role'].strip()
        edge_id = p.get('id')

        # Same alias rewrite normalize_personnel() applies for every
        # automated source -- "Executive Producer" typed straight into
        # this panel becomes "Producer" here too, not just when it comes
        # in via MB/Discogs/Wikipedia.
        role = apply_role_alias(role, role_config)

        # Real gap, John's report 2026-08-08: this manual-entry path was
        # the ONLY personnel ingestion route in the whole app that never
        # checked the junk-role/junk-name denylist (performance.json) --
        # every automated source (MB/Discogs/Wikipedia/AllMusic) already
        # filters through is_junk_role/is_junk_name via normalize_personnel()
        # or a direct call, but typing "Engineer" or "Photography" straight
        # into the Album Editor's Personnel panel sailed right through.
        # `continue` here does double duty: a NEW junk row is never
        # created, and an EXISTING edge that's junk under today's denylist
        # (e.g. saved before a term was added) is naturally cleaned up too,
        # since skipping it means it's never added to kept_edge_ids below --
        # the existing removed-edge cleanup deletes it, same as if the user
        # had clicked the row's own "x" button.
        if is_junk_role(role, role_config) or is_junk_name(p['name'], role_config):
            continue

        tid = hash_artist_identity(p['name'])

        # Dedicated Track(s) field -- real bug, John's report 2026-08-01:
        # the only way to scope a manual credit to specific tracks used to
        # be typing "(1, 2, 3)" into the Name field itself, which the
        # manual-entry path never parsed (unlike normalize_personnel()'s
        # automated path) -- it just became part of the artist's name,
        # splintering "Emory Smith" into a bogus separate identity
        # "Emory Smith (1, 2, 3, 4, 6, 7, 9)". This field is the real
        # mechanism: track_scope stays out of the name entirely and maps
        # straight to evidence_scope/evidence_detail, same as an automated
        # import's parenthetical qualifier already does.
        track_scope = (p.get('track_scope') or '').strip()
        evidence_scope = 'track' if track_scope else None
        evidence_detail = track_scope if track_scope else None

        db_engine.execute_query(
            "INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (tid, p['name']),
            commit=True
        )

        existing = existing_by_id.get(edge_id) if edge_id else None

        if existing:
            kept_edge_ids.add(edge_id)
            # Unchanged row -- leave it, and its original provenance/
            # confidence, completely untouched.
            if existing['target_id'] == tid and existing['role'] == role and (existing['evidence_detail'] or None) == evidence_detail:
                continue
            relation_type, confidence = classify_role(role, role_config)
            edge_store.update_edge_by_id(
                edge_id, target_id=tid, relation_type=relation_type,
                role=role, confidence=confidence, provenance="MetaForge (Manual)",
                evidence_scope=evidence_scope, evidence_detail=evidence_detail
            )
        else:
            # New row added in the UI -- upsert (not a blind insert), so a
            # manually-typed credit that happens to match one MB/Discogs
            # already resolved merges into it instead of duplicating.
            relation_type, confidence = classify_role(role, role_config)
            edge_store.upsert_edge(
                source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
                relation_type=relation_type, role=role,
                confidence=confidence, provenance="MetaForge (Manual)",
                evidence_scope=evidence_scope, evidence_detail=evidence_detail
            )

    # Rows that existed before but weren't in this submission were removed
    # by the user (the "x" button) -- delete exactly those, nothing else.
    removed_edge_ids = set(existing_by_id) - kept_edge_ids
    removed_artist_ids = set()
    for eid in removed_edge_ids:
        removed_artist_ids.add(existing_by_id[eid]['target_id'])
        edge_store.delete_edge(eid)

    for r_id in removed_artist_ids:
        # Real bug, John's report 2026-08-07 (the "Barbra Streisand"
        # case): this used to check only edges before deleting the
        # identity outright, so removing someone's PERSONNEL credit (the
        # "x" button) could silently delete their library_artist row even
        # while a track's own per-track artist field (tracks.mf_artist_id)
        # still pointed at that exact same identity -- orphaning the
        # track and making the artist unsearchable, with no error or
        # warning anywhere. An identity is only truly unused, and safe to
        # delete, when nothing in edges OR tracks OR library_master
        # references it anymore.
        still_used = (
            db_engine.execute_query("SELECT 1 FROM edges WHERE target_id=? LIMIT 1", (r_id,))
            or db_engine.execute_query("SELECT 1 FROM tracks WHERE mf_artist_id=? LIMIT 1", (r_id,))
            or db_engine.execute_query("SELECT 1 FROM library_master WHERE mf_artist_id=? LIMIT 1", (r_id,))
        )
        if not still_used:
            db_engine.execute_query("DELETE FROM library_artist WHERE mf_artist_id=?", (r_id,), commit=True)

    return jsonify({"status": "success", "mf_id": mf_id, "problems": problems})


# =========================================================
# TRACK-LEVEL DETAIL (fine-grained edit modal, 2026-07-17)
# =========================================================
# Everything the Album Editor's own track table couldn't expose (Title/
# Artist/Original Year already have their own inline fields) -- Genre/
# Sub-Genre/Mood/Sonic Texture/Emotional Flavor, the measured BPM/Key/
# Intensity trio, and the forensic MB/AcoustID identifiers. Deliberately
# excludes Personnel (has its own tool, Personnel Scout) and internal
# bookkeeping columns (file_path, is_remediated, last_updated, leak_flag,
# length) that aren't user data.

def _get_track_detail():
    file_path = (request.args.get('file_path') or '').strip()
    if not file_path:
        return jsonify({"status": "error", "message": "Missing file_path"}), 400

    res = db_engine.execute_query("SELECT * FROM tracks WHERE file_path = ?", (file_path,))
    if not res:
        return jsonify({"status": "error", "message": "Track not found."}), 404

    return jsonify({"status": "success", "track": dict(res[0])})


def _save_track_detail():
    data = request.json
    file_path = (data.get('file_path') or '').strip()
    if not file_path:
        return jsonify({"status": "error", "message": "Missing file_path"}), 400

    # Closed-vocabulary enforcement -- same lesson already applied in
    # ai_engine.py: a dropdown in the UI is not enforcement on its own,
    # since this is a real write path a stale client could bypass. Checked
    # server-side against the same taxonomy.json/moods.json files
    # map_track_taxonomy() validates against.
    taxonomy_path = config_handler.DATA_DIR / "taxonomy.json"
    moods_path = config_handler.DATA_DIR / "moods.json"
    taxonomy_data = json.loads(taxonomy_path.read_text(encoding='utf-8')) if taxonomy_path.exists() else {}
    moods_data = json.loads(moods_path.read_text(encoding='utf-8')) if moods_path.exists() else {}

    valid_moods = set(moods_data.get("anchors", []))
    valid_textures = set(moods_data.get("modifiers", {}).get("Sonic_Texture", []))
    valid_flavors = set(moods_data.get("modifiers", {}).get("Emotional_Flavor", []))

    genre = (data.get('genre') or '').strip()
    sub_genre = (data.get('sub_genre') or '').strip()
    mood = (data.get('mood') or '').strip()
    sonic_texture = (data.get('sonic_texture') or '').strip()
    emotional_flavor = (data.get('emotional_flavor') or '').strip()

    if genre and taxonomy_data and genre not in taxonomy_data:
        return jsonify({"status": "error", "message": f"Genre {genre!r} not in taxonomy."}), 400
    if genre and sub_genre and sub_genre not in taxonomy_data.get(genre, []):
        return jsonify({"status": "error", "message": f"Sub-Genre {sub_genre!r} not valid under {genre!r}."}), 400
    if mood and valid_moods and mood not in valid_moods:
        return jsonify({"status": "error", "message": f"Mood {mood!r} outside the fixed anchor list."}), 400
    if sonic_texture and valid_textures and sonic_texture not in valid_textures:
        return jsonify({"status": "error", "message": f"Sonic Texture {sonic_texture!r} outside the fixed list."}), 400
    if emotional_flavor and valid_flavors and emotional_flavor not in valid_flavors:
        return jsonify({"status": "error", "message": f"Emotional Flavor {emotional_flavor!r} outside the fixed list."}), 400

    def _num(key, label):
        raw = str(data.get(key) if data.get(key) is not None else '').strip()
        if not raw:
            return None, None          # blank stays blank (v2: was saved as 0)
        try:
            return int(float(raw)), None
        except ValueError:
            return None, f"{label} must be a number."

    bpm, err = _num('bpm', 'BPM')
    if err:
        return jsonify({"status": "error", "message": err}), 400
    intensity, err = _num('intensity', 'Intensity')
    if err:
        return jsonify({"status": "error", "message": err}), 400

    key_val = (data.get('key') or '').strip()
    mb_track_id = (data.get('mb_track_id') or '').strip()
    mb_recording_id = (data.get('mb_recording_id') or '').strip()
    mb_work_id = (data.get('mb_work_id') or '').strip()
    mb_artist_id = (data.get('mb_artist_id') or '').strip()
    acoustid = (data.get('acoustid') or '').strip()

    db_engine.execute_query(
        """UPDATE tracks SET
            genre=?, sub_genre=?, mood=?, sonic_texture=?, emotional_flavor=?,
            bpm=?, key_val=?, intensity=?,
            mb_track_id=?, mb_recording_id=?, mb_work_id=?, mb_artist_id=?, acoustid=?,
            last_updated=CURRENT_TIMESTAMP
        WHERE file_path=?""",
        (
            genre, sub_genre, mood, sonic_texture, emotional_flavor,
            bpm, key_val, intensity,
            mb_track_id, mb_recording_id, mb_work_id, mb_artist_id, acoustid,
            file_path
        ),
        commit=True
    )

    p_file = Path(file_path)
    if p_file.exists():
        values = {
            "genre": genre, "sub_genre": sub_genre, "mood": mood,
            "sonic_texture": sonic_texture, "emotional_flavor": emotional_flavor,
            "bpm": bpm, "key": key_val, "intensity": intensity,
            "mb_track_id": mb_track_id, "mb_recording_id": mb_recording_id,
            "mb_artist_id": mb_artist_id, "acoustid": acoustid,
        }
        ok, msg = tag_engine.update_tags(str(p_file), {k: v for k, v in values.items() if v is not None})
        if not ok:
            return jsonify({"status": "success", "problems": [f"Saved, but the file's tags weren't written: {msg}"]})
    else:
        return jsonify({"status": "success", "problems": ["Saved, but the music file wasn't found, so its tags weren't written."]})

    return jsonify({"status": "success", "problems": []})

# --- END OF FILE album_engine.py ---