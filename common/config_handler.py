# --- START OF FILE config_handler.py ---
# ======================================================================
# MetaForge Global Configuration
# File Location: \MetaForge Suite\common\config_handler.py
# Build 5.3.1: Added DIST_DIR for update manifest isolation.
# ======================================================================
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# --- THE ANCHOR (DRIVE ROOT) ---
COMMON_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = COMMON_DIR.parent.resolve()

# --- MODULE PATHS ---
UI_ROOT = PROJECT_ROOT / "ui"
HTML_DIR = UI_ROOT / "html"
TOOLS_DIR = PROJECT_ROOT / "tools"
BIN_DIR = PROJECT_ROOT / "bin"
DATA_DIR = PROJECT_ROOT / "data"
DIST_DIR = PROJECT_ROOT / "dist"  # Distribution and Update metadata

# --- THE USER SANDBOX (IDENTITY & STATE) ---
APPDATA_MF = Path(os.environ.get('APPDATA')) / "MetaForge"
LOGS_DIR = APPDATA_MF / "logs"
DB_PATH = APPDATA_MF / "metaforge.db"
ENV_PATH = APPDATA_MF / ".env"

# --- SYSTEM FILES ---
UPDATE_MANIFEST = DIST_DIR / "updates.json"

# --- LOAD SECRETS ---
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# API SECRETS
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
ACOUSTID_API_KEY = os.getenv("ACOUSTID_KEY")
LIBRARY_ROOT = Path(os.getenv("LIBRARY_ROOT", "C:\\Music"))

# --- EXECUTABLE DEPENDENCIES (\BIN) ---
FFMPEG_EXE = BIN_DIR / "ffmpeg.exe"
FPCALC_EXE = BIN_DIR / "fpcalc.exe"
SQLITE_EXE = BIN_DIR / "sqlite3.exe"
MP3VAL_EXE = BIN_DIR / "mp3val.exe"
YT_DLP_EXE = BIN_DIR / "yt-dlp.exe"

def check_system():
    """Diagnostic check for the MetaForge Suite."""
    print("--- MetaForge Suite: System Check ---")
    print(f"   Root: {PROJECT_ROOT}")
    print(f"   Dist: {DIST_DIR}")
    print(f"   Database: {'✅ Found' if DB_PATH.exists() else '❌ Missing'}")
    print(f"   Updates:  {'✅ Found' if UPDATE_MANIFEST.exists() else '⚠️ Missing'}")

if __name__ == "__main__":
    check_system()
# --- END OF FILE config_handler.py ---