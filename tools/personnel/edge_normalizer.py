# --- START OF FILE edge_normalizer.py ---
import re
import json
import os
import hashlib
from tools.personnel.edge_constants import RelationType

def load_config():
    """Loads classification configuration from absolute path."""
    config_path = r'D:\MetaForge Suite\tools\personnel\performance.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    print(f"CRITICAL ERROR: Could not find performance.json at {config_path}")
    return {"mappings": {}, "patterns": {}}

def normalize_identity_text(text: str) -> str:
    """
    Shared normalization used before any name/title is hashed into an
    identity key (mf_artist_id, mf_id). Collapses punctuation variance --
    commas, periods, exclamation/question marks, repeated whitespace --
    so the same real artist or album doesn't fragment into separate
    identities over trivial formatting differences: a stray comma
    (John's edges-table audit, 2026-07-31: "Al Jackson Jr." / "Al
    Jackson, Jr." split 3 albums / 6 albums across two mf_artist_id
    rows), or a missing "!" on an album title imported from MusicBrainz
    vs however a later retag resolves it (same failure mode, one level
    up -- mf_id fragmenting instead of mf_artist_id).

    Deliberately leaves parentheses/brackets (and their contents),
    colons, ampersands, apostrophes, and hyphens untouched -- those
    routinely distinguish one real release or name from another (an
    edition marker, a subtitle, a contraction, a compound word), unlike
    trailing emphasis punctuation which never does.
    """
    clean = (text or "").strip().lower()
    for ch in (",", ".", "!", "?"):
        clean = clean.replace(ch, "")
    return re.sub(r'\s+', ' ', clean).strip()


def normalize_artist_name(name: str) -> str:
    """Canonical form used before an artist name is hashed into mf_artist_id."""
    return normalize_identity_text(name)


def hash_artist_identity(name: str) -> str:
    """The one true mf_artist_id derivation -- sha256 of the normalized name."""
    return hashlib.sha256(normalize_artist_name(name).encode('utf-8')).hexdigest()


def hash_album_identity(artist: str, album: str) -> str:
    """
    The one true mf_id derivation -- sha256 of the normalized
    "artist|album" pair. Same rationale as hash_artist_identity, applied
    to the album-identity key that library_master/tracks.mf_id and
    edges.source_id (source_type='album') all key off of.
    """
    a = normalize_identity_text(artist)
    b = normalize_identity_text(album)
    return hashlib.sha256(f"{a}|{b}".encode('utf-8')).hexdigest()


def is_junk_role(raw_role: str, config: dict) -> bool:
    """
    True if this role is a known non-musical package/administrative
    credit (photography, album design, liner notes, etc.) -- carries no
    IPM "connective tissue" value and John deletes these manually today.
    Checked BEFORE classification -- a junk role is excluded outright,
    never even reaches ASSOCIATED_WITH.

    Word-boundary matching, not plain substring (John's 2026-08-01
    report): a bare `term in clean_role` check made "mix" (added that day
    to reject Mix/Mixed By/Mixing/Mixer credits) also swallow "Remix",
    "Remixing", "Remix Producer", "Remix Engineer" -- a real creative
    credit, not the technical mixing-engineer role being targeted. \\b
    only requires a boundary BEFORE the term (not after), so it still
    catches every inflected form a short root term is meant to
    (mix -> mixed/mixing/mixer), just not when it's glued onto a longer
    word with no boundary in front of it (re + mix). Known residual gap:
    a compound "Remix [Mixed By]"-style credit still matches, because the
    bracket itself creates a fresh word boundary right before "Mixed" --
    fixing that needs role-aware bracket handling, not just a matching
    strategy change, and hasn't been asked for yet.
    """
    clean_role = raw_role.strip().lower()
    junk_terms = config.get("junk_roles", [])
    return any(re.search(r'\b' + re.escape(term), clean_role) for term in junk_terms)


def is_junk_name(raw_name: str, config: dict) -> bool:
    """
    True if this is a known non-entity placeholder name (Discogs/
    MusicBrainz/Wikipedia's own filler for an unidentified or aggregate
    credit -- "Unknown Artist", "Various", etc.), not a real person or
    group. Exact match after strip/lower, unlike is_junk_role's substring
    match -- a real name could legitimately contain a word like "unknown"
    as part of a longer name, so this must not false-positive on that.
    """
    clean_name = (raw_name or "").strip().lower()
    return clean_name in set(config.get("junk_names", []))


