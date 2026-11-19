# ======================================================================
# MetaForge Dev Tool: third-party library list for the About page
# Physical Location: \dev\build_notices.py
# ======================================================================
"""
Writes licenses/python_libraries.json: every Python library MetaForge runs
on, with its version, licence and home page, read from the installed
packages (the virtual environment and the vendored common/lib folder).

The list is generated so it can't go stale: run this again whenever a
library is added, removed or upgraded, and commit the result.

    venv\\Scripts\\python.exe dev\\build_notices.py

Tools that only build MetaForge (PyInstaller and friends) are left out:
they are not part of the running program.
"""
import json
import re
import sys
from datetime import date
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "licenses" / "python_libraries.json"

BUILD_ONLY = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile",
              "pywin32-ctypes", "pip", "setuptools", "wheel"}

# What the main libraries do here, in plain words (shown on the About page).
USED_FOR = {
    "mutagen": "Reads and writes tags",
    "librosa": "Measures tempo, key and intensity",
    "flask": "Runs the screens",
    "pywebview": "The program window",
    "pillow": "Cover art, photos and the logo",
    "requests": "Talks to the online services",
    "google-genai": "Talks to Google Gemini",
    "wikipedia-api": "Reads Wikipedia",
    "numpy": "Number work for the audio measurements",
    "scipy": "Number work for the audio measurements",
    "soundfile": "Reads audio for measuring",
    "soxr": "Resamples audio for measuring",
    "python-dotenv": "Reads your settings file",
    "tenacity": "Retries a service that is busy",
    "pycountry": "Country names",
}

# Tidy names for the licences the packages declare in many spellings.
TIDY = [
    (r"lgpl-2\.1-or-later", "LGPL 2.1 or later"),      # before the GPL line: "lgpl" contains "gpl"
    (r"lgpl-2\.1-only", "LGPL 2.1"),
    (r"gpl.?v?2.*(later|\+)|gpl-2\.0-or-later", "GPL 2.0 or later"),
    (r"mozilla public license 2\.0|mpl-2\.0", "MPL 2.0"),
    (r"apache", "Apache 2.0"),
    (r"psf", "PSF 2.0"),
    (r"isc", "ISC"),
    (r"mit-cmu", "MIT-CMU"),
    (r"bsd-2", "BSD 2-Clause"),
    (r"bsd-3|bsd 3", "BSD 3-Clause"),
    (r"bsd", "BSD"),
    (r"mit", "MIT"),
]
# Licences the package metadata doesn't state; read from each project's own LICENSE file.
KNOWN = {"llvmlite": "BSD 2-Clause"}


def _licence(md):
    declared = (md.get("License-Expression") or "").strip()
    if not declared:
        classifiers = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License")]
        declared = "; ".join(classifiers) or (md.get("License") or "").strip().split("\n")[0]
    if " AND " in declared or " OR " in declared:
        return declared                      # a compound SPDX expression: keep as stated
    low = declared.lower()
    if ";" in declared:                      # several classifiers: tidy each
        parts = []
        for piece in declared.split(";"):
            parts.append(next((name for pat, name in TIDY if re.search(pat, piece.lower())), piece.strip()))
        return " / ".join(dict.fromkeys(parts))
    return next((name for pat, name in TIDY if re.search(pat, low)), declared[:60])


def _url(md):
    urls = {}
    for line in md.get_all("Project-URL") or []:
        if "," in line:
            label, url = line.split(",", 1)
            urls[label.strip().lower()] = url.strip()
    for key in ("homepage", "home", "source", "source code", "repository", "github", "documentation"):
        if key in urls:
            return urls[key]
    return (md.get("Home-page") or next(iter(urls.values()), "")).strip()


def main():
    found = {}
    for dist in list(metadata.distributions()) + list(metadata.distributions(path=[str(ROOT / "common" / "lib")])):
        md = dist.metadata
        name = md["Name"]
        if not name or name.lower().replace("_", "-") in BUILD_ONLY:
            continue
        key = name.lower().replace("_", "-")
        licence = KNOWN.get(key) or _licence(md)
        entry = {"name": name, "version": dist.version, "licence": licence or "Not stated", "url": _url(md)}
        if key in USED_FOR:
            entry["used_for"] = USED_FOR[key]
        # The vendored copy (scanned second) wins when both exist: it is the one MetaForge loads.
        found[key] = entry
    libs = sorted(found.values(), key=lambda e: e["name"].lower())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"generated": date.today().isoformat(), "libraries": libs}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    unstated = [e["name"] for e in libs if e["licence"] in ("Not stated", "")]
    print(f"{len(libs)} libraries written to {OUT}")
    if unstated:
        print("Licence not stated in the package metadata, check by hand:", ", ".join(unstated))
    return 0


if __name__ == "__main__":
    sys.exit(main())
