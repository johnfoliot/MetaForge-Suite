# --- START OF FILE bitstream_engine.py ---
# ======================================================================
# MetaForge Spoke: Bitstream Engine
# Role: Executes FFmpeg conversion and surgical ID3 enforcement.
# Build 7.4.9: Accessibility Hardening (WCAG 2.2 SC 1.1.1).
# ======================================================================
import os
import re
import subprocess
from pathlib import Path
from mutagen.id3 import ID3, ID3NoHeaderError, TXXX, TPE1, TALB, TIT2, TRCK, TPOS
from common.config_handler import FFMPEG_EXE, MP3VAL_EXE, DATA_DIR

# --- [ PROTOCOLS ] ---
EXTENSIONS_TO_CONVERT = {'.flac', '.ape', '.wav', '.m4a', '.wma', '.ogg', '.aiff', '.aif', '.wv', '.shn', '.tta'}
ID3_WHITELIST = {'TIT2', 'TPE1', 'TALB', 'TRCK', 'TYER', 'TDRC', 'TCON', 'TPOS'}
REMEDIATION_LOG = DATA_DIR / "repair" / "remediation_queue.log"


def _queue_for_repair(file_path, reason):
    """Appends a file to data/repair/remediation_queue.log for tools/repair to rebuild."""
    resolved = str(Path(file_path).resolve())
    REMEDIATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing_paths = set()
    if REMEDIATION_LOG.exists():
        for line in REMEDIATION_LOG.read_text(encoding="utf-8").splitlines():
            existing_paths.add(line.split("|")[0].strip())
    if resolved not in existing_paths:
        with open(REMEDIATION_LOG, "a", encoding="utf-8") as f:
            f.write(f"{resolved} | {reason}\n")


def _check_mp3val(mp3_path):
    """
    Runs mp3val in fix mode (handles container/header-level issues), then
    re-checks. If corruption remains, queues the file for tools/repair's
    FFmpeg raw-stream rebuild. Returns True if the file was queued.
    """
    try:
        subprocess.run([str(MP3VAL_EXE), "-f", str(mp3_path)], capture_output=True, timeout=30)
        verify = subprocess.run([str(MP3VAL_EXE), str(mp3_path)], capture_output=True, timeout=30)
        if verify.returncode != 0:
            _queue_for_repair(mp3_path, "Bitstream Data Corruption (Unpack/Convert)")
            return True
    except Exception:
        pass
    return False