def apply_role_alias(raw_role: str, config: dict) -> str:
    """
    Rewrites certain raw role text to a canonical replacement, before
    junk-filtering/classification -- distinct from is_junk_role: not
    every administratively-flavored credit should be REJECTED, some
    should just be RECLASSIFIED as something else entirely. E.g.
    "Executive Producer"/"Executive-Producer" are A&R-flavored by their
    raw text, but John's own established manual practice (2026-08-10,
    following his "A&R has zero IPM value" call) has been to treat the
    credited person as simply a Producer, not to reject the credit
    outright -- role_aliases in performance.json makes that automatic,
    rewriting both the stored/displayed role text AND what gets
    classified to "Producer", same as if it had been entered that way
    from the start. Exact match (not substring, unlike is_junk_role) --
    an alias is a precise, deliberate text swap, not a broad category
    filter.
    """
    clean_role = raw_role.strip().lower()
    aliases = config.get("role_aliases", {})
    return aliases.get(clean_role, raw_role)


def classify_role(raw_role: str, config: dict) -> tuple[str, float]:
    """
    Classifies a role based on config mappings and regex patterns.
    Returns a tuple of (relation_type_value, confidence_score).
    """
    clean_role = raw_role.strip().lower()

    # 1. Check direct mapping
    # Note: Ensure your performance.json keys are lowercase to match this
    mappings = config.get("mappings", {})
    if clean_role in mappings:
        return RelationType[mappings[clean_role]].value, 0.9

    # 2. Check regex patterns
    patterns = config.get("patterns", {})
    for pattern, relation in patterns.items():
        if re.search(pattern, clean_role):
            return RelationType[relation].value, 0.9

    # 3. Fallback
    return RelationType.ASSOCIATED_WITH.value, 0.5

def normalize_personnel(personnel_string: str) -> list[dict]:
    """
    Parses a comma-separated string of roles into a list of normalized 
    dictionaries using a strict, multi-step pipeline.
    """
    if not personnel_string:
        return []

    config = load_config()
    # Split by comma but respect commas inside parentheses
    raw_roles = re.split(r',(?![^\(]*\))', personnel_string)
    normalized_list = []

    for role_entry in raw_roles:
        # Step 1: Strip HTML artifacts (e.g., <small>)
        text = re.sub(r'<[^>]+>', '', role_entry)
        
        # Step 2: Qualifier Isolation
        evidence_detail = None
        evidence_scope = "album"
        
        match = re.search(r'\((.*?)\)', text)
        if match:
            qualifier = match.group(1).strip()
            # Numeric track data check (rejects date ranges and text)
            if re.match(r'^\s*[\d,\s\-\–]+\s*$', qualifier) and not re.search(r'\d{4}', qualifier):
                evidence_detail = qualifier
                evidence_scope = "track"
            else:
                evidence_detail = None
                evidence_scope = "album"
            
            # Remove parenthetical block for classification
            text = re.sub(r'\(.*?\)', '', text)
        
        # Step 3: Base Role Normalization
        final_role = text.strip().lower()

        # Step 3.4: Role aliasing -- some raw text gets rewritten to a
        # canonical replacement (e.g. "Executive Producer" -> "Producer")
        # rather than junk-rejected or classified as its literal text
        # would suggest. Must run before the junk filter below, since an
        # alias can rescue a role that would otherwise be caught by it.
        aliased_role = apply_role_alias(final_role, config)
        if aliased_role != final_role:
            role_entry = aliased_role
            final_role = aliased_role.strip().lower()

        # Debug Output
        print(f"DEBUG: Original: [{role_entry}], Cleaned: [{final_role}], Qualifier: [{evidence_detail}]")

        # Step 3.5: Junk filter -- a non-musical package/admin credit
        # (photography, album design, liner notes, etc.) is excluded
        # entirely here, never added to normalized_list at all, rather
        # than landing in ASSOCIATED_WITH for John to delete by hand.
        if is_junk_role(final_role, config):
            continue

        # Step 4: Classification
        relation_type, confidence = classify_role(final_role, config)
        
        normalized_list.append({
            "source_type": "album",
            "source_id": None,
            "target_type": "artist",
            "target_id": None,
            "relation_type": relation_type,
            "role": role_entry,
            "evidence_scope": evidence_scope,
            "evidence_detail": evidence_detail,
            "confidence": confidence,
            "weight": 1.0
        })
        
    return normalized_list
# --- END OF FILE edge_normalizer.py ---