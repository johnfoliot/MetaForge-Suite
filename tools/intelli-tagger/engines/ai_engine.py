# --- START OF FILE ai_engine.py ---
# ======================================================================
# MetaForge Engine: AI Taxonomy Mapping (Phase 4)
# Role: Semantic Classification Layer (Authority-Locked)
# Build 2.0.1: Stable Gemini client + strict semantic enforcement
# ======================================================================

import json
from pathlib import Path
from google import genai
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

DO NOT include any other fields.

Artist: {artist}
Title: {title}

Acoustic Data:
{json.dumps(acoustic_data)}

Taxonomy Reference:
{taxonomy}

Mood Reference:
{moods_taxonomy}
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
        "emotional_flavor"
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
        "emotional_flavor": data["emotional_flavor"]
    }

# --- END OF FILE ai_engine.py ---