# ======================================================================
# MetaForge Dev Tool: v2 standard screen header + shared Help (one-off)
# Physical Location: \dev\standardize_headers.py
# ======================================================================
"""
Phase 0.2 (2026-11-13). For every tool screen:
  1. Replace the header (h1 + description block) with the v2 standard header:
     the tool's <h1> (same id) and the shared Help button.
     (Header prose was already moved to help.mfi by dev/move_header_prose.py;
     this script refuses to drop any header prose that wasn't moved.)
  2. Remove the tool's own help panel markup (now one shared <dialog>).
  3. Remove the tool's own openHelp/closeHelp/trapFocus code.
  4. Make toolbar names match screen titles (WCAG 3.2.4).

  python dev\\standardize_headers.py           (dry run)
  python dev\\standardize_headers.py --apply
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
APPLY = "--apply" in sys.argv

# Final, agreed titles (John, 2026-11-13). Toolbar names are set to match.
TITLES = {
    "acoustid": "AcoustID Manager", "biography": "Bio Builder", "dashboard": "Dashboard",
    "database_tools": "Database Tools", "intelli-tagger": "Intelli-Tagger",
    "music-sharing": "Music Sharing", "musicbrainz_id": "MusicBrainz IDs",
    "musicbrainz_submit": "MusicBrainz Submit", "personnel": "Album Personnel",
    "playlist_generator": "Intelligent Playlist Maker", "repair": "Audio Repair",
    "settings": "Settings", "unpack_convert": "Unpack & Convert", "youtube_mp3": "YouTube to MP3",
}
MOVED = {"acoustid", "biography", "intelli-tagger", "music-sharing", "musicbrainz_id",
         "musicbrainz_submit", "personnel", "repair"}
PLACEHOLDER = {"", "&nbsp;", "Tool Notes go here"}


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def balanced_end(text, start, open_pat, close_pat):
    """Index just past the element/block opened at `start`, counting nesting."""
    depth, pos = 0, start
    token = re.compile(f"({open_pat})|({close_pat})")
    for m in token.finditer(text, start):
        depth += 1 if m.group(1) else -1
        if depth == 0:
            return m.end()
    raise ValueError("unbalanced block")


def header_block(text):
    """(start, end, h1_id) of the h1 plus its description section/paragraph."""
    h1 = re.search(r'<h1\b([^>]*)>(.*?)</h1>', text, re.S)
    if not h1:
        return None
    idm = re.search(r'\bid="([^"]+)"', h1.group(1))
    end = h1.end()
    after = re.match(r'\s*', text[end:]).end() + end
    sec = re.match(r'<section\b[^>]*class="[^"]*-description"', text[after:])
    para = re.match(r'<p\b[^>]*class="[^"]*tool_notes[^"]*"[^>]*>(.*?)</p>', text[after:], re.S)
    if sec:
        end = balanced_end(text, after, r"<section\b", r"</section>")
    elif para:
        end = after + para.end()
    return h1.start(), end, (idm.group(1) if idm else None)


def leftover_prose(block_html):
    """Visible or commented prose in the old header block (tool_notes text)."""
    m = re.search(r'<p\b[^>]*tool_notes[^>]*>(.*?)</p>', block_html, re.S)
    if not m:
        return ""
    txt = re.sub(r"<!--|-->", "", m.group(1))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", txt)).strip()


def remove_help_panel(text):
    m = re.search(r'<div\b[^>]*class="mf-help-panel"[^>]*>', text, re.S)
    if not m:
        return text, False
    start = text.rfind("\n", 0, m.start()) + 1
    end = balanced_end(text, m.start(), r"<div\b", r"</div>")
    return text[:start] + text[end:].lstrip("\n"), True


def remove_js_members(text, names):
    """Remove object-literal methods `name: [async] function (...) {...},`."""
    removed = []
    for name in names:
        pat = re.compile(r'\n([ \t]*)' + name + r'\s*:\s*(?:async\s+)?function\s*\([^)]*\)\s*\{')
        m = pat.search(text)
        if not m:
            continue
        brace = text.index("{", m.end() - 1)
        end = balanced_end(text, brace, r"\{", r"\}")
        tail = re.match(r'[ \t]*,?', text[end:]).end()
        text = text[:m.start()] + text[end + tail:]
        removed.append(name)
    return text, removed


def remove_js_statements(text, patterns):
    """Remove `<lhs> = [async] function(...) {...};` and `<lhs> = {...};` statements."""
    removed = []
    for lhs in patterns:
        m = re.search(r'\n' + re.escape(lhs) + r'\s*=\s*(?:async\s+)?(?:function\s*\([^)]*\)\s*)?\{', text)
        if not m:
            continue
        brace = text.index("{", m.end() - 1)
        end = balanced_end(text, brace, r"\{", r"\}")
        tail = re.match(r'[ \t]*;?', text[end:]).end()
        text = text[:m.start()] + text[end + tail:]
        removed.append(lhs)
    return text, removed


report = []
for tool_id, title in TITLES.items():
    tdir = TOOLS / tool_id
    mfi = tdir / f"{tool_id}.mfi"
    t = mfi.read_text(encoding="utf-8")
    hb = header_block(t)
    if not hb:
        report.append(f"{tool_id}: NO <h1> FOUND, skipped"); continue
    start, end, h1_id = hb
    old = t[start:end]
    prose = leftover_prose(old)
    if prose and prose not in PLACEHOLDER and tool_id not in MOVED:
        raise SystemExit(f"STOP: {tool_id} header has prose that was never moved: {prose[:80]}")
    id_attr = f' id="{h1_id}"' if h1_id else ""
    new = (f'<div class="mf-page-head">\n'
           f'    <h1{id_attr} class="main" tabindex="-1">{html_escape(title)}</h1>\n'
           f'    <button type="button" class="mf-help-btn" data-mf-help="{tool_id}" '
           f'data-mf-help-name="{html_escape(title)}">Help</button>\n'
           f'</div>')
    t = t[:start] + new + t[end:]
    t, panel = remove_help_panel(t)
    changes = [f"header ({len(old)} chars -> standard)"] + (["help panel removed"] if panel else [])

    js = tdir / f"{tool_id}.js"
    js_text = js.read_text(encoding="utf-8") if js.exists() else None
    if js_text is not None:
        js_new, gone = remove_js_members(js_text, ["openHelp", "closeHelp", "trapFocus"])
        js_new, gone2 = remove_js_statements(js_new, [
            "window.metaforge.database_tools.openHelp", "window.metaforge.database_tools.closeHelp",
            "window.metaforge.database"])
        if gone or gone2:
            changes.append("js removed: " + ", ".join(gone + [g.split('.')[-1] for g in gone2]))
    man = tdir / "manifest.json"
    m = json.loads(man.read_text(encoding="utf-8"))
    if m.get("name") != title:
        changes.append(f"toolbar name '{m.get('name')}' -> '{title}'")
    report.append(f"{tool_id}: " + "; ".join(changes))

    if APPLY:
        mfi.write_text(t, encoding="utf-8")
        if js_text is not None and js_new != js_text:
            js.write_text(js_new, encoding="utf-8")
        if m.get("name") != title:
            raw = man.read_text(encoding="utf-8")
            man.write_text(raw.replace(f'"name": "{m["name"]}"', f'"name": "{title}"', 1)
                           if f'"name": "{m["name"]}"' in raw
                           else json.dumps({**m, "name": title}, indent=4), encoding="utf-8")

print(("APPLIED" if APPLY else "DRY RUN") + "\n" + "\n".join(report))
