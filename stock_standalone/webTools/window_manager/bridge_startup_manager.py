"""Unified startup and shutdown settings for desktop bridges."""

from __future__ import annotations

from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from .antigravity_bridge_manager import AntigravityBridgeController
from .bridge_dialog_geometry import configure_bridge_dialog_geometry
from .codex_bridge_manager import BridgeController


class BridgeRestartWorker(QtCore.QThread):
    result_ready = QtCore.pyqtSignal(str, bool, str)
    progress = QtCore.pyqtSignal(str, str)

    def __init__(self, controller, bridge_name: str, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.bridge_name = bridge_name

    def run(self):
        try:
            result = self.controller.restart_bridge(
                progress_callback=lambda message: self.progress.emit(self.bridge_name, message)
            )
            self.result_ready.emit(self.bridge_name, True, result)
        except Exception as exc:
            self.result_ready.emit(self.bridge_name, False, f"{type(exc).__name__}: {str(exc)[:400]}")


class BridgeStartupManagerDialog(QtWidgets.QDialog):
    """Manage manager-start and manager-exit behavior for each desktop bridge."""

    def __init__(self, project_root: str | Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("桌面桥启动管理")
        self.setMinimumSize(760, 300)
        self.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        self.project_root = project_root
        self.controllers = {
            "codex": BridgeController(project_root),
            "antigravity": AntigravityBridgeController(project_root),
        }
        self._restart_workers: dict[str, BridgeRestartWorker] = {}
        self._restart_progress: dict[str, str] = {}
        self._restart_result: dict[str, tuple[bool, str]] = {}
        self.controls: dict[str, dict[str, QtWidgets.QWidget]] = {}
        self._build_ui()
        configure_bridge_dialog_geometry(
            self,
            "BridgeStartupManagerDialogV2",
            800,
            320,
            legacy_window_name="BridgeStartupManagerDialog",
        )
        self.refresh_settings()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "分别设置各桥的启动、退出行为和运行方式；修改立即保存。"
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
            mode.setFixedWidth(150)
            mode.setToolTip("设置下次启动桥的运行方式；不会中断当前任务或自动重启桥。")
            mode.currentIndexChanged.connect(lambda _index, bridge=key: self._set_mode(bridge))
            row.addWidget(mode)

            active_mode = QtWidgets.QLabel()
            active_mode.setMinimumWidth(115)
            active_mode.setWordWrap(False)
            row.addWidget(active_mode, 1)

            restart = QtWidgets.QPushButton("快速重启")
            restart.setToolTip("请求桥接在当前任务结束后停止，再按当前运行方式重新启动。")
            restart.clicked.connect(lambda _=False, bridge=key: self._restart_bridge(bridge))
            row.addWidget(restart)

            detail = QtWidgets.QPushButton("详细管理…")
            detail.clicked.connect(lambda _=False, name=detail_method: self._open_detail(name))
            row.addWidget(detail)
            root.addWidget(group)
            self.controls[key] = {
                "start": start, "stop": stop, "mode": mode,
                "active_mode": active_mode, "restart": restart,
            }

        footer = QtWidgets.QHBoxLayout()
        root.addStretch(1)
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
            worker = self._restart_workers.get(key)
            restarting = bool(worker and worker.isRunning())
            mode_mismatch = bool(task.get("running") and mode != configured_mode)
            active_mode = self.controls[key]["active_mode"]
            active_mode.setWordWrap(True)
            if restarting:
                active_text = self._restart_progress.get(key, "正在重启…")
            elif key in self._restart_result:
                success, result = self._restart_result[key]
                active_text = ("重启成功：" if success else "重启失败：") + result
            elif mode_mismatch:
                active_text = "待重启切换模式"
            else:
                active_text = f"当前：{current}" if task.get("running") else "桥未运行"
            active_mode.setText(active_text)
            active_mode.setToolTip(
                active_text if restarting or key in self._restart_result else
                "当前运行方式与所选设置不一致；重启桥后生效。" if mode_mismatch else ""
            )
            self.controls[key]["restart"].setEnabled(not restarting)

    def _restart_bridge(self, key: str):
        current = self._restart_workers.get(key)
        if current is not None and current.isRunning():
            return
        worker = BridgeRestartWorker(self.controllers[key], key, self)
        self._restart_workers[key] = worker
        self._restart_progress[key] = "正在检查桥状态…"
        self._restart_result.pop(key, None)
        worker.progress.connect(self._restart_progress_changed)
        worker.result_ready.connect(self._restart_finished)
        worker.finished.connect(self._clear_finished_restart_workers)
        worker.finished.connect(worker.deleteLater)
        self.controls[key]["restart"].setEnabled(False)
        self.controls[key]["active_mode"].setText(self._restart_progress[key])
        worker.start()

    def _restart_progress_changed(self, key: str, message: str):
        self._restart_progress[key] = message
        self.controls[key]["active_mode"].setText(message)
        self.controls[key]["active_mode"].setToolTip(message)

    def _restart_finished(self, key: str, success: bool, message: str):
        self._restart_result[key] = (success, message)
        self.controls[key]["restart"].setEnabled(True)
        self.controls[key]["active_mode"].setText(("重启成功：" if success else "重启失败：") + message)
        if not success:
            QtWidgets.QMessageBox.warning(self, "桥接重启失败", message)
        self.refresh_settings()

    def _clear_finished_restart_workers(self):
        for key, worker in tuple(self._restart_workers.items()):
            if not worker.isRunning():
                self._restart_workers.pop(key, None)
        QtCore.QTimer.singleShot(0, self.refresh_settings)

    def _set_mode(self, key: str):
        self._restart_result.pop(key, None)
        try:
            self.controllers[key].set_run_mode(self.controls[key]["mode"].currentData())
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "设置失败", f"保存桥运行方式失败：{type(exc).__name__}")
        self.refresh_settings()

    def _set_startup(self, key: str, enabled: bool):
        self._restart_result.pop(key, None)
        control = self.controls[key]["start"]
        try:
            self.controllers[key].set_autostart_enabled(enabled)
        except Exception as exc:
            control.blockSignals(True)
            control.setChecked(not enabled)
            control.blockSignals(False)
            QtWidgets.QMessageBox.warning(self, "设置失败", f"保存管理器启动设置失败：{type(exc).__name__}")

    def _set_shutdown(self, key: str, enabled: bool):
        self._restart_result.pop(key, None)
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

    def closeEvent(self, event):
        for worker in self._restart_workers.values():
            if worker.isRunning() and not worker.wait(1000):
                QtWidgets.QMessageBox.information(self, "正在重启", "桥接重启尚未完成，请稍后关闭此窗口。")
                event.ignore()
                return
        super().closeEvent(event)
