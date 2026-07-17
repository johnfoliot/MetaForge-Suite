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
from urllib.parse import urlencode
from flask import jsonify, request
from common import config_handler, db_engine

CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "original_year_correction_candidates.jsonl"
REVIEW_STATE = config_handler.DATA_DIR / "musicbrainz" / "year_correction_review_state.json"
PERSONNEL_CANDIDATE_LOG = config_handler.DATA_DIR / "musicbrainz" / "personnel_correction_candidates.jsonl"
PERSONNEL_REVIEW_STATE = config_handler.DATA_DIR / "musicbrainz" / "personnel_correction_review_state.json"

# Permanent audit trail of everything actually reached "submitted"
# (John, 2026-07-14: "a running record of all of our remediation/updates").
# ONE shared file for both year and personnel corrections -- his own
# wording asked for "ALL of our remediation/updates" in one place, not two
# parallel logs -- distinguished by each line's own "type" field. Written
# once per candidate, the first time its status is genuinely observed as
# "submitted" (never for "dismissed" -- that's a rejection, not a
# remediation), tracked via a "remediation_logged" flag persisted
# alongside the existing review-state entry so a page reload can never
# double-log the same fact.
REMEDIATION_LOG = config_handler.DATA_DIR / "musicbrainz" / "remediation_log.jsonl"


def _log_remediation(entry_type, payload):
    entry = {"type": entry_type, "timestamp": datetime.now().isoformat(), **payload}
    REMEDIATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REMEDIATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

MB_RELEASE_ADD_URL = "https://musicbrainz.org/release/add"
MB_API_USER_AGENT = "MetaForge/1.0 (musicbrainz_submit)"

# Public methodology doc explaining how MetaForge derives the evidence in
# every edit note below -- linked from every submission (John, 2026-07-09,
# supersedes the earlier "no MetaForge branding" decision from 2026-07-09
# earlier the same day; the doc's existence is the reason the reversal
# makes sense, an MB editor now has somewhere real to verify the claims
# instead of being asked to trust an anonymous tool).
METAFORGE_HEURISTICS_URL = "https://github.com/johnfoliot/MetaForge-Suite/blob/main/AI%20Heuristics.md"

# Third-person, permanent-record versions of the verify modal's own
# dropdown text (John, 2026-07-13 -- same "audience fix" rule as every
# other caveat in _personnel_evidence_paragraphs: this becomes permanent
# MusicBrainz edit history, its real audience is a future MB editor, not
# the submitter at the moment of clicking). Paired with a Source: URL
# line whenever candidate.verified_source_url is present -- the resolved
# destination page a human actually confirmed against, never Gemini's
# opaque grounding redirect link (see personnel.py's MANUAL_VERIFICATION_TIERS
# and project_mb_contribution_tool memory for the compliance reasoning
# this rests on). Keys must match personnel.py's MANUAL_VERIFICATION_TIERS
# exactly -- not re-imported from there since this tool has no dependency
# on tools/personnel today, deliberately kept that way.
VERIFICATION_TIER_EDIT_NOTE_TEXT = {
    "explicit": "The submitter directly confirmed this fact against an independent source.",
    "inferred": "The submitter found this matches independent evidence, though not specific to this exact track or release.",
    "anecdotal": "The submitter found some supporting mention of this in an independent source, without a solid citation.",
}

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

# Renamed 2026-07-14 (was UNSUPPORTED_RELATION_TYPES) once COMPOSED
# gained a real release-level home (RELEASE_ARTIST_LINK_TYPES above) --
# these stay genuinely unsupported at the RECORDING level specifically
# (Work-level only, confirmed 2026-07-09/2026-07-14), but "unsupported"
# outright is no longer accurate for any of them now that all three have
# a real release-level home below. LYRICIST added 2026-07-14 alongside
# the WRITTEN_BY correction -- MB's own style guide confirms "Writer" is
# deliberately the generic fallback and Lyricist the more precise type
# for a words-only credit (see edge_constants.py's RelationType comment).
RECORDING_LEVEL_UNSUPPORTED_RELATION_TYPES = {"COMPOSED", "WRITTEN_BY", "LYRICIST"}

