# --- START OF FILE [D:\MetaForge Suite\common\io_bridge.py] ---
# ======================================================================
# MetaForge Shared Primitive: IO Bridge
# Physical Location: \common\io_bridge.py
# Build 1.0.0: Standardized path validation and directory scanning.
# ======================================================================
import sys
import os
import json
from pathlib import Path

# --- [ PATH BOOTSTRAP ] ---
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from common import config_handler

def validate_path(target_path):
    """
    Ensures a path exists and is a directory.
    Returns (bool, Path_Object or Error_Message)
    """
    try:
        p = Path(target_path)
        if not p.exists():
            return False, "Path does not exist."
        if not p.is_dir():
            return False, "Target is not a directory."
        return True, p
    except Exception as e:
        return False, str(e)

def get_audio_targets(folder_path, recursive=False):
    """
    Scans a directory for .mp3 files.
    Returns a list of Path objects.
    """
    success, result = validate_path(folder_path)
    if not success:
        return []

    pattern = "**/*.mp3" if recursive else "*.mp3"
    # Case-insensitive globbing for .mp3 and .MP3
    targets = list(result.glob(pattern))
    
    # Sort alphabetically by filename for consistent processing order
    return sorted(targets, key=lambda x: x.name.lower())

def get_folder_manifest(folder_path):
    """
    Checks for and parses manifest.json in the target directory.
    Returns dictionary of manifest data or empty dict if not found.
    """
    success, result = validate_path(folder_path)
    if not success:
        return {}
    
    manifest_path = result / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

# --- [ DIAGNOSTIC SUITE ] ---

def run_diagnostics():
    print("\n--- MetaForge Primitive Diagnostic: IO Bridge ---")
    
    # Test 1: Path Validation
    print("[1/3] Testing Path Validation...", end=" ")
    success, _ = validate_path(PROJECT_ROOT)
    if success:
        print("PASS")
    else:
        print("FAIL")

    # Test 2: Directory Scanning
    print("[2/3] Testing .mp3 Discovery...", end=" ")
    test_dir = PROJECT_ROOT / "_mf_io_test"
    test_dir.mkdir(exist_ok=True)
    (test_dir / "test1.mp3").write_bytes(b"")
    (test_dir / "test2.MP3").write_bytes(b"")
    (test_dir / "ignore.txt").write_bytes(b"")

    targets = get_audio_targets(test_dir)
    
    if len(targets) == 2:
        print("PASS")
    else:
        print("FAIL")

    # Test 3: Manifest Discovery
    print("[3/3] Testing Manifest Discovery...", end=" ")
    test_manifest = test_dir / "manifest.json"
    test_manifest.write_text(json.dumps({"test": "data"}))
    
    manifest = get_folder_manifest(test_dir)
    if manifest.get("test") == "data":
        print("PASS")
    else:
        print("FAIL")

    # Cleanup
    import shutil
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    run_diagnostics()
# --- END OF FILE [D:\MetaForge Suite\common\io_bridge.py] ---