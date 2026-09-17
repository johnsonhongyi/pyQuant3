# -*- coding: utf-8 -*-
"""
run_ipo_detector.py
-------------------
新股次新股超短检测工具独立启动器 (SBC 极限 10日 VWAP 预判与异动引擎)
- 独立进程运行：与 ATS 主系统彻底解耦，不拖累 ATS 主界面刷新与交易；
- 独立持久化：config/ipo_detector_layout.json 集中保存监控池与窗口位置；
- 父进程孤儿守护：检测 ATS_MAIN_PID，父进程退出后自动持久化并安全退出。
"""

import sys
import os
import time
import signal
import atexit
import multiprocessing
from typing import Optional

if __name__ == "__main__":
    multiprocessing.freeze_support()

# 确保工作区根目录在 Python 路径中
try:
    from sys_utils import get_app_root, setup_qt_clean_environment
    current_dir = get_app_root()
    setup_qt_clean_environment()
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ats.ui.ipo_subnew_detector_dialog import IPOSubnewDetectorDialog
from sys_utils import ensure_backend_tk_running


def main():
    # 解析命令行参数
    initial_code = None
    args = sys.argv[1:]
    idx = 0
    while idx < len(args):
        arg = args[idx].strip()
        if arg in ("--code", "-c") and idx + 1 < len(args):
            initial_code = args[idx + 1].strip()
            idx += 1
        elif arg.startswith("--code="):
            initial_code = arg.split("=")[1].strip()
        elif not arg.startswith("-") and len(arg) == 6 and arg.isdigit():
            initial_code = arg
        idx += 1

    # 自动检查并后台静默拉起主 Tk 行情进程
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[IPO Detector] 检查行情服务警告: {e}")

    app = QApplication.instance() or QApplication(sys.argv)

    window = IPOSubnewDetectorDialog(initial_code=initial_code)
    window.show()

    # 退出集中持久化双重保险
    def _on_exit():
        try:
            window.save_persisted_state()
        except Exception:
            pass

    app.aboutToQuit.connect(_on_exit)
    atexit.register(_on_exit)

    # 孤儿进程自动守护 (P0)：若通过 ATS 调起，检测父进程 PID 是否存活
    parent_pid_str = os.environ.get("ATS_MAIN_PID")
    _parent_pid = int(parent_pid_str) if (parent_pid_str and parent_pid_str.isdigit()) else None

    def _on_orphan_check():
        if _parent_pid:
            try:
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    SYNCHRONIZE = 0x00100000
                    h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, _parent_pid)
                    if h_proc:
                        kernel32.CloseHandle(h_proc)
                    else:
                        print(f"\n[IPO Detector] 探针检测到 ATS 父进程 (PID={_parent_pid}) 已关闭，自动保存并退出...")
                        window.save_persisted_state()
                        app_inst = QApplication.instance()
                        if app_inst:
                            app_inst.quit()
                else:
                    os.kill(_parent_pid, 0)
            except Exception:
                print(f"\n[IPO Detector] ATS 父进程已终止，自动安全保存并退出...")
                window.save_persisted_state()
                app_inst = QApplication.instance()
                if app_inst:
                    app_inst.quit()

    _keep_alive_timer = QTimer()
    _keep_alive_timer.timeout.connect(_on_orphan_check)
    _keep_alive_timer.start(500)

    exit_code = 0
    try:
        exit_code = app.exec()
    except KeyboardInterrupt:
        print("\n[IPO Detector] 捕获键盘中断，已安全退出。")
        _on_exit()
        exit_code = 0
    except (SystemExit, BaseException) as e:
        _on_exit()
        exit_code = e.code if isinstance(e, SystemExit) and isinstance(e.code, int) else 0

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
