# -*- coding: utf-8 -*-
"""
ATS Main Window Panel
Assembles the complete Autonomous Trading System UI dashboard.
"""

import sys
import os
import time
import json
import logging
from typing import Optional, List, Dict, Any, Tuple

# 兼容开发模式单独运行子脚本（防重复挂载，打包运行下 if 为 False 不会污染 sys.path）
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CUR_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("ATS")

# 必须在导入任何 PyQt6 UI 元素前确保 HighDPI 高分屏自适应生效
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTabWidget, QLabel, QToolBar, QPushButton, QStatusBar, QDialog, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QGridLayout, QCheckBox, QComboBox, QAbstractItemView, QSizePolicy
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QRect, QSettings
from PyQt6.QtGui import QAction, QIcon, QColor, QBrush

from ats.ui.favorite_panel import FavoritePanel
from ats.ui.styles import DARK_THEME_QSS, enable_tab_direct_switch, save_config_node, load_config_node

PERSIST_KEY_CHANNEL_SCAN_PERIOD = "channel_scan_selected_period"
from ats.ui.universe_widget import UniverseTreeWidget
from ats.ui.heatmap_widget import SectorHeatmapWidget
from ats.ui.chart_widgets import DistributionBarChart, EquityCurveChart
from ats.ui.swing_table import SwingStateTable
from ats.ui.trade_flow import TradeFlowTable, PositionPanel, BacktestReportPanel
from ats.ui.kernel_trace_panel import KernelTracePanel
from ats.ui.dragon_monitor import DragonLeaderMonitorDialog
from ats.ui.hot_sector_leaderboard import HotSectorLeaderboardDialog
from ats.ui.daily_limit_up_dialog import DailyLimitUpDialog
from ats.ui.new_stock_panel import NewStockPanel
from ats.universe_manager import UniverseManager
from ats.swing_tracker import SwingTracker
from ats.signal_ledger import SignalLedger
from ats.volume_profiler import VolumeProfiler
from ats.session_snapshot import SessionSnapshot
from JohnsonUtil import commonTips as cct


class LedgerUpdateWorker(QThread):
    """
    ⚡ 后台信号账本计算 Worker — 彻底解耦数据计算与 UI 渲染，根治主线程卡顿

    职责：在后台线程中完成全部重量级数据计算：
      1. _update_signal_ledger (向量化偏离度 + volume_profiler 更新)
      2. swing_rows / fav_rows 列表计算
    计算完成后通过 results_ready Signal 推回主线程，主线程仅负责 <20ms 的纯 UI 渲染。

    线程安全规范：Worker 中绝不操作任何 Qt Widget。
    """
    # (swing_rows, fav_rows, sh_pct, alpha_signals, ledger_stats_str)
    results_ready = pyqtSignal(list, list, float, list, str)

    def __init__(self, df_all, signal_ledger, volume_profiler,
                 session_snapshot, swing_tracker, stock_history_cache,
                 price_pct_cache, name_cache, fav_stocks, universe_manager,
                 today_str):
        super().__init__()
        # 浅拷贝 DataFrame：仅复制 index/columns 结构元数据，数据块共享内存
        # 在 Worker 只读访问 df 的场景下足够安全，避免 ~80ms 的深拷贝开销
        import pandas as pd
        self._df = df_all.copy(deep=False)
        self._signal_ledger = signal_ledger
        self._volume_profiler = volume_profiler
        self._session_snapshot = session_snapshot
        self._swing_tracker = swing_tracker
        self._stock_history_cache = stock_history_cache
        self._price_pct_cache = price_pct_cache
        self._name_cache = name_cache
        self._fav_stocks = fav_stocks
        self._universe_manager = universe_manager
        self._today_str = today_str

    def _get_name(self, code):
        """从 name_cache 或 df 解析股票名称 (无 IO 纯内存)"""
        n = self._name_cache.get(code, '')
        if n and n not in ('未知', '重点标的'):
            return n
        code_clean = ''.join(c for c in str(code) if c.isdigit()).zfill(6)
        n2 = self._name_cache.get(code_clean, '')
        return n2 if (n2 and n2 not in ('未知', '重点标的')) else code

    def run(self):
        import time as _time
        import datetime
        import pandas as pd
        try:
            df_all = self._df
            t0 = _time.time()

            # ── 阶段 A: 更新信号账本 (原 _update_signal_ledger 逻辑) ──────────────
            self._volume_profiler.update_market_context(df_all)

            # 定位 MA20 列
            ma20_col = next((c for c in ('ma20d', 'ma20', 'MA20', 'ma20_series') if c in df_all.columns), None)
            close_col = 'close' if 'close' in df_all.columns else 'price'

            if ma20_col and close_col in df_all.columns:
                close_s = pd.to_numeric(df_all[close_col], errors='coerce')
                safe_ma20 = pd.to_numeric(df_all[ma20_col], errors='coerce').replace(0, float('nan'))
                dev_series = (close_s - safe_ma20) / safe_ma20 * 100.0

                tracked_codes = set(self._signal_ledger.entries.keys())
                valid_mask = (
                    ((dev_series >= self._signal_ledger.DEVIATION_MIN) &
                     (dev_series <= self._signal_ledger.DEVIATION_MAX)) |
                    df_all.index.isin(tracked_codes)
                )
                target_df = df_all[valid_mask]

                valid_target_codes = []
                target_dict = target_df.to_dict('index')
                for code, row in target_dict.items():
                    code_str = str(code).strip()
                    if not code_str or code_str in ('sh000001', 'sz399001', 'sz399006',
                                                     '000001.SH', '399001.SZ', '399006.SZ'):
                        continue
                    try:
                        price = float(row.get(close_col, 0.0))
                        ma20_val = float(row.get(ma20_col, 0.0))
                        if price <= 0 or ma20_val <= 0:
                            continue
                        self._volume_profiler.update_profile(code_str, row)
                        valid_target_codes.append((code_str, row, price, ma20_val))
                    except Exception:
                        continue

                active_codes_list = [item[0] for item in valid_target_codes]
                self._volume_profiler.analyze_sector_resonance(active_codes=active_codes_list)

                for code_str, row, price, ma20_val in valid_target_codes:
                    try:
                        name = str(row.get('name', ''))
                        pct = float(row.get('percent', 0.0))
                        deviation = (price - ma20_val) / ma20_val * 100.0
                        vol_score = self._volume_profiler.get_volume_score(code_str)
                        self._signal_ledger.record_signal(
                            code=code_str, name=name, price=price, pct=pct,
                            deviation=deviation, row=row, volume_score=vol_score,
                        )
                    except Exception:
                        continue

            # 快照持久化 (文件 IO 放在 Worker 线程，不阻塞主线程)
            if self._session_snapshot.should_snapshot():
                self._session_snapshot.save_snapshot(self._signal_ledger)
                self._session_snapshot.cleanup_old_snapshots()

            now_dt = datetime.datetime.now()
            try:
                is_trade_day = cct.get_trade_date_status()
            except Exception:
                is_trade_day = False
            if is_trade_day and now_dt.hour >= 15:
                self._session_snapshot.save_daily_summary(self._signal_ledger)

            # ── 阶段 B: 计算 swing_rows (原 refresh_realtime_ui 中的 for code in all_codes) ──
            # 从信号账本同步三级池
            self._universe_manager.sync_from_ledger(
                self._signal_ledger,
                df_realtime=df_all,
                price_pct_cache=self._price_pct_cache
            )

            pool_codes = (list(self._universe_manager.radar_pool.keys()) +
                          list(self._universe_manager.watch_pool.keys()) +
                          list(self._universe_manager.trade_pool.keys()))
            all_codes = list(dict.fromkeys(pool_codes + [c for c in self._fav_stocks if c]))

            # 计算大盘涨幅参考
            sh_pct = 0.0
            for idx_code in ('sh000001', '000001'):
                if idx_code in df_all.index:
                    try:
                        sh_pct = float(df_all.loc[idx_code, 'percent'])
                        break
                    except Exception:
                        pass
            if sh_pct == 0.0 and 'percent' in df_all.columns:
                sh_pct = float(df_all['percent'].mean())

            swing_rows = []
            alpha_signals = []  # [(code, name, pct_val, sh_pct, rs_val, resonance)]

            for code in all_codes:
                latest_close = 0.0
                pct_val = dff_val = dff2_val = dff3_val = 0.0
                rank_val = 0

                code_clean = ''.join(c for c in str(code) if c.isdigit()).zfill(6) if any(c.isdigit() for c in str(code)) else str(code).strip()

                # 从 df 获取行情
                row = None
                if code in df_all.index:
                    try:
                        r = df_all.loc[code]
                        row = r.iloc[0].to_dict() if hasattr(r, 'iloc') and len(r.shape) > 1 else r.to_dict()
                    except Exception:
                        pass
                elif code_clean in df_all.index:
                    try:
                        r = df_all.loc[code_clean]
                        row = r.iloc[0].to_dict() if hasattr(r, 'iloc') and len(r.shape) > 1 else r.to_dict()
                    except Exception:
                        pass

                if row is not None:
                    try: latest_close = float(row.get('close', row.get('price', 0.0)))
                    except: pass
                    try: pct_val = float(row.get('percent', 0.0))
                    except: pass
                    try: dff_val = float(row.get('dff', 0.0))
                    except: pass
                    try: rank_val = int(row.get('Rank', row.get('rank', 0)))
                    except: pass
                    try: dff2_val = float(row.get('dff2', 0.0))
                    except: pass
                    try: dff3_val = float(row.get('dff3', 0.0))
                    except: pass
                elif code_clean in self._price_pct_cache:
                    latest_close, pct_val = self._price_pct_cache[code_clean]
                elif code in self._price_pct_cache:
                    latest_close, pct_val = self._price_pct_cache[code]
                elif code_clean in self._stock_history_cache and self._stock_history_cache[code_clean]:
                    latest_close = float(self._stock_history_cache[code_clean][-1][1])
                elif code in self._stock_history_cache and self._stock_history_cache[code]:
                    latest_close = float(self._stock_history_cache[code][-1][1])

                name = self._get_name(code)

                rs_val = pct_val - sh_pct
                resonance = '同步整理'
                if sh_pct < -0.3 and pct_val > 1.5:
                    resonance = '逆市抗跌'
                elif sh_pct > 0.3 and pct_val > 3.0 and dff_val > 2.0:
                    resonance = '大盘共振'
                elif pct_val < -3.0 and rs_val < -2.0:
                    resonance = '同步走弱'

                # 历史数据重建
                has_history = (code in self._stock_history_cache and self._stock_history_cache[code]) or \
                              (code_clean in self._stock_history_cache and self._stock_history_cache[code_clean])
                if has_history:
                    hist = self._stock_history_cache.get(code) or self._stock_history_cache.get(code_clean)
                    close_series = [float(item[1]) for item in hist if item[1] is not None]
                    if hist[-1][0] == self._today_str:
                        if close_series: close_series[-1] = latest_close
                    else:
                        close_series.append(latest_close)
                    ma20_series, ma5_series = [], []
                    for i in range(len(close_series)):
                        sub20 = close_series[max(0, i - 19): i + 1]
                        ma20_series.append(sum(sub20) / len(sub20) if sub20 else close_series[i])
                        sub5 = close_series[max(0, i - 4): i + 1]
                        ma5_series.append(sum(sub5) / len(sub5) if sub5 else close_series[i])
                else:
                    row_data = row if row is not None else {}
                    history_closes = []
                    last_val = latest_close
                    for d_idx in range(9, 0, -1):
                        col_name = f'lastp{d_idx}d'
                        try:
                            val = float(row_data.get(col_name, last_val) if row_data else last_val)
                            if val > 0:
                                history_closes.append(val)
                                last_val = val
                        except Exception:
                            pass
                    close_series = history_closes + [latest_close]
                    try: current_ma20 = float(row_data.get('ma20d', row_data.get('ma20', row_data.get('MA20', latest_close)))) if row_data else latest_close
                    except: current_ma20 = latest_close
                    try: current_ma5 = float(row_data.get('ma5d', row_data.get('ma5', row_data.get('MA5', latest_close)))) if row_data else latest_close
                    except: current_ma5 = latest_close
                    ma20_series = [current_ma20] * len(close_series)
                    ma5_series = [current_ma5] * len(close_series)

                # 💥 【核心修复】权威 MA20d / MA5d 动态接入与对齐
                # 无论是否有 _stock_history_cache 历史缓存，只要 row/row_data 或 signal_ledger 中存在权威 MA20d/MA5d 数值，
                # 必须优先使用权威 MA20d/MA5d 作为 ma20_series[-1] / ma5_series[-1]，避免因 HDF5 历史不足20天/未复权导致的偏离度失真 Bug！
                real_ma20 = None
                real_ma5 = None
                row_data = row if row is not None else {}
                if row_data:
                    for k in ('ma20d', 'ma20', 'MA20', 'ma20_series'):
                        if k in row_data and row_data[k] is not None:
                            try:
                                v = float(row_data[k])
                                if v > 0:
                                    real_ma20 = v
                                    break
                            except Exception:
                                pass
                    for k in ('ma5d', 'ma5', 'MA5', 'ma5_series'):
                        if k in row_data and row_data[k] is not None:
                            try:
                                v = float(row_data[k])
                                if v > 0:
                                    real_ma5 = v
                                    break
                            except Exception:
                                pass

                # 兜底 fallback: 若 row_data 中无 ma20d，检查 _signal_ledger.entries 中绑定的偏离度反推 ma20
                if real_ma20 is None and code in self._signal_ledger.entries:
                    entry = self._signal_ledger.entries[code]
                    if entry and entry.latest_deviation is not None and latest_close > 0:
                        try:
                            dev_val = float(entry.latest_deviation)
                            if 1.0 + dev_val / 100.0 > 0:
                                real_ma20 = latest_close / (1.0 + dev_val / 100.0)
                        except Exception:
                            pass

                if real_ma20 and real_ma20 > 0:
                    if ma20_series:
                        ma20_series[-1] = real_ma20
                    else:
                        ma20_series = [real_ma20]

                if real_ma5 and real_ma5 > 0:
                    if ma5_series:
                        ma5_series[-1] = real_ma5
                    else:
                        ma5_series = [real_ma5]

                state, dev_str, position, reason = self._swing_tracker.update_stock_state(
                    code, name, latest_close, close_series, ma20_series, ma5_series
                )

                limit_ups = 0
                if len(close_series) > 1:
                    for idx in range(len(close_series) - 1, 0, -1):
                        if close_series[idx] > close_series[idx - 1] * 1.002:
                            limit_ups += 1
                        else:
                            break

                from ats.signal_ledger import PHASE_LABELS
                entry = self._signal_ledger.entries.get(code)
                if entry:
                    phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
                    first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
                    first_seen = f'{phase_label} [{first_time}]'
                    priority_val = f'{entry.priority_score:.1f}'
                else:
                    first_seen = '⏳ 初始/持仓'
                    priority_val = '0.0'
                from ats.ui.favorite_panel import get_ats_extra_cols
                extra_cols = get_ats_extra_cols()
                extra_vals = []
                for ec in extra_cols:
                    v_raw = None
                    if row is not None:
                        for k in (ec, ec.lower(), ec.upper()):
                            if k in row:
                                v_raw = row[k]
                                break
                    if v_raw is not None:
                        extra_vals.append(cct.format_col_value(ec, v_raw))
                    else:
                        extra_vals.append('--')

                swing_rows.append((
                    code, name, f'{latest_close:.2f}', state, dev_str, str(limit_ups), position,
                    first_seen, priority_val,
                    f'{dff_val:.2f}', str(rank_val), f'{dff2_val:.2f}', f'{dff3_val:.2f}',
                    f'{rs_val:+.2f}%', resonance,
                    *extra_vals,
                    reason
                ))

                if resonance in ('逆市抗跌', '大盘共振'):
                    alpha_signals.append((code, name, pct_val, sh_pct, rs_val, resonance))

            # fav_rows (支持原始代码与6位标准化数字代码双向匹配)
            fav_clean_set = {(''.join(c for c in str(s) if c.isdigit()).zfill(6) if any(c.isdigit() for c in str(s)) else str(s).strip()) for s in self._fav_stocks}
            fav_rows = [r for r in swing_rows if (str(r[0]).strip() in self._fav_stocks or ''.join(c for c in str(r[0]) if c.isdigit()).zfill(6) in fav_clean_set)]

            # ── 阶段 C: 构造状态栏统计文本 ────────────────────────────────────────
            env_label = ''
            if self._volume_profiler.market_context.is_rebound_from_shrink:
                n_shrink = self._volume_profiler.market_context.consecutive_market_shrink_days
                env_label = f' | 🔥 缩量{n_shrink}日后反弹'

            if hasattr(self._signal_ledger, 'get_stats'):
                stats = self._signal_ledger.get_stats()
            else:
                tier_counts = {}
                for e in self._signal_ledger.entries.values():
                    t = getattr(e, 'tier', 'RADAR')
                    tier_counts[t] = tier_counts.get(t, 0) + 1
                stats = {'tiers': tier_counts, 'today_new': getattr(self._signal_ledger, '_signal_count', 0)}

            tier_info = stats.get('tiers', {})
            stats_str = (
                f"📊 信号池: 候选 {tier_info.get('RADAR', 0)} | "
                f"精选 {tier_info.get('WATCH', 0)} | 实盘 {tier_info.get('TRADE', 0)} | "
                f"今日新发现: {stats.get('today_new', 0)}{env_label}"
            )

            elapsed = (_time.time() - t0) * 1000.0
            import logging
            logging.getLogger('ATS').debug(f'[LedgerWorker] 后台计算完成 {elapsed:.1f}ms, swing={len(swing_rows)}, fav={len(fav_rows)}')

            self.results_ready.emit(swing_rows, fav_rows, sh_pct, alpha_signals, stats_str)

        except Exception as exc:
            import traceback
            import logging
            logging.getLogger('ATS').error(f'[LedgerWorker] 异常: {exc}\n{traceback.format_exc()}')
            # 出错时仍要清除 busy 标志，由主线程在 _on_ledger_results 中处理，或直接在此 emit 空结果
            self.results_ready.emit([], [], 0.0, [], '')


class QtVarProxy:
    """包装 QCheckBox 或 Callable 为带 .get() 方法的 Var 对象，用于兼容全系统 StockSender 标准单例"""

    def __init__(self, getter_func):
        self.getter_func = getter_func
    def get(self):
        try:
            return bool(self.getter_func())
        except Exception:
            return True

class EquityPopDialog(QDialog):
    """资金曲线与大盘走势独立放大查看窗口"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📈 资金收益率曲线与全市场走势独立放大看板")
        self.resize(960, 640)
        self.setMinimumSize(720, 480)
        
        # 设置为独立 Window 模式，支持最大化、最小化和关闭按钮
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window
        flags |= Qt.WindowType.WindowMinMaxButtonsHint
        self.setWindowFlags(flags)

        if parent and hasattr(parent, 'styleSheet'):
            self.setStyleSheet(parent.styleSheet())
            
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 1. 顶部工具栏
        top_bar = QHBoxLayout()
        title_lbl = QLabel("📈 资金收益率曲线与全市场走势独立放大看板")
        title_lbl.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13pt;")
        
        btn_refresh = QPushButton("🔄 刷新收益曲线")
        btn_refresh.setStyleSheet("background-color: #1f1f2e; color: #aad4ff; font-weight: bold; padding: 4px 12px; border: 1px solid #3a3a48; border-radius: 4px;")
        btn_refresh.clicked.connect(self._on_refresh)

        btn_close = QPushButton("关闭窗口")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; padding: 4px 12px; border-radius: 4px;")
        btn_close.clicked.connect(self.close)

        top_bar.addWidget(title_lbl)
        top_bar.addStretch()
        top_bar.addWidget(btn_refresh)
        top_bar.addWidget(btn_close)
        layout.addLayout(top_bar)

        # 2. TabWidget
        self.pop_tabs = QTabWidget()
        self.pop_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #303042; background: #121216; }
            QTabBar::tab { background: #1a1a24; color: #a0a0b0; padding: 8px 16px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #252538; color: #38bdf8; border-bottom: 2px solid #38bdf8; }
        """)

        self.equity_chart = EquityCurveChart()
        self.dist_chart = DistributionBarChart()

        self.pop_tabs.addTab(self.equity_chart, "📈 策略资金收益曲线 (Equity Curve)")
        self.pop_tabs.addTab(self.dist_chart, "📊 全市场涨跌分布 (Market Distribution)")

        layout.addWidget(self.pop_tabs, 1)

    def _get_parent_mw(self):
        return getattr(self, '_py_parent', None) or self.parent()

    def _on_refresh(self):
        parent_mw = self._get_parent_mw()
        if parent_mw and hasattr(parent_mw, 'bridge') and parent_mw.bridge:
            try:
                dates, strat_equity, bench_equity = parent_mw.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self.equity_chart.update_curve(x, strat_equity, bench_equity)
                return
            except Exception as e:
                print(f"[EquityPopDialog] Refresh error: {e}")
        if hasattr(self.equity_chart, 'draw_mock_curve'):
            self.equity_chart.draw_mock_curve()

    def update_data(self, df_realtime=None):
        if hasattr(self.dist_chart, 'update_data') and df_realtime is not None:
            self.dist_chart.update_data(df_realtime)
        parent_mw = self._get_parent_mw()
        if parent_mw and hasattr(parent_mw, 'bridge') and parent_mw.bridge:
            try:
                dates, strat_equity, bench_equity = parent_mw.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self.equity_chart.update_curve(x, strat_equity, bench_equity)
            except Exception:
                pass


