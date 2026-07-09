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
# This function is the ONLY authority for tier-3 (AI web-search) personnel
# resolution -- the automatic last-resort tier of Personnel Engine v2's
# waterfall (tools/personnel/personnel.py), reached only when the merged
# MB+Discogs result is thin AND Wikipedia's automatic fallback didn't fill
# it in either. Same grounded-search contract as resolve_original_year_ai:
# NEVER fabricate names/roles with no real citation basis, and resolved
# credits require genuine search grounding, not the model's own recall.
#
# Deliberately source-agnostic -- the prompt does NOT name or steer
# toward AllMusic or any other specific site (see project_mb_contribution_tool
# memory's ToS research: AllMusic's Terms of Service prohibit automated
# reproduction of their content "by any means", and a prompt specifically
# steering the model toward AllMusic would just be that same prohibited
# extraction through an intermediary, not a loophole around it). If the
# model's search incidentally cites AllMusic among other sources, that's
# no different from it incidentally citing Wikipedia or Discogs -- nothing
# here asks for that specifically.
# =========================================================


def resolve_personnel_ai(artist, album):
    """
    Returns a list of {"name": str, "role": str} candidates, or an empty
    list if nothing could be grounded. Never raises.

    Prompt structure fixed 2026-07-09 -- same bug class as
    resolve_original_year_ai(), confirmed live against a real failing
    case (Clancy Eccles' "Feel The Rythm", found via John's own manual
    search in seconds while this function returned nothing). The old
    prompt demanded a rigid "Name - Role" list as the ENTIRE response,
    which produced a perfectly-formatted but completely UNGROUNDED
    15-person list -- grounding_chunks was empty, no real search ever
    happened, the model just answered from trained recall. Our own
    "never trust ungrounded recall" check correctly rejected it, but the
    underlying prompt was the actual problem. Asking for natural-language
    reasoning FIRST, with a clearly delimited "CREDITS:" section only at
    the end, reliably triggers real tool use. Parsing is scoped to ONLY
    the text after "CREDITS:" rather than every line of the response --
    the narrative section can legitimately contain a stray " - " (e.g. a
    date range) that would otherwise risk being misparsed as a name/role
    pair.

    Second fix, same day, John's own catch: once grounding was reliably
    happening, a real result STILL came back inconsistent from one call
    to the next on the exact same album -- one run surfaced the full
    backing band (bassist, drummer, guitarists, etc.), the next two runs
    found only production/engineering credits with zero performers, even
    though the actual band is real and well-documented. That's thin in
    the sense that actually matters for MetaForge's Personnel Bridge use
    case (a session musician's own performance credits), even when the
    raw credit COUNT looks rich. Explicitly calling out backing/session
    musicians as their own required search, not just one item in a flat
    list, made this reliable: live-tested 3-for-3 (vs. 1-for-3 with the
    old flat-list prompt) on the identical failing case, with richer
    detail each time (percussion, backing vocals, horn sections).
    """

    prompt = f"""Search the web to find out who performed on and contributed to
the album "{album}" by {artist}.

Two categories matter equally here, and the second is often harder to find
but just as important -- make a deliberate, separate search for it if your
first search does not surface it:
1. Production/technical credits: producers, engineers, songwriters.
2. The actual BACKING BAND / SESSION MUSICIANS who played the instruments
   and sang on the recordings -- bassist, guitarist(s), drummer, keyboard/
   organ player, horn players, backing vocalists, etc. For recordings from
   labels/eras with a well-documented house band (session musicians shared
   across many recordings on the same label), search specifically for the
   backing band/session musicians by name, not just the credited producer/
   artist.

Describe what you find in natural language, citing where the information
came from.

Then, end your response with a section that starts with exactly the line
CREDITS: followed by one line per person in the format Name - Role.

If your search genuinely finds nothing, end with CREDITS: UNKNOWN instead.
NEVER guess or fabricate a name or role with no basis.
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

        # Same rule as resolve_original_year_ai: no real search grounding,
        # no credits -- never trust ungrounded model recall.
        if not chunks:
            return []

        credits_section = text.split("CREDITS:", 1)
        if len(credits_section) < 2:
            return []
        credits_text = credits_section[1]

        if "UNKNOWN" in credits_text.upper() and len(credits_text.strip()) < 20:
            return []

        results = []
        for line in credits_text.split("\n"):
            # Non-greedy .{2,60}? for the name, NOT a [^-] exclusion --
            # a hyphenated entity name (e.g. "The Schuster-Longstreet
            # Company") is legitimate and must not be rejected just
            # because it contains a hyphen; only " - " (space-hyphen-
            # space) is treated as the real name/role delimiter.
            match = re.match(r"^\s*[-*]?\s*(.{2,60}?)\s+-\s+(.{2,80})\s*$", line)
            if match:
                name, role = match.group(1).strip(), match.group(2).strip()
                if name and role:
                    results.append({"name": name, "role": role})

        return results

    except Exception:
        return []


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
    """
    Returns {track_num: {"year": "YYYY", "date_type": "released"|
    "recorded"|"unclear"}} -- NOT a bare year. `original_year`/TORY is
    defined as the true original RELEASE year (see the IPM design doc's
    "Bimodal Rigor: NEVER use TYER" rule), but Discogs liner notes just as
    often describe recording/session dates ("Recorded at Universal
    Recorders... February 24, 1950") as release dates, and the two are
    genuinely different facts -- a session doesn't guarantee a release
    happened the same year, even though in practice (physical singles
    era) the gap is usually small. Confirmed live 2026-07-09 (John) the
    prior prompt conflated them by literally asking for "recorded/first
    released" as one interchangeable concept -- this fixes that at the
    source rather than presenting a recording date as if it were a
    confirmed release date. `date_type` lets every downstream consumer
    (confidence scoring, the correction-candidate evidence log, MB
    submission edit notes) be honest about which one it actually got,
    instead of asserting more certainty than the source text supports.
    """

    prompt = f"""The following is the raw "notes" text from a Discogs
release page for an album with {track_count} tracks (numbered 1 to
{track_count}). It may describe recording/session dates AND/OR release
dates for individual tracks or ranges of tracks (e.g. "Tracks 1 to 3:
recorded New York City, 26 December 1939" describes a RECORDING date;
"Tracks 1 to 3 released as a single, January 1940" describes a RELEASE
date -- these are different facts, do not treat them as the same thing).

Notes text:
{notes_text}

Return ONLY valid JSON: an object whose keys are track number strings
("1" through "{track_count}") and whose values are each an object with:
- "year": a 4-digit year string, or null if the notes don't give enough
  information to confidently determine that track's date.
- "date_type": one of "released" (the notes explicitly describe when
  this was issued/released to the public), "recorded" (the notes only
  describe a recording/session date, no release date is mentioned), or
  "unclear" (the notes give a year but don't make clear which kind of
  date it is).

If a track's notes mention BOTH a recording date and a release date,
use the RELEASE date and set date_type to "released" -- release date is
what matters here, recording date is only a fallback when that's all
the notes provide.

Every track number from 1 to {track_count} MUST appear as a key, with
"year": null and "date_type": "unclear" if the notes don't cover it. Do
NOT guess or fabricate a year for a track the notes don't cover. Do NOT
include any track numbers outside 1 to {track_count}.
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
            if not isinstance(v, dict):
                continue
            year = v.get("year")
            date_type = v.get("date_type") if v.get("date_type") in ("released", "recorded", "unclear") else "unclear"
            if year and str(year).isdigit() and len(str(year)) == 4:
                result[track_num] = {"year": str(year), "date_type": date_type}

        return result

    except Exception:
        return {}

# --- END OF FILE ai_engine.py ---