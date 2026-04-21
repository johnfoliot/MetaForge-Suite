@echo off
TITLE MetaForge Studio Launcher
COLOR 06

:: 1. Navigate to the project root
echo [SYSTEM] Moving to MetaForge Suite...
cd /d "D:\MetaForge Suite"

:: 2. Activate the Virtual Environment
echo [SYSTEM] Activating Sandbox...
call "venv\Scripts\activate.bat"

:: 3. Launch the Server and UI
echo [SYSTEM] Starting MetaForge Server Engine...
echo.
python ui\app.py

:: 4. Keep window open if it crashes so we can see why
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] MetaForge closed unexpectedly.
    pause
)
deactivate