class StockDetailDialog(QDialog):
    def __init__(self, code, name, df_row=None, context_info=None, parent=None, batch_codes=None):
        super().__init__(None) # [🚀 独立窗口解耦] 传入 None 剥离 Win32 HWND Owner 从属关系，防止窗口在 OS 视角下被强制浮在 Parent 主窗口上方
        self._py_parent = parent
        self.is_hidden_state = False
        self.anchor_edge = None
        self.hover_timer = None
        self.snap_timer = None
        self.code = str(code).strip()
        self.name = name
        self.df_row = df_row
        self.context_info = context_info
        self.batch_codes = batch_codes

        # 0. 明确设置为独立顶层窗口类型，并加载置顶配置
        self.stays_on_top = self._load_stays_on_top()
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.Dialog
        flags |= Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        
        self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
        self.resize(550, 650)
        self.setMinimumSize(450, 550)

        # 1. 继承/应用统一 ATS 暗黑风格
        from ats.ui.styles import apply_dark_theme
        apply_dark_theme(self)
        p = self._py_parent or self.parent()
        if p and hasattr(p, 'styleSheet') and callable(p.styleSheet):
            try:
                p_qss = p.styleSheet()
                if p_qss:
                    self.setStyleSheet(self.styleSheet() + "\n" + p_qss)
            except Exception:
                pass
        
        # 2. 自动扫描最新交易内核 Trace 记录
        self._scan_kernel_trace()
        
        # 3. 初始化 UI 布局与填充数据
        self._init_ui(self.code, self.name, self.df_row, self.context_info)
        self.update_data(self.df_row)

        # 5. 磁吸与隐藏状态初始化
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
        self._switching = False
        
        # 悬停与离开监控定时器
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(100)
        self.hover_timer.timeout.connect(self._check_hover)
        self.hover_timer.start()
        
        # 拖拽结束防抖定时器
        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(200)
        self.snap_timer.timeout.connect(self._detect_and_snap)

    def _get_parent_mw(self):
        return getattr(self, '_py_parent', None) or self.parent()

    def _load_stays_on_top(self) -> bool:
        try:
            from ats.ui.styles import load_config_node
            dialog_config = load_config_node("ats_stock_detail_dialog_config", {})
            if isinstance(dialog_config, dict) and "stays_on_top" in dialog_config:
                return bool(dialog_config["stays_on_top"])
        except Exception:
            pass
        return False

    def _save_config_state(self):
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_stock_detail_dialog_config", {"stays_on_top": getattr(self, "stays_on_top", False)})
        except Exception:
            pass

    def _on_stays_on_top_toggled(self, state):
        self.stays_on_top = self.chk_on_top.isChecked()
        flags = self.windowFlags()
        if self.stays_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            # 【置顶与磁吸互斥】：开启置顶时，立即退出磁吸并恢复正常窗口显示
            if getattr(self, 'is_hidden_state', False):
                self.show_normal_position()
            self.is_hidden_state = False
            self.anchor_edge = None
            self.normal_geometry = None
            if hasattr(self, 'snap_timer') and self.snap_timer:
                self.snap_timer.stop()
            if hasattr(self, 'hover_timer') and self.hover_timer:
                self.hover_timer.stop()
            self.hover_ticks = 0
            self.leave_ticks = 0
            self.setWindowOpacity(1.0)
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
            if hasattr(self, 'hover_timer') and self.hover_timer:
                self.hover_timer.start()
        self.setWindowFlags(flags)
        self.show()
        self._save_config_state()

    def _scan_kernel_trace(self):
        """扫描最新交易内核 Trace 记录"""
        self.kernel_info = {}
        try:
            from sys_utils import get_app_root
            import os
            import json
            base = get_app_root()
            trace_path = os.path.join(base, "logs", "trading_kernel_trace.jsonl")
            if os.path.exists(trace_path):
                with open(trace_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                data = json.loads(line)
                                signal_data = data.get("signal", {})
                                intent_data = data.get("intent", {})
                                trace_code = signal_data.get("code") or intent_data.get("code") or ""
                                if str(trace_code).strip() == str(self.code).strip():
                                    self.kernel_info = data
                            except Exception:
                                pass
        except Exception as e:
            print(f"Error scanning kernel trace in dialog: {e}")

    def _restore_geometry(self):
        """从 window_config.json 恢复个股详情弹窗位置与大小"""
        try:
            from sys_utils import get_app_root, get_conf_path
            import json, os
            from PyQt6.QtCore import QByteArray
            from ats.ui.styles import load_config_node
            geom = load_config_node("ats_stock_detail_dialog_geom")
            if geom:
                self.restoreGeometry(QByteArray.fromHex(geom.encode('utf-8')))
        except Exception:
            pass

    def _save_geometry(self):
        """原子写盘持久化个股详情弹窗位置与大小至 window_config.json"""
        try:
            from ats.ui.styles import save_config_node
            hex_data = self.saveGeometry().toHex().data().decode('utf-8')
            save_config_node("ats_stock_detail_dialog_geom", hex_data)
            self._save_config_state()
        except Exception:
            pass

    def closeEvent(self, event):
        """关闭时自动持久化窗口大小与位置"""
        if self.hover_timer:
            self.hover_timer.stop()
        if self.snap_timer:
            self.snap_timer.stop()
        self._save_geometry()
        super().closeEvent(event)

    def hideEvent(self, event):
        """隐藏时自动持久化窗口大小与位置"""
        self._save_geometry()
        super().hideEvent(event)

    def update_batch_codes(self, new_batch_codes=None, current_code=None):
        """【关键机制】动态实时更新弹窗顶部的 [本轮强势信号] 下拉框列表，并 100% 自动高亮选中当前 code"""
        if new_batch_codes is not None:
            self.batch_codes = new_batch_codes
            
        parent_mw = self._get_parent_mw()
        signal_list = self.batch_codes
        if not signal_list and parent_mw and hasattr(parent_mw, "_last_batch_signal_codes") and parent_mw._last_batch_signal_codes:
            signal_list = parent_mw._last_batch_signal_codes

        if not hasattr(self, 'combo_signals') or self.combo_signals is None:
            return

        target_code = str(current_code or self.code).strip()
        
        parsed_list = []
        seen = set()
        if signal_list:
            for item in signal_list:
                if isinstance(item, (tuple, list)):
                    c, n = str(item[0]).strip(), str(item[1]).strip()
                else:
                    c, n = str(item).strip(), str(item).strip()
                if c and c not in seen:
                    seen.add(c)
                    parsed_list.append((c, n))
                    
        # 确保当前被查看的股票 (如 601567) 绝对不会在下拉框中漏掉
        if target_code and target_code not in seen:
            t_name = target_code
            if parent_mw and hasattr(parent_mw, "get_stock_name"):
                t_name = parent_mw.get_stock_name(target_code)
            parsed_list.insert(0, (target_code, t_name))

        if not parsed_list:
            return

        self.combo_signals.blockSignals(True)
        try:
            self.combo_signals.clear()
            cur_idx = 0
            for idx, (c, n) in enumerate(parsed_list):
                self.combo_signals.addItem(f"{c} {n}", c)
                if c == target_code:
                    cur_idx = idx
            self.combo_signals.setCurrentIndex(cur_idx)
        finally:
            self.combo_signals.blockSignals(False)

    def switch_to_code(self, target_c: str, target_n: str = "", batch_codes=None):
        """【核心机制】窗口原地无缝复用刷新，包含磁吸恢复唤醒与下拉框实时更新"""
        if not target_c:
            return
        if getattr(self, '_switching', False):
            return
            
        import time
        t0 = time.perf_counter()
        self._switching = True
        try:
            self.code = str(target_c).strip()
            parent_mw = self._get_parent_mw()
            if parent_mw:
                if not target_n and hasattr(parent_mw, "get_stock_name"):
                    self.name = parent_mw.get_stock_name(self.code)
                elif target_n:
                    self.name = target_n
                else:
                    self.name = self.code

                # 1. 若处于贴边磁吸隐藏状态，强制滑出展平唤醒；若被最小化/隐藏则恢复显示并唤醒；正常显示中则仅原地更新数据
                if getattr(self, 'is_hidden_state', False):
                    if hasattr(self, 'show_normal_position'):
                        self.show_normal_position()
                    else:
                        self.show()
                        self.raise_()
                        self.activateWindow()
                elif self.isMinimized():
                    self.showNormal()
                    self.raise_()
                    self.activateWindow()
                elif not self.isVisible():
                    self.show()
                    self.raise_()
                    self.activateWindow()

                # 2. 内存极速提取最新 df_row 行情 (包含 current_df 与 df_realtime 级联回退)
                df_row = None
                c_clean = str(self.code).strip().zfill(6)
                for attr in ("current_df", "df_realtime"):
                    if hasattr(parent_mw, attr):
                        df = getattr(parent_mw, attr)
                        if df is not None and not df.empty:
                            if c_clean in df.index:
                                row = df.loc[c_clean]
                                df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                                break
                            elif 'code' in df.columns:
                                m = df[df['code'] == c_clean]
                                if not m.empty:
                                    df_row = m.iloc[0].to_dict()
                                    break

                t1 = time.perf_counter()
                # 3. 补齐策略上下文
                if hasattr(parent_mw, "_ensure_context_info"):
                    self.context_info = parent_mw._ensure_context_info(self.code, self.name, {})

                t2 = time.perf_counter()
                # 4. 【极速 UI 优先渲染】瞬间重绘窗口标题、策略上下文与特征表格 (0 毫秒肉眼无感反馈)
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
                if hasattr(self, 'title_label'):
                    self.title_label.setText(f"📊 {self.code}  {self.name}")
                    
                if hasattr(self, 'lbl_pos_val') and self.lbl_pos_val and self.context_info:
                    self.lbl_pos_val.setText(self.context_info.get('position', '--'))
                if hasattr(self, 'lbl_reason_val') and self.lbl_reason_val and self.context_info:
                    self.lbl_reason_val.setText(self.context_info.get('reason', '--'))
                if hasattr(self, 'lbl_status_val') and self.lbl_status_val and self.context_info:
                    self.lbl_status_val.setText(self.context_info.get('status', '--'))

                self.update_data(df_row)
                t3 = time.perf_counter()

                # 5. 【丝滑物理/软件联动】异步发送至外部通达信/同花顺/VIS 终端与 Tree 视图，彻底杜绝界面卡顿
                target_code = self.code
                target_name = self.name
                if hasattr(parent_mw, "link_stock"):
                    QTimer.singleShot(0, lambda: parent_mw.link_stock(target_code, target_name))

                import sys
                is_debug_log = ("-log" in sys.argv and "debug" in sys.argv) or (logger.getEffectiveLevel() <= logging.DEBUG)
                if is_debug_log:
                    print(
                        f"[PERF] StockDetailDialog switch_to_code({self.code}) total: {(t3 - t0)*1000:.2f}ms "
                        f"(prep: {(t1 - t0)*1000:.2f}ms, ctx: {(t2 - t1)*1000:.2f}ms, update: {(t3 - t2)*1000:.2f}ms)"
                    )
        finally:
            self._switching = False
        
    def _init_ui(self, code, name, df_row, context_info):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        # 0.5 仅加载【本轮输出的强势信号列表】(例如本轮 2 只或 6 只，绝不上百只堆叠)
        parent_mw = self._get_parent_mw()
        signal_list = self.batch_codes
        if not signal_list and parent_mw and hasattr(parent_mw, "_last_batch_signal_codes") and parent_mw._last_batch_signal_codes:
            signal_list = parent_mw._last_batch_signal_codes

        if signal_list and len(signal_list) > 1:
            nav_layout = QHBoxLayout()
            nav_label = QLabel("📋 本轮强势信号:")
            nav_label.setStyleSheet("color: #ffd700; font-weight: bold; font-size: 10pt;")
            
            self.btn_prev = QPushButton("◀ 上一只")
            self.btn_next = QPushButton("下一只 ▶")
            self.combo_signals = QComboBox()
            self.combo_signals.setStyleSheet("background-color: #1f1f26; color: #aad4ff; font-weight: bold; padding: 3px 8px; border: 1px solid #3a3a48;")
            
            cur_idx = 0
            for idx, item in enumerate(signal_list):
                if isinstance(item, (tuple, list)):
                    c, n = item[0], item[1]
                else:
                    c, n = str(item), str(item)
                
                c_str = str(c).strip().zfill(6)
                pct_lbl = self._get_pct_str_for_code(parent_mw, c_str)
                self.combo_signals.addItem(f"{c_str} {n}{pct_lbl}", c_str)
                if c_str == str(code).strip().zfill(6):
                    cur_idx = idx
            self.combo_signals.setCurrentIndex(cur_idx)
            
            def _on_signal_changed(idx):
                if idx >= 0 and hasattr(self, 'combo_signals'):
                    target_c = self.combo_signals.itemData(idx)
                    if target_c and str(target_c).strip() != str(self.code).strip():
                        target_text = self.combo_signals.itemText(idx)
                        parts = target_text.split(" ")
                        target_n = parts[1] if len(parts) > 1 else target_c
                        self.switch_to_code(target_c, target_n)
            
            def _on_prev_clicked():
                count = self.combo_signals.count()
                if count > 0:
                    c_idx = self.combo_signals.currentIndex()
                    next_idx = (c_idx - 1 + count) % count
                    self.combo_signals.setCurrentIndex(next_idx)
                    
            def _on_next_clicked():
                count = self.combo_signals.count()
                if count > 0:
                    c_idx = self.combo_signals.currentIndex()
                    next_idx = (c_idx + 1) % count
                    self.combo_signals.setCurrentIndex(next_idx)

            self.combo_signals.currentIndexChanged.connect(_on_signal_changed)
            self.btn_prev.clicked.connect(_on_prev_clicked)
            self.btn_next.clicked.connect(_on_next_clicked)
            
            nav_layout.addWidget(nav_label)
            nav_layout.addWidget(self.btn_prev)
            nav_layout.addWidget(self.combo_signals, 1)
            nav_layout.addWidget(self.btn_next)
            layout.addLayout(nav_layout)

        # 1. Title and header info
        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"📊 {code}  {name}")
        self.title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        self.price_pct_label = QLabel("--  (--)")
        self.price_pct_label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #8e8e93;")
        header_layout.addWidget(self.price_pct_label)
        header_layout.addSpacing(10)

        # 置顶复选框
        self.chk_on_top = QCheckBox("置顶")
        self.chk_on_top.setStyleSheet("""
            QCheckBox { color: #00FFCC; font-size: 9pt; font-weight: bold; }
            QCheckBox::indicator { width: 12px; height: 12px; }
        """)
        self.chk_on_top.setChecked(getattr(self, "stays_on_top", False))
        self.chk_on_top.stateChanged.connect(self._on_stays_on_top_toggled)
        header_layout.addWidget(self.chk_on_top)

        layout.addLayout(header_layout)
        
        # 1.5 Context Info Block (策略特征上下文)
        ctx_info_safe = context_info if context_info else {}
        ctx_group = QGroupBox("📍 策略特征上下文 (Context Info)")
        ctx_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #2e2e36;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #aad4ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """)
        ctx_layout = QGridLayout(ctx_group)
        ctx_layout.setContentsMargins(12, 18, 12, 12)
        ctx_layout.setSpacing(10)
        
        # Position
        lbl_pos_title = QLabel("触发位置:")
        lbl_pos_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
        self.lbl_pos_val = QLabel(ctx_info_safe.get('position', '--'))
        self.lbl_pos_val.setStyleSheet("color: #ffffff; font-weight: bold;")
        self.lbl_pos_val.setWordWrap(True)
        
        # Reason
        lbl_reason_title = QLabel("推荐理由:")
        lbl_reason_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
        self.lbl_reason_val = QLabel(ctx_info_safe.get('reason', '--'))
        self.lbl_reason_val.setStyleSheet("color: #ffaa44; font-weight: bold;")
        self.lbl_reason_val.setWordWrap(True)
        
        # Status
        lbl_status_title = QLabel("追涨/特征状态:")
        lbl_status_title.setStyleSheet("color: #8e8e93; font-weight: bold;")
        self.lbl_status_val = QLabel(ctx_info_safe.get('status', '--'))
        self.lbl_status_val.setStyleSheet("color: #00ff88; font-weight: bold;")
        self.lbl_status_val.setWordWrap(True)
        
        ctx_layout.addWidget(lbl_pos_title, 0, 0)
        ctx_layout.addWidget(self.lbl_pos_val, 0, 1)
        ctx_layout.addWidget(lbl_reason_title, 1, 0)
        ctx_layout.addWidget(self.lbl_reason_val, 1, 1)
        ctx_layout.addWidget(lbl_status_title, 2, 0)
        ctx_layout.addWidget(self.lbl_status_val, 2, 1)
        
        ctx_layout.setColumnStretch(1, 1)
        layout.addWidget(ctx_group)
            
        # 2. Source indicator
        self.hint_label = QLabel("⏳ 正在等待数据同步...")
        self.hint_label.setStyleSheet("color: #ff9900; font-size: 9.5pt; font-weight: bold;")
        layout.addWidget(self.hint_label)
        
        # 2.5 过滤公式匹配状态
        self.filter_status_layout = QHBoxLayout()
        self.lbl_filter_title = QLabel("🔍 过滤测试: ")
        self.lbl_filter_title.setStyleSheet("color: #aad4ff; font-weight: bold;")
        self.lbl_filter_expr = QLabel("无")
        self.lbl_filter_expr.setStyleSheet("color: #8e8e93; font-style: italic;")
        self.lbl_filter_result = QLabel("")
        self.lbl_filter_result.setStyleSheet("font-weight: bold;")
        
        self.filter_status_layout.addWidget(self.lbl_filter_title)
        self.filter_status_layout.addWidget(self.lbl_filter_expr)
        self.filter_status_layout.addStretch()
        self.filter_status_layout.addWidget(self.lbl_filter_result)
        layout.addLayout(self.filter_status_layout)
        
        # 3. Main feature table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["指标核心特征", "特征实盘数据值"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        # 绑定右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)
        
        # 4. Action buttons
        btn_sbc = QPushButton("📈 调出 SBC 分时走势")
        btn_sbc.setStyleSheet("""
            QPushButton {
                background-color: #1a2e22; color: #00ff88; font-weight: bold;
                border: 1px solid #00ff88; border-radius: 4px; padding: 4px 10px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #244633; }
        """)
        def _on_open_sbc_clicked():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, self.code)
        btn_sbc.clicked.connect(_on_open_sbc_clicked)

        btn_close = QPushButton("关闭窗口")
        btn_close.clicked.connect(self.accept)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(btn_sbc)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)
        layout.addLayout(bottom_layout)

    def _show_context_menu(self, pos):
        """个股详情弹窗右键菜单"""
        from PyQt6.QtWidgets import QMenu, QApplication
        from ats.ui.base_table import send_to_linkage
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
                color: #ffffff;
            }
        """)

        # 📈 调出 SBC 实盘分时走势
        sbc_act = menu.addAction(f"📈 调出 {self.name} SBC 实盘分时走势")
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, self.code)
        sbc_act.triggered.connect(_open_sbc)

        # ⚡ 发送到异动联动
        link_act = menu.addAction(f"⚡ 发送到异动联动 ({self.code})")
        link_act.triggered.connect(lambda: send_to_linkage(self.code, self.name, self))

        menu.addSeparator()
        copy_code = menu.addAction("📋 复制代码")
        copy_code.triggered.connect(lambda: QApplication.clipboard().setText(self.code))
        copy_name = menu.addAction("📋 复制名称")
        copy_name.triggered.connect(lambda: QApplication.clipboard().setText(self.name))

        sender = self.sender()
        map_widget = sender if isinstance(sender, QWidget) else self
        menu.exec(map_widget.mapToGlobal(pos))

    def update_data(self, df_row):
        t_u0 = time.perf_counter()
        self.df_row = df_row
        
        # 1. Update price pct header labels
        price_str = "--"
        pct_str = "--"
        color_hex = "#8e8e93"
        
        if df_row is not None:
            if hasattr(self, 'hint_label') and self.hint_label:
                self.hint_label.setText("🟢 已成功对接实盘行情快照核心特征:")
                self.hint_label.setStyleSheet("color: #00ff88; font-size: 9.5pt; font-weight: bold;")
            
            # Resolve price
            for p_col in ['close', 'trade', 'price']:
                if p_col in df_row and df_row[p_col] is not None and df_row[p_col] != '':
                    try:
                        price_str = f"{float(df_row[p_col]):.2f}"
                        break
                    except:
                        pass
            # Resolve percent
            if 'percent' in df_row and df_row['percent'] is not None and df_row['percent'] != '':
                try:
                    pct_val = float(df_row['percent'])
                    pct_str = f"{pct_val:+.2f}%"
                    if pct_val > 0:
                        color_hex = "#ff4444"
                    elif pct_val < 0:
                        color_hex = "#33cc5a"
                except:
                    pct_str = str(df_row['percent'])
                    if pct_str.startswith("+"):
                        color_hex = "#ff4444"
                    elif pct_str.startswith("-"):
                        color_hex = "#33cc5a"
        else:
            if hasattr(self, 'hint_label') and self.hint_label:
                self.hint_label.setText("⚠️ 暂无当前个股实盘快照特征数据（等待行情推送中）:")
                self.hint_label.setStyleSheet("color: #ff9900; font-size: 9.5pt; font-weight: bold;")
            
        if hasattr(self, 'price_pct_label') and self.price_pct_label:
            self.price_pct_label.setText(f"{price_str}  ({pct_str})")
            self.price_pct_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {color_hex};")
        
        t_u1 = time.perf_counter()
        # 1.5 动态补充更新顶部标题与窗口 title 上的 code + name + 涨跌幅
        if hasattr(self, 'title_label') and self.title_label:
            if pct_str != "--":
                self.title_label.setText(f"📊 {self.code}  {self.name}  ({pct_str})")
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name} ({pct_str})")
            else:
                self.title_label.setText(f"📊 {self.code}  {self.name}")
                self.setWindowTitle(f"📈 实时实盘个股详情 - {self.code} {self.name}")
        
        t_u2 = time.perf_counter()
        # 2. Update feature list
        features = []
        if df_row is not None:
            main_keys = {
                'percent': '今日涨幅 (%)',
                'close': '最新收盘价 (元)',
                'trade': '最新成交价 (元)',
                'open': '开盘价 (元)',
                'high': '最高价 (元)',
                'low': '最低价 (元)',
                'volume': '累计成交量 (手/股)',
                'amount': '累计成交额 (元)',
                'turnover': '换手率 (%)',
                'ratio': '量比',
                'vwap': '分时均价线 (VWAP)',
                'ma20': '20日移动平均 (MA20)',
                'category': '所属行业/概念板块',
                'strategy': '匹配筛选策略'
            }
            
            for k, label in main_keys.items():
                if k in df_row and df_row[k] is not None and df_row[k] != '':
                    val = df_row[k]
                    if isinstance(val, float):
                        if k in ('percent', 'pct_chg'):
                            val_str = f"{val:+.2f}%"
                        elif k in ('volume', 'amount') and val > 10000:
                            val_str = f"{val:,.2f}"
                        else:
                            val_str = f"{val:.2f}"
                    else:
                        val_str = str(val)
                    features.append((label, val_str))
                    
            extra_cnt = 0
            for k, val in df_row.items():
                if k not in main_keys and k not in ('code', 'name') and val is not None and val != '':
                    if extra_cnt >= 30:  # 🚀 [PERF] 严格限制 UI 控件特征数 (最多 30 个)，防止上千指标轰炸卡死 DOM
                        break
                    label = k.replace('_', ' ').title()
                    if isinstance(val, float):
                        val_str = f"{val:.4f}"
                    else:
                        val_str = str(val)
                    features.append((label, val_str))
                    extra_cnt += 1
        else:
            features.append(("证券代码", self.code))
            features.append(("证券名称", self.name))
            
        # Add trading kernel trace features if available
        if hasattr(self, 'kernel_info') and self.kernel_info:
            res = self.kernel_info.get("kernel_result", {})
            sig = self.kernel_info.get("signal", {})
            intent = self.kernel_info.get("intent", {})
            
            # Action
            action = res.get("kernel_action") or intent.get("action") or "HOLD"
            action_cn = "买入" if action == "BUY" else ("卖出" if action == "SELL" else "观察")
            features.append(("🤖 内核决策动作", action_cn))
            
            # Confidence
            conf = res.get("kernel_confidence") or intent.get("confidence") or 0.0
            conf_str = f"{conf:.2%}" if isinstance(conf, float) else str(conf)
            features.append(("🤖 内核决策置信度", conf_str))
            
            # State
            state = res.get("kernel_state") or "NORMAL"
            features.append(("🤖 内核运行状态", str(state)))
            
            # Reject code
            reject = res.get("kernel_reject_code")
            if reject:
                features.append(("🚫 风控阻断代码", str(reject)))
                
            # Signal Type
            sig_type = sig.get("signal_type") or ""
            if sig_type:
                features.append(("⚡ 触发信号类型", str(sig_type)))
                
            # Reason
            reason = sig.get("features", {}).get("raw_reason") or intent.get("reason", {}).get("raw_reason") or ""
            if not reason and intent.get("reason"):
                reason = str(intent.get("reason"))
            if reason:
                features.append(("💡 内核决策依据", str(reason)))
                
            # Timestamp
            ts = self.kernel_info.get("journal_ts") or self.kernel_info.get("timestamp") or ""
            if ts:
                features.append(("📅 内核评估时间", str(ts).replace("T", " ")))
                
        if len(features) <= 2:
            features = [
                ("证券代码", self.code),
                ("证券名称", self.name),
                ("日内价格", "加载中..."),
                ("实盘状态", "等待主进程推送行情"),
                ("说明", "双击可实现实盘特征一屏清，当前暂未收到主进程行情推送")
            ]
            
        t_u3 = time.perf_counter()
        if not hasattr(self, 'table') or self.table is None:
            return
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(features))
            for row, (lbl, val) in enumerate(features):
                item_lbl = QTableWidgetItem(lbl)
                item_lbl.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, 0, item_lbl)
                
                item_val = QTableWidgetItem(val)
                item_val.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if "涨幅" in lbl or "Percent" in lbl:
                    if val.startswith("+"):
                        item_val.setForeground(QColor("#ff4444"))
                    elif val.startswith("-"):
                        item_val.setForeground(QColor("#33cc5a"))
                self.table.setItem(row, 1, item_val)
        finally:
            self.table.setUpdatesEnabled(True)
            
        t_u4 = time.perf_counter()
        # 3. 同步刷新下拉框中所有股票的最新涨跌幅
        self._refresh_combo_signals_pct()
        
        t_u5 = time.perf_counter()
        # 4. Update filter evaluation
        self.update_filter_status()
        
        t_u6 = time.perf_counter()
        import sys
        is_debug_log = ("-log" in sys.argv and "debug" in sys.argv) or (logger.getEffectiveLevel() <= logging.DEBUG)
        if is_debug_log:
            print(
                f"[PERF-BREAKDOWN] update_data({self.code}): total={(t_u6-t_u0)*1000:.2f}ms | "
                f"hdr={(t_u1-t_u0)*1000:.2f}ms | title={(t_u2-t_u1)*1000:.2f}ms | feat_build={(t_u3-t_u2)*1000:.2f}ms | "
                f"tbl_render={(t_u4-t_u3)*1000:.2f}ms | combo_pct={(t_u5-t_u4)*1000:.2f}ms | filter_status={(t_u6-t_u5)*1000:.2f}ms"
            )

    def _get_pct_str_for_code(self, parent_mw, code):
        if not parent_mw:
            return ""
        c_clean = str(code).strip().zfill(6)
        df_row = None
        for attr in ("current_df", "df_realtime"):
            if hasattr(parent_mw, attr):
                df = getattr(parent_mw, attr)
                if df is not None and not df.empty:
                    if c_clean in df.index:
                        row = df.loc[c_clean]
                        df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                        break
        
        if df_row and 'percent' in df_row and df_row['percent'] is not None and df_row['percent'] != '':
            try:
                p_val = float(df_row['percent'])
                return f" ({p_val:+.2f}%)"
            except Exception:
                pass
        return ""

    def _refresh_combo_signals_pct(self):
        """同步刷新下拉框 combo_signals 中每一项的涨跌幅文本后缀 (0毫秒极速字典查找)"""
        if not hasattr(self, 'combo_signals') or self.combo_signals is None:
            return
        
        parent_mw = self._get_parent_mw()
        if not parent_mw:
            return

        # 1. 一次性向量化提取全量代码->涨跌幅字典 (耗时 0.01ms，替代 M*N 循环扫描)
        pct_map = {}
        for attr in ("current_df", "df_realtime"):
            if hasattr(parent_mw, attr):
                df = getattr(parent_mw, attr)
                if df is not None and not df.empty and 'percent' in df.columns:
                    try:
                        if 'code' in df.columns:
                            pct_map.update(dict(zip(df['code'].astype(str).str.strip().str.zfill(6), df['percent'])))
                        else:
                            pct_map.update(dict(zip(df.index.astype(str).str.strip().str.zfill(6), df['percent'])))
                    except Exception:
                        pass
        
        if not pct_map:
            return

        # 2. 下拉框极速 O(1) 字典查表匹配
        self.combo_signals.blockSignals(True)
        try:
            for idx in range(self.combo_signals.count()):
                c = self.combo_signals.itemData(idx)
                if not c:
                    continue
                c_str = str(c).strip().zfill(6)
                p_val = pct_map.get(c_str)
                pct_lbl = ""
                if p_val is not None and p_val != '':
                    try:
                        pct_lbl = f" ({float(p_val):+.2f}%)"
                    except Exception:
                        pass
                
                cur_text = self.combo_signals.itemText(idx)
                if pct_lbl and not cur_text.endswith(pct_lbl):
                    # 仅在文本变动时才调用 setItemText
                    parts = cur_text.split(" ")
                    c_part = parts[0] if len(parts) > 0 else c_str
                    n_part = parts[1] if len(parts) > 1 else ""
                    # 剥离旧括号
                    if "(" in n_part and ")" in n_part:
                        n_part = n_part.split("(")[0]
                    new_text = f"{c_part} {n_part}{pct_lbl}".strip()
                    if cur_text != new_text:
                        self.combo_signals.setItemText(idx, new_text)
        finally:
            self.combo_signals.blockSignals(False)

    def update_filter_status(self, query_expr=None):
        parent_mw = self._get_parent_mw()
        if query_expr is None:
            if parent_mw and hasattr(parent_mw, 'query_expr'):
                query_expr = parent_mw.query_expr
            else:
                query_expr = ""
                
        self.query_expr = query_expr
        if not query_expr:
            self.lbl_filter_expr.setText("无")
            self.lbl_filter_expr.setStyleSheet("color: #8e8e93; font-style: italic;")
            self.lbl_filter_result.setText("")
            return
            
        disp_expr = query_expr
        if len(disp_expr) > 40:
            disp_expr = disp_expr[:37] + "..."
        self.lbl_filter_expr.setText(disp_expr)
        self.lbl_filter_expr.setStyleSheet("color: #e2e2e5; font-style: normal;")
        
        # 🚀【极速 O(1) 6位清洗容错匹配】如果主窗口当前过滤集合已有预计算结果，0 毫秒确认命中
        c_clean = str(self.code).strip().zfill(6)
        
        if parent_mw and hasattr(parent_mw, "filtered_codes_set") and parent_mw.filtered_codes_set is not None and len(parent_mw.filtered_codes_set) > 0:
            if getattr(parent_mw, "query_expr", "") == query_expr:
                if any(str(x).strip().zfill(6) == c_clean for x in parent_mw.filtered_codes_set):
                    self.lbl_filter_result.setText("✅ 命中")
                    self.lbl_filter_result.setStyleSheet("color: #00ff88; font-weight: bold;")
                    return
                else:
                    self.lbl_filter_result.setText("❌ 未命中")
                    self.lbl_filter_result.setStyleSheet("color: #ff4444; font-weight: bold;")
                    return

        import pandas as pd
        df_code = None
        if parent_mw and hasattr(parent_mw, "current_df") and parent_mw.current_df is not None and not parent_mw.current_df.empty:
            df_cur = parent_mw.current_df
            if 'code' in df_cur.columns:
                sub = df_cur[df_cur['code'].astype(str).str.strip().str.zfill(6) == c_clean]
                if not sub.empty:
                    df_code = sub.copy()
            elif (df_cur.index.astype(str).str.strip().str.zfill(6) == c_clean).any():
                sub = df_cur[df_cur.index.astype(str).str.strip().str.zfill(6) == c_clean]
                if not sub.empty:
                    df_code = sub.copy()

        if df_code is None or df_code.empty:
            if self.df_row is None:
                self.lbl_filter_result.setText("⏳ 等待数据...")
                self.lbl_filter_result.setStyleSheet("color: #ff9900; font-weight: bold;")
                return
            row_dict = self.df_row.to_dict() if hasattr(self.df_row, 'to_dict') else dict(self.df_row)
            row_dict['code'] = self.code
            row_dict['name'] = self.name
            
            mapping = {
                '价格': 'close', '最新价': 'close', '现价': 'close', 
                '涨幅': 'pct', 
                '量': 'volume', '成交量': 'volume',
                '成交额': 'turnover',
                '最高': 'high', '最低': 'low', '开盘': 'open',
                '板块': 'category', '异动类型': 'category', 'hy': 'category'
            }
            for cn, en in mapping.items():
                if cn in row_dict and en not in row_dict:
                    row_dict[en] = row_dict[cn]
                    
            if 'close' in row_dict:
                for col in ['open', 'high', 'low']:
                    if col not in row_dict or row_dict[col] is None or row_dict[col] == '':
                        row_dict[col] = row_dict['close']
                        
            df_code = pd.DataFrame([row_dict])
            df_code.set_index('code', inplace=True, drop=False)
        
        from stock_logic_utils import test_code_against_queries
        try:
            res = test_code_against_queries(df_code, [{"query": query_expr}])
            hit = res[0].get("hit", 0) if res else 0
            if hit > 0:
                self.lbl_filter_result.setText("✅ 命中")
                self.lbl_filter_result.setStyleSheet("color: #00ff88; font-weight: bold;")
            else:
                self.lbl_filter_result.setText("❌ 未命中")
                self.lbl_filter_result.setStyleSheet("color: #ff4444; font-weight: bold;")
        except Exception as e:
            self.lbl_filter_result.setText("⚠️ 评估出错")
            self.lbl_filter_result.setStyleSheet("color: #ff9900; font-weight: bold;")

    def start_slide_animation(self, target_rect, target_opacity, duration=250, is_snap_feedback=False):
        """
        统一的滑动与透明度动画控制器，提供流畅的 QQ 窗口滑动和呼吸反馈效果
        """
        if hasattr(self, 'anim_group') and self.anim_group is not None:
            try:
                if self.anim_group.state() == QParallelAnimationGroup.State.Running:
                    self.anim_group.stop()
            except Exception:
                pass
                
        self.anim_group = QParallelAnimationGroup(self)
        
        # 1. 窗口位置大小动画 (Geometry)
        self.geom_anim = QPropertyAnimation(self, b"geometry")
        self.geom_anim.setDuration(duration)
        self.geom_anim.setStartValue(self.geometry())
        self.geom_anim.setEndValue(target_rect)
        if is_snap_feedback:
            # 磁吸成功时采用微弹插值，让贴边动作更具弹性物理质感
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        else:
            self.geom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            
        # 2. 窗口不透明度动画 (Opacity)
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(duration)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(target_opacity)
        if is_snap_feedback:
            # 磁吸动态提示：透明度从 1.0 快速淡化到 0.4 左右再恢复，模拟“吸附上”的视觉脉冲
            self.opacity_anim.setKeyValueAt(0.5, 0.4)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        self.anim_group.addAnimation(self.geom_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        
        self._in_snap_action = True
        
        def on_finished():
            self._in_snap_action = False
            # 动画结束时做状态对齐安全保护
            if self.is_hidden_state:
                self.setWindowOpacity(0.35)
            else:
                self.setWindowOpacity(1.0)
                
        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        # 【置顶与磁吸严格互斥】：置顶状态下完全禁用磁吸贴边功能，保持自由悬浮置顶
        if getattr(self, "stays_on_top", False) or getattr(self, "is_hidden_state", False):
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start()
            return
            
        screen = self.screen()
        if not screen:
            screen = QApplication.primaryScreen()
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35  # 磁吸检测门槛像素
        
        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()
        
        # 排除底边（即任务栏所在方向，通常不磁吸底边）。我们磁吸顶边、左边、右边。
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
            
            # 使用带有呼吸闪烁反馈的滑动动画平滑移动到磁吸位置
            self.start_slide_animation(self.normal_geometry, 1.0, duration=250, is_snap_feedback=True)
        else:
            self.anchor_edge = None
            self.normal_geometry = None

    def hide_to_edge(self):
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止折叠隐藏
        if getattr(self, "stays_on_top", False):
            return
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
        
        strip_size = 5  # 隐藏后在屏幕内留出的极窄感应/观察条像素宽度
        
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
        # 启动滑入贴边隐藏的平滑过渡动画
        self.start_slide_animation(QRect(target_x, target_y, w, h), 0.35, duration=300)

    def show_normal_position(self):
        if getattr(self, "is_hidden_state", False):
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            self.is_hidden_state = False
            import time
            self._last_show_time = time.time()
            self._has_hovered_since_show = False
            if self.normal_geometry:
                self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
            self.setWindowOpacity(1.0)
        else:
            self.setWindowOpacity(1.0)
        
        self.show()
        self.raise_()
        self.activateWindow()

    def _check_hover(self):
        # 【置顶与磁吸严格互斥】：置顶状态下不执行任何贴边或离开折叠检测
        if not self.isVisible() or getattr(self, "stays_on_top", False):
            return
            
        # 仅在有贴边锚定边缘或处于贴边隐藏状态时才执行悬浮检测，其余时刻 0 开销
        if not self.anchor_edge and not self.is_hidden_state:
            return
            
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
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
                if self.hover_ticks >= 2:  # 100ms * 2 = 200ms 停留防误触
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
                    import time
                    if time.time() - getattr(self, '_last_show_time', 0.0) < 1.2:
                        self.leave_ticks = 0
                        return
                        
                    self.leave_ticks += 1
                    if self.leave_ticks >= 4:  # 100ms * 4 = 400ms 离开防抖
                        self.hide_to_edge()
                        self.leave_ticks = 0
                else:
                    self.leave_ticks = 0

    def moveEvent(self, event):
        super().moveEvent(event)
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止触发磁吸贴边
        if getattr(self, "stays_on_top", False):
            if hasattr(self, "snap_timer") and self.snap_timer is not None:
                try:
                    self.snap_timer.stop()
                except Exception:
                    pass
            self.anchor_edge = None
            self.normal_geometry = None
            return
        if not getattr(self, "is_hidden_state", False) and not getattr(self, "_in_snap_action", False):
            self._is_dragging = True
            # 拖拽时立即重置磁吸边缘，避免拖动过程中鼠标离开导致的强行缩回
            self.anchor_edge = None
            if hasattr(self, "snap_timer") and self.snap_timer is not None:
                try:
                    self.snap_timer.start()
                except Exception:
                    pass
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not getattr(self, "is_hidden_state", False) and not getattr(self, "_in_snap_action", False):
            if self.anchor_edge:
                self.normal_geometry = self.geometry()
                
    def closeEvent(self, event):
        if hasattr(self, "hover_timer") and self.hover_timer is not None:
            try:
                self.hover_timer.stop()
            except Exception:
                pass
        if hasattr(self, "snap_timer") and self.snap_timer is not None:
            try:
                self.snap_timer.stop()
            except Exception:
                pass
        self._save_geometry()
        parent_mw = self._get_parent_mw()
        if parent_mw and hasattr(parent_mw, '_detail_dialog') and parent_mw._detail_dialog is self:
            parent_mw._detail_dialog = None
        super().closeEvent(event)
        
    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

class ATSMainWindow(QMainWindow):
    realtime_data_signal = pyqtSignal(object)
    realtime_signal_signal = pyqtSignal(object)
    db_data_loaded_signal = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        if app:
            app.main_window = self
        self.db_data_loaded_signal.connect(self._on_db_data_loaded)
        self.setWindowTitle("🛡️ ATS v2 智能自治股票交易终端 (Autonomous Trading Terminal)")
        self.resize(1440, 900)
        self.current_font_size = self.load_font_size()
        self.apply_qss_with_font_size(self.current_font_size)
        self.current_df = None  # Live streaming DataFrame snapshot data source
        self._listener_started = False
        self.name_cache = {}  # Global name cache to prevent "未知" names
        self.price_pct_cache = {}  # Cache for price and percent when current_df is empty/missing
        
        self.universe_manager = UniverseManager()
        self.swing_tracker = SwingTracker()
        from ats.signal_ledger import get_signal_ledger
        self.signal_ledger = get_signal_ledger()
        self.volume_profiler = VolumeProfiler()
        self.session_snapshot = SessionSnapshot()
        import threading
        self.hdf5_history_lock = threading.Lock()
        
        # 通达信 / OrderMon 信号文件后台监听器
        try:
            from ats.tdx_signal_watcher import TdxSignalWatcher
            self.tdx_watcher = TdxSignalWatcher(parent=self)
            self.tdx_watcher.signal_detected.connect(self._on_tdx_signal_detected)
            self.tdx_watcher.start()
        except Exception as e:
            print(f"[ATSMainWindow] 初始化 TdxSignalWatcher 异常: {e}")

        self.ladder_watcher = None

        # 自动加载昨日快照，恢复跨日 WATCH/TRADE 精选标的以实现跨日持续跟进
        try:
            prev_signals = self.session_snapshot.load_previous_day_signals()
            if prev_signals:
                self.signal_ledger.load_previous_signals(prev_signals)
        except Exception as e:
            print(f"[MainWindow] 跨日快照加载异常: {e}")
        self.stock_history_cache = {}
        self.dragon_monitor_dialog = None
        self.hot_sector_dialog = None
        self.daily_limit_up_dialog = None
        self.history_loading_codes = set()
        # Changed from a simple set to a {code: fail_timestamp} dict.
        # Codes that failed will be retried after 5 minutes, and the entire
        # blacklist is reset at the start of a new calendar day so that
        # next-day ATS startup always re-attempts history loading.
        self.history_failed_codes = {}   # {code: fail_time (float unix ts)}
        self._history_failed_date = None  # tracks the date when failures were recorded
        self.prices_loading_codes = set()
        self.prices_failed_codes = set()
        self._is_closing = False
        
        # 🛡️【批处理防抖队列与定时器】：防止零散多次触发并发开闭 HDF5 / Sina API 引起的刷屏与界面卡顿
        self._pending_price_codes = set()
        self._pending_history_codes = set()
        
        self._batch_price_timer = QTimer(self)
        self._batch_price_timer.setSingleShot(True)
        self._batch_price_timer.timeout.connect(self._flush_batch_stock_prices)
        
        self._batch_history_timer = QTimer(self)
        self._batch_history_timer.setSingleShot(True)
        self._batch_history_timer.timeout.connect(self._flush_batch_stock_history)
        
        # Initialize ratios for equal proportional scaling
        self._main_ratio = [0.24, 0.49, 0.27]
        self._center_ratio = [0.5, 0.5]
        self._right_ratio = [0.5, 0.5]
        self._is_restoring_sizes = False
        
        # Connect thread-safe PyQt signals
        self.realtime_data_signal.connect(self._handle_realtime_data)
        self.realtime_signal_signal.connect(self._handle_realtime_signal)
        
        # Initialize favorites version-tracking and start polling loop
        try:
            from global_favorites import GlobalFavoriteManager
            self._last_favorites_version = GlobalFavoriteManager().version
        except Exception:
            self._last_favorites_version = 0

        self._favorites_poll_timer = QTimer(self)
        self._favorites_poll_timer.setInterval(500)
        self._favorites_poll_timer.timeout.connect(self._poll_favorites_loop)
        self._favorites_poll_timer.start()
        
        # 初始化过滤公式表达式和搜索历史数据缓存 (History Filter Integration)
        self.query_expr = ""
        self.search_histories = {"history1": [], "history2": [], "history3": [], "history4": [], "history5": []}
        self._load_search_history_data()
        
        # 读取后台自动刷新状态持久化配置 (默认 False，被动等待 TK 主进程自动推送 IPC)
        settings = QSettings("pyQuant", "ATSMainWindow")
        self.is_auto_refresh_enabled = settings.value("auto_refresh_enabled", False, type=bool)

        # 读取通道测算最后使用的周期 (默认 60f)
        saved_period = load_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, "60f")
        self.channel_scan_period = str(saved_period).strip() if saved_period else "60f"

        self._init_toolbar()
        self._init_ui()
        self._restore_layout_state()
        self._init_statusbar()
        
        # Prepopulate name cache from database history on startup
        self._prepopulate_name_cache()
        
        # Load SQLite database data (P1 Integration)
        self.load_db_data(force=True)
        
        # Setup simple timer for ticker updating (当用户开启后台自动刷新时才运行)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.on_heartbeat)
        if self.is_auto_refresh_enabled:
            self.update_timer.start(60000)

    def _prepopulate_name_cache(self):
        self.name_cache = {}
        try:
            from ats.ipc_bridge import IPCBridge
            bridge = IPCBridge()
            queries = [
                "SELECT DISTINCT code, name FROM signal_history WHERE name IS NOT NULL AND name != ''",
                "SELECT DISTINCT code, name FROM trade_records WHERE name IS NOT NULL AND name != ''"
            ]
            for query in queries:
                try:
                    with bridge.db_manager.execute_query(query) as cursor:
                        for row in cursor.fetchall():
                            c = str(row[0]).strip()
                            n = str(row[1]).strip()
                            if c and n:
                                self.name_cache[c] = n
                except Exception as e:
                    print(f"[ATSMainWindow] Prepopulate cache query failed: {e}")
        except Exception as e:
            print(f"[ATSMainWindow] Prepopulate cache failed: {e}")

        # 尝试初始化全系统标准的 StockSender 通道 (动态绑定 UI checkbox 勾选与持久化状态)
        self.sender = None
        try:
            from JohnsonUtil.stock_sender import StockSender
            self.sender = StockSender(
                tdx_var=QtVarProxy(lambda: self.cb_tdx.isChecked() if hasattr(self, 'cb_tdx') else True),
                ths_var=QtVarProxy(lambda: self.cb_ths.isChecked() if hasattr(self, 'cb_ths') else True),
                dfcf_var=False,
                callback=None
            )
        except Exception as e:
            print(f"[ATSMainWindow] Init standard StockSender failed: {e}")



    def _get_search_history_filepath(self):
        try:
            from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
            return SEARCH_HISTORY_FILE
        except ImportError:
            import os
            from sys_utils import get_app_root
            return os.path.join(get_app_root(), "datacsv", "search_history.json")

    def _load_search_history_data(self):
        import os
        filepath = self._get_search_history_filepath()
        h1, h2, h3, h4, h5 = [], [], [], [], []
        self.last_query = ""
        self.last_group = "history5"
        if os.path.exists(filepath):
            try:
                import json
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                def _normalize_record(r):
                    hit = ""
                    if isinstance(r, dict):
                        q = r.get("query", "")
                        try:
                            q_dict = eval(q)
                            if isinstance(q_dict, dict) and "query" in q_dict:
                                q = q_dict["query"]
                        except:
                            pass
                        note = r.get("note", "")
                        starred = r.get("starred", 0)
                        hit = r.get("hit", "")
                    elif isinstance(r, str):
                        q = r
                        note = ""
                        starred = 0
                    else:
                        q = str(r)
                        note = ""
                        starred = 0
                    
                    q = q.strip()
                    note = note.strip()
                    if isinstance(starred, bool):
                        starred = 1 if starred else 0
                    elif not isinstance(starred, int):
                        starred = 0
                    res_dict = {"query": q, "starred": starred, "note": note}
                    if hit != "" and hit is not None:
                        res_dict["hit"] = hit
                    return res_dict
                
                h1 = [_normalize_record(r) for r in data.get("history1", [])]
                h2 = [_normalize_record(r) for r in data.get("history2", [])]
                h3 = [_normalize_record(r) for r in data.get("history3", [])]
                h4 = [_normalize_record(r) for r in data.get("history4", [])]
                h5 = [_normalize_record(r) for r in data.get("history5", [])]
                self.last_query = data.get("last_query", "")
                self.last_group = data.get("last_group", "history5")
            except Exception as e:
                print(f"[ATSMainWindow] Direct history load failed: {e}")
        
        self.search_histories = {
            "history1": h1,
            "history2": h2,
            "history3": h3,
            "history4": h4,
            "history5": h5
        }

    def _save_search_history_data(self):
        """将当前 search_histories 包含 query, note, starred, hit 原子落盘保存至 search_history.json"""
        import os
        import json
        from ats.ui.styles import CONFIG_FILE_LOCK
        filepath = self._get_search_history_filepath()
        if not filepath:
            return
        try:
            with CONFIG_FILE_LOCK:
                cur_real_q = self._get_real_query() if hasattr(self, '_get_real_query') else ""
                last_q_to_save = cur_real_q if cur_real_q else getattr(self, "last_query", "")
                self.last_query = last_q_to_save
                
                data = {
                    "history1": self.search_histories.get("history1", []),
                    "history2": self.search_histories.get("history2", []),
                    "history3": self.search_histories.get("history3", []),
                    "history4": self.search_histories.get("history4", []),
                    "history5": self.search_histories.get("history5", []),
                    "last_query": last_q_to_save,
                    "last_group": self.history_selector.currentText() if hasattr(self, 'history_selector') else "history5"
                }
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ATSMainWindow] Save search history failed: {e}")

        # 逐级异步 UI 刷新定时器 (Staggered Async Tier Timers for zero UI freezing)
        self._async_tier2_timer = QTimer(self)
        self._async_tier2_timer.setSingleShot(True)
        self._async_tier2_timer.timeout.connect(self._async_refresh_tier2)

        self._async_tier3_timer = QTimer(self)
        self._async_tier3_timer.setSingleShot(True)
        self._async_tier3_timer.timeout.connect(self._async_refresh_tier3)
        
        self._pending_swing_rows = []
        self._pending_fav_rows = []
        self._pending_sh_pct = 0.0

    def _init_toolbar(self):
        toolbar = QToolBar("Main Controls")
        self.addToolBar(toolbar)
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar { spacing: 2px; padding: 1px 2px; }
            QToolBar::separator { width: 1px; background-color: #383842; margin: 2px 2px; }
        """)
        
        self.btn_toggle_rotation = QPushButton("▶24x7")
        self.btn_toggle_rotation.setToolTip("启动/停止 24x7 自动过滤、信号评估与大级别历史回测轮转引擎")
        self.btn_toggle_rotation.setStyleSheet("QPushButton { background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 3px; padding: 1px 5px; font-size: 8.5pt; } QPushButton:hover { background-color: #00ff88; color: #000; }")
        self.btn_toggle_rotation.clicked.connect(self.toggle_rotation)
        toolbar.addWidget(self.btn_toggle_rotation)
        
        self.btn_multi_period = QPushButton("多周期🎯")
        self.btn_multi_period.setStyleSheet("QPushButton { background-color: #2b1f3c; color: #e0b0ff; font-weight: bold; border: 1px solid #c8a2c8; border-radius: 3px; padding: 1px 4px; font-size: 8.5pt; } QPushButton:hover { background-color: #3d2f54; border-color: #e0b0ff; }")
        self.btn_multi_period.clicked.connect(self.open_multi_period_tester)
        toolbar.addWidget(self.btn_multi_period)

        self.btn_global_market = QPushButton("外盘🌐")
        self.btn_global_market.setStyleSheet("QPushButton { background-color: #1e3a5f; color: #00e5ff; font-weight: bold; border: 1px solid #00e5ff; border-radius: 3px; padding: 1px 4px; font-size: 8.5pt; } QPushButton:hover { background-color: #00e5ff; color: #000; }")
        self.btn_global_market.clicked.connect(self.open_global_market_dialog)
        toolbar.addWidget(self.btn_global_market)

        self.btn_intraday_strategy = QPushButton("阶梯⚡")
        self.btn_intraday_strategy.setToolTip("打开分时阶梯策略独立盯盘窗口、7节点动态评分与实盘策略系统 (完全独立非模态运行)")
        self.btn_intraday_strategy.setStyleSheet("QPushButton { background-color: #381e1e; color: #ffaa44; font-weight: bold; border: 1px solid #ffaa44; border-radius: 3px; padding: 1px 4px; font-size: 8.5pt; } QPushButton:hover { background-color: #ffaa44; color: #000; }")
        self.btn_intraday_strategy.clicked.connect(self.open_intraday_strategy_dialog)
        toolbar.addWidget(self.btn_intraday_strategy)

        self.btn_limit_up_ladder = QPushButton("天梯🔥")
        self.btn_limit_up_ladder.setToolTip("打开每日涨停个股分析、封单比/量能比统计、多日强势股聚合与天梯看板 (完全独立非模态运行)")
        self.btn_limit_up_ladder.setStyleSheet("QPushButton { background-color: #3d1414; color: #ff5555; font-weight: bold; border: 1px solid #ff4444; border-radius: 3px; padding: 1px 4px; font-size: 8.5pt; } QPushButton:hover { background-color: #ff4444; color: #000; }")
        self.btn_limit_up_ladder.clicked.connect(self.open_daily_limit_up_analyzer)
        toolbar.addWidget(self.btn_limit_up_ladder)
        
        toolbar.addSeparator()

        # 🔄 后台自动刷新开关 (默认 False，被动等待 TK 自动推送 IPC)
        self.chk_auto_refresh = QCheckBox("自动🔄")
        self.chk_auto_refresh.setToolTip("开启/关闭后台自动刷新轮询 (默认关闭，被动等待主进程 TK 自动推送 IPC 数据；勾选后开启主动轮询)")
        self.chk_auto_refresh.setChecked(self.is_auto_refresh_enabled)
        self.chk_auto_refresh.setStyleSheet("QCheckBox { color: #ffaa44; font-weight: bold; font-size: 8.5pt; padding: 0px 2px; } QCheckBox::indicator { width: 11px; height: 11px; }")
        self.chk_auto_refresh.toggled.connect(self._on_auto_refresh_toggled)
        toolbar.addWidget(self.chk_auto_refresh)
        
        toolbar.addSeparator()
        
        self.lbl_ipc_status = QLabel("🔌IPC")
        self.lbl_ipc_status.setToolTip("IPC 通道: 🔌 已连接 (实时行情数据流已就绪)")
        self.lbl_ipc_status.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 8.5pt; padding: 0 1px;")
        toolbar.addWidget(self.lbl_ipc_status)
        
        self.lbl_db_status = QLabel("🗄️DB")
        self.lbl_db_status.setToolTip("数据库: 🗄️ 已加载 (本地历史数据池)")
        self.lbl_db_status.setStyleSheet("color: #aad4ff; font-weight: bold; font-size: 8.5pt; padding: 0 1px;")
        toolbar.addWidget(self.lbl_db_status)

        self.lbl_rotator_status = QLabel("⏸️")
        self.lbl_rotator_status.setToolTip("旋转引擎: ⏸️ 已暂停 (点击 '▶ 24x7' 启动轮转)")
        self.lbl_rotator_status.setStyleSheet("color: #ff9900; font-weight: bold; font-size: 8.5pt; padding: 0 1px;")
        toolbar.addWidget(self.lbl_rotator_status)
        
        toolbar.addSeparator()
        
        btn_font_dec = QPushButton("A-")
        btn_font_dec.setToolTip("减小字号 (Font Size Down)")
        btn_font_dec.setStyleSheet("min-width: 18px; max-width: 22px; background-color: #2e2e36; color: #e2e2e5; font-weight: bold; border: 1px solid #44444f; font-size: 8pt; padding: 0px;")
        btn_font_dec.clicked.connect(self.decrease_font_size)
        toolbar.addWidget(btn_font_dec)
        
        self.lbl_font_size = QLabel(f"{self.current_font_size}pt")
        self.lbl_font_size.setStyleSheet("color: #aad4ff; font-weight: bold; font-size: 8.5pt; padding: 0 1px;")
        toolbar.addWidget(self.lbl_font_size)
        
        btn_font_inc = QPushButton("A+")
        btn_font_inc.setToolTip("增大字号 (Font Size Up)")
        btn_font_inc.setStyleSheet("min-width: 18px; max-width: 22px; background-color: #2e2e36; color: #e2e2e5; font-weight: bold; border: 1px solid #44444f; font-size: 8pt; padding: 0px;")
        btn_font_inc.clicked.connect(self.increase_font_size)
        toolbar.addWidget(btn_font_inc)

        toolbar.addSeparator()
        
        lbl_link = QLabel("🔗")
        lbl_link.setToolTip("多端行情联动控制开关 (勾选后主窗切换联动对应行情软件)")
        lbl_link.setStyleSheet("color: #aad4ff; font-weight: bold; font-size: 8.5pt;")
        toolbar.addWidget(lbl_link)
        
        self.cb_tdx = QCheckBox("TDX")
        self.cb_tdx.setChecked(True)
        self.cb_tdx.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; font-size: 8.5pt; margin-left: 1px; margin-right: 1px; } QCheckBox::indicator { width: 11px; height: 11px; }")
        self.cb_tdx.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_tdx)
        
        self.cb_ths = QCheckBox("THS")
        self.cb_ths.setChecked(True)
        self.cb_ths.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; font-size: 8.5pt; margin-left: 1px; margin-right: 1px; } QCheckBox::indicator { width: 11px; height: 11px; }")
        self.cb_ths.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_ths)
        
        self.cb_vis = QCheckBox("VIS")
        self.cb_vis.setChecked(True)
        self.cb_vis.setStyleSheet("QCheckBox { color: #00ff88; font-weight: bold; font-size: 8.5pt; margin-left: 1px; margin-right: 1px; } QCheckBox::indicator { width: 11px; height: 11px; }")
        self.cb_vis.toggled.connect(lambda state: self._save_layout_state())
        toolbar.addWidget(self.cb_vis)
        
        self.cb_ladder = QCheckBox("天梯")
        self.cb_ladder.setToolTip("开启【连板天梯 / 涨停采集工具】上下键/选行与通达信无缝联动 (0% CPU 后台守护)")
        self.cb_ladder.setChecked(True)
        self.cb_ladder.setStyleSheet("QCheckBox { color: #ffaa44; font-weight: bold; font-size: 8.5pt; margin-left: 1px; margin-right: 1px; } QCheckBox::indicator { width: 11px; height: 11px; }")
        self.cb_ladder.toggled.connect(self._on_ladder_link_toggled)
        toolbar.addWidget(self.cb_ladder)
        
        toolbar.addSeparator()
        
        self.history_selector = QComboBox()
        self.history_selector.addItems(["history1", "history2", "history3", "history4", "history5"])
        self.history_selector.setCurrentText(getattr(self, "last_group", "history5"))
        self.history_selector.setStyleSheet("QComboBox { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; min-width: 56px; max-width: 62px; font-size: 8.5pt; padding: 1px 1px; }")
        self.history_selector.currentTextChanged.connect(self._on_history_group_changed)
        toolbar.addWidget(self.history_selector)
                
        lbl_filter = QLabel("🔍")
        lbl_filter.setToolTip("公式过滤引擎 (输入 Query 表达式过滤当前监控列表)")
        lbl_filter.setStyleSheet("color: #aad4ff; font-weight: bold; font-size: 9pt; padding: 0 1px;")
        toolbar.addWidget(lbl_filter)
        
        self.query_combo = QComboBox()
        self.query_combo.setEditable(True)
        self.query_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.query_combo.setStyleSheet("QComboBox { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; min-width: 75px; max-width: 260px; font-size: 8.5pt; padding: 1px 2px; } QComboBox:focus { border: 1px solid #00ffcc; }")
        self.query_combo.view().setMinimumWidth(450) # 展开下拉菜单时，宽度自适应为最少 450px，防止长公式截断
        self.query_combo.lineEdit().returnPressed.connect(self.apply_filter)
        self.query_combo.currentIndexChanged.connect(self.apply_filter)
        toolbar.addWidget(self.query_combo)
        
        self.btn_filter = QPushButton("过滤")
        self.btn_filter.setToolTip("执行当前公式过滤 (Enter 亦可触发)")
        self.btn_filter.setStyleSheet("QPushButton { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; padding: 1px 4px; min-width: 26px; font-size: 8.5pt; } QPushButton:hover { background-color: #3e3e4a; border-color: #aad4ff; }")
        self.btn_filter.clicked.connect(self.apply_filter)
        toolbar.addWidget(self.btn_filter)
        
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setToolTip("清空过滤条件，恢复展示当前组全部个股")
        self.btn_clear.setStyleSheet("QPushButton { background-color: #2e2e36; color: #ffffff; border: 1px solid #44444f; border-radius: 3px; padding: 1px 4px; min-width: 26px; font-size: 8.5pt; } QPushButton:hover { background-color: #3e3e4a; border-color: #ff4444; }")
        self.btn_clear.clicked.connect(self.clear_filter)
        toolbar.addWidget(self.btn_clear)

        self.btn_hit = QPushButton("Hit")
        self.btn_hit.setToolTip("计算当前组所有历史公式的命中数")
        self.btn_hit.setStyleSheet("QPushButton { background-color: #fff9c4; color: #000000; font-weight: bold; border: 1px solid #ffeb3b; border-radius: 3px; padding: 1px 3px; min-width: 20px; font-size: 8.5pt; } QPushButton:hover { background-color: #fdd835; }")
        self.btn_hit.clicked.connect(self.calculate_history_hits_ui)
        toolbar.addWidget(self.btn_hit)
        
        self.btn_view_filtered = QPushButton("查看")
        self.btn_view_filtered.setToolTip("查看当前过滤条件命中的个股明细")
        self.btn_view_filtered.setStyleSheet("QPushButton { background-color: #1a3333; color: #00ffcc; font-weight: bold; border: 1px solid #00ffcc; border-radius: 3px; padding: 1px 4px; min-width: 26px; font-size: 8.5pt; } QPushButton:hover { background-color: #00ffcc; color: #000000; }")
        self.btn_view_filtered.clicked.connect(self.view_filtered_stocks_dialog)
        toolbar.addWidget(self.btn_view_filtered)
        
        # 载入默认的公式数据
        self._on_history_group_changed()

    def _init_ui(self):
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.main_splitter)

        # 1. Left panel: Universe Tree (Width: 350)
        self.universe_widget = UniverseTreeWidget()
        self.universe_widget.setMinimumWidth(300)
        self.main_splitter.addWidget(self.universe_widget)

        # 2. Center panel: Swing Table & Trading Tabs (Width: 700)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. Top Tabs in center panel (顶部主看板 Tab: 重点关注 + 回调跟踪器)
        self.top_tabs = QTabWidget()
        self.top_tabs.setStyleSheet("""
            QTabBar::tab { font-size: 10.5pt; font-weight: bold; padding: 6px 14px; min-width: 140px; }
            QTabBar::tab:selected { background-color: #1a2a1a; color: #ffd700; border-bottom: 3px solid #ffd700; }
        """)
        
        self.favorite_panel = FavoritePanel()
        self.favorite_panel.stock_selected.connect(self.on_stock_clicked)
        self.top_tabs.addTab(self.favorite_panel, "⭐ 重点关注 (基础重点)")

        self.swing_table = SwingStateTable()
        self.swing_table.dragon_monitor_requested.connect(self.open_dragon_monitor)
        self.top_tabs.addTab(self.swing_table, "📉 大级别 MA20d 回调跟踪器")

        self.new_stock_panel = NewStockPanel(main_window=self)
        self.new_stock_panel.stock_selected.connect(self.link_stock)
        self.new_stock_panel.stock_double_clicked.connect(self.on_stock_clicked)
        self.top_tabs.addTab(self.new_stock_panel, "🆕 新股次新股 (IPO & 阶梯)")
        self.top_tabs.currentChanged.connect(self._on_top_tab_changed)
        
        # 顶部主看板 Tab 右上角添加【🔥 涨停天梯】、【🎯 60f通道测算】与【🪟 SBC 重排】组合入口
        top_corner_container = QWidget()
        top_corner_layout = QHBoxLayout(top_corner_container)
        top_corner_layout.setContentsMargins(0, 0, 0, 0)
        top_corner_layout.setSpacing(6)

        self.btn_top_limit_up = QPushButton("🔥 涨停天梯")
        self.btn_top_limit_up.setToolTip("打开每日涨停分析、封单比/量能比统计与多日强势股天梯看板")
        self.btn_top_limit_up.setStyleSheet("""
            QPushButton {
                background-color: #3d1414;
                color: #ff5555;
                font-weight: bold;
                border: 1px solid #ff4444;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #ff4444;
                color: #000000;
            }
        """)
        self.btn_top_limit_up.clicked.connect(self.open_daily_limit_up_analyzer)
        top_corner_layout.addWidget(self.btn_top_limit_up)

        self.channel_scan_period = getattr(self, "channel_scan_period", "60f")
        self.btn_top_scan_channel = QPushButton(f"🎯 {self.channel_scan_period}通道测算 ▾")
        self.btn_top_scan_channel.setToolTip(
            f"【直接点击】按当前周期 [{self.channel_scan_period}] 立即执行通道测算\n"
            f"【按住 Alt 点击 或 右键】弹出周期选择菜单 (60f / 120f / 日线 / 周线 / 月线)"
        )
        self.btn_top_scan_channel.setStyleSheet("""
            QPushButton {
                background-color: #0e2a38;
                color: #38bdf8;
                font-weight: bold;
                border: 1px solid #0284c7;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_top_scan_channel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_top_scan_channel.customContextMenuRequested.connect(self._show_channel_scan_period_menu)
        self.btn_top_scan_channel.clicked.connect(self._on_channel_scan_button_clicked)
        top_corner_layout.addWidget(self.btn_top_scan_channel)
        self.btn_top_scan_60f = self.btn_top_scan_channel  # 保持向后兼容别名

        self.btn_rearrange_sbc = QPushButton("🪟 SBC 重排")
        self.btn_rearrange_sbc.setToolTip("自动将所有已打开的 SBC 分时走势独立窗口在当前屏幕网格平铺重排对齐")
        self.btn_rearrange_sbc.setStyleSheet("""
            QPushButton {
                background-color: #1a2e22;
                color: #00ff88;
                font-weight: bold;
                border: 1px solid #00ff88;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #00ff88;
                color: #000000;
            }
        """)
        self.btn_rearrange_sbc.clicked.connect(self.rearrange_all_sbc_windows)
        top_corner_layout.addWidget(self.btn_rearrange_sbc)

        if hasattr(self.swing_table, "btn_refresh"):
            top_corner_layout.addWidget(self.swing_table.btn_refresh)

        self.top_tabs.setCornerWidget(top_corner_container, Qt.Corner.TopRightCorner)
        self.top_tabs.currentChanged.connect(self._on_top_tab_changed)
        enable_tab_direct_switch(self.top_tabs)
        self.center_splitter.addWidget(self.top_tabs)
        
        # 2. Bottom Tabs in center panel (底部从属 Tab: 持仓 + 订单 + 回测 + 轨迹)
        self.center_tabs = QTabWidget()
        self.center_tabs.setMinimumWidth(100)
        self.center_tabs.setMinimumHeight(80)
        
        self.position_panel = PositionPanel()
        self.center_tabs.addTab(self.position_panel, "💰 当前持仓 (Holdings)")
        
        self.trade_flow_table = TradeFlowTable()
        self.center_tabs.addTab(self.trade_flow_table, "📋 交易流水 (Orders)")
        
        self.backtest_panel = BacktestReportPanel()
        self.center_tabs.addTab(self.backtest_panel, "📊 离线回测报告 (Backtest)")
        
        self.kernel_trace_panel = KernelTracePanel()
        self.center_tabs.addTab(self.kernel_trace_panel, "🤖 内核轨迹 (Kernel Trace)")
        enable_tab_direct_switch(self.center_tabs)
        
        self.center_splitter.addWidget(self.center_tabs)
        self.center_splitter.setSizes([450, 450])
        
        center_layout.addWidget(self.center_splitter)
        self.main_splitter.addWidget(center_widget)

        # 3. Right panel: Heatmap & Distribution charts (Width: 390)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        self.heatmap_widget = SectorHeatmapWidget()
        self.right_splitter.addWidget(self.heatmap_widget)
        
        # Right charts tab (市场分布 + 资金明细，启用箭头点击直接切换)
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(100)
        self.right_tabs.setMinimumHeight(80)
        
        self.dist_chart = DistributionBarChart()
        self.right_tabs.addTab(self.dist_chart, "📊 市场分布")
        
        self.equity_chart = EquityCurveChart()
        self.right_tabs.addTab(self.equity_chart, "📈 资金明细")
        enable_tab_direct_switch(self.right_tabs)
        
        # 资金曲线 / 右侧 Tab 右上角添加【📋 强势黑马详情】(图2) 与【🗔 独立放大窗口】组合入口
        corner_container = QWidget()
        corner_layout = QHBoxLayout(corner_container)
        corner_layout.setContentsMargins(0, 0, 0, 0)
        corner_layout.setSpacing(6)

        self.btn_pop_signal_detail = QPushButton("📋 强势黑马详情")
        self.btn_pop_signal_detail.setToolTip("弹出/唤醒本轮强势黑马信号个股详情看板 (支持上一只/下一只轮转与特征分析)")
        self.btn_pop_signal_detail.setStyleSheet("""
            QPushButton {
                background-color: #1a261a;
                color: #4ade80;
                border: 1px solid #4ade80;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4ade80;
                color: #0f172a;
            }
        """)
        self.btn_pop_signal_detail.clicked.connect(self._open_signal_detail_dialog)

        self.btn_pop_equity_window = QPushButton("🗔 独立放大窗口")
        self.btn_pop_equity_window.setToolTip("在独立放大窗口中查看资金收益率曲线及全市场分布图表")
        self.btn_pop_equity_window.setStyleSheet("""
            QPushButton {
                background-color: #1a1a26;
                color: #38bdf8;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #38bdf8;
                color: #0f172a;
            }
        """)
        self.btn_pop_equity_window.clicked.connect(self._open_equity_pop_dialog)

        corner_layout.addWidget(self.btn_pop_signal_detail)
        corner_layout.addWidget(self.btn_pop_equity_window)
        self.right_tabs.setCornerWidget(corner_container, Qt.Corner.TopRightCorner)
        
        self.right_splitter.addWidget(self.right_tabs)
        self.right_splitter.setSizes([450, 450])
        
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_widget)

        # Set stretch factors and initial sizes (左0、中1、右0：确保窗口resize时左右维持用户调好的固定宽度，中间面板吸收全量增量空间)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        
        # Enforce non-collapsible panels to prevent UI collapse to 0 size
        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.center_splitter.setCollapsible(0, False)
        self.center_splitter.setCollapsible(1, False)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)
        
        self.main_splitter.setSizes([350, 700, 390])
        
        # Bind splitterMoved signals to track user-adjusted resize ratios & auto save layout
        self.main_splitter.splitterMoved.connect(self._on_main_splitter_moved)
        self.center_splitter.splitterMoved.connect(self._on_center_splitter_moved)
        self.right_splitter.splitterMoved.connect(self._on_right_splitter_moved)

        # Connect internal signal linkages
        # 1. 单击事件 -> 联动外部同花顺/通达信及可视化器 (link_stock)
        self.universe_widget.stock_clicked.connect(self.link_stock)
        self.swing_table.stock_clicked.connect(self.link_stock)
        self.favorite_panel.table.stock_activated.connect(self.link_stock)
        self.position_panel.stock_clicked.connect(self.link_stock)
        self.trade_flow_table.stock_clicked.connect(self.link_stock)
        self.kernel_trace_panel.stock_clicked.connect(self.link_stock)
        
        # 2. 双击事件 -> 弹窗详情展示 context_info (on_stock_clicked)
        self.universe_widget.stock_selected.connect(self.on_stock_clicked)
        self.swing_table.stock_double_clicked.connect(self.on_stock_clicked)
        self.position_panel.stock_double_clicked.connect(self.on_stock_clicked)
        self.trade_flow_table.stock_double_clicked.connect(self.on_stock_clicked)
        self.kernel_trace_panel.stock_double_clicked.connect(self.on_stock_clicked)
        
        self.heatmap_widget.sector_selected_with_codes.connect(lambda name, codes: self.on_sector_clicked(name, member_codes=codes if codes else None))
        self.swing_table.btn_refresh.clicked.connect(lambda: self.load_db_data(force=True))
        self.backtest_panel.btn_run_backtest.clicked.connect(self.on_run_backtest_clicked)

    def _on_history_group_changed(self):
        group = self.history_selector.currentText()
        h_list = self.search_histories.get(group, [])
            
        formatted_list = []
        for item in h_list:
            display_text = self._format_history_item_local(item)
            if display_text:
                formatted_list.append(display_text)
                
        self.query_combo.blockSignals(True)
        self.query_combo.clear()
        self.query_combo.addItems(formatted_list)
        
        restored_idx = -1
        last_q = getattr(self, "last_query", "")
        if last_q and h_list:
            last_q_clean = " ".join(str(last_q).split()).strip()
            for idx, item in enumerate(h_list):
                item_q = item.get("query", "").strip() if isinstance(item, dict) else str(item).strip()
                item_q_clean = " ".join(item_q.split()).strip()
                item_disp = self._format_history_item_local(item)
                item_disp_clean = " ".join(item_disp.split()).strip()
                
                if (item_q == last_q or 
                    item_q_clean == last_q_clean or 
                    item_disp == last_q or 
                    item_disp_clean == last_q_clean or
                    (item_q_clean and item_q_clean in last_q_clean)):
                    restored_idx = idx
                    break
                
        if restored_idx >= 0:
            self.query_combo.setCurrentIndex(restored_idx)
        elif formatted_list:
            self.query_combo.setCurrentIndex(0)
        else:
            self.query_combo.setCurrentText("")
                
        self.query_combo.blockSignals(False)
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))
        
        # 默认应用并加载当前历史过滤公式
        self.apply_filter()

    def _format_history_item_local(self, item):
        if not isinstance(item, dict): 
            return str(item)
        q = item.get("query", "").strip()
        q = " ".join(q.split())
        note = item.get("note", "").strip()
        hit = item.get("hit", "")
        parts = []
        if note: 
            parts.append(note)
        if hit != "" and hit is not None: 
            parts.append(f"[Hit: {hit}]")
        if q:
            parts.append(q)
        return "  |  ".join(parts)

    def _get_real_query(self):
        text = self.query_combo.currentText().strip()
        if not text:
            return ""
        text_clean = " ".join(text.split()).strip()
        
        # 1. 优先从当前活跃历史组中匹配原始完整记录 (保留 \n 和多行排版)
        group = self.history_selector.currentText() if hasattr(self, 'history_selector') else "history5"
        h_list = self.search_histories.get(group, []) if hasattr(self, 'search_histories') else []
        for item in h_list:
            if isinstance(item, dict):
                orig_q = item.get("query", "").strip()
                disp = self._format_history_item_local(item)
                disp_clean = " ".join(disp.split()).strip()
                orig_q_clean = " ".join(orig_q.split()).strip()
                if (text == disp or text_clean == disp_clean or 
                    text == orig_q or text_clean == orig_q_clean or
                    (orig_q_clean and orig_q_clean in text_clean)):
                    return orig_q
                    
        # 2. 检查其他历史组
        if hasattr(self, 'search_histories'):
            for g, items in self.search_histories.items():
                if g == group: continue
                for item in items:
                    if isinstance(item, dict):
                        orig_q = item.get("query", "").strip()
                        disp = self._format_history_item_local(item)
                        disp_clean = " ".join(disp.split()).strip()
                        orig_q_clean = " ".join(orig_q.split()).strip()
                        if (text == disp or text_clean == disp_clean or 
                            text == orig_q or text_clean == orig_q_clean or
                            (orig_q_clean and orig_q_clean in text_clean)):
                            return orig_q
                            
        # 3. 兜底剥离前缀标题与 [Hit: xxx] 标签
        import re
        cleaned = text
        cleaned = re.sub(r'^\s*【[^】]*】\s*(?:\||\s)*', '', cleaned)
        cleaned = re.sub(r'^\s*\[Hit:\s*\d+\]\s*(?:\||\s)*', '', cleaned)
        if "  |  " in cleaned:
            cleaned = cleaned.split("  |  ")[-1].strip()
        elif " | " in cleaned:
            cleaned = cleaned.split(" | ")[-1].strip()
        return cleaned.strip()

    def calculate_history_hits_ui(self):
        test_df = self.get_test_df_for_hits()
        if test_df.empty:
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, "⚠️ 实盘数据未就绪")
            return
            
        group = self.history_selector.currentText()
        target = self.search_histories.get(group, [])
        if not target: 
            from stock_logic_utils import toast_messageQT
            toast_messageQT(self, "⚠️ 当前历史组为空")
            return
            
        from stock_logic_utils import test_code_against_queries, toast_messageQT
        
        enriched_results = test_code_against_queries(test_df, target)
        
        new_values = []
        for i, item in enumerate(target):
            hit_count = 0
            if i < len(enriched_results):
                hit_count = enriched_results[i].get("hit", 0)
            item["hit"] = hit_count
            display = self._format_history_item_local(item)
            new_values.append(display)
            
        current_val = self.query_combo.currentText()
        raw_q = self._get_real_query()
        
        self.query_combo.blockSignals(True)
        self.query_combo.clear()
        self.query_combo.addItems(new_values)
        
        if raw_q:
            matched_display = None
            matched_idx = -1
            raw_q_clean = " ".join(raw_q.split()).strip()
            for idx, item in enumerate(target):
                item_q = item.get("query", "").strip()
                item_q_clean = " ".join(item_q.split()).strip()
                if item_q == raw_q or item_q_clean == raw_q_clean:
                    matched_idx = idx
                    matched_display = self._format_history_item_local(item)
                    break
            if matched_idx >= 0:
                self.query_combo.setCurrentIndex(matched_idx)
            elif matched_display:
                self.query_combo.setCurrentText(matched_display)
            else:
                self.query_combo.setCurrentText(current_val)
        elif current_val:
            self.query_combo.setCurrentText(current_val)
            
        self.query_combo.blockSignals(False)
                    
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))
            
        self._save_search_history_data()
        toast_messageQT(self, f"✅ 策略命中统计完成 (n={len(target)})")

    def get_test_df_for_hits(self):
        import pandas as pd
        if self.current_df is not None and not self.current_df.empty:
            test_df = self.current_df.copy()
            mapping = {
                '价格': 'close', '最新价': 'close', '现价': 'close', 
                '涨幅': 'pct', 
                '量': 'volume', '成交量': 'volume',
                '成交额': 'turnover',
                '最高': 'high', '最低': 'low', '开盘': 'open',
                '板块': 'category', '异动类型': 'category', 'hy': 'category'
            }
            for cn, en in mapping.items():
                if cn in test_df.columns and en not in test_df.columns:
                    test_df[en] = test_df[cn]
            if 'close' in test_df.columns:
                for col in ['open', 'high', 'low']:
                    if col not in test_df.columns:
                        test_df[col] = test_df['close']
            return test_df
        return pd.DataFrame()

    def _recompute_filtered_codes_set(self):
        """根据当前策略公式 query_expr 和最新的全市场行情 current_df 动态计算匹配的股票代码集合"""
        query = getattr(self, 'query_expr', '')
        self.filtered_codes_set = set()
        if query and self.current_df is not None and not self.current_df.empty:
            test_df = self.get_test_df_for_hits()
            if not test_df.empty:
                from stock_logic_utils import query_engine
                import pandas as pd
                try:
                    df_res = query_engine.execute(test_df, query)
                    if isinstance(df_res, pd.DataFrame) and not df_res.empty:
                        if 'code' in df_res.columns:
                            self.filtered_codes_set = {str(c).strip().zfill(6) for c in df_res['code']}
                        else:
                            self.filtered_codes_set = {str(c).strip().zfill(6) for c in df_res.index}
                except Exception as ex:
                    logger.debug(f"_recompute_filtered_codes_set query_engine error: {ex}")

    def apply_filter(self, force=False):
        import time
        now = time.time()
        query = self._get_real_query()
        
        # ⚡ 防抖与脏检查：若公式完全一致且距上次点击不足 300ms，直接跳过避免密集重算导致卡顿
        last_t = getattr(self, '_last_apply_filter_t', 0.0)
        last_q = getattr(self, '_last_applied_query', None)
        if not force and last_q == query and (now - last_t < 0.30):
            return
            
        self._last_apply_filter_t = now
        self._last_applied_query = query
        self.query_expr = query
        self.last_query = query
        
        # 1. 动态重新计算匹配集合
        self._recompute_filtered_codes_set()
                    
        from ats.ui.styles import save_config_node
        save_config_node("ats_query_expr", query)

        if query:
            group = self.history_selector.currentText()
            h_list = self.search_histories.get(group, [])
            
            exists = False
            for item in h_list:
                if isinstance(item, dict) and item.get("query") == query:
                    exists = True
                    break
                elif isinstance(item, str) and item == query:
                    exists = True
                    break
                    
            if not exists:
                h_list.insert(0, {"query": query, "starred": 0, "note": ""})
                if len(h_list) > 500: # MAX_HISTORY
                    h_list.pop()
                
                # 同步回写保存
                self._save_search_history_data()
                self._on_history_group_changed()
            else:
                self._save_search_history_data()
        else:
            self._save_search_history_data()
                
        # 2. 广播更新主界面三大 Tab 看板 (重点关注, 回调跟踪器, 新股次新股)
        if hasattr(self, 'favorite_panel') and hasattr(self.favorite_panel, '_apply_row_visibility'):
            self.favorite_panel._apply_row_visibility()
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, '_apply_favorite_filter'):
            self.swing_table._apply_favorite_filter()
        if hasattr(self, 'new_stock_panel') and hasattr(self.new_stock_panel, '_apply_filter'):
            self.new_stock_panel._apply_filter()

        # 3. 广播更新所有相关可见独立窗口 (板块成分股明细、个股详情、分布图表)
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'on_global_filter_changed') and widget.isVisible():
                widget.on_global_filter_changed(self.query_expr)
            elif isinstance(widget, StockDetailDialog) and widget.isVisible():
                widget.update_filter_status(self.query_expr)
                
        # 广播更新过滤后的个股明细窗口
        if hasattr(self, 'dist_chart'):
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)
                
        if self.query_combo.lineEdit():
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(50, lambda: self.query_combo.lineEdit().setCursorPosition(0))

    def clear_filter(self):
        self.query_combo.setCurrentText("")
        self.query_expr = ""
        self.last_query = ""
        self.filtered_codes_set = set()
        from ats.ui.styles import save_config_node
        save_config_node("ats_query_expr", "")
        self._save_search_history_data()
        
        # 广播清空过滤状态至三大 Tab 看板
        if hasattr(self, 'favorite_panel') and hasattr(self.favorite_panel, '_apply_row_visibility'):
            self.favorite_panel._apply_row_visibility()
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, '_apply_favorite_filter'):
            self.swing_table._apply_favorite_filter()
        if hasattr(self, 'new_stock_panel') and hasattr(self.new_stock_panel, '_apply_filter'):
            self.new_stock_panel._apply_filter()
        
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'on_global_filter_changed') and widget.isVisible():
                widget.on_global_filter_changed("")
            elif isinstance(widget, StockDetailDialog) and widget.isVisible():
                widget.update_filter_status("")
                
        # 广播清空过滤明细窗口
        if hasattr(self, 'dist_chart'):
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)
            
        toast_messageQT(self, "✨ 策略过滤已清空")

    def view_filtered_stocks_dialog(self):
        query = self._get_real_query()
        self.query_expr = query
        
        if hasattr(self, 'dist_chart'):
            # 1. 若窗口已存在且打开，则直接激活置顶，绝不重复刷新引起卡顿
            from PyQt6.sip import isdeleted
            for d in getattr(self.dist_chart, '_active_dialogs', []):
                try:
                    if d and not isdeleted(d) and getattr(d, 'bucket_idx', None) == 999:
                        if hasattr(d, 'show_normal_position'):
                            d.show_normal_position()
                        else:
                            d.show()
                            d.raise_()
                            d.activateWindow()
                        return
                except Exception:
                    pass
                    
            # 2. 首次打开或重新开启
            config = {}
            try:
                import os
                import json
                from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
                if os.path.exists(WINDOW_CONFIG_FILE):
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        config = data.get("distribution_details_dialog_999", {})
            except Exception:
                pass
                
            self.dist_chart.open_details_dialog(999, restore_state=config, cold_start=True)
            
            # 仅在首次拉起窗口时同步数据
            df_to_update = self.current_df if self.current_df is not None else self.dist_chart.current_df
            self.dist_chart.update_data([], stats_dict=None, df_all=df_to_update)

    def _init_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("初始化独立自治交易系统，就绪。")

        # 🕒 状态栏右侧常驻显示：数据更新时间与下次自动刷新倒计时
        self._last_data_update_time = None
        self._next_auto_refresh_time = None

        self.lbl_data_time_status = QLabel()
        self.lbl_data_time_status.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 9pt; padding-right: 8px;")
        self.status_bar.addPermanentWidget(self.lbl_data_time_status)

        # 每秒刷新一次右下角时间与倒计时状态
        self._status_clock_timer = QTimer(self)
        self._status_clock_timer.timeout.connect(self._refresh_statusbar_time_display)
        self._status_clock_timer.start(1000)
        self._refresh_statusbar_time_display()

    def _refresh_statusbar_time_display(self):
        """动态刷新状态栏右侧的数据更新时间与下次自动刷新倒计时"""
        import time
        from datetime import datetime

        now = time.time()
        if self._last_data_update_time:
            t_str = datetime.fromtimestamp(self._last_data_update_time).strftime("%H:%M:%S")
        else:
            t_str = "--:--:--"

        if getattr(self, "is_auto_refresh_enabled", False):
            if self._next_auto_refresh_time is None or self._next_auto_refresh_time <= now:
                self._next_auto_refresh_time = now + 60.0
            
            rem_sec = max(0, int(self._next_auto_refresh_time - now))
            next_str = datetime.fromtimestamp(self._next_auto_refresh_time).strftime("%H:%M:%S")
            self.lbl_data_time_status.setText(f"🕒 数据更新: {t_str}  |  🔄 下次自动刷新: {next_str} ({rem_sec}s)")
            self.lbl_data_time_status.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 9pt; padding-right: 8px;")
        else:
            self.lbl_data_time_status.setText(f"🕒 数据更新: {t_str}  |  🔄 自动刷新: 已关闭 (等待TK推送)")
            self.lbl_data_time_status.setStyleSheet("color: #8e8e93; font-weight: bold; font-size: 9pt; padding-right: 8px;")

    def toggle_rotation(self):
        if "▶" in self.btn_toggle_rotation.text():
            self.btn_toggle_rotation.setText("■ 24x7")
            self.btn_toggle_rotation.setStyleSheet("QPushButton { background-color: #3d0000; color: #ff6060; font-weight: bold; border: 1px solid #ff4444; border-radius: 3px; padding: 2px 8px; font-size: 9pt; } QPushButton:hover { background-color: #ff4444; color: #000; }")
            self.lbl_rotator_status.setText("旋转引擎: 🟢 运行中")
            self.lbl_rotator_status.setStyleSheet("color: #00ff88;")
            self.status_bar.showMessage("24x7 自动过滤、信号评估、及大级别历史回测轮转已启动。")
        else:
            self.btn_toggle_rotation.setText("▶ 24x7")
            self.btn_toggle_rotation.setStyleSheet("QPushButton { background-color: #1a3a1a; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 3px; padding: 2px 8px; font-size: 9pt; } QPushButton:hover { background-color: #00ff88; color: #000; }")
            self.lbl_rotator_status.setText("旋转引擎: ⏸️ 已暂停")
            self.lbl_rotator_status.setStyleSheet("color: #ff9900;")
            self.status_bar.showMessage("自动轮转引擎已暂停。")

    def link_stock(self, code, name):
        """
        [LINKAGE] 单击个股触发联动：
        1. 向 trade_visualizer_qt6 可视化服务器 (TCP 端口 26668) 发送 CODE|{code} 切换行情。
        2. 调用 get_link_manager().push() 执行外部通达信/同花顺终端物理联动。
        """
        code_clean = str(code).strip()
        if not code_clean:
            return

        # 记录主界面当前选中的股票和名称 (供分时策略等各独立功能模块联动)
        c_digits = "".join(x for x in code_clean if x.isdigit()).zfill(6) if any(x.isdigit() for x in code_clean) else code_clean
        self.current_selected_code = c_digits
        self.current_selected_name = str(name) if name and name != "未知" else self.get_stock_name(c_digits)
            
        import time
        now = time.time()
        last_code = getattr(self, "_last_linked_code", None)
        last_time = getattr(self, "_last_linked_time", 0)
        if last_code == code_clean and (now - last_time) < 0.2:
            # 500ms 内重复对同一代码发起联动，直接短路忽略，防止多重绑定信号引起重复联动导致 TDX/THS 闪烁
            return
        self._last_linked_code = code_clean
        self._last_linked_time = now
        
        self.status_bar.showMessage(f"🔗 [联动] 推送股票 {code_clean} {name} (已同步可视化及外部交易终端)")
        
        # 1. 异步向 26668 发送切换个股 socket 指令 (VIS 联动)
        if hasattr(self, 'cb_vis') and self.cb_vis.isChecked():
            import socket
            import threading
            
            # Check if this stock is in favorites and retrieve its add date
            add_date = None
            try:
                from global_favorites import GlobalFavoriteManager
                fav_mgr = GlobalFavoriteManager()
                if code_clean in fav_mgr.get_favorite_stocks():
                    add_date = fav_mgr.get_favorite_stock_date(code_clean)
            except Exception:
                pass
            
            # If add_date is available, format as TIME_LINK; otherwise CODE
            if add_date:
                cmd_str = f"TIME_LINK|{code_clean}|{add_date}|label=重点关注"
            else:
                cmd_str = f"CODE|{code_clean}"
            
            def send_switch(msg):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(0.1) # 极低超时，不阻塞 UI
                        s.connect(('127.0.0.1', 26668))
                        s.sendall(msg.encode("utf-8"))
                except Exception:
                    pass # 可视化器可能未启动，静默失败即可
                    
            threading.Thread(target=send_switch, args=(cmd_str,), daemon=True).start()

        # 2. 向独立联动进程投递物理联动任务 (TDX/THS 物理联动机能)
        is_tdx = self.cb_tdx.isChecked() if hasattr(self, 'cb_tdx') else True
        is_ths = self.cb_ths.isChecked() if hasattr(self, 'cb_ths') else True
        if is_tdx or is_ths:
            try:
                from linkage_service import get_link_manager
                flags = {'tdx': is_tdx, 'ths': is_ths, 'dfcf': False}
                get_link_manager().push(code_clean, flags=flags, auto=False)
            except Exception as e:
                print(f"[Linkage] External linkage failed: {e}")

    def _on_top_tab_changed(self, index: int):
        """主看板顶部 Tab 切换事件：极速 0ms 补齐渲染与同步对应 Tab 页面数据"""
        try:
            if index == 0:
                # 切换到 ⭐ 重点关注 (基础重点)
                if hasattr(self, 'favorite_panel'):
                    if hasattr(self, '_pending_fav_rows') and self._pending_fav_rows:
                        self.favorite_panel.update_favorite_rows(self._pending_fav_rows)
                    elif hasattr(self.favorite_panel, '_apply_row_visibility'):
                        self.favorite_panel._apply_row_visibility()
            elif index == 1:
                # 切换到 📉 大级别 MA20d 回调跟踪器
                if hasattr(self, 'swing_table'):
                    if hasattr(self, '_pending_swing_rows') and self._pending_swing_rows:
                        self.swing_table.update_data_list(self._pending_swing_rows)
                    elif hasattr(self.swing_table, '_apply_favorite_filter'):
                        self.swing_table._apply_favorite_filter()
            elif index == 2:
                # 切换到 🆕 新股次新股 (IPO & 阶梯)
                if hasattr(self, 'new_stock_panel'):
                    if hasattr(self.new_stock_panel, '_apply_filter'):
                        self.new_stock_panel._apply_filter()
        except Exception as e:
            logger.debug(f"[ATSMainWindow] _on_top_tab_changed error: {e}")

    def _get_today_signal_codes(self):
        """归纳今日所有已发现/记录的特异与共振强势股票代码列表 (供弹窗左右导航联动)"""
        codes = []
        seen = set()
        
        # 1. 优先从 SignalLedger 提取
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries'):
            for c, entry in self.signal_ledger.entries.items():
                c_clean = str(c).strip()
                if c_clean and c_clean not in seen:
                    seen.add(c_clean)
                    name = getattr(entry, 'name', c_clean)
                    if hasattr(self, 'get_stock_name'):
                        name = self.get_stock_name(c_clean)
                    codes.append((c_clean, name))
                    
        # 2. 补充从 SwingStateTable 提取
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            for r in range(tbl.rowCount()):
                c_item = tbl.item(r, 0)
                n_item = tbl.item(r, 1)
                if c_item:
                    c_clean = c_item.text().strip()
                    if c_clean and c_clean not in seen:
                        seen.add(c_clean)
                        n_str = n_item.text().strip() if n_item else c_clean
                        codes.append((c_clean, n_str))
        return codes

    def _ensure_context_info(self, code, name, context_info):
        """保证弹窗必定包含完整的 [📍 策略特征上下文 (Context Info)] 面板 (100% 对齐图 2 样式)"""
        code_clean = str(code).strip()
        res = context_info.copy() if context_info else {}

        # 1. 尝试从 swing_table 匹配 (优先获取 MA20d 回调跟踪器上下文, 使用 findItems 原生优化查找)
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            found_items = tbl.findItems(code_clean, Qt.MatchFlag.MatchExactly)
            if found_items:
                row = found_items[0].row()
                res['position'] = "波段回调跟踪器 (Swing Pullback Tracker)"
                res['reason'] = "股价缩量向大级别MA20均线回调靠拢中"
                parts = []
                for col in [3, 4, 5, 6, 7]:
                    h = tbl.horizontalHeaderItem(col)
                    v = tbl.item(row, col)
                    if h and v and v.text().strip():
                        parts.append(f"{h.text()}: {v.text().strip()}")
                res['status'] = " | ".join(parts) if parts else "MA20均线回调企稳中"
                return res

        # 2. 尝试从 signal_ledger 匹配
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries'):
            entry = self.signal_ledger.entries.get(code_clean)
            if entry:
                res['position'] = f"SignalLedger {getattr(entry, 'tier', 'RADAR')} 信号池"
                if hasattr(entry, 'tdx_label') and entry.tdx_label:
                    price_info = f" | 触发价格:{getattr(entry, 'tdx_price', 0.0):.2f}" if hasattr(entry, 'tdx_price') else ""
                    time_info = f" | 处理时间:[{entry.tdx_time_str}]" if hasattr(entry, 'tdx_time_str') and entry.tdx_time_str else ""
                    res['reason'] = f"{entry.tdx_label} | {getattr(entry, 'promote_reason', '')}{price_info}{time_info}"
                else:
                    res['reason'] = getattr(entry, 'promote_reason', '黄金特异高分跟进信号')
                res['status'] = (
                    f"MA20偏离: {getattr(entry, 'latest_deviation', 0.0):+.2f}% | "
                    f"优先级: {getattr(entry, 'priority_score', 0.0):.0f} | "
                    f"特异打分: {getattr(entry, 'specialty_score', 90.0):.0f}"
                )
                return res

        # 3. 兜底默认补齐
        if not res.get('position'):
            res['position'] = "大级别波段跟踪与实盘监控热点"
            res['reason'] = "大盘共振/相对大盘强偏离拉升买点"
            res['status'] = f"代码: {code_clean} | 已成功对接实盘行情快照核心特征"

        return res

    def on_stock_clicked(self, code, name, context_info=None, batch_codes=None):
        self.status_bar.showMessage(f"双击详情: {code} {name}")
        context_info = self._ensure_context_info(code, name, context_info)
        code_clean = str(code).strip()
        c_digits = "".join(x for x in code_clean if x.isdigit()).zfill(6) if any(x.isdigit() for x in code_clean) else code_clean
        self.current_selected_code = c_digits
        self.current_selected_name = str(name) if name and name != "未知" else self.get_stock_name(c_digits)

        # 【核心机制】若详情弹窗实例存在且有效（不论处于悬浮显示还是磁吸贴边隐藏），直接复用、更新并拉至最前端唤醒
        from PyQt6.sip import isdeleted
        if hasattr(self, '_detail_dialog') and self._detail_dialog is not None:
            if isdeleted(self._detail_dialog):
                self._detail_dialog = None
            else:
                try:
                    effective_batch = batch_codes or getattr(self, "_last_batch_signal_codes", None)
                    self._detail_dialog.switch_to_code(code_clean, name, batch_codes=effective_batch)
                    self._detail_dialog.show()
                    self._detail_dialog.raise_()
                    self._detail_dialog.activateWindow()
                    return
                except RuntimeError:
                    self._detail_dialog = None
                except Exception as e:
                    print(f"[ATSMainWindow] Error reusing detail dialog: {e}")
                    self._detail_dialog = None
        
        # 内存极速提取最新行情 (current_df -> df_realtime 级联匹配，杜绝主线程网络 API 阻塞)
        df_row = None
        c_clean = str(code).strip().zfill(6)
        for attr in ("current_df", "df_realtime"):
            if hasattr(self, attr):
                df = getattr(self, attr)
                if df is not None and not df.empty:
                    if c_clean in df.index:
                        row = df.loc[c_clean]
                        df_row = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                        break
                    elif 'code' in df.columns:
                        m = df[df['code'] == c_clean]
                        if not m.empty:
                            df_row = m.iloc[0].to_dict()
                            break
                    
        # 安全清理已存在的详情弹窗旧实例
        if hasattr(self, '_detail_dialog') and self._detail_dialog is not None:
            if not isdeleted(self._detail_dialog):
                try:
                    self._detail_dialog.close()
                except Exception:
                    pass
            self._detail_dialog = None
                
        # Launch detail dialog as non-modal so it can snap and auto-hide
        self._detail_dialog = StockDetailDialog(code, name, df_row, context_info, parent=self, batch_codes=batch_codes)
        self._detail_dialog.show()
        self._detail_dialog.raise_()
        self._detail_dialog.activateWindow()

    def on_sector_clicked(self, name, member_codes=None):
        try:
            self.status_bar.showMessage(f"选中板块: {name} | 正在展示成分股明细...")
            from ats.ui.sector_detail_dialog import ATSSectorDetailDialog
            from PyQt6.sip import isdeleted

            current_df = self.current_df if hasattr(self, 'current_df') else None

            # 【复用弹窗】如果板块详情弹窗实例已存在且有效，原地更新数据并拉至最前端
            if hasattr(self, "_sector_detail_dialog") and self._sector_detail_dialog and not isdeleted(self._sector_detail_dialog):
                dialog = self._sector_detail_dialog
                dialog.sector_name = name
                dialog.setWindowTitle(f"🔥 {name} 板块明细 (Real-time Sector Details)")
                dialog.member_codes = member_codes or []
                dialog.update_data(current_df)
                dialog.show()
                dialog.raise_()
                dialog.activateWindow()
                return

            # 若不存在旧实例则创建全新窗口（parent=self 确保能拿到主窗口的 current_df）
            dialog = ATSSectorDetailDialog(name, self.link_stock, self.on_stock_clicked, member_codes=member_codes, parent=self)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            self._sector_detail_dialog = dialog
        except Exception as e:
            if hasattr(self, "logger") and self.logger:
                self.logger.error(f"打开板块详情失败: {e}")
            else:
                print(f"打开板块详情失败: {e}")

    def _on_auto_refresh_toggled(self, checked: bool):
        """用户切换【自动刷新🔄】开关状态：持久化并即时启停主动轮询定时器"""
        import time
        self.is_auto_refresh_enabled = checked
        try:
            settings = QSettings("pyQuant", "ATSMainWindow")
            settings.setValue("auto_refresh_enabled", checked)
        except Exception as e:
            logger.debug(f"保存 auto_refresh_enabled 状态异常: {e}")

        if checked:
            self._next_auto_refresh_time = time.time() + 60.0
            if hasattr(self, 'update_timer') and self.update_timer:
                self.update_timer.start(60000)
            self.status_bar.showMessage("已开启后台自动刷新轮询 (60s)。")
            logger.info("⚡ [ATSMainWindow] 用户已开启后台自动刷新轮询")
        else:
            self._next_auto_refresh_time = None
            if hasattr(self, 'update_timer') and self.update_timer:
                self.update_timer.stop()
            self.status_bar.showMessage("已关闭后台自动刷新，被动等待 TK 主进程推送 IPC 数据。")
            logger.info("⏸️ [ATSMainWindow] 用户已关闭后台自动刷新，等待 TK 自动推送 IPC")

        if hasattr(self, '_refresh_statusbar_time_display'):
            self._refresh_statusbar_time_display()

    def on_heartbeat(self):
        # 0. 若未开启自动刷新，静默退出，不发起任何主动网络/管道轮询
        if not getattr(self, 'is_auto_refresh_enabled', False):
            return

        import time
        now = time.time()
        self._next_auto_refresh_time = now + 60.0
        if hasattr(self, '_refresh_statusbar_time_display'):
            self._refresh_statusbar_time_display()

        # 1. 🛡️【冷启动/盘后 IPC 健壮同步】：若当前尚未收到全量行情快照，不受交易时间限制，定时重试请求全量同步
        if not hasattr(self, "current_df") or self.current_df is None or self.current_df.empty:
            if now - getattr(self, "_last_pipe_sync_t", 0) > 15:
                self._last_pipe_sync_t = now
                try:
                    from data_utils import send_code_via_pipe, PIPE_NAME_TK
                    import logging
                    local_logger = logging.getLogger("ATS")
                    send_code_via_pipe({"cmd": "REQ_FULL_SYNC", "port": 26670}, logger=local_logger, pipe_name=PIPE_NAME_TK)
                except Exception as e:
                    print(f"[ATSMainWindow] Cold-start REQ_FULL_SYNC failed: {e}")

        # 2. 交易时段检查：非交易时段不执行高频 DB 轮询与热力图重刷
        try:
            is_work = cct.get_work_time()
        except Exception:
            is_work = False
        if not is_work:
            return

        # 3. 交易时段：定期加载 DB 数据与日志
        self.load_db_data()
        
        if hasattr(self, 'kernel_trace_panel'):
            self.kernel_trace_panel.load_trace_logs()
            
        if hasattr(self, 'heatmap_widget'):
            self.heatmap_widget.load_live_sectors(current_df=self.current_df)

        # 4. 交易时段 IPC 保活：若超过 10 分钟未收到任何推送，主动重试拉取全量同步
        if now - getattr(self, "_last_recv_t", 0) > 600:
            if now - getattr(self, "_last_pipe_sync_t", 0) > 60:
                self._last_pipe_sync_t = now
                try:
                    from data_utils import send_code_via_pipe, PIPE_NAME_TK
                    import logging
                    local_logger = logging.getLogger("ATS")
                    send_code_via_pipe({"cmd": "REQ_FULL_SYNC", "port": 26670}, logger=local_logger, pipe_name=PIPE_NAME_TK)
                except Exception as e:
                    print(f"[ATSMainWindow] Keep-alive REQ_FULL_SYNC failed: {e}")

    def _update_name_cache_from_df(self, df):
        if df is not None and not df.empty and 'name' in df.columns:
            try:
                # 向量化快速提取 IPC 推送的 DataFrame 中的 code -> name 关联字典
                temp_dict = df['name'].dropna().to_dict()
                cleaned_dict = {}
                for k, v in temp_dict.items():
                    name_str = str(v).strip()
                    if not name_str or name_str == "未知" or name_str.isdigit():
                        continue
                    k_str = str(k).strip()
                    k_clean = "".join(c for c in k_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in k_str) else k_str
                    if name_str != k_clean and name_str != k_str:
                        cleaned_dict[k_clean] = name_str
                        cleaned_dict[k_str] = name_str
                self.name_cache.update(cleaned_dict)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating name cache from df: {e}")

    def get_df_row_safe(self, df, code):
        """鲁棒安全从 DataFrame 提取单股 DataRow (全能兼容 index 索引、code 列、纯数字代码 600013、带前缀 sh600013 等)"""
        if df is None or df.empty or not code:
            return None
        code_str = str(code).strip()
        code_digits = "".join(c for c in code_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in code_str) else code_str

        # 1. 精确与纯数字匹配 (检查 index)
        if code_str in df.index:
            res = df.loc[code_str]
            return res.iloc[0] if hasattr(res, 'iloc') and len(res.shape) > 1 else res

        if code_digits in df.index:
            res = df.loc[code_digits]
            return res.iloc[0] if hasattr(res, 'iloc') and len(res.shape) > 1 else res

        # 2. 尝试匹配/剥离前缀 (sh/sz/bj) (检查 index)
        for pfx in ('sh', 'sz', 'bj'):
            pfx_code = f"{pfx}{code_digits}"
            if pfx_code in df.index:
                res = df.loc[pfx_code]
                return res.iloc[0] if hasattr(res, 'iloc') and len(res.shape) > 1 else res

        if len(code_str) > 6:
            unpfx = "".join(c for c in code_str if c.isdigit()).zfill(6)
            if unpfx in df.index:
                res = df.loc[unpfx]
                return res.iloc[0] if hasattr(res, 'iloc') and len(res.shape) > 1 else res

        # 3. 💥 关键兜底防线：如果 df.index 是 RangeIndex (0, 1, 2...)，但在 df.columns 里面有 'code' 列！
        if 'code' in df.columns:
            try:
                col_codes = df['code'].astype(str).str.strip()
                mask = (col_codes == code_str) | (col_codes == code_digits)
                if not mask.any() and code_digits:
                    mask = col_codes.str.endswith(code_digits)
                if mask.any():
                    matched = df[mask]
                    return matched.iloc[0]
            except Exception:
                pass

        return None

    def get_stock_name(self, code):
        if not code:
            return "未知"
        code_str = str(code).strip()
        code_clean = "".join(c for c in code_str if c.isdigit()).zfill(6) if any(c.isdigit() for c in code_str) else code_str
        
        # 1. ⚡ 优先从内存字典 name_cache 中 O(1) 极速提取 (微秒级, 极速响应)
        name = self.name_cache.get(code_clean) or self.name_cache.get(code_str)
        if name and name != "未知" and name != code_clean and not name.isdigit() and not name.startswith("个股_"):
            return name

        # 2. 回退：从 current_df / df_realtime 中安全匹配
        for attr_name in ('current_df', 'df_realtime'):
            df_obj = getattr(self, attr_name, None)
            if df_obj is not None and not df_obj.empty:
                row_val = self.get_df_row_safe(df_obj, code_clean)
                if row_val is not None:
                    try:
                        name_val = str(row_val.get('name', '') if hasattr(row_val, 'get') else row_val['name']).strip()
                        if name_val and name_val != code_clean and not name_val.isdigit() and name_val != "未知":
                            self.name_cache[code_clean] = name_val
                            return name_val
                    except Exception:
                        pass

        # 3. 调起全局权威解析器 sys_utils
        try:
            from sys_utils import resolve_stock_name
            res_name = resolve_stock_name(code_clean)
            if res_name and res_name != code_clean and not res_name.isdigit() and not res_name.startswith("个股_"):
                self.name_cache[code_clean] = res_name
                return res_name
        except Exception:
            pass

        return name if (name and name != code_clean and not name.isdigit()) else code_clean

    def load_db_data(self, force=False):
        """
        ⚡ 异步加载数据库数据，根治启动时 10+ 秒卡顿。

        策略：
         - 主线程: 立即启动 IPC 监听器 + 发送 REQ_FULL_SYNC (耗时 <100ms)
         - 后台线程: SQLite/JSON 查询 (步骤1-5)，完成后 QTimer.singleShot(0) 回调主线程刷新 UI
        """
        import os
        import json
        import threading
        from sys_utils import get_app_root

        base = get_app_root()
        state_path = os.path.join(base, "logs", "paper_account_state.json")
        db_path = os.path.join(base, "trading_signals.db")
        if not os.path.exists(db_path):
            db_path = "./trading_signals.db"

        db_mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else 0
        paper_mtime = os.path.getmtime(state_path) if os.path.exists(state_path) else 0

        # 未修改时跳过（仅非 force 时检查）
        if not force and getattr(self, '_last_db_mtime', None) == db_mtime and getattr(self, '_last_paper_mtime', None) == paper_mtime:
            return

        self._last_db_mtime = db_mtime
        self._last_paper_mtime = paper_mtime

        # ── ① 主线程立即启动 IPC 监听器（必须在主线程，<50ms）────────────────────
        try:
            from ats.ipc_bridge import IPCBridge
            if not hasattr(self, 'bridge') or self.bridge is None:
                self.bridge = IPCBridge()
        except Exception as e:
            print(f"[ATSMainWindow] IPCBridge 初始化失败: {e}")
            return

        if not getattr(self, '_listener_started', False):
            try:
                self.bridge.start_realtime_listener(
                    port=26670,
                    data_callback=lambda data: self.realtime_data_signal.emit(data),
                    signal_callback=lambda sig: self.realtime_signal_signal.emit(sig)
                )
                self._listener_started = True
            except Exception as e:
                print(f"[ATSMainWindow] start_realtime_listener 失败: {e}")

        # ── ② 主线程立即发送 REQ_FULL_SYNC，让主进程推送全量行情（不等待结果）──
        if force or not getattr(self, '_pipe_initial_synced', False):
            self._pipe_initial_synced = True
            try:
                from data_utils import send_code_via_pipe, PIPE_NAME_TK
                local_logger = logging.getLogger("ATS")
                self._last_pipe_sync_t = time.time()
                send_code_via_pipe({"cmd": "REQ_FULL_SYNC", "port": 26670}, logger=local_logger, pipe_name=PIPE_NAME_TK)
                print("[ATSMainWindow] 手动/强制刷新: 已成功向后台 Pipe 发送全量行情同步指令 (REQ_FULL_SYNC -> port 26670)")
                if hasattr(self, 'status_bar') and self.status_bar:
                    self.status_bar.showMessage("🔄 已下发 IPC 全量行情刷新请求，后台正在异步加载持仓与信号数据...", 4000)
            except Exception as e:
                print(f"[ATSMainWindow] Failed to send REQ_FULL_SYNC: {e}")

        # ── ③ 后台线程异步完成慢速 SQLite/JSON 查询（不阻塞主线程 UI）─────────────
        # 把需要的引用快照到局部变量，避免 lambda 闭包陷阱
        bridge_ref = self.bridge
        name_cache_ref = self.name_cache
        cur_df_ref = self.current_df

        def _bg_load():
            try:
                import json as _json
                state_data = None
                if os.path.exists(state_path):
                    try:
                        with open(state_path, "r", encoding="utf-8") as f:
                            state_data = _json.load(f)
                    except Exception as e:
                        print(f"[ATSMainWindow] Error loading paper_account_state.json: {e}")

                # 步骤 1: 交易流水 (9列格式: 时间, 代码, 名称, 方向, 成交价, 成交数量, 成交金额, 距今涨跌, 策略来源)
                def _calc_since_pct(code_str: str, trade_price_val: float) -> str:
                    if cur_df_ref is not None and code_str in cur_df_ref.index and trade_price_val > 0:
                        try:
                            row_c = cur_df_ref.loc[code_str]
                            now_p = float(row_c.get('trade', row_c.get('close', 0.0)))
                            if now_p > 0:
                                diff_pct = ((now_p - trade_price_val) / trade_price_val) * 100
                                return f"{diff_pct:+.2f}%"
                        except Exception:
                            pass
                    return "+0.00%"

                flow_data = []
                if state_data and "orders" in state_data:
                    for o in state_data["orders"]:
                        action = "买入" if o.get('action') == 'BUY' else "卖出"
                        qty = o.get('volume') or 0
                        price = float(o.get('price') or 0.0)
                        amount = price * qty
                        ts = (o.get('timestamp') or '').replace('T', ' ')
                        c = str(o.get('code') or '').strip().zfill(6)
                        since_pct = _calc_since_pct(c, price)
                        flow_data.append((str(ts), c, "",
                                          str(action),
                                          f"{price:.2f}" if price else "0.00",
                                          f"{int(qty):,}" if qty else "0",
                                          f"{amount:,.2f}" if amount else "0.00",
                                          since_pct,
                                          "核对无误"))
                    flow_data.sort(key=lambda x: x[0], reverse=True)

                flow_df = bridge_ref.get_all_trade_flows()
                final_flow = []
                if not flow_df.empty:
                    db_flow_data = []
                    for _, row in flow_df.iterrows():
                        action = row.get('action') or ('买入' if row.get('status') == 'OPEN' else '卖出')
                        date = row.get('buy_date') if action == '买入' else (row.get('sell_date') or row.get('buy_date'))
                        price = float(row.get('buy_price') if action == '买入' else (row.get('sell_price') or row.get('buy_price')) or 0.0)
                        qty = float(row.get('buy_amount') or 0)
                        amount = price * qty if price and qty else 0.0
                        c = str(row.get('code') or '').strip().zfill(6)
                        n = str(row.get('name') or '')
                        since_pct = _calc_since_pct(c, price)
                        db_flow_data.append((str(date or ''), c, n, str(action or ''),
                                             f"{price:.2f}" if price else "0.00",
                                             f"{int(qty):,}" if qty else "0",
                                             f"{amount:,.2f}" if amount else "0.00",
                                             since_pct,
                                             str(row.get('buy_reason') or '自动触发')))
                        if c and n and n != "未知":
                            name_cache_ref[c] = n
                    seen_orders = set()
                    for item in flow_data:
                        code, key = item[1], (item[0], item[1], item[3])
                        if key not in seen_orders:
                            n = name_cache_ref.get(code, code)
                            final_flow.append((item[0], code, n, item[3], item[4], item[5], item[6], item[7], item[8]))
                            seen_orders.add(key)
                    for item in db_flow_data:
                        key = (item[0], item[1], item[3])
                        if key not in seen_orders:
                            final_flow.append(item)
                            seen_orders.add(key)
                    final_flow.sort(key=lambda x: x[0], reverse=True)
                elif flow_data:
                    final_flow = [(i[0], i[1], name_cache_ref.get(i[1], i[1]), i[3], i[4], i[5], i[6], i[7], i[8])
                                  for i in flow_data]

                # 步骤 2: 持仓
                pos_formatted = []
                cash_val = 1000000.0
                total_assets_val = 1000000.0
                if state_data and "positions" in state_data:
                    cash_val = state_data.get("cash", 1000000.0)
                    total_mkt = 0.0
                    for code, p in state_data.get("positions", {}).items():
                        n = name_cache_ref.get(code) or p.get("name") or code
                        qty = p.get("volume") or 0.0
                        cost = p.get("entry_price") or 0.0
                        price = p.get("current_price") or cost
                        if cur_df_ref is not None and code in cur_df_ref.index:
                            try:
                                pv = float(cur_df_ref.loc[code].get('close', cur_df_ref.loc[code].get('trade', price)))
                                if pv > 0: price = pv
                            except: pass
                        mkt = qty * price
                        total_mkt += mkt
                        pnl_pct = f"{((price - cost) / cost * 100):+.2f}%" if cost else "+0.00%"
                        total_assets_val = cash_val + total_mkt
                        alloc = f"{(mkt / max(total_assets_val, 1)) * 100:.1f}%"
                        pos_formatted.append((str(code), str(n),
                                              f"{int(qty):,}" if qty else "0",
                                              f"{cost:.2f}" if cost else "0.00",
                                              f"{price:.2f}" if price else "0.00",
                                              f"{mkt:,.2f}" if mkt else "0.00",
                                              pnl_pct, alloc))
                    total_assets_val = cash_val + total_mkt
                else:
                    pos_df = bridge_ref.get_open_positions()
                    if not pos_df.empty:
                        total_mkt = 0.0
                        for _, row in pos_df.iterrows():
                            code = row.get('code')
                            n = row.get('name') or name_cache_ref.get(str(code), str(code))
                            qty = row.get('buy_amount') or 0
                            cost = row.get('buy_price') or 0.0
                            mkt = qty * cost
                            total_mkt += mkt
                            alloc = f"{(mkt / 1000000.0) * 100:.1f}%"
                            pos_formatted.append((str(code or ''), str(n or ''),
                                                  f"{int(qty):,}" if qty else "0",
                                                  f"{cost:.2f}" if cost else "0.00",
                                                  f"{cost:.2f}" if cost else "0.00",
                                                  f"{mkt:,.2f}" if mkt else "0.00",
                                                  "+0.00%", alloc))
                        cash_val = 1000000.0
                        total_assets_val = cash_val + total_mkt

                # 步骤 3: 历史信号
                radar_entries, watch_entries, trade_entries = {}, {}, {}
                signals_df = bridge_ref.get_historical_signals(limit=50)
                if not signals_df.empty:
                    for _, row in signals_df.iterrows():
                        code = str(row.get('code') or '').strip()
                        if not code: continue
                        n = row.get('name') or name_cache_ref.get(code, '')
                        if n == "未知": n = ""
                        price = float(row.get('price') or 0.0)
                        action = row.get('action')
                        entry = {"name": n, "price": price, "pct": 0.0,
                                 "strategy": f"周期:{row.get('resample') or 'd'}",
                                 "reason": row.get('reason') or '指标共振'}
                        if action == 'BUY':
                            watch_entries[code] = entry
                        else:
                            radar_entries[code] = entry

                pos_df2 = bridge_ref.get_open_positions()
                if not pos_df2.empty:
                    for _, row in pos_df2.iterrows():
                        p_code = str(row.get('code') or '').strip()
                        if not p_code: continue
                        n = row.get('name') or name_cache_ref.get(p_code, p_code)
                        trade_entries[p_code] = {"name": n, "price": float(row.get('buy_price') or 0.0),
                                                  "pct": 0.0, "strategy": "当前持仓",
                                                  "reason": "大级别多头持股"}
                init_codes = list(radar_entries) + list(watch_entries) + list(trade_entries)

                # 步骤 4: 权益曲线
                dates, strat_equity, bench_equity = bridge_ref.get_equity_curve_data()
                x = list(range(len(dates)))

                # 步骤 5: 绩效指标
                from ats.backtest_engine import BacktestEngine
                be = BacktestEngine(bridge_ref)
                metrics = be.calculate_performance_metrics()

                # ── 通过 Qt 线程安全信号将数据派发回主线程 UI ──────────────
                payload = {
                    "final_flow": final_flow,
                    "pos_formatted": pos_formatted,
                    "cash_val": cash_val,
                    "total_assets_val": total_assets_val,
                    "radar_entries": radar_entries,
                    "watch_entries": watch_entries,
                    "trade_entries": trade_entries,
                    "init_codes": init_codes,
                    "x": x,
                    "strat_equity": strat_equity,
                    "bench_equity": bench_equity,
                    "be": be,
                    "metrics": metrics,
                }
                self.db_data_loaded_signal.emit(payload)

            except Exception as e:
                print(f"[ATSMainWindow] load_db_data 后台线程异常: {e}")

        threading.Thread(target=_bg_load, daemon=True, name="ATS-load_db").start()

    def _on_db_data_loaded(self, payload):
        """主线程槽函数：安全接收后台线程计算结果并无卡顿刷新 UI"""
        if not isinstance(payload, dict) or getattr(self, '_is_closing', False):
            return
        try:
            final_flow = payload.get("final_flow")
            if final_flow is not None:
                self.trade_flow_table.update_flow_list(final_flow)

            pos_formatted = payload.get("pos_formatted")
            cash_val = payload.get("cash_val", 1000000.0)
            total_assets_val = payload.get("total_assets_val", 1000000.0)
            if pos_formatted is not None:
                self.position_panel.update_positions(pos_formatted, cash=cash_val, total_assets=total_assets_val)

            # 更新三级池
            radar_entries = payload.get("radar_entries", {})
            watch_entries = payload.get("watch_entries", {})
            trade_entries = payload.get("trade_entries", {})
            if radar_entries or watch_entries or trade_entries:
                self.universe_manager.radar_pool.clear()
                self.universe_manager.watch_pool.clear()
                self.universe_manager.trade_pool.clear()
                self.universe_manager.radar_pool.update(radar_entries)
                self.universe_manager.watch_pool.update(watch_entries)
                self.universe_manager.trade_pool.update(trade_entries)
                radar_list, watch_list, trade_list = self.universe_manager.get_pools()
                self.universe_widget.update_pools(radar_list, watch_list, trade_list)

            init_codes = payload.get("init_codes", [])
            if init_codes:
                self._async_load_stock_history(init_codes)

            # 权益曲线
            x = payload.get("x", [])
            strat_equity = payload.get("strat_equity", [])
            bench_equity = payload.get("bench_equity", [])
            if x and strat_equity:
                self.equity_chart.update_curve(x, strat_equity, bench_equity)

            # 绩效
            be = payload.get("be")
            metrics = payload.get("metrics")
            if be:
                self.backtest_engine = be
            if metrics:
                self.backtest_panel.update_stats(metrics)

            logger.debug("[ATSMainWindow] load_db_data 后台数据已成功安全派发至主线程 UI")
        except Exception as e:
            print(f"[ATSMainWindow] _on_db_data_loaded 回调异常: {e}")

    def on_run_backtest_clicked(self):
        self.status_bar.showMessage("正在读取历史信号与 K 线分时数据库进行多周期回测...")
        self.backtest_panel.lbl_status.setText("状态: 正在测算中...")
        
        try:
            from ats.backtest_engine import BacktestEngine
            engine = BacktestEngine(self.bridge)
            metrics = engine.calculate_performance_metrics()
            self.backtest_panel.update_stats(metrics)
            self.backtest_panel.lbl_status.setText("状态: 回测已完成 (数据已刷新)")
            self.status_bar.showMessage("历史回测计算完成，已更新全部绩效指标。")
        except Exception as e:
            self.backtest_panel.lbl_status.setText("状态: 计算失败")
            self.status_bar.showMessage(f"❌ 回测计算失败: {e}")

    def open_intraday_strategy_dialog(self, code=None, name=None):
        """调起新股分时阶梯策略独立窗口（非模态独立运行，完全不阻塞主界面）"""
        try:
            from ats.ui.intraday_strategy_dialog import PinzhunLadderStandaloneWindow
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            from PyQt6.sip import isdeleted

            engine = IntradayStrategyEngine.get_instance()
            json_target_codes = engine.get_all_target_codes()

            if isinstance(code, bool) or not code:
                # 1. 优先获取主界面当前选中的股票
                if hasattr(self, 'current_selected_code') and self.current_selected_code:
                    code = self.current_selected_code
                elif hasattr(self, 'selected_code') and self.selected_code:
                    code = self.selected_code
                # 2. 其次动态获取 JSON 策略中配置的 target_codes
                elif json_target_codes:
                    code = json_target_codes[0]
                # 3. 再次获取当前行情列表或 Universe 中的首只股票
                elif hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
                    code = str(self.current_df.index[0])
                elif hasattr(self, 'universe_manager') and hasattr(self.universe_manager, 'active_codes') and self.universe_manager.active_codes:
                    code = self.universe_manager.active_codes[0]
                else:
                    code = "688826"

            c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
            if isinstance(name, bool) or not name or name == "未知" or name == c_clean:
                name = self.get_stock_name(c_clean) if hasattr(self, 'get_stock_name') else "新股标的"

            # 自动联动匹配该标的归属的策略
            auto_st = engine.auto_select_strategy(0.0, code=c_clean)
            target_strat_id = auto_st.get("id") if auto_st else (engine.strategies[0].get("id") if engine.strategies else "")

            # 保持持久非模态独立窗口引用，彻底杜绝模态阻塞
            if not hasattr(self, 'ladder_monitor_win') or self.ladder_monitor_win is None or isdeleted(self.ladder_monitor_win):
                self.ladder_monitor_win = PinzhunLadderStandaloneWindow(code=c_clean, name=name, parent=None)
                if target_strat_id:
                    self.ladder_monitor_win.selected_strategy_id = target_strat_id
                    self.ladder_monitor_win._populate_strategy_combo()
                    self.ladder_monitor_win._populate_code_combo()
                    self.ladder_monitor_win._load_mock_or_live_data()
            else:
                self.ladder_monitor_win.switch_to_code(c_clean, name)

            # 将当前最新的行情 DataFrame 传入独立窗口
            if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
                self.ladder_monitor_win.on_realtime_df_update(self.current_df)

            self.ladder_monitor_win.show()
            self.ladder_monitor_win.raise_()
            self.ladder_monitor_win.activateWindow()
        except Exception as e:
            print(f"[ATSMainWindow] 调起独立新股分时策略窗口异常: {e}")

    def _handle_realtime_data(self, data_pkg):
        import pandas as pd
        
        # 1. 识别协议格式与提取 DataFrame 及板块强度数据 (SSOT 架构)
        msg_type = 'UPDATE_DF_ALL'
        df_payload = None
        sector_data = None
        
        if isinstance(data_pkg, dict):
            msg_type = data_pkg.get('type', 'UPDATE_DF_ALL')
            df_payload = data_pkg.get('data')
            sector_data = data_pkg.get('sector_data')
            if df_payload is None:
                # 兼容历史数据结构
                df_payload = data_pkg.get('full_snapshot')
        elif isinstance(data_pkg, pd.DataFrame):
            df_payload = data_pkg
        elif isinstance(data_pkg, tuple) and len(data_pkg) > 0:
            df_payload = data_pkg[0]
            if len(data_pkg) > 1 and isinstance(data_pkg[1], dict):
                sector_data = data_pkg[1].get('sector_data')
            
        # 🛡️ [SSOT 极限性能复用] 若 IPC 数据包包含 TK 赛道探测器的权威板块数据，直接更新热力图，杜绝重复计算
        if sector_data and hasattr(self, 'heatmap_widget') and self.heatmap_widget:
            try:
                self.heatmap_widget.update_from_tk_sector_data(sector_data)
            except Exception as e_sec:
                logger.debug(f"[ATS_Realtime] Update heatmap from TK sector_data failed: {e_sec}")

        if df_payload is None or not isinstance(df_payload, pd.DataFrame) or df_payload.empty:
            return

        # 2. 将提取出的 DataFrame 强制转换为以 code 字符串作为 index (如果后台没有预先处理)
        if not (df_payload.index.name == 'code' and df_payload.index.dtype == object):
            df_payload = df_payload.copy()
            if 'code' in df_payload.columns:
                df_payload['code'] = df_payload['code'].astype(str).str.strip()
                df_payload.set_index('code', inplace=True)
            else:
                df_payload.index = df_payload.index.astype(str).str.strip()
                df_payload.index.name = 'code'

        # 3. 处理全量/增量更新
        if msg_type == 'UPDATE_DF_DIFF' and hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            try:
                df_diff = df_payload
                # 💥 支持 MultiIndex 格式列 (如由 df.compare 产出)
                if isinstance(df_diff.columns, pd.MultiIndex):
                    new_cols = {}
                    for col in df_diff.columns:
                        if isinstance(col, tuple) and len(col) >= 2:
                            base_col, val_type = col[0], col[1]
                            if val_type == 'self':
                                new_cols[base_col] = df_diff[col]
                    df_diff = pd.DataFrame(new_cols, index=df_diff.index)
                # 取两边股票代码的交集
                common_idx = self.current_df.index.intersection(df_diff.index)
                if len(common_idx) > 0:
                    for col in df_diff.columns:
                        if col in self.current_df.columns:
                            try:
                                col_data = df_diff.loc[common_idx, col]
                                valid_mask = col_data.notna()
                                valid_indices = valid_mask[valid_mask].index
                                if len(valid_indices) > 0:
                                    self.current_df.loc[valid_indices, col] = df_diff.loc[valid_indices, col]
                            except Exception:
                                pass
                # 取 diff 中新出现的股票追加进来
                new_idx = df_diff.index.difference(self.current_df.index)
                if len(new_idx) > 0:
                    self.current_df = pd.concat([self.current_df, df_diff.loc[new_idx]])
            except Exception as e:
                print(f"[ATS_Realtime] Apply diff error: {e}")
        else:
            # 全量更新或冷启动
            if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
                # 🛡️【关键防丢失保护】：当收到 IPC 全量更新包且其缺少 category/industry/name 静态列时，从原 current_df 无缝继承！
                for static_col in ['category', 'industry', 'concept', 'name']:
                    if static_col in self.current_df.columns and static_col not in df_payload.columns:
                        df_payload[static_col] = self.current_df[static_col].reindex(df_payload.index)
            self.current_df = df_payload

        # 🛡️【自动缝合与补全静态分类列】：确保 current_df 永远保持完整的 category 板块分类数据
        if self.current_df is not None and not self.current_df.empty and ('category' not in self.current_df.columns or self.current_df['category'].dropna().empty):
            try:
                if hasattr(self, 'heatmap_widget') and hasattr(self.heatmap_widget, '_bidding_stock_to_sector'):
                    b_map = getattr(self.heatmap_widget, '_bidding_stock_to_sector', {})
                    if b_map:
                        self.current_df['category'] = [b_map.get(str(idx).strip(), '') or b_map.get("".join(c for c in str(idx) if c.isdigit()).zfill(6), '') for idx in self.current_df.index]
            except Exception:
                pass

        # Fast vectorized name cache update
        self._update_name_cache_from_df(self.current_df)

        # 🛡️ 实时推送到独立新股阶梯盯盘窗口 (非阻塞)
        if hasattr(self, 'ladder_monitor_win') and self.ladder_monitor_win is not None and self.ladder_monitor_win.isVisible():
            try:
                self.ladder_monitor_win.on_realtime_df_update(self.current_df)
            except Exception:
                pass

        # 🛡️ 实时推送到独立每日涨停看板 (非阻塞)
        from PyQt6.sip import isdeleted
        if hasattr(self, 'daily_limit_up_dialog') and self.daily_limit_up_dialog and not isdeleted(self.daily_limit_up_dialog):
            try:
                sh_pct_val = getattr(self, '_last_sh_pct', 0.0)
                self.daily_limit_up_dialog.update_data_payload(self.current_df, sh_pct_val)
            except Exception:
                pass

        # 4. 更新 UI 显示与计算
        if self.current_df is not None and not self.current_df.empty:
            self.lbl_ipc_status.setText("  IPC 通道: 🔌 实时接入中  |  ")
            self.lbl_ipc_status.setStyleSheet("color: #00ff88; font-weight: bold;")
            
            # 🛡️ 实时行情数据就绪，自动重新计算策略过滤命中集合 (根除启动时无数据导致空集合的联动 Bug)
            if getattr(self, 'query_expr', ''):
                self._recompute_filtered_codes_set()
            
            # 绘制 A 股涨跌幅度直方图
            if 'percent' in self.current_df.columns:
                pcts = self.current_df['percent'].dropna()
                bins = [-999, -8, -6, -4, -2, 0, 2, 4, 6, 8, 999]
                counts = pd.cut(pcts, bins=bins).value_counts().sort_index().tolist()
                
                # 计算统计数据以更新市场温度与家数
                up_count = int((pcts > 0).sum())
                down_count = int((pcts < 0).sum())
                flat_count = int((pcts == 0).sum())
                total_count = up_count + down_count + flat_count
                avg_pct = float(pcts.mean()) if total_count > 0 else 0.0
                market_temp = (up_count / total_count * 100.0) if total_count > 0 else 0.0
                
                stats_dict = {
                    "up": up_count,
                    "down": down_count,
                    "flat": flat_count,
                    "avg": avg_pct,
                    "temp": market_temp
                }
                
                if len(counts) == 10:
                    self.dist_chart.update_data(counts, stats_dict, self.current_df)
            
            # ⚡ 30ms 防抖异步触发 UI 渲染 (极其流畅汇聚高频 IPC 广播数据包)
            self._trigger_realtime_ui_update()
            
            # 🚀 首次收到全量行情数据后，自动加载打开退出前持久化的磁吸/监控窗口 (加速龙头跟踪器、各涨跌明细面板等)
            self._restore_persistent_monitors_on_data_ready()
            
            self.status_bar.showMessage(f"已同步接收到主进程最新实时行情快照 (个股数: {len(self.current_df)})")
            import time
            self._last_recv_t = time.time()
            self._last_data_update_time = self._last_recv_t
            if hasattr(self, '_refresh_statusbar_time_display'):
                self._refresh_statusbar_time_display()
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ATS_Realtime] Received data update: {msg_type}, rows={len(self.current_df)}")

    def _restore_persistent_monitors_on_data_ready(self):
        """
        🚀 在数据 IPC 首次获取完成（self.current_df 就绪）后，自动加载打开退出前持久化的监控窗口：
        1. 🐉 2D/3D 加速龙头追踪器 (DragonLeaderMonitorDialog)
        2. 📊 涨跌分布个股明细面板 (DistributionDetailsDialog)
        """
        if getattr(self, '_monitors_auto_restored', False):
            return
        self._monitors_auto_restored = True
        
        try:
            from tk_gui_modules.gui_config import WINDOW_CONFIG_FILE
            from ats.ui.chart_widgets import _CONFIG_FILE_LOCK
            config_data = {}
            if os.path.exists(WINDOW_CONFIG_FILE):
                with _CONFIG_FILE_LOCK:
                    with open(WINDOW_CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
        except Exception as e:
            print(f"[ATSMainWindow] Read window_config.json error: {e}")
            config_data = {}

        # 1. 恢复加载加速龙头追踪器
        try:
            dragon_cfg = config_data.get("dragon_leader_monitor_dialog", {})
            if dragon_cfg.get("is_open", False):
                logger.info("[ATSMainWindow] IPC数据就绪，自动加载打开持久化的加速龙头监控窗口...")
                self.open_dragon_monitor(restore_state=dragon_cfg, cold_start=True)
        except Exception as e:
            logger.warning(f"[ATSMainWindow] Error auto-restoring dragon monitor: {e}")

        # 1.1 恢复加载 Top 3 强势板块龙头突击跟单榜
        try:
            hot_cfg = config_data.get("hot_sector_leaderboard_dialog", {})
            if hot_cfg.get("is_open", False):
                logger.info("[ATSMainWindow] IPC数据就绪，自动加载打开持久化的龙头突击跟单榜...")
                self.open_hot_sector_leaderboard(restore_state=hot_cfg, cold_start=True)
        except Exception as e:
            logger.warning(f"[ATSMainWindow] Error auto-restoring hot sector leaderboard: {e}")

        # 1.2 恢复加载每日涨停与强势股天梯看板
        try:
            zt_cfg = config_data.get("daily_limit_up_dialog", {})
            if zt_cfg.get("is_open", False):
                logger.info("[ATSMainWindow] IPC数据就绪，自动加载打开持久化的每日涨停看板...")
                self.open_daily_limit_up_analyzer(restore_state=zt_cfg, cold_start=True)
        except Exception as e:
            logger.warning(f"[ATSMainWindow] Error auto-restoring daily limit-up dialog: {e}")

        # 2. 恢复加载涨跌分布个股明细面板
        try:
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_restore_details_dialog_if_saved'):
                logger.info("[ATSMainWindow] IPC数据就绪，自动加载打开持久化的涨跌分布个股明细面板...")
                self.dist_chart._restore_details_dialog_if_saved(cold_start=False)
        except Exception as e:
            logger.warning(f"[ATSMainWindow] Error auto-restoring distribution detail dialogs: {e}")

        # 3. 恢复加载持久化打开的 SBC 独立分时走势图窗口
        try:
            from ats.ui.intraday_strategy_dialog import restore_all_open_sbc_windows
            logger.info("[ATSMainWindow] IPC数据就绪，自动加载打开持久化的 SBC 独立分时窗口...")
            restore_all_open_sbc_windows(self)
        except Exception as e:
            logger.warning(f"[ATSMainWindow] Error auto-restoring SBC chart dialogs: {e}")

    def _trigger_realtime_ui_update(self):
        """防抖异步触发 UI 渲染 (30ms 汇聚高频 IPC 广播包, 防范主线程卡顿)"""
        if not hasattr(self, '_realtime_ui_debounce_timer'):
            from PyQt6.QtCore import QTimer
            self._realtime_ui_debounce_timer = QTimer(self)
            self._realtime_ui_debounce_timer.setSingleShot(True)
            self._realtime_ui_debounce_timer.setInterval(30)
            self._realtime_ui_debounce_timer.timeout.connect(self.refresh_realtime_ui)
        self._realtime_ui_debounce_timer.start(30)

    def _async_load_stock_prices(self, codes):
        if not codes:
            return
        
        codes_to_load = [c for c in codes if c not in self.prices_loading_codes and c not in self.prices_failed_codes]
        if not codes_to_load:
            return
            
        for code in codes_to_load:
            self._pending_price_codes.add(code)
            self.prices_loading_codes.add(code)
            
        # 启动防抖定时器，凑齐 150ms 内的所有价格请求进行一次批处理
        self._batch_price_timer.start(150)

    def _flush_batch_stock_prices(self):
        if not self._pending_price_codes:
            return
        codes_to_load = list(self._pending_price_codes)
        self._pending_price_codes.clear()
        
        logger.debug(f"[ATSMainWindow] Debounce batching price load for {len(codes_to_load)} codes...")
        import threading
        def worker():
            t0 = time.time()
            acquired = self.hdf5_history_lock.acquire(blocking=True, timeout=5.0)
            if not acquired:
                for code in codes_to_load:
                    self.prices_loading_codes.discard(code)
                    self.prices_failed_codes.add(code)
                logger.debug(f"[ATSMainWindow] HDF5 lock busy, postponed price load for {len(codes_to_load)} codes.")
                return
            try:
                from JSONData import sina_data
                s = sina_data.Sina(readonly=True)
                
                valid_codes = [c for c in codes_to_load if c and len(c) == 6]
                if not valid_codes:
                    for code in codes_to_load:
                        self.prices_loading_codes.discard(code)
                        self.prices_failed_codes.add(code)
                    return
                    
                tick_df = s.get_stock_list_data(valid_codes)
                loaded_codes = set()
                if tick_df is not None and not tick_df.empty:
                    for idx, row in tick_df.iterrows():
                        code_str = str(idx).strip().zfill(6)
                        price = float(row.get('close', 0.0))
                        llastp = float(row.get('llastp', 0.0))
                        pct = (price - llastp) / llastp * 100.0 if llastp > 0 else 0.0
                        self.price_pct_cache[code_str] = (price, pct)
                        loaded_codes.add(code_str)
                        
                for code in codes_to_load:
                    self.prices_loading_codes.discard(code)
                    if code not in loaded_codes:
                        self.prices_failed_codes.add(code)
                        
                cost_ms = (time.time() - t0) * 1000.0
                logger.debug(f"[ATSMainWindow] Batch prices loaded: {len(loaded_codes)}/{len(valid_codes)} in {cost_ms:.1f}ms")
                QTimer.singleShot(0, self.refresh_realtime_ui)
            except Exception as e:
                logger.debug(f"[ATSMainWindow] Error loading prices in background: {e}")
                for code in codes_to_load:
                    self.prices_loading_codes.discard(code)
                    self.prices_failed_codes.add(code)
            finally:
                self.hdf5_history_lock.release()
                
        threading.Thread(target=worker, daemon=True).start()

    def _async_load_stock_history(self, codes):
        if not codes:
            return
        
        import time, datetime, random
        now_ts = time.time()
        today = datetime.date.today().isoformat()
        
        sleep_base = 10
        try:
            if hasattr(cct, 'duration_sleep_time'):
                sleep_base = int(cct.duration_sleep_time)
        except Exception:
            pass
        cooldown_sec = sleep_base + random.randint(1, 10)
        
        if self._history_failed_date != today:
            self._history_failed_date = today
            self.history_failed_codes.clear()
        
        def is_cached(c):
            c_clean = ''.join(filter(str.isdigit, str(c)))
            return (c in self.stock_history_cache) or (c_clean in self.stock_history_cache)

        # 只要已经在 self.stock_history_cache 中存过（无论是有数据还是空列表占位），一律判定已缓存，绝对不再重载！
        codes_to_load = [
            c for c in codes
            if not is_cached(c)
            and c not in self.history_loading_codes
            and (c not in self.history_failed_codes or now_ts - self.history_failed_codes[c] > cooldown_sec)
        ]
        if not codes_to_load:
            return
            
        for code in codes_to_load:
            self._pending_history_codes.add(code)
            self.history_loading_codes.add(code)
                
        # 启动防抖定时器，凑齐 250ms 内的所有历史查询进行一次性 HDF5 批量 select
        self._batch_history_timer.start(250)

    def _flush_batch_stock_history(self):
        if not self._pending_history_codes:
            return
        codes_to_load = list(self._pending_history_codes)
        self._pending_history_codes.clear()
        
        logger.debug(f"[ATSHistory] Debounce batching history load for {len(codes_to_load)} codes...")
        import threading
        def worker():
            import time as _time
            import pandas as pd
            import os
            t0 = _time.time()

            acquired = self.hdf5_history_lock.acquire(blocking=True, timeout=5.0)
            if not acquired:
                fail_ts = _time.time()
                for code in codes_to_load:
                    self.history_loading_codes.discard(code)
                    self.history_failed_codes[code] = fail_ts
                logger.debug(f"[ATSHistory] HDF5 lock busy, postponed {len(codes_to_load)} codes.")
                return

            try:
                path = r'g:\sina_MultiIndex_data.h5'
                if not os.path.exists(path):
                    fail_ts = _time.time()
                    for code in codes_to_load:
                        self.history_loading_codes.discard(code)
                        self.history_failed_codes[code] = fail_ts
                    logger.debug(f"[ATSHistory] HDF5 File missing: {path}")
                    return

                MAX_RETRY = 3
                RETRY_SLEEP = 0.5

                df = None
                last_err = None
                raw_code_map = {}
                for c in codes_to_load:
                    c_clean = ''.join(filter(str.isdigit, str(c)))
                    if c_clean:
                        raw_code_map[c_clean] = c

                query_codes = list(raw_code_map.keys())

                for attempt in range(MAX_RETRY):
                    try:
                        with pd.HDFStore(path, mode='r') as store:
                            code_query = ", ".join([f"'{c}'" for c in query_codes])
                            df = store.select('/all_30', where=f"code in [{code_query}]")
                        last_err = None
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < MAX_RETRY - 1:
                            _time.sleep(RETRY_SLEEP)

                if last_err is not None:
                    fail_ts = _time.time() - (300 - 10)
                    for code in codes_to_load:
                        self.history_loading_codes.discard(code)
                        self.history_failed_codes[code] = fail_ts
                    logger.debug(f"[ATSHistory] HDF5 read error: {last_err}")
                    return

                for code in codes_to_load:
                    self.history_failed_codes.pop(code, None)

                loaded_codes = set()
                if df is not None and not df.empty:
                    dates = pd.to_datetime(df.index.get_level_values('ticktime')).date
                    grouped = df.groupby([df.index.get_level_values('code'), dates])['close'].last()

                    for (c_clean, d), val in grouped.items():
                        c_clean_str = str(c_clean).strip().zfill(6)
                        d_str = d.strftime("%Y-%m-%d")
                        orig_code = raw_code_map.get(c_clean_str, c_clean_str)
                        
                        hist = self.stock_history_cache.get(c_clean_str, [])
                        if not any(item[0] == d_str for item in hist):
                            hist.append((d_str, float(val)))
                            
                        self.stock_history_cache[c_clean_str] = hist
                        self.stock_history_cache[orig_code] = hist
                        loaded_codes.add(c_clean_str)
                        loaded_codes.add(orig_code)

                    for code in codes_to_load:
                        c_clean = ''.join(filter(str.isdigit, str(code)))
                        if c_clean in self.stock_history_cache:
                            self.stock_history_cache[c_clean].sort(key=lambda x: x[0])
                        if code in self.stock_history_cache:
                            self.stock_history_cache[code].sort(key=lambda x: x[0])

                # 无论是否有历史数据，查询结束后均建立 Cache 记录（无数据的存空列表占位），防二次轮询触发
                fail_ts = _time.time()
                for code in codes_to_load:
                    c_clean = ''.join(filter(str.isdigit, str(code)))
                    self.history_loading_codes.discard(code)
                    if code not in loaded_codes and c_clean not in loaded_codes:
                        self.stock_history_cache[code] = []
                        self.stock_history_cache[c_clean] = []
                        self.history_failed_codes[code] = fail_ts

                cost_ms = (_time.time() - t0) * 1000.0
                logger.debug(f"[ATSHistory] Batch history loaded: {len(loaded_codes)}/{len(codes_to_load)} in {cost_ms:.1f}ms")

                QTimer.singleShot(0, self.refresh_realtime_ui)
            finally:
                self.hdf5_history_lock.release()
                
        threading.Thread(target=worker, daemon=True).start()

    def refresh_realtime_ui(self):
        """
        ⚡ 轻量级 IPC 数据处理入口 — 主线程只做防重入检查和 Worker 启动 (<5ms)
        重量级计算 (signal ledger / volume profiler / swing_rows) 全部在 LedgerUpdateWorker 后台线程执行。
        UI 渲染结果通过 results_ready 信号在主线程的 _on_ledger_results 中完成。
        """
        if getattr(self, '_is_closing', False):
            return

        has_df = self.current_df is not None and not self.current_df.empty

        # ── 快速任务：检查缺少行情/历史数据的标的，异步补齐 ──────────────────────
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = set(GlobalFavoriteManager().get_favorite_stocks())
        except Exception:
            fav_stocks = set()
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'get_favorite_stocks_set'):
            fav_stocks = fav_stocks | self.signal_ledger.get_favorite_stocks_set()

        pool_codes = (list(self.universe_manager.radar_pool.keys()) +
                      list(self.universe_manager.watch_pool.keys()) +
                      list(self.universe_manager.trade_pool.keys()))
        all_codes = list(dict.fromkeys(pool_codes + [c for c in fav_stocks if c]))

        if has_df:
            # 池子名称与价格快速更新（纯内存操作, <5ms）
            missing_realtime_codes = []
            for pool in [self.universe_manager.radar_pool,
                         self.universe_manager.watch_pool,
                         self.universe_manager.trade_pool]:
                for code in list(pool.keys()):
                    real_name = self.get_stock_name(code)
                    if real_name and real_name not in ('未知', '重点标的', ''):
                        pool[code]['name'] = real_name
                    row = self.get_df_row_safe(self.current_df, code)
                    code_clean = (''.join(c for c in str(code) if c.isdigit()).zfill(6)
                                  if any(c.isdigit() for c in str(code)) else str(code).strip())
                    if row is not None:
                        pool[code]['price'] = float(row.get('close', row.get('price', 0.0)))
                        pool[code]['pct'] = float(row.get('percent', 0.0))
                    elif code_clean in self.price_pct_cache:
                        pool[code]['price'], pool[code]['pct'] = self.price_pct_cache[code_clean]
                    elif code in self.price_pct_cache:
                        pool[code]['price'], pool[code]['pct'] = self.price_pct_cache[code]
                    else:
                        pool[code]['price'] = 0.0
                        pool[code]['pct'] = 0.0
                        missing_realtime_codes.append(code)

            missing_realtime_codes = [c for c in missing_realtime_codes
                                      if c not in self.prices_loading_codes and c not in self.prices_failed_codes]
            if missing_realtime_codes:
                self._async_load_stock_prices(missing_realtime_codes)

        # 异步补齐历史数据（不在主线程阻塞）
        now_ts = time.time()
        missing_history_codes = [
            c for c in all_codes
            if c not in self.stock_history_cache
            and c not in self.history_loading_codes
            and (c not in self.history_failed_codes or now_ts - self.history_failed_codes[c] > 300)
        ]
        if missing_history_codes:
            self._async_load_stock_history(missing_history_codes)

        # ── 更新已打开的个股详情弹窗 (0ms, 主线程直接刷 visible widget) ──────────
        if has_df:
            if hasattr(self, 'trade_flow_table') and self.trade_flow_table is not None:
                try:
                    self.trade_flow_table.update_realtime_prices(self.current_df)
                except Exception:
                    pass

            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, StockDetailDialog) and widget.isVisible():
                    w_code = widget.code
                    if w_code in self.current_df.index:
                        w_row = self.current_df.loc[w_code]
                        import pandas as pd
                        if isinstance(w_row, pd.DataFrame):
                            w_row = w_row.iloc[0]
                        widget.update_data(w_row)

        # ── 防重入：若上一个 Worker 仍在运行，跳过本次触发 ──────────────────────
        if getattr(self, '_ledger_worker_busy', False):
            logger.debug('[ATS_Realtime] LedgerWorker busy, skipping this tick')
            return

        if not has_df:
            # 无行情数据时仅同步 universe tree
            self.universe_manager.sync_from_ledger(self.signal_ledger, price_pct_cache=self.price_pct_cache)
            radar_list, watch_list, trade_list = self.universe_manager.get_pools()
            self.universe_widget.update_pools(radar_list, watch_list, trade_list)
            return

        # ── 同步推送实时行情给新股次新股主控面板 ──
        if hasattr(self, 'new_stock_panel') and self.new_stock_panel is not None:
            try:
                self.new_stock_panel.update_from_ipc_df(self.current_df)
            except Exception as e_nsp:
                logger.debug(f"[ATSMainWindow] new_stock_panel update from ipc error: {e_nsp}")

        # ── 启动后台 Worker ─────────────────────────────────────────────────────
        import datetime
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        worker = LedgerUpdateWorker(
            df_all=self.current_df,
            signal_ledger=self.signal_ledger,
            volume_profiler=self.volume_profiler,
            session_snapshot=self.session_snapshot,
            swing_tracker=self.swing_tracker,
            stock_history_cache=self.stock_history_cache,
            price_pct_cache=self.price_pct_cache,
            name_cache=self.name_cache,
            fav_stocks=fav_stocks,
            universe_manager=self.universe_manager,
            today_str=today_str,
        )
        worker.results_ready.connect(self._on_ledger_results)
        worker.finished.connect(worker.deleteLater)
        self._ledger_worker_busy = True
        self._ledger_worker = worker  # 持有引用，防止提前 GC
        worker.start()

    def _on_ledger_results(self, swing_rows, fav_rows, sh_pct, alpha_signals, stats_str):
        """
        ⚡ Worker 计算完成回调 — 主线程纯 UI 渲染 (<20ms, 零卡顿)
        只做表格与状态栏刷新，不含任何数据计算或 IO。
        """
        self._ledger_worker_busy = False

        if getattr(self, '_is_closing', False):
            return

        # 记录 alpha 信号（内存去重，防重入）
        if alpha_signals:
            current_batch_alpha = []
            for code, name, pct_val, sh_pct_v, rs_val, resonance in alpha_signals:
                current_batch_alpha.append((code, name))
                self._record_alpha_signal(code, name, pct_val, sh_pct_v, rs_val, resonance)
            if current_batch_alpha:
                self._last_batch_signal_codes = current_batch_alpha

        # 缓存数据供 Tier 2 / Tier 3 异步排队使用
        self._pending_swing_rows = swing_rows
        self._pending_fav_rows = fav_rows
        self._pending_sh_pct = sh_pct

        # ⚡ Tier 1: 立即渲染当前激活的 Tab
        active_tab_idx = self.top_tabs.currentIndex() if hasattr(self, 'top_tabs') else 0
        if active_tab_idx == 0:
            if hasattr(self, 'favorite_panel') and fav_rows:
                self.favorite_panel.update_favorite_rows(fav_rows)
        else:
            if swing_rows:
                self.swing_table.update_data_list(swing_rows)

        # 更新左侧三级池 tree
        radar_list, watch_list, trade_list = self.universe_manager.get_pools()
        self.universe_widget.update_pools(radar_list, watch_list, trade_list)

        # 状态栏
        if stats_str:
            self.status_bar.showMessage(stats_str)

        # 🚀 Tier 2 (10ms 后): 补齐渲染非激活 Tab
        if hasattr(self, '_async_tier2_timer'):
            self._async_tier2_timer.start(10)

        # 🚀 Tier 3 (30ms 后): 板块热力图 + 独立副弹窗
        if hasattr(self, '_async_tier3_timer'):
            self._async_tier3_timer.start(30)

    def _async_refresh_tier2(self):
        """Tier 2 (10ms 延迟): 异步渲染未在激活态的副 Tab 看板"""
        if getattr(self, '_is_closing', False):
            return
        active_tab_idx = self.top_tabs.currentIndex() if hasattr(self, 'top_tabs') else 0
        if active_tab_idx == 0:
            # 补齐更新未在激活态的 MA20d 跟踪器
            if self._pending_swing_rows:
                self.swing_table.update_data_list(self._pending_swing_rows)
        else:
            # 补齐更新未在激活态的重点关注
            if hasattr(self, 'favorite_panel') and self._pending_fav_rows:
                self.favorite_panel.update_favorite_rows(self._pending_fav_rows)

    def _async_refresh_tier3(self):
        """Tier 3 (30ms 延迟): 异步加载右侧板块热力图与独立的辅助监控弹窗 (带防抖保护，杜绝主线程卡顿)"""
        if getattr(self, '_is_closing', False):
            return
        if hasattr(self, 'heatmap_widget'):
            self.heatmap_widget.load_live_sectors(force=False, current_df=self.current_df)

        from PyQt6.sip import isdeleted

        sh_pct = getattr(self, '_pending_sh_pct', 0.0)
        if self.dragon_monitor_dialog and not isdeleted(self.dragon_monitor_dialog) and self.dragon_monitor_dialog.isVisible():
            try:
                self.dragon_monitor_dialog.update_data(self.current_df, sh_pct)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating dragon monitor: {e}")

        if hasattr(self, '_equity_pop_dialog') and self._equity_pop_dialog is not None and not isdeleted(self._equity_pop_dialog) and self._equity_pop_dialog.isVisible():
            try:
                self._equity_pop_dialog.update_data(self.current_df)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating equity pop dialog: {e}")

        if hasattr(self, '_sector_detail_dialog') and self._sector_detail_dialog is not None and not isdeleted(self._sector_detail_dialog) and self._sector_detail_dialog.isVisible():
            try:
                self._sector_detail_dialog.update_data(self.current_df)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating sector detail dialog: {e}")


    def _update_signal_ledger(self, df_all):
        """增量更新信号账本（核心方法 — 替代全量 run_pipeline_filtering）

        核心逻辑:
        1. 扫描全市场 DataFrame，计算 MA20 偏离度
        2. 偏离度在范围内的标的 → 写入 SignalLedger
        3. 已存在的信号 → 仅更新最新价格，不改变首次发现时间
        4. 更新 VolumeProfiler 量能画像
        5. 定时执行 SessionSnapshot 快照持久化

        时间复杂度: O(候选数) 而非 O(全市场), 大幅降低 UI 开销
        """
        import pandas as pd

        if df_all is None or df_all.empty:
            return

        # 1. 更新大盘量能环境上下文
        self.volume_profiler.update_market_context(df_all)

        # 2. 定位 MA20 列
        ma20_col = None
        for col_name in ['ma20d', 'ma20', 'MA20', 'ma20_series']:
            if col_name in df_all.columns:
                ma20_col = col_name
                break

        if not ma20_col:
            return

        # 3. 计算全市场偏离度（向量化计算，极速）
        close_col = 'close' if 'close' in df_all.columns else 'price'
        if close_col not in df_all.columns:
            return

        close_s = pd.to_numeric(df_all[close_col], errors='coerce')
        safe_ma20 = pd.to_numeric(df_all[ma20_col], errors='coerce').replace(0, float('nan'))
        dev_series = (close_s - safe_ma20) / safe_ma20 * 100.0

        # 4. 筛选偏离度在目标范围内 OR 已在 ledger 中的标的
        tracked_codes = set(self.signal_ledger.entries.keys())
        valid_mask = (
            ((dev_series >= self.signal_ledger.DEVIATION_MIN) &
             (dev_series <= self.signal_ledger.DEVIATION_MAX)) |
            df_all.index.isin(tracked_codes)
        )
        target_df = df_all[valid_mask]

        # 5. 增量写入信号账本（第一步：转换为 dict 向量化高效遍历，比 iterrows 快 30 倍）
        valid_target_codes = []
        target_dict = target_df.to_dict('index')
        for code, row in target_dict.items():
            code_str = str(code).strip()
            if not code_str or code_str in ('sh000001', 'sz399001', 'sz399006', '000001.SH', '399001.SZ', '399006.SZ'):
                continue  # 跳过指数
                
            try:
                # 预提取价格与均线值，确保合法性
                price = float(row.get(close_col, 0.0))
                ma20_val = 0.0
                try:
                    ma20_val = float(row.get(ma20_col, 0.0))
                except (TypeError, ValueError):
                    pass
                    
                if price <= 0 or ma20_val <= 0:
                    continue
                    
                self.volume_profiler.update_profile(code_str, row)
                valid_target_codes.append((code_str, row, price, ma20_val))
            except Exception:
                continue

        # 核心板块分析第二步: 运行板块动能与共振分析 (识别板块内谁是带队大哥, 谁是跟风小弟并提权评分)
        active_codes_list = [item[0] for item in valid_target_codes]
        self.volume_profiler.analyze_sector_resonance(active_codes=active_codes_list)

        # 第三步: 将包含板块共振和连阳加权后的最终评分，正式录入信号账本
        for code_str, row, price, ma20_val in valid_target_codes:
            try:
                name = str(row.get('name', ''))
                pct = float(row.get('percent', 0.0))
                deviation = (price - ma20_val) / ma20_val * 100.0
                
                # 获取经过板块共振和多日连阳加成修正后的最终 vol_score
                vol_score = self.volume_profiler.get_volume_score(code_str)

                # 写入信号账本（新信号锁定首次发现时间，已有信号仅更新最新数据）
                self.signal_ledger.record_signal(
                    code=code_str,
                    name=name,
                    price=price,
                    pct=pct,
                    deviation=deviation,
                    row=row,
                    volume_score=vol_score,
                )
            except Exception:
                continue

        # 6. 定时快照持久化
        if self.session_snapshot.should_snapshot():
            self.session_snapshot.save_snapshot(self.signal_ledger)
            self.session_snapshot.cleanup_old_snapshots()

        # 6.5 收盘盘后自动生成当日总结快照 (必须是真实交易日 且 15:00 之后)
        import datetime
        now_dt = datetime.datetime.now()
        if cct.get_trade_date_status() and now_dt.hour >= 15:
            self.session_snapshot.save_daily_summary(self.signal_ledger)

        # 6.6 清理不再追踪的旧股票量能画像 (防 24x7 内存累积)
        if hasattr(self.signal_ledger, "get_all_tracked_codes"):
            tracked_codes = self.signal_ledger.get_all_tracked_codes()
        elif hasattr(self.signal_ledger, "entries") and isinstance(self.signal_ledger.entries, dict):
            tracked_codes = [code for code, entry in self.signal_ledger.entries.items()
                             if getattr(entry, 'tier', '') in ('RADAR', 'WATCH', 'TRADE')]
        else:
            tracked_codes = []

        if hasattr(self, "volume_profiler") and hasattr(self.volume_profiler, "cleanup_stale"):
            self.volume_profiler.cleanup_stale(tracked_codes)

        # 7. 状态栏显示信号统计
        if hasattr(self.signal_ledger, "get_stats"):
            stats = self.signal_ledger.get_stats()
        elif hasattr(self.signal_ledger, "entries") and isinstance(self.signal_ledger.entries, dict):
            tier_counts = {}
            for entry in self.signal_ledger.entries.values():
                t = getattr(entry, 'tier', 'RADAR')
                tier_counts[t] = tier_counts.get(t, 0) + 1
            stats = {
                'tiers': tier_counts,
                'today_new': getattr(self.signal_ledger, '_signal_count', len(self.signal_ledger.entries))
            }
        else:
            stats = {'tiers': {}, 'today_new': 0}
        tier_info = stats.get('tiers', {})
        radar_n = tier_info.get('RADAR', 0)
        watch_n = tier_info.get('WATCH', 0)
        trade_n = tier_info.get('TRADE', 0)

        # 大盘环境标签
        env_label = ''
        if self.volume_profiler.market_context.is_rebound_from_shrink:
            env_label = f' | 🔥 缩量{self.volume_profiler.market_context.consecutive_market_shrink_days}日后反弹'

        self.status_bar.showMessage(
            f"📊 信号池: 候选 {radar_n} | 精选 {watch_n} | 实盘 {trade_n} | "
            f"今日新发现: {stats.get('today_new', 0)}{env_label}"
        )

    def rearrange_all_sbc_windows(self):
        """【🪟 自动平铺重排 SBC 独立分时走势图窗口】"""
        try:
            from ats.ui.intraday_strategy_dialog import rearrange_all_sbc_windows
            rearrange_all_sbc_windows(self)
        except Exception as e:
            logger.error(f"[ATSMainWindow] Error rearranging SBC windows: {e}")

    def _open_signal_detail_dialog(self):
        """点击按钮直接弹出/唤醒 [实时实盘个股详情] 提示窗口 (自动归纳 SignalLedger、TDX 信号及历史精选)"""
        signal_list = []
        seen = set()

        # 1. 优先从 SignalLedger 按 priority_score 降序与 TDX 标签提取全量已被锁定/提醒的强势个股
        if hasattr(self, 'signal_ledger') and hasattr(self.signal_ledger, 'entries') and self.signal_ledger.entries:
            sorted_entries = sorted(
                self.signal_ledger.entries.values(),
                key=lambda e: (
                    1 if getattr(e, 'tdx_label', '') else 0,
                    getattr(e, 'priority_score', 0.0),
                    getattr(e, 'first_seen_ts', 0.0)
                ),
                reverse=True
            )
            for entry in sorted_entries:
                c_str = str(getattr(entry, 'code', '')).strip().zfill(6)
                if c_str and c_str not in seen:
                    seen.add(c_str)
                    n_str = getattr(entry, 'name', '')
                    if not n_str or n_str == c_str or n_str.isdigit():
                        n_str = self.get_stock_name(c_str)
                    
                    # 恢复默认模式，仅对通达信 (TDX) 信号单独增加 🔔 标记
                    if getattr(entry, 'tdx_label', '') or getattr(entry, 'signal_source', '') == 'TDX':
                        if not n_str.startswith('🔔'):
                            n_str = f"🔔 {n_str}"
                    signal_list.append((c_str, n_str))

        # 2. 补充 _last_batch_signal_codes 逆市/共振及 TDX 最新信号
        last_batch = getattr(self, "_last_batch_signal_codes", None) or []
        for item in last_batch:
            if isinstance(item, (tuple, list)):
                c_clean, n_clean = str(item[0]).strip().zfill(6), item[1]
            else:
                c_clean = str(item).strip().zfill(6)
                n_clean = self.get_stock_name(c_clean)
            if not n_clean or n_clean == c_clean or str(n_clean).isdigit():
                n_clean = self.get_stock_name(c_clean)
            if c_clean and c_clean not in seen:
                seen.add(c_clean)
                signal_list.append((c_clean, n_clean))

        # 3. 补充 SwingStateTable 大级别回调跟踪器中的个股
        if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
            tbl = self.swing_table.table
            for r in range(tbl.rowCount()):
                c_item = tbl.item(r, 0)
                n_item = tbl.item(r, 1)
                if c_item:
                    c_clean = c_item.text().strip().zfill(6)
                    if c_clean and c_clean not in seen:
                        seen.add(c_clean)
                        n_str = n_item.text().strip() if n_item else self.get_stock_name(c_clean)
                        signal_list.append((c_clean, n_str))

        target_code = "000039"
        target_name = "中集集团"
        if signal_list:
            target_code, target_name = signal_list[0][0], signal_list[0][1]

        self.on_stock_clicked(target_code, target_name, batch_codes=signal_list)

    def _open_equity_pop_dialog(self):
        """打开/唤醒资金收益曲线及全市场走势独立放大查看窗口"""
        from PyQt6.sip import isdeleted
        if not hasattr(self, '_equity_pop_dialog') or self._equity_pop_dialog is None or isdeleted(self._equity_pop_dialog):
            self._equity_pop_dialog = EquityPopDialog(parent=self)
            
        if hasattr(self, 'current_df') and self.current_df is not None:
            self._equity_pop_dialog.update_data(self.current_df)

        if hasattr(self, 'bridge') and self.bridge:
            try:
                dates, strat_equity, bench_equity = self.bridge.get_equity_curve_data()
                x = list(range(len(dates)))
                self._equity_pop_dialog.equity_chart.update_curve(x, strat_equity, bench_equity)
            except Exception as e:
                print(f"[ATSMainWindow] Sync equity curve error: {e}")

        self._equity_pop_dialog.show()
        self._equity_pop_dialog.raise_()
        self._equity_pop_dialog.activateWindow()

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
                print(f"[ATSMainWindow] Standard StockSender send failed: {e}")

        # 兜底静默剪贴板注入
        try:
            from PyQt6.QtWidgets import QApplication
            cb = QApplication.clipboard()
            if cb:
                cb.setText(code_clean)
        except Exception:
            pass

    def locate_stock_in_tree(self, code: str, auto_popup: bool = False, bring_tdx_to_top: bool = False):
        """自动在 Universe 树、MA20d回调跟踪器表格与重点关注列表中高亮定位显示行，并自动广播联动 TDX 通达信"""
        if not code:
            return
        target_code = str(code).strip()

        # 1. 树定位高亮 (UniverseTree)
        if hasattr(self, "universe_tree") and self.universe_tree is not None:
            try:
                self.universe_tree.select_code(target_code)
            except Exception:
                pass

        # 2. 大级别 MA20d 回调跟踪器表格 (SwingStateTable) 自动定位高亮显示行
        if hasattr(self, "swing_table") and hasattr(self.swing_table, "table"):
            try:
                tbl = self.swing_table.table
                for row in range(tbl.rowCount()):
                    item = tbl.item(row, 0)
                    if item and item.text().strip() == target_code:
                        tbl.setCurrentCell(row, 0)
                        tbl.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                        break
            except Exception:
                pass

        # 3. 重点关注面板表格 (FavoritePanel) 自动定位高亮显示行
        if hasattr(self, "favorite_panel") and hasattr(self.favorite_panel, "table"):
            try:
                tbl_fav = self.favorite_panel.table
                for row in range(tbl_fav.rowCount()):
                    item = tbl_fav.item(row, 0)
                    if item and item.text().strip() == target_code:
                        tbl_fav.setCurrentCell(row, 0)
                        tbl_fav.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
                        break
            except Exception:
                pass

        # 4. 秒级自动联动 TDX 通达信 (仅在显式请求时置顶通达信)
        self.broadcast_code_link(target_code, bring_tdx_to_top=bring_tdx_to_top)

        # 5. 仅在用户手动点击 Toast 时 (auto_popup=True) 自动弹出个股详情小窗口
        if auto_popup:
            try:
                name_str = target_code
                if hasattr(self, "get_stock_name"):
                    name_str = self.get_stock_name(target_code)
                batch_list = getattr(self, "_last_batch_signal_codes", None)
                self.on_stock_clicked(target_code, name_str, batch_codes=batch_list)
            except Exception:
                pass

    def _record_alpha_signal(self, code, name, pct_val, sh_pct, rs_val, resonance):
        """持久化记录大盘偏离共振信号，提供每日复盘与实时跟踪 (内存级极速去重 + 异步防抖落盘, 绝对零主线程 IO)"""
        import os
        import json
        import time
        
        # 仅在有意义的逆市/共振强信号时记录
        if resonance not in ("逆市抗跌", "大盘共振"):
            return False

        today_date = time.strftime("%Y-%m-%d")
        
        # 自动迁移旧路径下的所有 ats_alpha_tracker_*.json 文件到新的 datacsv 目录下
        try:
            from sys_utils import get_app_root
            data_dir = os.path.join(get_app_root(), "datacsv")
            if not os.path.exists(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                
            old_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            if os.path.exists(old_data_dir) and old_data_dir != data_dir:
                import shutil
                for fname in os.listdir(old_data_dir):
                    if fname.startswith("ats_alpha_tracker_") and fname.endswith(".json"):
                        old_filepath = os.path.join(old_data_dir, fname)
                        new_filepath = os.path.join(data_dir, fname)
                        if os.path.exists(old_filepath) and not os.path.exists(new_filepath):
                            shutil.copy2(old_filepath, new_filepath)
        except Exception:
            pass

        # 初始化内存锁与记录列表，仅启动时读一次磁盘
        if getattr(self, "_recorded_alpha_stocks", None) is None or getattr(self, "_recorded_alpha_today", None) != today_date:
            self._recorded_alpha_stocks = {}  # {code: max_pct_val}
            self._recorded_alpha_list = []
            self._recorded_alpha_today = today_date
            
            try:
                from sys_utils import get_app_root
                data_dir = os.path.join(get_app_root(), "datacsv")
                log_path = os.path.join(data_dir, f"ats_alpha_tracker_{today_date}.json")
                if os.path.exists(log_path):
                    with open(log_path, 'r', encoding='utf-8') as f:
                        existing_records = json.load(f)
                        self._recorded_alpha_list = existing_records if isinstance(existing_records, list) else []
                        for rec in self._recorded_alpha_list:
                            c = rec.get('code')
                            p_str = str(rec.get('pct', '0%')).replace('%', '').replace('+', '')
                            try:
                                p_float = float(p_str)
                            except ValueError:
                                p_float = 0.0
                            if c:
                                if c not in self._recorded_alpha_stocks or p_float > self._recorded_alpha_stocks[c]:
                                    self._recorded_alpha_stocks[c] = p_float
            except Exception:
                pass

        # 检查是否重复：若当天已记录且当前涨跌幅未超过上次记录的 2.0% 以上（未发生重大突破），则直接跳过去重
        last_pct = self._recorded_alpha_stocks.get(code)
        if last_pct is not None and (pct_val - last_pct) < 2.0:
            return False

        # 更新内存记录
        self._recorded_alpha_stocks[code] = max(pct_val, last_pct if last_pct is not None else -999.0)

        # 仅对暴拉偏离>=5.0%且偏离>=4.0%的排头黑马才触发系统 Toast 弹窗与语音 (杜绝刷屏)
        if pct_val >= 5.0 and (pct_val - sh_pct) >= 4.0 and last_pct is None:
            try:
                from PyQt6.QtWidgets import QApplication
                if QApplication.instance():
                    from ats.alert_notifier import AlertNotifier
                    AlertNotifier().notify_special_signal(
                        code, name,
                        reason=f"{resonance} | 暴拉偏离大盘: {pct_val - sh_pct:+.2f}%",
                        score=90.0,
                        parent=self
                    )
            except Exception:
                pass

        # 纯内存添加记录，绝不进行主线程阻塞式 IO 读写
        time_str = time.strftime("%H:%M:%S")
        if not hasattr(self, '_recorded_alpha_list') or self._recorded_alpha_list is None:
            self._recorded_alpha_list = []
            
        self._recorded_alpha_list.append({
            "time": time_str,
            "code": code,
            "name": name,
            "pct": f"{pct_val:+.2f}%",
            "index_pct": f"{sh_pct:+.2f}%",
            "relative_strength": f"{rs_val:+.2f}%",
            "type": resonance
        })
        
        if len(self._recorded_alpha_list) > 1000:
            self._recorded_alpha_list = self._recorded_alpha_list[-1000:]
            
        # 防抖后台异步落盘
        self._request_alpha_flush_debounced(today_date)
        print(f"[ATSAlphaTracker] 内存记录强势信号: {code} ({name}) {pct_val:+.2f}% {resonance}")
        return True

    def _request_alpha_flush_debounced(self, today_date):
        """500ms 防抖后台线程落盘 alpha 信号记录 (异步子线程, 绝对不占用 GUI 主线程)"""
        if not hasattr(self, '_alpha_flush_timer'):
            from PyQt6.QtCore import QTimer
            self._alpha_flush_timer = QTimer(self)
            self._alpha_flush_timer.setSingleShot(True)
            self._alpha_flush_timer.setInterval(500)
            self._alpha_flush_timer.timeout.connect(lambda: self._flush_alpha_records_to_disk(today_date))
        self._alpha_flush_timer.start(500)

    def _flush_alpha_records_to_disk(self, today_date):
        if not hasattr(self, '_recorded_alpha_list') or not self._recorded_alpha_list:
            return
        import threading
        records_copy = list(self._recorded_alpha_list)
        def worker():
            try:
                from sys_utils import get_app_root
                data_dir = os.path.join(get_app_root(), "datacsv")
                os.makedirs(data_dir, exist_ok=True)
                log_path = os.path.join(data_dir, f"ats_alpha_tracker_{today_date}.json")
                with open(log_path, 'w', encoding='utf-8') as f:
                    json.dump(records_copy, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[ATSAlphaTracker] Background flush error: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _handle_realtime_signal(self, signal):
        if not signal:
            return
        code = signal.get('code')
        name = signal.get('name')
        action = signal.get('action')
        reason = signal.get('reason') or '实时指标共振'
        self.status_bar.showMessage(f"🔔 [实时信号广播] {code} {name} -> 建议: {action} ({reason})")

    def load_font_size(self) -> int:
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            with CONFIG_FILE_LOCK:
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        return int(data.get("ats_font_size", 9))  # 默认降为更紧凑的 9pt
        except Exception as e:
            print(f"[ATSMainWindow] Error loading font size: {e}")
        return 9

    def save_font_size(self, size: int):
        try:
            from ats.ui.styles import save_config_node
            save_config_node("ats_font_size", size)
        except Exception as e:
            print(f"[ATSMainWindow] Error saving font size: {e}")

    def apply_qss_with_font_size(self, size: int):
        import re
        from PyQt6.QtWidgets import QApplication, QTableView, QTreeView
        
        app = QApplication.instance()
        if app:
            app._is_updating_font = True
            
        try:
            qss = DARK_THEME_QSS
            qss = re.sub(r'font-size:\s*\d+(\.\d+)?pt;', f'font-size: {size}pt;', qss)
            self.setStyleSheet(qss)
            
            # Force restore column widths for all tables/trees with persistent headers
            for table in self.findChildren(QTableView):
                if hasattr(table, "restore_header_state"):
                    table.restore_header_state()
            for tree in self.findChildren(QTreeView):
                if hasattr(tree, "restore_header_state"):
                    tree.restore_header_state()
        finally:
            if app:
                app._is_updating_font = False

    def decrease_font_size(self):
        if self.current_font_size > 7:
            self.current_font_size -= 1
            self.lbl_font_size.setText(f" {self.current_font_size} pt ")
            self.save_font_size(self.current_font_size)
            self.apply_qss_with_font_size(self.current_font_size)

    def increase_font_size(self):
        if self.current_font_size < 16:
            self.current_font_size += 1
            self.lbl_font_size.setText(f" {self.current_font_size} pt ")
            self.save_font_size(self.current_font_size)
            self.apply_qss_with_font_size(self.current_font_size)

    def _on_main_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        self._request_save_layout_debounced()

    def _on_center_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        self._request_save_layout_debounced()

    def _on_right_splitter_moved(self, pos, index):
        if getattr(self, '_is_restoring_sizes', False):
            return
        self._request_save_layout_debounced()

    def _request_save_layout_debounced(self):
        """用户拖动分隔线时 500ms 防抖自动持久化落盘"""
        if getattr(self, '_is_closing', False) or getattr(self, '_is_restoring_sizes', False):
            return
        if not hasattr(self, '_splitter_save_timer'):
            from PyQt6.QtCore import QTimer
            self._splitter_save_timer = QTimer(self)
            self._splitter_save_timer.setSingleShot(True)
            self._splitter_save_timer.setInterval(500)
            self._splitter_save_timer.timeout.connect(self._save_layout_state)
        self._splitter_save_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_layout_restored_on_show', False):
            self._layout_restored_on_show = True
            # 延时 60ms 在窗口完成 showMaximized/物理屏幕渲染后再强行精准对齐一次物理尺寸
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(60, self._restore_layout_state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 注意：Qt 原生 QSplitter 在已配置 setStretchFactor(0, 0), (1, 1), (2, 0) 时
        # 会自动在 resize 时保持左右两栏物理宽度不变、中间主看板独占全量伸缩空间。
        # 绝不在此处重新计算 ratio 覆盖 setSizes，彻底防范左右栏被无谓挤压!

    def _restore_layout_state(self):
        try:
            import json
            import os
            from sys_utils import get_app_root, get_conf_path
            from PyQt6.QtCore import QByteArray
            from ats.ui.styles import CONFIG_FILE_LOCK
            config_path = get_conf_path("window_config.json", get_app_root())
            if not os.path.exists(config_path):
                return
            with CONFIG_FILE_LOCK:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # 1. Restore geometry
            geom_hex = data.get("ats_main_window_geometry")
            if geom_hex:
                self.restoreGeometry(QByteArray.fromHex(geom_hex.encode()))
                
            # 2. Restore splitters (优先使用二进制 state，降级使用像素 sizes 数组)
            self._is_restoring_sizes = True
            try:
                if hasattr(self, 'main_splitter'):
                    main_state = data.get("ats_main_splitter_state")
                    if main_state:
                        self.main_splitter.restoreState(QByteArray.fromHex(main_state.encode()))
                    else:
                        main_sizes = data.get("ats_main_splitter_sizes")
                        if main_sizes and isinstance(main_sizes, list) and len(main_sizes) == 3:
                            self.main_splitter.setSizes(main_sizes)
                        
                if hasattr(self, 'center_splitter'):
                    center_state = data.get("ats_center_splitter_state")
                    if center_state:
                        self.center_splitter.restoreState(QByteArray.fromHex(center_state.encode()))
                    else:
                        center_sizes = data.get("ats_center_splitter_sizes")
                        if center_sizes and isinstance(center_sizes, list) and len(center_sizes) == 2:
                            self.center_splitter.setSizes(center_sizes)
                        
                if hasattr(self, 'right_splitter'):
                    right_state = data.get("ats_right_splitter_state")
                    if right_state:
                        self.right_splitter.restoreState(QByteArray.fromHex(right_state.encode()))
                    else:
                        right_sizes = data.get("ats_right_splitter_sizes")
                        if right_sizes and isinstance(right_sizes, list) and len(right_sizes) == 2:
                            self.right_splitter.setSizes(right_sizes)
            finally:
                self._is_restoring_sizes = False
            
            # 3. Restore tabs active indexes
            if hasattr(self, 'top_tabs'):
                top_index = data.get("ats_top_tab_index")
                if top_index is not None and 0 <= int(top_index) < self.top_tabs.count():
                    self.top_tabs.setCurrentIndex(int(top_index))
            if hasattr(self, 'center_tabs'):
                center_index = data.get("ats_center_tabs_index")
                if center_index is not None and 0 <= int(center_index) < self.center_tabs.count():
                    self.center_tabs.setCurrentIndex(int(center_index))
            if hasattr(self, 'right_tabs'):
                right_index = data.get("ats_right_tabs_index")
                if right_index is not None and 0 <= int(right_index) < self.right_tabs.count():
                    self.right_tabs.setCurrentIndex(int(right_index))
                    
            # 4. Restore link checkboxes
            if hasattr(self, 'cb_tdx'):
                tdx_link = data.get("ats_link_tdx")
                if tdx_link is not None:
                    self.cb_tdx.setChecked(bool(tdx_link))
            if hasattr(self, 'cb_ths'):
                ths_link = data.get("ats_link_ths")
                if ths_link is not None:
                    self.cb_ths.setChecked(bool(ths_link))
            if hasattr(self, 'cb_vis'):
                vis_link = data.get("ats_link_vis")
                if vis_link is not None:
                    self.cb_vis.setChecked(bool(vis_link))
            if hasattr(self, 'cb_ladder'):
                ladder_link = data.get("ats_link_ladder")
                if ladder_link is not None:
                    self.cb_ladder.setChecked(bool(ladder_link))
                # 无论是否已有持久化，启动恢复时显式触发一次状态同步，确保守护线程100%可靠拉起
                self._on_ladder_link_toggled(self.cb_ladder.isChecked())
        except Exception as e:
            print(f"[ATSMainWindow] Error restoring layout state: {e}")

    def _save_layout_state(self):
        if getattr(self, '_is_restoring_sizes', False):
            return
        try:
            from ats.ui.styles import save_config_nodes
            updates = {}
            # Save geometry
            updates["ats_main_window_geometry"] = self.saveGeometry().toHex().data().decode()
            
            # Save splitters (同时以二进制 State 与 像素 Sizes 两种方式精准持久化)
            if hasattr(self, 'main_splitter'):
                updates["ats_main_splitter_state"] = self.main_splitter.saveState().toHex().data().decode()
                updates["ats_main_splitter_sizes"] = self.main_splitter.sizes()
            if hasattr(self, 'center_splitter'):
                updates["ats_center_splitter_state"] = self.center_splitter.saveState().toHex().data().decode()
                updates["ats_center_splitter_sizes"] = self.center_splitter.sizes()
            if hasattr(self, 'right_splitter'):
                updates["ats_right_splitter_state"] = self.right_splitter.saveState().toHex().data().decode()
                updates["ats_right_splitter_sizes"] = self.right_splitter.sizes()
                
            # Save tabs index
            if hasattr(self, 'top_tabs'):
                updates["ats_top_tab_index"] = self.top_tabs.currentIndex()
            if hasattr(self, 'center_tabs'):
                updates["ats_center_tabs_index"] = self.center_tabs.currentIndex()
            if hasattr(self, 'right_tabs'):
                updates["ats_right_tabs_index"] = self.right_tabs.currentIndex()

            # Save link checkboxes
            if hasattr(self, 'cb_tdx'):
                updates["ats_link_tdx"] = self.cb_tdx.isChecked()
            if hasattr(self, 'cb_ths'):
                updates["ats_link_ths"] = self.cb_ths.isChecked()
            if hasattr(self, 'cb_vis'):
                updates["ats_link_vis"] = self.cb_vis.isChecked()
            if hasattr(self, 'cb_ladder'):
                updates["ats_link_ladder"] = self.cb_ladder.isChecked()
            
            save_config_nodes(updates)
        except Exception as e:
            print(f"[ATSMainWindow] Error saving layout state: {e}")

    def _on_ladder_link_toggled(self, checked: bool):
        """开启/关闭连板天梯上下键联动与右键注入守护线程"""
        if checked:
            if self.ladder_watcher is None or not self.ladder_watcher.isRunning():
                try:
                    from ats.ladder_linkage_watcher import LadderLinkageWatcher
                    if self.ladder_watcher is None:
                        self.ladder_watcher = LadderLinkageWatcher(parent=self)
                        self.ladder_watcher.code_linked.connect(self._on_ladder_code_linked)
                        self.ladder_watcher.right_click_requested.connect(self._show_ladder_context_menu)
                    if not self.ladder_watcher.isRunning():
                        self.ladder_watcher.start()
                except Exception as e:
                    print(f"[ATSMainWindow] 启动 LadderLinkageWatcher 异常: {e}")
        else:
            if self.ladder_watcher is not None and self.ladder_watcher.isRunning():
                try:
                    self.ladder_watcher.stop()
                except Exception as e:
                    print(f"[ATSMainWindow] 停止 LadderLinkageWatcher 异常: {e}")
        if not getattr(self, '_is_restoring_sizes', False):
            self._save_layout_state()

    def _on_ladder_code_linked(self, code: str, row: int, source: str):
        """连板天梯跨进程联动触发通知 (状态栏提示)"""
        if hasattr(self, 'statusBar') and self.statusBar():
            self.statusBar().showMessage(f"🪜 连板天梯联动 -> 第 {row} 行 [{code}] ({source})", 3000)

    def _show_ladder_context_menu(self, code: str, name: str, x: int, y: int):
        """
        [RIGHT-CLICK INJECTION] 在连板天梯窗口鼠标右键点击处，弹出 ATS 核心右键菜单
        """
        code_clean = "".join(c for c in str(code) if c.isalnum()).zfill(6) if any(c.isdigit() for c in str(code)) else str(code).strip()
        if not code_clean:
            return

        stock_name = str(name).strip() if name and name != "未知" else self.get_stock_name(code_clean)
        
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtCore import QPoint
        from global_favorites import GlobalFavoriteManager

        fav_mgr = GlobalFavoriteManager()
        is_fav = code_clean in fav_mgr.get_favorite_stocks()

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #16161c;
                border: 1px solid #333344;
                color: #e2e2e5;
                padding: 5px;
                font-size: 9.5pt;
            }
            QMenu::item {
                padding: 6px 22px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #262c3d;
                color: #00ff88;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2e2e3a;
                margin: 4px 8px;
            }
        """)

        # 1. 标的标题项
        title_action = QAction(f"📌 标的: 【{stock_name}】 ({code_clean})", self)
        title_action.setEnabled(False)
        menu.addAction(title_action)

        menu.addSeparator()

        # 2. 复制功能
        copy_code_act = QAction(f"📋 复制代码 ({code_clean})", self)
        copy_code_act.triggered.connect(lambda: QApplication.clipboard().setText(code_clean))
        menu.addAction(copy_code_act)

        copy_all_act = QAction(f"📝 复制名称与代码 ({stock_name} {code_clean})", self)
        copy_all_act.triggered.connect(lambda: QApplication.clipboard().setText(f"{code_clean} {stock_name}"))
        menu.addAction(copy_all_act)

        menu.addSeparator()

        # 3. SBC 独立分时走势图
        sbc_act = QAction(f"📈 调出 SBC 独立分时走势图", self)
        def _open_sbc():
            from ats.ui.intraday_strategy_dialog import open_sbc_chart_dialog
            open_sbc_chart_dialog(self, code_clean)
        sbc_act.triggered.connect(_open_sbc)
        menu.addAction(sbc_act)

        # 4. 重点关注 (自选)
        if is_fav:
            fav_act = QAction(f"❌ 取消重点关注 (移出自选)", self)
        else:
            fav_act = QAction(f"⭐ 设为重点关注 (加入自选)", self)
        def _toggle_fav():
            fav_mgr.toggle_favorite_stock(code_clean)
            if hasattr(self, '_safe_favorites_changed'):
                self._safe_favorites_changed()
        fav_act.triggered.connect(_toggle_fav)
        menu.addAction(fav_act)

        menu.addSeparator()

        # 6. 涨停天梯聚合分析
        limit_act = QAction(f"🔥 打开每日涨停天梯看板", self)
        limit_act.triggered.connect(self.open_daily_limit_up_analyzer)
        menu.addAction(limit_act)

        # 7. 物理联动 (通达信 + 同花顺 + 东财)
        link_all_act = QAction(f"📡 立即联动终端 (TDX / THS / DC)", self)
        link_all_act.triggered.connect(lambda: self.link_stock(code_clean, stock_name))
        menu.addAction(link_all_act)

        # 8. 发送到异动联动
        from ats.ui.base_table import send_to_linkage
        linkage_act = QAction(f"⚡ 发送到异动联动", self)
        linkage_act.triggered.connect(lambda: send_to_linkage(code_clean, stock_name, self))
        menu.addAction(linkage_act)

        # 弹出菜单在鼠标屏幕位置 (使用 QCursor.pos() 自动精准适配 High-DPI 缩放与多显示器拓展桌面)
        menu.exec(QCursor.pos())

    def _on_top_tab_changed(self, index: int):
        """自动持久化记忆当前打开的是【重点关注】还是【大级别回调跟踪器】Tab 选项卡"""
        if not getattr(self, '_is_restoring_sizes', False):
            self._save_layout_state()

    def _on_channel_scan_button_clicked(self):
        """
        通道测算按钮点击响应：
        - 若按住 Alt 键：弹出周期选择菜单；
        - 默认直接点击：立即以当前选中的周期执行通道测算。
        """
        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.AltModifier:
            self._show_channel_scan_period_menu()
        else:
            self._execute_channel_scan(period=getattr(self, "channel_scan_period", "60f"))

    def _show_channel_scan_period_menu(self):
        """
        【Tab 顶部通道测算入口】弹出周期列表菜单供用户选择，支持 60f、120f、日线、周线、月线，
        选择后自动更新按钮文字、自动持久化所选周期，并立即触发对应周期的通道策略批量测算。
        """
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { 
                background-color: #0f172a; 
                color: #f8fafc; 
                border: 1px solid #334155; 
                padding: 4px; 
                font-size: 9pt; 
            }
            QMenu::item { 
                padding: 6px 20px 6px 24px; 
                border-radius: 3px; 
            }
            QMenu::item:selected { 
                background-color: #1e293b; 
                color: #38bdf8; 
            }
            QMenu::separator { 
                height: 1px; 
                background-color: #334155; 
                margin: 4px 8px; 
            }
        """)

        cur_period = getattr(self, "channel_scan_period", "60f")
        
        # 周期定义: (period_key, display_label)
        period_options = [
            ("60f", "🎯 60f (60分钟通道 - 默认首选)"),
            ("120f", "⏱️ 120f (120分钟/2小时通道)"),
            ("日线", "📅 日线 (日K通道)"),
            ("周线", "📆 周线 (周K大级别通道)"),
            ("月线", "🌕 月线 (月K超大级别通道)")
        ]

        for p_key, label in period_options:
            is_active = (p_key == cur_period)
            prefix = "✓ " if is_active else "   "
            act = menu.addAction(f"{prefix}{label}")
            act.triggered.connect(lambda checked=False, p=p_key: self._on_channel_period_selected(p))

        # 在按钮正下方弹出菜单
        if hasattr(self, "btn_top_scan_channel"):
            pos = self.btn_top_scan_channel.mapToGlobal(self.btn_top_scan_channel.rect().bottomLeft())
            menu.exec(pos)
        else:
            menu.exec(QCursor.pos())

    def _on_channel_period_selected(self, period: str):
        """当用户在菜单中选择测算周期时的处理"""
        self.channel_scan_period = period
        if hasattr(self, "btn_top_scan_channel"):
            self.btn_top_scan_channel.setText(f"🎯 {period}通道测算 ▾")
            self.btn_top_scan_channel.setToolTip(
                f"【直接点击】按当前周期 [{period}] 立即执行通道测算\n"
                f"【按住 Alt 点击 或 右键】弹出周期选择菜单 (60f / 120f / 日线 / 周线 / 月线)"
            )
        # 自动持久化最后使用的周期
        try:
            save_config_node(PERSIST_KEY_CHANNEL_SCAN_PERIOD, period)
        except Exception as e:
            logger.debug(f"持久化通道测算周期失败: {e}")
        # 立即执行测算
        self._execute_channel_scan(period=period)

    def _on_top_tab_scan_60f_clicked(self):
        """兼容原有 60f 测算槽函数入口 (默认直接执行)"""
        self._on_channel_scan_button_clicked()

    def _execute_channel_scan(self, period: Optional[str] = None):
        """
        【Tab 顶部公共入口】走势通道策略批量测算 (支持 60f/120f/日线/周线/月线 等多周期，支持重点关注、MA20d回调、新股次新股等多选与全量)
        """
        target_period = period or getattr(self, "channel_scan_period", "60f")
        cur_idx = self.top_tabs.currentIndex()
        cur_widget = self.top_tabs.currentWidget()
        tab_title = self.top_tabs.tabText(cur_idx)
        
        # 1. 提取当前 Tab 中用户选中的标的对 [(code, name), ...]
        stock_pairs = []
        if hasattr(cur_widget, "table") and hasattr(cur_widget.table, "get_selected_stock_pairs"):
            stock_pairs = cur_widget.table.get_selected_stock_pairs()
        elif hasattr(cur_widget, "get_selected_stock_pairs"):
            stock_pairs = cur_widget.get_selected_stock_pairs()
        elif hasattr(cur_widget, "table") and hasattr(cur_widget.table, "selectedIndexes"):
            # 兼容普通 QTableWidget 单选与多选提取
            t = cur_widget.table
            sel_rows = sorted(list(set(idx.row() for idx in t.selectedIndexes())))
            if sel_rows:
                for r in sel_rows:
                    if not t.isRowHidden(r):
                        it_c = t.item(r, 0)
                        it_n = t.item(r, 1)
                        c = it_c.text().strip() if it_c else ""
                        n = it_n.text().strip().replace("⭐ ", "").replace("🐉 ", "") if it_n else ""
                        if c:
                            stock_pairs.append((c, n))
            else:
                for r in range(t.rowCount()):
                    if not t.isRowHidden(r):
                        it_c = t.item(r, 0)
                        it_n = t.item(r, 1)
                        c = it_c.text().strip() if it_c else ""
                        n = it_n.text().strip().replace("⭐ ", "").replace("🐉 ", "") if it_n else ""
                        if c:
                            stock_pairs.append((c, n))
        elif hasattr(cur_widget, "df_data") and not cur_widget.df_data.empty:
            for _, r in cur_widget.df_data.iterrows():
                c_val = str(r.get("code", "")).zfill(6)
                n_val = str(r.get("name", ""))
                if c_val:
                    stock_pairs.append((c_val, n_val))

        if not stock_pairs:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", f"【{tab_title}】当前列表中无可用股票进行 {target_period} 通道策略测算！")
            return

        code_list = [c for c, _ in stock_pairs if c]
        code_to_name = {c: n for c, n in stock_pairs if c}
        
        # 周期映射为 TDX category
        cat_map = {
            "60f": "60m", "120f": "120m", "日线": "day", "周线": "week", "月线": "month"
        }
        category = cat_map.get(target_period, target_period)

        # 2. 状态栏提示
        self.statusBar().showMessage(f"📡 正在直连 TDX API 批量拉取 【{tab_title}】 {len(code_list)} 只标的 {target_period} K线进行通道策略扫描...", 8000)
        QApplication.processEvents()

        # 3. 极速纯 NumPy 批量高并发测算
        try:
            from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
            strategy = ChannelBottomReversalStrategy()
            df_matched = strategy.scan_stocks_tdx(code_list, category=category, count=120)
            
            # 回填名称
            if not df_matched.empty:
                df_matched["name"] = df_matched["code"].map(lambda c: code_to_name.get(c, self.get_stock_name(c)))

            self.statusBar().showMessage(f"🟢 【{tab_title}】 {target_period} 通道策略测算完成: 扫描 {len(code_list)} 只, 命中 {len(df_matched)} 只", 10000)

            # 4. 弹出专业统计结果独立窗口 (非阻塞、自由层级、多屏支持)
            from ats.ui.channel_scan_result_dialog import ChannelReversalScanResultDialog
            dialog_valid = False
            if hasattr(self, '_channel_scan_dialog') and self._channel_scan_dialog is not None:
                try:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(self._channel_scan_dialog):
                        dialog_valid = True
                except Exception:
                    dialog_valid = True

            if not dialog_valid:
                self._channel_scan_dialog = ChannelReversalScanResultDialog(
                    parent=self, 
                    df_results=df_matched, 
                    total_scanned=len(code_list), 
                    source_tab_name=tab_title,
                    period=target_period
                )
                self._channel_scan_dialog.stock_linkage_requested.connect(self.link_stock)
            else:
                self._channel_scan_dialog.update_results(
                    df_results=df_matched,
                    total_scanned=len(code_list),
                    source_tab_name=tab_title,
                    period=target_period
                )
            self._channel_scan_dialog.show()
            self._channel_scan_dialog.raise_()
            self._channel_scan_dialog.activateWindow()
        except Exception as e:
            logger.error(f"批量通道策略测算异常: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "测算异常", f"执行批量 {target_period} 通道策略测算时发生异常: {e}")

    def _on_tdx_signal_detected(self, sig_dict):
        """当后台 TdxSignalWatcher 捕获到通达信 / OrderMon 信号时的全逻辑联动处理"""
        if not sig_dict or not isinstance(sig_dict, dict):
            return

        code = sig_dict.get('code')
        if not code:
            return

        name = sig_dict.get('name', code)
        flag_label = sig_dict.get('flag_label', 'TDX信号')
        direction_cn = sig_dict.get('direction_cn', '买入')
        price = sig_dict.get('price', 0.0)
        time_str = sig_dict.get('time_str', '')

        # 1. 查找内存行情数据行并由 current_df 精确定位真实中文名称 (df 数据获取 name)
        df_row = None
        c_clean = str(code).zfill(6)
        if hasattr(self, 'current_df') and self.current_df is not None and not self.current_df.empty:
            if c_clean in self.current_df.index:
                df_row = self.current_df.loc[c_clean]

        name = sig_dict.get('name', '')
        if df_row is not None and 'name' in df_row and str(df_row['name']).strip() and str(df_row['name']).strip() != c_clean:
            name = str(df_row['name']).strip()
        elif not name or name == c_clean or str(name).isdigit():
            name = self.get_stock_name(c_clean)

        sig_dict['name'] = name

        # 2. 写入 SignalLedger 并自动提权置顶
        if hasattr(self, 'signal_ledger'):
            entry = self.signal_ledger.record_tdx_signal(sig_dict, row=df_row)

        # 3. 将新捕获的通达信信号直接注册到 _last_batch_signal_codes 顶部
        if not hasattr(self, "_last_batch_signal_codes") or self._last_batch_signal_codes is None:
            self._last_batch_signal_codes = []
        self._last_batch_signal_codes = [x for x in self._last_batch_signal_codes if (x[0] if isinstance(x, (tuple, list)) else x) != c_clean]
        self._last_batch_signal_codes.insert(0, (c_clean, name))

        # 4. 实时更新并刷新 UI
        if hasattr(self, 'refresh_realtime_ui'):
            self.refresh_realtime_ui()

        is_initial_load = sig_dict.get('is_initial_load', False)

        # 启动初始扫描历史信号时，仅静默载入账本用于列表展示，坚决不触发报警通知与切股联动
        if is_initial_load:
            return

        # 5. 状态栏与控制台提醒 (带 AlertNotifier 去重语音与 Toast 提示)
        period_cn = sig_dict.get('period_cn', '')
        period_str = f"[{period_cn}] " if period_cn else ""
        msg = f"🔔 [通达信信号] {code} {name} {period_str}[{flag_label}] ({direction_cn}) 触发价格:{price:.2f} 处理时间:[{time_str}]"
        if hasattr(self, 'statusBar') and self.statusBar():
            self.statusBar().showMessage(msg, 10000)

        try:
            print(f"[ATS] {msg}")
        except Exception:
            pass

        try:
            from ats.alert_notifier import AlertNotifier
            AlertNotifier().notify_special_signal(
                code=code,
                name=name,
                reason=f"通达信实盘信号: {flag_label} ({direction_cn})",
                score=95.0,
                parent=self
            )
        except Exception as e_notify:
            print(f"[ATS] TDX signal alert notification error: {e_notify}")

        # 6. 自动切股并联动外部通达信/同花顺终端
        if hasattr(self, 'link_stock'):
            self.link_stock(code, name)

    def closeEvent(self, event):
        """主窗口关闭退出时，自动跟随关闭所有独立的 TopLevel 子窗口、对话框、保存全量布局配置及安全回收后台线程"""
        self._is_closing = True
        self._is_exiting = True

        # 0. 🚀【原子持久化打开的磁吸/监控窗口状态】：在子窗口被 close() 前优先保存 is_open: True
        try:
            from PyQt6.sip import isdeleted
            # 1. 持久化加速龙头跟踪器状态
            if hasattr(self, 'dragon_monitor_dialog') and self.dragon_monitor_dialog and not isdeleted(self.dragon_monitor_dialog):
                if self.dragon_monitor_dialog.isVisible() or getattr(self.dragon_monitor_dialog, 'is_hidden_state', False):
                    self.dragon_monitor_dialog._save_window_states(is_open=True)

            # 1.1 持久化龙头突击跟单榜状态
            if hasattr(self, 'hot_sector_dialog') and self.hot_sector_dialog and not isdeleted(self.hot_sector_dialog):
                if self.hot_sector_dialog.isVisible() or getattr(self.hot_sector_dialog, 'is_hidden_state', False):
                    self.hot_sector_dialog._save_window_states(is_open=True)

            # 1.2 持久化每日涨停与强势股天梯看板状态
            if hasattr(self, 'daily_limit_up_dialog') and self.daily_limit_up_dialog and not isdeleted(self.daily_limit_up_dialog):
                if self.daily_limit_up_dialog.isVisible() or getattr(self.daily_limit_up_dialog, 'is_hidden_state', False):
                    self.daily_limit_up_dialog._save_window_states(is_open=True)
            
            # 2. 持久化所有打开的涨跌分布个股明细窗口状态
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_active_dialogs'):
                for d in self.dist_chart._active_dialogs:
                    if d and not isdeleted(d):
                        if d.isVisible() or getattr(d, 'is_hidden_state', False):
                            d._save_window_states(is_open=True)

            # 3. 持久化所有打开的 SBC 独立分时走势图窗口状态与位置
            try:
                from ats.ui.intraday_strategy_dialog import save_all_open_sbc_windows
                save_all_open_sbc_windows()
            except Exception as e_sbc:
                print(f"[ATSMainWindow] Error persisting SBC dialogs on close: {e_sbc}")
        except Exception as e_persist:
            print(f"[ATSMainWindow] Error persisting active monitor dialogs on close: {e_persist}")
        
        # 1. 彻底停止所有 UI 状态定时器与后台轮询
        timers_to_stop = [
            '_status_clock_timer', 'update_timer', '_favorites_poll_timer',
            '_history_load_timer', '_price_load_timer', '_auto_switch_timer',
            'pool_rotation_timer', 'rotation_timer'
        ]
        for t_name in timers_to_stop:
            if hasattr(self, t_name):
                t = getattr(self, t_name)
                if t:
                    try:
                        t.stop()
                    except Exception:
                        pass

        try:
            from ats.hot_sector_engine import HotSectorEngine
            HotSectorEngine.get_instance().stop_polling_worker()
        except Exception:
            pass

        try:
            from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
            TDXRealtimeFetcher.get_instance().disconnect()
        except Exception:
            pass

        try:
            from global_favorites import GlobalFavoriteManager
            GlobalFavoriteManager().shutdown()
        except Exception as ex:
            print(f"[ATSMainWindow] Error shutting down favorites: {ex}")
            
        if hasattr(self, 'bridge') and self.bridge is not None:
            try:
                self.bridge.stop_listener()
            except Exception as ex:
                print(f"[ATSMainWindow] Error stopping IPC listener: {ex}")

        if hasattr(self, 'tdx_watcher') and self.tdx_watcher is not None:
            try:
                self.tdx_watcher.stop()
                self.tdx_watcher.wait(1000)
            except Exception as ex:
                print(f"[ATSMainWindow] Error stopping TDX signal watcher: {ex}")

        if hasattr(self, 'ladder_watcher') and self.ladder_watcher is not None:
            try:
                self.ladder_watcher.stop()
                self.ladder_watcher.wait(1000)
            except Exception as ex:
                print(f"[ATSMainWindow] Error stopping LadderLinkageWatcher: {ex}")

        # 2. 🚀【广播主窗口退出信号】：通知所有悬浮独立窗口 (DNA、诊断、个股详情等) 接收退出事件并主动 close()
        try:
            from ats.ui.multi_period_dialog import ui_event_hub
            ui_event_hub.main_window_closing.emit()
            ui_event_hub.multi_period_closing.emit()
        except Exception as e:
            print(f"[ATSMainWindow] Error emitting closing signals: {e}")

        # 3. 遍历关闭所有活动的顶级 TopLevelWidgets（如个股分类详情弹窗、检查报告弹窗、DNA审计窗口等）
        try:
            from PyQt6.QtWidgets import QApplication
            for widget in list(QApplication.topLevelWidgets()):
                if widget != self:
                    from PyQt6.sip import isdeleted
                    if not isdeleted(widget):
                        try:
                            widget.close()
                        except Exception:
                            pass
        except Exception as e:
            print(f"[ATSMainWindow] Error closing topLevelWidgets: {e}")

        # 4. 同步持久化保存所有物理窗口布局、Splitter 尺寸及 TDX/THS/VIS 联动勾选状态
        try:
            self._save_layout_state()
            
            if hasattr(self, 'universe_widget') and hasattr(self.universe_widget, 'tree'):
                if hasattr(self.universe_widget.tree, 'save_header_state'):
                    self.universe_widget.tree.save_header_state()
            elif hasattr(self, 'universe_tree') and hasattr(self.universe_tree, 'tree'):
                if hasattr(self.universe_tree.tree, 'save_header_state'):
                    self.universe_tree.tree.save_header_state()
            
            if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'table'):
                if hasattr(self.swing_table.table, 'save_column_widths'):
                    self.swing_table.table.save_column_widths()
                    
            if hasattr(self, 'trade_flow_table') and hasattr(self.trade_flow_table, 'table'):
                if hasattr(self.trade_flow_table.table, 'save_column_widths'):
                    self.trade_flow_table.table.save_column_widths()
                    
            if hasattr(self, 'position_panel') and hasattr(self.position_panel, 'table'):
                if hasattr(self.position_panel.table, 'save_column_widths'):
                    self.position_panel.table.save_column_widths()
        except Exception as e:
            print(f"[ATSMainWindow] Error saving column widths on close: {e}")

        try:
            if hasattr(self, "save_window_position_qt_visual"):
                self.save_window_position_qt_visual(self, getattr(self, "window_name", "ats_main_window"))
        except Exception:
            pass

        # 4.5 程序优雅退出时触发唯一的终盘总结与最新快照原子保存 (彻底消除盘中刷屏生成冗余散落 JSON)
        if hasattr(self, 'session_snapshot') and hasattr(self, 'signal_ledger'):
            try:
                self.session_snapshot.save_snapshot(self.signal_ledger, force=True)
                self.session_snapshot.save_daily_summary(self.signal_ledger, force=True)
                self.session_snapshot.cleanup_old_snapshots()
                print("[ATSMainWindow] 程序退出关闭，已成功原子落盘保存终盘信号账本与总结快照!")
            except Exception as ex:
                print(f"[ATSMainWindow] 程序退出保存信号快照异常: {ex}")

        # 4.6 外盘 K 线内存脏数据统一原子落盘 (彻底确保退出时 K 线缓存不丢失)
        try:
            from JSONData.global_market_data import flush_kline_disk_cache
            flush_kline_disk_cache('yahoo', force=False)
            flush_kline_disk_cache('sina', force=False)
            print("[ATSMainWindow] 外盘 K 线脏数据已成功原子落盘持久化!")
        except Exception as ex:
            print(f"[ATSMainWindow] 外盘 K 线落盘异常 (非致命): {ex}")


        # 5. 关闭散落的行情分布弹窗、搜索历史与辅助对话框
        try:
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_close_all_dialogs'):
                self.dist_chart._close_all_dialogs()
        except Exception as e:
            print(f"[ATSMainWindow] Error closing dist chart dialogs: {e}")
            
        self._save_search_history_data()
        
        from PyQt6.sip import isdeleted
        if hasattr(self, 'dragon_monitor_dialog') and self.dragon_monitor_dialog and not isdeleted(self.dragon_monitor_dialog):
            try:
                self.dragon_monitor_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing dragon monitor on close: {e}")

        if hasattr(self, 'hot_sector_dialog') and self.hot_sector_dialog and not isdeleted(self.hot_sector_dialog):
            try:
                self.hot_sector_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing hot sector leaderboard on close: {e}")

        if hasattr(self, 'daily_limit_up_dialog') and self.daily_limit_up_dialog and not isdeleted(self.daily_limit_up_dialog):
            try:
                self.daily_limit_up_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing daily limit-up dialog on close: {e}")
                
        try:
            import ats.ui.multi_period_dialog as mpd
            if mpd._dialog_instance and not isdeleted(mpd._dialog_instance):
                mpd._dialog_instance.close()
            mpd._dialog_instance = None
        except Exception as e:
            print(f"[ATSMainWindow] Error closing multi period dialog on close: {e}")

        if hasattr(self, 'ladder_monitor_win') and self.ladder_monitor_win and not isdeleted(self.ladder_monitor_win):
            try:
                self.ladder_monitor_win.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing ladder monitor on close: {e}")

        # 关闭个股详情弹窗
        if hasattr(self, '_detail_dialog') and self._detail_dialog and not isdeleted(self._detail_dialog):
            try:
                self._detail_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing detail dialog on close: {e}")

        # 关闭板块详情弹窗
        if hasattr(self, '_sector_detail_dialog') and self._sector_detail_dialog and not isdeleted(self._sector_detail_dialog):
            try:
                self._sector_detail_dialog.close()
            except Exception as e:
                print(f"[ATSMainWindow] Error closing sector detail dialog on close: {e}")

        # 彻底关闭并销毁 AlertNotifier 的系统托盘图标 (消除任务栏绿色小圆点常驻)
        try:
            from ats.alert_notifier import AlertNotifier
            AlertNotifier.get_instance().shutdown()
        except Exception as e:
            print(f"[ATSMainWindow] Error shutting down AlertNotifier: {e}")

        # 安全持久化分时策略引擎状态（有实质数据变动才落盘）
        try:
            from ats.intraday_strategy_engine import IntradayStrategyEngine
            IntradayStrategyEngine.get_instance().save_intraday_cache(force=False)
        except Exception as e:
            print(f"[ATSMainWindow] Error saving intraday strategy cache on close: {e}")
            
        super().closeEvent(event)

        # 确保主窗口关闭后，通知 Qt 应用退出事件循环
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
        except Exception:
            pass

    def _on_favorites_changed(self):
        # Thread-safe trigger UI refresh on favorite changes using QTimer
        QTimer.singleShot(0, self._safe_favorites_changed)

    def _poll_favorites_loop(self):
        try:
            from global_favorites import GlobalFavoriteManager
            current_version = GlobalFavoriteManager().version
            if current_version != getattr(self, '_last_favorites_version', 0):
                self._last_favorites_version = current_version
                self._on_favorites_changed()
        except Exception:
            pass

    def _safe_favorites_changed(self):
        if getattr(self, '_is_closing', False):
            return
        try:
            from global_favorites import GlobalFavoriteManager
            import time
            import pandas as pd

            fav_mgr = GlobalFavoriteManager()
            fav_stocks = fav_mgr.get_favorite_stocks()
            fav_stocks_clean = {str(c).strip().zfill(6) for c in fav_stocks}

            # 🚀 [PERF OPTIMIZE] 沿用既有内存数据，原位刷新所有当前可见视图上的 ⭐ 重点标识
            # 1. 刷新重点关注 Tab 视图 (favorite_panel)
            if hasattr(self, 'favorite_panel') and hasattr(self.favorite_panel, 'update_favorite_rows'):
                existing_fav_rows = {}
                if hasattr(self, '_pending_swing_rows') and self._pending_swing_rows:
                    for r in self._pending_swing_rows:
                        code_clean = str(r[0]).strip().zfill(6)
                        if code_clean in fav_stocks_clean:
                            existing_fav_rows[code_clean] = r

                fav_rows = []
                has_df = hasattr(self, 'current_df') and isinstance(self.current_df, pd.DataFrame) and not self.current_df.empty

                for code_clean in fav_stocks_clean:
                    if code_clean in existing_fav_rows:
                        fav_rows.append(existing_fav_rows[code_clean])
                    else:
                        name = "未知"
                        price_str = "0.00"
                        if has_df and code_clean in self.current_df.index:
                            row_df = self.current_df.loc[code_clean]
                            if isinstance(row_df, pd.DataFrame):
                                row_df = row_df.iloc[0]
                            name = str(row_df.get('name', '未知'))
                            price_val = row_df.get('trade', row_df.get('price', 0.0))
                            try:
                                price_str = f"{float(price_val):.2f}"
                            except Exception:
                                price_str = str(price_val)
                        else:
                            from sys_utils import resolve_stock_name
                            name = resolve_stock_name(code_clean) or "未知"
                        from ats.ui.favorite_panel import get_ats_extra_cols
                        extra_cols = get_ats_extra_cols()
                        extra_fallback = []
                        for ec in extra_cols:
                            ec_val = '--'
                            if has_df and code_clean in self.current_df.index:
                                try:
                                    row_df = self.current_df.loc[code_clean]
                                    if isinstance(row_df, pd.DataFrame):
                                        row_df = row_df.iloc[0]
                                    for k in (ec, ec.lower(), ec.upper()):
                                        if k in row_df:
                                            try:
                                                from JohnsonUtil import commonTips as cct
                                                ec_val = cct.format_col_value(ec, row_df[k])
                                            except Exception:
                                                ec_val = str(row_df[k])
                                            break
                                except Exception:
                                    pass
                            extra_fallback.append(ec_val)

                        fav_date = fav_mgr.get_favorite_stock_date(code_clean) or time.strftime("%Y-%m-%d")
                        fallback_row = (
                            code_clean, name, price_str, "重点关注", "+0.0%", "0", "观察",
                            fav_date, "200.0", "0.0", "0", "0.0", "0.0", "0.0", "普通",
                            *extra_fallback,
                            "基础重点关注标的"
                        )
                        fav_rows.append(fallback_row)

                self._pending_fav_rows = fav_rows
                self.favorite_panel.update_favorite_rows(fav_rows)

            # 2. 原位刷新 SwingStateTable (📉 大级别 MA20d 回调跟踪器) 上的 ⭐ 标识与背景高亮
            if hasattr(self, 'swing_table') and hasattr(self.swing_table, 'refresh_favorites_display'):
                self.swing_table.refresh_favorites_display()

            # 3. 原位刷新 NewStockPanel (🆕 新股次新股 (IPO & 阶梯)) 上的 ⭐ 标识与置顶排序
            if hasattr(self, 'new_stock_panel') and hasattr(self.new_stock_panel, 'refresh_favorites_display'):
                self.new_stock_panel.refresh_favorites_display()

            # 4. 同步更新左侧策略股票池 (UniverseManager & UniverseTreeWidget)
            if hasattr(self, 'universe_manager') and hasattr(self, 'universe_widget'):
                if getattr(self.universe_widget, '_is_mock_active', False):
                    self.universe_widget.load_mock_data()
                else:
                    try:
                        self.universe_manager.sync_from_ledger()
                        radar_list, watch_list, trade_list = self.universe_manager.get_pools()
                        self.universe_widget.update_pools(radar_list, watch_list, trade_list)
                    except Exception as e_um:
                        if hasattr(self.universe_widget, 'refresh_favorites_display'):
                            self.universe_widget.refresh_favorites_display()
                
            # 5. 刷新右侧板块热力图
            if hasattr(self, 'heatmap_widget'):
                self.heatmap_widget.load_live_sectors(current_df=self.current_df)
                
            # 6. 刷新打开的个股分布明细等独立弹窗
            if hasattr(self, 'dist_chart') and hasattr(self.dist_chart, '_active_dialogs'):
                from PyQt6.sip import isdeleted
                for d in self.dist_chart._active_dialogs:
                    try:
                        if not isdeleted(d) and d.isVisible() and hasattr(d, 'refresh_favorites_display'):
                            d.refresh_favorites_display()
                    except Exception:
                        pass
        except Exception as e:
            print(f"[ATSMainWindow] Error refreshing UI on favorites changed: {e}")


    def open_dragon_monitor(self, restore_state=None, cold_start=False):
        if getattr(self, '_is_closing', False) or getattr(self, '_is_exiting', False):
            return
        from PyQt6.sip import isdeleted
        if self.dragon_monitor_dialog is None or isdeleted(self.dragon_monitor_dialog):
            self.dragon_monitor_dialog = DragonLeaderMonitorDialog(self, restore_state=restore_state)
            self.dragon_monitor_dialog.code_clicked.connect(self.link_stock)
        
        # 如果是 cold_start 启动恢复且原处于贴边折叠隐藏状态，则保持贴边细条展示；
        # 若是用户主动点击唤起（cold_start=False），无论当前是否折叠隐藏，均强制展开显示（show_normal_position）！
        if cold_start and getattr(self.dragon_monitor_dialog, 'is_hidden_state', False):
            self.dragon_monitor_dialog.show()
        else:
            self.dragon_monitor_dialog.show_normal_position()
            
        if hasattr(self.dragon_monitor_dialog, '_save_window_states'):
            self.dragon_monitor_dialog._save_window_states(is_open=True)
        
        has_df = self.current_df is not None and not self.current_df.empty
        sh_pct = 0.0
        if has_df:
            if 'sh000001' in self.current_df.index:
                sh_pct = float(self.current_df.loc['sh000001'].get('percent', 0.0))
            elif '000001' in self.current_df.index and 'sh' in str(self.current_df.loc['000001'].get('code', '')):
                sh_pct = float(self.current_df.loc['000001'].get('percent', 0.0))
            else:
                if 'percent' in self.current_df.columns:
                    sh_pct = float(self.current_df['percent'].mean())
            try:
                self.dragon_monitor_dialog.update_data(self.current_df, sh_pct)
            except Exception as e:
                print(f"[ATSMainWindow] Error updating dragon monitor on open: {e}")

    def open_daily_limit_up_analyzer(self, restore_state=None, cold_start=False):
        """打开/激活【🔥 每日涨停分析与强势股天梯】独立看板 (非模态独立运行，完全不阻塞主界面)"""
        if getattr(self, '_is_closing', False) or getattr(self, '_is_exiting', False):
            return
        from PyQt6.sip import isdeleted
        if not hasattr(self, 'daily_limit_up_dialog') or self.daily_limit_up_dialog is None or isdeleted(self.daily_limit_up_dialog):
            self.daily_limit_up_dialog = DailyLimitUpDialog(parent=None, restore_state=restore_state)
            self.daily_limit_up_dialog._py_parent = self
            self.daily_limit_up_dialog.code_clicked.connect(self.link_stock)
            self.daily_limit_up_dialog.code_double_clicked.connect(self.on_stock_clicked)

        if cold_start and getattr(self.daily_limit_up_dialog, 'is_hidden_state', False):
            self.daily_limit_up_dialog.show()
        else:
            self.daily_limit_up_dialog.show_normal_position()

        if hasattr(self.daily_limit_up_dialog, '_save_window_states'):
            self.daily_limit_up_dialog._save_window_states(is_open=True)

        # 立即注入当前最新的 DataFrame 和大盘涨幅
        sh_pct = 0.0
        if self.current_df is not None and not self.current_df.empty:
            if 'sh000001' in self.current_df.index:
                sh_pct = float(self.current_df.loc['sh000001'].get('percent', 0.0))
            elif '000001' in self.current_df.index and 'sh' in str(self.current_df.loc['000001'].get('code', '')):
                sh_pct = float(self.current_df.loc['000001'].get('percent', 0.0))
            elif 'percent' in self.current_df.columns:
                sh_pct = float(self.current_df['percent'].mean())
        if hasattr(self.daily_limit_up_dialog, 'update_data_payload'):
            self.daily_limit_up_dialog.update_data_payload(self.current_df, sh_pct)

    def open_hot_sector_leaderboard(self, restore_state=None, cold_start=False):
        """调起 Top 3 强势板块龙头突击跟单榜独立窗口（非模态独立运行，完全不阻塞主界面）"""
        if getattr(self, '_is_closing', False) or getattr(self, '_is_exiting', False):
            return
        from PyQt6.sip import isdeleted
        if not hasattr(self, 'hot_sector_dialog') or self.hot_sector_dialog is None or isdeleted(self.hot_sector_dialog):
            self.hot_sector_dialog = HotSectorLeaderboardDialog(self, restore_state=restore_state)
            self.hot_sector_dialog.code_clicked.connect(self.link_stock)

        if cold_start and getattr(self.hot_sector_dialog, 'is_hidden_state', False):
            self.hot_sector_dialog.show()
        else:
            self.hot_sector_dialog.show_normal_position()

        if hasattr(self.hot_sector_dialog, '_save_window_states'):
            self.hot_sector_dialog._save_window_states(is_open=True)

        if hasattr(self.hot_sector_dialog, '_force_refresh_data'):
            self.hot_sector_dialog._force_refresh_data()

    def open_global_market_dialog(self):
        """打开/激活【🌐 全球外盘与热点情绪看板】独立自适应窗口 (不影响主界面原有布局)"""
        from ats.ui.global_market_dialog import open_global_market_dialog
        open_global_market_dialog(parent_window=self)

    def open_multi_period_tester(self):
        """[NEW] 打开/切换多周期联动策略筛选器 (优先检测内部调用，其次检测外部 MultiPeriodTester.exe/脚本)"""
        if getattr(self, '_is_closing', False):
            return

        import time
        now = time.time()
        last_t = getattr(self, "_last_multi_period_trigger_t", 0.0)
        if now - last_t < 0.3:
            return
        self._last_multi_period_trigger_t = now

        # 1. 优先检测并切换内部 PyQt6 Dialog 的打开/显示/隐藏状态
        from PyQt6.sip import isdeleted
        import ats.ui.multi_period_dialog as mpd
        
        dialog = mpd._dialog_instance
        if dialog is not None and not isdeleted(dialog):
            try:
                if dialog.isVisible() and not dialog.isMinimized():
                    dialog.hide()
                    print("[MultiPeriod] Internal dialog is visible, hiding it.")
                else:
                    if dialog.isMinimized():
                        dialog.showNormal()
                    else:
                        dialog.show()
                    dialog.raise_()
                    dialog.activateWindow()
                    print("[MultiPeriod] Internal dialog shown and activated.")
                return
            except Exception as e:
                print(f"[MultiPeriod] Toggle internal dialog error: {e}")
                mpd._dialog_instance = None

        # 2. 如果内部窗口不存在，检测并切换外部独立进程窗口
        titles = ["多周期联动策略筛选器", "⏱️ 多周期交叉筛选与诊断系统"]
        hwnd = None
        try:
            import ctypes
            import os
            for t in titles:
                found_hwnd = ctypes.windll.user32.FindWindowW(None, t)
                if found_hwnd:
                    # 排除本进程的窗口，防止标题一致时误判内部窗口为外部窗口
                    pid = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(found_hwnd, ctypes.byref(pid))
                    if pid.value != os.getpid():
                        hwnd = found_hwnd
                        break
            
            if hwnd:
                is_visible = ctypes.windll.user32.IsWindowVisible(hwnd)
                is_iconic = ctypes.windll.user32.IsIconic(hwnd)
                
                if is_visible and not is_iconic:
                    # 如果外部窗口当前可见且未最小化，再次点击则隐藏它
                    ctypes.windll.user32.ShowWindow(hwnd, 0) # SW_HIDE = 0
                    print("[MultiPeriod] External window is visible, hiding it.")
                else:
                    # 如果外部窗口不可见，或者在后台，则将其唤醒、恢复并置顶聚焦
                    if is_iconic:
                        ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE = 9
                    else:
                        ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW = 5
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    print("[MultiPeriod] External window is background/hidden, restoring and bringing to foreground.")
                return
        except Exception as e:
            print(f"[MultiPeriod] FindWindowW error: {e}")

        # 3. 否则，全新打开内部多周期窗口
        try:
            print("🚀 [MultiPeriod] Opening internal PyQt6 MultiPeriodDialog...")
            mpd.open_multi_period_tester(parent_window=self)
        except Exception as e:
            print(f"[MultiPeriod] Failed to open internal MultiPeriodDialog: {e}")