# Release-scoped artist-release relationship type IDs (John, 2026-07-13,
# confirmed live via his own DOM capture of /release/{id}/edit-relationships'
# "Add relationship" -> Related type: Artist dialog). A DIFFERENT numeric
# ID table than RELATION_TYPE_TO_LINK_TYPE above -- MusicBrainz keys
# relationship types per entity-PAIR, so the same real-world relationship
# ("produced") has two different IDs depending on whether it's attached
# to a Recording or a Release (confirmed: produced is 141 recording-scope,
# 30 release-scope). Only mapped for relation types actually seen and
# confirmed present in that dialog's real DOM -- not guessed for the rest.
#
# COMPOSED confirmed real 2026-07-14, acted on: John live-tested "composed
# / composer" (55) directly against a real release ("Hope Chest: The
# Fredonia Recordings") -- the field exists, auto-matched the artist by
# MBID, and the edit was successfully added (screenshot confirmed). This
# is what surfaced the actual bug: a Discogs "Written-By" credit was
# misclassified as ASSOCIATED_WITH (see performance.json) and the
# release-wide automation then tried searching that text in the
# Instrument field. COMPOSED still stays out of RELATION_TYPE_TO_LINK_TYPE
# above -- the Recording-level editor has no composer field at all
# (Work-level only, confirmed 2026-07-09) -- this is release-level-only
# support.
#
# WRITTEN_BY(54)/LYRICIST(56) added 2026-07-14, correcting the first-pass
# decision above: "Written-By" was initially mapped to COMPOSED, but
# MusicBrainz's own style guide states "Writer" (54) IS the precise,
# deliberate type for this -- "used... when no more specific information
# is available. If possible, the more specific composer, lyricist and/or
# librettist types should be used, rather than this relationship type."
# That's an exact match for what Discogs' "Written-By" itself represents
# (their own generic fallback for an unsplit music+lyrics credit). Both
# IDs confirmed via MB's own relationship-type detail pages, cross-checked
# against every ID already live-tested this session (writer/composer/
# performer/instrument/vocal all matched exactly) -- this method is now
# trusted for confirming NEW IDs, not just corroborating known ones.
RELEASE_ARTIST_LINK_TYPES = {
    "PRODUCED": 30,       # produced / producer
    "PERFORMED_ON": 51,   # performed / performer
    "ARRANGED_BY": 295,   # arranged / arranger
    "COMPOSED": 55,        # composed / composer
    "WRITTEN_BY": 54,      # wrote / writer (generic fallback)
    "LYRICIST": 56,        # lyrics / lyricist
}

# Search term to type into the relationship-type autocomplete before
# selecting by ID (John, 2026-07-13, live-caught bug: the UNFILTERED
# dropdown only shows a fixed "Recent items" + "performance" category
# preview -- "produced / producer" (30) never appeared there at all
# except as item-30-recent, a volatile per-session ID this code
# deliberately never relies on. Typing a query is what actually renders
# the plain, stable item-{ID} entry, confirmed from John's own second DOM
# capture (after he manually typed "produced").
RELEASE_LINK_TYPE_SEARCH_TERMS = {
    30: "produced",
    51: "performed",
    295: "arranged",
    55: "composed",
    # "wrote"/"lyrics" match MB's own dropdown label convention
    # ("wrote / writer", "lyrics / lyricist" -- verb-first, same pattern
    # as every entry above) but, unlike the numeric IDs above, these two
    # search TERMS haven't been live-confirmed by actually typing them
    # into the dialog and watching the filtered result render -- worth a
    # first live test rather than assuming.
    54: "wrote",
    56: "lyrics",
}

# Release-scoped "vocals" relationship type -- confirmed live in the same
# DOM capture as RELEASE_ARTIST_LINK_TYPES above.
RELEASE_VOCALS_LINK_TYPE = 60

# Release-scoped "instruments" relationship type (John, 2026-07-13, real
# catch mid-testing: a PERFORMED_ON credit whose role names a specific
# instrument -- "Guitar", "Bass", "Drums" -- was being seeded as generic
# "performed / performer" (51), throwing away information MetaForge
# actually has. Selecting THIS type instead reveals MB's own "Instrument"
# search field, confirmed live via John's own screenshot of the resulting
# dialog. Matches the existing RELATION_TYPE_TO_LINK_TYPE comment from
# 2026-07-09 flagging this exact limitation as deferred, not new scope.
RELEASE_INSTRUMENTS_LINK_TYPE = 44


# Generic ASSOCIATED_WITH noise that isn't a real instrument name, even
# though it's non-empty (John, 2026-07-13). ASSOCIATED_WITH is
# MetaForge's own lower-confidence catch-all -- real credits like "Organ"/
# "Saxophone"/"Trumpet" land here rather than PERFORMED_ON (confirmed
# live: this is exactly why those rows had no release-wide button at
# all), but so do genuinely vague ones this list exists to exclude.
GENERIC_NON_INSTRUMENT_ROLES = {
    "backing band", "associated with", "misc", "miscellaneous",
    "performer", "artist", "primary artist", "main artist", "lead artist",
}


