# --- START OF FILE year_corrections.py ---
# ======================================================================
# MetaForge Studio: MusicBrainz Submit -- ORIGINAL YEAR CORRECTIONS (parked)
# John parked year submissions on 2026-07-09 (see project memory): a real
# correction means adding a near-empty "format unknown" release to
# MusicBrainz. v2 (2026-11-16) hides the year tab; the Intelli-Tagger keeps
# logging candidates. This is the 1.x year code moved here word for word,
# still reachable through musicbrainz_submit.py's dispatcher, so the tab can
# be brought back without rebuilding it.
# ======================================================================
import json
import html
import re
import traceback
import requests
import pycountry
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from flask import jsonify, request
from common import config_handler, db_engine

CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "original_year_correction_candidates.jsonl"
REVIEW_STATE = config_handler.DATA_DIR / "musicbrainz" / "year_correction_review_state.json"

REMEDIATION_LOG = config_handler.DATA_DIR / "musicbrainz" / "remediation_log.jsonl"


def _log_remediation(entry_type, payload):
    entry = {"type": entry_type, "timestamp": datetime.now().isoformat(), **payload}
    REMEDIATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REMEDIATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

MB_RELEASE_ADD_URL = "https://musicbrainz.org/release/add"
MB_API_USER_AGENT = "MetaForge/1.0 (musicbrainz_submit)"
METAFORGE_HEURISTICS_URL = "https://github.com/johnfoliot/MetaForge-Suite/blob/main/AI%20Heuristics.md"

def _fetch_primary_artist_credit(mb_recording_id):
    """
    Live lookup, not a guess: the seeded artist_credit.names.0.mbid field
    is what makes MB's wizard auto-match the artist (green-highlighted
    field) instead of forcing a manual search -- confirmed live 2026-07-09
    that a plain-text-only artist_credit.names.0.name isn't enough for
    that. Returns {name, mbid} for the recording's first artist credit,
    or None on any failure -- if this lookup fails, the seed just falls
    back to the plain-text name exactly as before, no regression, never
    raises into the caller.
    """
    try:
        from common import mb_client
        res = mb_client.get(
            f"recording/{mb_recording_id}",
            params={"inc": "artist-credits"},
            headers={"User-Agent": MB_API_USER_AGENT},
            timeout=10,
        )
        credits = res.json().get("artist-credit") or []
        if not credits:
            return None
        artist = credits[0].get("artist") or {}
        return {"name": credits[0].get("name") or artist.get("name"), "mbid": artist.get("id")}
    except Exception:
        return None


