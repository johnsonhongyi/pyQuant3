# -*- coding: utf-8 -*-
"""
Sector Bidding Panel v3 - 竞价及尾盘板块联动监控面板
优化：紧凑布局、表格排序、TDX/可视化器联动、窗口位置持久化
"""
import logging
from datetime import datetime
from typing import Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QDoubleSpinBox, QSpinBox, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QGroupBox, QToolBar, QSizePolicy, QPushButton, QFrame,
    QStyledItemDelegate, QStyleOptionViewItem, QDialog, QLineEdit,
    QMessageBox, QFileDialog, QAbstractItemView, QCalendarWidget, QStyle
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPoint, QRect, QThread, pyqtSignal, QObject, QByteArray, QDate, QEvent
from PyQt6.QtGui import QColor, QFont, QAction, QPen, QPainter, QTextCharFormat
import pyqtgraph as pg
import numpy as np

from tk_gui_modules.window_mixin import WindowMixin
try:
    from bidding_momentum_detector import BiddingMomentumDetector
    from JohnsonUtil import commonTips as cct
except ImportError:
    from stock_standalone.bidding_momentum_detector import BiddingMomentumDetector
    from stock_standalone.JohnsonUtil import commonTips as cct
# [REMOVED] DataHubService Imports
import time
import re
import os
import json
import traceback

from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE

logger = logging.getLogger(__name__)

SETTINGS_SECTION = "sector_bidding_panel_persistence"


def _ascii_kline(klines: List[dict], width: int = 24, last_close: float = 0) -> str:
    """最近 N 根分钟 K 线 → 文字条形迷你图"""
    if not klines:
        return "─" * width
    closes = [float(k.get('close', 0)) for k in klines[-width:]]
    if not closes:
        return "─" * width
    
    # [NEW] 如果只有 1 根 K 线但有昨收，将昨收作为第一条，形成对比
    if len(closes) == 1 and last_close > 0:
        closes = [last_close] + closes

    mn, mx = min(closes), max(closes)
    if mx == mn:
        return "─" * len(closes)
    bars = '▁▂▃▅▇'
    return ''.join(bars[min(4, int((c - mn) / (mx - mn) * 4.99))] for c in closes)


class SearchHistoryDelegate(QStyledItemDelegate):
    """自定义委托：为 QComboBox 下拉项添加右侧删除按钮"""
    delete_clicked = pyqtSignal(int)
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        # 1. 绘制标准背景与文字
        super().paint(painter, option, index)
        
        # 保护常驻项
        if index.data() == "龙头":
            return
            
        # 2. 绘制右侧 'x' 按钮
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 计算按钮区域 (右侧 28 像素宽)
        btn_rect = self.get_btn_rect(option)
        
        # 判定状态
        is_hovered = option.state & QStyle.StateFlag.State_Selected
        
        # [NEW] 绘制微透明圆形衬底，增加点击反馈感
        if is_hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 68, 68, 45)) # 淡淡的珊瑚红背景
            # 按钮中心绘制圆形
            circle_r = 10
            painter.drawEllipse(btn_rect.center(), circle_r, circle_r)
        
        # [NEW] 精致化 'x' 图标
        painter.setPen(QPen(QColor("#FF4444" if is_hovered else "#929292"), 1.8))
        
        icon_margin = 9
        painter.drawLine(btn_rect.left() + icon_margin, btn_rect.top() + icon_margin,
                         btn_rect.right() - icon_margin, btn_rect.bottom() - icon_margin)
        painter.drawLine(btn_rect.right() - icon_margin, btn_rect.top() + icon_margin,
                         btn_rect.left() + icon_margin, btn_rect.bottom() - icon_margin)
        
        painter.restore()

    @staticmethod
    def get_btn_rect(option: QStyleOptionViewItem) -> QRect:
        r = option.rect
        btn_w = 28
        return QRect(r.right() - btn_w, r.top(), btn_w, r.height())

    # [REMOVED] editorEvent 交互逻辑移至 Panel 的 eventFilter 中处理以提高稳定性


class NumericTableWidgetItem(QTableWidgetItem):
    """支持数值排序的表格项"""
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        try:
            # 提取主要数值：处理 "38.5 (↑1.2)" 这种格式，只取前面的 38.5
            def get_val(item):
                text = item.text().replace('%', '').replace('+', '').strip()
                if '(' in text:
                    text = text.split('(')[0].strip()
                return float(text)
            
            return get_val(self) < get_val(other)
        except (ValueError, TypeError, IndexError):
            return super().__lt__(other)


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
            # 将价格限制在绘图区内，保留 10% 的上下缓冲
            val = (p - (p_min - rng*0.1)) / (rng * 1.2)
            return draw_rect.bottom() - val * draw_rect.height()

        # 1. 绘制昨收基准线 (蓝色虚线)
        if last_close > 0:
            y_lc = to_y(last_close)
            painter.setPen(QPen(QColor(64, 156, 255, 180), 1, Qt.PenStyle.DotLine))
            painter.drawLine(draw_rect.left(), int(y_lc), draw_rect.right(), int(y_lc))

        # 2. 绘制黄色均价线 (点划线)
        p_avg = sum(display_prices) / len(display_prices)
        y_avg = to_y(p_avg)
        painter.setPen(QPen(QColor(255, 255, 0, 150), 1, Qt.PenStyle.DashDotLine))
        painter.drawLine(draw_rect.left(), int(y_avg), draw_rect.right(), int(y_avg))

        # 3. 绘制微型成交量柱状图 (底部 25% 区域)
        vols = pdata.get('volumes', [])
        if vols:
            v_max = np.percentile(vols, 98) if len(vols) > 5 else max(vols)
            if v_max <= 0: v_max = 1.0
            v_rect = draw_rect.adjusted(0, int(draw_rect.height() * 0.75), 0, 0)
            
            v_step = v_rect.width() / max(1, len(vols) - 1) if len(vols) > 1 else v_rect.width()
            for i, v in enumerate(vols):
                vh = (v / v_max) * v_rect.height()
                vx = v_rect.left() + i * v_step
                vy = v_rect.bottom() - vh
                
                # 颜色逻辑：对应价格升降
                is_up = True
                if i > 0 and i < len(display_prices):
                    is_up = display_prices[i] >= display_prices[i-1]
                
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(255, 68, 68, 120) if is_up else QColor(68, 255, 68, 120))
                painter.drawRect(int(vx), int(vy), max(1, int(v_step - 1)), int(vh))

        # 4. 绘制价格走势线 (红/绿)
        base_ref = (last_close if last_close > 0 else display_prices[0])
        pen_color = QColor(255, 68, 68) if display_prices[-1] >= base_ref else QColor(68, 255, 68)
        painter.setPen(QPen(pen_color, 1.8))
        
        if len(display_prices) >= 2:
            step = draw_rect.width() / (len(display_prices) - 1)
            for i in range(len(display_prices) - 1):
                x1 = draw_rect.left() + i * step
                y1 = to_y(display_prices[i])
                x2 = draw_rect.left() + (i + 1) * step
                y2 = to_y(display_prices[i+1])
                painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
        elif len(display_prices) == 1:
            y = to_y(display_prices[0])
            painter.drawLine(draw_rect.left(), int(y), draw_rect.right(), int(y))
            
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(85, 30)



class SBCTestThread(QThread):
    """SBC 模式验证后台线程，防止 GUI 卡死"""
    finished_data = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, code: str, use_live: bool, hdf5_lock=None, extra_lines=None):
        super().__init__()
        self.code = code
        self.use_live = use_live
        self.hdf5_lock = hdf5_lock
        self.extra_lines = extra_lines

    def run(self):
        try:
            try:
                import verify_sbc_pattern
            except ImportError:
                from stock_standalone import verify_sbc_pattern
            # 调用验证函数，不开启可视化(同步弹窗)，仅返回计算结果包
            result = verify_sbc_pattern.verify_with_real_data(
                self.code, 
                use_live=self.use_live, 
                show_viz=False,
                hdf5_lock=self.hdf5_lock,
                extra_lines=self.extra_lines
            )
            if result and isinstance(result, dict):
                self.finished_data.emit(result)
            else:
                self.error_occurred.emit(f"未能获取 {self.code} 的验证数据或数据格式不正确")
        except Exception as e:
            import traceback
            error_msg = f"SBC 线程执行失败: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self.error_occurred.emit(error_msg)


class TimeAxisItem(pg.AxisItem):
    """自定义时间轴，支持索引到时间的映射，消除非交易时段空隙"""
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
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts)
                    # 如果跨度超过一天，显示日期；否则仅显示时间
                    if len(self.ts_list) > 240 or (self.ts_list[-1] - self.ts_list[0] > 86400):
                        ticks.append(dt.strftime('%m-%d %H:%M'))
                    else:
                        ticks.append(dt.strftime('%H:%M'))
                except Exception:
                    ticks.append("")
            else:
                ticks.append("")
        return ticks



class DetailedChartDialog(QDialog, WindowMixin):
    """双击弹出的详细分时图窗口 (带成交量、多重参考线及全量实时数据)"""
    def __init__(self, code, name, klines, meta, parent=None):
        super().__init__(parent)
        self.code_target = code # 为 WindowMixin 提供唯一标识
        self.setWindowTitle(f"📊 分时详情: {name} ({code})")
        
        # 提取附加信息 (从 meta 或 DataPublisher 获取)
        pop = meta.get('popularity', 'N/A')
        emotion = meta.get('emotion', 50.0)
        topic = meta.get('theme', 'N/A')
        last_close = meta.get('last_close', 0)
        
        # 计算当前涨跌幅
        curr_price = klines[-1].get('close', 0) if klines else 0
        pc = 0.0
        if last_close > 0 and curr_price > 0:
            pc = (curr_price - last_close) / last_close * 100
        
        self.setWindowTitle(f"📊 {name} ({code}) | 涨幅:{pc:+.2f}% | 人气:{pop} | 题材:{topic}")
        self.resize(1100, 700)
        lay = QVBoxLayout(self)
        
        # 顶部信息栏
        info_lay = QHBoxLayout()
        pc_color = '#ff4444' if pc >= 0 else '#44cc44'
        info_lbl = QLabel(
            f"<b>{name} ({code})</b> | 涨幅: <font color='{pc_color}'><b>{pc:+.2f}%</b></font> | "
            f"题材: <font color='#409cff'>{topic}</font> | 实时情绪: <font color='#ff9900'>{emotion:.1f}</font>"
        )
        info_lbl.setFont(QFont("Microsoft YaHei", 11))
        info_lay.addWidget(info_lbl)
        info_lay.addStretch()
        lay.addLayout(info_lay)
        
        # [NEW] Restore Geometry
        self._restore_geometry()
        
        # [NEW] 补全模拟 K 线逻辑：竞价或刚开盘没有分钟 K 时，至少显示一段平线
        if not klines:
            last_c = meta.get('last_close', 0)
            now_p = meta.get('now_price', last_c) 
            # 尝试获取基准时间，历史模式下使用 snapshot 时间，实时模式下使用当前时间
            parent = self.parent() if hasattr(self, 'parent') else None
            detector = getattr(parent, 'detector', None) if parent else None
            base_ts = getattr(detector, 'baseline_time', time.time()) if detector else time.time()
            if not base_ts or base_ts <= 0: base_ts = time.time()

            if now_p > 0:
                # 模拟两个点形成一条直线，使用 Unix 时间戳
                klines = [
                    {'time': base_ts - 60, 'close': now_p, 'volume': 0},
                    {'time': base_ts, 'close': now_p, 'volume': 0}
                ]
            elif last_c > 0:
                klines = [
                    {'time': base_ts - 60, 'close': last_c, 'volume': 0},
                    {'time': base_ts, 'close': last_c, 'volume': 0}
                ]
            else:
                return # 彻底没数据
        
        # [FIX] 如果只有一个点，模拟成两个点以确保护眼可见的线段
        if len(klines) == 1:
            k = klines[0]
            k_prev = k.copy()
            # 时间戳减去一分钟，如果是数值则减 60，如果是字符串则保持
            if isinstance(k_prev.get('time'), (int, float)):
                k_prev['time'] -= 60
            klines = [k_prev, k]

        # 提取数据，增强对非数字时间戳的兼容
        prices = [float(k.get('close', 0)) for k in klines]
        vols = [float(k.get('volume', 0)) for k in klines]
        
        raw_times = []
        for k in klines:
            t_val = k.get('time', 0)
            try:
                raw_times.append(float(t_val))
            except (ValueError, TypeError):
                # 如果依然是字符串格式，尝试 fallback (虽然上面已修复，但此处做二重保险)
                raw_times.append(time.time())
        times = list(range(len(prices)))
        
        # 使用自定义时间轴 (传入原始时间序列)
        self.pw = pg.PlotWidget(
            title=f"分时走势与成交量 (样本数:{len(klines)})",
            axisItems={'bottom': TimeAxisItem(ts_list=raw_times, orientation='bottom')}
        )
        self.pw.setBackground('#0d1b2a')
        self.pw.showGrid(x=True, y=True, alpha=0.3)
        lay.addWidget(self.pw)
        
        # 存储初始数据和元信息
        self.meta = meta
        self.name = name
        self._current_klines_len = 0
        
        # 初始渲染
        self._render_chart(klines)
        
        # [NEW] Restore Geometry
        self._restore_geometry()
        
        # [NEW] 动态定时刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.update_live_data)
        
        # 使用配置中的刷新间隔 (s -> ms)
        try:
            interval = float(getattr(cct.CFG, 'duration_sleep_time', 5.0))
            if interval < 1.0: interval = 1.0
        except:
            interval = 5.0
        self._refresh_timer.start(int(interval * 1000)) 

    def _render_chart(self, klines):
        """核心渲染逻辑，支持重用"""
        if not klines: return
        self._current_klines_len = len(klines)
        
        # 清理旧图形
        self.pw.clear()
        
        # 提取数据
        prices = [float(k.get('close', 0)) for k in klines]
        vols = [float(k.get('volume', k.get('vol', 0))) for k in klines]
        
        raw_times = []
        for k in klines:
            t_val = k.get('time', 0)
            try:
                raw_times.append(float(t_val))
            except (ValueError, TypeError):
                raw_times.append(time.time())
        times = list(range(len(prices)))
        
        # 更新时间轴
        axis_bottom = self.pw.getAxis('bottom')
        if hasattr(axis_bottom, 'ts_list'):
            axis_bottom.ts_list = raw_times
        
        last_close = self.meta.get('last_close', 0)
        high_day = self.meta.get('high_day', 0)
        low_day = self.meta.get('low_day', 0)
        last_high = self.meta.get('last_high', 0)
        last_low = self.meta.get('last_low', 0)

        # 比例与美化优化：Y轴范围
        y_min = min(prices) if prices else 0
        y_max = max(prices) if prices else 0
        if high_day > 0: y_max = max(y_max, high_day)
        if low_day > 0: y_min = min(y_min, low_day)
        if last_close > 0:
            y_min = min(y_min, last_close)
            y_max = max(y_max, last_close)
        
        if y_max > y_min:
            padding = (y_max - y_min) * 0.1
        else:
            padding = y_min * 0.05 if y_min > 0 else 1.0
        self.pw.setYRange(y_min - padding, y_max + padding, padding=0)
        
        # 1. 昨收/昨日最高/最低参考线
        if last_close > 0:
            inf_lc = pg.InfiniteLine(pos=last_close, angle=0, pen=pg.mkPen('#409cff', width=1, style=Qt.PenStyle.DashLine), 
                                     label="昨收 {value:.2f}", labelOpts={'position': 0.9, 'color': '#409cff'})
            self.pw.addItem(inf_lc)
        
        if last_high > 0 and last_high != last_close:
            inf_lh = pg.InfiniteLine(pos=last_high, angle=0, pen=pg.mkPen('#ff4444', width=0.8, style=Qt.PenStyle.DotLine), 
                                     label="昨高", labelOpts={'position': 0.8})
            self.pw.addItem(inf_lh)
            
        if last_low > 0 and last_low != last_close:
            inf_ll = pg.InfiniteLine(pos=last_low, angle=0, pen=pg.mkPen('#44cc44', width=0.8, style=Qt.PenStyle.DotLine), 
                                     label="昨低", labelOpts={'position': 0.8})
            self.pw.addItem(inf_ll)

        # 2. 今日最高/最低实线
        if high_day > 0:
            inf_hi = pg.InfiniteLine(pos=high_day, angle=0, pen=pg.mkPen('#ff4444', width=1.2, style=Qt.PenStyle.SolidLine), 
                                     label="今高", labelOpts={'position': 0.7})
            self.pw.addItem(inf_hi)
        if low_day > 0:
            inf_lo = pg.InfiniteLine(pos=low_day, angle=0, pen=pg.mkPen('#44cc44', width=1.2, style=Qt.PenStyle.SolidLine), 
                                     label="今低", labelOpts={'position': 0.7})
            self.pw.addItem(inf_lo)

        # 3. 价格曲线
        p_color = '#FF4444' if (last_close > 0 and prices[-1] >= last_close) or (prices[-1] >= prices[0]) else '#44CC44'
        self.pw.plot(times, prices, pen=pg.mkPen(p_color, width=3), name="价格")
        
        # 均价线 (金黄色虚线)
        avg_price = [sum(prices[:i+1])/(i+1) for i in range(len(prices))]
        self.pw.plot(times, avg_price, pen=pg.mkPen('#FFFF00', width=1.5, style=Qt.PenStyle.DashLine), name="均价")
        
        # 4. 成交量 (在主图下方叠加，自动缩放)
        if vols and len(prices) > 0:
            prices_np = np.array(prices)
            vols_np = np.array(vols)
            
            p_min_real, p_max_real = np.min(prices_np), np.max(prices_np)
            price_range = (p_max_real - p_min_real) if p_max_real > p_min_real else p_max_real * 0.05
            if price_range <= 0: price_range = 1.0
            
            # 使用 99 分位数或最大值
            v_max = np.percentile(vols_np, 99) if len(vols_np) > 10 else np.max(vols_np)
            if v_max <= 0: v_max = 1
            v_scale = (price_range * 0.2) / v_max

            brushes = []
            pens = []
            for i in range(len(times)):
                is_up = prices[i] >= prices[i-1] if i > 0 else prices[i] >= (last_close if last_close > 0 else prices[0])
                c = '#FF4444' if is_up else '#44CC44'
                brushes.append(pg.mkBrush(c))
                pens.append(pg.mkPen(c, width=0.5))
            
            v_bars = pg.BarGraphItem(x=times, height=vols_np * v_scale, width=0.7, brushes=brushes, pens=pens)
            v_bars.setPos(0, y_min - price_range * 0.05) 
            self.pw.addItem(v_bars)

    def update_live_data(self):
        """保持详情弹窗动态更新"""
        try:
            parent = self.parent()
            if not parent or not hasattr(parent, 'detector'): return
            ts = parent.detector._tick_series.get(self.code_target)
            if not ts or not ts.klines: return
            new_klines = list(ts.klines)
            if len(new_klines) > self._current_klines_len:
                self._render_chart(new_klines)
                last_c = self.meta.get('last_close', 0)
                curr_p = new_klines[-1].get('close', 0)
                if last_c > 0:
                    pc = (curr_p - last_c) / last_c * 100
                    self.setWindowTitle(f"📊 {self.name} ({self.code_target}) | 实时涨幅:{pc:+.2f}%")
        except Exception as e:
            logger.debug(f"[DetailDialog] Refresh failed: {e}")

    # ── [FIX] Persistence Support (DetailedChartDialog) ───────────────
    def _get_config_key(self):
        return self.__class__.__name__

    def _restore_geometry(self):
        try:
            if not os.path.exists(WINDOW_CONFIG_FILE): return
            with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            data = config.get(self._get_config_key(), {})
            geom_hex = data.get("geometry")
            if geom_hex:
                self.restoreGeometry(QByteArray.fromHex(geom_hex.encode('ascii')))
        except Exception: pass

    def _save_geometry(self):
        try:
            config = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            key = self._get_config_key()
            if key not in config: config[key] = {}
            geometry = self.saveGeometry()
            config[key]["geometry"] = bytes(geometry.toHex().data()).decode('ascii')
            config[key]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)


