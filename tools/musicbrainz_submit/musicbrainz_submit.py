# --- START OF FILE musicbrainz_submit.py ---
# ======================================================================
# MetaForge Studio: MusicBrainz Submit
# Role: Review queue for high-confidence original-year corrections the
# resolution waterfall found that MusicBrainz's own data doesn't have --
# builds a seeded MusicBrainz Release Editor submission per candidate,
# opened in a companion "pseudo-tab" window for the user to review and
# submit themselves through MB's own real wizard. MetaForge never
# authenticates to or submits anything to MusicBrainz directly -- see
# project_mb_contribution_tool memory for why the API has no write path
# for this at all, only the website's own editor.
# Physical Location: \tools\musicbrainz_submit\musicbrainz_submit.py
# ======================================================================
import json
import html
import re
import traceback
import requests
import pycountry
from datetime import datetime
from pathlib import Path
from flask import jsonify, request
from common import config_handler, db_engine

CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "original_year_correction_candidates.jsonl"
REVIEW_STATE = config_handler.DATA_DIR / "musicbrainz" / "year_correction_review_state.json"
PERSONNEL_CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "personnel_correction_candidates.jsonl"
PERSONNEL_REVIEW_STATE = config_handler.DATA_DIR / "musicbrainz" / "personnel_correction_review_state.json"

MB_RELEASE_ADD_URL = "https://musicbrainz.org/release/add"
MB_API_USER_AGENT = "MetaForge/1.0 (musicbrainz_submit)"

# Public methodology doc explaining how MetaForge derives the evidence in
# every edit note below -- linked from every submission (John, 2026-07-09,
# supersedes the earlier "no MetaForge branding" decision from 2026-07-09
# earlier the same day; the doc's existence is the reason the reversal
# makes sense, an MB editor now has somewhere real to verify the claims
# instead of being asked to trust an anonymous tool).
METAFORGE_HEURISTICS_URL = "https://github.com/johnfoliot/MetaForge-Suite/blob/main/AI%20Heuristics.md"

# Confirmed live 2026-07-09 by inspecting the real "Add relationship"
# autocomplete DOM on an existing recording's /edit page (not guessed,
# not from docs -- MB's own seeding docs don't cover this page at all).
# Each numeric ID is the recording-artist link_type MB actually uses.
# COMPOSED/WRITTEN_BY are deliberately absent: composer/writer/publisher
# never appeared in the captured dropdown at all, and the one adjacent
# entry that IS there ("published/publisher") carries MB's own tooltip
# "Publishers should be added on works instead" -- confirming those are
# Work-level facts, not Recording-level, and need a separate, unresearched
# mechanism. "Mastering" (136) is present but explicitly deprecated by MB
# ("add mastering engineers at the release level") -- excluded on purpose.
RELATION_TYPE_TO_LINK_TYPE = {
    "PERFORMED_ON": 156,   # performed / performer (generic; MB has finer
                           # sub-types like instruments=148/vocals=149 but
                           # MetaForge's own role text isn't reliably that
                           # specific yet)
    "PRODUCED": 141,       # produced / producer
    "ENGINEERED_BY": 138,  # engineered / engineer (general role; MB also
                           # has mixer=143/recording engineer=128/audio
                           # engineer=140 as more specific sub-types)
    "ARRANGED_BY": 297,    # arranged / arranger
    "A_AND_R": 135,        # artist & repertoire support
    "ASSOCIATED_WITH": 129,  # miscellaneous roles / miscellaneous support
}

UNSUPPORTED_RELATION_TYPES = {"COMPOSED", "WRITTEN_BY"}


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
        res = requests.get(
            f"https://musicbrainz.org/ws/2/recording/{mb_recording_id}",
            params={"inc": "artist-credits", "fmt": "json"},
            headers={"User-Agent": MB_API_USER_AGENT},
            timeout=10,
        )
        res.raise_for_status()
        credits = res.json().get("artist-credit") or []
        if not credits:
            return None
        artist = credits[0].get("artist") or {}
        return {"name": credits[0].get("name") or artist.get("name"), "mbid": artist.get("id")}
    except Exception:
        return None


def run_logic(action, tools_dir, env_path):
    try:
        if action == "list_candidates": return _list_candidates()
        if action == "build_seed": return _build_seed()
        if action == "mark_handled": return _mark_handled()
        if action == "list_personnel_candidates": return _list_personnel_candidates()
        if action == "build_personnel_seed": return _build_personnel_seed()
        if action == "mark_personnel_handled": return _mark_personnel_handled()
        if action == "mark_track_progress": return _mark_track_progress()
        if action == "apply_track_selection": return _apply_track_selection()
        if action == "build_bulk_personnel_seed": return _build_bulk_personnel_seed()
        return jsonify({"status": "error", "message": f"Action '{action}' unrecognized."}), 404
    except Exception:
        print(f"🔥 MusicBrainz Submit Hub Error [{action}]:\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": "Internal processing error."}), 500


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
    for c in candidates:
        rid = c["mb_recording_id"]
        review = state.get(rid)
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

    footer = f"Resolved via: {source}\nProposed by MetaForge Studio -- methodology: {METAFORGE_HEURISTICS_URL}"
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


