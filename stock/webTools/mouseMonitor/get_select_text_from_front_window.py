from ctypes import *
import win32gui
import win32api
import win32con


user32 = windll.user32
kernel32 = windll.kernel32

class RECT(Structure):
 _fields_ = [
     ("left", c_ulong),
     ("top", c_ulong),
     ("right", c_ulong),
     ("bottom", c_ulong)
 ]

class GUITHREADINFO(Structure):
 _fields_ = [
     ("cbSize", c_ulong),
     ("flags", c_ulong),
     ("hwndActive", c_ulong),
     ("hwndFocus", c_ulong),
     ("hwndCapture", c_ulong),
     ("hwndMenuOwner", c_ulong),
     ("hwndMoveSize", c_ulong),
     ("hwndCaret", c_ulong),
     ("rcCaret", RECT)
 ]



def get_selected_text_from_front_window(): # As String
    ''' vb6 to python translation '''

    gui = GUITHREADINFO(cbSize=sizeof(GUITHREADINFO))
    txt=''
    ast_Clipboard_Obj=None
    Last_Clipboard_Temp = -1

    hwndW = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwndW)
    tid = win32gui.FindWindowEx( hwndW , None , 'Edit' ,None ) #查找子句柄
    hwnd = tid
    # DlgItem=win32gui.GetDlgItem(hwnd, 8011) #symbol
    # user32.GetGUIThreadInfo(DlgItem, byref(gui))
    # control = win32gui.FindWindowEx(hwnd, 0, 'Edit', None)
    # controldlgid = win32gui.GetDlgCtrlID(control)
    # print("controldlgid:",controldlgid)
    # try:
    #     mytext = win32gui.GetDlgItemText(hwnd, controldlgid)
    #     print("mytext:",mytext)
    # except:
    #     print('an error occured')


    txt = GetCaretWindowText(hwnd, True)

    '''
    if Txt = "" Then
        LastClipboardClip = ""
        Last_Clipboard_Obj = GetClipboard
        Last_Clipboard_Temp = LastClipboardFormat
        SendKeys "^(c)"
        GetClipboard
        Txt = LastClipboardClip
        if LastClipboardClip <> "" Then Txt = LastClipboardClip
        RestoreClipboard Last_Clipboard_Obj, Last_Clipboard_Temp
        print "clbrd: " + Txt
    End If
    '''    
    return txt



def GetCaretWindowText(hWndCaret, Selected = False): # As String

    startpos =0
    endpos =0

    txt = ""

    if hWndCaret:

        # 获取 联系人系列 batys, 隐藏功能
        length = win32gui.SendMessage(hWndCaret, win32con.WM_GETTEXTLENGTH)
        new_length = length * 2 + 2 # 重点
        # 生成 buffer 对象
        buf = win32gui.PyMakeBuffer(new_length)
        win32api.SendMessage(hWndCaret, win32con.WM_GETTEXT, new_length, buf)
        address, result_length = win32gui.PyGetBufferAddressAndLen(buf)
        text = win32gui.PyGetString(address, result_length)
        buf.release()
        del buf
        # print('长度',length)
        print(text[:length])


        # # buf_size = 1 + win32gui.SendMessage(hWndCaret, win32con.WM_GETTEXTLENGTH, 0, 0)
        # length =   win32gui.SendMessage(hWndCaret, win32con.WM_GETTEXTLENGTH, 0, 0)
        # # The messages WM_GETTEXTLENGTH returns the length of the text in characters (excluding the terminating null character) and the maximum buffer length given to WM_GETTEXT also is based on characters (including the terminating null character).
        # # A character in the NT-based Windows systems is encoded in a double-byte character set (DBCS), meaning two bytes per character.
        # # The function win32gui.PyMakeBuffer(length) returns a buffer of length bytes.
        # # So if length is the return value of WM_GETTEXTLENGTH, the reserved buffer should be length * 2 + 2  bytes long and the maximum buffer length given to WM_GETTEXT should be length + 1.
        # buf_size = length * 2 + 2

        # if buf_size:

        #     buf = win32gui.PyMakeBuffer(buf_size)
        #     # win32gui.SendMessage(hWndCaret, win32con.WM_GETTEXT, buf_size, buffer)
        #     win32gui.SendMessage(hWndCaret, win32con.WM_GETTEXT, buf_size, buf)
        #     try:
        #          address, length = win32gui.PyGetBufferAddressAndLen(buf)  # 获取容器的内存地址
        #     except ValueError:
        #         print('error')
        #         return
        #     text = win32gui.PyGetString(address, length)  # 取得字符串
        #     # txt = buf[:buf_size]
        #     buf.release()
        #     del buf
        #     print('长度',length)
        #     print(txt)

        if Selected and new_length:
            selinfo  = win32gui.SendMessage(hWndCaret, win32con.EM_GETSEL, 0, 0)
            endpos   = win32api.HIWORD(selinfo)
            startpos = win32api.LOWORD(selinfo)
            return txt[startpos: endpos]

    return txt

if __name__ == '__main__':
    import time
    #can copy notepad  edit all text  not highlight
    for x in range(5):
        print(x)
        time.sleep(3)
        print(get_selected_text_from_front_window())