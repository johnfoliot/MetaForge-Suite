# --- START OF FILE tiles/bios/tile.py ---
# Dashboard tile: Who needs a bio? (v2, 2026-11-16)
# Main artists: 10+ tracks and no bio. Session players: credited on albums
# by at least N different artists (John: 8) with no tracks of their own.
# N is this tile's own setting (data\dashboard\tiles\bios.json), changed
# in the detail dialog (args["min"]).

PRIMARY_MIN_TRACKS = 10
DEFAULTS = {"supporting_min": 8}
EMPTY_BIO = "trim(coalesce(a.biography, '')) IN ('', '[EMPTY]', 'None')"


def _lists(conn, supporting_min):
    primary = [dict(r) for r in conn.execute(f"""
        SELECT a.mf_artist_id AS id, a.artist_name AS name, count(*) AS tracks
        FROM library_artist a JOIN tracks t ON t.mf_artist_id = a.mf_artist_id
        WHERE {EMPTY_BIO}
        GROUP BY a.mf_artist_id HAVING tracks >= ?
        ORDER BY tracks DESC, name""", (PRIMARY_MIN_TRACKS,))]
    # Ranked by how many DIFFERENT artists they're credited with (a player on
    # 12 artists' albums matters more to the web of credits than one on 25
    # tracks by one band). MusicBrainz placeholders ([traditional]...) left out.
    supporting = [dict(r) for r in conn.execute(f"""
        SELECT e.target_id AS id, a.artist_name AS name,
               count(DISTINCT lm.mf_artist_id) AS artists, count(*) AS credits
        FROM edges e
        JOIN library_master lm ON lm.mf_id = e.source_id
        JOIN library_artist a ON a.mf_artist_id = e.target_id
        WHERE e.source_type = 'album' AND e.target_type = 'artist' AND {EMPTY_BIO}
          AND a.artist_name NOT LIKE '[%'
          AND NOT EXISTS (SELECT 1 FROM tracks t WHERE t.mf_artist_id = e.target_id)
        GROUP BY e.target_id HAVING artists >= ?
        ORDER BY artists DESC, credits DESC, name""", (supporting_min,))]
    return primary, supporting


def run(kit, detail, args):
    s = kit.tile_settings("bios", DEFAULTS)
    n = s.get("supporting_min")
    if not (isinstance(n, int) and 2 <= n <= 50):
        n = DEFAULTS["supporting_min"]
    if detail and args.get("min"):
        try:
            asked = int(args["min"])
            if 2 <= asked <= 50:
                n = asked
                kit.save_tile_settings("bios", {**s, "supporting_min": n})
        except ValueError:
            pass
    with kit.db() as conn:
        primary, supporting = _lists(conn, n)
    out = {"primary_min": PRIMARY_MIN_TRACKS, "supporting_min": n,
           "primary_count": len(primary), "supporting_count": len(supporting)}
    if detail:
        out.update(primary=primary[:kit.DETAIL_LIMIT], supporting=supporting[:kit.DETAIL_LIMIT])
    return out
