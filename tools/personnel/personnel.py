# --- START OF FILE personnel.py ---
# ======================================================================
# MetaForge Studio: Personnel Scout - Processing Engine (Personnel Engine v2)
# Role: 4-tier waterfall (MusicBrainz + Discogs merged -> Wikipedia
# fallback -> AI Web Search fallback -> AllMusic semi-manual last resort)
# resolving album/track personnel credits into the `edges` graph.
# Physical Location: \tools\personnel\personnel.py
# ======================================================================
import requests
import re
import json
import sys
import hashlib
import traceback
from datetime import datetime
from pathlib import Path
from flask import jsonify, request
from common import db_engine, config_handler
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

# Evidence-collection log for a future MB contribution tool (see
# project_mb_contribution_tool memory) -- the submission tool itself is
# still deferred (MB relationship-editor seeding is unconfirmed for
# existing recordings), but there's no reason to let this evidence
# disappear in the meantime, and it lets it be visually spot-checked
# before that tool exists. One JSON line per candidate: a personnel
# credit committed from a non-MusicBrainz source for a person/relation
# MusicBrainz's own data doesn't yet have on this album.
MB_CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "personnel_correction_candidates.jsonl"

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
    the merged result is still thin, and AI Web Search only if it's
    STILL thin after that. Returns a preview list for the user
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

    thin = _is_thin(all_edges)

    wiki_edges = []
    if thin and artist and album:
        wiki_edges = _classify_free_text_candidates(_auto_wikipedia_personnel(artist, album), "Wikipedia")
        thin = _is_thin(all_edges + wiki_edges)

    ai_edges = []
    if thin and artist and album:
        ai_edges = _classify_free_text_candidates(_auto_ai_personnel(artist, album), "AI Web Search")

    candidates = [
        {
            "name": e['name'], "role": e['role'], "relation_type": e['relation_type'],
            "confidence": e['confidence'], "provenance": e['provenance'],
            "evidence_scope": e.get('evidence_scope'), "evidence_detail": e.get('evidence_detail'),
        }
        for e in all_edges + wiki_edges + ai_edges
    ]

    return jsonify({"status": "success", "candidates": candidates, "thin": thin})


def _is_thin(edges):
    """
    "Thin" counts only musically-relevant credits (anything classified
    to a real RelationType, not the ASSOCIATED_WITH catch-all) -- a
    photographer and a producer used to count identically toward "we
    have enough data", which meant an album with one real credit and two
    package-art credits looked fully resolved. Junk roles (photography,
    album design, etc.) never even reach this point now -- they're
    filtered out entirely in edge_normalizer.is_junk_role() before
    classification -- but a genuinely unclassified-but-real role could
    still land in ASSOCIATED_WITH, so that bucket still doesn't count as
    "answered" either.
    """
    valuable_names = {
        e['name'].strip().lower() for e in edges
        if e.get('name') and e.get('relation_type') != 'ASSOCIATED_WITH'
    }
    return len(valuable_names) < THIN_THRESHOLD


def _classify_free_text_candidates(candidates, provenance):
    """
    Runs raw {name, role} candidates (Wikipedia/AI, which return free
    text, not pre-classified data like MB/Discogs) through the same
    normalize_personnel() atomization/classification/junk-filter every
    other source uses -- so junk is excluded from the PREVIEW too, not
    just eventually at commit time, and so _is_thin() can accurately
    judge whether these results were actually valuable. One raw
    candidate can expand into zero (fully junk), one, or several atomic
    edges (a multi-role credit like "Producer, Photography").
    """
    edges = []
    for c in candidates:
        name, role = c.get('name'), c.get('role')
        if not name or not role:
            continue
        for atom in normalize_personnel(role):
            edges.append({
                "name": name, "role": atom['role'], "relation_type": atom['relation_type'],
                "confidence": atom['confidence'], "provenance": provenance,
                "evidence_scope": atom['evidence_scope'], "evidence_detail": atom['evidence_detail'],
            })
    return edges


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


# ==========================================================================
# TIER 4: AI WEB SEARCH (AUTOMATIC, ONLY IF STILL THIN AFTER WIKIPEDIA)
# ==========================================================================

def _auto_ai_personnel(artist, album):
    """
    Automatic last-resort AI tier, mirroring the original-year waterfall's
    AI Web Search tier -- only reached when MB+Discogs+Wikipedia together
    are still thin. Deliberately source-agnostic (see
    ai_engine.resolve_personnel_ai's own docstring for why AllMusic is
    never named in the prompt). Never raises; returns an empty list on
    any failure.
    """
    try:
        import ai_engine
        return ai_engine.resolve_personnel_ai(artist, album)
    except Exception:
        return []


