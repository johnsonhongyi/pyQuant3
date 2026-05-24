@echo off
title Nuitka Smart Compiler Assistant - Console Mode
chcp 65001 >nul
setlocal enabledelayedexpansion

:: =========================================
:: START TIME RECORDING
:: =========================================
for /f "usebackq delims=" %%i in (`python -c "import time; print(time.time())"`) do set "START_TIME=%%i"
for /f "usebackq delims=" %%i in (`python -c "import time; print(time.strftime('%%Y-%%m-%%d %%H:%%M:%%S'))"`) do set "START_TIME_STR=%%i"
echo [INFO] Build started at: %START_TIME_STR%
echo.

echo ==========================================
echo Nuitka Smart Compiler Assistant (Console Mode)
echo ==========================================
echo.

:: 1. Backup original PATH
set "OLD_PATH=%PATH%"

echo Checking current gcc / sh paths...
where gcc
where sh
echo.

:: 2. Clean conflicting paths to prevent Nuitka compile failures
set "NEED_CLEAN=0"

for %%P in (
    C:\Users\Johnson\anaconda3\Library\usr\bin
    C:\Users\Johnson\anaconda3\Library\mingw-w64\bin
    "C:\Program Files\Git\cmd"
    C:\Users\Johnson\scoop\shims
) do (
    echo !PATH! | findstr /I "%%~P" >nul
    if not errorlevel 1 (
        echo [WARNING] Conflicting path detected: %%~P
        set "NEED_CLEAN=1"
    )
)

if "%NEED_CLEAN%"=="1" (
    echo [INFO] Cleaning conflicting paths...
    set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\usr\bin;=%"
    set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\mingw-w64\bin;=%"
    set "PATH=%PATH:C:\Program Files\Git\cmd;=%"
    set "PATH=%PATH:C:\Users\Johnson\scoop\shims;=%"
) else (
    echo [SUCCESS] No conflicting paths detected.
)

:: 3. Configure sccache & Setup Mingw64 GCC Compiler
echo Configuring sccache...
set SCCACHE_DIR=D:\sccache
set SCCACHE_CACHE_SIZE=50G

set "PATH=C:\Users\Johnson\scoop\apps\sccache\current;%PATH%"

echo [INFO] Compiler set to sccache gcc
set CC=sccache gcc
set CXX=sccache g++

set "PATH=D:\mingw64\bin;%PATH%"

rem Check GCC fallback
where gcc >nul 2>&1
if errorlevel 1 (
    echo [ERROR] gcc not found, please check if D:\mingw64\bin exists
    pause
    exit /b
)
echo.

:: 4. Set temporary directory and build cache
echo [INFO] Setting temp directory to C:\Temp and configuring Nuitka cache...
set TEMP=C:\Temp
set TMP=C:\Temp
set NUITKA_CACHE_DIR=%~dp0.nuitka_cache\release
set CC_VERSION=13.2.0
echo [SUCCESS] TEMP=%TEMP%, TMP=%TMP%, NUITKA_CACHE_DIR=%NUITKA_CACHE_DIR%

where sh >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%S in ('where sh') do (
        echo [WARNING] sh.exe detected from: %%S
        echo [WARNING] Temporarily removing scoop sh to avoid interfering with Nuitka.
        set "PATH=%PATH:C:\Users\Johnson\scoop\shims;=%"
    )
)
echo.

:: ===== Configuration =====
set MAIN_SCRIPT=instock_MonitorTK.py
set OUTPUT_NAME=instock_MonitorTK_Nuita.exe
set OUTPUT_DIR=build
set ICON_FILE=MonitorTK.ico
set PATH=C:\JohnsonProgram\SetDisplayMode\init\upx;%PATH%

echo Checking Python environment...
:: Check if virtual environment is active
if defined VIRTUAL_ENV (
    echo [SUCCESS] Virtual environment detected: %VIRTUAL_ENV%
    set PYTHON_EXEC=%VIRTUAL_ENV%\Scripts\python.exe
@REM ) else if defined CONDA_PREFIX (
@REM     echo [SUCCESS] Conda environment detected: %CONDA_PREFIX%
@REM     set PYTHON_EXEC=%CONDA_PREFIX%\python.exe
) else (
    echo [WARNING] No virtual environment detected, using system Python
    set PYTHON_EXEC=python
)

