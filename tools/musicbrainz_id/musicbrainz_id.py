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
from flask import request, jsonify, Response, stream_with_context
from mutagen.id3 import ID3, TXXX, UFID, TYER, TRCK, ID3NoHeaderError

from common import io_bridge
from common import mb_client
from common.mf_events import event, signal, run_stream   # v2 event stream (Phase 0.3)

# All MusicBrainz traffic goes through common/mb_client.py (shared pace,
# retries on "busy", timeouts). Only the per-user User-Agent lives here.
_mb_headers = {}


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


def _own_title(path):
    """The title a file already has: its title tag, else the title part of
    its "Track - Artist - Title" file name, else the whole name.
    For a file with no matching MusicBrainz track (a bonus track that isn't
    on the chosen release). Until 2026-11-17 such files were renamed and
    tagged "Unknown Title", losing their real title (17 tracks, John)."""
    try:
        tit = ID3(str(path)).get("TIT2")
        text = (tit.text[0] if tit and tit.text else "").strip()
        if text and text != "Unknown Title":
            return text
    except Exception:
        pass
    parts = path.stem.split(" - ", 2)
    return parts[2].strip() if len(parts) == 3 and parts[2].strip() else path.stem


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
    _mb_headers.update(get_mb_headers(env_path))

    if action == "search":
        return search_musicbrainz()

    if action == "get_release_details":
        return get_release_details()

    if action == "get_folder_context":
        return get_folder_context()

    if action == "commit":
        # v2: one event per file, streamed to the screen's Activity log and
        # written to the album's MetaForge.log (common/mf_events.py).
        data = request.json or {}
        return Response(
            stream_with_context(run_stream(commit_ids_to_files(data), "MusicBrainz IDs",
                                           log_root=data.get("local_path"))),
            mimetype="application/x-ndjson"
        )

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
        res = mb_client.get(
            "release",
            params={"query": clean_query, "limit": 25},
            headers=_mb_headers,
        )
        result = res.json()

        releases = []
        for r in result.get("releases", []):
            # MB's release search already returns a "media" array natively
            # (no extra inc= params needed, confirmed live) -- one entry
            # per physical/digital medium, each with its own "format"
            # ("CD", "Digital Media", "Vinyl", etc.). A multi-disc release
            # has multiple media entries; joined with "+" rather than
            # picking just the first, so a real 2xCD release reads as
            # "CD+CD" instead of silently dropping a disc. "Digital Media"
            # shortened to "Digital" to fit the narrow column -- every
            # other MB format string is left exactly as MB returns it,
            # not guessed at or abbreviated further.
            formats = [m.get("format") or "Unknown" for m in (r.get("media") or [])]
            formats = ["Digital" if f == "Digital Media" else f for f in formats]
            releases.append({
                "id": r.get("id"),
                "score": r.get("score", "0"),
                "artist": r.get("artist-credit", [{}])[0].get("name", "Unknown"),
                "title": r.get("title", "Unknown"),
                "format": "+".join(formats) if formats else "Unknown",
                "track_count": r.get("track-count", "0"),
                "year": r.get("date", "Unknown")[:4],
                "country_code": r.get("country", "??").lower()
            })

        return jsonify({"status": "success", "results": releases})

    except mb_client.MusicBrainzUnavailable as e:
        # Distinct from "no matches": the UI must never show a failed
        # search as an empty result (John's report, 2026-11-13).
        return jsonify({"status": "error", "reason": "unavailable", "message": str(e)})
    except Exception as e:
        return jsonify({"status": "error", "reason": "failed", "message": f"MusicBrainz search failed: {e}"})


