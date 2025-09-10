; ================================
; 全局变量
; ================================
#Persistent

global ClipSaved := Clipboard
global custom_copy_triggered := false
global AutoSendToDFCF := true   ; <<< 开关：true=复制即推送，false=只提示不推送

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
        SetKeyDelay, 50
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
    global custom_copy_triggered, ClipSaved
    custom_copy_triggered := true

    ; ================================
    ; 逻辑分支
    ; ================================
    WinGet, activeWinID, ID, A

    if WinActive("ahk_class TdxW_MainFrame_Class") 
        || WinActive("ahk_class TdxW_SecondFrame_Class") 
    {

        ClipBackup := ClipboardAll
        ;ClipBackup := Clipboard
        ; 标记：接下来的剪贴板变化由我们触发，需要忽略回调

        ; 发送 TDX 的消息（你原来用的 0x111,33819）
        SendMessage, 0x111, 33819, 0,, ahk_class TdxW_MainFrame_Class

        ; 等待剪贴板被更新
        ClipWait, % timeout_sec
        if (ErrorLevel) {
            ;Log("FetchCodeFromTDX: ClipWait timeout")
            ClipSaved := Clipboard  ; 尝试读一下（可能没有变化）
        } else {
            ClipSaved := Clipboard
            ;Log("FetchCodeFromTDX: got clipboard: " . SubStr(new,1,200))
        }

        ; 恢复原来剪贴板
        Clipboard := ClipBackup
        Sleep, 50  ; 给系统一点时间

        ; 通过消息号获取股票代码
        ;SendMessage,0x111,33819,0,,ahk_class TdxW_MainFrame_Class
        RegExMatch(ClipSaved,  "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode)
        if (stockCode != "") {
            Notify("热键触发代码: " . stockCode, "tooltip", 1)
        }
        ;custom_copy_triggered := false
        ; → 从 TDX 联动到 东方财富 + 同花顺
        SendToDFCF(stockCode)
        SendToHexin(stockCode)
        ;Notify("通达信联动股成功: " . stockCode, "tray", 1)

    }
    else if WinActive("ahk_exe hexin.exe") {
        ; → 从同花顺提取股票代码
        SendMessage,0x111,31067,0,,a
        if WinExist("ahk_class #32770") {
            WinActivate
            WinWaitActive
            WinGetActiveTitle, title
            Send {Esc}
            RegExMatch(title,  "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", stockCode)
            if (stockCode != "") {
                Notify("热键触发代码: " . stockCode, "tooltip", 1)
            }
        }
        ; 再联动到 TDX + 东方财富
        SendToTDX(stockCode)
        SendToDFCF(stockCode)
        ;Notify("同花顺联动成功: " . stockCode, "tray", 1)
    }
    Sleep, 100
    WinActivate, ahk_id %activeWinID%
    WinWaitActive, ahk_id %activeWinID%
    ; 清除标志
    custom_copy_triggered := false
return

#If


; =====================
; 热键：切换开关
; =====================
^!d::  ; Ctrl+Alt+D 切换自动推送开关
AutoSendToDFCF := !AutoSendToDFCF
Notify("AutoSendToDFCF 切换为: " . (AutoSendToDFCF ? "开启" : "关闭"), "tray", 1)
return