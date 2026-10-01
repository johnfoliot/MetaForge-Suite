# --- START OF FILE dsf_engine.py ---
# ======================================================================
# MetaForge Spoke: DSF Engine
# Role: Decodes discrete DSD files (.dsf / .dff) to FLAC via the bundled
# ffmpeg so they flow into the normal pipeline exactly like SACD- or
# CUE-produced tracks.
# Build 1.0.0: Initial implementation.
# Physical Location: \tools\unpack_convert\engines\dsf_engine.py
# ======================================================================
import re
import subprocess
from pathlib import Path
from common.config_handler import FFMPEG_EXE

# Same decimation target sacd_engine already uses (88.2kHz / 24-bit in a
# 32-bit container) -- imported, not duplicated, so the two DSD paths can
# never drift apart. The FLAC is a temporary intermediate: bitstream_engine
# converts it to MP3 V0 in Step 2 and deletes it on success.
from sacd_engine import TARGET_SAMPLE_RATE, TARGET_SAMPLE_FMT

try:
    from mutagen import File as MutagenFile
except Exception:  # mutagen missing/old -- filename parsing still works
    MutagenFile = None

DSD_EXT = {'.dsf', '.dff'}

# "01 - Title", "01. Title", "01_Title", "1 Title", "001-Title"
_FILENAME_RE = re.compile(r'^0*(\d+)\s*[-._\s]\s*(.+)$')


def _register_failed(report_data, path):
    report_data.setdefault('failed_targets', [])
    if path.name not in report_data['failed_targets']:
        report_data['failed_targets'].append(path.name)


def _read_tags(path):
    """
    Returns (track_num or None, title or None) from the file's own ID3
    tags. DSF stores a standard ID3v2 block; DSDIFF (.dff) carries one in
    an ID3 chunk on newer mutagen. Any failure just returns (None, None)
    -- tags are a convenience here, never a requirement.
    """
    if MutagenFile is None:
        return None, None
    try:
        audio = MutagenFile(str(path))
        tags = getattr(audio, 'tags', None) if audio is not None else None
        if not tags:
            return None, None

        track = None
        trck = tags.get('TRCK')
        if trck and trck.text:
            m = re.match(r'^\s*0*(\d+)', str(trck.text[0]))
            if m:
                track = int(m.group(1))

        title = None
        tit2 = tags.get('TIT2')
        if tit2 and tit2.text:
            title = str(tit2.text[0]).strip() or None

        return track, title
    except Exception:
        return None, None


def _resolve_track(path, fallback_index):
    """
    Track number: filename prefix -> TRCK tag -> position in sorted list.
    Title:        TIT2 tag -> filename remainder -> "Track N".

    Title prefers the tag because DSD filenames very often carry the
    artist too ("01 - Artist - Title"); the tag is just the title.
    Track number prefers the filename because that's what the rest of the
    pipeline (bitstream_engine's dedup/sort) already keys on.
    """
    tag_track, tag_title = _read_tags(path)

    fn_track, fn_title = None, None
    m = _FILENAME_RE.match(path.stem)
    if m:
        fn_track = int(m.group(1))
        fn_title = m.group(2).strip() or None

    track = fn_track or tag_track or fallback_index
    title = tag_title or fn_title or f"Track {track}"
    return track, title


def _cue_referenced_dsd(root, dsd_files):
    """
    Returns the DSD files a .cue sheet in the same folder points at --
    monolithic DSD rips (one long .dff/.dsf + CUE). Matching by exact
    name or by stem, same rule as sacd_engine._cue_referenced_isos() and
    cue_engine._find_audio_source().
    """
    ref_names, ref_stems = set(), set()
    for cue_path in root.glob("*.cue"):
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for ref in re.findall(r'FILE\s+"(.*?)"', content):
            ref_names.add(ref.lower())
            ref_stems.add(Path(ref).stem.lower())
    return {
        f for f in dsd_files
        if f.name.lower() in ref_names or f.stem.lower() in ref_stems
    }


def _decode(src, out_path):
    """Runs ffmpeg DSD -> FLAC. Returns (ok, error_line)."""
    res = subprocess.run(
        [str(FFMPEG_EXE), "-i", str(src),
         "-ar", TARGET_SAMPLE_RATE, "-sample_fmt", TARGET_SAMPLE_FMT,
         str(out_path), "-y", "-loglevel", "error"],
        capture_output=True, text=True
    )
    if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
        return True, ""
    err = (res.stderr or "").strip()
    err_line = err.splitlines()[-1] if err else f"ffmpeg exit code {res.returncode}"
    # A partial FLAC from a failed run must not linger -- Step 2 would
    # happily convert a truncated file and the source would look "done."
    try:
        if out_path.exists():
            out_path.unlink()
    except Exception:
        pass
    return False, err_line


