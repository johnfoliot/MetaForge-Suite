# --- START OF FILE sacd_engine.py ---
# ======================================================================
# MetaForge Spoke: SACD Engine
# Role: Extracts Super Audio CD ISO images (via the external sacd_extract
# tool) to stereo DSD, then downsamples to FLAC via the bundled ffmpeg so
# the result flows into the normal pipeline exactly like a CUE-split album.
# Build 1.1.0: CD-DA ISO Deferral (CUE-referenced images go to cue_engine).
# ======================================================================
import re
import subprocess
import tempfile
from pathlib import Path
from common.mf_events import event, signal   # v2: events, not HTML (see common/mf_events.py)
from common.config_handler import FFMPEG_EXE, SACD_EXTRACT_EXE

# DSD64's native rate is an exact 64x multiple of the 44.1kHz family --
# 88.2kHz (2x oversample) is a cleaner decimation path for ffmpeg's DSD
# decoder than jumping straight to 44.1kHz. 24-bit avoids baking in
# quantization noise DSD's dynamic range would otherwise lose. This FLAC
# is a temporary intermediate on its way to the pipeline's existing MP3
# pass (bitstream_engine deletes it once it converts it), so the extra
# size costs nothing.
TARGET_SAMPLE_RATE = "88200"
TARGET_SAMPLE_FMT = "s32"

# Matches sacd_extract's own "Processing [path] (N/M).." announcement,
# printed once per track as extraction begins it.
_TRACK_START_RE = re.compile(r'Processing \[.*?\]\s*\((\d+)/(\d+)\)')


def _cue_referenced_isos(root, iso_files):
    """
    Returns the subset of iso_files that a .cue sheet in the same folder
    points at -- those are raw CD-DA PCM dumps ("ISO/CUE" rips), which
    cue_engine.py already handles via its RAW_PCM_EXT path, NOT SACD
    filesystem images.

    Real bug, found in the 2026-10-01 review: both engines claimed every
    .iso. sacd_engine runs first, so a CD-DA ISO/CUE rip was sent to
    sacd_extract, which failed and printed a red "SACD extraction failed"
    error -- even though cue_engine then split it correctly right after.
    The result was fine; the console was lying.

    Matching mirrors cue_engine._find_audio_source(): a CUE's FILE
    reference matches an .iso either by exact filename or by stem (CUE
    sheets commonly say FILE "Album.wav" while the actual dump on disk is
    Album.iso).
    """
    ref_names = set()
    ref_stems = set()
    for cue_path in root.glob("*.cue"):
        try:
            content = cue_path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for ref in re.findall(r'FILE\s+"(.*?)"', content):
            ref_names.add(ref.lower())
            ref_stems.add(Path(ref).stem.lower())

    return {
        iso for iso in iso_files
        if iso.name.lower() in ref_names or iso.stem.lower() in ref_stems
    }


def process_sacd(root, artist, report_data):
    """
    Scans for SACD ISO images and extracts them to per-track FLAC files
    using the same filename convention cue_engine.py's split_cue() already
    produces (f"{track_id} - {artist} - {title}.flac") -- bitstream_engine.py
    needs zero changes, it only ever reads the leading digit prefix of
    whatever discrete tracks already exist.

    CD-DA ISO images referenced by a .cue sheet are skipped here and left
    for cue_engine.py (see _cue_referenced_isos above).

    CRITICAL SAFETY NOTE: every non-success path below MUST register the
    iso into failed_targets. janitor_engine.py Build 7.3.0 now also never
    deletes source-class files (.iso included) as a backstop, but
    failed_targets is still what drives the "conversion failed" safety
    alert and the audit log -- keep registering.
    """
    iso_files = list(root.glob("*.iso"))
    if not iso_files:
        return

    cdda_isos = _cue_referenced_isos(root, iso_files)
    for iso_path in sorted(cdda_isos):
        yield event("info", "CD audio image named in a CUE sheet; the CUE splitter will handle it", file=iso_path.name)

    iso_files = [iso for iso in iso_files if iso not in cdda_isos]
    if not iso_files:
        # Checked BEFORE the sacd_extract presence test below -- a CD-DA
        # ISO/CUE rip must never trigger a "sacd_extract.exe missing"
        # error on a machine that simply doesn't need it.
        return

    if not SACD_EXTRACT_EXE.exists():
        for iso_path in iso_files:
            report_data.setdefault('failed_targets', [])
            if iso_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(iso_path.name)
        yield event("error", f"sacd_extract.exe is missing from /bin, so {len(iso_files)} SACD image%s kept and not processed" % ("s were" if len(iso_files) != 1 else " was"))
        return

    for iso_path in iso_files:
        try:
            with tempfile.TemporaryDirectory(prefix="mf_sacd_") as tmp_dir_str:
                tmp_dir = Path(tmp_dir_str)

                if not report_data.get('extraction_occurred', False):
                    yield event("step", "Step 1: Extracting the SACD source", file=iso_path.name)
                    report_data['extraction_occurred'] = True
                else:
                    yield event("info", "Additional source: extracting", file=iso_path.name)

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
                        yield event("detail", f"Extracting track {current} of {total}")
                        yield signal("progress", phase=1, current=current, total=max(total, 1))
                    else:
                        extract_returncode, extract_err = payload

                dsf_files = sorted(tmp_dir.rglob("*.dsf"))

                if extract_returncode != 0 or not dsf_files:
                    err_line = extract_err or "no DSD tracks produced"
                    report_data.setdefault('failed_targets', [])
                    if iso_path.name not in report_data['failed_targets']:
                        report_data['failed_targets'].append(iso_path.name)
                    yield event("error", f"SACD extraction failed: {err_line}. The source was kept", file=iso_path.name)
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
                        yield event("detail", "Extracted", file=out_name)
                        report_data['extraction']['count'] += 1
                        success_count += 1
                        yield signal("progress", phase=1, current=i, total=total_tracks)
                    else:
                        err_line = (conv_res.stderr or "").strip().splitlines()[-1] if (conv_res.stderr or "").strip() else "unknown error"
                        yield event("error", f"DSD to FLAC conversion failed: {err_line}", file=out_name)
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
                        yield event("success", "SACD source deleted after every track converted")
                    except Exception:
                        pass
                else:
                    report_data.setdefault('failed_targets', [])
                    if iso_path.name not in report_data['failed_targets']:
                        report_data['failed_targets'].append(iso_path.name)
                    yield event("warning", f"Only {success_count} of {total_tracks} tracks converted, so the SACD source was kept for a retry")

        except Exception as e:
            # Same "never silent" principle cue_engine.py's own exception
            # handler establishes -- an unexpected failure here must never
            # vanish without a trace, and must never leave the source
            # unregistered (see the module docstring's safety note).
            report_data.setdefault('failed_targets', [])
            if iso_path.name not in report_data['failed_targets']:
                report_data['failed_targets'].append(iso_path.name)
            yield event("error", f"SACD processing error: {e}. The source was kept", file=iso_path.name)
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
