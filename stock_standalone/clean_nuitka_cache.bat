@echo off
title Clean Nuitka and Compiler Cache
chcp 65001 >nul

set "ROOT_DIR=D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone"
if exist "%~dp0\.nuitka_cache" set "ROOT_DIR=%~dp0"
if exist "%~dp0\sys_utils.py" set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
cd /d "%ROOT_DIR%"

echo =======================================================
echo Nuitka Clean Build Assistant - 深度清理打包与编译器缓存
echo =======================================================
echo 工作区根目录: %ROOT_DIR%
echo.

REM 1. 清理当前工作区的 Nuitka 增量缓存目录 .nuitka_cache
if exist "%ROOT_DIR%\.nuitka_cache" (
    echo [1/5] 清理工作区 .nuitka_cache C中间代码与常量缓存...
    rd /s /q "%ROOT_DIR%\.nuitka_cache" >nul 2>&1
    echo [SUCCESS] .nuitka_cache 已清理。
) else (
    echo [1/5] 工作区 .nuitka_cache 不存在，跳过。
)

REM 2. 清理 build 目录下的中间编译产物
echo [2/5] 清理 build 目录下的中间编译和解压文件夹...
for /d %%D in ("%ROOT_DIR%\build\*.build" "%ROOT_DIR%\build\*.dist" "%ROOT_DIR%\build\*.onefile-build") do (
    if exist "%%D" (
        rd /s /q "%%D" >nul 2>&1
        echo   - 已删除 %%D
    )
)
echo [SUCCESS] build 中间产物已清理。

REM 3. 清理 G:\Temp 下的单文件运行时解包目录
echo [3/5] 清理 G:\Temp 下的 Onefile 解包目录...
if exist "G:\Temp\ATS_Nuitka" (
    rd /s /q "G:\Temp\ATS_Nuitka" >nul 2>&1
    echo   - 已清理 G:\Temp\ATS_Nuitka
)
if exist "G:\Temp\MultiPeriodTester_Nuitka" (
    rd /s /q "G:\Temp\MultiPeriodTester_Nuitka" >nul 2>&1
    echo   - 已清理 G:\Temp\MultiPeriodTester_Nuitka
)
if exist "G:\Temp\instock_Nuitka" (
    rd /s /q "G:\Temp\instock_Nuitka" >nul 2>&1
    echo   - 已清理 G:\Temp\instock_Nuitka
)
echo [SUCCESS] G:\Temp 解包目录已清理。

REM 4. 清理 sccache 编译器编译服务缓存
echo [4/5] 清理编译器缓存 sccache / clcache...
where sccache >nul 2>&1
if not errorlevel 1 (
    sccache --stop-server >nul 2>&1
)
if exist "D:\sccache" (
    rd /s /q "D:\sccache" >nul 2>&1
    mkdir "D:\sccache"
    echo   - 已清空 D:\sccache
)
echo [SUCCESS] 编译器缓存已清理。

REM 5. 清理全工程 __pycache__ 字节码
echo [5/5] 清理工程内的 __pycache__ 字节码...
for /r %%i in (__pycache__) do (
    if exist "%%i" rd /s /q "%%i" >nul 2>&1
)
echo [SUCCESS] __pycache__ 已全部清理。

echo.
echo =======================================================
echo 缓存清理完毕！现在处于绝对纯净状态，可以开始全新的 Nuitka 打包。
echo =======================================================
echo.
if not "%~1"=="-y" pause
:end
