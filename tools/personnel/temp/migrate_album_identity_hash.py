# --- START OF FILE migrate_album_identity_hash.py ---
# ======================================================================
# One-time migration: recompute every mf_id using the new normalized
# hash (edge_normalizer.hash_album_identity, added 2026-08-01 as the
# album-level counterpart to hash_artist_identity). Same rationale as
# migrate_artist_identity_hash.py: mf_id used to be
# sha256(f"{artist}|{album}") with only case/whitespace normalized, so a
# stray "!" or period on an album title -- e.g. a MusicBrainz-seeded stub
# titled "And Now!" vs however a later Intelli-Tagger retag resolves the
# same release -- would hash to a DIFFERENT mf_id and silently create a
# second, duplicate library_master row instead of filling in the
# existing one with real tracks. Unmigrated, every existing mf_id in the
# database still reflects the OLD hash, so the very next commit for an
# already-known album could immediately re-fragment it.
#
# Two cases per existing library_master row:
#   - No collision: old mf_id -> new mf_id is a straight 1:1 rename.
#     Updated everywhere it's referenced (library_master, tracks.mf_id,
#     edges.source_id where source_type='album').
#   - Collision: two or more DISTINCT existing (artist, album) rows
#     normalize to the same new mf_id (e.g. "And Now!" and "And Now" both
#     already present as separate rows). One row is kept as the merge
#     target -- preferring, in order: more tracks already attached, a
#     populated mb_album_id, then lowest old mf_id for a stable tiebreak.
#     Every other colliding row's references are repointed to the
#     winner's NEW id and the loser library_master rows are deleted.
#
# USAGE -- dry run against the live DB first (read-only, always safe):
#   python migrate_album_identity_hash.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db" --dry-run
# Inspect the collision report, THEN (only with John's go-ahead):
#   python migrate_album_identity_hash.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import hash_album_identity


def pick_winner(rows, track_counts, existing_file_counts):
    # File existence outranks everything else: a collision can involve two
    # tagging passes of the SAME album where the later pass renamed the
    # physical files (real case found live 2026-08-01 -- "Count Basie & The
    # Mills Brothers"/"The Board of Directors" had two 11-track rows, equal
    # track counts and equal mb_album_id, but the older row's file_paths no
    # longer existed at all -- picking by track count alone would have kept
    # the row pointing at dead paths and discarded the one matching what's
    # actually on disk).
    def sort_key(r):
        return (
            -existing_file_counts.get(r["mf_id"], 0),
            -track_counts.get(r["mf_id"], 0),
            0 if (r["mb_album_id"] and r["mb_album_id"] != "None") else 1,
            r["mf_id"],
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

    albums = cur.execute("SELECT * FROM library_master").fetchall()

    track_counts = defaultdict(int)
    for r in cur.execute("SELECT mf_id, COUNT(*) c FROM tracks GROUP BY mf_id"):
        track_counts[r["mf_id"]] = r["c"]

    groups = defaultdict(list)
    for a in albums:
        new_id = hash_album_identity(a["artist_name"], a["album_title"])
        groups[new_id].append(a)

    renames = []   # (old_id, new_id, artist, title) -- no collision
    merges = []    # (new_id, winner, [losers])

    # Only worth checking disk for rows actually involved in a collision --
    # everywhere else, the file-path column doesn't change at all.
    existing_file_counts = defaultdict(int)
    for new_id, rows in groups.items():
        if len(rows) > 1:
            for r in rows:
                for t in cur.execute("SELECT file_path FROM tracks WHERE mf_id=?", (r["mf_id"],)):
                    if Path(t["file_path"]).exists():
                        existing_file_counts[r["mf_id"]] += 1

    for new_id, rows in groups.items():
        if len(rows) == 1:
            old_id = rows[0]["mf_id"]
            if old_id != new_id:
                renames.append((old_id, new_id, rows[0]["artist_name"], rows[0]["album_title"]))
        else:
            winner = pick_winner(rows, track_counts, existing_file_counts)
            losers = [r for r in rows if r["mf_id"] != winner["mf_id"]]
            merges.append((new_id, winner, losers))

    print(f"Scanned {len(albums)} library_master rows -> {len(groups)} distinct normalized identities.")
    print(f"  Straight renames (no title collision): {len(renames)}")
    print(f"  Collisions requiring a merge: {len(merges)}")

    if merges:
        print("\n=== Collision detail ===")
        for new_id, winner, losers in merges:
            print(f"  KEEP \"{winner['artist_name']}\" - \"{winner['album_title']}\" "
                  f"({existing_file_counts.get(winner['mf_id'], 0)} of {track_counts.get(winner['mf_id'], 0)} track files exist, was {winner['mf_id']}) -> {new_id}")
            for l in losers:
                print(f"    MERGE \"{l['artist_name']}\" - \"{l['album_title']}\" "
                      f"({existing_file_counts.get(l['mf_id'], 0)} of {track_counts.get(l['mf_id'], 0)} track files exist, was {l['mf_id']}) into winner")

    if args.dry_run:
        print("\nDry run: no changes written. Re-run without --dry-run to apply.")
        conn.close()
        return

    for old_id, new_id, artist, title in renames:
        cur.execute("UPDATE library_master SET mf_id=? WHERE mf_id=?", (new_id, old_id))
        cur.execute("UPDATE tracks SET mf_id=? WHERE mf_id=?", (new_id, old_id))
        cur.execute("UPDATE edges SET source_id=? WHERE source_id=? AND source_type='album'", (new_id, old_id))

    for new_id, winner, losers in merges:
        for l in losers:
            old_id = l["mf_id"]
            # Tracks are DELETED, not repointed -- a same-mf_id collision
            # means artist+album normalized identically, so the loser's
            # tracks are (by strong likelihood) a stale re-tagging of the
            # SAME songs already present under the winner; repointing them
            # would double-list the album's track count instead of merging
            # it. Edges (personnel credits) repoint instead, same as the
            # artist merges -- distinct sources/roles worth preserving.
            cur.execute("DELETE FROM tracks WHERE mf_id=?", (old_id,))
            cur.execute("UPDATE edges SET source_id=? WHERE source_id=? AND source_type='album'", (new_id, old_id))
            cur.execute("DELETE FROM library_master WHERE mf_id=?", (old_id,))

        old_winner_id = winner["mf_id"]
        if old_winner_id != new_id:
            cur.execute("UPDATE library_master SET mf_id=? WHERE mf_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE tracks SET mf_id=? WHERE mf_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE edges SET source_id=? WHERE source_id=? AND source_type='album'", (new_id, old_winner_id))

    conn.commit()
    print(f"\nApplied {len(renames)} rename(s) and {len(merges)} merge(s).")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE migrate_album_identity_hash.py ---
