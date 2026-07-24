@echo off
setlocal EnableExtensions
title Build IDM Trial Resetter Pro EXE
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found on PATH.
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PyInstaller...
    python -m pip install -U pyinstaller
    if errorlevel 1 exit /b 1
)

python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing PySide6...
    python -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 exit /b 1
)

echo [*] Cleaning previous build...
if exist "build" rmdir /s /q "build"
if exist "dist\IDM_Trial_Resetter_Pro.exe" del /f /q "dist\IDM_Trial_Resetter_Pro.exe"

echo [*] Building one-file admin EXE...
python -m PyInstaller --noconfirm --clean "IDM_Trial_Resetter_Pro.spec"
if errorlevel 1 (
    echo [!] Build failed.
    exit /b 1
)

if not exist "dist\IDM_Trial_Resetter_Pro.exe" (
    echo [!] EXE not found after build.
    exit /b 1
)

echo.
echo [+] Built: %~dp0dist\IDM_Trial_Resetter_Pro.exe
for %%A in ("dist\IDM_Trial_Resetter_Pro.exe") do echo     Size: %%~zA bytes
echo [+] Double-click the EXE — Windows will prompt for Administrator.
echo.
exit /b 0
