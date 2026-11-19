# --- START OF FILE identity_ops.py ---
# ======================================================================
# MetaForge Studio: Database Tools - identity operations
# Physical Location: \tools\database_tools\engines\identity_ops.py
# v2 (2026-11-15). The one place that renames, merges, re-keys and purges
# artists and albums. John's decisions 2026-11-15: edits write the file
# tags too, an artist rename carries through to that artist's albums,
# tracks and tags, and two artists can be merged.
#
# Why this is more than an UPDATE: identities are hashes of names
# (mf_artist_id = sha256(normalized name), mf_id = sha256(artist|title),
# edge_normalizer.py), and the Intelli-Tagger re-derives them from each
# album folder's manifest.json (artist_seed / album_seed) when it re-runs.
# So a new name means a new ID, which has to be carried through:
#   database   library_artist, library_master, tracks, edges
#   files      TPE1 / TALB / TYER / TPUB tags, manifest.json seeds
#   logs       data/musicbrainz: the two correction-candidate logs, the
#              remediation log and MB Submit's personnel review state
#              (keyed "scope|name|relation|role", scope = recording or mf_id)
# When the new ID already exists, the two records are merged: blanks on the
# surviving record are filled from the other, never overwritten.
#
# Every operation runs twice: preview (inside a transaction that is rolled
# back, so the counts are exact) and apply (backup first, then the same
# transaction committed, then tags, manifests and logs). A failed tag or
# manifest write is reported, never fatal (never-abort philosophy).
# ======================================================================
import json
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from common import config_handler, tag_engine
from tools.personnel.edge_normalizer import (
    hash_album_identity, hash_artist_identity, normalize_identity_text,
)

KEEP_BACKUPS = 5
ARTIST_FILL = ("country", "biography", "photo_path", "bio_updated_at", "mb_artist_id")
ALBUM_FILL = ("mb_album_id", "original_year", "label", "date_audit_status")
FIELD_NAMES = {"mb_album_id": "MusicBrainz album ID", "mb_artist_id": "MusicBrainz artist ID",
               "original_year": "year", "date_audit_status": "date-check status",
               "bio_updated_at": "biography date", "photo_path": "photo"}
LOGS = ("personnel_correction_candidates.jsonl", "original_year_correction_candidates.jsonl",
        "remediation_log.jsonl", "personnel_correction_review_state.json")


def _log_dir():
    return config_handler.DATA_DIR / "musicbrainz"


def _backup_root():
    return config_handler.APPDATA_MF / "backups" / "database_tools"


def _norm(s):
    return normalize_identity_text(s or "")


def _connect():
    db = sqlite3.connect(str(config_handler.DB_PATH), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


class Change:
    """Everything one operation does, collected while the SQL runs."""

    def __init__(self):
        self.tags = {}            # file_path -> {tag_engine key: value}
        self.manifests = {}       # album folder -> {seed key: value}
        self.album_ids = {}       # old mf_id -> new mf_id
        self.artist_ids = {}      # old mf_artist_id -> new
        self.names = {}           # normalized old artist name -> new name
        self.album_text = {}      # new mf_id -> (artist, title), for log display fields
        self.touched_albums = set()
        self.maybe_orphans = set()
        self.notes = []           # plain-language lines for the preview
        self.counts = {"albums": 0, "albums_merged": 0, "tracks": 0, "credits": 0,
                       "credits_merged": 0, "artists_merged": 0, "artists_removed": 0,
                       "albums_removed": 0, "tracks_removed": 0, "credits_removed": 0, "artist_deleted": 0}

    def tag(self, file_path, **values):
        self.tags.setdefault(file_path, {}).update(values)

    def seed(self, file_path, **values):
        self.manifests.setdefault(str(Path(file_path).parent), {}).update(values)


# =========================================================
# SQL STEPS (run inside one transaction)
# =========================================================

def _fill_blanks(db, table, key_col, keep_id, other, cols, label, ch):
    keep = db.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (keep_id,)).fetchone()
    for c in cols:
        mine, theirs = keep[c], other[c]
        if (mine in (None, "") or str(mine).strip() == "") and theirs not in (None, ""):
            db.execute(f"UPDATE {table} SET {c}=? WHERE {key_col}=?", (theirs, keep_id))
        elif theirs not in (None, "") and mine not in (None, "") and str(mine) != str(theirs):
            ch.notes.append(f"Both {label} have a {FIELD_NAMES.get(c, c)}; the one already on the kept record stays.")