def _release_seed_fields(relation_type, role):
    """
    Decides (link_type, type_search_term, instrument_search_term) for the
    release-wide path, given BOTH the relation_type and the role text --
    or (None, None, None) if this credit shouldn't offer that path at
    all. Scoped to the release-wide path only for now -- the per-track
    URL-seeding path has its own, separate limitation, not touched here.

    PRODUCED/ARRANGED_BY/COMPOSED/WRITTEN_BY/LYRICIST: simple, static
    lookup, role text irrelevant. COMPOSED added 2026-07-14, live-
    confirmed working against a real release. WRITTEN_BY/LYRICIST added
    the same day, correcting the earlier COMPOSED-only decision -- see
    RELEASE_ARTIST_LINK_TYPES comment for the full reasoning.

    PERFORMED_ON: MetaForge's own "this artist performed" classification,
    fairly high confidence. A role naming vocals ("Vocals", "Lead
    Vocals") -> the dedicated "vocals" type (60). Any other non-empty
    role -> "instruments" (44), with the role text itself as the term to
    search MB's own Instrument field for -- the automation requires an
    EXACT (or startsWith, see the JS builder) match there, never a
    best-guess. An EMPTY role falls back to generic "performed /
    performer" (51) -- nothing to search for, and PERFORMED_ON's own
    confidence still supports asserting the plain relationship.

    ASSOCIATED_WITH (John, 2026-07-13, real bug caught live -- two real
    "Organ" credits had no release-wide button at all, since this
    relation_type wasn't in RELEASE_ARTIST_LINK_TYPES): deliberately
    does NOT fall back to "performed/performer" the way PERFORMED_ON
    does -- this is MetaForge's own genuinely LOWER-confidence catch-all
    (these credits are logged at confidence 0.2, versus 0.6-0.9 for
    PERFORMED_ON), so asserting a confident "performed on this release"
    relationship for a vague ASSOCIATED_WITH credit would overstate what
    MetaForge actually knows. Only offered when the role text is
    specific enough to plausibly BE an instrument -- empty roles and
    GENERIC_NON_INSTRUMENT_ROLES noise get (None, None, None), meaning no
    release-wide button at all for those, same as before this change.
    """
    role_clean = (role or "").strip()
    role_lower = role_clean.lower()

    # Strip a bracketed qualifier (e.g. "Drums [Studio]" -> "Drums")
    # before using role text as MB's Instrument search term -- John,
    # 2026-07-14, live-caught: this is a real, meaningful Discogs
    # qualifier and stays untouched everywhere else (display, edit note,
    # role classification -- role_clean/role above), but it isn't part
    # of the actual instrument name and broke the exact/startsWith match
    # against MB's own instrument label ("drums (drum set)"). A
    # DIFFERENT bracket style than the round-paren track-number
    # qualifier edge_normalizer.py already strips before classification.
    instrument_search_text = re.sub(r'\s*\[.*?\]\s*', ' ', role_clean).strip() or role_clean

    if relation_type in ("PRODUCED", "ARRANGED_BY", "COMPOSED", "WRITTEN_BY", "LYRICIST"):
        link_type = RELEASE_ARTIST_LINK_TYPES[relation_type]
        return link_type, RELEASE_LINK_TYPE_SEARCH_TERMS[link_type], None

    if relation_type == "PERFORMED_ON":
        if not role_clean:
            return RELEASE_ARTIST_LINK_TYPES["PERFORMED_ON"], RELEASE_LINK_TYPE_SEARCH_TERMS[51], None
        if "vocal" in role_lower:
            return RELEASE_VOCALS_LINK_TYPE, "vocals", None
        return RELEASE_INSTRUMENTS_LINK_TYPE, "instruments", instrument_search_text

    if relation_type == "ASSOCIATED_WITH":
        if not role_clean or role_lower in GENERIC_NON_INSTRUMENT_ROLES:
            return None, None, None
        if "vocal" in role_lower:
            return RELEASE_VOCALS_LINK_TYPE, "vocals", None
        return RELEASE_INSTRUMENTS_LINK_TYPE, "instruments", instrument_search_text

    return None, None, None


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
        if action == "build_release_relationship_seed": return _build_release_relationship_seed()
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


