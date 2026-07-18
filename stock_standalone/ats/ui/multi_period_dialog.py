# -*- coding: utf-8 -*-
"""
ATS PyQt6 Multi-Period Strategy Tester Dialog
Provides multi-period cross filtering, strategy management, concept analysis, 
and linkage with external terminals.
"""

import sys
import os

# 允许单独运行此脚本，将项目根目录加入 sys.path
if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.chdir(project_root)

# ---------------------------------------------
# 防御性 MOCK：当环境没有 tk 时，动态注入 Dummy 模块，防止导入 auditor 和 utils 崩溃
# ---------------------------------------------
try:
    import tkinter
    import tkinter.font
    import tkinter.messagebox
    import tkinter.ttk
    import tkinter.scrolledtext
except ImportError:
    from types import ModuleType
    mock_tk = ModuleType("tkinter")
    mock_tk.Toplevel = object
    mock_tk.Tk = object
    mock_tk.Frame = object
    mock_tk.Label = object
    mock_tk.Button = object
    mock_tk.Entry = object
    mock_tk.StringVar = object
    mock_tk.WORD = None
    mock_tk.END = None
    mock_tk.BOTH = None
    mock_tk.Y = None
    mock_tk.LEFT = None
    mock_tk.RIGHT = None
    mock_tk.W = None
    mock_tk.CENTER = None
    mock_tk.VERTICAL = None
    
    mock_font = ModuleType("tkinter.font")
    mock_font.Font = object
    
    mock_msg = ModuleType("tkinter.messagebox")
    mock_ttk = ModuleType("tkinter.ttk")
    mock_ttk.Style = object
    mock_ttk.Panedwindow = object
    mock_ttk.Treeview = object
    mock_ttk.Scrollbar = object
    
    mock_scroll = ModuleType("tkinter.scrolledtext")
    mock_scroll.ScrolledText = object
    
    sys.modules["tkinter"] = mock_tk
    sys.modules["tkinter.font"] = mock_font
    sys.modules["tkinter.messagebox"] = mock_msg
    sys.modules["tkinter.ttk"] = mock_ttk
    sys.modules["tkinter.scrolledtext"] = mock_scroll
# ---------------------------------------------

import json
import time
import re
import threading
import pandas as pd
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QApplication, QMessageBox, QTextEdit, QListWidget, QFrame,
    QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QRect, QByteArray
from PyQt6.QtGui import QBrush, QColor, QFont, QAction

from tk_gui_modules.window_mixin import WindowMixin
from ats.ui.base_table import BaseATSTableWidget
from ats.ui.styles import NumericTableWidgetItem
from logger_utils import LoggerFactory
from sys_utils import get_app_root
from multi_period_strategy_engine import MultiPeriodStrategyEngine
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger(__name__)
_CONFIG_FILE_LOCK = threading.RLock()
_active_workers = set()


def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default


