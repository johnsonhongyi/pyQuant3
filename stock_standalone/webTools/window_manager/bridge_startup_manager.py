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
            "分别设置每座桥的运行方式、随管理器启动及退出行为。修改立即保存；运行方式在下次启动桥时生效，退出选项以当前运行方式为准。"
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

            mode = QtWidgets.QComboBox()
            mode.addItem("独立进程", "process")
            mode.addItem("管理器线程", "thread")
            mode.setMinimumWidth(150)
            mode.setToolTip("设置下次启动桥的运行方式；不会中断当前任务或自动重启桥。")
            mode.currentIndexChanged.connect(lambda _index, bridge=key: self._set_mode(bridge))
            row.addWidget(mode)
            active_mode = QtWidgets.QLabel()
            active_mode.setWordWrap(True)
            row.addWidget(active_mode)
            row.addStretch(1)

            detail = QtWidgets.QPushButton("详细管理…")
            detail.clicked.connect(lambda _=False, name=detail_method: self._open_detail(name))
            row.addWidget(detail)
            root.addWidget(group)
            self.controls[key] = {"start": start, "stop": stop, "mode": mode, "active_mode": active_mode}

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
            configured_mode = controller.run_mode()
            mode = (task.get("mode") or configured_mode) if task.get("running") else configured_mode
            forced_shutdown = controller.manager_exit_shutdown_forced(mode)
            start = self.controls[key]["start"]
            stop = self.controls[key]["stop"]
            mode_choice = self.controls[key]["mode"]
            mode_choice.blockSignals(True)
            mode_choice.setCurrentIndex(mode_choice.findData(configured_mode))
            mode_choice.blockSignals(False)

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

            current = "管理器线程" if mode == "thread" else "独立进程"
            self.controls[key]["active_mode"].setText(
                f"当前：{current}；重启桥后切换" if task.get("running") and mode != configured_mode else
                f"当前：{current}" if task.get("running") else "桥未运行"
            )

    def _set_mode(self, key: str):
        try:
            self.controllers[key].set_run_mode(self.controls[key]["mode"].currentData())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "设置失败", f"保存桥运行方式失败：{type(exc).__name__}")
        self.refresh_settings()

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
