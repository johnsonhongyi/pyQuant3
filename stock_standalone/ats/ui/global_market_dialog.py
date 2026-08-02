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
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setWindowTitle("🌐 全球外盘与热点情绪看板")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        
        # 极窄自适应风格暗黑 CSS
        self.setStyleSheet("""
            QDialog {
                background-color: #12151c;
                color: #e2e2e5;
            }
        """)

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
            cfg_path = self._get_config_path()
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                geom_hex = data.get("ats_global_market_dialog_geometry")
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
            cfg_path = self._get_config_path()
            data = {}
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            data["ats_global_market_dialog_geometry"] = self.saveGeometry().toHex().data().decode('utf-8')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[GlobalMarketDialog] Save geometry error: {e}")

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