def _move_album(db, ch, mf_id, artist, artist_id, title, retag_artist):
    """Gives album mf_id a new artist and/or title; re-keys it to
    hash(artist, title), merging into that album if it already exists."""
    row = db.execute("SELECT * FROM library_master WHERE mf_id=?", (mf_id,)).fetchone()
    if not row:
        return mf_id
    new_id = hash_album_identity(artist, title)
    tracks = db.execute("SELECT file_path, mf_artist_id FROM tracks WHERE mf_id=?", (mf_id,)).fetchall()
    for t in tracks:
        if title != row["album_title"]:
            ch.tag(t["file_path"], album=title)
        if retag_artist and not row["is_compilation"]:
            ch.tag(t["file_path"], artist=artist)
            if t["mf_artist_id"] != artist_id:
                ch.maybe_orphans.add(t["mf_artist_id"])
        ch.seed(t["file_path"], artist_seed=artist, album_seed=title)
    if retag_artist and not row["is_compilation"]:
        db.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_id=?", (artist_id, mf_id))
    if row["mf_artist_id"] and row["mf_artist_id"] != artist_id:
        ch.maybe_orphans.add(row["mf_artist_id"])

    if new_id != mf_id:
        if db.execute("SELECT 1 FROM library_master WHERE mf_id=?", (new_id,)).fetchone():
            _fill_blanks(db, "library_master", "mf_id", new_id, row, ALBUM_FILL, "albums", ch)
            if row["is_compilation"]:
                db.execute("UPDATE library_master SET is_compilation=1 WHERE mf_id=?", (new_id,))
            db.execute("DELETE FROM library_master WHERE mf_id=?", (mf_id,))
            ch.counts["albums_merged"] += 1
            ch.notes.append(f"“{title}” by {artist} already exists, so the two albums are merged into one.")
        else:
            db.execute("UPDATE library_master SET mf_id=? WHERE mf_id=?", (new_id, mf_id))
        db.execute("UPDATE tracks SET mf_id=? WHERE mf_id=?", (new_id, mf_id))
        db.execute("UPDATE edges SET source_id=? WHERE source_type='album' AND source_id=?", (new_id, mf_id))
        ch.album_ids[mf_id] = new_id
    db.execute("UPDATE library_master SET artist_name=?, mf_artist_id=?, album_title=?, "
               "last_updated=CURRENT_TIMESTAMP WHERE mf_id=?", (artist, artist_id, title, new_id))
    ch.album_text[new_id] = (artist, title)
    ch.touched_albums.add(new_id)
    ch.counts["albums"] += 1
    return new_id


