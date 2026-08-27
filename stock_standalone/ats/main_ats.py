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
from PyQt6.QtCore import Qt
from ats.ui.main_window import ATSMainWindow
from sys_utils import ensure_backend_tk_running
from ats.startup_profiler import StartupProfiler, mark_checkpoint

def main():
    profiler = StartupProfiler.get_instance()
    mark_checkpoint("00. Python Runtime & Environment Setup")

    # 自动探测并拉起后台静默 Tk 进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")
    mark_checkpoint("01. Backend TK Process Check & Launch")

    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("ATS Autonomous Trading Terminal")
    mark_checkpoint("02. QApplication Bootstrap")
    
    window = ATSMainWindow()
    mark_checkpoint("03. ATSMainWindow Instantiation")
    
    window.show()
    mark_checkpoint("04. ATSMainWindow show()")
    
    # 打印启动全链路耗时看板
    profiler.print_summary()
    
    exit_code = app.exec()
    os._exit(exit_code)

if __name__ == "__main__":
    main()
