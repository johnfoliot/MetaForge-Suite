# --- START OF FILE edge_normalizer.py ---
import re
import json
import os
from tools.personnel.edge_constants import RelationType

def load_config():
    """Loads classification configuration from absolute path."""
    config_path = r'D:\MetaForge Suite\tools\personnel\performance.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    print(f"CRITICAL ERROR: Could not find performance.json at {config_path}")
    return {"mappings": {}, "patterns": {}}

def is_junk_role(raw_role: str, config: dict) -> bool:
    """
    True if this role is a known non-musical package/administrative
    credit (photography, album design, liner notes, etc.) -- carries no
    IPM "connective tissue" value and John deletes these manually today.
    Checked as a substring match against performance.json's junk_roles
    list, case-insensitive. Checked BEFORE classification -- a junk role
    is excluded outright, never even reaches ASSOCIATED_WITH.
    """
    clean_role = raw_role.strip().lower()
    junk_terms = config.get("junk_roles", [])
    return any(term in clean_role for term in junk_terms)


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