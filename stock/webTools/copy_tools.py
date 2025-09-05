from PIL import ImageGrab, Image
import pyperclip
import win32clipboard as clip
import win32con
from io import BytesIO
import json
import hashlib
import asyncio
import datetime
import os
import shutil
from ths_link import send_code_message

pre_hash = None

import win32api
# import win32con
import win32gui
import time

# import pandas as pd
# import sys
# sys.path.append("..")
# # from JSONData import tdx_data_Day as tdd
# # from JohnsonUtil import LoggerFactory as LoggerFactory
# # from JohnsonUtil import johnson_cons as ct
# from JohnsonUtil import commonTips as cct
# win32clipboard
# https://stackoverflow.com/questions/101128/how-do-i-read-text-from-the-windows-clipboard-in-python

from datetime import date
from ahk import AHK
import time
ahk = AHK()

# 获取当前日期
def get_today():
    current_date = date.today().strftime('%Y-%m-%d')
    return current_date

def isDigit(x):
    #re def isdigit()
    try:
        if str(x) == 'nan' or x is None:
            return False
        else:
            float(x)
            return True
    except ValueError:
        return False

def send_code_dfcf(code):
    applist=['东方财富']
    for window in ahk.list_windows():
        for app in applist:
            if window.title.find(app) >= 0:
                window.activate()
                time.sleep(0.3)
                print(f'class_name:{window.get_class()}')
                print(f'title:{window.title}')
                # Some more attributes
                # print(f'text:{window.text}')
                # print(window.text)           # window text -- or .get_text()
                print(window.get_position()) # (x, y, width, height)
                print(window.id)             # the ahk_id of the window
                print(window.pid)            # process ID -- or .get_pid()
                print(window.process_path)   # or .get_process_path()
                print('....................\n\n')
                # ahk.setKeyDelay(50)
                # window.activate()
                time.sleep(0.3)
                ahk.send(code)
                time.sleep(0.6)
                ahk.send('{Enter}')

def open_tdx_mscreen(sc=1):
    # #If WinActive("ahk_class TdxW_MainFrame_Class")
    # {
    #     SendMessage,0x111,33819,0,,ahk_class TdxW_MainFrame_Class
    # }
    # ;打开副屏一,二,三,一键四屏

    # ;SendMessage,0x111,3356,0,,ahk_class TdxW_MainFrame_Class
    # ;SendMessage,0x111,3357,0,,ahk_class TdxW_MainFrame_Class
    # ;SendMessage,0x111,3358,0,,ahk_class TdxW_MainFrame_Class
    sc = str(sc)
    screen = {'1':'3356','2':'3357','3':'3358','4':'3361'}
    window = ahk.find_window_by_class('TdxW_MainFrame_Class')
    if window:
        # 3. 如果窗口找到，获取其句柄
        hwnd = window.id
        print(f"找到窗口，句柄为：{hwnd}")
        window.activate()
        time.sleep(0.2)
        # 4. 构造 AHK 脚本字符串
        # 使用 f-string 插入句柄，确保 SendMessage 发送到正确的窗口
        ahk_script = f"""
            SendMessage, 0x111, {screen[sc]}, 0, , ahk_class TdxW_MainFrame_Class
        """
        # 5. 运行 AHK 脚本发送消息
        result = ahk.run_script(ahk_script)
        print(f"脚本执行结果：{result}")
        time.sleep(0.5)
        window.activate()
    else:
        print("未找到匹配 'ahk_class TdxW_MainFrame_Class' 的窗口。")
        return False
    return True

appdict = {'通达信金融终端(开心果交易版) 副屏三':'个股联动', '通达信金融终端(开心果交易版) 副屏一':'上证指数','通达信金融终端(开心果交易版) 副屏二':'科创50ETF'}
runkey = {'个股联动':'ggld','上证指数':'03','科创50ETF':'090 588000'}
# applist = []

def set_tdx_screen_show(appdict=appdict,check=True):
    for window in ahk.list_windows():
        # print(window.__doc__)
        for app in appdict.keys():
            if window.title.find(app) >= 0:
                check_status = False
                print(f'class_name:{window.get_class()}')
                # print(f'title:{window.title}')
                if window.title.find(appdict[app]) < 0:
                    # Some more attributes
                    # print(f'text:{window.text}')
                    # print(window.text)           # window text -- or .get_text()
                    # print(window.get_position()) # (x, y, width, height)
                    # print(window.id)             # the ahk_id of the window
                    # print(window.pid)            # process ID -- or .get_pid()
                    # print(window.process_path)   # or .get_process_path()
                    print(f'Not Find title:{window.title} Run {runkey[appdict[app]].split()}....................')
                    if appdict[app] in runkey.keys():
                        for inputKey in runkey[appdict[app]].split():
                            window.activate()
                            # ahk.setKeyDelay(50)
                            time.sleep(0.3)
                            ahk.send(inputKey)
                            print(f'key:{inputKey}')
                            # ahk.win_get(title=f'ahk_pid {window.pid}')
                            # print(f'{window.pid} title:{window.text}')
                            time.sleep(0.3)
                            ahk.send('{Enter}')
                            time.sleep(0.5)
                            if len(runkey[appdict[app]].split()) > 1:
                                # ahk.send('{Enter}')
                                time.sleep(0.5)
                        # if len(runkey[appdict[app]].split()) > 1:
                        if check and check_status:
                            check_status =False
                            print(f'check:{app} : {appdict[app]}')
                            set_tdx_screen_show({app:appdict[app]},check=False)

                    else:
                        print(f'not find {app} {appdict[app]} in {runkey.keys()}')
                else:
                    print(f'Find title:{window.title} {appdict[app]}')

