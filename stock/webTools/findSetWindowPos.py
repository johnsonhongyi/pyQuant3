from __future__ import print_function

import ctypes
from ctypes.wintypes import HWND, DWORD, RECT
import time
# dwmapi = ctypes.WinDLL("dwmapi")



tdx_ths_position={'通达信':'659, 50, 878,793','东方财富':'268, 0, 1067, 833','同花顺':'0, 20,1075,864','Firefox': '626, 0, 878, 869'}


def set_windows_hwnd_pos(hwnd,pos):
    # # 设置窗口标题
    # window_title = "通达信金融终端V7.642 - [分析图表-平安银行]"
    # window_title = title
    # # # window_title = "tdxw.exe"
    # # # 查找窗口句柄
    # hwnd = ctypes.windll.user32.FindWindowW(None, window_title)

    # rect = RECT()
    # DMWA_EXTENDED_FRAME_BOUNDS = 9
    # dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
    #                              ctypes.byref(rect), ctypes.sizeof(rect))
    # print(rect.left, rect.top, rect.right, rect.bottom)

    # left=644, top=1471, right=44, bottom=874
    # left=805, top=44, right=1835, bottom=1080
    # 设置新的窗口位置
    # x = int(805/1.25) # 新的窗口左上角的x坐标

    # x = 644 # 新的窗口左上角的x坐标
    # y = 44 # 新的窗口左上角的y坐标
    # top=1471
    # bottom=874

    # right=1872
    # bottom=1228
    # 移动窗口
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, top, bottom, 1)

    ctypes.windll.user32.SetForegroundWindow(hwnd)
    pos = pos.split(',')
    x,y = int(pos[0]),int(pos[1])
    width,height = int(pos[2]),int(pos[3])
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)
    print(x,y,width,height)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)

    # 设置新的窗口大小
    # left=644, top=44, width=827, height=830
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # 设定窗口大小
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 2)



def set_windows_pos(title,pos):
    # # 设置窗口标题
    # window_title = "通达信金融终端V7.642 - [分析图表-平安银行]"
    window_title = title
    # # window_title = "tdxw.exe"
    # # 查找窗口句柄
    hwnd = ctypes.windll.user32.FindWindowW(None, window_title)

    # rect = RECT()
    # DMWA_EXTENDED_FRAME_BOUNDS = 9
    # dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
    #                              ctypes.byref(rect), ctypes.sizeof(rect))
    # print(rect.left, rect.top, rect.right, rect.bottom)

    # left=644, top=1471, right=44, bottom=874
    # left=805, top=44, right=1835, bottom=1080
    # 设置新的窗口位置
    # x = int(805/1.25) # 新的窗口左上角的x坐标

    # x = 644 # 新的窗口左上角的x坐标
    # y = 44 # 新的窗口左上角的y坐标
    # top=1471
    # bottom=874

    # right=1872
    # bottom=1228
    # 移动窗口
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, top, bottom, 1)

    ctypes.windll.user32.SetForegroundWindow(hwnd)
    pos = pos.split(',')
    x,y = int(pos[0]),int(pos[1])
    width,height = int(pos[2]),int(pos[3])
    # ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)
    print(x,y,width,height)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, 0, 0, 1)

    # 设置新的窗口大小
    # left=644, top=44, width=827, height=830
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # width = 827 # 新的窗口宽度
    # height = 830 # 新的窗口高度
    # 设定窗口大小
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, width, height, 2)


global list_hwnd
list_hwnd = []
import ctypes
from ctypes import wintypes
from collections import namedtuple

user32 = ctypes.WinDLL('user32', use_last_error=True)

def check_zero(result, func, args):    
    if not result:
        err = ctypes.get_last_error()
        if err:
            raise ctypes.WinError(err)
    return args

if not hasattr(wintypes, 'LPDWORD'): # PY2
    wintypes.LPDWORD = ctypes.POINTER(wintypes.DWORD)

WindowInfo = namedtuple('WindowInfo', 'pid title,left, top, width, height')

WNDENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,    # _In_ hWnd
    wintypes.LPARAM,) # _In_ lParam

user32.EnumWindows.errcheck = check_zero
user32.EnumWindows.argtypes = (
   WNDENUMPROC,      # _In_ lpEnumFunc
   wintypes.LPARAM,) # _In_ lParam

