# --- START OF FILE id_engine.py ---
# ======================================================================
# MetaForge Engine: Identity Recovery (Phase 6)
# Role: Deterministic Identity Resolver (NON-DESTRUCTIVE)
# Build 2.2.1: Schema preservation + MB field normalization fix
# Physical Location: \tools\intelli-tagger\engines\id_engine.py
# ======================================================================

from pathlib import Path
from mutagen.id3 import ID3


# =========================================================
# CORE IDENTITY RESOLVER
# =========================================================
def get_identity(file_path, target_artist, duration, mb_ids, track_map=None):
    """
    Deterministic identity resolver (NON-DESTRUCTIVE VERSION)

    Rules:
    - NEVER overwrite MB fields if they already exist upstream
    - NEVER fabricate missing MusicBrainz relationships
    - ONLY recover or preserve identity signals
    """

    mb_track_id = "None"
    mb_recording_id = "None"
    track_title = ""

    # --------------------------------------------------
    # TITLE RECOVERY (FROM FILE)
    # --------------------------------------------------
    try:
        audio = ID3(str(file_path))
        if "TIT2" in audio:
            track_title = str(audio["TIT2"].text[0]).strip()
    except Exception:
        pass

    if not track_title:
        track_title = Path(file_path).stem

    # --------------------------------------------------
    # MANIFEST TRACK MAP LOOKUP (OPTIONAL MATCH)
    # --------------------------------------------------
    if track_map:
        try:
            for entry in track_map:
                manifest_title = entry.get("title", "").strip().lower()

                if manifest_title == track_title.lower():
                    mb_track_id = entry.get("mb_track_id", "None")
                    mb_recording_id = entry.get("mb_recording_id", "None")
                    break
        except Exception:
            mb_track_id = "None"
            mb_recording_id = "None"

    # --------------------------------------------------
    # BITSTREAM FALLBACK
    # UFID holds the Recording ID (Picard convention); the release-specific
    # Track ID, when present, lives in its own TXXX field.
    # --------------------------------------------------
    if mb_recording_id == "None":
        mb_recording_id = _get_bitstream_mb_recording_id(file_path)
    if mb_track_id == "None":
        mb_track_id = _get_bitstream_txxx(file_path, RELEASE_TRACK_DESCS)

    # --------------------------------------------------
    # ACOUSTID EXTRACTION (BITSTREAM AUTHORITATIVE)
    # --------------------------------------------------
    acoustid = _get_bitstream_acoustid(file_path)

    # --------------------------------------------------
    # PRESERVE MB IDS FROM INPUT (CRITICAL FIX)
    # --------------------------------------------------
    mb_artist_id = mb_ids.get("artist", "None")
    mb_album_id = mb_ids.get("album", "None")
    mb_group_id = mb_ids.get("release_group", mb_ids.get("group", "None"))

    # --------------------------------------------------
    # LEGACY BITSTREAM FALLBACK
    # If no manifest seed was supplied (e.g. this album was never run
    # through the MusicBrainz ID tool), recover MB IDs already embedded
    # as Picard-standard tags from a prior tagging tool.
    # --------------------------------------------------
    if mb_artist_id in (None, "None", ""):
        mb_artist_id = _get_bitstream_txxx(file_path, LEGACY_ARTIST_DESCS)
    if mb_album_id in (None, "None", ""):
        mb_album_id = _get_bitstream_txxx(file_path, LEGACY_ALBUM_DESCS)
    if mb_group_id in (None, "None", ""):
        mb_group_id = _get_bitstream_txxx(file_path, LEGACY_GROUP_DESCS)

    # --------------------------------------------------
    # CRITICAL FIX: DO NOT ZERO OUT WORK ID
    # (pass-through only; upstream owns truth)
    # --------------------------------------------------
    mb_work_id = mb_ids.get("work", "None")

    # --------------------------------------------------
    # STRICT OUTPUT CONTRACT (NO DESTRUCTIVE DEFAULTS)
    # --------------------------------------------------
    return {
        "title": track_title,
        "mb_track_id": mb_track_id,
        "mb_recording_id": mb_recording_id,
        "acoustid": acoustid if acoustid != "None" else None,

        # preserve identity layer inputs
        "mb_artist_id": mb_artist_id,
        "mb_album_id": mb_album_id,
        "mb_group_id": mb_group_id,
        "mb_work_id": mb_work_id,

        # metadata only (never authoritative here)
        "original_year": None,
        "label": None,
        "personnel": []
    }


# =========================================================
# BITSTREAM MB RECORDING RECOVERY
# =========================================================
def _get_bitstream_mb_recording_id(file_path):
    try:
        audio = ID3(str(file_path))
        ufid = audio.get("UFID:http://musicbrainz.org")

        if ufid:
            return ufid.data.decode("utf-8")

    except Exception:
        pass

    return "None"


# =========================================================
# BITSTREAM ACOUSTID RECOVERY
# =========================================================
def _get_bitstream_acoustid(file_path):
    try:
        audio = ID3(str(file_path))

        for frame in audio.getall("TXXX"):
            if frame.desc.strip().lower() in ("acoustid", "acoustid id"):
                return str(frame.text[0]).strip()

    except Exception:
        pass

    return "None"


# =========================================================
# LEGACY BITSTREAM MB ID RECOVERY (Picard-standard tags)
# =========================================================
# Covers both Picard's current naming and the older non-namespaced
# variant seen in some legacy libraries.
LEGACY_ARTIST_DESCS = ["MusicBrainz Artist Id", "MUSICBRAINZ_ARTISTID"]
LEGACY_ALBUM_DESCS = ["MusicBrainz Album Id", "MUSICBRAINZ_ALBUMID"]
LEGACY_GROUP_DESCS = ["MusicBrainz Release Group Id", "MUSICBRAINZ_RELEASEGROUPID"]
RELEASE_TRACK_DESCS = ["MusicBrainz Release Track Id"]


def _get_bitstream_txxx(file_path, desc_candidates):
    try:
        audio = ID3(str(file_path))
        for frame in audio.getall("TXXX"):
            desc = frame.desc.strip().lower()
            for candidate in desc_candidates:
                if desc == candidate.lower():
                    value = str(frame.text[0]).strip()
                    if value:
                        return value
    except Exception:
        pass

    return "None"


def get_legacy_mb_seeds(file_path):
    """
    Reads legacy/Picard-standard MusicBrainz TXXX tags directly from a
    file's bitstream. Used when no manifest.json seed data exists (e.g.
    an album tagged before it was ever run through MetaForge's own
    MusicBrainz ID tool).
    """
    return {
        "mb_artist_id": _get_bitstream_txxx(file_path, LEGACY_ARTIST_DESCS),
        "mb_album_id": _get_bitstream_txxx(file_path, LEGACY_ALBUM_DESCS),
        "mb_group_id": _get_bitstream_txxx(file_path, LEGACY_GROUP_DESCS),
    }

# --- END OF FILE id_engine.py ---