# ==============================================================
# MetaForge Studio: Original Year Resolution Engine
# File: year_resolution_engine.py
# Role: 6-tier waterfall resolving a track's TRUE original release year,
#       distinct from the release/reissue year of the specific pressing
#       in hand. Never fabricates: unresolved is reported honestly.
#
# Tier order: MB Recording (+ AcoustID sibling recordings) -> MB
# Release-Group -> Discogs -> Wikipedia -> AI web search -> honest
# fallback.
#
# "Tentative" mechanism: for a compilation (is_compilation=1), tier 1/2
# results are NOT trusted outright, whether they match release_year (a
# coincidental match -- MB often has no earlier catalogued release for
# obscure recordings, and silently defaults to whatever compilation is
# in its database) or differ from it (a real MB value that's still just
# some OTHER undocumented reissue's date, not necessarily the true
# original -- e.g. Blind Willie Johnson's true 1920s recordings showing
# "1991" in MB, a CD reissue date). Both are held as `tentative` at a
# confidence reflecting how strong that raw signal is on its own, and
# tiers 3-5 are still given a chance to corroborate or override it via
# ONE shared rule (see _consider_against_tentative):
#   - agreement -> corroborate (boost confidence, relabel source)
#   - an independently-found EARLIER year -> override outright (a real
#     original can never postdate any other verified appearance)
#   - a later/different year from a tier whose own flat confidence
#     beats the tentative's current confidence -> override
#   - otherwise -> hold the tentative, keep trying the next tier
# If MB found nothing at all (a genuine blank slate), tiers 3-5 keep
# their original behavior: first find wins outright, no extra
# corroboration required -- there's no unreliable MB signal to
# reconcile against in that case.
#
# AcoustID sibling recordings: the same acoustic performance sometimes
# gets catalogued as separate MB recording entities across different
# releases. fingerprint_engine.py's existing AcoustID lookup already
# fetches every sibling recording MBID for free (via meta=recordings);
# for compilations, Tier 1 checks all of them and takes the earliest
# plausible date, since a sibling may have better data than the one
# recording our pipeline happened to match.
# ==============================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from mb_resolution_engine import _normalize_mb_year

CONF_MB_RECORDING = 100
CONF_MB_RECORDING_DIFFERING_TENTATIVE = 70
CONF_DISCOGS_CORROBORATED = 95
CONF_DISCOGS = 90
# Notes explicitly describing a RECORDING/session date, with no release
# date mentioned at all, are weaker evidence for TORY (original RELEASE
# year) than an explicit release-date statement -- the two are genuinely
# different facts (see ai_engine.extract_track_dates_from_notes). Kept
# deliberately close to CONF_DISCOGS rather than far below it: in
# practice the recording-to-release gap for physical singles-era
# pressings is usually small (John, 2026-07-09), so this is an honest
# confidence penalty, not a signal to distrust the value outright.
CONF_DISCOGS_RECORDING_DATE_PROXY = 80
CONF_MB_RELEASE_GROUP = 75
CONF_MB_RELEASE_GROUP_DIFFERING_TENTATIVE = 62
CONF_WIKIPEDIA = 65
CONF_AI_GROUNDED = 50
CONF_MB_RECORDING_TENTATIVE = 40
CONF_MB_RELEASE_GROUP_TENTATIVE = 35
CONF_UNRESOLVED = 0

