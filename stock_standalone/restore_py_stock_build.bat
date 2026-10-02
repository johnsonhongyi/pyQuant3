@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ENV_NAME=py_stock_build"
set "ENV_FILE=%~dp0py_stock_build_backup.yml"
set "CONDA_CMD="

for /f "delims=" %%C in ('where conda 2^>nul') do if not defined CONDA_CMD set "CONDA_CMD=%%C"
if not defined CONDA_CMD if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "CONDA_CMD=%USERPROFILE%\anaconda3\condabin\conda.bat"
if not defined CONDA_CMD if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDA_CMD=%USERPROFILE%\miniconda3\condabin\conda.bat"

if not defined CONDA_CMD (
    echo [ERROR] Conda was not found. Open an Anaconda Prompt or add Conda to PATH.
    goto :fail
)
if not exist "%ENV_FILE%" (
    echo [ERROR] Environment backup file not found: "%ENV_FILE%"
    goto :fail
)

call "%CONDA_CMD%" run -n "%ENV_NAME%" python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Existing Conda environment "%ENV_NAME%" was not found.
    echo [INFO] This script never creates environments. Recreate it manually, then run this script again.
    goto :fail
)

echo This will update the existing "%ENV_NAME%" from:
echo "%ENV_FILE%"
echo Extra packages will be kept; the environment will not be pruned or recreated.
choice /C YN /N /M "Continue? [Y/N] "
if errorlevel 2 (
    echo [CANCELLED] No changes were made.
    endlocal
    exit /b 0
)

call "%CONDA_CMD%" env update --name "%ENV_NAME%" --file "%ENV_FILE%" --yes
if errorlevel 1 goto :fail

call "%CONDA_CMD%" run -n "%ENV_NAME%" python -c "import sys; print('Python: ' + sys.executable)"
if errorlevel 1 goto :fail

echo [SUCCESS] Existing "%ENV_NAME%" has been restored from the backup.
pause
endlocal
exit /b 0

:fail
echo [FAILED] Environment restore stopped. No environment was created.
pause
endlocal
exit /b 1
