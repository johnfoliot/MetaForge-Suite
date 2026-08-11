# --- START OF FILE sacd_engine.py ---
# ======================================================================
# MetaForge Spoke: SACD Engine
# Role: Extracts Super Audio CD ISO images (via the external sacd_extract
# tool) to stereo DSD, then downsamples to FLAC via the bundled ffmpeg so
# the result flows into the normal pipeline exactly like a CUE-split album.
# Build 1.0.0: Initial implementation.
# ======================================================================
import re
import subprocess
import tempfile
from pathlib import Path
from common.config_handler import FFMPEG_EXE, SACD_EXTRACT_EXE

# DSD64's native rate is an exact 64x multiple of the 44.1kHz family --
# 88.2kHz (2x oversample) is a cleaner decimation path for ffmpeg's DSD
# decoder than jumping straight to 44.1kHz. 24-bit avoids baking in
# quantization noise DSD's dynamic range would otherwise lose. This FLAC
# is a temporary intermediate on its way to the pipeline's existing MP3
# pass (janitor_engine deletes it once bitstream_engine converts it), so
# the extra size costs nothing.
TARGET_SAMPLE_RATE = "88200"
TARGET_SAMPLE_FMT = "s32"

# Matches sacd_extract's own "Processing [path] (N/M).." announcement,
# printed once per track as extraction begins it.
_TRACK_START_RE = re.compile(r'Processing \[.*?\]\s*\((\d+)/(\d+)\)')


