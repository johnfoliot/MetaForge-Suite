# --- START OF FILE zip_engine.py ---
# ======================================================================
# MetaForge Spoke: ZIP Engine
# Role: Extracts archives, executes ACR Discovery, and logs audit.
# Build 7.3.4: Accessibility Hardening (Wrapped Emojis).
# ======================================================================
import zipfile
import shutil
import tempfile
import os
from pathlib import Path

# --- [ CONFIGURATION ] ---
METADATA_JUNK = {'.ds_store', 'desktop.ini', 'thumbs.db', '__macosx', 'album_art_tips.txt'}
AUDIO_EXT = {'.flac', '.ape', '.wav', '.m4a', '.mp3', '.ogg', '.wma', '.wv'}

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
        except:
            yield f'<div class="status-error"><span aria-hidden="true">❌</span> Archive Corrupt: {zip_path.name}</div>'
            continue

    if total_files_to_unpack == 0:
        return

    cumulative_extracted = 0

    for zip_path in valid_zips:
        try:
            # 1. Step 1 Header Control
            if not report_data.get('extraction_occurred', False):
                yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><img src="/ui/images/zip.png" alt="" aria-hidden="true" style="margin-left:3px; height:14px; width:auto;"> Step 1: Unzipping Original Audio Source:<br><span style="margin-left:25px; color:var(--text-output)"> {zip_path.name}</span></div>'
                report_data['extraction_occurred'] = True
            else:
                yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Unzipping {zip_path.name}</div>'
            
            report_data['extraction']['source'] = f"ZIP Archive: {zip_path.name}"

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    file_list = zip_ref.infolist()
                    for member in file_list:
                        zip_ref.extract(member, tmp_path)
                        cumulative_extracted += 1
                        yield f"<!-- PROGRESS:1:{cumulative_extracted}:{total_files_to_unpack} -->"

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
                    
                report_data['extraction']['count'] = moved_count
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">📂</span> {moved_count} audio items moved to album directory.</div>'

            yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">✨</span> Extraction Successful: {zip_path.name}</div>'

            # 5. DELETE SOURCE (Forensic Logging)
            try:
                if zip_path.name not in report_data['deletions']:
                    report_data['deletions'].append(zip_path.name)
                
                zip_path.unlink()
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> ZIP source file deleted.</div>'
            except:
                pass

        except Exception as e:
            yield f'<div class="status-error"><span aria-hidden="true">❌</span> ZIP Spoke Error [{zip_path.name}]: {str(e)}</div>'

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