@echo off
title 🧠 Nuitka 智能编译助手 (修正版)
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==========================================
echo 🧩 Nuitka 智能编译助手 (修正版)
echo ==========================================
echo.

:: 1️⃣ 备份原 PATH
set "OLD_PATH=%PATH%"

echo 🧭 检查当前 gcc / sh 路径 ...
where gcc
where sh
echo.

:: 2️⃣ 清理干扰路径
set "NEED_CLEAN=0"

for %%P in (
    C:\Users\Johnson\anaconda3\Library\usr\bin
    C:\Users\Johnson\anaconda3\Library\mingw-w64\bin
    "C:\Program Files\Git\cmd"
    C:\Users\Johnson\scoop\shims
) do (
    echo !PATH! | findstr /I "%%~P" >nul
    if not errorlevel 1 (
        echo ⚠️ 检测到冲突路径: %%~P
        set "NEED_CLEAN=1"
    )
)

if "%NEED_CLEAN%"=="1" (
    echo 🚿 正在清理干扰路径...
    set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\usr\bin;=%"
    set "PATH=%PATH:C:\Users\Johnson\anaconda3\Library\mingw-w64\bin;=%"
    set "PATH=%PATH:C:\Program Files\Git\cmd;=%"
    set "PATH=%PATH:C:\Users\Johnson\scoop\shims;=%"
) else (
    echo ✅ 未检测到冲突路径。
)

:: 3️⃣ 添加编译工具路径
echo 🧱 添加编译工具路径...
set "PATH=D:\mingw64\bin;%PATH%"
echo ✅ 当前 PATH 已准备好。
echo.

:: 4️⃣ 设置临时目录
echo 🗂️ 设置临时目录为 C:\Temp ...
set TEMP=C:\Temp
set TMP=C:\Temp
set CC_VERSION=13.2.0
echo ✅ TEMP 和 TMP 已设置为 %TEMP%

:: 4️⃣ 检查编译器
where gcc >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 gcc，请检查 D:\mingw64\bin 是否存在。
    pause
    exit /b
)

where sh >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%S in ('where sh') do (
        echo ⚠️ 检测到 sh.exe 来自：%%S
        echo 🚫 暂时移除 scoop 的 sh，防止干扰 Nuitka。
        set "PATH=%PATH:C:\Users\Johnson\scoop\shims;=%"
    )
)
echo.

:: ===== 配置区 =====
set MAIN_SCRIPT=instock_MonitorTK.py
set OUTPUT_NAME=instock_MonitorTK_Nuita.exe
set OUTPUT_DIR=build
set ICON_FILE=MonitorTK.ico
set PATH=C:\JohnsonProgram\SetDisplayMode\init\upx;%PATH%

echo 🏗️ 检查 Python 环境
:: 检测是否在虚拟环境
if defined VIRTUAL_ENV (
    echo ✅ 虚拟环境检测到: %VIRTUAL_ENV%
    set PYTHON_EXEC=%VIRTUAL_ENV%\Scripts\python.exe
) else (
    echo ⚠️ 未检测到虚拟环境，使用系统 Python
    set PYTHON_EXEC=python
)

:: ===== 获取动态 CSV 路径 =====
for /f "usebackq delims=" %%i in (`%PYTHON_EXEC% -c "import os, a_trade_calendar; print(os.path.join(os.path.dirname(a_trade_calendar.__file__), 'a_trade_calendar.csv'))"`) do set CSV_PATH=%%i

if not exist "%CSV_PATH%" (
    echo ❌ 未找到 CSV 文件: %CSV_PATH%
    pause
    exit /b
)
echo ✅ 动态获取 CSV 路径: %CSV_PATH%
echo.

:: ===== 创建输出目录 =====
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"
rem --windows-console-mode=disable ^
rem --lto=yes ^

rem :: ===== 构建 Nuitka 命令 =====
rem set CMD="%PYTHON_EXEC%" -m nuitka --standalone --onefile "%MAIN_SCRIPT%" ^

rem --plugin-enable=upx ^
rem --upx-binary="C:\JohnsonProgram\SetDisplayMode\init\upx.exe" ^   

