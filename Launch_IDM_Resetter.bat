@echo off
title IDM Trial Resetter Pro
cd /d "%~dp0"

:: Prefer packaged one-file EXE (embeds requireAdministrator)
if exist "%~dp0dist\IDM_Trial_Resetter_Pro.exe" (
    start "" "%~dp0dist\IDM_Trial_Resetter_Pro.exe"
    exit /b 0
)
if exist "%~dp0IDM_Trial_Resetter_Pro.exe" (
    start "" "%~dp0IDM_Trial_Resetter_Pro.exe"
    exit /b 0
)

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    echo Or build the EXE with build_exe.bat
    pause
    exit /b 1
)

python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo Installing PySide6...
    python -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting Administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList '\"%~dp0app.py\"' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b 0
)

python "%~dp0app.py"
if errorlevel 1 pause
