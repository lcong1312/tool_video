@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "VERSION=%~1"
set "NOTES=%~2"

if "%VERSION%"=="" (
    echo Usage: tools\release_update.bat 1.0.4 "Update notes"
    exit /b 1
)

if "%NOTES%"=="" set "NOTES=update"

python .\tools\set_app_version.py %VERSION%
if not %errorlevel%==0 exit /b %errorlevel%

set "NO_PAUSE=1"
call .\build_setup.bat
if not %errorlevel%==0 exit /b %errorlevel%

python .\tools\make_update_manifest.py --version %VERSION% --notes "%NOTES%"
if not %errorlevel%==0 exit /b %errorlevel%

echo Release update ready: %VERSION%
echo Manifest: updates\latest.json
echo Installer: updates\CapCutVideoToolSetup.exe