# =========================================================
# RELEASE DETAILS (SINGLE-HOP ENRICHED)
# =========================================================
def get_release_details():
    data = request.json
    release_id = data.get("release_id")
    local_path = Path(data.get("local_path"))

    try:
        res = mb_client.get(
            f"release/{release_id}",
            params={"inc": "recordings+artist-credits+release-groups+work-rels+labels"},
            headers=_mb_headers,
        )

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

                # MB attaches its own artist-credit to the RECORDING
                # whenever a track's real performer differs from the
                # release's overall artist-credit -- exactly how Various
                # Artists compilations are modelled (already free in this
                # response via inc=artist-credits, zero extra calls). Empty
                # for a normal single-artist release, where commit_ids_to_
                # files() below falls back to the release-level artist_seed.
                # Real bug found live 2026-07-16: this was being fetched
                # and immediately discarded, so every track on a VA
                # compilation got renamed AND identity-hashed under the
                # single "Various Artists" filing name.
                track_artist_credit = recording.get("artist-credit") or []
                track_artist = track_artist_credit[0].get("name", "") if track_artist_credit else ""

                remote_tracks.append({
                    "position": str(track.get("number", "")),
                    "title": recording.get("title", "Unknown"),

                    # UI contract (critical)
                    "track_id": track.get("id", ""),

                    # enrichment fields (must exist for manifest)
                    "recording_id": recording_id,
                    "work_id": work_id,
                    "artist": track_artist
                })

        # The ARTIST's own home country (where a band formed / a solo
        # artist's nationality) -- a distinct concept from this release's
        # own "country" above (just wherever this particular pressing was
        # issued). John's report, 2026-08-01: Personnel Bridge/IPM needs
        # the artist's home country, not per-release distribution data --
        # he was manually overriding the release-country field for this
        # every time. One extra call, made once per album match (not per
        # track); missing/failed lookup is not fatal, just leaves this
        # blank and the caller falls back to release-country/AI guess.
        mb_artist_id = release.get("artist-credit", [{}])[0].get("artist", {}).get("id", "")
        mb_artist_country = ""
        if mb_artist_id:
            try:
                artist_res = mb_client.get(f"artist/{mb_artist_id}", headers=_mb_headers)
                mb_artist_country = (artist_res.json().get("country") or "").upper()
            except Exception:
                pass

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
            "artist_country": mb_artist_country,
            # For the MetaForge.log "MusicBrainz ID" audit block (John's
            # request, 2026-08-08) -- "Version Selected"/"Format" are the
            # exact fields already shown per-row in the search-results
            # table (see search_musicbrainz()'s own "format" computation
            # below), just re-derived here since the release-details
            # response is what actually reaches commit time, not the
            # search results the user clicked days/weeks earlier.
            "release_title": release.get("title", ""),
            "format": "+".join(
                ["Digital" if (m.get("format") or "Unknown") == "Digital Media" else (m.get("format") or "Unknown")
                 for m in (release.get("media") or [])]
            ) or "Unknown",
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
# FORENSIC AUDIT LOG
# =========================================================
def _write_mb_id_audit_log(root, release_title, artist_seed, fmt, track_count, mb_album_id, inside_run=False):
    """
    Appends a "MusicBrainz ID" block to MetaForge.log, same header/footer
    convention as Unpack & Convert's own block (context_engine.write_audit_
    log) and Intelli-Tagger's AUDIT RUN block (it_context_engine.update_
    audit_trail) -- three different tools, three separate writers (matching
    the precedent those two already set: each tool owns its own block's
    content, only the visual format is shared), but this is genuinely new:
    until now, this tool never wrote to MetaForge.log at all, only
    manifest.json (John's report, 2026-08-08 -- the log didn't lay out
    what this tool had actually done, because it never tried to).
    """
    log_path = root / "MetaForge.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = [
        f"Version Selected: {release_title}",
        f"Artist: {artist_seed}",
        f"Format: {fmt}",
        f"Track Count: {track_count}",
        f'mb_album_id: "{mb_album_id}"',
    ]
    if inside_run:
        # v2: the run already has its own block (common/mf_events.run_stream
        # writes header, every event and the "Finished" footer), so this
        # is a sub-section of it, not a second banner.
        log_content = ["", "SUMMARY"] + details + [""]
    else:
        log_content = [
            f"\n{'='*60}",
            f"METAFORGE AUDIT LOG | {timestamp}",
            "MetaForge Process: MusicBrainz ID",
            f"{'-'*60}",
        ] + details + [f"{'='*60}\n"]

    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write("\n".join(log_content))
    except Exception:
        pass


