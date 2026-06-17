# --- START OF FILE ai_engine.py ---
# ======================================================================
# MetaForge Engine: AI Taxonomy Mapping (Phase 4)
# Role: Maps Genre/Sub-Genre/Mood/Modifiers using Gemini 1.5 Flash.
# Build 1.1.9: Track-Level Forensic Injection (Logic Only).
# Physical Location: \tools\intelli-tagger\engines\ai_engine.py
# ======================================================================
import json
import time
from pathlib import Path
from google import genai
from google.genai import types
from common import config_handler

TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "data" / "taxonomy.json"
MOODS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "moods.json"
GEMINI_KEY = config_handler.GEMINI_API_KEY

client = genai.Client(
    api_key=GEMINI_KEY
)

def map_track_taxonomy(artist, title, acoustic_data):
    """
    Per-track forensic mapping.
    acoustic_data: dict from acoustic_engine (bpm, key, intensity)
    """
    with open(TAXONOMY_PATH, 'r') as f:
        taxonomy = f.read()
    with open(MOODS_PATH, 'r') as f:
        moods_taxonomy = f.read()

    # The AI now receives the acoustic 'fingerprint' for this specific track
    # No UI messaging inside the engine; reporting is now orchestrated externally.
    prompt = f"""Analyze track '{title}' by '{artist}'.
    Forensic Data: {json.dumps(acoustic_data)}
    Return ONLY a JSON object with these exact keys:
    "parent", "sub", "mood", "sonic_texture", "emotional_flavor", "intensity", "bpm", "key", "mb_track_id".

    Constraints:
    Genre Taxonomy: {taxonomy}
    Mood Taxonomy: {moods_taxonomy}

    The "sonic_texture" and "emotional_flavor" values MUST be selected from the Sonic_Texture and Emotional_Flavor lists in the Mood Taxonomy above, respectively.
    Ensure the full analysis is based on the forensic data provided."""

    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt
    )

    # Parse and Update
    data = json.loads(response.text.replace("```json", "").replace("```", ""))

    # Structural Validation: Ensure sonic_texture and emotional_flavor are present and strings
    sonic_texture = data.get('sonic_texture')
    if not isinstance(sonic_texture, str) or not sonic_texture.strip():
        raise ValueError(
            f"AI Engine returned invalid or missing 'sonic_texture' for '{title}': "
            f"expected a non-empty string, got {repr(sonic_texture)}."
        )
    emotional_flavor = data.get('emotional_flavor')
    if not isinstance(emotional_flavor, str) or not emotional_flavor.strip():
        raise ValueError(
            f"AI Engine returned invalid or missing 'emotional_flavor' for '{title}': "
            f"expected a non-empty string, got {repr(emotional_flavor)}."
        )

    # Merge forensic data with AI taxonomy for the final result packet
    data.update(acoustic_data)
    return data
# --- END OF FILE ai_engine.py ---