# --- START OF FILE id_engine.py ---
# ======================================================================
# MetaForge Engine: Identity Recovery (Phase 6)
# Role: Recovers AcoustID, Forensic "Original Year", Label, and Personnel.
# Build 1.6.9: Mapping-based TrackID Resolution for improved accuracy.
# Physical Location: \tools\intelli-tagger\engines\id_engine.py
# ======================================================================
import subprocess
import json
import time
import requests
import re
from pathlib import Path
from mutagen.id3 import ID3
from common import config_handler

# --- [ CONFIGURATION ] ---
FPCALC_EXE = config_handler.FPCALC_EXE
ACOUSTID_KEY = config_handler.ACOUSTID_API_KEY
DISCOGS_TOKEN = config_handler.DISCOGS_TOKEN
MB_BASE_URL = "https://musicbrainz.org/ws/2"
MB_DELAY = 1.1

BLACKLIST = ["Bear Family", "Ace", "JSP", "Document", "Proper", "Rhino", "Monogram", "Vogue", "Charly"]

# Forensic Filtering: Only contributors who physically impacted the bitstream.
FORENSIC_ROLE_KEYWORDS = [
    'vocal', 'instrument', 'musician', 'composer', 'lyricist', 
    'writer', 'producer', 'engineer', 'mixer', 'mastering', 
    'conductor', 'orchestrator', 'performer', 'collaborator'
]

session = requests.Session()
session.headers.update({"User-Agent": "MetaForgeStudio/1.2 ( johnfoliot@gmail.com )", "Accept": "application/json"})

def resolve_tracklist(mb_album_id):
    """
    Build 1.6.9: Builds a lookup map for MusicBrainz TrackIDs.
    Maps (Title, Duration_in_Seconds) to Recording UUID.
    """
    track_map = {}
    if not mb_album_id or mb_album_id == "None":
        return track_map

    try:
        time.sleep(MB_DELAY)
        res = session.get(f"{MB_BASE_URL}/release/{mb_album_id}?inc=recordings").json()
        for media in res.get('media', []):
            for track in media.get('tracks', []):
                rec = track.get('recording', {})
                rec_id = rec.get('id')
                title = rec.get('title', '').strip().lower()
                length = rec.get('length', 0)
                if rec_id:
                    # Map by title and rounded duration (allow 3s variance)
                    track_map[(title, int(length / 1000))] = rec_id
    except:
        pass
    return track_map

def get_identity(file_path, target_artist, duration, mb_ids, track_map=None):
    """
    The Forensic Orchestrator.
    Build 1.6.9: Utilizes track_map to resolve missing TrackIDs via Title/Duration.
    """
    # 1. Retrieve the Primary Key (Recording UUID)
    mb_track_id = _get_bitstream_mb_track_id(file_path)
    
    # Extract Native ID3 title
    track_title = ""
    try:
        audio = ID3(str(file_path))
        if 'TIT2' in audio:
            track_title = str(audio['TIT2'].text[0]).strip()
    except Exception:
        pass

    # Fallback to map if missing
    if mb_track_id == "None" and track_map:
        lookup_key = (track_title.lower(), int(duration))
        # Find match within 3s variance if direct duration match fails
        if lookup_key not in track_map:
            for (map_title, map_dur), map_id in track_map.items():
                if map_title == track_title.lower() and abs(map_dur - int(duration)) <= 3:
                    mb_track_id = map_id
                    break
        else:
            mb_track_id = track_map.get(lookup_key)

    mb_artist_id = mb_ids.get('artist')
    mb_album_id = mb_ids.get('album')
    mb_group_id = mb_ids.get('group')

    # 3. AcoustID Fingerprint
    aid = _fetch_acoustid(file_path, duration)

    # 4. Credits & Personnel
    credits = _fetch_surgical_credits(mb_album_id, mb_track_id, target_artist, track_title)
    
    # 5. Overwrite tracking resolution
    if credits.get("title") and credits["title"].strip():
        track_title = credits["title"].strip()
    
    # 6. Original Year
    final_group_id = mb_group_id if mb_group_id != "None" else credits.get('mb_group_id', "None")
    
    orig_year = "Unknown"
    if final_group_id != "None":
        orig_year = _fetch_rg_origyear(final_group_id)
    if orig_year == "Unknown" and track_title:
        orig_year = _fetch_hybrid_origyear(track_title, mb_artist_id)

    return {
        "acoustid": aid,
        "mb_track_id": mb_track_id,
        "original_year": orig_year,
        "label": credits.get("label", "Unknown"),
        "personnel": credits.get("personnel", []),
        "mb_work_id": credits.get("mb_work_id", "None"),
        "title": track_title
    }

