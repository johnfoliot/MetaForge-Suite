# --- START OF FILE biography.py ---
# ======================================================================
# MetaForge Tool: Biography Builder Logic
# File Location: \tools\biography\biography.py
# v2 (2026-11-15, John's answers):
#  - Bios are written with Gemini + Google Search grounding (like Personnel's
#    AI tier) and the sources are returned; a bio with no web sources is
#    flagged as unverified instead of passing silently.
#  - The portrait is a DRAFT until Save (1.x wrote it straight over the
#    artist's photo the moment Get Biography / Browse ran, even when the bio
#    was then discarded).
#  - Discogs search is properly encoded (an "&" in a name truncated it) and
#    prefers an exact name match; the match is reported so you can check it.
#  - folder_artist: the album's artist from manifest.json, so arriving from
#    Intelli-Tagger / Album Personnel loads the right artist.
# ======================================================================
import hashlib
import json
import os
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageOps
from flask import request, jsonify, send_file
from google import genai
from google.genai import types
from common import config_handler, db_engine


def get_md5_hash(artist_name):
    return hashlib.md5(artist_name.lower().encode('utf-8')).hexdigest()


def _photos_dir():
    d = config_handler.PROJECT_ROOT / "photos"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_hashed_path(artist_name):
    return _photos_dir() / f"{get_md5_hash(artist_name)}.jpg"


def _draft_path(artist_name):
    """Drafts live apart from the real portraits until the user saves."""
    d = _photos_dir() / "_draft"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{get_md5_hash(artist_name)}.jpg"


def _save_square(img, target):
    img = img.convert("RGB")
    img = ImageOps.pad(img, (500, 500), method=Image.Resampling.LANCZOS, color=(0, 0, 0))
    img.save(target, "JPEG", quality=90)


def _known_albums(mf_artist_id, limit=3):
    """A few of this artist's albums from the library, to tell the AI which
    artist is meant (common names are ambiguous)."""
    if not mf_artist_id:
        return []
    rows = db_engine.execute_query(
        "SELECT album_title, original_year FROM library_master WHERE mf_artist_id = ? ORDER BY original_year LIMIT ?",
        (mf_artist_id, limit)) or []
    return [f"{r['album_title']} ({r['original_year']})" if r.get('original_year') else r['album_title'] for r in rows]


def _discogs_portrait(artist_name):
    """
    Best Discogs artist image as a DRAFT portrait. Returns
    (draft_written, matched_name, exact_match). The name goes in `params`
    (properly encoded; 1.x pasted it into the URL, so "&" and "#" cut the
    name short) and an exact name match is preferred over the first hit.
    """
    token = config_handler.DISCOGS_TOKEN()
    headers = {"User-Agent": config_handler.USER_AGENT(), "Authorization": f"Discogs token={token}"}
    try:
        time.sleep(1.0)
        res = requests.get("https://api.discogs.com/database/search",
                           params={"q": artist_name, "type": "artist"}, headers=headers, timeout=15).json()
        results = res.get('results') or []
        if not results:
            return False, None, False
        want = artist_name.strip().lower()
        exact = [r for r in results if (r.get('title') or '').strip().lower() == want]
        pick = exact[0] if exact else results[0]
        img_url = pick.get('cover_image')
        if not img_url or img_url.endswith('spacer.gif'):
            return False, pick.get('title'), bool(exact)
        img_req = requests.get(img_url, headers=headers, timeout=15)
        if img_req.status_code != 200:
            return False, pick.get('title'), bool(exact)
        _save_square(Image.open(BytesIO(img_req.content)), _draft_path(artist_name))
        return True, pick.get('title'), bool(exact)
    except Exception as e:
        print(f"[BioBuilder] Discogs portrait fetch failed: {e}")
        return False, None, False


def _grounded_bio(artist_name, enhanced, albums):
    """Gemini + Google Search grounding. Returns (text, sources)."""
    if enhanced:
        length = ("a deep, comprehensive 5-paragraph professional biography of about 450-500 words. "
                  "Structure: 1 Origins, 2 Musical style, 3 Career milestones, 4 Challenges and innovations, 5 Legacy.")
    else:
        length = ("a concise 3-paragraph professional biography of about 250-300 words. "
                  "Structure: 1 Origins, 2 Musical style and milestones, 3 Legacy.")
    who = f"the music artist '{artist_name}'"
    if albums:
        who += f" (the artist of: {', '.join(albums)})"
    # Wording matters (tested 2026-11-15): a multi-line "Subject: ..." prompt
    # was answered from memory with NO search at all, while single-paragraph
    # "Search the web, then write..." prompts searched every time (5-7
    # sources). Plus a system instruction to always search, and one retry.
    rules = ("Start with the artist's name; plain prose, no headings or lists. Only use facts from your "
             "search results; do not invent dates, band members, chart positions or quotes. If little is "
             "documented about this artist, write less rather than guess.")
    prompts = [
        f"Search the web, then write {length} The subject is {who}. {rules}",
        f"You must use Google Search before answering. Search the web for {who}, then write {length} {rules}",
    ]
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        system_instruction="You are a music archivist. Always search the web before answering, "
                           "and only state facts found in the search results.",
    )
    client = genai.Client(api_key=config_handler.GEMINI_API_KEY())
    text, sources = "", []
    for prompt in prompts:
        response = client.models.generate_content(model="gemini-flash-latest", contents=prompt, config=config)
        text = (response.text or "").strip()
        candidate = response.candidates[0] if response.candidates else None
        grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
        chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
        sources = []
        for chunk in (chunks or []):
            web = getattr(chunk, "web", None)
            title = getattr(web, "title", None) if web else None
            if title and title not in sources:
                sources.append(title)
        if sources:
            break
    return text, sources