def _get_release_mbid(mf_id):
    """
    The release's own MusicBrainz ID (library_master.mb_album_id) --
    needed to seed /release/{id}/edit-relationships (John, 2026-07-13),
    a different target than mb_recording_id, which only identifies one
    track. Returns None if the album was never MB-ID'd.
    """
    if not mf_id:
        return None
    res = db_engine.execute_query("SELECT mb_album_id FROM library_master WHERE mf_id=?", (mf_id,))
    if res and res[0].get('mb_album_id'):
        return res[0]['mb_album_id']
    return None


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

            # Include a candidate if EITHER submission path can actually
            # use it -- recording-level (RELATION_TYPE_TO_LINK_TYPE) or
            # release-level (_release_seed_fields). Changed 2026-07-14:
            # this used to be a flat RELATION_TYPE_TO_LINK_TYPE-only check,
            # which meant COMPOSED never reached the queue at all even
            # after gaining real release-level support above -- it would
            # have just silently vanished instead of offering
            # "Submit Release-Wide". WRITTEN_BY has no home on either
            # path yet and still gets excluded here.
            if (entry.get("relation_type") not in RELATION_TYPE_TO_LINK_TYPE
                    and _release_seed_fields(entry.get("relation_type"), entry.get("role"))[0] is None):
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
    state_dirty = False
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
            # A directly-stored "submitted"/"dismissed" status (John,
            # 2026-07-13, real UX bug caught live) previously only
            # honored "dismissed" here -- "submitted" fell straight
            # through to the track_progress-based derivation below,
            # which still read as "pending" (0 of N tracks stepped)
            # even after mark_personnel_handled had genuinely recorded
            # it as submitted. This is exactly what a release-wide
            # submission needs: ONE relationship covers the whole album,
            # so the per-track stepper has nothing left to do and
            # shouldn't keep prompting for it.
            if review.get("status") in ("dismissed", "submitted"):
                status = review["status"]
            elif not album_tracks or len(track_progress) == 0:
                status = "pending"
            elif len(track_progress) < len(album_tracks):
                status = "in_progress"
            else:
                status = "submitted"

        # Log to the permanent remediation trail exactly once, the first
        # time this candidate is genuinely observed as "submitted" (John,
        # 2026-07-14). Deliberately checked HERE rather than in each
        # write-path (_mark_personnel_handled/_mark_track_progress)
        # separately -- this is the one place that already reconciles
        # BOTH ways a personnel credit can end up submitted (a direct
        # mark, or completing the per-track stepper), so logging here
        # can't miss the stepper-completion case or double-log the same
        # fact if the two paths ever raced.
        if status == "submitted" and not review.get("remediation_logged"):
            _log_remediation("personnel", {
                "key": key,
                "mf_id": c.get("mf_id"),
                "artist": c.get("artist"),
                "album": c.get("album"),
                "mb_recording_id": rid,
                "name": c.get("name"),
                "mb_target_mbid": c.get("mb_target_mbid"),
                "relation_type": c.get("relation_type"),
                "role": c.get("role"),
                "provenance": c.get("provenance"),
                "confidence": c.get("confidence"),
            })
            review["remediation_logged"] = True
            state[key] = review
            state_dirty = True

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
            # Whether this credit has a confirmed release-level MB
            # relationship type available (John, 2026-07-13, real bug
            # fixed: this used to check relation_type alone against
            # RELEASE_ARTIST_LINK_TYPES, which meant ASSOCIATED_WITH
            # credits -- real ones like "Organ"/"Saxophone" -- never got
            # the button at all, even though "instruments" was a genuine
            # fit for them). Now calls the SAME dispatcher
            # _build_release_relationship_seed() itself uses
            # (_release_seed_fields), so this flag and the actual seed
            # logic can never drift apart -- single source of truth,
            # server-side, role-aware, not just relation_type-aware.
            "release_seedable": _release_seed_fields(c.get("relation_type"), c.get("role"))[0] is not None,
        })

    if state_dirty:
        _save_personnel_review_state(state)

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


