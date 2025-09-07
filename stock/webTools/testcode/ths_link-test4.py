import time
import threading
import psutil
from ctypes import windll, c_size_t, byref
import win32gui
import win32api

# --------------------------
# 内核常量和接口
# --------------------------
kernel32 = windll.kernel32
PROCESS_ALL_ACCESS = 0x1F0FFF
VIRTUAL_MEM = 0x3000  # MEM_COMMIT | MEM_RESERVE
PAGE_READWRITE = 0x04

# --------------------------
# 获取 hexin.exe 进程句柄
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
# 查找 THS 窗口句柄
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
# 字节流转换
# --------------------------
def bytes_16(dec_num, code):
    ascii_char = chr(dec_num)
    codex = ascii_char + str(code)
    return codex.encode('ascii', 'ignore')

def ths_convert_code(code: str, dec_num: int):
    """
    代码转换，可传 dec_num 前缀
    """
    code = str(code).zfill(6)
    if str(code)[0] == '6':
        bytes_codex = bytes_16(dec_num, code)
    elif str(code).startswith('11'):
        bytes_codex = bytes_16(dec_num, code)
    elif str(code).startswith('12'):
        bytes_codex = bytes_16(dec_num, code)
    elif str(code).startswith('15'):
        bytes_codex = bytes_16(dec_num, code)
    else:
        bytes_codex = bytes_16(dec_num, code)
    return bytes_codex

# --------------------------
# 发送股票代码
# --------------------------
def send_code_message(code, ths_process_handle, ths_window_handle, dec_num):
    bytes_str = ths_convert_code(code, dec_num)
    argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
    if not argv_address:
        return False
    written = c_size_t(0)
    kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))
    # win32gui.SetForegroundWindow(ths_window_handle)
    time.sleep(0.1)
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
    print(f"发送成功，股票: {code}, 字节流: {bytes_str.hex()} 前缀: {hex(dec_num)}")
    return True

# def send_code_message(code, ths_process_handle, ths_window_handle, dec_num):
#     # 保存发送前窗口
#     hwnd_before = win32gui.GetForegroundWindow()

#     # 构造字节流
#     bytes_str = ths_convert_code(code, dec_num)
#     argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
#     written = c_size_t(0)
#     kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))

#     # 临时激活 THS 发送
#     win32gui.SetForegroundWindow(ths_window_handle)
#     time.sleep(0.05)
#     win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)

#     # 切回原窗口
#     if hwnd_before:
#         time.sleep(0.05)
#         win32gui.SetForegroundWindow(hwnd_before)

#     print(f"发送成功，股票: {code}, 字节流: {bytes_str.hex()} 前缀: {hex(dec_num)}")
#     return True

# --------------------------
# 自动确认，默认成功，手动输入失败
# --------------------------

'''
def auto_confirm(timeout=3):
    """
    默认成功，等待用户输入，若输入任意字符则认为失败
    """
    result = [True]  # 默认成功
    def get_input():
        val = input(f"输入任意字符认为失败，{timeout}秒后自动确认成功: ").strip()
        if val:
            result[0] = False

    t = threading.Thread(target=get_input)
    t.start()
    t.join(timeout)
    return result[0]
'''

'''
def auto_confirm(timeout=3):
    """
    等待用户输入，默认成功。
    手动输入任意字符算失败。
    """
    import threading

    result = [True]  # 默认成功

    def get_input():
        val = input(f"输入任意字符认为失败，{timeout}秒后自动确认成功: ").strip()
        if val:
            result[0] = False  # 输入任意字符 => 失败

    t = threading.Thread(target=get_input)
    t.daemon = True
    t.start()
    t.join(timeout)
    return result[0]
'''


import msvcrt
import time

def auto_confirm(timeout=3):
    start = time.time()
    print(f"输入任意字符认为失败，{timeout}秒后自动确认成功: ", end="", flush=True)
    while time.time() - start < timeout:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()  # 读取一个字符
            return False  # 输入则失败
        time.sleep(0.05)
    print()  # 换行
    return True  # 超时默认成功

# --------------------------
# 自动测试前缀
# --------------------------
def test_603_stocks_prefix(stock_codes):
    ths_process_handle = ths_prc_hwnd()
    ths_window_handle = find_window()
    if not ths_process_handle or not ths_window_handle:
        print("无法获取进程或窗口句柄")
        return
    
    result = {}
    
    # for code in stock_codes:
    #     success_prefix = None
    #     for prefix in [0x16, 0x11]:  # 尝试前缀顺序
    #         send_code_message(code, ths_process_handle, ths_window_handle, prefix)
            
    #         # 默认成功，手动输入任意字符算失败
    #         is_success = auto_confirm(timeout=3)
            
    #         if is_success:
    #             success_prefix = prefix
    #             break
    #     result[code] = success_prefix
    #     print(f"{code} 使用前缀 {hex(success_prefix) if success_prefix else '失败'}")
    


    for code in stock_codes:
        success_prefix = None
        for prefix in [0x16, 0x11]:  # 尝试前缀顺序
            send_code_message(code, ths_process_handle, ths_window_handle, prefix)
            is_success = auto_confirm(timeout=3)
            if is_success:  # 成功就记录
                success_prefix = prefix
                break  # 停止尝试下一个前缀
            else:
                print(f"{code} 前缀 {hex(prefix)} 失败，尝试下一个前缀")

        if success_prefix is None:
            print(f"{code} 所有前缀尝试失败")
        else:
            print(f"{code} 使用前缀 {hex(success_prefix)}")

    result[code] = success_prefix
    print(f"{code} 使用前缀 {hex(success_prefix) if success_prefix else '失败'}")
    
    # 分组输出
    group_16 = [code for code, pre in result.items() if pre == 0x16]
    group_11 = [code for code, pre in result.items() if pre == 0x11]
    failed = [code for code, pre in result.items() if pre is None]

    print("\n--- 分组结果 ---")
    print("前缀 0x16:", group_16)
    print("前缀 0x11:", group_11)
    print("发送失败:", failed)

# --------------------------
# 执行测试
# --------------------------
if __name__ == "__main__":
    stock_codes = ["603268","603839","603843","603855"]
    test_603_stocks_prefix(stock_codes)
