@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "PID_FILE=%CD%\updates\update_server.pid"

if not exist "%PID_FILE%" (
    echo Khong thay PID file: %PID_FILE%
    exit /b 0
)

for /f "usebackq delims=" %%P in ("%PID_FILE%") do set "PID=%%P"
if "%PID%"=="" (
    del "%PID_FILE%" >nul 2>nul
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Stop-Process -Id %PID% -Force -ErrorAction SilentlyContinue"
del "%PID_FILE%" >nul 2>nul
echo Da dung update server PID %PID%.
