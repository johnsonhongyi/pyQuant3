# -*- coding: utf-8 -*-
"""
ATS Dragon Leader Monitor Window
Provides automatic and manual tracking for 2D/3D acceleration leaders.
Supports magnetic edge-snapping and persistent storage.
"""

import os
import json
import time
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, 
    QPushButton, QFrame, QMenu, QApplication, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QBrush, QColor
import pandas as pd

from tk_gui_modules.window_mixin import WindowMixin
from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
from tk_gui_modules.qt_table_utils import NumericTableWidgetItem
from logger_utils import LoggerFactory
from ats.ui.styles import COLOR_UP, COLOR_DOWN, COLOR_INFO, COLOR_ACCENT, COLOR_WARN, auto_fit_columns_once, setup_header_persistence

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()


def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default



class DragonLeaderMonitorDialog(QDialog, WindowMixin):
    """
    Super strong 2D/3D dragon leader monitor window.
    Features magnetic edge snapping, auto hide, and persistent manually tracked codes.
    """
    code_clicked = pyqtSignal(str, str) # linkage

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("🐉 2D/3D 加速龙头追踪器")
        self.setMinimumWidth(250)
        self._is_updating = False
        
        # 1. Load config path and data files
        try:
            from sys_utils import get_app_root
            self.data_dir = os.path.join(get_app_root(), "datacsv")
            os.makedirs(self.data_dir, exist_ok=True)
            self.db_path = os.path.join(self.data_dir, "ats_dragon_leaders.json")
            
            # Auto-migrate old data from the root data directory if present
            old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            old_db_path = os.path.join(old_data_dir, "ats_dragon_leaders.json")
            if os.path.exists(old_db_path) and not os.path.exists(self.db_path):
                try:
                    import shutil
                    shutil.copy2(old_db_path, self.db_path)
                    logger.info(f"Successfully migrated old data from {old_db_path} to {self.db_path}")
                except Exception as e:
                    logger.warning(f"Failed to migrate old data folder: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize data directories: {e}")
            self.data_dir = None
            self.db_path = None
        
        self.manual_codes = []
        self.blacklist_codes = []
        self._load_dragon_data()
        self.auto_codes = []
        self._last_row_count = 0
        
        # 2. Stays on top
        self.stays_on_top = self._load_stays_on_top()
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags &= ~Qt.WindowType.Tool
        flags |= Qt.WindowType.Window
        flags |= Qt.WindowType.WindowMinimizeButtonHint
        flags |= Qt.WindowType.WindowMaximizeButtonHint
        flags |= Qt.WindowType.WindowCloseButtonHint
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        
        # Load window position and size
        self.load_window_position_qt(self, "dragon_leader_monitor_dialog", default_width=800, default_height=500)
        self._is_updating = True
        self.setStyleSheet("QDialog { background-color: #161822; color: #ffffff; }")
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Title bar & Controls
        header_frame = QFrame()
        header_frame.setStyleSheet("QFrame { background-color: #1b1e2a; border-radius: 4px; }")
        header_lay = QHBoxLayout(header_frame)
        header_lay.setContentsMargins(8, 4, 8, 4)
        
        self.header_label = QLabel("🐉 2D/3D 加速龙头追踪器 | 每日自动挖掘 + 手动跟踪")
        self.header_label.setStyleSheet("color: #00FFCC; font-size: 13px; font-weight: bold;")
        header_lay.addWidget(self.header_label)
        
        header_lay.addStretch()
        
        # Stays on top checkbox
        self.chk_on_top = QCheckBox("置顶")
        self.chk_on_top.setStyleSheet("""
            QCheckBox { color: #00FFCC; font-size: 9pt; font-weight: bold; }
            QCheckBox::indicator { width: 12px; height: 12px; }
        """)
        self.chk_on_top.setChecked(self.stays_on_top)
        self.chk_on_top.stateChanged.connect(self._on_stays_on_top_toggled)
        header_lay.addWidget(self.chk_on_top)
        header_lay.addSpacing(10)
        
        # Add manual code button
        self.btn_add_manual = QPushButton("➕ 添加股票")
        self.btn_add_manual.setFixedWidth(85)
        self.btn_add_manual.setStyleSheet("""
            QPushButton { background: #1a3a30; color: #00ffaa; border: 1px solid #00ffaa; border-radius: 3px; font-size: 8pt; font-weight: bold; height: 20px; }
            QPushButton:hover { background: #00ffaa; color: #000; }
        """)
        self.btn_add_manual.clicked.connect(self._on_add_manual_clicked)
        header_lay.addWidget(self.btn_add_manual)
        
        layout.addWidget(header_frame)
        
        # Main Table
        self.cols = ["代码", "名称", "现价", "涨幅%", "波段状态", "DFF", "DFF2", "DFF3", "大盘偏离", "共振状态", "来源"]
        self.table = QTableWidget(0, len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicatorShown(True)
        
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h_header.setFixedHeight(28)
        h_header.sortIndicatorChanged.connect(lambda: self.table.scrollToTop())
        
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #0c0d14;
                color: #ffffff;
                gridline-color: #222433;
                border: none;
            }
            QHeaderView {
                background-color: #141622;
                border: none;
            }
            QHeaderView::section {
                background-color: #141622;
                color: #8e90a6;
                padding: 4px;
                border: 0.5px solid #222433;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #24293e;
                color: #00ffaa;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 100);
                border-radius: 3px;
            }
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
            }
            QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 100);
                border-radius: 3px;
            }
        """)
        
        # Setup column widths and persistence
        default_widths = {
            0: 75,   # 代码
            1: 85,   # 名称
            2: 70,   # 现价
            3: 70,   # 涨幅
            4: 80,   # 波段状态
            5: 65,   # DFF
            6: 65,   # DFF2
            7: 65,   # DFF3
            8: 85,   # 大盘偏离
            9: 100,  # 共振状态
            10: 80   # 来源
        }
        setup_header_persistence(self.table, "dragon_leader_monitor_header_v1", default_widths=default_widths)
        h_header.setStretchLastSection(True)
        
        # Connect signals
        self.table.itemClicked.connect(self._on_item_clicked)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.currentItemChanged.connect(self._on_current_item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        self.setLayout(layout)
        
        QTimer.singleShot(200, lambda: setattr(self, '_is_updating', False))
        
        # 3. Magnetic snap setup
        self.anchor_edge = None
        self.is_hidden_state = False
        self.normal_geometry = None
        self.hover_ticks = 0
        self.leave_ticks = 0
        self._in_snap_action = False
        self.anim_group = None
        self._is_dragging = False
        self._last_show_time = 0.0
        self._has_hovered_since_show = False
        self._is_auto_popping = False
        
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)
        self.hover_timer.start()
        
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(200)
        self.snap_timer.timeout.connect(self._detect_and_snap)

    def _load_dragon_data(self):
        try:
            if self.db_path and os.path.exists(self.db_path):
                with open(self.db_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.manual_codes = data.get("manual", ["000779", "301528"])
                    self.blacklist_codes = data.get("blacklist", [])
                    return
        except Exception as e:
            logger.warning(f"Error loading dragon leader data: {e}")
        # Default mock codes showing acceleration structure as default placeholders
        self.manual_codes = ["000779", "301528"]
        self.blacklist_codes = []

    def _save_manual_codes(self):
        if not self.db_path or not self.data_dir:
            return
        try:
            import tempfile
            data = {
                "manual": list(self.manual_codes),
                "blacklist": list(self.blacklist_codes)
            }
            tmp_fd, tmp_path = tempfile.mkstemp(dir=self.data_dir, prefix="ats_dragon_tmp_")
            try:
                with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                os.replace(tmp_path, self.db_path)
            except Exception as e:
                try:
                    os.remove(tmp_path)
                except:
                    pass
                raise e
        except Exception as e:
            logger.warning(f"Error saving manual codes atomically: {e}")

    def _load_stays_on_top(self) -> bool:
        try:
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        cfg = data.get("dragon_leader_monitor_dialog", {})
                        return cfg.get("stays_on_top", False)
        except Exception:
            pass
        return False

    def _on_stays_on_top_toggled(self, state):
        self.stays_on_top = self.chk_on_top.isChecked()
        flags = self.windowFlags()
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _save_window_states(self, is_open=None) -> None:
        try:
            scale = self._get_dpi_scale_factor()
            geom = self.normal_geometry if (self.is_hidden_state and self.normal_geometry) else self.geometry()
            width = max(130, int(geom.width() / scale))
            height = max(150, int(geom.height() / scale))
            x = int(geom.x() / scale)
            y = int(geom.y() / scale)
            
            if is_open is None:
                is_open = self.isVisible()
                
            with _CONFIG_FILE_LOCK:
                data = {}
                if os.path.exists(WINDOW_CONFIG_FILE):
                    try:
                        with open(WINDOW_CONFIG_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except:
                        pass
                
                data["dragon_leader_monitor_dialog"] = {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "stays_on_top": self.stays_on_top,
                    "anchor_edge": self.anchor_edge,
                    "is_hidden_state": self.is_hidden_state,
                    "is_open": is_open
                }
                
                tmp = WINDOW_CONFIG_FILE + f".tmp_dragon_states_{id(self)}"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                # Windows 多进程并发写入重试退避机制，防止 WinError 5 拒绝访问
                for attempt in range(5):
                    try:
                        os.replace(tmp, WINDOW_CONFIG_FILE)
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        import time
                        time.sleep(0.05 * (attempt + 1))
        except Exception as e:
            logger.warning(f"Error saving window states: {e}")

    def update_data(self, current_df, sh_pct):
        """
        盘中高频实时刷新及自动替换挖掘逻辑
        """
        if current_df is None or current_df.empty:
            return
            
        self._is_updating = True
        
        # 0. 锁定当前选中的股票代码以防止刷新时焦点丢失
        selected_code = None
        curr_row = self.table.currentRow()
        if curr_row >= 0:
            c_item = self.table.item(curr_row, 0)
            if c_item:
                selected_code = c_item.text()
        
        # 智能匹配短、中、长周期的 DFF 列，应对带有周期后缀（如 dff_d, dff_3d, dff_3M）或动态配置列
        def get_period_weight(col_name):
            col_lower = str(col_name).lower()
            if col_lower == 'dff':
                return 1.0
            if col_lower == 'dff2':
                return 5.0
            if col_lower == 'dff3':
                return 20.0
            if '_' in col_lower:
                suffix = col_lower.split('_')[-1]
            else:
                suffix = col_lower.replace('dff', '')
            if not suffix:
                return 1.0
            try:
                import re
                num_part = re.findall(r'\d+', suffix)
                num = int(num_part[0]) if num_part else 1
                if 'y' in suffix:
                    return num * 240.0
                elif 'm' in suffix:
                    return num * 20.0
                elif 'w' in suffix:
                    return num * 5.0
                elif 'd' in suffix:
                    return num * 1.0
                return float(num)
            except Exception:
                return 999.0

        # ── 一次加锁读取全部三个周期数据，避免多次竞争锁 ──
        dff_dict = {}
        dff2_dict = {}
        dff3_dict = {}
        
        main_app = self._get_main_app()
        if main_app and hasattr(main_app, "engine") and hasattr(main_app.engine, "_period_dfs"):
            lock = getattr(main_app.engine, "lock", None)
            period_snapshots = {}
            if lock:
                with lock:
                    active_periods = list(main_app.engine._period_dfs.keys())
                    for p in active_periods:
                        raw = main_app.engine._period_dfs.get(p)
                        if raw is not None and not raw.empty:
                            period_snapshots[p] = raw.copy()
            else:
                active_periods = list(main_app.engine._period_dfs.keys())
                for p in active_periods:
                    raw = main_app.engine._period_dfs.get(p)
                    if raw is not None and not raw.empty:
                        period_snapshots[p] = raw.copy()
                        
            # 按顺序从已加载的周期中匹配：第1个周期为短周期，第2个为中周期，第3个为长周期
            sorted_periods = list(period_snapshots.keys())
            df_d = period_snapshots.get(sorted_periods[0]) if len(sorted_periods) > 0 else None
            df_w = period_snapshots.get(sorted_periods[1]) if len(sorted_periods) > 1 else None
            df_m = period_snapshots.get(sorted_periods[2]) if len(sorted_periods) > 2 else None

            def get_dff_col(df_p, preferred):
                if df_p is None:
                    return None
                for col_name in preferred:
                    if col_name in df_p.columns:
                        return col_name
                # 模糊匹配
                for col_name in df_p.columns:
                    if 'dff' in str(col_name).lower():
                        return col_name
                return None

            col_d = get_dff_col(df_d, ['dff', 'dff_d'])
            if col_d and df_d is not None:
                dff_dict = {str(k).zfill(6): v for k, v in df_d[col_d].to_dict().items() if k}
                    
            col_w = get_dff_col(df_w, ['dff2', 'dff', 'dff_w'])
            if col_w and df_w is not None:
                dff2_dict = {str(k).zfill(6): v for k, v in df_w[col_w].to_dict().items() if k}
                    
            col_m = get_dff_col(df_m, ['dff3', 'dff', 'dff_m'])
            if col_m and df_m is not None:
                dff3_dict = {str(k).zfill(6): v for k, v in df_m[col_m].to_dict().items() if k}
        
        # ── 降级兜底：如果无法从 engine 加载，且 current_df 自身有加速特征列，则直接提取 ──
        if not dff_dict and not dff2_dict and not dff3_dict:
            dff_cols = [c for c in current_df.columns if 'dff' in str(c).lower()]
            dff_cols.sort(key=get_period_weight)
            
            dff_col = dff_cols[0] if len(dff_cols) > 0 else 'dff'
            dff2_col = dff_cols[1] if len(dff_cols) > 1 else 'dff2'
            dff3_col = dff_cols[2] if len(dff_cols) > 2 else 'dff3'
            
            for c, r in current_df.iterrows():
                if isinstance(r, pd.DataFrame):
                    r = r.iloc[0]
                c_str = str(c).zfill(6)
                dff_dict[c_str] = safe_float(r.get(dff_col, 0.0))
                dff2_dict[c_str] = safe_float(r.get(dff2_col, 0.0))
                dff3_dict[c_str] = safe_float(r.get(dff3_col, 0.0))
        
        # 1. 每日自动替换更新潜力股 (2D/3D加速多头完美结构挖掘)
        new_auto_list = []
        
        for code, row in current_df.iterrows():
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
                
            code_str = str(code).zfill(6)
            if code_str in self.manual_codes:
                continue # 已在手动监控中
            if code_str in self.blacklist_codes:
                continue # 已在黑名单中，不予挖掘
                
            dff = safe_float(dff_dict.get(code_str, 0.0))
            dff2 = safe_float(dff2_dict.get(code_str, 0.0))
            dff3 = safe_float(dff3_dict.get(code_str, 0.0))
            pct = safe_float(row.get('ratio', row.get('percent', 0.0)))
            rs_val = pct - sh_pct
            
            # Super Strong 2D/3D 加速多头条件过滤
            is_accel = dff > 0.0 and dff2 > 0.0 and dff3 > 0.0
            is_strong_rs = rs_val >= 2.0 and pct > 1.5
            
            # 复合特征判决
            if is_accel and is_strong_rs:
                new_auto_list.append((code_str, rs_val))
                
        # 排序并保留偏离度最高的前 15 只超级潜力股
        new_auto_list.sort(key=lambda x: x[1], reverse=True)
        self.auto_codes = [c[0] for c in new_auto_list[:15]]
        
        # 2. 合并手动与自动代码列表
        all_codes = list(self.manual_codes) + [c for c in self.auto_codes if c not in self.manual_codes]
        
        # 3. 收集实时指标准备填充表格
        rows_data = []
        for code in all_codes:
            name = "未知个股"
            price = 0.0
            pct = 0.0
            state = "平稳期"
            dff = 0.0
            dff2 = 0.0
            dff3 = 0.0
            rs_val = 0.0
            resonance = "同步整理"
            source = "手动添加" if code in self.manual_codes else "🔥自动挖掘"
            
            # 从主窗口传递的个股信息库解析
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'get_stock_name'):
                name = main_app.get_stock_name(code)
            else:
                from sys_utils import resolve_stock_name
                name = resolve_stock_name(code) or "未知个股"
                
            if code in current_df.index:
                row = current_df.loc[code]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                row_name = str(row.get('name', '') or '').strip()
                if row_name and row_name not in ('nan', '--', '0', ''):
                    name = row_name
                price = safe_float(row.get('close', row.get('price', 0.0)))
                pct = safe_float(row.get('ratio', row.get('percent', 0.0)))
                state = str(row.get('state', '持股中' if pct > 0 else '回踩中'))
                dff = safe_float(dff_dict.get(code, 0.0))
                dff2 = safe_float(dff2_dict.get(code, 0.0))
                dff3 = safe_float(dff3_dict.get(code, 0.0))
                rs_val = pct - sh_pct
                
                # 共振类型判定
                if sh_pct < -0.5 and pct > 1.5 and rs_val > 2.0:
                    resonance = "逆市抗跌"
                elif sh_pct > 0.5 and pct > 3.0 and dff > 1.0:
                    resonance = "大盘共振"
                elif sh_pct < -1.0 and pct < -1.5:
                    resonance = "同步走弱"
            
            rows_data.append((
                code, name, price, pct, state, dff, dff2, dff3, rs_val, resonance, source
            ))
            
        # 4. 刷新渲染表格
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows_data))
        
        for idx, data in enumerate(rows_data):
            # ["代码", "名称", "现价", "涨幅%", "波段状态", "DFF", "DFF2", "DFF3", "大盘偏离", "共振状态", "来源"]
            code, name, price, pct, state, dff, dff2, dff3, rs_val, resonance, source = data
            
            c_item = QTableWidgetItem(code)
            c_item.setForeground(QBrush(QColor("#00FF88" if source.startswith("手动") else "#FFE4C4")))
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            n_item = QTableWidgetItem(name)
            n_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if source.startswith("手动"):
                n_item.setText(f"⭐ {name}")
                n_item.setForeground(QBrush(QColor("#00FF88")))
                
            p_item = NumericTableWidgetItem(f"{price:.2f}")
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            pct_item = NumericTableWidgetItem(f"{pct:+.2f}%")
            pct_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if pct > 0:
                pct_item.setForeground(QBrush(QColor(COLOR_UP)))
            elif pct < 0:
                pct_item.setForeground(QBrush(QColor(COLOR_DOWN)))
                
            st_item = QTableWidgetItem(state)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if "持股" in state:
                st_item.setForeground(QBrush(QColor(COLOR_UP)))
            else:
                st_item.setForeground(QBrush(QColor(COLOR_WARN)))
                
            d1_item = NumericTableWidgetItem(f"{dff:.2f}")
            d1_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            d1_item.setForeground(QBrush(QColor(COLOR_UP if dff > 0 else COLOR_DOWN)))
            
            d2_item = NumericTableWidgetItem(f"{dff2:.2f}")
            d2_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            d2_item.setForeground(QBrush(QColor(COLOR_UP if dff2 > 0 else COLOR_DOWN)))
            
            d3_item = NumericTableWidgetItem(f"{dff3:.2f}")
            d3_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            d3_item.setForeground(QBrush(QColor(COLOR_UP if dff3 > 0 else COLOR_DOWN)))
            
            rs_item = NumericTableWidgetItem(f"{rs_val:+.2f}%")
            rs_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if rs_val >= 2.0:
                rs_item.setForeground(QBrush(QColor(COLOR_UP)))
                font = self.table.font()
                font.setBold(True)
                rs_item.setFont(font)
            elif rs_val < -2.0:
                rs_item.setForeground(QBrush(QColor(COLOR_DOWN)))
                
            res_item = QTableWidgetItem(resonance)
            res_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if resonance == "逆市抗跌":
                res_item.setForeground(QBrush(QColor("#FF7F50"))) # Coral
                font = self.table.font()
                font.setBold(True)
                res_item.setFont(font)
            elif resonance == "大盘共振":
                res_item.setForeground(QBrush(QColor(COLOR_UP)))
                font = self.table.font()
                font.setBold(True)
                res_item.setFont(font)
                
            src_item = QTableWidgetItem(source)
            src_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if "自动" in source:
                src_item.setForeground(QBrush(QColor("#FFD700")))
                
            self.table.setItem(idx, 0, c_item)
            self.table.setItem(idx, 1, n_item)
            self.table.setItem(idx, 2, p_item)
            self.table.setItem(idx, 3, pct_item)
            self.table.setItem(idx, 4, st_item)
            self.table.setItem(idx, 5, d1_item)
            self.table.setItem(idx, 6, d2_item)
            self.table.setItem(idx, 7, d3_item)
            self.table.setItem(idx, 8, rs_item)
            self.table.setItem(idx, 9, res_item)
            self.table.setItem(idx, 10, src_item)
            
            # 手动添加整行高亮特殊背景色
            if source.startswith("手动"):
                for col in range(len(self.cols)):
                    item = self.table.item(idx, col)
                    if item:
                        item.setBackground(QBrush(QColor("#152a1a")))
                        
        if len(rows_data) != getattr(self, '_last_row_count', 0):
            self._last_row_count = len(rows_data)
            auto_fit_columns_once(self.table, "dragon_leader_monitor_header_v1")
            
        self.table.setSortingEnabled(True)
        
        # 恢复先前选中的个股焦点
        if selected_code:
            for r in range(self.table.rowCount()):
                c_item = self.table.item(r, 0)
                if c_item and c_item.text() == selected_code:
                    self.table.setCurrentCell(r, 0)
                    break
                    
        self._is_updating = False

    def _get_main_app(self):
        # 1. Prioritize parent widgets possessing engine & _period_dfs
        curr = self.parent()
        while curr:
            if hasattr(curr, 'engine') and hasattr(curr.engine, '_period_dfs'):
                return curr
            curr = curr.parent()
            
        # 2. Check general parent linkage-capable widgets
        curr = self.parent()
        while curr:
            if hasattr(curr, 'link_stock') or hasattr(curr, 'on_stock_clicked'):
                return curr
            curr = curr.parent()

        # 3. Check top-level widgets, prioritize MultiPeriodDialog (possessing engine)
        app = QApplication.instance()
        if app:
            widgets = app.topLevelWidgets()
            for widget in widgets:
                try:
                    from PyQt6.sip import isdeleted
                    if isdeleted(widget):
                        continue
                except:
                    pass
                if widget.__class__.__name__ == 'MultiPeriodDialog' or (hasattr(widget, 'engine') and hasattr(widget.engine, '_period_dfs')):
                    return widget
            
            # Fallback to ATSMainWindow or other windows with linkage capability
            for widget in widgets:
                try:
                    from PyQt6.sip import isdeleted
                    if isdeleted(widget):
                        continue
                except:
                    pass
                if hasattr(widget, 'link_stock') or hasattr(widget, 'on_stock_clicked'):
                    return widget
        return None

    def _on_add_manual_clicked(self):
        code, ok = QInputDialog.getText(self, "添加龙头追踪个股", "请输入6位股票代码:")
        if ok and code.strip():
            code_str = code.strip().zfill(6)
            if code_str in self.manual_codes:
                QMessageBox.information(self, "提示", f"代码 {code_str} 已在追踪列表中。")
                return
            if code_str in self.blacklist_codes:
                self.blacklist_codes.remove(code_str)
            self.manual_codes.append(code_str)
            self._save_manual_codes()
            # 立即触发主程序重绘
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'refresh_realtime_ui'):
                main_app.refresh_realtime_ui()

    def _on_item_clicked(self, item):
        if item:
            self._link_current_row(item.row())

    def _on_current_item_changed(self, current, previous):
        if current:
            self._link_current_row(current.row())

    def _on_item_double_clicked(self, item):
        if item:
            row = item.row()
            code_item = self.table.item(row, 0)
            name_item = self.table.item(row, 1)
            if code_item and name_item:
                code = code_item.text()
                name = name_item.text().replace("⭐ ", "")
                main_app = self._get_main_app()
                if main_app:
                    if hasattr(main_app, 'link_stock'):
                        main_app.link_stock(code, name)
                    if hasattr(main_app, 'on_stock_clicked'):
                        main_app.on_stock_clicked(code, name)

    def _link_current_row(self, row):
        if getattr(self, '_is_updating', False) or getattr(self, '_is_auto_popping', False):
            return
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item and name_item:
            code = code_item.text()
            name = name_item.text().replace("⭐ ", "")
            self.code_clicked.emit(code, name)
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'link_stock'):
                main_app.link_stock(code, name)

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return
        
        row = item.row()
        code = self.table.item(row, 0).text()
        name = self.table.item(row, 1).text().replace("⭐ ", "")
        source = self.table.item(row, 10).text()
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)
        
        # Link actions
        link_act = menu.addAction(f"⚡ 选中联动 ({code})")
        link_act.triggered.connect(lambda: self.code_clicked.emit(code, name))
        
        from ats.ui.base_table import send_to_linkage
        linkage_act = menu.addAction(f"⚡ 发送到异动联动 ({code})")
        linkage_act.triggered.connect(lambda: send_to_linkage(code, name, self))
        
        menu.addSeparator()
        
        # Manage manual list
        if source.startswith("手动"):
            rm_act = menu.addAction("❌ 移出手动跟踪列表")
            rm_act.triggered.connect(lambda: self._remove_from_manual(code))
            
            black_act = menu.addAction("🚫 移出并加入黑名单")
            black_act.triggered.connect(lambda: self._add_to_blacklist(code))
        else:
            add_act = menu.addAction("⭐ 转为重点手动跟踪")
            add_act.triggered.connect(lambda: self._convert_to_manual(code))
            
            black_act = menu.addAction("🚫 移除并加入黑名单")
            black_act.triggered.connect(lambda: self._add_to_blacklist(code))
            
        menu.addSeparator()
        
        # Copy actions
        copy_code = menu.addAction("复制代码")
        copy_code.triggered.connect(lambda: QApplication.clipboard().setText(code))
        copy_name = menu.addAction("复制名称")
        copy_name.triggered.connect(lambda: QApplication.clipboard().setText(name))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _convert_to_manual(self, code):
        if code not in self.manual_codes:
            self.manual_codes.append(code)
            self._save_manual_codes()
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'refresh_realtime_ui'):
                main_app.refresh_realtime_ui()

    def _remove_from_manual(self, code):
        if code in self.manual_codes:
            self.manual_codes.remove(code)
            self._save_manual_codes()
            main_app = self._get_main_app()
            if main_app and hasattr(main_app, 'refresh_realtime_ui'):
                main_app.refresh_realtime_ui()

    def _add_to_blacklist(self, code):
        if code in self.manual_codes:
            self.manual_codes.remove(code)
        if code not in self.blacklist_codes:
            self.blacklist_codes.append(code)
        self._save_manual_codes()
        main_app = self._get_main_app()
        if main_app and hasattr(main_app, 'refresh_realtime_ui'):
            main_app.refresh_realtime_ui()

    # --- Magnetic Snap Implementation ---
    def start_slide_animation(self, target_rect, target_opacity, duration=250, is_snap_feedback=False):
        if hasattr(self, 'anim_group') and self.anim_group is not None:
            try:
                if self.anim_group.state() == QParallelAnimationGroup.State.Running:
                    self.anim_group.stop()
            except Exception:
                pass
                
        self.anim_group = QParallelAnimationGroup(self)
        self.geom_anim = QPropertyAnimation(self, b"geometry")
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_rect)
        if is_snap_feedback:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(target_opacity)
        if is_snap_feedback:
            self.opacity_anim.setKeyValueAt(0.5, 0.4)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        
        self._in_snap_action = True
        
        def on_finished():
            self._in_snap_action = False
            if self.is_hidden_state:
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(1.0)
            self._save_window_states(is_open=True)
                
        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        if self.is_hidden_state:
            return
            
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start()
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35
        
        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()
        
        if abs(win_geo.top() - screen_geo.top()) < margin:
            edge = "top"
            target_y = screen_geo.top()
            snapped = True
        elif abs(win_geo.left() - screen_geo.left()) < margin:
            edge = "left"
            target_x = screen_geo.left()
            snapped = True
        elif abs(win_geo.right() - screen_geo.right()) < margin:
            edge = "right"
            target_x = screen_geo.right() - win_geo.width()
            snapped = True
            
        self._is_dragging = False
        if snapped:
            self.anchor_edge = edge
            self.normal_geometry = QRect(target_x, target_y, win_geo.width(), win_geo.height())
            self.start_slide_animation(self.normal_geometry, 1.0, duration=250, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None

    def hide_to_edge(self):
        if not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        
        w = self.normal_geometry.width()
        h = self.normal_geometry.height()
        x = self.normal_geometry.x()
        y = self.normal_geometry.y()
        strip_size = 5
        
        if self.anchor_edge == "left":
            target_x = screen_geo.left() - w + strip_size
            target_y = y
        elif self.anchor_edge == "right":
            target_x = screen_geo.right() - strip_size
            target_y = y
        elif self.anchor_edge == "top":
            target_x = x
            target_y = screen_geo.top() - h + strip_size
        else:
            return
            
        self.is_hidden_state = True
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=300)

    def show_normal_position(self):
        if self.is_hidden_state and self.normal_geometry:
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            
            self.is_hidden_state = False
            self._last_show_time = time.time()
            self._has_hovered_since_show = False
            self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
        
        self.show()
        self.raise_()
        self.activateWindow()

    def _check_hover(self):
        if not self.isVisible():
            return
            
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return
            
        from PyQt6.QtGui import QCursor
        mouse_pos = QCursor.pos()
        in_window = self.frameGeometry().contains(mouse_pos)
        
        if in_window:
            self._has_hovered_since_show = True
            
        if self.is_hidden_state:
            if in_window:
                self.hover_ticks += 1
                if self.hover_ticks >= 2:
                    self.show_normal_position()
                    self.hover_ticks = 0
            else:
                self.hover_ticks = 0
        else:
            if self.anchor_edge is not None:
                if not in_window:
                    if not getattr(self, '_has_hovered_since_show', False):
                        self.leave_ticks = 0
                        return
                    if time.time() - getattr(self, '_last_show_time', 0.0) < 1.2:
                        self.leave_ticks = 0
                        return
                        
                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        super().moveEvent(event)
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            self.anchor_edge = None
            self.snap_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

    def closeEvent(self, event):
        self.hover_timer.stop()
        self.snap_timer.stop()
        self._save_window_states(is_open=False)
        event.accept()

    def hideEvent(self, event):
        self._save_window_states(is_open=False)
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self.layout():
            self.layout().activate()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.layout():
            self.layout().setGeometry(self.rect())
        if not self.is_hidden_state and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()
