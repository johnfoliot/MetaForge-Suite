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

import app as mf  # noqa: E402  (importing does not start the window; only __main__ does)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
print(f"[dev] MetaForge UI-only server for {ROOT} on http://127.0.0.1:{port}")
mf.app.run(port=port, debug=False, use_reloader=False, threaded=True)
