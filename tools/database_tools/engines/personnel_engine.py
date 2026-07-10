# --- START OF FILE personnel_engine.py ---
# ======================================================================
# MetaForge Studio: Personnel Engine (Graph Layer)
# Physical Location: \tools\database_tools\engines\personnel_engine.py
# Build 1.1.28: Hub-Spoke Refactor (Dispatcher handling).
# ======================================================================
import hashlib
from flask import jsonify, request
from common import db_engine
from tools.personnel.edge_normalizer import normalize_personnel
from tools.personnel import edge_store

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
    # Routes through the same normalize_personnel()/classify_role() pipeline
    # personnel.py's Wikipedia commit already uses, instead of writing
    # role.lower() directly as relation_type -- this endpoint (the manual/
    # bulk-JSON path used for AllMusic imports) was the source of a large
    # share of legacy edge rows with raw free-text relation_type and no
    # evidence_scope/detail. See tools/personnel/temp/reclassify_legacy_edges.py
    # for the one-off backfill of rows already written the old way.
    #
    # Inserts go through edge_store.upsert_edge() (not a raw INSERT) so a
    # re-import of the same credit updates the existing row instead of
    # piling up a duplicate -- see edge_store.py's module docstring.
    data = request.json
    mf_id = data['mf_id']
    name = data['name'].strip()
    role = data['role']
    provenance = data.get('provenance', 'MetaForge')
    tid = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()

    db_engine.execute_query("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name) VALUES (?, ?)", (tid, name), commit=True)

    atomic_edges = normalize_personnel(role)
    count = 0

    for edge in atomic_edges:
        edge_store.upsert_edge(
            source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
            relation_type=edge['relation_type'], role=edge['role'],
            confidence=edge['confidence'], provenance=provenance,
            evidence_scope=edge['evidence_scope'], evidence_detail=edge['evidence_detail'],
            weight=edge['weight']
        )
        count += 1

    return jsonify({"status": "success", "count": count})

def _delete_personnel():
    eid = request.args.get('id')
    db_engine.execute_query("DELETE FROM edges WHERE id = ?", (eid,), commit=True)
    return jsonify({"status": "success"})
# --- END OF FILE personnel_engine.py ---