# ==========================================================================
# PERSONNEL CORRECTIONS (Phase 2 -- Recording relationship seeding,
# confirmed live 2026-07-09, see project_mb_contribution_tool memory)
# ==========================================================================

def _load_personnel_review_state():
    if PERSONNEL_REVIEW_STATE.exists():
        try:
            return json.loads(PERSONNEL_REVIEW_STATE.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_personnel_review_state(state):
    PERSONNEL_REVIEW_STATE.parent.mkdir(parents=True, exist_ok=True)
    PERSONNEL_REVIEW_STATE.write_text(json.dumps(state, indent=2), encoding='utf-8')


def _candidate_key(c):
    """
    A track-scoped candidate (real mb_recording_id) keys on that
    recording, same as before. An album-scoped candidate (AI Web
    Search/manual entries -- inherently "this person played on the
    album," not any one track) has no single recording to key on, so it
    keys on the album (mf_id) instead -- one queue row per person/role
    per album, stepped through track-by-track via the stepper UI rather
    than needing N separate rows (John, 2026-07-09).
    """
    rid = c.get("mb_recording_id")
    scope = rid if rid else c.get("mf_id")
    return f"{scope}|{c.get('name')}|{c.get('relation_type')}|{c.get('role')}"


def _get_album_tracks(mf_id, _cache={}):
    """
    Ordered {recording_id, track_number, title} list for this album's
    tracks that actually have a captured MB recording ID -- the set of
    targets an album-scoped credit's stepper walks through, one MB
    Recording edit per track. Sourced directly from the `tracks` table
    (mf_id is the real library_master.mf_id, already logged alongside
    every personnel candidate) rather than manifest.json, since the
    queue only has artist/album/mf_id to go on, not a local folder path.

    BUG FIX (John, 2026-07-09, caught live via a real "Recording not
    found" MusicBrainz error): this originally selected tracks.mb_track_id
    and used it as the recording ID. The `tracks` table actually has TWO
    separate, correctly-distinct columns -- mb_track_id (MusicBrainz's
    Track entity, release-tracklist-specific, captured in
    musicbrainz_id.py's get_release_details()/commit_ids_to_files() and
    written to its own column by commit_engine.py) and mb_recording_id
    (the actual Recording entity -- the only one valid at MB's
    /recording/{id} endpoint, which is everything this stepper needs).
    Both columns were always populated correctly by the rest of the
    pipeline; this function alone was reading the wrong one. Confirmed
    live: mb_track_id 404's against MusicBrainz's real API, mb_recording_id
    for the same row resolves correctly.

    Order comes from the leading number in each file's own filename
    (this pipeline's established naming convention, e.g. "12 - Artist -
    Title.mp3") -- the tracks table itself has no explicit position
    column. Cached per mf_id for the life of the process: one album's
    several album-scoped credits all need the identical list, and it
    doesn't change within a session.
    """
    if mf_id in _cache:
        return _cache[mf_id]
    rows = db_engine.execute_query(
        "SELECT file_path, title, mb_recording_id FROM tracks WHERE mf_id=? AND mb_recording_id IS NOT NULL AND mb_recording_id != ''",
        (mf_id,)
    ) or []
    tracks = []
    for r in rows:
        m = re.match(r'^\s*(\d+)', Path(r['file_path']).name)
        track_number = int(m.group(1)) if m else 9999
        tracks.append({"recording_id": r['mb_recording_id'], "title": r['title'], "track_number": track_number})
    tracks.sort(key=lambda t: t['track_number'])
    _cache[mf_id] = tracks
    return tracks


def _live_edges_for_album(mf_id, _cache={}):
    """
    Set of (target_id, normalized role) pairs the `edges` table
    currently, actually has for this album -- used to filter personnel
    candidates against what MetaForge's own database still believes
    (John, 2026-07-10, caught live: manually deleted a polluted
    personnel list from the database before re-running Personnel Scout,
    but MB Submit kept proposing the deleted person anyway -- confirmed
    live, "Arkland Parks" had zero rows in `edges` but was still sitting
    in the JSONL evidence log, since that log is append-only and nothing
    anywhere reconciles it against DB-side deletions). A candidate whose
    underlying fact no longer exists in the database shouldn't be
    proposed to MusicBrainz at all -- MetaForge itself no longer
    believes it. Cached per mf_id for the life of the process, same
    pattern as _get_album_tracks.
    """
    if mf_id in _cache:
        return _cache[mf_id]
    rows = db_engine.execute_query(
        "SELECT target_id, role FROM edges WHERE source_id=? AND source_type='album'",
        (mf_id,)
    ) or []
    result = {(r["target_id"], (r["role"] or "").strip().lower()) for r in rows}
    _cache[mf_id] = result
    return result


def _load_personnel_candidates():
    """
    Reads the append-only personnel evidence log and collapses it to one
    row per (target scope, name, relation_type, role) -- see
    _candidate_key(). The same person can legitimately be credited with
    different roles on the same recording/album (that's a different fact
    each time), but an exact repeat just needs the latest occurrence.

    Album-scoped candidates (no mb_recording_id) are no longer dropped
    here (John, 2026-07-09) -- they used to be, on the reasoning that
    there's no single Recording page to seed. That silently excluded
    almost all AI Web Search/manual personnel data, which is
    album-scoped by nature, from ever reaching this queue at all. They
    now flow through and get a per-track stepper in the UI instead (see
    _get_album_tracks/_mark_track_progress).

    Still filters out, rather than surfacing as "actionable":
    - COMPOSED/WRITTEN_BY relation types -- confirmed Work-level, not
      Recording-level; no seeding mechanism researched for those yet.
    - Anything is_junk_role()/is_junk_name() would now reject -- some
      entries in the live log predate junk-role fixes made earlier the
      same day (e.g. "Compilation Producer", "Remastered By"), so this
      is a real re-check against current rules, not a redundant one.
    - A bare "Primary Artist"/"Performer"-type credit for the album's
      OWN artist (John, 2026-07-09, caught reviewing the live queue
      himself: "is this perhaps a bit too redundantly redundant?").
      MusicBrainz's Recording already carries its own artist_credit --
      a contentless relationship that just re-states "the artist
      performed on their own recording," with no instrument/vocal/role
      detail beyond that, tells MB nothing it doesn't already know and
      reads as noise to an MB editor. Deliberately scoped to ONLY this
      queue, not Personnel Scout's own commit path -- "this artist
      performed on this album" is still real, useful connective-tissue
      data for MetaForge's own Personnel Bridge use case (see
      project_personnel_engine_v2 memory), it's specifically
      MB-submission-redundant, not database-redundant. A role with any
      real detail (an instrument, "Vocals", "Producer", etc.) is NOT
      filtered here -- only the bare self-evident label itself.
    - Anything no longer present in the `edges` table (see
      _live_edges_for_album) -- the log is append-only evidence, not a
      live mirror of the database; a fact deleted from the DB after
      being logged must not still be proposed to MusicBrainz.
    """
    if not PERSONNEL_CANDIDATE_LOG.exists():
        return []

    from tools.personnel.edge_normalizer import is_junk_role, is_junk_name, load_config
    config = load_config()

    REDUNDANT_SELF_CREDIT_ROLES = {"primary artist", "artist", "main artist", "performer", "lead artist"}

    by_key = {}
    with open(PERSONNEL_CANDIDATE_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue

            if entry.get("relation_type") in UNSUPPORTED_RELATION_TYPES:
                continue
            if entry.get("relation_type") not in RELATION_TYPE_TO_LINK_TYPE:
                continue
            if is_junk_role(entry.get("role", ""), config) or is_junk_name(entry.get("name", ""), config):
                continue
            if (entry.get("relation_type") == "PERFORMED_ON"
                    and (entry.get("role") or "").strip().lower() in REDUNDANT_SELF_CREDIT_ROLES
                    and (entry.get("name") or "").strip().lower() == (entry.get("artist") or "").strip().lower()):
                continue
            live_pair = (entry.get("target_id"), (entry.get("role") or "").strip().lower())
            if entry.get("mf_id") and live_pair not in _live_edges_for_album(entry["mf_id"]):
                continue  # deleted from the database since this was logged -- don't propose it

            key = _candidate_key(entry)
            existing = by_key.get(key)
            if not existing or entry.get("timestamp", "") >= existing.get("timestamp", ""):
                by_key[key] = entry
    return list(by_key.values())


def _list_personnel_candidates():
    """
    Track-scoped candidates (real mb_recording_id) work exactly as
    before -- one row, one status. Album-scoped candidates get a
    per-track stepper instead: album_tracks is the ordered list of
    recording targets, track_progress records which of them have been
    submitted/skipped so far, and the row's overall status is DERIVED
    from that progress rather than stored directly (John, 2026-07-09) --
    "in_progress" once any track is done, "submitted" once every track
    the album has a recording ID for has been accounted for. A manual
    "dismissed" always wins outright, same as the track-scoped case,
    since that's an explicit bail-out regardless of partial progress.
    """
    state = _load_personnel_review_state()
    candidates = _load_personnel_candidates()

    rows = []
    for c in candidates:
        key = _candidate_key(c)
        review = state.get(key) or {}
        rid = c.get("mb_recording_id")

        if rid:
            album_tracks = None
            track_progress = None
            status = review.get("status", "pending")
        else:
            album_tracks = _get_album_tracks(c["mf_id"])
            track_progress = review.get("track_progress", {}) or {}
            if review.get("status") == "dismissed":
                status = "dismissed"
            elif not album_tracks or len(track_progress) == 0:
                status = "pending"
            elif len(track_progress) < len(album_tracks):
                status = "in_progress"
            else:
                status = "submitted"

        rows.append({
            "key": key,
            "mb_recording_id": rid,
            "mb_target_mbid": c.get("mb_target_mbid"),
            "artist": c.get("artist"),
            "album": c.get("album"),
            "name": c.get("name"),
            "relation_type": c.get("relation_type"),
            "role": c.get("role"),
            "provenance": c.get("provenance"),
            "confidence": c.get("confidence"),
            "status": status,
            "album_tracks": album_tracks,
            "track_progress": track_progress,
        })

    rows.sort(key=lambda r: (r["status"] not in ("pending", "in_progress"), -(r["confidence"] or 0)))

    return jsonify({
        "status": "success",
        "candidates": rows,
        "counts": {
            "pending": sum(1 for r in rows if r["status"] in ("pending", "in_progress")),
            "submitted": sum(1 for r in rows if r["status"] == "submitted"),
            "dismissed": sum(1 for r in rows if r["status"] == "dismissed"),
        },
    })


def _mark_personnel_handled():
    data = request.json or {}
    key = data.get("key")
    status = data.get("status")
    if not key or status not in ("submitted", "dismissed"):
        return jsonify({"status": "error", "message": "key and a valid status are required."}), 400

    state = _load_personnel_review_state()
    state[key] = {"status": status, "timestamp": datetime.now().isoformat()}
    _save_personnel_review_state(state)
    return jsonify({"status": "success"})


def _mark_track_progress():
    """
    Records one step of an album-scoped credit's stepper -- "submitted"
    or "skipped" for one specific track's recording. Overall row status
    is never stored directly here, only derived at list-time from how
    many of the album's tracks have an entry (see
    _list_personnel_candidates) -- so this only ever needs to append one
    fact, never recompute or reconcile a summary.
    """
    data = request.json or {}
    key = data.get("key")
    recording_id = data.get("recording_id")
    status = data.get("status")
    if not key or not recording_id or status not in ("submitted", "skipped"):
        return jsonify({"status": "error", "message": "key, recording_id and a valid status are required."}), 400

    state = _load_personnel_review_state()
    entry = state.get(key) or {}
    track_progress = entry.get("track_progress", {})
    track_progress[recording_id] = status
    entry["track_progress"] = track_progress
    entry["timestamp"] = datetime.now().isoformat()
    state[key] = entry
    _save_personnel_review_state(state)
    return jsonify({"status": "success"})


def _apply_track_selection():
    """
    Batch-applies the track-selection modal's unchecked boxes as
    "skipped" in one write, instead of requiring N individual Skip Track
    clicks through the stepper for tracks the user already knows (from
    their own research) a credit doesn't apply to (John, 2026-07-09 --
    caught reviewing a real "Harmonica" credit that plausibly only
    applies to 1-2 of a 16-track album, not all of them; "Open Track 1"
    with no way to see or scope the whole album first was the actual
    problem).

    Only ever ADDS a skip entry for a track with no existing progress --
    never overwrites one already marked submitted/skipped by the
    per-track stepper. The modal's own checkboxes are disabled (and so
    never included in unchecked_recording_ids) for anything already
    resolved, but this is checked again here too rather than trusting
    the client.
    """
    data = request.json or {}
    key = data.get("key")
    unchecked_ids = data.get("unchecked_recording_ids") or []
    if not key:
        return jsonify({"status": "error", "message": "key is required."}), 400

    state = _load_personnel_review_state()
    entry = state.get(key) or {}
    track_progress = entry.get("track_progress", {})
    for rid in unchecked_ids:
        if rid not in track_progress:
            track_progress[rid] = "skipped"
    entry["track_progress"] = track_progress
    entry["timestamp"] = datetime.now().isoformat()
    state[key] = entry
    _save_personnel_review_state(state)
    return jsonify({"status": "success"})


def _fetch_artist_by_name(name):
    """
    Live MB artist search, only reached when a candidate has no
    mb_target_mbid already (the entire current Discogs-sourced backlog,
    since Discogs data never carries an MB artist MBID -- see
    project_mb_contribution_tool memory). Genuinely ambiguous by nature
    (common names collide), so this returns the top match AND its MB
    search score for John's own judgment, never silently commits to it --
    the seeded page shows whatever this finds for him to confirm or
    correct inside MB's own wizard, same two-layer review as everything
    else in this tool. Returns None on no match or any failure.
    """
    try:
        res = requests.get(
            "https://musicbrainz.org/ws/2/artist",
            params={"query": name, "fmt": "json", "limit": 1},
            headers={"User-Agent": MB_API_USER_AGENT},
            timeout=10,
        )
        res.raise_for_status()
        artists = res.json().get("artists") or []
        if not artists:
            return None
        top = artists[0]
        return {"name": top.get("name"), "mbid": top.get("id"), "score": top.get("score")}
    except Exception:
        return None


def _personnel_evidence_paragraphs(candidate, artist_match, is_album_scope_step=False, narrowed=False):
    """
    The per-person evidence/caveat paragraphs, WITHOUT the shared
    attribution footer -- factored out (John, 2026-07-09, "if we can do
    a 'bulk' upload all the better") so a bulk multi-relationship seed
    can reuse the exact same wording per person and just append ONE
    shared footer at the end, instead of duplicating this logic or
    drifting the two paths apart. See _evidence_to_personnel_edit_note
    and _evidence_to_bulk_personnel_edit_note below for the two callers.
    """
    paragraphs = []

    evidence_line = (f"Evidence: {candidate.get('provenance')} credits this recording to "
                      f"{candidate.get('name')} as \"{candidate.get('role')}\".")
    sources = candidate.get("sources")
    if sources:
        evidence_line += f" (sources: {', '.join(sources)})"
    paragraphs.append(evidence_line)

    if is_album_scope_step and narrowed:
        paragraphs.append(
            "This credit was captured at the album level; other tracks on this release have "
            "already been reviewed and excluded for this specific credit. This track was kept as "
            "one the credit is believed to apply to, based on available evidence."
        )
    elif is_album_scope_step:
        paragraphs.append(
            "This credit was captured at the album level using best available evidence, but not "
            "confirmed per-track; it is applied here on the assumption it holds across the whole "
            "release. Per-track confirmation is not possible without production notes currently "
            "not publicly accessible to MetaForge Studio."
        )

    if candidate.get("mb_target_mbid") and not artist_match:
        pass  # Already-known MBID, no live search needed -- no caveat required.
    elif artist_match:
        paragraphs.append(
            f"Artist name search matched \"{artist_match.get('name')}\" (MusicBrainz text-match "
            f"score {artist_match.get('score')}/100 -- this reflects how closely the NAME matched, "
            f"not whether this is confirmed to be the same real person; MusicBrainz can have "
            f"multiple distinct artists sharing an identical name). Not independently confirmed to "
            f"be the correct specific artist beyond this name-text match."
        )
    else:
        paragraphs.append("No confident MusicBrainz artist match found automatically.")

    return paragraphs


def _evidence_to_personnel_edit_note(candidate, artist_match, is_album_scope_step=False, narrowed=False):
    """
    Now carries MetaForge Studio attribution + a link to AI Heuristics.md
    (John, 2026-07-09), same reversal applied to the date-correction edit
    notes above -- see METAFORGE_HEURISTICS_URL. Pure evidence + a
    transparent note about how the artist was matched, since that's a
    genuine judgment call the human still needs to make, not a settled
    fact.

    Three distinct cases, not two -- a candidate can already carry a real
    mb_target_mbid (MB-sourced data, or a resolved-in-code match) with no
    live search ever happening at all, which is different from "a live
    search ran and found something" and different again from "nothing
    was found." Conflating the first two previously produced a false
    "no match found" caveat on candidates that actually had a confident,
    pre-existing match (caught 2026-07-09 testing against real data).

    is_album_scope_step adds a fourth, orthogonal caveat: the underlying
    evidence describes this person's credit for the ALBUM, not this
    specific track. narrowed distinguishes two genuinely different
    claims once the Select Tracks modal exists (John, 2026-07-09): once
    even one track has been excluded, "applies across the whole
    release" is simply false for this album anymore, so the remaining
    tracks get a different, accurate caveat instead of repeating a
    blanket claim that no longer holds.

    AUDIENCE FIX (John, 2026-07-09, the more important catch: "it
    appears to be a comment targeted to the submitter, not the reviewer.
    I don't like that mix of audience"). This entire note becomes
    PERMANENT public MusicBrainz edit history once submitted -- its real
    audience is a future MB editor reading provenance, not John at the
    moment he clicks submit. Every caveat below is now written in third
    person as a statement of fact/limitation for that future reader
    ("per-track confirmation is not possible...", "this reflects..."),
    never as a direct instruction to whoever happens to be looking at it
    right now ("please confirm X before submitting" -- removed
    everywhere in this function). Anything John needs to see in the
    moment belongs in MetaForge Studio's own UI (the queue row's
    "Album-wide credit -- Track X of Y" text, the status bar), not in
    text destined for MusicBrainz's permanent record.

    Also folds in: exact wording John supplied for the album-scope,
    non-narrowed case (2026-07-09) -- "captured at the album level using
    best available evidence, but not confirmed per-track... per-track
    confirmation is not possible without production notes currently not
    publicly accessible to MetaForge Studio" -- explicit about the
    actual epistemic limit (there is usually nothing further to check
    against) rather than asking for a confirmation nobody can perform.
    Same MusicBrainz-self-correction logic he named applies without
    needing to spell it out in the note itself: a good-faith edit that's
    later found wrong gets fixed by another editor, same as any other
    human-submitted MB edit.

    Built as separate PARAGRAPHS (blank line between each distinct
    concern -- evidence, scope caveat, artist-match caveat, attribution
    footer), not one dense run of single-linebreak sentences (John,
    2026-07-09: "some more tweaking please: (line breaks)").

    Sources are hinted inline right after the Evidence sentence (John,
    2026-07-09: "can we 'hint' at the sources that the AI search
    referenced? No need to provide URLs... unless trivial") -- site
    TITLES from the AI response's own grounding chunks (see
    ai_engine.resolve_personnel_ai), not resolved/validated URLs, which
    is exactly what he asked for. Only present for AI Web Search
    candidates; MB/Discogs/manual provenance has no grounding to report.

    The artist-match wording was also rewritten (caught the same day: a
    real self-contradiction, "(score 100/100)... this was not a certain
    match" reads as nonsense at a glance). MB's artist search score is a
    TEXT-relevance score from a name-only Lucene query -- how closely
    the search string matched the result's name/alias text, not whether
    this specific MB artist entity is confirmed to be the same real
    person as the credit. A 100/100 commonly just means an exact string
    match, which happens trivially even when MusicBrainz has multiple
    distinct artists sharing that exact name -- so a perfect score and
    "not a certain match" were never actually in tension, they answer
    two different questions, and the note now says so explicitly.
    """
    paragraphs = []

    evidence_line = (f"Evidence: {candidate.get('provenance')} credits this recording to "
                      f"{candidate.get('name')} as \"{candidate.get('role')}\".")
    sources = candidate.get("sources")
    if sources:
        evidence_line += f" (sources: {', '.join(sources)})"
    paragraphs.append(evidence_line)

    if is_album_scope_step and narrowed:
        paragraphs.append(
            "This credit was captured at the album level; other tracks on this release have "
            "already been reviewed and excluded for this specific credit. This track was kept as "
            "one the credit is believed to apply to, based on available evidence."
        )
    elif is_album_scope_step:
        paragraphs.append(
            "This credit was captured at the album level using best available evidence, but not "
            "confirmed per-track; it is applied here on the assumption it holds across the whole "
            "release. Per-track confirmation is not possible without production notes currently "
            "not publicly accessible to MetaForge Studio."
        )

    if candidate.get("mb_target_mbid") and not artist_match:
        pass  # Already-known MBID, no live search needed -- no caveat required.
    elif artist_match:
        paragraphs.append(
            f"Artist name search matched \"{artist_match.get('name')}\" (MusicBrainz text-match "
            f"score {artist_match.get('score')}/100 -- this reflects how closely the NAME matched, "
            f"not whether this is confirmed to be the same real person; MusicBrainz can have "
            f"multiple distinct artists sharing an identical name). Not independently confirmed to "
            f"be the correct specific artist beyond this name-text match."
        )
    else:
        paragraphs.append("No confident MusicBrainz artist match found automatically.")

    paragraphs.append(f"Proposed by MetaForge Studio -- methodology: {METAFORGE_HEURISTICS_URL}")
    return "\n\n".join(paragraphs)


def _build_personnel_seed_html(candidate, artist_match, recording_id, is_album_scope_step=False, narrowed=False):
    """
    Builds an auto-submitting form POSTing to MusicBrainz's real Recording
    Edit page (musicbrainz.org/recording/{id}/edit) -- confirmed live
    2026-07-09 this accepts the same rels.N.* relationship-seeding
    convention documented for the artist-creation form, even though MB's
    own docs never state that explicitly (see project_mb_contribution_tool
    memory for the live DOM inspection that found this). rels.0.target is
    only included when a real artist MBID exists (either already on the
    candidate, or found via _fetch_artist_by_name above) -- deliberately
    NOT guessed when no match exists, matching the same "never fabricate"
    rule as every other tier of this pipeline.

    recording_id is passed explicitly rather than read off
    candidate["mb_recording_id"] -- for a track-scoped candidate they're
    the same value, but an album-scoped candidate's stepper passes in
    whichever track in the album is the current step, since the
    candidate itself has no single recording of its own (John,
    2026-07-09).
    """
    link_type = RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"])
    target_mbid = candidate.get("mb_target_mbid") or (artist_match.get("mbid") if artist_match else None)

    fields = (
        _seed_field("rels.0.type", link_type)
        + _seed_field("rels.0.target", target_mbid)
        + _seed_field("rels.0.target_credit", candidate.get("name"))
        + _seed_field("edit_note", _evidence_to_personnel_edit_note(candidate, artist_match, is_album_scope_step, narrowed))
    )

    edit_url = f"https://musicbrainz.org/recording/{recording_id}/edit"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Opening MusicBrainz...</title></head>
<body>
<p>Opening MusicBrainz Recording editor, pre-filled from MetaForge Studio's evidence...</p>
<form id="mb-seed-form" method="POST" action="{html.escape(edit_url)}">
{fields}</form>
<script>document.getElementById('mb-seed-form').submit();</script>
</body>
</html>"""


def _build_personnel_seed():
    """
    recording_id in the request body is only sent for an album-scoped
    candidate's stepper step (the current track being opened) -- a
    track-scoped candidate already has its own mb_recording_id and never
    needs the override.
    """
    data = request.json or {}
    key = data.get("key")
    recording_id_override = data.get("recording_id")
    if not key:
        return jsonify({"status": "error", "message": "key is required."}), 400

    candidates = {_candidate_key(c): c for c in _load_personnel_candidates()}
    candidate = candidates.get(key)
    if not candidate:
        return jsonify({"status": "error", "message": "Candidate not found."}), 404

    recording_id = candidate.get("mb_recording_id") or recording_id_override
    if not recording_id:
        return jsonify({"status": "error", "message": "No target track specified for this album-wide credit."}), 400

    artist_match = None
    if not candidate.get("mb_target_mbid"):
        artist_match = _fetch_artist_by_name(candidate["name"])

    # "narrowed" = has ANY track for this album-scoped credit already
    # been excluded (skipped), whether via the Select Tracks modal's
    # batch action or an individual stepper Skip? If so, "applies to
    # the whole release" is no longer an accurate claim to make in the
    # edit note -- see _evidence_to_personnel_edit_note's narrowed
    # branch (John, 2026-07-09).
    narrowed = False
    if recording_id_override:
        review_state = _load_personnel_review_state()
        track_progress = (review_state.get(key) or {}).get("track_progress", {})
        narrowed = any(status == "skipped" for status in track_progress.values())

    seed_html = _build_personnel_seed_html(
        candidate, artist_match, recording_id,
        is_album_scope_step=bool(recording_id_override),
        narrowed=narrowed,
    )
    return jsonify({
        "status": "success",
        "html": seed_html,
        "title": f"MusicBrainz: {candidate.get('name')}",
        "artist_match": artist_match,
    })


def _evidence_to_bulk_personnel_edit_note(items):
    """
    items: list of (candidate, artist_match, is_album_scope_step, narrowed)
    tuples, one per bundled relationship. Combines each person's own
    evidence block under a name/role header (John, 2026-07-10: "if we
    can do a 'bulk' upload all the better", after ruling out
    MusicBrainz's release-level batch editor as unseedable -- see
    project_mb_contribution_tool memory) so a single seeded page
    carrying several rels.N relationships still has a clear,
    per-fact-attributable edit note, not one blurred paragraph a future
    MB reader can't pull apart. Reuses _personnel_evidence_paragraphs()
    so the wording is identical to the single-relationship path, just
    repeated once per person plus ONE shared attribution footer.
    """
    paragraphs = []
    for candidate, artist_match, is_album_scope_step, narrowed in items:
        paragraphs.append(f"--- {candidate.get('name')} ({candidate.get('role')}) ---")
        paragraphs.extend(_personnel_evidence_paragraphs(candidate, artist_match, is_album_scope_step, narrowed))
    paragraphs.append(f"Proposed by MetaForge Studio -- methodology: {METAFORGE_HEURISTICS_URL}")
    return "\n\n".join(paragraphs)


def _build_bulk_personnel_seed_html(items, recording_id):
    """
    Seeds MULTIPLE rels.N relationships into ONE Recording Edit page
    submission instead of one relationship per page-load (John,
    2026-07-10). Same rels.N.* naming already confirmed live for a
    single relationship -- MB's own "Add relationship" widget on this
    exact page lets a human add many people one at a time to the same
    recording, so multiple indices in one seed is the same underlying
    capability, just pre-filled instead of manually repeated N times.
    """
    fields = ""
    for i, (candidate, artist_match, is_album_scope_step, narrowed) in enumerate(items):
        link_type = RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"])
        target_mbid = candidate.get("mb_target_mbid") or (artist_match.get("mbid") if artist_match else None)
        fields += (
            _seed_field(f"rels.{i}.type", link_type)
            + _seed_field(f"rels.{i}.target", target_mbid)
            + _seed_field(f"rels.{i}.target_credit", candidate.get("name"))
        )
    fields += _seed_field("edit_note", _evidence_to_bulk_personnel_edit_note(items))

    edit_url = f"https://musicbrainz.org/recording/{recording_id}/edit"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Opening MusicBrainz...</title></head>
<body>
<p>Opening MusicBrainz Recording editor, pre-filled with {len(items)} credits from MetaForge Studio's evidence...</p>
<form id="mb-seed-form" method="POST" action="{html.escape(edit_url)}">
{fields}</form>
<script>document.getElementById('mb-seed-form').submit();</script>
</body>
</html>"""


def _build_bulk_personnel_seed():
    """
    Request: {keys: [candidate_key, ...], recording_id: "..."}. Every
    key must resolve to a candidate that either already targets this
    exact recording (track-scoped), or is an album-scoped credit
    currently still open for this specific track (not yet present in
    its own track_progress). Silently skips any key that doesn't
    actually apply here rather than erroring the whole batch --
    defensive against stale frontend state, e.g. a candidate got
    dismissed between page load and this click.
    """
    data = request.json or {}
    keys = data.get("keys") or []
    recording_id = data.get("recording_id")
    if not keys or not recording_id:
        return jsonify({"status": "error", "message": "keys and recording_id are required."}), 400

    candidates_by_key = {_candidate_key(c): c for c in _load_personnel_candidates()}
    review_state = _load_personnel_review_state()

    items = []
    for key in keys:
        candidate = candidates_by_key.get(key)
        if not candidate:
            continue
        rid = candidate.get("mb_recording_id")
        is_album_scope_step = not rid
        if rid and rid != recording_id:
            continue  # track-scoped for a DIFFERENT recording -- not part of this bundle

        entry = review_state.get(key) or {}
        track_progress = entry.get("track_progress", {}) or {}
        if is_album_scope_step and recording_id in track_progress:
            continue  # already resolved (submitted/skipped) for this specific track
        if not is_album_scope_step and entry.get("status") in ("submitted", "dismissed"):
            continue

        narrowed = any(status == "skipped" for status in track_progress.values())

        artist_match = None
        if not candidate.get("mb_target_mbid"):
            artist_match = _fetch_artist_by_name(candidate["name"])

        items.append((candidate, artist_match, is_album_scope_step, narrowed, key))

    # De-dup at the MB level, not MetaForge's (John, 2026-07-10, caught
    # live testing: 72 credits collapsed to 46 unique targets). Two
    # genuinely different free-text roles ("Harmonica", "Flute") can
    # both classify to the same coarse relation_type
    # (ASSOCIATED_WITH -> link_type 129, a catch-all with no
    # instrument-specific attribute wired up yet) -- correct and
    # distinct as separate facts in MetaForge's own database, but the
    # literal same relationship if both were seeded as rels.N here.
    # MusicBrainz itself rejects an exact duplicate ("this relationship
    # already exists," confirmed live the same evening) -- so this has
    # to be caught before building the seed, not left for MB to reject
    # one arbitrarily. Keys on (link_type, resolved target identity),
    # keeping whichever duplicate has the higher confidence; ties keep
    # whichever was seen first.
    best_by_target = {}
    for candidate, artist_match, is_album_scope_step, narrowed, key in items:
        link_type = RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"])
        target_mbid = candidate.get("mb_target_mbid") or (artist_match.get("mbid") if artist_match else None)
        dedup_key = (link_type, target_mbid or candidate.get("name", "").strip().lower())
        existing = best_by_target.get(dedup_key)
        if not existing or (candidate.get("confidence") or 0) > (existing[0].get("confidence") or 0):
            best_by_target[dedup_key] = (candidate, artist_match, is_album_scope_step, narrowed, key)

    items = [v[:4] for v in best_by_target.values()]
    included_keys = [v[4] for v in best_by_target.values()]

    if not items:
        return jsonify({"status": "error", "message": "None of the requested credits apply to this recording."}), 400

    seed_html = _build_bulk_personnel_seed_html(items, recording_id)
    return jsonify({
        "status": "success",
        "html": seed_html,
        "title": f"MusicBrainz: {len(items)} credits",
        "count": len(items),
        "included_keys": included_keys,
    })
# --- END OF FILE musicbrainz_submit.py ---
