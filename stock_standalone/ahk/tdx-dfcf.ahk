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
; Global State
; ================================
global ClipSaved := Clipboard
global custom_copy_triggered := false
global AutoSendToDFCF := False     ; Auto push switch (default off)
global DEBUG_MODE := false         ; Debug log switch
global LOG_FILE := A_ScriptDir "\hotkey_debug.log"

; Debounce: record last sent code and timestamp to prevent rapid double-clicks
global LastSentCode := ""
global LastSentTick := 0
global DEBOUNCE_INTERVAL_MS := 800  ; 800ms debounce for same stock code

; ================================
; Notification and Log
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

Log(msg) {
    global DEBUG_MODE, LOG_FILE
    if (!DEBUG_MODE)
        return
    FormatTime, now, , yyyy-MM-dd HH:mm:ss
    FileAppend, [%now%] %msg%`r`n, %LOG_FILE%
}

; Mouse hover helper
MouseIsOver(WinTitle) {
    MouseGetPos,,, WinHwnd
    return WinExist(WinTitle . " ahk_id " . WinHwnd)
}

; ================================
; Clipboard Monitor (Auto Send on Copy)
; ================================
OnClipboardChange("HandleClipboardChange")

HandleClipboardChange(Type) {
    global custom_copy_triggered, ClipSaved, AutoSendToDFCF
    if !custom_copy_triggered {
        current := Clipboard
        if (current != ClipSaved && current != "") {
            ClipSaved := current
            if RegExMatch(ClipSaved, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode) {
                Log("Clipboard detected code: " . stockCode . ", AutoSendToDFCF=" . AutoSendToDFCF)
                if (AutoSendToDFCF) {
                    Notify("Auto Send DFCF: " . stockCode, "sound", 0.3)
                    WinGet, activeWinID, ID, A
                    SendToDFCF(stockCode)
                    Sleep, 200
                    if (activeWinID) {
                        WinActivate, ahk_id %activeWinID%
                        WinWaitActive, ahk_id %activeWinID%,, 1
                    }
                }
            }
        }
    } else {
        Log("Clipboard event suppressed by hotkey flag")
    }
}

; ================================
; Target Sending Functions
; ================================
SendToDFCF(stockCode) {
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
; Hotkey: Block Alt+Q in TDX
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class")
!q::return
#If

; ================================
; Hotkey: Middle Click Linkage
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") 
    || WinActive("ahk_class TdxW_SecondFrame_Class") 
    || WinActive("ahk_exe hexin.exe")
    || MouseIsOver("ahk_class TdxW_MainFrame_Class")
    || MouseIsOver("ahk_class TdxW_SecondFrame_Class")
    || MouseIsOver("ahk_exe hexin.exe")

!MButton::   ; Alt + Middle click
MButton::
{
    global custom_copy_triggered, ClipSaved, LastSentCode, LastSentTick, DEBOUNCE_INTERVAL_MS
    custom_copy_triggered := true
    
    ; Activate target window under cursor if not already active
    MouseGetPos,,, hoverWin
    if (hoverWin) {
        WinActivate, ahk_id %hoverWin%
    }
    
    WinGet, activeWinID, ID, A
    WinGetActiveTitle, actitle
    Log("Hotkey triggered in window: " . actitle)

    stockCode := ""
    try {
        if WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class") {
            ClipBackup := ClipboardAll
            Clipboard := ""
            
            SendMessage, 0x111, 33819, 0,, ahk_id %activeWinID%
            ClipWait, 0.4
            if (ErrorLevel || Clipboard == "") {
                SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class
                ClipWait, 0.4
            }

            RegExMatch(Clipboard, "\b\d{6}\b", stockCode)
            Log("TDX parsed code: " . stockCode)

            if (stockCode != "") {
                nowTick := A_TickCount
                if (stockCode == LastSentCode && (nowTick - LastSentTick < DEBOUNCE_INTERVAL_MS)) {
                    Notify("Duplicate click skipped: " . stockCode, "tooltip", 0.6)
                } else {
                    Notify("Sync: " . stockCode, "tooltip", 0.8)
                    SendToDFCF(stockCode)
                    SendToHexin(stockCode)
                    LastSentCode := stockCode
                    LastSentTick := nowTick
                }
            } else {
                Notify("No stock code found", "tooltip", 1)
            }
            
        } else if WinActive("ahk_exe hexin.exe") {
            SendMessage, 0x111, 31067, 0,, a
            if WinExist("ahk_class #32770") {
                WinActivate
                WinWaitActive, ahk_class #32770,, 1
                WinGetActiveTitle, title
                Send, {Esc}
                Log("THS popup title: " . title)
                RegExMatch(title, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", stockCode)
                Log("THS parsed code: " . stockCode)
                
                if (stockCode != "") {
                    nowTick := A_TickCount
                    if (stockCode == LastSentCode && (nowTick - LastSentTick < DEBOUNCE_INTERVAL_MS)) {
                        Notify("Duplicate click skipped: " . stockCode, "tooltip", 0.6)
                    } else {
                        Notify("THS Sync: " . stockCode, "tooltip", 0.8)
                        SendToTDX(stockCode)
                        SendToDFCF(stockCode)
                        LastSentCode := stockCode
                        LastSentTick := nowTick
                    }
                }
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
        custom_copy_triggered := false
        Log("Hotkey finished")
    }
}
return
#If

; ================================
; Shortcuts
; ================================
^!d::  ; Ctrl+Alt+D toggle auto push
AutoSendToDFCF := !AutoSendToDFCF
Notify("AutoSendToDFCF: " . (AutoSendToDFCF ? "ON" : "OFF"), "tray", 1)
Log("AutoSendToDFCF = " . AutoSendToDFCF)
return

^!L::  ; Ctrl+Alt+L toggle debug log
DEBUG_MODE := !DEBUG_MODE
msg := DEBUG_MODE ? "Debug Log ON" : "Debug Log OFF"
Notify(msg, "tray", 1)
Log("====== " msg " ======")
return
