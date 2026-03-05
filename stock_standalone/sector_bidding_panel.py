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
    QDoubleSpinBox, QSplitter, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QGroupBox, QToolBar, QSizePolicy, QPushButton, QFrame,
    QStyledItemDelegate, QStyleOptionViewItem, QDialog
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QSize, QPoint, QRect
from PyQt6.QtGui import QColor, QFont, QAction, QPen, QPainter
import pyqtgraph as pg

from tk_gui_modules.window_mixin import WindowMixin
from bidding_momentum_detector import BiddingMomentumDetector
from JohnsonUtil import commonTips as cct
import time

logger = logging.getLogger(__name__)

SETTINGS_KEY = "SectorBiddingPanel"


def _ascii_kline(klines: List[dict], width: int = 24) -> str:
    """最近 N 根分钟 K 线 → 文字条形迷你图"""
    if not klines:
        return "─" * width
    closes = [float(k.get('close', 0)) for k in klines[-width:]]
    if not closes:
        return "─" * width
    mn, mx = min(closes), max(closes)
    if mx == mn:
        return "─" * len(closes)
    bars = '▁▂▃▅▇'
    return ''.join(bars[min(4, int((c - mn) / (mx - mn) * 4.99))] for c in closes)


class TrendDelegate(QStyledItemDelegate):
    """自定义委派：在单元格内绘制图形化分时走势和均价线"""
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        pdata = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(pdata, dict) or 'prices' not in pdata:
            super().paint(painter, option, index)
            return

        prices = pdata['prices']
        last_close = pdata.get('last_close', 0)
        
        if not prices or len(prices) < 2:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        margin_h, margin_v = 4, 4
        draw_rect = rect.adjusted(margin_h, margin_v, -margin_h, -margin_v)
        
        p_min, p_max = min(prices), max(prices)
        if last_close > 0:
            p_min = min(p_min, last_close)
            p_max = max(p_max, last_close)
        
        p_avg = sum(prices) / len(prices)
        rng = p_max - p_min if p_max > p_min else 1.0
        
        def to_y(p):
            return draw_rect.bottom() - (p - p_min) / rng * draw_rect.height()

        # 1. 绘制昨收基准线 (蓝色)
        if last_close > 0:
            y_lc = to_y(last_close)
            painter.setPen(QPen(QColor(64, 156, 255), 1, Qt.PenStyle.DotLine))
            painter.drawLine(draw_rect.left(), int(y_lc), draw_rect.right(), int(y_lc))

        # 2. 绘制黄色均价线 (虚线)
        y_avg = to_y(p_avg)
        painter.setPen(QPen(QColor(255, 255, 0), 1, Qt.PenStyle.DashLine))
        painter.drawLine(draw_rect.left(), int(y_avg), draw_rect.right(), int(y_avg))

        # 3. 绘制价格走势线
        pen_price = QPen(QColor(255, 68, 68) if prices[-1] >= (last_close if last_close > 0 else prices[0]) else QColor(68, 255, 68), 1.5)
        painter.setPen(pen_price)
        
        step = draw_rect.width() / (len(prices) - 1)
        for i in range(len(prices) - 1):
            x1 = draw_rect.left() + i * step
            y1 = to_y(prices[i])
            x2 = draw_rect.left() + (i + 1) * step
            y2 = to_y(prices[i + 1])
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
            
        painter.restore()


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