class MultiPeriodWorker(QThread):
    """
    QThread worker for running multi-period strategy evaluations in the background.
    """
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, float, object)  # result_df, elapsed, flat_df
    error = pyqtSignal(str)

    def __init__(self, engine, strat_config, active_periods, top_now=None, force_reload=False, period_cache_ts=None, top_now_cache_ts=None):
        super().__init__()
        self.engine = engine
        self.strat_config = strat_config
        self.active_periods = active_periods
        self.top_now = top_now
        self.force_reload = force_reload
        self.period_cache_ts = period_cache_ts or {}
        self.top_now_cache_ts = top_now_cache_ts or [0.0]

    def _is_cache_valid(self, ts):
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()
        if not is_trade:
            return True
        return (time.time() - ts) < 3600  # 1 hour TTL during trading hours

    def run(self):
        try:
            start_time = time.time()

            if self.force_reload:
                self.top_now = None
                self.top_now_cache_ts[0] = 0.0
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        self.engine._period_dfs.clear()
                else:
                    self.engine._period_dfs.clear()
                self.period_cache_ts.clear()

            # 1. Load market snapshots (top_now)
            if self.top_now is None or not self._is_cache_valid(self.top_now_cache_ts[0]):
                self.progress.emit("正在获取全市场实时行情...")
                from JSONData import sina_data
                _sina = sina_data.Sina(readonly=True)
                self.top_now = _sina.all
                if self.top_now is not None and not self.top_now.empty and 'ratio' not in self.top_now.columns:
                    try:
                        from JSONData import realdatajson as rl
                        dd = rl.get_sina_Market_json('all')
                        if isinstance(dd, pd.DataFrame) and 'ratio' in dd.columns:
                            self.top_now = cct.combine_dataFrame(self.top_now, dd.loc[:, ['name', 'ratio']])
                    except Exception as e:
                        logger.warning(f"Fallback ratio recovery failed: {e}")

                if self.top_now is None or self.top_now.empty:
                    self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType, readonly=True)
                self.top_now_cache_ts[0] = time.time()

            # 2. Load active periods
            for period in self.active_periods:
                cached = False
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        cached = (
                            period in self.engine._period_dfs
                            and not self.engine._period_dfs[period].empty
                            and self._is_cache_valid(self.period_cache_ts.get(period, 0.0))
                        )
                else:
                    cached = (
                        period in self.engine._period_dfs
                        and not self.engine._period_dfs[period].empty
                        and self._is_cache_valid(self.period_cache_ts.get(period, 0.0))
                    )

                if cached:
                    age = int(time.time() - self.period_cache_ts.get(period, 0.0))
                    self.progress.emit(f"⚡ [{period}] 命中缓存 (已存在 {age}s)，跳过重新加载")
                else:
                    self.progress.emit(f"📥 [{period}] 首次加载或缓存过期，正在读取计算...")
                    if hasattr(self.engine, "lock"):
                        with self.engine.lock:
                            self.engine._period_dfs.pop(period, None)
                    else:
                        self.engine._period_dfs.pop(period, None)
                    self.engine.load_period_data(period, self.top_now)
                    self.period_cache_ts[period] = time.time()

                    if period in self.engine._missing_periods:
                        reason = self.engine._missing_periods[period]
                        self.progress.emit(f"⚠️ [{period}] 数据不可用({reason})，策略将自适应跳过此周期过滤")

            self.progress.emit("🔍 正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(self.strat_config, self.active_periods)

            # Build flat data frame in background thread to avoid UI freeze
            flat_df = self._build_flat_df(result_df)
            elapsed = time.time() - start_time
            self.finished.emit(result_df, elapsed, flat_df)
        except Exception as e:
            import traceback
            err_stack = traceback.format_exc()
            logger.error(f"[MultiPeriodWorker] Error: {e}\n{err_stack}")
            self.error.emit(str(e))

    def _build_flat_df(self, df):
        if df is None or df.empty:
            return df
        flat_df = df.copy()
        for period in self.active_periods:
            df_p = self.engine._period_dfs.get(period)
            if df_p is not None and not df_p.empty:
                cols_to_join = [c for c in df_p.columns if c not in ('code', 'name')]
                if cols_to_join:
                    df_p_sub = df_p[cols_to_join]
                    df_p_sub = df_p_sub[~df_p_sub.index.duplicated(keep='first')]
                    df_p_sub = df_p_sub.rename(columns={c: f"{c}_{period}" for c in cols_to_join})
                    flat_df = flat_df.join(df_p_sub, how='left')
        flat_df.index.name = 'code'
        return flat_df


class MultiPeriodStrategyEditorDialog(QDialog):
    """
    PyQt6 dialog for editing multi-period filtering strategies, matching MultiPeriodStrategyEditor functionality.
    """
    def __init__(self, parent, engine, on_save_callback):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 多周期过滤策略编辑器")
        self.setMinimumSize(950, 650)
        self.engine = engine
        self.on_save_callback = on_save_callback
        self.strategies = [json.loads(json.dumps(s)) for s in self.engine.load_strategies()]
        self.current_idx = -1

        self.setStyleSheet("""
            QDialog { background-color: #1a1a24; color: #ffffff; }
            QLabel { color: #b0bec5; font-size: 12px; }
            QLineEdit, QTextEdit { background-color: #263238; color: #ffffff; border: 1px solid #37474f; border-radius: 4px; padding: 4px; }
            QListWidget { background-color: #212130; color: #ffffff; border: 1px solid #2e2e3e; border-radius: 4px; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #3f51b5; }
            QComboBox { background-color: #263238; color: #ffffff; border: 1px solid #37474f; border-radius: 4px; padding: 4px; }
            QCheckBox { color: #b0bec5; }
        """)

        # Load saved geometry
        self.config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")
        self._load_geometry()

        self._init_ui()
        self._refresh_list()

        # Select initial strategy
        if self.strategies:
            initial_idx = 0
            current_strat_id = parent.ui_state.get('strategy_id', '') if hasattr(parent, 'ui_state') else ''
            if current_strat_id:
                for idx, s in enumerate(self.strategies):
                    if s['id'] == current_strat_id:
                        initial_idx = idx
                        break
            self.list_widget.setCurrentRow(initial_idx)

    def _load_geometry(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    geom_saved = cfg.get("editor_geometry_qt")
                    if geom_saved:
                        self.restoreGeometry(QByteArray.fromHex(geom_saved.encode('utf-8')))
            except Exception as e:
                logger.warning(f"Failed to load editor geometry: {e}")

    def _save_geometry(self):
        try:
            geom = self.saveGeometry().toHex().data().decode('utf-8')
            cfg = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg["editor_geometry_qt"] = geom
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save editor geometry: {e}")

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(splitter)

        # ── Left Pane: Strategy List ──
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        lbl_list = QLabel("策略列表", self)
        lbl_list.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
        left_layout.addWidget(lbl_list)

        self.list_widget = QListWidget(self)
        self.list_widget.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("➕ 新增策略", self)
        self.btn_add.setStyleSheet("background-color: #2e7d32; border-color: #1b5e20;")
        self.btn_add.clicked.connect(self._add_strategy)
        self.btn_del = QPushButton("➖ 删除策略", self)
        self.btn_del.setStyleSheet("background-color: #c62828; border-color: #b71c1c;")
        self.btn_del.clicked.connect(self._del_strategy)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_del)
        left_layout.addLayout(btn_row)

        self.btn_import_json = QPushButton("📋 粘贴 JSON 策略", self)
        self.btn_import_json.setStyleSheet("background-color: #00796b;")
        self.btn_import_json.clicked.connect(self._import_json_strategy)
        left_layout.addWidget(self.btn_import_json)

        splitter.addWidget(left_widget)

        # ── Right Pane: Edit Configurations ──
        right_widget = QWidget(self)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)

        # 1. Strategy Name & Mode
        form_layout = QHBoxLayout()
        lbl_name = QLabel("策略名称:", self)
        self.name_edit = QLineEdit(self)
        self.name_edit.textChanged.connect(self._on_name_changed)
        form_layout.addWidget(lbl_name)
        form_layout.addWidget(self.name_edit)

        lbl_mode = QLabel("合并模式:", self)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItems(["交集 (intersection)", "并集 (union)"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form_layout.addWidget(lbl_mode)
        form_layout.addWidget(self.mode_combo)
        right_layout.addLayout(form_layout)

        # 2. Period Conditions List
        lbl_conds = QLabel("周期过滤条件 (各周期分别执行 DataFrame 过滤):", self)
        lbl_conds.setStyleSheet("font-weight: bold; color: #ffffff;")
        right_layout.addWidget(lbl_conds)

        self.cond_rows = {}
        periods = self.engine.SUPPORTED_PERIODS
        for p in periods:
            row_layout = QHBoxLayout()
            chk = QCheckBox(f"{p} 周期", self)
            chk.setFixedWidth(80)
            chk.toggled.connect(lambda checked, pd=p: self._on_enable_toggled(pd, checked))
            
            expr_edit = QLineEdit(self)
            expr_edit.setEnabled(False)
            expr_edit.textChanged.connect(lambda text, pd=p: self._on_expr_changed(pd, text))
            
            status_lbl = QLabel("未验证", self)
            status_lbl.setFixedWidth(120)
            
            btn_val = QPushButton("🔍 验证", self)
            btn_val.setEnabled(False)
            btn_val.clicked.connect(lambda checked, pd=p: self._validate_single(pd))
            
            row_layout.addWidget(chk)
            row_layout.addWidget(expr_edit)
            row_layout.addWidget(status_lbl)
            row_layout.addWidget(btn_val)
            right_layout.addLayout(row_layout)
            
            self.cond_rows[p] = {
                "chk": chk,
                "expr_edit": expr_edit,
                "status_lbl": status_lbl,
                "btn_val": btn_val
            }

        # 3. JSON Quick Editor
        line_sep = QFrame(self)
        line_sep.setFrameShape(QFrame.Shape.HLine)
        line_sep.setFrameShadow(QFrame.Shadow.Sunken)
        line_sep.setStyleSheet("background-color: #37474f;")
        right_layout.addWidget(line_sep)

        json_header = QHBoxLayout()
        lbl_json = QLabel("📋 JSON 快速编辑模式", self)
        lbl_json.setStyleSheet("font-weight: bold; color: #009688;")
        json_header.addWidget(lbl_json)

        json_header.addStretch()

        self.btn_fmt_json = QPushButton("🔄 格式化", self)
        self.btn_fmt_json.clicked.connect(self._reformat_json_editor)
        json_header.addWidget(self.btn_fmt_json)

        self.btn_copy_json = QPushButton("📋 复制", self)
        self.btn_copy_json.clicked.connect(self._copy_json_to_clipboard)
        json_header.addWidget(self.btn_copy_json)

        self.btn_apply_json = QPushButton("✅ 应用JSON", self)
        self.btn_apply_json.setStyleSheet("background-color: #00796b;")
        self.btn_apply_json.clicked.connect(self._apply_json_to_form)
        json_header.addWidget(self.btn_apply_json)
        right_layout.addLayout(json_header)

        self.json_editor = QTextEdit(self)
        self.json_editor.setFont(QFont("Consolas", 10))
        self.json_editor.setStyleSheet("background-color: #111116; color: #81d4fa;")
        right_layout.addWidget(self.json_editor)

        # ── Bottom Action Buttons ──
        bottom_layout = QHBoxLayout()
        self.btn_validate_all = QPushButton("🔍 验证全部条件", self)
        self.btn_validate_all.setStyleSheet("background-color: #0288d1;")
        self.btn_validate_all.clicked.connect(self._validate_all)
        bottom_layout.addWidget(self.btn_validate_all)

        bottom_layout.addStretch()

        self.btn_save = QPushButton("💾 保存并应用", self)
        self.btn_save.setStyleSheet("background-color: #2e7d32;")
        self.btn_save.clicked.connect(self._save_to_engine)
        bottom_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("❌ 取消", self)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        right_layout.addLayout(bottom_layout)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

    def _refresh_list(self):
        self.list_widget.clear()
        for s in self.strategies:
            self.list_widget.addItem(s['name'])

    def _on_select(self, row):
        if row < 0 or row >= len(self.strategies):
            self.current_idx = -1
            return

        self.current_idx = row
        strat = self.strategies[row]

        # Block signals temporarily to prevent loop updates
        self.name_edit.blockSignals(True)
        self.mode_combo.blockSignals(True)

        self.name_edit.setText(strat['name'])
        mode_str = "并集 (union)" if strat.get('cross_mode') == 'union' else "交集 (intersection)"
        self.mode_combo.setCurrentText(mode_str)

        self.name_edit.blockSignals(False)
        self.mode_combo.blockSignals(False)

        # Load period filters
        conds = strat.get('conditions', {})
        for period, widgets in self.cond_rows.items():
            widgets['chk'].blockSignals(True)
            widgets['expr_edit'].blockSignals(True)

            cond = conds.get(period, {})
            is_enabled = cond.get('enabled', False)
            widgets['chk'].setChecked(is_enabled)
            widgets['expr_edit'].setEnabled(is_enabled)
            widgets['btn_val'].setEnabled(is_enabled)
            widgets['expr_edit'].setText(cond.get('filter', ''))
            widgets['status_lbl'].setText("未验证")
            widgets['status_lbl'].setStyleSheet("color: gray;")

            widgets['chk'].blockSignals(False)
            widgets['expr_edit'].blockSignals(False)

        # Display json representation
        self._refresh_json_editor()

    def _on_name_changed(self, text):
        if self.current_idx >= 0:
            self.strategies[self.current_idx]['name'] = text.strip()
            self.list_widget.item(self.current_idx).setText(text.strip() or "未命名策略")
            self._refresh_json_editor()

    def _on_mode_changed(self, idx):
        if self.current_idx >= 0:
            mode_text = self.mode_combo.currentText()
            self.strategies[self.current_idx]['cross_mode'] = 'union' if 'union' in mode_text else 'intersection'
            self._refresh_json_editor()

    def _on_enable_toggled(self, period, checked):
        if self.current_idx >= 0:
            strat = self.strategies[self.current_idx]
            if 'conditions' not in strat:
                strat['conditions'] = {}
            if period not in strat['conditions']:
                strat['conditions'][period] = {'filter': '', 'enabled': False}
            strat['conditions'][period]['enabled'] = checked

            widgets = self.cond_rows[period]
            widgets['expr_edit'].setEnabled(checked)
            widgets['btn_val'].setEnabled(checked)
            if not checked:
                widgets['status_lbl'].setText("未验证")
                widgets['status_lbl'].setStyleSheet("color: gray;")

            self._refresh_json_editor()

    def _on_expr_changed(self, period, text):
        if self.current_idx >= 0:
            strat = self.strategies[self.current_idx]
            if 'conditions' not in strat:
                strat['conditions'] = {}
            if period not in strat['conditions']:
                strat['conditions'][period] = {'filter': '', 'enabled': True}
            strat['conditions'][period]['filter'] = text.strip()
            self.cond_rows[period]['status_lbl'].setText("未验证")
            self.cond_rows[period]['status_lbl'].setStyleSheet("color: gray;")
            self._refresh_json_editor()

    def _refresh_json_editor(self):
        if self.current_idx >= 0:
            try:
                js_str = json.dumps(self.strategies[self.current_idx], ensure_ascii=False, indent=2)
                self.json_editor.blockSignals(True)
                self.json_editor.setPlainText(js_str)
                self.json_editor.blockSignals(False)
            except Exception as e:
                logger.error(f"JSON serialization error: {e}")

    def _apply_json_to_form(self):
        if self.current_idx < 0:
            return
        try:
            raw_js = self.json_editor.toPlainText().strip()
            data = json.loads(raw_js)
            # Ensure critical keys exist
            if 'name' not in data or 'conditions' not in data:
                raise ValueError("JSON standard template keys missing ('name', 'conditions').")
            
            # Map ID persistence
            data['id'] = self.strategies[self.current_idx].get('id', data.get('id', str(int(time.time() * 1000))))
            
            self.strategies[self.current_idx] = data
            self._on_select(self.current_idx)
            QMessageBox.information(self, "成功", "JSON 配置应用成功！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"解析/应用 JSON 失败: {e}")

    def _copy_json_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.json_editor.toPlainText())
        QMessageBox.information(self, "提示", "策略 JSON 已复制到剪贴板！")

    def _reformat_json_editor(self):
        try:
            raw_js = self.json_editor.toPlainText().strip()
            if raw_js:
                data = json.loads(raw_js)
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                self.json_editor.setPlainText(formatted)
        except Exception as e:
            QMessageBox.critical(self, "格式化失败", f"无效的 JSON 字符串: {e}")

    def _add_strategy(self):
        new_id = str(int(time.time() * 1000))
        new_strat = {
            "id": new_id,
            "name": f"新策略_{new_id[-4:]}",
            "cross_mode": "intersection",
            "conditions": {
                "d": {"filter": "close > ma20d", "enabled": True}
            }
        }
        self.strategies.append(new_strat)
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self.strategies) - 1)

    def _del_strategy(self):
        if self.current_idx < 0:
            return
        
        reply = QMessageBox.question(
            self, "确认删除", f"确定删除策略【{self.strategies[self.current_idx]['name']}】吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.strategies.pop(self.current_idx)
            self._refresh_list()
            new_idx = min(self.current_idx, len(self.strategies) - 1)
            if new_idx >= 0:
                self.list_widget.setCurrentRow(new_idx)
            else:
                self.current_idx = -1
                self.name_edit.clear()
                self.json_editor.clear()

    def _import_json_strategy(self):
        clipboard = QApplication.clipboard()
        raw_text = clipboard.text().strip()
        if not raw_text:
            QMessageBox.warning(self, "警告", "剪贴板为空！")
            return
        try:
            data = json.loads(raw_text)
            if isinstance(data, dict) and 'name' in data and 'conditions' in data:
                data['id'] = str(int(time.time() * 1000))
                self.strategies.append(data)
                self._refresh_list()
                self.list_widget.setCurrentRow(len(self.strategies) - 1)
                QMessageBox.information(self, "成功", "策略导入成功！")
            else:
                raise ValueError("JSON必须是包含 'name' 和 'conditions' 字段的字典。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"从剪贴板解析/导入策略 JSON 失败: {e}")

    def _validate_single(self, period):
        widgets = self.cond_rows[period]
        expr = widgets['expr_edit'].text().strip()
        if not expr:
            widgets['status_lbl'].setText("❌ 条件为空")
            widgets['status_lbl'].setStyleSheet("color: red;")
            return False

        # Load period mock dataframe schema validation
        df_p = self.engine._period_dfs.get(period)
        if df_p is None or df_p.empty:
            # Load mock layout to validate columns
            try:
                self.engine.load_period_data(period, None)
                df_p = self.engine._period_dfs.get(period)
            except Exception:
                pass

        if df_p is None or df_p.empty:
            widgets['status_lbl'].setText("⚠️ 无法载入周期数据验证")
            widgets['status_lbl'].setStyleSheet("color: #ff9100;")
            return True

        try:
            df_p.query(expr)
            widgets['status_lbl'].setText("✅ 语法正确")
            widgets['status_lbl'].setStyleSheet("color: #4caf50;")
            return True
        except Exception as e:
            widgets['status_lbl'].setText(f"❌ 语法错误")
            widgets['status_lbl'].setStyleSheet("color: #f44336;")
            widgets['status_lbl'].setToolTip(str(e))
            return False

    def _validate_all(self):
        success = True
        for period, widgets in self.cond_rows.items():
            if widgets['chk'].isChecked():
                res = self._validate_single(period)
                if not res:
                    success = False
        if success:
            QMessageBox.information(self, "验证完成", "全部激活的条件均通过了语法校验！")
        else:
            QMessageBox.warning(self, "验证失败", "部分周期的过滤表达式包含语法错误，请查看标记！")

    def _save_to_engine(self):
        # Perform saving
        try:
            self.engine.save_strategies(self.strategies)
            self.on_save_callback(self.strategies)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存策略文件出错: {e}")


class QueryHistoryDialog(QDialog):
    """
    Native PyQt6 window for secondary filter query history management.
    """
    applied = pyqtSignal(str)

    def __init__(self, parent, history_file):
        super().__init__(parent)
        self.setWindowTitle("📜 过滤表达式历史管理")
        self.setMinimumSize(850, 480)
        self.history_file = history_file
        self.his_limit = 100

        self.setStyleSheet("""
            QDialog { background-color: #1a1a24; color: #ffffff; }
            QLabel { color: #b0bec5; font-size: 12px; }
            QLineEdit { background-color: #263238; color: #ffffff; border: 1px solid #37474f; border-radius: 4px; padding: 4px; }
            QTableWidget { background-color: #212130; color: #ffffff; gridline-color: #2e2e3e; border: 1px solid #2e2e3e; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #3f51b5; }
            QComboBox { background-color: #263238; color: #ffffff; border: 1px solid #37474f; border-radius: 4px; padding: 4px; }
        """)

        # Load history
        self._load_history()

        self._init_ui()
        self._refresh_table()

    def _load_history(self):
        self.history_groups = {
            "history1": [],
            "history2": [],
            "history3": [],
            "history4": [],
            "history5": []
        }
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for grp in self.history_groups.keys():
                        raw_list = data.get(grp, [])
                        normalized = []
                        for r in raw_list:
                            if isinstance(r, dict):
                                q = r.get("query", "").strip()
                                note = r.get("note", "").strip()
                                starred = r.get("starred", 0)
                                if isinstance(starred, bool):
                                    starred = 1 if starred else 0
                                normalized.append({"query": q, "note": note, "starred": starred})
                            elif isinstance(r, str):
                                normalized.append({"query": r.strip(), "note": "", "starred": 0})
                        self.history_groups[grp] = normalized[:self.his_limit]
            except Exception as e:
                logger.error(f"Failed to load search history: {e}")

    def _save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_groups, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save search history: {e}")

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Global Search
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 全局搜索:", self))
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("在所有组别中查找包含的条件或备注")
        self.search_edit.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_edit)
        
        btn_search = QPushButton("搜索所有历史", self)
        btn_search.clicked.connect(self._do_search)
        search_layout.addWidget(btn_search)
        layout.addLayout(search_layout)

        # Input & Controls
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("表达式:", self))
        self.query_edit = QLineEdit(self)
        input_layout.addWidget(self.query_edit)

        self.grp_combo = QComboBox(self)
        self.grp_combo.addItems(["history1", "history2", "history3", "history4", "history5"])
        self.grp_combo.currentIndexChanged.connect(self._on_group_changed)
        input_layout.addWidget(self.grp_combo)

        btn_add = QPushButton("添加", self)
        btn_add.clicked.connect(self._add_query)
        input_layout.addWidget(btn_add)

        btn_apply = QPushButton("使用选中", self)
        btn_apply.setStyleSheet("background-color: #2e7d32;")
        btn_apply.clicked.connect(self._use_selected)
        input_layout.addWidget(btn_apply)
        layout.addLayout(input_layout)

        # Table Widget
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Query 表达式", "⭐", "备注说明", "Group 组别"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._use_selected)
        self.table.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.table)

        # Header stretch
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 40)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 100)

        # Bottom Bar
        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel("准备就绪", self)
        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        
        btn_save = QPushButton("💾 保存", self)
        btn_save.clicked.connect(self._save_and_toast)
        bottom_layout.addWidget(btn_save)
        
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.close)
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

    def _refresh_table(self):
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        self.table.setRowCount(len(items))

        for idx, item in enumerate(items):
            # Query
            q_item = QTableWidgetItem(item.get("query", ""))
            self.table.setItem(idx, 0, q_item)

            # Star
            star_text = "⭐" if item.get("starred", 0) == 1 else "☆"
            star_item = QTableWidgetItem(star_text)
            star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 1, star_item)

            # Note
            note_item = QTableWidgetItem(item.get("note", ""))
            self.table.setItem(idx, 2, note_item)

            # Group
            grp_item = QTableWidgetItem(grp)
            grp_item.setFlags(grp_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 3, grp_item)

    def _on_group_changed(self):
        self._refresh_table()

    def _on_item_clicked(self, item):
        row = item.row()
        col = item.column()
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        
        if row < 0 or row >= len(items):
            return

        if col == 1:  # Star Column
            starred = items[row].get("starred", 0)
            items[row]["starred"] = 0 if starred == 1 else 1
            self._save_history()
            self._refresh_table()
        else:
            self.query_edit.setText(items[row].get("query", ""))

    def _add_query(self):
        q = self.query_edit.text().strip()
        if not q:
            return
        
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        
        # Check duplicate
        for item in items:
            if item.get("query") == q:
                QMessageBox.information(self, "提示", "该过滤条件已存在于当前组中。")
                return

        items.insert(0, {"query": q, "note": "", "starred": 0})
        self.history_groups[grp] = items[:self.his_limit]
        self._save_history()
        self._refresh_table()
        self.lbl_status.setText(f"已添加条件到 {grp}")

    def _do_search(self):
        kw = self.search_edit.text().strip().lower()
        if not kw:
            self._refresh_table()
            return

        results = []
        for grp, items in self.history_groups.items():
            for item in items:
                q = item.get("query", "").lower()
                n = item.get("note", "").lower()
                if kw in q or kw in n:
                    results.append((grp, item))

        if not results:
            QMessageBox.information(self, "搜索结果", f"未找到包含 '{kw}' 的记录")
            return

        self.table.setRowCount(len(results))
        for idx, (grp, item) in enumerate(results):
            q_item = QTableWidgetItem(item.get("query", ""))
            self.table.setItem(idx, 0, q_item)

            star_text = "⭐" if item.get("starred", 0) == 1 else "☆"
            star_item = QTableWidgetItem(star_text)
            star_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 1, star_item)

            note_item = QTableWidgetItem(item.get("note", ""))
            self.table.setItem(idx, 2, note_item)

            grp_item = QTableWidgetItem(grp)
            grp_item.setFlags(grp_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 3, grp_item)

    def _use_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        q_item = self.table.item(row, 0)
        if q_item:
            query = q_item.text().strip()
            self.applied.emit(query)
            self.accept()

    def _save_and_toast(self):
        # Save modifications in notes from QTableWidget back to data
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        for row in range(self.table.rowCount()):
            # Safe safeguard in case of searched table
            q_item = self.table.item(row, 0)
            note_item = self.table.item(row, 2)
            grp_item = self.table.item(row, 3)
            
            if q_item and note_item and grp_item:
                target_grp = grp_item.text()
                target_q = q_item.text()
                target_note = note_item.text()
                
                target_items = self.history_groups.get(target_grp, [])
                for item in target_items:
                    if item.get("query") == target_q:
                        item["note"] = target_note
                        break
        
        self._save_history()
        self.lbl_status.setText("✅ 历史记录备注已保存！")