def process_dsf(root, artist, report_data):
    """
    Scans the folder for .dsf / .dff files and decodes each to FLAC.

    Two cases:
      1. DISCRETE tracks (the normal case): each file becomes
         f"{track} - {artist} - {title}.flac" -- the same naming
         cue_engine and sacd_engine produce, so bitstream_engine needs no
         changes.
      2. MONOLITHIC rip referenced by a .cue: decoded to f"{stem}.flac"
         (same stem, new extension). cue_engine runs right after this
         engine and its _find_audio_source() stem fallback picks the FLAC
         up and splits it with the original CUE -- no CUE handling is
         duplicated here.

    Deletion rule: each DSD file is its own source, so each is deleted
    only after ITS OWN decode is verified (exit code 0 and a non-empty
    output file). Any failure registers the source in failed_targets and
    leaves it on disk. janitor_engine Build 7.3.0 also never deletes
    .dsf/.dff as a backstop.
    """
    dsd_files = sorted(
        [f for f in root.iterdir() if f.is_file() and f.suffix.lower() in DSD_EXT],
        key=lambda p: p.name.lower()
    )
    if not dsd_files:
        return

    if not FFMPEG_EXE.exists():
        for f in dsd_files:
            _register_failed(report_data, f)
        yield f'<div class="status-error" style="font-size:0.75rem;"><span aria-hidden="true">❌</span> DSD file(s) found ({len(dsd_files)}) but ffmpeg is not present -- source(s) preserved, not processed.</div>'
        return

    monolithic = _cue_referenced_dsd(root, dsd_files)
    discrete = [f for f in dsd_files if f not in monolithic]
    total = len(dsd_files)

    if not report_data.get('extraction_occurred', False):
        yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><img src="/ui/images/DSF.png" alt="" aria-hidden="true" style="margin-left:3px; height:32px; width:auto; margin-bottom:-12px;"> Step 1: Decoding DSD Audio Source:<br><span style="margin-left:42px; color:var(--text-output)"> {total} DSD file(s) found</span></div>'
        report_data['extraction_occurred'] = True
    else:
        yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">📂</span> Additional Source: Decoding {total} DSD file(s)</div>'

    report_data['extraction']['source'] = f"DSD Files: {total}"

    done = 0
    success_count = 0

    # --- 1. MONOLITHIC (CUE-referenced) ---
    for src in sorted(monolithic, key=lambda p: p.name.lower()):
        done += 1
        out_path = src.with_suffix('.flac')
        if out_path.exists():
            _register_failed(report_data, src)
            yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">⚠️</span> {out_path.name} already exists -- DSD source preserved, not overwritten: {src.name}</div>'
            yield f"<!-- PROGRESS:1:{done}:{total} -->"
            continue

        yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">💿</span> Decoding monolithic DSD for CUE split: {src.name}...</div>'
        ok, err = _decode(src, out_path)
        if ok:
            success_count += 1
            yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">📤</span> Decoded: {out_path.name} (handed to CUE splitter)</div>'
            try:
                if src.name not in report_data['deletions']:
                    report_data['deletions'].append(src.name)
                src.unlink()
            except Exception:
                pass
        else:
            _register_failed(report_data, src)
            yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">❌</span> DSD decode failed: {src.name} — {err}</div>'
        yield f"<!-- PROGRESS:1:{done}:{total} -->"

    # --- 2. DISCRETE TRACKS ---
    for i, src in enumerate(discrete, 1):
        done += 1
        track, title = _resolve_track(src, i)
        safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or f"Track {track}"
        out_name = f"{track} - {artist} - {safe_title}.flac"
        out_path = root / out_name

        if out_path.exists():
            _register_failed(report_data, src)
            yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">⚠️</span> {out_name} already exists -- DSD source preserved, not overwritten: {src.name}</div>'
            yield f"<!-- PROGRESS:1:{done}:{total} -->"
            continue

        ok, err = _decode(src, out_path)
        if ok:
            success_count += 1
            report_data['extraction']['count'] += 1
            yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:36px;"><span aria-hidden="true">📤</span> Unpacked: {out_name}</div>'
            try:
                if src.name not in report_data['deletions']:
                    report_data['deletions'].append(src.name)
                src.unlink()
            except Exception:
                pass
        else:
            _register_failed(report_data, src)
            yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">❌</span> DSD decode failed: {src.name} — {err}</div>'
        yield f"<!-- PROGRESS:1:{done}:{total} -->"

    if success_count < total:
        yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">⚠️</span> Only {success_count}/{total} DSD file(s) decoded successfully — failed source(s) preserved for retry.</div>'
    else:
        yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> DSD source file(s) deleted.</div>'

# --- END OF FILE dsf_engine.py ---
