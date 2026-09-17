# -*- coding: utf-8 -*-
"""
ATS Launcher Script
Runs the Autonomous Trading System dashboard.
"""

import sys
import os
import multiprocessing

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

import run_sbc
import run_ipo_detector

# 💡 命令行参数与环境变量双重分发：若带有 --sbc / --sbc-holdings 或 ATS_SBC_SUBPROCESS=1，直接作为独立 SBC 子进程运行，彻底阻断进入 ATS 主界面
if __name__ == "__main__":
    is_sbc_subproc = (
        os.environ.get("ATS_SBC_SUBPROCESS") == "1" or
        any(arg in sys.argv for arg in ("--sbc", "--sbc-holdings", "--holdings-sbc", "--holdings"))
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
        any(arg in sys.argv for arg in ("--ipo-detector", "--subnew-detector", "--ipo", "--subnew"))
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
