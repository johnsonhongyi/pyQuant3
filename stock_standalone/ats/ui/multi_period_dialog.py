# -*- coding: utf-8 -*-
"""
ATS PyQt6 Multi-Period Strategy Tester Dialog
Provides multi-period cross filtering, strategy management, concept analysis, 
and linkage with external terminals.
"""

import sys
import os

# 允许单独运行此脚本，将项目根目录加入 sys.path（打包环境下跳过工作目录切换，由 get_app_root 统一接管）
if __name__ == "__main__":
    is_packaged = getattr(sys, 'frozen', False) or "NUITKA_ONEFILE_DIRECTORY" in os.environ or hasattr(sys, 'nuitka_version')
    if not is_packaged:
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
    mock_font = ModuleType("tkinter.font")
    mock_msg = ModuleType("tkinter.messagebox")
    mock_ttk = ModuleType("tkinter.ttk")
    mock_scroll = ModuleType("tkinter.scrolledtext")
    
    sys.modules["tkinter"] = mock_tk
    sys.modules["tkinter.font"] = mock_font
    sys.modules["tkinter.messagebox"] = mock_msg
    sys.modules["tkinter.ttk"] = mock_ttk
    sys.modules["tkinter.scrolledtext"] = mock_scroll

# 🚀 [防弹属性补全] 无论是否真实导入了 tkinter，确保关键组件属性绝对存在
import tkinter
for _attr in ["Toplevel", "Tk", "Frame", "Label", "Button", "Entry", "StringVar", 
              "BooleanVar", "IntVar", "DoubleVar", "Widget", "PanedWindow", "Event"]:
    if not hasattr(tkinter, _attr):
        setattr(tkinter, _attr, object)

try:
    import tkinter.ttk as _ttk
    for _attr in ["Style", "PanedWindow", "Panedwindow", "Treeview", "Scrollbar"]:
        if not hasattr(_ttk, _attr):
            setattr(_ttk, _attr, object)
except Exception:
    pass
# ---------------------------------------------

import json
import time
import re
import io
import threading
import pandas as pd
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QComboBox, QSplitter, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu,
    QApplication, QMessageBox, QTextEdit, QListWidget, QFrame,
    QDialogButtonBox, QSizePolicy, QCompleter, QDateEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QRect, QByteArray, QStringListModel, QDate, QEvent
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

class QtVarProxy:
    """包装 QCheckBox 或 Callable 为带 .get() 方法的 Var 对象，用于兼容全系统 StockSender 标准单例"""
    def __init__(self, getter_func):
        self.getter_func = getter_func
    def get(self):
        try:
            return bool(self.getter_func())
        except Exception:
            return True

logger = LoggerFactory.getLogger(__name__)

from PyQt6.QtCore import QObject

class ATSUIEventHub(QObject):
    """全局 UI 事件广播中心：当主窗口或多周期窗口退出时，向所有悬浮独立窗口 (DNA、诊断、个股详情等) 广播退出事件以主动关闭"""
    multi_period_closing = pyqtSignal()
    main_window_closing = pyqtSignal()

ui_event_hub = ATSUIEventHub()
_CONFIG_FILE_LOCK = threading.RLock()
_active_workers = set()


def safe_float(val, default=0.0):
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return float(val)
    except Exception:
        return default


class TqdmToPyQtBridge(io.TextIOBase):
    """
    捕获底层 tqdm 控制台输出（如 Running_MP: 38%|... | 361/5.55k [00:21<04:23, 19.7it/s]）并实时发射为 PyQt 状态栏进度信号
    """
    def __init__(self, original_stream, progress_signal=None, prefix=""):
        super().__init__()
        self.original_stream = original_stream
        self.progress_signal = progress_signal
        self.prefix = prefix
        self._last_emit_ts = 0.0
        self._buffer = ""
        self._last_parsed_info = ""

    def write(self, s):
        if self.original_stream:
            try:
                self.original_stream.write(s)
            except Exception:
                pass

        if not self.progress_signal or not s:
            return len(s)

        self._buffer += s
        if '\r' in self._buffer or '\n' in self._buffer:
            lines = re.split(r'[\r\n]+', self._buffer)
            latest_chunk = ""
            for line in reversed(lines):
                if line.strip():
                    latest_chunk = line.strip()
                    break
            self._buffer = lines[-1]

            if latest_chunk:
                # 抓取数量/用时/速率细节，如 "991/5.55k [00:50<03:28, 21.8it/s]"
                m_detail = re.search(r'([\d\.]+[kMGT]?/[\d\.]+[kMGT]?\s*\[[^\]]+\])', latest_chunk)
                if m_detail:
                    self._last_parsed_info = m_detail.group(1).strip()

                # 抓取百分比/描述前缀，如 "Running_MP: 21%" 或 "21%"
                m_pct = re.search(r'((?:[\w_-]+:\s*)?\d+%)', latest_chunk)
                m_h5 = re.search(r'(st_df is not find [^\r\n]+)', latest_chunk)

                msg = ""
                if m_h5:
                    tbl = m_h5.group(1).split()[-1] if len(m_h5.group(1).split()) > 0 else ""
                    msg = f"⚡ {self.prefix} 正在自动拆分解构 H5 表 ({tbl})..."
                elif m_pct:
                    pct_str = m_pct.group(1).strip()
                    if self._last_parsed_info:
                        msg = f"⚡ {self.prefix} 数据初始化: {pct_str} | {self._last_parsed_info}"
                    else:
                        msg = f"⚡ {self.prefix} 数据初始化: {pct_str}"

                if msg:
                    now = time.time()
                    if now - self._last_emit_ts >= 0.08:
                        self._last_emit_ts = now
                        self.progress_signal.emit(msg)

        return len(s)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


class AllStrategiesHitWorker(QThread):
    """
    QThread worker for evaluating hit counts for all strategies in the background.
    """
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, engine, strategies, active_periods, top_now=None, force_reload=False, period_cache_ts=None, top_now_cache_ts=None, end=None, allow_auto_init=False):
        super().__init__()
        self.engine = engine
        self.strategies = strategies
        self.active_periods = active_periods
        self.top_now = top_now
        self.force_reload = force_reload
        self.period_cache_ts = period_cache_ts if period_cache_ts is not None else {}
        self.top_now_cache_ts = top_now_cache_ts if top_now_cache_ts is not None else [0.0]
        self.end = end
        self.allow_auto_init = allow_auto_init

    def _is_cache_valid(self, ts):
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()
        if not is_trade:
            return (time.time() - ts) < 1800
        return (time.time() - ts) < 900  # 盘中交易时段 15 分钟 (900s) TTL 自动刷新

    def run(self):
        try:
            # 1. 优先从 IPCSyncManager 获取实时行情 snapshot
            if self.top_now is None or not self._is_cache_valid(self.top_now_cache_ts[0]):
                try:
                    from multi_period_strategy_engine import get_global_ipc_sync_manager
                    ipc_mgr = get_global_ipc_sync_manager()
                    if ipc_mgr is not None:
                        ipc_df = ipc_mgr.get_current_df()
                        if ipc_df is not None and not ipc_df.empty and len(ipc_df) > 100:
                            self.top_now = ipc_df
                            self.top_now_cache_ts[0] = time.time()
                            logger.info(f"[AllStrategiesHitWorker] ⚡ 优先使用 IPC 实时行情数据 (共 {len(ipc_df)} 行)")
                except Exception as e_ipc:
                    logger.debug(f"IPC top_now fetch failed: {e_ipc}")

            if self.top_now is None or not self._is_cache_valid(self.top_now_cache_ts[0]):
                self.progress.emit("正在获取全市场实时行情数据...")
                from JSONData import sina_data
                _sina = sina_data.Sina(readonly=True)
                self.top_now = _sina.all
                if self.top_now is not None and not self.top_now.empty:
                    if 'ratio' not in self.top_now.columns:
                        try:
                            from sys_utils import get_ratio_from_percent
                            self.top_now['ratio'] = get_ratio_from_percent(self.top_now['percent'].values)
                        except Exception:
                            pass
                    self.top_now_cache_ts[0] = time.time()

            if self.top_now is None or self.top_now.empty:
                self.progress.emit("正在同步实时行情 (降级获取)...")
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
                self.top_now_cache_ts[0] = time.time()

            # 2. 确保各个勾选周期的数据已载入
            import contextlib
            with self.engine.lock:
                self.engine._missing_periods.clear()
            is_readonly = not self.allow_auto_init
            for period in self.active_periods:
                if self.force_reload or period not in self.engine._period_dfs or self.engine._period_dfs[period].empty:
                    self.progress.emit(f"正在同步 {period} 周期特征数据...")
                    bridge = TqdmToPyQtBridge(sys.stderr, self.progress, prefix=f"[{period}]")
                    with contextlib.redirect_stderr(bridge), contextlib.redirect_stdout(bridge):
                        self.engine.load_period_data(period, self.top_now, force_reload=self.force_reload, end=self.end, readonly=is_readonly)

            # 3. 开始评估各个策略
            total = len(self.strategies)
            results = {}
            for idx, strat in enumerate(self.strategies, 1):
                if self.isInterruptionRequested():
                    logger.info("[AllStrategiesHitWorker] Interruption requested during evaluation loop, exiting thread.")
                    return
                self.progress.emit(f"正在测试全量策略 Hit: {idx}/{total} ({strat['name']})...")
                try:
                    res_df = self.engine.evaluate_strategy(strat, self.active_periods)
                    hit_cnt = len(res_df) if res_df is not None else 0
                except Exception as ex:
                    logger.warning(f"Failed to evaluate strategy {strat['name']}: {ex}")
                    hit_cnt = 0
                strat_id = strat.get('id')
                if strat_id:
                    results[strat_id] = hit_cnt
                results[strat['name']] = hit_cnt

            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class SingleCodeAllHitWorker(QThread):
    """
    后台异步线程：评估全量策略库对单个诊断股票 code 的 Hit 状态，
    彻底脱离 UI 主线程事件循环，绝对避免 UI 界面 (未响应) 冻结卡死。
    """
    finished_signal = pyqtSignal(str, dict, list)  # (code, single_code_hit_results, all_strategy_reports)

    def __init__(self, engine, strategies, code, active_periods):
        super().__init__()
        self.engine = engine
        self.strategies = strategies
        self.code = code
        self.active_periods = active_periods

    def run(self):
        single_code_hit_results = {}
        all_strategy_reports = []
        if self.strategies and self.engine:
            for strat in self.strategies:
                if self.isInterruptionRequested():
                    break
                s_id = strat.get('id', strat.get('name'))
                s_name = strat.get('name', '未命名策略')
                try:
                    res_df = self.engine.evaluate_strategy(strat, self.active_periods)
                    is_hit = (res_df is not None and not res_df.empty and self.code in res_df.index)
                except Exception:
                    is_hit = False

                single_code_hit_results[s_id] = is_hit
                single_code_hit_results[s_name] = is_hit
                all_strategy_reports.append({
                    'id': s_id,
                    'name': s_name,
                    'hit': is_hit,
                    'strategy': strat
                })

        if not self.isInterruptionRequested():
            self.finished_signal.emit(self.code, single_code_hit_results, all_strategy_reports)


