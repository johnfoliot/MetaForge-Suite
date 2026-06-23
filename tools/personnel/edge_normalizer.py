# --- START OF FILE edge_normalizer.py ---
import re
import json
import os
from tools.personnel.edge_constants import RelationType

def load_config():
    """Loads classification configuration from performance.json."""
    config_path = 'performance.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {"mappings": {}, "patterns": {}}

def classify_role(raw_role: str, config: dict) -> tuple[str, float]:
    """
    Classifies a role based on config mappings and regex patterns.
    Returns a tuple of (relation_type_value, confidence_score).
    """
    clean_role = raw_role.strip().lower()
    
    # 1. Check direct mapping
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
    dictionaries including metadata scoring.
    """
    if not personnel_string:
        return []

    config = load_config()
    roles = [role.strip() for role in personnel_string.split(',')]
    normalized_list = []

    for role_entry in roles:
        # Extract evidence in parentheses
        match = re.search(r'\((.*?)\)', role_entry)
        evidence_detail = match.group(1) if match else None
        
        # Clean role name (remove parenthetical part)
        base_role = re.sub(r'\(.*?\)', '', role_entry).strip()
        
        # Determine classification and confidence
        relation_type, confidence = classify_role(base_role, config)
        
        # Determine scope
        evidence_scope = "track" if evidence_detail else "album"
        
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