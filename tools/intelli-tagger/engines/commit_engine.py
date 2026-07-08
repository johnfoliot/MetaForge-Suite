# ======================================================================
# MetaForge Engine: Relational & Physical Commit (Phase 7)
# Location: MetaForge Suite\tools\intelli-tagger\engines\commit_engine.py
# Role: PURE Persistence Layer (Write-Only Authority)
# Build 2.3.1: Database schema alignment remediation
# ======================================================================

import json
import sqlite3
import hashlib
from datetime import datetime

from mutagen.id3 import (
    ID3, TIT2, TCON, TBPM, TKEY,
    TXXX, TYER, TORY, TPUB, UFID, COMM,
    ID3NoHeaderError
)

from common import config_handler
from year_resolution_engine import SRC_DISCOGS, SRC_DISCOGS_MASTER, SRC_WIKIPEDIA, SRC_AI_WEB

DB_PATH = config_handler.DB_PATH
SIGNATURE = "Metadata by MetaForge Studio - the music management tool for Serious Collectors."

# Same evidence-collection pattern as tools/personnel/personnel.py's
# MB_CANDIDATE_LOG (added 2026-07-08 at John's request, extended here to
# the original-year waterfall) -- the MB contribution tool itself is
# still deferred, but there's no reason to lose this evidence in the
# meantime, and it lets it be visually spot-checked before that tool
# exists. Only these four source labels represent a NON-MusicBrainz
# source actually winning outright (either MB had nothing, or a
# genuinely different/earlier year overrode MB's own tentative) -- the
# *_CORROBORATED variants mean a second source agreed with MB's existing
# data (nothing to correct), and the MB_* tentative/differing labels are
# MB's own data, just unverified (also nothing to correct).
_YEAR_CANDIDATE_SOURCES = {SRC_DISCOGS, SRC_DISCOGS_MASTER, SRC_WIKIPEDIA, SRC_AI_WEB}
YEAR_CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "original_year_correction_candidates.jsonl"


def _log_year_correction_candidate(mf_id, file_path, artist, album, title,
                                    mb_recording_id, current_release_year,
                                    proposed_original_year, orig_year_conf, orig_year_source):
    """Appends one JSONL entry to YEAR_CANDIDATE_LOG. Never raises -- a
    logging failure must never break a real commit."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "mf_id": mf_id, "file_path": file_path,
        "artist": artist, "album": album, "title": title,
        "mb_recording_id": mb_recording_id,
        "current_release_year": current_release_year,
        "proposed_original_year": proposed_original_year,
        "orig_year_conf": orig_year_conf, "orig_year_source": orig_year_source,
    }
    try:
        YEAR_CANDIDATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(YEAR_CANDIDATE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as ex:
        print(f"⚠️ Year correction candidate log write failed: {ex}")


# =========================================================
# PUBLIC API
# =========================================================
def execute_commit(
    root_path,
    track_results,
    db_write=True,
    manifest_seeds=None,
    audit_callback=None
):

    if manifest_seeds is None:
        manifest_seeds = {}

    yield '<div class="it-log-entry it-val-gold"><img src="ui/images/database.png" alt="" style="height:16px; width:auto;"> Writing to MetaForge database...</div>'

    artist_name = manifest_seeds.get('artist')
    album_title = manifest_seeds.get('album')
    release_year = manifest_seeds.get('release_year', 'Unknown')

    mf_id, mf_artist_id = _generate_mf_hashes(artist_name, album_title)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = None
    cursor = None

    if db_write:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            cursor.execute("DELETE FROM tracks WHERE mf_id = ?", (mf_id,))
            cursor.execute("DELETE FROM edges WHERE source_id = ?", (mf_id,))

        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">DB ERROR: {str(e)}</div>'
            db_write = False

    primary = track_results[0][1] if track_results else {}
    label_val = primary.get('label', 'Unknown')
    personnel_list = primary.get('personnel', [])
    country_val = primary.get('country', 'Unknown')

    success_count = 0

    # =========================================================
    # TRACK LOOP
    # =========================================================
    for idx, (f_path, data) in enumerate(track_results, 1):

        try:
            title = data.get('title', f_path.stem)
            verified_length_seconds = int(data.get('duration', 0))

            _write_physical_tags(f_path, data, release_year)

            if db_write and cursor:

                mb_track_id = _normalize(data.get("mb_track_id"))
                mb_recording_id = _normalize(data.get("mb_recording_id"))
                mb_work_id = _normalize(data.get("mb_work_id"))
                acoustid = _normalize(data.get("acoustid"))
                mb_artist_id = _normalize(data.get("mb_artist_id"))

                cursor.execute("""
                    INSERT INTO tracks (
                        file_path, mf_id, mf_artist_id,
                        mb_artist_id, mb_track_id,
                        acoustid, title,
                        genre, sub_genre,
                        original_year,
                        bpm, key_val,
                        mood, intensity,
                        is_remediated,
                        last_updated,
                        mb_work_id,
                        orig_year_conf,
                        orig_year_source,
                        leak_flag,
                        length,
                        sonic_texture,
                        emotional_flavor,
                        mb_recording_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(f_path.resolve()).replace('\\', '/'),
                    mf_id,
                    mf_artist_id,
                    mb_artist_id,
                    mb_track_id,
                    acoustid,
                    title,
                    data.get('parent', 'Unknown'),
                    data.get('sub', 'Unknown'),
                    data.get('original_year', release_year),
                    data.get('bpm', 0),
                    data.get('key', '??'),
                    data.get('mood', 'Unknown'),
                    data.get('intensity', 1),
                    1,
                    now,
                    mb_work_id,
                    data.get('orig_year_conf', 0),
                    data.get('orig_year_source', 'Unresolved (Release Year Fallback)'),
                    data.get('leak_flag', 1),
                    verified_length_seconds,
                    data.get('sonic_texture', 'Unknown'),
                    data.get('emotional_flavor', 'Unknown'),
                    mb_recording_id,
                ))

                orig_year_source = data.get('orig_year_source', 'Unresolved (Release Year Fallback)')
                if orig_year_source in _YEAR_CANDIDATE_SOURCES:
                    _log_year_correction_candidate(
                        mf_id, str(f_path.resolve()).replace('\\', '/'),
                        artist_name, album_title, title,
                        mb_recording_id, release_year,
                        data.get('original_year'), data.get('orig_year_conf', 0), orig_year_source
                    )

                success_count += 1

        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">Commit Error: {f_path.name} | {str(e)}</div>'

    # =========================================================
    # MASTER SYNC
    # =========================================================
    if db_write and conn:
        try:
            _sync_relational_masters(
                cursor,
                mf_id,
                mf_artist_id,
                artist_name,
                album_title,
                release_year,
                label_val,
                country_val,
                manifest_seeds,
                now,
                manifest_seeds.get('is_compilation', 0)
            )

            conn.commit()
            conn.close()

        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">Graph commit failure: {str(e)}</div>'

    # =========================================================
    # AUDIT TRAIL
    # =========================================================
    try:
        if callable(audit_callback):
            audit_callback(
                root_path=root_path,
                manifest_seeds=manifest_seeds,
                track_results=track_results,
                label=label_val,
                personnel=personnel_list,
                db_write=db_write,
                release_year=release_year
            )
    except Exception as e:
        yield f'<div class="it-log-entry it-val-red">Audit warning: {str(e)}</div>'

    yield f'<div class="it-log-entry" style="margin-left:16px;">✅ {success_count} tracks committed.</div>'


