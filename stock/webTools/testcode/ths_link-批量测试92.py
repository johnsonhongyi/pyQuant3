import time
import psutil
import win32gui
import win32api
import msvcrt
from ctypes import windll, c_size_t, byref
import keyboard
import threading
# ----------------- 核心常量 -----------------
kernel32 = windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
VIRTUAL_MEM = 0x3000
PAGE_READWRITE = 0x04
import json,os
code_ths= "code_ths_other.json"
# 检查文件是否存在
ths_code = ["603268", "603843","603813","603559","600421"]
if os.path.exists(code_ths):
    print(f"{code_ths} exists, loading...")
    with open(code_ths, "r", encoding="utf-8") as f:
        codelist = json.load(f)['stock']
        ths_code = [co for co in codelist if co.startswith('603')]
    print("Loaded:", len(ths_code))
else:
    print(f"{code_ths} not found, creating...")
    data = {"stock": ths_code}
    with open(code_ths, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
# ----------------- 获取 hexin.exe 进程句柄 -----------------
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

# ----------------- 查找 THS 窗口句柄 -----------------
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

# ----------------- 字节流转换 -----------------
def bytes_16(dec_num, code):
    ascii_char = chr(dec_num)
    codex = ascii_char + str(code)
    return codex.encode('ascii', 'ignore')

# ----------------- 发送股票代码 -----------------
def send_code_message(code, ths_process_handle, ths_window_handle, dec_num):
    hwnd_before = win32gui.GetForegroundWindow()
    bytes_str = bytes_16(dec_num, code)
    argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
    written = c_size_t(0)
    kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))
    # win32gui.SetForegroundWindow(ths_window_handle)
    time.sleep(0.05)
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
    if hwnd_before:
        time.sleep(0.05)
        win32gui.SetForegroundWindow(hwnd_before)
    print(f"Sent code: {code}, byte stream: {bytes_str.hex()}, prefix: {hex(dec_num)}")

# ----------------- 自动确认 -----------------
# def auto_confirm(timeout=3):
#     print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
#     start = time.time()
#     while time.time() - start < timeout:
#         if msvcrt.kbhit():
#             _ = msvcrt.getwch()
#             # 清空缓冲
#             while msvcrt.kbhit():
#                 _ = msvcrt.getwch()
#             print()
#             return False
#         time.sleep(0.05)
#     print()
#     return True
def auto_confirm(timeout=1):
    print(f"Press any key to True, auto-confirm success in {timeout} seconds: ", end="", flush=True)
    start = time.time()
    
    # We use a separate thread to listen for key presses without blocking
    key_pressed_flag = threading.Event()
    keyboard.on_press(lambda e: key_pressed_flag.set())

    while time.time() - start < timeout:
        if key_pressed_flag.is_set():
            print("\nManual fail detected.")
            keyboard.unhook_all()
            return True
            
        # Optional: Add application confirmation logic here if needed
        # if monitor_hexin_for_success(ths_window_handle, timeout=3):
        #     print("Hexin application confirmed success.")
        #     keyboard.unhook_all()
        #     return True 

        time.sleep(0.05)
    
    print()
    keyboard.unhook_all()
    return False

# ----------------- 批量测试 92 开头股票 -----------------
def batch_test_92(stock_codes, ths_process_handle, ths_window_handle,prefixes=None):
    result = {}
    if prefix_candidates is None:
        prefixes = [0x11, 0x13, 0x16, 0x21, 0x23, 0x24, 0x31, 0x32, 0x33]
    for code in stock_codes:
        success_prefix = None
        for prefix in prefixes:
            send_code_message(code, ths_process_handle, ths_window_handle, prefix)
            if auto_confirm(timeout=1):
                success_prefix = prefix
                break
            else:
                print(f"{code} with prefix {hex(prefix)} failed, try next.")
        result[code] = success_prefix

    # 分组输出
    group = {}
    for code, prefix in result.items():
        key = hex(prefix) if prefix else 'fail'
        group.setdefault(key, []).append(code)

    print("\n--- Group Results ---")
    for prefix, codes in group.items():
        print(f"Prefix {prefix}: {codes}")

    return result

# ----------------- 使用示例 -----------------
prefix_candidates = [
    0x11,  # 17 深交所主板 / 创业板
    0x12,  # 18 （少见，用于特殊品种）
    0x13,  # 19 可转债
    0x14,  # 20 测试备用
    0x15,  # 21 测试备用
    0x16,  # 22 上交所主板
    0x17,  # 23 测试备用
    0x18,  # 24 测试备用
    0x19,  # 25 测试备用
    0x1A,  # 26 测试备用
    0x1B,  # 27 测试备用
    0x1C,  # 28 测试备用
    0x1D,  # 29 测试备用
    0x1E,  # 30 测试备用
    0x1F,  # 31 测试备用
    0x20,  # 32 测试备用
    0x21,  # 33 常见于指数/92开头代码
    0x22,  # 34 测试备用
    0x23,  # 35 可转债第二组
    0x24,  # 36 基金/ETF
]

# prefix_dict = {hex(x): chr(x) for x in range(0x22, 0x30)}
prefix_dict = {int(x) for x in range(0x31, 0x40)}
# prefix_dict = {int(x) for x in range(0x21, 0x30)}
# prefix_dict = {int(x) for x in range(0x11, 0x20)}
print(prefix_dict)

stock_codes_92 = ["920056", "920123", "920456"]  # 填入要测试的 92 开头股票
stock_codes_92 = ["920110"]  # 填入要测试的 92 开头股票
# stock_codes_92 = ["430718"]  # 填入要测试的 92 开头股票
# stock_codes_92 = ["900901"]  # 填入要测试的 92 开头股票
# stock_codes_92 = ["600421"]  # 填入要测试的 92 开头股票
# stock_codes_92 = ["603268"]  # 填入要测试的 92 开头股票
ths_process_handle = ths_prc_hwnd()
ths_window_handle = find_window()
batch_test_92(stock_codes_92, ths_process_handle, ths_window_handle,prefix_dict)
