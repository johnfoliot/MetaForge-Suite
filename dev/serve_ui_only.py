# ======================================================================
# MetaForge Dev Tool: UI-only server (no WebView2 window)
# Physical Location: \dev\serve_ui_only.py
# ======================================================================
"""
Runs MetaForge's Flask server WITHOUT opening the desktop window, so the
UI can be reviewed in an ordinary browser (used for v2 UI verification:
screenshots, keyboard walk-throughs, contrast checks).

Uses port 5050 so it never collides with a real MetaForge window (5000).
Nothing here changes how MetaForge is normally launched. Pages that call
the desktop bridge (folder pickers etc.) won't work in a plain browser;
everything else does. It uses the same live database as the real app, so
avoid pressing buttons that run jobs or write data while reviewing.

Usage (from the project root):  venv python dev\\serve_ui_only.py [port]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ui"))
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Sandbox (v2, 2026-11-15): a folder as the second argument makes the server
# use <folder>\appdata\metaforge.db and <folder>\data (taxonomy, moods,
# MusicBrainz logs) instead of the live ones, so tools that write can be
# tested on copies (e.g. the Database Tools test set: copies of the
# database, the logs and some albums' MP3s). Must run before `import app`.
if len(sys.argv) > 2:
    from common import config_handler
    box = Path(sys.argv[2])
    config_handler.APPDATA_MF = box / "appdata"
    config_handler.DB_PATH = box / "appdata" / "metaforge.db"
    config_handler.DATA_DIR = box / "data"
    print(f"[dev] SANDBOX: database {config_handler.DB_PATH}, data {config_handler.DATA_DIR}")

import app as mf  # noqa: E402  (importing does not start the window; only __main__ does)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
print(f"[dev] MetaForge UI-only server for {ROOT} on http://127.0.0.1:{port}")
mf.app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)   # this PC only (see ui/app.py run_flask)