user32.IsWindowVisible.argtypes = (
    wintypes.HWND,) # _In_ hWnd

user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = wintypes.HWND,wintypes.BOOL
user32.ShowWindow.restype = wintypes.BOOL # _In_ hWnd

user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = (
  wintypes.HWND,     # _In_      hWnd
  wintypes.LPDWORD,) # _Out_opt_ lpdwProcessId

user32.GetWindowTextLengthW.errcheck = check_zero
user32.GetWindowTextLengthW.argtypes = (
   wintypes.HWND,) # _In_ hWnd

user32.GetWindowTextW.errcheck = check_zero
user32.GetWindowTextW.argtypes = (
    wintypes.HWND,   # _In_  hWnd
    wintypes.LPWSTR, # _Out_ lpString
    ctypes.c_int,)   # _In_  nMaxCount

def GetWindowRectFromName(hwnd)-> tuple:
    # hwnd = ctypes.windll.user32.FindWindowW(0, name)
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.pointer(rect))
    # print(hwnd)
    # print(rect)
    left = rect.left
    top = rect.top
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return (left, top, width, height)
    # return (rect.left, rect.top, rect.right, rect.bottom)

def get_pos_dwmapi(hwnd):
    rect = RECT()
    DMWA_EXTENDED_FRAME_BOUNDS = 9
    dwmapi.DwmGetWindowAttribute(HWND(hwnd), DWORD(DMWA_EXTENDED_FRAME_BOUNDS),
                                 ctypes.byref(rect), ctypes.sizeof(rect))
    return rect.left, rect.right, rect.top, rect.bottom


def list_find_windows(proc):
    '''Return a sorted list of visible windows.'''
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)

            if len(title.value) > 0:
                # print(title.value)
                # left, right, top, bottom = get_pos(hWnd)
                if title.value.find(proc) >= 0:
                    # print(title.value)
                    left, top, width, height = GetWindowRectFromName(hWnd)
                    if left < 0 and top < 0:

                        # user32.ShowWindow(hWnd, SW_Restore);
                        time.sleep(0.1)
                        user32.ShowWindow(hWnd, SW_Normal);
                        left, top, width, height = GetWindowRectFromName(hWnd)

                    # left, right, top, bottom = GetWindowRectFromName(hWnd)
                    # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                    result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return sorted(result)
    # return sorted(result)


def set_proc_windows_position(proc):
    '''Return a sorted list of visible windows.'''
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)

            if len(title.value) > 0:
                # print(title.value)
                # left, right, top, bottom = get_pos(hWnd)

                if isinstance(proc, list):
                    for tdx in proc:
                        if title.value.find(tdx) >= 0:
                            left, top, width, height = GetWindowRectFromName(hWnd)
                            if left < 0 and top < 0:
                                # user32.ShowWindow(hWnd, SW_MAXIMIZE);
                                time.sleep(0.1)
                                user32.ShowWindow(hWnd, SW_Normal);
                                left, top, width, height = GetWindowRectFromName(hWnd)
                                print(left, top, width, height)

                            if tdx in tdx_ths_position.keys():
                                set_windows_hwnd_pos(hWnd,tdx_ths_position[tdx])
                else:
                    if title.value.find(proc) >= 0:
                        left, top, width, height = GetWindowRectFromName(hWnd)
                        if left < 0 and top < 0:
                            # user32.ShowWindow(hWnd, SW_MAXIMIZE);
                            time.sleep(0.1)
                            user32.ShowWindow(hWnd, SW_Normal);
                            left, top, width, height = GetWindowRectFromName(hWnd)
                            print(left, top, width, height)

                        if proc in tdx_ths_position.keys():
                            set_windows_hwnd_pos(hWnd,tdx_ths_position[proc])
                    # print(title.value)
                        # left, top, width, height = GetWindowRectFromName(hWnd)
                        # if left < 0 and top < 0:
                        #     time.sleep(0.1)
                        #     user32.ShowWindow(hwnd, SW_Normal);
                        #     left, top, width, height = GetWindowRectFromName(hWnd)

                        # # left, right, top, bottom = GetWindowRectFromName(hWnd)
                        # # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                        # result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return True


def list_user_windows():
    '''Return a sorted list of visible windows.'''
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            if len(title.value) > 0:
            # left, right, top, bottom = get_pos(hWnd)
                left, top, width, height = GetWindowRectFromName(hWnd)
                # left, right, top, bottom = GetWindowRectFromName(hWnd)
                # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
                result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    return (result)


