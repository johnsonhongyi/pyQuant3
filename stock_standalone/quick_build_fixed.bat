@echo off
REM ============================================
REM PyInstall 快速打包向导 (改进版)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo PyInstall 快速打包向导
echo ============================================
echo.

set ENV_NAME=py_stock_build

REM 菜单
:menu
echo.
echo 请选择操作:
echo   1. 创建打包环境
echo   2. 验证环境
echo   3. 打包应用
echo   4. 查看环境大小
echo   5. 查看使用说明
echo   0. 退出
echo.

set /p choice="请输入选择 (0-5): "

if "%choice%"=="1" goto create_env
if "%choice%"=="2" goto verify_env
if "%choice%"=="3" goto build_app
if "%choice%"=="4" goto show_size
if "%choice%"=="5" goto show_help
if "%choice%"=="0" goto end
echo 无效选择，请重试

goto menu

:create_env
echo.
echo [1] 创建打包环境...
echo.
call setup_build_env.bat
goto menu

:verify_env
echo.
echo [2] 验证环境...
echo.
python -c "import warnings; warnings.filterwarnings('ignore'); import numpy, pandas, PyQt5, pyqtgraph, tushare; print('[OK] 核心包已安装')" 2>nul
if %errorlevel% equ 0 (
    echo [OK] 所有核心包验证成功
    echo.
    echo 检查可选包...
    python -c "import talib; print('[OK] talib 已安装')" 2>nul
    if !errorlevel! equ 0 (
        echo [OK] talib 已安装
    ) else (
        echo [WARNING] talib 未安装（可选）
    )
) else (
    echo [ERROR] 核心包验证失败
    echo 请先运行选项 1 创建环境
)
echo.
goto menu

:build_app
echo.
echo [3] 打包应用...
echo.
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 不在激活的环境中
    echo 请先运行选项 1 创建环境
    goto menu
)
echo 开始打包...
echo.
pyinstaller --onefile instock_MonitorTK.py
if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo [SUCCESS] 打包完成！
    echo ============================================
    echo.
    echo EXE 文件位置: dist\instock_MonitorTK.exe
    echo.
) else (
    echo.
    echo [ERROR] 打包失败
    echo 请检查错误信息
    echo.
)
goto menu

:show_size
echo.
echo [4] 查看环境大小...
echo.
python -c "
import os
import subprocess

result = subprocess.run('python -c \"import sys; print(sys.prefix)\"', shell=True, capture_output=True, text=True)
env_path = result.stdout.strip()

if env_path:
    lib_path = os.path.join(env_path, 'Lib', 'site-packages')
    if os.path.exists(lib_path):
        total = 0
        for root, dirs, files in os.walk(lib_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except:
                    pass
        
        mb = total / (1024*1024)
        print(f'Site-packages 大小: {mb:.1f} MB')
        print(f'环境路径: {env_path}')
    else:
        print('环境未正确初始化')
else:
    print('无法获取环境信息')
" 2>nul
echo.
goto menu

:show_help
echo.
echo ============================================
echo 使用说明
echo ============================================
echo.
echo 【推荐流程】
echo.
echo 第一次使用:
echo   1. 选择 "1" 创建打包环境
echo      - 需要 Python 3.9.13 (推荐)
echo      - 耗时 5-10 分钟
echo      - 会自动安装所有必需的包
echo.
echo   2. 选择 "2" 验证环境
echo      - 检查所有包是否正确安装
echo.
echo   3. 选择 "3" 打包应用
echo      - 生成 EXE 文件
echo      - 输出: dist\instock_MonitorTK.exe
echo.
echo 【其他选项】
echo.
echo   4. 查看环境大小 - 显示包的占用空间
echo   5. 查看使用说明 - 显示此帮助
echo   0. 退出 - 退出程序
echo.
echo 【更多信息】
echo.
echo - BUILD_ENV_README.md - 详细的环境配置说明
echo - TROUBLESHOOTING.md - 问题排查和解决方案
echo - requirements_build.txt - pip 包列表
echo - PACKAGES_SUMMARY.md - 包的快速参考
echo.
echo ============================================
echo.
pause
goto menu

:end
echo.
echo 再见！
echo.
pause
