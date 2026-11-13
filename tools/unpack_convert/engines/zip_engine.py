# --- START OF FILE zip_engine.py ---
# ======================================================================
# MetaForge Spoke: ZIP Engine
# Role: Extracts archives, executes ACR Discovery, and logs audit.
# Build 7.4.0: Same-Drive Staging + Cumulative Counts + Failure Registry.
# ======================================================================
import zipfile
import shutil
import tempfile
import os
from pathlib import Path

from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)

# --- [ CONFIGURATION ] ---
METADATA_JUNK = {'.ds_store', 'desktop.ini', 'thumbs.db', '__macosx', 'album_art_tips.txt'}
AUDIO_EXT = {'.flac', '.ape', '.wav', '.m4a', '.mp3', '.ogg', '.wma', '.wv', '.dsf', '.dff'}


def _register_failed(report_data, zip_path):
    """Adds the archive to failed_targets so the audit log and safety alert report it."""
    report_data.setdefault('failed_targets', [])
    if zip_path.name not in report_data['failed_targets']:
        report_data['failed_targets'].append(zip_path.name)


def extract_zip(root, report_data):
    """
    Finds and extracts .zip archives within the root.
    Implements ACR Discovery and Collision-Safe Hoisting.
    """
    zip_files = list(root.glob("*.zip"))
    if not zip_files:
        return

    total_files_to_unpack = 0
    valid_zips = []
    for zip_path in zip_files:
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                total_files_to_unpack += len(z.infolist())
                valid_zips.append(zip_path)
        except Exception:
            _register_failed(report_data, zip_path)
            yield event("error", "Archive is corrupt; the source was kept", file=zip_path.name)
            continue

    if total_files_to_unpack == 0:
        return

    cumulative_extracted = 0

    for zip_path in valid_zips:
        try:
            # 1. Step 1 Header Control
            if not report_data.get('extraction_occurred', False):
                yield event("step", "Step 1: Unzipping the original audio source", file=zip_path.name)
                report_data['extraction_occurred'] = True
            else:
                yield event("info", "Additional source: unzipping", file=zip_path.name)

            report_data['extraction']['source'] = f"ZIP Archive: {zip_path.name}"

            # Staged inside the album folder (not the system temp dir) so
            # the hoist below is a same-drive rename, not a full cross-
            # drive copy of every file -- the album lives on D:/the DAS,
            # the system temp dir is on C:. Leading dot keeps it out of
            # the way; TemporaryDirectory still removes it on exit.
            with tempfile.TemporaryDirectory(prefix=".mf_zip_", dir=str(root)) as tmp_dir:
                tmp_path = Path(tmp_dir)

                # Any CRC or read error during extract() raises here and
                # drops to the except below -- the hoist and the source
                # deletion are never reached on a failed extraction.
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    file_list = zip_ref.infolist()
                    for member in file_list:
                        zip_ref.extract(member, tmp_path)
                        cumulative_extracted += 1
                        yield signal("progress", phase=1, current=cumulative_extracted, total=total_files_to_unpack)

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

                # Accumulate, don't overwrite -- multiple archives in one
                # album previously left only the last one's count in the
                # audit log.
                report_data['extraction']['count'] += moved_count
                yield event("success", f"{moved_count} audio item{'s' if moved_count != 1 else ''} moved to the album folder")

            yield event("success", "Extraction successful", file=zip_path.name)

            # 5. DELETE SOURCE (Forensic Logging)
            try:
                if zip_path.name not in report_data['deletions']:
                    report_data['deletions'].append(zip_path.name)

                zip_path.unlink()
                yield event("success", "ZIP source file deleted after a verified extraction")
            except Exception:
                pass

        except Exception as e:
            _register_failed(report_data, zip_path)
            yield event("error", f"ZIP extraction failed: {e}. The source was kept", file=zip_path.name)

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

# --- END OF FILE zip_engine.py ---
