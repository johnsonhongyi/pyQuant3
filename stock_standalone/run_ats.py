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

def main():
    app = QApplication(sys.argv)
    window = ATSMainWindow()
    # For automated headless testing/validation, we can show then immediately close or verify window title.
    print(f"[ATS Launcher] Successfully initialized: {window.windowTitle()}")
    
    # If running in a test/validation environment, close immediately to prevent blocking
    if os.environ.get("ATS_TEST_MODE") == "1":
        window.close()
        return 0
        
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