:: ===== Get dynamic CSV path =====
for /f "usebackq delims=" %%i in (`%PYTHON_EXEC% -c "import os, a_trade_calendar; print(os.path.join(os.path.dirname(a_trade_calendar.__file__), 'a_trade_calendar.csv'))"`) do set CSV_PATH=%%i

if not exist "%CSV_PATH%" (
    echo [ERROR] CSV file not found: %CSV_PATH%
    pause
    exit /b
)
echo [SUCCESS] Dynamically retrieved CSV path: %CSV_PATH%
echo.

:: ===== Create output directory =====
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"


set CMD="%PYTHON_EXEC%" -m nuitka --standalone "%MAIN_SCRIPT%" ^
    --output-filename="%OUTPUT_NAME%" ^
    --assume-yes-for-downloads ^
    --enable-plugin=tk-inter ^
    --enable-plugin=pyqt6 ^
    --windows-console-mode=force ^
    --windows-icon-from-ico="%ICON_FILE%" ^
    --windows-company-name="Johnson QuantLab" ^
    --windows-product-name="instock_MonitorTK" ^
    --windows-file-version="1.0.0" ^
    --windows-product-version="1.0.0" ^
    --output-dir="%OUTPUT_DIR%" ^
    --lto=no ^
    --no-pyi-file ^
    --jobs=8 ^
    --nofollow-import-to=scipy ^
    --nofollow-import-to=matplotlib ^
    --nofollow-import-to=tkinter.test ^
    --nofollow-import-to=numpy.testing ^
    --nofollow-import-to=pandas.tests ^
    --nofollow-import-to=tables.tests ^
    --nofollow-import-to=tables.nodes.tests ^
    --nofollow-import-to=numpy.tests ^
    --nofollow-import-to=PyQt6.QtWebEngineCore ^
    --nofollow-import-to=PyQt6.QtWebEngineWidgets ^
    --nofollow-import-to=PyQt6.QtQuick ^
    --nofollow-import-to=PyQt6.QtQml ^
    --nofollow-import-to=PyQt6.QtPdf ^
    --nofollow-import-to=PyQt6.QtVirtualKeyboard ^
    --nofollow-import-to=PyQt6.QtMultimedia ^
    --nofollow-import-to=PyQt6.QtBluetooth ^
    --nofollow-import-to=PyQt6.QtNetwork ^
    --nofollow-import-to=PyQt6.QtSvg ^
    --nofollow-import-to=PyQt6.QtSql ^
    --nofollow-import-to=PyQt6.QtTest ^
    --nofollow-import-to=PyQt6.QtXml ^
    --nofollow-import-to=IPython ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=numba ^
    --nofollow-import-to=llvmlite ^
    --noinclude-dlls=Qt6WebEngineCore.dll ^
    --noinclude-dlls=Qt6WebEngineWidgets.dll ^
    --noinclude-dlls=Qt6Pdf.dll ^
    --noinclude-dlls=Qt6Quick.dll ^
    --noinclude-dlls=Qt6Qml.dll ^
    --noinclude-dlls=Qt6VirtualKeyboard.dll ^
    --noinclude-dlls=Qt6Multimedia.dll ^
    --noinclude-dlls=Qt6Bluetooth.dll ^
    --noinclude-dlls=Qt6Network.dll ^
    --noinclude-dlls=Qt6Svg.dll ^
    --noinclude-dlls=Qt6Sql.dll ^
    --noinclude-dlls=Qt6Test.dll ^
    --noinclude-dlls=Qt6Xml.dll ^
    --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
    --include-data-file=MonitorTK.ico=MonitorTK.ico ^
    --include-data-file=window_config.json=window_config.json ^
    --include-data-file=global.ini=global.ini ^
    --include-data-file=scale2_window_config.json=scale2_window_config.json ^
    --include-data-file=monitor_category_list.json=monitor_category_list.json ^
    --include-data-file=visualizer_layout.json=visualizer_layout.json ^
    --include-data-file=voice_alert_config.json=voice_alert_config.json ^
    --include-data-file=macro_trends.json=macro_trends.json ^
    --include-data-file=display_cols.json=display_cols.json ^
    --include-data-file=intraday_pattern_config.json=intraday_pattern_config.json ^
    --include-data-file=datacsv\search_history.json=datacsv\search_history.json ^
    --include-data-file=datacsv\minute_kline_viewer_history.json=datacsv\minute_kline_viewer_history.json ^
    --include-data-file=JSONData\stock_codes.conf=JSONData\stock_codes.conf ^
    --include-data-file=JSONData\count.ini=JSONData\count.ini ^
    --include-data-file=JohnsonUtil\global.ini=JohnsonUtil\global.ini ^
    --include-data-file=JohnsonUtil\wencai\同花顺板块行业.xlsx=JohnsonUtil\wencai\同花顺板块行业.xlsx ^
    --include-package=a_trade_calendar ^
    --include-package=pyttsx3 ^
    --include-package=tables ^
    --include-package=tk_gui_modules ^
    --include-module=JSONData.tdx_hdf5_api ^
    --include-module=JSONData.wencaiData ^
    --include-module=JSONData.sina_data ^
    --include-module=JohnsonUtil.johnson_cons ^
    --include-module=configobj ^
    --include-module=tushare ^
    --include-module=pandas_ta ^
    --include-module=talib.stream ^
    --include-module=talib.abstract ^
    --include-module=stock_live_strategy ^
    --include-module=realtime_data_service ^
    --include-module=market_pulse_engine ^
    --include-module=signal_dashboard_panel ^
    --include-module=tables._comp_lzo ^
    --include-module=tables._comp_bzip2 ^
    --include-module=bidding_racing_panel ^
    --include-module=bidding_momentum_detector ^
    --include-module=market_pulse_viewer ^
    --include-module=sector_bidding_panel ^
    --include-module=stock_selector ^
    --include-module=trading_hub ^
    --include-module=signal_grading_hub ^
    --include-module=sector_focus_engine ^
    --include-module=scraper_55188 ^
    --include-module=backtest_feature_auditor ^
    --include-module=intraday_decision_engine ^
    --include-module=position_phase_engine ^
    --include-module=daily_top_detector ^
    --include-module=trading_analyzerQt6 ^
    --include-module=minute_kline_viewer_qt ^
    --include-module=live_signal_viewer ^
    --include-module=stock_selection_window ^
    --include-module=kline_monitor ^
    --include-module=db_repair_tool ^
    --include-module=cleanup_non_trading_signals ^
    --include-module=test_bidding_replay ^
    --include-module=signal_bus ^
    --include-module=keyboard ^
    --include-module=tkcalendar ^
    --include-module=psutil ^
    --include-module=tk_gil_monitor


