# --- START OF FILE music-sharing.py ---
# ======================================================================
# MetaForge Tool Logic: Music Sharing Studio (V.Core - Build 1.0.2)
# Role: Synthesizes MP3 and Folder Art into branded social media videos.
# Build 1.0.2: Accessibility Hardening (WCAG 2.2 SC 1.1.1).
# ======================================================================
import os
import subprocess
import time
import base64
import re
from pathlib import Path
from flask import Response, stream_with_context, jsonify, request
from common import config_handler

# --- [ CONFIGURATION ] ---
FFMPEG_EXE   = config_handler.FFMPEG_EXE
TOOL_DIR     = Path(__file__).parent.resolve()
WATERMARK    = TOOL_DIR / "branding.png"
OUTPUT_DIR   = Path.home() / "Videos" / "MetaForge Studio"

def run_logic(action, tools_dir, env_path):
    """
    Universal Dispatcher: Routes Studio requests from music-sharing.js.
    """
    if action == "get_preview":
        return _handle_preview_sync()

    if action == "render":
        return Response(stream_with_context(_execute_studio_render()), mimetype='text/plain')

    if action == "open_folder":
        return _handle_folder_discovery()

    return jsonify({"status": "error", "message": f"Action {action} unrecognized."}), 400

# --- [ STUDIO ACTIONS ] ---

def _handle_preview_sync():
    """
    Locates folder.jpg in the track's directory and returns a Base64 URI.
    """
    try:
        data = request.json
        mp3_path = Path(data.get('path'))
        art_path = mp3_path.parent / "folder.jpg"
        
        if art_path.exists():
            with open(art_path, "rb") as img_file:
                b64_data = base64.b64encode(img_file.read()).decode('utf-8')
                return jsonify({
                    "art_url": f"data:image/jpeg;base64,{b64_data}",
                    "filename": mp3_path.name
                })
    except Exception as e:
        print(f"DEBUG: Preview failure: {str(e)}")
        
    return jsonify({"art_url": None})

def _execute_studio_render():
    """
    Studio Synthesis: Wraps audio in an H.264 container with static imagery.
    Yields real-time heartbeats sanitized for Assistive Technology.
    """
    try:
        data = request.json
        mp3_path = Path(data.get('path'))
        
        if not mp3_path.exists():
            yield '<span aria-hidden="true">🔥</span> ERROR: Target file missing from disk.\n'
            return

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        clean_stem = re.sub(r'[^\w\s-]', '', mp3_path.stem).strip()
        target_output = OUTPUT_DIR / f"{clean_stem}.mp4"
        
        art_path = mp3_path.parent / "folder.jpg"
        has_art = art_path.exists()
        has_brand = WATERMARK.exists()

        yield f'<div class="status-api"><span aria-hidden="true">⚙️</span> Initializing Studio Session for: {mp3_path.name}</div>\n'
        yield f'<div class="status-message"><span aria-hidden="true">⚙️</span> Render Target: {target_output}</div>\n'

        cmd = [str(FFMPEG_EXE), "-y"]
        
        if has_art:
            cmd += ["-loop", "1", "-i", str(art_path)]
        else:
            cmd += ["-f", "lavfi", "-i", "color=c=black:s=1080x1080"]

        cmd += ["-i", str(mp3_path)]

        if has_brand:
            cmd += ["-i", str(WATERMARK)]
            filter_str = "[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[bg];[bg][2:v]overlay=0:0[out]"
        else:
            filter_str = "[0:v]scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080[out]"

        cmd += [
            "-filter_complex", filter_str,
            "-map", "[out]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p",
            str(target_output)
        ]

        yield f'<div class="status-api"><span aria-hidden="true">⚙️</span> Synthesis in progress (libx264/aac)...</div>\n'
        
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in process.stdout:
            if "frame=" in line and "fps=" in line:
                # Sanitized progress signal
                yield f'<span aria-hidden="true">🛰️</span> Processing: {line.strip()}\n'

        process.wait()
        
        if process.returncode == 0:
            yield f'\n<div class="status-ok"><span aria-hidden="true">✅</span> SUCCESS: Studio Render Concluded.</div>\n'
            yield f'<div class="status-message"><span aria-hidden="true">🛰️</span> File: {target_output.name} is ready for distribution.</div>\n'
        else:
            yield f'\n<div class="status-error"><span aria-hidden="true">🔥</span> ERROR: FFmpeg surgical sequence failed.</div>\n'

    except Exception as e:
        yield f'\n<div class="status-error"><span aria-hidden="true">🔥</span> ERROR: {str(e)}</div>\n'

def _handle_folder_discovery():
    """
    Opens the user's Video directory.
    """
    try:
        if os.name == 'nt':
            os.startfile(str(OUTPUT_DIR))
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- END OF FILE music-sharing.py ---