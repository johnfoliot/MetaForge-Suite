# --- START OF FILE id_engine.py ---
# ======================================================================
# MetaForge Engine: Identity Recovery (Phase 6)
# Build 1.7.2: REMEDIATED: Pre-flight tag reads before API calls.
# Physical Location: \tools\intelli-tagger\engines\id_engine.py
# ======================================================================
import subprocess, json, time, requests, re
from mutagen.id3 import ID3
from common import config_handler

FPCALC_EXE = config_handler.FPCALC_EXE
ACOUSTID_KEY = config_handler.ACOUSTID_API_KEY
MB_BASE_URL = "https://musicbrainz.org/ws/2"
session = requests.Session()
session.headers.update({"User-Agent": "MetaForgeStudio/1.2 ( johnfoliot@gmail.com )", "Accept": "application/json"})

def get_track_identity(file_path):
    tags = ID3(str(file_path))

    # --- Pre-flight: Read existing tags before hitting any API ---
    mb_track_id = _read_existing_mb_id(tags)
    acoustid     = _read_existing_acoustid(tags)
    original_year = _read_existing_origyear(tags)

    # --- Fall back to API only if pre-flight came up empty ---
    if mb_track_id == "None" or acoustid == "None":
        duration = _get_duration(file_path)
        api_acoustid, api_mb_id = _fetch_acoustid_and_mb(file_path, duration)
        if acoustid == "None":
            acoustid = api_acoustid
        if mb_track_id == "None":
            mb_track_id = api_mb_id

    # --- Fall back to MB recording lookup only if TDOR was absent ---
    if original_year == "Unknown" and mb_track_id != "None":
        original_year = _fetch_origyear_by_mb_id(mb_track_id)

    if original_year == "Unknown":
        title = str(tags.get('TIT2', file_path.stem))
        original_year = _fetch_hybrid_origyear(title)

    return {
        "acoustid": acoustid,
        "mb_track_id": mb_track_id,
        "original_year": original_year
    }

def _read_existing_mb_id(tags):
    """Read UFID:http://musicbrainz.org — the native MB track ID frame."""
    ufid = tags.get('UFID:http://musicbrainz.org')
    if ufid and ufid.data:
        try:
            return ufid.data.decode('utf-8').strip()
        except Exception:
            pass
    # Also check TXXX:MB_Track_ID written by commit_engine
    txxx = tags.get('TXXX:MB_Track_ID')
    if txxx and str(txxx.text[0]).strip() not in ('', 'None'):
        return str(txxx.text[0]).strip()
    return "None"

def _read_existing_acoustid(tags):
    """Read TXXX:AcoustID written by commit_engine."""
    txxx = tags.get('TXXX:AcoustID')
    if txxx and str(txxx.text[0]).strip() not in ('', 'None'):
        return str(txxx.text[0]).strip()
    return "None"

def _read_existing_origyear(tags):
    """Read TDOR — native ID3 original release year frame."""
    tdor = tags.get('TDOR')
    if tdor:
        val = str(tdor).strip()[:4]
        if val.isdigit():
            return val
    return "Unknown"

def _get_duration(file_path):
    try:
        cmd = [str(FPCALC_EXE), "-length", "60", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return int(json.loads(res.stdout).get("duration", 0))
    except:
        return 0

def _fetch_acoustid_and_mb(file_path, duration):
    try:
        # Use -json flag
        cmd = [str(FPCALC_EXE), "-json", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        output = res.stdout
        # Find the start of the JSON block
        json_start = output.find('{')
        if json_start == -1:
            print(f"DEBUG: No JSON structure found in fpcalc output.")
            return "None", "None"
        
        data = json.loads(output[json_start:])
        
        # API Call
        r = session.post("https://api.acoustid.org/v2/lookup", data={
            "client": ACOUSTID_KEY, 
            "meta": "recordings", 
            "fingerprint": data["fingerprint"], 
            "duration": int(data["duration"])
        }, timeout=10)
        
        if r.status_code == 200 and r.json().get("results"):
            res_data = r.json()["results"][0]
            return res_data.get("id", "None"), res_data.get("recordings", [{}])[0].get("id", "None")
        else:
            print(f"DEBUG: AcoustID API lookup failed: {r.status_code} - {r.text}")
            
    except Exception as e:
        print(f"DEBUG: Critical failure in AcoustID calculation: {e}")
    return "None", "None"

def _fetch_origyear_by_mb_id(mb_track_id):
    """Fetch original year directly from MB using the known recording ID."""
    try:
        time.sleep(1.1)
        r = session.get(f"{MB_BASE_URL}/recording/{mb_track_id}", params={"fmt": "json"})
        if r.status_code == 200:
            date = r.json().get('first-release-date', '')
            if date:
                return date[:4]
    except:
        pass
    return "Unknown"

def _fetch_hybrid_origyear(title):
    clean_title = re.sub(r"[:\-\(\)\[\]/]", " ", title)
    query = f'recording:"{clean_title}" AND status:official'
    try:
        time.sleep(1.1)
        r = session.get(f"{MB_BASE_URL}/recording", params={"query": query, "limit": 10, "fmt": "json"})
        if r.status_code == 200 and r.json().get('recordings'):
            dates = [rec.get('first-release-date', "9999") for rec in r.json()['recordings'] if rec.get('first-release-date')]
            return min(dates).split('-')[0] if dates else "Unknown"
    except:
        pass
    return "Unknown"
# --- END OF FILE id_engine.py ---