# private enum ShowWindowEnum{Hide = 0,
# ShowNormal = 1,ShowMinimized = 2,ShowMaximized = 3,
# Maximize = 3,ShowNormalNoActivate = 4,Show = 5,
# Minimize = 6,ShowMinNoActivate = 7,ShowNoActivate = 8,
# Restore = 9,ShowDefault = 10,ForceMinimized = 11};

def FindWindowRectFromName(title)-> tuple:
    # not ok 
    # hwnd = ctypes.windll.user32.FindWindowW(0, name)
    SW_Normal = 1
    SW_MAXIMIZE = 3
    SW_MINIMIZE = 6
    SW_Restore = 9
    SW_Show = 5
    global list_hwnd
    if len(list_hwnd) == 0:
        list_hwnd = list_user_windows()
    hwnd = 0
    for win in list_hwnd:
        if win.title.find(title) >= 0:
            print(win)
            hwnd = win.pid
            # break

            #需要前置步骤showwindow
            # hwnd = user32.GetForegroundWindow()
            # user32.ShowWindow(hwnd, SW_MINIMIZE);
            # import time 
            # time.sleep(0.5)
            # user32.ShowWindow(hwnd, SW_Normal);

            left, top, width, height = GetWindowRectFromName(hwnd)
            # print(hwnd)
            # print(rect)


            return (left, top, width, height)
    return (0,0,0,0)

def list_windows():
    '''Return a sorted list of visible windows.'''
    result = []
    @WNDENUMPROC
    def enum_proc(hWnd, lParam):
        # if user32.IsWindowVisible(hWnd):
        if user32.IsWindowVisible(hWnd):
            pid = wintypes.DWORD()
            tid = user32.GetWindowThreadProcessId(
                        hWnd, ctypes.byref(pid))
            length = user32.GetWindowTextLengthW(hWnd) + 1
            title = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hWnd, title, length)
            # left, right, top, bottom = get_pos(hWnd)
            # left, right, top, bottom = GetWindowRectFromName(hWnd)
            left, top, width, height = GetWindowRectFromName(hWnd)
            # result.append(WindowInfo(pid.value, title.value,left, top, right, bottom))
            result.append(WindowInfo(pid.value, title.value,left, top, width, height))
            # print(pid.value, title.value,end='')
        return True
    user32.EnumWindows(enum_proc, 0)
    # return sorted(result)
    return (result)

psapi = ctypes.WinDLL('psapi', use_last_error=True)

psapi.EnumProcesses.errcheck = check_zero
psapi.EnumProcesses.argtypes = (
   wintypes.LPDWORD,  # _Out_ pProcessIds
   wintypes.DWORD,    # _In_  cb
   wintypes.LPDWORD,) # _Out_ pBytesReturned

def list_pids():
    '''Return sorted list of process IDs.'''
    length = 4096
    PID_SIZE = ctypes.sizeof(wintypes.DWORD)
    while True:
        pids = (wintypes.DWORD * length)()
        cb = ctypes.sizeof(pids)
        cbret = wintypes.DWORD()
        psapi.EnumProcesses(pids, cb, ctypes.byref(cbret))
        if cbret.value < cb:
            length = cbret.value // PID_SIZE
            return sorted(pids[:length])
        length *= 2


if __name__ == '__main__':
    print('Process IDs:')
    # print(*list_pids(), sep='\n')
    print('\nWindows:')
    # print(*list_windows(), sep='\n')
    proc_title = ['通达信','东方财富','同花顺']
    
    proc_title =  [proc for proc in tdx_ths_position.keys()]

    import sys
    sys.path.append("..")
    # from JSONData import tdx_data_Day as tdd
    # from JohnsonUtil import LoggerFactory as LoggerFactory
    # from JohnsonUtil import johnson_cons as ct
    from JohnsonUtil import commonTips as cct
    sina = [ title for title in cct.terminal_positionKey1K_triton.keys()]
    # title = 'sina_Monitor'
    for title in proc_title:
        FindWindowRectFromName(title)

    # for proc in proc_title:
    #     win_info=list_find_windows(proc)
    #     for win in win_info:
    #         print(win)
    #         set_windows_pos(win.title,tdx_ths_position[proc])


    # print("set pos")
    # set_proc_windows_position(proc_title)
