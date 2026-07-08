# ==============================================================
# MetaForge Studio: Wikipedia Resolution Engine
# File: wikipedia_resolution_engine.py
# Role: Isolated external truth layer (Wikipedia only) for original-year
# resolution -- Tier 4 of year_resolution_engine.py's waterfall.
#
# Deliberately NOT a reuse of tools/personnel/personnel.py's _search()/
# _fetch_content() -- those are Flask route handlers coupled to
# request/jsonify and can't be imported as plain library functions. The
# HTTP call shape here mirrors that file's proven pattern, rewritten as
# importable functions, targeting the infobox "recorded" field instead
# of Personnel/Musicians/Credits sections.
# ==============================================================

from __future__ import annotations

import re
from typing import Optional

import requests

USER_AGENT = "MetaForgeStudio/1.0 (year-resolution, contact: forensic-dev@metaforge.studio)"
API_URL = "https://en.wikipedia.org/w/api.php"


def _search_album_page(artist: str, album: str) -> Optional[str]:
    """
    Finds the best-matching Wikipedia page title for an artist/album.
    Returns None on any failure or if no result title contains the
    album name (avoids confidently returning an unrelated page).
    """

    query = f'"{album}" {artist} album'

    try:
        response = requests.get(API_URL, params={
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": 5,
        }, headers={"User-Agent": USER_AGENT}, timeout=10)
        response.raise_for_status()

        results = response.json().get("query", {}).get("search", [])
        for r in results:
            if album.lower() in r.get("title", "").lower():
                return r["title"]
    except Exception:
        pass

    return None


def _fetch_wikitext(title: str) -> Optional[str]:
    """
    Fetches the raw wikitext of a page by title. Returns None on any
    failure or if the page doesn't exist.
    """

    try:
        response = requests.get(API_URL, params={
            "action": "query", "prop": "revisions", "titles": title,
            "rvprop": "content", "rvslots": "main", "format": "json",
        }, headers={"User-Agent": USER_AGENT}, timeout=10)
        response.raise_for_status()

        data = response.json()
        pages = data.get("query", {}).get("pages", {})
        page_id = next(iter(pages), None)

        if page_id is None or page_id == "-1":
            return None

        return pages[page_id]["revisions"][0]["slots"]["main"]["*"]
    except Exception:
        return None


def _clean_wikitext(text: str) -> str:
    """Strips common wikitext markup, matching the pattern already
    proven in tools/personnel/personnel.py's _fetch_content()."""

    text = re.sub(r'\{\{[^|}]+\|([^}]+)\}\}', r'\1', text)
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)
    text = re.sub(r'<ref.*?>.*?</ref>', '', text, flags=re.DOTALL)
    text = re.sub(r"'{2,}", "", text)
    return text


def _extract_recorded_field(wikitext: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extracts a 4-digit year from the album infobox's "recorded" field
    (e.g. "| Recorded = 26 December 1939"). Falls back to scanning near
    a "Recorded" label anywhere in the text if no infobox field is
    found. Returns (year, citation_text) -- citation_text is the raw
    matched snippet the year came from, for the correction-candidate log
    in commit_engine.py. Returns (None, None) if nothing confident is
    found.
    """

    match = re.search(r'\|\s*[Rr]ecorded\s*=\s*([^\n|]+)', wikitext)
    if match:
        cleaned = _clean_wikitext(match.group(1))
        year_match = re.search(r'\b(1[5-9]\d{2}|20\d{2})\b', cleaned)
        if year_match:
            return year_match.group(1), cleaned.strip()

    # Fallback: a "Recorded" label followed by a year within a short
    # window, anywhere in the page (looser, only used if the infobox
    # field itself wasn't present).
    fallback = re.search(r'[Rr]ecorded[^\n]{0,60}?\b(1[5-9]\d{2}|20\d{2})\b', wikitext)
    if fallback:
        return fallback.group(1), fallback.group(0).strip()

    return None, None


def resolve_album_recorded_year(artist: str, album: str, year_cache: dict) -> None:
    """
    Single entry point for the year-resolution waterfall: runs the full
    search -> fetch -> extract sequence exactly once per album, and
    memoizes the result (success or failure) into year_cache.

    Also populates wikipedia_evidence (page title/URL + the matched
    citation snippet) for the correction-candidate log in
    commit_engine.py -- same already-fetched wikitext, just not
    discarded this time.
    """

    if year_cache.get("wikipedia_checked"):
        return

    year_cache["wikipedia_checked"] = True
    year_cache["wikipedia_year"] = None
    year_cache["wikipedia_evidence"] = {}

    try:
        title = _search_album_page(artist, album)
        if not title:
            return

        wikitext = _fetch_wikitext(title)
        if not wikitext:
            return

        year, citation_text = _extract_recorded_field(wikitext)
        year_cache["wikipedia_year"] = year
        if year:
            year_cache["wikipedia_evidence"] = {
                "page_title": title,
                "page_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "citation_text": citation_text,
            }
    except Exception:
        pass
