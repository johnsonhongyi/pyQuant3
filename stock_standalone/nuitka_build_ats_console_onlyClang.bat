@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title ATS Nuitka Smart Compiler - Clang Only
chcp 65001 >nul

REM 可通过 ATS_PYTHON_EXEC 明确指定 ATS 构建环境；默认优先使用 tk_nuitka_env 专用环境。
if defined ATS_PYTHON_EXEC (
    set "PYTHON_EXEC=%ATS_PYTHON_EXEC%"
) else if defined VIRTUAL_ENV (
    set "PYTHON_EXEC=%VIRTUAL_ENV%\Scripts\python.exe"
) else if exist "C:\Users\Johnson\anaconda3\envs\tk_nuitka_env\python.exe" (
    echo [SUCCESS] Dedicated Nuitka environment detected: C:\Users\Johnson\anaconda3\envs\tk_nuitka_env
    set "PYTHON_EXEC=C:\Users\Johnson\anaconda3\envs\tk_nuitka_env\python.exe"
) else (
    set "PYTHON_EXEC=python"
)
"%PYTHON_EXEC%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found: %PYTHON_EXEC%
    goto :fail
)
"%PYTHON_EXEC%" -c "import sys, yaml; print('[INFO] Build Python: ' + sys.executable); print('[INFO] PyYAML: ' + yaml.__file__)"
if errorlevel 1 (
    echo [ERROR] Selected Python cannot import PyYAML package 'yaml'. ATS spec requires yaml submodules.
    echo [HINT] Set ATS_PYTHON_EXEC to the ATS environment Python, or install PyYAML in the selected environment.
    goto :fail
)

set "NUITKA_CACHE_DIR=%~dp0.nuitka_cache\ats_release"
if not exist "%NUITKA_CACHE_DIR%" mkdir "%NUITKA_CACHE_DIR%"
set "CAPTURE_FILE=%NUITKA_CACHE_DIR%\ats_capture_%RANDOM%_%RANDOM%.tmp"

"%PYTHON_EXEC%" -c "import time; print(time.time())" > "%CAPTURE_FILE%"
set /p START_TIME=<"%CAPTURE_FILE%"
"%PYTHON_EXEC%" -c "import time; print(time.strftime('%%Y-%%m-%%d %%H:%%M:%%S'))" > "%CAPTURE_FILE%"
set /p START_TIME_STR=<"%CAPTURE_FILE%"
echo [INFO] ATS build started at: %START_TIME_STR%

:: standalone 用于首次排查；默认 onefile_spec 与参考脚本保持一致。
set "BUILD_MODE=onefile_spec"
set "BUILD_MODE_ARG=%~1"
if /I "%BUILD_MODE_ARG%"=="onefile_spec" (
    set "BUILD_MODE=onefile_spec"
) else if /I "%BUILD_MODE_ARG%"=="onefile" (
    set "BUILD_MODE=onefile"
) else if /I "%BUILD_MODE_ARG%"=="standalone" (
    set "BUILD_MODE=standalone"
) else (
    echo.
    echo [1] Standalone folder
    echo [2] Onefile with fixed ATS temp directory ^(default^)
    echo [3] Onefile with unique temp directory
    choice /C 123 /T 5 /D 2 /M "Select build mode"
    if errorlevel 3 (
        set "BUILD_MODE=onefile"
    ) else if errorlevel 2 (
        set "BUILD_MODE=onefile_spec"
    ) else (
        set "BUILD_MODE=standalone"
    )
)

if "%BUILD_MODE%"=="onefile_spec" (
    set "NUITKA_MODE_OPT=--onefile --onefile-tempdir-spec="{TEMP}\ATS_Nuitka""
    echo [MODE] ATS onefile with fixed temp directory
) else if "%BUILD_MODE%"=="onefile" (
    set "NUITKA_MODE_OPT=--onefile"
    echo [MODE] ATS onefile
) else (
    set "NUITKA_MODE_OPT=--standalone"
    echo [MODE] ATS standalone folder
)

:: Keep the Clang-only compiler setup from the reference build script.
set "OLD_PATH=%PATH%"
set "VS_VARS=D:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"
if exist "%VS_VARS%" (
    echo [INFO] Loading Visual Studio x64 environment
    call "%VS_VARS%" >nul
)