class HistoricalTrackerWorker(QThread):
    """异步多日追踪工作线程：聚合历史异动并分析板块龙头的‘强弱链接’"""
    finished = pyqtSignal(list)
    progress = pyqtSignal(str)

    def __init__(self, snapshot_paths, realtime_service):
        super().__init__()
        self.snapshot_paths = snapshot_paths
        self.realtime_service = realtime_service

    def run(self):
        try:
            all_candidate_dict = {} # code -> data
            sector_stats = {}       # name -> {hits, codes}
            
            # STEP 1: 聚合历史快照中的异动个股
            for path in self.snapshot_paths:
                match = re.search(r'bidding_(\d+)', os.path.basename(path))
                date_str = match.group(1) if match else "Unknown"
                self.progress.emit(f"📁 聚合 {date_str} 的竞价快照...")
                
                temp_detector = BiddingMomentumDetector(realtime_service=self.realtime_service, simulation_mode=True)
                if not temp_detector.load_from_snapshot(path): continue

                for code, snap in temp_detector._global_snap_cache.items():
                    if snap.get('score', 0) >= 3.6 or snap.get('pct', 0) > 8.5:
                        sn = snap.get('sector', 'N/A')
                        if sn not in sector_stats: sector_stats[sn] = {'hits': 0, 'codes': set()}
                        sector_stats[sn]['hits'] += 1
                        sector_stats[sn]['codes'].add(code)
                        
                        if code not in all_candidate_dict:
                            all_candidate_dict[code] = {
                                'code': code, 'name': snap.get('name', code), 'sector': sn,
                                'hist_hits': 1, 'hist_scores': {date_str: snap.get('score', 0)},
                                'hist_price': float(snap.get('price', 0.0)),
                                'curr_price': 0.0, 'roi': 0.0, 'curr_score': 0.0, 'momentum': 0.0,
                                'pattern': '--', 'label': '', 'is_main': False, 'klines': [],
                                'potential_score': 0.0, 'meta': snap
                            }
                        else:
                            all_candidate_dict[code]['hist_hits'] += 1
                            all_candidate_dict[code]['hist_scores'][date_str] = snap.get('score', 0)

            # STEP 2: 深度刷新实时行情并执行“重点”判定
            all_codes = list(all_candidate_dict.keys())
            self.progress.emit(f"📡 深度扫描 {len(all_codes)} 只历史强势股的实时强度...")
            
            for code in all_codes:
                item = all_candidate_dict[code]
                if self.realtime_service:
                    klines = self.realtime_service.kline_cache.get_klines(code, n=120)
                    if klines:
                        item['klines'] = klines
                        item['curr_price'] = klines[-1].get('close', 0.0)
                        p_start = klines[-20].get('close', item['curr_price']) if len(klines) >= 20 else klines[0].get('close', item['curr_price'])
                        item['momentum'] = (item['curr_price'] / p_start - 1) * 100 if p_start > 0 else 0
                        item['curr_score'] = self.realtime_service.emotion_tracker.get_score(code)
                    
                    if item['hist_price'] <= 0 and klines:
                        item['hist_price'] = float(klines[0].get('close', 0))
                    if item['hist_price'] > 0 and item['curr_price'] > 0:
                        item['roi'] = (item['curr_price'] / item['hist_price'] - 1) * 100
                    if item['sector'] == 'N/A' or not item['sector']:
                        e_data = self.realtime_service.get_55188_data(code)
                        if e_data: item['sector'] = e_data.get('theme_name', e_data.get('concept', 'N/A'))

            # STEP 3: 板块效应与龙、一致性判定
            results = list(all_candidate_dict.values())
            sector_leaders = {}
            for item in results:
                p_score = item['curr_score'] * 0.4 + item['hist_hits'] * 12.0 + item['momentum'] * 2.5
                if 2.0 < item['roi'] < 10.0: p_score += 15
                item['potential_score'] = p_score
                s = item['sector']
                if s not in sector_leaders or p_score > all_candidate_dict[sector_leaders[s]]['potential_score']:
                    sector_leaders[s] = item['code']

            for item in results:
                s = item['sector']
                is_leader = (item['code'] == sector_leaders.get(s))
                phase = "震荡蓄势"
                if is_leader:
                    item['label'] = "🏆"
                    if item['momentum'] > 1.0: phase = "强势加速"
                    elif item['momentum'] < -0.8: phase = "龙头分歧/炸板"
                else:
                    item['label'] = "📌"
                    l_code = sector_leaders.get(s)
                    l_mom = all_candidate_dict[l_code]['momentum'] if l_code else 0
                    if l_mom > 0.8 and item['momentum'] > 0.5: phase = "板块共振一致"
                    elif l_mom < -1.0 and item['momentum'] > 0.3: phase = "逆势补涨"
                    elif l_mom < -1.0: phase = "板块集体退潮"
                
                if item['roi'] < -5 and item['momentum'] > 0.5 and item['hist_hits'] >= 3:
                    phase = "核心龙回头"
                    item['potential_score'] += 20
                item['pattern'] = f"[{s}] {phase}"
                if is_leader or "共振" in phase or "加速" in phase:
                    item['potential_score'] += 15
                    item['is_main'] = True

            results.sort(key=lambda x: x['potential_score'], reverse=True)
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"HistoricalTracker Error: {e}")
            self.progress.emit(f"❌ 分析出错: {str(e)}")


class HistoricalTrackerDialog(QDialog, WindowMixin):
    """历史多日追踪对比窗口 (增强型：支持键盘上下联动)"""
    def __init__(self, all_snap_paths, realtime_service, parent=None):
        super().__init__(parent)
        self.all_snap_paths = all_snap_paths
        self.realtime_service = realtime_service
        self.detector = getattr(parent, 'detector', None)
        self.code_target = "multi_day_track"
        self._all_results = []
        self._is_populating = False
        
        self.setWindowTitle("🔍 最近多日强势股自动追踪对比")
        self.resize(1280, 800)
        self._init_ui()
        self._restore_geometry()
        self._start_analysis(3)

    def _init_ui(self):
        lay = QVBoxLayout(self)
        tool_lay = QHBoxLayout()
        tool_lay.addWidget(QLabel("📅 分析多日:"))
        self.spin_days = QSpinBox()
        self.spin_days.setRange(1, min(10, len(self.all_snap_paths)))
        self.spin_days.setValue(3)
        self.spin_days.setFixedWidth(50)
        tool_lay.addWidget(self.spin_days)
        
        self.btn_reanalyze = QPushButton("🚀 刷新追踪")
        self.btn_reanalyze.setStyleSheet("background-color: #2c3e50; color: white; padding: 4px 10px; font-weight: bold;")
        self.btn_reanalyze.clicked.connect(lambda: self._start_analysis(self.spin_days.value()))
        tool_lay.addWidget(self.btn_reanalyze)
        tool_lay.addStretch()
        
        self.status_bar = QLabel("🚀 准备就绪")
        self.status_bar.setStyleSheet("color: #ff9900; font-weight: bold;")
        tool_lay.addWidget(self.status_bar)
        lay.addLayout(tool_lay)
        
        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(['代码', '名称', '命中次数', '所属板块', '分值(历史)', '分值(当前)', '追踪基准', '现价', 'ROI', '形态/效应'])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        
        self.table.cellClicked.connect(self._on_row_clicked)
        self.table.cellDoubleClicked.connect(self._on_row_dblclick)
        self.table.currentItemChanged.connect(self._on_current_changed)
        lay.addWidget(self.table)
        
        btm_lay = QHBoxLayout()
        tip = QLabel("💡 提示：🏆龙头 📌跟随。支持键盘 ↑ ↓ 联动主面板。")
        tip.setStyleSheet("color: #888; font-style: italic;")
        btm_lay.addWidget(tip)
        # [NEW] 龙头竞赛开关
        self.cb_dragon_race = QCheckBox("龙头竞赛")
        self.cb_dragon_race.setChecked(getattr(self.detector, 'use_dragon_race', False))
        self.cb_dragon_race.toggled.connect(self._on_dragon_race_toggled)
        self.cb_dragon_race.setStyleSheet("color: #aad4ff; font-weight: bold;")
        btm_lay.addWidget(self.cb_dragon_race)

        btm_lay.addStretch()
        
        self.btn_rearrange = QPushButton("🔳 铺满窗口")
        self.btn_rearrange.clicked.connect(self._on_rearrange_clicked)
        btm_lay.addWidget(self.btn_rearrange)
        lay.addLayout(btm_lay)

    def _start_analysis(self, days: int):
        target_snaps = self.all_snap_paths[:days]
        self.status_bar.setText(f"⏳ 正在聚合板块效应与强弱链接...")
        self.btn_reanalyze.setEnabled(False)
        self.worker = HistoricalTrackerWorker(target_snaps, self.realtime_service)
        self.worker.finished.connect(self._on_data_ready)
        self.worker.progress.connect(lambda t: self.status_bar.setText(t))
        self.worker.start()

    def _on_data_ready(self, data):
        self._all_results = data
        self._is_populating = True
        self.status_bar.setText(f"✅ 完成！精选 {len(data)} 只种子股。")
        self.btn_reanalyze.setEnabled(True)
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for i, item in enumerate(data):
            self.table.insertRow(i)
            code, label = item['code'], item.get('label', '')
            c_item = QTableWidgetItem(f"{label}{code}")
            if label == "🏆": c_item.setForeground(QColor("#FF4444")); f = c_item.font(); f.setBold(True); c_item.setFont(f)
            self.table.setItem(i, 0, c_item)
            self.table.setItem(i, 1, QTableWidgetItem(item.get('name', '--')))
            hit_item = NumericTableWidgetItem(str(item['hist_hits']))
            hit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if item['hist_hits'] >= 3: hit_item.setForeground(QColor("#FFCC00"))
            self.table.setItem(i, 2, hit_item)
            self.table.setItem(i, 3, QTableWidgetItem(item.get('sector', 'N/A')))
            
            # [RESTORED] Column 4: History Score (Most Recent)
            scores = item.get('hist_scores', {})
            last_date = sorted(scores.keys())[-1] if scores else "?"
            h_score = scores.get(last_date, 0.0)
            self.table.setItem(i, 4, NumericTableWidgetItem(f"{h_score:.1f}"))
            
            self.table.setItem(i, 5, NumericTableWidgetItem(f"{item['curr_score']:.1f}"))
            self.table.setItem(i, 6, NumericTableWidgetItem(f"{item['hist_price']:.2f}"))
            self.table.setItem(i, 7, NumericTableWidgetItem(f"{item['curr_price']:.2f}"))
            roi = item['roi']
            roi_item = NumericTableWidgetItem(f"{roi:+.2f}%")
            if roi > 0: roi_item.setForeground(QColor("#FF4444"))
            elif roi < 0: roi_item.setForeground(QColor("#44CC44"))
            self.table.setItem(i, 8, roi_item)
            pat_item = QTableWidgetItem(item['pattern'])
            if item['is_main']: pat_item.setForeground(QColor("#FF9900"))
            self.table.setItem(i, 9, pat_item)
        self.table.setSortingEnabled(True)
        self.table.setUpdatesEnabled(True)
        self.table.sortItems(2, Qt.SortOrder.DescendingOrder)
        self._is_populating = False

    def _on_current_changed(self, current, previous):
        if self._is_populating or not current or not self.table.hasFocus(): return
        item = self.table.item(current.row(), 0)
        if item:
            code = re.sub(r'[^\d]', '', item.text())
            # [SAFE] Use a timer that is property managed
            if not hasattr(self, '_link_timer'):
                self._link_timer = QTimer(self)
                self._link_timer.setSingleShot(True)
                self._link_timer.timeout.connect(self._exec_delayed_link)
            
            self._pending_link_code = code
            self._link_timer.start(50)

    def _exec_delayed_link(self):
        """执行延迟代码联动"""
        try:
            if hasattr(self, '_pending_link_code') and self.parent():
                self.parent()._link_code(self._pending_link_code, focus_widget=self.table)
        except RuntimeError: pass

    def _on_row_clicked(self, row, col):
        if col > 1: return
        item = self.table.item(row, 0)
        if item:
            code = re.sub(r'[^\d]', '', item.text())
            self.parent()._link_code(code, focus_widget=self.table)

    def _on_row_dblclick(self, row, col):
        item = self.table.item(row, 0)
        if not item: return
        code = re.sub(r'[^\d]', '', item.text())
        target = next((d for d in self._all_results if d['code'] == code), None)
        if target:
            meta = target.get('meta', {}).copy()
            meta.update({'last_close': target.get('hist_price', 0.0), 'theme': target.get('sector', 'N/A')})
            dialog = DetailedChartDialog(target['code'], target['name'], target['klines'], meta, self)
            dialog.exec()

    def _on_rearrange_clicked(self):
        if self.parent() and hasattr(self.parent(), '_on_rearrange_clicked'):
            self.parent()._on_rearrange_clicked()

    # ── [FIX] Persistence Support (HistoricalTrackerDialog) ──────────
    def _get_config_key(self):
        return self.__class__.__name__

    def _restore_geometry(self):
        try:
            if not os.path.exists(WINDOW_CONFIG_FILE): return
            with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            data = config.get(self._get_config_key(), {})
            geom_hex = data.get("geometry")
            if geom_hex:
                self.restoreGeometry(QByteArray.fromHex(geom_hex.encode('ascii')))
        except Exception: pass

    def _save_geometry(self):
        try:
            config = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            key = self._get_config_key()
            if key not in config: config[key] = {}
            geometry = self.saveGeometry()
            config[key]["geometry"] = bytes(geometry.toHex().data()).decode('ascii')
            config[key]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception: pass

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _on_dragon_race_toggled(self, checked):
        """同步龙头竞赛设置到主面板与检测器"""
        parent = self.parent()
        if parent and hasattr(parent, 'cb_dragon_race'):
            # blockSignals 禁止递归刷新
            parent.cb_dragon_race.blockSignals(True)
            parent.cb_dragon_race.setChecked(checked)
            parent.cb_dragon_race.blockSignals(False)
            
            # 手动调用父类的逻辑 slot 以执行实际的 detector 切换和刷新
            if hasattr(parent, '_on_dragon_race_toggled'):
                parent._on_dragon_race_toggled(checked)
        elif self.detector:
            self.detector.use_dragon_race = checked
            if hasattr(self.detector, 'reconstruct_all_from_cache'):
                self.detector.reconstruct_all_from_cache()



