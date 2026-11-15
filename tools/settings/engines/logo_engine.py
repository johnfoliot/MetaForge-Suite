# --- START OF FILE logo_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Theme logo
# Physical Location: \tools\settings\engines\logo_engine.py
# v2 (2026-11-15). Makes a theme's logo from the 3-D logo (ui/images/
# logo.svg: 254 traced shapes in shades of #CC9900). Replaces
# ui/images/logo_converter.py, which painted every shape one flat colour
# and lost the bevels. Two styles (John):
#  - "full":  the whole logo in the new colour. Each shape keeps its place
#             in the light-to-dark range, so the 3-D bevels survive.
#  - "faces": the letter faces and "Studio" in the new colour; the gold
#             bevels stay as edges. (John 2026-11-15: "Studio" changes colour
#             too. The built-in Festive logo, with a gold "Studio", is its
#             own file and isn't affected.)
# ======================================================================
import colorsys
import re

from common import config_handler

SOURCE = config_handler.PROJECT_ROOT / "ui" / "images" / "logo.svg"
FACE = "#cc9900"                 # the flat letter faces in logo.svg
FACE_L = 0.40                    # its lightness (HLS)
PATH = re.compile(r'<path fill="(#[0-9A-Fa-f]{6})"([^>]*?)d="([^"]*)"')
_cache = {}


def _source():
    if "svg" not in _cache:
        _cache["svg"] = SOURCE.read_text(encoding="utf-8")
    return _cache["svg"]


def _hls(h):
    return colorsys.rgb_to_hls(*(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)))


def _hex(h, l, s):
    return "#" + "".join(f"{round(c * 255):02x}" for c in colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s))))


def make(style, colour):
    colour = colour.lower()
    th, tl, ts = _hls(colour)
    memo = {}

    def shade(src):
        """Map a gold shade to the same place in the new colour's range."""
        if src not in memo:
            _, l, s = _hls(src)
            nl = l * tl / FACE_L if l <= FACE_L else tl + (l - FACE_L) * (1 - tl) / (1 - FACE_L)
            memo[src] = _hex(th, nl, s * ts)
        return memo[src]

    def swap(m):
        fill, mid, d = m.group(1).lower(), m.group(2), m.group(3)
        if style == "full":
            new = colour if fill == FACE else shade(fill)
        else:
            new = colour if fill == FACE else fill
        return f'<path fill="{new}"{mid}d="{d}"'

    svg = PATH.sub(swap, _source())
    note = f"<!-- MetaForge Studio 3-D logo, style {style}, colour {colour} (Settings > Theme > Create a theme) -->\n"
    return note + svg

# --- END OF FILE logo_engine.py ---
