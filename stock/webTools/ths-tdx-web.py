# -*- coding:utf-8 -*-
from pywebio import start_server

from pywebio.output import *
from pywebio.session import set_env
from functools import partial
from copy_tools import *
from findSetWindowPos import find_window_by_title_background,find_window_by_title_safe,find_proc_window_tasklist
import asyncio
import pyperclip

import win32api
import win32con
import win32gui
from ths_link import send_code_message
import time
import pandas as pd
import sys
import os


sys.path.append("..")
# from JSONData import tdx_data_Day as tdd
# from JohnsonUtil import LoggerFactory as LoggerFactory
# from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct

import ctypes
user32 = ctypes.windll.User32

def isLocked():
    print(user32.GetForegroundWindow())
    return user32.GetForegroundWindow() == 0


def search_ths_data(code):

    df_ths = cct.GlobalValues().getkey('df_ths')
    if df_ths is None:
        fpath = r'.././JohnsonUtil\wencai\同花顺板块行业.xlsx'
        df_ths = pd.read_excel(fpath)
        df_ths = df_ths.loc[:,['股票代码','股票简称','所属概念', '所属同花顺行业']]
        cct.GlobalValues().setkey('df_ths',df_ths)
        df = df_ths
    else:
        df = df_ths
    # df = df.reset_index().set_index('股票代码')
    # df = df.set_index('股票代码')
    # # df = df.iloc[:,[1,2,4,5,6,7,8,9]]
    # df = df.iloc[:,[4,5,6,7,8]]
    # # return (df[df.index == cct.code_to_symbol_ths(code)])
    # data = df[df.index == cct.code_to_symbol_ths(code)]
    # # table, widths=cct.format_for_print(data, widths=True)
    # # table=cct.format_for_print2(data).get_string(header=False)
    # table =cct.format_for_print(data,header=False)
    df_code = df.query("股票代码 == @cct.code_to_symbol_ths(@code)")
    if len(df_code) == 1:
        cname = df_code.股票简称.values[0]
        result = df_code.所属概念.values[0]
    else:
        cname = '未找到'
        result = '未找到'
    return cname,result

# def broadcast_stock_code(stock_code,message_type='stock'):
#     if isinstance(stock_code, dict):
#         stock_code = stock_code['content']
#         stock_code = stock_code.strip()
#     if len(stock_code) == 6:
#         if str(message_type) == 'stock':
#             if str(stock_code)[0] in ('0','3'):
#                 codex = '6' + str(stock_code)
#             elif str(stock_code)[0] == '6':
#                 codex = '7' + str(stock_code)
#             else:
#                 code = '4' + str(stock_code)
#         else:
#             codex = int(stock_code)
#         UWM_STOCK = win32api.RegisterWindowMessage('stock')
#         print(win32con.HWND_BROADCAST,UWM_STOCK,int(codex))
#         #系统广播
#         win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
#         send_code_message(stock_code)
# broadcast_stock_code('399001')

def edit_row(choice, row):
    if choice["type"] == "text":
        pyperclip.copy(choice["content"])
    elif choice["type"] == "img":
        set_clipboard_img(choice["content"])

# def delete_row(choice,row):
#     if choice["type"] == "text":
#         pyperclip.copy(choice["content"])
#     elif choice["type"] == "img":
#         set_clipboard_img(choice["content"])

async def get_content():
    pre = None
    while 1:
        content = pyperclip.paste()
        await asyncio.sleep(0.5)
        if content and content != pre:
            yield content
            pre = content


