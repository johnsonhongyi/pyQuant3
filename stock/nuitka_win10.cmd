@REM time_cost.cmd
@echo off
@setlocal
rem rem This script was created by Nuitka to execute 'sina_Monitor.exe' with Python DLL being found.
rem set PATH=c:\users\johnson\anaconda3;%PATH%
rem set PYTHONHOME=C:\Users\Johnson\anaconda3
rem set NUITKA_PYTHONPATH=D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock;C:\Users\Johnson\anaconda3\DLLs;C:\Users\Johnson\anaconda3\lib;c:\users\johnson\anaconda3;C:\Users\Johnson\AppData\Roaming\Python\Python39\site-packages;C:\Users\Johnson\anaconda3\lib\site-packages;C:\Users\Johnson\anaconda3\lib\site-packages\zstandard-0.23.0-py3.9-win-amd64.egg;C:\Users\Johnson\anaconda3\lib\site-packages\ordered_set-4.1.0-py3.9.egg;C:\Users\Johnson\anaconda3\lib\site-packages\nuitka-2.7.11-py3.9.egg;C:\Users\Johnson\anaconda3\lib\site-packages\win32;C:\Users\Johnson\anaconda3\lib\site-packages\win32\lib;C:\Users\Johnson\anaconda3\lib\site-packages\Pythonwin
rem "%~dp0sina_Monitor.exe" %*

echo ==========time cost start %time%==========
set "ts=%time%"

cd D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock
echo "sina_Monitor.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes sina_Monitor.py
sleep 2
echo "sina_Market-DurationUp.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes sina_Market-DurationUp.py
sleep 2
echo "sina_Market-DurationDnUp.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes sina_Market-DurationDnUp.py
sleep 2
echo "LinePower.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes LinePower.py
sleep 2
echo "singleAnalyseUtil.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes singleAnalyseUtil.py
sleep 2
echo "instock_Monitor.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes instock_Monitor.py
sleep 2
echo "filter_resample_Monitor.py "
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes filter_resample_Monitor.py
sleep 2
echo "dataBarFeed/chantdxpower.py "
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes dataBarFeed/chantdxpower.py 
sleep 2
move /Y chantdxpower.* dataBarFeed/
ls -alh dataBarFeed/chantdxpower.*
rem # rem start python LineHistogram.py
set "te=%time%"
echo ==========time cost end  %te%==========
if "%te:~,2%" lss "%ts:~,2%" set "add=+24"
set /a "seconds=((%te:~,2%-%ts:~,2%%add%)*3600+(1%te:~3,2%%%100-1%ts:~3,2%%%100)*60+(1%te:~6,2%%%100-1%ts:~6,2%%%100))" 
set /a "ms=(1%te:~-2%%%100-1%ts:~-2%%%100)"
if %ms% lss 0 (
  set /a "ms=(1000%ms%)"
  set /a "seconds=(%seconds%-1)"
)
set "ms0=100%ms%"
set "ms0=%ms0:~-3%"
set /a "minutes=((%seconds%/60))"
set /a "sec1=((%seconds% %60))"
echo time cost: %minutes% min %sec1% s cost:seconds %seconds%.%ms0% s
echo time cost: %minutes% min %sec1% s cost:seconds %seconds%.%ms0% s >> NuitkaTime.txt

rem set /a "seconds=952"
rem set /a "minutes=((%seconds%/60))"
rem set /a "sec1=((%seconds%%60))"