class DetailedChartDialog(QDialog):
    """双击弹出的详细分时图窗口 (带成交量、多重参考线及全量实时数据)"""
    def __init__(self, code, name, klines, meta, parent=None):
        super().__init__(parent)
        
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
        
        if not klines: return
        
        # 提取数据，使用索引作为 X 轴坐标，原始时间戳用于轴标签
        prices = [float(k.get('close', 0)) for k in klines]
        vols = [float(k.get('volume', 0)) for k in klines]
        raw_times = [float(k.get('time', 0)) for k in klines]
        times = list(range(len(prices)))
        
        # 使用自定义时间轴 (传入原始时间序列)
        self.pw = pg.PlotWidget(
            title=f"分时走势与成交量 (样本数:{len(klines)})",
            axisItems={'bottom': TimeAxisItem(ts_list=raw_times, orientation='bottom')}
        )
        self.pw.setBackground('#0d1b2a')
        self.pw.showGrid(x=True, y=True, alpha=0.3)
        lay.addWidget(self.pw)
        
        last_close = meta.get('last_close', 0)
        high_day = meta.get('high_day', 0)
        low_day = meta.get('low_day', 0)
        last_high = meta.get('last_high', 0)
        last_low = meta.get('last_low', 0)

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
        
        # 4. 成交量
        p_min, p_max = min(prices), max(prices)
        # 4. 成交量 (在主图下方叠加，自动缩放)
        if vols:
            p_min, p_max = min(prices), max(prices)
            v_max = max(vols) if vols else 1
            # 占据底部 20% 的空间
            vol_scale = (p_max - p_min) * 0.2 / v_max if p_max > p_min else 0.1
            
            for i in range(len(times)):
                # 颜色：红升绿降
                color = '#FF4444' if i > 0 and prices[i] >= prices[i-1] else '#44CC44'
                # 注意：目前 X 轴是索引 (0,1,2...), width 设为 0.6 即可
                rect = pg.BarGraphItem(x=[times[i]], height=[vols[i] * vol_scale], width=0.6, brush=color, pen=color)
                # 放在底部
                rect.setPos(0, y_min - (y_max - y_min)*0.05) 
                self.pw.addItem(rect)

