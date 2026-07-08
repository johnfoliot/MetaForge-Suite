# --- START OF FILE ai_engine.py ---
# ======================================================================
# MetaForge Engine: AI Taxonomy Mapping (Phase 4)
# Role: Semantic Classification Layer (Authority-Locked)
# Build 2.0.1: Stable Gemini client + strict semantic enforcement
# ======================================================================

import json
import re
from pathlib import Path
from google import genai
from google.genai import types
from common import config_handler


TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "taxonomy.json"
MOODS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "moods.json"

# ---------------------------------------------------------
# SAFE CONFIG BINDING (CRITICAL FIX)
# ---------------------------------------------------------
GEMINI_KEY = config_handler.GEMINI_API_KEY()

if not GEMINI_KEY:
    raise RuntimeError("GEMINI_API_KEY missing from environment (.env)")

GEMINI_KEY = str(GEMINI_KEY).strip()

client = genai.Client(api_key=GEMINI_KEY)


# =========================================================
# AUTHORITY CONTRACT
# =========================================================
# This engine is the ONLY authority for:
# - parent (genre)
# - sub (subgenre)
# - mood
# - sonic_texture
# - emotional_flavor
# - country (artist nationality inference -- NOT a release/distribution
#   territory; that comes from MusicBrainz separately)
# =========================================================


def map_track_taxonomy(artist, title, acoustic_data):

    # -------------------------------
    # LOAD TAXONOMY SOURCES
    # -------------------------------
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        taxonomy = f.read()

    with open(MOODS_PATH, "r", encoding="utf-8") as f:
        moods_taxonomy = f.read()

    # -------------------------------
    # PROMPT
    # -------------------------------
    prompt = f"""
You are a STRICT semantic classification engine.

Return ONLY valid JSON with:
- parent
- sub
- mood
- sonic_texture
- emotional_flavor
- country

DO NOT include any other fields.

Artist: {artist}
Title: {title}

Acoustic Data:
{json.dumps(acoustic_data)}

Taxonomy Reference:
{taxonomy}

Mood Reference:
{moods_taxonomy}

For "country", infer the artist's country of origin/nationality (e.g. "US",
"UK", "Canada") based on general knowledge of the artist. This is NOT the
release or distribution territory of this specific recording.
"""

    # -------------------------------
    # MODEL CALL (CORRECT MODEL NAME)
    # -------------------------------
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt
    )

    raw_text = (response.text or "").replace("```json", "").replace("```", "").strip()

    try:
        data = json.loads(raw_text)
    except Exception as e:
        raise ValueError(f"Gemini returned invalid JSON: {raw_text}") from e

    # -------------------------------
    # HARD SANITIZATION LAYER
    # -------------------------------
    forbidden_keys = {
        "mb_track_id",
        "acoustid",
        "mb_artist_id",
        "mb_album_id",
        "mb_work_id",
        "title",
        "duration"
    }

    for k in forbidden_keys:
        data.pop(k, None)

    # -------------------------------
    # VALIDATION
    # -------------------------------
    required = [
        "parent",
        "sub",
        "mood",
        "sonic_texture",
        "emotional_flavor",
        "country"
    ]

    for k in required:
        if k not in data:
            raise ValueError(f"Missing field from AI response: {k}")
        if not isinstance(data[k], str) or not data[k].strip():
            raise ValueError(f"Invalid field '{k}' from AI response")

    # -------------------------------
    # RETURN CONTRACT
    # -------------------------------
    return {
        "parent": data["parent"],
        "sub": data["sub"],
        "mood": data["mood"],
        "sonic_texture": data["sonic_texture"],
        "emotional_flavor": data["emotional_flavor"],
        "country": data["country"]
    }


# =========================================================
# AUTHORITY CONTRACT (SEPARATE FROM map_track_taxonomy)
# =========================================================
# This function is the ONLY authority for tier-3 (AI web-search) original
# year resolution -- the last-resort tier of year_resolution_engine.py's
# waterfall, reached only when MusicBrainz has no recording- or
# release-group-level date at all. It is a GROUNDED SEARCH call, not
# closed-form classification like map_track_taxonomy above -- it MUST
# NEVER fabricate a plausible-sounding year with no real citation basis.
# If it can't ground a real answer, it must say so (resolved=False), not
# guess.
#
# Fixed 2026-07-08: the previous version asked for bare JSON output and
# trusted the model's own self-reported "resolved": true flag. Live
# testing found the model can (and does) answer confidently with
# resolved=true from its own trained-knowledge recall WITHOUT actually
# invoking the search tool at all -- response.candidates[0]
# .grounding_metadata is None in that case, meaning no real grounding
# happened, contradicting this function's own documented contract. The
# strict-JSON-only prompt appears to suppress real tool use more often
# than a natural-language one (confirmed by live comparison). Now: (1)
# the prompt asks for a natural-language answer instead of bare JSON,
# which reliably triggers real search grounding, (2) resolved=True
# requires grounding_metadata.grounding_chunks to be genuinely present --
# an ungrounded answer is now always treated as unresolved, regardless of
# how confident the model's text sounds.
# =========================================================


