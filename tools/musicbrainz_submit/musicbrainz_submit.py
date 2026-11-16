# --- START OF FILE musicbrainz_submit.py ---
# ======================================================================
# MetaForge Studio: MusicBrainz Submit
# v2 (2026-11-16): rebuilt as an ALBUM PASS (John's decisions that day).
#
# The goal is giving back to MusicBrainz, so it has to be quick or nobody
# will bother. 1.x worked one credit at a time (open, submit, come back,
# mark), built for ~100 candidates; the queue is now ~41,000.
#
#   Queue:    personnel credits Album Personnel logged that MusicBrainz
#             didn't have, from Discogs, AllMusic and Wikipedia, plus the
#             user's own entries and AI credits the user confirmed in the
#             verify window. Unconfirmed AI credits are never sent (Google's
#             grounding terms don't allow citing them to MusicBrainz).
#             Confidence numbers are NOT used: they are a fixed value per
#             source, not a per-fact measure.
#   Mapping:  each credit's role text decides its MusicBrainz release
#             relationship (producer, arranger, composer, writer, lyricist,
#             vocals, backing vocals, a named instrument, performer). Vague
#             roles ("Featuring", "Musician") are not sendable.
#   Check:    opening an album reads the release from MusicBrainz (release,
#             track AND song level) so nothing it already has is re-sent,
#             and matches artists (MBID, or a unique exact-name match).
#   Batch:    up to 25 ticked credits go to the release's own relationship
#             editor in a companion window; the script adds them, writes one
#             edit note, and STOPS. The user clicks "Enter edit". Nothing
#             here submits itself.
#   Done:     afterwards MetaForge re-reads the release; credits now on
#             MusicBrainz are marked submitted and written to the
#             remediation log. No "Mark Submitted" button.
#
# Parked original-year code lives in year_corrections.py (tab hidden).
# ======================================================================
import contextlib
import io
import json
import re
import secrets
import shutil
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from flask import Response, current_app, jsonify, request, stream_with_context

from common import config_handler, db_engine
from common.mf_events import event, run_stream, signal

MB_DIR = config_handler.DATA_DIR / "musicbrainz"
PERSONNEL_CANDIDATE_LOG = MB_DIR / "personnel_correction_candidates.jsonl"
PERSONNEL_REVIEW_STATE = MB_DIR / "personnel_correction_review_state.json"
REMEDIATION_LOG = MB_DIR / "remediation_log.jsonl"
ARTIST_MATCH_CACHE = MB_DIR / "artist_match_cache.json"
ARTIST_CACHE_DAYS = 30

MB_API_USER_AGENT = "MetaForge/2.0 (musicbrainz_submit)"
METAFORGE_HEURISTICS_URL = "https://github.com/johnfoliot/MetaForge-Suite/blob/main/AI%20Heuristics.md"
BATCH_SIZE = 25

# --- [ QUEUE RULE ] ---------------------------------------------------------
QUEUE_SOURCES = {"Discogs", "AllMusic", "Wikipedia", "MetaForge (Manual)"}
# AI-found credits (and ones confirmed with Personnel's quick toggle) are sent
# only after the submitter checked a source page and found it explicit or
# inferred evidence. Anecdotal checks and no-source confirmations stay home.
SENDABLE_TIERS = {"explicit", "inferred"}

SOURCE_PHRASE = {
    "Discogs": "Discogs release credits",
    "AllMusic": "AllMusic album credits",
    "Wikipedia": "the Wikipedia article on this album",
    "MetaForge (Manual)": "the submitter's own research",
    "Submitter Confirmed": "a source the submitter checked",
    "AI Web Search": "a source the submitter checked",
}
SOURCE_LABEL = {"MetaForge (Manual)": "Your entry", "Submitter Confirmed": "Confirmed by you"}

VERIFICATION_TIER_EDIT_NOTE_TEXT = {
    "explicit": "The submitter directly confirmed this against an independent source.",
    "inferred": "The submitter found this matches independent evidence, though not specific to this exact release.",
    "anecdotal": "The submitter found a supporting mention in an independent source, without a solid citation.",
}


def in_queue(c):
    prov = c.get("provenance")
    if prov in QUEUE_SOURCES:
        return True
    return (prov in ("AI Web Search", "Submitter Confirmed")
            and c.get("verification_tier") in SENDABLE_TIERS
            and bool(c.get("verified_source_url")))


# --- [ ROLE -> MUSICBRAINZ RELEASE RELATIONSHIP ] ---------------------------
# Release-scope link_type IDs, all confirmed live or from MB's own
# relationship pages (see project_mb_contribution_tool memory): the same
# real-world relationship has a different ID per entity pair.
KINDS = {
    #  kind          link_type  type search term  label              MB API type names that already cover it
    "producer":   (30,  "produced",    "Producer",       {"producer"}),
    "arranger":   (295, "arranged",    "Arranger",       {"arranger", "instrument arranger", "vocal arranger", "orchestrator"}),
    "composer":   (55,  "composed",    "Composer",       {"composer", "writer"}),
    "writer":     (54,  "wrote",       "Writer",         {"writer", "composer", "lyricist"}),
    "lyricist":   (56,  "lyrics",      "Lyricist",       {"lyricist", "writer"}),
    "performer":  (51,  "performed",   "Performer",      {"performer", "instrument", "vocal"}),
    "vocals":     (60,  "vocals",      "Vocals",         {"vocal"}),
    "background": (60,  "vocals",      "Backing vocals", {"vocal"}),
    "instrument": (44,  "instruments", None,             {"instrument"}),
}

