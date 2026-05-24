@echo off
chcp 65001 >nul
title Nuitka Onefile Resource Extraction Test Runner (Clang-CL)
setlocal enabledelayedexpansion

echo ===================================================
echo Nuitka Onefile Test Pipeline (VS Clang-CL)
echo ===================================================
echo.

:: 1. Load VS Environment
echo [1/4] Loading VS 2019 Community Developer Environment...
call "D:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
echo.

:: 2. Remove GCC from PATH to guarantee Clang-CL is used
echo [2/4] Sanitizing PATH of any GCC/MinGW remnants...
set "PATH=!PATH:D:\mingw64\bin;=!"
set "PATH=!PATH:D:\mingw64\bin=!"
set "PATH=!PATH:D:\mingw64;=!"
set "PATH=!PATH:D:\mingw64=!"
echo.

:: 3. Execute Nuitka Onefile Compilation (Extreme Speed Mode)
echo [3/4] Compiling test_onefile_ini.py with Nuitka...
echo.
python -m nuitka ^
    --onefile ^
    --clang ^
    --remove-output ^
    --include-data-files=JohnsonUtil/global.ini=JohnsonUtil/global.ini ^
    test_onefile_ini.py

echo.
if exist "test_onefile_ini.exe" (
    echo [4/4] Compilation SUCCESSFUL! Running test_onefile_ini.exe...
    echo ----------------------------------------------------------
    test_onefile_ini.exe
    echo ----------------------------------------------------------
) else (
    echo [ERROR] Nuitka compilation failed. Please review compiler logs above.
)

echo.
echo ===================================================
echo Build pipeline execution complete.
echo ===================================================
pause
