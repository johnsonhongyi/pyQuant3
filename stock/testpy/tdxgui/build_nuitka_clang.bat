@echo off
title Nuitka 异动联动 本地极速构建助手
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo Nuitka 异动联动 本地极速构建 (Local MinGW + Cache)
echo ==========================================
echo.

set "DRY_RUN=0"
if /i "%~1"=="--dry-run" set "DRY_RUN=1"
if /i "%~2"=="--dry-run" set "DRY_RUN=1"

rem 1. 备份原 PATH
set "OLD_PATH=%PATH%"

rem 2. 清理可能干扰 Scons 的 sh.exe (如 scoop, Git sh 等)
set "PATH=%PATH:C:\Program Files\Git\bin;=%"
set "PATH=%PATH:C:\Program Files\Git\usr\bin;=%"
set "PATH=%PATH:<USER_HOME>\scoop\shims;=%"
set "PATH=%PATH:<USER_HOME>\anaconda3\Library\usr\bin;=%"
set "PATH=%PATH:<USER_HOME>\anaconda3\Library\mingw-w64\bin;=%"

rem 3. 智能解析本地已存在的 GCC/MinGW 编译器 (零下载、秒级命中)
set "LOCAL_GCC_DIR="
if exist "E:\Program\LocalTemp\Nuitka\Nuitka\Cache\downloads\gcc\x86_64\14.2.0posix-19.1.1-12.0.0-msvcrt-r2\mingw64\bin\gcc.exe" (
    set "LOCAL_GCC_DIR=E:\Program\LocalTemp\Nuitka\Nuitka\Cache\downloads\gcc\x86_64\14.2.0posix-19.1.1-12.0.0-msvcrt-r2\mingw64\bin"
    echo [SUCCESS] Local Nuitka-Dedicated GCC 14.2.0 resolved: !LOCAL_GCC_DIR!
) else if exist "%LOCALAPPDATA%\Nuitka\Nuitka\Cache\downloads\gcc\x86_64\14.2.0posix-19.1.1-12.0.0-msvcrt-r2\mingw64\bin\gcc.exe" (
    set "LOCAL_GCC_DIR=%LOCALAPPDATA%\Nuitka\Nuitka\Cache\downloads\gcc\x86_64\14.2.0posix-19.1.1-12.0.0-msvcrt-r2\mingw64\bin"
    echo [SUCCESS] AppData Nuitka-Dedicated GCC 14.2.0 resolved: !LOCAL_GCC_DIR!
) else if exist "D:\mingw64\bin\gcc.exe" (
    set "LOCAL_GCC_DIR=D:\mingw64\bin"
    echo [SUCCESS] Standalone System GCC resolved: !LOCAL_GCC_DIR!
)

if defined LOCAL_GCC_DIR (
    set "PATH=!LOCAL_GCC_DIR!;!PATH!"
)

where gcc >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No local GCC compiler found! Please check D:\mingw64\bin.
    pause
    exit /b 1
)
for /f "delims=" %%g in ('where gcc') do (
    echo [SUCCESS] Active C Compiler: %%g
    goto :gcc_checked
)
:gcc_checked
echo.

rem 4. 共享复用本地编译与工具链缓存 (完全复用本地 ccache/downloads，杜绝重复下载)
set "TEMP=C:\Temp"
set "TMP=C:\Temp"
if not exist "C:\Temp" mkdir "C:\Temp" >nul 2>&1

set "NUITKA_CACHE_DIR="
if exist "E:\Program\LocalTemp\Nuitka\Nuitka\Cache" (
    set "NUITKA_CACHE_DIR=E:\Program\LocalTemp\Nuitka\Nuitka\Cache"
) else (
    set "NUITKA_CACHE_DIR=%LOCALAPPDATA%\Nuitka\Nuitka\Cache"
)
echo [SUCCESS] TEMP=%TEMP%, NUITKA_CACHE_DIR=%NUITKA_CACHE_DIR%
echo.

