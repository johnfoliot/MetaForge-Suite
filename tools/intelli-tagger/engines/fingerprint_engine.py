# --- START OF FILE fingerprint_engine.py ---
# ======================================================================
# MetaForge Engine: Acoustic Fingerprint Resolver (Phase 6.5)
# Role: Generates AcoustID via fpcalc + lookup
# Build 1.1.0: Correct duration coercion + hard diagnostics
# ======================================================================

import subprocess
import json
import time
import requests
from common import config_handler


FPCALC = config_handler.FPCALC_EXE
ACOUSTID_KEY = config_handler.os.getenv("ACOUSTID_KEY")
PENDING_FILE = config_handler.DATA_DIR / "acoustid" / "pending_acoustid.txt"


def _queue_for_submission(file_path):
    """Logs a track with a confirmed-absent AcoustID match so tools/acoustid can submit it later."""
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = str(file_path)
    existing = set()
    if PENDING_FILE.exists():
        existing = set(PENDING_FILE.read_text(encoding="utf-8").splitlines())
    if entry not in existing:
        with open(PENDING_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")


def generate_acoustid(file_path):
    """
    Returns:
    {
        "acoustid": str
    }
    """
    try:
        # -------------------------------------------------
        # STEP 1: fpcalc
        # -------------------------------------------------
        result = subprocess.run(
            [str(FPCALC), "-json", str(file_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {"acoustid": "None"}

        fp_data = json.loads(result.stdout)

        fingerprint = fp_data.get("fingerprint")
        duration = fp_data.get("duration")

        if not fingerprint:
            return {"acoustid": "None"}

        if duration is None:
            print("[FINGERPRINT ERROR] Missing duration")
            return {"acoustid": "None"}

        # CRITICAL FIX:
        # AcoustID wants integer seconds, not float
        duration = int(round(float(duration)))


        # -------------------------------------------------
        # STEP 2: AcoustID lookup
        # -------------------------------------------------
        payload = {
            "client": str(ACOUSTID_KEY).strip(),
            "fingerprint": fingerprint,
            "duration": str(duration),
            "meta": "recordings"
        }

        # Rate limit: avoid bursting the AcoustID API across a batch of tracks
        time.sleep(1.0)

        response = requests.post(
            "https://api.acoustid.org/v2/lookup",
            data=payload,
            timeout=15
        )


        data = response.json()

        if data.get("status") != "ok":
            return {"acoustid": "None"}

        results = data.get("results", [])

        if not results:
            # Fingerprint submitted and looked up successfully, but AcoustID
            # has no record of it yet — queue it for the acoustid tool to submit.
            _queue_for_submission(file_path)
            return {"acoustid": "None"}

        acoustid = results[0].get("id", "None")

        return {
            "acoustid": acoustid
        }

    except Exception as e:
        return {"acoustid": "None"}


# --- END OF FILE fingerprint_engine.py ---