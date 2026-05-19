@echo off
setlocal enabledelayedexpansion

echo 1. Loading VS Environment...
call "D:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvars64.bat"

echo.
echo 2. Removing GCC from PATH just in case...
set "PATH=!PATH:D:\mingw64\bin;=!"
set "PATH=!PATH:D:\mingw64\bin=!"
set "PATH=!PATH:D:\mingw64;=!"
set "PATH=!PATH:D:\mingw64=!"

echo.
echo 3. Generating test python file...
echo print("Hello from Native VS Clang-CL") > test_vs_clang.py

echo.
echo 4. Compiling with Nuitka using --clang and --show-scons...
python -m nuitka --show-scons --clang --remove-output test_vs_clang.py

echo.
echo 5. Done.
