# -*- coding: utf-8 -*-
"""
ats/ui/intraday_strategy_dialog.py — ATS 分时阶梯交易策略 & 频准激光 8/18 上市动态时序评估一体化系统
特点：
1. 深度整合原有的分时阶梯交易策略（开盘定盘、时间轴阶段、规则达成、价格笼子挂单、买卖点信号路由与流水、SBC 实盘走势）与 7 节点时序动态打分评估体系；
2. Tab 1 为一体化实盘交易与动态评估工作台，数据由实时 df / TDX 秒级直连 / 手动估价自动摄入解析并动态驱动；
3. 支持【✍️ 估价推演 / 手动输入价格自动评分】模式，在行情未开盘、数据获取异常或需要推演时，用户输入开盘估价/现价/换手率即可全自动重新评估 7 节点打分与操作策略；
4. 彻底解决滚动条自动跳回顶部问题（采用滚动条位置保护与脏检查复用机制）；
5. Tab 2 为 8/18 开盘时间对齐全天分时模拟回测演练器（四大情景 A/B/C/D型）；
6. Tab 3 为频准激光 8/18 专属盯盘模板、综合加权汇总表与 7 条实盘法则；
7. 基于 QMainWindow 独立窗口运行，支持窗口置顶 (StayOnTop) 与 TDX 1 秒极速直连。
"""

import sys
import os
import json
import shutil
import time
import math
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 兼容开发模式单独运行子脚本（防重复挂载，打包运行下 if 为 False 不会污染 sys.path）
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CUR_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from sys_utils import setup_qt_clean_environment
    setup_qt_clean_environment()
except Exception:
    pass

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QGroupBox,
    QTextEdit, QPlainTextEdit, QLineEdit, QComboBox, QMessageBox, QFrame, QGridLayout, QProgressBar,
    QScrollArea, QTabWidget, QDoubleSpinBox, QRadioButton, QButtonGroup,
    QCheckBox, QSlider, QToolBar, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSettings, QParallelAnimationGroup, QPropertyAnimation, QEasingCurve, QRect, QEvent, QPoint, QPointF
from PyQt6.QtGui import QColor, QFont, QBrush, QIcon, QPainter, QPen, QPainterPath, QCursor, QPolygon, QPolygonF

from sys_utils import resolve_stock_name
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.ui.styles import apply_dark_theme, DARK_THEME_QSS, bind_top_shortcut, set_seamless_stay_on_top
from signal_types import SignalPoint, SignalType, SignalSource

logger = logging.getLogger("IntradayStrategyDialog")


def _format_cell_text(val) -> str:
    """安全格式化单元格文本"""
    if val is None:
        return ""
    if isinstance(val, (list, tuple, set)):
        return "；".join(str(x) for x in val)
    return str(val)


def save_ui_layout_state(key: str, val: Any):
    """【💾 布局落盘】保存 UI 布局、窗口大小、QSplitter 与表格列宽到 config/intraday_ui_layout.json"""
    try:
        conf_dir = os.path.join(get_app_root(), "config")
        os.makedirs(conf_dir, exist_ok=True)
        conf_file = os.path.join(conf_dir, "intraday_ui_layout.json")
        data = {}
        if os.path.exists(conf_file):
            with open(conf_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        data[key] = val
        with open(conf_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug(f"保存 UI 布局落盘文件异常: {e}")

def load_ui_layout_state(key: str, default: Any = None) -> Any:
    """【💾 布局恢复】从 config/intraday_ui_layout.json 恢复 UI 布局状态"""
    try:
        conf_file = os.path.join(get_app_root(), "config", "intraday_ui_layout.json")
        if os.path.exists(conf_file):
            with open(conf_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get(key, default)
    except Exception as e:
        logger.debug(f"读取 UI 布局落盘文件异常: {e}")
    return default

def bind_table_column_persistence(table: QTableWidget, key_name: str):
    """【📏 列宽落盘绑定】自动恢复并监听 QTableWidget 各列宽度改变，实现 100% 物理持久化"""
    saved_widths = load_ui_layout_state(key_name)
    if saved_widths and isinstance(saved_widths, list):
        for c, w in enumerate(saved_widths):
            if c < table.columnCount() and int(w) > 15:
                table.setColumnWidth(c, int(w))

    def _on_section_resized(logical_index, old_size, new_size):
        widths = [table.columnWidth(c) for c in range(table.columnCount())]
        save_ui_layout_state(key_name, widths)

    table.horizontalHeader().sectionResized.connect(_on_section_resized)

class DetailTextDialog(QDialog):
    """【🔍 详情悬浮弹窗】双击表格单元格查看完整应对备注、信号明细与指导建议"""
    def __init__(self, parent=None, title: str = "详细信息", content_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"🔍 【{title}】详细信息与实操应对")
        self.resize(640, 420)
        self.setStyleSheet("background-color: #12121c; color: #ffffff;")
        layout = QVBoxLayout(self)

        lbl = QLabel(f"📋 【{title}】")
        lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #00ff88;")
        layout.addWidget(lbl)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content_text)
        txt.setStyleSheet("background-color: #08080d; color: #38bdf8; font-family: Consolas, Microsoft YaHei; font-size: 10pt; line-height: 1.6; padding: 10px; border: 1px solid #303042; border-radius: 4px;")
        layout.addWidget(txt, 1)

        btn_box = QHBoxLayout()
        btn_copy = QPushButton("📋 复制文本内容")
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet("background-color: #1e2638; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 6px 16px;")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(content_text))

        btn_close = QPushButton("关闭")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("background-color: #222230; color: #aaaaaa; border: 1px solid #444455; border-radius: 4px; padding: 6px 16px;")
        btn_close.clicked.connect(self.accept)

        btn_box.addWidget(btn_copy)
        btn_box.addStretch()
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

def handle_table_cell_double_click(table: QTableWidget, row: int, col: int, parent=None):
    """通用单元格双击悬浮窗处理函数"""
    item = table.item(row, col)
    if not item:
        return
    cell_text = item.text()
    tooltip_text = item.toolTip()
    full_text = tooltip_text if (tooltip_text and len(tooltip_text) > len(cell_text)) else cell_text
    if not full_text or full_text == "--":
        return

    header_item = table.horizontalHeaderItem(col)
    col_title = header_item.text().replace("\n", " ") if header_item else f"第 {col+1} 列"

    node_item = table.item(row, 1) or table.item(row, 0)
    node_name = node_item.text() if node_item else f"行 {row+1}"

    dlg = DetailTextDialog(parent=parent, title=f"{node_name} - {col_title}", content_text=full_text)
    dlg.exec()

def _format_tooltip_text(val) -> Optional[str]:
    """安全格式化 Tooltip 文本"""
    if val is None:
        return None
    if isinstance(val, (list, tuple, set)):
        return "\n".join(str(x) for x in val)
    return str(val)


class NumericTableWidgetItem(QTableWidgetItem):
    """支持精确数值比较与自定义排序权重的 QTableWidgetItem"""
    def __init__(self, text: str = "", sort_val: Optional[float] = None):
        super().__init__(str(text))
        self.sort_val = float(sort_val) if sort_val is not None else None

    def __lt__(self, other):
        if self.sort_val is not None and isinstance(other, NumericTableWidgetItem) and other.sort_val is not None:
            return self.sort_val < other.sort_val
        if self.sort_val is not None and other is not None:
            try:
                raw = str(other.text()).replace("%", "").replace("元", "").replace("分", "").replace("万", "").replace("亿", "").replace("+", "").strip()
                return self.sort_val < float(raw)
            except Exception:
                pass
        return super().__lt__(other)


def _safe_set_cell_item(
    table: QTableWidget,
    row: int,
    col: int,
    text: Any,
    fg_color=None,
    bg_color=None,
    align=None,
    font=None,
    tooltip=None,
    sort_val: Optional[float] = None
) -> QTableWidgetItem:
    """
    安全设置或更新 QTableWidget 单元格 Item。
    若 Item 已经存在，则只调用 setText / setForeground 等属性更新，
    绝不重复调用 setItem()，彻底避免 'cannot insert an item that is already owned' 警告。
    支持自动格式化 list / tuple 类型的 text 与 tooltip，并支持精确数值排序 sort_val。
    """
    str_text = _format_cell_text(text)
    str_tooltip = _format_tooltip_text(tooltip)

    item = table.item(row, col)
    need_create = item is None or (sort_val is not None and not isinstance(item, NumericTableWidgetItem))
    
    if need_create:
        if sort_val is not None:
            item = NumericTableWidgetItem(str_text, sort_val)
        else:
            item = QTableWidgetItem(str_text)
        if fg_color is not None:
            item.setForeground(fg_color if isinstance(fg_color, (QColor, QBrush)) else QColor(fg_color))
        if bg_color is not None:
            item.setBackground(bg_color if isinstance(bg_color, (QColor, QBrush)) else QColor(bg_color))
        if align is not None:
            item.setTextAlignment(align)
        if font is not None:
            item.setFont(font)
        if str_tooltip is not None:
            item.setToolTip(str_tooltip)
        table.setItem(row, col, item)
    else:
        item.setText(str_text)
        if sort_val is not None and isinstance(item, NumericTableWidgetItem):
            item.sort_val = float(sort_val)
        if fg_color is not None:
            item.setForeground(fg_color if isinstance(fg_color, (QColor, QBrush)) else QColor(fg_color))
        if bg_color is not None:
            item.setBackground(bg_color if isinstance(bg_color, (QColor, QBrush)) else QColor(bg_color))
        if align is not None:
            item.setTextAlignment(align)
        if font is not None:
            item.setFont(font)
        if str_tooltip is not None:
            item.setToolTip(str_tooltip)
    return item


# 别名兼容
_set_or_update_table_item = _safe_set_cell_item


class SBCChartCanvas(QWidget):
    """
    SBC 多功能走势图画布控件 (支持 1日/2日/3日分时走势图 以及 5分/30分/60分/日K 线的 GG 通道图)
    - 🔍 支持鼠标滚轮以光标为中心自由缩放；
    - 🖐️ 支持按住鼠标左键左右拖拽平移历史 K 线/分时；
    - 🔄 支持鼠标右键一键重置回 100% 全景视图；
    - 🎯 通达信自动通道严格截止于最高价/最低价波段起点，杜绝左上角冗长斜线。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.df_intraday = pd.DataFrame()
        self.period_mode = "1m" # 1m | 2d | 3d | 5m | 30m | 60m | day | week
        self.open_price = 0.0
        self.vwap = 0.0
        self.high_price = 0.0
        self.low_price = 0.0
        self.target_sell_min = 0.0
        self.target_sell_max = 0.0
        self.signals = []

        # 🔍 缩放与平移视口状态
        self._zoom_start_idx = 0
        self._zoom_end_idx = -1  # -1 表示显示到最新一根
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_indices = (0, -1)
        self._last_period_mode = "1m"

        # 🔍 框选放大 (Rubberband Box Zoom) 状态
        self._box_zoom_origin = None
        self._box_zoom_current = None
        self._is_box_zooming = False

        # 🖐️ 鼠标右键平移/单击重置状态
        self._right_press_pos = None
        self._is_right_panning = False
        self._right_pan_start_indices = (0, -1)

        # 🎯 鼠标指针悬停与实时价格坐标
        self._hover_pos = None
        self._coord_info = {}

        # ⚡ 快捷键 R 自适应周期策略测算结果与标的代码
        self.code = ""
        self.strategy_eval_result = None
        self.auto_eval_enabled: bool = True

        # 🎯 点击收益与交易对高亮状态
        self.selected_trade_id: Optional[int] = None
        self._signal_hit_boxes: List[Dict[str, Any]] = []

        self.setMinimumSize(320, 180)
        self.setStyleSheet("background-color: #0c0d14;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def reset_view(self):
        """🔄 重置视口至 100% 全景显示"""
        self._zoom_start_idx = 0
        self._zoom_end_idx = -1
        self._is_panning = False
        self._is_box_zooming = False
        self._box_zoom_origin = None
        self._box_zoom_current = None
        self.selected_trade_id = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def _is_zoomed(self) -> bool:
        """检查当前是否处于局部放大状态"""
        if self.df_intraday is None or self.df_intraday.empty:
            return False
        total_n = len(self.df_intraday)
        cur_start = max(0, self._zoom_start_idx)
        cur_end = min(total_n - 1, self._zoom_end_idx if self._zoom_end_idx >= 0 else total_n - 1)
        return (cur_start > 0 or cur_end < total_n - 1) and (cur_end - cur_start + 1 < total_n)

    def _get_visible_slice(self):
        """获取当前可视切片 DataFrame 以及切片起止索引"""
        if self.df_intraday is None or self.df_intraday.empty:
            return pd.DataFrame(), 0, 0
        total_n = len(self.df_intraday)
        start_i = max(0, self._zoom_start_idx)
        end_i = min(total_n - 1, self._zoom_end_idx if self._zoom_end_idx >= 0 else total_n - 1)
        if start_i > end_i:
            start_i = 0
            end_i = total_n - 1
        return self.df_intraday.iloc[start_i:end_i + 1], start_i, end_i

    def keyPressEvent(self, event):
        """
        ⚡ 键盘快捷键响应：
        - 按下 R / r 键：自适应当前视图周期运行策略测算并在图上标记买卖介入点
        - 按下 F / f 键：触发全系统与通达信外部行情联动
        - 按下 Left / Up / PageUp / Backtab：向前环形轮转切换周期
        - 按下 Right / Down / PageDown / Tab：向后环形轮转切换周期
        - 按下 1~9 键：直接精准切换对应周期 (1:1日分时 2:2日 3:3日 4:5分 5:30分 6:60分 7:日K 8:周K 9:月K)
        - 按下 0 键：重置缩放回 100% 全景
        - 按下 Esc 键：关闭 SBC 窗口
        """
        key = event.key()
        parent_win = self.window()
        if key == Qt.Key.Key_R:
            self.run_adaptive_strategy_eval()
            event.accept()
            return
        elif key == Qt.Key.Key_T and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                if parent_win and hasattr(parent_win, '_toggle_stay_on_top'):
                    parent_win._toggle_stay_on_top()
                    event.accept()
                    return
                elif parent_win and hasattr(parent_win, 'chk_on_top'):
                    parent_win.chk_on_top.toggle()
                    event.accept()
                    return
        elif key == Qt.Key.Key_F:
            if parent_win and hasattr(parent_win, '_trigger_linkage'):
                parent_win._trigger_linkage()
            event.accept()
            return
        elif key == Qt.Key.Key_Q:
            if parent_win and hasattr(parent_win, '_on_rearrange_windows_clicked'):
                parent_win._on_rearrange_windows_clicked()
            event.accept()
            return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backtab):
            if parent_win and hasattr(parent_win, 'rotate_period'):
                parent_win.rotate_period(-1)
            event.accept()
            return
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Tab):
            if parent_win and hasattr(parent_win, 'rotate_period'):
                parent_win.rotate_period(1)
            event.accept()
            return
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            idx = key - Qt.Key.Key_1
            if parent_win and hasattr(parent_win, 'switch_period_by_index'):
                parent_win.switch_period_by_index(idx)
            event.accept()
            return
        elif key in (Qt.Key.Key_BracketRight, Qt.Key.Key_Space):
            self.cycle_selected_trade(1)
            event.accept()
            return
        elif key == Qt.Key.Key_BracketLeft:
            self.cycle_selected_trade(-1)
            event.accept()
            return
        elif key == Qt.Key.Key_0:
            self.reset_view()
            event.accept()
            return
        elif key == Qt.Key.Key_Escape:
            if parent_win:
                parent_win.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def cycle_selected_trade(self, step: int = 1):
        """【💰 轮巡切换回测交易对】按快捷键 (Space 或 [ / ]) 或点击按钮切换高亮交易并展示点击收益"""
        if not self.signals:
            return
        tids = sorted(list({int(s.get("trade_id")) for s in self.signals if s.get("trade_id") is not None}))
        if not tids:
            return
        if self.selected_trade_id is None or self.selected_trade_id not in tids:
            self.selected_trade_id = tids[0] if step >= 0 else tids[-1]
        else:
            cur_idx = tids.index(self.selected_trade_id)
            next_idx = (cur_idx + step) % len(tids)
            self.selected_trade_id = tids[next_idx]
        self.update()

    def run_adaptive_strategy_eval(self):
        """
        【自适应周期策略测算引擎 (快捷键 R 核心处理入口)】
        自动识别当前画布的周期模式 (1m/2d/3d/5m/30m/60m/day/week/month) 并执行对应策略测算与图上标记
        """
        c_clean = "".join(filter(str.isdigit, str(self.code))).zfill(6) if self.code else "688826"
        p_mode = str(self.period_mode).lower()

        # 1. 确保数据充足：若数据为空或过短，尝试从 TDX API 直连拉取
        if self.df_intraday is None or len(self.df_intraday) < 15:
            try:
                from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
                fetcher = TDXRealtimeFetcher.get_instance()
                cat_req = p_mode if p_mode in ("5m", "15m", "30m", "60m", "day", "week", "month") else "60m"
                df_k = fetcher.fetch_kline_bars(c_clean, category=cat_req, count=150)
                if not df_k.empty and len(df_k) >= 15:
                    self.df_intraday = df_k
            except Exception as e_tdx:
                logger.debug(f"[SBC自适应测算] TDX拉取异常: {e_tdx}")

        if self.df_intraday is None or len(self.df_intraday) < 8:
            self.strategy_eval_result = {
                "is_matched": False,
                "period": p_mode,
                "reason": f"当前周期 ({p_mode}) K线数据不足 8 根，无法测算"
            }
            self.update()
            return

        # 2. K 线多周期形态测算 (5m / 15m / 30m / 60m / day / week / month)
        if p_mode in ("5m", "15m", "30m", "60m", "day", "week", "month"):
            try:
                from ats.channel_bottom_reversal_strategy import ChannelBottomReversalStrategy
                strategy = ChannelBottomReversalStrategy()
                res = strategy.evaluate(self.df_intraday)
                res["period"] = p_mode
                res["code"] = c_clean
                self.strategy_eval_result = res
                self.update()

                # 💡 [日志防重与状态机去重] 没有变化的数据日志绝不重复刷屏输出
                cur_sig = (
                    c_clean,
                    p_mode,
                    bool(res.get('is_matched', False)),
                    round(float(res.get('score', 0.0) or 0.0), 1),
                    round(float(res.get('entry_price', 0.0) or 0.0), 2),
                    str(res.get('reason', ''))
                )
                last_sig = getattr(self, '_last_eval_log_signature', None)
                if last_sig != cur_sig:
                    self._last_eval_log_signature = cur_sig
                    logger.info(f"🎯 [SBC快捷键R测算·{p_mode}] {c_clean} 结果: matched={res.get('is_matched')} | score={res.get('score')} | entry={res.get('entry_price')} | reason={res.get('reason')}")
                else:
                    logger.debug(f"[SBC测算] {c_clean} {p_mode} 结果未变(静默保持)")
            except Exception as e_eval:
                logger.error(f"[SBC策略测算] 异常: {e_eval}")
                self.strategy_eval_result = {
                    "is_matched": False,
                    "period": p_mode,
                    "reason": f"策略测算异常: {e_eval}"
                }
                self.update()
        else:
            # 3. 日内分时周期 (1m / 2d / 3d): 运行分时 7 节点与阶梯买卖测算
            try:
                from ats.intraday_strategy_engine import IntradayStrategyEngine
                engine = IntradayStrategyEngine.get_instance()
                curr_t = str(self.df_intraday.index[-1]) if len(self.df_intraday) > 0 else "15:00:00"
                curr_p = float(self.df_intraday['close'].iloc[-1]) if 'close' in self.df_intraday.columns else (
                    float(self.df_intraday['trade'].iloc[-1]) if 'trade' in self.df_intraday.columns else self.open_price
                )
                hi_p = float(self.df_intraday['high'].max()) if 'high' in self.df_intraday.columns else curr_p
                lo_p = float(self.df_intraday['low'].min()) if 'low' in self.df_intraday.columns else curr_p

                eval_res = engine.evaluate_seven_nodes(
                    code=c_clean,
                    current_time_str=curr_t,
                    open_price=self.open_price if self.open_price > 0 else curr_p,
                    price=curr_p,
                    high_price=hi_p,
                    low_price=lo_p,
                    vwap=self.vwap if self.vwap > 0 else curr_p
                )
                self.strategy_eval_result = {
                    "is_matched": True,
                    "period": p_mode,
                    "score": eval_res.get("total_score", 0),
                    "entry_price": curr_p,
                    "stop_loss": round(lo_p * 0.985, 2),
                    "target_price_1": round(self.target_sell_min if self.target_sell_min > 0 else curr_p * 1.05, 2),
                    "target_price_2": round(self.target_sell_max if self.target_sell_max > 0 else curr_p * 1.10, 2),
                    "pattern_name": eval_res.get("pattern_name", ""),
                    "reason": f"分时7节点评分: {eval_res.get('total_score', 0)}分 ({eval_res.get('pattern_name', '')}) | {eval_res.get('guidance_text', '')}"
                }
                self.update()

                cur_node_sig = (
                    c_clean,
                    p_mode,
                    round(float(eval_res.get("total_score", 0)), 1),
                    str(eval_res.get("pattern_name", ""))
                )
                last_node_sig = getattr(self, '_last_node_log_signature', None)
                if last_node_sig != cur_node_sig:
                    self._last_node_log_signature = cur_node_sig
                    logger.info(f"🎯 [SBC快捷键R分时测算] {c_clean} 评分: {eval_res.get('total_score', 0)}分 | {eval_res.get('pattern_name')}")
                else:
                    logger.debug(f"[SBC分时测算] {c_clean} 分时节点未变(静默保持)")
            except Exception as e_node:
                logger.error(f"[SBC分时测算] 异常: {e_node}")
                self.strategy_eval_result = {
                    "is_matched": False,
                    "period": p_mode,
                    "reason": f"分时测算异常: {e_node}"
                }
                self.update()

    def wheelEvent(self, event):
        """🔍 鼠标滚轮缩放：以鼠标所在 X 坐标为锚点进行平滑缩放"""
        if self.df_intraday is None or self.df_intraday.empty:
            return

        total_n = len(self.df_intraday)
        if total_n < 5:
            return

        cur_start = max(0, self._zoom_start_idx)
        cur_end = min(total_n - 1, self._zoom_end_idx if self._zoom_end_idx >= 0 else total_n - 1)
        cur_count = cur_end - cur_start + 1

        delta_y = event.angleDelta().y()
        if delta_y == 0:
            return

        margin_left = 55
        margin_right = 75
        chart_w = max(10, self.width() - margin_left - margin_right)
        mouse_pos = event.position() if hasattr(event, "position") else event.pos()
        mouse_x = mouse_pos.x()
        rel_x = max(0.0, min(1.0, (mouse_x - margin_left) / float(chart_w)))

        if delta_y > 0:
            # 向上滚：放大 (缩减可视数量，最少保留 8 根 K 棒)
            new_count = max(8, int(cur_count * 0.80))
            if new_count >= cur_count:
                new_count = max(8, cur_count - 2)
            diff = cur_count - new_count
            left_diff = int(round(diff * rel_x))
            right_diff = diff - left_diff
            new_start = cur_start + left_diff
            new_end = cur_end - right_diff
        else:
            # 向下滚：缩小 (增加可视数量，最大至全量 total_n)
            new_count = min(total_n, int(cur_count * 1.25) + 2)
            diff = new_count - cur_count
            left_diff = int(round(diff * rel_x))
            right_diff = diff - left_diff
            new_start = max(0, cur_start - left_diff)
            new_end = min(total_n - 1, cur_end + right_diff)

        # 越界防溢出修正
        if new_start < 0:
            new_end = min(total_n - 1, new_end - new_start)
            new_start = 0
        if new_end >= total_n:
            new_start = max(0, new_start - (new_end - (total_n - 1)))
            new_end = total_n - 1

        if new_start == 0 and new_end == total_n - 1:
            self._zoom_start_idx = 0
            self._zoom_end_idx = -1
        else:
            self._zoom_start_idx = new_start
            self._zoom_end_idx = new_end

        self.update()
        event.accept()

    def mousePressEvent(self, event):
        """鼠标按下：默认左键拖拽为平移视图，Shift+左键为框选放大，右键单击重置"""
        mouse_pos = event.position() if hasattr(event, "position") else event.pos()

        if event.button() == Qt.MouseButton.RightButton:
            # 记录右键按下点，若松开未移动则为一键重置，若移动则为右键平移
            self._right_press_pos = mouse_pos
            self._is_right_panning = False
            if self.df_intraday is not None and not self.df_intraday.empty:
                total_n = len(self.df_intraday)
                cur_start = max(0, self._zoom_start_idx)
                cur_end = min(total_n - 1, self._zoom_end_idx if self._zoom_end_idx >= 0 else total_n - 1)
                self._right_pan_start_indices = (cur_start, cur_end)
            event.accept()
            return

        elif event.button() == Qt.MouseButton.LeftButton or event.button() == Qt.MouseButton.MiddleButton:
            # 🎯 优先检查是否点击命中了买卖信号标签或关键成交点 (点击收益与持仓连线交互)
            if event.button() == Qt.MouseButton.LeftButton and getattr(self, '_signal_hit_boxes', None):
                m_pt = mouse_pos.toPoint() if hasattr(mouse_pos, 'toPoint') else QPoint(int(mouse_pos.x()), int(mouse_pos.y()))
                for hb in reversed(self._signal_hit_boxes):
                    rect = hb["rect"]
                    expanded_rect = rect.adjusted(-6, -6, 6, 6)
                    dist_sq = (hb["x"] - mouse_pos.x())**2 + (hb["y"] - mouse_pos.y())**2
                    if expanded_rect.contains(m_pt) or dist_sq <= 400:
                        hit_tid = hb.get("trade_id")
                        if hit_tid is not None:
                            self.selected_trade_id = hit_tid
                            self.update()
                            event.accept()
                            return

            if self.df_intraday is not None and not self.df_intraday.empty:
                total_n = len(self.df_intraday)
                cur_start = max(0, self._zoom_start_idx)
                cur_end = min(total_n - 1, self._zoom_end_idx if self._zoom_end_idx >= 0 else total_n - 1)

                is_shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

                if is_shift and event.button() == Qt.MouseButton.LeftButton:
                    # 🔍 Shift+左键：框选放大模式 (Rubberband Box Zoom)
                    self._box_zoom_origin = mouse_pos
                    self._box_zoom_current = mouse_pos
                    self._is_box_zooming = False
                    self._pan_start_x = mouse_pos.x()
                    self._pan_start_indices = (cur_start, cur_end)
                else:
                    # 🖐️ 默认鼠标左键/中键：平移视图查看边缘被遮挡信息 (Pan)
                    self._is_panning = True
                    self._pan_start_x = mouse_pos.x()
                    self._pan_start_indices = (cur_start, cur_end)
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)

                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动：平滑平移视图或 Shift 框选选区绘制"""
        mouse_pos = event.position() if hasattr(event, "position") else event.pos()

        # 1. 🖐️ 默认左键/中键平移视图 (Pan)
        if self._is_panning and self.df_intraday is not None and not self.df_intraday.empty:
            total_n = len(self.df_intraday)
            dx = mouse_pos.x() - self._pan_start_x
            orig_start, orig_end = self._pan_start_indices
            if orig_start == 0 and orig_end == total_n - 1 and total_n > 50:
                # 若当前处于 100% 全景，拖拽时自动切入局部可平移视口
                orig_start = max(0, total_n - 80)
                orig_end = total_n - 1

            cur_count = orig_end - orig_start + 1
            margin_left = 55
            margin_right = 75
            chart_w = max(10, self.width() - margin_left - margin_right)
            bar_px = max(1.0, chart_w / max(1, cur_count))
            shift_bars = int(round(dx / bar_px))

            new_start = max(0, min(total_n - 1, orig_start - shift_bars))
            new_end = max(0, min(total_n - 1, orig_end - shift_bars))
            self._zoom_start_idx = new_start
            self._zoom_end_idx = new_end
            self.update()
            event.accept()
            return

        # 2. 🖐️ 右键按住拖拽平移
        if (event.buttons() & Qt.MouseButton.RightButton) and self._right_press_pos is not None:
            dx = mouse_pos.x() - self._right_press_pos.x()
            if abs(dx) > 3 or self._is_right_panning:
                self._is_right_panning = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                if self.df_intraday is not None and not self.df_intraday.empty:
                    total_n = len(self.df_intraday)
                    orig_start, orig_end = self._right_pan_start_indices
                    if orig_start == 0 and orig_end == total_n - 1 and total_n > 50:
                        orig_start = max(0, total_n - 80)
                        orig_end = total_n - 1

                    cur_count = orig_end - orig_start + 1
                    margin_left = 55
                    margin_right = 75
                    chart_w = max(10, self.width() - margin_left - margin_right)
                    bar_px = max(1.0, chart_w / max(1, cur_count))
                    shift_bars = int(round(dx / bar_px))

                    new_start = max(0, min(total_n - 1, orig_start - shift_bars))
                    new_end = max(0, min(total_n - 1, orig_end - shift_bars))
                    self._zoom_start_idx = new_start
                    self._zoom_end_idx = new_end
                    self.update()
                event.accept()
                return

        # 3. 🔍 Shift+左键拖拽框选放大 (Rubberband Box Zoom)
        if (event.buttons() & Qt.MouseButton.LeftButton) and self._box_zoom_origin is not None:
            dx = mouse_pos.x() - self._box_zoom_origin.x()
            dy = mouse_pos.y() - self._box_zoom_origin.y()
            if abs(dx) > 6 or abs(dy) > 6 or self._is_box_zooming:
                self._is_box_zooming = True
                self._box_zoom_current = mouse_pos
                self.setCursor(Qt.CursorShape.CrossCursor)
                self.update()
                event.accept()
                return

        # 4. 🎯 正常悬停：记录 hover_pos 触发实时十字光标与价格浮标
        self._hover_pos = mouse_pos
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """鼠标离开画布：清除光标价格与十字线"""
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标松开：结束平移、结算 Shift 框选放大或右键单击一键重置"""
        if event.button() == Qt.MouseButton.RightButton:
            if not self._is_right_panning:
                # 纯右键单击：执行一键重置 100% 全景
                self.reset_view()
            self._is_right_panning = False
            self._right_press_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        elif event.button() == Qt.MouseButton.LeftButton:
            if self._is_box_zooming and self._box_zoom_origin and self._box_zoom_current and self.df_intraday is not None and not self.df_intraday.empty:
                # 结算框选放大区域
                margin_left = 55
                margin_right = 75
                chart_w = max(10, self.width() - margin_left - margin_right)

                x1 = min(self._box_zoom_origin.x(), self._box_zoom_current.x())
                x2 = max(self._box_zoom_origin.x(), self._box_zoom_current.x())

                if (x2 - x1) >= 12:
                    df_view, cur_s, cur_e = self._get_visible_slice()
                    vis_n = len(df_view)
                    if vis_n > 0:
                        rel_x1 = max(0.0, min(1.0, (x1 - margin_left) / float(chart_w)))
                        rel_x2 = max(0.0, min(1.0, (x2 - margin_left) / float(chart_w)))

                        idx_from = cur_s + int(round(rel_x1 * (vis_n - 1)))
                        idx_to = cur_s + int(round(rel_x2 * (vis_n - 1)))
                        if idx_to - idx_from >= 3:
                            self._zoom_start_idx = max(0, min(len(self.df_intraday) - 1, idx_from))
                            self._zoom_end_idx = max(0, min(len(self.df_intraday) - 1, idx_to))

            self._is_box_zooming = False
            self._box_zoom_origin = None
            self._box_zoom_current = None
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            event.accept()
            return

        elif event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def set_data(self, df_intraday: pd.DataFrame, open_p: float, vwap_p: float, high_p: float, low_p: float, sell_min: float, sell_max: float, signals: list, period_mode: str = "1m"):
        self.df_intraday = df_intraday
        self.open_price = open_p
        self.vwap = vwap_p
        self.high_price = high_p
        self.low_price = low_p
        self.target_sell_min = sell_min
        self.target_sell_max = sell_max
        self.signals = signals or []
        if getattr(self, '_last_period_mode', None) != period_mode or getattr(self, '_last_code', None) != getattr(self, 'code', None):
            self._zoom_start_idx = 0
            self._zoom_end_idx = -1
            self._last_period_mode = period_mode
            self._last_code = getattr(self, 'code', None)
            self.strategy_eval_result = None  # 切换周期或标的时重置策略测算结果
            self._last_eval_log_signature = None
            self._last_node_log_signature = None
        self.period_mode = period_mode
        self.update()

    def set_kline_data(self, df_kline: pd.DataFrame, open_p: float = 0.0, vwap_p: float = 0.0, high_p: float = 0.0, low_p: float = 0.0, sell_min: float = 0.0, sell_max: float = 0.0, signals: list = None, period_mode: str = "5m"):
        self.df_intraday = df_kline
        self.open_price = open_p
        self.vwap = vwap_p
        self.high_price = high_p
        self.low_price = low_p
        self.target_sell_min = sell_min
        self.target_sell_max = sell_max
        self.signals = signals or []
        if getattr(self, '_last_period_mode', None) != period_mode or getattr(self, '_last_code', None) != getattr(self, 'code', None):
            self._zoom_start_idx = 0
            self._zoom_end_idx = -1
            self._last_period_mode = period_mode
            self._last_code = getattr(self, 'code', None)
            self.strategy_eval_result = None  # 切换周期或标的时重置策略测算结果
            self._last_eval_log_signature = None
            self._last_node_log_signature = None
        self.period_mode = period_mode
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self._signal_hit_boxes = []
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            w = self.width()
            h = self.height()

            painter.fillRect(0, 0, w, h, QColor("#0c0d14"))

            margin_left = 55
            margin_right = 75
            margin_top = 30
            margin_bottom = 30

            chart_w = w - margin_left - margin_right
            chart_h = h - margin_top - margin_bottom

            if chart_w <= 10 or chart_h <= 10:
                return

            painter.setPen(QPen(QColor("#202030"), 1))
            painter.drawRect(margin_left, margin_top, chart_w, chart_h)

            if self.df_intraday is None or self.df_intraday.empty:
                painter.setPen(QPen(QColor("#888899"), 1))
                painter.setFont(QFont("Microsoft YaHei", 10))
                painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"⏳ 正在加载 [{self.period_mode}] 行情走势图...")
                return

            # 1. K 线图模式 (5m / 15m / 30m / 60m / day / week / month)
            if self.period_mode in ["5m", "15m", "30m", "60m", "day", "week", "month"]:
                self._paint_kline(painter, margin_left, margin_top, chart_w, chart_h)
            else:
                # 2. 分时图模式 (1m / 2d / 3d)
                self._paint_intraday(painter, margin_left, margin_top, chart_w, chart_h)

            # 3. 🔍 顶层绘制鼠标左键框选放大矩形遮罩 (Rubberband Box Zoom)
            if getattr(self, '_is_box_zooming', False) and self._box_zoom_origin and self._box_zoom_current:
                x1 = min(self._box_zoom_origin.x(), self._box_zoom_current.x())
                x2 = max(self._box_zoom_origin.x(), self._box_zoom_current.x())
                y1 = min(self._box_zoom_origin.y(), self._box_zoom_current.y())
                y2 = max(self._box_zoom_origin.y(), self._box_zoom_current.y())

                rx = max(margin_left, x1)
                rw = max(1, min(margin_left + chart_w, x2) - rx)
                ry = max(margin_top, y1)
                rh = max(1, min(margin_top + chart_h, y2) - ry)

                # 估算框选涵盖的 K 棒数量
                df_view, start_i, end_i = self._get_visible_slice()
                vis_n = len(df_view)
                sel_n = max(1, int(round((rw / max(1.0, float(chart_w))) * vis_n))) if vis_n > 0 else 1

                box_rect = QRect(int(rx), int(ry), int(rw), int(rh))
                painter.setPen(QPen(QColor("#00E5FF"), 1.2, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(QColor(0, 229, 255, 35)))
                painter.drawRect(box_rect)

                # 框选角标提示
                lbl_tip = f"🔍 选定: {sel_n} 根 [松开放大]"
                painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                painter.setPen(QPen(QColor("#FFFFFF")))
                painter.setBrush(QBrush(QColor("#00384d")))
                tag_y = max(4, int(ry - 18))
                painter.drawRoundedRect(int(rx), tag_y, 130, 16, 2, 2)
                painter.drawText(int(rx + 4), tag_y + 12, lbl_tip)

            # 4. 🎯 鼠标指针悬停：十字光标、动态 Y 轴精确价格胶囊与光标跟随价格浮标
            if getattr(self, '_hover_pos', None) and self._coord_info.get("ready"):
                hx = self._hover_pos.x()
                hy = self._hover_pos.y()
                c_info = self._coord_info
                ml = c_info["margin_left"]
                mt = c_info["margin_top"]
                cw = c_info["chart_w"]
                mh = c_info["main_h"]
                min_p = c_info["min_p"]
                max_p = c_info["max_p"]
                times = c_info.get("times", [])

                if ml <= hx <= (ml + cw) and mt <= hy <= (mt + mh):
                    # 精确反推当前指针所在 Y 坐标的价格 (与绘制完全同源)
                    p_ratio = max(0.0, min(1.0, 1.0 - (hy - mt) / float(mh)))
                    p_hover = min_p + (max_p - min_p) * p_ratio

                    # ① 十字虚线 (水平线与垂直线)
                    painter.setPen(QPen(QColor("#4a5578"), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(int(ml), int(hy), int(ml + cw), int(hy))
                    painter.drawLine(int(hx), int(mt), int(hx), int(mt + mh))

                    # ② 右侧 Y 轴动态价格高亮胶囊 (醒目青底白字)
                    tag_w = 58
                    tag_h = 18
                    tag_y = max(mt, min(mt + mh - tag_h, int(hy - tag_h / 2)))
                    painter.setPen(QPen(QColor("#00E5FF"), 1.2))
                    painter.setBrush(QBrush(QColor("#002b3d")))
                    painter.drawRoundedRect(int(ml + cw + 2), tag_y, tag_w, tag_h, 3, 3)

                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#00FFFF")))
                    painter.drawText(int(ml + cw + 5), tag_y + 13, f"{p_hover:.2f}")

                    # 计算当前光标所指 K 棒序号
                    idx_hover = -1
                    if times and len(times) > 0:
                        idx_hover = max(0, min(len(times) - 1, int(round(((hx - ml) / float(cw)) * (len(times) - 1)))))

                    # ③ 鼠标指针右上角跟随微浮标 (指针指到哪，价格与通道大小高度跟到哪)
                    tip_str = f"{p_hover:.2f}"
                    ch_up_arr = c_info.get("ch_up", [])
                    ch_mid_arr = c_info.get("ch_mid", [])
                    ch_dn_arr = c_info.get("ch_dn", [])
                    if 0 <= idx_hover < len(ch_up_arr) and 0 <= idx_hover < len(ch_dn_arr):
                        c_u = float(ch_up_arr[idx_hover])
                        c_d = float(ch_dn_arr[idx_hover])
                        c_m = float(ch_mid_arr[idx_hover]) if idx_hover < len(ch_mid_arr) else 0.0
                        if c_u > 0 and c_d > 0:
                            h_diff = max(0.0, c_u - c_d)
                            h_pct = (h_diff / max(1e-4, c_m)) * 100.0 if c_m > 0 else 0.0
                            tip_str += f" | 通道:上{c_u:.2f} 中{c_m:.2f} 下{c_d:.2f} (高:{h_diff:.2f}元, {h_pct:.1f}%)"

                    tip_w = max(52, len(tip_str) * 7 + 12)
                    tip_h = 16
                    tip_x = min(ml + cw - tip_w - 4, max(ml + 4, int(hx + 12)))
                    tip_y = max(mt + 4, min(mt + mh - tip_h - 4, int(hy - 20)))
                    painter.setPen(QPen(QColor("#00E5FF"), 1))
                    painter.setBrush(QBrush(QColor(12, 16, 28, 230)))
                    painter.drawRoundedRect(tip_x, tip_y, tip_w, tip_h, 2, 2)
                    painter.setPen(QPen(QColor("#FFFFFF")))
                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.drawText(tip_x + 6, tip_y + 12, tip_str)

                    # ④ 底部 X 轴时间/日期对齐标签
                    if times and len(times) > 0:
                        t_str = str(times[idx_hover])
                        if len(t_str) > 10:
                            t_str = t_str[-8:]  # 截取 HH:MM:SS 或 HH:MM
                        t_w = max(46, len(t_str) * 7 + 8)
                        t_x = max(ml, min(ml + cw - t_w, int(hx - t_w / 2)))
                        painter.setPen(QPen(QColor("#8899bb"), 1))
                        painter.setBrush(QBrush(QColor("#181d2a")))
                        painter.drawRoundedRect(t_x, int(mt + mh + 2), t_w, 16, 2, 2)
                        painter.setFont(QFont("Consolas", 7))
                        painter.setPen(QPen(QColor("#ccddee")))
                        painter.drawText(t_x + 4, int(mt + mh + 14), t_str)

            # 5. 🔍 局部缩放状态提示 (默认彻底隐藏不遮挡任何内容，仅当鼠标移至右上角时展开悬浮气泡)
            if self._is_zoomed() and self._coord_info.get("ready"):
                ml = self._coord_info["margin_left"]
                mt = self._coord_info["margin_top"]
                cw = self._coord_info["chart_w"]
                c_hover = getattr(self, '_hover_pos', None)
                is_hover_top_right = (c_hover is not None and (ml + cw - 120 <= c_hover.x() <= ml + cw + 40) and (mt <= c_hover.y() <= mt + 28))

                if is_hover_top_right:
                    df_v, s_i, e_i = self._get_visible_slice()
                    zoom_tip = f"🔍 局部: {len(df_v)}/{len(self.df_intraday)} 根 [左键平移 | Shift框选 | 滚轮缩放 | 右键重置]"
                    painter.setFont(QFont("Microsoft YaHei", 8))
                    painter.setPen(QPen(QColor("#00E5FF"), 1))
                    painter.setBrush(QBrush(QColor(12, 18, 30, 240)))
                    tip_w = 340
                    tip_x = int(ml + cw - tip_w)
                    painter.drawRoundedRect(tip_x, int(mt + 4), tip_w, 20, 3, 3)
                    painter.setPen(QPen(QColor("#00E5FF")))
                    painter.drawText(tip_x + 8, int(mt + 18), zoom_tip)
        finally:
            painter.end()

    def _paint_intraday(self, painter: QPainter, margin_left: int, margin_top: int, chart_w: int, chart_h: int):
        df_view, start_i, end_i = self._get_visible_slice()
        if df_view.empty:
            return

        prices = df_view['close'].astype(float).values if 'close' in df_view.columns else []
        vwaps = df_view['vwap'].astype(float).values if 'vwap' in df_view.columns else []
        times = list(df_view.index.astype(str))

        if len(prices) == 0:
            return

        op_ref = self.open_price if self.open_price > 1.0 else (prices[0] if len(prices) > 0 else 10.0)
        max_valid_price = (op_ref * 1.70) if op_ref > 10.0 else (op_ref * 3.0)

        all_cands = []
        for p in prices:
            if 1.0 < p <= max_valid_price:
                all_cands.append(p)
        for v in vwaps:
            if 1.0 < v <= max_valid_price:
                all_cands.append(v)
        if op_ref > 0:
            all_cands.append(op_ref)
        if 0 < self.high_price <= max_valid_price:
            all_cands.append(self.high_price)
        if 0 < self.target_sell_min <= max_valid_price:
            all_cands.append(self.target_sell_min)
        if self.signals:
            for sig in self.signals:
                sig_p = float(sig.get("price", 0.0) if isinstance(sig, dict) else getattr(sig, "price", 0.0))
                if 0 < sig_p <= max_valid_price:
                    all_cands.append(sig_p)

        if not all_cands:
            all_cands = [op_ref if op_ref > 0 else 100.0]

        min_p = min(all_cands) * 0.98
        max_p = max(all_cands) * 1.02
        if max_p <= min_p:
            max_p = min_p + 1.0

        p_range = max_p - min_p

        self._coord_info = {
            "ready": True,
            "min_p": min_p,
            "max_p": max_p,
            "margin_left": margin_left,
            "margin_top": margin_top,
            "chart_w": chart_w,
            "main_h": chart_h,
            "times": times,
            "n_items": len(prices),
        }

        def price_to_y(p_val: float) -> float:
            return margin_top + chart_h - ((p_val - min_p) / p_range) * chart_h

        def time_to_x(idx_val: int) -> float:
            total_n = max(240 if self.period_mode == "1m" and not self._is_zoomed() else len(prices), len(prices))
            return margin_left + (idx_val / max(1, total_n - 1)) * chart_w

        # 绘制背景水平网格线
        grid_pens = [
            (min_p + p_range * 0.75, QColor("#1e2230"), Qt.PenStyle.DotLine),
            (min_p + p_range * 0.50, QColor("#282c3f"), Qt.PenStyle.DashLine),
            (min_p + p_range * 0.25, QColor("#1e2230"), Qt.PenStyle.DotLine),
        ]
        for gp_val, gp_col, gp_style in grid_pens:
            gy = price_to_y(gp_val)
            painter.setPen(QPen(gp_col, 1, gp_style))
            painter.drawLine(margin_left, int(gy), margin_left + chart_w, int(gy))

        # 📅 多日分时 (2d / 3d / 5d) 各交易日垂直虚线分割线与日期角标标注
        if self.period_mode in ["2d", "3d", "5d"] and len(times) > 1:
            dates_list = []
            if "date" in df_view.columns:
                dates_list = list(df_view["date"].astype(str))
            else:
                for t in times:
                    parts = str(t).split()
                    dates_list.append(parts[0] if len(parts) > 1 else str(t)[:10])

            prev_d = None
            for idx_t, d_cur in enumerate(dates_list):
                if prev_d is not None and d_cur != prev_d:
                    dx = time_to_x(idx_t)
                    painter.setPen(QPen(QColor("#2d3748"), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(int(dx), int(margin_top), int(dx), int(margin_top + chart_h))
                    
                    # 日期角标
                    d_short = d_cur[-5:] if len(d_cur) >= 5 else d_cur
                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#8899bb")))
                    painter.drawText(int(dx + 4), int(margin_top + 14), d_short)
                elif prev_d is None and d_cur:
                    d_short = d_cur[-5:] if len(d_cur) >= 5 else d_cur
                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#8899bb")))
                    painter.drawText(int(margin_left + 4), int(margin_top + 14), d_short)
                prev_d = d_cur

        # 绘制 VWAP 均价线 (金黄虚线)
        if len(vwaps) > 1:
            path_vwap = QPainterPath()
            path_vwap.moveTo(time_to_x(0), price_to_y(vwaps[0]))
            for i in range(1, len(vwaps)):
                if vwaps[i] > 1.0:
                    path_vwap.lineTo(time_to_x(i), price_to_y(vwaps[i]))
            painter.setPen(QPen(QColor("#ffd700"), 1.5, Qt.PenStyle.DashLine))
            painter.drawPath(path_vwap)

        # 绘制分时价格曲线 (亮青色)
        if len(prices) > 1:
            path_p = QPainterPath()
            path_p.moveTo(time_to_x(0), price_to_y(prices[0]))
            for i in range(1, len(prices)):
                if prices[i] > 1.0:
                    path_p.lineTo(time_to_x(i), price_to_y(prices[i]))
            painter.setPen(QPen(QColor("#00b4d8"), 1.8))
            painter.drawPath(path_p)

        # 🔴 开盘基准线
        if op_ref > 0:
            y_op = price_to_y(op_ref)
            painter.setPen(QPen(QColor("#ff4444"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(margin_left, int(y_op), margin_left + chart_w, int(y_op))
            painter.setPen(QPen(QColor("#ff4444"), 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(margin_left + chart_w + 3, int(y_op + 3), f"开盘:{op_ref:.2f}")

        # 🟢 目标止盈线
        if self.target_sell_min > 0:
            y_target = price_to_y(self.target_sell_min)
            painter.setPen(QPen(QColor("#00ff88"), 1, Qt.PenStyle.DashDotLine))
            painter.drawLine(margin_left, int(y_target), margin_left + chart_w, int(y_target))
            painter.setPen(QPen(QColor("#00ff88"), 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(margin_left + chart_w + 3, int(y_target + 3), f"目标:{self.target_sell_min:.2f}")

        # 🟡 最新 VWAP 标签
        if len(vwaps) > 0 and vwaps[-1] > 1.0:
            y_vwap = price_to_y(vwaps[-1])
            painter.setPen(QPen(QColor("#ffd700"), 1))
            painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            painter.drawText(margin_left + chart_w + 3, int(y_vwap + 3), f"VWAP:{vwaps[-1]:.2f}")

        # 🌟 绘制分时图上的买卖信号点与悬浮 Tag (自适应防遮挡 + 半透明毛玻璃 + 高对比度设计)
        if self.signals:
            times_raw = list(df_view.index.astype(str))
            times_5 = [t[-5:] if len(t) >= 5 else t for t in times_raw]

            sig_drawn_slots = {}
            for sig in self.signals:
                sig_p = float(sig.get("price", 0.0) if isinstance(sig, dict) else getattr(sig, "price", 0.0))
                if sig_p <= 0 or sig_p > max_valid_price:
                    continue

                sig_t = str(sig.get("timestamp", sig.get("time", "")) if isinstance(sig, dict) else getattr(sig, "timestamp", getattr(sig, "time", ""))).strip()
                action_type = str(sig.get("action", sig.get("type", "sell")) if isinstance(sig, dict) else getattr(sig, "action", getattr(sig, "type", "sell"))).lower()
                is_buy = "buy" in action_type or "买" in action_type
                prefix = "🟢 买" if is_buy else "🔴 卖"
                border_color = QColor("#00ff88") if is_buy else QColor("#ff4d4f")
                bg_color = QColor(10, 32, 18, 185) if is_buy else QColor(36, 12, 16, 185) # 半透明毛玻璃
                fg_color = QColor("#ffffff") # 高对比度清晰白字
                dot_color = QColor("#00ff88") if is_buy else QColor("#ff4d4f")

                y_s = price_to_y(sig_p)

                # 寻找在当前可视切片时间轴上的对应位置 idx_s
                idx_s = -1
                sig_t_5 = sig_t[-5:] if len(sig_t) >= 5 else sig_t
                if sig_t in times_raw:
                    idx_s = times_raw.index(sig_t)
                elif sig_t_5 in times_5:
                    idx_candidates = [i for i, t in enumerate(times_5) if t == sig_t_5]
                    idx_s = idx_candidates[-1] if idx_candidates else -1
                else:
                    for i, t in enumerate(times_5):
                        if t >= sig_t_5:
                            idx_s = i
                            break

                trade_id_val = sig.get("trade_id") if isinstance(sig, dict) else getattr(sig, "trade_id", None)
                is_selected_trade = (trade_id_val is not None and trade_id_val == self.selected_trade_id)
                if is_selected_trade:
                    border_color = QColor("#FFD700")
                    bg_color = QColor(48, 38, 10, 230)

                if idx_s >= 0:
                    x_s = time_to_x(idx_s)
                    pnl_pct_v = sig.get("pnl_pct") if isinstance(sig, dict) else getattr(sig, "pnl_pct", None)
                    if not is_buy and pnl_pct_v is not None:
                        lbl_text = f"{prefix}:{sig_p:.2f} ({float(pnl_pct_v):+.1f}%)"
                    else:
                        lbl_text = f"{prefix}:{sig_p:.2f}"

                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    fm = painter.fontMetrics()
                    tw_k = fm.horizontalAdvance(lbl_text) + 10
                    th_k = fm.height() + 4

                    # 智能自适应放置在价格曲线上方或下方，并支持错层排布避让
                    slot_cnt = sig_drawn_slots.get(idx_s, 0)
                    sig_drawn_slots[idx_s] = slot_cnt + 1

                    if is_buy:
                        target_y = y_s + 10 + slot_cnt * (th_k + 4)
                        if target_y + th_k > margin_top + chart_h - 4:
                            target_y = y_s - th_k - 10 - slot_cnt * (th_k + 4)
                    else:
                        target_y = y_s - th_k - 10 - slot_cnt * (th_k + 4)
                        if target_y < margin_top + 4:
                            target_y = y_s + 10 + slot_cnt * (th_k + 4)

                    tag_x = int(max(margin_left + 2, min(margin_left + chart_w - tw_k - 2, x_s - tw_k / 2 + (slot_cnt % 2) * 8)))
                    tag_y = int(max(margin_top + 2, min(margin_top + chart_h - th_k - 2, target_y)))

                    # 注册点击区域
                    tag_rect = QRect(tag_x, tag_y, tw_k, th_k)
                    self._signal_hit_boxes.append({
                        "rect": tag_rect,
                        "trade_id": trade_id_val,
                        "sig": sig,
                        "x": x_s,
                        "y": y_s,
                        "is_buy": is_buy
                    })

                    # 1. 绘制垂直贯穿虚线与引线
                    painter.setPen(QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 100), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(int(x_s), int(margin_top + chart_h), int(x_s), int(margin_top))

                    # 2. 从标签中心向实际成交价连接精巧微引线
                    painter.setPen(QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 180), 1, Qt.PenStyle.SolidLine))
                    painter.drawLine(int(x_s), int(y_s), int(tag_x + tw_k / 2), int(tag_y + th_k if tag_y < y_s else tag_y))

                    # 3. 实际成交价处的精巧圆点
                    painter.setPen(QPen(QColor("#ffffff") if not is_selected_trade else QColor("#FFD700"), 1.2))
                    painter.setBrush(QBrush(dot_color))
                    painter.drawEllipse(int(x_s - 3), int(y_s - 3), 6, 6)

                    # 4. 半透明高对比度圆角胶囊
                    painter.setPen(QPen(border_color, 1.8 if is_selected_trade else 1.2))
                    painter.setBrush(QBrush(bg_color))
                    painter.drawRoundedRect(tag_x, tag_y, tw_k, th_k, 3, 3)

                    # 5. 高对比度白字
                    painter.setPen(QPen(fg_color))
                    painter.drawText(tag_x + 5, tag_y + th_k - 4, lbl_text)

            # 绘制当前选中的回测交易收益光束与详情卡片
            if self.selected_trade_id is not None:
                self._draw_selected_trade_linkage(painter, margin_left, margin_top, chart_w, chart_h)

        # 🌟 快捷键 R 自适应策略测算浮动 HUD (精简高对比度轻量卡片，靠左下放置不遮挡右侧K线与价格轴)
        if getattr(self, 'strategy_eval_result', None):
            self._draw_compact_strategy_hud(painter, margin_left, margin_top, chart_w, chart_h, self.strategy_eval_result)

    def _draw_compact_strategy_hud(
        self,
        painter: QPainter,
        margin_left: int,
        margin_top: int,
        chart_w: int,
        main_h: int,
        res_strat: dict
    ):
        """
        绘制极致通透、位置靠左下、重点信息醒目高对比度的策略测算轻量 HUD
        - 彻底省略冗长模式文本（第一行）；
        - 位置调低至左下角，彻底避开右侧最新K线、分时底部与价格刻度；
        - 背景 80 超轻通透毛玻璃，清晰看透背后所有指标；
        - 关键信息分段高对比度高亮 (得分:金黄, 介入:翡翠绿, 止损:珊瑚红, 目标:青蓝光)
        """
        if not res_strat:
            return

        is_matched = res_strat.get("is_matched", False)
        if not is_matched:
            fail_reason = str(res_strat.get("reason", "未触发反转突破信号"))
            hud_text = f"⚠️ 测算提示: {fail_reason}"
            font = QFont("Microsoft YaHei", 8, QFont.Weight.Normal)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(hud_text) + 16
            th = fm.height() + 6
            x = int(margin_left + 8)
            y = int(margin_top + main_h - th - 3)
            painter.setPen(QPen(QColor("#475569"), 1.0))
            painter.setBrush(QBrush(QColor(15, 23, 42, 85)))
            painter.drawRoundedRect(x, y, tw, th, 3, 3)
            painter.setPen(QPen(QColor("#94A3B8")))
            painter.drawText(x + 8, y + th - 4, hud_text)
            return

        score_v = res_strat.get("score", 0)
        entry_p = float(res_strat.get("entry_price", 0.0))
        stop_p = float(res_strat.get("stop_loss", 0.0))
        tgt_p1 = float(res_strat.get("target_price_1", 0.0))

        # 构建高对比度分段信息: (文本, 颜色)
        segments = [
            ("🎯", QColor("#FFD700")),
            (f"得分:{score_v}分", QColor("#FFD700")),
            ("|", QColor("#4B5563")),
            (f"介入:{entry_p:.2f}", QColor("#00FF88")),
            ("|", QColor("#4B5563")),
            (f"止损:{stop_p:.2f}", QColor("#FF5555")),
            ("|", QColor("#4B5563")),
            (f"目标:{tgt_p1:.2f}", QColor("#00E5FF")),
        ]

        font = QFont("Microsoft YaHei", 8, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        # 计算总宽度
        total_w = sum(fm.horizontalAdvance(text) + 5 for text, _ in segments) + 10
        total_h = fm.height() + 6

        # 💡 位置调低：贴在主图左下侧 (margin_left + 8)，完全避开右侧走势与刻度
        hud_x = int(margin_left + 8)
        hud_y = int(margin_top + main_h - total_h - 3)

        # 超轻通透背景 (仅 85 透明度，通透看清后面所有均线走势)
        painter.setPen(QPen(QColor("#00FF88"), 1.0))
        painter.setBrush(QBrush(QColor(8, 16, 24, 85)))
        painter.drawRoundedRect(hud_x, hud_y, total_w, total_h, 3, 3)

        # 分段彩色高亮绘制
        curr_x = hud_x + 6
        draw_y = hud_y + total_h - 5
        for text, col in segments:
            painter.setPen(QPen(col))
            painter.drawText(curr_x, draw_y, text)
            curr_x += fm.horizontalAdvance(text) + 5

    def _draw_adaptive_hud_box(self, painter, margin_left, margin_top, chart_w, main_h, hud_text, is_matched=True):
        """兼容老接口调用，直接路由至紧凑高对比度 HUD"""
        res_strat = getattr(self, 'strategy_eval_result', None)
        if res_strat:
            self._draw_compact_strategy_hud(painter, margin_left, margin_top, chart_w, main_h, res_strat)

    def _draw_selected_trade_linkage(self, painter: QPainter, margin_left: int, margin_top: int, chart_w: int, main_h: int):
        """
        【🎯 点击收益联动图元】
        当用户点击任意买卖信号时：
        1. 绘制持有期高亮半透明垂直条带 (买入日期~卖出日期)；
        2. 绘制从买入点到卖出点的直观光束连线与指示箭头；
        3. 浮动渲染高对比度【点击收益卡片】HUD：
           显示交易序号、买入/卖出价格、持仓天数、收益率、净利润与出场原因。
        """
        if self.selected_trade_id is None or not getattr(self, '_signal_hit_boxes', None):
            return

        matched_boxes = [hb for hb in self._signal_hit_boxes if hb.get("trade_id") == self.selected_trade_id]
        if not matched_boxes:
            return

        buy_hb = next((hb for hb in matched_boxes if hb.get("is_buy")), None)
        sell_hb = next((hb for hb in matched_boxes if not hb.get("is_buy")), None)

        trade_sig = (buy_hb or sell_hb)["sig"]
        t_id = trade_sig.get("trade_id", 0)
        pnl_pct = float(trade_sig.get("pnl_pct", 0.0))
        pnl_val = float(trade_sig.get("pnl", 0.0))
        h_days = int(trade_sig.get("holding_days", 1))
        b_p = float(trade_sig.get("buy_price", (buy_hb["sig"]["price"] if buy_hb else 0.0)))
        s_p = float(trade_sig.get("sell_price", (sell_hb["sig"]["price"] if sell_hb else 0.0)))
        b_d = str(trade_sig.get("buy_date", (buy_hb["sig"].get("time", "") if buy_hb else "")))[:10]
        s_d = str(trade_sig.get("sell_date", (sell_hb["sig"].get("time", "") if sell_hb else "")))[:10]
        pat_name = str(trade_sig.get("pattern_name", "共振启动"))
        sell_rsn = str(trade_sig.get("sell_reason", "策略平仓"))

        is_profit = pnl_pct >= 0
        beam_color = QColor("#00FF88") if is_profit else QColor("#FF4D4F")
        fill_color = QColor(0, 255, 136, 28) if is_profit else QColor(255, 77, 79, 28)

        # 1. 持股周期半透明垂直条带 (若买卖均在可视区)
        if buy_hb and sell_hb:
            x_left = min(buy_hb["x"], sell_hb["x"])
            x_right = max(buy_hb["x"], sell_hb["x"])
            span_w = max(4.0, x_right - x_left)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawRect(int(x_left), int(margin_top), int(span_w), int(main_h))

            # 2. 买入到卖出的收益光束连线
            pen_beam = QPen(beam_color, 2.2, Qt.PenStyle.DashDotLine)
            painter.setPen(pen_beam)
            painter.drawLine(int(buy_hb["x"]), int(buy_hb["y"]), int(sell_hb["x"]), int(sell_hb["y"]))

            # 在连线中点绘制收益率胶囊小标签
            mid_x = (buy_hb["x"] + sell_hb["x"]) / 2
            mid_y = (buy_hb["y"] + sell_hb["y"]) / 2
            badge_text = f"盈亏:{pnl_pct:+.2f}% ({pnl_val:+,.0f}元)"
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            fm_b = painter.fontMetrics()
            bw = fm_b.horizontalAdvance(badge_text) + 12
            bh = fm_b.height() + 4
            bx = int(mid_x - bw / 2)
            by = int(max(margin_top + 4, min(margin_top + main_h - bh - 4, mid_y - bh / 2)))

            painter.setPen(QPen(beam_color, 1.2))
            painter.setBrush(QBrush(QColor(10, 16, 26, 230)))
            painter.drawRoundedRect(bx, by, bw, bh, 3, 3)
            painter.setPen(QPen(QColor("#FFFFFF") if not is_profit else QColor("#00FFAA")))
            painter.drawText(bx + 6, by + bh - 4, badge_text)

        # 3. 顶部/中部精致悬浮【点击收益卡片】HUD
        card_title = f"🎯 【交易 #{t_id + 1} 收益详情】 盈亏率: {pnl_pct:+.2f}%  |  净利润: {pnl_val:+,.0f}元  (持仓: {h_days}天)"
        card_detail = f"买入: {b_d} @ {b_p:.2f} ({pat_name}) ➔ 卖出: {s_d} @ {s_p:.2f} | 离场: {sell_rsn}"

        painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
        fm_c = painter.fontMetrics()
        w1 = fm_c.horizontalAdvance(card_title)
        w2 = fm_c.horizontalAdvance(card_detail)
        card_w = max(w1, w2) + 24
        card_h = 42

        card_x = int(margin_left + (chart_w - card_w) / 2)
        card_y = int(margin_top + 38)  # 避开顶部通道标题

        painter.setPen(QPen(beam_color, 1.5))
        painter.setBrush(QBrush(QColor(12, 18, 28, 240)))
        painter.drawRoundedRect(card_x, card_y, card_w, card_h, 4, 4)

        # 第一行标题
        painter.setPen(QPen(beam_color))
        painter.drawText(card_x + 10, card_y + 16, card_title)

        # 第二行明细
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Normal))
        painter.setPen(QPen(QColor("#ccddee")))
        painter.drawText(card_x + 10, card_y + 34, card_detail)

    def _paint_kline(self, painter: QPainter, margin_left: int, margin_top: int, chart_w: int, chart_h: int):
        df_view, start_i, end_i = self._get_visible_slice()
        if df_view.empty:
            return

        opens = df_view['open'].astype(float).values
        closes = df_view['close'].astype(float).values
        highs = df_view['high'].astype(float).values
        lows = df_view['low'].astype(float).values
        vols = df_view['vol'].astype(float).values if 'vol' in df_view.columns else np.zeros(len(df_view))
        times = list(df_view.index.astype(str))

        ma5 = df_view['ma5'].astype(float).values if 'ma5' in df_view.columns else []
        ma20 = df_view['ma20'].astype(float).values if 'ma20' in df_view.columns else []
        b_up = df_view['boll_upper'].astype(float).values if 'boll_upper' in df_view.columns else []
        b_dn = df_view['boll_lower'].astype(float).values if 'boll_lower' in df_view.columns else []

        # ⚡ 提取通达信自动通道 (calc_trend_channel) 系列指标
        ch_up = df_view['ch_upper'].astype(float).values if 'ch_upper' in df_view.columns else []
        ch_mid = df_view['ch_mid'].astype(float).values if 'ch_mid' in df_view.columns else []
        ch_dn = df_view['ch_lower'].astype(float).values if 'ch_lower' in df_view.columns else []
        ch_tc2 = int(df_view['ch_tc2'].iloc[-1]) if 'ch_tc2' in df_view.columns and len(df_view) > 0 else 1
        ch_bc2 = int(df_view['ch_bc2'].iloc[-1]) if 'ch_bc2' in df_view.columns and len(df_view) > 0 else 1
        ch_supp_p = float(df_view['ch_supp_price'].iloc[-1]) if 'ch_supp_price' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_supp_price'].iloc[-1]) else 0.0
        ch_supp_days = int(df_view['ch_supp_days'].iloc[-1]) if 'ch_supp_days' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_supp_days'].iloc[-1]) else 0
        ch_supp_slope = float(df_view['ch_supp_slope'].iloc[-1]) if 'ch_supp_slope' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_supp_slope'].iloc[-1]) else 0.0
        ch_supp_slope_deg = float(df_view['ch_supp_slope_deg'].iloc[-1]) if 'ch_supp_slope_deg' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_supp_slope_deg'].iloc[-1]) else 0.0
        ch_supp_pos = float(df_view['ch_supp_pos'].iloc[-1]) if 'ch_supp_pos' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_supp_pos'].iloc[-1]) else 0.0
        ch_slope_deg = float(df_view['ch_slope_deg'].iloc[-1]) if 'ch_slope_deg' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_slope_deg'].iloc[-1]) else 0.0
        ch_pos = float(df_view['ch_pos'].iloc[-1]) if 'ch_pos' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_pos'].iloc[-1]) else 50.0
        rev_line = df_view['reversal_line'].astype(float).values if 'reversal_line' in df_view.columns else []
        rev_last = float(rev_line[-1]) if len(rev_line) > 0 else 0.0

        # 拐点与启动信号
        sig_bot = df_view['sig_bottom'].values if 'sig_bottom' in df_view.columns else np.zeros(len(df_view))
        sig_top_arr = df_view['sig_top'].values if 'sig_top' in df_view.columns else np.zeros(len(df_view))
        sig_launch_arr = df_view['sig_launch'].values if 'sig_launch' in df_view.columns else np.zeros(len(df_view))
        sig_escape_arr = df_view['sig_escape'].values if 'sig_escape' in df_view.columns else np.zeros(len(df_view))

        n = len(df_view)
        if n == 0:
            return

        main_h = int(chart_h * 0.75)
        vol_h = int(chart_h * 0.20)
        vol_top = margin_top + main_h + int(chart_h * 0.05)

        # 🎯 通道严格截止于最高价/最低价波段起点 (遵照通达信规则，历史左侧不画，杜绝左上角冗长斜线与 Y 轴失真)
        total_n = len(self.df_intraday)
        chan_len = max(ch_tc2, ch_bc2)
        global_chan_start = max(0, total_n - chan_len)
        local_chan_start = max(0, global_chan_start - start_i)

        # 全图最高最低价与波段空间 (用于 Fibonacci 黄金分割阶梯稳定呈现)
        all_highs = self.df_intraday['high'].astype(float).values if 'high' in self.df_intraday.columns else highs
        all_lows = self.df_intraday['low'].astype(float).values if 'low' in self.df_intraday.columns else lows
        full_high = float(np.max(all_highs))
        full_low = float(np.min(all_lows))
        fib_range = full_high - full_low

        # 🌟 严格截断界限：低于最低价 10%，高于最高价 10% (杜绝穿底穿顶及底部横线折线)
        min_cutoff = full_low * 0.90
        max_cutoff = full_high * 1.10

        # Y 轴自适应计算：仅将可视区 K 棒和有效波段区间内的通道价格纳入范围，绝不纳入穿底/穿顶虚值
        all_vals = list(highs) + list(lows)
        if len(b_up) > 0:
            all_vals += [x for x in b_up if min_cutoff <= x <= max_cutoff]
        if len(b_dn) > 0:
            all_vals += [x for x in b_dn if min_cutoff <= x <= max_cutoff]

        if len(ch_up) > local_chan_start and local_chan_start < n:
            all_vals += [x for x in ch_up[local_chan_start:] if min_cutoff <= x <= max_cutoff]
        if len(ch_dn) > local_chan_start and local_chan_start < n:
            all_vals += [x for x in ch_dn[local_chan_start:] if min_cutoff <= x <= max_cutoff]

        if ch_supp_p > 0 and (total_n - ch_supp_days <= end_i) and min_cutoff <= ch_supp_p <= max_cutoff:
            all_vals.append(ch_supp_p)
        if rev_last > 0 and min_cutoff <= rev_last <= max_cutoff:
            all_vals.append(rev_last)

        # 💡 将 SBC 买卖信号价格、开盘价、目标价纳入 Y 轴范围计算，确保买卖线完整显示不被截断
        if self.open_price > 0 and min_cutoff <= self.open_price <= max_cutoff:
            all_vals.append(self.open_price)
        if self.target_sell_min > 0 and min_cutoff <= self.target_sell_min <= max_cutoff:
            all_vals.append(self.target_sell_min)
        if self.signals:
            for sig in self.signals:
                sig_p = float(sig.get("price", 0.0) if isinstance(sig, dict) else getattr(sig, "price", 0.0))
                if min_cutoff <= sig_p <= max_cutoff:
                    all_vals.append(sig_p)

        all_vals = [x for x in all_vals if x > 0]
        if not all_vals:
            return

        min_p = min(all_vals) * 0.99
        max_p = max(all_vals) * 1.01
        if max_p <= min_p:
            max_p = min_p + 1.0
        p_range = max_p - min_p

        self._coord_info = {
            "ready": True,
            "min_p": min_p,
            "max_p": max_p,
            "margin_left": margin_left,
            "margin_top": margin_top,
            "chart_w": chart_w,
            "main_h": main_h,
            "times": times,
            "n_items": n,
            "ch_up": ch_up,
            "ch_mid": ch_mid,
            "ch_dn": ch_dn,
        }

        max_v = max(vols) if len(vols) > 0 and max(vols) > 0 else 1.0

        def k_to_y(p_val: float) -> float:
            return margin_top + main_h - ((p_val - min_p) / p_range) * main_h

        def k_to_x(idx_val: int) -> float:
            return margin_left + (idx_val / max(1, n - 1)) * chart_w

        bar_w = max(2.0, (chart_w / n) * 0.7)

        # 1. 🌟 绘制 Fibonacci 黄金分割阶梯线 (基于加载的所有数据价格区间，通达信同款自上而下对齐)
        if fib_range > 1e-4:
            fib_levels = [
                (full_low + fib_range * 0.809, "80.9%", QColor("#FF7700")),  # 高阻位 (如 1231)
                (full_low + fib_range * 0.618, "61.8%", QColor("#FFD700")),  # 黄金阻力 (如 1122)
                (full_low + fib_range * 0.500, "50.0%", QColor("#00E5FF")),  # 中枢位 (如 1055)
                (full_low + fib_range * 0.382, "38.2%", QColor("#FFD700")),  # 黄金支撑 (如 988.5)
                (full_low + fib_range * 0.191, "19.1%", QColor("#00FF88")),  # 强撑位 (如 880.2)
            ]
            fib_start_x = int(margin_left + chart_w * 0.45)  # 短虚线，不遮挡左侧历史 K 线
            fib_end_x = int(margin_left + chart_w)
            for f_val, f_lbl, f_col in fib_levels:
                if min_p <= f_val <= max_p:
                    y_fib = k_to_y(f_val)
                    painter.setPen(QPen(f_col, 1, Qt.PenStyle.DotLine))
                    painter.drawLine(fib_start_x, int(y_fib), fib_end_x, int(y_fib))

        # 2. 🌟 绘制通达信自动通道三轨 (从波段起点开始，三轨各自独立延伸，各自在低于最低价10%/高于最高价10%处独立截止)
        if len(ch_up) > 1 and len(ch_dn) > 1 and local_chan_start < n:
            path_ch_up = QPainterPath()
            path_ch_mid = QPainterPath()
            path_ch_dn = QPainterPath()

            # 2.1 上轨独立绘制 (一直画到最新 K 棒或自身越界，不与下轨等长绑定截断)
            started_up = False
            for i in range(local_chan_start, n):
                v = ch_up[i] if i < len(ch_up) else 0.0
                if min_cutoff <= v <= max_cutoff:
                    if not started_up:
                        path_ch_up.moveTo(k_to_x(i), k_to_y(v))
                        started_up = True
                    else:
                        path_ch_up.lineTo(k_to_x(i), k_to_y(v))
                else:
                    break

            # 2.2 中轨独立绘制
            started_mid = False
            for i in range(local_chan_start, n):
                v = ch_mid[i] if i < len(ch_mid) else 0.0
                if min_cutoff <= v <= max_cutoff:
                    if not started_mid:
                        path_ch_mid.moveTo(k_to_x(i), k_to_y(v))
                        started_mid = True
                    else:
                        path_ch_mid.lineTo(k_to_x(i), k_to_y(v))
                else:
                    break

            # 2.3 下轨独立绘制
            started_dn = False
            for i in range(local_chan_start, n):
                v = ch_dn[i] if i < len(ch_dn) else 0.0
                if min_cutoff <= v <= max_cutoff:
                    if not started_dn:
                        path_ch_dn.moveTo(k_to_x(i), k_to_y(v))
                        started_dn = True
                    else:
                        path_ch_dn.lineTo(k_to_x(i), k_to_y(v))
                else:
                    break

            # 上下轨用通达信亮白色粗实线，中轨用白点划线
            painter.setPen(QPen(QColor("#FFFFFF"), 1.5, Qt.PenStyle.SolidLine))
            painter.drawPath(path_ch_up)
            painter.drawPath(path_ch_dn)
            painter.setPen(QPen(QColor("#C0C0D0"), 1.0, Qt.PenStyle.DashLine))
            painter.drawPath(path_ch_mid)
        elif len(b_up) > 1 and len(b_dn) > 1:
            path_up = QPainterPath()
            path_dn = QPainterPath()
            path_up.moveTo(k_to_x(0), k_to_y(b_up[0]))
            path_dn.moveTo(k_to_x(0), k_to_y(b_dn[0]))
            for i in range(1, n):
                if b_up[i] > 0: path_up.lineTo(k_to_x(i), k_to_y(b_up[i]))
                if b_dn[i] > 0: path_dn.lineTo(k_to_x(i), k_to_y(b_dn[i]))
            painter.setPen(QPen(QColor("#00ff88"), 1, Qt.PenStyle.DashLine))
            painter.drawPath(path_up)
            painter.setPen(QPen(QColor("#8888aa"), 1, Qt.PenStyle.DashLine))
            painter.drawPath(path_dn)

        # 3. 🌟 绘制通达信翻转线 (reversal_line)
        if len(rev_line) > 1:
            path_rev = QPainterPath()
            path_rev.moveTo(k_to_x(0), k_to_y(rev_line[0]))
            for i in range(1, n):
                if rev_line[i] > 0:
                    path_rev.lineTo(k_to_x(i), k_to_y(rev_line[i]))
            painter.setPen(QPen(QColor("#FFCC00"), 1.2, Qt.PenStyle.SolidLine))
            painter.drawPath(path_rev)

        # 4. 绘制 MA 均线 (MA5 金黄, MA20 紫红)
        if len(ma5) > 1:
            path_m5 = QPainterPath()
            path_m5.moveTo(k_to_x(0), k_to_y(ma5[0]))
            for i in range(1, n):
                if ma5[i] > 0: path_m5.lineTo(k_to_x(i), k_to_y(ma5[i]))
            painter.setPen(QPen(QColor("#ffd700"), 1))
            painter.drawPath(path_m5)

        if len(ma20) > 1:
            path_m20 = QPainterPath()
            path_m20.moveTo(k_to_x(0), k_to_y(ma20[0]))
            for i in range(1, n):
                if ma20[i] > 0: path_m20.lineTo(k_to_x(i), k_to_y(ma20[i]))
            painter.setPen(QPen(QColor("#ff00ff"), 1))
            painter.drawPath(path_m20)

        # 5. 🌟 绘制通达信上涨斜率支撑线 (KX DRAWLINE 斜向实体线)
        if ch_supp_p > 0:
            y_supp = k_to_y(ch_supp_p)

            supp_global_start = max(0, total_n - 1 - ch_supp_days)
            if supp_global_start <= end_i and 0 < ch_supp_days < total_n:
                supp_local_start = max(0, supp_global_start - start_i)
                p_start = ch_supp_p - ch_supp_slope * (total_n - 1 - (start_i + supp_local_start))
                x_s0 = k_to_x(supp_local_start)
                y_s0 = k_to_y(p_start)
                x_s1 = k_to_x(n - 1)
                y_s1 = y_supp
                painter.setPen(QPen(QColor("#FFD700"), 2.0, Qt.PenStyle.SolidLine))
                painter.drawLine(int(x_s0), int(y_s0), int(x_s1), int(y_s1))

        # 5.1 🌟 绘制通达信同款最近低点水平支撑虚线 (完全对齐 calc_trend_channel 向量化通道引擎输出)
        ch_lower_p = float(df_view['ch_anchor_low_price'].iloc[-1]) if 'ch_anchor_low_price' in df_view.columns and len(df_view) > 0 and pd.notna(df_view['ch_anchor_low_price'].iloc[-1]) else 0.0
        
        low_global_start = max(0, total_n - ch_bc2)
        if low_global_start <= end_i and ch_lower_p > 0:
            low_local_start = max(0, low_global_start - start_i)
            if 0 <= low_local_start < n:
                x_low_s0 = k_to_x(low_local_start)
                y_low_s0 = k_to_y(ch_lower_p)
                x_low_s1 = k_to_x(n - 1)

                # 黄色垂直引导虚线
                painter.setPen(QPen(QColor(255, 215, 0, 180), 1.2, Qt.PenStyle.DashLine))
                painter.drawLine(int(x_low_s0), int(margin_top + main_h), int(x_low_s0), int(margin_top))

                # 🌟 最近低点向右水平延伸支撑虚线 (青色虚线)
                painter.setPen(QPen(QColor(0, 255, 255, 200), 1.2, Qt.PenStyle.DashLine))
                painter.drawLine(int(x_low_s0), int(y_low_s0), int(x_low_s1), int(y_low_s0))

        # 提取神奇九转 (TD Sequential 9) 序列
        td_up_arr = df_view['td_sell_count'].values if 'td_sell_count' in df_view.columns else (
            df_view['td_up_label'].values if 'td_up_label' in df_view.columns else np.zeros(len(df_view))
        )
        td_dn_arr = df_view['td_buy_count'].values if 'td_buy_count' in df_view.columns else (
            df_view['td_dn_label'].values if 'td_dn_label' in df_view.columns else np.zeros(len(df_view))
        )
        if (len(td_up_arr) == 0 or np.all(td_up_arr == 0)) and len(closes) >= 5:
            td_up_arr = np.zeros(n, dtype=int)
            td_dn_arr = np.zeros(n, dtype=int)
            cur_u, cur_d = 0, 0
            for i_td in range(4, n):
                if closes[i_td] > closes[i_td - 4]:
                    cur_u = 1 if cur_u >= 9 else (cur_u + 1)
                    cur_d = 0
                    td_up_arr[i_td] = cur_u
                elif closes[i_td] < closes[i_td - 4]:
                    cur_d = 1 if cur_d >= 9 else (cur_d + 1)
                    cur_u = 0
                    td_dn_arr[i_td] = cur_d
                else:
                    cur_u, cur_d = 0, 0

        # 🌟 局部 10 根 K 棒窗口极值去重 (相邻 10 根 K 线内只在真正最高/最低极值点标注价格数字，彻底解决数字扎堆挤爆)
        show_top_price = np.zeros(n, dtype=bool)
        show_bot_price = np.zeros(n, dtype=bool)
        for i in range(n):
            if i < len(sig_top_arr) and sig_top_arr[i] == 1:
                w_s = max(0, i - 5)
                w_e = min(n, i + 6)
                cands = [highs[j] for j in range(w_s, w_e) if j < len(sig_top_arr) and sig_top_arr[j] == 1]
                if cands and highs[i] >= max(cands):
                    show_top_price[i] = True

            if i < len(sig_bot) and sig_bot[i] == 1:
                w_s = max(0, i - 5)
                w_e = min(n, i + 6)
                cands = [lows[j] for j in range(w_s, w_e) if j < len(sig_bot) and sig_bot[j] == 1]
                if cands and lows[i] <= min(cands):
                    show_bot_price[i] = True

        # 🌟 7.1 启动信号 (sig_launch) 与 逃顶信号 (sig_escape) 波段聚类精简 (去重合并，首尾统计，中间仅保留精致微图标)
        def _cluster_signals(sig_arr: np.ndarray, max_gap: int = 4) -> Dict[int, Dict[str, Any]]:
            sig_indices = [i for i in range(len(sig_arr)) if sig_arr[i] == 1]
            if not sig_indices:
                return {}
            clusters = []
            curr_cluster = [sig_indices[0]]
            for idx in sig_indices[1:]:
                if idx - curr_cluster[-1] <= max_gap:
                    curr_cluster.append(idx)
                else:
                    clusters.append(curr_cluster)
                    curr_cluster = [idx]
            if curr_cluster:
                clusters.append(curr_cluster)

            draw_plan = {}
            for cl in clusters:
                cnt = len(cl)
                if cnt == 1:
                    draw_plan[cl[0]] = {'role': 'single', 'count': 1, 'seq': 1}
                else:
                    for seq, idx in enumerate(cl, 1):
                        if seq == 1:
                            draw_plan[idx] = {'role': 'first', 'count': cnt, 'seq': 1}
                        elif seq == cnt:
                            draw_plan[idx] = {'role': 'last', 'count': cnt, 'seq': cnt}
                        else:
                            draw_plan[idx] = {'role': 'middle', 'count': cnt, 'seq': seq}
            return draw_plan

        launch_plan = _cluster_signals(sig_launch_arr, max_gap=4)
        escape_plan = _cluster_signals(sig_escape_arr, max_gap=4)

        # 6. 绘制 K 线蜡烛实体、影线、神奇九转与拐点信号
        for i in range(n):
            x_c = k_to_x(i)
            y_op = k_to_y(opens[i])
            y_cl = k_to_y(closes[i])
            y_hi = k_to_y(highs[i])
            y_lo = k_to_y(lows[i])

            is_up = closes[i] >= opens[i]
            color = QColor("#ff4444") if is_up else QColor("#00e5ff")

            painter.setPen(QPen(color, 1))
            painter.drawLine(int(x_c), int(y_hi), int(x_c), int(y_lo))

            y_top_c = min(y_op, y_cl)
            body_h = max(1.5, abs(y_cl - y_op))
            painter.setBrush(QBrush(color if is_up else QColor("#0c0d14")))
            painter.drawRect(int(x_c - bar_w / 2), int(y_top_c), int(bar_w), int(body_h))

            # 副图成交量柱
            vh = (vols[i] / max_v) * vol_h
            vy = vol_top + vol_h - vh
            painter.setBrush(QBrush(color))
            painter.drawRect(int(x_c - bar_w / 2), int(vy), int(bar_w), int(vh))

            # 🌟 6.1 绘制通达信神奇九转 (TD Sequential 9) 序列 (过滤 <4 碎片杂音，仅在成熟序列与变盘点显示)
            # 上涨九转 (卖出结构)：上方绘制粉色 4~8 与醒目红底 9 胶囊 (连续 9 转仅首个画胶囊)
            if i < len(td_up_arr) and td_up_arr[i] >= 4:
                num = int(td_up_arr[i])
                is_first_9 = (num == 9) and (i == 0 or td_up_arr[i-1] != 9)
                if is_first_9:
                    painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FF0055"), 1))
                    painter.setBrush(QBrush(QColor("#450018")))
                    painter.drawRoundedRect(int(x_c - 8), int(y_hi - 22), 16, 14, 3, 3)
                    painter.setPen(QPen(QColor("#FFFFFF")))
                    painter.drawText(int(x_c - 4), int(y_hi - 11), "9")
                else:
                    painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FF0055") if num == 9 else QColor("#FF77AA")))
                    painter.drawText(int(x_c - 3), int(y_hi - 9), str(num))

            # 下跌九转 (买入结构)：下方绘制薄荷绿 4~8 与醒目青绿底 9 胶囊 (连续 9 转仅首个画胶囊)
            if i < len(td_dn_arr) and td_dn_arr[i] >= 4:
                num = int(td_dn_arr[i])
                is_first_9 = (num == 9) and (i == 0 or td_dn_arr[i-1] != 9)
                if is_first_9:
                    painter.setFont(QFont("Arial", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#00E5FF"), 1))
                    painter.setBrush(QBrush(QColor("#003325")))
                    painter.drawRoundedRect(int(x_c - 8), int(y_lo + 8), 16, 14, 3, 3)
                    painter.setPen(QPen(QColor("#FFFFFF")))
                    painter.drawText(int(x_c - 4), int(y_lo + 19), "9")
                else:
                    painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#00E5FF") if num == 9 else QColor("#00FF88")))
                    painter.drawText(int(x_c - 3), int(y_lo + 17), str(num))

            # 🌟 7. 绘制通达信见底/见顶局部 10 根 K 棒极值价格 (移除密集杂乱的红点/青点，仅保留真正波段极值价格)
            if i < len(sig_bot) and sig_bot[i] == 1 and show_bot_price[i]:
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.setPen(QPen(QColor("#00FFFF")))
                y_offset = (y_lo + 26) if (i < len(td_dn_arr) and td_dn_arr[i] >= 4) else (y_lo + 16)
                painter.drawText(int(x_c - 16), int(y_offset), f"{lows[i]:.2f}")

            if i < len(sig_top_arr) and sig_top_arr[i] == 1 and show_top_price[i]:
                painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                painter.setPen(QPen(QColor("#FF7777")))
                y_offset = (y_hi - 24) if (i < len(td_up_arr) and td_up_arr[i] >= 4) else (y_hi - 10)
                painter.drawText(int(x_c - 16), int(y_offset), f"{highs[i]:.2f}")

            # 🌟 7.2 启动信号 (sig_launch)：首尾统计，中间仅保留精致微图标
            if i in launch_plan:
                info = launch_plan[i]
                role = info['role']
                total_c = info['count']
                seq_c = info['seq']
                if role == 'single':
                    lbl_la = "🚀启动"
                    painter.setFont(QFont("Microsoft YaHei", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FF007F"), 1))
                    painter.setBrush(QBrush(QColor("#2A0015")))
                    painter.drawRoundedRect(int(x_c - 18), int(y_lo + 14), 36, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FF66AA")))
                    painter.drawText(int(x_c - 16), int(y_lo + 25), lbl_la)
                elif role == 'first':
                    lbl_la = f"🚀启动×{total_c}"
                    tw = 44 if total_c < 10 else 48
                    painter.setFont(QFont("Microsoft YaHei", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FF007F"), 1))
                    painter.setBrush(QBrush(QColor("#35001C")))
                    painter.drawRoundedRect(int(x_c - tw / 2), int(y_lo + 14), tw, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FF66AA")))
                    painter.drawText(int(x_c - tw / 2 + 2), int(y_lo + 25), lbl_la)
                elif role == 'last':
                    lbl_la = f"🚀{seq_c}/{total_c}"
                    tw = 32
                    painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FF007F"), 1))
                    painter.setBrush(QBrush(QColor("#2A0015")))
                    painter.drawRoundedRect(int(x_c - tw / 2), int(y_lo + 14), tw, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FF88CC")))
                    painter.drawText(int(x_c - tw / 2 + 3), int(y_lo + 25), lbl_la)
                else:
                    # 中间节点：取消大方框文字，仅保留粉紫色精巧微箭头，零遮挡
                    painter.setPen(QPen(QColor("#FF007F"), 1))
                    painter.setBrush(QBrush(QColor("#FF3399")))
                    tri = QPolygon([
                        QPoint(int(x_c), int(y_lo + 12)),
                        QPoint(int(x_c - 3), int(y_lo + 17)),
                        QPoint(int(x_c + 3), int(y_lo + 17))
                    ])
                    painter.drawPolygon(tri)

            # 🌟 7.3 逃顶信号 (sig_escape)：首尾统计，中间仅保留精致微图标
            if i in escape_plan:
                info = escape_plan[i]
                role = info['role']
                total_c = info['count']
                seq_c = info['seq']
                if role == 'single':
                    lbl_es = "⚠️逃顶"
                    painter.setFont(QFont("Microsoft YaHei", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FFAA00"), 1))
                    painter.setBrush(QBrush(QColor("#2A1E00")))
                    painter.drawRoundedRect(int(x_c - 18), int(y_hi - 24), 36, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FFDD66")))
                    painter.drawText(int(x_c - 16), int(y_hi - 13), lbl_es)
                elif role == 'first':
                    lbl_es = f"⚠️逃顶×{total_c}"
                    tw = 44 if total_c < 10 else 48
                    painter.setFont(QFont("Microsoft YaHei", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FFAA00"), 1))
                    painter.setBrush(QBrush(QColor("#352400")))
                    painter.drawRoundedRect(int(x_c - tw / 2), int(y_hi - 24), tw, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FFDD66")))
                    painter.drawText(int(x_c - tw / 2 + 2), int(y_hi - 13), lbl_es)
                elif role == 'last':
                    lbl_es = f"⚠️{seq_c}/{total_c}"
                    tw = 32
                    painter.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#FFAA00"), 1))
                    painter.setBrush(QBrush(QColor("#2A1E00")))
                    painter.drawRoundedRect(int(x_c - tw / 2), int(y_hi - 24), tw, 14, 2, 2)
                    painter.setPen(QPen(QColor("#FFE088")))
                    painter.drawText(int(x_c - tw / 2 + 3), int(y_hi - 13), lbl_es)
                else:
                    # 中间节点：取消大方框文字，仅保留金黄色精巧微倒三角，零遮挡
                    painter.setPen(QPen(QColor("#FFAA00"), 1))
                    painter.setBrush(QBrush(QColor("#FFCC00")))
                    tri = QPolygon([
                        QPoint(int(x_c), int(y_hi - 10)),
                        QPoint(int(x_c - 3), int(y_hi - 15)),
                        QPoint(int(x_c + 3), int(y_hi - 15))
                    ])
                    painter.drawPolygon(tri)

        # 8. 🌟 统一收集右侧 Y 轴基准线与标签 (黄金分割、支撑、反转、开盘、止盈目标)
        # 完全移到右侧边栏刻度区，彻底消除主图内部悬浮框遮挡蜡烛图和通道线的问题
        right_axis_labels = []

        # 8.1 黄金分割阶梯线
        if fib_range > 1e-4:
            fib_levels = [
                (full_low + fib_range * 0.809, "80.9%", QColor("#FF7700")),  # 高阻位
                (full_low + fib_range * 0.618, "61.8%", QColor("#FFD700")),  # 黄金阻力
                (full_low + fib_range * 0.500, "50.0%", QColor("#00E5FF")),  # 中枢位
                (full_low + fib_range * 0.382, "38.2%", QColor("#FFD700")),  # 黄金支撑
                (full_low + fib_range * 0.191, "19.1%", QColor("#00FF88")),  # 强撑位
            ]
            fib_start_x = int(margin_left + chart_w * 0.45)
            fib_end_x = int(margin_left + chart_w)
            for f_val, f_lbl, f_col in fib_levels:
                if min_p <= f_val <= max_p:
                    y_fib = k_to_y(f_val)
                    painter.setPen(QPen(f_col, 1, Qt.PenStyle.DotLine))
                    painter.drawLine(fib_start_x, int(y_fib), fib_end_x, int(y_fib))
                    right_axis_labels.append((y_fib, f"{f_val:.1f} {f_lbl}", f_col, QFont("Consolas", 7)))

        # 8.2 通达信通道三轨右侧 Y 轴标签 (上轨、中轨、下轨)
        ch_up_last = float(ch_up[-1]) if len(ch_up) > 0 else 0.0
        ch_mid_last = float(ch_mid[-1]) if len(ch_mid) > 0 else 0.0
        ch_dn_last = float(ch_dn[-1]) if len(ch_dn) > 0 else 0.0

        if ch_up_last > 0 and min_p <= ch_up_last <= max_p:
            right_axis_labels.append((k_to_y(ch_up_last), f"上轨:{ch_up_last:.2f}", QColor("#FFFFFF"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))
        if ch_mid_last > 0 and min_p <= ch_mid_last <= max_p:
            right_axis_labels.append((k_to_y(ch_mid_last), f"中轨:{ch_mid_last:.2f}", QColor("#B0B0C0"), QFont("Microsoft YaHei", 7)))
        if ch_dn_last > 0 and min_p <= ch_dn_last <= max_p:
            right_axis_labels.append((k_to_y(ch_dn_last), f"下轨:{ch_dn_last:.2f}", QColor("#FFFFFF"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))

        # 8.3 上涨支撑线 (ch_supp_p) 右侧标签与短水平虚线
        if ch_supp_p > 0 and min_p <= ch_supp_p <= max_p:
            y_supp_line = k_to_y(ch_supp_p)
            painter.setPen(QPen(QColor("#FF4444"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(margin_left + chart_w * 0.50), int(y_supp_line), int(margin_left + chart_w), int(y_supp_line))
            right_axis_labels.append((y_supp_line, f"支撑:{ch_supp_p:.2f}", QColor("#FF4444"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))

        # 8.3 翻转线 (rev_last) 右侧标签与短水平虚线
        if rev_last > 0 and min_p <= rev_last <= max_p:
            y_rev_line = k_to_y(rev_last)
            painter.setPen(QPen(QColor("#00FF88"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(margin_left + chart_w * 0.50), int(y_rev_line), int(margin_left + chart_w), int(y_rev_line))
            right_axis_labels.append((y_rev_line, f"反转:{rev_last:.2f}", QColor("#00FF88"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))

        # 8.4 开盘基准线 (self.open_price) 右侧标签
        if self.open_price > 0 and min_p <= self.open_price <= max_p:
            y_op_line = k_to_y(self.open_price)
            painter.setPen(QPen(QColor("#FF4444"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(margin_left + chart_w * 0.35), int(y_op_line), int(margin_left + chart_w), int(y_op_line))
            right_axis_labels.append((y_op_line, f"开盘:{self.open_price:.2f}", QColor("#FF4444"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))

        # 8.5 止盈目标线 (self.target_sell_min) 右侧标签
        if self.target_sell_min > 0 and min_p <= self.target_sell_min <= max_p:
            y_tmin_line = k_to_y(self.target_sell_min)
            painter.setPen(QPen(QColor("#00FF88"), 1, Qt.PenStyle.DashDotLine))
            painter.drawLine(int(margin_left + chart_w * 0.35), int(y_tmin_line), int(margin_left + chart_w), int(y_tmin_line))
            right_axis_labels.append((y_tmin_line, f"目标:{self.target_sell_min:.2f}", QColor("#00FF88"), QFont("Microsoft YaHei", 7, QFont.Weight.Bold)))

        # 🌟 统一渲染右侧 Y 轴标签（带垂直防重叠智能微调）
        if right_axis_labels:
            right_axis_labels.sort(key=lambda item: item[0])
            adjusted_labels = []
            min_y_gap = 12.0
            last_drawn_y = -999.0
            for raw_y, text, col, font in right_axis_labels:
                target_y = max(raw_y, last_drawn_y + min_y_gap)
                target_y = max(margin_top + 8, min(margin_top + main_h - 2, target_y))
                adjusted_labels.append((target_y, text, col, font))
                last_drawn_y = target_y

            for adj_y, text, col, font in adjusted_labels:
                painter.setFont(font)
                painter.setPen(QPen(col))
                painter.drawText(int(margin_left + chart_w + 3), int(adj_y + 3), text)

        # 9. 🌟 绘制 SBC 买卖信号 (自适应智能避让 K 线实体 + 半透明毛玻璃 + 高对比度清晰设计)
        if self.signals:
            times_k = [str(t).strip() for t in df_view.index]
            last_k_time = times_k[-1] if times_k else ""
            today_str = last_k_time[:10] if len(last_k_time) >= 10 and "-" in last_k_time[:10] else ""

            k_hhmm_list = []
            today_k_indices = []
            for i, tk in enumerate(times_k):
                tk_sub = tk.split()[-1] if " " in tk else tk
                tk_hm = tk_sub[:5] if len(tk_sub) >= 5 else tk_sub
                k_hhmm_list.append(tk_hm)
                if not today_str or tk.startswith(today_str):
                    today_k_indices.append(i)

            if not today_k_indices:
                today_k_indices = list(range(n))

            sig_drawn_slots = {}

            for sig_idx, sig in enumerate(self.signals):
                sig_p = float(sig.get("price", 0.0) if isinstance(sig, dict) else getattr(sig, "price", 0.0))
                if sig_p <= 0:
                    continue

                sig_t_raw = str(sig.get("timestamp", sig.get("time", "")) if isinstance(sig, dict) else getattr(sig, "timestamp", getattr(sig, "time", ""))).strip()
                action_type = str(sig.get("action", sig.get("type", "sell")) if isinstance(sig, dict) else getattr(sig, "action", getattr(sig, "type", "sell"))).lower()
                is_buy = "buy" in action_type or "买" in action_type
                prefix = "🟢 买" if is_buy else "🔴 卖"
                border_color = QColor("#00ff88") if is_buy else QColor("#ff4d4f")
                bg_color = QColor(10, 32, 18, 185) if is_buy else QColor(36, 12, 16, 185) # 半透明毛玻璃
                fg_color = QColor("#ffffff") # 高对比度清晰白字
                dot_color = QColor("#00ff88") if is_buy else QColor("#ff4d4f")

                y_s = k_to_y(sig_p)

                sig_hm = sig_t_raw.split()[-1][:5] if " " in sig_t_raw else sig_t_raw[:5]
                sig_d = sig_t_raw[:10] if len(sig_t_raw) >= 10 else sig_t_raw

                idx_k = -1
                if self.period_mode in ["day", "week", "month"]:
                    for ki, tk in enumerate(times_k):
                        if str(tk).startswith(sig_d):
                            idx_k = ki
                            break
                    if idx_k < 0:
                        for ki, tk in enumerate(times_k):
                            if str(tk)[:10] >= sig_d:
                                idx_k = ki
                                break
                    if idx_k < 0 and today_k_indices:
                        idx_k = today_k_indices[-1]
                else:
                    for ki in today_k_indices:
                        if k_hhmm_list[ki] >= sig_hm:
                            idx_k = ki
                            break
                    if idx_k < 0 and today_k_indices:
                        idx_k = today_k_indices[-1]

                trade_id_val = sig.get("trade_id") if isinstance(sig, dict) else getattr(sig, "trade_id", None)
                is_selected_trade = (trade_id_val is not None and trade_id_val == self.selected_trade_id)
                if is_selected_trade:
                    border_color = QColor("#FFD700")
                    bg_color = QColor(48, 38, 10, 230)

                if 0 <= idx_k < n:
                    x_k = k_to_x(idx_k)
                    y_hi_k = k_to_y(highs[idx_k])
                    y_lo_k = k_to_y(lows[idx_k])

                    pnl_pct_v = sig.get("pnl_pct") if isinstance(sig, dict) else getattr(sig, "pnl_pct", None)
                    if not is_buy and pnl_pct_v is not None:
                        lbl_text = f"{prefix}:{sig_p:.2f} ({float(pnl_pct_v):+.1f}%)"
                    else:
                        lbl_text = f"{prefix}:{sig_p:.2f}"

                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    fm = painter.fontMetrics()
                    tw_k = fm.horizontalAdvance(lbl_text) + 10
                    th_k = fm.height() + 4

                    # 智能自适应放置在 K 棒上方或下方，避开蜡烛柱实体与影线
                    slot_cnt = sig_drawn_slots.get(idx_k, 0)
                    sig_drawn_slots[idx_k] = slot_cnt + 1

                    if is_buy:
                        target_y = y_lo_k + 8 + slot_cnt * (th_k + 4)
                        if target_y + th_k > margin_top + main_h - 4:
                            target_y = y_hi_k - th_k - 8 - slot_cnt * (th_k + 4)
                    else:
                        target_y = y_hi_k - th_k - 8 - slot_cnt * (th_k + 4)
                        if target_y < margin_top + 4:
                            target_y = y_lo_k + 8 + slot_cnt * (th_k + 4)

                    x_offset = (slot_cnt % 2) * 8
                    tag_kx = int(max(margin_left + 2, min(margin_left + chart_w - tw_k - 2, x_k - tw_k / 2 + x_offset)))
                    tag_ky = int(max(margin_top + 2, min(margin_top + main_h - th_k - 2, target_y)))

                    # 注册点击区域
                    tag_rect = QRect(tag_kx, tag_ky, tw_k, th_k)
                    self._signal_hit_boxes.append({
                        "rect": tag_rect,
                        "trade_id": trade_id_val,
                        "sig": sig,
                        "x": x_k,
                        "y": y_s,
                        "is_buy": is_buy
                    })

                    # 1. 绘制垂直贯穿虚线
                    painter.setPen(QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 90), 1, Qt.PenStyle.DotLine))
                    painter.drawLine(int(x_k), int(margin_top + main_h), int(x_k), int(margin_top))

                    # 2. 从标签框连接到实际成交价的精巧微引线
                    painter.setPen(QPen(QColor(border_color.red(), border_color.green(), border_color.blue(), 180), 1, Qt.PenStyle.SolidLine))
                    painter.drawLine(int(x_k), int(y_s), int(tag_kx + tw_k / 2), int(tag_ky + th_k if tag_ky < y_s else tag_ky))

                    # 3. 实际成交价处的精巧圆点
                    painter.setPen(QPen(QColor("#ffffff") if not is_selected_trade else QColor("#FFD700"), 1.2))
                    painter.setBrush(QBrush(dot_color))
                    painter.drawEllipse(int(x_k - 3), int(y_s - 3), 6, 6)

                    # 4. 半透明高对比度圆角胶囊背景
                    painter.setPen(QPen(border_color, 1.8 if is_selected_trade else 1.2))
                    painter.setBrush(QBrush(bg_color))
                    painter.drawRoundedRect(tag_kx, tag_ky, tw_k, th_k, 3, 3)

                    # 5. 高对比度白字
                    painter.setPen(QPen(fg_color))
                    painter.drawText(tag_kx + 5, tag_ky + th_k - 4, lbl_text)

            # 绘制当前选中的回测交易收益光束与详情卡片
            if self.selected_trade_id is not None:
                self._draw_selected_trade_linkage(painter, margin_left, margin_top, chart_w, main_h)

        # 11. 🌟 快捷键 R 自适应策略测算信号点与基准线绘制
        if getattr(self, 'auto_eval_enabled', True) and getattr(self, 'strategy_eval_result', None):
            res_strat = self.strategy_eval_result
            is_matched = res_strat.get("is_matched", False)
            strat_period = str(res_strat.get("period", self.period_mode)).upper()

            if is_matched:
                entry_p = float(res_strat.get("entry_price", 0.0))
                stop_p = float(res_strat.get("stop_loss", 0.0))
                tgt_p1 = float(res_strat.get("target_price_1", 0.0))
                score_v = res_strat.get("score", 0)

                # 突破 K 棒在可视切片中的 X 位置
                brk_idx_local = n - 1
                brk_raw = res_strat.get("breakout_bar_idx", -1)
                if brk_raw >= 0:
                    brk_idx_local = max(0, min(n - 1, brk_raw - start_i))

                x_brk = k_to_x(brk_idx_local)
                y_entry = k_to_y(entry_p) if (entry_p > 0 and min_p <= entry_p <= max_p) else k_to_y(closes[brk_idx_local])

                # 11.1 遍历绘制与通达信 100% 完全对齐的【明亮绿色垂直细虚线】与【| 逆势先锋】标记
                pioneer_list = res_strat.get("pioneer_sig_indices", [])
                if not pioneer_list and brk_raw >= 0:
                    pioneer_list = [brk_raw]

                for p_idx_raw in pioneer_list:
                    if p_idx_raw < 0:
                        continue
                    p_idx_local = p_idx_raw - start_i
                    if 0 <= p_idx_local < n:
                        x_p = k_to_x(p_idx_local)
                        # 通达信同款贯穿上下的绿色细虚线
                        painter.setPen(QPen(QColor("#00FF66"), 1.2, Qt.PenStyle.DashLine))
                        painter.drawLine(int(x_p), int(margin_top + main_h), int(x_p), int(margin_top))

                        # 通达信同款顶部【| 逆势先锋】绿色粗体文字 (避开左上角通道 HUD 卡片区域)
                        if x_p > margin_left + 450:
                            painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                            painter.setPen(QPen(QColor("#00FF66")))
                            painter.drawText(int(x_p + 3), int(margin_top + 14), "| 逆势先锋")

                        # 通达信同款 K 棒底部【★逆势先锋】红绿指示
                        y_k_low = k_to_y(lows[p_idx_local])
                        painter.drawText(int(x_p - 24), int(min(margin_top + main_h - 4, y_k_low + 16)), "★逆势先锋")

                # 11.2 介入信号胶囊卡片 (锚定在核心突破 K 棒)
                entry_tag = f"🚀 介入点:{entry_p:.2f} ({score_v}分)"
                painter.setFont(QFont("Microsoft YaHei", 8, QFont.Weight.Bold))
                fm_e = painter.fontMetrics()
                tw_e = fm_e.horizontalAdvance(entry_tag) + 12
                th_e = fm_e.height() + 6
                tag_x_e = int(max(margin_left, min(margin_left + chart_w - tw_e, x_brk - tw_e / 2)))
                tag_y_e = int(max(margin_top, min(margin_top + main_h - th_e, y_entry - th_e - 6)))

                painter.setPen(QPen(QColor("#00FF66"), 1.2))
                painter.setBrush(QBrush(QColor("#063018")))
                painter.drawRoundedRect(tag_x_e, tag_y_e, tw_e, th_e, 3, 3)
                painter.setPen(QPen(QColor("#FFFFFF")))
                painter.drawText(tag_x_e + 6, tag_y_e + th_e - 5, entry_tag)

                # 11.3 止损位水平虚线与标签
                if stop_p > 0 and min_p <= stop_p <= max_p:
                    y_stop = k_to_y(stop_p)
                    painter.setPen(QPen(QColor("#EF4444"), 1.2, Qt.PenStyle.DashDotLine))
                    painter.drawLine(int(x_brk), int(y_stop), int(margin_left + chart_w), int(y_stop))
                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#EF4444")))
                    painter.drawText(int(margin_left + chart_w - 95), int(y_stop - 3), f"🛡️止损:{stop_p:.2f}")

                # 11.4 目标位水平虚线与标签
                if tgt_p1 > 0 and min_p <= tgt_p1 <= max_p:
                    y_tgt1 = k_to_y(tgt_p1)
                    painter.setPen(QPen(QColor("#10B981"), 1.2, Qt.PenStyle.DashDotLine))
                    painter.drawLine(int(x_brk), int(y_tgt1), int(margin_left + chart_w), int(y_tgt1))
                    painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
                    painter.setPen(QPen(QColor("#10B981")))
                    painter.drawText(int(margin_left + chart_w - 95), int(y_tgt1 - 3), f"💎目标1:{tgt_p1:.2f}")

                # 11.5 K线主图左下侧极简高对比度轻量 HUD (彻底省略冗长模式行，位置调低靠左避开K线与坐标)
                self._draw_compact_strategy_hud(painter, margin_left, margin_top, chart_w, main_h, res_strat)
            else:
                # 未命中时的浮动提示条 (位置调低靠左)
                self._draw_compact_strategy_hud(painter, margin_left, margin_top, chart_w, main_h, res_strat)

        # 12. 🌟 顶层绘制通道标题与三轨大小高度 HUD 卡片 (置于最顶层，彻底杜绝任何被底层图元遮挡)
        info_header = f"📊 [{self.period_mode.upper()}] 通达信自动通道 (斜率:{ch_slope_deg:.1f}°)"
        if ch_up_last > 0 and ch_dn_last > 0:
            info_header += f" | 上轨:{ch_up_last:.2f} | 中轨:{ch_mid_last:.2f} | 下轨:{ch_dn_last:.2f}"
        if ch_supp_p > 0:
            info_header += f" | 支撑:{ch_supp_p:.2f}"
        if rev_last > 0:
            info_header += f" | 反转:{rev_last:.2f}"

        hud_box_h = 24
        if ch_up_last > 0 and ch_dn_last > 0:
            hud_box_h += 16
        if ch_supp_p > 0:
            hud_box_h += 16
        hud_box_w = max(420, min(chart_w - 20, int(len(info_header) * 8.0 + 20)))
        painter.setPen(QPen(QColor("#253248"), 1))
        painter.setBrush(QBrush(QColor(10, 15, 26, 220)))
        painter.drawRoundedRect(margin_left + 4, margin_top + 3, hud_box_w, hud_box_h, 3, 3)

        painter.setPen(QPen(QColor("#ffd700"), 1))
        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        painter.drawText(margin_left + 8, margin_top + 17, info_header)

        curr_y_offset = margin_top + 33
        # 第二行：通道大小高度 (绝对高度元, 相对宽幅%, 上半高, 下半高, 通道所处位置%)
        if ch_up_last > 0 and ch_dn_last > 0:
            ch_h_val = max(0.0, ch_up_last - ch_dn_last)
            ch_h_pct = (ch_h_val / max(1e-4, ch_mid_last)) * 100.0
            up_h = max(0.0, ch_up_last - ch_mid_last)
            dn_h = max(0.0, ch_mid_last - ch_dn_last)
            pos_desc = "超买突破" if ch_pos >= 90 else ("中上轨主升" if ch_pos >= 50 else ("中下轨企稳" if ch_pos >= 20 else "超跌触底"))
            painter.setPen(QPen(QColor("#00FFCC"), 1))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            chan_dim_info = f"📐 通道高度: Δ{ch_h_val:.2f}元 (宽幅:{ch_h_pct:.1f}%) | 上半高:{up_h:.2f}元 | 下半高:{dn_h:.2f}元 | 通道位置:{ch_pos:.1f}% ({pos_desc})"
            painter.drawText(margin_left + 8, curr_y_offset, chan_dim_info)
            curr_y_offset += 16

        # 第三行：上涨支撑线物理特征 (与第一行格式保持高度统一、简洁清晰)
        if ch_supp_p > 0:
            painter.setPen(QPen(QColor("#00E5FF"), 1))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
            supp_info = f"📈 上涨支撑 (斜率:{ch_supp_slope_deg:.1f}°) | 偏离:{ch_supp_pos:+.2f}% | 周期:{ch_supp_days}"
            painter.drawText(margin_left + 8, curr_y_offset, supp_info)


VALID_SBC_PERIODS = ["1m", "2d", "3d", "5d", "5m", "15m", "30m", "60m", "day", "week", "month"]


class SBCIntradayChartDialog(QWidget):
    """
    SBC 实盘分时走势与关键阶梯基准图 彻底独立实时观察窗口 (100% 非模态、非置顶、自由层级覆盖与多屏拉伸)
    """
    _global_sbc_size: Optional[tuple] = None
    _global_sbc_geo: Optional[dict] = None
    _global_auto_eval: bool = True  # 💡 全局维护自动测算状态开关

    def __init__(self, parent=None, code: str = "688826", engine: Optional[IntradayStrategyEngine] = None, initial_period_mode: Optional[str] = None):
        # 💡 保存主工作台引用用于边缘磁吸对齐，但向 Qt 构造函数传递 None
        # 彻底切断 Windows 属主窗口层级约束，使其表现为 100% 独立的桌面顶级 Window，绝不上浮置顶或遮挡主窗口！
        self.main_workbench = parent.window() if parent else None
        super().__init__(None)

        self.code = str(code).zfill(6)
        self.engine = engine if engine else IntradayStrategyEngine.get_instance()
        self._initial_period_mode = initial_period_mode
        self.auto_eval_enabled: bool = SBCIntradayChartDialog._global_auto_eval

        # 设置为彻底独立的顶层 Window (非模态，不置顶，不妨碍用户与其他窗口重叠与切换)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle(f"📈 【{self.code} {resolve_stock_name(self.code)}】SBC 实盘分时走势与关键阶梯基准图")
        self.setMinimumSize(320, 180) # 💡 极度紧凑的最小窗口尺寸保护
        self.setStyleSheet("background-color: #101018; color: #ffffff;")
        self._unmaximized_size = (680, 420)  # 💡 维护未最大化前的真实标准尺寸，绝不被最大化污染

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 1. 顶部工具栏 (超紧凑精致微型布局 + 周期切换按钮组)
        tb_layout = QHBoxLayout()
        tb_layout.setContentsMargins(2, 2, 2, 2)
        tb_layout.setSpacing(3)

        self.lbl_title = QLabel(f"📊 {self.code} {resolve_stock_name(self.code)}")
        self.lbl_title.setStyleSheet("font-size: 9pt; font-weight: bold; color: #00ff88;")

        # 周期切换按钮组: [1日分时] [2日分时] [3日分时] [5日分时] | [5分K] [30分K] [60分K] [日K] [周K] [月K]
        self._current_period_mode = "1m"
        self.btn_group_period = QButtonGroup(self)
        periods = [
            ("1日分时", "1m"),
            ("2日分时", "2d"),
            ("3日分时", "3d"),
            ("5日分时", "5d"),
            ("5分K", "5m"),
            ("30分K", "30m"),
            ("60分K", "60m"),
            ("日K", "day"),
            ("周K", "week"),
            ("月K", "month")
        ]

        tb_layout.addWidget(self.lbl_title)

        for text, mode in periods:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("period_mode", mode)
            if mode == "1m":
                btn.setChecked(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #141420; color: #8888aa; border: 1px solid #2a2a3c;
                    border-radius: 3px; padding: 2px 5px; font-size: 8pt; font-weight: bold;
                }
                QPushButton:checked {
                    background-color: #1e3a2e; color: #00ff88; border: 1px solid #00ff88;
                }
                QPushButton:hover {
                    color: #ffffff; border: 1px solid #38bdf8;
                }
                QPushButton:focus {
                    border: 1px solid #00ff88; background-color: #162c22; outline: none;
                }
            """)
            btn.clicked.connect(self._on_period_btn_clicked)
            self.btn_group_period.addButton(btn)
            tb_layout.addWidget(btn)

        btn_rearrange = QPushButton("🪟 重排 (Q)")
        btn_rearrange.setStyleSheet("background-color: #1a2e22; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;")
        btn_rearrange.setToolTip("快捷键: Q 键，自动将所有已打开的 SBC 分时走势窗口在当前屏幕网格平铺重排")
        btn_rearrange.clicked.connect(self._on_rearrange_windows_clicked)

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setStyleSheet("background-color: #1e2638; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;")
        btn_refresh.clicked.connect(self.reload_chart)

        btn_clear_cache = QPushButton("🧹 清缓存")
        btn_clear_cache.setStyleSheet("background-color: #3b1419; color: #ff6666; font-weight: bold; border: 1px solid #ff6666; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;")
        btn_clear_cache.setToolTip("强力清除当前标的的内存与磁盘错误缓存")
        btn_clear_cache.clicked.connect(self._on_clear_cache_clicked)

        self.btn_toggle_log = QPushButton("📋 日志")
        self.btn_toggle_log.setStyleSheet("background-color: #1e2638; color: #ffd700; font-weight: bold; border: 1px solid #ffd700; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;")
        self.btn_toggle_log.clicked.connect(self._toggle_log_panel)

        btn_linkage = QPushButton("⚡ 联动")
        btn_linkage.setStyleSheet("background-color: #2a1f10; color: #ffaa44; font-weight: bold; border: 1px solid #ffaa44; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;")
        btn_linkage.setToolTip("调用 ATS 主系统联动功能联动当前标的")
        def _on_send_linkage():
            c_digits = "".join(filter(str.isdigit, str(self.code))).zfill(6)
            st_name = resolve_stock_name(c_digits)
            # 1. 优先调用 main_workbench 上的 link_stock
            main_win = getattr(self, "main_workbench", None)
            if main_win and hasattr(main_win, "link_stock") and callable(getattr(main_win, "link_stock")):
                main_win.link_stock(c_digits, st_name)
                return
            # 2. 遍历全局 topLevelWidgets 查找具有 link_stock 的 ATS 主工作台
            from PyQt6.QtWidgets import QApplication
            for w in QApplication.topLevelWidgets():
                if hasattr(w, "link_stock") and callable(getattr(w, "link_stock")):
                    w.link_stock(c_digits, st_name)
                    return
            # 3. 备用：向本地联动服务推送
            try:
                from linkage_service import get_link_manager
                get_link_manager().push(c_digits, flags={'tdx': True, 'ths': True, 'dfcf': False}, auto=False)
            except Exception:
                pass
        btn_linkage.clicked.connect(_on_send_linkage)

        self.btn_eval_r = QPushButton("⚡ 测算 (开)")
        self.btn_eval_r.clicked.connect(lambda: self._on_eval_r_clicked(toggle=True))
        self._update_eval_btn_style()

        self.btn_cycle_trade = QPushButton("💰 点击收益")
        self.btn_cycle_trade.setStyleSheet("background-color: #1a233a; color: #ffd700; font-weight: bold; border: 1px solid #ffd700; border-radius: 3px; padding: 2px 8px; font-size: 8.5pt;")
        self.btn_cycle_trade.setToolTip("快捷键: Space 或 [ / ] 键，依次轮巡高亮回测买卖交易对并展示点击收益详情")
        self.btn_cycle_trade.clicked.connect(lambda: self.canvas.cycle_selected_trade(1))

        tb_layout.addStretch()
        tb_layout.addWidget(self.btn_eval_r)
        tb_layout.addWidget(self.btn_cycle_trade)
        tb_layout.addWidget(btn_linkage)
        tb_layout.addWidget(btn_rearrange)
        tb_layout.addWidget(btn_refresh)
        tb_layout.addWidget(btn_clear_cache)
        tb_layout.addWidget(self.btn_toggle_log)
        layout.addLayout(tb_layout)

        # 2. 实盘走势图画布
        self.canvas = SBCChartCanvas(self)
        self.canvas.code = self.code
        self.custom_trades_df = None
        self.custom_signals = None
        self.custom_kline_df = None
        layout.addWidget(self.canvas, 1)

        # 3. 折叠式行情数据与 TDX 通信日志区域
        self.log_box = QGroupBox("📋 实时行情获取与数据健康调试日志")
        self.log_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 4px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        log_box_lay = QVBoxLayout(self.log_box)
        log_box_lay.setContentsMargins(4, 4, 4, 4)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #08080c; color: #00ff88; font-family: 'Consolas', 'Segoe UI', 'Microsoft YaHei', sans-serif; font-size: 8.5pt;")
        self.txt_log.setMaximumHeight(120)
        log_box_lay.addWidget(self.txt_log)

        layout.addWidget(self.log_box)
        self.log_box.setVisible(False)

        # 4. 底部提示
        self.lbl_info = QLabel("💡 提示: 独立窗口支持【主窗口智能磁吸吸附】与脱离自由全屏。青蓝线为分时现价，黄虚线为 VWAP 均价，红虚线为开盘价，橙虚线为最高价，绿虚线为止盈目标。")
        self.lbl_info.setStyleSheet("color: #888899; font-size: 8.5pt;")
        self.lbl_info.setWordWrap(True)
        layout.addWidget(self.lbl_info)

        # 5. 30 分钟定时物理落盘与退出刷盘策略 (交易时段 30 分钟落盘一次，关闭窗口落盘；非交易时段只落盘一次)
        self._has_saved_post_market = False
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(30 * 60 * 1000) # 30 分钟物理落盘一次
        self._save_timer.timeout.connect(self._do_save_sbc_geometry)
        self._save_timer.start()

        # 6. 实盘交易期 2 秒级高频自动刷新与动态绘制定时器
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(2000)
        self.poll_timer.timeout.connect(self._on_poll_timer_tick)
        self.poll_timer.start()

        # 7. 磁吸贴边、自动隐藏与滑出动画系统 (与 ATS 加速龙头监视器完全统一)
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

        # 7.1 🪟 窗口尺寸与位置自动防抖持久化定时器 (350ms 用户停止拉伸/拖拽后自动原子落盘)
        self._geo_save_timer = QTimer(self)
        self._geo_save_timer.setSingleShot(True)
        self._geo_save_timer.setInterval(350)
        self._geo_save_timer.timeout.connect(self._do_save_sbc_geometry)

        # 8. 从 QSettings 与 config/intraday_ui_layout.json 强力物理恢复尺寸与屏显坐标
        self._restore_sbc_geometry()
        self.reload_chart()
        bind_top_shortcut(self, self._toggle_stay_on_top)

    def _on_poll_timer_tick(self):
        """定时器心跳周期检查与刷新：窗口隐藏或非交易期自动抑制"""
        if not self.isVisible():
            if hasattr(self, 'poll_timer') and self.poll_timer and self.poll_timer.isActive():
                self.poll_timer.stop()
            return
        self.reload_chart(is_timer_tick=True)

    def _get_max_allowed_sbc_size(self) -> Tuple[int, int]:
        """获取 SBC 窗口最大允许尺寸规格 (不得超过屏幕可用宽高的 2/3)"""
        try:
            screen = self.screen() or QApplication.primaryScreen()
            if screen:
                ag = screen.availableGeometry()
                max_w = max(400, int(ag.width() * 2 / 3))
                max_h = max(250, int(ag.height() * 2 / 3))
                return max_w, max_h
        except Exception:
            pass
        return 1280, 720

    def _get_effective_normal_geometry(self) -> Optional[dict]:
        """获取有效的正常窗口尺寸与坐标 (最大化状态下严格提取恢复尺寸 _unmaximized_size，绝不记忆最大化全屏或2/3截断尺寸)"""
        if self.isMinimized() or getattr(self, "_in_snap_action", False):
            return None

        if self.isMaximized() or self.isFullScreen():
            # 💡 最大化或全屏状态下，严格提取未最大化前的真实尺寸 _unmaximized_size，绝不使用全屏或 2/3 截断尺寸！
            uw, uh = 680, 420
            if hasattr(self, "_unmaximized_size") and isinstance(self._unmaximized_size, (tuple, list)):
                uw, uh = self._unmaximized_size
            elif SBCIntradayChartDialog._global_sbc_size:
                gw, gh = SBCIntradayChartDialog._global_sbc_size
                if gw < 1000 and gh < 650:
                    uw, uh = gw, gh
            
            # 位置提取 normalGeometry 或 100, 100
            nx, ny = 100, 100
            try:
                ng = self.normalGeometry()
                if ng and ng.isValid() and ng.width() > 0:
                    nx, ny = ng.x(), ng.y()
            except Exception:
                pass
            return {
                "x": nx,
                "y": ny,
                "width": max(320, min(uw, 900)),
                "height": max(180, min(uh, 600))
            }

        elif getattr(self, 'is_hidden_state', False) and getattr(self, 'normal_geometry', None):
            geo = self.normal_geometry
        else:
            geo = self.geometry()

        if not geo or geo.width() < 200 or geo.height() < 100:
            return None

        max_w, max_h = self._get_max_allowed_sbc_size()
        w = max(320, min(geo.width(), max_w))
        h = max(180, min(geo.height(), max_h))

        return {
            "x": geo.x(),
            "y": geo.y(),
            "width": w,
            "height": h
        }

    def _save_sbc_geometry(self):
        """【💾 内存缓存与防抖写盘】拖拽/缩放仅更新内存中的 Geometry 字典并触发防抖写盘"""
        # [CRITICAL] 最大化、全屏、最小化状态下绝对严禁覆盖保存 normal geometry！
        if self.isMaximized() or self.isFullScreen() or self.isMinimized():
            return
        geo_dict = self._get_effective_normal_geometry()
        if not geo_dict:
            return

        self._memory_geo_dict = geo_dict
        if geo_dict["width"] < 1000 and geo_dict["height"] < 650:
            SBCIntradayChartDialog._global_sbc_size = (geo_dict["width"], geo_dict["height"])
            self._unmaximized_size = (geo_dict["width"], geo_dict["height"])
        SBCIntradayChartDialog._global_sbc_geo = dict(self._memory_geo_dict)

        if hasattr(self, '_geo_save_timer'):
            self._geo_save_timer.start(350)

    def set_period_mode(self, mode: str, reload: bool = True, save: bool = True):
        """【📈 设定并切换 SBC 图表看盘周期】
        
        Args:
            mode: 周期模式 ('1m' | '2d' | '3d' | '5m' | '15m' | '30m' | '60m' | 'day' | 'week' | 'month')
            reload: 是否立即刷新重载走势图 (默认 True)
            save: 是否触发防抖持久化 (默认 True)
        """
        if not isinstance(mode, str):
            mode = "1m"
        mode_clean = mode.strip().lower()
        if mode_clean not in VALID_SBC_PERIODS:
            mode_clean = "1m"

        self._current_period_mode = mode_clean

        # 同步更新顶部按钮组的 checked 高亮状态并使当前按钮获得焦点
        if hasattr(self, 'btn_group_period') and self.btn_group_period:
            for btn in self.btn_group_period.buttons():
                btn_mode = (btn.property("period_mode") or "").strip().lower()
                is_match = (btn_mode == mode_clean)
                btn.setChecked(is_match)
                if is_match:
                    btn.setFocus()

        if reload:
            self.reload_chart()

        if save:
            self._save_sbc_geometry()

    def _do_save_sbc_geometry(self):
        """
        【💾 物理写盘】原子持久化窗口尺寸大小、屏显坐标与看盘周期到 JSON 与 QSettings (支持任意时段实时配置更新)
        """
        geo_dict = getattr(self, "_memory_geo_dict", None) or self._get_effective_normal_geometry()
        if not geo_dict or geo_dict.get("width", 0) < 200 or geo_dict.get("height", 0) < 100:
            return

        try:
            cur_period = getattr(self, "_current_period_mode", "1m")

            # 1. 写入 QSettings
            settings = QSettings("pyQuant3", "IntradayWorkbench")
            settings.setValue("sbc_window_geometry", geo_dict)
            settings.setValue("sbc_window_size", {"width": geo_dict["width"], "height": geo_dict["height"]})
            settings.setValue(f"sbc_period_{self.code}", cur_period)
            settings.setValue("sbc_period_latest", cur_period)
            settings.setValue("sbc_auto_eval_enabled", bool(getattr(self, "auto_eval_enabled", True)))

            # 2. 原子写入 JSON 配置文件
            cfg_path = _get_sbc_layout_cfg_path()
            data = {}
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}

            data["sbc_window_geometry"] = geo_dict
            data["sbc_window_size"] = {"width": geo_dict["width"], "height": geo_dict["height"]}
            data["sbc_auto_eval_enabled"] = bool(getattr(self, "auto_eval_enabled", True))
            if "sbc_geometries" not in data:
                data["sbc_geometries"] = {}
            data["sbc_geometries"]["latest"] = geo_dict
            data["sbc_geometries"][self.code] = geo_dict

            if "sbc_period_modes" not in data:
                data["sbc_period_modes"] = {}
            data["sbc_period_modes"]["latest"] = cur_period
            data["sbc_period_modes"][self.code] = cur_period

            # 同步更新 sbc_open_windows 中当前个股条目的尺寸、坐标与选择的周期
            if "sbc_open_windows" in data and isinstance(data["sbc_open_windows"], list):
                for item in data["sbc_open_windows"]:
                    if item.get("code") == self.code:
                        item["width"] = geo_dict["width"]
                        item["height"] = geo_dict["height"]
                        item["x"] = geo_dict["x"]
                        item["y"] = geo_dict["y"]
                        item["period_mode"] = cur_period
                        break

            tmp_path = cfg_path + f".tmp_{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                if os.path.exists(cfg_path):
                    os.replace(tmp_path, cfg_path)
                else:
                    os.rename(tmp_path, cfg_path)
            except Exception:
                shutil.move(tmp_path, cfg_path)

        except Exception as e:
            logger.debug(f"保存 SBC 窗口布局与周期异常: {e}")

    def _restore_sbc_geometry(self):
        """【💾 物理恢复】从内存/JSON/QSettings 还原 SBC 全局统一窗口尺寸、坐标、看盘周期与自动测算状态 (含越界与2/3屏幕规格保护)"""
        try:
            target_w, target_h = 680, 420
            x, y = 100, 100
            has_exact_pos = False
            restored_period = None
            restored_auto_eval = None

            # 0. 优先从类内存变量读取最新尺寸与测算状态
            if SBCIntradayChartDialog._global_sbc_size:
                gw, gh = SBCIntradayChartDialog._global_sbc_size
                if gw < 1000 and gh < 650:
                    target_w, target_h = gw, gh
            restored_auto_eval = SBCIntradayChartDialog._global_auto_eval

            # 1. 优先读取 JSON 配置文件
            cfg_path = _get_sbc_layout_cfg_path()
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    if "sbc_auto_eval_enabled" in data:
                        restored_auto_eval = bool(data["sbc_auto_eval_enabled"])

                    if "sbc_window_size" in data and isinstance(data["sbc_window_size"], dict):
                        sz = data["sbc_window_size"]
                        sw = int(sz.get("width", target_w))
                        sh = int(sz.get("height", target_h))
                        if sw < 1000 and sh < 650:
                            target_w, target_h = sw, sh

                    code_geo = data.get("sbc_geometries", {}).get(self.code)
                    latest_geo = data.get("sbc_window_geometry") or data.get("sbc_geometries", {}).get("latest")
                    
                    geo_dict = code_geo or latest_geo
                    if isinstance(geo_dict, dict) and "width" in geo_dict and "height" in geo_dict:
                        gw = int(geo_dict.get("width", target_w))
                        gh = int(geo_dict.get("height", target_h))
                        if gw < 1000 and gh < 650:
                            target_w, target_h = gw, gh
                        x = int(geo_dict.get("x", x))
                        y = int(geo_dict.get("y", y))
                        has_exact_pos = True

                    # 周期读取：优先个股历史周期 -> sbc_open_windows 记录 -> latest 周期
                    if "sbc_period_modes" in data and isinstance(data["sbc_period_modes"], dict):
                        restored_period = data["sbc_period_modes"].get(self.code) or data["sbc_period_modes"].get("latest")
                    if not restored_period and "sbc_open_windows" in data and isinstance(data["sbc_open_windows"], list):
                        for item in data["sbc_open_windows"]:
                            if item.get("code") == self.code:
                                restored_period = item.get("period_mode") or item.get("period")
                                break
                except Exception:
                    pass

            # 2. 回退读取 QSettings
            if target_w == 680 and target_h == 420:
                try:
                    settings = QSettings("pyQuant3", "IntradayWorkbench")
                    if restored_auto_eval is None:
                        val_s = settings.value("sbc_auto_eval_enabled")
                        if val_s is not None:
                            restored_auto_eval = str(val_s).lower() in ("true", "1")
                    sz = settings.value("sbc_window_size")
                    if isinstance(sz, dict):
                        target_w = int(sz.get("width", target_w))
                        target_h = int(sz.get("height", target_h))
                    geo = settings.value("sbc_window_geometry") or settings.value("sbc_geo_latest")
                    if isinstance(geo, dict) and "width" in geo and "height" in geo:
                        target_w = int(geo.get("width", target_w))
                        target_h = int(geo.get("height", target_h))
                        if not has_exact_pos:
                            x = int(geo.get("x", x))
                            y = int(geo.get("y", y))
                            has_exact_pos = True
                    if not restored_period:
                        restored_period = settings.value(f"sbc_period_{self.code}") or settings.value("sbc_period_latest")
                except Exception:
                    pass

            if restored_auto_eval is not None:
                self.auto_eval_enabled = bool(restored_auto_eval)
                SBCIntradayChartDialog._global_auto_eval = self.auto_eval_enabled
                self._update_eval_btn_style()

            # 3. 周期模式应用 (构造指定 > 历史恢复 > 默认 '1m')
            target_period = getattr(self, "_initial_period_mode", None) or restored_period or "1m"
            if target_period and str(target_period).lower() in VALID_SBC_PERIODS:
                self.set_period_mode(str(target_period).lower(), reload=False, save=False)

            # 4. 安全性防越界与屏幕规格 2/3 尺寸上限约束 (绝不超过屏幕 2/3 规格)
            max_w, max_h = self._get_max_allowed_sbc_size()
            target_w = max(320, min(target_w, max_w))
            target_h = max(180, min(target_h, max_h))

            from gui_utils import clamp_window_to_screens
            rx, ry = clamp_window_to_screens(x, y, target_w, target_h)

            self.setGeometry(rx, ry, target_w, target_h)
            SBCIntradayChartDialog._global_sbc_size = (target_w, target_h)
        except Exception as e:
            logger.debug(f"还原 SBC 窗口布局坐标异常: {e}")
            self.resize(680, 420)

    def showEvent(self, event):
        """窗口显示事件：自动将焦点赋予当前选中的周期按钮，便于直接键盘轮转与按键切周期"""
        super().showEvent(event)
        try:
            if hasattr(self, 'btn_group_period') and self.btn_group_period:
                btn = self.btn_group_period.checkedButton()
                if btn:
                    btn.setFocus()
        except Exception:
            pass

    def rotate_period(self, step: int = 1):
        """环形顺时针/逆时针轮转切换 SBC 周期"""
        period_list = ["1m", "2d", "3d", "5d", "5m", "30m", "60m", "day", "week", "month"]
        curr = getattr(self, "_current_period_mode", "1m").lower()
        if curr not in period_list:
            curr = "1m"
        idx = period_list.index(curr)
        new_idx = (idx + step) % len(period_list)
        new_mode = period_list[new_idx]
        self.set_period_mode(new_mode)
        if hasattr(self, 'lbl_info') and self.lbl_info:
            self.lbl_info.setText(f"📈 [周期轮转] 当前周期: 【{new_mode.upper()}】 (快捷键: ←/→ 键轮转, 1~9 直选, F 联动, Esc 关闭)")

    def switch_period_by_index(self, index: int):
        """通过数字键 1~9 直接切换到指定序号的周期"""
        period_list = ["1m", "2d", "3d", "5d", "5m", "30m", "60m", "day", "week", "month"]
        if 0 <= index < len(period_list):
            new_mode = period_list[index]
            self.set_period_mode(new_mode)
            if hasattr(self, 'lbl_info') and self.lbl_info:
                self.lbl_info.setText(f"📈 [周期直选] 当前周期: 【{new_mode.upper()}】 (快捷键: ←/→ 键轮转, 1~9 直选, F 联动, Esc 关闭)")

    def _toggle_stay_on_top(self):
        """切换 SBC 窗口置顶状态 (无缝 0 闪烁 0 重新刷新)"""
        self._is_stay_on_top = not getattr(self, '_is_stay_on_top', False)
        set_seamless_stay_on_top(self, self._is_stay_on_top)
        if hasattr(self, 'lbl_info') and self.lbl_info:
            txt = "开启" if self._is_stay_on_top else "关闭"
            self.lbl_info.setText(f"📌 [窗口置顶: {txt}] 当前标的: 【{self.code}】 (快捷键: T 开启/关闭置顶)")

    def keyPressEvent(self, event):
        """⚡ 窗口级快捷键：支持 T 置顶切换、R 测算、F 联动、方向键/Tab 轮转、1~9 直选、0 重置、Esc 关闭"""
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self._toggle_stay_on_top()
                event.accept()
                return
        elif key == Qt.Key.Key_R:
            self._on_eval_r_clicked()
            event.accept()
            return
        elif key == Qt.Key.Key_F:
            self._trigger_linkage()
            event.accept()
            return
        elif key == Qt.Key.Key_Q:
            self._on_rearrange_windows_clicked()
            event.accept()
            return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backtab):
            self.rotate_period(-1)
            event.accept()
            return
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Tab):
            self.rotate_period(1)
            event.accept()
            return
        elif Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
            idx = key - Qt.Key.Key_1
            self.switch_period_by_index(idx)
            event.accept()
            return
        elif key == Qt.Key.Key_0:
            if hasattr(self, 'canvas') and self.canvas:
                self.canvas.reset_view()
            event.accept()
            return
        elif key == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def _trigger_linkage(self):
        """⚡ 按下 F 键触发全系统与通达信/外部行情联动"""
        code = "".join(filter(str.isdigit, str(self.code))).zfill(6) if self.code else ""
        name = getattr(self, "name", "") or resolve_stock_name(code)
        if not code:
            return
        try:
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, 'main_window') and isinstance(app.main_window, ATSMainWindow):
                app.main_window.link_stock(code, name)
        except Exception as e:
            logger.debug(f"SBC link_stock exception: {e}")
        if hasattr(self, 'lbl_info') and self.lbl_info:
            self.lbl_info.setText(f"🔗 [F快捷联动] 已触发行情联动: {code} {name}")

    def _update_eval_btn_style(self):
        """更新测算按钮样式与高亮状态反馈"""
        if not hasattr(self, 'btn_eval_r') or not self.btn_eval_r:
            return
        if getattr(self, 'auto_eval_enabled', True):
            self.btn_eval_r.setText("⚡ 测算 (开)")
            self.btn_eval_r.setStyleSheet(
                "background-color: #064e3b; color: #34d399; font-weight: bold; "
                "border: 1px solid #059669; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;"
            )
            self.btn_eval_r.setToolTip("快捷键: R 键 (当前: 自动测算【已开启】)。数据刷新、切换周期、切股时全自动持续测算！点击或按 R 切换关闭")
        else:
            self.btn_eval_r.setText("⚡ 测算 (关)")
            self.btn_eval_r.setStyleSheet(
                "background-color: #1e1e28; color: #888899; font-weight: normal; "
                "border: 1px solid #333344; border-radius: 3px; padding: 2px 6px; font-size: 8.5pt;"
            )
            self.btn_eval_r.setToolTip("快捷键: R 键 (当前: 自动测算【已关闭】)。点击或按 R 开启全自动测算与标记")

    def _on_eval_r_clicked(self, toggle: bool = True):
        """⚡ 快捷键 R / 按钮切换自动测算状态并触发测算"""
        if toggle:
            self.auto_eval_enabled = not getattr(self, 'auto_eval_enabled', True)
            SBCIntradayChartDialog._global_auto_eval = self.auto_eval_enabled
            self._update_eval_btn_style()
            self._save_sbc_geometry()

        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.code = self.code
            self.canvas.auto_eval_enabled = bool(self.auto_eval_enabled)
            if self.auto_eval_enabled:
                self.canvas.run_adaptive_strategy_eval()
                res = getattr(self.canvas, 'strategy_eval_result', None)
                if res and res.get("is_matched", False):
                    self.lbl_info.setText(
                        f"🎉 [{res.get('period', '').upper()}] 自动测算开启: 得分={res.get('score')}分 | "
                        f"介入价={res.get('entry_price', 0.0):.2f}元 | 止损={res.get('stop_loss', 0.0):.2f}元 | "
                        f"目标1={res.get('target_price_1', 0.0):.2f}元"
                    )
                elif res:
                    self.lbl_info.setText(f"⚠️ [{res.get('period', '').upper()}] 自动测算: {res.get('reason', '当前周期未触发反转突破')}")
            else:
                self.canvas.strategy_eval_result = None
                self.canvas.update()
                self.lbl_info.setText("💡 [测算已关闭] 已清除图上测算介入标记。按 R 键可重新开启自动测算。")

    def showEvent(self, event):
        """SBC 窗口打开展示事件：恢复后台定时器，默认将焦点赋予当前显示的周期按钮上"""
        super().showEvent(event)
        if hasattr(self, 'poll_timer') and self.poll_timer and not self.poll_timer.isActive():
            self.poll_timer.start()
        if hasattr(self, 'hover_timer') and self.hover_timer and not self.hover_timer.isActive():
            self.hover_timer.start()
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.code = self.code
        if hasattr(self, 'btn_group_period') and self.btn_group_period:
            for btn in self.btn_group_period.buttons():
                if btn.isChecked():
                    btn.setFocus()
                    break

    def hideEvent(self, event):
        """窗口隐藏或贴边收起时，暂停后台高频轮询定时器，杜绝隐蔽消耗与日志刷屏"""
        if hasattr(self, 'poll_timer') and self.poll_timer:
            self.poll_timer.stop()
        if hasattr(self, 'hover_timer') and self.hover_timer:
            self.hover_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        """关闭窗口时彻底停止所有后台轮询定时器，从全局管理字典注销，自动持久化坐标并维护打开列表"""
        if hasattr(self, 'poll_timer') and self.poll_timer:
            self.poll_timer.stop()
        if hasattr(self, '_save_timer') and self._save_timer:
            self._save_timer.stop()
        if hasattr(self, 'hover_timer') and self.hover_timer:
            self.hover_timer.stop()
        if hasattr(self, 'snap_timer') and self.snap_timer:
            self.snap_timer.stop()
        if hasattr(self, '_geo_save_timer') and self._geo_save_timer:
            self._geo_save_timer.stop()
        self._do_save_sbc_geometry()

        # 从全局打开字典注销当前实例，彻底断开强引用，避免后台幽灵存活
        c_clean = getattr(self, "code", "")
        main_win = getattr(self, "main_workbench", None) or (self.parent().window() if (self.parent() and hasattr(self.parent(), 'window')) else None)
        target_win = main_win or (self.parent() if hasattr(self, 'parent') else None)
        if target_win and hasattr(target_win, '_sbc_dialogs') and isinstance(target_win._sbc_dialogs, dict):
            target_win._sbc_dialogs.pop(c_clean, None)
        if hasattr(SBCIntradayChartDialog, '_global_sbc_dialogs') and isinstance(SBCIntradayChartDialog._global_sbc_dialogs, dict):
            SBCIntradayChartDialog._global_sbc_dialogs.pop(c_clean, None)

        is_app_exiting = False
        if main_win:
            if not main_win.isVisible() or getattr(main_win, '_is_closing', False) or getattr(main_win, '_is_exiting', False):
                is_app_exiting = True

        # 若非整个程序退出（即用户手动单独关闭该 SBC 窗口），从持久化打开列表中移除
        if not is_app_exiting:
            try:
                _remove_sbc_open_record(self.code)
            except Exception:
                pass
        try:
            if hasattr(self, 'ladder_engine') and self.ladder_engine:
                self.ladder_engine.save_intraday_cache(force=False)
        except Exception:
            pass
        super().closeEvent(event)

    def resizeEvent(self, event):
        """调整大小事件自动防抖保存几何坐标"""
        super().resizeEvent(event)
        # [CRITICAL] 最大化、全屏、最小化、贴边隐藏或程序化移动期间，绝不记录为正常尺寸！
        if self.isMaximized() or self.isFullScreen() or self.isMinimized() or getattr(self, "is_hidden_state", False) or getattr(self, "_in_snap_action", False) or getattr(self, "_is_programmatic_move", False):
            return
        
        # 仅当处于普通浮动窗口且尺寸合理时，才记录为 _unmaximized_size 并防抖保存
        w, h = self.width(), self.height()
        if w >= 320 and h >= 180:
            max_w, max_h = self._get_max_allowed_sbc_size()
            # 严格保护：若尺寸过大（例如超过屏幕宽度的 60%），防止是最大化过渡中的假事件
            if w <= int(max_w * 0.9) and h <= int(max_h * 0.9):
                self._unmaximized_size = (w, h)
                if self.anchor_edge:
                    self.anchor_edge = None
                    self.normal_geometry = None
                self._save_sbc_geometry()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_user_dragging = True
        super().mousePressEvent(event)

    def moveEvent(self, event):
        """【🧲 移动防抖记录与磁吸触发】移动时记录内存坐标，仅在用户手动拖拽停止松手后触发磁吸吸附"""
        super().moveEvent(event)
        if self.isMaximized() or self.isFullScreen() or self.isMinimized() or getattr(self, "_is_programmatic_move", False) or getattr(self, "_in_snap_action", False):
            return
        self._save_sbc_geometry()
        if not self.is_hidden_state:
            if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                self._is_user_dragging = True
            if getattr(self, "_is_user_dragging", False):
                self.anchor_edge = None
                self.snap_timer.start(200)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow() and self.is_hidden_state:
                self._is_auto_popping = True
                QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
                self.show_normal_position()

    # --- 🧲 ATS 标准磁吸、边缘自动隐藏与滑出动画系统 ---
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
            self._save_sbc_geometry()

        self.anim_group.finished.connect(on_finished)
        self.anim_group.start()

    def _detect_and_snap(self):
        """【🧲 智能磁吸对齐】仅在用户手动拖拽停止松开鼠标后，才触发磁吸对齐"""
        if self.is_hidden_state or self.isMaximized() or self.isMinimized() or getattr(self, "_is_programmatic_move", False):
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.snap_timer.start(200)
            return

        # 💡 只有用户手动拖动触发时才允许进入磁吸贴边，重排与开机程序加载绝不自动贴边！
        if not getattr(self, "_is_user_dragging", False):
            return
        self._is_user_dragging = False

        screen = self.screen() or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if not screen:
            return
        screen_geo = screen.availableGeometry()
        win_geo = self.geometry()
        margin = 35

        snapped = False
        edge = None
        target_x = win_geo.left()
        target_y = win_geo.top()

        # 优先吸附屏幕四周边缘并激活边缘自动收缩
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

        # 次选：若未靠屏幕边缘，则检测是否靠近主工作台
        if not snapped:
            main_win = getattr(self, "main_workbench", None)
            if not main_win and self.parent() is not None:
                main_win = self.parent().window()
            if not main_win:
                for w in QApplication.topLevelWidgets():
                    if w.isVisible() and w.__class__.__name__ == 'ATSMainWindow':
                        main_win = w
                        break

            if main_win and main_win.isVisible() and not main_win.isMaximized() and not main_win.isMinimized():
                m_fg = main_win.geometry()
                if abs(win_geo.left() - m_fg.right()) < margin:
                    target_x = m_fg.right()
                    snapped = True
                elif abs(win_geo.right() - m_fg.left()) < margin:
                    target_x = m_fg.left() - win_geo.width()
                    snapped = True
                if abs(win_geo.top() - m_fg.top()) < margin:
                    target_y = m_fg.top()
                    snapped = True
                elif abs(win_geo.bottom() - m_fg.bottom()) < margin:
                    target_y = m_fg.bottom() - win_geo.height()
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
        """贴边自动收缩隐藏为 5px 边缘条，半透明 0.35"""
        # 【置顶与磁吸严格互斥】：置顶状态下绝对禁止折叠隐藏
        if getattr(self, "stays_on_top", False):
            return
        if not self.anchor_edge or self.is_hidden_state or not self.normal_geometry:
            return

        screen = self.screen() or QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        if not screen:
            return
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
        """鼠标悬停边缘条时自动滑出展开至正常完整画幅"""
        if self.is_hidden_state:
            self.is_hidden_state = False
            self._is_auto_popping = True
            QTimer.singleShot(500, lambda: setattr(self, '_is_auto_popping', False))
            self._last_show_time = time.time()
            self._has_hovered_since_show = False
            if self.normal_geometry:
                self.start_slide_animation(self.normal_geometry, 1.0, duration=200)
            self.setWindowOpacity(1.0)
        else:
            self.setWindowOpacity(1.0)

        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _check_hover(self):
        """100ms 鼠标位置巡检：实现边缘悬停极速展开与移出自动收缩隐藏"""
        # 【置顶与磁吸严格互斥】：置顶状态下不执行任何贴边或离开折叠检测
        if not self.isVisible() or getattr(self, "stays_on_top", False):
            return

        # 仅在有贴边锚定边缘或处于贴边隐藏状态时才执行悬浮检测，其余时刻 0 开销
        if not self.anchor_edge and not self.is_hidden_state:
            return

        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.leave_ticks = 0
            self.hover_ticks = 0
            return

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

    def _toggle_log_panel(self):
        vis = not self.log_box.isVisible()
        self.log_box.setVisible(vis)
        self.btn_toggle_log.setText("📋 行情数据日志 (显示)" if vis else "📋 行情数据日志")

    def _on_period_btn_clicked(self):
        """【📈 切换周期】在 1日分时 / 2日分时 / 3日分时 与 5分/30分/60分/日K 通道图间自由切换"""
        sender = self.sender()
        if not sender:
            return
        mode = sender.property("period_mode") or "1m"
        self.set_period_mode(mode, reload=True, save=True)

    def _on_rearrange_windows_clicked(self):
        """【🪟 所在屏幕窗口重排】就地自动平铺重排当前屏幕上所有打开的 SBC 窗口 (多显示器支持，保持原尺寸不变，绝不强行移至主屏)"""
        rearrange_all_sbc_windows(parent_win=self)

    def _on_clear_cache_clicked(self):
        """【🧹 清理缓存】清除当前标的在 TDX 与引擎内存中的错误/旧数据，并强力重置刷新"""
        c_clean = str(self.code).zfill(6)
        fetcher = TDXRealtimeFetcher.get_instance()
        fetcher.clear_stock_cache(c_clean)
        self.engine.clear_stock_cache(c_clean)

        # 向上同步刷新主工作台
        main_win = getattr(self, "main_workbench", None)
        if main_win and hasattr(main_win, "_on_manual_refresh"):
            main_win._on_manual_refresh()

        self.reload_chart()
        QMessageBox.information(self, "🧹 缓存已强力重置", f"标的 [{c_clean} {resolve_stock_name(c_clean)}] 的内存与磁盘行情缓存已成功强力清除！\n已自动拉取最新 TDX 分时数据并重置评级与分时走势线！")

    def set_custom_backtest_trades(self, trades_df: pd.DataFrame, df_kline: Optional[pd.DataFrame] = None):
        """
        【📈 注入多周期通道量化回测交易记录】
        将回测买卖点与收益指标一键注入 SBC 走势图画布：
        - 自动生成买卖信号对与收益率标签；
        - 默认选中首笔交易并激活【点击收益】高亮光束与悬浮卡片；
        - 切换至日K线通道模式展示完整回测周期。
        """
        from ats.multi_period_channel_backtester import convert_backtest_trades_to_sbc_signals
        self.custom_trades_df = trades_df
        self.custom_kline_df = df_kline
        self.custom_signals = convert_backtest_trades_to_sbc_signals(trades_df)

        if self.custom_signals:
            self.canvas.selected_trade_id = 0

        self.set_period_mode("day", reload=True, save=False)
        t_cnt = len(trades_df) if trades_df is not None else 0
        win_cnt = len(trades_df[trades_df['pnl_pct'] > 0]) if trades_df is not None and not trades_df.empty else 0
        win_r = (win_cnt / t_cnt * 100.0) if t_cnt > 0 else 0.0
        self.lbl_title.setText(f"📊 {self.code} {resolve_stock_name(self.code)} | [多周期通道回测] 交易:{t_cnt}笔 胜率:{win_r:.1f}% (点击标记看收益)")
        self.lbl_info.setText("💡 【点击收益交互提示】: 鼠标直接点击任意 🟢买 / 🔴卖 信号标签，即可高亮持仓区间并展开单笔盈亏卡片；按 [ 与 ] 键或 Space 键可快速轮巡切换各笔交易。")

    def reload_chart(self, is_timer_tick: bool = False):
        if is_timer_tick:
            # 1. 窗口关闭/隐藏保护：若窗口已经不可见，彻底跳过轮询与计算
            if not self.isVisible():
                if hasattr(self, 'poll_timer') and self.poll_timer and self.poll_timer.isActive():
                    self.poll_timer.stop()
                return

            # 2. 交易时段自适应判断：非交易时段降低轮询开销与日志刷屏
            is_trading = False
            try:
                from JohnsonUtil import commonTips as cct
                is_trading = bool(cct.get_work_time())
            except Exception:
                now = datetime.now()
                is_trading = (now.weekday() < 5) and ((9, 15) <= (now.hour, now.minute) <= (11, 30) or (13, 0) <= (now.hour, now.minute) <= (15, 5))

            if not is_trading:
                # 非交易期将定时器降频至 60 秒
                if hasattr(self, 'poll_timer') and self.poll_timer and self.poll_timer.interval() < 30000:
                    self.poll_timer.setInterval(60000)
                # 若非交易期已完成过首次加载，跳过重复的心跳计算与日志
                if getattr(self, '_has_initial_loaded', False):
                    return
            else:
                # 实盘交易期恢复 2 秒轮询
                if hasattr(self, 'poll_timer') and self.poll_timer and self.poll_timer.interval() != 2000:
                    self.poll_timer.setInterval(2000)

        self._has_initial_loaded = True

        mode = getattr(self, '_current_period_mode', '1m')
        fetcher = TDXRealtimeFetcher.get_instance()

        snap = fetcher.fetch_stock_snapshot(self.code)

        op = float(snap.get("open_price", 0.0))
        p = float(snap.get("price", 0.0))
        vw = float(snap.get("vwap", p))
        hi = float(snap.get("high_price", p))
        lo = float(snap.get("low_price", p))
        amt = float(snap.get("amount", 0.0))
        to_rate = float(snap.get("turnover_rate", 0.0))

        if getattr(self, "custom_signals", None):
            sigs = self.custom_signals
        else:
            state = self.engine._get_stock_state(self.code, op) if self.engine else {}
            sigs = state.get("signals", [])

            if not sigs and self.engine is not None and op > 1.0:
                now_t = datetime.now().strftime("%H:%M:%S")
                eval_res = self.engine.evaluate_seven_nodes(
                    code=self.code,
                    current_time_str=now_t,
                    open_price=op,
                    price=p,
                    high_price=hi,
                    low_price=lo,
                    vwap=vw,
                    turnover_rate=to_rate,
                    amount=amt
                )
                sigs = state.get("signals", []) or eval_res.get("signals", [])

        t_min = op * 1.03 if op > 1.0 else 0.0
        t_max = op * 1.05 if op > 1.0 else 0.0

        if mode in ["2d", "3d", "5d"]:
            days = 2 if mode == "2d" else (3 if mode == "3d" else 5)
            df_multi = fetcher.fetch_multi_day_intraday_bars(self.code, days=days)
            if not df_multi.empty:
                if op <= 1.0:
                    op = float(df_multi.iloc[-1].get("open", p))
                if vw <= 1.0:
                    vw = float(df_multi.iloc[-1].get("vwap", p))
                if hi <= 1.0:
                    hi = float(df_multi['high'].max()) if 'high' in df_multi.columns else p
                if lo <= 1.0:
                    lo = float(df_multi['low'].min()) if 'low' in df_multi.columns else p
                cl_last = float(df_multi.iloc[-1].get("close", p))
                self.canvas.set_data(df_multi, op, vw, hi, lo, t_min, t_max, sigs, period_mode=mode)
                self.lbl_title.setText(f"📊 {self.code} {resolve_stock_name(self.code)} | [{mode.upper()}多日分时] 今:{op:.2f} 现:{cl_last:.2f}")
                self.lbl_title.setToolTip(f"【{self.code} {resolve_stock_name(self.code)}】[{mode.upper()}多日分时] 今开={op:.2f}元, 现价={cl_last:.2f}元, VWAP={vw:.2f}元, 最高={hi:.2f}元, 最低={lo:.2f}元 | 买卖信号数: {len(sigs)} 步")
                if getattr(self, 'auto_eval_enabled', True):
                    self._on_eval_r_clicked(toggle=False)
            return

        if mode in ["5m", "15m", "30m", "60m", "day", "week", "month"]:
            if getattr(self, "custom_kline_df", None) is not None and not self.custom_kline_df.empty:
                df_kline = self.custom_kline_df
            else:
                fetch_c = min(800, max(250, len(self.custom_signals) * 5)) if getattr(self, "custom_signals", None) else 150
                df_kline = fetcher.fetch_kline_bars(self.code, category=mode, count=fetch_c)

            if not df_kline.empty:
                if op <= 1.0:
                    op = float(df_kline.iloc[-1].get("open", p))
                if vw <= 1.0:
                    vw = float(df_kline.iloc[-1].get("close", p))
                if hi <= 1.0:
                    hi = float(df_kline['high'].max()) if 'high' in df_kline.columns else p
                if lo <= 1.0:
                    lo = float(df_kline['low'].min()) if 'low' in df_kline.columns else p
                cl_last = float(df_kline.iloc[-1].get("close", p))
                self.canvas.set_kline_data(df_kline, open_p=op, vwap_p=vw, high_p=hi, low_p=lo, sell_min=t_min, sell_max=t_max, signals=sigs, period_mode=mode)
                if getattr(self, "custom_trades_df", None) is not None:
                    t_cnt = len(self.custom_trades_df)
                    win_cnt = len(self.custom_trades_df[self.custom_trades_df['pnl_pct'] > 0]) if not self.custom_trades_df.empty else 0
                    win_r = (win_cnt / t_cnt * 100.0) if t_cnt > 0 else 0.0
                    self.lbl_title.setText(f"📊 {self.code} {resolve_stock_name(self.code)} | [多周期通道回测] 交易:{t_cnt}笔 胜率:{win_r:.1f}% (点击标记看收益)")
                    self.lbl_title.setToolTip(f"【{self.code} {resolve_stock_name(self.code)}】多周期通道量化回测走势图 | 共 {t_cnt} 笔交易，胜率 {win_r:.1f}% | 点击任意买卖信号标记或按 Space/[/] 键查看单笔收益与持仓光束")
                else:
                    self.lbl_title.setText(f"📊 {self.code} {resolve_stock_name(self.code)} | [{mode.upper()}GG通道] 今:{op:.2f} 现:{cl_last:.2f}")
                    self.lbl_title.setToolTip(f"【{self.code} {resolve_stock_name(self.code)}】[{mode.upper()}K线通道] 今开={op:.2f}元, 现价={cl_last:.2f}元, VWAP={vw:.2f}元, 最高={hi:.2f}元, 最低={lo:.2f}元 | 买卖信号数: {len(sigs)} 步")
                if getattr(self, 'auto_eval_enabled', True):
                    self._on_eval_r_clicked(toggle=False)
            return

        # 默认为 1日分时 (1m)
        df_intraday = fetcher.fetch_intraday_bars(self.code)

        # 2. 三重物理兜底：若仍为空，利用 state["time_snapshots"] 物理构造全量 DataFrame
        if (df_intraday is None or df_intraday.empty) and state:
            snaps = state.get("time_snapshots", {})
            if snaps:
                rows = []
                for t_str, s_dict in sorted(snaps.items()):
                    rows.append({
                        "time": t_str,
                        "close": float(s_dict.get("price", op if op > 0 else 1.0)),
                        "open": op if op > 0 else float(s_dict.get("price", 1.0)),
                        "high": float(s_dict.get("high", op)),
                        "low": float(s_dict.get("low", op)),
                        "vwap": float(s_dict.get("vwap", op)),
                        "turnover_rate": float(s_dict.get("turnover_rate", 0.0)),
                        "amount": float(s_dict.get("amount", 0.0))
                    })
                if rows:
                    df_intraday = pd.DataFrame(rows).set_index("time")

        # 💡 [数据隔离防污染强校验] 若当前标的数据获取为空/异常，绝对不上溯抓取主工作台其他标的数据，维持当前有效画幅不变
        if df_intraday is None or df_intraday.empty:
            return

        if (op <= 1.0 or p <= 1.0) and not df_intraday.empty:
            if op <= 1.0:
                op = float(df_intraday.iloc[0].get("open", p))
            if p <= 1.0:
                p = float(df_intraday.iloc[-1].get("close", op))
            if hi <= 1.0:
                hi = float(df_intraday['high'].max()) if 'high' in df_intraday.columns else p
            if lo <= 1.0:
                lo = float(df_intraday['low'].min()) if 'low' in df_intraday.columns else p
            if vw <= 1.0:
                vw = float(df_intraday.iloc[-1].get("vwap", p))
            if amt <= 0:
                amt = float(df_intraday.iloc[-1].get("amount", 0.0))
            if to_rate <= 0:
                to_rate = float(df_intraday.iloc[-1].get("turnover_rate", 0.0))

        self.canvas.set_data(df_intraday, op, vw, hi, lo, t_min, t_max, sigs, period_mode="1m")
        self.lbl_title.setText(f"📊 {self.code} {resolve_stock_name(self.code)} | 今:{op:.2f} 现:{p:.2f}")
        self.lbl_title.setToolTip(f"【{self.code} {resolve_stock_name(self.code)}】今开={op:.2f}元, 现价={p:.2f}元, VWAP={vw:.2f}元, 最高={hi:.2f}元, 最低={lo:.2f}元 | 买卖信号数: {len(sigs)} 步")

        # 打印行情健康调试日志
        now_str = datetime.now().strftime("%H:%M:%S")
        server_info = fetcher.best_server.get("name", "TDX服务器") if hasattr(fetcher, "best_server") and fetcher.best_server else "TDX"
        k_count = len(df_intraday) if not df_intraday.empty else 0
        log_msg = (
            f"[{now_str}] 🚀 行情源: {server_info} | 分时 K 线: {k_count} 条\n"
            f"[{now_str}] 📈 关键价格: 今开={op:.2f}元, 现价={p:.2f}元, VWAP={vw:.2f}元, 最高={hi:.2f}元, 最低={lo:.2f}元\n"
            f"[{now_str}] 💰 量价换手: 换手率={to_rate:.2f}%, 累计成交额={amt/1e8:.2f}亿元 | 买卖信号数: {len(sigs)} 步\n"
            f"[{now_str}] ✅ 结论: 行情摄入 {k_count} 条，分时基准图与信号 Tag 渲染正常。"
        )
        self.txt_log.setPlainText(log_msg)

        if getattr(self, 'auto_eval_enabled', True):
            self._on_eval_r_clicked(toggle=False)


def open_sbc_chart_dialog(parent_win: Optional[QWidget] = None, code: str = "688826", period_mode: Optional[str] = None, *args, **kwargs) -> Optional[SBCIntradayChartDialog]:
    """
    【📈 全局通用 SBC 独立分时走势图调起入口】支持在 ATS 任意表格/面板右键菜单中一键唤醒调起分时图
    """
    # 兼容各种调用形式 (code, parent=self / parent_win, code)
    if "parent" in kwargs and parent_win is None:
        parent_win = kwargs.get("parent")
    if not isinstance(code, str) and isinstance(parent_win, str):
        temp = code
        code = parent_win
        parent_win = temp if isinstance(temp, QWidget) else None

    if not code:
        return None
    c_clean = "".join(filter(str.isdigit, str(code))).zfill(6)
    if not c_clean or c_clean == "000000":
        return None

    main_win = parent_win.window() if (parent_win and hasattr(parent_win, 'window')) else None
    target_win = main_win or parent_win

    if target_win:
        if not hasattr(target_win, '_sbc_dialogs'):
            target_win._sbc_dialogs = {}
        sbc_dict = target_win._sbc_dialogs
    else:
        if not hasattr(SBCIntradayChartDialog, '_global_sbc_dialogs'):
            SBCIntradayChartDialog._global_sbc_dialogs = {}
        sbc_dict = SBCIntradayChartDialog._global_sbc_dialogs

    dlg = sbc_dict.get(c_clean)
    engine = IntradayStrategyEngine.get_instance()

    if dlg is None or not dlg.isVisible():
        dlg = SBCIntradayChartDialog(parent=target_win, code=c_clean, engine=engine, initial_period_mode=period_mode)
        sbc_dict[c_clean] = dlg
    else:
        dlg.code = c_clean
        dlg.lbl_title.setText(f"📊 标的: {c_clean} {resolve_stock_name(c_clean)} | SBC 实盘走势基准线")
        dlg.setWindowTitle(f"📈 【{c_clean} {resolve_stock_name(c_clean)}】SBC 实盘分时走势与关键阶梯基准图")
        if period_mode:
            dlg.set_period_mode(period_mode, reload=True, save=True)
        else:
            dlg.reload_chart()

    trades_df = kwargs.get("trades_df", None)
    df_kline = kwargs.get("df_kline", None)
    if trades_df is not None:
        dlg.set_custom_backtest_trades(trades_df, df_kline=df_kline)

    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    _record_sbc_open(c_clean, dlg.geometry(), period_mode=getattr(dlg, '_current_period_mode', '1m'))
    return dlg


def _get_sbc_layout_cfg_path():
    from sys_utils import get_app_root
    cfg_dir = os.path.join(get_app_root(), "config")
    os.makedirs(cfg_dir, exist_ok=True)
    return os.path.join(cfg_dir, "intraday_ui_layout.json")


def _record_sbc_open(code: str, geo=None, period_mode: Optional[str] = None):
    """记录新打开的 SBC 窗口"""
    try:
        c_clean = str(code).zfill(6)
        cfg_path = _get_sbc_layout_cfg_path()
        data = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        sbc_list = data.get("sbc_open_windows", [])
        # 查找是否存在
        found = False
        for item in sbc_list:
            if item.get("code") == c_clean:
                if geo:
                    item["x"] = geo.x()
                    item["y"] = geo.y()
                    item["width"] = geo.width()
                    item["height"] = geo.height()
                if period_mode:
                    item["period_mode"] = period_mode
                found = True
                break
        if not found:
            entry = {"code": c_clean}
            if geo:
                entry["x"] = geo.x()
                entry["y"] = geo.y()
                entry["width"] = geo.width()
                entry["height"] = geo.height()
            else:
                entry["x"] = 100
                entry["y"] = 100
                entry["width"] = 680
                entry["height"] = 420
            if period_mode:
                entry["period_mode"] = period_mode
            sbc_list.append(entry)

        data["sbc_open_windows"] = sbc_list
        if period_mode:
            if "sbc_period_modes" not in data:
                data["sbc_period_modes"] = {}
            data["sbc_period_modes"]["latest"] = period_mode
            data["sbc_period_modes"][c_clean] = period_mode

        if geo and geo.width() >= 200 and geo.height() >= 100:
            data["sbc_window_size"] = {"width": geo.width(), "height": geo.height()}
            data["sbc_window_geometry"] = {"x": geo.x(), "y": geo.y(), "width": geo.width(), "height": geo.height()}
            if "sbc_geometries" not in data:
                data["sbc_geometries"] = {}
            data["sbc_geometries"]["latest"] = data["sbc_window_geometry"]
            data["sbc_geometries"][c_clean] = data["sbc_window_geometry"]
        tmp_path = cfg_path + f".tmp_{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            if os.path.exists(cfg_path):
                os.replace(tmp_path, cfg_path)
            else:
                os.rename(tmp_path, cfg_path)
        except Exception:
            import shutil
            shutil.move(tmp_path, cfg_path)
    except Exception as e:
        logger.debug(f"记录打开 SBC 窗口异常: {e}")


def _remove_sbc_open_record(code: str):
    """从已打开 SBC 窗口列表中移除指定个股"""
    try:
        c_clean = str(code).zfill(6)
        cfg_path = _get_sbc_layout_cfg_path()
        if not os.path.exists(cfg_path):
            return
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sbc_list = data.get("sbc_open_windows", [])
        new_list = [item for item in sbc_list if item.get("code") != c_clean]
        if len(new_list) != len(sbc_list):
            data["sbc_open_windows"] = new_list
            tmp_path = cfg_path + f".tmp_{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                if os.path.exists(cfg_path):
                    os.replace(tmp_path, cfg_path)
                else:
                    os.rename(tmp_path, cfg_path)
            except Exception:
                import shutil
                shutil.move(tmp_path, cfg_path)
    except Exception as e:
        logger.debug(f"移除 SBC 窗口记录异常: {e}")


def save_all_open_sbc_windows():
    """【💾 全局保存所有已打开的 SBC 窗口与坐标、周期】ATS 退出或定时刷盘时调用"""
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.sip import isdeleted
        active_list = []
        last_valid_geo = None
        period_map = {}
        latest_period = None
        for w in QApplication.topLevelWidgets():
            if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w) and w.isVisible():
                geo = w.normal_geometry if (getattr(w, 'is_hidden_state', False) and getattr(w, 'normal_geometry', None)) else w.geometry()
                c = getattr(w, 'code', None)
                cur_period = getattr(w, '_current_period_mode', '1m')
                if c:
                    c_clean = str(c).zfill(6)
                    active_list.append({
                        "code": c_clean,
                        "x": geo.x(),
                        "y": geo.y(),
                        "width": geo.width(),
                        "height": geo.height(),
                        "anchor_edge": getattr(w, "anchor_edge", None),
                        "is_hidden_state": bool(getattr(w, "is_hidden_state", False)),
                        "period_mode": cur_period
                    })
                    period_map[c_clean] = cur_period
                    latest_period = cur_period
                    if geo.width() >= 200 and geo.height() >= 100:
                        last_valid_geo = geo

        cfg_path = _get_sbc_layout_cfg_path()
        data = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data["sbc_open_windows"] = active_list
        if "sbc_period_modes" not in data:
            data["sbc_period_modes"] = {}
        data["sbc_period_modes"].update(period_map)
        if latest_period:
            data["sbc_period_modes"]["latest"] = latest_period

        if last_valid_geo:
            data["sbc_window_size"] = {"width": last_valid_geo.width(), "height": last_valid_geo.height()}
            data["sbc_window_geometry"] = {
                "x": last_valid_geo.x(),
                "y": last_valid_geo.y(),
                "width": last_valid_geo.width(),
                "height": last_valid_geo.height()
            }
            if "sbc_geometries" not in data:
                data["sbc_geometries"] = {}
            data["sbc_geometries"]["latest"] = data["sbc_window_geometry"]
        tmp_path = cfg_path + f".tmp_{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        try:
            if os.path.exists(cfg_path):
                os.replace(tmp_path, cfg_path)
            else:
                os.rename(tmp_path, cfg_path)
        except Exception:
            import shutil
            shutil.move(tmp_path, cfg_path)
    except Exception as e:
        logger.debug(f"保存所有已打开 SBC 窗口列表异常: {e}")


def restore_all_open_sbc_windows(parent_win=None):
    """【🚀 启动时自动恢复所有持久化的 SBC 窗口、位置及所选周期】"""
    try:
        cfg_path = _get_sbc_layout_cfg_path()
        if not os.path.exists(cfg_path):
            return
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sbc_list = data.get("sbc_open_windows", [])
        if not sbc_list:
            return

        from gui_utils import clamp_window_to_screens
        for item in sbc_list:
            code = item.get("code")
            if not code:
                continue
            x = item.get("x", 100)
            y = item.get("y", 100)
            w = item.get("width", 680)
            h = item.get("height", 420)
            saved_period = item.get("period_mode") or item.get("period") or (
                data.get("sbc_period_modes", {}).get(str(code).zfill(6))
            ) or "1m"
            rx, ry = clamp_window_to_screens(x, y, w, h)
            
            dlg = open_sbc_chart_dialog(parent_win, code, period_mode=saved_period)
            if dlg:
                dlg._is_programmatic_move = True
                dlg._is_user_dragging = False
                try:
                    dlg.setGeometry(rx, ry, w, h)
                    dlg.snap_timer.stop()
                    saved_edge = item.get("anchor_edge")
                    saved_hidden = item.get("is_hidden_state", False)
                    # 💡 只有退出前明确处于磁吸状态的窗口，启动才自动恢复磁吸；普通边缘位置绝不误触发收缩！
                    if saved_edge:
                        dlg.anchor_edge = saved_edge
                        dlg.normal_geometry = QRect(rx, ry, w, h)
                        if saved_hidden:
                            dlg.hide_to_edge()
                        else:
                            dlg.setWindowOpacity(1.0)
                    else:
                        dlg.anchor_edge = None
                        dlg.normal_geometry = None
                        dlg.is_hidden_state = False
                        dlg.setWindowOpacity(1.0)
                    if hasattr(dlg, 'set_period_mode'):
                        dlg.set_period_mode(saved_period, reload=False, save=False)
                    dlg._save_sbc_geometry()
                finally:
                    dlg._is_programmatic_move = False
    except Exception as e:
        logger.warning(f"自动恢复 SBC 窗口列表异常: {e}")
        logger.warning(f"自动恢复 SBC 窗口列表异常: {e}")


def rearrange_all_sbc_windows(parent_win=None):
    """
    【🪟 全局 SBC 独立窗口基于各自物理屏幕网格平铺重排】
    自动按物理显示器分组，对每个屏幕上打开的 SBC 分时走势独立窗口分别在其所在屏幕内就地网格平铺重排。
    - 多屏幕独立处理：每个物理显示器各自平铺重排，绝不把副屏窗口强行拉到主屏；
    - 尺寸与状态保持：保持各窗口已有宽高尺寸，彻底重置贴边半隐藏状态为完全展开显示；
    - 自动持久化：重排完成后即时同步保存全部最新窗口坐标。
    """
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.sip import isdeleted

    active_dialogs = []

    # 1. 优先从 parent_win 的 _sbc_dialogs 收集
    if parent_win and hasattr(parent_win, '_sbc_dialogs') and isinstance(parent_win._sbc_dialogs, dict):
        for d in parent_win._sbc_dialogs.values():
            if d is not None and not isdeleted(d) and d.isVisible():
                if d not in active_dialogs:
                    active_dialogs.append(d)

    # 2. 从全局 topLevelWidgets 补充收集所有可见的 SBCIntradayChartDialog
    for w in QApplication.topLevelWidgets():
        if isinstance(w, SBCIntradayChartDialog) and not isdeleted(w) and w.isVisible():
            if w not in active_dialogs:
                active_dialogs.append(w)

    if not active_dialogs:
        if parent_win and not os.environ.get("PYTEST_CURRENT_TEST"):
            QMessageBox.information(parent_win, "🪟 窗口重排", "当前暂无打开的 SBC 分时走势独立窗口。")
        return

    # 2.1 [FIX] 前置检查：若有任何窗口处于最大化或最小化状态，先强制还原为正常窗口大小
    for dlg in active_dialogs:
        if dlg.isMaximized() or dlg.isMinimized():
            dlg.showNormal()

    # 3. 按窗口当前所在物理屏幕进行分组 (多显示器支持)
    screens = QApplication.screens()
    primary_screen = QApplication.primaryScreen() or (screens[0] if screens else None)
    screen_map = {}  # screen_obj -> list of dlgs

    for dlg in active_dialogs:
        dlg_screen = None
        if hasattr(dlg, "screen") and callable(dlg.screen):
            try:
                dlg_screen = dlg.screen()
            except Exception:
                dlg_screen = None
        if not dlg_screen and hasattr(dlg, "geometry"):
            try:
                dlg_screen = QApplication.screenAt(dlg.geometry().center())
            except Exception:
                dlg_screen = None
        if not dlg_screen and screens:
            for s in screens:
                try:
                    if s.geometry().intersects(dlg.geometry()):
                        dlg_screen = s
                        break
                except Exception:
                    pass
        if not dlg_screen:
            dlg_screen = primary_screen

        if dlg_screen not in screen_map:
            screen_map[dlg_screen] = []
        screen_map[dlg_screen].append(dlg)

    # 4. 对每个屏幕分别独立执行：现有尺寸优先重排，超出屏幕边界时才自适应缩放 (<=2个按2列，>2个按最多3列)
    for target_screen, dlgs_on_screen in screen_map.items():
        if not target_screen or not dlgs_on_screen:
            continue
        sg = target_screen.availableGeometry()
        count = len(dlgs_on_screen)

        # 4.1 确保所有窗口退出最大化/全屏/最小化
        for dlg in dlgs_on_screen:
            if dlg.isMaximized() or dlg.isMinimized() or dlg.isFullScreen():
                dlg.showNormal()

        # 4.2 提取每个窗口的当前/历史期望尺寸
        dlg_sizes = []
        for dlg in dlgs_on_screen:
            unmax = getattr(dlg, "_unmaximized_size", None)
            if unmax and isinstance(unmax, (tuple, list)) and len(unmax) == 2:
                w, h = int(unmax[0]), int(unmax[1])
            else:
                w, h = dlg.width(), dlg.height()
            w = max(320, min(w, sg.width()))
            h = max(200, min(h, sg.height()))
            dlg_sizes.append((w, h))

        # 4.3 模拟【旧版保持原尺寸平铺排布】：检测是否会超出屏幕边界
        margin_x = 10
        margin_y = 10
        pad_x = 20
        pad_y = 20

        sim_x = sg.left() + pad_x
        sim_y = sg.top() + pad_y
        row_max_h = 0
        is_overflow = False
        legacy_positions = []

        for idx, (w, h) in enumerate(dlg_sizes):
            if sim_x + w > sg.right() and sim_x > sg.left() + pad_x:
                sim_x = sg.left() + pad_x
                sim_y += row_max_h + margin_y
                row_max_h = 0

            if (sim_x + w > sg.right()) or (sim_y + h > sg.bottom()):
                is_overflow = True
                break

            legacy_positions.append((sim_x, sim_y, w, h))
            sim_x += w + margin_x
            row_max_h = max(row_max_h, h)

        # 4.4 根据是否溢出选择排布策略：
        if not is_overflow and len(legacy_positions) == count:
            # 策略 A：【未超出屏幕 -> 保持旧逻辑与现有尺寸不变】
            logger.info(f"🪟 [SBC窗口重排] 现有尺寸容纳正常，采用旧版原尺寸平铺 (共 {count} 个窗口)")
            for idx, dlg in enumerate(dlgs_on_screen):
                pos_x, pos_y, w, h = legacy_positions[idx]
                dlg.resize(w, h)
                dlg._unmaximized_size = (w, h)

                if hasattr(dlg, "snap_timer"):
                    dlg.snap_timer.stop()
                dlg.anchor_edge = None
                dlg.normal_geometry = None
                dlg.is_hidden_state = False
                dlg._is_dragging = False
                dlg._is_user_dragging = False
                dlg.setWindowOpacity(1.0)
                dlg._is_programmatic_move = True
                try:
                    dlg.move(pos_x, pos_y)
                    if hasattr(dlg, "_save_sbc_geometry"):
                        dlg._save_sbc_geometry()
                    dlg.raise_()
                    dlg.activateWindow()
                finally:
                    dlg._is_programmatic_move = False
        else:
            # 策略 B：【现有尺寸超出屏幕 -> 启动自适应缩放 (<=2个按2列自适应，>2个按最多3列自适应)】
            logger.info(f"🪟 [SBC窗口重排] 现有尺寸超出屏幕边界，启动智能自适应网格缩放 (共 {count} 个窗口)")
            if count <= 2:
                cols = 2
            else:
                cols = 3
            rows = math.ceil(count / cols)

            margin_x = 8
            margin_y = 8
            pad_left = 12
            pad_top = 12
            pad_right = 12
            pad_bottom = 12

            avail_w = max(400, sg.width() - pad_left - pad_right)
            avail_h = max(300, sg.height() - pad_top - pad_bottom)

            target_w = int((avail_w - (cols - 1) * margin_x) / cols)
            target_w = max(320, min(target_w, avail_w))

            raw_target_h = int((avail_h - (rows - 1) * margin_y) / rows)
            if rows == 1:
                target_h = min(raw_target_h, int(target_w * 0.62), int(avail_h * 0.60))
            else:
                target_h = raw_target_h
            target_h = max(200, min(target_h, avail_h))

            for idx_d, dlg in enumerate(dlgs_on_screen):
                r = idx_d // cols
                c = idx_d % cols

                pos_x = sg.left() + pad_left + c * (target_w + margin_x)
                pos_y = sg.top() + pad_top + r * (target_h + margin_y)

                dlg.resize(target_w, target_h)
                dlg._unmaximized_size = (target_w, target_h)

                if hasattr(dlg, "snap_timer"):
                    dlg.snap_timer.stop()
                dlg.anchor_edge = None
                dlg.normal_geometry = None
                dlg.is_hidden_state = False
                dlg._is_dragging = False
                dlg._is_user_dragging = False
                dlg.setWindowOpacity(1.0)
                dlg._is_programmatic_move = True
                try:
                    dlg.move(pos_x, pos_y)
                    if hasattr(dlg, "_save_sbc_geometry"):
                        dlg._save_sbc_geometry()
                    dlg.raise_()
                    dlg.activateWindow()
                finally:
                    dlg._is_programmatic_move = False

            SBCIntradayChartDialog._global_sbc_size = (target_w, target_h)

    # 5. 持久化最新窗口坐标
    try:
        save_all_open_sbc_windows()
    except Exception as e:
        logger.debug(f"重排后持久化坐标异常: {e}")

    logger.info(f"🪟 [SBC自适应窗口重排] 已成功在 {len(screen_map)} 个屏幕上将 {len(active_dialogs)} 个 SBC 窗口自适应平铺排布！")


import copy


class IntradayStrategyEditDialog(QDialog):
    """自定制分时策略 JSON 编辑器（支持单策略精准聚焦、一键新建/复制/删除策略与全量 JSON 多模式管理）"""
    def __init__(self, parent=None, initial_strategy_id: Optional[str] = None, current_code: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 自定制分时交易策略编辑器")
        self.resize(920, 660)
        self.engine = IntradayStrategyEngine.get_instance()
        self.initial_strategy_id = initial_strategy_id
        self.current_code = current_code
        self._full_config_data = {}
        self._current_selected_mode = ""  # 记录当前选中的策略 ID 或 "__ALL__"
        apply_dark_theme(self)
        self._load_full_config()
        self._init_ui()

    def _load_full_config(self):
        if os.path.exists(self.engine.config_path):
            try:
                with open(self.engine.config_path, "r", encoding="utf-8") as f:
                    self._full_config_data = json.load(f)
            except Exception as e:
                logger.error(f"加载策略配置文件失败: {e}")
                self._full_config_data = {"version": "2.0", "strategies": self.engine.strategies}
        else:
            self._full_config_data = {"version": "2.0", "strategies": self.engine.strategies}

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 顶部策略选择与管理栏
        top_bar = QHBoxLayout()
        lbl_target = QLabel("🎯 策略选择:")
        lbl_target.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 10pt;")
        top_bar.addWidget(lbl_target)

        self.combo_strat = QComboBox()
        self.combo_strat.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #ffaa44; border: 1px solid #ffaa44; border-radius: 4px; padding: 4px 8px; font-weight: bold; min-width: 320px; font-size: 9.5pt; }")
        top_bar.addWidget(self.combo_strat)

        btn_new_strat = QPushButton("➕ 新建策略")
        btn_new_strat.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_new_strat.setToolTip("基于标准阶梯模板创建一个全新独立策略")
        btn_new_strat.clicked.connect(self._on_create_new_strategy)
        top_bar.addWidget(btn_new_strat)

        btn_clone_strat = QPushButton("📑 复制策略")
        btn_clone_strat.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_clone_strat.setToolTip("以当前选中的策略为蓝本快速克隆一套新策略")
        btn_clone_strat.clicked.connect(self._on_clone_current_strategy)
        top_bar.addWidget(btn_clone_strat)

        btn_del_strat = QPushButton("🗑️ 删除策略")
        btn_del_strat.setStyleSheet("background-color: #3a1e1e; color: #ff6666; font-weight: bold; border: 1px solid #ff4444; border-radius: 4px; padding: 4px 10px; font-size: 9pt;")
        btn_del_strat.setToolTip("从列表中移除当前选中的策略配置")
        btn_del_strat.clicked.connect(self._on_delete_strategy)
        top_bar.addWidget(btn_del_strat)

        top_bar.addStretch()

        self.lbl_tips = QLabel("💡 提示：在下方可实时编辑策略规则，保存后即时生效落盘。")
        self.lbl_tips.setStyleSheet("color: #00ff88; font-size: 9pt;")
        top_bar.addWidget(self.lbl_tips)

        layout.addLayout(top_bar)

        # JSON 编辑框
        self.txt_json = QTextEdit()
        self.txt_json.setStyleSheet("background-color: #121218; color: #00ff88; font-family: Consolas, 'Courier New', Monospace; font-size: 10pt; line-height: 1.3;")
        layout.addWidget(self.txt_json, 1)

        # 底部按钮栏
        btn_layout = QHBoxLayout()
        btn_format = QPushButton("🔄 格式化校验")
        btn_format.setStyleSheet("background-color: #242436; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 6px 14px;")
        btn_format.clicked.connect(self._on_format)

        btn_save = QPushButton("💾 保存并应用")
        btn_save.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 6px 18px;")
        btn_save.clicked.connect(self._on_save)

        btn_close = QPushButton("取消/关闭")
        btn_close.setStyleSheet("background-color: #333344; color: white; border-radius: 4px; padding: 6px 14px;")
        btn_close.clicked.connect(self.reject)

        btn_layout.addWidget(btn_format)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

        # 确定初始选中的策略
        target_id = self.initial_strategy_id
        if not target_id and self.current_code:
            auto_st = self.engine.auto_select_strategy(0.0, code=self.current_code)
            if auto_st:
                target_id = auto_st.get("id")

        self.combo_strat.currentIndexChanged.connect(self._on_combo_strat_changed)
        self._refresh_combo_strat(select_id=target_id)

    def _refresh_combo_strat(self, select_id: Optional[str] = None):
        self.combo_strat.blockSignals(True)
        self.combo_strat.clear()

        strats = self._full_config_data.get("strategies", [])
        for st in strats:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            t_codes = st.get("target_codes", [])
            t_str = f" [标的: {', '.join(t_codes)}]" if t_codes else ""
            self.combo_strat.addItem(f"📋 {st_name}{t_str}", st_id)

        self.combo_strat.addItem("🌐 全部策略配置 (全量 JSON 文件)", "__ALL__")

        target_idx = 0
        if select_id:
            for i in range(self.combo_strat.count()):
                if self.combo_strat.itemData(i) == select_id:
                    target_idx = i
                    break

        self.combo_strat.setCurrentIndex(target_idx)
        self.combo_strat.blockSignals(False)
        self._switch_to_mode(self.combo_strat.itemData(target_idx))

    def _switch_to_mode(self, mode: str):
        self._current_selected_mode = mode
        if mode == "__ALL__":
            self.setWindowTitle("⚙️ 自定制分时交易策略编辑器 - 【全量 JSON 配置】")
            content_str = json.dumps(self._full_config_data, ensure_ascii=False, indent=2)
            self.txt_json.setPlainText(content_str)
        else:
            strats = self._full_config_data.get("strategies", [])
            target_st = next((s for s in strats if s.get("id") == mode), None)
            if target_st:
                st_name = target_st.get("name", mode)
                self.setWindowTitle(f"⚙️ 自定制分时交易策略编辑器 - 【{st_name}】")
                content_str = json.dumps(target_st, ensure_ascii=False, indent=2)
                self.txt_json.setPlainText(content_str)
            else:
                self.txt_json.setPlainText("{\n}")

    def _on_combo_strat_changed(self, index: int):
        mode = self.combo_strat.itemData(index)
        self._switch_to_mode(mode)

    def _on_create_new_strategy(self):
        """【➕ 新建策略】一键根据标准阶梯模板生成全新独立策略并进入编辑"""
        strats = self._full_config_data.setdefault("strategies", [])
        new_idx = len(strats) + 1
        ts_suffix = str(int(time.time()))[-4:]
        new_id = f"strategy_custom_{ts_suffix}"
        target_code_str = self.current_code if self.current_code else "688888"
        new_name = f"新股自定义阶梯策略 {new_idx}（{target_code_str}）"

        new_strat = {
            "id": new_id,
            "name": new_name,
            "target_codes": [target_code_str] if target_code_str else [],
            "description": "基于时间轴分批减仓与价格笼子挂单的自定制分时阶梯策略",
            "applicable_rules": {
                "open_price_ranges": [
                    {"name": "标准档", "min": 0.0, "max": 99999.0, "action_mode": "standard"}
                ]
            },
            "phases": [
                {
                    "phase_id": "call_auction",
                    "name": "9:15~9:25 集合竞价定盘",
                    "start_time": "09:15",
                    "end_time": "09:25",
                    "description": "记录开盘价 Open，判定价格所属档位，锁定执行策略",
                    "rules": []
                },
                {
                    "phase_id": "opening_surge",
                    "name": "9:30~10:00 开盘冲高卖出",
                    "start_time": "09:30",
                    "end_time": "10:00",
                    "description": "开盘后冲高分批卖出第一批仓位",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_surge_10",
                            "name": "规则1: 开盘冲高涨10%卖50%",
                            "condition_mode": "standard",
                            "trigger_expr": "price >= open_price * 1.10",
                            "sell_ratio": 0.5,
                            "order_type": "limit_price_cage",
                            "price_offset_ratio": 1.02,
                            "description": "较开盘涨10%以上，按当前买一价*1.02限价单卖出50%"
                        },
                        {
                            "rule_id": f"rule_s{new_idx}_timeout",
                            "name": "规则1兜底: 10:00整超时卖30%",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '10:00'",
                            "sell_ratio": 0.3,
                            "order_type": "market_price",
                            "description": "若10:00前未触发冲高条件，10:00整按市价卖出30%"
                        }
                    ]
                },
                {
                    "phase_id": "circuit_breaker",
                    "name": "9:30~15:00 临停复牌卖出",
                    "start_time": "09:30",
                    "end_time": "15:00",
                    "description": "触发较开盘价+30%临停复牌后卖出",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_halt_30",
                            "name": "规则2: 较开盘+30%临停复牌卖30%",
                            "condition_mode": "all",
                            "trigger_expr": "max_price >= open_price * 1.30",
                            "sell_ratio": 0.3,
                            "order_type": "limit",
                            "limit_price_expr": "open_price * 1.28",
                            "description": "复牌后3分钟内再卖30%，复牌前挂 Open*1.28 限价单"
                        }
                    ]
                },
                {
                    "phase_id": "closing_clearance",
                    "name": "14:50~14:57 尾盘清仓",
                    "start_time": "14:50",
                    "end_time": "14:57",
                    "description": "尾盘清仓剩余全部仓位",
                    "rules": [
                        {
                            "rule_id": f"rule_s{new_idx}_clear_all",
                            "name": "规则3: 尾盘市价清仓剩余",
                            "condition_mode": "all",
                            "trigger_expr": "current_time >= '14:50'",
                            "sell_ratio": 1.0,
                            "order_type": "market_price",
                            "description": "14:50~14:57 按买一价市价卖出剩余全部"
                        }
                    ]
                }
            ]
        }

        strats.append(new_strat)
        self._refresh_combo_strat(select_id=new_id)
        QMessageBox.information(self, "新建策略成功", f"✅ 已成功生成新策略【{new_name}】模板！\n可在下方直接调整参数与规则，修改后点击“保存并应用”即可生效。")

    def _on_clone_current_strategy(self):
        """【📑 复制策略】以当前选中的策略为基础克隆一份并直接切换至编辑"""
        if self._current_selected_mode == "__ALL__":
            QMessageBox.warning(self, "提示", "请在上方下拉列表中先选择一个具体策略，再进行复制克隆。")
            return

        strats = self._full_config_data.setdefault("strategies", [])
        target_st = next((s for s in strats if s.get("id") == self._current_selected_mode), None)
        if not target_st:
            QMessageBox.warning(self, "错误", "未找到要克隆的目标策略。")
            return

        cloned_strat = copy.deepcopy(target_st)
        ts_suffix = str(int(time.time()))[-4:]
        cloned_strat["id"] = f"{target_st.get('id', 'strat')}_copy_{ts_suffix}"
        cloned_strat["name"] = f"{target_st.get('name', '策略')} (副本)"
        
        strats.append(cloned_strat)
        self._refresh_combo_strat(select_id=cloned_strat["id"])
        QMessageBox.information(self, "克隆成功", f"✅ 已成功克隆策略【{cloned_strat['name']}】！\n可在下方直接修改配置。")

    def _on_delete_strategy(self):
        """【🗑️ 删除策略】从列表中安全移除当前选中的策略"""
        if self._current_selected_mode == "__ALL__":
            QMessageBox.warning(self, "提示", "全量配置文件不可直接删除！")
            return

        strats = self._full_config_data.get("strategies", [])
        if len(strats) <= 1:
            QMessageBox.warning(self, "提示", "当前只剩 1 套策略，不可继续删除，至少需要保留 1 套有效策略。")
            return

        target_st = next((s for s in strats if s.get("id") == self._current_selected_mode), None)
        if not target_st:
            return

        st_name = target_st.get("name", self._current_selected_mode)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除策略【{st_name}】吗？\n删除后点击“保存并应用”将永久生效。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._full_config_data["strategies"] = [s for s in strats if s.get("id") != self._current_selected_mode]
            next_select = self._full_config_data["strategies"][0].get("id") if self._full_config_data["strategies"] else "__ALL__"
            self._refresh_combo_strat(select_id=next_select)
            QMessageBox.information(self, "已移除", f"策略【{st_name}】已从临时列表中移除，点击“保存并应用”即可写入磁盘。")

    def _on_format(self):
        try:
            cur_text = self.txt_json.toPlainText()
            data = json.loads(cur_text)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            self.txt_json.setPlainText(formatted)
            QMessageBox.information(self, "格式正确", "✅ JSON 语法校验通过并已自动格式化排版！")
        except Exception as e:
            QMessageBox.critical(self, "JSON 语法错误", f"❌ JSON 解析失败，请检查语法:\n{e}")

    def _on_save(self):
        content = self.txt_json.toPlainText()
        try:
            parsed = json.loads(content)
        except Exception as e:
            QMessageBox.critical(self, "JSON 语法错误", f"❌ 解析 JSON 格式失败，请修正后再保存:\n{e}")
            return

        try:
            if self._current_selected_mode == "__ALL__":
                if not isinstance(parsed, dict) or "strategies" not in parsed:
                    QMessageBox.warning(self, "格式错误", "❌ 全量配置必须为包含 'strategies' 列表的 JSON 对象！")
                    return
                self._full_config_data = parsed
            else:
                if not isinstance(parsed, dict):
                    QMessageBox.warning(self, "格式错误", "❌ 单策略配置必须为 JSON 对象 (dict)！")
                    return
                st_id = parsed.get("id") or self._current_selected_mode
                parsed["id"] = st_id
                strats = self._full_config_data.setdefault("strategies", [])
                replaced = False
                for idx, s in enumerate(strats):
                    if s.get("id") == st_id or s.get("id") == self._current_selected_mode:
                        strats[idx] = parsed
                        replaced = True
                        break
                if not replaced:
                    strats.append(parsed)

            if self.engine.save_config(self._full_config_data):
                self.engine.load_config()
                QMessageBox.information(self, "成功", "✅ 策略配置更新成功并已物理落盘！")
                self.accept()
            else:
                QMessageBox.warning(self, "错误", "❌ 策略配置保存失败，请检查文件写入权限。")
        except Exception as e:
            QMessageBox.critical(self, "保存异常", f"❌ 保存策略配置失败:\n{e}")


class IntegratedTradingStrategyPanel(QWidget):
    """
    【核心】分时阶梯交易策略 & 7 节点动态评估一体化工作台 (Tab 1)
    整合开盘定盘、策略阶段推进、规则达成状态、价格笼子挂单、买卖点信号流水与 SBC 实盘走势
    """
    manual_score_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.tdx_fetcher = TDXRealtimeFetcher.get_instance()
        self.code = "688826"
        self._is_updating = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. 顶部：开盘定盘速查与实时评级诊断卡
        status_card = QGroupBox("📌 开盘定盘速查 & 7 节点动态时序评级诊断")
        status_card.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 4px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        status_layout = QGridLayout(status_card)
        status_layout.setContentsMargins(10, 10, 10, 8)
        status_layout.setSpacing(6)

        self.lbl_open_info = QLabel("开盘基准: -- 元 | 所属档位: --")
        self.lbl_open_info.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffd700;")

        self.lbl_strat_name = QLabel("当前策略: --")
        self.lbl_strat_name.setStyleSheet("font-size: 10pt; font-weight: bold; color: #38bdf8;")

        self.lbl_score_badge = QLabel("🏆 综合评级: -- 分 (形态: --) | 资金强度: --")
        self.lbl_score_badge.setStyleSheet("font-size: 10.5pt; font-weight: bold; color: #00ff88;")

        self.lbl_position_status = QLabel("📦 持仓状态: 剩余 100% | 买卖步数: 0 步")
        self.lbl_position_status.setStyleSheet("font-size: 10pt; font-weight: bold; color: #ffaa44;")

        status_layout.addWidget(self.lbl_open_info, 0, 0)
        status_layout.addWidget(self.lbl_strat_name, 0, 1)
        status_layout.addWidget(self.lbl_score_badge, 1, 0)
        status_layout.addWidget(self.lbl_position_status, 1, 1)

        main_layout.addWidget(status_card)

        # 2. 💡 盘中阶段自动解析与实操指引
        self.action_card = QGroupBox()
        self.action_card.setStyleSheet("""
            QGroupBox {
                border: 2px solid #00ff88;
                border-radius: 6px;
                margin-top: 4px;
                font-weight: bold;
                color: #00ff88;
                background-color: #101918;
            }
        """)
        action_layout = QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(8, 6, 8, 8)
        action_layout.setSpacing(4)

        action_header_lay = QHBoxLayout()
        lbl_action_head = QLabel("💡 盘中阶段自动解析与实操指引 (当前情况如何操作)")
        lbl_action_head.setStyleSheet("color: #00ff88; font-weight: bold; font-size: 9.5pt;")
        btn_open_sbc_win_top = QPushButton("📈 SBC 独立分时走势图")
        btn_open_sbc_win_top.setStyleSheet("background-color: #1e2638; color: #00ff88; font-weight: bold; border: 1.5px solid #00ff88; border-radius: 4px; padding: 2px 10px; font-size: 9pt;")
        btn_open_sbc_win_top.clicked.connect(self._on_open_sbc_chart_dialog)
        action_header_lay.addWidget(lbl_action_head)
        action_header_lay.addStretch()
        action_header_lay.addWidget(btn_open_sbc_win_top)
        action_layout.addLayout(action_header_lay)

        self.lbl_diagnosis = QLabel("⏳ 正在自动解析当前盘中阶段与行情特征...")
        self.lbl_diagnosis.setStyleSheet("color: #ffffff; font-size: 9.5pt; font-weight: bold;")
        self.lbl_diagnosis.setWordWrap(True)

        self.lbl_action = QLabel("【实操操作指引】--")
        self.lbl_action.setStyleSheet("color: #ffd700; font-size: 10pt; font-weight: bold; background: #1a221f; padding: 4px 8px; border-radius: 4px;")
        self.lbl_action.setWordWrap(True)

        action_layout.addWidget(self.lbl_diagnosis)
        action_layout.addWidget(self.lbl_action)
        main_layout.addWidget(self.action_card)

        # 3. 主分割器：左侧策略阶段与规则达成，右侧 SBC 实盘分时走势与指令流水
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ===== 左侧容器：时间轴策略阶段 + 规则达成表 + 7节点动态速查 =====
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 阶段指示 ScrollArea
        phase_box = QGroupBox("⏳ 盘中时间轴策略阶段 (结合 7 节点动态指示)")
        phase_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #aad4ff; background-color: #14141d; }")
        phase_box_layout = QVBoxLayout(phase_box)
        phase_box_layout.setContentsMargins(4, 8, 4, 4)

        self.phase_scroll = QScrollArea(self)
        self.phase_scroll.setWidgetResizable(True)
        self.phase_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.phase_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.scroll_content = QWidget(self.phase_scroll)
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(2, 2, 2, 2)
        self.scroll_layout.setSpacing(4)
        self.phase_scroll.setWidget(self.scroll_content)
        phase_box_layout.addWidget(self.phase_scroll)
        phase_box.setMinimumHeight(140)
        left_layout.addWidget(phase_box, 1)

        # 规则达成表格
        rule_box = QGroupBox("🔍 策略规则条件达成与挂单监控")
        rule_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #00ff88; background-color: #14141d; }")
        rule_box_layout = QVBoxLayout(rule_box)
        rule_box_layout.setContentsMargins(4, 8, 4, 4)

        self.table_rules = QTableWidget()
        self.table_rules.setColumnCount(5)
        self.table_rules.setHorizontalHeaderLabels(["规则名称", "目标触发条件", "卖出比例", "建议挂单价", "触发状态"])
        self.table_rules.setAlternatingRowColors(True)
        self.table_rules.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_rules.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #00ff88; font-weight: bold; padding: 3px; }")

        h_r = self.table_rules.horizontalHeader()
        h_r.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_r.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_r.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_r.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_r.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table_rules.setColumnWidth(0, 130)
        self.table_rules.setColumnWidth(3, 85)
        bind_table_column_persistence(self.table_rules, "tab1_table_rules_col_widths")
        self.table_rules.cellDoubleClicked.connect(lambda r, c: handle_table_cell_double_click(self.table_rules, r, c, self))

        rule_box_layout.addWidget(self.table_rules)
        rule_box.setMinimumHeight(130)
        left_layout.addWidget(rule_box, 1)

        # 7 节点动态评估速查表 (输入价格校准自动评分)
        node_box = QGroupBox("🎯 7 节点时序评估 (根据当时价格/换手自动评分，数据异常可手动输入价格校准)")
        node_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_box_layout = QVBoxLayout(node_box)
        node_box_layout.setContentsMargins(4, 8, 4, 4)

        node_header_lay = QHBoxLayout()
        lbl_node_hint = QLabel("💡 评分由系统根据价格全自动评估；若行情出错可在【校准价格/换手】列输入真实价格。")
        lbl_node_hint.setStyleSheet("color: #00ff88; font-size: 8pt;")
        btn_reset_node_params = QPushButton("🔄 重置校准")
        btn_reset_node_params.setStyleSheet("background-color: #222232; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 1px 6px; font-size: 8pt;")
        btn_reset_node_params.clicked.connect(self._on_reset_node_custom_params)
        node_header_lay.addWidget(lbl_node_hint)
        node_header_lay.addStretch()
        node_header_lay.addWidget(btn_reset_node_params)
        node_box_layout.addLayout(node_header_lay)

        self.table_quick_nodes = QTableWidget()
        self.table_quick_nodes.setColumnCount(7)
        self.table_quick_nodes.setHorizontalHeaderLabels(["节点", "时间", "校准价格/换手", "特征观察解析", "信号判定", "自动评分", "权重"])
        self.table_quick_nodes.setAlternatingRowColors(True)
        self.table_quick_nodes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_quick_nodes.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #ffd700; font-weight: bold; padding: 3px; }")

        h_q = self.table_quick_nodes.horizontalHeader()
        h_q.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_q.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_q.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        h_q.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_quick_nodes.setColumnWidth(2, 95)

        bind_table_column_persistence(self.table_quick_nodes, "tab1_table_quick_nodes_col_widths")
        self.table_quick_nodes.cellDoubleClicked.connect(lambda r, c: handle_table_cell_double_click(self.table_quick_nodes, r, c, self))

        node_box_layout.addWidget(self.table_quick_nodes)
        node_box.setMinimumHeight(150)
        left_layout.addWidget(node_box, 1)

        self.main_splitter.addWidget(left_container)

        # ===== 右侧容器：SBC 实盘走势 + 买卖点触发明细 + 执行流水日志 =====
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # SBC 分时走势卡片
        sbc_box = QGroupBox("📊 SBC 实盘分时走势与关键阶梯基准线")
        sbc_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #00ff88; background-color: #14141d; }")
        sbc_box_layout = QVBoxLayout(sbc_box)
        sbc_box_layout.setContentsMargins(6, 8, 6, 6)

        self.txt_sbc_info = QTextEdit()
        self.txt_sbc_info.setReadOnly(True)
        self.txt_sbc_info.setStyleSheet("background-color: #0e0e14; color: #38bdf8; font-family: Consolas, Monospace; font-size: 9.5pt;")
        sbc_box_layout.addWidget(self.txt_sbc_info)
        sbc_box.setMinimumHeight(180)
        right_layout.addWidget(sbc_box, 1)

        # 买卖点明细表
        sig_box = QGroupBox("⚡ 策略执行买卖点明细 (实盘/模拟/推演触发)")
        sig_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #ffaa44; background-color: #14141d; }")
        sig_box_layout = QVBoxLayout(sig_box)
        sig_box_layout.setContentsMargins(4, 8, 4, 4)

        self.table_signals = QTableWidget()
        self.table_signals.setColumnCount(5)
        self.table_signals.setHorizontalHeaderLabels(["时间", "买卖动作", "执行价", "卖出比例", "触发规则/理由"])
        self.table_signals.setAlternatingRowColors(True)
        self.table_signals.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_signals.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 8.5pt; } QHeaderView::section { background-color: #1a1a26; color: #ffaa44; font-weight: bold; padding: 3px; }")

        h_s = self.table_signals.horizontalHeader()
        h_s.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_s.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        bind_table_column_persistence(self.table_signals, "tab1_table_signals_col_widths")
        self.table_signals.cellDoubleClicked.connect(lambda r, c: handle_table_cell_double_click(self.table_signals, r, c, self))
        sig_box_layout.addWidget(self.table_signals)
        sig_box.setMinimumHeight(130)
        right_layout.addWidget(sig_box, 1)

        # 路由日志
        log_box = QGroupBox("📋 策略路由与实盘指令流水日志")
        log_box.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        log_box_layout = QVBoxLayout(log_box)
        log_box_layout.setContentsMargins(4, 8, 4, 4)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setStyleSheet("background-color: #0e0e14; color: #00ff88; font-family: Consolas, Monospace; font-size: 9pt;")
        log_box_layout.addWidget(self.txt_log)
        log_box.setMinimumHeight(110)
        right_layout.addWidget(log_box, 1)

        self.main_splitter.addWidget(right_container)

        # 4. 从 QSettings 物理持久化恢复 Splitter 左右分割位置
        settings = QSettings("pyQuant3", "IntradayWorkbench")
        splitter_state = settings.value("main_splitter_state")
        if splitter_state:
            self.main_splitter.restoreState(splitter_state)
        else:
            self.main_splitter.setSizes([600, 620])

        self.main_splitter.splitterMoved.connect(self._save_splitter_state)
        main_layout.addWidget(self.main_splitter, 1)

        self.phase_items = []
        self._last_strategy_id = None

    def _save_splitter_state(self):
        """【💾 物理持久化】实时保存 Splitter 分割布局位置到 QSettings"""
        settings = QSettings("pyQuant3", "IntradayWorkbench")
        settings.setValue("main_splitter_state", self.main_splitter.saveState())

    def _on_reset_node_custom_params(self):
        self.engine.reset_node_custom_params(self.code)
        self.manual_score_signal.emit()

    def _rebuild_phase_items(self, strategy: Dict[str, Any]):
        st_id = strategy.get("id") if isinstance(strategy, dict) else None
        if getattr(self, "_last_strategy_id", None) == st_id and self.phase_items:
            return
        self._last_strategy_id = st_id

        # 记录滚动位置
        sb = self.phase_scroll.verticalScrollBar()
        old_val = sb.value()

        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        self.phase_items = []
        phases = strategy.get("phases", []) if isinstance(strategy, dict) else []

        if not phases:
            phase_defs = [
                ("09:15~09:25", "1️⃣ 集合竞价定盘段", "记录开盘价 Open，判定所属档位并锁定策略 (权重15%)"),
                ("09:30~10:00", "2️⃣ 开盘冲高卖出段", "冲高≥10%按价格笼子卖50%，10:00前未触发兜底卖30% (权重35%)"),
                ("10:00~15:00", "3️⃣ 临停复牌/持股观察段", "+30%临停复牌前挂1.28x卖30% / 回撤10%移动止盈 (权重25%)"),
                ("14:50~14:57", "4️⃣ 尾盘决策/清仓段", "收盘/最高>=90%且>=8分留10%底仓过夜，否则全部清仓 (权重25%)")
            ]
        else:
            num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
            phase_defs = []
            for idx, p in enumerate(phases):
                s_t = str(p.get("start_time", "") or "")
                e_t = str(p.get("end_time", "") or "")
                t_range = str(p.get("time_range", "") or "")
                if not t_range:
                    t_range = f"{s_t}~{e_t}" if (s_t and e_t) else f"阶段 {p.get('phase_id', idx+1)}"
                p_name = str(p.get("name", f"阶段 {idx+1}"))
                emoji = num_emojis[idx] if idx < len(num_emojis) else f"{idx+1}️⃣"
                if not any(char in p_name for char in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]):
                    p_name = f"{emoji} {p_name}"
                p_desc = str(p.get("description") or p.get("action_guidance") or "")
                phase_defs.append((str(t_range), str(p_name), str(p_desc)))

        for idx, (time_range, phase_title, phase_desc) in enumerate(phase_defs):
            p_box = QFrame(self.scroll_content)
            p_box.setObjectName("PhaseItemFrame")
            p_box.setMinimumHeight(44)
            p_box.setStyleSheet("QFrame#PhaseItemFrame { background-color: #14141c; border: 1px solid #22222d; border-radius: 4px; } QLabel { border: none; background: transparent; }")
            p_layout = QVBoxLayout(p_box)
            p_layout.setContentsMargins(6, 4, 6, 4)
            p_layout.setSpacing(2)

            h_lay = QHBoxLayout()
            h_lay.setContentsMargins(0, 0, 0, 0)

            lbl_time = QLabel(str(time_range))
            lbl_time.setStyleSheet("font-weight: bold; color: #ffaa44; font-size: 8.5pt;")
            lbl_title = QLabel(str(phase_title))
            lbl_title.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 8.5pt;")
            lbl_status = QLabel("⏳ 待生效")
            lbl_status.setStyleSheet("font-weight: bold; color: #555566; font-size: 8pt;")

            h_lay.addWidget(lbl_time)
            h_lay.addWidget(lbl_title)
            h_lay.addStretch()
            h_lay.addWidget(lbl_status)

            lbl_sub = QLabel(str(phase_desc))
            lbl_sub.setStyleSheet("color: #8e8e9e; font-size: 8pt;")

            p_layout.addLayout(h_lay)
            p_layout.addWidget(lbl_sub)
            self.scroll_layout.addWidget(p_box)

            self.phase_items.append({
                "frame": p_box,
                "lbl_time": lbl_time,
                "lbl_title": lbl_title,
                "lbl_status": lbl_status,
                "lbl_desc": lbl_sub
            })

        sb.setValue(old_val)

    def update_data(
        self,
        code: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float,
        turnover_rate: float,
        amount: float,
        bid1_price: float,
        current_time_str: str,
        strategy: Dict[str, Any],
        is_unlisted: bool = False,
        last_close: Optional[float] = None
    ):
        """全面刷新一体化工作台数据（带滚动条位置锁定保护）"""
        self.code = code
        c_clean = str(code).zfill(6)

        strat_id = strategy.get("id", "") if strategy else ""
        strat_type = strategy.get("strategy_type", "") if strategy else ""
        target_newstock_codes = self.engine.get_all_target_codes()
        has_stock_spec = bool(strategy and ("stock_spec" in strategy or strategy.get("schema_version") == "v1.0-unified"))
        is_daily_strategy = (
            strat_type in ("daily_surge", "general", "daily")
            or "daily" in strat_id
            or "surge" in strat_id
            or (not has_stock_spec and c_clean not in target_newstock_codes)
        )

        # 1. 评估 7 节点动态打分与形态
        eval_res = self.engine.evaluate_seven_nodes(
            code=c_clean,
            current_time_str=current_time_str,
            open_price=open_price,
            price=price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap,
            turnover_rate=turnover_rate,
            amount=amount,
            strategy_id=strat_id,
            last_close=last_close
        )

        tot_score = eval_res.get("total_weighted_score", 0.0)
        pattern = eval_res.get("pattern", "--")
        intensity_val = eval_res.get("intensity_ratio", 0.0)
        state = self.engine._get_stock_state(c_clean, open_price)
        rem_ratio = float(state.get("remaining_ratio", state.get("remaining_position_ratio", 1.0)))
        signals = state.get("signals", [])
        logs = state.get("execution_logs", [])

        # 🛡️ 待上市新股持仓与信号绝对纯净保护
        if is_unlisted:
            signals = []
            logs = []
            rem_ratio = 1.0
            state["signals"] = []
            state["triggered_rules"] = set()
            state["remaining_ratio"] = 1.0
            state["remaining_position_ratio"] = 1.0
            state["execution_logs"] = []
        elif signals:
            tot_sold = sum(
                float(getattr(s, "sell_ratio", 0.0) or (s.debug_info.get("sell_ratio", 0.0) if hasattr(s, "debug_info") and isinstance(s.debug_info, dict) else 0.0))
                for s in signals
            )
            if tot_sold > 0:
                rem_ratio = max(0.0, min(rem_ratio, 1.0 - tot_sold))
                state["remaining_ratio"] = rem_ratio
                state["remaining_position_ratio"] = rem_ratio

        # 2. 顶部状态卡
        tier_name, _, _ = self.engine.get_open_price_tier(open_price, code=c_clean)
        
        if is_unlisted:
            issue_p = float(strategy.get("stock_spec", {}).get("issue_price", open_price) or open_price)
            self.lbl_open_info.setText(f"💡 【待上市新股】发行基准: {issue_p:.2f}元 (尚未挂牌) | 估价档位: {tier_name} | 估价现价: {price:.2f}元")
            self.lbl_strat_name.setText(f"当前策略: {strategy.get('name', '专属上市阶梯策略')}")
            self.lbl_score_badge.setText(
                f"🏆 综合评级: <font color='#00ff88'>{tot_score:.2f}分</font> (形态: <font color='#ffd700'>【待上市估价】</font>) | 发行价: {issue_p:.2f}元"
            )
            self.lbl_position_status.setText(
                f"📦 标的状态: <font color='#38bdf8'><b>待上市挂牌</b></font> | 估价推演就绪"
            )
            self.lbl_diagnosis.setText(f"⏱️ [{current_time_str}] 【待上市新股】尚未正式挂牌上市交易，已为您自动载入发行基准价 ({issue_p:.2f}元)。")
            self.lbl_action.setText("【待上市估价推演】当前标的处于待上市阶段，系统已配置发行价与阶梯估价模型。您可开启顶部【💡 开启手动估价】自由推演 7 节点买卖点。")
        else:
            if is_daily_strategy:
                open_gain_str = f" (今开幅: {((open_price-last_close)/last_close*100):+.2f}%)" if (last_close and last_close > 0 and open_price > 0) else ""
                self.lbl_open_info.setText(f"开盘基准: {open_price:.2f}元{open_gain_str} | 现价: {price:.2f}元 | VWAP: {vwap:.2f}元")
            else:
                self.lbl_open_info.setText(f"开盘基准: {open_price:.2f}元 | 所属档位: {tier_name} | 现价: {price:.2f}元 | VWAP: {vwap:.2f}元")

            self.lbl_strat_name.setText(f"当前策略: {strategy.get('name', '默认策略')}")
            self.lbl_score_badge.setText(
                f"🏆 综合评级: <font color='#00ff88'>{tot_score:.2f}分</font> (形态: <font color='#ffd700'>【{pattern}】</font>) | 资金强度: {intensity_val:.2f}x"
            )
            pos_color_top = "#00ff88" if rem_ratio > 0.3 else ("#ffd700" if rem_ratio > 0.001 else "#ff5555")
            pos_suffix_top = " (已清仓)" if rem_ratio <= 0.001 else ""
            self.lbl_position_status.setText(
                f"📦 持仓状态: 剩余 <font color='{pos_color_top}'><b>{rem_ratio*100:.0f}%</b>{pos_suffix_top}</font> | 已触发: {len(signals)} 步买卖"
            )
            self.lbl_diagnosis.setText(f"⏱️ [{current_time_str}] {eval_res.get('current_status_diagnosis', '')}")
            self.lbl_action.setText(eval_res.get("action_execution_text", ""))

        # 4. 时间轴策略阶段高亮（带滚动条位置锁定）
        sb_phase = self.phase_scroll.verticalScrollBar()
        old_phase_pos = sb_phase.value()
        self._rebuild_phase_items(strategy)

        clean_t = current_time_str[-8:] if len(current_time_str) >= 8 else current_time_str
        if len(clean_t) > 5 and ":" in clean_t:
            clean_t = clean_t[:5]

        curr_phase, curr_phase_idx = self.engine.get_current_phase(clean_t, strategy)
        for idx, item in enumerate(self.phase_items):
            if idx == curr_phase_idx:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #1e2638; border: 2px solid #38bdf8; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("🔥 执行中")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #00ff88; font-size: 8pt;")
            elif idx < curr_phase_idx:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #161822; border: 1px solid #2a2a3a; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("✅ 已完成")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #8e8e93; font-size: 8pt;")
            else:
                item["frame"].setStyleSheet("QFrame#PhaseItemFrame { background-color: #12121a; border: 1px solid #20202c; border-radius: 4px; } QLabel { border: none; background: transparent; }")
                item["lbl_status"].setText("⏳ 待生效")
                item["lbl_status"].setStyleSheet("font-weight: bold; color: #555566; font-size: 8pt;")

        sb_phase.setValue(old_phase_pos)

        # 5. 规则达成表格（带滚动条锁定）
        sb_rules = self.table_rules.verticalScrollBar()
        old_rule_pos = sb_rules.value()

        if curr_phase:
            rules = curr_phase.get("rules", [])
            triggered_rules = state.get("triggered_rules", set())
            if self.table_rules.rowCount() != len(rules):
                self.table_rules.setRowCount(len(rules))

            for row, r in enumerate(rules):
                r_id = r.get("rule_id", "")
                r_name = r.get("name", r_id)
                r_ratio = f"{r.get('sell_ratio', 0.0)*100:.0f}%"

                if open_price > 0:
                    if r_id in ["rule_a1_surge", "rule_pz_surge_10"]:
                        target_str = f"≥ {open_price*1.10:.2f}元 (+10%)"
                        sugg_p = f"{round((bid1_price if bid1_price>0 else price)*1.02, 2):.2f}元"
                    elif r_id in ["rule_a2_halt_30", "rule_pz_halt_30"]:
                        target_str = f"最高 ≥ {open_price*1.30:.2f}元 (+30%)"
                        sugg_p = f"{round(open_price*1.28, 2):.2f}元"
                    elif is_daily_strategy and ("surge" in r_id or "profit" in r_id):
                        target_str = r.get("trigger_expr", f"冲高 ≥ {open_price*1.03:.2f}元")
                        sugg_p = f"{price:.2f}元(市价)"
                    else:
                        target_str = r.get("trigger_expr", "--")
                        sugg_p = f"{price:.2f}元(市价)"
                else:
                    target_str = r.get("trigger_expr", "--")
                    sugg_p = "--"

                status_str = "✅ 已触发卖出" if r_id in triggered_rules else "⏳ 监控中"
                status_color = "#00ff88" if r_id in triggered_rules else "#ffaa44"

                _set_or_update_table_item(self.table_rules, row, 0, r_name)
                _set_or_update_table_item(self.table_rules, row, 1, target_str)
                _set_or_update_table_item(self.table_rules, row, 2, r_ratio, align=Qt.AlignmentFlag.AlignCenter)
                _set_or_update_table_item(self.table_rules, row, 3, sugg_p, fg_color="#ffd700")
                _set_or_update_table_item(self.table_rules, row, 4, status_str, fg_color=status_color)

        sb_rules.setValue(old_rule_pos)

        # 6. 7 节点动态打分速查表（带滚动条锁定 & 价格校准自动评分）
        sb_quick = self.table_quick_nodes.verticalScrollBar()
        old_quick_pos = sb_quick.value()

        node_results = eval_res.get("node_results", [])
        if self.table_quick_nodes.rowCount() != len(node_results):
            self.table_quick_nodes.setRowCount(len(node_results))

        self._is_updating = True
        for row, nr in enumerate(node_results):
            judg_color = "#00ff88" if nr["judgment"] == "强" else ("#38bdf8" if nr["judgment"] == "中" else "#ff5555")
            _set_or_update_table_item(self.table_quick_nodes, row, 0, nr["name"])
            _set_or_update_table_item(self.table_quick_nodes, row, 1, nr["time_str"])

            # 列 2: 价格/换手校准输入框 (QDoubleSpinBox)
            unit_str = nr.get("input_unit", "元")
            input_v = float(nr.get("input_val", 0.0))
            spin = self.table_quick_nodes.cellWidget(row, 2)
            if not isinstance(spin, QDoubleSpinBox):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 5000.0)
                spin.setSingleStep(1.0 if unit_str == "%" else 5.0)
                spin.setSuffix(f" {unit_str}")
                spin.setStyleSheet("background-color: #1a1a26; color: #ffd700; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px;")
                spin.valueChanged.connect(self._make_param_spin_handler(row, nr["node_id"]))
                self.table_quick_nodes.setCellWidget(row, 2, spin)

            spin.blockSignals(True)
            spin.setSuffix(f" {unit_str}")
            spin.setValue(input_v)
            spin.blockSignals(False)

            # 列 3: 特征解析观察值
            _set_or_update_table_item(self.table_quick_nodes, row, 3, nr["observed_val"], tooltip=nr["observed_val"])

            # 列 4: 信号判定
            _set_or_update_table_item(self.table_quick_nodes, row, 4, nr["judgment"], fg_color=judg_color, align=Qt.AlignmentFlag.AlignCenter)

            # 列 5: 自动评分展示 (不可手动乱改，由价格严谨推导)
            score_fg = "#00ff88" if nr["final_score"] >= 8.0 else ("#38bdf8" if nr["final_score"] >= 6.0 else "#ff5555")
            _set_or_update_table_item(self.table_quick_nodes, row, 5, f"{nr['final_score']:.1f}分", fg_color=score_fg, font=QFont("Arial", 9, QFont.Weight.Bold), align=Qt.AlignmentFlag.AlignCenter)

            # 列 6: 权重
            _set_or_update_table_item(self.table_quick_nodes, row, 6, nr["weight_pct"], align=Qt.AlignmentFlag.AlignCenter)

        sb_quick.setValue(old_quick_pos)
        self._is_updating = False

        # 7. SBC 实盘走势与基准线 (100% 策略与标的自适应)
        strat_name = strategy.get("name", "分时阶梯策略") if strategy else "分时阶梯策略"
        spec = self.engine.get_stock_ladder_spec(code)
        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        if issue_p <= 0:
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
                if code in ipo_dict:
                    issue_p = float(ipo_dict[code].get("issue_price", 0.0) or 0.0)
            except Exception:
                pass
        float_mv_yi = float(spec.get("float_mv_yi", 14.24))

        # 获取昨日真实 OHLC (昨开、昨高、昨低、昨收)
        y_ohlc = self.tdx_fetcher.get_yesterday_ohlc(code) if hasattr(self, 'tdx_fetcher') and self.tdx_fetcher else {}
        y_open = y_ohlc.get("open", 0.0)
        y_high = y_ohlc.get("high", 0.0)
        y_low = y_ohlc.get("low", 0.0)
        y_close = y_ohlc.get("close", last_close if (last_close and last_close > 0) else 0.0)
        if y_close <= 0 and last_close and last_close > 0:
            y_close = last_close

        # 今日真实最高最低校准 (优先使用传入快照与今日分时校验后的极值，杜绝昨日极值残留)
        cur_snap_h = high_price if (high_price and high_price > 0) else price
        cur_snap_l = low_price if (low_price and low_price > 0) else price
        max_p = state.get("max_price", cur_snap_h)
        min_p = state.get("min_price", cur_snap_l)
        if cur_snap_h > 0 and (max_p <= 0 or max_p > cur_snap_h * 1.15 or max_p < cur_snap_h * 0.85):
            max_p = cur_snap_h
        if cur_snap_l > 0 and (min_p <= 0 or min_p < cur_snap_l * 0.85 or min_p > cur_snap_l * 1.15):
            min_p = cur_snap_l

        red = "#ff5555"
        gold = "#ffd700"
        cyan = "#38bdf8"
        green = "#00ff88"

        # 🛡️ 识别新股首日保护模式 (100% 由策略引擎权威判定，绝不因盘前缺少昨日数据而误判)
        is_first_listing_day = bool(self.engine.is_stock_first_listing_day(code))

        if is_unlisted:
            # 💡 【待上市新股展示模式】：尚未上市挂牌，以发行价与阶梯推演为主
            op_line_str = f"【开盘基准】: 发行基准价: <font color='{gold}'><b>{issue_p:.2f} 元</b></font> <font color='{cyan}'>(尚未上市挂牌·估价模式)</font><br/>"
            hl_line_str = f"【挂牌状态】: <font color='#ffd700'><b>待上市阶段</b></font> (发行价: <font color='{gold}'><b>{issue_p:.2f}元</b></font> | 估价推演就绪)<br/>"
        elif is_first_listing_day:
            # 🛡️ 【新股首日保护模式】：无昨日数据，以真实发行价 issue_p 与今日开盘价 open_price 为锚
            base_ref_p = issue_p if issue_p > 0 else (open_price if open_price > 0 else price)

            # 1. 今开 vs 发行价 (高开溢价为红，破发为绿)
            col_open = red if (open_price >= base_ref_p) else green
            op_gain_pct = ((open_price - base_ref_p) / base_ref_p * 100.0) if base_ref_p > 0 else 0.0
            col_op_pct = red if op_gain_pct >= 0 else green

            # 2. 最高价 vs 今日开盘价 (突破开盘价冲高为红，未超开盘为绿)
            col_high = red if (max_p > open_price and open_price > 0) else green

            # 3. 最低价 vs 今日开盘价 (日内从未跌破开盘价为红/极强，跌破开盘价为绿/防守)
            col_low = red if (min_p >= open_price and open_price > 0) else green

            # 4. 现价 vs 今日开盘价 (在开盘价上方为红，在开盘价下方为绿)
            col_price = red if (price >= open_price and open_price > 0) else green

            op_line_str = f"【开盘基准】: 今开: <font color='{col_open}'><b>{open_price:.2f} 元</b></font> <font color='{col_op_pct}'>({op_gain_pct:+.2f}%)</font> (发行价基准: <font color='{gold}'><b>{issue_p:.2f}元</b></font> | 首日挂牌无昨开)<br/>"
            hl_line_str = f"【实时成交】: <font color='{col_price}'><b>{price:.2f} 元</b></font>(最高: <font color='{col_high}'><b>{max_p:.2f}元</b></font> / 最低: <font color='{col_low}'><b>{min_p:.2f}元</b></font> | 首日对标开盘价)<br/>"
        else:
            # 📈 【常规多日对比模式】：已有昨日真实 OHLC
            lc_val = y_close if y_close > 0 else (last_close if (last_close and last_close > 0) else open_price)

            # 1. 开盘价：若 >= 昨开 (或昨收) 显示红，低于昨开显示绿
            if y_open > 0:
                col_open = red if (open_price >= y_open) else green
            else:
                col_open = red if (open_price >= lc_val) else green

            # 2. 最高价：若 >= 昨高 显示红 (突破昨高/强势新高)，低于昨高显示绿
            if y_high > 0:
                col_high = red if (max_p >= y_high) else green
            else:
                col_high = red if (max_p >= open_price) else green

            # 3. 最低价：若 >= 昨低 显示红 (低点抬升/未破昨低/强势防守)，低于昨低显示绿 (破位创新低)
            if y_low > 0:
                col_low = red if (min_p >= y_low) else green
            else:
                col_low = red if (min_p >= open_price) else green

            # 4. 现价：若 >= 昨收 显示红，低于昨收显示绿
            col_price = red if (price >= lc_val) else green

            # 格式化昨日关键位对比片段
            y_open_str = f" | 昨开: <font color='{gold}'><b>{y_open:.2f}元</b></font>" if y_open > 0 else ""

            lc_str = f"<font color='{gold}'><b>{lc_val:.2f} 元</b></font>" if lc_val > 0 else f"<font color='{gold}'><b>{open_price:.2f} 元</b></font>"
            op_pct_val = ((open_price - lc_val) / lc_val * 100.0) if lc_val > 0 else 0.0
            col_op_pct = red if op_pct_val >= 0 else green
            op_line_str = f"【开盘基准】: 今开: <font color='{col_open}'><b>{open_price:.2f} 元</b></font> <font color='{col_op_pct}'>({op_pct_val:+.2f}%)</font> (昨收基准: {lc_str}{y_open_str})<br/>"
            
            if y_high > 0 and y_low > 0:
                hl_line_str = (
                    f"【实时成交】: <font color='{col_price}'><b>{price:.2f} 元</b></font>"
                    f"(最高: <font color='{col_high}'><b>{max_p:.2f}元</b></font> |昨高:<font color='{gold}'><b>{y_high:.2f}元</b></font> /"
                    f"最低: <font color='{col_low}'><b>{min_p:.2f}元</b></font> |昨低: <font color='{gold}'><b>{y_low:.2f}元</b></font>)<br/>"
                )
            else:
                hl_line_str = f"【实时成交】: <font color='{col_price}'><b>{price:.2f} 元</b></font>(最高: <font color='{col_high}'><b>{max_p:.2f}元</b></font> / 最低: <font color='{col_low}'><b>{min_p:.2f}元</b></font>)<br/>"

        col_pos_sbc = green if rem_ratio > 0.3 else (gold if rem_ratio > 0.001 else "#ff5555")
        pos_suffix_sbc = " (已分批止盈/清仓完毕)" if rem_ratio <= 0.001 else ""
        if is_daily_strategy:
            sbc_html = (
                f"<div style='font-family: Consolas, Microsoft YaHei; font-size: 9.5pt; line-height: 1.5; color: #e0e0e0;'>"
                f"=== 📊 <font color='{cyan}'><b>【{code} {resolve_stock_name(code)}】{strat_name}</b></font> ===<br/>"
                f"{op_line_str}"
                f"{hl_line_str}"
                f"【均价线 VWAP】: <font color='{gold}'><b>{vwap:.2f} 元</b></font> | 换手率: <font color='{cyan}'><b>{turnover_rate:.2f}%</b></font> | 成交额: <font color='{gold}'><b>{amount/1e8:.2f} 亿元</b></font> (流通市值:{float_mv_yi:.1f}亿)<br/>"
                f"【冲高卖出目标 (+3%~+5%)】: <font color='{red}'><b>{open_price*1.03:.2f} ~ {open_price*1.05:.2f} 元</b></font> (冲高分批止盈 30%)<br/>"
                f"【破分时均线止损/减仓】: <font color='{red}'><b>{vwap:.2f} 元</b></font> (跌破分时均价线 VWAP 触发减仓)<br/>"
                f"【移动止盈清仓 (-3%~-5%)】: <font color='{red}'><b>{max_p*0.96:.2f} 元</b></font> (日内高点回撤触发)<br/>"
                f"【当前持仓管理】: 剩余持仓比例 <font color='{col_pos_sbc}'><b>{rem_ratio*100:.0f}%</b>{pos_suffix_sbc}</font><br/>"
                f"</div>"
            )
        else:
            sbc_html = (
                f"<div style='font-family: Consolas, Microsoft YaHei; font-size: 9.5pt; line-height: 1.5; color: #e0e0e0;'>"
                f"=== 📊 <font color='{cyan}'><b>【{code} {resolve_stock_name(code)}】{strat_name}</b></font> ===<br/>"
                f"{op_line_str}"
                f"{hl_line_str}"
                f"【均价线 VWAP】: <font color='{gold}'><b>{vwap:.2f} 元</b></font> | 换手率: <font color='{cyan}'><b>{turnover_rate:.1f}%</b></font> | 成交额: <font color='{gold}'><b>{amount/1e8:.2f} 亿元</b></font> (流通市值:{float_mv_yi:.1f}亿)<br/>"
                f"【冲高卖出目标 (+10%)】: <font color='{red}'><b>{open_price*1.10:.2f} 元</b></font> (价格笼子限价卖出 50%)<br/>"
                f"【临停触发目标 (+30%)】: <font color='{red}'><b>{open_price*1.30:.2f} 元</b></font> (复牌前挂单 1.28x=<font color='{red}'><b>{open_price*1.28:.2f}</b></font> 卖出 30%)<br/>"
                f"【移动止盈清仓 (-10%)】: <font color='{red}'><b>{max_p*0.90:.2f} 元</b></font> (高点回撤 10% 触发)<br/>"
                f"【当前持仓管理】: 剩余持仓比例 <font color='{col_pos_sbc}'><b>{rem_ratio*100:.0f}%</b>{pos_suffix_sbc}</font><br/>"
                f"</div>"
            )

        if self.txt_sbc_info.toHtml() != sbc_html:
            sb_sbc = self.txt_sbc_info.verticalScrollBar()
            saved_sbc_pos = sb_sbc.value()
            self.txt_sbc_info.setHtml(sbc_html)
            sb_sbc.setValue(saved_sbc_pos)

        # 8. 买卖点明细表（带滚动条锁定）
        sb_sig = self.table_signals.verticalScrollBar()
        old_sig_pos = sb_sig.value()

        if self.table_signals.rowCount() != len(signals):
            self.table_signals.setRowCount(len(signals))

        for r, s in enumerate(signals):
            pct_str = f"{getattr(s, 'sell_ratio', 0.5)*100:.0f}%"
            sugg_p = getattr(s, 'suggested_price', s.price)
            _set_or_update_table_item(self.table_signals, r, 0, s.timestamp)
            _set_or_update_table_item(self.table_signals, r, 1, "🔴 卖出", fg_color="#ff5555", font=QFont("Arial", 9, QFont.Weight.Bold))
            _set_or_update_table_item(self.table_signals, r, 2, f"{s.price:.2f}元 (挂单:{sugg_p:.2f})", fg_color="#ffd700")
            _set_or_update_table_item(self.table_signals, r, 3, pct_str, align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_signals, r, 4, s.reason, tooltip=s.reason)

        sb_sig.setValue(old_sig_pos)

        # 9. 路由日志 (带文本脏检查与滚动条锁定)
        new_log_text = "\n".join(logs) if logs else ""
        if self.txt_log.toPlainText() != new_log_text:
            sb_log = self.txt_log.verticalScrollBar()
            saved_log_pos = sb_log.value()
            self.txt_log.setPlainText(new_log_text)
            sb_log.setValue(saved_log_pos)

    def _on_open_sbc_chart_dialog(self):
        """【📈 打开/激活 SBC 独立分时走势图窗口】支持多标的多窗口并行对比观察，非模态、非置顶"""
        code = getattr(self, 'code', getattr(self, '_current_stock_code', '688826'))
        open_sbc_chart_dialog(self, code)

    def _make_param_spin_handler(self, row: int, node_id: str):
        def _handler(val: float):
            if not self._is_updating:
                self.engine.set_node_custom_param(self.code, node_id, val)
                # 反向同步到顶部的估价微调控件 (DoubleSpinBox)
                parent = self.parent()
                while parent:
                    if hasattr(parent, 'spin_eval_open') and hasattr(parent, 'spin_eval_price'):
                        if node_id == "node_1_auction":
                            parent.spin_eval_open.blockSignals(True)
                            parent.spin_eval_open.setValue(val)
                            parent.spin_eval_open.blockSignals(False)
                            # 同步更新 open_price
                            state = self.engine._get_stock_state(self.code, val)
                            state["open_price"] = val
                        elif node_id == "node_2_first_wave":
                            parent.spin_eval_price.blockSignals(True)
                            parent.spin_eval_price.setValue(val)
                            parent.spin_eval_price.blockSignals(False)
                        elif node_id == "node_3_turnover":
                            parent.spin_eval_turnover.blockSignals(True)
                            parent.spin_eval_turnover.setValue(val)
                            parent.spin_eval_turnover.blockSignals(False)
                        break
                    parent = parent.parent()
                self.manual_score_signal.emit()
        return _handler

    def _on_reset_node_custom_params(self):
        """【🔄 重置校准】清空节点自定义参数与人工评分，重新极速拉取 TDX 分时 K 线精准恢复早盘真实节点"""
        self.engine.reset_node_custom_params(self.code)
        try:
            intraday_bars = self.tdx_fetcher.fetch_intraday_bars(self.code)
            if not intraday_bars.empty:
                op = self.spin_eval_open.value()
                self.engine.hydrate_from_intraday_df(self.code, intraday_bars, op if op > 1.0 else None)
        except Exception as e:
            logger.debug(f"重置后刷新 TDX 分时 K 线异常: {e}")

        parent = self.parent()
        while parent:
            if hasattr(parent, '_sync_eval_spins_for_current_stock'):
                parent._sync_eval_spins_for_current_stock()
                break
            parent = parent.parent()
        self.manual_score_signal.emit()


class PinzhunLadderStandaloneWindow(QMainWindow):
    """
    频准激光 8/18 专属上市盯盘与分时阶梯交易策略独立主窗口
    具备完全独立的窗口生命周期、窗口置顶、最大化最小化、多屏支持、TDX 极速秒级直连与估价自动评分能力
    """
    def __init__(self, code: Optional[str] = None, name: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.tdx_fetcher = TDXRealtimeFetcher.get_instance()
        self.selected_strategy_id: Optional[str] = None
        self.selected_data_source: str = "TDX_REALTIME"  # TDX_REALTIME | ATS_IPC | MANUAL_EVAL
        self._is_stay_on_top = False
        self.tdx_log_dialog = None

        if isinstance(code, bool) or not code:
            json_codes = self.engine.get_all_target_codes()
            if json_codes:
                code = json_codes[0]
            elif parent and hasattr(parent, 'current_selected_code') and parent.current_selected_code:
                code = parent.current_selected_code
            elif parent and hasattr(parent, 'selected_code') and parent.selected_code:
                code = parent.selected_code
            else:
                code = "688826"

        self.code = "".join(filter(str.isdigit, str(code))).zfill(6) if code else "688826"
        if not self.code or self.code == "000000":
            self.code = "688826"
        self._known_codes = [self.code]

        if isinstance(name, bool) or not name or name == "未知" or name == self.code:
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        # 独立窗口属性设置 (允许独立任务栏、独立最小化/最大化/关闭)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")
        self.setMinimumSize(1020, 720)

        # 物理恢复窗口几何大小与位置 (QSettings + config/intraday_ui_layout.json 双保险落盘)
        settings = QSettings("pyQuant3", "IntradayWorkbench")
        geo = settings.value("main_window_geometry")
        layout_state = load_ui_layout_state("main_window_layout")

        restored = False
        if geo:
            try:
                restored = self.restoreGeometry(geo)
            except Exception:
                restored = False

        if not restored and layout_state and isinstance(layout_state, dict):
            w = layout_state.get("width", 1340)
            h = layout_state.get("height", 920)
            x = layout_state.get("x")
            y = layout_state.get("y")
            is_max = layout_state.get("is_maximized", False)
            self.resize(w, h)
            if x is not None and y is not None:
                self.move(x, y)
            if is_max:
                self.showMaximized()
            restored = True

        if not restored:
            self.resize(1340, 920)

        # 🎨 全局应用 ATS 统一暗黑主题样式表模板 (QSS)
        apply_dark_theme(self)

        # 缓存最新接收到的 DataFrame
        self._latest_df: Optional[pd.DataFrame] = None

        self._init_ui()
        self._load_mock_or_live_data()

        # 启动 3.0s 极速 UI 自动刷新定时器，驱动 UI 画面与 TDX 秒级直连后台无缝同步跳动！
        self.live_poll_timer = QTimer(self)
        self.live_poll_timer.timeout.connect(self._on_live_timer_tick)
        self.live_poll_timer.start(3000)

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. 顶部 Header 控制栏 第一行：以策略为主导驱动标的与价格联动
        hdr_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")
        self.title_lbl.setStyleSheet("font-size: 11pt; font-weight: bold; color: #38bdf8;")

        lbl_strat = QLabel("📋 策略:")
        lbl_strat.setStyleSheet("font-weight: bold; color: #ffaa44;")

        self.combo_strategy = QComboBox()
        self.combo_strategy.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #ffaa44; border: 1px solid #ffaa44; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 220px; }")
        self._populate_strategy_combo()
        self.combo_strategy.currentIndexChanged.connect(self._on_combo_strategy_changed)

        lbl_select = QLabel("🎯 标的:")
        lbl_select.setStyleSheet("font-weight: bold; color: #00ff88;")

        self.combo_code = QComboBox()
        self.combo_code.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #00ff88; border: 1px solid #00ff88; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 140px; }")
        self._populate_code_combo()
        self.combo_code.currentIndexChanged.connect(self._on_combo_code_changed)

        lbl_src = QLabel("📡 数据源:")
        lbl_src.setStyleSheet("font-weight: bold; color: #aad4ff;")

        self.combo_source = QComboBox()
        self.combo_source.addItem("⚡ 【TDX 极速秒级直连 1s】", "TDX_REALTIME")
        self.combo_source.addItem("🔄 【ATS 后台 IPC 同步】", "ATS_IPC")
        self.combo_source.addItem("✍️ 【手动估价/推演模式】", "MANUAL_EVAL")
        self.combo_source.setStyleSheet("QComboBox { background-color: #1e1e2d; color: #00ff88; border: 1px solid #00ff88; border-radius: 4px; padding: 2px 6px; font-weight: bold; min-width: 175px; }")
        self.combo_source.currentIndexChanged.connect(self._on_source_changed)

        # TDX 连接状态徽标
        tdx_host_str = f"{self.tdx_fetcher.current_host[1]}:{self.tdx_fetcher.current_host[2]}" if self.tdx_fetcher.current_host else "默认"
        self.lbl_tdx_status = QLabel(f"🟢 TDX: {tdx_host_str} ({self.tdx_fetcher.latency_ms:.0f}ms)")
        self.lbl_tdx_status.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold; background-color: #14241d; padding: 3px 6px; border-radius: 3px; border: 1px solid #00ff88;")

        btn_refresh = QPushButton("⚡ 刷新")
        btn_refresh.setStyleSheet("background-color: #0e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_refresh.clicked.connect(self._on_manual_refresh)

        btn_clear_cache = QPushButton("🧹 清理缓存")
        btn_clear_cache.setStyleSheet("background-color: #3b1419; color: #ff6666; font-weight: bold; border: 1px solid #ff6666; border-radius: 4px; padding: 3px 8px;")
        btn_clear_cache.setToolTip("强力清除当前标的的内存与磁盘错误缓存，重新拉取最新 TDX 分时数据")
        btn_clear_cache.clicked.connect(self._on_clear_stock_cache)

        self.btn_topmost = QPushButton("📌 置顶: 关")
        self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 3px 8px;")
        self.btn_topmost.clicked.connect(self._toggle_stay_on_top)

        btn_rearrange = QPushButton("🪟 窗口重排")
        btn_rearrange.setStyleSheet("background-color: #1a2e22; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 8px;")
        btn_rearrange.setToolTip("自动将所有已打开的 SBC 分时走势窗口网格平铺重排对齐")
        btn_rearrange.clicked.connect(self.rearrange_all_sbc_windows)

        btn_auto_eval = QPushButton("⚡ 全量检测")
        btn_auto_eval.setStyleSheet("background-color: #1e3a5f; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_auto_eval.clicked.connect(self._on_eval_all_codes)

        btn_edit = QPushButton("⚙️ 策略编辑")
        btn_edit.setStyleSheet("background-color: #242436; color: #aad4ff; font-weight: bold; border: 1px solid #38bdf8; border-radius: 4px; padding: 3px 8px;")
        btn_edit.clicked.connect(self._on_open_editor)

        btn_close = QPushButton("关闭")
        btn_close.setStyleSheet("background-color: #2b2b36; color: #d1d5db; border-radius: 4px; padding: 3px 8px;")
        btn_close.clicked.connect(self.close)

        hdr_layout.addWidget(self.title_lbl)
        hdr_layout.addStretch()
        hdr_layout.addWidget(lbl_strat)
        hdr_layout.addWidget(self.combo_strategy)
        hdr_layout.addWidget(lbl_select)
        hdr_layout.addWidget(self.combo_code)
        hdr_layout.addWidget(lbl_src)
        hdr_layout.addWidget(self.combo_source)
        hdr_layout.addWidget(self.lbl_tdx_status)
        hdr_layout.addWidget(btn_refresh)
        hdr_layout.addWidget(btn_clear_cache)
        hdr_layout.addWidget(btn_rearrange)
        hdr_layout.addWidget(self.btn_topmost)
        hdr_layout.addWidget(btn_auto_eval)
        hdr_layout.addWidget(btn_edit)
        hdr_layout.addWidget(btn_close)
        layout.addLayout(hdr_layout)

        # 2. 顶部第二行：【💡 估价自动评估 & 手动输入快速推演栏 (带默认关闭开关)】
        eval_bar_layout = QHBoxLayout()
        eval_bar_layout.setContentsMargins(0, 0, 0, 0)
        eval_bar_layout.setSpacing(8)

        self.chk_manual_eval = QCheckBox("💡 开启手动估价/异常推演 (默认关闭)")
        self.chk_manual_eval.setChecked(False) # 默认关闭，绝对优先保证实盘自动获取不受干扰
        self.chk_manual_eval.setStyleSheet("QCheckBox { color: #ffd700; font-weight: bold; font-size: 8.5pt; } QCheckBox::indicator:unchecked { border: 1px solid #777799; background: #1a1a24; } QCheckBox::indicator:checked { border: 1px solid #00ff88; background: #00ff88; }")
        self.chk_manual_eval.toggled.connect(self._on_toggle_manual_eval)

        lbl_open_p = QLabel("开盘估价:")
        lbl_open_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_open = QDoubleSpinBox()
        self.spin_eval_open.setRange(1.0, 5000.0)
        self.spin_eval_open.setValue(565.0)
        self.spin_eval_open.setSingleStep(5.0)
        self.spin_eval_open.setSuffix(" 元")
        self.spin_eval_open.setStyleSheet("background-color: #1a1a24; color: #ffd700; font-weight: bold; border: 1px solid #ffd700; border-radius: 3px; padding: 2px;")
        self.spin_eval_open.setEnabled(False) # 默认禁用
        self.spin_eval_open.valueChanged.connect(self._on_eval_param_changed)

        lbl_curr_p = QLabel("当前现价/估价:")
        lbl_curr_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_price = QDoubleSpinBox()
        self.spin_eval_price.setRange(1.0, 5000.0)
        self.spin_eval_price.setValue(625.0)
        self.spin_eval_price.setSingleStep(5.0)
        self.spin_eval_price.setSuffix(" 元")
        self.spin_eval_price.setStyleSheet("background-color: #1a1a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 3px; padding: 2px;")
        self.spin_eval_price.setEnabled(False) # 默认禁用
        self.spin_eval_price.valueChanged.connect(self._on_eval_param_changed)

        lbl_to_p = QLabel("换手率估算:")
        lbl_to_p.setStyleSheet("color: #aad4ff; font-size: 8.5pt;")
        self.spin_eval_turnover = QDoubleSpinBox()
        self.spin_eval_turnover.setRange(0.0, 100.0)
        self.spin_eval_turnover.setValue(62.5)
        self.spin_eval_turnover.setSingleStep(1.0)
        self.spin_eval_turnover.setSuffix(" %")
        self.spin_eval_turnover.setStyleSheet("background-color: #1a1a24; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px;")
        self.spin_eval_turnover.valueChanged.connect(self._on_eval_param_changed)

        self.btn_auto_calc = QPushButton("⚡ 根据估价全自动评分 & 策略推演")
        self.btn_auto_calc.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 12px;")
        self.btn_auto_calc.setEnabled(False) # 默认禁用
        self.btn_auto_calc.clicked.connect(self._on_apply_custom_eval)

        # 📜 TDX 数据获取日志与异常诊断按钮 (与龙头榜样式完全一致)
        self.btn_tdx_log = QPushButton("📜 TDX日志")
        self.btn_tdx_log.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tdx_log.setToolTip("查看通达信 (pytdx) 行情拉取实时日志、非交易休市状态与网络诊断")
        self.btn_tdx_log.setStyleSheet("""
            QPushButton { 
                background-color: #1a2233; 
                color: #aad4ff; 
                border: 1px solid #334466; 
                border-radius: 3px; 
                padding: 3px 10px; 
                font-size: 8.5pt; 
                font-weight: bold; 
            }
            QPushButton:hover { 
                background-color: #2b3855; 
                color: #00ffcc; 
                border: 1px solid #00ffcc; 
            }
        """)
        self.btn_tdx_log.clicked.connect(self._open_tdx_log_dialog)

        eval_bar_layout.addWidget(self.chk_manual_eval)
        eval_bar_layout.addWidget(lbl_open_p)
        eval_bar_layout.addWidget(self.spin_eval_open)
        eval_bar_layout.addWidget(lbl_curr_p)
        eval_bar_layout.addWidget(self.spin_eval_price)
        eval_bar_layout.addWidget(lbl_to_p)
        eval_bar_layout.addWidget(self.spin_eval_turnover)
        eval_bar_layout.addWidget(self.btn_auto_calc)
        eval_bar_layout.addStretch()
        eval_bar_layout.addWidget(self.btn_tdx_log)

        layout.addLayout(eval_bar_layout)

        # 3. 中央 3 大 Tab 选项卡
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2a2a3a;
                background-color: #101017;
            }
            QTabBar::tab {
                background-color: #161622;
                color: #a0a0c0;
                font-weight: bold;
                padding: 7px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e2638;
                color: #00ff88;
                border-bottom: 2px solid #00ff88;
            }
        """)

        # Tab 1: 【核心主工作台】分时阶梯交易策略 & 7节点动态时序评估工作台
        self.integrated_panel = IntegratedTradingStrategyPanel(self)
        self.integrated_panel.manual_score_signal.connect(self._load_mock_or_live_data)
        self.tab_widget.addTab(self.integrated_panel, "⚡ 分时阶梯交易策略 & 7节点动态评估一体化工作台")

        # Tab 2: 开盘全天分时模拟回测与情景演练器
        self.sim_panel = IntradaySimulationWidget(self)
        self.sim_panel.tick_emitted_signal.connect(self._on_simulation_tick_emitted)
        self.tab_widget.addTab(self.sim_panel, "🎮 上市全天分时模拟回测与情景演练 (A/B/C/D型)")

        # Tab 3: 专属盯盘模板 & 综合评分明细汇总
        self.pinzhun_monitor_panel = PinzhunLaserMonitorWidget(self)
        self.pinzhun_monitor_panel.score_changed_signal.connect(self._load_mock_or_live_data)
        self.tab_widget.addTab(self.pinzhun_monitor_panel, f"📋 【{self.name}】专属盯盘模板 & 综合评分汇总")

        layout.addWidget(self.tab_widget, 1)

        # 4. 定时刷新 Timer (秒级自动推进，基准 3.0s，支持自适应退避调节)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._on_tick_update)
        self.timer.start()

        # 5. 快捷键 T 置顶支持
        bind_top_shortcut(self, self._toggle_stay_on_top)

    def _toggle_stay_on_top(self):
        """切换窗口置顶状态 (快捷键: T, 无缝 0 闪烁)"""
        self._is_stay_on_top = not getattr(self, '_is_stay_on_top', False)
        set_seamless_stay_on_top(self, self._is_stay_on_top)
        if self._is_stay_on_top:
            self.btn_topmost.setText("📌 置顶 (T): 开")
            self.btn_topmost.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; border-radius: 4px; padding: 3px 8px;")
        else:
            self.btn_topmost.setText("📌 置顶 (T): 关")
            self.btn_topmost.setStyleSheet("background-color: #242436; color: #d0d0e0; font-weight: bold; border: 1px solid #555566; border-radius: 4px; padding: 3px 8px;")

    def _on_toggle_manual_eval(self, checked: bool):
        """【开关】手动估价/异常推演开关切换：默认关闭，防止干扰实盘"""
        # 更新输入框与推演按钮启用状态
        self.spin_eval_open.setEnabled(checked)
        self.spin_eval_price.setEnabled(checked)
        self.spin_eval_turnover.setEnabled(checked)
        self.btn_auto_calc.setEnabled(checked)

        target_source = "MANUAL_EVAL" if checked else "TDX_REALTIME"
        if self.selected_data_source != target_source:
            self.combo_source.blockSignals(True)
            idx = self.combo_source.findData(target_source)
            if idx >= 0:
                self.combo_source.setCurrentIndex(idx)
            self.selected_data_source = target_source
            self.combo_source.blockSignals(False)

        if not checked:
            # 关闭手动估价时，重置节点覆盖参数，完全恢复实盘自动拉取
            self.engine.reset_node_custom_params(self.code)
            self.lbl_tdx_status.show()
            self._update_tdx_status_badge()
        else:
            self.lbl_tdx_status.setText("✍️ 估价模式")
            self.lbl_tdx_status.show()
            self._on_eval_param_changed()
            return

        self._load_mock_or_live_data()

    def _on_source_changed(self, index: int):
        self.selected_data_source = self.combo_source.itemData(index)
        is_manual = (self.selected_data_source == "MANUAL_EVAL")
        if hasattr(self, 'chk_manual_eval'):
            self.chk_manual_eval.blockSignals(True)
            self.chk_manual_eval.setChecked(is_manual)
            self.spin_eval_open.setEnabled(is_manual)
            self.spin_eval_price.setEnabled(is_manual)
            self.spin_eval_turnover.setEnabled(is_manual)
            self.btn_auto_calc.setEnabled(is_manual)
            self.chk_manual_eval.blockSignals(False)

        if self.selected_data_source == "TDX_REALTIME":
            self.lbl_tdx_status.show()
            self._update_tdx_status_badge()
        elif self.selected_data_source == "MANUAL_EVAL":
            self.lbl_tdx_status.setText("✍️ 估价模式")
            self.lbl_tdx_status.show()
        else:
            self.lbl_tdx_status.hide()
        self._load_mock_or_live_data()

    def _on_clear_stock_cache(self):
        """【🧹 彻底清理单股缓存】强力清除内存与磁盘错误缓存并立即重置对齐"""
        c_clean = str(self.code).zfill(6)
        self.tdx_fetcher.clear_stock_cache(c_clean)
        self.engine.clear_stock_cache(c_clean)

        if hasattr(self, '_sbc_dialogs'):
            for d in self._sbc_dialogs.values():
                if d and d.isVisible():
                    d.reload_chart()
        elif hasattr(self, '_sbc_dialog') and self._sbc_dialog is not None:
            self._sbc_dialog.reload_chart()

        self._on_manual_refresh()
        QMessageBox.information(self, "🧹 缓存已强力重置", f"标的 [{c_clean} {self.name}] 的内存与磁盘行情缓存已成功强力清除！\n已自动拉取最新 TDX 分时数据并重置评级！")

    def rearrange_all_sbc_windows(self):
        """【🪟 窗口重排】自动平铺重排所有打开的 SBC 窗口 (保持各自窗口原尺寸不变，只顺畅排列 x, y 坐标)"""
        rearrange_all_sbc_windows(parent_win=self)

    def _on_eval_param_changed(self):
        """当用户修改开盘估价、现价估价或换手率时自动同步 7 节点校准参数并触发评分"""
        if not getattr(self, 'chk_manual_eval', None) or not self.chk_manual_eval.isChecked():
            return
        if hasattr(self, 'spin_eval_open'):
            op = self.spin_eval_open.value()
            tp = self.spin_eval_price.value()
            to_rate = self.spin_eval_turnover.value()
            self.open_price = op
            # 实时同步到引擎中 7 节点对应的节点校准槽位
            self.engine.set_node_custom_param(self.code, "node_1_auction", op)
            self.engine.set_node_custom_param(self.code, "node_2_first_wave", tp)
            self.engine.set_node_custom_param(self.code, "node_3_turnover", to_rate)
            # 同步更新股票状态
            state = self.engine._get_stock_state(self.code, op)
            state["open_price"] = op
            if tp > state.get("max_price", 0.0):
                state["max_price"] = tp
        self._load_mock_or_live_data()

    def _on_apply_custom_eval(self):
        """手动点击估价评估按钮：一键开启估价模式并全自动打分"""
        if hasattr(self, 'chk_manual_eval'):
            self.chk_manual_eval.setChecked(True)
        idx = self.combo_source.findData("MANUAL_EVAL")
        if idx >= 0:
            self.combo_source.setCurrentIndex(idx)
        self.selected_data_source = "MANUAL_EVAL"
        self._on_eval_param_changed()

    def _save_window_layout(self):
        """【💾 物理落盘】保存主窗口尺寸、坐标与最大化状态到 QSettings 及 JSON 配置文件"""
        try:
            settings = QSettings("pyQuant3", "IntradayWorkbench")
            settings.setValue("main_window_geometry", self.saveGeometry())

            geo = self.geometry()
            save_ui_layout_state("main_window_layout", {
                "width": geo.width(),
                "height": geo.height(),
                "x": geo.x(),
                "y": geo.y(),
                "is_maximized": self.isMaximized()
            })
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._save_window_layout()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._save_window_layout()

    def closeEvent(self, event):
        """关闭窗口时持久化保存主窗口大小与位置，并安全持久化策略状态变动"""
        self._save_window_layout()
        try:
            if hasattr(self, 'engine') and self.engine:
                self.engine.save_intraday_cache(force=False)
        except Exception:
            pass
        super().closeEvent(event)

    def _on_live_timer_tick(self):
        """3.0s 定时刷新回调：在 TDX 直连模式且未开启手动估价勾选时，自动驱动界面极速跳动与评估"""
        if getattr(self, "selected_data_source", "") == "TDX_REALTIME":
            if not hasattr(self, "chk_manual_eval") or not self.chk_manual_eval.isChecked():
                self._load_mock_or_live_data()

    def _on_manual_refresh(self):
        """用户手动点击【⚡ 刷新】按钮：重置 TDX 静默状态并立即拉取"""
        if self.tdx_fetcher:
            self.tdx_fetcher.reset_code_dormancy(self.code)
        self._load_mock_or_live_data()

    def _open_tdx_log_dialog(self):
        """打开/激活通达信高频数据获取诊断日志独立窗口"""
        from PyQt6.sip import isdeleted
        from ats.ui.hot_sector_leaderboard import TDXFetchLogDialog
        if self.tdx_log_dialog is not None and not isdeleted(self.tdx_log_dialog):
            self.tdx_log_dialog.show()
            self.tdx_log_dialog.raise_()
            self.tdx_log_dialog.activateWindow()
            return

        self.tdx_log_dialog = TDXFetchLogDialog(parent=self)
        self.tdx_log_dialog.show()
        self.tdx_log_dialog.raise_()
        self.tdx_log_dialog.activateWindow()

    def _update_tdx_status_badge(self):
        if self.tdx_fetcher and self.tdx_fetcher.current_host:
            h = self.tdx_fetcher.current_host
            is_dormant = self.code in getattr(self.tdx_fetcher, '_unlisted_or_dormant_codes', set())
            if is_dormant:
                self.lbl_tdx_status.setText(f"🟡 TDX: 暂无成交 (30s静默)")
            else:
                self.lbl_tdx_status.setText(f"🟢 TDX: {h[1]}:{h[2]} ({self.tdx_fetcher.latency_ms:.0f}ms)")
        else:
            self.lbl_tdx_status.setText("🔴 TDX: 未连接")

    def on_realtime_df_update(self, df: Optional[pd.DataFrame]):
        """接收来自 ATS 主窗口或独立 IPC 数据流的实时行情推送"""
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            self._latest_df = df
            if self.selected_data_source == "ATS_IPC":
                self._load_mock_or_live_data()

    def _populate_strategy_combo(self):
        self.combo_strategy.blockSignals(True)
        self.combo_strategy.clear()

        from ats.intraday_strategy_engine import is_valid_stock_code
        for st in self.engine.strategies:
            st_id = st.get("id", "")
            st_name = st.get("name", st_id)
            target_codes = st.get("target_codes", [])
            # 过滤垃圾无效占位策略
            if any(p in st_id for p in ("000000", "000123")) or any(p in st_name for p in ("000000", "000123", "标的_000000", "标的_000123")):
                continue
            if target_codes and not any(is_valid_stock_code(str(c)) for c in target_codes):
                continue
            self.combo_strategy.addItem(f"📋 {st_name}", st_id)

        target_id = self.selected_strategy_id
        if not target_id and self.engine.strategies:
            # 优先匹配当前标的归属的策略，若无则默认第一套
            auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
            target_id = auto_st.get("id") if auto_st else self.engine.strategies[0].get("id")
            self.selected_strategy_id = target_id

        for idx in range(self.combo_strategy.count()):
            if self.combo_strategy.itemData(idx) == target_id:
                self.combo_strategy.setCurrentIndex(idx)
                break
        self.combo_strategy.blockSignals(False)

    def switch_to_code(self, code: str, name: Optional[str] = None):
        """外部（如主窗口）动态切换当前监控标的"""
        from ats.intraday_strategy_engine import is_valid_stock_code
        c_clean = "".join(filter(str.isdigit, str(code))).zfill(6) if code else ""
        if not c_clean or not is_valid_stock_code(c_clean):
            return
        self.code = c_clean
        if not hasattr(self, '_known_codes'):
            self._known_codes = []
        if self.code not in self._known_codes:
            self._known_codes.append(self.code)

        # 切换标的时重置该标的的 TDX 静默保护状态
        if self.tdx_fetcher:
            self.tdx_fetcher.reset_code_dormancy(self.code)

        if isinstance(name, bool) or not name or name == "未知" or name == c_clean:
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)
        else:
            self.name = name

        self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")
        if hasattr(self, 'title_lbl'):
            self.title_lbl.setText(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")

        # 自动匹配新标的对应的策略并更新策略下拉框
        auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
        if auto_st:
            self.selected_strategy_id = auto_st.get("id")
            self._populate_strategy_combo()

        # 刷新并同步标的下拉框
        self._populate_code_combo()
        self._sync_eval_spins_for_current_stock()
        if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
            self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分汇总")
        self._load_mock_or_live_data()

    def _populate_code_combo(self):
        self.combo_code.blockSignals(True)
        self.combo_code.clear()

        from ats.intraday_strategy_engine import is_valid_stock_code
        strat_codes = []
        if self.code and is_valid_stock_code(self.code) and self.code not in strat_codes:
            strat_codes.append(self.code)
        for kc in getattr(self, '_known_codes', []):
            if kc and is_valid_stock_code(kc) and kc not in strat_codes:
                strat_codes.append(kc)

        # 获取当前选定策略所绑定的目标标的代码
        curr_strat = self.engine.get_strategy_by_id(self.selected_strategy_id) if self.selected_strategy_id else None
        if curr_strat and curr_strat.get("target_codes"):
            for tc in curr_strat.get("target_codes", []):
                c_clean = "".join(filter(str.isdigit, str(tc))).zfill(6)
                if c_clean and is_valid_stock_code(c_clean) and c_clean not in strat_codes:
                    strat_codes.append(c_clean)

        for c in self.engine.get_all_target_codes():
            if c and is_valid_stock_code(c) and c not in strat_codes:
                strat_codes.append(c)

        if not strat_codes:
            strat_codes = ["688826"]

        for c in strat_codes:
            c_name = resolve_stock_name(c)
            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                p_name = parent.get_stock_name(c)
                if p_name and p_name != "未知" and p_name != c:
                    c_name = p_name
            self.combo_code.addItem(f"{c} {c_name}", c)

        for idx in range(self.combo_code.count()):
            if self.combo_code.itemData(idx) == self.code:
                self.combo_code.setCurrentIndex(idx)
                break
        self.combo_code.blockSignals(False)

    def _sync_eval_spins_for_current_stock(self):
        """根据当前标的的策略规格（stock_spec / price_ladder）自动重置顶部预估价格与换手率，并清空旧节点的校准缓存"""
        if not hasattr(self, 'spin_eval_open') or not hasattr(self, 'spin_eval_price'):
            return

        spec = self.engine.get_stock_ladder_spec(self.code)
        is_first_day = self.engine.is_stock_first_listing_day(self.code)
        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        price_ladder = spec.get("price_ladder", [])

        if is_first_day and issue_p > 0:
            # 默认开盘估价取 +200% 强势基准（如果有价格阶梯则取第2档价格，否则 issue_p * 3.0）
            suggested_open = round(issue_p * 3.0, 2)
            if len(price_ladder) >= 2 and "price" in price_ladder[1]:
                suggested_open = float(price_ladder[1]["price"])
            elif len(price_ladder) >= 1 and "price" in price_ladder[0]:
                suggested_open = float(price_ladder[0]["price"])

            # 默认现价估价取开盘价 * 1.10（较开盘冲高 10%）
            suggested_price = round(suggested_open * 1.10, 2)
            suggested_turnover = 62.5
        else:
            # 常规非首日股票：基准价为昨收价/现价，开盘取基准*1.02，现价取基准*1.05
            ref_base = issue_p if issue_p > 0 else 10.0
            suggested_open = round(ref_base * 1.02, 2)
            suggested_price = round(ref_base * 1.05, 2)
            suggested_turnover = 5.0

        # 仅当手动估价勾选开启时才写入 custom_params；在实盘 TDX 直连模式下绝对不注入污染数据！
        if hasattr(self, 'chk_manual_eval') and self.chk_manual_eval.isChecked():
            self.engine.set_node_custom_param(self.code, "node_1_auction", suggested_open)
            self.engine.set_node_custom_param(self.code, "node_2_first_wave", suggested_price)
            self.engine.set_node_custom_param(self.code, "node_3_turnover", suggested_turnover)
        else:
            # 清理历史可能残留的手动覆盖参数
            state = self.engine._get_stock_state(self.code, 0.0)
            custom_p = state.get("node_custom_params", {})
            custom_p.pop("node_1_auction", None)
            custom_p.pop("node_2_first_wave", None)
            custom_p.pop("node_3_turnover", None)

        self.spin_eval_open.blockSignals(True)
        self.spin_eval_price.blockSignals(True)
        self.spin_eval_turnover.blockSignals(True)
        self.spin_eval_open.setValue(suggested_open)
        self.spin_eval_price.setValue(suggested_price)
        self.spin_eval_turnover.setValue(suggested_turnover)
        self.spin_eval_open.blockSignals(False)
        self.spin_eval_price.blockSignals(False)
        self.spin_eval_turnover.blockSignals(False)

    def _on_combo_strategy_changed(self, index: int):
        selected_strat_id = self.combo_strategy.itemData(index)
        self.selected_strategy_id = selected_strat_id
        strategy = self.engine.get_strategy_by_id(selected_strat_id)
        if strategy:
            t_codes = [str(c).zfill(6) for c in strategy.get("target_codes", []) if str(c).strip() not in ("", "000000", "0")]
            # 只有当策略具有专属 target_codes 且当前 code 不在该专属列表中时，才切换为专属代码
            if t_codes and self.code not in t_codes:
                self.code = t_codes[0]
                if not hasattr(self, '_known_codes'):
                    self._known_codes = []
                if self.code not in self._known_codes:
                    self._known_codes.append(self.code)
                self.name = resolve_stock_name(self.code)

            # 刷新并同步标的下拉框
            self._populate_code_combo()

            # 动态重置估价输入框为当前标的基准价格
            self._sync_eval_spins_for_current_stock()

            if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
                self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分明细汇总")

        self._load_mock_or_live_data()

    def _on_combo_code_changed(self, index: int):
        selected_code = self.combo_code.itemData(index)
        if selected_code and selected_code != self.code:
            self.code = str(selected_code).zfill(6)
            if not hasattr(self, '_known_codes'):
                self._known_codes = []
            if self.code not in self._known_codes:
                self._known_codes.append(self.code)

            # 切换标的时重置该标的的 TDX 静默保护状态
            if self.tdx_fetcher:
                self.tdx_fetcher.reset_code_dormancy(self.code)

            parent = self.parent()
            if parent and hasattr(parent, 'get_stock_name'):
                self.name = parent.get_stock_name(self.code)
            else:
                self.name = resolve_stock_name(self.code)

            if hasattr(self, 'title_lbl'):
                self.title_lbl.setText(f"📈 【{self.code} {self.name}】分时阶梯交易与时序评估工作台")
            self.setWindowTitle(f"⚡ 【{self.code} {self.name}】分时阶梯交易与时序评估系统")

            # 自动联动切换到该标的对应的策略
            auto_st = self.engine.auto_select_strategy(0.0, code=self.code)
            if auto_st:
                self.selected_strategy_id = auto_st.get("id")
                self.combo_strategy.blockSignals(True)
                for idx in range(self.combo_strategy.count()):
                    if self.combo_strategy.itemData(idx) == self.selected_strategy_id:
                        self.combo_strategy.setCurrentIndex(idx)
                        break
                self.combo_strategy.blockSignals(False)

            # 动态重置估价输入框为当前标的基准价格
            self._sync_eval_spins_for_current_stock()

            if hasattr(self, 'tab_widget') and self.tab_widget.count() > 2:
                self.tab_widget.setTabText(2, f"📋 【{self.name}】专属盯盘模板 & 综合评分明细汇总")

            self._load_mock_or_live_data()

    def _on_simulation_tick_emitted(self, tick_data: Dict[str, Any]):
        """处理模拟回放发出的 Tick 数据，联动刷新 Tab 1 和 Tab 3"""
        p = float(tick_data.get("trade", tick_data.get("close", 0.0)))
        open_p = float(tick_data.get("open", p))
        h_p = float(tick_data.get("high", p))
        l_p = float(tick_data.get("low", p))
        vwap_p = float(tick_data.get("vwap", p))
        to_rate = float(tick_data.get("turnover", 0.0))
        amt = float(tick_data.get("amount", 0.0))
        b1_p = float(tick_data.get("buy", p))
        t_str = tick_data.get("time", "09:30")

        self.open_price = open_p
        strategy = self.engine.auto_select_strategy(open_p, code=self.code)

        # 评估阶梯交易信号
        tick_row = {"trade": p, "close": p}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=open_p,
            current_time_str=t_str,
            bid1_price=b1_p
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=open_p,
            price=p,
            high_price=h_p,
            low_price=l_p,
            vwap=vwap_p,
            turnover_rate=to_rate,
            amount=amt,
            bid1_price=b1_p,
            current_time_str=t_str,
            strategy=strategy,
            is_unlisted=False
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=open_p,
            price=p,
            high_price=h_p,
            low_price=l_p,
            vwap=vwap_p,
            turnover_rate=to_rate,
            amount=amt,
            current_time_str=t_str
        )

    def _on_eval_all_codes(self):
        """打开或刷新【⚡ 全量 Code 分时阶梯策略自动检测评估】持久化滚动对话框"""
        if not hasattr(self, '_all_codes_eval_dialog') or self._all_codes_eval_dialog is None:
            self._all_codes_eval_dialog = AllCodesStrategyEvalDialog(self)
        self._all_codes_eval_dialog.show()
        self._all_codes_eval_dialog.raise_()
        self._all_codes_eval_dialog.activateWindow()
        self._all_codes_eval_dialog.run_evaluation()

    def keyPressEvent(self, event):
        """⚡ 窗口级快捷键：按下 T 键切换置顶，按下 R 键触发自适应策略测算"""
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self._toggle_stay_on_top()
                event.accept()
                return
        elif key == Qt.Key.Key_R:
            # 优先调用 Tab1 中的 SBC 画布测算
            if hasattr(self, 'tab1_sbc_canvas') and self.tab1_sbc_canvas:
                self.tab1_sbc_canvas.code = self.code
                self.tab1_sbc_canvas.run_adaptive_strategy_eval()
                event.accept()
                return
        super().keyPressEvent(event)

    def _get_stock_realtime_data_for_code(self, code_str: str) -> Tuple[float, float, float, float, float, float, float, float, str, bool, float]:
        """全自动从 TDX 秒级直连、手动估价输入、self._latest_df 或行情快照解析全量字段"""
        c_clean = str(code_str).zfill(6)
        resolved_name = resolve_stock_name(c_clean)
        parent = self.parent()
        if parent and hasattr(parent, 'get_stock_name'):
            p_name = parent.get_stock_name(c_clean)
            if p_name and p_name != "未知" and p_name != c_clean:
                resolved_name = p_name

        spec = self.engine.get_stock_ladder_spec(c_clean)
        float_mv_yi = float(spec.get("float_mv_yi", 15.0))

        # 0. 权威检测该标的是否为尚未挂牌交易的【待上市新股】
        is_unlisted = self.engine.is_stock_unlisted(c_clean)
        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        if issue_p <= 0:
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                ipo_dict = getattr(NewStockFetcher.get_instance(), '_cached_ipo_dict', {})
                if c_clean in ipo_dict:
                    issue_p = float(ipo_dict[c_clean].get("issue_price", 0.0) or 0.0)
            except Exception:
                pass

        # 1. 只有当用户显式勾选了【✍️ 开启手动估价/异常推演 (默认关闭)】复选框时，才由手动 SpinBox 驱动
        if hasattr(self, "chk_manual_eval") and self.chk_manual_eval.isChecked() and getattr(self, "selected_data_source", "") == "MANUAL_EVAL":
            op = self.spin_eval_open.value()
            tp = self.spin_eval_price.value()
            to_rate = self.spin_eval_turnover.value()
            hp = max(op, tp, op * 1.13)
            lp = min(op, tp)
            vw = (op + tp) / 2.0
            amt = float(to_rate / 100.0 * float_mv_yi * 1e8)
            b1 = tp
            lc = op
            return op, tp, hp, lp, vw, to_rate, amt, b1, resolved_name, is_unlisted, lc

        # 2. 🛡️ 待上市新股权威保护：若标的尚未挂牌交易，自动以发行价估价阶梯呈现，坚决过滤撮合测试脏数据 (如 0.01元/1.08元)
        if is_unlisted:
            op_base = issue_p if issue_p > 0 else 60.0
            op = op_base
            tp = op_base
            hp = op_base
            lp = op_base
            vw = op_base
            to_rate = 0.0
            amt = 0.0
            b1 = op_base
            lc = op_base
            if hasattr(self, 'lbl_tdx_status'):
                self.lbl_tdx_status.setText("💡 待上市新股 (估价模型)")
                self.lbl_tdx_status.show()
            if hasattr(self, 'spin_eval_open') and not getattr(self.chk_manual_eval, "isChecked", lambda: False)():
                self.spin_eval_open.blockSignals(True)
                self.spin_eval_price.blockSignals(True)
                self.spin_eval_turnover.blockSignals(True)
                self.spin_eval_open.setValue(op)
                self.spin_eval_price.setValue(round(op * 1.10, 2))
                self.spin_eval_turnover.setValue(60.0)
                self.spin_eval_open.blockSignals(False)
                self.spin_eval_price.blockSignals(False)
                self.spin_eval_turnover.blockSignals(False)
            return op, tp, hp, lp, vw, to_rate, amt, b1, resolved_name, True, lc

        # 3. 优先从 TDX 极速秒级直连获取
        if getattr(self, "selected_data_source", "TDX_REALTIME") == "TDX_REALTIME":
            try:
                tdx_snap = self.tdx_fetcher.fetch_stock_snapshot(c_clean)
                if tdx_snap and float(tdx_snap.get("price", 0.0)) > 0:
                    op = float(tdx_snap.get("open_price", tdx_snap.get("price", 0.0)))
                    tp = float(tdx_snap.get("price", 0.0))
                    hp = float(tdx_snap.get("high_price", tp))
                    lp = float(tdx_snap.get("low_price", tp))
                    vw = float(tdx_snap.get("vwap", tp))
                    to_rate = float(tdx_snap.get("turnover_rate", 0.0))
                    amt = float(tdx_snap.get("amount", 0.0))
                    b1 = float(tdx_snap.get("bid1_price", tp))
                    lc = float(tdx_snap.get("last_close", op))
                    self._update_tdx_status_badge()

                    # 首次加载或切换标的时，不受非交易时段限制，强力获取 TDX 今日 1分钟 K线全量回溯早盘节点 (09:25, 09:40, 10:00, 11:00 等)
                    st_state = self.engine._get_stock_state(c_clean, op)
                    intraday_bars = self.tdx_fetcher.fetch_intraday_bars(c_clean)
                    if not intraday_bars.empty:
                        self.engine.hydrate_from_intraday_df(c_clean, intraday_bars, op)

                    # 同步到界面估价框中方便观察
                    self.spin_eval_open.blockSignals(True)
                    self.spin_eval_price.blockSignals(True)
                    self.spin_eval_turnover.blockSignals(True)
                    self.spin_eval_open.setValue(op)
                    self.spin_eval_price.setValue(tp)
                    self.spin_eval_turnover.setValue(to_rate)
                    self.spin_eval_open.blockSignals(False)
                    self.spin_eval_price.blockSignals(False)
                    self.spin_eval_turnover.blockSignals(False)
                    return op, tp, hp, lp, vw, to_rate, amt, b1, resolved_name, False, lc
            except Exception as e:
                logger.debug(f"TDX 获取 {c_clean} 异常: {e}")

        # 4. 若 TDX 秒级快照未能获取，从 1 分钟 K 线历史或 ATS 推送 df 解析
        curr_df = self._latest_df
        if curr_df is None and parent is not None and hasattr(parent, 'current_df') and parent.current_df is not None:
            curr_df = parent.current_df

        try:
            bars_df = self.tdx_fetcher.fetch_intraday_bars(c_clean)
            if bars_df is not None and not bars_df.empty:
                self.engine.hydrate_from_intraday_df(c_clean, bars_df)
        except Exception:
            pass

        snap = self.engine.extract_market_snapshot_from_df(curr_df, c_clean)
        open_price = snap["open_price"]
        trade_price = snap["price"]
        high_price = snap["high_price"]
        low_price = snap["low_price"]
        vwap_price = snap["vwap"]
        turnover_rate = snap["turnover_rate"]
        amount_val = snap["amount"]
        bid1_price = snap["bid1_price"]
        last_close = snap.get("last_close", open_price)

        # 5. 若行情与 K线 历史均尚未产生，且用户显式勾选了手动估价，由界面估价 SpinBox 驱动
        if open_price <= 0 and trade_price <= 0:
            if hasattr(self, "chk_manual_eval") and self.chk_manual_eval.isChecked():
                open_price = self.spin_eval_open.value()
                trade_price = self.spin_eval_price.value()
                turnover_rate = self.spin_eval_turnover.value()
                high_price = max(open_price, trade_price)
                low_price = min(open_price, trade_price)
                amount_val = float(turnover_rate / 100.0 * float_mv_yi * 1e8)
                bid1_price = trade_price
                vwap_price = round((open_price + trade_price) / 2.0, 2)
                last_close = open_price
            else:
                st_state = self.engine._get_stock_state(c_clean, 0.0)
                open_price = st_state.get("open_price", 0.0)
                trade_price = st_state.get("max_price", open_price)
                high_price = st_state.get("max_price", open_price)
                low_price = st_state.get("min_price", open_price)
                vwap_price = open_price
                last_close = open_price
        elif open_price <= 0 and trade_price > 0:
            open_price = trade_price
            high_price = max(high_price, trade_price)
            low_price = min(low_price, trade_price) if low_price > 0 else trade_price
            vwap_price = trade_price if vwap_price <= 0 else vwap_price
            last_close = open_price if last_close <= 0 else last_close

        return open_price, trade_price, high_price, low_price, vwap_price, turnover_rate, amount_val, bid1_price, resolved_name, is_unlisted, last_close

    def _get_stock_realtime_data(self):
        return self._get_stock_realtime_data_for_code(self.code)

    def _on_open_editor(self):
        dlg = IntradayStrategyEditDialog(parent=self, initial_strategy_id=self.selected_strategy_id, current_code=self.code)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.engine.load_config()
            self._populate_strategy_combo()
            self._populate_code_combo()
            self._load_mock_or_live_data()

    def _load_mock_or_live_data(self):
        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted, last_close = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        # 1. 尝试从 TDX 极速行情拉取全量 240 分钟分时 K 线，驱动策略全量分时反演与买卖点流水挂单生成
        if getattr(self, "selected_data_source", "TDX_REALTIME") == "TDX_REALTIME":
            try:
                df_intraday = self.tdx_fetcher.fetch_intraday_bars(self.code)
                if df_intraday is not None and not df_intraday.empty:
                    self._latest_df = df_intraday
                    self.engine.hydrate_from_intraday_df(self.code, df_intraday, open_price=self.open_price)
            except Exception as e_hyd:
                logger.debug(f"加载 TDX 分时反演流异常: {e_hyd}")

        now_time_str = datetime.now().strftime("%H:%M:%S")

        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)

        tick_row = {"trade": trade_price, "close": trade_price}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=now_time_str,
            bid1_price=bid1_price if bid1_price > 0 else trade_price
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            bid1_price=bid1_price,
            current_time_str=now_time_str,
            strategy=strategy,
            is_unlisted=is_unlisted,
            last_close=last_close
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            current_time_str=now_time_str
        )

    def _on_tick_update(self):
        # 若正在进行模拟回放，则不被真实时钟覆盖
        if hasattr(self, 'sim_panel') and self.sim_panel.replay_timer.isActive():
            return

        open_price, trade_price, high_price, low_price, vwap_price, to_rate, amt_val, bid1_price, real_name, is_unlisted, last_close = self._get_stock_realtime_data()
        self.name = real_name
        self.open_price = open_price

        now_str = datetime.now().strftime("%H:%M:%S")
        strategy = None
        if self.selected_strategy_id:
            strategy = self.engine.get_strategy_by_id(self.selected_strategy_id)
        if not strategy:
            strategy = self.engine.auto_select_strategy(self.open_price, code=self.code)

        tick_row = {"trade": trade_price, "close": trade_price}
        self.engine.evaluate_tick(
            code=self.code,
            tick_row=tick_row,
            open_price=self.open_price,
            current_time_str=now_str,
            bid1_price=bid1_price if bid1_price > 0 else trade_price
        )

        # 刷新 Tab 1
        self.integrated_panel.update_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            bid1_price=bid1_price,
            current_time_str=now_str,
            strategy=strategy,
            is_unlisted=is_unlisted,
            last_close=last_close
        )

        # 刷新 Tab 3
        self.pinzhun_monitor_panel.update_monitor_data(
            code=self.code,
            open_price=self.open_price,
            price=trade_price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap_price,
            turnover_rate=to_rate,
            amount=amt_val,
            current_time_str=now_str
        )

    def closeEvent(self, event):
        """窗口关闭时停止所有后台定时器并释放资源，确保应用彻底安全退出"""
        try:
            if hasattr(self, 'timer') and self.timer.isActive():
                self.timer.stop()
            if hasattr(self, 'sim_panel') and hasattr(self.sim_panel, 'replay_timer') and self.sim_panel.replay_timer.isActive():
                self.sim_panel.replay_timer.stop()
            if hasattr(self, 'tdx_fetcher') and self.tdx_fetcher:
                self.tdx_fetcher.disconnect()
            if hasattr(self, 'engine') and self.engine:
                self.engine.save_intraday_cache(force=False)
        except Exception as e:
            logger.debug(f"closeEvent cleanup: {e}")
        event.accept()


# 向后兼容别名
IntradayStrategyDialog = PinzhunLadderStandaloneWindow


class AllCodesStrategyEvalDialog(QDialog):
    """
    全量 Code 分时阶梯策略自动检测评估报告窗口
    1. 采用科技暗夜风格，支持全屏与任意拉伸，并持久化保存窗口几何尺寸 (QSettings + config/intraday_ui_layout.json)
    2. 支持 【全内容表格模式】 与 【流式卡片模式】 双视图无缝切换
    3. 全内容表格包含 14 列：序号、代码、名称、⭐综合评分、形态分类、所属策略、现价、涨跌幅、开盘价、VWAP、换手率、成交额、实操指引与触发卖点、操作
    4. 评分列及行情列全部采用数值比较器 (NumericTableWidgetItem)，支持用户直接点击表头按分数/涨跌幅自由升降序排序
    5. 顶栏提供快速排序选择下拉框（综合评分高到低、涨跌幅、换手率、成交额等），卡片流与表格全自动响应排序
    6. 实时关键词过滤（代码/名称/策略/形态/动作）
    7. 支持双击行或点击【🎯 查看此标的】直接穿透切换主工作台当前标的
    """
    TABLE_HEADERS = [
        "#", "代码", "名称", "⭐ 综合评分", "形态分类", "所属策略",
        "现价(元)", "涨跌幅", "开盘基准", "VWAP", "换手率", "成交额",
        "实操指引 & 触发信号", "操作"
    ]

    def __init__(self, parent_workbench: 'PinzhunLadderStandaloneWindow'):
        super().__init__(parent_workbench)
        self.workbench = parent_workbench
        self.engine = parent_workbench.engine
        self.cards_data = []  # 存储所有评估结果数据字典
        self.card_widgets = []  # 存储渲染的卡片控件 (item_data, widget)
        self.full_report_text = ""
        self.current_sort_key = "score_desc"  # 默认按综合评分降序
        self.current_view_mode = "table"  # 默认全内容表格视图
        
        # 联动与防抖状态
        self._pending_linkage_row = -1
        self._last_linked_code = None
        self._last_linked_time = 0
        self._linkage_timer = QTimer(self)
        self._linkage_timer.setSingleShot(True)
        self._linkage_timer.setInterval(60)  # 60ms 平滑防抖 (防键盘快速连按风暴)
        self._linkage_timer.timeout.connect(self._fire_linkage_debounced)
        self.selected_card_index = -1

        self.setWindowTitle("⚡ 全量 Code 分时阶梯策略自动检测评估报告")
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b0f19;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }
            QScrollArea {
                border: 1px solid #1e293b;
                background-color: #0b0f19;
                border-radius: 8px;
            }
            QScrollBar:vertical {
                border: none;
                background: #0f172a;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #0284c7;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                color: #f8fafc;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
                background-color: #0f172a;
            }
            QComboBox {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 10px;
                color: #38bdf8;
                font-size: 12px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 1px solid #38bdf8;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                border: 1px solid #334155;
                selection-background-color: #0284c7;
                color: #f8fafc;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                color: #e2e8f0;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #334155;
                border: 1px solid #38bdf8;
                color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #0f172a;
            }
            QPushButton#PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0369a1);
                border: 1px solid #38bdf8;
                color: #ffffff;
            }
            QPushButton#PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #0284c7);
            }
            QPushButton#ActiveViewBtn {
                background-color: #0369a1;
                border: 1px solid #38bdf8;
                color: #ffffff;
            }
            QFrame#StockCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
            }
            QFrame#StockCard:hover {
                border: 1px solid #38bdf8;
                background-color: #131d33;
            }
            QTableWidget {
                background-color: #0f172a;
                gridline-color: #1e293b;
                color: #e2e8f0;
                font-size: 12px;
                border: 1px solid #1e293b;
                border-radius: 6px;
                selection-background-color: #1e3a8a;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #38bdf8;
                font-weight: bold;
                font-size: 12px;
                padding: 6px 4px;
                border: 1px solid #0f172a;
            }
            QHeaderView::section:hover {
                background-color: #334155;
                color: #ffd700;
            }
        """)

        self._init_ui()
        self._restore_geometry()
        bind_top_shortcut(self, self._toggle_stay_on_top)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. 顶栏 Toolbar
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(8)

        self.lbl_title = QLabel("⚡ 全量策略评估")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        top_layout.addWidget(self.lbl_title)

        self.lbl_meta = QLabel("📊 加载中...")
        self.lbl_meta.setStyleSheet("font-size: 12px; color: #94a3b8;")
        top_layout.addWidget(self.lbl_meta)

        top_layout.addSpacing(6)

        # 视图切换按钮组
        lbl_v = QLabel("视图:")
        lbl_v.setStyleSheet("font-size: 12px; color: #94a3b8;")
        top_layout.addWidget(lbl_v)

        self.btn_view_table = QPushButton("📊 全内容表格")
        self.btn_view_table.setObjectName("ActiveViewBtn")
        self.btn_view_table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_table.clicked.connect(lambda: self._switch_view_mode("table"))
        top_layout.addWidget(self.btn_view_table)

        self.btn_view_cards = QPushButton("🗂️ 流式卡片")
        self.btn_view_cards.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_cards.clicked.connect(lambda: self._switch_view_mode("cards"))
        top_layout.addWidget(self.btn_view_cards)

        top_layout.addSpacing(6)

        # 排序选择下拉框
        lbl_s = QLabel("排序:")
        lbl_s.setStyleSheet("font-size: 12px; color: #94a3b8;")
        top_layout.addWidget(lbl_s)

        self.combo_sort = QComboBox()
        self.combo_sort.addItem("⭐ 综合评分 ⬇️ (高到低)", "score_desc")
        self.combo_sort.addItem("⭐ 综合评分 ⬆️ (低到高)", "score_asc")
        self.combo_sort.addItem("📈 涨跌幅 ⬇️ (从强到弱)", "pct_desc")
        self.combo_sort.addItem("📉 涨跌幅 ⬆️ (从弱到强)", "pct_asc")
        self.combo_sort.addItem("🔄 换手率 ⬇️ (从大到小)", "turnover_desc")
        self.combo_sort.addItem("💰 成交额 ⬇️ (从大到小)", "amount_desc")
        self.combo_sort.addItem("🔢 标的代码 ⬆️ (默认)", "code_asc")
        self.combo_sort.currentIndexChanged.connect(self._on_sort_combo_changed)
        top_layout.addWidget(self.combo_sort)

        top_layout.addStretch()

        # 搜索过滤输入框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 快速过滤 (代码 / 名称 / 策略 / 形态 / 建议)...")
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        # 重新评估按钮
        self.btn_refresh = QPushButton("🔄 重新评估")
        self.btn_refresh.setObjectName("PrimaryBtn")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.run_evaluation)
        top_layout.addWidget(self.btn_refresh)

        # 复制报告按钮
        self.btn_copy = QPushButton("📋 复制报告")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_full_report)
        top_layout.addWidget(self.btn_copy)

        # 关闭按钮
        self.btn_close = QPushButton("关闭")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        top_layout.addWidget(self.btn_close)

        main_layout.addWidget(top_bar)

        # 2. 中间多视图堆栈容器 (QStackedWidget)
        self.stacked_widget = QStackedWidget()

        # Page 0: 全内容专业表格视图 (直接点击各列表头即可数值排序)
        self.table_all = QTableWidget()
        self.table_all.setColumnCount(len(self.TABLE_HEADERS))
        self.table_all.setHorizontalHeaderLabels(self.TABLE_HEADERS)
        self.table_all.setAlternatingRowColors(True)
        self.table_all.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_all.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_all.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_all.setShowGrid(True)
        self.table_all.setSortingEnabled(True)

        h_header = self.table_all.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # ⭐ 综合评分
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(9, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(10, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(11, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(12, QHeaderView.ResizeMode.Stretch)     # 实操指引
        h_header.setSectionResizeMode(13, QHeaderView.ResizeMode.ResizeToContents)

        self.table_all.setColumnWidth(3, 110)  # ⭐ 综合评分
        self.table_all.setColumnWidth(4, 115)  # 形态分类
        self.table_all.setColumnWidth(5, 140)  # 所属策略
        self.table_all.setColumnWidth(6, 85)   # 现价
        self.table_all.setColumnWidth(7, 95)   # 涨跌幅
        self.table_all.setColumnWidth(8, 85)   # 开盘
        self.table_all.setColumnWidth(9, 85)   # VWAP
        self.table_all.setColumnWidth(10, 85)  # 换手率
        self.table_all.setColumnWidth(11, 95)  # 成交额

        bind_table_column_persistence(self.table_all, "all_codes_eval_table_cols")
        self.table_all.cellDoubleClicked.connect(self._on_table_cell_double_clicked)
        # 绑定点击与键盘上下键联动 TDX
        self.table_all.currentCellChanged.connect(self._on_table_current_cell_changed)
        self.table_all.itemClicked.connect(self._on_table_item_clicked)
        self.stacked_widget.addWidget(self.table_all)

        # Page 1: 流式卡片视图
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background-color: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(6, 6, 6, 6)
        self.cards_layout.setSpacing(10)

        self.scroll_area.setWidget(self.cards_container)
        self.stacked_widget.addWidget(self.scroll_area)

        main_layout.addWidget(self.stacked_widget, 1)

        # 3. 底部状态栏
        bottom_bar = QHBoxLayout()
        self.lbl_status = QLabel("💡 提示：支持鼠标点击或键盘 ↑ / ↓ 键实时联动通达信 (TDX)；点击【⭐ 综合评分】表头可一键排序！")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #64748b;")
        bottom_bar.addWidget(self.lbl_status)
        bottom_bar.addStretch()

        self.lbl_card_count = QLabel("显示 0 / 0 只标的")
        self.lbl_card_count.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: bold;")
        bottom_bar.addWidget(self.lbl_card_count)

        main_layout.addLayout(bottom_bar)

    def _switch_view_mode(self, mode: str):
        """切换表格视图与卡片视图"""
        self.current_view_mode = mode
        if mode == "table":
            self.stacked_widget.setCurrentIndex(0)
            self.btn_view_table.setObjectName("ActiveViewBtn")
            self.btn_view_cards.setObjectName("")
            self.lbl_status.setText("💡 提示：表格各列支持直接点击表头按分数/涨幅精确数值排序；点击或按 ↑ / ↓ 键即时联动 TDX！")
        else:
            self.stacked_widget.setCurrentIndex(1)
            self.btn_view_table.setObjectName("")
            self.btn_view_cards.setObjectName("ActiveViewBtn")
            self.lbl_status.setText("💡 提示：流式卡片模式下点击卡片或按 ↑ / ↓ 键实时联动 TDX；点击【综合得分】快速切换排序！")

        self.btn_view_table.setStyle(self.btn_view_table.style())
        self.btn_view_cards.setStyle(self.btn_view_cards.style())
        self._apply_search_filter()

    def _on_sort_combo_changed(self, index: int):
        """响应排序下拉框切换"""
        sort_key = self.combo_sort.currentData()
        if sort_key:
            self.current_sort_key = sort_key
            self._apply_sort_and_render()

    def _restore_geometry(self):
        """恢复窗口尺寸与位置，并带屏幕边界安全保护"""
        try:
            settings = QSettings("pyQuant3", "AllCodesStrategyEvalDialog")
            saved_geom = settings.value("geometry")
            if saved_geom:
                self.restoreGeometry(saved_geom)
            else:
                self.resize(1000, 680)
                if self.workbench:
                    geo = self.workbench.geometry()
                    self.move(geo.center() - self.rect().center())
            
            saved_mode = settings.value("view_mode", "table")
            if saved_mode in ["table", "cards"]:
                self._switch_view_mode(saved_mode)
        except Exception as e:
            logger.debug(f"恢复 AllCodesStrategyEvalDialog 几何尺寸异常: {e}")
            self.resize(1000, 680)

    def _save_geometry(self):
        """持久化保存窗口尺寸与位置"""
        try:
            settings = QSettings("pyQuant3", "AllCodesStrategyEvalDialog")
            settings.setValue("geometry", self.saveGeometry())
            settings.setValue("view_mode", self.current_view_mode)
            save_ui_layout_state("all_codes_eval_dialog_size", f"{self.width()}x{self.height()}")
        except Exception as e:
            logger.debug(f"保存 AllCodesStrategyEvalDialog 几何尺寸异常: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._save_geometry()

    def closeEvent(self, event):
        self._save_geometry()
        super().closeEvent(event)

    def run_evaluation(self):
        """执行全量标的实时策略评估并构建双视图数据"""
        target_codes = self.engine.get_all_target_codes()
        # 过滤非法代码占位
        valid_codes = [c for c in target_codes if c and c not in ["000000", "000123"]]
        if not valid_codes:
            self.lbl_meta.setText("未配置有效的 target_codes 目标代码")
            return

        now_time_str = datetime.now().strftime("%H:%M:%S")
        self.lbl_meta.setText(f"📊 共 {len(valid_codes)} 只标的 | 评估时间: {now_time_str}")

        self.cards_data.clear()
        res_summary = f"=== ⚡ 全量 Code 分时阶梯策略自动检测评估报告 ({now_time_str}) ===\n\n"

        for c in valid_codes:
            try:
                st = self.engine.auto_select_strategy(0.0, code=c)
                c_name = resolve_stock_name(c)
                parent = self.workbench.parent() if self.workbench else None
                if parent and hasattr(parent, 'get_stock_name'):
                    p_name = parent.get_stock_name(c)
                    if p_name and p_name != "未知" and p_name != c:
                        c_name = p_name

                open_p, trade_p, high_p, low_p, vwap_p, to_rate, amt_val, bid1_p, _, is_unlisted, last_close = self.workbench._get_stock_realtime_data_for_code(c)
                tick_row = {"trade": trade_p, "close": trade_p}
                sigs = self.engine.evaluate_tick(
                    code=c, tick_row=tick_row, open_price=open_p, current_time_str=now_time_str, bid1_price=bid1_p
                )
                eval_res = self.engine.evaluate_seven_nodes(
                    code=c, current_time_str=now_time_str, open_price=open_p, price=trade_p, high_price=high_p,
                    low_price=low_p, vwap=vwap_p, turnover_rate=to_rate, amount=amt_val
                )

                score_val = float(eval_res.get('total_weighted_score', 0.0))
                # 涨跌幅计算（基于开盘或昨收）
                ref_base = last_close if (last_close and last_close > 0) else open_p
                pct_val = ((trade_p - ref_base) / ref_base * 100.0) if ref_base > 0 else 0.0

                item_info = {
                    "code": c,
                    "name": c_name,
                    "strategy_name": st.get('name', '通用分时阶梯策略'),
                    "open_p": open_p,
                    "trade_p": trade_p,
                    "high_p": high_p,
                    "low_p": low_p,
                    "vwap_p": vwap_p,
                    "turnover_rate": to_rate,
                    "amt_val": amt_val,
                    "last_close": last_close,
                    "pct": pct_val,
                    "score": score_val,
                    "pattern": eval_res.get('pattern', '--'),
                    "action_text": eval_res.get('action_execution_text', ''),
                    "signals": sigs,
                    "is_unlisted": is_unlisted,
                    "is_error": False,
                    "error_msg": ""
                }

                # 拼接文本报告
                if is_unlisted:
                    res_summary += f"📌 【{c} {c_name}】 -> 策略: {item_info['strategy_name']} [💡 待上市新股]\n"
                    res_summary += f"   发行价: {open_p:.2f}元 | 状态: 待上市挂牌 | 形态: 【待上市估价】 (模型得分: {score_val:.2f}分)\n"
                    res_summary += f"   实操指引: {item_info['action_text']}\n"
                    res_summary += "--------------------------------------------------\n"
                else:
                    res_summary += f"📌 【{c} {c_name}】 -> 策略: {item_info['strategy_name']}\n"
                    res_summary += f"   开盘: {open_p:.2f}元 | 现价: {trade_p:.2f}元 ({pct_val:+.2f}%) | 综合得分: {score_val:.2f}分 ({item_info['pattern']})\n"
                    res_summary += f"   实操指引: {item_info['action_text']}\n"
                    for sig in sigs:
                        res_summary += f"   🔴 {sig.reason} (建议价: {getattr(sig, 'suggested_price', sig.price):.2f})\n"
                    res_summary += "--------------------------------------------------\n"

            except Exception as e:
                item_info = {
                    "code": c,
                    "name": resolve_stock_name(c),
                    "strategy_name": "未知",
                    "open_p": 0.0,
                    "trade_p": 0.0,
                    "high_p": 0.0,
                    "low_p": 0.0,
                    "vwap_p": 0.0,
                    "turnover_rate": 0.0,
                    "amt_val": 0.0,
                    "last_close": 0.0,
                    "pct": 0.0,
                    "score": 0.0,
                    "pattern": "异常",
                    "action_text": f"评估异常: {e}",
                    "signals": [],
                    "is_unlisted": False,
                    "is_error": True,
                    "error_msg": str(e)
                }
                res_summary += f"⚠️ 【{c}】 评估异常: {e}\n--------------------------------------------------\n"

            self.cards_data.append(item_info)

        self.full_report_text = res_summary
        self._apply_sort_and_render()

    def _apply_sort_and_render(self):
        """根据当前选中的排序规则对数据排序并同步渲染表格与卡片"""
        if not self.cards_data:
            return

        # 排序逻辑
        key_mode = self.current_sort_key
        if key_mode == "score_desc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), -float(x.get('score', 0.0))))
        elif key_mode == "score_asc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), float(x.get('score', 0.0))))
        elif key_mode == "pct_desc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), -float(x.get('pct', 0.0))))
        elif key_mode == "pct_asc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), float(x.get('pct', 0.0))))
        elif key_mode == "turnover_desc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), -float(x.get('turnover_rate', 0.0))))
        elif key_mode == "amount_desc":
            self.cards_data.sort(key=lambda x: (x.get('is_error', False), -float(x.get('amt_val', 0.0))))
        elif key_mode == "code_asc":
            self.cards_data.sort(key=lambda x: str(x.get('code', '')))

        self._render_table()
        self._render_cards()
        self._apply_search_filter()

    def _render_table(self):
        """渲染全内容表格视图"""
        self.table_all.setSortingEnabled(False)
        self.table_all.setRowCount(len(self.cards_data))

        red_color = QColor("#ef4444")
        green_color = QColor("#10b981")
        gray_color = QColor("#94a3b8")
        gold_color = QColor("#ffd700")
        cyan_color = QColor("#38bdf8")

        for row, data in enumerate(self.cards_data):
            c = data['code']
            c_name = data['name']
            score = data['score']
            pct = data['pct']
            is_un = bool(data.get('is_unlisted'))

            # 0. 序号
            _safe_set_cell_item(self.table_all, row, 0, str(row + 1), fg_color=gray_color, align=Qt.AlignmentFlag.AlignCenter, sort_val=row + 1)

            # 1. 代码
            _safe_set_cell_item(self.table_all, row, 1, c, fg_color=cyan_color, align=Qt.AlignmentFlag.AlignCenter, font=QFont("Consolas", 9, QFont.Weight.Bold))

            # 2. 名称 (待上市新股展示专属徽章)
            name_display = f"{c_name} 💡待上市" if is_un else c_name
            name_fg = "#ffd700" if is_un else "#f8fafc"
            _safe_set_cell_item(self.table_all, row, 2, name_display, fg_color=name_fg, align=Qt.AlignmentFlag.AlignCenter, font=QFont("Microsoft YaHei", 9, QFont.Weight.Bold))

            # 3. ⭐ 综合评分 (分级色彩胶囊独立列)
            if is_un:
                score_bg = QColor("#082f49")  # 深蓝科技色
                score_fg = QColor("#38bdf8")
                score_str = f"💡 {score:.2f}分"
                score_tip = f"【待上市新股估价模型】发行基准价: {data['open_p']:.2f}元\n尚未正式挂牌上市交易，已就绪估价推演"
            else:
                score_fg = "#ffffff"
                if score >= 8.0:
                    score_bg = QColor("#064e3b")  # 绿色
                    score_fg = QColor("#34d399")
                elif score >= 6.5:
                    score_bg = QColor("#78350f")  # 橙色
                    score_fg = QColor("#fbbf24")
                else:
                    score_bg = QColor("#7f1d1d")  # 红色
                    score_fg = QColor("#f87171")
                score_str = f"⭐ {score:.2f}分" if not data.get("is_error") else "⚠️ 异常"
                score_tip = f"综合加权评分: {score:.2f}分\n点击此列表头可直接按分数由高到低/由低到高排序"

            _safe_set_cell_item(
                self.table_all, row, 3, score_str,
                fg_color=score_fg, bg_color=score_bg,
                align=Qt.AlignmentFlag.AlignCenter,
                font=QFont("Consolas", 10, QFont.Weight.Bold),
                sort_val=score,
                tooltip=score_tip
            )

            # 4. 形态分类
            pattern_display = "💡 待上市估价" if is_un else data['pattern']
            pattern_fg = cyan_color if is_un else gold_color
            _safe_set_cell_item(self.table_all, row, 4, pattern_display, fg_color=pattern_fg, align=Qt.AlignmentFlag.AlignCenter)

            # 5. 所属策略
            _safe_set_cell_item(self.table_all, row, 5, data['strategy_name'], fg_color="#38bdf8", align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tooltip=data['strategy_name'])

            # 6. 现价
            p_fg = red_color if pct > 0 else (green_color if pct < 0 else gray_color)
            _safe_set_cell_item(self.table_all, row, 6, f"{data['trade_p']:.2f}", fg_color=p_fg, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_val=data['trade_p'])

            # 7. 涨跌幅
            pct_str = f"{pct:+.2f}%" if not data.get("is_error") else "--"
            _safe_set_cell_item(self.table_all, row, 7, pct_str, fg_color=p_fg, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, font=QFont("Consolas", 9, QFont.Weight.Bold), sort_val=pct)

            # 8. 开盘价
            _safe_set_cell_item(self.table_all, row, 8, f"{data['open_p']:.2f}", fg_color="#e2e8f0", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_val=data['open_p'])

            # 9. VWAP
            _safe_set_cell_item(self.table_all, row, 9, f"{data['vwap_p']:.2f}", fg_color="#fbbf24", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_val=data['vwap_p'])

            # 10. 换手率
            to_str = f"{data['turnover_rate']:.2f}%" if not data.get("is_error") else "--"
            _safe_set_cell_item(self.table_all, row, 10, to_str, fg_color=cyan_color, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_val=data['turnover_rate'])

            # 11. 成交额
            amt_val = data['amt_val']
            amt_str = f"{amt_val / 1e8:.2f}亿" if amt_val >= 1e8 else f"{amt_val / 1e4:.0f}万"
            _safe_set_cell_item(self.table_all, row, 11, amt_str, fg_color="#f8fafc", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, sort_val=amt_val)

            # 12. 实操指引与触发卖点
            if is_un:
                full_guide = f"💡 【待上市估价推演】尚未挂牌交易，已载入发行基准价 ({data['open_p']:.2f}元)，估价模型推演就绪"
            else:
                full_guide = data['action_text']
                if data['signals']:
                    sig_texts = [f"🔴 {s.reason}(建议价:{getattr(s, 'suggested_price', s.price):.2f})" for s in data['signals']]
                    full_guide += " | 触发信号: " + "；".join(sig_texts)
            _safe_set_cell_item(self.table_all, row, 12, full_guide, fg_color="#e2e8f0", align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tooltip=full_guide)

            # 13. 操作按钮 (🎯 查看此标的)
            btn_cell = QPushButton("🎯 查看")
            btn_cell.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cell.setStyleSheet("""
                QPushButton {
                    background-color: #0369a1;
                    border: 1px solid #38bdf8;
                    color: #ffffff;
                    font-size: 11px;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #0284c7;
                }
            """)
            target_c = c
            target_n = c_name
            btn_cell.clicked.connect(lambda _, tc=target_c, tn=target_n: self._broadcast_link_stock(tc, tn))
            self.table_all.setCellWidget(row, 13, btn_cell)

        self.table_all.setSortingEnabled(True)

    def _render_cards(self):
        """渲染流式卡片视图"""
        # 清空旧卡片
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.card_widgets.clear()
        for idx, data in enumerate(self.cards_data):
            card_widget = self._create_card_widget(data)
            self.card_widgets.append((data, card_widget))
            self.cards_layout.addWidget(card_widget)

        self.cards_layout.addStretch()

    def _create_card_widget(self, data: dict) -> QFrame:
        """根据标的评估结果创建单只股票的专属卡片"""
        card = QFrame()
        card.setObjectName("StockCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 10, 12, 10)
        c_layout.setSpacing(6)

        target_c = data['code']
        target_n = data['name']

        # 点击整张卡片任意区域自动联动 TDX
        def _on_card_clicked(event):
            self._broadcast_link_stock(target_c, target_n)
        card.mousePressEvent = _on_card_clicked

        # 1. 顶行：代码 + 名称 + 策略名称 + 状态 + 【🎯 查看此标的】
        top_row = QHBoxLayout()
        lbl_code_name = QLabel(f"📌 【{data['code']} {data['name']}】")
        lbl_code_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #f8fafc;")
        top_row.addWidget(lbl_code_name)

        lbl_strat = QLabel(f"策略: {data['strategy_name']}")
        lbl_strat.setStyleSheet("font-size: 12px; color: #38bdf8; background: #082f49; border-radius: 4px; padding: 2px 6px;")
        top_row.addWidget(lbl_strat)

        if data.get("is_unlisted"):
            lbl_un = QLabel("💡 待上市")
            lbl_un.setStyleSheet("font-size: 11px; color: #ffd700; background: #422006; border: 1px solid #ca8a04; border-radius: 4px; padding: 1px 5px;")
            top_row.addWidget(lbl_un)

        top_row.addStretch()

        btn_view = QPushButton("🎯 查看此标的")
        btn_view.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_view.setStyleSheet("""
            QPushButton {
                background-color: #0369a1;
                border: 1px solid #38bdf8;
                color: #ffffff;
                font-size: 11px;
                padding: 3px 10px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0284c7;
            }
        """)
        btn_view.clicked.connect(lambda _, tc=target_c, tn=target_n: self._broadcast_link_stock(tc, tn))
        top_row.addWidget(btn_view)

        c_layout.addLayout(top_row)

        if data.get("is_error"):
            err_lbl = QLabel(f"⚠️ 评估异常: {data.get('error_msg')}")
            err_lbl.setStyleSheet("color: #ef4444; font-size: 12px;")
            c_layout.addWidget(err_lbl)
            return card

        # 2. 行情数据行
        amt_str = f"{data['amt_val'] / 1e8:.2f}亿" if data['amt_val'] >= 1e8 else f"{data['amt_val'] / 1e4:.0f}万"
        pct = data['pct']
        pct_color = "#ef4444" if pct > 0 else ("#10b981" if pct < 0 else "#94a3b8")
        pct_prefix = "+" if pct > 0 else ""

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        stats_text = (
            f"<span style='color:#94a3b8;'>开盘:</span> <b style='color:#f8fafc;'>{data['open_p']:.2f}元</b> &nbsp;|&nbsp; "
            f"<span style='color:#94a3b8;'>现价:</span> <b style='color:{pct_color};'>{data['trade_p']:.2f}元 ({pct_prefix}{pct:.2f}%)</b> &nbsp;|&nbsp; "
            f"<span style='color:#94a3b8;'>VWAP:</span> <b style='color:#fbbf24;'>{data['vwap_p']:.2f}元</b> &nbsp;|&nbsp; "
            f"<span style='color:#94a3b8;'>换手率:</span> <b style='color:#38bdf8;'>{data['turnover_rate']:.2f}%</b> &nbsp;|&nbsp; "
            f"<span style='color:#94a3b8;'>成交额:</span> <b style='color:#f8fafc;'>{amt_str}</b>"
        )
        lbl_stats = QLabel(stats_text)
        lbl_stats.setStyleSheet("font-size: 12px;")
        stats_row.addWidget(lbl_stats)
        stats_row.addStretch()

        # 评分与形态胶囊 (点击可快速切换评分升/降序)
        score = data['score']
        is_un = bool(data.get("is_unlisted"))
        if is_un:
            score_bg = "#082f49"
            score_border = "#38bdf8"
            score_title = f"🌟 估价模型: {score:.2f}分  (待上市估价)"
        else:
            score_bg = "#064e3b" if score >= 8.0 else ("#78350f" if score >= 6.5 else "#7f1d1d")
            score_border = "#10b981" if score >= 8.0 else ("#f59e0b" if score >= 6.5 else "#ef4444")
            score_title = f"🌟 综合得分: {score:.2f}分  ({data['pattern']})"
        
        btn_score = QPushButton(score_title)
        btn_score.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_score.setToolTip("💡 点击快速按综合评分由高到低/由低到高重排")
        btn_score.setStyleSheet(f"""
            QPushButton {{
                background-color: {score_bg};
                border: 1px solid {score_border};
                border-radius: 4px;
                color: #f8fafc;
                font-size: 11px;
                font-weight: bold;
                padding: 3px 8px;
            }}
            QPushButton:hover {{
                border: 1px solid #ffffff;
                background-color: #0284c7;
            }}
        """)
        btn_score.clicked.connect(self._toggle_score_sort)
        stats_row.addWidget(btn_score)

        c_layout.addLayout(stats_row)

        # 3. 实操指引
        act_text = f"【待上市估价推演】尚未正式挂牌上市交易，已自动载入发行基准价 ({data['open_p']:.2f}元)。可在分时工作台中开启【💡 开启手动估价】自由推演 7 节点买卖点。" if is_un else data['action_text']
        if act_text:
            act_box = QFrame()
            act_box.setStyleSheet("background-color: #1e293b; border-radius: 4px; padding: 4px;")
            act_layout = QHBoxLayout(act_box)
            act_layout.setContentsMargins(8, 4, 8, 4)
            lbl_act = QLabel(f"💡 <b>实操指引:</b> {act_text}")
            lbl_act.setWordWrap(True)
            lbl_act.setStyleSheet("color: #e2e8f0; font-size: 12px;")
            act_layout.addWidget(lbl_act)
            c_layout.addWidget(act_box)

        # 4. 触发信号列表 (待上市新股绝对不展示实盘卖出信号)
        if not is_un and data['signals']:
            sig_box = QFrame()
            sig_box.setStyleSheet("background-color: #18181b; border: 1px dashed #ef4444; border-radius: 4px; padding: 4px;")
            sig_layout = QVBoxLayout(sig_box)
            sig_layout.setContentsMargins(8, 4, 8, 4)
            sig_layout.setSpacing(2)
            for sig in data['signals']:
                s_price = getattr(sig, 'suggested_price', sig.price)
                lbl_sig = QLabel(f"🔴 <b>{sig.reason}</b> (触发建议价: <span style='color:#ef4444;'>{s_price:.2f}元</span>)")
                lbl_sig.setStyleSheet("color: #f87171; font-size: 11px;")
                sig_layout.addWidget(lbl_sig)
            c_layout.addWidget(sig_box)

        return card

    def _toggle_score_sort(self):
        """点击评分徽章快速在评分降序与升序之间切换"""
        if self.current_sort_key == "score_desc":
            new_key = "score_asc"
        else:
            new_key = "score_desc"
        
        # 联动下拉框
        idx = self.combo_sort.findData(new_key)
        if idx >= 0:
            self.combo_sort.setCurrentIndex(idx)
        else:
            self.current_sort_key = new_key
            self._apply_sort_and_render()

    def _on_table_cell_double_clicked(self, row: int, col: int):
        """双击表格行直接切入主工作台"""
        code_item = self.table_all.item(row, 1)
        name_item = self.table_all.item(row, 2)
        if code_item:
            target_code = code_item.text().strip()
            target_name = name_item.text().strip() if name_item else resolve_stock_name(target_code)
            if target_code:
                self._broadcast_link_stock(target_code, target_name)
        
        # 若双击指引列，同时弹出完整文本悬浮窗
        if col == 12:
            handle_table_cell_double_click(self.table_all, row, col, self)

    def _on_table_current_cell_changed(self, currentRow: int, currentColumn: int, previousRow: int, previousColumn: int):
        """键盘上下键导航与鼠标行选择统一防抖联动入口"""
        if currentRow < 0 or currentRow >= self.table_all.rowCount():
            return
        if currentRow == self._pending_linkage_row:
            return
        self._pending_linkage_row = currentRow
        self._linkage_timer.start()

    def _on_table_item_clicked(self, item):
        """鼠标单击单元格立即触发 TDX 联动"""
        if not item or item.row() < 0:
            return
        self._pending_linkage_row = item.row()
        self._fire_linkage_debounced()

    def _fire_linkage_debounced(self):
        """防抖定时器到期后执行真实 TDX 与工作台联动"""
        row = self._pending_linkage_row
        if row < 0 or row >= self.table_all.rowCount():
            return
        code_item = self.table_all.item(row, 1)
        name_item = self.table_all.item(row, 2)
        if code_item:
            c = code_item.text().strip()
            n = name_item.text().strip() if name_item else resolve_stock_name(c)
            if c and c != "N/A":
                self._broadcast_link_stock(c, n)

    def _broadcast_link_stock(self, code: str, name: str = None):
        """
        ⚡ [ATS 现成联动标准实现] 毫秒级直连通达信 (TDX)、同花顺与 ATS 主窗口
        1. 过滤与提取 6 位标准股票代码
        2. 调用 ATSMainWindow.link_stock 向全局可视化服务器与终端广播
        3. 调用 linkage_service.get_link_manager().push() 物理直连通达信
        4. 联动独立工作台切代码
        5. 底部状态栏反馈
        """
        if not code:
            return
        code_clean = str(code).strip()
        c_digits = "".join(x for x in code_clean if x.isdigit()).zfill(6) if any(x.isdigit() for x in code_clean) else code_clean
        st_name = str(name) if name and name != "未知" else resolve_stock_name(c_digits)

        now = time.time()
        if self._last_linked_code == c_digits and (now - self._last_linked_time) < 0.15:
            return
        self._last_linked_code = c_digits
        self._last_linked_time = now

        # 1. 优先通过 ATS 全局主窗口广播 (覆盖 TCP 26668 可视化与外部终端)
        try:
            from ats.ui.main_window import ATSMainWindow
            app = QApplication.instance()
            if hasattr(app, 'main_window') and isinstance(app.main_window, ATSMainWindow):
                app.main_window.link_stock(c_digits, st_name)
        except Exception as e_app:
            logger.debug(f"[ATS Linkage] main_window.link_stock 异常: {e_app}")

        # 2. 遍历全局顶级窗口联动具有 link_stock 的工作台
        try:
            for w in QApplication.topLevelWidgets():
                if w is not self and hasattr(w, "link_stock") and callable(getattr(w, "link_stock")):
                    try:
                        w.link_stock(c_digits, st_name)
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. 物理直连通达信 (TDX) / 同花顺 (LinkManager)
        try:
            from linkage_service import get_link_manager
            get_link_manager().push(c_digits, flags={'tdx': True, 'ths': True, 'dfcf': False}, auto=False)
        except Exception as e_tdx:
            logger.debug(f"[TDX Linkage] 物理推送异常: {e_tdx}")

        # 4. 同步切换当前独立分时工作台标的与走势图
        if self.workbench and hasattr(self.workbench, 'combo_code'):
            for idx in range(self.workbench.combo_code.count()):
                if self.workbench.combo_code.itemData(idx) == c_digits:
                    if self.workbench.combo_code.currentIndex() != idx:
                        self.workbench.combo_code.setCurrentIndex(idx)
                    break

        # 5. 底部状态栏反馈
        self.lbl_status.setText(f"🔗 【TDX 联动成功】已同步切换通达信行情与分时工作台: 【{c_digits} {st_name}】")

    def _switch_to_code(self, target_code: str):
        """兼容接口：切换并联动标的"""
        self._broadcast_link_stock(target_code, resolve_stock_name(target_code))

    def _toggle_stay_on_top(self):
        """切换窗口置顶状态 (快捷键: T, 无缝 0 闪烁)"""
        self._is_stay_on_top = not getattr(self, '_is_stay_on_top', False)
        set_seamless_stay_on_top(self, self._is_stay_on_top)
        if hasattr(self, 'lbl_status') and self.lbl_status:
            txt = "开启" if self._is_stay_on_top else "关闭"
            self.lbl_status.setText(f"📌 [窗口置顶: {txt}] (快捷键: T 开启/关闭置顶)")

    def keyPressEvent(self, event):
        """键盘事件处理：支持快捷键 T 切换置顶，卡片视图下的键盘上下键切换联动"""
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_T and not (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            from ats.ui.styles import is_editing_text
            if not is_editing_text(self):
                self._toggle_stay_on_top()
                event.accept()
                return
        if self.current_view_mode == "cards" and self.card_widgets:
            if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Left):
                self._navigate_cards(-1)
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Right):
                self._navigate_cards(1)
                event.accept()
                return
        super().keyPressEvent(event)

    def _navigate_cards(self, delta: int):
        """在卡片流中按上下键移动选中项并触发联动"""
        visible_cards = [(idx, data, w) for idx, (data, w) in enumerate(self.card_widgets) if w.isVisible()]
        if not visible_cards:
            return
        if self.selected_card_index < 0:
            new_idx = 0
        else:
            cur_pos = 0
            for i, (idx, _, _) in enumerate(visible_cards):
                if idx == self.selected_card_index:
                    cur_pos = i
                    break
            new_pos = max(0, min(len(visible_cards) - 1, cur_pos + delta))
            new_idx = visible_cards[new_pos][0]

        self.selected_card_index = new_idx
        # 高亮与联动
        for idx, (data, w) in enumerate(self.card_widgets):
            if idx == new_idx:
                w.setStyleSheet("QFrame#StockCard { background-color: #1e3a8a; border: 2px solid #38bdf8; border-radius: 8px; }")
                self.scroll_area.ensureWidgetVisible(w)
                self._broadcast_link_stock(data['code'], data['name'])
            else:
                w.setStyleSheet("")

    def _on_search_text_changed(self, text: str):
        """实时关键词搜索过滤"""
        self._apply_search_filter()

    def _apply_search_filter(self):
        """应用搜索过滤到当前激活的视图"""
        kw = self.search_edit.text().strip().lower()
        visible_cnt = 0

        if self.current_view_mode == "table":
            # 表格过滤
            for row in range(self.table_all.rowCount()):
                if not kw:
                    self.table_all.setRowHidden(row, False)
                    visible_cnt += 1
                else:
                    row_text = ""
                    for c in [1, 2, 4, 5, 12]:  # 搜索代码、名称、形态、策略、指引
                        it = self.table_all.item(row, c)
                        if it:
                            row_text += it.text().lower() + " "
                    match = kw in row_text
                    self.table_all.setRowHidden(row, not match)
                    if match:
                        visible_cnt += 1
        else:
            # 卡片过滤
            for item_data, widget in self.card_widgets:
                if not kw:
                    widget.setVisible(True)
                    visible_cnt += 1
                else:
                    match = (
                        kw in str(item_data.get('code', '')).lower() or
                        kw in str(item_data.get('name', '')).lower() or
                        kw in str(item_data.get('strategy_name', '')).lower() or
                        kw in str(item_data.get('pattern', '')).lower() or
                        kw in str(item_data.get('action_text', '')).lower() or
                        kw in str(f"{item_data.get('score', 0.0):.2f}")
                    )
                    widget.setVisible(match)
                    if match:
                        visible_cnt += 1

        self._update_card_count(visible_cnt)

    def _update_card_count(self, visible_cnt: int = None):
        total = len(self.cards_data)
        shown = visible_cnt if visible_cnt is not None else total
        mode_str = "全内容表格" if self.current_view_mode == "table" else "流式卡片"
        self.lbl_card_count.setText(f"显示 {shown} / {total} 只标的 | 视图: {mode_str}")

    def _copy_full_report(self):
        """一键复制全量纯文本报告到系统剪贴板"""
        if not self.full_report_text:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.full_report_text)
            self.lbl_status.setText("📋 全量评估报告已成功复制到剪贴板！")


# 补充 PinzhunLaserMonitorWidget 类的定义供 Tab 3 使用（带滚动条位置保持保护）
class PinzhunLaserMonitorWidget(QWidget):
    """
    新股上市专属盯盘与动态评分实操看板组件 (Tab 3)
    全自动由实时推送的 df / TDX 秒级行情获取换手率、成交量、成交额、最高最低价并自动填表打分
    100% 动态自适应不同标的（688826、688835、688836等）的发行价、阶梯价位与流通盘
    """
    score_changed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.code = "688826"
        self._current_spec_code = None
        self._is_updating = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(8)

        # 1. 🔑 关键阈值速查与量能档位面板（动态容器）
        self.card_spec = QGroupBox("🔑 关键阈值速查与量能档位面板")
        self.card_spec.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        self.spec_layout = QGridLayout(self.card_spec)
        self.spec_layout.setContentsMargins(10, 14, 10, 8)
        self.spec_layout.setSpacing(8)

        self._refresh_spec_card(self.code)
        content_layout.addWidget(self.card_spec)

        # 2. 🎯 七节点实盘观察表
        node_group = QGroupBox("🎯 七节点实盘观察表（通过行情/估价自动解析换手率、成交量与价格，自动填表打分）")
        node_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #ffd700; background-color: #14141d; }")
        node_layout = QVBoxLayout(node_group)
        node_layout.setContentsMargins(6, 14, 6, 6)

        top_bar = QHBoxLayout()
        lbl_hint = QLabel("⚡ 全自动模式：数据根据行情/估价自动计算；您也可在【节点评分】列手动微调分值。")
        lbl_hint.setStyleSheet("color: #00ff88; font-size: 8.5pt; font-weight: bold;")
        
        btn_reset_scores = QPushButton("🔄 重置为自动打分")
        btn_reset_scores.setStyleSheet("background-color: #242436; color: #38bdf8; font-weight: bold; border: 1px solid #38bdf8; border-radius: 3px; padding: 2px 8px;")
        btn_reset_scores.clicked.connect(self._on_reset_scores)

        top_bar.addWidget(lbl_hint)
        top_bar.addStretch()
        top_bar.addWidget(btn_reset_scores)
        node_layout.addLayout(top_bar)

        self.table_nodes = QTableWidget()
        self.table_nodes.setColumnCount(9)
        self.table_nodes.setHorizontalHeaderLabels([
            "#", "时间节点", "观察项目", "强势信号（打✓）", "风险信号（打✓）",
            "实际观察值\n(实时df/估价自动获取)", "信号判定\n强/中/弱", "节点评分\n(0-10分)", "备注/应对"
        ])
        self.table_nodes.setAlternatingRowColors(True)
        self.table_nodes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_nodes.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1a1a26; color: #ffd700; font-weight: bold; padding: 4px; border: 1px solid #2a2a38; }")
        
        h_header = self.table_nodes.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        h_header.setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)

        self.table_nodes.setColumnWidth(1, 95)
        self.table_nodes.setColumnWidth(2, 95)
        self.table_nodes.setColumnWidth(5, 150)
        self.table_nodes.setColumnWidth(7, 85)
        self.table_nodes.setMinimumHeight(240)

        # 绑定列宽落盘与单元格双击悬浮弹窗查看完整备注
        bind_table_column_persistence(self.table_nodes, "tab3_table_nodes_col_widths")
        self.table_nodes.cellDoubleClicked.connect(lambda r, c: handle_table_cell_double_click(self.table_nodes, r, c, self))

        node_layout.addWidget(self.table_nodes)
        content_layout.addWidget(node_group)

        # 3. 📋 综合评分汇总与形态判定
        summary_group = QGroupBox("📋 综合评分汇总（自动计算加权得分、形态分类与 T+1 操作建议）")
        summary_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(6, 14, 6, 6)

        self.table_summary = QTableWidget()
        self.table_summary.setColumnCount(9)
        self.table_summary.setHorizontalHeaderLabels([
            "评分项", "时间", "节点分(0-10)", "权重", "加权得分",
            "首日涨幅", "换手率", "收盘/最高价", "形态分类"
        ])
        self.table_summary.setAlternatingRowColors(True)
        self.table_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_summary.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1e2638; color: #38bdf8; font-weight: bold; padding: 4px; border: 1px solid #2a2a38; }")
        
        sum_header = self.table_summary.horizontalHeader()
        sum_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_summary.setMinimumHeight(280)

        summary_layout.addWidget(self.table_summary)
        content_layout.addWidget(summary_group)

        # 4. 📝 实盘盯盘使用说明
        guide_group = QGroupBox("📝 实盘盯盘使用说明与应对规则（7条核心法则）")
        guide_group.setStyleSheet("QGroupBox { border: 1px solid #303042; border-radius: 6px; margin-top: 4px; font-weight: bold; color: #a0a0d0; background-color: #14141d; }")
        guide_layout = QVBoxLayout(guide_group)
        guide_layout.setContentsMargins(8, 12, 8, 8)

        self.lbl_guide = QLabel()
        self.lbl_guide.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_guide.setStyleSheet("color: #b0b0c8; font-size: 8.5pt; line-height: 140%;")
        self.lbl_guide.setWordWrap(True)
        self._refresh_guide_text(self.code)
        guide_layout.addWidget(self.lbl_guide)
        content_layout.addWidget(guide_group)

        self.scroll_area.setWidget(content_widget)
        main_layout.addWidget(self.scroll_area)

    def _refresh_spec_card(self, code: str):
        """根据当前标的重新渲染顶部阈值卡片（支持5档/6档价格阶梯与不同流通盘）"""
        c_clean = str(code).zfill(6)
        spec = self.engine.get_stock_ladder_spec(c_clean)
        is_first_day = self.engine.is_stock_first_listing_day(c_clean)
        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        if issue_p <= 0:
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
                if c_clean in ipo_dict:
                    issue_p = float(ipo_dict[c_clean].get("issue_price", 0.0) or 0.0)
            except Exception:
                pass
        float_shares_wan = float(spec.get("float_shares_wan", 1000.0))
        float_mv = float(spec.get("float_mv_yi", 15.0))
        lottery = spec.get("lottery_rate", "--")
        name = spec.get("name", resolve_stock_name(c_clean))

        price_tag_name = "发行价" if (is_first_day or "上市" in str(spec.get("note", ""))) else "基准价"
        self.card_spec.setTitle(
            f"🔑 【{name}】关键阈值速查（{price_tag_name} {issue_p:.2f} 元 | 流通股≈{float_shares_wan:.2f}万股 | 流通市值≈{float_mv:.2f}亿 | 中签率 {lottery}）"
        )

        # 清空已有子控件
        while self.spec_layout.count():
            item = self.spec_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        price_ladder = spec.get("price_ladder", [])
        colors = ["#00ff88", "#ffd700", "#ffaa44", "#ff5555", "#ff00ff", "#00ffff"]
        cols = max(len(price_ladder), 5)

        for i, ld in enumerate(price_ladder):
            p_val = float(ld.get("price", 0.0))
            p_name = ld.get("name", "")
            p_mean = ld.get("meaning", "")
            lbl = QLabel(f"<b>{p_name}</b>: {p_val:.2f}元 ({p_mean})")
            c_idx = i % len(colors)
            lbl.setStyleSheet(f"color: {colors[c_idx]}; font-size: 9pt; {'font-weight: bold;' if i==1 else ''}")
            self.spec_layout.addWidget(lbl, 0, i)

        lbl_t1 = QLabel("<b>换手档位</b>: 弱(<40%) | 标准(50-70%健康) | 高(70-90%充分) | 极高(>90%过热)")
        lbl_t1.setStyleSheet("color: #a0a0c0; font-size: 9pt;")
        
        self.lbl_intensity = QLabel(f"<b>资金强度</b>: 成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强 [当前: --]")
        self.lbl_intensity.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 9pt;")

        span_left = max(1, cols - 2)
        self.spec_layout.addWidget(lbl_t1, 1, 0, 1, span_left)
        self.spec_layout.addWidget(self.lbl_intensity, 1, span_left, 1, cols - span_left)
        self._current_spec_code = c_clean

    def _refresh_guide_text(self, code: str):
        c_clean = str(code).zfill(6)
        spec = self.engine.get_stock_ladder_spec(c_clean)
        float_mv = float(spec.get("float_mv_yi", 15.0))
        guide_txt = (
            f"1. <b>节点观察</b>: 每个时间节点到达时，系统自动抓取价格/涨幅/换手/量能/VWAP；<br>"
            f"2. <b>信号判定</b>: 自动判定 \"强\" / \"中\" / \"弱\" 并高亮呈现；<br>"
            f"3. <b>节点评分</b>: 强=8-10分，中=5-7分，弱=0-4分；<br>"
            f"4. <b>加权得分</b>: 自动计算 (加权得分 = 节点分 × 权重)；<br>"
            f"5. <b>形态判定</b>: <b>综合得分≥8.0</b> → A型超强趋势(★关注次日竞价接力)；<b>6.5-8.0</b> → B型(★观察回踩承接)；<b>5.0-6.5</b> → C型(★冲高兑现)；<b><5.0</b> → D/E型(★弱势回避)；<br>"
            f"6. <b>重点监控</b>: <b>成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强</b>；<b>收盘/最高 > 90% 为超强锁仓</b>；<br>"
            f"7. <b>同板块联动</b>: 同步观察关联板块龙头走势，确认资金协同性与做多共识。"
        )
        self.lbl_guide.setText(guide_txt)

    def _on_reset_scores(self):
        state = self.engine._get_stock_state(self.code, 0.0)
        state["manual_scores"].clear()
        self.score_changed_signal.emit()

    def update_monitor_data(
        self,
        code: str,
        open_price: float,
        price: float,
        high_price: float,
        low_price: float,
        vwap: float,
        turnover_rate: float,
        amount: float,
        current_time_str: str
    ):
        """全面刷新盯盘看板数据（带全局滚动条锁定保护）"""
        self.code = code
        c_clean = str(code).zfill(6)
        if getattr(self, "_current_spec_code", None) != c_clean:
            self._refresh_spec_card(c_clean)
            self._refresh_guide_text(c_clean)

        # 保护外层 ScrollArea 滚动条位置
        outer_sb = self.scroll_area.verticalScrollBar()
        saved_outer_pos = outer_sb.value()

        res = self.engine.evaluate_seven_nodes(
            code=code,
            current_time_str=current_time_str,
            open_price=open_price,
            price=price,
            high_price=high_price,
            low_price=low_price,
            vwap=vwap,
            turnover_rate=turnover_rate,
            amount=amount
        )

        spec = self.engine.get_stock_ladder_spec(code)
        float_mv = float(spec.get("float_mv_yi", 14.24))
        intensity_val = res.get("intensity_ratio", 0.0)
        int_str = f"{intensity_val:.2f}x"
        int_color = "#00ff88" if intensity_val >= 2.5 else "#38bdf8"
        if hasattr(self, 'lbl_intensity'):
            self.lbl_intensity.setText(
                f"<b>资金强度</b>: 成交额/流通市值({float_mv:.2f}亿) > 2.5x 为极强 [当前: <font color='{int_color}'>{int_str}</font>]"
            )

        node_results = res.get("node_results", [])
        if self.table_nodes.rowCount() != len(node_results):
            self.table_nodes.setRowCount(len(node_results))

        self._is_updating = True

        for row, nr in enumerate(node_results):
            n_id = nr["node_id"]
            _set_or_update_table_item(self.table_nodes, row, 0, nr["node_num"], align=Qt.AlignmentFlag.AlignCenter)

            fg_t = QColor("#00ff88") if nr["is_active"] else (QColor("#888899") if nr["is_completed"] else None)
            bg_t = QColor("#1a2e24") if nr["is_active"] else None
            _set_or_update_table_item(self.table_nodes, row, 1, f"{nr['name']}\n({nr['time_str']})", fg_color=fg_t, bg_color=bg_t, align=Qt.AlignmentFlag.AlignCenter)

            _set_or_update_table_item(self.table_nodes, row, 2, nr["focus"], tooltip=nr["focus"])
            _set_or_update_table_item(self.table_nodes, row, 3, nr["strong_signals"], fg_color="#00ff88", tooltip=nr["strong_signals"])
            _set_or_update_table_item(self.table_nodes, row, 4, nr["risk_signals"], fg_color="#ff5555", tooltip=nr["risk_signals"])
            _set_or_update_table_item(self.table_nodes, row, 5, nr["observed_val"], fg_color="#ffd700", tooltip=nr["observed_val"])

            judg = nr["judgment"]
            fg_j = QColor("#00ff88") if judg == "强" else (QColor("#38bdf8") if judg == "中" else QColor("#ff4444"))
            bg_j = QColor("#163322") if judg == "强" else (QColor("#162838") if judg == "中" else QColor("#331616"))
            _set_or_update_table_item(self.table_nodes, row, 6, judg, fg_color=fg_j, bg_color=bg_j, align=Qt.AlignmentFlag.AlignCenter)

            spin = self.table_nodes.cellWidget(row, 7)
            if not isinstance(spin, QDoubleSpinBox):
                spin = QDoubleSpinBox()
                spin.setRange(0.0, 10.0)
                spin.setSingleStep(0.5)
                spin.setStyleSheet("background-color: #1e1e2d; color: #ffd700; font-weight: bold; border: 1px solid #38bdf8;")
                spin.valueChanged.connect(self._make_spin_handler(row, n_id))
                self.table_nodes.setCellWidget(row, 7, spin)

            spin.blockSignals(True)
            spin.setValue(float(nr["final_score"]))
            spin.blockSignals(False)

            remark_text = f"{nr['remarks']} | {nr['action_guide']}"
            _set_or_update_table_item(self.table_nodes, row, 8, remark_text, tooltip=remark_text)

        if self.table_summary.rowCount() != 10:
            self.table_summary.setRowCount(10)

        tot_score = res.get("total_weighted_score", 0.0)
        pattern = res.get("pattern", "--")
        t1_advice = res.get("t1_advice", "--")
        pat_color = res.get("pattern_color", "#00ff88")

        for row, nr in enumerate(node_results):
            _set_or_update_table_item(self.table_summary, row, 0, f"{nr['name']}({nr['time_str']})")
            _set_or_update_table_item(self.table_summary, row, 1, nr["time_str"], align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 2, f"{nr['final_score']:.1f}", align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 3, nr["weight_pct"], fg_color="#38bdf8", align=Qt.AlignmentFlag.AlignCenter)
            _set_or_update_table_item(self.table_summary, row, 4, f"{nr['weighted_score']:.2f}", align=Qt.AlignmentFlag.AlignCenter)

            if row == 0:
                _set_or_update_table_item(self.table_summary, row, 5, f"{res.get('gain_from_issue', 0.0):+.1f}%", fg_color="#00ff88")
                _set_or_update_table_item(self.table_summary, row, 6, f"{res.get('turnover_rate', 0.0):.1f}%")
                _set_or_update_table_item(self.table_summary, row, 7, f"{res.get('close_high_ratio', 1.0)*100:.1f}%")
                _set_or_update_table_item(self.table_summary, row, 8, pattern, fg_color=pat_color, font=QFont("Arial", 9, QFont.Weight.Bold))
            else:
                for c in range(5, 9):
                    _set_or_update_table_item(self.table_summary, row, c, "")

        r_sum = 7
        score_fg = "#ff0055" if tot_score < 5 else ("#00ff88" if tot_score >= 8 else "#ffd700")
        _set_or_update_table_item(self.table_summary, r_sum, 0, "综合得分", fg_color="#38bdf8", font=QFont("Arial", 9, QFont.Weight.Bold))
        _set_or_update_table_item(self.table_summary, r_sum, 1, "合计", align=Qt.AlignmentFlag.AlignCenter)
        _set_or_update_table_item(self.table_summary, r_sum, 2, "")
        _set_or_update_table_item(self.table_summary, r_sum, 3, "100%", fg_color="#38bdf8", align=Qt.AlignmentFlag.AlignCenter)
        _set_or_update_table_item(self.table_summary, r_sum, 4, f"{tot_score:.2f}", fg_color=score_fg, bg_color="#2d2218", font=QFont("Arial", 10, QFont.Weight.Bold), align=Qt.AlignmentFlag.AlignCenter)
        for c in range(5, 9):
            _set_or_update_table_item(self.table_summary, r_sum, c, "")

        r_pat = 8
        _set_or_update_table_item(self.table_summary, r_pat, 0, "形态判定", font=QFont("Arial", 9, QFont.Weight.Bold))
        for c in range(1, 8):
            _set_or_update_table_item(self.table_summary, r_pat, c, "")
        _set_or_update_table_item(self.table_summary, r_pat, 8, f"【{pattern}】", fg_color=pat_color, bg_color="#22182d", font=QFont("Arial", 10, QFont.Weight.Bold))

        r_t1 = 9
        _set_or_update_table_item(self.table_summary, r_t1, 0, "T+1建议", font=QFont("Arial", 9, QFont.Weight.Bold))
        for c in range(1, 8):
            _set_or_update_table_item(self.table_summary, r_t1, c, "")
        _set_or_update_table_item(self.table_summary, r_t1, 8, t1_advice, fg_color=pat_color, font=QFont("Arial", 9, QFont.Weight.Bold))

        self._is_updating = False

        # 恢复外层滚动条位置
        outer_sb.setValue(saved_outer_pos)

    def _make_spin_handler(self, row: int, node_id: str):
        def _handler(val: float):
            if not self._is_updating:
                self.engine.set_manual_node_score(self.code, node_id, val)
                self.score_changed_signal.emit()
        return _handler


class IntradaySimulationWidget(QWidget):
    """
    8/18 开盘实盘全天分时模拟回测与情景演练面板 (Tab 2)
    支持 A/B/C/D 4大情景、一键秒级全天回测与分时动态逐帧回放
    """
    tick_emitted_signal = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.engine = IntradayStrategyEngine.get_instance()
        self.sim_df: Optional[pd.DataFrame] = None
        self.current_frame_idx = 0
        self.replay_timer = QTimer(self)
        self.replay_timer.timeout.connect(self._on_replay_step)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 1. 顶部情景选择与操作控制栏
        ctrl_group = QGroupBox("🎮 8/18 开盘分时模拟情景演练与全天回测控制")
        ctrl_group.setStyleSheet("QGroupBox { border: 1px solid #38bdf8; border-radius: 6px; margin-top: 6px; font-weight: bold; color: #38bdf8; background-color: #14141d; }")
        ctrl_layout = QHBoxLayout(ctrl_group)
        ctrl_layout.setContentsMargins(10, 14, 10, 10)
        ctrl_layout.setSpacing(10)

        lbl_sc = QLabel("🎯 演练情景:")
        lbl_sc.setStyleSheet("color: #ffd700; font-weight: bold;")
        self.combo_scenario = QComboBox()
        self.combo_scenario.setStyleSheet("background-color: #1e1e2d; color: #00ff88; font-weight: bold; min-width: 320px; padding: 4px;")
        self.combo_scenario.addItem("🚀 情景1: A型·超强主升主线 (+210%高开 -> 冲高 -> +30%临停 -> 815元锁仓)", "A_SUPER_TREND")
        self.combo_scenario.addItem("📈 情景2: B型·强势换手洗盘 (+162%高开 -> 冲高 -> 均线强承接 -> 540元健康收盘)", "B_STRONG_TURNOVER")
        self.combo_scenario.addItem("📉 情景3: C型·冲高兑现回落 (+108%开盘 -> 冲高卖出50% -> 破均线兑现 -> 355元回落)", "C_SURGE_AND_CASH")
        self.combo_scenario.addItem("⚠️ 情景4: D/E型·高开低走衰竭 (+125%开盘 -> 放量砸盘破位 -> 阴跌跳水 -> 310元清仓)", "D_WEAK_EXHAUSTION")

        btn_run_full = QPushButton("⚡ 一键全天秒级回测")
        btn_run_full.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; padding: 5px 14px; border-radius: 4px;")
        btn_run_full.clicked.connect(self._on_run_full_backtest)

        self.btn_play = QPushButton("▶️ 分时动态逐帧回放")
        self.btn_play.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; border: 1px solid #00ff88; padding: 5px 14px; border-radius: 4px;")
        self.btn_play.clicked.connect(self._on_toggle_play)

        btn_reset = QPushButton("⏮️ 重置")
        btn_reset.setStyleSheet("background-color: #333344; color: white; padding: 5px 12px; border-radius: 4px;")
        btn_reset.clicked.connect(self._on_reset_replay)

        lbl_spd = QLabel("速度:")
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["5x 快速", "10x 极速", "1x 真实", "20x 飞速"])
        self.combo_speed.setStyleSheet("background-color: #1e1e2d; color: #e0e0e0;")

        ctrl_layout.addWidget(lbl_sc)
        ctrl_layout.addWidget(self.combo_scenario)
        ctrl_layout.addWidget(btn_run_full)
        ctrl_layout.addWidget(self.btn_play)
        ctrl_layout.addWidget(btn_reset)
        ctrl_layout.addWidget(lbl_spd)
        ctrl_layout.addWidget(self.combo_speed)
        ctrl_layout.addStretch()

        layout.addWidget(ctrl_group)

        # 2. 进度条与当前回放状态
        prog_box = QHBoxLayout()
        self.lbl_replay_status = QLabel("⏱️ 回放进度: 0 / 241 分钟 (待开始)")
        self.lbl_replay_status.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 9.5pt;")
        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setRange(0, 241)
        self.slider_progress.setValue(0)
        self.slider_progress.sliderMoved.connect(self._on_slider_moved)
        self.slider_progress.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #252535; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #00ff88; border-radius: 3px; }
            QSlider::handle:horizontal { background: #ffd700; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }
        """)

        prog_box.addWidget(self.lbl_replay_status)
        prog_box.addWidget(self.slider_progress, 1)
        layout.addLayout(prog_box)

        # 3. 回测结果总览卡片与阶梯指令流水 Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：回测报告与评分演进
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.txt_backtest_report = QTextEdit()
        self.txt_backtest_report.setReadOnly(True)
        self.txt_backtest_report.setStyleSheet("background-color: #0e0e14; color: #38bdf8; font-family: Consolas, Monospace; font-size: 9.5pt;")
        left_layout.addWidget(QLabel("📊 8/18 模拟回测总览与评分诊断报告:"))
        left_layout.addWidget(self.txt_backtest_report)
        splitter.addWidget(left_widget)

        # 右侧：买卖点阶梯信号流水
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.table_sim_signals = QTableWidget()
        self.table_sim_signals.setColumnCount(5)
        self.table_sim_signals.setHorizontalHeaderLabels(["时间", "买卖动作", "执行价", "卖出比例", "触发规则/理由"])
        self.table_sim_signals.setAlternatingRowColors(True)
        self.table_sim_signals.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_sim_signals.setStyleSheet("QTableWidget { background-color: #101017; gridline-color: #252535; color: #d0d0e0; font-size: 9pt; } QHeaderView::section { background-color: #1a1a26; color: #00ff88; font-weight: bold; padding: 4px; }")
        
        h_h = self.table_sim_signals.horizontalHeader()
        h_h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        right_layout.addWidget(QLabel("⚡ 阶梯交易买卖点触发明细与实盘挂单流水:"))
        right_layout.addWidget(self.table_sim_signals)
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 650])
        layout.addWidget(splitter, 1)

    def _get_current_code(self) -> str:
        parent = self.parent()
        while parent:
            if hasattr(parent, 'code') and getattr(parent, 'code'):
                return str(getattr(parent, 'code')).zfill(6)
            parent = parent.parent()
        return "688826"

    def _ensure_scenario_df(self):
        sc_type = self.combo_scenario.currentData()
        cur_code = self._get_current_code()
        last_code = getattr(self, "_last_code", None)
        if self.sim_df is None or getattr(self, "_last_sc_type", None) != sc_type or last_code != cur_code:
            self.sim_df = self.engine.generate_scenario_intraday_df(sc_type, code=cur_code)
            self._last_sc_type = sc_type
            self._last_code = cur_code
            self.slider_progress.setMaximum(len(self.sim_df) - 1)
        return self.sim_df

    def _on_run_full_backtest(self):
        """一键全天秒级回测"""
        cur_code = self._get_current_code()
        spec = self.engine.get_stock_ladder_spec(cur_code)
        issue_p = float(spec.get("issue_price", 0.0) or 0.0)
        if issue_p <= 0:
            try:
                from ats.new_stock_fetcher import NewStockFetcher
                ipo_dict = NewStockFetcher.get_instance().fetch_ipo_calendar()
                if cur_code in ipo_dict:
                    issue_p = float(ipo_dict[cur_code].get("issue_price", 0.0) or 0.0)
            except Exception:
                pass
        float_mv = float(spec.get("float_mv_yi", 15.0))
        stock_name = spec.get("name", resolve_stock_name(cur_code))

        df = self._ensure_scenario_df()
        res = self.engine.run_full_day_backtest(cur_code, df)

        final_eval = res.get("final_evaluation", {})
        sigs = res.get("signals", [])
        logs = res.get("execution_logs", [])
        rem_ratio = res.get("remaining_ratio", 0.0)

        report = (
            f"=== ⚡ 【{cur_code} {stock_name}】全天分时模拟回测报告 ===\n"
            f"【情景选择】: {self.combo_scenario.currentText()}\n"
            f"【开盘基准】: {res.get('open_price', 0):.2f} 元 | 发行价: {issue_p:.2f} 元\n"
            f"【收盘价格】: {final_eval.get('price', 0):.2f} 元 (较开盘 {final_eval.get('gain_from_open', 0):+.1f}% | 较发行价 {final_eval.get('gain_from_issue', 0):+.1f}%)\n"
            f"【全天最高】: {final_eval.get('high_price', 0):.2f} 元 | 最低: {final_eval.get('low_price', 0):.2f} 元 | VWAP均价: {final_eval.get('vwap', 0):.2f} 元\n"
            f"【全天换手】: {final_eval.get('turnover_rate', 0):.1f}% | 成交金额: {final_eval.get('amount_yi', 0):.2f} 亿元\n"
            f"【资金强度】: {final_eval.get('intensity_ratio', 0):.2f}x (流通市值{float_mv:.2f}亿) | 锁仓比例: {final_eval.get('close_high_ratio', 1)*100:.1f}%\n"
            f"--------------------------------------------------\n"
            f"【🏆 15:00 最终综合评分】: {final_eval.get('total_weighted_score', 0):.2f} 分 (满分10分)\n"
            f"【🎯 最终形态分类】: 【{final_eval.get('pattern', '--')}】\n"
            f"【💡 次日 T+1 操作建议】: {final_eval.get('t1_advice', '--')}\n"
            f"【📦 持仓管理状态】: 剩余持仓比例 {rem_ratio*100:.0f}%\n"
            f"--------------------------------------------------\n"
            f"【📋 实操执行诊断】:\n{final_eval.get('action_execution_text', '')}\n"
        )
        self.txt_backtest_report.setText(report)

        # 填充买卖点表格
        self.table_sim_signals.setRowCount(len(sigs))
        for r, s in enumerate(sigs):
            pct_str = f"{getattr(s, 'sell_ratio', 0.5)*100:.0f}%"
            sugg_p = getattr(s, 'suggested_price', s.price)
            it_t = QTableWidgetItem(s.timestamp)
            it_act = QTableWidgetItem("🔴 卖出")
            it_act.setForeground(QColor("#ff5555"))
            it_act.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            it_p = QTableWidgetItem(f"{s.price:.2f}元 (挂单:{sugg_p:.2f})")
            it_p.setForeground(QColor("#ffd700"))
            it_rt = QTableWidgetItem(pct_str)
            it_rt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_rs = QTableWidgetItem(s.reason)
            it_rs.setToolTip(s.reason)

            self.table_sim_signals.setItem(r, 0, it_t)
            self.table_sim_signals.setItem(r, 1, it_act)
            self.table_sim_signals.setItem(r, 2, it_p)
            self.table_sim_signals.setItem(r, 3, it_rt)
            self.table_sim_signals.setItem(r, 4, it_rs)

        self.table_sim_signals.resizeRowsToContents()
        self.current_frame_idx = len(df) - 1
        self.slider_progress.setValue(self.current_frame_idx)
        self.lbl_replay_status.setText(f"⏱️ 回测完成: 241 / 241 分钟 (15:00 收盘)")

    def _on_toggle_play(self):
        if self.replay_timer.isActive():
            self.replay_timer.stop()
            self.btn_play.setText("▶️ 继续回放")
            self.btn_play.setStyleSheet("background-color: #1e3a24; color: #00ff88; font-weight: bold; padding: 5px 14px;")
        else:
            self._ensure_scenario_df()
            spd_text = self.combo_speed.currentText()
            interval = 50 if "20x" in spd_text else (100 if "10x" in spd_text else (200 if "5x" in spd_text else 800))
            self.replay_timer.setInterval(interval)
            self.replay_timer.start()
            self.btn_play.setText("⏸️ 暂停回放")
            self.btn_play.setStyleSheet("background-color: #3a2e1e; color: #ffd700; font-weight: bold; padding: 5px 14px;")

    def _on_reset_replay(self):
        self.replay_timer.stop()
        self.current_frame_idx = 0
        self.slider_progress.setValue(0)
        self.btn_play.setText("▶️ 分时动态逐帧回放")
        self.lbl_replay_status.setText("⏱️ 回放进度: 0 / 241 分钟 (已重置)")
        self.engine.reset_state("688826")
        self.table_sim_signals.setRowCount(0)
        self.txt_backtest_report.clear()

    def _on_slider_moved(self, val):
        self.current_frame_idx = val
        self._render_frame(val)

    def _on_replay_step(self):
        df = self._ensure_scenario_df()
        if self.current_frame_idx >= len(df):
            self.replay_timer.stop()
            self.btn_play.setText("▶️ 重新回放")
            self.lbl_replay_status.setText("⏱️ 全天回放完毕 (15:00)")
            return

        self._render_frame(self.current_frame_idx)
        self.current_frame_idx += 1
        self.slider_progress.setValue(self.current_frame_idx)

    def _render_frame(self, frame_idx: int):
        df = self._ensure_scenario_df()
        if frame_idx >= len(df):
            return
        row = df.iloc[frame_idx]
        t_str = row["time"]
        self.lbl_replay_status.setText(f"⏱️ 回放时间: {t_str} ({frame_idx+1}/{len(df)} 分钟) | 价格: {row['close']:.2f}元")
        self.tick_emitted_signal.emit(row.to_dict())


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    apply_dark_theme(app)

    # 启用定时器周期唤醒 Python 解释器处理 Ctrl+C 信号
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(300)

    engine = IntradayStrategyEngine.get_instance()
    default_code = engine.get_default_target_code() or "688826"
    win = PinzhunLadderStandaloneWindow(code=default_code)
    win.show()
    sys.exit(app.exec())
