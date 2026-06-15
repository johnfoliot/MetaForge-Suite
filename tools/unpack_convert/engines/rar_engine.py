# --- START OF FILE rar_engine.py ---
# ======================================================================
# MetaForge Spoke: RAR Engine
# Role: Extracts RAR archives, handles spanned volumes, real-time progress.
# Build 1.1.5: Accessibility Hardening (WCAG 2.2 SC 1.1.1).
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
AUDIO_EXT = {'.flac', '.ape', '.wav', '.m4a', '.mp3', '.ogg', '.wma', '.wv'}

def extract_rar(root, report_data):
    """
    Finds and extracts .rar archives. 
    Checks report_data to prevent Step 1 header duplication.
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
            if part_match.group(2) in ["1", "01"]:
                rar_heads.append(r)
        else:
            rar_heads.append(r)
            rar_sets[r.stem] = [r]

    if not rar_heads:
        return 

    if not UNRAR_EXE.exists():
        yield f'<div class="status-error"><span aria-hidden="true">❌</span> System Error: unrar.exe missing.</div>'
        return

    for rar_path in rar_heads:
        try:
            # 1. Step 1 Header Control
            if not report_data.get('extraction_occurred', False):
                yield f'<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:5px;"><img src="/ui/images/rar.png" alt="" aria-hidden="true" style="margin-left:3px; height:14px; width:auto;"> Step 1: Extracting Original Audio Source:<br><span style="margin-left:25px; color:var(--text-output)"> {rar_path.name}</span></div>'
                report_data['extraction_occurred'] = True
            else:
                yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Extracting {rar_path.name}</div>'
            
            report_data['extraction']['source'] = f"RAR Archive: {rar_path.name}"

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                process = subprocess.Popen(
                    [str(UNRAR_EXE), "x", "-y", str(rar_path), str(tmp_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                for line in iter(process.stdout.readline, ''):
                    perc_match = re.search(r'(\d+)%', line)
                    if perc_match:
                        yield f"<!-- PROGRESS:1:{perc_match.group(1)}:100 -->"

                process.wait()

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

            yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">✨</span> Extraction Successful: {rar_path.name}</div>'

            # 4. DELETE SOURCE SET
            base_key = re.search(r'(.*)\.part\d+\.rar$', rar_path.name, re.I)
            set_key = base_key.group(1) if base_key else rar_path.stem
            
            if set_key in rar_sets:
                for part_file in rar_sets[set_key]:
                    try:
                        if part_file.name not in report_data['deletions']:
                            report_data['deletions'].append(part_file.name)
                        part_file.unlink()
                    except:
                        pass
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> RAR source set deleted.</div>'

        except Exception as e:
            yield f'<div class="status-error"><span aria-hidden="true">❌</span> RAR Spoke Error: {str(e)}</div>'

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