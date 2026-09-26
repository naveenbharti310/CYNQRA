@echo off
title Cynqra
cd /d "%~dp0"
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (echo Python is missing. Run INSTALL.bat first. & pause & exit /b 1)
if "%~1"=="" (%PY% poc\cynqra_cli.py run) else (%PY% poc\cynqra_cli.py %*)
echo.
pause