SRC_MB_RECORDING = "MusicBrainz Recording"
SRC_MB_RECORDING_DIFFERING_TENTATIVE = "MusicBrainz Recording (Unverified — Differs From Release Year)"
SRC_MB_RELEASE_GROUP = "MusicBrainz Release-Group"
SRC_MB_RELEASE_GROUP_DIFFERING_TENTATIVE = "MusicBrainz Release-Group (Unverified — Differs From Release Year)"
SRC_DISCOGS_CORROBORATED = "Discogs (Corroborates MusicBrainz)"
SRC_DISCOGS = "Discogs"
SRC_DISCOGS_MASTER = "Discogs (Master Release)"
SRC_WIKIPEDIA = "Wikipedia"
SRC_WIKIPEDIA_CORROBORATED = "Wikipedia (Corroborates MusicBrainz)"
SRC_AI_WEB = "AI Web Search"
SRC_AI_WEB_CORROBORATED = "AI Web Search (Corroborates MusicBrainz)"
SRC_MB_RECORDING_TENTATIVE = "MusicBrainz Recording (Unverified — Coincidental Match)"
SRC_MB_RELEASE_GROUP_TENTATIVE = "MusicBrainz Release-Group (Unverified — Coincidental Match)"
SRC_UNRESOLVED = "Unresolved (Release Year Fallback)"

MIN_PLAUSIBLE_YEAR = 1860  # comfortably before the phonograph (1877); guards
                           # against a malformed/misattributed 4-digit year
                           # being blindly trusted as "earlier, therefore true."


