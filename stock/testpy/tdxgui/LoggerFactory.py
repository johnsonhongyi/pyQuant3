# -*- coding: UTF-8 -*-
'''
Created on 2015-3-11
@author: Casey
'''
import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import multiprocessing
import os
import atexit

# _GLOBAL_LOGGER = None
# _GLOBAL_LOG_NAME = None
# _GLOBAL_QUEUE = None
# _GLOBAL_LISTENER = None

import sys,os
# sys.path.append("..")
# from JohnsonUtil.LoggerFactoryMultiprocess import MultiprocessHandler
import configparser
# from config.loader import GlobalConfig

import ctypes
import shutil

# --- Win32 API 用于获取 EXE 原始路径 (仅限 Windows) ---
def _get_win32_exe_path():
    """
    使用 Win32 API 获取当前进程的主模块路径。
    这在 Nuitka/PyInstaller 的 Onefile 模式下能可靠地返回原始 EXE 路径。
    """
    # 假设是 32767 字符的路径长度是足够的
    MAX_PATH_LENGTH = 32767 
    buffer = ctypes.create_unicode_buffer(MAX_PATH_LENGTH)
    
    # 调用 GetModuleFileNameW(HMODULE hModule, LPWSTR lpFilename, DWORD nSize)
    # 传递 NULL 作为 hModule 获取当前进程的可执行文件路径
    ctypes.windll.kernel32.GetModuleFileNameW(
        None, buffer, MAX_PATH_LENGTH
    )
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
            # print(f"[DEBUG] Path Mode: Python Script (__file__). Path: {path}")
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
                 # print(f"[DEBUG] Path Mode: WinAPI (Override). Path: {real_path}")
                 return real_path
            
            # 如果 Win32 API 结果与 sys.executable 目录一致，且我们处于打包状态
            if not is_interpreter:
                 # print(f"[DEBUG] Path Mode: WinAPI (Standalone). Path: {real_path}")
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


# logger.info(f'_get_win32_exe_path() : {_get_win32_exe_path()}')
#print(f'_get_win32_exe_path() : {_get_win32_exe_path()}')
#print(f'get_base_path() : {get_base_path()}')

def get_resource_file(rel_path, out_name=None,BASE_DIR=None):
    """
    从 PyInstaller 内置资源释放文件到 EXE 同目录

    rel_path:   打包资源的相对路径
    out_name:   释放目标文件名
    """
    if BASE_DIR is None:
        BASE_DIR = get_base_path()
        # log.info(f"BASE_DIR配置文件: {BASE_DIR}")

    if out_name is None:
        out_name = os.path.basename(rel_path)

    # BASE_DIR = os.path.dirname(
    #     sys.executable if getattr(sys, "frozen", False)
    #     else os.path.abspath(__file__)    # ✅ 修复点
    # )

    target_path = os.path.join(BASE_DIR, out_name)
    print(f"target_path配置文件: {target_path}")

    # 已存在 → 直接返回
    if os.path.exists(target_path):
        return target_path

    # 从 MEIPASS 复制
    base = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.abspath(".")
    src = os.path.join(base, rel_path)

    if not os.path.exists(src):
        print(f"内置资源缺失: {src}")
        return None

    try:
        shutil.copy(src, target_path)
        print(f"释放配置文件: {target_path}")
        return target_path
    except Exception as e:
        print(f"释放资源失败: {e}")
        return None


# --------------------------------------
# STOCK_CODE_PATH 专用逻辑
# --------------------------------------
BASE_DIR = get_base_path()

def get_conf_path(fname):
    """
    获取并验证 stock_codes.conf

    逻辑：
      1. 优先使用 BASE_DIR/stock_codes.conf
      2. 不存在 → 从 JSONData/stock_codes.conf 释放
      3. 校验文件
    """
    # default_path = os.path.join(BASE_DIR, "stock_codes.conf")
    default_path = os.path.join(BASE_DIR, fname)

    # --- 1. 直接存在 ---
    if os.path.exists(default_path):
        if os.path.getsize(default_path) > 0:
            # print(f"使用本地配置: {default_path}")
            return default_path
        else:
            print("配置文件存在但为空，将尝试重新释放")

    # --- 2. 释放默认资源 ---
    cfg_file = get_resource_file(
        rel_path=f"JohnsonUtil/{fname}",
        out_name=fname,
        BASE_DIR=BASE_DIR
    )

    # --- 3. 校验释放结果 ---
    if not cfg_file:
        print(f"获取 {fname} 失败（释放阶段）")
        return None

    if not os.path.exists(cfg_file):
        print(f"释放后文件仍不存在: {cfg_file}")
        return None

    if os.path.getsize(cfg_file) == 0:
        print(f"配置文件为空: {cfg_file}")
        return None

    print(f"使用内置释放配置: {cfg_file}")
    return cfg_file