class ConceptStocksDialog(QDialog):
    """
    Sub dialog showing all stocks matching a selected concept.
    """
    def __init__(self, parent, concept_name, matched_stocks, columns, headers):
        super().__init__(parent)
        self.setWindowTitle(f"板块【{concept_name}】个股列表")
        self.setMinimumSize(800, 450)
        self.matched_stocks = matched_stocks
        self.columns = columns
        self.headers = headers

        self.setStyleSheet("""
            QDialog { background-color: #161822; color: #ffffff; }
            QTableWidget { background-color: #212130; color: #ffffff; gridline-color: #2e2e3e; border: 1px solid #2e2e3e; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #3f51b5; }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = BaseATSTableWidget(self)
        self.table.setColumnCount(len(self.columns) + 1)
        self.table.setHorizontalHeaderLabels(["序号"] + [self.headers.get(col, col) for col in self.columns])
        p = self.parent()
        if p and hasattr(p, 'link_stock'):
            self.table.stock_activated.connect(p.link_stock)
        layout.addWidget(self.table)

        # Populate
        self.table.setRowCount(len(self.matched_stocks))
        for idx, (code, row) in enumerate(self.matched_stocks):
            idx_item = NumericTableWidgetItem(str(idx + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 0, idx_item)

            for c_idx, col in enumerate(self.columns, 1):
                if col == 'code':
                    val = code
                elif col == 'price':
                    val = row.get('close', row.get('price', '--'))
                else:
                    val = row.get(col, '--')

                if pd.isna(val):
                    val = '--'
                
                # Check for float formatting
                if isinstance(val, (int, float)):
                    if col in ('price', 'percent', 'volume', 'ratio') or col.startswith('pass_'):
                        val_str = f"{val:.2f}"
                    else:
                        val_str = str(val)
                    item = NumericTableWidgetItem(val_str)
                    
                    # Color A-share涨跌幅
                    if col == 'percent':
                        if val > 0:
                            item.setForeground(QBrush(QColor("#ff4444")))
                        elif val < 0:
                            item.setForeground(QBrush(QColor("#33cc5a")))
                else:
                    item = QTableWidgetItem(str(val))
                    if col == 'percent' and val != '--':
                        try:
                            f_val = float(str(val).replace('%', ''))
                            if f_val > 0:
                                item.setForeground(QBrush(QColor("#ff4444")))
                            elif f_val < 0:
                                item.setForeground(QBrush(QColor("#33cc5a")))
                        except Exception:
                            pass
                
                self.table.setItem(idx, c_idx, item)

        if len(self.matched_stocks) > 0:
            self.table.setCurrentCell(0, 1)
            self.table.setFocus()

        # Apply persistence and interactive resizing
        default_widths = {0: 35}
        for idx, col in enumerate(self.columns, 1):
            if col == "code":
                w = 55
            elif col == "name":
                w = 65
            elif col == "price":
                w = 50
            elif col == "percent":
                w = 55
            elif col == "volume":
                w = 60
            elif col == "ratio":
                w = 45
            elif col.startswith("pass_"):
                w = 55
            else:
                w = 50
            default_widths[idx] = w

        self.table.setup_persistence("concept_stocks_table", default_widths=default_widths)
        if not getattr(self.table, "_first_width_applied", False):
            self.table._first_width_applied = True
            for idx, w in default_widths.items():
                self.table.setColumnWidth(idx, w)

        # Action Buttons
        action_layout = QHBoxLayout()
        btn_diag = QPushButton("🔍 诊断所选个股", self)
        btn_diag.setStyleSheet("background-color: #0288d1;")
        btn_diag.clicked.connect(self._diagnose_stock)
        action_layout.addWidget(btn_diag)

        btn_dna = QPushButton("🧬 DNA审计所选", self)
        btn_dna.setStyleSheet("background-color: #2e7d32;")
        btn_dna.clicked.connect(self._dna_audit_stock)
        action_layout.addWidget(btn_dna)
        
        action_layout.addStretch()
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.close)
        action_layout.addWidget(btn_close)
        layout.addLayout(action_layout)

    def _diagnose_stock(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        
        # Code is in column 1 (index 1)
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            self.parent().diagnose_stock_strategy(code, name)

    def _dna_audit_stock(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            code_to_name = {code: name}
            
            # Reconstruct resample from active periods
            active_periods = [p for p, chk in self.parent().period_checkboxes.items() if chk.isChecked()]
            PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
            sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
            min_period = sorted_periods[0] if sorted_periods else 'd'
            
            self.parent()._run_dna_audit_batch(code_to_name, resample=min_period)


class ConceptDetailDialog(QDialog):
    """
    Sub dialog displaying detailed frequency statistics of concept sectors.
    """
    def __init__(self, parent, all_concepts, concept_to_codes):
        super().__init__(parent)
        self.setWindowTitle("📊 概念板块统计详情")
        self.setMinimumSize(450, 550)
        self.all_concepts = all_concepts
        self.concept_to_codes = concept_to_codes

        self.setStyleSheet("""
            QDialog { background-color: #161822; color: #ffffff; }
            QTableWidget { background-color: #212130; color: #ffffff; gridline-color: #2e2e3e; border: 1px solid #2e2e3e; }
        """)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel(f"📊 概念板块统计详情 (共 {len(self.all_concepts)} 个)", self)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #00b0ff;")
        layout.addWidget(lbl)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["序号", "概念板块名称", "股票只数"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        # Stretch columns
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 35)
        self.table.setColumnWidth(2, 65)

        # Populate
        self.table.setRowCount(len(self.all_concepts))
        for idx, (cat_name, count) in enumerate(self.all_concepts):
            idx_item = NumericTableWidgetItem(str(idx + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 0, idx_item)

            name_item = QTableWidgetItem(cat_name)
            name_item.setForeground(QBrush(QColor("#80d8ff")))
            self.table.setItem(idx, 1, name_item)

            count_item = NumericTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 2, count_item)

    def _on_double_click(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        name_item = self.table.item(row, 1)
        if name_item:
            concept_name = name_item.text().strip()
            self.parent().show_concept_top10_window(concept_name)


class StockCategoryDetailDialog(QDialog):
    """
    Sub dialog displaying detailed category details for a specific stock.
    """
    def __init__(self, parent, code, name, category_str):
        super().__init__(parent)
        self.setWindowTitle(f"🏷️ 个股分类详情: {name}({code})")
        self.setMinimumSize(400, 250)

        self.setStyleSheet("""
            QDialog { background-color: #161822; color: #ffffff; }
            QTextEdit { background-color: #212130; color: #ffffff; border: 1px solid #2e2e3e; font-size: 13px; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 6px 12px; }
            QPushButton:hover { background-color: #3f51b5; }
        """)

        layout = QVBoxLayout(self)

        lbl = QLabel(f"个股: {name} ({code}) 分类与概念标签列表:", self)
        lbl.setStyleSheet("font-weight: bold; color: #00b0ff;")
        layout.addWidget(lbl)

        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setPlainText(category_str)
        layout.addWidget(self.text_area)

        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)


class MultiPeriodDialog(QDialog, WindowMixin):
    """
    PyQt6 dialog representing the multi-period Strategy Tester.
    Subclasses BaseATSTableWidget and implements WindowMixin snapping.
    """
    code_clicked = pyqtSignal(str, str)  # Linkage emission
    status_message_signal = pyqtSignal(str) # Thread-safe status message updater

    def __init__(self, parent=None):
        super().__init__(parent)
        self._initializing = True
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("⏱️ 多周期交叉筛选与诊断系统")
        self.setMinimumSize(800, 500)

        # Config File Setup
        self.config_file = os.path.join(get_app_root(), "config", "standalone_tester_config.json")

        self._is_updating = False
        self._last_flat_df = None
        self._last_selected_code = None
        self._current_history_query = ""
        self._history_filter_error = None
        self.top_now = None
        self._top_now_cache_ts = [0.0]
        self._period_cache_ts = {}
        self.last_result_df = None
        self.last_elapsed = 0.0
        self._block_cache = {}

        # Snapping setup
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
        self.setWindowFlags(flags)

        self.load_window_position_qt(self, "multi_period_dialog", default_width=1100, default_height=700)

        self.setStyleSheet("""
            QDialog { background-color: #121216; color: #e2e2e5; }
            QLabel { color: #b0bec5; font-size: 12px; }
            QLineEdit { background-color: #212130; color: #ffffff; border: 1px solid #2e2e3e; border-radius: 4px; padding: 4px; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 5px 10px; font-weight: bold; }
            QPushButton:hover { background-color: #3f51b5; }
            QComboBox { background-color: #212130; color: #ffffff; border: 1px solid #2e2e3e; border-radius: 4px; padding: 4px; }
            QCheckBox { color: #b0bec5; }
            QSplitter::handle { background-color: #2e2e3e; }
        """)

        # Initialize Strategy Engine
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.manual_col_pool = []

        self.ui_state = self._load_state()

        self._in_adjust_widths = False
        self._init_ui()
        self._apply_state()

        # Thread-safe status update connection
        self.status_message_signal.connect(self.lbl_status.setText)

        # Connect signals after state application to avoid redundant triggers
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_selected)
        self.table.horizontalHeader().sectionResized.connect(self._on_section_resized)
        self.link_vis_chk.toggled.connect(self._save_state)
        self.link_tdx_chk.toggled.connect(self._save_state)
        self.link_ths_chk.toggled.connect(self._save_state)
        self.on_top_chk.toggled.connect(self._on_top_toggled)

        # Linkage: BaseATSTableWidget's internal 80ms debounce handles the
        # coalescing; link_stock just needs a same-code guard to skip redundant IPC calls
        self._pending_link_code = None
        self._pending_link_name = None

        # Enable strong keyboard focus policy for base table to capture Up/Down arrow keys
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Favorites poll: 3s interval — low-frequency to avoid constant allocation
        try:
            from global_favorites import GlobalFavoriteManager
            self._last_favorites_version = GlobalFavoriteManager().version
            self.favorites_timer = QTimer(self)
            self.favorites_timer.timeout.connect(self._poll_favorites_loop)
            self.favorites_timer.start(3000)
        except Exception:
            pass

        self._initializing = False

    def get_stock_name(self, code):
        from sys_utils import resolve_stock_name
        return resolve_stock_name(code) or "未知个股"

    def _is_cache_valid(self, ts):
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()
        if not is_trade:
            return True
        return (time.time() - ts) < 3600  # 1 hour TTL during trading hours

    def _load_stays_on_top(self):
        self.ui_state = self._load_state()
        return self.ui_state.get("stays_on_top", False)

    def _load_state(self):
        default_state = {
            "strategy_id": "",
            "periods": ["d", "w", "m"],
            "custom_cols": [],
            "stays_on_top": False,
            "manual_col_pool": [],
            "link_vis": True,
            "link_tdx": False,
            "link_ths": False,
            "sort_level1_col": None,
            "sort_level1_asc": True,
            "sortby_col": None,
            "sortby_col_ascend": False,
            "current_history_query": ""
        }
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in default_state.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception:
                pass
        return default_state

    def _save_state(self, write_to_disk=False):
        if getattr(self, "_initializing", False):
            return
        try:
            strat_name = self.strategy_combo.currentText()
            strat_id = ""
            for s in self.strategies:
                if s['name'] == strat_name:
                    strat_id = s['id']
                    break
            
            self.ui_state['strategy_id'] = strat_id
            self.ui_state['periods'] = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
            self.ui_state['custom_cols'] = [c for c, act in self.custom_col_actions.items() if act.isChecked()]
            self.ui_state['manual_col_pool'] = list(self.manual_col_pool)
            self.ui_state['link_vis'] = self.link_vis_chk.isChecked()
            self.ui_state['link_tdx'] = self.link_tdx_chk.isChecked()
            self.ui_state['link_ths'] = self.link_ths_chk.isChecked()
            self.ui_state['stays_on_top'] = self.on_top_chk.isChecked()
            self.ui_state['current_history_query'] = self._current_history_query

            if write_to_disk == "FORCE_WRITE":
                cfg = {}
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)

                for k, v in self.ui_state.items():
                    if k != "editor_geometry_qt":
                        cfg[k] = v

                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")

    def _on_top_toggled(self, checked):
        self.stays_on_top = checked
        self._save_state()
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # ── Toolbar 1: Strategy Selection & Execution ──
        tb1_layout = QHBoxLayout()
        tb1_layout.addWidget(QLabel("策略:", self))
        self.strategy_combo = QComboBox(self)
        self.strategy_combo.setFixedWidth(200)
        self.strategy_combo.addItems([s['name'] for s in self.strategies])
        tb1_layout.addWidget(self.strategy_combo)

        btn_edit_strat = QPushButton("⚙", self)
        btn_edit_strat.setFixedWidth(30)
        btn_edit_strat.clicked.connect(self.open_strategy_editor)
        tb1_layout.addWidget(btn_edit_strat)

        tb1_layout.addWidget(QLabel(" 参与周期:", self))
        self.period_checkboxes = {}
        for p in self.engine.SUPPORTED_PERIODS:
            chk = QCheckBox(p, self)
            chk.toggled.connect(self._on_period_changed)
            tb1_layout.addWidget(chk)
            self.period_checkboxes[p] = chk

        tb1_layout.addStretch()

        btn_run = QPushButton("▶ 运行筛选", self)
        btn_run.setStyleSheet("background-color: #2e7d32;")
        btn_run.clicked.connect(lambda: self.run_filter(force_reload=False))
        tb1_layout.addWidget(btn_run)

        btn_reload = QPushButton("🔄 强制刷新", self)
        btn_reload.setStyleSheet("background-color: #ff6f00;")
        btn_reload.clicked.connect(lambda: self.run_filter(force_reload=True))
        tb1_layout.addWidget(btn_reload)

        self.btn_dragon = QPushButton("🐉 龙头监控", self)
        self.btn_dragon.setStyleSheet("background-color: #37474f;")
        self.btn_dragon.clicked.connect(self.open_dragon_monitor)
        tb1_layout.addWidget(self.btn_dragon)

        main_layout.addLayout(tb1_layout)

        # ── Toolbar 2: Custom Columns ──
        tb2_layout = QHBoxLayout()
        tb2_layout.addWidget(QLabel("手动列:", self))
        self.manual_col_edit = QLineEdit(self)
        self.manual_col_edit.setPlaceholderText("自定义列名称")
        self.manual_col_edit.setFixedWidth(120)
        self.manual_col_edit.returnPressed.connect(self._add_manual_col)
        tb2_layout.addWidget(self.manual_col_edit)

        btn_add_col = QPushButton("+", self)
        btn_add_col.setFixedWidth(30)
        btn_add_col.setStyleSheet("background-color: #1b5e20; color: #ffffff;")
        btn_add_col.clicked.connect(self._add_manual_col)
        tb2_layout.addWidget(btn_add_col)

        btn_remove_col = QPushButton("-", self)
        btn_remove_col.setFixedWidth(30)
        btn_remove_col.setStyleSheet("background-color: #b71c1c; color: #ffffff;")
        btn_remove_col.clicked.connect(self._remove_manual_col)
        tb2_layout.addWidget(btn_remove_col)

        # Dropdown selection menu for custom columns
        self.btn_custom_cols_menu = QPushButton("⚙️ 自定义列 ▼", self)
        self.custom_cols_menu = QMenu(self)
        self.custom_cols_menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; color: #ffffff; border: 1px solid #37474f; }
            QMenu::item:selected { background-color: #293952; }
        """)
        self.btn_custom_cols_menu.setMenu(self.custom_cols_menu)
        tb2_layout.addWidget(self.btn_custom_cols_menu)

        tb2_layout.addStretch()

        # Secondary Filter Query
        tb2_layout.addWidget(QLabel("🔍 历史/二次过滤:", self))
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("例如: dff > 2.0 and close > 10")
        self.filter_edit.setFixedWidth(250)
        self.filter_edit.returnPressed.connect(self._apply_secondary_filter_from_edit)
        tb2_layout.addWidget(self.filter_edit)

        btn_clear_filter = QPushButton("❌", self)
        btn_clear_filter.setFixedWidth(30)
        btn_clear_filter.clicked.connect(self._clear_secondary_filter)
        tb2_layout.addWidget(btn_clear_filter)

        btn_history = QPushButton("📜 历史管理", self)
        btn_history.clicked.connect(self._open_history_dialog)
        tb2_layout.addWidget(btn_history)

        main_layout.addLayout(tb2_layout)

        # ── Plate/Concept Display Bar ──
        concept_layout = QHBoxLayout()
        lbl_concept_title = QLabel("当前概念:", self)
        lbl_concept_title.setStyleSheet("font-weight: bold; color: #4caf50; font-size: 13px;")
        concept_layout.addWidget(lbl_concept_title)

        self.concept_flow_widget = QWidget(self)
        self.concept_flow_layout = QHBoxLayout(self.concept_flow_widget)
        self.concept_flow_layout.setContentsMargins(0, 0, 0, 0)
        concept_layout.addWidget(self.concept_flow_widget)

        self.lbl_empty_concept = QLabel("暂无板块数据", self)
        self.lbl_empty_concept.setStyleSheet("color: #757575;")
        self.concept_flow_layout.addWidget(self.lbl_empty_concept)
        concept_layout.addStretch()

        main_layout.addLayout(concept_layout)

        # ── Results Data Table (BaseATSTableWidget) ──
        # BaseATSTableWidget already handles currentCellChanged + debounce internally
        # and emits stock_activated → we just connect to link_stock
        self.table = BaseATSTableWidget(self)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.stock_activated.connect(self.link_stock)
        main_layout.addWidget(self.table)

        # ── Bottom Status Bar ──
        status_bar_layout = QHBoxLayout()
        
        self.lbl_status = QLabel("准备就绪", self)
        self.lbl_status.setStyleSheet("color: #4fc3f7; font-weight: bold;")
        status_bar_layout.addWidget(self.lbl_status)
        
        status_bar_layout.addStretch()

        # Linkage configurations
        status_bar_layout.addWidget(QLabel("联动方式:", self))
        self.link_vis_chk = QCheckBox("Vis", self)
        self.link_vis_chk.setChecked(True)
        status_bar_layout.addWidget(self.link_vis_chk)

        self.link_tdx_chk = QCheckBox("Tdx", self)
        status_bar_layout.addWidget(self.link_tdx_chk)

        self.link_ths_chk = QCheckBox("Ths", self)
        status_bar_layout.addWidget(self.link_ths_chk)

        self.on_top_chk = QCheckBox("置顶", self)
        self.on_top_chk.setChecked(self.stays_on_top)
        status_bar_layout.addWidget(self.on_top_chk)

        # Diagnostics
        status_bar_layout.addWidget(QLabel(" 诊断个股:", self))
        self.diag_edit = QLineEdit(self)
        self.diag_edit.setPlaceholderText("代码")
        self.diag_edit.setFixedWidth(80)
        self.diag_edit.returnPressed.connect(self._on_diagnose_click)
        status_bar_layout.addWidget(self.diag_edit)

        btn_diag = QPushButton("🔍 诊断", self)
        btn_diag.setStyleSheet("background-color: #0288d1;")
        btn_diag.clicked.connect(self._on_diagnose_click)
        status_bar_layout.addWidget(btn_diag)

        btn_dna = QPushButton("🧬 DNA审计", self)
        btn_dna.setStyleSheet("background-color: #2e7d32;")
        btn_dna.clicked.connect(self._on_diagnose_dna_click)
        status_bar_layout.addWidget(btn_dna)

        self.lbl_final_stats = QLabel("【最终筛选结果】暂无数据", self)
        self.lbl_final_stats.setStyleSheet("font-weight: bold; color: #81c784;")
        status_bar_layout.addWidget(self.lbl_final_stats)

        main_layout.addLayout(status_bar_layout)

        # Setup custom column actions list
        self.custom_col_actions = {}
        self._rebuild_custom_cols_menu()

    def _apply_state(self):
        # 1. Apply active strategy
        if self.strategies:
            strat_name = self.strategies[0]['name']
            for s in self.strategies:
                if s['id'] == self.ui_state.get('strategy_id'):
                    strat_name = s['name']
                    break
            self.strategy_combo.setCurrentText(strat_name)

        # 2. Apply active periods
        for p in self.ui_state.get('periods', []):
            if p in self.period_checkboxes:
                self.period_checkboxes[p].setChecked(True)

        # 3. Apply active custom columns
        for c in self.ui_state.get('custom_cols', []):
            if c in self.custom_col_actions:
                self.custom_col_actions[c].setChecked(True)

        # 4. Apply manual column pool
        self.manual_col_pool = self.ui_state.get('manual_col_pool', [])
        self._rebuild_custom_cols_menu()

        # 5. Apply linkage checks
        self.link_vis_chk.setChecked(self.ui_state.get('link_vis', True))
        self.link_tdx_chk.setChecked(self.ui_state.get('link_tdx', False))
        self.link_ths_chk.setChecked(self.ui_state.get('link_ths', False))

        # 6. Apply secondary filter query
        self._current_history_query = self.ui_state.get('current_history_query', '')
        self.filter_edit.setText(self._current_history_query)

    def _rebuild_custom_cols_menu(self):
        self.custom_cols_menu.clear()
        
        default_cols = ["dff", "dff2", "dff3", "Rank", "upper", "lower", "ma5d", "ma20d", "ma60d", "lastp1d"]
        all_cols = list(default_cols)
        for col in self.manual_col_pool:
            if col not in all_cols:
                all_cols.append(col)

        self.custom_col_actions = {}
        for c in all_cols:
            act = QAction(c, self, checkable=True)
            # Re-read active states
            is_active = c in self.ui_state.get('custom_cols', [])
            act.setChecked(is_active)
            act.triggered.connect(self._on_custom_col_changed)
            self.custom_cols_menu.addAction(act)
            self.custom_col_actions[c] = act

    def _on_strategy_selected(self):
        if getattr(self, "_initializing", False):
            return
        self._save_state()
        self.run_filter(force_reload=False)

    def _on_period_changed(self):
        if getattr(self, "_initializing", False):
            return
        self._save_state()
        self.run_filter(force_reload=False)

    def _on_section_resized(self, logicalIndex, oldSize, newSize):
        # Only update in-memory cache; NO disk write here
        if getattr(self, "_in_adjust_widths", False):
            return
        if hasattr(self.table, "_base_widths") and logicalIndex < len(self.table._base_widths):
            self.table._base_widths[logicalIndex] = newSize

    def _on_custom_col_changed(self):
        self._save_state()
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _add_manual_col(self):
        c = self.manual_col_edit.text().strip()
        if not c:
            return
        if c not in self.manual_col_pool:
            self.manual_col_pool.append(c)
            # Make active by default
            if 'custom_cols' not in self.ui_state:
                self.ui_state['custom_cols'] = []
            if c not in self.ui_state['custom_cols']:
                self.ui_state['custom_cols'].append(c)
            
            self._rebuild_custom_cols_menu()
            self._save_state()
            self.manual_col_edit.clear()
            if self.last_result_df is not None:
                self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _remove_manual_col(self):
        c = self.manual_col_edit.text().strip()
        if not c:
            # Try to grab current text from selected menu action or pop the last one
            if self.manual_col_pool:
                c = self.manual_col_pool[-1]
            else:
                return
        
        if c in self.manual_col_pool:
            self.manual_col_pool.remove(c)
            if c in self.ui_state.get('custom_cols', []):
                self.ui_state['custom_cols'].remove(c)
            self._rebuild_custom_cols_menu()
            self._save_state()
            self.manual_col_edit.clear()
            if self.last_result_df is not None:
                self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def run_filter(self, force_reload=False):
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        if not active_periods:
            QMessageBox.warning(self, "警告", "请至少选择一个参与周期！")
            return

        strat_name = self.strategy_combo.currentText()
        strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
        if not strat_config:
            return

        if force_reload:
            # 强制刷新：清空所有缓存和时间戳
            self.top_now = None
            self._top_now_cache_ts[0] = 0.0
            if hasattr(self.engine, "lock"):
                with self.engine.lock:
                    self.engine._period_dfs.clear()
            else:
                self.engine._period_dfs.clear()
            self._period_cache_ts.clear()
            if hasattr(self, "_block_cache"):
                self._block_cache.clear()
            self.lbl_status.setText("🔄 强制刷新：正在重新获取全部数据...")
        else:
            # 智能缓存：检查 top_now 缓存是否过期
            if not self._is_cache_valid(self._top_now_cache_ts[0]):
                self.top_now = None
                self._top_now_cache_ts[0] = 0.0
            # 检查各周期缓存是否过期，过期则清除
            for p in list(self._period_cache_ts.keys()):
                if not self._is_cache_valid(self._period_cache_ts.get(p, 0.0)):
                    self._period_cache_ts.pop(p, None)
                    if hasattr(self.engine, "lock"):
                        with self.engine.lock:
                            self.engine._period_dfs.pop(p, None)
                    else:
                        self.engine._period_dfs.pop(p, None)
            
            if self.top_now is None:
                self.lbl_status.setText("正在获取基础全市场数据...")
            else:
                is_trade = cct.get_work_time_duration()
                age = int(time.time() - self._top_now_cache_ts[0])
                trade_hint = "交易时段" if is_trade else "非交易时段"
                self.lbl_status.setText(f"⚡ 使用内存缓存 ({trade_hint}，缓存已存在 {age}s)，开始筛选...")

        self.btn_run_filter_worker(strat_config, active_periods, force_reload)

    def btn_run_filter_worker(self, strat_config, active_periods, force_reload):
        # Prevent starting a new thread if the previous one is still active
        from PyQt6.sip import isdeleted
        if hasattr(self, "worker") and self.worker is not None:
            try:
                if not isdeleted(self.worker) and self.worker.isRunning():
                    logger.info("Previous worker thread is still running. Ignoring new filter request.")
                    return
            except RuntimeError:
                self.worker = None

        # Run standard QThread worker
        worker = MultiPeriodWorker(
            self.engine, strat_config, active_periods,
            top_now=self.top_now, force_reload=force_reload,
            period_cache_ts=self._period_cache_ts, top_now_cache_ts=self._top_now_cache_ts
        )
        self.worker = worker
        _active_workers.add(worker)

        worker.progress.connect(self.update_status)
        worker.finished.connect(self._on_worker_finished)
        worker.error.connect(self._on_worker_error)

        def cleanup():
            _active_workers.discard(worker)
            if getattr(self, "worker", None) == worker:
                self.worker = None
            try:
                if not isdeleted(worker):
                    worker.deleteLater()
            except RuntimeError:
                pass

        worker.finished.connect(cleanup)
        worker.error.connect(cleanup)
        worker.start()

    def update_status(self, text):
        self.lbl_status.setText(text)

    def _on_worker_finished(self, result_df, elapsed, flat_df):
        self.last_result_df = result_df
        self.last_elapsed = elapsed
        self._last_flat_df = flat_df
        if self.worker is not None:
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(self.worker):
                    self.top_now = self.worker.top_now  # Synchronize back top_now from background thread
            except RuntimeError:
                pass
        self._show_results(result_df, elapsed, flat_df)

        # Automatically update Dragon Monitor if it is currently open and visible
        if hasattr(self, "dragon_monitor_dialog") and self.dragon_monitor_dialog is not None:
            from PyQt6.sip import isdeleted
            try:
                if not isdeleted(self.dragon_monitor_dialog) and self.dragon_monitor_dialog.isVisible():
                    sh_pct = 0.0
                    if self.top_now is not None and not self.top_now.empty:
                        if 'sh000001' in self.top_now.index:
                            sh_pct = float(self.top_now.loc['sh000001'].get('percent', 0.0))
                        self.dragon_monitor_dialog.update_data(self.top_now, sh_pct)
            except Exception as e:
                logger.warning(f"Failed to auto-update dragon monitor: {e}")

    def refresh_realtime_ui(self):
        """Called externally to re-run filtering and update all charts/displays."""
        self.run_filter(force_reload=False)

    def closeEvent(self, event):
        """
        唯一写盘时机：窗口关闭时一次性保存窗口位置、状态和列宽。
        运行期间 resizeEvent / moveEvent / sectionResized 均不写盘。
        """
        from PyQt6.sip import isdeleted

        # Stop all timers
        if hasattr(self, "favorites_timer"):
            self.favorites_timer.stop()

        # Disconnect worker signals to prevent crash after Dialog is deleted
        if hasattr(self, "worker") and self.worker is not None:
            try:
                if not isdeleted(self.worker):
                    for sig in (self.worker.progress, self.worker.finished, self.worker.error):
                        try:
                            sig.disconnect()
                        except Exception:
                            pass
            except RuntimeError:
                pass

        # ── ONE-TIME disk write: position + state + column widths ──
        try:
            self.save_window_position_qt(self, "multi_period_dialog")
        except Exception:
            pass
        self._save_state()

        # Cascade-close Dragon Monitor
        if hasattr(self, "dragon_monitor_dialog") and self.dragon_monitor_dialog is not None:
            try:
                if not isdeleted(self.dragon_monitor_dialog):
                    self.dragon_monitor_dialog.close()
            except Exception:
                pass

        super().closeEvent(event)

    def resizeEvent(self, event):
        # NO disk write on resize — only update UI layout in memory
        super().resizeEvent(event)
        self._adjust_column_widths()

    def moveEvent(self, event):
        # NO disk write on move — position saved once on closeEvent
        super().moveEvent(event)

    def _adjust_column_widths(self):
        """
        Dynamically stretches columns to fit the viewport width when the window gets wider,
        preserving a compact layout and user manually adjusted column widths as baseline.
        """
        if getattr(self, "_in_adjust_widths", False):
            return
        self._in_adjust_widths = True
        try:
            viewport_w = self.table.viewport().width()
            col_count = self.table.columnCount()
            if col_count <= 0 or viewport_w <= 100:
                return

            if not hasattr(self.table, "_base_widths") or len(self.table._base_widths) != col_count:
                base_widths = []
                for i in range(col_count):
                    w = self.table.columnWidth(i)
                    if w <= 0:
                        w = 50
                    if i == 1: # Name column default compact width
                        w = 65
                    base_widths.append(w)
                self.table._base_widths = base_widths

            total_base_w = sum(self.table._base_widths)

            if viewport_w > total_base_w:
                extra_w = viewport_w - total_base_w
                # Distribute extra width to columns other than Code and Name
                distribute_cols = []
                for i in range(col_count):
                    header_item = self.table.horizontalHeaderItem(i)
                    if header_item:
                        col_text = header_item.text()
                        if col_text not in ("代码", "名称"):
                            distribute_cols.append(i)

                if not distribute_cols:
                    distribute_cols = list(range(col_count))

                add_w_per_col = extra_w // len(distribute_cols)
                rem_w = extra_w % len(distribute_cols)

                for idx, col_idx in enumerate(distribute_cols):
                    add_val = add_w_per_col + (1 if idx < rem_w else 0)
                    self.table.setColumnWidth(col_idx, self.table._base_widths[col_idx] + add_val)
            else:
                for i in range(col_count):
                    self.table.setColumnWidth(i, self.table._base_widths[i])
        finally:
            self._in_adjust_widths = False

    def _on_worker_error(self, err_msg):
        self.lbl_status.setText(f"❌ 错误: {err_msg}")
        QMessageBox.critical(self, "筛选出错", f"执行过滤策略时发生异常: {err_msg}")

    def _get_display_periods_for_custom_col(self, col_name, active_periods, df=None):
        if not active_periods:
            return []
        if col_name.lower() in ("dff", "dff2", "dff3", "rank"):
            return [active_periods[0]]
        if df is not None and not df.empty and len(active_periods) > 1:
            sample_df = df.head(100)
            p0 = active_periods[0]
            col0 = f"{col_name}_{p0}"
            if col0 in sample_df.columns:
                is_all_same = True
                for p in active_periods[1:]:
                    col_p = f"{col_name}_{p}"
                    if col_p in sample_df.columns:
                        series0 = sample_df[col0]
                        series_p = sample_df[col_p]
                        try:
                            diff = (series0 - series_p).abs().max()
                            if pd.isna(diff) or diff > 1e-5:
                                if not series0.fillna("").astype(str).equals(series_p.fillna("").astype(str)):
                                    is_all_same = False
                                    break
                        except Exception:
                            if not series0.fillna("").astype(str).equals(series_p.fillna("").astype(str)):
                                is_all_same = False
                                break
                    else:
                        is_all_same = False
                        break
                if is_all_same:
                    return [p0]
        return active_periods

    def _show_results(self, df, elapsed, flat_df=None):
        self._is_updating = True
        self.table._is_updating = True
        try:
            logger.debug(f"[MultiPeriodDialog] _show_results called. df empty: {df.empty if df is not None else True}, len(df): {len(df) if df is not None else 0}")
            
            # Backup current selection before updating the table
            selected_code = None
            curr_row = self.table.currentRow()
            if curr_row >= 0:
                c_item = self.table.item(curr_row, 0)
                if c_item:
                    selected_code = c_item.text().strip()

            self._last_selected_code = None
            if flat_df is None:
                flat_df = self._build_flat_df(df)
            self._last_flat_df = flat_df

            self.table.setRowCount(0)
            self.table.current_df = flat_df

            self._update_stats_ui()

            if df.empty:
                logger.debug("[MultiPeriodDialog] df is empty, returning early.")
                self.lbl_status.setText(f"完成，未找到符合条件的标的。(耗时 {elapsed:.1f}s)")
                self.update_concept_ranking(None)
                return

            # Apply secondary filtering
            filtered_df = flat_df
            if self._current_history_query:
                filtered_df = self._apply_secondary_filter(flat_df, self._current_history_query)

            if filtered_df.empty:
                if self._history_filter_error:
                    self.lbl_status.setText(f"⚠️ {self._history_filter_error} (耗时 {elapsed:.1f}s)")
                else:
                    self.lbl_status.setText(f"完成，未找到符合二次过滤条件的标的。(二次过滤前 {len(df)} 只，耗时 {elapsed:.1f}s)")
                self.update_concept_ranking(None)
                return

            # Final stats labels
            stats = getattr(self.engine, "last_stats", None)
            if stats and stats.get("final"):
                final = stats["final"]
                mode_str = "交集" if final["mode"] == "intersection" else "并集"
                if self._current_history_query:
                    self.lbl_final_stats.setText(
                        f"【最终 ({mode_str})】 共 {len(filtered_df)} / 二次前 {len(df)} 只 ({len(filtered_df)/final['total']*100:.3f}%)"
                    )

            if self._current_history_query:
                if self._history_filter_error:
                    self.lbl_status.setText(f"⚠️ {self._history_filter_error} (二次前 {len(df)} 只，耗时 {elapsed:.1f}s)")
                else:
                    self.lbl_status.setText(f"完成，共筛选出 {len(filtered_df)} 只 (二次前 {len(df)} 只，耗时 {elapsed:.1f}s)")
            else:
                self.lbl_status.setText(f"完成，共筛选出 {len(filtered_df)} 只标的。(耗时 {elapsed:.1f}s)")

            # Columns configuration
            active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
            active_customs = [c for c, act in self.custom_col_actions.items() if act.isChecked()]

            custom_cols = []
            for c in active_customs:
                disp_periods = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)
                for p in disp_periods:
                    custom_cols.append(f"{c}_{p}")
            pass_cols = [f"pass_{p}" for p in active_periods]

            base_cols = ["code", "name", "price", "percent", "volume", "ratio"]
            columns = base_cols + custom_cols + pass_cols
            
            headers = {
                "code": "代码", 
                "name": "名称", 
                "price": "现价", 
                "percent": "涨幅%", 
                "volume": "成交量", 
                "ratio": "换手"
            }
            for c in active_customs:
                disp_periods = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)
                for p in disp_periods:
                    headers[f"{c}_{p}"] = f"{c}({p})"
            for p in active_periods:
                headers[f"pass_{p}"] = f"{p}通过"

            self.table.setColumnCount(len(columns))
            self.table.setHorizontalHeaderLabels([headers.get(col, col) for col in columns])

            try:
                from global_favorites import GlobalFavoriteManager
                fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            except Exception:
                fav_stocks = set()

            custom_disp_periods = {}
            for c in active_customs:
                custom_disp_periods[c] = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)

            self.table.setRowCount(len(filtered_df))
            print(f"[DEBUG] setRowCount to {len(filtered_df)}. Disabling sorting during population.")
            self.table.setSortingEnabled(False)
            
            for idx, (code, row) in enumerate(filtered_df.iterrows()):
                name = row.get('name', '--')
                price = round(row.get('close', 0), 2)
                percent = round(row.get('percent', 0), 2)
                vol = round(row.get('volume', 0), 2)
                ratio = round(row.get('ratio', 0), 2)

                # Block cache concepts extraction
                category_str = row.get('category', row.get('block', ''))
                if not category_str or str(category_str).strip() == 'nan':
                    if self.top_now is not None and code in self.top_now.index:
                        r = self.top_now.loc[code]
                        if isinstance(r, pd.DataFrame):
                            r = r.iloc[0]
                        category_str = r.get('category', r.get('block', ''))
                if pd.notna(category_str) and str(category_str).strip() not in ('', 'nan', '--'):
                    self._block_cache[code] = str(category_str).strip()

                is_fav = code in fav_stocks
                display_name = f"★ {name}" if is_fav else name

                # Code
                c_item = QTableWidgetItem(code)
                self.table.setItem(idx, 0, c_item)

                # Name
                n_item = QTableWidgetItem(display_name)
                if is_fav:
                    n_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                    n_item.setForeground(QBrush(QColor("#ff4444")))
                self.table.setItem(idx, 1, n_item)

                # Price, Percent, Volume, Ratio
                p_item = NumericTableWidgetItem(f"{price:.2f}")
                self.table.setItem(idx, 2, p_item)

                pct_item = NumericTableWidgetItem(f"{percent:.2f}")
                if percent > 0:
                    pct_item.setForeground(QBrush(QColor("#ff4444")))
                elif percent < 0:
                    pct_item.setForeground(QBrush(QColor("#33cc5a")))
                self.table.setItem(idx, 3, pct_item)

                v_item = NumericTableWidgetItem(f"{vol:.0f}" if vol > 1000 else f"{vol:.2f}")
                self.table.setItem(idx, 4, v_item)

                r_item = NumericTableWidgetItem(f"{ratio:.2f}")
                self.table.setItem(idx, 5, r_item)

                c_idx = 6
                for c in active_customs:
                    disp_periods = custom_disp_periods[c]
                    for p in disp_periods:
                        val = '--'
                        col_name = f"{c}_{p}"
                        if col_name in filtered_df.columns:
                            raw_val = row.get(col_name)
                            if pd.notna(raw_val):
                                if isinstance(raw_val, (int, float)):
                                    val = f"{raw_val:.2f}"
                                else:
                                    val = str(raw_val)
                        
                        item = NumericTableWidgetItem(val) if val != '--' else QTableWidgetItem(val)
                        self.table.setItem(idx, c_idx, item)
                        c_idx += 1

                for p in active_periods:
                    pass_val = row.get(f'pass_{p}', False)
                    item = QTableWidgetItem('✅' if pass_val else '--')
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if pass_val:
                        item.setForeground(QBrush(QColor("#66bb6a")))
                    self.table.setItem(idx, c_idx, item)
                    c_idx += 1

            self.table.setSortingEnabled(True)
            logger.info(f"[MultiPeriodDialog] Table populated successfully. Column count: {self.table.columnCount()}, Row count: {self.table.rowCount()}")
            
            # Setup narrow default widths configuration
            default_widths = {}
            for idx, col in enumerate(columns):
                if col == "code":
                    w = 55
                elif col == "name":
                    w = 65
                elif col == "price":
                    w = 50
                elif col == "percent":
                    w = 55
                elif col == "volume":
                    w = 60
                elif col == "ratio":
                    w = 45
                elif col.startswith("pass_"):
                    w = 55
                else:
                    w = 50
                default_widths[idx] = w
            
            self.table.setup_persistence("multi_period_table", default_widths=default_widths)
            if not getattr(self.table, "_first_width_applied", False):
                self.table._first_width_applied = True
                for idx, w in default_widths.items():
                    self.table.setColumnWidth(idx, w)
            
            # Read back real column widths into _base_widths cache
            base_widths = []
            for i in range(self.table.columnCount()):
                w = self.table.columnWidth(i)
                base_widths.append(w if w > 0 else default_widths.get(i, 50))
            self.table._base_widths = base_widths

            # Automatically stretch columns to utilize viewport width
            self._adjust_column_widths()

            # Restore previous row selection and prevent redundant linkage refresh
            if selected_code:
                for r in range(self.table.rowCount()):
                    c_item = self.table.item(r, 0)
                    if c_item and c_item.text().strip() == selected_code:
                        self.table.setCurrentCell(r, 0)
                        self._last_selected_code = selected_code
                        break

            self.update_concept_ranking(filtered_df)
        except Exception as ex:
            import traceback
            err_stack = traceback.format_exc()
            logger.error(f"[MultiPeriodDialog] Crashed in _show_results: {ex}\n{err_stack}")
        finally:
            self._is_updating = False
            self.table._is_updating = False

    def _build_flat_df(self, df):
        if df is None or df.empty:
            return df
        
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        flat_df = df.copy()
        
        for period in active_periods:
            df_p = self.engine._period_dfs.get(period)
            if df_p is not None and not df_p.empty:
                cols_to_join = [c for c in df_p.columns if c not in ('code', 'name')]
                if cols_to_join:
                    df_p_sub = df_p[cols_to_join]
                    df_p_sub = df_p_sub[~df_p_sub.index.duplicated(keep='first')]
                    df_p_sub = df_p_sub.rename(columns={c: f"{c}_{period}" for c in cols_to_join})
                    flat_df = flat_df.join(df_p_sub, how='left')
                    
        flat_df.index.name = 'code'
        return flat_df

    def _suffix_query(self, expr, period_suffix):
        cols_set = set()
        df_p = self.engine._period_dfs.get(period_suffix)
        if df_p is not None and not df_p.empty:
            cols_set = set(df_p.columns)
            
        def repl(match):
            word = match.group(0)
            if word in cols_set:
                return f"{word}_{period_suffix}"
            return word
        return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)

    def _apply_secondary_filter(self, df, query_expr):
        if not query_expr or df is None or df.empty:
            self._history_filter_error = None
            return df
        
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        target_period = 'd' if 'd' in active_periods else (active_periods[0] if active_periods else 'd')
        
        converted_query = self._suffix_query(query_expr, target_period)
        
        try:
            filtered_df = df.query(converted_query)
            self._history_filter_error = None
            return filtered_df
        except Exception as e1:
            try:
                filtered_df = df.query(query_expr)
                self._history_filter_error = None
                return filtered_df
            except Exception as e2:
                self._history_filter_error = f"过滤语法错误: {e2}"
                return df

    def _apply_secondary_filter_from_edit(self):
        query = self.filter_edit.text().strip()
        self._current_history_query = query
        self._save_state()
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _clear_secondary_filter(self):
        self._current_history_query = ""
        self._history_filter_error = None
        self.filter_edit.clear()
        self._save_state()
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _on_table_double_clicked(self, index):
        row = index.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            if name.startswith("★ "):
                name = name[2:]
            self.diagnose_stock_strategy(code, name)

    def _on_diagnose_click(self):
        code = self.diag_edit.text().strip()
        if not code:
            row = self.table.currentRow()
            if row >= 0:
                code_item = self.table.item(row, 0)
                if code_item:
                    code = code_item.text().strip()
        
        if not code:
            QMessageBox.warning(self, "警告", "请输入或在表格中选择要诊断的个股代码！")
            return
        
        self.diagnose_stock_strategy(code)

    def _on_diagnose_dna_click(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        
        code_to_name = {}
        for r in range(row, min(self.table.rowCount(), row + 21)):
            c_item = self.table.item(r, 0)
            n_item = self.table.item(r, 1)
            if c_item:
                c = c_item.text().strip()
                n = n_item.text().strip() if n_item else c
                if n.startswith("★ "):
                    n = n[2:]
                code_to_name[c] = n
                
        if code_to_name:
            # Reconstruct resample from active periods
            active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
            PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
            sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
            min_period = sorted_periods[0] if sorted_periods else 'd'
            
            self._run_dna_audit_batch(code_to_name, resample=min_period)

    def _run_dna_audit_batch(self, code_to_name, end_date=None, resample='d'):
        from backtest_feature_auditor import audit_multiple_codes
        try:
            # We can use wait cursor as loading hint
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self.lbl_status.setText("🧬 正在执行 DNA 审计，请稍后...")
            QApplication.processEvents()
            
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=end_date,
                code_to_name=code_to_name,
                progress_callback=None,
                resample=resample
            )
            
            # Use Qt-native DNA audit window to completely avoid Tkinter runtime and missing tk dependency issues
            try:
                self._dna_audit_win = QtDnaAuditReportWindow(summaries, parent=self, end_date=end_date, resample=resample)
                self._dna_audit_win.show()
            except Exception as e:
                QMessageBox.critical(self, "错误", f"调起 DNA 报告窗口失败: {e}")
        except Exception as e:
            QMessageBox.critical(self, "DNA审计出错", str(e))
        finally:
            QApplication.restoreOverrideCursor()
            self.lbl_status.setText("准备就绪")

    def diagnose_stock_strategy(self, code, name=None):
        code = str(code).strip().zfill(6)
        if not name:
            if self.top_now is not None and code in self.top_now.index:
                name = self.top_now.loc[code, 'name']
            else:
                try:
                    name = tdd.get_name_code(code)
                except Exception:
                    name = "未知股票"
            if not name or name == "未知股票":
                name = "未知股票"

        strat_name = self.strategy_combo.currentText()
        strat_config = next((s for s in self.strategies if s['name'] == strat_name), None)
        if not strat_config:
            QMessageBox.warning(self, "警告", "未选中任何有效策略！")
            return
            
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        if not active_periods:
            QMessageBox.warning(self, "警告", "请至少选择一个参与周期！")
            return

        self.lbl_status.setText(f"正在诊断 {code} 的多周期指标...")
        QApplication.processEvents()

        # Fetch top_now if missing
        if self.top_now is None:
            try:
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"初始化市场基础数据失败: {e}")
                return

        # Load missing period data synchronously
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for period in active_periods:
                if period not in self.engine._period_dfs or self.engine._period_dfs[period].empty:
                    self.lbl_status.setText(f"正在加载 {period} 周期特征数据...")
                    QApplication.processEvents()
                    self.engine.load_period_data(period, self.top_now)
        finally:
            QApplication.restoreOverrideCursor()

        self.lbl_status.setText("准备就绪")

        # Build merged row flat DF
        merged_row = {"name": name}

        def suffix_expr(expr, period_suffix, cols_set):
            def repl(match):
                word = match.group(0)
                if word in cols_set:
                    return f"{word}_{period_suffix}"
                return word
            return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)

        queries = []
        for period in active_periods:
            df_p = self.engine._period_dfs.get(period)
            if df_p is not None and not df_p.empty:
                valid_cols = set(df_p.columns)
                if code in df_p.index:
                    row_p = df_p.loc[code]
                    if isinstance(row_p, pd.DataFrame):
                        row_p = row_p.iloc[0]
                    for k, val in row_p.to_dict().items():
                        if k not in ('code', 'name'):
                            merged_row[f"{k}_{period}"] = val
                
                cond = strat_config['conditions'].get(period)
                if cond:
                    raw_filter = cond['filter']
                    suffixed_filter = suffix_expr(raw_filter, period, valid_cols)
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "expr": suffixed_filter
                    })
            else:
                cond = strat_config['conditions'].get(period)
                if cond:
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "expr": cond['filter']
                    })

        if not queries:
            QMessageBox.warning(self, "警告", "未生成任何有效的诊断条件！")
            return

        df_flat = pd.DataFrame([merged_row], index=[code])
        df_flat.index.name = 'code'

        # Use Qt-native check code dialog to completely avoid Tkinter dependency
        try:
            dialog = QtCheckCodeDialog(df_flat, code, queries, parent=self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"调起股票检查报告失败: {e}")

    def link_stock(self, code, name):
        """
        接收来自 BaseATSTableWidget.stock_activated 信号的联动请求。
        彻底实现与主窗口一致的极速无阻塞联动：
        1. 异步发送 Socket 指令切换 K线可视化器 (Vis)。
        2. 向独立 LinkageProcess 后台进程投递物理联动任务 (Tdx/Ths)，彻底消除 UI 线程卡顿和延迟。
        """
        code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
        if not code:
            return

        # Same-code guard: skip if exactly the same code was just linked
        if code == getattr(self, "_last_link_code", ""):
            return
        self._last_link_code = code

        # Reset base_table's emitted-code tracker so switching to another window
        # and coming back can re-trigger the same code
        try:
            self.table._last_emitted_code = ""
        except Exception:
            pass

        # Prepare parameters
        do_vis = self.link_vis_chk.isChecked()
        do_tdx = self.link_tdx_chk.isChecked()
        do_ths = self.link_ths_chk.isChecked()

        if not (do_vis or do_tdx or do_ths):
            return

        status_msg_parts = []

        # 1. 异步向 26668 发送 K线可视化联动指令
        if do_vis:
            import socket
            import threading
            
            # Check if this stock is in favorites and retrieve its add date
            add_date = None
            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                if code in fav_mgr.get_favorite_stocks():
                    add_date = fav_mgr.get_favorite_stock_date(code)
            except Exception:
                pass
            
            # If add_date is available, format as TIME_LINK; otherwise CODE
            if add_date:
                cmd_str = f"TIME_LINK|{code}|{add_date}|label=重点关注"
            else:
                cmd_str = f"CODE|{code}"
            
            def send_switch(msg):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.1) # 极低超时，不阻塞 UI
                        s.connect(('127.0.0.1', 26668))
                        s.sendall(msg.encode("utf-8"))
                except Exception:
                    pass # 可视化器可能未启动，静默失败即可
                    
            threading.Thread(target=send_switch, args=(cmd_str,), daemon=True).start()
            status_msg_parts.append("Vis")

        # 2. 向独立联动进程投递物理联动任务 (TDX/THS 物理联动机能)
        if do_tdx or do_ths:
            try:
                from linkage_service import get_link_manager
                flags = {'tdx': do_tdx, 'ths': do_ths, 'dfcf': False}
                get_link_manager().push(code, flags=flags, auto=False)
                if do_tdx: status_msg_parts.append("Tdx")
                if do_ths: status_msg_parts.append("Ths")
            except Exception as e:
                logger.error(f"[Linkage] External linkage failed: {e}")
                status_msg_parts.append("Tdx/Ths(失败)")

        if status_msg_parts:
            msg = f"✅ 联动: {code} ({', '.join(status_msg_parts)})"
            self.status_message_signal.emit(msg)

    def _open_history_dialog(self):
        from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
        dialog = QueryHistoryDialog(self, SEARCH_HISTORY_FILE)
        dialog.applied.connect(self._on_history_query_applied)
        dialog.exec()

    def _on_history_query_applied(self, query):
        self._current_history_query = query
        self.filter_edit.setText(query)
        self._save_state()
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _update_stats_ui(self):
        stats = getattr(self.engine, "last_stats", None)
        if not stats:
            return
        
        # Display single period rates
        parts = []
        for period in self.period_checkboxes.keys():
            if period in stats:
                info = stats[period]
                ratio_pct = info['ratio'] * 100
                parts.append(f"{period}:{info['passed']}/{info['total']} ({ratio_pct:.1f}%)")
        
        if parts:
            # We can print it to standard text
            self.lbl_status.setText(f"【单周期通过率】 " + "  ".join(parts))

    def _get_stock_category(self, code, row):
        category = row.get('category', row.get('block', ''))
        if not category or str(category).strip() == 'nan':
            category = self._block_cache.get(code, '')
        return category

    def _normalize_concept_name(self, name):
        if not name:
            return ""
        name = name.strip()
        # Remove common suffixes like '概念', '板块'
        for suff in ("概念", "板块", "行业"):
            if name.endswith(suff) and len(name) > len(suff):
                name = name[:-len(suff)]
        return name

    def _is_noise_concept(self, name):
        # Ignore noisy generic concepts
        return name in ("昨日涨停", "昨日触板", "深股通", "沪股通", "融资融券", "标普道琼斯A股", "MSCI中国")

    def update_concept_ranking(self, df_filtered):
        # Clear flow widget layout
        while self.concept_flow_layout.count():
            item = self.concept_flow_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if df_filtered is None or df_filtered.empty:
            self.lbl_empty_concept = QLabel("暂无板块数据", self)
            self.lbl_empty_concept.setStyleSheet("color: #757575;")
            self.concept_flow_layout.addWidget(self.lbl_empty_concept)
            return

        from collections import Counter
        concept_counter = Counter()
        for code, row in df_filtered.iterrows():
            category = self._get_stock_category(code, row)
            if not category:
                continue
            
            cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
            for cat in cats:
                norm_cat = self._normalize_concept_name(cat)
                if not norm_cat or self._is_noise_concept(norm_cat):
                    continue
                try:
                    from stock_logic_utils import is_generic_concept
                    if is_generic_concept(norm_cat):
                        continue
                except Exception:
                    pass
                concept_counter[norm_cat] += 1

        top_concepts = concept_counter.most_common(10)
        if not top_concepts:
            self.lbl_empty_concept = QLabel("暂无板块数据", self)
            self.lbl_empty_concept.setStyleSheet("color: #757575;")
            self.concept_flow_layout.addWidget(self.lbl_empty_concept)
            return

        # Populating Flow Buttons
        for cat_name, count in top_concepts:
            btn = QPushButton(f"{cat_name}({count})", self)
            btn.setStyleSheet("""
                QPushButton { background-color: #1e293b; color: #64b5f6; border: 1px solid #2d3748; border-radius: 4px; padding: 2px 6px; font-size: 11px; }
                QPushButton:hover { background-color: #2b394f; color: #ffffff; }
            """)
            btn.clicked.connect(lambda checked, name=cat_name: self.show_concept_top10_window(name))
            self.concept_flow_layout.addWidget(btn)

    def show_concept_detail_window(self):
        if self._last_flat_df is None or self._last_flat_df.empty:
            QMessageBox.information(self, "提示", "当前无筛选数据，请先执行筛选。")
            return

        from collections import Counter
        concept_counter = Counter()
        concept_to_codes = {}
        for code, row in self._last_flat_df.iterrows():
            category = self._get_stock_category(code, row)
            if not category:
                continue
            cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
            for cat in cats:
                norm_cat = self._normalize_concept_name(cat)
                if not norm_cat or self._is_noise_concept(norm_cat):
                    continue
                try:
                    from stock_logic_utils import is_generic_concept
                    if is_generic_concept(norm_cat):
                        continue
                except Exception:
                    pass
                concept_counter[norm_cat] += 1
                concept_to_codes.setdefault(norm_cat, []).append(code)

        all_concepts = concept_counter.most_common()
        if not all_concepts:
            QMessageBox.information(self, "提示", "当前筛选结果中没有包含板块概念信息。")
            return

        self._concept_index = concept_to_codes
        self._concept_detail_win = ConceptDetailDialog(self, all_concepts, concept_to_codes)
        self._concept_detail_win.show()

    def show_concept_top10_window(self, concept_name):
        target_concept = self._normalize_concept_name(concept_name)
        if not target_concept:
            return

        if self._last_flat_df is None or self._last_flat_df.empty:
            QMessageBox.information(self, "信息", "当前无筛选数据，无法查看个股列表")
            return

        # Try indexed lookup
        concept_index = getattr(self, "_concept_index", None)
        if concept_index is None:
            # Lazy rebuild
            concept_index = {}
            for code, row in self._last_flat_df.iterrows():
                category = self._get_stock_category(code, row)
                if not category:
                    continue
                cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
                for cat in cats:
                    norm_cat = self._normalize_concept_name(cat)
                    if norm_cat:
                        concept_index.setdefault(norm_cat, []).append(code)
            self._concept_index = concept_index

        matched_codes = concept_index.get(target_concept, [])
        matched_stocks = [(code, self._last_flat_df.loc[code]) for code in matched_codes if code in self._last_flat_df.index]

        if not matched_stocks:
            QMessageBox.information(self, "信息", f"当前筛选结果中暂无属于【{target_concept}】的个股")
            return

        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        active_customs = [c for c, act in self.custom_col_actions.items() if act.isChecked()]

        custom_cols = []
        for c in active_customs:
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, self._last_flat_df)
            for p in disp_periods:
                custom_cols.append(f"{c}_{p}")
        pass_cols = [f"pass_{p}" for p in active_periods]

        base_cols = ["code", "name", "price", "percent", "volume", "ratio"]
        columns = base_cols + custom_cols + pass_cols
        
        headers = {
            "code": "代码", 
            "name": "名称", 
            "price": "现价", 
            "percent": "涨幅%", 
            "volume": "成交量", 
            "ratio": "换手"
        }
        for c in active_customs:
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, self._last_flat_df)
            for p in disp_periods:
                headers[f"{c}_{p}"] = f"{c}({p})"
        for p in active_periods:
            headers[f"pass_{p}"] = f"{p}通过"

        dialog = ConceptStocksDialog(self, target_concept, matched_stocks, columns, headers)
        dialog.exec()

    def open_dragon_monitor(self):
        try:
            from ats.ui.dragon_monitor import DragonLeaderMonitorDialog
            from PyQt6.sip import isdeleted
            if not hasattr(self, "dragon_monitor_dialog") or self.dragon_monitor_dialog is None or isdeleted(self.dragon_monitor_dialog):
                self.dragon_monitor_dialog = DragonLeaderMonitorDialog(parent=None)
                self.dragon_monitor_dialog.code_clicked.connect(self.link_stock)
            
            self.dragon_monitor_dialog.show_normal_position()
            if self.top_now is not None and not self.top_now.empty:
                sh_pct = 0.0
                if 'sh000001' in self.top_now.index:
                    sh_pct = float(self.top_now.loc['sh000001'].get('percent', 0.0))
                self.dragon_monitor_dialog.update_data(self.top_now, sh_pct)
        except Exception as e:
            logger.error(f"Failed to open dragon monitor: {e}")
            QMessageBox.critical(self, "错误", f"调起龙头监控看板失败: {e}")

    def open_strategy_editor(self):
        dialog = MultiPeriodStrategyEditorDialog(self, self.engine, self._on_strategies_saved)
        dialog.exec()

    def _on_strategies_saved(self, new_strategies):
        self.strategies = new_strategies
        self.strategy_combo.blockSignals(True)
        current_text = self.strategy_combo.currentText()
        self.strategy_combo.clear()
        self.strategy_combo.addItems([s['name'] for s in self.strategies])
        if current_text in [s['name'] for s in self.strategies]:
            self.strategy_combo.setCurrentText(current_text)
        else:
            if self.strategies:
                self.strategy_combo.setCurrentIndex(0)
        self.strategy_combo.blockSignals(False)

    def _poll_favorites_loop(self):
        try:
            from global_favorites import GlobalFavoriteManager
            fav_mgr = GlobalFavoriteManager()
            if fav_mgr.version != self._last_favorites_version:
                self._last_favorites_version = fav_mgr.version
                # Refresh table view items if displayed
                if self.last_result_df is not None:
                    self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)
        except Exception:
            pass




