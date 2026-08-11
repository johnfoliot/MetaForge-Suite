# --- START OF FILE fix_discogs_disambiguation_suffix.py ---
# ======================================================================
# One-off cleanup: strips Discogs' trailing "(N)" disambiguation number
# (e.g. "Carl Smith (2)") off every already-polluted library_artist row,
# and reconciles the result against whatever else is already in the
# table -- same rationale as edge_normalizer.py's 2026-08-01 identity-
# hash fix, just for a Discogs-specific pattern discogs_personnel_engine.py
# now strips at ingestion time going forward (see that file's 2026-08-07
# fix). This script is the one-time catch-up for rows already written
# before that fix existed.
#
# Two cases per polluted row, same shape as migrate_artist_identity_hash.py:
#   - Stripping the suffix produces a name with NO existing clean
#     identity anywhere else in the table: renamed in place to the
#     canonical hash of the clean name (so a future Discogs import of
#     the same clean name resolves to this same row instead of creating
#     a third identity).
#   - Stripping produces a name that ALREADY has a real, populated
#     identity elsewhere (from MusicBrainz, Wikipedia, a different
#     Discogs credit, manual entry, etc): the polluted row is merged
#     into it -- edges/tracks/library_master repointed, any unique
#     bio/photo/country preserved, the polluted row deleted. Multiple
#     polluted rows stripping to the same clean name (e.g. two different
#     Discogs-numbered "Richard Jones" entries with no other name on
#     file) also collapse together here -- consistent with how this
#     whole identity system already works: it resolves by name text, not
#     real-world entity, so two genuinely different people sharing one
#     plain name were never distinguished by this system either.
#
# USAGE -- dry run against a COPY of the live database first:
#   python fix_discogs_disambiguation_suffix.py --db path\to\copy.db --dry-run
# Inspect the results, THEN (only with John's go-ahead):
#   python fix_discogs_disambiguation_suffix.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import hash_artist_identity

SUFFIX_RE = re.compile(r'\s*\(\d+\)\s*$')


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
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    all_artists = cur.execute("SELECT * FROM library_artist").fetchall()
    polluted = [a for a in all_artists if SUFFIX_RE.search(a["artist_name"] or "")]

    print(f"Scanned {len(all_artists)} library_artist rows -> {len(polluted)} with a Discogs-style trailing (N).")
    if not polluted:
        print("Nothing to fix.")
        conn.close()
        return

    edge_counts = defaultdict(int)
    for r in cur.execute("SELECT target_id, COUNT(*) c FROM edges WHERE target_type='artist' GROUP BY target_id"):
        edge_counts[r["target_id"]] = r["c"]

    track_counts = defaultdict(int)
    for r in cur.execute("SELECT mf_artist_id, COUNT(*) c FROM tracks WHERE mf_artist_id IS NOT NULL GROUP BY mf_artist_id"):
        track_counts[r["mf_artist_id"]] = r["c"]

    # Group EVERY row (polluted or not) by the clean-name hash, so a
    # polluted row correctly finds an already-clean identity elsewhere in
    # the table, not just other polluted rows.
    groups = defaultdict(list)
    for a in all_artists:
        clean_name = SUFFIX_RE.sub('', a["artist_name"] or "").strip()
        if not clean_name:
            continue
        clean_id = hash_artist_identity(clean_name)
        groups[clean_id].append((a, clean_name))

    renames = []   # (old_id, new_id, clean_name)
    merges = []    # (new_id, winner, [losers], clean_name)

    for clean_id, entries in groups.items():
        involved_polluted = [e for e in entries if e[0] in polluted]
        if not involved_polluted:
            continue  # this identity group has no polluted member, nothing to do

        rows = [e[0] for e in entries]
        clean_name = entries[0][1]

        if len(rows) == 1:
            old_id = rows[0]["mf_artist_id"]
            if old_id != clean_id:
                renames.append((old_id, clean_id, clean_name))
        else:
            winner = pick_winner(rows, edge_counts, track_counts)
            losers = [r for r in rows if r["mf_artist_id"] != winner["mf_artist_id"]]
            merges.append((clean_id, winner, losers, clean_name))

    print(f"  Straight renames (no other identity to merge into): {len(renames)}")
    print(f"  Merges (a clean/other identity already exists): {len(merges)}")

    if renames:
        print("\n=== Renames ===")
        for old_id, new_id, clean_name in renames:
            print(f"  \"{clean_name}\" (was {old_id}) -> {new_id}")

    if merges:
        print("\n=== Merges ===")
        for new_id, winner, losers, clean_name in merges:
            print(f"  KEEP \"{winner['artist_name']}\" (was {winner['mf_artist_id']}) -> {new_id}")
            for l in losers:
                print(f"    MERGE \"{l['artist_name']}\" (was {l['mf_artist_id']}) into winner")

    if args.dry_run:
        print("\nDry run: no changes written. Re-run without --dry-run to apply.")
        conn.close()
        return

    for old_id, new_id, clean_name in renames:
        cur.execute("UPDATE library_artist SET mf_artist_id=?, artist_name=? WHERE mf_artist_id=?", (new_id, clean_name, old_id))
        cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
        cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
        cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_id))

    for new_id, winner, losers, clean_name in merges:
        for l in losers:
            old_id = l["mf_artist_id"]
            w = cur.execute("SELECT biography, photo_path, country FROM library_artist WHERE mf_artist_id=?", (winner["mf_artist_id"],)).fetchone()
            if not (w["biography"] and w["photo_path"] and w["country"]):
                cur.execute(
                    "UPDATE library_artist SET biography=COALESCE(NULLIF(biography,''), ?), "
                    "photo_path=COALESCE(NULLIF(photo_path,''), ?), country=COALESCE(NULLIF(country,''), ?) "
                    "WHERE mf_artist_id=?",
                    (l["biography"], l["photo_path"], l["country"], winner["mf_artist_id"])
                )
            cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
            cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_id))
            cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_id))
            cur.execute("DELETE FROM library_artist WHERE mf_artist_id=?", (old_id,))

        old_winner_id = winner["mf_artist_id"]
        cur.execute("UPDATE library_artist SET mf_artist_id=?, artist_name=? WHERE mf_artist_id=?", (new_id, clean_name, old_winner_id))
        if old_winner_id != new_id:
            cur.execute("UPDATE library_master SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, old_winner_id))
            cur.execute("UPDATE edges SET target_id=? WHERE target_id=? AND target_type='artist'", (new_id, old_winner_id))

    conn.commit()
    print(f"\nApplied {len(renames)} rename(s) and {len(merges)} merge(s).")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE fix_discogs_disambiguation_suffix.py ---
