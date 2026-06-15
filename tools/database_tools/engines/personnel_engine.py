# --- START OF FILE personnel_engine.py ---
# ======================================================================
# MetaForge Studio: Personnel Engine (Graph Layer)
# Physical Location: \tools\database_tools\engines\personnel_engine.py
# Build 1.1.28: Hub-Spoke Refactor (Dispatcher handling).
# ======================================================================
import hashlib
from flask import jsonify, request
from common import db_engine

def handle(action):
    """Dispatcher for Personnel Graph actions."""
    if action == "personnel_get": return _get_personnel()
    if action == "personnel_add": return _add_personnel()
    if action == "personnel_delete": return _delete_personnel()
    return jsonify({"status": "error", "message": "Action unknown"}), 404

def _get_personnel():
    mf_id = request.args.get('mf_id')
    edges = db_engine.execute_query(
        "SELECT e.id, e.role, a.artist_name as name, e.provenance FROM edges e "
        "JOIN library_artist a ON e.target_id = a.mf_artist_id "
        "WHERE e.source_id = ? AND e.source_type = 'album'", (mf_id,)
    )
    return jsonify({"status": "success", "edges": [dict(e) for e in edges] if edges else[]})

def _add_personnel():
    data = request.json
    mf_id = data['mf_id']
    name = data['name']
    role = data['role']
    provenance = data.get('provenance', 'MetaForge')
    tid = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()
    
    db_engine.execute_query("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name) VALUES (?, ?)", (tid, name), commit=True)
    db_engine.execute_query("INSERT INTO edges (source_type, source_id, target_type, target_id, relation_type, role, provenance) VALUES (?,?,?,?,?,?,?)", ("album", mf_id, "artist", tid, role.lower(), role, provenance), commit=True)
    return jsonify({"status": "success"})

def _delete_personnel():
    eid = request.args.get('id')
    db_engine.execute_query("DELETE FROM edges WHERE id = ?", (eid,), commit=True)
    return jsonify({"status": "success"})
# --- END OF FILE personnel_engine.py ---