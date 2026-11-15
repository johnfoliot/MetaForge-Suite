# --- START OF FILE taxonomy_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Taxonomy (genres and sub-genres)
# Physical Location: \tools\settings\engines\taxonomy_engine.py
# v2 (2026-11-15):
#  - save() keeps a backup of the previous taxonomy.json first
#    (data/backups/taxonomy.<stamp>.json, newest 20 kept); 1.x overwrote it.
#  - save() refuses blank names and duplicates (case-insensitive).
#  - usage() reports how many tracks use each genre / sub-genre, so the
#    screen can warn before a rename or delete strands tagged tracks.
#  data/ is shared with the 1.x build (junction), so is this file.
# ======================================================================
import json
import shutil
import sqlite3
import time

from flask import jsonify, request

from common import config_handler

KEEP_BACKUPS = 20


def _path():
    return config_handler.DATA_DIR / "taxonomy.json"


def get():
    try:
        if _path().exists():
            return jsonify(json.loads(_path().read_text(encoding="utf-8")))
        return jsonify({"status": "error", "message": "The genre list (taxonomy.json) is missing."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": f"The genre list couldn't be read: {e}"}), 500


def _validate(tax):
    if not isinstance(tax, dict):
        return "The genre list wasn't in the expected format."
    seen = set()
    for genre, subs in tax.items():
        g = (genre or "").strip()
        if not g:
            return "A genre has no name."
        if g.lower() in seen:
            return f"The genre “{g}” appears twice."
        seen.add(g.lower())
        if not isinstance(subs, list):
            return f"“{g}” has no sub-genre list."
        sub_seen = set()
        for s in subs:
            s2 = (s or "").strip() if isinstance(s, str) else ""
            if not s2:
                return f"A sub-genre under “{g}” has no name."
            if s2.lower() in sub_seen:
                return f"The sub-genre “{s2}” appears twice under “{g}”."
            sub_seen.add(s2.lower())
    return None


def _backup():
    src = _path()
    if not src.exists():
        return None
    folder = config_handler.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"taxonomy.{time.strftime('%Y%m%d-%H%M%S')}.json"
    shutil.copy2(src, dest)
    old = sorted(folder.glob("taxonomy.*.json"))
    for f in old[:-KEEP_BACKUPS]:
        f.unlink(missing_ok=True)
    return dest.name


def save():
    try:
        tax = request.json
        problem = _validate(tax)
        if problem:
            return jsonify({"status": "error", "message": problem}), 400
        clean = {g.strip(): [s.strip() for s in subs] for g, subs in tax.items()}
        backup = _backup()
        tmp = _path().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(clean, indent=4, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_path())
        return jsonify({"status": "success", "backup": backup})
    except Exception as e:
        return jsonify({"status": "error", "message": f"The genre list couldn't be saved: {e}"}), 500


def usage():
    """{"genres": {"Blues": 812, ...}, "sub_genres": {"Blues\u001fDelta Blues": 40, ...}}"""
    try:
        db = config_handler.DB_PATH
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            genres = {g: n for g, n in con.execute(
                "SELECT genre, COUNT(*) FROM tracks WHERE COALESCE(genre,'') <> '' GROUP BY genre")}
            subs = {f"{g}\u001f{s}": n for g, s, n in con.execute(
                "SELECT genre, sub_genre, COUNT(*) FROM tracks "
                "WHERE COALESCE(sub_genre,'') <> '' GROUP BY genre, sub_genre")}
        finally:
            con.close()
        return jsonify({"status": "success", "genres": genres, "sub_genres": subs})
    except Exception as e:
        # Counts are a courtesy; the screen still works without them.
        return jsonify({"status": "error", "message": f"Track counts unavailable: {e}"})

# --- END OF FILE taxonomy_engine.py ---
