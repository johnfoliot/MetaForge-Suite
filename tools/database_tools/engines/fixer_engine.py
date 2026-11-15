# --- START OF FILE fixer_engine.py ---
# ======================================================================
# MetaForge Studio: Database Tools - Find and remove records
# Physical Location: \tools\database_tools\engines\fixer_engine.py
# v2 (2026-11-15). Rebuilt after the Database Tools audit:
#  - results carry real keys (mf_artist_id, mf_id, file_path, credit id),
#    not SQLite rowids, and say what each record is (credits show person,
#    role and album, not just the role);
#  - removing goes through identity_ops: a preview with counts first, a
#    typed confirmation, a backup, one transaction;
#  - removing an artist no longer deletes other artists' albums or tracks
#    (it used to delete every track where they were the performer,
#    2,377 tracks on other artists' albums at the time), and removing a
#    track works (it used to report success and do nothing).
# Only database records are removed; music files are never touched.
# ======================================================================
from flask import jsonify, request

from common import db_engine
from tools.database_tools.engines import identity_ops

LIMIT = 200


def handle(action):
    data = request.get_json() or {}
    if action == "diagnose":
        return _find(data)
    if action == "purge":
        return _purge(data)
    return jsonify({"status": "error", "message": "Invalid action"}), 400


def _q(sql, params=()):
    return db_engine.execute_query(sql, params) or []


def _find(data):
    term = (data.get("term") or "").strip()
    cat = data.get("category") or "all"
    if not term:
        return jsonify({"status": "error", "message": "Type something to search for."})
    like = f"%{term}%"
    out = []
    if cat in ("all", "artist"):
        for r in _q("SELECT a.mf_artist_id, a.artist_name, "
                    "(SELECT count(*) FROM library_master m WHERE m.mf_artist_id = a.mf_artist_id) AS albums, "
                    "(SELECT count(*) FROM tracks t WHERE t.mf_artist_id = a.mf_artist_id) AS tracks, "
                    "(SELECT count(*) FROM edges e WHERE e.target_id = a.mf_artist_id) AS credits "
                    "FROM library_artist a WHERE a.artist_name LIKE ? ORDER BY a.artist_name COLLATE NOCASE LIMIT ?",
                    (like, LIMIT)):
            out.append({"kind": "artist", "key": r["mf_artist_id"], "name": r["artist_name"],
                        "detail": f"{r['albums']} albums, {r['tracks']} tracks, {r['credits']} credits"})
    if cat in ("all", "album"):
        for r in _q("SELECT m.mf_id, m.album_title, m.artist_name, "
                    "(SELECT count(*) FROM tracks t WHERE t.mf_id = m.mf_id) AS tracks "
                    "FROM library_master m WHERE m.album_title LIKE ? ORDER BY m.album_title COLLATE NOCASE LIMIT ?",
                    (like, LIMIT)):
            out.append({"kind": "album", "key": r["mf_id"], "name": r["album_title"],
                        "detail": f"by {r['artist_name']}, {r['tracks']} tracks"})
    if cat in ("all", "track"):
        for r in _q("SELECT t.file_path, t.title, m.album_title, a.artist_name FROM tracks t "
                    "LEFT JOIN library_master m ON m.mf_id = t.mf_id "
                    "LEFT JOIN library_artist a ON a.mf_artist_id = t.mf_artist_id "
                    "WHERE t.title LIKE ? ORDER BY t.title COLLATE NOCASE LIMIT ?", (like, LIMIT)):
            out.append({"kind": "track", "key": r["file_path"], "name": r["title"] or r["file_path"],
                        "detail": f"by {r['artist_name'] or 'unknown artist'}, on {r['album_title'] or 'no album'}"})
    if cat in ("all", "personnel"):
        for r in _q("SELECT e.id, e.role, a.artist_name, m.album_title FROM edges e "
                    "LEFT JOIN library_artist a ON a.mf_artist_id = e.target_id "
                    "LEFT JOIN library_master m ON m.mf_id = e.source_id "
                    "WHERE a.artist_name LIKE ? OR e.role LIKE ? "
                    "ORDER BY a.artist_name COLLATE NOCASE, m.album_title COLLATE NOCASE LIMIT ?",
                    (like, like, LIMIT)):
            out.append({"kind": "credit", "key": r["id"], "name": f"{r['artist_name'] or 'Unknown person'}: {r['role']}",
                        "detail": f"on {r['album_title'] or 'an album no longer in the database'}"})
    return jsonify({"status": "success", "data": out, "limit": LIMIT})


def _purge(data):
    kind, key = data.get("kind"), data.get("key")
    if kind not in ("artist", "album", "track", "credit") or key in (None, ""):
        return jsonify({"status": "error", "message": "Choose something to remove."}), 400
    try:
        if not data.get("confirmed"):
            prev = identity_ops.run("purge", kind=kind, key=key)
            return jsonify({"status": "confirm", "summary": prev["summary"], "notes": prev["notes"]})
        # A short fixed word, not the record's name (COGA: no long exact
        # retyping); it still can't be confirmed by a stray Enter.
        if (data.get("typed") or "").strip().lower() != "remove":
            return jsonify({"status": "error", "message": "Type the word remove to confirm."}), 400
        res = identity_ops.run("purge", apply=True, label=f"remove {kind}", kind=kind, key=key)
        return jsonify({"status": "success", "summary": res["summary"], "backup": res["backup"]})
    except ValueError as ex:
        return jsonify({"status": "error", "message": str(ex)}), 409

# --- END OF FILE fixer_engine.py ---
