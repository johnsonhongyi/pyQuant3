@echo off
REM Popularity Resonance GUI Compilation Script
setlocal enabledelayedexpansion

echo.
echo ================== PR GUI Build Script ==================
echo.

REM Check PyInstaller
echo [CHECK] Checking if PyInstaller is installed...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed. Please run: pip install pyinstaller
    pause
    exit /b 1
)
echo [OK] PyInstaller is installed.

set SCRIPT_NAME=popularity_resonance_gui.py
set EXE_NAME=PopularityResonanceSync

echo.
echo [BUILD] Building standalone executable...
echo Script: %SCRIPT_NAME%
echo.

pyinstaller -y "%EXE_NAME%.spec"

if errorlevel 1 (
    echo [ERROR] Compilation failed.
    pause
    exit /b 1
)

echo.
echo ================== BUILD SUCCESSFUL ==================
echo.
echo [OUTPUT] .\dist\%EXE_NAME%.exe
echo.
explorer "%CD%\dist"

pause
