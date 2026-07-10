# --- START OF FILE ab_test_lean_prompt.py ---
# ======================================================================
# One-off dev script, NOT part of the app. A/B tests the CURRENT
# production resolve_personnel_ai() prompt (heavy, itemized) against a
# leaner candidate closer to John's own manually-successful phrasing
# ("can you give me an accurate, track-by-track personnel list?"), both
# run against the SAME engine (Gemini, via the real configured
# GEMINI_KEY) so the only variable is prompt density -- isolates whether
# the heavier prompt is suppressing search effort the way an earlier,
# even-more-rigid prompt was proven to (2026-07-09 fix).
# ======================================================================

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "intelli-tagger" / "engines"))

from google import genai
from google.genai import types
from common import config_handler

ARTIST = "Clancy Eccles"
ALBUM = "Feel The Rhythm"
LABEL = "Jamaican Gold"
CATALOG = "JMC 200.235"
TRACK_COUNT = 16


def _release_id_line(label, catalog_number):
    bits = [b for b in [
        f'label "{label}"' if label else None,
        f'catalog number "{catalog_number}"' if catalog_number else None,
    ] if b]
    if not bits:
        return ""
    return (
        f'The specific release I\'m asking about is identified by '
        f'{" and ".join(bits)} -- this is confirmed data, use it to make '
        f'sure you have the right release, not a same-titled reissue or '
        f'compilation on a different label.\n\n'
    )


def build_heavy_prompt(artist, album, label=None, catalog_number=None):
    """Verbatim copy of the CURRENT production prompt in ai_engine.py's resolve_personnel_ai()."""
    release_id_line = _release_id_line(label, catalog_number)
    return f"""Search the web to find out who performed on and contributed to
the album "{album}" by {artist}.

{release_id_line}Two categories matter equally here, and the second is often harder to find
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

First, confirm which specific release you found (label, year, format) --
if multiple different releases share this artist/title combination, say
so explicitly and state which one your search results actually describe.
Do not silently pick one.

If this release is a COMPILATION (a later collection of tracks originally
issued elsewhere), also identify the ORIGINAL release(s) each track -- or
the album as a whole -- was first issued on, and treat those as ADDITIONAL
search targets. A compilation's own packaging often has no track-level
credits at all, while the original single/session release frequently does.

Then produce a TRACK-BY-TRACK breakdown, not just an album-level summary.
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

If you cannot find genuine track-level detail for most tracks, say so
plainly rather than filling every track in with the same inferred list.

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


def build_lean_prompt(artist, album, label=None, catalog_number=None):
    """Candidate: opens with John's own successful phrasing, same guardrails, much less scaffolding."""
    release_id_line = _release_id_line(label, catalog_number)
    return f"""Who performed on and contributed to the album "{album}" by {artist}? Give me
an accurate, track-by-track personnel list.

{release_id_line}Include both production/technical credits (producer, engineer, songwriter)
and the backing band/session musicians who actually played on the
recordings -- search specifically for the session musicians if your first
pass only turns up the credited artist/producer.

If this is a compilation, also check the original release(s) each track
first came from -- a compilation's own packaging often lacks track-level
credits even when the original single/session release has them.

For each credit, note whether it's CONFIRMED for that specific track (a
source ties it directly to that track) or INFERRED from general/era/house-
band knowledge -- don't present those at the same confidence.

End with a CREDITS: section, one line per credit: "Track N: Name - Role
[confirmed]" or "Track N: Name - Role [inferred]" ("Album:" for album-wide
credits). CREDITS: UNKNOWN if you find nothing. Never invent a name or role
you can't support.
"""


def run(label_for_output, prompt_text, client):
    print("\n" + "=" * 78)
    print(label_for_output)
    print("=" * 78)
    print(f"[prompt length: {len(prompt_text)} chars]\n")

    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt_text,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        text = response.text or ""
        candidate = response.candidates[0] if response.candidates else None
        grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
        chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
        queries = getattr(grounding, "web_search_queries", None) if grounding else None

        print(f"[grounded: {bool(chunks)}] [search queries run: {len(queries) if queries else 0}]")
        if queries:
            for q in queries:
                print(f"   - {q}")

        credits_section = text.split("CREDITS:", 1)
        credits_text = credits_section[1] if len(credits_section) > 1 else ""

        track_lines = re.findall(r"^\s*Track\s*(\d+)\s*:", credits_text, re.IGNORECASE | re.MULTILINE)
        distinct_tracks = sorted(set(int(t) for t in track_lines))
        confirmed_count = len(re.findall(r"\[confirmed\]", credits_text, re.IGNORECASE))
        inferred_count = len(re.findall(r"\[inferred\]", credits_text, re.IGNORECASE))
        total_credit_lines = len(re.findall(r"^\s*(?:Track\s*\d+|Album)\s*:", credits_text, re.IGNORECASE | re.MULTILINE))

        print(f"[total credit lines: {total_credit_lines}] [confirmed: {confirmed_count}] [inferred: {inferred_count}]")
        print(f"[distinct tracks covered: {len(distinct_tracks)} of {TRACK_COUNT} -- {distinct_tracks}]")
        print()
        print(text)
    except Exception as e:
        print(f"[error] {e}")


def main():
    gemini_key = str(config_handler.GEMINI_API_KEY() or "").strip()
    if not gemini_key:
        print("GEMINI_KEY not configured -- cannot run.")
        return
    client = genai.Client(api_key=gemini_key)

    heavy = build_heavy_prompt(ARTIST, ALBUM, LABEL, CATALOG)
    lean = build_lean_prompt(ARTIST, ALBUM, LABEL, CATALOG)

    run("1. HEAVY -- current production prompt", heavy, client)
    run("2. LEAN -- candidate, closer to John's own successful phrasing", lean, client)


if __name__ == "__main__":
    main()

# --- END OF FILE ab_test_lean_prompt.py ---
