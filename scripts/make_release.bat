@echo off
setlocal EnableExtensions
title Create GitHub Release with EXE
cd /d "%~dp0.."

:: Usage:
::   scripts\make_release.bat
::   scripts\make_release.bat v5.0.1

set "TAG=%~1"
if "%TAG%"=="" set "TAG=v5.0.0"

where gh >nul 2>&1
if errorlevel 1 (
    echo [!] GitHub CLI not found.
    echo     winget install GitHub.cli
    echo     then: gh auth login
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo [!] git not found.
    exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [!] No git remote "origin".
    echo.
    echo     1. Create empty repo on GitHub named IDM-Trial-Resetter-Pro
    echo     2. Run:
    echo        git remote add origin https://github.com/YOUR_USER/IDM-Trial-Resetter-Pro.git
    echo        git push -u origin main
    echo     3. Re-run this script
    exit /b 1
)

if not exist "dist\IDM_Trial_Resetter_Pro.exe" (
    echo [*] EXE missing — building with build_exe.bat ...
    call build_exe.bat
    if errorlevel 1 exit /b 1
)

if not exist "dist\IDM_Trial_Resetter_Pro.exe" (
    echo [!] dist\IDM_Trial_Resetter_Pro.exe still missing
    exit /b 1
)

echo [*] Hashing artifact...
powershell -NoProfile -Command ^
  "Get-FileHash 'dist\IDM_Trial_Resetter_Pro.exe' -Algorithm SHA256 | Format-List | Out-File -Encoding utf8 'dist\SHA256.txt'; Copy-Item 'dist\IDM_Trial_Resetter_Pro.exe' 'dist\IDM_Trial_Resetter_Pro-windows-x64.exe' -Force"

echo [*] Writing release notes...
> "%TEMP%\idm_release_notes.md" echo ## IDM Trial Resetter Pro %TAG%
>> "%TEMP%\idm_release_notes.md" echo.
>> "%TEMP%\idm_release_notes.md" echo ### Downloads
>> "%TEMP%\idm_release_notes.md" echo - `IDM_Trial_Resetter_Pro.exe` — one-file Windows x64 UI
>> "%TEMP%\idm_release_notes.md" echo - `SHA256.txt` — checksum
>> "%TEMP%\idm_release_notes.md" echo.
>> "%TEMP%\idm_release_notes.md" echo ### Run
>> "%TEMP%\idm_release_notes.md" echo 1. Download the EXE
>> "%TEMP%\idm_release_notes.md" echo 2. Double-click and approve UAC
>> "%TEMP%\idm_release_notes.md" echo 3. Use Operations -^> Reset Trial / Freeze

echo [*] Pushing main...
git push -u origin main
if errorlevel 1 (
    echo [!] git push failed. Fix remote/auth, then retry.
    exit /b 1
)

git rev-parse "%TAG%" >nul 2>&1
if errorlevel 1 (
    echo [*] Creating tag %TAG%
    git tag -a "%TAG%" -m "Release %TAG%"
)

echo [*] Pushing tag %TAG%...
git push origin "%TAG%"
if errorlevel 1 (
    echo [!] tag push failed ^(tag may already exist on remote^) — continuing
)

gh release view "%TAG%" >nul 2>&1
if errorlevel 1 (
    echo [*] Creating release %TAG%...
    gh release create "%TAG%" ^
      "dist\IDM_Trial_Resetter_Pro.exe" ^
      "dist\IDM_Trial_Resetter_Pro-windows-x64.exe" ^
      "dist\SHA256.txt" ^
      --title "IDM Trial Resetter Pro %TAG%" ^
      --notes-file "%TEMP%\idm_release_notes.md"
) else (
    echo [*] Updating assets on existing release %TAG%...
    gh release upload "%TAG%" ^
      "dist\IDM_Trial_Resetter_Pro.exe" ^
      "dist\IDM_Trial_Resetter_Pro-windows-x64.exe" ^
      "dist\SHA256.txt" ^
      --clobber
)

if errorlevel 1 (
    echo [!] gh release failed. Run: gh auth login
    exit /b 1
)

echo.
echo [+] Done. Opening release page...
gh release view "%TAG%" --web
exit /b 0
