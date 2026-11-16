# --- START OF FILE database_tools.py ---
# ======================================================================
# MetaForge Studio: Database Tools - dispatcher
# v2 (2026-11-15): the unused audit / personnel / master actions are gone
# (no screen called them) and so is fetch_sub_module (the three panels
# are now tabs in database_tools.mfi); rename, merge and remove go
# through engines/identity_ops.py.
# ======================================================================
import traceback
from flask import jsonify
from tools.database_tools.engines import identity_engine, album_engine, fixer_engine

def run_logic(action, tools_dir, env_path):
    try:
        if action in ("diagnose", "purge"):
            return fixer_engine.handle(action)
        if action in ("get_taxonomy", "search_artist", "get_artist_details", "save_artist", "merge_artists"):
            return identity_engine.handle(action)
        if action in ("search_album", "get_album_details", "save_album", "get_track_detail", "save_track_detail"):
            return album_engine.handle(action)
        return jsonify({"status": "error", "message": f"Action '{action}' unrecognized."}), 404
    except Exception as e:
        print(f"🔥 Database Tools error [{action}]:\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"Something went wrong on the server ({e}).",
                        "trace": str(e)}), 500
# --- END OF FILE database_tools.py ---
