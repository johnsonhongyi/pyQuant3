# -*- coding: utf-8 -*-
"""
ATS Launcher Script
Runs the Autonomous Trading System dashboard.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication

# Ensure workspace root is in path (Nuitka / PyInstaller / dev 统一兼容的物理根目录方案)
try:
    from sys_utils import get_app_root
    current_dir = get_app_root()
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from ats.ui.main_window import ATSMainWindow
from sys_utils import ensure_backend_tk_running

def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[ATS Launcher] Failed to ensure backend running: {e}")

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
