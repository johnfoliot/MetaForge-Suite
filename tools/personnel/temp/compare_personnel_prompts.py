# --- START OF FILE compare_personnel_prompts.py ---
# ======================================================================
# One-off dev script, NOT part of the app. Compares personnel-credit
# search quality across:
#   1. PRODUCTION  -- the real resolve_personnel_ai() prompt/parser as
#      shipped in tools/intelli-tagger/engines/ai_engine.py, run against
#      Gemini exactly as Personnel Scout calls it today.
#   2. GEMINI_TRACK -- a candidate track-by-track prompt, same model.
#   3. CLAUDE_TRACK -- the same candidate track-by-track prompt, run
#      against Claude's web_search tool instead.
#
# Purpose: isolate two variables John raised in the same conversation --
# (a) does asking for a track-by-track breakdown surface better data
#     regardless of provider, and
# (b) does Claude's search/grounding out-perform Gemini's for this task.
# Comparing PRODUCTION vs GEMINI_TRACK answers (a) on a fixed provider;
# comparing GEMINI_TRACK vs CLAUDE_TRACK answers (b) on a fixed prompt.
#
# Usage:
#   set ANTHROPIC_API_KEY=sk-ant-...   (or export on bash)
#   python compare_personnel_prompts.py "Clancy Eccles" "Feel The Rhythm" --tracks 28
#
# Requires GEMINI_KEY already configured in %APPDATA%\MetaForge\.env
# (same as the real app) and ANTHROPIC_API_KEY in the environment (kept
# OUT of the app's own .env deliberately -- this is a dev-only tool, not
# a shipped credential).
# ======================================================================

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "intelli-tagger" / "engines"))

from google import genai
from google.genai import types
from common import config_handler

import ai_engine  # tools/intelli-tagger/engines/ai_engine.py -- the real production module


# ---------------------------------------------------------------------
# Candidate track-by-track prompt. Deliberately keeps MetaForge's
# never-fabricate contract intact: John's own manual Google test
# produced genuinely useful per-track detail, but ALSO silently
# pattern-completed the "core house band" onto tracks with no per-track
# citation at all -- confident-looking, not necessarily grounded per
# track. This prompt forces the model to say which regime each line
# came from instead of blending them, which the earlier ungrounded
# result never did.
# ---------------------------------------------------------------------
def build_track_by_track_prompt(artist, album, track_count=None, label=None, catalog=None):
    count_line = (
        f'This release has {track_count} tracks.\n'
        if track_count else ""
    )
    release_id_bits = [b for b in [
        f'label "{label}"' if label else None,
        f'catalog number "{catalog}"' if catalog else None,
    ] if b]
    release_line = (
        f"The specific release I'm asking about is identified by {' and '.join(release_id_bits)} "
        f"-- use this to confirm you have the right release, not a same-titled reissue or "
        f"compilation on a different label.\n"
        if release_id_bits else ""
    )
    return f"""Search the web to find out who performed on and contributed to
the album "{album}" by {artist}.
{count_line}{release_line}
First, confirm which specific release you found (label, year, format) --
if multiple different releases share this artist/title combination, say
so explicitly and state which one your search results actually describe.
Do not silently pick one.

Then produce a TRACK-BY-TRACK personnel breakdown, not just an album-level
summary. For each track, distinguish clearly between two different kinds
of evidence -- do not blend them:
  (a) CONFIRMED FOR THIS TRACK: a source explicitly documents personnel
      for this specific track (liner notes, a discography entry keyed to
      track/session, a review naming the specific performance).
  (b) ALBUM-LEVEL / INFERRED: personnel documented for the release or
      artist generally (e.g. "the house band for this label's sessions
      was X, Y, Z"), but NOT confirmed track-by-track. If you apply this
      to a track only because it's the general house band and the track
      itself has no specific documentation, label it as such -- do not
      present it with the same confidence as (a).

If you cannot find genuine track-level detail for most tracks, say so
plainly rather than filling every track in with the same inferred list.

Describe your findings in natural language first, citing where each piece
of information came from.

Then end your response with a section starting with exactly the line
CREDITS: followed by one line per credit, in this format:
Track N: Name - Role [confirmed]
Track N: Name - Role [inferred]
Album: Name - Role [confirmed]

Use "Album:" instead of a track number for album-wide credits (producer,
songwriter, etc.) that aren't track-specific by nature.

If your search genuinely finds nothing, end with CREDITS: UNKNOWN instead.
NEVER guess or fabricate a name or role with no basis.
"""


