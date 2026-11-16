# ======================================================================
# MetaForge Common: audio checks (v2, 2026-11-16)
# Physical Location: \common\audio_check.py
# ======================================================================
"""
Shared MP3 health checks.

mp3val ALWAYS exits 0, even for a damaged file (measured 2026-11-16): it
reports problems only as "WARNING:"/"ERROR:" lines on stdout. Code that
tested its return code never saw any damage. Use mp3val_problems().
"""
import subprocess

from common import config_handler


def mp3val_problems(path, fix=False):
    """mp3val's WARNING/ERROR lines for a file (empty list = clean). fix=True repairs in place, no .bak."""
    cmd = [str(config_handler.MP3VAL_EXE)] + (["-f", "-nb"] if fix else []) + [str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=120).stdout
    problems = []
    for line in out.splitlines():
        if line.startswith(("WARNING", "ERROR")):
            # Drop the quoted path so the message reads on its own.
            msg = line.split('": ', 1)[-1] if '": ' in line else line
            msg = msg.split("): ", 1)[-1] if msg.startswith(("WARNING", "ERROR")) and "): " in msg else msg
            problems.append(msg.strip())
    return problems


def decode_errors(path):
    """How many errors FFmpeg reports while decoding the whole file (0 = it plays cleanly)."""
    res = subprocess.run([str(config_handler.FFMPEG_EXE), "-v", "error", "-i", str(path), "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace", timeout=600)
    return len([l for l in res.stderr.splitlines() if l.strip()])


def length_seconds(path):
    """Playing length from the file's own headers (mutagen), or None."""
    try:
        import mutagen
        f = mutagen.File(str(path))
        return float(f.info.length) if f and f.info else None
    except Exception:
        return None
