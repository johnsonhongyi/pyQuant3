import time
import win32api
import msvcrt
import threading
import psutil
from ctypes import windll, c_size_t, byref
import win32gui

# --------------------------
# Kernel constants and interfaces
# --------------------------
kernel32 = windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
VIRTUAL_MEM = 0x3000  # MEM_COMMIT | MEM_RESERVE
PAGE_READWRITE = 0x04

# --------------------------
# Get hexin.exe process handle
# --------------------------
def ths_prc_hwnd():
    for pid in psutil.pids():
        try:
            proc = psutil.Process(pid)
            if proc.name().lower() == 'hexin.exe':
                handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, int(pid))
                if handle:
                    return handle
        except:
            continue
    return None

# --------------------------
# Find THS window handle
# --------------------------
def find_window(title_substr="同花顺"):
    hwnd_found = []
    def enum_win(hwnd_enum, lParam):
        if win32gui.IsWindowVisible(hwnd_enum):
            text = win32gui.GetWindowText(hwnd_enum)
            if title_substr in text:
                hwnd_found.append(hwnd_enum)
    win32gui.EnumWindows(enum_win, None)
    if hwnd_found:
        hwnd = hwnd_found[0]
        win32gui.ShowWindow(hwnd, 5)  # SW_SHOW
        return hwnd
    return None

# --------------------------
# Convert code to byte stream
# --------------------------
def bytes_16(dec_num, code):
    ascii_char = chr(dec_num)
    codex = ascii_char + str(code)
    return codex.encode('ascii', 'ignore')

def ths_convert_code(code: str, dec_num: int):
    code = str(code).zfill(6)
    return bytes_16(dec_num, code)



def monitor_hexin_for_success(hexin_window_handle, timeout=3):
    start = time.time()
    while time.time() - start < timeout:
        # Check window text for stock code (modify this to match application's expected response)
        window_text = win32gui.GetWindowText(hexin_window_handle)
        if "Stock Code" in window_text:  # Replace with actual success indicator
            return True  # success detected
        time.sleep(0.05)  # Check every 50ms
    return False  # timeout

# if msvcrt.kbhit():
#     print(f"\ntime:{time.time() - start:.2f}", flush=True)
#     inputkey = msvcrt.getwch()
#     print(f"inputkey: {inputkey}", flush=True), flush=True)
#     return False  # manual input counts as failure
# time.sleep(0.05)

import keyboard
import time
import win32gui
# ... other imports

# import tushare as ts
import pandas as pd

# # 替换成你的 tushare token
# token = "your_token_here"
# ts.set_token(token)
# pro = ts.pro_api()

# # 获取所有在市股票
# df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,list_date')

# # 筛选 603 开头股票
# df_603 = df[df['symbol'].str.startswith('603')]

# # 提取代码列表
# codes_603 = df_603['symbol'].tolist()

# # 输出前 10 个看看
# print("603 开头股票数量:", len(codes_603))
# print("示例:", codes_603[:10])

# # 保存
# df_603.to_csv("stocks_603.csv", index=False, encoding="utf-8-sig")
# with open("stocks_603.txt", "w", encoding="utf-8") as f:
#     f.write("\n".join(codes_603))
import os
import json
codelist = []
ths_code=[]
# filename = "data.json"
filename= "D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock\\JSONData\\stock_codes.conf"
# 检查文件是否存在
if os.path.exists(filename):
    print(f"{filename} exists, loading...")
    with open(filename, "r", encoding="utf-8") as f:
        codelist = json.load(f)['stock']
        ths_code = [co for co in codelist if co.startswith('603')]
    print("Loaded:", len(code603))
# else:
#     print(f"{filename} not found, creating...")
#     data = {"code": [], "prefix": None}
#     with open(filename, "w", encoding="utf-8") as f:
#         json.dump(data, f, ensure_ascii=False, indent=4)

# with open(filename) as f:
#     codelist = json.load(f)['stock']


# loaded_df = pd.read_csv("stocks_603.txt", encoding='utf-8-sig')

# 603code=[co for co in codelist if co.start('603')]
# code603 = [co for co in codelist if co.startswith('603')]

