# -*- coding: utf-8 -*-
"""
ats/ui/ipo_subnew_detector_dialog.py
------------------------------------
新股次新股超短检测工具主窗口 (SBC 极限 10日 VWAP 预判与异动引擎)
- 独立进程原生顶级桌面窗口，不拖累 ATS 主界面；
- 默认检测全市场新股与次新股；
- 实时捕捉在 VWAP 走平 1~3 天蓄势 (预下单) 与在 VWAP 之上回踩不碰 (极限买点)；
- 结合大趋势 K 线支撑与启动标签；
- 支持手动输入代码、ATS 跨进程一键发送、双击一键调出 SBC 10d VWAP 走势。
"""

import os
import sys
import json
import time
import math
import logging
import warnings
from datetime import datetime
from collections import deque
from typing import List, Dict, Optional, Set, Any, Tuple
import pandas as pd

# 全局深度屏蔽高频指标计算中的 PerformanceWarning 与 SettingWithCopyWarning
try:
    pd.options.mode.chained_assignment = None
    if hasattr(pd, 'errors') and hasattr(pd.errors, 'PerformanceWarning'):
        warnings.filterwarnings('ignore', category=pd.errors.PerformanceWarning)
except Exception:
    pass
warnings.filterwarnings('ignore', message='.*DataFrame is highly fragmented.*')
warnings.filterwarnings('ignore', message='.*A value is trying to be set on a copy of a slice from a DataFrame.*')

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFrame,
    QMenu, QApplication, QPlainTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut, QAction

from tk_gui_modules.qt_table_utils import NumericTableWidgetItem


class IPONumericTableWidgetItem(NumericTableWidgetItem):
    """专用数值单元格，确保点击表头按真实 float/int 排序，显示带格式化文本"""
    def __init__(self, display_text: str, raw_val: float):
        super().__init__(display_text)
        self.raw_val = raw_val

    def data(self, role: int):
        if role == Qt.ItemDataRole.EditRole:
            return self.raw_val
        return super().data(role)

from concurrent.futures import ThreadPoolExecutor, as_completed

from ats.ui.base_table import BaseATSTableWidget
from ats.strategy.ipo_vwap_detector_engine import (
    IPOVWAPDetectorEngine, VWAPDetectorSignal, resolve_fast_ipo_name
)
from ats.ui.ipo_detector_ipc import (
    get_ipo_detector_layout_file,
    pop_queued_stocks,
    update_detector_heartbeat
)
from ats.new_stock_fetcher import NewStockFetcher

logger = logging.getLogger("IPODetectorUI")


def is_stock_actually_listed(code: str) -> bool:
    """
    严密判定标的是否真正已在二级市场上市交易 (P0 核心拦截)
    - 坚决杜绝未上市股票 (待上市/待申购/发行未上市) 进入超短检测池；
    - 剔除虚拟无盘口代码 (如 920295)。
    """
    c_str = str(code).zfill(6)
    if c_str == "920295" or c_str.startswith("N"):
        return False
    try:
        fetcher = NewStockFetcher.get_instance()
        ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
        info = ipo_dict.get(c_str)
        if info:
            ld = str(info.get("listing_date") or "").strip()
            today_str = datetime.now().strftime("%Y-%m-%d")
            # 必须具有上市日期，且上市日期已到达（<= 今天）
            if not ld or ld > today_str:
                return False
            return True
    except Exception:
        pass
    return True


def get_ipo_detector_extra_cols() -> List[str]:
    """获取 ats_col 排除基础固定列后的自定义追加列"""
    try:
        from JohnsonUtil import commonTips as cct
        cfg_cols = getattr(cct, 'ats_col', []) or getattr(cct.CFG, 'ats_col', []) or []
    except Exception:
        cfg_cols = ['win', 'dff', 'ch_bc2']
    BASE_EXCLUDE = {
        'code', 'name', 'price', 'close', 'now', 'trade', 'pct', 'percent', 'vwap', 'vwap_diff', 
        'structure', 'trend', 'signal', 'stop_loss', 'desc', 'time', 'action'
    }
    extra = []
    seen = set(BASE_EXCLUDE)
    for c in cfg_cols:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            extra.append(c_str)
            seen.add(c_str.lower())
    return extra


def get_ipo_detector_table_headers(extra_cols: Optional[List[str]] = None) -> List[str]:
    if extra_cols is None:
        extra_cols = get_ipo_detector_extra_cols()
    try:
        from JohnsonUtil import commonTips as cct
        col_map = getattr(cct, 'vis_column_map', {}) or {}
    except Exception:
        col_map = {}

    base_left = [
        "代码", "名称", "现价", "涨跌幅", "10d VWAP", "VWAP偏离",
        "VWAP结构形态", "大趋势K线状态", "信号评级", "极窄止损位"
    ]
    extra_headers = [col_map.get(c, col_map.get(c.lower(), c)) for c in extra_cols]
    base_right = [
        "操作建议 / 为什么 (预下单逻辑)", "更新时间", "快捷操作"
    ]
    return base_left + extra_headers + base_right


def get_ipo_detector_default_widths(extra_cols: Optional[List[str]] = None) -> List[int]:
    """与其它主力 Tab 100% 对齐的默认极窄模式列宽 (紧凑规整，杜绝空隙与撕裂)"""
    if extra_cols is None:
        extra_cols = get_ipo_detector_extra_cols()
    # 基础 10 列 (极窄模式):
    # 代码(55), 名称(78), 现价(52), 涨跌%(50), 10d VWAP(52), VWAP偏离(52), VWAP形态(68), 大趋势(80), 信号评级(62), 止损位(52)
    base_widths = [55, 78, 52, 50, 52, 52, 68, 80, 62, 52]
    # 动态扩展列 (每个极窄 50)
    extra_widths = [50] * len(extra_cols)
    # 右侧: 预下单逻辑(220), 更新时间(52), 快捷操作(88)
    right_widths = [220, 52, 88]
    return base_widths + extra_widths + right_widths


class IPODetectorTableWidget(BaseATSTableWidget):
    """
    【专用超短检测高响应表格】
    - 统一继承 BaseATSTableWidget，拥有全 ATS 标准的丝滑列宽调整与一体化联动
    - 统一支持键盘方向键 (Up/Down) 极速逐行导航与智能联动；
    - 统一支持键盘翻页键 (PageUp/PageDown) 视口按页跨行极速翻页；
    - 统一支持回车 (Return/Enter) 强制刷新联动；
    - 与主窗口协同，彻底杜绝重复联动。
    """
    def __init__(self, parent_dialog=None):
        super().__init__(parent_dialog)
        self.dialog = parent_dialog

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            if self.dialog and hasattr(self.dialog, "_handle_navigation_key"):
                if self.dialog._handle_navigation_key(key):
                    event.accept()
                    return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            curr = self.currentRow()
            if curr >= 0 and self.dialog and hasattr(self.dialog, "_trigger_linkage_for_row"):
                self.dialog._trigger_linkage_for_row(curr, force=True)
                event.accept()
                return
        super().keyPressEvent(event)


class IPOScanWorker(QThread):
    """【🚀 批量分组多进程+多线程分析 Worker】多进程批量获取日线 + 多线程并发跑策略，极限性能秒级完成"""
    stock_analyzed = pyqtSignal(object)           # 单只信号 (向下兼容)
    batch_analyzed = pyqtSignal(list)             # 整组信号批量输出 (List[VWAPDetectorSignal])
    scan_finished = pyqtSignal(int, float, object)# 总数, 耗时秒, 性能审计字典
    perf_log_emitted = pyqtSignal(str)            # 实时性能审计文本信号 (逐批次实时推送 UI)

    def __init__(self, codes: List[str], batch_size: int = 8, perf_log_enabled: bool = False):
        super().__init__()
        self.codes = list(codes)
        self.batch_size = max(1, min(batch_size, 32))
        self.perf_log_enabled = perf_log_enabled
        self.is_running = True
        self.engine = IPOVWAPDetectorEngine.get_instance()

    def run(self):
        t0 = time.time()
        count = 0
        if not self.codes:
            self.scan_finished.emit(0, 0.0, {})
            return

        # 0. 在并发跑策略前预热解析所有标的名称，100% 写入内存字典，杜绝工作线程中多线程并发 I/O
        try:
            from ats.strategy.ipo_vwap_detector_engine import preload_ipo_stock_names
            preload_ipo_stock_names(self.codes)
        except Exception:
            pass

        # 1. 将全量代码切分成若干批次 (批量分组计算，杜绝单只零碎调度浪费性能)
        batches = [self.codes[i:i + self.batch_size] for i in range(0, len(self.codes), self.batch_size)]
        tot_day_ms = 0.0
        tot_bars_ms = 0.0
        tot_strat_ms = 0.0
        all_stock_costs = []

        start_msg = f"[IPO-SCAN] 启动批量顺序扫描: 共 {len(self.codes)} 只标的 | 切分 {len(batches)} 组 (每组至多 {self.batch_size} 只)"
        if self.perf_log_enabled:
            print(f"\n[IPO-PERF] ------------------------------------------------------------", flush=True)
            print(f"[IPO-PERF] {start_msg}", flush=True)
        self.perf_log_emitted.emit(f"[IPO-PERF] {start_msg}")

        for b_idx, batch_codes in enumerate(batches):
            if not self.is_running:
                break

            t_batch_start = time.perf_counter()

            # ── 步骤 A: 批量顺序读取日线 fastohlc 原始数据 (纯内存与本地 txt，零 H5，零锁) ──
            t_day_start = time.perf_counter()
            day_df_map = {}
            try:
                from ats.strategy.ipo_vwap_detector_engine import batch_fetch_day_kline_fast
                day_df_map = batch_fetch_day_kline_fast(batch_codes, dl=60)
            except Exception as e_mp:
                logger.debug(f"批量预取批次 {b_idx} 日线异常: {e_mp}")
            t_day_ms = (time.perf_counter() - t_day_start) * 1000
            tot_day_ms += t_day_ms

            # ── 步骤 B: 纯单线程顺序跑策略计算 (对齐 --sbc-holdings，零线程池竞争，安全稳定) ──
            t_strat_start = time.perf_counter()
            batch_results = []
            for c in batch_codes:
                if not self.is_running:
                    break
                try:
                    sig = self._analyze_one(c, day_df_map.get(c))
                    if sig:
                        batch_results.append(sig)
                        count += 1
                        p_bars = sig.extra_data.get("_perf_bars_ms", 0.0)
                        p_strat = sig.extra_data.get("_perf_strat_ms", 0.0)
                        p_tot = sig.extra_data.get("_perf_total_ms", 0.0)
                        tot_bars_ms += p_bars
                        tot_strat_ms += p_strat
                        all_stock_costs.append((sig.code, p_tot, p_bars, p_strat))
                except Exception as e:
                    logger.debug(f"分析单股异常: {e}")

            t_batch_total_ms = (time.perf_counter() - t_batch_start) * 1000

            # 批次性能日志
            batch_stock_costs = [item for item in all_stock_costs if item[0] in batch_codes]
            batch_stock_costs.sort(key=lambda x: x[1], reverse=True)
            top3 = batch_stock_costs[:3]
            top3_str = " | ".join(f"{c}(总{t:.0f}ms/分时{b:.0f}ms)" for c, t, b, s in top3)
            codes_summary = ",".join(batch_codes)
            batch_log = f"[IPO-SCAN] 批次 {b_idx + 1}/{len(batches)} ({len(batch_codes)}只: {codes_summary}) | 日线预取: {t_day_ms:.1f}ms | 批次总耗时: {t_batch_total_ms:.1f}ms (均{t_batch_total_ms / max(1, len(batch_codes)):.1f}ms/只)"
            if top3:
                batch_log += f"\n   └─ 耗时 Top3: {top3_str}"

            if self.perf_log_enabled:
                print(f"[IPO-PERF] {batch_log}", flush=True)
            self.perf_log_emitted.emit(f"[IPO-PERF] {batch_log}")

            # ── 步骤 C: 整组批量交付 UI ──
            if batch_results:
                self.batch_analyzed.emit(batch_results)

        cost = time.time() - t0
        all_stock_costs.sort(key=lambda x: x[1], reverse=True)
        global_top3 = all_stock_costs[:3]

        perf_summary = {
            "day_ms": tot_day_ms,
            "bars_ms": tot_bars_ms,
            "strat_ms": tot_strat_ms,
            "batches": len(batches),
            "top3": [(c, t) for c, t, b, s in global_top3],
            "avg_ms": (cost * 1000) / max(1, count)
        }

        top3_report = " | ".join(f"{c}({t:.0f}ms)" for c, t in perf_summary["top3"])
        summary_log = f"🏁 全量扫描结束: 共 {count} 只标的 | 总耗时: {cost:.2f}s | 日线: {tot_day_ms:.0f}ms | 分时: {tot_bars_ms:.0f}ms | 策略: {tot_strat_ms:.0f}ms | 均{perf_summary['avg_ms']:.1f}ms/只"
        if top3_report:
            summary_log += f"\n🏆 全局瓶颈 Top3: {top3_report}"

        if self.perf_log_enabled:
            print(f"[IPO-PERF] {summary_log}", flush=True)
            print(f"[IPO-PERF] ══════════════════════════════════════════════════════════════════\n", flush=True)
        self.perf_log_emitted.emit(f"[IPO-PERF] {summary_log}")

        self.scan_finished.emit(count, cost, perf_summary)

    def _analyze_one(self, code: str, day_df: Optional[pd.DataFrame] = None) -> Optional[VWAPDetectorSignal]:
        if not self.is_running:
            return None
        return self.engine.analyze_stock(code, day_df=day_df)

    def stop(self):
        self.is_running = False


