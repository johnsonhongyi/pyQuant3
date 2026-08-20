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

def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")

    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("ATS Autonomous Trading Terminal")
    
    window = ATSMainWindow()
    window.show()
    
    exit_code = app.exec()
    os._exit(exit_code)

if __name__ == "__main__":
    main()
