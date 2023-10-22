rem set var="D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM cd "D:\MacTools\WorkFile\WorkSpace\pyQuant\stock"
REM E:
D:
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock"
rem cd stock
start cmd /k python instock_Monitor.py
set TDX=G:\tdx_last_df.h5

IF NOT EXIST  G:\tdx_last_df.h5 (
	ping -n 352 localhost > nul
)
rem ELSE (
rem	goto A
rem )


for %%i in ("%TDX%") do (
set indexdx=%%~zi
)
rem if %indexdx% gtr 512000 (
if %indexdx% gtr 2048000 (
    ping -n 5 localhost > nul
)else (
    ping -n 352 localhost > nul
)

start cmd /k python singleAnalyseUtil.py
ping -n 20 localhost > nul
REM start python sina_Monitor.py 
REM ping -n 15 localhost > nul

rem start cmd /k python sina_Monitor-GOLD.py
rem ping -n 20 localhost > nul

start cmd /k python sina_Monitor.py
ping -n 20 localhost > nul
start cmd /k python sina_Market-DurationCXDN.py
ping -n 20 localhost > nul

start cmd /k python sina_Market-DurationUP.py
ping -n 20 localhost > nul

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
ping -n 20 localhost > nul 
start cmd /k python LinePower.py
rem cd dataBarFeed\
rem start cmd /k python chantdxpower.py
ping -n 20 localhost > nul 
cd "D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\"
python macRun.py
rem pause
rem start python LineHistogram.py
