# -*- coding:utf-8 -*-
from pywebio import start_server

from pywebio.output import *
from pywebio.session import set_env
from functools import partial
# from copy_tools import broadcast_stock_code
from copy_tools import *
from findSetWindowPos import find_proc_windows
import asyncio
import pyperclip

import win32api
import win32con
import win32gui
from ths_link import send_code_message
import time
import pandas as pd
import sys


sys.path.append("..")
# from JSONData import tdx_data_Day as tdd
# from JohnsonUtil import LoggerFactory as LoggerFactory
# from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct




def search_ths_data(code):

    df_ths = cct.GlobalValues().getkey('df_ths')
    if df_ths is None:
        fpath = r'.././JohnsonUtil\wencai\同花顺板块行业.xls'
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
    head = [["Name", 'Code', 'Actions', "概念"]]
    all_data = []
    txt_data = []
    img_data = []
    file_data = []
    for idx, data in enumerate(show_content, 1):
        cname,result = search_ths_data(data["content"])
        # cur = [data["create_time"], data["type"],
        cur = [cname,
               data["content"] if data["type"] == "text" else put_image(open(data["content"], 'rb').read()),
               put_buttons(
                   [
                       {
                           "label": "执行",
                           "value": data,
                       }
                    ], onclick=partial(broadcast_stock_code))
               ,result]
                   # ], onclick=partial(edit_row, row=idx))]
        all_data.append(cur)
        if data["type"] == "text":
            txt_data.append(cur)
        elif data["type"] == "img":
            img_data.append(cur)
        elif data["type"] == "file":
            file_data.append(cur)

    with use_scope('content', clear=True):
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

# 示例
# port_to_check = 8080
# check_info, is_port_used = check_port_in_use(port_to_check)
# print(check_info)
# print("端口是否使用:", is_port_used)

if __name__ == '__main__':
    # search_ths_data('000006')
    import os
    # or open with iexplore
    # os.system('cmd /c start iexplore "http://127.0.0.1:8080/"')

    if not find_proc_windows('人气综合排行榜2.2',fuzzysearch=False):
        os.system('cmd /c start C:\\Users\\Johnson\\Documents\\TDX\\55188\\人气共振2.2.exe')
        time.sleep(1)
    if not find_proc_windows('同花顺'):
        os.system('cmd /c start D:\\MacTools\\WinTools\\同花顺\\hexin.exe')
        time.sleep(1)
    if not find_proc_windows('东方财富'):
        os.system('cmd /c start D:\\MacTools\\WinTools\\eastmoney\\swc8\\mainfree.exe')
        time.sleep(1)

    if not find_proc_windows('通达信',fuzzysearch=True):
        os.system('cmd /c start D:\\MacTools\\WinTools\\new_tdx2\\tdxw.exe')
        time.sleep(5)
    if not find_proc_windows('pywin32_mouse'):
        os.system('start cmd /k python pywin32_mouse.py')
        time.sleep(5)
    if not find_proc_windows('findSetWindowPos'):
        os.system('cmd /c start python findSetWindowPos.py')
        time.sleep(2)
    if not find_proc_windows('联动精灵',visible=False):
        # os.system('cmd /c start /min D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
        # os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')
        os.system('cmd /c start D:\\MacTools\\WinTools\\联动精灵V2\\link.exe')

        time.sleep(3)
    
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
    # print(find_proc_windows('ths-tdx-web.py'))
    while 1:
        try:
            # status = find_proc_windows('ths-tdx-web')
            port_to_check = 1080
            check_info, is_port_used = check_port_in_use(port_to_check)
            print(check_info)
            # print("端口是否使用:", is_port_used)

            # status = find_proc_windows('ths-tdx-web')
            # if len(status) == 0:
            if not is_port_used:
                os.system('cmd /c start "" "http://127.0.0.1:%s/"'%(port_to_check))
                start_server(main, port=port_to_check, debug=False)
            else:
                print("Find ths-tdx-web no run start_server")
                time.sleep(30)
        except Exception as e:
            print(e)
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
