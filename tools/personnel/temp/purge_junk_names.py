# --- START OF FILE purge_junk_names.py ---
# ======================================================================
# One-off purge of already-committed edges whose CREDITED NAME (not
# role) is a known non-entity placeholder -- "Traditional", "Public
# Domain", etc, added to performance.json's junk_names 2026-08-01 after
# John's live audit found "Traditional" bridging 17 albums in the edges
# table as if it were a real session musician. Unlike a junk role, a
# junk name is never legitimate regardless of what role accompanies it
# -- no re-atomization needed, the whole edge is simply invalid.
#
# Reuses edge_normalizer.is_junk_name() -- the exact same denylist
# ingestion already checks -- so this can never drift out of sync with
# what new personnel data gets filtered going forward.
#
# USAGE -- run by hand, against a COPY of the live database first:
#   python purge_junk_names.py --db path\to\copy.db --dry-run
#   python purge_junk_names.py --db path\to\copy.db
# Inspect the results, THEN (only with John's go-ahead) run for real:
#   python purge_junk_names.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import is_junk_name, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    config = load_config()

    cur.execute("SELECT mf_artist_id, artist_name FROM library_artist")
    artists = cur.fetchall()
    junk_artists = [a for a in artists if is_junk_name(a["artist_name"], config)]

    print(f"Scanned {len(artists)} library_artist rows. Found {len(junk_artists)} junk-name match(es).\n")

    if not junk_artists:
        print("Nothing to purge.")
        conn.close()
        return

    total_edges = 0
    for a in junk_artists:
        cur.execute("SELECT COUNT(*) FROM edges WHERE target_id = ?", (a["mf_artist_id"],))
        n = cur.fetchone()[0]
        total_edges += n
        print(f"  \"{a['artist_name']}\": {n} edge(s) to remove, library_artist row to remove")

    if args.dry_run:
        print(f"\nDry run: would delete {total_edges} edge(s) and {len(junk_artists)} library_artist row(s). "
              f"Re-run without --dry-run to apply.")
        conn.close()
        return

    for a in junk_artists:
        cur.execute("DELETE FROM edges WHERE target_id = ?", (a["mf_artist_id"],))
        cur.execute("DELETE FROM library_artist WHERE mf_artist_id = ?", (a["mf_artist_id"],))

    conn.commit()
    print(f"\nDeleted {total_edges} edge(s) and {len(junk_artists)} library_artist row(s).")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE purge_junk_names.py ---
