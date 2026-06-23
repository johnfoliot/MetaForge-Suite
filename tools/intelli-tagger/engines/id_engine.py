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
                    break
        except Exception:
            mb_track_id = "None"

    # --------------------------------------------------
    # UFID FALLBACK (BITSTREAM AUTHORITATIVE)
    # --------------------------------------------------
    if mb_track_id == "None":
        mb_track_id = _get_bitstream_mb_track_id(file_path)

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
# BITSTREAM MB TRACK RECOVERY
# =========================================================
def _get_bitstream_mb_track_id(file_path):
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
            if frame.desc.strip().lower() == "acoustid":
                return str(frame.text[0]).strip()

    except Exception:
        pass

    return "None"

# --- END OF FILE id_engine.py ---