def _personnel_evidence_paragraphs(candidate, artist_match, is_album_scope_step=False, narrowed=False, entity_label="recording"):
    """
    The per-person evidence/caveat paragraphs, WITHOUT the shared
    attribution footer -- factored out (John, 2026-07-09, "if we can do
    a 'bulk' upload all the better") so a bulk multi-relationship seed
    can reuse the exact same wording per person and just append ONE
    shared footer at the end, instead of duplicating this logic or
    drifting the two paths apart. See _evidence_to_personnel_edit_note
    and _evidence_to_bulk_personnel_edit_note below for the two callers.

    entity_label (2026-07-13): "recording" (default, matches every
    existing caller) or "release" -- the release-level relationship path
    (_build_release_relationship_seed) attaches the fact to the RELEASE
    entity itself, not any one recording, so the evidence sentence needs
    to say so accurately rather than always claiming "this recording."
    """
    paragraphs = []

    evidence_line = (f"Evidence: {candidate.get('provenance')} credits this {entity_label} to "
                      f"{candidate.get('name')} as \"{candidate.get('role')}\".")
    sources = candidate.get("sources")
    if sources:
        evidence_line += f" (sources: {', '.join(sources)})"
    paragraphs.append(evidence_line)

    # Human "click to verify" judgment, when present (John, 2026-07-13) --
    # only ever set together (see personnel.py's _log_mb_correction_candidate),
    # so tier_text without a URL never happens in practice, but the URL is
    # still gated on its own presence rather than assumed.
    tier = candidate.get("verification_tier")
    if tier in VERIFICATION_TIER_EDIT_NOTE_TEXT:
        tier_line = VERIFICATION_TIER_EDIT_NOTE_TEXT[tier]
        url = candidate.get("verified_source_url")
        if url:
            tier_line += f" Source: {url}"
        paragraphs.append(tier_line)

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


def _evidence_to_personnel_edit_note(candidate, artist_match, is_album_scope_step=False, narrowed=False, entity_label="recording"):
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
    # Was a byte-for-byte duplicate of _personnel_evidence_paragraphs()
    # until 2026-07-13 -- consolidated while adding the verification_tier/
    # verified_source_url paragraph there, so this and the bulk path
    # (_evidence_to_bulk_personnel_edit_note) can never silently drift
    # apart on wording again.
    paragraphs = _personnel_evidence_paragraphs(candidate, artist_match, is_album_scope_step, narrowed, entity_label)
    paragraphs.append(f"Proposed by MetaForge Studio<br>Methodology: {METAFORGE_HEURISTICS_URL}")
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

    query = _seed_query_params([
        ("rels.0.type", link_type),
        ("rels.0.target", target_mbid),
        ("rels.0.target_credit", candidate.get("name")),
        ("edit_note", _evidence_to_personnel_edit_note(candidate, artist_match, is_album_scope_step, narrowed)),
    ])
    edit_url = f"https://musicbrainz.org/recording/{recording_id}/edit?{query}"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Opening MusicBrainz...</title></head>
<body>
<p>Opening MusicBrainz Recording editor, pre-filled from MetaForge Studio's evidence...</p>
<script>window.location.replace({json.dumps(edit_url)});</script>
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

    # Guard added 2026-07-14: the queue can now include relation_types
    # (COMPOSED) that only have a release-level seed, no recording-level
    # one -- reachable here via the per-track stepper fallback UI, which
    # would otherwise build a broken rels.0.type=None seed.
    if RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"]) is None:
        return jsonify({"status": "error", "message": (
            f'"{candidate.get("relation_type")}" has no recording-level MusicBrainz relationship type -- '
            f'use "Submit Release-Wide" for this credit instead.'
        )}), 400

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
    paragraphs.append(f"Proposed by MetaForge Studio <br>Methodology: {METAFORGE_HEURISTICS_URL}")
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
    pairs = []
    for i, (candidate, artist_match, is_album_scope_step, narrowed) in enumerate(items):
        link_type = RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"])
        target_mbid = candidate.get("mb_target_mbid") or (artist_match.get("mbid") if artist_match else None)
        pairs.append((f"rels.{i}.type", link_type))
        pairs.append((f"rels.{i}.target", target_mbid))
        pairs.append((f"rels.{i}.target_credit", candidate.get("name")))
    pairs.append(("edit_note", _evidence_to_bulk_personnel_edit_note(items)))

    query = _seed_query_params(pairs)
    edit_url = f"https://musicbrainz.org/recording/{recording_id}/edit?{query}"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Opening MusicBrainz...</title></head>
<body>
<p>Opening MusicBrainz Recording editor, pre-filled with {len(items)} credits from MetaForge Studio's evidence...</p>
<script>window.location.replace({json.dumps(edit_url)});</script>
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
        # Same guard as _build_personnel_seed() (2026-07-14): a
        # release-level-only relation_type (COMPOSED) has no recording
        # seed to build here -- skip it silently, same as any other
        # stale/inapplicable key, rather than building rels.N.type=None.
        if RELATION_TYPE_TO_LINK_TYPE.get(candidate["relation_type"]) is None:
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