for %%P in (
    C:\Users\Johnson\anaconda3\Library\usr\bin
    C:\Users\Johnson\anaconda3\Library\mingw-w64\bin
    "C:\Program Files\Git\cmd"
    C:\Users\Johnson\scoop\shims
) do (
    echo !PATH! | findstr /I "%%~P" >nul
    if not errorlevel 1 (
        set "PATH=!PATH:C:\Users\Johnson\anaconda3\Library\usr\bin;=!"
        set "PATH=!PATH:C:\Users\Johnson\anaconda3\Library\mingw-w64\bin;=!"
        set "PATH=!PATH:C:\Program Files\Git\cmd;=!"
        set "PATH=!PATH:C:\Users\Johnson\scoop\shims;=!"
    )
)

set "SCCACHE_DIR=%~dp0.nuitka_cache\ats_sccache"
set "SCCACHE_CACHE_SIZE=50G"
set "PATH=C:\Users\Johnson\scoop\apps\sccache\current;%PATH%"
where sccache >nul 2>&1
if not errorlevel 1 (
    sccache --start-server >nul 2>&1
)
:: Nuitka Windows Clang 模式通过 Scons 调用 clang-cl，由 Nuitka 原生内置 clcache 统一加速
if defined LOCALAPPDATA (
    set "CLCACHE_DIR=%LOCALAPPDATA%\Nuitka\Nuitka\Cache\clcache"
)
echo [INFO] Nuitka compiler cache: clcache enabled (Windows Clang-cl native)

set "CLANG_EXE="
if exist "C:\Users\Johnson\scoop\apps\llvm\current\bin\clang.exe" (
    set "CLANG_EXE=C:\Users\Johnson\scoop\apps\llvm\current\bin\clang.exe"
) else if exist "C:\Program Files\LLVM\bin\clang.exe" (
    set "CLANG_EXE=C:\Program Files\LLVM\bin\clang.exe"
) else (
    for /f "delims=" %%i in ('where clang 2^>nul') do if not defined CLANG_EXE set "CLANG_EXE=%%i"
)
if not defined CLANG_EXE (
    echo [ERROR] Clang not found; ATS build stopped.
    goto :fail
)
for %%A in ("!CLANG_EXE!") do set "LLVM_BIN=%%~dpA"
set "PATH=!LLVM_BIN!;!PATH!"
set "PATH=!PATH:D:\mingw64\bin;=!"
set "PATH=!PATH:D:\mingw64\bin=!"
set "PATH=!PATH:D:\mingw64;=!"
set "PATH=!PATH:D:\mingw64=!"
set "CC="
set "CXX="
set "NUITKA_CLANG_OPT=--clang"

where gcc >nul 2>&1
if not errorlevel 1 (
    echo [ERROR] GCC is still visible in PATH; strict Clang-only build stopped.
    where gcc
    goto :fail
)
echo [SUCCESS] Clang-only compiler: !CLANG_EXE!

set "TEMP=C:\Temp"
set "TMP=C:\Temp"
if not exist "C:\Temp" mkdir "C:\Temp"
if exist "C:\JohnsonProgram\SetDisplayMode\init\upx\upx.exe" set "PATH=C:\JohnsonProgram\SetDisplayMode\init\upx;%PATH%"

:: ATS entry point, output, and icon match ats.spec; aligned with TK and MultiPeriodTester builds in build\
set "MAIN_SCRIPT=run_ats.py"
set "OUTPUT_NAME=ATS_Terminal.exe"
set "OUTPUT_DIR=build"
set "ICON_FILE=MonitorTK32.ico"
set "PRODUCT_VERSION=1.0.0"

if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] ATS entry point not found: %MAIN_SCRIPT%
    goto :fail
)
if not exist "%ICON_FILE%" (
    echo [ERROR] ATS icon not found: %ICON_FILE%
    goto :fail
)
if not exist "MonitorTK.ico" (
    echo [ERROR] ATS runtime icon resource not found: MonitorTK.ico
    goto :fail
)

