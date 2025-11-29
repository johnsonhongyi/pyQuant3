@echo off
REM 精简pyinstall环境创建脚本
REM 用于stock_standalone项目的打包

setlocal enabledelayedexpansion

echo ========================================
echo 创建精简 PyInstall 环境
echo ========================================

REM 检查conda是否可用
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] conda 未找到，请确保已安装Anaconda或Miniconda
    exit /b 1
)

echo [1/4] 创建新环境: py_stock_minimal (Python 3.9)
call conda create -y -n py_stock_minimal python=3.9

if %errorlevel% neq 0 (
    echo [ERROR] 创建环境失败
    exit /b 1
)

echo.
echo [2/4] 激活环境并安装conda包
call conda activate py_stock_minimal

REM 安装conda包
call conda install -y -c conda-forge numpy pandas pyqt5 pywin32

if %errorlevel% neq 0 (
    echo [ERROR] 安装conda包失败
    exit /b 1
)

echo.
echo [3/4] 安装pip包
pip install --no-cache-dir ^
    pyperclip>=1.8.2 ^
    pyqtgraph>=0.12.4 ^
    talib>=0.4.21 ^
    tushare>=1.2.70 ^
    pandas-ta>=0.3.14b0 ^
    requests>=2.26.0 ^
    configobj>=5.0.6 ^
    tqdm>=4.62.0 ^
    chardet>=4.0.0 ^
    a-trade-calendar>=0.0.69

if %errorlevel% neq 0 (
    echo [WARNING] 部分pip包安装失败，继续验证
)

echo.
echo [4/4] 验证环境
python -c "import numpy, pandas, PyQt5, pyqtgraph, talib, tushare; print('[OK] 所有必需包安装成功')"

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo [SUCCESS] 环境创建完成！
    echo ========================================
    echo.
    echo 使用方法：
    echo   激活环境:  conda activate py_stock_minimal
    echo   停用环境:  conda deactivate
    echo   删除环境:  conda remove -y -n py_stock_minimal --all
    echo.
    echo PyInstall 打包：
    echo   pyinstaller --onefile instock_MonitorTK.py
    echo.
) else (
    echo [ERROR] 环境验证失败
    exit /b 1
)

endlocal
pause
