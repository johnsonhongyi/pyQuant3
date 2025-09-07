# import time
# import psutil
# from ctypes import windll, c_size_t, byref, create_string_buffer
# import win32gui
# import win32api

# # --------------------------
# # 内核常量和接口
# # --------------------------
# kernel32 = windll.kernel32
# PROCESS_ALL_ACCESS = 0x1F0FFF
# VIRTUAL_MEM = 0x3000  # MEM_COMMIT | MEM_RESERVE
# PAGE_READWRITE = 0x04

# # --------------------------
# # 获取 hexin.exe 进程句柄
# # --------------------------
# def ths_prc_hwnd():
#     for pid in psutil.pids():
#         try:
#             proc = psutil.Process(pid)
#             if proc.name().lower() == 'hexin.exe':
#                 handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, int(pid))
#                 if handle:
#                     return handle
#         except:
#             continue
#     return None

# # --------------------------
# # 查找 THS 窗口句柄
# # --------------------------
# def find_window(title_substr="同花顺"):
#     hwnd_found = []
#     def enum_win(hwnd_enum, lParam):
#         if win32gui.IsWindowVisible(hwnd_enum):
#             text = win32gui.GetWindowText(hwnd_enum)
#             if title_substr in text:
#                 hwnd_found.append(hwnd_enum)
#     win32gui.EnumWindows(enum_win, None)
#     return hwnd_found[0] if hwnd_found else None

# # --------------------------
# # 字节流转换
# # --------------------------
# def bytes_16(dec_num, code):
#     ascii_char = chr(dec_num)
#     codex = ascii_char + str(code)
#     return codex.encode('ascii', 'ignore')

# def ths_convert_code_test(code, prefix):
#     return bytes_16(prefix, code)

# # --------------------------
# # 发送股票代码
# # --------------------------
# def send_code_message(bytes_str, ths_process_handle, ths_window_handle):
#     argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
#     if not argv_address:
#         return False
#     written = c_size_t(0)
#     kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))
#     win32gui.SetForegroundWindow(ths_window_handle)
#     time.sleep(0.1)
#     win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
#     return True

# # --------------------------
# # 自动测试前缀
# # --------------------------
# def test_603_stocks_prefix(stock_codes):
#     ths_process_handle = ths_prc_hwnd()
#     ths_window_handle = find_window()
#     if not ths_process_handle or not ths_window_handle:
#         print("无法获取进程或窗口句柄")
#         return
    
#     result = {}
    
#     for code in stock_codes:
#         success_prefix = None
#         for prefix in [0x16, 0x11]:
#             bytes_str = ths_convert_code_test(code, prefix)
#             send_code_message(bytes_str, ths_process_handle, ths_window_handle)
#             # 假设这里可以人工或者程序检查 THS 是否显示正确
#             # 可以结合 OCR 或 ReadProcessMemory 判断，示例中用输入模拟
#             check = input(f"股票 {code} 显示正确？(y/n) 前缀 {hex(prefix)}: ").lower()
#             if check == 'y':
#                 success_prefix = prefix
#                 break
#         result[code] = success_prefix
#         print(f"{code} 使用前缀 {hex(success_prefix) if success_prefix else '失败'}")
    
#     # 分组输出
#     group_16 = [code for code, pre in result.items() if pre == 0x16]
#     group_11 = [code for code, pre in result.items() if pre == 0x11]
#     failed = [code for code, pre in result.items() if pre is None]

#     print("\n--- 分组结果 ---")
#     print("前缀 0x16:", group_16)
#     print("前缀 0x11:", group_11)
#     print("发送失败:", failed)

# # --------------------------
# # 执行测试
# # --------------------------
# if __name__ == "__main__":
#     # 示例 603 开头股票列表，可用 Tushare 或 Excel 获取完整
#     stock_codes = ["603268","603839","603843","603855"]
#     test_603_stocks_prefix(stock_codes)




# import time
# import threading
# import psutil
# from ctypes import windll, c_size_t, byref
# import win32gui
# import win32api

# # --------------------------
# # 内核常量和接口
# # --------------------------
# kernel32 = windll.kernel32
# PROCESS_ALL_ACCESS = 0x1F0FFF
# VIRTUAL_MEM = 0x3000  # MEM_COMMIT | MEM_RESERVE
# PAGE_READWRITE = 0x04

# # --------------------------
# # 获取 hexin.exe 进程句柄
# # --------------------------
# def ths_prc_hwnd():
#     for pid in psutil.pids():
#         try:
#             proc = psutil.Process(pid)
#             if proc.name().lower() == 'hexin.exe':
#                 handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, int(pid))
#                 if handle:
#                     return handle
#         except:
#             continue
#     return None

# # --------------------------
# # 查找 THS 窗口句柄
# # --------------------------
# def find_window(title_substr="同花顺"):
#     hwnd_found = []
#     def enum_win(hwnd_enum, lParam):
#         if win32gui.IsWindowVisible(hwnd_enum):
#             text = win32gui.GetWindowText(hwnd_enum)
#             if title_substr in text:
#                 hwnd_found.append(hwnd_enum)
#     win32gui.EnumWindows(enum_win, None)
#     if hwnd_found:
#         hwnd = hwnd_found[0]
#         # 如果最小化，先显示
#         win32gui.ShowWindow(hwnd, 5)  # SW_SHOW
#         return hwnd
#     return None

# # --------------------------
# # 字节流转换（成功测试版）
# # --------------------------
# def bytes_16(dec_num, code):
#     ascii_char = chr(dec_num)
#     codex = ascii_char + str(code)
#     return codex.encode('ascii', 'ignore')

