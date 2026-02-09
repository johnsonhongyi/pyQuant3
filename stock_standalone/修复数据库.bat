@echo off
chcp 65001 >nul
title 数据库修复工具
color 0A

echo.
echo ================================================
echo           SQLite 数据库修复工具
echo ================================================
echo.
echo 正在修复数据库...
echo.

cd /d "%~dp0"
python instock_MonitorTK.py -repair-db

echo.
echo ================================================
if %ERRORLEVEL% EQU 0 (
    echo           修复完成!
    color 0A
) else (
    echo           修复失败!
    color 0C
)
echo ================================================
echo.
pause
