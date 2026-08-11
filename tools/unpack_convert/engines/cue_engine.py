# --- START OF FILE cue_engine.py ---
# ======================================================================
# MetaForge Spoke: CUE Engine
# Role: Parses CUE sheets and executes FFmpeg splitting.
# Build 7.2.0: Loud-Failure Hardening (no more silent source deletion).
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
            yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><span aria-hidden="true">📦</span> Step 1: Discrete tracks detected ({discrete_count}). Unpacking not required.</div>'
            yield "<!-- PROGRESS:1:1:1 -->"
            report_data['extraction_occurred'] = True
        return

    # 2. SELECTION & VALIDATION
    for cue_path in cue_files:
        source_audio = None
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
            file_references = re.findall(r'FILE\s+"(.*?)"', content)
            if len(file_references) > 1:
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888;"><span aria-hidden="true">ℹ️</span> Non-compliant CUE ignored: {cue_path.name}</div>'
                continue

            # Real bug, found live 2026-07-20 (John's Don Bryant "Precious
            # Soul" report -- console "jumped straight past" Step 1 with no
            # message at all): this used to be a totally silent `continue`,
            # so a CUE sheet with no parseable FILE reference vanished
            # without a trace instead of telling the user why nothing
            # happened.
            if not file_references:
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888;"><span aria-hidden="true">ℹ️</span> No FILE reference found in CUE, skipped: {cue_path.name}</div>'
                continue

            source_audio = _find_audio_source(cue_path.parent, file_references[0])

            if not source_audio:
                yield f'<div class="status-message" style="font-size:0.7rem; color:#888;"><span aria-hidden="true">ℹ️</span> Ghost CUE ignored: {cue_path.name} (Blob missing).</div>'
                continue

            # Header Control with Accessibility Guard
            if not report_data.get('extraction_occurred', False):
                yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><img src="/ui/images/cue.png" alt="" aria-hidden="true" style="margin-left:3px; height:14px; width:auto;"> Step 1: Splitting Original Audio Source:<br><span style="margin-left:25px; color:var(--text-output)"> {source_audio.name}</span></div>'
                report_data['extraction_occurred'] = True
            else:
                yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Splitting {source_audio.name}</div>'

            report_data['extraction']['source'] = f"CUE Bundle: {source_audio.name}"

            # 3. PARSE & SPLIT
            tracks = re.findall(r'TRACK (\d+) AUDIO.*?TITLE "(.*?)"', content, re.DOTALL)
            times = re.findall(r'INDEX 01 (\d{1,3}:\d{2}:\d{2})', content)

            total_tracks = len(tracks)
            success_count = 0
            for i, (num, title) in enumerate(tracks):
                t_start = _format_ts(times[i])
                t_dur = ["-to", _format_ts(times[i+1])] if i+1 < len(times) else []

                safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip()
                track_id = str(int(num))
                out_name = f"{track_id} - {artist} - {safe_title}.wav"
                out_path = cue_path.parent / out_name

                # Raw BIN/ISO CD-DA dumps have no container header for
                # ffmpeg to auto-detect -- has to be told explicitly it's
                # Red Book audio (16-bit little-endian PCM, 44.1kHz,
                # stereo) or the split fails immediately on every track.
                # FLAC/APE/WAV/WV all still auto-detect fine as before.
                raw_pcm_flags = ["-f", "s16le", "-ar", "44100", "-ac", "2"] if source_audio.suffix.lower() in RAW_PCM_EXT else []

                # capture_output so a real failure reason is visible instead
                # of silently discarded -- -loglevel panic already suppresses
                # ffmpeg's own console spam, but previously nothing captured
                # stderr at all, so a failed split left zero trace of why.
                res = subprocess.run([
                    str(FFMPEG_EXE)] + raw_pcm_flags + ["-i", str(source_audio),
                    "-ss", t_start] + t_dur +
                    [str(out_path), "-y", "-loglevel", "panic"],
                    capture_output=True, text=True
                )

                if res.returncode == 0:
                    # FIX: Wrapped Outbox emoji in aria-hidden span
                    yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">📤</span> Unpacked: {out_name}</div>'
                    report_data['extraction']['count'] += 1
                    success_count += 1
                    yield f"<!-- PROGRESS:1:{i+1}:{total_tracks} -->"
                else:
                    # Real bug, found live 2026-07-20: a failed split used to
                    # be completely silent (no message at all) -- the user
                    # had no way to know a track failed short of noticing
                    # the final file count didn't match.
                    err_line = (res.stderr or "").strip().splitlines()[-1] if (res.stderr or "").strip() else "unknown error"
                    yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">❌</span> Split failed: {out_name} — {err_line}</div>'

            # 4. DELETE SOURCE -- only when EVERY track split successfully.
            # Real bug, found live 2026-07-20 (John's Don Bryant "Precious
            # Soul" report): this used to run unconditionally regardless of
            # success_count, so any split failure (even just one track)
            # still deleted the only source audio and the CUE sheet needed
            # to ever retry -- confirmed capable of destroying an entire
            # album with zero tracks recovered. A partial success (some
            # tracks split, others failed) is treated the same as total
            # failure here -- deleting the source would still permanently
            # strand whichever tracks failed, so nothing gets deleted
            # unless the whole split succeeded.
            if total_tracks > 0 and success_count == total_tracks:
                try:
                    if source_audio.name not in report_data['deletions']:
                        report_data['deletions'].append(source_audio.name)
                    if cue_path.name not in report_data['deletions']:
                        report_data['deletions'].append(cue_path.name)

                    source_audio.unlink()
                    cue_path.unlink()
                    yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> Monolithic source deleted.</div>'
                except: pass
            else:
                # Register with the SAME failed_targets list bitstream_
                # engine populates -- janitor_engine.py's cleanup pass
                # already knows to preserve (not delete) anything in this
                # list, so this reuses that existing safety net rather
                # than adding a new, separate one.
                report_data.setdefault('failed_targets', [])
                if source_audio.name not in report_data['failed_targets']:
                    report_data['failed_targets'].append(source_audio.name)
                if cue_path.name not in report_data['failed_targets']:
                    report_data['failed_targets'].append(cue_path.name)
                yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">⚠️</span> Only {success_count}/{total_tracks} tracks split successfully — source and CUE sheet preserved for retry.</div>'

        except Exception as e:
            # Real bug, found live 2026-07-20: this used to be a bare
            # `except Exception: continue` -- ANY unexpected failure
            # anywhere in CUE parsing or splitting (a bad regex edge case,
            # a permissions error, a subprocess failure) vanished with zero
            # trace, console just "jumped straight past" Step 1 entirely.
            # Whatever the actual cause turns out to be, it must never
            # again be invisible.
            report_data.setdefault('failed_targets', [])
            if cue_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(cue_path.name)
            if source_audio and source_audio.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(source_audio.name)
            yield f'<div class="status-error" style="font-size:0.75rem;"><span aria-hidden="true">❌</span> CUE processing error on {cue_path.name}: {e}</div>'
            continue

# Raw, headerless CD-DA PCM dumps -- the standard "BIN/CUE" or "ISO/CUE"
# rip convention (EAC, dBpoweramp, etc all support this alongside FLAC).
# Not a filesystem image and not the same thing as an SACD ISO (see
# sacd_engine.py) -- just uncompressed Red Book audio with no container
# header, which is exactly why ffmpeg needs to be told the format
# explicitly in _run_split() below rather than auto-detecting it.
RAW_PCM_EXT = {'.iso', '.bin'}

def _find_audio_source(directory, filename):
    if (directory / filename).exists(): return directory / filename
    stem = Path(filename).stem
    for ext in ['.flac', '.ape', '.wav', '.wv'] + sorted(RAW_PCM_EXT):
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
