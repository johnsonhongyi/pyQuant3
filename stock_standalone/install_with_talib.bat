@echo off
REM ============================================
REM 完整安装脚本 (支持 talib 编译)
REM ============================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo 完整安装脚本 - PyInstall 打包环境
echo ============================================
echo.

REM 检查Python版本
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo 检测到 Python 版本: %PYTHON_VER%

REM 检查是否在虚拟环境中 (支持 conda 和 venv)
if not defined CONDA_PREFIX (
    python -c "import sys; sys.exit(0 if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else 1)" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [WARNING] 未在虚拟环境中运行！
        set /p cont="是否继续? (y/n): "
        if /i not "!cont!"=="y" exit /b 1
    )
) else (
    echo [OK] Conda 环境: !CONDA_DEFAULT_ENV!
)

echo.
echo [1/6] 升级 pip, setuptools 和 wheel...
python -m pip install --upgrade pip setuptools wheel -q

echo.
echo [2/6] 安装基础包 (numpy, pandas, PyQt5)...
pip install numpy==1.21.0 pandas PyQt5 pywin32 -i https://mirrors.aliyun.com/pypi/simple/ --only-binary :all: -q
if !errorlevel! neq 0 (
    echo [WARNING] 国内源失败，尝试官方源...
    pip install numpy==1.21.0 pandas PyQt5 pywin32 --only-binary :all: -q
)

echo.
echo [3/6] 安装 pyqtgraph 和其他图形包...
pip install pyperclip pyqtgraph -i https://mirrors.aliyun.com/pypi/simple/ --only-binary :all: -q

echo.
echo [4/6] 安装金融数据库...
pip install tushare pandas-ta requests configobj tqdm chardet a-trade-calendar -i https://mirrors.aliyun.com/pypi/simple/ -q

echo.
echo [5/6] 尝试安装 talib...
echo 注意: talib 需要 C 编译器，可能需要较长时间或失败...
echo.
echo 选项:
echo   1) 尝试编译 talib (需要 Microsoft C++ Build Tools)
echo   2) 跳过 talib (使用 pandas-ta 替代)
echo   3) 稍后手动安装 talib
echo.
set /p talib_opt="选择 (1/2/3): "

if "!talib_opt!"=="1" (
    echo 尝试编译 talib...
    pip install talib==0.4.21 --no-binary talib -i https://mirrors.aliyun.com/pypi/simple/ -q
    if !errorlevel! neq 0 (
        echo [WARNING] talib 编译失败 (需要 C 编译器)
        echo 请按以下步骤安装:
        echo   1. 下载 Microsoft C++ Build Tools
        echo   2. 安装 talib-0.4.21-*.whl 文件
        echo   或使用: pip install TA_Lib-0.4.21-cp310-cp310-win_amd64.whl
    ) else (
        echo [OK] talib 安装成功！
    )
) else if "!talib_opt!"=="2" (
    echo [OK] 跳过 talib，使用 pandas-ta 替代
    echo 注意: 应用已安装 pandas-ta，可正常运行
) else (
    echo [INFO] 稍后可使用以下命令安装 talib:
    echo   pip install talib==0.4.21
)

echo.
echo [6/6] 安装打包工具...
pip install pyinstaller -q

echo.
echo ============================================
echo 安装完成！
echo ============================================
echo.
echo 验证安装:
echo   python -c "import numpy, pandas, PyQt5, pyqtgraph, tushare; print('OK')"
echo.
echo 打包应用:
echo   pyinstaller --onefile instock_MonitorTK.py
echo.
pause
