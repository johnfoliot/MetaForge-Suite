# --- START OF FILE theme_engine.py ---
# ======================================================================
# MetaForge Mini-Engine: Themes
# Physical Location: \tools\settings\engines\theme_engine.py
# v2 (2026-11-15):
#  - Built-in themes: ui/css/*_theme.css (read-only).
#  - Your own themes (Create a theme): AppData\MetaForge\themes\
#    <slug>_theme.css + logo_<slug>.svg. AppData so they survive updates
#    and a future installer (John). Only the v2 build lists them.
#  - Each theme names its logo in its header comment (mf-logo: ...), so
#    the app no longer needs a hard-coded theme -> logo list.
#  - save_custom() refuses anything the theme template says fails
#    (contrast pairs, the one-gold brand rule).
# ======================================================================
import re
import time

from flask import jsonify, request, Response

from common import config_handler
import theme_template as T
import logo_engine

BUILTIN_DIR = config_handler.PROJECT_ROOT / "ui" / "css"
IMAGES_DIR = config_handler.PROJECT_ROOT / "ui" / "images"
CUSTOM_DIR = config_handler.APPDATA_MF / "themes"
THEME_FILE = re.compile(r"^[a-z0-9_]+_theme\.css$")


def _palette(text):
    vals = T.read_values(text)
    return {f"--{k}": v for k, v in vals.items()}


def _label(path, meta):
    return meta.get("name") or path.name.replace("_theme.css", "").replace("_", " ").title()


def find_theme(file_name):
    """(path, is_custom) for a theme file name, or (None, None)."""
    if not THEME_FILE.match(file_name or ""):
        return None, None
    for folder, custom in ((BUILTIN_DIR, False), (CUSTOM_DIR, True)):
        p = folder / file_name
        if p.is_file():
            return p, custom
    return None, None


def logo_path_for(file_name):
    """The logo a theme names (mf-logo), falling back to the gold logo."""
    p, custom = find_theme(file_name)
    if p:
        logo = T.read_meta(p.read_text(encoding="utf-8")).get("logo", "")
        if re.match(r"^[\w-]+\.svg$", logo):
            for folder in ((CUSTOM_DIR, IMAGES_DIR) if custom else (IMAGES_DIR,)):
                if (folder / logo).is_file():
                    return folder / logo
    return IMAGES_DIR / "logo.svg"


def discover(base_dir=None):
    themes = []
    try:
        for folder, custom in ((BUILTIN_DIR, False), (CUSTOM_DIR, True)):
            if not folder.is_dir():
                continue
            for f in sorted(folder.glob("*_theme.css")):
                if custom and (BUILTIN_DIR / f.name).exists():
                    continue          # a built-in name always wins
                text = f.read_text(encoding="utf-8")
                meta = T.read_meta(text)
                themes.append({"file": f.name, "name": _label(f, meta), "palette": _palette(text), "custom": custom})
        themes.sort(key=lambda t: (t["custom"], t["name"].lower()))
        return jsonify(themes)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def template():
    return jsonify(T.as_json())


def values():
    """The 17 colours (+ logo settings) of an existing theme, to start from."""
    p, custom = find_theme(request.args.get("file", ""))
    if not p:
        return jsonify({"status": "error", "message": "That theme wasn't found."}), 404
    text = p.read_text(encoding="utf-8")
    meta = T.read_meta(text)
    vals = T.read_values(text)
    return jsonify({"status": "success", "values": vals, "name": _label(p, meta), "custom": custom,
                    "logo_style": meta.get("logo-style", "full"),
                    "logo_colour": meta.get("logo-colour") or vals.get("mf-gold", T.BRAND_GOLD)})


def _logo_args(src):
    style = src.get("style", "full")
    colour = (src.get("colour") or "").lower()
    if style not in ("full", "faces") or not T.HEX.match(colour):
        return None, None
    return style, colour


def logo_preview():
    style, colour = _logo_args(request.args)
    if not style:
        return jsonify({"status": "error", "message": "Logo style or colour not understood."}), 400
    return Response(logo_engine.make(style, colour), mimetype="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def save_custom():
    body = request.json or {}
    name = re.sub(r"\s+", " ", str(body.get("name", ""))).strip()
    vals = {k: str(v).lower() for k, v in (body.get("values") or {}).items() if k in T.KEYS}
    style, colour = _logo_args(body.get("logo") or {})
    slug = _slug(name)
    if not name or not slug:
        return jsonify({"status": "error", "message": "Give the theme a name (letters or numbers)."}), 400
    if len(name) > 40:
        return jsonify({"status": "error", "message": "Keep the name to 40 characters or fewer."}), 400
    if not style:
        return jsonify({"status": "error", "message": "Choose a logo style and colour."}), 400
    file_name = f"{slug}_theme.css"
    if (BUILTIN_DIR / file_name).exists():
        return jsonify({"status": "error", "message": f"“{name}” is the name of a built-in theme. Choose another name."}), 400
    issues = T.problems(vals, colour)
    if issues:
        return jsonify({"status": "error", "message": "The theme wasn't saved: " + " ".join(issues[:3])
                        + (f" (and {len(issues) - 3} more)" if len(issues) > 3 else ""), "problems": issues}), 400
    css_path = CUSTOM_DIR / file_name
    if css_path.exists() and not body.get("overwrite"):
        return jsonify({"status": "exists", "message": f"You already have a theme called “{name}”."}), 409
    CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    logo_file = f"logo_{slug}.svg"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    for path, text in ((CUSTOM_DIR / logo_file, logo_engine.make(style, colour)),
                       (css_path, T.render_css(name, vals, logo_file, style, colour, stamp))):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return jsonify({"status": "success", "file": file_name, "name": name})


def delete_custom():
    file_name = (request.json or {}).get("file", "")
    p, custom = find_theme(file_name)
    if not p or not custom:
        return jsonify({"status": "error", "message": "Only themes you made can be deleted."}), 400
    meta = T.read_meta(p.read_text(encoding="utf-8"))
    p.unlink()
    logo = meta.get("logo", "")
    if re.match(r"^[\w-]+\.svg$", logo):
        (CUSTOM_DIR / logo).unlink(missing_ok=True)
    return jsonify({"status": "success"})

# --- END OF FILE theme_engine.py ---
