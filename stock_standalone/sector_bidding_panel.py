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
    QStyledItemDelegate, QStyleOptionViewItem, QDialog, QLineEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QSize, QPoint, QRect, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QFont, QAction, QPen, QPainter
import pyqtgraph as pg

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
import traceback

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
            y2 = to_y(prices[i+1])
            painter.drawLine(QPoint(int(x1), int(y1)), QPoint(int(x2), int(y2)))
            
        painter.restore()


class SBCTestThread(QThread):
    """SBC 模式验证后台线程，防止 GUI 卡死"""
    finished_data = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, code: str, use_live: bool, hdf5_lock=None):
        super().__init__()
        self.code = code
        self.use_live = use_live
        self.hdf5_lock = hdf5_lock

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
                hdf5_lock=self.hdf5_lock
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


class NumericTableWidgetItem(QTableWidgetItem):
    """自定义表格项，支持数值排序而不是字符串字典排序"""
    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            try:
                # 去除可能的百分号和加号再转换为浮点数
                val_self = float(self.text().replace('%', '').replace('+', '').strip())
                val_other = float(other.text().replace('%', '').replace('+', '').strip())
                return val_self < val_other
            except ValueError:
                pass # 回退到普通字符串比较
        return super().__lt__(other)

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

class DataProcessWorker(QObject):
    """Worker object to process realtime data in a separate QThread."""
    finished = pyqtSignal()
    
    def __init__(self, detector):
        super().__init__()
        self.detector = detector
        self.df_queue = []
        self._is_running = True
        
    def add_data(self, df):
        self.df_queue.append(df)
        
    def process_data(self):
        """Continuously process data from the queue."""
        while self._is_running:
            if self.df_queue:
                df = self.df_queue.pop(0)
                try:
                    # [HEARTBEAT] 后台数据处理心跳
                    if self.detector.enable_log:
                        logger.info(f"💓 [Worker] Processing heartbeat: Queue size={len(self.df_queue)}")
                        
                    self.detector.register_codes(df)
                    self.detector.update_scores()
                    self.finished.emit()
                except Exception as e:
                    logger.error(f"[SectorBiddingPanel Worker] Error: {e}")
            else:
                QThread.msleep(50)
        # Emit finished again when loop exits to ensure thread knows it can quit
        self.finished.emit()
                
    def stop(self):
        self._is_running = False

