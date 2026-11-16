# --- START OF FILE tiles/health/tile.py ---
# Dashboard tile: What looks wrong? (v2, 2026-11-16)
# Each check is (id, label, sql returning item/value rows). Years are read
# from their first 4 characters; an empty year isn't counted as wrong.
# "Missing files" comes from the shared disk count (kit.last_scan).
from datetime import datetime


def _checks():
    this_year = datetime.now().year
    return [
        ("years", "Track years that look wrong", f"""
            SELECT file_path AS item, original_year AS value FROM tracks
            WHERE trim(coalesce(original_year, '')) <> ''
              AND (cast(substr(trim(original_year), 1, 4) AS INTEGER) < 1900
                   OR cast(substr(trim(original_year), 1, 4) AS INTEGER) > {this_year})
            ORDER BY original_year"""),
        ("album_year", "Album year later than its tracks", """
            SELECT lm.artist_name || ' - ' || lm.album_title AS item,
                   lm.original_year || ' (tracks up to ' || max(cast(substr(t.original_year, 1, 4) AS INTEGER)) || ')' AS value
            FROM tracks t JOIN library_master lm ON lm.mf_id = t.mf_id
            WHERE cast(substr(t.original_year, 1, 4) AS INTEGER) >= 1900
            GROUP BY lm.mf_id
            HAVING cast(substr(lm.original_year, 1, 4) AS INTEGER) > max(cast(substr(t.original_year, 1, 4) AS INTEGER))
            ORDER BY item"""),
        ("orphans", "Credits for albums no longer here", """
            SELECT e.source_id AS item, count(*) || ' credits' AS value FROM edges e
            LEFT JOIN library_master lm ON lm.mf_id = e.source_id
            WHERE e.source_type = 'album' AND lm.mf_id IS NULL
            GROUP BY e.source_id ORDER BY count(*) DESC"""),
        ("no_mood", "Tracks with no AI mood", """
            SELECT file_path AS item, '' AS value FROM tracks
            WHERE trim(coalesce(mood, '')) = '' ORDER BY file_path"""),
    ]


def run(kit, detail, args):
    limit = kit.DETAIL_LIMIT
    scan = kit.last_scan()
    checks = []
    with kit.db() as conn:
        for cid, label, sql in _checks():
            rows = conn.execute(sql).fetchall()
            n = len(rows) if cid != "orphans" else sum(int(r["value"].split()[0]) for r in rows)
            c = {"id": cid, "label": label, "count": n}
            if detail:
                c["items"] = [{"item": r["item"], "value": r["value"]} for r in rows[:limit]]
                c["more"] = max(0, len(rows) - limit)
            checks.append(c)
    missing = {"id": "missing", "label": "Tracks whose file is missing",
               "count": scan.get("missing_count") if scan else None}
    if detail and scan:
        paths = scan.get("missing", [])
        missing["items"] = [{"item": p, "value": ""} for p in paths[:limit]]
        missing["more"] = max(0, len(paths) - limit)
    checks.insert(1, missing)
    return {"checks": checks}
