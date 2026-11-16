# --- START OF FILE repair.py ---
# ======================================================================
# MetaForge Tool Logic: Audio Repair
# v2 (2026-11-16): rebuilt (John's decisions the same day: rebuild first,
# keep a copy of every original, files can be taken off the list).
#
# Each file is repaired on a COPY next to the original, checked, and only
# then swapped in (os.replace, atomic). The original is copied to
#   %APPDATA%\MetaForge\backups\repair\<date time>\<album>\...
# first. A copy that fails the check is thrown away; the original is
# untouched and stays on the list.
#
#   MP3:      1) mp3val's fix on the copy: drops damaged frames, no
#                re-encoding (an FFmpeg stream copy carries the damage
#                straight through, measured 2026-11-16)
#             2) still bad: re-encode at V0 with FFmpeg error concealment,
#                tags copied back from the original
#   Lossless: (queued by Unpack & Convert when its conversion failed)
#             converted the way Unpack & Convert does it: standard
#             "<number> - <artist> - <title>.mp3" name, V0, whitelisted
#             tags from the album's manifest.json. The source is moved to
#             the backup only after the MP3 passes the check.
#   Check:    no mp3val warnings, FFmpeg decodes it with no errors, and
#             the length is within 1 second of the original's.
#
# Files in data/repair (shared with 1.x through the junction):
#   remediation_queue.log  "<path> | <reason>" per line (Intelli-Tagger and
#                          Unpack & Convert add; format unchanged)
#   not_found.txt          paths that no longer exist
# repaired.log is no longer written: nothing ever read it.
# ======================================================================
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Response, current_app, jsonify, request, stream_with_context

from common import config_handler
from common.audio_check import decode_errors, length_seconds, mp3val_problems
from common.mf_events import _LogWriter, event, run_stream, signal

LENGTH_TOLERANCE = 1.0   # seconds
UC_DIR = Path(__file__).resolve().parent.parent / "unpack_convert"


# --- [ LIST FILES ] ---------------------------------------------------------

def _dir():
    return Path(config_handler.DATA_DIR) / "repair"


def _queue_file():
    return _dir() / "remediation_queue.log"


def _notfound_file():
    return _dir() / "not_found.txt"


_JOINED = re.compile(r"(?<!^)(?=[A-Za-z]:[\\/])")   # a drive letter mid-line = two entries glued together


def read_queue():
    """[(path, reason)], glued lines split, duplicates dropped (first kept)."""
    f = _queue_file()
    out, seen = [], set()
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        for part in _JOINED.split(line.strip()):
            if not part.strip():
                continue
            path, _, reason = part.partition("|")
            path, reason = path.strip(), reason.strip() or "Damaged audio"
            key = os.path.normcase(path)
            if path and key not in seen:
                seen.add(key)
                out.append((path, reason))
    return out


def _write(f, lines):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f.suffix + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lines), encoding="utf-8")   # always ends with a newline
    os.replace(tmp, f)


def remove_from_queue(path):
    """Re-read and drop one entry (keeps anything another tool appended meanwhile)."""
    key = os.path.normcase(path)
    _write(_queue_file(), [f"{p} | {r}" for p, r in read_queue() if os.path.normcase(p) != key])


def _add_not_found(path):
    f = _notfound_file()
    have = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    if os.path.normcase(path) not in {os.path.normcase(h) for h in have}:
        _write(f, [h for h in have if h.strip()] + [path])


def _album_root(path):
    """The album folder: the nearest of the file's folder / its parent holding manifest.json."""
    p = Path(path).parent
    for cand in (p, p.parent):
        if (cand / "manifest.json").exists():
            return cand
    return p


# --- [ DISPATCH ] -----------------------------------------------------------

def _run_state():
    """Survives the per-request module reload (ui/routes.py re-executes this file each call)."""
    return current_app.extensions.setdefault("repair_run", {"lock": threading.Lock(), "stop": threading.Event()})


def run_logic(action, tools_dir, env_path):
    if action == "get_queue":
        nf = _notfound_file()
        return jsonify({
            "status": "ok",
            "queue": [{"path": p, "name": Path(p).name, "album": _album_root(p).name,
                       "reason": r, "exists": Path(p).exists()} for p, r in read_queue()],
            "not_found": len([l for l in nf.read_text(encoding="utf-8").splitlines() if l.strip()]) if nf.exists() else 0,
        })
    if action == "remove":
        path = (request.get_json(silent=True) or {}).get("path", "")
        if _run_state()["lock"].locked():
            return jsonify({"status": "error", "message": "Wait for the repair run to finish."}), 409
        remove_from_queue(path)
        return jsonify({"status": "ok"})
    if action == "stop":
        _run_state()["stop"].set()
        return jsonify({"status": "ok"})
    if action == "run":
        state = _run_state()
        if not state["lock"].acquire(blocking=False):
            return jsonify({"status": "error", "message": "A repair run is already going."}), 409
        state["stop"].clear()

        def guarded():
            try:
                yield from repair_stream(state["stop"])
            finally:
                state["lock"].release()

        return Response(stream_with_context(run_stream(guarded(), "Audio Repair")), mimetype="application/x-ndjson")
    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400


