# --- START OF FILE acoustid.py ---
# ======================================================================
# MetaForge Tool Logic: AcoustID Manager
# v2 (2026-11-16): rebuilt.
#   Step 1 submits fingerprints AcoustID doesn't know yet and KEEPS the
#   submission number AcoustID returns. Step 2 asks AcoustID for the status
#   of those submissions (no re-fingerprinting); tracks submitted before v2
#   have no number and fall back to a fresh lookup.
#   A found AcoustID goes to the standard "Acoustid Id" tag (the same frame
#   the Intelli-Tagger writes) and tracks.acoustid, but only for tracks the
#   database knows; other files are left alone (John, 2026-11-16) and the
#   Intelli-Tagger finds the ID itself when that album is processed.
#   Queue files are updated after every track, so stopping or a crash
#   never loses work, and always end with a newline (1.x left it off and
#   the next appended path was glued onto the last line).
# Files (data/acoustid, shared with 1.x through the junction, so the two
# .txt formats are unchanged: one path per line):
#   pending_acoustid.txt    waiting to be submitted (Intelli-Tagger adds)
#   submission_history.txt  submitted, waiting for an AcoustID
#   submission_ids.json     {path: AcoustID submission id} (v2 only)
#   not_found.txt           paths that no longer exist on disk
# ======================================================================
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Response, current_app, jsonify, request, stream_with_context

from common import config_handler, db_engine, tag_engine
from common.mf_events import event, signal, run_stream
from common.version import APP_VERSION

API = "https://api.acoustid.org/v2/"
REQUEST_GAP = 0.4            # AcoustID asks for no more than 3 requests a second
MAX_RATE_LIMIT_RETRIES = 5
STATUS_BATCH = 20            # submission ids per status request
LOOKUP_MIN_SCORE = 0.9       # legacy lookups: only a near-certain match counts

http = requests.Session()    # replaced by a stub in tests


# --- [ QUEUE FILES ] -------------------------------------------------------

def _dir():
    return Path(config_handler.DATA_DIR) / "acoustid"


def _file(name):
    return _dir() / {
        "pending": "pending_acoustid.txt",
        "history": "submission_history.txt",
        "ids": "submission_ids.json",
        "not_found": "not_found.txt",
        "not_found_cleared": "not_found_cleared.txt",
    }[name]


_JOINED = re.compile(r"(?<!^)(?=[A-Za-z]:[\\/])")   # a drive letter mid-line = two paths glued together


def normalise(lines):
    """Split glued-together paths, trim, drop blanks and duplicates (keeps the first, in order)."""
    out, seen = [], set()
    for line in lines:
        for part in _JOINED.split(line.strip()):
            p = part.strip()
            key = os.path.normcase(p)
            if p and key not in seen:
                seen.add(key)
                out.append(p)
    return out


def read_list(name):
    f = _file(name)
    if not f.exists():
        return []
    return normalise(f.read_text(encoding="utf-8").splitlines())


def _write_text(f, text):
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(f.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, f)


def write_list(name, paths):
    _write_text(_file(name), "".join(p + "\n" for p in paths))


def _remove(name, path):
    """Re-read, drop one path, write back: keeps anything another tool appended meanwhile."""
    key = os.path.normcase(path)
    write_list(name, [p for p in read_list(name) if os.path.normcase(p) != key])


def _add(name, path):
    items = read_list(name)
    if os.path.normcase(path) not in {os.path.normcase(p) for p in items}:
        write_list(name, items + [path])


def read_ids():
    f = _file("ids")
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def _set_id(path, sub_id):
    ids = read_ids()
    if sub_id is None:
        ids.pop(path, None)
    else:
        ids[path] = sub_id
    _write_text(_file("ids"), json.dumps(ids, indent=1, ensure_ascii=False))


# --- [ DISPATCH ] -----------------------------------------------------------

def _run_state():
    """Survives the per-request module reload (ui/routes.py re-executes this file each call)."""
    return current_app.extensions.setdefault("acoustid_run", {"lock": threading.Lock(), "stop": threading.Event()})


def run_logic(action, tools_dir, env_path):
    if action == "status":
        return jsonify(status())
    if action == "stop":
        _run_state()["stop"].set()
        return jsonify({"status": "ok"})
    if action == "clear_not_found":
        if _run_state()["lock"].locked():
            return jsonify({"status": "error", "message": "Wait for the run to finish, then clear the list."}), 409
        return jsonify(clear_not_found())
    if action in ("submit", "resolve"):
        state = _run_state()
        if not state["lock"].acquire(blocking=False):
            return jsonify({"status": "error", "message": "A run is already going."}), 409
        state["stop"].clear()
        work = submit_stream if action == "submit" else resolve_stream

        def guarded():
            try:
                yield from work(state["stop"])
            finally:
                state["lock"].release()

        return Response(stream_with_context(run_stream(guarded(), "AcoustID Manager")),
                        mimetype="application/x-ndjson")
    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400


