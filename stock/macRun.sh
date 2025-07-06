#!/bin/bash
startTime=`date +%s`
cd /Users/Johnson/Documents/Quant/pyQuant3/stock
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
echo "filter_resample_Monitor.py"
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes filter_resample_Monitor.py
sleep 2
echo "dataBarFeed/chantdxpower.py "
python -m nuitka --show-memory --show-progress --follow-import-to=JohnsonUtil,JSONData --remove-output --lto=yes dataBarFeed/chantdxpower.py 
sleep 2
mv chantdxpower.bin dataBarFeed/
ls -alh dataBarFeed/chantdxpower.*
# rem start python LineHistogram.py
#do something here
endTime=`date +%s`
sumTime=$(( $endTime - $startTime ))
minT=`expr $sumTime / 60`
echo "Total run $sumTime seconds min: $minT min"
