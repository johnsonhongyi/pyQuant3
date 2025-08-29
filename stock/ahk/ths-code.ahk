;作者微信：sunwind1576157
;开发时间：2020年2月12日22:38:54
;功能说明：稳定获取同花顺软件中正在浏览的股票代码
;最新版本：https://blog.csdn.net/liuyukuan/article/details/104288389

;#If WinActive("ahk_class Afx:006C0000:b:00010005:00000006:00010C2F") || WinActive("ahk_class #32770")
#If WinActive("ahk_exe hexin.exe")
;MButton::
#z::

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
    Sleep, 10
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
    SetKeyDelay, 30
    ;SendInput, %stockCode%
    Send, %stockCode%
    Sleep, 250
    Send, {Enter}
    ;MsgBox %stockCode%
} else {
    MsgBox, ❌ 找不到TDX终端窗口。
}

return