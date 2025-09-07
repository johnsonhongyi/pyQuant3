import psutil
import time
from ctypes import windll, c_size_t, byref
import win32gui
import win32api

# --------------------------
# Windows 内核接口
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
        except psutil.NoSuchProcess:
            continue
        except Exception as e:
            print(f"获取进程句柄出错: {e}")
    print("未找到 hexin.exe 进程")
    return None

# --------------------------
# 查找窗口句柄
# --------------------------
def find_window(title_substr: str):
    hwnd_found = []

    def enum_win(hwnd_enum, lParam):
        if win32gui.IsWindowVisible(hwnd_enum):
            text = win32gui.GetWindowText(hwnd_enum)
            if title_substr in text:
                hwnd_found.append(hwnd_enum)

    win32gui.EnumWindows(enum_win, None)
    return hwnd_found[0] if hwnd_found else None

# def ths_convert_code(code: str) -> bytes:
#     code = str(code).zfill(6)
#     if code.startswith('6'):
#         prefix = 0x11
#     elif code.startswith('11'):
#         prefix = 0x13
#     elif code.startswith('12'):
#         prefix = 0x23
#     elif code.startswith('15'):
#         prefix = 0x24
#     else:
#         prefix = 0x21

#     b1 = (int(code[0]) << 4) | int(code[1])
#     b2 = (int(code[2]) << 4) | int(code[3])
#     b3 = (int(code[4]) << 4) | int(code[5])
#     return bytes([prefix, b1, b2, b3])

def bytes_16(dec_num, code):
    # num=ord(char)   # 将ASCII字符转换为对应的整数
    # ord('?') -> 63  chr(63) -> ? bytes_16(63, code) ->b'?833171'
    # char=chr(num) # 将整数转换为对应的ASCII字符
    ascii_char = chr(dec_num)  # 将整数转换为对应的ASCII字符
    codex = ascii_char + str(code)
    # 将Python字符串转换为bytes类型
    bytes_codex = codex.encode('ascii', 'ignore')
    return bytes_codex

def ths_convert_codeOK(code):
    '''
    代码转换
    :param code:
    :return:
    '''
    # 上海，深圳股票判断;
    if str(code)[0] == '6':
        # 将16进制数转换为整数
        dec_num = int('11', 16)
        if code.startswith('603'):
            dec_num = 0x16
        bytes_codex = bytes_16(dec_num, code)
    # 11开头的可转债
    elif str(code).startswith('11'):
        # 将16进制数转换为整数
        dec_num = int('13', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('12'):
        # 将16进制数转换为整数
        dec_num = int('23', 16)
        bytes_codex = bytes_16(dec_num, code)
    # 12开头的可转债
    elif str(code).startswith('15'):
        # 将16进制数转换为整数
        dec_num = int('24', 16)
        bytes_codex = bytes_16(dec_num, code)

    else:
        # 将16进制数转换为整数
        dec_num = int('21', 16)
        bytes_codex = bytes_16(dec_num, code)

    return bytes_codex


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

# --------------------------
# 自定义前缀生成字节流
# --------------------------
def ths_convert_with_prefix(code: str, prefix: int) -> bytes:
    code = str(code).zfill(6)
    b1 = (int(code[0]) << 4) | int(code[1])
    b2 = (int(code[2]) << 4) | int(code[3])
    b3 = (int(code[4]) << 4) | int(code[5])
    return bytes([prefix, b1, b2, b3])

# --------------------------
# 发送字节流到 THS
# --------------------------
def send_code_message_test(bytes_str: bytes, ths_process_handle, ths_window_handle):
    if not ths_process_handle or not ths_window_handle:
        print("进程或窗口句柄无效，无法发送")
        return

    # 分配目标内存
    argv_address = kernel32.VirtualAllocEx(ths_process_handle, 0, len(bytes_str), VIRTUAL_MEM, PAGE_READWRITE)
    if not argv_address:
        print("分配内存失败")
        return

    # 写入字节流
    written = c_size_t(0)
    kernel32.WriteProcessMemory(ths_process_handle, argv_address, bytes_str, len(bytes_str), byref(written))

    # 激活窗口
    win32gui.SetForegroundWindow(ths_window_handle)
    time.sleep(0.1)

    # 发送消息
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)
    print(f"发送成功，字节流: {bytes_str.hex()}")

# --------------------------
# 前缀暴力测试
# --------------------------
def test_603_prefix():
    # code = "603839"
    code = "603268"
    ths_process_handle = ths_prc_hwnd()
    ths_window_handle = find_window("同花顺")  # 替换为 hexin.exe 窗口标题部分

    if not ths_process_handle or not ths_window_handle:
        print("无法获取进程或窗口句柄，测试结束")
        return

    # 测试 0x10 ~ 0x1F 前缀
    # for prefix in range(0x10, 0x20):
    for prefix in range(0x16, 0x20):
        # bytes_str = ths_convert_with_prefix(code, prefix)
        bytes_str = ths_convert_code(code,prefix)
        print(f"\n尝试前缀: {hex(prefix)}")
        send_code_message_test(bytes_str, ths_process_handle, ths_window_handle)
        time.sleep(2)  # 观察窗口变化，防止消息堆叠

# --------------------------
# 执行测试
# --------------------------
if __name__ == "__main__":


    codel = ["603268","603843"]
    code = "603843"
    for co in codel:
        ths_process_handle = ths_prc_hwnd()
        ths_window_handle = find_window("同花顺")  # 替换为 hexin.exe 窗口标题部分
        bytes_str = ths_convert_codeOK(co)
        # bytes_str = ths_convert_code(code)
        send_code_message_test(bytes_str, ths_process_handle, ths_window_handle)
    
    # test_603_prefix()
    # test_603_prefix()

#  ["603268", "603843", "603839",  "603855"]
# "603268", "603843", 使用前缀0x16有效 "603839",  "603855"无效
# "603268", "603839", "603843", "603855" 查询发行时间板块有什么区别差异,前两个一组,后两个一组