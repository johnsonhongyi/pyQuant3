# -*- coding: utf-8 -*-
"""
SignalDashboardPanel - 策略信号分类仪表盘
聚合实时信号，提供市场温度计、板块热力统计及分类过滤功能。
支持个股信号聚合、样式持久化与时间排序。
"""
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger(__name__)
import sys
import re
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTabWidget,
    QFrame, QPushButton, QApplication, QDialog, QTextEdit, QLineEdit,
    QProgressBar, QGridLayout, QComboBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QByteArray, QModelIndex
import threading
import time
from PyQt6.QtGui import QColor, QFont, QBrush
from JohnsonUtil.commonTips import timed_ctx
try:
    from sector_focus_engine import get_focus_controller
except ImportError:
    get_focus_controller = lambda: None

from tk_gui_modules.window_mixin import WindowMixin
from signal_bus import get_signal_bus, SignalBus, BusEvent
import os
import json
from bidding_racing_panel import SectorDetailDialog
from alert_manager import get_alert_manager
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE

SETTINGS_SECTION = "signal_dashboard_persistence"

# [NEW] 模块级锁，防止 Panel 和 Dialog 同时写入同一个配置文件导致状态丢失
_CONFIG_FILE_LOCK = threading.RLock()
# ✅ 盘中交易引擎
def get_engine_controller():
    """获取全局引擎控制器单例 (已优化为顶层导入)"""
    return get_focus_controller()

class MarketAlertDetailDialog(QDialog, WindowMixin):
    """市场预警个股异动详情弹窗"""
    code_clicked = pyqtSignal(str, str) # 信号联动 (代码, 名称)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📡 预警个股异动明细")
        self.setMinimumWidth(480)
        self._is_updating = False
        
        # ⭐ [FIX] 先设置 WindowFlags（防范句柄重建导致 load_window_position_qt 被重置破坏）
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        
        # 加载窗口位置与大小
        self.load_window_position_qt(self, "market_alert_detail_dialog", default_width=550, default_height=500)
        self.setStyleSheet("QDialog { background-color: #1a1e2b; color: #ffffff; }")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # [NEW] 顶部统计信息与标题
        top_layout = QHBoxLayout()
        header = QLabel("📡 异动详情 | 单击联动")
        header.setStyleSheet("color: #00FFCC; font-size: 13px; font-weight: bold;")
        top_layout.addWidget(header)
        
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")
        top_layout.addStretch()
        top_layout.addWidget(self.stats_label)
        layout.addLayout(top_layout)
        
        # [MOD] 扩展列: 代码, 名称, 涨幅, 量比, DFF, DFF2, 理由
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "涨幅%", "量比", "DFF", "DFF2", "详情/理由"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d121f;
                color: #ffffff;
                gridline-color: #2a2d42;
                border: none;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 100);
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 100);
                min-width: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
        
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        
        self._is_updating = True # 🛡️ [FIX] 启动初始保护，防止默认设置触发保存
        # [MOD] 极致精简布局：设置核心列宽 (极致紧凑版)
        self.table.setColumnWidth(0, 55)  # 代码
        self.table.setColumnWidth(1, 65)  # 名称
        self.table.setColumnWidth(2, 55)  # 涨幅
        self.table.setColumnWidth(3, 45)  # 量比
        self.table.setColumnWidth(4, 40)  # DFF
        self.table.setColumnWidth(5, 40)  # DFF2
        
        h.setStretchLastSection(True)
        # [NEW] 启用排序
        h.setSectionsClickable(True)
        self.table.setSortingEnabled(True)

        # [NEW] 持久化支持
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_column_widths)
        h.sectionResized.connect(self._on_section_resized)
        
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed) # [NEW] 增加键盘上下键联动支持
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)
        self.setLayout(layout) # ⭐ [FIX] 显式绑定激活布局，确保 resize 事件在句柄销毁后依然物理传导
        
        # [NEW] 结束初始化保护延迟一点，确保 restoreState 完成后再放开 sectionResized 的保存
        QTimer.singleShot(500, lambda: setattr(self, '_is_updating', False))
        
    def _on_item_clicked(self, item):
        if item and not self._is_updating:
            row = item.row()
            self.code_clicked.emit(self.table.item(row, 0).text(), self.table.item(row, 1).text())

    def _on_selection_changed(self):
        """[GUI] 监听选择变动（支持键盘上下键联动）"""
        if self._is_updating: return
        items = self.table.selectedItems()
        if not items: return
        
        # [PERF] 仅在键盘或鼠标切换行时触发联动
        row = items[0].row()
        code_it = self.table.item(row, 0)
        name_it = self.table.item(row, 1)
        if code_it and name_it:
            code, name = code_it.text(), name_it.text()
            if code and code != "N/A":
                self.code_clicked.emit(code, name)

    def _show_context_menu(self, pos):
        """[GUI] 右键菜单：支持代码复制"""
        item = self.table.itemAt(pos)
        if not item: return
        row = item.row()
        code_item = self.table.item(row, 0)
        if not code_item: return
        code = code_item.text()
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #1a1c2c; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #2a2d42; }")
        
        copy_action = menu.addAction(f"📋 复制代码: {code}")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_section_resized(self, index, old_size, new_size):
        """[GUI] 监听列宽变动，触发延迟保存"""
        if not getattr(self, '_is_updating', False):
            self._save_timer.start(2000)

    def _save_column_widths(self):
        """[DATA] 聚合保存列宽状态 (使用 Hex 协议)"""
        try:
            # 1. 采集状态
            state = self.table.horizontalHeader().saveState().toHex().data().decode()
            
            config_file = WINDOW_CONFIG_FILE
            
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except: pass
                
                # 写入状态
                data["market_alert_detail_header_v2"] = state
                
                # 原子写盘
                tmp = config_file + f".tmp_{id(self)}"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                os.replace(tmp, config_file)
                
            logger.debug(f"✅ [Dashboard] Market alert details columns saved.")
        except Exception as e:
            logger.error(f"❌ [Dashboard] Failed to save alert detail columns: {e}")

    def _restore_column_widths(self):
        """[DATA] 从磁盘恢复列宽状态"""
        try:
            config_file = WINDOW_CONFIG_FILE
            if not os.path.exists(config_file): return
            
            with _CONFIG_FILE_LOCK:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # 优先尝试 v2 (Hex)
            state_hex = data.get("market_alert_detail_header_v2")
            if state_hex:
                ok = self.table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode()))
                logger.debug(f"📊 [Dashboard] Market alert details columns restored: {ok}")
                return

            # 兼容旧版 (widths dict)
            widths = data.get("market_alert_detail_cols", {})
            if widths:
                for col_idx_str, w in widths.items():
                    try:
                        idx = int(col_idx_str)
                        if idx < self.table.columnCount():
                            self.table.setColumnWidth(idx, w)
                    except: pass
        except Exception as e:
            logger.debug(f"⚠️ [Dashboard] Failed to restore alert detail columns: {e}")

    def keyPressEvent(self, event):
        """[GUI] 按下 ESC 键自动关闭窗口"""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def update_data(self, codes, df_snapshot=None, details=None):
        """[GUI] 使用快照数据或预定义的 details 填充表格"""
        self._is_updating = True # 🔐 [LOCK] 开启更新锁，防止填表期间触发多余联动
        self.table.setSortingEnabled(False) # [PERF] 更新时关闭排序
        self.table.setRowCount(0)
        
        try:
            if not codes: 
                self.stats_label.setText("总计: 0 | 平均涨幅: 0.00%")
                return
            
            # 将 details 转为 dict 方便查找
            detail_map = {d['code']: d for d in (details or [])}
            
            self.table.setRowCount(len(codes))
            
            # 统计变量
            total_pct = 0.0
            valid_count = 0
            sector_counts = {} # {sector: count}
            
            for i, code in enumerate(codes):
                d_item = detail_map.get(code, {})
                name = d_item.get('name', '-')
                detail = str(d_item.get('sig_type', ''))
                pct = 0.0
                vol_ratio = 1.0
                dff = 0.0
                dff2 = 0.0
                
                # [MOD] 注入实时行情快照数据 (包含 DFF/DFF2)
                if df_snapshot is not None and code in df_snapshot.index:
                    row = df_snapshot.loc[code]
                    if name == "-": name = str(row.get('name', '-'))
                    pct = row.get('percent', 0.0)
                    vol_ratio = row.get('volume_ratio', 1.0)
                    dff = row.get('dff', 0.0)
                    dff2 = row.get('dff2', 0.0)
                    
                    # [NEW] 板块分布统计
                    raw_cats = str(row.get('category', ''))
                    if raw_cats:
                        cats = [c.strip() for c in raw_cats.replace("；", ";").replace("+", ";").split(";") if c.strip()]
                        for ca in cats:
                            if not self._is_generic_concept(ca):
                                sector_counts[ca] = sector_counts.get(ca, 0) + 1
                    
                    total_pct += pct
                    valid_count += 1
                    
                    if not detail: detail = str(row.get('signal', ''))
                    
                self._fast_set_item(i, 0, code)
                self._fast_set_item(i, 1, name)
                # 数值列使用 NumericTableWidgetItem 以支持排序
                self._fast_set_item(i, 2, f"{pct:+.2f}%", color="#ff4444" if pct > 0 else "#44ff44", is_numeric=True)
                self._fast_set_item(i, 3, f"{vol_ratio:.2f}", is_numeric=True)
                self._fast_set_item(i, 4, f"{dff:+.2f}", is_numeric=True)
                self._fast_set_item(i, 5, f"{dff2:+.2f}", is_numeric=True)
                self._fast_set_item(i, 6, detail)

            # [MOD] 使用极高饱和度颜色 (Neon Style) 提高清晰度
            avg_pct = total_pct / valid_count if valid_count > 0 else 0.0
            avg_color = "#00FF00" if avg_pct >= 0 else "#FF3333" 
            
            # 统计文本构建 (使用高对比度 HTML)
            stats_html = (
                f"<font color='#FFFFFF'>总计:</font> <font color='#FFFF00'>{len(codes)}</font> "
                f"<font color='#666666'>|</font> "
                f"<font color='#FFFFFF'>平均涨幅:</font> <font color='{avg_color}'>{avg_pct:+.2f}%</font>"
            )
            
            # 提取并排序板块分布
            sorted_sectors = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
            
            if sorted_sectors:
                # 领头板块使用青色高亮，计数用黄色
                top_3 = [f"<font color='#00FFFF'>{s}</font>(<font color='#FFFF00'>{c}</font>)" for s, c in sorted_sectors[:3]]
                stats_html += f" <font color='#666666'>|</font> <font color='#FFFFFF'>核心板块:</font> " + " ".join(top_3)
                
            self.stats_label.setText(stats_html)
        except Exception as e:
            logger.error(f"❌ [Dashboard] MarketAlertDetailDialog update failed: {e}")
        finally:
            self.table.setSortingEnabled(True) # [PERF] 恢复排序
            self._is_updating = False # 🔓 [UNLOCK] 数据填充完毕，解锁联动

    def _is_generic_concept(self, name):
        """[UTIL] 过滤泛概念"""
        generics = [
            "其它", "融资融券", "深股通", "沪股通", "预盈预增", "昨日涨停", 
            "昨日大涨", "昨日首板", "破净股", "转融券标的", "富时罗素概念股",
            "标普道琼斯纳指", "MSCI中国", "央企改革", "地方国企改革", "低价股"
        ]
        return any(g in str(name) for g in generics)

    def _fast_set_item(self, r, c, text, color=None, is_numeric=False):
        if is_numeric:
            it = NumericTableWidgetItem(text)
        else:
            it = QTableWidgetItem(text)
            
        if color: it.setForeground(QBrush(QColor(color)))
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(r, c, it)

    def closeEvent(self, event):
        """[GUI] 关闭时持久化所有状态"""
        # 保存窗口位置与大小
        self.save_window_position_qt_visual(self, "market_alert_detail_dialog")
        # 强制保存当前列宽
        self._save_column_widths()
        event.accept()

    def hideEvent(self, event):
        """[GUI] 隐藏时也保存位置 (应对 Tool 模式)"""
        self.save_window_position_qt_visual(self, "market_alert_detail_dialog")
        super().hideEvent(event)

    def showEvent(self, event):
        """[GUI] 展现时安全恢复列宽与大小，防范 C++ 构造期 access violation"""
        super().showEvent(event)
        if self.layout():
            self.layout().activate() # ⭐ [FIX] 强制触发布局重算，确保加载完位置后视图尺寸同步填充
        if not getattr(self, '_columns_restored', False):
            self._restore_column_widths()
            self._columns_restored = True

    def resizeEvent(self, event):
        """[GUI] 强力重写 resizeEvent，保证窗口放大缩小时，内部布局和表格大小 100% 物理同步，不留多余空白底框"""
        super().resizeEvent(event)
        if self.layout():
            self.layout().setGeometry(self.rect())


class VolumeDetailsDialog(QDialog, WindowMixin):
    """持久化的放量详情弹窗"""
    code_clicked = pyqtSignal(str, str) # 信号联动 (代码, 名称)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔥 今日异动放量个股 (Top 200)")
        self.setMinimumWidth(380)
        self._is_updating = False # 更新标志
        
        # ⭐ [FIX] 先设置 WindowFlags（防范句柄重建导致 load_window_position_qt 被重置破坏）
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        
        # 加载窗口位置与大小
        self.load_window_position_qt(self, "volume_details_dialog", default_width=450, default_height=600)
        self._is_updating = True # 开启初始化保护
        self.setStyleSheet("QDialog { background-color: #1a1e2b; color: #ffffff; }")
        
        # 窗口内置布局 (超窄边框配置)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        
        # 头部说明 (精简版)
        header_frame = QFrame()
        header_lay = QHBoxLayout(header_frame)
        header_lay.setContentsMargins(0, 0, 0, 0)
        
        header = QLabel("🔥 异动放量 | 双击行联动")
        header.setStyleSheet("color: #ffa500; font-size: 12px; padding-left: 5px; font-weight: bold;")
        header_lay.addWidget(header)
        
        header_lay.addStretch()
        self.btn_dna_audit_vol = QPushButton("🧬 DNA审计")
        self.btn_dna_audit_vol.setFixedWidth(85)
        self.btn_dna_audit_vol.setStyleSheet("""
            QPushButton { background: #333; color: #fff; border: 1px solid #555; border-radius: 3px; font-size: 8pt; font-weight: bold; height: 20px; }
            QPushButton:hover { background: #444; border-color: #00ff88; }
        """)
        self.btn_dna_audit_vol.clicked.connect(self._run_dna_audit_selected)
        header_lay.addWidget(self.btn_dna_audit_vol)
        
        layout.addWidget(header_frame)
        
        # 表格展示
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "涨幅%", "量比", "DFF", "DFF2"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26) # 行高微调 (适应 13px 文字)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch) # ⭐ [MOD] 设为 Stretch 模式，让四列随窗口拉伸一体化自动等宽放大缩小，保持完美视觉一致性
        h_header.setFixedHeight(28) # 表头高度微调
        h_header.sortIndicatorChanged.connect(lambda: self.table.scrollToTop())
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0d121f;
                color: #ffffff;
                gridline-color: #2a2d42;
                border: none;
            }
            QHeaderView {
                background-color: #1a1c2c;
                border: none;
            }
            QHeaderView::section {
                background-color: #1a1c2c;
                color: #888;
                padding: 4px;
                border: 0.5px solid #2a2d42;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #2a2d42;
                color: #00ff88;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 100);
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 100);
                min-width: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)
        
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_clicked)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)
        self.setLayout(layout) # ⭐ [FIX] 显式绑定激活布局，确保 resize 事件在句柄销毁后依然物理传导
        
        # 结束初始化保护
        QTimer.singleShot(200, lambda: setattr(self, '_is_updating', False))

    def _on_section_resized(self, index, old_size, new_size):
        """[GUI] 监听列宽变动，触发延迟保存"""
        if not getattr(self, '_is_updating', False):
            self._save_timer.start(2000)

    def _save_column_widths(self):
        """[DATA] 聚合保存列宽状态"""
        try:
            state = self.table.horizontalHeader().saveState().toHex().data().decode()
            config_file = WINDOW_CONFIG_FILE
            
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except: pass
                
                data["volume_details_header_v1"] = state
                
                tmp = config_file + f".tmp_vol_{id(self)}"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, config_file)
            logger.debug(f"✅ [Dashboard] Volume details columns saved.")
        except Exception as e:
            logger.error(f"❌ [Dashboard] Failed to save volume detail columns: {e}")

    def _restore_column_widths(self):
        """[DATA] 从磁盘恢复列宽状态"""
        try:
            config_file = WINDOW_CONFIG_FILE
            if not os.path.exists(config_file): return
            
            with _CONFIG_FILE_LOCK:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            state_hex = data.get("volume_details_header_v1")
            if state_hex:
                self.table.horizontalHeader().restoreState(QByteArray.fromHex(state_hex.encode()))
        except Exception as e:
            logger.debug(f"⚠️ [Dashboard] Failed to restore volume detail columns: {e}")
        
    def _on_item_clicked(self, item):
        if item:
            row = item.row()
            code = self.table.item(row, 0).text()
            name = self.table.item(row, 1).text()
            self.code_clicked.emit(code, name)
            
    def _on_selection_changed(self):
        """处理键盘上下键选择变化"""
        if self._is_updating: return
        items = self.table.selectedItems()
        if items:
            # 取得选中行的 Item
            row = items[0].row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                self.code_clicked.emit(code_item.text(), name_item.text())
            
    def update_data(self, details_list: List[dict]):
        """刷新数据内容"""
        self._is_updating = True
        self.table.setSortingEnabled(False) # 写入数据时关闭排序避免错位
        self.table.setRowCount(0)
        
        try:
            if not details_list: 
                return
            
            self.table.setRowCount(len(details_list))
            for i, item in enumerate(details_list):
                code = item.get("code", "")
                name = item.get("name", "")
                change = item.get("change", 0.0)
                ratio = item.get("ratio", 0.0)
                dff = item.get("dff", 0.0)
                dff2 = item.get("dff2", 0.0)
                
                # 代码 (亮色)
                c_item = QTableWidgetItem(code)
                c_item.setForeground(QBrush(QColor("#00ff00" if code.startswith(('60', '00')) else "#00bfff")))
                c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 0, c_item)
                
                # 名称
                n_item = QTableWidgetItem(name)
                n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, 1, n_item)
                
                # 涨幅 (注意：NumericTableWidgetItem 会处理排序，展示带格式文字)
                ch_item = NumericTableWidgetItem(change)
                ch_item.setText(f"{change:+.2f}%")
                ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if change > 0: ch_item.setForeground(QBrush(QColor("#ff4444")))
                elif change < 0: ch_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 2, ch_item)
                
                # 量比 (亮黄)
                r_item = NumericTableWidgetItem(ratio)
                r_item.setText(f"{ratio:.2f}")
                r_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                r_item.setForeground(QBrush(QColor("#ffff00")))
                self.table.setItem(i, 3, r_item)

                # DFF (高可靠 NumericTableWidgetItem)
                d_item = NumericTableWidgetItem(dff)
                d_item.setText(f"{dff:+.2f}")
                d_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if dff > 0: d_item.setForeground(QBrush(QColor("#ff4444")))
                elif dff < 0: d_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 4, d_item)
                
                # DFF2 (高可靠 NumericTableWidgetItem)
                d2_item = NumericTableWidgetItem(dff2)
                d2_item.setText(f"{dff2:+.2f}")
                d2_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if dff2 > 0: d2_item.setForeground(QBrush(QColor("#ff4444")))
                elif dff2 < 0: d2_item.setForeground(QBrush(QColor("#44ff44")))
                self.table.setItem(i, 5, d2_item)
        finally:
            self.table.setSortingEnabled(True)
            self.table.horizontalHeader().setSortIndicatorShown(True) # 恢复自适应排序
            self._is_updating = False

    def _run_dna_audit_selected(self):
        """🚀 [DNA-BATCH] 极限审计：针对异动放量列表"""
        items = []
        for r in range(self.table.rowCount()):
            c_it = self.table.item(r, 0)
            n_it = self.table.item(r, 1)
            if c_it and n_it:
                items.append((c_it.text(), n_it.text()))
        
        if not items: return
        
        # 确定候选名单
        sel_rows = sorted(list(set(i.row() for i in self.table.selectedItems())))
        target_items = []
        
        if len(sel_rows) > 1:
            # 锁定多选
            for r in sel_rows[:50]:
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
        elif len(sel_rows) == 1:
            # 向下 20
            start = sel_rows[0]
            for r in range(start, min(start + 20, self.table.rowCount())):
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
        else:
            # 默认前 20
            for r in range(min(20, self.table.rowCount())):
                target_items.append((self.table.item(r, 0).text(), self.table.item(r, 1).text()))
        
        code_to_name = {c: n for c, n in target_items if c and c != "N/A"}
        if code_to_name:
            main_app = getattr(self.parent(), 'parent_app', None)
            if not main_app: main_app = getattr(self.window(), 'parent_app', None)
            
            if main_app and hasattr(main_app, '_run_dna_audit_batch'):
                if hasattr(main_app, 'tk_dispatch_queue'):
                    # 🚀 [THREAD-SAFE] 通过 Tk 调度队列执行
                    _cn = dict(code_to_name)
                    main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
                else:
                    main_app._run_dna_audit_batch(code_to_name)
            else:
                logger.error("No access to main monitor app for DNA audit.")

    def closeEvent(self, event):
        """关闭事件时保存位置"""
        self.save_window_position_qt_visual(self, "volume_details_dialog")
        event.accept()

    def hideEvent(self, event):
        """隐藏事件时保存位置 (用于该 Dialog 频繁 hide/show 的场景)"""
        self.save_window_position_qt_visual(self, "volume_details_dialog")
        super().hideEvent(event)

    def showEvent(self, event):
        """[GUI] 展现时安全恢复大小，防范 C++ 构造期 access violation"""
        super().showEvent(event)
        if self.layout():
            self.layout().activate() # ⭐ [FIX] 强制触发布局重算，确保加载完位置后视图尺寸同步填充

    def resizeEvent(self, event):
        """[GUI] 强力重写 resizeEvent，保证窗口放大缩小时，内部布局和表格大小 100% 物理同步，不留多余空白底框"""
        super().resizeEvent(event)
        if self.layout():
            self.layout().setGeometry(self.rect())