def process_sacd(root, artist, report_data):
    """
    Scans for SACD ISO images and extracts them to per-track FLAC files
    using the same filename convention cue_engine.py's split_cue() already
    produces (f"{track_id} - {artist} - {title}.flac") -- bitstream_engine.py
    needs zero changes, it only ever reads the leading digit prefix of
    whatever discrete tracks already exist.

    CRITICAL SAFETY NOTE: janitor_engine.py's cleanup pass (Step 3)
    unconditionally deletes any non-.mp3, non-system file in the album
    folder UNLESS its filename is registered in report_data['failed_targets'].
    A bare .iso is not exempted anywhere else in the pipeline -- every
    non-success path below MUST register the iso into failed_targets, or
    a multi-GB source file gets silently destroyed on the very next
    janitorial pass. This is not optional hardening, it's the only thing
    standing between this file and deletion.
    """
    iso_files = list(root.glob("*.iso"))
    if not iso_files:
        return

    if not SACD_EXTRACT_EXE.exists():
        for iso_path in iso_files:
            report_data.setdefault('failed_targets', [])
            if iso_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(iso_path.name)
        yield f'<div class="status-error" style="font-size:0.75rem;"><span aria-hidden="true">❌</span> SACD ISO found ({len(iso_files)}) but sacd_extract.exe is not present in /bin -- source(s) preserved, not processed.</div>'
        return

    for iso_path in iso_files:
        try:
            with tempfile.TemporaryDirectory(prefix="mf_sacd_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)

                if not report_data.get('extraction_occurred', False):
                    yield f'<div class="status-api" style="margin-top:5px; padding-top:5px;"><span aria-hidden="true">💿</span> Step 1: Extracting SACD Source:<br><span style="margin-left:25px; color:var(--text-output)"> {iso_path.name}</span></div>'
                    report_data['extraction_occurred'] = True
                else:
                    yield f'<div class="status-message" style="font-size:0.75rem; color:var(--mf-gold); margin-top:5px;"><span aria-hidden="true">💿</span> Additional Source: Extracting {iso_path.name}</div>'

                report_data['extraction']['source'] = f"SACD ISO: {iso_path.name}"

                # 1. EXTRACT TO STEREO DSF (+ CUE for real track titles)
                # Verified 2026-07-30 against the real binary's own --help
                # output -- the web-research-derived guess was wrong on
                # exactly the part flagged as unverified: -o is the output
                # dir for ISO/DSDIFF-Edit-Master output ONLY, DSF output
                # (-s, what this uses) is controlled by -y/--output-dir-conc
                # instead. -C/--export-cue is confirmed real (was previously
                # unconfirmed).
                #
                # Real bug, found live 2026-07-30 (John's Todd Rundgren
                # report): this used to be one blocking subprocess.run()
                # call with zero output until it finished -- a real
                # extraction took ~90 seconds with nothing on screen the
                # whole time, indistinguishable from a hang even though it
                # was actively working. Streaming per-track progress here
                # instead, same "never leave a long operation silent"
                # principle already applied to Music Sharing's render step.
                extract_returncode = 1
                extract_err = ""
                for kind, payload in _run_sacd_extract(iso_path, tmp_dir):
                    if kind == 'progress':
                        current, total = payload
                        yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">💿</span> Extracting track {current}/{total}...</div>'
                        yield f"<!-- PROGRESS:1:{current}:{max(total, 1)} -->"
                    else:
                        extract_returncode, extract_err = payload

                dsf_files = sorted(tmp_dir.rglob("*.dsf"))

                if extract_returncode != 0 or not dsf_files:
                    err_line = extract_err or "no DSD tracks produced"
                    report_data.setdefault('failed_targets', [])
                    if iso_path.name not in report_data['failed_targets']:
                        report_data['failed_targets'].append(iso_path.name)
                    yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">❌</span> SACD extraction failed: {iso_path.name} — {err_line}</div>'
                    continue

                # 2. RESOLVE TRACK NUMBERS + TITLES
                tracks = _resolve_tracks(dsf_files, tmp_dir)

                # 3. CONVERT EACH TRACK: DSF -> FLAC (via bundled ffmpeg)
                total_tracks = len(dsf_files)
                success_count = 0
                for i, (dsf_path, (track_num, title)) in enumerate(zip(dsf_files, tracks), 1):
                    safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip()
                    track_id = str(track_num)
                    out_name = f"{track_id} - {artist} - {safe_title}.flac"
                    out_path = root / out_name

                    conv_res = subprocess.run(
                        [str(FFMPEG_EXE), "-i", str(dsf_path),
                         "-ar", TARGET_SAMPLE_RATE, "-sample_fmt", TARGET_SAMPLE_FMT,
                         str(out_path), "-y", "-loglevel", "panic"],
                        capture_output=True, text=True
                    )

                    if conv_res.returncode == 0:
                        yield f'<div class="status-message" style="font-size:0.75rem; color:#888; margin-left:20px;"><span aria-hidden="true">📤</span> Unpacked: {out_name}</div>'
                        report_data['extraction']['count'] += 1
                        success_count += 1
                        yield f"<!-- PROGRESS:1:{i}:{total_tracks} -->"
                    else:
                        err_line = (conv_res.stderr or "").strip().splitlines()[-1] if (conv_res.stderr or "").strip() else "unknown error"
                        yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">❌</span> DSD-to-FLAC conversion failed: {out_name} — {err_line}</div>'
                        # A partially-written FLAC from a failed ffmpeg run
                        # shouldn't linger and confuse Step 2's track count.
                        try:
                            if out_path.exists():
                                out_path.unlink()
                        except Exception:
                            pass

                # 4. ALL-OR-NOTHING SOURCE DELETION -- same rule as
                # cue_engine.py: only delete the source once EVERY track
                # has succeeded end-to-end. A partial success still leaves
                # the multi-GB .iso in place for retry, never guesses.
                if total_tracks > 0 and success_count == total_tracks:
                    try:
                        if iso_path.name not in report_data['deletions']:
                            report_data['deletions'].append(iso_path.name)
                        iso_path.unlink()
                        yield f'<div class="status-message" style="font-size:0.7rem; color:#888; margin-left:20px;"><span aria-hidden="true">🧹</span> SACD source deleted.</div>'
                    except Exception:
                        pass
                else:
                    report_data.setdefault('failed_targets', [])
                    if iso_path.name not in report_data['failed_targets']:
                        report_data['failed_targets'].append(iso_path.name)
                    yield f'<div class="status-error" style="font-size:0.75rem; margin-left:20px;"><span aria-hidden="true">⚠️</span> Only {success_count}/{total_tracks} tracks converted successfully — SACD source preserved for retry.</div>'

        except Exception as e:
            # Same "never silent" principle cue_engine.py's own exception
            # handler establishes -- an unexpected failure here must never
            # vanish without a trace, and must never leave the source
            # unregistered (see the module docstring's safety note).
            report_data.setdefault('failed_targets', [])
            if iso_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(iso_path.name)
            yield f'<div class="status-error" style="font-size:0.75rem;"><span aria-hidden="true">❌</span> SACD processing error on {iso_path.name}: {e}</div>'
            continue


def _run_sacd_extract(iso_path, tmp_dir):
    """
    Runs sacd_extract with streamed progress instead of one multi-minute
    blocking call. Yields ('progress', (current_track, total_tracks)) each
    time a new track begins, then exactly one ('done', (returncode,
    last_output_line)) once the process exits.

    sacd_extract prints its per-sector percentage spam using carriage
    returns (\\r) to overwrite one line on a real terminal, not newlines --
    Python's default line iteration (splits on \\n only) would silently
    swallow all of it as one unbroken chunk and never see the per-track
    "Processing [...] (N/M).." announcements in between. Reading
    character-by-character and treating BOTH \\r and \\n as a line
    boundary is what actually catches them reliably.
    """
    process = subprocess.Popen(
        [str(SACD_EXTRACT_EXE), "-2", "-s", "-C", "-i", str(iso_path), "-y", str(tmp_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )

    buf = ""
    last_line = ""
    while True:
        ch = process.stdout.read(1)
        if ch == '':
            if process.poll() is not None:
                break
            continue
        if ch in ('\r', '\n'):
            line = buf.strip()
            if line:
                last_line = line
                m = _TRACK_START_RE.search(line)
                if m:
                    yield ('progress', (int(m.group(1)), int(m.group(2))))
            buf = ""
        else:
            buf += ch

    process.wait()
    yield ('done', (process.returncode, last_line))


def _resolve_tracks(dsf_files, tmp_dir):
    """
    Returns one (track_num, title) tuple per entry in dsf_files, same
    order. Confirmed live 2026-07-30 against a real SACD extraction:
    sacd_extract names its own DSF output "04 - You Need Your Head.dsf" --
    number and title both already embedded in the filename, so that's the
    primary source, not the separately-exported CUE. The CUE (from -C)
    describes a single continuous file (matching -p/DSDIFF Edit Master
    mode) rather than the discrete per-track DSF layout actually on disk,
    so it isn't reliably position-matched to it -- only used here as a
    title-only fallback (by track count match) for whichever tracks don't
    parse cleanly from their own filename, never for numbering.
    """
    parsed = []
    for dsf_path in dsf_files:
        m = re.match(r'^0*(\d+)\s*-\s*(.+)$', dsf_path.stem)
        parsed.append((int(m.group(1)), m.group(2).strip()) if m else None)

    if all(parsed):
        return parsed

    cue_titles = None
    for cue_path in tmp_dir.rglob("*.cue"):
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
            cue_tracks = re.findall(r'TRACK (\d+) AUDIO.*?TITLE "(.*?)"', content, re.DOTALL)
            if len(cue_tracks) == len(dsf_files):
                cue_titles = [title for _, title in cue_tracks]
                break
        except Exception:
            continue

    resolved = []
    for i, p in enumerate(parsed, 1):
        if p:
            resolved.append(p)
        elif cue_titles:
            resolved.append((i, cue_titles[i - 1]))
        else:
            resolved.append((i, f"Track {i}"))
    return resolved

# --- END OF FILE sacd_engine.py ---