class GlobalConfig:
    def __init__(self, cfg_file=None):
        if not cfg_file:
            # 兜底：优先使用程序 EXE 所在的真实目录
            cfg_file = os.path.join(get_base_path(), "global.ini")

        self.cfg_file = cfg_file
        # 禁用 % 插值，防止路径中的 % 引起解析错误
        self.cfg = configparser.ConfigParser(interpolation=None)

        # 定义默认配置结构
        default_config = {
            "general": {
                "initGlobalValue": "1"
            },
            "terminal": {
                "clean_terminal": "cls, clear"
            },
            "expressions": {
                # 预留
            },
            "path": {
                "win10_ramdisk_triton": r"G:",
                "win10_ramdisk_root": r"R:",
                "mac_ramdisk_root": r"/Volumes/RamDisk"
            }
        }

        # 1. 尝试读取现有文件
        if os.path.exists(self.cfg_file):
            try:
                # 尝试多种编码
                for enc in ['utf-8', 'gbk', 'utf-8-sig']:
                    try:
                        self.cfg.read(self.cfg_file, encoding=enc)
                        if self.cfg.sections(): break
                    except: continue
            except Exception as e:
                print(f"[WARN] 读取配置文件 {self.cfg_file} 失败: {e}")

        # 2. 自动补全缺失的 Section 和 Option
        modified = False
        for section, options in default_config.items():
            if not self.cfg.has_section(section):
                self.cfg.add_section(section)
                modified = True
            for option, value in options.items():
                if not self.cfg.has_option(section, option):
                    self.cfg.set(section, option, str(value))
                    modified = True

        # 3. 如果文件不存在或有更新，则物理保存
        if modified or not os.path.exists(self.cfg_file):
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.cfg_file)), exist_ok=True)
                with open(self.cfg_file, "w", encoding="utf-8") as f:
                    self.cfg.write(f)
                print(f"✅ 配置文件已创建/自动修复: {self.cfg_file}")
            except Exception as e:
                print(f"❌ 无法保存配置文件: {e}")

        # 4. 加载属性
        try:
            self.init_value = self.cfg.getint("general", "initGlobalValue", fallback=1)
            self.clean_terminal = self._split(self.cfg.get("terminal", "clean_terminal", fallback=""))
            self.expressions = dict(self.cfg.items("expressions"))
            self.paths = dict(self.cfg.items("path"))
        except Exception as e:
            print(f"💣 解析配置属性时发生严重错误: {e}")
            # 极简兜底
            self.init_value = 1
            self.clean_terminal = []
            self.expressions = {}
            self.paths = default_config["path"]

    def _split(self, s):
        return [x.strip() for x in s.split(",") if x.strip()]

    def get_expr(self, name):
        return self.expressions.get(name)

    def get_path(self, key):
        return self.paths.get(key)

    def __repr__(self):
        return f"<GlobalConfig {self.cfg_file}>"


conf_ini= get_conf_path('global.ini')
if not conf_ini:
    print("[INFO] 未找到主目录 global.ini，将使用默认配置并尝试创建。")

CFG = GlobalConfig(conf_ini)

# --- 默认值与配置加载 ---
win10_ramdisk_triton = CFG.get_path("win10_ramdisk_triton") or r'G:'
win10_ramdisk_root = CFG.get_path("win10_ramdisk_root") or r'R:'
mac_ramdisk_root = CFG.get_path("mac_ramdisk_root") or r'/Volumes/RamDisk' 

path_sep = os.path.sep
ramdisk_rootList = [win10_ramdisk_triton,win10_ramdisk_root, mac_ramdisk_root]

def get_log_file(log_n='stock.log'):
    basedir = None
    for root in ramdisk_rootList:
        basedir = root.replace('/', path_sep).replace('\\', path_sep)
        if os.path.exists(basedir):
            break
    if basedir is not None and os.path.exists(basedir):
        path = basedir + os.path.sep
        # print basedir,path
    else:
        # path = os.path.split(os.path.abspath(sys.argv[0]))[0]
        # alist = path.split('stock')
        # if len(alist) > 0:
        #     path = alist[0]
        #     # os_sep=get_os_path_sep()
        #     path = path + 'stock' + os.path.sep
        # else:
        #     print("error")
        #     raise TypeError('log path error.')
        # path = get_base_path()
        path = ''
    path = path + log_n
    return path

'''
传入名称
'''
#global log_path
#print get_run_path()
# log_path = get_run_path() + 'stock.log'
#print log_path
CRITICAL = 50
FATAL = CRITICAL
ERROR = 40
WARNING = 30
WARN = WARNING
INFO = 20
DEBUG = 10
NOTSET = 0


