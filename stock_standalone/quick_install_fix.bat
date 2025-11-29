@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================
echo PyInstall 快速安装脚本
echo ============================================
echo.

echo [1/5] 升级 pip setuptools wheel
python -m pip install --upgrade pip setuptools wheel -q

echo [2/5] 安装基础包
pip install numpy==1.21.6 pandas==1.4.4 pandas-ta==0.3.14b0 PyQt5 pywin32 -i https://mirrors.aliyun.com/pypi/simple/ --only-binary :all: -q

echo [3/5] 安装图形包
pip install pyperclip pyqtgraph -i https://mirrors.aliyun.com/pypi/simple/ -q

echo [4/5] 安装数据和工具包
pip install tushare requests configobj tqdm chardet -i https://mirrors.aliyun.com/pypi/simple/ -q

echo [5/5] 安装打包工具
pip install pyinstaller -q

echo.
echo ============================================
echo 安装完成!
echo ============================================
echo.
echo 验证: python -c "import numpy, pandas, PyQt5, pyqtgraph; print('OK')"
echo 打包: pyinstaller instock_MonitorTK.spec
rem echo 打包: pyinstaller --onefile instock_MonitorTK.py
echo.
pause