# ==========================================================================
# RELEASE-LEVEL RELATIONSHIP SEEDING (John, 2026-07-13)
#
# For a genuinely album-wide credit (Producer, Arranger -- see
# RELEASE_ARTIST_LINK_TYPES), one release-level MusicBrainz relationship
# is the correct fact to submit, not N per-track ones. Confirmed live
# that /release/{id}/edit-relationships has NO query-string seeding
# mechanism at all (unlike /recording/{id}/edit) -- a GET test with the
# same rels.N.* params produced no visible change. The only way to get
# this page pre-filled is to actually drive its own "Add relationship"
# dialog with injected JS, stopping short of the page's real "Enter
# edit" submit button. See _build_release_relationship_automation_js's
# own docstring for the fragility trade-off this accepts.
# ==========================================================================

def _build_release_relationship_automation_js(link_type, target_mbid, target_name, edit_note, search_term, instrument_term=None):
    """
    DOM automation against MusicBrainz's LIVE /release/{id}/edit-relationships
    page. This drives the page's own "Add relationship" dialog under
    "Release relationships" directly: clicks it open, selects the
    relationship type by its numeric link_type ID (deterministic --
    avoids fuzzy text matching against a label that could theoretically
    change), pastes the artist's real MBID into the target field (the
    field's own placeholder documents MBID-paste as supported input,
    sidestepping fuzzy name search entirely -- same principle as the
    recording-edit seed always preferring a real MBID over a name
    search), clicks the dialog's own "Done" button (which only adds the
    relationship to THIS PAGE's pending in-memory list -- not a
    MusicBrainz submission by itself), fills the shared edit-note
    textarea, and STOPS. Never touches "Enter edit" -- that remains the
    one real submission action, same "nothing here submits itself" rule
    as every other seed in this file.

    instrument_term (2026-07-13): when the relationship type is
    "instruments" (44), MB reveals an additional Instrument search field
    -- this MUST be filled with an exact (case-insensitive) label match
    before the automation proceeds to click "Done", never a best-guess
    suggestion. There's no known, stable numeric ID to select by here
    (unlike link_type, which is MB's own real controlled-vocabulary ID) --
    matching is by the option's own visible text instead, using
    directText() to read just the instrument name and exclude any nested
    description span. If no exact match renders, this throws (same as
    every other required step), surfacing the fallback alert() rather
    than silently clicking Done with no instrument specified -- that
    would submit a real fact with less precision than MetaForge actually
    has evidence for.

    Genuinely riskier than the URL-seeding approach used elsewhere in
    this file: this scripts MusicBrainz's own live React-based
    relationship editor, which MetaForge has no control over and no test
    coverage against -- if MusicBrainz changes this page's markup or
    component structure, this breaks silently. Every step below has its
    own timeout and falls through to an alert() telling the user to
    finish adding the relationship by hand, rather than failing silently
    or leaving the page in a half-filled state with no explanation.
    """
    payload = json.dumps({
        "linkType": str(link_type),
        "targetMbid": target_mbid,
        "targetName": target_name,
        "editNote": edit_note,
        "searchTerm": search_term,
        "instrumentTerm": instrument_term,
    })
    return f"""
(function() {{
    var DATA = {payload};

    function findVisible(selector) {{
        var els = document.querySelectorAll(selector);
        for (var i = 0; i < els.length; i++) {{
            if (els[i].offsetParent !== null) return els[i];
        }}
        return null;
    }}

    function setNativeValue(el, value) {{
        var proto = Object.getPrototypeOf(el);
        var desc = Object.getOwnPropertyDescriptor(proto, 'value');
        if (desc && desc.set) {{ desc.set.call(el, value); }} else {{ el.value = value; }}
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}

    // Text of an option <li> BEFORE any nested description <span> --
    // these dropdown items render as "Label<span class=autocomplete-comment>
    // description</span>", and the description text must never count
    // toward an exact match.
    function directText(li) {{
        var text = '';
        for (var i = 0; i < li.childNodes.length; i++) {{
            var node = li.childNodes[i];
            if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
            else break;
        }}
        return text.trim().toLowerCase();
    }}

    function waitFor(checkFn, timeoutMs) {{
        return new Promise(function(resolve, reject) {{
            var waited = 0;
            var intervalMs = 150;
            var timer = setInterval(function() {{
                var result;
                try {{ result = checkFn(); }} catch (e) {{ result = null; }}
                if (result) {{
                    clearInterval(timer);
                    resolve(result);
                }} else {{
                    waited += intervalMs;
                    if (waited >= timeoutMs) {{
                        clearInterval(timer);
                        reject(new Error('timed out waiting for the page'));
                    }}
                }}
            }}, intervalMs);
        }});
    }}

    function fail(err) {{
        alert('MetaForge could not finish this automatically (' + (err ? err.message : 'unknown error') +
              ').\\n\\nPlease add it manually under "Release relationships":\\nRelationship type ID: ' + DATA.linkType +
              '\\nArtist: ' + DATA.targetName + ' (' + DATA.targetMbid + ')');
    }}

    async function run() {{
        // The page's initial shell (what 'loaded'/evaluate_js sees) renders
        // fast, but the actual tracklist/relationships editor content
        // loads asynchronously after that -- confirmed live 2026-07-13,
        // this automation was firing while the page still showed its own
        // "Loading..." spinner. Poll for both the section AND its button
        // together, generously timed (a large release with many tracks
        // can take a real while to finish fetching/rendering), instead of
        // a single synchronous check.
        var addBtn = await waitFor(function() {{
            var section = document.getElementById('release-rels');
            return section ? section.querySelector('button.add-relationship') : null;
        }}, 20000);
        addBtn.click();

        var typeInput = await waitFor(function() {{ return findVisible('input.relationship-type'); }}, 6000);
        typeInput.click();
        typeInput.focus();

        // Typing a query is required, not optional (John, 2026-07-13,
        // caught live): the UNFILTERED dropdown only ever shows a fixed
        // "Recent items" + "performance" category preview -- the exact,
        // stable item-ID entry this code selects by only actually
        // renders once a search has been typed to filter the list.
        setNativeValue(typeInput, DATA.searchTerm);

        var typeOption = await waitFor(function() {{
            return document.querySelector('li[id$="-item-' + DATA.linkType + '"]');
        }}, 6000);
        typeOption.click();

        // Instrument sub-field (John, 2026-07-13) -- only present when
        // linkType is "instruments" (44), which reveals a new,
        // narrower attributes panel with its own search field. No known
        // stable ID to select by here (unlike relationship type), so
        // this matches by the option's own exact visible text via
        // directText() -- required, not best-effort: if nothing matches
        // exactly, this throws and the whole automation stops rather
        // than clicking Done with a vaguer credit than the evidence
        // actually supports.
        if (DATA.instrumentTerm) {{
            var instrumentInput = await waitFor(function() {{
                return findVisible('.attribute-container.instrument input[placeholder="instrument"]');
            }}, 6000);
            instrumentInput.click();
            instrumentInput.focus();
            setNativeValue(instrumentInput, DATA.instrumentTerm);

            // startsWith, not exact equality (John, 2026-07-13, real bug
            // caught live): MB's actual controlled-vocabulary label for
            // "Drums" is "drums (drum set)" -- a real parenthetical
            // qualifier this pipeline's plain role text was never going
            // to match exactly. startsWith is still precise enough to
            // avoid matching an unrelated instrument that merely
            // contains the search term somewhere in the middle, while
            // handling MB's own naming convention correctly.
            var wantedText = DATA.instrumentTerm.trim().toLowerCase();
            var instrumentOption = await waitFor(function() {{
                var opts = document.querySelectorAll('li[role="option"]');
                for (var i = 0; i < opts.length; i++) {{
                    if (directText(opts[i]).indexOf(wantedText) === 0) return opts[i];
                }}
                return null;
            }}, 6000);
            instrumentOption.click();
        }}

        // Selecting a relationship type (and, for instruments, then an
        // instrument) changes which attribute fields the dialog shows --
        // John's own screenshots confirm the attributes panel is
        // genuinely different per type. That strongly suggests this
        // section re-renders, and a real live bug (2026-07-13, Artist
        // field left empty even though Instrument had correctly filled)
        // is consistent with grabbing an element reference while that
        // re-render is still settling. A short pause here, plus
        // verifying the value actually stuck immediately after setting
        // it (and retrying once against a freshly re-queried element if
        // not), is a defensive mitigation for that race -- not a
        // confirmed root cause, since this couldn't be directly debugged
        // without live devtools access.
        await new Promise(function(resolve) {{ setTimeout(resolve, 400); }});

        var targetInput = await waitFor(function() {{ return findVisible('input.relationship-target'); }}, 6000);
        targetInput.click();
        targetInput.focus();
        setNativeValue(targetInput, DATA.targetMbid);

        if (targetInput.value !== DATA.targetMbid) {{
            // The value didn't stick -- likely a re-render replaced this
            // element out from under us. Re-query fresh and try once more
            // before giving up to the normal resolve-or-timeout wait below.
            targetInput = await waitFor(function() {{ return findVisible('input.relationship-target'); }}, 4000);
            targetInput.click();
            targetInput.focus();
            setNativeValue(targetInput, DATA.targetMbid);
        }}

        // MBID paste either auto-resolves (the input's own value changes
        // to the artist's real name) or surfaces a matching suggestion
        // to click -- whichever happens first, this doesn't assume which.
        await waitFor(function() {{
            if (targetInput.value && targetInput.value !== DATA.targetMbid) return true;
            var opt = document.querySelector('li[id*="' + DATA.targetMbid + '"]');
            if (opt) {{ opt.click(); return true; }}
            return false;
        }}, 8000);

        var doneBtn = await waitFor(function() {{
            var btns = document.querySelectorAll('.form .buttons-right button.positive');
            for (var i = 0; i < btns.length; i++) {{
                if (!btns[i].disabled) return btns[i];
            }}
            return null;
        }}, 6000);
        doneBtn.click();

        // Same stale-element-reference race as the Artist field mitigation
        // above (John, 2026-07-14, confirmed live: dialog closed and the
        // relationship showed as pending correctly, but the edit note
        // textarea stayed empty despite this fill step running with no
        // error). Adding a relationship likely re-renders nearby page
        // regions -- a short settle pause plus verify-and-retry against a
        // freshly re-queried element, exactly like the Artist field fix.
        await new Promise(function(resolve) {{ setTimeout(resolve, 400); }});

        var noteEl = await waitFor(function() {{ return document.getElementById('edit-note-text'); }}, 4000);
        setNativeValue(noteEl, DATA.editNote);

        if (noteEl.value !== DATA.editNote) {{
            noteEl = await waitFor(function() {{ return document.getElementById('edit-note-text'); }}, 4000);
            setNativeValue(noteEl, DATA.editNote);
        }}

        alert('MetaForge filled in the relationship and edit note below "Release relationships" -- '
              + 'please review the Preview and edit note, then click "Enter edit" yourself to submit.');
    }}

    run().catch(fail);
}})();
"""