ROLE_RULES = [
    (re.compile(r"\barrange(d|r|rs|ment|ments)?\b"), "arranger"),
    (re.compile(r"^(composed by|composer|music by)\b"), "composer"),
    (re.compile(r"^(written[- ]by|writer|songwriter|words and music( by)?)\b"), "writer"),
    (re.compile(r"^(lyrics by|lyricist|words by|lyrics)\b"), "lyricist"),
    (re.compile(r"^(producer|produced by|co-producer)$"), "producer"),
    (re.compile(r"\b(backing|background) vocals?\b"), "background"),
    (re.compile(r"\bvocals?\b|\bvoice\b|\bsinger\b"), "vocals"),
]
RELATION_KIND = {"PRODUCED": "producer", "ARRANGED_BY": "arranger", "COMPOSED": "composer",
                 "WRITTEN_BY": "writer", "LYRICIST": "lyricist"}
VAGUE_ROLES = {
    "featuring", "featured", "featured artist", "musician", "musicians", "main personnel", "personnel",
    "backing band", "band", "associated with", "misc", "miscellaneous", "performer", "artist",
    "primary artist", "main artist", "lead artist", "guest", "other", "with", "accompanied by",
    "orchestra", "ensemble", "group member", "member",
}


# Wikipedia/AllMusic role text sometimes lists the tracks: "Backing Vocals (6, 15)",
# "Songwriting (tracks 5 and 13)". Those credits are not release-wide.
TRACK_LIST = re.compile(r"\((tracks?|songs?)?\s*[\d\s,\-–&]+(and\s*\d+)?\)|\btracks?\s+\d")
# Roles that are clearly not an instrument and have no confirmed release relationship.
NOT_INSTRUMENT = re.compile(
    r"\b(program+(ed|ing)?|remix(ed)?|engineer(ed)?|mix(ed|ing)?|master(ed|ing)|record(ed|ing)|"
    r"orchestrat\w*|conduct\w*|photo\w*|design\w*|artwork|art direction|cover|liner|notes|crew|"
    r"management|manager|executive|soloist|guest|speech|instruments|lacquer|sleeve|layout|"
    r"compiled|edited|editor|director|assistant|technician|tour|a&r|copyist|transcri\w*)\b")


QUALIFIED_ROLE = re.compile(r"\b(executive|reissue|compilation|film|associate|assistant|additional|co|remaster\w*)\b")


