# --- START OF FILE tile_kit.py ---
# ======================================================================
# MetaForge Dashboard: the tile kit (v2, 2026-11-16)
#
# What every tile's tile.py may use. The Dashboard hands this module to a
# tile as `kit`:   def run(kit, detail, args) -> dict
# so a tile never imports the Dashboard or another tile. Everything here
# is read-only on the database and the library; the only files written are
# in data\dashboard\.
# ======================================================================
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from flask import current_app

from common import config_handler

AUDIO_EXT = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".ape", ".wma", ".aac", ".aiff", ".alac"}
SKIP_TOP = {"system volume information", "$recycle.bin", "recycler", "found.000"}
DETAIL_LIMIT = 500               # rows per list in a detail dialog


# --- [ FILES ] ---------------------------------------------------------------

def data_dir():
    """MetaForge's data folder (other tools' queues live under it)."""
    return Path(config_handler.DATA_DIR)


def dashboard_dir():
    return data_dir() / "dashboard"


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, data):
    """Atomic: write a .tmp, then swap it in."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def count_lines(path):
    """Non-blank lines in a queue file; 0 if it doesn't exist."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def tile_settings(tile_id, defaults):
    """A tile's own saved settings (data\\dashboard\\tiles\\<id>.json),
    with defaults for anything missing."""
    saved = read_json(dashboard_dir() / "tiles" / f"{tile_id}.json", {})
    return {**defaults, **(saved if isinstance(saved, dict) else {})}


def save_tile_settings(tile_id, values):
    write_json(dashboard_dir() / "tiles" / f"{tile_id}.json", values)


# --- [ DATABASE ] ------------------------------------------------------------

@contextmanager
def db():
    """Read-only connection, rows as sqlite3.Row. Always closed afterwards
    (a plain `with sqlite3.connect()` only commits; it doesn't close)."""
    uri = Path(config_handler.DB_PATH).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# --- [ LIBRARY FOLDERS ] -----------------------------------------------------

def library_root():
    return config_handler.LIBRARY_ROOT()


def norm(path):
    return str(path).replace("\\", "/")


def category_of(path, root):
    """The top folder under the library root: 'F:/Pop, Rock/Artist/Album/x.mp3'
    -> 'Pop, Rock'. Paths outside the root use their first folder."""
    p, r = norm(path), norm(root).rstrip("/") + "/"
    rest = p[len(r):] if p.lower().startswith(r.lower()) else p.split(":", 1)[-1].lstrip("/")
    return rest.split("/", 1)[0] if "/" in rest else "(not in a folder)"


# --- [ DISK COUNT (background, shared by every tile) ] -----------------------

def last_scan():
    """The last finished count of files on disk, or None:
    {scanned_at, root, files, categories:{name:{files, albums}}, missing_count, missing[]}"""
    return read_json(dashboard_dir() / "library_scan.json", None)


def _scan_state():
    return current_app.extensions.setdefault("dashboard_scan", {"running": False, "files": 0, "error": None})


def scan_status():
    st = _scan_state()
    return {"status": "ok", "running": st["running"], "files": st["files"], "error": st["error"]}


def _scan(root, state, db_path):
    """Count audio files and album folders per category folder, then find
    database tracks whose file isn't there. About 10 minutes for F:\\ over USB."""
    try:
        cats, seen = {}, set()
        for top in os.scandir(root):
            if not top.is_dir(follow_symlinks=False) or top.name.lower() in SKIP_TOP or top.name.startswith((".", "$")):
                continue
            files = albums = 0
            stack = [top.path]
            while stack:
                d = stack.pop()
                here = 0
                try:
                    with os.scandir(d) as it:
                        for e in it:
                            if e.is_dir(follow_symlinks=False):
                                stack.append(e.path)
                            elif os.path.splitext(e.name)[1].lower() in AUDIO_EXT:
                                here += 1
                                seen.add(norm(e.path).lower())
                except OSError:
                    continue
                if here:
                    files += here
                    albums += 1
                    state["files"] += here
            if files:
                cats[top.name] = {"files": files, "albums": albums}
        conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
        r = norm(root).rstrip("/").lower() + "/"
        missing = [p for (p,) in conn.execute("SELECT file_path FROM tracks")
                   if p and norm(p).lower().startswith(r) and norm(p).lower() not in seen]
        conn.close()
        write_json(dashboard_dir() / "library_scan.json", {
            "scanned_at": datetime.now().isoformat(timespec="seconds"), "root": str(root),
            "files": sum(c["files"] for c in cats.values()), "categories": cats,
            "missing_count": len(missing), "missing": sorted(missing)})
    except Exception as e:      # shown on the tile; never crashes the app
        state["error"] = str(e)
    finally:
        state["running"] = False


def start_scan():
    state = _scan_state()
    if state["running"]:
        return {"status": "ok", "running": True}
    root = library_root()
    if not Path(root).is_dir():
        return {"status": "error", "message": f"The library folder ({root}) isn't available. Check that the drive is connected."}
    state.update(running=True, files=0, error=None, started=time.time())
    threading.Thread(target=_scan, args=(root, state, config_handler.DB_PATH), daemon=True).start()
    return {"status": "ok", "running": True}
# --- END OF FILE tile_kit.py ---