# 定义信号分类
CATEGORY_MAP = {
    "跟单信号": ["跟单", "FOLLOW", "enter_queue", "WATCHING", "VALIDATED", "就绪", "入场", "BREAKOUT_STAR", "起跳新星", "low_open_pinbar", "rising_structure", "Pinbar", "结构改善", "赛马", "重点", "终极确认", "优胜", "候选者"],
    "突破加速": ["BREAKOUT_STAR", "Fast-Track", "momentum", "breakout", "strong_auction_open", "master_momentum", "high_sideways_break", "突破", "SBC-Breakout", "🚀强势结构", "🔥趋势加速", "跟单"],
    "买入机会": ["BREAKOUT_STAR", "ma60反转启动", "BUY", "bottom_signal", "instant_pullback", "open_is_low", "low_open_high_walk", "open_is_low_volume", "nlow_is_low_volume", "low_open_breakout", "bear_trap_reversal", "early_momentum_buy"],
    "卖点预警": ["SELL", "EXIT", "top_signal", "high_drop", "bull_trap_exit", "momentum_failure", "风险", "警告", "卖出", "止损", "平仓"],
    "结构破位": ["SBC-Breakdown", "Breakdown", "断头铡刀", "严重破位", "跌破MA10", "跌破MA5", "结构派发", "破位", "momentum_failure", "⚠️结构破位"],
    "尾盘诱多": ["tail_end_trap", "尾盘诱多", "陷阱"],
    "其它信号": []
}

# 信号类型中文化与聚合映射
SIGNAL_TYPE_MAP = {
    "ALL": "全部信号",
    "Fast-Track": "极速跟单",
    "MOMENTUM": "强势动能",
    "SBC-Breakout": "结构突破",
    "SBC-Breakdown": "结构破位",
    "BREAKOUT_STAR": "起跳新星",
    "PATTERN": "形态异动",
    "ALERT": "预警信号",
    "tail_end_trap": "尾盘诱多"
}

SIGNAL_TYPE_KEYWORDS = {
    "Fast-Track": ["Fast-Track", "跟单", "Pinbar", "结构改善", "起跳新星", "赛马", "终极确认", "优胜"],
    "MOMENTUM": ["MOMENTUM", "超级动能", "动能", "加速"],
    "SBC-Breakout": ["SBC-Breakout", "突破", "强势结构", "趋势加速", "突破"],
    "SBC-Breakdown": ["SBC-Breakdown", "破位", "结构破位", "跌破", "风险", "破位"],
    "BREAKOUT_STAR": ["BREAKOUT_STAR", "起跳新星"],
    "PATTERN": ["PATTERN", "形态", "信号"],
    "tail_end_trap": ["tail_end_trap", "尾盘诱多"],
}

