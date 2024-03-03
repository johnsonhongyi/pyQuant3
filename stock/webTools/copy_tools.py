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

# import pandas as pd
# import sys
# sys.path.append("..")
# # from JSONData import tdx_data_Day as tdd
# # from JohnsonUtil import LoggerFactory as LoggerFactory
# # from JohnsonUtil import johnson_cons as ct
# from JohnsonUtil import commonTips as cct
# win32clipboard
# https://stackoverflow.com/questions/101128/how-do-i-read-text-from-the-windows-clipboard-in-python





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
        content = pyperclip.paste()
        content = content.strip()
        nowTime = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

        cur = {
            "type": "text",
            "content": content,
            "create_time": nowTime,
            "hash": hashlib.md5(content.encode("utf8")).hexdigest()
        }

        if len(content) == 6:
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
    search_ths_data('000006')