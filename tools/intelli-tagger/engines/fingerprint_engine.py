# --- START OF FILE fingerprint_engine.py ---
# ======================================================================
# MetaForge Engine: Acoustic Fingerprint Resolver (Phase 6.5)
# Role: Generates AcoustID via fpcalc + lookup
# Build 1.1.0: Correct duration coercion + hard diagnostics
# ======================================================================

import subprocess
import json
import requests
from common import config_handler


FPCALC = config_handler.FPCALC_EXE
ACOUSTID_KEY = config_handler.os.getenv("ACOUSTID_KEY")

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
            return {"acoustid": "None"}

        acoustid = results[0].get("id", "None")

        return {
            "acoustid": acoustid
        }

    except Exception as e:
        return {"acoustid": "None"}


# --- END OF FILE fingerprint_engine.py ---