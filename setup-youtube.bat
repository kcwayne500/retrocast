@echo off
setlocal
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 (python -m venv .venv)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "import sys; sys.exit(1) if sys.version_info < (3, 11) else None"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --upgrade "yt-dlp[default]"
if errorlevel 1 goto failed
echo YouTube support installed. Run start.bat.
pause
exit /b 0
:failed
echo Install Python 3.11 or newer and check internet access.
pause
exit /b 1
