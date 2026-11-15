# ======================================================================
# MetaForge Studio: the app's version (single source of truth)
# Physical Location: \common\version.py
# ======================================================================
"""
The version of THIS build. It lives in code, so nothing on screen can
change it (1.x kept the "installed version" in an editable JSON file that
the update screen overwrote whenever you clicked View details or Dismiss).

Format: MAJOR.MINOR.PATCH, optionally followed by a pre-release label
("-dev", "-beta.2"). A pre-release sorts BEFORE its release:
2.0.0-dev < 2.0.0 < 2.0.1.

Release steps (see deploy/README.md): set APP_VERSION here, then publish
the same number in deploy/updates.json on GitHub's main branch.
"""
import re

APP_VERSION = "2.0.0-dev"   # v2 rebuild in progress; first remediated release = 2.0.1 (John, 2026-11-15)

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\s*$")


def parse_version(text):
    """'2.0.1' -> (2, 0, 1, None); '2.0.0-dev' -> (2, 0, 0, 'dev'); None if not a version."""
    m = _VERSION_RE.match(str(text or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)


def _key(v):
    major, minor, patch, pre = v
    # A release (no pre-release label) sorts after any pre-release of the same number.
    pre_key = (1, ()) if pre is None else (0, tuple(int(p) if p.isdigit() else p for p in pre.split(".")))
    return (major, minor, patch, pre_key)


def is_newer(candidate, current=APP_VERSION):
    """True only if `candidate` is a strictly newer version than `current`."""
    a, b = parse_version(candidate), parse_version(current)
    if a is None or b is None:
        return False
    return _key(a) > _key(b)
