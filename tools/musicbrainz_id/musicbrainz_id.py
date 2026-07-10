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

    # Exact-phrase artist matching (artist:"...") is too brittle for real-
    # world naming variation -- an artist's as-credited name on a specific
    # release can differ from their canonical MB entity name (e.g. "Golden
    # Gate Quartet" credited vs. "The Golden Gate Jubilee Quartet" entity),
    # and phrase queries can't bridge that. Unquoted, parenthesized matching
    # (same style already used for the album title below) is more forgiving
    # and still lets the user pick the right result from the returned list.
    scrubbed_artist = re.sub(r'[:\-\(\)\[\]/]', ' ', artist)
    scrubbed_album = re.sub(r'[:\-\(\)\[\]/]', ' ', album)
    clean_query = f'artist:({" ".join(scrubbed_artist.split())}) AND release:({" ".join(scrubbed_album.split())})'

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
                "inc": "recordings+artist-credits+release-groups+work-rels+labels",
                "fmt": "json"
            }
        )
        res.raise_for_status()

        release = res.json()

        # Already present in this same response (inc=release-groups) --
        # zero extra HTTP calls. Feeds year_resolution_engine's tier 2
        # (release-group first-release-date) and is_compilation detection.
        rg_data = release.get("release-group", {}) or {}
        rg_first_release_date = rg_data.get("first-release-date", "")
        rg_secondary_types = rg_data.get("secondary-types", [])

        # Also free in this same response (inc=labels). Unlike Discogs'
        # equivalent label/catalog capture (discogs_evidence in
        # discogs_resolution_engine.py, explicitly hedged as "a lead, not
        # confirmed fact" because its release match is an unverified
        # top-search-hit), this release_id was already picked by the user
        # from search_musicbrainz()'s scored candidate list -- genuinely
        # confirmed data, no hedge needed. Feeds Personnel Scout's AI Web
        # Search tier (resolve_personnel_ai()) as release-disambiguating
        # context. First label-info entry only, same "take the primary"
        # convention as Discogs' labels[0].
        label_info = (release.get("label-info") or [None])[0] or {}
        mb_label_name = (label_info.get("label") or {}).get("name", "")
        mb_catalog_number = label_info.get("catalog-number", "")

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
                # Path relative to local_path, NOT bare f.name -- for a
                # box set, targets were found via recursive=True and can
                # live inside a "CD 1"/"CD 2" subfolder. A bare filename
                # here meant commit_ids_to_files() below reconstructed
                # `local_path / filename` pointing at a location that
                # doesn't exist (the real file is one level deeper),
                # silently failing old_path.exists() for every track in
                # a multi-disc box set -- the actual root cause of the
                # box-set "choke" John flagged 2026-07-08.
                "filename": str(f.relative_to(local_path).as_posix()),
                "title": f.stem
            })

        return jsonify({
            "status": "success",
            "artist_id": release.get("artist-credit", [{}])[0]
                .get("artist", {}).get("id", ""),
            "release_group_id": release.get("release-group", {}).get("id", ""),
            # `.get(key, default)`'s default only applies when the key is
            # MISSING -- MB releases commonly have "country": null (a real,
            # valid JSON null, not an absent key), which would otherwise
            # crash .upper()/[:4] on None and silently strand the UI on
            # "Retrieving MusicBrainz data..." forever (see except below).
            "country_code": (release.get("country") or "??").upper(),
            "release_year": (release.get("date") or "Unknown")[:4],
            "release_group_first_date": rg_first_release_date,
            "release_group_secondary_types": rg_secondary_types,
            "mb_label_name": mb_label_name,
            "mb_catalog_number": mb_catalog_number,
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
    release_group_first_date = data.get("release_group_first_date", "")
    release_group_secondary_types = data.get("release_group_secondary_types", [])
    mb_label_name = data.get("mb_label_name", "")
    mb_catalog_number = data.get("mb_catalog_number", "")

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

            # UFID holds the Recording ID (Picard convention -- the true,
            # cross-release identity anchor). track_id is release-specific
            # and gets its own TXXX field instead (see commit_engine.py's
            # matching physical-tag write for the same convention).
            if item.get("recording_id"):
                audio.delall("UFID")
                audio.add(UFID(
                    owner="http://musicbrainz.org",
                    data=item["recording_id"].encode("utf-8")
                ))

            tags = {
                "MusicBrainz Artist Id": item["artist_id"],
                "MusicBrainz Album Id": item["album_id"],
                "MusicBrainz Release Group Id": item["release_group_id"],
                "MusicBrainz Release Country": item["country_code"],
                "MusicBrainz Release Track Id": item.get("track_id"),
            }

            for desc, val in tags.items():
                if val:
                    audio.delall(f"TXXX:{desc}")
                    audio.add(TXXX(encoding=1, desc=desc, text=[str(val)]))

            if release_year != "Unknown":
                audio.delall("TDRC")
                audio.delall("TYER")
                audio.add(TYER(encoding=1, text=[str(release_year)]))

            # save() alone doesn't downgrade v2.4-native frames (e.g. TDRC ->
            # TYER) even when v2_version=3 is requested -- must call this first.
            audio.update_to_v23()
            audio.save(str(old_path), v2_version=3)

            # No zero-padding -- matches Unpack/Convert's own convention
            # (bitstream_engine.py's filing_id is a plain str(int), never
            # padded). This used to disagree with Stage 1's own naming,
            # so a file born "1 - ..." in Unpack/Convert would get
            # silently renamed to "01 - ..." here in Stage 2 -- the
            # actual source of the inconsistency John flagged 2026-07-08.
            t_num = str(item["track_num"])
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
        _update_manifest(
            local_path, mapping, release_year, artist_seed, album_seed,
            release_group_first_date, release_group_secondary_types,
            mb_label_name, mb_catalog_number
        )

    return jsonify({"status": "success", "summary": stats})


# =========================================================
# MANIFEST WRITER
# =========================================================
def _update_manifest(
    root, mapping, year, artist_seed, album_seed,
    release_group_first_date="", release_group_secondary_types=None,
    mb_label_name="", mb_catalog_number=""
):
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
            "filename": f"{item['track_num']} - "
                        f"{sanitize_filename(artist_seed)} - "
                        f"{sanitize_filename(item['target_title'])}.mp3",
            "title": item["target_title"],
            "mb_track_id": item.get("track_id", ""),
            "mb_recording_id": item.get("recording_id", ""),
            "mb_work_id": item.get("work_id", ""),
        })

    m.update({
        "artist_seed": m.get("artist_seed") or artist_seed,
        "album_seed": m.get("album_seed") or album_seed,
        "mb_artist_id": sample["artist_id"],
        "mb_album_id": sample["album_id"],
        "mb_release_group_id": sample["release_group_id"],
        "mb_release_country": sample["country_code"],
        "release_year": year,
        "mb_release_group_first_date": release_group_first_date,
        "mb_release_group_secondary_types": release_group_secondary_types or [],
        "mb_label_name": mb_label_name,
        "mb_catalog_number": mb_catalog_number,
        "is_physically_synced": True,
        "synced_at": datetime.now().isoformat()
    })

    manifest_path.write_text(json.dumps(m, indent=4), encoding="utf-8")