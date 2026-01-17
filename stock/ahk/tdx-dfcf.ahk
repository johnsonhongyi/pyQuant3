; ================================
; 全局变量
; ================================
#Persistent
#NoEnv
#SingleInstance Force

global ClipSaved := Clipboard
global custom_copy_triggered := false
global AutoSendToDFCF := False     ; <<< 自动推送开关（默认关闭）
global DEBUG_MODE := false         ; <<< 调试日志开关
global LOG_FILE := A_ScriptDir "\hotkey_debug.log"
global SentCodes := {}  ; <<< 已发送代码记录

; ================================
; 屏蔽 通达信 Alt+Q（终极方案）
; ================================
#Persistent
#NoEnv
#SingleInstance Force

OnMessage(0x0104, "BlockSysKey")  ; WM_SYSKEYDOWN
OnMessage(0x0105, "BlockSysKey")  ; WM_SYSKEYUP

BlockSysKey(wParam, lParam, msg, hwnd) {
    WinGetClass, cls, ahk_id %hwnd%
    if (cls != "TdxW_MainFrame_Class")
        return

    ; Q 键
    if (wParam = 0x51) { ; 'Q'
        ; Alt 是否按下
        if (GetKeyState("Alt", "P")) {
            ; 吞掉消息
            return 0
        }
    }
}


; ================================
; 通知与日志函数
; ================================
Notify(msg, type:="tray", duration:=3) {
    if (type = "msgbox") {
        MsgBox, %msg%
    } else if (type = "tooltip") {
        Gui, Tooltip:New, +AlwaysOnTop -Caption +ToolWindow
        Gui, Tooltip:Font, s10
        Gui, Tooltip:Add, Text,, %msg%
        MouseGetPos, xpos, ypos
        Gui, Tooltip:Show, x%xpos% y%ypos%
        Sleep, duration*1000
        Gui, Tooltip:Destroy
    } else if (type = "tray") {
        TrayTip, 通知, %msg%, %duration%, 1
    } else if (type = "sound") {
        SoundBeep, 750, duration*1000
    }
}

Log(msg) {
    global DEBUG_MODE, LOG_FILE
    if (!DEBUG_MODE)
        return
    FormatTime, now, , yyyy-MM-dd HH:mm:ss
    FileAppend, [%now%] %msg%`r`n, %LOG_FILE%
}

; ================================
; 剪贴板变化监控
; ================================
OnClipboardChange("HandleClipboardChange")

HandleClipboardChange(Type) {
    global custom_copy_triggered, ClipSaved, AutoSendToDFCF
    if !custom_copy_triggered {
        current := Clipboard
        if (current != ClipSaved && current != "") {
            ClipSaved := current
            if RegExMatch(ClipSaved, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode) {
                Log("剪贴板检测到股票代码: " . stockCode)
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
    } else {
        Log("剪贴板事件被热键保护拦截")
    }
}

; ================================
; 功能函数
; ================================
SendToDFCF(stockCode) {
    Log("执行 SendToDFCF(" stockCode ")")
    if WinExist("ahk_exe mainfree.exe") {
        WinActivate
        WinWaitActive
        Sleep, 150
        SetKeyDelay, 100
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
    } else {
        Log("DFCF 窗口未找到")
        Notify("DFCF not found:" . stockCode, "tooltip", 1)
    }
}

SendToTDX(stockCode) {
    Log("执行 SendToTDX(" stockCode ")")
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
    Log("执行 SendToHexin(" stockCode ")")
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
; 热键：鼠标中键（仅在特定窗口）
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") 
    || WinActive("ahk_class TdxW_SecondFrame_Class") 
    || WinActive("ahk_exe hexin.exe")

!MButton::   ; Alt + 中键
MButton::
{
    global custom_copy_triggered, ClipSaved,SentCodes
    custom_copy_triggered := true
    WinGet, activeWinID, ID, A
    WinGetActiveTitle, actitle
    Log("中键热键触发于窗口: " . actitle)

    try {
        if WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class") {
            ClipBackup := ClipboardAll
            SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class

            ClipWait, 0.5
            if (ErrorLevel)
                Log("ClipWait 超时")
            else
                Log("ClipWait 成功")

            RegExMatch(Clipboard, "\b\d{6}\b", stockCode)
            Log("提取到代码：" . stockCode)

            if (stockCode != "") {
                if SentCodes.HasKey(stockCode) {
                    Notify("股票代码 " . stockCode . " 已发送过，跳过", "tooltip", 1)
                } else {
                    Notify("热键触发: " . stockCode, "tooltip", 0.8)
                    SendToDFCF(stockCode)
                    SendToHexin(stockCode)
                    SentCodes[stockCode] := true
                }
            } else {
                Notify("未检测到股票代码", "tooltip", 1)
            }

            ;Clipboard := ClipBackup
            
        } else if WinActive("ahk_exe hexin.exe") {
            SendMessage, 0x111, 31067, 0,, a
            if WinExist("ahk_class #32770") {
                WinActivate
                WinWaitActive, ahk_class #32770,, 1
                WinGetActiveTitle, title
                Send {Esc}
                Log("检测到弹窗标题: " . title)
                RegExMatch(title, "\b(?:60|30|00|43|83|87|92)\d{4}\b|(?:688|200)\d{3}\b", stockCode)
                Log("同花顺提取股票代码: " . stockCode)
                if (stockCode != "") {
                    if SentCodes.HasKey(stockCode) {
                        Notify("股票代码 " . stockCode . " 已发送过，跳过", "tooltip", 1)
                    } else {
                        Notify("Hexin热键触发: " . stockCode, "tooltip", 0.8)
                        SendToTDX(stockCode)
                        SendToDFCF(stockCode)
                        SentCodes[stockCode] := true
                    }
                }
            }
        }
    } catch e {
        Log("热键异常: " . e.Message)
        Notify("热键异常: " . e.Message, "tray", 2)
    } finally {
        Sleep, 100
        if (activeWinID) {
            WinActivate, ahk_id %activeWinID%
            WinWaitActive, ahk_id %activeWinID%,, 1
        }
        custom_copy_triggered := false
        Log("热键执行结束")
    }
}
return
#If

; ================================
; 快捷键：切换功能
; ================================
^!d::  ; Ctrl+Alt+D 切换自动推送
AutoSendToDFCF := !AutoSendToDFCF
Notify("AutoSendToDFCF 切换为: " . (AutoSendToDFCF ? "开启" : "关闭"), "tray", 1)
Log("AutoSendToDFCF = " . AutoSendToDFCF)
return

^!L::  ; Ctrl+Alt+L 切换日志模式
DEBUG_MODE := !DEBUG_MODE
msg := DEBUG_MODE ? "🔵 调试日志已开启" : "⚪ 调试日志已关闭"
Notify(msg, "tray", 1)
Log("====== " msg " ======")
return
