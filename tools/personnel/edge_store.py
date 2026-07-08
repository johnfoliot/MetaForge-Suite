# --- START OF FILE edge_store.py ---
# ======================================================================
# MetaForge Studio: Edge Store (Shared Write Path)
# Physical Location: \tools\personnel\edge_store.py
# Role: The ONLY place that writes personnel data to the `edges` table.
# Every producer (Wikipedia, MusicBrainz, Discogs, AllMusic-paste, and
# Album Editor's manual edits) goes through upsert_edge() so dedup and
# overwrite semantics are identical everywhere, instead of each caller
# re-inventing its own insert logic (the exact drift that previously
# produced three incompatible relation_type schemes and a save path that
# deleted+rewrote an album's entire personnel graph on every edit).
# ======================================================================
from common import db_engine


def find_matching_edge(source_type, source_id, target_id, role):
    """
    Dedup key: (source_type, source_id, target_id, role) -- exact role-text
    match, per the original design ("useful, not gospel", don't
    over-engineer corroboration beyond this). Different role text for the
    same person (e.g. "guitar" vs "vocals") is a different fact and stays
    a separate edge; only an exact repeat of the same fact is deduplicated.
    """
    rows = db_engine.execute_query(
        "SELECT id, confidence FROM edges WHERE source_type=? "
        "AND LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND target_id=? AND role=?",
        (source_type, source_id, target_id, role)
    )
    return rows[0] if rows else None


def upsert_edge(source_type, source_id, target_type, target_id, relation_type, role,
                 confidence, provenance, evidence_scope=None, evidence_detail=None, weight=1.0):
    """
    If no edge matches (source_id, target_id, role), INSERT it. If one
    already exists, overwrite it in place -- UPDATE, not a second row --
    but only when the new confidence is >= the existing row's, so a
    weaker duplicate (e.g. a stale re-save) never downgrades a fact a
    stronger source already corroborated. Returns (action, edge_id) where
    action is "inserted" | "updated" | "skipped".
    """
    existing = find_matching_edge(source_type, source_id, target_id, role)

    if existing is None:
        db_engine.execute_query(
            """INSERT INTO edges (
                source_type, source_id, target_type, target_id, relation_type, role,
                weight, confidence, provenance, evidence_scope, evidence_detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (source_type, source_id, target_type, target_id, relation_type, role,
             weight, confidence, provenance, evidence_scope, evidence_detail),
            commit=True
        )
        return "inserted", None

    existing_confidence = existing.get("confidence") or 0
    if (confidence or 0) < existing_confidence:
        return "skipped", existing["id"]

    db_engine.execute_query(
        """UPDATE edges SET relation_type=?, weight=?, confidence=?, provenance=?,
           evidence_scope=?, evidence_detail=? WHERE id=?""",
        (relation_type, weight, confidence, provenance, evidence_scope, evidence_detail, existing["id"]),
        commit=True
    )
    return "updated", existing["id"]


def update_edge_by_id(edge_id, target_id, relation_type, role, confidence, provenance):
    """
    Direct update for a KNOWN edge id -- used when the caller (Album
    Editor) already knows exactly which existing row the user edited,
    rather than re-matching by (source_id, target_id, role). Overwrites
    that one row's fields only; every other edge for the album is
    untouched.
    """
    db_engine.execute_query(
        "UPDATE edges SET target_id=?, relation_type=?, role=?, confidence=?, provenance=? WHERE id=?",
        (target_id, relation_type, role, confidence, provenance, edge_id),
        commit=True
    )


def delete_edge(edge_id):
    db_engine.execute_query("DELETE FROM edges WHERE id=?", (edge_id,), commit=True)

# --- END OF FILE edge_store.py ---
