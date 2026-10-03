# -*- coding: utf-8 -*-
"""
ATS Main Executable Entry Point
Initializes the Qt6 Application and launches the ATS Terminal.
"""

import sys
import os
import multiprocessing

# Ensure project root is in python path (Nuitka / PyInstaller / dev 统一兼容的物理根目录方案)
try:
    from sys_utils import get_app_root, setup_qt_clean_environment
    project_root = get_app_root()
    setup_qt_clean_environment()
except Exception:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false;qt.qpa.fonts.debug=false;qt.text.font.warning=false;qt.text.font.debug=false;qt.qpa.fonts=false"

if project_root not in sys.path:
    sys.path.insert(0, project_root)
    try:
        from sys_utils import setup_qt_clean_environment
        setup_qt_clean_environment()
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QTimer
from ats.ui.main_window import ATSMainWindow
from sys_utils import ensure_backend_tk_running
from ats.startup_profiler import StartupProfiler, mark_checkpoint

def main():
    profiler = StartupProfiler.get_instance()
    mark_checkpoint("00. Python Runtime & Environment Setup")

    # 💥 打包自修复：必须在任何 ATS 模块读取 yaml/json 配置之前完成自愈释放。
    # PyInstaller Onefile 模式下，配置文件打包在 _MEIPASS，
    # 自愈引擎负责将其复制到 EXE 所在物理目录的 config/ 子目录下。
    try:
        from sys_utils import ensure_all_configs_released
        ensure_all_configs_released()
    except Exception as _e:
        print(f"[ATS Launcher] ensure_all_configs_released 异常 (非致命): {_e}")

    # Continuously read the collector's SQLite snapshot outside the order path.
    try:
        from ats.strategy.ipo_gate_context_provider import get_default_ipo_gate_context_provider

        provider = get_default_ipo_gate_context_provider(project_root)
        provider.start_auto_refresh()
    except Exception as exc:
        print(f"[IPO Gate] Shared data refresh unavailable: {type(exc).__name__}")

    # 自动探测并拉起后台静默 Tk 进程 (P0)
    try:
        if os.environ.get('ATS_TEST_MODE') != '1':
            ensure_backend_tk_running()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")
    mark_checkpoint("01. Backend TK Process Check & Launch")

    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    if 'provider' in locals():
        app.aboutToQuit.connect(provider.stop_auto_refresh)
    def flush_archives():
        import threading
        from ats.bounded_evaluation_store import evaluation_store
        threading.Thread(target=evaluation_store.flush, name='ATS-ArchiveClose', daemon=False).start()
    app.aboutToQuit.connect(flush_archives)
    app.setApplicationName("ATS Autonomous Trading Terminal")
    try:
        from PyQt6.QtGui import QPalette, QColor
        pal = app.palette()
        pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1a1a24"))
        pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#f1f5f9"))
        app.setPalette(pal)
    except Exception:
        pass
    mark_checkpoint("02. QApplication Bootstrap")
    
    window = ATSMainWindow()
    mark_checkpoint("03. ATSMainWindow Instantiation")
    
    window.show()
    if os.environ.get('ATS_TEST_MODE') == '1':
        QTimer.singleShot(0, window.close)
    mark_checkpoint("04. ATSMainWindow show()")
    
    # 打印启动全链路耗时看板
    profiler.print_summary()
    
    exit_code = app.exec()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
