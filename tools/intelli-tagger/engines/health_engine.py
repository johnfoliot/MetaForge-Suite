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

def check_health(root_path):
    """
    Scans and repairs .mp3 files. Runs mp3val in fix mode, then verifies;
    anything still corrupt after the fix attempt is queued to
    remediation_queue.log for the Repair tool. Never halts the batch --
    every file is checked and tagging continues regardless of findings.
    Yields HTML log entries for the streaming console.
    """
    # Ensure remediation directory exists
    REPAIR_DIR.mkdir(parents=True, exist_ok=True)

    target_files = list(root_path.glob("**/*.mp3"))
    if not target_files:
        yield '<div class="it-log-entry it-val-error" style="margin-left:1rem;">⚠️ No .mp3 files found in target directory.</div>'
        return

    yield f'<div class="it-log-entry it-val-gold" style="margin-top:10px;"><img src="ui/images/health.png" alt="" style="height:12px; width: auto;"> Running Health Check on {len(target_files)} tracks...</div>'

    repair_count = 0
    queued_count = 0
    for f in target_files:
        try:
            # Attempt a container/header-level fix
            fix_res = subprocess.run([str(MP3VAL_EXE), "-f", str(f)], capture_output=True, text=True)
            # Verify the fix actually resolved the issue
            verify_res = subprocess.run([str(MP3VAL_EXE), str(f)], capture_output=True, text=True)

            if verify_res.returncode != 0:
                _log_to_remediation_queue(f, "Bitstream Data Corruption (Intelli-Tagger)")
                queued_count += 1
            elif fix_res.returncode != 0:
                repair_count += 1

        except Exception as e:
            yield f'<div class="it-log-entry it-val-red" style="margin-left:1rem;">🔥 Health Engine Exception on {f.name}: {str(e)}</div>'

    if queued_count > 0:
        yield f'<div class="it-log-entry it-val-red" style="margin-left:1rem;">🩹 {queued_count} file(s) could not be structurally repaired and were queued for the Repair tool.</div>'
    if repair_count > 0:
        yield f'<div class="it-log-entry it-val-success" style="margin-left:1rem;">✅ Health Check complete. {repair_count} file(s) structurally aligned.</div>'
    if queued_count == 0 and repair_count == 0:
        yield '<div class="it-log-entry" style="margin-left:1rem;">✅ No structural header repairs required.</div>'

def _log_to_remediation_queue(file_path, reason="Bitstream Data Corruption"):
    """
    Appends the corrupt file path and error summary to the shared
    data/repair/remediation_queue.log for tools/repair to rebuild.
    Skips duplicate entries for a path already queued.
    """
    resolved = str(file_path.resolve())
    existing_paths = set()
    if QUEUE_LOG.exists():
        for line in QUEUE_LOG.read_text(encoding="utf-8").splitlines():
            existing_paths.add(line.split("|")[0].strip())

    if resolved in existing_paths:
        return

    try:
        with open(QUEUE_LOG, "a", encoding="utf-8") as f:
            f.write(f"{resolved} | {reason}\n")
    except Exception:
        pass
# --- END OF FILE health_engine.py ---