def _move_artist(db, ch, src_id, name):
    """Renames artist src_id to name, re-keying to hash(name) and merging
    into that artist if it already exists. Carries the change through to
    the artist's albums (as album artist), tracks (as performer) and
    credits."""
    row = db.execute("SELECT * FROM library_artist WHERE mf_artist_id=?", (src_id,)).fetchone()
    if not row:
        raise ValueError("That artist is no longer in the database.")
    old_name = row["artist_name"] or ""
    new_id = hash_artist_identity(name)
    if new_id == src_id and old_name == name:
        return src_id               # the artist being kept in a merge: nothing to change
    if new_id == src_id:
        db.execute("UPDATE library_artist SET artist_name=?, last_updated=CURRENT_TIMESTAMP WHERE mf_artist_id=?",
                   (name, src_id))
    elif db.execute("SELECT 1 FROM library_artist WHERE mf_artist_id=?", (new_id,)).fetchone():
        _fill_blanks(db, "library_artist", "mf_artist_id", new_id, row, ARTIST_FILL, "artists", ch)
        db.execute("DELETE FROM library_artist WHERE mf_artist_id=?", (src_id,))
        ch.notes.append(f"{old_name} is merged into {name}: one artist from now on.")
        db.execute("UPDATE library_artist SET artist_name=?, last_updated=CURRENT_TIMESTAMP WHERE mf_artist_id=?",
                   (name, new_id))
        ch.counts["artists_merged"] += 1
    else:
        db.execute("UPDATE library_artist SET mf_artist_id=?, artist_name=?, last_updated=CURRENT_TIMESTAMP "
                   "WHERE mf_artist_id=?", (new_id, name, src_id))
    if new_id != src_id:
        ch.artist_ids[src_id] = new_id
    if old_name != name:
        ch.names[_norm(old_name)] = name

    # Tracks this artist performs (their own albums and compilations).
    for t in db.execute("SELECT file_path FROM tracks WHERE mf_artist_id=?", (src_id,)).fetchall():
        ch.tag(t["file_path"], artist=name)
        ch.counts["tracks"] += 1
    db.execute("UPDATE tracks SET mf_artist_id=? WHERE mf_artist_id=?", (new_id, src_id))

    # Credits.
    n = db.execute("SELECT count(*) FROM edges WHERE target_type='artist' AND target_id=?", (src_id,)).fetchone()[0]
    ch.counts["credits"] += n
    for r in db.execute("SELECT DISTINCT source_id FROM edges WHERE target_id=?", (src_id,)).fetchall():
        ch.touched_albums.add(r["source_id"])
    db.execute("UPDATE edges SET target_id=? WHERE target_type='artist' AND target_id=?", (new_id, src_id))
    db.execute("UPDATE edges SET source_id=? WHERE source_type='artist' AND source_id=?", (new_id, src_id))

    # Albums where this artist is the album artist: by ID, or by name where
    # the album's artist ID is stale (7 such albums found 2026-11-15).
    old_n = _norm(old_name)
    albums = [r for r in db.execute("SELECT mf_id, mf_artist_id, artist_name, album_title FROM library_master").fetchall()
              if r["mf_artist_id"] == src_id or (old_n and _norm(r["artist_name"]) == old_n)]
    for a in albums:
        _move_album(db, ch, a["mf_id"], name, new_id, a["album_title"], retag_artist=False)
    return new_id


def _dedupe_credits(db, ch):
    """A merge can leave the same credit twice on one album (same person,
    role and track scope: edge_store.find_matching_edge's key). Keeps the
    highest-confidence copy (oldest on a tie)."""
    for sid in ch.touched_albums:
        seen = {}
        rows = db.execute("SELECT id, source_type, target_id, role, evidence_scope, evidence_detail, confidence "
                          "FROM edges WHERE source_id=? ORDER BY COALESCE(confidence, 0) DESC, id", (sid,)).fetchall()
        for r in rows:
            k = (r["source_type"], r["target_id"], (r["role"] or "").strip().lower(), r["evidence_scope"], r["evidence_detail"])
            if k in seen:
                db.execute("DELETE FROM edges WHERE id=?", (r["id"],))
                ch.counts["credits_merged"] += 1
            else:
                seen[k] = r["id"]


def _artist_in_use(db, aid):
    return (db.execute("SELECT 1 FROM edges WHERE target_id=? LIMIT 1", (aid,)).fetchone()
            or db.execute("SELECT 1 FROM tracks WHERE mf_artist_id=? LIMIT 1", (aid,)).fetchone()
            or db.execute("SELECT 1 FROM library_master WHERE mf_artist_id=? LIMIT 1", (aid,)).fetchone())


def _drop_orphans(db, ch):
    """An artist left with no albums, tracks or credits is removed only if
    their record holds nothing worth keeping (no bio, photo, country or
    MusicBrainz ID); otherwise it stays and the preview says so."""
    for aid in ch.maybe_orphans - set(ch.artist_ids):
        if not aid or _artist_in_use(db, aid):
            continue
        row = db.execute("SELECT * FROM library_artist WHERE mf_artist_id=?", (aid,)).fetchone()
        if not row:
            continue
        # "None" and "Unknown" are the Intelli-Tagger's placeholders for
        # "nothing found", not something worth keeping (2026-11-19).
        if any((row[c] or "").strip() not in ("", "None", "Unknown")
               for c in ("biography", "photo_path", "country", "mb_artist_id")):
            ch.notes.append(f"{row['artist_name']} no longer has any albums, tracks or credits. "
                            "Their record is kept because it has a biography, photo, country or MusicBrainz ID.")
        else:
            db.execute("DELETE FROM library_artist WHERE mf_artist_id=?", (aid,))
            ch.counts["artists_removed"] += 1


