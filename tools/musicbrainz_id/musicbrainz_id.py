# --- START OF FILE musicbrainz_id.py ---
# ======================================================================
# MetaForge Studio: MusicBrainz Forensic Logic (Structural Sync Build)
# File Location: \tools\musicbrainz_id\musicbrainz_id.py
# Build 2.21.3: Implemented per-track ID validation and debugging.
# Directive IX: ID3v2.3 Standard | UTF-16 Encoding (1)
# ======================================================================

import os
import time
import json
import re
import requests
from datetime import datetime
from pathlib import Path
from flask import request, jsonify
from mutagen.id3 import ID3, TXXX, UFID, TYER, TRCK, TIT2, TPE1, ID3NoHeaderError
from mutagen.mp3 import MP3

# --- [ SHARED PRIMITIVES ] ---
from common import config_handler, io_bridge

# --- [ GLOBAL SESSION ENGINE ] ---
session = requests.Session()
BASE_URL = "https://musicbrainz.org/ws/2"
MB_DELAY = 1.1 

def natural_sort_key(s):
    """Helper: Generates a key for natural alphanumeric sorting."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', s)]

def sanitize_filename(name):
    """Removes illegal filesystem characters."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    return clean.strip()

def get_mb_headers(env_path):
    email = "anonymous@metaforge.studio"
    if env_path.exists():
        try:
            content = env_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                if line.startswith("USER_EMAIL="):
                    email = line.split("=", 1)[1].strip()
                    break
        except Exception: pass
    return {"User-Agent": f"MetaForgeStudio/1.0.0 ({email})", "Accept": "application/json"}

def run_logic(action, tools_dir, env_path):
    headers = get_mb_headers(env_path)
    session.headers.update(headers)

    if action == "search": return search_musicbrainz()
    if action == "get_release_details": return get_release_details()
    if action == "get_folder_context": return get_folder_context()
    if action == "commit": return commit_ids_to_files(env_path)
    
    return jsonify({"status": "error", "message": f"Action '{action}' not implemented."})

def get_folder_context():
    data = request.json
    local_path = data.get('local_path')
    if not local_path: return jsonify({"status": "error", "message": "⚠️ No path provided."})

    manifest_path = Path(local_path) / "manifest.json"
    context = {"artist": "", "album": "", "track_count": 0}

    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding='utf-8'))
            context = {"artist": m.get('artist_seed', ''), "album": m.get('album_seed', ''), "track_count": m.get('track_count', 0)}
        except Exception: pass

    return jsonify({"status": "success", "context": context})

def search_musicbrainz():
    data = request.json
    artist, album = data.get('artist', ''), data.get('album', '')
    scrubbed_album = re.sub(r'[:\-\(\)\[\]/]', ' ', album)
    clean_query = f'artist:"{artist}" AND release:({" ".join(scrubbed_album.split())})'
    
    try:
        time.sleep(MB_DELAY)
        params = {"query": clean_query, "fmt": "json", "limit": 25}
        res = session.get(f"{BASE_URL}/release", params=params)
        res.raise_for_status()
        result = res.json()
        
        releases = []
        for r in result.get('releases', []):
            releases.append({
                "id": r.get('id'),
                "score": r.get('score', '0'),
                "artist": r.get('artist-credit', [{}])[0].get('name', 'Unknown'),
                "title": r.get('title', 'Unknown'),
                "track_count": r.get('track-count', '0'),
                "year": r.get('date', 'Unknown')[:4],
                "country_code": r.get('country', '??').lower()
            })
        return jsonify({"status": "success", "results": releases})
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

def get_release_details():
    data = request.json
    release_id, local_path = data.get('release_id'), Path(data.get('local_path'))

    try:
        time.sleep(MB_DELAY)
        params = {"inc": "recordings+release-groups+artists", "fmt": "json"}
        res = session.get(f"{BASE_URL}/release/{release_id}", params=params)
        res.raise_for_status()
        release = res.json()
        
        remote_tracks = []
        for media in release.get('media', []):
            for track in media.get('tracks', []):
                remote_tracks.append({
                    "position": str(track.get('number', '')),
                    "title": track.get('recording', {}).get('title', 'Unknown'),
                    "track_id": track.get('recording', {}).get('id', '')
                })

        local_tracks = []
        targets = io_bridge.get_audio_targets(local_path, recursive=True)
        targets.sort(key=lambda x: natural_sort_key(str(x.name)))

        for f in targets:
            local_tracks.append({"filename": str(f.name), "title": f.stem})
        
        return jsonify({
            "status": "success",
            "artist_id": release.get('artist-credit', [{}])[0].get('artist', {}).get('id', ''),
            "release_group_id": release.get('release-group', {}).get('id', ''),
            "country_code": release.get('country', '??').upper(),
            "release_year": (release.get('date', 'Unknown')[:4]),
            "remote_tracks": remote_tracks,
            "local_tracks": local_tracks
        })
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

