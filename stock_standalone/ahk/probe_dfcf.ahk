DetectHiddenWindows, On
res := ""
WinGet, id_list, List, ahk_exe mainfree.exe
res .= "mainfree count: " . id_list . "`r`n"
Loop, %id_list%
{
    this_id := id_list%A_Index%
    WinGetTitle, title, ahk_id %this_id%
    WinGetClass, class, ahk_id %this_id%
    res .= "HWND=" . this_id . " | CLASS=" . class . " | TITLE=" . title . "`r`n"
}
WinGet, id_list2, List, ahk_exe stockway.exe
res .= "stockway count: " . id_list2 . "`r`n"
Loop, %id_list2%
{
    this_id := id_list2%A_Index%
    WinGetTitle, title, ahk_id %this_id%
    WinGetClass, class, ahk_id %this_id%
    res .= "HWND=" . this_id . " | CLASS=" . class . " | TITLE=" . title . "`r`n"
}
FileDelete, %A_Temp%\dfcf_probe.txt
FileAppend, %res%, %A_Temp%\dfcf_probe.txt, UTF-8
ExitApp
