# --- START OF FILE theme_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Themes
# Physical Location: \tools\settings\engines\theme_engine.py
# v2 (2026-11-17, John): a theme is a FOLDER, found the way tools are:
#   <themes>/<id>/manifest.json   name, id, version, description, logo_colour
#   <themes>/<id>/theme.css       the 17 colours, one :root block, nothing else
#   <themes>/<id>/logo.png        optional: a hand-made logo always wins
#   manifest "header_image"       optional, rare (Festive, 2026-11-17): a
#                                 picture in the folder behind the top bar.
#                                 MetaForge adds that rule itself, so a
#                                 theme's own CSS stays colours only.
# Built-in themes: ui/themes/. Themes you make (Create a theme): AppData\
# MetaForge\themes\ (they survive updates; one can be shared by copying its
# folder). A built-in id always wins over one of yours.
# Every theme is checked before it's offered (manifest, the 17 colours,
# colours only - no @import / url() / other rules - and the theme
# template's contrast and one-gold checks). One that fails isn't offered;
# Settings lists it with the reason, so whoever made it knows what to fix.
# ======================================================================
import json
import re
import shutil
import time

from flask import jsonify, request, Response

from common import config_handler
import theme_template as T
import logo_engine

BUILTIN_DIR = config_handler.PROJECT_ROOT / "ui" / "themes"
DEFAULT_ID = "default"
THEME_ID = re.compile(r"^[a-z0-9_]{1,60}$")
# Colours only: inside :root, each declaration is color-scheme or a custom
# property set to a colour code or another custom property.
DECL = re.compile(r"^(color-scheme\s*:\s*(light|dark)|--[a-z0-9-]+\s*:\s*(#[0-9a-f]{6}|var\(--[a-z0-9-]+\)))$")
HEADER_IMAGE = re.compile(r"^[\w-]+\.(png|jpe?g|webp)$", re.I)
HEADER_MAX = 5 * 1024 * 1024
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


def custom_dir():
    return config_handler.APPDATA_MF / "themes"          # read at call time (sandbox-safe)


def _first(problems):
    more = len(problems) - 1
    return problems[0] + (f" (and {more} more)" if more else "")


def check(folder, custom):
    """(theme, None) if the folder is a usable theme, else (None, reason)."""
    try:
        man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "It has no manifest.json."
    except (ValueError, OSError):
        return None, "Its manifest.json can't be read."
    name = str(man.get("name") or "").strip()
    colour = str(man.get("logo_colour") or "").lower()
    if not name or len(name) > 40:
        return None, "Its manifest needs a name of 40 characters or fewer."
    if man.get("id") != folder.name:
        return None, f"Its manifest id must match its folder name ({folder.name})."
    if not T.HEX.match(colour):
        return None, "Its manifest needs a logo_colour like #1a2fb5."
    header = man.get("header_image")
    if header is not None:
        pic = folder / str(header)
        if not (HEADER_IMAGE.match(str(header)) and pic.is_file() and pic.stat().st_size <= HEADER_MAX):
            return None, "Its header_image must be a .png, .jpg or .webp file of 5 MB or less in its own folder."
    try:
        css = (folder / "theme.css").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "It has no readable theme.css."
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S).strip().lower()
    block = re.fullmatch(r":root\s*\{([^{}]*)\}", bare)
    decls = [d.strip() for d in block.group(1).split(";") if d.strip()] if block else []
    if not block or not all(DECL.match(re.sub(r"\s+", " ", d)) for d in decls):
        return None, "Its theme.css may only set colours in one :root block (no other rules, @import or url())."
    values = T.read_values(css)
    missing = [k for k in T.KEYS if k not in values]
    if missing:
        return None, f"Its theme.css is missing {len(missing)} of the 17 colours (for example --{missing[0]})."
    problems = T.problems(values, colour)
    if problems:
        return None, "Its colours don't pass the contrast check: " + _first(problems)
    return {"id": folder.name, "name": name, "description": str(man.get("description") or ""),
            "logo_colour": colour, "custom": custom, "folder": folder, "header_image": header,
            "palette": {f"--{k}": v for k, v in values.items()}}, None


def _scan():
    themes, rejected, seen = [], [], set()
    for base, custom in ((BUILTIN_DIR, False), (custom_dir(), True)):
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            if not THEME_ID.match(folder.name):
                continue
            if folder.name in seen:
                continue                        # a built-in id always wins
            theme, reason = check(folder, custom)
            if theme:
                seen.add(folder.name)
                themes.append(theme)
            else:
                rejected.append({"folder": folder.name, "custom": custom, "reason": reason})
    themes.sort(key=lambda t: (t["custom"], t["id"] != DEFAULT_ID, t["name"].lower()))
    return themes, rejected