:: ===== Execute compilation =====
echo ==========================================
echo [INFO] Executing Nuitka compilation...
echo ==========================================
echo !CMD!
echo.
!CMD!

:: ===== Verification =====
if exist "%OUTPUT_DIR%\instock_MonitorTK.dist\%OUTPUT_NAME%" (
    echo.
    echo [SUCCESS] Compilation completed successfully!
    echo [SUCCESS] Output directory: %OUTPUT_DIR%\instock_MonitorTK.dist
) else (
    echo [ERROR] Compilation failed. Please check the error logs.
)

:: ===== Calculate and Record Elapsed Time =====
for /f "usebackq delims=" %%i in (`python -c "import time; print(time.time())"`) do set "END_TIME=%%i"
for /f "usebackq delims=" %%i in (`python -c "import time; print(time.strftime('%%Y-%%m-%%d %%H:%%M:%%S'))"`) do set "END_TIME_STR=%%i"

for /f "usebackq delims=" %%i in (`python -c "import time; elapsed = %END_TIME% - %START_TIME%; m, s = divmod(elapsed, 60); h, m = divmod(m, 60); print('{:02d}:{:02d}:{:02d} ({:.2f}s)'.format(int(h), int(m), int(s), elapsed))"`) do set "ELAPSED_TIME=%%i"

echo ==========================================
echo 🕒 Build Time Summary:
echo Start Time:    %START_TIME_STR%
echo End Time:      %END_TIME_STR%
echo Elapsed Time:  %ELAPSED_TIME%
echo ==========================================

:: Persist to time.txt
(
echo ==========================================
echo Build Date:    %START_TIME_STR%
echo Start Time:    %START_TIME_STR%
echo End Time:      %END_TIME_STR%
echo Elapsed Time:  %ELAPSED_TIME%
echo ==========================================
) >> "%~dp0time.txt"

:: 6. Restore original PATH
set "PATH=%OLD_PATH%"
echo Original PATH has been restored.
echo.

exit /b
