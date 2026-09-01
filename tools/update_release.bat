@echo off
setlocal EnableExtensions

REM Sua 2 dong nay moi khi muon phat hanh ban update moi.
set "APP_VERSION=1.0.7"
set "UPDATE_NOTES=update"

cd /d "%~dp0\.."

echo ========================================
echo Release CapCut Video Tool update
echo ========================================
echo Version: %APP_VERSION%
echo Notes  : %UPDATE_NOTES%
echo.

call .\tools\release_update.bat %APP_VERSION% "%UPDATE_NOTES%"
set "EXIT_CODE=%errorlevel%"

if "%EXIT_CODE%"=="0" (
    echo.
    echo [OK] Release update ready: %APP_VERSION%
    echo Public manifest: https://update.nexflow.click/latest.json
) else (
    echo.
    echo [ERROR] Release failed with code %EXIT_CODE%
)

echo.
pause
exit /b %EXIT_CODE%
