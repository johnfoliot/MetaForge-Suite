# --- START OF FILE album_engine.py ---
# ======================================================================
# MetaForge Studio: Album Engine (Master Record Layer)
# Physical Location: \tools\database_tools\engines\album_engine.py
# Build 1.3.5: relation_type derived from ROLE_MAP (aligned with commit_engine.py)
# ======================================================================
import json
import sys
import hashlib
from flask import jsonify, request
from pathlib import Path
from common import db_engine, tag_engine

# --- [ RELATIONSHIP MAP ] ---
# Mirrors commit_engine.py ROLE_MAP exactly — must remain in sync
ROLE_MAP = {
    "Engineer": "engineered",
    "Producer": "produced",
    "Composer": "composed",
    "Writer": "composed",
    "Lyricist": "composed",
    "Mixer": "mixed",
    "Mastering": "mastered",
    "Vocal": "performed",
    "Instrument": "performed",
    "Musician": "performed",
    "Performer": "performed",
    "Conductor": "conducted"
}

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

    album['tracks'] = []
    if tracks:
        for t in tracks:
            track_dict = dict(t)

            raw_title = track_dict.get('title') or track_dict.get('track_title') or track_dict.get('name') or ""
            db_title = str(raw_title).strip()

            display_title = db_title if db_title else (Path(track_dict['file_path']).parent.stem if track_dict.get('file_path') else "Unknown Track")
            if not db_title and track_dict.get('file_path'):
                display_title = Path(track_dict['file_path']).stem

            album['tracks'].append({
                "file_path": track_dict.get('file_path', ''),
                "title": display_title,
                "artist": album.get('artist_name', '')
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
        "SELECT e.role, a.artist_name as name FROM edges e "
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
        "SELECT file_path, title FROM tracks WHERE LOWER(TRIM(mf_id)) = LOWER(TRIM(?))",
        (clean_mf_id,)
    )
    old_titles_map = {t['file_path']: t['title'] for t in old_tracks} if old_tracks else {}

    db_engine.execute_query(
        "UPDATE library_master SET album_title=?, artist_name=?, original_year=?, label=?, last_updated=CURRENT_TIMESTAMP WHERE mf_id=?",
        (data['title'], data['artist'], data['year'], data['label'], mf_id),
        commit=True
    )

    for t in tracks:
        f_path_str = t.get('file_path')
        if not f_path_str: continue

        new_title = t['title'].strip()

        db_engine.execute_query(
            "UPDATE tracks SET title=?, genre=?, sub_genre=?, last_updated=CURRENT_TIMESTAMP WHERE file_path=? AND LOWER(TRIM(mf_id))=LOWER(TRIM(?))",
            (new_title, data['genre'], data['sub_genre'], f_path_str, clean_mf_id),
            commit=True
        )

        p_file = Path(f_path_str)
        if p_file.exists():
            if f_path_str not in old_titles_map or old_titles_map[f_path_str] != new_title:
                try:
                    tag_engine.update_tags(str(p_file), {"title": new_title})
                except Exception as ex:
                    print(f"⚠️ Centralized tag_engine update_tags failed for {p_file.name}: {ex}")

    current_edges = db_engine.execute_query(
        "SELECT target_id FROM edges WHERE LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND source_type='album'",
        (clean_mf_id,)
    )
    old_artist_ids = set(e['target_id'] for e in current_edges) if current_edges else set()

    db_engine.execute_query(
        "DELETE FROM edges WHERE LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND source_type='album'",
        (clean_mf_id,),
        commit=True
    )

    active_artist_ids = set()
    for p in personnel:
        if not p.get('name') or not p.get('role'): continue
        role = p['role'].strip()
        tid = hashlib.sha256(p['name'].lower().encode('utf-8')).hexdigest()
        active_artist_ids.add(tid)

        # Derive relation_type from ROLE_MAP — mirrors commit_engine.py exactly
        relation = ROLE_MAP.get(role, "contributed")
        if "Vocal" in role: relation = "performed"
        if "Instrument" in role: relation = "performed"

        db_engine.execute_query(
            "INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (tid, p['name']),
            commit=True
        )
        db_engine.execute_query(
            "INSERT INTO edges (source_type, source_id, target_type, target_id, relation_type, role, provenance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            ("album", mf_id, "artist", tid, relation, role, "MetaForge"),
            commit=True
        )

    removed_ids = old_artist_ids - active_artist_ids
    for r_id in removed_ids:
        remainder = db_engine.execute_query("SELECT 1 FROM edges WHERE target_id=? LIMIT 1", (r_id,))
        if not remainder:
            db_engine.execute_query("DELETE FROM library_artist WHERE mf_artist_id=?", (r_id,), commit=True)

    return jsonify({"status": "success"})

# --- END OF FILE album_engine.py ---