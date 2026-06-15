# --- START OF FILE it_context_engine.py ---
# ======================================================================
# MetaForge Engine: Intelli-Tagger Context (Phase 1)
# Role: Manages the Audit Pair (manifest.json & MetaForge.log).
# Build 1.0.2: Renamed to prevent Namespace Collision with UPK tool.
# Physical Location: \tools\intelli-tagger\engines\it_context_engine.py
# ======================================================================
import json
import os
from pathlib import Path
from datetime import datetime

def initialize_audit_pair(root_path, seeds):
    """
    Phase 1 Logic: Ingests or initializes the MetaForge forensic trail.
    Yields HTML log entries for the streaming console.
    """
    manifest_path = root_path / "manifest.json"
    log_path = root_path / "MetaForge.log"
    

    # 1. MANIFEST LOGIC
    manifest_data = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">⚠️ Manifest Corrupt: {str(e)}. Re-initializing...</div>'
    else:
        yield '<div class="it-log-entry" style="margin-left:15px;">🛰️ No manifest found. Initializing new forensic trail...</div>'

    # Update manifest with current session seeds
    manifest_data.update({
        "artist_seed": seeds.get('artist'),
        "album_seed": seeds.get('album'),
        "mb_artist_id": seeds['mb_ids'].get('artist'),
        "mb_album_id": seeds['mb_ids'].get('album'),
        "mb_release_group_id": seeds['mb_ids'].get('group'),
        "mb_release_country": seeds['mb_ids'].get('country'),
        "working_directory": str(root_path.resolve()),
        "last_tool_run": "intelli-tagger",
        "timestamp": datetime.now().isoformat()
    })

    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=4)
    except Exception as e:
        yield f'<div class="it-log-entry it-val-red">🔥 Critical IO Failure: Cannot write manifest.json ({str(e)})</div>'

    # 2. LOG LOGIC
    if not log_path.exists():
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"METAFORGE FORENSIC AUDIT LOG\n{'='*30}\nInitialized: {datetime.now()}\n")
        except:
            pass

# --- END OF FILE it_context_engine.py ---