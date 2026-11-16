# --- START OF FILE tiles/progress/tile.py ---
# Dashboard tile: How much is tagged? (v2, 2026-11-16)
# Category = the top folder of a track's path under the library root
# (folder names as they are, John 2026-11-16). "On disk" comes from the
# shared disk count (kit.last_scan); the detail adds tagged genres.


def run(kit, detail, args):
    root = kit.library_root()
    scan = kit.last_scan()
    with kit.db() as conn:
        tagged = {}
        for (p,) in conn.execute("SELECT file_path FROM tracks"):
            if p:
                c = kit.category_of(p, root)
                tagged[c] = tagged.get(c, 0) + 1
        genres = None
        if detail:
            genres = {}
            for row in conn.execute("""SELECT coalesce(nullif(trim(genre), ''), '(no genre)') g,
                                              coalesce(nullif(trim(sub_genre), ''), '') s, count(*) n
                                       FROM tracks GROUP BY g, s"""):
                g = genres.setdefault(row["g"], {"genre": row["g"], "tracks": 0, "subs": []})
                g["tracks"] += row["n"]
                if row["s"]:
                    g["subs"].append({"name": row["s"], "tracks": row["n"]})
            genres = sorted(genres.values(), key=lambda g: -g["tracks"])
            for g in genres:
                g["subs"].sort(key=lambda s: -s["tracks"])
    on_disk = (scan or {}).get("categories", {})
    names = set(tagged) | set(on_disk)
    rows = [{"name": n, "tagged": tagged.get(n, 0), "on_disk": (on_disk.get(n) or {}).get("files")} for n in names]
    rows.sort(key=lambda r: (-(r["on_disk"] or 0), -r["tagged"], r["name"].lower()))
    return {"tagged_total": sum(tagged.values()),
            "disk_total": (scan or {}).get("files"), "scanned_at": (scan or {}).get("scanned_at"),
            "categories": rows, "genres": genres, "scan": kit.scan_status()}