# def ths_convert_codeOK(code):
#     code = str(code).zfill(6)
#     if code.startswith('6'):
#         dec_num = int('11', 16)
#         if code.startswith('603'):
#             # 603 系列部分股票特殊前缀
#             if code in ["603268","603843"]:
#                 dec_num = 0x16
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('11'):
#         dec_num = int('13', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('12'):
#         dec_num = int('23', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('15'):
#         dec_num = int('24', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     else:
#         dec_num = int('21', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     return bytes_codex

def ths_convert_code(code: str, dec_num: int):
    '''
    代码转换
    :param code:
    :return:
    '''
    # 上海，深圳股票判断;
    if str(code)[0] == '6':
        # 将16进制数转换为整数
        # dec_num = int('11', 16)
        # if code.startswith('6'):
        bytes_codex = bytes_16(dec_num, code)
    # 11开头的可转债
    elif str(code).startswith('11'):
        # 将16进制数转换为整数
        # dec_num = int('13', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('12'):
        # 将16进制数转换为整数
        # dec_num = int('23', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('15'):
        # 将16进制数转换为整数
        # dec_num = int('24', 16)
        bytes_codex = bytes_16(dec_num, code)

    else:
        # 将16进制数转换为整数
        # dec_num = int('21', 16)
        bytes_codex = bytes_16(dec_num, code)

    return bytes_codex
    
# # --------------------------
# # 发送股票代码
# # --------------------------
# def send_code_message(code, ths_process_handle, ths_window_handle):
#     bytes_str = ths_convert_codeOK(code)
#     argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
#     if not argv_address:
#         return False
#     written = c_size_t(0)
#     kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))
#     win32gui.SetForegroundWindow(ths_window_handle)
#     time.sleep(0.1)
#     win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
#     print(f"发送成功，股票: {code}, 字节流: {bytes_str.hex()}")
#     return True

# # --------------------------
# # 带超时手动确认函数
# # --------------------------
# def timed_input_any(prompt, timeout=3, default='n'):
#     user_input = [None]

#     def get_input():
#         val = input(prompt).strip()
#         if val:
#             user_input[0] = val

#     thread = threading.Thread(target=get_input)
#     thread.daemon = True
#     thread.start()
#     thread.join(timeout)

#     return True if user_input[0] else False  # 有输入算成功，超时返回 False

# # --------------------------
# # 自动测试前缀
# # --------------------------
# def test_603_stocks_prefix(stock_codes):
#     ths_process_handle = ths_prc_hwnd()
#     ths_window_handle = find_window()
#     if not ths_process_handle or not ths_window_handle:
#         print("无法获取进程或窗口句柄")
#         return
    
#     result = {}
    
#     for code in stock_codes:
#         success_prefix = None
#         for prefix in [0x16, 0x11]:
#             # 临时修改 ths_convert_code 测试前缀
#             bytes_str = bytes_16(prefix, code)
#             send_code_message(code, ths_process_handle, ths_window_handle)
            
#             # 超时 3 秒默认失败，任意输入算成功
#             is_success = timed_input_any(f"股票 {code} 显示正确？输入任意字符算成功，3秒默认失败 前缀 {hex(prefix)}: ", timeout=3)
            
#             if is_success:
#                 success_prefix = prefix
#                 break  # 成功就不用尝试下一个前缀
#         result[code] = success_prefix
#         print(f"{code} 使用前缀 {hex(success_prefix) if success_prefix else '失败'}")
    
#     # 分组输出
#     group_16 = [code for code, pre in result.items() if pre == 0x16]
#     group_11 = [code for code, pre in result.items() if pre == 0x11]
#     failed = [code for code, pre in result.items() if pre is None]

#     print("\n--- 分组结果 ---")
#     print("前缀 0x16:", group_16)
#     print("前缀 0x11:", group_11)
#     print("发送失败:", failed)

# # --------------------------
# # 执行测试
# # --------------------------
# if __name__ == "__main__":
#     # 示例 603 开头股票列表，可用 Tushare 获取完整列表
#     stock_codes = ["603268","603839","603843","603855"]
#     test_603_stocks_prefix(stock_codes)




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
# 字节流转换（成功测试版）
# --------------------------
def bytes_16(dec_num, code):
    ascii_char = chr(dec_num)
    codex = ascii_char + str(code)
    return codex.encode('ascii', 'ignore')

# def ths_convert_codeOK(code):
#     code = str(code).zfill(6)
#     if code.startswith('6'):
#         dec_num = int('11', 16)
#         if code.startswith('603'):
#             if code in ["603268","603843"]:
#                 dec_num = 0x16
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('11'):
#         dec_num = int('13', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('12'):
#         dec_num = int('23', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     elif code.startswith('15'):
#         dec_num = int('24', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     else:
#         dec_num = int('21', 16)
#         bytes_codex = bytes_16(dec_num, code)
#     return bytes_codex

# --------------------------
# 发送股票代码
# --------------------------
def send_code_message(code, ths_process_handle, ths_window_handle):
    bytes_str = ths_convert_code(code)
    argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
    if not argv_address:
        return False
    written = c_size_t(0)
    kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))
    win32gui.SetForegroundWindow(ths_window_handle)
    time.sleep(0.1)
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
    print(f"发送成功，股票: {code}, 字节流: {bytes_str.hex()}")
    return True

# --------------------------
# 自动确认，默认成功，手动输入失败
# --------------------------
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
    
    for code in stock_codes:
        success_prefix = None
        for prefix in [0x16, 0x11]:
            # 临时修改 ths_convert_code 测试前缀
            bytes_str = bytes_16(prefix, code)
            send_code_message(code, ths_process_handle, ths_window_handle)
            
            # 默认成功，手动输入任意字符算失败
            is_success = auto_confirm(timeout=3)
            
            if is_success:
                success_prefix = prefix
                break  # 成功就不用尝试下一个前缀
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
