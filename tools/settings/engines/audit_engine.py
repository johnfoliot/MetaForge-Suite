# ======================================================================
# MetaForge Mini-Engine: Binary Dependency Auditor
# Physical Location: \tools\settings\engines\audit_engine.py
# ======================================================================
import subprocess
from pathlib import Path
from flask import jsonify

# --- SETTINGS AUDIT ENGINE ---

def run(base_dir):
    """
    Executes local binaries to verify presence and versioning.
    """
    bin_dir = base_dir / "bin"
    results = []
    
    # Map of target binaries and the flags required to return a version string
    targets = {
        "yt-dlp.exe": "--version",
        "ffmpeg.exe": "-version",
        "fpcalc.exe": "-version",
        "mp3val.exe": "-h", 
        "sqlite3.exe": "--version"
    }

    for exe, flag in targets.items():
        exe_path = bin_dir / exe
        version_str = "Missing"
        status = "error"

        if exe_path.exists():
            try:
                # Execute the binary and capture the standard output
                res = subprocess.run(
                    [str(exe_path), flag], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                raw_output = res.stdout.strip()
                
                # Logic-based parsing for specific binary output formats
                if exe == "ffmpeg.exe": 
                    version_str = raw_output.split('version ')[1].split(' ')[0]
                elif exe == "mp3val.exe": 
                    # Extract version from the help header
                    parts = raw_output.split(' ')
                    version_str = parts[1] if len(parts) > 1 else "Found"
                elif exe == "sqlite3.exe": 
                    version_str = raw_output.split(' ')[0]
                else: 
                    # Default to the first line of output
                    version_str = raw_output.split('\n')[0]
                
                status = "ok"
            except Exception as e:
                version_str = "Execution Error"
        
        results.append({
            "name": exe, 
            "version": version_str, 
            "status": status
        })
    
    return jsonify(results)

# --- SETTINGS AUDIT ENGINE END ---