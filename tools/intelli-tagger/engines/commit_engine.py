# --- START OF FILE commit_engine.py ---
# ======================================================================
# MetaForge Engine: Relational & Physical Commit (Phase 7)
# Role: Finalizes bitstream metadata and synchronizes metaforge.db.
# Build 1.5.4: MusicBrainz API Brute-Force Title & Length Sync.
# Physical Location: \tools\intelli-tagger\engines\commit_engine.py
# ======================================================================
import sqlite3
import json
import hashlib
import os
import time
import requests
from datetime import datetime
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TCON, TMOO, TBPM, TKEY, TXXX, TYER, TORY, TPUB, UFID, COMM
from common import config_handler

# --- [ CONFIGURATION ] ---
DB_PATH = config_handler.DB_PATH
SIGNATURE = "Remediation and metadata by MetaForge Studio - the music management tool for Serious Collectors."
MB_BASE_URL = "https://musicbrainz.org/ws/2"

# --- [ RELATIONSHIP MAP ] ---
ROLE_MAP = {
    "Engineer": "engineered",
    "Producer": "produced",
    "Composer": "composed",
    "Writer": "composed",
    "Lyricist": "composed",
    "Mixer": "mixed",
    "Mastering": "mastered",
    "Vocal": "performed",
    "Instrument": "performed",
    "Musician": "performed",
    "Performer": "performed",
    "Conductor": "conducted"
}

