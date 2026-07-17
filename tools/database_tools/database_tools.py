# --- START OF FILE database_tools.py ---
# ======================================================================
# MetaForge Studio: Database Tools - Hub Dispatcher
# Role: Central Orchestrator supporting dynamic air-gapped layout modules.
# ======================================================================
import traceback
import sys
from pathlib import Path
from flask import jsonify, request
from tools.database_tools.engines import (
    identity_engine, 
    personnel_engine, 
    album_engine,
    audit_engine,
    fixer_engine
)

TOOL_DIR = Path(__file__).parent.resolve()

def run_logic(action, tools_dir, env_path):
    try:
        # Dynamic Sub-Module Fetch Action
        if action == "fetch_sub_module":
            target = request.args.get("module", "").strip().lower()
            module_map = {
                "artist": TOOL_DIR / "artist" / "artist_editor.mfi",
                "album": TOOL_DIR / "album" / "album_editor.mfi",
                "fixer": TOOL_DIR / "fixer" / "fixer_editor.mfi"
            }
            path = module_map.get(target)
            if path and path.exists():
                return jsonify({"status": "success", "html": path.read_text(encoding="utf-8")})
            return jsonify({"status": "error", "message": "Module missing"}), 404

        # Route: Fixer Module Actions
        if action in ["diagnose", "purge"]:
            return fixer_engine.handle(action)

        # Standard routes
        if action in ["get_taxonomy", "search_artist", "get_artist_details"]:
            return identity_engine.handle(action)
        if action in ["personnel_get", "personnel_add", "personnel_delete"]:
            return personnel_engine.handle(action)
        if action in ["search_album", "get_album_details", "save_album", "master_get", "master_save",
                      "get_track_detail", "save_track_detail"]:
            return album_engine.handle(action)
        if action in ["audit_run", "audit_maintenance"]:
            return audit_engine.handle(action)
        if action == "save_artist":
            from tools.database_tools.engines.identity_engine import _save_artist
            return _save_artist()

        return jsonify({"status": "error", "message": f"Action '{action}' unrecognized."}), 404
    except Exception as e:
        print(f"🔥 Database Hub Orchestrator Error [{action}]:\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Internal failure.", "trace": str(e)}), 500
# --- END OF FILE database_tools.py ---