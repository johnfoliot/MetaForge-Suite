# --- START OF FILE cue_engine.py ---
# ======================================================================
# MetaForge Spoke: CUE Engine
# Role: Parses CUE sheets and executes FFmpeg splitting.
# Build 7.4.1: Accurate out-of-spec timestamp warning wording.
# ======================================================================
import re
import os
import subprocess
from pathlib import Path
from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)
from common.config_handler import FFMPEG_EXE

# Audio extensions that qualify as "Discrete Tracks"
DISCRETE_EXT = {'.flac', '.mp3', '.m4a', '.ape', '.wav'}

# Raw, headerless CD-DA PCM dumps -- the standard "BIN/CUE" or "ISO/CUE"
# rip convention (EAC, dBpoweramp, etc all support this alongside FLAC).
# Not a filesystem image and not the same thing as an SACD ISO (see
# sacd_engine.py, which as of Build 1.1.0 skips any .iso a CUE sheet
# references so it lands here) -- just uncompressed Red Book audio with
# no container header, which is exactly why ffmpeg needs to be told the
# format explicitly in split_cue() below rather than auto-detecting it.
RAW_PCM_EXT = {'.iso', '.bin'}

_FILE_RE = re.compile(r'^FILE\s+(?:"(.*?)"|(\S+))', re.IGNORECASE)
_TRACK_RE = re.compile(r'^TRACK\s+(\d+)\s+(\S+)', re.IGNORECASE)
_TITLE_RE = re.compile(r'^TITLE\s+(?:"(.*?)"|(.+?))\s*$', re.IGNORECASE)
_INDEX01_RE = re.compile(r'^INDEX\s+01\s+(\d{1,3}):(\d{2}):(\d{2})', re.IGNORECASE)