:: Resolve the trading calendar resource using the selected Python environment.
set "CSV_PATH="
"%PYTHON_EXEC%" -c "import os, a_trade_calendar; print(os.path.join(os.path.dirname(a_trade_calendar.__file__), 'a_trade_calendar.csv'))" > "%CAPTURE_FILE%" 2>nul
set /p CSV_PATH=<"%CAPTURE_FILE%"
if not defined CSV_PATH (
    echo [ERROR] Could not resolve a_trade_calendar.csv.
    goto :fail
)
if not exist "%CSV_PATH%" (
    echo [ERROR] Trading calendar file not found: %CSV_PATH%
    goto :fail
)

:: Fail early if a runtime data file required by ats.spec is missing.
for %%F in (
    "window_config.json"
    "strategy_config.json"
    "JSONData\stock_codes.conf"
    "JSONData\count.ini"
    "JohnsonUtil\global.ini"
    "config\vwap_trading_rules.json"
    "config\strategy_rules.json"
    "config\next_day_watch_strategies.json"
    "config\next_day_watch_columns.json"
    "config\multi_period_strategies.json"
    "config\multi_period_help.md"
    "config\intraday_newstock_strategies.json"
    "config\subnew_real_market_deployment.json"
    "config\new_stock_columns.json"
    "config\ipo_detector_columns.json"
    "config\ipo_detector_layout.json"
    "config\ipo_detector_ipc.json"
    "config\llm_config.yaml"
    "config\ipo_sentiment.yaml"
    "config\indicator_help_custom.json"
) do (
    if not exist "%%~F" (
        echo [ERROR] ATS runtime data required by ats.spec is missing: %%~F
        goto :fail
    )
)

if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