# ── Global Shim Functions ──
_dialog_instance = None

def open_multi_period_tester(parent_window=None):
    """
    Standard compatibility shim function, to be called from instock_MonitorTK.py.
    Checks and maintains a single active PyQt6 Dialog instance.
    """
    global _dialog_instance
    from PyQt6.sip import isdeleted
    
    if _dialog_instance is not None:
        try:
            if not isdeleted(_dialog_instance):
                _dialog_instance.showNormal()
                _dialog_instance.raise_()
                _dialog_instance.activateWindow()
                return _dialog_instance
        except Exception:
            pass
        _dialog_instance = None

    try:
        # Check active QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        
        _dialog_instance = MultiPeriodDialog()
        _dialog_instance.show()
        return _dialog_instance
    except Exception as e:
        logger.error(f"Failed to open MultiPeriodDialog: {e}")
        return None


class NumericWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        if not isinstance(other, QTableWidgetItem):
            return super().__lt__(other)
        try:
            s1 = self.text().replace('%', '').strip()
            s2 = other.text().replace('%', '').strip()
            return float(s1) < float(s2)
        except Exception:
            return super().__lt__(other)


class QtDnaAuditReportWindow(QDialog, WindowMixin):
    def __init__(self, summaries, parent=None, end_date=None, resample='d'):
        super().__init__(parent)
        self.summaries = summaries
        self.monitor_app = parent
        self.end_date = end_date
        self.resample = resample
        
        self.setWindowTitle(f"🧬 DNA 专项审计报告 (深度挖掘) - {len(summaries)}只 (周期: {resample.upper()})")
        self.setMinimumSize(600, 400)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0c0d14;
                color: #e2e2e5;
            }
            QTableWidget {
                background-color: #12131a;
                color: #e2e2e5;
                gridline-color: #23242e;
                border: 1px solid #23242e;
            }
            QHeaderView::section {
                background-color: #1a1b24;
                color: #a9abb6;
                padding: 6px;
                border: 1px solid #23242e;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #2c2d3a;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #12131a;
                color: #e2e2e5;
                border: 1px solid #23242e;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 12px;
            }
            QPushButton {
                background-color: #23242e;
                color: #e2e2e5;
                border: 1px solid #323340;
                padding: 6px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2d2e3b;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        main_layout.addWidget(splitter)
        
        self.table = BaseATSTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["代码", "名称", "DNA意图分", "波段涨幅%", "极限判定"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # 自适应列宽，前四列根据内容，极限判定拉满
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        
        splitter.addWidget(self.table)
        
        self.detail_text = QTextEdit(self)
        self.detail_text.setReadOnly(True)
        splitter.addWidget(self.detail_text)
        
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("关闭报告", self)
        btn_close.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        main_layout.addLayout(btn_layout)
        
        self.table.setSortingEnabled(False)
        self._fill_data()
        self.table.setSortingEnabled(True)
        
        self.table.stock_activated.connect(self.monitor_app.link_stock)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.cellClicked.connect(self._on_cell_clicked)
        
        # 智能设定初始上下分割大小比例，防止空表格过度撑高
        splitter.setSizes([180, 320])
        
        self.window_name = "qt_dna_audit_report"
        if hasattr(self, "load_window_position_qt"):
            self.load_window_position_qt(self, self.window_name, default_width=800, default_height=500)
            
        if self.table.rowCount() > 0:
            self.table.setCurrentCell(0, 0)
            self.table.setFocus()
            
    def _fill_data(self):
        sorted_sums = sorted(self.summaries, key=lambda x: x.intent_score, reverse=True)
        self.table.setRowCount(len(sorted_sums))
        
        for idx, s in enumerate(sorted_sums):
            code_item = NumericWidgetItem(str(s.code).zfill(6))
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 0, code_item)
            
            name_item = QTableWidgetItem(s.name)
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 1, name_item)
            
            score_item = NumericWidgetItem(f"{s.intent_score:.1f}")
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 2, score_item)
            
            gain_item = NumericWidgetItem(f"{s.total_pct:.1f}%")
            gain_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if s.total_pct > 0:
                gain_item.setForeground(QBrush(QColor("#ff4444")))
            elif s.total_pct < 0:
                gain_item.setForeground(QBrush(QColor("#33cc5a")))
            self.table.setItem(idx, 3, gain_item)
            
            verdict_item = QTableWidgetItem(s.verdict)
            self.table.setItem(idx, 4, verdict_item)
            
    def _on_selection_changed(self):
        selected_ranges = self.table.selectedRanges()
        if not selected_ranges:
            return
        row = selected_ranges[0].topRow()
        code_item = self.table.item(row, 0)
        if not code_item:
            return
        code = code_item.text()
        
        target_s = next((x for x in self.summaries if str(x.code).zfill(6) == code), None)
        if target_s:
            html_content = f"""
            <h2 style='color:#5cb85c;'>【基因解剖】 {target_s.name} ({target_s.code})</h2>
            <p><b>意图评分:</b> <span style='color:#ffc107; font-size:14px; font-weight:bold;'>{target_s.intent_score:.1f} 分</span></p>
            <p><b>极限判定:</b> <span style='color:#00bcff; font-weight:bold;'>{target_s.verdict}</span></p>
            <p><b>波段涨幅:</b> {target_s.total_pct:.1f} %</p>
            <hr style='border: 1px solid #23242e;' />
            <h3 style='color:#a9abb6;'>[ 审计专家洞察 ]</h3>
            <ul>
            """
            for sug in target_s.suggestions:
                html_content += f"<li style='margin-bottom:6px;'>{sug}</li>"
            html_content += "</ul>"
            
            html_content += """
            <h3 style='color:#a9abb6;'>[ 指标演进提炼 (Indicator Evolution) ]</h3>
            <pre style='font-family: "Consolas", monospace; font-size:11px; line-height: 1.4; color:#d1d2d6;'>
"""
            header = f"{'日期':<12} {'Alpha':>8} {'涨幅%':>8} {'指数%':>8} {'Bol-U':>8} {'量比':>8}\n"
            html_content += header
            html_content += "-" * 60 + "\n"
            for h in target_s.history[-15:]:
                html_content += f"{h['date']:<12} {h['alpha']:>8.2f} {h['pct']:>8.2f} {h['idx_pct']:>8.2f} {h['c_upper']:>8.2f} {h['v_ratio']:>8.2f}\n"
            
            html_content += "</pre>"
            self.detail_text.setHtml(html_content)
            
    def _on_item_double_clicked(self, item):
        code = self.table.item(item.row(), 0).text()
        name_item = self.table.item(item.row(), 1)
        name = name_item.text().strip() if name_item else ""
        if self.monitor_app and hasattr(self.monitor_app, 'link_stock'):
            self.monitor_app.link_stock(code, name)

    def _on_cell_clicked(self, row, column):
        if column == 0:  # 点击代码列
            code_item = self.table.item(row, 0)
            if code_item:
                code = code_item.text().strip()
                if self.monitor_app:
                    if hasattr(self.monitor_app, 'diag_edit'):
                        self.monitor_app.diag_edit.setText(code)
                    if hasattr(self.monitor_app, 'diagnose_stock_strategy'):
                        self.monitor_app.diagnose_stock_strategy(code)
            
    def closeEvent(self, event):
        if hasattr(self, "save_window_position_qt_visual"):
            self.save_window_position_qt_visual(self, self.window_name)
        super().closeEvent(event)


