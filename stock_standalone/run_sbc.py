# -*- coding: utf-8 -*-
"""
run_sbc.py
----------
SBC 分时图独立启动器 (便捷入口)
用法:
    python run_sbc.py               # 默认打开 600733 (北汽蓝谷)
    python run_sbc.py 301531        # 打开指定标的 301531
    python run_sbc.py 600733 1m     # 打开 600733 且指定周期为 1m
"""

import sys
import os
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

# 确保工作区根目录在 Python 路径中
try:
    from sys_utils import get_app_root, setup_qt_clean_environment
    current_dir = get_app_root()
    setup_qt_clean_environment()
except Exception:
    current_dir = os.path.dirname(os.path.abspath(__file__))

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyQt6.QtWidgets import QApplication
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
from sys_utils import ensure_backend_tk_running


def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[SBC Launcher] 检查行情服务警告: {e}")

    # 解析命令行参数
    code = sys.argv[1] if len(sys.argv) > 1 else "600733"
    period = sys.argv[2] if len(sys.argv) > 2 else "1m"

    print(f"[SBC Launcher] 正在启动 SBC 实盘分时窗口: 标的代码={code}, 初始周期={period}")

    app = QApplication(sys.argv)
    window = SBCIntradayChartDialog(code=code, initial_period_mode=period)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
