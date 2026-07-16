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

    # Parsed (not just the raw text sent to the prompt above) so the
    # validation step below can check the AI's answer against the real
    # controlled vocabulary, not just trust it followed the prompt's
    # instructions. Real bug, found live 2026-07-16: "STRICT semantic
    # classification engine" in the prompt was the ONLY enforcement --
    # nothing in code ever checked the returned value was actually one
    # of the fixed values, and mood had genuinely drifted in the live
    # database as a result (e.g. "Uplifting", "Soulful", a literal typo
    # "Melocnholic" -- none of which are real anchors). genre/
    # sonic_texture/emotional_flavor happened to have zero drift in
    # practice, but shared the identical unenforced gap.
    taxonomy_data = json.loads(taxonomy)
    moods_data = json.loads(moods_taxonomy)
    valid_moods = set(moods_data.get("anchors", []))
    valid_textures = set(moods_data.get("modifiers", {}).get("Sonic_Texture", []))
    valid_flavors = set(moods_data.get("modifiers", {}).get("Emotional_Flavor", []))

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

    # Closed-vocabulary enforcement -- an off-list value here must fail
    # loudly, not get silently written to the database. The caller
    # (intelli-tagger.py's _orchestrate_tagger_batch) already wraps this
    # whole function in try/except and falls back to "Unknown" for every
    # AI field on any exception -- raising here is safe and lands
    # exactly on that existing, already-correct safety net, never a new
    # crash risk.
    if data["parent"] not in taxonomy_data:
        raise ValueError(f"AI returned parent genre {data['parent']!r} not in taxonomy.json")
    if data["sub"] not in taxonomy_data.get(data["parent"], []):
        raise ValueError(f"AI returned sub-genre {data['sub']!r} not valid under parent {data['parent']!r}")
    if data["mood"] not in valid_moods:
        raise ValueError(f"AI returned mood {data['mood']!r} outside the fixed anchor list {sorted(valid_moods)}")
    if data["sonic_texture"] not in valid_textures:
        raise ValueError(f"AI returned sonic_texture {data['sonic_texture']!r} outside the fixed list {sorted(valid_textures)}")
    if data["emotional_flavor"] not in valid_flavors:
        raise ValueError(f"AI returned emotional_flavor {data['emotional_flavor']!r} outside the fixed list {sorted(valid_flavors)}")

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


def _credit_name_is_grounded(name, grounded_text):
    """
    Defense-in-depth check for a [confirmed]-tagged credit, added
    2026-07-10. NOT a guarantee the specific track/role claim attached to
    this name is what a real search backed -- just that the name itself
    isn't conjured from nowhere despite the model tagging it [confirmed].
    This is the exact gap that let a real hallucination through: an
    earlier prompt version produced "Lee \"Scratch\" Perry" as a
    [confirmed] backing-vocals credit on a track where 12 genuine grounded
    searches had run, yet the name never appeared in a single grounded
    span -- the model's own self-reported tag was simply wrong, the same
    over-trust bug class already found and fixed once before for
    resolve_original_year_ai()'s self-reported "resolved: true" flag.

    Checks the full (quote-stripped) name first, then falls back to just
    the last word (typically a surname, >2 chars to avoid noise) so a
    minor formatting difference between the CREDITS line and the
    narrative text (e.g. "Ernest Ranglin" vs. a Sources sentence that
    just says "Ranglin") doesn't cause a false downgrade of a credit that
    really is grounded.
    """
    if not name or not grounded_text:
        return False
    cleaned = re.sub(r"[\"'“”]", "", name).strip()
    grounded_lower = grounded_text.lower()
    if cleaned.lower() in grounded_lower:
        return True
    words = cleaned.split()
    last_word = words[-1] if words else ""
    return len(last_word) > 2 and last_word.lower() in grounded_lower


def _credit_candidate_uris(name, supports, chunks):
    """
    Per-credit candidate source links for Personnel Scout's "click to
    verify" flow (2026-07-11) -- NOT for persistence. See the Google
    grounding-terms finding in project_mb_contribution_tool memory:
    displaying a grounded link to the SAME user who ran the search, in
    their own live session, is the one thing these terms clearly permit;
    extracting and storing that same data for later reuse/redisplay is
    not. Callers MUST treat this as ephemeral, frontend-only data -- never
    write it to a database row or a log file.

    Same name-matching rule as _credit_name_is_grounded (full name, then
    a >2-char last-word fallback) but applied per grounding_supports SPAN
    instead of one pooled string, so a matching span's own
    grounding_chunk_indices can be resolved back to that chunk's real
    web.uri. Deduplicated, capped at 3 -- a credit rarely needs more than
    a couple of candidate links to check, and showing more would just be
    clutter for the person reviewing them.
    """
    if not name or not supports or not chunks:
        return []
    cleaned = re.sub(r"[\"'“”]", "", name).strip()
    if not cleaned:
        return []
    words = cleaned.split()
    last_word = words[-1] if words else ""
    cleaned_lower = cleaned.lower()
    last_word_lower = last_word.lower() if len(last_word) > 2 else None

    uris = []
    for s in supports:
        seg = getattr(s, "segment", None)
        seg_text = getattr(seg, "text", None) if seg else None
        if not seg_text:
            continue
        seg_lower = seg_text.lower()
        if cleaned_lower not in seg_lower and not (last_word_lower and last_word_lower in seg_lower):
            continue
        for idx in (getattr(s, "grounding_chunk_indices", None) or []):
            if idx is None or idx < 0 or idx >= len(chunks):
                continue
            web = getattr(chunks[idx], "web", None)
            uri = getattr(web, "uri", None) if web else None
            if uri and uri not in uris:
                uris.append(uri)
                if len(uris) >= 3:
                    return uris
    return uris