def run_gemini_production(artist, album):
    print("\n" + "=" * 78)
    print("1. PRODUCTION -- current resolve_personnel_ai() as shipped, Gemini")
    print("=" * 78)
    try:
        results = ai_engine.resolve_personnel_ai(artist, album)
    except Exception as e:
        print(f"[error] {e}")
        return
    if not results:
        print("(no grounded results -- production prompt returned nothing)")
        return
    for r in results:
        print(f"  {r['name']} -- {r['role']}")
    sources = results[0].get("sources") if results else None
    if sources:
        print(f"\n  sources: {', '.join(sources)}")


def run_gemini_track_by_track(artist, album, track_count, label=None, catalog=None):
    print("\n" + "=" * 78)
    print("2. GEMINI_TRACK -- candidate track-by-track prompt, Gemini")
    print("=" * 78)

    gemini_key = str(config_handler.GEMINI_API_KEY() or "").strip()
    if not gemini_key:
        print("[skipped] GEMINI_KEY not configured")
        return
    client = genai.Client(api_key=gemini_key)

    prompt = build_track_by_track_prompt(artist, album, track_count, label, catalog)
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        text = response.text or ""
        candidate = response.candidates[0] if response.candidates else None
        grounding = getattr(candidate, "grounding_metadata", None) if candidate else None
        chunks = getattr(grounding, "grounding_chunks", None) if grounding else None
        grounded = bool(chunks)
        print(f"[grounded search actually ran: {grounded}]\n")
        print(text)
        if chunks:
            titles = [
                web.title for chunk in chunks[:8]
                if (web := getattr(chunk, "web", None)) and getattr(web, "title", None)
            ]
            print(f"\n  sources: {', '.join(titles)}")
    except Exception as e:
        print(f"[error] {e}")


def run_claude_track_by_track(artist, album, track_count, label=None, catalog=None):
    print("\n" + "=" * 78)
    print("3. CLAUDE_TRACK -- same candidate prompt, Claude web_search")
    print("=" * 78)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[skipped] ANTHROPIC_API_KEY not set in environment")
        return

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_track_by_track_prompt(artist, album, track_count, label, catalog)

    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        text_parts = []
        sources = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "web_search_tool_result":
                content = block.content
                if isinstance(content, list):
                    for item in content:
                        title = getattr(item, "title", None)
                        if title:
                            sources.append(title)

        print("\n".join(text_parts))
        if sources:
            print(f"\n  sources: {', '.join(sources[:8])}")
    except Exception as e:
        print(f"[error] {e}")


def main():
    parser = argparse.ArgumentParser(description="Compare personnel-credit search prompts across Gemini and Claude.")
    parser.add_argument("artist")
    parser.add_argument("album")
    parser.add_argument("--tracks", type=int, default=None, help="Track count, for context in the track-by-track prompt")
    parser.add_argument("--label", default=None, help="Label name, to disambiguate the release (quote it if it has spaces)")
    parser.add_argument("--catalog", default=None, help="Catalog number, to disambiguate the release (quote it if it has spaces)")
    parser.add_argument("--skip-production", action="store_true")
    parser.add_argument("--skip-gemini-track", action="store_true")
    parser.add_argument("--skip-claude-track", action="store_true")
    args = parser.parse_args()

    print(f"Artist: {args.artist}")
    print(f"Album:  {args.album}")
    if args.tracks:
        print(f"Tracks: {args.tracks}")
    if args.label:
        print(f"Label:  {args.label}")
    if args.catalog:
        print(f"Catalog: {args.catalog}")

    if not args.skip_production:
        run_gemini_production(args.artist, args.album)
    if not args.skip_gemini_track:
        run_gemini_track_by_track(args.artist, args.album, args.tracks, args.label, args.catalog)
    if not args.skip_claude_track:
        run_claude_track_by_track(args.artist, args.album, args.tracks, args.label, args.catalog)


if __name__ == "__main__":
    main()

# --- END OF FILE compare_personnel_prompts.py ---