def resolve_original_year_ai(artist, title, album, known_release_year):

    prompt = f"""Search the web to find the TRUE ORIGINAL release year (the
first time this recording was ever released, NOT this pressing/reissue/
remaster) for the recording "{title}" by {artist} (album: {album}).

This copy's release year is {known_release_year}, which may itself be a
reissue/remaster year, not the original.

State the year clearly in your answer (e.g. "released in 1962"). If you
cannot find a real, sourced answer via search, respond with exactly the
word UNKNOWN and nothing else. NEVER guess or fabricate a plausible-
sounding year with no basis.
"""

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )

        text = response.text or ""

        candidate = response.candidates[0] if response.candidates else None
        grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
        chunks = getattr(grounding, "grounding_chunks", None) if grounding else None

        # No real search grounding happened -- this is the model's own
        # trained-knowledge recall, not a verified web-search answer.
        # Never counts as resolved, no matter how confident the text is.
        if not chunks:
            return {"resolved": False, "year": None, "evidence": None}

        if "UNKNOWN" in text.upper():
            return {"resolved": False, "year": None, "evidence": None}

        year_match = re.search(r"\b(1[5-9]\d{2}|20\d{2})\b", text)
        if not year_match:
            return {"resolved": False, "year": None, "evidence": None}

        sources = [
            web.title for chunk in chunks[:5]
            if (web := getattr(chunk, "web", None)) and getattr(web, "title", None)
        ]

        evidence = {
            "citation_text": text.strip()[:500],
            "sources": sources,
            "search_queries": list(getattr(grounding, "web_search_queries", None) or []),
        }

        return {"resolved": True, "year": year_match.group(1), "evidence": evidence}

    except Exception:
        pass

    return {"resolved": False, "year": None, "evidence": None}


# =========================================================
# AUTHORITY CONTRACT (SEPARATE FROM map_track_taxonomy AND
# resolve_original_year_ai)
# =========================================================
# This function is the ONLY authority for Discogs-notes-to-track-date
# extraction (the Discogs tier of year_resolution_engine.py's waterfall).
# It is a CLOSED-FORM PARSE of text already retrieved, NOT a search or
# classification call -- it MUST NOT use search grounding, since there is
# nothing to search: the notes text is handed to it directly. Its job is
# to map track numbers to recording dates found in that text, and it must
# return null for any track it cannot confidently map -- never a guess,
# and never a fabricated entry for a track number outside the given range.
# =========================================================


def extract_track_dates_from_notes(notes_text, track_count):

    prompt = f"""The following is the raw "notes" text from a Discogs
release page for an album with {track_count} tracks (numbered 1 to
{track_count}). It may describe recording/session dates for individual
tracks or ranges of tracks (e.g. "Tracks 1 to 3: New York City, 26
December 1939").

Notes text:
{notes_text}

Return ONLY valid JSON: an object whose keys are track number strings
("1" through "{track_count}") and whose values are either a 4-digit year
string (the year that specific track was recorded/first released,
according to the notes) or null if the notes don't give enough
information to confidently determine that track's date.

Every track number from 1 to {track_count} MUST appear as a key. Do NOT
guess or fabricate a year for a track the notes don't cover -- use null.
Do NOT include any track numbers outside 1 to {track_count}.
"""

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        raw_text = (response.text or "").replace("```json", "").replace("```", "").strip()
        data = json.loads(raw_text)

        result = {}
        for k, v in data.items():
            try:
                track_num = int(k)
            except (TypeError, ValueError):
                continue
            if not (1 <= track_num <= track_count):
                continue
            if v and str(v).isdigit() and len(str(v)) == 4:
                result[track_num] = str(v)

        return result

    except Exception:
        return {}

# --- END OF FILE ai_engine.py ---