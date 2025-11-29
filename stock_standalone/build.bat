@echo off
REM PyInstaller 快速打包脚本（Windows 批处理）
REM 用法：在 stock_standalone 目录中执行此脚本

setlocal enabledelayedexpansion

echo.
echo ================== instock_MonitorTK PyInstaller 打包脚本 ==================
echo.

REM 检查 PyInstaller 是否安装
echo [检查] PyInstaller 是否已安装...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [错误] PyInstaller 未安装。请运行：pip install pyinstaller
    pause
    exit /b 1
)
echo [完成] PyInstaller 已安装

REM 设置变量
set SPEC_FILE=instock_MonitorTK.spec
set DIST_DIR=dist
set BUILD_DIR=build
set WORK_DIR=__pycache__

echo.
echo [步骤 1] 清理旧的构建文件...
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
echo [完成] 旧文件已清理

echo.
echo [步骤 2] 开始构建 exe...
echo 使用 spec 文件：%SPEC_FILE%
echo.

pyinstaller "%SPEC_FILE%"

if errorlevel 1 (
    echo [错误] 打包失败！请检查错误信息。
    pause
    exit /b 1
)

echo.
echo ================== 打包完成 ==================
echo.
echo [输出位置] .\%DIST_DIR%\instock_MonitorTK.exe
echo.
echo 下一步：
echo   1. 可执行文件已生成：.\dist\instock_MonitorTK.exe
echo   2. 双击运行或在命令行执行
echo   3. 首次启动可能需要较长时间（正常现象）
echo.
echo 可选：打开输出目录
explorer "%CD%\%DIST_DIR%"

pause
