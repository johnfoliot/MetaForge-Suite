# --- START OF FILE context_engine.py ---
# ======================================================================
# MetaForge Spoke: Context Engine
# Role: Manages .env parsing, manifest generation, and forensic auditing.
# Build 7.4.0: Frictionless Handoff (Working Directory Persistence).
# Physical Location: \tools\unpack_convert\engines\context_engine.py
# ======================================================================
import re
import json
import time
import os
from pathlib import Path
from flask import jsonify
from common import config_handler

def _read_env_fresh(env_path):
    """
    Internal Helper: Physically reads the .env file as text.
    Ensures 100% synchronization with disk state per Directive III.3.
    """
    target_env = Path(env_path)
    if not target_env.exists():
        target_env = Path(os.getenv('APPDATA')) / "MetaForge" / ".env"
    
    if target_env.exists():
        try:
            return target_env.read_text(encoding='utf-8')
        except Exception:
            return ""
    return ""

def get_policy(env_path):
    """
    Retrieves current filing policy from .env via fresh physical read.
    """
    content = _read_env_fresh(env_path)
    if content:
        p_match = re.search(r'MF_FILING_POLICY\s*=\s*"?([^"\s\n\r]*)', content)
        if p_match:
            return p_match.group(1).strip().upper()
    return "STANDARD"

def handle_interview_fetch(env_path):
    """
    Retrieves fresh system context for UI synchronization.
    This is called every time the tool is loaded in the SPA Stage.
    """
    content = _read_env_fresh(env_path)
    
    # 1. Atomic Policy Sync
    policy = "STANDARD"
    p_match = re.search(r'MF_FILING_POLICY\s*=\s*"?([^"\s\n\r]*)', content)
    if p_match:
        policy = p_match.group(1).strip().upper()

    # 2. Atomic Consent Sync
    consent = False
    c_match = re.search(r'MF_UNPACKER_CONSENT\s*=\s*"?([^"\s\n\r]*)', content)
    if c_match:
        consent = c_match.group(1).strip().upper() == "TRUE"

    # 3. Category Discovery (For Enhanced Policy)
    categories = []
    if policy == "ENHANCED":
        cat_path = config_handler.APPDATA_MF / "categories.json"
        if cat_path.exists():
            try:
                cat_data = json.loads(cat_path.read_text(encoding='utf-8'))
                categories = cat_data.get('silos', [])
            except Exception:
                pass

    return jsonify({
        "status": "success",
        "policy": policy,
        "categories": sorted(categories),
        "stored_consent": consent
    })

def write_audit_log(root, report_data):
    """
    Writes or Appends to the forensic MetaForge.log.
    Build 7.4.0: Maintained forensic track count logging.
    """
    log_path = root / "MetaForge.log"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    
    log_content = [
        f"\n{'='*60}",
        f"METAFORGE AUDIT LOG | {timestamp}",
        f"MetaForge Process: {report_data.get('phase', 'Unpack & Convert')}",
        f"{'-'*60}"
    ]

    # Forensic Track Count Persistence
    final_count = report_data.get('final_track_count', 0)
    log_content.append(f"TRACKS: {final_count} audio files identified in final structure.")
    
    if report_data.get('extraction'):
        source_name = report_data['extraction'].get('source', 'Unknown')
        unpacked_count = report_data['extraction'].get('count', 0)
        if unpacked_count > 0:
            log_content.append(f"SOURCE: {source_name}")
            log_content.append(f"UNPACKED: {unpacked_count} files.")

    if report_data.get('conversion'):
        log_content.append(f"CONVERSION: Converted {len(report_data['conversion'])} files to MP3 VBR (V0).")
        for f in sorted(report_data['conversion']):
            log_content.append(f"  > {f}")

    if report_data.get('artwork'):
        log_content.append(f"ARTWORK: Moved {len(report_data['artwork'])} images to /art folder.")
        for f in sorted(report_data['artwork']):
            log_content.append(f"  [+] {f}")

    if report_data.get('deletions'):
        log_content.append(f"PURGE: Permanently deleted {len(report_data['deletions'])} legacy files:")
        for f in sorted(report_data['deletions']):
            log_content.append(f"  [X] {f}")

    log_content.append(f"{'='*60}\n")
    
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write("\n".join(log_content))
    except Exception:
        pass

def update_consent_status(env_path, status_str):
    """
    Physically updates the .env file to persist the Unpacker Consent choice.
    """
    target_env = Path(env_path)
    if not target_env.exists():
        target_env = Path(os.getenv('APPDATA')) / "MetaForge" / ".env"
    
    if not target_env.exists(): 
        return
    
    content = target_env.read_text(encoding='utf-8')
    key = "MF_UNPACKER_CONSENT"
    value = status_str.upper()
    
    # Surgical Regex Update to preserve other .env keys
    pattern = re.compile(rf'^{key}\s*=.*$', re.MULTILINE)
    
    if pattern.search(content):
        new_content = pattern.sub(f"{key}={value}", content)
    else:
        new_content = content.rstrip() + f"\n{key}={value}\n"
        
    target_env.write_text(new_content, encoding='utf-8')

def generate_manifest(root, artist, album, category, library_type, track_count=0):
    """
    Creates the JSON manifest for Step 2 ingestion (Intelli-Tagger).
    Build 7.4.0: Includes 'working_directory' for frictionless tool handoff.
    """
    manifest_path = root / "manifest.json"
    local_ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    
    data = {
        "artist_seed": artist,
        "album_seed": album,
        "category_seed": category,
        "library_type": library_type,
        "track_count": track_count,
        "working_directory": str(root.resolve()),
        "prepared_at": local_ts
    }
    
    try:
        manifest_path.write_text(json.dumps(data, indent=4), encoding='utf-8')
    except Exception:
        pass

# --- END OF FILE context_engine.py ---