def commit_ids_to_files(env_path):
    """
    Surgically writes forensic IDs, updates TRCK, and RENAMES files.
    Standard: [track_num] - [artist_seed] - [target_title].mp3
    """
    data = request.json
    local_path, mapping = Path(data.get('local_path')), data.get('mapping') 
    artist_seed = data.get('artist_seed', 'Unknown Artist')
    album_seed = data.get('album_seed', local_path.name)
    release_year = data.get('release_year', 'Unknown')

    stats = {"success": 0, "failed": 0}

    for item in mapping:
        old_path = local_path / item['current_filename']
        if not old_path.exists():
            stats["failed"] += 1
            continue

        try:
            # DEBUG TRACER: See exactly what ID is being passed to each file
            track_id = item.get('track_id')
            print(f"DEBUG: COMMIT START | File: {item['current_filename']} | TrackID: {track_id}")

            # 1. Update Tags
            try: audio = ID3(str(old_path))
            except ID3NoHeaderError: audio = ID3()

            audio.delall("TRCK")
            audio.add(TRCK(encoding=1, text=[str(item['track_num'])]))
            
            # Validation: Only write if valid
            if track_id and isinstance(track_id, str) and track_id.strip():
                # Clear existing UFID to ensure we aren't appending duplicates
                audio.delall("UFID") 
                audio.add(UFID(owner="http://musicbrainz.org", data=track_id.encode('utf-8')))
            else:
                print(f"WARNING: Skipping UFID for {item['current_filename']} (Invalid/Missing ID).")
            
            tags = {
                "MusicBrainz Artist Id": item['artist_id'],
                "MusicBrainz Album Id": item['album_id'],
                "MusicBrainz Release Group Id": item['release_group_id'],
                "MusicBrainz Release Country": item['country_code']
            }
            for desc, val in tags.items():
                if val:
                    audio.delall(f"TXXX:{desc}")
                    audio.add(TXXX(encoding=1, desc=desc, text=[str(val)]))
            
            # Remediated: Scrub TDRC (v2.4) and enforce TYER (v2.3)
            if release_year != "Unknown":
                audio.delall("TDRC")
                audio.delall("TYER")
                audio.add(TYER(encoding=1, text=[str(release_year)]))
            
            audio.save(str(old_path), v2_version=3)

            # 2. Rename File
            t_num = str(item['track_num']).zfill(2)
            safe_artist = sanitize_filename(artist_seed)
            safe_title = sanitize_filename(item['target_title'])
            new_name = f"{t_num} - {safe_artist} - {safe_title}.mp3"
            new_path = old_path.parent / new_name

            if old_path != new_path:
                os.rename(str(old_path), str(new_path))
            
            stats["success"] += 1
        except Exception as e:
            print(f"Commit/Rename Failure: {e}")
            stats["failed"] += 1

    if stats["success"] > 0:
        _update_manifest(local_path, mapping[0], release_year, artist_seed, album_seed)

    return jsonify({"status": "success", "summary": stats})

def _update_manifest(root, sample, year, artist_seed, album_seed):
    manifest_path = root / "manifest.json"
    log_path = root / "MetaForge.log"
    
    # 1. Manifest Initialization & Bootstrapping
    m = {}
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding='utf-8'))
        except Exception:
            pass
            
    # Preserve pre-existing values if they exist, otherwise initialize with seeds
    m.update({
        "artist_seed": m.get("artist_seed") or artist_seed,
        "album_seed": m.get("album_seed") or album_seed,
        "mb_artist_id": sample['artist_id'], 
        "mb_album_id": sample['album_id'],
        "mb_release_group_id": sample['release_group_id'], 
        "mb_release_country": sample['country_code'],
        "release_year": year, 
        "is_physically_synced": True, 
        "synced_at": datetime.now().isoformat()
    })
    
    try:
        manifest_path.write_text(json.dumps(m, indent=4), encoding='utf-8')
    except Exception as e:
        print(f"Error bootstrapping manifest: {e}")

    # 2. Audit Log Initialization & Bootstrapping
    if not log_path.exists():
        try:
            log_header = (
                "============================================================\n"
                f"METAFORGE AUDIT LOG | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                "MetaForge Process: MusicBrainz Alignment\n"
                "------------------------------------------------------------\n"
                f"WORKING_DIRECTORY    - {root}\n"
                f"RELEASE_YEAR (TYER)  - {year}\n"
                f"DATABASE_SYNC        - SUCCESS\n"
                "============================================================\n"
            )
            log_path.write_text(log_header, encoding='utf-8')
        except Exception as e:
            print(f"Error bootstrapping MetaForge.log: {e}")

# --- END OF FILE musicbrainz_id.py ---