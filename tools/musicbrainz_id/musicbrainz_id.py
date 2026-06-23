# ======================================================================
# MetaForge Studio: MusicBrainz Forensic Logic (Structural Sync Build)
# Build 2.25.0: Single-hop enriched release resolution (no recording hop)
# Location: MetaForge Suite\tools\musicbrainz_id\musicbrainz_id.py
# ======================================================================

import os
import time
import json
import re
import requests
from datetime import datetime
from pathlib import Path
from flask import request, jsonify
from mutagen.id3 import ID3, TXXX, UFID, TYER, TRCK, ID3NoHeaderError

from common import io_bridge

session = requests.Session()
BASE_URL = "https://musicbrainz.org/ws/2"
MB_DELAY = 1.1


# =========================================================
# HELPERS
# =========================================================
def natural_sort_key(s):
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r'(\d+)', s)
    ]


def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()


def get_mb_headers(env_path):
    email = "anonymous@metaforge.studio"

    if env_path and env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("USER_EMAIL="):
                    email = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass

    return {
        "User-Agent": f"MetaForgeStudio/1.0.0 ({email})",
        "Accept": "application/json"
    }


# =========================================================
# ENTRYPOINT
# =========================================================
def run_logic(action, tools_dir, env_path):
    session.headers.update(get_mb_headers(env_path))

    if action == "search":
        return search_musicbrainz()

    if action == "get_release_details":
        return get_release_details()

    if action == "get_folder_context":
        return get_folder_context()

    if action == "commit":
        return commit_ids_to_files(env_path)

    return jsonify({
        "status": "error",
        "message": f"Action '{action}' not implemented."
    })


# =========================================================
# CONTEXT
# =========================================================
def get_folder_context():
    data = request.json
    local_path = data.get("local_path")

    if not local_path:
        return jsonify({"status": "error", "message": "⚠️ No path provided."})

    manifest_path = Path(local_path) / "manifest.json"
    context = {"artist": "", "album": "", "track_count": 0}

    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            context = {
                "artist": m.get("artist_seed", ""),
                "album": m.get("album_seed", ""),
                "track_count": m.get("track_count", 0)
            }
        except Exception:
            pass

    return jsonify({"status": "success", "context": context})


# =========================================================
# SEARCH
# =========================================================
def search_musicbrainz():
    data = request.json
    artist = data.get("artist", "")
    album = data.get("album", "")

    scrubbed_album = re.sub(r'[:\-\(\)\[\]/]', ' ', album)
    clean_query = f'artist:"{artist}" AND release:({" ".join(scrubbed_album.split())})'

    try:
        time.sleep(MB_DELAY)

        res = session.get(
            f"{BASE_URL}/release",
            params={"query": clean_query, "fmt": "json", "limit": 25}
        )
        res.raise_for_status()
        result = res.json()

        releases = []
        for r in result.get("releases", []):
            releases.append({
                "id": r.get("id"),
                "score": r.get("score", "0"),
                "artist": r.get("artist-credit", [{}])[0].get("name", "Unknown"),
                "title": r.get("title", "Unknown"),
                "track_count": r.get("track-count", "0"),
                "year": r.get("date", "Unknown")[:4],
                "country_code": r.get("country", "??").lower()
            })

        return jsonify({"status": "success", "results": releases})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# =========================================================
