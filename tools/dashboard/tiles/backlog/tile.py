# --- START OF FILE tiles/backlog/tile.py ---
# Dashboard tile: What's waiting? (v2, 2026-11-16)
# Counts from other tools' hand-off files and the database; each line names
# the tool that works on it. "Credits to give MusicBrainz" is written by
# MusicBrainz Submit (submit_summary.json) each time it lists albums.


def run(kit, detail, args):
    data = kit.data_dir()
    with kit.db() as conn:
        no_acoustid = conn.execute("SELECT count(*) FROM tracks WHERE coalesce(trim(acoustid), '') IN ('', 'None')").fetchone()[0]
        no_mb = conn.execute("SELECT count(*) FROM tracks WHERE coalesce(trim(mb_track_id), '') IN ('', 'None')").fetchone()[0]
    mbs = kit.read_json(data / "musicbrainz" / "submit_summary.json", None)
    return {"lines": [
        {"label": "AcoustIDs to submit", "tool": "acoustid",
         "count": kit.count_lines(data / "acoustid" / "pending_acoustid.txt")},
        {"label": "Tracks without an AcoustID", "tool": "acoustid", "count": no_acoustid},
        {"label": "Tracks without a MusicBrainz ID", "tool": "musicbrainz_id", "count": no_mb},
        {"label": "Files waiting for repair", "tool": "repair",
         "count": kit.count_lines(data / "repair" / "remediation_queue.log")},
        {"label": "Credits to give MusicBrainz", "tool": "musicbrainz_submit",
         "count": mbs.get("credits") if mbs else None, "as_of": mbs.get("as_of") if mbs else None},
    ]}
