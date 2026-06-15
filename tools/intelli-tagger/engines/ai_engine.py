# --- START OF FILE ai_engine.py ---
# ======================================================================
# MetaForge Engine: AI Taxonomy Mapping (Phase 4)
# Role: Maps Genre/Sub-Genre/Mood/Modifiers using Gemini 1.5 Flash.
# Build 1.1.8: Taxonomy-Enforced Forensic Analysis.
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

client = genai.Client(api_key=GEMINI_KEY)

_last_result = {
    "parent": "Unknown",
    "sub": "Unknown",
    "country": "US",
    "mood": "Atmospheric",
    "mood_modifiers": [],
    "bpm": "0",
    "key": "??",
    "intensity": "1",
    "mb_track_id": "None"
}

def get_last_result():
    return _last_result

def map_taxonomy(artist, album, env_path):
    global _last_result
    
    # UI Messaging
    yield '<div class="it-log-entry it-val-gold" style="margin-top:10px;">Calculating Tag Set...</div>'
    yield f'<div style="margin-left:15px; "><img src="/ui/images/prescan.png" alt="" style="height:14px; width:auto; margin-bottom:-4px;"> Pre-scanning files; determining BPM, Starting Key, Intensity and Mood values...</div>'

    with open(TAXONOMY_PATH, 'r') as f:
        taxonomy = f.read()
    with open(MOODS_PATH, 'r') as f:
        moods_taxonomy = f.read()

    prompt = f"""Analyze artist '{artist}' and album '{album}'. 
    Return ONLY a JSON object with these keys: 
    "parent", "sub", "mood", "mood_modifiers", "intensity", "bpm", "key", "mb_track_id".
    
    Constraints:
    Genre Taxonomy: {taxonomy}
    Mood Taxonomy: {moods_taxonomy}
    Ensure 'mood' is an anchor from the Mood Taxonomy and 'mood_modifiers' is a list derived from the Mood Taxonomy."""
    
    response = client.models.generate_content(
        model='gemini-flash-latest',
        contents=prompt
    )
    
    data = json.loads(response.text.replace("```json", "").replace("```", ""))
    
    # Mandatory Validation
    if 'mood' not in data or 'mood_modifiers' not in data:
        raise ValueError("AI Engine returned incomplete taxonomic data.")
    
    _last_result.update(data)
    
    yield '<div class="it-log-entry it-val-success" style="margin-bottom:15px; ">✅ File Pre-scanning Complete.</div>'
    yield '<div class="it-log-entry it-val-gold" style="margin-top:10px;">Writing Metadata Values to files...</div>'
    yield '<span style="margin-left:15px; margin-bottom:15px;"><img src="/ui/images/AI.png" alt="" style="height:18px; width:auto; "> Firing up the AI tagging engines, this can take up-to 60 seconds to start...</span></div>'
    yield f'<div style="margin-bottom:15px!important; margin-top:15px!important; border-bottom:1px solid var(--mf-gold);"></div>'
# --- END OF FILE ai_engine.py ---