class MultiPeriodWorker(QThread):
    """
    QThread worker for running multi-period strategy evaluations in the background.
    """
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, float, object)  # result_df, elapsed, flat_df
    error = pyqtSignal(str)

    def __init__(self, engine, strat_config, active_periods, top_now=None, force_reload=False, allow_auto_init=False, period_cache_ts=None, top_now_cache_ts=None, end=None):
        super().__init__()
        self.engine = engine
        self.strat_config = strat_config
        self.active_periods = active_periods
        self.top_now = top_now
        self.force_reload = force_reload
        self.allow_auto_init = allow_auto_init
        self.period_cache_ts = period_cache_ts if period_cache_ts is not None else {}
        self.top_now_cache_ts = top_now_cache_ts if top_now_cache_ts is not None else [0.0]
        self.end = end

    def _is_cache_valid(self, ts):
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()
        if not is_trade:
            # 🛡️ 非交易时段 (非盘中/夜间/周末): 市场收盘状态，行情数据保持静态不变，Cache 始终有效
            return True
        return (time.time() - ts) < 900  # 盘中交易时段 15 分钟 (900s) TTL 自动刷新

    def run(self):
        try:
            start_time = time.time()

            if self.force_reload:
                # 盘中强制刷新：仅更新 top_now 实时行情，不清空内存中已载入的多周期历史特征数据
                self.top_now = None
                self.top_now_cache_ts[0] = 0.0

            # 1. Load market snapshots (top_now) - 优先 IPC 高密实时行情
            if self.top_now is None or not self._is_cache_valid(self.top_now_cache_ts[0]) or self.force_reload:
                try:
                    from multi_period_strategy_engine import get_global_ipc_sync_manager
                    ipc_mgr = get_global_ipc_sync_manager()
                    if ipc_mgr is not None:
                        ipc_df = ipc_mgr.get_current_df()
                        if ipc_df is not None and not ipc_df.empty and len(ipc_df) > 100 and len(ipc_df.columns) >= 20:
                            self.top_now = ipc_df
                            self.top_now_cache_ts[0] = time.time()
                            logger.info(f"[MultiPeriodWorker] ⚡ 优先使用 IPC 实时行情数据 (共 {len(ipc_df)} 行, {len(ipc_df.columns)} 列)")
                except Exception as e_ipc:
                    logger.debug(f"IPC top_now fetch failed: {e_ipc}")

            if self.top_now is None or not self._is_cache_valid(self.top_now_cache_ts[0]) or self.force_reload:
                self.progress.emit("正在获取全市场实时行情数据...")
                from JSONData import sina_data
                try:
                    _sina = sina_data.Sina(readonly=True)
                    self.top_now = _sina.all
                except Exception as e:
                    logger.warning(f"Sina fetch error: {e}")
                    self.top_now = None

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

            # ── 2. 各周期数据同步与衍生指标重算 ──
            # 设计对齐 data_utils.py L3531-3558：
            #   - 已缓存周期：combine_dataFrame(top_all, top_now_filtered) + complete_indicators_pipeline
            #   - 未缓存/强制初始化：走 load_period_data（内部已包含完整 pipeline）
            # 保证 dff/dff2/dff3/percent/Rank/win 等全部衍生指标每次刷新都被重算，不再静默跳过。
            from data_utils import complete_indicators_pipeline
            import contextlib

            for period in self.active_periods:
                if self.isInterruptionRequested():
                    logger.info("[MultiPeriodWorker] Interruption requested during period loop, exiting thread.")
                    return
                p_norm = str(period).strip()
                is_force_init = self.force_reload and self.allow_auto_init

                # 读取缓存状态（在锁内）—— 使用显式 None 判断，避免 DataFrame 布尔歧义
                if hasattr(self.engine, "lock"):
                    with self.engine.lock:
                        df_cached = self.engine._period_dfs.get(period)
                        if df_cached is None:
                            df_cached = self.engine._period_dfs.get(p_norm)
                        is_missing = (period in self.engine._missing_periods or
                                      p_norm in self.engine._missing_periods)
                else:
                    df_cached = self.engine._period_dfs.get(period)
                    if df_cached is None:
                        df_cached = self.engine._period_dfs.get(p_norm)
                    is_missing = (period in self.engine._missing_periods or
                                  p_norm in self.engine._missing_periods)

                has_cache = df_cached is not None and not df_cached.empty
                cache_ts = self.period_cache_ts.get(period) or self.period_cache_ts.get(p_norm) or 0.0
                if has_cache and cache_ts == 0.0:
                    cache_ts = time.time()
                    self.period_cache_ts[period] = cache_ts
                    self.period_cache_ts[p_norm] = cache_ts

                # 🛡️ [全周期防死锁自愈机制]
                # 若某周期 (d, 2d, 3d, w, m 等) 曾因开盘瞬间/临时波动被划入 _missing_periods，
                # 在后台刷新时全自动解除 missing 锁定，给予其重新加载的机会，彻底根治开盘 hit 信号丢失死锁！
                if is_missing:
                    _lock = self.engine.lock if hasattr(self.engine, "lock") else threading.RLock()
                    with _lock:
                        self.engine._missing_periods.pop(period, None)
                        self.engine._missing_periods.pop(p_norm, None)
                    is_missing = False

                if has_cache and self._is_cache_valid(cache_ts) and not self.force_reload:
                    # ── 1. 内存缓存有效且未超时（<15分钟）：直接极速复用，不重新计算 ──
                    self.progress.emit(f"⚡ [{period}] 命中内存缓存 (极速复用)")
                    continue

                elif has_cache and not is_force_init and not self.force_reload:
                    # ── 2. 内存有缓存，但已超时（>15分钟）：增量合并 top_now 并重算衍生指标 ──
                    self.progress.emit(f"⚡ [{period}] 缓存已超时(>15分钟)，合并实时行情并重算衍生指标...")
                    try:
                        if self.top_now is not None and not self.top_now.empty:
                            if p_norm != 'd':
                                # 非日线大周期：只合并 OHLCV + name，与 data_utils.py L3547-3549 一致
                                core_cols = ['open', 'high', 'low', 'close', 'vol', 'volume', 'amount', 'name']
                                top_now_filtered = self.top_now[[c for c in core_cols
                                                                  if c in self.top_now.columns]].copy()
                            else:
                                # 日线：全量合并（与 data_utils.py L3550-3551 一致）
                                top_now_filtered = self.top_now

                            # combine_dataFrame：用 top_now 更新 df_cached，保留历史特征列不丢
                            top_all = cct.combine_dataFrame(df_cached, top_now_filtered,
                                                            col="couts", compare="dff")

                            # complete_indicators_pipeline：重算全量衍生指标
                            top_all = complete_indicators_pipeline(top_all, logger, resample=p_norm)

                            # 写回 engine 缓存
                            _lock = self.engine.lock if hasattr(self.engine, "lock") else threading.RLock()
                            with _lock:
                                self.engine._period_dfs[period] = top_all
                                self.engine._period_dfs[p_norm] = top_all
                            self.period_cache_ts[period] = time.time()
                            self.period_cache_ts[p_norm] = time.time()
                    except Exception as e:
                        logger.warning(f"[{period}] combine+pipeline 刷新异常，降级复用旧缓存: {e}")

                else:
                    # ── 3. 未缓存/强制初始化路径：走完整 load_period_data ──
                    if is_force_init:
                        self.progress.emit(f"⚡ [{period}] 正在强制刷新并全自动初始化底层 [{period}] 数据...")
                    else:
                        self.progress.emit(f"📥 [{period}] 首次/只读加载特征数据，正在读取计算...")

                    _lock = self.engine.lock if hasattr(self.engine, "lock") else threading.RLock()
                    with _lock:
                        self.engine._period_dfs.pop(period, None)
                        self.engine._period_dfs.pop(p_norm, None)

                    bridge = TqdmToPyQtBridge(sys.stderr, self.progress, prefix=f"[{period}]")
                    is_readonly = not self.allow_auto_init
                    with contextlib.redirect_stderr(bridge), contextlib.redirect_stdout(bridge):
                        self.engine.load_period_data(period, self.top_now,
                                                     force_reload=self.force_reload,
                                                     end=self.end, readonly=is_readonly)

                    self.period_cache_ts[period] = time.time()
                    self.period_cache_ts[p_norm] = time.time()

                    if period in self.engine._missing_periods:
                        reason = self.engine._missing_periods[period]
                        self.progress.emit(f"⚠️ [{period}] 数据不可用({reason})，策略将自适应跳过此周期过滤")

            # ── 3. [最后数据回补] 所有周期选择加载完成后，最后统一全量回补高密 IPC 实时行情数据 ──
            try:
                from multi_period_strategy_engine import get_global_ipc_sync_manager
                ipc_mgr = get_global_ipc_sync_manager()
                if ipc_mgr is not None:
                    ipc_df = ipc_mgr.get_current_df()
                    try:
                        is_work_time = cct.get_work_time()
                    except Exception:
                        is_work_time = False

                    last_recv = getattr(ipc_mgr, 'last_recv_t', 0.0)
                    cache_expired = (time.time() - last_recv > 900.0) if is_work_time else False
                    has_valid_ipc = (ipc_df is not None and not ipc_df.empty and len(ipc_df.columns) >= 20)

                    # 仅在内存无数据/数据不足/或交易期内 Cache 超时且 force_reload 时，才触发 Pipe 管道 request_full_sync
                    if not has_valid_ipc or (cache_expired and self.force_reload):
                        ipc_mgr.request_full_sync()
                        for _ in range(25):
                            time.sleep(0.1)
                            ipc_df = ipc_mgr.get_current_df()
                            if ipc_df is not None and not ipc_df.empty and len(ipc_df.columns) >= 20:
                                break

                    if ipc_df is not None and not ipc_df.empty and len(ipc_df.columns) >= 20:
                        self.top_now = ipc_df
                        self.top_now_cache_ts[0] = time.time()

                        # 回补更新日线 'd' 周期的 IPC 策略与 400+ 高密衍生列（按需缓存，防范非交易时段与重复点击造成的卡顿）
                        df_d = self.engine._period_dfs.get('d')
                        if df_d is not None and not df_d.empty:
                            df_d = self.engine.ensure_strategy_ipc_columns(df_d, force_refresh=self.force_reload)
                            with self.engine.lock:
                                self.engine._period_dfs['d'] = df_d
                        logger.info(f"[MultiPeriodWorker] ⚡ [最后数据回补完成] 成功注入 IPC 高密实时行情 (共 {len(ipc_df)} 行, {len(ipc_df.columns)} 列)")
            except Exception as e_backfill:
                logger.warning(f"[MultiPeriodWorker] 最后 IPC 数据回补遇到异常: {e_backfill}")

            self.progress.emit("🔍 正在执行跨周期交叉验证...")
            result_df = self.engine.evaluate_strategy(self.strat_config, self.active_periods, force_refresh=self.force_reload)

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
                    renamed_dict = {c: (c if c.endswith(f"_{period}") else f"{c}_{period}") for c in cols_to_join}
                    df_p_sub = df_p[cols_to_join].rename(columns=renamed_dict)
                    df_p_sub = df_p_sub.loc[:, ~df_p_sub.columns.duplicated(keep='first')]
                    df_p_sub = df_p_sub[~df_p_sub.index.duplicated(keep='first')]
                    
                    overlap_cols = [col for col in df_p_sub.columns if col in flat_df.columns]
                    if overlap_cols:
                        flat_df = flat_df.drop(columns=overlap_cols, errors='ignore')
                    
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
        
        # 🚀 开启标准窗口标志：允许标题栏双击/点击最大化与还原、最小化与尺寸拖拽
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)

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
            
            /* 赛马视觉：极窄精美滚动条 */
            QScrollBar:vertical {
                border: none;
                background: #12121a;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3a3f58;
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #6366f1;
            }
            QScrollBar::handle:vertical:pressed {
                background: #818cf8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                border: none;
                background: #12121a;
                height: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal {
                background: #3a3f58;
                min-width: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #6366f1;
            }
            QScrollBar::handle:horizontal:pressed {
                background: #818cf8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                border: none;
                background: none;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        # Load saved geometry
        self.config_path = os.path.join(get_app_root(), "config", "standalone_tester_config.json")

        self._init_ui()
        self._load_geometry()
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

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if hasattr(self, 'btn_toggle_max') and self.btn_toggle_max is not None:
                if self.isMaximized():
                    self.btn_toggle_max.setText("🗗 还原窗口")
                    self.btn_toggle_max.setToolTip("还原为常规窗口尺寸")
                else:
                    self.btn_toggle_max.setText("🗖 快速放大")
                    self.btn_toggle_max.setToolTip("全屏最大化显示策略编辑器")
        super().changeEvent(event)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def showEvent(self, event):
        super().showEvent(event)
        # 布局完成 50ms 后精确恢复 Splitter 分割线尺寸与比例，防止被初次窗口绘制初始化布局重置冲掉
        QTimer.singleShot(50, self._restore_splitter_state)

    def _load_geometry(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    geom_saved = cfg.get("editor_geometry_qt")
                    if geom_saved:
                        self.restoreGeometry(QByteArray.fromHex(geom_saved.encode('utf-8')))
                    if cfg.get("editor_is_maximized", False):
                        QTimer.singleShot(0, self.showMaximized)
            except Exception as e:
                logger.warning(f"Failed to load editor geometry: {e}")

    def _restore_splitter_state(self):
        if not hasattr(self, 'splitter') or self.splitter is None:
            return
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    splitter_saved = cfg.get("editor_splitter_qt")
                    restored = False
                    if splitter_saved:
                        restored = self.splitter.restoreState(QByteArray.fromHex(splitter_saved.encode('utf-8')))
                    if not restored and "editor_splitter_sizes" in cfg:
                        sizes = cfg["editor_splitter_sizes"]
                        if isinstance(sizes, list) and len(sizes) == 2 and sum(sizes) > 0:
                            self.splitter.setSizes(sizes)
            except Exception as e:
                logger.warning(f"Failed to restore editor splitter state: {e}")

    def _save_geometry(self):
        try:
            geom = self.saveGeometry().toHex().data().decode('utf-8')
            cfg = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg["editor_geometry_qt"] = geom
            cfg["editor_is_maximized"] = self.isMaximized()
            if hasattr(self, 'splitter') and self.splitter is not None:
                cfg["editor_splitter_qt"] = self.splitter.saveState().toHex().data().decode('utf-8')
                cfg["editor_splitter_sizes"] = self.splitter.sizes()
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save editor geometry/splitter: {e}")

    def done(self, r):
        self._save_geometry()
        super().done(r)

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.splitterMoved.connect(lambda *args: self._save_geometry())
        main_layout.addWidget(self.splitter)

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

        # ── 排序控制按钮 ──
        sort_row = QHBoxLayout()
        self.btn_top = QPushButton("📍 置顶", self)
        self.btn_top.setStyleSheet("background-color: #0d47a1; border-color: #0a357a;")
        self.btn_top.clicked.connect(self._move_to_top)
        
        self.btn_up = QPushButton("⬆️ 上移", self)
        self.btn_up.setStyleSheet("background-color: #2e3b4e; border-color: #3d4d65;")
        self.btn_up.clicked.connect(self._move_up)
        
        self.btn_down = QPushButton("⬇️ 下移", self)
        self.btn_down.setStyleSheet("background-color: #2e3b4e; border-color: #3d4d65;")
        self.btn_down.clicked.connect(self._move_down)
        
        sort_row.addWidget(self.btn_top)
        sort_row.addWidget(self.btn_up)
        sort_row.addWidget(self.btn_down)
        left_layout.addLayout(sort_row)

        self.splitter.addWidget(left_widget)

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

        # 1.5 Strategy Description
        desc_layout = QHBoxLayout()
        lbl_desc = QLabel("策略说明:", self)
        self.desc_edit = QTextEdit(self)
        self.desc_edit.setMinimumHeight(85)
        self.desc_edit.setMaximumHeight(125)
        self.desc_edit.setPlaceholderText("请输入策略详细说明、买点逻辑与防追高规则...")
        self.desc_edit.textChanged.connect(self._on_desc_changed)
        desc_layout.addWidget(lbl_desc)
        desc_layout.addWidget(self.desc_edit)
        right_layout.addLayout(desc_layout)

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

        self.btn_toggle_max = QPushButton("🗖 快速放大", self)
        self.btn_toggle_max.setToolTip("全屏最大化/还原策略编辑器窗口")
        self.btn_toggle_max.setStyleSheet("background-color: #37474f; color: #81d4fa; border: 1px solid #455a64;")
        self.btn_toggle_max.clicked.connect(self._toggle_maximize)
        bottom_layout.addWidget(self.btn_toggle_max)

        bottom_layout.addStretch()

        self.btn_save = QPushButton("✅ 先应用并保存", self)
        self.btn_save.setStyleSheet("background-color: #2e7d32; font-weight: bold;")
        self.btn_save.clicked.connect(self._save_to_engine)
        bottom_layout.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("❌ 取消", self)
        self.btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(self.btn_cancel)

        right_layout.addLayout(bottom_layout)

        self.splitter.addWidget(right_widget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

    def _refresh_list(self):
        self.list_widget.clear()
        # 建立主窗口下拉框中策略纯名字到含 Hit 文本的映射
        hit_map = {}
        recent_ids = []
        p = self.parent()
        if p:
            if hasattr(p, 'strategy_combo'):
                import re
                for i in range(p.strategy_combo.count()):
                    t = p.strategy_combo.itemText(i)
                    raw_name = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
                    raw_name = re.sub(r'\s*\[Hit:[^\]]+\]$', '', raw_name)
                    hit_map[raw_name] = t
            if hasattr(p, 'ui_state'):
                recent_ids = p.ui_state.get('recent_strategy_ids', [])

        # 对 recent_ids 中的有效策略进行编号
        valid_strat_ids = {s['id'] for s in self.strategies}
        recent_ids = [rid for rid in recent_ids if rid in valid_strat_ids]
        recent_ids = recent_ids[:10]

        prefixes = ["❶ ", "❷ ", "❸ ", "❹ ", "❺ ", "❻ ", "❼ ", "❽ ", "❾ ", "❿ "]
        for s in self.strategies:
            display_name = s['name']
            if display_name in hit_map:
                display_name = hit_map[display_name]
            
            # 补漏保障
            import re
            has_pref = re.match(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]', display_name)
            if not has_pref and s['id'] in recent_ids:
                idx = recent_ids.index(s['id'])
                if idx < len(prefixes):
                    display_name = f"{prefixes[idx]}{display_name}"
            self.list_widget.addItem(display_name)

    def _move_to_top(self):
        row = self.list_widget.currentRow()
        if row <= 0 or row >= len(self.strategies):
            return
        strat = self.strategies.pop(row)
        self.strategies.insert(0, strat)
        self._refresh_list()
        self.list_widget.setCurrentRow(0)

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row <= 0 or row >= len(self.strategies):
            return
        self.strategies[row], self.strategies[row - 1] = self.strategies[row - 1], self.strategies[row]
        self._refresh_list()
        self.list_widget.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.strategies) - 1:
            return
        self.strategies[row], self.strategies[row + 1] = self.strategies[row + 1], self.strategies[row]
        self._refresh_list()
        self.list_widget.setCurrentRow(row + 1)


    def _on_select(self, row):
        if row < 0 or row >= len(self.strategies):
            self.current_idx = -1
            return

        self.current_idx = row
        strat = self.strategies[row]

        # Block signals temporarily to prevent loop updates
        self.name_edit.blockSignals(True)
        self.mode_combo.blockSignals(True)
        self.desc_edit.blockSignals(True)

        self.name_edit.setText(strat['name'])
        self.desc_edit.setPlainText(strat.get('description', ''))
        mode_str = "并集 (union)" if strat.get('cross_mode') == 'union' else "交集 (intersection)"
        self.mode_combo.setCurrentText(mode_str)

        self.name_edit.blockSignals(False)
        self.mode_combo.blockSignals(False)
        self.desc_edit.blockSignals(False)

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

    def _on_desc_changed(self):
        if self.current_idx >= 0:
            self.strategies[self.current_idx]['description'] = self.desc_edit.toPlainText().strip()
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
            
            # 🚀 [3秒自动关闭弹窗模式] 不卡顿用户交互
            msg_box = QMessageBox(QMessageBox.Icon.Information, "成功", "✅ JSON 配置应用成功！(3秒后自动关闭)", parent=self)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            QTimer.singleShot(3000, msg_box.accept)
            msg_box.exec()
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
            return False, None

        if hasattr(self.engine, 'validate_condition'):
            success, msg = self.engine.validate_condition(expr, period)
            if success:
                # 🎯 自动加载/求解实际命中数据 Hit Count
                hit_cnt = None
                try:
                    df_p = None
                    # 1. 尝试从引擎已有的周期缓存中提取
                    if hasattr(self.engine, "_period_dfs") and period in self.engine._period_dfs:
                        df_p = self.engine._period_dfs[period]

                    # 2. 获取基准 top_now 数据（主窗口缓存 > 全局数据）
                    top_now = None
                    if hasattr(self, "parent") and self.parent is not None and getattr(self.parent, "top_now", None) is not None:
                        top_now = self.parent.top_now

                    # 3. 若当前周期 DataFrame 尚未加载，自动触发 load_period_data 动态装载
                    if (df_p is None or df_p.empty) and hasattr(self.engine, "load_period_data"):
                        if top_now is None or top_now.empty:
                            try:
                                from JSONData import sina_data
                                _sina = sina_data.Sina(readonly=True)
                                top_now = _sina.all
                            except Exception as ex:
                                logger.debug(f"Sina fallback failed: {ex}")
                        if top_now is not None and not top_now.empty:
                            df_p = self.engine.load_period_data(period, top_now)

                    if (df_p is None or df_p.empty) and period == 'd' and top_now is not None and not top_now.empty:
                        df_p = top_now

                    # 4. 执行 query_engine.execute 高级花括号宏与全Col过滤求值
                    if df_p is not None and not df_p.empty:
                        if hasattr(self.engine, 'ensure_strategy_ipc_columns') and str(period).strip() in ('d', '1d', 'day'):
                            df_p = self.engine.ensure_strategy_ipc_columns(df_p, strategy_expr=expr)
                            if hasattr(self.engine, 'lock'):
                                with self.engine.lock:
                                    self.engine._period_dfs[period] = df_p
                                    self.engine._period_dfs['d'] = df_p

                        from query_engine_util import query_engine
                        df_clean = df_p.fillna(0)
                        if query_engine:
                            matched = query_engine.execute(df_clean, expr)
                        else:
                            matched = df_clean.query(expr)
                        hit_cnt = len(matched) if matched is not None else 0
                except Exception as ex:
                    logger.warning(f"Hit calculation error for {period}: {ex}")

                if hit_cnt is not None:
                    widgets['status_lbl'].setText(f"✅ 语法正确 (🎯{hit_cnt})")
                    widgets['status_lbl'].setStyleSheet("color: #4caf50; font-weight: bold;")
                    widgets['status_lbl'].setToolTip(f"{msg}\n\n🎯 命中测试: 当前【{period}】周期筛选出 {hit_cnt} 只股票")
                else:
                    widgets['status_lbl'].setText("✅ 语法正确")
                    widgets['status_lbl'].setStyleSheet("color: #4caf50;")
                    widgets['status_lbl'].setToolTip(f"{msg}\n\n(提示: 正在准备基础行情数据)")
                return True, hit_cnt
            else:
                widgets['status_lbl'].setText("❌ 语法错误")
                widgets['status_lbl'].setStyleSheet("color: #f44336;")
                widgets['status_lbl'].setToolTip(msg)
                return False, None

        # Fallback if engine has no validate_condition
        try:
            widgets['status_lbl'].setText("✅ 语法正确")
            widgets['status_lbl'].setStyleSheet("color: #4caf50;")
            return True, None
        except Exception as e:
            widgets['status_lbl'].setText("❌ 语法错误")
            widgets['status_lbl'].setStyleSheet("color: #f44336;")
            widgets['status_lbl'].setToolTip(str(e))
            return False, None

    def _validate_all(self):
        success = True
        hit_summary = []
        for period, widgets in self.cond_rows.items():
            if widgets['chk'].isChecked():
                res, hit_cnt = self._validate_single(period)
                if not res:
                    success = False
                elif hit_cnt is not None:
                    hit_summary.append(f" • {period} 周期: 🎯 Hit {hit_cnt} 只")
                else:
                    hit_summary.append(f" • {period} 周期: ✅ 语法正确 (待载入数据)")

        if success:
            msg = "✅ 全部激活的条件均通过了语法校验！"
            if hit_summary:
                msg += "\n\n🎯 各周期命中数据分布测试：\n" + "\n".join(hit_summary)
            QMessageBox.information(self, "验证完成", msg)
        else:
            QMessageBox.warning(self, "验证失败", "部分周期的过滤表达式包含语法错误，请查看具体标记！")

    def _save_to_engine(self):
        # 🚀 [先应用，后保存]
        try:
            if self.current_idx >= 0 and hasattr(self, 'json_editor') and self.json_editor.toPlainText().strip():
                try:
                    raw_js = self.json_editor.toPlainText().strip()
                    data = json.loads(raw_js)
                    if 'name' in data and 'conditions' in data:
                        data['id'] = self.strategies[self.current_idx].get('id', data.get('id', str(int(time.time() * 1000))))
                        self.strategies[self.current_idx] = data
                except Exception as ex:
                    logger.warning(f"Auto-apply JSON before saving warning: {ex}")

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
                                hit = str(r.get("hit", "--"))
                                if isinstance(starred, bool):
                                    starred = 1 if starred else 0
                                normalized.append({"query": q, "note": note, "starred": starred, "hit": hit})
                            elif isinstance(r, str):
                                normalized.append({"query": r.strip(), "note": "", "starred": 0, "hit": "--"})
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

        # Input & Controls: Matching baseline order: [Expression Input] [Test] [Add] [Use Selected] [Group Combo]
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("表达式:", self))
        self.query_edit = QLineEdit(self)
        input_layout.addWidget(self.query_edit)

        btn_test = QPushButton("🧪 测试", self)
        btn_test.setStyleSheet("background-color: #0288d1; color: #ffffff;")
        btn_test.setToolTip("测试当前表达式及列表中各条件在筛选数据集中的 Hit 命中股票数")
        btn_test.clicked.connect(self._test_query)
        input_layout.addWidget(btn_test)

        btn_add = QPushButton("添加", self)
        btn_add.clicked.connect(self._add_query)
        input_layout.addWidget(btn_add)

        btn_apply = QPushButton("使用选中", self)
        btn_apply.setStyleSheet("background-color: #2e7d32; color: #ffffff;")
        btn_apply.clicked.connect(self._use_selected)
        input_layout.addWidget(btn_apply)

        self.grp_combo = QComboBox(self)
        self.grp_combo.addItems(["history1", "history2", "history3", "history4", "history5"])
        self.grp_combo.currentIndexChanged.connect(self._on_group_changed)
        input_layout.addWidget(self.grp_combo)
        layout.addLayout(input_layout)

        # Table Widget (5 Columns: Query 表达式, ⭐, 备注说明, Hit 命中数, Group 组别)
        self.table = QTableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Query 表达式", "⭐", "备注说明", "Hit", "Group 组别"])
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
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 35)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 85)

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

    def _calc_expr_hit(self, expr):
        if not expr:
            return "--"
        p = self.parent()
        if not p:
            return "--"
        try:
            if hasattr(p, 'get_current_display_df'):
                df = p.get_current_display_df()
            elif hasattr(p, '_last_flat_df') and p._last_flat_df is not None:
                df = p._last_flat_df
            elif hasattr(p, 'last_result_df') and p.last_result_df is not None:
                df = p.last_result_df
            else:
                return "--"

            if df is None or df.empty:
                return "0"

            if hasattr(p, '_suffix_query'):
                active_periods = [per for per, chk in p.period_checkboxes.items() if chk.isChecked()]
                p_suffix = active_periods[0] if active_periods else 'd'
                conv_query = p._suffix_query(expr, p_suffix)
            else:
                conv_query = expr

            from query_engine_util import query_engine
            try:
                if query_engine:
                    m_df = query_engine.execute(df, conv_query)
                else:
                    m_df = df.query(conv_query)
                return str(len(m_df))
            except Exception:
                try:
                    if query_engine:
                        m_df = query_engine.execute(df, expr)
                    else:
                        m_df = df.query(expr)
                    return str(len(m_df))
                except Exception:
                    return "Err"
        except Exception:
            return "--"

    def _test_query(self):
        # 1. Test current edit text
        q_text = self.query_edit.text().strip()
        edit_hit_msg = ""
        if q_text:
            h_val = self._calc_expr_hit(q_text)
            edit_hit_msg = f"表达式【{q_text}】在当前结果集中命中 {h_val} 只股票；"

        # 2. Batch test all items in current table
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        for idx in range(self.table.rowCount()):
            q_item = self.table.item(idx, 0)
            if q_item:
                expr = q_item.text().strip()
                hit_cnt = self._calc_expr_hit(expr)
                
                # Update table Hit cell
                hit_cell = NumericTableWidgetItem(hit_cnt)
                hit_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if hit_cnt.isdigit() and int(hit_cnt) > 0:
                    hit_cell.setForeground(QBrush(QColor("#66bb6a")))
                    hit_cell.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
                elif hit_cnt == "Err":
                    hit_cell.setForeground(QBrush(QColor("#ef5350")))
                else:
                    hit_cell.setForeground(QBrush(QColor("#b0bec5")))
                self.table.setItem(idx, 3, hit_cell)

                # Update memory
                if idx < len(items) and items[idx].get("query") == expr:
                    items[idx]["hit"] = hit_cnt

        self.lbl_status.setText(f"✅ {edit_hit_msg}列表中各条目 Hit 命中测试完成！")

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

            # Hit
            hit_val = str(item.get("hit", "--"))
            hit_item = NumericTableWidgetItem(hit_val)
            hit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if hit_val.isdigit() and int(hit_val) > 0:
                hit_item.setForeground(QBrush(QColor("#66bb6a")))
                hit_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif hit_val == "Err":
                hit_item.setForeground(QBrush(QColor("#ef5350")))
            else:
                hit_item.setForeground(QBrush(QColor("#b0bec5")))
            self.table.setItem(idx, 3, hit_item)

            # Group
            grp_item = QTableWidgetItem(grp)
            grp_item.setFlags(grp_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 4, grp_item)

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

        items.insert(0, {"query": q, "note": "", "starred": 0, "hit": "--"})
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

            hit_val = str(item.get("hit", "--"))
            hit_item = NumericTableWidgetItem(hit_val)
            hit_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if hit_val.isdigit() and int(hit_val) > 0:
                hit_item.setForeground(QBrush(QColor("#66bb6a")))
                hit_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            elif hit_val == "Err":
                hit_item.setForeground(QBrush(QColor("#ef5350")))
            else:
                hit_item.setForeground(QBrush(QColor("#b0bec5")))
            self.table.setItem(idx, 3, hit_item)

            grp_item = QTableWidgetItem(grp)
            grp_item.setFlags(grp_item.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(idx, 4, grp_item)

    def _use_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        q_item = self.table.item(row, 0)
        note_item = self.table.item(row, 2)
        if q_item:
            query = q_item.text().strip()
            note = note_item.text().strip() if note_item else ""
            display_text = f"{note} ({query})" if note else query
            self.applied.emit(display_text)
            self.accept()

    def _save_and_toast(self):
        # Save modifications in notes from QTableWidget back to data
        grp = self.grp_combo.currentText()
        items = self.history_groups.get(grp, [])
        for row in range(self.table.rowCount()):
            # Safe safeguard in case of searched table
            q_item = self.table.item(row, 0)
            note_item = self.table.item(row, 2)
            hit_item = self.table.item(row, 3)
            grp_item = self.table.item(row, 4)
            
            if q_item and note_item and grp_item:
                target_grp = grp_item.text()
                target_q = q_item.text()
                target_note = note_item.text()
                target_hit = hit_item.text() if hit_item else "--"
                
                target_items = self.history_groups.get(target_grp, [])
                for item in target_items:
                    if item.get("query") == target_q:
                        item["note"] = target_note
                        item["hit"] = target_hit
                        break
        
        self._save_history()
        self.lbl_status.setText("✅ 历史记录备注已保存！")


class ConceptStocksDialog(QDialog, WindowMixin):
    """
    Sub dialog showing all stocks matching a selected concept, with window size/position persistence.
    """
    def __init__(self, parent, concept_name, matched_stocks, columns, headers):
        super().__init__(None)  # 传入 None 彻底切断物理属主关系，绝不强行置顶遮挡
        self._real_parent = parent
        self.setWindowTitle(f"板块【{concept_name}】个股列表 ({len(matched_stocks)}只)")

        # 允许自由拉伸、最大化、最小化，可以放置在多周期主窗口后面，不再强行在父窗口前方遮挡
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)

        self.setMinimumSize(600, 350)
        self.load_window_position_qt(self, "concept_stocks_dialog", default_width=850, default_height=480)

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

    def parent(self):
        return getattr(self, "_real_parent", None)

    def closeEvent(self, event):
        try:
            self.save_window_position_qt(self, "concept_stocks_dialog")
        except Exception:
            pass
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.save_window_position_qt(self, "concept_stocks_dialog")
        except Exception:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        try:
            self.save_window_position_qt(self, "concept_stocks_dialog")
        except Exception:
            pass

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self.table = BaseATSTableWidget(self)
        self.table.setColumnCount(len(self.columns) + 1)
        self.table.setHorizontalHeaderLabels(["序号"] + [self.headers.get(col, col) for col in self.columns])
        
        p = self.parent()
        if p and hasattr(p, 'link_stock'):
            self.table.stock_activated.connect(p.link_stock)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
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
                elif col == 'name':
                    val = row.get('name', '--')
                elif col == 'price':
                    val = row.get('close', row.get('price', '--'))
                else:
                    val = row.get(col, '--')

                if pd.isna(val):
                    val = '--'
                
                # Format numbers & badges
                if isinstance(val, (int, float)):
                    if col == 'price':
                        val_str = f"{val:.2f}"
                    elif col == 'percent':
                        val_str = f"{val:.2f}"
                    elif col == 'volume':
                        val_str = f"{val:.0f}" if val > 1000 else f"{val:.2f}"
                    elif col == 'ratio':
                        val_str = f"{val:.2f}"
                    elif col.startswith('pass_'):
                        val_str = '✅' if bool(val) else '--'
                    else:
                        val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
                    
                    item = NumericTableWidgetItem(val_str)
                    if col.startswith('pass_'):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        if bool(val):
                            item.setForeground(QBrush(QColor("#66bb6a")))
                    elif col == 'percent':
                        if val > 0:
                            item.setForeground(QBrush(QColor("#ff4444")))
                        elif val < 0:
                            item.setForeground(QBrush(QColor("#33cc5a")))
                else:
                    item = QTableWidgetItem(str(val))
                    if col.startswith('pass_'):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        if str(val) in ('True', '1', '✅'):
                            item.setText('✅')
                            item.setForeground(QBrush(QColor("#66bb6a")))
                    elif col == 'percent' and val != '--':
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
        btn_cat = QPushButton("🏷️ 查看所选板块分类", self)
        btn_cat.setStyleSheet("background-color: #00796b;")
        btn_cat.clicked.connect(self._show_selected_category)
        action_layout.addWidget(btn_cat)

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

    def _on_table_double_clicked(self, index):
        row = index.row()
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            if name.startswith("★ "):
                name = name[2:]
            p = self.parent()
            if p and hasattr(p, '_show_stock_category_dialog'):
                p._show_stock_category_dialog(code, name)

    def _show_selected_category(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            if name.startswith("★ "):
                name = name[2:]
            p = self.parent()
            if p and hasattr(p, '_show_stock_category_dialog'):
                p._show_stock_category_dialog(code, name)

    def _diagnose_stock(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        
        code_item = self.table.item(row, 1)
        name_item = self.table.item(row, 2)
        if code_item:
            code = code_item.text().strip()
            name = name_item.text().strip() if name_item else code
            if name.startswith("★ "):
                name = name[2:]
            self.parent().diagnose_stock_strategy(code, name)

    def _dna_audit_stock(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请在个股列表中选择一只股票！")
            return
        
        code_to_name = {}
        for r in range(row, min(self.table.rowCount(), row + 21)):
            code_item = self.table.item(r, 1)
            name_item = self.table.item(r, 2)
            if code_item:
                c = code_item.text().strip().zfill(6)
                n = name_item.text().strip() if name_item else c
                n = n.replace("★ ", "").strip()
                code_to_name[c] = n
            
        if code_to_name:
            active_periods = [p for p, chk in self.parent().period_checkboxes.items() if chk.isChecked()]
            PERIOD_ORDER = {'d': 1, '2d': 2, '3d': 3, 'w': 4, 'm': 5, '45d': 6, '3M': 7}
            sorted_periods = sorted(active_periods, key=lambda x: PERIOD_ORDER.get(x, 99))
            min_period = sorted_periods[0] if sorted_periods else 'd'
            self.parent()._run_dna_audit_batch(code_to_name, resample=min_period)


class ConceptDetailDialog(QDialog, WindowMixin):
    """
    Sub dialog displaying detailed frequency statistics of concept sectors, with window size/position persistence.
    """
    def __init__(self, parent, all_concepts, concept_to_codes):
        super().__init__(None)  # 传入 None 彻底切断物理属主关系，绝不强行置顶遮挡
        self._real_parent = parent
        self.setWindowTitle("📊 概念板块统计详情")

        # 允许自由拉伸、最大化、最小化，可独立在主窗口身后与前台间自由切换层级
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)

        self.setMinimumSize(380, 400)
        self.load_window_position_qt(self, "concept_detail_dialog", default_width=480, default_height=550)

        self.all_concepts = all_concepts
        self.concept_to_codes = concept_to_codes

        self.setStyleSheet("""
            QDialog { background-color: #161822; color: #ffffff; }
            QTableWidget { background-color: #212130; color: #ffffff; gridline-color: #2e2e3e; border: 1px solid #2e2e3e; }
        """)

        self._init_ui()

    def parent(self):
        return getattr(self, "_real_parent", None)

    def closeEvent(self, event):
        try:
            self.save_window_position_qt(self, "concept_detail_dialog")
        except Exception:
            pass
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.save_window_position_qt(self, "concept_detail_dialog")
        except Exception:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        try:
            self.save_window_position_qt(self, "concept_detail_dialog")
        except Exception:
            pass

    def _init_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel(f"📊 当前筛选结果概念板块分布 (共包含 {len(self.all_concepts)} 个概念板块)", self)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #00b0ff; margin-bottom: 4px;")
        layout.addWidget(lbl)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["序号", "概念板块名称", "符合条件只数"])
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
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(2, 90)

        # Populate
        self.table.setRowCount(len(self.all_concepts))
        for idx, (cat_name, count) in enumerate(self.all_concepts):
            idx_item = NumericTableWidgetItem(str(idx + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(idx, 0, idx_item)

            name_item = QTableWidgetItem(f"{cat_name} 概念" if not cat_name.endswith(("概念", "板块")) else cat_name)
            name_item.setForeground(QBrush(QColor("#80d8ff")))
            name_item.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            self.table.setItem(idx, 1, name_item)

            count_item = NumericTableWidgetItem(f"{count} 只")
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            count_item.setForeground(QBrush(QColor("#ffb74d")))
            self.table.setItem(idx, 2, count_item)

    def _on_double_click(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        if row < len(self.all_concepts):
            cat_name, _ = self.all_concepts[row]
            self.parent().show_concept_top10_window(cat_name)


class StockCategoryDetailDialog(QDialog, WindowMixin):
    """
    Sub dialog displaying detailed category details for a specific stock, with window size/position persistence.
    """
    def __init__(self, parent, code, name, category_str):
        super().__init__(None)  # 传入 None 彻底切断物理属主关系，绝不强行置顶遮挡
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._real_parent = parent

        # 🚀【接收主窗口退出事件】：保持为独立悬浮窗口，收到主窗口/多周期退出信号时主动 close()
        try:
            ui_event_hub.multi_period_closing.connect(self.close)
            ui_event_hub.main_window_closing.connect(self.close)
        except Exception:
            pass

        self.setWindowTitle(f"🏷️ 个股分类详情: {name}({code})")
        
        # 允许自由拉伸、最大化、最小化，可独立在主窗口身后与前台间自由切换层级
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        self.setSizeGripEnabled(True)

        self.setMinimumSize(380, 240)
        self.load_window_position_qt(self, "stock_category_detail_dialog", default_width=480, default_height=340)

        self.code = code
        self.name = name
        self.category_str = category_str

        self.setStyleSheet("""
            QDialog { background-color: #161822; color: #ffffff; }
            QTextEdit { background-color: #212130; color: #81d4fa; border: 1px solid #2e2e3e; font-size: 13px; border-radius: 4px; padding: 8px; }
            QPushButton { background-color: #2e3b4e; color: #ffffff; border: 1px solid #3d4d65; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #3f51b5; }
        """)

        layout = QVBoxLayout(self)

        lbl = QLabel(f"🏷️ 个股【{name}】({code}) 完整分类与所属概念标签:", self)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #00b0ff;")
        layout.addWidget(lbl)

        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.text_area.setFont(QFont("Consolas", 10))
        self.text_area.setPlainText(category_str)
        layout.addWidget(self.text_area)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 复制分类信息", self)
        btn_copy.clicked.connect(self._copy_category)
        btn_layout.addWidget(btn_copy)

        btn_diag = QPushButton("🔍 诊断该股", self)
        btn_diag.setStyleSheet("background-color: #0288d1;")
        btn_diag.clicked.connect(self._diagnose_stock)
        btn_layout.addWidget(btn_diag)

        btn_layout.addStretch()
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def parent(self):
        return getattr(self, "_real_parent", None)

    def closeEvent(self, event):
        try:
            self.save_window_position_qt(self, "stock_category_detail_dialog")
        except Exception:
            pass
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            self.save_window_position_qt(self, "stock_category_detail_dialog")
        except Exception:
            pass

    def moveEvent(self, event):
        super().moveEvent(event)
        try:
            self.save_window_position_qt(self, "stock_category_detail_dialog")
        except Exception:
            pass

    def _copy_category(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.category_str)
        QMessageBox.information(self, "提示", "板块概念分类信息已成功复制到剪贴板！")

    def _diagnose_stock(self):
        p = self.parent()
        if p and hasattr(p, 'diagnose_stock_strategy'):
            p.diagnose_stock_strategy(self.code, self.name)

    def _diagnose_stock(self):
        p = self.parent()
        if p and hasattr(p, 'diagnose_stock_strategy'):
            p.diagnose_stock_strategy(self.code, self.name)


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
        self.setWindowTitle("多周期联动策略筛选器")
        self.setMinimumSize(800, 500)

        self._child_dialogs = set()
        self._stock_category_wins = {}

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

        # 初始化项目全系统标准的 StockSender 通道 (动态绑定界面 linkage checkbox 勾选与持久化状态)
        self.sender = None
        try:
            from JohnsonUtil.stock_sender import StockSender
            self.sender = StockSender(
                tdx_var=QtVarProxy(lambda: self.link_tdx_chk.isChecked() if hasattr(self, 'link_tdx_chk') else True),
                ths_var=QtVarProxy(lambda: self.link_ths_chk.isChecked() if hasattr(self, 'link_ths_chk') else False),
                dfcf_var=False,
                callback=None
            )
        except Exception as e:
            print(f"[MultiPeriodDialog] Init standard StockSender failed: {e}")

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
            QTableView { selection-background-color: #1a8cff; selection-color: #ffffff; }
            QTableView::item:selected { background-color: #1a8cff; color: #ffffff; }
            QTableView::item:selected:!active { background-color: #3399ff; color: #ffffff; }
        """)


        # Initialize Strategy Engine
        self.engine = MultiPeriodStrategyEngine()
        self.strategies = self.engine.load_strategies()
        self.manual_col_pool = []
        self._current_table_columns = []

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
        
        # 打开后自动用默认选中的最小周期触发一次筛选
        QTimer.singleShot(6000, lambda: self.run_filter(force_reload=False))

        # ── 后台定时自动刷新 ──
        # 每 15 分钟检查一次：若缓存过期（盘中 >15min / 盘后 >30min）则自动刷新 top_now 并重算指标
        # 非交易时段定时器静默不触发实际拉取（_is_cache_valid 返回 True 时 run_filter 复用缓存不重拉）
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)
        self._auto_refresh_timer.start(900_000)  # 每 900 秒 (15 分钟) tick 一次


    def get_stock_name(self, code):
        from sys_utils import resolve_stock_name
        return resolve_stock_name(code) or "未知个股"

    def _is_cache_valid(self, ts):
        if ts == 0.0:
            return False
        is_trade = cct.get_work_time_duration()
        if not is_trade:
            return (time.time() - ts) < 1800
        return (time.time() - ts) < 900  # 盘中交易时段 15 分钟 (900s) TTL 自动刷新

    def _on_auto_refresh_tick(self):
        """
        后台定时自动刷新回调（每 15 分钟由 _auto_refresh_timer 触发）。
        规则：
          - 仅在交易时段（09:15~15:05）执行，盘后/盘前静默跳过；
          - 若 worker 仍在运行（上次刷新未完成），跳过本次避免堆叠；
          - 调用 run_filter(force_reload=False)，top_now 缓存 TTL 过期时自动重拉，
            否则复用缓存直接重算衍生指标。
        """
        try:
            if not cct.get_work_time_duration():
                # 非交易时段，静默跳过，不产生任何网络请求
                return

            # 若上次 worker 仍在运行，本次跳过（防止堆叠）
            try:
                from PyQt6.sip import isdeleted
                if hasattr(self, "worker") and self.worker is not None:
                    if not isdeleted(self.worker) and self.worker.isRunning():
                        logger.debug("[AutoRefresh] worker 仍在运行，跳过本次定时刷新")
                        return
            except Exception:
                pass

            logger.info("[AutoRefresh] 定时 15min 自动刷新触发 run_filter")
            self.run_filter(force_reload=False)
        except Exception as e:
            logger.warning(f"[AutoRefresh] 定时刷新异常: {e}")

    def _on_focus_mode_changed(self, index):
        """专注能力模式切换回调:
        0: ⭐ 当日买卖特异个股 (专注精选)
        1: ⚡ 自动通道强企稳 (Fib50/下轨)
        2: 👑 板块共振龙头 (大哥带队)
        3: 🌐 全量多周期大结构 (全景)
        """
        if getattr(self, '_initializing', False):
            return
        mode_names = ["⭐ 当日特异", "⚡ 自动通道企稳", "👑 板块共振", "🌐 全量大结构"]
        curr_name = mode_names[index] if index < len(mode_names) else "全量"
        logger.info(f"🔥 [FOCUS_MODE] 切换至专注能力模式: {curr_name}")
        self.lbl_status.setText(f"🔥 已切换专注能力模式: {curr_name}，正在重新计算过滤...")
        if self.last_result_df is not None and not self.last_result_df.empty:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)
        else:
            self.run_filter(force_reload=False)

    def _apply_focus_mode_filter(self, df, focus_idx):
        """执行专注能力模式的数据切片过滤:
        0: ⭐ 当日买卖特异个股 (交集精选顶级特异买点)
        1: ⚡ 自动通道强企稳 (Fib50/下轨/底角)
        2: 👑 板块共振龙头 (大哥带队/大幅领涨)
        3: 🌐 全量多周期大结构 (全景放行)
        """
        if df is None or df.empty or focus_idx == 3:
            return df

        import pandas as pd
        filtered = df.copy()

        if focus_idx == 0:  # ⭐ 仅看当日买卖特异个股 (极致精选特异异动买点)
            cond_bottom = pd.Series(False, index=filtered.index)
            cond_support = pd.Series(False, index=filtered.index)
            cond_momentum = pd.Series(False, index=filtered.index)

            # 1. 见底/起爆信号
            for col in ['sig_bottom_d', 'sig_launch_d', 'sig_bottom_2d', 'sig_bottom']:
                if col in filtered.columns:
                    cond_bottom |= (filtered[col] == 1)

            # 2. 支撑位与上升斜率
            for col in ['ch_pos_d', 'ch_pos_2d', 'ch_pos']:
                if col in filtered.columns:
                    cond_support |= ((filtered[col] >= 5.0) & (filtered[col] <= 38.0))
            for col in ['ch_slope_deg_d', 'slope_deg_d', 'ch_slope_deg']:
                if col in filtered.columns:
                    cond_support |= (filtered[col] >= 1.5)

            # 3. 强动量抬升
            for col in ['percent_d', 'percent']:
                if col in filtered.columns:
                    cond_momentum |= (filtered[col] >= 2.5)
            for col in ['win_d', 'win']:
                if col in filtered.columns:
                    cond_momentum |= (filtered[col] >= 2.0)

            # 要求: 满足见底信号 OR 支撑位，且同时具备强动量
            final_cond = (cond_bottom | cond_support) & cond_momentum
            if final_cond.any():
                filtered = filtered[final_cond]

        elif focus_idx == 1:  # ⚡ 仅看自动通道强企稳 (Fib50/下轨)
            cond = pd.Series(False, index=filtered.index)
            for col in ['sig_bottom_d', 'sig_bottom_2d', 'sig_bottom']:
                if col in filtered.columns:
                    cond |= (filtered[col] == 1)
            for col in ['ch_pos_d', 'ch_pos_2d', 'ch_pos']:
                if col in filtered.columns:
                    cond |= ((filtered[col] >= 5.0) & (filtered[col] <= 30.0))
            if cond.any():
                filtered = filtered[cond]

        elif focus_idx == 2:  # 👑 仅看板块共振龙头 (大哥带队)
            cond = pd.Series(False, index=filtered.index)
            for col in ['is_leader', 'is_sector_leader', 'sector_leader']:
                if col in filtered.columns:
                    cond |= (filtered[col] == 1)
            for col in ['percent_d', 'percent']:
                if col in filtered.columns:
                    cond |= (filtered[col] >= 5.5)  # 强放量拉升带队
            if cond.any():
                filtered = filtered[cond]

        logger.info(f"🔥 [FOCUS_MODE] 专注过滤(模式 {focus_idx}): {len(df)} -> {len(filtered)} 只标的")
        return filtered

    def _load_stays_on_top(self):
        self.ui_state = self._load_state()
        return self.ui_state.get("stays_on_top", False)

    def _load_state(self):
        default_state = {
            "strategy_id": "",
            "recent_strategy_ids": [],
            "periods": ["d", "w", "m"],
            "custom_cols": [],
            "stays_on_top": False,
            "manual_col_pool": [],
            "link_vis": True,
            "link_tdx": False,
            "link_ths": False,
            "sort_level1_col": None,
            "sort_level1_asc": True,
            "sort_level2_col": None,
            "sort_level2_asc": True,
            "sort_level3_col": None,
            "sort_level3_asc": True,
            "sortby_col": None,
            "sortby_col_ascend": False,
            "current_history_query": "",
            "recent_secondary_filters": []
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

    def _get_current_selected_strategy(self):
        if not hasattr(self, 'strategy_combo') or self.strategy_combo is None:
            return None
        import re
        strat_id = self.strategy_combo.currentData()
        if strat_id and hasattr(self, 'strategies') and self.strategies:
            strat = next((s for s in self.strategies if s.get('id') == strat_id), None)
            if strat:
                return strat
        strat_name = self.strategy_combo.currentText()
        if not strat_name:
            return None
        clean_name = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', strat_name)
        clean_name = re.sub(r'\s*\[Hit:[^\]]+\]$', '', clean_name)
        if hasattr(self, 'strategies') and self.strategies:
            return next((s for s in self.strategies if s.get('name') == clean_name), None)
        return None

    def _save_state(self, write_to_disk=True):
        if getattr(self, "_initializing", False):
            return
        try:
            strat = self._get_current_selected_strategy()
            strat_id = strat.get('id', '') if strat else ''
            self.ui_state['strategy_id'] = strat_id
            self.ui_state['recent_strategy_ids'] = self.ui_state.get('recent_strategy_ids', [])
            self.ui_state['periods'] = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
            self.ui_state['custom_cols'] = [c for c, act in self.custom_col_actions.items() if act.isChecked()]
            self.ui_state['manual_col_pool'] = list(self.manual_col_pool)
            self.ui_state['link_vis'] = self.link_vis_chk.isChecked()
            self.ui_state['link_tdx'] = self.link_tdx_chk.isChecked()
            self.ui_state['link_ths'] = self.link_ths_chk.isChecked()
            if hasattr(self, 'chk_readonly'):
                self.ui_state['readonly_mode'] = self.chk_readonly.isChecked()
            self.ui_state['stays_on_top'] = self.on_top_chk.isChecked()
            self.ui_state['sort_level1_col'] = getattr(self, 'sort_level1_col', None)
            self.ui_state['sort_level1_asc'] = getattr(self, 'sort_level1_asc', True)
            self.ui_state['sort_level2_col'] = getattr(self, 'sort_level2_col', None)
            self.ui_state['sort_level2_asc'] = getattr(self, 'sort_level2_asc', True)
            self.ui_state['sort_level3_col'] = getattr(self, 'sort_level3_col', None)
            self.ui_state['sort_level3_asc'] = getattr(self, 'sort_level3_asc', True)
            self.ui_state['sortby_col'] = getattr(self, 'sortby_col', None)
            self.ui_state['sortby_col_ascend'] = getattr(self, 'sortby_col_ascend', False)
            self.ui_state['current_history_query'] = self._current_history_query
            self.ui_state['recent_secondary_filters'] = list(getattr(self, 'recent_secondary_filters', []))
            if hasattr(self, 'focus_mode_combo') and self.focus_mode_combo is not None:
                self.ui_state['focus_mode_index'] = self.focus_mode_combo.currentIndex()

            if write_to_disk:
                cfg = {}
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)

                skip_editor_keys = {"editor_geometry_qt", "editor_splitter_qt", "editor_splitter_sizes", "editor_is_maximized"}
                for k, v in self.ui_state.items():
                    if k not in skip_editor_keys:
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
        self.strategy_combo.setMinimumWidth(280)
        self.strategy_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.strategy_combo.addItems([s['name'] for s in self.strategies])
        tb1_layout.addWidget(self.strategy_combo, stretch=2)

        btn_edit_strat = QPushButton("⚙", self)
        btn_edit_strat.setFixedWidth(30)
        btn_edit_strat.clicked.connect(self.open_strategy_editor)
        tb1_layout.addWidget(btn_edit_strat)

        # 🎯 Hit 命中能力状态展示
        self.lbl_hit_status = QLabel("🎯 Hit: --", self)
        self.lbl_hit_status.setStyleSheet("""
            QLabel {
                background-color: #1e2836;
                color: #00e676;
                border: 1px solid #00b0ff;
                border-radius: 4px;
                padding: 3px 8px;
                font-weight: bold;
                font-size: 12px;
            }
            QLabel:hover {
                background-color: #26384d;
                color: #ffffff;
                border-color: #00e676;
            }
        """)
        self.lbl_hit_status.setToolTip("点击即可快速对全策略进行 Hit 命中测试")
        self.lbl_hit_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_hit_status.mousePressEvent = lambda e: self._test_all_strategies_hit()
        tb1_layout.addWidget(self.lbl_hit_status)

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

        # ── Toolbar 2: Custom Columns & Focus Mode & End Date ──
        tb2_layout = QHBoxLayout()
        tb2_layout.addWidget(QLabel("手动列:", self))
        self.manual_col_edit = QLineEdit(self)
        self.manual_col_edit.setPlaceholderText("自定义列名称")
        self.manual_col_edit.setFixedWidth(120)
        self.manual_col_edit.setToolTip("💡 输入纯列名(如 dff3, ma20, dif, upper)，系统会自动补齐智能匹配且不会带 _d 后缀")
        self.manual_col_edit.returnPressed.connect(self._add_manual_col)
        
        # 自动补全 QCompleter
        self._col_completer_model = QStringListModel(self)
        self._col_completer = QCompleter(self._col_completer_model, self)
        self._col_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._col_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.manual_col_edit.setCompleter(self._col_completer)
        self._update_manual_col_completer()

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
        self.btn_custom_cols_menu = QPushButton("⚙️ 自定义列", self)
        self.custom_cols_menu = QMenu(self)
        self.custom_cols_menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; color: #ffffff; border: 1px solid #37474f; }
            QMenu::item:selected { background-color: #293952; }
        """)
        self.btn_custom_cols_menu.setMenu(self.custom_cols_menu)
        tb2_layout.addWidget(self.btn_custom_cols_menu)

        # 🔥 专注能力极简控件 (放置于截止日期前面，极简宽度占用)
        lbl_focus = QLabel(" 🔥 专注:", self)
        lbl_focus.setStyleSheet("color: #ffca28; font-weight: bold; margin-left: 6px;")
        tb2_layout.addWidget(lbl_focus)

        self.focus_mode_combo = QComboBox(self)
        self.focus_mode_combo.setFixedWidth(125)
        self.focus_mode_combo.addItems([
            "⭐ 当日特异",
            "⚡ 通道企稳",
            "👑 板块共振",
            "🌐 全量大结构"
        ])
        self.focus_mode_combo.setToolTip("🔥 专注能力选择: 切换精选特异/通道企稳/板块龙头或全量模式")
        self.focus_mode_combo.setStyleSheet("""
            QComboBox {
                background-color: #1a237e;
                color: #ffffff;
                font-weight: bold;
                font-size: 11px;
                border: 1px solid #3d5aff;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 15px;
                border-left-width: 0px;
            }
        """)
        self.focus_mode_combo.currentIndexChanged.connect(self._on_focus_mode_changed)
        tb2_layout.addWidget(self.focus_mode_combo)

        # 📅 预处理截止日期选项 (默认关闭，关闭时传递 end=None；勾选后启用 date_edit，当只读模式关闭时生效)
        self.chk_end_date = QCheckBox("📅 截止日期:", self)
        self.chk_end_date.setChecked(False)
        self.chk_end_date.setToolTip("默认关闭(使用最新数据)。勾选打开后可选择指定 end 截止日期，配合取消[只读模式]进行盘前/历史预处理。")
        self.chk_end_date.setStyleSheet("""
            QCheckBox {
                color: #81c784;
                font-weight: bold;
                font-size: 12px;
                margin-left: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox:hover {
                color: #a5d6a7;
            }
        """)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setFixedWidth(110)
        self.date_edit.setEnabled(False)  # 默认禁用，只有勾选 chk_end_date 后方可操作
        self.date_edit.setToolTip("预处理/回溯截止日期。仅在勾选[截止日期]并取消[只读模式]时生效。")
        self.date_edit.setStyleSheet("""
            QDateEdit {
                background-color: #1a1a24;
                color: #00e676;
                border: 1px solid #37474f;
                border-radius: 4px;
                padding: 2px 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QDateEdit:disabled {
                background-color: #12121a;
                color: #5c6bc0;
                border-color: #212130;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #37474f;
            }
            QDateEdit:hover {
                border-color: #6366f1;
            }
            QCalendarWidget QWidget {
                background-color: #1e1e2d;
                color: #e0e0e0;
            }
        """)

        # 联动：勾选 chk_end_date 动态控制 date_edit 的可编辑状态
        self.chk_end_date.toggled.connect(self.date_edit.setEnabled)

        tb2_layout.addWidget(self.chk_end_date)
        tb2_layout.addWidget(self.date_edit)

        tb2_layout.addStretch()

        # 只读模式复选框（默认勾选为只读；取消勾选后点击【强制刷新】方可初始化底层缺失的周期数据）
        self.chk_readonly = QCheckBox("🔒 只读模式", self)
        self.chk_readonly.setChecked(True)
        self.chk_readonly.setToolTip("默认勾选为纯只读模式（不触发底层H5数据写盘与初始化）；\n取消勾选后点击【🔄 强制刷新】可全自动初始化并落盘缺失的周期数据。")
        self.chk_readonly.setStyleSheet("""
            QCheckBox {
                color: #81c784;
                font-weight: bold;
                font-size: 12px;
                margin-right: 12px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox:hover {
                color: #a5d6a7;
            }
        """)
        tb2_layout.addWidget(self.chk_readonly)

        # Secondary Filter Query
        # Secondary Filter Query (Integrated Editable QComboBox with 8 History Entries)
        tb2_layout.addWidget(QLabel("🔍 历史/二次过滤:", self))
        self.filter_edit = QComboBox(self)
        self.filter_edit.setEditable(True)
        self.filter_edit.setFixedWidth(320)
        self.filter_edit.setToolTip("输入二次过滤表达式或点击下拉菜单选择最近8条历史记录")
        if self.filter_edit.lineEdit():
            self.filter_edit.lineEdit().setPlaceholderText("例如: dff > 2.0 and close > 10")
            self.filter_edit.lineEdit().returnPressed.connect(self._apply_secondary_filter_from_edit)
        self.filter_edit.activated.connect(self._on_quick_history_combo_selected)
        self.filter_edit.currentIndexChanged.connect(lambda: self.filter_edit.lineEdit() and self.filter_edit.lineEdit().setCursorPosition(0))
        
        self.filter_edit.setStyleSheet("""
            QComboBox {
                background-color: #161822;
                color: #81d4fa;
                border: 1px solid #37474f;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1a24;
                color: #ffffff;
                selection-background-color: #293952;
                border: 1px solid #37474f;
            }
        """)
        tb2_layout.addWidget(self.filter_edit)

        btn_history = QPushButton("📜 历史管理", self)
        btn_history.clicked.connect(self._open_history_dialog)
        tb2_layout.addWidget(btn_history)

        main_layout.addLayout(tb2_layout)

        # ── Plate/Concept Display Bar ──
        concept_layout = QHBoxLayout()
        self.btn_concept_title = QPushButton("当前概念:", self)
        self.btn_concept_title.setFlat(True)
        self.btn_concept_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_concept_title.setToolTip("📊 点击查看当前筛选结果的完整概念板块统计详情")
        self.btn_concept_title.setStyleSheet("""
            QPushButton {
                font-weight: bold;
                color: #4caf50;
                font-size: 13px;
                background: transparent;
                border: none;
                padding: 0px 4px;
                text-align: left;
            }
            QPushButton:hover {
                color: #81c784;
                text-decoration: underline;
            }
        """)
        self.btn_concept_title.clicked.connect(self.show_concept_detail_window)
        concept_layout.addWidget(self.btn_concept_title)

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
        self.table = BaseATSTableWidget(self)
        self.table.setSortingEnabled(False)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.stock_activated.connect(self.link_stock)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_table_context_menu)
        
        # 绑定表头点击和右键多级排序
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._on_header_context_menu)
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

    def _rebuild_strategy_combo(self):
        if not hasattr(self, 'strategy_combo') or self.strategy_combo is None:
            return
        self.strategy_combo.blockSignals(True)
        try:
            # 1. 抓取当前下拉框中各策略纯名字的 [Hit: N] 后缀映射
            hit_names = {}
            import re
            for i in range(self.strategy_combo.count()):
                t = self.strategy_combo.itemText(i)
                # 清洗前缀和后缀
                raw = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
                raw = re.sub(r'\s*\[Hit:[^\]]+\]$', '', raw)
                hit_names[raw] = t

            current_text = self.strategy_combo.currentText()
            clean_current_text = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', current_text)
            clean_current_text = re.sub(r'\s*\[Hit:[^\]]+\]$', '', clean_current_text)

            self.strategy_combo.clear()
            
            # 2. 根据 recent_strategy_ids 重新组织 strategies 的渲染顺序
            recent_ids = self.ui_state.get('recent_strategy_ids', [])
            valid_strat_ids = {s['id'] for s in self.strategies}
            recent_ids = [rid for rid in recent_ids if rid in valid_strat_ids]
            self.ui_state['recent_strategy_ids'] = recent_ids[:10]
            recent_ids = recent_ids[:10]
            
            recent_strats = []
            other_strats = []
            for rid in recent_ids:
                s = next(x for x in self.strategies if x['id'] == rid)
                recent_strats.append(s)
                
            recent_ids_set = set(recent_ids)
            for s in self.strategies:
                if s['id'] not in recent_ids_set:
                    other_strats.append(s)
                    
            # 3. 拼接并添加 Items
            prefixes = ["❶ ", "❷ ", "❸ ", "❹ ", "❺ ", "❻ ", "❼ ", "❽ ", "❾ ", "❿ "]
            
            # 优先从计算出的 self._last_hit_results 中读取，备选从原本的文本中读取
            hit_results = getattr(self, "_last_hit_results", {})
            single_code_results = getattr(self, "_single_code_hit_results", {})

            def _build_hit_suffix(s_id, raw_name, prev_full=None):
                hit_cnt = None
                if s_id and s_id in hit_results:
                    hit_cnt = hit_results[s_id]
                elif raw_name in hit_results:
                    hit_cnt = hit_results[raw_name]
                elif prev_full:
                    prev_hit = re.search(r'\[Hit:\s*(\d+)', prev_full)
                    if prev_hit:
                        hit_cnt = int(prev_hit.group(1))

                single_hit = None
                if single_code_results:
                    if s_id and s_id in single_code_results:
                        single_hit = single_code_results[s_id]
                    elif raw_name in single_code_results:
                        single_hit = single_code_results[raw_name]

                if hit_cnt is not None and single_hit is not None:
                    hit_tag = "✅命中" if single_hit else "❌未命中"
                    return f" [Hit: {hit_cnt} | {hit_tag}]"
                elif hit_cnt is not None:
                    return f" [Hit: {hit_cnt}]"
                elif single_hit is not None:
                    hit_tag = "✅命中" if single_hit else "❌未命中"
                    return f" [Hit: {hit_tag}]"
                return ""

            for idx, s in enumerate(recent_strats):
                prefix = prefixes[idx] if idx < len(prefixes) else ""
                raw_name = s['name']
                s_id = s.get('id', '')
                prev_full = hit_names.get(raw_name)
                hit_suffix = _build_hit_suffix(s_id, raw_name, prev_full)
                item_text = f"{prefix}{raw_name}{hit_suffix}"
                self.strategy_combo.addItem(item_text, userData=s_id)
                    
            for s in other_strats:
                raw_name = s['name']
                s_id = s.get('id', '')
                prev_full = hit_names.get(raw_name)
                hit_suffix = _build_hit_suffix(s_id, raw_name, prev_full)
                item_text = f"{raw_name}{hit_suffix}"
                self.strategy_combo.addItem(item_text, userData=s_id)
            
            # 4. 恢复之前选中的策略
            matched_idx = -1
            target_id = self.ui_state.get('strategy_id')
            if target_id:
                for i in range(self.strategy_combo.count()):
                    if self.strategy_combo.itemData(i) == target_id:
                        matched_idx = i
                        break
            if matched_idx < 0:
                for i in range(self.strategy_combo.count()):
                    t = self.strategy_combo.itemText(i)
                    t_clean = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
                    t_clean = re.sub(r'\s*\[Hit:[^\]]+\]$', '', t_clean)
                    if t_clean == clean_current_text:
                        matched_idx = i
                        break
            if matched_idx >= 0:
                self.strategy_combo.setCurrentIndex(matched_idx)
            else:
                if self.strategy_combo.count() > 0:
                    self.strategy_combo.setCurrentIndex(0)
        finally:
            self.strategy_combo.blockSignals(False)

    def _apply_state(self):
        # 1. Apply active strategy
        # 先根据最近使用历史重构下拉列表
        self._rebuild_strategy_combo()

        if self.strategies:
            target_id = self.ui_state.get('strategy_id')
            strat = next((s for s in self.strategies if s['id'] == target_id), None)
            if strat:
                import re
                for i in range(self.strategy_combo.count()):
                    t = self.strategy_combo.itemText(i)
                    t_clean = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩]\s*', '', t)
                    t_clean = re.sub(r'\s*\[Hit:[^\]]+\]$', '', t_clean)
                    if t_clean == strat['name']:
                        self.strategy_combo.setCurrentIndex(i)
                        break

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
        if hasattr(self, 'chk_readonly'):
            self.chk_readonly.setChecked(True)  # 只读模式不持久化，默认始终直接处于勾选开启状态

        # 6. Apply secondary filter query
        raw_curr = self.ui_state.get('current_history_query', '')
        label, pure = self._format_filter_item_with_note(raw_curr)
        self._current_history_query = label if label else raw_curr
        self._set_filter_edit_text(self._current_history_query)

        # 7. Apply recent secondary filters with strict deduplication
        raw_recent = self.ui_state.get('recent_secondary_filters', [])
        seen_norm = set()
        cleaned_recent = []
        for q in raw_recent:
            norm = self._normalize_filter_query(q)
            if norm and norm not in seen_norm:
                seen_norm.add(norm)
                cleaned_recent.append(norm)
                if len(cleaned_recent) >= 8:
                    break
        self.recent_secondary_filters = cleaned_recent
        self._rebuild_quick_history_menu()

        # 8. Apply multi-level sort state
        self.sort_level1_col = self.ui_state.get('sort_level1_col', None)
        self.sort_level1_asc = self.ui_state.get('sort_level1_asc', True)
        self.sort_level2_col = self.ui_state.get('sort_level2_col', None)
        self.sort_level2_asc = self.ui_state.get('sort_level2_asc', True)
        self.sort_level3_col = self.ui_state.get('sort_level3_col', None)
        self.sort_level3_asc = self.ui_state.get('sort_level3_asc', True)
        self.sortby_col = self.ui_state.get('sortby_col', None)
        self.sortby_col_ascend = self.ui_state.get('sortby_col_ascend', False)

        # 9. Apply focus mode selection
        if hasattr(self, 'focus_mode_combo') and self.focus_mode_combo is not None:
            focus_idx = self.ui_state.get('focus_mode_index', 3)
            if 0 <= focus_idx < self.focus_mode_combo.count():
                self.focus_mode_combo.blockSignals(True)
                self.focus_mode_combo.setCurrentIndex(focus_idx)
                self.focus_mode_combo.blockSignals(False)

    def _on_focus_mode_changed(self, index):
        if getattr(self, "_initializing", False):
            return
        self._save_state()
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _update_manual_col_completer(self, force_refresh=False):
        if not hasattr(self, "_col_completer_model"):
            return
            
        # 如果已有缓存候选且非强制刷新，直接复用
        if getattr(self, "_cached_completer_candidates", None) and not force_refresh:
            return

        candidates = set()
        
        # 1. 动态确定当前勾选参与周期中的最小周期（优先级: d > 2d > 3d > w > m > 45d > 3M）
        active_periods = []
        if hasattr(self, "period_checkboxes"):
            active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
            
        min_period = active_periods[0] if active_periods else 'd'
        
        # 2. 从选中的最小周期基础数据集 (self.engine._period_dfs[min_period]) 提取原始物理列名
        try:
            if hasattr(self, "engine") and hasattr(self.engine, "_period_dfs"):
                df_min = self.engine._period_dfs.get(min_period)
                if df_min is None or df_min.empty:
                    # 降级尝试已有任意周期的 DF
                    for p_df in self.engine._period_dfs.values():
                        if p_df is not None and not p_df.empty:
                            df_min = p_df
                            break
                            
                if df_min is not None and not df_min.empty:
                    for c in df_min.columns:
                        c_str = str(c).strip()
                        if c_str and c_str not in ("code", "name", "index"):
                            candidates.add(c_str)
        except Exception:
            pass

        # 3. 若引擎尚未加载，从 query_engine_util 别名定义短路兜底
        if not candidates:
            try:
                from query_engine_util import query_engine
                if query_engine and hasattr(query_engine, 'col_map'):
                    for k in query_engine.col_map.keys():
                        if k not in ("code", "name"):
                            candidates.add(k)
            except Exception:
                pass

        if hasattr(self, 'manual_col_pool'):
            candidates.update(self.manual_col_pool)

        sorted_candidates = sorted(list(candidates))
        self._cached_completer_candidates = sorted_candidates
        self._col_completer_model.setStringList(sorted_candidates)

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

        self._update_manual_col_completer()

    def _on_strategy_selected(self):
        if getattr(self, "_initializing", False):
            return
        strat = self._get_current_selected_strategy()
        if strat:
            tip = f"{strat.get('name', '')}\n\n{strat.get('description', '')}"
            self.strategy_combo.setToolTip(tip)
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

        strat_config = self._get_current_selected_strategy()
        if not strat_config:
            return

        # 记录到最近使用的 10 个策略中（保持持久化，但在此处切勿重构列表以防按上下键浏览时列表顺序动态重排破坏键盘焦点）
        strat_id = strat_config['id']
        recent_ids = self.ui_state.get('recent_strategy_ids', [])
        if strat_id in recent_ids:
            recent_ids.remove(strat_id)
        recent_ids.insert(0, strat_id)
        self.ui_state['recent_strategy_ids'] = recent_ids[:10]
        self._save_state(write_to_disk=True)

        if force_reload:
            # 盘中强制刷新：仅清空 top_now 实时行情以强行更新最新盘中数据，持久复用内存中多周期历史特征数据 (_period_dfs)
            self.top_now = None
            self._top_now_cache_ts[0] = 0.0
            if hasattr(self, "_block_cache"):
                self._block_cache.clear()
            self.lbl_status.setText("🔄 盘中强制刷新：正在更新全市场实时行情数据...")
        else:
            # 智能缓存：检查 top_now 缓存是否过期
            if not self._is_cache_valid(self._top_now_cache_ts[0]):
                self.top_now = None
                self._top_now_cache_ts[0] = 0.0
            
            if self.top_now is None:
                self.lbl_status.setText("正在获取基础全市场数据...")
            else:
                is_trade = cct.get_work_time_duration()
                age = int(time.time() - self._top_now_cache_ts[0])
                trade_hint = "交易时段" if is_trade else "非交易时段"
                self.lbl_status.setText(f"⚡ 使用内存缓存 ({trade_hint}，缓存已存在 {age}s)，开始筛选...")

        self.btn_run_filter_worker(strat_config, active_periods, force_reload)

    def _get_effective_end_date(self):
        """
        获取有效的 end 截止日期。
        规则：
        1. 若未勾选 chk_end_date 选项（默认关闭），返回 None（使用最新数据）；
        2. 若处于【只读模式】(chk_readonly 勾选)，返回 None；
        3. 仅当勾选了 chk_end_date 且取消了【只读模式】时：
           - 若选择的日期 >= 最近交易日，返回 None（等效于"使用最新数据"）；
           - 否则返回所选日期的 'YYYY-MM-DD' 格式字符串。

        关键修复: 使用「最近交易日」而非「日历今天」做基准比较，
        确保同一截止日期在不同日历日运行（如 07-31 vs 08-01）
        始终走完全相同的数据加载路径，回测 Hit 结果 100% 可复现。
        """
        if not hasattr(self, "chk_end_date") or not self.chk_end_date.isChecked():
            return None

        if hasattr(self, "chk_readonly") and self.chk_readonly.isChecked():
            return None

        if not hasattr(self, "date_edit"):
            return None

        selected_date_str = self.date_edit.date().toString("yyyy-MM-dd")

        # 使用最近交易日做基准比较（而非日历 today），确保跨日回测可复现
        try:
            last_trade = cct.get_last_trade_date()
            if last_trade is not None:
                # get_last_trade_date 返回的可能是 datetime.date 或 str
                if hasattr(last_trade, 'strftime'):
                    last_trade_str = last_trade.strftime('%Y-%m-%d')
                else:
                    last_trade_str = str(last_trade)[:10]
                # 如果选择的日期 >= 最近交易日，视为"使用最新数据"
                if selected_date_str >= last_trade_str:
                    return None
        except Exception:
            pass

        # 兜底：若无法获取最近交易日，与今天比较
        today_str = cct.get_today()
        if selected_date_str >= today_str:
            return None

        return selected_date_str

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

        allow_auto_init = not self.chk_readonly.isChecked() if hasattr(self, 'chk_readonly') else False
        end_date = self._get_effective_end_date()

        # Run standard QThread worker
        worker = MultiPeriodWorker(
            self.engine, strat_config, active_periods,
            top_now=self.top_now, force_reload=force_reload, allow_auto_init=allow_auto_init,
            period_cache_ts=self._period_cache_ts, top_now_cache_ts=self._top_now_cache_ts,
            end=end_date
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
        if hasattr(self, 'lbl_status') and self.lbl_status is not None:
            self.lbl_status.setText(text)
            QApplication.processEvents()

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
        self._update_hit_status(result_df)

    def _update_hit_status(self, result_df=None):
        if not hasattr(self, "lbl_hit_status") or self.lbl_hit_status is None:
            return
        total_hit = len(result_df) if result_df is not None and not result_df.empty else 0

        # 极速计算 4 种专注能力模式在当前 result_df / _last_flat_df 下的真实 Hit 数量
        flat_target = getattr(self, '_last_flat_df', None)
        if flat_target is None or flat_target.empty:
            flat_target = result_df

        cnt_0, cnt_1, cnt_2, cnt_3 = 0, 0, 0, total_hit
        if flat_target is not None and not flat_target.empty:
            cnt_0 = len(self._apply_focus_mode_filter(flat_target, 0))  # ⭐ 当日特异
            cnt_1 = len(self._apply_focus_mode_filter(flat_target, 1))  # ⚡ 通道企稳
            cnt_2 = len(self._apply_focus_mode_filter(flat_target, 2))  # 👑 板块共振
            cnt_3 = len(flat_target)                                    # 🌐 全量大结构

        # 1. 胶囊框保持与原样一模一样的极简显示 (只显示总 Hit 只数)
        self.lbl_hit_status.setText(f"🎯 Hit: {cnt_3}只")

        # 1.5 实时同步当前选中策略在 self._last_hit_results 及 strategy_combo 下拉框项中的 Hit 命中
        strat = self._get_current_selected_strategy()
        if strat:
            s_id = strat.get('id')
            s_name = strat.get('name')
            if not hasattr(self, '_last_hit_results'):
                self._last_hit_results = {}
            if s_id:
                self._last_hit_results[s_id] = cnt_3
            if s_name:
                self._last_hit_results[s_name] = cnt_3
            if hasattr(self, 'strategy_combo') and self.strategy_combo is not None:
                curr_idx = self.strategy_combo.currentIndex()
                if curr_idx >= 0:
                    import re
                    item_text = self.strategy_combo.itemText(curr_idx)
                    single_code_results = getattr(self, "_single_code_hit_results", {})
                    s_id = strat.get('id', '')
                    s_name = strat.get('name', '')
                    single_hit = single_code_results.get(s_id, single_code_results.get(s_name))
                    if single_hit is not None:
                        hit_tag = "✅命中" if single_hit else "❌未命中"
                        hit_suffix_str = f" [Hit: {cnt_3} | {hit_tag}]"
                    else:
                        hit_suffix_str = f" [Hit: {cnt_3}]"
                    new_text = re.sub(r'\s*\[Hit:[^\]]+\]$', '', item_text) + hit_suffix_str
                    self.strategy_combo.blockSignals(True)
                    self.strategy_combo.setItemText(curr_idx, new_text)
                    self.strategy_combo.blockSignals(False)

        # 2. 同步更新 focus_mode_combo 下拉框选项后面的 Hit 命中显示
        if hasattr(self, "focus_mode_combo") and self.focus_mode_combo is not None:
            old_idx = self.focus_mode_combo.currentIndex()
            self.focus_mode_combo.blockSignals(True)
            self.focus_mode_combo.setItemText(0, f"⭐ 当日特异 [{cnt_0}]")
            self.focus_mode_combo.setItemText(1, f"⚡ 通道企稳 [{cnt_1}]")
            self.focus_mode_combo.setItemText(2, f"👑 板块共振 [{cnt_2}]")
            self.focus_mode_combo.setItemText(3, f"🌐 全量大结构 [{cnt_3}]")

            # 设置悬停对比 ToolTip
            tooltips = [
                f"⭐ 当日特异买卖逻辑 (交集精选顶级特异买点，Hit: {cnt_0} 只)",
                f"⚡ 自动通道 & Fib50 支撑定位 (强企稳，Hit: {cnt_1} 只)",
                f"👑 热点主线与领头羊 (板块共振/带队，Hit: {cnt_2} 只)",
                f"🌐 全量多周期大结构 (全景放行，Hit: {cnt_3} 只)"
            ]
            for i, tt in enumerate(tooltips):
                self.focus_mode_combo.setItemData(i, tt, Qt.ItemDataRole.ToolTipRole)
            self.focus_mode_combo.setCurrentIndex(old_idx)
            self.focus_mode_combo.blockSignals(False)

        # 3. 悬停气泡对比
        tip_lines = [
            f"🎯 策略 Hit 命中测试详情 (全量: {cnt_3} 只)",
            "-" * 38,
            f"  🔥 ⭐ 当日买卖特异: {cnt_0} 只 (高胜率/强确定性)",
            f"  🔥 ⚡ 自动通道企稳: {cnt_1} 只 (Fib50%/下轨支撑)",
            f"  🔥 👑 板块共振龙头: {cnt_2} 只 (热点主线/大哥带队)",
            f"  🔥 🌐 全量多周期大结构: {cnt_3} 只 (全景放行)",
            "-" * 38
        ]
        if hasattr(self.engine, "_period_dfs") and self.engine._period_dfs:
            for p, df in self.engine._period_dfs.items():
                if df is not None and not df.empty:
                    tip_lines.append(f" • {p} 周期基础数据: {len(df)} 只")
        tip_lines.append("\n(点击胶囊框即可快速对全策略及专注模式再次触发 Hit 测试)")
        self.lbl_hit_status.setToolTip("\n".join(tip_lines))

    def _test_all_strategies_hit(self):
        # 1. 检查是否有已有线程运行，防止重入
        from PyQt6.sip import isdeleted
        if hasattr(self, "_hit_worker") and self._hit_worker is not None:
            try:
                if not isdeleted(self._hit_worker) and self._hit_worker.isRunning():
                    logger.info("Previous hit test worker is still running. Ignoring request.")
                    return
            except RuntimeError:
                self._hit_worker = None

        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        if not active_periods:
            QMessageBox.warning(self, "警告", "请至少选择一个参与周期！")
            return

        self.lbl_hit_status.setEnabled(False)  # 暂时禁用以防止高频连续点击
        self.lbl_status.setText("正在准备全策略测试线程...")
        
        end_date = self._get_effective_end_date()
        allow_auto_init = not self.chk_readonly.isChecked() if hasattr(self, 'chk_readonly') else False
        # 2. 启动后台线程
        worker = AllStrategiesHitWorker(
            self.engine, self.strategies, active_periods,
            top_now=self.top_now, period_cache_ts=self._period_cache_ts, top_now_cache_ts=self._top_now_cache_ts,
            end=end_date, allow_auto_init=allow_auto_init
        )
        self._hit_worker = worker
        _active_workers.add(worker)

        worker.progress.connect(self.update_status)
        worker.finished.connect(self._on_hit_worker_finished)
        worker.error.connect(self._on_hit_worker_error)

        def cleanup():
            _active_workers.discard(worker)
            if getattr(self, "_hit_worker", None) == worker:
                self._hit_worker = None
            self.lbl_hit_status.setEnabled(True)
            try:
                if not isdeleted(worker):
                    worker.deleteLater()
            except RuntimeError:
                pass

        worker.finished.connect(cleanup)
        worker.error.connect(cleanup)
        worker.start()

    def _on_hit_worker_finished(self, results):
        if self._hit_worker is not None:
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(self._hit_worker):
                    # 同步 top_now 缓存
                    self.top_now = self._hit_worker.top_now
            except RuntimeError:
                pass

        # 缓存计算结果，注意保存 ID 和清洗后的名称后缀
        import re
        self._last_hit_results = {}
        for key, hit_cnt in results.items():
            self._last_hit_results[str(key)] = hit_cnt
            clean_name = re.sub(r'^[❶❷❸❹❺❻❼❽❾❿①②③④⑤⑥⑦⑧⑨⑩\d\s\.\-\[\]]+', '', str(key))
            clean_name = re.sub(r'\s*\[Hit:\s*\d+\]$', '', clean_name)
            self._last_hit_results[clean_name] = hit_cnt

        # 统一使用 _rebuild_strategy_combo 重构下拉列表，避免前置序号丢失！
        self._rebuild_strategy_combo()

        self.lbl_status.setText("✅ 全量策略 Hit 命中率测试完成！")

        # 手动同步刷新 lbl_hit_status
        strat_name = self.strategy_combo.currentText()
        match = re.search(r'\[Hit:\s*(\d+)\]$', strat_name)
        if match:
            curr_hit = int(match.group(1))
            self.lbl_hit_status.setText(f"🎯 Hit: {curr_hit}只")

    def _on_hit_worker_error(self, err_msg):
        self.lbl_status.setText(f"❌ 全量策略 Hit 测试失败: {err_msg}")
        QMessageBox.critical(self, "错误", f"全策略 Hit 命中率测试出错: {err_msg}")

        # Automatically update Dragon Monitor if it is currently open and visible
        if hasattr(self, "dragon_monitor_dialog") and self.dragon_monitor_dialog is not None:
            from PyQt6.sip import isdeleted
            try:
                if not isdeleted(self.dragon_monitor_dialog) and self.dragon_monitor_dialog.isVisible():
                    sh_pct = 0.0
                    if self.top_now is not None and not self.top_now.empty:
                        if 'ratio' in self.top_now.columns:
                            sh_pct = float(self.top_now['ratio'].mean())
                        elif 'percent' in self.top_now.columns:
                            sh_pct = float(self.top_now['percent'].mean())
                        elif 'sh000001' in self.top_now.index:
                            sh_pct = float(self.top_now.loc['sh000001'].get('percent', 0.0))
                        elif '000001' in self.top_now.index and 'sh' in str(self.top_now.loc['000001'].get('code', '')):
                            sh_pct = float(self.top_now.loc['000001'].get('percent', 0.0))
                        self.dragon_monitor_dialog.update_data(self.top_now, sh_pct)
            except Exception as e:
                logger.warning(f"Failed to auto-update dragon monitor: {e}")

    def refresh_realtime_ui(self):
        """Called externally to re-run filtering and update all charts/displays."""
        self.run_filter(force_reload=False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
        else:
            super().keyPressEvent(event)

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
        self._save_state("FORCE_WRITE")

        # Clear global _dialog_instance reference
        global _dialog_instance
        _dialog_instance = None

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

    def broadcast_code_link(self, code: str, bring_tdx_to_top: bool = False):
        """全系统统一标准的 StockSender 广播引擎：支持 TDX/THS 的零卡顿高可靠联动"""
        if not code:
            return
        code_clean = "".join(x for x in str(code) if x.isdigit()).zfill(6)
        if not code_clean:
            return

        # 优先使用项目标准的 StockSender 发送通道 (基于句柄消息投递与进程 Proxy 防卡死)
        if hasattr(self, 'sender') and self.sender is not None:
            try:
                self.sender.send(code_clean)
                return
            except Exception as e:
                print(f"[MultiPeriodDialog] Standard StockSender send failed: {e}")

        # 兜底静默剪贴板注入
        try:
            cb = QApplication.clipboard()
            if cb:
                cb.setText(code_clean)
        except Exception:
            pass

    def locate_stock_in_table(self, code: str, auto_popup: bool = False):
        """自动在表格中高亮定位并滚动对齐指定股票代码 (点击 Toast 打开详情窗口，绝不触发诊断窗口)"""
        if not code or not hasattr(self, "table") or self.table is None:
            return

        target_code = str(code).strip()
        found = False
        name_val = target_code
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text().strip() == target_code:
                self.table.setCurrentCell(row, 0)
                self.table.scrollToItem(item, QTableWidget.ScrollHint.PositionAtCenter)
                n_item = self.table.item(row, 1)
                if n_item:
                    name_val = n_item.text().strip()
                self.lbl_status.setText(f"🎯 已自动定位高亮联动标的: {target_code}")
                found = True
                break

        # 自动触发秒级通达信 (TDX) 行情联动
        self.broadcast_code_link(target_code)

        if not found:
            self.lbl_status.setText(f"⚠️ 当前表格结果中未包含标的 [{target_code}]")

        # 仅在用户手动点击 Toast 提醒卡片时 (auto_popup=True) 打开【详情窗口】，绝对不联动诊断窗口
        if auto_popup:
            if hasattr(self, 'isMinimized') and self.isMinimized():
                self.showNormal()
            if hasattr(self, 'isHidden') and self.isHidden():
                self.show()
            self.show()
            self.raise_()
            self.activateWindow()

            if found:
                try:
                    if hasattr(self, "_show_stock_category_dialog"):
                        self._show_stock_category_dialog(target_code, name_val)
                except Exception:
                    pass

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
        
        # 针对带明确周期后缀的自定义列 (如 strong_structure_d, red_2d)
        for p in active_periods:
            if col_name.endswith(f"_{p}"):
                return [p]

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
                self._current_displayed_df = None
                self._concept_index = None
                self.update_concept_ranking(None)
                return

            self._update_manual_col_completer(force_refresh=True)

            # Apply focus mode & secondary filtering
            filtered_df = flat_df
            focus_idx = self.focus_mode_combo.currentIndex() if hasattr(self, "focus_mode_combo") else 3
            if focus_idx != 3:
                filtered_df = self._apply_focus_mode_filter(filtered_df, focus_idx)

            if self._current_history_query:
                filtered_df = self._apply_secondary_filter(filtered_df, self._current_history_query)

            self._current_displayed_df = filtered_df
            self._concept_index = None


            # 当模式为 ⭐ 当日特异 (focus_idx == 0) 且筛选出结果时，自动推送 Top 1 黄金特异黑马弹窗与语音
            if focus_idx == 0 and filtered_df is not None and not filtered_df.empty:
                try:
                    top_row = filtered_df.iloc[0]
                    code_val = str(top_row.name) if hasattr(top_row, 'name') else str(top_row.get('code', ''))
                    name_val = str(top_row.get('name', '特异精选'))
                    from ats.alert_notifier import AlertNotifier
                    AlertNotifier().notify_special_signal(
                        code_val, name_val,
                        reason="多周期自动通道企稳 / 阶梯抬升交集特异买点",
                        score=92.0,
                        parent=self
                    )
                except Exception as ex_alert:
                    logger.warning(f"Focus alert trigger failed: {ex_alert}")

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
                    safe_total = max(final.get('total', 0), 1)
                    self.lbl_final_stats.setText(
                        f"【最终 ({mode_str})】 共 {len(filtered_df)} / 二次前 {len(df)} 只 ({len(filtered_df)/safe_total*100:.3f}%)"
                    )

            if self._current_history_query:
                if self._history_filter_error:
                    self.lbl_status.setText(f"⚠️ {self._history_filter_error} (二次前 {len(df)} 只，耗时 {elapsed:.1f}s)")
                else:
                    self.lbl_status.setText(f"完成，共筛选出 {len(filtered_df)} 只 (二次前 {len(df)} 只，耗时 {elapsed:.1f}s)")
            else:
                self.lbl_status.setText(f"完成，共筛选出 {len(filtered_df)} 只标的。(耗时 {elapsed:.1f}s)")

            # 触发应用内与系统托盘 Toast 提醒卡片
            if len(filtered_df) > 0:
                try:
                    first_row = filtered_df.iloc[0]
                    top_code = str(first_row.get('code', '') if 'code' in first_row else filtered_df.index[0]).strip()
                    top_name = str(first_row.get('name', top_code) if 'name' in first_row else top_code).strip()
                    pct_val = 0.0
                    try:
                        pct_val = float(first_row.get('percent', 0.0))
                    except:
                        pass
                    
                    from ats.alert_notifier import AlertNotifier
                    notifier = AlertNotifier()
                    if notifier:
                        notifier.notify(
                            title=f"🎯 多周期策略选股完成 (共命中 {len(filtered_df)} 只)",
                            message=f"排头标的: {top_code} {top_name} ({pct_val:+.2f}%)",
                            code=top_code,
                            score=95.0,
                            level="GOLD"
                        )
                except Exception as e:
                    logger.warning(f"MultiPeriod notification trigger failed: {e}")

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
            self._current_table_columns = columns

            # 向前兼容：若历史保存的排序参数为物理列索引 (int)，则在数据首次就绪后智能翻译并重写为当前的英文列名 (str)
            cols = self._current_table_columns
            if hasattr(self, "sort_level1_col") and isinstance(self.sort_level1_col, int) and 0 <= self.sort_level1_col < len(cols):
                self.sort_level1_col = cols[self.sort_level1_col]
            if hasattr(self, "sort_level2_col") and isinstance(self.sort_level2_col, int) and 0 <= self.sort_level2_col < len(cols):
                self.sort_level2_col = cols[self.sort_level2_col]
            if hasattr(self, "sort_level3_col") and isinstance(self.sort_level3_col, int) and 0 <= self.sort_level3_col < len(cols):
                self.sort_level3_col = cols[self.sort_level3_col]
            if hasattr(self, "sortby_col") and isinstance(self.sortby_col, int) and 0 <= self.sortby_col < len(cols):
                self.sortby_col = cols[self.sortby_col]
            
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
            for col_i, col in enumerate(columns):
                header_text = headers.get(col, col)
                h_item = QTableWidgetItem(header_text)
                h_item.setData(Qt.ItemDataRole.UserRole, header_text)
                h_item.setToolTip(col)
                self.table.setHorizontalHeaderItem(col_i, h_item)

            try:
                from global_favorites import GlobalFavoriteManager
                fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            except Exception:
                fav_stocks = set()

            custom_disp_periods = {}
            for c in active_customs:
                custom_disp_periods[c] = self._get_display_periods_for_custom_col(c, active_periods, filtered_df)

            self.table.setRowCount(len(filtered_df))
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

                is_fav = str(code).strip().zfill(6) in fav_stocks
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
                p_item.setData(Qt.ItemDataRole.UserRole, price)
                self.table.setItem(idx, 2, p_item)

                pct_item = NumericTableWidgetItem(f"{percent:.2f}")
                pct_item.setData(Qt.ItemDataRole.UserRole, percent)
                if percent > 0:
                    pct_item.setForeground(QBrush(QColor("#ff4444")))
                elif percent < 0:
                    pct_item.setForeground(QBrush(QColor("#33cc5a")))
                self.table.setItem(idx, 3, pct_item)

                v_item = NumericTableWidgetItem(f"{vol:.0f}" if vol > 1000 else f"{vol:.2f}")
                v_item.setData(Qt.ItemDataRole.UserRole, vol)
                self.table.setItem(idx, 4, v_item)

                r_item = NumericTableWidgetItem(f"{ratio:.2f}")
                r_item.setData(Qt.ItemDataRole.UserRole, ratio)
                self.table.setItem(idx, 5, r_item)

                c_idx = 6
                for c in active_customs:
                    disp_periods = custom_disp_periods[c]
                    for p in disp_periods:
                        val = '--'
                        col_name = f"{c}_{p}"
                        raw_val = None
                        if col_name in filtered_df.columns:
                            raw_val = row.get(col_name)
                        elif c in filtered_df.columns:
                            raw_val = row.get(c)

                        if raw_val is not None and pd.notna(raw_val):
                            if isinstance(raw_val, (int, float)):
                                val = f"{raw_val:.2f}" if isinstance(raw_val, float) else str(raw_val)
                            else:
                                val = str(raw_val)
                        
                        if val != '--':
                            item = NumericTableWidgetItem(val)
                            item.setData(Qt.ItemDataRole.UserRole, raw_val)
                        else:
                            item = QTableWidgetItem(val)
                            item.setData(Qt.ItemDataRole.UserRole, -999999.0)
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

            self.table.setSortingEnabled(False)
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
                    w = 50
                elif col == "volume":
                    w = 55
                elif col == "ratio":
                    w = 45
                elif col.startswith("pass_"):
                    w = 45
                else:
                    # 自定义指标默认极窄紧凑宽度 48px
                    w = 48
                default_widths[idx] = w
            
            self.table.setup_persistence("multi_period_table", default_widths=default_widths)
            
            # 当动态新增/减少列导致列数变化时，自动强制重置 setColumnWidth 并更新 _base_widths
            if not getattr(self.table, "_first_width_applied", False) or len(getattr(self.table, "_base_widths", [])) != len(columns):
                self.table._first_width_applied = True
                for idx, w in default_widths.items():
                    self.table.setColumnWidth(idx, w)
            
            # Read back real column widths into _base_widths cache
            base_widths = []
            for i in range(self.table.columnCount()):
                w = self.table.columnWidth(i)
                base_widths.append(w if w > 0 else default_widths.get(i, 48))
            self.table._base_widths = base_widths

            # Automatically stretch columns to utilize viewport width
            self._adjust_column_widths()

            # ── 记录刷新前的垂直滚动位置，用于恢复视口位置 ──
            pre_sort_scroll_val = self.table.verticalScrollBar().value()

            self._update_header_labels()
            self._perform_multi_level_sort()
            self.update_concept_ranking(filtered_df)

            # ── 恢复选中行并确保滚动到可见区域 ──
            if selected_code:
                # 排序完成后，重新定位选中 code 的行并滚动到可见区域
                for r in range(self.table.rowCount()):
                    c_item = self.table.item(r, 0)
                    if c_item and c_item.text().strip() == selected_code:
                        self.table.setCurrentCell(r, 0)
                        self._last_selected_code = selected_code
                        self.table.scrollToItem(
                            self.table.item(r, 0),
                            QAbstractItemView.ScrollHint.PositionAtCenter
                        )
                        break
            else:
                # 无选中行时：恢复刷新前的滚动条位置，避免跑到底部
                self.table.verticalScrollBar().setValue(pre_sort_scroll_val)
        except Exception as ex:
            import traceback
            err_stack = traceback.format_exc()
            logger.error(f"[MultiPeriodDialog] Crashed in _show_results: {ex}\n{err_stack}")
        finally:
            self._is_updating = False
            self.table._is_updating = False

    def _on_header_clicked(self, logical_index):
        cols = getattr(self, "_current_table_columns", [])
        if not cols or logical_index >= len(cols):
            return
        col_name = cols[logical_index]

        # 1. 检查当前是否点击了多级排序列之一 (L1-L3)
        is_multi_clicked = False
        if col_name == getattr(self, "sort_level1_col", None):
            self.sort_level1_asc = not self.sort_level1_asc
            is_multi_clicked = True
        elif col_name == getattr(self, "sort_level2_col", None):
            self.sort_level2_asc = not self.sort_level2_asc
            is_multi_clicked = True
        elif col_name == getattr(self, "sort_level3_col", None):
            self.sort_level3_asc = not self.sort_level3_asc
            is_multi_clicked = True
            
        if is_multi_clicked:
            self._update_header_labels()
            self._perform_multi_level_sort()
            self._save_state()
            # 点击排序后自动滚到顶部
            self.table.scrollToTop()
            return
            
        # 2. 如果当前有 L1 主排序，点击全新列时，设为临时从/次排序后缀（保持主排序不动！）
        if getattr(self, "sort_level1_col", None) is not None:
            if getattr(self, "sortby_col", None) == col_name:
                self.sortby_col_ascend = not self.sortby_col_ascend
            else:
                self.sortby_col = col_name
                self.sortby_col_ascend = False
        else:
            # 一键自动解除所有多级排序，切回单列排序
            self.sort_level1_col = None
            self.sort_level2_col = None
            self.sort_level3_col = None
            if getattr(self, "sortby_col", None) == col_name:
                self.sortby_col_ascend = not self.sortby_col_ascend
            else:
                self.sortby_col = col_name
                self.sortby_col_ascend = False
            
        self._update_header_labels()
        self._perform_multi_level_sort()
        self._save_state()
        # 点击排序后自动滚到顶部
        self.table.scrollToTop()

    def _on_header_context_menu(self, pos):
        header = self.table.horizontalHeader()
        logical_index = header.logicalIndexAt(pos)
        if logical_index < 0:
            return
            
        cols = getattr(self, "_current_table_columns", [])
        if not cols or logical_index >= len(cols):
            return
        col_name = cols[logical_index]
            
        header_item = self.table.horizontalHeaderItem(logical_index)
        raw_col_name = header_item.text() if header_item else f"第{logical_index+1}列"
        for prefix in ["🔴[主] ", "🟡[从] ", "🟢[次] ", "↓ ", "↑ "]:
            raw_col_name = raw_col_name.replace(prefix, "")
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; border: 1px solid #2e2e36; color: #e2e2e5; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #2c2c35; color: #ffffff; }
        """)
        
        action_l1 = QAction(f"🔴 设为 【主排序】 ({raw_col_name})", self)
        action_l2 = QAction(f"🟡 设为 【从排序】 ({raw_col_name})", self)
        action_l3 = QAction(f"🟢 设为 【次排序】 ({raw_col_name})", self)
        
        menu.addAction(action_l1)
        menu.addAction(action_l2)
        menu.addAction(action_l3)
        menu.addSeparator()
        
        action_clear_col = QAction("❌ 取消此列的排序设置", self)
        action_clear_all = QAction("🚫 清空所有多级排序", self)
        menu.addAction(action_clear_col)
        menu.addAction(action_clear_all)
        
        global_pos = header.mapToGlobal(pos)
        selected_action = menu.exec(global_pos)
        if not selected_action:
            return
            
        if selected_action == action_l1:
            self.sort_level1_col = col_name
            self.sort_level1_asc = True
        elif selected_action == action_l2:
            self.sort_level2_col = col_name
            self.sort_level2_asc = True
        elif selected_action == action_l3:
            self.sort_level3_col = col_name
            self.sort_level3_asc = True
        elif selected_action == action_clear_col:
            if getattr(self, "sort_level1_col", None) == col_name: self.sort_level1_col = None
            if getattr(self, "sort_level2_col", None) == col_name: self.sort_level2_col = None
            if getattr(self, "sort_level3_col", None) == col_name: self.sort_level3_col = None
            if getattr(self, "sortby_col", None) == col_name: self.sortby_col = None
        elif selected_action == action_clear_all:
            self.sort_level1_col = None
            self.sort_level2_col = None
            self.sort_level3_col = None
            self.sortby_col = None
            self.sortby_col_ascend = False
            
        self._update_header_labels()
        self._perform_multi_level_sort()
        self._save_state()
        # 右键菜单设置排序后也自动滚到顶部
        self.table.scrollToTop()

    def _update_header_labels(self):
        col_count = self.table.columnCount()
        def get_col_idx_by_name(val):
            if val is None:
                return None
            if isinstance(val, int):
                return val if 0 <= val < col_count else None
            if isinstance(val, str):
                cols = getattr(self, "_current_table_columns", [])
                if val in cols:
                    return cols.index(val)
            return None

        bound_cols = set()
        l1 = get_col_idx_by_name(getattr(self, "sort_level1_col", None))
        l2 = get_col_idx_by_name(getattr(self, "sort_level2_col", None))
        l3 = get_col_idx_by_name(getattr(self, "sort_level3_col", None))
        sb = get_col_idx_by_name(getattr(self, "sortby_col", None))
        sb_asc = getattr(self, "sortby_col_ascend", False)
        
        if l1 is not None: bound_cols.add(l1)
        if l2 is not None: bound_cols.add(l2)
        if l3 is not None: bound_cols.add(l3)
        
        for col_idx in range(self.table.columnCount()):
            item = self.table.horizontalHeaderItem(col_idx)
            if not item:
                continue
                
            clean_text = item.data(Qt.ItemDataRole.UserRole)
            if not clean_text:
                clean_text = item.text()
                for prefix in ["🔴[主]", "🟡[从]", "🟢[次]", "↓", "↑", "[主]", "[从]", "[次]"]:
                    clean_text = clean_text.replace(prefix, "")
                clean_text = clean_text.strip()
                item.setData(Qt.ItemDataRole.UserRole, clean_text)
                
            text = clean_text
            prefix = ""
            asc = True
            is_sorted = False
            
            if l1 == col_idx:
                prefix = "🔴[主] "
                asc = getattr(self, "sort_level1_asc", True)
                is_sorted = True
            elif l2 == col_idx:
                prefix = "🟡[从] "
                asc = getattr(self, "sort_level2_asc", True)
                is_sorted = True
            elif l3 == col_idx:
                prefix = "🟢[次] "
                asc = getattr(self, "sort_level3_asc", True)
                is_sorted = True
                
            if l1 is not None and col_idx not in bound_cols:
                if sb == col_idx:
                    cnt = len(bound_cols)
                    if cnt == 1:
                        prefix = "🟡[从] "
                    elif cnt >= 2:
                        prefix = "🟢[次] "
                    asc = sb_asc
                    is_sorted = True
            elif l1 is None:
                if sb == col_idx:
                    asc = sb_asc
                    is_sorted = True
                    
            if is_sorted:
                arrow = "↑ " if asc else "↓ "
                item.setText(f"{arrow}{prefix}{text}")
            else:
                item.setText(text)

    def _perform_multi_level_sort(self):
        row_count = self.table.rowCount()
        col_count = self.table.columnCount()
        if row_count <= 1 or col_count == 0:
            return

        def get_col_idx_by_name(val):
            if val is None:
                return None
            if isinstance(val, int):
                return val if 0 <= val < col_count else None
            if isinstance(val, str):
                cols = getattr(self, "_current_table_columns", [])
                if val in cols:
                    return cols.index(val)
            return None

        bound_cols = set()
        active_levels = []

        l1 = get_col_idx_by_name(getattr(self, "sort_level1_col", None))
        l2 = get_col_idx_by_name(getattr(self, "sort_level2_col", None))
        l3 = get_col_idx_by_name(getattr(self, "sort_level3_col", None))
        sb = get_col_idx_by_name(getattr(self, "sortby_col", None))
        sb_asc = getattr(self, "sortby_col_ascend", False)

        if l1 is not None:
            active_levels.append((l1, not getattr(self, "sort_level1_asc", True)))
            bound_cols.add(l1)
        if l2 is not None:
            active_levels.append((l2, not getattr(self, "sort_level2_asc", True)))
            bound_cols.add(l2)
        if l3 is not None:
            active_levels.append((l3, not getattr(self, "sort_level3_asc", True)))
            bound_cols.add(l3)

        # 100% 对齐 bidding_racing_panel.py 中的多级稳定级联排序算法
        # 构建从低到高的层级列表 sort_levels: [最底层 (sb 临时列), L3 (次), L2 (从), L1 (主)]
        sort_levels = []
        
        if l1 is None and l2 is None and l3 is None and sb is None:
            # 兜底默认按涨幅% (第 3 列) 降序排列
            sb = 3
            sb_asc = False
            
        if sb is not None and sb not in bound_cols:
            sort_levels.append((sb, not sb_asc))
            
        if l3 is not None:
            sort_levels.append((l3, not getattr(self, "sort_level3_asc", True)))
        if l2 is not None:
            sort_levels.append((l2, not getattr(self, "sort_level2_asc", True)))
        if l1 is not None:
            sort_levels.append((l1, not getattr(self, "sort_level1_asc", True)))

        # 备份每一行的单元格 item 并根据多级 key 稳定排序
        rows_data = []
        for r in range(row_count):
            items = [self.table.takeItem(r, c) for c in range(col_count)]
            rows_data.append((r, items))
            
        def get_val_for_sort(items, col_idx, is_descending):
            if col_idx >= len(items) or items[col_idx] is None:
                return -999999.0 if is_descending else 999999.0
            
            item = items[col_idx]
            raw = item.data(Qt.ItemDataRole.UserRole)
            if raw is not None and isinstance(raw, (int, float)):
                return float(raw)

            txt = item.text().strip()
            if not txt or txt == '--':
                return -999999.0 if is_descending else 999999.0
            txt_clean = txt.replace('%', '').replace('+', '').replace('★ ', '')
            try:
                return float(txt_clean)
            except ValueError:
                return txt_clean.lower()
                
        # 1. 逐级依次对数据执行稳定排序 (Python sort 是 stable sort，倒序依次执行可保证高层级绝对覆盖并保留次层级相对位置)
        for col_idx, is_descending in sort_levels:
            try:
                rows_data.sort(key=lambda pair: get_val_for_sort(pair[1], col_idx, is_descending), reverse=is_descending)
            except TypeError:
                rows_data.sort(key=lambda pair: str(get_val_for_sort(pair[1], col_idx, is_descending)), reverse=is_descending)

        # 2. 100% 对齐竞价赛马板块最顶层：重点关注★ 优先级置顶排序 (稳定排序)
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            def prio_key(pair):
                items = pair[1]
                code = str(items[0].text()).strip().zfill(6) if items and items[0] else ""
                return 1 if code in fav_stocks else 0
            rows_data.sort(key=prio_key, reverse=True)
        except Exception:
            pass
            
        self.table.setSortingEnabled(False)
        # 回写前记录当前滚动位置，防止 takeItem/setItem 序列触发 Qt 自动滚到最后一行
        _scroll_bar = self.table.verticalScrollBar()
        _saved_scroll = _scroll_bar.value()
        for new_r, (old_r, items) in enumerate(rows_data):
            for c_idx, item in enumerate(items):
                if item:
                    self.table.setItem(new_r, c_idx, item)
        # 恢复滚动位置（调用者在此之后可按需再次覆盖）
        _scroll_bar.setValue(_saved_scroll)
        self.table.setSortingEnabled(False)

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
                    renamed_dict = {c: (c if c.endswith(f"_{period}") else f"{c}_{period}") for c in cols_to_join}
                    df_p_sub = df_p[cols_to_join].rename(columns=renamed_dict)
                    df_p_sub = df_p_sub.loc[:, ~df_p_sub.columns.duplicated(keep='first')]
                    df_p_sub = df_p_sub[~df_p_sub.index.duplicated(keep='first')]
                    
                    overlap_cols = [col for col in df_p_sub.columns if col in flat_df.columns]
                    if overlap_cols:
                        flat_df = flat_df.drop(columns=overlap_cols, errors='ignore')
                    
                    flat_df = flat_df.join(df_p_sub, how='left')
                    
        flat_df.index.name = 'code'
        return flat_df

    def _suffix_query(self, expr, period_suffix):
        if not expr:
            return ""
        from query_engine_util import query_engine
        if query_engine:
            expr = query_engine._preprocess_query(expr)

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

    @staticmethod
    def _extract_real_query(query: str) -> str:
        """对齐竞价面板：拆分'备注 (逻辑)'格式(来自 UI 组合框显示)，优先提取核心逻辑以防 NameError"""
        if not query or not isinstance(query, str):
            return ""
        q = query.strip()
        if '(' in q and q.endswith(')'):
            m = re.match(r'^(.*?)\s*\((.*)\)$', q)
            if m:
                p1, p2 = m.groups()
                # 判定为 UI 标签格式：左侧含中文/破折号，右侧含逻辑符
                if re.search(r'[\u4e00-\u9fa5]|--', p1) and any(op in p2.lower() for op in ['>', '<', '=', '&', '|', 'and', 'or']):
                    return p2.strip()
        return q

    @staticmethod
    def _get_note_for_query(raw_query: str) -> str:
        """从 SEARCH_HISTORY_FILE 中搜索匹配 query 的 note 备注"""
        pure_q = MultiPeriodDialog._extract_real_query(raw_query)
        if not pure_q:
            return ""
        norm_pure = MultiPeriodDialog._normalize_filter_query(pure_q)
        try:
            from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
            if os.path.exists(SEARCH_HISTORY_FILE):
                with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for grp, items in data.items():
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    item_q = item.get("query", "").strip()
                                    pure_item = MultiPeriodDialog._extract_real_query(item_q)
                                    if MultiPeriodDialog._normalize_filter_query(pure_item) == norm_pure:
                                        note = item.get("note", "").strip()
                                        if note:
                                            return note
        except Exception:
            pass
        return ""

    @staticmethod
    def _format_filter_item_with_note(expr: str) -> tuple:
        """对齐竞价面板：格式化显示标签，返回 (display_label, pure_query)"""
        pure_q = MultiPeriodDialog._extract_real_query(expr)
        if not pure_q:
            return "", ""
        
        note = ""
        if '(' in expr and expr.endswith(')'):
            m = re.match(r'^(.*?)\s*\((.*)\)$', expr.strip())
            if m:
                p1, p2 = m.groups()
                if re.search(r'[\u4e00-\u9fa5]|--', p1) and any(op in p2.lower() for op in ['>', '<', '=', '&', '|', 'and', 'or']):
                    note = p1.strip()
        
        if not note:
            note = MultiPeriodDialog._get_note_for_query(pure_q)

        label = f"{note} ({pure_q})" if note else pure_q
        return label, pure_q

    def _apply_secondary_filter(self, df, query_expr):
        query_expr = self._extract_real_query(query_expr)
        if not query_expr or df is None or df.empty:
            self._history_filter_error = None
            return df
        
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        target_period = 'd' if 'd' in active_periods else (active_periods[0] if active_periods else 'd')
        
        converted_query = self._suffix_query(query_expr, target_period)
        
        from query_engine_util import query_engine
        try:
            if query_engine:
                filtered_df = query_engine.execute(df, converted_query)
            else:
                filtered_df = df.query(converted_query)
            self._history_filter_error = None
            return filtered_df
        except Exception as e1:
            try:
                if query_engine:
                    filtered_df = query_engine.execute(df, query_expr)
                else:
                    filtered_df = df.query(query_expr)
                self._history_filter_error = None
                return filtered_df
            except Exception as e2:
                self._history_filter_error = f"过滤语法错误: {e2}"
                return df

    @staticmethod
    def _normalize_filter_query(query):
        if not query:
            return ""
        return " ".join(str(query).strip().split())

    def _set_filter_edit_text(self, text):
        if not hasattr(self, "filter_edit") or not isinstance(self.filter_edit, QComboBox):
            return
        label, pure = self._format_filter_item_with_note(text)
        display_text = label if label else text
        self.filter_edit.blockSignals(True)
        self.filter_edit.setCurrentText(display_text)
        line_edit = self.filter_edit.lineEdit()
        if line_edit:
            line_edit.setCursorPosition(0)
        self.filter_edit.blockSignals(False)

    def _rebuild_quick_history_menu(self):
        if not hasattr(self, "filter_edit") or not isinstance(self.filter_edit, QComboBox):
            return
        
        self.filter_edit.blockSignals(True)
        curr_text = self.filter_edit.currentText().strip()
        self.filter_edit.clear()

        recent = getattr(self, "recent_secondary_filters", [])
        seen_norm = set()
        unique_items = []
        for expr in recent:
            pure_q = self._extract_real_query(expr)
            norm = self._normalize_filter_query(pure_q)
            if norm and norm not in seen_norm:
                seen_norm.add(norm)
                label, pure = self._format_filter_item_with_note(expr)
                if label and pure:
                    unique_items.append((label, pure))
                    if len(unique_items) >= 8:
                        break

        for label, pure in unique_items:
            self.filter_edit.addItem(label, userData=pure)

        if curr_text:
            self._set_filter_edit_text(curr_text)
        elif getattr(self, "_current_history_query", ""):
            self._set_filter_edit_text(self._current_history_query)
        else:
            self.filter_edit.setCurrentIndex(-1)
            self._set_filter_edit_text("")

        self.filter_edit.blockSignals(False)

    def _record_secondary_filter_history(self, query):
        pure_q = self._extract_real_query(query)
        norm_query = self._normalize_filter_query(pure_q)
        if not norm_query:
            return

        label, pure = self._format_filter_item_with_note(query)
        record_text = label if label else query

        if not hasattr(self, "recent_secondary_filters"):
            self.recent_secondary_filters = []

        # Deduplicate strictly based on normalized pure query comparison
        self.recent_secondary_filters = [
            q for q in self.recent_secondary_filters 
            if self._normalize_filter_query(self._extract_real_query(q)) != norm_query
        ]

        self.recent_secondary_filters.insert(0, record_text)
        self.recent_secondary_filters = self.recent_secondary_filters[:8]  # 保持 8 个
        self._save_state()
        self._rebuild_quick_history_menu()

    def _on_quick_history_combo_selected(self, index):
        pure_query = self.filter_edit.itemData(index)
        display_text = self.filter_edit.itemText(index).strip()
        if not pure_query:
            pure_query = self._extract_real_query(display_text)
        if display_text:
            self._current_history_query = display_text
            self._set_filter_edit_text(display_text)
            self._record_secondary_filter_history(display_text)
            if self.last_result_df is not None:
                self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _clear_quick_history(self):
        self.recent_secondary_filters = []
        self._save_state()
        self._rebuild_quick_history_menu()

    def _apply_secondary_filter_from_edit(self):
        query = self.filter_edit.currentText().strip()
        label, pure_q = self._format_filter_item_with_note(query)
        display_text = label if label else query
        self._current_history_query = display_text
        self._set_filter_edit_text(display_text)
        self._record_secondary_filter_history(display_text)
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

    def _clear_secondary_filter(self):
        self._current_history_query = ""
        self._history_filter_error = None
        self._set_filter_edit_text("")
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
            self._show_stock_category_dialog(code, name)

    def _show_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        code_item = self.table.item(row, 0)
        name_item = self.table.item(row, 1)
        if not code_item:
            return
        code = code_item.text().strip()
        name = name_item.text().strip() if name_item else code
        if name.startswith("★ "):
            name = name[2:]

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1a1a24; color: #ffffff; border: 1px solid #37474f; }
            QMenu::item:selected { background-color: #293952; }
        """)

        act_cat = menu.addAction("🏷️ 查看板块行业详情")
        act_cat.triggered.connect(lambda: self._show_stock_category_dialog(code, name))

        act_diag = menu.addAction("🔍 诊断所选个股")
        act_diag.triggered.connect(lambda: self.diagnose_stock_strategy(code, name))

        act_dna = menu.addAction("🧬 DNA 审计所选")
        act_dna.triggered.connect(self._on_diagnose_dna_click)

        menu.addSeparator()
        act_copy = menu.addAction("📋 复制股票代码")
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(code))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _on_diagnose_click(self):
        input_code = self.diag_edit.text().strip()
        code = input_code
        from_input_box = bool(input_code)
        if not code:
            row = self.table.currentRow()
            if row >= 0:
                code_item = self.table.item(row, 0)
                if code_item:
                    code = code_item.text().strip()
        
        if not code:
            code = "300058"
        
        self.diagnose_stock_strategy(code, from_input_box=from_input_box)

    def _on_diagnose_dna_click(self):
        code = self.diag_edit.text().strip()
        code = "".join(x for x in code if x.isdigit()).zfill(6) if code else ""
        
        found_row = -1
        if code:
            # Try to find the code in the table
            for r in range(self.table.rowCount()):
                c_item = self.table.item(r, 0)
                if c_item and c_item.text().strip().zfill(6) == code:
                    found_row = r
                    break
        else:
            # If no code in edit box, use current selected row
            found_row = self.table.currentRow()
            if found_row >= 0:
                c_item = self.table.item(found_row, 0)
                if c_item:
                    code = c_item.text().strip().zfill(6)
            
        if not code:
            QMessageBox.warning(self, "警告", "请输入或在表格中选择要诊断的个股代码！")
            return
            
        code_to_name = {}
        if found_row != -1:
            # Found the row: take this row and the next 20 rows (total 21 max)
            for r in range(found_row, min(self.table.rowCount(), found_row + 21)):
                c_item = self.table.item(r, 0)
                n_item = self.table.item(r, 1)
                if c_item:
                    c = c_item.text().strip().zfill(6)
                    n = n_item.text().strip() if n_item else c
                    n = n.replace("★ ", "").strip()
                    code_to_name[c] = n
        else:
            # Not in table (manual entry not in list), fallback to auditing just this stock
            name = None
            if self.top_now is not None and code in self.top_now.index:
                name = self.top_now.loc[code, 'name']
            if not name:
                from backtest_feature_auditor import NAME_CACHE
                name = NAME_CACHE.get(code, code)
            name = name.replace("★ ", "").strip()
            code_to_name[code] = name

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
            # 1. 动态加载自定义列配置
            try:
                custom_cols = cct.dna_audit_custom_cols if (cct and hasattr(cct, 'dna_audit_custom_cols')) else ['dff2', 'dff3', 'Rank']
            except:
                custom_cols = ['dff2', 'dff3', 'Rank']
                
            # 2. 直接获取当前包含自定义列的 DataFrame
            # 优先级: engine._period_dfs[resample] > engine._period_dfs other > flat_df > result_df > top_now (实时行情，必含自定义列)
            def _has_custom(df, cols):
                if df is None or df.empty: return False
                return any(str(c).lower() in [x.lower() for x in df.columns] for c in cols)

            df_active = None
            # 1. 优先从 engine 对应最小周期获取数据
            if hasattr(self, 'engine') and self.engine:
                with self.engine.lock:
                    cand = self.engine._period_dfs.get(resample)
                    if _has_custom(cand, custom_cols):
                        df_active = cand
                    
                    if df_active is None:
                        # 遍历其它存在的周期 DataFrame
                        for p_key, cand in self.engine._period_dfs.items():
                            if _has_custom(cand, custom_cols):
                                df_active = cand
                                break

            # 2. 其次从成员变量中找
            if df_active is None:
                for attr in ('_last_flat_df', 'last_result_df'):
                    cand = getattr(self, attr, None)
                    if _has_custom(cand, custom_cols):
                        df_active = cand
                        break
            # 兜底：top_now 是实时行情 df，必然含有自定义列
            if df_active is None:
                top = getattr(self, 'top_now', None)
                if top is not None and not top.empty:
                    df_active = top
                
            summaries = audit_multiple_codes(
                list(code_to_name.keys()),
                end_date=end_date,
                code_to_name=code_to_name,
                progress_callback=None,
                resample=resample,
                period_data=df_active,
                custom_cols=custom_cols
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

    def diagnose_stock_strategy(self, code=None, name=None, from_input_box=False):
        if not code or not str(code).strip() or str(code).strip() == "000000":
            code = "300058"
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

        # 定位 tree 视图（表格）中的 code，若未找到则进行消息提示
        found = False
        for r in range(self.table.rowCount()):
            c_item = self.table.item(r, 0)
            if c_item and c_item.text().strip().zfill(6) == code:
                self.table.setCurrentCell(r, 0)
                self.table.scrollToItem(c_item)
                found = True
                break
        if not found:
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, f"在当前列表中未找到股票 {code} {name}", duration=2500)

        strat_config = self._get_current_selected_strategy()
        if not strat_config:
            QMessageBox.warning(self, "警告", "未选中任何有效策略！")
            return

        # 记录到最近使用的 10 个策略中并重构列表
        strat_id = strat_config['id']
        recent_ids = self.ui_state.get('recent_strategy_ids', [])
        if strat_id in recent_ids:
            recent_ids.remove(strat_id)
        recent_ids.insert(0, strat_id)
        self.ui_state['recent_strategy_ids'] = recent_ids[:10]
        self._save_state(write_to_disk=True)
        self._rebuild_strategy_combo()
            
        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        if not active_periods:
            QMessageBox.warning(self, "警告", "请至少选择一个参与周期！")
            return

        self.lbl_status.setText(f"正在诊断 {code} 的多周期指标...")
        QApplication.processEvents()

        # Fetch top_now if missing (优先从 IPCSyncManager 读取)
        if self.top_now is None:
            try:
                from multi_period_strategy_engine import get_global_ipc_sync_manager
                ipc_mgr = get_global_ipc_sync_manager()
                if ipc_mgr is not None:
                    ipc_df = ipc_mgr.get_current_df()
                    if ipc_df is not None and not ipc_df.empty:
                        self.top_now = ipc_df
            except Exception:
                pass

        if self.top_now is None:
            try:
                self.top_now = tdd.getSinaAlldf(market='all', vol=ct.json_countVol, vtype=ct.json_countType)
            except Exception as e:
                QMessageBox.critical(self, "错误", f"初始化市场基础数据失败: {e}")
                return

        # 诊断单股时在 UI 主线程进行只读装载 (force_reload=False)，避免在主线程发起重度写盘初始化导致的界面卡死
        is_readonly = self.chk_readonly.isChecked()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for period in active_periods:
                p_norm = str(period).strip()
                if p_norm not in self.engine._period_dfs or self.engine._period_dfs[p_norm].empty:
                    self.lbl_status.setText(f"正在读取 {period} 周期特征数据...")
                    QApplication.processEvents()
                    self.engine.load_period_data(period, self.top_now, force_reload=False, readonly=is_readonly)
                else:
                    df_p = self.engine._period_dfs[p_norm]
                    if p_norm == 'd':
                        self.engine.ensure_strategy_ipc_columns(df_p, force_refresh=False)
        finally:
            QApplication.restoreOverrideCursor()

        self.lbl_status.setText("准备就绪")

        # Build merged row flat DF
        merged_row = {"name": name}

        known_period_suffixes = tuple(f"_{p}" for p in ['d', '2d', '3d', 'w', 'm', '45d', '3M', 'W', 'M', '3m'])
        from query_engine_util import query_engine
        from stock_logic_utils import extract_columns, RESERVED_SQL_FUNCS

        def norm_col(w):
            return re.sub(r'([a-zA-Z]+)(\d*)_(\d+[a-zA-Z]*)', r'\1\2\3', w)

        def suffix_expr(expr, period_suffix, cols_set):
            def repl(match):
                word = match.group(0)
                if word.isdigit() or word in RESERVED_SQL_FUNCS or word in {"and", "or", "not", "True", "False"}:
                    return word
                if any(word.endswith(suf) for suf in known_period_suffixes):
                    return word
                n_word = norm_col(word)
                if word in cols_set or n_word in cols_set:
                    target_w = word if word in cols_set else n_word
                    return f"{target_w}_{period_suffix}"
                # 其它没有周期后缀的变量名（如 macdlast1, dif, dea 等），自动追加当前周期后缀
                return f"{word}_{period_suffix}"
            return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', repl, expr)

        queries = []
        for period in active_periods:
            p_norm = str(period).lower().strip()
            df_p = self.engine._period_dfs.get(p_norm)
            if df_p is None or df_p.empty:
                df_p = self.engine._period_dfs.get(period)

            if df_p is not None and not df_p.empty:
                ctx_p = query_engine._prepare_context(df_p)
                valid_cols = set(df_p.columns) | set(ctx_p.keys())
                
                row_p_df = pd.DataFrame()
                if code in df_p.index:
                    row_p_df = df_p.loc[[code]]
                elif 'code' in df_p.columns:
                    row_p_df = df_p[df_p['code'].astype(str).str.strip().str.zfill(6) == code]
                else:
                    matched_idx = [idx for idx in df_p.index if str(idx).strip().zfill(6) == code]
                    if matched_idx:
                        row_p_df = df_p.loc[matched_idx]

                if not row_p_df.empty:
                    ctx_row = query_engine._prepare_context(row_p_df)
                    for k, val in ctx_row.items():
                        if k in ('df', 'pd', 'np', 'result', 'signal') or callable(val):
                            continue
                        if isinstance(val, pd.Series):
                            v = val.iloc[-1] if not val.empty else None
                        else:
                            v = val
                        if v is not None:
                            v_clean = v.item() if hasattr(v, 'item') and not isinstance(v, (str, bytes)) else v
                            merged_row[f"{k}_{period}"] = v_clean
                            if k not in merged_row or period == 'd':
                                merged_row[k] = v_clean
                
                cond = strat_config['conditions'].get(period)
                if not cond:
                    cond = strat_config['conditions'].get(p_norm)
                if not cond:
                    cond = strat_config['conditions'].get(period.upper())

                if cond:
                    raw_filter = cond['filter']
                    expanded_filter = query_engine._preprocess_query(raw_filter)
                    suffixed_filter = suffix_expr(expanded_filter, period, valid_cols)
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "period": period.upper(),
                        "expr": suffixed_filter
                    })
            else:
                cond = strat_config['conditions'].get(period)
                if not cond:
                    cond = strat_config['conditions'].get(p_norm)
                if not cond:
                    cond = strat_config['conditions'].get(period.upper())
                if cond:
                    raw_filter = cond['filter']
                    expanded_filter = query_engine._preprocess_query(raw_filter)
                    queries.append({
                        "name": f"{period.upper()}周期条件",
                        "period": period.upper(),
                        "expr": expanded_filter
                    })

        if not queries:
            QMessageBox.warning(self, "警告", "未生成任何有效的诊断条件！")
            return

        df_flat = pd.DataFrame([merged_row], index=[code])
        df_flat.index.name = 'code'

        # ⚡【优先/第1时间调起诊断弹窗】：先看诊断数据
        last_hit_code = getattr(self, "_last_diagnosed_hit_code", None)
        all_strategy_reports = getattr(self, "_last_all_strategy_reports", []) if code == last_hit_code else []

        try:
            self._check_code_dialog = QtCheckCodeDialog(df_flat, code, queries, parent=self, all_strategy_reports=all_strategy_reports)
            if hasattr(self, "_register_child_dialog"):
                self._register_child_dialog(self._check_code_dialog)
            else:
                if not hasattr(self, "_child_dialogs"):
                    self._child_dialogs = set()
                self._child_dialogs.add(self._check_code_dialog)
            self._check_code_dialog.show()
            self._check_code_dialog.raise_()
            self._check_code_dialog.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"调起股票检查报告失败: {e}")

        # ⚡【防重复 & 仅在诊断框中输入新 code 时才跑全策略 Hit】
        should_eval_hit = from_input_box and (code != last_hit_code)
        if should_eval_hit:
            self._last_diagnosed_hit_code = code
            QTimer.singleShot(50, lambda: self._eval_all_strategies_hit_for_code(code, active_periods))

    def _eval_all_strategies_hit_for_code(self, code, active_periods):
        """后/异步评估全量策略库对特定股票 code 的 Hit 状态 (使用独立 QThread 后台运行，绝不卡顿 UI)"""
        if hasattr(self, "_single_hit_worker") and self._single_hit_worker is not None:
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(self._single_hit_worker) and self._single_hit_worker.isRunning():
                    self._single_hit_worker.requestInterruption()
                    self._single_hit_worker.quit()
            except Exception:
                pass
            self._single_hit_worker = None

        if not hasattr(self, 'strategies') or not self.strategies:
            return

        self._single_hit_worker = SingleCodeAllHitWorker(self.engine, self.strategies, code, active_periods)
        self._single_hit_worker.finished_signal.connect(self._on_single_code_hit_worker_finished)
        self._single_hit_worker.start()

    def _on_single_code_hit_worker_finished(self, code, single_code_hit_results, all_strategy_reports):
        """后台子线程完成单股全策略评估后的 UI 安全回调"""
        self._single_code_hit_results = single_code_hit_results
        self._diagnosed_code = code
        self._last_all_strategy_reports = all_strategy_reports
        self._rebuild_strategy_combo()

        # 同步更新已打开的诊断窗口里的全策略报告列表
        if hasattr(self, "_check_code_dialog") and self._check_code_dialog is not None:
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(self._check_code_dialog) and hasattr(self._check_code_dialog, "update_all_strategy_reports"):
                    self._check_code_dialog.update_all_strategy_reports(all_strategy_reports)
            except Exception:
                pass

    def _open_history_dialog(self):
        dlg = QueryHistoryDialog(self)
        dlg.applied.connect(self._on_history_query_applied)
        dlg.exec()

    def _on_history_query_applied(self, query):
        self._current_history_query = query
        self.filter_edit.setCurrentText(query)
        self._record_secondary_filter_history(query)
        if self.last_result_df is not None:
            self._show_results(self.last_result_df, self.last_elapsed, self._last_flat_df)

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
        self.filter_edit.setCurrentText(query)
        self._record_secondary_filter_history(query)
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

    def get_current_display_df(self):
        if hasattr(self, "_current_displayed_df") and self._current_displayed_df is not None and not self._current_displayed_df.empty:
            return self._current_displayed_df
        return getattr(self, "_last_flat_df", None)

    def _get_stock_category(self, code, row):
        category = row.get('category', row.get('block', ''))
        if not category or str(category).strip() in ('nan', ''):
            category = self._block_cache.get(code, '')
        return category

    def _format_category_details(self, code, name, category_str):
        if not category_str or str(category_str).strip() in ('nan', '--'):
            return f"股票代码: {code}\n股票名称: {name}\n\n暂无详细板块概念分类数据。"

        cats = [c.strip() for c in re.split(r'[;；,，/|]', str(category_str)) if c.strip()]
        lines = [
            f"股票代码: {code}",
            f"股票名称: {name}",
            f"关联概念板块数量: 共 {len(cats)} 个",
            "-" * 45,
            "所属分类与概念标签列表:"
        ]
        for idx, cat in enumerate(cats, 1):
            lines.append(f"  {idx:02d}. {cat}")
            
        return "\n".join(lines)

    def _show_stock_category_dialog(self, code, name=None):
        code = str(code).strip().zfill(6)
        if not name or name == code or name == "未知股票":
            name = self.get_stock_name(code)
            
        category_str = ""
        df_curr = self.get_current_display_df()
        if df_curr is not None and code in df_curr.index:
            row = df_curr.loc[code]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            category_str = self._get_stock_category(code, row)
            
        if not category_str:
            category_str = self._block_cache.get(code, '')
        if not category_str and self.top_now is not None and code in self.top_now.index:
            r = self.top_now.loc[code]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            category_str = r.get('category', r.get('block', ''))
            
        formatted_cat = self._format_category_details(code, name, category_str)
        if not hasattr(self, "_stock_category_wins"):
            self._stock_category_wins = {}

        win_key = f"{code}_{name}"
        if win_key in self._stock_category_wins:
            win = self._stock_category_wins[win_key]
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(win):
                    win.showNormal()
                    win.raise_()
                    win.activateWindow()
                    return
            except Exception:
                pass

        dialog = StockCategoryDetailDialog(self, code, name, formatted_cat)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._stock_category_wins[win_key] = dialog
        if hasattr(self, "_register_child_dialog"):
            self._register_child_dialog(dialog)
        else:
            if not hasattr(self, "_child_dialogs"):
                self._child_dialogs = set()
            self._child_dialogs.add(dialog)
        dialog.show()

    def _normalize_concept_name(self, name):
        if not name:
            return ""
        name = name.strip()
        for suff in ("概念", "板块", "行业"):
            if name.endswith(suff) and len(name) > len(suff):
                name = name[:-len(suff)]
        return name

    def _is_noise_concept(self, name):
        if not name:
            return True
        name = name.strip()
        noise_keywords = (
            "昨日涨停", "昨日触板", "深股通", "沪股通", "融资融券", "标普道琼斯A股", "MSCI中国",
            "富时罗素", "标准普尔", "破净股", "证监会行业", "地方国企改革", "央企国企改革",
            "转融通扣券", "注册制", "同花顺", "东方财富", "含可转债", "高送转", "机构重仓",
            "富时概念", "沪企改革", "百元股"
        )
        if name in noise_keywords:
            return True
            
        # 过滤财报/业绩预增/年份预增（如 2025中报预增、2024三季报预增、中报预增、年报预增、季报预增、业绩预增、预盈预增等）
        if re.search(r'(\d{4})?(中报|年报|季报|一季报|三季报)?(预增|预盈|业绩预增|预降|亏损|递增)', name):
            return True
        if re.search(r'\d{4}(中报|年报|季报|一季报|三季报)', name):
            return True

        return False

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
        df_curr = self.get_current_display_df()
        if df_curr is None or df_curr.empty:
            QMessageBox.information(self, "提示", "当前无筛选数据，请先执行筛选。")
            return

        from collections import Counter
        concept_counter = Counter()
        concept_to_codes = {}
        for code, row in df_curr.iterrows():
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

        df_curr = self.get_current_display_df()
        if df_curr is None or df_curr.empty:
            QMessageBox.information(self, "信息", "当前无筛选数据，无法查看个股列表")
            return

        # Rebuild index dynamically for current active display dataframe
        concept_index = getattr(self, "_concept_index", None)
        if concept_index is None:
            concept_index = {}
            for code, row in df_curr.iterrows():
                category = self._get_stock_category(code, row)
                if not category:
                    continue
                cats = [c.strip() for c in re.split(r'[;；,，/|]', category) if c.strip()]
                for cat in cats:
                    norm_cat = self._normalize_concept_name(cat)
                    if norm_cat and not self._is_noise_concept(norm_cat):
                        concept_index.setdefault(norm_cat, []).append(code)
            self._concept_index = concept_index

        matched_codes = concept_index.get(target_concept, [])
        matched_stocks = [(code, df_curr.loc[code]) for code in matched_codes if code in df_curr.index]

        if not matched_stocks:
            QMessageBox.information(self, "信息", f"当前筛选结果中暂无属于【{target_concept}】的个股")
            return

        active_periods = [p for p, chk in self.period_checkboxes.items() if chk.isChecked()]
        active_customs = [c for c, act in self.custom_col_actions.items() if act.isChecked()]

        custom_cols = []
        for c in active_customs:
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, df_curr)
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
            disp_periods = self._get_display_periods_for_custom_col(c, active_periods, df_curr)
            for p in disp_periods:
                headers[f"{c}_{p}"] = f"{c}({p})"
        for p in active_periods:
            headers[f"pass_{p}"] = f"{p}通过"

        # 使用非模态 (Non-Modal) 方式打开，管理与维护句柄字典避免重复或被 GC 提前释放，且不阻塞主窗口及其他板块操作
        if not hasattr(self, "_concept_stocks_wins"):
            self._concept_stocks_wins = {}

        if target_concept in self._concept_stocks_wins:
            win = self._concept_stocks_wins[target_concept]
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(win):
                    win.showNormal()
                    win.raise_()
                    win.activateWindow()
                    return
            except Exception:
                pass

        dialog = ConceptStocksDialog(self, target_concept, matched_stocks, columns, headers)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._concept_stocks_wins[target_concept] = dialog
        dialog.show()

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
                if 'ratio' in self.top_now.columns:
                    sh_pct = float(self.top_now['ratio'].mean())
                elif 'percent' in self.top_now.columns:
                    sh_pct = float(self.top_now['percent'].mean())
                elif 'sh000001' in self.top_now.index:
                    sh_pct = float(self.top_now.loc['sh000001'].get('percent', 0.0))
                elif '000001' in self.top_now.index and 'sh' in str(self.top_now.loc['000001'].get('code', '')):
                    sh_pct = float(self.top_now.loc['000001'].get('percent', 0.0))
                self.dragon_monitor_dialog.update_data(self.top_now, sh_pct)
        except Exception as e:
            logger.error(f"Failed to open dragon monitor: {e}")
            QMessageBox.critical(self, "错误", f"调起龙头监控看板失败: {e}")

    def open_strategy_editor(self):
        dialog = MultiPeriodStrategyEditorDialog(self, self.engine, self._on_strategies_saved)
        dialog.exec()

    def _on_strategies_saved(self, new_strategies):
        self.strategies = new_strategies
        self._rebuild_strategy_combo()

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
        self.monitor_app = parent
        self._real_parent = parent
        active_modal = QApplication.activeModalWidget()
        if active_modal and parent is not active_modal:
            parent = active_modal
        super().__init__(None)  # 彻底切断底层 Win32 Owner 物理置顶关系，允许多周期主窗口点击时置顶盖在前面
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # 🚀【接收主窗口退出事件】：保持为独立悬浮窗口，收到主窗口/多周期退出信号时主动 close()
        try:
            ui_event_hub.multi_period_closing.connect(self.close)
            ui_event_hub.main_window_closing.connect(self.close)
        except Exception:
            pass

        self.summaries = summaries
        self.end_date = end_date
        self.resample = resample
        try:
            self.custom_cols = cct.dna_audit_custom_cols if (cct and hasattr(cct, 'dna_audit_custom_cols')) else ['dff2', 'dff3', 'Rank']
        except:
            self.custom_cols = ['dff2', 'dff3', 'Rank']
        
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
        
        columns = ["代码", "名称", "DNA意图分", "波段涨幅%"]
        for col in self.custom_cols:
            columns.append(col)
        columns.append("极限判定")
        
        self.table = BaseATSTableWidget(self)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # 自适应列宽，除最后一列极限判定拉满外，前几列均根据内容自适应
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i in range(len(columns) - 1):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(len(columns) - 1, QHeaderView.ResizeMode.Stretch)
        
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
        
        # 寻找可用的 link_stock
        self.link_target = None
        if self.monitor_app and hasattr(self.monitor_app, 'link_stock'):
            self.link_target = self.monitor_app
        else:
            p = parent
            while p:
                if hasattr(p, 'link_stock'):
                    self.link_target = p
                    break
                if hasattr(p, 'parent') and p.parent():
                    p = p.parent()
                elif hasattr(p, 'window') and p.window() and p.window() != p:
                    p = p.window()
                else:
                    break

        if self.link_target:
            self.table.stock_activated.connect(self.link_target.link_stock)
        
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
        
        # 填充数据时暂时禁用排序，避免插入过程混乱
        self.table.setSortingEnabled(False)
        
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
            
            # 动态填充自定义列
            latest_bar = s.history[-1] if s.history else {}
            col_offset = 4
            for col in self.custom_cols:
                val = latest_bar.get(col, 0)
                custom_item = NumericWidgetItem(str(int(val)))
                custom_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(idx, col_offset, custom_item)
                col_offset += 1
                
            verdict_item = QTableWidgetItem(s.verdict)
            self.table.setItem(idx, col_offset, verdict_item)
            
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
            def _cjk_w(s):
                """计算字符串视觉宽度（CJK字符占2格）"""
                return sum(2 if '\u4e00' <= c <= '\u9fff' or '\uff00' <= c <= '\uffef' or '\u3000' <= c <= '\u303f' else 1 for c in str(s))
            def _rjust(s, w):
                s = str(s); pad = w - _cjk_w(s); return ' ' * max(0, pad) + s
            def _ljust(s, w):
                s = str(s); pad = w - _cjk_w(s); return s + ' ' * max(0, pad)

            header = _ljust('日期', 12) + ' ' + _rjust('Alpha', 8) + ' ' + _rjust('涨幅%', 8) + ' ' + _rjust('指数%', 8) + ' ' + _rjust('Bol-U', 8) + ' ' + _rjust('量比', 8)
            for col in self.custom_cols:
                header += ' ' + _rjust(col, 8)
            header += "\n"

            html_content += header
            html_content += "-" * (60 + len(self.custom_cols) * 9) + "\n"
            for h in target_s.history[-15:]:
                row_str = f"{h['date']:<12} {h['alpha']:>8.2f} {h['pct']:>8.2f} {h['idx_pct']:>8.2f} {h['c_upper']:>8.2f} {h['v_ratio']:>8.2f}"
                for col in self.custom_cols:
                    val = h.get(col, 0)
                    row_str += f" {int(val):>8}"
                row_str += "\n"
                html_content += row_str
            
            html_content += "</pre>"
            self.detail_text.setHtml(html_content)
            
    def _on_item_double_clicked(self, item):
        code = self.table.item(item.row(), 0).text()
        name_item = self.table.item(item.row(), 1)
        name = name_item.text().strip() if name_item else ""
        if self.link_target and hasattr(self.link_target, 'link_stock'):
            self.link_target.link_stock(code, name)

    def _on_cell_clicked(self, row, column):
        if column == 0:  # 点击代码列
            code_item = self.table.item(row, 0)
            if code_item:
                code = code_item.text().strip()
                
                # 级联寻找可以回填的 diag_edit/diag_entry 或是 诊断方法
                diag_target = None
                p = self.monitor_app
                while p:
                    if hasattr(p, 'diag_edit') or hasattr(p, 'diag_entry') or hasattr(p, 'diagnose_stock_strategy'):
                        diag_target = p
                        break
                    if hasattr(p, 'parent') and p.parent():
                        p = p.parent()
                    elif hasattr(p, 'window') and p.window() and p.window() != p:
                        p = p.window()
                    else:
                        break
                
                if diag_target:
                    if hasattr(diag_target, 'diag_edit') and diag_target.diag_edit:
                        # QLineEdit 或者 Tk Entry
                        if hasattr(diag_target.diag_edit, 'setText'):
                            diag_target.diag_edit.setText(code)
                        else:
                            try:
                                diag_target.diag_edit.delete(0, 'end')
                                diag_target.diag_edit.insert(0, code)
                            except:
                                pass
                    elif hasattr(diag_target, 'diag_entry') and diag_target.diag_entry:
                        if hasattr(diag_target.diag_entry, 'setText'):
                            diag_target.diag_entry.setText(code)
                        else:
                            try:
                                diag_target.diag_entry.delete(0, 'end')
                                diag_target.diag_entry.insert(0, code)
                            except:
                                pass
                                
                    if hasattr(diag_target, 'diagnose_stock_strategy'):
                        diag_target.diagnose_stock_strategy(code)
            
    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        if self.table.rowCount() > 0:
            self.table.setFocus()

    def closeEvent(self, event):
        if hasattr(self, "save_window_position_qt_visual"):
            try:
                self.save_window_position_qt_visual(self, self.window_name)
            except Exception as e:
                logger.warning(f"Error saving window position: {e}")

        # 1. 停止并安全清理当前窗口持有的子线程 worker
        for attr in ("worker", "_hit_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(w) and w.isRunning():
                        logger.info(f"[MultiPeriodDialog] Stopping background {attr} thread...")
                        w.requestInterruption()
                        w.quit()
                        if not w.wait(1000):
                            logger.warning(f"[MultiPeriodDialog] {attr} thread timed out, terminating...")
                            w.terminate()
                            w.wait(500)
                except Exception as e:
                    logger.warning(f"[MultiPeriodDialog] Exception stopping {attr}: {e}")
                finally:
                    setattr(self, attr, None)

        # 2. 清理 _active_workers 全局集合中残留的活跃 Worker
        global _active_workers
        for w in list(_active_workers):
            try:
                from PyQt6.sip import isdeleted
                if not isdeleted(w) and w.isRunning():
                    w.requestInterruption()
                    w.quit()
                    if not w.wait(800):
                        w.terminate()
                        w.wait(300)
            except Exception:
                pass
        _active_workers.clear()

        # 3. 停止对话框下的所有 QTimer 定时器
        try:
            for timer in self.findChildren(QTimer):
                if timer.isActive():
                    timer.stop()
        except Exception as e:
            logger.warning(f"[MultiPeriodDialog] Error stopping QTimers: {e}")

        # 4. 🚀【广播多周期退出事件】：通知所有独立悬浮窗口 (DNA、诊断、个股详情等) 接收退出事件并主动 close() 销毁
        try:
            ui_event_hub.multi_period_closing.emit()
        except Exception as e:
            logger.warning(f"[MultiPeriodDialog] Error emitting multi_period_closing signal: {e}")

        if hasattr(self, "_child_dialogs") and self._child_dialogs:
            for dlg in list(self._child_dialogs):
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(dlg):
                        dlg.close()
                except Exception:
                    pass
            self._child_dialogs.clear()

        if hasattr(self, "_stock_category_wins") and self._stock_category_wins:
            for win in list(self._stock_category_wins.values()):
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(win):
                        win.close()
                except Exception:
                    pass
            self._stock_category_wins.clear()

        for child_attr in ("_check_code_dialog", "_dna_audit_win", "_strategy_editor_win"):
            child_win = getattr(self, child_attr, None)
            if child_win is not None:
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(child_win):
                        child_win.close()
                except Exception:
                    pass
                setattr(self, child_attr, None)

        super().closeEvent(event)

    def _register_child_dialog(self, dlg):
        """自动注册并跟踪由本多周期窗口发起的子弹窗 (个股详情、诊断报告等)，以便多周期退出时 100% 跟随关闭"""
        if not hasattr(self, "_child_dialogs"):
            self._child_dialogs = set()
        if dlg is not None:
            self._child_dialogs.add(dlg)
            try:
                dlg.destroyed.connect(lambda obj=None, d=dlg: self._child_dialogs.discard(d) if hasattr(self, "_child_dialogs") else None)
            except Exception:
                pass


class QtCheckCodeDialog(QDialog, WindowMixin):
    def __init__(self, df, code, queries, parent=None, all_strategy_reports=None):
        self._real_parent = parent
        super().__init__(None)  # 彻底切断底层 Win32 Owner 物理置顶关系，允许窗口自由移至主窗口身后
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        # 🚀【接收主窗口退出事件】：保持为独立悬浮窗口，收到主窗口/多周期退出信号时主动 close()
        try:
            ui_event_hub.multi_period_closing.connect(self.close)
            ui_event_hub.main_window_closing.connect(self.close)
        except Exception:
            pass

        self.df = df
        self.code = str(code).strip().zfill(6)
        self.queries = queries
        self.all_strategy_reports = all_strategy_reports or []
        self.name = df.at[code, 'name'] if 'name' in df.columns else ""
        
        self.setWindowTitle(f"股票检查报告 - {code} {self.name}")
        self.setMinimumSize(450, 320)
        self.setSizeGripEnabled(True)
        
        flags = Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        self.setWindowFlags(flags)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0c0d14;
                color: #e2e2e5;
            }
            QLabel {
                color: #e2e2e5;
                font-weight: bold;
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
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(6)
        
        right_layout.addWidget(QLabel(">>> 所有数据字段详情", self))
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("过滤字段:", self))
        self.filter_edit = QLineEdit(self)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_edit)
        right_layout.addLayout(filter_layout)
        
        self.details_text = QTextEdit(self)
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.details_text)
        
        self.splitter.addWidget(self.right_widget)
        self.right_widget.hide()
        
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("历史/策略:", self))
        self.history_combo = QComboBox(self)
        self.history_combo.addItem("选择历史/策略...")
        
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

        # 关联添加全策略诊断报告到下拉菜单中
        if self.all_strategy_reports:
            main_hit_results = getattr(self._real_parent, '_last_hit_results', {}) if self._real_parent else {}
            self.history_combo.addItem("--- 🎯 全策略命中测试列表 ---")
            self.history_queries.append(None)
            for i, r in enumerate(self.all_strategy_reports, 1):
                status_tag = "✅" if r.get('hit') else "❌"
                s_id = r.get('id', '')
                s_name = r.get('name', '')
                h_cnt = main_hit_results.get(s_id, main_hit_results.get(s_name))
                h_cnt_str = f" [{h_cnt}只]" if h_cnt is not None else ""
                self.history_combo.addItem(f"S{i:02d}: {status_tag} {s_name}{h_cnt_str}")
                self.history_queries.append(r)
                
        self.history_combo.currentIndexChanged.connect(self._on_history_changed)
        self.history_combo.setMinimumWidth(120)
        self.history_combo.setMaximumWidth(200)
        ctrl_layout.addWidget(self.history_combo)
        
        ctrl_layout.addWidget(QLabel("手动测试:", self))
        self.manual_edit = QLineEdit(self)
        self.manual_edit.setPlaceholderText("输入测试表达式，回车执行...")
        self.manual_edit.returnPressed.connect(self._run_manual_test)
        ctrl_layout.addWidget(self.manual_edit, 1)
        
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
            from stock_logic_utils import test_code_query, format_check_result, generate_channel_strategy_text
            self.report_data = test_code_query(self.df_code, queries)
            header_str = f"股票: {code} {self.name}\n" + "="*40 + "\n"

            # ⚡ 自动接入通道策略计划 (使用最小周期匹配，放在最上方，与 Tk 诊断 100% 对齐)
            row_dict = self.df.loc[self.code].to_dict() if self.code in self.df.index else {}
            channel_strat_text = generate_channel_strategy_text(row_dict, df_code=self.df_code)

            summary_content = header_str
            if channel_strat_text:
                summary_content += channel_strat_text + "\n\n"
            summary_content += format_check_result(self.report_data)

            if self.all_strategy_reports:
                main_hit_results = getattr(self._real_parent, '_last_hit_results', {}) if self._real_parent else {}
                hit_cnt_total = sum(1 for r in self.all_strategy_reports if r.get('hit'))
                total_strats = len(self.all_strategy_reports)
                
                summary_lines = [
                    "\n" + "="*40,
                    f"📊 全策略命中诊断汇总 [ 股票: {code} {self.name} ]",
                    f"🎯 总计测试 {total_strats} 套策略 | 共命中 {hit_cnt_total} 套策略",
                    "-"*40
                ]
                for i, r in enumerate(self.all_strategy_reports, 1):
                    status_tag = "✅ 命中" if r.get('hit') else "❌ 未命中"
                    s_id = r.get('id', '')
                    s_name = r.get('name', '')
                    h_cnt = main_hit_results.get(s_id, main_hit_results.get(s_name))
                    h_cnt_str = f" [Hit: {h_cnt}只]" if h_cnt is not None else ""
                    summary_lines.append(f"  {status_tag} | {s_name}{h_cnt_str}")
                summary_lines.append("="*40)
                summary_content += "\n" + "\n".join(summary_lines)

            self.summary_text.setPlainText(summary_content)
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
            from query_engine_util import query_engine
            ctx = query_engine._prepare_context(self.df)
            full_row_dict = dict(row_dict)
            for k, v in ctx.items():
                if k in ('df', 'pd', 'np', 'result', 'signal') or callable(v):
                    continue
                if isinstance(v, pd.Series) and self.code in v.index:
                    val = v.loc[self.code]
                    full_row_dict[k] = val.item() if hasattr(val, 'item') and not isinstance(val, (str, bytes)) else val

            used_cols = set()
            from stock_logic_utils import extract_columns
            for r in self.report_data:
                if 'expr' in r:
                    used_cols.update(extract_columns(r['expr']))
            
            # 计算统计数据
            total_queries = len(self.report_data) if hasattr(self, 'report_data') and self.report_data else 0
            pass_queries = sum(1 for r in self.report_data if r.get('ok')) if total_queries > 0 else 0
            pass_ratio = (pass_queries / total_queries * 100) if total_queries > 0 else 0.0
            all_ok = (pass_queries == total_queries) if total_queries > 0 else False
            total_fields_cnt = len(self.df.columns)

            self.raw_fields_lines.append("==================================================")
            self.raw_fields_lines.append("📊 诊断与字段统计摘要")
            self.raw_fields_lines.append("--------------------------------------------------")
            self.raw_fields_lines.append(f"  • 检查股票: {self.code} {self.name}")
            self.raw_fields_lines.append(f"  • 综合结果: {'✅ 全部通过' if all_ok else '❌ 未能完全通过'}")
            self.raw_fields_lines.append(f"  • 条件通过率: {pass_queries} / {total_queries} ({pass_ratio:.1f}%)")
            self.raw_fields_lines.append(f"  • 查询涉及关键字段: {len(used_cols)} 个")
            self.raw_fields_lines.append(f"  • 全量数据字段总数: {total_fields_cnt} 个")
            self.raw_fields_lines.append("==================================================")
            self.raw_fields_lines.append("")

            if used_cols:
                self.raw_fields_lines.append(">>> 查询涉及的关键字段:")
                for c in sorted(list(used_cols)):
                    self.raw_fields_lines.append(f"  {c}: {full_row_dict.get(c, 'N/A')}")
                self.raw_fields_lines.append("-" * 40)
                
            self.raw_fields_lines.append(">>> 所有字段列表 (DataFrame 顺序):")
            for c in self.df.columns:
                self.raw_fields_lines.append(f"  {c}: {row_dict.get(c, 'N/A')}")
        except Exception as e:
            self.raw_fields_lines.append(f"提取字段信息失败: {e}")
            
        self._render_fields(self.raw_fields_lines)
        
    def _render_fields(self, lines):
        self.details_text.setPlainText("\n".join(lines))
            
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
        if index <= 0 or index - 1 >= len(self.history_queries):
            return
        try:
            item = self.history_queries[index - 1]
            if item is None:
                return
            if isinstance(item, str):
                self.manual_edit.setText(item)
                self._run_manual_test(item)
            elif isinstance(item, dict) and 'strategy' in item:
                strat = item['strategy']
                conds = strat.get('conditions', {})
                expr_parts = []
                for p_name, cond_info in conds.items():
                    if cond_info and cond_info.get('enabled', True):
                        f_expr = cond_info.get('filter', '')
                        if f_expr:
                            expr_parts.append(f"({f_expr})")
                combined_expr = " and ".join(expr_parts) if expr_parts else ""
                if combined_expr:
                    self.manual_edit.setText(combined_expr)
                    self._run_manual_test(combined_expr)
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
        if hasattr(self, "save_window_position_qt_visual"):
            self.save_window_position_qt_visual(self, self.window_name)
        super().closeEvent(event)


if __name__ == "__main__":
    import sys
    import multiprocessing
    multiprocessing.freeze_support()

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    
    dialog = MultiPeriodDialog()
    dialog.show()
    sys.exit(app.exec())
