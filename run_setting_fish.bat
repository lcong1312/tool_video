@echo off
setlocal
cd /d "%~dp0"
title Fish Mexico GUI

if exist "%~dp0CapCutVideoTool.exe" (
    "%~dp0CapCutVideoTool.exe" --fish-settings
    goto check_error
)

python "%CD%\fish_mexico_gui.py"

:check_error
if errorlevel 1 (
    echo.
    echo Chuong trinh da dung do co loi.
    pause
)
