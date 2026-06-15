# --- START OF FILE cue_engine.py ---
# ======================================================================
# MetaForge Spoke: CUE Engine
# Role: Parses CUE sheets and executes FFmpeg splitting.
# Build 7.1.7: Hardened Accessibility (Wrapped Emojis).
# ======================================================================
import re
import os
import subprocess
from pathlib import Path
from common.config_handler import FFMPEG_EXE

# Audio extensions that qualify as "Discrete Tracks"
DISCRETE_EXT = {'.flac', '.mp3', '.m4a', '.ape', '.wav'}

def split_cue(root, artist, report_data):
    """
    Scans for CUE sheets. 
    Checks report_data to prevent Step 1 header duplication.
    """
    cue_files = list(root.glob("*.cue"))
    if not cue_files:
        return

    # 1. DISCRETE PRESENCE CHECK
    discrete_count = 0
    for f in root.iterdir():
        if f.suffix.lower() in DISCRETE_EXT:
            if re.match(r'^\d+', f.name):
                discrete_count += 1
    
    if discrete_count >= 2:
        if not report_data.get('extraction_occurred', False):
            yield f'<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:5px;"><span aria-hidden="true">📦</span> Step 1: Discrete tracks detected ({discrete_count}). Unpacking not required.</div>'
            yield "<!-- PROGRESS:1:1:1 -->"
            report_data['extraction_occurred'] = True
        return

    # 2. SELECTION & VALIDATION
    for cue_path in cue_files:
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
            file_references = re.findall(r'FILE\s+"(.*?)"', content)
            if len(file_references) > 1:
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888;"><span aria-hidden="true">ℹ️</span> Non-compliant CUE ignored: {cue_path.name}</div>'
                continue

            if not file_references: continue
            source_audio = _find_audio_source(cue_path.parent, file_references[0])
            
            if not source_audio:
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888;"><span aria-hidden="true">ℹ️</span> Ghost CUE ignored: {cue_path.name} (Blob missing).</div>'
                continue

            # Header Control with Accessibility Guard
            if not report_data.get('extraction_occurred', False):
                yield f'<div class="status-api" style="margin-top:5px; border-top:1px solid #333; padding-top:5px;"><img src="/ui/images/cue.png" alt="" aria-hidden="true" style="margin-left:3px; height:14px; width:auto;"> Step 1: Splitting Original Audio Source:<br><span style="margin-left:25px; color:var(--text-output)"> {source_audio.name}</span></div>'
                report_data['extraction_occurred'] = True
            else:
                yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Splitting {source_audio.name}</div>'

            report_data['extraction']['source'] = f"CUE Bundle: {source_audio.name}"

            # 3. PARSE & SPLIT
            tracks = re.findall(r'TRACK (\d+) AUDIO.*?TITLE "(.*?)"', content, re.DOTALL)
            times = re.findall(r'INDEX 01 (\d{1,3}:\d{2}:\d{2})', content)
            
            total_tracks = len(tracks)
            for i, (num, title) in enumerate(tracks):
                t_start = _format_ts(times[i])
                t_dur = ["-to", _format_ts(times[i+1])] if i+1 < len(times) else []
                
                safe_title = re.sub(r'[\\/*?:\u0022<>|]', '', title).strip()
                track_id = str(int(num)) 
                out_name = f"{track_id} - {artist} - {safe_title}.wav"
                out_path = cue_path.parent / out_name
                
                res = subprocess.run([
                    str(FFMPEG_EXE), "-i", str(source_audio), 
                    "-ss", t_start] + t_dur + 
                    [str(out_path), "-y", "-loglevel", "panic"]
                )
                
                if res.returncode == 0:
                    # FIX: Wrapped Outbox emoji in aria-hidden span
                    yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">📤</span> Unpacked: {out_name}</div>'
                    report_data['extraction']['count'] += 1
                    yield f"<!-- PROGRESS:1:{i+1}:{total_tracks} -->"

            # 4. DELETE SOURCE
            try:
                if source_audio.name not in report_data['deletions']:
                    report_data['deletions'].append(source_audio.name)
                if cue_path.name not in report_data['deletions']:
                    report_data['deletions'].append(cue_path.name)
                
                source_audio.unlink()
                cue_path.unlink()
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> Monolithic source deleted.</div>'
            except: pass

        except Exception: continue

def _find_audio_source(directory, filename):
    if (directory / filename).exists(): return directory / filename
    stem = Path(filename).stem
    for ext in ['.flac', '.ape', '.wav', '.wv']:
        if (directory / f"{stem}{ext}").exists(): return directory / f"{stem}{ext}"
    return None

def _format_ts(ts):
    parts = ts.split(':')
    m_raw, s, f = int(parts[0]), int(parts[1]), int(parts[2])
    ms = int(f * (1000 / 75))
    h = m_raw // 60
    m = m_raw % 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

# --- END OF FILE cue_engine.py ---