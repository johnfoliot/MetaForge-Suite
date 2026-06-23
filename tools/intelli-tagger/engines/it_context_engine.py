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


def update_audit_trail(
    root_path,
    manifest_seeds,
    track_results,
    label,
    personnel,
    db_write,
    release_year
):
    log_path = root_path / "MetaForge.log"

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"AUDIT RUN: {datetime.now().isoformat()}\n")
            f.write(f"Artist: {manifest_seeds.get('artist')}\n")
            f.write(f"Album: {manifest_seeds.get('album')}\n")
            f.write(f"Tracks processed: {len(track_results)}\n")
            f.write(f"Label: {label}\n")
            f.write(f"Release Year: {release_year}\n")
            f.write(f"Personnel: {personnel}\n")
            f.write("=" * 60 + "\n")

    except Exception:
        pass