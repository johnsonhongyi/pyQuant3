# -*- coding: utf-8 -*-
"""
ATS Global Market K-Line Viewer Dialog
独立极速外盘资产 (美股7巨头/存储芯片/A50/原油黄金) 近 120 日 K 线与 OHLC 走势查看器
采用 TradingView 极简 Pro 暗黑交易画板设计，支持异步无卡顿后台加载、格式化 DateAxis/VolumeAxis、
支持 🕯️ 蜡烛图 (Candlestick) 与 📊 竹节线 (OHLC) 双模式平滑切换、
MA5/MA20/MA60 动态均线、成交量 Subplot 柱状图、十字光标与磁盘 JSON 物理持久化
"""

import json
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPicture, QPainter, QPen, QBrush

import pyqtgraph as pg
from JSONData.global_market_data import fetch_global_kline_history, get_kline_cache_file_path
from sys_utils import get_app_root, get_conf_path
from ats.ui.styles import CONFIG_FILE_LOCK


class KLineWorkerThread(QThread):
    """后台非阻塞异步 K 线抓取线程，彻底解决 UI 界面调起卡顿问题"""
    finished_signal = pyqtSignal(list, str)  # klines, error_msg

    def __init__(self, symbol: str, force_refresh: bool = False):
        super().__init__()
        self.symbol = symbol
        self.force_refresh = force_refresh

    def run(self):
        try:
            klines = fetch_global_kline_history(self.symbol, limit=120, force_refresh=self.force_refresh)
            self.finished_signal.emit(klines or [], "")
        except Exception as e:
            self.finished_signal.emit([], str(e))


