; ================================
; TDX - DFCF - THS Linkage Script
; ================================
#Persistent
#NoEnv
#SingleInstance Force
#MaxThreadsPerHotkey 2
SetWorkingDir %A_ScriptDir%

; Auto-elevate to Administrator to interact with elevated trading software
if !A_IsAdmin {
    try {
        Run *RunAs "%A_ScriptFullPath%"
        ExitApp
    }
}

; ================================
; Global State (Auto-Execute Section)
; ================================
global ClipSaved := Clipboard
global custom_copy_triggered := false
global AutoSendToDFCF := False     ; Auto push switch (default OFF)
global DEBUG_MODE := true          ; Debug log switch (keep ON to hotkey_debug.log)
global LOG_FILE := A_ScriptDir "\hotkey_debug.log"

; Debounce: record last sent code and timestamp to prevent rapid double-clicks
global LastSentCode := ""
global LastSentTick := 0
global DEBOUNCE_INTERVAL_MS := 800  ; 800ms debounce for same stock code

; Register clipboard hook inside auto-execute section before any return
OnClipboardChange("HandleClipboardChange")

; Automatically prune logs older than 2 days on startup and every 6 hours
PruneLog(2)
SetTimer, AutoPruneLog, % 6 * 3600 * 1000

Log("=== Script started, AutoSendToDFCF=" . AutoSendToDFCF . " ===")

return  ; Formal end of auto-execute section!

; ================================
; Notification and Log Functions
; ================================
Notify(msg, type:="tray", duration:=2) {
    if (type = "msgbox") {
        MsgBox, %msg%
    } else if (type = "tooltip") {
        ToolTip, %msg%
        SetTimer, RemoveToolTip, % -duration * 1000
    } else if (type = "tray") {
        TrayTip, pyQuant3 Linkage, %msg%, %duration%, 1
    } else if (type = "sound") {
        SoundBeep, 750, 200
    }
}

RemoveToolTip:
ToolTip
return

AutoPruneLog:
    PruneLog(2)
return

Log(msg) {
    global DEBUG_MODE, LOG_FILE
    if (!DEBUG_MODE)
        return
    FormatTime, now, , yyyy-MM-dd HH:mm:ss
    FileAppend, [%now%] %msg%`r`n, %LOG_FILE%
}

PruneLog(days:=2) {
    global LOG_FILE
    if !FileExist(LOG_FILE)
        return

    cutoff := A_Now
    EnvAdd, cutoff, -%days%, Days
    FormatTime, cutoffStr, %cutoff%, [yyyy-MM-dd HH:mm:ss]

    FileRead, content, %LOG_FILE%
    if (content == "")
        return

    ; Zero I/O short-circuit: if first line is already within cutoff, do nothing
    firstLineEnd := InStr(content, "`n")
    if (firstLineEnd > 0) {
        firstLine := SubStr(content, 1, firstLineEnd)
        if RegExMatch(firstLine, "^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]", m) {
            if (m >= cutoffStr)
                return
        }
    }

    pos := 1
    cutoffPos := 0
    while (pos := RegExMatch(content, "m)^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", m, pos)) {
        if (m >= cutoffStr) {
            cutoffPos := pos
            break
        }
        nextN := InStr(content, "`n", false, pos)
        if (!nextN)
            break
        pos := nextN + 1
    }

    if (cutoffPos > 1) {
        newContent := SubStr(content, cutoffPos)
        file := FileOpen(LOG_FILE, "w")
        if IsObject(file) {
            file.Write(newContent)
            file.Close()
        }
    } else if (cutoffPos == 0) {
        file := FileOpen(LOG_FILE, "w")
        if IsObject(file)
            file.Close()
    }
}

