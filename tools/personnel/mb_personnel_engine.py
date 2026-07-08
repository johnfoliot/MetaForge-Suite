# --- START OF FILE mb_personnel_engine.py ---
# ======================================================================
# MetaForge Studio: MusicBrainz Personnel Engine
# Physical Location: \tools\personnel\mb_personnel_engine.py
# Role: Converts MusicBrainz recording/work relationship data into
# Personnel Engine v2's atomic edge shape. Consumes the manifest.json
# pre-seed Intelli-Tagger captures for free (see mb_resolution_engine.py's
# get_recording_first_release_date_and_relations()) when available, and
# falls back to a live MB fetch otherwise -- same fast-path-or-fallback
# shape as intelli-tagger.py's fast_track/MB-ID pattern, so Personnel
# still works standalone on an album that skipped Intelli-Tagger.
# ======================================================================
from typing import Any, Dict, List, Optional

CONFIDENCE_MB = 0.95  # MB's own structured relationship data -- highest
                       # trust tier, above Wikipedia's 0.9 direct-mapped
                       # ceiling (see edge_normalizer.classify_role).

# MB relation `type` -> canonical RelationType. Deliberately NOT reusing
# edge_normalizer.classify_role() here -- that function regex-parses
# free-text role strings, but MB's `type` field is already a clean,
# structured value; matching it directly is more reliable than routing it
# through a free-text classifier built for messier sources.
_TYPE_MAP = {
    "engineer": "ENGINEERED_BY",
    "mix": "ENGINEERED_BY",
    "master": "ENGINEERED_BY",
    "producer": "PRODUCED",
    "instrument": "PERFORMED_ON",
    "vocal": "PERFORMED_ON",
    "performer": "PERFORMED_ON",
    "arranger": "ARRANGED_BY",
    "composer": "COMPOSED",
    "lyricist": "WRITTEN_BY",
    "writer": "WRITTEN_BY",
}


def relations_to_edges(relations: List[Dict[str, Any]], track_number: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Converts a raw MB `relations` array (from a recording's inc=artist-rels
    lookup) into atomic edge candidates. Skips work-link relations
    (type="performance", target-type="work") -- those feed the Work-hop
    below instead, not a direct personnel credit.

    Returns a list of {name, mbid, relation_type, role, confidence,
    evidence_scope, evidence_detail} dicts.
    """

    edges = []

    for rel in relations or []:
        if rel.get("target-type") != "artist":
            continue

        artist = rel.get("artist") or {}
        name = artist.get("name")
        mbid = artist.get("id")
        if not name or not mbid:
            continue

        rel_type_raw = (rel.get("type") or "").strip().lower()
        relation_type = _TYPE_MAP.get(rel_type_raw, "ASSOCIATED_WITH")

        attributes = rel.get("attributes") or []
        role = ", ".join(attributes) if attributes else rel_type_raw.title() or "Contributed"

        edges.append({
            "name": name,
            "mbid": mbid,
            "relation_type": relation_type,
            "role": role,
            "confidence": CONFIDENCE_MB,
            "provenance": "MusicBrainz",
            "evidence_scope": "track" if track_number is not None else None,
            "evidence_detail": str(track_number) if track_number is not None else None,
        })

    return edges


def extract_work_ids(relations: List[Dict[str, Any]]) -> List[str]:
    """Distinct MB Work MBIDs linked to a recording via a "performance" relation."""
    ids = []
    for rel in relations or []:
        if rel.get("type") == "performance" and rel.get("target-type") == "work":
            work = rel.get("work") or {}
            wid = work.get("id")
            if wid and wid not in ids:
                ids.append(wid)
    return ids


def resolve_work_credits(mb, work_id: str, work_cache: Dict[str, Any], track_number: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    The MB Work-hop: composer/lyricist/arranger credits live on the Work
    entity, one level out from the recording itself -- a genuinely
    separate MB call (never pre-seeded by Intelli-Tagger, see
    project_personnel_engine_v2 design/plan). work_cache is a plain dict,
    shared across the whole album resolution pass, so a work referenced
    by more than one track is only ever fetched once. Never raises.
    """

    if work_id in work_cache:
        return work_cache[work_id]

    try:
        data = mb.get_work(work_id, inc=["artist-rels"])
        edges = relations_to_edges(data.get("relations", []) or [], track_number=track_number)
    except Exception:
        edges = []

    work_cache[work_id] = edges
    return edges


def resolve_track_personnel(mb, recording_id: str, track_number: int,
                             preseeded_relations: Optional[List[Dict[str, Any]]],
                             work_cache: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Single entry point for one track's MB personnel: uses the manifest
    pre-seed if provided (fast path, zero fetch), otherwise fetches fresh
    (fallback, e.g. an album that skipped Intelli-Tagger). Merges direct
    recording relations with the Work-hop's composer/lyricist credits.
    Never raises -- any failure yields an empty list for that track.
    """

    if not recording_id or recording_id in ("None", "Unknown", ""):
        return []

    if preseeded_relations is not None:
        relations = preseeded_relations
    else:
        try:
            data = mb.get_recording(recording_id, inc=["artist-rels", "work-rels"])
            relations = data.get("relations", []) or []
        except Exception:
            relations = []

    edges = relations_to_edges(relations, track_number=track_number)

    for work_id in extract_work_ids(relations):
        edges.extend(resolve_work_credits(mb, work_id, work_cache, track_number=track_number))

    return edges

# --- END OF FILE mb_personnel_engine.py ---
