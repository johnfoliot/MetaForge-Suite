# --- START OF FILE rar_engine.py ---
# ======================================================================
# MetaForge Spoke: RAR Engine
# Role: Extracts RAR archives, handles spanned volumes, real-time progress.
# Build 1.2.0: Verified-Success Deletion + Same-Drive Staging.
# Physical Location: \tools\unpack_convert\engines\rar_engine.py
# ======================================================================
import subprocess
import shutil
import tempfile
import re
import os
from pathlib import Path
from common.config_handler import BIN_DIR

# --- [ CONFIGURATION ] ---
UNRAR_EXE = BIN_DIR / "unrar.exe"
METADATA_JUNK = {'.ds_store', 'desktop.ini', 'thumbs.db', '__macosx', 'album_art_tips.txt'}
AUDIO_EXT = {'.flac', '.ape', '.wav', '.m4a', '.mp3', '.ogg', '.wma', '.wv', '.dsf', '.dff'}


def _register_failed(report_data, files):
    """Adds every file in a RAR set to failed_targets so nothing downstream deletes it."""
    report_data.setdefault('failed_targets', [])
    for f in files:
        if f.name not in report_data['failed_targets']:
            report_data['failed_targets'].append(f.name)


def extract_rar(root, report_data):
    """
    Finds and extracts .rar archives.
    Checks report_data to prevent Step 1 header duplication.

    Build 1.2.0 (2026-10-01 review): the source set is deleted ONLY when
    unrar exits with code 0. Previously the exit code was never checked
    -- a corrupt archive, a missing .partN volume, or a password-protected
    RAR still hoisted whatever partial output existed and then deleted
    every part of the set. Same all-or-nothing rule cue_engine and
    sacd_engine already follow. unrar's exit code 1 ("non-fatal error")
    is treated as failure too: a warning still means unrar itself didn't
    vouch for a clean extraction, and the cost of keeping a good archive
    is zero while the cost of deleting a bad one is the album.
    """
    all_rars = list(root.glob("*.rar"))
    rar_heads = []
    rar_sets = {}

    for r in all_rars:
        part_match = re.search(r'(.*)\.part(\d+)\.rar$', r.name, re.I)
        if part_match:
            base_name = part_match.group(1)
            if base_name not in rar_sets:
                rar_sets[base_name] = []
            rar_sets[base_name].append(r)
            if int(part_match.group(2)) == 1:
                rar_heads.append(r)
        else:
            rar_heads.append(r)
            # Old-style spanned volumes (name.rar + name.r00, name.r01...)
            # belong to the same set -- previously only the .rar itself
            # was deleted, stranding the .rNN volumes.
            old_style = [p for p in root.iterdir()
                         if p.is_file() and p.stem == r.stem and re.match(r'^\.r\d{2}$', p.suffix, re.I)]
            rar_sets[r.stem] = [r] + sorted(old_style)

    if not rar_heads:
        return

    if not UNRAR_EXE.exists():
        for part_list in rar_sets.values():
            _register_failed(report_data, part_list)
        yield f'<div class="status-error"><span aria-hidden="true">❌</span> System Error: unrar.exe missing. RAR source(s) preserved, not processed.</div>'
        return

    for rar_path in rar_heads:
        base_key = re.search(r'(.*)\.part\d+\.rar$', rar_path.name, re.I)
        set_key = base_key.group(1) if base_key else rar_path.stem
        set_files = rar_sets.get(set_key, [rar_path])

        try:
            # 1. Step 1 Header Control
            if not report_data.get('extraction_occurred', False):
                yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><img src="/ui/images/rar.png" alt="" aria-hidden="true" style="margin-left:3px; height:32px; width:auto; margin-bottom:-12px;"> Step 1: Extracting Original Audio Source:<br><span style="margin-left:43px; color:var(--text-output)"> {rar_path.name}</span></div>'
                report_data['extraction_occurred'] = True
            else:
                yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Extracting {rar_path.name}</div>'

            report_data['extraction']['source'] = f"RAR Archive: {rar_path.name}"

            extraction_ok = False

            # Staged inside the album folder (not the system temp dir) so
            # the hoist below is a same-drive rename, not a full cross-
            # drive copy of every file -- the album lives on D:/the DAS,
            # the system temp dir is on C:. Leading dot keeps it out of
            # the way; TemporaryDirectory still removes it on exit.
            with tempfile.TemporaryDirectory(prefix=".mf_rar_", dir=str(root)) as tmp_dir:
                tmp_path = Path(tmp_dir)

                process = subprocess.Popen(
                    [str(UNRAR_EXE), "x", "-y", str(rar_path), str(tmp_path) + os.sep],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                last_line = ""
                for line in iter(process.stdout.readline, ''):
                    perc_match = re.search(r'(\d+)%', line)
                    if perc_match:
                        yield f"<!-- PROGRESS:1:{perc_match.group(1)}:100 -->"
                    stripped = line.strip()
                    if stripped and not perc_match:
                        last_line = stripped

                process.wait()

                if process.returncode != 0:
                    # Nothing is hoisted from a failed extraction -- the
                    # partial output is discarded with the temp dir, and
                    # the whole source set stays on disk for retry.
                    _register_failed(report_data, set_files)
                    reason = last_line or f"unrar exit code {process.returncode}"
                    yield f'<div class="status-error" style="font-size:0.75rem; margin-left:40px;"><span aria-hidden="true">❌</span> RAR extraction failed: {rar_path.name} — {reason}</div>'
                    yield f'<div class="status-error" style="font-size:0.75rem; margin-left:40px;"><span aria-hidden="true">⚠️</span> RAR source set preserved for retry ({len(set_files)} file(s)).</div>'
                else:
                    # --- [ ACR DISCOVERY & COLLISION-SAFE HOIST ] ---
                    content_root = _find_atomic_content_root(tmp_path)
                    moved_count = 0

                    for item in content_root.iterdir():
                        if item.name.lower() in METADATA_JUNK:
                            continue

                        dest = root / item.name

                        if item.is_dir() and dest.exists() and dest.is_dir():
                            for sub_item in item.iterdir():
                                sub_dest = dest / sub_item.name
                                if sub_dest.exists():
                                    sub_dest = dest / f"{sub_item.stem}_{moved_count}{sub_item.suffix}"
                                shutil.move(str(sub_item), str(sub_dest))
                                if sub_item.suffix.lower() in AUDIO_EXT:
                                    moved_count += 1
                            shutil.rmtree(str(item))
                        else:
                            if dest.exists() and not dest.is_dir():
                                dest = root / f"{item.stem}_{moved_count}{item.suffix}"

                            shutil.move(str(item), str(dest))

                            if item.is_dir():
                                moved_count += len([f for f in dest.rglob('*') if f.suffix.lower() in AUDIO_EXT])
                            elif item.suffix.lower() in AUDIO_EXT:
                                moved_count += 1

                    # Accumulate, don't overwrite -- multiple archives in
                    # one album previously left only the last one's count
                    # in the audit log.
                    report_data['extraction']['count'] += moved_count
                    yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:40px;"><span aria-hidden="true">📂</span> {moved_count} audio items moved to album directory.</div>'
                    extraction_ok = True

            if not extraction_ok:
                continue

            yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:40px;"><span aria-hidden="true">✨</span> Extraction Successful: {rar_path.name}</div>'

            # 4. DELETE SOURCE SET (verified success only)
            for part_file in set_files:
                try:
                    if part_file.name not in report_data['deletions']:
                        report_data['deletions'].append(part_file.name)
                    part_file.unlink()
                except Exception:
                    pass
            yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:40px;"><span aria-hidden="true">🧹</span> RAR source set deleted.</div>'

        except Exception as e:
            _register_failed(report_data, set_files)
            yield f'<div class="status-error"><span aria-hidden="true">❌</span> RAR Spoke Error [{rar_path.name}]: {str(e)} — source set preserved.</div>'

def _find_atomic_content_root(current_path):
    """
    Recursively drills until it finds a folder with multiple items
    OR any audio files.
    """
    all_items = [p for p in current_path.iterdir() if p.name.lower() not in METADATA_JUNK]
    audio_files = [p for p in all_items if p.suffix.lower() in AUDIO_EXT]
    sub_dirs = [p for p in all_items if p.is_dir()]

    if len(audio_files) == 0 and len(sub_dirs) == 1:
        return _find_atomic_content_root(sub_dirs[0])

    return current_path

# --- END OF FILE rar_engine.py ---
