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
# Lookups only ever need the application key (John, 2026-07-13 -- renamed
# from ACOUSTID_KEY once AcoustID's separate "user" key, needed only for
# submissions, was discovered; see config_handler.ACOUSTID_APPLICATION_KEY).
ACOUSTID_KEY = config_handler.ACOUSTID_APPLICATION_KEY()
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
        "acoustid": str,
        "acoustid_recording_ids": list[str]  # sibling MB recording MBIDs
            # linked to this fingerprint -- the same acoustic performance
            # sometimes gets catalogued as separate recording entities
            # across different releases, so a sibling may have better
            # original-year data than whichever recording our pipeline
            # happened to match during MB ID matching. Parsed from the
            # "recordings" field already present in the response below
            # (meta=recordings) -- zero extra API calls. May be empty.
    }
    """
    EMPTY = {"acoustid": "None", "acoustid_recording_ids": []}
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
            print(f"[FINGERPRINT ERROR] fpcalc exited {result.returncode} for {file_path}: {result.stderr.strip()}")
            return dict(EMPTY)

        fp_data = json.loads(result.stdout)

        fingerprint = fp_data.get("fingerprint")
        duration = fp_data.get("duration")

        if not fingerprint:
            print(f"[FINGERPRINT ERROR] fpcalc produced no fingerprint for {file_path}")
            return dict(EMPTY)

        if duration is None:
            print("[FINGERPRINT ERROR] Missing duration")
            return dict(EMPTY)

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
            # A real API-level failure (bad/revoked key, quota exceeded,
            # malformed request) previously collapsed into the exact same
            # silent "acoustid: None" as a genuine "not in the database"
            # miss -- indistinguishable without live investigation
            # (caught 2026-07-13: every track in a batch came back None,
            # which turned out to be AcoustID rejecting the stored key
            # outright, not 100% of tracks being unrecognized). Loud and
            # specific now, so a broken key/account shows up on the very
            # first track instead of looking like normal "nothing found."
            err = data.get("error", {})
            print(f"[FINGERPRINT ERROR] AcoustID API returned status={data.get('status')!r} "
                  f"(code {err.get('code')}: {err.get('message')}) for {file_path}")
            return dict(EMPTY)

        results = data.get("results", [])

        if not results:
            # Fingerprint submitted and looked up successfully, but AcoustID
            # has no record of it yet — queue it for the acoustid tool to submit.
            _queue_for_submission(file_path)
            return dict(EMPTY)

        acoustid = results[0].get("id", "None")
        sibling_recordings = results[0].get("recordings", []) or []
        sibling_ids = [r.get("id") for r in sibling_recordings if r.get("id")]

        return {
            "acoustid": acoustid,
            "acoustid_recording_ids": sibling_ids
        }

    except Exception as e:
        print(f"[FINGERPRINT ERROR] {type(e).__name__}: {e} for {file_path}")
        return dict(EMPTY)


# --- END OF FILE fingerprint_engine.py ---