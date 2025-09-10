; 检查 AutoHotkey 版本是否为 v1.1+
#Requires AutoHotkey v1.1

; 保持脚本常驻内存，以便持续监听剪贴板变化
#Persistent

; 设置 OnClipboardChange 函数，当剪贴板内容变化时，调用 CheckClipboard()
OnClipboardChange("CheckClipboard")

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
    if RegExMatch(Clipboard, "\b(\d{6})\b", found_match)
    {
        ; 找到匹配，将提取的6位数字存储到变量中
        six_digits := found_match1
        
        ; 提示用户已找到6位数字
        MsgBox, 0x40,, 剪贴板中检测到6位数字: %six_digits%
        
        ; 你可以在这里添加其他操作，例如：
        ; Send, %six_digits% ; 自动发送数字
        ; Run, "https://example.com/?code=" . six_digits ; 用数字打开网页
    }
}
