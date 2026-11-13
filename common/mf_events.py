# ======================================================================
# MetaForge Common: Event stream (v2, 2026-11-13)
# Physical Location: \common\mf_events.py
# ======================================================================
"""
One stream of events per run; two outputs from it.

Engines report what happened as EVENTS instead of building HTML:

    from common.mf_events import event, signal
    yield event("success", "Archive deleted after a verified extraction", file=zip_path.name)
    yield signal("progress", phase=1, current=3, total=18)

run_stream() wraps a tool's generator and turns every item into:
  1. one complete JSON line for the screen (NDJSON). The shared renderer in
     ui/js/metaforge_core.js (MFEvents) draws it, escaped and themed. A line
     is always complete, so an HTML tag can never be split across network
     reads (the 1.x "split-tag" bug).
  2. one plain, timestamped line appended to the album's MetaForge.log, so
     the human-readable log records everything the screen shows (John's
     original intent: manifest.json is for the tool, MetaForge.log is for
     people). Progress ticks and other signals are not logged.

Migration: engines that still yield 1.x HTML strings keep working. Each
legacy HTML chunk is passed through as an "html" event (drawn as before)
and its TEXT is written to MetaForge.log, and legacy marker comments
(<!-- PROGRESS:a:b:c -->, <!-- ART_READY -->, ...) become signals. So the
log is complete for a whole tool immediately, and engines are converted
one at a time with nothing breaking in between.

Event kinds: step, info, detail, success, warning, error, done, track.
  track: one entry per file (John, 2026-11-13: per-track lines must be
  easy to tell apart). `file` is the headline, `text` says everything
  that was done to it, e.g.
      event("track", "Converted to MP3 (V0), metadata cleaned (track 1)", file=name)
"""
import html as _html
import json
import re
from datetime import datetime
from pathlib import Path

KINDS = {"step", "info", "detail", "success", "warning", "error", "done", "track"}

# Plain-text prefixes for MetaForge.log (ASCII, so the log reads cleanly in
# any editor). Steps stand out; outcomes are tagged; details are indented.
_LOG_PREFIX = {
    "step":    "",
    "info":    "  ",
    "detail":  "    ",
    "success": "  [ok] ",
    "warning": "  [!]  ",
    "error":   "  [X]  ",
    "done":    "DONE: ",
    "track":   "  [ok] ",
    "html":    "  ",
}


def _now():
    return datetime.now().strftime("%H:%M:%S")


def event(kind, text, file=None, **extra):
    """A screen + log event. `file` is shown in the mono face after the text."""
    if kind not in KINDS:
        raise ValueError(f"unknown event kind: {kind}")
    ev = {"mf": 1, "kind": kind, "text": str(text)}
    if file:
        ev["file"] = str(file)
    ev.update(extra)
    return ev


def signal(name, **data):
    """A control signal for the screen only (progress, art_ready, handoff_ready...). Not logged."""
    return {"mf": 1, "kind": "signal", "name": name, "data": data}


# --- legacy (1.x HTML) handling -------------------------------------------
_COMMENT = re.compile(r"<!--\s*(.*?)\s*-->", re.S)
_PROGRESS = re.compile(r"^PROGRESS:(\d+):(\d+):(\d+)$")
_HIDDEN = re.compile(r'<span[^>]*aria-hidden="true"[^>]*>.*?</span>', re.S | re.I)


def _legacy_signal(comment):
    m = _PROGRESS.match(comment)
    if m:
        return signal("progress", phase=int(m.group(1)), current=int(m.group(2)), total=int(m.group(3)))
    name, _, value = comment.partition(":")
    if re.fullmatch(r"[A-Z_]+", name):
        return signal(name.lower(), value=value) if value else signal(name.lower())
    return None


def html_to_text(fragment):
    """Readable text from a 1.x HTML log fragment (decorative icons dropped)."""
    t = _HIDDEN.sub("", fragment)
    t = re.sub(r"<img[^>]*>", "", t, flags=re.I)
    t = re.sub(r"<br\s*/?>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


# --- the log writer ---------------------------------------------------------
class _LogWriter:
    def __init__(self, root, tool):
        self.path = Path(root) / "MetaForge.log"
        self.tool = tool
        self.f = None
        try:
            if Path(root).is_dir():
                self.f = open(self.path, "a", encoding="utf-8")
                started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.f.write(f"\n{'=' * 60}\nMetaForge Studio v2 | {tool} | {started}\n{'-' * 60}\n")
                self.f.flush()
        except OSError:
            self.f = None   # logging must never break the run itself

    def line(self, kind, text, file=None, time=None):
        if not self.f or not text:
            return
        body = f"{text} ({file})" if file else text
        if kind == "track" and file:
            body = f"{file}: {text}"      # file first, as on screen
        if kind == "step":
            body = f"== {body}"
        self.f.write(f"{time or _now()}  {_LOG_PREFIX.get(kind, '  ')}{body}\n")
        self.f.flush()   # line by line, so the log survives a crash

    def close(self, finished):
        if not self.f:
            return
        end = "Finished" if finished else "Run ended before finishing (stopped or failed)"
        self.f.write(f"{'-' * 60}\n{end} at {_now()}\n{'=' * 60}\n")
        self.f.close()
        self.f = None


def run_stream(source, tool, log_root=None):
    """
    Wrap a tool's generator. Yields NDJSON lines for the screen and writes
    MetaForge.log in log_root (if given and it exists).
    """
    log = _LogWriter(log_root, tool) if log_root else None
    finished = False
    try:
        for item in source:
            for ev in _normalise(item):
                if ev["kind"] != "signal":
                    ev.setdefault("time", _now())
                    if log:
                        text = ev["text"] if ev["kind"] != "html" else html_to_text(ev["html"])
                        log.line(ev["kind"], text, ev.get("file"), ev["time"])
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        finished = True
    finally:
        if log:
            log.close(finished)


def _normalise(item):
    """Native events pass through; legacy strings become signals and/or html events."""
    if isinstance(item, dict):
        yield item
        return
    if not isinstance(item, str) or not item.strip():
        return
    for comment in _COMMENT.findall(item):
        sig = _legacy_signal(comment)
        if sig:
            yield sig
    remainder = _COMMENT.sub("", item).strip()
    if remainder:
        yield {"mf": 1, "kind": "html", "html": remainder}
