; ================================
; 全局变量
; ================================
#Persistent

global ClipSaved := Clipboard
global custom_copy_triggered := false
global AutoSendToDFCF := False   ; <<< 开关：true=复制即推送，false=只提示不推送

; 通用通知函数
; ================================
Notify(msg, type:="tray", duration:=3) {
    if (type = "msgbox") {
        MsgBox, %msg%
    } 
    else if (type = "tooltip") {
        Gui, Tooltip:New, +AlwaysOnTop -Caption +ToolWindow
        Gui, Tooltip:Font, s10
        Gui, Tooltip:Add, Text,, %msg%
        MouseGetPos, xpos, ypos
        Gui, Tooltip:Show, x%xpos% y%ypos%
        Sleep, duration*1000
        Gui, Tooltip:Destroy
    } 
    else if (type = "tray") {
        TrayTip, 通知, %msg%, %duration%, 1
    } 
    else if (type = "sound") {
        SoundBeep, 750, duration*1000
    }
}


; ================================
; 剪贴板变化监控
; ================================
OnClipboardChange("HandleClipboardChange")

HandleClipboardChange(Type) {
    global custom_copy_triggered, ClipSaved,AutoSendToDFCF
    if !custom_copy_triggered {
        current := Clipboard
        if (current != ClipSaved && current != "") {
            ClipSaved := current
            if RegExMatch(ClipSaved,  "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode) 
            {
                ;Notify(剪贴板中检测到6位数字stockCode, "tray", 1)
                if (AutoSendToDFCF) {
                    Notify("检测到股票代码: " . stockCode, "sound", 0.3)
                    WinGet, activeWinID, ID, A
                    SendToDFCF(stockCode)
                    Sleep, 100
                    WinActivate, ahk_id %activeWinID%
                    WinWaitActive, ahk_id %activeWinID%
                    }
            }
        }
    }else {
        Notify("ClipboardChang触发，但已被热键处理:" . . , "tooltip", 1)
    } 
}

; ================================
; 功能函数
; ================================
SendToDFCF(stockCode) {
    if WinExist("ahk_exe mainfree.exe") {
        WinActivate
        WinWaitActive
        Sleep, 150
        SetKeyDelay, 100
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
    } else {
        Notify("DFCF not found:" . stockCode, "tooltip", 1)
    }
}

SendToTDX(stockCode) {
    if WinExist("ahk_class TdxW_MainFrame_Class") {
        WinActivate
        WinWaitActive
        Sleep, 100
        SetKeyDelay, 80
        Send, %stockCode%
        Sleep, 200
        Send, {Enter}
    }
}

SendToHexin(stockCode) {
    if WinExist("ahk_exe hexin.exe") {
        WinActivate
        WinWaitActive
        SetKeyDelay, 50
        Send, %stockCode%
        Sleep, 150
        Send, {Enter}
    }
}

; ================================
; 热键：鼠标中键（只在特定程序生效）
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") 
    || WinActive("ahk_class TdxW_SecondFrame_Class") 
    || WinActive("ahk_exe hexin.exe")

MButton::
{
    global custom_copy_triggered, ClipSaved
    custom_copy_triggered := true
    WinGet, activeWinID, ID, A

    try {
        if WinActive("ahk_class TdxW_MainFrame_Class") 
            || WinActive("ahk_class TdxW_SecondFrame_Class") 
        {
            ClipBackup := ClipboardAll
            SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class

            ; 等待剪贴板变化，设置超时 1 秒
            ClipWait, 0.5
            if (ErrorLevel)
                Clipboard := ClipSaved
            else
                ClipSaved := Clipboard

            ; 提取股票代码
            RegExMatch(ClipSaved, "\b\d{6}\b", stockCode)
            if (stockCode != "") {
                Notify("热键触发: " . stockCode, "tooltip", 0.8)
                SendToDFCF(stockCode)
                SendToHexin(stockCode)
            } else {
                Notify("未检测到股票代码", "tooltip", 1)
            }
            Clipboard := ClipBackup
        }
        else if WinActive("ahk_exe hexin.exe") {
            SendMessage,0x111,31067,0,,a
            if WinExist("ahk_class #32770") {
                WinActivate
                WinWaitActive, ahk_class #32770,, 1
                WinGetActiveTitle, title
                Send {Esc}
                RegExMatch(title, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", stockCode)
                if (stockCode != "") {
                    Notify("Hexin热键触发: " . stockCode, "tooltip", 0.8)
                    SendToTDX(stockCode)
                    SendToDFCF(stockCode)
                }
            }
        }
    } catch e {
        Notify("热键异常: " . e.Message, "tray", 2)
    } finally {
        Sleep, 100
        if (activeWinID) {
            WinActivate, ahk_id %activeWinID%
            WinWaitActive, ahk_id %activeWinID%,, 1
        }
        custom_copy_triggered := false
    }
}
return


#If


; =====================
; 热键：切换开关
; =====================
^!d::  ; Ctrl+Alt+D 切换自动推送开关
AutoSendToDFCF := !AutoSendToDFCF
Notify("AutoSendToDFCF 切换为: " . (AutoSendToDFCF ? "开启" : "关闭"), "tray", 1)
return