:: Runtime data mirrors ats.spec; ATS UI uses PyQt6 and does not bundle Tk.
set CMD="%PYTHON_EXEC%" -m nuitka !NUITKA_MODE_OPT! "%MAIN_SCRIPT%" ^
    --output-filename="%OUTPUT_NAME%" ^
    !NUITKA_CLANG_OPT! ^
    --assume-yes-for-downloads ^
    --enable-plugin=pyqt6 ^
    --enable-plugin=tk-inter ^
    --windows-console-mode=force ^
    --windows-icon-from-ico="%ICON_FILE%" ^
    --windows-company-name="Johnson QuantLab" ^
    --windows-product-name="ATS_Terminal" ^
    --windows-file-version="%PRODUCT_VERSION%" ^
    --windows-product-version="%PRODUCT_VERSION%" ^
    --output-dir="%OUTPUT_DIR%" ^
    --no-pyi-file ^
    --lto=no ^
    --jobs=8 ^
    --python-flag=no_asserts ^
    --nofollow-import-to=PyQt6.QtWebEngineCore ^
    --nofollow-import-to=PyQt6.QtWebEngineWidgets ^
    --nofollow-import-to=PyQt6.QtPdf ^
    --nofollow-import-to=PyQt6.QtQuick ^
    --nofollow-import-to=PyQt6.QtQml ^
    --nofollow-import-to=PyQt6.QtVirtualKeyboard ^
    --nofollow-import-to=PyQt6.QtMultimedia ^
    --nofollow-import-to=PyQt6.QtBluetooth ^
    --nofollow-import-to=PyQt6.QtPositioning ^
    --nofollow-import-to=PyQt6.QtSensors ^
    --nofollow-import-to=PyQt6.QtWebChannel ^
    --nofollow-import-to=PyQt6.QtWebSockets ^
    --nofollow-import-to=PyQt6.QtSql ^
    --nofollow-import-to=PyQt6.QtTest ^
    --nofollow-import-to=PyQt6.QtXml ^
    --nofollow-import-to=PyQt6.QtQuickWidgets ^
    --nofollow-import-to=PyQt6.QtQuick3D ^
    --nofollow-import-to=PyQt6.QtRemoteObjects ^
    --nofollow-import-to=PyQt5 ^
    --nofollow-import-to=PySide2 ^
    --nofollow-import-to=PySide6 ^
    --nofollow-import-to=matplotlib ^
    --nofollow-import-to=scipy ^
    --nofollow-import-to=jedi ^
    --nofollow-import-to=IPython ^
    --nofollow-import-to=notebook ^
    --nofollow-import-to=tkinter.test ^
    --nofollow-import-to=lxml ^
    --nofollow-import-to=cryptography ^
    --nofollow-import-to=win32ui ^
    --nofollow-import-to=numba ^
    --nofollow-import-to=llvmlite ^
    --nofollow-import-to=botocore ^
    --nofollow-import-to=boto3 ^
    --nofollow-import-to=trading_kernel.tests ^
    --nofollow-import-to=tables.tests ^
    --nofollow-import-to=tables.nodes.tests ^
    --nofollow-import-to=pandas.tests ^
    --nofollow-import-to=numpy.tests ^
    --nofollow-import-to=numpy.testing ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=doctest ^
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
    --noinclude-dlls=opengl32sw.dll ^
    --noinclude-dlls=mfc140u.dll ^
    --noinclude-dlls=mfc140.dll ^
    --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
    --include-data-file=MonitorTK.ico=MonitorTK.ico ^
    --include-data-file=window_config.json=window_config.json ^
    --include-data-file=strategy_config.json=strategy_config.json ^
    --include-data-file=JSONData\stock_codes.conf=JSONData\stock_codes.conf ^
    --include-data-file=JSONData\count.ini=JSONData\count.ini ^
    --include-data-file=JohnsonUtil\global.ini=JohnsonUtil\global.ini ^
    --include-data-file=config\vwap_trading_rules.json=config\vwap_trading_rules.json ^
    --include-data-file=config\strategy_rules.json=config\strategy_rules.json ^
    --include-data-file=config\next_day_watch_strategies.json=config\next_day_watch_strategies.json ^
    --include-data-file=config\next_day_watch_columns.json=config\next_day_watch_columns.json ^
    --include-data-file=config\multi_period_strategies.json=config\multi_period_strategies.json ^
    --include-data-file=config\multi_period_help.md=config\multi_period_help.md ^
    --include-data-file=config\intraday_newstock_strategies.json=config\intraday_newstock_strategies.json ^
    --include-data-file=config\subnew_real_market_deployment.json=config\subnew_real_market_deployment.json ^
    --include-data-file=config\new_stock_columns.json=config\new_stock_columns.json ^
    --include-data-file=config\ipo_detector_columns.json=config\ipo_detector_columns.json ^
    --include-data-file=config\ipo_detector_layout.json=config\ipo_detector_layout.json ^
    --include-data-file=config\ipo_detector_ipc.json=config\ipo_detector_ipc.json ^
    --include-data-file=config\llm_config.yaml=config\llm_config.yaml ^
    --include-data-file=config\ipo_sentiment.yaml=config\ipo_sentiment.yaml ^
    --include-data-file=config\indicator_help_custom.json=config\indicator_help_custom.json ^
    --include-module=a_trade_calendar ^
    --include-module=pandas ^
    --include-module=numpy ^
    --include-module=pyqtgraph ^
    --include-module=sqlite3 ^
    --include-module=sys_utils ^
    --include-module=db_utils ^
    --include-module=ats ^
    --include-module=ats.ipc_bridge ^
    --include-module=ats.universe_manager ^
    --include-module=ats.swing_tracker ^
    --include-module=ats.backtest_engine ^
    --include-module=ats.trade_journal ^
    --include-module=ats.ui.main_window ^
    --include-module=ats.ui.chart_widgets ^
    --include-module=ats.ui.universe_widget ^
    --include-module=ats.ui.heatmap_widget ^
    --include-module=ats.ui.swing_table ^
    --include-module=ats.ui.trade_flow ^
    --include-module=configobj ^
    --include-module=JSONData ^
    --include-module=JSONData.sina_data ^
    --include-package=tables ^
    --include-module=tables._comp_lzo ^
    --include-module=tables._comp_bzip2 ^
    --include-module=JSONData.tdx_hdf5_api ^
    --include-module=JSONData.realdatajson ^
    --include-module=JSONData.wencaiData ^
    --include-module=JSONData.tdxbk ^
    --include-module=JohnsonUtil.johnson_cons ^
    --include-module=tushare ^
    --include-module=pandas_ta ^
    --include-module=JohnsonUtil.commonTips ^
    --include-module=talib.stream ^
    --include-module=talib.abstract ^
    --include-module=run_sbc ^
    --include-module=run_ipo_detector ^
    --include-module=ats.ui.ipo_subnew_detector_dialog ^
    --include-module=ats.ui.ipo_detector_ipc ^
    --include-module=ats.strategy.ipo_vwap_detector_engine ^
    --include-module=ats.new_stock_fetcher ^
    --include-module=ats.strategy.ipo_data_contracts ^
    --include-module=ats.strategy.ipo_gate_context_provider ^
    --include-module=ats.strategy.ipo_outcome_labels ^
    --include-module=ats.strategy.ipo_trading_center ^
    --include-module=ats.strategy.gate_orchestrator ^
    --include-module=ats.llm.backend_factory ^
    --include-module=ats.next_day_watch_process ^
    --include-module=ats.bounded_evaluation_store ^
    --include-module=ats.archive_policy ^
    --include-module=ats.storage_archive ^
    --include-module=ats.llm.antigravity_cli_backend ^
    --include-module=ats.llm.codex_cli_backend ^
    --include-module=ats.llm.offline_learning ^
    --include-module=ats.ui.ipo_learning_console ^
    --include-package=trading_kernel ^
    --include-package=yaml