class IPOSubnewDetectorDialog(QMainWindow):
    """新股次新股超短检测独立主窗口"""

    def __init__(self, initial_code: Optional[str] = None):
        super().__init__(None)

        self.setWindowTitle("新股次新股超短检测工具 (SBC 极限 10日 VWAP 预判与异动引擎)")
        self.setMinimumSize(980, 580)
        self.resize(1180, 680)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #101018;
                color: #ffffff;
            }
            QLabel {
                color: #e2e2e5;
                font-size: 9pt;
            }
            QLineEdit {
                background-color: #1a1a24;
                border: 1px solid #3d3d4d;
                border-radius: 4px;
                color: #00ff88;
                font-weight: bold;
                font-size: 9.5pt;
                padding: 3px 8px;
            }
            QLineEdit:focus {
                border: 1px solid #00e5ff;
            }
            QPushButton {
                background-color: #212130;
                border: 1px solid #3d3d4d;
                border-radius: 4px;
                color: #ffffff;
                font-size: 9pt;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #2e2e42;
                border-color: #00e5ff;
            }
            QTableWidget {
                background-color: #12121c;
                border: none;
                gridline-color: #1c1c28;
                color: #ffffff;
                font-size: 9pt;
                selection-background-color: #2b3145;
                selection-color: #ffffff;
            }
            QHeaderView {
                background-color: #1a1a26;
                border: none;
            }
            QHeaderView::section {
                background-color: #1a1a26;
                color: #9aa0a6;
                padding: 4px;
                border: 1px solid #232332;
                font-weight: bold;
                font-size: 9pt;
            }
            QTableCornerButton::section {
                background-color: #1a1a26;
                border: 1px solid #232332;
            }
            /* 垂直与水平滚动条暗黑金融质感 (彻底消除右上角与滚动条浅色白块) */
            QScrollBar:vertical {
                border: none;
                background-color: #121214;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #2e2e36;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #3e3e4a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QScrollBar:horizontal {
                border: none;
                background-color: #121214;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background-color: #2e2e36;
                min-width: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #3e3e4a;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        self.monitored_codes: List[str] = []
        self.signals_map: Dict[str, VWAPDetectorSignal] = {}
        self.extra_cols: List[str] = get_ipo_detector_extra_cols()
        self.ipc_df: Optional[pd.DataFrame] = None

        # 列宽手动拖拽与跨会话自动持久化
        self.column_widths: Dict[str, int] = {}
        self._is_restoring_header = False

        # 扫描线程与性能日志控制
        self.worker: Optional[IPOScanWorker] = None
        self.perf_log_enabled = False
        self._is_table_updating = False
        self._pending_linkage_row = -1
        self._pending_linkage_code = ""
        self._last_linkage_code = ""
        self._current_sort_col = -1
        self._current_sort_order = Qt.SortOrder.DescendingOrder

        # 待渲染平滑队列与 30ms 分帧渲染定时器 (彻底消除多线程并发冲刷 UI 导致的掉帧、全表重排与顿卡)
        self._pending_render_queue = deque()
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._flush_pending_renders)

        # 0. 初始化全局实时行情 IPC 同步管理器 (为自定义扩展列连阳/DFF/ch_bc2等提供实时高速数据流)
        try:
            from multi_period_strategy_engine import get_global_ipc_sync_manager
            self.ipc_mgr = get_global_ipc_sync_manager()
            if self.ipc_mgr and not getattr(self.ipc_mgr, '_listener_running', False):
                self.ipc_mgr.start()
        except Exception:
            self.ipc_mgr = None

        self._init_ui()
        self._load_persisted_state()

        if initial_code:
            self.add_stock(initial_code)

        # 1. IPC 接收与心跳守护定时器 (500ms)
        self.ipc_timer = QTimer(self)
        self.ipc_timer.timeout.connect(self._on_ipc_poll_and_heartbeat)
        self.ipc_timer.start(500)

        # 2. 定期自动刷新机制：改为单次按需调度 (整轮任务完成后延时触发，彻底告别不停狂刷)
        self.auto_refresh_enabled = False  # 默认不自动狂刷，单轮跑完宁静展示
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.trigger_scan)

        # 立即启动首轮扫描
        QTimer.singleShot(200, self.trigger_scan)

    def _init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        # ── 1. 顶部操作工具栏 ──
        tb_layout = QHBoxLayout()
        tb_layout.setSpacing(8)

        self.lbl_status = QLabel("📊 监控中: 0 只 | 正在初始化全市场新股次新池...")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #00e5ff;")
        tb_layout.addWidget(self.lbl_status)

        tb_layout.addStretch()

        # 手动输入框
        self.txt_code = QLineEdit()
        self.txt_code.setPlaceholderText("输入6位代码按回车添加...")
        self.txt_code.setFixedWidth(180)
        self.txt_code.returnPressed.connect(self._on_add_code_clicked)
        self.txt_code.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.txt_code.customContextMenuRequested.connect(self._show_code_context_menu)
        tb_layout.addWidget(self.txt_code)

        btn_add = QPushButton("➕ 添加")
        btn_add.clicked.connect(self._on_add_code_clicked)
        tb_layout.addWidget(btn_add)

        btn_tile_sbc = QPushButton("📈 一键平铺 SBC")
        btn_tile_sbc.setToolTip(
            "【一键平铺 SBC 走势图】\n"
            "• 支持在表格视图中直接点击单选，按住 Ctrl 单选/加选，按住 Shift 连续多选；\n"
            "• 点击将选中的所有标的在屏幕网格自动平铺盯盘 (未选择时默认平铺前 4 只)；\n"
            "• 快捷键: Q 键可随时重新平铺对齐所有已打开的 SBC 窗口。"
        )
        btn_tile_sbc.setStyleSheet("background-color: #1a3328; border-color: #00ff88; color: #00ff88; font-weight: bold;")
        btn_tile_sbc.clicked.connect(self._on_tile_sbc_clicked)
        tb_layout.addWidget(btn_tile_sbc)

        btn_refresh = QPushButton("🔄 立即刷新")
        btn_refresh.clicked.connect(self._on_refresh_clicked)
        tb_layout.addWidget(btn_refresh)

        btn_auto = QPushButton("⏳ 自动轮询: 关")
        btn_auto.setToolTip("开启/关闭后台自动延时轮询 (默认关闭，避免不停重刷)")
        btn_auto.setCheckable(True)
        btn_auto.setChecked(False)
        btn_auto.clicked.connect(self._on_toggle_auto_refresh)
        self.btn_auto = btn_auto
        tb_layout.addWidget(btn_auto)

        btn_perf = QPushButton("📊 性能日志: 关")
        btn_perf.setToolTip("开启/关闭控制台细粒度分组计算性能审计日志 (快捷键: L)")
        btn_perf.setCheckable(True)
        btn_perf.setChecked(self.perf_log_enabled)
        btn_perf.clicked.connect(self._on_toggle_perf_log)
        self.btn_perf = btn_perf
        tb_layout.addWidget(btn_perf)

        btn_clean = QPushButton("🧹 仅看预下单/启动")
        btn_clean.setCheckable(True)
        btn_clean.setChecked(False)
        btn_clean.toggled.connect(self._on_filter_toggled)
        self.btn_clean = btn_clean
        tb_layout.addWidget(btn_clean)

        btn_reset_default = QPushButton("🔄 重置新股池")
        btn_reset_default.setToolTip("重新从全市场拉取最新的全部新股与次新股")
        btn_reset_default.clicked.connect(self._on_reset_default_clicked)
        tb_layout.addWidget(btn_reset_default)

        btn_cmd_room = QPushButton("🚢 集中交易指挥室")
        btn_cmd_room.setToolTip("打开集中交易总指挥室：掌握全数据赛马天梯、持仓盈亏追踪、一键批量执行与全自动跟随交易")
        btn_cmd_room.setStyleSheet("background-color: #2b1f14; border-color: #ff9900; color: #ffaa00; font-weight: bold;")
        btn_cmd_room.clicked.connect(self._on_open_command_room)
        tb_layout.addWidget(btn_cmd_room)

        root_layout.addLayout(tb_layout)

        # ── 1.5 战情面板：全市场情绪风向标与集中交易调度总指挥 ──
        self.fleet_bar = QHBoxLayout()
        self.fleet_bar.setSpacing(6)

        self.lbl_market_sentiment = QLabel("🌐 大盘量能: 正在感知... | 新股梯队: 梯队升温中")
        self.lbl_market_sentiment.setStyleSheet("background-color: #161824; border: 1px solid #2f334d; border-radius: 4px; padding: 2px 8px; color: #ffcc00; font-weight: bold; font-size: 8.5pt;")
        self.fleet_bar.addWidget(self.lbl_market_sentiment)

        self.lbl_fleet_leader = QLabel("🥇 爆款领头羊: 计算中...")
        self.lbl_fleet_leader.setStyleSheet("background-color: #241c14; border: 1px solid #5c3a1e; border-radius: 4px; padding: 2px 8px; color: #ffaa00; font-weight: bold; font-size: 8.5pt;")
        self.fleet_bar.addWidget(self.lbl_fleet_leader)

        self.lbl_fleet_action = QLabel("🚢 集中交易决议: 紧盯 9:30-10:00 早鸟拔地而起 | 买错破 VWAP 立即出局")
        self.lbl_fleet_action.setStyleSheet("background-color: #122118; border: 1px solid #1e452e; border-radius: 4px; padding: 2px 8px; color: #00ff88; font-weight: bold; font-size: 8.5pt;")
        self.fleet_bar.addWidget(self.lbl_fleet_action)

        self.fleet_bar.addStretch()
        root_layout.addLayout(self.fleet_bar)

        # ── 2. 中部数据表格 (支持动态 ats_col、Ctrl/Shift 多选与上下翻页联动，与其他主力 Tab 100% 对齐) ──
        self.table = IPODetectorTableWidget(self)
        self.table.setCornerButtonEnabled(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(True)

        self._setup_table_headers()

        # 统一鼠标点击与键盘上下翻页联动 (彻底杜绝重复触发)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.cellClicked.connect(lambda r, c: self._trigger_linkage_for_row(r, force=False))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        root_layout.addWidget(self.table)

        # ── 2.5 底部实时性能审计控制台 (点击【📊 性能日志: 开】展开) ──
        self.txt_perf_console = QPlainTextEdit(self)
        self.txt_perf_console.setReadOnly(True)
        self.txt_perf_console.setMaximumHeight(150)
        self.txt_perf_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0b0c10;
                color: #66fcf1;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 8.5pt;
                border: 1px solid #1f2833;
                border-radius: 4px;
            }
        """)
        self.txt_perf_console.setVisible(self.perf_log_enabled)
        root_layout.addWidget(self.txt_perf_console)

        # 联动防抖机制 (20ms 防抖，支持鼠标单击行与键盘连续翻页)
        self._pending_linkage_row = -1
        self._pending_linkage_code = ""
        self._last_linkage_code = ""
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._linkage_timer.timeout.connect(self._fire_linkage_debounced)


        # ── 3. 底部快捷提示栏 ──
        bottom_bar = QHBoxLayout()
        lbl_hint = QLabel(
            "💡 [操盘手法则] 只捕捉在 VWAP 上的强势走势结构 | 预下单绝不大涨后追单 | 在 VWAP 走平 1~3 天潜伏蓄势 | 回踩不碰到是黄金启动点 | 跌破 VWAP 反抽仅为止损点\n"
            "⌨️ 快捷键: [双击行 / 空格] 调出 SBC 走势 | [F / 回车] 联动通达信 | [↑/↓/PgUp/PgDn] 上下翻页切图 | [L] 性能日志 | [Q] 重排 SBC | [Del] 移除股票"
        )
        lbl_hint.setStyleSheet("color: #8f939d; font-size: 8.5pt;")
        bottom_bar.addWidget(lbl_hint)
        root_layout.addLayout(bottom_bar)

        # 快捷键绑定
        QShortcut(QKeySequence("F"), self, self._on_shortcut_f_linkage)
        QShortcut(QKeySequence("L"), self, self._on_toggle_perf_log)
        QShortcut(QKeySequence("Q"), self, self._on_shortcut_q_rearrange)
        QShortcut(QKeySequence("Space"), self, self._on_shortcut_space_open_sbc)
        QShortcut(QKeySequence("Delete"), self, self._on_shortcut_delete)

    def _load_persisted_state(self):
        """从本地磁盘恢复上次保存的监控池、已计算信号全景数据与窗口位置 (支持冷启动 0 秒瞬间直出)"""
        cfg_file = get_ipo_detector_layout_file()
        codes = []
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    codes = data.get("monitored_codes", [])
                    geo = data.get("geometry")
                    if geo and isinstance(geo, dict):
                        self.setGeometry(
                            geo.get("x", 100),
                            geo.get("y", 100),
                            geo.get("width", 1180),
                            geo.get("height", 680)
                        )
                    self.perf_log_enabled = bool(data.get("perf_log_enabled", False))
                    if hasattr(self, "btn_perf"):
                        self.btn_perf.setChecked(self.perf_log_enabled)
                        if self.perf_log_enabled:
                            self.btn_perf.setText("📊 性能日志: 开")
                            self.btn_perf.setStyleSheet("background-color: #3d2f00; border-color: #ffd700; color: #ffd700; font-weight: bold;")
                        else:
                            self.btn_perf.setText("📊 性能日志: 关")
                            self.btn_perf.setStyleSheet("")

                    # ⚡ 冷启动核心：从持久化缓存中直接反序列化还原上次各标的的 VWAPDetectorSignal 信号全景
                    raw_sigs = data.get("cached_signals", {})
                    if isinstance(raw_sigs, dict):
                        for c_k, s_dict in raw_sigs.items():
                            if isinstance(s_dict, dict) and s_dict.get("code"):
                                try:
                                    sig_obj = VWAPDetectorSignal(
                                        code=str(s_dict.get("code")),
                                        name=str(s_dict.get("name", "")),
                                        price=float(s_dict.get("price", 0.0)),
                                        change_pct=float(s_dict.get("change_pct", 0.0)),
                                        vwap=float(s_dict.get("vwap", 0.0)),
                                        vwap_diff_pct=float(s_dict.get("vwap_diff_pct", 0.0)),
                                        structure_tag=str(s_dict.get("structure_tag", "常规")),
                                        consolidation_days=int(s_dict.get("consolidation_days", 0)),
                                        pullback_no_touch=bool(s_dict.get("pullback_no_touch", False)),
                                        is_above_vwap=bool(s_dict.get("is_above_vwap", False)),
                                        trend_support_level=float(s_dict.get("trend_support_level", 0.0)),
                                        trend_slope_deg=float(s_dict.get("trend_slope_deg", 0.0)),
                                        has_kline_launch_sig=bool(s_dict.get("has_kline_launch_sig", False)),
                                        trend_desc=str(s_dict.get("trend_desc", "")),
                                        signal_type=str(s_dict.get("signal_type", "WATCH")),
                                        signal_level=str(s_dict.get("signal_level", "⚪")),
                                        signal_desc=str(s_dict.get("signal_desc", "")),
                                        stop_loss_price=float(s_dict.get("stop_loss_price", 0.0)),
                                        update_time=str(s_dict.get("update_time", "")),
                                        extra_data=s_dict.get("extra_data", {})
                                    )
                                    self.signals_map[sig_obj.code] = sig_obj
                                except Exception:
                                    pass
            except Exception as e:
                logger.debug(f"加载持久化配置异常: {e}")

        # 严格过滤历史持久化配置中的未上市/未发行脏数据 (彻底剔除 920295, 301686 等)
        if codes:
            codes = [c for c in codes if is_stock_actually_listed(c)]

        # 🛡️ 智能自愈防护 (P0)：若本地配置中仅有 <= 2 只标的 (说明此前被未沙盒隔离的测试覆盖写入)，
        # 自动融合全市场 35 只新股次新股，恢复完整新股池！
        if len(codes) <= 2:
            default_codes = self._get_default_ipo_subnew_codes()
            for dc in default_codes:
                if dc not in codes:
                    codes.append(dc)

        # 若过滤后为空或无历史配置，默认加载系统真正已上市的次新股
        if not codes:
            codes = self._get_default_ipo_subnew_codes()

        self.monitored_codes = list(dict.fromkeys(codes))
        # 瞬间重建表格并填入已有的历史信号数据 (0秒直出)
        self._rebuild_table_rows()
        # 清洗并写回持久化配置
        self.save_persisted_state()

    def _get_default_ipo_subnew_codes(self) -> List[str]:
        """
        从 NewStockFetcher 中提取最新的全市场真正已上市的新股与次新股代码
        - 坚决杜绝未上市股票 (待上市/待申购/发行未上市) 进入超短检测池；
        - 按上市日期倒序排列，优先保留最新 35~40 只近期活跃次新标的。
        """
        res = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        try:
            fetcher = NewStockFetcher.get_instance()
            ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
            valid_items = []
            for c, v in ipo_dict.items():
                c_str = str(c).zfill(6)
                if not is_stock_actually_listed(c_str):
                    continue
                ld = str(v.get("listing_date") or "").strip()
                if ld and ld <= today_str and len(ld) >= 8:
                    valid_items.append((c_str, ld))

            # 按上市日期从最新到较早排序
            valid_items.sort(key=lambda x: x[1], reverse=True)
            for c_str, _ in valid_items:
                if c_str not in res:
                    res.append(c_str)

            # 提取 DataFrame 兜底补充
            df = fetcher.get_new_stocks_summary()
            if df is not None and not df.empty and "code" in df.columns:
                for idx, row in df.iterrows():
                    c_str = str(row["code"]).zfill(6)
                    if not is_stock_actually_listed(c_str):
                        continue
                    ld = str(row.get("listing_date") or "").strip()
                    if ld and ld <= today_str and len(ld) >= 8 and c_str not in res:
                        res.append(c_str)
        except Exception as e:
            logger.debug(f"获取全市场新股列表提示: {e}")

        # 兜底注入典型活跃标的 (含天海电子、频准激光、沈鼓集团等已上市标的)
        fallback = ["001365", "688826", "301677", "688835", "688801", "601091", "688837", "920298"]
        for fb in fallback:
            if fb not in res and is_stock_actually_listed(fb):
                res.append(fb)

        # 超短线聚焦：默认取最新上市的 35 只最活跃新股/次新股，极速秒级完成全表分析
        return res[:35] if len(res) > 35 else res

    def save_persisted_state(self):
        """集中持久化保存当前窗口几何、监控池与全量信号计算结果 (支持冷启动秒出)"""
        if hasattr(self, "table") and hasattr(self.table, "save_header_state"):
            self.table.save_header_state()
        cfg_file = get_ipo_detector_layout_file()
        # 序列化当前已算好的全量信号
        cached_sigs = {}
        for code, sig in self.signals_map.items():
            if sig:
                cached_sigs[code] = {
                    "code": sig.code,
                    "name": sig.name,
                    "price": sig.price,
                    "change_pct": sig.change_pct,
                    "vwap": sig.vwap,
                    "vwap_diff_pct": sig.vwap_diff_pct,
                    "structure_tag": sig.structure_tag,
                    "consolidation_days": sig.consolidation_days,
                    "pullback_no_touch": sig.pullback_no_touch,
                    "is_above_vwap": sig.is_above_vwap,
                    "trend_support_level": sig.trend_support_level,
                    "trend_slope_deg": sig.trend_slope_deg,
                    "has_kline_launch_sig": sig.has_kline_launch_sig,
                    "trend_desc": sig.trend_desc,
                    "signal_type": sig.signal_type,
                    "signal_level": sig.signal_level,
                    "signal_desc": sig.signal_desc,
                    "stop_loss_price": sig.stop_loss_price,
                    "update_time": sig.update_time,
                    "extra_data": getattr(sig, "extra_data", {}) or {}
                }

        data = {
            "monitored_codes": self.monitored_codes,
            "cached_signals": cached_sigs,
            "geometry": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height()
            },
            "perf_log_enabled": getattr(self, "perf_log_enabled", False),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        tmp_file = cfg_file + f".tmp_{os.getpid()}"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(tmp_file):
                os.replace(tmp_file, cfg_file)
        except Exception as e:
            logger.debug(f"保存检测工具配置异常: {e}")
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception:
                pass

    def add_stock(self, code: str):
        """添加股票到监控池 (自动置顶于首位)"""
        clean_code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        if not clean_code or len(clean_code) != 6:
            return
        if clean_code in self.monitored_codes:
            self.monitored_codes.remove(clean_code)
        self.monitored_codes.insert(0, clean_code)
        self._rebuild_table_rows()
        self.save_persisted_state()
        # 立即单只优先评估
        self._eval_single_code_now(clean_code)

    def remove_stock(self, code: str):
        """从监控池移除某只股票"""
        if code in self.monitored_codes:
            self.monitored_codes.remove(code)
            self.signals_map.pop(code, None)
            self._rebuild_table_rows()
            self.save_persisted_state()

    def _eval_single_code_now(self, code: str):
        """单只立即优先评估"""
        def _task():
            try:
                sig = IPOVWAPDetectorEngine.get_instance().analyze_stock(code, force_refresh=True)
                self.signals_map[code] = sig
                self._update_table_row_data(sig)
            except Exception:
                pass
        QTimer.singleShot(50, _task)

    def trigger_scan(self):
        """触发新一轮后台扫描"""
        if self.worker and self.worker.isRunning():
            return
        if not self.monitored_codes:
            self.lbl_status.setText("📊 监控池为空，请在上方输入代码添加或点击【重置新股池】")
            return

        self.lbl_status.setText(f"⏳ 正在扫描 {len(self.monitored_codes)} 只新股/次新股 VWAP 结构 (多进程批量+多线程并发)...")
        # 扫描期间全程保持表格物理行静止稳定，绝不打乱排序
        if self.table.isSortingEnabled():
            self.table.setSortingEnabled(False)
        self.worker = IPOScanWorker(self.monitored_codes, batch_size=8, perf_log_enabled=self.perf_log_enabled)
        self.worker.batch_analyzed.connect(self._on_batch_analyzed)
        self.worker.stock_analyzed.connect(self._on_stock_analyzed)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.perf_log_emitted.connect(self._on_perf_log_received)
        # 🛡️ 明确降级为 LowPriority，保障 GUI 主线程 60fps 丝滑响应，鼠标滚轮与键盘翻页零卡顿
        from PyQt6.QtCore import QThread
        self.worker.start(QThread.Priority.LowPriority)

    def _on_perf_log_received(self, text: str):
        """实时将后台 Worker 发送的分组性能审计日志打印并滚入内嵌控制台 (仅在开启模式下追加)"""
        if getattr(self, "perf_log_enabled", False) and hasattr(self, "txt_perf_console"):
            self.txt_perf_console.appendPlainText(text)
            self.txt_perf_console.ensureCursorVisible()

    def _on_batch_analyzed(self, batch_signals: List[VWAPDetectorSignal]):
        """【🚀 批量分组接收】整组多只信号批量压入平滑待渲染队列，彻底消灭单只零碎调度性能损耗"""
        for sig in batch_signals:
            self.signals_map[sig.code] = sig
            self._pending_render_queue.append(sig)
        if not self._render_timer.isActive():
            self._render_timer.start(40)

    def _on_stock_analyzed(self, sig: VWAPDetectorSignal):
        """单只兼容接收 (如手动单只优先评估)"""
        self.signals_map[sig.code] = sig
        self._pending_render_queue.append(sig)
        if not self._render_timer.isActive():
            self._render_timer.start(40)

    def _flush_pending_renders(self):
        """【🚀 分帧错峰原地平滑刷新】每 40ms 原地更新至多 8 只，原地 setText 与调色，全程冻结排序，消灭重排风暴"""
        if not self._pending_render_queue:
            self._render_timer.stop()
            return

        self._is_table_updating = True
        batch_size = 8
        try:
            for _ in range(min(batch_size, len(self._pending_render_queue))):
                sig = self._pending_render_queue.popleft()
                self._update_table_row_data(sig, manage_sorting=False)
        finally:
            self._is_table_updating = False

        if not self._pending_render_queue:
            self._render_timer.stop()

    def _on_scan_finished(self, count: int, cost: float, perf_summary: Optional[Dict[str, Any]] = None):
        # 若仍有排队渲染未完成，单次强制刷新剩余全部
        if self._pending_render_queue:
            try:
                while self._pending_render_queue:
                    sig = self._pending_render_queue.popleft()
                    self._update_table_row_data(sig, manage_sorting=False)
            finally:
                pass
            self._render_timer.stop()

        # 统一任务完成集中持久化 (5-10分钟统一持久化，绝不实时写盘)
        try:
            from ats.tdx_realtime_fetcher import TDXGlobalCachePool
            TDXGlobalCachePool.get_instance().flush_if_due(interval=300.0)
        except Exception:
            pass

        # 集中持久化当前监控池与全量信号计算结果，确保下次冷启动瞬间直出
        try:
            self.save_persisted_state()
        except Exception:
            pass

        # 统计高价值信号
        pre_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "PRE_ORDER")
        pull_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "PULLBACK_BUY")
        break_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "BREAKOUT")

        perf_text = ""
        if perf_summary:
            day_ms = perf_summary.get("day_ms", 0.0)
            bars_ms = perf_summary.get("bars_ms", 0.0)
            strat_ms = perf_summary.get("strat_ms", 0.0)
            batches = perf_summary.get("batches", 1)
            perf_text = f" | 批次: {batches}组 | 日线: {day_ms:.0f}ms | 分时: {bars_ms:.0f}ms"

        # 统一提交全池守护报告至集中交易调度中心，横向赛马冒泡排位，并刷新顶栏战情
        try:
            from ats.strategy.ipo_trading_center import IPOTradingCenter
            trading_center = IPOTradingCenter.get_instance()
            for s in self.signals_map.values():
                trading_center.submit_stock_perception_report(s)
            directives = trading_center.evaluate_fleet_and_generate_orders()
            fleet_summary = trading_center.get_fleet_summary()
            sentiment = trading_center.sentiment_engine.get_market_sentiment(list(self.signals_map.values()))

            if hasattr(self, "lbl_market_sentiment"):
                self.lbl_market_sentiment.setText(
                    f"🌐 大盘: {sentiment.index_phase} (量比{sentiment.sh_volume_ratio:.2f}) | "
                    f"新股梯队: {sentiment.heat_stage} (站稳率{sentiment.vwap_hold_ratio}%)"
                )
            if hasattr(self, "lbl_fleet_leader"):
                self.lbl_fleet_leader.setText(
                    f"🥇 爆款领头羊: {fleet_summary['top_leader_name']} ({fleet_summary['top_leader_score']}分)"
                )
            if hasattr(self, "lbl_fleet_action"):
                if directives:
                    top_d = directives[0]
                    self.lbl_fleet_action.setText(f"🎯 集中决议 [{top_d.action}]: {top_d.name} {top_d.reason[:32]}...")
                else:
                    self.lbl_fleet_action.setText("🚢 集中交易决议: 紧盯 9:30-10:00 早鸟拔地而起 | 买错破 VWAP 立即出局")
            
            # 原地更新全表各行的全局仲裁与操盘决议 (消除各管一摊、不知山外有山盲区)
            self._refresh_all_table_arbitrations()
        except Exception as e:
            logger.debug(f"更新集中交易调度战情异常: {e}")


        self.lbl_status.setText(
            f"✅ 监控中: {len(self.monitored_codes)} 只 | "
            f"🎯 预下单: {pre_cnt} 只 | 🚀 回踩启动: {pull_cnt} 只 | ⚡ 加速: {break_cnt} 只 | 耗时: {cost:.2f}s{perf_text}"
        )

        # 扫描结束统一按用户当前排序列整理一次，并精准记住操盘手多选列表与高亮行焦点
        selected_codes = []
        for idx in self.table.selectedIndexes():
            r = idx.row()
            it_c = self.table.item(r, 0)
            if it_c and it_c.text().strip():
                c_clean = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)
                if c_clean and c_clean not in selected_codes:
                    selected_codes.append(c_clean)

        current_code = ""
        cur_r = self.table.currentRow()
        if cur_r >= 0:
            it_c = self.table.item(cur_r, 0)
            if it_c:
                current_code = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)

        col = self.table.horizontalHeader().sortIndicatorSection()
        order = self.table.horizontalHeader().sortIndicatorOrder()
        self.table.setSortingEnabled(True)
        if col >= 0:
            self.table.sortItems(col, order)

        # 恢复操盘手多选选区与高亮行焦点
        if selected_codes:
            for r in range(self.table.rowCount()):
                it_c = self.table.item(r, 0)
                if it_c:
                    c_txt = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)
                    if c_txt in selected_codes:
                        self.table.selectRow(r)
        if current_code:
            for r in range(self.table.rowCount()):
                it_c = self.table.item(r, 0)
                if it_c:
                    c_txt = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)
                    if c_txt == current_code:
                        self.table.setCurrentCell(r, 0)
                        break

        # 只有在操盘手开启【⏳ 自动轮询: 开】时，才在上一轮全部完成 15 秒之后单次延时启动下一轮，绝不追尾抢跑！
        if getattr(self, "auto_refresh_enabled", False):
            self.refresh_timer.start(15000)

    def _on_refresh_clicked(self):
        """【🔄 立即刷新】清空底层全局历史静态缓存，强制全网重新同步全量最新数据"""
        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            TDXRealtimeFetcher.get_instance().invalidate_static_history_cache()
        except Exception:
            pass
        self.trigger_scan()

    def _on_toggle_auto_refresh(self, checked: bool):
        """【⏳ 自动轮询开关】切换是否后台延时自动轮询 (默认关闭，避免不停重刷)"""
        self.auto_refresh_enabled = checked
        if checked:
            self.btn_auto.setText("⏳ 自动轮询: 开")
            self.btn_auto.setStyleSheet("background-color: #1a3328; border-color: #00ff88; color: #00ff88; font-weight: bold;")
            if not (self.worker and self.worker.isRunning()):
                QTimer.singleShot(500, self.trigger_scan)
        else:
            self.btn_auto.setText("⏳ 自动轮询: 关")
            self.btn_auto.setStyleSheet("")
            if hasattr(self, "refresh_timer"):
                self.refresh_timer.stop()

    def _on_toggle_perf_log(self):
        """【📊 性能模式】切换控制台细粒度批次审计与耗时分析"""
        self.perf_log_enabled = not self.perf_log_enabled
        if hasattr(self, "txt_perf_console"):
            self.txt_perf_console.setVisible(self.perf_log_enabled)
            if self.perf_log_enabled and not self.txt_perf_console.toPlainText():
                self.txt_perf_console.appendPlainText("[IPO-PERF] 📊 性能审计日志模式已开启，等待下一批次扫描日志...")
        if self.worker and hasattr(self.worker, "perf_log_enabled"):
            self.worker.perf_log_enabled = self.perf_log_enabled
        if self.perf_log_enabled:
            self.btn_perf.setText("📊 性能日志: 开")
            self.btn_perf.setStyleSheet("background-color: #3d2f00; border-color: #ffd700; color: #ffd700; font-weight: bold;")
        else:
            self.btn_perf.setText("📊 性能日志: 关")
            self.btn_perf.setStyleSheet("")
        self.save_persisted_state()

    def _setup_table_headers(self):
        """动态配置表格列头与列宽 (与其他主力 Tab 100% 对齐，默认极窄模式，原生一体化丝滑拖拽)"""
        self.extra_cols = get_ipo_detector_extra_cols()
        headers = get_ipo_detector_table_headers(self.extra_cols)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        hv = self.table.horizontalHeader()
        hv.setSectionsClickable(True)
        hv.setSortIndicatorShown(True)
        try:
            hv.sectionClicked.disconnect()
        except Exception:
            pass
        hv.sectionClicked.connect(self._on_header_section_clicked)

        # 全面对齐全系统统一的标准 setup_persistence 与极窄模式 (彻底消除拖拽撕裂与分离延时)
        default_widths = get_ipo_detector_default_widths(self.extra_cols)
        self.table.setup_persistence(
            config_key="ats_ipo_subnew_detector_headers_v5",
            default_widths=default_widths
        )
        hv.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def _on_header_section_clicked(self, logical_index: int):
        """【📊 表头点击排序】支持全表高精度数值与文本升降序切换"""
        total_cols = self.table.columnCount()
        # 最后一列是操作按钮，不进行排序
        if logical_index >= total_cols - 1:
            return

        if getattr(self, "_current_sort_col", -1) == logical_index:
            # 同一列切换升降序
            if self._current_sort_order == Qt.SortOrder.DescendingOrder:
                self._current_sort_order = Qt.SortOrder.AscendingOrder
            else:
                self._current_sort_order = Qt.SortOrder.DescendingOrder
        else:
            self._current_sort_col = logical_index
            # 默认降序 (看涨跌幅、偏离度、连阳等更符合看盘习惯)
            self._current_sort_order = Qt.SortOrder.DescendingOrder

        self.table.horizontalHeader().setSortIndicator(self._current_sort_col, self._current_sort_order)
        self._apply_current_sort()

    def _apply_current_sort(self):
        """应用当前记录的排序列与排序方向"""
        col = getattr(self, "_current_sort_col", -1)
        if col < 0 or col >= self.table.columnCount() - 1:
            return
        if getattr(self, "_is_table_updating", False):
            return

        try:
            self.table.setSortingEnabled(True)
            self.table.sortItems(col, self._current_sort_order)
        except Exception as e:
            logger.debug(f"表格排序异常: {e}")

    def _rebuild_table_rows(self):
        """根据当前 monitored_codes 重建表格行"""
        self._is_table_updating = True
        self.table.setSortingEnabled(False)
        try:
            n_extra = len(self.extra_cols)
            total_cols = 13 + n_extra
            if self.table.columnCount() != total_cols:
                self.table.setColumnCount(total_cols)
                headers = get_ipo_detector_table_headers(self.extra_cols)
                self.table.setHorizontalHeaderLabels(headers)
            self.table.setRowCount(len(self.monitored_codes))

            for row, code in enumerate(self.monitored_codes):
                name = resolve_fast_ipo_name(code)
                self.table.setItem(row, 0, QTableWidgetItem(code))
                self.table.setItem(row, 1, QTableWidgetItem(name))
                for c in range(2, total_cols):
                    self.table.setItem(row, c, QTableWidgetItem("--"))

                # 操作按钮 (放于最后一列: 12 + n_extra)
                btn_box = QWidget()
                btn_l = QHBoxLayout(btn_box)
                btn_l.setContentsMargins(2, 1, 2, 1)
                btn_l.setSpacing(4)
                btn_sbc = QPushButton("📈 SBC")
                btn_sbc.setFixedWidth(54)
                btn_sbc.setStyleSheet("background-color: #1a2c3a; color: #00e5ff; font-weight: bold; padding: 2px 4px;")
                btn_sbc.clicked.connect(lambda _, c=code: self._open_sbc_for_code(c))
                btn_del = QPushButton("❌")
                btn_del.setFixedWidth(28)
                btn_del.setStyleSheet("background-color: #2b1d1d; color: #ff5555; padding: 2px 4px;")
                btn_del.clicked.connect(lambda _, c=code: self.remove_stock(c))
                btn_l.addWidget(btn_sbc)
                btn_l.addWidget(btn_del)
                self.table.setCellWidget(row, 12 + n_extra, btn_box)

                # 若已有信号数据，立即填充
                if code in self.signals_map:
                    self._update_table_row_data(self.signals_map[code], target_row=row, manage_sorting=False)

            self.table.setSortingEnabled(True)
            if len(self.monitored_codes) > 0 and self.table.currentRow() < 0:
                self.table.setCurrentCell(0, 0)
        finally:
            self._is_table_updating = False

    def _update_table_row_data(self, sig: VWAPDetectorSignal, target_row: Optional[int] = None, manage_sorting: bool = True):
        """【🛡️ 整行原子原地增量更新】复用已存在的单元格对象，纯原地 setText 与调色，消除全表排版与重绘风暴"""
        prev_updating = getattr(self, "_is_table_updating", False)
        self._is_table_updating = True
        was_sorting = self.table.isSortingEnabled() if manage_sorting else False
        if was_sorting:
            self.table.setSortingEnabled(False)
        try:
            row = target_row
            if row is None:
                # 动态精确匹配目标行
                for r in range(self.table.rowCount()):
                    item = self.table.item(r, 0)
                    if item and item.text().strip() == sig.code:
                        row = r
                        break
            if row is None or row >= self.table.rowCount():
                return

            # 同步最新名称
            if sig.name:
                it_name = self.table.item(row, 1)
                if it_name and it_name.text() != sig.name:
                    it_name.setText(sig.name)

            # 检查过滤
            if getattr(self, "btn_clean", None) and self.btn_clean.isChecked():
                is_valid_signal = (sig.signal_type in ("PRE_ORDER", "PULLBACK_BUY", "BREAKOUT"))
                self.table.setRowHidden(row, not is_valid_signal)

            # 辅助函数：原地复用或创建数值单元格
            def _set_numeric_cell(col_idx, val_str, raw_val, fg=None, bg=None):
                it = self.table.item(row, col_idx)
                if isinstance(it, IPONumericTableWidgetItem):
                    if it.text() != val_str:
                        it.setText(val_str)
                    it.raw_val = float(raw_val)
                    if fg is not None:
                        it.setForeground(fg)
                    if bg is not None:
                        it.setBackground(bg)
                else:
                    it = IPONumericTableWidgetItem(val_str, raw_val=float(raw_val))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if fg is not None:
                        it.setForeground(fg)
                    if bg is not None:
                        it.setBackground(bg)
                    self.table.setItem(row, col_idx, it)

            # 辅助函数：原地复用或创建文本单元格
            def _set_text_cell(col_idx, text_str, fg=None, bg=None, font=None, tooltip=None, align=None):
                it = self.table.item(row, col_idx)
                if it is not None:
                    if it.text() != text_str:
                        it.setText(text_str)
                    if fg is not None:
                        it.setForeground(fg)
                    if bg is not None:
                        it.setBackground(bg)
                    if font is not None:
                        it.setFont(font)
                    if tooltip is not None:
                        it.setToolTip(tooltip)
                    if align is not None:
                        it.setTextAlignment(align)
                else:
                    it = QTableWidgetItem(text_str)
                    if fg is not None:
                        it.setForeground(fg)
                    if bg is not None:
                        it.setBackground(bg)
                    if font is not None:
                        it.setFont(font)
                    if tooltip is not None:
                        it.setToolTip(tooltip)
                    if align is not None:
                        it.setTextAlignment(align)
                    self.table.setItem(row, col_idx, it)

            # 2. 现价
            p_str = f"{sig.price:.2f}" if sig.price > 0 else "--"
            _set_numeric_cell(2, p_str, float(sig.price) if sig.price > 0 else -999999.0)

            # 3. 涨跌幅
            chg_str = f"{sig.change_pct:+.2f}%" if sig.price > 0 else "--"
            chg_fg = QColor("#ff4444") if sig.change_pct > 0 else (QColor("#00ff88") if sig.change_pct < 0 else QColor("#e2e2e5"))
            _set_numeric_cell(3, chg_str, float(sig.change_pct) if sig.price > 0 else -999999.0, fg=chg_fg)

            # 4. 10d VWAP
            vw_str = f"{sig.vwap:.2f}" if sig.vwap > 0 else "--"
            _set_numeric_cell(4, vw_str, float(sig.vwap) if sig.vwap > 0 else -999999.0, fg=QColor("#ffcc00"))

            # 5. VWAP偏离
            diff_str = f"{sig.vwap_diff_pct:+.1f}%" if sig.vwap > 0 else "--"
            diff_fg = QColor("#ff8800") if sig.vwap_diff_pct > 0 else (QColor("#00bbff") if sig.vwap_diff_pct < 0 else QColor("#e2e2e5"))
            _set_numeric_cell(5, diff_str, float(sig.vwap_diff_pct) if sig.vwap > 0 else -999999.0, fg=diff_fg)

            # 6. VWAP结构形态 (融合赛马动能分与启动时点)
            struct_fg = QColor("#ffd700") if sig.consolidation_days >= 1 else (QColor("#00ff88") if sig.pullback_no_touch else QColor("#e2e2e5"))
            struct_font = QFont("Arial", 9, QFont.Weight.Bold) if (sig.consolidation_days >= 1 or sig.pullback_no_touch) else None
            display_struct = sig.structure_tag
            if getattr(sig, "horse_race_score", 0.0) > 0:
                t_str = getattr(sig, "launch_time_str", "")
                t_tag = f" {t_str}" if (t_str and t_str != "未启动") else ""
                display_struct = f"[{sig.horse_race_score:.0f}分{t_tag}] {sig.structure_tag}"
            _set_text_cell(6, display_struct, fg=struct_fg, font=struct_font)

            # 7. 大趋势K线状态
            trend_fg = QColor("#ff33aa") if sig.has_kline_launch_sig else QColor("#e2e2e5")
            _set_text_cell(7, sig.trend_desc or "--", fg=trend_fg)

            # 8. 信号评级 (融合赛马排位徽章与终极闭环信号)
            sig_fg = QColor("#ffd700")
            sig_bg = QColor("#2d2400")
            if sig.signal_type == "CLIMAX_EXIT" or getattr(sig, "is_climax_exit", False):
                sig_fg = QColor("#ff3333")
                sig_bg = QColor("#3d0b0b")
            elif sig.signal_type == "IPO_FIRST_BUY":
                sig_fg = QColor("#ff8800")
                sig_bg = QColor("#331800")
            elif sig.signal_type == "PULLBACK_BUY":
                sig_fg = QColor("#00ff88")
                sig_bg = QColor("#002d18")
            elif sig.signal_type == "BREAKOUT":
                sig_fg = QColor("#ff007f")
                sig_bg = QColor("#2d0015")
            elif sig.signal_type == "WEAK_EXIT":
                sig_fg = QColor("#ff5555")
                sig_bg = QColor("#2d1111")
            elif sig.signal_type == "WATCH":
                sig_fg = QColor("#ffffff")
                sig_bg = QColor("#1f2430")

            level_str = sig.signal_level
            hr_tier = getattr(sig, "horse_race_tier", "")
            if hr_tier and hr_tier not in ("⚪ 观察", "--") and hr_tier not in level_str:
                level_str = f"{hr_tier} {sig.signal_level}"
            _set_text_cell(8, level_str, fg=sig_fg, bg=sig_bg, font=QFont("Arial", 9, QFont.Weight.Bold))

            # 9. 极窄止损位
            sl_str = f"{sig.stop_loss_price:.2f}" if sig.stop_loss_price > 0 else "--"
            _set_numeric_cell(9, sl_str, float(sig.stop_loss_price) if sig.stop_loss_price > 0 else -999999.0, fg=QColor("#ff5555"))

            # ── 动态自定义列 (ats_col, 优先从 ATS 的 IPC df 提取，tdd 兜底) ──
            ipc_row = None
            if self.ipc_df is not None and not self.ipc_df.empty:
                c_clean = sig.code
                cand_idx = [c_clean, c_clean.lstrip('0'), f"sh{c_clean}", f"sz{c_clean}", f"bj{c_clean}"]
                for c_k in cand_idx:
                    if c_k in self.ipc_df.index:
                        try:
                            ipc_row = self.ipc_df.loc[c_k]
                            break
                        except Exception:
                            pass
                if ipc_row is None and 'code' in self.ipc_df.columns:
                    try:
                        matched = self.ipc_df[self.ipc_df['code'].astype(str).str.zfill(6) == c_clean]
                        if not matched.empty:
                            ipc_row = matched.iloc[0]
                    except Exception:
                        pass

            if ipc_row is not None and hasattr(ipc_row, "iloc") and len(ipc_row.shape) > 1:
                ipc_row = ipc_row.iloc[0]

            extra_mem_row = getattr(sig, "extra_data", None) or {}

            try:
                from JohnsonUtil import commonTips as cct
                cct_co2 = [str(x).lower() for x in (getattr(cct, 'co2int', []) or [])]
                co2int = set(cct_co2).union({"ch_tc2", "ch_bc2", "ch_nod", "pdays", "pbreak", "obs_d", "win", "red"})
                col_map = getattr(cct, 'vis_column_map', {}) or {}
            except Exception:
                co2int = {"ch_tc2", "ch_bc2", "ch_nod", "pdays", "pbreak", "obs_d", "win", "red"}
                col_map = {}

            n_extra = len(self.extra_cols)
            for i, c_name in enumerate(self.extra_cols):
                col_idx = 10 + i
                mapped_name = col_map.get(c_name, col_map.get(c_name.lower(), c_name))
                cand_keys = [c_name, c_name.lower(), c_name.upper()]
                if mapped_name and mapped_name not in cand_keys:
                    cand_keys.append(mapped_name)

                raw_c_val = None
                source_row = ipc_row if ipc_row is not None else extra_mem_row
                if source_row is not None and len(source_row) > 0:
                    for k in cand_keys:
                        if k in source_row:
                            raw_c_val = source_row.get(k)
                            break

                if raw_c_val is not None and not pd.isna(raw_c_val):
                    try:
                        num_v = float(raw_c_val)
                        if not (math.isnan(num_v) or math.isinf(num_v)):
                            if c_name.lower() in co2int:
                                int_v = int(num_v)
                                disp_str = f"+{int_v}" if int_v > 0 else f"{int_v}"
                                ext_fg = QColor("#ffd700") if (c_name.lower() == "ch_bc2" and int_v > 0) else (
                                    QColor("#ff4444") if (c_name.lower() in ("win", "red") and int_v > 0) else (
                                        QColor("#00ff88") if (c_name.lower() in ("win", "red") and int_v < 0) else QColor("#e2e2e5")
                                    )
                                )
                                _set_numeric_cell(col_idx, disp_str, float(int_v), fg=ext_fg)
                            else:
                                disp_str = f"{num_v:+.2f}"
                                ext_fg = QColor("#ff4444") if num_v > 0 else (QColor("#00ff88") if num_v < 0 else QColor("#8f939d"))
                                _set_numeric_cell(col_idx, disp_str, float(num_v), fg=ext_fg)
                        else:
                            _set_numeric_cell(col_idx, "--", -999999.0)
                    except Exception:
                        _set_text_cell(col_idx, str(raw_c_val), align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    _set_numeric_cell(col_idx, "--", -999999.0)

            # 为什么 / 操盘决议 (优先融合交易中心基于全数据的全局仲裁与山外有山决议)
            desc_text = getattr(sig, "global_arbitration_desc", "") or sig.signal_desc
            desc_fg = None
            role = getattr(sig, "global_fleet_role", "")
            if role == "CLIMAX_EXIT" or getattr(sig, "is_climax_exit", False):
                desc_fg = QColor("#ff4444")
            elif role == "STOP_LOSS" or sig.signal_type == "WEAK_EXIT":
                desc_fg = QColor("#ff5555")
            elif role == "LEADER" or sig.signal_type == "IPO_FIRST_BUY":
                desc_fg = QColor("#00ff88")
            elif role == "VANGUARD":
                desc_fg = QColor("#00e5ff")
            elif role == "FOLLOWER":
                desc_fg = QColor("#8f93a8")
            elif role == "ICE_ABORT":
                desc_fg = QColor("#66fcf1")
            elif getattr(sig, "horse_race_rank", 999) <= 2 and sig.is_above_vwap:
                desc_fg = QColor("#00ff88")
            _set_text_cell(10 + n_extra, desc_text, tooltip=desc_text, fg=desc_fg)


            # 更新时间
            _set_text_cell(11 + n_extra, sig.update_time or "--")
        finally:
            if was_sorting:
                self.table.setSortingEnabled(True)
            self._is_table_updating = prev_updating

    def _refresh_all_table_arbitrations(self):

        """【集中仲裁原地极速反哺】全池统筹完成后，原地极速更新全表各行操盘决议，彻底消除单股盲区"""
        n_extra = len(self.extra_cols)
        desc_col = 10 + n_extra
        was_sorting = self.table.isSortingEnabled()
        if was_sorting:
            self.table.setSortingEnabled(False)
        try:
            for r in range(self.table.rowCount()):
                it_c = self.table.item(r, 0)
                if not it_c:
                    continue
                code = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)
                sig = self.signals_map.get(code)
                if not sig:
                    continue
                desc_text = getattr(sig, "global_arbitration_desc", "") or sig.signal_desc
                desc_fg = None
                role = getattr(sig, "global_fleet_role", "")
                if role == "CLIMAX_EXIT" or getattr(sig, "is_climax_exit", False):
                    desc_fg = QColor("#ff4444")
                elif role == "STOP_LOSS" or sig.signal_type == "WEAK_EXIT":
                    desc_fg = QColor("#ff5555")
                elif role == "LEADER" or sig.signal_type == "IPO_FIRST_BUY":
                    desc_fg = QColor("#00ff88")
                elif role == "VANGUARD":
                    desc_fg = QColor("#00e5ff")
                elif role == "FOLLOWER":
                    desc_fg = QColor("#8f93a8")
                elif role == "ICE_ABORT":
                    desc_fg = QColor("#66fcf1")
                elif getattr(sig, "horse_race_rank", 999) <= 2 and sig.is_above_vwap:
                    desc_fg = QColor("#00ff88")
                
                it_desc = self.table.item(r, desc_col)
                if it_desc:
                    it_desc.setText(desc_text)
                    it_desc.setToolTip(desc_text)
                    if desc_fg:
                        it_desc.setForeground(desc_fg)
                else:
                    it_desc = QTableWidgetItem(desc_text)
                    it_desc.setToolTip(desc_text)
                    if desc_fg:
                        it_desc.setForeground(desc_fg)
                    self.table.setItem(r, desc_col, it_desc)
        finally:
            if was_sorting:
                self.table.setSortingEnabled(True)

    def _on_open_command_room(self):
        """【🚢 集中交易总指挥室】掌握全数据赛马天梯、持仓盈亏追踪、一键批量执行与全自动跟随交易"""
        try:
            from ats.ui.ipo_command_room_dialog import IPOCommandRoomDialog
            dlg = IPOCommandRoomDialog(self)
            dlg.exec()
        except Exception as e:
            logger.error(f"打开集中交易指挥室异常: {e}")

    def _open_sbc_for_code(self, code: str):

        """【📈 一键调出 SBC 走势】秒级打开 10d VWAP 分时图"""
        try:
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            dlg = open_sbc_chart_dialog(code=code, period_mode="10d")
            if dlg:
                dlg.show()
                dlg.raise_()
                dlg.activateWindow()
        except Exception as e:
            logger.error(f"打开 SBC 走势图异常: {e}")

    def _on_tile_sbc_clicked(self):
        """【📈 一键平铺 SBC】
        - 优先平铺操盘手在表格视图中主动选择的标的 (支持鼠标点击选择、Ctrl 单选/加选、Shift 连续范围多选)；
        - 若当前未选择任何行，自动平铺默认前 4 只标的 (信号优先，兜底前 4 只)；
        - 自动在当前屏幕进行整齐网格平铺重排对齐。
        """
        # 1. 优先获取操盘手在表格视图中主动选中的标的 (单选、Ctrl加选、Shift多选)
        selected_rows = sorted(list(set(idx.row() for idx in self.table.selectedIndexes())))
        selected_codes = []
        if selected_rows:
            for r in selected_rows:
                if not self.table.isRowHidden(r):
                    it_c = self.table.item(r, 0)
                    if it_c and it_c.text().strip():
                        c_clean = "".join(ch for ch in it_c.text().strip() if ch.isdigit()).zfill(6)
                        if c_clean and len(c_clean) == 6 and c_clean not in selected_codes:
                            selected_codes.append(c_clean)

        if selected_codes:
            candidates = selected_codes
            self.lbl_status.setText(f"📈 正在一键平铺操盘手选中的 {len(candidates)} 只标的 SBC 走势图...")
        else:
            # 2. 未选择任何行时回退默认逻辑：优先取排在前面有信号的最多 4 只标的，兜底取前 4 只
            candidates = []
            for c in self.monitored_codes:
                sig = self.signals_map.get(c)
                if sig and sig.signal_type in ("PRE_ORDER", "PULLBACK_BUY", "BREAKOUT"):
                    candidates.append(c)
            if not candidates:
                candidates = self.monitored_codes[:4]
            else:
                candidates = candidates[:4]
            self.lbl_status.setText(f"📈 正在一键平铺默认关注的 {len(candidates)} 只标的 SBC 走势图...")

        if not candidates:
            return

        from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog, rearrange_all_sbc_windows
        for c in candidates:
            dlg = open_sbc_chart_dialog(code=c, period_mode="10d")
            if dlg:
                dlg.show()

        # 短暂延时自动在屏幕网格平铺重排
        QTimer.singleShot(250, rearrange_all_sbc_windows)

    def _on_filter_toggled(self, checked: bool):
        """过滤仅看有预下单/启动信号标的"""
        for r in range(self.table.rowCount()):
            it_code = self.table.item(r, 0)
            if it_code:
                c = it_code.text()
                sig = self.signals_map.get(c)
                if checked:
                    is_valid = (sig is not None and sig.signal_type in ("PRE_ORDER", "PULLBACK_BUY", "BREAKOUT"))
                    self.table.setRowHidden(r, not is_valid)
                else:
                    self.table.setRowHidden(r, False)

    def _show_code_context_menu(self, pos):
        """【📋 代码输入框右键快捷菜单】支持右键一键粘贴并清洗股票代码、一键粘贴并添加"""
        menu = QMenu(self.txt_code)
        menu.setStyleSheet("""
            QMenu { background-color: #0f172a; color: #f8fafc; border: 1px solid #334155; padding: 4px; font-size: 9pt; }
            QMenu::item:selected { background-color: #1e293b; color: #38bdf8; }
            QMenu::separator { height: 1px; background-color: #334155; margin: 3px 0; }
        """)

        # 检查系统剪贴板内容
        clipboard = QApplication.clipboard()
        clip_text = clipboard.text().strip() if clipboard else ""

        # 智能提取股票代码 (优先提取连续数字)
        digits_only = "".join(filter(str.isdigit, clip_text))
        extracted_code = ""
        if len(digits_only) == 6:
            extracted_code = digits_only
        elif len(digits_only) > 6:
            extracted_code = digits_only[:6]

        # 1. 粘贴股票代码选项
        if extracted_code:
            act_paste_code = menu.addAction(f"📋 粘贴股票代码: {extracted_code}")
            act_paste_code.triggered.connect(lambda: self._paste_code_to_input(extracted_code))

            act_paste_and_add = menu.addAction(f"➕ 粘贴并立即添加 ({extracted_code})")
            act_paste_and_add.triggered.connect(lambda: self._paste_and_add_code(extracted_code))
            menu.addSeparator()
        elif clip_text:
            display_text = clip_text if len(clip_text) <= 10 else f"{clip_text[:10]}..."
            act_paste_text = menu.addAction(f"📋 粘贴剪贴板内容 ({display_text})")
            act_paste_text.triggered.connect(self.txt_code.paste)
            menu.addSeparator()
        else:
            act_paste_empty = menu.addAction("📋 粘贴 (剪贴板为空)")
            act_paste_empty.setEnabled(False)
            menu.addSeparator()

        # 2. 基础编辑操作 (复制/剪切/全选/清空)
        has_selection = self.txt_code.hasSelectedText()
        has_text = bool(self.txt_code.text().strip())

        act_copy = menu.addAction("📑 复制 (Copy)")
        act_copy.setEnabled(has_selection or has_text)
        act_copy.triggered.connect(lambda: self.txt_code.copy() if has_selection else (clipboard.setText(self.txt_code.text()) if clipboard else None))

        act_cut = menu.addAction("✂️ 剪切 (Cut)")
        act_cut.setEnabled(has_selection)
        act_cut.triggered.connect(self.txt_code.cut)

        act_select_all = menu.addAction("🔘 全选 (Select All)")
        act_select_all.setEnabled(has_text)
        act_select_all.triggered.connect(self.txt_code.selectAll)

        menu.addSeparator()
        act_clear = menu.addAction("🧹 清空输入框")
        act_clear.setEnabled(has_text)
        act_clear.triggered.connect(self.txt_code.clear)

        menu.exec(self.txt_code.mapToGlobal(pos))

    def _paste_code_to_input(self, code: str):
        """将提取的代码填入输入框并聚焦"""
        self.txt_code.setText(code)
        self.txt_code.setFocus()
        self.txt_code.selectAll()

    def _paste_and_add_code(self, code: str):
        """将提取的代码填入并立即添加到监控池"""
        self.txt_code.setText(code)
        self._on_add_code_clicked()

    def _on_add_code_clicked(self):
        raw = self.txt_code.text().strip()
        if raw:
            self.add_stock(raw)
            self.txt_code.clear()

    def _on_reset_default_clicked(self):
        codes = self._get_default_ipo_subnew_codes()
        self.monitored_codes = list(dict.fromkeys(codes))
        self._rebuild_table_rows()
        self.save_persisted_state()
        self.trigger_scan()

    def _on_table_double_clicked(self, row: int, col: int):
        it = self.table.item(row, 0)
        if it:
            code = it.text().strip()
            self._open_sbc_for_code(code)

    def _on_shortcut_space_open_sbc(self):
        row = self.table.currentRow()
        if row >= 0:
            it = self.table.item(row, 0)
            if it:
                self._open_sbc_for_code(it.text().strip())

    def _broadcast_link_external(self, code: str):
        """联动外部通达信/同花顺终端"""
        try:
            from linkage_service import get_link_manager
            lm = get_link_manager()
            if lm:
                clean_c = "".join(c for c in str(code) if c.isdigit()).zfill(6)
                lm.push(clean_c, flags={'tdx': True, 'ths': True, 'dfcf': False}, auto=False)
        except Exception as e:
            logger.debug(f"[IPODetector] 外部联动异常: {e}")

    def _on_shortcut_f_linkage(self):
        """按 F 键联动外部行情软件 (通达信等)"""
        row = self.table.currentRow()
        if row >= 0:
            it = self.table.item(row, 0)
            if it:
                code = it.text().strip()
                self._broadcast_link_external(code)
                self.lbl_status.setText(f"🔗 已联动外部通达信/同花顺: {code}")

    def _on_shortcut_q_rearrange(self):
        """按 Q 键重排桌面所有 SBC 窗口"""
        try:
            from ats.ui.intraday_strategy_dialog import rearrange_all_sbc_windows
            rearrange_all_sbc_windows()
        except Exception:
            pass

    def _on_shortcut_delete(self):
        row = self.table.currentRow()
        if row >= 0:
            it = self.table.item(row, 0)
            if it:
                self.remove_stock(it.text().strip())

    def _find_next_visible_row(self, start_row: int, target_row: int, forward: bool = True) -> int:
        """寻找目标位置最近的未隐藏行 (完美兼容过滤模式)"""
        total = self.table.rowCount()
        if total <= 0:
            return -1
        if 0 <= target_row < total and not self.table.isRowHidden(target_row):
            return target_row
        step = 1 if forward else -1
        r = target_row
        while 0 <= r < total:
            if not self.table.isRowHidden(r):
                return r
            r += step
        r = target_row - step
        while 0 <= r < total:
            if not self.table.isRowHidden(r):
                return r
            r -= step
        return start_row

    def _handle_navigation_key(self, key) -> bool:
        """统一键盘上下翻页导航计算 (Up/Down/PageUp/PageDown)"""
        total_rows = self.table.rowCount()
        if total_rows <= 0:
            return False

        curr_row = self.table.currentRow()
        if curr_row < 0:
            curr_row = 0

        # 估算一页可见行数 (视口高度 / 行高，默认至少 4 行)
        row_h = self.table.rowHeight(0) if self.table.rowHeight(0) > 0 else 28
        visible_rows = max(3, self.table.viewport().height() // row_h)

        if key == Qt.Key.Key_Up:
            candidate = max(0, curr_row - 1)
            target_row = self._find_next_visible_row(curr_row, candidate, forward=False)
        elif key == Qt.Key.Key_Down:
            candidate = min(total_rows - 1, curr_row + 1)
            target_row = self._find_next_visible_row(curr_row, candidate, forward=True)
        elif key == Qt.Key.Key_PageUp:
            candidate = max(0, curr_row - visible_rows)
            target_row = self._find_next_visible_row(curr_row, candidate, forward=False)
        elif key == Qt.Key.Key_PageDown:
            candidate = min(total_rows - 1, curr_row + visible_rows)
            target_row = self._find_next_visible_row(curr_row, candidate, forward=True)
        else:
            return False

        if target_row >= 0:
            self.table.setCurrentCell(target_row, 0)
            item = self.table.item(target_row, 0)
            if item:
                self.table.scrollToItem(item)
            self._trigger_linkage_for_row(target_row, force=False)
            return True
        return False

    def keyPressEvent(self, event):
        """主窗口级别键盘导航支持：无论焦点在何处，均可按 Up/Down/PageUp/PageDown 上下翻页"""
        # 若焦点在输入框且正在打字，不拦截普通按键，仅拦截 Escape 键回切表格
        if hasattr(self, "txt_code") and self.txt_code.hasFocus():
            if event.key() == Qt.Key.Key_Escape:
                self.table.setFocus()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            if self._handle_navigation_key(key):
                event.accept()
                return
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            curr = self.table.currentRow()
            if curr >= 0:
                self._trigger_linkage_for_row(curr, force=True)
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_current_cell_changed(self, currentRow: int, currentColumn: int, previousRow: int, previousColumn: int):
        """鼠标单击行或键盘上下翻页移动行时触发联动 (严格过滤更新中与同列内切换)"""
        if getattr(self, "_is_table_updating", False) or currentRow < 0:
            return
        if currentRow == previousRow:
            return
        self._trigger_linkage_for_row(currentRow, force=False)

    def _trigger_linkage_for_row(self, row: int, force: bool = False):
        """
        统一且防重的极速联动触发入口 (鼠标点击、键盘上下翻页、回车等全部统一由此分发)
        - 严格执行四重铁壁防重：更新期拦截、代码相同拦截、同行切列拦截、20ms 防抖合并；
        - 彻底杜绝出现重复触发联动。
        """
        if getattr(self, "_is_table_updating", False) or row < 0 or row >= self.table.rowCount():
            return
        it_code = self.table.item(row, 0)
        if not it_code:
            return
        code = it_code.text().strip()
        clean_code = "".join(c for c in code if c.isdigit()).zfill(6)
        if not clean_code or len(clean_code) != 6:
            return

        # 严密防重：若与上一次联动的标的一致且非强制，坚决阻断重复触发联动！
        if not force and clean_code == self._last_linkage_code:
            return

        self._pending_linkage_row = row
        self._pending_linkage_code = clean_code
        self._linkage_timer.start(20)

    def _fire_linkage_debounced(self):
        """20ms 防抖最终落地联动 (消灭连续按键/翻页过程中的重复/雪崩式触发)"""
        if getattr(self, "_is_table_updating", False):
            return
        code = getattr(self, "_pending_linkage_code", "")
        row = getattr(self, "_pending_linkage_row", -1)
        if not code or row < 0 or row >= self.table.rowCount():
            return
        if code == self._last_linkage_code:
            return

        self._last_linkage_code = code

        it_name = self.table.item(row, 1)
        name = it_name.text().strip() if it_name else ""

        # 联动外部通达信/同花顺终端 (严格对齐 ATS: 仅切图，绝不触发异动管道或弹窗)
        self._broadcast_link_external(code)
        self.lbl_status.setText(f"🔗 已联动通达信/同花顺: {code} ({name})")

    def _show_context_menu(self, pos):
        """右键弹出 ATS 核心基础功能菜单"""
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        it_code = self.table.item(row, 0)
        it_name = self.table.item(row, 1)
        if not it_code:
            return
        code = it_code.text().strip()
        name = it_name.text().strip() if it_name else ""
        code_clean = "".join(c for c in code if c.isdigit()).zfill(6)
        if not code_clean:
            return

        from global_favorites import GlobalFavoriteManager

        fav_mgr = GlobalFavoriteManager()
        is_fav = code_clean in fav_mgr.get_favorite_stocks()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                border: 1px solid #2e2e36;
                color: #e2e2e5;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2c2c35;
                color: #00e5ff;
            }
        """)

        # 1. 复制股票代码
        copy_label = f"📋 复制股票代码 {code_clean}"
        if name:
            copy_label += f" ({name})"
        act_copy = QAction(copy_label, self)
        def _copy():
            cb = QApplication.clipboard()
            if cb:
                cb.setText(code_clean)
                self.lbl_status.setText(f"📋 已复制股票代码: {code_clean}")
        act_copy.triggered.connect(_copy)
        menu.addAction(act_copy)

        menu.addSeparator()

        # 2. ⚡ 发送到异动联动
        act_pipe = QAction(f"⚡ 发送到异动联动 ({code_clean})", self)
        def _trigger_pipe():
            def _async_send():
                try:
                    from ats.ui.base_table import send_to_linkage
                    send_to_linkage(code_clean, name, self)
                except Exception as e_pipe:
                    logger.debug(f"异步发送异动联动异常: {e_pipe}")
            import threading
            threading.Thread(target=_async_send, daemon=True).start()
            self.lbl_status.setText(f"⚡ 已发送异动联动: {code_clean}")
        act_pipe.triggered.connect(_trigger_pipe)
        menu.addAction(act_pipe)

        # 3. 📈 使用 SBC 打开独立分时图
        act_sbc = QAction(f"📈 调出 SBC 10d VWAP 走势 ({code_clean})", self)
        act_sbc.triggered.connect(lambda: self._open_sbc_for_code(code_clean))
        menu.addAction(act_sbc)

        # 3.1 📈 一键平铺选中的所有 SBC (当操盘手 Ctrl/Shift 多选了多只标的时直通一键平铺)
        selected_rows = sorted(list(set(idx.row() for idx in self.table.selectedIndexes())))
        sel_codes = []
        for r in selected_rows:
            if not self.table.isRowHidden(r):
                it = self.table.item(r, 0)
                if it and it.text().strip():
                    c_c = "".join(ch for ch in it.text().strip() if ch.isdigit()).zfill(6)
                    if c_c and len(c_c) == 6 and c_c not in sel_codes:
                        sel_codes.append(c_c)
        if len(sel_codes) > 1:
            act_tile_sel = QAction(f"📈 一键平铺选中的 {len(sel_codes)} 只标的 SBC 走势图", self)
            act_tile_sel.triggered.connect(self._on_tile_sbc_clicked)
            menu.addAction(act_tile_sel)

        # 4. 🎯 联动外部通达信/同花顺
        act_link = QAction(f"🎯 联动外部通达信/同花顺 ({code_clean})", self)
        def _link_external():
            self._broadcast_link_external(code_clean)
            self.lbl_status.setText(f"🎯 已联动通达信: {code_clean}")
        act_link.triggered.connect(_link_external)
        menu.addAction(act_link)

        # 5. 🧬 调出 DNA 特征审计报告
        act_dna = QAction(f"🧬 调出 {name or code_clean} DNA 特征审计报告", self)
        def _open_dna():
            try:
                from ats.ui.multi_period_dialog import run_dna_audit_batch_qt
                run_dna_audit_batch_qt({code_clean: name}, parent=self.window())
            except Exception as e_dna:
                logger.error(f"DNA 审计唤起异常: {e_dna}")
        act_dna.triggered.connect(_open_dna)
        menu.addAction(act_dna)

        menu.addSeparator()

        # 6. ⭐ 设为重点关注 / 取消重点关注
        fav_label = f"❌ 取消重点关注 {code_clean}" if is_fav else f"⭐ 设为重点关注 {code_clean}"
        act_fav = QAction(fav_label, self)
        def _toggle_fav():
            if is_fav:
                fav_mgr.remove_favorite(code_clean)
                self.lbl_status.setText(f"已移出重点关注: {code_clean}")
            else:
                fav_mgr.add_favorite(code_clean)
                self.lbl_status.setText(f"⭐ 已加入重点关注: {code_clean}")
        act_fav.triggered.connect(_toggle_fav)
        menu.addAction(act_fav)

        menu.addSeparator()

        # 7. ❌ 从当前超短检测池移除
        act_remove = QAction(f"❌ 从超短检测池移除 {code_clean}", self)
        act_remove.triggered.connect(lambda: self.remove_stock(code_clean))
        menu.addAction(act_remove)

        # 8. ↔️ 一键自适应全列宽
        menu.addSeparator()
        act_fit = QAction("↔️ 一键自适应全列宽", self)
        act_fit.triggered.connect(self._auto_fit_columns)
        menu.addAction(act_fit)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _auto_fit_columns(self):
        """自适应调整表格所有列宽，确保全列保持 Interactive 自由拖拽并自动持久化"""
        self.table.resizeColumnsToContents()
        hv = self.table.horizontalHeader()
        for i in range(self.table.columnCount()):
            hv.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        if hasattr(self.table, "save_header_state"):
            self.table.save_header_state()

    def _on_ipc_poll_and_heartbeat(self):
        """消费来自 ATS 跨进程一键发送过来的新代码，同步 IPC 数据并更新心跳"""
        # 1. 维护心跳
        update_detector_heartbeat(os.getpid())

        # 2. 🛡️【父进程存活心跳守护】：检测 ATS_MAIN_PID，若主进程已退出，本子进程 0.5s 安全退出
        main_pid_str = os.environ.get("ATS_MAIN_PID", "")
        if main_pid_str and main_pid_str.isdigit():
            main_pid = int(main_pid_str)
            is_parent_alive = True
            if sys.platform == "win32":
                try:
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    SYNCHRONIZE = 0x00100000
                    h_proc = kernel32.OpenProcess(SYNCHRONIZE, False, main_pid)
                    if h_proc:
                        kernel32.CloseHandle(h_proc)
                    else:
                        is_parent_alive = False
                except Exception:
                    pass
            else:
                try:
                    os.kill(main_pid, 0)
                except OSError:
                    is_parent_alive = False

            if not is_parent_alive:
                logger.info(f"[IPODetector] 监测到 ATS 主进程 (PID={main_pid}) 已注销，子进程立即安全持久化并退出")
                self.close()
                return

        # 3. 消费跨进程待添加队列
        new_stocks = pop_queued_stocks()
        if new_stocks:
            for s in new_stocks:
                self.add_stock(s)
            self.lbl_status.setText(f"⚡ 收到来自 ATS 跨进程发送的标的: {', '.join(new_stocks)}")

        # 4. 检查 ats_col 动态配置是否热变动
        cur_extra = get_ipo_detector_extra_cols()
        if getattr(self, "extra_cols", None) != cur_extra:
            self._setup_table_headers()
            self._rebuild_table_rows()

        # 5. 从全局 IPC 同步管理器获取最新实时行情快照 (实时回补连阳/DFF/ch_bc2等自定义列)
        if getattr(self, "ipc_mgr", None):
            try:
                df_now = self.ipc_mgr.get_current_df()
                if df_now is not None and not df_now.empty and len(df_now) > 100:
                    was_empty = (self.ipc_df is None or self.ipc_df.empty)
                    self.ipc_df = df_now
                    # 若首次拿到实时行情，且表格已有行，触发快速刷新回补自定义列
                    if was_empty and self.table.rowCount() > 0 and not getattr(self, "_is_table_updating", False):
                        for r in range(self.table.rowCount()):
                            it_c = self.table.item(r, 0)
                            if it_c:
                                cd = it_c.text().strip()
                                if cd in self.signals_map:
                                    self._update_table_row_data(self.signals_map[cd], target_row=r, manage_sorting=False)
            except Exception as e_ipcdf:
                logger.debug(f"从 IPC 获取实时行情异常: {e_ipcdf}")



    def closeEvent(self, event):
        """窗口关闭时集中保存配置"""
        if hasattr(self, "_render_timer") and self._render_timer.isActive():
            self._render_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(500)
        self.save_persisted_state()
        super().closeEvent(event)
