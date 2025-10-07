import sys
import os
import ctypes
from ctypes import wintypes 
import tempfile # 假设你已经导入了 tempfile

# --- Win32 API 用于获取 EXE 原始路径 (仅限 Windows) ---
def _get_win32_exe_path():
    # ... (保持不变) ...
    MAX_PATH_LENGTH = 32767 
    buffer = ctypes.create_unicode_buffer(MAX_PATH_LENGTH)
    ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, MAX_PATH_LENGTH)
    return os.path.dirname(os.path.abspath(buffer.value))


def get_base_path():
    """
    获取程序基准路径。在 Windows 打包环境 (Nuitka/PyInstaller) 中，
    使用 Win32 API 优先获取真实的 EXE 目录。
    """
    
    # 检查是否为 Python 解释器运行
    is_interpreter = os.path.basename(sys.executable).lower() in ('python.exe', 'pythonw.exe')
    
    # 1. 普通 Python 脚本模式
    if is_interpreter and not getattr(sys, "frozen", False):
        # 只有当它是 python.exe 运行 且 没有 frozen 标志时，才进入脚本模式
        try:
            # 此时 __file__ 是可靠的
            path = os.path.dirname(os.path.abspath(__file__))
            print(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
            return path
        except NameError:
             pass # 忽略交互模式
    
    # 2. Windows 打包模式 (Nuitka/PyInstaller EXE 模式)
    # 只要不是解释器运行，或者 sys.frozen 被设置，我们就认为是打包模式
    if sys.platform.startswith('win'):
        try:
            # 无论是否 Onefile，Win32 API 都会返回真实 EXE 路径
            real_path = _get_win32_exe_path()
            
            # 核心：确保我们返回的是 EXE 的真实目录
            if real_path != os.path.dirname(os.path.abspath(sys.executable)):
                 # 这是一个强烈信号：sys.executable 被欺骗了 (例如 Nuitka Onefile 启动器)，
                 # 或者程序被从其他地方调用，我们信任 Win32 API。
                 print(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
                 return real_path
            
            # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
            if not is_interpreter:
                 print(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
                 return real_path

        except Exception:
            pass 

    # 3. 最终回退（适用于所有打包模式，包括 Linux/macOS）
    if getattr(sys, "frozen", False) or not is_interpreter:
        path = os.path.dirname(os.path.abspath(sys.executable))
        print(f"[DEBUG] Path Mode: Final Fallback. Path: {path}")
        return path

    # 4. 极端脚本回退
    print(f"[DEBUG] Path Mode: Final Script Fallback.")
    return os.path.dirname(os.path.abspath(sys.argv[0]))
        
# def get_base_path():
#     """
#     获取程序基准路径。优先使用 Win32 API 获取真正的 EXE 目录。
#     """
    
#     # 1. Windows 打包模式优先判断
#     # 检查是否是 Windows 平台 且 处于任何形式的打包状态
#     # if sys.platform.startswith('win') and getattr(sys, "frozen", False):
#     if sys.platform.startswith('win') :
#         try:
#             # 无论 sys.executable 是否被篡改，Win32 API 都会返回真实路径
#             real_path = _get_win32_exe_path()
#             print(f"[DEBUG] Path Mode: WinAPI (Frozen). Path: {real_path}")
#             return real_path
#         except Exception:
#             pass # Win32 API 失败，继续回退

#     # 2. PyInstaller 模式 (_MEIPASS 存在)
#     if hasattr(sys, "_MEIPASS"):
#         # ... (PyInstaller 逻辑)
#         path = os.path.dirname(os.path.abspath(sys.executable))
#         print(f"[DEBUG] Path Mode: PyInstaller. Path: {path}")
#         return path

#     # 3. Nuitka/其他打包模式回退（使用 sys.executable）
#     if getattr(sys, "frozen", False):
#         # Nuitka Standalone 或其他情况
#         path = os.path.dirname(os.path.abspath(sys.executable))
#         print(f"[DEBUG] Path Mode: Nuitka Fallback. Path: {path}")
#         return path

#     # 4. 普通 Python 脚本模式
#     print(f"[DEBUG] Path Mode: Python Script")
#     return os.path.dirname(os.path.abspath(__file__))

def main():
    # ❗ 修正：现在只调用修正后的 get_base_path
    base_path = get_base_path() 
    
    # 打印新的调试信息
    print("-" * 50)
    print("程序模式：", "Nuitka Onefile" if 'onefile_' in os.path.basename(os.path.abspath(sys.executable)) else "Normal/Standalone")
    print("sys.executable =", os.path.abspath(sys.executable))
    print("_get_win32_exe_path =", _get_win32_exe_path())
    print("当前工作目录 =", os.getcwd())
    print("-" * 50)
    print(f"✅ 最终基准路径: {base_path}")
    
    # ... (其他 main 函数内容) ...

# ❗ 修正：确保 get_base_path2 被删除或重命名为 get_base_path
if __name__ == "__main__":
    main()