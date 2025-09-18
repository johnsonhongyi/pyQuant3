@echo off
chcp 65001 >nul
echo 你好，世界
@echo off
REM ===================================================
REM pyQuant3 stock 启动脚本，保留原有逻辑，逐步运行
REM 第一个程序立即启动，后续依赖文件检测再顺序启动
REM ===================================================

REM 设置工作目录
D:
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock"
set WORKDIR=%CD%
echo 当前目录: %WORKDIR%

REM ============================
REM 启动第一个程序 sina_Monitor
REM ============================
if exist "%WORKDIR%\sina_Monitor.exe" (
    echo 启动 EXE: sina_Monitor.exe
    start cmd /k  "%WORKDIR%\sina_Monitor.exe"
) else if exist "%WORKDIR%\sina_Monitor.py" (
    echo 启动 Python: sina_Monitor.py
    start cmd /k  python "%WORKDIR%\sina_Monitor.py"
) else (
    echo ERROR: 找不到 sina_Monitor.exe 或 sina_Monitor.py
)

REM ============================
REM 等待依赖文件准备好
REM ============================
set TDX=G:\tdx_last_df.h5

:WAIT_TDX
if not exist "%TDX%" (
    echo 等待文件生成: %TDX%
    timeout /t 10 /nobreak >nul
    goto WAIT_TDX
)

for %%i in ("%TDX%") do set indexdx=%%~zi
if "%indexdx%"=="" set indexdx=4096

if not "%indexdx%"=="" if %indexdx% LEQ 4096000 (
    echo 文件大小 %indexdx% 不足，等待...
    timeout /t 10 /nobreak >nul
    goto WAIT_TDX
)
echo 文件准备就绪，大小: %indexdx%

REM ============================
REM 启动后续程序
REM ============================

REM 依次启动 exe 或 py 文件，保持延迟
set PROGRAMS=instock_Monitor singleAnalyseUtil sina_Market-DurationUP LinePower filter_resample_Monitor

for %%P in (%PROGRAMS%) do (
    if exist "%WORKDIR%\%%P.exe" (
        echo 启动 EXE: %%P.exe
        start cmd /k  "%WORKDIR%\%%P.exe"
    ) else if exist "%WORKDIR%\%%P.py" (
        echo 启动 Python: %%P.py
        start cmd /k  python "%WORKDIR%\%%P.py"
    ) else (
        echo ERROR: 找不到 %%P.exe 或 %%P.py
    )
    timeout /t 5 /nobreak >nul
)

REM dataBarFeed 目录启动 chantdxpower
cd dataBarFeed
if exist "chantdxpower.exe" (
    echo 启动 EXE: chantdxpower.exe
    start cmd /k  "chantdxpower.exe"
) else if exist "chantdxpower.py" (
    echo 启动 Python: chantdxpower.py
    start cmd /k  python "chantdxpower.py"
) else (
    echo ERROR: 找不到 chantdxpower.exe 或 chantdxpower.py
)
cd /d "%WORKDIR%"
timeout /t 5 /nobreak >nul

REM webTools 目录启动 ths-tdx-web
cd webTools
if exist "ths-tdx-web.exe" (
    echo 启动 EXE: ths-tdx-web.exe
    start cmd /k  "ths-tdx-web.exe"
) else if exist "ths-tdx-web.py" (
    echo 启动 Python: ths-tdx-web.py
    start cmd /k  python "ths-tdx-web.py"
) else (
    echo ERROR: 找不到 ths-tdx-web.exe 或 ths-tdx-web.py
)
cd /d "%WORKDIR%"
timeout /t 5 /nobreak >nul

REM 最后启动 macRun.py
echo 启动 macRun.py
python macRun.py
timeout /t 2 /nobreak >nul

echo 所有程序启动完成
rem pause