def _parse_cue(content):
    """
    Line-by-line CUE parser. Returns (file_refs, tracks, bad_frame_count):
      file_refs: FILE names in sheet order
      tracks:    list of dicts, sheet order, ALL track types:
                 {'num', 'type', 'title', 'start', 'file'}
                 'start' is (min, sec, frame) or None
                 'file'  is the FILE in effect when INDEX 01 appeared

    Build 7.4.0 (John's Joe Bonamassa "Dust Bowl" report, 2026-10-01):
    multi-FILE sheets are now supported -- e.g. one FLAC per vinyl side,
    each side's timestamps restarting at 00:00:00. Previously any CUE
    with more than one FILE line was rejected as "Non-compliant."

    A track belongs to whichever FILE is in effect when its INDEX 01
    line appears, not where its TRACK line appears. That's the CUE spec,
    and it matters for EAC "noncompliant" rips where a track's pregap
    (INDEX 00) sits at the end of the previous file and its INDEX 01 is
    at the start of the next one.

    Line-based (not block-regex) parsing also keeps Build 7.3.0's fix:
    each track's title/start come only from that track's own lines, so a
    missing TITLE can never shift titles onto other tracks.
    """
    file_refs = []
    tracks = []
    current_file = None
    cur = None
    bad_frames = 0

    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue

        m = _FILE_RE.match(line)
        if m:
            current_file = m.group(1) if m.group(1) is not None else m.group(2)
            file_refs.append(current_file)
            continue

        m = _TRACK_RE.match(line)
        if m:
            cur = {'num': int(m.group(1)), 'type': m.group(2).upper(),
                   'title': None, 'start': None, 'file': None}
            tracks.append(cur)
            continue

        if cur is None:
            continue  # album-level TITLE/PERFORMER/REM before any TRACK

        m = _TITLE_RE.match(line)
        if m:
            t = (m.group(1) if m.group(1) is not None else m.group(2) or "").strip()
            cur['title'] = t or None
            continue

        m = _INDEX01_RE.match(line)
        if m:
            mm, ss, ff = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if ff > 74:
                bad_frames += 1
            cur['start'] = (mm, ss, ff)
            cur['file'] = current_file

    return file_refs, tracks, bad_frames


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
            yield event("step", "Step 1: Inspecting the original audio source")
            yield event("info", f"{discrete_count} separate tracks found, so no CUE splitting is needed")
            yield signal("progress", phase=1, current=1, total=1)
            report_data['extraction_occurred'] = True
        return

    # 2. SELECTION & VALIDATION
    for cue_path in cue_files:
        sources = {}  # FILE reference -> resolved Path (or None)
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
            file_refs, all_tracks, bad_frames = _parse_cue(content)

            # Real bug, found live 2026-07-20 (John's Don Bryant "Precious
            # Soul" report -- console "jumped straight past" Step 1 with no
            # message at all): this used to be a totally silent `continue`,
            # so a CUE sheet with no parseable FILE reference vanished
            # without a trace instead of telling the user why nothing
            # happened.
            if not file_refs:
                yield event("info", "CUE sheet skipped: it doesn't name an audio file", file=cue_path.name)
                continue

            for ref in file_refs:
                if ref not in sources:
                    sources[ref] = _find_audio_source(cue_path.parent, ref)

            found = [p for p in sources.values() if p]
            if not found:
                yield event("info", "CUE sheet ignored: the audio file it names isn't here", file=cue_path.name)
                continue

            source_names = ", ".join(p.name for p in found)

            # Header Control with Accessibility Guard
            if not report_data.get('extraction_occurred', False):
                yield event("step", "Step 1: Splitting the original audio source", file=source_names)
                report_data['extraction_occurred'] = True
            else:
                yield event("info", "Additional source: splitting", file=source_names)

            report_data['extraction']['source'] = f"CUE Bundle: {source_names}"

            missing = [ref for ref, p in sources.items() if p is None]
            for ref in missing:
                yield event("error", "The CUE sheet names a file that isn't on disk", file=ref)

            # Build 7.4.1 (John's report, 2026-10-01): the previous wording
            # ("split points may be off by up to ~1 second") read as though
            # audio could be lost. It can't -- each track ends exactly where
            # the next begins, so an off timestamp only moves a boundary
            # between neighbouring tracks. Say that plainly.
            if bad_frames:
                yield event("warning", f"The CUE sheet has {bad_frames} out-of-spec timestamp{'s' if bad_frames != 1 else ''}; track boundaries may shift by a fraction of a second. No audio is lost")

            # 3. PARSE & SPLIT
            audio_positions = [i for i, t in enumerate(all_tracks) if t['type'] == 'AUDIO']
            total_tracks = len(audio_positions)
            success_count = 0

            if total_tracks == 0:
                yield event("error", "No audio tracks found in the CUE sheet", file=cue_path.name)

            for n, pos in enumerate(audio_positions, 1):
                track = all_tracks[pos]
                track_id = str(track['num'])
                title = track['title'] or f"Track {track['num']}"
                safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or f"Track {track['num']}"
                out_name = f"{track_id} - {artist} - {safe_title}.wav"
                out_path = cue_path.parent / out_name

                if not track['start']:
                    yield event("error", f"Split failed: the CUE sheet has no INDEX 01 for track {track_id}", file=out_name)
                    continue

                source_audio = sources.get(track['file'])
                if not source_audio:
                    yield event("error", f"Split failed: source file missing ({track['file']})", file=out_name)
                    continue

                t_start = _format_ts(track['start'])

                # End boundary = the next track's INDEX 01, but ONLY if it
                # sits in the same FILE. If the next start is in a
                # different file (or there is none), this track runs to
                # the end of its own file -- no -to at all.
                t_dur = []
                for nxt in all_tracks[pos + 1:]:
                    if nxt['start']:
                        if nxt['file'] == track['file']:
                            t_dur = ["-to", _format_ts(nxt['start'])]
                        break

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

                    yield event("detail", "Split", file=out_name)
                    report_data['extraction']['count'] += 1
                    success_count += 1
                    yield signal("progress", phase=1, current=n, total=total_tracks)
                else:
                    # Real bug, found live 2026-07-20: a failed split used to
                    # be completely silent (no message at all) -- the user
                    # had no way to know a track failed short of noticing
                    # the final file count didn't match.
                    err_line = (res.stderr or "").strip().splitlines()[-1] if (res.stderr or "").strip() else "unknown error"
                    yield event("error", f"Split failed: {err_line}", file=out_name)

            # 4. DELETE SOURCES -- only when EVERY track split successfully
            # AND every referenced FILE was found. Real bug, found live
            # 2026-07-20 (John's Don Bryant "Precious Soul" report): this
            # used to run unconditionally regardless of success_count, so
            # any split failure (even just one track) still deleted the
            # only source audio and the CUE sheet needed to ever retry.
            # Multi-FILE sheets follow the same all-or-nothing rule across
            # the WHOLE sheet: one failed track keeps every source file
            # and the CUE, since the CUE is needed to retry any of them.
            if total_tracks > 0 and success_count == total_tracks and not missing:
                try:
                    for src in found:
                        if src.name not in report_data['deletions']:
                            report_data['deletions'].append(src.name)
                        src.unlink()
                    if cue_path.name not in report_data['deletions']:
                        report_data['deletions'].append(cue_path.name)
                    cue_path.unlink()
                    label = ("Single-file source deleted after every track split" if len(found) == 1
                             else f"{len(found)} source files deleted after every track split")
                    yield event("success", label)
                except Exception:
                    pass
            else:
                # Register with the SAME failed_targets list bitstream_
                # engine populates -- janitor_engine.py's cleanup pass
                # preserves (not deletes) anything in this list.
                report_data.setdefault('failed_targets', [])
                for src in found:
                    if src.name not in report_data['failed_targets']:
                        report_data['failed_targets'].append(src.name)
                if cue_path.name not in report_data['failed_targets']:
                    report_data['failed_targets'].append(cue_path.name)
                yield event("warning", f"Only {success_count} of {total_tracks} tracks split, so the source and CUE sheet were kept for a retry")

        except Exception as e:
            # Real bug, found live 2026-07-20: this used to be a bare
            # `except Exception: continue` -- ANY unexpected failure
            # anywhere in CUE parsing or splitting vanished with zero
            # trace. Whatever the actual cause turns out to be, it must
            # never again be invisible.
            report_data.setdefault('failed_targets', [])
            if cue_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(cue_path.name)
            for src in sources.values():
                if src and src.name not in report_data['failed_targets']:
                    report_data['failed_targets'].append(src.name)
            yield event("error", f"CUE processing error: {e}. The sources were kept", file=cue_path.name)
            continue

def _find_audio_source(directory, filename):
    if (directory / filename).exists(): return directory / filename
    stem = Path(filename).stem
    for ext in ['.flac', '.ape', '.wav', '.wv'] + sorted(RAW_PCM_EXT):
        if (directory / f"{stem}{ext}").exists(): return directory / f"{stem}{ext}"
    return None

def _format_ts(mmssff):
    """
    (minutes, seconds, frames) -> "HH:MM:SS.mmm" for ffmpeg.

    Build 7.4.0: converts to total milliseconds FIRST, then formats. The
    old version formatted each field separately, so an out-of-spec frame
    value (> 74, e.g. "05:23:88") produced 1173 "milliseconds" and a
    malformed "00:05:23.1173" -- which ffmpeg reads as 23.117s instead of
    the intended ~24.17s. Total-ms math carries the overflow correctly.
    """
    m_raw, s, f = mmssff
    total_ms = round((m_raw * 60 + s) * 1000 + f * 1000 / 75)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"

# --- END OF FILE cue_engine.py ---
