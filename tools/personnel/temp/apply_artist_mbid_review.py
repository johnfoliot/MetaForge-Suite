# --- START OF FILE apply_artist_mbid_review.py ---
# ======================================================================
# One-off companion to backfill_artist_mbids.py: parses John's filled-in
# ">>> CHOICE:" answers out of the review text file that script wrote,
# and applies the chosen MBID to library_artist.mb_artist_id for each
# resolved block. Blocks left blank (or "skip") are left untouched --
# nothing is guessed, only what John explicitly picked gets written.
#
# Parses by the embedded [mf_artist_id: ...] line in each block, not by
# re-hashing the artist name, so there's no risk of a parsing mismatch
# silently targeting the wrong row.
#
# USAGE -- same COPY-first discipline as the backfill script:
#   python apply_artist_mbid_review.py --db path\to\copy.db --dry-run
#   python apply_artist_mbid_review.py --db path\to\copy.db
# Then, only with John's go-ahead:
#   python apply_artist_mbid_review.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REVIEW_FILE = REPO_ROOT / "data" / "musicbrainz" / "artist_mbid_review.txt"

BLOCK_RE = re.compile(
    r"=== (?P<name>.+?) ===\n"
    r"\[mf_artist_id: (?P<mf_artist_id>[0-9a-f]+)\]\n"
    r"Credited on: .*?\n"
    r"Candidates:\n"
    r"(?P<candidates>(?:  \d+\..*\n?)+)"
    r"\s*>>> CHOICE:\s*(?P<choice>\S*)",
    re.MULTILINE,
)
CANDIDATE_LINE_RE = re.compile(r"^  (\d+)\. .*?MBID: ([0-9a-f\-]+)\s*$", re.MULTILINE)


def parse_review_file(text):
    """
    Returns a list of (name, mf_artist_id, chosen_mbid_or_None, raw_choice)
    tuples. chosen_mbid is None for a blank/"skip" choice, or for a choice
    number pointing at the "None of the above / skip" line (which has no
    MBID to extract).
    """
    results = []
    for m in BLOCK_RE.finditer(text):
        name = m.group("name")
        mf_artist_id = m.group("mf_artist_id")
        raw_choice = m.group("choice").strip()
        candidates = dict(CANDIDATE_LINE_RE.findall(m.group("candidates")))

        chosen_mbid = None
        if raw_choice and raw_choice.lower() != "skip":
            chosen_mbid = candidates.get(raw_choice)  # None if it pointed at the "skip" line or was invalid

        results.append((name, mf_artist_id, chosen_mbid, raw_choice))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--review-file", default=str(REVIEW_FILE), help="Path to the filled-in review file")
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing")
    args = parser.parse_args()

    review_path = Path(args.review_file)
    if not review_path.exists():
        print(f"Review file not found: {review_path}")
        sys.exit(1)

    text = review_path.read_text(encoding="utf-8")
    parsed = parse_review_file(text)
    print(f"Found {len(parsed)} reviewed blocks in {review_path}.\n")

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    applied = 0
    skipped = 0
    unrecognized = 0

    for name, mf_artist_id, chosen_mbid, raw_choice in parsed:
        if chosen_mbid:
            print(f"  APPLY: {name} -> {chosen_mbid} (choice {raw_choice!r})")
            applied += 1
            if not args.dry_run:
                cur.execute(
                    "UPDATE library_artist SET mb_artist_id = ? WHERE mf_artist_id = ?",
                    (chosen_mbid, mf_artist_id),
                )
        elif not raw_choice or raw_choice.lower() == "skip":
            print(f"  skip: {name} (left blank / skip)")
            skipped += 1
        else:
            print(f"  [WARN] {name}: choice {raw_choice!r} didn't match a real candidate number -- left untouched")
            unrecognized += 1

    if not args.dry_run:
        conn.commit()

    print(f"\nApplied: {applied}, skipped: {skipped}, unrecognized choices: {unrecognized}")
    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE apply_artist_mbid_review.py ---