# =========================================================
# OPERATIONS
# =========================================================

def _artist_merge(db, ch, ids, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("The artist name can't be blank.")
    for aid in ids:
        _move_artist(db, ch, aid, name)
    _dedupe_credits(db, ch)


def _album_edit(db, ch, mf_id, artist, title):
    artist, title = (artist or "").strip(), (title or "").strip()
    if not artist or not title:
        raise ValueError("The album's artist and title can't be blank.")
    aid = hash_artist_identity(artist)
    db.execute("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) "
               "VALUES (?, ?, CURRENT_TIMESTAMP)", (aid, artist))
    _move_album(db, ch, mf_id, artist, aid, title, retag_artist=True)
    _dedupe_credits(db, ch)
    _drop_orphans(db, ch)


def _purge(db, ch, kind, key):
    if kind == "artist":
        row = db.execute("SELECT artist_name FROM library_artist WHERE mf_artist_id=?", (key,)).fetchone()
        if not row:
            raise ValueError("That artist is no longer in the database.")
        elsewhere = db.execute("SELECT count(*) FROM tracks t JOIN library_master m ON m.mf_id=t.mf_id "
                               "WHERE t.mf_artist_id=? AND m.mf_artist_id IS NOT ?", (key, key)).fetchone()[0]
        if elsewhere:
            raise ValueError(f"{row['artist_name']} performs {elsewhere} track{'s' if elsewhere != 1 else ''} on "
                             "other artists' albums, so they can't be removed. Merge them into the right artist instead.")
        for a in db.execute("SELECT mf_id FROM library_master WHERE mf_artist_id=?", (key,)).fetchall():
            _purge(db, ch, "album", a["mf_id"])
        ch.counts["credits_removed"] += db.execute("DELETE FROM edges WHERE target_id=? OR source_id=?", (key, key)).rowcount
        db.execute("DELETE FROM library_artist WHERE mf_artist_id=?", (key,))
        ch.counts["artist_deleted"] += 1
        ch.maybe_orphans.discard(key)
    elif kind == "album":
        if not db.execute("SELECT 1 FROM library_master WHERE mf_id=?", (key,)).fetchone():
            raise ValueError("That album is no longer in the database.")
        for r in db.execute("SELECT DISTINCT target_id FROM edges WHERE source_id=?", (key,)).fetchall():
            ch.maybe_orphans.add(r["target_id"])
        for r in db.execute("SELECT DISTINCT mf_artist_id FROM tracks WHERE mf_id=?", (key,)).fetchall():
            ch.maybe_orphans.add(r["mf_artist_id"])
        ch.counts["credits_removed"] += db.execute("DELETE FROM edges WHERE source_type='album' AND source_id=?", (key,)).rowcount
        ch.counts["tracks_removed"] += db.execute("DELETE FROM tracks WHERE mf_id=?", (key,)).rowcount
        db.execute("DELETE FROM library_master WHERE mf_id=?", (key,))
        ch.counts["albums_removed"] += 1
    elif kind == "track":
        row = db.execute("SELECT mf_artist_id FROM tracks WHERE file_path=?", (key,)).fetchone()
        if not row:
            raise ValueError("That track is no longer in the database.")
        ch.maybe_orphans.add(row["mf_artist_id"])
        ch.counts["tracks_removed"] += db.execute("DELETE FROM tracks WHERE file_path=?", (key,)).rowcount
    elif kind == "credit":
        row = db.execute("SELECT target_id FROM edges WHERE id=?", (key,)).fetchone()
        if not row:
            raise ValueError("That credit is no longer in the database.")
        ch.maybe_orphans.add(row["target_id"])
        ch.counts["credits_removed"] += db.execute("DELETE FROM edges WHERE id=?", (key,)).rowcount
    else:
        raise ValueError("Unknown kind of record.")


def _purge_op(db, ch, kind, key):
    _purge(db, ch, kind, key)
    _drop_orphans(db, ch)


OPS = {"artist_merge": _artist_merge, "album_edit": _album_edit, "purge": _purge_op}


def run(op, apply=False, label="", **args):
    """Preview (apply=False) or apply one operation. Returns a dict:
    counts, notes, files (tags to rewrite), and on apply: backup folder
    and any file/log problems."""
    ch = Change()
    db = _connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            OPS[op](db, ch, **args)
        except Exception:
            db.execute("ROLLBACK")
            raise
        if not apply:
            db.execute("ROLLBACK")
            return _result(ch)
        db.execute("ROLLBACK")      # back up the untouched database first...
        backup = _backup(label or op, ch)
        ch2 = Change()              # ...then redo the work for real
        db.execute("BEGIN IMMEDIATE")
        try:
            OPS[op](db, ch2, **args)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        ch = ch2
    finally:
        db.close()
    res = _result(ch)
    res["backup"] = str(backup)
    res["problems"] = _write_files(ch) + _repoint_logs(ch)
    return res


def carry_over_retag(artist, title, file_paths, mb_album_id=None):
    """Called by the Intelli-Tagger just before it saves an album
    (John, 2026-11-18). An album's ID is hash(artist, title), so tagging
    the same files again under a corrected name used to be treated as a
    brand-new album: the save failed on every track (file_path is the
    tracks key) and the saved credits stayed behind on the old record.

    For each OTHER album record that owns any of these files:
      - every one of its tracks is among these files: it is the same album
        under its old name. Its record, credits and MusicBrainz logs move to
        the new name (merging if that record exists), as a Database Tools
        rename does. No tags are written: the Intelli-Tagger writes them.
      - it has other tracks too: only these files' track rows are released,
        so the save can succeed. Its credits stay where they are, because
        which album they describe is not this code's call.
    Files RENAMED since the first run share no path with the old record, so
    an old record also counts as this album when all three hold (rule agreed
    with John, 2026-11-19): none of its tracks' files exist any more, it has
    the same MusicBrainz release ID as this run, and the same number of
    tracks. Anything short of that is left alone.
    Returns plain-language lines for the Activity log. Raises on failure;
    the caller reports it and carries on."""
    artist, title = (artist or "").strip(), (title or "").strip()
    paths = {str(p).replace("\\", "/").lower() for p in file_paths}
    if not artist or not title or not paths:
        return []
    new_id = hash_album_identity(artist, title)
    artist_id = hash_artist_identity(artist)

    def owners(db):
        """{other album id: (its tracks among these files, its other tracks)}"""
        out = {}
        for r in db.execute("SELECT file_path, mf_id FROM tracks WHERE mf_id IS NOT ?", (new_id,)).fetchall():
            if (r["file_path"] or "").replace("\\", "/").lower() in paths:
                out.setdefault(r["mf_id"], [[], 0])[0].append(r["file_path"])
        for old in out:
            out[old][1] = db.execute("SELECT count(*) FROM tracks WHERE mf_id=?", (old,)).fetchone()[0] - len(out[old][0])
        release = (mb_album_id or "").strip()
        if release not in ("", "None", "Unknown"):
            for a in db.execute("SELECT mf_id FROM library_master WHERE mb_album_id=? AND mf_id IS NOT ?",
                                (release, new_id)).fetchall():
                if a["mf_id"] in out:
                    continue
                theirs = [r["file_path"] for r in db.execute("SELECT file_path FROM tracks WHERE mf_id=?", (a["mf_id"],)).fetchall()]
                if len(theirs) == len(paths) and not any(os.path.exists(fp) for fp in theirs):
                    out[a["mf_id"]] = [theirs, 0]
        return out

    def work(db, ch):
        lines = []
        for old, (mine, others) in owners(db).items():
            row = db.execute("SELECT artist_name, album_title FROM library_master WHERE mf_id=?", (old,)).fetchone()
            was = f"“{row['album_title']}” by {row['artist_name']}" if row else "an album record that no longer exists"
            if others:
                for fp in mine:
                    db.execute("DELETE FROM tracks WHERE file_path=?", (fp,))
                lines.append(f"{_n(len(mine), 'file')} here {'was' if len(mine) == 1 else 'were'} filed under {was}, "
                             f"which has {_n(others, 'other track')}. Its credits were left where they are. "
                             "If it is the same album, rename it in Database Tools.")
                continue
            credits = db.execute("SELECT count(*) FROM edges WHERE source_type='album' AND source_id=?", (old,)).fetchone()[0]
            if row:
                db.execute("INSERT OR IGNORE INTO library_artist (mf_artist_id, artist_name, last_updated) "
                           "VALUES (?, ?, CURRENT_TIMESTAMP)", (artist_id, artist))
                _move_album(db, ch, old, artist, artist_id, title, retag_artist=False)
            else:               # tracks and credits whose album record is already gone
                db.execute("UPDATE tracks SET mf_id=? WHERE mf_id=?", (new_id, old))
                db.execute("UPDATE edges SET source_id=? WHERE source_type='album' AND source_id=?", (new_id, old))
                ch.album_ids[old] = new_id
                ch.touched_albums.add(new_id)
            # These files' track rows go now (the Intelli-Tagger deletes and
            # rewrites them a moment later anyway), so an artist only they
            # pointed at, such as a misspelt name, is seen as unused below.
            for fp in mine:
                t = db.execute("SELECT mf_artist_id FROM tracks WHERE file_path=?", (fp,)).fetchone()
                if t:
                    ch.maybe_orphans.add(t["mf_artist_id"])
                db.execute("DELETE FROM tracks WHERE file_path=?", (fp,))
            lines.append(f"This album was in the database as {was}. "
                         + (f"Its record and {_n(credits, 'credit')} now belong" if credits else "Its record now belongs")
                         + " to the name used here.")
        _dedupe_credits(db, ch)
        _drop_orphans(db, ch)
        return lines

    db = _connect()
    try:
        if not owners(db):
            return []
        db.execute("BEGIN IMMEDIATE")
        try:
            ch = Change()
            lines = work(db, ch)
            if ch.album_ids:                    # a record moves: back up the untouched
                db.execute("ROLLBACK")          # database first, as run() does...
                _backup(f"Intelli-Tagger re-tag {title}", ch)
                db.execute("BEGIN IMMEDIATE")   # ...then the same work again, for real
                ch = Change()
                lines = work(db, ch)
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:       # not while the backup is being made
                db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    return lines + list(dict.fromkeys(ch.notes)) + _repoint_logs(ch)


def _result(ch):
    return {"counts": ch.counts, "notes": list(dict.fromkeys(ch.notes)), "files": len(ch.tags),
            "album_ids": ch.album_ids, "artist_ids": ch.artist_ids, "summary": describe(ch.counts, len(ch.tags))}


def _n(k, one, many=None):
    return f"{k:,} {one if k == 1 else (many or one + 's')}"


def describe(c, files):
    """Plain-language lines for the confirmation dialog (COGA: one fact
    per line, counts first)."""
    lines = []
    if c["artists_merged"]:
        lines.append(f"{c['artists_merged'] + 1} artist records become one")
    if c["albums"]:
        lines.append(f"{_n(c['albums'], 'album')} updated")
    if c["albums_merged"]:
        lines.append(f"{_n(c['albums_merged'], 'album')} merged with an album that already exists")
    if c["tracks"]:
        lines.append(f"{_n(c['tracks'], 'track')} moved to the new name")
    if c["credits"]:
        lines.append(f"{_n(c['credits'], 'credit')} moved to the new name")
    if c["credits_merged"]:
        lines.append(f"{_n(c['credits_merged'], 'duplicate credit')} removed")
    if c["artist_deleted"]:
        lines.append("The artist's own record deleted")
    if c["albums_removed"]:
        lines.append(f"{_n(c['albums_removed'], 'album')} deleted")
    if c["tracks_removed"]:
        lines.append(f"{_n(c['tracks_removed'], 'track')} deleted from the database")
    if c["credits_removed"]:
        lines.append(f"{_n(c['credits_removed'], 'credit')} deleted")
    if c["artists_removed"]:
        lines.append(f"{_n(c['artists_removed'], 'other artist')} left with nothing deleted")
    if files:
        lines.append(f"Tags rewritten in {_n(files, 'music file')}")
    return lines


# =========================================================
# BACKUP, FILES AND LOGS (after the transaction)
# =========================================================

def _backup(label, ch):
    """Copies the database (SQLite's online backup, safe while open) and
    any log this change will rewrite into a dated folder; keeps the last
    KEEP_BACKUPS folders."""
    root = _backup_root()
    root.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in label)[:60].strip()
    folder = root / f"{datetime.now():%Y-%m-%d %H%M%S} {safe}"
    folder.mkdir()
    src = sqlite3.connect(str(config_handler.DB_PATH))
    dst = sqlite3.connect(str(folder / "metaforge.db"))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    if ch.album_ids or ch.names or ch.artist_ids:
        for name in LOGS:
            p = _log_dir() / name
            if p.exists():
                shutil.copy2(p, folder / name)
    for old in sorted((d for d in root.iterdir() if d.is_dir()), key=lambda d: d.name)[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)
    return folder


