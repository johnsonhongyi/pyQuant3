"""Unified startup and shutdown settings for desktop bridges."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from .antigravity_bridge_manager import AntigravityBridgeController
from .codex_bridge_manager import BridgeController


class BridgeStartupManagerDialog(QtWidgets.QDialog):
    """Manage manager-start and manager-exit behavior for each desktop bridge."""

    def __init__(self, project_root: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌面桥启动管理")
        self.setMinimumWidth(700)
        self.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        self.project_root = project_root
        self.controllers = {
            "codex": BridgeController(project_root),
            "antigravity": AntigravityBridgeController(project_root),
        }
        self.controls: dict[str, dict[str, QtWidgets.QWidget]] = {}
        self._build_ui()
        self.refresh_settings()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "分别设置每座桥是否随桌面管理器启动，以及桌面管理器退出时是否请求关闭。"
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        for key, title, detail_method in (
            ("codex", "🧩 Codex 桌面桥", "open_codex_bridge_manager"),
            ("antigravity", "🌟 Antigravity 桌面桥", "open_antigravity_bridge_manager"),
        ):
            group = QtWidgets.QGroupBox(title)
            row = QtWidgets.QHBoxLayout(group)
            start = QtWidgets.QCheckBox("随管理器启动")
            start.setToolTip("只控制下次管理器启动时是否拉起此桥；勾选或取消都不会立即启停当前桥。")
            start.toggled.connect(lambda checked, bridge=key: self._set_startup(bridge, checked))
            row.addWidget(start)

            stop = QtWidgets.QCheckBox("随管理器退出关闭")
            stop.setToolTip("开启后，管理器退出时请求桥接在当前任务完成后优雅停止。")
            stop.toggled.connect(lambda checked, bridge=key: self._set_shutdown(bridge, checked))
            row.addWidget(stop)

            mode = QtWidgets.QLabel()
            mode.setMinimumWidth(150)
            row.addWidget(mode)
            row.addStretch(1)

            detail = QtWidgets.QPushButton("详细管理…")
            detail.clicked.connect(lambda _=False, name=detail_method: self._open_detail(name))
            row.addWidget(detail)
            root.addWidget(group)
            self.controls[key] = {"start": start, "stop": stop, "mode": mode}

        footer = QtWidgets.QHBoxLayout()
        footer.addStretch(1)
        refresh = QtWidgets.QPushButton("刷新设置")
        refresh.clicked.connect(self.refresh_settings)
        footer.addWidget(refresh)
        close = QtWidgets.QPushButton("关闭")
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    def refresh_settings(self):
        for key, controller in self.controllers.items():
            try:
                task = controller.task_info()
            except Exception:
                task = {}
            mode = task.get("mode") if task.get("running") else controller.run_mode()
            forced_shutdown = controller.manager_exit_shutdown_forced(mode)
            start = self.controls[key]["start"]
            stop = self.controls[key]["stop"]
            mode_label = self.controls[key]["mode"]

            start.blockSignals(True)
            start.setChecked(controller.autostart_enabled())
            start.blockSignals(False)

            stop.blockSignals(True)
            stop.setChecked(controller.stop_on_manager_exit_enabled(mode))
            stop.setEnabled(not forced_shutdown)
            stop.setToolTip(
                "管理器线程无法脱离管理器进程，退出时会随管理器结束。切换为独立进程后可单独设置。"
                if forced_shutdown else
                "开启后，管理器退出时请求桥接在当前任务完成后优雅停止。"
            )
            stop.blockSignals(False)

            mode_label.setText("线程模式 · 随管理器退出" if forced_shutdown else "独立进程")

    def _set_startup(self, key: str, enabled: bool):
        control = self.controls[key]["start"]
        try:
            self.controllers[key].set_autostart_enabled(enabled)
        except Exception as exc:
            control.blockSignals(True)
            control.setChecked(not enabled)
            control.blockSignals(False)
            QtWidgets.QMessageBox.warning(self, "设置失败", f"保存管理器启动设置失败：{type(exc).__name__}")

    def _set_shutdown(self, key: str, enabled: bool):
        control = self.controls[key]["stop"]
        try:
            self.controllers[key].set_stop_on_manager_exit_enabled(enabled)
        except Exception as exc:
            control.blockSignals(True)
            control.setChecked(not enabled)
            control.blockSignals(False)
            QtWidgets.QMessageBox.warning(self, "设置失败", f"保存管理器退出设置失败：{type(exc).__name__}")

    def _open_detail(self, method_name: str):
        opener = getattr(self.parent(), method_name, None)
        if callable(opener):
            opener()
