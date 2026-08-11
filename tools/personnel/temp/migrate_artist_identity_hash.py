# --- START OF FILE migrate_artist_identity_hash.py ---
# ======================================================================
# One-time migration: recompute every mf_artist_id using the new
# normalized hash (edge_normalizer.hash_artist_identity, added 2026-07-31
# after John's edges-table audit found "Al Jackson Jr." and
# "Al Jackson, Jr." split into two identities purely over a comma). All
# ingestion code now hashes through that normalized form, but every
# mf_artist_id already sitting in the database was computed with the OLD
# raw sha256(name.strip().lower()) -- unmigrated, the very next
# personnel/tag commit for "Al Jackson, Jr." would compute a hash that no
# longer matches its own existing library_artist row, creating a THIRD
# identity instead of fixing anything.
#
# Two cases per existing library_artist row:
#   - No collision: old mf_artist_id -> new mf_artist_id is a straight
#     1:1 rename. Updated everywhere it's referenced (library_artist,
#     library_master, tracks, edges.target_id).
#   - Collision: two or more DISTINCT existing names normalize to the
#     same new hash (e.g. the Al Jackson case, generalized). One row is
#     kept as the merge target -- preferring, in order: a populated
#     mb_artist_id, then a populated biography/photo_path/country, then
#     more total edges+track references, then lowest old mf_artist_id for
#     a stable tiebreak. Every other colliding row's references are
#     repointed to the winner's NEW id and the loser library_artist rows
#     are deleted, mirroring the manual Al Jackson merge done by hand
#     this same session.
#
# USAGE -- dry run against the live DB first (read-only, always safe):
#   python migrate_artist_identity_hash.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db" --dry-run
# Inspect the collision report, THEN (only with John's go-ahead):
#   python migrate_artist_identity_hash.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import hash_artist_identity


def pick_winner(rows, edge_counts, track_counts):
    def sort_key(r):
        return (
            0 if r["mb_artist_id"] else 1,
            0 if (r["biography"] or r["photo_path"] or r["country"]) else 1,
            -(edge_counts.get(r["mf_artist_id"], 0) + track_counts.get(r["mf_artist_id"], 0)),
            r["mf_artist_id"],
        )
    return sorted(rows, key=sort_key)[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    artists = cur.execute("SELECT * FROM library_artist").fetchall()

    edge_counts = defaultdict(int)
    for r in cur.execute("SELECT target_id, COUNT(*) c FROM edges WHERE target_type='artist' GROUP BY target_id"):
        edge_counts[r["target_id"]] = r["c"]

    track_counts = defaultdict(int)
    for r in cur.execute("SELECT mf_artist_id, COUNT(*) c FROM tracks WHERE mf_artist_id IS NOT NULL GROUP BY mf_artist_id"):
        track_counts[r["mf_artist_id"]] = r["c"]

    groups = defaultdict(list)
    for a in artists:
        new_id = hash_artist_identity(a["artist_name"])
        groups[new_id].append(a)

    renames = []      # (old_id, new_id, name) -- no collision
    merges = []        # (new_id, winner_old_id, [loser_old_ids], names)

    for new_id, rows in groups.items():
        if len(rows) == 1:
            old_id = rows[0]["mf_artist_id"]
            if old_id != new_id:
                renames.append((old_id, new_id, rows[0]["artist_name"]))
        else:
            winner = pick_winner(rows, edge_counts, track_counts)
            losers = [r for r in rows if r["mf_artist_id"] != winner["mf_artist_id"]]
            merges.append((new_id, winner, losers))

    print(f"Scanned {len(artists)} library_artist rows -> {len(groups)} distinct normalized identities.")
    print(f"  Straight renames (no name collision): {len(renames)}")
    print(f"  Collisions requiring a merge: {len(merges)}")

    if merges:
        print("\n=== Collision detail ===")
        for new_id, winner, losers in merges:
            print(f"  KEEP \"{winner['artist_name']}\" (was {winner['mf_artist_id']}) -> {new_id}")
            for l in losers:
                print(f"    MERGE \"{l['artist_name']}\" (was {l['mf_artist_id']}) into winner")

    if args.dry_run:
        print("\nDry run: no changes written. Re-run without --dry-run to apply.")
        conn.close()
        return

    # Apply straight renames
    for old_id, new_id, name in renames:
        cur.execute("UPDATE library_artist SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
        cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
        cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
        cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_id))

    # Apply merges: repoint every loser's references to the winner's NEW id,
    # then rename the winner row itself, then drop the loser rows.
    for new_id, winner, losers in merges:
        for l in losers:
            old_id = l["mf_artist_id"]
            cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
            cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
            cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_id))
            cur.execute("DELETE FROM library_artist WHERE mf_artist_id=?", (old_id,))

        old_winner_id = winner["mf_artist_id"]
        if old_winner_id != new_id:
            cur.execute("UPDATE library_artist SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_winner_id))

    conn.commit()
    print(f"\nApplied {len(renames)} rename(s) and {len(merges)} merge(s).")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE migrate_artist_identity_hash.py ---
