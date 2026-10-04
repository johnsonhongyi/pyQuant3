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

_ipo_flags = ("--ipo-detector", "--subnew-detector", "--ipo", "--subnew")
_sbc_flags = ("--sbc", "--sbc-hold", "--hold-sbc", "--hold")
_shadow_flags = ("--shadow-live",)
_learning_flags = ("--ipo-learning", "--ipo-console", "--learning-console", "--ipo-learning-console")

if __name__ == "__main__" and any(arg in sys.argv[1:] for arg in _learning_flags):
    import tools.run_ipo_learning_console as _learning_runner
    sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg not in _learning_flags]
    sys.exit(_learning_runner.main())

if __name__ == "__main__" and any(arg in sys.argv[1:] for arg in _shadow_flags):
    import tools.run_shadow_live_test as _shadow_runner
    sys.argv = [sys.argv[0]] + [arg for arg in sys.argv[1:] if arg not in _shadow_flags]
    sys.exit(_shadow_runner.main())

# 根入口帮助不应初始化 GUI 或行情后端；指定子模式时由对应启动器处理自己的 -h。
if __name__ == "__main__" and any(arg in sys.argv[1:] for arg in ("-h", "--help")):
    wants_ipo = os.environ.get("ATS_IPO_SUBPROCESS") == "1" or any(arg in sys.argv for arg in _ipo_flags)
    wants_sbc = os.environ.get("ATS_SBC_SUBPROCESS") == "1" or any(arg in sys.argv for arg in _sbc_flags)
    wants_shadow = any(arg in sys.argv for arg in _shadow_flags)
    wants_learning = any(arg in sys.argv for arg in _learning_flags)
    if not wants_ipo and not wants_sbc and not wants_shadow and not wants_learning:
        parser = argparse.ArgumentParser(description="ATS 主程序与独立工具启动器")
        parser.add_argument("--ipo-detector", "--subnew-detector", "--ipo", "--subnew",
                            action="store_true", help="只启动新股次新股检测器")
        parser.add_argument("--ipo-learning", "--ipo-console", "--learning-console",
                            action="store_true", help="只启动 IPO 情绪感知与自学习监控控制台")
        parser.add_argument("--sbc-hold", "--hold-sbc", "--hold",
                            action="store_true", help="只启动 SBC 持仓独立看板")
        parser.add_argument("--sbc", metavar="CODE", help="只启动 SBC 指定股票窗口（可接周期参数）")
        parser.add_argument("--shadow-live", action="store_true", help="启动隔离 PAPER 影子运行器；参数转交给运行器")
        parser.print_help()
        sys.exit(0)

# 💡 命令行参数与环境变量双重分发：若带有 --sbc / --sbc-hold 或 ATS_SBC_SUBPROCESS=1，直接作为独立 SBC 子进程运行，彻底阻断进入 ATS 主界面
if __name__ == "__main__":
    is_sbc_subproc = (
        os.environ.get("ATS_SBC_SUBPROCESS") == "1" or
        any(arg in sys.argv for arg in _sbc_flags)
    )
    if is_sbc_subproc:
        import run_sbc
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

    # 💡 新股次新股超短检测工具独立子进程分发 (对齐 --sbc-hold 独立子进程规范)
    is_ipo_subproc = (
        os.environ.get("ATS_IPO_SUBPROCESS") == "1" or
        any(arg in sys.argv for arg in _ipo_flags)
    )
    if is_ipo_subproc:
        import run_ipo_detector
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
    # 💥 1. 打包自修复：在任何 ATS 模块读取配置之前，抢占式完成所有注册核心配置文件的自愈释放。
    # PyInstaller Onefile 模式下，内置资源打包在临时解压目录 _MEIPASS，
    # 自愈引擎负责将其无损释放至物理运行目录下的对应路径（若已存在且有效则绝不覆盖）。
    try:
        from sys_utils import ensure_all_configs_released
        ensure_all_configs_released()
    except Exception as _e:
        print(f"[ATS Launcher] 核心配置自愈释放异常 (非致命): {_e}")

    try:
        from ats.bounded_evaluation_store import evaluation_store, recovery_journal_path
        restored = evaluation_store.restore_recovery(recovery_journal_path(current_dir))
        if restored:
            print(f"[ATS] 已恢复 {restored} 项上次退出时待归档数据")
    except Exception as exc:
        print(f"[ATS] 待归档数据恢复失败: {exc}")

    # 🚀 3. 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        import threading
        def ensure_backend():
            try:
                ensure_backend_tk_running()
            except Exception as err:
                print(f"[ATS] Backend startup failed: {err}")
        if os.environ.get('ATS_TEST_MODE') != '1':
            threading.Thread(target=ensure_backend, daemon=True, name="ATS-BackendStart").start()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")

    # try:
    #     from sys_utils import resolve_stock_name
    #     print(f"[ATS Test Resolve] Starting test resolve for 600000...")
    #     resolved = resolve_stock_name('600000')
    #     print(f"[ATS Test Resolve] Result for 600000 -> {resolved}")
    # except Exception as e:
    #     print(f"[ATS Test Resolve] Exception occurred: {e}")

    if os.name == "nt" and ("__compiled__" in globals() or hasattr(sys, "nuitka_version")):
        from ats.ui.windows_taskbar_group import group_console_and_windows
        group_console_and_windows()

    app = QApplication(sys.argv)
    window = ATSMainWindow()
    from ats.qt_interrupt import install_qt_keyboard_interrupt_handler
    keyboard_interrupt_guard = install_qt_keyboard_interrupt_handler(app, window)
    def flush_archives():
        if getattr(window, '_exit_cleanup_complete', False):
            return
        import threading
        from ats.bounded_evaluation_store import evaluation_store
        threading.Thread(target=evaluation_store.flush, name='ATS-ArchiveClose', daemon=False).start()
    app.aboutToQuit.connect(flush_archives)
    if window._ipo_learning_console_enabled:
        try:
            from ats.strategy.ipo_gate_context_provider import get_default_ipo_gate_context_provider
            provider = get_default_ipo_gate_context_provider(current_dir)
            provider.start_auto_refresh()
            app.aboutToQuit.connect(provider.stop_auto_refresh)
        except Exception as exc:
            print(f"[IPO Gate] Shared data refresh unavailable: {type(exc).__name__}")
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
        health = window._next_day_watch_process.request('health', timeout=30.0)
        window.close()
        import time
        close_deadline = time.monotonic() + 35.0
        while window.isVisible() and time.monotonic() < close_deadline:
            QApplication.processEvents()
            time.sleep(.01)
        if window.isVisible():
            raise RuntimeError('ATS packaged shutdown did not drain')
        if not health.get('pid') or health.get('error'):
            raise RuntimeError('Next-day worker failed its packaged startup check')
        keyboard_interrupt_guard.restore()
        return 0
        
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
