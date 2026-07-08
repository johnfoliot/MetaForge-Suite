# ==============================================================
# MetaForge Studio: MusicBrainz Resolution Engine
# File: mb_resolution_engine.py
# Role: Isolated external truth layer (MusicBrainz only)
# Build: 1.1.0 — Added get_release_label() for label resolution
# ==============================================================

from __future__ import annotations

import requests
import time
from typing import Dict, Any, Optional, List


def _normalize_mb_year(date_str: Optional[str]) -> Optional[str]:
    """
    MusicBrainz dates are partial: '1975', '1975-06', '1975-06-01', or
    missing entirely. Returns a clean 4-digit year string, or None if the
    input isn't a real, well-formed year.
    """
    if not date_str or not isinstance(date_str, str):
        return None
    year_part = date_str.split("-")[0].strip()
    return year_part if year_part.isdigit() and len(year_part) == 4 else None


class MBResolutionEngine:
    """
    PURE MusicBrainz external resolution layer.

    Responsibilities:
    ------------------
    - MusicBrainz API queries (recording, release, work, artist)
    - Credit / relationship extraction
    - Release-group enrichment
    - External metadata normalization

    Strict Exclusions:
    -------------------
    - NO ID3 writing
    - NO database writes
    - NO file system operations
    - NO fingerprinting (AcoustID belongs elsewhere)
    - NO identity decisions (id_engine owns that)
    """

    BASE_URL = "https://musicbrainz.org/ws/2/"
    USER_AGENT = "MetaForge/1.0 (mb_resolution_engine)"

    def __init__(self, rate_limit_delay: float = 1.0):
        self.rate_limit_delay = rate_limit_delay
        self._last_call = 0.0

    # ----------------------------------------------------------
    # INTERNAL HTTP HANDLER
    # ----------------------------------------------------------

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Controlled MusicBrainz GET wrapper with basic rate limiting.
        """

        now = time.time()
        elapsed = now - self._last_call

        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)

        headers = {
            "User-Agent": self.USER_AGENT
        }

        params = params.copy()
        params["fmt"] = "json"

        url = self.BASE_URL + endpoint

        response = requests.get(url, params=params, headers=headers)
        self._last_call = time.time()

        response.raise_for_status()
        return response.json()

    # ----------------------------------------------------------
    # RECORDING LOOKUP
    # ----------------------------------------------------------

    def get_recording(self, recording_id: str, inc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch MusicBrainz recording entity.
        """

        params = {}

        if inc:
            params["inc"] = "+".join(inc)

        return self._get(f"recording/{recording_id}", params)

    # ----------------------------------------------------------
    # RELEASE LOOKUP
    # ----------------------------------------------------------

    def get_release(self, release_id: str, inc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch MusicBrainz release entity.
        """

        params = {}

        if inc:
            params["inc"] = "+".join(inc)

        return self._get(f"release/{release_id}", params)

    # ----------------------------------------------------------
    # WORK LOOKUP
    # ----------------------------------------------------------

    def get_work(self, work_id: str, inc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch MusicBrainz work entity -- used by Personnel Engine v2's MB
        Work-hop (composer/lyricist/arranger credits, one level out from a
        recording's own artist-rels; see project_personnel_engine_v2 design).
        """

        params = {}

        if inc:
            params["inc"] = "+".join(inc)

        return self._get(f"work/{work_id}", params)

    # ----------------------------------------------------------
    # RELEASE LABEL LOOKUP
    # ----------------------------------------------------------

    def get_release_label(self, release_id: str) -> str:
        """
        Fetch the record label name for a given MusicBrainz release MBID.

        Uses the label-info sub-query on the release endpoint. Label is a
        release-level attribute in MusicBrainz — not track- or recording-level —
        so this should be called once per batch, not per track.

        Returns the label name string, or "Unknown" if unavailable or on error.
        """

        if not release_id or release_id in ("None", "Unknown", ""):
            return "Unknown"

        try:
            data = self.get_release(release_id, inc=["labels"])
            label_info = data.get("label-info", [])

            if label_info:
                first = label_info[0]
                label_obj = first.get("label")

                if label_obj and label_obj.get("name"):
                    return label_obj["name"].strip()

        except Exception:
            pass

        return "Unknown"

    # ----------------------------------------------------------
    # RELEASE GROUP LOOKUP
    # ----------------------------------------------------------

    def get_release_group(self, rg_id: str, inc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch MusicBrainz release-group entity.
        """

        params = {}

        if inc:
            params["inc"] = "+".join(inc)

        return self._get(f"release-group/{rg_id}", params)

    # ----------------------------------------------------------
    # ARTIST LOOKUP
    # ----------------------------------------------------------

    def get_artist(self, artist_id: str, inc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Fetch MusicBrainz artist entity.
        """

        params = {}

        if inc:
            params["inc"] = "+".join(inc)

        return self._get(f"artist/{artist_id}", params)

    # ----------------------------------------------------------
    # SEARCH HELPERS
    # ----------------------------------------------------------

    def search_recordings(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Search recordings by text query.
        """

        return self._get("recording", {
            "query": query,
            "limit": limit
        })

    def search_releases(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Search releases by text query.
        """

        return self._get("release", {
            "query": query,
            "limit": limit
        })

    # ----------------------------------------------------------
    # CREDIT EXTRACTION (NORMALIZED)
    # ----------------------------------------------------------

    def extract_recording_credits(self, recording_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize artist credits from recording response.
        """

        credits = []

        for credit in recording_json.get("artist-credit", []):
            if isinstance(credit, dict) and "artist" in credit:
                artist = credit["artist"]

                credits.append({
                    "artist_id": artist.get("id"),
                    "name": artist.get("name"),
                    "sort_name": artist.get("sort-name"),
                    "join_phrase": credit.get("joinphrase", "")
                })

        return {
            "recording_id": recording_json.get("id"),
            "title": recording_json.get("title"),
            "length": recording_json.get("length"),
            "credits": credits
        }

    # ----------------------------------------------------------
    # ORIGINAL YEAR RESOLUTION (TIER 1)
    # ----------------------------------------------------------

    def get_recording_first_release_date(self, recording_id: str) -> Optional[str]:
        """
        Tier 1 of the original-year waterfall: the recording's own
        first-release-date, which MusicBrainz defines as the earliest
        release date across ALL releases containing this recording --
        not just the one in hand. This is what makes compilations resolve
        correctly for free, with no separate branching needed.

        Returns a normalized 4-digit year string, or None on any failure
        (missing ID, 404 for a bogus/deleted ID, or the field simply being
        empty on the recording). Never raises.
        """
        return self.get_recording_first_release_date_and_relations(recording_id)["year"]

    def get_recording_first_release_date_and_relations(self, recording_id: str) -> Dict[str, Any]:
        """
        Same Tier-1 lookup as get_recording_first_release_date(), widened
        to inc=artist-rels+work-rels -- costs zero extra HTTP round-trips
        (MB's inc values combine into one request), just a larger response
        body. This is Personnel Engine v2's manifest pre-seed free-ride:
        the artist-relationship data (performer/instrument/vocal/producer/
        engineer credits) AND the recording's work-link (needed for the
        composer/lyricist Work-hop -- see mb_personnel_engine.py's
        extract_work_ids()) both ride along on the same call the year
        waterfall already makes once per track, so Intelli-Tagger can
        capture them into manifest.json for Personnel to consume without a
        separate fetch. Returns {"year": <normalized 4-digit str or None>,
        "relations": <raw MB relations list, possibly empty>}. Never raises.
        """

        if not recording_id or recording_id in ("None", "Unknown", ""):
            return {"year": None, "relations": []}

        try:
            data = self.get_recording(recording_id, inc=["artist-rels", "work-rels"])
            return {
                "year": _normalize_mb_year(data.get("first-release-date")),
                "relations": data.get("relations", []) or []
            }
        except Exception:
            return {"year": None, "relations": []}

    # ----------------------------------------------------------
    # RELEASE-GROUP SIMPLIFICATION
    # ----------------------------------------------------------

    def extract_release_group_core(self, rg_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize release-group core metadata.
        """

        return {
            "release_group_id": rg_json.get("id"),
            "title": rg_json.get("title"),
            "primary_type": rg_json.get("primary-type"),
            "first_release_date": rg_json.get("first-release-date"),
            "artist_credit": rg_json.get("artist-credit", [])
        }

    # ----------------------------------------------------------
    # HEALTH CHECK
    # ----------------------------------------------------------

    def ping(self) -> bool:
        """
        Lightweight API sanity check.
        """

        try:
            self.search_recordings("test", limit=1)
            return True
        except Exception:
            return False