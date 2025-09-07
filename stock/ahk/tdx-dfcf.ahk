;---- ---- 通达信联动东方财富---- ----  

; 检查 AutoHotkey 版本是否为 v1.1+
#Requires AutoHotkey v1.1

; 保持脚本常驻内存，以便持续监听剪贴板变化
#Persistent

global custom_copy_triggered := false


; 设置 OnClipboardChange 函数，当剪贴板内容变化时，调用 CheckClipboard()
;OnClipboardChange("CheckClipboard")
OnClipboardChange("HandleClipboardChange")

return

; -----------------------------------------------------
; 函数定义
; -----------------------------------------------------

CheckClipboard()
{
    ; 在新内容到达前，清空剪贴板，避免处理旧内容
    ; 如果剪贴板为空，则 ClipWait 会等待内容
    local
    clipboard_content := ""
    ClipWait, 0.2 ; 等待剪贴板内容到达，超时0.2秒

    ; 检查剪贴板是否真的包含文本
    if (ErrorLevel) {
        return ; 如果超时或剪贴板不含文本，则退出
    }

    ; 使用正则表达式查找6位数字
    ; \b - 单词边界，确保匹配独立的6位数字，而不是长数字的一部分
    ; \d{6} - 匹配精确的6位数字
    ; $1 - 将第一个捕获组（括号内的内容）赋值给变量
    ;if RegExMatch(Clipboard, "\b(\d{6})\b", found_match)

    ; 使用正则表达式查找以指定数字开头的6位数字
    ; (^|\s) - 匹配字符串开头或空格，确保数字是独立的
    ; (60|30|00|688|43|83|87|92) - 匹配指定开头的数字
    ; \d{6-len(start)} - 匹配剩余的数字，例如如果开头是"60"（2位），则匹配4位数字。
    ; 这里我们直接用 \d{4} 来匹配2位开头的情况，或者直接用 \d{3} 匹配3位开头的情况，这样更通用。
    ; 完整模式: \b(60|30|00|688|43|83|87|92)\d{6-len(start)}\b
    
    ; 最终的正则表达式模式，匹配以指定前缀开头的6位数字。
    ; 例如: \b(60)\d{4}\b 或 \b(688)\d{3}\b
    ; 为简化起见，可以匹配以指定数字开头的6位数字。
    
    ; \b((60|30|00)\d{4}|(688|43|83|87|92)\d{3})\b
    ; 简化为：匹配指定前缀，后跟3或4个数字，总共6位
    ; 匹配以 60/30/00/43/83/87/92 开头的6位，或者 688/200 开头的6位

    ;"603268 bytes_str:b'\x11603268' bytes_str.hex():11363033323638"
    ;"发送成功code:603268 bytes_str:b'\x11603268' bytes_str.hex():11363033323638"
    ;RegExMatch(Clipboard, "(?<!\d)((?:60|30|00|43|83|87|92)\d{4}|(?:688|200)\d{3})(?!\d)", found_match)

    ;if RegExMatch(Clipboard, "\b((?:60|30|00|43|83|87|92)\d{4}|(?:688|200)\d{3})\b", found_match)
    ;if RegExMatch(Clipboard, "(?<!\d)((?:60|30|00|43|83|87|92)\d{4}|(?:688|200)\d{3})(?!\d)", found_match)

    if RegExMatch(Clipboard, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", found_match)

    {
        ; 找到匹配，将提取的6位数字存储到变量中
        six_digits := found_match
        
        ; 提示用户已找到6位数字
        
        MsgBox, 0x40,, 剪贴板中检测到6位数字: %six_digits%
        
        ; 你可以在这里添加其他操作，例如：
        ; Send, %six_digits% ; 自动发送数字
        ; Run, "https://example.com/?code=" . six_digits ; 用数字打开网页
        ;SendAllTDX(six_digits)
        ; 获取当前活动窗口 → 保存句柄
        WinGet, activeWinID, ID, A
        Sleep, 100
        SendDFCF(six_digits)
        Sleep, 100
        ; 返回之前的窗口
        WinActivate, ahk_id %activeWinID%
        WinWaitActive, ahk_id %activeWinID%
    }
}

; 这是 OnClipboardChange 的回调函数
HandleClipboardChange(Type) {
    global custom_copy_triggered
    
    ; 检查标志
    if custom_copy_triggered {
        ; 如果标志为 true，说明是自定义复制操作触发的
        ; 执行一次，然后重置标志为 false
        custom_copy_triggered := false
        
        ; 执行你的功能，例如：
        ;MsgBox, 0x40,,OnClipboardChange 触发，但已被热键处理
        
        ; 提示 1.5 秒后自动消失
        ;SetTimer(() => ToolTip(), -1500)
    } else {
        ; 如果标志为 false，说明是其他原因触发的，忽略
        ;MsgBox, 0x40,,custom_copy_triggered_CheckClipboard
        CheckClipboard()
        return
    }
}


SendDFCF(stockCode) {
    ;MsgBox ,%stockCode%
    ; 激活同花顺
    ; 激活东方财富终端
    if WinExist("ahk_exe mainfree.exe") {
        WinActivate
        WinWaitActive
        ; 模拟打开搜索框（假设 Ctrl+F 可用）
        ;Send, ^f
        Sleep, 80

        ; 直接输入股票代码
        ;SetKeyDelay 1000
        SetKeyDelay, 80
        ;SendInput, %stockCode%
        Send, %stockCode%
        Sleep, 100
        Send, {Enter}
        ;MsgBox %stockCode%
    } else {
        ;MsgBox, ❌ 找不到东方财富终端窗口。
    }

    return
    

}

SendAllTDX(stockCode) {
    ;MsgBox ,%stockCode%
    ; 激活同花顺
    ; 激活东方财富终端
    if WinExist("ahk_exe mainfree.exe") {
        WinActivate
        WinWaitActive
        ; 模拟打开搜索框（假设 Ctrl+F 可用）
        ;Send, ^f
        Sleep, 150

        ; 直接输入股票代码
        ;SetKeyDelay 1000
        SetKeyDelay, 100
        ;SendInput, %stockCode%
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
        ;MsgBox %stockCode%
    } else {
        ;MsgBox, ❌ 找不到东方财富终端窗口。
    }

    ; 激活同花顺
    if WinExist("ahk_exe hexin.exe") {
        WinActivate
        WinWaitActive
        ; 模拟打开搜索框（假设 Ctrl+F 可用）
        ;Send, ^f
        ;Sleep, 100

        ; 直接输入股票代码
        SetKeyDelay, 50
        ;SendInput, %stockCode%
        Send, %stockCode%
        Sleep, 100
        Send, {Enter}
        ;MsgBox %stockCode%
    } else {
        ;MsgBox, ❌ 找不到同花顺窗口。
    }

    if WinExist("ahk_class TdxW_MainFrame_Class") {
        WinActivate
        WinWaitActive
        ; 模拟打开搜索框（假设 Ctrl+F 可用）
        ;Send, ^f
        Sleep, 150

        ; 直接输入股票代码
        ;SetKeyDelay 1000
        SetKeyDelay, 50
        ;SendInput, %stockCode%
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
        ;MsgBox, 0x40,,TdxW_MainFrame_Class %stockCode%
    } else {
        ;MsgBox, ❌ 找不到TDX终端窗口。
    }

    ;if WinExist("ahk_class TdxW_MainFrame_Class") {
    ;    WinActivate
    ;    }
    return
    

}


#SingleInstance force
SetTitleMatchMode 2 
;#IfWinActive,ahk_class TdxW_MainFrame_Class  ahk_exe TdxW.exe
;#IfWinActive,ahk_class TdxW_SecondFrame_Class ahk_exe TdxW.exe  

#If WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class")
{
    MButton::
    ;Z::
    ;鼠标中键
    ; 在执行自定义功能前设置标志为 true
    global custom_copy_triggered
    custom_copy_triggered := true

    ;GroupAdd, EditingApps,ahk_class TdxW_MainFrame_Class  ahk_exe TdxW.exe
    ;GroupAdd, EditingApps,ahk_class TdxW_SecondFrame_Class ahk_exe TdxW.exe 
    ;#IfWinActive, ahk_group EditingApps 

    #If WinActive("ahk_class TdxW_MainFrame_Class")
    {
        SendMessage,0x111,33819,0,,ahk_class TdxW_MainFrame_Class
        ;联动精灵  5208115txwd   1q2w3e4r!!!
        ;打开副屏一,二,三,一键四屏
        ;if !WinExist("ahk_class TdxW_SecondFrame_Class")
        ;{
            ;SendMessage,0x111,3356,0,,ahk_class TdxW_MainFrame_Class
            ;SendMessage,0x111,3357,0,,ahk_class TdxW_MainFrame_Class
            ;SendMessage,0x111,3357,0,,ahk_class TdxW_MainFrame_Class
            ;一键四屏
            ;SendMessage,0x111,3361,0,,ahk_class TdxW_MainFrame_Class
            ;平铺
            ;SendMessage,0x111,3364,0,,ahk_class TdxW_MainFrame_Class
        ;}

        Sleep,100
        ;A_Clipboard  :=clipboard 
        RegExMatch(Clipboard, "\d{6}", stockCode)
        ;MsgBox %stockCode%
        ;用消息号获取当前浏览的股票名称代码黏贴到剪贴板
        ;Sleep,100 
        ;看电脑配置,自己修改等待反应的时间
        ;Send, %Clipboard%
        ;Sleep,500
        ;Send, {Enter}
        #If

        ; 激活东方财富终端
        if WinExist("ahk_exe mainfree.exe") {
            WinActivate
            WinWaitActive
            ; 模拟打开搜索框（假设 Ctrl+F 可用）
            ;Send, ^f
            Sleep, 150

            ; 直接输入股票代码
            ;SetKeyDelay 1000
            SetKeyDelay, 100
            ;SendInput, %stockCode%
            Send, %stockCode%
            Sleep, 250
            Send, {Enter}
            ;MsgBox %stockCode%
        } else {
            ;MsgBox, ❌ 找不到东方财富终端窗口。
        }

        ; 激活同花顺
        if WinExist("ahk_exe hexin.exe") {
            WinActivate
            WinWaitActive
            ; 模拟打开搜索框（假设 Ctrl+F 可用）
            ;Send, ^f
            ;Sleep, 100

            ; 直接输入股票代码
            SetKeyDelay, 50
            ;SendInput, %stockCode%
            Send, %stockCode%
            Sleep, 100
            Send, {Enter}
            ;MsgBox %stockCode%
        } else {
            ;MsgBox, ❌ 找不到同花顺终端窗口。
        }
        ;if WinExist("ahk_class TdxW_MainFrame_Class") {
        ;    WinActivate
        ;    }
        return
    }

    #If WinActive("ahk_class TdxW_SecondFrame_Class")
    {
        SendMessage,0x111,33819,0,,ahk_class TdxW_SecondFrame_Class
        ;联动精灵  5208115txwd   1q2w3e4r!!!
        ;打开副屏一,二,三,一键四屏
        ;if !WinExist("ahk_class TdxW_SecondFrame_Class")
        ;{
            ;SendMessage,0x111,3356,0,,ahk_class TdxW_MainFrame_Class
            ;SendMessage,0x111,3357,0,,ahk_class TdxW_MainFrame_Class
            ;SendMessage,0x111,3357,0,,ahk_class TdxW_MainFrame_Class
            ;一键四屏
            ;SendMessage,0x111,3361,0,,ahk_class TdxW_MainFrame_Class
            ;平铺
            ;SendMessage,0x111,3364,0,,ahk_class TdxW_MainFrame_Class
        ;}

        Sleep,100
        ;A_Clipboard  :=clipboard 
        RegExMatch(Clipboard, "\d{6}", stockCode)
        ;MsgBox %stockCode%
        ;用消息号获取当前浏览的股票名称代码黏贴到剪贴板
        ;Sleep,100 
        ;看电脑配置,自己修改等待反应的时间
        ;Send, %Clipboard%
        ;Sleep,500
        ;Send, {Enter}
        #If

        ; 激活东方财富终端
        if WinExist("ahk_exe mainfree.exe") {
            WinActivate
            WinWaitActive
            ; 模拟打开搜索框（假设 Ctrl+F 可用）
            ;Send, ^f
            Sleep, 150

            ; 直接输入股票代码
            ;SetKeyDelay 1000
            SetKeyDelay, 100
            ;SendInput, %stockCode%
            Send, %stockCode%
            Sleep, 250
            Send, {Enter}
            ;MsgBox %stockCode%
        } else {
            ;MsgBox, ❌ 找不到东方财富终端窗口。
        }

        ; 激活同花顺
        if WinExist("ahk_exe hexin.exe") {
            WinActivate
            WinWaitActive
            ; 模拟打开搜索框（假设 Ctrl+F 可用）
            ;Send, ^f
            ;Sleep, 100

            ; 直接输入股票代码
            SetKeyDelay, 50
            ;SendInput, %stockCode%
            Send, %stockCode%
            Sleep, 100
            Send, {Enter}
            ;MsgBox %stockCode%
        } else {
            ;MsgBox, ❌ 找不到同花顺终端窗口。
        }

        if WinExist("ahk_class TdxW_SecondFrame_Class") {
            WinActivate
            }
        return
    }

}



#If WinActive("ahk_exe hexin.exe")
{
    MButton::
    ;#z::

    #If WinActive("ahk_exe hexin.exe")
    {
        ;SendMessage,0x111,33819,0,,ahk_class Afx:00690000:b:00010007:00000006:00380F7B
        SendMessage,0x111,31067,0,,a   ;打开 持股机构
    }

    ;MsgBox 123
    ;PostMessage,0x111,31067,0,,a   ;打开 持股机构
    ;WinActivate,持股机构
    ;WinWaitActive,持股机构, , 2
    ;if !ErrorLevel
    ;if WinExist("
    ;if WinActive("ahk_class #32770")") {

    if WinExist("ahk_class #32770") {
        WinActivate
        WinWaitActive
        WinGetActiveTitle,title
        ;Sleep, 5
        Send {Esc}  ;关闭标记股票窗口
        ;stocktitle:=StrSplit(title,"-")
        ;MsgBox %title%
        RegExMatch(title, "\d{6}", stockCode)
        ;MsgBox % stockCode
    }

    if WinExist("ahk_class TdxW_MainFrame_Class") {
        WinActivate
        WinWaitActive
        ; 模拟打开搜索框（假设 Ctrl+F 可用）
        ;Send, ^f
        Sleep, 100

        ; 直接输入股票代码
        ;SetKeyDelay 1000
        SetKeyDelay, 50
        ;SendInput, %stockCode%
        Send, %stockCode%
        Sleep, 250
        Send, {Enter}
        ;MsgBox %stockCode%
    } else {
        ;MsgBox, ❌ 找不到TDX终端窗口。
    }

    ; 激活东方财富终端
        if WinExist("ahk_exe mainfree.exe") {
            WinActivate
            WinWaitActive
            ; 模拟打开搜索框（假设 Ctrl+F 可用）
            ;Send, ^f
            Sleep, 150

            ; 直接输入股票代码
            ;SetKeyDelay 1000
            SetKeyDelay, 100
            ;SendInput, %stockCode%
            Send, %stockCode%
            Sleep, 250
            Send, {Enter}
            ;MsgBox %stockCode%
        } else {
            ;MsgBox, ❌ 找不到东方财富终端窗口。
        }

    if WinExist("ahk_exe hexin.exe") {
        WinActivate
        }
    return
}

/*
Clipboard := "603268 bytes_str:b'\x11603268'"
RegExMatch(Clipboard, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", found_match)
MsgBox % found_match  ; 输出 603268 ✅

Clipboard := "6032681 bytes_str:b'\x11603268'"
RegExMatch(Clipboard, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", found_match)
MsgBox % found_match  ; 不匹配 ❌

Clipboard := "发送成功code:603268"
RegExMatch(Clipboard, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", found_match)
MsgBox % found_match  ; 不匹配 ❌

Clipboard := "688001abc"
RegExMatch(Clipboard, "^(?:60|30|00|43|83|87|92)\d{4}(?!\d)|^(?:688|200)\d{3}(?!\d)", found_match)
MsgBox % found_match  ; 输出 688001 ✅

*/