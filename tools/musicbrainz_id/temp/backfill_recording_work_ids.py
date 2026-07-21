# ======================================================================
# MetaForge one-off: mb_recording_id / mb_work_id backfill
# ======================================================================
# Scope, confirmed via live DB audit 2026-07-20: 1,046 tracks across 90
# albums were processed before the 2026-07-03 "UFID/mb_recording_id swap"
# fix and never got a recording_id (or work_id) backfilled -- that fix was
# forward-looking only. Of those 90 albums, 83 were already correctly
# matched to a specific MusicBrainz release (they have a real mb_track_id
# on every track) -- for those, re-fetching recording_id/work_id is pure
# enrichment against an already-confirmed release, no new search or
# disambiguation needed, and no risk of a wrong-album match. The other 7
# albums have at least one never-matched track and are deliberately
# EXCLUDED here -- those need a human to actually search/confirm a
# release via the real MusicBrainz ID tool, not a backfill script.
#
# One MB API call per ALBUM (not per track) -- release-level inc=
# recordings+work-rels returns every track's recording_id and work_id
# (via recording.relations, same extraction logic as musicbrainz_id.py's
# get_release_details()) in a single response, matched back to local
# tracks by mb_track_id (exact ID match, already 100% reliable per the
# audit -- no fuzzy title matching needed).
#
# Non-destructive: only writes mb_recording_id/mb_work_id when the local
# row is currently empty. Physical file gets the UFID tag written for
# mb_recording_id (matching the app's Picard-convention writer everywhere
# else); mb_work_id is DB-only, matching this codebase's existing
# convention (commit_engine.py's _write_physical_tags() never writes it
# to a physical tag either).
import re
import sys
import time
import sqlite3
import argparse
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler, tag_engine

BASE_URL = "https://musicbrainz.org/ws/2"
MB_DELAY = 1.1
ANOMALY_LOG = PROJECT_ROOT / "data" / "musicbrainz" / "recording_work_id_backfill_anomalies.txt"

session = requests.Session()


def get_mb_headers():
    email = "anonymous@metaforge.studio"
    env_path = config_handler.ENV_PATH
    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("USER_EMAIL="):
                    email = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    return {
        "User-Agent": f"MetaForgeStudio/1.0.0-backfill ({email})",
        "Accept": "application/json",
    }


def get_batch_safe_albums(cur):
    def has(col):
        return f"{col} IS NOT NULL AND {col} != '' AND {col} != 'None'"

    cur.execute(f"""
        SELECT lm.mf_id, lm.artist_name, lm.album_title, lm.mb_album_id
        FROM library_master lm
        JOIN tracks t ON t.mf_id = lm.mf_id
        WHERE lm.mb_album_id IS NOT NULL AND lm.mb_album_id != '' AND lm.mb_album_id != 'None'
        GROUP BY lm.mf_id
        HAVING
            SUM(CASE WHEN {has('t.mb_track_id')} AND NOT ({has('t.mb_recording_id')}) THEN 1 ELSE 0 END) > 0
            AND SUM(CASE WHEN NOT ({has('t.mb_track_id')}) AND NOT ({has('t.mb_recording_id')}) THEN 1 ELSE 0 END) = 0
        ORDER BY lm.artist_name, lm.album_title
    """)
    return cur.fetchall()


def fetch_release_recording_work_ids(mb_album_id):
    """
    Returns (by_track_id, by_position) -- two views of the same data.
    by_track_id: {mb_track_id: {"recording_id", "work_id", "track_id"}}
    by_position: {int position: {"recording_id", "work_id", "track_id"}}

    Real gap found live 2026-07-20: a release's own MusicBrainz "track"
    identifiers (distinct from the more stable "recording" identifiers)
    can get regenerated when an editor touches the tracklist -- confirmed
    directly against a real affected release (The Staple Singers' "Amen!"):
    same release, same recording titles, completely different track IDs
    than what was stored locally from the original match. Position within
    the medium is the stable fallback -- it isn't a retracklisting, just
    internal ID churn, so physical track order is still trustworthy.
    """
    res = session.get(
        f"{BASE_URL}/release/{mb_album_id}",
        params={"inc": "recordings+work-rels", "fmt": "json"},
        headers=get_mb_headers(),
        timeout=15,
    )
    res.raise_for_status()
    release = res.json()

    by_track_id = {}
    by_position = {}
    for media in release.get("media", []):
        for track in media.get("tracks", []):
            recording = track.get("recording") or {}
            recording_id = recording.get("id", "")

            work_id = ""
            for rel in recording.get("relations", []):
                rel_type = (rel.get("type") or "").lower()
                if "work" in rel_type or "performance" in rel_type:
                    work = rel.get("work") or {}
                    work_id = work.get("id", "")
                    if work_id:
                        break

            track_id = track.get("id", "")
            entry = {"recording_id": recording_id, "work_id": work_id, "track_id": track_id}

            if track_id:
                by_track_id[track_id] = entry

            position = track.get("position")
            if position is not None:
                try:
                    by_position[int(position)] = entry
                except (TypeError, ValueError):
                    pass

    return by_track_id, by_position