echo.
echo [INFO] Clang pre-flight check
set "PROBE_SCRIPT=%TEMP%\_ats_nuitka_clang_probe.py"
echo pass > "%PROBE_SCRIPT%"
"%PYTHON_EXEC%" -m nuitka --show-scons --clang --remove-output "%PROBE_SCRIPT%"
if errorlevel 1 (
    echo [ERROR] Clang pre-flight failed.
    del /q "%PROBE_SCRIPT%" >nul 2>&1
    goto :fail
)
del /q "%PROBE_SCRIPT%" >nul 2>&1

echo.
echo [INFO] Building ATS from %MAIN_SCRIPT%
echo [INFO] Runtime data and hidden imports follow ats.spec.
echo !CMD!
!CMD!
if errorlevel 1 goto :fail

if "%BUILD_MODE%"=="standalone" (
    if not exist "%OUTPUT_DIR%\ATS_Terminal.dist\%OUTPUT_NAME%" (
        echo [ERROR] ATS standalone output not found.
        goto :fail
    )
    echo [SUCCESS] ATS standalone output: %OUTPUT_DIR%\ATS_Terminal.dist
) else (
    if not exist "%OUTPUT_DIR%\%OUTPUT_NAME%" (
        echo [ERROR] ATS onefile output not found.
        goto :fail
    )
    echo [SUCCESS] ATS executable: %OUTPUT_DIR%\%OUTPUT_NAME%
)

"%PYTHON_EXEC%" -c "import time; print(time.time())" > "%CAPTURE_FILE%"
set /p END_TIME=<"%CAPTURE_FILE%"
"%PYTHON_EXEC%" -c "import time; print(time.strftime('%%Y-%%m-%%d %%H:%%M:%%S'))" > "%CAPTURE_FILE%"
set /p END_TIME_STR=<"%CAPTURE_FILE%"
"%PYTHON_EXEC%" -c "import time; elapsed=%END_TIME%-%START_TIME%; m,s=divmod(elapsed,60); h,m=divmod(m,60); print('{:02d}:{:02d}:{:02d} ({:.2f}s)'.format(int(h),int(m),int(s),elapsed))" > "%CAPTURE_FILE%"
set /p ELAPSED_TIME=<"%CAPTURE_FILE%"
echo [INFO] Build ended at: %END_TIME_STR%; elapsed %ELAPSED_TIME%
>> "%~dp0ats_nuitka_build_time.txt" echo ATS Build Date: %START_TIME_STR%
>> "%~dp0ats_nuitka_build_time.txt" echo End Time: %END_TIME_STR%
>> "%~dp0ats_nuitka_build_time.txt" echo Elapsed: %ELAPSED_TIME%
del /q "%CAPTURE_FILE%" >nul 2>&1
endlocal
exit /b 0

:fail
echo [ERROR] ATS Nuitka Clang build failed.
if defined CAPTURE_FILE del /q "%CAPTURE_FILE%" >nul 2>&1
pause
endlocal
exit /b 1
