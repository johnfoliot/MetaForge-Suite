# --- START OF FILE janitor_engine.py ---
# ======================================================================
# MetaForge Spoke: Janitor Engine
# Role: Final folder sanitation, asset siloing, and legacy deletion.
# Build 7.2.0: Accessibility Hardening (WCAG 2.2 SC 1.1.1).
# Physical Location: \tools\unpack_convert\engines\janitor_engine.py
# ======================================================================
import os
import shutil
from pathlib import Path

# --- [ CONFIGURATION ] ---
ART_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf', '.tiff', '.bmp'}
ART_FOLDER_NAMES = {'scans', 'covers', 'artwork', 'graphics', 'images'}

def execute_cleanup(root, report_data):
    """
    Final janitorial pass for the provided directory. 
    1. Consolidates artwork from sub-folders into local /art folder.
    2. Deletes non-standard files (preserving failed conversions). 
    3. Performs a final discovery of the /art folder to signal Step 4.
    """
    yield '<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:5px;"><img src="/ui/images/cleanup.png" alt="" aria-hidden="true" style="margin-left:3px; height:15px; width:auto;"> Step 3: Cleaning Album Folder...</div>'

    if 'artwork' not in report_data:
        report_data['artwork'] = []

    failed_to_convert = report_data.get('failed_targets', [])
    preserved_count = 0
    art_dir = root / "art"
    
    if not art_dir.exists():
        art_dir.mkdir(parents=True, exist_ok=True)

    moved_count = 0

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
            
            # B. The Deletion Pass (Non-MP3, Non-System files)
            elif ext != '.mp3' and f not in ["MetaForge.log", "manifest.json"]:
                if f in failed_to_convert:
                    preserved_count += 1
                    continue

                try:
                    if f not in report_data['deletions']:
                        report_data['deletions'].append(f)
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
            is_disc_folder = any(d_p.name.lower().startswith(x) for x in ['disc', 'cd', 'vol'])
            
            if d_p.name.lower() != 'art' and not is_disc_folder:
                try:
                    if not any(d_p.iterdir()):
                        d_p.rmdir()
                except Exception:
                    pass

    # 4. REPORTING
    total_art_discovered = len(report_data['artwork'])
    if total_art_discovered > 0:
        yield f'<div class="status-message" style="color:var(--text-output); margin-left: 1rem;"><span aria-hidden="true">🖼️</span> Art Discovery: {total_art_discovered} image(s) available in /art.</div>'
    
    yield f'<div class="status-message" style="color:var(--text-message); margin-left: 1rem;"><span aria-hidden="true">🧹</span> Cleanup: {len(report_data["deletions"])} legacy files deleted.</div>'
    
    if preserved_count > 0:
        yield f'<div class="status-error" style="margin-top:5px;"><span aria-hidden="true">⚠️</span> SAFETY ALERT: {preserved_count} source file(s) were preserved because conversion failed. Check MetaForge.log.</div>'

# --- END OF FILE janitor_engine.py ---