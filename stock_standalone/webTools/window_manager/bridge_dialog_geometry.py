"""Shared size and position persistence for desktop bridge dialogs."""

from __future__ import annotations

import logging

from PyQt6 import QtCore

logger = logging.getLogger(__name__)


class _BridgeDialogGeometryPersistence(QtCore.QObject):
    def __init__(self, dialog, window_name: str):
        super().__init__(dialog)
        self.dialog = dialog
        self.window_name = window_name
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.save)
        dialog.installEventFilter(self)
        dialog.finished.connect(lambda _result: self.save())

    def eventFilter(self, watched, event):
        if watched is self.dialog and event.type() in (
            QtCore.QEvent.Type.Move,
            QtCore.QEvent.Type.Resize,
        ):
            self._timer.start()
        return False

    def save(self):
        self._timer.stop()
        parent = self.dialog.parentWidget()
        saver = getattr(parent, "save_window_position_qt_visual", None)
        if callable(saver):
            try:
                saver(self.dialog, self.window_name, force=True)
            except Exception:
                # Geometry persistence must not interfere with bridge operations or dialog shutdown.
                logger.exception("保存桥管理窗口位置失败：%s", self.window_name)


def configure_bridge_dialog_geometry(
    dialog,
    window_name: str,
    default_width: int,
    default_height: int,
    legacy_window_name: str | None = None,
):
    """Restore a saved dialog geometry and persist subsequent move/resize changes."""
    dialog.resize(default_width, default_height)
    parent = dialog.parentWidget()
    loader = getattr(parent, "load_window_position_qt", None)
    migrated = False
    if callable(loader):
        try:
            geometry = loader(
                dialog,
                window_name,
                default_width=default_width,
                default_height=default_height,
                preserve_default_position=True,
            )
            if legacy_window_name and geometry[2] is None:
                legacy_geometry = loader(
                    dialog,
                    legacy_window_name,
                    default_width=default_width,
                    default_height=default_height,
                    preserve_default_position=True,
                )
                if legacy_geometry[2] is not None and legacy_geometry[3] is not None:
                    dialog.resize(default_width, default_height)
                    dialog.move(legacy_geometry[2], legacy_geometry[3])
                    migrated = True
        except Exception:
            logger.exception("恢复桥管理窗口位置失败：%s", window_name)
    dialog._bridge_geometry_persistence = _BridgeDialogGeometryPersistence(dialog, window_name)
    if migrated:
        dialog._bridge_geometry_persistence.save()
