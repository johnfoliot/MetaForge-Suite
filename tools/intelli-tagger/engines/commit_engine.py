# --- START OF FILE commit_engine.py ---
# ======================================================================
# MetaForge Engine: Relational & Physical Commit (Phase 7)
# Role: Finalizes bitstream metadata.
# Build 1.6.0: REMEDIATED: Removed Integrity Guard. Dumb Writer only.
# Physical Location: \tools\intelli-tagger\engines\commit_engine.py
# ======================================================================
import sqlite3
import hashlib
import requests
from datetime import datetime
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TCON, TMOO, TBPM, TKEY, TXXX, TYER, TORY, TPUB, COMM
from common import config_handler

DB_PATH = config_handler.DB_PATH
SIGNATURE = "Remediation and metadata by MetaForge Studio - the music management tool for Serious Collectors."
MB_BASE_URL = "https://musicbrainz.org/ws/2"

def execute_commit(root_path, track_results, db_write=True, manifest_seeds=None):
    yield '<div class="it-log-entry it-val-gold">Writing to the MetaForge database...</div>'

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
        except Exception: db_write = False

    for idx, (f_path, data) in enumerate(track_results, 1):
        try:
            # DUMB WRITER: No remediation, no validation. Write what we are given.
            _write_physical_tags(f_path, data, album_reissue_year)

            if db_write and conn:
                cursor.execute("INSERT INTO tracks (file_path, mf_id, mf_artist_id, mb_artist_id, mb_track_id, acoustid, title, genre, sub_genre, original_year, bpm, key_val, mood, intensity, is_remediated, last_updated, length) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                    (str(f_path.resolve()).replace('\\', '/'), mf_id, mf_artist_id, current_mb_artist_id, data.get('mb_track_id', 'None'), data.get('acoustid', 'None'), data.get('title'), data.get('parent', 'Unknown'), data.get('sub', 'Unknown'), data.get('original_year', 'Unknown'), data.get('bpm', 0), data.get('key', '??'), data.get('mood', 'Unknown'), data.get('intensity', 1), 1, now, int(data.get('duration', 0))))
                success_count += 1
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">🔥 Commit Error on {f_path.name}: {str(e)}</div>'

    if db_write and conn:
        conn.commit(); conn.close()
    yield f'<div class="it-log-entry">✅ {success_count} tracks synchronized.</div>'

def _write_physical_tags(file_path, data, album_reissue_year):
    tags = ID3(str(file_path))
    tags.delall("COMM"); tags.add(COMM(encoding=3, lang='eng', desc='', text=[SIGNATURE]))
    
    # Standard Fields
    tags.add(TIT2(encoding=3, text=[data.get('title', file_path.stem)]))
    tags.add(TYER(encoding=3, text=[str(album_reissue_year)]))
    tags.add(TORY(encoding=3, text=[str(data.get('original_year', 'Unknown'))]))
    tags.add(TCON(encoding=3, text=[data.get('parent', 'Unknown')]))
    tags.add(TMOO(encoding=3, text=[data.get('mood', 'Unknown')]))
    tags.add(TBPM(encoding=3, text=[str(data.get('bpm', 0))]))
    tags.add(TKEY(encoding=3, text=[data.get('key', '??')]))
    
    # Metadata Fields
    tags.delall("TXXX") # Clear old TXXX to ensure clean write
    tags.add(TXXX(encoding=3, desc='Sub-Genre', text=[data.get('sub', 'Unknown')]))
    tags.add(TXXX(encoding=3, desc='Intensity', text=[str(data.get('intensity', 1))]))
    tags.add(TXXX(encoding=3, desc='Country', text=[data.get('country', 'Unknown')]))
    
    # Mood_Modifier: Dumb write of whatever the Tagger passed in
    mods = data.get('mood_modifiers', [])
    if mods:
        tags.add(TXXX(encoding=3, desc='Mood_Modifier', text=[", ".join(mods)]))
    
    tags.save(str(file_path), v2_version=3)

def _generate_mf_hashes(artist, album):
    a, b = str(artist).strip().lower(), str(album).strip().lower()
    return hashlib.sha256(f"{a}|{b}".encode('utf-8')).hexdigest(), hashlib.sha256(a.encode('utf-8')).hexdigest()
# --- END OF FILE commit_engine.py ---