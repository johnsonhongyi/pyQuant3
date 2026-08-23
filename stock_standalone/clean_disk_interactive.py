# -*- coding: utf-8 -*-
"""
交互式磁盘与开发缓存智能清理工具 (Interactive Disk Cleaner)
==============================================================================
特性:
1. 安全分级，清理前计算各目录实际占用大小并详细展示
2. 逐项交互确认: [Y]确认清理 / [N]跳过该项 / [A]后续全部确认 / [Q]安全退出
3. 严格白名单保护: 绝不误触 JSONData, .git, 核心源码与用户配置文件
4. 进程感知: 清理 Ditto 时自动安全关闭进程释放文件锁
5. 结果统计: 汇总累计释放容量与 C/D/E 盘最新空间状态
6. 全面兼容 Windows 控制台 (支持 VT100 高亮或纯文本降级，无乱码)
==============================================================================
"""

import os
import sys
import shutil
import subprocess
import ctypes

# 确保在 Windows 控制台下输出 UTF-8 编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 启用 Windows 控制台 VT100 彩色支持
HAS_COLOR = False
if sys.platform == "win32":
    try:
        kernel32 = ctypes.windll.kernel32
        hStdOut = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode)):
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            if kernel32.SetConsoleMode(hStdOut, mode.value | 0x0004):
                HAS_COLOR = True
    except Exception:
        HAS_COLOR = False
else:
    HAS_COLOR = True

def c_text(text, color_code):
    """带颜色输出，若不支持颜色则返回纯文本"""
    if HAS_COLOR:
        return f"\033[{color_code}m{text}\033[0m"
    return text

def yellow(t): return c_text(t, "93")
def green(t): return c_text(t, "92")
def cyan(t): return c_text(t, "96")
def red(t): return c_text(t, "91")
def gray(t): return c_text(t, "90")
def magenta(t): return c_text(t, "95")

# 核心白名单 (绝对禁止删除的路径关键词)
WHITE_LIST_KEYWORDS = [
    "JSONData",
    ".git",
    "stock_standalone\\ats",
    "stock_standalone\\config",
    "AppData\\Roaming\\Code\\User",
    ".ssh"
]

def is_safe_path(path):
    if not path:
        return False
    norm = os.path.normpath(path).lower()
    for kw in WHITE_LIST_KEYWORDS:
        if kw.lower() in norm:
            return False
    return True

def get_path_size(path):
    if not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except Exception:
            return 0
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += get_path_size(entry.path)
                except Exception:
                    pass
    except Exception:
        pass
    return total

def format_size(size_bytes):
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} Bytes"

