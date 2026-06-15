# --- START OF FILE identity_engine.py ---
# ======================================================================
# MetaForge Studio: Identity Spoke (Identity Radar)
# Physical Location: \tools\database_tools\engines\identity_engine.py
# Build 2.8.1: Added commit enforcement and explicit HTTP status responses.
# ======================================================================
import json
from flask import jsonify, request
from common import db_engine, config_handler

def handle(action):
    if action == "get_taxonomy": return _get_taxonomy()
    
    if action == "search_artist": 
        artist = request.args.get('artist', '').strip()
        album = request.args.get('album', '').strip()
        if album: return _search_album_logic(album)
        return _search_artist_logic(artist)
        
    if action == "get_artist_details": 
        aid = request.args.get('mf_artist_id')
        return _get_artist_details_logic(aid)
        
    return jsonify({"status": "error", "message": "Action unknown"}), 404

def _get_taxonomy():
    path = config_handler.DATA_DIR / "taxonomy.json"
    if path.exists():
        return jsonify({"status": "success", "taxonomy": json.loads(path.read_text(encoding='utf-8'))})
    return jsonify({"status": "error", "message": "Taxonomy missing"}), 404

def _search_artist_logic(query_str):
    res = db_engine.execute_query(
        "SELECT * FROM library_artist WHERE artist_name LIKE ?", (f"%{query_str}%",)
    )
    if not res:
        return jsonify({"status": "error", "message": f"No records found matching name: {query_str}"})
    
    if len(res) > 1:
        candidates = []
        for row in res:
            candidates.append({
                "mf_artist_id": row['mf_artist_id'],
                "artist_name": row['artist_name'],
                "country": row['country'] if row['country'] else "Unknown"
            })
        return jsonify({"status": "multiple", "candidates": candidates})
    
    # Single match identified
    return _get_artist_details_logic(res[0]['mf_artist_id'])

def _search_album_logic(query_str):
    res = db_engine.execute_query(
        "SELECT * FROM library_master WHERE album_title LIKE ?", (f"%{query_str}%",)
    )
    if not res:
        return jsonify({"status": "error", "message": f"No albums found matching title: {query_str}"})
    
    candidates = []
    for row in res:
        candidates.append({
            "mf_id": row['mf_id'],
            "album_title": row['album_title'],
            "artist_name": row['artist_name']
        })
    return jsonify({"status": "albums", "candidates": candidates})

def _get_artist_details_logic(aid):
    res = db_engine.execute_query(
        "SELECT * FROM library_artist WHERE mf_artist_id = ?", (aid,)
    )
    if not res:
        return jsonify({"status": "error", "message": "Artist details lookup failure."}), 404
        
    row = res[0]
    artist = {
        "mf_artist_id": row['mf_artist_id'],
        "artist_name": row['artist_name'],
        "country": row['country'] if row['country'] else "",
        "biography": row['biography'] if row['biography'] else "",
        "photo_path": row['photo_path'] if row['photo_path'] else ""
    }

    # 2. Gather master collection releases directly connected to this artist identity
    albums_res = db_engine.execute_query(
        "SELECT mf_id, album_title FROM library_master WHERE artist_name = ?", (artist['artist_name'],)
    )
    
    albums = []
    if albums_res:
        for r in albums_res:
            albums.append({
                "mf_id": r['mf_id'],
                "album_title": r['album_title'],
                "role": "Primary Artist"
            })
            
    # Keep track of album keys to track and suppress secondary duplicates
    primary_ids = set(a['mf_id'] for a in albums)
    
    # 3. Gather personnel edge network mappings matching base schema structures
    edges = db_engine.execute_query(
        "SELECT e.source_id as mf_id, m.album_title, e.role FROM edges e "
        "JOIN library_master m ON e.source_id = m.mf_id "
        "WHERE e.target_id = ? AND e.source_type = 'album'", (aid,)
    )
    
    # 4. Filter duplicates seamlessly and attach the requested fallback role text string
    if edges:
        for e in edges:
            mid = e['mf_id']
            # If the artist is already tracked as a Primary Artist on this release, skip duplication entirely
            if mid in primary_ids:
                continue
                
            albums.append({
                "mf_id": mid,
                "album_title": e['album_title'],
                "role": "Appears On"
            })
            primary_ids.add(mid)

    artist['albums'] = albums
    return jsonify({"status": "success", "type": "artist", "artist": artist})

def _save_artist():
    data = request.json
    
    # Universal execution primitive requires commit=True parameter to save modifications permanently
    db_engine.execute_query(
        "UPDATE library_artist SET artist_name = ?, country = ?, biography = ?, photo_path = ?, last_updated = CURRENT_TIMESTAMP WHERE mf_artist_id = ?",
        (data['name'], data['country'], data['biography'], data['photo_path'], data['mf_artist_id']),
        commit=True
    )
    
    # Return explicit JSON response block to close out the workspace fetch pipeline cleanly
    return jsonify({"status": "success", "message": "Artist identity committed."})