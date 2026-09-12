DetectHiddenWindows, Off
res := ""
WinGet, id_list, List, ahk_exe mainfree.exe
Loop, %id_list%
{
    this_id := id_list%A_Index%
    WinGetTitle, title, ahk_id %this_id%
    WinGetClass, class, ahk_id %this_id%
    res .= "mainfree: HWND=" . this_id . " CLASS=" . class . " TITLE=" . title . "`r`n"
}
WinGet, id_list2, List, ahk_exe stockway.exe
Loop, %id_list2%
{
    this_id := id_list2%A_Index%
    WinGetTitle, title, ahk_id %this_id%
    WinGetClass, class, ahk_id %this_id%
    res .= "stockway: HWND=" . this_id . " CLASS=" . class . " TITLE=" . title . "`r`n"
}
FileDelete, d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\ahk\dfcf_detect.txt
FileAppend, %res%, d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\ahk\dfcf_detect.txt
ExitApp
