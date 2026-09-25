# -*- coding: utf-8 -*-
"""Independent entry point for Next Day Watch Center UI.

Usage:
    python run_next_day_watch.py
"""
import sys
import os

# Ensure current workspace is on sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from PyQt6.QtWidgets import QApplication
from ats.ui.next_day_watch_dialog import NextDayAnomalyWatchDialog


def main():
    app = QApplication.instance()
    is_new = False
    if app is None:
        app = QApplication(sys.argv)
        is_new = True

    dialog = NextDayAnomalyWatchDialog.get_instance()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

    if is_new:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