def process_targets(root, artist, album, category, report_data, disc_num=1, total_discs=1, offset=0, is_multidisc=False, do_norm=False):
    """
    Identifies audio targets and executes conversion or normalization.
    """
    yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><img src="/ui/images/conversion.png" alt="" aria-hidden="true" style="margin-left:3px; height:15px; width:auto;"> Step 2: Format Conversion &amp; Metadata Cleaning...</div>'

    if 'failed_targets' not in report_data:
        report_data['failed_targets'] = []


    already_flagged = set(report_data['failed_targets'])
    all_files = [
        f for f in root.iterdir()
        if f.is_file() and (f.suffix.lower() in EXTENSIONS_TO_CONVERT or f.suffix.lower() == '.mp3')
        and f.name not in already_flagged
    ]

    if not all_files:
        yield "<!-- PROGRESS:2:1:1 -->"
        return

    # 2. SORTING
    def _strict_track_key(path):
        match = re.match(r'^(\d+)', path.name)
        track_num = int(match.group(1)) if match else 999
        ext_priority = 0 if path.suffix.lower() != '.mp3' else 1
        return (track_num, ext_priority, path.name)

    all_files.sort(key=_strict_track_key)

    # 3. DEDUPLICATION
    final_targets = []
    seen_tracks = set()
    for f_p in all_files:
        match = re.match(r'^(\d+)', f_p.name)
        track_id = int(match.group(1)) if match else None
        if track_id is not None:
            if track_id in seen_tracks: continue
            seen_tracks.add(track_id)
        final_targets.append(f_p)

    total_to_process = len(final_targets)

    # --- [ EMBEDDED ART RESCUE ] ---
    art_dir = root / "art"
    if not art_dir.exists() or not any(art_dir.iterdir()):
        if final_targets:
            _rescue_embedded_art(final_targets[0], root)

    # 4. EXECUTION LOOP
    for idx, f_p in enumerate(final_targets, 1):
        match = re.match(r'^(\d+)', f_p.name)
        claimed_track = int(match.group(1)) if match else None

        original_stem = f_p.stem
        parts = original_stem.split(" - ")
        if len(parts) >= 3:
            extracted_title = parts[-1].strip()
        elif len(parts) == 2:
            extracted_title = parts[1].strip()
        else:
            extracted_title = re.sub(r'^\d+[\s\.\-_]*', '', original_stem).strip()

        mp3_path = None
        
        if is_multidisc and claimed_track:
            filing_id = str(claimed_track) if claimed_track >= 100 else str((disc_num * 100) + claimed_track)
        else:
            filing_id = str(claimed_track if claimed_track else idx)
        
        is_already_mp3 = f_p.suffix.lower() == '.mp3'

        if not is_already_mp3 or do_norm:
            success = False
            for msg in _convert_to_mp3(f_p, artist, filing_id, extracted_title, do_norm, report_data):
                if "Converted" in msg:
                    success = True
                    match_conv = re.search(r': (.*?)</div>', msg)
                    if match_conv:
                        mp3_path = f_p.parent / match_conv.group(1)
                yield msg
            if not success:
                report_data['failed_targets'].append(f_p.name)
        else:
            mp3_path = _rename_existing_mp3(f_p, artist, filing_id, extracted_title)
            yield f'<div class="status-message" style="font-size:0.75rem; color:var(--text-output); margin-left:20px;"><span aria-hidden="true">✨</span> Converted: {mp3_path.name}</div>'

        # 5. METADATA ENFORCEMENT
        if mp3_path:
            # Physical filename keeps the 3-digit disc+track enumerator
            # (filing_id, e.g. "205") so files sort correctly on disk.
            # The ID3 TRCK tag, however, should be the album-wide running
            # count across all discs (offset is the cumulative track count
            # of every prior disc, computed once by unpack_convert.py) --
            # per-disc-only numbering here would make disc 2+ restart at 1
            # in the tags even though the files are correctly enumerated.
            per_disc_track = int(filing_id) % 100 if int(filing_id) >= 100 else int(filing_id)
            metadata_track = str(offset + per_disc_track) if is_multidisc else str(per_disc_track)
            _enforce_metadata_truth(mp3_path, artist, album, extracted_title, metadata_track, category, disc_num, total_discs, is_multidisc)

            status_suffix = f"(Disc {disc_num}, Track {metadata_track})" if is_multidisc else f"(Track {metadata_track})"
            yield f'<div class="status-message" style="font-size:0.7rem; color:var(--text-message); margin-left:25px; margin-bottom:10px;"><span aria-hidden="true">🧼</span> Metadata Cleaned: {mp3_path.name} {status_suffix}</div>'
            
            if mp3_path.name not in report_data['conversion']:
                report_data['conversion'].append(mp3_path.name)

            # 6. BITSTREAM VALIDATION (mp3val runs on every resulting file)
            if _check_mp3val(mp3_path):
                yield f'<div class="status-warn" style="font-size:0.7rem; color:var(--mf-gold); margin-left:25px;"><span aria-hidden="true">🩹</span> Bitstream corruption queued for Repair: {mp3_path.name}</div>'

        yield f"<!-- PROGRESS:2:{idx}:{total_to_process} -->"

def _rescue_embedded_art(source_file, root):
    """Extracts image stream from source audio for Step 4 discovery."""
    art_dir = root / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    out_path = art_dir / "rescued_embedded_art.jpg"
    
    cmd = [
        str(FFMPEG_EXE), "-i", str(source_file),
        "-an", "-vcodec", "mjpeg",
        "-frames:v", "1",
        str(out_path), "-y", "-loglevel", "quiet"
    ]
    try:
        subprocess.run(cmd, timeout=5)
        if out_path.exists() and out_path.stat().st_size == 0:
            out_path.unlink()
    except Exception:
        pass

