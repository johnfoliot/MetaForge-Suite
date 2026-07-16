# --- START OF FILE backfill_artist_mbids.py ---
# ======================================================================
# One-off batch backfill: resolves a real MusicBrainz artist MBID for
# every library_artist row currently missing one, via a live MB
# /ws/2/artist name search (same query-construction pattern as
# musicbrainz_id.py's release search). Confirmed live 2026-07-16 this
# is genuinely needed -- only 27 of 1,273 artists had mb_artist_id
# populated before this script; the rest never had a real MBID
# captured at all. `edges.target_id` is a pure SHA256 name-hash, not
# an MBID, so Personnel Bridge (see project_playlist_maker_vision
# memory) is currently entirely name-string-dependent -- this backfill
# is the fix for that, going through library_artist.mb_artist_id
# rather than touching edges.target_id or its dedup key at all.
#
# Auto-accepts a match only when it's genuinely unambiguous: top score
# >= AUTO_ACCEPT_MIN_SCORE AND at least AUTO_ACCEPT_MIN_GAP points
# clear of the next-best candidate. Confirmed live against three real
# names from this exact library before writing this threshold:
#   "John Lennon"    -> 100 vs 61 (gap 39)  -- clear, real match
#   "Alan Cohen"     -> 100 vs 98 (gap 2)   -- genuinely ambiguous
#   "James Lawrence" -> 100 vs 99 (gap 1)   -- genuinely ambiguous
# A bare score threshold alone would have wrongly auto-accepted both
# ambiguous cases; the gap check is what actually separates them.
#
# Anything not auto-accepted is written to a human-reviewable flat
# text file (REVIEW_FILE below), never guessed at. Each block embeds
# the artist's own mf_artist_id (the same hash used as edges.target_id)
# so apply_artist_mbid_review.py can target the exact row directly,
# without re-deriving or re-matching by name. See that script for how
# John's filled-in choices get applied back.
#
# Names with zero MB candidates at all are reported in the console
# summary and a short informational section at the end of the review
# file, but get no "CHOICE" block -- there's nothing to choose between.
#
# USAGE -- run by hand, against a COPY of the live database first:
#   python backfill_artist_mbids.py --db path\to\copy.db --dry-run
#   python backfill_artist_mbids.py --db path\to\copy.db
# Inspect the results, THEN (only with John's go-ahead) run for real:
#   python backfill_artist_mbids.py --db "C:\Users\John Foliot\AppData\Roaming\MetaForge\metaforge.db"
# ======================================================================
import argparse
import sqlite3
import sys
import time
import requests
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MB_API_URL = "https://musicbrainz.org/ws/2/artist"
MB_USER_AGENT = "MetaForge/1.0 (artist-mbid-backfill)"
MB_DELAY = 1.1  # matches musicbrainz_id.py's own rate-limit courtesy delay

AUTO_ACCEPT_MIN_SCORE = 95
AUTO_ACCEPT_MIN_GAP = 15

REVIEW_FILE = REPO_ROOT / "data" / "musicbrainz" / "artist_mbid_review.txt"


def search_artist(session, name):
    try:
        res = session.get(
            MB_API_URL,
            params={"query": f'artist:"{name}"', "fmt": "json", "limit": 5},
            timeout=10,
        )
        res.raise_for_status()
        return res.json().get("artists", []) or []
    except Exception as e:
        print(f"  [ERROR] lookup failed for {name!r}: {e}")
        return []


def get_credited_albums(cur, mf_artist_id):
    cur.execute(
        """
        SELECT DISTINCT lm.artist_name, lm.album_title
        FROM edges e JOIN library_master lm ON e.source_id = lm.mf_id
        WHERE e.target_id = ?
        """,
        (mf_artist_id,),
    )
    return [f"{r[0]} -- {r[1]}" for r in cur.fetchall()]


