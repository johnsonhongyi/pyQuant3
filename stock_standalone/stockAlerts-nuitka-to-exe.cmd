@echo off
setlocal enabledelayedexpansion

echo ==========================================================
echo Running Nuitka Build Process for 股票异动联动 (Clang-CL)...
echo ==========================================================

rem 记录开始时间
set "STARTTIME=%TIME: =0%"

rem 自动适配与锁定专用构建环境 (优先 nuitka_env, 次选 tk_nuitka_env)
if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" (
    call "%USERPROFILE%\anaconda3\condabin\conda.bat" activate nuitka_env >nul 2>&1
) else if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" (
    call "%USERPROFILE%\anaconda3\Scripts\activate.bat" nuitka_env >nul 2>&1
)
if not defined CONDA_PREFIX (
    if exist "%USERPROFILE%\anaconda3\envs\nuitka_env\python.exe" (
        set "CONDA_PREFIX=%USERPROFILE%\anaconda3\envs\nuitka_env"
        set "CONDA_DEFAULT_ENV=nuitka_env"
        set "VIRTUAL_ENV=%USERPROFILE%\anaconda3\envs\nuitka_env"
        set "PATH=%USERPROFILE%\anaconda3\envs\nuitka_env;%USERPROFILE%\anaconda3\envs\nuitka_env\Scripts;%USERPROFILE%\anaconda3\envs\nuitka_env\Library\bin;!PATH!"
    ) else if exist "%USERPROFILE%\anaconda3\envs\tk_nuitka_env\python.exe" (
        set "CONDA_PREFIX=%USERPROFILE%\anaconda3\envs\tk_nuitka_env"
        set "CONDA_DEFAULT_ENV=tk_nuitka_env"
        set "VIRTUAL_ENV=%USERPROFILE%\anaconda3\envs\tk_nuitka_env"
        set "PATH=%USERPROFILE%\anaconda3\envs\tk_nuitka_env;%USERPROFILE%\anaconda3\envs\tk_nuitka_env\Scripts;%USERPROFILE%\anaconda3\envs\tk_nuitka_env\Library\bin;!PATH!"
    )
)

for /f "usebackq delims=" %%i in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "BUILD_PYTHON=%%i"
for /f "usebackq delims=" %%i in (`python -m nuitka --version 2^>nul`) do (
    set "BUILD_NUITKA_VER=%%i"
    goto :nuitka_ver_done
)
:nuitka_ver_done

echo [INFO] Build Python : !BUILD_PYTHON!
echo [INFO] Build Nuitka : !BUILD_NUITKA_VER!
echo [INFO] Workspace    : D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\testpy\tdxgui

rem 切换到异动模块源码目录
d:
cd /d D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\testpy\tdxgui
set "TEMP=C:\Temp"
set "TMP=C:\Temp"

rem 执行现代优化的 Clang 构建脚本
echo [INFO] Invoking build_nuitka_clang.bat %*
call build_nuitka_clang.bat %*
set "BUILD_RESULT=!ERRORLEVEL!"

rem 记录结束时间
set "ENDTIME=%TIME: =0%"

rem 计算时间差 (防御空变量语法错)
set "start_h=0" & set "start_m=0" & set "start_s=0" & set "start_cs=0"
set "end_h=0" & set "end_m=0" & set "end_s=0" & set "end_cs=0"

for /F "tokens=1-4 delims=:.," %%a in ("%STARTTIME%") do (
   set /A "start_h=1%%a-100", "start_m=1%%b-100", "start_s=1%%c-100", "start_cs=1%%d-100"
)
for /F "tokens=1-4 delims=:.," %%a in ("%ENDTIME%") do (
   set /A "end_h=1%%a-100", "end_m=1%%b-100", "end_s=1%%c-100", "end_cs=1%%d-100"
)

set /A "start_total_cs=(start_h*360000)+(start_m*6000)+(start_s*100)+start_cs"
set /A "end_total_cs=(end_h*360000)+(end_m*6000)+(end_s*100)+end_cs"

if !end_total_cs! LSS !start_total_cs! (
   set /A "end_total_cs+=8640000"
)

set /A "diff_cs=end_total_cs-start_total_cs"
set /A "diff_s=diff_cs/100"
set /A "diff_m=diff_s/60"
set /A "rem_s=diff_s%%60"

echo ==========================================================
if "!BUILD_RESULT!"=="0" (
    echo Nuitka Build Completed Successfully!
    if exist "build\异动联动_Nuitka.exe" (
        for %%F in ("build\异动联动_Nuitka.exe") do (
            set /A "size_mb=%%~zF / 1048576"
            echo Target Exe: %%~fF [!size_mb! MB]
        )
        if exist "<USER_HOME>\Documents\TDX\55188" (
            echo [DEPLOY] Syncing 异动联动_Nuitka.exe to <USER_HOME>\Documents\TDX\55188...
            copy /y "build\异动联动_Nuitka.exe" "<USER_HOME>\Documents\TDX\55188\异动联动_Nuitka.exe" >nul 2>&1
            if exist "<USER_HOME>\Documents\TDX\55188\异动联动_Nuitka.exe" (
                echo [SUCCESS] Auto-deployed to <USER_HOME>\Documents\TDX\55188\异动联动_Nuitka.exe
            )
        )
    )
) else (
    echo Nuitka Build FAILED! [ExitCode: !BUILD_RESULT!]
)
echo ==========================================================
echo Start Time : %STARTTIME%
echo End Time   : %ENDTIME%
if !diff_m! GTR 0 (
    echo Time Cost  : !diff_m! min !rem_s! sec (!diff_s! sec)
) else (
    echo Time Cost  : !diff_s! sec
)
echo ==========================================================
pause