def auto_confirmFkey(ths_window_handle, timeout=4):
    print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        if keyboard.is_pressed('f'): # Or any key you want to designate as "fail"
            print("\nManual fail detected.")
            return False
        # ... The rest of your confirmation logic
        time.sleep(0.1)
    print()
    return True


def auto_confirm(ths_window_handle, timeout=1):
    print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
    start = time.time()
    
    # We use a separate thread to listen for key presses without blocking
    key_pressed_flag = threading.Event()
    keyboard.on_press(lambda e: key_pressed_flag.set())

    while time.time() - start < timeout:
        if key_pressed_flag.is_set():
            print("\nManual fail detected.")
            keyboard.unhook_all()
            return False
            
        # Optional: Add application confirmation logic here if needed
        # if monitor_hexin_for_success(ths_window_handle, timeout=3):
        #     print("Hexin application confirmed success.")
        #     keyboard.unhook_all()
        #     return True 

        time.sleep(0.05)
    
    print()
    keyboard.unhook_all()
    return True
# def auto_confirm(ths_window_handle, timeout=4):
#     print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
#     start = time.time()
#     while time.time() - start < timeout:
#         inputkey = msvcrt.getwch()
#         print(f"\nDetected inputkey: {inputkey}", flush=True)
#         # flush all extra keys
#         while msvcrt.kbhit():
#             _ = msvcrt.getwch()
#         return False
#     print()
#     return True # Default to failure if timeout

# --------------------------
# Auto confirm input
# --------------------------
# def auto_confirm(timeout=4):
#     print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
#     start = time.time()
#     while time.time() - start < timeout:
#         if msvcrt.kbhit():
#             _ = msvcrt.getwch()
#             print()
#             return False  # manual input counts as failure
#         time.sleep(0.05)
#     print()
#     return True  # timeout counts as success

# --------------------------
# Send code message
# --------------------------
def send_code_message(code, ths_process_handle, ths_window_handle, dec_num):
    hwnd_before = win32gui.GetForegroundWindow()

    bytes_str = ths_convert_code(code, dec_num)
    argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
    written = c_size_t(0)
    kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))

    # Temporarily activate THS window to send
    # win32gui.SetForegroundWindow(ths_window_handle)
    # time.sleep(0.05)
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)

    # Switch back to previous window
    # if hwnd_before:
    #     time.sleep(0.05)
    #     win32gui.SetForegroundWindow(hwnd_before)

    print(f"Sent code: {code}, byte stream: {bytes_str.hex()}, prefix: {hex(dec_num)}")
    return True

# --------------------------
# Batch test prefixes (Fixed)
# --------------------------
def batch_test_prefix(stock_codes, ths_process_handle, ths_window_handle):
    result = {}
    for code in stock_codes:
        success_prefix = None
        for prefix in [0x11,0x16]:
            send_code_message(code, ths_process_handle, ths_window_handle, prefix)
            if auto_confirm(ths_window_handle,timeout=3):
                success_prefix = prefix
                break  # stop if successful
            else:
                # User pressed a key, indicating a failure.
                # Stop checking prefixes for the current code and mark it as failed.
                print(f"{code} prefix {hex(prefix)} failed due to manual input.")
                success_prefix = None
                break  # Exit the inner loop to check the next stock code
        result[code] = success_prefix

    # Group results
    group = {}
    for code, prefix in result.items():
        key = hex(prefix) if prefix else 'failed'
        group.setdefault(key, []).append(code)

    print("\n--- Group Results ---")
    for prefix, codes in group.items():
        print(f"Prefix {prefix}: {codes}")

    return result

# --------------------------
# Main example
# --------------------------
if __name__ == "__main__":
    # stock_codes = ["603268", "603839", "603843", "603855"]
    # stock_codes = code603[-100:]
    stock_codes = ths_code[-100:]

    ths_process_handle = ths_prc_hwnd()
    ths_window_handle = find_window()
    if ths_process_handle and ths_window_handle:
        batch_test_prefix(stock_codes, ths_process_handle, ths_window_handle)
    else:
        print("Could not find hexin.exe process or window.")
