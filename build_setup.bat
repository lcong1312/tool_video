@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_NAME=CapCutVideoTool"
set "SPEC_FILE=CapCutVideoTool.spec"
set "ISS_FILE=installer\CapCutVideoToolSetup.iss"
set "DIST_DIR=dist\%APP_NAME%"
set "SETUP_EXE=installer_output\CapCutVideoToolSetup.exe"
set "APP_BIN=%~dp0bin"
set "LOCAL_FFMPEG=%~dp0tools\ffmpeg\bin"

echo ========================================
echo Build CapCut Video Tool setup
echo ========================================
echo.

set "PY_CMD="
where python >nul 2>nul
if %errorlevel%==0 set "PY_CMD=python"

if not defined PY_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 set "PY_CMD=py -3"
)

if not defined PY_CMD (
    echo [ERROR] Khong tim thay Python.
    echo Hay cai Python 3.12+ roi chay lai file nay.
    pause
    exit /b 1
)

if exist "%APP_BIN%\ffmpeg.exe" set "PATH=%APP_BIN%;%PATH%"
if exist "%LOCAL_FFMPEG%\ffmpeg.exe" set "PATH=%LOCAL_FFMPEG%;%PATH%"

if not exist "%APP_BIN%\ffmpeg.exe" if not exist "%LOCAL_FFMPEG%\ffmpeg.exe" (
    echo.
    echo [0/4] Thieu FFmpeg, dang chay install_deps.ps1 de tai portable FFmpeg...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_deps.ps1"
    if not %errorlevel%==0 goto failed
)

if not exist "%APP_BIN%" mkdir "%APP_BIN%"
if not exist "%APP_BIN%\ffmpeg.exe" if exist "%LOCAL_FFMPEG%\ffmpeg.exe" copy /y "%LOCAL_FFMPEG%\ffmpeg.exe" "%APP_BIN%\" >nul
if not exist "%APP_BIN%\ffprobe.exe" if exist "%LOCAL_FFMPEG%\ffprobe.exe" copy /y "%LOCAL_FFMPEG%\ffprobe.exe" "%APP_BIN%\" >nul
if not exist "%APP_BIN%\ffplay.exe" if exist "%LOCAL_FFMPEG%\ffplay.exe" copy /y "%LOCAL_FFMPEG%\ffplay.exe" "%APP_BIN%\" >nul

if not exist "%APP_BIN%\ffmpeg.exe" (
    echo [ERROR] Thieu bin\ffmpeg.exe.
    echo Chay run_gui.bat mot lan de tu tai FFmpeg, hoac dat ffmpeg.exe vao thu muc bin.
    pause
    exit /b 1
)

if not exist "%APP_BIN%\ffprobe.exe" (
    echo [ERROR] Thieu bin\ffprobe.exe.
    echo Chay run_gui.bat mot lan de tu tai FFmpeg, hoac dat ffprobe.exe vao thu muc bin.
    pause
    exit /b 1
)

if not exist "vendor\VOICEVOX" (
    echo [WARN] Khong thay vendor\VOICEVOX.
    echo Setup van co the build loi neu spec dang yeu cau bundle VOICEVOX.
)

if not exist "vendor\auto_capcut_pro" (
    echo [WARN] Khong thay vendor\auto_capcut_pro.
    echo Setup van co the build loi neu spec dang yeu cau bundle Auto CapCut.
)

echo.
echo [1/4] Cai/cap nhat thu vien build...
%PY_CMD% -m pip install --upgrade pyinstaller fish-audio-sdk python-dotenv httpx tkinterdnd2 python-docx requests
if not %errorlevel%==0 goto failed

echo.
echo [2/4] Don output build cu...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if not exist installer_output mkdir installer_output

echo.
echo [3/4] Build app bang PyInstaller...
%PY_CMD% -m PyInstaller --clean --noconfirm "%SPEC_FILE%"
if not %errorlevel%==0 goto failed

if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo [ERROR] Khong thay file exe sau khi build: %DIST_DIR%\%APP_NAME%.exe
    goto failed
)

set "ISCC_CMD="
where iscc >nul 2>nul
if %errorlevel%==0 set "ISCC_CMD=iscc"

if not defined ISCC_CMD if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC_CMD (
    echo [ERROR] Khong tim thay Inno Setup Compiler ^(ISCC.exe^).
    echo Cai Inno Setup 6: https://jrsoftware.org/isinfo.php
    pause
    exit /b 1
)

echo.
echo [4/4] Dong goi setup exe bang Inno Setup...
"%ISCC_CMD%" "%ISS_FILE%"
if not %errorlevel%==0 goto failed

if exist "%SETUP_EXE%" (
    echo.
    echo [OK] Da build xong:
    echo %~dp0%SETUP_EXE%
    pause
    exit /b 0
)

echo [ERROR] Build xong nhung khong thay setup exe: %SETUP_EXE%
goto failed

:failed
echo.
echo [FAILED] Build setup khong thanh cong.
pause
exit /b 1
