@echo off
rem Cynqra for Windows, straight from its source: double-click to get the latest version and open it.
rem No installer and no build: each start fetches the newest changes, so a fix is ready the moment it is pushed.
rem Needs, once: Python 3.10 or newer (python.org) and Git for Windows (git-scm.com).
title Cynqra
cd /d "%~dp0"

where git >nul 2>&1
if %errorlevel%==0 (
  echo Getting the latest version of Cynqra...
  git pull --ff-only
  if errorlevel 1 echo Could not update ^(offline, or files changed here^). Starting the version you have.
) else (
  echo Git is not installed, so Cynqra cannot update itself. Get it from https://git-scm.com/download/win
)

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Python 3.10 or newer is needed. Install it from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during the install. Then double-click this file again.
  pause
  exit /b 1
)

echo Starting Cynqra...
%PY% -X utf8 poc\desktop.py
if errorlevel 1 (
  echo.
  echo Cynqra stopped with an error. The details are above; send a screenshot of this window.
  pause
)