set CMD="%PYTHON_EXEC%" -m nuitka --onefile "%MAIN_SCRIPT%" ^
    --output-filename="%OUTPUT_NAME%" ^
    --output-dir="%OUTPUT_DIR%" ^
    --enable-plugin=tk-inter ^
    --include-module=talib.stream ^
    --include-module=talib.abstract ^
    --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
    --include-data-file=MonitorTK.ico=MonitorTK.ico ^
    --include-data-file=window_config.json=window_config.json ^
    --include-data-file=webTools\window_manager\window_layout_config.json=webTools\window_manager\window_layout_config.json ^
    --include-data-file=scale2_window_config.json=scale2_window_config.json ^
    --include-data-file=monitor_category_list.json=monitor_category_list.json ^
    --include-data-file=visualizer_layout.json=visualizer_layout.json ^
    --include-data-file=voice_alert_config.json=voice_alert_config.json ^
    --include-data-file=macro_trends.json=macro_trends.json ^
    --include-data-file=intraday_pattern_config.json=intraday_pattern_config.json ^
    --include-data-file=display_cols.json=display_cols.json ^
    --include-data-file=datacsv\search_history.json=datacsv\search_history.json ^
    --include-data-file=JSONData\stock_codes.conf=JSONData\stock_codes.conf ^
    --include-data-file=JSONData\count.ini=JSONData\count.ini ^
    --include-data-file=JohnsonUtil\global.ini=JohnsonUtil\global.ini ^
    --include-data-file=JohnsonUtil\wencai\同花顺板块行业.xlsx=JohnsonUtil\wencai\同花顺板块行业.xlsx ^
    --windows-icon-from-ico=MonitorTK.ico ^
    --windows-company-name="Johnson QuantLab" ^
    --windows-product-name=instock_MonitorTK ^
    --windows-file-version="1.0.0" ^
    --windows-product-version="1.0.0" ^
    --windows-console-mode=force ^
    --lto=yes ^
    --jobs=8 ^
    --remove-output



rem set CMD="%PYTHON_EXEC%" -m nuitka --onefile "%MAIN_SCRIPT%" ^
rem     --output-filename="%OUTPUT_NAME%" ^
rem     --output-dir="%OUTPUT_DIR%" ^
rem     --enable-plugin=tk-inter ^
rem     --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
rem     --windows-icon-from-ico="%ICON_FILE%" ^
rem     --windows-company-name="Johnson QuantLab" ^
rem     --windows-product-name="instock_MonitorTK" ^
rem     --windows-file-version="1.0.0" ^
rem     --windows-product-version="1.0.0" ^
rem     --windows-console-mode=disable ^
rem     --lto=yes ^
rem     --jobs=8 ^
rem     --remove-output

rem :: =====debug 构建 Nuitka 命令 =====
rem set CMD="%PYTHON_EXEC%" -m nuitka --standalone "%MAIN_SCRIPT%" ^
rem     --output-filename="%OUTPUT_NAME%" ^
rem     --output-dir="%OUTPUT_DIR%" ^
rem     --enable-plugin=tk-inter ^
rem     --include-data-file="%CSV_PATH%=a_trade_calendar\a_trade_calendar.csv" ^
rem     --windows-icon-from-ico="%ICON_FILE%" ^
rem     --windows-company-name="Johnson QuantLab" ^
rem     --windows-product-name="异动联动" ^
rem     --windows-file-version="1.0.0" ^
rem     --windows-product-version="1.0.0" ^
rem     --jobs=10 ^
rem     --remove-output


:: ===== 执行编译 =====
echo 🏗️ 正在执行 Nuitka 编译...
echo !CMD!
echo.
!CMD!

:: ===== 完成检查 =====
if exist "%OUTPUT_DIR%\%OUTPUT_NAME%" (
    echo.
    echo ✅ 编译成功！
    echo 📦 输出路径：%OUTPUT_DIR%\%OUTPUT_NAME%
) else (
    echo ❌ 编译失败，请检查错误日志。
)


:: 6️⃣ 恢复原 PATH
set "PATH=%OLD_PATH%"
rem echo 🔄 已恢复原始 PATH。
echo 已恢复原始 PATH。
echo.

rem pause
exit /b
