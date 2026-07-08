# --- START OF FILE personnel.py ---
# ======================================================================
# MetaForge Studio: Personnel Scout - Processing Engine (Personnel Engine v2)
# Role: 3-tier waterfall (MusicBrainz + Discogs merged -> Wikipedia
# fallback -> AllMusic semi-manual last resort) resolving album/track
# personnel credits into the `edges` graph.
# Physical Location: \tools\personnel\personnel.py
# ======================================================================
import requests
import re
import json
import sys
import hashlib
import traceback
from pathlib import Path
from flask import jsonify, request
from common import db_engine
from tools.personnel.edge_normalizer import normalize_personnel
from tools.personnel import edge_store
from tools.personnel import mb_personnel_engine
from tools.personnel import discogs_personnel_engine

# MBResolutionEngine lives under Intelli-Tagger's own engines/ folder --
# only on sys.path while Intelli-Tagger's run_logic() is executing, so it
# must be added explicitly here too (same reasoning as
# discogs_personnel_engine.py's own bootstrap).
_IT_ENGINES_DIR = Path(__file__).resolve().parents[2] / "tools" / "intelli-tagger" / "engines"
if str(_IT_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_IT_ENGINES_DIR))
from mb_resolution_engine import MBResolutionEngine  # noqa: E402

USER_AGENT = "MetaForgeStudio/1.0 (contact: forensic-dev@metaforge.studio)"
API_URL = "https://en.wikipedia.org/w/api.php"

# Below this many distinct credited names, the merged MB+Discogs result
# counts as "thin" and triggers the automatic Wikipedia fallback tier.
# Deliberately low and simple -- personnel data is "useful, not gospel"
# (see project_personnel_engine_v2 design), not worth a more elaborate
# heuristic.
THIN_THRESHOLD = 2


def run_logic(action, tools_dir, env_path):
    try:
        if action == "get_folder_context": return _get_folder_context()
        if action == "resolve_waterfall": return _resolve_waterfall()
        if action == "search": return _search()
        if action == "fetch_content": return _fetch_content()
        if action == "parse_allmusic_html": return _parse_allmusic_html()
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


# ==========================================================================
# TIER 1+2: MUSICBRAINZ + DISCOGS (MERGED, AUTOMATIC)
# ==========================================================================

def _resolve_waterfall():
    """
    Runs automatically when Personnel opens on an album (triggered by the
    frontend right after folder-context loads, mirroring the existing
    "Optional: Add Personnel" hand-off from Intelli-Tagger). Merges MB +
    Discogs candidates (don't stop at first -- coverage is complementary,
    per the original design), then auto-falls-back to Wikipedia only if
    the merged result is still thin. Returns a preview list for the user
    to review/edit before committing -- nothing is written to the
    database here.
    """
    data = request.json
    local_path = data.get('local_path', '')
    artist = data.get('artist', '')
    album = data.get('album', '')

    manifest = {}
    if local_path:
        manifest_file = Path(local_path) / "manifest.json"
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            except Exception:
                manifest = {}

    mb_track_map = manifest.get('mb_track_map', []) or []
    mb_preseed = manifest.get('mb_artist_rels_by_recording')  # dict or None if absent
    discogs_preseed = manifest.get('discogs_extraartists')    # dict or None if absent

    all_edges = []

    if mb_track_map:
        mb = MBResolutionEngine()
        work_cache = {}
        for idx, entry in enumerate(mb_track_map, 1):
            recording_id = entry.get('mb_recording_id')
            if not recording_id or recording_id in ("None", "Unknown", ""):
                continue
            preseeded = mb_preseed.get(recording_id) if mb_preseed is not None else None
            track_number = entry.get('position', idx)
            all_edges.extend(mb_personnel_engine.resolve_track_personnel(
                mb, recording_id, track_number, preseeded, work_cache
            ))

    all_edges.extend(discogs_personnel_engine.resolve_album_personnel(artist, album, discogs_preseed))

    distinct_names = {e['name'].strip().lower() for e in all_edges if e.get('name')}
    thin = len(distinct_names) < THIN_THRESHOLD

    wiki_candidates = []
    if thin and artist and album:
        wiki_candidates = _auto_wikipedia_personnel(artist, album)

    candidates = [
        {
            "name": e['name'], "role": e['role'], "relation_type": e['relation_type'],
            "confidence": e['confidence'], "provenance": e['provenance'],
            "evidence_scope": e.get('evidence_scope'), "evidence_detail": e.get('evidence_detail'),
        }
        for e in all_edges
    ] + [
        {"name": c['name'], "role": c['role'], "provenance": "Wikipedia"}
        for c in wiki_candidates
    ]

    return jsonify({"status": "success", "candidates": candidates, "thin": thin})


# ==========================================================================
# TIER 3: WIKIPEDIA (AUTOMATIC FALLBACK, AND STILL MANUALLY SEARCHABLE)
# ==========================================================================

def _extract_credits_from_wikitext(full_text):
    """
    Shared by both the manual search-and-pick flow (_fetch_content, below)
    and the automatic fallback (_auto_wikipedia_personnel) -- same
    regex-based Personnel/Musicians/Credits section extraction either way.
    Returns (raw_text, candidates) or (None, []) if no credit section
    was found.
    """
    combined_content = []
    for header in ["Personnel", "Musicians", "Credits"]:
        match = re.search(rf"(?i)==\s*{header}\s*==\n(.*?)(?=\n==[^=]|$)", full_text, re.DOTALL)
        if match and len(match.group(1).strip()) > 20: combined_content.append(match.group(1).strip())

    if not combined_content: return None, []

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

    return text, candidates