def execute_commit(root_path, track_results, db_write=True, manifest_seeds=None):
    """
    The Finalizer: 
    1. Writes physical ID3v2.3 tags (TIT2/TYER/TORY/TPUB/TXXX/COMM).
    2. Brute-forces MusicBrainz title & length recovery using the mb_track_id.
    3. Updates Relational Database (Tracks/Master/Artist).
    4. Option A: Extracts and writes relationship Edges.
    5. Finalizes Audit Manifest and forensic MetaForge.log.
    """
    yield '<div class="it-log-entry it-val-gold" style="margin-top:10px; padding-top:5px; border-top:1px solid var(--mf-gold)"><img src="/ui/images/database.png" style="height:13px; width:auto;" alt=""> Writing to the MetaForge database...</div>'

    artist_name = manifest_seeds.get('artist')
    album_title = manifest_seeds.get('album')
    album_reissue_year = manifest_seeds.get('release_year', 'Unknown')
    current_mb_artist_id = manifest_seeds['mb_ids'].get('artist', 'None')
    
    historical_year = track_results[0][1].get('original_year', 'Unknown')
    mf_id, mf_artist_id = _generate_mf_hashes(artist_name, album_title)
    
    success_count = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = None
    if db_write:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tracks WHERE mf_id = ?", (mf_id,))
            cursor.execute("DELETE FROM edges WHERE source_id = ?", (mf_id,))
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">🚨 DB Connection Error: {str(e)}</div>'
            db_write = False

    forensic_context = track_results[0][1]
    label_val = forensic_context.get('label', 'Unknown')
    personnel_list = forensic_context.get('personnel', [])
    personnel_str = "; ".join(personnel_list) if personnel_list else "Unknown"

    session = requests.Session()
    session.headers.update({"User-Agent": "MetaForgeStudio/1.2 ( johnfoliot@gmail.com )", "Accept": "application/json"})

    for idx, (f_path, data) in enumerate(track_results, 1):
        try:
            current_title = data.get('title', '').strip()
            mb_track_id = data.get('mb_track_id', 'None')
            
            verified_length_seconds = 0
            
            if mb_track_id != 'None':
                try:
                    time.sleep(1.1)
                    rec_res = session.get(f"{MB_BASE_URL}/recording/{mb_track_id}").json()
                    
                    if not current_title or current_title == f_path.stem:
                        mb_verified_title = rec_res.get('title', '').strip()
                        if mb_verified_title:
                            data['title'] = mb_verified_title
                    
                    mb_ms = rec_res.get('length')
                    if mb_ms:
                        verified_length_seconds = int(mb_ms // 1000)
                except Exception:
                    pass 

            if not data.get('title'):
                data['title'] = f_path.stem

            if verified_length_seconds <= 0:
                try:
                    verified_length_seconds = int(data.get('duration', 0))
                except:
                    verified_length_seconds = 0

            _write_physical_tags(f_path, data, album_reissue_year)

            if db_write and conn:
                try:
                    cursor.execute("""
                        INSERT INTO tracks (
                            file_path, mf_id, mf_artist_id, mb_artist_id, mb_track_id, 
                            acoustid, title, genre, sub_genre, original_year, 
                            bpm, key_val, mood, intensity, is_remediated, 
                            last_updated, mb_work_id, orig_year_conf, orig_year_source, leak_flag,
                            length
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(f_path.resolve()).replace('\\', '/'), mf_id, mf_artist_id,
                        current_mb_artist_id, data.get('mb_track_id', 'None'),
                        data.get('acoustid', 'None'), data.get('title'), data.get('parent', 'Unknown'), 
                        data.get('sub', 'Unknown'), data.get('original_year', 'Unknown'),
                        data.get('bpm', 0), data.get('key', '??'), data.get('mood', 'Unknown'), 
                        data.get('intensity', 1), 1, now, data.get('mb_work_id', 'None'),
                        100, "MetaForge Forensic", 0,
                        verified_length_seconds
                    ))
                    success_count += 1
                except sqlite3.IntegrityError:
                    import logging
                    logging.warning(f"INTEL-TAGGER COLLISION: Conflict detected at {f_path}")
                    yield f'<div class="it-log-entry it-val-red">🛑 Collision: {f_path.name} already in database.</div>'
                    return 
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">🔥 Commit Error on {f_path.name}: {str(e)}</div>'

    if db_write and conn:
        try:
            _sync_relational_masters(cursor, mf_id, mf_artist_id, artist_name, album_title, historical_year, label_val, personnel_str, current_mb_artist_id, manifest_seeds, now)
            
            if personnel_list:
                _extract_and_write_edges(cursor, mf_id, personnel_list)
            
            conn.commit()
            conn.close()
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">🚨 Graph Layer Update Failed: {str(e)}</div>'

    _update_audit_trail(root_path, manifest_seeds, track_results, label_val, personnel_list, db_write, historical_year)
    yield f'<div class="it-log-entry">✅ {success_count} tracks synchronized.</div>'

def _extract_and_write_edges(cursor, album_mf_id, personnel):
    for entry in personnel:
        try:
            if ":" not in entry: continue
            role_part, name_part = entry.split(":", 1)
            role = role_part.strip()
            name = name_part.strip()

            relation = ROLE_MAP.get(role, "contributed")
            if "Vocal" in role: relation = "performed"
            if "Instrument" in role: relation = "performed"

            target_id = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()

            cursor.execute("""
                INSERT INTO edges (
                    source_type, source_id, target_type, target_id, 
                    relation_type, role, confidence, source_system, provenance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("album", album_mf_id, "artist", target_id, relation, role, 0.95, "musicbrainz", entry))
        except:
            continue

def _sync_relational_masters(cursor, mf_id, mf_artist_id, artist_name, album_title, historical_year, label_val, personnel_str, mb_artist_id, seeds, now):
    cursor.execute("SELECT 1 FROM library_master WHERE mf_id = ?", (mf_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE library_master SET last_updated=?, mb_album_id=?, original_year=?, label=?, personnel=?, date_audit_status=1 WHERE mf_id=?", 
                       (now, seeds['mb_ids'].get('album'), historical_year, label_val, personnel_str, mf_id))
    else:
        cursor.execute("INSERT INTO library_master (mf_id, mf_artist_id, artist_name, album_title, mb_album_id, original_year, label, personnel, is_compilation, last_updated, date_audit_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                       (mf_id, mf_artist_id, artist_name, album_title, seeds['mb_ids'].get('album'), historical_year, label_val, personnel_str, 0, now, 1))
    
    cursor.execute("SELECT 1 FROM library_artist WHERE mf_artist_id = ?", (mf_artist_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE library_artist SET artist_name=?, last_updated=?, mb_artist_id=? WHERE mf_artist_id=?", 
                       (artist_name, now, mb_artist_id, mf_artist_id))
    else:
        cursor.execute("INSERT INTO library_artist (mf_artist_id, mb_artist_id, artist_name, last_updated) VALUES (?, ?, ?, ?)", 
                       (mf_artist_id, mb_artist_id, artist_name, now))

def _write_physical_tags(file_path, data, album_reissue_year):
    tags = ID3(str(file_path))
    
    # Remove existing comment frames and add the new one with a blank descriptor
    tags.delall("COMM")
    tags.add(COMM(encoding=3, lang='eng', desc='', text=[SIGNATURE]))
    
    tags.add(TIT2(encoding=3, text=[data.get('title')]))
    tags.add(TYER(encoding=3, text=[str(album_reissue_year)]))
    tags.add(TORY(encoding=3, text=[str(data.get('original_year', 'Unknown'))]))
    tags.add(TCON(encoding=3, text=[data.get('parent', 'Unknown')]))
    tags.add(TMOO(encoding=3, text=[data.get('mood', 'Unknown')]))
    tags.add(TBPM(encoding=3, text=[str(data.get('bpm', 0))]))
    tags.add(TKEY(encoding=3, text=[data.get('key', '??')]))
    
    tags.add(TXXX(encoding=3, desc='Sub-Genre', text=[data.get('sub', 'Unknown')]))
    tags.add(TXXX(encoding=3, desc='Intensity', text=[str(data.get('intensity', 1))]))
    tags.add(TXXX(encoding=3, desc='Country', text=[data.get('country', 'Unknown')]))
    
    if data.get('personnel'):
        tags.add(TXXX(encoding=3, desc='Personnel', text=["; ".join(data['personnel'])]))
    if data.get('label'):
        tags.add(TPUB(encoding=3, text=[data['label']]))
    if data.get('acoustid') and data['acoustid'] != 'None':
        tags.add(TXXX(encoding=3, desc='Acoustid Id', text=[data['acoustid']]))
        
    tags.save(str(file_path), v2_version=3)

def _generate_mf_hashes(artist, album):
    a, b = str(artist).strip().lower(), str(album).strip().lower()
    mf_artist_id = hashlib.sha256(a.encode('utf-8')).hexdigest()
    mf_id = hashlib.sha256(f"{a}|{b}".encode('utf-8')).hexdigest()
    return mf_id, mf_artist_id

def _update_audit_trail(root, seeds, results, label, personnel, db_sync, historical_year):
    manifest_path = root / "manifest.json"
    log_path = root / "MetaForge.log"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    primary = results[0][1]

    manifest = {}
    if manifest_path.exists():
        try: manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except: pass
    
    manifest.update({
        "original_year_seed": historical_year,
        "release_year": seeds.get('release_year', 'Unknown'),
        "tagging_status": "REMEDIATED",
        "last_forensic_audit": now,
        "historical_rescue_label": label,
        "personnel_count": len(personnel),
        "forensic_profile": {
            "bpm": primary.get('bpm', 0), "musical_key": primary.get('key', '??'),
            "mood": primary.get('mood', 'Unknown'), "intensity": primary.get('intensity', 1),
            "acoustid_id": primary.get('acoustid', 'None')
        },
        "last_tool_run": "intelli-tagger"
    })
    try: manifest_path.write_text(json.dumps(manifest, indent=4), encoding='utf-8')
    except: pass

    log_entry = (
        f"\n{'='*60}\nMETAFORGE AUDIT LOG | {now}\nMetaForge Process: Intelli-Tagger\n{'-'*60}\n"
        f"WORKING_DIRECTORY    - {root}\nRELEASE_YEAR (TYER)  - {seeds.get('release_year')}\n"
        f"ORIGINAL_YEAR (TORY) - {historical_year}\nGENRE_CLASSIFICATION - {primary.get('parent')} // {primary.get('sub')}\n"
        f"FORENSIC_BPM         - {primary.get('bpm')}\nFORENSIC_KEY         - {primary.get('key')}\n"
        f"FORENSIC_MOOD        - {primary.get('mood')} (Intensity: {primary.get('intensity')})\n"
        f"HISTORICAL_LABEL     - {label}\nPERSONNEL_RECOVERY   - {len(personnel)} entries\n"
        f"GRAPH_EDGES_EMITTED  - {len(personnel) if db_sync else 0}\n"
        f"DATABASE_SYNC        - {'SUCCESS' if db_sync else 'DISABLED'}\n{'='*60}\n"
    )
    try:
        with open(log_path, 'a', encoding='utf-8') as f: f.write(log_entry)
    except: pass

# --- END OF FILE commit_engine.py ---