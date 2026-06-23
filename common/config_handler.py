# --- START OF FILE config_handler.py ---
# ======================================================================
# MetaForge Global Configuration (FIXED RUNTIME SAFE VERSION)
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
DEPLOY_DIR = PROJECT_ROOT / "deploy"

# --- USER SANDBOX ---
APPDATA_MF = Path(os.environ.get('APPDATA')) / "MetaForge"
LOGS_DIR = APPDATA_MF / "logs"
DB_PATH = APPDATA_MF / "metaforge.db"
ENV_PATH = APPDATA_MF / ".env"

# --- LOAD ENV (SAFE, IDEMPOTENT) ---
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

# ---------------------------------------------------------
# RUNTIME RESOLVERS (CRITICAL FIX)
# ---------------------------------------------------------

def GEMINI_API_KEY():
    return os.getenv("GEMINI_KEY")


def ACOUSTID_API_KEY():
    return os.getenv("ACOUSTID_KEY")


def DISCOGS_TOKEN():
    return os.getenv("DISCOGS_TOKEN")


def LIBRARY_ROOT():
    return Path(os.getenv("LIBRARY_ROOT", "C:\\Music"))

# --- EXECUTABLE DEPENDENCIES ---
FFMPEG_EXE = BIN_DIR / "ffmpeg.exe"
FPCALC_EXE = BIN_DIR / "fpcalc.exe"
SQLITE_EXE = BIN_DIR / "sqlite3.exe"
MP3VAL_EXE = BIN_DIR / "mp3val.exe"
YT_DLP_EXE = BIN_DIR / "yt-dlp.exe"


def check_system():
    print("--- MetaForge Suite: System Check ---")
    print(f"Root: {PROJECT_ROOT}")
    print(f"DB: {'OK' if DB_PATH.exists() else 'MISSING'}")
    print(f"ACOUSTID: {'OK' if ACOUSTID_API_KEY() else 'MISSING'}")
    print(f"DISCOGS: {'OK' if DISCOGS_TOKEN() else 'MISSING'}")


if __name__ == "__main__":
    check_system()

# --- END OF FILE config_handler.py ---