def _auto_wikipedia_personnel(artist, album):
    """
    Automatic tier-3 fallback: searches Wikipedia, takes the top-scored
    result (same scoring _search() already uses), fetches and extracts --
    no human pick required, since this only runs when MB+Discogs were
    already thin and the alternative is nothing at all. Never raises;
    returns an empty list on any failure.
    """
    try:
        search_query = f'"{album}" {artist} album'
        params = {"action": "query", "list": "search", "srsearch": search_query, "format": "json", "srlimit": 5}
        res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
        res.raise_for_status()
        raw_results = res.json().get('query', {}).get('search', [])
        scored = [r for r in raw_results if album.lower() in r['title'].lower()]
        if not scored:
            return []
        title = scored[0]['title']

        params = {"action": "query", "prop": "revisions", "titles": title, "rvprop": "content", "rvslots": "main", "format": "json"}
        res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
        res.raise_for_status()
        page_data = res.json()
        page_id = list(page_data['query']['pages'].keys())[0]
        if page_id == "-1":
            return []

        full_text = page_data['query']['pages'][page_id]['revisions'][0]['slots']['main']['*']
        _, candidates = _extract_credits_from_wikitext(full_text)
        return candidates
    except Exception:
        return []


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
    text, candidates = _extract_credits_from_wikitext(full_text)

    if text is None: return jsonify({"status": "error", "message": "No credit sections identified."})

    return jsonify({"status": "success", "raw_text": text, "candidates": candidates})


# ==========================================================================
# TIER 4: ALLMUSIC (SEMI-MANUAL, TRUE LAST RESORT)
# ==========================================================================

def _parse_allmusic_html():
    """
    Parses AllMusic's #credits table HTML, pasted by the user into
    Personnel's own modal (the fetch itself stays 100% human-driven --
    see project_mb_contribution_tool memory's ToS research; this endpoint
    only ever receives HTML the user already copied in their own browser,
    it never fetches anything from AllMusic itself). Same regex
    previously living in tools/personnel/temp/parse_credits.py, ported
    from a stdin-reading CLI script into a route.
    """
    data = request.json
    html_content = data.get('html', '')

    pattern = r'<span class="artist">\s*<a[^>]*>(.*?)</a>\s*</span>\s*<span class="artistCredits">(.*?)</span>'
    matches = re.findall(pattern, html_content, re.DOTALL)

    candidates = []
    for name, role in matches:
        clean_name = re.sub(r'<[^>]+>', '', name).strip()
        clean_role = re.sub(r'<[^>]+>', '', role).strip()
        if clean_name and clean_role:
            candidates.append({"name": clean_name, "role": clean_role})

    if not candidates:
        return jsonify({"status": "error", "message": "No recognizable credits table found in the pasted content."})

    return jsonify({"status": "success", "candidates": candidates})


# ==========================================================================
# COMMIT (SHARED BY EVERY TIER)
# ==========================================================================

def _commit():
    """
    Shared commit path for every source. Rows already carrying a
    relation_type (MB/Discogs -- pre-classified, structured data) are
    written as-is via edge_store.upsert_edge(), no re-classification.
    Rows with only a free-text role (Wikipedia/AllMusic/manual entries)
    go through normalize_personnel()/classify_role() first, same as
    always. Either way, upsert_edge() handles dedup -- a re-commit of the
    same fact updates the existing row instead of duplicating it.
    """
    data = request.json
    artist, album, personnel = data.get('artist'), data.get('album'), data.get('personnel', [])
    res = db_engine.execute_query("SELECT mf_id FROM library_master WHERE album_title LIKE ? AND artist_name LIKE ? LIMIT 1", (f"%{album}%", f"%{artist}%"))
    if not res: return jsonify({"status": "error", "message": "Album ID resolution failed."})

    mf_id = res[0]['mf_id']
    count = 0

    for p in personnel:
        name = (p.get('name') or '').strip()
        if not name: continue

        tid = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()
        db_engine.execute_query("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name) VALUES (?, ?)", (tid, name), commit=True)

        if p.get('relation_type'):
            role = (p.get('role') or '').strip()
            if not role: continue
            edge_store.upsert_edge(
                source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
                relation_type=p['relation_type'], role=role,
                confidence=p.get('confidence', 0.9), provenance=p.get('provenance', 'MetaForge'),
                evidence_scope=p.get('evidence_scope'), evidence_detail=p.get('evidence_detail'),
            )
            count += 1
        else:
            role_string = (p.get('role') or '').strip()
            if not role_string: continue
            provenance = p.get('provenance', 'Wikipedia')

            for edge in normalize_personnel(role_string):
                edge_store.upsert_edge(
                    source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
                    relation_type=edge['relation_type'], role=edge['role'],
                    confidence=edge['confidence'], provenance=provenance,
                    evidence_scope=edge['evidence_scope'], evidence_detail=edge['evidence_detail'],
                    weight=edge['weight']
                )
                count += 1

    return jsonify({"status": "success", "count": count}), 200
# --- END OF FILE personnel.py ---