def _role_base(role):
    """'Arranged By [Strings]' -> 'Arranged By'; 'Drums [Studio]' -> 'Drums'; Wikipedia <ref> tags dropped."""
    role = re.sub(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>|<ref[^>]*>", " ", role or "")
    return re.sub(r"\s+", " ", re.sub(r"\s*\[.*?\]\s*", " ", role)).strip()


def _not_sendable(label, reason, why):
    return {"sendable": False, "label": label, "reason": reason, "why": why}


def mb_relationship(relation_type, role, tracks=None):
    """What MusicBrainz release relationship a credit becomes, or why it can't be sent.

    tracks: the source restricted this credit to certain tracks (Discogs' own
    "tracks" field), so it is not release-wide.

    -> {"sendable": True, "kind", "link_type", "type_term", "instrument", "label", "mb_types"}
       {"sendable": False, "label", "reason", "why"}   why: tracks | vague | unsupported
    """
    base = _role_base(role)
    low = base.lower()
    if tracks or TRACK_LIST.search(low):
        on = f" (tracks {tracks})" if tracks else ""
        return _not_sendable(base or role, f"Only on some tracks{on}, so it isn't a credit for the whole release. "
                             "Sending credits to single tracks is a later step.", "tracks")
    # Qualified or non-musical roles never fall back to their broad relation:
    # "Executive Producer", "Reissue Producer" and "Compilation Producer" are
    # not the release's producer, and "Mastered By" is not a performance.
    if QUALIFIED_ROLE.search(low) or NOT_INSTRUMENT.search(low):
        return _not_sendable(base, "MetaForge can't send this kind of credit to MusicBrainz yet.", "unsupported")
    kind = next((k for rx, k in ROLE_RULES if rx.search(low)), None)
    if not kind:
        kind = RELATION_KIND.get(relation_type)
    if not kind:
        if relation_type in ("PERFORMED_ON", "ASSOCIATED_WITH"):
            if not low or low in VAGUE_ROLES:
                return _not_sendable(base or "No role given", "Too general for a MusicBrainz relationship.", "vague")
            kind = "instrument"
        else:
            return _not_sendable(base or role or relation_type,
                                 "MetaForge can't send this kind of credit to MusicBrainz yet.", "unsupported")
    link_type, term, label, mb_types = KINDS[kind]
    return {
        "sendable": True, "kind": kind, "link_type": link_type, "type_term": term,
        "instrument": low if kind == "instrument" else None,
        "label": label or base[:1].upper() + base[1:],
        "mb_types": sorted(mb_types),
    }


# --- [ MUSICBRAINZ INSTRUMENT NAMES ] ---------------------------------------
# Credits say "Sax (Tenor)", "Guitars", "Lead Guitar"; MusicBrainz's instrument
# list says "tenor saxophone", "guitar". Each distinct role is looked up once
# (instrument search, exact name or alias only) and remembered. A role with no
# exact MusicBrainz instrument is not sendable: guessing would send a vaguer
# or different fact than the source gives.
INSTRUMENT_CACHE = MB_DIR / "instrument_names.json"
SECTION_WORDS = re.compile(r"\b(horns|brass|strings|reeds|winds|woodwinds|percussions?|rhythm section)$")


def _instrument_variants(term):
    t = term.strip().lower()
    out = [t]
    m = re.match(r"^(.+?)\s*\((.+)\)$", t)          # "sax (tenor)" -> "tenor sax"
    if m:
        out.append(f"{m.group(2)} {m.group(1)}")
    for v in list(out):
        out.append(re.sub(r"\bsax\b", "saxophone", v))
    for v in list(out):
        if v.endswith(" bass") and v != "double bass":
            out.append(v + " guitar")               # "electric bass" -> "electric bass guitar"
    for v in list(out):
        # "guitars" -> "guitar". Never for section words: "Horns" is a horn
        # section, while MusicBrainz's "horn" is the French horn.
        if v.endswith("s") and not v.endswith("ss") and not SECTION_WORDS.search(v):
            out.append(v[:-1])
    return list(dict.fromkeys(out))


def _lookup_instrument(term, cache):
    """-> MusicBrainz's own instrument name, or None. Cached (hits and misses)."""
    if term in cache:
        return cache[term]
    # An instrument's own name always wins over an alias: "harmonica" is also
    # an alias of the glass harmonica, a different instrument (seen live).
    # Otherwise an alias counts when exactly one instrument has it; that
    # includes MusicBrainz's own curated search hints ("drums" -> drum set,
    # "vibes" -> vibraphone, "upright bass" -> double bass).
    found = None
    for v in _instrument_variants(term):
        q = v.replace('"', "")
        d = _mb_get("instrument", {"query": f'instrument:"{q}" OR alias:"{q}"', "limit": 25})
        insts = d.get("instruments") or []
        named = [i for i in insts if (i.get("name") or "").lower() == v]
        if named:
            found = v
            break
        aliased = [i for i in insts if any((a.get("name") or "").lower() == v for a in i.get("aliases") or [])]
        if len(aliased) == 1:
            found = (aliased[0].get("name") or "").lower()
            break
    cache[term] = found
    return found


# --- [ HELPERS ] ------------------------------------------------------------

def _norm(s):
    """Name comparison key: accents, case, punctuation and 'The ' ignored."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"^the\s+", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


TITLE_STOP = {"the", "and", "of", "a", "an", "in", "on", "to", "for", "live", "vol", "volume", "edition", "deluxe",
              "remastered", "remaster", "version", "album", "de", "la", "le", "el", "los"}


def _source_elsewhere(url, album):
    """True when a confirmed credit's source link names no word of this album's
    title: the source probably describes a different release (seen live: Lee
    Oskar's "Those Sunny Days" credits confirmed against "So Much In Love")."""
    if not url:
        return False
    from urllib.parse import unquote, urlparse
    path = _norm(unquote(urlparse(url).path).replace("-", " ").replace("_", " "))
    words = [w for w in _norm(album).split() if len(w) > 2 and w not in TITLE_STOP]
    return bool(words) and not any(re.search(rf"\b{re.escape(w)}\b", path) for w in words)


def _candidate_key(c):
    """Same key as 1.x, so existing review state carries over."""
    rid = c.get("mb_recording_id")
    scope = rid if rid else c.get("mf_id")
    return f"{scope}|{c.get('name')}|{c.get('relation_type')}|{c.get('role')}"


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_state():
    return _read_json(PERSONNEL_REVIEW_STATE, {})


def _save_state(state):
    """The state file is shared with 1.x. The first v2 write keeps a copy of the 1.x file."""
    PERSONNEL_REVIEW_STATE.parent.mkdir(parents=True, exist_ok=True)
    backup = PERSONNEL_REVIEW_STATE.with_name(PERSONNEL_REVIEW_STATE.stem + ".pre-v2.json")
    if PERSONNEL_REVIEW_STATE.exists() and not backup.exists():
        shutil.copy2(PERSONNEL_REVIEW_STATE, backup)
    tmp = PERSONNEL_REVIEW_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(PERSONNEL_REVIEW_STATE)


def _log_remediation(payload):
    entry = {"type": "personnel", "timestamp": datetime.now().isoformat(), **payload}
    REMEDIATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REMEDIATION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# --- [ THE QUEUE ] ----------------------------------------------------------

def _build_queue():
    """Every queue credit, latest log line per key, still believed by MetaForge's own DB.

    1.x took ~100 s here: one edges query per album (77 s) and the junk-role
    regexes rebuilt 5.3 million times (47 s). Now: one edges query, one
    library query, and each distinct role/name checked once.
    """
    if not PERSONNEL_CANDIDATE_LOG.exists():
        return [], {}
    from tools.personnel.edge_normalizer import is_junk_name, is_junk_role, load_config
    config = load_config()
    junk_role, junk_name = {}, {}

    live = {}
    for r in db_engine.execute_query("SELECT source_id, target_id, role FROM edges WHERE source_type='album'") or []:
        live.setdefault(r["source_id"], set()).add((r["target_id"], (r["role"] or "").strip().lower()))
    albums = {r["mf_id"]: r for r in db_engine.execute_query(
        "SELECT mf_id, artist_name, album_title, mb_album_id FROM library_master") or []}

    self_roles = {"primary artist", "artist", "main artist", "performer", "lead artist"}
    by_key = {}
    with open(PERSONNEL_CANDIDATE_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                c = json.loads(line)
            except Exception:
                continue
            if not in_queue(c):
                continue
            mf_id = c.get("mf_id")
            if mf_id not in albums:
                continue   # album no longer in the library (renamed, merged or removed)
            role = c.get("role") or ""
            name = c.get("name") or ""
            if role not in junk_role:
                junk_role[role] = is_junk_role(role, config)
            if name not in junk_name:
                junk_name[name] = is_junk_name(name, config)
            if junk_role[role] or junk_name[name]:
                continue
            if (c.get("relation_type") == "PERFORMED_ON" and role.strip().lower() in self_roles
                    and _norm(name) == _norm(c.get("artist"))):
                continue   # "the artist performed on their own album": MusicBrainz already knows
            if (c.get("target_id"), role.strip().lower()) not in live.get(mf_id, ()):
                continue   # deleted from MetaForge's database since it was logged
            key = _candidate_key(c)
            old = by_key.get(key)
            if not old or c.get("timestamp", "") >= old.get("timestamp", ""):
                by_key[key] = c
    cands = list(by_key.values())
    _mark_discogs_track_credits(cands)
    return cands, albums


def _mark_discogs_track_credits(cands):
    """Discogs' release-level credits can carry their own "tracks" field
    ("A1 to A3", "3, 5, 11"). Album Personnel logged those as album-wide;
    the album's manifest still has the field, so read it back here and set
    c["_tracks"]. If the same person also has the same role with no track
    list, the album-wide credit stands. (2,527 of 10,854 such credits, measured
    2026-11-16.)"""
    want = {c["mf_id"] for c in cands if c.get("provenance") == "Discogs" and not c.get("mb_recording_id")}
    if not want:
        return
    from tools.personnel.discogs_personnel_engine import _strip_discogs_disambiguation
    from tools.personnel.edge_normalizer import normalize_personnel
    atoms = {}   # role text -> [(relation_type, role)]: the same split Album Personnel made,
                 # once per distinct text (the parser re-reads its config on every call)

    def split(role_text):
        if role_text not in atoms:
            with contextlib.redirect_stdout(io.StringIO()):   # it prints a DEBUG line per role
                atoms[role_text] = [(a["relation_type"], a["role"]) for a in normalize_personnel(role_text)]
        return atoms[role_text]

    folders = {}
    for r in db_engine.execute_query("SELECT mf_id, file_path FROM tracks") or []:
        if r["mf_id"] in want and r["mf_id"] not in folders:
            folders[r["mf_id"]] = Path(r["file_path"]).parent
    restricted = {}
    for mf_id, folder in folders.items():
        try:
            d = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        limited, whole = {}, set()
        for entry in (d.get("discogs_extraartists") or {}).get("album") or []:
            tracks = (entry.get("tracks") or "").strip()
            name = _strip_discogs_disambiguation(entry.get("name") or "")
            if not name or not entry.get("role"):
                continue
            for rel_type, role in split(entry["role"]):
                k = (name, rel_type, role)
                if tracks:
                    limited.setdefault(k, tracks)
                else:
                    whole.add(k)
        restricted[mf_id] = {k: t for k, t in limited.items() if k not in whole}
    for c in cands:
        if c.get("provenance") == "Discogs" and not c.get("mb_recording_id"):
            t = restricted.get(c["mf_id"], {}).get((c.get("name"), c.get("relation_type"), c.get("role")))
            if t:
                c["_tracks"] = t


def _queue():
    """Cached across requests until the log or the database changes (this file is
    re-executed on every request, so the cache lives on the Flask app)."""
    def stamp(p):
        try:
            s = Path(p).stat()
            return (s.st_size, s.st_mtime_ns)
        except OSError:
            return None
    key = (stamp(PERSONNEL_CANDIDATE_LOG), stamp(config_handler.DB_PATH))
    cache = current_app.extensions.setdefault("mbs_queue", {})
    if cache.get("key") != key:
        cands, albums = _build_queue()
        cache.update(key=key, cands=cands, albums=albums)
    return cache["cands"], cache["albums"]


def _status(c, state):
    """pending | dismissed | sent | submitted | on_mb (1.x 'submitted'/'dismissed' carry over)."""
    st = (state.get(_candidate_key(c)) or {}).get("status")
    return st if st in ("dismissed", "sent", "submitted", "on_mb") else "pending"


# --- [ DISPATCH ] -----------------------------------------------------------

def run_logic(action, tools_dir, env_path):
    if action in ("list_candidates", "build_seed", "mark_handled"):
        from tools.musicbrainz_submit import year_corrections   # parked; tab hidden in v2
        return {"list_candidates": year_corrections._list_candidates,
                "build_seed": year_corrections._build_seed,
                "mark_handled": year_corrections._mark_handled}[action]()
    actions = {
        "albums": _albums, "album": _album, "check": _check, "set_credit": _set_credit,
        "set_artist": _set_artist, "skip_album": _skip_album, "batch": _batch,
        "batch_status": _batch_status, "batch_done": _batch_done,
    }
    fn = actions.get(action)
    if not fn:
        return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400
    return fn()


# --- [ ALBUM LIST ] ---------------------------------------------------------

def _albums():
    cands, albums = _queue()
    state = _load_state()
    instruments = _read_json(INSTRUMENT_CACHE, {})
    out = {}
    for c in cands:
        mf = c["mf_id"]
        a = out.get(mf)
        if a is None:
            info = albums[mf]
            a = out[mf] = {"mf_id": mf, "artist": info["artist_name"], "album": info["album_title"],
                           "to_send": 0, "waiting": 0, "newest": "", "has_release": bool(info["mb_album_id"]),
                           "skipped": (state.get(f"album|{mf}") or {}).get("status") == "skipped",
                           "checked": bool((state.get(f"album|{mf}") or {}).get("checked_at"))}
        a["newest"] = max(a["newest"], c.get("timestamp", ""))
        st = _status(c, state)
        if c.get("mb_recording_id"):
            continue   # single-track credits: a later step
        if st == "sent":
            a["waiting"] += 1
        elif st == "pending" and _relationship(c, instruments)["sendable"]:
            a["to_send"] += 1
    rows = [a for a in out.values() if a["has_release"] and (a["to_send"] or a["waiting"])]
    return jsonify({"status": "ok", "albums": rows,
                    "credits": sum(a["to_send"] for a in rows if not a["skipped"])})


# --- [ ONE ALBUM ] ----------------------------------------------------------

def _relationship(c, instruments):
    """mb_relationship plus what's known about MusicBrainz's instrument names."""
    rel = mb_relationship(c.get("relation_type"), c.get("role"), c.get("_tracks"))
    if rel["sendable"] and rel["kind"] == "instrument" and rel["instrument"] in instruments:
        mb_name = instruments[rel["instrument"]]
        if not mb_name:
            return _not_sendable(rel["label"], f"MusicBrainz has no instrument called “{rel['label']}”.", "instrument")
        rel["instrument"] = mb_name
        rel["instrument_known"] = True
    return rel


def _album_credits(mf_id, state):
    cands, albums = _queue()
    info = albums.get(mf_id)
    if not info:
        return None, []
    instruments = _read_json(INSTRUMENT_CACHE, {})
    rows = []
    for c in cands:
        if c["mf_id"] != mf_id:
            continue
        key = _candidate_key(c)
        rel = _relationship(c, instruments)
        own = state.get(key) or {}
        rows.append({
            "key": key, "name": c.get("name"), "role": c.get("role"),
            "source": SOURCE_LABEL.get(c.get("provenance"), c.get("provenance")),
            "provenance": c.get("provenance"),
            "verification_tier": c.get("verification_tier"),
            "verified_source_url": c.get("verified_source_url"),
            "source_elsewhere": _source_elsewhere(c.get("verified_source_url"), info["album_title"]),
            "track": bool(c.get("mb_recording_id")),
            "tracks": c.get("_tracks"),
            "relationship": rel,
            "status": _status(c, state),
            "artist_mbid": own.get("artist_mbid") or c.get("mb_target_mbid"),
            "artist_name": own.get("artist_name"),
            "artist_chosen": bool(own.get("artist_mbid")),
            "artist_match": own.get("artist_match"),
            "mb_check": own.get("mb_check"),
            "mb_has": own.get("mb_has"),
            "timestamp": c.get("timestamp"),
        })
    rows.sort(key=lambda r: (r["relationship"].get("label") or "", _norm(r["name"])))
    return info, rows


def _album():
    data = request.get_json(silent=True) or {}
    state = _load_state()
    info, rows = _album_credits(data.get("mf_id"), state)
    if not info:
        return jsonify({"status": "error", "message": "That album isn't in the queue any more."}), 404
    album_state = state.get(f"album|{info['mf_id']}") or {}
    return jsonify({"status": "ok", "album": {
        "mf_id": info["mf_id"], "artist": info["artist_name"], "album": info["album_title"],
        "release": info["mb_album_id"], "checked_at": album_state.get("checked_at"),
        "skipped": album_state.get("status") == "skipped"}, "credits": rows})


# --- [ MUSICBRAINZ CHECK ] --------------------------------------------------

def _mb_get(path, params):
    from common import mb_client
    res = mb_client.get(path, params=params, headers={"User-Agent": MB_API_USER_AGENT}, timeout=30)
    return res.json()


def _release_relationships(release_id):
    """{(artist_mbid or None, norm_name): [(mb_type, (attributes...)), ...]} at release,
    track (recording) and song (work) level."""
    d = _mb_get(f"release/{release_id}", {
        "inc": "artist-rels+recordings+recording-level-rels+work-rels+work-level-rels+artist-credits"})
    found = []

    def take(rels):
        for x in rels or []:
            if x.get("target-type") == "artist" and x.get("artist"):
                found.append((x["artist"].get("id"), x["artist"].get("name"), x.get("target-credit") or "",
                              x.get("type"), tuple(a.lower() for a in (x.get("attributes") or []))))

    take(d.get("relations"))
    for medium in d.get("media") or []:
        for track in medium.get("tracks") or []:
            rec = track.get("recording") or {}
            take(rec.get("relations"))
            for x in rec.get("relations") or []:
                if x.get("target-type") == "work" and x.get("work"):
                    take(x["work"].get("relations"))
    return found


def _on_musicbrainz(credit, mbid, found):
    """('exact' | 'similar' | None, what MusicBrainz has). 'similar' = same person
    already credited in a related way that doesn't clearly match (e.g. organ
    where we have keyboards)."""
    rel = credit["relationship"]
    want = set(rel["mb_types"])
    name = _norm(credit["name"])
    similar = set()
    for a_id, a_name, credited, typ, attrs in found:
        same_person = (mbid and a_id == mbid) or name in (_norm(a_name), _norm(credited))
        if not same_person:
            continue
        has = f"{typ}: {', '.join(attrs)}" if attrs else typ
        if typ in want:
            if rel["kind"] == "instrument":
                inst = rel["instrument"]
                if any(a == inst or a.startswith(inst + " (") or inst.startswith(a + " (") for a in attrs):
                    return "exact", has
                similar.add(has)
            elif rel["kind"] == "background":
                if any("background" in a for a in attrs):
                    return "exact", has
                similar.add(has)
            else:
                return "exact", has
        elif typ in ("instrument", "vocal", "performer") and rel["kind"] in ("instrument", "vocals", "background", "performer"):
            similar.add(has)
    return ("similar", "; ".join(sorted(similar))) if similar else (None, None)


def _match_artist(name, cache):
    """MusicBrainz artist for a credited name. 'exact' only when exactly one artist
    scores 100 with this exact name (or alias); otherwise the user chooses."""
    key = _norm(name)
    hit = cache.get(key)
    if hit and time.time() - hit.get("at", 0) < ARTIST_CACHE_DAYS * 86400:
        return hit
    q = name.replace("\\", "\\\\").replace('"', '\\"')
    try:
        d = _mb_get("artist", {"query": f'artist:"{q}" OR alias:"{q}"', "limit": 5})
    except Exception:
        return {"status": "error", "options": []}
    options = []
    for a in d.get("artists") or []:
        names = {_norm(a.get("name"))} | {_norm(x.get("name")) for x in a.get("aliases") or []}
        options.append({"mbid": a.get("id"), "name": a.get("name"), "score": a.get("score"),
                        "disambiguation": a.get("disambiguation") or "", "country": a.get("country") or "",
                        "same_name": key in names})
    # "Perfect match" = exactly one result whose name or alias IS this name.
    # MusicBrainz's score ranks results against each other, so a real exact
    # name can score under 100 when a band name containing it ranks higher
    # (seen live: "Frank Gambale" vs "Frank Gambale All Star Band").
    exact = [o for o in options if o["same_name"]]
    status = "exact" if len(exact) == 1 else ("ambiguous" if len(exact) > 1 else ("loose" if options else "none"))
    hit = {"status": status, "mbid": exact[0]["mbid"] if status == "exact" else None,
           "name": exact[0]["name"] if status == "exact" else None, "options": options[:4], "at": time.time()}
    cache[key] = hit
    return hit


def _check():
    """NDJSON stream: read the release from MusicBrainz, settle each credit
    (already there / now there / needs checking), match artists."""
    data = request.get_json(silent=True) or {}
    mf_id = data.get("mf_id")
    lock = current_app.extensions.setdefault("mbs_check_lock", threading.Lock())
    if not lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "MusicBrainz is already being checked."}), 409

    def gen():
        try:
            yield from _check_stream(mf_id)
        finally:
            lock.release()
    return Response(stream_with_context(run_stream(gen(), "MusicBrainz Submit")), mimetype="application/x-ndjson")


def _check_stream(mf_id):
    state = _load_state()
    info, credits = _album_credits(mf_id, state)
    if not info or not info["mb_album_id"]:
        yield event("error", "This album has no MusicBrainz release ID, so it can't be checked.")
        return
    yield signal("progress", percent=2, label="Reading the release from MusicBrainz…")
    try:
        found = _release_relationships(info["mb_album_id"])
    except Exception as e:
        yield event("error", f"MusicBrainz couldn't be reached: {e}")
        return

    instruments = _read_json(INSTRUMENT_CACHE, {})
    unknown = sorted({c["relationship"]["instrument"] for c in credits
                      if c["relationship"].get("kind") == "instrument" and not c["relationship"].get("instrument_known")
                      and c["status"] in ("pending", "sent")})
    if unknown:
        for i, term in enumerate(unknown, 1):
            yield signal("progress", percent=3 + int(20 * i / len(unknown)),
                         label=f"Checking instrument names: {i} of {len(unknown)}")
            try:
                _lookup_instrument(term, instruments)
            except Exception:
                pass   # left unknown; looked up again next time
        INSTRUMENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        INSTRUMENT_CACHE.write_text(json.dumps(instruments, indent=1), encoding="utf-8")
        info, credits = _album_credits(mf_id, state)

    cache = _read_json(ARTIST_MATCH_CACHE, {})
    album_scope = [c for c in credits if not c["track"] and c["relationship"]["sendable"]
                   and c["status"] in ("pending", "sent")]
    need_lookup = sorted({c["name"] for c in album_scope if not c["artist_mbid"]}, key=_norm)
    matches = {}
    for i, name in enumerate(need_lookup, 1):
        if _norm(name) not in cache or time.time() - cache[_norm(name)].get("at", 0) >= ARTIST_CACHE_DAYS * 86400:
            yield signal("progress", percent=25 + int(70 * i / max(1, len(need_lookup))),
                         label=f"Matching artists: {i} of {len(need_lookup)}")
        matches[name] = _match_artist(name, cache)
    ARTIST_MATCH_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ARTIST_MATCH_CACHE.write_text(json.dumps(cache), encoding="utf-8")

    now = datetime.now().isoformat()
    counts = {"already": 0, "added": 0, "similar": 0}
    for c in album_scope:
        entry = state.setdefault(c["key"], {})
        m = None if c["artist_mbid"] else matches.get(c["name"])
        if m:   # options are kept only when the user has to choose (keeps the state file small)
            entry["artist_match"] = {k: m[k] for k in ("status", "mbid", "name")}
            if m["status"] != "exact":
                entry["artist_match"]["options"] = [{k: o[k] for k in ("mbid", "name", "disambiguation", "country")}
                                                    for o in m["options"]]
        mbid = c["artist_mbid"] or (m or {}).get("mbid")
        where, has = _on_musicbrainz(c, mbid, found)
        entry["mb_check"], entry["mb_has"] = where, has
        if where == "exact":
            if c["status"] == "sent":
                entry.update(status="submitted", timestamp=now, confirmed_at=now)
                counts["added"] += 1
                if not entry.get("remediation_logged"):
                    _log_remediation({"key": c["key"], "mf_id": mf_id, "artist": info["artist_name"],
                                      "album": info["album_title"], "name": c["name"], "role": c["role"],
                                      "provenance": c["provenance"], "mb_release_id": info["mb_album_id"],
                                      "artist_mbid": mbid, "relationship": c["relationship"]["label"],
                                      "via": "album pass (v2)"})
                    entry["remediation_logged"] = True
            else:
                entry.update(status="on_mb", timestamp=now)
                counts["already"] += 1
        elif where == "similar":
            counts["similar"] += 1
    state.setdefault(f"album|{mf_id}", {})["checked_at"] = now
    _save_state(state)
    yield signal("progress", percent=100, label="Checked")
    bits = []
    if counts["added"]:
        bits.append(f"{counts['added']} you sent {'is' if counts['added'] == 1 else 'are'} now on MusicBrainz")
    if counts["already"]:
        bits.append(f"{counts['already']} {'was' if counts['already'] == 1 else 'were'} already there")
    if counts["similar"]:
        bits.append(f"{counts['similar']} need{'s' if counts['similar'] == 1 else ''} checking")
    yield signal("checked")
    yield event("done", "MusicBrainz checked" + (": " + "; ".join(bits) + "." if bits else "."))


# --- [ USER CHOICES ] -------------------------------------------------------

def _set_credit():
    """Tick / untick ('dismissed' is remembered: don't send this credit)."""
    data = request.get_json(silent=True) or {}
    key, send = data.get("key"), data.get("send")
    if not key:
        return jsonify({"status": "error", "message": "No credit given."}), 400
    state = _load_state()
    entry = state.setdefault(key, {})
    if send:
        if entry.get("status") == "dismissed":
            entry.pop("status", None)
    else:
        entry["status"] = "dismissed"
    entry["timestamp"] = datetime.now().isoformat()
    _save_state(state)
    return jsonify({"status": "ok"})


def _set_artist():
    """The user picked which MusicBrainz artist a credit means (or cleared it)."""
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    if not key:
        return jsonify({"status": "error", "message": "No credit given."}), 400
    state = _load_state()
    entry = state.setdefault(key, {})
    if data.get("mbid"):
        entry["artist_mbid"], entry["artist_name"] = data["mbid"], data.get("name") or ""
    else:
        entry.pop("artist_mbid", None)
        entry.pop("artist_name", None)
    _save_state(state)
    return jsonify({"status": "ok"})


def _skip_album():
    data = request.get_json(silent=True) or {}
    mf_id = data.get("mf_id")
    state = _load_state()
    entry = state.setdefault(f"album|{mf_id}", {})
    if data.get("skip", True):
        entry["status"] = "skipped"
    else:
        entry.pop("status", None)
    _save_state(state)
    return jsonify({"status": "ok"})


# --- [ BATCH ] --------------------------------------------------------------

def _note_line(c):
    rel = c["relationship"]
    line = f"- {rel['label']}: {c['name']} (from {SOURCE_PHRASE.get(c['provenance'], c['provenance'])}"
    if c.get("verified_source_url"):
        line += f": {c['verified_source_url']}"
    line += ")"
    tier = VERIFICATION_TIER_EDIT_NOTE_TEXT.get(c.get("verification_tier") or "")
    if tier:
        line += " " + tier
    return line


def _batch():
    """Builds the companion-window script for up to 25 ticked credits."""
    data = request.get_json(silent=True) or {}
    mf_id, keys = data.get("mf_id"), list(dict.fromkeys(data.get("keys") or []))[:BATCH_SIZE]
    state = _load_state()
    info, credits = _album_credits(mf_id, state)
    if not info or not info["mb_album_id"]:
        return jsonify({"status": "error", "message": "This album has no MusicBrainz release ID."}), 400
    by_key = {c["key"]: c for c in credits}
    items = []
    for k in keys:
        c = by_key.get(k)
        if not c or c["track"] or not c["relationship"]["sendable"] or c["status"] != "pending":
            continue
        if c["relationship"]["kind"] == "instrument" and not c["relationship"].get("instrument_known"):
            continue   # not checked against MusicBrainz's instrument list yet
        entry = state.get(k) or {}
        mbid = c["artist_mbid"] or ((entry.get("artist_match") or {}).get("mbid"))
        if not mbid:
            continue
        rel = c["relationship"]
        items.append({"key": k, "name": c["name"], "mbid": mbid, "linkType": str(rel["link_type"]),
                      "typeTerm": rel["type_term"], "instrument": rel["instrument"],
                      "background": rel["kind"] == "background", "label": rel["label"],
                      "noteLine": _note_line(c)})
    if not items:
        return jsonify({"status": "error", "message": "None of the ticked credits can be sent yet."}), 400
    token = secrets.token_urlsafe(16)
    batches = current_app.extensions.setdefault("mbs_batches", {})
    batches[token] = {"mf_id": mf_id, "keys": [i["key"] for i in items], "results": {},
                      "finished": False, "closed": False, "started": time.time()}
    head = "Release relationships added from published credits for this release:"
    foot = ("Artists were matched by MusicBrainz ID, by a unique exact name match, "
            "or chosen by the submitter.\n\n"
            f"Proposed with MetaForge Studio. Methodology: {METAFORGE_HEURISTICS_URL}")
    report = request.host_url.rstrip("/") + f"/mb_report/{token}"
    script = _automation_js(items, head, foot, report)
    return jsonify({"status": "ok", "token": token, "count": len(items),
                    "url": f"https://musicbrainz.org/release/{info['mb_album_id']}/edit-relationships",
                    "title": f"MusicBrainz: {info['album_title']}", "script": script})


def _batch_status():
    data = request.get_json(silent=True) or {}
    b = current_app.extensions.setdefault("mbs_batches", {}).get(data.get("token"))
    if not b:
        return jsonify({"status": "error", "message": "Unknown batch."}), 404
    return jsonify({"status": "ok", "results": b["results"], "finished": b["finished"],
                    "closed": b["closed"], "count": len(b["keys"])})


def _batch_done():
    """The MusicBrainz window closed. Only the user knows whether they clicked
    "Enter edit", so they say: entered -> the added credits are "sent" (waiting
    for MusicBrainz; a later check marks them submitted). Not entered ->
    nothing changes."""
    data = request.get_json(silent=True) or {}
    b = current_app.extensions.setdefault("mbs_batches", {}).pop(data.get("token"), None)
    if not b:
        return jsonify({"status": "error", "message": "Unknown batch."}), 404
    marked = 0
    if data.get("entered"):
        state = _load_state()
        now = datetime.now().isoformat()
        for k, r in b["results"].items():
            if r.get("ok") and k in b["keys"]:
                entry = state.setdefault(k, {})
                if entry.get("status") not in ("submitted", "on_mb"):
                    entry.update(status="sent", timestamp=now, sent_at=now)
                    marked += 1
        _save_state(state)
    return jsonify({"status": "ok", "marked": marked})


def _automation_js(items, head, foot, report_url):
    """Runs inside the companion window on MusicBrainz's own
    /release/{id}/edit-relationships page. For each credit it drives the page's
    "Add relationship" dialog (same steps 1.x proved live one credit at a time),
    reports each result to MetaForge, writes ONE edit note listing only what
    was actually added, and STOPS. It never clicks "Enter edit".

    Selectors and waits are 1.x's live-tested ones. New and still to be
    confirmed live: several credits in one session, and the vocal attribute
    for backing vocals.
    """
    payload = json.dumps({"items": items, "head": head, "foot": foot, "report": report_url})
    return """
(function () {
  if (!/\\/edit-relationships\\/?$/.test(location.pathname)) return;   // e.g. after "Enter edit"
  if (window.__mfBatchRan) return;
  window.__mfBatchRan = true;
  var DATA = %s;

  function report(body) {
    return fetch(DATA.report, {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify(body)}).catch(function () {});
  }
  function visible(sel) {
    var els = document.querySelectorAll(sel);
    for (var i = 0; i < els.length; i++) if (els[i].offsetParent !== null) return els[i];
    return null;
  }
  function setValue(el, value) {
    var d = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value');
    if (d && d.set) d.set.call(el, value); else el.value = value;
    el.dispatchEvent(new Event('input', {bubbles: true}));
  }
  function directText(li) {
    var t = '';
    for (var i = 0; i < li.childNodes.length; i++) {
      var n = li.childNodes[i];
      if (n.nodeType === Node.TEXT_NODE) t += n.textContent; else break;
    }
    return t.trim().toLowerCase();
  }
  function waitFor(fn, ms) {
    return new Promise(function (resolve, reject) {
      var waited = 0, timer = setInterval(function () {
        var r; try { r = fn(); } catch (e) { r = null; }
        if (r) { clearInterval(timer); resolve(r); }
        else if ((waited += 150) >= ms) { clearInterval(timer); reject(new Error('timed out waiting for the page')); }
      }, 150);
    });
  }
  function pause(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function pickOption(text) {   // MusicBrainz's exact name; never a near miss
    return waitFor(function () {
      var opts = document.querySelectorAll('li[role="option"]');
      for (var i = 0; i < opts.length; i++) if (directText(opts[i]) === text) return opts[i];
      return null;
    }, 6000);
  }
  async function closeDialog() {
    var btns = document.querySelectorAll('.form .buttons-right button, .dialog button');
    for (var i = 0; i < btns.length; i++) {
      if (/cancel/i.test(btns[i].textContent) && btns[i].offsetParent !== null) { btns[i].click(); await pause(300); return; }
    }
    document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
    await pause(300);
  }

  async function addOne(item) {
    var addBtn = await waitFor(function () {
      var s = document.getElementById('release-rels');
      return s ? s.querySelector('button.add-relationship') : null;
    }, 20000);
    addBtn.click();
    var typeInput = await waitFor(function () { return visible('input.relationship-type'); }, 6000);
    typeInput.click(); typeInput.focus();
    setValue(typeInput, item.typeTerm);
    var typeOpt = await waitFor(function () {
      return document.querySelector('li[id$="-item-' + item.linkType + '"]');
    }, 6000);
    typeOpt.click();

    if (item.instrument) {
      var inst = await waitFor(function () {
        return visible('.attribute-container.instrument input[placeholder="instrument"]');
      }, 6000);
      inst.click(); inst.focus();
      setValue(inst, item.instrument);
      (await pickOption(item.instrument)).click();
    }
    if (item.background) {
      var voc = await waitFor(function () {
        return visible('.attribute-container.vocal input');
      }, 6000);
      voc.click(); voc.focus();
      setValue(voc, 'background vocals');
      (await pickOption('background vocals')).click();
    }

    await pause(400);   // the dialog re-renders after a type/attribute is chosen
    var target = await waitFor(function () { return visible('input.relationship-target'); }, 6000);
    target.click(); target.focus();
    setValue(target, item.mbid);
    if (target.value !== item.mbid) {
      target = await waitFor(function () { return visible('input.relationship-target'); }, 4000);
      target.click(); target.focus();
      setValue(target, item.mbid);
    }
    await waitFor(function () {
      if (target.value && target.value !== item.mbid) return true;
      var opt = document.querySelector('li[id*="' + item.mbid + '"]');
      if (opt) { opt.click(); return true; }
      return false;
    }, 8000);
    var done = await waitFor(function () {
      var b = document.querySelectorAll('.form .buttons-right button.positive');
      for (var i = 0; i < b.length; i++) if (!b[i].disabled) return b[i];
      return null;
    }, 6000);
    done.click();
    await pause(400);
  }

  async function run() {
    var added = [], failed = [];
    for (var i = 0; i < DATA.items.length; i++) {
      var item = DATA.items[i];
      try {
        await addOne(item);
        added.push(item);
        await report({key: item.key, ok: true});
      } catch (e) {
        failed.push(item);
        await report({key: item.key, ok: false, message: (e && e.message) || 'unknown error'});
        await closeDialog();
      }
    }
    if (added.length) {
      var note = DATA.head + '\\n' + added.map(function (x) { return x.noteLine; }).join('\\n') + '\\n\\n' + DATA.foot;
      await pause(400);
      var noteEl = await waitFor(function () { return document.getElementById('edit-note-text'); }, 4000).catch(function () { return null; });
      if (noteEl) {
        setValue(noteEl, note);
        if (noteEl.value !== note) {
          noteEl = document.getElementById('edit-note-text');
          if (noteEl) setValue(noteEl, note);
        }
      }
    }
    await report({finished: true, added: added.length, failed: failed.length});
    alert('MetaForge added ' + added.length + ' of ' + DATA.items.length + ' relationships' +
          (failed.length ? ' (' + failed.length + ' could not be added: MetaForge lists them).' : '.') +
          (added.length ? '\\n\\nCheck them and the edit note below, then click "Enter edit" yourself.' : ''));
  }
  run();
})();
""" % payload

# --- END OF FILE musicbrainz_submit.py ---
