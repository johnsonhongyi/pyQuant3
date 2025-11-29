@echo off
REM ============================================
REM PyInstall 打包用精简环境创建脚本
REM ============================================

setlocal enabledelayedexpansion

REM 设置环境变量
set ENV_NAME=py_stock_build
set PYTHON_VERSION=3.9.13

echo.
echo ============================================
echo 创建 PyInstall 打包环境: %ENV_NAME%
echo ============================================
echo.

REM 1. 检查conda
echo [1/5] 检查 conda...
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] conda 不可用，请确保已安装 Anaconda/Miniconda
    pause
    exit /b 1
)
echo [OK] conda 已找到

REM 2. 清理旧环境（如果存在）
echo.
echo [2/5] 清理旧环境...
call conda env list | find "%ENV_NAME%" >nul
if %errorlevel% equ 0 (
    echo 找到旧环境 %ENV_NAME%，正在删除...
    call conda remove -y -n %ENV_NAME% --all
    if %errorlevel% neq 0 (
        echo [WARNING] 旧环境删除可能不完整，继续执行
    )
    echo [OK] 旧环境已删除
) else (
    echo [OK] 无旧环境
)

REM 3. 创建新环境
echo.
echo [3/5] 创建新环境 (Python %PYTHON_VERSION%)...
set USE_VENV=0

echo 注意: Python 3.9.13 用于最佳兼容性 (numpy, talib 等)
echo 尝试使用 conda 创建环境...
call conda create -y -n %ENV_NAME% python=%PYTHON_VERSION% pip
if %errorlevel% neq 0 (
    echo [WARNING] 默认源失败，尝试清理缓存并重试...
    call conda clean --all -y
    call conda create -y -n %ENV_NAME% python=%PYTHON_VERSION% pip
    if !errorlevel! neq 0 (
        echo [WARNING] Conda 创建失败。正在尝试切换到标准 Python venv...
        set USE_VENV=1
        
        REM 检查当前目录下是否有同名文件夹，如果有则删除
        if exist "%ENV_NAME%" (
            echo 删除旧的 venv 文件夹...
            rmdir /s /q "%ENV_NAME%"
        )
        
        python -m venv %ENV_NAME%
        if !errorlevel! neq 0 (
            echo [ERROR] venv 创建也失败了。请检查 Python 安装。
            pause
            exit /b 1
        )
        echo [OK] venv 环境创建成功
    )
)

if "%USE_VENV%"=="0" echo [OK] Conda 环境创建成功

REM 创建激活脚本 helper
echo @echo off > activate_env.bat
if "!USE_VENV!"=="1" (
    echo call "%%~dp0%ENV_NAME%\Scripts\activate.bat" >> activate_env.bat
) else (
    echo call conda activate %ENV_NAME% >> activate_env.bat
)

REM 4. 激活环境并安装包
echo.
echo [4/5] 安装包...

if "!USE_VENV!"=="1" (
    call %ENV_NAME%\Scripts\activate.bat
    
    echo [venv] 升级 pip...
    python -m pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/
    
    echo [venv] 安装基础包 numpy, pandas, pyqt5, pywin32...
    pip install --no-cache-dir numpy pandas pyqt5 pywin32 -i https://mirrors.aliyun.com/pypi/simple/
) else (
    call conda activate %ENV_NAME%
    
    echo [conda] 安装 conda 包...
    call conda install -y -c conda-forge ^
        numpy ^
        pandas ^
        pyqt5 ^
        pywin32 >nul 2>&1
)

REM 4b. 安装pip包 (通用)
echo 安装其他 pip 包...
pip install --no-cache-dir ^
    pyperclip ^
    pyqtgraph ^
    talib ^
    tushare ^
    pandas-ta ^
    requests ^
    configobj ^
    tqdm ^
    chardet ^
    a-trade-calendar ^
    pyinstaller ^
    -i https://mirrors.aliyun.com/pypi/simple/ >nul 2>&1

echo [OK] 所有包安装完成

REM 5. 验证环境
echo.
echo [5/5] 验证环境...
python -c "import warnings; warnings.filterwarnings('ignore'); import numpy, pandas, PyQt5, pyqtgraph, talib, tushare; print('[OK] 所有关键包验证成功')" 2>nul
if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo [SUCCESS] 环境创建完成！
    echo ============================================
    echo.
    echo 环境信息:
    if "!USE_VENV!"=="1" (
        echo 类型: Python venv
        echo 路径: %CD%\%ENV_NAME%
    ) else (
        echo 类型: Conda env
        call conda info
    )
    echo.
    echo 使用方法:
    echo   1. 激活环境:  call activate_env.bat
    echo   2. 打包应用:  pyinstaller --onefile instock_MonitorTK.py
    echo.
) else (
    echo [ERROR] 环境验证失败
    pause
    exit /b 1
)

REM 6. 显示环境信息
echo.
echo 环境路径:
call conda run -n %ENV_NAME% python -c "import sys; print('  ' + sys.prefix)"

echo.
pause
