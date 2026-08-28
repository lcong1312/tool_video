@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PORT=%~1"
if "%PORT%"=="" set "PORT=18080"

echo Serving update files from %CD%\updates
echo Local URL: http://localhost:%PORT%/latest.json
echo Cloudflare Tunnel can point to: http://localhost:%PORT%
python -m http.server %PORT% --directory updates
