# import psutil
# import time
# from ctypes import windll, c_size_t, byref
# import win32gui
# import win32api

# # --------------------------
# # Windows 内核接口
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
#         except psutil.NoSuchProcess:
#             continue
#         except Exception as e:
#             print(f"获取进程句柄出错: {e}")
#     print("未找到 hexin.exe 进程")
#     return None

# # --------------------------
# # 查找窗口句柄
# # --------------------------
# def find_window(title_substr: str):
#     hwnd_found = []

#     def enum_win(hwnd_enum, lParam):
#         if win32gui.IsWindowVisible(hwnd_enum):
#             text = win32gui.GetWindowText(hwnd_enum)
#             if title_substr in text:
#                 hwnd_found.append(hwnd_enum)

#     win32gui.EnumWindows(enum_win, None)
#     return hwnd_found[0] if hwnd_found else None

# # --------------------------
# # 股票代码转换，支持 0x16 前缀
# # --------------------------
def bytes_16(dec_num, code):
    """
    将整数前缀和股票代码拼接为 ASCII 字节流
    :param dec_num: 前缀整数，例如 0x11, 0x16
    :param code: 股票代码字符串
    :return: bytes 类型
    """
    ascii_char = chr(dec_num)         # 将整数转换为 ASCII 字符
    codex = ascii_char + str(code)    # 拼接股票代码
    bytes_codex = codex.encode('ascii', 'ignore')  # 转为 bytes
    return bytes_codex

# def ths_convert_codeOK(code):
#     """
#     股票代码转换为 THS 可识别的字节流
#     :param code: 股票代码字符串
#     :return: bytes 类型
#     """
#     code = str(code).zfill(6)  # 补齐到6位
    
#     # 沪市股票
#     if code.startswith('6'):
#         dec_num = int('11', 16)      # 默认前缀
#         if code.startswith('603'):   # 603 系列特殊前缀
#             dec_num = 0x16
#         bytes_codex = bytes_16(dec_num, code)
        
#     # 11开头可转债
#     elif code.startswith('11'):
#         dec_num = int('13', 16)
#         bytes_codex = bytes_16(dec_num, code)
        
#     # 12开头可转债
#     elif code.startswith('12'):
#         dec_num = int('23', 16)
#         bytes_codex = bytes_16(dec_num, code)
        
#     # 15开头可转债
#     elif code.startswith('15'):
#         dec_num = int('24', 16)
#         bytes_codex = bytes_16(dec_num, code)
        
#     # 其他股票或默认
#     else:
#         dec_num = int('21', 16)
#         bytes_codex = bytes_16(dec_num, code)

#     return bytes_codex

# # --------------------------
# # 发送字节流到 THS
# # --------------------------
# def send_code_message(bytes_str: bytes, ths_process_handle, ths_window_handle):
#     if not ths_process_handle or not ths_window_handle:
#         print("进程或窗口句柄无效，无法发送")
#         return False

#     argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
#     if not argv_address:
#         print("分配内存失败")
#         return False

#     written = c_size_t(0)
#     kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))

#     win32gui.SetForegroundWindow(ths_window_handle)
#     time.sleep(0.1)

#     win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
#     return True

# # --------------------------
# # 批量发送测试
# # --------------------------
# def test_603_stocks(codes):
#     ths_process_handle = ths_prc_hwnd()
#     ths_window_handle = find_window("同花顺")  # 替换为 hexin.exe 窗口标题部分

#     if not ths_process_handle or not ths_window_handle:
#         print("无法获取进程或窗口句柄，测试结束")
#         return

#     for code in codes:
#         bytes_str = ths_convert_codeOK(code)
#         success = send_code_message(bytes_str, ths_process_handle, ths_window_handle)
#         print(f"发送股票: {code}, 字节流: {bytes_str.hex()}, 发送成功: {success}")
#         time.sleep(0.3)  # 防止消息堆叠

# # --------------------------
# # 测试执行
# # --------------------------
# if __name__ == "__main__":
#     stock_codes = ["603268", "603843", "603839",  "603855"]
#     test_603_stocks(stock_codes)



import time
import pyautogui
import pytesseract

# 发送股票函数，使用前缀
def send_code_message_with_prefix(code, prefix):
    bytes_str = bytes_16(prefix, code)
    # 调用你的 THS 发送函数
    # send_code_message(bytes_str, ths_process_handle, ths_window_handle)
    print(f"发送代码: {code}, 前缀: {hex(prefix)}, 字节流: {bytes_str.hex()}")
    time.sleep(0.5)  # 等待 THS 更新显示

# 检查窗口显示
def check_stock_display(expected_code, region=None):
    """
    region: (left, top, width, height) 可选，限制截图范围
    """
    screenshot = pyautogui.screenshot(region=region)
    text = pytesseract.image_to_string(screenshot)
    return expected_code in text

# 自动发送并重试前缀
def send_with_retry(code, candidate_prefixes=[0x16, 0x11], max_retry=2):
    for prefix in candidate_prefixes[:max_retry]:
        send_code_message_with_prefix(code, prefix)
        if check_stock_display(code):
            print(f"{code} 显示成功，使用前缀 {hex(prefix)}")
            return True
        else:
            print(f"{code} 显示失败，尝试下一个前缀")
    print(f"{code} 所有前缀尝试失败")
    return False

# --------------------------
# 批量测试
# --------------------------
stock_codes = ["603268", "603839", "603843", "603855"]
for code in stock_codes:
    send_with_retry(code, candidate_prefixes=[0x16, 0x11])