rem 5. Python 环境检测 (优先 nuitka_env 与 tk_nuitka_env)
set "PYTHON_EXEC="
if exist "%USERPROFILE%\anaconda3\envs\nuitka_env\python.exe" (
    set "PYTHON_EXEC=%USERPROFILE%\anaconda3\envs\nuitka_env\python.exe"
    echo [SUCCESS] Dedicated Nuitka environment detected: %USERPROFILE%\anaconda3\envs\nuitka_env
) else if exist "%USERPROFILE%\anaconda3\envs\tk_nuitka_env\python.exe" (
    set "PYTHON_EXEC=%USERPROFILE%\anaconda3\envs\tk_nuitka_env\python.exe"
    echo [SUCCESS] Dedicated Nuitka environment detected: %USERPROFILE%\anaconda3\envs\tk_nuitka_env
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set "PYTHON_EXEC=%%i"
        goto :py_resolved
    )
)

:py_resolved
if not defined PYTHON_EXEC (
    echo [ERROR] Python executable not found!
    pause
    exit /b 1
)

rem 6. 项目配置与命名对齐 (Nuitka 专享 _Nuitka 后缀，避免覆盖 PyInstaller 版本)
set "MAIN_SCRIPT=异动联动.py"
set "OUTPUT_NAME=异动联动_Nuitka.exe"
set "OUTPUT_DIR=build"
set "ICON_FILE=app.ico"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%" >nul 2>&1

rem 7. 动态安全获取 CSV 路径 (交易日历)
set "CSV_PATH="
set "CSV_CAPTURE=%TEMP%\_csv_path_%RANDOM%.txt"
"%PYTHON_EXEC%" -c "import os, a_trade_calendar; print(os.path.join(os.path.dirname(a_trade_calendar.__file__), 'a_trade_calendar.csv'))" > "%CSV_CAPTURE%" 2>nul
if exist "%CSV_CAPTURE%" (
    set /p CSV_PATH=<"%CSV_CAPTURE%"
    del /f /q "%CSV_CAPTURE%" >nul 2>&1
)

if not defined CSV_PATH (
    echo [ERROR] Could not resolve a_trade_calendar.csv.
    pause
    exit /b 1
)
if not exist "%CSV_PATH%" (
    echo [ERROR] CSV file not found: %CSV_PATH%
    pause
    exit /b 1
)
echo [SUCCESS] Dynamically retrieved CSV path: %CSV_PATH%
echo.

rem 8. 智能编译优化插件检查 (跳过第三方大包的 C 编译，极大缩短构建时间)
set "SMART_OPT_PLUGIN=D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\tools\nuitka_smart_optimizer_plugin.py"
set "PLUGIN_ARG="
if exist "!SMART_OPT_PLUGIN!" (
    echo [SUCCESS] Nuitka Smart Optimizer Plugin detected: !SMART_OPT_PLUGIN!
    set PLUGIN_ARG=--user-plugin="!SMART_OPT_PLUGIN!" --no-deployment-flag=excluded-module-usage
) else (
    echo [INFO] Smart Optimizer Plugin not found, proceeding standard mode.
)

rem 9. 额外数据文件检查 (globalYD.ini, code_ths_other.json, window_config.json, query_history.json, linkage_config.json, app.ico)
rem 注意: 绝对不要通过 --include-data-file 手动添加 DLL (如 sqlite3.dll, libcrypto*.dll, libssl*.dll)
rem 否则会与 Nuitka 内置的 dll-files 插件发生 'conflicts with dll' 冲突崩溃！
set "EXTRA_DATA_ARGS="
if exist "globalYD.ini" (
    set EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --include-data-file=globalYD.ini=globalYD.ini
)
if exist "code_ths_other.json" (
    set EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --include-data-file=code_ths_other.json=code_ths_other.json
)
if exist "window_config.json" (
    set EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --include-data-file=window_config.json=window_config.json
)
if exist "query_history.json" (
    set EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --include-data-file=query_history.json=query_history.json
)
if exist "linkage_config.json" (
    set EXTRA_DATA_ARGS=!EXTRA_DATA_ARGS! --include-data-file=linkage_config.json=linkage_config.json
)
set "ICON_ARG="
if exist "%ICON_FILE%" (
    set ICON_ARG=--windows-icon-from-ico="%ICON_FILE%"
)

