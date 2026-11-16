# --- START OF FILE youtube_mp3.py ---
# ======================================================================
# MetaForge Tool Logic: YouTube to MP3
# v2 (2026-11-16): built (the 1.x tool was an empty shell). John's
# decisions the same day: V0 MP3s, each album in its own "Artist - Album"
# folder for Unpack & Convert, and a review of the cut points before a
# whole-album video is split.
#
# Three kinds of link:
#   song      one video -> one MP3
#   playlist  a YouTube playlist (list=...) -> one MP3 per video
#   album     a whole album uploaded as ONE video -> one MP3 per song.
#             Cut points come from, in order: the video's chapters, times
#             in its description, or quiet gaps in the audio, placed with
#             MusicBrainz (or description) track lengths when known. The
#             user reviews and can play every cut before anything is made.
#
# Quality: YouTube's best audio is ~130 kbps AAC/Opus. It is downloaded
# as-is and encoded ONCE to MP3 V0 (the suite's standard), so there's no
# extra generation of loss; Unpack & Convert only renames MP3s.
#
# Files:
#   %APPDATA%\MetaForge\youtube_mp3\<id>\   downloaded audio, deleted
#                                            once its MP3s are made
#   data\youtube_mp3\settings.json          the remembered "Save in" folder
# ======================================================================
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import Response, current_app, jsonify, request, send_file, stream_with_context

from common import config_handler, mb_client
from common.mf_events import event, run_stream, signal

YTDLP = str(config_handler.YT_DLP_EXE)
FFMPEG = str(config_handler.FFMPEG_EXE)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ALBUM_MINUTES = 15          # a single video longer than this is offered as an album first
WORK_KEEP_DAYS = 7          # downloads left behind by an abandoned album are cleared after this
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be"}


def _work_root():
    return Path(config_handler.APPDATA_MF) / "youtube_mp3"


def _settings_file():
    return Path(config_handler.DATA_DIR) / "youtube_mp3" / "settings.json"


def _load_settings():
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(s):
    f = _settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    os.replace(tmp, f)


# --- [ LINKS ] --------------------------------------------------------------

