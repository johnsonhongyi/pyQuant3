@echo off
title 🧠 Nuitka CLANG ONLY FIXED (v4 compatible)
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo 🧠 Nuitka CLANG ONLY FINAL FIX
echo ==========================================
echo.

:: =========================================
:: 1. 保留 Python + LLVM，不破坏 PATH
:: =========================================
set "OLD_PATH=%PATH%"
set "CLANG_PATH=C:\Users\Johnson\scoop\apps\llvm\current\bin"

set "PATH=%CLANG_PATH%;%PATH%"

echo 🧹 Cleaning all potential GCC paths from PATH to force Clang-only...
set "PATH=%PATH:D:\mingw64\bin;=%"
set "PATH=%PATH:D:\mingw64;=%"
set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\usr\bin;=%"
set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\mingw-w64\bin;=%"
set "PATH=%PATH:C:\Users\Johnson\scoop\shims;=%"

echo 🧹 PATH READY. Current PATH clean of GCC.
echo.

:: =========================================
:: 2. clang 检查
:: =========================================
set "CLANG_CHECK_EXE=%CLANG_PATH%\clang.exe"

if not exist "%CLANG_CHECK_EXE%" (
    echo ❌ clang not found
    pause
    exit /b
)

echo 🧪 clang OK: %CLANG_CHECK_EXE%
echo.

:: =========================================
:: 2.5 GCC 泄露拦截断言 - 极速拦截
:: =========================================
echo 🛡️ Asserting GCC-free environment...
where gcc >nul 2>&1
if not errorlevel 1 (
    echo.
    echo ❌ [FATAL ERROR] GCC still detected in active PATH:
    where gcc
    echo ❌ [FATAL ERROR] Strict Clang-Only build aborted to prevent silent GCC fallback!
    echo.
    pause
    exit /b
)
echo 🛡️ GCC check passed. No GCC visible in PATH.
echo.

rem Let Nuitka Scons automatically detect and use the native MSVC clang-cl
rem DO NOT override CC/CXX here, as it breaks Scons Windows parsing.
set "CC="
set "CXX="

:: =========================================
:: 3. Python
:: =========================================
if defined VIRTUAL_ENV (
    set "PYTHON_EXEC=%VIRTUAL_ENV%\Scripts\python.exe"
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set "PYTHON_EXEC=%%i"
        goto :pyok
    )
)

:pyok
if "%PYTHON_EXEC%"=="" (
    echo ❌ Python not found
    pause
    exit /b
)

echo 🐍 Python: %PYTHON_EXEC%
echo.

:: =========================================
:: 4. 项目配置
:: =========================================
set MAIN_SCRIPT=异动联动.py
set OUTPUT_NAME=异动联动.exe
set OUTPUT_DIR=build
set ICON_FILE=app.ico

:: =========================================
:: 5. CSV 路径
:: =========================================
for /f "usebackq delims=" %%i in (`
%PYTHON_EXEC% -c "import os,a_trade_calendar; print(os.path.join(os.path.dirname(a_trade_calendar.__file__), 'a_trade_calendar.csv'))"
`) do set CSV_PATH=%%i

if "%CSV_PATH%"=="" (
    echo ❌ CSV_PATH empty
    pause
    exit /b
)

echo ✅ CSV: %CSV_PATH%
echo.

:: =========================================
:: 0. Activate Visual Studio Native Environment for full MSVC+Clang-CL
:: =========================================
set "VS_VARS=D:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
if exist "%VS_VARS%" (
    echo [INFO] Activating Native Visual Studio Environment for Full Clang-CL mode...
    call "%VS_VARS%" >nul
    echo [SUCCESS] MSVC Native Linker and Environment loaded!
    echo.
)

:: =========================================
:: 6. Nuitka CLANG ONLY (NO clang-path !!!)
:: =========================================
set CMD=%PYTHON_EXEC% -m nuitka ^
--onefile ^
--clang ^
--show-scons ^
--assume-yes-for-downloads ^
--enable-plugin=tk-inter ^
--output-dir="%OUTPUT_DIR%" ^
--output-filename="%OUTPUT_NAME%" ^
--windows-icon-from-ico="%ICON_FILE%" ^
--windows-console-mode=disable ^
--jobs=4 ^
--remove-output ^
--lto=no ^
--include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
--nofollow-import-to=configobj ^
--nofollow-import-to=tqdm ^
--nofollow-import-to=chardet ^
--nofollow-import-to=ta_lib ^
--nofollow-import-to=pandas_ta ^
--nofollow-import-to=tushare ^
--nofollow-import-to=lxml ^
--nofollow-import-to=aiohttp ^
--nofollow-import-to=screeninfo ^
--nofollow-import-to=PyQt5 ^
--nofollow-import-to=pyqtgraph ^
--nofollow-import-to=prompt_toolkit ^
"%MAIN_SCRIPT%"

echo ==========================================
echo 🔬 PRE-FLIGHT COMPILER DRY RUN (Takes ~2s)
echo ==========================================
echo pass > "%TEMP%\_nuitka_dry_run.py"
%PYTHON_EXEC% -m nuitka --show-scons --clang --remove-output "%TEMP%\_nuitka_dry_run.py"
if errorlevel 1 (
    echo.
    echo ❌ [FATAL ERROR] Pre-flight failed! Could not compile properly.
    pause
    exit /b
)
echo.
echo ✅ Pre-flight compiler check passed! (Check the logs above for 'clang' execution details)
echo.

echo ==========================================
echo 🚀 BUILD START
echo ==========================================
echo.

call %CMD%

:: =========================================
:: 7. RESULT
:: =========================================
if exist "%OUTPUT_DIR%\%OUTPUT_NAME%" (
    echo.
    echo ✅ BUILD SUCCESS
    echo 📦 OUTPUT READY
) else (
    echo ❌ BUILD FAILED
)

:: =========================================
:: 8. RESTORE
:: =========================================
set "PATH=%OLD_PATH%"
echo.
echo 🔄 PATH restored
echo.
pause
exit /b