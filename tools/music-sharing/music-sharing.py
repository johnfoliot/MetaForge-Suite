# --- START OF FILE music-sharing.py ---
# ======================================================================
# MetaForge Tool Logic: Music Sharing
# v2 (2026-11-16): rebuilt (John's decisions the same day: embedded cover
# first, ask before replacing a video, copy the song's info into the MP4).
#
# One MP3 -> one 1080x1080 MP4 (H.264 still image + 192k AAC) with the
# caption overlay (branding.png), written to <Videos>\MetaForge Studio.
#   Picture:  the MP3's embedded cover, else folder.jpg, else plain black.
#   Safety:   rendered to "<name>.part.mp4", checked (it exists and its
#             length matches the track's within 1.5 s), then renamed. A
#             failed or stopped render leaves nothing behind (1.x left a
#             10-second "Sweet Home Chicago.mp4" from a failed render).
#   Progress: FFmpeg's own -progress position against the track's length.
# ======================================================================
import base64
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import Response, current_app, jsonify, request, stream_with_context

from common import config_handler
from common.mf_events import event, run_stream, signal

TOOL_DIR = Path(__file__).parent.resolve()
CAPTION = TOOL_DIR / "branding.png"
SIZE = 1080
LENGTH_TOLERANCE = 1.5   # seconds (AAC adds a little padding)


def output_dir():
    return Path.home() / "Videos" / "MetaForge Studio"


# --- [ TRACK INFO ] ---------------------------------------------------------

def _tags(path):
    """Title, artist, album, year and the embedded cover (bytes, mime) from the MP3."""
    from mutagen.id3 import ID3
    info = {"title": "", "artist": "", "album": "", "year": "", "cover": None}
    try:
        t = ID3(str(path))
    except Exception:
        return info
    for key, frame in (("title", "TIT2"), ("artist", "TPE1"), ("album", "TALB"), ("year", "TYER")):
        if frame in t:
            info[key] = str(t[frame].text[0]).strip()
    if not info["year"] and "TDRC" in t:
        info["year"] = str(t["TDRC"].text[0])[:4]
    pics = t.getall("APIC")
    if pics:
        front = next((p for p in pics if p.type == 3), pics[0])
        info["cover"] = (front.data, front.mime or "image/jpeg")
    return info


def _length(path):
    try:
        import mutagen
        f = mutagen.File(str(path))
        return float(f.info.length) if f and f.info else None
    except Exception:
        return None


def _picture(path, info):
    """('embedded'|'folder'|'none', bytes or None, mime)."""
    if info["cover"]:
        return "embedded", info["cover"][0], info["cover"][1]
    folder = Path(path).parent / "folder.jpg"
    if folder.exists():
        return "folder", folder.read_bytes(), "image/jpeg"
    return "none", None, None


def _clean_stem(path):
    return re.sub(r"[^\w\s\-\(\),&'.]", "", Path(path).stem).strip() or "MetaForge video"


def _numbered(target):
    n = 2
    while True:
        cand = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not cand.exists():
            return cand
        n += 1


def track_info(path):
    p = Path(path)
    if not p.exists():
        return {"status": "error", "message": "That file can't be found."}
    if p.suffix.lower() != ".mp3":
        return {"status": "error", "message": "Choose an MP3 file."}
    info = _tags(p)
    source, data, mime = _picture(p, info)
    target = output_dir() / f"{_clean_stem(p)}.mp4"
    return {
        "status": "ok", "path": str(p), "name": p.name,
        "title": info["title"] or p.stem, "artist": info["artist"], "album": info["album"], "year": info["year"],
        "length": _length(p),
        "picture": source,
        "picture_url": f"data:{mime};base64,{base64.b64encode(data).decode()}" if data else None,
        "video_name": target.name, "video_exists": target.exists(),
        "kept_name": _numbered(target).name if target.exists() else None,
    }


# --- [ DISPATCH ] -----------------------------------------------------------

def _run_state():
    """Survives the per-request module reload (ui/routes.py re-executes this file each call)."""
    return current_app.extensions.setdefault("sharing_run", {"lock": threading.Lock(), "stop": threading.Event(), "proc": None})


def run_logic(action, tools_dir, env_path):
    data = request.get_json(silent=True) or {}
    if action == "info":
        return jsonify(track_info(data.get("path", "")))
    if action == "stop":
        state = _run_state()
        state["stop"].set()
        if state["proc"] and state["proc"].poll() is None:
            state["proc"].terminate()
        return jsonify({"status": "ok"})
    if action == "render":
        state = _run_state()
        if not state["lock"].acquire(blocking=False):
            return jsonify({"status": "error", "message": "A video is already being made."}), 409
        state["stop"].clear()

        def guarded():
            try:
                yield from render_stream(data.get("path", ""), data.get("existing", "ask"), state)
            finally:
                state["proc"] = None
                state["lock"].release()

        return Response(stream_with_context(run_stream(guarded(), "Music Sharing")), mimetype="application/x-ndjson")
    if action == "show":
        target = Path(data.get("path", ""))
        try:
            if target.exists():
                subprocess.Popen(["explorer", "/select,", str(target)])
            else:
                output_dir().mkdir(parents=True, exist_ok=True)
                os.startfile(str(output_dir()))
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400


