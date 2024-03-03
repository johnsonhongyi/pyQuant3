import win32api
import win32con
import win32gui
import clipboard

# @staticmethod
def _fetch_tdx_code():
    tdx_hwnd = win32gui.FindWindow("TdxW_MainFrame_Class", None)
    if tdx_hwnd:
        # 点一下当前股票窗口，尝试修复他取错代码的BUG
        # win32api.SetCursorPos((666, 88))
        # win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        # win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

        #复制当前股票
        win32gui.SendMessage(tdx_hwnd, win32con.WM_COMMAND, 33780, 0)
        import ipdb;ipdb.set_trace()

        # txt = clipboard.copy('text')
        # txt = clipboard.paste()

        if txt:
            code = txt[:6]
            if code.isdigit():
                return code
        else:
            print('找到了Tdxw但没有取到股票代码....看看是啥情况哦！')
    else:
        print("<<<没有找到通达信窗口")
    return ""
_fetch_tdx_code()