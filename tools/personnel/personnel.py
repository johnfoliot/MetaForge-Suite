# --- START OF FILE personnel.py ---
# ======================================================================
# MetaForge Studio: Personnel Scout - Processing Engine (V.1.2.2)
# Role: Scrapes Wikipedia wikitext and parses Name-Role relationships.
# Physical Location: \tools\personnel\personnel.py
# Build 1.2.2: Fixed extraction scoping and stabilized character preservation.
# ======================================================================
import requests
import re
import json
import hashlib
import traceback
import datetime
from pathlib import Path
from flask import jsonify, request
from common import db_engine
from tools.personnel.edge_normalizer import normalize_personnel

USER_AGENT = "MetaForgeStudio/1.0 (contact: forensic-dev@metaforge.studio)"
API_URL = "https://en.wikipedia.org/w/api.php"

def run_logic(action, tools_dir, env_path):
    try:
        if action == "get_folder_context": return _get_folder_context()
        if action == "search": return _search()
        if action == "fetch_content": return _fetch_content()
        if action == "commit": return _commit()
        return jsonify({"status": "error", "message": f"Action '{action}' unrecognized."}), 404
    except Exception:
        print(f"🔥 Personnel Scout Hub Error [{action}]:\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Internal processing error."}), 500

def _get_folder_context():
    data = request.json
    local_path = data.get('local_path')
    if not local_path: return jsonify({"status": "error", "message": "No path provided."})
    manifest_file = Path(local_path) / "manifest.json"
    if manifest_file.exists():
        try:
            m_data = json.loads(manifest_file.read_text(encoding='utf-8'))
            return jsonify({
                "status": "success",
                "context": {
                    "artist_seed": m_data.get("artist_seed", ""),
                    "album_seed": m_data.get("album_seed", ""),
                    "release_year": m_data.get("release_year", "")
                }
            })
        except Exception as e:
            return jsonify({"status": "error", "message": f"Manifest read error: {str(e)}"})
    return jsonify({"status": "error", "message": "Manifest not found."})

def _search():
    data = request.json
    artist, album, year = data.get('artist', ''), data.get('album', ''), data.get('year', '')
    search_query = f'"{album}" {artist} album'
    if year: search_query += f" {year}"
    params = {"action": "query", "list": "search", "srsearch": search_query, "format": "json", "srlimit": 10}
    res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT})
    res.raise_for_status()
    raw_results = res.json().get('query', {}).get('search', [])
    guarded_results = [{"title": r['title'], "pageid": r['pageid'], "score": 50 if album.lower() in r['title'].lower() else 0} for r in raw_results]
    guarded_results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({"status": "success", "results": guarded_results})

def _fetch_content():
    data = request.json
    title = data.get('title')
    params = {"action": "query", "prop": "revisions", "titles": title, "rvprop": "content", "rvslots": "main", "format": "json"}
    res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT})
    res.raise_for_status()
    data = res.json()
    page_id = list(data['query']['pages'].keys())[0]
    if page_id == "-1": return jsonify({"status": "error", "message": "Page unavailable."})
    
    full_text = data['query']['pages'][page_id]['revisions'][0]['slots']['main']['*']
    combined_content = []
    for header in ["Personnel", "Musicians", "Credits"]:
        match = re.search(rf"(?i)==\s*{header}\s*==\n(.*?)(?=\n==[^=]|$)", full_text, re.DOTALL)
        if match and len(match.group(1).strip()) > 20: combined_content.append(match.group(1).strip())

    if not combined_content: return jsonify({"status": "error", "message": "No credit sections identified."})

    full_extracted_text = "\n".join(combined_content)
    
    text = re.sub(r'\{\{[^|}]+\|([^}]+)\}\}', r'\1', full_extracted_text) 
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)      
    text = re.sub(r'<ref.*?>.*?</ref>', '', text, flags=re.DOTALL)     
    text = re.sub(r"'{3,}", "", text) 
    text = re.sub(r"''", "", text)

    candidates = []
    for line in text.split('\n'):
        line = line.strip().strip('|').strip()
        if not line or any(x in line.lower() for x in ['colwidth=', 'style=', 'class=', 'title=']): continue
        line = re.sub(r'^[*#]+\s*', '', line)
        parts = re.split(r" – | - |:", line)
        if len(parts) >= 2: candidates.append({"name": parts[0].strip(), "role": parts[1].strip()})

    return jsonify({"status": "success", "raw_text": text, "candidates": candidates})

def _commit():
    data = request.json
    artist, album, personnel = data.get('artist'), data.get('album'), data.get('personnel', [])
    res = db_engine.execute_query("SELECT mf_id FROM library_master WHERE album_title LIKE ? AND artist_name LIKE ? LIMIT 1", (f"%{album}%", f"%{artist}%"))
    if not res: return jsonify({"status": "error", "message": "Album ID resolution failed."})
    
    mf_id = res[0]['mf_id']
    count = 0
    now = datetime.datetime.now().isoformat()
    
    for p in personnel:
        name, role_string = p.get('name', '').strip(), p.get('role', '').strip()
        if not name or not role_string: continue
        
        tid = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()
        db_engine.execute_query("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name) VALUES (?, ?)", (tid, name), commit=True)
        
        atomic_edges = normalize_personnel(role_string)
        
        for edge in atomic_edges:
            db_engine.execute_query("""
                INSERT INTO edges (
                    source_type, source_id, target_type, target_id, 
                    relation_type, role, weight, confidence, provenance, 
                    evidence_scope, evidence_detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "album", mf_id, "artist", tid, 
                edge['relation_type'], edge['role'], edge['weight'], 
                edge['confidence'], "Wikipedia", edge['evidence_scope'], 
                edge['evidence_detail'], now
            ), commit=True)
            count += 1
            
    return jsonify({"status": "success", "count": count}), 200
# --- END OF FILE personnel.py ---