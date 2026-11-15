"""
Switch Settings > Check for updates into TEST MODE, or back to normal.

    python dev\\use_update_test.py update_available   # pretend 2.0.1 is out
    python dev\\use_update_test.py up_to_date
    python dev\\use_update_test.py required_update    # can't be dismissed
    python dev\\use_update_test.py unsafe_link        # link must be refused
    python dev\\use_update_test.py offline            # pretend GitHub is unreachable
    python dev\\use_update_test.py off                # back to the real GitHub check

Test mode copies a scenario to dev/update_test.json; the update engine reads
that file instead of GitHub while it exists, and the screen says "Test mode"
so it can never be mistaken for the real thing. No app restart needed.
Also: python dev\\use_update_test.py reset-dismissed  (forget a Dismiss).
"""
import json, os, shutil, sys
from pathlib import Path

DEV = Path(__file__).resolve().parent
ACTIVE = DEV / "update_test.json"
SCENARIOS = DEV / "update_tests"

arg = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
if arg == "off":
    ACTIVE.unlink(missing_ok=True)
    print("Test mode OFF: Check for updates reads GitHub again.")
elif arg == "offline":
    ACTIVE.write_text("this is deliberately not JSON, to simulate a failed download", encoding="utf-8")
    print("Test mode ON: 'offline' (the check fails as if GitHub were unreachable).")
elif arg == "reset-dismissed":
    prefs = Path(os.environ["APPDATA"]) / "MetaForge" / "preferences.json"
    data = json.loads(prefs.read_text(encoding="utf-8")) if prefs.exists() else {}
    data.pop("dismissed_update_version", None)
    prefs.write_text(json.dumps(data, indent=4), encoding="utf-8")
    print("Forgot the dismissed update version.")
elif (SCENARIOS / f"{arg}.json").exists():
    shutil.copyfile(SCENARIOS / f"{arg}.json", ACTIVE)
    print(f"Test mode ON: '{arg}'. Open Settings > Check for updates.")
else:
    print(__doc__)
    print("Scenarios:", ", ".join(p.stem for p in SCENARIOS.glob("*.json")), "+ offline, off, reset-dismissed")
    sys.exit(1)