class SectorBiddingPanel(QWidget, WindowMixin):
    """竞价和尾盘板块联动监控面板 v3"""

    # ------------------------------------------------------------------ init
    def __init__(self, main_window: Any):
        # 🚀 [NEW] Centralized Data Hub Initialization (Multi-Point Protection)
        # Ensure DataHub is ready in the Bidding Panel process
        # self.data_hub = DataHubService.get_instance()
        pass
        
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
        self._force_update_requested = False
        self._sbc_test_windows = []     # 持有 SBC 测试窗口引用，防止 GC

        # Async Data Processing Worker - DON'T parent thread to widget!
        # Parenting to QWidget causes Qt to delete the thread when the widget is destroyed,
        # even if the thread is still running. Manage lifecycle manually instead.
        self._worker_thread = QThread()  # No parent - managed manually
        self._worker = DataProcessWorker(self.detector)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.process_data)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker_thread.start()

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
        if self.sector_list.count() == 0:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("🔄 准备首次数据评分映射...")
            QTimer.singleShot(500, self.manual_refresh)

    def closeEvent(self, event):
        """Window close event, clean up threads gracefully."""
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
                thread.quit()   # 请求事件循环退出（process_data 是普通 while，需要 _is_running 来退出）
                if not thread.wait(3000):
                    # 超时则强制终止
                    logger.warning("[SectorBiddingPanel] Worker thread did not stop in time, terminating...")
                    thread.terminate()
                    thread.wait(500)
            thread.deleteLater()   # 安全释放
            self._worker_thread = None
        self._save_geometry()
        super().closeEvent(event)


    # ------------------------------------------------------------------ UI
    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

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
        
        # [NEW] Search Bar
        bar_lay_1.addWidget(QLabel("🔍搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("例如: MA60反转 涨幅>3")
        self.search_input.setFixedWidth(180)
        self.search_input.returnPressed.connect(self._on_search_triggered)
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
        self.btn_refresh.clicked.connect(self.manual_refresh)
        bar_lay_2.addWidget(self.btn_refresh)

        self.cb_log = QCheckBox("Log")
        self.cb_log.setToolTip("开启/关闭后台日志输出")
        self.cb_log.setChecked(self.detector.enable_log)
        self.cb_log.stateChanged.connect(self._on_strategy_changed)
        bar_lay_2.addWidget(self.cb_log)

        self.btn_hide = QPushButton("隐藏 ✖")
        self.btn_hide.setFixedWidth(55)
        self.btn_hide.clicked.connect(self.hide)
        bar_lay_2.addWidget(self.btn_hide)

        # [NEW] 板块综合强度过滤
        bar_lay_2.addWidget(self._sep())
        lbl_strength = QLabel("🔥 强度≥")
        lbl_strength.setStyleSheet("color: #ff3333; font-weight: bold;")
        bar_lay_2.addWidget(lbl_strength)
        self.spin_strength = self._make_spin(0.0, 500.0, 1.0, self.detector.sector_score_threshold)
        self.spin_strength.setToolTip("过滤核心强度(板分)较低的噪点板块")
        self.spin_strength.valueChanged.connect(self._on_threshold_changed)
        bar_lay_2.addWidget(self.spin_strength)

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
        bar_lay_3.addWidget(self.spin_score_threshold)

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
        COLS = ['代码', '名称', '角色', '现价', '涨幅%', '分时走势', '形态暗示(安)']
        self.stock_table = QTableWidget(0, len(COLS))
        self.stock_table.setHorizontalHeaderLabels(COLS)
        hdr = self.stock_table.horizontalHeader()
        if hdr:
            hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
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

        # ── [NEW] 底部：当日重点表 (Watchlist) ───────────────────────────
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setChildrenCollapsible(False)
        self.v_splitter.addWidget(splitter)

        self.watchlist_group = QGroupBox("📋 当日重点表 (共 0 只, 涨停/溢出个股)")
        self.watchlist_group.setStyleSheet("QGroupBox { font-weight:bold; color:#aad4ff; }")
        w_lay = QVBoxLayout(self.watchlist_group)
        w_lay.setContentsMargins(2, 6, 2, 2)
        
        W_COLS = ['代码', '名称', '涨幅%', '核心板块', '触发时间', '状态/原因']
        self.watchlist_table = QTableWidget(0, len(W_COLS))
        self.watchlist_table.setHorizontalHeaderLabels(W_COLS)
        self.watchlist_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.watchlist_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.watchlist_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.watchlist_table.setAlternatingRowColors(True)
        self.watchlist_table.setFont(QFont("Microsoft YaHei", 9))
        self.watchlist_table.setSortingEnabled(True) # [ADD] Enable table clicking/sorting
        self.watchlist_table.cellClicked.connect(self._on_watchlist_clicked)
        self.watchlist_table.cellDoubleClicked.connect(self._on_watchlist_dblclick)
        self.watchlist_table.currentCellChanged.connect(self._on_watchlist_cell_changed)
        
        # 启用右键菜单支持 (用于联动活跃板块)
        self.watchlist_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.watchlist_table.customContextMenuRequested.connect(self._on_watchlist_context_menu)
        
        w_lay.addWidget(self.watchlist_table)
        self.v_splitter.addWidget(self.watchlist_group)
        self.v_splitter.setSizes([500, 180]) # 默认分配比例
        
        root.addWidget(self.v_splitter, 1)   # stretch=1 撑满剩余高度

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
    def manual_refresh(self):
        """手动触发评分计算和 UI 刷新 (增加防抖和状态反馈)"""
        if not hasattr(self, 'btn_refresh'): return
        
        try:
            # 1. 按钮防抖与反馈
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText("刷新中...")
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText("⏳ 正在全量计算评分 (请稍候)...")
                self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")
            
            # 2. 强制触发全量重算
            # [REFINED] 要求后台线程在处理下一帧时忽略时间窗口限制
            self._force_update_requested = True
            
            # 立即在当前线程尝试刷新（如果队列为空）
            if not self._worker.df_queue:
                self.detector.update_scores()
                self._refresh_sector_list()
                logger.info("⚡ [Manual] 已完成同步数据评分刷新")
            else:
                logger.info("⚡ [Manual] 任务已加入队列，等待后台处理...")

            # 3. 3秒后恢复按钮 (防抖)
            QTimer.singleShot(3000, lambda: self.btn_refresh.setEnabled(True))
            QTimer.singleShot(3000, lambda: self.btn_refresh.setText("刷新 🔄"))
            
        except Exception as e:
            logger.error(f"Manual refresh failed: {e}")
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("刷新 🔄")

    def _run_sbc_test(self, use_live: bool):
        """
        [NEW] 调用 verify_sbc_pattern.py 逻辑验证选中个股 of SBC 信号
        使用线程异步执行，防止 GUI 卡死
        """
        # 检查是否已有线程正在运行
        if hasattr(self, '_sbc_thread') and self._sbc_thread.isRunning():
            QMessageBox.information(self, "请稍候", f"后台正在对 {self._sbc_thread.code} 进行验证，请等待完成后再试。")
            return

        code = self._get_selected_stock()
        if not code:
            QMessageBox.warning(self, "未选中个股", "请在个股表或重点表中先选中一只个股再执行测试。")
            return
            
        # 尝试获取主窗口的 HDF5 锁
        hdf5_lock = getattr(self.main_window, 'hdf5_mutex', None)
        
        # 记录正在测试的状态
        status_msg = f"正在测试 {code} ({'实时' if use_live else '回放'})..."
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"⏳ {status_msg}")
            self.status_lbl.setStyleSheet("color: yellow; font-weight: bold;")
        
        # 创建并启动后台线程
        self._sbc_thread = SBCTestThread(code, use_live, hdf5_lock=hdf5_lock)
        self._sbc_thread.finished_data.connect(self._on_sbc_test_finished)
        self._sbc_thread.error_occurred.connect(self._on_sbc_test_error)
        self._sbc_thread.start()
        
        logger.info(f"⏳ SBC 信号测试已启动后台线程: {code} (Live Mode: {use_live})")

    def _on_sbc_test_finished(self, data: dict):
        """线程完成后的回调，在 GUI 线程显示图表"""
        try:
            # 动态导入可视化函数
            try:
                from stock_visual_utils import show_chart_with_signals
            except ImportError:
                from stock_standalone.stock_visual_utils import show_chart_with_signals
            
            # 使用返回的结果包调用可视化
            win = show_chart_with_signals(
                data["viz_df"],
                data["signals"],
                data["title"],
                avg_series=data["avg_series"],
                time_labels=data["time_labels"],
                use_line=data["use_line"]
            )
            
            # 管理窗口引用，防止被回收
            self._sbc_test_windows = [w for w in self._sbc_test_windows if w.isVisible()]
            if win:
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
        """主线程调用，将数据推入后台线程列队避免卡顿 UI"""
        try:
            # Drop obsolete frames if we are piling up
            if len(self._worker.df_queue) > 1:
                 self._worker.df_queue.clear()
                 
            self._worker.add_data(df_all)
            
            # Record force_update request state
            self._force_update_requested = force_update
            
        except Exception as e:
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
            
            if getattr(self, '_force_update_requested', False) or (now - self._last_refresh_ts >= limit):
                # [HEARTBEAT] 前台刷新心跳
                if self.detector.enable_log:
                    logger.info(f"💓 [Board Panel] Refreshing heartbeat: Total sectors={len(self.detector.active_sectors)}")
                    
                self._refresh_sector_list()
                self._last_refresh_ts = now
                self._force_update_requested = False
                
        except Exception as e:
            logger.error(f"[SectorBiddingPanel] _on_worker_finished err: {e}")

    # ------------------------------------------------------------------ UI refresh
    def _refresh_sector_list(self):
        # 1. 如果还在排队（尤其是第一次注册大量个股），在 UI 提示
        if self._worker.df_queue:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(f"📡 正在拉取个股分时 (队列: {len(self._worker.df_queue)})...")
                self.status_lbl.setStyleSheet("color: #FFD700; font-weight: bold;")
        
        sectors = self.detector.get_active_sectors()
        
        if not sectors:
            # 如果目前没有活跃板块，在状态栏提示
            if hasattr(self, 'status_lbl') and not self._worker.df_queue:
                self.status_lbl.setText("📝 目前无满足门槛的活跃板块")
                self.status_lbl.setStyleSheet("color: #AAAAAA;")
            return
        
        now_str = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, 'status_lbl'):
            self.status_lbl.setText(f"✅ 刷新完成 ({now_str}) | 活跃板块: {len(sectors)}")
            self.status_lbl.setStyleSheet("color: #aad4ff; font-weight: bold;")
        
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
        
        # 🚦 [FIX] 强制触发：无论是否 auto_select，只要有选中项，都重刷一次右侧个股表
        # 否则如果板块选择没变，右侧数据（现价/涨幅）就不会随刷新周期更新
        if self.sector_list.currentItem():
            self._on_sector_selected(self.sector_list.currentItem(), None)
        
        # 4. 更新状态栏
        sub_cnt = len(self.detector._subscribed)
        sess = self._session_str()
        
        # [NEW] Render total hits if search is active
        if hasattr(self, '_active_search_query') and self._active_search_query:
            self.status_lbl.setText(f"[{sess}] 过滤模式 | 关键字: {self._active_search_query}")
        else:
            if hasattr(self, 'status_lbl'):
                self.status_lbl.setText(f"[{sess}] 订阅:{sub_cnt}  活跃板块:{len(sectors)}")

        # 5. [NEW] 更新底部重点表
        self._populate_watchlist()

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

    # ------------------------------------------------------------------ search functionality
    def _on_search_triggered(self):
        query = self.search_input.text().strip()
        if not query:
            query = self.search_input.placeholderText().replace("例如: ", "").strip()
            self.search_input.setText(query)
        self._active_search_query = query
        self.manual_refresh()
        
    def _on_search_cleared(self):
        self.search_input.clear()
        self._active_search_query = ""
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
                        pass # Requires extracting vol ratio from df_all if needed. Skip for now or default true.
                    
                    if op == '>':
                        if not actual_val > target_val: return False
                    elif op == '<':
                        if not actual_val < target_val: return False
                    elif op in ('>=', '=>'):
                        if not actual_val >= target_val: return False
                    elif op in ('<=', '=<'):
                        if not actual_val <= target_val: return False
                    elif op in ('=', '=='):
                        if not abs(actual_val - target_val) < 0.01: return False
                        
                except ValueError:
                    continue # Ignore invalid floats
            else:
                # Fallback to general text inclusion search (Code, Name, Hint, Role)
                text_to_search = (
                    str(row_data.get('code', '')) + 
                    str(row_data.get('name', '')) + 
                    str(row_data.get('hint', '')) + 
                    str(row_data.get('pattern_hint', '')) + 
                    str(row_data.get('leader_name', '')) +
                    str(row_data.get('role', '')) +
                    str(row_data.get('tags', ''))
                )
                if cond.lower() not in text_to_search.lower():
                    return False
                    
        return True

    # ------------------------------------------------------------------ table fill
    def _populate_table(self, data: dict):
        leader_code   = data.get('leader', '')
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
            'code': leader_code, 
            'name': leader_name,
            'role': '🏆龙头',
            'pct': leader_pct, 
            'price': leader_price,
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
                'hint': f.get('pattern_hint', '板块联动'),
                'untradable': f.get('untradable', False), # Follower untradability not fully tracked yet but added for safety
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

            hint_str = r['hint']
            if r['untradable']:
                hint_str = "🚫一字板 " + hint_str
            if r['is_counter']:
                hint_str = "🔥逆势 " + hint_str
                
            hint_item = QTableWidgetItem(hint_str)
            
            # [Added] 增强颜色提示
            if "今日主杀" in hint_str or "破均价线" in hint_str:
                hint_item.setForeground(QColor("#FF1111")) # 亮红提示风险
            elif "新高" in hint_str or "突破" in hint_str or "放量" in hint_str:
                hint_item.setForeground(QColor("#FFCC00")) # 金黄色提示异动/突破
            elif "支撑" in hint_str or "多头" in hint_str:
                hint_item.setForeground(QColor("#FF99CC")) # 粉紫色提示持仓优势
            elif r['untradable']:
                hint_item.setForeground(QColor("#888888")) # 灰色显示不可交易
            elif r['is_counter']:
                hint_item.setForeground(QColor("#FFCC00"))
                
            self.stock_table.setItem(i, 6, hint_item)

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

    # ── [NEW] Watchlist Support ──────────────────────────────────────
    def _populate_watchlist(self):
        """填充底部当日重点表"""
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
        curr_row = self.watchlist_table.currentRow()
        if curr_row >= 0:
            item = self.watchlist_table.item(curr_row, 0)
            if item: selected_code = item.text()

        self.watchlist_table.setRowCount(len(watchlist))
        
        # [NEW] Disable sorting while populating to prevent sort crashes
        self.watchlist_table.setSortingEnabled(False)
        target_row = -1
        
        for i, w in enumerate(watchlist):
            # 1. 代码
            self.watchlist_table.setItem(i, 0, QTableWidgetItem(w['code']))
            # 2. 名称
            self.watchlist_table.setItem(i, 1, QTableWidgetItem(w['name']))
            # 3. 涨幅
            p_val = w.get('pct', 0)
            p_item = NumericTableWidgetItem(f"{p_val:+.2f}%")
            p_item.setForeground(QColor("#FF4444") if p_val > 0 else QColor("#44CC44"))
            self.watchlist_table.setItem(i, 2, p_item)
            # 4. 核心板块
            s_val = w.get('sector', '')
            # 过滤掉市场标签
            market_tags = ['科创板', '创业板', '主板', '中小板', '北证']
            all_cats = s_val.split(';')
            cats = [c for c in all_cats if c not in market_tags]
            sector_short = cats[0] if cats else (all_cats[0] if all_cats else 'N/A')
            self.watchlist_table.setItem(i, 3, QTableWidgetItem(sector_short))
            # 5. 触发时间
            self.watchlist_table.setItem(i, 4, QTableWidgetItem(w.get('time_str', '--:--:--')))
            # 6. 状态/原因
            reason = w.get('reason', '')
            r_item = QTableWidgetItem(reason)
            if '涨停' in reason:
                r_item.setForeground(QColor("#FF1493"))
            self.watchlist_table.setItem(i, 5, r_item)

            if w['code'] == selected_code:
                target_row = i

        # 设置不可编辑
        for r_idx in range(self.watchlist_table.rowCount()):
            for c_idx in range(self.watchlist_table.columnCount()):
                it = self.watchlist_table.item(r_idx, c_idx)
                if it: it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if target_row >= 0:
            # 仅当当前没有选中行，或者选中行变动时，才恢复选中
            # 避免实时刷新时反复 setCurrentCell 导致滚动跳动
            if self.watchlist_table.currentRow() != target_row:
                self.watchlist_table.blockSignals(True)
                self.watchlist_table.setCurrentCell(target_row, 0)
                self.watchlist_table.blockSignals(False)
                
        # [NEW] Re-enable sorting
        self.watchlist_table.setSortingEnabled(True)
        # [NEW] Update Watchlist title stats
        self.watchlist_group.setTitle(f"📋 当日重点表 (共 {len(watchlist)} 只, 涨停/溢出个股)")

    def _on_watchlist_clicked(self, row, col):
        """重点表联动"""
        item = self.watchlist_table.item(row, 0)
        if item:
            code = item.text()
            self._link_code(code, focus_widget=self.watchlist_table)

    def _on_watchlist_dblclick(self, row, col):
        """重点表双击：对应列执行不同动作"""
        # 1. 如果是代码(0)或名称(1)列，弹出详细走势图 (与主表一致)
        if col <= 1:
            code_item = self.watchlist_table.item(row, 0)
            name_item = self.watchlist_table.item(row, 1)
            if code_item and name_item:
                code, name = code_item.text(), name_item.text()
                klines = self._follower_klines(code)
                # 尽量匹配 meta
                meta = {'sector': self.watchlist_table.item(row, 3).text() if self.watchlist_table.item(row, 3) else 'N/A'}
                dlg = DetailedChartDialog(code, name, klines, meta, parent=self)
                dlg.exec()
        
        # 2. 如果是核心板块(3)列，仅执行复制 (联动改为右键)
        elif col == 3:
            item = self.watchlist_table.item(row, col)
            if item:
                sector_name = item.text()
                # 去除末尾可能存在的空格
                sector_name = sector_name.strip()
                self._copy_to_clipboard(sector_name)
                # 状态栏提示仅显示复制
                if hasattr(self, 'status_lbl'):
                    sess = self._session_str()
                    self.status_lbl.setText(f"[{sess}] 📋 已复制板块: {sector_name}")

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
            for i in range(self.sector_list.count()):
                list_item = self.sector_list.item(i)
                sn = list_item.data(Qt.ItemDataRole.UserRole)
                if sn in parts or any(p in sn for p in parts) or sn == sector_name:
                    self.sector_list.setCurrentItem(list_item)
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
            self._link_code(code, focus_widget=self.stock_table)

    def _link_code(self, code: str, focus_widget=None):
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
        
            # 4. [FIX] 根据来源恢复焦点，点击哪里光标留在哪里
            if focus_widget and focus_widget.isVisible():
                focus_widget.setFocus()
            elif not focus_widget and self.stock_table.isVisible():
                # 默认回退到个股表
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
    def _on_threshold_changed(self, val):
        """同步强度门槛到 detector 并刷新列表"""
        self.detector.sector_score_threshold = float(val)
        self._refresh_sector_list()

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
            
        # [FIX] 确保改动即时在 UI 生效
        self.manual_refresh()
        if self.sector_list.currentItem():
             self._on_sector_selected(self.sector_list.currentItem(), None)

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

    def _on_rearrange_clicked(self):
        """Trigger global window tiling."""
        try:
            from qt_window_utils import tile_all_windows
            tile_all_windows()
        except Exception as e:
            logger.error(f"Rearrange error: {e}")

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