# --- [ CHECKS AND STEPS ] ---------------------------------------------------

def check(path, ref_len):
    """None if the file is sound, else a plain reason."""
    problems = mp3val_problems(path)
    if problems:
        return f"still damaged ({problems[0]})"
    errs = decode_errors(path)
    if errs:
        return f"still doesn't play cleanly ({errs} decoding error{'s' if errs != 1 else ''})"
    new_len = length_seconds(path)
    if ref_len and new_len is not None and abs(new_len - ref_len) > LENGTH_TOLERANCE:
        return f"its length changed by {abs(new_len - ref_len):.1f} seconds"
    return None


def _ffmpeg_v0(src, dst, keep_metadata):
    cmd = [str(config_handler.FFMPEG_EXE), "-v", "error", "-err_detect", "ignore_err", "-i", str(src),
           "-map", "0:a:0", "-c:a", "libmp3lame", "-q:a", "0",
           "-map_metadata", "0" if keep_metadata else "-1", "-id3v2_version", "3",
           "-fflags", "+bitexact", "-y", str(dst)]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=1800)
    return res.returncode == 0 and Path(dst).exists() and Path(dst).stat().st_size > 0


def _copy_tags(src, dst):
    """Every ID3 frame from the original onto the re-encoded copy (ID3v2.3, UTF-16)."""
    from mutagen.id3 import ID3
    try:
        original = ID3(str(src))
    except Exception:
        return False
    new = ID3()
    for frame in original.values():
        if hasattr(frame, "encoding"):
            frame.encoding = 1
        new.add(frame)
    new.update_to_v23()
    new.save(str(dst), v2_version=3)
    return True


class _Run:
    """One repair run: backup folder and per-album MetaForge.log writers, made on first use."""

    def __init__(self):
        self.stamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        self.logs = {}

    def backup_dir(self, root):
        d = Path(config_handler.APPDATA_MF) / "backups" / "repair" / self.stamp / root.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def backup(self, path, root, move=False):
        rel = Path(path).relative_to(root) if Path(path).is_relative_to(root) else Path(Path(path).name)
        dest = self.backup_dir(root) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        (shutil.move if move else shutil.copy2)(str(path), str(dest))
        return dest

    def log(self, root, kind, text, file):
        if root not in self.logs:
            self.logs[root] = _LogWriter(root, "Audio Repair")
        self.logs[root].line(kind, text, file)

    def close(self):
        for w in self.logs.values():
            w.close(True)


def _repair_mp3(src, root, run):
    """Returns (ok, text)."""
    ref = length_seconds(src)
    tmp = src.with_name(src.stem + ".mf-repair.tmp.mp3")
    try:
        shutil.copy2(src, tmp)
        mp3val_problems(tmp, fix=True)
        why = check(tmp, ref)
        how = "Damaged frames removed, no re-encoding"
        if why:
            tmp.unlink(missing_ok=True)
            if not _ffmpeg_v0(src, tmp, keep_metadata=False):
                return False, f"Couldn't be repaired: the first attempt was {why}, and re-encoding failed. The original is untouched."
            why = check(tmp, ref)
            if why:
                return False, f"Couldn't be repaired: even after re-encoding it was {why}. The original is untouched."
            tagged = _copy_tags(src, tmp)
            how = "Re-encoded at V0" + ("" if tagged else " (the original's tags couldn't be read, so it has none)")
        backup = run.backup(src, root)
        os.replace(tmp, src)
        return True, f"{how}. Checked: plays cleanly. Original kept in {backup.parent}."
    finally:
        Path(tmp).unlink(missing_ok=True)


def _uc():
    """Unpack & Convert's own code, so a lossless source is named and tagged exactly as it would be."""
    eng = str(UC_DIR / "engines")
    if eng not in sys.path:
        sys.path.insert(0, eng)
    import bitstream_engine
    spec = importlib.util.spec_from_file_location("mf_unpack_convert_for_repair", UC_DIR / "unpack_convert.py")
    uc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uc)
    return uc, bitstream_engine


