# --- START OF FILE database_tools.py ---
# ======================================================================
# MetaForge Studio: Database Tools - dispatcher
# v2 (2026-11-15): the unused audit / personnel / master actions are gone
# (no screen called them); rename, merge and remove go through
# engines/identity_ops.py.
# ======================================================================
import traceback
from pathlib import Path
from flask import jsonify, request
from tools.database_tools.engines import identity_engine, album_engine, fixer_engine

TOOL_DIR = Path(__file__).parent.resolve()
MODULES = {
    "artist": TOOL_DIR / "artist" / "artist_editor.mfi",
    "album": TOOL_DIR / "album" / "album_editor.mfi",
    "fixer": TOOL_DIR / "fixer" / "fixer_editor.mfi",
}


def run_logic(action, tools_dir, env_path):
    try:
        if action == "fetch_sub_module":
            path = MODULES.get(request.args.get("module", "").strip().lower())
            if path and path.exists():
                return jsonify({"status": "success", "html": path.read_text(encoding="utf-8")})
            return jsonify({"status": "error", "message": "Module missing"}), 404
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