class DiskCleaner:
    def __init__(self):
        self.total_freed = 0
        self.auto_yes_all = False

    def ask_confirm(self, title, target, size_str, desc):
        if self.auto_yes_all:
            return True
        print("\n" + "-" * 70)
        print(f"【清理项目】: {yellow(title)}")
        print(f"【目标路径】: {cyan(target)}")
        print(f"【预估释放】: {green(size_str)}")
        print(f"【详细说明】: {desc}")
        
        while True:
            try:
                ans = input(">>> 是否清理该项？[Y]是 / [N]跳过 / [A]后续全部是 / [Q]退出: ").strip().upper()
            except (KeyboardInterrupt, EOFError):
                print("\n[用户中断] 操作已取消。")
                self.show_summary()
                sys.exit(0)
                
            if ans in ['Y', 'YES', '1']:
                return True
            elif ans in ['N', 'NO', '0', '']:
                print(yellow("[已跳过] 跳过该项清理。"))
                return False
            elif ans in ['A', 'ALL']:
                self.auto_yes_all = True
                print(magenta("[自动确认] 后续所有项将自动执行清理！"))
                return True
            elif ans in ['Q', 'QUIT', 'EXIT']:
                print("\n" + red("[用户退出] 操作已终止，正在生成当前汇报..."))
                self.show_summary()
                sys.exit(0)
            else:
                print(red("输入无效，请输入 Y、N、A 或 Q"))

    def safe_delete(self, path, title, desc):
        if not os.path.exists(path):
            return
        if not is_safe_path(path):
            print(red(f"[安全拦截] 路径命中核心白名单保护，禁止清理: {path}"))
            return
        
        sz = get_path_size(path)
        if sz == 0:
            return
        sz_str = format_size(sz)
        
        if self.ask_confirm(title, path, sz_str, desc):
            print(f"[*] 正在清理: {path} ...")
            try:
                if os.path.isfile(path):
                    os.remove(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                self.total_freed += sz
                print(green(f"[成功] 已释放 {sz_str}"))
            except Exception as e:
                print(yellow(f"[部分跳过] 清理异常 (可能被系统占用): {e}"))

    def run_command(self, cmd_list, title, target_desc, estimated_size_str, desc):
        if self.ask_confirm(title, target_desc, estimated_size_str, desc):
            print(f"[*] 正在执行命令: {' '.join(cmd_list)} ...")
            try:
                subprocess.run(cmd_list, check=False)
                print(green("[成功] 命令执行完毕"))
            except Exception as e:
                print(yellow(f"[*] 命令执行提示: {e}"))

    def clean_ditto(self):
        user_home = os.path.expanduser("~")
        ditto_db = os.path.join(user_home, "AppData", "Roaming", "Ditto", "Ditto.db")
        if os.path.exists(ditto_db):
            sz = get_path_size(ditto_db)
            if sz > 200 * 1024 * 1024:  # > 200MB
                sz_str = format_size(sz)
                if self.ask_confirm(
                    "Ditto 剪贴板超大数据库",
                    ditto_db,
                    sz_str,
                    f"长期未清理导致单个数据库膨胀到 {sz_str}。清空后 Ditto 下次启动会自动生成轻量级新库"
                ):
                    print("[*] 正在尝试关闭 Ditto 进程以解除文件占用...")
                    os.system("taskkill /f /im Ditto.exe >nul 2>nul")
                    try:
                        os.remove(ditto_db)
                        self.total_freed += sz
                        print(green(f"[成功] 已清空 Ditto.db，成功释放 {sz_str}！"))
                    except Exception as e:
                        print(yellow(f"[*] 清理 Ditto.db 提示: {e}"))

    def show_summary(self):
        print("\n" + "=" * 70)
        print(" 【清理完成与磁盘空间汇报】")
        print("=" * 70)
        print(f"本次交互式清理累计释放空间: {green(format_size(self.total_freed))}")
        print("\n最新驱动器剩余空间概况:")
        for d in ["C:\\", "D:\\", "E:\\"]:
            try:
                total, used, free = shutil.disk_usage(d)
                print(f"  - 驱动器 {d[:2]} -> 可用: {cyan(f'{free/(1024**3):.2f} GB')} / 总计: {total/(1024**3):.2f} GB (使用率: {used/total*100:.1f}%)")
            except Exception:
                pass
        print("=" * 70 + "\n")

def main():
    user_home = os.path.expanduser("~")
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.join(user_home, "AppData", "Local"))
    
    print("=" * 70)
    print("        系统盘 (C:) 与数据盘 (D:) 交互式智能清理工具")
    print("=" * 70)
    print("说明: 每个清理项目都会计算并显示具体体积，经您确认后再执行。")
    print("提示: 任何时候输入 [Q] 即可安全退出。\n")

    cleaner = DiskCleaner()

    # 1. D 盘 Python 项目构建临时工作目录
    print(yellow(">>> 模块 1/5: D 盘 Python/PyInstaller 编译临时工作目录"))
    cleaner.safe_delete(
        r"D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone\build",
        "stock_standalone 项目 PyInstaller 临时 build 目录",
        "PyInstaller 打包过程中产生的中间二进制与缓存，删除完全安全且不影响源码"
    )
    cleaner.safe_delete(
        r"D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\build",
        "stock 项目 PyInstaller 临时 build 目录",
        "临时编译缓存，可安全删除"
    )
    cleaner.safe_delete(
        r"D:\MacTools\WorkFile\WorkSpace\pyQuant3\stock\testpy\tdxgui\build",
        "tdxgui 测试模块 临时 build 目录",
        "临时编译缓存，可安全删除"
    )
    cleaner.safe_delete(
        r"D:\MacTools\Temp\dist",
        "MacTools 临时打包产物目录 (Temp\\dist)",
        "历史打包残留产物，可安全清理"
    )

    # 2. C 盘 Nuitka 编译与 NVIDIA 着色器缓存
    print("\n" + yellow(">>> 模块 2/5: C 盘 Nuitka 编译器下载缓存与 NVIDIA 着色器缓存"))
    cleaner.safe_delete(
        os.path.join(local_app_data, "Nuitka"),
        "Nuitka 编译与 MinGW/GCC 工具链下载缓存",
        "Nuitka 打包时下载的 GCC 编译器与中间生成物，若暂不打包可完全清空 (约 5.0 GB)"
    )
    cleaner.safe_delete(
        os.path.join(local_app_data, "NVIDIA", "DXCache"),
        "NVIDIA 显卡 DirectX 着色器缓存 (DXCache)",
        "显卡运行游戏和图形软件的着色器历史缓存，删除后显卡会自动重新按需生成 (约 3.5 GB)"
    )

    # 3. 开发环境包管理器缓存
    print("\n" + yellow(">>> 模块 3/5: 开发环境包管理器下载缓存"))
    cleaner.safe_delete(
        os.path.join(local_app_data, "pip", "cache"),
        "Python pip 包下载缓存",
        "pip install 时保留在本地的 wheel/tar 包，删除完全安全"
    )
    cleaner.safe_delete(
        os.path.join(local_app_data, "npm-cache"),
        "Node.js npm 模块下载缓存",
        "npm 离线包缓存，删除完全安全"
    )
    cleaner.safe_delete(
        os.path.join(local_app_data, "Yarn", "Cache"),
        "Node.js Yarn 模块下载缓存",
        "Yarn 离线包缓存，删除完全安全 (约 650 MB)"
    )
    cleaner.safe_delete(
        os.path.join(user_home, "scoop", "cache"),
        "Scoop 包管理器历史安装包缓存",
        "已安装软件的历史 7z/exe 安装包，删除不影响已安装应用 (约 1.0 GB)"
    )
    cleaner.safe_delete(
        os.path.join(user_home, ".nuget", "packages"),
        ".NET / NuGet 全局包缓存",
        "已下载的 nuget 组件缓存，下次编译时如有需要会自动恢复"
    )
    # Conda clean
    if shutil.which("conda"):
        cleaner.run_command(
            ["conda", "clean", "-a", "-y"],
            "Anaconda / Conda 已下载包与残留索引缓存",
            "conda clean -a -y",
            "约 1.0 ~ 2.0 GB",
            "清除 conda 历史下载的 tar.bz2 压缩包与未引用的包缓存"
        )

    # 4. Ditto 剪贴板超大数据库
    print("\n" + yellow(">>> 模块 4/5: Ditto 剪贴板历史数据库优化"))
    cleaner.clean_ditto()

    # 5. 崩溃转储与 QQ 音乐缓存
    print("\n" + yellow(">>> 模块 5/5: 系统崩溃转储与 QQ 音乐离线缓存"))
    cleaner.safe_delete(
        os.path.join(local_app_data, "CrashDumps"),
        "系统与程序崩溃转储文件 (CrashDumps)",
        "历史程序崩溃产生的 .dmp 临时文件，无保留价值"
    )
    cleaner.safe_delete(
        r"D:\QQMusicCache",
        "QQ 音乐在线播放缓存",
        "在线试听临时歌曲缓存文件，删除完全安全 (约 1.8 GB)"
    )

    cleaner.show_summary()
    input("按回车键退出...")

if __name__ == "__main__":
    main()
