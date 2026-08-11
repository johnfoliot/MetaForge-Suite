# --- START OF FILE purge_junk_edges.py ---
# ======================================================================
# One-off purge of already-committed junk-role edges (photography, album/
# package design, artwork, liner notes, etc.) written before
# edge_normalizer.is_junk_role() started filtering these at ingestion
# time (2026-07-08). Going forward, junk never gets created in the first
# place, so this is a one-time cleanup of historical debt, not something
# that needs to run again.
#
# Reuses the exact same junk_roles denylist from performance.json via
# edge_normalizer.is_junk_role() -- not a separate/duplicated list, so
# it can never drift out of sync with what new ingestion already filters.
#
# Also cleans up any library_artist row left with zero remaining edges
# after its only credit(s) turn out to be junk (e.g. a photographer with
# no other real credit anywhere) -- same orphan-cleanup pattern already
# used in album_engine.py's _save_album().
#
# IMPORTANT -- caught during dry-run testing, not assumed: some legacy
# rows (predating this session's atomization fixes) store a whole
# COMBINED multi-role string as one row, e.g. "Assistant Producer,
# Engineer, Guitar, Photography, Pilot Vocals". A naive substring match
# on the full string would delete that entire row -- including three
# genuinely valuable credits -- just because "Photography" also appears
# in it. This script re-runs each junk-matching row's role text through
# normalize_personnel() (the same atomizer/classifier/junk-filter every
# other ingestion path uses): if that yields NOTHING, the row really was
# fully junk and gets deleted outright; if it yields ONE OR MORE surviving
# atoms, the old combined row is replaced by properly atomized edges for
# just the real credits, not deleted wholesale. This script does NOT
# re-atomize rows that don't match the junk filter at all (e.g. a clean
# "Guitar, Bass" combined row) -- that's a separate legacy-atomization
# question, out of scope here.
#
# USAGE -- run by hand, against a COPY of the live database first:
#   python purge_junk_edges.py --db path\to\copy.db --dry-run
#   python purge_junk_edges.py --db path\to\copy.db
# Inspect the results, THEN (only with John's go-ahead) run for real:
#   python purge_junk_edges.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import is_junk_role, load_config, normalize_personnel
from tools.personnel import edge_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    parser.add_argument(
        "--exclude-ids", default="",
        help="Comma-separated edges.id values to skip even if they match the junk-role filter -- "
             "for known false-positive substring collisions (e.g. 'stylist' matching 'Performer "
             "[The Stylistics]'), confirmed by hand from a prior --dry-run before excluding."
    )
    args = parser.parse_args()
    exclude_ids = {int(x) for x in args.exclude_ids.split(",") if x.strip()}

    # edge_store.upsert_edge() (reused below for the partial-junk repair
    # path) goes through db_engine.execute_query(), which opens its own
    # connection via common.config_handler.DB_PATH -- NOT whatever --db
    # points at. Without this, upsert_edge() calls would silently write
    # to the REAL live database even during a --db <copy> test run,
    # defeating the entire point of testing against a copy first.
    from common import config_handler
    config_handler.DB_PATH = args.db

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    config = load_config()

    cur.execute("""
        SELECT id, source_type, source_id, target_type, target_id,
               role, provenance, relation_type
        FROM edges WHERE role IS NOT NULL
    """)
    rows = cur.fetchall()

    junk_rows = [r for r in rows if is_junk_role(r["role"], config) and r["id"] not in exclude_ids]
    excluded_count = sum(1 for r in rows if is_junk_role(r["role"], config) and r["id"] in exclude_ids)
    print(f"Scanned {len(rows)} edges rows with a role. Found {len(junk_rows)} whole/partial junk-role matches"
          + (f" ({excluded_count} excluded via --exclude-ids).\n" if excluded_count else ".\n"))

    if not junk_rows:
        print("Nothing to purge.")
        conn.close()
        return

    # Re-atomize each match: a row that's fully junk once split (e.g. bare
    # "Photography", or "Art Direction, Design") gets deleted outright.
    # A row where junk was mixed in with real credits (e.g. "Assistant
    # Producer, Engineer, Guitar, Photography, Pilot Vocals") gets its
    # real atoms preserved -- NOT deleted wholesale just because one part
    # of the combined string matched the junk list.
    fully_junk = []
    partially_junk = []

    for r in junk_rows:
        atoms = normalize_personnel(r["role"])
        if not atoms:
            fully_junk.append(r)
        else:
            partially_junk.append((r, atoms))

    print(f"Fully junk -- delete outright ({len(fully_junk)}):")
    for r in fully_junk:
        print(f"  id={r['id']} role={r['role']!r} provenance={r['provenance']!r}")

    print(f"\nPartially junk -- replace with surviving real credits ({len(partially_junk)}):")
    for r, atoms in partially_junk:
        kept = ", ".join(f"{a['role']}->{a['relation_type']}" for a in atoms)
        print(f"  id={r['id']} role={r['role']!r}\n    keeping: {kept}")

    if args.dry_run:
        fully_junk_ids = [r["id"] for r in fully_junk]
        would_orphan = 0
        if fully_junk_ids:
            placeholders = ",".join("?" for _ in fully_junk_ids)
            for aid in {r["target_id"] for r in fully_junk}:
                cur.execute(
                    f"SELECT COUNT(*) FROM edges WHERE target_id = ? AND id NOT IN ({placeholders})",
                    (aid, *fully_junk_ids)
                )
                if cur.fetchone()[0] == 0:
                    would_orphan += 1
        total_kept_atoms = sum(len(atoms) for _, atoms in partially_junk)
        print(f"\nDry run: would delete {len(fully_junk)} fully-junk edges ({would_orphan} now-orphaned "
              f"library_artist rows), and replace {len(partially_junk)} partially-junk rows with "
              f"{total_kept_atoms} real atomic credits. Re-run without --dry-run to apply.")
        conn.close()
        return

    for r in fully_junk:
        cur.execute("DELETE FROM edges WHERE id = ?", (r["id"],))

    for r, atoms in partially_junk:
        cur.execute("DELETE FROM edges WHERE id = ?", (r["id"],))

    conn.commit()

    for r, atoms in partially_junk:
        for atom in atoms:
            edge_store.upsert_edge(
                source_type=r["source_type"], source_id=r["source_id"],
                target_type=r["target_type"], target_id=r["target_id"],
                relation_type=atom["relation_type"], role=atom["role"],
                confidence=atom["confidence"], provenance=r["provenance"],
                evidence_scope=atom["evidence_scope"], evidence_detail=atom["evidence_detail"],
                weight=atom["weight"],
            )

    fully_junk_ids = [r["id"] for r in fully_junk]
    orphaned = 0
    if fully_junk_ids:
        for aid in {r["target_id"] for r in fully_junk}:
            cur.execute("SELECT 1 FROM edges WHERE target_id = ? LIMIT 1", (aid,))
            if not cur.fetchone():
                cur.execute("DELETE FROM library_artist WHERE mf_artist_id = ?", (aid,))
                orphaned += 1
    conn.commit()

    total_kept_atoms = sum(len(atoms) for _, atoms in partially_junk)
    print(f"\nDeleted {len(fully_junk)} fully-junk edges, replaced {len(partially_junk)} partially-junk rows "
          f"with {total_kept_atoms} real atomic credits, removed {orphaned} orphaned library_artist rows.")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE purge_junk_edges.py ---