class SnapshotCalendarDialog(QDialog):
    """日历模式快照选择器 - 增强体验，红色显示有数据的日期"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📅 历史复盘日期选择")
        self.resize(380, 480)
        
        self.selected_file = None
        # 统一路径获取方式
        self.snapshots_dir = os.path.join(cct.get_base_path(), "snapshots")
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)
        
        tip_lbl = QLabel("💡 红色字体日期代表已有快照文件")
        tip_lbl.setStyleSheet("color: #aad4ff; font-weight: bold; background: #2a3a4a; padding: 5px; border-radius: 4px;")
        lay.addWidget(tip_lbl)
        
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)

        # 【最终强效修复：覆盖所有星期表头格式】
        # 这种方式优先级最高，能绕过任何系统的 QSS 限制
        header_fmt = QTextCharFormat()
        header_fmt.setForeground(QColor("#90caf9")) #⭐ 淡天蓝色，高亮且护眼
        header_fmt.setBackground(QColor("#2b2b2b"))
        f = header_fmt.font()
        f.setBold(True)
        header_fmt.setFont(f)

        for day in [
            Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
            Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday,
            Qt.DayOfWeek.Sunday
        ]:
            self.calendar.setWeekdayTextFormat(day, header_fmt)

        # 调色板兜底：强制背景为深色
        pal = self.calendar.palette()
        dark_color = QColor("#2b2b2b")
        pal.setColor(pal.ColorRole.Window, dark_color)
        pal.setColor(pal.ColorRole.Base, dark_color)
        pal.setColor(pal.ColorRole.Button, dark_color)
        pal.setColor(pal.ColorRole.ButtonText, QColor("#90caf9"))
        self.calendar.setPalette(pal)

        # 样式表全局覆盖
        self.calendar.setStyleSheet("""
            QCalendarWidget { background: #2b2b2b; color: #dddddd; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background: #333333; }
            QCalendarWidget QToolButton { color: #00ff88; font-weight: bold; background: transparent; padding: 5px; }
            /* 针对表格格子的核心样式 */
            QCalendarWidget QAbstractItemView {
                background: #2b2b2b;
                color: #dddddd;
                selection-background-color: #409cff;
                selection-color: white;
            }
        """)
        
        # 初始标记
        self._highlight_snapshot_dates()
        
        # 当月份或日期改变时刷新标记或状态
        self.calendar.currentPageChanged.connect(self._highlight_snapshot_dates)
        self.calendar.selectionChanged.connect(self._on_selection_changed)
        # 【新增：双击日期或回车支持快速加载】
        self.calendar.activated.connect(self._on_calendar_activated)
        
        lay.addWidget(self.calendar)
        
        self.info_lbl = QLabel("请从日历中选择日期...")
        self.info_lbl.setStyleSheet("color: #888; font-style: italic; padding: 5px;")
        self.info_lbl.setWordWrap(True)
        lay.addWidget(self.info_lbl)
        
        btn_lay = QHBoxLayout()
        
        # [NEW] 手动选择文件按钮
        self.btn_browse = QPushButton("📁 浏览文件...")
        self.btn_browse.setFixedHeight(35)
        self.btn_browse.setToolTip("手动选择特定的 .json.gz 快照文件")
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        btn_lay.addWidget(self.btn_browse)
        
        btn_lay.addStretch()
        
        self.btn_ok = QPushButton("🚀 确认加载")
        self.btn_ok.setEnabled(False)
        self.btn_ok.setFixedHeight(35)
        self.btn_ok.setStyleSheet("background-color: #2a3a4a; color: #00ff88; font-weight: bold;")
        self.btn_ok.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(35)
        btn_cancel.clicked.connect(self.reject)
        
        btn_lay.addWidget(btn_cancel)
        btn_lay.addWidget(self.btn_ok)
        lay.addLayout(btn_lay)
        
        # 如果当前已经选了日期，触发一下检查
        self._on_selection_changed()
        
    def _highlight_snapshot_dates(self):
        """遍历快照目录，并在日历上标红有快照的日期"""
        if not os.path.exists(self.snapshots_dir):
            return
            
        fmt = QTextCharFormat()
        # 现实红色 (Display Red)
        fmt.setForeground(QColor("#FF4444")) 
        f = fmt.font()
        f.setBold(True)
        f.setUnderline(True)
        fmt.setFont(f)
        
        # 获取所有快照文件名并提取日期
        try:
            files = os.listdir(self.snapshots_dir)
            for f_name in files:
                if f_name.startswith("bidding_") and f_name.endswith(".json.gz"):
                    match = re.search(r'bidding_(\d{8})', f_name)
                    if match:
                        date_str = match.group(1) 
                        qdate = QDate.fromString(date_str, "yyyyMMdd")
                        if qdate.isValid():
                            self.calendar.setDateTextFormat(qdate, fmt)
        except Exception as e:
            logger.debug(f"[Calendar] Highlight error: {e}")

    def _on_selection_changed(self):
        qdate = self.calendar.selectedDate()
        date_str = qdate.toString("yyyyMMdd")
        fname = f"bidding_{date_str}.json.gz"
        fpath = os.path.join(self.snapshots_dir, fname)
        
        if os.path.exists(fpath):
            self.selected_file = fpath
            self.info_lbl.setText(f"✅ 已选中: {fname}\n可以加载该日期的历史快照。")
            self.info_lbl.setStyleSheet("color: #00ff88; font-weight: bold; background: #1a2a1a; border-radius: 3px;")
            self.btn_ok.setEnabled(True)
            self.btn_ok.setStyleSheet("background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88;")
        else:
            self.selected_file = None
            self.info_lbl.setText(f"❌ 日期 {date_str} 暂无快照文件。\n请选择标记为红色的日期。")
            self.info_lbl.setStyleSheet("color: #FF4444; background: #2a1a1a; border-radius: 3px;")
            self.btn_ok.setEnabled(False)
            self.btn_ok.setStyleSheet("background-color: #222; color: #555;")

    def _on_calendar_activated(self, qdate):
        """处理双击或回车：如果有数据则直接加载"""
        self._on_selection_changed()
        if self.btn_ok.isEnabled() and self.selected_file:
            self.accept()

    def _on_browse_clicked(self):
        """手动浏览文件系统选择快照"""
        # 统一路径获取方式
        start_dir = self.snapshots_dir
        if not os.path.exists(start_dir):
            try:
                os.makedirs(start_dir, exist_ok=True)
            except:
                start_dir = os.getcwd()
            
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择历史快照文件", start_dir, "快照文件 (*.json.gz);;所有文件 (*.*)"
        )
        if file_path:
            self.selected_file = file_path
            self.accept()


from queue import Queue, Empty
import time

class DataProcessWorker(QObject):
    """Worker object to process realtime data in a separate QThread."""

    data_updated = pyqtSignal(object)
    stopped = pyqtSignal()

    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        # 线程安全队列
        self.df_queue = Queue()
        # 用队列替代 bool（彻底线程安全）
        self.force_queue = Queue()
        self._is_running = True

    def add_data(self, df):
        """外部线程安全调用"""
        self.df_queue.put(df)

    def trigger_recalc(self):
        """线程安全强制刷新"""
        # 防止重复堆积刷新信号，先清空再放最新的
        while not self.force_queue.empty():
            try: self.force_queue.get_nowait()
            except Empty: break
        self.force_queue.put(True)

    def stop(self):
        self._is_running = False

    def process_data(self):
        """子线程主循环（生产稳定版）"""
        # [NEW] 1. 延迟初始化：将耗时的种子加载与持久化恢复移至后台线程执行，解决启动阻塞（491ms问题）
        try:
            if hasattr(self.detector, '_load_stock_selector_data'):
                logger.info("📡 [Worker] Background initial loading for BiddingMomentumDetector...")
                self.detector._load_stock_selector_data()
                logger.info("📡 [Worker] Background loading completed.")
        except Exception as e:
            logger.error(f"❌ [Worker] Failed to load detector persistent data: {e}")

        logger.info("🚀 [Worker] Data processing loop started.")

        while self._is_running:
            df = None
            has_done_work = False

            try:
                # ⚡ 快速响应（超时时间设为 0.05s）
                # 这一步会自动让出 GIL，对系统非常友好
                try:
                    df = self.df_queue.get(timeout=0.05)
                except Empty:
                    pass

                # 1. 处理数据（关键优化：丢弃旧包，防堆积）
                if df is not None:
                    # 🔥 丢弃逻辑：如果有更新的数据在排队，只取最后一个
                    count = 0
                    while not self.df_queue.empty():
                        try:
                            df = self.df_queue.get_nowait()
                            count += 1
                        except Empty:
                            break
                    
                    if count > 0 and self.detector.enable_log:
                        logger.debug(f"⏩ [Worker] Skipped {count} stale data frames.")

                    # 执行核心计算
                    self.detector.register_codes(df)
                    self.detector.update_scores()

                    v = getattr(self.detector, "data_version", 0) + 1
                    setattr(self.detector, "data_version", v)

                    self.data_updated.emit(df)
                    has_done_work = True

                # 2. 强制刷新判定
                force = False
                try:
                    force = self.force_queue.get_nowait()
                except Empty:
                    force = False

                if force:
                    if self.detector.enable_log:
                        logger.info("⚡ [Worker] Force recalculation")

                    self.detector.update_scores()

                    v = getattr(self.detector, "data_version", 0) + 1
                    setattr(self.detector, "data_version", v)

                    self.data_updated.emit(None)
                    has_done_work = True

            except Exception as e:
                logger.error(f"[Worker] Runtime Error: {e}", exc_info=True)

            # 3. 最后的保险：防止在数据极高频时榨干 CPU
            # 如果连续处理了任务，微小休眠 1ms 让系统调度一下
            if has_done_work:
                time.sleep(0.001) 

        logger.info("🏁 [Worker] Loop exited safely.")
        self.stopped.emit()


class SectorBiddingPanel(QWidget, WindowMixin):
    """竞价和尾盘板块联动监控面板 v3"""

    # ------------------------------------------------------------------ init
    def __init__(self, main_window: Any, allow_real_close: bool = False):
        # 🚀 [NEW] Centralized Data Hub Initialization (Multi-Point Protection)
        # Ensure DataHub is ready in the Bidding Panel process
        # self.data_hub = DataHubService.get_instance()
        pass
        
        super().__init__(None)         # 独立窗口
        self.main_window = main_window
        rs = getattr(main_window, 'realtime_service', None)
        self.detector = BiddingMomentumDetector(realtime_service=rs)

        # [NEW] 1. 本地化联动：尝试初始化 StockSender
        try:
            from JohnsonUtil.stock_sender import StockSender
            # 使用默认变量，兼容 Tk/Qt 灵活包装
            self.sender = StockSender(callback=None)
            logger.info("📡 [SectorPanel] StockSender initialized for standalone linkage.")
        except Exception as e:
            logger.warning(f"⚠️ [SectorPanel] StockSender init failed (Expected on fresh env): {e}")
            self.sender = None

        # 排序状态：(col_index, ascending)
        self._sort_col = 4             # 默认按涨幅排序
        self._sort_asc = False

        # 状态记录
        self._is_populating = False
        self._last_selected_code = None
        self._last_refresh_ts = 0
        self._force_update_requested = False
        self._sbc_test_windows = []     # 持有 SBC 测试窗口引用，防止 GC
        self._is_history_mode = False   # [NEW] 历史复盘模式标志
        self._history_date = ""         # [NEW] 历史数据日期
        self._allow_real_close = allow_real_close  # [NEW] 区分隐藏还是彻底关闭 (X按钮隐藏，工具栏按钮关闭)
        self._last_rendered_data_version = -1
        self._last_rendered_stock_cache = {} # sector -> version
        self._search_history = []           # [NEW] 搜索历史记录
        self._is_leader_search_mode = False # [NEW] 龙头搜索模式标志
        self._active_search_query = ""

        # 🚀 [Performance] Pre-cached UI Resources
        self._color_red = QColor("#FF4444")
        self._color_green = QColor("#44CC44")
        self._color_orange = QColor("#FF9900")
        self._color_yellow = QColor("#FFCC00")
        self._color_blue = QColor("#409cff")
        self._color_gray = QColor("#888888")
        self._color_light_blue = QColor("#aad4ff")
        
        self._bold_font = QFont("Microsoft YaHei", 9)
        self._bold_font.setBold(True)
        self._small_font = QFont("Microsoft YaHei", 8)
        
        # 🔒 [Thread Safety]
        import threading
        self._update_lock = threading.Lock()

        self.setWindowTitle("🚀 竞价/尾盘板块联动监控 (Tick 订阅)")
        self.resize(1100, 680)
        
        # # Async Data Processing Worker - MUST be before UI init
        # self._worker_thread = QThread()  # No parent - managed manually
        # self._worker = DataProcessWorker(self.detector)
        # self._worker.moveToThread(self._worker_thread)
        # self._worker_thread.started.connect(self._worker.process_data)
        # self._worker.finished.connect(self._on_worker_finished)
        # self._worker_thread.start()


        # Async Data Processing Worker - MUST be before UI init
        self._worker_thread = QThread()  # no parent

        self._worker = DataProcessWorker(self.detector)
        self._worker.moveToThread(self._worker_thread)

        # 启动
        self._worker_thread.started.connect(self._worker.process_data)

        # 正确的停止信号
        self._worker.stopped.connect(self._worker_thread.quit)

        # 线程结束后清理
        self._worker_thread.finished.connect(self._worker.deleteLater)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)

        # UI层回调
        # [FIX] 连接数据处理信号到刷新函数，而不是停止信号
        self._worker.data_updated.connect(self._on_worker_finished)

        self._worker_thread.start()


        self._init_ui()
        # [FIX] Implementation of geometry methods locally
        self._restore_geometry()
        self._restore_ui_state()

        # UI 刷新计时器 (保持定义但默认不启动，作为 fallback 或数据中断时的兜底)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_sector_list)
        # self._refresh_timer.start(2000) # [CHANGE] 改为数据驱动

        # 评分聚合计时器
        self._score_timer = QTimer(self)
        self._score_timer.timeout.connect(self.detector.update_scores)
        # self._score_timer.start(5000) # [CHANGE] 改为数据驱动

        # 🚀 [Proactive] 启动引导初始化
        if hasattr(self.main_window, 'df_all') and self.main_window.df_all is not None and not self.main_window.df_all.empty:
             self.on_realtime_data_arrived(self.main_window.df_all, force_update=True)
             logger.info("📡 [SectorPanel] Cold start initialized with main window's df_all")
        else:
             if hasattr(self, 'status_lbl'):
                 self.status_lbl.setText("⏳ 等待主窗口数据或手动刷新...")

    def showEvent(self, event):
        """窗口显示时，尝试触发初次刷新以填补白板"""
        super().showEvent(event)
        # 即使数据还未到，先清空加载一次状态
        if self.sector_table.rowCount() == 0:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("🔄 准备首次数据评分映射...")
            QTimer.singleShot(500, self.manual_refresh)

    def _on_btn_close_clicked(self):
        """工具栏'关闭'按钮触发的彻底退出"""
        self._allow_real_close = True
        self.close()

    def _on_dragon_race_toggled(self, checked):
        """切换龙头竞赛模式"""
        self.detector.use_dragon_race = checked
        logger.info(f"🔄 [SectorPanel] Dragon Race Mode: {'ENABLED (追涨模式)' if checked else 'DISABLED (挖掘模式)'}")
        
        # [NEW] 同步到追踪 Dialog 的状态 (双向同步)
        if hasattr(self, '_hist_tracker_dialog'):
            try:
                if self._hist_tracker_dialog.isVisible():
                    self._hist_tracker_dialog.cb_dragon_race.blockSignals(True)
                    self._hist_tracker_dialog.cb_dragon_race.setChecked(checked)
                    self._hist_tracker_dialog.cb_dragon_race.blockSignals(False)
            except (RuntimeError, AttributeError): pass # 即使窗口已销毁也不触发报错

        if self._is_history_mode:
            # [FIX] 历史模式下，直接触发全量缓存重映射，无需重选文件
            self.detector.reconstruct_all_from_cache()
            self._refresh_sector_list()
            # [NEW] 强制刷新当前选中的板块右侧表格，确保龙头角色和位次立即更新
            self._on_sector_table_selection_changed()
        else:
            # 实时模式处理
            self.detector._last_gc_ts = 0 
            self.manual_refresh()
        
        if hasattr(self, 'status_lbl'):
            mode_str = "竞赛模式 (追涨)" if checked else "挖掘模式 (先锋)"
            self.status_lbl.setText(f"⚙️ 模式切换: {mode_str}")
            self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")
            # 3秒后还原
            QTimer.singleShot(3000, lambda: self.status_lbl.setText("准备就绪"))

    def closeEvent(self, event):
        """处理窗口关闭事件，执行资源回收"""
        if not self._allow_real_close:
            self.hide()
            event.ignore()
            return

        # --- 以下是真正关闭时的资源回收和保存 ---
        # 1. 先停止定时器，不产生新任务
        if hasattr(self, '_refresh_timer'):
            self._refresh_timer.stop()
        if hasattr(self, '_score_timer'):
            self._score_timer.stop()
        # 2. 告知 worker 停止循环
        if hasattr(self, '_worker'):
            try:
                self._worker.stop()
            except Exception:
                pass
        # 3. 等待线程退出（最多 3 秒）
        if hasattr(self, '_worker_thread') and self._worker_thread is not None:
            thread = self._worker_thread
            if thread.isRunning():
                thread.quit()   # 请求事件循环退出
                if not thread.wait(3000):
                    # 超时则强制终止
                    logger.warning("[SectorBiddingPanel] Worker thread did not stop in time, terminating...")
                    thread.terminate()
                    thread.wait(500)
            thread.deleteLater()   # 安全释放
            self._worker_thread = None
        
        # [NEW] Persist scores and layout on close
        self._save_geometry()
        self._save_ui_state()
        if hasattr(self, 'detector'):
            # 这里是真正关闭，我们保存数据
            self.detector.save_persistent_data()
            
        event.accept()

    def _save_ui_state(self):
        """保存表格布局和状态"""
        try:
            scale = self._get_dpi_scale_factor()
            data_to_save = {}
            
            # 保存各表状态 (Hex 格式)
            data_to_save['sector_table_state'] = self.sector_table.horizontalHeader().saveState().toHex().data().decode()
            data_to_save['stock_table_state'] = self.stock_table.horizontalHeader().saveState().toHex().data().decode()
            data_to_save['watchlist_table_state'] = self.watchlist_table.horizontalHeader().saveState().toHex().data().decode()
            
            # 保存 Splitter 状态
            data_to_save['splitter_h_state'] = self.splitter.saveState().toHex().data().decode()
            data_to_save['v_splitter_state'] = self.v_splitter.saveState().toHex().data().decode()
            
            # [NEW] 保存搜索历史
            data_to_save['search_history'] = self._search_history

            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            
            # 读取并合并现有配置
            full_data = {}
            if os.path.exists(config_file_path):
                try:
                    with open(config_file_path, "r", encoding="utf-8") as f:
                        full_data = json.load(f)
                except Exception: pass
            
            full_data[SETTINGS_SECTION + "_ui_state"] = data_to_save
            with open(config_file_path, "w", encoding="utf-8") as f:
                json.dump(full_data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"📊 [SectorPanel] UI state saved to {config_file_path}")
        except Exception as e:
            logger.error(f"Failed to save UI state: {e}")

    def _restore_ui_state(self):
        """恢复表格列宽、Splitter 状态等 UI 设置"""
        try:
            scale = self._get_dpi_scale_factor()
            config_file_path = self._get_config_file_path(WINDOW_CONFIG_FILE, scale)
            if not os.path.exists(config_file_path):
                return
                
            with open(config_file_path, "r", encoding="utf-8") as f:
                full_data = json.load(f)
            
            ui_state = full_data.get(SETTINGS_SECTION + "_ui_state")
            if not ui_state:
                return
            
            # 恢复各表列状态
            if 'sector_table_state' in ui_state:
                self.sector_table.horizontalHeader().restoreState(QByteArray.fromHex(ui_state['sector_table_state'].encode()))
            if 'stock_table_state' in ui_state:
                self.stock_table.horizontalHeader().restoreState(QByteArray.fromHex(ui_state['stock_table_state'].encode()))
            if 'watchlist_table_state' in ui_state:
                self.watchlist_table.horizontalHeader().restoreState(QByteArray.fromHex(ui_state['watchlist_table_state'].encode()))
            
            # 恢复 Splitter 比例
            if 'splitter_h_state' in ui_state:
                self.splitter.restoreState(QByteArray.fromHex(ui_state['splitter_h_state'].encode()))
            if 'v_splitter_state' in ui_state:
                self.v_splitter.restoreState(QByteArray.fromHex(ui_state['v_splitter_state'].encode()))
            
            # [NEW] 恢复搜索历史
            if 'search_history' in ui_state:
                self._search_history = ui_state['search_history']
                self._update_search_combo_list()
            
            logger.debug("📊 [SectorPanel] UI state restored")
        except Exception as e:
            logger.error(f"Failed to restore UI state: {e}")


    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        # ── 紧凑工具栏 ──────────────────────────────────────────────────
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.StyledPanel)
        bar_lay_main = QVBoxLayout(bar)
        bar_lay_main.setContentsMargins(4, 2, 4, 2)
        bar_lay_main.setSpacing(2)
        
        # 第一排工具栏
        bar_lay_1 = QHBoxLayout()
        bar_lay_1.setSpacing(6)

        bold = QFont()
        bold.setBold(True)

        # 策略开关
        self.cb_new_high   = self._make_cb("新高",    'new_high',        bar_lay_1)
        self.cb_ma_rebound = self._make_cb("MA回踩高开", 'ma_rebound',   bar_lay_1)
        self.cb_surge_vol  = self._make_cb("放量",     'surge_vol',       bar_lay_1)
        self.cb_consec     = self._make_cb("连续拉升", 'consecutive_up',  bar_lay_1)
        
        # [NEW] 龙头竞赛开关
        self.cb_dragon_race = QCheckBox("竞赛模式")
        self.cb_dragon_race.setToolTip("开启后切换到‘追涨模式’，更强调涨幅和防回撤；关闭则回到‘挖掘模式’，更侧重早盘异动先锋。")
        self.cb_dragon_race.setChecked(getattr(self.detector, 'use_dragon_race', False))
        self.cb_dragon_race.toggled.connect(self._on_dragon_race_toggled)
        self.cb_dragon_race.setStyleSheet("color: #aad4ff; font-weight: bold;")
        bar_lay_1.addWidget(self.cb_dragon_race)

        bar_lay_1.addStretch()
        # 🚀 [NEW] Rearrange Button
        self.btn_tile = QPushButton("窗口重排")
        self.btn_tile.setFixedWidth(70)
        self.btn_tile.setStyleSheet("background-color: #444; color: #00ff88; border: 1px solid #00ff88;")
        self.btn_tile.clicked.connect(self._on_rearrange_clicked)
        bar_lay_1.addWidget(self.btn_tile)

        bar_lay_1.addWidget(self._sep())

        bar_lay_1.addWidget(QLabel("放量倍≥"))
        self.spin_vol_ratio = self._make_spin(1.0, 10.0, 0.1,
            self.detector.strategies['surge_vol']['min_ratio'])
        bar_lay_1.addWidget(self.spin_vol_ratio)

        bar_lay_1.addWidget(QLabel(" 涨幅%"))
        self.spin_pct_min = self._make_spin(-20, 20, 0.5,
            self.detector.strategies['pct_change']['min'])
        bar_lay_1.addWidget(self.spin_pct_min)
        bar_lay_1.addWidget(QLabel("~"))
        self.spin_pct_max = self._make_spin(-20, 20, 0.5,
            self.detector.strategies['pct_change']['max'])
        bar_lay_1.addWidget(self.spin_pct_max)

        for w in [self.spin_vol_ratio, self.spin_pct_min, self.spin_pct_max]:
            w.valueChanged.connect(self._on_strategy_changed)

        bar_lay_1.addSpacing(4)
        bar_lay_1.addWidget(self._sep())
        
        # [NEW] Search Bar (Upgraded to QComboBox for history)
        from PyQt6.QtWidgets import QComboBox
        bar_lay_1.addWidget(QLabel("🔍搜索:"))
        self.search_input = QComboBox()
        self.search_input.setEditable(True)
        self.search_input.setDuplicatesEnabled(False)
        self.search_input.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.search_input.setPlaceholderText("例如:涨幅>3")
        self.search_input.setFixedWidth(180)
        self.search_input.lineEdit().returnPressed.connect(self._on_search_triggered)
        # [NEW] 实现选择历史项后自动触发搜索
        self.search_input.activated.connect(self._on_search_triggered)
        # 添加默认常驻选项
        self.search_input.addItem("龙头")
        # [NEW] 为历史列表视图配置右键菜单，实现删除功能
        self.search_input.view().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.search_input.view().customContextMenuRequested.connect(self._on_search_history_context_menu)
        # [NEW] 应用可视化删除委托
        self.history_delegate = SearchHistoryDelegate(self.search_input)
        # 信号连接保留作为备用逻辑
        self.history_delegate.delete_clicked.connect(self._delete_history_item_by_row)
        self.search_input.view().setItemDelegate(self.history_delegate)
        # [NEW] 核心补强：在视口层安装过滤器，抢在 QComboBox 之前拦截点击
        self.search_input.view().viewport().installEventFilter(self)
        bar_lay_1.addWidget(self.search_input)
        
        self.btn_search = QPushButton("查询")
        self.btn_search.setFixedWidth(55)
        self.btn_search.clicked.connect(self._on_search_triggered)
        bar_lay_1.addWidget(self.btn_search)
        
        self.btn_clear_search = QPushButton("清除")
        self.btn_clear_search.setFixedWidth(55)
        self.btn_clear_search.clicked.connect(self._on_search_cleared)
        bar_lay_1.addWidget(self.btn_clear_search)
        
        bar_lay_1.addStretch()
        bar_lay_main.addLayout(bar_lay_1)

        # 第二排工具栏
        bar_lay_2 = QHBoxLayout()
        bar_lay_2.setSpacing(6)
        
        self.btn_refresh = QPushButton("刷新 🔄")
        self.btn_refresh.setFixedWidth(65)
        self.btn_refresh.setToolTip("刷新评分并更新表格内容\n快捷键: F5 或双击空白处")
        self.btn_refresh.clicked.connect(self.manual_refresh)
        bar_lay_2.addWidget(self.btn_refresh)

        self.cb_log = QCheckBox("Log")
        self.cb_log.setToolTip("开启/关闭后台日志输出")
        self.cb_log.setChecked(self.detector.enable_log)
        self.cb_log.stateChanged.connect(self._on_strategy_changed)
        bar_lay_2.addWidget(self.cb_log)

        self.btn_close = QPushButton("关闭 ✖")
        self.btn_close.setFixedWidth(55)
        self.btn_close.clicked.connect(self._on_btn_close_clicked)
        bar_lay_2.addWidget(self.btn_close)

        bar_lay_2.addWidget(self._sep())

        self.btn_history = QPushButton("历史复盘 📂")
        self.btn_history.setFixedWidth(85)
        self.btn_history.clicked.connect(self._on_history_load_clicked)
        bar_lay_2.addWidget(self.btn_history)

        self.btn_track = QPushButton("🔍 历史追踪")
        self.btn_track.setFixedWidth(85)
        self.btn_track.setStyleSheet("background-color: #2a3a4a; color: #ff9900;")
        self.btn_track.setToolTip("选择快照并对比当前走势，寻找 10 个潜力结构")
        self.btn_track.clicked.connect(self._on_history_track_clicked)
        bar_lay_2.addWidget(self.btn_track)

        self.btn_live = QPushButton("实时 📡")
        self.btn_live.setFixedWidth(65)
        self.btn_live.setStyleSheet("background-color: #2a3a4a; color: #00ff88; font-weight: bold;")
        self.btn_live.clicked.connect(self._on_back_to_live_clicked)
        self.btn_live.setVisible(False) # 初始隐藏
        bar_lay_2.addWidget(self.btn_live)


        # ── [NEW] SBC Test Buttons ──
        bar_lay_2.addWidget(self._sep())
        
        self.btn_sbc_live = QPushButton("SBC实时⚡")
        self.btn_sbc_live.setFixedWidth(85)
        self.btn_sbc_live.setStyleSheet("background-color: #2a3a4a; color: #00ff88; font-weight: bold;")
        self.btn_sbc_live.setToolTip("使用Sina实时数据验证SBC信号 (需在个股表选中代码)")
        self.btn_sbc_live.clicked.connect(lambda: self._run_sbc_test(True))
        bar_lay_2.addWidget(self.btn_sbc_live)

        self.btn_sbc_replay = QPushButton("SBC回放")
        self.btn_sbc_replay.setFixedWidth(75)
        self.btn_sbc_replay.setStyleSheet("background-color: #2a3a4a; color: #aad4ff;")
        self.btn_sbc_replay.setToolTip("使用本地缓存/日线数据执行SBC逻辑回放")
        self.btn_sbc_replay.clicked.connect(lambda: self._run_sbc_test(False))
        bar_lay_2.addWidget(self.btn_sbc_replay)

        bar_lay_2.addWidget(self._sep())

        self.status_lbl = QLabel("等待数据...")
        self.status_lbl.setStyleSheet("color:#FFA500;font-weight:bold;")
        bar_lay_2.addWidget(self.status_lbl)
        bar_lay_2.addStretch()
        
        bar_lay_main.addLayout(bar_lay_2)

        # 第三排工具栏：门槛与灵敏度
        bar_lay_3 = QHBoxLayout()
        bar_lay_3.setSpacing(6)

        bar_lay_3.addWidget(QLabel("🎯 个股分≥"))
        self.spin_score_threshold = self._make_spin(0.0, 20.0, 0.5, self.detector.score_threshold)
        self.spin_score_threshold.valueChanged.connect(self._on_strategy_changed)
        bar_lay_3.addWidget(self.spin_score_threshold)
        
        bar_lay_3.addWidget(self._sep())
        
        bar_lay_3.addWidget(QLabel(" 观测时长:"))
        self.btn_sub_10 = QPushButton("-10m")
        self.btn_sub_10.setFixedWidth(45)
        self.btn_sub_10.clicked.connect(lambda: self._adjust_interval(-10))
        bar_lay_3.addWidget(self.btn_sub_10)
        
        self.lbl_interval = QLabel(f"{int(self.detector.comparison_interval/60)}m")
        self.lbl_interval.setStyleSheet("color: #00ff88; font-weight: bold; min-width: 30px;")
        self.lbl_interval.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_lay_3.addWidget(self.lbl_interval)
        
        self.btn_add_10 = QPushButton("+10m")
        self.btn_add_10.setFixedWidth(45)
        self.btn_add_10.clicked.connect(lambda: self._adjust_interval(10))
        bar_lay_3.addWidget(self.btn_add_10)

        bar_lay_3.addStretch()

        bar_lay_3.addWidget(QLabel(" 🏗️ 板块分≥"))
        self.spin_sector_min_score = self._make_spin(0.0, 50.0, 0.5, self.detector.sector_min_score)
        bar_lay_3.addWidget(self.spin_sector_min_score)

        bar_lay_3.addWidget(QLabel(" 🔥 强度≥"))
        self.spin_sector_score_threshold = self._make_spin(0.0, 500.0, 5.0, getattr(self.detector, 'sector_score_threshold', 5.0))
        bar_lay_3.addWidget(self.spin_sector_score_threshold)

        bar_lay_3.addWidget(self._sep())

        bar_lay_3.addWidget(QLabel(" 📉 最小振幅%:"))
        self.spin_amplitude_min = self._make_spin(0.0, 10.0, 0.5, self.detector.strategies['amplitude']['min'])
        bar_lay_3.addWidget(self.spin_amplitude_min)

        bar_lay_3.addWidget(QLabel(" 🧱 连红K棒:"))
        self.spin_consec_bars = self._make_spin(1, 10, 1, self.detector.strategies['consecutive_up']['bars'])
        bar_lay_3.addWidget(self.spin_consec_bars)

        for w in [self.spin_score_threshold, self.spin_sector_min_score, 
                 self.spin_sector_score_threshold, self.spin_amplitude_min, self.spin_consec_bars]:
            w.valueChanged.connect(self._on_strategy_changed)

        bar_lay_3.addStretch()
        bar_lay_main.addLayout(bar_lay_3)

        root.addWidget(bar)

        # ── 主体：Splitter ───────────────────────────────────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        # 左：板块排行
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(2)
        lbl_sec = QLabel(" 活跃板块 (双击联动)")
        lbl_sec.setStyleSheet("font-weight:bold;background:#2a2a3e;color:#aad4ff;padding:2px;")
        llay.addWidget(lbl_sec)

        self.sector_table = QTableWidget(0, 5)
        self.sector_table.setHorizontalHeaderLabels(['板块', '强度', '涨跌', '龙头', '状态'])
        self.sector_table.setAlternatingRowColors(True)
        self.sector_table.setFont(QFont("Microsoft YaHei", 9))
        self.sector_table.verticalHeader().setVisible(False)
        self.sector_table.verticalHeader().setDefaultSectionSize(25) # 紧凑行高
        self.sector_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sector_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sector_table.setAlternatingRowColors(True)
        self.sector_table.setFont(QFont("Microsoft YaHei", 9))
        self.sector_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.sector_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.sector_table.setSortingEnabled(False) # [PURE PYTHON SORT]
        self.sector_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sector_table.customContextMenuRequested.connect(self._on_sector_context_menu)
        
        self.sector_table.horizontalHeader().sectionClicked.connect(self._on_sector_header_clicked)
        
        self.sector_table.itemSelectionChanged.connect(self._on_sector_table_selection_changed)
        self.sector_table.cellDoubleClicked.connect(self._on_sector_table_dblclick)
        self.sector_table.cellClicked.connect(self._on_sector_table_cell_clicked)
        # [NEW] 排序后自动滚动到顶部
        self.sector_table.horizontalHeader().sortIndicatorChanged.connect(lambda: self.sector_table.scrollToTop())
        llay.addWidget(self.sector_table)
        self.splitter.addWidget(left)

        # 右：个股明细
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(2)

        # 龙头迷你 K 线
        self.kline_lbl = QLabel("─" * 40)
        self.kline_lbl.setFont(QFont("Courier New", 11))
        self.kline_lbl.setStyleSheet(
            "background:#0d1b2a;color:#00ff88;padding:3px 6px;border-radius:3px;"
        )
        rlay.addWidget(self.kline_lbl)

        # 🚀 [NEW] Sorting State Initialization
        self._sector_sort_col = 1 # Default: Score
        self._sector_sort_asc = False 
        self._watchlist_sort_col = 4 # Default: Time
        self._watchlist_sort_asc = False

        self.leader_lbl = QLabel("")
        self.leader_lbl.setStyleSheet("color:#FF6666;font-weight:bold;font-size:12px;")
        rlay.addWidget(self.leader_lbl)

        # 个股表（带排序）
        COLS = ['代码', '名称', '角色', '现价', '涨幅%', '涨跌', 'dff', '分时走势', '形态暗示(安)']
        self.stock_table = QTableWidget(0, len(COLS))
        self.stock_table.setHorizontalHeaderLabels(COLS)
        hdr = self.stock_table.horizontalHeader()
        if hdr:
            hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            # 🚀 [C-Reinforcement] 显式设置各列初始宽度与伸缩行为
            self.stock_table.setColumnWidth(0, 65)  # 代码
            self.stock_table.setColumnWidth(1, 75)  # 名称
            self.stock_table.setColumnWidth(2, 60)  # 角色
            self.stock_table.setColumnWidth(3, 65)  # 现价
            self.stock_table.setColumnWidth(4, 75)  # 涨幅
            self.stock_table.setColumnWidth(5, 120) # 涨跌 [p_diff (pct_slc)]
            self.stock_table.setColumnWidth(6, 60)  # dff
            self.stock_table.setColumnWidth(7, 95)  # 分时走势 (绘图列)
            
            # 最后一列“形态暗示”设置为自动拉伸，确前面的列位置固定
            hdr.setSectionResizeMode(len(COLS)-1, QHeaderView.ResizeMode.Stretch)
            
            hdr.sectionClicked.connect(self._on_header_clicked)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self._show_context_menu)
        self.stock_table.cellClicked.connect(self.on_stock_clicked)  # 点击联动
        self.stock_table.cellDoubleClicked.connect(self._on_stock_double_clicked) # 双击放大
        self.stock_table.currentCellChanged.connect(self.on_stock_cell_changed) # 键盘光标联动
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.setFont(QFont("Microsoft YaHei", 9))
        self.stock_table.setSortingEnabled(False)   # 手动排序
        self.stock_table.setItemDelegateForColumn(7, TrendDelegate(self)) # [FIX] 对准分时走势列
        self.stock_table.horizontalHeader().sortIndicatorChanged.connect(lambda: self.stock_table.scrollToTop())
        vh = self.stock_table.verticalHeader()
        if vh: vh.setDefaultSectionSize(32) # 紧凑行高
        rlay.addWidget(self.stock_table)
        self.splitter.addWidget(right)

        # [MODIFIED] Default ratio 4.5:5.5
        self.splitter.setSizes([495, 605]) 
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)

        # ── [NEW] 底部：当日重点表 (Watchlist) ───────────────────────────
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setChildrenCollapsible(False)
        self.v_splitter.addWidget(self.splitter)

        self.watchlist_group = QGroupBox("📋 当日重点表 (共 0 只, 涨停/溢出个股)")
        self.watchlist_group.setStyleSheet("QGroupBox { font-weight:bold; color:#aad4ff; }")
        w_lay = QVBoxLayout(self.watchlist_group)
        w_lay.setContentsMargins(2, 6, 2, 2)
        
        W_COLS = ['代码', '名称', '涨幅%', '核心板块', '触发时间', '状态/原因']
        self.watchlist_table = QTableWidget(0, len(W_COLS))
        self.watchlist_table.setHorizontalHeaderLabels(W_COLS)
        self.watchlist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.watchlist_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.watchlist_table.verticalHeader().setVisible(False)
        self.watchlist_table.verticalHeader().setDefaultSectionSize(25) # 紧凑行高
        self.watchlist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.watchlist_table.setAlternatingRowColors(True)
        self.watchlist_table.setFont(QFont("Microsoft YaHei", 9))
        self.watchlist_table.setSortingEnabled(False) # [PURE PYTHON SORT]
        self.watchlist_table.horizontalHeader().sectionClicked.connect(self._on_watchlist_header_clicked)
        # [NEW] 排序后自动滚动到顶部
        self.watchlist_table.horizontalHeader().sortIndicatorChanged.connect(lambda: self.watchlist_table.scrollToTop())
        
        # 启用右键菜单支持 (用于联动活跃板块)
        self.watchlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.watchlist_table.customContextMenuRequested.connect(self._on_watchlist_context_menu)
        
        # [FIX] 补齐联动信号
        self.watchlist_table.cellClicked.connect(self._on_watchlist_clicked)
        self.watchlist_table.cellDoubleClicked.connect(self._on_watchlist_dblclick)
        self.watchlist_table.currentCellChanged.connect(self._on_watchlist_cell_changed)
        
        w_lay.addWidget(self.watchlist_table)
        self.v_splitter.addWidget(self.watchlist_group)
        self.v_splitter.setSizes([500, 180]) # 默认分配比例
        
        root.addWidget(self.v_splitter, 1)   # stretch=1 撑满剩余高度

        # [NEW] 焦点监控：用于处理排序回顶与选中项跟踪的动态切换
        self._last_focused_widget = None
        for table in [self.sector_table, self.stock_table, self.watchlist_table]:
            table.installEventFilter(self)
            table._reset_on_next_sort = False

    # ------------------------------------------------------------------ helpers
    def eventFilter(self, obj, event):
        """[UX] 监控焦点切换，自动处理排序重置逻辑"""
        if event.type() == QEvent.Type.FocusIn:
            if obj in [self.sector_table, self.stock_table, self.watchlist_table]:
                if self._last_focused_widget != obj:
                    obj._reset_on_next_sort = True
                    self._last_focused_widget = obj
                    # logger.debug(f"[Focus] Reset sort top for {obj.objectName()}")
        return super().eventFilter(obj, event)

    def _make_cb(self, text: str, key: str, layout: QHBoxLayout) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(self.detector.strategies[key]['enabled'])
        cb.stateChanged.connect(self._on_strategy_changed)
        layout.addWidget(cb)
        return cb

    @staticmethod
    def _make_spin(lo, hi, step, val) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setValue(val)
        sp.setFixedWidth(58)
        return sp

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet("color:#555;")
        return f

    # ------------------------------------------------------------------ data
    def manual_refresh(self):
        """手动触发评分计算和 UI 刷新 (增加防抖和状态反馈)"""
        if not hasattr(self, 'btn_refresh'): return
        
        # [NEW] 历史模式专门路径
        if self._is_history_mode:
            self._refresh_sector_list()
            self._populate_watchlist()
            # [FIX] 搜索时右侧表无法及时更新：强制同步当前板块详情
            if self.sector_table.currentRow() >= 0:
                self._on_sector_table_selection_changed()
            return

        try:
            # 1. 按钮防抖与反馈
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText("扫描中...")
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("⏳ [实时模式] 正在异步计算评分映射...")
                self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")
            
            # [FIX] 利用现有的 QThread (_worker) 安全执行
            if hasattr(self, '_worker'):
                self.detector.reset_observation_anchors()
                with self._update_lock:
                    self._force_update_requested = True
                
                if hasattr(self.main_window, 'df_all') and self.main_window.df_all is not None:
                    # 如果有实盘数据，推入队列，触发计算
                    self.on_realtime_data_arrived(self.main_window.df_all, force_update=True)
                else:
                    # 否则触发全量异步 sweep
                    self._worker.trigger_recalc()
            
            # 使用更安全的定时恢复 (避免已销毁组件的 lambda crash)
            QTimer.singleShot(2500, self._restore_refresh_button_state)
            
        except Exception as e:
            logger.error(f"Manual refresh failed: {e}")
            self._restore_refresh_button_state()

    def _restore_refresh_button_state(self):
        """安全恢复刷新按钮状态"""
        try:
            if hasattr(self, 'btn_refresh'):
                self.btn_refresh.setEnabled(True)
                self.btn_refresh.setText("刷新 🔄")
        except RuntimeError: pass # Handle C++ object deleted

    def _run_sbc_test(self, use_live: bool, code: str = None, extra_lines: dict = None):
        """调用 SBC 信号验证逻辑"""
        # 检查是否已有线程正在运行
        if hasattr(self, '_sbc_thread') and self._sbc_thread.isRunning():
            QMessageBox.information(self, "请稍候", f"后台正在对 {self._sbc_thread.code} 进行验证，请等待完成后再试。")
            return

        if not code:
            code = self._get_selected_stock()
            
        if not code:
            QMessageBox.warning(self, "未选中个股", "请在个股表或重点表中先选中一只个股再执行测试。")
            return
            
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import Qt
        modifiers = QGuiApplication.keyboardModifiers()
        is_multi_window = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        self._sbc_test_is_multi = is_multi_window
        
        # 尝试获取主窗口的 HDF5 锁
        hdf5_lock = getattr(self.main_window, 'hdf5_mutex', None)
        
        # 记录正在测试的状态
        status_msg = f"正在测试 {code} ({'实时' if use_live else '回放'})..."
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"⏳ {status_msg}")
            self.status_lbl.setStyleSheet("color: yellow; font-weight: bold;")
        
        # 创建并启动后台线程
        self._sbc_thread = SBCTestThread(code, use_live, hdf5_lock=hdf5_lock, extra_lines=extra_lines)
        self._sbc_thread.finished_data.connect(self._on_sbc_test_finished)
        self._sbc_thread.error_occurred.connect(self._on_sbc_test_error)
        self._sbc_thread.start()
        
        logger.info(f"⏳ SBC 信号测试已启动后台线程: {code} (Live Mode: {use_live})")

    def _on_sbc_test_finished(self, data: dict):
        """SBC 测试完成回调"""
        try:
            # 动态导入可视化函数
            try:
                from stock_visual_utils import show_chart_with_signals
            except ImportError:
                from stock_standalone.stock_visual_utils import show_chart_with_signals
            
            # 管理窗口引用，防止被回收
            if not hasattr(self, '_sbc_test_windows'):
                self._sbc_test_windows = []
            
            # [CLEANUP] Remove destroyed windows
            self._sbc_test_windows = [w for w in self._sbc_test_windows if w and not w.isHidden()]
            
            is_multi = getattr(self, '_sbc_test_is_multi', False)
            existing_win = self._sbc_test_windows[-1] if self._sbc_test_windows and not is_multi else None
            
            # 使用返回的结果包调用可视化
            win = show_chart_with_signals(
                data["viz_df"],
                data["signals"],
                data["title"],
                avg_series=data["avg_series"],
                time_labels=data["time_labels"],
                use_line=data["use_line"],
                extra_lines=data.get("extra_lines"),
                existing_win=existing_win
            )
            
            if win and win not in self._sbc_test_windows:
                self._sbc_test_windows.append(win)
                logger.info(f"✅ SBC 可视化窗口已创建: {data['title']}")
            
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(f"✅ SBC 测试完成: {data['title']}")
                self.status_lbl.setStyleSheet("color: #00FF00; font-weight: bold;")
                # 5秒后还原
                QTimer.singleShot(5000, lambda: self.status_lbl.setText("准备就绪"))
                
        except Exception as e:
            logger.error(f"SBC 可视化显示失败: {e}")
            self._on_sbc_test_error(f"渲染图表失败: {str(e)}")

    def _on_sbc_test_error(self, err_msg: str):
        """线程出错回调"""
        logger.error(f"❌ SBC 测试线程出错: {err_msg}")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText("❌ SBC 错误")
            self.status_lbl.setStyleSheet("color: red; font-weight: bold;")
        QMessageBox.critical(self, "SBC 测试错误", err_msg)

    def _get_selected_stock(self) -> Optional[str]:
        """提取当前选中的个股代码"""
        # 1. 优先检查中间个股明细表
        row = self.stock_table.currentRow()
        if row >= 0:
            it = self.stock_table.item(row, 0)
            if it: return it.text()
            
        # 2. 兜底检查底部重点表
        row = self.watchlist_table.currentRow()
        if row >= 0:
            it = self.watchlist_table.item(row, 0)
            if it: return it.text()
            
        return None

    def on_realtime_data_arrived(self, df_all, force_update=False):
        """主线程调用，将数据推入后台线程避免卡顿 UI"""
        
        if self._is_history_mode:
            return

        try:
            # ✔ 丢弃旧数据（正确方式）
            while True:
                try:
                    self._worker.df_queue.get_nowait()
                except Empty:
                    break

            # 推入最新数据（纵深防御：即使调用者忘记 copy，此处兜底）
            self._worker.add_data(df_all.copy())  # [THREAD-SAFETY] 防御性 copy

            with self._update_lock:
                self._force_update_requested = force_update

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error(f"[SectorBiddingPanel] queue realtime_data failed: {e}")

    def _on_worker_finished(self):
        """在主线程被调用，由后台真正计算完毕后触发UI更新"""
        try:
            now = time.time()
            
            # [REFINED] 动态获取 sleep 时间，直接从已经导入的 cct.CFG 获取
            try:
                # cct (JohnsonUtil.commonTips) 已经在模块顶部导入
                limit = float(getattr(cct.CFG, 'duration_sleep_time', 5.0))
            except:
                limit = 5.0
                
            # 允许竞价期间更快速刷新 (最低 1s)
            limit = max(1.0, limit)
            
            with self._update_lock:
                should_refresh = self._force_update_requested or (now - self._last_refresh_ts >= 0.2) # Throttled to 5 FPS
            
            if should_refresh:
                # [HEARTBEAT] 前台刷新心跳
                if self.detector.enable_log:
                    logger.info(f"💓 [Board Panel] Refreshing heartbeat: Total sectors={len(self.detector.active_sectors)}")
                    
                self._refresh_sector_list()
                self._last_refresh_ts = now
                with self._update_lock:
                    self._force_update_requested = False
                
        except Exception as e:
            logger.error(f"[SectorBiddingPanel] _on_worker_finished err: {e}")

    def _refresh_sector_list(self, reset_to_top: bool = False):
        # 1. 安全检查
        if not hasattr(self, '_worker') or self._worker is None:
            return

        # 2. 状态判断：不再直接访问 Queue（关键修复）
        qsize = self._worker.df_queue.qsize() if self._worker else 0

        if qsize > 0:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(
                    f"📡 正在拉取个股分时 (队列: {qsize})..."
                )
                self.status_lbl.setStyleSheet(
                    "color: #FFD700; font-weight: bold;"
                )

        # 3. 获取板块数据
        sectors = self.detector.get_active_sectors()

        if not sectors:
            if hasattr(self, 'status_lbl') and qsize == 0:
                self.status_lbl.setText("📝 目前无满足门槛的活跃板块 (或正在计算中)")
                self.status_lbl.setStyleSheet("color: #AAAAAA;")

            self.sector_table.setRowCount(0)
            return

        now_str = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(
                f"✅ 刷新完成 ({now_str}) | 活跃板块: {len(sectors)}"
            )
            self.status_lbl.setStyleSheet("color: #aad4ff; font-weight: bold;")

        # 4. 记住选中项 (为复用做准备)
        selected_sector = ""
        items = self.sector_table.selectedItems()
        if items:
            selected_sector = self.sector_table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)

        # [NEW] 5. Python Level Sorting
        col, asc = self._sector_sort_col, self._sector_sort_asc
        if col == 0: sectors.sort(key=lambda x: x.get('sector', ''), reverse=not asc)
        elif col == 1: sectors.sort(key=lambda x: x.get('score', 0), reverse=not asc)
        elif col == 2: sectors.sort(key=lambda x: x.get('score_diff', 0), reverse=not asc)
        elif col == 3: sectors.sort(key=lambda x: x.get('leader_name', ''), reverse=not asc)

        # 6. 表格渲染 (Dirty Check Update)
        self.sector_table.setUpdatesEnabled(False)
        self.sector_table.blockSignals(True)
        
        current_rows = self.sector_table.rowCount()
        new_count = len(sectors)
        if current_rows != new_count:
            self.sector_table.setRowCount(new_count)

        # 6. 填充数据 (Reuse & Diff Update)
        for i, sdata in enumerate(sectors):
            sn = sdata['sector']
            sc = sdata['score']
            tags = sdata.get('tags', '')
            lp = sdata.get('leader_pct', 0)
            ln = sdata.get('leader_name', '未知')

            # Pre-compute search blob (avoid concat in eval)
            sdata['_search_blob'] = f"{sn} {tags} {ln}".lower()

            if sc >= 15:
                color = self._color_red
                icon_char = "🔥"
            elif sc >= 8:
                color = self._color_orange
                icon_char = "⚡"
            else:
                color = self._color_gray
                icon_char = "📊"

            # Col 0: Name
            self._update_cell(self.sector_table, i, 0, f"{icon_char} {sn}", 
                            color=color, user_role=sn)

            diff = sdata.get('score_diff', 0.0)

            # Col 1: Score
            self._update_cell(self.sector_table, i, 1, f"{sc:.1f}", 
                            color=color, alignment=Qt.AlignmentFlag.AlignCenter, 
                            is_numeric=True)

            # Col 2: Diff
            diff_text = f"{diff:+.1f}" if diff != 0 else "0.0"
            diff_color = self._color_red if diff > 0.1 else (self._color_green if diff < -0.1 else color)
            self._update_cell(self.sector_table, i, 2, diff_text, 
                            color=diff_color, alignment=Qt.AlignmentFlag.AlignCenter, 
                            is_numeric=True)

            # Col 3: Leader
            self._update_cell(self.sector_table, i, 3, f"{ln} ({lp:+.1f}%)", 
                            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            # Col 4: Tags
            self._update_cell(self.sector_table, i, 4, tags, font=self._small_font)

            if sn == selected_sector:
                self.sector_table.selectRow(i)

        # 7. 恢复 UI
        self.sector_table.setUpdatesEnabled(True)
        self.sector_table.blockSignals(False)

        # 8. 默认选中
        if not self.sector_table.selectedItems() and self.sector_table.rowCount() > 0:
            self.sector_table.selectRow(0)
            
        if reset_to_top and self.sector_table.rowCount() > 0:
            self.sector_table.selectRow(0)
            self.sector_table.scrollToTop()

        # 9. 联动刷新
        if self.sector_table.selectedItems():
            self._on_sector_table_selection_changed()

        # 10. 状态栏最终更新
        sub_cnt = len(self.detector._subscribed)
        sess = self._session_str()

        if hasattr(self, '_active_search_query') and self._active_search_query:
            self.status_lbl.setText(
                f"[{sess}] 过滤模式 | 关键字: {self._active_search_query}"
            )
        else:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(
                    f"[{sess}] 订阅:{sub_cnt}  活跃板块:{len(sectors)}"
                )

        # 11. 重点表刷新
        self._populate_watchlist()
        
    # ------------------------------------------------------------------ sector select
    def _on_sector_table_selection_changed(self):
        """板块表选中项变更 → 刷新个股列表"""
        curr_row = self.sector_table.currentRow()
        if curr_row < 0:
            self.stock_table.setRowCount(0)
            return

        # 获取当前单元格的内容，Data 被存在第一列
        item = self.sector_table.item(curr_row, 0)
        if not item: return
        
        sn = item.data(Qt.ItemDataRole.UserRole)
        # [OPTIMIZE] 仅当版本变化或强制请求时更新
        current_version = getattr(self.detector, 'data_version', 0)
        
        # 遍历探测器中的活跃板块，找到匹配的数据
        for d in self.detector.get_active_sectors():
            if d['sector'] == sn:
                # [OPTIMIZE] 检查是否需要更新
                with self._update_lock:
                    force = self._force_update_requested
                
                # [UX] 响应个股标题点击传导的重置信号，或者检测到板块切换时也自动回顶
                reset_to_top = getattr(self.stock_table, '_temp_reset_to_top', False)
                if not reset_to_top:
                    last_sect = getattr(self.stock_table, '_last_populated_sector', None)
                    if last_sect != sn:
                        reset_to_top = True

                self.stock_table._temp_reset_to_top = False # 消费掉
                    
                self._populate_table(d, reset_to_top=reset_to_top)
                
                # [NEW] 联动逻辑：如果是用户光标切换（且不是正在刷新的静默状态），自动联动龙头
                if self.sector_table.hasFocus():
                    leader_code = d.get('leader')
                    if leader_code:
                        self._link_code(leader_code, focus_widget=self.sector_table)
                return

    def _on_sector_table_cell_clicked(self, row, col):
        """点击板块表单元格 → 自动联动龙头"""
        item = self.sector_table.item(row, 0)
        if not item: return
        
        sn = item.data(Qt.ItemDataRole.UserRole)
        for d in self.detector.get_active_sectors():
            if d['sector'] == sn:
                # 无论点击哪一列，都联动该板块的龙头
                self._link_code(d['leader'], focus_widget=self.sector_table)
                break

    def _on_sector_table_dblclick(self, row, col):
        """双击板块行 → 将龙头代码同步联动 (TK/Qt) + 复制板块名称"""
        item = self.sector_table.item(row, 0)
        if not item: return
        
        sn = item.data(Qt.ItemDataRole.UserRole)
        # 复制板块名称到剪贴板
        self._copy_to_clipboard(str(sn))
        
        for d in self.detector.get_active_sectors():
            if d['sector'] == sn:
                # 执行代码联动 (Link Code)
                self._link_code(d['leader'])
                break

    # [DEPRECATED] 兼容性占位
    def _on_sector_selected(self, cur, _prev):
        pass

    def _on_sector_dblclick(self, item):
        pass

    # ------------------------------------------------------------------ Event Handling
    def eventFilter(self, source, event):
        """拦截并处理特定组件的底层事件"""
        # 1. 拦截搜索历史下拉列表的点击，防止误触发选择
        if hasattr(self, 'search_input') and source == self.search_input.view().viewport():
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                pos = event.pos()
                view = self.search_input.view()
                index = view.indexAt(pos)
                if index.isValid():
                    # 获取该项的物理矩形
                    visual_rect = view.visualRect(index)
                    # 模拟 option 以复用 Delegate 的位置算法
                    option = QStyleOptionViewItem()
                    option.rect = visual_rect
                    
                    btn_rect = SearchHistoryDelegate.get_btn_rect(option)
                    if btn_rect.contains(pos):
                        # 确认为删除按钮点击
                        if index.data() != "龙头":
                            self._delete_history_item_by_row(index.row())
                        # 🛡️ 核心：返回 True 彻底截断该按下事件，让 ComboBox 无法触发 activated 信号
                        return True
        
        return super().eventFilter(source, event)

    # ------------------------------------------------------------------ search functionality
    def _on_search_triggered(self):
        query = self.search_input.currentText().strip()
        if not query:
            query = self.search_input.placeholderText().replace("例如:", "").strip()
            self.search_input.setCurrentText(query)
        
        # [NEW] 龙头特殊逻辑
        if query == "龙头":
            self._is_leader_search_mode = True
            self._active_search_query = ""
        else:
            self._is_leader_search_mode = False
            self._active_search_query = query
        
        # [NEW] 维护历史记录 (置顶并去重)
        if query not in self._search_history:
            self._search_history.insert(0, query)
        else:
            self._search_history.remove(query)
            self._search_history.insert(0, query)
        
        # 保持 ComboBox 列表同步 (仅保留最近 20 条)
        self._search_history = self._search_history[:20]
        self._update_search_combo_list(current_text=query)
        
        self.manual_refresh()
        
    def _on_search_history_context_menu(self, pos):
        """处理搜索历史下拉项的右键删除逻辑"""
        index = self.search_input.view().indexAt(pos)
        if not index.isValid():
            return
        
        item_text = self.search_input.itemText(index.row())
        if item_text == "龙头": # 保留默认核心项
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2c3e50; color: white; border: 1px solid #444; } QMenu::item:selected { background-color: #34495e; }")
        
        del_action = menu.addAction("❌ 删除此条记录")
        menu.addSeparator()
        clear_action = menu.addAction("🗑️ 清空所有历史")
        
        action = menu.exec(self.search_input.view().mapToGlobal(pos))
        if action == del_action:
            self._delete_history_item_by_row(index.row())
        elif action == clear_action:
            self._search_history = []
            self._update_search_combo_list()
            self._save_ui_state()

    def _delete_history_item_by_row(self, row: int):
        """按行号删除搜索历史"""
        item_text = self.search_input.itemText(row)
        if not item_text or item_text == "龙头":
            return
            
        if item_text in self._search_history:
            self._search_history.remove(item_text)
        
        self._update_search_combo_list()
        self._save_ui_state()
        # logger.debug(f"🗑️ [SectorPanel] Deleted history: {item_text}")

    def _update_search_combo_list(self, current_text: str = None):
        """统一管理搜索下拉框列表，确保'龙头'始终在首位"""
        self.search_input.blockSignals(True)
        self.search_input.clear()
        # 1. 强制添加龙头
        self.search_input.addItem("龙头")
        # 2. 添加其余历史记录 (排除龙头)
        other_history = [it for it in self._search_history if it != "龙头"]
        self.search_input.addItems(other_history)
        
        if current_text is not None:
            self.search_input.setCurrentText(current_text)
        else:
            # [FIX] 不再默认选中“龙头”，保持输入框空白或显示 Placeholder
            self.search_input.setCurrentIndex(-1)
            self.search_input.lineEdit().clear()
            
        self.search_input.blockSignals(False)
            
    def _on_search_cleared(self):
        self.search_input.setCurrentText("")
        self._active_search_query = ""
        self._is_leader_search_mode = False
        # 恢复标题
        self.watchlist_group.setTitle("📋 当日重点表 (共 0 只, 涨停/溢出个股)")
        # [FIX] 无论什么模式，清空搜索后都强制全局重刷一次 UI
        self.manual_refresh()
        
    def _evaluate_search_condition(self, query_str: str, row_data: dict) -> bool:
        """
        Evaluate natural queries like "MA60反转 涨幅>3 涨幅<8".
        Returns True if row_data matches ALL whitespace-separated conditions.
        """
        if not query_str:
            return True
            
        conditions = query_str.split()
        
        for cond in conditions:
            # Check for numeric comparators: >, <, >=, <=, =
            match = re.search(r'(涨幅|现价|量比)(>=|<=|>|<|==|=)([-+]?\d*\.?\d+)', cond)
            if match:
                field, op, val_str = match.groups()
                try:
                    target_val = float(val_str)
                    actual_val = 0.0
                    
                    if field == '涨幅':
                        actual_val = row_data.get('pct', 0.0)
                        if 'leader_pct' in row_data:
                            actual_val = row_data.get('leader_pct', 0.0) 
                    elif field == '现价':
                        actual_val = row_data.get('price', 0.0)
                        if 'leader_price' in row_data:
                             actual_val = row_data.get('leader_price', 0.0)
                    elif field == '量比':
                        # [FIX] 从元数据或当前行情中尝试提取量比，如果没有则默认为 0
                        actual_val = row_data.get('vol_ratio', row_data.get('meta', {}).get('vol_ratio', 0.0))
                    
                    # [FIX] 运算符归一化映射
                    op_map = {
                        '>=': '>=', '=>': '>=',
                        '<=': '<=', '=<': '<=',
                        '>': '>', '<': '<',
                        '=': '==', '==': '=='
                    }
                    real_op = op_map.get(op, '==')
                    
                    if real_op == '>':
                        if not actual_val > target_val: return False
                    elif real_op == '<':
                        if not actual_val < target_val: return False
                    elif real_op == '>=':
                        if not actual_val >= target_val: return False
                    elif real_op == '<=':
                        if not actual_val <= target_val: return False
                    elif real_op == '==':
                        if not abs(actual_val - target_val) < 0.01: return False
                        
                except ValueError:
                    continue # Ignore invalid floats
            else:
                # [OPTIMIZE] Use pre-computed search blob
                search_blob = row_data.get('_search_blob')
                if not search_blob:
                    # Fallback compute once if missing
                    search_blob = (
                        str(row_data.get('code', '')) + 
                        str(row_data.get('name', '')) + 
                        str(row_data.get('hint', '')) + 
                        str(row_data.get('pattern_hint', '')) + 
                        str(row_data.get('leader_name', '')) +
                        str(row_data.get('role', '')) +
                        str(row_data.get('tags', ''))
                    ).lower()
                    row_data['_search_blob'] = search_blob
                
                if cond.lower() not in search_blob:
                    return False
                    
        return True

    # ------------------------------------------------------------------ table fill
    def _populate_table(self, data: dict, reset_to_top: bool = False):
        leader_code   = data.get('leader', '')
        leader_name   = data.get('leader_name', leader_code)
        leader_pct    = data.get('leader_pct', 0.0)
        leader_price  = data.get('leader_price', 0.0)
        leader_klines = data.get('leader_klines', [])
        followers     = data.get('followers', [])

        mini = _ascii_kline(leader_klines, width=44, last_close=data.get('leader_last_close', 0))
        self.kline_lbl.setText(f"龙头分时: {mini}")
        self.leader_lbl.setText(
            f"🏆 {leader_name} [{leader_code}]  "
            f"现价:{leader_price:.2f}  涨幅:{leader_pct:+.2f}%  "
            f"K线:{len(leader_klines)}棒"
        )

        # [NEW] 支撑精细化角色显示 (龙头竞赛逻辑)
        race_candidates = data.get('race_candidates', [])
        rows = []
        
        if race_candidates:
            # 优先采用 detector 算好的竞赛明细
            for rc in race_candidates:
                code = rc['code']
                # 尝试补充详情 (从 followers 或 global_snap_cache)
                r_data = None
                # 先找 leader
                if code == leader_code:
                    r_data = {
                        'pct_diff': data.get('leader_pct_diff', 0.0),
                        'price_diff': data.get('leader_price_diff', 0.0),
                        'dff': data.get('leader_dff', 0.0),
                        'klines': leader_klines,
                        'last_close': data.get('leader_last_close', 0),
                        'high_day': data.get('leader_high_day', 0),
                        'low_day': data.get('leader_low_day', 0),
                        'last_high': data.get('leader_last_high', 0),
                        'last_low': data.get('leader_last_low', 0),
                        'hint': data.get('pattern_hint', '主力拉升'),
                        'untradable': data.get('is_untradable', False),
                        'is_counter': data.get('is_counter_trend', False)
                    }
                else:
                    # 再从 followers 中找
                    for f in data.get('followers', []):
                        if f['code'] == code:
                            r_data = f
                            break
                
                if r_data:
                    f_klines = r_data.get('klines', [])
                    rows.append({
                        'code': code, 'name': rc.get('name', '未知'),
                        'role': rc.get('role', '跟随📌'),
                        'pct': rc.get('pct', 0.0), 'price': r_data.get('price', 0.0),
                        'pct_diff': r_data.get('pct_diff', 0.0),
                        'price_diff': r_data.get('price_diff', 0.0),
                        'dff': r_data.get('dff', 0.0),
                        'klines': f_klines,
                        'k_cache': {
                            'prices': [float(k.get('close', 0)) for k in f_klines],
                            'volumes': [float(k.get('volume', k.get('vol', 0))) for k in f_klines]
                        },
                        'last_close': r_data.get('last_close', 0),
                        'high_day': r_data.get('high_day', 0),
                        'low_day': r_data.get('low_day', 0),
                        'last_high': r_data.get('last_high', 0),
                        'last_low': r_data.get('last_low', 0),
                        'hint': r_data.get('hint', r_data.get('pattern_hint', '板块联动')),
                        'untradable': r_data.get('untradable', r_data.get('is_untradable', False)),
                        'is_counter': r_data.get('is_counter', False)
                    })
        else:
            # Fallback: 使用传统的 Leader + Followers 结构
            rows = [{
                'code': leader_code, 
                'name': leader_name,
                'role': '🏆龙头',
                'pct': leader_pct, 
                'price': leader_price,
                'pct_diff': data.get('leader_pct_diff', data.get('pct_diff', 0.0)),
                'price_diff': data.get('leader_price_diff', 0.0),
                'dff': data.get('leader_dff', 0.0),
                'klines': leader_klines,
                'last_close': data.get('leader_last_close', 0),
                'high_day': data.get('leader_high_day', 0),
                'low_day': data.get('leader_low_day', 0),
                'last_high': data.get('leader_last_high', 0),
                'last_low': data.get('leader_last_low', 0),
                'hint': data.get('pattern_hint', '主力拉升'),
                'untradable': data.get('is_untradable', False),
                'is_counter': data.get('is_counter_trend', False)
            }]
            for f in data.get('followers', []):
                f_klines = f.get('klines', [])
                rows.append({
                    'code': f['code'], 'name': f['name'],
                    'role': '📌跟随',
                    'pct': f['pct'], 'price': f['price'],
                    'pct_diff': f.get('pct_diff', 0.0),
                    'price_diff': f.get('price_diff', 0.0),
                    'dff': f.get('dff', 0.0),
                    'klines': f_klines,
                    'k_cache': {
                        'prices': [float(k.get('close', 0)) for k in f_klines],
                        'volumes': [float(k.get('volume', k.get('vol', 0))) for k in f_klines]
                    },
                    'last_close': f.get('last_close', 0),
                    'high_day': f.get('high_day', 0),
                    'low_day': f.get('low_day', 0),
                    'last_high': f.get('last_high', 0),
                    'last_low': f.get('last_low', 0),
                    'hint': f.get('pattern_hint', '板块联动'),
                    'untradable': f.get('untradable', False),
                    'is_counter': False
                })

        # Filter based on active search
        active_query = getattr(self, '_active_search_query', '')
        if active_query:
            filtered_rows = []
            for r in rows:
                if self._evaluate_search_condition(active_query, r):
                    filtered_rows.append(r)
            rows = filtered_rows

        # 应用排序 (Manual Sort)
        col = self._sort_col
        rev = not self._sort_asc
        
        if col == 0:    # 代码
            rows.sort(key=lambda r: r.get('code', ''), reverse=rev)
        elif col == 1:  # 名称
            rows.sort(key=lambda r: r.get('name', ''), reverse=rev)
        elif col == 2:  # 角色
            rows.sort(key=lambda r: r.get('role', ''), reverse=rev)
        elif col == 3:  # 现价
            rows.sort(key=lambda r: r.get('price', 0.0), reverse=rev)
        elif col == 4:  # 涨幅
            rows.sort(key=lambda r: r.get('pct', 0.0), reverse=rev)
        elif col == 5:  # 涨跌 (切片涨跌/价格差值)
            # 优先按价格差值排序，更直观
            rows.sort(key=lambda r: r.get('price_diff', 0.0), reverse=rev)
        elif col == 6:  # dff (切片力度)
            rows.sort(key=lambda r: r.get('dff', 0.0), reverse=rev)
        
        # [NEW] Pre-compute search blobs for all rows (bulk move to worker context eventually)
        for r in rows:
            if '_search_blob' not in r:
                r['_search_blob'] = (f"{r['code']} {r['name']} {r['hint']} {r['role']}").lower()

        # 💡 [ENHANCEMENT] 如果用户没有主动点击排序，默认将龙头置顶
        # (这仅在上述 col 匹配不到或强制恢复时生效)
        # if col == -1: ...
        # 龙头始终置顶
        # [FIX] 减少闪烁并保持选择状态
        self.stock_table.setUpdatesEnabled(False)
        self._is_populating = True
        
        # 记录当前选中的代码，以便恢复
        if not self._last_selected_code and not reset_to_top:
            curr_row = self.stock_table.currentRow()
            if curr_row >= 0:
                item = self.stock_table.item(curr_row, 0)
                if item: self._last_selected_code = item.text()
        
        if reset_to_top:
            self._last_selected_code = None # 强制清除记忆以防干扰

        cur_rows = self.stock_table.rowCount()
        if cur_rows != len(rows):
            self.stock_table.setRowCount(len(rows))

        target_row = -1
        for i, r in enumerate(rows):
            # 1. 代码
            self._update_cell(self.stock_table, i, 0, r['code'], 
                            user_role_v1=data.get('sector', '未知'))
            
            # 2. 名称
            self._update_cell(self.stock_table, i, 1, r['name'])

            # 3. 角色
            role_c = self._color_red if '龙头' in r['role'] else None
            role_f = self._bold_font if '龙头' in r['role'] else None
            self._update_cell(self.stock_table, i, 2, r['role'], color=role_c, font=role_f)

            # 4. 现价
            self._update_cell(self.stock_table, i, 3, f"{r['price']:.2f}")

            # 5. 涨幅
            pct_c = self._color_red if r['pct'] > 0 else self._color_green
            self._update_cell(self.stock_table, i, 4, f"{r['pct']:+.2f}%", color=pct_c)
            
            # 6. 涨跌 [绝对额]
            p_diff = r.get('price_diff', 0.0)
            pct_slc = r.get('pct_diff', 0.0)
            diff_c = self._color_red if (p_diff > 0.001 or pct_slc > 0.01) else (self._color_green if (p_diff < -0.001 or pct_slc < -0.01) else self._color_gray)
            self._update_cell(self.stock_table, i, 5, f"{p_diff:+.2f}", 
                            color=diff_c, alignment=Qt.AlignmentFlag.AlignCenter, is_numeric=True)

            # 7. dff
            dff_val = r.get('dff', 0.0)
            dff_c = self._color_yellow if dff_val > 0 else (QColor("#00FFFF") if dff_val < 0 else None)
            self._update_cell(self.stock_table, i, 6, f"{dff_val:+.2f}", 
                            color=dff_c, is_numeric=True)

            # 8. 分时走势 (绘图列)
            # [OPTIMIZE] Use pre-calculated cache from Step 1
            k_cache = r.get('k_cache', {})
            k_data = {
                'klines': r.get('klines', []),      
                'prices': k_cache.get('prices', []),
                'volumes': k_cache.get('volumes', []),
                'last_close': r.get('last_close', 0),
                'now_price': r.get('price', 0)
            }
            # Note: _update_cell handles diff check for data objects
            self._update_cell(self.stock_table, i, 7, "", user_role=k_data)

            # 9. 形态暗示
            hint_str = r['hint']
            if r['untradable']: hint_str = "🚫一字板 " + hint_str
            if r['is_counter']: hint_str = "🔥逆势 " + hint_str
            
            hint_c = None
            if "今日主杀" in hint_str or "破均价线" in hint_str: hint_c = QColor("#FF1111")
            elif "新高" in hint_str or "突破" in hint_str or "放量" in hint_str: hint_c = self._color_yellow
            elif "支撑" in hint_str or "多头" in hint_str: hint_c = QColor("#FF99CC")
            elif r['untradable']: hint_c = self._color_gray
            elif r['is_counter']: hint_c = self._color_yellow
                
            self._update_cell(self.stock_table, i, 8, hint_str, color=hint_c)

            if r['code'] == self._last_selected_code:
                target_row = i

        self.stock_table._last_populated_sector = data.get('sector')

        # 恢复选中状态
        if reset_to_top and self.stock_table.rowCount() > 0:
            self.stock_table.setCurrentCell(0, 0)
            self.stock_table.scrollToTop()
        elif target_row >= 0:
            # [OPTIMIZE] Only set if focus or manually requested to avoid jumpy UI
            if self.stock_table.currentRow() != target_row:
                self.stock_table.setCurrentCell(target_row, 0)
        elif self.stock_table.rowCount() > 0 and not self.stock_table.selectedItems():
            # 没有任何选中的时候默认选第1个
            self.stock_table.setCurrentCell(0, 0)
        
        self._is_populating = False
        self.stock_table.setUpdatesEnabled(True)
        

    def _on_sector_header_clicked(self, col):
        """Python-level sort for sector table"""
        if self._sector_sort_col == col:
            self._sector_sort_asc = not self._sector_sort_asc
        else:
            self._sector_sort_col = col
            self._sector_sort_asc = False
            
        self.sector_table.horizontalHeader().setSortIndicator(col, Qt.SortOrder.AscendingOrder if self._sector_sort_asc else Qt.SortOrder.DescendingOrder)
        
        # [UX] 手动点击排序项始终回顶，并清理焦点重置标记
        reset_top = True
        self.sector_table._reset_on_next_sort = False
            
        self._refresh_sector_list(reset_to_top=reset_top)
        
    def _on_watchlist_header_clicked(self, col):
        """Python-level sort for watchlist table"""
        if self._watchlist_sort_col == col:
            self._watchlist_sort_asc = not self._watchlist_sort_asc
        else:
            self._watchlist_sort_col = col
            self._watchlist_sort_asc = False
            
        self.watchlist_table.horizontalHeader().setSortIndicator(col, Qt.SortOrder.AscendingOrder if self._watchlist_sort_asc else Qt.SortOrder.DescendingOrder)
        
        # [UX] 手动点击排序项始终回顶，并清理焦点重置标记
        reset_top = True
        self.watchlist_table._reset_on_next_sort = False
             
        self._populate_watchlist(reset_to_top=reset_top)

    def _update_cell(self, table, row, col, text, color=None, font=None, alignment=None, 
                     user_role=None, user_role_v1=None, is_numeric=False):
        """[INDUSTRIAL] Reuses table items and only updates if changed to minimize UI jitter."""
        item = table.item(row, col)
        if not item:
            if is_numeric:
                item = NumericTableWidgetItem(str(text))
            else:
                item = QTableWidgetItem(str(text))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, col, item)
        
        # 1. Text Update (Dirty Check)
        if item.text() != str(text):
            item.setText(str(text))
            
        # 2. Visual Style (Cached check would be faster but Qt QColor/QFont internal check is decent)
        if color: item.setForeground(color)
        if font: item.setFont(font)
        if alignment: item.setTextAlignment(alignment)
        
        # 3. Metadata
        if user_role is not None:
            # For dict/objects, simple equality check might be slow but it's better than full rebuild
            if item.data(Qt.ItemDataRole.UserRole) != user_role:
                item.setData(Qt.ItemDataRole.UserRole, user_role)
        if user_role_v1 is not None:
             if item.data(Qt.ItemDataRole.UserRole + 1) != user_role_v1:
                item.setData(Qt.ItemDataRole.UserRole + 1, user_role_v1)
        return item

    def _set_item(self, row, col, text):
        """[DEPRECATED] Use _update_cell instead."""
        return self._update_cell(self.stock_table, row, col, text)

    # ── [NEW] Watchlist Support ──────────────────────────────────────
    def _populate_watchlist(self, reset_to_top: bool = False):
        """填充底部当日重点表"""
        # [NEW] 龙头搜索模式逻辑
        if getattr(self, '_is_leader_search_mode', False):
            watchlist = []
            seen_codes = set()
            sectors = self.detector.get_active_sectors()
            for d in sectors:
                code = d.get('leader', '')
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)
                
                # [NEW] 获取精准挖掘时间 (first_breakout_ts)
                trigger_ts = 0
                # 尝试从探测器内部状态直接获取该个股的历史触发时间
                ts_obj = self.detector._tick_series.get(code)
                if ts_obj:
                    trigger_ts = ts_obj.first_breakout_ts
                
                # 如果尚未记录挖掘时间（可能属于刚领涨但未达爆发分值的萌芽股），使用数据流最后更新时间
                if trigger_ts <= 0:
                    trigger_ts = self.detector.last_data_ts if self.detector.last_data_ts > 0 else time.time()
                
                time_str = datetime.fromtimestamp(trigger_ts).strftime('%H:%M:%S')
                
                watchlist.append({
                    'code': code,
                    'name': d.get('leader_name', ''),
                    'pct': d.get('leader_pct', 0.0),
                    'sector': d.get('sector', ''),
                    'reason': '核心龙头',
                    'time_str': time_str
                })
        else:
            watchlist = self.detector.get_daily_watchlist()
        
        # [NEW] Filter based on active search
        active_query = getattr(self, '_active_search_query', '')
        if active_query:
            filtered_wl = []
            for w in watchlist:
                # Map watchlist fields to expect format for _evaluate_search_condition
                row_mock = {
                    'code': w['code'],
                    'name': w['name'],
                    'pct': w.get('pct', 0.0),
                    'sector': w.get('sector', ''),
                    'reason': w.get('reason', '')
                }
                if self._evaluate_search_condition(active_query, row_mock):
                    filtered_wl.append(w)
            watchlist = filtered_wl
        
        # 记录当前选中代码以便恢复
        selected_code = ""
        if not reset_to_top:
            curr_row = self.watchlist_table.currentRow()
            if curr_row >= 0:
                item = self.watchlist_table.item(curr_row, 0)
                if item: selected_code = item.text()

        cur_w_rows = self.watchlist_table.rowCount()
        new_count = len(watchlist)
        
        # [NEW] Pre-compute search blobs for watchlist (O(1) logic)
        for w in watchlist:
            if '_search_blob' not in w:
                w['_search_blob'] = (f"{w['code']} {w['name']} {w.get('sector', '')} {w.get('reason', '')}").lower()
        
        # [NEW] Python Level Sorting for Watchlist
        w_col, w_asc = self._watchlist_sort_col, self._watchlist_sort_asc
        if w_col == 0: watchlist.sort(key=lambda x: x.get('code', ''), reverse=not w_asc)
        elif w_col == 1: watchlist.sort(key=lambda x: x.get('name', ''), reverse=not w_asc)
        elif w_col == 2: watchlist.sort(key=lambda x: x.get('pct', 0), reverse=not w_asc)
        elif w_col == 3: watchlist.sort(key=lambda x: x.get('sector', ''), reverse=not w_asc)
        elif w_col == 4: watchlist.sort(key=lambda x: x.get('time_str', x.get('time', '')), reverse=not w_asc)
        
        # [OPTIMIZE] Only toggle layout changes if row count changed
        row_count_changed = (cur_w_rows != new_count)
        if row_count_changed:
            self.watchlist_table.setRowCount(new_count)
        
        target_row = -1
        
        for i, w in enumerate(watchlist):
            # 1. 代码
            self._update_cell(self.watchlist_table, i, 0, w['code'])
            
            # 2. 名称
            self._update_cell(self.watchlist_table, i, 1, w['name'])
            
            # 3. 涨幅
            p_val = w.get('pct', 0)
            p_c = self._color_red if p_val > 0 else self._color_green
            self._update_cell(self.watchlist_table, i, 2, f"{p_val:+.2f}%", color=p_c, is_numeric=True)
            
            # 4. 核心板块
            s_val = w.get('sector', '')
            # 过滤掉市场标签
            market_tags = ['科创板', '创业板', '主板', '中小板', '北证']
            all_cats = s_val.split(';')
            cats = [c for c in all_cats if c not in market_tags]
            sector_short = cats[0] if cats else (all_cats[0] if all_cats else 'N/A')
            self._update_cell(self.watchlist_table, i, 3, sector_short)
            
            # 5. 触发时间
            self._update_cell(self.watchlist_table, i, 4, str(w.get('time_str', w.get('time', '--:--:--'))))
            
            # 6. 状态/原因
            reason = w.get('reason', '')
            r_c = QColor("#FF1493") if '涨停' in reason else None
            self._update_cell(self.watchlist_table, i, 5, reason, color=r_c)

            if w['code'] == selected_code:
                target_row = i

        if reset_to_top and self.watchlist_table.rowCount() > 0:
            self.watchlist_table.setCurrentCell(0, 0)
            self.watchlist_table.scrollToTop()
        elif target_row >= 0:
            # [OPTIMIZE] Selection Debouncing: Only set if the jump is significant or no current selection
            curr_w_row = self.watchlist_table.currentRow()
            if curr_w_row < 0 or abs(curr_w_row - target_row) > 0:
                self.watchlist_table.blockSignals(True)
                self.watchlist_table.setCurrentCell(target_row, 0)
                self.watchlist_table.blockSignals(False)
        elif self.watchlist_table.rowCount() > 0 and not self.watchlist_table.selectedItems():
            self.watchlist_table.setCurrentCell(0, 0)
                
        # [NEW] Update Watchlist title stats (History/Search indicator integrated)
        search_suffix = ""
        if getattr(self, '_is_leader_search_mode', False):
            search_suffix = " | 🔍 搜索结果: 各板块龙头"
        elif getattr(self, '_active_search_query', ''):
            search_suffix = f" | 🔍 筛选: {self._active_search_query}"

        hist_suffix = ""
        if self._is_history_mode:
            try:
                # 显示完整日期时间
                f_dt = datetime.fromtimestamp(self.detector.baseline_time).strftime('%Y-%m-%d %H:%M:%S')
                hist_suffix = f" | 🎬 [历史复盘: {f_dt}]"
            except:
                hist_suffix = " | 🎬 [历史复盘]"
                
        self.watchlist_group.setTitle(f"📋 当日重点表 (共 {len(watchlist)} 只){search_suffix}{hist_suffix}")

    def _on_watchlist_clicked(self, row, col):
        """重点表联动"""
        item = self.watchlist_table.item(row, 0)
        if item:
            code = item.text()
            self._link_code(code, focus_widget=self.watchlist_table)

    def _on_watchlist_dblclick(self, row, col):
        """重点表双击：对应列执行不同动作"""
        code_item = self.watchlist_table.item(row, 0)
        name_item = self.watchlist_table.item(row, 1)
        if not code_item: return
        code, name = code_item.text(), (name_item.text() if name_item else "")

        # [NEW] 1. 复制功能：代码(0)复制代码, 名称(1)复制名称, 核心板块(3)复制板块
        if col == 0:
            self._copy_to_clipboard(code)
            return
        elif col == 1:
            self._copy_to_clipboard(name)
            return
        elif col == 3:
            sect_item = self.watchlist_table.item(row, 3)
            if sect_item: self._copy_to_clipboard(sect_item.text().strip())
            return

        # 2. 如果是代码/名称列，弹出详细走势图 (联动)
        if col <= 1:
            klines = self._follower_klines(code)
            meta = {'sector': self.watchlist_table.item(row, 3).text() if self.watchlist_table.item(row, 3) else 'N/A'}
            dlg = DetailedChartDialog(code, name, klines, meta, parent=self)
            dlg.exec()
            
            if hasattr(self, 'status_lbl'):
                sess = self._session_str()
                self.status_lbl.setText(f"[{sess}] 📊 已打开个股详情: {name} ({code})")

    def _on_watchlist_context_menu(self, pos):
        """重点表右键点击：联动到活跃板块"""
        item = self.watchlist_table.itemAt(pos)
        if not item: return
        
        row = item.row()
        col = item.column()
        
        # 仅在点击核心板块列(3)时触发联动
        if col == 3:
            sector_name = item.text().strip()
            if not sector_name: return
            
            # 自动联动到活跃板块列表
            target_sector = None
            # 兼容多板块字符串
            parts = [p.strip() for p in sector_name.split(';') if p.strip()]
            
            # 遍历左侧列表项寻找匹配
            found = False
            for i in range(self.sector_table.rowCount()):
                list_item = self.sector_table.item(i, 0)
                sn = list_item.data(Qt.ItemDataRole.UserRole)
                if sn in parts or any(p in sn for p in parts) or sn == sector_name:
                    self.sector_table.setCurrentCell(i, 0)
                    # 联动后焦点保留在重点表
                    self.watchlist_table.setFocus()
                    found = True
                    target_sector = sn
                    break
            
            # 状态栏提示结果
            if hasattr(self, 'status_lbl'):
                sess = self._session_str()
                if found:
                    self.status_lbl.setText(f"[{sess}] 🔗 已联动活跃板块: {target_sector}")
                else:
                    self.status_lbl.setText(f"[{sess}] ❌ 未在活跃板块中匹配到: {sector_name}")

    def _on_watchlist_cell_changed(self, row, col, old_row, old_col):
        """重点表键盘光标联动"""
        if self._is_populating or row < 0 or row == old_row:
            return
        if not self.watchlist_table.hasFocus():
            return
        item = self.watchlist_table.item(row, 0)
        if item:
            code = item.text()
            # 键盘切换时延迟触发联动，防止快速连续按键卡顿
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self._link_code(code, focus_widget=self.watchlist_table))

    def _follower_klines(self, code: str) -> List[dict]:
        with self.detector._lock:
            ts = self.detector._tick_series.get(code)
            klines = list(ts.klines)[-35:] if ts else []
            
        # [FIX] 如果 TickSeries 为空（可能由于冷启动尚未同步），尝试从实时服务拉取
        if not klines and self.detector.realtime_service:
            klines = self.detector.realtime_service.get_minute_klines(code, n=35)
            # 如果拉取到了，顺便同步给 TickSeries 以便后续性能更好
            if klines and ts:
                with self.detector._lock:
                    ts.load_history(klines)
        return klines

    def _render_kline_sparkline(self, klines: List[dict]) -> str:
        """简单的文本趋势图渲染 (增强版：支持更长趋势和相对均价指示)"""
        if not klines: return "───"
        try:
            # 提取收盘价
            prices = [float(k['close']) for k in klines]
            if len(prices) < 2: return "───"
            
            # 缩放窗口：增加到 30 个采样点，让趋势更绵长
            subset = prices[-30:] 
            p_min, p_max = min(subset), max(subset)
            p_avg = sum(subset) / len(subset)
            rng = p_max - p_min
            
            # 基础文本符号
            chars = " ▂▃▄▅▆▇█"
            
            res = []
            for p in subset:
                if rng == 0:
                    res.append("─")
                else:
                    idx = int((p - p_min) / rng * (len(chars) - 1))
                    res.append(chars[idx])
            
            # 计算总趋势点缀
            # 📈/📉 代表末尾对比开头的方向
            # 🟢/🔴 代表当前价格对比这段时间均价的位置 (强势度)
            trend_icon = "📈" if subset[-1] >= subset[0] else "📉"
            power_dot  = "●" if subset[-1] >= p_avg else "○" 
            
            return f"{power_dot}{trend_icon} " + "".join(res)
        except Exception as e:
            logger.debug(f"sparkline error: {e}")
            return "───"

    # ------------------------------------------------------------------ sort
    def _on_header_clicked(self, col: int):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = False # Default descending for scores/pct
            
        # Update header icons or sort indicators manually
        self.stock_table.horizontalHeader().setSortIndicator(col, Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder)
            
        # [UX] 手动点击排序项始终回顶，并清理焦点重置标记
        reset_top = True
        self.stock_table._reset_on_next_sort = False
            
        curr_row = self.sector_table.currentRow()
        if curr_row >= 0:
            # 内部调用 _populate_table 时，如果我们需要 reset，可以通过某种方式告知
            # 这里简单起见，我们直接设置属性让后续刷新感知
            self.stock_table._temp_reset_to_top = reset_top
            self._on_sector_table_selection_changed()
        else:
            # 兜底：如果左侧没选，尝试用缓存的板块刷新
            current_sector = getattr(self.stock_table, '_last_populated_sector', None)
            if current_sector:
                for d in self.detector.get_active_sectors():
                    if d['sector'] == current_sector:
                        self._populate_table(d, reset_to_top=reset_top)
                        break
    # ------------------------------------------------------------------ linkage
    def _on_stock_double_clicked(self, row, col):
        code_item = self.stock_table.item(row, 0)
        name_item = self.stock_table.item(row, 1)
        if not code_item: return
        code = code_item.text()
        name = name_item.text() if name_item else code

        # 复制功能：代码列(0)复制代码，名称列(1)复制名称
        if col == 0:
            self._copy_to_clipboard(code)
            return
        elif col == 1:
            self._copy_to_clipboard(name)
            return

        # 双击功能只在分时走势 (Column 7) 上有效
        if col != 7:
            return

        # 💡 [ENHANCEMENT] 尝试从 realtime_service 获取全量 K 线 (n=240, 约一整天)
        klines = []
        meta = {
            'last_close': 0, 'high_day': 0, 'low_day': 0,
            'last_high': 0, 'last_low': 0,
            'emotion': 50.0, 'popularity': 'N/A', 'theme': 'N/A'
        }
        
        if self.detector.realtime_service:
            rs = self.detector.realtime_service
            # 获取全量 K 线
            klines = rs.get_minute_klines(code, n=240)
            # 获取情绪分
            meta['emotion'] = rs.get_emotion_score(code)
            # 获取 55188 题材/人气等元数据
            ext = rs.get_55188_data(code)
            if ext:
                meta['popularity'] = ext.get('rank', 'N/A')
                meta['theme'] = ext.get('theme_name', ext.get('concept', 'N/A'))

        # 获取该行对应的基础价格元数据 (对应 _populate_table 中的 k_item 所在列 7)
        k_item = self.stock_table.item(row, 7)
        if k_item:
            pdata = k_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(pdata, dict):
                # [FIX] 优先从表格缓存获取 K 线 (支持历史快照)
                if not klines:
                    klines = pdata.get('klines', [])
                
                meta['last_close'] = pdata.get('last_close', 0)
                # 记录当前现价，以便在没有 K 线时补全
                meta['now_price'] = pdata.get('prices')[-1] if pdata.get('prices') else 0
        
        with self.detector._lock:
            ts = self.detector._tick_series.get(code)
            if ts:
                # [FIX] 如果依然没 K 线，尝试从 detector 内存获取
                if not klines:
                    klines = list(ts.klines)
                
                meta['high_day'] = ts.high_day
                meta['low_day'] = ts.low_day
                meta['last_high'] = ts.last_high
                meta['last_low'] = ts.last_low
                if meta['last_close'] == 0:
                    meta['last_close'] = ts.last_close

        dlg = DetailedChartDialog(code, name, klines, meta, self)
        dlg.exec()

    def on_stock_clicked(self, row, col, force_link=False):
        # 仅当点击 code(0) 或 name(1) 列时才联动，除非是 force_link (如键盘触发)
        if not force_link and col > 1: return

        code_item = self.stock_table.item(row, 0)
        if code_item:
            code = code_item.text()
            self._link_code(code, focus_widget=self.stock_table)

    def _link_code(self, code: str, focus_widget=None):
        """将股票代码同步联动到主界面或外挂工具"""
        host = self.main_window
        if not host: return
        
        try:
            # 🚀 [NEW] 核心修复：判断可视化窗口是否已打开，避免点击冷启动导致的 GIL 锁
            is_viz_open = False
            if hasattr(host, 'qt_process') and host.qt_process and host.qt_process.is_alive():
                is_viz_open = True

            is_history = getattr(self, '_is_history_mode', False)
            history_date = getattr(self, '_history_date', "")
            
            def _do_linkage_in_main_thread():
                # 🚀 [FIXED] 统一联动逻辑：竞价面板核心在于时间对齐，因此无论是否历史模式都执行 link_to_visualizer
                target_date = history_date
                today_str = datetime.now().strftime("%Y-%m-%d")
                if not target_date or history_date == today_str:
                    if hasattr(host, 'open_visualizer'):
                        host.open_visualizer(code)
                # 1. 优先调用 link_to_visualizer (代码切换 + 时间标记)
                elif hasattr(host, 'link_to_visualizer'):
                     host.link_to_visualizer(code, target_date)
                     logger.info(f"[SectorPanel] Linked {code} at {target_date} (Unified Linkage Mode)")
                
                # 2. 只有在没有综合接口时，才回退到简单的代码切换信号
                else:
                    if hasattr(host, 'scroll_to_code_signal'):
                        host.scroll_to_code_signal.emit(code)
                    elif hasattr(host, 'tree_scroll_to_code'):
                        host.tree_scroll_to_code(code, vis=is_viz_open)
        
                # 3. 如果主界面有 sender 对象，通过它发送 (处理 TDX/THS 联动)
                # 在主线程调用以保证安全提取 Tk 变量并防止剪贴板竞争
                if hasattr(host, 'sender') and host.sender:
                    host.sender.send(code)
                elif hasattr(self, 'sender') and self.sender:
                    # [NEW] 当独立运行或主窗口不具备 sender 时，使用本地 sender 联动
                    self.sender.send(code)

            # 🛡️ 深度防护：优先通过 Tkinter 调度队列转发，确保完全运行在 Tk 主线程
            if hasattr(host, 'tk_dispatch_queue'):
                host.tk_dispatch_queue.put_nowait(_do_linkage_in_main_thread)
            else:
                # 兜底方案：使用 Qt 异步定时器 (适用于纯 Qt 宿主或旧版本)
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, _do_linkage_in_main_thread)
        
            # 4. [FIX] 交互优化：根据来源恢复焦点，点击哪里光标留在哪里
            if focus_widget and focus_widget.isVisible():
                focus_widget.setFocus()
            elif not focus_widget and self.stock_table.isVisible():
                # 默认回退到个股表
                self.stock_table.setFocus()
            
            # 更新状态记录
            self._last_selected_code = code
            logger.debug(f"[SectorPanel] Linked code: {code} (viz_active:{is_viz_open})")
                 
        except Exception as e:
            logger.error(f"Error linking code {code}: {e}")

    def on_stock_cell_changed(self, row, col, old_row, old_col):
        """键盘上下键切换行时触发联动"""
        if self._is_populating:
            return
        if row < 0 or row == old_row:
            return
            
        # 只有在表格有焦点时，才是用户主动通过键盘切换的
        if not self.stock_table.hasFocus():
            return
            
        # 记录当前选中的代码
        item = self.stock_table.item(row, 0)
        if item:
            self._last_selected_code = item.text()

        # 联动逻辑同点击，强制触发联动
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self.on_stock_clicked(row, col, force_link=True))

    def _show_context_menu(self, pos):
        item = self.stock_table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code = (self.stock_table.item(row, 0) or QTableWidgetItem()).text()
        name = (self.stock_table.item(row, 1) or QTableWidgetItem()).text()
        if not code:
            return

        menu = QMenu(self)
        menu.addAction(f"🔗 联动 [{code}] {name}",
                       lambda: self.on_stock_clicked(row, 0))
        menu.addAction(f"📈 主窗口定位",
                       lambda: self.on_stock_clicked(row, 0))
        
        # [NEW] 定位所属板块
        sector_name = (self.stock_table.item(row, 0) or QTableWidgetItem()).data(Qt.ItemDataRole.UserRole + 1)
        if sector_name:
            menu.addAction(f"📂 定位所属板块: {sector_name}", lambda: self._locate_sector(sector_name))
            
        menu.addSeparator()
        menu.addAction("📋 复制代码", lambda: self._copy_to_clipboard(code))
        menu.addAction("📋 复制名称", lambda: self._copy_to_clipboard(name))
        menu.exec(self.stock_table.mapToGlobal(pos))

    def _add_to_hotlist(self, code: str, name: str):
        mw = self.main_window
        if mw and hasattr(mw, 'tk_dispatch_queue'):
            try:
                mw.tk_dispatch_queue.put_nowait(
                    (lambda c=code: mw.original_push_logic(c, select_win=True))
                    if hasattr(mw, 'original_push_logic') else (lambda: None)
                )
                return
            except Exception as e:
                logger.warning(f"[linkage] tk_dispatch_queue fail: {e}")
        # if hasattr(mw, 'original_push_logic'):
        #     mw.original_push_logic(code, select_win=False)
        elif hasattr(mw, 'current_code') and hasattr(mw, '_add_to_hotlist'):
            old = mw.current_code
            mw.current_code = code
            mw._add_to_hotlist()
            mw.current_code = old

    def _copy_to_clipboard(self, code: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(code)

    # ------------------------------------------------------------------ strategy
    def _on_threshold_changed(self, val):
        """同步强度门槛到 detector 并刷新列表"""
        self.detector.sector_score_threshold = float(val)
        # 板块分改变，通常也意味着观测锚点的重新审视 (可选：不一定要重置锚点)
        self._refresh_sector_list()

    def _adjust_interval(self, delta_m: int):
        """调节对比时长 (分钟)"""
        curr_m = int(self.detector.comparison_interval / 60)
        new_m = max(1, curr_m + delta_m)
        self.detector.comparison_interval = new_m * 60
        self.lbl_interval.setText(f"{new_m}m")
        # 调节时间意味着对比基准变了，重置所有锚点 (包括个股价格瞄点)
        self.detector.reset_observation_anchors()
        self.manual_refresh()


    def _on_strategy_changed(self):
        s = self.detector.strategies
        s['new_high']['enabled']       = self.cb_new_high.isChecked()
        s['ma_rebound']['enabled']     = self.cb_ma_rebound.isChecked()
        s['surge_vol']['enabled']      = self.cb_surge_vol.isChecked()
        s['consecutive_up']['enabled'] = self.cb_consec.isChecked()
        s['surge_vol']['min_ratio']    = self.spin_vol_ratio.value()
        s['pct_change']['min']         = self.spin_pct_min.value()
        s['pct_change']['max']         = self.spin_pct_max.value()
        
        # [NEW] Real-time Thresholds
        if hasattr(self, 'spin_score_threshold'):
            self.detector.score_threshold = self.spin_score_threshold.value()
        if hasattr(self, 'spin_sector_min_score'):
            self.detector.sector_min_score = self.spin_sector_min_score.value()
        if hasattr(self, 'spin_sector_score_threshold'):
            self.detector.sector_score_threshold = self.spin_sector_score_threshold.value()
        
        # [NEW] Extended Strategy Params
        s['amplitude']['min'] = self.spin_amplitude_min.value()
        s['consecutive_up']['bars'] = int(self.spin_consec_bars.value())
        
        # [NEW] Log state
        if hasattr(self, 'cb_log'):
            self.detector.enable_log = self.cb_log.isChecked()
            
        # [FIX] 防抖3秒后再统一刷新，避免连续加减卡顿
        if not hasattr(self, '_strategy_debounce_timer'):
            self._strategy_debounce_timer = QTimer(self)
            self._strategy_debounce_timer.setSingleShot(True)
            self._strategy_debounce_timer.timeout.connect(self._apply_strategy_and_refresh)
        
        # 重新启动计时器 (3000ms延时)
        self._strategy_debounce_timer.start(3000)

    def _apply_strategy_and_refresh(self):
        self.manual_refresh()
        if self.sector_table.currentRow() >= 0:
             self._on_sector_table_selection_changed()

    # ------------------------------------------------------------------ window state
    def _restore_geometry(self):
        """[NEW] 从 window_config.json 恢复 UI 布局 (弃用注册表)避色 HKEY_CURRENT_USER 污染"""
        try:
            if not os.path.exists(WINDOW_CONFIG_FILE):
                return
            
            with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            p_data = config.get(SETTINGS_SECTION, {})
            if not isinstance(p_data, dict) or not p_data:
                return

            # Helper: Hex string -> QByteArray
            def to_qba(hex_str: Any) -> Optional[QByteArray]:
                if not isinstance(hex_str, str) or not hex_str:
                    return None
                return QByteArray.fromHex(hex_str.encode('ascii'))

            # 恢复窗口几何形状
            geom_hex = p_data.get("geometry")
            q_geom = to_qba(geom_hex)
            if q_geom:
                self.restoreGeometry(q_geom)
            
            # 恢复分割条状态
            if hasattr(self, 'splitter') and self.splitter:
                s_state_hex = p_data.get("splitter_state")
                q_s_state = to_qba(s_state_hex)
                if q_s_state:
                    self.splitter.restoreState(q_s_state)
            
            if hasattr(self, 'v_splitter') and self.v_splitter:
                vs_state_hex = p_data.get("v_splitter_state")
                q_vs_state = to_qba(vs_state_hex)
                if q_vs_state:
                    self.v_splitter.restoreState(q_vs_state)
            
            # [NEW] 恢复业务参数
            try:
                if "score_threshold" in p_data:
                    self.spin_score_threshold.setValue(p_data["score_threshold"])
                if "pct_min" in p_data:
                    self.spin_pct_min.setValue(p_data["pct_min"])
                if "pct_max" in p_data:
                    self.spin_pct_max.setValue(p_data["pct_max"])
                if "vol_ratio" in p_data:
                    self.spin_vol_ratio.setValue(p_data["vol_ratio"])
                if "comparison_interval_min" in p_data:
                    ival = p_data["comparison_interval_min"]
                    self.detector.comparison_interval = ival * 60
                    self.lbl_interval.setText(f"{ival}m")
                
                # 恢复勾选状态
                strat_data = p_data.get("strategies", {})
                if strat_data:
                    self.cb_new_high.setChecked(strat_data.get('new_high', True))
                    self.cb_ma_rebound.setChecked(strat_data.get('ma_rebound', True))
                    self.cb_surge_vol.setChecked(strat_data.get('surge_vol', True))
                    self.cb_consec.setChecked(strat_data.get('consecutive_up', True))
                
                if "cb_log" in p_data:
                    self.cb_log.setChecked(p_data["cb_log"])

                # [NEW] 补充缺失的持久化参数
                if "sector_min_score" in p_data:
                    self.spin_sector_min_score.setValue(p_data["sector_min_score"])
                if "amplitude_min" in p_data:
                    self.spin_amplitude_min.setValue(p_data["amplitude_min"])
                if "consec_bars" in p_data:
                    self.spin_consec_bars.setValue(p_data["consec_bars"])
                if "sector_score_threshold" in p_data:
                    # 优先使用 spin_sector_score_threshold
                    self.spin_sector_score_threshold.setValue(p_data["sector_score_threshold"])

                # 同步到 detector
                self._on_strategy_changed()
            except Exception as e:
                logger.warning(f"Error restoring business settings: {e}")
                
            logger.info(f"♻️ [UI] 布局已从 {os.path.basename(WINDOW_CONFIG_FILE)} 恢复")
        except Exception as e:
            logger.warning(f"⚠️ [UI] 恢复布局失败: {e}")

    def _save_geometry(self):
        """[NEW] 将 UI 布局保存至 window_config.json (弃用注册表)"""
        try:
            config: dict[str, Any] = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                try:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            config = data
                except Exception:
                    pass
            
            # Helper: QByteArray -> Hex string
            def to_hex(qba: QByteArray) -> str:
                # QByteArray.toHex() returns another QByteArray in PyQt6.
                # Convert to bytes then decode.
                return bytes(qba.toHex().data()).decode('ascii')

            p_data = config.get(SETTINGS_SECTION, {})
            if not isinstance(p_data, dict):
                p_data = {}
                
            p_data["geometry"] = to_hex(self.saveGeometry())
            p_data["splitter_state"] = to_hex(self.splitter.saveState())
            p_data["v_splitter_state"] = to_hex(self.v_splitter.saveState())
            
            # [NEW] 持久化所有过滤设置
            p_data["score_threshold"] = self.spin_score_threshold.value()
            p_data["sector_score_threshold"] = self.spin_sector_score_threshold.value()
            p_data["sector_min_score"] = self.spin_sector_min_score.value()
            p_data["amplitude_min"] = self.spin_amplitude_min.value()
            p_data["consec_bars"] = self.spin_consec_bars.value()
            
            p_data["pct_min"] = self.spin_pct_min.value()
            p_data["pct_max"] = self.spin_pct_max.value()
            p_data["vol_ratio"] = self.spin_vol_ratio.value()
            p_data["comparison_interval_min"] = int(self.detector.comparison_interval / 60)
            
            # 策略勾选状态
            p_data["strategies"] = {
                k: v.get('enabled', False) for k, v in self.detector.strategies.items()
            }
            p_data["cb_log"] = self.cb_log.isChecked()
            
            p_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            config[SETTINGS_SECTION] = p_data
            
            with open(WINDOW_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 [UI] 布局已同步至 {os.path.basename(WINDOW_CONFIG_FILE)}")
        except Exception as e:
            logger.error(f"❌ [UI] 保存布局失败: {e}")

    def _on_history_load_clicked(self):
        """弹出【增强型日历】选择框加载历史快照"""
        dialog = SnapshotCalendarDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            file_path = dialog.selected_file
            if file_path and self.detector.load_from_snapshot(file_path):
                self._is_history_mode = True
                self.detector.in_history_mode = True
                # 从文件名尝试提取日期 bidding_20260312.json.gz
                match = re.search(r'bidding_(\d+)', os.path.basename(file_path))
                self._history_date = match.group(1) if match else "Unknown"
                
                # 更新 UI 状态
                self.btn_live.setVisible(True)
                self.btn_history.setStyleSheet("background-color: #4a3a2a; color: #ff9900; border: 1px solid #ff9900;")
                self.btn_refresh.setEnabled(False) # 历史模式下不能“刷新”实时数据
                
                # 触发一次 UI 刷新
                self._refresh_sector_list()
                self._populate_watchlist()
                
                if hasattr(self, 'status_lbl'):
                    self.status_lbl.setText(f"🎬 [历史复盘] 📅 {self._history_date} | 快照已就绪")
                    self.status_lbl.setStyleSheet("color: #ff9900; font-weight: bold;")
                
                # [NEW] 同步更新窗口标题，防止被搜索信息覆盖
                self.setWindowTitle(f"🎞️ [历史复盘] {self._history_date} | 竞价及联动监控")
                    
                # 触发重点表标题刷新
                self._populate_watchlist()
            else:
                if dialog.selected_file:
                    QMessageBox.warning(self, "加载失败", "无法读取该快照文件，可能已损坏或格式不正确。")

    def _on_history_track_clicked(self):
        """[NEW] 自动选择最近几日的快照进行强势股追踪分析"""
        snapshots_dir = os.path.join(cct.get_base_path(), "snapshots")
        if not os.path.exists(snapshots_dir):
            os.makedirs(snapshots_dir, exist_ok=True)
            
        # 自动获取所有快照文件
        all_snaps = [os.path.join(snapshots_dir, f) for f in os.listdir(snapshots_dir) if f.startswith('bidding_') and f.endswith('.json.gz')]
        all_snaps.sort(reverse=True) # 最近的在前
        
        # 剔除过于小的文件（可能是损坏的）
        valid_snaps = [s for s in all_snaps if os.path.getsize(s) > 10240]
        
        if not valid_snaps:
            QMessageBox.information(self, "未找到数据", "snapshots/ 目录下未找到有效的历史快照文件。")
            return
            
        rs = getattr(self.main_window, 'realtime_service', None)
        # 传入所有快照，供 Dialog 自由选择
        # [FIX] 存储引用并同步状态
        self._hist_tracker_dialog = HistoricalTrackerDialog(valid_snaps, rs, self)
        self._hist_tracker_dialog.show()


    def _on_back_to_live_clicked(self):
        """切回实时模式"""
        self._is_history_mode = False
        self.detector.in_history_mode = False
        self.btn_live.setVisible(False)
        self.btn_history.setStyleSheet("")
        self.btn_refresh.setEnabled(True)
        
        # 恢复锚点并尝试冷启一次数据
        self.detector.reset_observation_anchors()
        self.manual_refresh()
        
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText("📡 已切回实时监控模式")
            self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")
        
        # [NEW] 恢复默认窗口标题
        self.setWindowTitle("🚀 竞价/尾盘板块联动监控 (Tick 订阅)")
            
        # 触发重点表标题刷新
        self._populate_watchlist()

    def _locate_sector(self, sector_name: str):
        """在左侧板块表中找到并滚动到指定的板块"""
        if not sector_name: return
        for i in range(self.sector_table.rowCount()):
            item = self.sector_table.item(i, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == sector_name:
                self.sector_table.selectRow(i)
                self.sector_table.scrollToItem(item, QTableWidget.ScrollHint.PositionAtCenter)
                # 触发联动刷新右侧表
                self._on_sector_table_selection_changed()
                break

    # ------------------------------------------------------------------ misc
    @staticmethod
    def _session_str() -> str:
        n = datetime.now()
        hm = n.hour * 100 + n.minute
        if 915 <= hm <= 945:
            return "集合竞价"
        if 1430 <= hm <= 1500:
            return "尾盘异动"
        return "盘中监控"

    def _on_rearrange_clicked(self):
        """Trigger global window tiling."""
        try:
            try:
                from .qt_window_utils import tile_all_windows
            except (ImportError, ValueError):
                from qt_window_utils import tile_all_windows
            tile_all_windows()
        except Exception as e:
            logger.error(f"Rearrange error: {e}")


    # ── [NEW] Context Menu Handlers ──────────────────────────────
    def _on_sector_context_menu(self, pos):
        """板块列表右键菜单"""
        item = self.sector_table.itemAt(pos)
        if item is None:
            return
            
        row = self.sector_table.row(item)
        sector_name = self.sector_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: #2a2a3e; color: #aad4ff; border: 1px solid #4a4a6e; } QMenu::item:selected { background-color: #3e3e5e; }")
        
        act_reconstruct = menu.addAction("🛠️ 手工重建跟随股 (针对旧快照)")
        act_reconstruct.triggered.connect(lambda: self._handle_reconstruct_followers(sector_name))
        
        menu.exec(self.sector_table.viewport().mapToGlobal(pos))
        
    def _handle_reconstruct_followers(self, sector_name):
        """调用 detector 重建跟随股并刷新 UI"""
        self.detector.reconstruct_followers(sector_name)
        # 刷新板块列表（内部会重新填充）
        self._refresh_sector_list()
        
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"✅ 板块 [{sector_name}] 跟随股已智能找回")
            self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    # 配置基础日志
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # 简单的 MockMainWindow 以满足初始化需求
    class MockMainWindow:
        def __init__(self):
            self.realtime_service = None
    app = QApplication(sys.argv)
    
    # 尝试设置美观的暗色风格 (如果系统支持)
    app.setStyle('Fusion')
    
    mock_win = MockMainWindow()
    window = SectorBiddingPanel(main_window=mock_win, allow_real_close=True)
    window.show()
    
    sys.exit(app.exec())