def _write_files(ch):
    problems = []
    for fp, values in ch.tags.items():
        if not Path(fp).exists():
            problems.append(f"Tags not written, file not found: {fp}")
            continue
        ok, msg = tag_engine.update_tags(fp, values)
        if not ok:
            problems.append(f"Tags not written to {fp}: {msg}")
    for folder, seeds in ch.manifests.items():
        mp = Path(folder) / "manifest.json"
        if not mp.exists():
            continue
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
            if all(data.get(k) == v for k, v in seeds.items()):
                continue
            data.update(seeds)
            tmp = mp.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, mp)
        except Exception as ex:
            problems.append(f"manifest.json not updated in {folder}: {ex}")
    return problems


def _rekey(ch, key):
    parts = key.split("|", 3)
    if len(parts) != 4:
        return key
    scope, name, rel, role = parts
    scope = ch.album_ids.get(scope, scope)
    name = ch.names.get(_norm(name), name)
    return "|".join((scope, name, rel, role))


def _fix_entry(ch, e):
    changed = False
    mf = e.get("mf_id")
    if mf in ch.album_ids:
        e["mf_id"] = mf = ch.album_ids[mf]
        changed = True
    if mf in ch.album_text and (e.get("artist"), e.get("album")) != ch.album_text[mf] and "album" in e:
        e["artist"], e["album"] = ch.album_text[mf]
        changed = True
    if e.get("target_id") in ch.artist_ids:
        e["target_id"] = ch.artist_ids[e["target_id"]]
        changed = True
    if "name" in e and _norm(e["name"]) in ch.names and e["name"] != ch.names[_norm(e["name"])]:
        e["name"] = ch.names[_norm(e["name"])]
        changed = True
    if "key" in e:
        k = _rekey(ch, e["key"])
        if k != e["key"]:
            e["key"] = k
            changed = True
    return changed