def resolve_personnel_ai(artist, album, label=None, catalog_number=None):
    """
    Returns a list of {"name", "role", "sources", "evidence_scope",
    "evidence_detail", "ai_confirmed"} candidates, or an empty list if
    nothing could be grounded. Never raises.

    label/catalog_number are optional, MB-sourced confirmed release
    identity (see musicbrainz_id.py's get_release_details -- the release
    the user already picked from a scored candidate list, not a guess).
    Used to disambiguate the search when given; the function works fine
    without them, just with less certainty about which exact release the
    model's search actually describes.

    Prompt structure fixed 2026-07-09 -- same bug class as
    resolve_original_year_ai(): a rigid "entire response must be a
    Name - Role list" instruction measurably suppresses real grounded
    search in this SDK/model combination (confirmed live: produced a
    perfectly-formatted but completely UNGROUNDED list, grounding_chunks
    empty). Fixed by asking for natural-language reasoning FIRST, with a
    "CREDITS:" section only at the end -- reliably triggers real tool
    use. Second fix, same day: raw credit COUNT looked "thin-safe" even
    when every credit was production/engineering and zero were
    performers -- fixed by explicitly requiring backing/session
    musicians as their own required search, not one item in a flat list.

    Rebuilt 2026-07-10 after a real, validated failure found via a live
    A/B/C comparison (Gemini flat-list vs. Gemini track-by-track vs.
    Claude web_search, same album -- see project_personnel_engine_v2
    memory for the full writeup). Concrete finding: the OLD flat-list
    prompt confidently blended a real, track-specific credit with an
    unconfirmed house-band guess on ONE line, and separately produced a
    name unsupported by any other source or method used in the same test
    -- a probable hallucination the old prompt let straight through. The
    new prompt requires every credit be explicitly tagged CONFIRMED (a
    source ties it to that specific track) or INFERRED (general/era/
    house-band knowledge, not track-verified) -- never presented at the
    same confidence -- and explicitly instructs the model to identify a
    compilation's ORIGINAL constituent release(s) as additional search
    targets.

    Rebuilt AGAIN same day, two further fixes from a direct A/B test of
    that prompt against a leaner candidate closer to John's own manually-
    successful phrasing ("give me an accurate, track-by-track personnel
    list"):

    1. Prompt trimmed toward the lean version's structure (the itemized
       "two categories" list and the separate release-confirmation
       paragraph collapsed into one line each) -- but the CONFIRMED/
       INFERRED definitions were kept at the ORIGINAL, more detailed
       wording verbatim (naming concrete evidence types: liner notes, a
       discography entry keyed to track/session, a review naming the
       specific performance). A/B test showed the lean version's vaguer
       one-line definition ("a source ties it directly to that track")
       let a [confirmed] tag slip onto a name ("Lee \"Scratch\" Perry")
       that the heavier prompt's version correctly excluded -- length
       wasn't the load-bearing variable, definition specificity was.
       Confirmed harmless to trim elsewhere: the lean version's broad
       [inferred] coverage repeating the same house-band list across many
       tracks looked templated at first glance but John spot-checked it
       and confirmed the underlying claim (the same five people really
       were the documented house band for most of this release) --
       repetition of a TRUE inferred fact isn't a flaw, it's just what an
       honest answer looks like when the underlying reality doesn't vary
       track to track.
    2. _credit_name_is_grounded() added as a second, independent check on
       top of the model's own [confirmed] tag -- see its own docstring.
       The old code only checked `grounding_chunks` (did ANY real search
       happen this turn, aggregate/binary) which the Perry-hallucinating
       response passed easily (12 real searches ran); nothing checked
       whether that SPECIFIC name was backed by any of them. Confirmed
       live via `grounding_supports` (a real, populated field pinning
       spans of the model's own text to the chunks that back them) that
       genuinely grounded names ("Ranglin", "Jackie Jackson") DO appear
       in that text, giving a real, non-hypothetical signal to check
       against rather than trusting the model's self-report alone.
    """

    release_id_bits = [b for b in [
        f'label "{label}"' if label else None,
        f'catalog number "{catalog_number}"' if catalog_number else None,
    ] if b]
    release_id_line = (
        f'The specific release I\'m asking about is identified by '
        f'{" and ".join(release_id_bits)} -- this is confirmed data, use '
        f'it to make sure you have the right release, not a same-titled '
        f'reissue or compilation on a different label.\n\n'
        if release_id_bits else ""
    )

    prompt = f"""Who performed on and contributed to the album "{album}" by {artist}? Give me
an accurate, track-by-track personnel list.

{release_id_line}Include both production/technical credits (producer, engineer, songwriter)
and the backing band/session musicians who actually played on the
recordings -- search specifically for the session musicians if your first
pass only turns up the credited artist/producer.

If this is a compilation, also check the original release(s) each track
first came from -- a compilation's own packaging often lacks track-level
credits even when the original single/session release has them.

For every credit, distinguish clearly between two kinds of evidence -- do
NOT blend them into one line at the same confidence:
  CONFIRMED: a source explicitly documents this credit for THIS SPECIFIC
      track (liner notes, a discography entry keyed to track/session, a
      review naming the specific performance).
  INFERRED: documented for the release or artist generally (e.g. "the
      house band for this label's sessions was X, Y, Z") but NOT confirmed
      for this specific track. If you name someone only because they were
      the general house band/era session musicians, not because a source
      ties them to this track, this is INFERRED.

Describe what you find in natural language first, citing where each piece
of information came from.

Then end your response with a section that starts with exactly the line
CREDITS: followed by one line per credit, in this format:
Track N: Name - Role [confirmed]
Track N: Name - Role [inferred]
Album: Name - Role [confirmed]
Album: Name - Role [inferred]

Use "Album:" instead of a track number for album-wide credits (producer,
songwriter, etc.) that aren't track-specific by nature.

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

        # Per-claim check (2026-07-10) -- see _credit_name_is_grounded's
        # docstring. The chunk-presence check above only proves SOME real
        # search happened this turn, not that any specific credit is
        # backed by it. grounding_supports ties spans of the model's OWN
        # generated text to the real chunks that back them -- pool all
        # grounded span text together so each [confirmed] credit's name
        # can be checked against genuinely search-backed text below,
        # rather than trusting the model's self-reported tag alone.
        supports = getattr(grounding, "grounding_supports", None) or []
        grounded_text = " ".join(
            seg.text for s in supports
            if (seg := getattr(s, "segment", None)) and getattr(seg, "text", None)
        )

        credits_section = text.split("CREDITS:", 1)
        if len(credits_section) < 2:
            return []
        credits_text = credits_section[1]

        if "UNKNOWN" in credits_text.upper() and len(credits_text.strip()) < 20:
            return []

        # Same extraction as resolve_original_year_ai's `sources` --
        # web.title per grounding chunk, capped at 5. All credits in
        # this response share ONE search call for the whole album, so
        # the same source list is attached to every credit rather than
        # trying to attribute individual sources to individual people
        # (John, 2026-07-09, "can we 'hint' at the sources... no need
        # for URLs unless trivial" -- titles, not links, satisfies that
        # without extra work to resolve/validate real URLs).
        sources = [
            web.title for chunk in chunks[:5]
            if (web := getattr(chunk, "web", None)) and getattr(web, "title", None)
        ]

        results = []
        for line in credits_text.split("\n"):
            # "Track N:" or "Album:" prefix, then the same Name - Role
            # shape as before (non-greedy name group, " - " as the real
            # delimiter -- a hyphenated entity name like "The Schuster-
            # Longstreet Company" must not be rejected just for
            # containing a hyphen). The [confirmed|inferred] tag is
            # optional in the match -- if the model drops it, default to
            # NOT confirmed rather than assuming the stronger claim; see
            # module-level "never trust unlabeled as verified" rule.
            match = re.match(
                r"^\s*(?:Track\s*(\d+)|Album)\s*:\s*(.{2,60}?)\s+-\s+(.{2,80}?)"
                r"\s*(?:\[\s*(confirmed|inferred)\s*\])?\s*$",
                line, re.IGNORECASE
            )
            if match:
                track_num, name, role, tag = match.groups()
                name, role = name.strip(), role.strip()
                if name and role:
                    # Model's own tag is necessary but no longer
                    # sufficient -- a [confirmed] claim also has to
                    # survive the grounded-text check, or it's treated as
                    # unconfirmed. An [inferred] tag is never upgraded by
                    # this check (era/house-band knowledge legitimately
                    # may not appear verbatim in any grounded span).
                    self_reported_confirmed = (tag or "").lower() == "confirmed"
                    ai_confirmed = self_reported_confirmed and _credit_name_is_grounded(name, grounded_text)
                    results.append({
                        "name": name,
                        "role": role,
                        "sources": sources,
                        "evidence_scope": "track" if track_num else "album",
                        "evidence_detail": track_num,
                        "ai_confirmed": ai_confirmed,
                        # Ephemeral only -- see _credit_candidate_uris'
                        # docstring. Callers must never persist this list.
                        "candidate_urls": _credit_candidate_uris(name, supports, chunks),
                    })

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