def status():
    """Counts for the screen."""
    return {
        "status": "ok",
        "pending": len(read_list("pending")),
        "submitted": len(read_list("history")),
        "not_found": len(read_list("not_found")),
        "not_found_paths": read_list("not_found")[:500],
        "has_app_key": bool(config_handler.ACOUSTID_APPLICATION_KEY()),
        "has_user_key": bool(config_handler.ACOUSTID_USER_KEY()),
    }


def clear_not_found():
    """Clear this list (John, 2026-11-17): the set-aside files are a record,
    not work to do, and the note about them never went away. Nothing is
    thrown away: the cleared paths are added, with the date, to
    not_found_cleared.txt. Only the paths read here are removed, so one
    set aside meanwhile stays on the list."""
    paths = read_list("not_found")
    if paths:
        f = _file("not_found_cleared")
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"# Cleared {datetime.now().isoformat(timespec='seconds')}\n")
            fh.writelines(p + "\n" for p in paths)
        gone = {os.path.normcase(p) for p in paths}
        write_list("not_found", [p for p in read_list("not_found") if os.path.normcase(p) not in gone])
    return {"status": "ok", "cleared": len(paths)}


# --- [ HELPERS ] ------------------------------------------------------------

def _fingerprint(path):
    result = subprocess.run([str(config_handler.FPCALC_EXE), "-json", str(path)],
                            capture_output=True, text=True, timeout=180)
    data = json.loads(result.stdout or "{}")
    fp, duration = data.get("fingerprint"), data.get("duration")
    if not fp or duration is None:
        raise ValueError("fpcalc couldn't read the audio")
    return fp, int(round(float(duration)))


def _call(method, endpoint, stop, **kw):
    """One API call, with backoff on 429. Yields waiting events; returns the JSON (or None if stopped)."""
    delay = 2
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        r = http.request(method, API + endpoint, timeout=20, **kw)
        time.sleep(REQUEST_GAP)
        if r.status_code != 429:
            return r.json()
        if attempt == MAX_RATE_LIMIT_RETRIES:
            break
        ra = r.headers.get("Retry-After", "")
        wait = float(ra) if ra.replace(".", "", 1).isdigit() else delay
        yield event("info", f"AcoustID is busy. Waiting {wait:.0f} seconds, then trying again.")
        if stop.wait(wait):
            return None
        delay = min(delay * 2, 60)
    raise RuntimeError("AcoustID was still busy after several tries")


def _db_track(path):
    """The database row for a file, matched regardless of upper/lower case and slash direction."""
    rows = db_engine.execute_query(
        "SELECT t.file_path, t.title, t.acoustid, t.mb_recording_id, "
        "       lm.artist_name, lm.album_title, lm.original_year AS release_year "
        "FROM tracks t LEFT JOIN library_master lm ON t.mf_id = lm.mf_id "
        "WHERE lower(replace(t.file_path, '\\', '/')) = lower(?)",
        (str(path).replace("\\", "/"),))
    return rows[0] if rows else None


def _blank(v):
    return v in (None, "", "None")


def _progress(i, total, label):
    return signal("progress", percent=round(100 * i / total) if total else 100, label=label)


def _stopped(name):
    left = len(read_list(name))
    return event("warning", f"Stopped. {left} track{'s' if left != 1 else ''} still waiting; nothing was lost.")


def _not_found(name, path):
    _remove(name, path)
    _set_id(path, None)
    _add("not_found", path)
    return event("warning", "File not found. Moved to the not-found list.", file=path)


# --- [ STEP 1: SUBMIT ] -----------------------------------------------------

def submit_stream(stop):
    app_key, user_key = config_handler.ACOUSTID_APPLICATION_KEY(), config_handler.ACOUSTID_USER_KEY()
    missing = [n for n, v in (("application key", app_key), ("user key", user_key)) if not v]
    if missing:
        yield event("error", f"The AcoustID {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing. "
                             "Add them in Settings > Configuration & keys.")
        return
    paths = read_list("pending")
    total = len(paths)
    if not total:
        yield event("done", "Nothing is waiting to be submitted.")
        return
    yield event("step", f"Submitting {total} track{'s' if total != 1 else ''} to AcoustID")
    sent = kept = 0
    for i, path in enumerate(paths, 1):
        if stop.is_set():
            break
        yield _progress(i - 1, total, f"Submitting {i} of {total}")
        name = Path(path).name
        if not Path(path).exists():
            yield _not_found("pending", path)
            continue
        try:
            fp, duration = _fingerprint(path)
            meta = _db_track(path) or {}
            data = {"client": app_key, "user": user_key, "clientversion": APP_VERSION, "format": "json",
                    "duration.0": duration, "fingerprint.0": fp}
            for field, key in (("track.0", "title"), ("artist.0", "artist_name"), ("album.0", "album_title"),
                               ("year.0", "release_year"), ("mbid.0", "mb_recording_id")):
                if not _blank(meta.get(key)):
                    data[field] = meta[key]
            res = yield from _call("POST", "submit", stop, data=data)
            if res is None:
                continue                      # stopped while waiting; the loop reports it
            if res.get("status") != "ok":
                err = res.get("error") or {}
                yield event("warning", f"AcoustID refused it: {err.get('message', 'no reason given')}. It stays in the list.", file=name)
                kept += 1
                continue
            sub = (res.get("submissions") or [{}])[0]
            _add("history", path)
            if sub.get("id") is not None:
                _set_id(path, sub["id"])
            _remove("pending", path)
            sent += 1
            yield event("track", "Submitted. Check for AcoustIDs later to collect its ID.", file=name)
        except Exception as e:  # one bad file never stops the run
            kept += 1
            yield event("warning", f"Not submitted ({e}). It stays in the list.", file=name)
    if stop.is_set():
        yield _stopped("pending")
    yield _progress(1, 1, "Stopped" if stop.is_set() else "Finished")
    yield event("done", f"Submitted {sent} of {total}." + (f" {kept} stay in the list to try again." if kept else ""))