def _fetch_surgical_credits(mb_album_id, mb_track_id, artist, track_title):
    data = {"label": "Unknown", "personnel": [], "mb_work_id": "None", "mb_group_id": "None", "title": ""}
    if not mb_album_id or mb_album_id == "None": return data

    try:
        time.sleep(MB_DELAY)
        mb_res = session.get(f"{MB_BASE_URL}/release/{mb_album_id}?inc=labels+release-groups+artist-rels+recordings").json()
        
        data["label"] = mb_res.get('label-info', [{}])[0].get('label', {}).get('name', "Unknown")
        data["mb_group_id"] = mb_res.get('release-group', {}).get('id', "None")
        
        for rel in mb_res.get('relations', []):
            if rel.get('target-type') == 'artist' and _is_forensic_role(rel.get('type', '')):
                data["personnel"].append(f"{rel['type'].replace('-', ' ').title()}: {rel['artist']['name']}")

        if mb_track_id and mb_track_id != "None":
            for media in mb_res.get('media', []):
                for track in media.get('tracks', []):
                    if track.get('recording', {}).get('id') == mb_track_id:
                        mb_title_str = track.get('recording', {}).get('title', '').strip()
                        if mb_title_str:
                            data["title"] = mb_title_str

            time.sleep(MB_DELAY)
            rec_res = session.get(f"{MB_BASE_URL}/recording/{mb_track_id}?inc=artist-credits+artist-rels+work-rels").json()
            rec_title_str = rec_res.get('title', '').strip()
            if rec_title_str:
                data["title"] = rec_title_str

            for rel in rec_res.get('relations', []):
                if rel.get('target-type') == 'artist' and _is_forensic_role(rel.get('type', '')):
                    data["personnel"].append(f"{rel['type'].replace('-', ' ').title()}: {rel['artist']['name']}")
                
                if rel.get('target-type') == 'work':
                    w_id = rel.get('work', {}).get('id')
                    data["mb_work_id"] = w_id
                    time.sleep(MB_DELAY)
                    w_res = session.get(f"{MB_BASE_URL}/work/{w_id}?inc=artist-rels").json()
                    for wr in w_res.get('relations', []):
                        if _is_forensic_role(wr.get('type', '')):
                            data["personnel"].append(f"{wr['type'].replace('-', ' ').title()}: {wr['artist']['name']}")

        if track_title and any(b in data["label"] for b in BLACKLIST) and DISCOGS_TOKEN:
            d_res = session.get("https://api.discogs.com/database/search", 
                                headers={"Authorization": f"Discogs token={DISCOGS_TOKEN}"}, 
                                params={"q": f"{artist} {track_title}", "type": "master"}).json()
            if d_res.get('results'):
                time.sleep(MB_DELAY)
                res = session.get(d_res['results'][0]['resource_url'], headers={"Authorization": f"Discogs token={DISCOGS_TOKEN}"}).json()
                if "masters" in d_res['results'][0]['resource_url']:
                    res = session.get(res['main_release_url'], headers={"Authorization": f"Discogs token={DISCOGS_TOKEN}"}).json()
                
                data["label"] = res.get('labels', [{}])[0].get('name', data["label"])
                for e in res.get('extraartists', []):
                    if e.get('role') and _is_forensic_role(e['role']):
                        data["personnel"].append(f"{e['role'].replace('-', ' ').title()}: {e['name'].split(' (')[0]}")

        data["personnel"] = sorted(list(set(data["personnel"])))
    except:
        pass
    return data

def _is_forensic_role(role_name):
    role_lower = role_name.lower()
    return any(k in role_lower for k in FORENSIC_ROLE_KEYWORDS)

def _get_bitstream_mb_track_id(file_path):
    try:
        audio = ID3(str(file_path))
        ufid = audio.get('UFID:http://musicbrainz.org')
        if ufid: return ufid.data.decode('utf-8')
    except: pass
    return "None"

def _fetch_rg_origyear(group_id):
    try:
        time.sleep(MB_DELAY)
        r = session.get(f"{MB_BASE_URL}/release-group/{group_id}")
        if r.status_code == 200:
            first_date = r.json().get('first-release-date', "")
            return str(_clean_date(first_date)) if _clean_date(first_date) else "Unknown"
    except: pass
    return "Unknown"

def _fetch_acoustid(file_path, duration):
    if not ACOUSTID_KEY: return "None"
    try:
        cmd = [str(FPCALC_EXE), "-json", str(file_path)]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        fp_data = json.loads(res.stdout)
        r = session.post("https://api.acoustid.org/v2/lookup", data={"client": ACOUSTID_KEY, "meta": "recordings", "fingerprint": fp_data["fingerprint"], "duration": int(fp_data["duration"])}, timeout=10)
        if r.status_code == 200 and r.json().get("results"):
            return r.json()["results"][0].get("id", "None")
    except: pass
    return "None"

def _fetch_hybrid_origyear(title, artist_id):
    if not artist_id or artist_id == "None": return "Unknown"
    clean_title = re.sub(r"[:\-\(\)\[\]/]", " ", title)
    query = f'recording:"{clean_title}" AND arid:{artist_id} AND status:official'
    try:
        time.sleep(MB_DELAY)
        r = session.get(f"{MB_BASE_URL}/recording", params={"query": query, "limit": 50, "fmt": "json"})
        if r.status_code == 200:
            years = [_clean_date(rec.get('first-release-date', "")) for rec in r.json().get('recordings', []) if _clean_date(rec.get('first-release-date', ""))]
            return str(min(years)) if years else "Unknown"
    except: pass
    return "Unknown"

def _clean_date(date_str):
    if date_str and len(date_str) >= 4:
        y = date_str[:4]
        if y.isdigit() and int(y) > 1920: return int(y)
    return None

# --- END OF FILE id_engine.py ---