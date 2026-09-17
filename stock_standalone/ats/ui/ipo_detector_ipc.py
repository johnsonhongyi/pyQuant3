# -*- coding: utf-8 -*-
"""
ats/ui/ipo_detector_ipc.py
--------------------------
新股次新股超短检测工具跨进程通信中心 (IPC) 与子进程生命周期管理器
- 原子队列：config/ipo_detector_ipc.json，跨进程高可靠无锁/文件锁通信；
- 独立启动：与 --sbc-holdings 相同的隔离规范 (close_fds=True, ATS_MAIN_PID)；
- 一键发送：ATS 主表、股票池、右键菜单向检测工具瞬间发送股票代码。
"""

import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

from sys_utils import get_app_root, is_packaged_env

logger = logging.getLogger("IPODetectorIPC")


def get_ipo_detector_ipc_file() -> str:
    """获取 IPC 通信文件路径"""
    cfg_dir = os.path.join(get_app_root(), "config")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "ipo_detector_ipc.json")


def get_ipo_detector_layout_file() -> str:
    """获取检测工具专用布局与监控池持久化文件路径"""
    cfg_dir = os.path.join(get_app_root(), "config")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "ipo_detector_layout.json")


def _read_ipc_data() -> Dict[str, Any]:
    ipc_file = get_ipo_detector_ipc_file()
    if not os.path.exists(ipc_file):
        return {"queue": [], "heartbeat": 0.0, "detector_pid": 0}
    try:
        with open(ipc_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug(f"读取 IPC 数据异常: {e}")
    return {"queue": [], "heartbeat": 0.0, "detector_pid": 0}


def _write_ipc_data(data: Dict[str, Any]) -> bool:
    ipc_file = get_ipo_detector_ipc_file()
    tmp_file = ipc_file + ".tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if os.path.exists(tmp_file):
            os.replace(tmp_file, ipc_file)
            return True
    except Exception as e:
        logger.debug(f"写入 IPC 数据异常: {e}")
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass
    return False


def find_ipo_detector_window() -> Optional[int]:
    """
    通过 Windows API 枚举查找当前桌面是否存在新股次新超短检测工具窗口 HWND
    严格遵守安全规范，绝不修改进程 WindowStation 或 Desktop，确保 100% 渲染安全。
    """
    if sys.platform != "win32":
        return None
    try:
        import win32gui
        found_hwnd = None

        def _enum_cb(hwnd, _):
            nonlocal found_hwnd
            try:
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if "新股次新股超短检测" in t or "SBC 极限 10日 VWAP" in t:
                        found_hwnd = hwnd
                        return False
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_enum_cb, None)
        return found_hwnd
    except Exception:
        # ctypes fallback (安全无侵入)
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            found_hwnd = None
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _c_cb(hwnd, _):
                nonlocal found_hwnd
                try:
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value
                            if "新股次新股超短检测" in title or "SBC 极限 10日 VWAP" in title:
                                found_hwnd = hwnd
                                return False
                except Exception:
                    pass
                return True

            user32.EnumWindows(WNDENUMPROC(_c_cb), 0)
            return found_hwnd
        except Exception:
            return None


def is_ipo_detector_alive() -> bool:
    """检查独立检测工具进程是否处于活跃存活状态 (多重探针：窗口探测 > 进程存在 > 心跳验证)"""
    # 1. 优先查桌面是否存在该窗口，若存在则 100% 存活
    if sys.platform == "win32":
        hwnd = find_ipo_detector_window()
        if hwnd:
            return True

    # 2. 检查 IPC 文件与底层系统进程
    data = _read_ipc_data()
    hb = float(data.get("heartbeat", 0.0))
    pid = int(data.get("detector_pid", 0))

    if pid > 0:
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h_proc:
                    kernel32.CloseHandle(h_proc)
                    if time.time() - hb < 15.0 or hb == 0.0:
                        return True
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 0)
                if time.time() - hb < 15.0 or hb == 0.0:
                    return True
            except Exception:
                pass

    return False