def show_tab(show_content):
    # head = [["Time", "type", 'Content', 'Actions']]
    head = [["Index","Name", 'Code', 'Actions','Date', "概念"]]
    all_data = []
    txt_data = []
    img_data = []
    file_data = []
    for idx, data in enumerate(show_content, 1):
        cname,result = search_ths_data(data["content"])
        # cur = [data["create_time"], data["type"],
        cur = [idx,cname,
               data["content"] if data["type"] == "text" else put_image(open(data["content"], 'rb').read()),
               put_buttons(
                   [
                       {
                           "label": "执行",
                           "value": data,
                       }
                    ], onclick=partial(broadcast_stock_code))
               ,data['create_time'][:10],result]
                   # ], onclick=partial(edit_row, row=idx))]
        all_data.append(cur)
        if data["type"] == "text":
            txt_data.append(cur)
        elif data["type"] == "img":
            img_data.append(cur)
        elif data["type"] == "file":
            file_data.append(cur)

    with use_scope('content', clear=True):
        # put_button("Refresh", onclick=lambda: run_js('window.location.reload()'))
        put_tabs([
            {'title': '全部', 'content': put_table(head + all_data)},
            {'title': '文本', 'content': put_table(head + txt_data)},
            {'title': '图片', 'content': put_table(head + img_data)},
            {'title': '文件', 'content': put_table(head + file_data)},

        ])



async def main():
    """TDX_THS_联动 Previewer"""
    set_env(output_animation=False)
    put_markdown('## 历史剪切板')
    # put_button("Refresh", onclick=lambda: run_js('window.location.reload()'))
    if not os.path.exists("history_data.json"):
        with open("history_data.json", "w+", encoding="utf-8") as f:
            f.write("[]")
    with open('history_data.json', 'r', encoding='utf8')as fp:
        show_content = json.load(fp)
    show_tab(show_content)
    async for data in get_clipboard_contents():
        if show_content and show_content[0]["hash"] == data["hash"]: continue
        show_content.insert(0, data)
        show_tab(show_content)

#cmd最小化,test error
# import ctypes
# ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 6)

# @echo off

# %1(start /min cmd.exe /c %0 :&exit)

# #下面是自己的cmd命令，可以随便输入

# ping www.baidu.com > baidu.txt

import socket
import subprocess
import platform


