import os
import pythoncom
import pymem
import re
import time
import psutil
import win32gui # Win 图形界面接口，主要负责操作窗口切换以及窗口中元素
import win32api # Win 开发接口模块，主要负责模拟键盘和鼠标操作
import win32con # 全面的库函数，提供Win32gui和Win32api需要的操作参数
import pyWinhook
import ctypes
import win32com.client
import sys
hookmonitor = pyWinhook.HookManager()
old_code = None
Share_hwnd = None
# 读取指定应用程序中dll库的基址
def Get_moduladdr(dll, exe): # 读DLL模块基址
    GetGameProcess = pymem.Pymem(exe)
    modules = list(GetGameProcess.list_modules()) # 列出exe的全部DLL模块
    for module in modules:
        if module.name == dll:
            # print(module.name) # 模块名字
            # print(module.lpBaseOfDll) # 模块基址
            # print("找到了")
            Moduladdr = module.lpBaseOfDll
    return GetGameProcess, Moduladdr
def get_tdx_add_code(OffsetAdd):
     try:
         Proc, BaseAdd = Get_moduladdr("Viewthem.dll", "tdxw.exe")
         ptr = Proc.read_int(BaseAdd+OffsetAdd)
         # print("股票代码指针："+hex(ptr))
         data = Proc.read_bytes(ptr, 6)
         Stock_code1 = data.decode('utf-8')
         strlist = list(Stock_code1)
         Stock_code = "".join(strlist)
     except Exception as e:
         print("")
         # print("无法取通达信的代码,检查通达信是否打开")
     return Stock_code
    # 获取开心果版股票代码
def get_tdx_kxg_code():
     try:
         # 获取开心果6月版股票代码
         Stock_code=get_tdx_add_code(0x00036290) 
     except Exception as e: 
        print(e)
        # 获取开心果7月版股票代码
        try: 
            Stock_code=get_tdx_add_code(0x000366D0)
            # print("应用程序无法取通达信6的代码,检查通达信是否打开")
            # hookmonitor.UnhookKeyboard()#取消键盘钩子
            # hookmonitor.UnhookMouse()#取消鼠标钩子
        except Exception as e:
            print("通达信开心果7代码读取失败")
        else:
            print("读取通达信7代码成功！")
     else:
         print("读取通达信代码成功！") 
     return Stock_code
# if __name__ == '__main__':
#      print(get_tdx_kxg_code())

ths_count=0
# 同花顺联动通达信
def ths_to_tdx():
   
    global ths_count
    #点后防止切换慢
    # time.sleep(0.3)
    try:
        Stock_code = hx_ths_module.get_ths_code()
        tdx_Stock_code=hx_tdx_module.get_tdx_kxg_code()
    except Exception as e:
        hookmonitor.UnhookKeyboard()#取消键盘钩子
        hookmonitor.UnhookMouse()#取消鼠标钩子
        print("联动重置")
        main_start()
   
    if Stock_code != tdx_Stock_code:
        # 获取同花顺金融大师的实时股票代码        
        print(f'同花顺当前股票代码：{Stock_code}')
        hx_ths_module.Tdx_BroadCast('Stock', Stock_code)
        time.sleep(0.2)
        if hx_ths_module.get_ths_code() != hx_tdx_module.get_tdx_kxg_code() and ths_count<2:
            ths_count+=1
            print(f"同花顺自回调同步！{ths_count}次")
            ths_to_tdx()
        if hx_ths_module.get_ths_code() == hx_tdx_module.get_tdx_kxg_code():
            # print("同步到通达信成功！！！")
            ths_count=0
            print("【同花顺】to【通达信】")  

            

tdx_count=0
# 通达信联动同花顺
def tdx_to_ths():
    global tdx_count
    global Share_hwnd
    try:
        Stock_code = hx_tdx_module.get_tdx_kxg_code()
        ths_Stock_code=hx_ths_module.get_ths_code()
    except Exception as e:
        hookmonitor.UnhookKeyboard()#取消键盘钩子
        hookmonitor.UnhookMouse()#取消鼠标钩子
        print("联动重置")
        main_start()


    if Stock_code != ths_Stock_code:

        # 获取开心果通达信6月份版的股票代码

        print(f'通达信当前股票代码：{Stock_code}')
        hookmonitor.UnhookMouse()  # 取消鼠标钩子
        hookmonitor.UnhookKeyboard()  # 取消键盘钩子        

        dict_ths = get_all_ths_windows()  # 返回进程字典
        # print(dict_ths)
        # keys = dict_ths.keys()  # 返回字典中所有键
        items = dict_ths.items()  # 返回键值对
        for key, value in items:  # 字典拆包
            # print(f"进程句柄：{key}=窗口标题【{value[1]}】")
            if value[1] != "同花顺机器人":
                for zi in Stock_code:
                    asc = ord(zi)
                    win32api.PostMessage(key, win32con.WM_CHAR, asc, 0)

                if Share_hwnd == None:
                    hwnd_down = win32gui.FindWindow("Afx:00400000:0", None)
                    # print(hwnd_down)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

                    #  第一套回车无效第二回车
                    hwnd_down = win32gui.FindWindow("Afx:00E40000:0", None)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

                    hwnd_down = win32gui.FindWindow("Afx:00DE0000:0", None)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

                    hwnd_down = win32gui.FindWindow("Afx:00EC0000:0", None)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(hwnd_down, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

                else:
                    # print(f"同花顺键盘精灵成功获取：{hex(Share_hwnd)}")
                    win32gui.PostMessage(Share_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(Share_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)

                    # 加一次回车弹起，精灵界面不停留
                    # win32gui.PostMessage(Share_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
                    win32gui.PostMessage(Share_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)        

            # win32api.keybd_event(13,0,0,0)
            # win32api.keybd_event(13,0,win32con.KEYEVENTF_KEYUP,0)
        hookmonitor.HookKeyboard()
        hookmonitor.HookMouse()
    # if get_ths_code() != get_tdx_kxg6_code():
    #             print("二次同步！")
    #             tdx_to_ths()   
   
    if Share_hwnd == None:
        print("不联动！解决方案：开启同花顺后，手动输入一次股票代码并回车！即可解决。")
    time.sleep(0.3)   
    if Share_hwnd != None and hx_ths_module.get_ths_code() != hx_tdx_module.get_tdx_kxg_code():
        tdx_count+=1
        print(f"通达信自回调![{tdx_count}]次")
        tdx_to_ths()
        if hx_ths_module.get_ths_code() == hx_tdx_module.get_tdx_kxg_code():
            tdx_count=0
            print("{通达信}to{同花顺}")
    # print(f"通达信{tdx_count}")


if __name__ == '__main__':
    print(get_tdx_kxg_code())