def format_candidate_line(idx, c):
    disamb = f" - {c['disambiguation']}" if c.get("disambiguation") else ""
    ctype = c.get("type") or "Unknown type"
    country = f", {c['country']}" if c.get("country") else ""
    return f"  {idx}. {c['name']} ({ctype}{country}){disamb} - score {c.get('score')} - MBID: {c['id']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="Path to the metaforge.db to operate on (use a COPY first)")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen without writing")
    args = parser.parse_args()

    # Real crash, found live 2026-07-16: Windows' console defaults to
    # cp1252, which can't encode plenty of real characters that show up
    # in artist names (a Unicode hyphen ‐, accented Latin letters,
    # etc.) -- the run died at item 523/1246 on a name containing one,
    # after 522 items had already processed fine. errors='replace' means
    # a name with an unencodable character prints with a placeholder
    # instead of crashing the whole run -- the DATA written is never
    # affected by this, only what gets shown on screen.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    cur.execute(
        "SELECT mf_artist_id, artist_name FROM library_artist "
        "WHERE mb_artist_id IS NULL OR mb_artist_id = '' ORDER BY artist_name"
    )
    targets = cur.fetchall()
    print(f"{len(targets)} artists need an MBID lookup.\n")

    session = requests.Session()
    session.headers.update({"User-Agent": MB_USER_AGENT})

    auto_accepted = 0
    flagged = 0
    no_match_names = []

    # Real bug, found live 2026-07-16: the review file used to only get
    # written once, at the very end of the whole loop -- when the crash
    # above hit at item 523, every one of the ~150 flagged entries found
    # in the first 522 items was lost, never persisted anywhere, even
    # though the auto-accepted DB writes (committed per-row, above) were
    # completely safe. Opening the file once here and writing each block
    # immediately as it's found means a future crash can only ever lose
    # the ONE in-flight lookup, never previously-found entries.
    review_fh = None
    if not args.dry_run:
        REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
        review_fh = open(REVIEW_FILE, "w", encoding="utf-8")

    for i, (mf_artist_id, name) in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {name}...", end=" ")
        candidates = search_artist(session, name)
        time.sleep(MB_DELAY)

        if not candidates:
            print("no MB match")
            no_match_names.append(name)
            continue

        top = candidates[0]
        top_score = top.get("score", 0) or 0
        second_score = (candidates[1].get("score", 0) or 0) if len(candidates) > 1 else 0
        gap = top_score - second_score

        if top_score >= AUTO_ACCEPT_MIN_SCORE and gap >= AUTO_ACCEPT_MIN_GAP:
            print(f"AUTO-ACCEPTED ({top['name']}, score {top_score}, gap {gap})")
            auto_accepted += 1
            if not args.dry_run:
                cur.execute(
                    "UPDATE library_artist SET mb_artist_id = ? WHERE mf_artist_id = ?",
                    (top["id"], mf_artist_id),
                )
                conn.commit()
        else:
            print(f"FLAGGED (top score {top_score}, gap {gap})")
            flagged += 1
            albums = get_credited_albums(cur, mf_artist_id)
            block = [
                f"=== {name} ===",
                f"[mf_artist_id: {mf_artist_id}]",
                f"Credited on: {', '.join(albums) if albums else 'unknown'}",
                "Candidates:",
            ]
            for idx, c in enumerate(candidates, 1):
                block.append(format_candidate_line(idx, c))
            block.append(f"  {len(candidates) + 1}. None of the above / skip")
            block.append("")
            block.append(">>> CHOICE: ")
            block.append("")
            if review_fh:
                review_fh.write("\n".join(block) + "\n")
                review_fh.flush()

    if review_fh and no_match_names:
        review_fh.write("=== No MusicBrainz match found (informational only, nothing to choose) ===\n")
        review_fh.write("\n".join(f"  - {n}" for n in no_match_names) + "\n")
    if review_fh:
        review_fh.close()

    print(f"\nDone. Auto-accepted: {auto_accepted}, flagged for review: {flagged}, no MB match: {len(no_match_names)}")
    if not args.dry_run and flagged:
        print(f"Wrote review file: {REVIEW_FILE}")
    elif args.dry_run:
        print(f"(dry run -- would write {flagged} flagged entries + {len(no_match_names)} no-match names to {REVIEW_FILE})")

    conn.close()


if __name__ == "__main__":
    main()
# --- END OF FILE backfill_artist_mbids.py ---
