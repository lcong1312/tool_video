@echo off
setlocal
cd /d "%~dp0"

set "APP_BIN=%~dp0bin"
set "LOCAL_FFMPEG=%~dp0tools\ffmpeg\bin"
if exist "%APP_BIN%\ffmpeg.exe" set "PATH=%APP_BIN%;%PATH%"
if exist "%LOCAL_FFMPEG%\ffmpeg.exe" set "PATH=%LOCAL_FFMPEG%;%PATH%"

echo Dang kiem tra va cai cac thanh phan can thiet...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_deps.ps1"
if not %errorlevel%==0 goto failed

if exist "%APP_BIN%\ffmpeg.exe" set "PATH=%APP_BIN%;%PATH%"
if exist "%LOCAL_FFMPEG%\ffmpeg.exe" set "PATH=%LOCAL_FFMPEG%;%PATH%"

set "PY_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PY_CMD=python"

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
        if exist "%%~fD\python.exe" set "PY_CMD=%%~fD\python.exe"
    )
)

if not defined PY_CMD (
    if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" set "PY_CMD=%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
)

if not defined PY_CMD (
    for /d %%D in ("%ProgramFiles%\Python*") do (
        if exist "%%~fD\python.exe" set "PY_CMD=%%~fD\python.exe"
    )
)

if not defined PY_CMD (
    echo Khong tim thay Python sau khi cai.
    echo Hay dong cua so nay, mo lai, roi chay lai run_gui.bat.
    goto failed
)

where ffmpeg >nul 2>nul
if not %errorlevel%==0 (
    echo Khong tim thay ffmpeg sau khi cai.
    goto failed
)

where ffprobe >nul 2>nul
if not %errorlevel%==0 (
    echo Khong tim thay ffprobe sau khi cai.
    goto failed
)

echo Dang mo giao dien...
%PY_CMD% capcut_video_gui.py
goto done

:failed
echo.
echo Chua the mo giao dien.
pause
exit /b 1

:done
pause
