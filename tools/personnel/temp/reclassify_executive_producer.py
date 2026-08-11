# --- START OF FILE reclassify_executive_producer.py ---
# ======================================================================
# One-off reclassification of already-committed "Executive Producer"/
# "Executive-Producer" edges to "Producer" -- John's established manual
# practice (2026-08-10): he's been hand-editing these to read "Producer"
# rather than treating them as a distinct A&R-flavored credit. Written
# before edge_normalizer.py's new role_aliases config (2026-08-10) started
# applying this rewrite at ingestion time, so this is a one-time catch-up
# for historical data, not something that needs to run again.
#
# Reuses normalize_personnel() -- the SAME atomizer/alias/junk-filter/
# classifier pipeline every ingestion path uses -- rather than a bespoke
# string replace, so a legacy combined row like "Arranger, Executive
# Producer" gets correctly split (Arranger survives untouched, Executive
# Producer becomes Producer) instead of being mishandled wholesale.
#
# A rewritten "Executive Producer" -> "Producer" atom can collide with an
# ALREADY-EXISTING real "Producer" edge for the exact same (source_id,
# target_id, evidence_scope, evidence_detail) -- e.g. someone credited as
# both "Producer" and "Executive Producer" separately on the same album.
# edge_store.upsert_edge() already handles this correctly (updates the
# existing row if the new confidence is >=, never creates a duplicate),
# so every write here goes through it rather than a raw INSERT.
#
# USAGE -- run by hand, against a COPY of the live database first:
#   python reclassify_executive_producer.py --db path\to\copy.db --dry-run
# Inspect the results, THEN (only with John's go-ahead) run for real:
#   python reclassify_executive_producer.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.personnel.edge_normalizer import normalize_personnel
from tools.personnel import edge_store

TARGET_RE = re.compile(r'executive[\s\-]producer', re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from common import config_handler
    config_handler.DB_PATH = args.db

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, source_type, source_id, target_type, target_id,
               role, provenance, evidence_scope, evidence_detail
        FROM edges WHERE role IS NOT NULL
    """)
    rows = cur.fetchall()

    matches = [r for r in rows if TARGET_RE.search(r["role"])]
    print(f"Scanned {len(rows)} edges rows with a role. Found {len(matches)} Executive Producer match(es).\n")

    if not matches:
        print("Nothing to reclassify.")
        conn.close()
        return

    for r in matches:
        atoms = normalize_personnel(r["role"])
        kept = ", ".join(f"{a['role']}->{a['relation_type']}" for a in atoms) if atoms else "(nothing survives)"
        print(f"  id={r['id']} role={r['role']!r} provenance={r['provenance']!r}\n    becomes: {kept}")

    if args.dry_run:
        print(f"\nDry run: would reclassify {len(matches)} row(s). Re-run without --dry-run to apply.")
        conn.close()
        return

    for r in matches:
        atoms = normalize_personnel(r["role"])
        cur.execute("DELETE FROM edges WHERE id = ?", (r["id"],))
        conn.commit()
        for atom in atoms:
            edge_store.upsert_edge(
                source_type=r["source_type"], source_id=r["source_id"],
                target_type=r["target_type"], target_id=r["target_id"],
                relation_type=atom["relation_type"], role=atom["role"],
                confidence=atom["confidence"], provenance=r["provenance"],
                evidence_scope=atom["evidence_scope"] or r["evidence_scope"],
                evidence_detail=atom["evidence_detail"] or r["evidence_detail"],
                weight=atom["weight"],
            )

    print(f"\nReclassified {len(matches)} row(s).")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE reclassify_executive_producer.py ---