rem 10. 构建 Nuitka 编译命令 (恢复 tables/HDF5 数据管道，优化 OpenSSL 与核心模块)
set CMD="%PYTHON_EXEC%" -m nuitka ^
    --onefile ^
    --onefile-tempdir-spec="{TEMP}\stockAlerts_Nuitka" ^
    --assume-yes-for-downloads ^
    --enable-plugin=tk-inter ^
    --windows-console-mode=disable ^
    !ICON_ARG! ^
    --windows-company-name="Johnson QuantLab" ^
    --windows-product-name="异动联动_Nuitka" ^
    --windows-file-version="1.0.0" ^
    --windows-product-version="1.0.0" ^
    --output-dir="%OUTPUT_DIR%" ^
    --output-filename="%OUTPUT_NAME%" ^
    --lto=no ^
    --jobs=8 ^
    --python-flag=no_asserts ^
    !PLUGIN_ARG! ^
    --nofollow-import-to=scipy ^
    --nofollow-import-to=matplotlib ^
    --nofollow-import-to=PyQt5 ^
    --nofollow-import-to=PyQt6 ^
    --nofollow-import-to=PySide2 ^
    --nofollow-import-to=PySide6 ^
    --nofollow-import-to=pyqtgraph ^
    --nofollow-import-to=IPython ^
    --nofollow-import-to=notebook ^
    --nofollow-import-to=jedi ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=bokeh ^
    --nofollow-import-to=seaborn ^
    --nofollow-import-to=flask ^
    --nofollow-import-to=django ^
    --nofollow-import-to=sqlalchemy ^
    --nofollow-import-to=zmq ^
    --nofollow-import-to=tornado ^
    --nofollow-import-to=pytest ^
    --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
    !EXTRA_DATA_ARGS! ^
    --include-package=tables ^
    --include-module=tables._comp_lzo ^
    --include-module=tables._comp_bzip2 ^
    --include-module=filelock ^
    --include-module=_ssl ^
    --include-module=_hashlib ^
    --include-package=a_trade_calendar ^
    "%MAIN_SCRIPT%"

rem 11. 演练模式 (--dry-run) 支持
if "!DRY_RUN!"=="1" (
    echo ==========================================================
    echo [DRY-RUN 演练] 模拟命令生成完毕 [不执行实际编译]
    echo !CMD!
    echo ==========================================================
    set "PATH=%OLD_PATH%"
    exit /b 0
)

rem 12. 归档历史旧版本 (保留最近 7 天)
set "ARCHIVE_DIR=%OUTPUT_DIR%\archive"
if not exist "%ARCHIVE_DIR%" mkdir "%ARCHIVE_DIR%" >nul 2>&1
if exist "%OUTPUT_DIR%\%OUTPUT_NAME%" (
    set "TS_NOW=%DATE:~0,4%%DATE:~5,2%%DATE:~8,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
    set "TS_NOW=!TS_NOW: =0!"
    copy /y "%OUTPUT_DIR%\%OUTPUT_NAME%" "%ARCHIVE_DIR%\异动联动_Nuitka_!TS_NOW!.exe" >nul 2>&1
    echo [INFO] Archived previous build to %ARCHIVE_DIR%
)

rem 13. 执行正式编译
echo ==========================================
echo BUILD START: %OUTPUT_NAME%
echo ==========================================
echo !CMD!
echo.
call !CMD!
set "BUILD_RESULT=!ERRORLEVEL!"

rem 14. 结果检查与收尾
echo.
echo ==========================================
if exist "%OUTPUT_DIR%\%OUTPUT_NAME%" (
    echo [SUCCESS] BUILD SUCCESS!
    echo Target Executable: %OUTPUT_DIR%\%OUTPUT_NAME%
    set "BUILD_RESULT=0"
) else (
    echo [FAILED] BUILD FAILED!
    set "BUILD_RESULT=1"
)
echo ==========================================

set "PATH=%OLD_PATH%"
exit /b !BUILD_RESULT!