; High-performance single-pass hover/active window tester
IsStockWindowHoverOrActive() {
    WinGet, activeHwnd, ID, A
    if (activeHwnd) {
        WinGetClass, aCls, ahk_id %activeHwnd%
        if (aCls = "TdxW_MainFrame_Class" || aCls = "TdxW_SecondFrame_Class")
            return true
        WinGet, aExe, ProcessName, ahk_id %activeHwnd%
        if (aExe = "hexin.exe" || aExe = "mainfree.exe")
            return true
    }
    
    MouseGetPos,,, hoverHwnd
    if (hoverHwnd && hoverHwnd != activeHwnd) {
        WinGetClass, hCls, ahk_id %hoverHwnd%
        if (hCls = "TdxW_MainFrame_Class" || hCls = "TdxW_SecondFrame_Class")
            return true
        WinGet, hExe, ProcessName, ahk_id %hoverHwnd%
        if (hExe = "hexin.exe" || hExe = "mainfree.exe")
            return true
    }
    return false
}

; ================================
; Code Extraction Helpers (Single Responsibility)
; ================================
GetCodeFromTDX(winId) {
    Clipboard := ""
    SendMessage, 0x111, 33819, 0,, ahk_id %winId%
    ClipWait, 0.4
    if (ErrorLevel || Clipboard == "") {
        SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class
        ClipWait, 0.4
    }
    code := ""
    RegExMatch(Clipboard, "\b\d{6}\b", code)
    Clipboard := ""
    ClipSaved := ""
    Log("TDX parsed code: " . code)
    return code
}