class DateAxisItem(pg.AxisItem):
    """自定义 X 轴日期刻度格式化类 (将索引转换为 06/29 精简日期)"""

    def __init__(self, dates=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dates = dates or []

    def set_dates(self, dates):
        self.dates = dates

    def tickStrings(self, values, scale, spacing):
        strings = []
        n = len(self.dates)
        for v in values:
            idx = int(round(v))
            if 0 <= idx < n:
                dt_str = str(self.dates[idx])
                if len(dt_str) >= 10:
                    strings.append(dt_str[5:].replace('-', '/'))
                else:
                    strings.append(dt_str)
            else:
                strings.append('')
        return strings


class VolumeAxisItem(pg.AxisItem):
    """自定义 Y 轴成交量格式化类 (转换为 万/亿 简洁中文单位)"""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            abs_v = abs(v)
            if abs_v >= 1e8:
                strings.append(f"{v / 1e8:.2f}亿")
            elif abs_v >= 1e4:
                strings.append(f"{int(v / 1e4)}万")
            elif abs_v == 0:
                strings.append("0")
            else:
                strings.append(f"{int(v)}")
        return strings


class CandlestickItem(pg.GraphicsObject):
    """TradingView Pro 级 Candlestick K 线抗锯齿精准绘制组件"""

    def __init__(self, data):
        super().__init__()
        self.data = data  # list of tuples: (i, open, close, low, high)
        self.picture = QPicture()
        self.generate_picture()

    def generate_picture(self):
        p = QPainter(self.picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 国际/国内大厂高辨识度配色: 阳线 #F6465D (珊瑚红), 阴线 #089981 (青绿)
        color_up = QColor("#F6465D")
        color_down = QColor("#089981")

        pen_up = QPen(color_up, 1.0)
        pen_up.setCosmetic(True)  # 核心点：设为 cosmetic 避免屏幕放大缩小导致线宽为坐标轴 1.0 单位的肥厚块！

        pen_down = QPen(color_down, 1.0)
        pen_down.setCosmetic(True)

        brush_up = QBrush(color_up)
        brush_down = QBrush(color_down)

        w = 0.30
        for (i, open_p, close_p, low_p, high_p) in self.data:
            is_up = close_p >= open_p
            p.setPen(pen_up if is_up else pen_down)
            p.setBrush(brush_up if is_up else brush_down)

            # 1. 绘制上下影线 (1px 极细精美线条)
            p.drawLine(QPointF(i, low_p), QPointF(i, high_p))

            # 2. 绘制实体蜡烛 (标准 pyqtgraph QRectF 区域填充)
            top_p = max(open_p, close_p)
            bottom_p = min(open_p, close_p)
            h = top_p - bottom_p

            if h < 0.01:
                # 平盘/十字星: 绘制横线
                p.drawLine(QPointF(i - w, open_p), QPointF(i + w, open_p))
            else:
                p.drawRect(QRectF(i - w, bottom_p, w * 2, h))

        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


class OHLCItem(pg.GraphicsObject):
    """标准专业 OHLC (Open-High-Low-Close) 竹节线 / 美国线绘制组件"""

    def __init__(self, data):
        super().__init__()
        self.data = data  # list of tuples: (i, open, close, low, high)
        self.picture = QPicture()
        self.generate_picture()

    def generate_picture(self):
        p = QPainter(self.picture)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        color_up = QColor("#F6465D")
        color_down = QColor("#089981")

        pen_up = QPen(color_up, 1.5)
        pen_up.setCosmetic(True)

        pen_down = QPen(color_down, 1.5)
        pen_down.setCosmetic(True)

        w = 0.32
        for (i, open_p, close_p, low_p, high_p) in self.data:
            p.setPen(pen_up if close_p >= open_p else pen_down)

            # 1. 绘制 High-Low 主干竖线
            p.drawLine(QPointF(i, low_p), QPointF(i, high_p))

            # 2. 绘制左侧 Open 横线 (开盘价)
            p.drawLine(QPointF(i - w, open_p), QPointF(i, open_p))

            # 3. 绘制右侧 Close 横线 (收盘价)
            p.drawLine(QPointF(i, close_p), QPointF(i + w, close_p))

        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


class GlobalMarketKLineDialog(QDialog):
    """外盘资产 120 日 K 线 / OHLC 走势弹窗 (TradingView 风格极简暗黑画板)"""

    def __init__(self, symbol: str, name: str = "", parent=None):
        super().__init__(parent)
        self.symbol = symbol.strip().upper()
        self.name = name or self.symbol
        self.klines = []
        self.worker = None
        self.chart_mode = 'candlestick'  # 'candlestick' 或 'ohlc'
        self.show_boll = True  # 布林线 BOLL 显示开关

        self.setWindowTitle(f"📈 [{self.symbol} · {self.name}] 近 120 日外盘 K 线走势图")
        self.resize(920, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #131722;
                color: #d1d4dc;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QLabel {
                color: #d1d4dc;
            }
        """)

        self._init_ui()
        self._load_fast_cached_or_async()
        self._restore_geometry()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ---------------- 1. 顶部 Header 控件 ----------------
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1e222d;
                border: 1px solid #2a2e39;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(10, 6, 10, 6)

        self.lbl_title = QLabel(f"🌐 {self.name} ({self.symbol})")
        self.lbl_title.setStyleSheet("font-weight: bold; color: #00F0FF; font-size: 13pt;")
        header_layout.addWidget(self.lbl_title)

        self.lbl_price_info = QLabel("最新价: -- | 涨跌: --")
        self.lbl_price_info.setStyleSheet("font-size: 11pt; font-weight: bold; margin-left: 15px;")
        header_layout.addWidget(self.lbl_price_info)

        header_layout.addStretch()

        # BOLL 线开关按键
        self.btn_boll_toggle = QPushButton("📈 BOLL(20,2): 开")
        self.btn_boll_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_boll_toggle.setStyleSheet("""
            QPushButton {
                background-color: #262b3e;
                color: #FF2A6D;
                border: 1px solid #FF2A6D;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #363c56;
            }
        """)
        self.btn_boll_toggle.clicked.connect(self._toggle_boll)
        header_layout.addWidget(self.btn_boll_toggle)

        # K线 / OHLC 模式切换按键
        self.btn_mode_toggle = QPushButton("📊 切换 OHLC(美国线)")
        self.btn_mode_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_toggle.setStyleSheet("""
            QPushButton {
                background-color: #2962ff;
                color: #ffffff;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1e54b7;
            }
        """)
        self.btn_mode_toggle.clicked.connect(self._toggle_chart_mode)
        header_layout.addWidget(self.btn_mode_toggle)

        # 视区快捷控制组
        btn_focus_60 = QPushButton("🔍 最新60日")
        btn_focus_60.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_focus_60.setStyleSheet("""
            QPushButton {
                background-color: #2a2e39;
                color: #d1d4dc;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #363c4e;
                color: #ffffff;
            }
        """)
        btn_focus_60.clicked.connect(self._focus_recent_60)
        header_layout.addWidget(btn_focus_60)

        btn_focus_120 = QPushButton("🌐 120日全览")
        btn_focus_120.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_focus_120.setStyleSheet("""
            QPushButton {
                background-color: #2a2e39;
                color: #d1d4dc;
                border: 1px solid #363c4e;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #363c4e;
                color: #ffffff;
            }
        """)
        btn_focus_120.clicked.connect(self._focus_full_120)
        header_layout.addWidget(btn_focus_120)

        layout.addWidget(header_frame)

        # ---------------- 2. 动态信息条 (Info Banner) ----------------
        self.lbl_info = QLabel("提示: 鼠标悬浮移入画板查看开高低收明细与指标数据")
        self.lbl_info.setStyleSheet("""
            QLabel {
                background-color: #181c27;
                border: 1px solid #232733;
                border-radius: 4px;
                padding: 4px 10px;
                color: #9db2c6;
                font-size: 9.5pt;
            }
        """)
        layout.addWidget(self.lbl_info)

        # ---------------- 3. pyqtgraph 图表区域 ----------------
        self.graphics_widget = pg.GraphicsLayoutWidget()
        self.graphics_widget.setBackground('#131722')

        # 构建自定义 DateAxis 与 VolumeAxis
        self.date_axis = DateAxisItem(orientation='bottom')
        self.date_axis.setPen(pg.mkPen('#363c4e'))
        self.date_axis.setTextPen(pg.mkPen('#787b86'))

        self.vol_axis = VolumeAxisItem(orientation='left')
        self.vol_axis.setPen(pg.mkPen('#363c4e'))
        self.vol_axis.setTextPen(pg.mkPen('#787b86'))

        # 3.1 主 K 线 Plot (row 0)
        self.p_kline = self.graphics_widget.addPlot(row=0, col=0, axisItems={'bottom': self.date_axis})
        self.p_kline.showGrid(x=True, y=True, alpha=0.18)
        self.p_kline.getAxis('left').setPen(pg.mkPen('#363c4e'))
        self.p_kline.getAxis('left').setTextPen(pg.mkPen('#787b86'))
        self.p_kline.hideButtons()  # 隐藏左下角丑陋的 'A' 标按键

        # 3.2 成交量 Subplot (row 1)
        self.p_vol = self.graphics_widget.addPlot(row=1, col=0, axisItems={'left': self.vol_axis, 'bottom': DateAxisItem(orientation='bottom')})
        self.p_vol.showGrid(x=True, y=True, alpha=0.18)
        self.p_vol.setMaximumHeight(125)
        self.p_vol.getAxis('bottom').setPen(pg.mkPen('#363c4e'))
        self.p_vol.getAxis('bottom').setTextPen(pg.mkPen('#787b86'))
        self.p_vol.hideButtons()
        self.p_vol.setXLink(self.p_kline)

        layout.addWidget(self.graphics_widget)

        # 十字光标 Crosshair
        self.v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DashLine, width=1))
        self.h_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('#787b86', style=Qt.PenStyle.DashLine, width=1))
        self.p_kline.addItem(self.v_line, ignoreBounds=True)
        self.p_kline.addItem(self.h_line, ignoreBounds=True)

        self.proxy = pg.SignalProxy(self.p_kline.scene().sigMouseMoved, rateLimit=60, slot=self._on_mouse_moved)

    def _toggle_boll(self):
        """切换 BOLL 布林线显示状态"""
        self.show_boll = not self.show_boll
        if self.show_boll:
            self.btn_boll_toggle.setText("📈 BOLL(20,2): 开")
            self.btn_boll_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #262b3e;
                    color: #FF2A6D;
                    border: 1px solid #FF2A6D;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 9pt;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #363c56;
                }
            """)
        else:
            self.btn_boll_toggle.setText("📈 BOLL(20,2): 关")
            self.btn_boll_toggle.setStyleSheet("""
                QPushButton {
                    background-color: #1e222d;
                    color: #787b86;
                    border: 1px solid #363c4e;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 9pt;
                }
                QPushButton:hover {
                    background-color: #2a2e39;
                    color: #d1d4dc;
                }
            """)
        self._draw_chart()

    def _toggle_chart_mode(self):
        """切换 🕯️ 蜡烛图 (Candlestick) 与 📊 竹节线 (OHLC)"""
        if self.chart_mode == 'candlestick':
            self.chart_mode = 'ohlc'
            self.btn_mode_toggle.setText("🕯️ 切换 蜡烛图(K线)")
        else:
            self.chart_mode = 'candlestick'
            self.btn_mode_toggle.setText("📊 切换 OHLC(美国线)")
        self._draw_chart()

    def _load_fast_cached_or_async(self):
        """0 毫秒极速读取本地 JSON 缓存；若无缓存则触发后台异步线程"""
        cache_path = get_kline_cache_file_path()
        print(f"[GlobalMarketKLineDialog] 检查外盘 K线物理持久化文件路径: {cache_path}")
        cached_klines = []
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                    cached_klines = all_data.get(self.symbol, [])
            except Exception as ex:
                print(f"[GlobalMarketKLineDialog] 读取本地 K线缓存文件异常: {ex}")
                cached_klines = []

        if cached_klines and len(cached_klines) >= 5:
            # 本地有缓存，瞬间秒载渲染，无任何卡顿！
            print(f"[GlobalMarketKLineDialog] 0ms 瞬间秒载本地 K线缓存 ({len(cached_klines)} 条) -> {self.symbol}")
            self.klines = cached_klines
            self._draw_chart()
            self._focus_recent_60()

        # 后台异步抓取最新或静默刷新
        self._trigger_async_load(force_refresh=False if (cached_klines and len(cached_klines) >= 5) else True)

    def _trigger_async_load(self, force_refresh: bool = False):
        if self.worker and self.worker.isRunning():
            return

        if not self.klines:
            self.lbl_info.setText("🌐 正在后台异步加载最新外盘 K 线数据...")

        self.worker = KLineWorkerThread(self.symbol, force_refresh=force_refresh)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self, klines: list, err_msg: str):
        cache_path = get_kline_cache_file_path()
        if klines and len(klines) >= 5:
            self.klines = klines
            print(f"[GlobalMarketKLineDialog] K线数据加载完成 ({len(klines)} 条)，物理文件: {cache_path}")
            self._draw_chart()
            self._focus_recent_60()
        elif not self.klines:
            print(f"[GlobalMarketKLineDialog] K线数据加载失败: {err_msg} | 持久化路径: {cache_path}")
            self.lbl_info.setText(f"❌ K 线数据加载失败: {err_msg or '网络或解析异常'}")

    def _draw_chart(self):
        self.p_kline.clear()
        self.p_vol.clear()

        # 重新置入 Crosshair
        self.p_kline.addItem(self.v_line, ignoreBounds=True)
        self.p_kline.addItem(self.h_line, ignoreBounds=True)

        n = len(self.klines)
        if n == 0:
            return

        dates = [item['date'] for item in self.klines]
        opens = [float(item['open']) for item in self.klines]
        closes = [float(item['close']) for item in self.klines]
        lows = [float(item['low']) for item in self.klines]
        highs = [float(item['high']) for item in self.klines]
        vols = [float(item.get('volume', 0)) for item in self.klines]

        # 刷新日期 Axis
        self.date_axis.set_dates(dates)

        # 最新价与涨跌幅 Header 控件更新
        last_item = self.klines[-1]
        last_c = float(last_item['close'])
        last_pct = float(last_item['pct'])
        color_str = "#F6465D" if last_pct >= 0 else "#089981"
        self.lbl_price_info.setText(
            f"最新价: <font color='{color_str}'>{last_c:.2f}</font> | "
            f"涨跌: <font color='{color_str}'>{last_pct:+.2f}%</font>"
        )

        # 1. 绘制 Pro 级 蜡烛图 (Candlestick) 或 竹节线 (OHLC)
        candle_data = [(i, opens[i], closes[i], lows[i], highs[i]) for i in range(n)]
        if self.chart_mode == 'ohlc':
            chart_item = OHLCItem(candle_data)
        else:
            chart_item = CandlestickItem(candle_data)
        self.p_kline.addItem(chart_item)

        # 2. 计算均线 MA5 / MA20 / MA60 与 BOLL 布林线
        def calc_ma(period):
            ma = []
            for i in range(n):
                if i < period - 1:
                    ma.append(None)
                else:
                    sub = closes[i - period + 1: i + 1]
                    ma.append(sum(sub) / len(sub))
            return ma

        def calc_std(period, ma_list):
            std_list = []
            for i in range(n):
                if i < period - 1 or ma_list[i] is None:
                    std_list.append(None)
                else:
                    sub = closes[i - period + 1: i + 1]
                    m = ma_list[i]
                    variance = sum((x - m) ** 2 for x in sub) / len(sub)
                    std_list.append(variance ** 0.5)
            return std_list

        self.ma5 = calc_ma(5)
        self.ma20 = calc_ma(20)
        self.ma60 = calc_ma(60)

        # 计算 BOLL 布林线 (20, 2)
        std20 = calc_std(20, self.ma20)
        self.boll_upper = [self.ma20[i] + 2 * std20[i] if (self.ma20[i] is not None and std20[i] is not None) else None for i in range(n)]
        self.boll_lower = [self.ma20[i] - 2 * std20[i] if (self.ma20[i] is not None and std20[i] is not None) else None for i in range(n)]

        x_indices = list(range(n))

        # 绘制均线
        valid_ma5_x = [x_indices[i] for i in range(n) if self.ma5[i] is not None]
        valid_ma5_y = [self.ma5[i] for i in range(n) if self.ma5[i] is not None]
        self.p_kline.plot(valid_ma5_x, valid_ma5_y, pen=pg.mkPen('#f0b90b', width=1.5), name="MA5")

        valid_ma20_x = [x_indices[i] for i in range(n) if self.ma20[i] is not None]
        valid_ma20_y = [self.ma20[i] for i in range(n) if self.ma20[i] is not None]
        self.p_kline.plot(valid_ma20_x, valid_ma20_y, pen=pg.mkPen('#00F0FF', width=1.5), name="MA20")

        valid_ma60_x = [x_indices[i] for i in range(n) if self.ma60[i] is not None]
        valid_ma60_y = [self.ma60[i] for i in range(n) if self.ma60[i] is not None]
        self.p_kline.plot(valid_ma60_x, valid_ma60_y, pen=pg.mkPen('#e040fb', width=1.5), name="MA60")

        # 绘制 BOLL 布林线上轨与下轨
        if self.show_boll:
            valid_up_x = [x_indices[i] for i in range(n) if self.boll_upper[i] is not None]
            valid_up_y = [self.boll_upper[i] for i in range(n) if self.boll_upper[i] is not None]
            self.p_kline.plot(valid_up_x, valid_up_y, pen=pg.mkPen('#FF2A6D', width=1.4, style=Qt.PenStyle.DashLine), name="BOLL_UPPER")

            valid_dn_x = [x_indices[i] for i in range(n) if self.boll_lower[i] is not None]
            valid_dn_y = [self.boll_lower[i] for i in range(n) if self.boll_lower[i] is not None]
            self.p_kline.plot(valid_dn_x, valid_dn_y, pen=pg.mkPen('#00E5FF', width=1.4, style=Qt.PenStyle.DashLine), name="BOLL_LOWER")

        # 3. 绘制成交量柱状图
        vol_bars_up_x, vol_bars_up_y = [], []
        vol_bars_down_x, vol_bars_down_y = [], []

        for i in range(n):
            if closes[i] >= opens[i]:
                vol_bars_up_x.append(i)
                vol_bars_up_y.append(vols[i])
            else:
                vol_bars_down_x.append(i)
                vol_bars_down_y.append(vols[i])

        bg_up = pg.BarGraphItem(x=vol_bars_up_x, height=vol_bars_up_y, width=0.65, brush='#F6465D', pen='#F6465D')
        bg_down = pg.BarGraphItem(x=vol_bars_down_x, height=vol_bars_down_y, width=0.65, brush='#089981', pen='#089981')
        self.p_vol.addItem(bg_up)
        self.p_vol.addItem(bg_down)

        self._update_info_banner(n - 1)

    def _focus_recent_60(self):
        """缩放聚焦至最右侧最新 60 日"""
        n = len(self.klines)
        if n > 0:
            start_x = max(0, n - 60)
            self.p_kline.setXRange(start_x, n, padding=0.02)

    def _focus_full_120(self):
        """全览近 120 日完整 K 线"""
        n = len(self.klines)
        if n > 0:
            self.p_kline.setXRange(0, n, padding=0.02)

    def _update_info_banner(self, idx: int):
        """更新顶部动态数据信息条"""
        if not self.klines or not (0 <= idx < len(self.klines)):
            return

        item = self.klines[idx]
        dt = item['date']
        o = float(item['open'])
        h = float(item['high'])
        l = float(item['low'])
        c = float(item['close'])
        pct = float(item['pct'])
        v = float(item.get('volume', 0))

        c_color = "#F6465D" if pct >= 0 else "#089981"
        v_str = f"{v/1e8:.2f}亿" if v >= 1e8 else (f"{v/1e4:.1f}万" if v >= 1e4 else f"{int(v)}")

        ma5_str = f"{self.ma5[idx]:.2f}" if hasattr(self, 'ma5') and self.ma5[idx] else "--"
        ma20_str = f"{self.ma20[idx]:.2f}" if hasattr(self, 'ma20') and self.ma20[idx] else "--"
        ma60_str = f"{self.ma60[idx]:.2f}" if hasattr(self, 'ma60') and self.ma60[idx] else "--"

        boll_up_str = f"{self.boll_upper[idx]:.2f}" if hasattr(self, 'boll_upper') and self.boll_upper[idx] else "--"
        boll_dn_str = f"{self.boll_lower[idx]:.2f}" if hasattr(self, 'boll_lower') and self.boll_lower[idx] else "--"

        mode_name = "📊 OHLC美国线" if self.chart_mode == 'ohlc' else "🕯️ K线蜡烛图"
        boll_info = f" | <font color='#FF2A6D'>BOLL上轨 {boll_up_str}</font> · <font color='#00E5FF'>下轨 {boll_dn_str}</font>" if self.show_boll else ""

        self.lbl_info.setText(
            f"模式: <b>{mode_name}</b> | 日期: <b>{dt}</b> | 开: {o:.2f} | 高: {h:.2f} | 低: {l:.2f} | "
            f"收: <font color='{c_color}'><b>{c:.2f}</b></font> ({pct:+.2f}%) | 量: {v_str} | "
            f"均线: <font color='#f0b90b'>MA5 {ma5_str}</font> · <font color='#00F0FF'>MA20 {ma20_str}</font> · <font color='#e040fb'>MA60 {ma60_str}</font>"
            f"{boll_info}"
        )

    def _on_mouse_moved(self, evt):
        """鼠标悬浮十字光标穿透交互"""
        pos = evt[0]
        if self.p_kline.sceneBoundingRect().contains(pos):
            mouse_point = self.p_kline.vb.mapSceneToView(pos)
            x_idx = int(round(mouse_point.x()))
            if 0 <= x_idx < len(self.klines):
                self.v_line.setPos(mouse_point.x())
                self.h_line.setPos(mouse_point.y())
                self._update_info_banner(x_idx)

    def _restore_geometry(self):
        """恢复物理窗口几何尺寸与位置"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                geom = data.get("ats_global_kline_dialog_geom")
                if geom:
                    from PyQt6.QtCore import QByteArray
                    self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
                mode = data.get("ats_global_kline_dialog_mode")
                if mode in ['candlestick', 'ohlc']:
                    self.chart_mode = mode
                    if mode == 'ohlc':
                        self.btn_mode_toggle.setText("🕯️ 切换 蜡烛图(K线)")
        except Exception:
            pass

    def closeEvent(self, event):
        """关闭事件，自动保存几何尺寸"""
        try:
            cfg_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(cfg_path):
                    try:
                        with open(cfg_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                data["ats_global_kline_dialog_geom"] = self.saveGeometry().toHex().data().decode('utf-8')
                data["ats_global_kline_dialog_mode"] = self.chart_mode
                tmp_path = cfg_path + ".tmp_gkline"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, cfg_path)
        except Exception:
            pass
        super().closeEvent(event)
