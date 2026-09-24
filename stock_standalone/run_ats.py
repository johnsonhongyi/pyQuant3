# -*- coding: utf-8 -*-
"""
ATS Launcher Script
Runs the Autonomous Trading System dashboard.
"""

import sys
import os
import multiprocessing
import argparse

if __name__ == "__main__":
    multiprocessing.freeze_support()

# Ensure workspace root is in path (Nuitka / PyInstaller / dev 统一兼容的物理根目录方案)
try:
    from sys_utils import get_app_root
    current_dir = get_app_root()
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Static import keeps the isolated shadow entry point available in the frozen ATS EXE.
import tools.run_shadow_live_test as _shadow_runner

_ipo_flags = ("--ipo-detector", "--subnew-detector", "--ipo", "--subnew")
_sbc_flags = ("--sbc", "--sbc-holdings", "--holdings-sbc", "--holdings")
_shadow_flags = ("--shadow-live",)

if __name__ == "__main__" and any(arg in sys.argv[1:] for arg in _shadow_flags):
    sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg not in _shadow_flags]
    sys.exit(_shadow_runner.main())

# 根入口帮助不应初始化 GUI 或行情后端；指定子模式时由对应启动器处理自己的 -h。
if __name__ == "__main__" and any(arg in sys.argv[1:] for arg in ("-h", "--help")):
    wants_ipo = os.environ.get("ATS_IPO_SUBPROCESS") == "1" or any(arg in sys.argv for arg in _ipo_flags)
    wants_sbc = os.environ.get("ATS_SBC_SUBPROCESS") == "1" or any(arg in sys.argv for arg in _sbc_flags)
    wants_shadow = any(arg in sys.argv for arg in _shadow_flags)
    if not wants_ipo and not wants_sbc and not wants_shadow:
        parser = argparse.ArgumentParser(description="ATS 主程序与独立工具启动器")
        parser.add_argument("--ipo-detector", "--subnew-detector", "--ipo", "--subnew",
                            action="store_true", help="只启动新股次新股检测器")
        parser.add_argument("--sbc-holdings", "--holdings-sbc", "--holdings",
                            action="store_true", help="只启动 SBC 持仓独立看板")
        parser.add_argument("--sbc", metavar="CODE", help="只启动 SBC 指定股票窗口（可接周期参数）")
        parser.add_argument("--shadow-live", action="store_true", help="启动隔离 PAPER 影子运行器；参数转交给运行器")
        parser.print_help()
        sys.exit(0)

import run_sbc
import run_ipo_detector

# 💡 命令行参数与环境变量双重分发：若带有 --sbc / --sbc-holdings 或 ATS_SBC_SUBPROCESS=1，直接作为独立 SBC 子进程运行，彻底阻断进入 ATS 主界面
if __name__ == "__main__":
    is_sbc_subproc = (
        os.environ.get("ATS_SBC_SUBPROCESS") == "1" or
        any(arg in sys.argv for arg in _sbc_flags)
    )
    if is_sbc_subproc:
        try:
            sys.exit(run_sbc.main())
        except KeyboardInterrupt:
            try:
                run_sbc.quit_and_save_all_sbc_windows()
            except Exception:
                pass
            sys.exit(0)
        except SystemExit as se:
            sys.exit(se.code if isinstance(se.code, int) else 0)
        except BaseException as e:
            try:
                run_sbc.quit_and_save_all_sbc_windows()
            except Exception:
                pass
            sys.exit(0)

    # 💡 新股次新股超短检测工具独立子进程分发 (对齐 --sbc-holdings 独立子进程规范)
    is_ipo_subproc = (
        os.environ.get("ATS_IPO_SUBPROCESS") == "1" or
        any(arg in sys.argv for arg in _ipo_flags)
    )
    if is_ipo_subproc:
        try:
            sys.exit(run_ipo_detector.main())
        except KeyboardInterrupt:
            try:
                run_ipo_detector.quit_and_save_detector()
            except Exception:
                pass
            sys.exit(0)
        except SystemExit as se:
            sys.exit(se.code if isinstance(se.code, int) else 0)
        except BaseException:
            try:
                run_ipo_detector.quit_and_save_detector()
            except Exception:
                pass
            sys.exit(0)

from PyQt6.QtWidgets import QApplication

from ats.ui.main_window import ATSMainWindow
from sys_utils import ensure_backend_tk_running

def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")

    # try:
    #     from sys_utils import resolve_stock_name
    #     print(f"[ATS Test Resolve] Starting test resolve for 600000...")
    #     resolved = resolve_stock_name('600000')
    #     print(f"[ATS Test Resolve] Result for 600000 -> {resolved}")
    # except Exception as e:
    #     print(f"[ATS Test Resolve] Exception occurred: {e}")

    app = QApplication(sys.argv)
    window = ATSMainWindow()
    # For automated headless testing/validation, we can show then immediately close or verify window title.
    try:
        print(f"[ATS Launcher] Successfully initialized: {window.windowTitle()}")
    except UnicodeEncodeError:
        # Fallback to ascii safe string
        safe_title = window.windowTitle().encode('ascii', errors='ignore').decode('ascii')
        print(f"[ATS Launcher] Successfully initialized: {safe_title}")
    
    # If running in a test/validation environment, close after showing briefly to allow events to process
    if os.environ.get("ATS_TEST_MODE") == "1":
        window.show()
        QApplication.processEvents()
        window.close()
        return 0
        
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