def _search():
    data = request.json
    artist, album, year = data.get('artist', ''), data.get('album', ''), data.get('year', '')
    search_query = f'"{album}" {artist} album'
    if year: search_query += f" {year}"
    params = {"action": "query", "list": "search", "srsearch": search_query, "format": "json", "srlimit": 10}
    # Bounded, matching the pattern already used in the automatic
    # Wikipedia tier -- this call previously had no timeout at all, so a
    # slow/unreachable Wikipedia response would hang indefinitely with
    # zero feedback (John, 2026-07-08: "hangs... even after 60+ seconds").
    res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
    res.raise_for_status()
    raw_results = res.json().get('query', {}).get('search', [])
    guarded_results = [{"title": r['title'], "pageid": r['pageid'], "score": 50 if album.lower() in r['title'].lower() else 0} for r in raw_results]
    guarded_results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify({"status": "success", "results": guarded_results})

def _fetch_content():
    data = request.json
    title = data.get('title')
    params = {"action": "query", "prop": "revisions", "titles": title, "rvprop": "content", "rvslots": "main", "format": "json"}
    res = requests.get(API_URL, params=params, headers={'User-Agent': USER_AGENT}, timeout=10)
    res.raise_for_status()
    data = res.json()
    page_id = list(data['query']['pages'].keys())[0]
    if page_id == "-1": return jsonify({"status": "error", "message": "Page unavailable."})

    full_text = data['query']['pages'][page_id]['revisions'][0]['slots']['main']['*']
    text, raw_candidates = _extract_credits_from_wikitext(full_text)

    if text is None: return jsonify({"status": "error", "message": "No credit sections identified."})

    # Junk-filtered/pre-classified here too, same as the automatic tier
    # and the AllMusic paste path -- package credits never reach the
    # review table at all, regardless of which source found them.
    candidates = _classify_free_text_candidates(raw_candidates, "Wikipedia")

    return jsonify({"status": "success", "raw_text": text, "candidates": candidates})


# ==========================================================================
# TIER 4: ALLMUSIC (SEMI-MANUAL, TRUE LAST RESORT)
# ==========================================================================

def _extract_allmusic_credits(content):
    """
    Runs the AllMusic credits-table regex against a single string. Same
    regex previously living in tools/personnel/temp/parse_credits.py,
    ported from a stdin-reading CLI script into a route. Verified
    2026-07-08 against a real captured AllMusic credits table (21/21
    entries parsed correctly) -- the regex itself was never the problem,
    see _parse_allmusic_html's docstring for what actually was.
    """
    if not content:
        return []

    pattern = r'<span class="artist">\s*<a[^>]*>(.*?)</a>\s*</span>\s*<span class="artistCredits">(.*?)</span>'
    matches = re.findall(pattern, content, re.DOTALL)

    candidates = []
    for name, role in matches:
        clean_name = re.sub(r'<[^>]+>', '', name).strip()
        clean_role = re.sub(r'<[^>]+>', '', role).strip()
        if clean_name and clean_role:
            candidates.append({"name": clean_name, "role": clean_role})
    return candidates


def _parse_allmusic_html():
    """
    Parses AllMusic's #credits table HTML, pasted by the user into
    Personnel's own modal (the fetch itself stays 100% human-driven --
    see project_mb_contribution_tool memory's ToS research; this endpoint
    only ever receives HTML the user already copied in their own browser,
    it never fetches anything from AllMusic itself).

    Tries the html clipboard field first, falls back to plain -- a
    normal Ctrl+C on rendered text has the real markup in text/html, but
    copying from a "View Selection Source" page (John, 2026-07-08) is
    different: that page displays markup AS TEXT, so ITS OWN text/html
    is the browser's syntax-highlighting wrapper around that display,
    not the original page's markup. The literal source text lives in
    text/plain for that path instead. Confirmed live: the regex itself
    correctly parses a real captured AllMusic sample (21/21 entries) --
    the bug was reading the wrong clipboard field for the view-source
    case, not the parser.
    """
    data = request.json
    raw_candidates = _extract_allmusic_credits(data.get('html', ''))
    if not raw_candidates:
        raw_candidates = _extract_allmusic_credits(data.get('plain', ''))

    if not raw_candidates:
        return jsonify({"status": "error", "message": "No recognizable credits table found in the pasted content."})

    # Junk-filtered/pre-classified here too (not just at eventual commit)
    # so package credits (photography, design, etc.) never show up in
    # the review table for John to have to notice and delete by hand.
    candidates = _classify_free_text_candidates(raw_candidates, "AllMusic")

    if not candidates:
        return jsonify({"status": "error", "message": "Found a credits table, but every entry was a non-musical package credit (photography, design, etc.) -- nothing to add."})

    return jsonify({"status": "success", "candidates": candidates})


