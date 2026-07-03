@ECHO OFF
REM BFCPEOPTIONSTART
REM Advanced BAT to EXE Converter www.BatToExeConverter.com
REM BFCPEEXE=
REM BFCPEICON=
REM BFCPEICONINDEX=-1
REM BFCPEEMBEDDISPLAY=0
REM BFCPEEMBEDDELETE=1
REM BFCPEADMINEXE=0
REM BFCPEINVISEXE=0
REM BFCPEVERINCLUDE=0
REM BFCPEVERVERSION=1.0.0.0
REM BFCPEVERPRODUCT=Product Name
REM BFCPEVERDESC=Product Description
REM BFCPEVERCOMPANY=Your Company
REM BFCPEVERCOPYRIGHT=Copyright Info
REM BFCPEWINDOWCENTER=1
REM BFCPEDISABLEQE=0
REM BFCPEWINDOWHEIGHT=30
REM BFCPEWINDOWWIDTH=120
REM BFCPEWTITLE=Window Title
REM BFCPEOPTIONEND
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
:: Updated to run app.py from root
python ui\app.py

:: 4. Keep window open if it crashes so we can see why
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] MetaForge closed unexpectedly.
    pause
)
deactivate