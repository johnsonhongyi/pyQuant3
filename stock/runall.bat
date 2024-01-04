rem set var="D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM cd "D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM E:
D:
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock"

start cmd /k python sina_Monitor.py
TIMEOUT /T 20 /NOBREAK

set TDX=G:\tdx_last_df.h5

rem ping -n 352 localhost > nul
IF NOT EXIST  G:\tdx_last_df.h5 (
	TIMEOUT /T 10 /NOBREAK
)

for %%i in ("%TDX%") do (
set indexdx=%%~zi
)

if %indexdx% LEQ  2048000 (
  TIMEOUT /T 50 /NOBREAK
)


start cmd /k python instock_Monitor.py

rem ELSE (
rem	goto A
rem )
rem if %indexdx% gtr 512000 ( LEQ GEQ 


start cmd /k python singleAnalyseUtil.py
TIMEOUT /T 20 /NOBREAK


rem start cmd /k python sina_Monitor-GOLD.py
rem ping -n 20 localhost > nul


start cmd /k python sina_Market-DurationCXDN.py
TIMEOUT /T 20 /NOBREAK

start cmd /k python sina_Market-DurationUP.py
TIMEOUT /T 20 /NOBREAK

rem start cmd /k python sina_Monitor-Market.py
rem ping -n 20 localhost > nul
rem start cmd /k python sina_Monitor-Market-New.py
rem ping -n 20 localhost > nul
rem start cmd /k python sina_Monitor-Market-LH.py
rem start cmd /k python sina_Market-DurationUp.py
rem ping -n 20 localhost > nul 
start cmd /k python sina_Monitor-Market-LH.py
rem ping -n 20 localhost > nul 
start cmd /k python sina_Market-DurationDn.py
TIMEOUT /T 20 /NOBREAK
start cmd /k python LinePower.py
TIMEOUT /T 5 /NOBREAK
cd dataBarFeed\
start cmd /k python chantdxpower.py
TIMEOUT /T 20 /NOBREAK
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\"
python macRun.py
rem pause
rem start python LineHistogram.py