def broadcast_stock_code(stock_code,message_type='stock'):
    if isinstance(stock_code, dict):
        stock_code = stock_code['content']
        stock_code = stock_code.strip()
    if len(stock_code) == 6:
        codex = int(stock_code)
        if str(message_type) == 'stock':
            if str(stock_code)[0] in ['0','3','1']:
                codex = '6' + str(stock_code)
            elif str(stock_code)[0] in ['6','5']:
                codex = '7' + str(stock_code)
            # elif str(stock_code)[0] == '9':
            #     codex = '2' + str(stock_code)
            else:
                codex = '4' + str(stock_code)
        else:
            codex = int(stock_code)
        UWM_STOCK = win32api.RegisterWindowMessage('stock')
        print(win32con.HWND_BROADCAST,UWM_STOCK,str(codex))
        #系统广播
        win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
        send_code_message(stock_code)
# broadcast_stock_code('399001')
# broadcast_stock_code('833171')

def add_data(new_data):
    new_status=False
    with open("history_data.json", "r", encoding="utf-8") as f:
        old_data = json.load(f)
        if new_data['content'] not in [data['content'] for data in old_data]:
            old_data.insert(0, new_data)
            if len(old_data) > 200:
                old_data = old_data[:200]
            new_status = True
    if new_status:
        with open("history_data.json", "w", encoding="utf-8") as f:
            json.dump(old_data, f, indent=2, ensure_ascii=False)


def get_text(cur):
    if pre_hash != cur["hash"]:
        broadcast_stock_code(cur)
        # send_code_dfcf(cur)
    return cur


def get_img(cur, data, nowTime):
    cur_hash = hashlib.md5(data.tobytes()).hexdigest()
    cur["hash"] = cur_hash
    cur["type"] = "img"
    img_dir = os.path.join(os.path.dirname(__file__), "img")
    if not os.path.exists(img_dir):
        os.mkdir(img_dir)
    if pre_hash == cur_hash:
        return cur
    data.save(os.path.join(img_dir, f"{nowTime}.png"))
    cur["content"] = os.path.join(img_dir, f"{nowTime}.png")
    return cur


def get_folders():
    pass


def file_hash(file_path: str, hash_method) -> str:
    if not os.path.isfile(file_path):
        print('文件不存在。')
        return ''
    h = hash_method()
    with open(file_path, 'rb') as f:
        while b := f.read(8192):
            h.update(b)
    return h.hexdigest()


def get_files(cur, data, nowTime):
    cur["type"] = "file"
    for item in data:
        cur["content"] = os.path.join(os.path.dirname(__file__), "files", f"{nowTime}_{os.path.basename(item)}")
        cur["hash"] = file_hash(cur["content"], hashlib.md5)
        file_dir = os.path.join(os.path.dirname(__file__), "img")
        if not os.path.exists(file_dir):
            os.mkdir(file_dir)
        shutil.copy(item, os.path.join(file_dir, f"{nowTime}_{os.path.basename(item)}"))
    return cur


def setImage(data):
    clip.OpenClipboard()  # 打开剪贴板
    clip.EmptyClipboard()  # 先清空剪贴板
    clip.SetClipboardData(win32con.CF_DIB, data)  # 将图片放入剪贴板
    clip.CloseClipboard()


def set_clipboard_img(path):
    img = Image.open(path)
    output = BytesIO()
    img.save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    setImage(data)


async def get_clipboard_contents():
    global pre_hash

    while 1:
        await asyncio.sleep(0.5)
        
        try:
            content = pyperclip.paste()
        except pyperclip.PyperclipWindowsException as e:
            # print(e)
            time.sleep(1)
            continue 

        # content = pyperclip.paste()
        content = content.strip()
        if len(content.split()) > 1:
            if  isDigit(content.split()[0]):
                content = content.split()[0]
        if not isDigit(content):
            continue
        # nowTime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        nowTime = date.today().strftime('%Y-%m-%d')

        cur = {
            "type": "text",
            "content": content,
            "create_time": nowTime,
            "hash": hashlib.md5(content.encode("utf8")).hexdigest()
        }

        if len(content) == 6 and (content.startswith(('00','1','30')) or content.startswith(('5', '6', '8','9'))):
            if content:
                cur = get_text(cur)
            else:
                try:
                    data = ImageGrab.grabclipboard()
                except:
                    continue
                if isinstance(data, list):
                    cur = get_files(cur, data, nowTime)
                elif isinstance(data, Image.Image):
                    cur = get_img(cur, data, nowTime)

                else:
                    continue

        else:
            continue

        if pre_hash == cur["hash"]: continue
        pre_hash = cur["hash"]
        add_data(cur)
        yield cur

if __name__ == '__main__':
    # 让同花顺切换到股票代码
    # search_ths_data('000006')
    pass