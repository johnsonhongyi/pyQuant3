;---- ---- 通达信联动东方财富---- ----  
#SingleInstance force
SetTitleMatchMode 2 
;#IfWinActive,ahk_class TdxW_MainFrame_Class  ahk_exe TdxW.exe
;#IfWinActive,ahk_class TdxW_SecondFrame_Class ahk_exe TdxW.exe  

#If WinActive("ahk_class TdxW_MainFrame_Class") || WinActive("ahk_class TdxW_SecondFrame_Class")

MButton::
;Z::
;鼠标中键


;GroupAdd, EditingApps,ahk_class TdxW_MainFrame_Class  ahk_exe TdxW.exe
;GroupAdd, EditingApps,ahk_class TdxW_SecondFrame_Class ahk_exe TdxW.exe 
;#IfWinActive, ahk_group EditingApps 

#If WinActive("ahk_class TdxW_MainFrame_Class")
{
    SendMessage,0x111,33819,0,,ahk_class TdxW_MainFrame_Class
}

#If WinActive("ahk_class TdxW_SecondFrame_Class")
{
    SendMessage,0x111,33819,0,,ahk_class TdxW_SecondFrame_Class
}

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
    SetKeyDelay, 50
    ;SendInput, %stockCode%
    Send, %stockCode%
    Sleep, 250
    Send, {Enter}
    ;MsgBox %stockCode%
} else {
    MsgBox, ❌ 找不到东方财富终端窗口。
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
    MsgBox, ❌ 找不到东方财富终端窗口。
}

return



