# -*- coding: utf-8 -*-
"""
ATS Main Executable Entry Point
Initializes the Qt6 Application and launches the ATS Terminal.
"""

import sys
import os

# Ensure project root is in python path (Nuitka / PyInstaller / dev 统一兼容的物理根目录方案)
try:
    from sys_utils import get_app_root
    project_root = get_app_root()
except Exception:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from ats.ui.main_window import ATSMainWindow

def main():
    # Support high DPI scaling on Windows
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    app.setApplicationName("ATS Autonomous Trading Terminal")
    
    window = ATSMainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