def _load_review_state():
    if REVIEW_STATE.exists():
        try:
            return json.loads(REVIEW_STATE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_review_state(state):
    REVIEW_STATE.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def _load_candidates():
    """
    Reads the append-only JSONL evidence log and collapses it down to one
    row per mb_recording_id -- the same track can appear multiple times
    if an album was reprocessed, and only the most recent finding is
    authoritative. Never raises on a malformed line; skips it instead,
    since one bad line must never take down the whole review queue.
    """
    if not CANDIDATE_LOG.exists():
        return []

    by_recording = {}
    with open(CANDIDATE_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            rid = entry.get("mb_recording_id")
            if not rid:
                continue
            existing = by_recording.get(rid)
            if not existing or entry.get("timestamp", "") >= existing.get("timestamp", ""):
                by_recording[rid] = entry
    return list(by_recording.values())


def _list_candidates():
    state = _load_review_state()
    candidates = _load_candidates()

    rows = []
    state_dirty = False
    for c in candidates:
        rid = c["mb_recording_id"]
        review = state.get(rid)

        if review and review.get("status") == "submitted" and not review.get("remediation_logged"):
            _log_remediation("year", {
                "mb_recording_id": rid,
                "artist": c.get("artist"),
                "album": c.get("album"),
                "title": c.get("title"),
                "current_release_year": c.get("current_release_year"),
                "proposed_original_year": c.get("proposed_original_year"),
                "orig_year_conf": c.get("orig_year_conf"),
                "orig_year_source": c.get("orig_year_source"),
                "evidence": c.get("evidence"),
            })
            review["remediation_logged"] = True
            state_dirty = True

        rows.append({
            "mb_recording_id": rid,
            "artist": c.get("artist"),
            "album": c.get("album"),
            "title": c.get("title"),
            "current_release_year": c.get("current_release_year"),
            "proposed_original_year": c.get("proposed_original_year"),
            "orig_year_conf": c.get("orig_year_conf"),
            "orig_year_source": c.get("orig_year_source"),
            "evidence": c.get("evidence"),
            "status": review["status"] if review else "pending",
            "status_timestamp": review["timestamp"] if review else None,
        })

    if state_dirty:
        _save_review_state(state)

    # Highest-confidence, still-pending candidates first -- the ones most
    # worth a human's limited review time surface at the top, not buried
    # under low-confidence AI Web Search guesses or already-handled rows.
    rows.sort(key=lambda r: (r["status"] != "pending", -(r["orig_year_conf"] or 0)))

    return jsonify({
        "status": "success",
        "candidates": rows,
        "counts": {
            "pending": sum(1 for r in rows if r["status"] == "pending"),
            "submitted": sum(1 for r in rows if r["status"] == "submitted"),
            "dismissed": sum(1 for r in rows if r["status"] == "dismissed"),
        },
    })


def _mark_handled():
    data = request.json or {}
    rid = data.get("mb_recording_id")
    status = data.get("status")
    if not rid or status not in ("submitted", "dismissed"):
        return jsonify({"status": "error", "message": "mb_recording_id and a valid status are required."}), 400

    state = _load_review_state()
    state[rid] = {"status": status, "timestamp": datetime.now().isoformat()}
    _save_review_state(state)
    return jsonify({"status": "success"})


def _evidence_to_edit_note(candidate):
    """
    Builds the edit_note content John explicitly wants to double as the
    evidence trail, not just internal documentation (confirmed 2026-07-06)
    -- MB community norms value a reproducible, sourced derivation over a
    bare assertion. Shape differs per tier since the evidence itself does:
    Discogs carries structured release/catalog data, AI Web Search carries
    a natural-language citation + its own search sources.

    Now carries MetaForge Studio attribution + a link to AI Heuristics.md
    (John, 2026-07-09) -- supersedes the earlier "no branding" decision
    from earlier the same day, now that there's a real public
    methodology doc for an MB editor to check the claim against, not
    just a bare self-promotion line.

    Built as two PARAGRAPHS (blank line between), not one dense run of
    single-linebreak sentences (John, 2026-07-09: "some more tweaking
    please: (line breaks)") -- the evidence detail is one paragraph,
    the "Resolved via"/attribution footer is its own paragraph, since
    they're a genuinely different kind of content (the actual evidence
    vs. bookkeeping about the note itself).
    """
    source = candidate.get("orig_year_source", "")
    evidence = candidate.get("evidence") or {}
    lines = []

    if source.startswith("Discogs"):
        # date_type only exists when this year came from AI-parsed per-
        # track notes text (source == SRC_DISCOGS), never from Discogs'
        # own structured master-release year (SRC_DISCOGS_MASTER) -- see
        # year_resolution_engine.py. "released" means the notes explicitly
        # described a release date; anything else means this is a
        # recording/session date being used as a proxy, which is a
        # genuinely weaker claim about the RELEASE year specifically
        # (confirmed 2026-07-09: the notes for this exact recording say
        # "Recorded at..." with no release date given at all). Surfaced
        # up front, not buried, so a human reviewer sees the caveat before
        # the supporting detail, not after.
        date_type = evidence.get("date_type")
        if date_type and date_type != "released":
            label = "a recording/session date" if date_type == "recorded" else "an unclear date type"
            lines.append(f"Note: the year below comes from {label} in Discogs' notes, not an explicitly stated release date -- treat as a strong proxy, not a confirmed release date.")

        parts = []
        if evidence.get("catalog_number"): parts.append(f"catalog {evidence['catalog_number']}")
        if evidence.get("label_name"): parts.append(evidence["label_name"])
        if evidence.get("country"): parts.append(evidence["country"])
        if evidence.get("released"): parts.append(f"released {evidence['released']}")
        detail = ", ".join(parts)
        lines.append(f"Evidence: Discogs release data ({detail}) for this recording.")
        if evidence.get("notes_excerpt"):
            lines.append(f"Release notes excerpt: \"{evidence['notes_excerpt']}\"")
        if evidence.get("release_id"):
            lines.append(f"Discogs release: https://www.discogs.com/release/{evidence['release_id']}")
    elif source == "Wikipedia":
        if evidence.get("citation_text"):
            lines.append(f"Evidence: {evidence['citation_text']}")
        if evidence.get("page_title"):
            lines.append(f"Wikipedia page: {evidence.get('page_title')} ({evidence.get('page_url', '')})")
    elif source == "AI Web Search":
        if evidence.get("citation_text"):
            lines.append(f"Evidence: {evidence['citation_text']}")
        if evidence.get("sources"):
            lines.append(f"Sources cited: {', '.join(evidence['sources'])}")
    else:
        lines.append(f"Evidence source tier: {source}")

    footer = f"Resolved via: {source}\nProposed by MetaForge Studio<br>Methodology: {METAFORGE_HEURISTICS_URL}"
    return "\n\n".join(["\n".join(lines), footer])


def _evidence_source_url(candidate):
    """
    A real, verifiable URL for the evidence source, when one exists --
    seeded as a urls.0.url relationship so the new release carries a
    direct link back to where the correction came from. link_type is
    deliberately omitted (confirmed optional per MB's seeding docs) --
    guessing the numeric relationship-type ID isn't worth the risk when
    MB's own wizard just asks the human to pick it interactively instead.
    AI Web Search's `sources` are bare hostnames (e.g. "discogs.com"),
    not full URLs, so there's nothing reliable to link there.
    """
    source = candidate.get("orig_year_source", "")
    evidence = candidate.get("evidence") or {}
    if source.startswith("Discogs") and evidence.get("release_id"):
        return f"https://www.discogs.com/release/{evidence['release_id']}"
    if source == "Wikipedia" and evidence.get("page_url"):
        return evidence["page_url"]
    return None


def _seed_field(name, value):
    if value is None or value == "":
        return ""
    return f'<input type="hidden" name="{html.escape(str(name))}" value="{html.escape(str(value))}">\n'


def _seed_query_params(pairs):
    """
    Builds a URL query string for the Recording relationship editor's
    seeding mechanism (John, 2026-07-13). Switched from a POST-submitted
    hidden-field form (_seed_field, above) after live-confirming that
    /recording/{id}/edit only reads rels.N.*/edit_note from the URL's own
    query string -- a POST body loaded a real, completely blank edit
    page instead (Relationships and Edit note both empty, even though the
    browser's own "confirm form submission" dialog correctly showed the
    POST data being sent). This matches the ORIGINAL live-tested
    mechanism from 2026-07-09, which used a GET query string throughout
    -- the POST-form implementation had quietly drifted from it. Note
    this does NOT apply to the date-correction seeding elsewhere in this
    file (_build_seed_html, /release/add) -- that target was separately
    confirmed to require an actual POST (see project_mb_contribution_tool
    memory, 2026-07-09), so it's untouched. Skips None/empty values, same
    as _seed_field.
    """
    return urlencode([(k, v) for k, v in pairs if v not in (None, "")])


def _country_to_iso(name):
    """
    Discogs' `country` field is a free-text display name ("Jamaica"), but
    MB's seed form's events.0.country expects an ISO 3166-1 alpha-2 code
    (confirmed live 2026-07-09: seeding raw "JAMAICA" produced "Invalid
    events.0.country" -- MB's own release API returns country the same
    way MetaForge already reads it in musicbrainz_id.py, alpha-2). Only
    applied here at the seed field -- _evidence_to_edit_note's prose stays
    the human-readable Discogs name on purpose, that's for a person to
    read, not MB's form parser.

    search_fuzzy() handles real-world Discogs values like "UK"/"USA" that
    aren't a country's official ISO name. Deliberately returns None (field
    left blank for John to fill in manually) rather than guessing on
    Discogs values that aren't a real single country at all -- "Europe",
    "Worldwide", "US & Canada" all genuinely have no ISO alpha-2 code, and
    a wrong guess here would be worse than an empty field MB's wizard
    already handles fine.
    """
    if not name:
        return None
    try:
        return pycountry.countries.search_fuzzy(name)[0].alpha_2
    except LookupError:
        return None


def _build_seed_html(candidate):
    """
    Builds an auto-submitting HTML form POSTing to MusicBrainz's real Add
    Release wizard (musicbrainz.org/doc/Development/Seeding/Release_Editor
    -- confirmed live 2026-07-09 this is a POST endpoint, not a plain GET
    query string, so a clickable link alone can't seed it). Only fields
    MetaForge has real evidence for are pre-filled -- country/label/
    catalog data from a Discogs-sourced candidate genuinely describes the
    REISSUE release the evidence came from, not confirmed to be identical
    to the true original pressing being added here, so it's passed
    through as a useful lead for John's own review inside MB's wizard,
    never silently trusted. Format/barcode/release-group type are left
    entirely blank -- no evidence exists for those at all, and guessing
    would violate the "never fabricate" rule applied everywhere else in
    this pipeline. mediums.0.track.0.recording is the one field that MUST
    be correct -- it's what links the new release to the EXISTING
    recording instead of creating a duplicate.

    Live-fetches the recording's own primary artist credit (name + MBID)
    -- confirmed live 2026-07-09 that a plain-text-only artist name isn't
    enough for MB's wizard to auto-match the artist field (it stays
    unhighlighted, requiring a manual search), and the wizard blocks
    submission on both the release-level AND every track-level artist
    field until matched. Falls back to the plain evidence-log artist
    string if the live lookup fails for any reason -- same behavior as
    before, not a regression, just no auto-match in that edge case.
    """
    evidence = candidate.get("evidence") or {}
    artist_lookup = _fetch_primary_artist_credit(candidate.get("mb_recording_id"))
    artist_name = (artist_lookup or {}).get("name") or candidate.get("artist")
    artist_mbid = (artist_lookup or {}).get("mbid")

    fields = (
        _seed_field("name", candidate.get("title"))
        + _seed_field("artist_credit.names.0.name", artist_name)
        + _seed_field("artist_credit.names.0.artist.name", artist_name)
        + _seed_field("artist_credit.names.0.mbid", artist_mbid)
        + _seed_field("events.0.date.year", candidate.get("proposed_original_year"))
        + _seed_field("events.0.country", _country_to_iso(evidence.get("country")))
        + _seed_field("labels.0.name", evidence.get("label_name"))
        + _seed_field("labels.0.catalog_number", evidence.get("catalog_number"))
        + _seed_field("mediums.0.track.0.name", candidate.get("title"))
        + _seed_field("mediums.0.track.0.number", "1")
        + _seed_field("mediums.0.track.0.recording", candidate.get("mb_recording_id"))
        + _seed_field("mediums.0.track.0.artist_credit.names.0.name", artist_name)
        + _seed_field("mediums.0.track.0.artist_credit.names.0.mbid", artist_mbid)
        + _seed_field("urls.0.url", _evidence_source_url(candidate))
        + _seed_field("edit_note", _evidence_to_edit_note(candidate))
    )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Opening MusicBrainz...</title></head>
<body>
<p>Opening MusicBrainz Release Editor, pre-filled from MetaForge Studio's evidence...</p>
<form id="mb-seed-form" method="POST" action="{html.escape(MB_RELEASE_ADD_URL)}">
{fields}</form>
<script>document.getElementById('mb-seed-form').submit();</script>
</body>
</html>"""


def _build_seed():
    data = request.json or {}
    rid = data.get("mb_recording_id")
    if not rid:
        return jsonify({"status": "error", "message": "mb_recording_id is required."}), 400

    candidates = {c["mb_recording_id"]: c for c in _load_candidates()}
    candidate = candidates.get(rid)
    if not candidate:
        return jsonify({"status": "error", "message": "Candidate not found."}), 404

    seed_html = _build_seed_html(candidate)
    return jsonify({
        "status": "success",
        "html": seed_html,
        "title": f"MusicBrainz: {candidate.get('title', 'Release')}",
    })

# --- END OF FILE year_corrections.py ---