# =========================================================
# COMMIT (UNCHANGED CONTRACT)
# =========================================================
def commit_ids_to_files(data):
    """
    Writes the MusicBrainz IDs into each file and renames it.

    v2 (2026-11-13): a generator of events instead of one silent JSON
    reply. Every file gets its own entry ("track" event), so a box set
    shows live progress, and every failure is reported with its reason
    instead of only being counted (the 1.x screen said "N files updated"
    even when some had failed, and offered the hand-off anyway). The
    hand-off is only signalled after a clean commit.
    """
    local_path = Path(data.get("local_path") or "")
    mapping = data.get("mapping") or []

    artist_seed = data.get("artist_seed", "Unknown Artist")
    album_seed = data.get("album_seed", local_path.name)
    release_year = data.get("release_year", "Unknown")
    release_title = data.get("release_title", album_seed)
    fmt = data.get("format", "Unknown")
    release_group_first_date = data.get("release_group_first_date", "")
    release_group_secondary_types = data.get("release_group_secondary_types", [])
    mb_label_name = data.get("mb_label_name", "")
    mb_catalog_number = data.get("mb_catalog_number", "")

    stats = {"success": 0, "failed": 0}
    total = len(mapping)

    # John, 2026-11-13 (option b): when the user REORDERED the files on
    # screen, the filename's number prefix follows the new position, but
    # keeps the disc hundreds (a disc-2 file placed 3rd on its disc ->
    # "203"). Without a reorder the prefix is left exactly as Unpack &
    # Convert wrote it (the July 2026 box-set rule below), gaps and all.
    renumbered = {}
    if data.get("renumber"):
        per_disc = {}
        for i, item in enumerate(mapping):
            m = re.match(r'^(\d+)', Path(item["current_filename"]).stem)
            old = int(m.group(1)) if m else 0
            disc = old // 100 if old >= 100 else 0
            per_disc[disc] = per_disc.get(disc, 0) + 1
            renumbered[i] = str(disc * 100 + per_disc[disc]) if disc else str(per_disc[disc])

    yield event("step", "Writing MusicBrainz IDs and renaming files", file=release_title)
    if not mapping:
        yield event("error", "There are no files to update. Choose the album folder, then a release")
        return

    for idx, item in enumerate(mapping, 1):
        old_path = local_path / item["current_filename"]
        shown_name = Path(item["current_filename"]).name

        if not old_path.exists():
            stats["failed"] += 1
            yield event("error", "File not found, so it was skipped", file=shown_name)
            yield signal("progress", current=idx, total=total)
            continue

        # No MusicBrainz track for this file: it keeps its own title.
        if not (item.get("target_title") or "").strip():
            item["target_title"] = _own_title(old_path)

        # 1. TAGS
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
        except Exception as e:
            stats["failed"] += 1
            yield event("error", f"IDs not written: {e}. The file was left as it was", file=shown_name)
            yield signal("progress", current=idx, total=total)
            continue

        # 2. RENAME
        # Real bug, found live 2026-07-21 (John's Matt Bianco box set
        # report, watched live on a second run): this used to rename
        # the physical file to item["track_num"] -- the album-wide
        # linear position (1, 2, 3... continuing across every disc,
        # matching MB's own tracklist position and what the TRCK tag
        # above correctly carries). That collapsed Unpack & Convert's
        # disc-aware "101"/"102"/"201"/"202" filing convention (disc N
        # * 100 + per-disc track, see bitstream_engine.py's filing_id)
        # down to a flat "1"/"2"/"3", discarding which disc a track
        # belongs to. The TAG should be the album-wide position; the
        # FILENAME's numeric prefix is Unpack & Convert's concern, not
        # this tool's -- so it's preserved as-is from whatever the file
        # is already named, not recomputed from track_num.
        existing_prefix_match = re.match(r'^(\d+)', old_path.stem)
        if renumbered:
            filing_prefix = renumbered[idx - 1]
        else:
            filing_prefix = existing_prefix_match.group(1) if existing_prefix_match else str(item["track_num"])
        item["_filing_prefix"] = filing_prefix

        # Real per-track performer (e.g. from MB's own recording-level
        # artist-credit on a Various Artists compilation) takes priority
        # over the blanket release-level artist_seed -- see track_artist
        # capture in get_release_details() above. Falls back to
        # artist_seed for the normal case where every track shares one
        # artist and MB never returned a differing recording credit.
        safe_artist = sanitize_filename(item.get("track_artist") or artist_seed)
        safe_title = sanitize_filename(item["target_title"])

        new_name = f"{filing_prefix} - {safe_artist} - {safe_title}.mp3"
        new_path = old_path.parent / new_name

        try:
            # Compare the exact names, not the paths: Windows paths compare
            # case-insensitively, so a capitalisation-only correction from
            # MusicBrainz ("Out in the country" -> "Out In The Country") used
            # to count as "same file" and was silently never applied.
            if old_path.name != new_name:
                os.rename(str(old_path), str(new_path))
                did = f"IDs written (track {item['track_num']}), renamed from \u201c{old_path.name}\u201d"
            else:
                did = f"IDs written (track {item['track_num']}), name already correct"
        except FileExistsError:
            stats["failed"] += 1
            yield event("error", f"IDs written, but not renamed: a file called \u201c{new_name}\u201d already exists",
                        file=shown_name)
            yield signal("progress", current=idx, total=total)
            continue
        except Exception as e:
            stats["failed"] += 1
            yield event("error", f"IDs written, but not renamed: {e}", file=shown_name)
            yield signal("progress", current=idx, total=total)
            continue

        stats["success"] += 1
        yield event("track", did, file=new_name)
        yield signal("progress", current=idx, total=total)

    if stats["success"] > 0:
        _update_manifest(
            local_path, mapping, release_year, artist_seed, album_seed,
            release_group_first_date, release_group_secondary_types,
            mb_label_name, mb_catalog_number
        )

    n_ok, n_bad = stats["success"], stats["failed"]
    yield signal("commit_result", success=n_ok, failed=n_bad)
    if n_bad == 0:
        yield event("done", f"{n_ok} file{'s' if n_ok != 1 else ''} updated. Ready for Intelli-Tagger")
        yield signal("handoff_ready")
    else:
        yield event("warning", f"{n_bad} of {total} files were not fully updated (listed above in red). "
                               f"Fix those, then choose the release again to retry")

    # Last, so MetaForge.log reads in order: events, then the SUMMARY,
    # then the run's "Finished" footer.
    if n_ok > 0:
        _write_mb_id_audit_log(
            local_path, release_title, artist_seed, fmt,
            n_ok, mapping[0].get("album_id", "") if mapping else "",
            inside_run=True
        )


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
        # Same per-track-artist-over-blanket-seed precedence as the physical
        # rename above -- keeps the manifest's filename field in sync with
        # what's actually on disk, and surfaces the real per-track performer
        # ("artist") for Intelli-Tagger's identity resolution downstream.
        track_artist = item.get("track_artist") or artist_seed
        # _filing_prefix is the disc-aware number the file was actually
        # renamed to above (falls back to track_num only for an item whose
        # rename never happened -- e.g. it was already counted under
        # stats["failed"] -- so the manifest still records its best guess
        # rather than crashing on a missing key).
        filing_prefix = item.get("_filing_prefix") or str(item["track_num"])
        m["mb_track_map"].append({
            "position": item["track_num"],
            "filename": f"{filing_prefix} - "
                        f"{sanitize_filename(track_artist)} - "
                        f"{sanitize_filename(item['target_title'])}.mp3",
            "title": item["target_title"],
            "artist": track_artist,
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
        "mb_artist_country": sample.get("artist_country", ""),
        "release_year": year,
        "mb_release_group_first_date": release_group_first_date,
        "mb_release_group_secondary_types": release_group_secondary_types or [],
        "mb_label_name": mb_label_name,
        "mb_catalog_number": mb_catalog_number,
        "is_physically_synced": True,
        "synced_at": datetime.now().isoformat()
    })

    manifest_path.write_text(json.dumps(m, indent=4), encoding="utf-8")