def get_host_ip():
    """
    查询本机ip地址
    :return: ip
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()

    return ip

def check_port_in_use(port):
    system = platform.system()
    print(f"尝试使用socket方式检查端口:{port}")
    check_dict ={}
    is_port_in_use = False
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', port))
        sock.close()
        check_dict["Socket"] = False
    except socket.error:
        #print(f"socket检查无法使用端口号{port}，可能被占用")
        check_dict["Socket"] = True
        is_port_in_use = True  # 如果出现socket错误，标记端口被占用

    print(f"尝试使用命令行方式检查端口:{port}")

    # 对于Unix-like系统（包括macOS和Linux），尝试使用lsof命令
    if system in ["Linux", "Darwin"]:
        print("system in [Linux, Darwin]")
        command = f'lsof -i :{port}'
        output = subprocess.check_output(command, shell=True, text=True)
        result = bool(output.strip())
        check_dict["Command_Line_lsof"] = result
        is_port_in_use |= result  # 如果lsof检查结果显示端口被占用，更新标志位

    # 对于Windows系统
    elif system == "Windows":
        local_ip = get_host_ip()
        print("system == Windows:%s"%(local_ip))
        # command = f'netstat -ano | findstr "{local_ip}:{port} 0.0.0.0:{port}"'
        command = f'netstat -ano | findstr "0.0.0.0:{port}"'
        output = subprocess.run(command, shell=True, capture_output=True, text=True)
        result = bool(output.stdout.strip())
        check_dict["Command_Line_netstat"] = result
        print("command:%s"%(command))
        is_port_in_use |= result  # 如果netstat检查结果显示端口被占用，更新标志位
    else:
        print("system == None")
        raise ValueError(f"Unsupported operating system: {system}")

    # 返回端口占用情况字典及是否被占用的布尔值
    print(f"检查端口in_use:{is_port_in_use}")
    return check_dict, is_port_in_use


def run_system_fpath(fpath):
    if cct.check_file_exist(fpath): 
        os.system('cmd /c start %s'%(fpath))
    else:
        print("fpath:%s isn't exist"%(fpath))

# 示例
# port_to_check = 8080
# check_info, is_port_used = check_port_in_use(port_to_check)
# print(check_info)
# print("端口是否使用:", is_port_used)

# import win32api
# import win32con
# import win32gui
# import platform
# import time
import win32api
import win32con
import win32gui

WM_POWERBROADCAST = 0x218
PBT_APMRESUMEAUTOMATIC = 0x0012  # 系统唤醒事件

def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_POWERBROADCAST:
        if wparam == PBT_APMRESUMEAUTOMATIC:
            print("系统从睡眠中唤醒")
    return True

def register_power_listener():
    hwnd = win32gui.CreateWindowEx(
        0, "STATIC", "PowerMonitor", 0, 0, 0, 0, 0, 0, 0, 0, None)
    win32gui.SetWindowLong(hwnd, win32con.GWL_WNDPROC, wnd_proc)
    print("正在监听唤醒事件...")
    while True:
        win32gui.PumpWaitingMessages()

if __name__ == '__main__':
    # search_ths_data('000006')
    # or open with iexplore
    # os.system('cmd /c start iexplore "http://127.0.0.1:8080/"')
    # findproc = find_proc_windows('联动精灵',visible=False)
    # find_proc_window_tasklist('link.exe')
    # import ipdb;ipdb.set_trace()

    # if not find_proc_window_tasklist('link.exe'):
    #     # os.system('cmd /c start /min D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     time.sleep(3)



    if not find_window_by_title_safe('人气综合排行榜2.2'):
        # os.system('cmd /c start C:\\Users\\Johnson\\Documents\\TDX\\55188\\人气共振2.2.exe')
        run_system_fpath("C:\\Users\\Johnson\\Documents\\TDX\\55188\\人气共振2.22.exe")
        time.sleep(1)
    if not find_window_by_title_safe('行业跟随'):
        # os.system('cmd /c start C:\\Users\\Johnson\\Documents\\TDX\\55188\\竞价定行业1.1.exe')
        run_system_fpath("C:\\Users\\Johnson\\Documents\\TDX\\55188\\竞价定行业1.1.exe")
        time.sleep(1)

    if not find_window_by_title_safe('同花顺'):
        # os.system('cmd /c start D:\\MacTools\\WinTools\\同花顺\\hexin.exe')
        run_system_fpath('D:\\MacTools\\WinTools\\同花顺\\hexin.exe')
        time.sleep(6)
    if not find_window_by_title_safe('东方财富'):
        # os.system('cmd /c start D:\\MacTools\\WinTools\\eastmoney\\swc8\\mainfree.exe')
        run_system_fpath('D:\\MacTools\\WinTools\\eastmoney\\swc8\\mainfree.exe')
        time.sleep(6)


    if not find_window_by_title_safe('通达信金融终端'):
        run_system_fpath('%s\\tdxw.exe'%(cct.get_tdx_dir()))
        time.sleep(8)

    # if not find_proc_windows('东兴证券'):
    #     run_system_fpath('%s\\tdxw.exe'%('D:\\MacTools\\WinTools\\zd_dxzq'))
    #     # run_system_fpath('%s\\tdxw.exe'%(cct.win10dxzq.))
    #     time.sleep(8)
    
    if not find_window_by_title_safe('pywin32_mouse'):
        os.system('start cmd /k python pywin32_mouse.py')
        time.sleep(5)

    if not find_window_by_title_safe('交易信号监控'):
        # os.system('cmd /c start /min D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
        # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
        os.system('cmd /c start D:\\MacTools\\OrderMonitor\\OrderMon.exe')

    time.sleep(5)

    if not (find_window_by_title_background('AutoHotkey')):
        run_system_fpath('D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\ahk\\tdx-dfcf.ahk')
        # run_system_fpath('D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\ahk\\ths-code.ahk')
    else:
        print('find AutoHotkey')

    if not find_window_by_title_safe('findSetWindowPos'):
        os.system('cmd /c start python findSetWindowPos.py')
        time.sleep(2)
    # if not find_proc_windows('联动精灵',visible=False):
    
    if find_window_by_title_safe('通达信金融终端'): 
        # if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏一')):
        #     print('start : 通达信金融终端(开心果交易版) 副屏一')
        #     print(open_tdx_mscreen(1))
        # if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏二')):
        #     print('start : 通达信金融终端(开心果交易版) 副屏二')
        #     print(open_tdx_mscreen(2))
        if not (find_window_by_title_safe('通达信金融终端(开心果交易版) 副屏三')):
            print('start : 通达信金融终端(开心果交易版) 副屏三')
            print(open_tdx_mscreen(3))
    else:
        set_tdx_screen_show()

    time.sleep(6)
    if not find_window_by_title_background('开盘啦板块竞价'): 
        run_system_fpath('C:\\Users\\Johnson\\Documents\\TDX\\55188\\开盘啦板块竞价.exe')
        time.sleep(2)
    if not find_window_by_title_background('异动联动'): 
        run_system_fpath('C:\\Users\\Johnson\\Documents\\TDX\\55188\\异动联动.exe')
        time.sleep(2)
    
    if not find_window_by_title_background('涨停采集工具共享版'): 
        run_system_fpath('C:\\Users\\Johnson\\Documents\\TDX\\55188\\涨停采集工具共享版.exe')
        time.sleep(2)
    # if not find_proc_window_tasklist('link.exe'):
    #     # os.system('cmd /c start /min D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
    #     run_system_fpath('D:\\JohnsonProgram\\联动精灵\\link.exe')


    #     time.sleep(3)
    
    # os.system('cmd /c start "" "http://127.0.0.1:8080/"')

    # cmd /c start /min  #cmd 最小化,程序窗口正常
    # start "" firefox
    # start "" chrome
    if cct.isMac():
        width, height = 80, 22
        cct.set_console(width, height)
    else:
        width, height = 80, 22
        cct.set_console(width, height)
    # time.sleep(1)
    print(('ths-tdx-web.py'))
    if platform.system() == 'Windows':
        def window_proc(hwnd, msg, wparam, lparam):
            if msg == win32con.WM_POWERBROADCAST:
                if wparam == win32con.PBT_APMRESUMEAUTOMATIC:
                    print("System has woken up from sleep/hibernation.")
                    # Add your actions here
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        # wc = win32gui.WNDCLASS()
        # wc.hInstance = win32api.GetModuleHandle(None)
        # wc.lpszClassName = "WakeUpHandler"
        # wc.lpfnWndProc = window_proc
        # class_atom = win32gui.RegisterClass(wc)
        # hwnd = win32gui.CreateWindow(class_atom, "WakeUpHandler", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

        # # GUID for system resume
        # GUID_SYSTEM_RESUME = "{05fb411a-b8e2-4dca-b9d5-eae426bad8ca}"
        
        # # Register for system resume notifications
        # notification_handle = win32api.RegisterPowerSettingNotification(
        #     hwnd, GUID_SYSTEM_RESUME, win32con.DEVICE_NOTIFY_WINDOW_HANDLE
        # )
        print("Listening for system wake-up events...")
    start_edge = 0
    port_to_check = 8080
    while 1:
        try:
            # status = find_proc_windows('ths-tdx-web')
            check_info, is_port_used = check_port_in_use(port_to_check)
            print(check_info)
            # print("端口是否使用:", is_port_used)

            # status = find_proc_windows('ths-tdx-web')
            # if len(status) == 0:

            if not is_port_used and start_edge < 10:
                os.system('cmd /c start "" "http://127.0.0.1:%s/"'%(port_to_check))
                start_server(main, port=port_to_check, debug=True)
                start_edge += 1
            else:
                port_to_check +=1
                print("Find %s no run start_server"%(find_window_by_title_safe('ths-tdx-web.py')))
                time.sleep(30)
        except Exception as e:
            time.sleep(6)
            print(e)
            if start_edge > 10:
                print("start_edge:{start_edge}")
                break
                # time.sleep(10)

            # raise e
        # finally:
        #     print("TryCatch:finally:")
        #     check_info, is_port_used = check_port_in_use(port_to_check)

        #     if not is_port_used:
        #         os.system('cmd /c start "" "http://127.0.0.1:%s/"'%(port_to_check))
        #         start_server(main, port=port_to_check, debug=False)
        #     else:
        #         print("ths-tdx-web already Running and Done")
        #         time.sleep(30)