# http://blog.sina.com.cn/s/blog_411fed0c0100wkvj.html


def testlog():
    #logging.basicConfig(filename="test.log",level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # create file handler which logs even debug messages
    fh = logging.FileHandler('test.log', encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    # create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

import logging
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
import multiprocessing
import os
import atexit
from colorama import Fore, Back, Style, init as colorama_init

colorama_init(autoreset=True)

class ColorFormatter(logging.Formatter):
    """仅给控制台日志加颜色，不影响文件日志"""

    def format(self, record):
        msg = super().format(record)

        if record.levelno >= logging.CRITICAL:
            return Back.RED + Fore.WHITE + Style.BRIGHT + msg
        elif record.levelno >= logging.ERROR:
            # banner = "█" * 70
            banner = "-" * 70
            # return Fore.RED + Style.BRIGHT + f"\n{banner}\n{msg}\n{banner}"
            # return Fore.RED + Style.BRIGHT + f"{banner}\n{msg}\n{banner}"
            return Fore.RED + Style.BRIGHT + f"{banner}\n{msg}"
        elif record.levelno >= logging.WARNING:
            return Fore.YELLOW + msg
        else:
            return msg

# ---------------- 全局变量 ----------------
_GLOBAL_LOGGER = None
_GLOBAL_QUEUE = None
_GLOBAL_LISTENER = None
_GLOBAL_LOG_NAME = None
_MAIN_PID = os.getpid()  # 父进程 PID，用于防止子进程重复启动 Listener

# ---------------- 辅助函数 ----------------
def stopLogger():
    """停止 QueueListener，在程序退出时调用"""
    global _GLOBAL_LISTENER
    if _GLOBAL_LISTENER:
        try:
            # ⭐ [FIX] 优雅停止，忽略退出时的 BrokenPipe/EOFError
            _GLOBAL_LISTENER.stop()
        except Exception:
            pass
        _GLOBAL_LISTENER = None


class RobustQueueListener(QueueListener):
    """
    ⭐ [FIX] 增强型 QueueListener
    在 Windows 多进程环境下，当主进程或 Pipe 关闭时，默认的 _monitor 会抛出 BrokenPipeError 或 EOFError。
    该类捕获并屏蔽这些异常，确保退出时不报红。
    """
    def _monitor(self):
        try:
            super()._monitor()
        except (EOFError, BrokenPipeError, ConnectionResetError):
            pass

import queue

class DropQueueHandler(QueueHandler):
    """
    丢弃式日志处理器 (P0-4)
    当 Queue 满载时，直接丢弃新日志，防止阻塞业务线程。
    """
    def enqueue(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            pass  # 💣 满载即丢弃


def _ensure_listener_started(log_f, show_detail=True):
    global _GLOBAL_QUEUE, _GLOBAL_LISTENER

    # ⭐ [STABILITY] 在 Windows 混合 GUI 环境下，multiprocessing.Queue 的 feeder 线程会引发 GIL 崩溃。
    # 我们改为每个进程使用各自独立的 queue.Queue（线程安全且无后台 feeder 线程）。
    if _GLOBAL_QUEUE is None:
        # ⭐ [PERF] 限制队列长度为 2000，配合 DropQueueHandler 实现丢弃策略，防止 IO 阻塞业务
        _GLOBAL_QUEUE = queue.Queue(2000)


        # ================= Console handler（彩色） =================
        ch = logging.StreamHandler()

        fmt = (
            "[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s"
            if show_detail else
            "(%(funcName)s:%(lineno)s): %(message)s"
        )

        ch_formatter = ColorFormatter(fmt, datefmt="%m-%d %H:%M:%S")
        ch.setFormatter(ch_formatter)

        # ================= File handler（无颜色） =================
        import shutil
        os.makedirs(os.path.dirname(os.path.abspath(log_f)), exist_ok=True)

        fh = RotatingFileHandler(
            log_f,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            delay=True
        )

        def win_safe_rotator(src, dst):
            shutil.copyfile(src, dst)
            with open(src, "w", encoding="utf-8"):
                pass

        fh.rotator = win_safe_rotator

        def underscore_namer(name):
            if name.endswith(".log"):
                return name
            base, idx = name.rsplit(".log.", 1)
            return f"{base}_{idx}.log"

        fh.namer = underscore_namer

        fh_formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s"
            if show_detail else
            "(%(funcName)s:%(lineno)s): %(message)s",
            datefmt="%m-%d %H:%M:%S"
        )
        fh.setFormatter(fh_formatter)

        # ================= 启动监听器 =================
        _GLOBAL_LISTENER = RobustQueueListener(_GLOBAL_QUEUE, ch, fh)
        _GLOBAL_LISTENER.start()

        atexit.register(stopLogger)


# def _ensure_listener_started_nocolor(log_f, show_detail=True):
#     global _GLOBAL_QUEUE, _GLOBAL_LISTENER

#     if _GLOBAL_QUEUE is None and os.getpid() == _MAIN_PID:
#         _GLOBAL_QUEUE = multiprocessing.Queue(-1)

#         # Console handler
#         ch = logging.StreamHandler()
#         ch_formatter = logging.Formatter(
#             "[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s"
#             if show_detail else
#             "(%(funcName)s:%(lineno)s): %(message)s",
#             datefmt="%m-%d %H:%M:%S"
#         )
#         ch.setFormatter(ch_formatter)

#         # File handler
#         import shutil
#         os.makedirs(os.path.dirname(os.path.abspath(log_f)), exist_ok=True)
#         fh = RotatingFileHandler(
#             log_f,
#             maxBytes=5*1024*1024,
#             backupCount=3,
#             encoding="utf-8",
#             delay=True      # ✅ 必需
#         )

#         def win_safe_rotator(src, dst):
#             shutil.copyfile(src, dst)
#             with open(src, "w", encoding="utf-8"):
#                 pass

#         fh.rotator = win_safe_rotator

#         # ---------- Custom namer: instock_tk_1.log ----------
#         def underscore_namer(name):
#             """
#             logging 默认给的是:
#               instock_tk.log.1
#             这里改成:
#               instock_tk_1.log
#             """
#             if name.endswith(".log"):
#                 return name

#             base, idx = name.rsplit(".log.", 1)
#             return f"{base}_{idx}.log"

#         fh.namer = underscore_namer
        
#         fh_formatter = logging.Formatter(
#             "[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s"
#             if show_detail else
#             "(%(funcName)s:%(lineno)s): %(message)s",
#             datefmt="%m-%d %H:%M:%S"
#         )
#         fh.setFormatter(fh_formatter)

#         _GLOBAL_LISTENER = RobustQueueListener(_GLOBAL_QUEUE, ch, fh)
#         _GLOBAL_LISTENER.start()

#         atexit.register(stopLogger)

# _GLOBAL_LOGGER_PRINTED = False  # 全局标志
# 全局保存上一次 log_f
_GLOBAL_LAST_LOG_F = None

def getLogger(name=None, logpath='instock_tk.log', show_detail=True,level=logging.ERROR):
    """
    获取全局 logger，支持多进程/多线程
    """
    global _GLOBAL_LOGGER, _GLOBAL_LOG_NAME, _GLOBAL_LAST_LOG_F

    # 已初始化，直接返回
    if _GLOBAL_LOGGER is not None:
        return _GLOBAL_LOGGER

    # 设置全局 logger 名称
    if name:
        _GLOBAL_LOG_NAME = name
    elif not _GLOBAL_LOG_NAME:
        _GLOBAL_LOG_NAME = "instock_TK.log"

    # 确定 log 文件路径
    log_f = logpath if logpath else get_log_file(log_n=_GLOBAL_LOG_NAME)
    # log_f = get_log_file(logpath) if logpath else get_log_file(log_n=_GLOBAL_LOG_NAME)

    # print(f'log_f: {log_f}')
    # 只在 log_f 变化时打印
    # if _GLOBAL_LAST_LOG_F != log_f:
    #     print(f'log_f: {log_f}')
    #     _GLOBAL_LAST_LOG_F = log_f

    # 父进程初始化 QueueListener
    _ensure_listener_started(log_f, show_detail=show_detail)

    # 创建 logger
    logger = logging.getLogger(_GLOBAL_LOG_NAME)
    logger.setLevel(level)
    logger.propagate = False

    # # 添加 QueueHandler
    # logger.handlers = [h for h in logger.handlers if not isinstance(h, QueueHandler)]
    # logger.addHandler(QueueHandler(_GLOBAL_QUEUE))

    try:
        logger.handlers = [h for h in logger.handlers if not isinstance(h, (QueueHandler, DropQueueHandler))]
        logger.addHandler(DropQueueHandler(_GLOBAL_QUEUE))

    except Exception as e:
        print(f"Failed to add QueueHandler: {e}")

    # 保存单例
    _GLOBAL_LOGGER = logger
    return logger


# ---------------- 全局单例 ----------------
log = getLogger()

def set_log_file(console, level_s='DEBUG'):
    console = logging.StreamHandler()
    console.setLevel(eval('logging.%s' % level_s))
    formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)


if __name__ == '__main__':
    getLogger("www").debug("www")
    # log=JohnsonLoger("www").setLevel(DEBUG)
#   pass