def run_logic(action, tools_dir, env_path):

    # SEARCH
    if action == "search":
        query = request.args.get('q', '').strip()
        results = db_engine.execute_query(
            "SELECT mf_artist_id, artist_name, country, biography, photo_path FROM library_artist WHERE artist_name LIKE ?",
            (f"%{query}%",)
        ) or []
        for r in results:
            r['md5_hash'] = get_md5_hash(r['artist_name'])
        return jsonify({"status": "success", "data": results})

    # THE ALBUM'S ARTIST (arriving from Intelli-Tagger / Album Personnel)
    elif action == "folder_artist":
        path = (request.json or {}).get('path') or ''
        manifest = Path(path) / "manifest.json"
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
            return jsonify({"status": "success", "artist": m.get("artist_seed") or ""})
        except Exception:
            return jsonify({"status": "error", "message": "The album's manifest.json couldn't be read."})

    # GENERATE BIO (draft: text to the editor, portrait to photos/_draft)
    elif action == "generate_bio":
        data = request.json or {}
        artist_name = data.get('artist_name') or ''
        try:
            bio_text, sources = _grounded_bio(artist_name, bool(data.get('enhanced')),
                                              _known_albums(data.get('mf_artist_id')))
        except Exception as e:
            return jsonify({"status": "error", "message": f"The biography couldn't be written: {e}"})
        if not bio_text:
            return jsonify({"status": "error", "message": "The AI returned no text. Try again."})
        photo, match, exact = _discogs_portrait(artist_name)
        return jsonify({"status": "success", "biography": bio_text, "sources": sources,
                        "grounded": bool(sources), "draft_photo": photo,
                        "photo_match": match, "photo_exact": exact,
                        "md5_hash": get_md5_hash(artist_name)})

    # LOCAL PHOTO (manual override) -> also a draft until Save
    elif action == "upload_local_photo":
        data = request.json or {}
        artist_name, local_path = data.get('artist_name'), data.get('local_path')
        if not artist_name or not local_path:
            return jsonify({"status": "error", "message": "Missing artist name or file path."})
        if not os.path.exists(local_path):
            return jsonify({"status": "error", "message": "That file doesn't exist."})
        try:
            _save_square(Image.open(local_path), _draft_path(artist_name))
        except Exception as e:
            return jsonify({"status": "error", "message": f"That image couldn't be used: {e}"})
        return jsonify({"status": "success", "md5_hash": get_md5_hash(artist_name)})

    # SHOW A DRAFT PORTRAIT (not yet saved)
    elif action == "draft_photo":
        md5 = request.args.get('md5', '')
        p = _photos_dir() / "_draft" / f"{md5}.jpg"
        if len(md5) == 32 and all(c in "0123456789abcdef" for c in md5) and p.exists():
            return send_file(str(p), mimetype="image/jpeg", max_age=0)
        return jsonify({"status": "error", "message": "No draft portrait."}), 404

    # DISCARD A DRAFT PORTRAIT (another artist loaded, or the user cancels)
    elif action == "discard_draft":
        name = (request.json or {}).get('artist_name') or ''
        try:
            _draft_path(name).unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify({"status": "success"})

    # GET DETAILS
    elif action == "get_details":
        mf_id = request.args.get('mf_id')
        results = db_engine.execute_query("SELECT * FROM library_artist WHERE mf_artist_id = ?", (mf_id,))
        if results:
            data = results[0]
            data['md5_hash'] = get_md5_hash(data['artist_name'])
            data['has_photo'] = get_hashed_path(data['artist_name']).exists()
            return jsonify({"status": "success", "data": data})
        return jsonify({"status": "error", "message": "Not found"})

    # SAVE BIO (+ the draft portrait, if one was chosen)
    elif action == "save_bio":
        data = request.json or {}
        name = data.get('artist_name') or ''
        final, draft = get_hashed_path(name), _draft_path(name)
        if data.get('use_draft_photo') and draft.exists():
            os.replace(draft, final)   # the approved portrait replaces the old one only now
        # photo_path only ever points at a file that exists (1.x stored the
        # hashed path even when no portrait was ever fetched)
        if final.exists():
            sql, args = ("UPDATE library_artist SET biography = ?, photo_path = ?, bio_updated_at = CURRENT_TIMESTAMP WHERE mf_artist_id = ?",
                         (data.get('biography', ''), str(final), data.get('mf_artist_id')))
        else:
            sql, args = ("UPDATE library_artist SET biography = ?, bio_updated_at = CURRENT_TIMESTAMP WHERE mf_artist_id = ?",
                         (data.get('biography', ''), data.get('mf_artist_id')))
        ok = db_engine.execute_query(sql, args, commit=True)
        return jsonify({"status": "success" if ok else "error",
                        "message": None if ok else "The biography couldn't be saved to the database."})

    return jsonify({"status": "error", "message": "Unknown action"})

# --- END OF FILE biography.py ---
