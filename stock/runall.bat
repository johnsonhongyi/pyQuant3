rem set var="D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM cd "D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM E:
D:
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock"

rem start cmd /k python sina_Monitor.py
start cmd /k  sina_Monitor.exe

IF NOT EXIST  G:\tdx_last_df.h5 (
    TIMEOUT /T 200 /NOBREAK
)

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)

if "%indexdx%"=="" (set indexdx=4096)

if not "%indexdx%"==""  if %indexdx% LEQ  4096000 (TIMEOUT /T 50 /NOBREAK)


set TDX=G:\tdx_last_df.h5

TIMEOUT /T 5 /NOBREAK

rem ping -n 352 localhost > nul
IF NOT EXIST  G:\tdx_last_df.h5 (
	TIMEOUT /T 10 /NOBREAK
)

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)

if "%indexdx%"=="" (set indexdx=4096)

if not "%indexdx%"==""  if %indexdx% LEQ  4096000 (TIMEOUT /T 50 /NOBREAK)

rem if not "%indexdx%"=="" (TIMEOUT /T 0 /NOBREAK) else (if %indexdx% LEQ  2048000 (TIMEOUT /T 50 /NOBREAK))
rem if %indexdx% LEQ  2048000 (TIMEOUT /T 50 /NOBREAK)

rem start cmd /k python instock_Monitor.py
start cmd /k  instock_Monitor.exe

rem ELSE (
rem	goto A
rem )
rem if %indexdx% gtr 512000 ( LEQ GEQ 
TIMEOUT /T 10 /NOBREAK

rem start cmd /k python singleAnalyseUtil.py
start cmd /k singleAnalyseUtil.exe
TIMEOUT /T 5 /NOBREAK



rem start cmd /k python sina_Monitor-GOLD.py
rem ping -n 20 localhost > nul


rem start cmd /k python sina_Market-DurationCXDN.py
rem TIMEOUT /T 20 /NOBREAK

rem start cmd /k python sina_Market-DurationUP.py
start cmd /k sina_Market-DurationUP.exe

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)

if "%indexdx%"=="" (set indexdx=4096000)

if not "%indexdx%"==""  if %indexdx% LEQ  10000000 (TIMEOUT /T 200 /NOBREAK)

TIMEOUT /T 10 /NOBREAK

rem start cmd /k python sina_Monitor-Market.py
rem ping -n 20 localhost > nul
rem start cmd /k python sina_Monitor-Market-New.py
rem ping -n 20 localhost > nul
rem start cmd /k python sina_Monitor-Market-LH.py
rem start cmd /k python sina_Market-DurationUp.py
rem ping -n 20 localhost > nul 



rem start cmd /k python sina_Monitor-Market-LH.py
rem ping -n 20 localhost > nul 
rem 20250212
rem start cmd /k python sina_Market-DurationDn.py
rem TIMEOUT /T 20 /NOBREAK
rem start cmd /k python LinePower.py
start cmd /k  LinePower.exe
TIMEOUT /T 10 /NOBREAK
cd dataBarFeed\
rem start cmd /k python chantdxpower.py
start cmd /k  chantdxpower.exe
TIMEOUT /T 20 /NOBREAK
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\"
python macRun.py

cd webTools/
start cmd /k python ths-tdx-web.py
cd ../

rem start cmd /k python sina_Market-DurationDnUP.py

start cmd /k  sina_Market-DurationDnUP.exe

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)

if "%indexdx%"=="" (set indexdx=4096000)
if not "%indexdx%"==""  if %indexdx% LEQ  20000000 (TIMEOUT /T 250 /NOBREAK)
TIMEOUT /T 10 /NOBREAK


start cmd /k  filter_resample_Monitor.exe

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)
if "%indexdx%"=="" (set indexdx=4096000)
if not "%indexdx%"==""  if %indexdx% LEQ  28000000 (TIMEOUT /T 100 /NOBREAK)
TIMEOUT /T 5 /NOBREAK

rem C:
rem cd "C:\Users\Johnson\Documents\TDX\55188\"
rem start  "人气共振2.2.exe"
rem pause
rem start python LineHistogram.py
TIMEOUT /T 20 /NOBREAK
cd webTools/
python findSetWindowPos.py

exit