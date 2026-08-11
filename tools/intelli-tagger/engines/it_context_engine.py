# MetaForge Engine: Intelli-Tagger Context (Phase 1)
# Role: Manages the Audit Pair (manifest.json & MetaForge.log)
# Build 1.1.1: hardened file IO + safe audit hook

import json
from pathlib import Path
from datetime import datetime


def initialize_audit_pair(root_path, seeds):
    manifest_path = root_path / "manifest.json"
    log_path = root_path / "MetaForge.log"

    manifest_data = {}

    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
        except Exception as e:
            yield f'<div class="it-log-entry it-val-red">⚠ Manifest Corrupt: {str(e)}</div>'
    else:
        yield '<div class="it-log-entry">🛰️ Initializing new forensic trail...</div>'

    manifest_data.update({
        "artist_seed": seeds.get('artist'),
        "album_seed": seeds.get('album'),
        "mb_artist_id": seeds.get('mb_ids', {}).get('artist'),
        "mb_album_id": seeds.get('mb_ids', {}).get('album'),
        "mb_release_group_id": seeds.get('mb_ids', {}).get('group'),
        "working_directory": str(root_path.resolve()),
        "last_tool_run": "intelli-tagger",
        "timestamp": datetime.now().isoformat()
    })

    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=4)
    except Exception as e:
        yield f'<div class="it-log-entry it-val-red">🔥 Cannot write manifest: {str(e)}</div>'

    if not log_path.exists():
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(
                    "METAFORGE FORENSIC LOG\n"
                    f"Initialized: {datetime.now()}\n"
                )
        except Exception:
            pass


# Core forensic identity fields Intelli-Tagger is specifically responsible
# for attaching per track (from MusicBrainz/AcoustID) -- distinct from the
# AI-inferred taxonomy fields (genre/mood/etc), which always land on SOME
# value (even a fallback "Unknown") rather than staying genuinely blank.
# These four are the ones that can legitimately fail to resolve (no
# AcoustID fingerprint match, no MB work relationship, etc), so they're
# what "Incomplete" means for this report. John's request, 2026-08-08.
_EXPECTED_TRACK_FIELDS = ["mb_track_id", "mb_recording_id", "mb_work_id", "acoustid"]


def _is_blank(value):
    return value is None or value == "" or value == "None"


def _health_check_summary_line(health_summary):
    if not health_summary:
        return "Not run"
    parts = []
    if health_summary.get("vanished"):
        parts.append(f"{health_summary['vanished']} file(s) went missing during the scan")
    if health_summary.get("queued"):
        parts.append(f"{health_summary['queued']} file(s) queued for the Repair tool")
    if health_summary.get("repaired"):
        parts.append(f"{health_summary['repaired']} file(s) structurally repaired")
    return "; ".join(parts) if parts else "No structural header repairs required"


def update_audit_trail(
    root_path,
    manifest_seeds,
    track_results,
    label,
    personnel,
    db_write,
    release_year,
    health_summary=None
):
    """
    Appends an "Intelli-Tagger" block to MetaForge.log -- same header/
    footer convention as Unpack & Convert's own block (context_engine.
    write_audit_log) and MusicBrainz ID's (musicbrainz_id._write_mb_id_
    audit_log). Replaced the old terse "AUDIT RUN" summary entirely
    (John's report, 2026-08-08: the log didn't actually lay out what this
    tool had done -- a bare track count told him nothing about which
    tracks, or whether any of them came out with real MB/AcoustID data
    attached vs silently falling back to nothing).
    """
    log_path = root_path / "MetaForge.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_content = [
        f"\n{'='*60}",
        f"METAFORGE AUDIT LOG | {timestamp}",
        "MetaForge Process: Intelli-Tagger",
        f"{'-'*60}",
        f"Health Check: {_health_check_summary_line(health_summary)}",
        "Tagging:",
    ]

    for f_path, track_data in track_results:
        missing = [field for field in _EXPECTED_TRACK_FIELDS if _is_blank(track_data.get(field))]
        if missing:
            detail = ", ".join(f'"{field}": ""' for field in missing)
            log_content.append(f'filename: "{f_path.name}" - Incomplete: {detail}')
        else:
            log_content.append(f'filename: "{f_path.name}"  - Complete')

    log_content.append(f"{'='*60}\n")

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(log_content))
    except Exception:
        pass