def _convert_to_mp3(f_path, artist, filing_id, title, do_norm, report_data):
    """Standardizes bitstream to MP3 VBR(V0)."""
    out_name = f"{filing_id} - {artist} - {title}.mp3"
    out_path = f_path.parent / out_name
    
    work_path = out_path
    is_same_file = f_path.resolve() == out_path.resolve()
    
    if is_same_file:
        work_path = out_path.with_suffix('.tmp.mp3')

    cmd = [str(FFMPEG_EXE), "-i", str(f_path)]
    if do_norm:
        cmd.extend(["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"])
    
    cmd.extend([
        "-codec:a", "libmp3lame", "-q:a", "0",
        "-map_metadata", "0", "-id3v2_version", "3", 
        str(work_path), "-y", "-loglevel", "error"
    ])
    
    res = subprocess.run(cmd)
    
    if res.returncode == 0 and work_path.exists():
        if is_same_file:
            f_path.unlink()
            work_path.rename(out_path)
        else:
            try: 
                if f_path.name not in report_data['deletions']:
                    report_data['deletions'].append(f_path.name)
                os.remove(f_path)
            except: pass
            
        yield f'<div class="status-message" style="font-size:0.75rem; color:var(--text-output); margin-left:20px;"><span aria-hidden="true">✨</span> Converted: {out_name}</div>'
        if do_norm:
            yield f'<div class="status-message" style="font-size:0.7rem; color:var(--text-message); margin-left:25px;"><span aria-hidden="true">⚖️</span> Normalized: {out_name}</div>'
    else:
        _queue_for_repair(f_path, "FFmpeg Conversion Failure - Source Likely Corrupted")
        yield f'<div class="status-error">❌ Processing failed: {f_path.name}</div>'
        yield f'<div class="status-warn" style="font-size:0.7rem; color:var(--mf-gold); margin-left:25px;"><span aria-hidden="true">🩹</span> Source queued for Repair: {f_path.name}</div>'

def _rename_existing_mp3(f_path, artist, filing_id, title):
    """Aligns existing MP3 filenames with the standard."""
    out_name = f"{filing_id} - {artist} - {title}.mp3"
    out_path = f_path.parent / out_name
    
    if f_path.resolve() != out_path.resolve():
        try:
            if out_path.exists(): out_path.unlink()
            f_path.rename(out_path)
        except: return f_path
    return out_path

def _clean_filename_stem(stem, artist):
    """Surgical removal of existing sequence noise."""
    clean = re.sub(r'^\d+[\s\.\-_]*', '', stem)
    if artist.lower() in clean.lower():
        clean = re.compile(re.escape(artist), re.IGNORECASE).sub('', clean)
    return clean.strip(" .-_")

def _enforce_metadata_truth(f_path, artist, album, title, track, category, disc_num, total_discs, is_multidisc):
    """Surgically purges junk and injects truth per Directive IX."""
    try:
        tags = ID3(str(f_path))
        to_delete = [k for k in tags.keys() if not any(k.startswith(w) for w in ID3_WHITELIST)]
        for key in to_delete: tags.delall(key)
            
        tags.add(TPE1(encoding=1, text=[artist]))
        tags.add(TALB(encoding=1, text=[album]))
        tags.add(TIT2(encoding=1, text=[title]))
        tags.add(TRCK(encoding=1, text=[track]))
        if is_multidisc:
            tags.add(TPOS(encoding=1, text=[f"{disc_num}/{total_discs}"]))
        if category:
            tags.add(TXXX(encoding=1, description='CATEGORY', text=[category]))
        # save() alone doesn't downgrade v2.4-native frames (e.g. TDRC ->
        # TYER) even when v2_version=3 is requested -- must call this first.
        tags.update_to_v23()
        tags.save(v2_version=3)
    except ID3NoHeaderError:
        tags = ID3()
        tags.add(TPE1(encoding=1, text=[artist]))
        tags.add(TALB(encoding=1, text=[album]))
        tags.add(TIT2(encoding=1, text=[title]))
        tags.add(TRCK(encoding=1, text=[track]))
        if is_multidisc:
            tags.add(TPOS(encoding=1, text=[f"{disc_num}/{total_discs}"]))
        if category:
            tags.add(TXXX(encoding=1, description='CATEGORY', text=[category]))
        tags.update_to_v23()
        tags.save(str(f_path), v2_version=3)

# --- END OF FILE bitstream_engine.py ---