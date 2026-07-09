# --- START OF FILE audit_recording_ids.py ---
# Role: One-off audit script, NOT part of the app's tool suite. Checks
# every distinct tracks.mb_track_id in the live database against
# MusicBrainz's own API to find recording IDs that no longer resolve
# (John, 2026-07-09 -- caught live via a real "Recording not found" MB
# Submit failure, root-caused to a stale mb_track_id: MusicBrainz 404'd
# on it directly, while a live search found the same song under a
# different, currently-valid ID).
#
# Read-only. Never writes to the database -- a 404 tells you an ID is
# dead, not what the correct replacement is; that needs the same kind
# of individual "search and confirm" judgment call used for the one
# track already fixed by hand, not an automated guess-and-replace that
# risks picking the wrong match for an ambiguous title.
#
# Physical Location: \tools\musicbrainz_id\temp\audit_recording_ids.py
# ======================================================================
import sys
import json
import time
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "intelli-tagger" / "engines"))

from common import config_handler  # noqa: E402
from mb_resolution_engine import MBResolutionEngine  # noqa: E402
import requests  # noqa: E402

REPORT_PATH = config_handler.DATA_DIR / "musicbrainz" / "stale_recording_ids_report.txt"


def main():
    conn = sqlite3.connect(str(config_handler.DB_PATH))
    conn.row_factory = sqlite3.Row

    # mb_recording_id, NOT mb_track_id -- the `tracks` table has two
    # separate, correctly-distinct MusicBrainz ID columns (Track entity
    # vs Recording entity; only the latter is valid at MB's
    # /recording/{id} endpoint). This script originally checked the
    # wrong one, which would have reported nearly the whole library as
    # "stale" even though the real problem was a single wrong-column
    # read in musicbrainz_submit.py, not bad data (John, 2026-07-09).
    rows = conn.execute("""
        SELECT mb_recording_id, MIN(file_path) AS sample_path, MIN(title) AS sample_title, MIN(mf_artist_id) AS artist_id
        FROM tracks
        WHERE mb_recording_id IS NOT NULL AND mb_recording_id != ''
        GROUP BY mb_recording_id
        ORDER BY sample_path
    """).fetchall()

    total = len(rows)
    print(f"Auditing {total} distinct recording IDs against live MusicBrainz (1 req/sec, ~{total/60:.0f} min)...")

    mb = MBResolutionEngine(rate_limit_delay=1.0)
    stale = []
    errors = []

    for i, row in enumerate(rows, 1):
        rid = row["mb_recording_id"]
        try:
            mb._get(f"recording/{rid}", {})
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 404:
                stale.append({"mb_recording_id": rid, "sample_path": row["sample_path"], "sample_title": row["sample_title"]})
                print(f"[{i}/{total}] STALE: {rid} ({row['sample_title']})")
            else:
                errors.append({"mb_recording_id": rid, "sample_path": row["sample_path"], "status": status})
                print(f"[{i}/{total}] ERROR {status}: {rid}")
        except Exception as ex:
            errors.append({"mb_recording_id": rid, "sample_path": row["sample_path"], "status": str(ex)})
            print(f"[{i}/{total}] ERROR: {rid} -- {ex}")

        if i % 100 == 0:
            print(f"--- progress: {i}/{total}, {len(stale)} stale so far ---")

    conn.close()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(f"Recording ID audit -- {total} distinct IDs checked\n")
        f.write(f"{len(stale)} stale (404), {len(errors)} errors/skipped\n\n")
        f.write("=== STALE (recording no longer exists on MusicBrainz) ===\n")
        for s in stale:
            f.write(json.dumps(s) + "\n")
        f.write("\n=== ERRORS (not confirmed stale, transient/other failure) ===\n")
        for e in errors:
            f.write(json.dumps(e) + "\n")

    print(f"\nDone. {len(stale)} stale, {len(errors)} errors. Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
# --- END OF FILE audit_recording_ids.py ---
