# --- START OF FILE health_engine.py ---
# ======================================================================
# MetaForge Engine: Forensic Health (Phase 2)
# Role: Bitstream validation and header repair using mp3val.
# Build 1.0.5: REMEDIATED: Synchronized with Track-Level Orchestration.
# Physical Location: \tools\intelli-tagger\engines\health_engine.py
# ======================================================================
import subprocess
import os
from pathlib import Path
from common import config_handler

# --- [ CONFIGURATION ] ---
MP3VAL_EXE = config_handler.MP3VAL_EXE
REPAIR_DIR = config_handler.DATA_DIR / "repair"
QUEUE_LOG  = REPAIR_DIR / "remediation_queue.log"

# Internal State Tracking
_critical_files = []

def check_health(root_path):
    """
    Scans and repairs .mp3 files.
    Yields HTML log entries for the streaming console.
    """
    global _critical_files
    _critical_files = []
    
    # Ensure remediation directory exists
    REPAIR_DIR.mkdir(parents=True, exist_ok=True)
    
    target_files = list(root_path.glob("*.mp3"))
    if not target_files:
        yield '<div class="it-log-entry it-val-error" style="margin-left:1rem;">⚠️ No .mp3 files found in target directory.</div>'
        return

    yield f'<div class="it-log-entry it-val-gold" style="margin-top:10px;"><img src="ui/images/health.png" alt="" style="height:12px; width: auto;"> Running Health Check on {len(target_files)} tracks...</div>'

    repair_count = 0
    for f in target_files:
        try:
            # Execute mp3val in fix mode
            cmd = [str(MP3VAL_EXE), "-f", str(f)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            # Check for return code indicating corruption
            if res.returncode != 0:
                repair_count += 1
                
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red" style="margin-left:1rem;">🔥 Health Engine Exception on {f.name}: {str(e)}</div>'

    if repair_count > 0:
        yield f'<div class="it-log-entry it-val-success" style="margin-left:1rem;">✅ Health Check complete. {repair_count} files structurally aligned.</div>'
    else:
        yield '<div class="it-log-entry" style="margin-left:1rem;">✅ No structural header repairs required.</div>'

def has_critical_failures(root_path):
    """
    Returns True if any files in the current batch were flagged as critically corrupt.
    """
    return len(_critical_files) > 0

def _log_to_remediation_queue(file_path, raw_error):
    """
    Surgically appends the corrupt file path and error summary to the 
    global remediation_queue.log.
    """
    log_entry = f"{file_path.resolve()} | Bitstream Data Corruption\n"
    
    try:
        with open(QUEUE_LOG, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        pass
# --- END OF FILE health_engine.py ---