class SectorBiddingPanel(QWidget, WindowMixin):
    """竞价和尾盘板块联动监控面板 v3"""

    # ------------------------------------------------------------------ init
    def __init__(self, main_window: Any):
        super().__init__(None)         # 独立窗口
        self.main_window = main_window
        rs = getattr(main_window, 'realtime_service', None)
        self.detector = BiddingMomentumDetector(realtime_service=rs)

        # 排序状态：(col_index, ascending)
        self._sort_col = 4             # 默认按涨幅排序
        self._sort_asc = False

        self.setWindowTitle("🚀 竞价/尾盘板块联动监控 (Tick 订阅)")
        self.resize(1100, 680)
        self._restore_geometry()
        self._init_ui()

        # 状态记录
        self._is_populating = False
        self._last_selected_code = None
        self._last_refresh_ts = 0

        # UI 刷新计时器 (保持定义但默认不启动，作为 fallback 或数据中断时的兜底)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_sector_list)
        # self._refresh_timer.start(2000) # [CHANGE] 改为数据驱动

        # 评分聚合计时器
        self._score_timer = QTimer(self)
        self._score_timer.timeout.connect(self.detector.update_scores)
        # self._score_timer.start(5000) # [CHANGE] 改为数据驱动

    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        # ── 紧凑工具栏 ──────────────────────────────────────────────────
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.StyledPanel)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(4, 2, 4, 2)
        bar_lay.setSpacing(6)

        bold = QFont()
        bold.setBold(True)

        # 策略开关
        self.cb_new_high   = self._make_cb("新高",    'new_high',        bar_lay)
        self.cb_ma_rebound = self._make_cb("MA回踩高开", 'ma_rebound',   bar_lay)
        self.cb_surge_vol  = self._make_cb("放量",     'surge_vol',       bar_lay)
        self.cb_consec     = self._make_cb("连续拉升", 'consecutive_up',  bar_lay)

        bar_lay.addWidget(self._sep())

        bar_lay.addWidget(QLabel("放量倍≥"))
        self.spin_vol_ratio = self._make_spin(1.0, 10.0, 0.1,
            self.detector.strategies['surge_vol']['min_ratio'])
        bar_lay.addWidget(self.spin_vol_ratio)

        bar_lay.addWidget(QLabel(" 涨幅%"))
        self.spin_pct_min = self._make_spin(-20, 20, 0.5,
            self.detector.strategies['pct_change']['min'])
        bar_lay.addWidget(self.spin_pct_min)
        bar_lay.addWidget(QLabel("~"))
        self.spin_pct_max = self._make_spin(-20, 20, 0.5,
            self.detector.strategies['pct_change']['max'])
        bar_lay.addWidget(self.spin_pct_max)

        for w in [self.spin_vol_ratio, self.spin_pct_min, self.spin_pct_max]:
            w.valueChanged.connect(self._on_strategy_changed)

        bar_lay.addSpacing(4)
        bar_lay.addWidget(self._sep())

        self.status_lbl = QLabel("等待数据...")
        self.status_lbl.setStyleSheet("color:#FFA500;font-weight:bold;")
        bar_lay.addWidget(self.status_lbl)
        bar_lay.addStretch()

        root.addWidget(bar)

        # ── 主体：Splitter ───────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左：板块排行
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(2)
        lbl_sec = QLabel(" 活跃板块 (双击联动)")
        lbl_sec.setStyleSheet("font-weight:bold;background:#2a2a3e;color:#aad4ff;padding:2px;")
        llay.addWidget(lbl_sec)

        self.sector_list = QListWidget()
        self.sector_list.setFont(QFont("Microsoft YaHei", 10))
        self.sector_list.currentItemChanged.connect(self._on_sector_selected)
        self.sector_list.itemDoubleClicked.connect(self._on_sector_dblclick)
        llay.addWidget(self.sector_list)
        splitter.addWidget(left)

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

        self.leader_lbl = QLabel("")
        self.leader_lbl.setStyleSheet("color:#FF6666;font-weight:bold;font-size:12px;")
        rlay.addWidget(self.leader_lbl)

        # 个股表（带排序）
        COLS = ['代码', '名称', '角色', '现价', '涨幅%', '分时走势', '操作']
        self.stock_table = QTableWidget(0, len(COLS))
        self.stock_table.setHorizontalHeaderLabels(COLS)
        hdr = self.stock_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.sectionClicked.connect(self._on_header_clicked)
        self.stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self._show_context_menu)
        self.stock_table.cellClicked.connect(self.on_stock_clicked)  # 点击联动
        self.stock_table.cellDoubleClicked.connect(self._on_stock_double_clicked) # 双击放大
        self.stock_table.currentCellChanged.connect(self.on_stock_cell_changed) # 键盘光标联动
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.setFont(QFont("Microsoft YaHei", 10))
        self.stock_table.setSortingEnabled(False)   # 手动排序
        self.stock_table.setItemDelegateForColumn(5, TrendDelegate(self)) # 图形化走势
        vh = self.stock_table.verticalHeader()
        if vh: vh.setDefaultSectionSize(40) # 增大行高以便看清曲线
        rlay.addWidget(self.stock_table)
        splitter.addWidget(right)

        splitter.setSizes([280, 820])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)   # stretch=1 撑满剩余高度

    # ------------------------------------------------------------------ helpers
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
    def on_realtime_data_arrived(self, df_all):
        """主线程调用，注册订阅、更新评分并同步触发 UI 刷新"""
        try:
            # 1. 更新底层数据与映射
            self.detector.register_codes(df_all)
            
            # 2. 实时评分聚合
            self.detector.update_scores()

            # 3. 节流刷新：根据 duration_sleep_time 控制频率
            now = time.time()
            limit = getattr(cct.CFG, 'duration_sleep_time', 5.0)
            if now - self._last_refresh_ts >= limit:
                self._refresh_sector_list()
                self._last_refresh_ts = now

        except Exception as e:
            logger.error(f"[SectorBiddingPanel] on_realtime_data_arrived: {e}")

    # ------------------------------------------------------------------ UI refresh
    def _refresh_sector_list(self):
        sectors = self.detector.get_active_sectors()
        
        # 1. 记录当前选中的板块名，以便在刷新后恢复
        current_item = self.sector_list.currentItem()
        selected_sector = ""
        if current_item:
            selected_sector = current_item.data(Qt.ItemDataRole.UserRole)
            
        self.sector_list.blockSignals(True)
        self.sector_list.clear()
        
        # 2. 填充列表
        for sdata in sectors:
            sn = sdata['sector']
            sc = sdata['score']
            tags = sdata.get('tags', '')
            lp = sdata.get('leader_pct', 0)
            followers = sdata.get('followers', [])
            fc = len(followers)
            
            # 格式化显示：🔥 板块名 [标签] 强:xx 龙:xx% 跟:xx
            if sc >= 40:
                icon = '🌋'
                color = "#FF1493" # 深粉红/火山红
                bold = True
            elif sc >= 30:
                icon = '🔥'
                color = "#FF3333" # 鲜红
                bold = True
            elif sc >= 20:
                icon = '⚡'
                color = "#FF9900" # 橙色
                bold = False
            elif sc >= 12:
                icon = '🌟'
                color = "#FFD700" # 金黄色
                bold = False
            elif sc >= 6:
                icon = '🌊'
                color = "#00BFFF" # 亮蓝色
                bold = False
            else:
                icon = '📊'
                color = "#AAAAAA" # 灰色
                bold = False

            tag_str = f" [{tags}]" if tags else ""
            txt = f"{icon} {sn}{tag_str}  强:{sc:.1f}  龙:{lp:+.1f}%  跟:{fc}"
            
            item = QListWidgetItem(txt)
            item.setData(Qt.ItemDataRole.UserRole, sn)
            
            # 高强度标红提示
            item.setForeground(QColor(color))
            if bold:
                f = item.font(); f.setBold(True); item.setFont(f)
                
            self.sector_list.addItem(item)
            
            # 恢复之前的选择
            if sn == selected_sector:
                self.sector_list.setCurrentItem(item)
        
        # 3. 自动选中：如果当前没选中（初次打开或旧选失效），自动选第一个
        do_auto_select = False
        if not self.sector_list.currentItem() and self.sector_list.count() > 0:
            self.sector_list.setCurrentRow(0)
            do_auto_select = True
            
        self.sector_list.blockSignals(False)
        
        # 🚦 强制触发：如果执行了自动选中，手动调用一次选中逻辑（因为 blockSignals 会屏蔽信号）
        if do_auto_select:
            self._on_sector_selected(self.sector_list.currentItem(), None)
        
        # 4. 更新状态栏
        sub_cnt = len(self.detector._subscribed)
        sess = self._session_str()
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"[{sess}] 订阅:{sub_cnt}  活跃板块:{len(sectors)}")

    # ------------------------------------------------------------------ sector select
    def _on_sector_selected(self, cur, _prev):
        if not cur:
            self.stock_table.setRowCount(0)
            return
        sn = cur.data(Qt.ItemDataRole.UserRole)
        for d in self.detector.get_active_sectors():
            if d['sector'] == sn:
                self._populate_table(d)
                return

    def _on_sector_dblclick(self, item):
        """双击板块 → 将龙头推送到 TK / Qt 联动"""
        sn = item.data(Qt.ItemDataRole.UserRole)
        for d in self.detector.get_active_sectors():
            if d['sector'] == sn:
                self._link_code(d['leader'])
                break

    # ------------------------------------------------------------------ table fill
    def _populate_table(self, data: dict):
        leader_code   = data['leader']
        leader_name   = data.get('leader_name', leader_code)
        leader_pct    = data.get('leader_pct', 0.0)
        leader_price  = data.get('leader_price', 0.0)
        leader_klines = data.get('leader_klines', [])
        followers     = data.get('followers', [])

        mini = _ascii_kline(leader_klines, width=44)
        self.kline_lbl.setText(f"龙头分时: {mini}")
        self.leader_lbl.setText(
            f"🏆 {leader_name} [{leader_code}]  "
            f"现价:{leader_price:.2f}  涨幅:{leader_pct:+.2f}%  "
            f"K线:{len(leader_klines)}棒"
        )

        rows = [{
            'code': data['leader'], 'name': data['leader_name'],
            'role': '🏆龙头',
            'pct': data['leader_pct'], 'price': data['leader_price'],
            'klines': data['leader_klines'],
            'last_close': data.get('leader_last_close', 0),
            'high_day': data.get('leader_high_day', 0),
            'low_day': data.get('leader_low_day', 0),
            'last_high': data.get('leader_last_high', 0),
            'last_low': data.get('leader_last_low', 0),
            'hint': '主力拉升'
        }]
        for f in data['followers']:
            rows.append({
                'code': f['code'], 'name': f['name'],
                'role': '📌跟随',
                'pct': f['pct'], 'price': f['price'],
                'klines': self._follower_klines(f['code']),
                'last_close': f.get('last_close', 0),
                'high_day': f.get('high_day', 0),
                'low_day': f.get('low_day', 0),
                'last_high': f.get('last_high', 0),
                'last_low': f.get('last_low', 0),
                'hint': '板块联动'
            })

        # 应用排序
        col = self._sort_col
        rev = not self._sort_asc
        if col == 3:    # 现价
            rows.sort(key=lambda r: r['price'], reverse=rev)
        elif col == 4:  # 涨幅
            rows.sort(key=lambda r: r['pct'], reverse=rev)
        # 龙头始终置顶
        # [FIX] 减少闪烁并保持选择状态
        self.stock_table.setUpdatesEnabled(False)
        self._is_populating = True
        
        # 记录当前选中的代码，以便恢复
        if not self._last_selected_code:
            curr_row = self.stock_table.currentRow()
            if curr_row >= 0:
                item = self.stock_table.item(curr_row, 0)
                if item: self._last_selected_code = item.text()

        self.stock_table.setRowCount(len(rows))
        target_row = -1
        for i, r in enumerate(rows):
            self._set_item(i, 0, r['code'])
            self._set_item(i, 1, r['name'])

            role_item = QTableWidgetItem(r['role'])
            if '龙头' in r['role']:
                role_item.setForeground(QColor("#FF3344"))
                f2 = role_item.font(); f2.setBold(True); role_item.setFont(f2)
            self.stock_table.setItem(i, 2, role_item)

            self._set_item(i, 3, f"{r['price']:.2f}")

            # 恢复丢失的涨幅列 (Column 4)
            pct_item = QTableWidgetItem(f"{r['pct']:+.2f}%")
            pct_item.setForeground(QColor("#FF4444") if r['pct'] > 0
                                   else QColor("#44CC44"))
            self.stock_table.setItem(i, 4, pct_item)

            # 更新分时走势列 (Column 5)，传递原始价格列表供 Delegate 绘制
            k_prices = []
            for k in r['klines']:
                try:
                    k_prices.append(float(k.get('close', 0)))
                except (ValueError, TypeError):
                    k_prices.append(0.0)
            
            k_item = QTableWidgetItem("")
            k_item.setData(Qt.ItemDataRole.UserRole, {
                'prices': k_prices,
                'last_close': r.get('last_close', 0)
            })
            # 关闭分时走势的编辑功能
            k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.stock_table.setItem(i, 5, k_item)

            self._set_item(i, 6, r['hint'])

            # 匹配之前选中的行
            if r['code'] == self._last_selected_code:
                target_row = i

        # 统一设置所有项为不可编辑 (除特定交互外)
        for r_idx in range(self.stock_table.rowCount()):
            for c_idx in range(self.stock_table.columnCount()):
                it = self.stock_table.item(r_idx, c_idx)
                if it:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

        # 恢复选中状态
        if target_row >= 0:
            self.stock_table.setCurrentCell(target_row, 0)
        
        self._is_populating = False
        self.stock_table.setUpdatesEnabled(True)

    def _set_item(self, row, col, text):
        self.stock_table.setItem(row, col, QTableWidgetItem(str(text)))

    def _follower_klines(self, code: str) -> List[dict]:
        with self.detector._lock:
            ts = self.detector._tick_series.get(code)
            # 延长样本长度到 35，以便 Sparkline 能看到更长趋势
            return list(ts.klines)[-35:] if ts else []

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
            self._sort_asc = False
        # 刷新当前板块
        cur = self.sector_list.currentItem()
        if cur:
            self._on_sector_selected(cur, None)
    # ------------------------------------------------------------------ linkage
    def _on_stock_double_clicked(self, row, col):
        # 双击功能只在分时走势 (Column 5) 上有效
        if col != 5:
            return

        code_item = self.stock_table.item(row, 0)
        name_item = self.stock_table.item(row, 1)
        if not code_item: return
        code = code_item.text()
        name = name_item.text() if name_item else code
        
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

        # Fallback to detector session cache if service empty
        if not klines:
            klines = self._follower_klines(code)
        
        # 获取该行对应的基础价格元数据
        k_item = self.stock_table.item(row, 5)
        if k_item:
            pdata = k_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(pdata, dict):
                meta['last_close'] = pdata.get('last_close', 0)
        
        with self.detector._lock:
            ts = self.detector._tick_series.get(code)
            if ts:
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
            self._link_code(code)

    def _link_code(self, code: str):
        """将股票代码同步联动到主界面或外挂工具"""
        host = self.main_window
        if not host: return
        
        try:
            # 1. 尝试联动主界面的 scroll 信号
            if hasattr(host, 'scroll_to_code_signal'):
                host.scroll_to_code_signal.emit(code)
            
            # 2. 尝试直接调用 tree_scroll_to_code (常见于 Qt 版)
            if hasattr(host, 'tree_scroll_to_code'):
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: host.tree_scroll_to_code(code, vis=True))
    
            # 3. 如果主界面有 sender 对象，通过它发送 (兼容旧版)
            if hasattr(host, 'sender') and host.sender:
                host.sender.send(code)
        
            # 4. 联动后强制将焦点拿回来，支持左右手配合操作
            if self.stock_table.isVisible():
                self.stock_table.setFocus()
            
            # 更新状态记录
            self._last_selected_code = code
            logger.debug(f"[SectorPanel] Linked code: {code}")
                 
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
        menu.addSeparator()
        menu.addAction("📋 复制代码", lambda: self._copy_to_clipboard(code))
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
    def _on_strategy_changed(self):
        s = self.detector.strategies
        s['new_high']['enabled']       = self.cb_new_high.isChecked()
        s['ma_rebound']['enabled']     = self.cb_ma_rebound.isChecked()
        s['surge_vol']['enabled']      = self.cb_surge_vol.isChecked()
        s['consecutive_up']['enabled'] = self.cb_consec.isChecked()
        s['surge_vol']['min_ratio']    = self.spin_vol_ratio.value()
        s['pct_change']['min']         = self.spin_pct_min.value()
        s['pct_change']['max']         = self.spin_pct_max.value()

    # ------------------------------------------------------------------ window state
    def _restore_geometry(self):
        try:
            settings = QSettings("StockMonitor", SETTINGS_KEY)
            geom = settings.value("geometry")
            if geom:
                self.restoreGeometry(geom)
        except Exception:
            pass

    def _save_geometry(self):
        try:
            settings = QSettings("StockMonitor", SETTINGS_KEY)
            settings.setValue("geometry", self.saveGeometry())
        except Exception:
            pass

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

    def closeEvent(self, event):
        self._refresh_timer.stop()
        self._score_timer.stop()
        self._save_geometry()
        # 兼容旧接口
        try:
            self.save_window_position_qt_visual(self, "sector_bidding_panel")
        except Exception:
            pass
        super().closeEvent(event)
