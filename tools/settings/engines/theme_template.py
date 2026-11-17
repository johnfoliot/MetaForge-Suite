# --- START OF FILE theme_template.py ---
# ======================================================================
# MetaForge Mini-Engine: Theme template (single source of truth)
# Physical Location: \tools\settings\engines\theme_template.py
# v2 (2026-11-15, John): every theme has the same 17 colours. This file
# defines them once: plain-language name, group, what it's for, starting
# values for a light and a dark theme, the contrast pairs each must pass,
# and the brand rule (#CC9900 is the only gold). Settings > Theme > Create a
# theme builds its controls, checks and the saved CSS from this; the server
# re-checks everything on save, so a failing theme can't be written.
# ======================================================================
import colorsys
import re

BRAND_GOLD = "#cc9900"

# key (CSS custom property without --), label, group, hint, dark, light
TOKENS = [
    ("bg-main", "Page background", "Backgrounds", "Behind everything: the page, the rail and the header.", "#121212", "#eef0f3"),
    ("bg-stage", "Panels", "Backgrounds", "The area each tool works in.", "#1c1c1c", "#ffffff"),
    ("bg-accent", "Raised areas", "Backgrounds", "Cards, selected items and highlighted rows.", "#262626", "#f5f6f8"),
    ("text-output", "Main text", "Text", "Body text and headings inside panels.", "#f0f0f0", "#1b1d21"),
    ("text-message", "Secondary text", "Text", "Descriptions and less important text.", "#cccccc", "#33373e"),
    ("text-muted", "Hints and placeholders", "Text", "Hints under fields and placeholder text in empty fields.", "#b4b4b4", "#4f5560"),
    ("mf-gold", "Brand colour", "Brand and buttons", "Headings, selected tabs and items, scrollbars.", "#cc9900", "#1a2fb5"),
    ("input-background", "Button colour", "Brand and buttons", "The fill of main action buttons.", "#cc9900", "#1a2fb5"),
    ("input-foreground", "Button text", "Brand and buttons", "Text on main action buttons.", "#121212", "#ffffff"),
    ("input-background2", "Field background", "Fields", "Inside text boxes and lists.", "#101010", "#ffffff"),
    ("input-foreground2", "Field text", "Fields", "What you type into text boxes.", "#f0f0f0", "#1b1d21"),
    ("status-success", "Success messages", "Status messages", "“Saved.” and other good news.", "#48d97a", "#1d6b3a"),
    ("status-error", "Error messages", "Status messages", "Problems that stopped something.", "#ff7a86", "#b3202f"),
    ("status-warning", "Warning messages", "Status messages", "Things to check. Must not look gold.", "#ff9a3c", "#a34700"),
    ("border-ui", "Control borders", "Lines and focus", "Outlines of fields and secondary buttons.", "#8c8c8c", "#767c86"),
    ("border-subtle", "Separator lines", "Lines and focus", "Decorative dividers only (no contrast needed).", "#333333", "#d5d8dd"),
    ("focus-ring", "Keyboard focus ring", "Lines and focus", "The outline around whatever has keyboard focus.", "#ffffff", "#1b1d21"),
]
KEYS = [t[0] for t in TOKENS]

# v2 names, always derived from the colours above (same in every theme)
ALIASES = [
    ("surface-page", "bg-main"), ("surface-panel", "bg-stage"), ("surface-raised", "bg-accent"),
    ("surface-field", "input-background2"), ("text-primary", "text-output"), ("text-secondary", "text-message"),
    ("accent", "mf-gold"), ("accent-fill", "input-background"), ("on-accent-fill", "input-foreground"),
]

SURFACES = ["bg-main", "bg-stage", "bg-accent"]
TEXT_ON_SURFACES = ["text-output", "text-message", "text-muted", "mf-gold", "status-success", "status-error", "status-warning"]

# (foreground, background, minimum ratio, why)
PAIRS = (
    [(t, s, 4.5, "text") for t in TEXT_ON_SURFACES for s in SURFACES]
    + [("input-foreground", "input-background", 4.5, "text"),
       ("input-foreground2", "input-background2", 4.5, "text"),
       ("text-muted", "input-background2", 4.5, "text")]
    + [("border-ui", s, 3.0, "control boundary") for s in SURFACES + ["input-background2"]]
    + [("focus-ring", s, 3.0, "focus indicator") for s in SURFACES]
)

# Brand rule: a colour that reads as gold must BE #CC9900. "Reads as gold"
# = a yellow-orange hue, clearly saturated, mid lightness. Pale creams and
# lemons, browns too dark to read as gold, and orange warnings are allowed.
GOLD_RULE = {"hue_min": 33, "hue_max": 52, "sat_min": 0.45, "light_min": 0.2, "light_max": 0.7}

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def luminance(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def reads_as_gold(h):
    if h.lower() == BRAND_GOLD:
        return False
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    R = GOLD_RULE
    return R["hue_min"] <= hue * 360 <= R["hue_max"] and sat >= R["sat_min"] and R["light_min"] <= light <= R["light_max"]


def problems(values, logo_colour=None):
    """Every reason this theme can't be saved, in plain language."""
    out = []
    labels = {t[0]: t[1] for t in TOKENS}
    for k in KEYS:
        if not HEX.match(values.get(k) or ""):
            out.append(f"{labels[k]} isn't a 6-digit colour code like #1a2fb5.")
    if out:
        return out
    for fg, bg, need, _ in PAIRS:
        r = contrast(values[fg], values[bg])
        if r < need:
            out.append(f"{labels[fg]} on {labels[bg]}: {r:.2f}:1 (needs {need:g}:1).")
    for k in KEYS:
        if reads_as_gold(values[k]):
            out.append(f"{labels[k]} ({values[k]}) reads as gold: the only gold allowed is #CC9900.")
    if logo_colour and reads_as_gold(logo_colour):
        out.append(f"Logo colour ({logo_colour}) reads as gold: the only gold allowed is #CC9900.")
    return out


def as_json():
    return {
        "tokens": [{"key": k, "label": l, "group": g, "hint": h, "dark": d, "light": li} for k, l, g, h, d, li in TOKENS],
        "pairs": [{"fg": f, "bg": b, "min": m, "kind": w} for f, b, m, w in PAIRS],
        "gold_rule": GOLD_RULE,
        "brand_gold": BRAND_GOLD,
    }


def render_css(name, values, stamp):
    """A theme folder's theme.css (its name and logo colour live in manifest.json)."""
    scheme = "light" if luminance(values["bg-main"]) > 0.4 else "dark"
    labels = {t[0]: t[1] for t in TOKENS}
    lines = [
        f"/* --- METAFORGE THEME: {name.upper()} --- */",
        "/* Made with Settings > Theme > Create a theme (" + stamp + ").",
        "   Every contrast pair in the theme template passed when it was saved",
        "   (text 4.5:1, control borders and focus ring 3:1). */",
        ":root {",
        f"    color-scheme: {scheme};",
        "",
    ]
    for k in KEYS:
        lines.append(f"    --{k}: {values[k].lower()};".ljust(40) + f"/* {labels[k]} */")
    lines.append("")
    for alias, src in ALIASES:
        lines.append(f"    --{alias}: var(--{src});")
    lines.append("}")
    return "\n".join(lines) + "\n"


def read_values(css_text):
    return {k: v.lower() for k, v in re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})\b", css_text) if k in KEYS}

# --- END OF FILE theme_template.py ---