GetCodeFromTHS() {
    code := ""
    SendMessage, 0x111, 31067, 0,, a
    if WinExist("ahk_class #32770") {
        WinActivate
        WinWaitActive, ahk_class #32770,, 1
        WinGetActiveTitle, title
        Send, {Esc}
        Log("THS popup title: " . title)
        RegExMatch(title, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", code)
    }
    Log("THS parsed code: " . code)
    return code
}

GetCodeFromDFCF(winId) {
    static cachedDfcfDir := ""
    code := ""
    WinGetTitle, title, ahk_id %winId%
    WinGetClass, cls, ahk_id %winId%
    Log("DFCF Main: HWND=" . winId . " CLS=" . cls . " TITLE=" . title)
    
    ; Strategy 1: Scan real-time stock data files (instant on browsing, zero lag)
    dfcfDir := cachedDfcfDir
    if (dfcfDir == "" || !FileExist(dfcfDir)) {
        dfcfExePath := ""
        if (winId) {
            WinGet, dfcfExePath, ProcessPath, ahk_id %winId%
        }
        if (dfcfExePath == "" || !FileExist(dfcfExePath)) {
            WinGet, dfcfExePath, ProcessPath, ahk_exe mainfree.exe
        }
        if (dfcfExePath == "" || !FileExist(dfcfExePath)) {
            dfcfExePath := "D:\MacTools\WinTools\eastmoney\swc8\mainfree.exe"
        }
        if (dfcfExePath != "") {
            SplitPath, dfcfExePath,, dfcfDir
            cachedDfcfDir := dfcfDir
        }
    }
    if (dfcfDir != "") {
        latestTime := ""
        latestCode := ""
        
        ; 1.1 Check STK_REPORT_V2 (lightweight, ~600 files, instant touch on browsing)
        rptDir := dfcfDir . "\data\STOCK\STK_REPORT_V2"
        if InStr(FileExist(rptDir), "D") {
            Loop, Files, %rptDir%\*.rpt
            {
                if (A_LoopFileTimeModified > latestTime) {
                    latestTime := A_LoopFileTimeModified
                    if RegExMatch(A_LoopFileName, "^\d+_([A-Za-z0-9]{6})\.", m) {
                        latestCode := m1
                    }
                }
            }
        }
        
        ; 1.2 Check K_RT_MSGTIP_V2 (most reliable, updated on EVERY stock switch)
        msgDir := dfcfDir . "\data\STOCK\K_RT_MSGTIP_V2"
        if InStr(FileExist(msgDir), "D") {
            Loop, Files, %msgDir%\*.msg
            {
                if (A_LoopFileTimeModified > latestTime) {
                    latestTime := A_LoopFileTimeModified
                    if RegExMatch(A_LoopFileName, "^\d+_([A-Za-z0-9]{6})_", m) {
                        latestCode := m1
                    }
                }
            }
        }
        
        if (latestCode != "") {
            if RegExMatch(latestCode, "^(?:60|30|00|43|83|87|92)\d{4}$|^(?:688|200)\d{3}$") {
                Log("Matched valid A-share from DFCF realtime data files: " . latestCode . " (time: " . latestTime . ")")
                return latestCode
            } else if RegExMatch(latestCode, "^\d{6}$") {
                Log("Matched 6-digit code from DFCF realtime data files: " . latestCode . " (time: " . latestTime . ")")
                return latestCode
            }
        }

        ; Strategy 2: Fallback to RecentStocks.dat (historical cache)
        datFile := dfcfDir . "\data\RecentStocks.dat"
        if FileExist(datFile) {
            FileRead, rawStr, %datFile%
            if RegExMatch(rawStr, "^\s*([A-Za-z0-9]+)\t", m) {
                candidate := m1
                if RegExMatch(candidate, "^(?:60|30|00|43|83|87|92)\d{4}$|^(?:688|200)\d{3}$") {
                    code := candidate
                    Log("Matched valid A-share from DFCF RecentStocks.dat: " . code)
                    return code
                } else if RegExMatch(candidate, "^\d{6}$") {
                    code := candidate
                    Log("Matched 6-digit code from DFCF RecentStocks.dat: " . code)
                    return code
                }
            }
        }
    }

    ; Strategy 2: check title
    RegExMatch(title, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", code)
    if (code != "") {
        Log("Matched from DFCF title: " . code)
        return code
    }

    ; Strategy 3: ControlList scan
    WinGet, ctrlList, ControlList, ahk_id %winId%
    Loop, Parse, ctrlList, `n
    {
        if (A_LoopField != "") {
            ControlGetText, txt, %A_LoopField%, ahk_id %winId%
            if (txt != "") {
                Log("DFCF Ctrl [" . A_LoopField . "]: " . SubStr(txt, 1, 50))
                if RegExMatch(txt, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", m) {
                    Log("Matched from DFCF ctrl: " . m)
                    return m
                }
            }
        }
    }

    ; Strategy 4: SubWindows scan
    WinGet, wList, List, ahk_exe mainfree.exe
    Loop, %wList%
    {
        subH := wList%A_Index%
        if (subH != winId) {
            WinGetTitle, sT, ahk_id %subH%
            if (sT != "") {
                Log("DFCF sub: " . sT)
                if RegExMatch(sT, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", m) {
                    Log("Matched from DFCF sub: " . m)
                    return m
                }
            }
        }
    }

    ; Strategy 5: Message 33819
    Clipboard := ""
    SendMessage, 0x111, 33819, 0,, ahk_id %winId%
    ClipWait, 0.15
    if (Clipboard != "") {
        RegExMatch(Clipboard, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", m)
        if (m != "") {
            Log("Matched from DFCF 33819: " . m)
            code := m
        }
    }
    Clipboard := ""

    ; Strategy 6: Silent Ctrl+C
    if (code == "") {
        Clipboard := ""
        Send, ^c
        ClipWait, 0.2
        if (Clipboard != "") {
            Log("DFCF Ctrl+C: " . SubStr(Clipboard, 1, 50))
            RegExMatch(Clipboard, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", m)
            if (m != "") {
                Log("Matched from DFCF Ctrl+C: " . m)
                code := m
            }
        }
        Clipboard := ""
        ClipSaved := ""
    }

    Log("DFCF Final code: " . code)
    return code
}

; ================================
; Sync Dispatchers
; ================================
SyncFromTDX(stockCode) {
    global LastSentCode, LastSentTick, DEBOUNCE_INTERVAL_MS
    nowTick := A_TickCount
    if (stockCode == LastSentCode && (nowTick - LastSentTick < DEBOUNCE_INTERVAL_MS)) {
        Notify("Duplicate click skipped: " . stockCode, "tooltip", 0.6)
        return
    }
    Notify("Sync: " . stockCode, "tooltip", 0.8)
    SendToDFCF(stockCode)
    SendToHexin(stockCode)
    LastSentCode := stockCode
    LastSentTick := nowTick
}

SyncFromTHS(stockCode) {
    global LastSentCode, LastSentTick, DEBOUNCE_INTERVAL_MS
    nowTick := A_TickCount
    if (stockCode == LastSentCode && (nowTick - LastSentTick < DEBOUNCE_INTERVAL_MS)) {
        Notify("Duplicate click skipped: " . stockCode, "tooltip", 0.6)
        return
    }
    Notify("THS Sync: " . stockCode, "tooltip", 0.8)
    SendToTDX(stockCode)
    SendToDFCF(stockCode)
    LastSentCode := stockCode
    LastSentTick := nowTick
}

SyncFromDFCF(stockCode) {
    global LastSentCode, LastSentTick, DEBOUNCE_INTERVAL_MS
    nowTick := A_TickCount
    if (stockCode == LastSentCode && (nowTick - LastSentTick < DEBOUNCE_INTERVAL_MS)) {
        Notify("Duplicate click skipped: " . stockCode, "tooltip", 0.6)
        return
    }
    Notify("DFCF Sync: " . stockCode, "tooltip", 0.8)
    SendToTDX(stockCode)
    SendToHexin(stockCode)
    LastSentCode := stockCode
    LastSentTick := nowTick
}

; ================================
; Target Sending Functions
; ================================
SendToDFCF(stockCode) {
    global AutoSendToDFCF
    if (!AutoSendToDFCF) {
        Log("AutoSendToDFCF is OFF, skip SendToDFCF(" . stockCode . ")")
        return
    }
    Log("Execute SendToDFCF(" . stockCode . ")")
    targetWin := "ahk_exe mainfree.exe"
    if WinExist(targetWin) {
        WinActivate, %targetWin%
        WinWaitActive, %targetWin%,, 1.5
        Sleep, 200
        SetKeyDelay, 60, 30
        Send, %stockCode%
        Sleep, 350
        Send, {Enter}
        Sleep, 400
        Log("SendToDFCF completed: " . stockCode)
    } else {
        Log("DFCF window not found (mainfree.exe)")
        Notify("DFCF not found: " . stockCode, "tooltip", 1.5)
    }
}

SendToTDX(stockCode) {
    Log("Execute SendToTDX(" . stockCode . ")")
    targetWin := "ahk_class TdxW_MainFrame_Class"
    if WinExist(targetWin) {
        WinActivate, %targetWin%
        WinWaitActive, %targetWin%,, 1
        Sleep, 150
        SetKeyDelay, 80, 20
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
        Sleep, 250
        Log("SendToTDX completed: " . stockCode)
    }
}

SendToHexin(stockCode) {
    Log("Execute SendToHexin(" . stockCode . ")")
    targetWin := "ahk_exe hexin.exe"
    if WinExist(targetWin) {
        WinActivate, %targetWin%
        WinWaitActive, %targetWin%,, 1
        Sleep, 150
        SetKeyDelay, 50, 20
        Send, %stockCode%
        Sleep, 200
        Send, {Enter}
        Sleep, 250
        Log("SendToHexin completed: " . stockCode)
    }
}

; ================================
; Clipboard Monitor (Auto Send on Copy)
; ================================
HandleClipboardChange(Type) {
    global custom_copy_triggered, ClipSaved, AutoSendToDFCF
    ; Zero-overhead early exit when auto push is disabled or hotkey in progress
    if (custom_copy_triggered || !AutoSendToDFCF)
        return

    current := Clipboard
    if (current != ClipSaved && current != "") {
        ClipSaved := current
        if RegExMatch(ClipSaved, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode) {
            Log("Clipboard detected code: " . stockCode . ", AutoSendToDFCF=" . AutoSendToDFCF)
            Notify("Auto Send DFCF: " . stockCode, "sound", 0.3)
            WinGet, activeWinID, ID, A
            SendToDFCF(stockCode)
            Sleep, 200
            if (activeWinID) {
                WinActivate, ahk_id %activeWinID%
                WinWaitActive, ahk_id %activeWinID%,, 1
            }
            Clipboard := ""
            ClipSaved := ""
        }
    }
}

; ================================
; Hotkey: Block Alt+Q in TDX
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class")
!q::return
#If

; ================================
; Hotkey: Middle Click Linkage (TDX / THS / DFCF)
; ================================
#If IsStockWindowHoverOrActive()

!MButton::   ; Alt + Middle click (Preserve/Copy clipboard)
MButton::    ; Middle click (Clean clipboard)
    isAltTriggered := InStr(A_ThisHotkey, "!") || GetKeyState("Alt", "P")
    origClip := Clipboard
    custom_copy_triggered := true
    
    MouseGetPos,,, hoverWin
    if (hoverWin) {
        WinActivate, ahk_id %hoverWin%
    }
    
    WinGet, activeWinID, ID, A
    WinGetActiveTitle, actitle
    Log("Hotkey triggered (" . (isAltTriggered ? "Alt+MButton" : "MButton") . ") in window: " . actitle)

    stockCode := ""
    try {
        if WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class") {
            stockCode := GetCodeFromTDX(activeWinID)
            if (stockCode != "") {
                SyncFromTDX(stockCode)
            } else {
                Notify("No stock code found in TDX", "tooltip", 1)
            }
        } else if WinActive("ahk_exe hexin.exe") {
            stockCode := GetCodeFromTHS()
            if (stockCode != "") {
                SyncFromTHS(stockCode)
            } else {
                Notify("No stock code found in THS", "tooltip", 1)
            }
        } else if WinActive("ahk_exe mainfree.exe") {
            stockCode := GetCodeFromDFCF(activeWinID)
            if (stockCode != "") {
                SyncFromDFCF(stockCode)
            } else {
                Notify("No stock code found in DFCF (check log)", "tooltip", 1.5)
            }
        }
    } catch e {
        Log("Hotkey error: " . e.Message)
        Notify("Hotkey error: " . e.Message, "tray", 2)
    } finally {
        Sleep, 200
        if (activeWinID) {
            WinActivate, ahk_id %activeWinID%
            WinWaitActive, ahk_id %activeWinID%,, 1
        }
        if (isAltTriggered) {
            if (stockCode != "") {
                Clipboard := stockCode
                ClipSaved := stockCode
                Notify("Synced & Copied: " . stockCode, "tooltip", 0.8)
                Log("Hotkey finished, Alt+MButton -> stockCode copied to clipboard: " . stockCode)
            } else {
                Clipboard := origClip
                ClipSaved := origClip
                Log("Hotkey finished, Alt+MButton -> original clipboard restored")
            }
        } else {
            Clipboard := ""
            ClipSaved := ""
            Log("Hotkey finished, normal MButton -> clipboard cleaned")
        }
        custom_copy_triggered := false
    }
return
#If

; ================================
; Shortcuts
; ================================
^!d::  ; Ctrl+Alt+D toggle auto push
AutoSendToDFCF := !AutoSendToDFCF
Notify("AutoSendToDFCF: " . (AutoSendToDFCF ? "ON" : "OFF"), "tray", 1)
Log("AutoSendToDFCF toggled to: " . AutoSendToDFCF)
return

^!L::  ; Ctrl+Alt+L toggle debug log
DEBUG_MODE := !DEBUG_MODE
msg := DEBUG_MODE ? "Debug Log ON" : "Debug Log OFF"
Notify(msg, "tray", 1)
Log("====== " msg " ======")
return
