@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PORT=%~1"
if "%PORT%"=="" set "PORT=18080"

set "PID_FILE=%CD%\updates\update_server.pid"
set "OUT_LOG_FILE=%CD%\updates\update_server.out.log"
set "ERR_LOG_FILE=%CD%\updates\update_server.err.log"

if not exist "updates" mkdir "updates"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$root=(Resolve-Path '.').Path;" ^
  "$updates=Join-Path $root 'updates';" ^
  "$pidFile=Join-Path $updates 'update_server.pid';" ^
  "$outLogFile=Join-Path $updates 'update_server.out.log';" ^
  "$errLogFile=Join-Path $updates 'update_server.err.log';" ^
  "$port=%PORT%;" ^
  "$existing=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1;" ^
  "if ($existing) { Set-Content -Encoding ascii -Path $pidFile -Value $existing.OwningProcess; exit 0 }" ^
  "$args='-m http.server ' + $port + ' --bind 127.0.0.1';" ^
  "$p=Start-Process -FilePath 'python' -ArgumentList $args -WorkingDirectory $updates -WindowStyle Hidden -RedirectStandardOutput $outLogFile -RedirectStandardError $errLogFile -PassThru;" ^
  "Set-Content -Encoding ascii -Path $pidFile -Value $p.Id;"

if not %errorlevel%==0 (
    echo Khong start duoc update server.
    exit /b 1
)

echo Update server is running in background on http://localhost:%PORT%
echo PID file: %PID_FILE%
echo Output log file: %OUT_LOG_FILE%
echo Error log file: %ERR_LOG_FILE%
