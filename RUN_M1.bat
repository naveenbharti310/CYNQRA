@echo off
title Cynqra M1
setlocal
cd /d "%~dp002_harness"

rem Find Python 3. The py launcher comes with the python.org installer.
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto nopython

%PY% m1.py
echo.
pause
exit /b 0

:nopython
echo.
echo Python 3 is not installed on this computer.
echo A download page will open. Choose the latest Python 3 for Windows,
echo tick "Add python.exe to PATH" on the first screen, finish the install,
echo then double click RUN_M1.bat again.
echo.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
