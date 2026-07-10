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


def find_matching_edge(source_type, source_id, target_id, role, evidence_scope=None, evidence_detail=None):
    """
    Dedup key: (source_type, source_id, target_id, role, evidence_scope,
    evidence_detail) -- role-text match AND which track/album this credit
    applies to, per the original design ("useful, not gospel", don't
    over-engineer corroboration beyond this). Different role text for the
    same person (e.g. "guitar" vs "vocals") is a different fact and stays
    a separate edge; only a repeat of the same fact is deduplicated.

    evidence_scope/evidence_detail added to the key 2026-07-10 -- a real
    data-loss bug found live, not cosmetic. The key used to be just
    (source_id, target_id, role), which was correct when a person+role
    could only ever be ONE album-wide fact, but broke the moment a single
    source started legitimately producing several DISTINCT facts for the
    same person+role text on one album (Ernest Ranglin - Guitar on track
    7 vs track 15 vs a general album-level inference -- all real, all
    different). Without scope in the key, each one silently overwrote the
    last instead of staying separate -- confirmed live: a 79-credit AI
    Web Search commit left exactly ONE surviving row for Ranglin/Guitar
    (whichever track processed last), the others gone with no error.
    Likely also affects any pre-existing MB/Discogs track-scoped credits
    from Personnel Engine v2 (2026-07-08) with a repeated role text
    across tracks -- not remediated here, per John's own call 2026-07-10
    that the current database is disposable while this tool is still
    being finessed; only new commits need to be correct going forward.

    Uses SQLite's `IS` operator (not `=`) for evidence_scope/
    evidence_detail specifically -- `=` never matches a NULL column
    against a NULL parameter, which would break the common album-scope
    case (evidence_detail is always NULL there); `IS` handles NULL
    correctly on both sides while still being a normal bound parameter.

    role comparison is case/whitespace-insensitive (John, 2026-07-10,
    caught live: re-running Personnel Scout on the same album produced
    "Clancy Eccles: Producer" three times with no dedup at all). The AI
    Web Search tier's output isn't byte-identical run to run -- the same
    real fact can come back as "Producer" one time and differently-cased
    or whitespace-padded another, and the OLD exact-string match treated
    any such variance as a genuinely different role, inserting a new row
    instead of updating the existing one. LOWER(TRIM()) matches the
    normalization already applied to source_id just below it.
    """
    rows = db_engine.execute_query(
        "SELECT id, confidence FROM edges WHERE source_type=? "
        "AND LOWER(TRIM(source_id))=LOWER(TRIM(?)) AND target_id=? AND LOWER(TRIM(role))=LOWER(TRIM(?)) "
        "AND evidence_scope IS ? AND evidence_detail IS ?",
        (source_type, source_id, target_id, role, evidence_scope, evidence_detail)
    )
    return rows[0] if rows else None


def upsert_edge(source_type, source_id, target_type, target_id, relation_type, role,
                 confidence, provenance, evidence_scope=None, evidence_detail=None, weight=1.0):
    """
    If no edge matches (source_id, target_id, role, evidence_scope,
    evidence_detail), INSERT it. If one already exists, overwrite it in
    place -- UPDATE, not a second row -- but only when the new confidence
    is >= the existing row's, so a weaker duplicate (e.g. a stale
    re-save) never downgrades a fact a stronger source already
    corroborated. Returns (action, edge_id) where action is
    "inserted" | "updated" | "skipped".
    """
    existing = find_matching_edge(source_type, source_id, target_id, role, evidence_scope, evidence_detail)

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