# RELEASE DETAILS (SINGLE-HOP ENRICHED)
# =========================================================
def get_release_details():
    data = request.json
    release_id = data.get("release_id")
    local_path = Path(data.get("local_path"))

    try:
        time.sleep(MB_DELAY)

        res = session.get(
            f"{BASE_URL}/release/{release_id}",
            params={
                "inc": "recordings+artist-credits+release-groups",
                "fmt": "json"
            }
        )
        res.raise_for_status()

        release = res.json()

        remote_tracks = []

        for media in release.get("media", []):
            for track in media.get("tracks", []):

                recording = track.get("recording") or {}
                recording_id = recording.get("id", "")

                # Single-hop enrichment ONLY (no extra API calls)
                work_id = ""
                for rel in recording.get("relations", []):
                    rel_type = (rel.get("type") or "").lower()
                    if "work" in rel_type or "performance" in rel_type:
                        work = rel.get("work") or {}
                        work_id = work.get("id", "")
                        if work_id:
                            break

                remote_tracks.append({
                    "position": str(track.get("number", "")),
                    "title": recording.get("title", "Unknown"),

                    # UI contract (critical)
                    "track_id": track.get("id", ""),

                    # enrichment fields (must exist for manifest)
                    "recording_id": recording_id,
                    "work_id": work_id
                })

        local_tracks = []
        targets = io_bridge.get_audio_targets(local_path, recursive=True)
        targets.sort(key=lambda x: natural_sort_key(str(x.name)))

        for f in targets:
            local_tracks.append({
                "filename": str(f.name),
                "title": f.stem
            })

        return jsonify({
            "status": "success",
            "artist_id": release.get("artist-credit", [{}])[0]
                .get("artist", {}).get("id", ""),
            "release_group_id": release.get("release-group", {}).get("id", ""),
            "country_code": release.get("country", "??").upper(),
            "release_year": release.get("date", "Unknown")[:4],
            "remote_tracks": remote_tracks,
            "local_tracks": local_tracks
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# =========================================================
# COMMIT (UNCHANGED CONTRACT)
# =========================================================
def commit_ids_to_files(env_path):
    data = request.json

    local_path = Path(data.get("local_path"))
    mapping = data.get("mapping")

    artist_seed = data.get("artist_seed", "Unknown Artist")
    album_seed = data.get("album_seed", local_path.name)
    release_year = data.get("release_year", "Unknown")

    stats = {"success": 0, "failed": 0}

    for item in mapping:
        old_path = local_path / item["current_filename"]

        if not old_path.exists():
            stats["failed"] += 1
            continue

        try:
            try:
                audio = ID3(str(old_path))
            except ID3NoHeaderError:
                audio = ID3()

            audio.delall("TRCK")
            audio.add(TRCK(encoding=1, text=[str(item["track_num"])]))

            if item.get("track_id"):
                audio.delall("UFID")
                audio.add(UFID(
                    owner="http://musicbrainz.org",
                    data=item["track_id"].encode("utf-8")
                ))

            tags = {
                "MusicBrainz Artist Id": item["artist_id"],
                "MusicBrainz Album Id": item["album_id"],
                "MusicBrainz Release Group Id": item["release_group_id"],
                "MusicBrainz Release Country": item["country_code"]
            }

            for desc, val in tags.items():
                if val:
                    audio.delall(f"TXXX:{desc}")
                    audio.add(TXXX(encoding=1, desc=desc, text=[str(val)]))

            if release_year != "Unknown":
                audio.delall("TDRC")
                audio.delall("TYER")
                audio.add(TYER(encoding=1, text=[str(release_year)]))

            audio.save(str(old_path), v2_version=3)

            t_num = str(item["track_num"]).zfill(2)
            safe_artist = sanitize_filename(artist_seed)
            safe_title = sanitize_filename(item["target_title"])

            new_name = f"{t_num} - {safe_artist} - {safe_title}.mp3"
            new_path = old_path.parent / new_name

            if old_path != new_path:
                os.rename(str(old_path), str(new_path))

            stats["success"] += 1

        except Exception as e:
            print(f"Commit/Rename Failure: {e}")
            stats["failed"] += 1

    if stats["success"] > 0:
        _update_manifest(local_path, mapping, release_year, artist_seed, album_seed)

    return jsonify({"status": "success", "summary": stats})


# =========================================================
# MANIFEST WRITER
# =========================================================
def _update_manifest(root, mapping, year, artist_seed, album_seed):
    manifest_path = root / "manifest.json"

    m = {}
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    sample = mapping[0]

    m["mb_track_map"] = []

    for item in mapping:
        m["mb_track_map"].append({
            "position": item["track_num"],
            "filename": f"{str(item['track_num']).zfill(2)} - "
                        f"{sanitize_filename(artist_seed)} - "
                        f"{sanitize_filename(item['target_title'])}.mp3",
            "title": item["target_title"],
            "mb_track_id": item.get("track_id", ""),
            "mb_recording_id": item.get("recording_id", ""),
        })

    m.update({
        "artist_seed": m.get("artist_seed") or artist_seed,
        "album_seed": m.get("album_seed") or album_seed,
        "mb_artist_id": sample["artist_id"],
        "mb_album_id": sample["album_id"],
        "mb_release_group_id": sample["release_group_id"],
        "mb_release_country": sample["country_code"],
        "release_year": year,
        "is_physically_synced": True,
        "synced_at": datetime.now().isoformat()
    })

    manifest_path.write_text(json.dumps(m, indent=4), encoding="utf-8")