# =========================================================
# PHYSICAL TAG WRITER
# =========================================================
def _write_physical_tags(file_path, data, album_reissue_year):
    # encoding=1 (UTF-16) throughout: ID3v2.3 (v2_version=3 below) only
    # officially permits Latin-1 or UTF-16 for text frames -- UTF-8 wasn't
    # added to the spec until v2.4. Matches bitstream_engine.py and
    # musicbrainz_id.py's writers.
    try:
        tags = ID3(str(file_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("UFID:http://musicbrainz.org")
    tags.delall("COMM")
    # Only clear the specific TXXX fields MetaForge itself manages (current
    # names plus prior MetaForge-internal names, for migration) -- leave any
    # other TXXX data on the file (Picard tags MetaForge doesn't own, tags
    # from earlier pipeline stages like Unpack/Convert's CATEGORY, etc.) untouched.
    MANAGED_TXXX = [
        "MusicBrainz Artist Id", "MusicBrainz Album Id",
        "MusicBrainz Release Group Id", "MusicBrainz Release Track Id",
        "Acoustid Id",
        "MB Artist ID", "MB Album ID", "MB Release Group ID", "MB Recording ID", "AcoustID",
        "Sub-Genre", "Intensity", "Sonic Texture", "Emotional Flavor", "Mood",
    ]
    for desc in MANAGED_TXXX:
        tags.delall(f"TXXX:{desc}")

    tags.add(
        COMM(
            encoding=1,
            lang="XXX",
            desc="",
            text=[SIGNATURE]
        )
    )

    mb_track_id = _normalize(data.get("mb_track_id"))
    mb_artist_id = _normalize(data.get("mb_artist_id"))
    mb_album_id = _normalize(data.get("mb_album_id"))
    mb_group_id = _normalize(data.get("mb_group_id"))
    mb_recording_id = _normalize(data.get("mb_recording_id"))
    acoustid = _normalize(data.get("acoustid"))

    # UFID holds the Recording ID (Picard convention -- the true, cross-release
    # identity anchor). mb_track_id is release-specific (e.g. "which reissue/
    # compilation this copy came from") and gets its own TXXX field instead.
    if mb_recording_id:
        tags.add(
            UFID(
                owner="http://musicbrainz.org",
                data=mb_recording_id.encode("utf-8")
            )
        )

    if mb_artist_id:
        tags.add(TXXX(encoding=1, desc="MusicBrainz Artist Id", text=[mb_artist_id]))

    if mb_album_id:
        tags.add(TXXX(encoding=1, desc="MusicBrainz Album Id", text=[mb_album_id]))

    if mb_group_id:
        tags.add(TXXX(encoding=1, desc="MusicBrainz Release Group Id", text=[mb_group_id]))

    if mb_track_id:
        tags.add(TXXX(encoding=1, desc="MusicBrainz Release Track Id", text=[mb_track_id]))

    if acoustid:
        tags.add(TXXX(encoding=1, desc="Acoustid Id", text=[acoustid]))

    tags.add(TIT2(encoding=1, text=[data.get("title", "")]))
    tags.add(TYER(encoding=1, text=[str(album_reissue_year)]))
    tags.add(TORY(encoding=1, text=[str(data.get("original_year", album_reissue_year))]))
    tags.add(TCON(encoding=1, text=[data.get("parent", "Unknown")]))
    tags.add(TBPM(encoding=1, text=[str(data.get("bpm", 0))]))
    tags.add(TKEY(encoding=1, text=[data.get("key", "??")]))

    # Mood has no ID3v2.3 equivalent -- TMOO is a v2.4-only frame, and
    # update_to_v23() silently drops it entirely on save (verified: zero
    # frames survive), rather than erroring or downgrading it. TXXX is
    # the same fix already applied to every other non-standard field
    # here (Sub-Genre, Intensity, Sonic Texture, Emotional Flavor).
    tags.add(TXXX(encoding=1, desc="Mood", text=[data.get("mood", "Unknown")]))
    tags.add(TXXX(encoding=1, desc="Sub-Genre", text=[data.get("sub", "Unknown")]))
    tags.add(TXXX(encoding=1, desc="Intensity", text=[str(data.get("intensity", 1))]))
    tags.add(TXXX(encoding=1, desc="Sonic Texture", text=[data.get("sonic_texture", "Unknown")]))
    tags.add(TXXX(encoding=1, desc="Emotional Flavor", text=[data.get("emotional_flavor", "Unknown")]))

    if data.get("label"):
        tags.add(TPUB(encoding=1, text=[data["label"]]))

    # Mutagen's save() alone does not downgrade v2.4-native frames -- per
    # its own docs, it defaults to v2.4 internally and only the on-disk
    # header/serialization respects v2_version. Without this call, TYER/
    # TORY get silently replaced by TDRC/TDOR (v2.4-only frame types)
    # even though the file is declared ID3v2.3.
    tags.update_to_v23()
    tags.save(str(file_path), v2_version=3)


# =========================================================
# NORMALIZATION
# =========================================================
def _normalize(value):
    if value in [None, "", "None", "Unknown"]:
        return None
    return str(value)


# =========================================================
# HASHING
# =========================================================
def _generate_mf_hashes(artist, album):
    a = str(artist).strip().lower()
    b = str(album).strip().lower()

    return (
        hashlib.sha256(f"{a}|{b}".encode("utf-8")).hexdigest(),
        hashlib.sha256(a.encode("utf-8")).hexdigest()
    )


# =========================================================
# RELATIONAL SYNC
# =========================================================
def _sync_relational_masters(
    cursor,
    mf_id,
    mf_artist_id,
    artist_name,
    album_title,
    release_year,
    label_val,
    country_val,
    manifest_seeds,
    now,
    is_compilation=0
):
    cursor.execute("SELECT 1 FROM library_master WHERE mf_id = ?", (mf_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE library_master
            SET last_updated=?,
                mb_album_id=?,
                original_year=?,
                label=?,
                date_audit_status=1
            WHERE mf_id=?
        """, (
            now,
            manifest_seeds.get("mb_ids", {}).get("album", "None"),
            release_year,
            label_val,
            mf_id
        ))
    else:
        cursor.execute("""
            INSERT INTO library_master (
                mf_id, mf_artist_id, artist_name, album_title,
                mb_album_id, original_year, label,
                is_compilation, last_updated, date_audit_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mf_id,
            mf_artist_id,
            artist_name,
            album_title,
            manifest_seeds.get("mb_ids", {}).get("album", "None"),
            release_year,
            label_val,
            is_compilation,
            now,
            1
        ))

    cursor.execute("SELECT 1 FROM library_artist WHERE mf_artist_id = ?", (mf_artist_id,))
    if cursor.fetchone():
        cursor.execute("""
            UPDATE library_artist
            SET artist_name=?, last_updated=?, mb_artist_id=?, country=?
            WHERE mf_artist_id=?
        """, (
            artist_name,
            now,
            manifest_seeds.get("mb_ids", {}).get("artist", "None"),
            country_val,
            mf_artist_id
        ))
    else:
        cursor.execute("""
            INSERT INTO library_artist (
                mf_artist_id, mb_artist_id, artist_name, last_updated, country
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            mf_artist_id,
            manifest_seeds.get("mb_ids", {}).get("artist", "None"),
            artist_name,
            now,
            country_val
        ))