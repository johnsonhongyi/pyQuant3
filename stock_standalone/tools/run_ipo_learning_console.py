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
import socket
import threading
import logging
import time
from pathlib import Path

if not getattr(sys, "frozen", False) and "__compiled__" not in globals():
    _source_root = str(Path(__file__).absolute().parents[1])
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)

if __name__ == "__main__":
    multiprocessing.freeze_support()

from sys_utils import get_app_root, setup_qt_clean_environment, safe_resolve_path
app_dir = str(safe_resolve_path(get_app_root()))
setup_qt_clean_environment()

if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QStatusBar,
    QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QTimer
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
        from ats.ui.responsive_flow import ResponsiveFlow
        toolbar_layout = ResponsiveFlow()
        toolbar_layout.setSpacing(10)

        title_lbl = QLabel("<b>IPO 情绪感知与自学习</b>")
        title_lbl.setToolTip("新股情绪感知与本地自学习系统 (IPO Learning Console)")
        title_lbl.setMinimumWidth(0)
        title_lbl.setMaximumWidth(500)
        title_lbl.setStyleSheet("font-size: 13px; color: #3388ff;")
        toolbar_layout.addWidget(title_lbl)


        self.btn_open_dialog = QPushButton("🔍 打开单股仲裁因果透视 (Arbitration Dialog)")
        self.btn_open_dialog.setToolTip(self.btn_open_dialog.text())
        self.btn_open_dialog.setText("打开单股仲裁透视")
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
        self.current_selected_code = ""
        self.current_selected_name = ""

        # Keep the page at viewport height; scroll inside individual panes only.
        scroll_area.takeWidget()
        scroll_area.deleteLater()
        main_layout.addWidget(self.console, 1)
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(400)
        self._geometry_timer.timeout.connect(self._save_geometry)
        saved = self.console.layout_settings.value("window/geometry")
        if saved is not None:
            self.restoreGeometry(saved)

        # 5. 状态栏
        status_bar = QStatusBar(self)
        status_bar.setStyleSheet("QStatusBar { color: #9ca3af; background-color: #17191f; border-top: 1px solid #353a45; } QStatusBar::item { border: none; }")
        self.setStatusBar(status_bar)
        status_bar.showMessage("已就绪 [自适应模式]。窗口已根据当前显示器尺寸自动缩放，支持自由拖拽或最大化。")

    def _save_geometry(self):
        if not self.isMinimized():
            self.console.layout_settings.setValue("window/geometry", self.saveGeometry())
            self.console.layout_settings.sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_geometry_timer"):
            self._geometry_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_geometry_timer"):
            self._geometry_timer.start()

    def _open_arbitration_dialog(self):
        """弹出单例仲裁因果透视对话框"""
        IPOArbitrationDetailDialog.show_or_update(
            code=getattr(self.console, "_active_ticker", "301689"),
            parent=self,
        )

    def link_stock(self, code, name=""):
        """Receive table Up/Down linkage without an ATS main window."""
        clean_code = "".join(ch for ch in str(code) if ch.isdigit())
        if len(clean_code) != 6:
            return
        self.current_selected_code = clean_code
        self.current_selected_name = str(name or "")
        self.console._active_ticker = clean_code
        self.console.codex_dialogue.ticker.setText(clean_code)
        self.statusBar().showMessage(f"联动标的：{clean_code} {self.current_selected_name}")
        dialog = IPOArbitrationDetailDialog._shared_instance
        if dialog is not None and dialog.isVisible():
            dialog.update_content(clean_code)

        def push_read_only_linkage():
            try:
                with socket.create_connection(("127.0.0.1", 26668), timeout=0.1) as channel:
                    channel.sendall(f"CODE|{clean_code}".encode("ascii"))
            except OSError:
                pass
            try:
                from linkage_service import get_link_manager
                get_link_manager().push(
                    clean_code, flags={"tdx": True, "ths": True, "dfcf": False}, auto=False,
                )
            except Exception:
                logging.getLogger(__name__).exception("IPO外部联动失败：%s", clean_code)

        threading.Thread(target=push_read_only_linkage, daemon=True).start()

    def closeEvent(self, event):
        if getattr(self, "_close_ready", False):
            return super().closeEvent(event)
        event.ignore()
        if getattr(self, "_close_pending", False):
            return
        self._close_pending = True
        self._geometry_timer.stop()
        self._save_geometry()
        self._close_started = time.monotonic()
        log_dir = self.console._root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._shutdown_logger = logging.getLogger(f"ipo.shutdown.{id(self)}")
        handler = logging.FileHandler(log_dir / "ipo_console_lifecycle.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self._shutdown_logger.addHandler(handler)
        self._shutdown_logger.setLevel(logging.INFO)
        self._shutdown_logger.info("关闭请求：停止定时器，取消CLI、监控及采集任务")
        self.console.runtime_log.appendPlainText("正在关闭：取消后台任务，等待资源释放…")
        self.statusBar().showMessage("正在关闭；窗口保持响应，详细进度见右侧日志及logs/ipo_console_lifecycle.log")
        self.console.stop_monitor(timeout_ms=0)
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(200)
        self._close_timer.timeout.connect(self._poll_close)
        self._close_timer.start()

    def _poll_close(self):
        pending = []
        for name, worker in (("监控", self.console._worker),
                             ("采集", self.console._source_worker),
                             ("Codex", self.console.codex_dialogue.worker)):
            if worker is not None and worker.isRunning():
                pending.append(name)
        control = self.console._runtime_control
        if control is not None and control.is_alive():
            pending.append("运行控制")
        state = ", ".join(pending) or "全部后台任务已结束"
        if state != getattr(self, "_close_state", None):
            self._close_state = state
            self._shutdown_logger.info("关闭进度：%s", state)
            self.console.runtime_log.appendPlainText(f"关闭进度：{state}")
        self.statusBar().showMessage(f"正在关闭（{time.monotonic()-self._close_started:.1f}秒）：{state}")
        if not pending:
            self._close_timer.stop()
            self._shutdown_logger.info("关闭完成")
            for handler in list(self._shutdown_logger.handlers):
                handler.close()
                self._shutdown_logger.removeHandler(handler)
            self._close_ready = True
            self.close()


def main():
    parser = argparse.ArgumentParser(description="启动 IPO 自学习监控控制台")
    parser.add_argument("--project-root", help="指定运行数据根目录")
    parser.add_argument("--codex-chat", action="store_true", help="直接打开Codex CLI互动与模拟对账页")
    parser.add_argument("--simulation-read-only", action="store_true", help="只读展示仿真结果，不采集、不启 Worker")
    args = parser.parse_args()
    if args.simulation_read_only:
        print("[IPO Console] 仿真只读展示：不采集、不启动 Worker、不调用模型或交易。", flush=True)
    elif args.codex_chat:
        print("[IPO Console] Codex CLI互动与对账：仅手动发送，不启动自动采集或策略Worker。", flush=True)
    else:
        print(
            "[IPO Console] ATS 只读监控已启动：约 2.5 秒后执行一次冷启动读取；"
            "采集与历史计算使用独立子进程；工作日 08:55–15:40 每 5 分钟检查，其他时段等待下个工作日。",
            flush=True,
        )
        print(
            "[IPO Console] 使用顺序：数据契约与时效 → Gate 阻断原因 → D1-D3 人工复核 → 回放验收；"
            "Ollama 仅分析有效新鲜观察，训练与交易授权保持关闭。",
            flush=True,
        )
    from sys_utils import get_app_root
    resolved_root = str(safe_resolve_path(args.project_root or get_app_root()))
    os.environ["INSTOCK_APP_ROOT"] = resolved_root
    if args.codex_chat and not args.simulation_read_only:
        from ats.ui.ipo_codex_dialogue import CodexIPODialogue
        app = QApplication.instance() or QApplication([sys.argv[0]])
        window = QMainWindow()
        window.setWindowTitle("IPO · Codex CLI 互动 / 对账")
        dialogue = CodexIPODialogue(resolved_root, window)
        window.setCentralWidget(dialogue)
        window.resize(1100, 800)
        app.aboutToQuit.connect(dialogue.shutdown)
        window.show()
        return app.exec()

    gate_provider = None
    if not args.simulation_read_only:
        # run_ats.py dispatches --ipo-console before its normal ATS startup.
        # This mode owns only the read-only Gate reader lifecycle.
        try:
            from ats.strategy.ipo_gate_context_provider import get_default_ipo_gate_context_provider

            gate_provider = get_default_ipo_gate_context_provider(resolved_root)
            gate_provider.start_auto_refresh()
        except Exception as exc:
            print(f"[IPO Console] Read-only services unavailable: {type(exc).__name__}", flush=True)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("IPOLearningConsoleStandalone")

    window = StandaloneLearningWindow(
        project_root=resolved_root,
        simulation_read_only=args.simulation_read_only,
    )
    window.show()
    if args.codex_chat:
        window.console._select_console_tab("Codex CLI 互动 / 对账")

    try:
        return app.exec()
    finally:
        if gate_provider is not None:
            gate_provider.stop_auto_refresh()


if __name__ == "__main__":
    main()
