import win32gui
import win32con
import win32api

# 明确要查找的主窗口的类名，通过类名查找主窗口，类名可以通过spy++找到
# 比如浏览器窗口的类名是Chrome_WidgetWin_1，下面会传图

mainwindow_classname='MainWindowClassName'
mainwindow_name=None
# 获得主窗口的句柄
main_hwnd = win32gui.FindWindow(mainwindow_classname, mainwindow_name)
# 定位要操作的combobox，
child_hwnd = win32gui.FindWindowEx(main_hwnd, None, 'ComboBox', None)

# 如果主窗口下有多个 Combobox,需要多找几次，才能找到我们需要的下拉框
#for i in range(4):
#     child_hwnd = win32gui.FindWindowEx(main_hwnd, child_hwnd, 'ComboBox', None)
# 直接操作 combobox
item_index = 2  # 索引值是从0开始的，这里是第3项
win32api.SendMessage(child_hwnd, win32con.CB_SETCURSEL, item_index, 0)
win32api.SendMessage(win, child_hwnd, win32con.WM_COMMAND, 0)

# 下面获取当前项的内容
# 当前 combobox的当前项的名称字符串长度
length = win32api.SendMessage(child_hwnd, win32con.WM_GETTEXTLENGTH) + 1


# 生成一个存储空间，buf，下面取内容的时候会放在这里
buf = win32gui.PyMakeBuffer(length)
# 获取当前被选中项的索引
now_item_index=win32api.SendMessage(child_hwnd, win32con.CB_GETCURSEL, 0, 0)
win32api.SendMessage(child_hwnd, win32con.CB_GETLBTEXT, now_item_index, buf)

# 找到buf的内存地址
address, length = win32gui.PyGetBufferAddressAndLen(buf[:-1])
# 从内存中取出 combobox的当前项的内容
text = win32gui.PyGetString(address, length)