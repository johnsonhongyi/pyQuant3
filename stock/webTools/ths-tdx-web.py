from pywebio import start_server

from pywebio.output import *
from pywebio.session import set_env
from functools import partial
from copy_tools import *
import asyncio
import pyperclip

import win32api
import win32con
import win32gui
from ths_link import send_code_message

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

def broadcast_stock_code(stock_code,message_type='stock'):
    if isinstance(stock_code, dict):
        stock_code = stock_code['content']
        stock_code = stock_code.strip()
    if len(stock_code) == 6:
        if str(message_type) == 'stock':
            if str(stock_code)[0] in ('0','3'):
                codex = '6' + str(stock_code)
            elif str(stock_code)[0] == '6':
                codex = '7' + str(stock_code)
            else:
                code = '4' + str(stock_code)
        else:
            codex = int(stock_code)
        UWM_STOCK = win32api.RegisterWindowMessage('stock')
        print(win32con.HWND_BROADCAST,UWM_STOCK,int(codex))
        #系统广播
        win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
        send_code_message(stock_code)
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

if __name__ == '__main__':
    # search_ths_data('000006')
    import os
    # or open with iexplore
    # os.system('cmd /c start iexplore "http://127.0.0.1:8080/"')
    os.system('cmd /c start "" "http://127.0.0.1:8080/"')
    os.system('cmd /c start python pywin32_mouse.py')
    # cmd /c start /min  #cmd 最小化,程序窗口正常
    # start "" firefox
    # start "" chrome
    if cct.isMac():
        width, height = 80, 22
        cct.set_console(width, height)
    else:
        width, height = 80, 22
        cct.set_console(width, height)

    start_server(main, port=8080, debug=False)