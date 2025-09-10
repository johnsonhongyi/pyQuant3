#NoEnv
#SingleInstance force
#Persistent
#Requires AutoHotkey v1.1
SetTitleMatchMode, 2
SendMode Input

; ---------------------------
; 全局设置
; ---------------------------
global ClipSaved := Clipboard
global custom_copy_triggered := false
global ClipMonitor := true      ; Ctrl+Alt+C 切换
global ClipAutoSend := true     ; Ctrl+Alt+D 切换，是否自动把剪贴板的 code 发送到 DFCF
global LogFile := A_ScriptDir "\ahk_link.log"

; 启用剪贴板变化回调
OnClipboardChange("HandleClipboardChange")

; ---------------------------
; 日志（用于调试）
; ---------------------------
Log(msg) {
    time := A_Now
    FileAppend, %time% - %msg%`n, %LogFile%
}



; ================================
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

; ---------------------------
; 剪贴板变化回调
; ---------------------------
HandleClipboardChange(Type) {
    global custom_copy_triggered, ClipSaved, ClipMonitor, ClipAutoSend
    ; 仅在开关打开且为文本变化时处理
    if (!ClipMonitor)
        return
    if (Type != 1)  ; 1 = text
        return

    ; 如果是本脚本写入的临时内容，忽略一次并复位标志
    if (custom_copy_triggered) {
        custom_copy_triggered := false
        Log("HandleClipboardChange: ignored self-change")
        return
    }

    current := Clipboard
    if (current = "" || current = ClipSaved)
        return

    ClipSaved := current
    ;Log("HandleClipboardChange: new clipboard: " . SubStr(current, 1, 200))
    if RegExMatch(ClipSaved, "\d{6}", found) {
        stockCode := found
        ;NotifyTooltip("剪贴板读取: " code, 1000)
        Notify("检测到股票代码: " . stockCode, "sound", 0.3)
        if (ClipAutoSend) {
            Log("Auto sending code to DFCF: " . stockCode)
            SendToDFCF(stockCode)
        }
    }
}

; ---------------------------
; 辅助发送函数（根据你机器环境可调整等待/延时）
; ---------------------------

; ================================
; 功能函数
; ================================
SendToDFCF(stockCode) {
    if WinExist("ahk_exe mainfree.exe") {
        WinActivate
        WinWaitActive
        Sleep, 150
        SetKeyDelay, 200
        Send, %stockCode%
        Sleep, 500
        Send, {Enter}
        Sleep, 100
        Log("SendToDFCF sent: " . stockCode)
    } else {
        Log("SendToDFCF: mainfree.exe not found")
        ;NotifyTooltip("DFCF not found", 1000)
    }
}

SendToTDX(stockCode) {
    if WinExist("ahk_class TdxW_MainFrame_Class") {
        WinActivate
        WinWaitActive
        SetKeyDelay, 80
        Send, %stockCode%
        Sleep, 200
        Send, {Enter}
        Log("SendToTDX sent: " . stockCode)
    } else {
        Log("SendToTDX: TDX not found")
    }

}

SendToHexin(stockCode) {
    if WinExist("ahk_exe hexin.exe") {
        WinActivate
        WinWaitActive
        SetKeyDelay, 80
        Send, %stockCode%
        Sleep, 150
        Send, {Enter}
        Log("SendToHexin sent: " . stockCode)
    } else {
        Log("SendToHexin: hexin.exe not found")
    }
}


SendAllTDX(stockCode) {
    ; 三端同步：DFCF, Hexin, TDX（顺序可调整）
    SendToDFCF(stockCode)
    Sleep, 120
    SendToHexin(stockCode)
    Sleep, 120
    SendToTDX(stockCode)
}

; ---------------------------
; 从 TDX 获取 code（通过 SendMessage -> clipboard）
; 安全地保存/恢复剪贴板，防止 OnClipboardChange 干扰
; ---------------------------
FetchCodeFromTDX(timeout_sec := 1) {
    global ClipSaved, custom_copy_triggered
    ; 备份当前剪贴板（完整内容）
    ClipBackup := ClipboardAll
    ;ClipBackup := Clipboard
    ; 标记：接下来的剪贴板变化由我们触发，需要忽略回调

    ; 发送 TDX 的消息（你原来用的 0x111,33819）
    SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class

    ; 等待剪贴板被更新
    ClipWait, % timeout_sec
    if (ErrorLevel) {
        Log("FetchCodeFromTDX: ClipWait timeout")
        new := Clipboard  ; 尝试读一下（可能没有变化）
    } else {
        new := Clipboard
        Log("FetchCodeFromTDX: got clipboard: " . SubStr(new,1,200))
    }

    ; 恢复原来剪贴板
    Clipboard := ClipBackup
    Sleep, 50  ; 给系统一点时间
    ;custom_copy_triggered := false

    ; 返回捕获到的 6 位码（如果有）
    if RegExMatch(new, "\d{6}", m) {
        return m
    }
    return ""  ; 没有拿到
}

; ================================
; 热键：鼠标中键（只在特定程序生效）
; ================================
#If WinActive("ahk_class TdxW_MainFrame_Class") 
    || WinActive("ahk_class TdxW_SecondFrame_Class") 
    || WinActive("ahk_exe hexin.exe")

MButton::
    global custom_copy_triggered, ClipSaved
    custom_copy_triggered := true

    ; ================================
    ; 逻辑分支
    ; ================================
    if WinActive("ahk_class TdxW_MainFrame_Class") 
        || WinActive("ahk_class TdxW_SecondFrame_Class") 
    {
        stockCode := FetchCodeFromTDX(1)
        if (stockCode != "") {
            ;NotifyTooltip("TDX读取: " . stockCode, 1000)
            ;Notify("通达信读取: " . stockCode, "tooltip", 1)
            Notify("通达信读取: " . stockCode, "tooltip", 1)
            ;SendAllTDX(stockCode)  ; 或者只 SendToDFCF / SendToHexin
            ;return
            Sleep, 150
            SendToHexin(stockCode)
            SendToDFCF(stockCode)
        }
       
    }
    else if WinActive("ahk_exe hexin.exe") {
        ; → 从同花顺提取股票代码
        SendMessage,0x111,31067,0,,a
        if WinExist("ahk_class #32770") {
            WinActivate
            WinWaitActive
            WinGetActiveTitle, title
            Send {Esc}
            RegExMatch(title, "\d{6}", stockCode)
            if (stockCode != "") {
                Notify("同花顺读取: " . stockCode, "tooltip", 1)
            }
        }
        ; 再联动到 TDX + 东方财富
        SendToTDX(stockCode)
        SendToDFCF(stockCode)
        ;Notify("同花顺联动成功: " . stockCode, "tray", 1)
    }

    ; 清除标志
    custom_copy_triggered := false
return



; ---------------------------
; 全局热键：开关与调试
; ---------------------------
^!c::  ; Ctrl+Alt+C 切换剪贴板监控
    ClipMonitor := !ClipMonitor
    ;NotifyTooltip(ClipMonitor ? "Clip monitor ON" : "Clip monitor OFF", 1000)
    Notify("ClipMonitor: " . (ClipMonitor ? "Clip monitor ON" : "Clip monitor OFF"), "tray", 2)
    Log("ClipMonitor toggled: " . (ClipMonitor ? "ON" : "OFF"))
return

^!d::  ; Ctrl+Alt+D 切换自动推送开关
    ClipAutoSend := !ClipAutoSend
    ;NotifyTooltip(ClipAutoSend ? "AutoSend ON" : "AutoSend OFF", 1000)
    Notify("AutoSendToDFCF 切换为: " . (ClipAutoSend ? "ON" : "OFF"), "tray", 2)
    Log("ClipAutoSend toggled: " . (ClipAutoSend ? "ON" : "OFF"))
return


^!r::  ; Ctrl+Alt+R 手动写一条 log 用于测试
    Log("Manual log entry by user")
    ;NotifyTooltip("Logged", 800)
return



/*
; ---------------------------
; 单一条件热键（避免多处 #If 重复绑定）
; 在 TDX 主/副页面生效
; ---------------------------
#If WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class")
MButton::
    ; 当鼠标中键在 TDX 页面按下时
    global ClipSaved, custom_copy_triggered
    Log("MButton pressed in TDX")

    ; 方案 A: 通过消息号让 TDX 把 code 放到剪贴板（更可靠）
    code := FetchCodeFromTDX(1)
    if (code != "") {
        NotifyTooltip("TDX读取: " . code, 1000)
        SendAllTDX(code)  ; 或者只 SendToDFCF / SendToHexin
        return
    }

    
    ; 方案 B: 如果上面失败，退回到剪贴板现有值（ClipSaved）
    if RegExMatch(ClipSaved, "\d{6}", found) {
        code := found
        NotifyTooltip("Use existing clipboard: " . code, 900)
        SendAllTDX(code)
    } else {
        NotifyTooltip("No 6-digit code found", 900)
        Log("MButton: no code found in clipboard or Fetch")
    }
    
return
#If
*/



/*
; 通过消息号获取股票代码
SendMessage,0x111,33819,0,,ahk_class TdxW_MainFrame_Class
RegExMatch(Clipboard, "\d{6}", stockCode)
if (stockCode != "") {
    Notify("热键触发代码: " . stockCode, "tooltip", 1)
}
;custom_copy_triggered := false
; → 从 TDX 联动到 东方财富 + 同花顺
SendToDFCF(stockCode)
SendToHexin(stockCode)
;Notify("通达信联动股成功: " . stockCode, "tray", 1)



; ---------------------------
; Tooltip 通知（精确控制显示 ms）
; ---------------------------
NotifyTooltip(msg, duration_ms := 1200) {
    Tooltip, %msg%
    SetTimer, ClearTooltip, -%duration_ms%
}
ClearTooltip:
    Tooltip
return


*/