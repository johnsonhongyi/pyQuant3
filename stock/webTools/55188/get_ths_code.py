import os
import pythoncom
import pymem
import re
import time
import psutil
import win32gui  # Win 图形界面接口，主要负责操作窗口切换以及窗口中元素
import win32api  # Win 开发接口模块，主要负责模拟键盘和鼠标操作
import win32con  # 全面的库函数，提供Win32gui和Win32api需要的操作参数
import pyWinhook
import ctypes
import win32com.client
import sys

#通过同花顺基址，取单一版本的，实时股票代码
def get_ths_add_code(OffsetAdd):
    try:
        # 进程层
        GetGameProcess = pymem.Pymem("hexin.exe")

        # 获取同花顺的内存基址
        GetGameModuleProcess = pymem.process.module_from_name(
            GetGameProcess.process_handle, "hexin.exe").lpBaseOfDll
        ReadGameMemory = GetGameProcess.read_int(
            GetGameModuleProcess+OffsetAdd)
        # print(ReadGameMemory)

        data = GetGameProcess.read_bytes(ReadGameMemory, 7)
        import ipdb;ipdb.set_trace()
        
        str1 = data.decode('utf-8')
        # 字符串拆分成由单个字母组成的列表：
        strlist = list(str1)
        strlist.pop(0)  # 删除下标为0的字符
        Stock_code = "".join(strlist)
    except Exception as e:
        print("取代码失败")
    return Stock_code

# 遍历版本基址，直到获取当前股票代码为止
def get_ths_code():
    try:
        Stock_code = get_ths_add_code(0x015568F4)

    except Exception as e:
        print(e)

        try:
            Stock_code = get_ths_add_code(0x0150E228)
        except Exception as e:
            print(e)

            try:
                Stock_code = get_ths_add_code(0x017160E8)
            except Exception as e:
                print(e)
                print("应用程序无法取到同花顺的代码：,检查同花顺是否打开")
                print("联动自动重置")
    return Stock_code


# 向通达信广播股票代码
def Tdx_BroadCast(Message, Code):
    if str(Message) == 'Stock':
        # 上海，深圳股票判断;
        if str(Code)[0] == '6':
            codex = '7'+str(Code)
            # print(codex)
        else:
            codex = '6'+str(Code)
    else:
        codex = int(Code)
    UWM_STOCK = win32api.RegisterWindowMessage('Stock')  # 获得TDX在系统注册过的消息;
    win32gui.PostMessage(win32con.HWND_BROADCAST,
                         UWM_STOCK, int(codex), 0)  # 向系统广播消息;
    # pWnd->win32gui.PostMessage(UWM_STOCK,int(codex),0)  #获得要发送窗口的句柄即可
# 遍历所有窗口并筛选出符合条件的同花顺窗口，输出窗口句柄+窗口标题




if __name__ == '__main__':
    print(get_ths_code())