def _result(year, conf: int, source: str, leak: int, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = {
        "original_year": str(year),
        "orig_year_conf": conf,
        "orig_year_source": source,
        "leak_flag": leak,
    }
    if evidence:
        result["orig_year_evidence"] = evidence
    return result


def _is_plausible_year(year) -> bool:
    return bool(year) and str(year).isdigit() and int(year) >= MIN_PLAUSIBLE_YEAR


def _consider_against_tentative(
    tentative: Optional[Dict[str, Any]],
    candidate_year,
    candidate_conf: int,
    candidate_source: str,
    corroborated_conf: int,
    corroborated_source: str,
    candidate_evidence: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Shared decision rule for whether a later tier's finding corroborates,
    overrides, or is held off against an existing tentative result:

      - candidate agrees with tentative -> corroborate (boost confidence,
        relabel source) -- independent agreement is the strongest signal
        short of a citation.
      - candidate is EARLIER than tentative (both plausible) -> override
        outright, regardless of raw tier confidence. A verified original
        can never postdate an independently-sourced earlier appearance.
      - candidate is later/different AND this tier's own flat confidence
        beats the tentative's current confidence -> override.
      - otherwise -> hold (keep the existing tentative, try next tier).

    Returns (result, is_final). is_final=False means "this is the new
    tentative, keep going" -- callers should assign it back to their
    `tentative` variable and continue the waterfall.
    """
    if tentative is None:
        return _result(candidate_year, candidate_conf, candidate_source, 0, candidate_evidence), False

    tent_year = tentative["original_year"]
    tent_conf = tentative["orig_year_conf"]

    if str(candidate_year) == str(tent_year):
        return _result(candidate_year, corroborated_conf, corroborated_source, 0, candidate_evidence), True

    if _is_plausible_year(candidate_year) and _is_plausible_year(tent_year):
        if int(candidate_year) < int(tent_year):
            return _result(candidate_year, candidate_conf, candidate_source, 0, candidate_evidence), True

    if candidate_conf > tent_conf:
        return _result(candidate_year, candidate_conf, candidate_source, 0, candidate_evidence), True

    return tentative, False


def _earliest_recording_year(mb, recording_id: Optional[str], sibling_ids: Optional[List[str]]) -> Optional[str]:
    """
    Returns the earliest plausible first-release-date across the primary
    recording_id and any AcoustID-discovered sibling recording MBIDs
    (acoustically identical performances catalogued as separate MB
    recording entities). One extra MB API call per sibling, via the same
    rate-limited `mb` instance. Never raises; a sibling lookup failure is
    silently skipped. Falls back to the primary's own raw result if no
    plausible year is found anywhere (preserves prior behavior when
    there are no siblings or none are plausible).
    """
    primary_year = mb.get_recording_first_release_date(recording_id)

    years = [primary_year] if _is_plausible_year(primary_year) else []

    for sib_id in (sibling_ids or []):
        if not sib_id or sib_id == recording_id:
            continue
        try:
            sib_year = mb.get_recording_first_release_date(sib_id)
        except Exception:
            sib_year = None
        if _is_plausible_year(sib_year):
            years.append(sib_year)

    if not years:
        return primary_year

    return min(years, key=int)


def resolve_original_year(
    recording_id: Optional[str],
    group_id: Optional[str],
    group_first_release_date_hint: Optional[str],
    artist: str,
    title: str,
    album: str,
    release_year: str,
    track_number: int,
    total_tracks: int,
    is_compilation: int,
    mb,
    year_cache: Dict[str, Any],
    ai_enabled: bool = True,
    acoustid_recording_ids: Optional[List[str]] = None,
    personnel_preseed: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolves a track's true original release year via the 6-tier waterfall
    described above. Never raises -- any failure at any tier falls through
    to the next, and the final fallback always succeeds.

    year_cache is a plain dict, shared and mutated across every track in
    the same album batch -- Discogs and Wikipedia lookups are expensive
    (HTTP + AI extraction) and album-level, not track-level, so they must
    only ever run ONCE per album regardless of how many tracks need them.

    personnel_preseed, if provided, is a plain dict this function WRITES
    to (keyed by recording_id -> raw MB relations list) as a side effect
    of Tier 1's own lookup -- Personnel Engine v2's free-riding manifest
    pre-seed capture, see MBResolutionEngine.
    get_recording_first_release_date_and_relations(). Purely additive;
    does not affect the year this function returns.
    """

    tentative: Optional[Dict[str, Any]] = None

    # ---------------------------------------------------------
    # Tier 1: MB recording direct lookup, strengthened by AcoustID
    # sibling recordings. Sibling check is MB-only cost (no Discogs/AI),
    # so it runs whenever a primary year was found, regardless of
    # is_compilation -- it might resolve a track for free before ever
    # touching the more expensive tiers below.
    #
    # "Coincidental match" (MB's answer exactly equals release_year) is
    # ALWAYS ambiguous -- MB may just be echoing this pressing's own year
    # rather than having genuinely resolved anything -- regardless of
    # whether the release is flagged Compilation. Verified live: an
    # ordinary, non-compilation reissue (The Pilgrim Travelers' "Soul
    # Stirring Gospel Sounds," 1962 original miscatalogued as 2005) hit
    # this exact failure mode. "Differing" (a real, different MB value)
    # stays compilation-only, since for an ordinary album a differing MB
    # value is usually genuinely trustworthy -- widening THAT branch
    # would reintroduce Discogs/AI cost for the common, already-correct
    # case (e.g. Eagles/Nevermind).
    # ---------------------------------------------------------
    mb_lookup = mb.get_recording_first_release_date_and_relations(recording_id)
    year = mb_lookup["year"]

    if personnel_preseed is not None and recording_id:
        personnel_preseed[recording_id] = mb_lookup["relations"]

    if year:
        year = _earliest_recording_year(mb, recording_id, acoustid_recording_ids)

    if year:
        if str(year) == str(release_year):
            tentative = _result(year, CONF_MB_RECORDING_TENTATIVE, SRC_MB_RECORDING_TENTATIVE, 0)
        elif is_compilation:
            tentative = _result(year, CONF_MB_RECORDING_DIFFERING_TENTATIVE, SRC_MB_RECORDING_DIFFERING_TENTATIVE, 0)
        else:
            return _result(year, CONF_MB_RECORDING, SRC_MB_RECORDING, 0)

    # ---------------------------------------------------------
    # Tier 2: MB release-group first-release-date. Only evaluated if
    # tier 1 found nothing at all (a tentative tier-1 match already
    # outranks whatever tier 2 would find). Prefers the hint captured
    # once at Stage 2. No AcoustID sibling check here -- siblings are
    # recording-level entities; release-group has no equivalent.
    # Same coincidental-vs-differing split as tier 1 above.
    # ---------------------------------------------------------
    if tentative is None:
        year = _normalize_mb_year(group_first_release_date_hint)
        if not year and group_id and group_id not in ("None", "Unknown", ""):
            try:
                rg = mb.get_release_group(group_id)
                year = _normalize_mb_year(rg.get("first-release-date"))
            except Exception:
                year = None
        if year:
            if str(year) == str(release_year):
                tentative = _result(year, CONF_MB_RELEASE_GROUP_TENTATIVE, SRC_MB_RELEASE_GROUP_TENTATIVE, 0)
            elif is_compilation:
                tentative = _result(year, CONF_MB_RELEASE_GROUP_DIFFERING_TENTATIVE, SRC_MB_RELEASE_GROUP_DIFFERING_TENTATIVE, 0)
            else:
                return _result(year, CONF_MB_RELEASE_GROUP, SRC_MB_RELEASE_GROUP, 0)

    # ---------------------------------------------------------
    # Tier 3: Discogs. Reached whenever tiers 1-2 didn't already return
    # outright -- either nothing was found, or only a tentative match
    # (coincidental or differing). Fetch+parse is memoized in
    # year_cache, so this is a cheap dict lookup after the first track
    # that needs it.
    #
    # Two independent Discogs signals are consulted: a per-track year
    # parsed from a specific release's notes (chronological-compilation
    # style, e.g. Golden Gate Quartet/Eddie Condon), and an album-wide
    # master-release year (Discogs' own canonical/original concept,
    # analogous to MB's release-group first-release-date -- verified
    # live to correctly resolve cases the per-release notes path can't,
    # e.g. an ordinary album whose notes have no date breakdown at all).
    # When both exist and disagree, earliest wins, same rule as
    # everywhere else in this file. Source label reflects whichever
    # signal actually produced the final value.
    # ---------------------------------------------------------
    try:
        import discogs_resolution_engine

        discogs_resolution_engine.resolve_album_track_dates(artist, album, year_cache)
        track_year_entry = year_cache.get("discogs_track_map", {}).get(track_number)
        track_year = track_year_entry.get("year") if track_year_entry else None
        track_date_type = track_year_entry.get("date_type") if track_year_entry else None
        master_year = year_cache.get("discogs_master_year")

        # A compilation's Discogs "master year" is when the compilation
        # PRODUCT was first assembled/issued -- not when any individual
        # track was originally recorded. Meaningless (and actively
        # misleading) as a per-track date for a various-era anthology, so
        # it's excluded entirely for is_compilation=1; only the per-track
        # notes-parsed signal is trustworthy there. Verified live: Discogs
        # master 1006666 ("The Best Of The Pilgrim Travelers," 1970) is a
        # correctly-matched compilation -- the bug wasn't a wrong match, it
        # was applying a product-level year to tracks each originally
        # recorded decades apart.
        if is_compilation:
            master_year = None

        discogs_used_track_year = False
        if track_year and master_year and str(track_year) != str(master_year):
            if (_is_plausible_year(track_year) and _is_plausible_year(master_year)
                    and int(master_year) < int(track_year)):
                discogs_year, discogs_source_label = master_year, SRC_DISCOGS_MASTER
            else:
                discogs_year, discogs_source_label, discogs_used_track_year = track_year, SRC_DISCOGS, True
        elif track_year:
            discogs_year, discogs_source_label, discogs_used_track_year = track_year, SRC_DISCOGS, True
        elif master_year:
            discogs_year, discogs_source_label = master_year, SRC_DISCOGS_MASTER
        else:
            discogs_year, discogs_source_label = None, None

        if discogs_year:
            discogs_evidence = year_cache.get("discogs_evidence")
            # Master-year comes from Discogs' own structured "year" field
            # (no free-text ambiguity), always full confidence. Track-year
            # comes from AI-parsed notes text, which may only describe a
            # recording/session date rather than a confirmed release date
            # -- see CONF_DISCOGS_RECORDING_DATE_PROXY's own comment. The
            # per-track date_type is copied into a fresh evidence dict
            # (never mutating the shared album-level year_cache entry,
            # which gets reused across every track in this album) so
            # downstream consumers (the correction-candidate log, MB
            # submission edit notes) can be honest about which kind of
            # date this actually is.
            discogs_conf = CONF_DISCOGS
            if discogs_used_track_year:
                if discogs_evidence:
                    discogs_evidence = dict(discogs_evidence)
                    discogs_evidence["date_type"] = track_date_type
                if track_date_type != "released":
                    discogs_conf = CONF_DISCOGS_RECORDING_DATE_PROXY
            if tentative is None:
                return _result(discogs_year, discogs_conf, discogs_source_label, 0, discogs_evidence)
            result, is_final = _consider_against_tentative(
                tentative, discogs_year, discogs_conf, discogs_source_label,
                CONF_DISCOGS_CORROBORATED, SRC_DISCOGS_CORROBORATED,
                candidate_evidence=discogs_evidence,
            )
            if is_final:
                return result
            tentative = result
    except Exception:
        pass

    # ---------------------------------------------------------
    # Tier 4: Wikipedia. Same memoization approach. If there's no
    # tentative to reconcile against, a lone find wins outright as
    # before. Typically only yields an album-level date (coarser than
    # Discogs' per-track/session granularity), which is expected.
    # ---------------------------------------------------------
    try:
        import wikipedia_resolution_engine

        wikipedia_resolution_engine.resolve_album_recorded_year(artist, album, year_cache)
        wiki_year = year_cache.get("wikipedia_year")

        # Same category error as Discogs master_year above: an album-level
        # "Recorded" infobox field is a product-level fact, not a per-track
        # one -- excluded entirely for compilations.
        if is_compilation:
            wiki_year = None

        if wiki_year:
            wiki_evidence = year_cache.get("wikipedia_evidence")
            if tentative is None:
                return _result(wiki_year, CONF_WIKIPEDIA, SRC_WIKIPEDIA, 0, wiki_evidence)
            result, is_final = _consider_against_tentative(
                tentative, wiki_year, CONF_WIKIPEDIA, SRC_WIKIPEDIA,
                CONF_WIKIPEDIA, SRC_WIKIPEDIA_CORROBORATED,
                candidate_evidence=wiki_evidence,
            )
            if is_final:
                return result
            tentative = result
    except Exception:
        pass

    # ---------------------------------------------------------
    # Tier 5: AI grounded web search -- the least reliable structured
    # attempt, tried before giving up entirely. Same "no tentative ->
    # lone find wins" shape as tiers 3-4.
    # ---------------------------------------------------------
    if ai_enabled:
        try:
            import ai_engine

            ai_result = ai_engine.resolve_original_year_ai(
                artist, title, album, release_year
            )
            if ai_result.get("resolved") and ai_result.get("year"):
                ai_year = ai_result["year"]
                ai_evidence = ai_result.get("evidence")
                if tentative is None:
                    return _result(ai_year, CONF_AI_GROUNDED, SRC_AI_WEB, 0, ai_evidence)
                result, is_final = _consider_against_tentative(
                    tentative, ai_year, CONF_AI_GROUNDED, SRC_AI_WEB,
                    CONF_AI_GROUNDED, SRC_AI_WEB_CORROBORATED,
                    candidate_evidence=ai_evidence,
                )
                if is_final:
                    return result
                tentative = result
        except Exception:
            pass

    # ---------------------------------------------------------
    # Tier 6: fall back to the tentative match if we have one (demoted,
    # honestly labeled), else the honest unresolved fallback. This is
    # the only path that can set leak_flag.
    # ---------------------------------------------------------
    if tentative is not None:
        return tentative

    return _result(str(release_year), CONF_UNRESOLVED, SRC_UNRESOLVED, 1)
