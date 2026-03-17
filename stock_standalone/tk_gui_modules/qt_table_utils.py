# -*- coding: utf-8 -*-
import os
import json
import logging
import traceback
from datetime import datetime
from typing import Any, List, Optional, Union, Dict

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QAbstractItemView, QApplication, QStyledItemDelegate,
    QStyleOptionViewItem, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QByteArray, QSize
from PyQt6.QtGui import QColor, QFont, QAction, QBrush, QPainter, QPen
import pyqtgraph as pg

logger = logging.getLogger("qt_table_utils")

class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格项"""
    def __init__(self, value: Any):
        self._raw_value = value
        if isinstance(value, (int, float)):
            super().__init__(str(value))
        else:
            super().__init__(str(value))
            try:
                # 处理 "%", "+" 等干扰字符
                text = str(value).replace('%', '').replace('+', '').strip()
                if '(' in text:
                    text = text.split('(')[0].strip()
                self._raw_value = float(text)
            except (ValueError, TypeError):
                self._raw_value = value

    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        
        try:
            val_self = self._get_numeric_value()
            val_other = self._get_numeric_value(other)
            
            if isinstance(val_self, (int, float)) and isinstance(val_other, (int, float)):
                return val_self < val_other
        except:
            pass
            
        return super().__lt__(other)

    def _get_numeric_value(self, item=None):
        target = item if item is not None else self
        if hasattr(target, '_raw_value') and isinstance(target._raw_value, (int, float)):
            return target._raw_value
        
        text = target.text().replace('%', '').replace('+', '').strip()
        if '(' in text:
            text = text.split('(')[0].strip()
        try:
            return float(text)
        except:
            return text

class EnhancedTableWidget(QTableWidget):
    """
    增强型 QTableWidget，封装了常用的联动、排序、复制和右键菜单功能。
    """
    # 信号定义
    code_clicked = pyqtSignal(str, str)        # 单击联动 (代码, 名称)
    code_double_clicked = pyqtSignal(str, str) # 双击联动 (代码, 名称)
    
    def __init__(self, rows: int = 0, cols: int = 0, parent=None):
        super().__init__(rows, cols, parent)
        self._is_updating = False
        self._init_default_style()
        self._setup_connections()
        
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.set_theme(dark=True)

    def set_theme(self, dark: bool = True):
        """一键切换深浅色增强主题 (处理对比度)"""
        if dark:
            self.setStyleSheet("""
                QTableWidget {
                    background-color: #0d121f;
                    color: #ffffff;
                    gridline-color: #2a2d42;
                    selection-background-color: #3d425c;
                    selection-color: #00ffcc;
                    alternate-background-color: #161b2e;
                }
                QHeaderView::section {
                    background-color: #1a1c2c;
                    color: #aaa;
                    padding: 4px;
                    border: 0.5px solid #2a2d42;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("")
        # 默认使用深色增强主题 (符合系统调性)
        self.set_theme(dark=True)
        
    def set_theme(self, dark: bool = True):
        """一键切换深浅色增强主题"""
        if dark:
            self.setStyleSheet("""
                QTableWidget {
                    background-color: #0d121f;
                    color: #ffffff;
                    gridline-color: #2a2d42;
                    selection-background-color: #3d425c;
                    selection-color: #00ffcc;
                    alternate-background-color: #161b2e;
                }
                QHeaderView::section {
                    background-color: #1a1c2c;
                    color: #aaa;
                    padding: 4px;
                    border: 0.5px solid #2a2d42;
                    font-weight: bold;
                }
                QTableWidget::item:selected {
                    background-color: #3d425c;
                }
            """)
        else:
            self.setStyleSheet("") # 恢复默认
        
    def _setup_connections(self):
        """绑定内部事件"""
        self.itemClicked.connect(self._on_item_clicked)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
    def _on_item_clicked(self, item: QTableWidgetItem):
        if self._is_updating: return
        code, name = self._get_row_code_name(item.row())
        if code:
            self.code_clicked.emit(code, name)
            
    def _on_item_double_clicked(self, item: QTableWidgetItem):
        if self._is_updating: return
        code, name = self._get_row_code_name(item.row())
        if code:
            self.code_double_clicked.emit(code, name)
            
    def _on_selection_changed(self):
        if self._is_updating: return
        items = self.selectedItems()
        if items:
            row = items[0].row()
            code, name = self._get_row_code_name(row)
            if code:
                self.code_clicked.emit(code, name)
                
    def _get_row_code_name(self, row: int) -> tuple[Optional[str], str]:
        """获取指定行的代码和名称"""
        try:
            # 假设第一列是代码，第二列是名称（通用约定）
            code_item = self.item(row, 0)
            name_item = self.item(row, 1)
            code = code_item.text().strip() if code_item else None
            name = name_item.text().strip() if name_item else ""
            
            # 某些表可能带有图形图标，过滤掉
            if code and ' ' in code:
                code = code.split()[-1]
            return code, name
        except:
            return None, ""

    def _on_context_menu(self, pos: QPoint):
        """弹出标准右键菜单"""
        item = self.itemAt(pos)
        if not item: return
        
        row = item.row()
        col = item.column()
        code, name = self._get_row_code_name(row)
        cell_text = item.text()
        
        menu = QMenu(self)
        
        # 复制操作
        copy_code_act = QAction(f"复制代码 ({code})", self)
        copy_code_act.triggered.connect(lambda: QApplication.clipboard().setText(code))
        menu.addAction(copy_code_act)
        
        copy_name_act = QAction(f"复制名称 ({name})", self)
        copy_name_act.triggered.connect(lambda: QApplication.clipboard().setText(name))
        menu.addAction(copy_name_act)
        
        copy_cell_act = QAction(f"复制单元格: {cell_text[:10]}...", self)
        copy_cell_act.triggered.connect(lambda: QApplication.clipboard().setText(cell_text))
        menu.addAction(copy_cell_act)
        
        menu.addSeparator()
        
        # 联动操作 (如果外部有特殊需求可以扩展)
        link_tdx_act = QAction("⚡ 联动至 TDX", self)
        link_tdx_act.triggered.connect(lambda: self.code_clicked.emit(code, name))
        menu.addAction(link_tdx_act)
        
        menu.exec(self.viewport().mapToGlobal(pos))

    def flash_row(self, row: int, color_hex: str = "#FFFF00", alpha: int = 60, duration_ms: int = 800):
        """让指定行闪烁（背景色高亮后恢复）"""
        try:
            items = [self.item(row, i) for i in range(self.columnCount())]
            if not items or not items[0]: return
            
            highlight = QBrush(QColor(color_hex))
            highlight.color().setAlpha(alpha)
            
            for item in items:
                if item: item.setBackground(highlight)
            
            def reset_bg():
                for it in items:
                    try:
                        if it: it.setBackground(QBrush(QColor(0, 0, 0, 0)))
                    except RuntimeError: pass 
            
            QTimer.singleShot(duration_ms, reset_bg)
        except: pass

    def safe_clear(self):
        """线程安全的清空表格数据"""
        self._is_updating = True
        self.setSortingEnabled(False)
        self.setRowCount(0)
        self.setSortingEnabled(True)
        self._is_updating = False

    def get_selected_code(self) -> Optional[str]:
        """快速获取当前选中行的代码"""
        row = self.currentRow()
        if row >= 0:
            code, _ = self._get_row_code_name(row)
            return code
        return None

# ==============================================================================
# 自定义委派与弹窗 (UI 强化)
# ==============================================================================

class TrendDelegate(QStyledItemDelegate):
    """自定义委派：在单元格内绘制图形化分时走势和均价线"""
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        pdata = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(pdata, dict) or 'prices' not in pdata:
            super().paint(painter, option, index)
            return

        prices = pdata['prices']
        last_close = pdata.get('last_close', 0)
        
        if not prices and last_close <= 0:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        margin_h, margin_v = 4, 4
        draw_rect = rect.adjusted(margin_h, margin_v, -margin_h, -margin_v)
        
        display_prices = list(prices)
        if not display_prices:
            now_p = pdata.get('now_price', last_close)
            if now_p > 0:
                display_prices = [now_p, now_p]
            else:
                painter.restore()
                return

        if len(display_prices) == 1:
            if last_close > 0:
                display_prices = [last_close] + display_prices
            else:
                display_prices = [display_prices[0], display_prices[0]]

        p_min, p_max = min(display_prices), max(display_prices)
        if last_close > 0:
            p_min, p_max = min(p_min, last_close), max(p_max, last_close)
            
        rng = p_max - p_min if p_max > p_min else p_max * 0.01
        if rng == 0: rng = 1.0
        
        def to_y(p):
            val = (p - (p_min - rng*0.1)) / (rng * 1.2)
            return draw_rect.bottom() - val * draw_rect.height()

        # 1. 绘制昨收基准线
        if last_close > 0:
            y_lc = to_y(last_close)
            painter.setPen(QPen(QColor(64, 156, 255, 180), 1, Qt.PenStyle.DotLine))
            painter.drawLine(draw_rect.left(), int(y_lc), draw_rect.right(), int(y_lc))

        # 2. 绘制分时线
        base_ref = (last_close if last_close > 0 else display_prices[0])
        pen_color = QColor(255, 68, 68) if display_prices[-1] >= base_ref else QColor(68, 255, 68)
        painter.setPen(QPen(pen_color, 1.5))
        
        if len(display_prices) >= 2:
            step = draw_rect.width() / (len(display_prices) - 1)
            for i in range(len(display_prices) - 1):
                x1 = draw_rect.left() + i * step
                y1 = to_y(display_prices[i])
                x2 = draw_rect.left() + (i + 1) * step
                y2 = to_y(display_prices[i+1])
                painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
                
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(80, 28)

from tk_gui_modules.window_mixin import WindowMixin

class TimeAxisItem(pg.AxisItem):
    """自定义时间轴，支持索引到时间的映射"""
    def __init__(self, ts_list, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ts_list = ts_list

    def tickStrings(self, values, scale, spacing):
        ticks = []
        for v in values:
            idx = int(v)
            if 0 <= idx < len(self.ts_list):
                ts = self.ts_list[idx]
                try:
                    dt = datetime.fromtimestamp(ts)
                    if len(self.ts_list) > 240 or (self.ts_list[-1] - self.ts_list[0] > 86400):
                        ticks.append(dt.strftime('%m-%d %H:%M'))
                    else:
                        ticks.append(dt.strftime('%H:%M'))
                except:
                    ticks.append("")
            else:
                ticks.append("")
        return ticks

class DetailedChartDialog(QDialog, WindowMixin):
    """标准分时详情弹窗 (支持成交量、多重参考线及窗口位置持久化)"""
    def __init__(self, code, name, klines, meta, parent=None):
        super().__init__(parent)
        self.code_target = code  # 为 WindowMixin 提供标识
        
        # 提取元数据
        last_close = meta.get('last_close', 0)
        theme = meta.get('theme', 'N/A')
        emotion = meta.get('emotion', 50.0)
        pop = meta.get('popularity', 'N/A')
        
        # 计算涨跌幅
        curr_price = klines[-1].get('close', 0) if klines else 0
        pc = (curr_price - last_close) / last_close * 100 if last_close > 0 else 0
        
        self.setWindowTitle(f"📊 {name} ({code}) | 涨幅:{pc:+.2f}% | 人气:{pop} | 题材:{theme}")
        self.resize(1100, 700)
        self._init_ui(code, name, klines, meta, pc)
        
    def _init_ui(self, code, name, klines, meta, pc):
        lay = QVBoxLayout(self)
        
        # 顶部信息栏
        info_lay = QHBoxLayout()
        pc_color = '#ff4444' if pc >= 0 else '#44cc44'
        emotion = meta.get('emotion', 50.0)
        theme = meta.get('theme', 'N/A')
        
        info_lbl = QLabel(
            f"<b>{name} ({code})</b> | 涨幅: <font color='{pc_color}'><b>{pc:+.2f}%</b></font> | "
            f"题材: <font color='#409cff'>{theme}</font> | 实时情绪: <font color='#ff9900'>{emotion:.1f}</font>"
        )
        info_lbl.setFont(QFont("Microsoft YaHei", 10))
        info_lay.addWidget(info_lbl)
        info_lay.addStretch()
        lay.addLayout(info_lay)
        
        # 恢复窗口位置
        try:
            self.load_window_position_qt(self, f"chart_{code}")
        except: pass

        # 补全逻辑：竞价或刚开盘没有分钟 K 时
        if not klines:
            import time
            last_c = meta.get('last_close', 0)
            now_p = meta.get('now_price', last_c)
            base_ts = time.time()
            if now_p > 0:
                klines = [{'time': base_ts - 60, 'close': now_p, 'volume': 0}, {'time': base_ts, 'close': now_p, 'volume': 0}]
            elif last_c > 0:
                klines = [{'time': base_ts - 60, 'close': last_c, 'volume': 0}, {'time': base_ts, 'close': last_c, 'volume': 0}]
            else:
                lay.addWidget(QLabel("暂无分时数据"))
                return

        if len(klines) == 1:
            k = klines[0]
            k_prev = k.copy()
            if isinstance(k_prev.get('time'), (int, float)): k_prev['time'] -= 60
            klines = [k_prev, k]

        prices = [float(k.get('close', 0)) for k in klines]
        vols = [float(k.get('volume', 0)) for k in klines]
        raw_times = [float(k.get('time', 0)) for k in klines]
        times = list(range(len(prices)))
        
        # 价格图
        self.pw = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(ts_list=raw_times, orientation='bottom')})
        self.pw.setBackground('#0d1b2a')
        self.pw.showGrid(x=True, y=True, alpha=0.3)
        lay.addWidget(self.pw, stretch=3)
        
        last_close = meta.get('last_close', 0)
        
        # 绘制主线
        p_color = '#FF4444' if (last_close > 0 and prices[-1] >= last_close) or (prices[-1] >= prices[0]) else '#44CC44'
        self.pw.plot(times, prices, pen=pg.mkPen(p_color, width=2.5))
        
        # 均价线
        avg_price = [sum(prices[:i+1])/(i+1) for i in range(len(prices))]
        self.pw.plot(times, avg_price, pen=pg.mkPen('#FFFF00', width=1, style=Qt.PenStyle.DashLine))

        if last_close > 0:
            inf_lc = pg.InfiniteLine(pos=last_close, angle=0, pen=pg.mkPen('#409cff', width=1, style=Qt.PenStyle.DashLine))
            self.pw.addItem(inf_lc)
            
        # 成交量图
        self.vw = pg.PlotWidget(axisItems={'bottom': TimeAxisItem(ts_list=raw_times, orientation='bottom')})
        self.vw.setBackground('#0d1b2a')
        self.vw.showGrid(x=True, y=True, alpha=0.3)
        self.vw.setXLink(self.pw) # 联动 X 轴
        lay.addWidget(self.vw, stretch=1)
        
        # 绘制成交量柱状图
        brushes = [pg.mkBrush('#FF4444' if i > 0 and prices[i] >= prices[i-1] else '#44CC44') for i in range(len(times))]
        bg = pg.BarGraphItem(x=times, height=vols, width=0.6, brushes=brushes)
        self.vw.addItem(bg)

    def closeEvent(self, event):
        """关闭时保存位置"""
        try:
            self.save_window_position_qt(self, f"chart_{self.code_target}")
        except: pass
        super().closeEvent(event)

# ==============================================================================
# 通用 UI 辅助方法
# ==============================================================================

def save_table_header_state(table: QTableWidget, key: str, config_file: str):
    """保存表格列状态到配置文件"""
    try:
        header = table.horizontalHeader()
        state = header.saveState().toHex().data().decode()
        
        data = {}
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        
        if "ui_states" not in data: data["ui_states"] = {}
        data["ui_states"][key] = state
        
        with os.fdopen(os.open(config_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Failed to save table state for {key}: {e}")

def restore_table_header_state(table: QTableWidget, key: str, config_file: str):
    """从配置文件恢复表格列状态"""
    try:
        if not os.path.exists(config_file): return
        
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        state = data.get("ui_states", {}).get(key)
        if state:
            val = QByteArray.fromHex(state.encode())
            table.horizontalHeader().restoreState(val)
    except Exception as e:
        logger.error(f"Failed to restore table state for {key}: {e}")
