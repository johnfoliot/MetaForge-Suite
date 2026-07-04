# --- START OF FILE repair.py ---
# ======================================================================
# MetaForge Tool Logic: Audio Repair Workbench (V.Core - Build 1.0.3)
# Role: Batch bitstream remediation using FFmpeg RAW re-encoding.
# Build 1.0.3: Accessibility Hardening (WCAG 2.2 SC 1.1.1).
# ======================================================================
import json
import subprocess
import time
import os
import sqlite3
from pathlib import Path
from flask import Response, stream_with_context, jsonify
from common import config_handler

# --- [ DEPENDENCIES ] ---
try:
    from mutagen.id3 import ID3
except ImportError:
    pass

# --- [ CONFIGURATION ] ---
FFMPEG_EXE   = config_handler.FFMPEG_EXE
REPAIR_DIR   = config_handler.DATA_DIR / "repair"
QUEUE_LOG    = REPAIR_DIR / "remediation_queue.log"
REPAIRED_LOG = REPAIR_DIR / "repaired.log" 
DB_PATH      = config_handler.DB_PATH

def run_logic(action, tools_dir, env_path):
    """
    Universal Dispatcher: Routes UI triggers to repair engines.
    """
    REPAIR_DIR.mkdir(parents=True, exist_ok=True)

    if action == "get_queue":
        return get_remediation_queue()
    
    if action == "run_rebuild":
        return Response(stream_with_context(execute_batch_rebuild()), mimetype='text/plain')

    return jsonify({"status": "error", "message": f"Action {action} unrecognized."}), 400

# --- [ CORE ENGINES ] ---

def get_remediation_queue():
    """Reads the remediation_queue.log and returns a structured JSON list."""
    queue = []
    if QUEUE_LOG.exists():
        try:
            lines = QUEUE_LOG.read_text(encoding='utf-8').splitlines()
            for line in lines:
                if "|" in line:
                    path_str, error_msg = line.split("|", 1)
                    p = Path(path_str.strip())
                    queue.append({
                        "filename": p.name,
                        "full_path": str(p),
                        "error": error_msg.strip()
                    })
                else:
                    p = Path(line.strip())
                    queue.append({
                        "filename": p.name,
                        "full_path": str(p),
                        "error": "Bitstream Corruption"
                    })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"queue": queue})

def execute_batch_rebuild():
    """
    Iterates through the queue, performs FFmpeg RAW rebuild.
    Implements aria-hidden for all bitstream symbols.
    """
    if not QUEUE_LOG.exists() or QUEUE_LOG.stat().st_size == 0:
        yield '<span aria-hidden="true">⚠</span> Remediation queue is empty.'
        return

    queue_entries = QUEUE_LOG.read_text(encoding='utf-8').splitlines()
    remaining_queue = []
    total = len(queue_entries)

    yield f'\n<div class="status-api"><span aria-hidden="true">📂</span> Initializing Batch Surgery for {total} files...</div>\n'

    for index, line in enumerate(queue_entries, 1):
        path_str = line.split("|")[0].strip() if "|" in line else line.strip()
        input_path = Path(path_str)

        if not input_path.exists():
            yield f'<div class="status-error"><span aria-hidden="true">🔥</span> [{index}/{total}] MISSING: {input_path.name}</div>\n'
            continue

        yield f'<div class="status-message"><span aria-hidden="true">🛠️</span> [{index}/{total}] Rebuilding: {input_path.name}...</div>\n'
        
        success = perform_surgical_rebuild(input_path)
        final_path = input_path.with_suffix('.mp3')

        if success:
            yield f'<div class="status-message" style="margin-left:20px;"><span aria-hidden="true">✅</span> [{index}/{total}] REPAIRED: {final_path.name}</div>\n'
            update_database_remediation_status(final_path)
            try:
                with open(REPAIRED_LOG, 'a', encoding='utf-8') as rl:
                    rl.write(f"{final_path}\n")
            except Exception as e:
                yield f'<div class="status-warn"><span aria-hidden="true">⚠</span> Error writing to hand-off log: {str(e)}</div>\n'
        else:
            yield f'<div class="status-error"><span aria-hidden="true">🔥</span> [{index}/{total}] FAILED: {input_path.name}</div>\n'
            remaining_queue.append(line)

        time.sleep(0.5)

    QUEUE_LOG.write_text("\n".join(remaining_queue), encoding='utf-8')
    yield f'\n<div class="status-ok"><span aria-hidden="true">✅</span> Batch Remediation Sequence Concluded.</div>\n'
    yield f'<div class="status-api"><span aria-hidden="true">🛰️</span> {total - len(remaining_queue)} paths staged in \\data\\repair\\repaired.log for Tagger sync.</div>'

def perform_surgical_rebuild(input_path):
    """
    Deconstructs and rebuilds the bitstream via RAW buffer.
    Enforces ID3v2.3 and UTF-16 (Encoding 1) for wide compatibility.
    """
    final_path = input_path.with_suffix('.mp3')
    temp_path = input_path.with_suffix('.rebuild.tmp.mp3')

    try:
        try:
            original_tags = ID3(str(input_path))
        except:
            original_tags = None

        cmd = [
            str(FFMPEG_EXE), "-y", "-i", str(input_path),
            "-map", "0:a", "-c:a", "libmp3lame", "-q:a", "0", str(temp_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and temp_path.exists():
            if original_tags:
                new_audio = ID3(str(temp_path))
                for frame in original_tags.values():
                    if hasattr(frame, 'encoding'):
                        frame.encoding = 1
                    new_audio.add(frame)
                # save() alone doesn't downgrade v2.4-native frames (e.g.
                # TDRC -> TYER) even when v2_version=3 is requested.
                new_audio.update_to_v23()
                new_audio.save(v2_version=3)

            os.remove(input_path)
            os.rename(temp_path, final_path)
            return True
        else:
            if temp_path.exists(): os.remove(temp_path)
            return False

    except Exception:
        if temp_path.exists(): os.remove(temp_path)
        return False

def update_database_remediation_status(file_path):
    """Updates the tracks table to mark the file as structurally sound."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        clean_path = str(file_path).replace('\\', '/')
        cursor.execute(
            "UPDATE tracks SET is_remediated = 1, last_updated = ? WHERE file_path = ?",
            (time.strftime('%Y-%m-%d %H:%M:%S'), clean_path)
        )
        conn.commit()
        conn.close()
    except:
        pass

# --- AUDIO REPAIR ENGINE END ---
# --- END OF FILE repair.py ---