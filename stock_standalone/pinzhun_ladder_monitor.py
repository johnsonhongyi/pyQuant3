# -*- coding: utf-8 -*-
"""
pinzhun_ladder_monitor.py — 频准激光 (688826) 8/18 上市盯盘与分时阶梯策略独立启动程序
特点：
1. 100% 适配 PyInstaller / Nuitka 打包模式 (支持 is_packaged_env 与 get_app_root 物理定位)；
2. 支持 Windows HighDPI 高分屏自适应与 multiprocessing.freeze_support()；
3. 具备独立 IPC 数据流监听与本地行情解析，不与 ATS 共享主界面，杜绝模态阻塞；
4. 支持双击直接启动、或在命令行中指定标的代码（如 pinzhun_ladder_monitor.exe 688826）；
5. 具备窗口置顶、全天分时模拟回测演练、7 节点动态评分与 ATS 统一 QSS 暗黑样式。
"""

import sys
import os
import argparse
import multiprocessing

# 1. 必须在导入任何 PyQt6 组件前开启 Windows HighDPI 高分屏自适应
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

# 2. Windows 下打包必须加 freeze_support 防止子进程递归重开
if __name__ == "__main__":
    multiprocessing.freeze_support()

# 3. 严格使用 sys_utils.get_app_root() 进行 Nuitka / PyInstaller / Dev 统一兼容的物理根目录定位
try:
    from sys_utils import get_app_root, is_packaged_env, resolve_stock_name
    app_root = get_app_root()
except Exception:
    app_root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(app_root, "config")):
        parent_root = os.path.dirname(app_root)
        if os.path.exists(os.path.join(parent_root, "config")):
            app_root = parent_root

if app_root not in sys.path:
    sys.path.insert(0, app_root)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow
from ats.ui.styles import apply_dark_theme, DARK_THEME_QSS
from sys_utils import resolve_stock_name


def main():
    parser = argparse.ArgumentParser(description="频准激光 8/18 上市盯盘与分时阶梯交易独立系统")
    parser.add_argument("code", nargs="?", default="688826", help="目标股票代码 (默认 688826 频准激光)")
    parser.add_argument("--top", action="store_true", help="启动时默认窗口置顶")
    args = parser.parse_args()

    # 高分屏缩放策略
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("PinzhunLadderMonitor")
    app.setStyle("Fusion")
    
    # 🎨 全局应用 ATS 统一暗黑主题与字体
    apply_dark_theme(app)
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    engine = IntradayStrategyEngine.get_instance()
    code_clean = "".join(filter(str.isdigit, str(args.code))).zfill(6)
    name = resolve_stock_name(code_clean)

    win = PinzhunLadderStandaloneWindow(code=code_clean, name=name)
    if args.top:
        win._toggle_stay_on_top()
    win.show()

    pkg_info = " [打包环境]" if is_packaged_env() else " [源码环境]"
    print(f"🚀 频准激光 8/18 独立盯盘窗口已成功启动！[股票: {code_clean} {name}]{pkg_info}")
    print(f"📁 根目录定位: {app_root}")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