def _build_release_relationship_seed():
    """
    Request: {key: candidate_key}. Resolves the candidate's release-level
    seed (link_type/artist MBID/release MBID), builds the automation
    script, and hands back {url, script} for the frontend to open via a
    real navigation + evaluate_js -- NOT the html= companion-window
    pattern the other seed builders use, since this needs a genuine
    top-level load of MusicBrainz's own live page for the script to run
    against, not a locally-built static page.
    """
    data = request.json or {}
    key = data.get("key")
    if not key:
        return jsonify({"status": "error", "message": "key is required."}), 400

    candidates = {_candidate_key(c): c for c in _load_personnel_candidates()}
    candidate = candidates.get(key)
    if not candidate:
        return jsonify({"status": "error", "message": "Candidate not found."}), 404

    link_type, search_term, instrument_term = _release_seed_fields(candidate.get("relation_type"), candidate.get("role"))
    if not link_type:
        return jsonify({"status": "error", "message": "No confirmed release-level relationship type for this credit yet -- use the per-track submission instead."}), 400

    release_id = _get_release_mbid(candidate.get("mf_id"))
    if not release_id:
        return jsonify({"status": "error", "message": "No MusicBrainz release ID found for this album."}), 400

    artist_match = None
    target_mbid = candidate.get("mb_target_mbid")
    if not target_mbid:
        artist_match = _fetch_artist_by_name(candidate.get("name"))
        target_mbid = artist_match.get("mbid") if artist_match else None
    if not target_mbid:
        return jsonify({"status": "error", "message": "No MusicBrainz artist match found -- add this relationship manually."}), 400

    # is_album_scope_step=False deliberately: the whole point of a
    # release-level relationship is that the "captured at album level,
    # not confirmed per-track" caveat no longer applies -- the fact IS
    # genuinely release-wide now, not an assumption being spread across
    # tracks that were never individually checked.
    edit_note = _evidence_to_personnel_edit_note(candidate, artist_match, is_album_scope_step=False, narrowed=False, entity_label="release")
    script = _build_release_relationship_automation_js(link_type, target_mbid, candidate.get("name"), edit_note, search_term, instrument_term)

    return jsonify({
        "status": "success",
        "url": f"https://musicbrainz.org/release/{release_id}/edit-relationships",
        "script": script,
        "title": f"MusicBrainz: {candidate.get('name')} (release-wide)",
        "artist_match": artist_match,
    })
# --- END OF FILE musicbrainz_submit.py ---
