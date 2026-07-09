# --- START OF FILE discogs_personnel_engine.py ---
# ======================================================================
# MetaForge Studio: Discogs Personnel Engine
# Physical Location: \tools\personnel\discogs_personnel_engine.py
# Role: Converts Discogs extraartists data into Personnel Engine v2's
# atomic edge shape. Consumes the manifest.json pre-seed Intelli-Tagger
# captures for free when available, falls back to a live Discogs fetch
# otherwise (same fast-path-or-fallback shape as mb_personnel_engine.py).
# ======================================================================
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.personnel.edge_normalizer import normalize_personnel, is_junk_name, load_config

_JUNK_CONFIG = load_config()

# The live-fallback path below imports discogs_resolution_engine, which
# lives under Intelli-Tagger's own engines/ folder, not Personnel's --
# that directory is only on sys.path while Intelli-Tagger's own
# run_logic() is executing, so it must be added explicitly here too.
_IT_ENGINES_DIR = Path(__file__).resolve().parents[2] / "tools" / "intelli-tagger" / "engines"
if str(_IT_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_IT_ENGINES_DIR))

CONFIDENCE_DISCOGS = 0.9  # Discogs' own structured extraartists data --
                           # same trust tier as Wikipedia's direct-mapped
                           # ceiling (see edge_normalizer.classify_role).


def _extraartist_to_edges(entry: Dict[str, Any], evidence_scope: Optional[str],
                           evidence_detail: Optional[str]) -> List[Dict[str, Any]]:
    """
    A Discogs extraartist's `role` field is free text, same as Wikipedia's
    -- can be comma-joined ("Vocals, Guitar"), so it goes through the SAME
    normalize_personnel()/classify_role() atomization used everywhere
    else, not a bespoke parser. Only the name/confidence/provenance/scope
    wrapping is Discogs-specific.
    """

    name = entry.get("name")
    role_text = entry.get("role")
    if not name or not role_text:
        return []
    if is_junk_name(name, _JUNK_CONFIG):
        return []

    edges = []
    for atom in normalize_personnel(role_text):
        edges.append({
            "name": name,
            "relation_type": atom["relation_type"],
            "role": atom["role"],
            # Discogs' own structured data is more trustworthy than
            # classify_role()'s free-text guess, so the flat Discogs
            # confidence wins over whatever normalize_personnel() guessed
            # for this atom.
            "confidence": CONFIDENCE_DISCOGS,
            "provenance": "Discogs",
            "evidence_scope": evidence_scope,
            "evidence_detail": evidence_detail,
        })
    return edges


def extraartists_to_edges(discogs_extraartists: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    discogs_extraartists is the {"album": [...], "by_track": {position:
    [...]}} shape produced by discogs_resolution_engine.extract_extraartists()
    (either read from the manifest pre-seed, or fetched fresh below).

    Track-level scope deliberately stores Discogs' own raw `tracks` field
    (e.g. "A1 to A3") as-is in evidence_detail, rather than force-converting
    vinyl-side notation into plain track numbers -- "store messy evidence,
    but only traverse clean atoms" (see the original edge-normalization
    project plan). Track-level entries without a `tracks` field of their
    own fall back to the track's own tracklist position.
    """

    if not discogs_extraartists:
        return []

    edges = []

    for entry in discogs_extraartists.get("album", []) or []:
        edges.extend(_extraartist_to_edges(entry, evidence_scope="album", evidence_detail=None))

    for position, track_extraartists in (discogs_extraartists.get("by_track") or {}).items():
        for entry in track_extraartists or []:
            scope_detail = (entry.get("tracks") or "").strip() or str(position)
            edges.extend(_extraartist_to_edges(entry, evidence_scope="track", evidence_detail=scope_detail))

    return edges


def resolve_album_personnel(artist: str, album: str,
                             preseeded_extraartists: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Single entry point: uses the manifest pre-seed if provided (fast path,
    zero fetch), otherwise searches+fetches fresh (fallback, e.g. an album
    that skipped Intelli-Tagger). Never raises.
    """

    if preseeded_extraartists is not None:
        return extraartists_to_edges(preseeded_extraartists)

    try:
        import discogs_resolution_engine
        release_id = discogs_resolution_engine.search_release_id(artist, album)
        if not release_id:
            return []
        release_data = discogs_resolution_engine._fetch_release_json(release_id)
        if not release_data:
            return []
        return extraartists_to_edges(discogs_resolution_engine.extract_extraartists(release_data))
    except Exception:
        return []

# --- END OF FILE discogs_personnel_engine.py ---
