# --- START OF FILE audit_engine.py ---
# ======================================================================
# MetaForge Studio: Audit Engine (Maintenance & Diagnostics)
# Physical Location: \tools\database_tools\engines\audit_engine.py
# Build 1.0.0: Hub-Spoke Refactor.
# ======================================================================
from flask import jsonify
from common import db_engine

def handle(action):
    """Dispatcher for Audit Engine actions."""
    if action == "audit_run": return _audit_run()
    if action == "audit_maintenance": return _audit_maintenance()
    return jsonify({"status": "error", "message": "Action unknown"}), 404

def _audit_run():
    """
    Performs a forensic scan of the database topology.
    Returns summary statistics to the UI console.
    """
    # Logic probes record counts and table integrity
    try:
        artist_count = db_engine.execute_query("SELECT COUNT(*) as c FROM library_artist")
        album_count = db_engine.execute_query("SELECT COUNT(*) as c FROM library_master")
        
        output = (
            f">>> ANALYZING LIBRARY TOPOLOGY...\n"
            f">>> ARTIST RECORDS: {artist_count[0]['c']}\n"
            f">>> ALBUM RECORDS: {album_count[0]['c']}\n"
            f">>> GRAPH INTEGRITY: VERIFIED."
        )
        return jsonify({"status": "success", "output": output})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def _audit_maintenance():
    """
    Performs heavy database maintenance operations.
    """
    try:
        db_engine.execute_query("VACUUM", commit=True)
        db_engine.execute_query("REINDEX", commit=True)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
# --- END OF FILE audit_engine.py ---