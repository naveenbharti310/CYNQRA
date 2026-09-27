@echo off
title Cynqra POC
setlocal
cd /d "%~dp0poc"

rem Find Python 3.10 or newer. The py launcher comes with the python.org installer.
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || goto oldpython

echo.
echo Cynqra POC is starting at http://127.0.0.1:8750
echo Your browser opens by itself. Close this window to stop Cynqra.
echo For live mode, set ANTHROPIC_API_KEY before double clicking this file.
echo.
%PY% run_poc.py
echo.
pause
exit /b 0

:oldpython
echo.
echo This Python is older than 3.10. Install the latest Python 3 from python.org,
echo then double click RUN_POC.bat again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:nopython
echo.
echo Python 3 is not installed on this computer.
echo A download page will open. Choose the latest Python 3 for Windows,
echo tick "Add python.exe to PATH" on the first screen, finish the install,
echo then double click RUN_POC.bat again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