def parse_link(url):
    """-> {"kind": "video"|"playlist", "id", "url"} or None if it isn't a YouTube link.

    A Mix ("RD...") or Watch Later/Liked list is endless or personal, so a
    link carrying one is treated as its video.
    """
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or host not in YT_HOSTS:
        return None
    q = parse_qs(u.query)
    lst = (q.get("list") or [""])[0]
    if host.endswith("youtu.be"):
        vid = u.path.strip("/").split("/")[0]
    elif u.path.startswith(("/shorts/", "/live/", "/embed/")):
        vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else ""
    else:
        vid = (q.get("v") or [""])[0]
    if lst and ID_RE.match(lst) and not lst.startswith(("RD", "UL")) and lst not in ("WL", "LL"):
        if u.path.startswith("/playlist") or not vid:
            return {"kind": "playlist", "id": lst, "url": f"https://www.youtube.com/playlist?list={lst}"}
        # A video link that also names a playlist: the playlist is what was shared
        return {"kind": "playlist", "id": lst, "url": f"https://www.youtube.com/playlist?list={lst}", "video": vid}
    if vid and ID_RE.match(vid):
        return {"kind": "video", "id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
    return None


def _ytdlp(args, timeout=120):
    r = subprocess.run([YTDLP, "--no-warnings", "--no-update", *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=NO_WINDOW)
    if r.returncode != 0:
        msg = (r.stderr or "").strip().splitlines()
        raise RuntimeError(_plain_error(msg[-1] if msg else "yt-dlp failed"))
    return r.stdout


def _plain_error(line):
    low = line.lower()
    if "private" in low:
        return "This video or playlist is private."
    if "unavailable" in low or "removed" in low or "terminated" in low:
        return "YouTube says this video isn't available."
    if "sign in" in low or "age" in low:
        return "YouTube wants a signed-in account for this video (age or region limits), so it can't be fetched."
    if "unable to download webpage" in low or "getaddrinfo" in low or "timed out" in low:
        return "YouTube couldn't be reached. Check the internet connection and try again."
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", line).strip() or "yt-dlp couldn't read this link."


# --- [ NAMES ] --------------------------------------------------------------

_BRACKET_NOISE = re.compile(
    r"\s*[\(\[]([^\)\]]*\b(official|audio|video|lyrics?|visuali[sz]er|hd|hq|4k|1080p|720p|remaster(ed)?|full album|"
    r"vinyl|lp|stereo|mono)\b[^\)\]]*|\d{4})[\)\]]", re.I)
_PHRASE_NOISE = re.compile(r"\s*\b(full album|vinyl lp|vinyl rip|lp rip|official (audio|video)|\d{4})\s*$", re.I)
DASH = re.compile(r"\s+[-–—]\s+")


def clean_title(s):
    s = _BRACKET_NOISE.sub("", s or "")
    for _ in range(3):
        s2 = _PHRASE_NOISE.sub("", s).strip(" -–—|")
        if s2 == s:
            break
        s = s2
    return re.sub(r"\s{2,}", " ", s).strip()


def artist_from_channel(ch):
    ch = re.sub(r"\s*-\s*Topic$", "", ch or "").strip()
    return re.sub(r"VEVO$", "", ch).strip()


def split_artist(title):
    """'Artist - Title' -> (artist, title); no dash -> ('', title)."""
    parts = DASH.split(title, maxsplit=1)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("", title.strip())


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "").strip().rstrip(". ")
    return s[:120] or "Untitled"


# --- [ TRACK LISTS IN DESCRIPTIONS ] -----------------------------------------

TS = r"(?:\d{1,2}:)?\d{1,2}:\d{2}"
_TS_FIRST = re.compile(rf"^\s*(?:\d{{1,2}}[\.\)]\s*)?[\(\[]?(?P<ts>{TS})[\)\]]?\s*[-–—:.|)]?\s*(?P<title>\S.*?)\s*$")
_TS_LAST = re.compile(rf"^\s*(?:\d{{1,2}}[\.\)]\s*|[A-Da-d]\d{{1,2}}\.?\s+)?(?P<title>\S.*?)\s*[-–—|]?\s*[\(\[]?(?P<ts>{TS})[\)\]]?\s*$")
_NAMED = re.compile(r"^(?:[A-Da-d]\d{1,2}\.?|\d{1,2}[\.\)]|\d{1,2}\s*[-–—]|\d{1,2}(?=\s))\s*(?P<title>\S.*?)\s*$")


def secs(ts):
    v = 0
    for p in ts.split(":"):
        v = v * 60 + int(p)
    return v


def _strip_number(t):
    return re.sub(r"^\s*(?:[A-Da-d]\d{1,2}\.?|\d{1,2}[\.\)]|\d{1,2}\s*[-–—])\s+", "", t).strip()


def tracks_from_description(desc, duration):
    """-> {"titles": [...], "starts": [...] or None, "lengths": [...] or None} or None.

    Lines with times are start times when they rise from ~0, otherwise
    track lengths (when they add up to about the video's length). Lines
    numbered "1." or "A1" with no time give titles only.
    """
    lines = [l for l in (desc or "").splitlines() if l.strip()]
    timed = []
    for l in lines:
        m = _TS_FIRST.match(l) or _TS_LAST.match(l)
        if m and not re.match(r"^\s*https?://", l):
            title = _strip_number(m.group("title")).strip(" -–—|")
            if title:
                timed.append((secs(m.group("ts")), title))
    if len(timed) >= 3:
        times = [t for t, _ in timed]
        if times[0] <= 15 and all(b > a for a, b in zip(times, times[1:])) and times[-1] < (duration or 1e9):
            return {"titles": [t for _, t in timed], "starts": times, "lengths": None, "from": "times"}
        if duration and abs(sum(times) - duration) <= max(60, duration * 0.08):
            return {"titles": [t for _, t in timed], "starts": None, "lengths": times, "from": "lengths"}
    named = []
    for l in lines:
        if l[:1].isspace():
            continue          # indented credit lines under a track ("Written-By - ...")
        m = _NAMED.match(l)
        if m:
            named.append(m.group("title").strip())
    if len(named) >= 3:
        return {"titles": named, "starts": None, "lengths": None, "from": "names"}
    return None


# --- [ MUSICBRAINZ TRACK LENGTHS ] -------------------------------------------

def _mb_cache():
    return current_app.extensions.setdefault("yt_mb_cache", {})


def mb_tracks(artist, album, count=None):
    """The MusicBrainz release best matching artist + album (and the track
    count, when known): {"id", "title", "date", "tracks": [{"title", "length"}]} or None."""
    if not artist or not album:
        return None
    key = (artist.lower(), album.lower(), count)
    cache = _mb_cache()
    if key in cache:
        return cache[key]
    found = None
    try:
        # Words, not an exact phrase: YouTube's "Dutch Mason Blues Band" is
        # MusicBrainz's "Dutch Mason" (measured 2026-11-16; the phrase search
        # found nothing, the word search scored the right release 100).
        esc = lambda s: re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", s)
        res = mb_client.get("release", {"query": f"release:({esc(album)}) AND artist:({esc(artist)})", "limit": 10}).json()
        cands = [r for r in res.get("releases", []) if int(r.get("score", 0)) >= 90]
        if count:
            cands.sort(key=lambda r: (r.get("track-count") != count, -int(r.get("score", 0))))
        for r in cands[:3]:
            if count and r.get("track-count") != count:
                continue
            full = mb_client.get(f"release/{r['id']}", {"inc": "recordings"}).json()
            tracks = [{"title": t.get("title", ""), "length": (t.get("length") or 0) / 1000}
                      for m in full.get("media", []) for t in m.get("tracks", [])]
            if tracks and all(t["length"] > 0 for t in tracks):
                found = {"id": r["id"], "title": r.get("title", ""), "date": r.get("date", ""), "tracks": tracks}
                break
    except Exception as e:   # MusicBrainz busy or unreachable: split by the audio alone
        print(f"[youtube_mp3] MusicBrainz lookup skipped: {e}")
        return None
    cache[key] = found
    return found


# --- [ FINDING THE CUTS ] ----------------------------------------------------

HOP = 0.05     # seconds per loudness frame


def find_gaps(src):
    """Quiet stretches in the audio, judged against the music around them
    (vinyl surface noise is never true silence). -> (duration, [gap])."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
    sr = 11025
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True, creationflags=NO_WINDOW).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = int(sr * HOP)
    if len(x) < n * 10:
        return len(x) / sr, []
    db = 10 * np.log10(np.mean(x[: len(x) // n * n].reshape(-1, n) ** 2, axis=1) + 1e-10)
    w = int(20 / HOP)
    ref = np.percentile(sliding_window_view(np.pad(db, w // 2, mode="edge"), w)[: len(db)], 80, axis=1)
    depth = ref - db
    quiet = depth > 12
    runs, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if (j - i) * HOP >= 0.3:
                runs.append([i * HOP, j * HOP, float(depth[i:j].mean()), float(depth[i:j].max())])
            i = j
        else:
            i += 1
    gaps = []
    for r in runs:      # quiet runs a moment apart are one gap
        if gaps and r[0] - gaps[-1]["end"] < 2.5:
            g = gaps[-1]
            g["end"], g["depth"] = r[1], max(g["depth"], r[2])
        else:
            gaps.append({"start": r[0], "end": r[1], "depth": r[2]})
    for g in gaps:
        g["len"] = g["end"] - g["start"]
        g["score"] = g["depth"] * g["len"] ** 0.5
        g["strong"] = g["depth"] >= 25 and g["len"] >= 1.0
        g["cut"] = max(g["start"], g["end"] - 0.4)    # just before the next song starts
    return len(x) / sr, gaps


def place_cuts(n, duration, gaps, lengths=None):
    """Start times for n tracks. -> [(start, how)]; how: start | gap | faint | length | guess."""
    if n <= 1:
        return [(0.0, "start")]
    inner = [g for g in gaps if 10 < g["cut"] < duration - 10]
    out = [(0.0, "start")]
    if lengths and len(lengths) == n:
        prev = 0.0
        for i in range(1, n):
            exp = prev + lengths[i - 1]
            near = [g for g in inner if abs(g["cut"] - exp) <= 20 and g["cut"] > prev + 15]
            if near:
                g = max(near, key=lambda g: g["score"] - abs(g["cut"] - exp) * 0.5)
                prev = g["cut"]
                out.append((prev, "gap" if g["strong"] else "faint"))
            else:
                prev = min(exp, duration - 1)
                out.append((prev, "length"))
        return out
    chosen = []
    for g in sorted(inner, key=lambda g: -g["score"]):
        if len(chosen) == n - 1:
            break
        if all(abs(g["cut"] - c["cut"]) >= 30 for c in chosen):
            chosen.append(g)
    starts = sorted([(g["cut"], "gap" if g["strong"] else "faint") for g in chosen])
    out += starts
    while len(out) < n:      # not enough gaps: split the longest piece in half
        bounds = [s for s, _ in out] + [duration]
        k = max(range(len(out)), key=lambda i: bounds[i + 1] - bounds[i])
        out.insert(k + 1, ((bounds[k] + bounds[k + 1]) / 2, "guess"))
    return out


# --- [ DOWNLOADING AND ENCODING ] --------------------------------------------

def _run_state():
    """Survives the per-request module reload (ui/routes.py re-executes this file each call)."""
    return current_app.extensions.setdefault("yt_run", {"lock": threading.Lock(), "stop": threading.Event(), "proc": None})


def _source_file(work):
    for f in sorted(work.glob("source.*")):
        if f.suffix not in (".part", ".ytdl") and f.stat().st_size > 0:
            return f
    return None


def download(url, work, state, label):
    """Best audio, as-is, into work/source.<ext>. Yields events and progress; returns the file."""
    have = _source_file(work)
    if have:
        yield event("info", "Already downloaded, so it's used again", file=have.name)
        return have
    work.mkdir(parents=True, exist_ok=True)
    cmd = [YTDLP, "--no-warnings", "--no-update", "--no-playlist", "-f", "bestaudio/best", "--newline",
           "--progress-template", "download:MFP %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s",
           "-o", str(work / "source.%(ext)s"), url]
    for attempt in (1, 2):
        # One pipe for both streams: two separate pipes can deadlock if
        # yt-dlp fills the unread one.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        state["proc"] = proc
        last, errors = 0, []
        for line in proc.stdout:
            if state["stop"].is_set():
                proc.kill()
                break
            m = re.match(r"MFP (\d+) (\S+) (\S+)", line.strip())
            if m:
                got = int(m.group(1))
                total = next((int(v) for v in (m.group(2), m.group(3)) if v.isdigit()), 0)
                pct = got * 100 / total if total else 0
                if pct - last >= 2 or pct >= 100:
                    last = pct
                    yield signal("progress", percent=pct, label=f"{label}: {got / 1048576:.1f} of {total / 1048576:.1f} MB")
            elif line.startswith("ERROR"):
                errors.append(line.strip())
        proc.wait()
        state["proc"] = None
        if state["stop"].is_set():
            return None
        if proc.returncode == 0:
            break
        problem = _plain_error(errors[-1] if errors else "The download failed.")
        # YouTube now and then refuses a download (HTTP 403) that works a
        # moment later (measured 2026-11-16), so try once more.
        if attempt == 1 and not any(w in problem for w in ("private", "isn't available", "signed-in")):
            for f in work.glob("source.*"):
                f.unlink(missing_ok=True)
            yield event("info", f"YouTube refused the download ({problem}); trying again")
            time.sleep(2)
            continue
        raise RuntimeError(problem)
    f = _source_file(work)
    if not f:
        raise RuntimeError("The download finished but no audio file was found.")
    return f


def encode(src, dest, start, end, tags):
    """One MP3 V0 from src[start:end], tags written, through a .part file."""
    tmp = dest.with_name(dest.name + ".part")
    cmd = [FFMPEG, "-v", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    if end:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(src), "-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-q:a", "0",
            "-map_metadata", "-1", "-id3v2_version", "3", "-f", "mp3"]
    for k, v in tags.items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(tmp))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError((r.stderr or "").strip().splitlines()[-1] if r.stderr.strip() else "FFmpeg couldn't make the MP3.")
    os.replace(tmp, dest)


def _remove_work(vid):
    """Delete a downloaded source. Windows refuses while the preview player
    still has it open, so try a few times; anything left goes after WORK_KEEP_DAYS."""
    d = _work_root() / vid
    for _ in range(5):
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            return
        time.sleep(0.5)


def _album_folder(data):
    parent = (data.get("folder") or "").strip()
    if not parent or not Path(parent).is_dir():
        raise ValueError("Choose the folder to save in.")
    artist, album = (data.get("artist") or "").strip(), (data.get("album") or "").strip()
    if not artist or not album:
        raise ValueError("Fill in the artist and the album.")
    folder = Path(parent) / safe_name(f"{artist} - {album}")
    if folder.exists() and any(folder.iterdir()):
        raise ValueError(f'A folder named "{folder.name}" already has files in it. Change the album name, or move that folder first.')
    return folder


def _track_name(n, artist, title):
    return safe_name(f"{n:02d} - {artist} - {title}") + ".mp3"


# --- [ RUNS ] ----------------------------------------------------------------

def song_run(data, state):
    folder = _album_folder(data)
    artist, album, title = data["artist"].strip(), data["album"].strip(), (data.get("title") or "").strip() or "Untitled"
    yield event("step", "Downloading the audio")
    src = yield from download(data["url"], _work_root() / data["id"], state, "Downloading")
    if not src:
        yield event("warning", "Stopped. Nothing was made.")
        return
    yield event("step", "Making the MP3")
    folder.mkdir(parents=True, exist_ok=True)
    name = _track_name(1, artist, title)
    encode(src, folder / name, 0, None, {"title": title, "artist": artist, "album": album, "track": "1/1"})
    yield event("track", "Made (MP3 V0, track 1)", file=name)
    _remove_work(data["id"])
    yield signal("progress", percent=100, label="Done")
    yield event("done", f"1 MP3 saved in {folder}")
    yield signal("made", folder=str(folder), artist=artist, album=album)


def playlist_run(data, state):
    folder = _album_folder(data)
    artist, album = data["artist"].strip(), data["album"].strip()
    items = [t for t in data.get("tracks") or [] if t.get("include") and ID_RE.match(t.get("id") or "")]
    if not items:
        raise ValueError("Tick at least one song.")
    folder.mkdir(parents=True, exist_ok=True)
    total, made = len(items), 0
    for n, t in enumerate(items, 1):
        if state["stop"].is_set():
            break
        title = (t.get("title") or "").strip() or "Untitled"
        yield event("step", f"Song {n} of {total}: {title}")
        try:
            src = yield from download(f"https://www.youtube.com/watch?v={t['id']}", _work_root() / t["id"], state,
                                      f"Song {n} of {total}")
            if not src:
                break
            name = _track_name(n, artist, title)
            encode(src, folder / name, 0, None, {"title": title, "artist": artist, "album": album, "track": f"{n}/{total}"})
            _remove_work(t["id"])
            made += 1
            yield event("track", f"Made (MP3 V0, track {n})", file=name)
        except Exception as e:     # never abort the album for one bad video
            yield event("error", f"Song {n} was skipped: {e}", file=title)
        yield signal("progress", percent=n * 100 / total, label=f"{n} of {total} songs")
    if state["stop"].is_set():
        yield event("warning", f"Stopped. {made} of {total} MP3s were made.")
    else:
        yield event("done", f"{made} of {total} MP3s saved in {folder}")
    if made:
        yield signal("made", folder=str(folder), artist=artist, album=album)


def album_find(data, state):
    """Download the whole-album video, then propose a start time for every title."""
    titles = [t.strip() for t in data.get("titles") or [] if t.strip()]
    if not titles:
        raise ValueError("List the track titles, one per line.")
    _album_folder(data)     # problems with the folder show now, not after the download
    yield event("step", "Downloading the audio")
    src = yield from download(data["url"], _work_root() / data["id"], state, "Downloading")
    if not src:
        yield event("warning", "Stopped.")
        return
    yield signal("progress", percent=100, label="Listening for the gaps between songs…", busy=True)
    yield event("step", "Finding where each song starts")
    duration, gaps = find_gaps(src)
    n = len(titles)
    starts, lengths, basis = data.get("starts"), None, None
    if starts and len(starts) == n:
        rows = [(float(s), "chapter" if data.get("starts_from") == "chapters" else "times") for s in starts]
        basis = "chapters" if data.get("starts_from") == "chapters" else "the times in the description"
    else:
        if data.get("lengths") and len(data["lengths"]) == n:
            lengths, basis = [float(v) for v in data["lengths"]], "the track lengths in the description"
        else:
            mb = mb_tracks(data.get("artist", "").strip(), data.get("album", "").strip(), n)
            if mb:
                lengths = [t["length"] for t in mb["tracks"]]
                basis = f'MusicBrainz track lengths ({mb["title"]}{", " + mb["date"][:4] if mb.get("date") else ""})'
        rows = place_cuts(n, duration, gaps, lengths)
    if basis:
        yield event("info", f"Placed using {basis}")
    else:
        yield event("info", "No track lengths were found, so the cuts are placed at the clearest gaps")
    check = sum(1 for _, how in rows if how in ("faint", "length", "guess"))
    yield event("success", f"{n} start times found" + (f"; {check} to listen to" if check else ""))
    yield signal("progress", percent=100, label="Ready to check")
    yield signal("cuts", duration=duration, basis=basis or "",
                 rows=[{"title": t, "start": round(s, 2), "how": how} for t, (s, how) in zip(titles, rows)])


def album_make(data, state):
    folder = _album_folder(data)
    artist, album = data["artist"].strip(), data["album"].strip()
    rows = data.get("rows") or []
    src = _source_file(_work_root() / data["id"])
    if not src:
        raise ValueError("The downloaded audio is gone. Choose Find the tracks again.")
    starts = [float(r["start"]) for r in rows]
    if not rows or starts[0] < 0 or any(b <= a for a, b in zip(starts, starts[1:])):
        raise ValueError("Each song has to start after the one before it.")
    folder.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    yield event("step", f"Making {total} MP3s")
    yield signal("progress", percent=0, label=f"0 of {total} MP3s")

    def one(n, r):
        if state["stop"].is_set():
            return n, None, None, "stopped"
        title = (r.get("title") or "").strip() or "Untitled"
        name = _track_name(n, artist, title)
        try:
            encode(src, folder / name, starts[n - 1], starts[n] if n < total else None,
                   {"title": title, "artist": artist, "album": album, "track": f"{n}/{total}"})
            return n, title, name, None
        except Exception as e:
            return n, title, name, str(e)

    # FFmpeg's MP3 encoder uses one core, so tracks are made several at a
    # time (a 9-track album: ~2 minutes one by one, measured 2026-11-16).
    from concurrent.futures import ThreadPoolExecutor, as_completed
    made = done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1))) as pool:
        for fut in as_completed([pool.submit(one, n, r) for n, r in enumerate(rows, 1)]):
            n, title, name, problem = fut.result()
            done += 1
            if problem == "stopped":
                continue
            if problem:
                yield event("error", f"Track {n} wasn't made: {problem}", file=title)
            else:
                made += 1
                yield event("track", f"Made (MP3 V0, track {n})", file=name)
            yield signal("progress", percent=done * 100 / total, label=f"{done} of {total} MP3s")
    if state["stop"].is_set():
        yield event("warning", f"Stopped. {made} of {total} MP3s were made; the downloaded audio is kept so it can be done again.")
        return
    if made == total:
        _remove_work(data["id"])
    yield event("done", f"{made} of {total} MP3s saved in {folder}")
    if made:
        yield signal("made", folder=str(folder), artist=artist, album=album)


RUNS = {"song": song_run, "playlist": playlist_run, "album_find": album_find, "album_make": album_make}


# --- [ LOOKUP ] --------------------------------------------------------------

def inspect(url):
    link = parse_link(url)
    if not link:
        return {"status": "error", "message": "That isn't a YouTube link. Copy the address of a YouTube video or playlist."}
    _clear_old_work()
    if link["kind"] == "playlist":
        info = json.loads(_ytdlp(["--flat-playlist", "--yes-playlist", "-J", link["url"]]))
        entries = [e for e in info.get("entries") or [] if e and e.get("id")]
        ptitle = re.sub(r"^(Album|Playlist)\s*[-–—:]\s*", "", info.get("title") or "").strip()
        artist = artist_from_channel(info.get("channel") or info.get("uploader") or "")
        guess_a, guess_album = split_artist(clean_title(ptitle))
        if guess_a:
            artist = guess_a
        tracks = []
        for e in entries:
            t = clean_title(e.get("title") or "")
            a, rest = split_artist(t)
            if a and artist and a.lower() == artist.lower():
                t = rest
            tracks.append({"id": e["id"], "title": t, "duration": e.get("duration"),
                           "include": (e.get("title") or "") not in ("[Private video]", "[Deleted video]")})
        return {"status": "ok", "kind": "playlist", "id": link["id"], "url": link["url"],
                "heading": info.get("title") or "Playlist", "channel": info.get("channel") or info.get("uploader") or "",
                "artist": artist, "album": guess_album or ptitle, "tracks": tracks}
    info = json.loads(_ytdlp(["--no-playlist", "-J", link["url"]]))
    duration = info.get("duration") or 0
    raw = info.get("title") or ""
    artist = info.get("artist") or info.get("creator") or ""
    a, rest = split_artist(clean_title(raw))
    artist = (artist.split(",")[0].strip() if artist else "") or a or artist_from_channel(info.get("channel") or info.get("uploader"))
    title = info.get("track") or (rest if a else clean_title(raw))
    album_name = info.get("album") or title
    chapters = [c for c in info.get("chapters") or [] if c.get("title") is not None]
    found = None
    if len(chapters) >= 2:
        found = {"titles": [_strip_number(c["title"]) for c in chapters],
                 "starts": [float(c.get("start_time") or 0) for c in chapters], "lengths": None, "from": "chapters"}
    else:
        found = tracks_from_description(info.get("description"), duration)
    mb = None
    if not found and duration >= ALBUM_MINUTES * 60:
        mb = mb_tracks(artist, album_name)
    return {"status": "ok", "kind": "video", "id": link["id"], "url": link["url"], "heading": raw,
            "channel": info.get("channel") or info.get("uploader") or "", "duration": duration,
            "artist": artist, "title": title, "album": album_name,
            "looks_like_album": bool(found and len(found["titles"]) >= 3) or duration >= ALBUM_MINUTES * 60,
            "tracklist": found, "mb": mb}


def _clear_old_work():
    root = _work_root()
    if not root.exists():
        return
    cutoff = time.time() - WORK_KEEP_DAYS * 86400
    for d in root.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


# --- [ DISPATCH ] ------------------------------------------------------------

def run_logic(action, tools_dir, env_path):
    if action == "inspect":
        url = (request.get_json(silent=True) or {}).get("url", "")
        try:
            return jsonify(inspect(url))
        except subprocess.TimeoutExpired:
            return jsonify({"status": "error", "message": "YouTube took too long to answer. Try again."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    if action == "settings":
        if request.method == "POST":
            s = _load_settings()
            s["folder"] = (request.get_json(silent=True) or {}).get("folder", "")
            _save_settings(s)
        return jsonify({"status": "ok", "folder": _load_settings().get("folder", ""),
                        "running": _run_state()["lock"].locked()})
    if action == "preview":
        vid = request.args.get("id", "")
        src = _source_file(_work_root() / vid) if ID_RE.match(vid) else None
        if not src:
            return jsonify({"status": "error", "message": "Nothing to play."}), 404
        return send_file(src, conditional=True)
    if action == "stop":
        st = _run_state()
        st["stop"].set()
        if st.get("proc"):
            try:
                st["proc"].kill()
            except Exception:
                pass
        return jsonify({"status": "ok"})
    if action == "run":
        data = request.get_json(silent=True) or {}
        fn = RUNS.get(data.get("mode"))
        if not fn or not ID_RE.match(data.get("id") or ""):
            return jsonify({"status": "error", "message": "Look the link up again."}), 400
        if data.get("mode") in ("song", "album_find"):
            link = parse_link(data.get("url", ""))
            if not link or link["kind"] != "video":
                return jsonify({"status": "error", "message": "Look the link up again."}), 400
            data["url"] = link["url"]
        state = _run_state()
        if not state["lock"].acquire(blocking=False):
            return jsonify({"status": "error", "message": "Something is already being downloaded."}), 409
        state["stop"].clear()

        def guarded():
            try:
                yield from fn(data, state)
            except ValueError as e:
                yield event("error", str(e))
                yield signal("refused", message=str(e))
            except Exception as e:
                yield event("error", f"It stopped: {e}")
            finally:
                state["proc"] = None
                state["lock"].release()

        return Response(stream_with_context(run_stream(guarded(), "YouTube to MP3")), mimetype="application/x-ndjson")
    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400
# --- END OF FILE youtube_mp3.py ---
