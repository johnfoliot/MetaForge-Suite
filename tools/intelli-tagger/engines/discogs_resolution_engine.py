# ==============================================================
# MetaForge Studio: Discogs Resolution Engine
# File: discogs_resolution_engine.py
# Role: Isolated external truth layer (Discogs only) for original-year
# resolution -- Tier 3 of year_resolution_engine.py's waterfall.
#
# Deliberately separate from common/discogs_engine.py (cover-art search):
# different endpoint shape (numeric release lookup vs. fuzzy image
# search), different consumer contract, and its own session -- does NOT
# import that module's _session, so a problem with the cover-art token
# binding can never silently affect year resolution or vice versa.
# ==============================================================

from __future__ import annotations

import time
import requests
from typing import Any, Dict, Optional

from common import config_handler

TOKEN = config_handler.DISCOGS_TOKEN()
USER_AGENT = "MetaForgeStudio/1.0 (year-resolution)"
SEARCH_URL = "https://api.discogs.com/database/search"
RELEASE_URL = "https://api.discogs.com/releases/{id}"
MASTER_URL = "https://api.discogs.com/masters/{id}"
RATE_LIMIT_DELAY = 0.6  # matches common/discogs_engine.py's established convention

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})
if TOKEN:
    _session.headers.update({"Authorization": f"Discogs token={TOKEN}"})

_last_call = 0.0


def _rate_limited_get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[requests.Response]:
    global _last_call

    elapsed = time.time() - _last_call
    if elapsed < RATE_LIMIT_DELAY:
        time.sleep(RATE_LIMIT_DELAY - elapsed)

    try:
        response = _session.get(url, params=params, timeout=10)
        _last_call = time.time()
        return response
    except Exception:
        _last_call = time.time()
        return None


def search_release_id(artist: str, album: str) -> Optional[str]:
    """
    Finds the Discogs release ID for an artist/album via fuzzy search.
    Returns the top result's numeric ID as a string, or None on any
    failure (auth failure, no results, network error). Never raises.
    """

    response = _rate_limited_get(SEARCH_URL, {
        "q": f"{artist} {album}",
        "type": "release",
    })

    if response is None or response.status_code != 200:
        return None

    try:
        results = response.json().get("results", [])
        if results and results[0].get("id"):
            return str(results[0]["id"])
    except Exception:
        pass

    return None


def _fetch_release_json(release_id: str) -> Optional[Dict[str, Any]]:
    """
    Raw fetch of a Discogs release, unopinionated about what's inside --
    the single point every release-level consumer below reads from, so a
    release with rich `extraartists` but no `notes` text (or vice versa)
    doesn't get its data thrown away by a caller that only cared about one
    of the two. Returns the parsed JSON dict, or None on any failure.
    Never raises.
    """

    if not release_id:
        return None

    response = _rate_limited_get(RELEASE_URL.format(id=release_id))

    if response is None or response.status_code != 200:
        return None

    try:
        return response.json()
    except Exception:
        return None


