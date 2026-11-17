# --- START OF FILE logo_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Theme logo (PNG)
# Physical Location: \tools\settings\engines\logo_engine.py
# v2 (2026-11-17, theme folders): makes a theme's 3-D logo as a PNG from
# one master, ui/images/logo_master.png: John's silver logo (option B),
# rendered once from logo_silver.svg. Every pixel of the master is a pure
# grey with the letter faces at #CCCCCC, so a pixel's grey says only how
# light or dark it is. Recolouring keeps that, relative to the faces:
# the faces become exactly the theme's logo colour (#CC9900 for the default
# theme), darker edges keep the same fraction of the face's lightness, and
# brighter highlights the same fraction of the way to white. Transparency
# is untouched. Replaces the SVG version, which repainted 254 traced shapes
# and was too hard to keep 3-D in every colour (John).
# A theme's own hand-made logo.png is never generated or replaced here.
# ======================================================================
import colorsys
import io
import re

from PIL import Image

from common import config_handler

MASTER = config_handler.PROJECT_ROOT / "ui" / "images" / "logo_master.png"
FACE_L = 0xCC / 255              # the master's flat letter faces (#CCCCCC)
HEIGHT = 192                     # saved height: 6x the header's 32px, sharp at 150% scaling and zoom
HEX = re.compile(r"^#[0-9a-f]{6}$")
_cache = {}


def _master():
    """The master, scaled once to the saved height (grey + transparency)."""
    if "img" not in _cache:
        im = Image.open(MASTER).convert("RGBA")
        im = im.resize((round(im.width * HEIGHT / im.height), HEIGHT), Image.LANCZOS)
        _cache["img"] = im
    return _cache["img"]


def _table(colour):
    """256-step lookup: master grey -> (r, g, b) lists in the new colour."""
    th, tl, ts = colorsys.rgb_to_hls(*(int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    r, g, b = [], [], []
    for v in range(256):
        l = v / 255
        nl = l / FACE_L * tl if l <= FACE_L else tl + (l - FACE_L) / (1 - FACE_L) * (1 - tl)
        rgb = colorsys.hls_to_rgb(th, max(0.0, min(1.0, nl)), ts)
        for chan, c in zip((r, g, b), rgb):
            chan.append(round(c * 255))
    return r, g, b


def make(colour):
    """The logo in `colour` (#rrggbb) as PNG bytes."""
    colour = colour.lower()
    if not HEX.match(colour):
        raise ValueError(f"not a colour code: {colour}")
    im = _master()
    grey = im.getchannel("R")            # the master is pure grey: R = G = B
    tr, tg, tb = _table(colour)
    out = Image.merge("RGBA", (grey.point(tr), grey.point(tg), grey.point(tb), im.getchannel("A")))
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def cached(colour):
    """A generated logo kept in AppData (for a theme folder without its own
    logo.png): made once per colour, so the program folder is never written."""
    colour = colour.lower()
    folder = config_handler.APPDATA_MF / "logo_cache"
    path = folder / f"logo_{colour[1:]}.png"
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(make(colour))
        tmp.replace(path)
    return path

# --- END OF FILE logo_engine.py ---