def find_theme(theme_id):
    """The checked theme with this id, or None."""
    if not THEME_ID.match(theme_id or ""):
        return None
    for base, custom in ((BUILTIN_DIR, False), (custom_dir(), True)):
        folder = base / theme_id
        if folder.is_dir():
            return check(folder, custom)[0]
    return None


def css_text(theme_id):
    """The theme's CSS as served, or None. A header picture named in the
    manifest is added here as one custom property (layout.css uses it)."""
    t = find_theme(theme_id)
    if not t:
        return None
    css = (t["folder"] / "theme.css").read_text(encoding="utf-8")
    if t["header_image"]:
        css += (f"\n/* Added by MetaForge: header_image from manifest.json */\n"
                f":root {{ --theme-header-image: url(\"/theme_header/{t['id']}\"); }}\n")
    return css


def header_image(theme_id):
    """(path, mimetype) of the theme's header picture, or (None, None)."""
    t = find_theme(theme_id)
    if not t or not t["header_image"]:
        return None, None
    return t["folder"] / t["header_image"], IMAGE_TYPES[t["header_image"].rsplit(".", 1)[1].lower()]


def logo_path(theme_id):
    """The theme's own logo.png, else its generated logo; the default theme's
    if the theme isn't found."""
    t = find_theme(theme_id) or find_theme(DEFAULT_ID)
    if not t:
        return logo_engine.cached(T.BRAND_GOLD)
    own = t["folder"] / "logo.png"
    return own if own.is_file() else logo_engine.cached(t["logo_colour"])


def discover(base_dir=None):
    try:
        themes, rejected = _scan()
        public = [{k: v for k, v in t.items() if k not in ("folder", "header_image")} for t in themes]
        return jsonify({"themes": public, "rejected": rejected})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def template():
    return jsonify(T.as_json())


def values():
    """The 17 colours and logo colour of an existing theme, to start from."""
    t = find_theme(request.args.get("id", ""))
    if not t:
        return jsonify({"status": "error", "message": "That theme wasn't found."}), 404
    return jsonify({"status": "success", "values": {k[2:]: v for k, v in t["palette"].items()},
                    "name": t["name"], "custom": t["custom"], "logo_colour": t["logo_colour"]})


def _logo_colour(src):
    colour = (src.get("colour") or "").lower()
    return colour if T.HEX.match(colour) else None


def logo_preview():
    colour = _logo_colour(request.args)
    if not colour:
        return jsonify({"status": "error", "message": "Logo colour not understood."}), 400
    return Response(logo_engine.make(colour), mimetype="image/png", headers={"Cache-Control": "no-store"})


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:60]


def _write(path, data):
    tmp = path.with_name(path.name + ".tmp")
    if isinstance(data, bytes):
        tmp.write_bytes(data)
    else:
        tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def save_custom():
    body = request.json or {}
    name = re.sub(r"\s+", " ", str(body.get("name", ""))).strip()
    vals = {k: str(v).lower() for k, v in (body.get("values") or {}).items() if k in T.KEYS}
    colour = _logo_colour(body.get("logo") or {})
    slug = _slug(name)
    if not name or not slug:
        return jsonify({"status": "error", "message": "Give the theme a name (letters or numbers)."}), 400
    if len(name) > 40:
        return jsonify({"status": "error", "message": "Keep the name to 40 characters or fewer."}), 400
    if not colour:
        return jsonify({"status": "error", "message": "Choose a logo colour."}), 400
    if (BUILTIN_DIR / slug).exists():
        return jsonify({"status": "error", "message": f"“{name}” is the name of a built-in theme. Choose another name."}), 400
    issues = T.problems(vals, colour)
    if issues:
        return jsonify({"status": "error", "message": "The theme wasn't saved: " + " ".join(issues[:3])
                        + (f" (and {len(issues) - 3} more)" if len(issues) > 3 else ""), "problems": issues}), 400
    folder = custom_dir() / slug
    if folder.exists() and not body.get("overwrite"):
        return jsonify({"status": "exists", "message": f"You already have a theme called “{name}”."}), 409
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    manifest = {"name": name, "id": slug, "version": "1.0.0",
                "description": f"Made with Settings > Theme > Create a theme ({stamp}).", "logo_colour": colour}
    _write(folder / "logo.png", logo_engine.make(colour))
    _write(folder / "theme.css", T.render_css(name, vals, stamp))
    _write(folder / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return jsonify({"status": "success", "id": slug, "name": name})


def delete_custom():
    theme_id = (request.json or {}).get("id", "")
    folder = custom_dir() / theme_id
    if not THEME_ID.match(theme_id or "") or not folder.is_dir():
        return jsonify({"status": "error", "message": "Only themes you made can be deleted."}), 400
    shutil.rmtree(folder)
    return jsonify({"status": "success"})

# --- END OF FILE theme_engine.py ---
