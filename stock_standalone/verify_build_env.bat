@echo off
REM ============================================
REM 环境验证和清理脚本
REM ============================================

setlocal enabledelayedexpansion

set ENV_NAME=py_stock_build

echo.
echo ============================================
echo 环境验证和优化工具
echo ============================================
echo.

if "%1"=="" (
    echo 用法:
    echo   verify_build_env.bat verify    - 验证环境和包
    echo   verify_build_env.bat cleanup   - 清理不需要的包
    echo   verify_build_env.bat size      - 显示环境大小
    echo   verify_build_env.bat list      - 列出所有已安装包
    echo.
    goto :end
)

if "%1"=="verify" (
    echo [验证模式]
    echo.
    call conda activate %ENV_NAME%
    
    echo 检查必需的包...
    for %%p in (numpy pandas PyQt5 pyqtgraph talib tushare pyinstaller) do (
        python -c "import %%p" >nul 2>&1
        if !errorlevel! equ 0 (
            echo   [OK] %%p
        ) else (
            echo   [FAIL] %%p
        )
    )
    
    echo.
    echo 环境信息:
    python --version
    echo Python 路径: %PYTHON%
    goto :end
)

if "%1"=="cleanup" (
    echo [清理模式]
    echo.
    call conda activate %ENV_NAME%
    
    echo 删除不需要的包...
    for %%p in (bokeh scipy plotly statsmodels astropy ipython jupyter notebook) do (
        pip uninstall -y %%p >nul 2>&1
        if !errorlevel! equ 0 (
            echo   [删除] %%p
        )
    )
    
    echo [OK] 清理完成
    goto :end
)

if "%1"=="size" (
    echo [环境大小]
    echo.
    call conda activate %ENV_NAME%
    
    echo 计算环境大小...
    python -c "
import os
import subprocess

result = subprocess.run('python -c \"import sys; print(sys.prefix)\"', shell=True, capture_output=True, text=True)
env_path = result.stdout.strip()

if env_path:
    lib_path = os.path.join(env_path, 'Lib', 'site-packages')
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
"
    goto :end
)

if "%1"=="list" (
    echo [已安装的包]
    echo.
    call conda activate %ENV_NAME%
    pip list
    goto :end
)

:end
echo.
pause
