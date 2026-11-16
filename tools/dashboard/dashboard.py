# --- START OF FILE dashboard.py ---
# ======================================================================
# MetaForge Tool Logic: Dashboard (v2, 2026-11-16)
#
# The Dashboard is a frame; the tiles are plug-ins, found the same way the
# app finds tools. Each tile is a folder:
#
#   tools\dashboard\tiles\<id>\
#       tile.json   id, title, description, width (1-3), order   (required)
#       tile.py     def run(kit, detail, args) -> dict            (its data)
#       tile.js     registers its drawing (see dashboard.js)       (its look)
#       tile.css    optional styles for that tile only
#
# Add a tile = drop in a folder. Remove one = delete the folder. Nothing
# else is edited. `kit` is tile_kit.py (read-only database, data files,
# the shared disk count).
#
# Layout (shown, width, order) is chosen in Settings > Dashboard and saved
# in data\dashboard\layout.json through the `layout` action below.
# ======================================================================
import importlib.util
import re
import sqlite3
from pathlib import Path

from flask import jsonify, request

HERE = Path(__file__).resolve().parent
TILES_DIR = HERE / "tiles"
ID_OK = re.compile(r"^[a-z0-9_-]+$")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kit = _load("dashboard_tile_kit", HERE / "tile_kit.py")


# --- [ DISCOVERY ] -----------------------------------------------------------

def discover():
    """Every tiles\\<id>\\tile.json with a matching id, ordered by its
    `order` then title. A malformed folder is skipped, never fatal."""
    found = {}
    if TILES_DIR.is_dir():
        for folder in TILES_DIR.iterdir():
            m = kit.read_json(folder / "tile.json", None) if folder.is_dir() else None
            if not isinstance(m, dict) or m.get("id") != folder.name or not ID_OK.match(folder.name):
                continue
            if not (folder / "tile.py").exists() or not (folder / "tile.js").exists():
                continue
            w = m.get("width")
            found[folder.name] = {
                "id": folder.name,
                "title": str(m.get("title") or folder.name),
                "description": str(m.get("description") or ""),
                "width": w if w in (1, 2, 3) else 1,
                "order": m.get("order") if isinstance(m.get("order"), (int, float)) else 999,
                "css": (folder / "tile.css").exists(),
            }
    return dict(sorted(found.items(), key=lambda kv: (kv[1]["order"], kv[1]["title"].lower())))


def default_layout(tiles):
    return [{"id": t, "shown": True, "width": m["width"]} for t, m in tiles.items()]


def load_layout(tiles):
    """The saved layout, cleaned: tiles whose folder is gone are dropped,
    newly found tiles are added at the end (shown), widths kept to 1-3."""
    saved = kit.read_json(kit.dashboard_dir() / "layout.json", {}).get("tiles")
    if not isinstance(saved, list):
        return default_layout(tiles)
    out, seen = [], set()
    for t in saved:
        tid = t.get("id") if isinstance(t, dict) else None
        if tid in tiles and tid not in seen:
            seen.add(tid)
            w = t.get("width")
            out.append({"id": tid, "shown": t.get("shown") is not False,
                        "width": w if w in (1, 2, 3) else tiles[tid]["width"]})
    out += [{"id": t, "shown": True, "width": m["width"]} for t, m in tiles.items() if t not in seen]
    return out


# --- [ DISPATCH ] ------------------------------------------------------------

def run_logic(action, tools_dir, env_path):
    try:
        if action == "layout":
            tiles = discover()
            if request.method == "POST":
                body = (request.get_json(silent=True) or {}).get("tiles")
                kit.write_json(kit.dashboard_dir() / "layout.json",
                               {"tiles": body if isinstance(body, list) else default_layout(tiles)})
            return jsonify({"status": "ok", "tiles": tiles, "layout": load_layout(tiles), "default": default_layout(tiles)})

        if action == "tile":
            tid = request.args.get("id", "")
            if not ID_OK.match(tid) or tid not in discover():
                return jsonify({"status": "error", "message": f"There's no tile called {tid}."}), 404
            module = _load(f"dashboard_tile_{tid}", TILES_DIR / tid / "tile.py")
            args = {k: v for k, v in request.args.items() if k not in ("id", "detail")}
            out = module.run(kit, request.args.get("detail") == "1", args)
            return jsonify({"status": "ok", **out})

        if action == "scan":
            return jsonify(kit.start_scan() if request.method == "POST" else kit.scan_status())
    except sqlite3.Error as e:
        return jsonify({"status": "error", "message": f"The database couldn't be read: {e}"}), 500
    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400
# --- END OF FILE dashboard.py ---