def lossless_target(src, root):
    """(target mp3 path, tag args) for a lossless source, following Unpack & Convert's rules."""
    import json
    uc, be = _uc()
    m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    artist, album = m.get("artist_seed") or "", m.get("album_seed") or ""
    category = m.get("category_seed")
    if not artist or not album:
        raise ValueError("the album's manifest.json has no artist or album name")
    category = None if category in (None, "", "None Provided") else category

    stem = src.stem
    parts = stem.split(" - ")
    title = parts[-1].strip() if len(parts) >= 2 else re.sub(r"^\d+[\s\.\-_]*", "", stem).strip()
    num = re.match(r"^(\d+)", src.name)
    if not num:
        raise ValueError("its file name doesn't start with a track number")
    claimed = int(num.group(1))

    discs = uc._find_disc_dirs(root) if src.parent != root else []
    is_multi = len(discs) > 1
    if is_multi:
        disc = [d.resolve() for d in discs].index(src.parent.resolve()) + 1
        filing = str(claimed) if claimed >= 100 else str(disc * 100 + claimed)
        per_disc = int(filing) % 100
        offset = 0
        for d in discs[:disc - 1]:   # each earlier disc's highest track number (Unpack & Convert's offset)
            nums = [int(x.group(1)) for f in d.iterdir() if f.is_file() and (x := re.match(r"^(\d+)", f.name))]
            offset += max([n % 100 if n >= 100 else n for n in nums], default=0)
        track, disc_args = str(offset + per_disc), (disc, len(discs), True)
    else:
        filing, track, disc_args = str(claimed), str(claimed), (1, 1, False)
    target = src.parent / f"{filing} - {artist} - {title}.mp3"
    return target, (artist, album, title, track, category) + disc_args, be


def _repair_lossless(src, root, run):
    if not (root / "manifest.json").exists():
        return False, "No manifest.json in the album folder, so the right name and tags aren't known. Run Unpack & Convert on the album first."
    try:
        target, tag_args, be = lossless_target(src, root)
    except Exception as e:
        return False, f"Not converted: {e}."
    ref = length_seconds(src)
    tmp = target.with_name(target.stem + ".mf-repair.tmp.mp3")
    try:
        if not _ffmpeg_v0(src, tmp, keep_metadata=True):
            return False, "FFmpeg couldn't convert it even with error concealment. The source is untouched."
        why = check(tmp, ref)
        if why:
            return False, f"Converted, but the result was {why}. The source is untouched."
        be._enforce_metadata_truth(tmp, *tag_args)
        if target.exists():
            run.backup(target, root, move=True)
        os.replace(tmp, target)
        backup = run.backup(src, root, move=True)
        return True, (f"Converted to MP3 (V0) as {target.name}. Checked: plays cleanly. "
                      f"Source moved to {backup.parent}. Run the Intelli-Tagger on this album next.")
    finally:
        Path(tmp).unlink(missing_ok=True)


# --- [ THE RUN ] ------------------------------------------------------------

def repair_stream(stop):
    items = read_queue()
    total = len(items)
    if not total:
        yield event("done", "Nothing is waiting to be repaired.")
        return
    run = _Run()
    fixed = failed = gone = 0
    yield event("step", f"Repairing {total} file{'s' if total != 1 else ''}")
    try:
        for i, (path, reason) in enumerate(items, 1):
            if stop.is_set():
                break
            yield signal("progress", percent=round(100 * (i - 1) / total), label=f"Repairing {i} of {total}")
            src = Path(path)
            if not src.exists():
                remove_from_queue(path)
                _add_not_found(path)
                gone += 1
                yield event("warning", "File not found. Moved to the not-found list.", file=path)
                continue
            root = _album_root(src)
            try:
                ok, text = (_repair_mp3 if src.suffix.lower() == ".mp3" else _repair_lossless)(src, root, run)
            except Exception as e:   # one bad file never stops the run
                ok, text = False, f"Couldn't be repaired ({e}). The original is untouched."
            if ok:
                remove_from_queue(path)
                fixed += 1
                yield event("track", text, file=src.name)
            else:
                failed += 1
                yield event("warning", text + " It stays on the list.", file=src.name)
            run.log(root, "track" if ok else "warning", text, src.name)
    finally:
        run.close()
    if stop.is_set():
        left = len(read_queue())
        yield event("warning", f"Stopped. {left} file{'s' if left != 1 else ''} still waiting; nothing was lost.")
    yield signal("progress", percent=100, label="Stopped" if stop.is_set() else "Finished")
    parts = [f"Repaired {fixed} of {total}."]
    if failed:
        parts.append(f"{failed} couldn't be repaired and {'stay' if failed != 1 else 'stays'} on the list.")
    if gone:
        parts.append(f"{gone} {'were' if gone != 1 else 'was'} not found.")
    yield event("done", " ".join(parts))

# --- END OF FILE repair.py ---