class QtCheckCodeDialog(QDialog, WindowMixin):
    def __init__(self, df, code, queries, parent=None):
        super().__init__(parent)
        self.df = df
        self.code = code
        self.queries = queries
        self.name = df.at[code, 'name'] if 'name' in df.columns else ""
        
        self.setWindowTitle(f"股票检查报告 - {code} {self.name}")
        self.setMinimumSize(700, 500)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0c0d14;
                color: #e2e2e5;
            }
            QTextEdit {
                background-color: #12131a;
                color: #e2e2e5;
                border: 1px solid #23242e;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 12px;
            }
            QListWidget {
                background-color: #12131a;
                color: #e2e2e5;
                border: 1px solid #23242e;
                font-family: "Consolas", "Microsoft YaHei";
                font-size: 11px;
            }
            QLineEdit {
                background-color: #12131a;
                color: #ffffff;
                border: 1px solid #23242e;
                padding: 4px;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #23242e;
                color: #e2e2e5;
                border: 1px solid #323340;
                padding: 6px 16px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #2d2e3b;
            }
            QComboBox {
                background-color: #12131a;
                color: #e2e2e5;
                border: 1px solid #23242e;
                border-radius: 3px;
                padding: 4px;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_layout.addWidget(self.splitter)
        
        left_widget = QWidget(self)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("[ 检查结果摘要 ]", self))
        self.summary_text = QTextEdit(self)
        self.summary_text.setReadOnly(True)
        left_layout.addWidget(self.summary_text)
        
        self.splitter.addWidget(left_widget)
        
        self.right_widget = QWidget(self)
        right_layout = QVBoxLayout(self.right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        right_layout.addWidget(QLabel(">>> 所有数据字段详情", self))
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("过滤字段:", self))
        self.filter_edit = QLineEdit(self)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_edit)
        right_layout.addLayout(filter_layout)
        
        self.details_list = QListWidget(self)
        right_layout.addWidget(self.details_list)
        
        self.splitter.addWidget(self.right_widget)
        self.right_widget.hide()
        
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("历史:", self))
        self.history_combo = QComboBox(self)
        self.history_combo.addItem("选择历史...")
        
        _queries_list = queries if isinstance(queries, list) else [queries]
        self.history_queries = []
        for i, q in enumerate(_queries_list):
            if isinstance(q, dict):
                expr = q.get("expr", "")
                q_name = q.get("name") or expr[:15]
                self.history_combo.addItem(f"H{i+1}: {q_name}")
                self.history_queries.append(expr)
            elif isinstance(q, str):
                self.history_combo.addItem(f"H{i+1}: {q[:15]}")
                self.history_queries.append(q)
                
        self.history_combo.currentIndexChanged.connect(self._on_history_changed)
        ctrl_layout.addWidget(self.history_combo)
        
        ctrl_layout.addWidget(QLabel("手动测试:", self))
        self.manual_edit = QLineEdit(self)
        self.manual_edit.setPlaceholderText("输入测试表达式，回车执行...")
        self.manual_edit.returnPressed.connect(self._run_manual_test)
        ctrl_layout.addWidget(self.manual_edit)
        
        btn_test = QPushButton("执行测试", self)
        btn_test.clicked.connect(self._run_manual_test)
        ctrl_layout.addWidget(btn_test)
        
        main_layout.addLayout(ctrl_layout)
        
        btn_bar = QHBoxLayout()
        self.btn_toggle_details = QPushButton("显示数据详情", self)
        self.btn_toggle_details.setStyleSheet("QPushButton { background-color: #2196F3; color: white; font-weight: bold; }")
        self.btn_toggle_details.clicked.connect(self._toggle_details)
        btn_bar.addWidget(self.btn_toggle_details)
        btn_bar.addStretch()
        
        btn_close = QPushButton("关闭窗口", self)
        btn_close.clicked.connect(self.close)
        btn_bar.addWidget(btn_close)
        main_layout.addLayout(btn_bar)
        
        self.df_code = df.loc[[code]]
        try:
            from stock_logic_utils import test_code_query, format_check_result
            self.report_data = test_code_query(self.df_code, queries)
            header_str = f"股票: {code} {self.name}\n" + "="*40 + "\n"
            self.summary_text.setPlainText(header_str + format_check_result(self.report_data))
        except Exception as e:
            self.summary_text.setPlainText(f"诊断逻辑执行失败: {e}")
            
        self._init_all_fields()
        
        self.window_name = "qt_check_code_dialog"
        if hasattr(self, "load_window_position_qt"):
            self.load_window_position_qt(self, self.window_name, default_width=750, default_height=550)
            
    def _init_all_fields(self):
        self.raw_fields_lines = []
        try:
            row_dict = self.df.loc[self.code].to_dict()
            used_cols = set()
            from stock_logic_utils import extract_columns
            for r in self.report_data:
                if 'expr' in r:
                    used_cols.update(extract_columns(r['expr']))
            
            if used_cols:
                self.raw_fields_lines.append(">>> 查询涉及的关键字段:")
                for c in sorted(list(used_cols)):
                    self.raw_fields_lines.append(f"  {c}: {row_dict.get(c, 'N/A')}")
                self.raw_fields_lines.append("-" * 40)
                
            self.raw_fields_lines.append(">>> 所有字段列表:")
            for c in self.df.columns:
                self.raw_fields_lines.append(f"  {c}: {row_dict.get(c, 'N/A')}")
        except Exception as e:
            self.raw_fields_lines.append(f"提取字段信息失败: {e}")
            
        self._render_fields(self.raw_fields_lines)
        
    def _render_fields(self, lines):
        self.details_list.clear()
        for line in lines:
            self.details_list.addItem(line)
            
    def _on_filter_changed(self, text):
        query = text.lower().strip()
        if not query:
            self._render_fields(self.raw_fields_lines)
            return
        filtered = [l for l in self.raw_fields_lines if query in l.lower()]
        self._render_fields(filtered)
        
    def _toggle_details(self):
        if self.right_widget.isVisible():
            self.right_widget.hide()
            self.btn_toggle_details.setText("显示数据详情")
        else:
            self.right_widget.show()
            self.btn_toggle_details.setText("隐藏数据详情")
            self.splitter.setSizes([450, 250])
            self.filter_edit.setFocus()
            
    def _on_history_changed(self, index):
        if index <= 0:
            return
        try:
            expr = self.history_queries[index - 1]
            self.manual_edit.setText(expr)
            self._run_manual_test(expr)
        except Exception:
            pass
            
    def _run_manual_test(self, expr=None):
        from datetime import datetime
        target_expr = expr or self.manual_edit.text().strip()
        if not target_expr or target_expr == "选择历史...":
            return
            
        try:
            from stock_logic_utils import test_code_query, format_check_result
            res = test_code_query(self.df_code, [{"expr": target_expr}])
            summary = format_check_result(res)
            
            curr_text = self.summary_text.toPlainText()
            new_text = curr_text + f"\n{'='*20} 手动测试: {datetime.now().strftime('%H:%M:%S')} {'='*20}\n" + summary
            self.summary_text.setPlainText(new_text)
            self.summary_text.moveCursor(self.summary_text.textCursor().MoveOperation.End)
        except Exception as e:
            QMessageBox.warning(self, "执行测试失败", f"表达式执行出错: {e}")
            
    def closeEvent(self, event):
        self._save_state("FORCE_WRITE")
        if hasattr(self, "save_window_position_qt_visual"):
            self.save_window_position_qt_visual(self, self.window_name)
        super().closeEvent(event)


if __name__ == "__main__":
    import sys
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    dialog = MultiPeriodDialog()
    dialog.show()
    sys.exit(app.exec())
