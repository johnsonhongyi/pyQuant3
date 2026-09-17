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
import logging
from typing import List, Dict, Optional, Set

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QShortcut

from concurrent.futures import ThreadPoolExecutor, as_completed

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


class IPOScanWorker(QThread):
    """【🚀 8路高并发分析 Worker】并发多只一起跑策略，极限性能秒级完成"""
    stock_analyzed = pyqtSignal(object)  # VWAPDetectorSignal
    scan_finished = pyqtSignal(int, float)  # 总数, 耗时秒

    def __init__(self, codes: List[str]):
        super().__init__()
        self.codes = list(codes)
        self.is_running = True
        self.engine = IPOVWAPDetectorEngine.get_instance()

    def run(self):
        t0 = time.time()
        count = 0
        if not self.codes:
            self.scan_finished.emit(0, 0.0)
            return

        workers = min(8, max(2, len(self.codes)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_code = {executor.submit(self._analyze_one, c): c for c in self.codes}
            for fut in as_completed(future_to_code):
                if not self.is_running:
                    break
                try:
                    sig = fut.result()
                    if sig:
                        self.stock_analyzed.emit(sig)
                        count += 1
                except Exception as e:
                    logger.debug(f"并发分析单股异常: {e}")

        cost = time.time() - t0
        self.scan_finished.emit(count, cost)

    def _analyze_one(self, code: str) -> Optional[VWAPDetectorSignal]:
        if not self.is_running:
            return None
        return self.engine.analyze_stock(code)

    def stop(self):
        self.is_running = False


class IPOSubnewDetectorDialog(QMainWindow):
    """新股次新股超短检测独立主窗口"""

    def __init__(self, initial_code: Optional[str] = None):
        super().__init__(None)

        self.setWindowTitle("🎯 ATS 新股次新股超短检测工具 (SBC 极限 10日 VWAP 预判与异动引擎)")
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
                border: 1px solid #232332;
                gridline-color: #1c1c28;
                color: #ffffff;
                font-size: 9pt;
                selection-background-color: #2b3145;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1a1a26;
                color: #9aa0a6;
                padding: 4px;
                border: 1px solid #232332;
                font-weight: bold;
                font-size: 9pt;
            }
        """)

        # 监控代码集合 (保序)
        self.monitored_codes: List[str] = []
        self.signals_map: Dict[str, VWAPDetectorSignal] = {}

        # 扫描线程
        self.worker: Optional[IPOScanWorker] = None

        self._init_ui()
        self._load_persisted_state()

        if initial_code:
            self.add_stock(initial_code)

        # 1. IPC 接收与心跳守护定时器 (300ms)
        self.ipc_timer = QTimer(self)
        self.ipc_timer.timeout.connect(self._on_ipc_poll_and_heartbeat)
        self.ipc_timer.start(300)

        # 2. 定期自动刷新轮询定时器 (默认 8 秒一轮)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.trigger_scan)
        self.refresh_timer.start(8000)

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
        tb_layout.addWidget(self.txt_code)

        btn_add = QPushButton("➕ 添加")
        btn_add.clicked.connect(self._on_add_code_clicked)
        tb_layout.addWidget(btn_add)

        btn_tile_sbc = QPushButton("📈 一键平铺 SBC")
        btn_tile_sbc.setToolTip("将当前前 4 只标的以 SBC 走势窗口在屏幕平铺盯盘 (按 Q 重排)")
        btn_tile_sbc.setStyleSheet("background-color: #1a3328; border-color: #00ff88; color: #00ff88; font-weight: bold;")
        btn_tile_sbc.clicked.connect(self._on_tile_sbc_clicked)
        tb_layout.addWidget(btn_tile_sbc)

        btn_refresh = QPushButton("🔄 立即刷新")
        btn_refresh.clicked.connect(self.trigger_scan)
        tb_layout.addWidget(btn_refresh)

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

        root_layout.addLayout(tb_layout)

        # ── 2. 中部数据表格 ──
        self.table = QTableWidget()
        self.table.setColumnCount(13)
        headers = [
            "代码", "名称", "现价", "涨跌幅", "10d VWAP", "VWAP偏离",
            "VWAP结构形态", "大趋势K线状态", "信号评级", "极窄止损位",
            "操作建议 / 为什么 (预下单逻辑)", "更新时间", "快捷操作"
        ]
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)
        self.table.setSortingEnabled(True)

        # 列宽策略
        hv = self.table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)
        hv.setSectionResizeMode(11, QHeaderView.ResizeMode.ResizeToContents)
        hv.setSectionResizeMode(12, QHeaderView.ResizeMode.ResizeToContents)

        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        root_layout.addWidget(self.table)

        # ── 3. 底部快捷提示栏 ──
        bottom_bar = QHBoxLayout()
        lbl_hint = QLabel(
            "💡 [操盘手法则] 只捕捉在 VWAP 上的强势走势结构 | 预下单绝不大涨后追单 | 在 VWAP 走平 1~3 天潜伏蓄势 | 回踩不碰到是黄金启动点 | 跌破 VWAP 反抽仅为止损点\n"
            "⌨️ 快捷键: [双击行 / 空格] 调出 SBC 走势 | [F] 联动通达信 | [Q] 重排 SBC 窗口 | [Del] 移除当前股票"
        )
        lbl_hint.setStyleSheet("color: #8f939d; font-size: 8.5pt;")
        bottom_bar.addWidget(lbl_hint)
        root_layout.addLayout(bottom_bar)

        # 快捷键绑定
        QShortcut(QKeySequence("F"), self, self._on_shortcut_f_linkage)
        QShortcut(QKeySequence("Q"), self, self._on_shortcut_q_rearrange)
        QShortcut(QKeySequence("Space"), self, self._on_shortcut_space_open_sbc)
        QShortcut(QKeySequence("Delete"), self, self._on_shortcut_delete)

    def _load_persisted_state(self):
        """从本地磁盘恢复上次保存的监控池与窗口位置"""
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
            except Exception as e:
                logger.debug(f"加载持久化配置异常: {e}")

        # 若无历史配置，默认加载系统新股与次新股
        if not codes:
            codes = self._get_default_ipo_subnew_codes()

        self.monitored_codes = list(dict.fromkeys(codes))
        self._rebuild_table_rows()

    def _get_default_ipo_subnew_codes(self) -> List[str]:
        """从 NewStockFetcher 中提取最新的全市场新股与次新股代码"""
        res = []
        try:
            fetcher = NewStockFetcher.get_instance()
            # 优先使用已缓存的 IPO 字典
            ipo_dict = getattr(fetcher, "_cached_ipo_dict", {})
            if ipo_dict:
                for c in ipo_dict.keys():
                    c_str = str(c).zfill(6)
                    if c_str not in res:
                        res.append(c_str)
            # 尝试提取 DataFrame
            df = fetcher.get_new_stocks_summary()
            if df is not None and not df.empty and "code" in df.columns:
                for c in df["code"]:
                    c_str = str(c).zfill(6)
                    if c_str not in res:
                        res.append(c_str)
        except Exception as e:
            logger.debug(f"获取全市场新股列表提示: {e}")

        # 兜底注入典型活跃标的 (含天海电子等)
        fallback = ["001365", "688826", "301677", "688835", "688801", "601091", "920295"]
        for fb in fallback:
            if fb not in res:
                res.append(fb)
        return res

    def save_persisted_state(self):
        """集中持久化保存当前窗口几何与监控池"""
        cfg_file = get_ipo_detector_layout_file()
        data = {
            "monitored_codes": self.monitored_codes,
            "geometry": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height()
            },
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"保存检测工具配置异常: {e}")

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

        self.lbl_status.setText(f"⏳ 正在扫描 {len(self.monitored_codes)} 只新股/次新股 VWAP 结构...")
        self.worker = IPOScanWorker(self.monitored_codes)
        self.worker.stock_analyzed.connect(self._on_stock_analyzed)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.start()

    def _on_stock_analyzed(self, sig: VWAPDetectorSignal):
        self.signals_map[sig.code] = sig
        self._update_table_row_data(sig)

    def _on_scan_finished(self, count: int, cost: float):
        # 统计高价值信号
        pre_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "PRE_ORDER")
        pull_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "PULLBACK_BUY")
        break_cnt = sum(1 for s in self.signals_map.values() if s.signal_type == "BREAKOUT")

        self.lbl_status.setText(
            f"✅ 监控中: {len(self.monitored_codes)} 只 | "
            f"🎯 预下单: {pre_cnt} 只 | 🚀 回踩启动: {pull_cnt} 只 | ⚡ 加速: {break_cnt} 只 | 耗时: {cost:.2f}s"
        )

        # 扫描结束统一按用户当前排序列整理一次
        if self.table.isSortingEnabled():
            col = self.table.horizontalHeader().sortIndicatorSection()
            order = self.table.horizontalHeader().sortIndicatorOrder()
            if col >= 0:
                self.table.sortItems(col, order)

    def _rebuild_table_rows(self):
        """根据当前 monitored_codes 重建表格行"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.monitored_codes))
        for row, code in enumerate(self.monitored_codes):
            name = resolve_fast_ipo_name(code)
            self.table.setItem(row, 0, QTableWidgetItem(code))
            self.table.setItem(row, 1, QTableWidgetItem(name))
            for c in range(2, 13):
                self.table.setItem(row, c, QTableWidgetItem("--"))

            # 操作按钮
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
            self.table.setCellWidget(row, 12, btn_box)

            # 若已有信号数据，立即填充
            if code in self.signals_map:
                self._update_table_row_data(self.signals_map[code], target_row=row)

        self.table.setSortingEnabled(True)

    def _update_table_row_data(self, sig: VWAPDetectorSignal, target_row: Optional[int] = None):
        """【🛡️ 整行原子写入】写入期间严格禁用 sorting，彻底杜绝数据错位串行"""
        was_sorting = self.table.isSortingEnabled()
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

            # 现价 (支持纯数值排序)
            it_price = QTableWidgetItem(f"{sig.price:.2f}" if sig.price > 0 else "--")
            it_price.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sig.price > 0:
                it_price.setData(Qt.ItemDataRole.EditRole, float(sig.price))
            self.table.setItem(row, 2, it_price)

            # 涨跌幅 (支持纯数值排序)
            it_chg = QTableWidgetItem(f"{sig.change_pct:+.2f}%" if sig.price > 0 else "--")
            it_chg.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sig.price > 0:
                it_chg.setData(Qt.ItemDataRole.EditRole, float(sig.change_pct))
            if sig.change_pct > 0:
                it_chg.setForeground(QColor("#ff4444"))
            elif sig.change_pct < 0:
                it_chg.setForeground(QColor("#00ff88"))
            self.table.setItem(row, 3, it_chg)

            # 10d VWAP (支持纯数值排序)
            it_vw = QTableWidgetItem(f"{sig.vwap:.2f}" if sig.vwap > 0 else "--")
            it_vw.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sig.vwap > 0:
                it_vw.setData(Qt.ItemDataRole.EditRole, float(sig.vwap))
            it_vw.setForeground(QColor("#ffcc00"))
            self.table.setItem(row, 4, it_vw)

            # VWAP偏离 (支持纯数值排序)
            it_diff = QTableWidgetItem(f"{sig.vwap_diff_pct:+.1f}%" if sig.vwap > 0 else "--")
            it_diff.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sig.vwap > 0:
                it_diff.setData(Qt.ItemDataRole.EditRole, float(sig.vwap_diff_pct))
            if sig.vwap_diff_pct > 0:
                it_diff.setForeground(QColor("#ff8800"))
            elif sig.vwap_diff_pct < 0:
                it_diff.setForeground(QColor("#00bbff"))
            self.table.setItem(row, 5, it_diff)

            # VWAP结构形态
            it_struct = QTableWidgetItem(sig.structure_tag)
            if sig.consolidation_days >= 1:
                it_struct.setForeground(QColor("#ffd700"))
                it_struct.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            elif sig.pullback_no_touch:
                it_struct.setForeground(QColor("#00ff88"))
                it_struct.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            self.table.setItem(row, 6, it_struct)

            # 大趋势K线状态
            it_trend = QTableWidgetItem(sig.trend_desc or "--")
            if sig.has_kline_launch_sig:
                it_trend.setForeground(QColor("#ff33aa"))
            self.table.setItem(row, 7, it_trend)

            # 信号评级
            it_sig = QTableWidgetItem(sig.signal_level)
            it_sig.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            if sig.signal_type == "PRE_ORDER":
                it_sig.setForeground(QColor("#ffd700"))  # 金黄
                it_sig.setBackground(QColor("#2d2400"))
            elif sig.signal_type == "PULLBACK_BUY":
                it_sig.setForeground(QColor("#00ff88"))  # 荧光绿
                it_sig.setBackground(QColor("#002d18"))
            elif sig.signal_type == "BREAKOUT":
                it_sig.setForeground(QColor("#ff007f"))  # 亮粉红
                it_sig.setBackground(QColor("#2d0015"))
            elif sig.signal_type == "WEAK_EXIT":
                it_sig.setForeground(QColor("#ff5555"))
            self.table.setItem(row, 8, it_sig)

            # 极窄止损位 (支持纯数值排序)
            it_sl = QTableWidgetItem(f"{sig.stop_loss_price:.2f}" if sig.stop_loss_price > 0 else "--")
            it_sl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if sig.stop_loss_price > 0:
                it_sl.setData(Qt.ItemDataRole.EditRole, float(sig.stop_loss_price))
            it_sl.setForeground(QColor("#ff5555"))
            self.table.setItem(row, 9, it_sl)

            # 为什么 (详细解释)
            it_desc = QTableWidgetItem(sig.signal_desc)
            it_desc.setToolTip(sig.signal_desc)
            self.table.setItem(row, 10, it_desc)

            # 更新时间
            it_time = QTableWidgetItem(sig.update_time or "--")
            self.table.setItem(row, 11, it_time)
        finally:
            if was_sorting:
                self.table.setSortingEnabled(True)

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
        """【📈 一键平铺全部关注的 SBC】"""
        # 取排在前面有信号的最多 4 只标的
        candidates = []
        for c in self.monitored_codes:
            sig = self.signals_map.get(c)
            if sig and sig.signal_type in ("PRE_ORDER", "PULLBACK_BUY", "BREAKOUT"):
                candidates.append(c)
        if not candidates:
            candidates = self.monitored_codes[:4]
        else:
            candidates = candidates[:4]

        if not candidates:
            return

        from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog, rearrange_all_sbc_windows
        for c in candidates:
            dlg = open_sbc_chart_dialog(code=c, period_mode="10d")
            if dlg:
                dlg.show()

        # 短暂延时自动平铺重排
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

    def _on_shortcut_f_linkage(self):
        """按 F 键联动外部行情软件 (通达信等)"""
        row = self.table.currentRow()
        if row >= 0:
            it = self.table.item(row, 0)
            if it:
                code = it.text().strip()
                try:
                    from ats.ui.intraday_strategy_dialog import _send_linkage_to_external_apps
                    _send_linkage_to_external_apps(code)
                    self.lbl_status.setText(f"🔗 已联动外部通达信/同花顺: {code}")
                except Exception as e:
                    logger.debug(f"联动异常: {e}")

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

    def _on_ipc_poll_and_heartbeat(self):
        """消费来自 ATS 跨进程一键发送过来的新代码，并更新心跳"""
        # 1. 维护心跳
        update_detector_heartbeat(os.getpid())

        # 2. 消费队列
        new_stocks = pop_queued_stocks()
        if new_stocks:
            for s in new_stocks:
                self.add_stock(s)
            self.lbl_status.setText(f"⚡ 收到来自 ATS 跨进程发送的标的: {', '.join(new_stocks)}")

    def closeEvent(self, event):
        """窗口关闭时集中保存配置"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(500)
        self.save_persisted_state()
        super().closeEvent(event)
