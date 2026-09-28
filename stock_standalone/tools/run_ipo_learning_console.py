# -*- coding: utf-8 -*-
"""
tools/run_ipo_learning_console.py
---------------------------------
新股情绪感知与自学习决策监控控制台 (IPOLearningConsole) 独立启动器
- 屏幕尺寸动态自适应：根据主显示器可用分辨率 (availableGeometry) 自动按比例适配，避免超宽爆屏；
- 高 DPI 与小分辨率保护：内置 QScrollArea 优雅滚动支撑与流式排布，适配 1080p/2K/4K 及缩放环境；
- 包含【因果仲裁详情透视 (IPOArbitrationDetailDialog)】一键打开与查看；
- 干净的 Qt 运行环境，支持离线或实盘联机查看。
"""

import sys
import os
import multiprocessing
import argparse

if __name__ == "__main__":
    multiprocessing.freeze_support()

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

try:
    from sys_utils import setup_qt_clean_environment
    setup_qt_clean_environment()
except Exception:
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QStatusBar,
    QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt
from ats.ui.ipo_learning_console import IPOLearningConsole
from ats.ui.ipo_arbitration_detail_dialog import IPOArbitrationDetailDialog


class StandaloneLearningWindow(QMainWindow):
    """独立承载 IPOLearningConsole 的主窗口 (支持动态自适应与滚动保护)"""

    def __init__(self, parent=None, project_root=None, simulation_read_only=False):
        super().__init__(parent)
        self.setWindowTitle("🤖 IPO 新股情绪感知与自学习监控控制台 [独立自适应模式]")
        self.setMinimumSize(780, 500)

        # 1. 动态自适应屏幕分辨率与可用工作区
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            # 宽取可用宽度的 86% (限制在 880 ~ 1320 之间，且绝不超过可用宽度的 95%)
            target_w = max(800, min(int(avail.width() * 0.86), 1320, avail.width() - 40))
            # 高取可用高度的 85% (限制在 560 ~ 880 之间，且绝不超过可用高度的 92%)
            target_h = max(520, min(int(avail.height() * 0.85), 880, avail.height() - 60))
            pos_x = avail.x() + (avail.width() - target_w) // 2
            pos_y = avail.y() + (avail.height() - target_h) // 2
            self.setGeometry(pos_x, pos_y, target_w, target_h)
        else:
            self.resize(1024, 720)

        # 2. 顶层主容器
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet("QWidget { color: #e5e7eb; background-color: #17191f; }")
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 3. 快捷工具条
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        title_lbl = QLabel("<b>新股情绪感知与本地自学习系统 (IPO Learning Console)</b>")
        title_lbl.setStyleSheet("font-size: 13px; color: #3388ff;")
        toolbar_layout.addWidget(title_lbl)

        toolbar_layout.addStretch()

        self.btn_open_dialog = QPushButton("🔍 打开单股仲裁因果透视 (Arbitration Dialog)")
        self.btn_open_dialog.setStyleSheet("""
            QPushButton {
                background-color: #1e3a5f;
                color: #ffffff;
                font-weight: bold;
                padding: 4px 10px;
                border-radius: 4px;
                border: 1px solid #3388ff;
            }
            QPushButton:hover {
                background-color: #2b5288;
            }
        """)
        self.btn_open_dialog.clicked.connect(self._open_arbitration_dialog)
        toolbar_layout.addWidget(self.btn_open_dialog)

        main_layout.addLayout(toolbar_layout)

        # 4. 外层滚动保护区 (针对小分辨率屏幕或高 DPI 缩放)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea { background-color: #17191f; border: none; }
            QScrollBar:vertical, QScrollBar:horizontal { background-color: #17191f; border: none; margin: 0; }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal { background-color: #454c58; border-radius: 4px; min-width: 18px; min-height: 18px; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        """)

        # 核心控制台
        self.console = IPOLearningConsole(
            parent=scroll_area, project_root=project_root,
            simulation_read_only=simulation_read_only,
        )
        if simulation_read_only:
            self.btn_open_dialog.setEnabled(False)
            self.setWindowTitle("IPO 自学习仿真监控 [只读·无交易授权]")
        scroll_area.setWidget(self.console)

        main_layout.addWidget(scroll_area, 1)

        # 5. 状态栏
        status_bar = QStatusBar(self)
        status_bar.setStyleSheet("QStatusBar { color: #9ca3af; background-color: #17191f; border-top: 1px solid #353a45; } QStatusBar::item { border: none; }")
        self.setStatusBar(status_bar)
        status_bar.showMessage("已就绪 [自适应模式]。窗口已根据当前显示器尺寸自动缩放，支持自由拖拽或最大化。")

    def _open_arbitration_dialog(self):
        """弹出单例仲裁因果透视对话框"""
        IPOArbitrationDetailDialog.show_or_update(
            code="301689",
            parent=self,
        )

    def closeEvent(self, event):
        try:
            self.console.stop_monitor()
        except Exception:
            pass
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description="启动 IPO 自学习监控控制台")
    parser.add_argument("--project-root", help="指定运行数据根目录")
    parser.add_argument("--simulation-read-only", action="store_true", help="只读展示仿真结果，不采集、不启 Worker")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("IPOLearningConsoleStandalone")

    window = StandaloneLearningWindow(
        project_root=args.project_root,
        simulation_read_only=args.simulation_read_only,
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