def _repoint_logs(ch):
    if not (ch.album_ids or ch.names or ch.artist_ids):
        return []
    problems = []
    for name in LOGS[:3]:
        p = _log_dir() / name
        if not p.exists():
            continue
        try:
            out, n = [], 0
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.rstrip("\n")
                    try:
                        e = json.loads(line)
                    except Exception:
                        out.append(line)
                        continue
                    if _fix_entry(ch, e):
                        n += 1
                        out.append(json.dumps(e))
                    else:
                        out.append(line)
            if n:
                tmp = p.with_suffix(p.suffix + ".tmp")
                tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
                os.replace(tmp, p)
        except Exception as ex:
            problems.append(f"{name} not updated: {ex}")
    p = _log_dir() / LOGS[3]
    if p.exists():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
            new, changed = {}, False
            for k, v in state.items():
                k2 = _rekey(ch, k)
                changed |= k2 != k
                if k2 in new:   # two entries now mean the same thing: keep a submitted one
                    if (v.get("status") == "submitted") and new[k2].get("status") != "submitted":
                        new[k2] = v
                else:
                    new[k2] = v
            if changed:
                tmp = p.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(new, indent=2), encoding="utf-8")
                os.replace(tmp, p)
        except Exception as ex:
            problems.append(f"{LOGS[3]} not updated: {ex}")
    return problems

# --- END OF FILE identity_ops.py ---