def build_ipo_detector_command(code: Optional[str] = None) -> List[str]:
    """智能构造调起独立检测工具的命令行 (兼容源码与打包环境)"""
    app_root = get_app_root()
    is_frozen = is_packaged_env()
    is_py = ("python" in os.path.basename(sys.executable).lower())

    run_script = os.path.join(app_root, "run_ipo_detector.py")
    if not is_frozen and is_py and os.path.exists(run_script):
        cmd = [sys.executable, run_script]
        if code:
            cmd.extend(["--code", str(code)])
        return cmd

    # 打包环境
    target_exe = None
    candidate_ats = os.path.join(app_root, "ATS_Terminal.exe")
    if is_frozen and sys.executable.lower().endswith(".exe"):
        target_exe = sys.executable
    elif os.path.exists(candidate_ats):
        target_exe = candidate_ats

    if target_exe and os.path.exists(target_exe):
        cmd = [target_exe, "--ipo-detector"]
        if code:
            cmd.extend(["--code", str(code)])
        return cmd

    if os.path.exists(run_script):
        cmd = [sys.executable, run_script]
        if code:
            cmd.extend(["--code", str(code)])
        return cmd

    return [sys.executable, "-m", "run_ipo_detector"]


def activate_ipo_detector_window(target_hwnd: Optional[int] = None) -> bool:
    """
    【安全置顶激活 (严格对齐 SBCProcessManager.activate_launcher_windows 标准范式)】
    将已有新股次新检测工具窗口唤醒、解除最小化、置顶激活。
    绝不调用任何 SetProcessWindowStation / AttachThreadInput 等破坏渲染管线的危险操作。
    """
    if sys.platform != "win32":
        return False
    try:
        import win32gui
        import win32con
        hwnd = target_hwnd or find_ipo_detector_window()
        if hwnd and win32gui.IsWindow(hwnd):
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass

    # ctypes 纯净回退
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = target_hwnd or find_ipo_detector_window()
        if hwnd and user32.IsWindow(hwnd):
            SW_RESTORE = 9
            SW_SHOW = 5
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    return False


def launch_ipo_detector_process(code: Optional[str] = None) -> Optional[subprocess.Popen]:
    """
    【🚀 独立进程启动】
    以高可靠、句柄隔离 (close_fds=True)、父进程守护模式启动新股次新股超短检测工具
    严格对齐 --sbc-holdings 独立子进程启动规范：
    1. 优先查窗与置顶：若已有窗口或活跃子进程，直接置顶激活前置，绝不重复生成第二个实例；
    2. stdout/stderr 严格重定向到独立的 logs/ipo_detector.log 文件，切断与父进程控制台句柄冲突；
    3. 剥离 _MEIPASS2 防止 PyInstaller 锁死；
    4. 独立进程组 CREATE_NEW_PROCESS_GROUP。
    """
    # 1. 优先激活桌面已有窗口！
    if activate_ipo_detector_window():
        logger.info("[IPC] 新股次新超短检测工具已有窗口，已成功置顶激活，无需重复启动。")
        if code:
            send_stock_to_ipo_detector(code)
        return None

    # 2. 检查进程存活
    if is_ipo_detector_alive():
        logger.info("[IPC] 新股次新超短检测工具进程已在运行中，尝试激活窗口...")
        activate_ipo_detector_window()
        if code:
            send_stock_to_ipo_detector(code)
        return None

    cmd = build_ipo_detector_command(code)
    try:
        env = os.environ.copy()
        # 剥离 PyInstaller 解压目录防止锁死 (对齐 sbc_launcher)
        env.pop('_MEIPASS2', None)
        env["ATS_MAIN_PID"] = str(os.getpid())
        env["ATS_IPO_SUBPROCESS"] = "1"

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        # 独立日志文件重定向，切断与主终端共享控制台 handle 的死锁竞争 (对齐 sbc_launcher)
        app_root = get_app_root()
        log_dir = os.path.join(app_root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "ipo_detector.log")
        log_fh = open(log_file, "a", encoding="utf-8", errors="replace")

        logger.info(f"[IPC] 正在启动新股次新超短检测工具独立子进程: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            cwd=app_root,
            env=env,
            creationflags=creationflags,
            close_fds=True,
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL
        )
        try:
            log_fh.close()
        except Exception:
            pass

        logger.info(f"[IPC] 成功拉起新股次新超短检测工具子进程 (PID={proc.pid}), 日志: {log_file}")
        # 同步更新心跳和 PID
        update_detector_heartbeat(proc.pid)
        return proc
    except Exception as e:
        logger.error(f"[IPC] 拉起检测工具子进程失败: {e}")
        return None