# --- [ STEP 2: COLLECT ACOUSTIDS ] -----------------------------------------

def _record(path, aid):
    """Store a found AcoustID. Returns (kind, text) for the track's entry."""
    row = _db_track(path)
    if row is None:
        return "track", f"AcoustID {aid}. Not in the database yet, so the file was left alone; the Intelli-Tagger will add it."
    if not _blank(row["acoustid"]) and row["acoustid"] != aid:
        return "warning", f"AcoustID {aid} found, but the database already has {row['acoustid']}. Left as it is."
    if row["acoustid"] == aid:
        return "track", f"AcoustID {aid}. Already in the database."
    ok, msg = tag_engine.update_tags(str(path), {"acoustid": aid})
    if not ok:
        raise RuntimeError(f"the tag couldn't be written: {msg}")
    db_engine.execute_query("UPDATE tracks SET acoustid = ? WHERE file_path = ?", (aid, row["file_path"]), commit=True)
    return "track", f"AcoustID {aid}. Tag and database updated."


def _done(path, kind, text):
    _remove("history", path)
    _set_id(path, None)
    return event(kind, text, file=Path(path).name)


def resolve_stream(stop):
    app_key = config_handler.ACOUSTID_APPLICATION_KEY()
    if not app_key:
        yield event("error", "The AcoustID application key is missing. Add it in Settings > Configuration & keys.")
        return
    paths = read_list("history")
    total = len(paths)
    if not total:
        yield event("done", "No submitted tracks are waiting for an AcoustID.")
        return
    ids = read_ids()
    with_id = [p for p in paths if p in ids]
    without = [p for p in paths if p not in ids]
    yield event("step", f"Checking {total} submitted track{'s' if total != 1 else ''} for AcoustIDs")
    found = waiting = 0
    done_n = 0

    # 1) Submissions with a number: ask for their status, many per request.
    for b in range(0, len(with_id), STATUS_BATCH):
        if stop.is_set():
            break
        batch = with_id[b:b + STATUS_BATCH]
        yield _progress(done_n, total, f"Checking {done_n + 1} of {total}")
        try:
            res = yield from _call("GET", "submission_status", stop,
                                   params=[("client", app_key), ("format", "json")] + [("id", ids[p]) for p in batch])
        except Exception as e:
            yield event("warning", f"AcoustID couldn't be reached ({e}). These stay in the list.")
            done_n += len(batch); waiting += len(batch)
            continue
        if res is None:
            break
        by_id = {str(s.get("id")): s for s in res.get("submissions") or []}
        for p in batch:
            done_n += 1
            s = by_id.get(str(ids[p])) or {}
            aid = (s.get("result") or {}).get("id")
            if not Path(p).exists():
                yield _not_found("history", p)
            elif s.get("status") == "imported" and aid:
                try:
                    kind, text = _record(p, aid)
                    yield _done(p, kind, text)
                    found += 1
                except Exception as e:
                    waiting += 1
                    yield event("warning", f"AcoustID {aid} found, but {e}. It stays in the list.", file=Path(p).name)
            else:
                waiting += 1

    # 2) Older submissions (before v2) have no number: fingerprint and look up.
    for p in without:
        if stop.is_set():
            break
        done_n += 1
        yield _progress(done_n - 1, total, f"Checking {done_n} of {total}")
        if not Path(p).exists():
            yield _not_found("history", p)
            continue
        try:
            fp, duration = _fingerprint(p)
            res = yield from _call("POST", "lookup", stop,
                                   data={"client": app_key, "format": "json", "duration": duration, "fingerprint": fp})
            if res is None:
                break
            best = max(res.get("results") or [], key=lambda r: r.get("score", 0), default=None)
            if best and best.get("score", 0) >= LOOKUP_MIN_SCORE and best.get("id"):
                kind, text = _record(p, best["id"])
                yield _done(p, kind, text)
                found += 1
            else:
                waiting += 1
        except Exception as e:
            waiting += 1
            yield event("warning", f"Couldn't check it ({e}). It stays in the list.", file=Path(p).name)

    if stop.is_set():
        yield _stopped("history")
    yield _progress(1, 1, "Stopped" if stop.is_set() else "Finished")
    yield event("done", f"Found {found} AcoustID{'s' if found != 1 else ''}."
                        + (f" {waiting} {'are' if waiting != 1 else 'is'} still being processed by AcoustID; check again later." if waiting else ""))

# --- END OF FILE acoustid.py ---