def run(db_path, dry_run):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    albums = get_batch_safe_albums(cur)
    print(f"{len(albums)} batch-safe albums to process (dry_run={dry_run})")

    ANOMALY_LOG.parent.mkdir(parents=True, exist_ok=True)
    anomaly_f = open(ANOMALY_LOG, "a", encoding="utf-8")

    stats = {
        "albums_ok": 0, "albums_failed": 0,
        "tracks_updated_exact": 0, "tracks_updated_position_fallback": 0,
        "tracks_unmatched": 0,
    }

    for idx, album in enumerate(albums, 1):
        mf_id, artist, title, mb_album_id = album["mf_id"], album["artist_name"], album["album_title"], album["mb_album_id"]
        print(f"[{idx}/{len(albums)}] {artist} -- {title}")

        try:
            time.sleep(MB_DELAY)
            by_track_id, by_position = fetch_release_recording_work_ids(mb_album_id)
        except Exception as e:
            print(f"  FAILED to fetch release {mb_album_id}: {e}")
            anomaly_f.write(f"ALBUM FETCH FAILED | {artist} -- {title} | mf_id={mf_id} | mb_album_id={mb_album_id} | {e}\n")
            anomaly_f.flush()
            stats["albums_failed"] += 1
            continue

        cur.execute(
            "SELECT file_path, mb_track_id, mb_recording_id, mb_work_id FROM tracks WHERE mf_id = ?",
            (mf_id,),
        )
        local_tracks = cur.fetchall()

        for lt in local_tracks:
            local_track_id = lt["mb_track_id"]
            if not local_track_id or local_track_id == "None":
                continue

            remote = by_track_id.get(local_track_id)
            used_fallback = False

            if not remote:
                # Real gap found live: the release's own track IDs can drift
                # (regenerated on MB's side since the original match) even
                # though the release and recordings are unquestionably the
                # same. Position within the medium is stable in that case --
                # not a retracklisting, just internal ID churn.
                pos_match = re.match(r'^0*(\d+)', Path(lt["file_path"]).stem)
                local_position = int(pos_match.group(1)) if pos_match else None
                remote = by_position.get(local_position) if local_position is not None else None
                used_fallback = remote is not None

            if not remote:
                stats["tracks_unmatched"] += 1
                anomaly_f.write(
                    f"TRACK NOT FOUND IN FRESH MB RESPONSE (id or position) | {artist} -- {title} | "
                    f"{Path(lt['file_path']).name} | mb_track_id={local_track_id}\n"
                )
                anomaly_f.flush()
                continue

            needs_recording = not lt["mb_recording_id"] or lt["mb_recording_id"] in (None, "", "None")
            needs_work = not lt["mb_work_id"] or lt["mb_work_id"] in (None, "", "None")
            # Position-fallback means the stored mb_track_id is confirmed
            # stale (that's WHY it didn't match) -- refresh it to the
            # release's current track ID as a free side effect of already
            # having fetched it, rather than leaving known-wrong data behind.
            needs_track_id_refresh = used_fallback and remote["track_id"] and remote["track_id"] != local_track_id

            if not needs_recording and not needs_work and not needs_track_id_refresh:
                continue

            new_recording_id = remote["recording_id"] if needs_recording and remote["recording_id"] else lt["mb_recording_id"]
            new_work_id = remote["work_id"] if needs_work and remote["work_id"] else lt["mb_work_id"]
            new_track_id = remote["track_id"] if needs_track_id_refresh else local_track_id

            tag = "[position fallback]" if used_fallback else "[exact id match]"
            if dry_run:
                print(f"    would update {Path(lt['file_path']).name} {tag}: recording_id={new_recording_id!r} work_id={new_work_id!r}" + (f" track_id={new_track_id!r}" if needs_track_id_refresh else ""))
                if used_fallback:
                    stats["tracks_updated_position_fallback"] += 1
                else:
                    stats["tracks_updated_exact"] += 1
                continue

            cur.execute(
                "UPDATE tracks SET mb_recording_id = ?, mb_work_id = ?, mb_track_id = ? WHERE file_path = ?",
                (new_recording_id, new_work_id, new_track_id, lt["file_path"]),
            )
            conn.commit()

            f_path = Path(lt["file_path"])
            if f_path.exists() and needs_recording and remote["recording_id"]:
                try:
                    tag_engine.update_tags(str(f_path), {"mb_recording_id": remote["recording_id"]})
                except Exception as e:
                    print(f"    tag write failed for {f_path.name}: {e}")

            if used_fallback:
                stats["tracks_updated_position_fallback"] += 1
            else:
                stats["tracks_updated_exact"] += 1

        stats["albums_ok"] += 1

    anomaly_f.close()

    print()
    print("=== SUMMARY ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if stats["tracks_unmatched"] > 0 or stats["albums_failed"] > 0:
        print(f"  Anomalies logged to: {ANOMALY_LOG}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(config_handler.DB_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run(Path(args.db), args.dry_run)