def get_release_notes_and_tracklist(release_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a Discogs release's notes text and track count. Returns
    {"notes": str, "track_count": int} or None on any failure. Never
    raises -- a missing/empty notes field returns None (nothing useful
    to parse), not an empty-string result.
    """

    data = _fetch_release_json(release_id)
    if not data:
        return None

    notes = data.get("notes", "") or ""
    tracklist = data.get("tracklist", []) or []

    if not notes.strip() or not tracklist:
        return None

    return {"notes": notes, "track_count": len(tracklist)}


def extract_extraartists(release_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Pulls personnel credits out of an already-fetched release JSON --
    Personnel Engine v2's free-riding manifest pre-seed. Deliberately
    independent of notes/tracklist presence (unlike
    get_release_notes_and_tracklist above) -- a release with no notes text
    can still have rich extraartists data, and vice versa.

    Returns {"album": [...], "by_track": {position: [...]}} or None if
    neither album-level nor any track-level extraartists exist.
    """

    album_level = release_data.get("extraartists", []) or []
    tracklist = release_data.get("tracklist", []) or []

    by_track = {}
    for t in tracklist:
        track_extraartists = t.get("extraartists")
        if track_extraartists:
            by_track[t.get("position", "")] = track_extraartists

    if not album_level and not by_track:
        return None

    return {"album": album_level, "by_track": by_track}


def search_master_id(artist: str, album: str) -> Optional[str]:
    """
    Finds the Discogs MASTER release ID for an artist/album -- Discogs'
    own canonical/original-release concept (every pressing/reissue links
    underneath one master), analogous to MusicBrainz's release-group.
    More robust than search_release_id() for a plain album-wide year,
    since it doesn't depend on which single pressing a fuzzy `type=release`
    search happens to surface. Returns the master ID as a string, or
    None on any failure. Never raises.
    """

    response = _rate_limited_get(SEARCH_URL, {
        "q": f"{artist} {album}",
        "type": "master",
    })

    if response is None or response.status_code != 200:
        return None

    try:
        results = response.json().get("results", [])
        if results and results[0].get("id"):
            return str(results[0]["id"])
    except Exception:
        pass

    return None


def get_master_year(master_id: str) -> Optional[str]:
    """
    Fetches a Discogs master release's own `year` field -- the earliest
    year across every pressing/reissue linked to that master. Returns a
    normalized 4-digit year string, or None on any failure. Never raises.
    """

    if not master_id:
        return None

    response = _rate_limited_get(MASTER_URL.format(id=master_id))

    if response is None or response.status_code != 200:
        return None

    try:
        year = response.json().get("year")
        if year and str(year).isdigit() and len(str(year)) == 4:
            return str(year)
    except Exception:
        pass

    return None


def build_track_date_map(notes_text: str, track_count: int) -> Dict[int, str]:
    """
    Parses Discogs notes text into a {track_number: year} mapping via
    the AI extraction tier (ai_engine.extract_track_dates_from_notes).
    Returns an empty dict on any failure -- never raises.
    """

    try:
        import ai_engine
        return ai_engine.extract_track_dates_from_notes(notes_text, track_count)
    except Exception:
        return {}


def resolve_album_track_dates(artist: str, album: str, year_cache: Dict[str, Any]) -> None:
    """
    Single entry point for the year-resolution waterfall: runs the full
    search -> fetch -> extract sequence exactly once per album, and
    memoizes the result (success or failure) into year_cache so it is
    never repeated for other tracks in the same batch.

    Populates THREE independent signals:
    - discogs_master_year: Discogs' own canonical master-release year,
      an album-wide fallback that works for any ordinary album (even one
      whose specific release notes have no date-breakdown text at all).
    - discogs_track_map: per-track years parsed from a specific release's
      notes, for chronological-compilation-style releases needing finer
      granularity than the master year alone provides.
    - discogs_extraartists: Personnel Engine v2's free-riding manifest
      pre-seed (album- and track-level credits) -- reads the SAME release
      JSON already fetched for discogs_track_map above (one fetch, kept in
      a local variable, not re-requested), so this costs zero extra HTTP
      calls and is captured independently of whether notes text exists.
    Each block runs in its own try/except so one failing doesn't suppress
    the others -- a master-search failure shouldn't cost the still-valuable
    notes/personnel paths, and vice versa.
    """

    if year_cache.get("discogs_checked"):
        return

    year_cache["discogs_checked"] = True
    year_cache["discogs_track_map"] = {}
    year_cache["discogs_master_year"] = None
    year_cache["discogs_extraartists"] = None

    try:
        master_id = search_master_id(artist, album)
        if master_id:
            year_cache["discogs_master_year"] = get_master_year(master_id)
    except Exception:
        pass

    try:
        release_id = search_release_id(artist, album)
        if release_id:
            release_data = _fetch_release_json(release_id)
            if release_data:
                notes = release_data.get("notes", "") or ""
                tracklist = release_data.get("tracklist", []) or []
                if notes.strip() and tracklist:
                    year_cache["discogs_track_map"] = build_track_date_map(notes, len(tracklist))
                year_cache["discogs_extraartists"] = extract_extraartists(release_data)
    except Exception:
        pass
