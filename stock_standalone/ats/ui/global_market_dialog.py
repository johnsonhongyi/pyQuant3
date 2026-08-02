# -*- coding: utf-8 -*-
"""
ATS Global Market Dialog (独立外盘看盘弹窗)
打破对 ATS 主界面布局与 TabBar 的撑宽影响，以极窄风格、独立非阻塞窗口展现外盘情绪与连带看板。

核心功能:
1. 独立窗口 (QDialog), 默认极窄自适应风格 (1020x680).
2. 窗口位置、大小及内部 Col 列宽 100% 物理自动持久化 (window_config.json).
3. 动态响应全局股票与板块联动.
"""

import json
import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from PyQt6.QtCore import Qt, QByteArray
from sys_utils import get_app_root, get_conf_path
from ats.ui.global_market_panel import GlobalMarketPanel

_dialog_instance = None


class GlobalMarketDialog(QDialog):
    """🌐 ATS 全球外盘与热点情绪独立看板窗口"""

    def __init__(self, parent_window=None):
        super().__init__(None)  # ⚡ 传入 None 使其成为完全独立的顶级 Window 窗口，不作为主窗口的子窗口受限
        self.parent_window = parent_window
        self.setWindowTitle("🌐 全球外盘与热点情绪看板")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        from ats.ui.styles import apply_dark_theme
        apply_dark_theme(self)

        self._init_ui()
        self._restore_dialog_geometry()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.panel = GlobalMarketPanel(parent=self)
        layout.addWidget(self.panel)

        # 联动信号传递
        if self.parent_window:
            if hasattr(self.parent_window, "on_sector_clicked"):
                self.panel.sector_selected.connect(self.parent_window.on_sector_clicked)
            if hasattr(self.parent_window, "on_stock_clicked"):
                self.panel.stock_selected.connect(self.parent_window.on_stock_clicked)

    def _get_config_path(self):
        try:
            return get_conf_path("window_config.json", get_app_root())
        except Exception:
            return "window_config.json"

    def _restore_dialog_geometry(self):
        """恢复窗口物理尺寸与位置"""
        try:
            from ats.ui.styles import load_config_node
            geom_hex = load_config_node("ats_global_market_dialog_geometry", None)
            if geom_hex:
                self.restoreGeometry(QByteArray.fromHex(geom_hex.encode('utf-8')))
                return
        except Exception as e:
            print(f"[GlobalMarketDialog] Restore geometry error: {e}")

        # 默认极窄自适应尺寸
        self.resize(1020, 680)

    def _save_dialog_geometry(self):
        """物理持久化落盘窗口尺寸与位置"""
        try:
            from ats.ui.styles import save_config_node
            geom_hex = self.saveGeometry().toHex().data().decode('utf-8')
            save_config_node("ats_global_market_dialog_geometry", geom_hex)
        except Exception as e:
            print(f"[GlobalMarketDialog] Save geometry error: {e}")

    def keyPressEvent(self, event):
        """禁用 Esc 键关闭窗口"""
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self._save_dialog_geometry()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._save_dialog_geometry()
        super().hideEvent(event)


def open_global_market_dialog(parent_window=None):
    """单例调起/激活全球外盘看板独立弹窗"""
    global _dialog_instance
    from PyQt6.sip import isdeleted

    if _dialog_instance is not None and not isdeleted(_dialog_instance):
        try:
            if _dialog_instance.isMinimized():
                _dialog_instance.showNormal()
            _dialog_instance.show()
            _dialog_instance.raise_()
            _dialog_instance.activateWindow()
            if hasattr(_dialog_instance.panel, "refresh_data"):
                _dialog_instance.panel.refresh_data(force=False)
            return _dialog_instance
        except Exception:
            _dialog_instance = None

    _dialog_instance = GlobalMarketDialog(parent_window=parent_window)
    _dialog_instance.show()
    _dialog_instance.raise_()
    _dialog_instance.activateWindow()
    return _dialog_instance
