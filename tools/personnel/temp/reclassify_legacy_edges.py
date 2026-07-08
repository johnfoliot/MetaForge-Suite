# --- START OF FILE reclassify_legacy_edges.py ---
# ======================================================================
# One-off reclassification for `edges` rows written before this project's
# fixes landed 2026-07-08 (see edge_store.py, album_engine.py's rewritten
# _save_album, personnel_engine.py's _add_personnel).
#
# Two separate historical write paths bypassed edge_normalizer.classify_role()
# and wrote a raw/non-canonical string directly into relation_type:
#   1. ~1,210 rows, provenance='MetaForge' -- Album Editor's old _save_album(),
#      which used its own ROLE_MAP + "Vocal"/"Instrument" substring checks
#      (now replaced by classify_role()).
#   2. ~30 older rows, provenance values like "Engineer: A. B. Lincoln" --
#      an even earlier import path, same underlying defect.
# In both cases the `role` column itself holds the original, correct role
# text (confirmed by inspecting live data before writing this script) --
# only `relation_type`/`confidence` are wrong. This script re-runs each
# row's own `role` text through the SAME classify_role() every other write
# path now uses, and updates relation_type/confidence in place.
#
# evidence_scope/evidence_detail are NOT backfilled -- the original scraped
# text (which may have carried a track-number qualifier) no longer exists
# for these rows, only the flattened role string survives. Left NULL, which
# is honest, not a bug in this script.
#
# Also collapses true duplicates (identical source_id/target_id/role) that
# survived from the era before edge_store.upsert_edge() existed -- confirmed
# via live query: exactly 2 such groups as of 2026-07-08. Keeps whichever
# row has the higher id (most recently written), deletes the rest.
#
# USAGE -- run by hand, against a COPY of the live database first:
#   python reclassify_legacy_edges.py --db path\to\copy.db --dry-run
#   python reclassify_legacy_edges.py --db path\to\copy.db
# Inspect the results, THEN (only with John's go-ahead) run for real:
#   python reclassify_legacy_edges.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_constants import RelationType
from tools.personnel.edge_normalizer import load_config, classify_role

CANONICAL_VALUES = {rt.value for rt in RelationType}


def dedupe_exact_repeats(cur, dry_run):
    cur.execute("""
        SELECT source_id, target_id, role, GROUP_CONCAT(id) AS ids
        FROM edges
        WHERE source_type = 'album'
        GROUP BY source_id, target_id, role
        HAVING COUNT(*) > 1
    """)
    groups = cur.fetchall()
    print(f"\nFound {len(groups)} exact-duplicate (source_id, target_id, role) groups.")

    removed = 0
    for g in groups:
        ids = sorted(int(i) for i in g["ids"].split(","))
        keep, drop = ids[-1], ids[:-1]
        print(f"  keeping id={keep}, dropping ids={drop} ({g['role']!r})")
        if not dry_run:
            cur.executemany("DELETE FROM edges WHERE id = ?", [(i,) for i in drop])
        removed += len(drop)

    return removed


def reclassify(cur, dry_run):
    placeholders = ",".join("?" for _ in CANONICAL_VALUES)
    cur.execute(f"""
        SELECT id, role, relation_type, provenance
        FROM edges
        WHERE relation_type NOT IN ({placeholders})
    """, tuple(CANONICAL_VALUES))
    rows = cur.fetchall()

    print(f"Found {len(rows)} edges rows with a non-canonical relation_type.")

    by_provenance = {}
    for r in rows:
        by_provenance[r["provenance"]] = by_provenance.get(r["provenance"], 0) + 1
    for prov, count in sorted(by_provenance.items(), key=lambda x: -x[1])[:15]:
        print(f"  provenance={prov!r}: {count} rows")

    config = load_config()
    updated = 0

    for r in rows:
        role_text = r["role"] or r["relation_type"]
        new_relation_type, new_confidence = classify_role(role_text, config)

        if dry_run:
            print(f"  id={r['id']}: relation_type {r['relation_type']!r} -> {new_relation_type!r} "
                  f"(confidence={new_confidence}) [role={role_text!r}]")
        else:
            cur.execute(
                "UPDATE edges SET relation_type = ?, confidence = ? WHERE id = ?",
                (new_relation_type, new_confidence, r["id"])
            )
        updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    dupes_removed = dedupe_exact_repeats(cur, args.dry_run)
    reclassified = reclassify(cur, args.dry_run)

    if args.dry_run:
        print(f"\nDry run: would remove {dupes_removed} duplicate rows and "
              f"reclassify {reclassified} rows. Re-run without --dry-run to apply.")
    else:
        conn.commit()
        print(f"\nRemoved {dupes_removed} duplicate rows, reclassified {reclassified} rows.")

    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE reclassify_legacy_edges.py ---