def send_stock_to_ipo_detector(code: str, name: str = "") -> bool:
    """
    【⚡ 一键发送】
    将股票代码追加到检测工具的接收队列中。
    若工具未运行，自动后台静默拉起工具并将代码注入；若已运行，激活窗口！
    """
    clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
    if not clean_code or len(clean_code) != 6:
        return False

    data = _read_ipc_data()
    q = data.get("queue", [])
    if clean_code not in q:
        q.append(clean_code)
        data["queue"] = q
        _write_ipc_data(data)

    # 检查进程是否活跃，未活跃则立即拉起；已活跃则激活前置
    if not is_ipo_detector_alive():
        launch_ipo_detector_process(clean_code)
    else:
        activate_ipo_detector_window()
    return True


def pop_queued_stocks() -> List[str]:
    """检测工具端拉取并清空当前待处理的外部新增股票队列"""
    data = _read_ipc_data()
    q = data.get("queue", [])
    if q:
        data["queue"] = []
        _write_ipc_data(data)
        return q
    return []


def update_detector_heartbeat(pid: int):
    """检测工具更新心跳"""
    data = _read_ipc_data()
    data["heartbeat"] = time.time()
    data["detector_pid"] = pid
    _write_ipc_data(data)


def close_ipo_detector_process(timeout: float = 3.0) -> bool:
    """
    【🛑 统一优雅关闭超短检测工具子进程 (对齐 close_launcher_process)】
    在 ATS 主窗口退出时调用：
    1. 优先通过 Win32 PostMessage 发送 WM_CLOSE 消息让窗口触发 closeEvent，完成数据原子持久化；
    2. 给予充足超时 (3s) 让 PyInstaller bootloader 安全清理 _MEI* 临时目录，杜绝 PYI-10032 警告；
    3. 若超时再执行 terminate 与 kill 回收句柄，杜绝孤儿进程残留。
    """
    data = _read_ipc_data()
    pid = data.get("detector_pid", 0)
    if not pid or pid <= 0:
        return False

    logger.info(f"[IPC] 正在优雅关闭新股次新超短检测工具子进程 (PID={pid}) 并等待持久化...")
    closed_gracefully = False

    # 1. 优先向窗口投递 WM_CLOSE 消息 (对齐 sbc_launcher)
    if sys.platform == "win32":
        try:
            import win32gui
            import win32process
            import win32con

            def _enum_close_cb(hwnd, _):
                try:
                    _, w_pid = win32process.GetWindowThreadProcessId(hwnd)
                    if w_pid == pid and win32gui.IsWindow(hwnd):
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(_enum_close_cb, None)
        except Exception:
            pass

    # 2. 等待进程安全退出
    try:
        import psutil
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            try:
                proc.wait(timeout=timeout)
                closed_gracefully = True
            except psutil.TimeoutExpired:
                logger.warning(f"[IPC] 检测工具子进程 (PID={pid}) 优雅退出等待超时，执行 terminate")
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                    closed_gracefully = True
                except psutil.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        pass
    except Exception:
        # Win32 fallback
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                PROCESS_TERMINATE = 0x0001
                h_proc = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_TERMINATE, False, pid)
                if h_proc:
                    # 等待最多 2 秒
                    res = kernel32.WaitForSingleObject(h_proc, 2000)
                    if res != 0:
                        kernel32.TerminateProcess(h_proc, 0)
                    kernel32.CloseHandle(h_proc)
                    closed_gracefully = True
            except Exception:
                pass

    logger.info(f"[IPC] ✅ 新股次新超短检测工具子进程已安全退出并回收句柄 (PID={pid})")
    data["detector_pid"] = 0
    data["heartbeat"] = 0.0
    _write_ipc_data(data)
    return closed_gracefully



