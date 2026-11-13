# ======================================================================
# MetaForge Dev Tool: move screen-header prose into help.mfi (v2, one-off)
# Physical Location: \dev\move_header_prose.py
# ======================================================================
"""
v2 standard header = tool title + Help button only (John, 2026-11-13).
Any descriptive prose in a tool's screen header moves, word for word, to
the TOP of that tool's help.mfi so none of it is lost (prose review later).
This script only COPIES the prose into help.mfi; the header markup itself is
replaced separately when each tool gets the shared header.

  python dev\\move_header_prose.py          (dry run: prints what would move)
  python dev\\move_header_prose.py --apply  (writes the help.mfi files)
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ["acoustid", "biography", "intelli-tagger", "music-sharing",
         "musicbrainz_id", "musicbrainz_submit", "personnel", "repair"]
MARK = "v2-moved-header-prose"

def header_prose(mfi_text):
    """First tool_notes paragraph after the <h1>: (inner_html, was_hidden)."""
    h1 = re.search(r"<h1[^>]*>.*?</h1>", mfi_text, re.S)
    rest = mfi_text[h1.end():] if h1 else mfi_text
    m = re.search(r'<p[^>]*class="[^"]*tool_notes[^"]*"[^>]*>(.*?)</p>', rest, re.S)
    if not m:
        return None, False
    inner = m.group(1).strip()
    hidden = inner.startswith("<!--") and inner.endswith("-->")
    if hidden:
        inner = inner[4:-3].strip()
    inner = re.sub(r"[ \t]*\n[ \t]*", " ", inner).strip()   # source line-wraps only
    return inner, hidden

def block(inner, hidden):
    note = (" In 1.x this text was commented out of the screen (hidden), but it is kept here so nothing is lost."
            if hidden else "")
    return (f"<!-- {MARK}: moved word for word from this tool's screen header on 2026-11-13 "
            f"(v2 headers show only the title and Help). Prose review pending.{note} -->\n"
            f"<h3 class=\"help first\">What this tool does</h3>\n"
            f"<p class=\"help\">{inner}</p>\n")

apply = "--apply" in sys.argv
for tool in TOOLS:
    tdir = ROOT / "tools" / tool
    mfi = tdir / f"{tool}.mfi"
    helpf = tdir / "help.mfi"
    inner, hidden = header_prose(mfi.read_text(encoding="utf-8"))
    print(f"=== {tool}{'  [was hidden]' if hidden else ''}\n{inner}\n")
    if not apply or inner is None:
        continue
    h = helpf.read_text(encoding="utf-8")
    if MARK in h:
        print("   (already moved, skipped)")
        continue
    silo = re.search(r'<div class="help-content-silo">\s*', h)
    if silo:                       # keep it inside the styled silo when the file has one
        pos = silo.end()
    else:                          # otherwise after any leading file-banner comments
        lead = re.match(r"(\s*<!--.*?-->\s*)*", h, re.S)
        pos = lead.end()
    helpf.write_text(h[:pos] + block(inner, hidden) + "\n" + h[pos:], encoding="utf-8")
    print("   -> written to help.mfi")
