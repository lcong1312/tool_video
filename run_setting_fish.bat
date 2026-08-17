@echo off
setlocal
cd /d "%~dp0"
title Fish Mexico GUI

python "%CD%\fish_mexico_gui.py"

if errorlevel 1 (
    echo.
    echo Chuong trinh da dung do co loi.
    pause
)
