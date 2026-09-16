# -*- coding: utf-8 -*-
"""
run_sbc.py
----------
SBC 分时图独立启动器 (便捷入口)
用法:
    python run_sbc.py               # 自动恢复上次退出时打开的所有窗口及设置 (若无记录则打开 600733)
    python run_sbc.py 301531        # 打开指定标的 301531
    python run_sbc.py 600733 10d    # 打开 600733 且指定周期为 10d
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
from ats.ui.intraday_strategy_dialog import (
    SBCIntradayChartDialog,
    open_sbc_chart_dialog,
    save_all_open_sbc_windows,
    restore_all_open_sbc_windows,
)
from sys_utils import ensure_backend_tk_running


def main():
    # 自动检查并后台静默拉起主 Tk 行情进程 (P0)
    try:
        ensure_backend_tk_running()
    except Exception as e:
        print(f"[SBC Launcher] 检查行情服务警告: {e}")

    app = QApplication(sys.argv)

    # 💡 核心特性：退出时自动持久化所有已打开的 SBC 窗口与设置
    def _on_app_about_to_quit():
        try:
            app.setProperty("is_app_exiting", True)
            save_all_open_sbc_windows()
            print("[SBC Launcher] 退出时已自动持久化保存所有已打开的 SBC 窗口与设置")
        except Exception as err:
            print(f"[SBC Launcher] 退出持久化警告: {err}")

    app.aboutToQuit.connect(_on_app_about_to_quit)

    # 解析命令行参数
    has_cli_code = len(sys.argv) > 1 and sys.argv[1].strip()
    if has_cli_code:
        code = sys.argv[1].strip()
        period = sys.argv[2].strip() if len(sys.argv) > 2 else "10d"
        print(f"[SBC Launcher] 启动指定 SBC 实盘分时窗口: 标的代码={code}, 初始周期={period}")
        window = open_sbc_chart_dialog(code=code, period_mode=period)
        if window:
            window.show()
    else:
        # 💡 无参启动：优先自动恢复上次退出时持久化的所有窗口、位置与个性化设置
        restored = restore_all_open_sbc_windows()
        if not restored:
            # 若从未保存过窗口或配置为空，使用默认兜底标的 600733
            code = "600733"
            period = "10d"
            print(f"[SBC Launcher] 无历史窗口记录，启动默认 SBC 窗口: 标的代码={code}, 周期={period}")
            window = open_sbc_chart_dialog(code=code, period_mode=period)
            if window:
                window.show()
        else:
            codes_str = ", ".join(getattr(d, 'code', '') for d in restored)
            print(f"[SBC Launcher] 成功自动恢复上次退出的 {len(restored)} 个 SBC 窗口与设置: [{codes_str}]")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
