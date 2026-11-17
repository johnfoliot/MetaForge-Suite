# --- START OF FILE tiles/backlog/tile.py ---
# Dashboard tile: What's waiting? (v2, 2026-11-16)
# Counts from other tools' hand-off files and the database; each line names
# the tool that works on it. "Credits to give MusicBrainz" is written by
# MusicBrainz Submit (submit_summary.json) each time it lists albums.
#
# 2026-11-17 (John): "Tracks without a MusicBrainz ID" and "Tracks without
# an AcoustID" used to open their tool on an empty screen, with no way to
# tell which tracks were meant. They now open a list by album (detail,
# args list=mb|acoustid), and each album opens in the tool that fixes it.
import re
from pathlib import Path

NO_MB = "coalesce(trim(mb_track_id), '') IN ('', 'None')"
NO_ACOUSTID = "coalesce(trim(acoustid), '') IN ('', 'None')"
DISC = re.compile(r"^(cd|disc|disk)\s*\d+$", re.I)


def _album_folder(file_path):
    """The album folder: the file's folder, or its parent for a disc folder."""
    folder = Path(file_path).parent
    return folder.parent if DISC.match(folder.name) else folder


def _albums(kit, conn, where):
    """Tracks matching `where`, grouped by album folder, biggest first."""
    rows = conn.execute(f"SELECT file_path FROM tracks WHERE {where}").fetchall()
    groups = {}
    for (fp,) in rows:
        groups.setdefault(_album_folder(fp), []).append(fp)
    out = []
    for folder, files in groups.items():
        prefix = str(folder).replace("\\", "/").rstrip("/") + "/"
        total = conn.execute("SELECT count(*) FROM tracks WHERE file_path LIKE ? ESCAPE '\\'",
                             (prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",)).fetchone()[0]
        out.append({"folder": str(folder), "album": f"{folder.parent.name} › {folder.name}",
                    "files": files, "missing": len(files), "total": total})
    out.sort(key=lambda a: (-a["missing"], a["album"].lower()))
    return out


def _mb_list(kit, conn):
    albums = _albums(kit, conn, NO_MB)
    for a in albums:
        a["why"] = ("No MusicBrainz release chosen"
                    if a["missing"] >= a["total"] else
                    "Not on the release chosen")
        del a["files"]
    return albums


def _acoustid_list(kit, conn, data):
    hist = data / "acoustid" / "submission_history.txt"
    waiting = set()
    if hist.exists():
        waiting = {l.strip().replace("\\", "/").lower()
                   for l in hist.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()}
    albums = _albums(kit, conn, NO_ACOUSTID)
    for a in albums:
        w = sum(1 for f in a["files"] if f.replace("\\", "/").lower() in waiting)
        a["waiting"] = w
        a["why"] = ("Sent; waiting for AcoustID" if w == a["missing"] else
                    "No AcoustID found" if w == 0 else
                    f"{w} sent and waiting; no AcoustID found for the rest")
        del a["files"]
    return albums


def run(kit, detail, args):
    data = kit.data_dir()
    with kit.db() as conn:
        no_acoustid = conn.execute(f"SELECT count(*) FROM tracks WHERE {NO_ACOUSTID}").fetchone()[0]
        no_mb = conn.execute(f"SELECT count(*) FROM tracks WHERE {NO_MB}").fetchone()[0]
        which = (args or {}).get("list")
        if detail and which in ("mb", "acoustid"):
            albums = _mb_list(kit, conn) if which == "mb" else _acoustid_list(kit, conn, data)
            return {"list": which, "count": no_mb if which == "mb" else no_acoustid,
                    "albums": albums[:kit.DETAIL_LIMIT], "more": max(0, len(albums) - kit.DETAIL_LIMIT)}
    mbs = kit.read_json(data / "musicbrainz" / "submit_summary.json", None)
    return {"lines": [
        {"label": "AcoustIDs to submit", "tool": "acoustid",
         "count": kit.count_lines(data / "acoustid" / "pending_acoustid.txt")},
        {"label": "Tracks without an AcoustID", "list": "acoustid", "count": no_acoustid},
        {"label": "Tracks without a MusicBrainz ID", "list": "mb", "count": no_mb},
        {"label": "Files waiting for repair", "tool": "repair",
         "count": kit.count_lines(data / "repair" / "remediation_queue.log")},
        {"label": "Credits to give MusicBrainz", "tool": "musicbrainz_submit",
         "count": mbs.get("credits") if mbs else None, "as_of": mbs.get("as_of") if mbs else None},
    ]}
