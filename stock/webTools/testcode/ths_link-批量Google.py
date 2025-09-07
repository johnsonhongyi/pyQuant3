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

# --------------------------
# Auto confirm input
# --------------------------
def auto_confirm(timeout=4):
    print(f"Press any key to fail, auto-confirm success in {timeout} seconds: ", end="", flush=True)
    start = time.time()
    while time.time() - start < timeout:
        if msvcrt.kbhit():
            _ = msvcrt.getwch()
            print()
            return False  # manual input counts as failure
        time.sleep(0.05)
    print()
    return True  # timeout counts as success

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
    win32gui.SetForegroundWindow(ths_window_handle)
    time.sleep(0.05)
    win32api.SendMessage(ths_window_handle, 1168, 0, argv_address)

    # Switch back to previous window
    if hwnd_before:
        time.sleep(0.05)
        win32gui.SetForegroundWindow(hwnd_before)

    print(f"Sent code: {code}, byte stream: {bytes_str.hex()}, prefix: {hex(dec_num)}")
    return True

# --------------------------
# Batch test prefixes
# --------------------------
def batch_test_prefix(stock_codes, ths_process_handle, ths_window_handle):
    result = {}
    for code in stock_codes:
        success_prefix = None
        for prefix in [0x16, 0x11]:
            send_code_message(code, ths_process_handle, ths_window_handle, prefix)
            if auto_confirm(timeout=3):
                success_prefix = prefix
                break  # stop if successful
            else:
                print(f"{code} prefix {hex(prefix)} failed, trying next prefix")
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
    stock_codes = ["603268", "603839", "603843", "603855"]
    ths_process_handle = ths_prc_hwnd()
    ths_window_handle = find_window()
    batch_test_prefix(stock_codes, ths_process_handle, ths_window_handle)