# --- [ RENDER ] -------------------------------------------------------------

def build_command(src, picture_file, out, info, total):
    cmd = [str(config_handler.FFMPEG_EXE), "-v", "error", "-nostats", "-progress", "pipe:1", "-y"]
    if picture_file:
        cmd += ["-loop", "1", "-framerate", "25", "-i", str(picture_file)]
    else:
        cmd += ["-f", "lavfi", "-i", f"color=c=black:s={SIZE}x{SIZE}:r=25"]
    cmd += ["-i", str(src)]
    crop = f"[0:v]scale={SIZE}:{SIZE}:force_original_aspect_ratio=increase,crop={SIZE}:{SIZE},setsar=1"
    if CAPTION.exists():
        cmd += ["-i", str(CAPTION)]
        fc = f"{crop}[bg];[bg][2:v]overlay=0:0,format=yuv420p[out]"
    else:
        fc = f"{crop},format=yuv420p[out]"
    cmd += ["-filter_complex", fc, "-map", "[out]", "-map", "1:a:0",
            # 25 fps: social sites reject very low frame rates.
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-r", "25",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
            "-map_metadata", "-1"]
    for key in ("title", "artist", "album"):
        if info.get(key):
            cmd += ["-metadata", f"{key}={info[key]}"]
    if info.get("year"):
        cmd += ["-metadata", f"date={info['year']}"]
    if total:
        cmd += ["-t", f"{total:.3f}"]
    cmd += ["-f", "mp4", str(out)]
    return cmd


def render_stream(path, existing, state):
    src = Path(path)
    if not src.exists():
        yield event("error", "The track can't be found.", file=str(src))
        return
    info = _tags(src)
    total = _length(src)
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{_clean_stem(src)}.mp4"
    if final.exists():
        if existing == "keep":
            final = _numbered(final)
        elif existing != "replace":
            yield event("error", f"A video named {final.name} already exists. Choose Replace or Keep both.")
            return
    part = final.with_name(final.stem + ".part.mp4")
    source, data, mime = _picture(src, info)
    pic_file = None
    yield event("step", f"Making a video of {info['title'] or src.stem}")
    yield event("info", {"embedded": "Picture: the cover stored in the MP3",
                         "folder": "Picture: folder.jpg from the album folder",
                         "none": "Picture: none found, so the video is a plain black square"}[source])
    try:
        if data:
            fd, name = tempfile.mkstemp(suffix=".png" if "png" in (mime or "") else ".jpg")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            pic_file = Path(name)
        cmd = build_command(src, pic_file, part, info, total)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        state["proc"] = proc
        errors = []
        reader = threading.Thread(target=lambda: errors.extend(proc.stderr.read().splitlines()), daemon=True)
        reader.start()
        last = -1
        for line in proc.stdout:
            if line.startswith("out_time_us=") and total:
                try:
                    done = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                pct = max(0, min(99, int(100 * done / total)))
                if pct != last:
                    last = pct
                    m, s = divmod(int(done), 60)
                    yield signal("progress", percent=pct, label=f"Making the video: {m}:{s:02d} of {int(total // 60)}:{int(total % 60):02d}")
        proc.wait()
        reader.join(timeout=5)
        if state["stop"].is_set():
            yield event("warning", "Stopped. No video was saved.")
            yield signal("progress", percent=0, label="Stopped")
            return
        if proc.returncode != 0 or not part.exists():
            reason = errors[-1] if errors else f"FFmpeg stopped with code {proc.returncode}"
            yield event("error", f"The video couldn't be made: {reason}")
            return
        got = _length(part)
        if total and (got is None or abs(got - total) > LENGTH_TOLERANCE):
            yield event("error", f"The video came out the wrong length ({got or 0:.1f} s instead of {total:.1f} s), so it wasn't saved.")
            return
        os.replace(part, final)
        yield signal("progress", percent=100, label="Finished")
        yield signal("video_ready", path=str(final), file_name=final.name)
        yield event("done", f"Your video is ready: {final.name}", file=str(out_dir))
    finally:
        if pic_file:
            pic_file.unlink(missing_ok=True)
        part.unlink(missing_ok=True)

# --- END OF FILE music-sharing.py ---