class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格项 [FIXED] 支持 setText 实时同步数值"""
    def __init__(self, value):
        super().__init__(str(value))
        self.update_value(value)

    def update_value(self, value):
        """解析并更新用于排序的内部数值"""
        if isinstance(value, (int, float)):
            self._value = float(value)
        else:
            # 🚀 [UPGRADE] 智能数值提取：剥离百分比、正负号以支持整体排序
            try:
                clean_val = str(value).replace('%', '').replace('+', '').strip()
                if not clean_val or clean_val == '-':
                    self._value = -999999.0
                else:
                    self._value = float(clean_val)
            except (ValueError, TypeError):
                self._value = value

    def setText(self, text):
        """同步更新内部数值，解决复用 Item 时的排序滞后问题"""
        super().setText(text)
        self.update_value(text)

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            try:
                return self._value < other._value
            except (TypeError, ValueError):
                return super().__lt__(other)
        return super().__lt__(other)

class SignalDetailDialog(QDialog):
    """信号详情弹出框"""
    def __init__(self, code, name, pattern, detail, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"信号详情 - {code} {name}")
        self.setMinimumSize(500, 300)
        layout = QVBoxLayout(self)
        
        info_label = QLabel(f"<b>股票:</b> {code} {name} | <b>信号:</b> {pattern}")
        info_label.setStyleSheet("font-size: 11pt;")
        layout.addWidget(info_label)
        
        detail_edit = QTextEdit()
        detail_edit.setPlainText(detail)
        detail_edit.setReadOnly(True)
        detail_edit.setStyleSheet("background-color: #1a1c2c; color: #ffffff; font-family: 'Consolas'; font-size: 11pt;")
        layout.addWidget(detail_edit)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        close_btn.setFixedHeight(35)
        layout.addWidget(close_btn)

class SignalDashboardPanel(QWidget, WindowMixin):
    """
    策略信号分类仪表盘
    """
    code_clicked = pyqtSignal(str, str)
    sig_bus_event = pyqtSignal(object)
    sig_heartbeat = pyqtSignal(object) # [NEW] 专门用于心跳与统计更新的信号
    sig_show_banner = pyqtSignal(str)  # [NEW] 专门用于置顶滚动预警的信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 策略信号仪表盘")
        self.setMinimumSize(400, 300)
        
        # 数据缓存
        # --- 1. 数据结构初始化 ---
        self._all_events: List[BusEvent] = []
        self._hub_alerts = [] # [NEW] 聚合预警池
        self._history_write_lock = threading.Lock() # 🛡️ [LOCK] 预警历史专属文件写盘锁，防 Windows 并发重入
        self._last_saved_hash = None # [NEW] 记录上一次成功写盘的内容哈希，用于物理拦截无变动的无效写盘
        self._alert_save_timer = QTimer(self) # [NEW] 预警历史专属防抖节流定时器
        self._alert_save_timer.setSingleShot(True)
        self._alert_save_timer.timeout.connect(self._save_alert_history)
        self.parent_app = None # [NEW] 用于跨框架(Tk/Qt)引用数据 (如 self.parent_app.df_all)
        self._alert_detail_dialog = None # [NEW] 详情对话框
        self._banner_timer = QTimer(self)
        self._banner_timer.setSingleShot(True)
        self._banner_timer.timeout.connect(lambda: self.alert_banner.setVisible(False))
        
        self.sig_show_banner.connect(self._show_alert_banner)
        
        self._stock_stats: Dict[str, Dict] = {} 
        self._sector_heat: Dict[str, int] = {}  
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        self._signal_type_counts = {k: 0 for k in SIGNAL_TYPE_MAP.keys()}
        self._signal_type_counts["ALL"] = 0
        self._stats_counters = {"follow": 0, "breakout": 0, "risk": 0, "breakdown": 0, "bull": 0, "bear": 0, "other": 0}
        self._is_updating_ui = False
        self._table_update_buffer: List[BusEvent] = [] # [NEW] UI 更新缓冲
        self._data_lock = threading.Lock() # ⭐ [NEW] 线程锁保护共享数据
        self._row_cache = {} # {table_obj: {code: table_item_at_col2}} 用于 O(1) 查找现有行
        
        # [NEW] 极速渲染所需常量与预分配对象
        self._ROLE_TEXT    = Qt.ItemDataRole.UserRole + 100
        self._ROLE_COLOR   = Qt.ItemDataRole.UserRole + 101
        self._ROLE_BOLD    = Qt.ItemDataRole.UserRole + 102
        self._ROLE_DATA    = Qt.ItemDataRole.UserRole + 103
        self._ROLE_BG      = Qt.ItemDataRole.UserRole + 104
        self._ROLE_NUMERIC = Qt.ItemDataRole.UserRole + 105
        self._ROLE_SEARCH_BLOB = Qt.ItemDataRole.UserRole + 106
        
        self._font_normal = QFont()
        self._font_normal.setBold(False)
        self._font_bold = QFont()
        self._font_bold.setBold(True)
        
        _ALL_COLOR_KEYS = [
            "#ff4444", "#44ff44", "#ffffff", "#FFD700", "#00ffff",
            "#ffff00", "#ff4500", "#FF4500", "#00ff88", "#00ff00",
            "#00bfff", "#888888", "#ffaa00", "#ff0000", "#4B0082", "#ff00ff"
        ]
        self._BRUSH_PRESET = {k: QBrush(QColor(k)) for k in _ALL_COLOR_KEYS}
        self._BRUSH_PRESET["transparent"] = QBrush(QColor(0, 0, 0, 0))
        self._BRUSH_PRESET["gold_bg"] = QBrush(QColor(100, 80, 0, 100))
        self._BRUSH_PRESET["alert_bg"] = QBrush(QColor("#4B0082"))
        self._BRUSH_PRESET["highlight_bg"] = QBrush(QColor(255, 127, 80, 50))
        
        # [NEW] 排序防抖定时器
        self._sort_timer = QTimer(self)
        self._sort_timer.setSingleShot(True)
        self._sort_timer.setInterval(100)
        self._sort_timer.timeout.connect(self._trigger_sorted_refresh)
        
        # [NEW] 决策引擎相关
        self._decision_queue_data: List[dict] = []
        self._sector_focus_data: List[dict] = []
        self._engine_ctrl = None
        
        # --- 2. 组件与窗口初始化 ---
        self._vol_dialog = VolumeDetailsDialog(self)
        self._vol_dialog.code_clicked.connect(self._on_vol_code_clicked)
        self.setWindowFlags(Qt.WindowType.Window)
        
        # [PERF] 列宽持久化防抖 Timer：避免 sectionResized 每次触发磁盘 IO
        self._save_ui_timer = QTimer(self)
        self._save_ui_timer.setSingleShot(True)
        self._save_ui_timer.setInterval(5000)  # 5s 防抖，合并连续列宽调整为单次写入
        self._save_ui_timer.timeout.connect(self._save_ui_state)

        # --- 3. UI 渲染 (依赖上述数据结构) ---
        self._init_ui()
        self.load_window_position_qt(self, "signal_dashboard_panel", default_width=1100, default_height=750)
        
        # [NEW] 恢复历史预警信息
        self._load_alert_history()
        
        self._restore_ui_state()
        
        # --- 4. 总线连接 ---
        self._setup_bus_connection()
        # ⭐ [FIX] 显式指定 QueuedConnection，确保跨线程信号在 GUI 线程处理
        self.sig_bus_event.connect(self._safe_process_event, Qt.ConnectionType.QueuedConnection)
        self.sig_heartbeat.connect(self._on_heartbeat_received_gui, Qt.ConnectionType.QueuedConnection)
        
        # [NEW] 核心渲染调度器：彻底解决心跳堆积引发的“无限刷新”与卡死
        self._render_scheduler = QTimer(self)
        self._render_scheduler.setInterval(500) # 500ms 刷新率
        self._render_scheduler.timeout.connect(self._on_render_timer_timeout)
        self._render_scheduler.start()
        self._engine_dirty = False 

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats_display)
        self._stats_timer.start(2000)
        
        self._batch_timer = QTimer(self)
        self._batch_timer.timeout.connect(self._process_batch_signals)
        self._batch_timer.start(3000)

        # [FIX] 废弃原有的定时器机制，改为监听 MonitorTK 发出的心跳信号触发 _update_engine_views
        # 这确保了 UI 刷新能够 100% 对齐数据聚合周期，避免无数据更新时的空转或脏检查开销
        logger.info(f"🚀 SignalDashboard 决策引擎同步已启动，变更为心跳驱动模式")
        
        # [MOD] 状态栏 UI 布局优化：废除轮播模式，改为固定/滚动综合展示
        self._carousel_idx = 0
        self._carousel_messages = []
        
        # 监听 Tab 切换，实现“tab当前点击查看的视图的统计信息”实时更新
        self.tabs.currentChanged.connect(self._update_stats_display)

        # ⭐ [NEW] 统一将主仪表盘内部的所有水平和垂直滚动条调整为极窄样式，消除厚重感
        self.setStyleSheet("""
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 100);
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 100);
                min-width: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 150);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)

    def stop(self):
        """停止所有计时器和订阅，释放资源"""
        try:
            if hasattr(self, '_stats_timer') and self._stats_timer: 
                self._stats_timer.stop()
        except Exception: pass
        
        try:
            if hasattr(self, '_batch_timer') and self._batch_timer: 
                self._batch_timer.stop()
        except Exception: pass

        try:
            if hasattr(self, '_search_timer') and self._search_timer: 
                self._search_timer.stop()
        except Exception: pass
        
        try:
            bus = get_signal_bus()
            if bus:
                bus.unsubscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_RISK, self._on_signal_received)
                bus.unsubscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
                bus.unsubscribe(SignalBus.EVENT_STRATEGIC_TREND, self._on_signal_received)
        except Exception: pass
        
        if hasattr(self, '_table_update_buffer'):
            self._table_update_buffer.clear()
        
    def closeEvent(self, event):
        self.save_window_position_qt_visual(self, "signal_dashboard_panel")
        self._save_ui_state()
        self.stop()
        event.accept()

    def _collect_ui_state(self) -> dict:
        """收集当前 UI 布局状态（纯内存，无副作用）"""
        if not hasattr(self, 'tables') or not self.tables:
            return {}

        data = {}

        for name, table in self.tables.items():
            try:
                clean_name = (
                    name.replace("🌟 ", "")
                        .replace("🐉 ", "")
                        .replace("🔥 ", "")
                )

                data[f'table_state_{clean_name}'] = (
                    table.horizontalHeader()
                        .saveState()
                        .toHex()
                        .data()
                        .decode()
                )

            except Exception:
                continue

        return data


    def _save_ui_state(self):
        """高性能保存表格布局状态（Dirty Check + 防重复写盘）"""
        if not hasattr(self, 'tables') or not self.tables:
            return

        try:
            new_state = self._collect_ui_state()

            if not new_state:
                return

            # -----------------------------
            # Dirty Check：无变化直接跳过
            # -----------------------------
            if new_state == getattr(self, '_last_saved_ui_state', None):
                return

            self._last_saved_ui_state = dict(new_state)

            config_file = WINDOW_CONFIG_FILE

            # -----------------------------
            # 读取旧配置（仅一次）
            # -----------------------------
            full_data = {}

            if os.path.exists(config_file):
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        full_data = json.load(f)
                except Exception:
                    full_data = {}

            # -----------------------------
            # Merge 当前 Section
            # -----------------------------
            full_data[SETTINGS_SECTION] = new_state

            # -----------------------------
            # 原子写入（防止配置损坏）
            # -----------------------------
            with _CONFIG_FILE_LOCK:
                # 重新读取一次以防在保存期间被其他组件更新了根级别的 key
                if os.path.exists(config_file):
                    try:
                        with open(config_file, "r", encoding="utf-8") as f:
                            current_all = json.load(f)
                            # 仅更新我们负责的 Section，保留其他 root keys (如 market_alert_detail_header_v2)
                            current_all[SETTINGS_SECTION] = new_state
                            full_data = current_all
                    except: pass

                tmp_file = config_file + ".tmp"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(full_data, f, ensure_ascii=False, indent=2)

                os.replace(tmp_file, config_file)

            logger.debug("UI state saved.")

        except Exception as e:
            logger.error(f"Failed to save UI state: {e}")

    def _restore_ui_state(self):
        """恢复表格布局设置"""
        try:
            config_file = WINDOW_CONFIG_FILE
            if not os.path.exists(config_file): return
            
            with _CONFIG_FILE_LOCK:
                with open(config_file, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
            
            ui_state = full_data.get(SETTINGS_SECTION)
            if not ui_state: return
            
            for name, table in self.tables.items():
                clean_name = name.replace("🌟 ", "").replace("🐉 ", "").replace("🔥 ", "")
                state_key = f'table_state_{clean_name}'
                if state_key in ui_state:
                    table.horizontalHeader().restoreState(QByteArray.fromHex(ui_state[state_key].encode()))
            # [PERF] 最稳方案：延迟一个 event-loop 再采集快照
            # 确保 restoreState() 引引发的异步布局事件全部稳定后再建立基准，防止启动即触发 save_ui
            QTimer.singleShot(0, lambda: setattr(self, '_last_saved_ui_state', self._collect_ui_state()))
        except Exception as e:
            logger.error(f"Failed to restore UI state: {e}")

    def _limit_table_column_widths(self, table: QTableWidget):
        """
        [🚀 极致性能] 节流版的列宽限制。
        强制对特定列施加最大宽度限制，防止自适应伸缩导致 UI 崩溃。
        """
        # [NEW] 节流保护：如果 2 秒内刚限制过，则跳过，减少高频刷新时的布局重算
        last_limit = getattr(table, '_last_limit_ts', 0)
        curr_ts = time.time()
        if curr_ts - last_limit < 2.0:
             return
        table._last_limit_ts = curr_ts

        header = table.horizontalHeader()
        # 先触发一次自适应 (如果当前是自适应模式)
        # table.resizeColumnsToContents() # 慎用，可能会导致死循环或性能抖动
        
        column_count = table.columnCount()
        for i in range(column_count):
            h_text = table.horizontalHeaderItem(i).text() if table.horizontalHeaderItem(i) else ""
            curr_width = table.columnWidth(i)
            
            # 设定限制规则
            max_w = 150 # 默认上限
            if h_text in ["所属板块", "板块名称"]:
                max_w = 120
            elif h_text in ["形态/信号", "形态详情", "详情", "捕捉理由", "跟风明细", "标签"]:
                max_w = 250
            elif h_text in ["代码", "时间", "评级"]:
                max_w = 80
            
            if curr_width > max_w:
                # 如果超过限制，将模式改为 Interactive（允许手动调整）或 Fixed 
                # 这里设为 Interactive 并强制指定宽度
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                table.setColumnWidth(i, max_w)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # [NEW] 顶部全宽预警跑马灯 (最显眼位置，置于主布局最上方)
        self.alert_banner = QLabel("")
        self.alert_banner.setFixedHeight(30)
        self.alert_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert_banner.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #800000, stop:0.5 #ff0000, stop:1 #800000);
            color: #ffff00; font-weight: bold; font-size: 11pt;
            border-bottom: 2px solid #ff4444; 
        """)
        self.alert_banner.setVisible(False)
        layout.addWidget(self.alert_banner)
        
        self.header = QFrame()
        self.header.setMinimumHeight(60)
        self.header.setStyleSheet("QFrame { background-color: #1a1c2c; border: 1px solid #333; border-radius: 6px; } QLabel { color: #ddd; }")
        header_layout = QHBoxLayout(self.header)
        
        temp_frame = QFrame()
        temp_frame.setStyleSheet("background: transparent; border: none;")
        temp_lay = QVBoxLayout(temp_frame)
        self.temp_label = QLabel("市场温度: --")
        self.temp_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        self.market_breadth_label = QLabel("📊 上涨:-- 下跌:--")
        self.vol_stat_label = QLabel("🚀 放量:--")
        self.vol_stat_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_stat_label.mousePressEvent = self._on_market_breadth_clicked 
        self.ls_ratio_label = QLabel("多空比: --")
        
        temp_lay.addWidget(self.temp_label)
        
        # [NEW] 市场温度进度条
        self.temp_bar = QProgressBar()
        self.temp_bar.setRange(0, 100)
        self.temp_bar.setValue(50)
        self.temp_bar.setTextVisible(False)
        self.temp_bar.setFixedHeight(8)
        self.temp_bar.setMinimumWidth(120)
        self.temp_bar.setStyleSheet("""
            QProgressBar {
                background-color: #333;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5bc0de, stop:0.5 #f0ad4e, stop:1 #d9534f);
                border-radius: 4px;
            }
        """)
        temp_lay.addWidget(self.temp_bar)
        
        # ⭐ [🚀 极致性能] 预缓存笔刷与颜色对象，消除亚毫秒级渲染热点内的动态分配
        self._brushes = {
            "bull": QBrush(QColor("#ff4444")),
            "bear": QBrush(QColor("#44ff44")),
            "dragon": QBrush(QColor("#FFD700")),
            "warn": QBrush(QColor("#FF4500")),
            "gold_bg": QBrush(QColor(100, 80, 0, 100)),
            "transparent": QBrush(QColor(0, 0, 0, 0)),
            "alert_bg": QBrush(QColor("#4B0082")),
            "highlight_bg": QBrush(QColor(255, 127, 80, 50)),
            "flash": QBrush(QColor(255, 255, 0, 60)),
            "#ff0000": QBrush(QColor("#ff0000")),
            "#ffaa00": QBrush(QColor("#ffaa00")),
            "#00ff88": QBrush(QColor("#00ff88")),
            "#ffff00": QBrush(QColor("#ffff00")),
            "#00ffff": QBrush(QColor("#00ffff")),
            "#888888": QBrush(QColor("#888888")),
            "#FFD700": QBrush(QColor("#FFD700")),
            "#ff4444": QBrush(QColor("#ff4444")),
            "#44ff44": QBrush(QColor("#44ff44")),
            "#ff4500": QBrush(QColor("#ff4500")),
            "#ff00ff": QBrush(QColor("#ff00ff")),
        }
        # [PERF] 预缓存所有高频颜色对象，消除每次心跳 ~240 次 QColor(str) C++ 解析开销
        self._colors = {
            "#ff4444": QColor("#ff4444"),
            "#44ff44": QColor("#44ff44"),
            "#FFD700": QColor("#FFD700"),
            "#00ffff": QColor("#00ffff"),
            "#ffff00": QColor("#ffff00"),
            "#ffffff": QColor("#ffffff"),
            "#ff4500": QColor("#ff4500"),
            "#FF4500": QColor("#FF4500"),
            "#00ff88": QColor("#00ff88"),
            "#00ff00": QColor("#00ff00"),
            "#00bfff": QColor("#00bfff"),
            "#888888": QColor("#888888"),
            "#ffaa00": QColor("#ffaa00"),
            "#ff0000": QColor("#ff0000"),
            "#ff00ff": QColor("#ff00ff"),
        }

        temp_lay.addWidget(self.market_breadth_label)
        temp_lay.addWidget(self.vol_stat_label)
        temp_lay.addWidget(self.ls_ratio_label)
        header_layout.addWidget(temp_frame)
        
        # [NEW] 增加点击联动详情
        temp_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        temp_frame.mousePressEvent = self._on_market_temp_clicked

        header_layout.addSpacing(20)
        
        # [NEW] 指数网格显示
        self.index_frame = QFrame()
        self.index_frame.setMinimumWidth(150)
        self.index_frame.setStyleSheet("background: #111; border: 0.5px solid #444; border-radius: 5px; padding: 2px;")
        idx_grid = QGridLayout(self.index_frame)
        idx_grid.setContentsMargins(5, 5, 5, 5)
        idx_grid.setSpacing(5)
        
        self.idx_labels = {}
        indices_list = [("sh000001", "上证"), ("sz399001", "深证"), ("sz399006", "创业"), ("sh000688", "科创")]
        for i, (code, name) in enumerate(indices_list):
            nl = QLabel(f"{name}")
            nl.setStyleSheet("color: #aaa; font-size: 9pt;")
            vl = QLabel("--%")
            vl.setStyleSheet("color: #ddd; font-family: 'Consolas'; font-size: 10pt; font-weight: bold;")
            idx_grid.addWidget(nl, i, 0)
            idx_grid.addWidget(vl, i, 1)
            self.idx_labels[name] = vl
            
        header_layout.addWidget(self.index_frame)
        
        header_layout.addSpacing(30)
        self.cards = {}
        # [MOD] 增加 "alert_hub" 预警卡片，放在第一位
        card_configs = [
            ("alert_hub", "📡 预警", "#FF4444"), # [NEW] 聚合预警卡片
            ("dragon", "🐉 龙头池", "#FFD700"),
            ("follow", "跟单信号", "#FFD700"), 
            ("breakout", "突破加速", "#FF4500"), 
            ("trap", "尾盘诱多", "#1E90FF"),
            ("risk", "风险卖出", "#00FA9A"), 
            ("breakdown", "结构破位", "#87CEFA"), 
            ("other", "其它信号", "#A9A9A9"),
        ]
        for key, name, color in card_configs:
            card = QFrame()
            card.setMinimumWidth(60)
            card.setMaximumWidth(200)
            card.setStyleSheet(f"QFrame {{ border: 1px solid {color}44; border-radius: 8px; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {color}11, stop:1 {color}22); }}")
            c_lay = QVBoxLayout(card)
            n_lbl = QLabel(name)
            n_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n_lbl.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: bold; border: none; background: transparent;")
            v_lbl = QLabel("0")
            v_lbl.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: #ffffff; border: none; background: transparent;")
            v_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            c_lay.addWidget(n_lbl)
            c_lay.addWidget(v_lbl)
            header_layout.addWidget(card)
            self.cards[key] = v_lbl
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda e, k=key: self._on_card_clicked(k)
            
        header_layout.addStretch()
        sector_frame = QFrame()
        sector_frame.setMinimumWidth(100)
        sector_frame.setMaximumWidth(350)
        sector_frame.setStyleSheet("background: transparent; border: none;")
        sector_lay = QVBoxLayout(sector_frame)
        h_lbl = QLabel("🔥 热门板块")
        h_lbl.setStyleSheet("color: #FFA500; font-weight: bold; font-size: 10pt;")
        sector_lay.addWidget(h_lbl)
        self.hot_sectors_label = QLabel("等待数据...")
        self.hot_sectors_label.setWordWrap(True)
        self.hot_sectors_label.setStyleSheet("color: #00FFCC; font-family: 'Consolas'; font-size: 10pt; background: transparent;")
        self.hot_sectors_label.setOpenExternalLinks(False)
        self.hot_sectors_label.linkActivated.connect(self._filter_by_sector)
        sector_lay.addWidget(self.hot_sectors_label)
        header_layout.addWidget(sector_frame)
        layout.addWidget(self.header)
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 1px solid #333; background: #0d121f; } QTabBar::tab { background: #1a1c2c; color: #888; padding: 4px 12px; font-size: 9pt; border: 1px solid #333; } QTabBar::tab:selected { background: #2a2d42; color: #fff; border-bottom-color: #00ff88; font-weight: bold; }")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索代码/名称/形态...")
        self.search_input.setFixedWidth(240)
        self.search_input.setClearButtonEnabled(True) # 内置原生清空按钮
        self.search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.customContextMenuRequested.connect(self._on_search_context_menu)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        
        # [NEW] 信号类型下拉过滤
        self.type_filter = QComboBox()
        self.type_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents) # 自适应宽度
        self.type_filter.setStyleSheet("QComboBox { background: #1a1c2c; color: #fff; border: 1px solid #333; padding: 2px 10px 2px 5px; } QComboBox QAbstractItemView { background: #1a1c2c; color: #fff; selection-background-color: #2a2d42; }")
        self._refresh_type_filter_items()
        self.type_filter.currentTextChanged.connect(lambda: self._on_search_text_changed(self.search_input.text()))
        
        # 搜索与过滤容器
        search_lay = QHBoxLayout()
        search_lay.setContentsMargins(5, 5, 5, 5)
        search_lay.addWidget(self.type_filter)
        search_lay.addWidget(self.search_input)
        
        # [MOD] 原清空按钮重构为：[🛠️ 引擎执行] (全链路逻辑触发)
        self.manual_run_btn = QPushButton("🛠️ 引擎执行")
        self.manual_run_btn.setFixedWidth(80)
        self.manual_run_btn.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ff8c00, stop:1 #ff4500); 
                color: #fff; 
                border: 1px solid #ff4500; 
                border-radius: 4px; 
                padding: 3px; 
                font-size: 8.5pt; 
                font-weight: bold; 
            } 
            QPushButton:hover { background: #ff4500; border-color: #ff0000; }
            QPushButton:pressed { background: #cc3700; }
        """)
        self.manual_run_btn.clicked.connect(self._on_engine_manual_run)

        # [NEW] DNA审计按钮
        self.btn_dna_audit_signal = QPushButton("🧬 DNA审计")
        self.btn_dna_audit_signal.setFixedWidth(85)
        self.btn_dna_audit_signal.setStyleSheet("""
            QPushButton { 
                background: #2C2C2E; 
                color: #ffffff; 
                border: 1px solid #555; 
                border-radius: 4px; 
                padding: 3px; 
                font-size: 8.5pt; 
                font-weight: bold; 
            } 
            QPushButton:hover { background: #3A3A3C; border-color: #00ff88; }
        """)
        self.btn_dna_audit_signal.clicked.connect(self._run_dna_audit_selected)
        search_lay.addWidget(self.btn_dna_audit_signal)

        search_lay.addStretch()
        
        # [RESTORED] 右侧统计标签 (联动全部信号)
        self.total_stat_label = QLabel("全部: 0")
        self.total_stat_label.setStyleSheet("color: #00ffff; font-family: 'Consolas'; font-size: 14pt; font-weight: bold;")
        self.total_stat_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.total_stat_label.mousePressEvent = lambda e: self._on_card_clicked("ALL")
        search_lay.addWidget(self.total_stat_label)

        # [NEW] 重置按钮
        self.reset_btn = QPushButton("♻️ 重置")
        self.reset_btn.setFixedWidth(70)
        self.reset_btn.setStyleSheet("QPushButton { background: #333; color: #aaa; border: 1px solid #444; border-radius: 4px; padding: 3px; font-weight: bold; } QPushButton:hover { background: #444; color: #fff; border-color: #666; }")
        self.reset_btn.clicked.connect(self._reset_signals)
        search_lay.addWidget(self.reset_btn)
        
        # 组装右上角控制区域 (类型过滤 + 搜索 + 清空 + 重置)
        corner_widget = QWidget()
        corner_lay = QHBoxLayout(corner_widget)
        corner_lay.setContentsMargins(0, 0, 10, 0)
        corner_lay.setSpacing(5)
        corner_lay.addWidget(self.type_filter)
        corner_lay.addWidget(self.search_input)
        corner_lay.addWidget(self.btn_dna_audit_signal)
        corner_lay.addWidget(self.manual_run_btn)
        corner_lay.addWidget(self.reset_btn)
        self.tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)
        self.tables: Dict[str, QTableWidget] = {}

        # [MOD] 恢复页签：保留基础页签，并将预警中枢置后以供查看效果
        all_tabs = ["🌟 决策队列", "🐉 龙头追踪", "🌐 战略趋势", "🔥 板块热力", "全部信号", "跟单信号", "突破加速", "尾盘诱多", "卖点预警", "结构破位", "买入机会", "其它信号", "📡 市场预警"]
        for tab_name in all_tabs:
            if tab_name == "📡 市场预警":
                table = self._create_alert_hub_table()
            elif tab_name == "🌟 决策队列":
                table = self._create_decision_table()
            elif tab_name == "🐉 龙头追踪":
                table = self._create_dragon_table()
            elif tab_name == "🌐 战略趋势":
                table = self._create_strategic_table()
            elif tab_name == "🔥 板块热力":
                table = self._create_sector_table()
            else:
                table = self._create_signal_table()
            
            self.tables[tab_name] = table
            # [INTERACTIVE-FIX] 为引擎表注入初始排序锚点，消除“冷启动点击无反应”的痛点
            if tab_name in ["🌟 决策队列", "🐉 龙头追踪", "🌐 战略趋势", "🔥 板块热力", "📡 市场预警"]:
                table._sort_col = 0
                table._sort_order = Qt.SortOrder.DescendingOrder
                table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder)
            self.tabs.addTab(table, tab_name)
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        
        # --- 底部状态栏布局优化 ---
        self.status_container = QFrame()
        self.status_container.setStyleSheet("QFrame { background-color: #1a1c2c; border-top: 1px solid #333; } QLabel { color: #888; font-size: 9pt; }")
        status_layout = QHBoxLayout(self.status_container)
        status_layout.setContentsMargins(10, 2, 10, 2)
        status_layout.setSpacing(15)

        self.status_label = QLabel("就绪")
        # [NEW] 实时更新时间标签，修复 AttributeError
        self.last_update_label = QLabel("--:--:--")
        self.last_update_label.setStyleSheet("color: #666; font-family: 'Consolas';")
        
        self.stats_info_label = QLabel("跟单: 0 | 突破: 0 | 尾盘: 0 | 全部: 0")
        self.stats_info_label.setStyleSheet("color: #00ff88; font-family: 'Microsoft YaHei'; font-weight: bold;")

        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.last_update_label) # 放置在中间或右侧
        status_layout.addWidget(self.stats_info_label)

        layout.addWidget(self.status_container)
        
    def _refresh_type_filter_items(self):
        """刷新下拉框项目（带计数）"""
        current_text = self.type_filter.currentText()
        # 提取分类名称 (不含括号)
        current_cat = current_text.split(' (')[0] if ' (' in current_text else current_text
        
        # [FIX] 下拉框中的数量统计，必须扫描实际可视表以保证所点即所得 (消除因多重覆写去重引发的 Phantom空项)
        table = getattr(self, "tables", {}).get("全部信号")
        counts = {k: 0 for k in SIGNAL_TYPE_MAP.keys()}
        if table is not None:
            counts["ALL"] = table.rowCount()
            for r in range(table.rowCount()):
                pattern_item = table.item(r, 4)
                if pattern_item:
                    raw_pattern = str(pattern_item.data(Qt.ItemDataRole.UserRole) or pattern_item.text())
                    matched_type = "ALERT"
                    for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                        if any(kw.lower() in raw_pattern.lower() for kw in keywords):
                            matched_type = eng_key
                            break
                    if matched_type in counts:
                        counts[matched_type] += 1
                    else:
                        counts[matched_type] = 1

        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        for eng_key, ch_name in SIGNAL_TYPE_MAP.items():
            count = counts.get(eng_key, 0)
            item_text = f"{ch_name} ({count})" if eng_key != "ALL" else f"{ch_name} ({counts['ALL']})"
            self.type_filter.addItem(item_text, eng_key)
            if ch_name == current_cat:
                self.type_filter.setCurrentText(item_text)
        self.type_filter.blockSignals(False)

    def _create_alert_hub_table(self) -> QTableWidget:
        table = QTableWidget()
        # 基础样式配置
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; alternate-background-color: #161b29; }")
        
        cols = ["时间", "级别", "类型", "板块/内容", "活跃度", "详情"]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        # 预设列宽
        table.setColumnWidth(0, 80)
        table.setColumnWidth(1, 60)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 150)
        table.setColumnWidth(4, 100)
        
        h = table.horizontalHeader()
        h.setSectionsClickable(True)
        # [NEW] 绑定表头点击，实现手动排序联动
        h.sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        
        # [NEW] 绑定双击详情查看 (使用 cellDoubleClicked 传递 row, col)
        table.cellDoubleClicked.connect(self._on_alert_double_clicked)
        # [NEW] 绑定单击与选择变化，实现单击任意列/键盘上下键切换时，自动联动第一个股票
        table.cellClicked.connect(self._on_alert_cell_clicked)
        table.itemSelectionChanged.connect(self._on_alert_selection_changed)
        
        # [NEW] 绑定回车键快捷键，按下回车键时双击打开详情页
        from PyQt6.QtGui import QShortcut, QKeySequence
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), table)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self._on_alert_enter_pressed)
        
        shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), table)
        shortcut_enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut_enter.activated.connect(self._on_alert_enter_pressed)
        
        return table

    def _create_signal_table(self) -> QTableWidget:
        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels(["时间", "评级", "代码", "名称", "形态/信号", "详情", "次数", "得分"])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        
        # [MOD] 设置默认按时间(第0列)倒序排列
        table.setSortingEnabled(False)
        table.horizontalHeader().setSectionsClickable(True)  # Qt 内部会关闭，必须显式恢复
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder)
        table.horizontalHeader().sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        header = table.horizontalHeader()
        # [PERF] Interactive 模式：不再随每次 setText 触发全列像素重测量（原 ResizeToContents 杀手）
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch) # 详情自动拉伸
        # 首次数据就位后执行一次自适应
        QTimer.singleShot(800, lambda: table.resizeColumnsToContents() if table.rowCount() > 0 else None)
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)

        # [PERF] 防抖持久化：sectionResized 不再直接写磁盘，合并为 2s 后单次写入
        table.horizontalHeader().sectionResized.connect(lambda: self._save_ui_timer.start())
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        
        # [NEW] A3: 列映射缓存
        table._col_map = {table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())}
        return table

    def _create_decision_table(self) -> QTableWidget:
        """创建决策队列表"""
        columns = ["时间", "优先级", "状态", "代码", "名称", "形态类别", "所属板块", "现价", "建议价", "周期涨变", "DFF动量", "捕捉理由"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)
        table.horizontalHeader().setSectionsClickable(True)  # Qt 内部会关闭，必须显式恢复
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(0, Qt.SortOrder.DescendingOrder) # 默认按时间倒序
        table.horizontalHeader().sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        # [PERF] Interactive 模式
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 理由拉伸
        QTimer.singleShot(800, lambda: table.resizeColumnsToContents() if table.rowCount() > 0 else None)
        
        # [MOD] 统一单击与双击联动处理器
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)

        # [PERF] 防抖持久化
        table.horizontalHeader().sectionResized.connect(lambda: self._save_ui_timer.start())
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        
        # [NEW] A3: 列映射缓存
        table._col_map = {table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())}
        return table

    def _create_sector_table(self) -> QTableWidget:
        """创建板块热力表"""
        columns = ["板块名称", "热度", "竞分", "类型", "龙头", "龙头名称", "龙头涨幅", "跟涨%", "跟风明细", "更新时间"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)  # [PERF] 永远关闭 Qt 排序，Python 侧排序
        table.horizontalHeader().setSectionsClickable(True)  # Qt 内部会关闭，必须显式恢复
        table.horizontalHeader().sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        # [PERF] Interactive 模式
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 跟风明细拉伸
        QTimer.singleShot(800, lambda: table.resizeColumnsToContents() if table.rowCount() > 0 else None)
        
        # [MOD] 统一单击与双击联动处理器
        table.cellClicked.connect(self._on_sector_table_clicked)
        table.cellDoubleClicked.connect(self._on_sector_table_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)

        # [PERF] 防抖持久化
        table.horizontalHeader().sectionResized.connect(lambda: self._save_ui_timer.start())
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        
        # [NEW] A3: 列映射缓存
        table._col_map = {table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())}
        return table

    def _create_dragon_table(self) -> QTableWidget:
        """创建龙头追踪列表"""
        columns = ["状态", "代码", "名称", "所属板块", "现点%", "累计涨%", "追踪天", "新高天", "DFF动量", "VWAP", "更新时间", "标签"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)  # [PERF] 永远关闭 Qt 排序，Python 侧排序
        table.horizontalHeader().setSectionsClickable(True)  # Qt 内部会关闭，必须显式恢复
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(5, Qt.SortOrder.DescendingOrder) # 默认按累跌倒序
        table.horizontalHeader().sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        # [PERF] Interactive 模式
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 标签拉伸
        QTimer.singleShot(800, lambda: table.resizeColumnsToContents() if table.rowCount() > 0 else None)
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)

        # [PERF] 防抖持久化
        table.horizontalHeader().sectionResized.connect(lambda: self._save_ui_timer.start())
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        
        # [NEW] A3: 列映射缓存
        table._col_map = {table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())}
        return table

    def _create_strategic_table(self) -> QTableWidget:
        """创建战略大格局趋势表"""
        columns = ["趋势类型", "代码", "名称", "阶段", "所属板块", "战略分", "结构分", "共振分", "更新时间", "核心理由"]
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(False)  # [PERF] 永远关闭 Qt 排序，Python 侧排序
        table.horizontalHeader().setSectionsClickable(True)  # Qt 内部会关闭，必须显式恢复
        table.horizontalHeader().setSortIndicatorShown(True)
        table.horizontalHeader().setSortIndicator(5, Qt.SortOrder.DescendingOrder) # 默认按战略分倒序
        table.horizontalHeader().sectionClicked.connect(lambda idx: self._on_engine_header_clicked(table, idx))
        table.setStyleSheet("QTableWidget { background-color: #0d121f; color: #ffffff; }")
        
        header = table.horizontalHeader()
        # [PERF] Interactive 模式
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(columns)-1, QHeaderView.ResizeMode.Stretch) # 理由拉伸
        QTimer.singleShot(800, lambda: table.resizeColumnsToContents() if table.rowCount() > 0 else None)
        
        table.cellClicked.connect(self._on_cell_clicked)
        table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection_changed)

        # [PERF] 防抖持久化
        table.horizontalHeader().sectionResized.connect(lambda: self._save_ui_timer.start())
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        return table

    def _on_sector_table_clicked(self, row, col):
        """板块表单击联动：同步龙头 K 线"""
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                t = header.text()
                if t == "龙头": code_col = i
                elif t == "龙头名称": name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it and c_it.text():
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

    def _on_sector_table_double_clicked(self, row, col):
        """板块表双击：寻找该行龙头并复制到剪贴板，随后发送联动"""
        table = self.tables.get("🔥 板块热力")
        if not table: return
        item = table.item(row, 4)
        name_item = table.item(row, 5)
        if item and item.text():
            code = item.text()
            name = name_item.text() if name_item else ""
            
            # [NEW] 双击复制功能
            header = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
            if header in ["龙头", "龙头名称"]:
                clipboard = QApplication.clipboard()
                clipboard.setText(code)
                self.status_label.setText(f"📋 龙头代码 {code} ({name}) 已复制")
                
            self.code_clicked.emit(code, name)

    def _setup_bus_connection(self):
        bus = get_signal_bus()
        bus.subscribe(SignalBus.EVENT_PATTERN, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_ALERT, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_RISK, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_STRATEGIC_TREND, self._on_signal_received)
        bus.subscribe(SignalBus.EVENT_HEARTBEAT, self._on_heartbeat_received)
        bus.subscribe(SignalBus.EVENT_MARKET_ALERT, self._on_signal_received)
        history = bus.get_history(limit=500) # [UPGRADE] 增加初始化回溯深度至 500 条
        for event in history: self._process_event(event, update_ui=False)
        self._refresh_all_tables()

    def _on_heartbeat_received(self, event: BusEvent):
        """[BACKGROUND THREAD] 仅发射信号，不触碰任何 Qt 对象"""
        self.sig_heartbeat.emit(event)

    def _on_heartbeat_received_gui(self, event: BusEvent):
        """[GUI THREAD] 接收心跳，仅设置脏位与轻量数据更新，不直接触发耗时渲染"""
        try:
            # 1. 更新最后同步时间
            self._update_last_sync_time()

            # 2. 更新市场统计数据
            if event.source == "market_stats" and isinstance(event.payload, dict):
                self._market_stats = event.payload
                # 统计数据脏位（状态栏更新）
                self._stats_dirty = True
            
            # 3. 设置引擎视图脏位
            self._engine_dirty = True

        except Exception as e:
            logger.exception(f"❌ [DASHBOARD] Heartbeat GUI process failed: {e}")

    def _on_render_timer_timeout(self):
        """[GUI THREAD] 渲染调度器：以固定频率消费脏位，确保在大规模数据或心跳洪水时 UI 依然流畅"""
        # 1. 处理引擎视图刷新
        if self._engine_dirty:
            self._engine_dirty = False
            self._update_engine_views()

        # 2. 处理统计状态栏刷新 (如果需要)
        if getattr(self, "_stats_dirty", False):
            self._stats_dirty = False
            self._update_stats_display()

    def _update_last_sync_time(self):
        self.last_update_label.setText(f"{datetime.now().strftime('%H:%M:%S')} (实时)")

    # --- [NEW] 决策引擎同步渲染逻辑 ---
    def _on_engine_header_clicked(self, table, col_idx):
        """表头点击：极致简化交互，确保点击后数据立即产生物理位移"""
        cur_col = getattr(table, "_sort_col", -1)
        cur_order = getattr(table, "_sort_order", Qt.SortOrder.DescendingOrder)

        # 核心逻辑：如果是当前列，则翻转；如果是新列，则强制切换为升序
        # 理由：引擎默认都是降序排好的，点新列变升序能保证 100% 看到数据变化
        if col_idx == cur_col:
            new_order = (Qt.SortOrder.AscendingOrder 
                         if cur_order == Qt.SortOrder.DescendingOrder 
                         else Qt.SortOrder.DescendingOrder)
        else:
            new_order = Qt.SortOrder.AscendingOrder

        table._sort_col = col_idx
        table._sort_order = new_order

        # 立即同步视觉指示器并触发排序任务
        table.horizontalHeader().setSortIndicator(col_idx, new_order)
        self._sort_timer.start()

    def _sort_table_python(self, table, col_idx, sort_order):
        """[NUCLEAR-PERF] 核弹级排序优化：物理脱离布局引擎与模型通知"""
        if getattr(table, "_is_sorting_locked", False): return
        table._is_sorting_locked = True
        
        import gc
        gc.disable()
        from PyQt6.QtWidgets import QHeaderView
        from PyQt6.QtCore import QModelIndex
        
        hh = table.horizontalHeader()
        vh = table.verticalHeader()
        model = table.model()
        
        # 1. 物理屏蔽布局引擎
        orig_modes = [hh.sectionResizeMode(j) for j in range(table.columnCount())]
        for j in range(table.columnCount()): hh.setSectionResizeMode(j, QHeaderView.ResizeMode.Interactive)

        # 2. 彻底切断通知流
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.setUpdatesEnabled(False)
        table.viewport().setUpdatesEnabled(False)
        hh.setUpdatesEnabled(False)
        vh.setUpdatesEnabled(False)

        # 3. 开启模型重置闸门 (此期间所有 View 停止观察)
        if model: model.beginResetModel()

        try:
            with timed_ctx(f"_sort_table_python({table.rowCount()})", warn_ms=200):
                row_count = table.rowCount()
                col_count = table.columnCount()
                if row_count <= 1: return
                reverse = (sort_order == Qt.SortOrder.DescendingOrder)

                # Phase 1: Extraction
                with timed_ctx("  [Phase 1] Extraction", warn_ms=100):
                    rows_data = []
                    sel_model = table.selectionModel()
                    idx0 = QModelIndex()
                    for r in range(row_count):
                        it_sort = table.item(r, col_idx)
                        sort_val = it_sort.data(self._ROLE_NUMERIC) if it_sort else None
                        if sort_val is None and it_sort: sort_val = it_sort.text()
                        is_selected = sel_model.isRowSelected(r, idx0) if sel_model else False
                        row_items = [table.takeItem(r, c) for c in range(col_count)]
                        rows_data.append({'sort_val': sort_val if sort_val is not None else "", 'items': row_items, 'hidden': table.isRowHidden(r), 'selected': is_selected})

                # Phase 2: Sort
                with timed_ctx("  [Phase 2] Python Sort", warn_ms=50):
                    def safe_key(v):
                        # [FIX] 使用二元组 (is_numeric, value) 解决 float 与 str 不可比较的问题
                        if isinstance(v, (int, float)): return (0, float(v))
                        try: 
                            val_str = str(v).replace("%", "").replace(",", "").strip()
                            if not val_str: return (1, "") # 空字符串排在后面
                            return (0, float(val_str))
                        except: 
                            return (1, str(v)) # 非数字作为字符串排在后面
                    rows_data.sort(key=lambda x: safe_key(x["sort_val"]), reverse=reverse)

                # Phase 3: Write-back
                with timed_ctx("  [Phase 3] Write-back", warn_ms=100):
                    table.clearSelection()
                    for r, row in enumerate(rows_data):
                        table.setRowHidden(r, row["hidden"])
                        for c, item in enumerate(row["items"]):
                            if item: table.setItem(r, c, item)
                        if row["selected"]: table.selectRow(r)
        finally:
            # 4. 释放重置闸门并恢复
            if model: model.endResetModel()
            for j, m in enumerate(orig_modes): hh.setSectionResizeMode(j, m)
            table.setSortingEnabled(was_sorting)
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
            table.viewport().setUpdatesEnabled(True)
            hh.setUpdatesEnabled(True)
            vh.setUpdatesEnabled(True)
            table.viewport().update()
            table._is_sorting_locked = False
            gc.enable()

    def _trigger_sorted_refresh(self):
        """[ASYNC] 排序意图落地：决策引擎表直接物理排序；信号表延迟异步排序"""
        _ENGINE_TABS = {"🌟 决策队列", "🐉 龙头追踪", "🔥 板块热力", "🌐 战略趋势", "📡 市场预警"}
        current_tab_text = self.tabs.tabText(self.tabs.currentIndex())
        table = self.tables.get(current_tab_text)
        if not table: return

        if current_tab_text in _ENGINE_TABS:
            # 🚀 [PERF-FIX] 核心改进：点击排序时，仅对当前表中的 Item 进行物理位置迁移
            # 严禁将 table._render_version 设为 -1，严禁触发 _update_engine_views()
            sort_col = getattr(table, "_sort_col", table.horizontalHeader().sortIndicatorSection())
            sort_order = getattr(table, "_sort_order", table.horizontalHeader().sortIndicatorOrder())
            self._sort_table_python(table, sort_col, sort_order)
        else:
            # [DEBOUNCE] 如果当前已经有一个单次定时器在排队，不再重复添加，实现“只做最后一次”
            if not getattr(self, "_deferred_sort_pending", False):
                self._deferred_sort_pending = True
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(15, self._do_deferred_sort)

    def _do_deferred_sort(self):
        # \"\"\"执行实际的延迟排序操作\"\"\"
        self._deferred_sort_pending = False # 释放挂起标志
        with timed_ctx("_do_deferred_sort", warn_ms=200):
            current_tab_text = self.tabs.tabText(self.tabs.currentIndex())
            table = self.tables.get(current_tab_text)
            if not table: return
            
            # 提取已保存的排序状态
            sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
            sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
            
            # 执行高效排序
            self._sort_table_python(table, sort_col, sort_order)
            table.horizontalHeader().setSectionsClickable(True)

    def _fast_update_cell(self, table, r_idx, c_idx, text, color_key=None, bold=False, bg_key=None, numeric_val=None, data=None):
        """[PERF] 极速单元格更新逻辑：
        1. 仅在内容真实变化时调用 Qt C++ 接口
        2. 缓存 Font/Brush 对象，避免高频创建
        3. 严格脏检查，减少渲染树扰动
        """
        it = table.item(r_idx, c_idx)
        if not it:
            # [PERF] 新建 item 路径
            it = QTableWidgetItem()
            text_str = str(text) if text is not None else ""
            it.setText(text_str)
            it.setData(self._ROLE_TEXT, text_str)
            if numeric_val is not None:
                it.setData(self._ROLE_NUMERIC, numeric_val)
            if data is not None:
                it.setData(self._ROLE_DATA, data)
            
            # 只有在非默认值时才调用 expensive 的 Qt 方法
            if color_key and color_key != "#ffffff":
                it.setForeground(self._BRUSH_PRESET.get(color_key, self._BRUSH_PRESET["#ffffff"]))
                it.setData(self._ROLE_COLOR, color_key)
            if bg_key:
                it.setBackground(self._BRUSH_PRESET.get(bg_key, self._BRUSH_PRESET["transparent"]))
                it.setData(self._ROLE_BG, bg_key)
            if bold:
                it.setFont(self._font_bold)
                it.setData(self._ROLE_BOLD, True)
            
            table.setItem(r_idx, c_idx, it)
            
            # [NEW] 初始路径即建立搜索索引
            if c_idx in [0, 1, 2, 4]: # 关键搜索列 (代码/名称/板块)
                it.setData(self._ROLE_SEARCH_BLOB, str(text).lower())
            return

        # ---- 已有 item：全路径脏检查 ----
        text_str = str(text) if text is not None else ""
        # [PERF] 优先使用 text() 快速比对
        if it.text() != text_str:
            it.setText(text_str)
            it.setData(self._ROLE_TEXT, text_str)
            # [NEW] 更新搜索索引
            if c_idx in [0, 1, 2, 4]:
                it.setData(self._ROLE_SEARCH_BLOB, text_str.lower())

        if data is not None and it.data(self._ROLE_DATA) != data:
            it.setData(self._ROLE_DATA, data)

        if numeric_val is not None:
            # [PERF] 浮点数防抖脏检查
            old_num = it.data(self._ROLE_NUMERIC)
            try:
                if old_num is None or abs(float(old_num) - float(numeric_val)) > 0.00001:
                    it.setData(self._ROLE_NUMERIC, numeric_val)
            except (ValueError, TypeError):
                if old_num != numeric_val:
                    it.setData(self._ROLE_NUMERIC, numeric_val)

        # [PERF] 颜色/字体脏检查优化：不再对 None 或 默认值 重复设置
        # Foreground
        current_color = it.data(self._ROLE_COLOR)
        target_color = color_key if color_key else "#ffffff"
        if current_color != target_color:
            it.setForeground(self._BRUSH_PRESET.get(target_color, self._BRUSH_PRESET["#ffffff"]))
            it.setData(self._ROLE_COLOR, target_color)

        # Background
        current_bg = it.data(self._ROLE_BG)
        target_bg = bg_key # 可以为 None (transparent)
        if current_bg != target_bg:
            it.setBackground(self._BRUSH_PRESET.get(target_bg, self._BRUSH_PRESET["transparent"]))
            it.setData(self._ROLE_BG, target_bg)

        # Font Bold
        if it.data(self._ROLE_BOLD) != bold:
            it.setFont(self._font_bold if bold else self._font_normal)
            it.setData(self._ROLE_BOLD, bold)
    def _update_engine_views(self, force: bool = False):
        """[PERF] 分类刷新引擎视图，仅刷新当前可见 Tab，实现资源按需加载"""
        now = time.time()
        if not force and now - getattr(self, '_last_view_update', 0) < 0.2: # 200ms 节流
            return
        self._last_view_update = now

        if self._engine_ctrl is None:
            self._engine_ctrl = get_engine_controller()
            if self._engine_ctrl:
                logger.info("✅ [DASHBOARD] SectorFocusController connected.")
        
        if self._engine_ctrl is None:
            self.status_label.setText("未连接决策引擎")
            return

        current_tab_text = self.tabs.tabText(self.tabs.currentIndex())

        if current_tab_text == "📡 市场预警":
            self._refresh_alert_hub_table()
        # 1. 更新决策队列表
        elif current_tab_text == "🌟 决策队列":
            try:
                decisions = self._engine_ctrl.get_decision_queue()
                self._refresh_decision_table(decisions)
            except Exception as e:
                logger.error(f"❌ [DASHBOARD] Refresh decision table failed: {e}", exc_info=True)
                self.status_label.setText(f"错误: 决策同步失败")

        # 2. 更新龙头追踪表 [NEW]
        elif current_tab_text == "🐉 龙头追踪":
            try:
                dragons = self._engine_ctrl.get_dragon_leaders()
                self._refresh_dragon_table(dragons)
            except Exception as e:
                logger.error(f"❌ [DASHBOARD] Refresh dragon table failed: {e}", exc_info=True)
                self.status_label.setText(f"错误: 龙头同步失败")

        # 3. 更新战略趋势表 [PERF] 优先使用 EVENT_STRATEGIC_TREND 直推缓存，避免重复拉取
        elif current_tab_text == "🌐 战略趋势":
            try:
                # 若 _process_event 已通过 EVENT_STRATEGIC_TREND 缓存了最新数据，直接使用
                # 否则回退到 engine 查询（兜底）
                trends = getattr(self, '_cached_strategic_trends', None)
                if trends is None:
                    trends = self._engine_ctrl.get_strategic_trends()
                self._refresh_strategic_table(trends)
            except Exception as e:
                logger.error(f"❌ [DASHBOARD] Refresh strategic table failed: {e}")

        # 4. 更新板块热力表
        elif current_tab_text == "🔥 板块热力":
            try:
                sectors = self._engine_ctrl.get_hot_sectors(top_n=20)
                self._refresh_sector_table(sectors)
            except Exception as e:
                logger.error(f"❌ [DASHBOARD] Refresh sector table failed: {e}", exc_info=True)

    def _refresh_alert_hub_table(self):
        table = self.tables.get("📡 市场预警")
        if not table: return
        
        alerts = self._hub_alerts[:] # 复制副本防止干扰
        
        # [NEW] 增加手动排序支持
        sort_col = getattr(table, '_sort_col', 0)
        sort_order = getattr(table, '_sort_order', Qt.SortOrder.DescendingOrder)
        
        def _get_sort_key(a):
            if sort_col == 0: return a.get('ts', a.get('timestamp', ''))
            if sort_col == 1: return a.get('grade', 'B')
            if sort_col == 2: return a.get('type', '')
            if sort_col == 3: return a.get('content', '')
            if sort_col == 4: 
                v = a.get('metadata', {}).get('count', a.get('count', 0))
                try: return int(v) if str(v).isdigit() else 0
                except: return 0
            if sort_col == 5: return str(a.get('metadata', {}).get('codes', []))
            return 0
            
        alerts.sort(key=_get_sort_key, reverse=(sort_order == Qt.SortOrder.DescendingOrder))
        
        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False) # 🛡️ [FIX] 刷新期间强制关闭排序，确保 i 对齐 visual row
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        
        try:
            table.setRowCount(len(alerts))
            for i, alert in enumerate(alerts):
                grade = alert.get('grade', 'B')
                ts = alert.get('ts', alert.get('timestamp', ''))
                type_str = alert.get('type', '')
                content = alert.get('content', '')
                
                metadata = alert.get('metadata', {})
                count = metadata.get('count', alert.get('count', '-'))
                codes = metadata.get('codes', alert.get('codes', []))
                
                # [MOD] 详情列展示优化：尝试将代码转为名称，并增强板块信息
                detail = ""
                if type_str == "MARKET_ALERT" and not codes:
                    top_sectors = metadata.get('top_sectors', [])
                    if top_sectors:
                        detail = "影响板块: " + ", ".join(top_sectors)
                        density = "Temp"
                    else:
                        density = str(count)
                        detail = ""
                else:
                    density = str(count)
                    # 尝试转换代码为 "名称(代码)" 格式
                    df_all = self._get_snapshot_df()
                    display_list = []
                    for c in codes[:8]: # 限制展示数量，避免撑爆单元格
                        if df_all is not None and c in df_all.index:
                            display_list.append(f"{df_all.loc[c, 'name']}({c})")
                        else:
                            display_list.append(c)
                    if len(codes) > 8: display_list.append("...")
                    detail = ",".join(display_list)
                    
                    # 修正 "其它" 板块显示
                    if "其它" in content and len(codes) > 0:
                        # 如果是其它板块，但在详情里有明确个股，这里可以保持 detail 为个股列表
                        pass
                
                self._fast_update_cell(table, i, 0, ts, data=alert) 
                self._fast_update_cell(table, i, 1, grade, data=alert)
                self._fast_update_cell(table, i, 2, type_str, data=alert)
                self._fast_update_cell(table, i, 3, content, data=alert)
                self._fast_update_cell(table, i, 4, density, data=alert)
                self._fast_update_cell(table, i, 5, detail, data=alert)
                
                # 视觉分级
                row_color = None
                if grade == 'S':
                    row_color = QColor("#4B0000") # 深红色背景
                elif grade == 'A':
                    row_color = QColor("#332200") # 深褐色
                
                if row_color:
                    for j in range(table.columnCount()):
                        item = table.item(i, j)
                        if item: item.setBackground(row_color)
                        
        finally:
            table.setSortingEnabled(was_sorting)
            table.blockSignals(False)
            table.setUpdatesEnabled(True)

    def _on_alert_cell_clicked(self, row, column):
        """[GUI] 单击预警行单元格事件，实现单击任意列瞬间联动第一个股票，不弹出详情弹窗"""
        table = self.tables.get("📡 市场预警")
        if not table: return
        
        # 保护：如果是表格后台刷新/更新期间，直接忽略
        if table.signalsBlocked(): return
        
        it = table.item(row, column)
        if not it: it = table.item(row, 0)
        if not it: return
        
        alert = it.data(self._ROLE_DATA)
        if not alert or not isinstance(alert, dict):
            # 尝试遍历当前行寻找有数据的 item
            for c in range(table.columnCount()):
                tmp_it = table.item(row, c)
                if tmp_it:
                    alert = tmp_it.data(self._ROLE_DATA)
                    if isinstance(alert, dict): break
            
            if not isinstance(alert, dict):
                if row < 0 or row >= len(self._hub_alerts): return
                alert = self._hub_alerts[row]
                
        if not isinstance(alert, dict): return
        
        metadata = alert.get('metadata', {})
        codes = metadata.get('codes', [])
        details = metadata.get('details', [])
        
        if not codes:
            codes = re.findall(r'\d{6}', alert.get('content', ''))
            
        if not codes: return
        
        first_code = codes[0]
        first_name = "-"
        df_all = self._get_snapshot_df()
        if df_all is not None and first_code in df_all.index:
            first_name = str(df_all.loc[first_code, 'name'])
        else:
            for d in details:
                if d.get('code') == first_code:
                    first_name = d.get('name', '-')
                    break
                    
        # 直接触发联动！
        self.code_clicked.emit(first_code, first_name)

    def _on_alert_selection_changed(self):
        """[GUI] 监听市场预警表格的选择变化（支持键盘上下翻页时自动联动第一个代码）"""
        table = self.tables.get("📡 市场预警")
        if not table or table.signalsBlocked(): return
        
        items = table.selectedItems()
        if not items: return
        
        # 获取当前选中的首个行
        row = items[0].row()
        if row >= 0:
            self._on_alert_cell_clicked(row, 0)

    def _on_alert_enter_pressed(self):
        """[GUI] 按下回车键时，模拟双击打开详情页"""
        table = self.tables.get("📡 市场预警")
        if not table: return
        
        row = table.currentRow()
        col = table.currentColumn()
        if row >= 0:
            if col < 0: col = 0
            self._on_alert_double_clicked(row, col)

    def _on_alert_double_clicked(self, row, column):
        """[GUI] 双击预警行，查看个股异动明细"""
        table = self.tables.get("📡 市场预警")
        if not table: return
        
        # ⭐ [FIX] 从单元格 UserRole 中直接获取原始 alert 数据，解决排序/过滤导致的索引错位问题
        it = table.item(row, column) # 优先取当前点击列
        if not it: it = table.item(row, 0) # 兜底取首列
        if not it: return
        
        alert = it.data(self._ROLE_DATA)
        if not alert or not isinstance(alert, dict): 
            # 尝试遍历当前行寻找有数据的 item (部分列可能由于复用没来得及写 data)
            for c in range(table.columnCount()):
                tmp_it = table.item(row, c)
                if tmp_it:
                    alert = tmp_it.data(self._ROLE_DATA)
                    if isinstance(alert, dict): break
            
            if not isinstance(alert, dict):
                # 最后的兜底：如果 Role 数据缺失，尝试使用 legacy 索引（可能错位但能跑）
                if row < 0 or row >= len(self._hub_alerts): return
                alert = self._hub_alerts[row]
        metadata = alert.get('metadata', {})
        codes = metadata.get('codes', [])
        details = metadata.get('details', [])
        
        if not codes: 
            # 如果没有 codes，尝试从 content 中提取
            codes = re.findall(r'\d{6}', alert.get('content', ''))
            
        if not codes: return
        
        if not self._alert_detail_dialog:
            self._alert_detail_dialog = MarketAlertDetailDialog(self)
            self._alert_detail_dialog.code_clicked.connect(self.code_clicked)
            
        # [MOD] 注入当前行情快照（从多渠道尝试获取）
        df_all = self._get_snapshot_df()
            
        self._alert_detail_dialog.update_data(codes, df_snapshot=df_all, details=details)
        self._alert_detail_dialog.show()
        self._alert_detail_dialog.raise_()
        self._alert_detail_dialog.activateWindow()
        
        # 🎯 [NEW] 双击打开详情后自动选择第一行并切入焦点，可以直接键盘上下键查看联动
        if self._alert_detail_dialog.table.rowCount() > 0:
            self._alert_detail_dialog.table.clearSelection()
            self._alert_detail_dialog.table.selectRow(0)
        self._alert_detail_dialog.table.setFocus()

    def _refresh_decision_table(self, decisions: List[dict]):
        table = self.tables.get("🌟 决策队列")
        if not table: return
        
        # [PERF] 阶段2：版本号脏检查
        if getattr(self, '_engine_ctrl', None):
            if getattr(table, '_render_version', -1) == self._engine_ctrl._decision_render_version:
                return
            table._render_version = self._engine_ctrl._decision_render_version

        current_selection = None
        sel_items = table.selectedItems()
        if sel_items: 
            it = table.item(sel_items[0].row(), 3)
            if it: current_selection = it.data(self._ROLE_TEXT)

        sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
        sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
        
        def _get_sort_key(d):
            if sort_col == 0: return d.get('created_at', '')
            if sort_col == 1: return d.get('priority', 0)
            if sort_col == 2: return d.get('status', '')
            if sort_col == 3: return d.get('code', '')
            if sort_col == 4: return d.get('name', '')
            if sort_col == 5: return d.get('signal_type', '')
            if sort_col == 6: return d.get('sector', '')
            if sort_col == 7: return d.get('current_price', 0.0)
            if sort_col == 8: return d.get('suggest_price', 0.0)
            if sort_col == 9: return d.get('pct_diff', 0.0)
            if sort_col == 10: return d.get('dff', 0.0)
            if sort_col == 11: return d.get('reason', '')
            return 0

        decisions = sorted(decisions, key=_get_sort_key, reverse=(sort_order == Qt.SortOrder.DescendingOrder))

        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        table.setProperty("uniformItemSizes", True)
        table.setProperty("layoutAboutToBeChanged", True)
        table.blockSignals(True)
        table.verticalHeader().setUpdatesEnabled(False)
        table.horizontalHeader().setUpdatesEnabled(False)
        vp = table.viewport()
        vp.setUpdatesEnabled(False)

        try:
            if table.rowCount() != len(decisions):
                table.setRowCount(len(decisions))

            for i, d in enumerate(decisions):
                self._fast_update_cell(table, i, 0, d.get('created_at', ''))
                
                prio = d.get('priority', 0)
                p_color = "#ff0000" if prio >= 75 else ("#ffaa00" if prio >= 60 else "#ffffff")
                self._fast_update_cell(table, i, 1, prio, color_key=p_color, numeric_val=prio)
                
                st_text = d.get('status', '待处理')
                st_color = "#00ff88" if '成交' in st_text else "#ffffff"
                self._fast_update_cell(table, i, 2, st_text, color_key=st_color)
                
                code = d.get('code', '')
                c_color = "#ffff00" if code.startswith('30') else "#00ffff"
                self._fast_update_cell(table, i, 3, code, color_key=c_color, bold=True)
                
                self._fast_update_cell(table, i, 4, d.get('name', ''))
                self._fast_update_cell(table, i, 5, d.get('signal_type', ''))
                self._fast_update_cell(table, i, 6, d.get('sector', ''))
                self._fast_update_cell(table, i, 7, d.get('current_price', 0.0), numeric_val=d.get('current_price', 0.0))
                self._fast_update_cell(table, i, 8, d.get('suggest_price', 0.0), numeric_val=d.get('suggest_price', 0.0))
                
                pd_val = d.get('pct_diff', 0.0)
                pd_color = "#ff4444" if pd_val > 0 else ("#44ff44" if pd_val < 0 else "#ffffff")
                self._fast_update_cell(table, i, 9, f"{pd_val:+.2f}%", color_key=pd_color, numeric_val=pd_val)
                self._fast_update_cell(table, i, 10, d.get('dff', 0.0), numeric_val=d.get('dff', 0.0))
                self._fast_update_cell(table, i, 11, d.get('reason', ''))

                if '🐉' in d.get('reason', ''):
                    for col in range(table.columnCount()):
                        it_col = table.item(i, col)
                        if it_col is None:
                            continue  # 防止未初始化列崩溃
                        self._fast_update_cell(
                            table, i, col,
                            it_col.data(self._ROLE_TEXT) or '',
                            bg_key="gold_bg",
                            numeric_val=it_col.data(self._ROLE_NUMERIC)
                        )

            if current_selection:
                for r in range(table.rowCount()):
                    it = table.item(r, 3)
                    if it and it.data(self._ROLE_TEXT) == current_selection:
                        table.selectRow(r)
                        break
        finally:
            table.setSortingEnabled(was_sorting)
            table.blockSignals(False)
            table.setProperty("layoutAboutToBeChanged", False)
            table.verticalHeader().setUpdatesEnabled(True)
            table.horizontalHeader().setUpdatesEnabled(True)
            vp.setUpdatesEnabled(True)
            table.setUpdatesEnabled(True)

    def _refresh_dragon_table(self, dragons: List[dict]):
        table = self.tables.get("🐉 龙头追踪")
        if not table: return
        
        # [PERF] 强制显示上限
        dragons = dragons[:200]

        # [PERF] 性能分析上下文
        with timed_ctx("_refresh_dragon_table", warn_ms=300):
            if getattr(self, '_engine_ctrl', None):
                if getattr(table, '_render_version', -1) == self._engine_ctrl._dragon_render_version:
                    return
                table._render_version = self._engine_ctrl._dragon_render_version

            current_selection = None
            sel_items = table.selectedItems()
            if sel_items: 
                it = table.item(sel_items[0].row(), 1) # code col
                if it: current_selection = it.data(self._ROLE_TEXT)

            sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
            sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
            
            def _get_sort_key(d):
                if sort_col == 0: return d.get('status_label', '')
                if sort_col == 1: return d.get('code', '')
                if sort_col == 2: return d.get('name', '')
                if sort_col == 3: return d.get('sector', '')
                if sort_col == 4: return d.get('current_pct', 0.0)
                if sort_col == 5: return d.get('cum_pct', 0.0)
                if sort_col == 6: return d.get('tracked_days', 0)
                if sort_col == 7: return d.get('consecutive_new_highs', 0)
                if sort_col == 8: return d.get('dff', 0.0)
                if sort_col == 9: return d.get('vwap', 0.0)
                if sort_col == 10: return d.get('last_update', '')
                if sort_col == 11: return d.get('tags', '')
                return 0

            dragons = sorted(dragons, key=_get_sort_key, reverse=(sort_order == Qt.SortOrder.DescendingOrder))

            # [PERF] 极致锁定：停止一切布局重绘
            was_sorting = table.isSortingEnabled()
            table.setSortingEnabled(False)
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            table.verticalHeader().setUpdatesEnabled(False)
            table.horizontalHeader().setUpdatesEnabled(False)
            vp = table.viewport()
            vp.setUpdatesEnabled(False)

            try:
                if table.rowCount() != len(dragons):
                    table.setRowCount(len(dragons))
                    
                # [PERF] 建立代码到行号的快速索引，用于 selection 恢复
                code_to_row = {}
                
                for i, d in enumerate(dragons):
                    st_lbl = d.get('status_label', '')
                    st_color = "#FFD700" if '龙' in st_lbl else ("#00ff00" if '候' in st_lbl else "#ffffff")
                    self._fast_update_cell(table, i, 0, st_lbl, color_key=st_color)
                    
                    code = d.get('code', '')
                    code_to_row[code] = i 
                    
                    c_color = "#ffff00" if code.startswith('30') else "#00ffff"
                    self._fast_update_cell(table, i, 1, code, color_key=c_color, bold=True)
                    self._fast_update_cell(table, i, 2, d.get('name', ''), bold=('龙' in st_lbl))
                    self._fast_update_cell(table, i, 3, d.get('sector', ''))
                    
                    c_pct = d.get('current_pct', 0.0)
                    cp_color = "#ff4444" if c_pct > 0 else ("#44ff44" if c_pct < 0 else "#ffffff")
                    self._fast_update_cell(table, i, 4, f"{c_pct:+.2f}%", color_key=cp_color, numeric_val=c_pct)
                    
                    cum_pct = d.get('cum_pct', 0.0)
                    cum_color = "#FFD700" if cum_pct > 5 else ("#ff4444" if cum_pct > 0 else "#ffffff")
                    self._fast_update_cell(table, i, 5, f"{cum_pct:+.2f}%", color_key=cum_color, numeric_val=cum_pct)
                    
                    self._fast_update_cell(table, i, 6, d.get('tracked_days', 0), numeric_val=d.get('tracked_days', 0))
                    
                    nh_days = d.get('consecutive_new_highs', 0)
                    nh_color = "#ff4500" if nh_days >= 3 else "#ffffff"
                    self._fast_update_cell(table, i, 7, nh_days, color_key=nh_color, numeric_val=nh_days)
                    
                    dff = d.get('dff', 0.0)
                    dff_color = "#00ff88" if dff > 0 else "#ffffff"
                    self._fast_update_cell(table, i, 8, dff, color_key=dff_color, numeric_val=dff)
                    self._fast_update_cell(table, i, 9, d.get('vwap', 0.0), numeric_val=d.get('vwap', 0.0))
                    
                    up_time = d.get('last_update', '')
                    if len(up_time) > 19: up_time = up_time[11:19]
                    self._fast_update_cell(table, i, 10, up_time)
                    self._fast_update_cell(table, i, 11, d.get('tags', ''))

                # [PERF] O(1) 快速恢复选中态
                if current_selection and current_selection in code_to_row:
                    target_row = code_to_row[current_selection]
                    table.selectRow(target_row)
                        
            finally:
                # [PERF] 恢复布局并触发一次性刷新
                vp.setUpdatesEnabled(True)
                table.verticalHeader().setUpdatesEnabled(True)
                table.horizontalHeader().setUpdatesEnabled(True)
                table.setSortingEnabled(was_sorting)
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                table.viewport().update()

    def _refresh_sector_table(self, sectors: List[dict]):
        table = self.tables.get("🔥 板块热力")
        if not table: return
        
        # [PERF] 强制显示上限
        sectors = sectors[:100]
        
        if getattr(self, '_engine_ctrl', None):
            if getattr(table, '_render_version', -1) == self._engine_ctrl._sector_render_version:
                return
            table._render_version = self._engine_ctrl._sector_render_version

        current_selection = None
        sel_items = table.selectedItems()
        if sel_items: 
            it = table.item(sel_items[0].row(), 0)
            if it: current_selection = it.data(self._ROLE_TEXT)

        sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
        sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
        
        def _get_sort_key(s):
            if sort_col == 0: return s.get('name', '')
            if sort_col == 1: return s.get('heat_score', 0.0)
            if sort_col == 2: return s.get('bidding_score', 0.0)
            if sort_col == 3: return s.get('sector_type', '')
            if sort_col == 4: return s.get('leader_code', '')
            if sort_col == 5: return s.get('leader_name', '')
            if sort_col == 6: return s.get('leader_change_pct', 0.0)
            if sort_col == 7: return s.get('follow_ratio', 0.0)
            if sort_col == 8: return s.get('follower_detail', '')
            if sort_col == 9: return s.get('updated_at', '')
            return 0

        sectors = sorted(sectors, key=_get_sort_key, reverse=(sort_order == Qt.SortOrder.DescendingOrder))

        was_sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        table.setProperty("uniformItemSizes", True)
        table.setProperty("layoutAboutToBeChanged", True)
        table.blockSignals(True)
        table.verticalHeader().setUpdatesEnabled(False)
        table.horizontalHeader().setUpdatesEnabled(False)
        vp = table.viewport()
        vp.setUpdatesEnabled(False)

        try:
            if table.rowCount() != len(sectors):
                table.setRowCount(len(sectors))

            for i, s in enumerate(sectors):
                self._fast_update_cell(table, i, 0, s.get('name', ''), bold=True)
                
                heat = s.get('heat_score', 0.0)
                h_color = "#ff0000" if heat >= 40 else "#ffffff"
                self._fast_update_cell(table, i, 1, heat, color_key=h_color, numeric_val=heat)
                self._fast_update_cell(table, i, 2, s.get('bidding_score', 0.0), numeric_val=s.get('bidding_score', 0.0))
                
                type_str = s.get('sector_type', '跟随')
                res_tag = s.get('resonance_tag', '')
                merged_type = f"{type_str} | {res_tag}" if res_tag else type_str
                t_color = "#FF4500" if res_tag else ("#ff4444" if '强攻' in type_str else ("#ffaa00" if '蓄势' in type_str else "#ffffff"))
                t_bg = "alert_bg" if res_tag else None
                self._fast_update_cell(table, i, 3, merged_type, color_key=t_color, bg_key=t_bg, bold=bool(res_tag))

                self._fast_update_cell(table, i, 4, s.get('leader_code', ''))
                self._fast_update_cell(table, i, 5, s.get('leader_name', ''))
                
                l_pct = s.get('leader_change_pct', 0.0)
                lp_color = "#ff4444" if l_pct > 0 else "#ffffff"
                self._fast_update_cell(table, i, 6, f"{l_pct:+.2f}%", color_key=lp_color, numeric_val=l_pct)

                self._fast_update_cell(table, i, 7, s.get('follow_ratio', 0.0), numeric_val=s.get('follow_ratio', 0.0))
                self._fast_update_cell(table, i, 8, s.get('follower_detail', ''))
                self._fast_update_cell(table, i, 9, s.get('updated_at', ''))

            if current_selection:
                for r in range(table.rowCount()):
                    it = table.item(r, 0)
                    if it and it.data(self._ROLE_TEXT) == current_selection:
                        table.selectRow(r)
                        break
        finally:
            vp.setUpdatesEnabled(True)
            vp.update()
            table.horizontalHeader().setUpdatesEnabled(True)
            table.verticalHeader().setUpdatesEnabled(True)
            table.setSortingEnabled(was_sorting)
            table.blockSignals(False)
            table.setUpdatesEnabled(True)

    def _refresh_strategic_table(self, trends: List[dict]):
        table = self.tables.get("🌐 战略趋势")
        if not table: return

        # [PERF] 强制显示上限，防止数据爆炸导致 GUI 卡死
        trends = trends[:100]
        
        # [PERF] 性能分析上下文
        with timed_ctx("_refresh_strategic_table", warn_ms=300):
            if getattr(self, '_engine_ctrl', None):
                if getattr(table, '_render_version', -1) == self._engine_ctrl._strategic_render_version:
                    return
                table._render_version = self._engine_ctrl._strategic_render_version

            current_selection = None
            sel_items = table.selectedItems()
            if sel_items: 
                it = table.item(sel_items[0].row(), 1)
                if it: current_selection = it.data(self._ROLE_TEXT)

            sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
            sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
            
            def _get_sort_key(t):
                if sort_col == 0: return t.get('trend_type', '')
                if sort_col == 1: return t.get('code', '')
                if sort_col == 2: return t.get('name', '')
                if sort_col == 3: return str(t.get('stage_label', '')) # 使用 label 排序
                if sort_col == 4: return t.get('sector', '')
                if sort_col == 5: return t.get('score', 0.0)
                if sort_col == 6: return t.get('upper_score', 0.0)
                if sort_col == 7: return t.get('resonance', 0.0)
                if sort_col == 8: return t.get('updated_at', '')
                if sort_col == 9: return t.get('reason', '')
                return 0

            trends = sorted(trends, key=_get_sort_key, reverse=(sort_order == Qt.SortOrder.DescendingOrder))

            # [PERF] 极致锁定：停止一切布局重绘
            was_sorting = table.isSortingEnabled()
            table.setSortingEnabled(False)
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            table.verticalHeader().setUpdatesEnabled(False)
            table.horizontalHeader().setUpdatesEnabled(False)
            vp = table.viewport()
            vp.setUpdatesEnabled(False)

            try:
                if table.rowCount() != len(trends):
                    table.setRowCount(len(trends))

                # [PERF] 建立快速索引
                code_to_row = {}
                for i, t in enumerate(trends):
                    self._fast_update_cell(table, i, 0, t.get('trend_type', ''))
                    
                    code = t.get('code', '')
                    code_to_row[code] = i
                    c_color = "#00ffff" if not code.startswith('30') else "#ffff00"
                    self._fast_update_cell(table, i, 1, code, color_key=c_color, bold=True)
                    
                    self._fast_update_cell(table, i, 2, t.get('name', ''))
                    self._fast_update_cell(table, i, 3, t.get('stage', ''))
                    self._fast_update_cell(table, i, 4, t.get('sector', ''))
                    
                    sc = t.get('score', 0.0)
                    sc_color = "#ff0000" if sc > 80 else ("#ffaa00" if sc > 60 else "#ffffff")
                    self._fast_update_cell(table, i, 5, sc, color_key=sc_color, numeric_val=sc)
                    self._fast_update_cell(table, i, 6, t.get('upper_score', 0.0), numeric_val=t.get('upper_score', 0.0))
                    self._fast_update_cell(table, i, 7, t.get('resonance', 0.0), numeric_val=t.get('resonance', 0.0))
                    
                    self._fast_update_cell(table, i, 8, t.get('updated_at', ''))
                    # [PERF] 限制长文本长度，防止渲染卡顿
                    reason_str = str(t.get('reason', ''))
                    if len(reason_str) > 100: reason_str = reason_str[:100] + "..."
                    self._fast_update_cell(table, i, 9, reason_str)

                # [PERF] O(1) 快速恢复选中态
                if current_selection and current_selection in code_to_row:
                    target_row = code_to_row[current_selection]
                    table.selectRow(target_row)
                        
            finally:
                # [PERF] 恢复布局并触发一次性刷新
                vp.setUpdatesEnabled(True)
                table.verticalHeader().setUpdatesEnabled(True)
                table.horizontalHeader().setUpdatesEnabled(True)
                table.setSortingEnabled(was_sorting)
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                table.viewport().update()

    def _on_signal_received(self, event: BusEvent):
        """[BACKGROUND THREAD] 仅发射信号，不触碰任何 Qt 对象"""
        if not event or not event.payload: 
            return # 🛡️ 防御空事件
        
        # [DEBUG] 打印信号流入快照 (仅在 Debug 或高频时查看)
        logger.debug(f"📡 [DASHBOARD_BUS] Received {event.event_type} from {event.source}: {event.payload.get('code')}")

        if event.event_type == SignalBus.EVENT_MARKET_ALERT:
            payload = event.payload
            content = payload.get('content') or payload.get('message', '')
            metadata = payload.get('metadata', {})
            codes = sorted(metadata.get('codes', []))
            
            # [NEW] 聚合去重逻辑：如果“内容”和“个股名单”完全一致，则剔除旧的，只保留最新的（置顶）
            # 时间不参与比较，确保同一板块同一动作在列表中全局唯一
            idx_to_remove = -1
            for i, old in enumerate(self._hub_alerts):
                if (old.get('content') or old.get('message', '')) == content:
                    old_metadata = old.get('metadata', {})
                    # 只有当个股清单也完全一致时才触发去重（忽略顺序）
                    old_codes = sorted(old_metadata.get('codes', []) or [])
                    if old_codes == codes:
                        idx_to_remove = i
                        break
            
            if idx_to_remove != -1:
                self._hub_alerts.pop(idx_to_remove)

            self._hub_alerts.insert(0, payload)
            if len(self._hub_alerts) > 100: self._hub_alerts.pop()
            
            # 驱动横幅播报
            content = payload.get('content') or payload.get('message', '')
            grade = payload.get('grade', 'B')
            
            logger.info(f"🔔 [DASHBOARD] Received Market Alert: {content} (Grade={grade})")
            
            if grade in ['S', 'A'] and content:
                self.sig_show_banner.emit(str(content))
            
            # [NEW] 记录历史 (使用 QTimer 1.5s 防抖节流定时器进行合并写入，防范高频 IO 冲突与无效写盘)
            self._alert_save_timer.start(1500)

            # [NEW] 联动全部：将预警消息转化为“虚拟信号”注入主表
            # 使用标准的 dict 构建方式，避免 class 实例化问题
            metadata = payload.get('metadata', {})
            codes = metadata.get('codes', [])
            codes_str = f" | {','.join(codes)}" if codes else ""
            
            virtual_payload = {
                "code": "MARKET",
                "name": "📊 市场预警",
                "price": payload.get('temp', 0.0),
                "action": grade,
                "pattern": str(content),
                "grade": grade,
                "detail": f"Type: {payload.get('type', 'HUB')}{codes_str}"
            }
            # 物理重新发布到 UI 队列，确保出现在“全部信号”表中
            self.sig_bus_event.emit(BusEvent(
                event_type=SignalBus.EVENT_PATTERN,
                timestamp=datetime.now(),
                source="MarketHub",
                payload=virtual_payload
            ))

        self.sig_bus_event.emit(event)


    def _show_alert_banner(self, msg):
        """[GUI THREAD] 显示滚动横幅"""
        self.alert_banner.setText(f" 🔔 {msg} ")
        self.alert_banner.setVisible(True)
        self._banner_timer.start(10000) # 10秒后消失
        
        # [NEW] 语音预警
        try:
            get_alert_manager().speak(msg)
        except Exception as e:
            logger.debug(f"Speak failed: {e}")

    def _categorize_and_count(self, event: BusEvent, increment: bool = True):
        delta = 1 if increment else -1
        payload = event.payload
        if not payload: return
        
        # [🛡️ FIX] 增加防御性，确保 p 和 d 始终是有效字符串
        p = str(payload.get('pattern', payload.get('subtype', '')) or '').lower()
        d = str(payload.get('detail', payload.get('message', '')) or '').lower()
        
        if not hasattr(event, '_cached_cats'):
            cats = set()
            # [REVERTED] 恢复重叠多重标签
            for cat_key, keywords in CATEGORY_MAP.items():
                if not keywords: continue
                if any(str(x).lower() in p or str(x).lower() in d for x in keywords):
                    # 映射内部 key
                    if cat_key == "突破加速": cats.add("breakout")
                    elif cat_key == "卖点预警": cats.add("risk")
                    elif cat_key == "结构破位": cats.add("breakdown")
                    elif cat_key == "跟单信号": cats.add("follow")
                    elif cat_key == "买入机会": cats.add("bull")
                    elif cat_key == "尾盘诱多": cats.add("trap")
            
            if not cats: cats.add("other")
            event._cached_cats = cats
            
        for cat in event._cached_cats:
            if self._stats_counters and cat in self._stats_counters: 
                self._stats_counters[cat] += delta
        
        if self._stats_counters:
            if "breakout" in event._cached_cats: self._stats_counters["bull"] += delta
            if "risk" in event._cached_cats or "breakdown" in event._cached_cats: self._stats_counters["bear"] += delta

        # [NEW] 统计信号类型用于下拉框
        raw_type = str(payload.get('pattern', payload.get('subtype', 'ALERT')) or 'ALERT').lower()
        matched_type = "ALERT"
        if SIGNAL_TYPE_KEYWORDS:
            for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                if not keywords: continue
                if any(str(kw).lower() in raw_type for kw in keywords):
                    matched_type = eng_key
                    break
        
        self._signal_type_counts[matched_type] = max(0, self._signal_type_counts.get(matched_type, 0) + delta)
        self._signal_type_counts["ALL"] = max(0, self._signal_type_counts["ALL"] + delta)
        
        # 实时触发下拉框更新 (节流)
        if increment: 
            QTimer.singleShot(100, self._refresh_type_filter_items)

    def _safe_process_event(self, event: BusEvent):
        """线程安全地接管总线事件，先更新内存统计，再将 UI 更新推入缓冲"""
        try:
            # 1. 立即更新内存统计与计数 (满足实时性)
            self._process_event(event, update_ui=False)
            
            # 2. 推入 UI 更新缓冲 (满足稳定性)
            with self._data_lock: # ⭐ [FIX] 使用锁保护缓冲区写入
                self._table_update_buffer.append(event)
            
            # 3. 如果是高优信号，缩短批次等待，尽快显示 (可选)
            # if event.payload.get('is_high_priority'): QTimer.singleShot(500, self._process_batch_signals)
        except Exception as e:
            logger.error(f"Error in _safe_process_event: {e}")

    def _process_batch_signals(self):
        """批量处理 UI 更新，确保滚动条稳定"""
        # with timed_ctx("_process_batch_signals", warn_ms=200):
        if not self._table_update_buffer:
            return
        
        # [🚀 极致性能] 非阻塞锁获取，避免 UI 线程在重负载期间因等待锁而产生丢帧
        if not self._data_lock.acquire(blocking=False):
            # 如果背景线程正在大量写入缓冲区，UI 线程避让并推迟 500ms 重试
            QTimer.singleShot(500, self._process_batch_signals)
            return

        try:
            events_raw = self._table_update_buffer[:]
            self._table_update_buffer.clear()
        finally:
            self._data_lock.release()
        
        if not events_raw: return
        
        # ⚡ [FIX] 移除此处的批次内按股票代码去重！
        # 如果同一个股票在3秒内同时触发"跟单"与"破位"，较早的跨分类信号若被去重丢弃，会导致某分类卡片统计增加了但表格中永远不出现该行的严重Bug。
        # 去重下放至 _insert_row 内部，针对每个子分类表格进行精准的独立覆盖更新。
        events_to_process = events_raw

        # 记录当前各表格的滚动状态
        scroll_states = {}
        for name, table in self.tables.items():
            # ⚡ [PERF] 批量禁用更新、信号和排序全家桶，提升性能
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            
            scroll_states[name] = {
                'value': table.verticalScrollBar().value(),
                'at_top': table.verticalScrollBar().value() == 0,
                'selected': [(r.topRow(), r.bottomRow()) for r in table.selectedRanges()],
                'sorting': table.isSortingEnabled() # 记录排序状态
            }
            # [FIX] 在大批量插入期间，必须全局禁用排序，否则在 setItem 时仍然有 O(N*logN) 的触发或者布局更新
            table.setSortingEnabled(False)
        
        # 批量插入
        self._is_updating_ui = True
        batch_start = time.perf_counter()
        processed_count = 0
            
        try:
            for event in events_to_process:
                self._append_to_tables(event)
                processed_count += 1
        finally:
            current_tab_text = self.tabs.tabText(self.tabs.currentIndex())
            for name, table in self.tables.items():
                state = scroll_states.get(name)
                # [PERF] ENGINE TABS 不接收信号插入，自有一套排序刷新逻辑
                if name not in ["🌟 决策队列", "🐉 龙头追踪", "🔥 板块热力", "🌐 战略趋势"]:
                    # [STEP-2 FIX] 仅对当前可见的 Tab 执行实时排序，不可见 Tab 标记为“需要排序”
                    if name == current_tab_text:
                        sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
                        sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
                        self._sort_table_python(table, sort_col, sort_order)
                        table._needs_sort = False # 已完成
                    else:
                        table._needs_sort = True # 标记脏位，切回来时再排
                    
                    table.horizontalHeader().setSectionsClickable(True)
                        
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                # [PERF] Interactive 模式下不再需要每次限制列宽
                table.viewport().update()
                
            self._is_updating_ui = False
            batch_dur = (time.perf_counter() - batch_start) * 1000
            if batch_dur > 50:
                logger.debug(f"📊 [DASHBOARD_PERF] Batch processed {processed_count} signals in {batch_dur:.1f}ms (TotalReceived={len(events_raw)})")
            
        # 恢复/修正滚动位置
        for name, table in self.tables.items():
            state = scroll_states.get(name)
            if not state: continue
            
            # [MOD] 逻辑：
            # 1. 如果用户之前就在顶部(at_top=True)，则继续保持在顶部(0位置)，此时能看到最新冒出来的信号
            # 2. 如果用户之前正在往下翻看旧数据(at_top=False)，则向下偏移新插入的行数，以保持视窗内原来的内容不动
            if state['at_top']:
                table.verticalScrollBar().setValue(0)
            else:
                new_val = state['value'] + len(events_to_process)
                table.verticalScrollBar().setValue(new_val)

        # [NEW] 批量插入后立即触发统计重算，消除统计更新滞后的体感
        self._update_stats_display()

    def _process_event(self, event: BusEvent, update_ui=True):
        payload = event.payload

        if event.event_type == SignalBus.EVENT_STRATEGIC_TREND:
            self._cached_strategic_trends = payload.get('trends', [])
            _st_table = self.tables.get("🌐 战略趋势")
            if _st_table: _st_table._render_version = -1
            return

        # [MOD] 处理市场预警事件
        if event.event_type == SignalBus.EVENT_MARKET_ALERT:
            if update_ui and self.tabs.tabText(self.tabs.currentIndex()) == "📡 市场预警":
                self._refresh_alert_hub_table()
            return


        code = payload.get('code', '')
        # 🛡️ [GUARD] 必须有有效的股票代码才处理，防止空信号进入列表 (放行虚拟代码 MARKET)
        if not (isinstance(code, str) and (code.isdigit() and len(code) == 6 or code == "MARKET")): return
        
        self._all_events.append(event)
        self._categorize_and_count(event, increment=True)
        if len(self._all_events) > 5000:
            self._categorize_and_count(self._all_events.pop(0), increment=False)
        
        sector = payload.get('sector', '其它')
        with self._data_lock: # ⭐ [FIX] 使用锁保护统计数据更新
            if sector: self._sector_heat[sector] = self._sector_heat.get(sector, 0) + 1
            if code not in self._stock_stats: self._stock_stats[code] = {"count": 0, "name": payload.get('name', '')}
            self._stock_stats[code]["count"] += 1

        if update_ui: self._append_to_tables(event)

    def _append_to_tables(self, event: BusEvent):
        payload = event.payload
        code = payload.get('code', '')
        name = payload.get('name', '')
        
        # 🛡️ [FIX] 核心 code 必须有，name 缺失则兜底，不再暴力 return 阻断显示
        if not code:
            return 
        if not name:
            name = code

        append_start = time.perf_counter()
        pattern = payload.get('pattern', payload.get('subtype', 'ALERT'))
        detail = payload.get('detail', payload.get('message', ''))
        score = payload.get('score', 0.0)
        if pd.isna(score) or score is None:
            score = 0.0
            
        grade = str(payload.get('grade', '') or '')
        time_str = event.timestamp.strftime("%H:%M:%S")
        count = self._stock_stats.get(code, {}).get("count", 1)
        
        # 1. 全部信号
        self._insert_row(self.tables["全部信号"], time_str, code, name, pattern, detail, count, score, grade, payload)
        
        # 2. 分类信号 
        matched_cats = 0
        for cat, patterns in CATEGORY_MAP.items():
            if any(p.lower() in pattern.lower() or p.lower() in detail.lower() for p in patterns):
                self._insert_row(self.tables[cat], time_str, code, name, pattern, detail, count, score, grade, payload)
                matched_cats += 1
        
        # 3. 未命中任何关键分类的归入其它
        if matched_cats == 0:
            self._insert_row(self.tables["其它信号"], time_str, code, name, pattern, detail, count, score, grade, payload)
        
        append_dur = (time.perf_counter() - append_start) * 1000
        # 节流日志，仅输出严重延迟
        if append_dur > 150:
            logger.debug(f"⚠️ [DASHBOARD_PERF] _append_to_tables cost {append_dur:.1f}ms for {code} (matches={matched_cats})")

    def _get_pattern_color(self, pattern, detail, grade=""):
        if grade == "极高":
            if "⚠️" in pattern or "SELL" in pattern or "破位" in detail: 
                return "#ff00ff"
            return "#FFD700"
            
        if "[重点]" in detail or "[重点]" in pattern: 
            return "#FFD700"
        if "SELL" in pattern or "风险" in detail or "破位" in detail: 
            return "#00ff00"
        if "BUY" in pattern or "突破" in detail or any(kw in detail for kw in ["上涨", "反转", "抢筹"]): 
            return "#ff4444"
        if "跟单" in detail: 
            return "#FFD700"
        return "#ffffff"

    def _get_item_color(self, pattern, detail, grade=""):
        color_str = self._get_pattern_color(pattern, detail, grade)
        return self._colors.get(color_str, self._colors["#ffffff"])

    def _insert_row(self, table, time_str, code, name, pattern, detail, count, score, grade='', payload=None):
        insert_start = time.perf_counter()
        was_sorting = table.isSortingEnabled()
        if was_sorting:
            table.setSortingEnabled(False)
        try:
            # 🔍 [PERF] O(1) 查找现有行索引
            table_cache = self._row_cache.setdefault(table, {})
            existing_row = -1
            old_meta = table_cache.get(code)
            if old_meta:
                try:
                    # 兼容旧版本直接存 Item 的情况
                    old_item = old_meta['item'] if isinstance(old_meta, dict) else old_meta
                    existing_row = table.row(old_item)
                    if existing_row >= 0:
                        table.removeRow(existing_row)
                except (RuntimeError, Exception): 
                    pass 
            
            # [A1] insertRow(0) → appendRow (O(1) 尾部追加)
            new_row = table.rowCount()
            table.insertRow(new_row)
            
            # 🛡️ [CAPPING] 限制表格总长度
            max_rows = 5000
            if table.rowCount() > max_rows:
                # 始终移除物理上的第一行
                rem_row_idx = 0
                rem_item = table.item(rem_row_idx, 2)
                if rem_item:
                    table_cache.pop(rem_item.text(), None)
                table.removeRow(rem_row_idx)
                new_row = table.rowCount() - 1 

            # 形态/信号 (中文化展示)
            display_pattern = pattern
            for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                if any(kw.lower() in pattern.lower() for kw in keywords):
                    display_pattern = SIGNAL_TYPE_MAP.get(eng_key, pattern)
                    break
            
            p_item = QTableWidgetItem(display_pattern)
            p_item.setData(Qt.ItemDataRole.UserRole, pattern)
            
            grade_item = QTableWidgetItem(grade)
            grade_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if grade in ['S', 'A']:
                color_key = "#ff0000" if grade=='S' else "#ffaa00"
                grade_item.setForeground(self._brushes.get(color_key, QBrush(self._colors.get(color_key))))
                f = grade_item.font(); f.setBold(True); grade_item.setFont(f)

            # 核心列 (存入缓存)
            is_alerted = get_alert_manager().is_alerted(code)
            display_name = f"🔔{name}" if is_alerted else name
            alert_bg = self._brushes.get("alert_bg", QBrush(QColor("#4B0082")))
            alert_fg = self._colors.get("#ffffff") if is_alerted else None
            
            code_item = QTableWidgetItem(code)
            
            # [A2] search_blob 预计算并存入 item
            sector = payload.get('sector', '') if payload else ''
            search_blob = f"{code} {name} {display_pattern} {detail} {sector}".lower()
            code_item.setData(self._ROLE_SEARCH_BLOB, search_blob)
            
            table_cache[code] = {
                'item': code_item, 
                'search_blob': search_blob,
                'pattern_raw': pattern
            }

            name_item = QTableWidgetItem(display_name)
            if payload:
                name_item.setData(Qt.ItemDataRole.UserRole, payload.get('sector', ''))

            table.setItem(new_row, 0, QTableWidgetItem(time_str))
            table.setItem(new_row, 1, grade_item)
            table.setItem(new_row, 2, code_item)
            table.setItem(new_row, 3, name_item)
            table.setItem(new_row, 4, p_item) 
            table.setItem(new_row, 5, QTableWidgetItem(detail))
            table.setItem(new_row, 6, NumericTableWidgetItem(str(count)))
            table.setItem(new_row, 7, NumericTableWidgetItem(str(int(score))))
            
            # 搜索隐藏逻辑 (使用 blob 代替逐个 item 访问)
            search_text = self.search_input.text().strip().lower()
            if search_text and search_text not in search_blob:
                table.setRowHidden(new_row, True)
            
            color = self._get_item_color(pattern, detail, grade)
            if is_alerted: color = alert_fg
            
            for i in [0, 2, 3, 4, 5, 6, 7]:
                it = table.item(new_row, i)
                if it: 
                    it.setForeground(color)
                    if is_alerted: it.setBackground(alert_bg)
            
            # [NEW] 重点信号行高亮
            if "[重点]" in detail or "[重点]" in pattern:
                highlight_bg = self._brushes.get("highlight_bg", QBrush(QColor(255, 127, 80, 50)))
                for i in range(table.columnCount()):
                    it = table.item(new_row, i)
                    if it: 
                        it.setBackground(highlight_bg)
                        if i in [2, 3]:
                            f = it.font(); f.setBold(True); it.setFont(f)

            # [A4] 修复重复调用，闪烁新插入行
            self._flash_row(table, new_row)
            
            # [FIX] 不要在这里执行 sortByColumn，这会导致每一行插入都重排一次
            # 如果是批量插入，排序会在 _process_batch_signals 恢复时进行一次全局排序
                
        finally: 
            if was_sorting and not table.isSortingEnabled():
                table.setSortingEnabled(True)
            insert_dur = (time.perf_counter() - insert_start) * 1000
            if insert_dur > 20:
                 logger.debug(f"⚠️ [DASHBOARD_PERF] _insert_row cost {insert_dur:.1f}ms for {name}({code})")

    def _flash_row(self, table, row):
        try:
            items = [table.item(row, i) for i in range(table.columnCount())]
            if not items or not items[0]: return
            flash_bg = self._brushes.get("flash", QBrush(QColor(255, 255, 0, 60)))
            for item in items:
                if item: item.setBackground(flash_bg)
            
            def reset_bg():
                transparent = self._brushes.get("transparent", QBrush(QColor(0, 0, 0, 0)))
                for it in items:
                    try:
                        if it: it.setBackground(transparent)
                    except RuntimeError:
                        pass # Item was deleted from C++ side
            QTimer.singleShot(800, reset_bg)
        except: pass

    def _refresh_all_tables(self):
        """[PERF v4.0] 极致 O(N) 全量刷新，彻底根治 L2917 循环内的 O(N^2) 性能陷阱"""
        start_t = time.perf_counter()
        
        # 1. 预案锁定
        active_sortings = {}
        for name, table in self.tables.items():
            active_sortings[name] = table.isSortingEnabled()
            table.setUpdatesEnabled(False)
            table.blockSignals(True)
            table.setSortingEnabled(False)
            table.setRowCount(0) # 物理清空
            self._row_cache[table] = {} # 物理清理旧缓存
            
        try:
            # 2. 批量归类（内存操作，亚毫秒级）
            table_events = {name: [] for name in self.tables.keys()}
            for event in self._all_events:
                payload = event.payload
                # 简单复刻 _append_to_tables 的逻辑（仅分组）
                if event.event_type in [SignalBus.EVENT_PATTERN, SignalBus.EVENT_ALERT, SignalBus.EVENT_RISK]:
                    table_events["全部信号"].append(event)
                    
                    pattern = str(payload.get('pattern', payload.get('subtype', 'ALERT')) or '').lower()
                    detail = str(payload.get('detail', payload.get('message', '')) or '').lower()
                    
                    matched_cats = 0
                    for cat, keywords in CATEGORY_MAP.items():
                        if not keywords: continue
                        if any(kw.lower() in pattern or kw.lower() in detail for kw in keywords):
                            if cat in table_events:
                                table_events[cat].append(event)
                                matched_cats += 1
                    
                    if matched_cats == 0 and "其它信号" in table_events:
                        table_events["其它信号"].append(event)
                
            # 3. 物理灌入（O(N) 填充）
            for name, table in self.tables.items():
                # 引擎表通过 _update_engine_views 刷新，此处跳过
                if name in ["🌟 决策队列", "🐉 龙头追踪", "🔥 板块热力", "🌐 战略趋势", "📡 市场预警"]:
                    continue
                    
                events = table_events.get(name, [])
                # 限制最大展示量
                max_show = 500
                events = events[-max_show:]
                
                table.setRowCount(len(events))
                for i, ev in enumerate(events):
                    self._fill_row_data(table, i, ev.payload, timestamp=ev.timestamp)

        finally:
            for name, table in self.tables.items():
                table.blockSignals(False)
                table.setUpdatesEnabled(True)
                was_sorting = active_sortings.get(name, False)
                if was_sorting and name not in ["🌟 决策队列", "🐉 龙头追踪", "🔥 板块热力", "🌐 战略趋势"]:
                    table.setSortingEnabled(True)
                    # 仅对可见表进行一次性排序
                    if table.isVisible():
                        sort_col = getattr(table, '_sort_col', 0)
                        sort_order = getattr(table, '_sort_order', Qt.SortOrder.DescendingOrder)
                        self._sort_table_python(table, sort_col, sort_order)
                
                self._limit_table_column_widths(table)
                table.viewport().update()
                
        dur = (time.perf_counter() - start_t) * 1000
        logger.info(f"🔄 [DASHBOARD_PERF] Optimized Full refresh cost {dur:.1f}ms for {len(self._all_events)} events")

    def _fill_row_data(self, table, row_idx, p, timestamp=None):
        """纯粹的数据填充逻辑，不触发任何布局改变信号"""
        if timestamp:
            time_str = timestamp.strftime('%H:%M:%S')
        else:
            time_str = p.get('time', datetime.now().strftime('%H:%M:%S'))
        code = p.get('code', '')
        name = p.get('name', '')
        pattern = p.get('pattern', '')
        detail = p.get('detail', p.get('message', ''))
        grade = p.get('grade', '')
        score = p.get('score', 0.0)
        if pd.isna(score) or score is None:
            score = 0.0

        # 获取次数统计和报警状态
        count = self._stock_stats.get(code, {}).get("count", 1)
        is_alerted = get_alert_manager().is_alerted(code)
        display_name = f"🔔{name}" if is_alerted else name

        # 转换中文化形态/信号展示
        display_pattern = pattern
        for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
            if any(kw.lower() in pattern.lower() for kw in keywords):
                display_pattern = SIGNAL_TYPE_MAP.get(eng_key, pattern)
                break

        # 判断高亮和前景色
        is_highlight = "[重点]" in detail or "[重点]" in pattern
        default_color_key = self._get_pattern_color(pattern, detail, grade)
        
        # 确定常规列的前景色和背景色
        if is_alerted:
            cur_color_key = "#ffffff"
            cur_bg_key = "alert_bg"
        else:
            cur_color_key = default_color_key
            cur_bg_key = "highlight_bg" if is_highlight else None

        # 0. 时间
        self._fast_update_cell(table, row_idx, 0, time_str, color_key=cur_color_key, bg_key=cur_bg_key)

        # 1. 评级
        grade_bg = "alert_bg" if is_alerted else ("highlight_bg" if is_highlight else None)
        if grade in ['S', 'A']:
            grade_color = "#ff0000" if grade == 'S' else "#ffaa00"
            self._fast_update_cell(table, row_idx, 1, grade, color_key=grade_color, bold=True, bg_key=grade_bg)
        else:
            self._fast_update_cell(table, row_idx, 1, grade, bg_key=grade_bg)

        # 2. 代码 (预计算 search_blob)
        sector = p.get('sector', '')
        search_blob = f"{code} {name} {display_pattern} {detail} {sector}".lower()
        
        self._fast_update_cell(table, row_idx, 2, code, bold=True, color_key=cur_color_key, bg_key=cur_bg_key)
        it2 = table.item(row_idx, 2)
        if it2:
            it2.setData(self._ROLE_SEARCH_BLOB, search_blob)
            
            # 更新缓存
            table_cache = self._row_cache.setdefault(table, {})
            table_cache[code] = {
                'item': it2,
                'search_blob': search_blob,
                'pattern_raw': pattern
            }

        # 3. 名称
        self._fast_update_cell(table, row_idx, 3, display_name, bold=is_highlight, color_key=cur_color_key, bg_key=cur_bg_key)
        it3 = table.item(row_idx, 3)
        if it3:
            it3.setData(Qt.ItemDataRole.UserRole, sector)

        # 4. 形态与信号
        self._fast_update_cell(table, row_idx, 4, display_pattern, color_key=cur_color_key, bg_key=cur_bg_key)
        it4 = table.item(row_idx, 4)
        if it4:
            it4.setData(Qt.ItemDataRole.UserRole, pattern)

        # 5. 详情
        self._fast_update_cell(table, row_idx, 5, detail, color_key=cur_color_key, bg_key=cur_bg_key)

        # 6. 次数
        self._fast_update_cell(table, row_idx, 6, str(count), color_key=cur_color_key, bg_key=cur_bg_key, numeric_val=count)

        # 7. 得分
        self._fast_update_cell(table, row_idx, 7, str(int(score)), color_key=cur_color_key, bg_key=cur_bg_key, numeric_val=int(score))

    def _update_stats_display(self):
        total = len(self._all_events)
        
        # [FIX] 提前获取市场统计，确保无论是否有信号，后续逻辑都能安全访问
        market_up = self._market_stats.get('up', 0)
        market_down = self._market_stats.get('down', 0)
        prof_temp = self._market_stats.get('temperature')

        # [FIX] 不要因为没有信号就退出！市场温度和指数需要更新
        # [FIX] 无论当前窗口是否有新信号，都必须更新统计（确保清空或低频时 UI 准确）
        with self._data_lock: # ⭐ [FIX] 使用锁保护统计刷新
            # [UPGRADE] 顶部卡片现在直接读取表格行数，确保与状态栏和实际展示 100% 对齐，消除“窗口统计”与“持久化表格”的理解歧义
            def get_row_count(tab_name):
                tbl = self.tables.get(tab_name)
                return tbl.rowCount() if tbl else 0

            self.cards["follow"].setText(str(get_row_count("跟单信号")))
            self.cards["breakout"].setText(str(get_row_count("突破加速")))
            self.cards["risk"].setText(str(get_row_count("卖点预警")))
            self.cards["breakdown"].setText(str(get_row_count("结构破位")))
            self.cards["trap"].setText(str(get_row_count("尾盘诱多")))
            self.cards["other"].setText(str(get_row_count("其它信号")))

            
            # [NEW] 更新聚合预警统计 (展示全量预警条数以便观察系统活性)
            total_hub_count = len(self._hub_alerts)
            self.cards["alert_hub"].setText(str(total_hub_count))
            if total_hub_count > 0:
                # 如果有 S/A 级，显示深红警示，否则显示深蓝活跃色
                has_critical = any(a.get('grade') in ['S', 'A'] for a in self._hub_alerts)
                if has_critical:
                    self.cards["alert_hub"].setStyleSheet("background: #4B0000; color: #fff; border: 1px solid #ff4444;")
                else:
                    self.cards["alert_hub"].setStyleSheet("background: #001a33; color: #fff; border: 1px solid #00aaff;")
            else:
                self.cards["alert_hub"].setStyleSheet("background: #1a1c2c; color: #ddd; border: 1px solid #333;")

            # [Dragon] 更新龙头统计
            if self._engine_ctrl:
                d_counts = self._engine_ctrl.get_dragon_count()
                d_total = d_counts.get('dragon', 0)
                c_total = d_counts.get('candidate', 0)
                self.cards["dragon"].setText(str(d_total + c_total))
                
                # [MOD] 准备轮播消息池 (在这里更新变量，UI由定时器切换显示)
                self._carousel_messages = [
                    f"🕒 同步: {datetime.now().strftime('%H:%M:%S')} | 下次扫描: {self._get_next_scan_time()} |🐉: 真龙 {d_total} | 候选 {c_total}",
                    f"🔥 市场信号: F:{get_row_count('跟单信号')} | B:{get_row_count('突破加速')} | T:{get_row_count('尾盘诱多')} | R:{get_row_count('卖点预警')} | S:{get_row_count('结构破位')}",
                    f"🌡️ 盘中概况: 涨 {market_up} | 跌 {market_down} | 均温 {prof_temp if prof_temp else 'N/A'}℃"
                ]
                
                # [MOD] 动态获取各 Tab 行数用于状态栏展示
                counts_parts = []
                tab_to_count = ["🌟 决策队列", "全部信号", "跟单信号", "突破加速", "尾盘诱多", "买入机会", "卖点预警", "结构破位"]
                for t_name in tab_to_count:
                    tbl = self.tables.get(t_name)
                    if tbl:
                        # 简写映射
                        short_name = t_name.replace("信号", "").replace("🌟 ", "").replace("🔥 ", "").replace("🐉 ", "")
                        counts_parts.append(f"{short_name}: {tbl.rowCount()}")
                
                self.stats_info_label.setText(" | ".join(counts_parts))
                if hasattr(self, 'total_stat_label'):
                    self.total_stat_label.setText(f"全部: {get_row_count('全部信号')}")

        # 1. 通用计算多空比
        total_bull = self._stats_counters.get("bull", 0)
        total_bear = self._stats_counters.get("bear", 0)
        
        # 优先使用全市场涨跌比，因为它更稳定且反映大盘真实深度
        if market_up + market_down > 100:
            ratio = market_up / max(1, market_down)
        elif total_bull + total_bear > 0:
            ratio = total_bull / max(1, total_bear)
        else:
            ratio = 0.0 # 默认修正为0更符合逻辑
            
        # 2. 优先使用从 monitor 传来的专业市场温度评分
        if prof_temp is not None:
            temp_val = float(prof_temp)
            status = "冷清"
            if temp_val > 80: status = "火热"
            elif temp_val > 60: status = "活跃"
            elif temp_val > 40: status = "平淡"
            elif temp_val > 20: status = "低迷"
            else: status = "冰点"
            
            # [MOD] 状态栏综合显示：🌡️ 冰点 (15℃) | tab当前点击查看的视图的统计信息 | 🕒 21:33:59
            # 1. 获取当前 Tab 统计信息
            current_tab_name = self.tabs.tabText(self.tabs.currentIndex())
            tab_stat_info = ""
            if "🐉 龙头追踪" in current_tab_name:
                if self._engine_ctrl:
                    d_counts = self._engine_ctrl.get_dragon_count()
                    tab_stat_info = f"🐉 真龙:{d_counts.get('dragon', 0)} 候选:{d_counts.get('candidate', 0)}"
            else:
                table = self.tabs.currentWidget()
                if isinstance(table, QTableWidget):
                    tab_stat_info = f"📊 {current_tab_name.strip()}: {table.rowCount()}条"

            # 2. 组装展示文本 (固定模式，不再跳变)
            status_text = f"🌡️ {status} ({temp_val:.1f}°C) | {tab_stat_info} | 🕒 {datetime.now().strftime('%H:%M:%S')}"
            
            self.temp_label.setText(f"市场温度: {status} ({temp_val:.1f}°C)")
            self.ls_ratio_label.setText(f"多空比: {ratio:.2f}")
            
            summary = self._market_stats.get('summary', '')
            if summary:
                self.temp_label.setToolTip(summary)
            
            # [FIX] 更新状态栏显示
            self.status_label.setText(status_text)
            self.status_label.setToolTip(f"市场指数概况: {market_up}涨 / {market_down}跌")
            
            # 动态改色
            color = "#ddd"
            if temp_val > 80: color = "#ff4444" 
            elif temp_val > 60: color = "#ff8c00" 
            elif temp_val < 30: color = "#5bc0de" 
            self.temp_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            
            if hasattr(self, 'temp_bar'):
                self.temp_bar.setValue(int(temp_val))
        else:
            # 3. 降级使用信号比例计算 (修正以匹配专业风格)
            temp_status = "冰点"
            color = "#5bc0de" # 蓝色
            if ratio > 1.5: 
                temp_status = "活跃"; color = "#ff8c00"
            elif ratio > 0.8: 
                temp_status = "平淡"; color = "#ddd"
            elif ratio > 0.3: 
                temp_status = "低迷"; color = "#6c757d"
                
            self.temp_label.setText(f"市场温度: {temp_status}")
            self.ls_ratio_label.setText(f"多空比: {ratio:.2f} (采样比例)")
            
            self.temp_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            if hasattr(self, 'temp_bar'): 
                self.temp_bar.setValue(min(100, int(ratio * 40)))

        # 更新指数网格 (独立于信号数)
        indices_data = self._market_stats.get('indices', [])
        if indices_data and hasattr(self, 'idx_labels'):
            for idx_info in indices_data:
                name = idx_info.get('name', '')
                pct = idx_info.get('percent', 0.0)
                # 寻找匹配的标签 (简单匹配即可)
                name_key = name.replace("指数", "")
                for label_key, label_widget in self.idx_labels.items():
                    if label_key in name_key or name_key in label_key:
                        color = "#ff4444" if pct > 0 else "#44ff44" if pct < 0 else "#aaa"
                        label_widget.setText(f"{pct:+.2f}%")
                        label_widget.setStyleSheet(f"color: {color}; font-family: 'Consolas'; font-size: 10pt; font-weight: bold;")
                        break

        sorted_sectors = sorted(self._sector_heat.items(), key=lambda x: x[1], reverse=True)
        top_3 = []
        for s, c in sorted_sectors[:3]:
            if s == "其它":
                top_3.append(f'<a href="全部" style="color: #00FFCC; text-decoration: none;">全部: {c}</a>')
            else:
                top_3.append(f'<a href="{s}" style="color: #00FFCC; text-decoration: none;">{s}: {c}</a>')
        self.hot_sectors_label.setText(" | ".join(top_3) if top_3 else "暂无数据")
        self.hot_sectors_label.setTextFormat(Qt.TextFormat.RichText)
        
        # 更新底部统计信息 - 用于对比校验真实显示的表格行数结构
        follow_cnt = self.tables["跟单信号"].rowCount() if "跟单信号" in self.tables else 0
        breakout_cnt = self.tables["突破加速"].rowCount() if "突破加速" in self.tables else 0
        risk_cnt = self.tables["卖点预警"].rowCount() if "卖点预警" in self.tables else 0
        breakdown_cnt = self.tables["结构破位"].rowCount() if "结构破位" in self.tables else 0
        other_cnt = self.tables["其它信号"].rowCount() if "其它信号" in self.tables else 0
        total_cnt = self.tables["全部信号"].rowCount() if "全部信号" in self.tables else 0
        
        # [FIX] 使用清晰文案说明卡片展示的是历史信号流总数，而底部展示的是去重排版后的界面数据，消除数据理解误区。
        self.stats_info_label.setText(f"跟单:{follow_cnt} 突破:{breakout_cnt} 风险:{risk_cnt} 破位:{breakdown_cnt} | 总表可视数: {total_cnt}")

    def update_market_stats(self, stats: dict):
        try:
            # from PyQt6 import QtWidgets
            # app = QtWidgets.QApplication.instance()
            # if app: app.processEvents() # ⚡ [MINIMAL HEARTBEAT] 每次接收统计时驱动一次循环，确保 UI 活跃
            
            self._market_stats.update(stats)
            if hasattr(self, '_vol_dialog') and self._vol_dialog.isVisible(): self._vol_dialog.update_data(stats.get("vol_details", []))
            self.market_breadth_label.setText(f"📊 上涨:{stats.get('up', 0)} 下跌:{stats.get('down', 0)}")
            self.vol_stat_label.setText(f"🚀 放量:{stats.get('vol_up', 0)}")
            
            # [FIX] 显式触发全局统计刷新，确保温度计和指数网格即时更新
            self._update_stats_display()
        except Exception as e:
            logger.debug(f"Update market stats failed: {e}")

    def _on_card_clicked(self, key):
        # 1. 映射表定义
        mapping = {
            "alert_hub": "📡 市场预警", # [RESTORED] 联动新中枢
            "dragon": "🐉 龙头追踪",
            "follow": "跟单信号", 
            "breakout": "突破加速", 
            "trap": "尾盘诱多",
            "risk": "卖点预警", 
            "breakdown": "结构破位", 
            "other": "其它信号",
            "ALL": "全部信号"
        }
        
        tab_name = mapping.get(key)
        if tab_name:
            # 跳转到对应页签
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == tab_name:
                    self.tabs.setCurrentIndex(i)
                    break
            
            # 点击顶部卡片或右侧“全部”时，重置过滤器状态，确保看到完整数据
            if hasattr(self, 'type_filter'):
                idx = self.type_filter.findData("ALL")
                if idx >= 0:
                    self.type_filter.setCurrentIndex(idx)
            if hasattr(self, 'search_input'):
                self.search_input.clear()
            if hasattr(self, 'search_input'):
                self.search_input.clear()

    def _on_market_breadth_clicked(self, event):
        self._vol_dialog.update_data(self._market_stats.get("vol_details", []))
        self._vol_dialog.show()

    def _on_market_temp_clicked(self, event):
        """点击温度计弹出专业复盘详情窗口 - 异步稳定版"""
        try:
            # 1. 发布到总线作为日志/追踪 (不使用 return，因为主程序暂无监听器，仅作解耦记录)
            bus = get_signal_bus()
            if bus:
                bus.publish(SignalBus.EVENT_ALERT, "UI_ACTION", {"action": "open_market_pulse"})
                logger.info("📡 [UI] MarketPulse opening request published via SignalBus")

            # 2. 寻找主窗口并进行安全分发 (这是目前最可靠的跨框架打开方式)
            main_window = getattr(self, 'parent_app', None)
            if not main_window:
                for widget in QApplication.topLevelWidgets():
                    if hasattr(widget, 'open_market_pulse'):
                        main_window = widget
                        break
            
            if main_window:
                # ✅ [关键适配] 使用 tk_dispatch_queue 确保在 Tkinter 主线程执行，彻底规避 GIL 锁问题
                if hasattr(main_window, 'tk_dispatch_queue') and main_window.tk_dispatch_queue:
                    # 优先级最高：如果主程序提供了专门的 Tk 任务调度队列
                    main_window.tk_dispatch_queue.put(lambda: main_window.open_market_pulse())
                elif hasattr(main_window, 'after'):
                    # 备选：如果主程序是 Tkinter 对象但没有扩展队列
                    main_window.after(10, lambda: main_window.open_market_pulse())
                else:
                    # 纯 Qt 或其它环境：通过 QTimer 异步触发，避免当前调用栈冲突
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(10, lambda: main_window.open_market_pulse())
            else:
                logger.warning("⚠️ [UI] Failed to find main_window for open_market_pulse")
                    
        except Exception as e:
            logger.error(f"Failed to open MarketPulseViewer: {e}")

    def _on_vol_code_clicked(self, code, name):
        """处理异动放量窗口代码点击联动"""
        # 1. 触发仪表盘对外的主联动信号 (代码与名称)
        self.code_clicked.emit(code, name)
        # 2. 发送内部总线事件，以便总线相关组件也能同步
        self.sig_bus_event.emit(BusEvent(SignalBus.EVENT_PATTERN, datetime.now(), "VolDialog", {"code": code, "name": name}))

    def _emit_test_signal(self):
        """[SELF-TEST] 发送一个模拟的 Fast-Track 信号用于自检"""
        try:
            from signal_bus import get_signal_bus, SignalBus
            bus = get_signal_bus()
            bus.publish(
                event_type=SignalBus.EVENT_ALERT,
                source="SelfTest",
                payload={
                    "code": "000001", "name": "自检样本", "action": "突破/跟单", 
                    "pattern": "Fast-Track", "detail": "这是一条自检测试信号，验证总线与看板连通性",
                    "score": 99.0, "grade": "S"
                }
            )
            self.status_label.setText("✅ 自检信号已发出，请检查 [极速跟单] 分类")
        except Exception as e:
            self.status_label.setText(f"❌ 自检失败: {e}")

    def _on_hot_sectors_clicked(self, event):
        pass # Discarded, using linkActivated instead

    def _filter_by_sector(self, sector_name):
        self.tabs.setCurrentIndex(0)
        if sector_name == "全部":
            self.search_input.clear()
        else:
            self.search_input.setText(sector_name)
        self.status_label.setText(f"当前筛选板块: {sector_name}")

    def _on_cell_clicked(self, row, col):
        table = self.sender()
        # 动态获取列
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                t = header.text()
                if t in ["代码", "龙头"]: code_col = i
                elif t in ["名称", "龙头名称"]: name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it:
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

    def _on_selection_changed(self):
        """处理键盘上下键切换时的联动 - 带更新锁保护版"""
        if getattr(self, '_is_updating_ui', False): return
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        # 获取当前选中的行（取第一个）
        items = table.selectedItems()
        if not items: return
        row = items[0].row()
        
        # 动态查找当前表格的【代码】和【名称】所在列索引
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                text = header.text()
                if text in ["代码", "龙头"]: code_col = i
                elif text in ["名称", "龙头名称"]: name_col = i
        
        if code_col >= 0:
            c_it = table.item(row, code_col)
            n_it = table.item(row, name_col) if name_col >= 0 else None
            if c_it and c_it.text():
                self.code_clicked.emit(c_it.text(), n_it.text() if n_it else "")

    def _show_context_menu(self, pos):
        """通用右键菜单"""
        table = self.sender()
        if not isinstance(table, QTableWidget): return
        
        index = table.indexAt(pos)
        if not index.isValid(): return
        
        row = index.row()
        item = table.item(row, 0)
        if not item: return

        # 发现选中行
        sel_rows = sorted(list(set(i.row() for i in table.selectedItems())))
        if row not in sel_rows:
            table.selectRow(row)
            sel_rows = [row]

        # 动态获取代码
        code_col = -1
        name_col = -1
        for i in range(table.columnCount()):
            h = table.horizontalHeaderItem(i)
            if h:
                if h.text() in ["代码", "龙头"]: code_col = i
                elif h.text() in ["名称", "龙头名称"]: name_col = i
        
        if code_col == -1: return
        code = table.item(row, code_col).text()
        name = table.item(row, name_col).text() if name_col != -1 else ""

        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #1a1c2c; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #2a2d42; }")
        
        # 1. 复制
        copy_action = menu.addAction(f"📋 复制代码: {code}")
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(code))
        
        menu.addSeparator()

        # 2. DNA 审计
        title = f"🧬 执行 DNA 审计 ({len(sel_rows)}只...)" if len(sel_rows) > 1 else f"🧬 执行 DNA 审计"
        dna_action = menu.addAction(title)
        dna_action.triggered.connect(lambda: self._run_dna_audit_selected(table))

        menu.addSeparator()

        # 3. 大格局战略关注 (Macro Watchlist)
        # ⭐ [FIX] 即使初始化时没连上，右键点击时也尝试重新连接一次
        if self._engine_ctrl is None:
            self._engine_ctrl = get_engine_controller()

        if self._engine_ctrl:
            try:
                m_watchlist = self._engine_ctrl.get_macro_watchlist()
                if code in m_watchlist:
                    macro_action = menu.addAction(f"🛡️ 移除战略关注: {code}")
                    macro_action.triggered.connect(lambda: self._engine_ctrl.remove_from_macro_watchlist(code))
                else:
                    macro_action = menu.addAction(f"🌐 战略趋势重点关注: {code}")
                    macro_action.triggered.connect(lambda: self._engine_ctrl.add_to_macro_watchlist(code, name))
            except Exception as e:
                logger.error(f"❌ [Dashboard] Menu logic failed: {e}")

        menu.exec(table.viewport().mapToGlobal(pos))

    def _run_dna_audit_selected(self, source_table=None):
        """🚀 [DNA-BATCH] 极限审计：当前 Tab 选区 / Top20"""
        table = source_table if source_table else self.tabs.currentWidget()
        if not isinstance(table, QTableWidget): 
            # 兜底：如果是按钮触发且当前Tab没有Table（绝大多数Tab都有），则尝试获取当前
            table = self.tabs.currentWidget()
        
        if not isinstance(table, QTableWidget): return
        
        rowCount = table.rowCount()
        if rowCount == 0: return

        # 动态找出代码和名称列
        code_col, name_col = -1, -1
        for i in range(table.columnCount()):
            h = table.horizontalHeaderItem(i)
            if h:
                if h.text() in ["代码", "龙头"]: code_col = i
                elif h.text() in ["名称", "龙头名称"]: name_col = i
        
        if code_col == -1: return

        sel_rows = sorted(list(set(i.row() for i in table.selectedItems())))
        target_rows = []
        
        if len(sel_rows) > 1:
            target_rows = sel_rows[:50]
        elif len(sel_rows) == 1:
            start = sel_rows[0]
            target_rows = list(range(start, min(start + 20, rowCount)))
        else:
            target_rows = list(range(min(20, rowCount)))
            
        code_to_name = {}
        for r in target_rows:
            c_it = table.item(r, code_col)
            n_it = table.item(r, name_col) if name_col != -1 else None
            if c_it and c_it.text():
                c = c_it.text().strip()
                n = n_it.text().strip() if n_it else ""
                if c and c != "N/A":
                    code_to_name[c] = n
                    
        if code_to_name:
            # 这里的 SignalDashboard 一般被 MainWindow 挂载了 .parent_app
            main_app = getattr(self, 'parent_app', None)
            if main_app and hasattr(main_app, '_run_dna_audit_batch'):
                if hasattr(main_app, 'tk_dispatch_queue'):
                    # 🚀 [THREAD-SAFE] 通过 Tk 调度队列跨进程/线程安全调用
                    _cn = dict(code_to_name)  # 捕获闭包副本
                    main_app.tk_dispatch_queue.put(lambda: main_app._run_dna_audit_batch(_cn))
                else:
                    # 兜底：直接调用 (仅在缺失队列时)
                    main_app._run_dna_audit_batch(code_to_name)
            else:
                logger.error("No access to main monitor app for DNA audit.")

    def _on_cell_double_clicked(self, row, col):
        table = self.sender()
        
        # 自动探测 代码 和 名称 列的位置
        code_col, name_col = 1, 2 # 默认值
        for i in range(table.columnCount()):
            header = table.horizontalHeaderItem(i)
            if header:
                txt = header.text()
                if "代码" in txt: code_col = i
                elif "名称" in txt: name_col = i

        it_code = table.item(row, code_col)
        it_name = table.item(row, name_col)
        if not it_code or not it_name: return
        
        code, name = it_code.text().strip(), it_name.text().strip()
        clipboard = QApplication.clipboard()
        header = table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else ""
        
        if header == "详情":
            detail = table.item(row, col).text()
            # 动态寻找时间列 (通常在 0 或 1)
            time_str = table.item(row, 0).text() if table.columnCount() > 0 else ""
            try:
                from signal_dashboard_panel import SignalDetailDialog
                dialog = SignalDetailDialog(code, name, time_str, detail, self)
                dialog.exec()
            except: pass
            return
            
        if header == "代码": clipboard.setText(code)
        elif header == "名称": clipboard.setText(name)
        else: clipboard.setText(code)
        
        self.status_label.setText(f"📋 已复制: {clipboard.text()}")
        self.code_clicked.emit(code, name)

    def _get_snapshot_df(self):
        """[DATA] 尝试从宿主窗口或父应用获取最新的行情快照"""
        # 1. 尝试从父应用 (MonitorTK) 获取
        if hasattr(self, 'parent_app') and self.parent_app and hasattr(self.parent_app, 'df_all'):
            return self.parent_app.df_all
            
        # 2. 尝试从 Qt 窗口层级 (Visualizer MainWindow) 获取
        main_win = self.window()
        if hasattr(main_win, 'df_all'):
            return main_win.df_all
            
        return None

    def _on_search_text_changed(self, text):
        if not hasattr(self, '_search_timer'):
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.timeout.connect(self._apply_filter)
        self._search_timer.start(200)

    def _apply_filter(self):
        search_text = self.search_input.text().strip().lower()
        target_type_key = self.type_filter.currentData() or "ALL"
        
        # [FIX] 如果使用了下拉过滤且当前不在"全部信号"标签，则自动切到"全部信号"以防止交叉过滤导致全空
        if target_type_key != "ALL" and self.tabs.tabText(self.tabs.currentIndex()) != "全部信号":
            for i in range(self.tabs.count()):
                if self.tabs.tabText(i) == "全部信号":
                    self.tabs.blockSignals(True)
                    self.tabs.setCurrentIndex(i)
                    self.tabs.blockSignals(False)
                    break
                    
        table = self.tabs.currentWidget()
        if not isinstance(table, QTableWidget): return

        # [PERF] 锁定渲染，防止 setRowHidden 触发联排重算
        table.setUpdatesEnabled(False)
        table.viewport().setUpdatesEnabled(False)
        try:
            visible_count = 0
            # [PERF] A3: 使用预缓存的列映射
            col_map = getattr(table, '_col_map', {})
            code_col = col_map.get("代码", col_map.get("龙头", -1))
            name_col = col_map.get("名称", col_map.get("龙头名称", -1))
            pattern_col = col_map.get("形态类别", col_map.get("形态/信号", -1))
            sector_col = col_map.get("所属板块", -1)

            for row in range(table.rowCount()):
                row_visible = True
                code_item = table.item(row, code_col) if code_col >= 0 else None
                
                # 1. 文本搜索 (使用 A2 预计算的 blob)
                if search_text:
                    if code_item:
                        blob = str(code_item.data(self._ROLE_SEARCH_BLOB) or "").lower()
                        if not blob:
                            # 兼容性兜底：如果没 blob，则回退到拼接几个关键列
                            n_text = table.item(row, name_col).text().lower() if name_col >= 0 and table.item(row, name_col) else ""
                            s_text = table.item(row, sector_col).text().lower() if sector_col >= 0 and table.item(row, sector_col) else ""
                            blob = f"{code_item.text()} {n_text} {s_text}".lower()
                        
                        if search_text not in blob:
                            row_visible = False
                    else:
                        pass
                
                # 2. 类型下拉过滤 (保证逻辑与下拉框计数完全一致)
                if row_visible and target_type_key != "ALL" and pattern_col >= 0:
                    pattern_item = table.item(row, pattern_col)
                    if pattern_item:
                        raw_pattern = str(pattern_item.data(Qt.ItemDataRole.UserRole) or pattern_item.text())
                        matched_type = "ALERT"
                        for eng_key, keywords in SIGNAL_TYPE_KEYWORDS.items():
                            if any(kw.lower() in raw_pattern.lower() for kw in keywords):
                                matched_type = eng_key
                                break
                        row_visible = (matched_type == target_type_key)
                
                table.setRowHidden(row, not row_visible)
                if row_visible: visible_count += 1
            
            # [NEW] 搜索反馈：在状态栏显示匹配数
            if search_text or target_type_key != "ALL":
                self.status_label.setText(f"🔍 搜索/过滤结果: 在「{self.tabs.tabText(self.tabs.currentIndex())}」中找到 {visible_count} 条匹配")
            
            # [NEW] 手动搜索过滤后，自动滚动到顶部显示最新信号
            table.verticalScrollBar().setValue(0)
        finally:
            # [PERF] 恢复渲染
            table.viewport().setUpdatesEnabled(True)
            table.setUpdatesEnabled(True)

    def _on_tab_changed(self, index):
        """[MANUAL] 手动切换 Tab 时，应用搜索并回到顶部，同时检查是否需要补做延迟排序"""
        self._apply_filter() # 先根据搜索框内容过滤
        table = self.tabs.widget(index)
        if isinstance(table, QTableWidget):
            # [STEP-2 FIX] 如果该页签之前在后台累积了信号但未排序，现在补做
            if getattr(table, '_needs_sort', False):
                sort_col = getattr(table, '_sort_col', table.horizontalHeader().sortIndicatorSection())
                sort_order = getattr(table, '_sort_order', table.horizontalHeader().sortIndicatorOrder())
                self._sort_table_python(table, sort_col, sort_order)
                table._needs_sort = False
                
            table.verticalScrollBar().setValue(0) # 回到顶部
            
        # [🚀 性能优化] 切换 Tab 时主动刷新当前页，实现可见性门控的即时响应
        self._update_engine_views()

    def _on_search_context_menu(self, pos):
        """合并版：支持粘贴、清除、及测试信号"""
        from PyQt6.QtWidgets import QMenu, QApplication
        menu = QMenu()
        paste_act = menu.addAction("📋 粘贴并搜索")
        clear_act = menu.addAction("🧹 清除内容")
        menu.addSeparator()
        test_act = menu.addAction("🚀 发送并验证自检信号 (Fast-Track)")
        
        action = menu.exec(self.search_input.mapToGlobal(pos))
        if action == paste_act:
            self.search_input.setText(QApplication.clipboard().text().strip())
        elif action == clear_act:
            self.search_input.clear()
        elif action == test_act:
            self._emit_test_signal()

    def _clear_filters(self):
        """一键清空搜索框和下拉过滤状态"""
        self.search_input.clear()
        if self.type_filter.count() > 0:
            self.type_filter.setCurrentIndex(0)

    def _reset_signals(self):
        """重置所有信号数据与统计，开始新监控周期"""
        # 1. 清空基础数据结构
        self._all_events.clear()
        self._table_update_buffer.clear()
        self._stock_stats.clear()
        self._sector_heat.clear()
        
        # 2. 重置计数器
        for k in self._stats_counters: self._stats_counters[k] = 0
        for k in self._signal_type_counts: self._signal_type_counts[k] = 0
        self._market_stats = {"up": 0, "down": 0, "flat": 0, "vol_up": 0, "vol_down": 0, "vol_details": []}
        
        # 3. 清空 UI 表格
        for table in self.tables.values():
            table.setRowCount(0)
            
        # 4. 重置 UI 标签与卡片 (进入“等待同步”状态)
        for key, lbl in self.cards.items():
            lbl.setText("0")
            
        self.temp_label.setText("市场温度: 等待数据...")
        self.temp_bar.setValue(0)
        self.market_breadth_label.setText("📊 上涨:-- 下跌:--")
        self.vol_stat_label.setText("🚀 放量:--")
        self.ls_ratio_label.setText("多空比: --")
        self.hot_sectors_label.setText("等待数据...")
        self.stats_info_label.setText("跟单: 0 | 突破: 0 | 尾盘: 0 | 风险: 0 | 破位: 0 | 全部: 0")
        
        # 5. 刷新下拉框计数
        self._refresh_type_filter_items()
        self.status_label.setText("📊 信号面板已重置，等待新行情数据流入...")
        logger.info("SignalDashboard: User manual reset triggered.")

    def _on_engine_manual_run(self):
        """手动触发引擎全链路逻辑验证 (后台线程异步执行防卡死)"""
        self.status_label.setText("⚡ 正在执行引擎全链路重算...")
        self.manual_run_btn.setEnabled(False)
        
        def _worker():
            try:
                # 1. 触发引擎层强制重算
                from sector_focus_engine import get_focus_controller
                ctrl = get_focus_controller()
                if ctrl:
                    ctrl.manual_run()
                
                # 2. 触发信号中枢手动审计
                from signal_grading_hub import get_signal_grading_hub
                hub = get_signal_grading_hub()
                hub.force_report()
                
                # 3. [EFFECT] 发射一条强视觉反馈信号，展示中枢效果
                from signal_bus import get_signal_bus, SignalBus
                bus = get_signal_bus()
                
                # [🛡️ FIX] 修正 publish 调用方式，直接传递 payload 而不是 BusEvent 对象
                bus.publish(
                    SignalBus.EVENT_MARKET_ALERT,
                    source="ManualTest",
                    payload={
                        'timestamp': datetime.now().strftime("%H:%M:%S"),
                        'type': "系统手动审计",
                        'grade': "S",
                        'content': "🚀 引擎全链路验证成功！中枢预警已激活，当前处于实时监控状态。",
                        'temp': 50.0
                    }
                )

                # 4. 立即更新 UI 视图
                def _success():
                    self._update_engine_views()
                    self.status_label.setText("✅ 引擎重算与预警激活完成")
                    logger.info("📡 [UI] 仪表盘已通过手动触发完成引擎数据刷新与预警播报演示")
                    QTimer.singleShot(1500, lambda: self.manual_run_btn.setEnabled(True))
                    
                QTimer.singleShot(0, _success)
                
            except Exception as e:
                err_msg = f"❌ 重算失败: {e}"
                logger.error(f"📡 [UI] Manual run FAILED: {e}")
                import traceback
                traceback.print_exc()
                
                def _fail():
                    self.status_label.setText(err_msg)
                    QTimer.singleShot(1500, lambda: self.manual_run_btn.setEnabled(True))
                    
                QTimer.singleShot(0, _fail)

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _get_next_scan_time(self):
        """[Dragon] 计算下一个 30 分钟扫描节点"""
        now = datetime.now()
        cur_min_total = now.hour * 60 + now.minute
        # 交易节拍节点 (相对于 9:30 的偏移量)
        slots = [0, 30, 60, 90, 120, 240, 270, 300, 330] # 9:30, 10:00, 10:30...
        for s in slots:
            target_min = 570 + s
            if target_min > cur_min_total:
                h, m = target_min // 60, target_min % 60
                return f"{h:02d}:{m:02d}"
        return "15:00"

    def _update_status_carousel(self):
        """[MOD] 底部状态栏轮播逻辑"""
        if not self._carousel_messages:
            self.status_label.setText("⌛ 系统初始化中...")
            return
        self._carousel_idx = (self._carousel_idx + 1) % len(self._carousel_messages)
        self.status_label.setText(self._carousel_messages[self._carousel_idx])

    def _get_history_file_path(self):
        """获取预警历史存储路径"""
        config_dir = os.path.dirname(WINDOW_CONFIG_FILE)
        return os.path.join(config_dir, "market_alerts_history.json")

    def _load_alert_history(self):
        """[DATA] 从磁盘加载历史预警"""
        path = self._get_history_file_path()
        if not os.path.exists(path): return
        
        try:
            # 🚀 [ROBUST] 优先尝试 utf-8，失败则尝试 gbk (兼容 Windows 可能存在的历史遗留编码)
            content = None
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"⚠️ [Dashboard] Alert history encoding issue, falling back to GBK...")
                try:
                    with open(path, 'r', encoding='gbk', errors='ignore') as f:
                        content = f.read()
                except Exception as gbk_err:
                    logger.error(f"❌ [Dashboard] Failed to read alert history with GBK fallback: {gbk_err}")
            
            if content:
                try:
                    history = json.loads(content)
                except json.JSONDecodeError as jde:
                    logger.error(f"❌ [Dashboard] Alert history JSON corrupted: {jde}. Backing up and resetting...")
                    bak_path = path + ".bak"
                    try:
                        import shutil
                        if os.path.exists(bak_path):
                            os.remove(bak_path)
                        shutil.copy2(path, bak_path)
                        logger.info(f"💾 [Dashboard] Corrupted alert history backed up to {bak_path}")
                    except Exception as backup_err:
                        logger.error(f"⚠️ [Dashboard] Failed to backup corrupted alert history: {backup_err}")
                    
                    try:
                        os.remove(path)
                        logger.info(f"🧹 [Dashboard] Removed corrupted alert history file to force self-healing.")
                    except Exception as rm_err:
                        logger.error(f"⚠️ [Dashboard] Failed to remove corrupted alert history: {rm_err}")
                    history = []
                
                if isinstance(history, list):
                    # [FIX] 启动时物理去重：仅保留每个事件（内容+个股）的最顶层记录
                    unique_alerts = []
                    seen_keys = set()
                    # 假定文件存储顺序是 [Newest -> Oldest]
                    for alert in history:
                        content = alert.get('content') or alert.get('message', '')
                        metadata = alert.get('metadata', {})
                        codes = sorted(metadata.get('codes', []) or [])
                        key = f"{content}_{','.join(codes)}"
                        if key not in seen_keys:
                            unique_alerts.append(alert)
                            seen_keys.add(key)
                    
                    self._hub_alerts = unique_alerts[:500] # 最多保留 500 条
                    
                    # 💡 [HASH-INIT] 初始化读取内容后的历史指纹哈希，防止刚启动时的冗余写入
                    loaded_fingerprint = tuple((x.get("time", ""), x.get("code", ""), x.get("message", "")) for x in self._hub_alerts)
                    self._last_saved_hash = hash(loaded_fingerprint)
                    
                    logger.info(f"✅ [Dashboard] Loaded {len(self._hub_alerts)} unique alert history records.")
        except Exception as e:
            logger.error(f"❌ [Dashboard] Failed to load alert history: {e}")

    def _save_alert_history(self):
        """[DATA] 将当前预警持久化到磁盘 (原子替换写盘，保障文件不损坏，引入专属锁与 Windows 重试退避防 WinError 32)"""
        path = self._get_history_file_path()
        tmp_path = path + ".tmp"
        
        # 🛡️ [LOCK] 临界区上锁保护，彻底排除本进程多线程下的写冲突
        with self._history_write_lock:
            try:
                # [FIX] 只保存最近 500 条 (Newest at front)
                to_save = self._hub_alerts[:500]
                
                # 💡 [HASH-DEDUP] 计算当前数据的指纹哈希，防范无变动的重复写盘
                # 提取关键字段生成不可变特征元组以防 value dict 无法直接 hash
                current_fingerprint = tuple((x.get("time", ""), x.get("code", ""), x.get("message", "")) for x in to_save)
                current_hash = hash(current_fingerprint)
                
                if current_hash == self._last_saved_hash:
                    # 内容指纹完全一致，短路返回，零 IO 损耗！
                    return
                
                # 先写入临时文件，确保中途被切断时原文件完好无损
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(to_save, f, ensure_ascii=False, indent=2)
                
                # Windows 原子替换文件路径 (加入重试退避，抗御杀毒软件扫描及瞬间 IO 冲突)
                if os.path.exists(tmp_path):
                    for attempt in range(5):
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                            os.rename(tmp_path, path)
                            self._last_saved_hash = current_hash # 成功写入，更新哈希标记
                            break
                        except Exception as rename_err:
                            if attempt == 4:
                                raise rename_err
                            time.sleep(0.05) # 50ms 优雅回退
            except Exception as e:
                logger.error(f"❌ [Dashboard] Failed to save alert history: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SignalDashboardPanel()
    window.show()
    sys.exit(app.exec())
