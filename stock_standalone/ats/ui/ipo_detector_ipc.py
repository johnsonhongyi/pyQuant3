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


def is_ipo_detector_alive() -> bool:
    """检查独立检测工具进程是否处于活跃存活状态"""
    data = _read_ipc_data()
    hb = float(data.get("heartbeat", 0.0))
    pid = int(data.get("detector_pid", 0))
    if time.time() - hb < 4.0 and pid > 0:
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h_proc:
                    kernel32.CloseHandle(h_proc)
                    return True
                return False
            except Exception:
                return True
        else:
            try:
                os.kill(pid, 0)
                return True
            except Exception:
                return False
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


def launch_ipo_detector_process(code: Optional[str] = None) -> Optional[subprocess.Popen]:
    """
    【🚀 独立进程启动】
    以高可靠、句柄隔离 (close_fds=True)、父进程守护模式启动新股次新股超短检测工具
    """
    cmd = build_ipo_detector_command(code)
    try:
        env = os.environ.copy()
        # 剥离 PyInstaller 解压目录防止锁死
        env.pop('_MEIPASS2', None)
        env["ATS_MAIN_PID"] = str(os.getpid())
        env["ATS_IPO_SUBPROCESS"] = "1"

        creationflags = 0
        if sys.platform == "win32":
            # 独立进程组
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            cmd,
            cwd=get_app_root(),
            env=env,
            creationflags=creationflags,
            close_fds=True,
            stdout=None,
            stderr=None,
            stdin=None
        )
        logger.info(f"[IPC] 成功拉起新股次新超短检测工具子进程 (PID={proc.pid}), 命令: {' '.join(cmd)}")
        return proc
    except Exception as e:
        logger.error(f"[IPC] 拉起检测工具子进程失败: {e}")
        return None


def send_stock_to_ipo_detector(code: str, name: str = "") -> bool:
    """
    【⚡ 一键发送】
    将股票代码追加到检测工具的接收队列中。
    若工具未运行，自动后台静默拉起工具并将代码注入！
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

    # 检查进程是否活跃，未活跃则立即拉起
    if not is_ipo_detector_alive():
        launch_ipo_detector_process(clean_code)
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
