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
from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)
from common import config_handler
from common.audio_check import mp3val_problems

# --- [ CONFIGURATION ] ---
MP3VAL_EXE = config_handler.MP3VAL_EXE
REPAIR_DIR = config_handler.DATA_DIR / "repair"
QUEUE_LOG  = REPAIR_DIR / "remediation_queue.log"

def check_health(root_path, health_summary=None):
    """
    Scans and repairs .mp3 files. Runs mp3val in fix mode, then verifies;
    anything still corrupt after the fix attempt is queued to
    remediation_queue.log for the Repair tool. Never halts the batch --
    every file is checked and tagging continues regardless of findings.
    Yields HTML log entries for the streaming console.

    health_summary, if given a dict, is populated in place with this
    run's counts (vanished/queued/repaired) -- lets the caller fold the
    outcome into MetaForge.log's own "Intelli-Tagger" audit block later
    (John's request, 2026-08-08) without this generator's own console-
    only yields being the only record of what happened.
    """
    # Ensure remediation directory exists
    REPAIR_DIR.mkdir(parents=True, exist_ok=True)

    target_files = list(root_path.glob("**/*.mp3"))
    if not target_files:
        yield event("error", "No MP3 files were found in the album folder")
        return

    yield event("step", f"Step 1: Health check of {len(target_files)} track{'s' if len(target_files) != 1 else ''}")

    repair_count = 0
    queued_count = 0
    vanished_count = 0
    for f in target_files:

        if not f.exists():
            vanished_count += 1
            yield event("error", "File went missing before the health check. Skipped: investigate before re-running this album", file=f.name)
            continue

        try:
            # mp3val always exits 0 (measured 2026-11-16): damage shows only
            # as WARNING/ERROR lines, so the 1.x return-code checks below
            # never saw any. Check first; fix only what needs it.
            if not mp3val_problems(f):
                continue
            # Attempt a container/header-level fix (keeps a .bak, see below)
            subprocess.run([str(MP3VAL_EXE), "-f", str(f)], capture_output=True, text=True)
            # Verify the fix actually resolved the issue
            still_damaged = bool(mp3val_problems(f)) if f.exists() and f.stat().st_size else True

            # Defense-in-depth around mp3val's own in-place rewrite: if the
            # "fixed" file is gone or has collapsed to (near-)zero bytes,
            # that's worse than the original corruption it was trying to
            # repair. mp3val writes an original.mp3.bak backup by default
            # (no -nb flag is passed) -- restore it rather than leaving an
            # empty/missing file behind.
            if not f.exists() or f.stat().st_size == 0:
                bak = f.with_name(f.name + ".bak")
                if bak.exists() and bak.stat().st_size > 0:
                    bak.replace(f)
                    yield event("error", "The repair produced an empty file, so it was restored from its backup. Investigate before trusting this album", file=f.name)
                else:
                    vanished_count += 1
                    yield event("error", "CRITICAL: the repair destroyed this file and no backup was found to restore. It may be unrecoverable", file=f.name)
                continue

            if still_damaged:
                _log_to_remediation_queue(f, "Bitstream Data Corruption (Intelli-Tagger)")
                queued_count += 1
            else:
                repair_count += 1

        except Exception as e:
            yield event("error", f"Health check failed: {e}", file=f.name)

    if vanished_count > 0:
        yield event("warning", f"{vanished_count} file{'s' if vanished_count != 1 else ''} went missing during the health check. The run continues with the rest, but this album needs investigating")

    if queued_count > 0:
        yield event("warning", f"{queued_count} file{'s' if queued_count != 1 else ''} couldn't be repaired here and {'were' if queued_count != 1 else 'was'} queued for the Repair tool")
    if repair_count > 0:
        yield event("success", f"Health check done: {repair_count} file{'s' if repair_count != 1 else ''} repaired")
    if queued_count == 0 and repair_count == 0:
        yield event("success", "Health check done: no repairs needed")

    if health_summary is not None:
        health_summary["vanished"] = vanished_count
        health_summary["queued"] = queued_count
        health_summary["repaired"] = repair_count

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
        text = QUEUE_LOG.read_text(encoding="utf-8") if QUEUE_LOG.exists() else ""
        with open(QUEUE_LOG, "a", encoding="utf-8") as f:
            # Never glue onto a last line that has no newline.
            f.write(("\n" if text and not text.endswith("\n") else "") + f"{resolved} | {reason}\n")
    except Exception:
        pass
# --- END OF FILE health_engine.py ---