# ==========================================================================
# COMMIT (SHARED BY EVERY TIER)
# ==========================================================================

def _log_mb_correction_candidate(mf_id, artist, album, name, target_id, relation_type, role,
                                  provenance, confidence, evidence_scope, evidence_detail):
    """Appends one JSONL entry to MB_CANDIDATE_LOG. Never raises -- a
    logging failure must never break a real commit."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "mf_id": mf_id, "artist": artist, "album": album,
        "name": name, "target_id": target_id,
        "relation_type": relation_type, "role": role,
        "provenance": provenance, "confidence": confidence,
        "evidence_scope": evidence_scope, "evidence_detail": evidence_detail,
    }
    try:
        MB_CANDIDATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(MB_CANDIDATE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as ex:
        print(f"⚠️ MB correction candidate log write failed: {ex}")


def _commit():
    """
    Shared commit path for every source. Rows already carrying a
    relation_type (MB/Discogs -- pre-classified, structured data) are
    written as-is via edge_store.upsert_edge(), no re-classification.
    Rows with only a free-text role (Wikipedia/AllMusic/manual entries)
    go through normalize_personnel()/classify_role() first, same as
    always. Either way, upsert_edge() handles dedup -- a re-commit of the
    same fact updates the existing row instead of duplicating it.

    Also logs a candidate MB correction (see MB_CANDIDATE_LOG above) for
    any committed edge whose provenance isn't MusicBrainz AND for which
    no MusicBrainz-provenance edge already exists for the same
    (target, relation_type) on this album -- i.e. something MB's own
    data doesn't have yet. The check is a single query per commit, not
    per row.
    """
    data = request.json
    artist, album, personnel = data.get('artist'), data.get('album'), data.get('personnel', [])
    res = db_engine.execute_query("SELECT mf_id FROM library_master WHERE album_title LIKE ? AND artist_name LIKE ? LIMIT 1", (f"%{album}%", f"%{artist}%"))
    if not res: return jsonify({"status": "error", "message": "Album ID resolution failed."})

    mf_id = res[0]['mf_id']
    count = 0

    mb_rows = db_engine.execute_query(
        "SELECT target_id, relation_type FROM edges WHERE source_id=? AND source_type='album' AND provenance='MusicBrainz'",
        (mf_id,)
    )
    mb_known = {(r['target_id'], r['relation_type']) for r in mb_rows} if mb_rows else set()

    def _maybe_log_candidate(name, tid, relation_type, role, provenance, confidence, evidence_scope, evidence_detail):
        if provenance != "MusicBrainz" and (tid, relation_type) not in mb_known:
            _log_mb_correction_candidate(
                mf_id, artist, album, name, tid, relation_type, role,
                provenance, confidence, evidence_scope, evidence_detail
            )

    for p in personnel:
        name = (p.get('name') or '').strip()
        if not name: continue

        tid = hashlib.sha256(name.lower().encode('utf-8')).hexdigest()
        db_engine.execute_query("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name) VALUES (?, ?)", (tid, name), commit=True)

        if p.get('relation_type'):
            role = (p.get('role') or '').strip()
            if not role: continue
            confidence = p.get('confidence', 0.9)
            provenance = p.get('provenance', 'MetaForge')
            evidence_scope = p.get('evidence_scope')
            evidence_detail = p.get('evidence_detail')
            edge_store.upsert_edge(
                source_type="album", source_id=mf_id, target_type="artist", target_id=tid,
                relation_type=p['relation_type'], role=role,
                confidence=confidence, provenance=provenance,
                evidence_scope=evidence_scope, evidence_detail=evidence_detail,
            )
            _maybe_log_candidate(name, tid, p['relation_type'], role, provenance, confidence, evidence_scope, evidence_detail)
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
                _maybe_log_candidate(name, tid, edge['relation_type'], edge['role'], provenance,
                                      edge['confidence'], edge['evidence_scope'], edge['evidence_detail'])
                count += 1

    return jsonify({"status": "success", "count": count}), 200
# --- END OF FILE personnel.py ---
