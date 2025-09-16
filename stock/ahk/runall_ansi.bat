@echo off
REM ===================================================
REM pyQuant3 stock �����ű�������ԭ���߼���������
REM ��һ�������������������������ļ������˳������
REM ===================================================

REM ���ù���Ŀ¼
D:
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock"
set WORKDIR=%CD%
echo ��ǰĿ¼: %WORKDIR%

REM ============================
REM ������һ������ sina_Monitor
REM ============================
if exist "%WORKDIR%\sina_Monitor.exe" (
    echo ���� EXE: sina_Monitor.exe
    start cmd /k  "%WORKDIR%\sina_Monitor.exe"
) else if exist "%WORKDIR%\sina_Monitor.py" (
    echo ���� Python: sina_Monitor.py
    start cmd /k  python "%WORKDIR%\sina_Monitor.py"
) else (
    echo ERROR: �Ҳ��� sina_Monitor.exe �� sina_Monitor.py
)

REM ============================
REM �ȴ������ļ�׼����
REM ============================
set TDX=G:\tdx_last_df.h5

:WAIT_TDX
if not exist "%TDX%" (
    echo �ȴ��ļ�����: %TDX%
    timeout /t 10 /nobreak >nul
    goto WAIT_TDX
)

for %%i in ("%TDX%") do set indexdx=%%~zi
if "%indexdx%"=="" set indexdx=4096

if not "%indexdx%"=="" if %indexdx% LEQ 4096000 (
    echo �ļ���С %indexdx% ���㣬�ȴ�...
    timeout /t 10 /nobreak >nul
    goto WAIT_TDX
)
echo �ļ�׼����������С: %indexdx%

REM ============================
REM ������������
REM ============================

REM �������� exe �� py �ļ��������ӳ�
set PROGRAMS=instock_Monitor singleAnalyseUtil sina_Market-DurationUP LinePower filter_resample_Monitor

for %%P in (%PROGRAMS%) do (
    if exist "%WORKDIR%\%%P.exe" (
        echo ���� EXE: %%P.exe
        start cmd /k  "%WORKDIR%\%%P.exe"
    ) else if exist "%WORKDIR%\%%P.py" (
        echo ���� Python: %%P.py
        start cmd /k  python "%WORKDIR%\%%P.py"
    ) else (
        echo ERROR: �Ҳ��� %%P.exe �� %%P.py
    )
    timeout /t 5 /nobreak >nul
)

REM dataBarFeed Ŀ¼���� chantdxpower
cd dataBarFeed
if exist "chantdxpower.exe" (
    echo ���� EXE: chantdxpower.exe
    start cmd /k  "chantdxpower.exe"
) else if exist "chantdxpower.py" (
    echo ���� Python: chantdxpower.py
    start cmd /k  python "chantdxpower.py"
) else (
    echo ERROR: �Ҳ��� chantdxpower.exe �� chantdxpower.py
)
cd /d "%WORKDIR%"
timeout /t 5 /nobreak >nul

REM webTools Ŀ¼���� ths-tdx-web
cd webTools
if exist "ths-tdx-web.exe" (
    echo ���� EXE: ths-tdx-web.exe
    start cmd /k  "ths-tdx-web.exe"
) else if exist "ths-tdx-web.py" (
    echo ���� Python: ths-tdx-web.py
    start cmd /k  python "ths-tdx-web.py"
) else (
    echo ERROR: �Ҳ��� ths-tdx-web.exe �� ths-tdx-web.py
)
cd /d "%WORKDIR%"
timeout /t 5 /nobreak >nul

REM ������� macRun.py
echo ���� macRun.py
python macRun.py
timeout /t 2 /nobreak >nul

echo ���г����������
pause
