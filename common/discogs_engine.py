# --- START OF FILE discogs_engine.py ---
# ======================================================================
# MetaForge Shared Primitive: Discogs Engine
# Role: Fetches high-fidelity primary covers from Discogs.
# Physical Location: \common\discogs_engine.py
# Build 1.0.3: Flattened Functional Structure (Compatibility Restore).
# Role: Preserves Build 1.0.1 Logic while fixing Spoke access.
# ======================================================================
import requests
import sys
import time
from pathlib import Path

# --- [ PATH BOOTSTRAP ] ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler, image_processor

# --- [ ARCHITECTURAL CONSTANTS ] ---
TOKEN = getattr(config_handler, 'DISCOGS_TOKEN', None)
USER_AGENT = "MetaForgeSuite/1.2 +http://metaforge.audio"
BASE_URL = "https://api.discogs.com/database/search"

# Maintain a module-level session for connection pooling (Build 1.0.1 parity)
_session = requests.Session()
_session.headers.update({
    "User-Agent": USER_AGENT,
    "Authorization": f"Discogs token={TOKEN}"
})

def fetch_archival_cover(artist, album, target_dir):
    """
    Executes a fuzzy keyword search for the primary album cover.
    1. Uses combined keyword query (q) for maximum discovery.
    2. Filters by type (master then release).
    3. Downloads and applies 500x500 Archival Fit.
    """
    if not TOKEN:
        return {"status": "error", "message": "Discogs Token missing from .env"}

    target_dir = Path(target_dir)
    dest_path = target_dir / "folder.jpg"

    # Step 1: Broad Keyword Discovery
    cover_url = _search_for_image_url(artist, album)
    
    if not cover_url:
        return {"status": "error", "message": f"Discogs: No image URL found for {artist} - {album}"}

    try:
        # Step 2: High-Resolution Retrieval
        response = _session.get(cover_url, timeout=15)
        response.raise_for_status()
        image_bytes = response.content

        # Step 3: Archival Standard Hand-off
        # Ensures 500x500 centered crop via common processor
        result = image_processor.apply_archival_fit(image_bytes, dest_path)
        
        if result['status'] == 'success':
            return {
                "status": "success",
                "source": "Discogs Archive",
                "filename": "folder.jpg",
                "dims": result['dims']
            }
        return result

    except Exception as e:
        return {"status": "error", "message": f"Discogs Download Failed: {str(e)}"}

def _search_for_image_url(artist, album):
    """
    Internal search orchestrator.
    Uses the 'q' parameter for fuzzy matching to bypass strict index naming.
    """
    search_query = f"{artist} {album}"
    
    # Priority 1: Master Release (The curated "Parent" image)
    params = {
        "q": search_query,
        "type": "master"
    }
    
    try:
        # First Pass: Master
        res = _session.get(BASE_URL, params=params)
        time.sleep(0.6) # Rate limit respect (60 req/min)
        
        if res.status_code == 200:
            data = res.json()
            results = data.get('results', [])
            if results and results[0].get('cover_image'):
                # Discogs returns a placeholder if no image exists; we filter it
                img_url = results[0]['cover_image']
                if "spacer.gif" not in img_url:
                    return img_url

        # Second Pass: Specific Release (Fallback)
        params["type"] = "release"
        res = _session.get(BASE_URL, params=params)
        time.sleep(0.6)
        
        if res.status_code == 200:
            data = res.json()
            results = data.get('results', [])
            if results and results[0].get('cover_image'):
                img_url = results[0]['cover_image']
                if "spacer.gif" not in img_url:
                    return img_url

    except Exception as e:
        print(f"DEBUG: Discogs Search Error: {e}")
        return None
    
    return None

# --- [ DIAGNOSTIC SUITE ] ---
if __name__ == "__main__":
    print("\n--- MetaForge Primitive Diagnostic: Discogs Engine (Build 1.0.3) ---")
    
    print(f"[1/2] API Key Check...", end=" ")
    if TOKEN: print("PASS")
    else: print("FAIL")

    print(f"[2/2] Fuzzy Search Test (John Stewart Willard)...", end=" ")
    url = _search_for_image_url("John Stewart", "Willard")
    if url and "discogs" in url:
        print(f"PASS\n      URL Found: {url[:60]}...")
    else:
        print("FAIL")

# --- END OF FILE discogs_engine.py ---