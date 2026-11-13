# --- START OF FILE janitor_engine.py ---
# ======================================================================
# MetaForge Spoke: Janitor Engine
# Role: Final folder sanitation, asset siloing, and legacy deletion.
# Build 7.3.0: Source-Class Preservation (janitor never deletes sources).
# Physical Location: \tools\unpack_convert\engines\janitor_engine.py
# ======================================================================
import os
import re
import shutil
from pathlib import Path
from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)

# --- [ CONFIGURATION ] ---
ART_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf', '.tiff', '.bmp'}
ART_FOLDER_NAMES = {'scans', 'covers', 'artwork', 'graphics', 'images'}
SYSTEM_FILES = {"MetaForge.log", "manifest.json"}

# Source-class files: anything that IS (or contains) original audio.
# Build 7.3.0 rule: the janitor never deletes these. Only the engine that
# actually processed a source deletes it, and only after verified
# success (cue_engine / sacd_engine all-or-nothing rule, bitstream_engine
# post-conversion delete, zip/rar post-extraction delete). Anything
# source-class still on disk by Step 3 was therefore never successfully
# processed -- an unrecognized subfolder, a failed archive, a format no
# engine handles yet, a skipped duplicate -- and deleting it here would
# be silent data loss. Real case that motivated this (2026-10-01 review):
# .dsf tracks passed untouched through Steps 1-2 (no engine claimed
# them) and were then deleted here as "legacy cruft."
SOURCE_AUDIO_EXT = {
    '.flac', '.ape', '.wav', '.m4a', '.wma', '.ogg', '.aiff', '.aif',
    '.wv', '.shn', '.tta', '.dsf', '.dff', '.alac', '.opus'
}
SOURCE_CONTAINER_EXT = {'.zip', '.rar', '.7z', '.iso', '.bin', '.img'}
# Old-style spanned RAR volumes: .r00, .r01, ...
_RAR_VOLUME_RE = re.compile(r'^\.r\d{2}$')


def _is_source_class(ext):
    return (
        ext in SOURCE_AUDIO_EXT
        or ext in SOURCE_CONTAINER_EXT
        or bool(_RAR_VOLUME_RE.match(ext))
    )


def execute_cleanup(root, report_data):
    """
    Final janitorial pass for the provided directory.
    1. Consolidates artwork from sub-folders into local /art folder.
    2. Deletes non-standard, non-source files. Source-class files are
       always preserved (see SOURCE_AUDIO_EXT note above), as is any
       .cue sheet sitting in a folder that still holds a preserved
       source -- without its CUE, a preserved monolithic rip can't be
       retried.
    3. Performs a final discovery of the /art folder to signal Step 4.
    """
    yield event("step", "Step 3: Cleaning the album folder")

    if 'artwork' not in report_data:
        report_data['artwork'] = []
    report_data.setdefault('deletions', [])
    report_data.setdefault('preserved', [])

    failed_to_convert = report_data.get('failed_targets', [])
    preserved_failed = 0
    art_dir = root / "art"

    if not art_dir.exists():
        art_dir.mkdir(parents=True, exist_ok=True)

    moved_count = 0

    # Deletion is deferred until the whole tree has been scanned, so the
    # CUE-preservation check below can see every preserved source first.
    deletion_candidates = []
    folders_with_preserved_source = set()
    unprocessed_sources = []

    # 1. RECURSIVE ASSET MANAGEMENT
    for cur_root, dirs, files in os.walk(root, topdown=False):
        current_path = Path(cur_root)

        # PROTECT: Do not delete or move files already inside the local /art directory
        if current_path == art_dir:
            continue

        for f in files:
            f_p = current_path / f
            ext = f_p.suffix.lower()

            # A. Consolidate Graphics to the Local Silo Art Folder
            if ext in ART_EXTENSIONS:
                dest = art_dir / f
                if dest.exists():
                    dest = art_dir / f"{f_p.stem}_{moved_count}{ext}"

                try:
                    shutil.move(str(f_p), str(dest))
                    if f not in report_data['artwork']:
                        report_data['artwork'].append(f)
                    moved_count += 1
                except Exception:
                    pass
                continue

            # B. Never touch finished output or MetaForge's own files
            if ext == '.mp3' or f in SYSTEM_FILES:
                continue

            # C. Engine-registered failures (existing safety net)
            if f in failed_to_convert:
                preserved_failed += 1
                folders_with_preserved_source.add(current_path)
                continue

            # D. Source-class files: never deleted by the janitor
            if _is_source_class(ext):
                folders_with_preserved_source.add(current_path)
                rel = f_p.relative_to(root)
                unprocessed_sources.append(str(rel))
                if str(rel) not in report_data['preserved']:
                    report_data['preserved'].append(str(rel))
                continue

            # E. Everything else is a deletion candidate
            deletion_candidates.append(f_p)

    # 1b. DEFERRED DELETION PASS
    for f_p in deletion_candidates:
        if f_p.suffix.lower() == '.cue' and f_p.parent in folders_with_preserved_source:
            rel = str(f_p.relative_to(root))
            if rel not in report_data['preserved']:
                report_data['preserved'].append(rel)
            continue
        try:
            if f_p.name not in report_data['deletions']:
                report_data['deletions'].append(f_p.name)
            f_p.unlink()
        except Exception:
            pass

    # 2. FINAL ART DISCOVERY
    if art_dir.exists():
        for art_file in art_dir.iterdir():
            if art_file.is_file() and art_file.suffix.lower() in ART_EXTENSIONS:
                if art_file.name not in report_data['artwork']:
                    report_data['artwork'].append(art_file.name)

    # 3. FINAL STRUCTURE FLATTENING
    for cur_root, dirs, _ in os.walk(root, topdown=False):
        for d in dirs:
            d_p = Path(cur_root) / d
            is_disc_folder = any(d_p.name.lower().startswith(x) for x in ['disc', 'disk', 'cd', 'vol'])

            if d_p.name.lower() != 'art' and not is_disc_folder:
                try:
                    if not any(d_p.iterdir()):
                        d_p.rmdir()
                except Exception:
                    pass

    # 4. REPORTING
    total_art_discovered = len(report_data['artwork'])
    if total_art_discovered > 0:
        yield event("info", f"{total_art_discovered} image{'s' if total_art_discovered != 1 else ''} available in the art folder")

    n_del = len(report_data["deletions"])
    yield event("success", f"Cleanup done: {n_del} file{'s' if n_del != 1 else ''} deleted in this run")

    if preserved_failed > 0:
        one = preserved_failed == 1
        yield event("warning", f"{preserved_failed} source file{'' if one else 's'} {'was' if one else 'were'} kept "
                               f"because processing failed. The summary in MetaForge.log lists {'it' if one else 'them'}")

    if unprocessed_sources:
        n_unproc = len(unprocessed_sources)
        one = n_unproc == 1
        yield event("warning", f"{n_unproc} source file{'' if one else 's'} {'was' if one else 'were'} kept "
                               f"because no engine processed {'it' if one else 'them'}")
        for p in sorted(unprocessed_sources):
            yield event("detail", "Kept", file=p)

# --- END OF FILE janitor_engine.py ---
