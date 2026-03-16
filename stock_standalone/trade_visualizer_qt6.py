import sys
import os
import time
import pickle
import struct
import json
import socket
import logging
import platform
from queue import Queue, Empty
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Callable
from functools import partial
import signal
import pandas as pd
import numpy as np
import pyqtgraph as pg # ⚡ 已移至局部作用域 (修复：由于类定义需要，恢复至全局但保持 lazy)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QSplitter, 
    QFrame, QMessageBox, QAbstractItemView, QPushButton, QComboBox, 
    QToolBar, QMenu, QSizePolicy, QStyle, QLineEdit, QCheckBox,
    QTreeWidget, QTreeWidgetItem
)
from PyQt6.QtCore import (
    QObject, Qt, pyqtSignal, QThread, QTimer, QPoint, QMutex, QMutexLocker, 
    QRect, QPointF, QRectF
)

from PyQt6.QtGui import (
    QAction, QColor, QPainter, QPicture, QFont, QPen, QBrush, 
    QActionGroup, QShortcut, QKeySequence,QFontMetrics
)
from PyQt6.QtWidgets import QGraphicsItem
from PyQt6 import sip
from PyQt6 import QtGui
# # 确保当前目录在路径中，防止 ModuleNotFoundError
# current_dir = os.path.dirname(os.path.abspath(__file__))
# if current_dir not in sys.path:
#     sys.path.insert(0, current_dir)

import stock_logic_utils
from stock_logic_utils import ensure_parentheses_balanced, remove_invalid_conditions
from JohnsonUtil import LoggerFactory
from JohnsonUtil.stock_sender import StockSender
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx, print_timing_summary
from JohnsonUtil import johnson_cons as ct
from strategy_controller import StrategyController
from signal_types import SignalPoint, SignalType, SignalSource
from StrongPullbackMA5Strategy import StrongPullbackMA5Strategy
from strong_consolidation_strategy import StrongConsolidationStrategy
from data_utils import (
    calc_compute_volume, calc_indicators, fetch_and_process, send_code_via_pipe,PIPE_NAME_TK)
from hotlist_panel import HotlistPanel
from signal_log_panel import SignalLogPanel
from hotspot_popup import HotSpotPopup
from signal_message_queue import SignalMessage, SignalMessageQueue
from trading_hub import get_trading_hub, TrackedSignal
from realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
import sbc_core
from stock_visual_utils import PercentAxisItem
# from data_hub_service import DataHubService
from sys_utils import get_base_path
BASE_DIR = get_base_path()
visualizer_config = cct.get_resource_file("visualizer_layout.json",BASE_DIR=BASE_DIR)
intraday_pattern_config = cct.get_resource_file("intraday_pattern_config.json",BASE_DIR=BASE_DIR)
from data_utils import (
    calc_cycle_stage_vect
)

import re
try:
    import pythoncom
except ImportError:
    pythoncom = None

# System-wide hotkey support
try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    keyboard = None  # type: ignore
    KEYBOARD_AVAILABLE = False
    print("Warning: 'keyboard' library not available. System-wide hotkeys disabled.")

# Configuration
IPC_PORT = 26668
IPC_HOST = '127.0.0.1'
logger = LoggerFactory.getLogger()
# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
from multiprocessing import Process, Queue
import queue  # 这个一定要加，用于捕获 Empty 异常
from multiprocessing import Event
import multiprocessing as mp
# 全局或窗口属性
stop_event = Event()
try:
    from trading_logger import TradingLogger
    from JSONData import tdx_data_Day as tdd
    from JSONData import sina_data
    from tk_gui_modules.window_mixin import WindowMixin
    from dpi_utils import get_windows_dpi_scale_factor
except ImportError as e:
    print(f"Import Error: {e}. Please run this script from the stock_standalone directory.")
    sys.exit(1)
    
# Integrated Query Engine
try:
    from query_engine_util import query_engine
    if query_engine:
        query_engine.set_logger(logger)
except ImportError:
    query_engine = None

# Configuration for pyqtgraph
pg.setConfigOptions(antialias=True)
# pg.setConfigOption('background', 'w')
# pg.setConfigOption('foreground', 'k')

PERIOD_COL_PATTERN = re.compile(r'per\d+d', re.IGNORECASE)

def get_compact_width(col_name: str):
    """根据列名自动返回紧凑列宽，None 表示不使用紧凑模式"""

    base_map = {
        'code': 60,
        'rank': 40,
        'win': 20,
        'percent': 45,
        'dff': 40,
        'dff2': 40,
    }

    key = col_name.lower()

    # 1️⃣ 固定列
    if key in base_map:
        return base_map[key]

    # 2️⃣ perXd 动态涨幅列（per1d/per2d/...）
    if PERIOD_COL_PATTERN.fullmatch(key):
        return 40   # 所有 N 日涨幅统一列宽
    return None


class IntradayAxis(pg.DateAxisItem):
    def tickStrings(self, values, scale, spacing):
        return [time.strftime('%H:%M', time.localtime(v)) for v in values]

def normalize_speech_text(text: str) -> str:
    """将数值符号转换为适合中文语音播报的表达"""
    # 百分号
    text = text.replace('%', '百分之')
    # 负数
    text = re.sub(r'(?<!\d)-(\d+(\.\d+)?)', r'负\1', text)
    # 正号
    text = re.sub(r'(?<!\d)\+(\d+(\.\d+)?)', r'正\1', text)
    # 小数点
    text = re.sub(r'(\d+)\.(\d+)', r'\1点\2', text)
    return text


def _voice_worker(queue, stop_flag, feedback_queue=None, abort_event=None, pause_event=None):
    """语音播报工作者 (运行在独立进程)"""
    import pyttsx3
    import time
    
    # 延迟加载，防止进程初始化时卡顿
    try:
        import pythoncom
    except ImportError:
        pythoncom = None
    
    logger.debug("[VoiceProcess] Worker started")
    
    last_speech_end_ts = 0.0 # [FIX] Timestamp filtering
    
    while stop_flag.value:
        try:
            # ⚡ [NEW] 检查暂停状态 (阻塞直到恢复)
            if pause_event:
                pause_event.wait()
            
            # 获取消息（阻塞等待 1s）
            data = None
            try:
                data = queue.get(timeout=1)
            except:
                continue
            
            if not data or not stop_flag.value:
                continue
                
            # 兼容处理
            msg_ts = 0.0
            if isinstance(data, dict):
                msg = data.get('text', '')
                meta = data.get('meta', None)
                msg_ts = data.get('timestamp', 0.0)
            else:
                msg = str(data)
                meta = None
                msg_ts = time.time()

            # [FIX] 移除错误的时间戳过滤逻辑。
            # 原逻辑：if msg_ts > 0 and msg_ts < last_speech_end_ts: continue
            # 这会导致在播报第一条期间入队的所有信号都被视为“陈旧”而丢弃。
            # 我们只需要确保不播报启动之前的极老信号即可（可选）。
            if msg_ts > 0 and time.time() - msg_ts > 300: # 超过5分钟的才视为陈旧
                continue


            # 向主进程反馈：开始播报该条信号
            if feedback_queue and meta:
                try:
                    feedback_queue.put(meta)
                except:
                    pass

            # 执行播报
            speech_text = normalize_speech_text(msg)
            logger.debug(f"[VoiceProcess] 🔊 播报: {speech_text}")
            
            # ⚡ [STABILITY] 在每一条播报前初始化，确保 Windows 引擎状态正确
            engine = None
            try:
                if pythoncom:
                    pythoncom.CoInitialize()
                
                engine = pyttsx3.init()
                rate = engine.getProperty('rate')
                logger.debug(f'rate:{rate}')
                if isinstance(rate, (int, float)):
                    # engine.setProperty('rate', rate + 40)
                    engine.setProperty('rate', cct.voice_rate)
                    engine.setProperty('volume', cct.voice_volume)

                    
                def check_abort(name=None, location=None, length=None):
                    if (abort_event and abort_event.is_set()) or not stop_flag.value:
                        try:
                            engine.stop()
                        except:
                            pass

                engine.connect('started-utterance', check_abort)
                engine.connect('started-word', check_abort)

                engine.say(speech_text)
                engine.runAndWait() # ⭐ 稳健模式：等待当前语音播完
                
                # [FIX] Update completion timestamp
                last_speech_end_ts = time.time()
                
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"[VoiceProcess] Engine error: {e}")
            finally:
                if engine:
                    try:
                        engine.stop()
                        del engine
                    except:
                        pass
                if pythoncom:
                    try:
                        pythoncom.CoUninitialize()
                    except:
                        pass
                    
        except Exception as e:
            logger.debug(f"[VoiceProcess] Loop error: {e}")
            
    logger.info("✅ Voice worker process exited cleanly")
    
    logger.debug("[VoiceProcess] Worker stopped")


class VoiceProcess:
    """
    语音播报进程管理器 (多进程完全隔离，不干扰主进程)
    
    使用 multiprocessing 而非 QThread，完全隔离 COM 调用，
    避免与 Qt 事件循环产生冲突导致卡死。
    """
    def __init__(self, parent=None):  # 接受 parent 参数保持兼容性
        import multiprocessing as mp
        self.queue = mp.Queue()
        self.feedback_queue = mp.Queue() # 新增反馈队列
        self.stop_flag = mp.Value('b', True)  # boolean, True = running
        self.abort_event = mp.Event() # 新增：强制中止事件
        self.pause_event = mp.Event() # [NEW] 暂停事件
        self.pause_event.set()        # 初始为非暂停状态
        self.process = None
        self.pause_for_sync = False  # 保留接口兼容性（但多进程下无需使用）

    def start(self):
        """启动语音播报进程"""
        import multiprocessing as mp
        if self.process is None or not self.process.is_alive():
            self.stop_flag.value = True
            self.abort_event.clear()
            self.pause_event.set() # 确保不处于暂停
            self.process = mp.Process(
                target=_voice_worker, 
                args=(self.queue, self.stop_flag, self.feedback_queue, self.abort_event, self.pause_event),
                daemon=False # ⚡ [STABILITY] 改为非守护进程，依靠 stop() 优雅退出，防止 COM 引起的 Access Violation
            )
            self.process.start()
            logger.info("✅ 语音播报进程已启动 (PID: %s)", self.process.pid)

    def speak(self, text, meta=None):
        """添加文本及元数据到播报队列"""
        if self.stop_flag.value:
            # 推送新消息时，确保中止事件是清除的
            self.abort_event.clear()
            # [FIX] Always include timestamp for deduplication
            t_now = time.time()
            if meta:
                self.queue.put({'text': text, 'meta': meta, 'timestamp': t_now})
            else:
                self.queue.put({'text': text, 'meta': None, 'timestamp': t_now})

    def abort(self):
        """立即中止当前所有播报"""
        # 1. 设置中止事件，让 worker 停止当前播放
        self.abort_event.set()
        # 2. 清空队列中剩余的消息
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
        
        # 3. 如果处于暂停，强制恢复以便处理中止
        self.pause_event.set()
        
        logger.info("🛑 Voice broadcast aborted and queue cleared")

    def pause(self):
        """暂停播报"""
        self.pause_event.clear()
        # 同时触发 abort_event 中止当前正在说的
        self.abort_event.set()
        logger.info("⏸ Voice broadcast paused")

    def resume(self):
        """恢复播报"""
        self.abort_event.clear()
        self.pause_event.set()
        logger.info("▶ Voice broadcast resumed")

    def stop(self):
        """停止语音播报进程 (强化退出版)"""
        logger.info("Stopping voice worker process...")
        self.stop_flag.value = False
        self.abort_event.set() # 立即中止当前播报
        
        # 清空队列，防止进程卡在 put/get 上
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break
                
        if self.process and self.process.is_alive():
            # ⚡ [STABILITY] 先尝试优雅关闭，给足时间以便 COM 组件释放
            self.process.join(timeout=2.0)
            if self.process.is_alive():
                logger.warning("Voice worker timed out on join, terminating...")
                try:
                    self.process.terminate()
                    self.process.join(timeout=1.0)
                except:
                    pass
        
        # ⚡ [NEW] 彻底关闭进程池/队列
        try:
            self.queue.close()
            self.feedback_queue.close()
        except:
            pass
            
        self.process = None
        logger.info("✅ Voice worker process shutdown complete")

    def wait(self, timeout_ms=2000):
        """等待进程完成（兼容旧接口）"""
        if self.process and self.process.is_alive():
            self.process.join(timeout=timeout_ms / 1000)


# 保留旧名称作为别名，确保兼容性
VoiceThread = VoiceProcess


class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data=None, theme='dark'):
        # 🚀 [NEW] Centralized Data Hub Initialization (Multi-Point Protection)
        # Ensure DataHub is ready in the Visualizer process
            # self.data_hub = DataHubService.get_instance()
        pass
        
        super().__init__()
        self.data = np.asarray(data)
        self.theme = theme
        self.picture = pg.QtGui.QPicture()
        self._gen_colors()
        self.generatePicture()

    def _gen_colors(self):
        if self.theme == 'dark':
            self.up_pen = pg.mkPen(QColor(220, 80, 80))
            self.up_brush = pg.mkBrush(QColor(220, 80, 80))
            self.down_pen = pg.mkPen(QColor(80, 200, 120))
            self.down_brush = pg.mkBrush(QColor(80, 200, 120))
            self.wick_pen = pg.mkPen(QColor(200, 200, 200))
        else:
            self.up_pen = pg.mkPen(QColor(200, 0, 0))
            self.up_brush = pg.mkBrush(QColor(200, 0, 0))
            self.down_pen = pg.mkPen(QColor(0, 150, 0))
            self.down_brush = pg.mkBrush(QColor(0, 150, 0))
            self.wick_pen = pg.mkPen(QColor(80, 80, 80))

    def setData(self, data):
        self.data = np.asarray(data)
        self.generatePicture()
        self.prepareGeometryChange()
        self.update()

    def generatePicture(self):
        self.picture = pg.QtGui.QPicture()
        p = pg.QtGui.QPainter(self.picture)
        w = 0.4

        for row in self.data:
            t, open_, close, low, high = row[:5]
            if close >= open_:
                pen = self.up_pen
                brush = self.up_brush
            else:
                pen = self.down_pen
                brush = self.down_brush

            # wick
            p.setPen(self.wick_pen)
            p.drawLine(
                pg.QtCore.QPointF(t, low),
                pg.QtCore.QPointF(t, high)
            )

            # body
            p.setPen(pen)
            p.setBrush(brush)
            p.drawRect(
                pg.QtCore.QRectF(
                    t - w,
                    open_,
                    w * 2,
                    close - open_
                )
            )
        p.end()

    def setTheme(self, theme):
        if theme != self.theme:
            self.theme = theme
            self._gen_colors()
            self.generatePicture()
            self.update()

    def paint(self, p, *args):
        if self.picture:
            p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return pg.QtCore.QRectF(self.picture.boundingRect())

class DateAxis(pg.AxisItem):
    def __init__(self, dates, orientation='bottom'):
        super().__init__(orientation=orientation)
        self.dates = list(dates)

    def updateDates(self, dates):
        self.dates = list(dates)
        self.update()

    def tickStrings(self, values, scale, spacing):
        """把整数索引映射成日期字符串，最后一天显示在末尾"""
        strs = []
        n = len(self.dates)
        if n == 0:
            # dates 为空，直接用原始值
            return [str(v) for v in values]

        for val in values:
            try:
                idx = int(val)
                if idx < 0:
                    idx = 0  # 负索引归零
                elif idx >= n:
                    idx = n - 1  # 超出范围用最后一天
                strs.append(str(self.dates[idx])[5:10])  # MM-DD
            except Exception as e:
                # 捕捉意外异常
                logger.warning(f"[tickStrings] val={val} error: {e}")
                strs.append("")  # 出错显示空
        return strs


class TimeAxis(pg.AxisItem):
    def __init__(self, times, orientation='bottom'):
        super().__init__(orientation=orientation)
        self.times = list(times)

    def updateTimes(self, times):
        self.times = list(times)
        self.update()

    # def tickStrings(self, values, scale, spacing):
    #     strs = []
    #     n = len(self.times)

    #     if n == 0:
    #         return [""] * len(values)

    #     for v in values:
    #         try:
    #             idx = int(round(v))
    #             if idx < 0 or idx >= n:
    #                 strs.append("")
    #                 continue

    #             ts = int(self.times[idx])  # Unix 秒
    #             strs.append(time.strftime('%H:%M', time.localtime(ts)))
    #         except Exception:
    #             strs.append("")
    #     return strs

    def tickStrings(self, values, scale, spacing):
        """把整数索引映射成时间字符串"""
        strs = []
        n = len(self.times)
        if n == 0:
            return [str(v) for v in values]

        for val in values:
            try:
                idx = int(val)
                if idx < 0:
                    idx = 0
                elif idx >= n:
                    idx = n - 1
                
                # 假设 times 里存的是 "HH:MM:SS" 或 "HH:MM"
                t_str = str(self.times[idx])
                # 只显示 HH:MM
                if len(t_str) >= 5:
                    strs.append(t_str[:5])
                else:
                    strs.append(t_str)
            except Exception:
                strs.append("")
        return strs


class SignalOverlay:
    """[UPGRADE] 信号覆盖层管理器：负责在 K 线和分时图上绘制标准化信号"""
    def __init__(self, kline_plot, tick_plot):
        self.kline_plot = kline_plot
        self.tick_plot = tick_plot

        # K线信号散点 (pxMode=True 保证缩放时图标大小不变)
        self.kline_scatter = pg.ScatterPlotItem(pxMode=True, zValue=100)
        self.kline_plot.addItem(self.kline_scatter)

        # 分时图信号散点
        self.tick_scatter = pg.ScatterPlotItem(pxMode=True, zValue=101)
        self.tick_plot.addItem(self.tick_scatter)

        # 按图表分开管理文本，防止跨图表覆盖
        self.text_items = {'kline': [], 'tick': []}
        self._text_pool = {'kline': [], 'tick': []}

    def _get_text_item(self, target='kline') -> pg.TextItem:
        """从对应池中获取或新建 TextItem"""
        if self._text_pool[target]:
            t = self._text_pool[target].pop()
            t.show()
            return t
        
        t = pg.TextItem('', anchor=(0.5, 1))
        plot = self.kline_plot if target == 'kline' else self.tick_plot
        plot.addItem(t)
        return t

    def clear(self):
        """清理所有信号标记 (回收对象到池)"""
        self.kline_scatter.clear()
        self.tick_scatter.clear()
        # 兼容处理未转换的情况
        if isinstance(self.text_items, list):
            for item in self.text_items:
                item.hide()
            self.text_items.clear()
        else:
            for t in ['kline', 'tick']:
                for item in self.text_items[t]:
                    item.hide()
                    self._text_pool[t].append(item)
                self.text_items[t].clear()

    # def update_signals_old(self, signals: list[SignalPoint], target='kline', y_visuals=None):
    #     """
    #     更新信号显示
    #     :param signals: SignalPoint 列表
    #     :param target: 'kline' 或 'tick'
    #     :param y_visuals: 可选的视觉 Y 坐标列表 (用于对齐 K 线上下方)
    #     """
    #     plot = self.kline_plot if target == 'kline' else self.tick_plot
    #     scatter = self.kline_scatter if target == 'kline' else self.tick_scatter

    #     if not signals:
    #         scatter.clear()
    #         # 立即清理旧文本并回收入池
    #         for item in self.text_items:
    #             item.hide()
    #             self._text_pool.append(item)
    #         self.text_items.clear()
    #         return

    #     xs, ys, brushes, symbols, sizes, data = [], [], [], [], [], []

    #     # 先将当前显示的文本回收入池
    #     for item in self.text_items:
    #         item.hide()
    #         self._text_pool.append(item)
    #     self.text_items.clear()

    #     for i, sig in enumerate(signals):
    #         y_pos = y_visuals[i] if y_visuals is not None else sig.price
            
    #         xs.append(sig.bar_index)
    #         ys.append(y_pos)
    #         brushes.append(pg.mkBrush(sig.color))
    #         symbols.append(sig.symbol)
    #         sizes.append(sig.size)
    #         # data 存储 meta 信息供点击回调使用
    #         data.append(sig.to_visual_hit()['meta'])

    #         # 添加价格文字标签
    #         is_buy = sig.signal_type in (SignalType.BUY, SignalType.ADD, SignalType.SHADOW_BUY)
    #         # anchor (x, y): (0.5, 1) means center-bottom of text is at pos
    #         # If is_buy, text should be BELOW the marker
    #         anchor = (0.5, -0.5) if is_buy else (0.5, 1.5)
    #         # 颜色适配主题
    #         text_color = (255, 120, 120) if is_buy else (120, 255, 120)

    #         txt = self._get_text_item()
    #         txt.setText(f"{sig.price:.2f}")
    #         txt.setAnchor(anchor)
    #         txt.setColor(text_color)
    #         txt.setPos(sig.bar_index, y_pos)
    #         self.text_items.append(txt)

    #     scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=sizes, data=data)

    def update_signals(self, signals: list[SignalPoint], target='kline', y_visuals=None):
        """
        更新信号显示
        :param signals: SignalPoint 列表
        :param target: 'kline' 或 'tick'
        :param y_visuals: 可选的视觉 Y 坐标列表 (用于对齐 K 线上下方)
        """
        import math

        plot = self.kline_plot if target == 'kline' else self.tick_plot
        scatter = self.kline_scatter if target == 'kline' else self.tick_scatter

        if not signals:
            scatter.clear()
            for item in self.text_items[target]:
                item.hide()
                self._text_pool[target].append(item)
            self.text_items[target].clear()
            return

        xs, ys, brushes, symbols, sizes, data = [], [], [], [], [], []

        xs, ys, brushes, symbols, sizes, data, pens = [], [], [], [], [], [], []

        # 回收旧文本
        for item in self.text_items[target]:
            item.hide()
            self._text_pool[target].append(item)
        self.text_items[target].clear()

        for i, sig in enumerate(signals):
            y_pos = y_visuals[i] if y_visuals is not None else sig.price
            x_pos = sig.bar_index

            # === NaN / None / Slice 保护 ===
            # [FIX] math.isnan cannot handle slice objects. Must convert or skip.
            if isinstance(x_pos, slice):
                x_pos = x_pos.start if x_pos.start is not None else 0
            if isinstance(y_pos, slice):
                y_pos = y_pos.start if y_pos.start is not None else 0

            if x_pos is None or y_pos is None:
                continue
                
            try:
                # Convert to float to ensure math.isnan works and check for validity
                fx = float(x_pos)
                fy = float(y_pos)
                if math.isnan(fx) or math.isnan(fy):
                    continue
                # 后续使用转换后的数值
                x_pos, y_pos = fx, fy
            except (TypeError, ValueError):
                continue

            # [UPGRADE] Special handling for Emoji Markers (like '🎯', '🔥', '🚀', '⚠️')
            # Natively pyqtgraph ScatterPlotItem does not support these unicode symbols as shapes.
            is_emoji = isinstance(sig.symbol, str) and len(sig.symbol) == 1 and ord(sig.symbol) > 127
            if is_emoji or sig.symbol == '🎯':
                # Draw Emoji as TextItem (centered on point)
                marker = self._get_text_item(target)
                # Use HTML to control size/color explicitly if needed, but simple unicode works too.
                # Center anchor (0.5, 0.5) puts the center of text at (x,y)
                marker.setHtml(f'<div style="font-size: {sig.size}pt; color: #FFD700; font-weight: bold;">{sig.symbol}</div>')
                marker.setAnchor((0.5, 0.5))
                marker.setPos(x_pos, y_pos)
                self.text_items[target].append(marker)
                
                # Add invisible hit target for interaction
                xs.append(x_pos)
                ys.append(y_pos)
                brushes.append(pg.mkBrush((0,0,0,0))) # Transparent
                symbols.append('o') 
                sizes.append(sig.size) # Hit area size
                pens.append(pg.mkPen((0,0,0,0))) # Transparent border
                data.append(sig.to_visual_hit()['meta'])
            else:
                xs.append(x_pos)
                ys.append(y_pos)
                brushes.append(pg.mkBrush(sig.color))
                symbols.append(sig.symbol)
                sizes.append(sig.size)
                pens.append(pg.mkPen(None)) # No outline for standard shapes
                data.append(sig.to_visual_hit()['meta'])

            # 添加价格文字标签 (K线图上通常隐藏具体价格数字以保持整洁，主要通过分时图查看详情)
            if target != 'kline':
                is_buy = sig.signal_type in (SignalType.BUY, SignalType.ADD, SignalType.SHADOW_BUY)
                
                # [UPGRADE] Support specific Text Colors for FOLLOW/EXIT
                if sig.signal_type == SignalType.FOLLOW:
                    text_color = (255, 215, 0) # Gold
                    anchor = (0.5, -0.8) # Below (leave space for large marker)
                elif sig.signal_type == SignalType.EXIT_FOLLOW:
                    text_color = (255, 69, 0) # OrangeRed
                    anchor = (0.5, 1.5) # Above (Exit)
                else:
                    anchor = (0.5, -0.5) if is_buy else (0.5, 1.5)
                    text_color = (255, 120, 120) if is_buy else (120, 255, 120)

                txt = self._get_text_item(target)
                txt.setText(f"{sig.price:.2f}")
                txt.setAnchor(anchor)
                txt.setColor(text_color)
                txt.setPos(x_pos, y_pos)
                self.text_items[target].append(txt)

        # 最后统一更新 scatter
        scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=sizes, pen=pens, data=data)


    def set_on_click_handler(self, handler):
        """设置信号点击回调"""
        self.kline_scatter.sigClicked.connect(handler)
        self.tick_scatter.sigClicked.connect(handler)


def recv_exact(sock: socket.socket, size: int, running_cb: Optional[Callable[[], bool]] = None) -> bytes:
    buf = b""
    while len(buf) < size:
        if running_cb and not running_cb():
            raise RuntimeError("Listener stopped")
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed")
        buf += chunk
    return buf


class CommandListenerThread(QThread):
    command_received = pyqtSignal(str)
    dataframe_received = pyqtSignal(object, str)

    def __init__(self, server_socket):
        super().__init__()
        self.server_socket = server_socket
        self.running = True

    def stop(self):
        """退出监听线程"""
        self.running = False
        try:
            # ⭐ 关键：强制关闭连接以解除 accept() 阻塞
            if self.server_socket:
                try:
                    self.server_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                self.server_socket.close()
        except Exception as e:
            logger.debug(f"[IPC] Error closing server socket: {e}")
        
        self.quit()
        # 等待线程自然退出
        if not self.wait(1000):
            self.terminate()

    def run(self):
        # ⭐ 关键：避免 accept 无限阻塞
        self.server_socket.settimeout(1.0)
        while self.running:
            try:
                # accept 阻塞，直到有客户端连接
                client_socket: socket.socket
                client_socket, _ = self.server_socket.accept()
                try:
                    client_socket.settimeout(10.0)
                    # 尝试增加接收缓冲区
                    try:
                        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024) # 2MB
                    except Exception:
                        pass

                    # 1. 精确读取 4 字节协议头
                    prefix = recv_exact(client_socket, 4, lambda: self.running)
                    if not prefix:
                        client_socket.close()
                        continue

                    if prefix == b"DATA":
                        # --- DATA 模式：二进制大数据包 ---
                        try:
                            # 2. 读取长度头 (4 字节)
                            header = recv_exact(client_socket, 4, lambda: self.running)
                            size = struct.unpack("!I", header)[0]
                            
                            # 限制异常大小，防止内存攻击（200MB 限制）
                            if size > 200 * 1024 * 1024:
                                logger.error(f"[IPC] Packet too large ({size} bytes). Discarding.")
                                client_socket.close()
                                continue

                            logger.debug(f"[IPC] Start receiving payload: {size/(1024*1024):.2f} MB")
                            
                            # 3. 读取完整负载
                            payload = recv_exact(client_socket, size, lambda: self.running)
                            if payload:
                                raw_data = pickle.loads(payload)
                                if isinstance(raw_data, tuple) and len(raw_data) == 2:
                                    msg_type, df_obj = raw_data
                                    self.dataframe_received.emit(df_obj, msg_type)
                                    logger.info(f"[IPC] Dataframe processed: {msg_type}")
                        except Exception as e:
                            logger.error(f"[IPC] DATA Packet process error: {e}")

                    elif prefix == b"CODE":
                        # --- CODE 模式：短文本指令 (CODE|...) ---
                        try:
                            # 尝试非阻塞读取剩余内容 (加大缓冲区防止JSON截断)
                            client_socket.settimeout(1.0) # 防止这里死锁
                            remaining = client_socket.recv(16384) # 1KB -> 16KB
                            full_cmd_bytes = prefix + remaining
                            cmd = full_cmd_bytes.decode("utf-8", errors='ignore')
                            
                            # logger.info(f"[IPC DEBUG] Prefix=CODE, len={len(remaining)}, cmd[:50]={cmd[:50]}")

                            if "|" in cmd:
                                # logger.info(f"[IPC] Command received: {cmd}")
                                self.command_received.emit(cmd)
                            else:
                                logger.warning(f"[IPC] Invalid command (no pipe): {cmd}")
                        except Exception as e:
                            logger.error(f"[IPC] Command process error: {e}")
                    
                    else:
                        # 未知协议头，可能是脏数据，直接丢弃
                        logger.warning(f"[IPC] Unknown protocol prefix: {prefix}. Discarding connection.")
                        client_socket.close()
                finally:
                    try:
                        client_socket.close()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except OSError as e:
                # server_socket 被关闭时，这是“正常退出路径”
                if not self.running:
                    break
                logger.warning(f"[IPC] accept OSError: {e}")

            except Exception as e:
                logger.exception("[IPC] Unexpected listener error")

        print("[IPC] CommandListenerThread exited cleanly")

            # except Exception as e:
            #     if self.running:
            #         print(f"[IPC] Listener Loop Error: {e}")
            #     else:
            #         break


duration_date_day = 120
duration_date_2d = 250      #
duration_date_up = 250      #
# duration_date_up = 190
# duration_date_up = 120
duration_date_week = 500    #3-ma60d
# duration_date_month = 300
duration_date_month = 1000    #3-ma20d
#m : 510 ma26

Resample_LABELS_Days = {'d':duration_date_day,'2d':duration_date_2d,'3d':duration_date_up,
                      'w':duration_date_week,'m':duration_date_month}

class DataLoaderThread(QThread):
    data_loaded: pyqtSignal = pyqtSignal(object, object, object) # code, day_df, tick_df
    code: str
    resample: str
    mutex_lock: QMutex
    fastohlc: bool
    _search_code: Optional[str]
    _resample: Optional[str]

    def __init__(self, code: str, mutex_lock: QMutex, resample: str = 'd', fastohlc: bool = True) -> None:
        super().__init__()
        self.code = code
        self.resample = resample
        self.mutex_lock = mutex_lock # 存储锁对象
        self.fastohlc = fastohlc
        self._search_code = None
        self._resample = None

    def stop(self):
        """退出数据加载线程"""
        if self.isRunning():
            self.quit()
            if not self.wait(1000):
                self.terminate()

    def run(self) -> None:
        try:
            # 使用 QMutexLocker 自动管理锁定和解锁
            if self._search_code == self.code and self._resample == self.resample:
                return  # 数据已经加载过，不重复
            
            day_df = pd.DataFrame()
            tick_df = pd.DataFrame()

            # 1. Fetch Daily Data (Historical) with Retry
            for attempt in range(3):
                try:
                    with QMutexLocker(self.mutex_lock):
                        with timed_ctx(f"get_tdx_Exp_day_to_df_att{attempt}", warn_ms=800):
                            day_df = tdd.get_tdx_Exp_day_to_df(
                                self.code, 
                                dl=Resample_LABELS_Days[self.resample], 
                                resample=self.resample, 
                                fastohlc=self.fastohlc
                            )
                    if not day_df.empty:
                        if 'ma60d' in day_df.columns:
                            with timed_ctx(f"get_tdx_Exp_day_to_df_att_cycle_stage{attempt}", warn_ms=800):
                                day_df['cycle_stage'] = calc_cycle_stage_vect(day_df)
                            # print(f"'ma60d' in day_df.columns : {'ma60d' in day_df.columns} day_df['cycle_stage']:{day_df['cycle_stage']}")
                        break
                except Exception as e:
                    if attempt == 2:
                        logger.warning(f"Final attempt failed for day_df {self.code}: {e}")
                    else:
                        time.sleep(0.05 * (attempt + 1))
            
            # 2. Fetch Realtime/Tick Data (Intraday) with Retry
            for attempt in range(3):
                try:
                    with QMutexLocker(self.mutex_lock):
                        with timed_ctx(f"get_real_time_tick_att{attempt}", warn_ms=800):
                            tick_df = sina_data.Sina().get_real_time_tick(self.code, enrich_data=True)
                    if not tick_df.empty:
                        break
                except Exception as e:
                    if attempt == 2:
                        logger.warning(f"Final attempt failed for tick_df {self.code}: {e}")
                    else:
                        time.sleep(0.05 * (attempt + 1))

            if day_df.empty and tick_df.empty:
                logger.error(f"Failed to load any data for {self.code} after retries")

            self._search_code = self.code
            self._resample = self.resample
            with timed_ctx("emit", warn_ms=800):
                self.data_loaded.emit(self.code, day_df, tick_df)

        except Exception:
            logger.exception(f"DataLoaderThread Critical Error for {self.code}")
            # 注意：即便出错也 emit，否则 UI 线程可能一直处于等待状态
            self.data_loaded.emit(self.code, pd.DataFrame(), pd.DataFrame())
        finally:
            logger.debug(f"[DataLoaderThread] Thread for {self.code} is exiting run().")

class SBCTestThread(QThread):
    """SBC 模式验证后台线程，防止 GUI 卡死"""

    finished_data = pyqtSignal(dict, object)
    error_occurred = pyqtSignal(str)

    def __init__(self, code: str, use_live: bool, hdf5_lock=None, extra_lines=None, realtime=False, win_ref=None):
        super().__init__()
        self.code = code
        self.use_live = use_live
        self.hdf5_lock = hdf5_lock
        self.extra_lines = extra_lines
        self.realtime = realtime
        self.win_ref = win_ref

    def run(self):
        try:
            try:
                import verify_sbc_pattern
            except ImportError:
                from stock_standalone import verify_sbc_pattern

            result = verify_sbc_pattern.verify_with_real_data(
                self.code,
                use_live=self.use_live,
                show_viz=False,
                hdf5_lock=self.hdf5_lock,
                extra_lines=self.extra_lines
            )

            if result and isinstance(result, dict):
                result["_realtime"] = self.realtime   # 带回GUI
                result["_use_live"] = self.use_live   # 带回GUI
                result["code"] = self.code           # 增加 code 标识
                self.finished_data.emit(result, self.win_ref)
            else:
                self.error_occurred.emit(f"未能获取 {self.code} 的验证数据")

        except Exception as e:
            import traceback
            error_msg = f"SBC 线程执行失败: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self.error_occurred.emit(error_msg)

def tick_to_daily_bar(tick_df: pd.DataFrame) -> pd.DataFrame:
    """
    极限性能版：将 tick_df 聚合成“今天的一根日 K”
    输出和原 tick_to_daily_bar 逻辑完全一致
    """
    if tick_df is None or tick_df.empty:
        return pd.DataFrame()

    df = tick_df

    # --- 1. 取 ticktime ---
    if isinstance(df.index, pd.MultiIndex) and 'ticktime' in df.index.names:
        tick_time = pd.to_datetime(df.index.get_level_values('ticktime').values)
    elif 'ticktime' in df.columns:
        tick_time = pd.to_datetime(df['ticktime'].values)
    else:
        return pd.DataFrame()

    dates = tick_time.normalize()
    latest_date = dates.max()
    mask = dates == latest_date
    df = df.loc[mask]

    if df.empty:
        return pd.DataFrame()

    # --- 2. 确定价格列 ---
    price_col = 'close'
    if price_col not in df.columns:
        for c in ['price', 'trade']:
            if c in df.columns:
                price_col = c
                break

    # --- 3. 获取 OHLC ---
    def get_val(keys, fallback_func, use_last=True):
        for k in keys:
            if k in df.columns:
                valid = df[k].to_numpy()
                valid = valid[valid > 0]
                if valid.size > 0:
                    return valid[-1] if use_last else valid[0]
        return fallback_func()

    open_p = get_val(['open', 'nopen'], lambda: df[price_col].to_numpy()[0], use_last=False)
    high_p = get_val(['high', 'nhigh'], lambda: df[price_col].to_numpy().max())
    low_p = get_val(['low', 'nlow'], lambda: df[price_col].to_numpy().min())
    close_p = df[price_col].to_numpy()[-1]

    # --- 4. 修正 High/Low 包络 Open/Close ---
    high_p = max(high_p, open_p, close_p)
    low_p = min(low_p, open_p, close_p)

    volume = df['volume'].to_numpy()[-1] if 'volume' in df.columns else 0

    bar = pd.DataFrame(
        {
            'open': [open_p],
            'high': [high_p],
            'low': [low_p],
            'close': [close_p],
            'volume': [volume]
        },
        index=[latest_date.strftime('%Y-%m-%d')]
    )

    logger.debug(f'Generated bar for {latest_date.strftime("%Y-%m-%d")}, close={close_p}')
    return bar


def tick_to_daily_bar_slow(tick_df: pd.DataFrame) -> pd.DataFrame:
    """
    将 tick_df（MultiIndex: code, ticktime）聚合成“今天的一根日 K”
    返回：
        index: DatetimeIndex([today])
        columns: open, high, low, close, volume
    """
    if tick_df is None or tick_df.empty:
        return pd.DataFrame()

    df = tick_df.copy()
    # === 1. 取 ticktime ===
    if isinstance(df.index, pd.MultiIndex) and 'ticktime' in df.index.names:
        tick_time = pd.to_datetime(df.index.get_level_values('ticktime'))
    elif 'ticktime' in df.columns:
        tick_time = pd.to_datetime(df['ticktime'])
    else:
        return pd.DataFrame()

    df['_dt'] = tick_time
    df['_date'] = df['_dt'].dt.normalize()

    # [FIX] 不要强制使用系统日期的“今天”，因为在凌晨或非交易日，数据实际上是上一个交易日的。
    # 应该使用数据中的最新日期。
    if df.empty:
        return pd.DataFrame()
        
    latest_date = df['_date'].max()
    df = df[df['_date'] == latest_date]
    today_str = latest_date.strftime('%Y-%m-%d')
    
    if df.empty:
        return pd.DataFrame()

    # === 2. 价格列统一与 OHLC 获取 ===
    # 优先使用官方字段 (open, high, low)，因为它们通常代表全天的累进值
    # 如果缺失，再降级到价格列统计
    price_col = 'close'
    if price_col not in df.columns:
        for c in ['price', 'trade']:
            if c in df.columns:
                price_col = c
                break
    
    # 查找官方 OHLC 列
    def get_val(df, keys, fallback_func, use_last=True):
        for k in keys:
            if k in df.columns:
                valid = df[k][df[k] > 0]
                if not valid.empty:
                    return valid.iloc[-1] if use_last else valid.iloc[0]
        return fallback_func()

    try:
        # Open: 优先官方 open，其次第一笔价
        open_p = get_val(df, ['open', 'nopen'], lambda: df[price_col].iloc[0], use_last=False)
        # High: 优先官方 high，其次统计最高价
        high_p = get_val(df, ['high', 'nhigh'], lambda: df[price_col].max())
        # Low: 优先官方 low，其次统计最低价
        low_p = get_val(df, ['low', 'nlow'], lambda: df[price_col].min())
        # Close: 最后一笔价
        close_p = df[price_col].iloc[-1]
        
        # 修正逻辑：High/Low 必须包络 Open/Close
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)

        bar = pd.DataFrame(
            {
                'open':   [open_p],
                'high':   [high_p],
                'low':    [low_p],
                'close':  [close_p],
                'volume': [df['volume'].iloc[-1] if 'volume' in df.columns else 0],
            },
            index=[today_str],
        )
        logger.debug(f'Generated bar for {today_str}, close={bar["close"].values[0]}')
        return bar
    except Exception as e:
        logger.error(f"tick_to_daily_bar error: {e}")
        return pd.DataFrame()


def test_tick_df():
    s = sina_data.Sina()
    tick_df = s.get_real_time_tick('000603')
    today_bar = tick_to_daily_bar(tick_df)
    print(f'today_bar: {today_bar}')
    import ipdb;ipdb.set_trace()

    # test_tick_df()

def drop_tick_all_zero(df: pd.DataFrame) -> pd.DataFrame:
    """
    删除 tick 中 OHLC + volume 全为 0 的脏行
    - 不 reset index
    - 保留 MultiIndex
    - 适用于 tick / 分时
    """
    if df.empty:
        return df

    cols = [c for c in ('close', 'high', 'low', 'volume') if c in df.columns]
    if not cols:
        return df

    mask_valid = df[cols].ne(0).any(axis=1)
    return df.loc[mask_valid]


def realtime_worker_process(task_queue, queue, stop_flag, log_level=None, debug_realtime=False, interval=None):
    """多进程常驻拉取实时数据"""
    if interval is None:
        interval = getattr(cct.CFG, 'duration_sleep_time', 5)
    
    s = sina_data.Sina()
    current_code = None
    force_fetch = False
    
    while stop_flag.value:
        # 1. 检查是否有新任务（切换股票）
        try:
            new_code = task_queue.get_nowait()
            if new_code:
                current_code = new_code
                force_fetch = True # 切换股票后强制拉取一次
        except Empty:
            pass

        if not current_code:
            time.sleep(1)
            continue

        try:
            code = current_code
            # ⭐ 核心逻辑：如果是切股后的第一笔，或者处于交易时间，则执行抓取
            is_work_time = (cct.get_work_time() and cct.get_now_time_int() > 925)
            if is_work_time or debug_realtime or force_fetch:
                with timed_ctx("realtime_worker_process", warn_ms=800):
                    tick_df = s.get_real_time_tick(code, enrich_data=True)
                    # logger.debug(f'tick_df: {tick_df[:3]}')
                    # tick_df = drop_tick_all_zero(tick_df)
                if tick_df is not None and not tick_df.empty:
                    with timed_ctx("realtime_worker_tick_to_daily_bar", warn_ms=800):
                        today_bar = tick_to_daily_bar(tick_df)
                        # print(f'today_bar:{today_bar}')
                        try:
                            queue.put_nowait((code, tick_df, today_bar))
                            force_fetch = False # 成功抓取一次后清除强制标记
                        except queue.Full:
                            pass
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(interval)  # 避免无限抛异常占用 CPU
        if stop_flag.value:
            # 使用配置的 interval 作为冷却时间
            for _ in range(int(interval)):
                if not stop_flag.value:
                    break
                # 冷却期间也要检查是否有切股任务
                try:
                    nc = task_queue.get_nowait()
                    if nc:
                        current_code = nc
                        break # 立即切股，不等待冷却
                except Empty:
                    pass
                time.sleep(1)

    print("[IPC] realtime_worker_process exited cleanly")

def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    统一 DataFrame 结构（最终稳定版）：

    输出保证：
    - 存在列：code, date
    - date 类型：datetime64[ns]，粒度为 YYYY-MM-DD（normalize）
    - 不混用 str / Timestamp
    - 可直接 set_index('date') + sort_index()

    处理逻辑：
    - MultiIndex(code, ticktime/date/...) → 列
    - 单层 index → 兜底转列
    - 所有时间统一 → datetime → normalize
    """
    df = df.copy()

    # ---------- 1. 统一抽取 code / time ----------
    ts = None

    if isinstance(df.index, pd.MultiIndex):
        idx_names = df.index.names

        # code
        if 'code' in idx_names:
            df['code'] = df.index.get_level_values('code')
        else:
            df['code'] = df.index.get_level_values(0)

        # time / date
        time_level = None
        for name in idx_names:
            if name and name.lower() in ('ticktime', 'time', 'datetime', 'date'):
                time_level = name
                break

        ts = (
            df.index.get_level_values(time_level)
            if time_level
            else df.index.get_level_values(1)
        )

        df.reset_index(drop=True, inplace=True)

    else:
        # 单层 index
        if 'ticktime' in df.columns:
            ts = df['ticktime']
        elif 'date' in df.columns:
            ts = df['date']
        else:
            # index 当时间兜底
            ts = df.index

        # code 兜底
        if 'code' not in df.columns:
            df = df.reset_index(drop=False)
            df.rename(columns={df.columns[0]: 'code'}, inplace=True)

    # ---------- 2. 时间统一转 datetime ----------
    ts = pd.to_datetime(ts, errors='coerce')

    # ---------- 3. 统一成“日粒度 YYYY-MM-DD” ----------
    if 'date' in df.columns:
        df['date'] = ts.dt.normalize()

        # ---------- 4. 清洗非法数据 ----------
        df = df.dropna(subset=['date'])

    # ---------- 5. 删除旧时间字段，避免污染 ----------
    for col in ('ticktime',):
        if col in df.columns:
            df.drop(columns=col, inplace=True)

    return df


from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6 import sip


class NumericTreeWidgetItem(QtWidgets.QTreeWidgetItem):
    """支持数值排序的 QTreeWidgetItem

    使用 UserRole 存储的数值进行排序,而非文本
    对于没有 UserRole 数据的列,回退到字符串比较
    """
    def __lt__(self, other):
        if not isinstance(other, QtWidgets.QTreeWidgetItem):
            return super().__lt__(other)

        tree = self.treeWidget()
        if tree is None:
            return super().__lt__(other)

        col = tree.sortColumn()

        # 尝试获取 UserRole 存储的数值
        my_data = self.data(col, Qt.ItemDataRole.UserRole)
        other_data = other.data(col, Qt.ItemDataRole.UserRole)

        # 如果两者都是数值,则数值比较
        if my_data is not None and other_data is not None:
            try:
                return float(my_data) < float(other_data)
            except (ValueError, TypeError):
                pass

        # 回退到字符串比较
        return self.text(col) < other.text(col)

# ----------------- 信号消息盒子 -----------------
from typing import List
from datetime import datetime
SIGNAL_QUEUE_AVAILABLE = True

class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    """支持数值排序的 TableWidgetItem"""
    def __lt__(self, other):
        try:
            # 处理 '-' 等非数字字符为 0 或最小
            val1 = self.text().replace(',', '').strip()
            val2 = other.text().replace(',', '').strip()
            
            f1 = float(val1) if val1 and val1 != '-' else -999999.0
            f2 = float(val2) if val2 and val2 != '-' else -999999.0
            
            return f1 < f2
        except ValueError:
            return super().__lt__(other)


class SignalBoxDialog(QtWidgets.QDialog, WindowMixin):
    """信号消息盒子弹窗 (分级显示)"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("策略信号队列 (Top 60)")
        self.resize(850, 550)
        self.parent_window = parent
        
        # WindowMixin requirement
        self.scale_factor = get_windows_dpi_scale_factor()
        
        try:
            self.load_window_position_qt(self, "signal_box_dialog")
        except Exception as e:
            print(f"Failed to load signal box position: {e}")

        self._queue_mgr = SignalMessageQueue() if SIGNAL_QUEUE_AVAILABLE else None

        self.tables = {} # type: Dict[str, QtWidgets.QTableWidget]

        self._init_ui()
        
        # Apply initial theme from parent if available
        current_theme = getattr(parent, 'qt_theme', 'dark')
        self.apply_theme(current_theme)
        
        self.refresh()

    def apply_theme(self, theme_name):
        """应用主题样式"""
        if theme_name == 'dark':
            self.setStyleSheet("""
                QDialog {
                    background-color: #1E1E1E;
                    color: #DDDDDD;
                }
                QLabel {
                    color: #DDDDDD;
                }
                QTabWidget::pane {
                    border: 1px solid #333333;
                    background-color: #1E1E1E;
                }
                QTabBar::tab {
                    background: #2D2D2D;
                    color: #BBBBBB;
                    padding: 5px 10px;
                    border: 1px solid #333333;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                }
                QTabBar::tab:selected {
                    background: #3D3D3D;
                    color: #FFFFFF;
                    border-bottom: 2px solid #007ACC;
                }
                QTabBar::tab:hover {
                    background: #333333;
                }
                QTableWidget {
                    background-color: #252526;
                    color: #DDDDDD;
                    gridline-color: #333333;
                    border: none;
                }
                QTableWidget QTableCornerButton::section {
                    background-color: #2D2D2D;
                    border: 1px solid #333333;
                }
                QTableWidget::item:selected {
                    background-color: #094771;
                    color: #FFFFFF;
                }
                QHeaderView::section {
                    background-color: #2D2D2D;
                    color: #DDDDDD;
                    padding: 4px;
                    border: 1px solid #333333;
                }
                QPushButton {
                    background-color: #333333;
                    color: #DDDDDD;
                    border: 1px solid #555555;
                    padding: 4px 8px;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    background-color: #444444;
                }
                QCheckBox {
                    color: #DDDDDD;
                }
                QScrollBar:vertical {
                    border: none;
                    background: #2D2D2D;
                    width: 10px;
                    margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:vertical {
                    background: #555555;
                    min-height: 20px;
                    border-radius: 5px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #666666;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    height: 0px;
                }
                QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                    background: none;
                }
                QHeaderView {
                    background-color: #2D2D2D;
                }
            """)
            self.help_label.setStyleSheet("color: #AAAAAA;")
        else:
            # Light theme (default or specific)
            self.setStyleSheet("") # Clear to use system default
            self.help_label.setStyleSheet("color: gray;")

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # 1. 顶部统计与工具栏
        top_layout = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("暂无信号")
        top_layout.addWidget(self.status_label)
        top_layout.addStretch()

        # 热度周期控制
        top_layout.addWidget(QtWidgets.QLabel("🔥热度(分):"))
        self.heat_spin = QtWidgets.QSpinBox()
        self.heat_spin.setRange(5, 240) # 5分钟 ~ 4小时
        self.heat_spin.setValue(30)     # 默认30分钟
        self.heat_spin.setSingleStep(5)
        self.heat_spin.valueChanged.connect(self.on_heat_period_changed)
        top_layout.addWidget(self.heat_spin)

        # 清理重复
        btn_clean = QtWidgets.QPushButton("🧹清理")
        btn_clean.setToolTip("清理历史重复数据 (保留最新)")
        btn_clean.clicked.connect(self.on_clean_duplicates)
        top_layout.addWidget(btn_clean)

        btn_refresh = QtWidgets.QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.refresh)
        top_layout.addWidget(btn_refresh)

        # 强势整理扫描按钮
        btn_scan = QtWidgets.QPushButton("🛡️ 强势整理扫描")
        btn_scan.setToolTip("全市场实时扫描强势阶段整理突破潜伏股 (需 df_all 完整)")
        btn_scan.clicked.connect(self.on_scan_consolidation)
        top_layout.addWidget(btn_scan)

        layout.addLayout(top_layout)

        # 2. 分类标签页
        self.tabs = QtWidgets.QTabWidget()

        # 创建各分类表格
        self.tables['all'] = self._create_table()
        self.tables['main'] = self._create_table()
        self.tables['conso'] = self._create_table() # 强势整理
        self.tables['startup'] = self._create_table()
        self.tables['sudden'] = self._create_table()

        self.tabs.addTab(self.tables['all'], "全部 (All)")
        self.tabs.addTab(self.tables['main'], "🔥 主升浪 (Hot)")
        self.tabs.addTab(self.tables['conso'], "🛡️ 强势整理 (Conso)")
        self.tabs.addTab(self.tables['startup'], "🚀 启动蓄势 (Startup)")
        self.tabs.addTab(self.tables['sudden'], "⚡ 突发 (Sudden)")

        layout.addWidget(self.tabs)

        # 3. 底部说明
        self.help_label = QtWidgets.QLabel("双击跳转K线 | 勾选 '跟单' 自动记录到数据库(限5只) | Alt+T 快速唤起")
        layout.addWidget(self.help_label)
        
        # Theme is applied via apply_theme() called in __init__

    def _create_table(self):
        """创建统一格式的信号表格"""
        table = QtWidgets.QTableWidget()
        cols = ["时间", "代码", "名称", "类型", "理由", "评分", "热度", "天数", "Rank", "操作"]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        
        # [FIX] 更好的列宽适配策略
        header = table.horizontalHeader()
        # 1. 大部分列自动适配内容
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        # 2. 理由/类型 占据剩余空间
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch) # 理由列拉伸
        # header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Interactive) # 类型列

        # 定宽列
        table.setColumnWidth(6, 40)  # 热度
        table.setColumnWidth(7, 40)  # 天数
        table.setColumnWidth(8, 45)  # Rank
        
        # [MODIFIED] 单选模式 & 信号连接
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        
        # 允许键盘获得焦点
        table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # 单击联动
        table.cellClicked.connect(self._on_table_clicked)
        # 键盘导航联动
        table.currentCellChanged.connect(self._on_current_cell_changed)
        
        # ⭐ 启用列排序功能
        table.setSortingEnabled(True)
        return table

    def _on_table_clicked(self, row, col):
        """单击行联动"""
        self._link_signal(row, self.sender())

    def _on_current_cell_changed(self, current_row, current_col, previous_row, previous_col):
        """键盘导航联动"""
        if current_row >= 0:
            self._link_signal(current_row, self.sender())

    def _link_signal(self, row, table):
        """执行联动逻辑"""
        if not table or row < 0: return

        code_item = table.item(row, 1)
        if code_item:
            code = code_item.text()
            name_item = table.item(row, 2)
            name = name_item.text() if name_item else ""

            # 1. 联动主窗口
            self.parent_window.load_stock_by_code(code, name=name)
            # [FIX] Do NOT activate main window, keep focus on this dialog for keyboard nav
            # self.parent_window.showNormal()
            # self.parent_window.activateWindow()
            
            # 2. 标记已读 (Evaluated)
            if self._queue_mgr:
                self._queue_mgr.mark_evaluated(code)
                # [OPTIMIZATION] 不调用 refresh()，而是直接置灰当前行，避免破坏焦点
                self._mark_row_evaluated_ui(table, row)

    def _mark_row_evaluated_ui(self, table, row):
        """原地更新行的样式为已读 (灰色)"""
        try:
            for c in range(table.columnCount()):
                item = table.item(row, c)
                if item:
                    item.setBackground(QColor("#333333")) # 深灰色背景
                    item.setForeground(QColor("#555555")) # 更暗的灰色
                    # font = item.font()
                    # item.setFont(font)
        except Exception:
            pass

    def refresh(self):
        if not self._queue_mgr:
            self.status_label.setText("信号队列服务不可用")
            return

        signals = self._queue_mgr.get_top()
        self.status_label.setText(f"总信号: {len(signals)} 条")

        # ⭐ 暂时禁用排序，加快数据填充
        for t in self.tables.values():
            t.setSortingEnabled(False)

        # 此时可以检查是否需要执行扫描
        # (通常 refresh 只是显示 queue, 扫描是主动触发的)

        # 清空所有表格
        for t in self.tables.values():
            t.setRowCount(0)

        # 分发信号到各 Tab
        for msg in signals:
            # 1. 全部
            self._add_row(self.tables['all'], msg)

            # 2. 主升浪 (热榜)
            if msg.signal_type == 'HOT_WATCH':
                self._add_row(self.tables['main'], msg)

            # 3. 强势整理 (Conso)
            elif msg.signal_type == 'CONSOLIDATION':
                self._add_row(self.tables['conso'], msg)

            # 4. 启动蓄势
            elif msg.signal_type == 'STARTUP':
                self._add_row(self.tables['startup'], msg)

            # 5. 突发 (Sudden / Alert)
            elif msg.signal_type in ['SUDDEN_LAUNCH', 'ALERT']:
                self._add_row(self.tables['sudden'], msg)

            # USER_SELECT 默认只在全部显示，或可视情况加到 main

        # ⭐ 数据填充完成，重新启用排序
        for t in self.tables.values():
            t.setSortingEnabled(True)

    def _add_row(self, table: QtWidgets.QTableWidget, msg):
        """向指定表格添加一行"""
        row_idx = table.rowCount()
        table.insertRow(row_idx)

        # 存储 msg 对象，便于事件处理
        # 注意: 这里的 UserRole 存在 Item 上，可以用于后续获取 full msg, 但目前主要用到 code
        # 简单起见，我们重新构建 Item

        # 时间
        ts_str = msg.timestamp[11:] if len(msg.timestamp) > 10 else msg.timestamp
        table.setItem(row_idx, 0, QtWidgets.QTableWidgetItem(ts_str))

        # 1. 代码
        table.setItem(row_idx, 1, QtWidgets.QTableWidgetItem(msg.code))

        # 2. 名称 (带名称传递逻辑，ItemDataRole 存储 name 用于 retrieve)
        name_item = QtWidgets.QTableWidgetItem(msg.name)
        table.setItem(row_idx, 2, name_item)

        # 3. 类型
        type_item = QtWidgets.QTableWidgetItem(msg.signal_type)
        if msg.signal_type == "HOT_WATCH":
            type_item.setForeground(Qt.GlobalColor.red)
        elif msg.signal_type == "USER_SELECT":
            type_item.setForeground(Qt.GlobalColor.blue)
        elif msg.signal_type == "SUDDEN_LAUNCH":
            type_item.setForeground(Qt.GlobalColor.darkMagenta)
        elif msg.signal_type == "CONSOLIDATION":
            type_item.setForeground(QColor("#00CCFF")) # 天蓝色
        table.setItem(row_idx, 3, type_item)

        # 4. 理由
        table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(msg.reason))

        # 5. 评分
        score_item = NumericTableWidgetItem(f"{msg.score:.2f}")
        table.setItem(row_idx, 5, score_item)

        # 6. 热度 (count)
        count = getattr(msg, 'count', 1)
        count_item = NumericTableWidgetItem(str(count))
        count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 6, count_item)
        
        # 7. 连续天数 (consecutive_days)
        consecutive_days = getattr(msg, 'consecutive_days', 1)
        days_item = NumericTableWidgetItem(str(consecutive_days))
        days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 7, days_item)

        # 8. Rank (当日排名)
        rank_val = getattr(msg, 'rank', 0)
        # 如果 rank 为 0/None，尝试从 df_all 获取实时排名
        if not rank_val and hasattr(self, 'parent_window') and hasattr(self.parent_window, 'df_all'):
             df = self.parent_window.df_all
             code = msg.code[-6:] if len(msg.code) > 6 else msg.code
             if not df.empty and code in df.index:
                 # 从 df_all 获取 rank (通常为 int)
                 rank_val =  int(df.loc[code].get('Rank', 0))
                 # [NEW] 补全并回写数据库
                 if rank_val > 0 and self._queue_mgr:
                     msg.rank = rank_val
                     self._queue_mgr.update_signal_rank(msg.code, msg.signal_type, rank_val)
        
        rank_item = NumericTableWidgetItem(str(rank_val) if rank_val else "-")
        rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 8, rank_item)

        # 热度染色逻辑 (基于 self.heat_spin.value())
        # 如果 now - msg.timestamp > heat_period, 则视为冷却 (变灰)
        try:
            heat_min = self.heat_spin.value()
            msg_time = datetime.strptime(msg.timestamp, "%Y-%m-%d %H:%M:%S")
            diff_min = (datetime.now() - msg_time).total_seconds() / 60
            
            is_cool = diff_min > heat_min
            
            if is_cool:
                # 冷却样式: 全行灰色/斜体
                for c in range(9): # Adjusted for new column
                    item = table.item(row_idx, c)
                    if item:
                        item.setForeground(QColor("#777777"))
                        font = item.font()
                        font.setItalic(True)
                        item.setFont(font)
            else:
                # 活跃样式: 计数高亮
                # count_item.setBackground(QColor("#330000")) # 微红背景
                count_item.setForeground(QColor("#FF4444"))
                font = count_item.font()
                font.setBold(True)
                count_item.setFont(font)
                
        except Exception as e:
            pass

        # 9. 操作 (跟单 checkbox)
        follow_widget = QtWidgets.QWidget()
        follow_layout = QtWidgets.QHBoxLayout(follow_widget)
        follow_layout.setContentsMargins(0, 0, 0, 0)
        follow_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        follow_cb = QtWidgets.QCheckBox("跟单")
        followed = getattr(msg, 'followed', False)
        follow_cb.setChecked(followed)
        follow_cb.stateChanged.connect(lambda checked, m=msg: self._on_follow_toggled(m, checked))
        follow_layout.addWidget(follow_cb)
        table.setCellWidget(row_idx, 9, follow_widget)
        
        # 10. 已评估标记 (灰化)
        evaluated = getattr(msg, 'evaluated', False)
        if evaluated:
            for c in range(10):  # Updated to 9 columns
                item = table.item(row_idx, c)
                if item: 
                    item.setBackground(QColor("#333333")) # 深灰色背景
                    item.setForeground(QColor("#555555")) # 更暗的灰色
                    font = item.font()
                    font.setItalic(False) # 取消斜体? 或者保持
                    item.setFont(font)

    def on_clean_duplicates(self):
        """清理重复数据"""
        if not self._queue_mgr: return
        reply = QMessageBox.question(self, "清理重复", "确定要清理数据库中的历史重复信号吗？\n(同一天/同代码/同类型只保留最后一条)",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            deleted = self._queue_mgr.clean_duplicates_in_db()
            QMessageBox.information(self, "完成", f"清理了 {deleted} 条重复记录。")
            self.refresh()

    def _on_table_double_clicked(self, index):
        """双击行跳转 (通用)"""
        # 获取触发信号的表格
        sender_table = self.sender() # QTableWidget
        if not sender_table: return

        row = index.row()
        code_item = sender_table.item(row, 1)
        if code_item:
            code = code_item.text()
            name_item = sender_table.item(row, 2)
            name = name_item.text() if name_item else ""

            self.parent_window.load_stock_by_code(code, name=name)
            self.parent_window.showNormal()
            self.parent_window.activateWindow()

            if self._queue_mgr:
                self._queue_mgr.mark_evaluated(code)
                self.refresh()

    def _on_follow_toggled(self, msg, checked):
        """跟单状态切换"""
        if not checked: return

        if self._queue_mgr:
            active = self._queue_mgr.get_active_follows()
            if len(active) >= self._queue_mgr.FOLLOW_LIMIT and not msg.followed:
                QtWidgets.QMessageBox.warning(self, "限制", f"当前跟单已达上限 ({self._queue_mgr.FOLLOW_LIMIT}只)!")
                self.refresh()
                return

            # 获取当前 close 价格作为默认值
            default_price = 0.0
            if hasattr(self, 'parent_window') and hasattr(self.parent_window, 'df_all'):
                df_all = self.parent_window.df_all
                code = msg.code[-6:] if len(msg.code) > 6 else msg.code
                if not df_all.empty and code in df_all.index:
                    default_price = float(df_all.loc[code].get('trade', 0) or df_all.loc[code].get('close', 0))
            
            price, ok = QtWidgets.QInputDialog.getDouble(self, "跟单确认",
                                                       f"确认跟踪 {msg.name}({msg.code})?\n输入当前价格:",
                                                       value=default_price, decimals=2)
            if ok:
                # 默认止损 -3%
                default_stop_loss = price * 0.97
                stop_loss, ok2 = QtWidgets.QInputDialog.getDouble(self, "设置止损",
                                                                "输入止损价格 (默认-3%):",
                                                                value=default_stop_loss, decimals=2)
                if ok2:
                    self._queue_mgr.add_follow(msg, price, stop_loss)
                    self.refresh()
            else:
                self.refresh()

    def on_scan_consolidation(self):
        """执行强势整理全市场扫描"""
        if not hasattr(self.parent_window, 'df_all') or self.parent_window.df_all.empty:
            _ = QtWidgets.QMessageBox.warning(self, "扫描提示", "当前市场数据(df_all)为空，无法进行扫描。\n请确保已开启'实时数据'接收全场快照。")
            return

        if not hasattr(self.parent_window, 'consolidation_strat'):
            _ = QtWidgets.QMessageBox.warning(self, "扫描提示", "策略引擎未就绪。")
            return

        # 禁用按钮防止重复点击
        btn = self.sender()
        if btn and isinstance(btn, QtWidgets.QPushButton): 
            btn.setEnabled(False)
            
        self.status_label.setText("正在执行全市场扫描 (强势整理)...")
        QtWidgets.QApplication.processEvents()

        try:
            # 执行扫描 (默认 parallel=True)
            resample = getattr(self.parent_window, 'resample', 'd')
            
            # 从 MainWindow 获取 df_all
            df_all = self.parent_window.df_all
            
            results = self.parent_window.consolidation_strat.execute_scan(
                df_all, 
                resample=resample,
                parallel=True
            )

            # 将结果推送到信号 queue
            if results:
                # 直接使用全局导入的 SignalMessage
                for item in results:
                    msg = SignalMessage(
                        priority=30, # 扫描出的信号优先级稍低于实时监控
                        timestamp=item['timestamp'],
                        code=item['code'],
                        name=item['name'],
                        signal_type='CONSOLIDATION',
                        source='SCANNER', # 新的来源标识
                        reason=item['reason'],
                        score=item['score']
                    )
                    if self._queue_mgr:
                        self._queue_mgr.push(msg)

                _ = QtWidgets.QMessageBox.information(self, "扫描完成", 
                    f"扫描完毕，共发现 {len(results)} 个潜在信号。\n已同步至'强势整理'标签页。")
            else:
                _ = QtWidgets.QMessageBox.information(self, "扫描完成", "全市场扫描完毕，未发现符合特征的股票。")
            
            self.refresh()
            # 切换到 conso 标签页 (索引 2)
            self.tabs.setCurrentIndex(2)
            
        except Exception as e:
            logger.error(f"Scan execution error: {e}")
            _ = QtWidgets.QMessageBox.critical(self, "扫描失败", f"扫描过程中发生错误: {e}")
        finally:
            if btn and isinstance(btn, QtWidgets.QPushButton): 
                btn.setEnabled(True)
            if self._queue_mgr:
                self.status_label.setText(f"总信号: {len(self._queue_mgr.get_top())} 条")

    def on_heat_period_changed(self, val):
        self.refresh()

    def closeEvent(self, event):
        """窗口关闭时保存位置"""
        try:
            self.save_window_position_qt_visual(self, "signal_box_dialog")
        except Exception as e:
            print(f"Failed to save signal box position: {e}")
        event.accept()


class ScrollableMsgBox(QtWidgets.QDialog):

    """可滚动的详细信息弹窗，用于显示高密度决策日志"""
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 400)
        self.resize(600, 500)

        layout = QtWidgets.QVBoxLayout(self)

        # 滚动区域
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content_widget)

        self.label = QtWidgets.QLabel(content)
        self.label.setWordWrap(True)
        # self.label.setTextFormat(Qt.TextFormat.PlainText) # 修改为 PlainText 以支持 \n 换行
        self.label.setTextFormat(Qt.TextFormat.RichText)  # [FIX] 修改为 RichText 以正确渲染 HTML 信号透视信息
        self.label.setOpenExternalLinks(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_layout.addWidget(self.label)
        scroll.setWidget(content_widget)

        layout.addWidget(scroll)

        # 按钮
        btn_box = QtWidgets.QHBoxLayout()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

class GlobalInputFilter(QtCore.QObject):
    """
    捕捉全窗口鼠标侧键和键盘按键 (App-wide)
    默认在应用程序内任何窗口都有效
    """
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        # 注册终端信号处理（Ctrl+C 或 kill）
        signal.signal(signal.SIGINT, self._handle_exit)
        signal.signal(signal.SIGTERM, self._handle_exit)

    def _handle_exit(self, signum, frame):
        logger.info(f"⚡ Received signal {signum}, exiting...")
        QtWidgets.QApplication.quit()
        sys.exit(0)

    def eventFilter(self, obj, event):
        # 检查主窗口是否还存在
        if not hasattr(self, 'main_window') or sip.isdeleted(self.main_window):
            return False

        # App-wide 模式: 不检查窗口激活状态，只要应用程序有焦点即可
        # 注意: Qt 不支持真正的系统级快捷键，这是应用程序级别的最大范围

        # 鼠标按键
        if event.type() in (QtCore.QEvent.Type.MouseButtonPress, 
                            QtCore.QEvent.Type.MouseButtonRelease,
                            QtCore.QEvent.Type.MouseButtonDblClick):
            if event.button() in (Qt.MouseButton.XButton1, Qt.MouseButton.XButton2):
                # 仅在按下时触发切换
                if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                    if event.button() == Qt.MouseButton.XButton1:  # 侧键后退 -> 上一个周期
                        self.main_window.switch_resample_prev()
                    elif event.button() == Qt.MouseButton.XButton2:  # 侧键前进 -> 下一个周期
                        self.main_window.switch_resample_next()
                return True # 彻底拦截，防止 pyqtgraph 看到这些侧键导致 KeyError

        # ⭐ [FIX] 拦截带有侧键标志的鼠标移动，彻底避免 pyqtgraph 内部状态不一致导致的崩溃
        if event.type() == QtCore.QEvent.Type.MouseMove:
            if event.buttons() & (Qt.MouseButton.XButton1 | Qt.MouseButton.XButton2):
                return True

        # 键盘按键
        elif event.type() == QtCore.QEvent.Type.KeyPress:
            # ⭐ 安全防护：仅当主窗口是当前激活窗口时，才拦截处理其定义的全局快捷键
            # 否则会干扰其他独立窗口（如 TradingGUI、SignalBox）的正常输入
            if not self.main_window.isActiveWindow():
                return False

            # ⭐ 避开组合键(Alt/Ctrl)，交给 QShortcut 或系统处理，防止重复响应
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier):
                return False
                
            key = event.key()
            # --- 通达信模式: 上下左右导航 ---
            if key == Qt.Key.Key_Up:
                # 1.1: 如果左侧列表或过滤器树有焦点，交给控件处理翻页
                if self.main_window.stock_table.hasFocus() or \
                   (hasattr(self.main_window, 'filter_tree') and self.main_window.filter_tree.hasFocus()):
                    return False
                # 1.2: 如果鼠标在 K 线图，缩放 K 线；如果在分时图，切换至上一只股票 (专业模式)
                if self.main_window.is_mouse_in_kline_plot():
                    self.main_window.zoom_kline(in_=True)
                    return True
                elif self.main_window.is_mouse_in_tick_plot():
                    self.main_window.switch_stock_prev()
                    return True
                return False # 其他情况交给系统
            elif key == Qt.Key.Key_Down:
                if self.main_window.stock_table.hasFocus() or \
                   (hasattr(self.main_window, 'filter_tree') and self.main_window.filter_tree.hasFocus()):
                    return False
                if self.main_window.is_mouse_in_kline_plot():
                    self.main_window.zoom_kline(in_=False)
                    return True
                elif self.main_window.is_mouse_in_tick_plot():
                    self.main_window.switch_stock_next()
                    return True
                return False
            elif key == Qt.Key.Key_Left:
                # 1.2: 根据当前鼠标所在位置，决定是移动 K 线光标还是分时图光标
                if self.main_window.is_mouse_in_tick_plot():
                    self.main_window.move_tick_crosshair(-1)
                else:
                    self.main_window.move_crosshair(-1)
                return True
            elif key == Qt.Key.Key_Right:
                if self.main_window.is_mouse_in_tick_plot():
                    self.main_window.move_tick_crosshair(1)
                else:
                    self.main_window.move_crosshair(1)
                return True
            
            # --- 原有快捷键 ---
            # elif key == Qt.Key.Key_1:
            #     self.main_window.on_resample_changed('d')
            #     return True
            # elif key == Qt.Key.Key_2:
            #     self.main_window.on_resample_changed('3d')
            #     return True
            # elif key == Qt.Key.Key_3:
            #     self.main_window.on_resample_changed('w')
            #     return True
            # elif key == Qt.Key.Key_4:
            #     self.main_window.on_resample_changed('m')
            #     return True
            elif key == Qt.Key.Key_Space:
                self.main_window.show_comprehensive_briefing()
                return True
            elif key == Qt.Key.Key_R:
                self.main_window._reset_kline_view()
                self.main_window._reset_tick_view() # ⭐ [NEW] R 键联动重置分时图
                return True
            elif key == Qt.Key.Key_S:
                self.main_window.show_supervision_details()
                return True
            elif key == Qt.Key.Key_T:
                # 切换模拟显示
                btn = next((a for a in self.main_window.toolbar.actions() if a.text() == "模拟信号"), None)
                if btn:
                    btn.trigger()
                return True

        return super().eventFilter(obj, event)

class RealtimeWorker(QObject):
    data_updated = pyqtSignal(object, object, object)  # code, tick_df, today_bar

    def __init__(self, mutex, interval_ms=3000):
        super().__init__()
        self._mutex = mutex
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)
        self._code = None
        self._running = False
        self._sina = sina_data.Sina()

    def start(self, code):
        self._code = code
        self._running = True
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self._running = False
        self._code = None

    def _poll(self):
        if not self._running or not self._code:
            return
        try:
            with timed_ctx("_sina.get_real_time_tick", warn_ms=800):
                tick_df = self._sina.get_real_time_tick(self._code, enrich_data=True)
            with timed_ctx("_sina.get_real_time_tick_to_daily_bar", warn_ms=800):
                today_bar = tick_to_daily_bar(tick_df)
            if today_bar.empty:
                return
            self.data_updated.emit(self._code, tick_df, today_bar)
        except Exception as e:
            print(f"[RealtimeWorker] {e}")


class MainWindow(QMainWindow, WindowMixin):
    def __init__(self, stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
        super().__init__()
        # 初始化语音线程
        self.voice_thread = VoiceThread(self)
        self.voice_thread.start()
        self.last_voice_ts = "" # 记录最后一次播报的信号时间
        self._voice_paused = False # [NEW] 独立的语音暂停标志
        
        # [FIX] 内部实时进程专用的停止标志，避免污染全局 stop_flag
        self.rt_worker_stop_flag = mp.Value('b', True)
        
        # 统一快捷键注册
        self._init_global_shortcuts()

        # 1. 窗口基本设置
        self.setWindowTitle("PyQuant Stock Visualizer (Qt6 + PyQtGraph)")
        
        # 信号上下文 (用于 K线图标注和详情弹窗)
        self.active_signal_context = None
        # -------------------------
        # SBC 多窗口管理容器
        # -------------------------
        self._sbc_windows = {}  # win -> {"code":..., "extra_lines":..., "timer":..., "thread":...}

        # === Qt 版 BooleanVar 包装器，用于兼容 StockSender ===
        class QtBoolVar:
            """模拟 tk.BooleanVar 接口，用于 Qt 环境"""
            def __init__(self, value=False):
                self._value = value
            def get(self):
                return self._value
            def set(self, value):
                self._value = bool(value)
        
        # === TDX / THS 独立联动开关 ===
        self.tdx_var = QtBoolVar(True)  # 默认开启
        self.ths_var = QtBoolVar(True)  # 默认开启
        self.dfcf_var = QtBoolVar(False)  # 东方财富默认关闭
        
        # 使用独立开关初始化 StockSender
        self.sender = StockSender(self.tdx_var, self.ths_var, self.dfcf_var, callback=None)
        self.command_queue = command_queue  # ⭐ 新增：内部指令队列
        # WindowMixin 要求: scale_factor
        self._debug_realtime = debug_realtime   # 临时调试用
        self.scale_factor = get_windows_dpi_scale_factor()
        self.hdf5_mutex = QMutex()
        self.stop_flag = stop_flag
        self.log_level = log_level
        self.resample = 'd'
        self.qt_theme = 'dark'  # 默认使用黑色主题
        self.custom_bg_app = None    # 用户自定义界面背景色
        self.custom_bg_chart = None  # 用户自定义图表背景色
        self.show_bollinger = True
        self.tdx_enabled = True  # 保留兼容，同步到 tdx_var
        self.ths_enabled = True  # THS 开关状态
        self.show_td_sequential = True  # 神奇九转默认开启
        self.realtime = True  # 默认开启
        # 缓存 df_all
        self.df_cache = pd.DataFrame()
        self.garbage_threads = []         # ⭐ 线程回收站：防止 QThread 被提前 GC 导致崩溃 (1.6)
        # self.realtime_worker = None
        self.last_initialized_trade_day = None  # 记录最后一次初始化的交易日
        self._closing = False
        self.current_day_df_code = None  # ⭐ 追踪当前 day_df 实际对应哪个股票 (1.5)
        self.expected_sync_version = -1  # ⭐ 初始化同步版本 (1.4)
        self._table_item_map = {}        # ⭐ 初始化表映射 (1.4)
        self.follow_marker_items = []    # ⭐ [NEW] 跟单信号标记容器
        self._sbc_test_windows = []      # ⭐ [NEW] SBC 测试窗口引用容器

        self.realtime_queue = Queue()
        self.realtime_task_queue = Queue() # ⭐ 新增：任务队列 (1.3)
        self.realtime_process = None
        self._tick_cache = {}  # ⭐ 新增：实时数据缓存 (code -> {tick_df, today_bar, ts}) (1.3)
        self._signal_dedup_cache = {} # 信号去重缓存
        
        # 加载形态检测配置
        self.pattern_config = self._load_pattern_config()

        # ⚡ [NEW] 表格更新节流器
        self._table_refresh_timer = QTimer(self)
        self._table_refresh_timer.setSingleShot(True)
        self._table_refresh_timer.timeout.connect(self._flush_table_updates)
        self._pending_changed_codes = set()
        self._last_table_update_time = 0
        self._table_update_interval = 1.5  # 1.5s 刷新一次界面，单位秒 (与 time.time() 对比)

        # ⚡ [NEW] 用户交互锁定计时：记录用户最后一次操作界面的时间
        # 用于播报反馈同步时判断是否强行滚动 (避免“拉回”效应)
        self._last_ui_interaction_time = 0

        # ⭐ [FIX] 线程持有引用，确保 closeEvent 可停
        self.loader: Optional[DataLoaderThread] = None
        self.command_listener_thread: Optional[CommandListenerThread] = None
        self.garbage_threads: List[DataLoaderThread] = []  # 垃圾回收站,存放待清理的线程

        # 定时检查队列 - 使用配置的数据更新频率
        refresh_interval_ms = int(cct.CFG.duration_sleep_time * 1000)  # 秒转毫秒
        self.refresh_interval_ms = max(refresh_interval_ms, 30000)  # 最小 2 秒，避免过于频繁
        # ⚡ 修正：GUI 轮询队列的频率应保持高频 (如 1s)，
        # 而抓取频率 (duration_sleep_time) 由后台进程控制。
        self.realtime_timer = QTimer()
        self.realtime_timer.timeout.connect(self._poll_realtime_queue)
        self.realtime_timer.start(1000)  # 1秒轮询一次，保证响应速度
        
        # # ⚡ [NEW] 盘后策略自动分析定时器 (16:00 触发)
        # self.backtest_timer = QTimer(self)
        # self.backtest_timer.timeout.connect(self._check_and_run_backtest_analysis)
        # self.backtest_timer.start(60000) # 每分钟检查一次
        # self._last_backtest_date = None

        logger.info(f"[Visualizer] Realtime UI poll timer started at 1000ms")
        logger.info(f"[Visualizer] Realtime timer interval: {refresh_interval_ms}ms (from CFG.duration_sleep_time={cct.CFG.duration_sleep_time}s)")

        # ⭐ 新增：指令队列轮询 (处理来自 MonitorTK 的直连指令)
        if self.command_queue:
            logger.info(f"[Visualizer] Command queue detected: {self.command_queue}")
            self.command_timer = QTimer()
            self.command_timer.timeout.connect(self._poll_command_queue)
            self.command_timer.start(200)  # 200ms 轮询一次，保证响应速度
        else:
            logger.warning("[Visualizer] No command queue detected! Sync from MonitorTK may fail.")

        # 🎤 [NEW] 语音反馈监听定时器：实现声画同步定位
        self.voice_feedback_timer = QTimer()
        self.voice_feedback_timer.timeout.connect(self._poll_voice_feedback)
        self.voice_feedback_timer.start(500) # 每 500ms 检查一次播报进度

        self.day_df = pd.DataFrame()
        self.df_all = pd.DataFrame()

        # ---- resample state ----
        self.resample_keys = ['d','2d', '3d', 'w', 'm']

        if self.resample in self.resample_keys:
            self.current_resample_idx = self.resample_keys.index(self.resample)
        else:
            self.current_resample_idx = 0
            self.resample = self.resample_keys[0]

        self.select_resample = None
        # ⭐ 先初始化策略相关属性，再创建工具栏，防止 AttributeError
        # Initialize Logger with default path to ensure consistency with main program
        self.logger = TradingLogger()
        from intraday_decision_engine import IntradayDecisionEngine
        from StrongPullbackMA5Strategy import StrongPullbackMA5Strategy
        from strong_consolidation_strategy import StrongConsolidationStrategy
        from strategy_controller import StrategyController

        self.decision_engine = IntradayDecisionEngine() # ⭐ 内部决策引擎
        self.pullback_strat = StrongPullbackMA5Strategy(min_score=60) # ⭐ 强力回撤策略
        self.consolidation_strat = StrongConsolidationStrategy()     # ⭐ 强势整理策略
        self.strategy_controller = StrategyController(self) # ⭐ 新增：统一策略控制器
        
        # ⚡ [NEW] SBC Strategy Components (Structural Breakout Champion)
        self.sbc_tracker = IntradayEmotionTracker()
        self.sbc_baseline_loader = DailyEmotionBaseline()

        # 策略模拟开关
        self.show_strategy_simulation = True
        
        # ⭐ 性能优化缓存
        self._hist_df_cache = pd.DataFrame()
        self._hist_df_last_load = 0  # 上次加载时间
        self._cache_code_info = {}   # 标题信息缓存
        self._last_rendered_code = ""
        self._last_rendered_resample = ""
        
        # ⚡ [OPTIMIZATION] 图表渲染节流控制器
        # code -> last_render_timestamp
        self._last_kline_render_time = {}
        # 实时数据更新时的最小渲染间隔 (秒)
        self._render_throttle_interval = 0.1 

        # --- 1. 创建工具栏 ---
        self._init_toolbar()
        self._init_resample_toolbar()
        self._init_theme_selector()
        self._init_tdx()
        self._init_real_time()
        self._init_layout_menu()  # ⭐ 新增：布局预设菜单
        self._init_layout_menu()  # ⭐ 新增：布局预设菜单
        self._init_theme_menu()   # ⭐ 新增：主题背景菜单
        self._init_voice_toolbar() # ⭐ 新增：语音控制栏
        self._init_strategy_analysis_menu() # ⭐ 新增：策略分析菜单


        # ⭐ 数据同步序列号 (用于防重发、防漏发、防乱序)
        self.expected_sync_version = -1

        # ⭐ 新增：图表交互状态
        self.tick_prices = np.array([])
        self.tick_avg_prices = np.array([])
        self.tick_times = []
        self.current_kline_signals = []
        self.current_tick_crosshair_idx = -1
        self.mouse_last_pos = QPointF(0, 0)
        self.mouse_last_scene = None # ⭐ 记录鼠标最后所在的场景 ('kline' or 'tick') (1.1/1.2)

        self.current_code = None
        self.df_all = pd.DataFrame()  # Store real-time data from MonitorTK
        self.code_name_map = {}
        self.code_info_map = {}   # ⭐ 新增
        self.current_crosshair_idx = -1  # ⭐ 新增：通达信模式焦点索引

        # 主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a horizontal splitter for the main layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- 决策面板 (第 7 阶段) ---
        self.decision_panel = QFrame()
        self.decision_panel.setFixedHeight(40)
        self.decision_panel.setObjectName("DecisionPanel")
        self.decision_panel.setStyleSheet("""
            #DecisionPanel {
                background-color: transparent;
                border-top: 1px solid #b3d7ff;
            }
            QLabel {
                font-family: 'Microsoft YaHei UI', 'Segoe UI';
                font-size: 10pt;
            }
            QComboBox {
                background-color: #2a2a2a;
                color: #00FF00;
                border: 1px solid #444;
                border-radius: 3px;
                padding: 2px 5px;
                min-width: 100px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #00FF00;
                selection-background-color: #444;
            }
        """)
        self.decision_layout = QHBoxLayout(self.decision_panel)
        self.decision_layout.setContentsMargins(15, 0, 15, 0)

        # --- 策略选择器 (Phase 25) ---
        from PyQt6.QtWidgets import QComboBox
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([
            "📊 回调MA5",
            "🎯 决策引擎",
            "🛡️ 全策略(含监理)",
        ])
        self.strategy_combo.setCurrentIndex(2)  # 默认全策略
        self.strategy_combo.currentIndexChanged.connect(self._on_strategy_changed)
        self.decision_layout.addWidget(self.strategy_combo)

        self.decision_label = QLabel("实时决策中心: 等待策略信号...")
        self.decision_label.setStyleSheet("color: #00FF00; font-weight: bold;")
        self.decision_layout.addWidget(self.decision_label)

        self.supervision_label = QLabel("🛡️ 流程监理: 就绪")
        self.supervision_label.setStyleSheet("color: #FFD700; margin-left: 20px;")
        self.decision_layout.addWidget(self.supervision_label)

        self.decision_layout.addStretch(1)

        # [NEW] 中间状态消息 (替代原 StatusBar)
        self.center_msg_label = QLabel("")
        self.center_msg_label.setStyleSheet("color: #00FF00; font-weight: bold;") 
        self.decision_layout.addWidget(self.center_msg_label)

        self.decision_layout.addStretch(1)

        # [NEW] 统计信息标签 (左侧列表/热点/跟单)
        self.stats_label = QLabel("📊 市场: 0 | 🔥 热股: 0 | 📋 跟单: 0")
        self.stats_label.setStyleSheet("color: #aaa; margin-right: 15px; font-weight: normal;")
        self.decision_layout.addWidget(self.stats_label)

        # 💓 心跳标签 (策略运行指示器)
        self.hb_label = QLabel("💓")
        self.decision_layout.addWidget(self.hb_label)

        main_layout.addWidget(self.decision_panel)


        # 1. Left Sidebar: Stock Table
        self.stock_table = QTableWidget()


        self.stock_table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
            }

            /* 垂直滚动条 */
            QTableWidget QScrollBar:vertical {
                width: 6px;
                background: transparent;
                margin: 0px;
            }

            QTableWidget QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 120);
                min-height: 30px;
                border-radius: 3px;
            }

            QTableWidget QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 180);
            }

            QTableWidget QScrollBar::add-line:vertical,
            QTableWidget QScrollBar::sub-line:vertical {
                height: 0px;
            }

            QTableWidget QScrollBar::add-page:vertical,
            QTableWidget QScrollBar::sub-page:vertical {
                background: transparent;
            }

            /* 水平滚动条 */
            QTableWidget QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
            }

            QTableWidget QScrollBar::handle:horizontal {
                background: rgba(180, 180, 180, 120);
                min-width: 30px;
                border-radius: 3px;
            }

            QTableWidget QScrollBar::handle:horizontal:hover {
                background: rgba(220, 220, 220, 180);
            }

            QTableWidget QScrollBar::add-line:horizontal,
            QTableWidget QScrollBar::sub-line:horizontal {
                width: 0px;
            }

            QTableWidget QScrollBar::add-page:horizontal,
            QTableWidget QScrollBar::sub-page:horizontal {
                background: transparent;
            }

            /* 鼠标悬停 & 选中效果 */
            QTableWidget::item:hover {
                background: rgba(255, 255, 255, 30);
            }

            QTableWidget::item:selected {
                background: rgba(255, 215, 0, 80);
                color: white;
                font-weight: bold;
            }
        """)

        # 设置滚动条固定大小
        self.stock_table.verticalScrollBar().setFixedWidth(6)
        self.stock_table.horizontalScrollBar().setFixedHeight(6)

        # ⭐ 安装全局事件过滤器，实现应用程序级别的快捷键捕捉
        self.input_filter = GlobalInputFilter(self)
        QApplication.instance().installEventFilter(self.input_filter)


        # 禁止编辑：防止误触发覆盖 Code/Name 等关键信息，只允许选择和复制
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # self.stock_table.setHorizontalHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
        # # 列名中英文映射
        # self.column_map = {
        #     'code': '代码', 'name': '名称', 'percent': '涨幅%', 'Rank': '排名',
        #     'dff': 'DFF', 'per1d': 'per1d','win': '连阳', 'slope': '斜率', 'volume': '虚拟量', 'power_idx': '爆发力',
        #     'last_action': '策略动作', 'last_reason': '决策理由', 'shadow_info': '影子比对',
        #     'market_win_rate': '全场胜率', 'loss_streak': '连亏次数', 'vwap_bias': '均价偏离'
        # }
        # ===== 1. 内置默认列名映射（永远作为兜底）=====
        default_column_map = {
            'code': '代码', 'name': '名称', 'Rank': '排名','percent': '涨幅%', 
            'dff': 'DFF', 'per1d': 'per1d', 'win': '连阳', 'slope': '斜率',
            'volume': '虚拟量', 'power_idx': '爆发力',
            'last_action': '策略动作', 'last_reason': '决策理由', 'shadow_info': '影子比对',
            'market_win_rate': '全场胜率', 'loss_streak': '连亏次数', 'vwap_bias': '均价偏离'
        }
        # ===== 2. 从配置读取（可能为空或被用户删坏）=====
        cfg_map = getattr(cct, "vis_column_map", None)
        
        # ===== 3. 生成最终 column_map =====
        if isinstance(cfg_map, dict) and cfg_map:
            # 用配置覆盖默认，但不允许删掉默认字段
            self.column_map = {**default_column_map, **cfg_map}
        else:
            self.column_map = default_column_map.copy()


        # 1️⃣ 原始 real_time_cols 顺序保持不变
        real_time_cols = list(cct.real_time_cols)
        strategy_cols = ['last_action', 'last_reason', 'shadow_info', 'market_win_rate', 'loss_streak', 'vwap_bias']
        visualizer_core_cols = ['code', 'name', 'percent', 'dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']

        # 使用去重的方式合并列
        source_cols = real_time_cols if len(real_time_cols) > 4 and 'percent' in real_time_cols else visualizer_core_cols
        all_candidate_cols = source_cols + visualizer_core_cols + strategy_cols

        # 2️⃣ 保持 real_time_cols 顺序，其他列按 column_map 排序
        combined_header_cols = []

        # 先把 real_time_cols 加进去，顺序不变
        for c in source_cols:
            if c not in combined_header_cols:
                combined_header_cols.append(c)

        # 然后按 column_map 的顺序加入剩余已知列
        for c in self.column_map.keys():
            if c in all_candidate_cols and c not in combined_header_cols:
                combined_header_cols.append(c)

        # 最后补漏：所有还没在 combined_header_cols 的列，按原顺序加上
        for c in all_candidate_cols:
            if c not in combined_header_cols:
                combined_header_cols.append(c)

        self.headers = combined_header_cols

        self.stock_table.setColumnCount(len(self.headers))

        # 使用映射显示中文表头
        display_headers = [self.column_map.get(h, h) for h in self.headers]
        self.stock_table.setHorizontalHeaderLabels(display_headers)
        self.stock_table.setSortingEnabled(True)
        headers = self.stock_table.horizontalHeader()
        headers.setStretchLastSection(True)
        # 设置表格列自适应
        # ⭐ [BUGFIX REVERTED] 恢复自动宽度，以保证默认显示不空旷
        for col in range(len(self.headers)):
            headers.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        
        headers.setStretchLastSection(True)

        # 在 MainWindow.__init__ 中修改
        self.stock_table.cellClicked.connect(self.on_table_cell_clicked) # 保留点击
        self.stock_table.cellDoubleClicked.connect(self.on_table_cell_double_clicked) # 新增双击复制
        self.stock_table.currentItemChanged.connect(self.on_current_item_changed) # 新增键盘支持
        # 排序后自动滚动到顶部
        self.stock_table.horizontalHeader().sectionClicked.connect(self.on_header_section_clicked)

        # 1️⃣ 启用自定义上下文菜单
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self.on_table_right_click)

        self.stock_table.verticalHeader().setVisible(False)
        self.main_splitter.addWidget(self.stock_table)

        # 2. 右侧区域: 分离器 (日 K 线 + 分时图)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.right_splitter)

        # 3. 初始状态：面板会在后面通过 _init_hotlist_and_signal_log 统一初始化
        # 我们在这里保留布局结构，但不反复实例化面板对象


        # Set initial sizes for the main splitter (left table: 200, right charts: remaining)
        self.main_splitter.setSizes([200, 900])
        self.main_splitter.setCollapsible(0, False)  # Prevent table from being completely hidden


        # -- 顶部图表: 日 K 线
        self.kline_widget = pg.GraphicsLayoutWidget()
        self.kline_plot = self.kline_widget.addPlot(title="日线 K 线")
        # [NEW] 双击标题复制板块信息
        self.kline_plot.titleLabel.mouseDoubleClickEvent = self._on_title_double_clicked
        self.kline_plot.showGrid(x=True, y=True)
        self.kline_plot.setLabel('bottom', '日期索引')
        self.kline_plot.setLabel('left', '价格')
        # ⭐ 禁用自动范围，防止鼠标悬停时视图跳动
        self.kline_plot.disableAutoRange()
        self.right_splitter.addWidget(self.kline_widget)

        # ⭐ 安装 ViewBox 守护钩子 (锁定 X 轴, Y 轴自动)
        # self._install_viewbox_guard(self.kline_plot)
        # --- 添加重置按钮 (只添加一次) ---
        # self._add_reset_button()

        # -- 底部图表: 分时图
        self.tick_widget = pg.GraphicsLayoutWidget()
        # [FIX] 使用自定义时间轴
        self.tick_axis = TimeAxis([], orientation='bottom')
        self.tick_pct_axis = PercentAxisItem(None, orientation='right')
        self.tick_plot = self.tick_widget.addPlot(title="实时 / 分时图", axisItems={'bottom': self.tick_axis, 'right': self.tick_pct_axis})
        self.tick_plot.showAxis('right')
        self.tick_plot.getAxis('right').linkToView(self.tick_plot.getViewBox())
        self.tick_plot.showGrid(x=True, y=True)
        # ⭐ 禁用自动范围，防止鼠标悬停时视图跳动
        self.tick_plot.disableAutoRange()
        self.right_splitter.addWidget(self.tick_widget)

        # ⭐ 安装分时图的 ViewBox 守护钩子
        # self._install_viewbox_guard(self.tick_plot)

        # ⭐ [UPGRADE] 初始化信号覆盖层管理器
        self.signal_overlay = SignalOverlay(self.kline_plot, self.tick_plot)
        self.signal_overlay.set_on_click_handler(self.on_signal_clicked)

        # ⭐ [NEW] 初始化十字光标组件
        self.crosshair_enabled = True  # 默认开启十字光标

        # 创建十字线 (虚线样式)
        crosshair_pen = pg.mkPen(color=(128, 128, 128), width=1, style=Qt.PenStyle.DashLine)
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self.vline.setZValue(50)  # 确保在 K 线之上,但在信号点之下
        self.hline.setZValue(50)

        # 创建数据浮窗
        self.crosshair_label = pg.TextItem(anchor=(0, 1), color=(255, 255, 255), fill=(0, 0, 0, 180))
        self.crosshair_label.setZValue(100)  # 最上层

        # 初始隐藏
        self.vline.setVisible(False)
        self.hline.setVisible(False)
        self.crosshair_label.setVisible(False)

        # 将十字线和浮窗添加到 K 线图 (全部忽略边界，防止触发autoRange)
        self.kline_plot.addItem(self.vline, ignoreBounds=True)
        self.kline_plot.addItem(self.hline, ignoreBounds=True)
        self.kline_plot.addItem(self.crosshair_label, ignoreBounds=True)

        # 连接鼠标移动事件
        self.kline_plot.scene().sigMouseMoved.connect(self._on_kline_mouse_moved)

        # ⭐ [NEW] 初始化分时图十字光标
        self.tick_vline = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self.tick_hline = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self.tick_vline.setZValue(50)
        self.tick_hline.setZValue(50)
        self.tick_crosshair_label = pg.TextItem(anchor=(0, 1), color=(255, 255, 255), fill=(0, 0, 0, 180))
        self.tick_crosshair_label.setZValue(100)
        
        self.tick_plot.addItem(self.tick_vline, ignoreBounds=True)
        self.tick_plot.addItem(self.tick_hline, ignoreBounds=True)
        self.tick_plot.addItem(self.tick_crosshair_label, ignoreBounds=True)
        self.tick_plot.scene().sigMouseMoved.connect(self._on_tick_mouse_moved)

        # 初始隐藏分时十字线
        self.tick_vline.setVisible(False)
        self.tick_hline.setVisible(False)
        self.tick_crosshair_label.setVisible(False)

        # 设置分割器大小 (80% 顶部, 20% 底部) - 给 K 线更多空间
        # self.right_splitter.setSizes([800, 150])
        self.right_splitter.setSizes([300, 100])  # 3:1 比例

        # 3. Filter Panel (Initially Hidden)
        self.filter_panel = QWidget()
        filter_layout = QVBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        # Top Controls - 按钮行
        button_row = QHBoxLayout()

        # ⭐ 新增 History Selector ComboBox
        self.history_selector = QComboBox()
        self.history_selector.addItems(["history1", "history2", "history3", "history4", "history5"])
        self.history_selector.setCurrentIndex(4)  # 默认选 history5
        self.history_selector.setMaximumWidth(100)
        self.history_selector.currentIndexChanged.connect(self.load_history_filters)
        button_row.addWidget(self.history_selector)

        btn_manage = QPushButton("Manage")
        btn_manage.setMaximumWidth(60)
        btn_manage.clicked.connect(self.open_history_manager)
        button_row.addWidget(btn_manage)

        btn_refresh = QPushButton("R") # Refresh
        btn_refresh.setMaximumWidth(30)
        btn_refresh.clicked.connect(self.load_history_filters)
        button_row.addWidget(btn_refresh)

        # ⭐ 新增: 面板折叠切换按钮
        self.toggle_filter_btn = QPushButton("▶")
        self.toggle_filter_btn.setToolTip("收起筛选面板")
        self.toggle_filter_btn.setMaximumWidth(30)
        self.toggle_filter_btn.setCheckable(True) # 让它可以保持按下状态? 不需要，只是触发
        self.toggle_filter_btn.clicked.connect(self._on_toggle_filter_clicked)
        button_row.addWidget(self.toggle_filter_btn)

        button_row.addStretch()
        filter_layout.addLayout(button_row)


        # 信号消息盒子初始化
        self._init_signal_message_box()
        # 过滤初始化
        self._init_filter_toolbar()

        # ComboBox - 过滤条件选择
        self.filter_combo = QComboBox()
        self.filter_combo.currentIndexChanged.connect(self.on_filter_combo_changed)
        filter_layout.addWidget(self.filter_combo)

        # Filter Tree - 过滤结果
        self.filter_tree = QTreeWidget()
        self.filter_tree.setHeaderLabels(["Filtered Results"])
        self.filter_tree.setColumnCount(1)
        self.filter_tree.itemClicked.connect(self.on_filter_tree_item_clicked)
        self.filter_tree.itemDoubleClicked.connect(self._on_filter_tree_item_double_clicked)

        # 添加键盘导航支持
        self.filter_tree.currentItemChanged.connect(self.on_filter_tree_current_changed)
        
        # ⭐ 确保点击 filter_tree 任意位置都能获得键盘焦点
        self.filter_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.filter_tree.viewport().installEventFilter(self)

        # 应用窄边滚动条样式，与左侧列表一致
        filter_tree_scrollbar_style = """
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(180, 180, 180, 120);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(220, 220, 220, 180);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """
        self.filter_tree.setStyleSheet(filter_tree_scrollbar_style)
        
        # [NEW] Enable Context Menu for Filter Tree
        self.filter_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.filter_tree.customContextMenuRequested.connect(self.on_filter_tree_right_click)
        
        filter_layout.addWidget(self.filter_tree)

        # self.filter_panel.setVisible(False)
        self.main_splitter.addWidget(self.filter_panel)

        # 设置默认分割比例
        self.main_splitter.setSizes([350, 800, 160])
        self.filter_panel.setMinimumWidth(150)
        self.filter_panel.setMaximumWidth(400)
        self.main_splitter.setStretchFactor(0, 0) # 左侧列表：不自动拉伸
        self.main_splitter.setStretchFactor(1, 1) # 中间图表：自动占满空间
        self.main_splitter.setStretchFactor(2, 0) # 右侧过滤：不自动拉伸

        # ⭐ [SYNC] 监听 Splitter 移动，实时更新按钮状态
        self.main_splitter.splitterMoved.connect(self.on_main_splitter_moved)

        # 安装全局事件过滤器
        self.input_filter = GlobalInputFilter(self)
        QApplication.instance().installEventFilter(self.input_filter)
        # Apply initial theme [MOVED AFTER PANELS INIT]
        # self.apply_qt_theme()

        # Load Stock List
        self.load_stock_list()

        # ⭐ Load saved window position (Restores size and location)
        self._window_pos_loaded = False   # ⭐ 必须加
        self.load_splitter_state()
        self._init_td_text_pool()
        self._init_tick_signal_pool()
        
        self._init_hotlist_and_signal_log()

        # [FIX] Apply Theme AFTER panels are initialized
        self.apply_qt_theme()

        self.stock_table.horizontalHeader().sectionResized.connect(self._on_column_resized_debounced)
        if hasattr(self, 'filter_tree'):
            self.filter_tree.header().sectionResized.connect(self._on_column_resized_debounced)

    def _load_pattern_config(self) -> Dict[str, Any]:
        """加载形态检测配置"""
        # config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intraday_pattern_config.json")
        config_path = intraday_pattern_config
        default_config = {
            "low_open_high_walk": {
                "gain_threshold": 3.0,
                "open_low_tolerance": 0.002,
                "open_low_abs_tolerance": 0.01
            }
        }
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if "low_open_high_walk" in loaded:
                        default_config["low_open_high_walk"].update(loaded["low_open_high_walk"])
                logger.info(f"Visualizer loaded pattern config from {config_path}")
            except Exception as e:
                logger.error(f"Visualizer failed to load pattern config: {e}")
        return default_config
        
    def showEvent(self, event):
        super().showEvent(event)

        if not self._window_pos_loaded:
            self._window_pos_loaded = True
            self.load_window_position_qt(
                self, "trade_visualizer", default_width=1400, default_height=900)
            
            # ⭐ [SYNC] 重启后主动向主 TK 请求全量同步，确保数据第一时间到位
            QtCore.QTimer.singleShot(2000, self._request_full_sync)


    def _init_global_shortcuts(self):
        """统一注册全局快捷键"""
        self.shortcuts = {}
        
        # 帮助信息配置 (Key, Desc, Handler)
        self.shortcut_map = [
            ("Alt+T", "显示/隐藏信号盒子 / 切换模拟信号(T)", self._show_signal_box),
            ("Alt+F", "显示快捷键帮助 (此弹窗)", self._show_filter_panel),
            ("Alt+H", "显示/隐藏热点自选面板 (Global)", self._toggle_hotlist_panel),
            ("Alt+L", "显示/隐藏信号日志面板 (Global)", self._toggle_signal_log),
            ("Alt+V", "开启/关闭热点语音播报 (Voice)", self._toggle_hotlist_voice),
            ("Alt+W", "紧凑自适应列宽 (当前焦点表格)", self._on_shortcut_autofit),
            ("Ctrl+/", "显示快捷键帮助 (此弹窗)", self.show_shortcut_help),
            ("H", "添加当前股票到热点自选", self._add_to_hotlist),
            ("Space", "显示综合研报 / 弹窗详情 (K线图内生效)", None),
            ("R", "重置 K 线视图 (全览模式)", None),
            ("S", "显示策略监理 & 风控详情", None),
            ("1 / 2 / 3", "切换周期: 日线 / 3日 / 周线", None),
            ("4", "切换周期: 月线", None),
        ]
        
        # 注册非事件捕获型快捷键
        for key_seq, desc, handler in self.shortcut_map:
            if handler and key_seq != "Space": # Space in keyPressEvent
                # 所有键统一注册为 QShortcut，并在 on_toggle_global_keys 中集中管理冲突
                sc = QShortcut(QKeySequence(key_seq), self)
                # 所有组合键默认为 App-wide（应用程序级别）
                # 即使子窗口（信号盒子、帮助窗口）激活时也能响应
                if "+" in key_seq:  # 检测组合键 (Alt+T, Ctrl+/ 等)
                    sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(handler)
                self.shortcuts[key_seq] = sc
        
        # 提示：系统级全局热键已统一在 _register_system_hotkeys 中管理，
        # 即使窗口不在前台也能响应。如果 keyboard 库可用，用户可通过 UI 菜单切换模式。
        pass

    def show_shortcut_help(self):
        """显示/隐藏快捷键帮助弹窗 (Toggle)"""
        # 如果帮助对话框已存在且可见，则隐藏
        if hasattr(self, 'help_dialog') and self.help_dialog and self.help_dialog.isVisible():
            self.help_dialog.hide()
            return
        
        # 创建或显示帮助对话框
        content = "<h3>⌨️ 快捷键说明 (Shortcuts)</h3><table border='1' cellspacing='0' cellpadding='4' style='border-collapse: collapse;'>"
        content += "<tr style='background-color: #333; color: white;'><th>按键</th><th>功能说明</th></tr>"
        
        for key, desc, _ in self.shortcut_map:
            content += f"<tr><td><b>{key}</b></td><td>{desc}</td></tr>"
        content += "</table>"
        
        if not hasattr(self, 'help_dialog') or not self.help_dialog:
            self.help_dialog = ScrollableMsgBox("快捷键帮助", content, self)
        
        self.help_dialog.show()
        self.help_dialog.raise_()
        self.help_dialog.activateWindow()

    # ================== 热点面板 & 信号日志 ==================
    def _init_hotlist_and_signal_log(self):
        """初始化热点自选面板和信号日志面板"""
        from hotlist_panel import HotlistPanel
        from signal_log_panel import SignalLogPanel
        # 1. 热点自选面板 (集中初始化，防止重复)
        if not hasattr(self, 'hotlist_panel'):
            # ⭐ [Independent Window] 设置为 None，允许面板掉到主窗口后面
            self.hotlist_panel = HotlistPanel(None)
            self.hotlist_panel.stock_selected.connect(self._on_hotlist_stock_selected)
            self.hotlist_panel.item_double_clicked.connect(self._on_hotlist_double_click)
            self.hotlist_panel.voice_alert.connect(self._on_hotlist_voice_alert)
            self.hotlist_panel.signal_log.connect(self._on_signal_log)
            self.hotlist_panel.hide()
            
            # 恢复保存的语音状态 (应对 Config 加载早于 Init 的情况)
            if hasattr(self, '_pending_hotlist_voice_paused'):
                self.hotlist_panel._voice_paused = self._pending_hotlist_voice_paused
        
        # 2. 信号日志面板
        # ⭐ [Independent Window] 设置为 None，允许面板掉到主窗口后面
        self.signal_log_panel = SignalLogPanel(None)
        self.signal_log_panel.log_clicked.connect(self._on_signal_log_clicked)
        # ⚡ [NEW] 连接日志添加信号，用于同步语音播报 (所见即所播)
        self.signal_log_panel.log_added.connect(self._on_signal_log_added)
        # ⚡ [NEW] 连接清理信号：清理日志时同步清理播报队列
        self.signal_log_panel.cleared.connect(self.voice_thread.abort)
        # ⚡ [NEW] 连接暂停信号：信号日志面板的暂停按钮 -> 控制全局语音
        self.signal_log_panel.pause_toggled.connect(
            lambda paused: self.voice_thread.pause() if paused else self.voice_thread.resume()
        )
        # ⚡ [NEW] 交互监控：任何手动选择操作都视为用户交互，激活防夺权锁定 (5秒)
        self.signal_log_panel.log_table.itemSelectionChanged.connect(self._on_signal_log_user_interaction)

        # [FIX] Force Apply Pending Voice State (Override any earlier reset)
        if hasattr(self, 'hotlist_panel') and hasattr(self, '_pending_hotlist_voice_paused'):
            self.hotlist_panel._voice_paused = self._pending_hotlist_voice_paused
            logger.info(f"StartUp: Final Voice State Enforced: {self._pending_hotlist_voice_paused}")
        
        # 3. 热点检测：不再使用独立定时器，由主数据刷新周期驱动
        #    在 IPC 数据包接收后或手动调用 _check_hotlist_patterns()
        #    避免与 StockLiveStrategy 的形态检测重复
        
        # 4. ⚡ [NEW] 语音播报缓冲池与定时器 (防并发刷屏)
        self.voice_batch_buffer = {} # {code: {'name': name, 'messages': set(), 'meta': meta}}
        self.voice_batch_timer = QtCore.QTimer(self)
        self.voice_batch_timer.setInterval(2500) # 每2.5秒统一播报一次
        self.voice_batch_timer.timeout.connect(self._process_voice_batch)
        self.voice_batch_timer.start()
        
        logger.info("✅ 热点面板和信号日志面板已初始化")

    def _process_voice_batch(self):
        """统一处理并在固定窗口内播报累积的信号语音 (去重、合并)"""
        if not hasattr(self, 'voice_thread') or not self.voice_thread:
            return
        if getattr(self, '_voice_paused', False):
            self.voice_batch_buffer.clear()
            return
            
        if not self.voice_batch_buffer:
            return
            
        # 复制并清空缓冲池
        batch = self.voice_batch_buffer.copy()
        self.voice_batch_buffer.clear()
        
        # --- [NEW] 按优先级定义 ---
        PRIORITY_MAP = {
            '跑路': 100,
            '止损': 100,
            '诱多': 95,
            '买入': 90,
            '强势': 80,
            '突破': 80,
            '涨停': 80,
            '高开': 70,
            '主升': 70,
            '动量': 60,
            '底部': 60
        }
        
        def get_msg_priority(msg_str):
            score = 0
            for kw, w in PRIORITY_MAP.items():
                if kw in msg_str:
                    score = max(score, w)
            return score
            
        # 1. 对批量内的股票按最高优先级排序
        batch_list = []
        for code, data in batch.items():
            max_prio = 0
            for m in data['messages']:
                max_prio = max(max_prio, get_msg_priority(m))
            data['priority'] = max_prio
            batch_list.append((code, data))
            
        batch_list.sort(key=lambda x: x[1]['priority'], reverse=True)
        
        # 2. 依次发音
        for code, data in batch_list:
            name = data['name']
            messages = data['messages']
            meta = data['meta']
            
            # 组合消息
            stock_id = f"{name} {code}" if name else code
            
            # 去除包含相同子串的冗余消息 (比如: "低开走高", "(2次) 低开走高")
            filtered_msgs = []
            for m in messages:
                # 把带计数的 `(x次)` 去掉进行比对
                core_m = re.sub(r'^\(\d+次\)\s*', '', m)
                if not any(core_m in existing and core_m != existing for existing in filtered_msgs):
                     filtered_msgs.append(m)

            # 内部消息也按优先级排序，确保重点短语在前
            filtered_msgs.sort(key=get_msg_priority, reverse=True)
            
            combined_msg = "。".join(filtered_msgs)
            
            # 去除一些常见重叠
            combined_msg = combined_msg.replace('->', '转').replace('ACCUMULATE', '蓄势').replace('SURGE', '冲击')
            speak_msg = f"{stock_id}, {combined_msg}"
            
            self.voice_thread.speak(speak_msg, meta=meta)

    def _on_signal_log_clicked(self, code: str, pattern: str = '', message: str = ''):
        """处理信号日志中的代码点击：一键直达"""
        if not code: return
        
        # ⚡ [NEW] 更新用户交互时间，防止语音播报立即强行滚回
        import time as _time
        self._last_ui_interaction_time = _time.time()
        
        # 保存信号上下文
        self.active_signal_context = {
            'code': code,
            'pattern': pattern,
            'message': message,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 1. 联动 K 线视图与基础数据
        self.load_stock_by_code(code)
        
        # 2. 联动左侧主表格 (Treeview)
        self._select_stock_in_main_table(code)
        
        # 3. 联动热点自选面板 (如果存在且可见)
        if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
            self.hotlist_panel.select_stock(code)
            
        # 4. 激活主窗口，确保在顶层
        # [FIX] Do NOT steal focus! allow user to keep using Up/Down in Signal Log Panel
        # self.showNormal()
        # self.raise_()
        # self.activateWindow()
        logger.debug(f"[LINK] Signal Log clicked: {code}, linked to all views. Ctx: {pattern}")
    
    
    def _toggle_signal_log(self):
        """切换信号日志面板显示"""
        if not hasattr(self, 'signal_log_panel'):
            return
        
        # [MODIFIED] Check if visible, if so, bring to front instead of hiding
        # User Feedback: "clicked again, the panel should be brought to the foreground"
        if self.signal_log_panel.isVisible():
            self.signal_log_panel.show()
            self.signal_log_panel.raise_()
            self.signal_log_panel.activateWindow()
        else:
            self.signal_log_panel.show()
            self.signal_log_panel.raise_()
            self.signal_log_panel.activateWindow()

    def _toggle_hotlist_panel(self):
        """显示/隐藏热点自选面板 (Global)"""
        if not hasattr(self, 'hotlist_panel'):
            return
            
        # [MODIFIED] Check if visible, if so, bring to front instead of hiding
        if self.hotlist_panel.isVisible():
            self.hotlist_panel.show()
            self.hotlist_panel.raise_()
            self.hotlist_panel.activateWindow()
        else:
            self.hotlist_panel.show()
            self.hotlist_panel.raise_()
            self.hotlist_panel.activateWindow()
            
    # def _open_sector_bidding_panel(self):
    #     """打开并显示竞价板块联动监控面板"""
    #     if not hasattr(self, 'sector_bidding_panel') or self.sector_bidding_panel is None:
    #         # 延迟初始化导入，避免循环引用
    #         try:
    #             from sector_bidding_panel import SectorBiddingPanel
    #             self.sector_bidding_panel = SectorBiddingPanel(main_window=self)
    #             logger.info("📡 Sector Bidding Panel Initialized")
    #         except Exception as e:
    #             logger.error(f"Failed to initialize Sector Bidding Panel: {e}")
    #             return

    #     if self.sector_bidding_panel.isVisible():
    #         self.sector_bidding_panel.raise_()
    #         self.sector_bidding_panel.activateWindow()
    #     else:
    #         self.sector_bidding_panel.show()
    #         self.sector_bidding_panel.raise_()
    #         self.sector_bidding_panel.activateWindow()
            
    #     # 主动推一次最新的 df_all 数据进去 (防止刚打开时空白)
    #     if hasattr(self, 'df_all') and not self.df_all.empty:
    #         self.sector_bidding_panel.on_realtime_data_arrived(self.df_all)
    
    def _add_to_hotlist(self):
        """添加当前股票到热点自选"""
        if not hasattr(self, 'hotlist_panel') or not self.current_code:
            return
        
        name = self.code_name_map.get(self.current_code, self.current_code)
        price = 0.0
        
        # 尝试从 df_all 获取当前价格
        if not self.df_all.empty and self.current_code in self.df_all.index:
            row = self.df_all.loc[self.current_code]
            price = float(row.get('close', row.get('price', 0)))
        
        if self.hotlist_panel.add_stock(self.current_code, name, price, "手动添加"):
            if hasattr(self, 'voice_thread') and self.voice_thread:
                self.voice_thread.speak(f"已添加 {name}")
            logger.info(f"✅ 已添加到热点: {self.current_code} {name}")
            
            # 立即在图表上绘制标记
            self._draw_hotspot_markers(self.current_code, getattr(self, 'x_axis', None), self.day_df)
            
            # [NEW] 同时也通知 MonitorTK 重点监控该股 (实时队列)
            self._notify_monitor_add(self.current_code)
    
    def _notify_monitor_add(self, code: str):
        """通知 MonitorTK (通过命名管道) 增加重点监控股票"""
        try:
            from data_utils import send_code_via_pipe, PIPE_NAME_TK
            payload = {"cmd": "ADD_MONITOR", "code": code}
            send_code_via_pipe(payload, logger=logger, pipe_name=PIPE_NAME_TK)
            logger.info(f"[Pipe] Sent ADD_MONITOR for {code}")
        except Exception as e:
            logger.error(f"[Pipe] Failed to send ADD_MONITOR: {e}")
    
    def _on_hotlist_stock_selected(self, code: str, name: str):
        """热点面板选中股票回调"""
        self.show_stock(code)

    def _on_hotlist_double_click(self, code: str, name: str, price: float):
        """热点面板双击回调 - 切换到K线并聚焦"""
        logger.info(f"[Hotlist] Double clicked: {code} {name}")
        self.show_stock(code)
        # 激活窗口
        self.raise_()
        self.activateWindow()
    
    def _on_hotlist_voice_alert(self, code: str, message: str):
        """热点面板语音提醒回调 - 同时更新信号日志面板"""
        try:
            # 1. 过滤：保留买卖信号、低开走高、强势股及一般信号提醒
            # [STABILITY] 扩充关键字支持，减少“时有时无”的漏报情况
            is_valid = any(kw in message for kw in ['买入', '卖出', '低开走高', '强势', '信号', '突破', '拐点'])
            if not is_valid:
                return

            # ⚡ [NEW] 细化过滤：低开走高模型 只要 早盘最低点即开盘点 的个股
            if '低开走高' in message and not any(kw in message for kw in ['强势', '买入', '卖出']):
                if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                    row = self.df_all.loc[code]
                    o = row.get('open', 0)
                    l = row.get('low', 0)
                    if o > l > 0: # 如果开盘价不是最低点，则跳过
                        return

            # ⭐ CHECK MUTE STATE (only for voice, log panel always updates)
            is_muted = hasattr(self, 'hotlist_panel') and self.hotlist_panel._voice_paused
            
            # 2. 更新信号日志面板 (详尽信息模式)
            if hasattr(self, 'signal_log_panel'):
                from datetime import datetime
                timestamp = datetime.now().strftime('%H:%M:%S')
                name = self.code_name_map.get(code, code)
                pattern = 'ALERT'
                if '状态变更' in message:
                    pattern = 'STATUS'
                    
                full_detail = f"[{timestamp}] {name}({code}) {message}"
                
                if not self.signal_log_panel.isVisible():
                    self.signal_log_panel.show()
                    self.signal_log_panel.raise_()
                self.signal_log_panel.append_log(code, name, pattern, full_detail, is_high_priority=False)
            
            # 3. 播放语音 (受静音状态控制)
            # ⚡ [REMOVED] 改为由 signal_log_panel.log_added 信号统一触发，避免逻辑分散
            # if not is_muted:
            #     if hasattr(self, 'voice_thread'):
            #         self.voice_thread.speak(message)
        except:
            pass

    
    def _on_signal_log(self, code: str, name: str, pattern: str, message: str, is_high_priority: bool = False):
        """信号日志回调 - 追加到日志面板并写入数据库"""
        try:
            # ⚡ [FIX] 信号过滤:扩充白名单,确保更多关键信号能被记录和播报
            valid_patterns = [
                'BUY', 'SELL', 'MOMENTUM', 'ALERT', 'STATUS', 'PATTERN',
                # 形态信号 - 完整列表
                'auction_high_open', 'gap_up', 'low_open_high_walk', 'open_is_low',
                'open_is_low_volume', 'nlow_is_low_volume', 'low_open_breakout',
                'instant_pullback', 'shrink_sideways', 'pullback_upper',
                'high_drop', 'top_signal', 'master_momentum', 'open_low_retest',
                'high_sideways_break', 'bull_trap_exit', 'momentum_failure',
                'strong_auction_open'
            ]
            if not (pattern in valid_patterns or is_high_priority):
                return

            # ⚡ [NEW] 细化过滤：低开走高模型 仅捕捉 开盘即最低 且 涨幅 > 3% 的个股 (强势意图)
            if pattern == 'low_open_high_walk' and not is_high_priority:
                if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
                    row = self.df_all.loc[code]
                    o = row.get('open', 0)
                    l = row.get('low', 0)
                    p = row.get('percent', 0)
                    
                    conf = self.pattern_config.get("low_open_high_walk", {})
                    # 1. 开盘即最低 (使用配置的容错)
                    tol_rel = conf.get("open_low_tolerance", 0.002)
                    tol_abs = conf.get("open_low_abs_tolerance", 0.01)
                    gain_thresh = conf.get("gain_threshold", 3.0)
                    
                    is_open_low = (o > 0 and l > 0 and (abs(o - l) < tol_abs or abs(o - l) / o < tol_rel)) or (o == l and o > 0)
                    
                    # 2. 涨幅条件: 使用配置的阈值
                    if not (is_open_low and p > gain_thresh):
                        return


            # ⚡ [FIX] 信号去重：同一股票同一信号类型 5 秒内不重复推送
            import time
            dedup_key = f"{code}_{pattern}"
            if not hasattr(self, '_signal_dedup_cache'):
                self._signal_dedup_cache = {}
            
            now = time.time()
            last_time = self._signal_dedup_cache.get(dedup_key, 0)
            if now - last_time < 5.0:  # 5 秒内重复不推送
                return
            self._signal_dedup_cache[dedup_key] = now
            
            # ⚡ [FIX] 详细日志显示
            from datetime import datetime
            timestamp = datetime.now().strftime('%H:%M:%S')

            # 信号名称中文映射
            PATTERN_NAMES = {
                'auction_high_open': '竞价高开',
                'gap_up': '跳空高开',
                'low_open_high_walk': '低开走高',
                'open_is_low': '开盘最低',
                'open_is_low_volume': '开盘最低带量',
                'nlow_is_low_volume': '日低反转带量',
                'low_open_breakout': '低开突破',
                'instant_pullback': '回踩支撑',
                'shrink_sideways': '缩量横盘',
                'pullback_upper': '回踩上轨',
                'high_drop': '冲高回落',
                'top_signal': '顶部信号',
                'master_momentum': '核心主升',
                'open_low_retest': '开盘回踩',
                'high_sideways_break': '横盘突破',
                'bull_trap_exit': '诱多跑路',
                'momentum_failure': '主升转弱',
                'strong_auction_open': '强力竞价',
                # 策略信号
                'ALERT': '报警触发',
                'MOMENTUM': '动量信号',
                'BUY': '买入信号',
                'SELL': '卖出信号',
                'HOLD': '持有',
                'EXIT': '离场',
            }

            pattern_cn = PATTERN_NAMES.get(pattern, pattern)
            # 切回详细信息格式
            detailed_msg = f"[{timestamp}] {name}({code}) {pattern_cn}: {message}"
            
            logger.info(f"⚡ [SIGNAL LOG] {code} {name} {pattern_cn}")

            # 1. 播报语音 - ⚠️ 已重构：改为由 signal_log_panel.log_added 驱动
            # 此处不再执行 speak，确保只有成功记录到日志的信息才会被播报。

            # 2. 显示到信号日志面板（传递高优先级标志以触发闪屏）
            if hasattr(self, 'signal_log_panel'):
                # [REFINED] 连接已在 _init_hotlist_and_signal_log 中建立，此处无需动态判断
                
                if not self.signal_log_panel.isVisible():
                    self.signal_log_panel.show()
                    self.signal_log_panel.raise_()
                self.signal_log_panel.append_log(code, name, pattern, detailed_msg, is_high_priority=is_high_priority)
            
            # 3. 推送到 SignalMessageQueue (静默处理，不影响日志面板)
            if hasattr(self, '_queue_mgr') and self._queue_mgr:
                from signal_message_queue import SignalMessage
                
                # 构建 SignalMessage 对象
                msg = SignalMessage(
                    priority=100 if is_high_priority else 50,
                    timestamp=timestamp,
                    code=code,
                    name=name,
                    signal_type=pattern,
                    source='hotlist_panel',
                    reason=detailed_msg,  # 使用详细消息
                    score=0.0
                )
                if hasattr(self, 'signal_box_dialog') and self.signal_box_dialog._queue_mgr:
                    self.signal_box_dialog._queue_mgr.push(msg)
                
                    # 触发 UI 刷新及显示
                    if not self.signal_box_dialog.isVisible() and is_high_priority:
                         self.signal_box_dialog.show()
                    if self.signal_box_dialog.isVisible():
                        self.signal_box_dialog.refresh()

        except Exception as e:
            logger.error(f"Failed to process signal log: {e}")

    # --- ⚡ [NEW] 策略自动化分析相关方法 ---
    def _init_strategy_analysis_menu(self):
        """初始化策略分析菜单"""
        strategy_menu = self.menuBar().addMenu("策略分析(&A)")
        
        # 1. 手动运行当日分析
        act_run_today = strategy_menu.addAction("运行今日策略复盘评估")
        act_run_today.triggered.connect(lambda: self.run_strategy_backtest_analysis())
        
        # 2. 查看历史修正建议
        act_view_log = strategy_menu.addAction("查看策略修正日志")
        act_view_log.triggered.connect(self._view_strategy_correction_log)
        
        # # 3. 竞价及尾盘板块联动监控
        # strategy_menu.addSeparator()
        # act_sector_bidding = strategy_menu.addAction("竞价及尾盘板块联动监控(一点带面)🚀")
        # act_sector_bidding.triggered.connect(self._open_sector_bidding_panel)
        
        # 3. 自动分析开关 (可选)
        strategy_menu.addSeparator()
        self.act_auto_analysis = strategy_menu.addAction("收盘后自动分析")
        self.act_auto_analysis.setCheckable(True)
        self.act_auto_analysis.setChecked(True)

    def run_strategy_backtest_analysis(self, date_str=None):
        """执行策略回测分析 (支持手动触发)"""
        from strategy_backtest_analyzer import StrategyBacktestAnalyzer
        analyzer = StrategyBacktestAnalyzer()
        
        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')
            
        # self.statusBar().showMessage(f"正在执行策略分析: {date_str}...")
        self.show_status_message(f"正在执行策略分析: {date_str}...")
        try:
            analyzer.run_daily_analysis(target_date=date_str)
            self.show_status_message(f"策略分析完成，结果已存入修正日志。", 5000)
            
            # 如果是手动触发，弹窗确认
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "策略分析完成", f"{date_str} 的策略复盘已完成。\n建议已存入: strategy_self_correction.log")
        except Exception as e:
            logger.error(f"Strategy Analysis Failed: {e}")
            self.show_status_message(f"策略分析失败: {e}", 5000)

    def _check_and_run_backtest_analysis(self):
        """定时检查是否需要运行盘后分析 (16:00)"""
        if not hasattr(self, 'act_auto_analysis') or not self.act_auto_analysis.isChecked():
            return
            
        now = datetime.now()
        # 如果当前时间在 16:00 - 16:05 之间且今天还没跑过
        if now.hour == 16 and 0 <= now.minute <= 5:
            date_today = now.strftime('%Y-%m-%d')
            if getattr(self, '_last_backtest_date', None) != date_today:
                logger.info(f"Market closed. Running automated strategy backtest for {date_today}")
                self._last_backtest_date = date_today
                # 异步运行，避免阻塞 UI
                QtCore.QTimer.singleShot(1000, lambda: self.run_strategy_backtest_analysis(date_today))

    def _view_strategy_correction_log(self):
        """查看策略修正日志内容"""
        log_path = "./strategy_self_correction.log"
        if not os.path.exists(log_path):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", "尚未生成策略修正日志。")
            return
            
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 使用 ScrollableMsgBox 显示
            msg_box = ScrollableMsgBox("策略自修正日志 (Strategy Self-Correction)", content, self)
            msg_box.show()
        except Exception as e:
            logger.error(f"Failed to view correction log: {e}")

    def _on_signal_log_added(self, code: str, name: str, pattern: str, message: str):
        """同步播报信号日志中新增的内容 (所见即所播)"""
        try:
            # 1. 状态环境检查
            if not hasattr(self, 'voice_thread') or not self.voice_thread:
                return
            
            # [FIX] 使用 MainWindow 自身的语音标志，增强独立性
            is_muted = getattr(self, '_voice_paused', False)
            if is_muted:
                return

            # 2. 处理播报内容
            speak_msg = message
            
            # --- 深度去重与格式化处理 ---
            import re
            # (1) 移除时间戳前缀 [HH:MM:SS]
            speak_msg = re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*', '', speak_msg)
            
            # (2) 移除名称和代码组合 (稍后会统一加上)
            if name:
                speak_msg = speak_msg.replace(name, '').strip()
            speak_msg = re.sub(r'\(?\[?\d{6}\]?\)?', '', speak_msg).strip()
            
            # (3) 移除冗余的前缀 (如 "动量信号:", "报警触发:" 等)
            from signal_log_panel import SignalLogPanel
            pattern_names = getattr(SignalLogPanel, 'PATTERN_NAMES', {})
            for pat_val in pattern_names.values():
                if speak_msg.startswith(pat_val):
                    speak_msg = speak_msg[len(pat_val):].strip()
            
            # (4) 最终修整空白和多余冒号
            speak_msg = re.sub(r'^[:：\s]+', '', speak_msg).strip()
            
            # ⭐ [关键修复] 捕获用于 UI 匹配的片段 (保持精简形式)
            match_snippet = speak_msg[:20] 

            if speak_msg:
                # 放入缓冲池，等待定时器统一处理 (去重合并)
                if code not in self.voice_batch_buffer:
                    self.voice_batch_buffer[code] = {'name': name, 'messages': set(), 'meta': {'code': code, 'snippet': match_snippet}}
                
                self.voice_batch_buffer[code]['messages'].add(speak_msg)
                
        except Exception as e:
            logger.error(f"Error in signal log sync broadcast: {e}")

    def _poll_voice_feedback(self):
        """轮询语音进程的反馈队列，同步 UI 位置"""
        if not hasattr(self, 'voice_thread') or not self.voice_thread:
            return
            
        try:
            # 获取所有待处理的反馈 (非阻塞)
            while not self.voice_thread.feedback_queue.empty():
                meta = self.voice_thread.feedback_queue.get_nowait()
                if isinstance(meta, dict):
                    code = meta.get('code')
                    snippet = meta.get('snippet')
                    if code and hasattr(self, 'signal_log_panel'):
                        # ⭐ [UI LINKAGE LOCK] 用户交互锁定：如果用户刚才点击或滚动过，暂不强行同步
                        import time as _time
                        man_diff = _time.time() - getattr(self, '_last_ui_interaction_time', 0)
                        
                        # 联动 1: 日志面板自动定位与高亮 (仅在用户超过 5 秒未交互时自动滚动)
                        self.signal_log_panel.highlight_row_by_content(code, snippet, force_scroll=(man_diff > 5.0))
        except Exception as e:
            pass # 队列空或读取异常不影响主程

    def _on_signal_log_user_interaction(self):
        """处理信号日志面板的用户交互回调"""
        # 仅处理非程序性选择 (即真实用户操作)
        if hasattr(self, 'signal_log_panel') and not getattr(self.signal_log_panel, '_is_programmatic_selection', False):
            import time as _time
            self._last_ui_interaction_time = _time.time()
            # logger.debug("👤 User interaction detected in signal log, locking auto-scroll for 5s")

    def process_ipc_command(self, cmd_str: str):
        """处理 IPC 命令分发"""
        try:
            if not cmd_str: return
            
            # 移除协议前缀 "CODE|" 如果存在
            if cmd_str.startswith("CODE|"):
                content = cmd_str[5:]
            else:
                content = cmd_str
                
            # 1. 信号推送命令: SIGNAL|{json_str}
            logger.debug(f"[IPC RAW] process_ipc_command content: {content[:50]}...")
            if content.startswith("SIGNAL|"):
                try:
                    json_str = content[7:]
                    # logger.debug(f"[IPC DEBUG] Processing SIGNAL payload: {json_str[:50]}...")
                    data = json.loads(json_str)
                    # 转发给 _update_signal_log_from_ipc
                    # data 应该是 list of signals 或 single signal dict
                    if isinstance(data, dict):
                        self._update_signal_log_from_ipc([data])
                    elif isinstance(data, list):
                        self._update_signal_log_from_ipc(data)
                    logger.debug(f"IPC SIGNAL processed: {len(data) if isinstance(data, list) else 1} items")
                except Exception as e:
                    logger.error(f"Failed to parse IPC SIGNAL: {e}")
                    
            # 2. 普通股票代码: 6位数字
            elif len(content) == 6 and content.isdigit():
                self.load_stock_by_code(content)
                # self.activateWindow() # 收到代码时激活窗口 (联动时不抢焦点)
            
            # 2.5 带有参数管道符的格式: 600598|resample=d
            elif "|" in content and content.split('|')[0].strip().isdigit() and len(content.split('|')[0].strip()) == 6:
                self.load_stock_by_code(content)
                # self.activateWindow()
                
            # 3. 带名称的股票代码: 000001,平安银行 (兼容旧格式)
            elif "," in content:
                parts = content.split(",")
                if len(parts) >= 1 and len(parts[0]) == 6:
                    self.load_stock_by_code(parts[0])
                    # self.activateWindow()
            
            else:
                logger.warning(f"Unknown IPC command content: {content}")
                
        except Exception as e:
            logger.error(f"Error processing IPC command: {e}")

    def _update_signal_log_from_ipc(self, data_list: list):
        from signal_message_queue import SignalMessage
        from signal_log_panel import SignalLogPanel
        """处理通过 IPC 推送的信号数据列表 (供测试套件或外部程序使用)"""
        logger.info(f"[IPC] Processing {len(data_list)} signals from IPC")
        for data in data_list:
            try:
                # 提取核心参数，兼容 PatternEvent, StandardSignal 和 SignalMessage 格式
                code = data.get('code', '')
                name = data.get('name', '')
                
                # 优先级: subtype (StandardSignal) > pattern (PatternEvent) > signal_type (SignalMessage)
                pattern = data.get('subtype', data.get('pattern', data.get('signal_type', 'UNKNOWN')))
                
                # 特殊处理：如果 type 是 'pattern'，subtype 才是具体形态
                if data.get('type') == 'pattern' and 'subtype' in data:
                    pattern = data['subtype']
                
                # 兼容 detail (StandardSignal) / reason (PatternEvent) / message (SignalMessage)
                message = data.get('detail', data.get('reason', data.get('message', '')))
                
                is_high_priority = data.get('is_high_priority', False)
                
                # 直接调用现有的信号处理逻辑
                self._on_signal_log(code, name, pattern, message, is_high_priority)
            except Exception as e:
                logger.error(f"[IPC] Error processing signal item: {e}")
    
    def _check_hotlist_patterns(self):
        """定时检测热点股票形态"""
        if not hasattr(self, 'hotlist_panel') or self.df_all.empty:
            return
        try:
            self.hotlist_panel.check_patterns(self.df_all)
        except Exception as e:
            logger.debug(f"Hotlist pattern check error: {e}")


    def _init_td_text_pool(self, max_items=50):
        self.td_text_pool = []

        self.td_font_9 = QtGui.QFont('Arial', 14, QtGui.QFont.Weight.Bold)
        self.td_font_7p = QtGui.QFont('Arial', 12, QtGui.QFont.Weight.Bold)
        self.td_font_norm = QtGui.QFont('Arial', 11, QtGui.QFont.Weight.Normal)

        for _ in range(max_items):
            t = pg.TextItem('', anchor=(0.5, 1))
            t.hide()
            self.kline_plot.addItem(t)
            self.td_text_pool.append(t)

    def _init_tick_signal_pool(self, max_items=50):
        """
        初始化分时图影子信号对象池，用于复用 TextItem 避免频繁 add/remove。
        """
        self.tick_signal_pool = []

        # 字体缓存
        self.tick_font_bold = QtGui.QFont('Arial', 12, QtGui.QFont.Weight.Bold)
        self.tick_font_normal = QtGui.QFont('Arial', 11, QtGui.QFont.Weight.Normal)

        for _ in range(max_items):
            t = pg.TextItem('', anchor=(0.5, 1))
            t.hide()
            self.kline_plot.addItem(t)
            self.tick_signal_pool.append(t)

    def _update_tick_shadow_signal(self, code, tick_df, shadow_decision, x_axis=None):
        """
        高速绘制分时影子信号，复用对象池，显示最近 N 个信号
        """
        if not shadow_decision or 'action' not in shadow_decision:
            return

        action = shadow_decision['action']
        if action not in ("买入", "卖出", "止损", "止盈", "ADD"):
            return

        # 最新价格和索引 - 优先使用 close, 其次 trade
        price_col = 'close' if 'close' in tick_df.columns else ('trade' if 'trade' in tick_df.columns else 'price')
        y_p = float(tick_df[price_col].iloc[-1]) if price_col in tick_df.columns else 0
        idx = len(tick_df) - 1
        x = x_axis[idx] if x_axis is not None else idx

        # 获取对象池元素
        if not hasattr(self, 'tick_signal_pool') or len(self.tick_signal_pool) == 0:
            return  # 对象池耗尽，可扩容或丢弃
        t = self.tick_signal_pool.pop(0)

        # 设置文本和样式
        text = '买入' if action in ('买入', 'ADD') else action
        t.setText(text)

        if action in ('止损', '止盈'):
            t.setColor('#FF4500')   # 红橙色
            t.setFont(self.tick_font_bold)
        elif action in ('买入', 'ADD'):
            t.setColor('#00FF00')   # 绿色
            t.setFont(self.tick_font_bold)
        else:
            t.setColor('#FFD700')   # 金黄色
            t.setFont(self.tick_font_normal)

        # 设置位置并显示
        t.setPos(x, y_p)
        t.show()

        # 回收对象池（末尾追加，实现循环复用）
        self.tick_signal_pool.append(t)


    def _init_toolbar(self):
        self.toolbar = QToolBar("Settings", self)
        self.toolbar.setObjectName("ResampleToolbar")
        # action = QAction("模拟信号", self)
        # action.setCheckable(True)
        # action.setChecked(self.show_strategy_simulation)
        # action.triggered.connect(self.on_toggle_simulation)
        # self.toolbar.addAction(action)
        # self.toolbar.addSeparator()

        # 模拟信号 Action
        self.sim_action = QAction("模拟信号", self)
        self.sim_action.setCheckable(True)
        self.sim_action.setChecked(self.show_strategy_simulation)
        self.sim_action.triggered.connect(self.on_toggle_simulation)
        self.toolbar.addAction(self.sim_action)

        # 神奇九转 Action
        self.td_action = QAction("九转", self)
        self.td_action.setCheckable(True)
        self.td_action.setChecked(self.show_td_sequential)
        self.td_action.setToolTip("显示/隐藏神奇九转指标")
        self.td_action.triggered.connect(self.on_toggle_td_sequential)
        self.toolbar.addAction(self.td_action)

        # [NEW] SBC 回放 Action
        self.sbc_replay_action = QAction("SBC回放", self)
        self.sbc_replay_action.setToolTip("使用本地缓存/日线数据执行SBC逻辑回放")
        self.sbc_replay_action.triggered.connect(lambda: self._run_sbc_test(False))
        self.toolbar.addAction(self.sbc_replay_action)

        # [NEW] Rearrange Action
        self.rearrange_action = QAction("重排", self)
        self.rearrange_action.setToolTip("自动平铺所有打开的监控窗口")
        self.rearrange_action.triggered.connect(self._on_rearrange_clicked)
        self.toolbar.addAction(self.rearrange_action)

        # # [RESTORE] 测试信号按钮
        # test_action = QAction("测试信号", self)
        # test_action.triggered.connect(self._test_send_signal)
        # self.toolbar.addAction(test_action)
        
        # self.toolbar.addSeparator()

        # 系统级全局快捷键开关
        self.global_shortcuts_enabled = False  # 默认关闭（仅 App-wide）
        self.system_hotkeys_registered = False
        
        if KEYBOARD_AVAILABLE:
            self.gs_action = QAction("GlobalKeys", self)
            self.gs_action.setCheckable(True)
            self.gs_action.setToolTip("开启后快捷键为系统级（即使应用失去焦点也有效）")
            self.gs_action.setChecked(self.global_shortcuts_enabled)
            self.gs_action.triggered.connect(self.on_toggle_global_keys)
            self.toolbar.addAction(self.gs_action)
        else:
            # keyboard 库不可用，添加提示
            label = QLabel(" [系统快捷键不可用] ")
            label.setStyleSheet("color: gray; font-size: 10px;")
            self.toolbar.addWidget(label)

        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self.toolbar.setStyleSheet("""
        QToolBar#ResampleToolbar QToolButton {
            padding: 4px 8px;
            margin: 2px;
        }

        QToolBar#ResampleToolbar QToolButton:checked {
            background-color: #ffd700;
            color: black;
            font-weight: bold;
            border-radius: 3px;
        }
        """)

    # def _test_send_signal(self):
    #     """测试发送信号 (Restored)"""
    #     if hasattr(self, 'signal_log_panel'):
    #         import random
    #         patterns = ['上升三法', '老鸭头', '蚂蚁上树', '出水芙蓉', '均线金叉']
    #         code = f"{random.randint(600000, 603000):06d}"
    #         pattern = random.choice(patterns)
    #         self.signal_log_panel.append_log(code, "测试股票", pattern, f"测试信号: {pattern} 出现", is_high_priority=True)
    #         logger.info(f"Test signal sent: {code} - {pattern}")
    #     else:
    #         QMessageBox.warning(self, "错误", "信号面板未初始化")

    def on_toggle_simulation(self, checked):
        self.show_strategy_simulation = checked
        if self.current_code:
            self.render_charts(self.current_code, self.day_df, getattr(self, 'tick_df', pd.DataFrame()))

    def _on_rearrange_clicked(self):
        """Trigger global window tiling across all PyQuant windows."""
        try:
            try:
                from .qt_window_utils import tile_all_windows
            except ImportError:
                from qt_window_utils import tile_all_windows
            tile_all_windows()
        except Exception as e:
            logger.error(f"Rearrange error: {e}")

    # def on_toggle_td_sequential(self, checked):
    #     """切换神奇九转显示"""
    #     self.show_td_sequential = checked
    #     # 清除现有的 TD 标记
    #     if not checked and hasattr(self, 'td_text_items'):
    #         for item in self.td_text_items:
    #             if hasattr(self, 'kline_plot') and item in self.kline_plot.items:
    #                 self.kline_plot.removeItem(item)
    #         self.td_text_items = []
    #     # 如果开启，重新渲染图表
    #     elif checked and self.current_code:
    #         self.render_charts(self.current_code, self.day_df, getattr(self, 'tick_df', pd.DataFrame()))

    def on_toggle_td_sequential(self, checked):
        """切换神奇九转显示（对象池安全版）"""
        self.show_td_sequential = checked

        # TD 图层还没初始化，直接返回
        if not hasattr(self, 'td_text_pool'):
            return

        if not checked:
            # ❗ 只隐藏，不 remove
            for t in self.td_text_pool:
                t.hide()
        else:
            # 开启时，重新渲染（会复用对象池）
            if self.current_code:
                self.render_charts(
                    self.current_code,
                    self.day_df,
                    getattr(self, 'tick_df', pd.DataFrame())
                )

    def _on_sbc_window_destroyed(self, win):
        """窗口关闭时自动清理资源"""
        if win in self._sbc_windows:
            state = self._sbc_windows.pop(win)
            if 'timer' in state and state['timer']:
                state['timer'].stop()
            if 'thread' in state and state['thread'] and state['thread'].isRunning():
                state['thread'].quit()
            logger.info(f"🗑️ SBC 窗口已关闭，自动停止刷新: {state.get('code')}")

    def _start_sbc_realtime_refresh(self, data, win):
        """启动特定窗口的实时刷新"""
        if win in self._sbc_windows:
             return
             
        code = data.get("code") or re.search(r"\[(\d+)\]", data.get("title", "")).group(1) if re.search(r"\[(\d+)\]", data.get("title", "")) else None
        if not code: return

        # 每 180 秒运行一次刷新 跟随duration_sleep_time
        timer = QTimer(win)
        timer.timeout.connect(partial(self._refresh_sbc_data, win))
        timer.start(self.refresh_interval_ms)

        self._sbc_windows[win] = {
            "code": code,
            "extra_lines": data.get("extra_lines"),
            "timer": timer,
            "thread": None,
            "use_live": data.get("_use_live", True),
            "realtime": data.get("_realtime", True)
        }

        # 窗口关闭自动清理
        win.destroyed.connect(lambda: self._on_sbc_window_destroyed(win))

    def _refresh_sbc_data(self, win):
        """针对特定窗口刷新数据"""
        try:
            if sip.isdeleted(win) or not win.isVisible():
                return

            state = self._sbc_windows.get(win)
            if not state: return

            # 防止针对同一窗口的并发刷新
            if state['thread'] and state['thread'].isRunning():
                return

            thread = SBCTestThread(
                state['code'],
                use_live=state.get('use_live', True),
                hdf5_lock=getattr(self, "hdf5_lock", None),
                extra_lines=state['extra_lines'],
                realtime=state.get('realtime', True),
                win_ref=win
            )

            thread.finished_data.connect(self._on_sbc_test_finished)
            thread.error_occurred.connect(self._on_sbc_test_error)
            state['thread'] = thread
            thread.start()

        except Exception as e:
            logger.error(f"SBC 自动刷新失败: {e}")

    def _run_sbc_test(self, use_live: bool, code: Optional[str] = None):
        """
        [NEW] 调用 verify_sbc_pattern.py 逻辑验证指定或当前个股 of SBC 信号
        使用线程异步执行，防止 GUI 卡死
        """
        target_code = code or self.current_code
        if not target_code:
            QMessageBox.warning(self, "未选中个股", "请先在主图或列表中选中/加载一只个股再执行测试。")
            return

        # 检查是否该代码已有线程正在运行 (允许不同代码并发)
        active_threads = []
        if hasattr(self, '_sbc_test_windows'):
             for win in self._sbc_test_windows:
                 state = self._sbc_windows.get(win)
                 if state and state.get('code') == target_code and state.get('thread') and state['thread'].isRunning():
                     active_threads.append(state['thread'])
        
        if not active_threads:
            # 同时也检查主请求线程
            if hasattr(self, '_sbc_req_thread') and self._sbc_req_thread and self._sbc_req_thread.isRunning() and self._sbc_req_thread.code == target_code:
                active_threads.append(self._sbc_req_thread)

        if active_threads:
            QMessageBox.information(self, "请稍候", f"后台正在对 {target_code} 进行验证，请等待完成后再试。")
            return

        target_code = code or self.current_code
        if not target_code:
            QMessageBox.warning(self, "未选中个股", "请先在主图或列表中选中/加载一只个股再执行测试。")
            return
            
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import Qt
        modifiers = QGuiApplication.keyboardModifiers()
        is_multi_window = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        self._sbc_test_is_multi = is_multi_window

        # 尝试获取 HDF5 锁
        hdf5_lock = getattr(self, 'hdf5_mutex', None)
        
        # 发送开始日志
        logger.info(f"⏳ SBC 信号测试已启动后台线程: {target_code} (Live Mode: {use_live})")
        
        # [NEW DATA EXTRACTION] 从 df_all 提取最新数据透传给 SBC 验证逻辑
        extra_lines = {}
        if hasattr(self, 'df_all') and not self.df_all.empty and target_code in self.df_all.index:
            try:
                row = self.df_all.loc[target_code]
                row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                extra_lines = {
                    'last_close': float(row_dict.get('lastp1d', 0)),
                    'last_high':  float(row_dict.get('lasth1d', 0)),
                    'last_low':   float(row_dict.get('lastl1d', 0)),
                    'high4':      float(row_dict.get('high4', 0)),
                    'df_all_row': row_dict  # 完整透传给 verify_sbc_pattern
                }
            except Exception as e:
                logger.warning(f"Failed to extract extra_lines for SBC test in GUI: {e}")

        # [FIX] 如果是回放模式 (use_live=False)，通常不开启自动刷新，除非明确要求。
        # 这样可以解决用户反馈的“回放变成了实时模式”的问题。
        # is_realtime_req = self.realtime if use_live else False
        is_realtime_req = self.realtime
        
        # 创建并启动后台线程 (使用独立属性避免阻塞)
        self._sbc_req_thread = SBCTestThread(target_code, use_live, hdf5_lock=hdf5_lock, extra_lines=extra_lines, realtime=is_realtime_req)
        self._sbc_req_thread.finished_data.connect(self._on_sbc_test_finished)
        self._sbc_req_thread.error_occurred.connect(self._on_sbc_test_error)
        self._sbc_req_thread.start()




    def _on_sbc_test_finished(self, data: dict, win_ref=None):
        """线程完成后的回调，在 GUI 线程显示图表"""
        try:
            if win_ref and sip.isdeleted(win_ref):
                return

            realtime = data.get("_realtime", False)
            
            # 动态导入可视化函数
            try:
                from stock_visual_utils import show_chart_with_signals
            except ImportError:
                from stock_standalone.stock_visual_utils import show_chart_with_signals

            # 管理窗口引用，防止被回收
            if not hasattr(self, '_sbc_test_windows'):
                self._sbc_test_windows = []

            self._sbc_test_windows = [
                w for w in self._sbc_test_windows if not sip.isdeleted(w) and w.isVisible()
            ]

            is_multi = getattr(self, '_sbc_test_is_multi', False)
            
            # 确定要更新的窗口
            existing_win = win_ref
            if not existing_win and not is_multi and self._sbc_test_windows:
                existing_win = self._sbc_test_windows[-1]

            # 使用返回的结果包调用可视化
            win = show_chart_with_signals(
                data["viz_df"],
                data["signals"],
                data["title"],
                avg_series=data.get("avg_series"),
                time_labels=data.get("time_labels"),
                use_line=data.get("use_line", False) if realtime else False,
                extra_lines=data.get("extra_lines"),
                existing_win=existing_win,
                skip_focus=bool(win_ref) # 如果是自动刷新，不抢焦点
            )

            if win and win not in self._sbc_test_windows:
                self._sbc_test_windows.append(win)
                logger.info(f"✅ SBC 可视化窗口已创建并激活: {data['title']}")
                
                # [NEW] 自动平铺窗口
                try:
                    from .qt_window_utils import tile_all_windows
                    QTimer.singleShot(1000, tile_all_windows)
                except Exception:
                    pass

            # ★ 启动或更新自动刷新管理
            if realtime and win:
                self._start_sbc_realtime_refresh(data, win)

        except Exception as e:
            import traceback
            logger.error(f"SBC 可视化显示失败: {e}\n{traceback.format_exc()}")
            self._on_sbc_test_error(f"渲染图表失败: {str(e)}")

    def _on_sbc_test_error(self, err_msg: str):
        """线程出错回调"""
        logger.error(f"❌ SBC 测试线程出错: {err_msg}")
        QMessageBox.critical(self, "SBC 测试错误", err_msg)



    def on_toggle_global_keys(self, checked):
        """切换系统级全局快捷键"""
        self.global_shortcuts_enabled = checked
        
        # 1. 注销/注册系统热键 (keyboard)
        if checked:
            self._register_system_hotkeys()
        else:
            self._unregister_system_hotkeys()
            
        # 2. 动态启用/禁用冲突的 App-wide 快捷键 (防止双重触发)
        # 包含所有的核心全局热键，确保系统模式开启时，App 内部的 Shortcut 被屏蔽
        # conflict_keys = ["Alt+T", "Alt+F", "Ctrl+/", "Alt+H", "Alt+L"]
        conflict_keys = ["Alt+T", "Alt+F",  "Alt+H", "Alt+L"]
        if hasattr(self, 'shortcuts'):
            for key in conflict_keys:
                if key in self.shortcuts:
                    self.shortcuts[key].setEnabled(not checked)
        
        state = "全局模式 (System Wide)" if checked else "窗口模式 (App Wide)"
        logger.info(f"Shortcut mode changed to: {state}")

    def _register_system_hotkeys(self):
        """注册系统级全局快捷键"""
        if not KEYBOARD_AVAILABLE or not keyboard or self.system_hotkeys_registered:
            return
            
        try:
            # 注册系统全局快捷键 (使用 QTimer 确保主线程执行)
            keyboard.add_hotkey('alt+t', lambda: QTimer.singleShot(0, self._show_signal_box))
            keyboard.add_hotkey('alt+f', lambda: QTimer.singleShot(0, self._show_filter_panel))
            # keyboard.add_hotkey('ctrl+/', lambda: QTimer.singleShot(0, self.show_shortcut_help))
            keyboard.add_hotkey('alt+h', lambda: QTimer.singleShot(0, self._toggle_hotlist_panel))
            keyboard.add_hotkey('alt+l', lambda: QTimer.singleShot(0, self._toggle_signal_log))
            
            # 兼容性补充 (Ctrl+Alt+H 等)
            # keyboard.add_hotkey('ctrl+alt+h', lambda: QTimer.singleShot(0, self._toggle_hotlist_panel))
            # keyboard.add_hotkey('ctrl+alt+l', lambda: QTimer.singleShot(0, self._toggle_signal_log))
            
            self.system_hotkeys_registered = True
            logger.info("✅ 系统级全局快捷键已注册 (Alt+T, Alt+H, Alt+L)")
        except Exception as e:
            logger.error(f"❌ 系统快捷键注册失败: {e}")
            self.global_shortcuts_enabled = False
    
    def _unregister_system_hotkeys(self):
        """注销系统级全局快捷键"""
        if not KEYBOARD_AVAILABLE or not keyboard or not self.system_hotkeys_registered:
            return
        
        try:
            keyboard.remove_hotkey('alt+t')
            keyboard.remove_hotkey('alt+f')
            # keyboard.remove_hotkey('ctrl+/')
            keyboard.remove_hotkey('alt+h')
            keyboard.remove_hotkey('alt+l')
            self.system_hotkeys_registered = False
            logger.info("✅ 系统级全局快捷键已注销")
        except Exception as e:
            logger.warning(f"⚠️ 系统快捷键注销失败: {e}")

    def _safe_len(self, df, fallback=150):
        """
        安全获取数据长度：
        1. 优先 df
        2. 其次 self.df_all
        3. 最后 fallback
        """
        if isinstance(df, pd.DataFrame) and not df.empty:
            return len(df)

        day_df = getattr(self, 'day_df', None)
        if isinstance(day_df, pd.DataFrame) and not day_df.empty:
            return len(day_df)

        return fallback

    # def _reset_kline_view(self, df=None):
    #     """重置 K 线图视图：始终优先显示右侧最新的 120-150 根（不压缩全览）
        
    #     [FIX] 自适应 filter 面板宽度：当 filter 面板打开时，动态计算额外的右侧边距，
    #           防止 K 线最新数据被 filter 面板遮挡。
    #     """
    #     if not isinstance(df, pd.DataFrame):
    #         df = getattr(self, 'day_df', pd.DataFrame())

    #     if not hasattr(self, 'kline_plot') or df.empty:
    #         return

    #     vb = self.kline_plot.getViewBox()
    #     n = len(df) 
        
    #     # 设定默认显示根数 ( trader 视角: 120-150 根最舒适)
    #     display_n = self._safe_len(df, fallback=150)
    #     logger.debug(f'display_n:{display_n}')
    #     # 1. 暂时启用全局自动缩放，让 pyqtgraph 找到 Y 数据边界
    #     vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
    #     vb.setAutoVisible(y=True)

    #     # 2. X 轴：右对齐，显示最新的 display_n 根
    #     vb.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        
    #     # ⭐ [FIX] 计算 filter 面板占用的像素宽度，转换为需要额外留出的 K 线根数
    #     extra_right_margin = 0.0
    #     try:
    #         if hasattr(self, 'main_splitter'):
    #             sizes = self.main_splitter.sizes()
    #             if len(sizes) >= 3 and sizes[2] > 0:
    #                 filter_width_px = sizes[2]  # filter 面板像素宽度
    #                 chart_width_px = sizes[1]   # K 线图区域像素宽度（直接从 splitter 获取，更准确）
                    
    #                 if chart_width_px > 0 and display_n > 0:
    #                     # 计算每根 K 线占用的像素宽度
    #                     bar_width_px = chart_width_px / display_n
                        
    #                     # filter 面板虽然不会直接遮挡 K 线图（它们是并列的），
    #                     # 但当 filter 面板打开时，K 线图区域变窄，每根 K 线占用的像素更少，
    #                     # 导致原来的 3.5 根缓冲空间可能不够。
    #                     # 额外边距 = filter 宽度占 K 线区域宽度的比例 * 显示根数的一定比例
    #                     ratio = filter_width_px / chart_width_px
    #                     extra_right_margin = ratio * display_n * 0.02  # 取 2% 作为安全边距
    #                     extra_right_margin = min(max(extra_right_margin, 1.0), 8.0)  # 限制在 1-8 根之间
    #     except Exception as e:
    #         logger.debug(f"_reset_kline_view filter margin calc error: {e}")
        
    #     # 右侧留 3.5 根缓冲空间（给信号箭头和最新 ghost 留位置），确保不被右侧边界遮挡
    #     base_right_margin = 3.5
    #     x_max = n + base_right_margin + extra_right_margin
    #     x_min = max(-1.5, x_max - display_n)
        
    #     # 核心：使用 setRange 并确保 padding 为 0，精准控制
    #     vb.setRange(xRange=(x_min, x_max), padding=0)

    #     # 3. 强制刷新 Y 轴到当前可见 X 范围的最佳高度
    #     vb.autoRange()
    #     # logger.debug(f"[VIEW] Reset to TraderView: {x_min:.1f} to {x_max:.1f} (total {n})")
    #     # logger.debug(f"[VIEW] Reset to FullView: 0-{n} (Range: {x_min}-{x_max})")

    def _init_resample_toolbar(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Resample:"))

        self.resample_group = QActionGroup(self)
        self.resample_group.setExclusive(True)

        self.resample_actions = {}

        label_map = {
            'd': '1D',
            '2d': '2D',
            '3d': '3D',
            'w': '1W',
            'm': '1M',
        }

        for key in self.resample_keys:
            act = QAction(label_map.get(key, key), self)
            act.setCheckable(True)
            act.setData(key)

            if key == self.resample:
                act.setChecked(True)

            act.triggered.connect(lambda checked, k=key: self.on_resample_changed(k))

            self.resample_group.addAction(act)
            self.toolbar.addAction(act)
            self.resample_actions[key] = act

        # 分隔符并添加监理详情按钮
        self.toolbar.addSeparator()
        self.supervision_action = QAction("🛡️监理详情", self)
        self.supervision_action.triggered.connect(self.show_supervision_details)
        self.toolbar.addAction(self.supervision_action)

    def switch_resample_prev(self):
        self.current_resample_idx = (self.current_resample_idx - 1) % len(self.resample_keys)
        key = self.resample_keys[self.current_resample_idx]
        self.on_resample_changed(key)

    def switch_resample_next(self):
        self.current_resample_idx = (self.current_resample_idx + 1) % len(self.resample_keys)
        key = self.resample_keys[self.current_resample_idx]
        self.on_resample_changed(key)

    def on_resample_changed(self, key):
        if key not in self.resample_keys:
            return

        if key == self.resample:
            return

        # ① 更新内部状态
        self.resample = key
        self.current_resample_idx = self.resample_keys.index(key)

        # ② 同步 toolbar UI（关键）
        act = self.resample_actions.get(key)
        if act is not None and not act.isChecked():
            act.setChecked(True)

        # ③ 执行真实业务逻辑
        if self.current_code:
            self.load_stock_by_code(self.current_code)

    def _init_tdx(self):
        """Initialize TDX / THS independent link toggles"""
        self.toolbar.addSeparator()
        
        # 简洁样式：只增大指示器
        checkbox_style = """
            QCheckBox { font-weight: bold; spacing: 5px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """
        
        # TDX 开关
        self.tdx_btn = QCheckBox("📡 TDX")
        self.tdx_btn.setChecked(self.tdx_enabled)
        self.tdx_btn.stateChanged.connect(self._on_tdx_toggled)
        self.tdx_btn.setStyleSheet(checkbox_style)
        self.toolbar.addWidget(self.tdx_btn)
        
        # THS 开关
        self.ths_btn = QCheckBox("📡 THS")
        self.ths_btn.setChecked(self.ths_enabled)
        self.ths_btn.stateChanged.connect(self._on_ths_toggled)
        self.ths_btn.setStyleSheet(checkbox_style)
        self.toolbar.addWidget(self.ths_btn)

    def _on_tdx_toggled(self, state):
        """TDX 联动开关切换"""
        self.tdx_enabled = bool(state)
        if hasattr(self, 'tdx_var'):
            self.tdx_var.set(self.tdx_enabled)
        logger.info(f'TDX 联动: {"已开启" if self.tdx_enabled else "已关闭"}')
        # 刷新 sender 句柄
        if hasattr(self, 'sender') and hasattr(self.sender, 'reload'):
            self.sender.reload()

    def _on_ths_toggled(self, state):
        """THS 联动开关切换"""
        self.ths_enabled = bool(state)
        if hasattr(self, 'ths_var'):
            self.ths_var.set(self.ths_enabled)
        logger.info(f'THS 联动: {"已开启" if self.ths_enabled else "已关闭"}')
        # 刷新 sender 句柄
        if hasattr(self, 'sender') and hasattr(self.sender, 'reload'):
            self.sender.reload()

    # 保留旧方法作为兼容
    def on_tdx_toggled(self, state):
        """Enable or disable code sending via sender (legacy compatibility)"""
        self._on_tdx_toggled(state)

    def _init_real_time(self):
        """Initialize TDX / code link toggle"""
        self.real_time_cb = QCheckBox("实时")
        self.real_time_cb.setChecked(self.realtime)  # 默认联动
        self.real_time_cb.stateChanged.connect(self.on_real_time_toggled)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.real_time_cb)

        # --- 添加股票代码搜索框 ---
        self.toolbar.addSeparator()
        search_label = QLabel("🔍")
        self.toolbar.addWidget(search_label)
        
        self.code_search_input = QLineEdit()
        self.code_search_input.setPlaceholderText("输入代码...")
        self.code_search_input.setFixedWidth(80)
        self.code_search_input.setMaxLength(6)
        self.code_search_input.returnPressed.connect(self._on_search_code_jump)
        # 输入后延迟2秒自动执行
        self._search_debounce_timer = QTimer()
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.timeout.connect(self._on_search_code_jump)
        self.code_search_input.textChanged.connect(self._on_search_text_changed)
        # 右键菜单：自动粘贴并提取6位数字
        self.code_search_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.code_search_input.customContextMenuRequested.connect(self._on_search_input_right_click)
        self.code_search_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(40, 40, 40, 200);
                color: #00FF00;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 5px;
            }
            QLineEdit:focus {
                border: 1px solid #00BFFF;
            }
        """)
        self.toolbar.addWidget(self.code_search_input)

        # --- [NEW] 板块过滤框 ---
        self.toolbar.addSeparator()
        cat_label = QLabel("🏷️")
        cat_label.setToolTip("过滤板块: 双击 K 线图标题中的板块词复制，再右键此框粘贴过滤")
        self.toolbar.addWidget(cat_label)

        self.cat_filter_input = QComboBox()
        self.cat_filter_input.setEditable(True)
        self.cat_filter_input.lineEdit().setPlaceholderText("板块过滤...")
        self.cat_filter_input.setFixedWidth(130)
        self.cat_filter_input.setToolTip("选择 history5 记录或输入名称过滤 (支持右键粘贴自动智能格式化)")
        self.cat_filter_input.setStyleSheet("""
            QComboBox {
                background-color: rgba(40, 40, 40, 200);
                color: #FFCC00;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 5px;
            }
            QComboBox:focus {
                border: 1px solid #FFCC00;
            }
            QComboBox QAbstractItemView {
                background-color: rgba(30, 30, 30, 240);
                color: #FFCC00;
                selection-background-color: #555;
            }
        """)
        self.cat_filter_input.lineEdit().returnPressed.connect(self._on_cat_filter_apply)
        self.cat_filter_input.activated.connect(self._on_cat_filter_activated)
        
        # 右键菜单：自动粘贴并智能格式化
        self.cat_filter_input.lineEdit().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cat_filter_input.lineEdit().customContextMenuRequested.connect(self._on_cat_filter_right_click)
        self.toolbar.addWidget(self.cat_filter_input)

        cat_query_btn = QPushButton("过滤")
        cat_query_btn.setToolTip("按板块名称过滤左侧股票列表")
        cat_query_btn.setFixedWidth(40)
        cat_query_btn.clicked.connect(self._on_cat_filter_apply)
        self.toolbar.addWidget(cat_query_btn)

        cat_clear_btn = QPushButton("清空")
        cat_clear_btn.setToolTip("清空板块过滤，还原列表")
        cat_clear_btn.setFixedWidth(40)
        cat_clear_btn.clicked.connect(self._on_cat_filter_clear)
        self.toolbar.addWidget(cat_clear_btn)

        # --- 添加右侧 Reset 按钮 ---
        spacer = QWidget()        # 占位伸缩
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.toolbar.addWidget(spacer)  # 占满中间空间，把后面的按钮推到右边

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_kline_view)
        self.toolbar.addWidget(reset_btn)



    def on_real_time_toggled(self, state):
        self.realtime = bool(state)
        # 当前时间是否在交易时段
        is_work_time = cct.get_work_time_duration()

        if self.realtime and self.current_code and is_work_time or self._debug_realtime:
            self._start_realtime_process(self.current_code)
        else:
            self._stop_realtime_process()
            # 清理今天的数据（保留历史日 K）
            if not self.day_df.empty and cct.get_work_time_duration():
                today_str = pd.Timestamp.today().strftime('%Y-%m-%d')
                self.day_df = self.day_df[self.day_df.index < today_str]
                logger.info(f"[INFO] Real-time stopped, cleared today's:{today_str} data for {self.current_code}")

    def _on_search_code_jump(self):
        """处理搜索框回车：支持 6 位代码或中文名称跳转"""
        raw_input = self.code_search_input.text().strip()
        if not raw_input:
            return
        
        self._search_code = raw_input
        # 判断是否包含中文
        is_name_search = any('\u4e00' <= char <= '\u9fa5' for char in raw_input)
        
        found_row = -1
        target_code = ""
        
        if is_name_search:
            # --- 1. 名称搜索模式 ---
            name_col = -1
            if hasattr(self, 'headers'):
                try:
                    name_col = self.headers.index('name')
                except ValueError:
                    pass
            
            if name_col >= 0:
                for row in range(self.stock_table.rowCount()):
                    name_item = self.stock_table.item(row, name_col)
                    if name_item and name_item.text().strip() == raw_input:
                        found_row = row
                        break
            
            # 如果表格中没找到，尝试在全量映射中反查代码
            if found_row == -1 and hasattr(self, 'code_name_map') and self.code_name_map:
                for c, n in self.code_name_map.items():
                    if n == raw_input:
                        target_code = c
                        break
        else:
            # --- 2. 代码搜索模式 (原有逻辑) ---
            code = raw_input.zfill(6)
            target_code = code
            for row in range(self.stock_table.rowCount()):
                item = self.stock_table.item(row, 0)  # 第一列是 code
                if item:
                    item_code = item.data(Qt.ItemDataRole.UserRole) or item.text()
                    if str(item_code).zfill(6) == code:
                        found_row = row
                        break
        
        # 执行跳转或直接加载
        if found_row >= 0:
            # 找到匹配行 - 选中并滚动到可见
            self.stock_table.setCurrentCell(found_row, 0)
            self.stock_table.scrollToItem(self.stock_table.item(found_row, 0))
            # 提取真实代码加载
            code_item = self.stock_table.item(found_row, 0)
            final_code = code_item.data(Qt.ItemDataRole.UserRole) or code_item.text()
            self.load_stock_by_code(str(final_code).zfill(6))
            self.show_status_message(f"✅ 跳转到: {raw_input}", 3000)
        elif target_code:
            # 表中未找到，但有目标代码，直接加载
            self.load_stock_by_code(str(target_code).zfill(6))
            self.show_status_message(f"🚀 直接加载: {raw_input} ({target_code})", 3000)
        else:
            self.show_status_message(f"❌ 未找到匹配: {raw_input[:10]}", 3000)
            logger.error(f"❌ 未找到匹配: {raw_input}")

    def _on_search_input_right_click(self, pos):
        """搜索框右键菜单：自动粘贴并提取6位数字"""
        import re
        
        # 获取剪贴板内容
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        
        if not text:
            self.show_status_message("📋 剪贴板为空", 2000)
            return
        
        # 提取6位连续数字（优先匹配第一个6位数字串）
        matches = re.findall(r'\d{6}', text)
        if matches:
            code = matches[0]
        else:
            # 如果没有6位连续数字，尝试提取所有数字并取前6位
            digits = re.sub(r'\D', '', text)[:6]
            if len(digits) >= 1:
                code = digits.zfill(6)
            else:
                self.show_status_message("📋 未找到有效数字", 2000)
                return
        
        # 设置到输入框（textChanged 会触发2秒延迟定时器）
        self.code_search_input.setText(code)
        self.code_search_input.setFocus()  # 获取焦点，方便用户按Enter立即跳转

    def _on_search_text_changed(self, text):
        """输入框文本变化时重启延迟定时器（2秒后自动执行）"""
        # 如果输入为空，停止定时器
        if not text.strip():
            self._search_debounce_timer.stop()
            return
        # 重启2秒定时器（每次输入都重置）
        self._search_debounce_timer.stop()
        self._search_debounce_timer.start(2000)  # 2秒延迟

    def _on_cat_filter_right_click(self, pos):
        """板块过滤框右键：自动粘贴剪贴板内容并智能格式化为 category.str.contains("xxx") 查询"""
        import re as _re
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if not text:
            self.show_status_message("📋 剪贴板为空", 2000)
            return

        # 如果是6位数字，转为代码过滤
        if text.isdigit() and len(text) == 6:
            fmt = f'index.str.contains("^{text}")'
        else:
            # 提取第一个中文词（允许混合英文/数字）
            matches = _re.findall(r'[\u4e00-\u9fa5]+[A-Za-z0-9\-\(\)（）]*', text)
            if matches:
                # fmt = matches[0]
                fmt = f'category.str.contains("{matches[0]}")'
            else:
                fmt = text  # 原样

        self.cat_filter_input.setCurrentText(fmt)
        self.cat_filter_input.setFocus()
        # 立即触发过滤
        self._on_cat_filter_apply()

    def _on_cat_filter_activated(self, index):
        """用户在板块过滤下拉框选择了某一项"""
        q = self.cat_filter_input.itemData(index)
        if q:
            self.cat_filter_input.setCurrentText(q)
            self._on_cat_filter_apply()

    def _on_cat_filter_apply(self):
        """执行板块过滤：快速路径用 setRowHidden，不重建行"""
        keyword = self.cat_filter_input.currentText().strip()
        if not keyword:
            self._on_cat_filter_clear()
            return
        try:
            df = self.df_all if hasattr(self, 'df_all') and not self.df_all.empty else pd.DataFrame()
            if df.empty:
                self.show_status_message("⚠️ 当前无数据", 2000)
                return

            # 构建过滤条件
            if '.str.contains' in keyword or '==' in keyword or '>' in keyword or '<' in keyword:
                query_str = keyword
            else:
                if 'category' in df.columns:
                    query_str = f'category.str.contains("{keyword}", na=False)'
                else:
                    query_str = keyword

            from stock_logic_utils import ensure_parentheses_balanced
            final_query = ensure_parentheses_balanced(query_str)
            
            if query_engine:
                matched = query_engine.execute(df, final_query)
            else:
                matched = df.query(final_query)
            if matched.empty:
                self.show_status_message(f"❌ 未找到匹配: {len(matched)}", 3000)
                logger.error(f"❌ 未找到匹配: {keyword}")
                return

            # ⚡ 快速路径：使用 setRowHidden 而非完整重建
            col_key = 'code' if 'code' in matched.columns else None
            matched_codes = set(matched[col_key].astype(str)) if col_key else set(matched.index.astype(str))
            self._cat_filter_visible_codes = matched_codes

            if hasattr(self, '_table_item_map') and self._table_item_map:
                self.stock_table.setUpdatesEnabled(False)
                for code, row_idx in self._table_item_map.items():
                    self.stock_table.setRowHidden(row_idx, code not in matched_codes)
                self.stock_table.setUpdatesEnabled(True)

            self.update_bottom_stats()
            self.show_status_message(f"🏷️ 过滤成功: 共 {len(matched)} 只", 5000)

            # ⭐ [NEW] 自动保存成功的查询到 history5 (如果不在列表中)
            try:
                exists = False
                for i in range(self.cat_filter_input.count()):
                    if self.cat_filter_input.itemData(i) == keyword:
                        exists = True
                        break
                if not exists:
                    from history_manager import quick_save_specific_history
                    if quick_save_specific_history(keyword, "history5"):
                        self.load_cat_filter_history5()
            except Exception as e:
                logger.debug(f"自动保存过滤历史失败: {e}")

        except Exception as e:
            logger.error(f"板块过滤失败: {e}")
            self.show_status_message(f"❌ 过滤出错: {e}", 3000)

    def _on_cat_filter_clear(self):
        """清空板块过滤，快速路径：un-hide 所有行"""
        if hasattr(self, 'cat_filter_input'):
            self.cat_filter_input.clearEditText()
        self._cat_filter_visible_codes = None
        # ⚡ 只 un-hide，不重建，O(n) 极速
        if hasattr(self, 'stock_table') and self.stock_table:
            self.stock_table.setUpdatesEnabled(False)
            for row_idx in range(self.stock_table.rowCount()):
                self.stock_table.setRowHidden(row_idx, False)
            self.stock_table.setUpdatesEnabled(True)
        self.update_bottom_stats()
        self.show_status_message("✅ 已清空板块过滤", 2000)



    def _init_signal_message_box(self):
        """初始化信号消息盒子"""
        if not SIGNAL_QUEUE_AVAILABLE:
            return

        # 添加到工具栏 (放在"实时数据" toggle 后面)
        # 找到包含 '实时数据' 的工具栏
        # 注意: self.toolbar_actions 包含 action 对象

        # 这里创建一个新的工具栏按钮
        self.signal_badge_action = QAction("📬 信号(0)", self)
        self.signal_badge_action.triggered.connect(self._show_signal_box)
        # self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar) # 已经在 _init_toolbar 中添加
        self.toolbar.addAction(self.signal_badge_action)

        self.signal_box_dialog = SignalBoxDialog(self)

        # 快捷键 Alt+Q 已在 _init_global_shortcuts 中统一注册
        # self.signal_shortcut = QShortcut(QKeySequence("Alt+Q"), self)
        # self.signal_shortcut.activated.connect(self._show_signal_box)
        
        # 定时更新徽章 (可选,或者在 push 时触发信号)
        self.signal_timer = QTimer(self)
        self.signal_timer.timeout.connect(self._update_signal_badge)
        self.signal_timer.start(2000) # 每2秒检查一次

    def _show_signal_box(self):
        if hasattr(self, 'signal_box_dialog'):
            if self.signal_box_dialog.isVisible():
                self.signal_box_dialog.hide()
            else:
                # 同步主题
                self.signal_box_dialog.apply_theme(self.qt_theme)
                self.signal_box_dialog.refresh()
                self.signal_box_dialog.show()
                self.signal_box_dialog.raise_()
                self.signal_box_dialog.activateWindow()

     # 安全折叠 filter
    # def collapse_filter(self):
    #     sizes = self.main_splitter.sizes()
    #     logger.info(f'collapse_filter sizes: {len(sizes)}')
    #     # if len(sizes) > 2:
    #     sizes[2] = 0
    #     self.main_splitter.setSizes(sizes)

    # 安全展开 filter
    # def expand_filter(self, width=250):
    #     sizes = self.main_splitter.sizes()
    #     logger.info(f'expand_filter sizes: {len(sizes)}')
    #     sizes[2] = width
    #     self.main_splitter.setSizes(sizes)

    # def toggle_filter(self):
    #     sizes = self.main_splitter.sizes()
    #     if sizes[2] == 0:
    #         self.expand_filter(250)
    #     else:
    #         self.collapse_filter()

    def _show_filter_panel(self):
        """
        切换 Filter 面板显示状态：
        - 如果当前可见，则关闭
        - 如果当前隐藏，则打开
        - 内部通过 toggle_filter_panel 控制实际显示/隐藏
        """
        if not hasattr(self, 'filter_panel'):
            return

        sizes = self.main_splitter.sizes()
        # 当前是否可见
        is_presently_visible = True if sizes[2] > 0 else False

        # 切换状态
        if is_presently_visible:
            # 隐藏 Filter
            self.toggle_filter_panel(False)
            self.filter_action.setChecked(False)
        else:
            # 打开 Filter
            self.toggle_filter_panel(True)
            self.filter_action.setChecked(True)

    def _update_signal_badge(self):
        if hasattr(self, 'signal_box_dialog') and self.signal_box_dialog._queue_mgr:
            signals = self.signal_box_dialog._queue_mgr.get_top()
            count = len(signals)
            self.signal_badge_action.setText(f"📬 信号({count})")

            # 检查是否有新信号并播报 (语音播报逻辑)
            if not signals: return

            # ⭐ CHECK MUTE STATE (Global / Hotlist Control)
            if hasattr(self, 'hotlist_panel') and self.hotlist_panel._voice_paused:
                return

            # ⚡ [OPTIMIZATION] 语音去重缓存，避免重复播报
            if not hasattr(self, '_spoken_cache'): 
                self._spoken_cache = set()
                self._last_spoken_clean_time = 0
            
            import time
            now = time.time()
            if now - self._last_spoken_clean_time > 300: # 每5分钟清理一次缓存
                self._spoken_cache.clear()
                self._last_spoken_clean_time = now

            count_spoken = 0
            for msg in signals[:5]: # 前5条
                # 仅播报 High Priority (<100)
                if msg.priority < 100: # 放宽限制
                    # 去重键: 代码 + 类型 + 分钟级时间戳 (同一分钟内不重复报)
                    dedup_key = (msg.code, msg.signal_type, msg.timestamp[:16]) 
                    if dedup_key in self._spoken_cache:
                        continue
                        
                    strategy_name = msg.signal_type
                    if strategy_name == "HOT_WATCH": strategy_name = "热点"
                    elif strategy_name == "CONSOLIDATION": strategy_name = "蓄势"
                    elif strategy_name == "SUDDEN_LAUNCH": strategy_name = "突发"
                    
                    # ⚡ [REMOVED] 已重构：统一由信号日志面板 log_added 驱动语音播报
                    # 避免重复播报
                    pass
                    # if hasattr(self, 'voice_thread') and self.voice_thread:
                    #     self.voice_thread.speak(text)
                    
                    self._spoken_cache.add(dedup_key)
                    count_spoken += 1
            
            if count_spoken > 0:
                logger.debug(f"Voice broadcast {count_spoken} signals (deduplicated)")

    def _on_strategy_changed(self, index: int) -> None:
        """
        处理策略选择器变更

        策略组合:
        - 0: 回调MA5策略
        - 1: 决策引擎
        - 2: 全策略(含监理)
        """
        from strategy_controller import StrategyController
        strategy_map = {
            0: [StrategyController.STRATEGY_PULLBACK_MA5],
            1: [StrategyController.STRATEGY_DECISION_ENGINE],
            2: [StrategyController.STRATEGY_PULLBACK_MA5,
                StrategyController.STRATEGY_DECISION_ENGINE,
                StrategyController.STRATEGY_SUPERVISOR,
                StrategyController.STRATEGY_STRONG_CONSOLIDATION,
                StrategyController.STRATEGY_SUDDEN_LAUNCH],
        }

        selected_strategies = strategy_map.get(index, [])

        # 更新策略控制器的启用状态
        all_strategies = [
            StrategyController.STRATEGY_PULLBACK_MA5,
            StrategyController.STRATEGY_DECISION_ENGINE,
            StrategyController.STRATEGY_SUPERVISOR,
            StrategyController.STRATEGY_STRONG_CONSOLIDATION,
            StrategyController.STRATEGY_SUDDEN_LAUNCH,
        ]

        for strat in all_strategies:
            if strat in selected_strategies:
                self.strategy_controller.enable_strategy(strat)
            else:
                self.strategy_controller.disable_strategy(strat)

        # 更新决策面板状态显示
        enabled_list = self.strategy_controller.get_enabled_strategies()
        status_text = f"策略: {', '.join(enabled_list)}"
        self.decision_label.setText(f"🎯 {status_text}")

        # 如果当前有加载的股票,自动刷新信号
        if self.current_code and not self.day_df.empty:
            self._refresh_strategy_signals()

        logger.info(f"[策略选择器] 切换到组合 {index}, 启用策略: {enabled_list}")

    def _refresh_strategy_signals(self) -> None:
        """刷新当前股票的策略信号显示"""
        if not self.current_code or self.day_df.empty:
            return

        try:
            # 重新生成信号
            signals = self.strategy_controller.evaluate_historical_signals(
                self.current_code, self.day_df
            )

            # 更新信号覆盖层
            if hasattr(self, 'signal_overlay') and self.signal_overlay:
                self.signal_overlay.update_signals(signals, target='kline')

            logger.info(f"[刷新信号] {self.current_code} 生成 {len(signals)} 个信号")
        except Exception as e:
            logger.error(f"[刷新信号] 失败: {e}")


    def show_supervision_details(self):
        """显示监理详细信息"""
        if not hasattr(self, 'current_supervision_data') or not self.current_supervision_data:
            QMessageBox.information(self, "监理详情", "暂无监理数据。请稍候或检查策略服务是否运行。")
            return

        data = self.current_supervision_data

        # 优先显示点击的信号详情
        if hasattr(self, 'active_signal_context') and self.active_signal_context:
            ctx = self.active_signal_context
            if ctx.get('code') == self.current_code:
                # 覆盖或追加最近信号详情
                data['last_action'] = "SIGNAL LOG"
                data['last_reason'] = ctx.get('message', 'N/A')
                data['shadow_info'] = ctx.get('pattern', 'N/A')

        # 构建 HTML 内容
        content = f"""
        <h3>🛡️ 实时策略监理报告</h3>
        <hr>
        <p><b>股票代码:</b> {self.current_code}</p>
        <br>
        <table border="0" cellpadding="4">
            <tr>
                <td><b>市场胜率 (Win Rate):</b></td>
                <td><span style="color: {'red' if data.get('market_win_rate',0) > 50 else 'green'};">{data.get('market_win_rate', 0):.1f}%</span></td>
            </tr>
            <tr>
                <td><b>当前连亏 (Loss Streak):</b></td>
                <td>{data.get('loss_streak', 0)}</td>
            </tr>
            <tr>
                <td><b>VWAP 偏离:</b></td>
                <td>{data.get('vwap_bias', 0):+.2f}%</td>
            </tr>
        </table>
        <hr>
        <h4>🔎 信号详情 (点击来源)</h4>
        <p><b>模式:</b> {data.get('shadow_info', 'N/A')}</p>
        <p><b>消息:</b> {data.get('last_reason', 'N/A')}</p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle(f"监理详情 - {self.current_code}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(content)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def show_comprehensive_briefing(self):
        """[⭐极限弹窗] 一键显示综合研报信息 (复用模式)"""
        if not self.current_code: return

        # 窗口复用逻辑
        if hasattr(self, '_briefing_dlg') and self._briefing_dlg is not None:
            try:
                if self._briefing_dlg.isVisible():
                    self._briefing_dlg.raise_()
                    self._briefing_dlg.activateWindow()
                    # 更新内容
                    self._update_briefing_content(self._briefing_dlg)
                    return
            except RuntimeError:
                pass  # 窗口已被删除

        # 创建新窗口
        briefing = self._generate_briefing_html()
        dlg = ScrollableMsgBox(f"📈 综合简报 - {self.current_code}", briefing, self)
        self._briefing_dlg = dlg
        dlg.show()  # 使用 show() 而不是 exec() 以允许复用

    def _update_briefing_content(self, dlg):
        """更新简报窗口内容"""
        briefing = self._generate_briefing_html()
        dlg.setWindowTitle(f"📈 综合简报 - {self.current_code}")
        if hasattr(dlg, 'content_label'):
            dlg.content_label.setText(briefing)

    def _generate_briefing_html(self):
        """生成简报HTML内容"""
        # 1. 基础个股信息
        info = self.code_info_map.get(self.current_code)
        if info is None and len(self.current_code) > 6:
            info = self.code_info_map.get(self.current_code[-6:])
        info = info or {}

        # 2. 策略监理信息
        sup = getattr(self, 'current_supervision_data', {})

        # 3. 影子决策 (即时计算)
        shadow = None
        if hasattr(self, 'day_df') and hasattr(self, 'tick_df'):
            shadow = self._run_realtime_strategy(self.current_code, self.day_df, self.tick_df)

        mwr = sup.get('market_win_rate', 0)
        m_color = "#FF4500" if mwr > 50 else "#32CD32"

        briefing = f"""
        <div style='font-family: Microsoft YaHei;'>
            <h2 style='color: #FFD700;'>📊 {self.current_code} 综合实战简报</h2>
            <hr>
            <table width='100%' border='0'>
                <tr>
                    <td><b>个股名称:</b> {info.get('name','N/A')}</td>
                    <td><b>全场排名:</b> <span style='color: yellow;'>{info.get('Rank','N/A')}</span></td>
                </tr>
                <tr>
                    <td><b>当日涨幅:</b> <span style='color: {'red' if info.get('percent',0)>0 else 'green'};'>{info.get('percent','0.00')}%</span></td>
                    <td><b>昨日胜率:</b> {info.get('win','N/A')}</td>
                </tr>
            </table>

            <h3 style='border-bottom: 1px solid #555;'>🛡️ 监理与风控</h3>
            <p><b>市场热度:</b> <span style='color: {m_color}; font-weight: bold;'>{mwr:.1f}% Win Rate</span></p>
            <p><b>账户连亏:</b> <span style='color: orange;'>{sup.get('loss_streak', 0)} 次</span></p>
            <p><b>价量偏离:</b> {sup.get('vwap_bias', 0):+.2f}% (VWAP Bias)</p>

            <h3 style='border-bottom: 1px solid #555;'>🤖 实时策略影子评分</h3>
        """

        if shadow:
            briefing += f"""
            <p><b>影子动作:</b> <span style='color: cyan; font-size: 14pt;'>{shadow.get('action', '持仓待定')}</span></p>
            <p><b>逻辑考量:</b> {shadow.get('reason', '无明确触发')}</p>
            <div style='background: #333; padding: 5px; border-radius: 3px;'>
                <b>核心指标快照:</b><br>
                {" ".join([f"• {k}: {v if not isinstance(v,float) else f'{v:.2f}'}" for k,v in shadow.get('debug',{}).items() if k!='indicators'])}
            </div>
            """
        else:
            briefing += "<p>暂无影子决策数据 (等待行情更新或检查数据源)</p>"

        briefing += """
            <hr>
            <p style='font-size: 9pt; color: #888;'>[快捷键提示] Space: 综述 | S: 监理 | R: 重置视图 | T: 模拟开关</p>
        </div>
        """
        return briefing

    # def _start_realtime_process(self, code):
    #     # 停止旧进程
    #     if self.realtime_process and self.realtime_process.is_alive():
    #         self.realtime_process.terminate()
    #         self.realtime_process.join()

    #     # 启动新进程
    #     self.realtime_process = Process(
    #         target=realtime_worker_process,
    #         args=(code, self.realtime_queue,self.stop_flag,self.log_level,self._debug_realtime),
    #         daemon=False
    #     )
    #     self.realtime_process.start()

    def _start_realtime_process(self, code):
        """常驻进程模式启动/更新实时任务"""
        # 1. 检查缓存 (超过 duration_sleep_time 就获取一次新的)
        now = time.time()
        limit = getattr(cct.CFG, 'duration_sleep_time', 10)
        cached = self._tick_cache.get(code)
        
        if cached and (now - cached['ts']) < limit:
            logger.debug(f"[RT] Cache HIT for {code} (age: {now - cached['ts']:.1f}s)")
            # [FIX] 不再立即触发 GUI 更新，等待 DataLoader 完成后统一渲染
            # 这样可以确保只渲染一次，使用完整的新周期数据
            # self.on_realtime_update(code, cached['tick_df'], cached['today_bar'])
            
            # 虽然有缓存，但如果常驻进程没跑，还是得启动它以便后续更新
            if self.realtime_process and self.realtime_process.is_alive():
                 # 发送到任务队列，让进程在后台慢慢更新
                 self.realtime_task_queue.put(code)
                 return

        # 2. 确保常驻进程在运行
        if not self.realtime_process or not self.realtime_process.is_alive():
            logger.info("[RealtimeProcess] Starting persistent worker...")
            # 重置 stop_flag (专用)
            self.rt_worker_stop_flag.value = True
            # 清空旧任务
            while not self.realtime_task_queue.empty():
                try: self.realtime_task_queue.get_nowait()
                except: break
                
            self.realtime_process = Process(
                target=realtime_worker_process,
                args=(self.realtime_task_queue, self.realtime_queue, self.rt_worker_stop_flag, self.log_level, self._debug_realtime),
                daemon=False
            )
            self.realtime_process.start()

        # 3. 发送新任务
        logger.debug(f"[RealtimeProcess] Switching task to {code}")
        self.realtime_task_queue.put(code)
        
        # ⭐ 4. 立即触发一次 UI 轮询，尝试捕捉随后产生的第一笔数据
        # QTimer.singleShot(1000, self._poll_realtime_queue)
        QTimer.singleShot(3000, self._poll_realtime_queue)  # 双重保险，由于 network 可能有延迟


    def _stop_realtime_process(self):
        if self.realtime_process:
            # 停止常驻进程 (使用专用 flag)
            self.rt_worker_stop_flag.value = False
            self.realtime_process.join(timeout=0.5)
            if self.realtime_process.is_alive():
                self.realtime_process.terminate()
                logger.debug("[RealtimeProcess] Force terminated (timeout)")
            self.realtime_process = None

    def _poll_realtime_queue(self):
        # 顺便清理不再运行的旧线程
        self._cleanup_garbage_threads()
        
        if not hasattr(self, "_closing") or getattr(self, "_closing", False):
            return  # 窗口正在关闭，不再处理队列

        updates_batch = {}  # key: code, value: (tick_df, today_bar)
        
        # 🔄 聚合本周轮所有更新，只保留最新的
        while True:
            try:
                code, tick_df, today_bar = self.realtime_queue.get_nowait()
                updates_batch[code] = (tick_df, today_bar)
            except queue.Empty:
                break
            except (EOFError, OSError):
                logger.warning("Realtime queue closed unexpectedly")
                break
            except Exception:
                logger.exception("Unexpected error in realtime queue")
                break

        # ⚡ 批量处理 GUI 更新
        if self.isVisible():
            for code, (tick_df, today_bar) in updates_batch.items():
                try:
                    self.on_realtime_update(code, tick_df, today_bar)
                    # 更新缓存
                    self._tick_cache[code] = {
                        'tick_df': tick_df,
                        'today_bar': today_bar,
                        'ts': time.time()
                    }
                except RuntimeError as e:
                    logger.warning(f"GUI update skipped: {e}")
                except Exception:
                    logger.exception(f"Error in on_realtime_update for {code}")
        
        # [NEW] 定时更新底部统计信息
        if self.isVisible():
            self.update_bottom_stats()
            
        # [NEW] 联动板块监控面板，推送最新 df_all
        if hasattr(self, 'sector_bidding_panel') and self.sector_bidding_panel is not None:
            if self.sector_bidding_panel.isVisible():
                if hasattr(self, "df_all") and not self.df_all.empty:
                    self.sector_bidding_panel.on_realtime_data_arrived(self.df_all)

    def update_bottom_stats(self):
        """[NEW] 汇总更新底部状态栏统计信息 (支持热点与跟单同步)"""
        try:
            # 1. 主列表计数 (左侧 df_all)
            market_count = len(self.df_all) if hasattr(self, 'df_all') else 0
            
            # 2. 热点与跟单计数 (从 HotlistPanel 获取)
            hot_count = 0
            follow_count = 0
            if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
                hot_count = len(self.hotlist_panel.items)
                follow_count = getattr(self.hotlist_panel, 'follow_count', 0)
            
            # 3. 筛选计数 (Filter Panel)
            filter_count = 0
            if hasattr(self, 'filter_tree') and self.filter_tree:
                filter_count = self.filter_tree.topLevelItemCount()
            
            # 4. 板块过滤计数 (新增)
            cat_filter_active = False
            filtered_count = 0
            if hasattr(self, 'cat_filter_input') and self.cat_filter_input:
                cat_filter_text = self.cat_filter_input.currentText().strip()
                if cat_filter_text:
                    cat_filter_active = True
                    # ⚡ 直接读取可见 code 集合，避免 rowCount() 含隐藏行
                    active_codes = getattr(self, '_cat_filter_visible_codes', None)
                    filtered_count = len(active_codes) if active_codes else 0

            # 5. 构造并更新文本
            # 仅显示非零项，或紧凑显示
            display_parts = []
            display_parts.append(f"📊 市场: {market_count}")
            # 热股大于0才显示醒目
            if hot_count > 0: display_parts.append(f"🔥 热股: {hot_count}")
            else: display_parts.append(f"热股: 0")
            
            if follow_count > 0: display_parts.append(f"📋 跟单: {follow_count}")
            
            # 筛选数 > 0 才显示
            if filter_count > 0: 
                display_parts.append(f"🔍 筛选: {filter_count}")

            # 过滤数激活才显示
            if cat_filter_active:
                display_parts.append(f"🏷️ 过滤: {filtered_count}")

            stats_txt = " | ".join(display_parts)
            
            if hasattr(self, 'stats_label'):
                # 只有在内容变化时才刷新 UI，减少绘图开销
                if self.stats_label.text() != stats_txt:
                    self.stats_label.setText(stats_txt)
        except Exception:
            # 这里的异常通常发生窗口关闭时，静默处理
            pass


    def show_status_message(self, message: str, timeout: int = 0):
        if not hasattr(self, "center_msg_label"):
            return

        if not message:
            self.center_msg_label.clear()
            self.center_msg_label.setVisible(False)
            return

        # 自动省略文本
        fm = QFontMetrics(self.center_msg_label.font())
        # Qt6 中 ElideRight 是 Qt.TextElideMode 枚举
        message = fm.elidedText(message, Qt.TextElideMode.ElideRight, 600)

        self.center_msg_label.setMaximumWidth(600)
        self.center_msg_label.setText(message)
        self.center_msg_label.setVisible(True)

        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.show_status_message(""))

    def show_status_message_nolimit(self, message, timeout=0):
        """
        ⭐ [NEW] 在底部中间显示状态消息 (替代原 StatusBar)
        Args:
            message (str): 要显示的消息内容。如果为空，则清空显示。
            timeout (int): 消息显示的持续时间（毫秒）。0 表示一直显示。
        """
        if not hasattr(self, 'center_msg_label'):
            return
            
        if not message:
            self.center_msg_label.setText("")
            self.center_msg_label.setVisible(False) # Hiding it completely if empty
            return

        self.center_msg_label.setText(message)
        self.center_msg_label.setVisible(True)
        
        # 如果设置了超时，使用 QTimer 清除
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.show_status_message(""))

    def _cleanup_garbage_threads(self):
        """清理线程回收站中已经结束运行的线程"""
        if not self.garbage_threads:
            return
            
        remaining = []
        for t in self.garbage_threads:
            if t.isFinished():
                # 线程已结束，可以安全释放 (由 Python GC 处理)
                logger.debug(f"[DataLoaderThread] Scavenged finished thread: {id(t)}")
                continue
            remaining.append(t)
        self.garbage_threads = remaining

    def apply_df_diff(self, df_diff):
        """安全地应用增量更新到 df_all"""
        try:
            if df_diff is None or df_diff.empty or self.df_all is None or self.df_all.empty:
                return
            
            # 获取两个 DataFrame 共有的索引
            common_idx = self.df_all.index.intersection(df_diff.index)
            if len(common_idx) == 0:
                logger.debug("[apply_df_diff] No common indices between df_diff and df_all")
                return
            
            for col in df_diff.columns:
                if col not in self.df_all.columns:
                    continue  # 跳过 df_all 中不存在的列
                try:
                    # 只处理共有索引上的有效值
                    col_data = df_diff.loc[common_idx, col]
                    valid_mask = col_data.notna()
                    valid_indices = valid_mask[valid_mask].index
                    
                    if len(valid_indices) > 0:
                        self.df_all.loc[valid_indices, col] = df_diff.loc[valid_indices, col]
                except Exception as e:
                    logger.debug(f"[apply_df_diff] Column {col} update failed: {e}")
                    
            # ⚡ [OPTIMIZATION] 记录变更代码，交给节流器异步刷新
            changed_codes = set(df_diff.index.tolist())
            self.update_df_all(self.df_all, changed_codes=changed_codes)
        except Exception as e:
            logger.error(f"[apply_df_diff] Error: {e}")

    def _poll_command_queue(self):
        """轮询内部指令队列 (消费所有积压，只取最新数据)"""
        # ⭐ [FIX] 僵尸进程自杀机制：检查退出标志
        # MonitorTK 在 on_close 时会将 stop_flag 设为 False
        if hasattr(self, 'stop_flag') and self.stop_flag and not self.stop_flag.value:
            logger.info("[Visualizer] Stop flag detected (False), initiating self-destruct...")
            self.close()
            # 确保 Qt 循环结束
            QApplication.quit()
            return

        if not self.command_queue:
            return
        try:
            latest_full_df = None
            df_diffs = []
            
            # 🔄 移除 unreliable 的 empty() 检查，直接进入消费循环
            while True:
                try:
                    cmd_data = self.command_queue.get_nowait()
                except Empty: # queue.Empty
                    break
                except EOFError:
                    break
                    
                if isinstance(cmd_data, tuple) and len(cmd_data) == 2:
                    cmd, val = cmd_data
                    if cmd == 'SWITCH_CODE':
                        if isinstance(val, dict):
                            logger.debug(f"Queue CMD: Switching to {val.get('code')} with params {val}")
                            # [FIX] 避免 multiple values for argument 'code'
                            params = val.copy()
                            code = params.pop('code', None)
                            if code:
                                self.load_stock_by_code(code, **params)
                        else:
                            logger.debug(f"Queue CMD: Switching to {val}")
                            self.load_stock_by_code(val)

                    elif cmd == 'UPDATE_DF_ALL':
                        if isinstance(val, pd.DataFrame):
                            # 全量覆盖 → 丢弃之前的增量
                            latest_full_df = val
                            df_diffs.clear()

                    elif cmd == 'UPDATE_DF_DIFF':
                        if isinstance(val, pd.DataFrame):
                            df_diffs.append(val)
                    
                    elif cmd == 'UPDATE_DF_DATA' and isinstance(val, dict):
                        m_type = val.get('type')
                        payload = val.get('data')
                        ver = val.get('ver', 0)

                        if m_type == 'UPDATE_DF_ALL':
                            self.expected_sync_version = ver
                            latest_full_df = payload
                            df_diffs.clear()
                            logger.debug(f"[Queue] Received Full DF_ALL (ver={ver}, rows={len(payload)})")
                        elif m_type == 'UPDATE_DF_DIFF':
                            if self.expected_sync_version == -1:
                                # 还没有全量包，丢弃增量并请求同步
                                logger.warning("[Queue] Received DIFF before ALL. Requesting full sync.")
                                self._request_full_sync()
                            elif ver == self.expected_sync_version + 1:
                                self.expected_sync_version = ver
                                df_diffs.append(payload)
                            else:
                                logger.warning(f"[Queue] Version mismatch! Got {ver}, expected {self.expected_sync_version + 1}. Requesting full sync.")
                                self._request_full_sync()
                                # 终止本轮增量应用，等待全量同步
                                df_diffs.clear()
                                break
                    
                    elif cmd == 'CMD_SCAN_CONSOLIDATION':
                        # 触发策略扫描
                        logger.debug("Queue CMD: Triggering Consolidation Scan...")
                        # 确保 SignalBoxDialog 已显示
                        self._show_signal_box()
                        # 延迟以确保窗口初始化完成
                        QTimer.singleShot(500, self.signal_box_dialog.on_scan_consolidation)

            # --- 处理最新全量数据 ---
            if latest_full_df is not None:
                logger.info(f"[Queue] Applying full sync ({len(latest_full_df)} rows)...")
                self._process_df_all_update(latest_full_df)

            # --- 处理增量数据 ---
            for diff_df in df_diffs:
                logger.info(f"[Queue] Applying df diff ({len(diff_df)} rows)...")
                self.apply_df_diff(diff_df)

        except Exception as e:
            logger.warning(f"Poll command queue failed: {e}")

    # def _poll_command_queue_ALL(self):
    #     """轮询内部指令队列 (优化：消费所有积压，只取最新全量数据)"""
    #     if not self.command_queue:
    #         return
    #
    #     try:
    #         latest_df = None
    #         while not self.command_queue.empty():
    #             cmd_data = self.command_queue.get_nowait()
    #             if isinstance(cmd_data, tuple) and len(cmd_data) == 2:
    #                 cmd, val = cmd_data
    #                 if cmd == 'SWITCH_CODE':
    #                     logger.info(f"Queue CMD: Switching to {val}")
    #                     self.load_stock_by_code(val)
    #                 elif cmd == 'UPDATE_DF_ALL':
    #                     # 记录最新的全量数据，跳过中间过时的
    #                     if isinstance(val, pd.DataFrame):
    #                         latest_df = val
    #
    #         # 处理最鲜活的一份数据
    #         if latest_df is not None:
    #             logger.debug(f"Queue CMD: Instant sync df_all ({len(latest_df)} rows)")
    #             self.update_df_all(latest_df)
    #
    #     except Exception as e:
    #         logger.debug(f"Poll command queue failed: {e}")

    def push_stock_info(self,stock_code, row):
        """
        从 self.df_all 的一行数据提取 stock_info 并推送
        """
        try:
            stock_info = {
                "code": str(stock_code),
                "name": str(row["name"]),
                "high": str(row["high"]),
                "lastp1d": str(row["lastp1d"]),
                "percent": float(row.get("percent", 0)),
                "price": float(row.get("close", 0)),
                "volume": int(row.get("volume", 0))
            }
            # code, _ , percent,price, vol
            # 转为 JSON 字符串
            payload = json.dumps(stock_info, ensure_ascii=False)

            # ---- 根据传输方式选择 ----
            # 如果用 WM_COPYDATA，需要 encode 成 bytes 再传
            # if hasattr(self, "send_wm_copydata"):
            #     self.send_wm_copydata(payload.encode("utf-8"))

            # 如果用 Pipe / Queue，可以直接传 str
            # elif hasattr(self, "pipe"):
            #     self.pipe.send(payload)


            # 推送给异动联动（用管道/消息）
            send_code_via_pipe(payload, logger=logger)   # 假设你用 multiprocessing.Pipe
            # 或者 self.queue.put(stock_info)  # 如果是队列
            # 或者 send_code_to_other_window(stock_info) # 如果是 WM_COPYDATA
            logger.info(f"推送: {stock_info}")
            return True
        except Exception as e:
            logger.error(f"推送 stock_info 出错: {e} {row}")
            return False



    def on_signal_clicked(self, plot, points):
        """点击 K 线信号图标时触发，显示详细决策理由与指标"""
        # 终极健壮性保障：使用 try-except 规避所有 numpy 数组或 PySide 对象的布尔判定异常
        try:
            if points is None or len(points) == 0:
                return
        except Exception:
            # 如果发生 truth value 歧义或其他评估错误，跳过信号处理
            return

        point = points[0]
        data = point.data()
        if not data:
            return

        # 构造信息
        date = data.get("date", "Unknown")
        action = data.get("action", "Unknown")
        reason = data.get("reason", "No reason")
        price = data.get("price", 0.0)
        indicators_raw = data.get("indicators", "{}")

        # 处理指标 JSON
        try:
            if isinstance(indicators_raw, str):
                indicators = json.loads(indicators_raw)
            else:
                indicators = indicators_raw

            # 提取关键指标美化显示
            ind_text = ""
            for k, v in indicators.items():
                if isinstance(v, float):
                    ind_text += f"• {k}: {v:.2f}\n"
                else:
                    ind_text += f"• {k}: {v}\n"
        except:
            ind_text = str(indicators_raw)

        # msg = (
        #     f"<b>日期:</b> {date}<br>"
        #     f"<b>动作:</b> <span style='color:red;'>{action}</span><br>"
        #     f"<b>价格:</b> {price:.2f}<br>"
        #     f"<b>理由:</b> {reason}<br><br>"
        #     f"<b>📊 决策指标快照:</b><br>{ind_text.replace('\n', '<br>')}"
        # )
        ind_html = ind_text.replace('\n', '<br>')
        msg = (
            f"<div style='font-family: Microsoft YaHei; font-size: 10pt;'>"
            f"<p><b>📅 日期:</b> {date}</p>"
            f"<p><b>🎬 动作:</b> <span style='color:red; font-size: 12pt;'>{action}</span></p>"
            f"<p><b>💰 价格:</b> <span style='color:#00FF00;'>{price:.2f}</span></p>"
            f"<p><b>📝 理由:</b> {reason}</p>"
            f"<hr>"
            f"<p><b>📊 决策指标快照 (可滚动查看):</b><br>{ind_html}</p>"
            f"</div>"
        )

        dlg = ScrollableMsgBox(f"🔍 信号透视: {self.current_code} ({date})", msg, self)
        dlg.exec()

    def _on_kline_mouse_moved(self, pos):
        """
        K 线图鼠标移动事件处理器
        显示十字光标和 OHLC 数据浮窗
        只在鼠标悬停在有效K线柱上时显示
        """
        if not self.crosshair_enabled or self.day_df.empty:
            self._hide_crosshair()
            return
        
        self.mouse_last_pos = pos # ⭐ 记录鼠标位置 (1.1/1.2)
        self.mouse_last_scene = 'kline'
 
        # 检查鼠标是否在图表范围内
        if self.kline_plot.sceneBoundingRect().contains(pos):
            # 将场景坐标转换为数据坐标
            mouse_point = self.kline_plot.vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()

            # 将 X 坐标转换为 DataFrame 索引
            idx = int(round(x))
            
            # 记录当前索引，方便键盘操作接管
            if 0 <= idx < len(self.day_df):
                self.current_crosshair_idx = idx
                self._update_crosshair_ui(idx, y)
            else:
                self._hide_crosshair()
        else:
            self._hide_crosshair()

    def _on_tick_mouse_moved(self, pos):
        """分时图鼠标移动回调 (1.2)"""
        if not self.crosshair_enabled: return
        self.mouse_last_pos = pos
        self.mouse_last_scene = 'tick'
        
        if self.tick_plot.sceneBoundingRect().contains(pos):
            mouse_point = self.tick_plot.vb.mapSceneToView(pos)
            x, y = mouse_point.x(), mouse_point.y()
            idx = int(round(x))
            
            if 0 <= idx < len(self.tick_prices):
                self.current_tick_crosshair_idx = idx
                self._update_tick_crosshair_ui(idx, y)
            else:
                self._hide_tick_crosshair()
        else:
            self._hide_tick_crosshair()

    def is_mouse_in_tick_plot(self):
        """判断鼠标是否在分时图范围内"""
        if self.mouse_last_scene != 'tick': return False
        return self.tick_plot.sceneBoundingRect().contains(self.mouse_last_pos)

    def is_mouse_in_kline_plot(self):
        """判断鼠标是否在 K 线图或成交量图范围内"""
        if self.mouse_last_scene != 'kline': return False
        in_kline = self.kline_plot.sceneBoundingRect().contains(self.mouse_last_pos)
        in_vol = False
        if hasattr(self, 'volume_plot'):
            in_vol = self.volume_plot.sceneBoundingRect().contains(self.mouse_last_pos)
        return in_kline or in_vol

    def move_tick_crosshair(self, step):
        """左右键移动分时图十字光标"""
        if len(self.tick_prices) == 0: return
        if self.current_tick_crosshair_idx < 0:
            self.current_tick_crosshair_idx = len(self.tick_prices) - 1
        
        new_idx = self.current_tick_crosshair_idx + step
        if 0 <= new_idx < len(self.tick_prices):
            self.current_tick_crosshair_idx = new_idx
            self._update_tick_crosshair_ui(new_idx)
            self.tick_vline.setVisible(True)
            self.tick_hline.setVisible(True)
            self.tick_crosshair_label.setVisible(True)

    def _update_tick_crosshair_ui(self, idx, y_price=None):
        """更新分时图十字光标 UI (1.2)"""
        if len(self.tick_prices) == 0 or idx < 0 or idx >= len(self.tick_prices):
            self._hide_tick_crosshair()
            return
        
        price = self.tick_prices[idx]
        avg_price = self.tick_avg_prices[idx] if idx < len(self.tick_avg_prices) else 0
        if y_price is None: y_price = price
        
        self.tick_vline.setPos(idx)
        self.tick_hline.setPos(y_price)
        self.tick_vline.setVisible(True)
        self.tick_hline.setVisible(True)
        
        time_str = self.tick_times[idx] if idx < len(self.tick_times) else ""
        
        text = f"""
        <div style='color:#FFFFFF; font-family:monospace;'>
        P: <span style='color:#FF3333;'>{price:.2f}</span><br>
        A: <span style='color:#FFFF00;'>{avg_price:.2f}</span><br>
        T: {time_str}
        </div>
        """
        self.tick_crosshair_label.setHtml(text)
        self.tick_crosshair_label.setVisible(True)
        
        # 自动调整位置
        vb = self.tick_plot.vb
        view_range = vb.viewRange()
        y_range = view_range[1]
        label_y = y_price - (y_range[1] - y_range[0]) * 0.15
        if label_y < y_range[0]: label_y = y_price + (y_range[1] - y_range[0]) * 0.15
        self.tick_crosshair_label.setPos(idx, label_y)

    def _hide_tick_crosshair(self):
        self.tick_vline.setVisible(False)
        self.tick_hline.setVisible(False)
        self.tick_crosshair_label.setVisible(False)

    def _hide_crosshair(self):
        """隐藏十字光标及其标签"""
        self.vline.setVisible(False)
        self.hline.setVisible(False)
        self.crosshair_label.setVisible(False)

    def _update_crosshair_ui(self, idx, y_price=None):
        """
        核心 UI 更新逻辑：根据索引和可选的价格显示十字线和信息浮窗。
        """
        if self.day_df.empty or idx < 0 or idx >= len(self.day_df):
            self._hide_crosshair()
            return

        row = self.day_df.iloc[idx]
        
        # 如果没有传入价格（键盘操作），则默认使用收盘价
        if y_price is None:
            y_price = row.get('close', 0)

        # 更新十字线位置
        self.vline.setPos(idx)
        self.hline.setPos(y_price)
        self.vline.setVisible(True)
        self.hline.setVisible(True)

        # 准备显示文本
        date_str = row.name.strftime('%Y-%m-%d') if hasattr(row.name, 'strftime') else str(row.name)
        open_p = row.get('open', 0)
        high_p = row.get('high', 0)
        low_p = row.get('low', 0)
        close_p = row.get('close', 0)
        volume = row.get('amount', 0)
        volume_yi = volume / 100000000
        ratio = row.get('p_change', row.get('percent', 0.0))

        RED, WHITE = "#FF3333", "#FFFFFF"
        is_bullish = close_p > open_p
        open_color = RED if is_bullish else WHITE
        close_color = RED if (abs(close_p - high_p) < 0.01 or is_bullish) else WHITE
        low_color = RED if abs(open_p - low_p) < 0.01 else WHITE
        high_color = RED if is_bullish else WHITE

        text = f"""
        <table style='font-family:monospace; border-collapse:collapse;'>
        <tr><td style='color:{WHITE}'>O:</td><td style='text-align:right;color:{open_color}'>{open_p:.2f}</td><td style='padding-left:8px;color:{WHITE}'>C:</td><td style='text-align:right;color:{close_color}'>{close_p:.2f}</td></tr>
        <tr><td style='color:{WHITE}'>L:</td><td style='text-align:right;color:{low_color}'>{low_p:.2f}</td><td style='padding-left:8px;color:{WHITE}'>H:</td><td style='text-align:right;color:{high_color}'>{high_p:.2f}</td></tr>
        </table>
        <div style='color:#FFFFFF; font-family:monospace;'>V:{volume_yi:6.2f}亿 R:{ratio:6.2f}%</div>
        <div style='color:#FFFFFF; font-family:monospace;'>{date_str}</div>
        """
        
        # 1.3: 检查是否有信号透视信息
        signal = next((s for s in self.current_kline_signals if s.bar_index == idx), None)
        if signal:
            text += f"""
            <hr>
            <div style='color:#FFD700; font-family:monospace;'><b>动作:</b> {signal.signal_type.value}</div>
            <div style='color:#FFD700; font-family:monospace;'><b>理由:</b> {signal.reason}</div>
            """
            
        self.crosshair_label.setHtml(text)

        # 计算浮窗位置
        view_range = self.kline_plot.viewRange()
        x_range, y_range = view_range[0], view_range[1]

        label_x = idx
        label_y = y_price - (y_range[1] - y_range[0]) * 0.08

        if idx > (x_range[0] + x_range[1]) * 0.7:
            label_x = idx - (x_range[1] - x_range[0]) * 0.12
        elif idx < (x_range[0] + x_range[1]) * 0.3:
            label_x = idx + (x_range[1] - x_range[0]) * 0.02

        if y_price < (y_range[0] + y_range[1]) * 0.3:
            label_y = y_price + (y_range[1] - y_range[0]) * 0.08

        self.crosshair_label.setPos(label_x, label_y)
        self.crosshair_label.setVisible(True)

    def zoom_kline(self, in_=True):
        """通达信模式：上下键缩放"""
        vb = self.kline_plot.vb
        view_range = vb.viewRange()
        center_x = (view_range[0][1] + view_range[0][0]) / 2
        scale = 0.85 if in_ else 1.15  # 这里的比例可以根据手感微调
        vb.scaleBy(x=scale, center=(center_x, 0))

    def move_crosshair(self, step):
        """通达信模式：左右键移动十字光标并显示信息"""
        if self.day_df.empty:
            return
        
        if self.current_crosshair_idx < 0:
            self.current_crosshair_idx = len(self.day_df) - 1
            
        new_idx = self.current_crosshair_idx + step
        if 0 <= new_idx < len(self.day_df):
            self.current_crosshair_idx = new_idx
            self._update_crosshair_ui(new_idx)
            # 确保十字线在移动后可见（如果原先被隐藏了）
            self.vline.setVisible(True)
            self.hline.setVisible(True)
            self.crosshair_label.setVisible(True)
            
            # 自动调整视图范围，确保当前焦点可见
            self._ensure_idx_visible(new_idx)

    def _ensure_idx_visible(self, idx):
        """确保索引 idx 在 K 线图中可见"""
        vb = self.kline_plot.vb
        x_range = vb.viewRange()[0]
        margin = 5 # 边缘留白
        
        if idx < x_range[0] + margin:
            vb.setXRange(idx - margin, idx - margin + (x_range[1] - x_range[0]), padding=0)
        elif idx > x_range[1] - margin:
            vb.setXRange(idx + margin - (x_range[1] - x_range[0]), idx + margin, padding=0)

    def _on_initial_loaded(self, code, day_df, tick_df):
        # ⚡ 立即更新标题,清除 "Loading..." 状态
        if day_df is not None and not day_df.empty:
            self._update_plot_title(code, day_df, tick_df)

        # 检查是否是当前请求的代码
        if code != self.current_code:
            logger.debug(f"[Rapid Browse] Discarding outdated result for {code}, current is {self.current_code}")
            return

        # [FIX] 如果加载失败(empty)且我们已经有该股的数据，则不要覆盖(防止图表消失)
        if (day_df is None or day_df.empty) and not self.day_df.empty and self.current_day_df_code == code:
            logger.warning(f"[InitialLoad] RECEIVED EMPTY DATA for {code}, but keeping existing data to prevent clearing.")
            # 尝试使用缓存补全实时
            cached = self._tick_cache.get(code)
            if cached:
                self.on_realtime_update(code, cached['tick_df'], cached['today_bar'])
            return

        # ⚡ 过滤掉今天的数据，只保留过去的日 K
        today_str = pd.Timestamp.today().strftime('%Y-%m-%d')
        is_intraday = self.realtime and cct.get_work_time_duration()

        if is_intraday or self._debug_realtime:
            day_df = day_df[day_df.index < today_str]

        self.day_df = day_df.copy()
        datetime_index = pd.to_datetime(self.day_df.index)
        self.day_df.index = datetime_index.strftime('%Y-%m-%d')
        
        # ⭐ 记录当前加载成功的股票代码
        self.current_day_df_code = code
        # 1. 優先獲取可用於渲染的實時/模擬數據 (The "Ghost Bar" Source)

        effective_tick_df = None
        if tick_df is not None and not tick_df.empty:
            effective_tick_df = tick_df
        elif self._tick_cache.get(code):
            # 即使 DataLoader 沒傳，如果快取有，也應該拿出來用
            effective_tick_df = self._tick_cache.get(code).get("tick_df")

        # 2. 決定是否執行詳細渲染 (包含幽靈 K 線)
        should_render_detailed = (
            self.realtime or self.show_strategy_simulation
        ) and effective_tick_df is not None

        if should_render_detailed:
            logger.debug(
                f"[InitialLoad] Detailed rendering for {code} (Realtime:{self.realtime}, Sim:{self.show_strategy_simulation})"
            )
            today_bar = tick_to_daily_bar(effective_tick_df)

            # 注意：這裡直接調用渲染，確保模擬數據被帶入
            self._capture_view_state()
            with timed_ctx("render_charts_detailed", warn_ms=50):
                # 重點：即便 realtime 為 False，只要 show_strategy_simulation 為 True，也要帶入 tick_df
                self.render_charts(code, self.day_df, effective_tick_df)

            # 如果 realtime 真的有開，才去啟動定時刷新或同步狀態
            if self.realtime:
                self.on_realtime_update(code, effective_tick_df, today_bar)
        else:
            # 3. 兜底：純歷史數據渲染
            logger.debug(f"[InitialLoad] historical rendering only for {code}")
            self._capture_view_state()
            with timed_ctx("rrender_charts_detailed_historical", warn_ms=50):
                self.render_charts(code, self.day_df, None)

        '''
        # ⭐ 核心修复：既然 DataLoaderThread 已经带回了最新的 tick_df，直接利用它来生成首个幽灵 K 线
        # 这样无论是否在交易时间，只要打开图表，就能看到最新的今天行情。
        # [FIX] 只要开启了实时模式 OR 开启了策略模拟，都应该尝试使用 tick_df 进行详细渲染
        if (self.realtime or self.show_strategy_simulation) and tick_df is not None and not tick_df.empty:
            logger.debug(f"[InitialLoad] Using fresh tick_df from DataLoader for {code}, triggering update...")
            today_bar = tick_to_daily_bar(tick_df)
            # 立即触发同步 (不使用 QTimer 以防闪烁)
            self.on_realtime_update(code, tick_df, today_bar)
            # [FIX] on_realtime_update 已经调用了 render_charts，无需重复渲染
        elif self.realtime:
            # 如果 realtime 开启但 DataLoader 没拿到 tick_df，再尝试从缓存补全
            cached = self._tick_cache.get(code)
            if cached:
                logger.info(f"[InitialLoad] Using cached realtime data for {code}...")
                self.on_realtime_update(code, cached['tick_df'], cached['today_bar'])
                # [FIX] on_realtime_update 已经调用了 render_charts，无需重复渲染
            else:
                # realtime 开启但没有任何实时数据，兜底渲染
                self._capture_view_state()
                with timed_ctx("render_charts", warn_ms=100):
                    self.render_charts(code, self.day_df, None)
        else:
            # [FIX] realtime 关闭时，如果开启了策略模拟且有数据，尝试展示
            if self.show_strategy_simulation and tick_df is not None and not tick_df.empty:
                logger.debug(f"[InitialLoad] Realtime disabled but strategy simulation on. Rendering with tick_df for {code}")
                self._capture_view_state()
                with timed_ctx("render_charts", warn_ms=100):
                    self.render_charts(code, self.day_df, tick_df)
            else:
                # [FIX] realtime 关闭时，直接渲染历史数据（不使用缓存）
                logger.debug(f"[InitialLoad] Realtime disabled, rendering historical data only for {code}")
                self._capture_view_state()
                with timed_ctx("render_charts", warn_ms=100):
                    self.render_charts(code, self.day_df, None)
        '''
        # [FIX] 首次加载完成后，必须重置视野到最新的 K 线，否则可能仍停留在初始范围导致黑屏
        # self._reset_kline_view(self.day_df)

    def _need_ghost_bar(self,day_df):

        last_hist_date = str(day_df.index[-1]).split()[0]
        today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
        last_trade_date = cct.get_last_trade_date()

        now = pd.Timestamp.now()
        today = now.date()
        last_hist_dt = pd.to_datetime(day_df.index[-1]).date()
        is_trade_day = cct.get_trade_date_status()
        # 是否在交易时段
        t = now.time()
        in_session = (
            (t >= pd.to_datetime("09:30").time() and t <= pd.to_datetime("11:30").time()) or
            (t >= pd.to_datetime("13:00").time() and t <= pd.to_datetime("15:00").time())
        )
        # ===============================
        # ① 历史数据是否缺失最近交易日
        # ===============================
        missing_last_trade_bar = last_hist_date < last_trade_date
        if missing_last_trade_bar:
            logger.error(
                f"[KLINE DATA MISSING] Last hist date {last_hist_date} "
                f"< last trade date {last_trade_date} — 日线缺失最近交易日数据"
            )

        # ===============================
        # ② 是否需要画“临时K线”
        # ===============================
        # 两种情况要画：
        # A. 正常盘中今日K
        # B. 历史数据断档，需要补偿K

        need_ghost_bar = (
            (is_trade_day and in_session and last_hist_dt < today)  # 正常今日实时K
            or
            missing_last_trade_bar  # 数据缺失补偿K
        )

        # free_time_resample = cct.get_work_time() and self.resample not in ['d']
        return need_ghost_bar 


    def on_realtime_update(self, code, tick_df, today_bar):
        """实时更新（极限优化 + day_df 安全合并）"""
        import time

        self._tick_cache[code] = {
            'tick_df': tick_df,
            'today_bar': today_bar,
            'ts': time.time()
        }

        if today_bar is None or today_bar.empty:
            return

        # --- 股票匹配检查 ---
        if code != self.current_day_df_code:
            return
        if not self._debug_realtime and (not self.realtime or code != self.current_code):
            return

        # --- 索引统一 ---
        today_idx = pd.to_datetime(today_bar.index[0]).strftime('%Y-%m-%d')
        today_bar.index = [today_idx]

        # 数值列精度
        for col in ['open', 'high', 'low', 'close']:
            if col in today_bar.columns:
                today_bar[col] = today_bar[col].round(2)

        today_bar['vol'] = today_bar['volume'] if 'volume' in today_bar.columns else 0

        # --- 补全实时指标 ---
        if not self.df_all.empty:
            stock_row = None
            if code in self.df_all.index:
                stock_row = self.df_all.loc[code]
            elif 'code' in self.df_all.columns:
                filtered = self.df_all[self.df_all['code'] == code]
                if not filtered.empty:
                    stock_row = filtered.iloc[0]

            if stock_row is not None:
                for col in ['ma5d','ma10d','ma20d','ma60d','Rank','win','slope','macddif','macddea','macd']:
                    if col in self.df_all.columns and col not in today_bar.columns:
                        today_bar[col] = stock_row[col]

        # --- 合并到 day_df ---
        if today_idx in self.day_df.index:
            # 安全列对齐更新
            for col in self.day_df.columns:
                if col in today_bar.columns:
                    if col == 'open':
                        # open 已有有效值时不覆盖
                        if pd.notna(self.day_df.at[today_idx, col]) and self.day_df.at[today_idx, col] > 0:
                            continue
                    self.day_df.at[today_idx, col] = today_bar.at[today_idx, col]
        else:
            # 新增一行，列顺序和类型对齐
            today_bar_aligned = today_bar.reindex(columns=self.day_df.columns, fill_value=0)
            self.day_df.loc[today_idx] = today_bar_aligned.iloc[0]

        # --- 渲染图表（节流） ---
        now = time.time()
        last_render = self._last_kline_render_time.get(code, 0)
        if now - last_render >= self._render_throttle_interval:
            with timed_ctx("render_charts_realtime", warn_ms=100):
                self.render_charts(code, self.day_df, tick_df)
                self._last_kline_render_time[code] = time.time()

    def on_realtime_update_slow(self, code, tick_df, today_bar):
        """处理实时分时与幽灵 K 线更新"""
        # 0. 永远缓存最新数据
        self._tick_cache[code] = {
            'tick_df': tick_df,
            'today_bar': today_bar,
            'ts': time.time()
        }

        if today_bar is None or today_bar.empty:
            return

        # 1. 严格检查：如果当前加载的历史 K 线不是这只股票，则不合并，防止“串号”
        if code != self.current_day_df_code:
             return

        # ⭐ 允许休盘期间的“首笔”或强制更新。抓取是否继续由后台 worker 控制。
        if not self._debug_realtime and (not self.realtime or code != self.current_code):
            return

        # --- 2. 统一索引与格式化 ---
        today_bar = today_bar.copy()
        datetime_index = pd.to_datetime(today_bar.index)
        today_idx = datetime_index.strftime('%Y-%m-%d')[0]
        today_bar.index = [today_idx]
        today_bar['vol'] = today_bar['volume']  # 统一列名

        # 数值列精度处理
        num_cols = ['open', 'high', 'low', 'close']
        for col in num_cols:
            if col in today_bar.columns:
                today_bar[col] = round(pd.to_numeric(today_bar[col], errors='coerce'), 2)

        # --- 3. 补全实时指标 (Rank, win 等) ---
        if not self.df_all.empty:
            stock_row = pd.DataFrame()
            if code in self.df_all.index:
                stock_row = self.df_all.loc[[code]]
            elif 'code' in self.df_all.columns:
                stock_row = self.df_all[self.df_all['code'] == code]

            if not stock_row.empty:
                for col in ['ma5d', 'ma10d', 'ma20d', 'ma60d', 'Rank', 'win', 'slope', 'macddif', 'macddea', 'macd']:
                    if col in stock_row.columns:
                        today_bar[col] = stock_row[col].iloc[0]

        # --- 4. 合并到主数据集 ---
        # ⭐ [FIX] 前置去重：确保主数据集索引唯一，防止 .loc 赋值时因重复索引产生 slice/报错
        if self.day_df.index.duplicated().any():
            self.day_df = self.day_df[~self.day_df.index.duplicated(keep='last')]

        last_day = self.day_df.index[-1] if not self.day_df.empty else None

        if last_day == today_idx:
            # 覆盖当天最后一行
            today_row = today_bar.iloc[0]
            for col in self.day_df.columns:
                if col in today_row.index and pd.notna(today_row[col]):
                    # ⭐ [FIX] 如果是 open，且当前已有有效值，不轻易覆盖，防止被 segment 里的第一笔价格带歪
                    if col == 'open' and pd.notna(self.day_df.loc[today_idx, col]) and self.day_df.loc[today_idx, col] > 0:
                        continue
                    self.day_df.loc[today_idx, col] = today_row[col]
            logger.debug(f"[RT] Updated today's bar for {code}")
        else:
            # 新增一行 (第二天或者刚从历史加载完成)
            # 确保列顺序和类型对齐
            today_bar_aligned = today_bar.reindex(columns=self.day_df.columns)
            self.day_df = pd.concat([self.day_df, today_bar_aligned])
            
            # 再次去重加固（防止 concat 引入重复）
            if self.day_df.index.duplicated().any():
                self.day_df = self.day_df[~self.day_df.index.duplicated(keep='last')]
                
            logger.debug(f"[RT] Appended today's bar for {code}")

        # --- 5. 渲染图表 (节流优化) ---
        now = time.time()
        last_render = self._last_kline_render_time.get(code, 0)
        
        # ⚡ 如果距离上次渲染不足 1s，且不是由于切换股票引发的强制刷新，则跳过
        # 注意: 手动切换股票(render_charts)会更新 _last_kline_render_time，所以这里主要限制高频 tick 带来的重绘
        if now - last_render < self._render_throttle_interval:
            # logger.debug(f"[Throttle] Skipping render for {code} (Interval: {now-last_render:.2f}s)")
            return

        with timed_ctx("render_charts_realtime_slow", warn_ms=100):
            self.render_charts(code, self.day_df, tick_df)
            # 更新最后渲染时间
            self._last_kline_render_time[code] = time.time()




    def _init_theme_selector(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Theme:"))

        self.theme_cb = QComboBox()
        self.theme_cb.addItems(['light', 'dark'])
        self.theme_cb.setCurrentText(self.qt_theme)
        self.theme_cb.currentTextChanged.connect(self.on_theme_changed)

        self.toolbar.addWidget(self.theme_cb)


    def on_theme_changed(self, text):
        self.qt_theme = text
        self.apply_qt_theme()

    def _apply_pg_theme_to_plot(self, plot):
        """为单个 PlotItem 应用主题（坐标轴、标题、背景等）"""
        vb = plot.getViewBox()

        # 1. 确定图表亮度与背景色
        if getattr(self, 'custom_bg_chart', None):
            bg_color = self.custom_bg_chart
            chart_text_color = self._get_contrast_color(bg_color)
            is_dark = (chart_text_color == "#F0F0F0")
        else:
            is_dark = (self.qt_theme == 'dark')
            bg_color = '#111111' if is_dark else '#FFFFFF'

        # 2. 根据亮度配置辅助色
        if is_dark:
            axis_color = '#CCCCCC'
            border_color = '#555555'
            title_color = '#EEEEEE'
        else:
            axis_color = '#000000'
            border_color = '#BBBBBB'
            title_color = '#000000'

        # 应用背景与边框
        vb.setBackgroundColor(bg_color)
        vb.setBorder(pg.mkPen(border_color, width=1))

        # 3. 设置坐标轴与文字颜色
        for ax_name in ('left', 'bottom', 'right', 'top'):
            ax = plot.getAxis(ax_name)
            if ax is not None:
                ax.setPen(pg.mkPen(axis_color, width=1))
                ax.setTextPen(pg.mkPen(axis_color))

        if hasattr(plot, 'titleLabel'):
            plot.titleLabel.item.setDefaultTextColor(QColor(title_color))

        # 网格
        plot.showGrid(x=True, y=True, alpha=0.3)

    def _get_contrast_color(self, bg_hex):
        """根据背景色亮度返回黑色或白色的前景文字色"""
        if not bg_hex or bg_hex == 'transparent':
            return "#e6e6e6" if self.qt_theme == 'dark' else "#000000"
        try:
            bg_hex = bg_hex.lstrip('#')
            if len(bg_hex) == 3:
                bg_hex = ''.join([c*2 for c in bg_hex])
            r, g, b = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
            luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
            return "#000000" if luminance > 0.5 else "#F0F0F0"
        except:
            return "#000000"

    def _apply_widget_theme(self, widget):
        """Apply theme to GraphicsLayoutWidget (Enhanced)"""
        if self.custom_bg_chart:
            bg = self.custom_bg_chart
        else:
            bg = '#111111' if self.qt_theme == 'dark' else '#FFFFFF'
            
        widget.setBackground(bg)
        border = "#555555" if self.qt_theme == 'dark' else "#d0e5f5"
        widget.setStyleSheet(f"""
            QGraphicsView {{
                border: 1px solid {border};
                background-color: {bg};
            }}
        """)



    def apply_qt_theme(self):
        """Apply Qt theme / color scheme (Enhanced for dynamic backgrounds)"""
        current_sizes = self.main_splitter.sizes()
        
        # 1. 确定背景色与前景文字色
        if self.custom_bg_app:
            bg_main = self.custom_bg_app
            color_text = self._get_contrast_color(bg_main)
            is_dark = (color_text == "#F0F0F0")
        else:
            is_dark = (self.qt_theme == 'dark')
            # [THEME UPDATE] Match Hotlist/SignalLog Panel (Darker #1e1e1e)
            bg_main = "#1e1e1e" if is_dark else "#f2faff"
            color_text = "#e6e6e6" if is_dark else "#000000"

        # 2. 生成全局样式表
        if is_dark:
            # 深色基调 (Premium Dark)
            border_color = "#333333"
            # Gold Selection
            item_selected = "rgba(255, 215, 0, 80)"
            header_bg = "#2a2a2a"
            decision_bg = "#1a1a1a"
        else:
            # 浅色基调 (Trader Blue 风格)
            border_color = "#b3d7ff"
            item_selected = "#cce8ff"
            header_bg = "#eef7ff"
            decision_bg = "#e1f3ff"

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_main};
                color: {color_text};
            }}
            #DecisionPanel {{
                background-color: {decision_bg if not self.custom_bg_app else 'transparent'};
                border-top: 1px solid {border_color};
            }}
            QMenuBar {{
                background-color: {bg_main};
                color: {color_text};
                border-bottom: 1px solid {border_color};
            }}
            QMenuBar::item:selected {{
                background-color: {item_selected};
            }}
            QMenu {{
                background-color: {bg_main if is_dark else '#ffffff'};
                color: {color_text};
                border: 1px solid {border_color};
            }}
            QMenu::item:selected {{
                background-color: #0078d4;
                color: #ffffff;
            }}
            QTableWidget, QTreeWidget, QHeaderView::section {{
                background-color: {bg_main if not is_dark else '#1e1e1e'};
                color: {color_text};
                gridline-color: {border_color};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                border: 1px solid {border_color};
                padding: 4px;
            }}
            /* Unified Gold Selection */
            QTableWidget::item:selected, QTreeWidget::item:selected {{
                background-color: {item_selected};
                color: #FFFFFF;
                font-weight: bold;
            }}
            QComboBox, QPushButton {{
                background-color: {decision_bg if not self.custom_bg_app else 'rgba(255,255,255,50)'};
                border: 1px solid {border_color};
                border-radius: 4px;
                padding: 4px;
                color: {color_text};
            }}
            QComboBox::drop-down, QPushButton:hover {{
                background-color: {item_selected};
            }}
            QSplitter::handle {{
                background-color: {border_color};
            }}
        """)

        # 2.1 更新标签颜色（处理“看不清”的问题）
        if hasattr(self, 'decision_label'):
            label_color = "#00FF00" if is_dark else "#006400" # 深绿或翠绿
            self.decision_label.setStyleSheet(f"color: {label_color}; font-weight: bold; background: transparent;")
        if hasattr(self, 'supervision_label'):
            super_color = "#FFD700" if is_dark else "#B8860B" # 金色或暗金
            self.supervision_label.setStyleSheet(f"color: {super_color}; background: transparent;")

        # 3. 确定图表亮度（独立于界面亮度，确保坐标轴可见）
        if self.custom_bg_chart:
            # 根据图表背色计算图表文字色
            chart_text_color = self._get_contrast_color(self.custom_bg_chart)
            is_chart_dark = (chart_text_color == "#F0F0F0")
        else:
            is_chart_dark = is_dark

        # 4. 应用图表全局配置
        pg.setConfigOption('background', self.custom_bg_chart if self.custom_bg_chart else ('k' if is_dark else 'w'))
        pg.setConfigOption('foreground', 'w' if is_chart_dark else 'k')

        self._apply_widget_theme(self.kline_widget)
        self._apply_widget_theme(self.tick_widget)

        self._apply_pg_theme_to_plot(self.kline_plot)
        self._apply_pg_theme_to_plot(self.tick_plot)
        if hasattr(self, 'volume_plot'):
            self._apply_pg_theme_to_plot(self.volume_plot)

        # 4. 刷新渲染
        if self.current_code:
            self.render_charts(self.current_code, self.day_df, getattr(self, 'tick_df', pd.DataFrame()))

        # 5. 恢复分割器手柄样式与尺寸
        handle_color = border_color
        self.main_splitter.setStyleSheet(f"QSplitter::handle {{ background-color: {handle_color}; width: 4px; }}")
        
        if any(current_sizes):
            logger.debug(f'load_layout_preset current_sizes: {current_sizes}')
            self.main_splitter.setSizes(current_sizes)

        # [THEME PROPAGATION] Sync theme with child panels
        if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
            self.hotlist_panel.apply_theme(is_dark)
        
        if hasattr(self, 'signal_log_panel') and self.signal_log_panel:
            self.signal_log_panel.apply_theme(is_dark)

        # [NEW] Init Hotspot Menu
        self._init_hotspot_menu()

    def _init_hotspot_menu(self):
        """初始化热点跟踪与信号日志菜单"""
        if hasattr(self, '_hotspot_action'):
            return

        menubar = self.menuBar()
        # 1. 热点跟踪
        self._hotspot_action = QAction("🔥 热点跟踪(Alt+H)", self)
        self._hotspot_action.setShortcut("") 
        self._hotspot_action.triggered.connect(self._toggle_hotlist_panel)
        menubar.addAction(self._hotspot_action)

        # 2. 信号日志 - 新增
        self._signal_log_action = QAction("📋 信号日志(Alt+L)", self)
        self._signal_log_action.setShortcut("")
        self._signal_log_action.triggered.connect(self._toggle_signal_log)
        menubar.addAction(self._signal_log_action)
        
        # 3. 语音播报 (移至 MenuBar)
        # 补救措施：确保 Pending 状态被应用
        if hasattr(self, '_pending_hotlist_voice_paused') and hasattr(self, 'hotlist_panel'):
             self.hotlist_panel._voice_paused = self._pending_hotlist_voice_paused
        
        # 默认根据当前状态开启
        is_paused = False
        if hasattr(self, 'hotlist_panel'):
             is_paused = self.hotlist_panel._voice_paused
             
        text = "🔇 热点播报: 关(Alt+V)" if is_paused else "🔊 热点播报: 开(Alt+V)"
        self.voice_action = QAction(text, self)
        self.voice_action.setShortcut("") 
        self.voice_action.setStatusTip("点击开启/关闭热点信号语音播报")
        self.voice_action.triggered.connect(self._toggle_hotlist_voice)
        menubar.addAction(self.voice_action)

    def _apply_widget_theme(self, widget: pg.GraphicsLayoutWidget):
        """应用主题到 GraphicsLayoutWidget"""
        if not widget: return
        
        # 0. 决定背景色
        if self.custom_bg_chart:
            # 优先使用自定义背色
            bg_color = self.custom_bg_chart
        else:
            # 否则根据整体主题暗/亮决定
            is_dark = (self.qt_theme == 'dark') 
            bg_color = 'k' if is_dark else 'w'
        
        # 1. 设置 Widget 背景
        widget.setBackground(bg_color)
        
        # 2. 遍历所有 PlotItem 应用主题
        # 注意: ci.items 是个列表，包含了布局里的所有 Item
        is_chart_dark = True
        
        # 如果是自定义背景，计算反差色
        if self.custom_bg_chart:
             contrast = self._get_contrast_color(self.custom_bg_chart)
             is_chart_dark = (contrast == "#F0F0F0")
        else:
             is_chart_dark = (self.qt_theme == 'dark')

        fg_color = 'w' if is_chart_dark else 'k'
        axis_pen = pg.mkPen(color=fg_color, width=1)
        
        # 显式更新已知图表
        if hasattr(self, 'kline_plot'):
             self._apply_pg_theme_to_plot(self.kline_plot)
        if hasattr(self, 'tick_plot'):
             self._apply_pg_theme_to_plot(self.tick_plot)
        if hasattr(self, 'volume_plot'):
             self._apply_pg_theme_to_plot(self.volume_plot)

    def _init_layout_menu(self):
        """初始化布局预设菜单 (优化版：分层明确，防误触)"""
        if not hasattr(self, '_layout_menu'):
            menubar = self.menuBar()
            self._layout_menu = menubar.addMenu("布局(Layout)")
        
        self._layout_menu.clear() # 每次刷新前先清空旧项

        # 1. 加载预设 (放在最外层，方便快速切换)
        for i in range(1, 4):
            # 尝试获取描述信息
            desc = ""
            if hasattr(self, 'layout_presets'):
                preset = self.layout_presets.get(str(i))
                if preset:
                    # 兼容新旧格式: 新格式是 dict，旧格式是 list
                    if isinstance(preset, dict):
                        sizes = preset.get('sizes', [])
                    else:
                        sizes = preset  # 旧格式直接是 list
                    if sizes and len(sizes) >= 3:
                        desc = f" ({sizes[0]}:{sizes[1]}:{sizes[2]})"
            
            action = QAction(f"加载 布局预设 {i}{desc}", self)
            action.triggered.connect(lambda checked, idx=i: self.load_layout_preset(idx))
            self._layout_menu.addAction(action)
            
        self._layout_menu.addSeparator()
            
        # 2. 保存预设 (放入子菜单，并明确提示“保存此布局”)
        save_menu = self._layout_menu.addMenu("⚙️ 保存当前布局为...")
        for i in range(1, 4):
            action = QAction(f"保存为 预设 {i}", self)
            action.triggered.connect(lambda checked, idx=i: self.save_layout_preset(idx))
            save_menu.addAction(action)

    def _init_theme_menu(self):
        """初始化自定义背景颜色菜单"""
        menubar = self.menuBar()
        theme_menu = menubar.addMenu("主题(Theme)")
        
        # 常见颜色选项
        colors = [
            ("默认方案", None),
            ("纯白 (Classic)", "#FFFFFF"),
            ("淡蓝 (Trader Blue)", "#F2FAFF"),
            ("浅灰 (Soft Gray)", "#F0F0F0"),
            ("中灰 (Medium)", "#DCDCDC"),
            ("深灰 (Deep Gray)", "#333333"),
            ("纯黑 (Dark)", "#000000"),
        ]
        
        # 1. 界面背景
        app_bg_menu = theme_menu.addMenu("🖼️ 界面背景颜色")
        for name, code in colors:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=code: self._update_app_bg(c))
            app_bg_menu.addAction(action)
            
        # 2. 图表背景
        chart_bg_menu = theme_menu.addMenu("📈 K线/分时背景颜色")
        for name, code in colors:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=code: self._update_chart_bg(c))
            chart_bg_menu.addAction(action)

    def _init_voice_toolbar(self):
        """语音控制已集成到 MenuBar (_init_hotspot_menu)，此处保留空方法以兼容旧调用"""
        pass

    def _toggle_hotlist_voice(self):
        """切换主语音状态 (Stop/Mute) - 原有功能不变，停止播放并清空队列"""
        if not hasattr(self, 'voice_thread'):
            return

        # 获取当前静音状态 (这里假设我们用一个本地变量或者检查 voice_thread 状态)
        # 为了保持 UI 同步，我们可以检查 voice_action 的文本
        is_muted = "开" in self.voice_action.text() # 如果当前是"开"，说明点击后要关
        
        if is_muted:
            # 🔇 关闭：停止当前并清空队列
            self.voice_thread.abort()
            # self.voice_action.setText("🔇 播报: 关")
            self.voice_action.setText("🔇 热点播报: 关(Alt+V)")
            logger.info("🔇 语音播报已关闭 (队列已清空)")
        else:
            # 🔊 开启
            # self.voice_action.setText("🔊 播报: 开")
            self.voice_action.setText("🔊 热点播报: 开(Alt+V)")
            # 确保不处于暂停状态
            self.voice_thread.resume()
            logger.info("🔊 语音播报已开启")
            
        # ⭐ [IPC] 反向同步给主进程
        # self._send_voice_state_to_main_app(enabled=is_muted)

    def _send_voice_state_to_main_app(self, enabled=True):
        """通过命名管道同步语音状态给主程序 (实现进程间互斥)"""
        import win32pipe, win32file, pywintypes
        import json
        
        try:
            # 这里的 PIPE_NAME_TK 是在 data_utils 中定义的，并被 instock_MonitorTK 监听
            pipe_name = r'\\.\pipe\instock_tk_pipe'
            handle = win32file.CreateFile(
                pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None
            )
            
            payload = json.dumps({
                "cmd": "SET_VOICE_STATE",
                "enabled": enabled,
                "source": "Visualizer"
            })
            
            win32file.WriteFile(handle, payload.encode('utf-8'))
            win32file.CloseHandle(handle)
            logger.info(f"Sent SET_VOICE_STATE(enabled={enabled}) to Main App")
        except pywintypes.error as e:
            # 管道不存在或没被监听很正常，不需要报错
            logger.debug(f"Main App pipe not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to sync voice state to main app: {e}")

    def _update_app_bg(self, color):
        self.custom_bg_app = color
        self.apply_qt_theme()
        # self._save_visualizer_config()
        logger.info(f"App background updated to: {color}")
        
    def _update_chart_bg(self, color):
        self.custom_bg_chart = color
        self.apply_qt_theme()
        # self._save_visualizer_config()
        logger.info(f"Chart background updated to: {color}")

    def save_layout_preset(self, index):
        """保存当前布局到指定预设 (1-3) - 包含背景色设置"""
        try:
            from PyQt6.QtWidgets import QMessageBox
            if not hasattr(self, 'layout_presets'):
                self.layout_presets = {}

            # sizes = self.main_splitter.sizes()
            # is_visible = sizes[2] > 0
            # if is_visible:
            #     self.toggle_filter_panel(False)


            # 二次确认
            reply = QMessageBox.question(
                self, '确认保存', 
                f"确定要将当前布局（包含界面颜色、K线颜色）覆盖到 预设 {index} 吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                sizes = self.main_splitter.sizes()
                # 保存尺寸与主题色
                # 'sizes': [sizes[0], sizes[1]], # 只记录 Table + Chart
                self.layout_presets[str(index)] = {
                    'sizes': sizes,
                    'bg_app': getattr(self, 'custom_bg_app', None),
                    'bg_chart': getattr(self, 'custom_bg_chart', None),
                    'theme': getattr(self, 'qt_theme', 'dark')
                }
                # 刷新菜单显示新的尺寸描述
                self._init_layout_menu()
                # if is_visible:
                #     self.toggle_filter_panel(True)
                
                self._save_visualizer_config()
                logger.info(f"Layout preset {index} saved (with theme): {self.layout_presets[str(index)]}")
                QMessageBox.information(self, "布局保存", f"布局预设 {index}（含环境色）已保存成功。")
        except Exception as e:
            logger.error(f"Failed to save layout preset {index}: {e}")

    def load_stock_list(self):
        """Load stocks from df_all if available, otherwise from signal history"""
        if not self.df_all.empty:
            self.update_stock_table(self.df_all)
        elif not self.df_cache.empty:
            self.update_stock_table(self.df_cache)
        else:
            # Fallback to signal history
            df = self.logger.get_signal_history_df()
            if not df.empty and 'code' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values(by='date', ascending=False)
                unique_stocks = df[['code', 'name']].drop_duplicates()
                # Create a minimal df_all structure
                fallback_df = unique_stocks.copy()
                for col in self.headers:
                    if col not in ['code' , 'name']:
                        fallback_df[col] = 0
                self.update_stock_table(fallback_df)

    def update_stock_table(self, df, force_full=False, changed_codes=None):
        """Update table with df_all data (增量更新优化版 - 参考TK性能优化)
        
        Args:
            df: DataFrame 数据
            force_full: 是否强制全量刷新 (默认 False)
            changed_codes: 仅更新这些代码的行 (优化点)
        """
        start_time = time.time()

        
        if df is None or df.empty:
            self.stock_table.setRowCount(0)
            self._table_item_map = {}  # 重置映射
            return
        

        # ⚡ 性能优化: 预先关闭信号和排序
        self.stock_table.blockSignals(True)
        self.stock_table.setUpdatesEnabled(False) 
        self.stock_table.setSortingEnabled(False) # 关键性能点
        
        n_rows = len(df)
        
        # ⚡ [CRITICAL] 大数据量（>500行）使用异步分块更新，避免UI卡死
        # [FINAL DECISION] 异步分块已被证实为卡死元凶，永久禁用，使用稳健的同步更新
        if n_rows > 999999: 
            logger.info(f"[TableUpdate] Large dataset ({n_rows} rows), using async chunked update")
            self._update_table_in_chunks_full_async(df, chunk_size=100, force_full=force_full)
            return
        
        # ⚡ 初始化映射表（首次或重置后）
        if not hasattr(self, '_table_item_map'):
            self._table_item_map = {}  # code -> row_idx 映射
        if not hasattr(self, '_table_update_count'):
            self._table_update_count = 0
            
        self._table_update_count += 1
        
        # ⚡ 每50次增量更新后强制全量刷新，防止累积误差
        # 或者外部明确要求强制全量
        if force_full or self._table_update_count >= 50 or not self._table_item_map:
            force_full = True
            self._table_update_count = 0
            self._table_item_map = {}
        
        # ⚡ 性能优化: 禁用信号和排序
        self.stock_table.blockSignals(True)
        # 保存状态：排序、选择、滚动位置
        saved_v_scroll = self.stock_table.verticalScrollBar().value()
        saved_h_scroll = self.stock_table.horizontalScrollBar().value()
        header = self.stock_table.horizontalHeader()
        saved_sort_col = header.sortIndicatorSection()
        saved_sort_order = header.sortIndicatorOrder()

        self.stock_table.setSortingEnabled(False)
        self.stock_table.setUpdatesEnabled(False)
        self.stock_table.viewport().setUpdatesEnabled(False) # 额外锁定视口
        
        update_type = "FULL" if (force_full or not self._table_item_map) else "INCR"
        
        try:
            n_rows = len(df)
            
            # ⚡ 预处理列名映射（一次性）
            cols_in_df = {c.lower(): c for c in df.columns}
            optional_cols = [col for col in self.headers if col.lower() not in ['code', 'name']]
            optional_cols_real = [(col, cols_in_df.get(col.lower())) for col in optional_cols]
            
            # ⚡ 批量获取数据为 numpy 数组
            has_code_col = 'code' in cols_in_df
            has_name_col = 'name' in cols_in_df
            
            codes = df[cols_in_df['code']].values if has_code_col else df.index.values
            names = df[cols_in_df['name']].values if has_name_col else [''] * n_rows
            
            # ⚡ 预获取可选列数据
            optional_data = {}
            for col_name, real_col in optional_cols_real:
                if real_col:
                    optional_data[col_name] = df[real_col].values
                else:
                    optional_data[col_name] = [0] * n_rows
            
            # ⚡ 计算新旧代码差异
            new_codes = set(str(c) for c in codes)
            old_codes = set(self._table_item_map.keys())
            
            codes_to_delete = old_codes - new_codes
            codes_to_add = new_codes - old_codes
            codes_to_update = old_codes & new_codes
            
            # ⚡ 如果有大量行需要删除/添加，使用全量刷新
            if len(codes_to_delete) > 100 or len(codes_to_add) > 100:
                force_full = True
                self._table_item_map = {}
            
            no_edit_flag = Qt.ItemFlag.ItemIsEditable
            
            if force_full or not self._table_item_map:
                # === 全量刷新 ===
                # ⚡ [UI FIX] 保存当前选中/关注的股票
                target_code = getattr(self, 'current_code', None)
                target_row_idx = -1

                logger.debug("[TableUpdate] Clearing table...")
                self.stock_table.setRowCount(0) # 显式清空
                # ⚡ [UI FIX] 减少处理事件频率，仅在大规模清空时处理一次
                if n_rows > 1000:
                    QtGui.QGuiApplication.processEvents()
                
                self.stock_table.setRowCount(n_rows)
                self._table_item_map = {}
                
                for row_idx in range(n_rows):
                    # if row_idx % 1000 == 0:
                    #     logger.debug(f"[TableUpdate] Filling row {row_idx}...")
                    try:
                        stock_code = str(codes[row_idx])
                        if stock_code == target_code:
                            target_row_idx = row_idx
                        stock_name = str(names[row_idx]) if pd.notnull(names[row_idx]) else ''
                        
                        self._set_table_row(row_idx, stock_code, stock_name, 
                                           optional_cols_real, optional_data, no_edit_flag)
                        self._table_item_map[stock_code] = row_idx
                    except Exception as e:
                        logger.warning(f"[TableUpdate] Row error at {row_idx}: {e}")
                        continue
            else:
                # === 增量更新 ===
                # 1. 删除不存在的行 (从后往前删除避免索引错乱)
                if codes_to_delete:
                    rows_to_delete = sorted([self._table_item_map[c] for c in codes_to_delete], reverse=True)
                    for row_idx in rows_to_delete:
                        self.stock_table.removeRow(row_idx)
                    # 更新映射
                    for code in codes_to_delete:
                        if code in self._table_item_map:
                            del self._table_item_map[code]
                    # 重新计算剩余行的索引
                    self._rebuild_item_map_from_table()
                
                # 2. 更新或新增行
                for row_idx in range(n_rows):
                    try:
                        stock_code = str(codes[row_idx])
                        
                        # ⭐ [OPTIMIZATION] 如果提供了变更列表，且该代码未变，则跳过 UI 更新
                        if changed_codes is not None and stock_code not in changed_codes:
                            continue

                        if stock_code in self._table_item_map:
                            # 更新现有行
                            old_row_idx = self._table_item_map[stock_code]
                            stock_name = str(names[row_idx]) if pd.notnull(names[row_idx]) else ''
                            self._update_table_row(old_row_idx, stock_code, stock_name,
                                                  optional_cols_real, optional_data, row_idx)
                        else:
                            # 新增行
                            new_row_idx = self.stock_table.rowCount()
                            self.stock_table.insertRow(new_row_idx)
                            stock_name = str(names[row_idx]) if pd.notnull(names[row_idx]) else ''
                            self._set_table_row(new_row_idx, stock_code, stock_name,
                                               optional_cols_real, optional_data, no_edit_flag, row_idx)
                            self._table_item_map[stock_code] = new_row_idx
                    except Exception as e:
                        logger.warning(f"[TableUpdate] Incr row error at {row_idx}: {e}")
                        continue
        
        finally:
            # ⚡ 恢复排序状态
            self.stock_table.setSortingEnabled(True)
            self.stock_table.horizontalHeader().setSortIndicator(saved_sort_col, saved_sort_order)
            
            # ⚡ [OPTIMIZATION] 仅在全量刷新或行数变化时重建索引
            if update_type == "FULL" or len(codes_to_delete) > 0 or len(codes_to_add) > 0:
                self._rebuild_item_map_from_table()
            
            # ⚡ 恢复选中项 (在排序和映射重建之后)
            if self.current_code:
                self.stock_table.blockSignals(True)
                code_str = str(self.current_code)
                if code_str in self._table_item_map:
                    row = self._table_item_map[code_str]
                    # logger.debug(f"[TableUpdate] Restoring selection to row {row} for {code_str}")
                    self.stock_table.setCurrentCell(row, 0)
                self.stock_table.blockSignals(False)

            # ⚡ 恢复滚动位置
            self.stock_table.verticalScrollBar().setValue(saved_v_scroll)
            self.stock_table.horizontalScrollBar().setValue(saved_h_scroll)
            
            # ⚡ 恢复信号和更新
            self.stock_table.setUpdatesEnabled(True)
            self.stock_table.viewport().setUpdatesEnabled(True)
            self.stock_table.blockSignals(False)
            
            # ⭐ [BUGFIX] 限制过宽列，防止挤压 K 线图
            if not df.empty:
                try:
                    # 确保 i 有效，防止 headers 长度与表格列数不匹配
                    header_count = len(self.headers)
                    table_col_count = self.stock_table.columnCount()
                    for i in range(min(header_count, table_col_count)):
                        h = self.headers[i]
                        if h in ('last_reason', 'shadow_info'):
                            if self.stock_table.columnWidth(i) > 200:
                                self.stock_table.setColumnWidth(i, 200)
                except Exception:
                    pass

            # ⚡ 性能日志
            duration = time.time() - start_time
            n_rows = len(df) if not df.empty else 0
            if duration > 0.5:
                logger.warning(f"[TableUpdate] {update_type}: {n_rows}行, 耗时{duration:.3f}s ⚠️")
            else:
                logger.info(f"[TableUpdate] {update_type}: {n_rows}行, 耗时{duration:.3f}s")

            # ⚡ 全量更新完成后，如果有激活的板块可见性过滤，重新应用 setRowHidden
            active_codes = getattr(self, '_cat_filter_visible_codes', None)
            if active_codes and hasattr(self, '_table_item_map') and self._table_item_map:
                self.stock_table.setUpdatesEnabled(False)
                for code, row_idx in self._table_item_map.items():
                    self.stock_table.setRowHidden(row_idx, code not in active_codes)
                self.stock_table.setUpdatesEnabled(True)

    def _limit_table_column_widths(self):
        """限制表格列宽，防止过宽列挤压其他内容"""
        try:
            for i, h in enumerate(self.headers):
                if h in ('last_reason', 'shadow_info'):
                    if self.stock_table.columnWidth(i) > 200:
                        self.stock_table.setColumnWidth(i, 200)
        except Exception:
            pass

    def _do_sync_update_logic(self, df, n_rows, codes, names, optional_cols_real, optional_data, no_edit_flag):
        """同步更新的核心逻辑块 (用于小数据量或全量刷新)"""
        new_codes = set(str(c) for c in codes)
        old_codes = set(self._table_item_map.keys())
        codes_to_delete = old_codes - new_codes
        
        # 1. 删除不存在的行 (从后往前删除避免索引错乱)
        if codes_to_delete:
            rows_to_delete = sorted([self._table_item_map[c] for c in codes_to_delete if c in self._table_item_map], reverse=True)
            for ridx in rows_to_delete: self.stock_table.removeRow(ridx)
            # 更新映射
            for c in codes_to_delete: self._table_item_map.pop(c, None)
            self._rebuild_item_map_from_table()
        
        # 2. 更新或新增
        for row_idx in range(n_rows):
            stock_code = str(codes[row_idx])
            stock_name = str(names[row_idx]) if pd.notnull(names[row_idx]) else ''
            if stock_code in self._table_item_map:
                # 更新现有行
                self._update_table_row(self._table_item_map[stock_code], stock_code, stock_name,
                                      optional_cols_real, optional_data, row_idx)
            else:
                # 新增行
                new_idx = self.stock_table.rowCount()
                self.stock_table.insertRow(new_idx)
                self._set_table_row(new_idx, stock_code, stock_name,
                                   optional_cols_real, optional_data, no_edit_flag, row_idx)
                self._table_item_map[stock_code] = new_idx

    def _update_table_in_chunks_full_async(self, df, chunk_size, force_full):
        """完全异步地更新表格：数据准备 + 分块渲染均在计时器中分步触发
        
        [OPTIMIZATION] 修复全量数据卡死问题：
        - 将数据准备阶段也异步化，在 QTimer 中分步执行
        - 避免大数据量时阻塞主线程
        """
        import time
        n_rows = len(df)
        
        # ⚡ [CRITICAL FIX] 立即返回控制权给主线程，
        # 将所有重活（包括数据准备）都推入 QTimer 链
        logger.info(f"[TableUpdate] Scheduling async update for {n_rows} rows...")
        
        def _do_async_update():
            """真正的异步更新逻辑，在下一个事件循环中执行"""
            prep_start = time.time()
            
            try:
                # 1. 数据准备 (现在在异步上下文中执行)
                cols_in_df = {c.lower(): c for c in df.columns}
                optional_cols = [col for col in self.headers if col.lower() not in ['code', 'name']]
                optional_cols_real = [(col, cols_in_df.get(col.lower())) for col in optional_cols]
                codes = df[cols_in_df['code']].values if 'code' in cols_in_df else df.index.values
                names = df[cols_in_df['name']].values if 'name' in cols_in_df else [''] * n_rows
                optional_data = {}
                for col_name, real_col in optional_cols_real:
                    optional_data[col_name] = df[real_col].values if real_col else [0] * n_rows
                
                no_edit_flag = Qt.ItemFlag.ItemIsEditable
                nonlocal force_full
                
                # 2. 结构调整 (全量包直接 setRowCount，杜绝 removeRow 死循环)
                self.stock_table.blockSignals(True)
                self.stock_table.setSortingEnabled(False)
                
                if force_full or not self._table_item_map:
                    self.stock_table.setRowCount(n_rows)
                    self._table_item_map = {}
                    force_full = True
                else:
                    # 增量包下的删除检测
                    new_codes = set(str(c) for c in codes)
                    old_codes = set(self._table_item_map.keys())
                    codes_to_delete = old_codes - new_codes
                    if len(codes_to_delete) > 100:
                        self.stock_table.setRowCount(n_rows)
                        self._table_item_map = {}
                        force_full = True # 降级为全量，更快
                    elif codes_to_delete:
                        rows_to_delete = sorted([self._table_item_map[c] for c in codes_to_delete if c in self._table_item_map], reverse=True)
                        for ridx in rows_to_delete: self.stock_table.removeRow(ridx)
                        for c in codes_to_delete: self._table_item_map.pop(c, None)
                        self._rebuild_item_map_from_table()

                prep_duration = time.time() - prep_start
                logger.info(f"[TableUpdate] Prep done (is_full={force_full}) in {prep_duration:.3f}s, starting async chunking...")

                # 3. 分块渲染器
                # ⚡ [OPTIMIZATION] 全程禁用 UI 更新，最后统一恢复，避免中间重绘卡死
                self.stock_table.setUpdatesEnabled(False)
                self.stock_table.setSortingEnabled(False)
                
                def process_next_chunk(start_idx):
                    # 辅助：恢复语音
                    def _ensure_voice_resumed(tag):
                        if hasattr(self, 'voice_thread') and self.voice_thread:
                            if self.voice_thread.pause_for_sync:
                                self.voice_thread.pause_for_sync = False
                                logger.debug(f"[TableUpdate] Voice thread resumed ({tag})")
                    
                    try:
                        logger.debug(f"[TableUpdate] Chunk START: idx={start_idx}/{n_rows}")
                        
                        if not self.isVisible(): 
                            # 窗口不可见时，恢复表格状态并退出
                            logger.debug("[TableUpdate] Window not visible, aborting chunk update")
                            self.stock_table.setUpdatesEnabled(True)
                            self.stock_table.setSortingEnabled(True)
                            if block_signals_state is False: # 只有之前没阻塞才恢复
                                self.stock_table.blockSignals(False)
                            _ensure_voice_resumed("WindowHidden")
                            return

                        if start_idx >= n_rows:
                            # 最终收尾
                            self.stock_table.setUpdatesEnabled(True) # ⚡ [CRITICAL] 恢复 UI 更新
                            self.stock_table.setSortingEnabled(True)
                            if block_signals_state is False:
                                self.stock_table.blockSignals(False)
                                
                            self._limit_table_column_widths()
                            logger.info(f"[TableUpdate] DEFERRED update finished: {n_rows} rows")
                            _ensure_voice_resumed("Finished")
                            return

                        end_idx = min(start_idx + chunk_size, n_rows)
                        logger.debug(f"[TableUpdate] Processing rows {start_idx}-{end_idx}")
                        
                        # 批量写入，不再中间开关 updatesEnabled
                        for i in range(start_idx, end_idx):
                            try:
                                s_code = str(codes[i])
                                s_name = str(names[i]) if pd.notnull(names[i]) else ''
                                
                                if force_full or s_code not in self._table_item_map:
                                    if force_full:
                                        self._set_table_row(i, s_code, s_name, optional_cols_real, optional_data, no_edit_flag)
                                        self._table_item_map[s_code] = i
                                    else:
                                        new_r = self.stock_table.rowCount()
                                        self.stock_table.insertRow(new_r)
                                        self._set_table_row(new_r, s_code, s_name, optional_cols_real, optional_data, no_edit_flag, i)
                                        self._table_item_map[s_code] = new_r
                                else:
                                    r_idx = self._table_item_map[s_code]
                                    self._update_table_row(r_idx, s_code, s_name, optional_cols_real, optional_data, i)

                            except Exception as row_e:
                                logger.warning(f"[TableUpdate] Row error at {i} ({s_code}): {row_e}")
                                continue

                        logger.debug(f"[TableUpdate] Chunk DONE: idx={start_idx}-{end_idx}, scheduling next...")
                        
                        # ⚡ 核心呼吸：保持较大的时间片，与 UI 循环交互
                        QtCore.QTimer.singleShot(10, lambda: process_next_chunk(end_idx))
                        
                    except Exception as e:
                        import traceback
                        logger.error(f"[TableUpdate] Chunk processing error at row {start_idx}: {e}")
                        logger.error(f"[TableUpdate] Traceback: {traceback.format_exc()}")
                        # 恢复表格状态
                        try:
                            self.stock_table.setUpdatesEnabled(True)
                            self.stock_table.setSortingEnabled(True)
                            self.stock_table.blockSignals(False)
                        except:
                            pass
                        _ensure_voice_resumed("Error")

                # 启动第一块处理
                block_signals_state = self.stock_table.signalsBlocked() # 记录原始状态
                if not block_signals_state:
                    self.stock_table.blockSignals(True)
                    
                logger.debug("[TableUpdate] Starting first chunk...")
                process_next_chunk(0)
                
            except Exception as e:
                logger.error(f"[TableUpdate] Async update error: {e}")
                # 确保恢复表格状态
                try:
                    self.stock_table.setSortingEnabled(True)
                    self.stock_table.blockSignals(False)
                except:
                    pass
        
        # ⚡ [KEY] 使用 singleShot(0) 将整个数据准备推入下一个事件循环
        # 10ms 延迟给 UI 一个喘息机会
        QtCore.QTimer.singleShot(10, _do_async_update)
    
    def _set_table_row(self, row_idx, stock_code, stock_name, optional_cols_real, 
                       optional_data, no_edit_flag, data_idx=None):
        """设置表格行数据（用于新增和全量刷新）"""
        if data_idx is None:
            data_idx = row_idx
            
        # Code 列
        code_item = QTableWidgetItem(stock_code)
        code_item.setData(Qt.ItemDataRole.UserRole, stock_code)
        code_item.setFlags(code_item.flags() & ~no_edit_flag)
        self.stock_table.setItem(row_idx, 0, code_item)
        
        # Name 列
        name_item = QTableWidgetItem(stock_name)
        name_item.setFlags(name_item.flags() & ~no_edit_flag)
        self.stock_table.setItem(row_idx, 1, name_item)
        
        # 更新映射
        self.code_name_map[stock_code] = stock_name
        code_info = {"name": stock_name}
        
        # 可选列
        for col_idx, (col_name, _) in enumerate(optional_cols_real, start=2):
            val = optional_data[col_name][data_idx]
            code_info[col_name] = val
            
            item = QTableWidgetItem()
            if pd.notnull(val):
                if isinstance(val, (int, float, np.integer, np.floating)):
                    item.setData(Qt.ItemDataRole.DisplayRole, float(val))
                else:
                    item.setData(Qt.ItemDataRole.DisplayRole, str(val))
            else:
                item.setData(Qt.ItemDataRole.DisplayRole, 0.0)
            
            # 颜色渲染
            # if col_name in ('percent', 'dff','per1d') and pd.notnull(val):
            if pd.notnull(val) and (
                col_name in ('percent', 'dff') 
                or (col_name.startswith('per') and col_name.endswith('d') and col_name[3:-1].isdigit())
            ):
                val_float = float(val)
                if val_float > 0:
                    item.setForeground(QColor('red'))
                elif val_float < 0:
                    item.setForeground(QColor('green'))
            
            item.setFlags(item.flags() & ~no_edit_flag)
            self.stock_table.setItem(row_idx, col_idx, item)
        
        self.code_info_map[stock_code] = code_info
    
    def _update_table_row(self, row_idx, stock_code, stock_name, optional_cols_real, 
                          optional_data, data_idx):
        """更新表格行数据（用于增量更新，只更新变化的值）"""
        # 检查并更新可选列
        for col_idx, (col_name, _) in enumerate(optional_cols_real, start=2):
            val = optional_data[col_name][data_idx]
            
            item = self.stock_table.item(row_idx, col_idx)
            if item:
                old_val = item.data(Qt.ItemDataRole.DisplayRole)
                new_val = float(val) if pd.notnull(val) and isinstance(val, (int, float, np.integer, np.floating)) else str(val) if pd.notnull(val) else 0.0
                
                # 只有值变化时才更新
                if old_val != new_val:
                    item.setData(Qt.ItemDataRole.DisplayRole, new_val)
                    
                    # 更新颜色
                    # if col_name in ('percent', 'dff','per1d') and pd.notnull(val):
                    if pd.notnull(val) and (
                        col_name in ('percent', 'dff') 
                        or (col_name.startswith('per') and col_name.endswith('d') and col_name[3:-1].isdigit())
                    ):
                        val_float = float(val)
                        if val_float > 0:
                            item.setForeground(QColor('red'))
                        elif val_float < 0:
                            item.setForeground(QColor('green'))
                        else:
                            item.setForeground(QColor('black'))
        
        # 更新映射
        if stock_code in self.code_info_map:
            for col_name, _ in optional_cols_real:
                self.code_info_map[stock_code][col_name] = optional_data[col_name][data_idx]
    
    def _rebuild_item_map_from_table(self):
        """从表格重建 item_map（优化版：直读模型数据）"""
        self._table_item_map = {}
        model = self.stock_table.model()
        for row_idx in range(self.stock_table.rowCount()):
            # 尝试从模型索引获取数据，避开 QTableWidgetItem 对象访问
            code_data = model.index(row_idx, 0).data(Qt.ItemDataRole.UserRole)
            if code_data:
                self._table_item_map[str(code_data)] = row_idx

    # 2️⃣ 处理右键事件
    def on_table_right_click(self, pos):
        logger.info(f"on_table_right_click at {pos}")
        item = self.stock_table.itemAt(pos)
        if not item:
            logger.info("No item at pos")
            return

        # 尝试从当前单元格获取 UserRole (通常是 code)
        stock_code = item.data(Qt.ItemDataRole.UserRole)
        
        # [NEW] 如果当前单元格没有 code (比如点击了名称列)，则从同行的第 0 列获取
        if not stock_code:
            row_idx = self.stock_table.row(item)
            code_item = self.stock_table.item(row_idx, 0)
            if code_item:
                stock_code = code_item.data(Qt.ItemDataRole.UserRole)
        
        logger.info(f"Right click stock_code: {stock_code}")
        
        if not stock_code:
            return

        # 获取股票信息 (允许 df_all 为空时尝试从 item 获取基础信息)
        if hasattr(self, 'df_all') and not self.df_all.empty and stock_code in self.df_all.index:
            row = self.df_all.loc[stock_code]
        else:
            row = None
        
        stock_name = row.get('name', '') if row is not None else ''
        
        # 创建右键菜单
        menu = QMenu(self)
        
        # [NEW] SBC 回放分析
        sbc_action = menu.addAction("📊 SBC 回放分析")
        sbc_action.triggered.connect(lambda: self._run_sbc_test(False, stock_code))
        
        menu.addSeparator()
        
        # 发送到通达信
        send_action = menu.addAction("📤 发送到通达信")
        send_action.triggered.connect(lambda: self._on_send_to_tdx(stock_code, row))
        
        menu.addSeparator()
        
        # 添加到热点
        hotlist_action = menu.addAction("🔥 添加到热点自选")
        hotlist_action.triggered.connect(lambda: self._on_add_to_hotlist_from_menu(stock_code, stock_name, row))
        
        menu.exec(self.stock_table.mapToGlobal(pos))

    def on_filter_tree_right_click(self, pos):
        """Filter Tree 右键菜单"""
        logger.info(f"on_filter_tree_right_click at {pos}")
        item = self.filter_tree.itemAt(pos)
        if not item: 
            logger.info("No filter item at pos")
            return
        
        # 假设第一列是 Code
        stock_code = item.text(0)
        stock_name = item.text(1) if item.columnCount() > 1 else ""
        logger.info(f"Filter tree code: {stock_code}")
        
        if not stock_code: return
        
        menu = QMenu(self)
        
        # [NEW] SBC 回放分析
        sbc_action = menu.addAction("📊 SBC 回放分析")
        sbc_action.triggered.connect(lambda: self._run_sbc_test(False, stock_code))
        
        menu.addSeparator()
        
        # 添加到热点
        hotlist_action = menu.addAction("🔥 添加到热点自选")
        row = self.df_all.loc[stock_code] if (hasattr(self, 'df_all') and not self.df_all.empty and stock_code in self.df_all.index) else None
        hotlist_action.triggered.connect(lambda: self._on_add_to_hotlist_from_menu(stock_code, stock_name, row))
        
        # 发送到通达信
        send_action = menu.addAction("📤 发送到通达信")
        send_action.triggered.connect(lambda: self._on_send_to_tdx(stock_code, row))

        menu.exec(self.filter_tree.mapToGlobal(pos))

    def _on_send_to_tdx(self, stock_code, row):
        """发送到通达信"""
        if row is not None:
            success = self.push_stock_info(stock_code, row)
            if success:
                self.show_status_message(f"发送成功: {stock_code}")
            else:
                self.show_status_message(f"发送失败: {stock_code}")

    def _on_add_to_hotlist_from_menu(self, code: str, name: str, row):
        """从右键菜单添加到热点"""
        price = 0.0
        if row is not None:
            price = float(row.get('close', row.get('price', 0)))
        
        if hasattr(self, 'hotlist_panel'):
            if self.hotlist_panel.contains(code):
                self.show_status_message(f"热点已存在: {code} {name}")
            else:
                success = self.hotlist_panel.add_stock(code, name, price, "右键添加")
                if success:
                    self.show_status_message(f"🔥 添加热点: {code} {name}")
                    # 自动显示面板
                    if not self.hotlist_panel.isVisible():
                        self.hotlist_panel.show()

    def on_header_section_clicked(self, _logicalIndex):
        """
        排序后逻辑：
        仅保留滚动位置恢复，防止视图跳动。
        不再自动调整列宽，完全保留用户的微调记忆。
        """
        scroll_state = self._save_h_scroll_state(self.stock_table)
        
        # 恢复水平位置，防止排序导致的选择项偏移
        self._restore_h_scroll_state(self.stock_table, scroll_state)
        
        # 延时滚动到顶部
        QTimer.singleShot(100, self.stock_table.scrollToTop)

    def on_filter_tree_header_clicked(self, _logicalIndex):
        """Filter Tree: 排序时保留手动列宽"""
        scroll_state = self._save_h_scroll_state(self.filter_tree)
        self._restore_h_scroll_state(self.filter_tree, scroll_state)

    def _on_shortcut_autofit(self):
        """Alt+W 触发：紧凑型自适应"""
        widget = self.focusWidget()
        target = None
        if isinstance(widget, (QTableWidget, QTreeWidget)):
            target = widget
        elif hasattr(self, 'stock_table') and self.stock_table.hasFocus():
            target = self.stock_table
        elif hasattr(self, 'filter_tree') and self.filter_tree.hasFocus():
            target = self.filter_tree
            
        if target:
            self._resize_columns_tightly(target)
            self.show_status_message(f"Layout Optimized: {target.objectName() or 'Table'}", 2000)

    def _on_column_resized_debounced(self, index, old_size, new_size):
        """列宽变动防抖保存"""
        if abs(new_size - old_size) <= 2: return # 忽略微小变动
        if hasattr(self, '_resize_timer'):
            self._resize_timer.start(2000) # 2秒后执行 _save_visualizer_config

    def on_table_cell_clicked(self, row, column):
        code_item = self.stock_table.item(row, 0)
        if code_item:
            code = code_item.data(Qt.ItemDataRole.UserRole)
            if code:
                self._clicked_change = True
                if code == self.current_code: 
                    # 如果 code 没变，说明 currentItemChanged 不会触发，手动同步一次 (强制同步)
                    # TDX 或 THS 任一开启时都发送
                    if self.tdx_enabled or self.ths_enabled:
                        try:
                            self.sender.send(code)
                        except Exception:
                            pass
                # 如果 code 变了，currentItemChanged 会处理加载和同步

    def on_table_cell_double_clicked(self, row, column):
        """双击事件：如果是代码列则复制到剪贴板"""
        if column == 0:  # 代码列
            code_item = self.stock_table.item(row, column)
            if code_item:
                code = code_item.data(Qt.ItemDataRole.UserRole) or code_item.text()
                if code:
                    # 获取剪贴板并设置文本
                    cb = QApplication.clipboard()
                    if cb:
                        cb.setText(code)
                        # self.statusBar().showMessage(f"📋 已复制代码: {code}", 3000)
                        self.show_status_message(f"📋 已复制代码: {code}", 3000)
                    logger.info(f"[Table] Copied to clipboard: {code}")
                
        if column == 1:  # Name列
            code_item = self.stock_table.item(row, 0)
            if code_item:
                code = code_item.data(Qt.ItemDataRole.UserRole) or code_item.text()
                if code:
                    # [NEW] 双击代码列同时执行 SBC 回放分析
                    self._run_sbc_test(False, code)
        if column == 2:  # 涨幅列
            code_item = self.stock_table.item(row, 0)
            if code_item:
                code = code_item.data(Qt.ItemDataRole.UserRole) or code_item.text()
                if code:
                    # [NEW] 双击代码列同时执行 SBC 回放分析
                    self._run_sbc_test(True, code)

    def switch_stock_prev(self):
        """切换至上一只股票 (1.1/1.2 Context navigation)"""
        curr_row = self.stock_table.currentRow()
        if curr_row > 0:
            self.stock_table.setCurrentCell(curr_row - 1, 0)

    def switch_stock_next(self):
        """切换至下一只股票 (1.1/1.2 Context navigation)"""
        curr_row = self.stock_table.currentRow()
        if curr_row < self.stock_table.rowCount() - 1:
            self.stock_table.setCurrentCell(curr_row + 1, 0)

    def on_current_item_changed(self, current, previous):
        """处理键盘上下键引起的行切换"""
        if current:
            row = current.row()
            code_item = self.stock_table.item(row, 0)
            if code_item:
                code = code_item.data(Qt.ItemDataRole.UserRole)
                if code != self.current_code:
                    self.load_stock_by_code(code)
                    
                    # 1.1: 无论是键盘还是点击，只要切换了代码，且开启了同步，就发送给外部工具
                    # TDX 或 THS 任一开启时都发送
                    if self.tdx_enabled or self.ths_enabled:
                        try:
                            self.sender.send(code)
                        except Exception as e:
                            print(f"Error sending stock code: {e}")
                    
                    # 消费掉点击标记
                    if getattr(self, "_clicked_change", False):
                        self._clicked_change = False

    def _check_hotspot_alerts(self, df):
        """检查热点股票的实时信号并语音播报"""
        if not hasattr(self, 'hotlist_panel') or not self.hotlist_panel.items:
            return
            
        # 如果传入的是 dict (新协议)，尝试提取 data 部分
        if isinstance(df, dict):
            df = df.get('data', getattr(self, 'df_all', None))
            
        if not isinstance(df, pd.DataFrame):
            return

        # 简单的频率控制 (每5秒最多一次播报)
        import time
        now = time.time()
        if not hasattr(self, '_last_alert_time'):
            self._last_alert_time = 0
            self._alerted_signals = {}  # {code: last_action_str}
        
        # 遍历热点股
        alerts = []
        for item in self.hotlist_panel.items:
            if item.code in df.index:
                row = df.loc[item.code]
                # [FIX] 数据保护：当 index 重复时，df.loc 返回 DataFrame，需取第一行
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                
                # [NEW] 顺便更新热点面板中的现价和盈亏
                # [FIX] 安全获取价格，防止 Series 类型错误
                try:
                    price_val = row.get('close', row.get('price', 0))
                    # 处理可能的 Series 或 NaN
                    if isinstance(price_val, pd.Series):
                        price_val = price_val.iloc[0] if len(price_val) > 0 else 0
                    curr_price = float(price_val) if pd.notnull(price_val) else 0.0
                except (TypeError, ValueError, IndexError):
                    curr_price = 0.0
                if curr_price > 0:
                    item.current_price = curr_price
                    if item.add_price > 0:
                        item.pnl_percent = (curr_price - item.add_price) / item.add_price * 100
                
                # 检查 last_action 列 (策略信号)
                try:
                    action_val = row.get('last_action', '')
                    if isinstance(action_val, pd.Series):
                        action_val = action_val.iloc[0] if len(action_val) > 0 else ''
                    action = str(action_val) if pd.notnull(action_val) else ''
                except (TypeError, ValueError, IndexError):
                    action = ''
                
                if action and ('买' in action or '卖' in action):
                    # 检查是否是新信号
                    last_val = self._alerted_signals.get(item.code, '')
                    if str(action) != last_val:
                        self._alerted_signals[item.code] = str(action)
                        alerts.append(f"{item.name}({action})")
                        # ⚡ [SYNC] 转给 _on_signal_log，确保同步记录后再播报
                        self._on_signal_log(item.code, item.name, 'ALERT', action, is_high_priority=True)
        
        # 刷新热点面板表格
        if hasattr(self, 'hotlist_panel'):
            self.hotlist_panel._refresh_table()

        if alerts:
            alert_msg = " | ".join(alerts)
            # 状态栏提示 (如果界面存在)
            if self.isVisible():
                self.show_status_message(f"🔔 热点股异动: {alert_msg}", 10000)
            
            self._last_alert_time = now

    def on_dataframe_received(self, df, msg_type):
        """接收 DataFrame 更新 (优化: 避免阻塞主线程)
        
        [CRITICAL FIX] 防重复处理：
        - 当正在处理全量同步时，忽略后续的重复 ver=0 请求
        - 避免多个全量同步并发执行导致卡死
        
        [NEW] 实时热点监控
        """
        # [NEW] 实时热点监控
        self._check_hotspot_alerts(df)

        # ⚡ [CRITICAL] 初始化/检查防重复标志
        if not hasattr(self, '_is_processing_full_sync'):
            self._is_processing_full_sync = False
        if not hasattr(self, '_last_full_sync_time'):
            self._last_full_sync_time = 0
            
        if msg_type == 'UPDATE_DF_DATA' and isinstance(df, dict):
            # 新版字典协议
            m_type = df.get('type')
            payload = df.get('data')
            ver = df.get('ver', 0)
            
            # 版本校验逻辑
            # ⭐ [SYNC FIX] 如果 ver == 0，视为全量强制覆盖，无视之前的所有版本记录
            actual_type = df.get('type')
            
            # ⚡ [CRITICAL] 检测是否为全量同步请求
            is_full_sync = (m_type == 'UPDATE_DF_ALL' or ver == 0 or 
                           (m_type == 'UPDATE_DF_DATA' and actual_type == 'UPDATE_DF_ALL'))
            
            if is_full_sync:
                import time
                now = time.time()
                # ⚡ [CRITICAL] 防重复：如果正在处理或距离上次同步不到2秒，忽略
                if self._is_processing_full_sync:
                    logger.warning(f"[IPC] Ignoring duplicate full sync (already processing)")
                    return
                if now - self._last_full_sync_time < 2.0:
                    logger.warning(f"[IPC] Ignoring full sync request (too frequent, last: {now - self._last_full_sync_time:.2f}s ago)")
                    return
                    
                self._is_processing_full_sync = True
                self._last_full_sync_time = now
                self.expected_sync_version = ver
                logger.info(f"[IPC] Received Full Sync (ver={ver}, rows={len(payload)})")
                
                # ⚡ [CRITICAL] 暂停语音播报，防止 COM 冲突导致卡死
                if hasattr(self, 'voice_thread') and self.voice_thread:
                    # ⚡ [OPTIMIZATION] 使用真正的 pause() 挂起语音，避免 COM 冲突
                    self.voice_thread.pause()
                    self.voice_thread.pause_for_sync = True
                    logger.debug("[IPC] Voice thread PAUSED for full sync")
                
                def _safe_process():
                    logger.debug("[_safe_process] START")
                    try:
                        self._process_df_all_update(payload)
                        logger.debug("[_safe_process] _process_df_all_update completed")
                    except Exception as e:
                        import traceback
                        logger.error(f"[_safe_process] Error: {e}")
                        logger.error(f"[_safe_process] Traceback: {traceback.format_exc()}")
                    finally:
                        self._is_processing_full_sync = False
                        # ⚡ [CRITICAL] 恢复语音播报（已弃用分块，直接恢复）
                        if hasattr(self, 'voice_thread') and self.voice_thread:
                            # ⚡ [OPTIMIZATION] 恢复语音
                            self.voice_thread.pause_for_sync = False
                            self.voice_thread.resume()
                            logger.debug("[IPC] Voice thread RESUMED after full sync")
                        logger.debug("[_safe_process] END, _is_processing_full_sync reset to False")
                        
                QtCore.QTimer.singleShot(10, _safe_process)
                return
                
            if m_type == 'UPDATE_DF_DIFF':
                if self.expected_sync_version != -1 and ver == self.expected_sync_version + 1:
                    self.expected_sync_version = ver
                    logger.info(f"[IPC] Received DF_DIFF (ver={ver}, rows={len(payload)})")
                    
                    # ⚡ [OPTIMIZATION] 大数据量 Diff 也需要暂停语音，防止卡顿
                    is_large_diff = len(payload) > 1000
                    if is_large_diff:
                        if hasattr(self, 'voice_thread') and self.voice_thread:
                            self.voice_thread.pause()
                            self.voice_thread.pause_for_sync = True
                            logger.debug(f"[IPC] Voice thread PAUSED for large DIFF ({len(payload)} rows)")

                    def _safe_apply_diff():
                        try:
                            self.apply_df_diff(payload)
                        finally:
                            if is_large_diff:
                                if hasattr(self, 'voice_thread') and self.voice_thread:
                                    self.voice_thread.pause_for_sync = False
                                    self.voice_thread.resume()
                                    logger.debug("[IPC] Voice thread RESUMED after large DIFF")

                    QtCore.QTimer.singleShot(0, _safe_apply_diff)
                else:
                    logger.warning(f"[IPC] Version mismatch! Got {ver}, expected {self.expected_sync_version + 1}. Requesting full sync.")
                    self._request_full_sync()
            return

        if msg_type == "UPDATE_DF_ALL":
            # 同样应用防重复逻辑
            import time
            now = time.time()
            if self._is_processing_full_sync or (now - self._last_full_sync_time < 2.0):
                logger.warning(f"[IPC] Ignoring duplicate UPDATE_DF_ALL")
                return
            self._is_processing_full_sync = True
            self._last_full_sync_time = now
            
            # ⚡ [CRITICAL] 暂停语音播报
            if hasattr(self, 'voice_thread') and self.voice_thread:
                # ⚡ [OPTIMIZATION] 同样处理 UPDATE_DF_ALL
                self.voice_thread.pause()
                self.voice_thread.pause_for_sync = True
                logger.debug("[IPC] Voice thread PAUSED for UPDATE_DF_ALL")
            
            def _safe_process():
                try:
                    self._process_df_all_update(df)
                finally:
                    self._is_processing_full_sync = False
                    # ⚡ [CRITICAL] 恢复语音播报（已弃用分块，直接恢复）
                    if hasattr(self, 'voice_thread') and self.voice_thread:
                        self.voice_thread.pause_for_sync = False
                        self.voice_thread.resume()
                        logger.debug("[IPC] Voice thread RESUMED (UPDATE_DF_ALL)")
            QtCore.QTimer.singleShot(10, _safe_process)
        elif msg_type == "UPDATE_DF_DIFF":
            # diff 更新通常较小，可以直接处理
            QtCore.QTimer.singleShot(0, lambda: self.apply_df_diff(df))
        else:
            logger.warning(f"Unknown msg_type: {msg_type}")
    
    def _process_df_all_update(self, df):
        """处理完整 DataFrame 更新 (优化: 分块处理避免 UI 冻结)
        
        [OPTIMIZATION] 修复全量数据卡死问题：
        - 移除同步的 df.copy() 操作
        - 直接引用 DataFrame，避免大数据量时的内存复制阻塞
        """
        logger.debug(f"[_process_df_all_update] START: df type={type(df)}, rows={len(df) if df is not None else 'None'}")
        try:
            # ⚡ [CRITICAL FIX] 直接引用 DataFrame，不做 copy() 避免阻塞
            # copy() 在大数据量（5000+行）时可能需要数秒
            if df is not None and not df.empty:
                self.df_cache = df  # 直接引用，不复制
                self.df_all = df
                logger.debug(f"[_process_df_all_update] df_all updated, rows={len(self.df_all)}")
                # [REMOVED] DataHubService publish logic
                pass
            elif df is not None:
                self.df_cache = pd.DataFrame()
                self.df_all = self.df_cache
                logger.debug("[_process_df_all_update] df is empty, reset df_all")
            
            # ⚡ 更新表格 (完全异步)
            # ⭐ [SYNC FIX] 全量包 ver=0 必须强制刷新表格
            is_full = True # 默认全量
            logger.debug(f"[_process_df_all_update] Calling update_stock_table, force_full={is_full}")
            self.update_stock_table(self.df_all, force_full=is_full)
            logger.debug("[_process_df_all_update] update_stock_table dispatched")
            
            # ⭐ [STABILITY FIX] 移除了强制 processEvents，防止在大规模同步期间产生危险的逻辑重入
            
            # ⚡ 刷新监理看板 (延迟执行，避免阻塞)
            def _delayed_refresh():
                try:
                    logger.debug("[_delayed_refresh] Executing...")
                    if getattr(self, 'current_code', None) and hasattr(self, 'kline_plot'):
                        self._refresh_sensing_bar(self.current_code)
                    logger.debug("[_delayed_refresh] Done")
                except Exception as e:
                    logger.error(f"[_delayed_refresh] Error: {e}")
            QtCore.QTimer.singleShot(100, _delayed_refresh)
            
            # ⭐ [SYNC FIX] 确保 IPC 数据导致的布局剧烈变化后，K 线图能自适应感知新的几何尺寸
            if hasattr(self, 'kline_plot'):
                def _force_sync_geometry():
                    try:
                        logger.debug("[_force_sync_geometry] Executing...")
                        if not hasattr(self.kline_plot, 'vb'): return
                        vb = self.kline_plot.vb
                        # 1. 强力刷新坐标映射
                        vb.sigResized.emit(vb)
                        vb.update()
                        # 2. 如果当前处于全览模式，则自动重置一次以校准范围
                        self.kline_plot.update()
                        logger.debug("[_force_sync_geometry] Done")
                    except Exception as e:
                        logger.error(f"[_force_sync_geometry] Error: {e}")
                    
                # 稍微多等一会儿，确保表格渲染完毕且 QSplitter 动作结束
                QtCore.QTimer.singleShot(350, _force_sync_geometry)
            
            # ⚡ 处理热榜信号 (延迟执行，轻量操作)
            if SIGNAL_QUEUE_AVAILABLE:
                def _delayed_hot_signals():
                    try:
                        logger.debug("[_delayed_hot_signals] Executing...")
                        self._process_hot_signals(df if df is not None else self.df_all)
                        logger.debug("[_delayed_hot_signals] Done")
                    except Exception as e:
                        logger.error(f"[_delayed_hot_signals] Error: {e}")
                QtCore.QTimer.singleShot(200, _delayed_hot_signals)
            
            # ⚡ [FIX] 热点形态检测 - 驱动信号日志面板
            def _delayed_hotlist_check():
                try:
                    # 如果 self._check_hotlist_patterns 存在则调用，否则降级到 _check_hotspot_alerts
                    if hasattr(self, '_check_hotlist_patterns'):
                        self._check_hotlist_patterns()
                    else:
                        self._check_hotspot_alerts(df if df is not None else self.df_all)
                except Exception as e:
                    logger.error(f"[_delayed_hotlist_check] Error: {e}")
            QtCore.QTimer.singleShot(300, _delayed_hotlist_check)
            
            # ⚡ [NEW] 全市场缺口探测
            def _delayed_gap_check():
                try:
                    self._check_market_gaps()
                except Exception as e:
                    logger.debug(f"[_delayed_gap_check] Error: {e}")
            QtCore.QTimer.singleShot(500, _delayed_gap_check)

            # ⚡ [NEW] 如果 Filter Panel 可见，则自动刷新 Filter 结果
            def _delayed_filter_refresh():
                try:
                    if not hasattr(self, 'main_splitter'): return
                    sizes = self.main_splitter.sizes()
                    # Check visibility safely
                    is_presently_visible = True if (len(sizes) > 2 and sizes[2] > 0) else False
                    
                    if hasattr(self, 'filter_panel') and is_presently_visible:
                         logger.debug("[_process_df_all_update] Triggering delayed filter refresh")
                         self.load_history_filters()
                except Exception as e:
                    logger.error(f"[_delayed_filter_refresh] Error: {e}")

            QtCore.QTimer.singleShot(400, _delayed_filter_refresh)
            
            logger.debug("[_process_df_all_update] END: All tasks dispatched successfully")
                
        except Exception as e:
            import traceback
            logger.error(f"Error processing df_all update: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    def _request_full_sync(self):
        """向 Monitor 发送全量同步请求 (带重试)"""
        max_retries = 3
        for i in range(max_retries):
            try:
                success = send_code_via_pipe({"cmd": "REQ_FULL_SYNC"}, logger=logger,pipe_name=PIPE_NAME_TK)
                if success:
                    logger.info(f"[Sync] Requested full sync via Pipe (Attempt {i+1})")
                    # 暂时将版本设为无效，防止在收到全量包前继续处理碎片增量
                    self.expected_sync_version = -1
                    return
                else:
                    logger.warning(f"[Sync] Failed to send sync request via Pipe (Attempt {i+1})")
                    time.sleep(0.5) # Wait before retry
            except Exception as e:
                logger.error(f"[Sync] Request full sync error (Attempt {i+1}): {e}")
                time.sleep(0.5)
        
        logger.error("[Sync] Gave up requesting full sync after retries")

    def _process_hot_signals(self, df):
        """从df中提取热榜Top5推送到信号队列"""
        if not SIGNAL_QUEUE_AVAILABLE: return

        try:
            queue = SignalMessageQueue()
            # 确保有 Rank 列
            if 'Rank' not in df.columns:
                return

            # 转 numeric
            df_temp = df.copy()
            df_temp['Rank'] = pd.to_numeric(df_temp['Rank'], errors='coerce')

            # 取 Rank 前 5 (Rank > 0)
            top5 = df_temp[df_temp['Rank'] > 0].nsmallest(5, 'Rank')

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for _, row in top5.iterrows():
                code = row['code'] if 'code' in row else row.name
                if not isinstance(code, str): code = str(code)
                code = code.zfill(6)

                # 检查是否已经在队列Top中且未评估？避免重复刷屏?
                # SignalMessageQueue 会自动处理排序，但不会自动去重(相同timestamp)。
                # 作为一个简单策略，我们每次都推送最新的状态

                rank_val = int(row['Rank'])
                cat = row.get('category', '')

                msg = SignalMessage(
                    priority=rank_val,
                    timestamp=timestamp,
                    code=code,
                    name=row.get('name', ''),
                    signal_type='HOT_WATCH',
                    source='HOT_LIST',
                    reason=f"Rank#{rank_val}: {cat}",
                    score=100 - rank_val * 10
                )
                queue.push(msg)

            self._update_signal_badge()

        except Exception as e:
            logger.error(f"Error processing hot signals: {e}")

    def _flush_table_updates(self):
        """节流器回调：正式执行缓存的表格更新"""
        if self.df_all is None or self.df_all.empty:
            return
            
        import time
        now = time.time()
        
        # 确保最小间隔
        if now - self._last_table_update_time < 0.8:
            self._table_refresh_timer.start(500)
            return

        codes = self._pending_changed_codes.copy()
        self._pending_changed_codes.clear()
        
        logger.debug(f"[TableThrottle] Flushing {len(codes)} updates...")
        force_full = "ALL" in codes
        if force_full:
            codes.remove("ALL")
            
        # 如果 codes 为空且没有 ALL，说明没啥好更新的
        if not codes and not force_full:
            return
            
        self.update_stock_table(self.df_all, force_full=force_full, changed_codes=None if force_full else codes)
        self._last_table_update_time = now

    def update_df_all(self, df=None, changed_codes=None):
        """
        更新 df_all 数据并请求表格刷新 (节流)
        """
        if df is not None:
            self.df_all = df
            self.df_cache = df
            
        self.request_table_update(changed_codes)

    def request_table_update(self, changed_codes=None):
        """请求刷新表格 (带节流)"""
        if changed_codes:
            self._pending_changed_codes.update(changed_codes)
        else:
            self._pending_changed_codes.add("ALL")
            
        import time
        now = time.time()
        
        # 立即更新或延迟
        if now - self._last_table_update_time > (self._table_update_interval * 2):
            self._flush_table_updates()
        elif not self._table_refresh_timer.isActive():
            delay = max(50, int((self._table_update_interval - (now - self._last_table_update_time)) * 1000))
            self._table_refresh_timer.start(delay)

        # ⚡ [NEW] 如果 Filter Panel 可见，则自动刷新 Filter 结果
        sizes = self.main_splitter.sizes()
        # 当前是否可见
        is_presently_visible = True if sizes[2] > 0 else False
        if hasattr(self, 'filter_panel') and is_presently_visible:
             QtCore.QTimer.singleShot(200, self.load_history_filters)


    def _capture_view_state(self):
        """在切换数据前，精准捕获当前的可见窗口"""
        if not hasattr(self, 'day_df') or self.day_df.empty:
            return
        try:
            vb = self.kline_plot.getViewBox()
            view_rect = vb.viewRect()
            total = len(self.day_df)

            # 1. 检测是否处于“全览”状态（即当前已经看完了绝大部分数据）
            # 如果左边缘接近 0 且右边缘接近末尾，则标记为 FullView
            self._prev_is_full_view = (view_rect.left() <= 10 and view_rect.right() >= total - 5)
            logger.debug(f'total: {total} _prev_is_full_view: { self._prev_is_full_view }')
            # 2. 捕获两端相对于末尾的偏移根数
            self._prev_dist_left = total - view_rect.left()
            self._prev_dist_right = total - view_rect.right()

            # 3. 捕获价格比例关系
            v_start, v_end = int(max(0, view_rect.left())), int(min(total, view_rect.right()))
            visible_old = self.day_df.iloc[v_start:v_end]
            if not visible_old.empty:
                old_h, old_l = visible_old['high'].max(), visible_old['low'].min()
                old_rng = old_h - old_l if old_h > old_l else 1.0
                self._prev_y_zoom = view_rect.height() / old_rng
                self._prev_y_center_rel = (view_rect.center().y() - old_l) / old_rng
            else:
                self._prev_y_zoom = None

            # logger.debug(f"[VIEW] Capture: is_full={self._prev_is_full_view}, left_d={self._prev_dist_left:.1f}")
        except Exception as e:
            logger.debug(f"Capture state failed: {e}")

    def _reset_kline_view(self, df=None, force=False, target_width=None):
        """
        ⭐ [核心修复] 重置 K 线视图范围
        
        使用 main_splitter.sizes()[1] 获取图表区域的实际像素宽度（可靠值），
        而不是 ViewBox.width()（有时不准）。
        
        Args:
            df: DataFrame，用于计算 Y 轴范围，默认使用 self.day_df
            force: 是否强制重置，忽略手动调整状态
            target_width: 强制使用的图表宽度（像素），用于布局加载时的预计算
        """
        try:
            # 1. 净化 df 参数
            # Qt 信号槽可能会把 checked (bool) 传给第一个参数，所以必须处理 bool
            if df is None or isinstance(df, bool):
                df = getattr(self, 'day_df', None)
            
            # 2. 最后的防线：确保 df 是 DataFrame
            if df is None or not isinstance(df, pd.DataFrame):
                # logger.warning(f"[_reset_kline_view] Valid DataFrame not found (got {type(df)}), aborting.")
                return

            # 3. 检查是否为空
            if df.empty:
                return
            
            total_bars = len(df)
            vb = self.kline_plot.getViewBox()
            
            # ========== 1. 计算图表区域的实际像素宽度 ==========
            # 优先顺序: target_width > widget.width() (最准) > splitter.sizes()[1] > ViewBox.width()
            chart_pixel_width = 800  # 默认值
            
            sizes = []
            if target_width is not None and isinstance(target_width, (int, float)) and target_width > 0:
                chart_pixel_width = int(target_width)
            elif hasattr(self, 'kline_widget') and self.kline_widget.width() > 100:
                # ⭐ [OPTIMIZATION] Widget 宽度在渲染稳定后是最准确的
                chart_pixel_width = self.kline_widget.width()
            elif hasattr(self, 'main_splitter'):
                try:
                    sizes = self.main_splitter.sizes()
                    if len(sizes) >= 2:
                        chart_pixel_width = max(sizes[1], 200)
                except Exception:
                    pass
            
            if chart_pixel_width <= 200: # 最后的兜底
                try:
                    vb_width = vb.width()
                    if vb_width and vb_width > 100:
                        chart_pixel_width = vb_width
                except Exception:
                    pass
            
            # ========== 2. 计算可见 K 线数 ==========
            # ⭐ [OPTIMIZATION] 增加单根 K 线宽度，减少可见根数，使显示不那么“拥挤”
            # 原为 10，现改为 18
            BAR_PIXEL_WIDTH = 18
            visible_bars = max(35, int(chart_pixel_width / BAR_PIXEL_WIDTH))
            
            # 限制最小显示根数，防止显示过少但也不要强制太多导致拥挤
            visible_bars = min(visible_bars, 120) 
            
            # ========== 3. 计算 X 轴范围 ==========
            # 始终让最新数据在右侧可见
            # ⭐ [FIX] 预留 2 根 K 线位置 (由 8 改回 2)
            RIGHT_MARGIN = 2 
            x_max = total_bars + RIGHT_MARGIN
            x_min = max(-1, total_bars - visible_bars)
            
            # ========== 4. 设置 X 轴范围 ==========
            vb.setRange(xRange=(x_min, x_max), padding=0)
            
            # ========== 5. 自适应 Y 轴 ==========
            # 根据可见区域的价格范围自动调整 Y 轴
            visible_start = int(max(0, x_min))
            visible_end = int(min(total_bars, x_max))
            
            if visible_start < visible_end and visible_start < len(df):
                visible_df = df.iloc[visible_start:visible_end]
                logger.debug(f'visible_df: {visible_df[-1:]}')
                if visible_df is not None and not visible_df.empty and 'high' in visible_df.columns and 'low' in visible_df.columns:
                    y_high = visible_df['high'].max()
                    y_low = visible_df['low'].min()
                    y_margin = (y_high - y_low) * 0.05  # 5% 边距
                    vb.setRange(yRange=(y_low - y_margin, y_high + y_margin), padding=0)
            
            # ========== 6. 启用 Y 轴自动范围 ==========
            vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            vb.setAutoVisible(y=True)
            
            logger.debug(f"[_reset_kline_view] sizes:{sizes} Reset: bars={total_bars}, visible={visible_bars}, xRange=({x_min:.0f}, {x_max:.0f}), width={chart_pixel_width}px")
            
        except Exception as e:
            logger.warning(f"[_reset_kline_view] Failed: {e}")
            import traceback
            traceback.print_exc()
            try:
                vb = self.kline_plot.getViewBox()
                vb.enableAutoRange(enable=True)
            except Exception:
                pass

    def _reset_tick_view(self, tick_df=None, pre_close=None):
        """
        ⭐ [NEW] 重置分时图 (Tick Plot) 视图范围
        支持在 render_charts 中自动调用，或通过 R 键手动触发。
        """
        try:
            # 1. 确定数据源与极限值
            if tick_df is not None and not tick_df.empty:
                prices = tick_df['close'].values
                # 提取有效的 high/low 数据（过滤 NaN）
                valid_high = tick_df['high'].dropna()
                valid_low = tick_df['low'].dropna()
                
                if not valid_high.empty and not valid_low.empty:
                    y_max = float(valid_high.max())
                    y_min = float(valid_low.min())
                else:
                    y_max = prices.max() if prices.size > 0 else 0
                    y_min = prices.min() if prices.size > 0 else 0
                
                x_count = len(tick_df)
                
                # 缓存状态供 R 键重置使用
                self.tick_high_max = y_max
                self.tick_low_min = y_min
                self.tick_x_max = x_count - 1
            else:
                # 如果没传 df，使用缓存
                y_max = getattr(self, 'tick_high_max', 0)
                y_min = getattr(self, 'tick_low_min', 0)
                x_max_idx = getattr(self, 'tick_x_max', 0)
                x_count = x_max_idx + 1
                if y_max == 0 and y_min == 0:
                    return # 无数据可重置
            
            # 2. 确定昨日收盘价 (基准线)
            if pre_close is None:
                pre_close = getattr(self, 'current_pre_close', 0)
            
            if pre_close <= 0:
                # 最后的兜底：如果完全没数据，不重置
                if x_count == 0: return
                pre_close = y_max if y_max > 0 else 1.0

            # 3. 计算 Y 轴自适应范围
            view_y_max = max(y_max, pre_close)
            view_y_min = min(y_min, pre_close)
            y_range = view_y_max - view_y_min
            
            if y_range <= 0: 
                y_range = pre_close * 0.01
            
            padding = y_range * 0.1
            
            vb = self.tick_plot.getViewBox()
            # 设置 Y 轴范围 (确保基准线和成交价都在视野内)
            vb.setYRange(view_y_min - padding, view_y_max + padding, padding=0)
            
            # 4. 设置 X 轴范围 (时间轴)
            if x_count > 0:
                x_min = 0
                x_max = x_count - 1
                x_padding = (x_max - x_min) * 0.02 if x_max > x_min else 1
                vb.setXRange(x_min - x_padding, x_max + x_padding, padding=0)
            
        except Exception as e:
            logger.debug(f"[_reset_tick_view] Failed: {e}")

    def load_stock_by_code(self, code, name=None, **kwargs):
        """
        加载股票数据并渲染。支持可扩展参数模式：
        1. 字符串模式: "CODE|代码|key1=val1|key2=val2" (来自 IPC)
        2. 字典模式: 通过 **kwargs 传入 (来自 Queue)
        """
        # [FIX] 强制类型安全，防止 Queue 传递非标字符串导致的底层库查询失败
        if code is not None:
            code = str(code).strip()
            
        # [UPGRADE] 始终捕获当前视角，以便切换股票或周期时能尽可能保持缩放习惯
        self._capture_view_state()

        if isinstance(code, str):
            # 1. 清理可能的空白和前缀
            code = code.strip()
            if code.startswith("CODE|"):
                code = code[5:] # 移除 "CODE|"
            # 2. 解析可能的参数管道符 (code|key=val)
            if "|" in code:
                parts = code.split('|')
                real_code = parts[0]
                
                # 解析后续参数
                for p in parts[1:]:
                    if "=" in p:
                        try:
                            k, v = p.split("=", 1)
                            kwargs[k.strip()] = v.strip()
                        except ValueError:
                            pass
                code = real_code
        
        # [NEW] Capture signal metadata for marking
        self.current_signal_date = kwargs.get('signal_date')
        self.current_signal_type = kwargs.get('signal_type', 'Follow')
        
        # [NEW] Handle specific commands from Monitor (e.g. key bindings)
        if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
            if code == 'TOGGLE_HOTLIST':
                if self.hotlist_panel.isVisible():
                    self.hotlist_panel.hide()
                else:
                    self.hotlist_panel.show()
                    self.hotlist_panel.raise_()
                    self.hotlist_panel.activateWindow()
                return

        logger.debug(f'code: {code} :kwargs :{kwargs}')
        # --- 解析可扩展参数 ---
        params = kwargs.copy()
        # --- 处理周期同步 (resample) ---
        target_resample = params.get('resample')
        if target_resample and target_resample in self.resample_keys:
            if target_resample != self.resample:
                logger.info(f"Syncing resample to {target_resample}")
                # 调用 on_resample_changed 会触发递归调用 load_stock_by_code，
                # 但内部有相同 code/resample 的拦截逻辑
                self.on_resample_changed(target_resample)

        if self.current_code == code and self.select_resample == self.resample and not self.day_df.empty:
            return
        
        # ⭐ 清理交互状态，防止数据残留 (1.2/1.3)
        self.current_code = code
        self.select_resample = self.resample
        self.tick_prices = np.array([])
        self.tick_avg_prices = np.array([])
        self.tick_times = []
        self.current_kline_signals = []
        self.current_tick_crosshair_idx = -1
        
        # [NEW] Main View Linkage -> Signal Log Panel (Reverse Linkage)
        # Highlight the stock in Signal Log Panel if visible, but DO NOT steal focus
        if hasattr(self, 'signal_log_panel') and self.signal_log_panel and self.signal_log_panel.isVisible():
            self.signal_log_panel.highlight_row_by_content(code, "")
        self._hide_crosshair()
        self._hide_tick_crosshair()


        current_row = self.stock_table.currentRow()
        found_in_list = False

        for row in range(self.stock_table.rowCount()):
            item = self.stock_table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == str(code):

                if row != current_row:
                    self.stock_table.blockSignals(True)
                    self.stock_table.setCurrentCell(row, 0)
                    self.stock_table.blockSignals(False)

                    self.stock_table.scrollToItem(
                        item, QAbstractItemView.ScrollHint.EnsureVisible
                    )
                found_in_list = True
                break

        # 如果列表中没找到且提供了名称，则临时添加到列表并选中 (解决信号联动问题)
        if not found_in_list and name:
            row = 0 # 插入到顶部
            self.stock_table.insertRow(row)

            # Code
            code_item = QTableWidgetItem(str(code))
            code_item.setData(Qt.ItemDataRole.UserRole, str(code))
            code_item.setFlags(code_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.stock_table.setItem(row, 0, code_item)

            # Name
            name_item = QTableWidgetItem(str(name))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.stock_table.setItem(row, 1, name_item)

            # Update maps
            self.code_name_map[str(code)] = str(name)
            if str(code) not in self.code_info_map:
                self.code_info_map[str(code)] = {"name": str(name)}

            # Select and Scroll
            self.stock_table.clearSelection() # 清除之前的选择
            self.stock_table.setCurrentCell(row, 0)
            self.stock_table.scrollToItem(code_item, QAbstractItemView.ScrollHint.EnsureVisible)
        
        # [FIX] 设置 Loading 状态同时清理标题缓存, 确保数据加载完成后能强制刷新标题
        # (否则切换周期时因 code 没变, _update_plot_title 会误判为标题无需更新)
        self.kline_plot.setTitle(f"Loading {code}...")
        self._last_full_title = None 

        # ⭐ 清理旧的 DataLoaderThread，使用回收站机制防止闪推
        if hasattr(self, 'loader') and self.loader is not None:
            if self.loader.isRunning():
                logger.debug(f"[DataLoaderThread] Moving active thread to scavenger: {id(self.loader)}")
                try:
                    self.loader.data_loaded.disconnect()  # 重要：断开信号，防止旧数据乱跳
                except Exception:
                    pass
                # 将运行中的线程移入回收站
                self.garbage_threads.append(self.loader)
            self.loader = None

        # ② 加载历史
        with timed_ctx("DataLoaderThreadloader", warn_ms=30):
            # 如果开启策略模拟，则需要加载完整日线指标 (fastohlc=False)
            fastohlc_val = not getattr(self, 'show_strategy_simulation', False)
            self.loader = DataLoaderThread(
                code,
                self.hdf5_mutex,
                resample=self.resample,
                fastohlc=fastohlc_val
            )
        with timed_ctx("data_loaded", warn_ms=50):
            self.loader.data_loaded.connect(self._on_initial_loaded)
        with timed_ctx("start", warn_ms=80):
            self.loader.start()

        # ---- 3. 如果开启 realtime，则确保推送任务 ----
        with timed_ctx("start_realtime_worker", warn_ms=80):
            if self.realtime:
                # 不再检查时间，让 worker 进程自己决定是休眠还是强制抓取一次
                self._start_realtime_process(code)
        if logger.level == LoggerFactory.DEBUG:
            print_timing_summary(top_n=6)

    def show_stock(self, code, name=None, **kwargs):
        """ Alias for load_stock_by_code for backward compatibility """
        return self.load_stock_by_code(code, name, **kwargs)

    def _draw_hotspot_markers(self, code, x_axis, day_df):
        """在 K 线图上绘制热点加入标记 - 复用对象版"""
        self._clear_hotspot_markers() # [FIX] 先清理，防止切股残留
        
        if not hasattr(self, 'hotlist_panel'):
            return
            
        # 1. 初始化持久项 (只运行一次)
        if not hasattr(self, 'hotspot_line_p'):
            self.hotspot_line_p = pg.PlotCurveItem(pen=pg.mkPen('#FF4500', width=1, style=Qt.PenStyle.DashLine))
            self.hotspot_label_p = pg.TextItem(anchor=(0, 1))
            self.hotspot_marker_p = pg.TextItem(html='<div style="font-size: 14pt;">🔥</div>', anchor=(0, 0))
            self.kline_plot.addItem(self.hotspot_line_p)
            self.kline_plot.addItem(self.hotspot_label_p)
            self.kline_plot.addItem(self.hotspot_marker_p)
            
        # 默认隐藏
        self.hotspot_line_p.hide()
        self.hotspot_label_p.hide()
        self.hotspot_marker_p.hide()

        # 尝试匹配：直接匹配 or 6位代码匹配
        target_item = None
        
        # 1. 直接匹配
        if self.hotlist_panel.contains(code):
            for it in self.hotlist_panel.items:
                if it.code == code:
                    target_item = it
                    break
        
        # 2. 如果没找到，尝试模糊匹配 (6位代码)
        if not target_item:
            short_code = code[:6]
            for it in self.hotlist_panel.items:
                if it.code[:6] == short_code:
                    target_item = it
                    break
                    
        if not target_item: 
            return
        
        item = target_item
        
        try:
            # 解析日期
            add_time_str = item.add_time
            if len(add_time_str) >= 10:
                add_date = add_time_str[:10]
            else:
                add_date = add_time_str
            
            # 查找对应的 K 线索引
            idx = -1
            if add_date in day_df.index:
                idx_res = day_df.index.get_loc(add_date)
                if isinstance(idx_res, slice):
                    idx = idx_res.start
                elif hasattr(idx_res, '__iter__'): 
                    idx = idx_res[0]
                else:
                    idx = idx_res
            
            # Fallback: 如果是今天但 index 里还没刷出来，强制用最后一根
            if idx == -1:
                today_str = datetime.now().strftime("%Y-%m-%d")
                if add_date == today_str:
                    idx = len(day_df) - 1
            
            if idx != -1:
                # 获取坐标
                try: 
                    x_pos = x_axis[idx] 
                except:
                    x_pos = idx
                
                price = item.add_price
                
                # 更新位置并显示
                line_len = 12
                x_end = x_pos + line_len
                self.hotspot_line_p.setData(x=[x_pos, x_end], y=[price, price])
                self.hotspot_line_p.show()

                msg = f'<div style="color: #FF4500; font-weight: bold; font-size: 9pt;">¥{price:.2f}</div>'
                self.hotspot_label_p.setHtml(msg)
                self.hotspot_label_p.setPos(x_pos, price)
                self.hotspot_label_p.show()

                self.hotspot_marker_p.setPos(x_pos, price)
                self.hotspot_marker_p.show()
                
        except Exception as e:
            logger.debug(f"Draw hotspot marker error: {e}")


    def _draw_signal_annotation(self, code, x_axis, day_df):
        """在 K 线图上绘制被点击的信号标注 - 复用对象版"""
        # 1. 初始化持久项
        if not hasattr(self, 'anno_arrow_p'):
            self.anno_arrow_p = pg.ArrowItem(angle=90, tipAngle=30, baseAngle=20, headLen=15, tailLen=10, tailWidth=5, pen={'color': 'w', 'width': 1})
            self.anno_label_p = pg.TextItem(anchor=(0.5, 0))
            self.kline_plot.addItem(self.anno_arrow_p)
            self.kline_plot.addItem(self.anno_label_p)
            
            def on_click(event):
                self.show_supervision_details()
            self.anno_arrow_p.mouseClickEvent = on_click
            self.anno_label_p.mouseClickEvent = on_click
            
        # 默认隐藏
        self.anno_arrow_p.hide()
        self.anno_label_p.hide()
        
        # 检查是否有激活的信号上下文，并且代码匹配
        if not hasattr(self, 'active_signal_context') or not self.active_signal_context:
            return
            
        ctx = self.active_signal_context
        if ctx.get('code') != code:
            return
            
        try:
            # 定位到最后一根 K 线
            idx = len(day_df) - 1
            if idx < 0: return
            
            # 获取坐标
            try:
                x_pos = x_axis[idx]
            except:
                x_pos = idx
                
            row = day_df.iloc[idx]
            high_val = row['high']
            low_val = row['low']
            
            pattern = ctx.get('pattern', 'SIGNAL')
            message = ctx.get('message', '')
            
            short_msg = pattern
            if "卖出" in message:
                short_msg = "卖出"
            elif "买入" in message:
                short_msg = "买入"
            
            is_sell = "卖出" in message or "高开" in pattern or "回落" in pattern
            
            if is_sell:
                anchor_y = high_val
                self.anno_arrow_p.setStyle(angle=-90, brush='g')
                self.anno_arrow_p.setPos(x_pos, anchor_y)
                
                label_html = f'<div style="color: #00FF00; font-weight: bold; font-size: 10pt;">{short_msg}</div>'
                self.anno_label_p.setHtml(label_html)
                self.anno_label_p.setAnchor((0.5, 1))
                self.anno_label_p.setPos(x_pos, anchor_y + (high_val * 0.01))
            else:
                anchor_y = low_val
                self.anno_arrow_p.setStyle(angle=90, brush='r')
                self.anno_arrow_p.setPos(x_pos, anchor_y)
                
                label_html = f'<div style="color: #FF0000; font-weight: bold; font-size: 10pt;">{short_msg}</div>'
                self.anno_label_p.setHtml(label_html)
                self.anno_label_p.setAnchor((0.5, 0))
                self.anno_label_p.setPos(x_pos, anchor_y - (low_val * 0.01))

            self.anno_arrow_p.show()
            self.anno_label_p.show()
            logger.debug(f"[Annotation] Updated signal annotation for {code}: {short_msg}")
            
        except Exception as e:
            logger.error(f"Failed to draw signal annotation: {e}")


    def _clear_hotspot_markers(self):
        """清理旧的热点标记 - 仅隐藏版本"""
        if hasattr(self, 'hotspot_line_p'):
            self.hotspot_line_p.hide()
            self.hotspot_label_p.hide()
            self.hotspot_marker_p.hide()


    def _clear_follow_markers(self):
        """清理旧的跟单标记 - 仅隐藏版本"""
        if hasattr(self, 'follow_line_p'):
            self.follow_line_p.hide()
            self.follow_label_p.hide()
            self.follow_marker_p.hide()
        if hasattr(self, 'exit_line_p'):
            self.exit_line_p.hide()
            self.exit_label_p.hide()
            self.exit_marker_p.hide()


    def _get_follow_signals(self, code, day_df) -> list[SignalPoint]:
        """获取跟单信号点列表 (Follow/Exit)"""
        signals = []
        try:
            import sqlite3
            conn = sqlite3.connect("signal_strategy.db", timeout=5)
            c = conn.cursor()
            c.execute("""
                SELECT detected_date, exit_date, detected_price, exit_price, status
                FROM follow_queue
                WHERE code = ?
                ORDER BY detected_date DESC
                LIMIT 1
            """, (code[:6],))
            row = c.fetchone()
            conn.close()
            
            if not row:
                # 降级处理：仅当明确请求 follow 类型时显示
                if getattr(self, 'current_signal_type', None) == 'follow' and getattr(self, 'current_signal_date', None):
                    t_date = self.current_signal_date
                    idx = self._find_date_index(day_df, t_date)
                    if idx != -1:
                        price = day_df['close'].iloc[idx]
                        signals.append(SignalPoint(
                            code=code, timestamp=t_date, bar_index=idx, price=price,
                            signal_type=SignalType.FOLLOW, reason="Follow Entry (Manual)"
                        ))
                return signals

            detected_date, exit_date, detected_price, exit_price, status = row
            
            # 1. Follow Entry
            if detected_date:
                idx = self._find_date_index(day_df, detected_date)
                if idx != -1:
                     # Use detected_price if available, else close
                    price = detected_price if detected_price else day_df['close'].iloc[idx]
                    signals.append(SignalPoint(
                        code=code, timestamp=detected_date, bar_index=idx, price=price,
                        signal_type=SignalType.FOLLOW, reason="Follow Entry"
                    ))

            # 2. Exit
            if exit_date and status == "EXITED":
                idx = self._find_date_index(day_df, exit_date)
                if idx != -1:
                    price = exit_price if exit_price else day_df['close'].iloc[idx]
                    signals.append(SignalPoint(
                        code=code, timestamp=exit_date, bar_index=idx, price=price,
                        signal_type=SignalType.EXIT_FOLLOW, reason="Follow Exit"
                    ))
                    
        except Exception as e:
            logger.debug(f"Get follow signals error: {e}")
            
        return signals

    def _draw_follow_lines(self, code, day_df):
        """仅绘制跟单的价格参考线 (虚线)"""
        # 清理旧线
        for attr in ['follow_line_p', 'exit_line_p']:
             if hasattr(self, attr): getattr(self, attr).hide()
        
        # 复用逻辑获取数据，只画线
        try:
             import sqlite3
             conn = sqlite3.connect("signal_strategy.db", timeout=5)
             row = conn.execute("SELECT detected_date, exit_date, detected_price, exit_price, status FROM follow_queue WHERE code=? ORDER BY detected_date DESC LIMIT 1", (code[:6],)).fetchone()
             conn.close()
             
             if not row: return

             detected_date, exit_date, detected_price, exit_price, status = row
             
             # Entry Line
             if detected_date:
                 self._draw_single_line(day_df, detected_date, detected_price, 'follow', '#FFD700')
             
             # Exit Line
             if exit_date and status == "EXITED":
                 self._draw_single_line(day_df, exit_date, exit_price, 'exit', '#FF4500')
                 
        except Exception:
            pass

    def _get_watchlist_signals(self, code, day_df) -> list[SignalPoint]:
        """获取观察池信号标记 (WATCH)"""
        signals = []
        try:
            # 1. 优先处理显式传递的上下文 (来自双击/联动)
            if getattr(self, 'current_signal_type', None) == 'watchlist' and getattr(self, 'current_signal_date', None):
                t_date = self.current_signal_date
                idx = self._find_date_index(day_df, t_date)
                if idx != -1:
                    price = day_df['close'].iloc[idx]
                    signals.append(SignalPoint(
                        code=code, timestamp=t_date, bar_index=idx, price=price,
                        signal_type=SignalType.WATCH, reason="Watchlist Trigger (Context)"
                    ))
                return signals

            # 2. 数据库回溯 (兜底显示)
            import sqlite3
            db_path = "signal_strategy.db"
            if not os.path.exists(db_path):
                return signals
                
            conn = sqlite3.connect(db_path, timeout=5)
            c = conn.cursor()
            c.execute("""
                SELECT discover_date, discover_price 
                FROM hot_stock_watchlist 
                WHERE code = ? AND validation_status != 'DROPPED'
                ORDER BY discover_date DESC LIMIT 1
            """, (code[:6],))
            row = c.fetchone()
            conn.close()
            
            if row:
                d_date, d_price = row
                if d_date:
                    idx = self._find_date_index(day_df, d_date)
                    if idx != -1:
                        price = d_price if d_price else day_df['close'].iloc[idx]
                        signals.append(SignalPoint(
                            code=code, timestamp=d_date, bar_index=idx, price=price,
                            signal_type=SignalType.WATCH, reason="Watchlist Discovery"
                        ))
        except Exception as e:
            logger.debug(f"Error getting watchlist signals: {e}")
        return signals

    def _draw_single_line(self, day_df, target_date, price, prefix, color):
        idx = self._find_date_index(day_df, target_date)
        if idx == -1: return
        
        if not price: price = day_df['close'].iloc[idx]
        
        attr_line = f'{prefix}_line_p'
        if not hasattr(self, attr_line):
            setattr(self, attr_line, pg.PlotCurveItem(pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)))
            self.kline_plot.addItem(getattr(self, attr_line))
            
        line_item = getattr(self, attr_line)
        line_item.setData(x=[idx, idx + 15], y=[price, price])
        line_item.show()

    def _find_date_index(self, day_df, target_date):
        """Helper to find date index"""
        if ' ' in target_date: target_date = target_date.split(' ')[0]
        # Optimize: Check exact match first
        if target_date in day_df.index:
            res = day_df.index.get_loc(target_date)
            if isinstance(res, slice):
                return int(res.start) if res.start is not None else 0
            elif isinstance(res, (np.ndarray, list)):
                # 如果是 array, 返回第一个索引
                if len(res) > 0:
                    if hasattr(res, 'dtype') and res.dtype == bool:
                        return int(np.flatnonzero(res)[0]) if np.any(res) else -1
                    return int(res[0])
                return -1
            return int(res)
            
        # Fallback to string search
        for i, d_str in enumerate(day_df.index):
            if target_date in str(d_str):
                return i
        
        # Current day fallback
        if target_date == datetime.now().strftime("%Y-%m-%d"):
            return len(day_df) - 1
        return -1

    def _clear_follow_markers(self):
        """清理跟单相关的线和标记 (Compatibility wrapper)"""
        for attr in ['follow_line_p', 'exit_line_p']:
            if hasattr(self, attr): getattr(self, attr).hide()


    def _clear_price_gaps(self):
        pass # ... existing code ...
        """清理价格缺口 - 仅隐藏版本"""
        if hasattr(self, 'gap_items_pool'):
            for item in self.gap_items_pool:
                item.setVisible(False)


    def _draw_price_gaps(self, x_axis, day_df):
        """在 K 线图上绘制最近 5 个跳空缺口 - 对象池版"""
        if not hasattr(self, 'gap_items_pool'):
            self.gap_items_pool = []
            for _ in range(10):
                item = pg.QtWidgets.QGraphicsRectItem()
                item.setPen(pg.mkPen(None))
                item.setBrush(pg.mkBrush(pg.mkColor(190, 190, 190, 90)))
                item.setVisible(False)
                self.kline_plot.addItem(item)
                self.gap_items_pool.append(item)
        
        self._clear_price_gaps()

        if len(day_df) < 2: return

        try:
            highs, lows = day_df['high'].values, day_df['low'].values
            total = len(day_df)
            found_gaps = []
            scan_start = max(1, total - 20)

            for i in range(scan_start, total):
                prev_high, prev_low = highs[i-1], lows[i-1]
                curr_high, curr_low = highs[i], lows[i]
                
                if curr_low > prev_high:
                    gap_start_p, gap_end_p = prev_high, curr_low
                elif curr_high < prev_low:
                    gap_start_p, gap_end_p = curr_high, prev_low 
                else: continue
                
                found_gaps.append((i, gap_start_p, gap_end_p))
            
            targets = found_gaps[-5:]
            for i, (idx, low, high) in enumerate(targets):
                if i >= len(self.gap_items_pool): break
                x_start = x_axis[idx] - 0.4
                x_end = len(day_df) + 500 
                item = self.gap_items_pool[i]
                item.setRect(x_start, low, x_end - x_start, high - low)
                item.setVisible(True)

        except Exception as e:
            logger.error(f"Draw price gaps error: {e}")


    def _install_viewbox_guard(self, plot: pg.PlotItem):
        vb = plot.getViewBox()
        
        def on_range_changed(vb_self, range):
            # 强制锁定 X 轴
            vb_self.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
            # Y 轴保持自动
            vb_self.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        
        # 连接一次，后续 addItem 不会破坏这个 hook
        vb.sigRangeChanged.connect(on_range_changed)

    def _check_market_gaps(self):
        """
        全市场跳空缺口探测 (向量化优化)
        """
        try:
            if not hasattr(self, 'df_all') or self.df_all.empty:
                return
            # 仅检查当天产生缺口的股票
            # 需要遍历 df_all 中的股票，但在主线程全量遍历太慢
            # 策略：
            # 1. 仅对 "关注" 或 "持仓" 列表里的？不行，用户要求自动加入热点
            # 2. 既然是增量检测，能否只检测最近更新的？
            #    Monitor 传来的 df_all 通常是全量的。
            # 3. 简化方案：遍历 df_all，但只对前 N 个活跃股？或者只对涨跌幅较大的？
            #    跳空通常伴随较大幅度。
            #    或者：直接 iterate all，只要逻辑够快。
            
            # --- 阶段 1: 向量化筛选 ---
            df = self.df_all.copy()
            if not all(col in df.columns for col in ['low', 'high', 'pre_close']):
                return

            # 疑似跳空高开 (启动动能)
            mask_up = (df['low'] > df['pre_close'] * 1.005) & (df['pct_chg'] > 0)
            # 疑似跳空低开 (卖出动能/风险)
            mask_down = (df['high'] < df['pre_close'] * 0.995) & (df['pct_chg'] < 0)

            up_candidates = df[mask_up]
            down_candidates = df[mask_down]

            if up_candidates.empty and down_candidates.empty:
                return

            # --- 阶段 2: 逻辑处理与自动跟进 ---
            hub = get_trading_hub()
            sig_queue = SignalMessageQueue()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            date_today = datetime.now().strftime("%Y-%m-%d")

            # 处理高开 (启动动能)
            for code, row in up_candidates.iterrows():
                code_str = str(code).zfill(6)
                name = str(row.get('name', ''))
                price = float(row.get('price', 0))
                
                # 1. 加入热点面板 (缺口跟踪组)
                if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
                    self.hotlist_panel.add_stock(code_str, name, price, signal_type="跳空高开", group="缺口跟踪")
                
                # 2. 自动加入跟单队列 (Follow Queue)
                follow_sig = TrackedSignal(
                    code=code_str,
                    name=name,
                    signal_type="跳空启动",
                    detected_date=date_today,
                    detected_price=price,
                    entry_strategy="竞价买入",
                    priority=9,
                    source="GAP_SCAN",
                    notes=f"向量化扫描: 跳空启动 Low:{row['low']} > Pre:{row['pre_close']}"
                )
                hub.add_to_follow_queue(follow_sig)

                # 3. 推送高优先级报警消息
                msg = SignalMessage(
                    priority=20, 
                    timestamp=timestamp,
                    code=code_str,
                    name=name,
                    signal_type="向上跳空",
                    source="LiveStrategy",
                    reason=f"启动动能强劲 (涨幅:{row['pct_chg']:.1f}%)",
                    score=90
                )
                sig_queue.push(msg)

            # 处理低开 (风险/卖出动能)
            for code, row in down_candidates.iterrows():
                code_str = str(code).zfill(6)
                name = str(row.get('name', ''))
                price = float(row.get('price', 0))

                # 1. 推送卖出动能报警
                msg = SignalMessage(
                    priority=15, 
                    timestamp=timestamp,
                    code=code_str,
                    name=name,
                    signal_type="向下跳空",
                    source="LiveStrategy",
                    reason=f"卖出动能! 向下跳空风险 (跌幅:{row['pct_chg']:.1f}%)",
                    score=95
                )
                sig_queue.push(msg)

            self._update_signal_badge()

        except Exception as e:
            logger.error(f"[_check_market_gaps] Error: {e}")

    def render_charts(self, code, day_df, tick_df):
        """
        渲染完整图表...
        """
        # print(f'self.right_splitter.count():{self.right_splitter.count()}\n')
        
        if day_df.empty:
            # [FIX] 只有当 code 发生变化且数据为空时才彻底清理。
            # 如果是同一只股由于某种原因触发了空渲染，我们选择保留旧图，防止“闪没”
            if self.current_day_df_code != code:
                self.kline_plot.setTitle(f"{code} - No Data")
                self.tick_plot.setTitle("No Tick Data")
                # 清理旧图形，防止切股后还有残留
                self.kline_plot.clear()
            self.tick_plot.clear()
            if hasattr(self, 'volume_plot'):
                self.volume_plot.clear()
            # 清除缓存的 Items
            for attr in ['candle_item', 'date_axis', 'vol_up_item', 'vol_down_item',
                        'ma5_curve', 'ma10_curve', 'ma20_curve','ma60_curve', 'upper_curve', 'lower_curve',
                        'vol_ma5_curve', 'signal_scatter', 'tick_curve', 'avg_curve', 'pre_close_line', 'ghost_candle']:
                if hasattr(self, attr):
                    delattr(self, attr)
            return

        # --- 标题 (含监理看板) ---
        self._update_plot_title(code, day_df, tick_df)

        # --- 主题颜色 ---
        if self.qt_theme == 'dark':
            # ma_colors = {'ma5':'b','ma10':'orange','ma20':QColor(255,255,0),'ma60':QColor(0, 180, 255)}
            ma_colors = {
                   'ma5': QColor(0, 255, 0),          # ✅ 亮绿色（改这里）
                   'ma10': QColor(255, 165, 0),        # orange
                   'ma20': QColor(255, 255, 0),        # yellow
                   'ma60': QColor(0, 180, 255)         # cyan-blue
               }
            # bollinger_colors = {'upper':QColor(139,0,0),'lower':QColor(0,128,0)}
            bollinger_colors = {
                    'upper': QColor(220, 20, 60),       # Crimson Red（比 139,0,0 更清晰）
                    'lower': QColor(0, 200, 120)        # 明亮绿
               }

            vol_ma_color = QColor(255,255,0)
            tick_curve_color = 'w'
            tick_avg_color = QColor(255,255,0)
            # pre_close_color = '#FF0000' # Bright Red for Yesterday's Close
            pre_close_color = '#FF4040'             # 柔亮红（不刺眼）
        else:
            ma_colors = {
                'ma5': QColor(0, 200, 0),            # ✅ 亮绿但不刺眼
                'ma10': QColor(255, 140, 0),          # Dark Orange
                'ma20': QColor(255, 165, 0),          # Orange
                'ma60': QColor(0, 120, 255)           # 深蓝
            }

            bollinger_colors = {
                'upper': QColor(200, 0, 0),
                'lower': QColor(0, 150, 0)
            }

            vol_ma_color = QColor(255, 140, 0)
            tick_curve_color = 'k'
            tick_avg_color = QColor(255, 140, 0)
            pre_close_color = '#FF0000'

        day_df = _normalize_dataframe(day_df)

        if 'date' in day_df.columns:
            day_df = day_df.set_index('date')
        logger.debug(f'day_df.index:\n {day_df.index[-3:]}')
        day_df = day_df.sort_index()
        
        # ⚡ [DEBUG] Check OHLC data integrity
        try:
            if not day_df.empty:
                cols_to_check = [c for c in ['open', 'close', 'high', 'low'] if c in day_df.columns]
                tail_data = day_df[cols_to_check].tail(3)
                logger.debug(f"[RT] day_df OHLC tail:\n{tail_data}")
                if day_df[cols_to_check].isnull().values.any():
                    logger.warning(f"[RT] day_df contains NaNs:\n{day_df[cols_to_check].isnull().sum()}")
        except Exception as e:
            logger.error(f"[RT] Error inspecting day_df: {e}")
        # day_df.index = day_df.index.normalize()   # 去掉时间
        dates = day_df.index
        x_axis = np.arange(len(day_df))

        # ----------------- 设置底部轴 -----------------
        if not hasattr(self, 'date_axis'):
            self.date_axis = DateAxis(day_df.index, orientation='bottom')
            self.kline_plot.setAxisItems({'bottom': self.date_axis})
        else:
            self.date_axis.updateDates(day_df.index)

        # --- Candlestick ---
        ohlc_data = np.column_stack((
            x_axis,
            day_df['open'].values,
            day_df['close'].values,
            day_df['low'].values,
            day_df['high'].values
        ))

        if not hasattr(self, 'candle_item') or self.candle_item not in self.kline_plot.items:
            self.candle_item = CandlestickItem(ohlc_data, theme=self.qt_theme)
            self.kline_plot.addItem(self.candle_item)
        else:
            self.candle_item.setTheme(self.qt_theme)
            self.candle_item.setData(ohlc_data)

        # --- MA5 / MA10 / MA20 / MA60 ---
        ma5  = day_df['close'].rolling(5).mean().values
        ma10 = day_df['close'].rolling(10).mean().values
        # ma20 = day_df['close'].rolling(20).mean().values
        # ma60 = day_df['close'].rolling(60).mean().values
        # ma20 = day_df['close'].ewm(span=26, adjust=False).mean().values
        # ma60 = day_df['close'].ewm(span=60, adjust=False).mean().values
        ma20 = tdd.ema_tdx_numpy(day_df['close'], timeperiod=26)
        ma60 = tdd.ema_tdx_numpy(day_df['close'], timeperiod=60)
        # MA60 颜色：亮蓝色（深浅主题都清晰）
        # ma60_color = QColor(0, 180, 255)

        ma_defs = [
            ('ma5_curve',  ma5,  ma_colors['ma5'],  QtCore.Qt.PenStyle.SolidLine),
            ('ma10_curve', ma10, ma_colors['ma10'], QtCore.Qt.PenStyle.SolidLine),
            ('ma20_curve', ma20, ma_colors['ma20'], QtCore.Qt.PenStyle.SolidLine),
            ('ma60_curve', ma60, ma_colors['ma60'], QtCore.Qt.PenStyle.DashLine),
        ]

        for attr, series, color, style in ma_defs:
            pen = pg.mkPen(color, width=1, style=style)

            if not hasattr(self, attr) or getattr(self, attr) not in self.kline_plot.items:
                setattr(self, attr, self.kline_plot.plot(x_axis, series, pen=pen))
            else:
                curve = getattr(self, attr)
                curve.setData(x_axis, series)
                curve.setPen(pen)



        # --- Bollinger ---
        std20 = day_df['close'].rolling(20).std().values
        upper_band = ma20 + 2*std20
        lower_band = ma20 - 2*std20

        for attr, series, color in [('upper_curve', upper_band, bollinger_colors['upper']),
                                    ('lower_curve', lower_band, bollinger_colors['lower'])]:
            if not hasattr(self, attr) or getattr(self, attr) not in self.kline_plot.items:
                setattr(self, attr, self.kline_plot.plot(x_axis, series, pen=pg.mkPen(color, width=2)))
            else:
                getattr(self, attr).setData(x_axis, series)
                getattr(self, attr).setPen(pg.mkPen(color, width=2))

        # 仅在开关开启时绘制
        if getattr(self, 'show_td_sequential', True):

            # --- TD Sequential (神奇九转) ---
            try:
                from JSONData.tdx_data_Day import td_sequential_fast

                # 1️⃣ 计算 TD Sequential（完整历史）
                with timed_ctx("td_sequential_fast", warn_ms=100):
                    df_td = td_sequential_fast(day_df)

                # 2️⃣ 初始化对象池（第一次调用）
                if not hasattr(self, 'td_text_pool'):
                    self.td_text_pool = []

                    # 字体缓存
                    self.td_font_9 = QtGui.QFont('Arial', 14, QtGui.QFont.Weight.Bold)
                    self.td_font_7p = QtGui.QFont('Arial', 12, QtGui.QFont.Weight.Bold)
                    self.td_font_norm = QtGui.QFont('Arial', 11, QtGui.QFont.Weight.Normal)

                    # 预创建 TextItem，最大 50 个
                    for _ in range(50):
                        t = pg.TextItem('', anchor=(0.5, 1))
                        t.hide()
                        self.kline_plot.addItem(t)
                        self.td_text_pool.append(t)

                # 3️⃣ 仅在开关开启时绘制
                if not getattr(self, 'show_td_sequential', True):
                    # TD 关闭时，全部隐藏
                    for t in self.td_text_pool:
                        t.hide()
                    return

                # 4️⃣ 只显示最近 30 根 K
                N = 30
                total = len(df_td)
                start = max(0, total - N)

                # 5️⃣ 预取 numpy 避免 iloc
                buy = df_td['td_buy_count'].values
                sell = df_td['td_sell_count'].values
                highs = day_df['high'].values

                # 6️⃣ 对象池绘制
                pool = self.td_text_pool
                pool_idx = 0

                # 先隐藏全部
                for t in pool:
                    t.hide()

                with timed_ctx("draw_td_sequential", warn_ms=40):
                    for i in range(start, total):
                        buy_cnt = buy[i]
                        sell_cnt = sell[i]

                        if buy_cnt == 0 and sell_cnt == 0:
                            continue
                        if pool_idx >= len(pool):
                            break

                        t = pool[pool_idx]
                        pool_idx += 1

                        # 判断是 buy 还是 sell
                        if buy_cnt > 0:
                            td_cnt = buy_cnt
                            # buy 用黄色系
                            if td_cnt == 9:
                                t.setColor('#FFFF00')      # 明黄色，买入信号
                                t.setFont(self.td_font_9)
                            elif td_cnt >= 7:
                                t.setColor('#FFD700')      # 金黄色，买入强势
                                t.setFont(self.td_font_7p)
                            else:
                                t.setColor('#E6C200')      # 深黄色，买入弱势
                                t.setFont(self.td_font_norm)

                        else:
                            td_cnt = sell_cnt
                            # sell 用绿色系
                            if td_cnt == 9:
                                t.setColor('#00FF00')      # 明绿色，卖出信号
                                t.setFont(self.td_font_9)
                            elif td_cnt >= 7:
                                t.setColor('#32CD32')      # 亮绿色，卖出强势
                                t.setFont(self.td_font_7p)
                            else:
                                t.setColor('#228B22')      # 深绿色，卖出弱势
                                t.setFont(self.td_font_norm)

                        t.setText(str(td_cnt))
                        t.setPos(x_axis[i], highs[i] * 1.008)
                        t.show()

            except Exception as e:
                logger.debug(f"TD Sequential display error: {e}")

        # [NEW] 绘制跳空缺口 (最近 5 个)
        self._draw_price_gaps(x_axis, day_df)


        # ----------------- 绘制 Volume -----------------
        if 'amount' in day_df.columns:
            if not hasattr(self, 'volume_plot'):
                # [FIX] Volume 使用 DateAxis
                self.vol_date_axis = DateAxis(day_df.index, orientation='bottom')
                self.volume_plot = self.kline_widget.addPlot(row=1, col=0, axisItems={'bottom': self.vol_date_axis})
                self.volume_plot.setXLink(self.kline_plot)
                self.volume_plot.setMaximumHeight(85)
                self.volume_plot.setLabel('left', 'Volume')
                self.volume_plot.showGrid(x=True, y=True)
                self.volume_plot.setMenuEnabled(False)
            else:
                # 更新 Volume 的日期轴
                if hasattr(self, 'vol_date_axis'):
                    self.vol_date_axis.updateDates(day_df.index)

            # 重要：不使用 clear()，而是复用 BarGraphItem
            amounts = day_df['amount'].values
            up_idx = day_df['close'] >= day_df['open']
            down_idx = day_df['close'] < day_df['open']

            x_vol = x_axis

            # 处理上涨柱
            if up_idx.any():
                if not hasattr(self, 'vol_up_item') or self.vol_up_item not in self.volume_plot.items:
                    self.vol_up_item = pg.BarGraphItem(x=x_vol[up_idx], height=amounts[up_idx], width=0.6, brush='r')
                    self.volume_plot.addItem(self.vol_up_item)
                else:
                    self.vol_up_item.setOpts(x=x_vol[up_idx], height=amounts[up_idx], width=0.6, brush='r')
            elif hasattr(self, 'vol_up_item'):
                self.vol_up_item.setOpts(x=[], height=[], width=0.6)

            # 处理下跌柱
            if down_idx.any():
                if not hasattr(self, 'vol_down_item') or self.vol_down_item not in self.volume_plot.items:
                    self.vol_down_item = pg.BarGraphItem(x=x_vol[down_idx], height=amounts[down_idx], width=0.6, brush='g')
                    self.volume_plot.addItem(self.vol_down_item)
                else:
                    self.vol_down_item.setOpts(x=x_vol[down_idx], height=amounts[down_idx], width=0.6, brush='g')
            elif hasattr(self, 'vol_down_item'):
                self.vol_down_item.setOpts(x=[], height=[], width=0.6)

            # 5日均量线
            ma5_vol = pd.Series(amounts).rolling(5).mean().values
            if not hasattr(self, 'vol_ma5_curve') or self.vol_ma5_curve not in self.volume_plot.items:
                self.vol_ma5_curve = self.volume_plot.plot(x_axis, ma5_vol, pen=pg.mkPen(vol_ma_color, width=1.5))
            else:
                self.vol_ma5_curve.setData(x_axis, ma5_vol)
                self.vol_ma5_curve.setPen(pg.mkPen(vol_ma_color, width=1.5))

        # --- [升级] 信号标记渲染 ---
        self.signal_overlay.clear()
        kline_signals = []

        # 1. 历史模拟信号 (优化版：只处理最近 50 行)
        if self.show_strategy_simulation:
            with timed_ctx("_run_strategy_simulation_signal", warn_ms=50):
                kline_signals.extend(self._run_strategy_simulation_new50(code, day_df, n_rows=50))

        # 2. 实盘日志历史信号 (CSV) - 引入缓存优化
        import time
        now_ts = time.time()
        # 每 30 秒重新加载一次历史信号 CSV
        if now_ts - getattr(self, '_hist_df_last_load', 0) > 30:
            with timed_ctx("get_signal_history_df", warn_ms=50):
                self._hist_df_cache = self.logger.get_signal_history_df()
                if not self._hist_df_cache.empty:
                    self._hist_df_cache['code'] = self._hist_df_cache['code'].astype(str)
                self._hist_df_last_load = now_ts
        
        hist_df = self._hist_df_cache
        if not hist_df.empty:
            stock_signals = hist_df[hist_df['code'] == str(code)]
            
            # 性能优化：缓存 date_map
            cache_dates_key = (code, len(dates), dates[-1] if len(dates)>0 else "")
            if getattr(self, "_last_dates_cache_key", None) != cache_dates_key:
                self._cached_date_map = {d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i for i, d in enumerate(dates)}
                self._last_dates_cache_key = cache_dates_key
            
            date_map = self._cached_date_map
            
            # 使用 itertuples 替代 iterrows，速度提升约 10 倍
            for row in stock_signals.itertuples(index=False):
                # row 属性对应 DataFrame 列名，如果没有列名则按位置
                # 假设列顺序已知或通过 getattr 安全获取
                sig_date = str(row.date).split()[0]
                if sig_date in date_map:
                    idx = date_map[sig_date]
                    y_p = row.price if pd.notnull(row.price) else day_df.iloc[idx]['close']
                    action = str(row.action)
                    reason = str(row.reason)
                    
                    is_buy = 'Buy' in action or '买' in action or 'ADD' in action
                    stype = SignalType.BUY if is_buy else SignalType.SELL
                    if "VETO" in action: stype = SignalType.VETO
                    source = SignalSource.SHADOW_ENGINE if "SHADOW" in action else SignalSource.STRATEGY_ENGINE

                    kline_signals.append(SignalPoint(
                        code=code, timestamp=sig_date, bar_index=idx, price=y_p,
                        signal_type=stype, source=source, reason=reason,
                        debug_info=getattr(row, 'indicators', {})
                    ))

        # 3. 实时影子信号 (K线占位图标)
        # [FIX] 无论什么条件，必须有实时数据才能激活实时模式，否则无法获取最新价格导致 Crash
        is_realtime_active = (self.realtime or cct.get_work_time_duration() or self._debug_realtime) and tick_df is not None and not tick_df.empty
        
        if is_realtime_active:
            with timed_ctx("_run_realtime_strategy", warn_ms=100):
                shadow_decision = self._run_realtime_strategy(code, day_df, tick_df)
                if shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                    # 优先使用 close, 其次 trade, 最后 price
                    price_col = 'close' if 'close' in tick_df.columns else ('trade' if 'trade' in tick_df.columns else 'price')
                    y_p = float(tick_df[price_col].iloc[-1]) if price_col in tick_df.columns else 0
                    # 当前 K 线索引是 dates 长度（即下一根未收盘的 K 线）
                    kline_signals.append(SignalPoint(
                        code=code, timestamp="REALTIME", bar_index=len(dates), price=y_p,
                        signal_type=SignalType.BUY if '买' in shadow_decision['action'] or 'ADD' in shadow_decision['action'] else SignalType.SELL,
                        source=SignalSource.SHADOW_ENGINE,
                        reason=shadow_decision['reason'],
                        debug_info=shadow_decision.get('debug', {})
                    ))
                    self.last_shadow_decision = shadow_decision # 存储供简报使用

        # 4. Follow Queue Signals (Integrated)
        follow_signals = self._get_follow_signals(code, day_df)
        if follow_signals:
             kline_signals.extend(follow_signals)
             
        # 5. Watchlist Discovery Signals (Integrated)
        watch_signals = self._get_watchlist_signals(code, day_df)
        if watch_signals:
            kline_signals.extend(watch_signals)

        # 6. ⚡ [NEW] Structural Breakout Champion (SBC) Signals
        # TODO: 以后将 sbc_tracker/baseline_loader 等都收纳到 sbc_core 内部
        self.all_today_sbc_signals = []
        if tick_df is not None and not tick_df.empty and self.show_strategy_simulation:
            with timed_ctx("sbc_core_analysis", warn_ms=100):
                try:
                    # 委托 sbc_core 进行高性能批量分析
                    sbc_results = sbc_core.run_sbc_analysis_core(code, day_df, tick_df, verbose=True)
                    self.all_today_sbc_signals = sbc_results.get("signals", [])
                    # ⭐ [FIX] 立即刷新视觉层数据
                    self.signal_overlay.update_signals(self.all_today_sbc_signals, target='tick')
                except Exception as e:
                    logger.debug(f"SBC integration error: {e}")
        else:
            # 性能优化：如果不显示或没数据，确保旧信号被清理
            self.signal_overlay.update_signals([], target='tick')

        # 执行 K 线绘图 (计算视觉偏移)
        self.current_kline_signals = kline_signals # ⭐ 保存信号供十字光标显示 (1.3)
        
        y_visuals = []
        for sig in kline_signals:
            is_buy = sig.signal_type in (SignalType.BUY, SignalType.ADD, SignalType.SHADOW_BUY, SignalType.FOLLOW, SignalType.WATCH)
            
            # 保护:确保 bar_index 是整数而不是 slice
            bar_idx = sig.bar_index
            if isinstance(bar_idx, slice):
                bar_idx = int(bar_idx.start) if bar_idx.start is not None else 0
                sig.bar_index = bar_idx # ⚡ [FIX] 同步修正对象内的索引，防止下游 update_signals 崩溃
            else:
                bar_idx = int(bar_idx)
                sig.bar_index = bar_idx
            
            # 1. 历史 K 线信号
            if bar_idx < len(day_df):
                row = day_df.iloc[bar_idx]
                y_low = row['low']
                y_high = row['high']
                if is_buy:
                    # 价格标签在低价下方 1.5%，防止悬空
                    y_v = y_low * 0.985
                else:
                    # 价格标签在高价上方 1.5%
                    y_v = y_high * 1.015
            else:
                # 2. 实时幽灵 K 线信号 (Ghost Candle)
                if not tick_df.empty:
                    # [FIX] Use safe column access
                    p_col = 'close' if 'close' in tick_df.columns else ('trade' if 'trade' in tick_df.columns else 'price')
                    current_p = float(tick_df[p_col].iloc[-1]) if p_col in tick_df.columns else sig.price
                    
                    h_col = 'high' if 'high' in tick_df.columns else p_col
                    l_col = 'low' if 'low' in tick_df.columns else p_col
                    
                    high_p = tick_df[h_col].max() if h_col in tick_df.columns else current_p
                    low_p = tick_df[l_col].min() if l_col in tick_df.columns else current_p
                else:
                    current_p = sig.price
                    high_p = sig.price
                    low_p = sig.price
                
                if is_buy:
                    y_v = low_p * 0.985
                else:
                    y_v = high_p * 1.015
            y_visuals.append(y_v)

        self.signal_overlay.update_signals(kline_signals, target='kline', y_visuals=y_visuals)

        # -------------------------
        # 移除此处的 sensing_bar 设置，改到 intraday 内容设置之后
        # -------------------------

        # --- Ghost Candle (实时占位) ---
        logger.debug(f'is_realtime_active: {is_realtime_active} tick_df keys:{tick_df.keys() if tick_df is not None and not tick_df.empty else "None"}')
        if is_realtime_active:
            # [FIX] Safe column choice
            price_col = 'close' if 'close' in tick_df.columns else ('trade' if 'trade' in tick_df.columns else 'price')
            
            if price_col not in tick_df.columns:
                logger.error(f"Tick DF missing price column. Columns: {tick_df.columns}")
                return # Abort drawing ghost candle if no data
                
            current_price = float(tick_df[price_col].iloc[-1])

            last_hist_date = str(day_df.index[-1]).split()[0]
            today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
            last_trade_date = cct.get_last_trade_date()

            # [FIX] strict check for trading day
            # If not a trading day, do not draw ghost candle
            # is_trade_day = cct.get_trade_date_status()

            # 是否需要画“幽灵K线”（今日尚未入库）
            # last_hist_dt = pd.to_datetime(day_df.index[-1]).date()
            # last_trade_dt= pd.to_datetime(cct.get_last_trade_date()).date()
            # need_ghost_bar = last_hist_dt < last_trade_dt

            need_ghost_bar = self._need_ghost_bar(day_df)
            if not need_ghost_bar:
                if hasattr(self, 'ghost_candle'):
                    self.kline_plot.removeItem(self.ghost_candle)
                    delattr(self, 'ghost_candle')
            elif today_str > last_hist_date:
                new_x = len(day_df)
                
                # [FIX] 增强实时 OHLC 字段获取，防止 T 字形 K 线 (Open=Close)
                # 统一从 tick_df 获取日线级别的 OHLC（如果存在官方列）
                
                def get_tick_val(df, keys, fallback_func, use_last=True):
                    for k in keys:
                        if k in df.columns:
                            valid = df[k][df[k] > 0]
                            if not valid.empty:
                                return valid.iloc[-1] if use_last else valid.iloc[0]
                    return fallback_func()

                # 1. Open
                open_p = get_tick_val(tick_df, ['open', 'nopen'], lambda: tick_df[price_col].iloc[0], use_last=False)
                
                # 2. High
                high_p = get_tick_val(tick_df, ['high', 'nhigh'], lambda: tick_df[price_col].max())
                
                # 3. Low
                low_p = get_tick_val(tick_df, ['low', 'nlow'], lambda: tick_df[price_col].min())
                
                # 修正 High/Low 必须包含 Current/Open
                high_p = max(high_p, current_price, open_p)
                low_p = min(low_p, current_price, open_p)

                ghost_ohlc = np.array([[new_x, open_p, current_price, low_p, high_p]], dtype=float)

                if not hasattr(self, 'ghost_candle') or self.ghost_candle not in self.kline_plot.items:
                    self.ghost_candle = CandlestickItem(ghost_ohlc, theme=self.qt_theme)
                    self.kline_plot.addItem(self.ghost_candle)
                else:
                    self.ghost_candle.setTheme(self.qt_theme)
                    self.ghost_candle.setData(ghost_ohlc)
            elif hasattr(self, 'ghost_candle'):
                self.kline_plot.removeItem(self.ghost_candle)
                delattr(self, 'ghost_candle')
        else:
            if hasattr(self, 'ghost_candle'):
                self.kline_plot.removeItem(self.ghost_candle)
                delattr(self, 'ghost_candle')

        # --- Tick Plot (Intraday) ---
        if tick_df is not None and not tick_df.empty:

            # 取收盘价和索引
            _prices = tick_df['close'].values
            _x_ticks = np.arange(len(_prices))

            # 找到非 NaN 的位置
            valid_mask = ~np.isnan(_prices)
            prices = _prices[valid_mask]
            x_ticks = _x_ticks[valid_mask]

            # ⭐ 准确获取昨日收盘价作为百分比基准 (解决百分比不对齐问题)
            pre_close = 0
            if 'llastp' in tick_df.columns and tick_df['llastp'].iloc[-1] > 0:
                pre_close = tick_df['llastp'].iloc[-1]
            elif 'pre_close' in tick_df.columns and tick_df['pre_close'].iloc[-1] > 0:
                pre_close = tick_df['pre_close'].iloc[-1]
            
            # 如果 tick_df 里没有，从历史日线 day_df 获取
            if pre_close <= 0 and day_df is not None and not day_df.empty:
                # 判断最后一行是否是今天
                today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
                last_dt_str = str(day_df.index[-1]).split()[0]
                if last_dt_str == today_str and len(day_df) >= 2:
                    pre_close = float(day_df.iloc[-2]['close'])
                else:
                    pre_close = float(day_df.iloc[-1]['close'])
            
            # 最终兜底
            if pre_close <= 0:
                pre_close = prices[0] if len(prices) > 0 else 1.0

            if hasattr(self, 'tick_pct_axis'):
                self.tick_pct_axis.set_base_price(pre_close)

            if not hasattr(self, 'tick_curve') or self.tick_curve not in self.tick_plot.items:
                self.tick_curve = self.tick_plot.plot(x_ticks, prices, pen=pg.mkPen(tick_curve_color, width=2))
            else:
                self.tick_curve.setData(x_ticks, prices)
                self.tick_curve.setPen(pg.mkPen(tick_curve_color, width=2))

            # 均价线
            if 'amount' in tick_df.columns and 'volume' in tick_df.columns:
                cum_amount = tick_df['amount'].cumsum()
                cum_volume = tick_df['volume'].cumsum()
                avg_prices = np.where(cum_volume>0, cum_amount/cum_volume, prices)
            else:
                avg_prices = pd.Series(prices).expanding().mean().values

            if not hasattr(self, 'avg_curve') or self.avg_curve not in self.tick_plot.items:
                self.avg_curve = self.tick_plot.plot(x_ticks, avg_prices, pen=pg.mkPen(tick_avg_color, width=1.5))
            else:
                self.avg_curve.setData(x_ticks, avg_prices)
                self.avg_curve.setPen(pg.mkPen(tick_avg_color, width=1.5))

            # ⭐ 保存分时数据供十字光标使用 (1.2)
            self.tick_prices = prices
            self.tick_avg_prices = avg_prices
            self.tick_times = tick_df['time'].tolist() if 'time' in tick_df.columns else []

            # --- 分时图参考线 ---
            # 1. 昨日收盘
            if not hasattr(self, 'pre_close_line') or self.pre_close_line not in self.tick_plot.items:
                self.pre_close_line = self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, width=2, style=Qt.PenStyle.DashLine))
            else:
                self.pre_close_line.setValue(pre_close)
                self.pre_close_line.setPen(pg.mkPen(pre_close_color, width=2, style=Qt.PenStyle.DashLine))

            # 2. 前日均价
            ppre_drawn = False
            if len(day_df) >= 2:
                ppre_row = day_df.iloc[-2]
                ppre_vol = ppre_row.get('volume', ppre_row.get('vol', 0))
                if ppre_vol > 0:
                    ppre_avg = ppre_row.get('amount', 0) / ppre_vol
                    # 防止前日均价过远撑爆图表，做个限制
                    y_max_temp = float(tick_df['high'].dropna().max()) if 'high' in tick_df.columns and not tick_df['high'].dropna().empty else prices.max()
                    y_min_temp = float(tick_df['low'].dropna().min()) if 'low' in tick_df.columns and not tick_df['low'].dropna().empty else prices.min()
                    max_dev = max(abs(y_max_temp - pre_close), abs(pre_close - y_min_temp))
                    
                    if abs(ppre_avg - pre_close) <= max_dev * 1.5:
                        if not hasattr(self, 'ppre_avg_line') or self.ppre_avg_line not in self.tick_plot.items:
                            self.ppre_avg_line = self.tick_plot.addLine(y=ppre_avg, pen=pg.mkPen('#00FF00', width=2, style=Qt.PenStyle.DashLine))
                        else:
                            self.ppre_avg_line.setValue(ppre_avg)
                            self.ppre_avg_line.setPen(pg.mkPen('#00FF00', width=2, style=Qt.PenStyle.DashLine))
                        self.ppre_avg_line.setVisible(True)
                        ppre_drawn = True

            # 兜底：如果没拿到 ppre 数据，隐藏线条
            if not ppre_drawn and hasattr(self, 'ppre_avg_line'):
                self.ppre_avg_line.hide()

            pct_change = (prices[-1]-pre_close)/pre_close*100 if pre_close!=0 else 0

            self.current_pre_close = pre_close # ⭐ 保存基准价供 R 键使用

            # ⭐ 使用统一的自适应方法调整视图，确保逻辑一致
            self._reset_tick_view(tick_df=tick_df, pre_close=pre_close)


            # ⭐ 构建分时图标题（显式包含当日最高/最低及其涨幅）
            y_max = getattr(self, 'tick_high_max', prices.max() if prices.size > 0 else 0)
            y_min = getattr(self, 'tick_low_min', prices.min() if prices.size > 0 else 0)
            
            high_pct = (y_max - pre_close) / pre_close * 100 if pre_close > 0 else 0
            low_pct = (y_min - pre_close) / pre_close * 100 if pre_close > 0 else 0
            
            tick_title = f"Intraday: {prices[-1]:.2f} ({pct_change:+.2f}%)  H:{y_max:.2f} ({high_pct:+.2f}%) L:{y_min:.2f} ({low_pct:+.2f}%)"

            # 追加监理看板信息
            if not self.df_all.empty:
                crow = None
                # 尝试多种匹配方式：原样匹配、去掉市场前缀匹配
                search_codes = [code]
                if len(code) > 6:
                    search_codes.append(code[-6:])

                for sc in search_codes:
                    if sc in self.df_all.index:
                        crow = self.df_all.loc[sc]
                        break
                    elif 'code' in self.df_all.columns:
                        mask = self.df_all['code'] == sc
                        if mask.any():
                            crow = self.df_all[mask].iloc[0]
                            break

                if crow is not None:
                    mwr = crow.get('market_win_rate', 0)
                    ls = crow.get('loss_streak', 0)
                    vwap_bias = crow.get('vwap_bias', 0)

                    # 保存数据供详情弹窗使用
                    self.current_supervision_data = {
                        'market_win_rate': mwr,
                        'loss_streak': ls,
                        'vwap_bias': vwap_bias,
                        'last_action': crow.get('last_action', ''),
                        'last_reason': crow.get('last_reason', ''),
                        'shadow_info': crow.get('shadow_info', '')
                    }
                    tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理: 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"
                else:
                    # 尝试自主计算
                    auto_data = self._get_autonomous_supervision_data(code)
                    if auto_data:
                        mwr = auto_data.get('market_win_rate', 0.5)
                        ls = auto_data.get('loss_streak', 0)
                        vwap_bias = auto_data.get('vwap_bias', 0)

                        # ⭐ 重点：补齐自主模式下的详情数据分配
                        has_sh = 'shadow_decision' in locals() and shadow_decision is not None
                        shadow_act = shadow_decision.get('action', 'N/A') if has_sh else 'N/A'
                        shadow_res = shadow_decision.get('reason', 'N/A') if has_sh else 'N/A'

                        self.current_supervision_data = {
                            'market_win_rate': mwr,
                            'loss_streak': ls,
                            'vwap_bias': vwap_bias,
                            'last_action': f"自主检测({shadow_act})",
                            'last_reason': shadow_res,
                            'shadow_info': 'AUTONOMOUS'
                        }
                        tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"
            else:
                # df_all 为空，直接自主计算
                auto_data = self._get_autonomous_supervision_data(code)
                if auto_data:
                    mwr = auto_data.get('market_win_rate', 0.5)
                    ls = auto_data.get('loss_streak', 0)
                    vwap_bias = auto_data.get('vwap_bias', 0)

                    has_sh = 'shadow_decision' in locals() and shadow_decision is not None
                    shadow_act = shadow_decision.get('action', 'N/A') if has_sh else 'N/A'
                    shadow_res = shadow_decision.get('reason', 'N/A') if has_sh else 'N/A'

                    self.current_supervision_data = {
                        'market_win_rate': mwr,
                        'loss_streak': ls,
                        'vwap_bias': vwap_bias,
                        'last_action': f"直接启动模式({shadow_act})",
                        'last_reason': shadow_res,
                        'shadow_info': 'DIRECT_LAUNCH'
                    }
                    tick_title += f"  |  <span style='color: #FFD700; font-weight: bold;'>🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}</span>"

            # [FIX] 更新分时图时间轴
            if hasattr(self, 'tick_axis'):
                t_list = []
                try:
                    # 1. 优先使用已提取的 self.tick_times (来自 tick_df['time'])
                    if hasattr(self, 'tick_times') and self.tick_times:
                        t_list = [str(t) for t in self.tick_times]
                    # 2. 其次尝试 Index Level
                    elif 'ticktime' in tick_df.index.names:
                        _times = tick_df.index.get_level_values('ticktime')
                        t_list = pd.to_datetime(_times).strftime('%H:%M:%S').tolist()
                    # 3. 最后直接使用 Index
                    else:
                        t_list = [str(t) for t in tick_df.index]
                except Exception as te:
                    logger.debug(f"Failed to extract tick times: {te}")
                    t_list = [str(i) for i in range(len(tick_df))]

                self.tick_axis.updateTimes(t_list)

            self.tick_plot.setTitle(tick_title)
            self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

            # --- [UPGRADE] Intraday Tick Signals (Shadow/Realtime) ---
            # 直接在分时图上标记影子信号
            tick_signals_to_draw = []

            if tick_df is not None and not tick_df.empty and self.show_strategy_simulation:
                # 复用刚才计算好的实时影子决策
                if 'shadow_decision' in locals() and shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                    y_p = float(tick_df['close'].iloc[-1])
                    idx = len(tick_df) - 1
                    tick_signals_to_draw.append(SignalPoint(
                        code=code, timestamp="TICK_LIVE", bar_index=idx, price=y_p,
                        signal_type=SignalType.BUY if '买' in shadow_decision['action'] or 'ADD' in shadow_decision['action'] else SignalType.SELL,
                        source=SignalSource.SHADOW_ENGINE,
                        reason=shadow_decision['reason'],
                        debug_info=shadow_decision.get('debug', {})
                    ))
                
                # [NEW] 提取 SBC 实时信号展示在分时图
                # 直接从专门的列表中获取 (已避免在 kline_signals 中污染日线图)
                if hasattr(self, 'all_today_sbc_signals') and getattr(self, 'all_today_sbc_signals'):
                    import copy
                    for sig in getattr(self, 'all_today_sbc_signals'):
                        tick_sig = copy.deepcopy(sig)
                        # tick_sig.bar_index 已经是分时图中的 index, 不需再赋值
                        tick_signals_to_draw.append(tick_sig)

                if tick_signals_to_draw:
                    self.signal_overlay.update_signals(tick_signals_to_draw, target='tick')

        # --- 绘制热点/跟单标记 ---
        self._draw_hotspot_markers(code, x_axis, day_df)
        
        # Draw Follow Lines separately (Markers are now handled by SignalOverlay)
        self._draw_follow_lines(code, day_df)
        
        self._draw_signal_annotation(code, x_axis, day_df)

        # ----------------- 5. 数据同步与视角处理 -----------------
        # 同步归一化后的数据到 self.day_df
        self.day_df = day_df

        is_new_stock = not hasattr(self, '_last_rendered_code') or self._last_rendered_code != code
        self._last_rendered_code = code


        # 判断周期是否变化
        last_resample = getattr(self, "_last_resample", None)
        is_resample_change = last_resample != self.resample  # None != '3d' 第一次会是 True
        logger.debug(f"resample check: last={last_resample}, current={self.resample}, is_change={is_resample_change}")
        
        # 复合视角恢复标志
        has_captured_state = hasattr(self, '_prev_dist_left') and getattr(self, '_prev_y_zoom', None) is not None
        was_full_view = getattr(self, '_prev_is_full_view', False)

        if is_new_stock or is_resample_change or has_captured_state:
            # [FIX] 只在真正发生变化时更新 _last_resample
            if is_resample_change:
                self._last_resample = self.resample
                logger.debug(f"✅ Resample changed: {last_resample} → {self.resample}")
            
            vb = self.kline_plot.getViewBox()
            # 如果之前是"全览"状态，或者根本没有捕获状态，则执行 Reset (全览)
            logger.debug(f'was_full_view: {was_full_view} has_captured_state: {has_captured_state}')
            if was_full_view or not has_captured_state or is_resample_change:
                self._reset_kline_view(df=day_df)
            else:
                # 处于“记忆”状态：用户之前可能缩放到了某个特定区域
                new_total = len(day_df)
                target_left = max(-1, new_total - self._prev_dist_left)
                target_right = new_total - self._prev_dist_right

                # 设置 X 轴，留出缓冲
                vb.setRange(xRange=(target_left, target_right), padding=0)

                # 适配 Y 轴
                visible_new = day_df.iloc[int(max(0, target_left)):int(min(new_total, target_right+1))]
                if not visible_new.empty:
                    new_h, new_l = visible_new['high'].max(), visible_new['low'].min()
                    
                    # [FIX] 如果是切换新股，我们保留 X 轴的缩放习惯（看末尾多少根），
                    # 但 Y 轴由于价格量级可能完全不同（如 20 vs 400），不再使用上一只股票的比例，而是直接全量适配。
                    if is_new_stock:
                        y_margin = (new_h - new_l) * 0.05 if new_h > new_l else 1.0
                        vb.setRange(yRange=(new_l - y_margin, new_h + y_margin), padding=0)
                        logger.debug(f"[VIEW] New stock {code} detected, resetting Y-range only.")
                    else:
                        # 周期切换或增量刷新：尽量保持之前的 Y 轴缩放比例关系
                        new_rng = new_h - new_l if new_h > new_l else 1.0
                        p_zoom, p_center_rel = float(self._prev_y_zoom), float(self._prev_y_center_rel)
                        target_h = new_rng * p_zoom
                        target_y_center = new_l + (new_rng * p_center_rel)
                        vb.setRange(yRange=(target_y_center - target_h/2, target_y_center + target_h/2), padding=0)

                # 保持自适应开启
                vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                vb.setAutoVisible(y=True)

            # 清理刚才使用的临时状态
            for attr in ['_prev_dist_left', '_prev_dist_right', '_prev_y_zoom', '_prev_y_center_rel', '_prev_is_full_view']:
                if hasattr(self, attr): delattr(self, attr)
        # ----------------- 5.1 数据自适应安全检查 (FIX) -----------------
        # 如果不是新股切换，检查当前价格是否在视野内。如果偏离过大（例如缓存数据与实时数据价差巨大），强制回正
        if not (is_new_stock or is_resample_change or has_captured_state):
             # 检查最后一条 K 线是否可见
             if not day_df.empty:
                 last_c = day_df['close'].iloc[-1]
                 vb = self.kline_plot.getViewBox()
                 y_min, y_max = vb.viewRange()[1]
                 
                 # 容差 20% (稍微宽松一点，避免频繁跳动)
                 height = y_max - y_min
                 
                 # [FIX] 如果价格偏离当前视口过大，或者视口没有高度，强制进行自动范围调整
                 # 特别是针对从 20 跳到 400 这种极端情况，常规的 enableAutoRange 可能不够及时或被其他设置抵消
                 if height <= 0 or last_c < (y_min - height*0.2) or last_c > (y_max + height*0.2):
                     logger.info(f"[AutoRange] Price {last_c:.2f} out of view [{y_min:.2f}, {y_max:.2f}], forcing Y-AutoRange/Reset")
                     
                     # 1. 尝试最温和的自动范围开启
                     vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                     vb.setAutoVisible(y=True)
                     
                     # 2. 如果偏离实在太离谱 (超过 2 倍高度)，说明之前的缩放完全不适用了，直接调用 Reset 恢复默认视角
                     if height > 0 and (last_c > y_max + height*2 or last_c < y_min - height*2):
                         logger.warning(f"[AutoRange] Extreme price gap detected, forcing full reset for {code}")
                         self._reset_kline_view(df=day_df)
                     else:
                         # 否则，尝试强制更新一次范围
                         vb.autoRange()

        # ----------------- 6. 更新实时决策面板 (Phase 7) -----------------
        if is_realtime_active and 'shadow_decision' in locals() and shadow_decision:
            action = shadow_decision.get('action', '无')
            reason = shadow_decision.get('reason', '运行中')

            # 颜色逻辑
            color_hex = "#00FF00" if "买" in action or "ADD" in action else "#FF4444" if ("卖" in action or "止" in action) else "#CCCCCC"

            self.decision_label.setText(
                f"实时决策中心: <span style='color:{color_hex}; font-weight: bold;'>{action}</span> "
                f"<span style='color:#888; font-size: 9pt;'>(理由: {reason})</span>"
            )

            # 更新心跳状态
            current_hb = self.hb_label.text()
            self.hb_label.setText("💗" if current_hb == "💓" else "💓")

            # 同步更新监理看板
            if hasattr(self, 'current_supervision_data'):
                sd = self.current_supervision_data
                self.supervision_label.setText(
                    f"🛡️ 流程监理: <span style='color:#FFD700;'>偏离{sd['vwap_bias']:+.1%} | "
                    f"胜率{sd['market_win_rate']:.1%} | 连亏{sd['loss_streak']}</span>"
                )
        else:
            self.decision_label.setText("实时决策中心: <span style='color:#666;'>未开启实时监控或等待信号...</span>")
            self.supervision_label.setText("🛡️ 流程监理: <span style='color:#666;'>就绪</span>")
            self.hb_label.setText("💤")
        
    def _update_plot_title(self, code, day_df, tick_df):
        """仅更新 K 线图基础信息（代码、名称、排名、板块等） - 极限性能版"""
        if not hasattr(self, 'kline_plot'):
            return

        # 1. 快速检查代码基本信息 (从缓存获取)
        info = self.code_info_map.get(code)
        if info is None and len(code) > 6:
            info = self.code_info_map.get(code[-6:])
        if info is None:
            info = {}

        # 2. 构建主标题 (只有在 info/code 改变或强制更新时才重新构建)
        # 使用 tuple 作为缓存键提高效率
        cache_key = (code, info.get('name'), info.get('Rank'), info.get('percent'))
        main_title = getattr(self, "_cached_main_title_str", "")
        
        if getattr(self, "_last_title_cache_key", None) != cache_key:
            title_parts = [code]
            for k, fmt in [('name', '{}'), ('Rank', 'Rank: {}'), ('percent', '{:+.2f}%'),
                           ('win', 'win: {}'), ('slope', 'slope: {:.1f}%'), ('volume', 'vol: {:.1f}')]:
                v = info.get(k)
                if v is not None:
                    title_parts.append(fmt.format(v))

            main_title = " | ".join(title_parts)
            self._cached_main_title_str = main_title
            self._last_title_cache_key = cache_key

        # 3. 获取板块信息 (category)
        category_text = getattr(self, "_cached_category_text", "")
        if self._last_rendered_code != code:
            category_text = ""
            if not self.df_all.empty:
                # 提前进行 numpy 掩码查找比 iterrows 快
                if code in self.df_all.index:
                    crow = self.df_all.loc[code]
                else:
                    sc = code[-6:] if len(code) > 6 else code
                    if sc in self.df_all.index:
                        crow = self.df_all.loc[sc]
                    else:
                        mask = self.df_all['code'].to_numpy() == sc
                        idx = np.flatnonzero(mask)
                        crow = self.df_all.iloc[idx[-1]] if len(idx) > 0 else None
                
                if crow is not None:
                    raw_cat = crow.get('category', '')
                    if pd.notna(raw_cat) and str(raw_cat).lower() != 'nan':
                        cats = [c.strip() for c in str(raw_cat).split(';') if c.strip() and c.strip() != '0']
                        if cats:
                            category_text = " | ".join(cats[:5])
            
            self._cached_category_text = category_text
            self._last_rendered_code = code

        # 4. 组合最终标题并设置
        full_title = f"{main_title}\n<span style='color: #FFCC00; font-size: 10pt;'>{category_text}</span>" if category_text else main_title
        
        if getattr(self, "_last_full_title", "") != full_title:
            self.kline_plot.setTitle(full_title)
            self._last_full_title = full_title

    def _on_title_double_clicked(self, ev):
        """双击标题复制板块信息 (category_text)"""
        category_text = getattr(self, "_cached_category_text", "")
        if category_text:
            try:
                # 分割板块文本，找到用户可能点击的那一个
                categories = [c.strip() for c in category_text.split("|")]
                target_copy = category_text # 默认
                
                # 尝试通过点击位置估算点击了哪个词
                if hasattr(ev, 'pos') and hasattr(self, 'kline_plot') and hasattr(self.kline_plot, 'titleLabel'):
                    label_item = self.kline_plot.titleLabel
                    text_item = label_item.item
                    
                    if text_item and hasattr(text_item, 'document'):
                        # 将坐标映射到 QTextItem 内
                        pos_in_text = label_item.mapToItem(text_item, ev.pos())
                        
                        doc = text_item.document()
                        layout = doc.documentLayout()
                        hit_idx = layout.hitTest(pos_in_text, Qt.HitTestAccuracy.FuzzyHit)
                        plain_text = doc.toPlainText()
                        
                        if 0 <= hit_idx < len(plain_text) and len(plain_text) > 0:
                            # 终极修复：不再手工算左右边界（防各种隐藏字符、换行越位）
                            # 直接暴力查找各版块词在 plain_text 中的绝对坐标区间
                            best_match = None
                            min_dist = 9999
                            for cat in categories:
                                start_idx = 0
                                while True:
                                    idx = plain_text.find(cat, start_idx)
                                    if idx == -1:
                                        break
                                    end_idx = idx + len(cat)
                                    
                                    # 放宽容差：前后3个字符内都算作点击了这个板块（包含 | 的距离）
                                    if idx - 3 <= hit_idx <= end_idx + 3:
                                        # 计算距离
                                        dist = 0 if idx <= hit_idx <= end_idx else min(abs(idx - hit_idx), abs(end_idx - hit_idx))
                                        if dist < min_dist:
                                            min_dist = dist
                                            best_match = cat
                                    start_idx = idx + len(cat)
                            
                            if best_match:
                                target_copy = best_match

                clipboard = QApplication.clipboard()
                clipboard.setText(target_copy)
                logger.info(f"✅ 已复制特定板块信息到剪贴板: {target_copy}")
                # 使用状态栏反馈（如果存在）
                if hasattr(self, 'statusBar') and self.statusBar():
                    self.statusBar().showMessage(f"已复制板块: {target_copy}", 3000)
            except Exception as e:
                logger.error(f"复制板块信息失败: {e}")
        ev.accept()

    def _refresh_sensing_bar(self, code):
        """刷新分时图标题中的监理看板（避免刷新 K 线标题导致布局抖动）"""
        if not hasattr(self, 'tick_plot'):
            return

        # 1. 获取基础分时信息
        # 尝试从之前的标题中恢复基础部分，或者简单重构
        base_title = self.tick_plot.titleLabel.text
        if "🛡️监理" in base_title:
            # 剥离旧的监理部分
            base_title = base_title.split("  |  <span")[0]

        # 2. 追加最新的监理看板信息
        sensing_parts = []
        if not self.df_all.empty:
            crow = None
            search_codes = [code]
            if len(code) > 6:
                search_codes.append(code[-6:])

            for sc in search_codes:
                if sc in self.df_all.index:
                    crow = self.df_all.loc[sc]
                    break
                elif 'code' in self.df_all.columns:
                    mask = self.df_all['code'] == sc
                    if mask.any():
                        crow = self.df_all[mask].iloc[0]
                        break

            if crow is not None:
                mwr = crow.get('market_win_rate', 0)
                ls = crow.get('loss_streak', 0)
                vwap_bias = crow.get('vwap_bias', 0)
                sensing_parts.append(f"🛡️监理: 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}")
            else:
                # ⭐ 备选方案：尝试自主计算（脱离主程序推送）
                auto_data = self._get_autonomous_supervision_data(code)
                if auto_data:
                    mwr = auto_data.get('market_win_rate', 0.5)
                    ls = auto_data.get('loss_streak', 0)
                    vwap_bias = auto_data.get('vwap_bias', 0)
                    sensing_parts.append(f"🛡️监理(自): 偏离{vwap_bias:+.1%} 胜率{mwr:.1%} 连亏{ls}")

        # [NEW] 实时决策信息显示
        decision_html = ""
        if hasattr(self, 'last_shadow_decision') and self.last_shadow_decision:
            d = self.last_shadow_decision
            action = d.get('action', '')
            reason = d.get('reason', '')
            if action:
                color = "#FF4500" if "买" in action or "ADD" in action else "#00CED1"
                decision_html = f"  |  🚀策略: <span style='color: {color}; font-weight: bold; font-size: 14pt;'>{action}</span> <span style='color: #AAA; font-size: 10pt;'>({reason})</span>"

        if sensing_parts:
            sensing_html = " ".join(sensing_parts)
            new_title = f"{base_title}  |  <span style='color: #FFD700; font-weight: bold;'>{sensing_html}</span>{decision_html}"
            self.tick_plot.setTitle(new_title)

    def _get_autonomous_supervision_data(self, code):
        """自主计算并获取监理数据（胜率、连亏、偏离度）"""
        try:
            # 1. 从数据库读取胜率和连亏
            mwr = self.logger.get_market_sentiment(days=10)
            ls = self.logger.get_consecutive_losses(code, days=15)

            # 2. 计算偏离度 (VWAP Bias)
            vwap_bias = 0
            if hasattr(self, 'tick_df') and not self.tick_df.empty:
                tick = self.tick_df
                if 'amount' in tick.columns and 'volume' in tick.columns:
                    cum_amount = tick['amount'].cumsum().iloc[-1]
                    cum_vol = tick['volume'].cumsum().iloc[-1]
                    if cum_vol > 0:
                        vwap = cum_amount / cum_vol
                        # 优先使用 close, 其次 trade, 最后 price
                        price_col = 'close' if 'close' in tick.columns else ('trade' if 'trade' in tick.columns else 'price')
                        current_price = tick[price_col].iloc[-1] if price_col in tick.columns else 0
                        if current_price > 0:
                            vwap_bias = (current_price - vwap) / vwap
            return {
                'market_win_rate': mwr,
                'loss_streak': ls,
                'vwap_bias': vwap_bias
            }
        except Exception as e:
            logger.debug(f"Autonomous supervision failed for {code}: {e}")
            return None


    def _run_realtime_strategy(self, code, day_df, tick_df):
        """
        [DEEP INTEGRATION v2] 实时策略决策
        直接调用 StrategyController 提供的实时决策接口
        """
        try:
            if day_df is None or day_df.empty or tick_df.empty:
                return None

            # 1. 准备行情行 (row)
            last_tick = tick_df.iloc[-1]
            # 优先使用 close, 其次 trade, 最后 price
            price_col = 'close' if 'close' in tick_df.columns else ('trade' if 'trade' in tick_df.columns else 'price')
            current_price = float(last_tick.get(price_col, last_tick.get('close', last_tick.get('trade', 0))))
            
            # 成交量：优先 vol, 其次 volume（注意：某些数据源 volume 是量比，vol 是成交量）
            vol_col = 'vol' if 'vol' in tick_df.columns else 'volume'
            # 成交额：优先 amount, 其次用 vol * close 估算
            amount_val = float(last_tick.get('amount', 0))
            if amount_val == 0 and vol_col in tick_df.columns and price_col in tick_df.columns:
                amount_val = float(tick_df[vol_col].sum() * current_price)
            
            vol_val = float(last_tick.get(vol_col, last_tick.get('vol', last_tick.get('volume', 0))))
            
            # 计算 nclose（均价）
            if vol_col in tick_df.columns and 'amount' in tick_df.columns:
                vol_sum = tick_df[vol_col].sum()
                nclose_val = float(tick_df['amount'].sum() / vol_sum) if vol_sum > 0 else current_price
            else:
                nclose_val = current_price
                
            row = {
                'code': code,
                'trade': current_price,
                'high': float(tick_df[price_col].max()) if price_col in tick_df.columns else current_price,
                'low': float(tick_df[price_col].min()) if price_col in tick_df.columns else current_price,
                'open': float(tick_df[price_col].iloc[0]) if price_col in tick_df.columns else current_price,
                'ratio': float(last_tick.get('ratio', last_tick.get('volume', 0))),  # volume 可能是量比
                'volume': vol_val,
                'amount': amount_val,
                'ma5d': float(day_df['close'].rolling(5).mean().iloc[-1]),
                'ma10d': float(day_df['close'].rolling(10).mean().iloc[-1]),
                'ma20d': float(day_df['close'].rolling(20).mean().iloc[-1]),
                'ma60d': float(day_df['close'].rolling(60).mean().iloc[-1]),
                'nclose': nclose_val
            }

            # 2. 准备快照 (snapshot)
            snapshot = {
                'last_close': float(day_df['close'].iloc[-2] if len(day_df) > 1 else day_df['close'].iloc[-1]),
                'market_win_rate': float(self.logger.get_market_sentiment(days=5)),
                'loss_streak': int(self.logger.get_consecutive_losses(code, days=10)),
                'highest_today': float(tick_df[price_col].max()) if price_col in tick_df.columns else current_price
            }

            # 3. 运行控制器评估
            decision = self.strategy_controller.get_realtime_decision(code, row, snapshot)
            return decision

        except Exception as e:
            logger.error(f"Realtime strategy evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _run_strategy_simulation_new50(self, code, day_df, n_rows=50) -> list[SignalPoint]:
        """
        [极限性能版 v2] 历史策略模拟（保持结果一致）
        """
        try:
            if day_df is None or len(day_df) < 10:
                return []

            # --- slice 不 copy ---
            _df = day_df if n_rows == 0 else day_df.iloc[-n_rows:]

            cols = _df.columns
            col_idx_map = {c: i for i, c in enumerate(cols)}

            target_cols = (
                'ma5d','ma10d','ma20d','ma60d',
                'lastp1d','lastv1d',
                'macddif','macddea','macd',
                'rsi','upper','cycle_stage'
            )

            # --- df_all 回填 ---
            if not self.df_all.empty:

                if code in self.df_all.index:
                    stock_row = self.df_all.loc[code]
                else:
                    codes = self.df_all['code'].to_numpy()
                    idx = np.flatnonzero(codes == code)
                    stock_row = self.df_all.iloc[idx[-1]] if idx.size else None

                if stock_row is not None:

                    values = _df.values
                    last_row = values[-1]

                    row_values = stock_row.values
                    row_cols = stock_row.index

                    # 提前构建 set 加速判断
                    row_col_set = set(row_cols)

                    for col in target_cols:
                        if col in col_idx_map and col in row_col_set:
                            v = stock_row[col]
                            if pd.notnull(v):
                                last_row[col_idx_map[col]] = v

            # --- 策略计算 ---
            signals = self.strategy_controller.evaluate_historical_signals(code, _df)

            # --- bar_index 偏移 ---
            if n_rows and len(day_df) > n_rows:
                offset = len(day_df) - n_rows
                for sig in signals:
                    sig.bar_index += offset

            return signals

        except Exception:
            logger.exception(f"Strategy simulation failed for {code}")
            return []

    def _run_strategy_simulation_new50_slow(self, code, day_df, n_rows=50) -> list[SignalPoint]:
        """
        [极限性能版] 历史策略模拟（保持顺序，高速，最近 N 行）
        """
        try:
            if day_df is None or len(day_df) < 10:
                return []

            # --- 只保留最近 n_rows 行 ---
            if n_rows == 0:
                _df = day_df.copy()
            else:
                _df = day_df.iloc[-n_rows:].copy()
            cols = _df.columns.tolist()

            target_cols = ['ma5d', 'ma10d', 'ma20d', 'ma60d', 'lastp1d', 'lastv1d', 'macddif', 'macddea', 'macd', 'rsi', 'upper','cycle_stage']
            target_cols = [c for c in target_cols if c in cols]

            # --- 快速从 df_all 回填最新指标（只最后一行） ---
            if not self.df_all.empty:
                # 如果 df_all 已经以 code 为索引，直接 loc 获取
                if code in self.df_all.index:
                    stock_row = self.df_all.loc[code]
                else:
                    # 否则用 numpy 避免全 DataFrame 扫描
                    mask = self.df_all['code'].to_numpy() == code
                    idx = np.flatnonzero(mask)
                    stock_row = self.df_all.iloc[idx[-1]] if len(idx) > 0 else None

                if stock_row is not None:
                    _df_values = _df.values
                    col_idx_map = {c:i for i,c in enumerate(cols)}
                    for col in target_cols:
                        if col in stock_row and pd.notnull(stock_row[col]):
                            _df_values[-1, col_idx_map[col]] = stock_row[col]
                    _df.iloc[:,:] = _df_values

            # --- 调用策略控制器 ---
            signals = self.strategy_controller.evaluate_historical_signals(code, _df)
            
            # --- 修正 bar_index 偏移：信号索引需对应原始 day_df ---
            if n_rows > 0 and len(day_df) > n_rows:
                offset = len(day_df) - n_rows
                for sig in signals:
                    sig.bar_index += offset
            
            return signals

        except Exception as e:
            logger.error(f"Strategy simulation failed for {code}: {e}", exc_info=True)
            return []



    def _run_strategy_simulation(self, code, day_df) -> list[SignalPoint]:
        """
        [DEEP INTEGRATION v2] 历史策略模拟
        直接调用 StrategyController 封装的完整策略规则
        """
        try:
            if day_df is None or len(day_df) < 10:
                return []

            # ⭐ 数据增强：如果 day_df 缺失指标，尝试从 df_all 回填最新的实时指标
            # 这样即使 K 线图加载的是基础 OHLC，也能利用推送池里的实时计算结果
            _df = day_df.copy()
            if 'ma5d' not in _df.columns and not self.df_all.empty:
                # 尝试从 df_all 获取当前股票的行
                stock_row = pd.DataFrame()
                if code in self.df_all.index:
                    stock_row = self.df_all.loc[[code]]
                elif 'code' in self.df_all.columns:
                    stock_row = self.df_all[self.df_all['code'] == code]

                if not stock_row.empty:
                    # 将 df_all 中的指标值更新到最新的一行
                    target_cols = ['ma5d', 'ma10d', 'ma20d', 'ma60d', 'lastp1d', 'lastv1d', 'macddif', 'macddea', 'macd', 'rsi', 'upper','cycle_stage']
                    for col in target_cols:
                        if col in stock_row.columns:
                            val = stock_row[col].iloc[0]
                            if pd.notnull(val):
                                # 仅更新最后一行，或者根据需要扩散（策略回放通常需要历史指标，这里仅作最新数据同步）
                                _df.loc[_df.index[-1], col] = val

            # 1. 调用统一控制器获取信号点
            signals = self.strategy_controller.evaluate_historical_signals(code, _df)
            return signals

        except Exception as e:
            logger.error(f"Strategy simulation failed for {code}: {e}", exc_info=True)
            return []

    def _init_filter_toolbar(self):
        # 查找或创建 Filter Action
        actions = self.toolbar.actions()
        has_filter = any(a.text() == "Filter" for a in actions)
        if not has_filter:
            filter_action = self.toolbar.addAction("Filter")
            filter_action.setCheckable(True)
            filter_action.triggered.connect(self.toggle_filter_panel)
            self.filter_action = filter_action

    def _init_filter_state(self):
        # 默认逻辑状态
        is_visible = not getattr(self, 'is_filter_collapsed', False)
        sizes = self.main_splitter.sizes()
        if is_visible:
            # 当前是“展开态”，需要构造一个“关闭态快照”
            self._filter_closed_sizes = [
                sizes[0] + sizes[2],
                sizes[1],
                0
            ]
        else:
            # 当前已经是关闭态
            self._filter_closed_sizes = sizes.copy()
        logger.debug(f'_filter_closed_sizes: {self._filter_closed_sizes} is_visible:{is_visible}')

    def on_main_splitter_moved(self, pos, index):
        """当 Splitter 被拖动时，实时同步 Filter 按钮状态"""
        # 只有当拖动的是右侧分割条 (index=2 ? check logic)
        # Splitter valid indices for moved signal are 1..count-1. 
        # For 3 widgets (0,1,2), moving the right handle is usually index 2 (between 1 and 2).
        
        sizes = self.main_splitter.sizes()
        if len(sizes) >= 3:
            filter_width = sizes[2]
            
            # 判断是否处于折叠状态
            is_collapsed = (filter_width <= 0)
            self.is_filter_collapsed = is_collapsed
            
            # 1. 更新 Toolbar Action
            if hasattr(self, 'filter_action'):
                self.filter_action.blockSignals(True)
                self.filter_action.setChecked(not is_collapsed)
                self.filter_action.blockSignals(False)
                
            # 2. 更新 Toggle 按钮图标
            if hasattr(self, 'toggle_filter_btn'):
                btn_text = "◀" if is_collapsed else "▶"
                self.toggle_filter_btn.setText(btn_text)
                tooltip = "展开筛选面板" if is_collapsed else "收起筛选面板"
                self.toggle_filter_btn.setToolTip(tooltip)

        # ⭐ [NEW] 当拖动 Splitter 时也需要触发 K 线视图重置，以自适应新尺寸
        if hasattr(self, 'day_df') and not self.day_df.empty:
            # 使用频率限制/简单延迟防抖，避免拖动时过于卡顿
            if not hasattr(self, '_splitter_reset_timer'):
                from PyQt6.QtCore import QTimer
                self._splitter_reset_timer = QTimer(self)
                self._splitter_reset_timer.setSingleShot(True)
                self._splitter_reset_timer.timeout.connect(lambda: self._reset_kline_view(force=True))
            
            self._splitter_reset_timer.start(50) # 50ms 防抖
    
    def _on_toggle_filter_clicked(self):
        """处理面板上的 Toggle 按钮点击"""
        # 获取当前状态
        sizes = self.main_splitter.sizes()
        if len(sizes) < 3: return
        
        is_collapsed = (sizes[2] <= 0)
        # 如果当前是折叠的，点击意味着展开 -> checked=True
        # 如果当前是展开的，点击意味着折叠 -> checked=False
        target_state = is_collapsed 
        
        self.toggle_filter_panel(target_state)

    def toggle_filter_panel(self, checked=False):
        """⭐ [UI OPTIMIZATION] 内部平移方案：开启 Filter 时压缩左侧列表，确保 K 线图不被挤压，且窗口不漂移"""
        # 1. 记录当前所有面板的宽度 [Table, Charts, Filter]
        sizes = self.main_splitter.sizes()
        is_visible = sizes[2] > 0

        if checked and not is_visible:
            # ⭐ 核心修复：记录关闭状态的原始 sizes
            self._filter_closed_sizes = sizes.copy()
        # 2. 记录当前可见性状态
        # is_presently_visible = self.filter_panel.isVisible()
        is_presently_visible = True if sizes[2] > 0 else False
        
        # 3. 确定 Filter 目标宽度 (若当前尺寸太小则设个保底值)
        # 如果即将开启
        if checked and not is_presently_visible:
            # target_f_width = 160
            # #尝试从历史配置获取用户习惯的宽度
            # try:
            #     # config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
            #     config_file = visualizer_config
            #     if os.path.exists(config_file):
            #         with open(config_file, 'r', encoding='utf-8') as f:
            #             config = json.load(f)
            #             s_sizes = config.get('splitter_sizes', [])
            #             if len(s_sizes) == 3 and s_sizes[2] > 50:
            #                 target_f_width = s_sizes[2]
            # except Exception:
            #     pass

            # # 逻辑：从左侧列表(sizes[0])中借用宽度给右侧 Filter(sizes[2])
            # # 确保 K 线区域(sizes[1]) 宽度几乎不变
            # if sizes[0] > target_f_width + 100:
            #     new_sizes = [sizes[0] - target_f_width, sizes[1], target_f_width]
            # else:
            #     # 若列表太窄，则列表保留 100，剩余从图表扣
            #     available_from_table = max(0, sizes[0] - 100)
            #     from_charts = target_f_width - available_from_table
            #     new_sizes = [100, max(100, sizes[1] - from_charts), target_f_width]
            # self.main_splitter.setSizes(new_sizes)

            target_f_width = 160
            try:
                # config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
                config_file = visualizer_config
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        s_sizes = config.get('splitter_sizes', [])
                        if len(s_sizes) == 3 and s_sizes[2] > 50:
                            target_f_width = s_sizes[2]
            except Exception:
                pass
            base = self._filter_closed_sizes
            # 从 table 借，不动 chart
            borrow = min(target_f_width, max(0, base[0] - 100))
            new_sizes = [
                base[0] - borrow,
                base[1],
                borrow
            ]
            self._close_auto_size()

            # self.filter_tree.setMinimumWidth(150)
            # self.filter_tree.setMaximumWidth(400)  # 根据你期望的最大宽度

            self.main_splitter.setSizes(new_sizes)
            self.load_history_filters()
            self._open_auto_size()
            logger.debug(f'new_sizes set : {new_sizes} base:{base} now:{self.main_splitter.sizes()}')
        elif not checked:
            if is_visible:
                if hasattr(self, '_filter_closed_sizes'):
                    self.main_splitter.setSizes(self._filter_closed_sizes)
                else:
                    sizes = self.main_splitter.sizes()
                    table_width = sizes[0] + sizes[2]  # 把 Filter 宽度加回 Table
                    chart_width = sizes[1]
                    filter_width = 0
                    self.main_splitter.setSizes([table_width, chart_width, filter_width])

        # elif not checked and is_presently_visible:
        #     # --- 动作：关闭 Filter ---
        #     # 逻辑：把 Filter 回收的宽度全部还给左侧列表，不影响 K 线图宽度
        #     f_w = sizes[2]
        #     new_sizes = [sizes[0] + f_w, sizes[1], 0]
        #     self.main_splitter.setSizes(new_sizes)
            # self.collapse_filter()
        
        # ⭐ [FIX] 面板切换后，延迟重置 K 线视图边距，确保最新数据不被遮挡
        # 使用双重延迟：50ms 等待 splitter 初步重排，150ms 等待渲染完成
        if hasattr(self, 'day_df') and not self.day_df.empty:
            from PyQt6.QtCore import QTimer
            def _delayed_reset():
                # ⭐ 传入当前 splitter 的准确宽度，确保计算结果立即可靠
                sizes = self.main_splitter.sizes()
                tw = sizes[1] if len(sizes) >= 2 else None
                self._reset_kline_view(df=self.day_df, force=True, target_width=tw)
            
            # 第一次延迟：等待 splitter 布局初始反应
            QTimer.singleShot(20, _delayed_reset)
            # 第二次延迟：确保布局完全稳定（比如动画结束或系统重排）
            QTimer.singleShot(150, _delayed_reset)


    def open_history_manager(self):
        try:
            import history_manager
            import multiprocessing
            import win32gui
            import win32con
            
            # --- 1. 优先尝试查找并置顶现有窗口 ---
            found_hwnd = None
            def check_window(hwnd, extra):
                nonlocal found_hwnd
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if "Query History Manager" in title:
                        found_hwnd = hwnd
                        return False # Stop enumerating
                return True
                
            try:
                win32gui.EnumWindows(check_window, None)
            except Exception as e:
                logger.warning(f"Error enumerating windows: {e}")

            if found_hwnd:
                logger.info("History Manager window found, bringing to front.")
                try:
                    # 恢复最小化窗口
                    if win32gui.IsIconic(found_hwnd):
                        win32gui.ShowWindow(found_hwnd, win32con.SW_RESTORE)
                    else:
                        win32gui.ShowWindow(found_hwnd, win32con.SW_SHOW)
                    
                    # 尝试置顶
                    win32gui.SetForegroundWindow(found_hwnd)
                except Exception as e:
                    logger.warning(f"Failed to bring window to front: {e}")
                    # 有时 SetForegroundWindow 会因权限问题失败，尝试 AttachThreadInput 方法 (虽然有点复杂，先试简单的)
                    pass
                return

            # --- 2. 窗口未找到，检查进程状态 ---
            # 如果进程活着但没窗口，说明正在启动中，不要重复启动
            if hasattr(self, 'history_manager_process') and self.history_manager_process and self.history_manager_process.is_alive():
                logger.info("History Manager process is running (startup phase), please wait...")
                return

            # --- 3. 启动新进程 ---
            logger.info("Launching History Manager...")
            self.history_manager_process = multiprocessing.Process(target=history_manager.run_manager_process, kwargs={'df_all': getattr(self, 'df_all', None)})
            self.history_manager_process.daemon = False 
            self.history_manager_process.start()
            logger.info(f"History Manager launched (PID: {self.history_manager_process.pid})")
            
        except ImportError:
             QMessageBox.warning(self, "Error", f"Failed to import history_manager module or win32gui.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch manager: {e}")


    def populate_tree_from_df(self, df: pd.DataFrame):
        """
        将 DataFrame 高速填充到 QTreeWidget
        - 支持列、颜色标记、图标
        - 左对齐、紧凑列宽、水平滚动
        """
        import time
        prep_start = time.time()
        self.filter_tree.clear()

        if df.empty:
            return

        # --- 配置列 ---
        columns = self._filter_columns  # 需要显示的列
        self.filter_tree.setColumnCount(len(columns))
        self.filter_tree.setHeaderLabels(columns)
        self.filter_tree.setSortingEnabled(True)
        self.filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.filter_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        # self.filter_tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)  <-- REMOVED: Caused panel to force expansion

        n_rows = len(df)

        # --- 预提取列数据，避免循环内索引 ---
        col_arrays = []
        for col in columns:
            if col in df.columns:
                arr = df[col].fillna('').tolist()
            else:
                arr = [''] * n_rows
            col_arrays.append(arr)

        # --- 特征标记预提取 ---
        feature_data = None
        fm = getattr(self, 'feature_marker', None)
        if fm and fm.enable_colors:
            # 使用 close/trade 替代 price（数据中不存在 price 列）
            feature_cols = ['percent', 'volume', 'category', 'close', 'trade', 'high4',
                            'max5', 'max10', 'hmax', 'hmax60', 'low4', 'low10', 'low60',
                            'lmin', 'min5', 'cmean', 'hv', 'lv', 'llowvol', 'lastdu4']
            fd = {}
            for k in feature_cols:
                if k in df.columns:
                    if k == 'category':
                        fd[k] = df[k].fillna('').tolist()
                    else:
                        fd[k] = df[k].fillna(0).tolist()
                else:
                    fd[k] = None
            feature_data = fd

        name_idx = columns.index('name') if 'name' in columns else -1

        # --- 构建行 ---
        for i in range(n_rows):
            values = [col_arrays[j][i] for j in range(len(columns))]

            row_data = None
            if feature_data:
                try:
                    fd = feature_data
                    # 优先使用 close, 其次 trade
                    price_val = fd['close'][i] if fd.get('close') else 0
                    if price_val == 0 and fd.get('trade'):
                        price_val = fd['trade'][i]

                    row_data = {
                        'percent': fd['percent'][i] if fd['percent'] else 0,
                        'volume': fd['volume'][i] if fd['volume'] else 0,
                        'category': fd['category'][i] if fd['category'] else '',
                        'price': price_val,
                        'high4': fd['high4'][i] if fd['high4'] else 0,
                        'max5': fd['max5'][i] if fd['max5'] else 0,
                        'max10': fd['max10'][i] if fd['max10'] else 0,
                        'hmax': fd['hmax'][i] if fd['hmax'] else 0,
                        'hmax60': fd['hmax60'][i] if fd['hmax60'] else 0,
                        'low4': fd['low4'][i] if fd['low4'] else 0,
                        'low10': fd['low10'][i] if fd['low10'] else 0,
                        'low60': fd['low60'][i] if fd['low60'] else 0,
                        'lmin': fd['lmin'][i] if fd['lmin'] else 0,
                        'min5': fd['min5'][i] if fd['min5'] else 0,
                        'cmean': fd['cmean'][i] if fd['cmean'] else 0,
                        'hv': fd['hv'][i] if fd['hv'] else 0,
                        'lv': fd['lv'][i] if fd['lv'] else 0,
                        'llowvol': fd['llowvol'][i] if fd['llowvol'] else 0,
                        'lastdu4': fd['lastdu4'][i] if fd['lastdu4'] else 0
                    }

                    # 添加图标
                    if name_idx >= 0:
                        icon = fm.get_icon_for_row(row_data)
                        if icon:
                            values[name_idx] = f"{icon} {values[name_idx]}"
                except Exception:
                    row_data = None

            # --- 插入 QTreeWidgetItem ---
            item = QTreeWidgetItem(self.filter_tree)
            for col, val in enumerate(values):
                item.setText(col, str(val))
                item.setTextAlignment(col, Qt.AlignmentFlag.AlignLeft)

            # 设置 UserRole 保存 code
            code_col = df.columns.get_loc('code') if 'code' in df.columns else 0
            item.setData(0, Qt.ItemDataRole.UserRole, str(values[code_col]))

            # 上色 percent 列
            pct_idx = columns.index('percent') if 'percent' in columns else -1
            if feature_data and pct_idx >= 0:
                pct_val = row_data['percent'] if row_data else 0
                if pct_val > 0:
                    item.setForeground(pct_idx, QBrush(QColor("red")))
                elif pct_val < 0:
                    item.setForeground(pct_idx, QBrush(QColor("green")))

        # --- 调整列宽 ---
        header = self.filter_tree.header()
        for col in range(self.filter_tree.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)

        prep_time = time.time() - prep_start
        if prep_time > 0.1:
            logger.debug(f"[TreeviewUpdater] 填充 {n_rows} 行耗时 {prep_time:.3f}s")

    def load_history_filters(self):
        from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE

        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.load_cat_filter_history5() # ✅ 同步刷新左侧板块过滤下拉框

        history_path = SEARCH_HISTORY_FILE

        if not os.path.exists(history_path):
            self.filter_combo.addItem("History file not found")
            self.filter_combo.blockSignals(False)
            return

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 根据选择的 history 载入
            history_key = self.history_selector.currentText()  # "history1" / "history2" / ...
            self.history_items = data.get(history_key, [])

            for item in self.history_items:
                q = item.get("query", "")
                note = item.get("note", "")
                label = f"{note} ({q})" if note else q
                self.filter_combo.addItem(label, userData=q)  # Store query in UserData

            if not self.history_items:
                self.filter_combo.addItem("(No history)")

        except Exception as e:
            self.filter_combo.addItem(f"Error: {e}")

        self.filter_combo.blockSignals(False)

        # ⭐ 延迟刷新 ComboBox 触发的 tree 填充
        if self.filter_combo.count() > 0:
            QTimer.singleShot(100, lambda: self.on_filter_combo_changed(self.filter_combo.currentIndex()))


    def load_cat_filter_history5(self):
        """[NEW] 为界面左侧的板块过滤框加载 history5 选项"""
        from tk_gui_modules.gui_config import SEARCH_HISTORY_FILE
        if not hasattr(self, 'cat_filter_input'): return
        
        self.cat_filter_input.blockSignals(True)
        # 保存用户当前可能输入的内容，防止重新加载清空正在打字的字
        cur_text = self.cat_filter_input.currentText()
        self.cat_filter_input.clear()
        
        history_path = SEARCH_HISTORY_FILE
        if os.path.exists(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                history5_items = data.get("history5", [])
                for item in history5_items:
                    q = item.get("query", "")
                    note = item.get("note", "")
                    label = f"{note} | {q}" if note else q
                    self.cat_filter_input.addItem(label, userData=q)
            except Exception as e:
                pass
                
        self.cat_filter_input.setCurrentText(cur_text)
        self.cat_filter_input.blockSignals(False)

    def on_filter_combo_changed(self, index):
        query_str = self.filter_combo.currentData()
        self.filter_tree.clear()

        if not query_str or self.df_all.empty:
            return

        try:
            # --- 1. 准备数据 ---
            df_to_search = self.df_all.copy()
            if 'code' not in df_to_search.columns:
                df_to_search['code'] = df_to_search.index.astype(str)
            if 'volume' in df_to_search.columns and 'vol' not in df_to_search.columns:
                df_to_search['vol'] = df_to_search['volume']

            # --- 2. 执行查询 ---
            final_query = ensure_parentheses_balanced(query_str)
            if query_engine:
                matches = query_engine.execute(df_to_search, final_query)
            else:
                matches = df_to_search.query(final_query)
            if matches.empty:
                # # self.statusBar().showMessage("Results: 0")
                # self.show_status_message("Results: 0", 2000)
                # # 设置为红色更醒目
                # if hasattr(self, 'center_msg_label'):
                #     self.center_msg_label.setStyleSheet("color: red; font-weight: bold;")
                return

            # # 调用高速填充
            # self.populate_tree_from_df(matches)

            # --- 3. 设置列头 ---
            base_cols = ['Code', 'Name', 'Rank', 'win', 'Percent']
            extra_cols = []
            if 'dff' in matches.columns:
                extra_cols.append('dff')
            if 'dff2' in matches.columns:
                extra_cols.append('dff2')

            display_cols = base_cols + extra_cols
            count_col = len(display_cols)
            self.filter_tree.setColumnCount(count_col)
            self.filter_tree.setHeaderLabels(display_cols)
            self.filter_tree.setSortingEnabled(True)
            self.filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.filter_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)

            # --- 4. 填充数据 ---
            for idx, row in matches.iterrows():
                code = str(row['code'])
                name = str(row.get('name', ''))
                rank = row.get('Rank', 0)
                win = row.get('win', 0)
                pct = row.get('percent', 0)

                # 安全转换数值
                try:
                    rank_val = int(rank) if rank not in ('', None, 'nan') else float('inf')
                except (ValueError, TypeError):
                    rank_val = 0
                try:
                    pct_val = float(pct) if pct not in ('', None, 'nan') else 0.0
                except (ValueError, TypeError):
                    pct_val = 0.0

                try:
                    win_val = int(win) if win not in ('', None, 'nan') else 0
                except (ValueError, TypeError):
                    win_val = 0

                child = NumericTreeWidgetItem(self.filter_tree)
                child.setText(0, code)
                child.setText(1, name)
                child.setText(2, str(rank) if rank not in ('', None) else '')
                child.setText(3, f"{win_val}")
                child.setText(4, f"{pct_val:.2f}")
                
                # 填入额外列
                curr_col_idx = len(base_cols)
                for col_name in extra_cols:
                    val = row.get(col_name, '-')
                    child.setText(curr_col_idx, str(val))
                    try:
                        # 尝试为额外列也设置数值用于排序
                        num_val = float(val) if val not in ('', None, '-', 'nan') else 0.0
                        child.setData(curr_col_idx, Qt.ItemDataRole.UserRole, num_val)
                        
                        # 为 dff / dff2 增加红绿颜色
                        if col_name in ('dff', 'dff2'):
                            if num_val > 0:
                                child.setForeground(curr_col_idx, QBrush(QColor("red")))
                            elif num_val < 0:
                                child.setForeground(curr_col_idx, QBrush(QColor("green")))
                                
                    except:
                        pass
                    curr_col_idx += 1

                child.setData(0, Qt.ItemDataRole.UserRole, code)

                # ⭐ 关键修复：使用UserRole存储数值用于排序
                child.setData(2, Qt.ItemDataRole.UserRole, rank_val)  # Rank列数值
                child.setData(3, Qt.ItemDataRole.UserRole, win_val)   # Win列数值
                child.setData(4, Qt.ItemDataRole.UserRole, pct_val)   # Percent列数值

                # 对齐
                for col in range(count_col):
                    child.setTextAlignment(col, Qt.AlignmentFlag.AlignLeft)

                # 百分比上色
                if pct_val > 0:
                    child.setForeground(4, QBrush(QColor("red")))
                elif pct_val < 0:
                    child.setForeground(4, QBrush(QColor("green")))

            # --- 5. 调整列宽 ---
            # ⭐ [OPTIMIZE] 使用 Interactive 模式并预设紧凑宽度
            header = self.filter_tree.header()
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setStretchLastSection(True)

            # # 定义紧凑列宽配置 (列名 -> 宽度)
            # compact_map = {
            #     'Code': 60, 'Rank': 40, 'win': 35, 'Percent': 55,
            #     'dff': 45, 'dff2': 45
            # }
            # # 应用宽度
            # # headers are dynamic, check match
            # current_headers = [self.filter_tree.headerItem().text(i) for i in range(self.filter_tree.columnCount())]
            
            # for i, h_text in enumerate(current_headers):
            #     if h_text in compact_map:
            #         self.filter_tree.setColumnWidth(i, compact_map[h_text])
            #     elif h_text == 'Name':
            #         # Name 列自适应
            #         header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

            current_headers = [
                self.filter_tree.headerItem().text(i)
                for i in range(self.filter_tree.columnCount())
            ]

            self.filter_tree.setRootIsDecorated(False)  # ⭐ 关闭首列树形缩进
            for i, h_text in enumerate(current_headers):
                h = h_text.strip()
                width = get_compact_width(h)
                # logger.info(f'h: {h} width: {width}')
                if width is not None:
                    self.filter_tree.setColumnWidth(i, width)
                elif h == 'Name':
                    header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)


            # for i, h_text in enumerate(current_headers):
            #     h = h_text.strip()
            #     width = get_compact_width(h)
            #     # logger.info(f'h: {h} width: {width}')
            #     # ⭐ Code 列左对齐
            #     if h == 'Code':
            #         # logger.info(f'左对齐 h: {h} width: {width}')
            #         for row in range(self.filter_tree.topLevelItemCount()):
            #             item = self.filter_tree.topLevelItem(row)
            #             if item:
            #                 # 确保 Code 列没有图标
            #                 item.setTextAlignment(0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            #     if width is not None:
            #         self.filter_tree.setColumnWidth(i, width)
            #     elif h == 'Name':
            #         header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)


            header.setStretchLastSection(True)

            # ⭐ 默认按Rank升序排序
            self.filter_tree.sortItems(2, Qt.SortOrder.AscendingOrder)

            # # self.statusBar().showMessage(f"Results: {len(matches)}")
            # if hasattr(self, 'center_msg_label'):
            #     self.center_msg_label.setStyleSheet("color: #00FF00; font-weight: bold;")
            # self.show_status_message(f"Results: {len(matches)}", 3000)

        except Exception as e:
            err_item = QTreeWidgetItem(self.filter_tree)
            err_item.setText(0, f"Error: {e}")


    def on_filter_tree_item_clicked(self, item, column):
        code = item.data(0, Qt.ItemDataRole.UserRole)
        if code:
            # 1. 触发图表加载
            self.load_stock_by_code(code)
            # 2. 联动左侧列表选中
            self._select_stock_in_main_table(code)
        
        # ⭐ 无论如何确保焦点留在 filter_tree，防止联动逻辑掠夺焦点
        self.filter_tree.setFocus()

    def _on_filter_tree_item_double_clicked(self, item, column):
        """Filter Tree 双击事件：执行 SBC 回放分析"""
        code = item.data(0, Qt.ItemDataRole.UserRole) or item.text(0)
        if code:
            self._run_sbc_test(False, code)


    def on_filter_tree_current_changed(self, current, previous):
        """处理键盘导航（上下键）"""
        if current:
            code = current.data(0, Qt.ItemDataRole.UserRole)
            if code:
                # 触发图表加载
                self.load_stock_by_code(code)
                # 联动左侧列表选中
                self._select_stock_in_main_table(code)
        
        # ⭐ 确保焦点留在 filter_tree，防止键盘连续上下切换失效
        self.filter_tree.setFocus()

    def eventFilter(self, watched, event):
        """处理 filter_tree viewport 点击事件，确保获取焦点"""
        from PyQt6.QtCore import QEvent
        if watched == self.filter_tree.viewport():
            if event.type() == QEvent.Type.MouseButtonPress:
                # ⭐ 点击 filter_tree 区域时强制获取焦点
                self.filter_tree.setFocus()
        return super().eventFilter(watched, event)

    def _select_stock_in_main_table(self, target_code):
        """在左侧 stock_table 中查找并滚动到指定 code"""
        # 遍历查找 (假设数据量不大，几千行以内尚可)
        # 如果 self.stock_table 行数过多，建议维护 code -> row 映射
        row_count = self.stock_table.rowCount()
        for row in range(row_count):
            item = self.stock_table.item(row, 0) # 第0列通常是 Code? 需确认
            # get data from UserRole or text
            if item:
                code_data = item.data(Qt.ItemDataRole.UserRole)
                if not code_data:
                    code_data = item.text()

                if str(code_data) == str(target_code):
                    self.stock_table.selectRow(row)
                    self.stock_table.scrollToItem(item)
                    break

    def load_splitter_state(self):
        """加载保存的分割器状态 (兼容旧版调用)"""
        self._load_visualizer_config()

    def _load_visualizer_config(self):
        """
        统一加载可视化器配置 (支持未来扩展)
        配置文件: visualizer_layout.json
        """
        try:
            # config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
            config_file = visualizer_config
            config = {}
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # --- 1. 分割器尺寸 ---
            # --- 1. 分割器尺寸 ---
            # --- 1. 分割器尺寸 ---
            sizes = config.get('splitter_sizes', [])
            if sizes and len(sizes) == 3:
                # 🛡️ [Self-Healing] 检查并修复异常尺寸 (修复 1110px 问题)
                table_w, chart_w, filter_w = sizes
                
                # 如果 Filter 异常大 (> 600) 或 Chart 异常小 (< 300)
                if filter_w > 600 or chart_w < 300:
                    logger.warning(f"Detected corrupted layout {sizes}, resetting to safe defaults.")
                    # 重置为更合理的比例，保留用户可能的 Table 宽度习惯
                    safe_table = max(150, min(table_w, 400))
                    safe_filter = 250
                    # Chart 自动填充剩余
                    self.main_splitter.setSizes([safe_table, 800, safe_filter])
                else:
                    self.main_splitter.setSizes(sizes)
                
                # 确保 Filter 宽度为 0 也能被正确识别为折叠
                # 确保 Filter 宽度为 0 也能被正确识别为折叠
                if sizes[2] == 0:
                    # 临时允许缩小至 0，防止 setMinimumWidth 阻挡
                    if hasattr(self, 'filter_panel_container'):
                        self.filter_panel_container.setMinimumWidth(0)
                        
                    f_w = 0 
                    new_sizes = [sizes[0], sizes[1], f_w]
                    # 强制应用
                    self.main_splitter.setSizes(new_sizes)
                    
                    # 更新 toggle 按钮状态
                    if hasattr(self, 'toggle_filter_btn'):
                        self.toggle_filter_btn.setText("◀")
                        self.toggle_filter_btn.setToolTip("展开筛选面板")
                    
                    self.is_filter_collapsed = True
                else:
                    self.is_filter_collapsed = False
                    if hasattr(self, 'toggle_filter_btn'):
                        self.toggle_filter_btn.setText("▶")
                    
            else:
                # 默认分割比例：股票列表:过滤面板:图表区域 = 1:1:4
                self.main_splitter.setSizes([200, 800, 200])
            
            # --- 1.1 加载布局预设 ---
            self.layout_presets = config.get('layout_presets', {})
            
            # --- 2. Filter 配置 ---
            filter_config = config.get('filter', {})
            
            # 2.1 历史文件选择 (history1-5)
            history_index = filter_config.get('history_index', 4)  # 默认 history5
            if hasattr(self, 'history_selector'):
                if 0 <= history_index < self.history_selector.count():
                    self.history_selector.blockSignals(True)
                    self.history_selector.setCurrentIndex(history_index)
                    self.history_selector.blockSignals(False)
            
            # 2.2 上次使用的查询规则索引 (延迟应用，等 filter_combo 加载完成后)
            self._pending_filter_query_index = filter_config.get('last_query_index', 0)
            
            # --- 3. 窗口配置 ---
            window_config = config.get('window', {})
            
            # 3.1 主题 (如果有)
            saved_theme = window_config.get('theme')
            if saved_theme and hasattr(self, 'qt_theme'):
                 self.qt_theme = saved_theme
            
            # 3.1.2 自定义背景色
            if 'custom_bg_app' in window_config:
                self.custom_bg_app = window_config.get('custom_bg_app')
            if 'custom_bg_chart' in window_config:
                self.custom_bg_chart = window_config.get('custom_bg_chart')
            
            # 初始应用一次主题样式
            self.apply_qt_theme()
            
            # --- 4. 列宽配置 ---
            self.saved_col_widths = config.get('column_widths', {})
            if 'stock_table' in self.saved_col_widths:
                # 延迟应用，确保表头和数据已初次加载完成 (主要针对独立运行模式)
                QTimer.singleShot(800, lambda: self._apply_saved_column_widths(
                    self.stock_table, self.saved_col_widths.get('stock_table', {})
                ))
            
            # # 3.2 全局快捷键开关
            # if 'global_shortcuts_enabled' in window_config:
            #     enabled = window_config.get('global_shortcuts_enabled', False)
            #     self.global_shortcuts_enabled = enabled
            #     if hasattr(self, 'gs_action'):
            #         self.gs_action.setChecked(enabled)
            #         if enabled:
            #             self.on_toggle_global_keys(enabled)

            # 3.2 全局快捷键开关
            if 'global_shortcuts_enabled' in window_config:
                enabled = bool(window_config.get('global_shortcuts_enabled', False))
                self.global_shortcuts_enabled = enabled

                if hasattr(self, 'gs_action'):
                    self.gs_action.blockSignals(True)
                    self.gs_action.setChecked(enabled)
                    self.gs_action.blockSignals(False)

                    # 主动执行一次逻辑（仅初始化）
                    self.on_toggle_global_keys(enabled)


            # 3.3 模拟信号开关（修复重点）
            if 'show_strategy_simulation' in window_config:
                enabled = bool(window_config.get('show_strategy_simulation', False))
                self.show_strategy_simulation = enabled

                if hasattr(self, 'sim_action'):
                    self.sim_action.blockSignals(True)
                    self.sim_action.setChecked(enabled)
                    self.sim_action.blockSignals(False)

                    # ❗ 调用正确的 slot
                    self.on_toggle_simulation(enabled)

            # 3.4 TDX 联动开关
            if 'tdx_enabled' in window_config:
                enabled = bool(window_config.get('tdx_enabled', True))
                self.tdx_enabled = enabled
                if hasattr(self, 'tdx_var'):
                    self.tdx_var.set(enabled)
                if hasattr(self, 'tdx_btn'):
                    self.tdx_btn.blockSignals(True)
                    self.tdx_btn.setChecked(enabled)
                    self.tdx_btn.blockSignals(False)

            # 3.4.1 THS 联动开关
            if 'ths_enabled' in window_config:
                enabled = bool(window_config.get('ths_enabled', True))
                self.ths_enabled = enabled
                if hasattr(self, 'ths_var'):
                    self.ths_var.set(enabled)
                if hasattr(self, 'ths_btn'):
                    self.ths_btn.blockSignals(True)
                    self.ths_btn.setChecked(enabled)
                    self.ths_btn.blockSignals(False)

            # 3.5 神奇九转开关
            if 'show_td_sequential' in window_config:
                enabled = bool(window_config.get('show_td_sequential', True))
                self.show_td_sequential = enabled
                if hasattr(self, 'td_action'):
                    self.td_action.setChecked(enabled)
                    self.td_action.blockSignals(False)

            # 3.6 顶部 Filter 按钮状态同步
            if hasattr(self, 'filter_action'):
                # 如果 collapsed=True, 则 visible=False -> checked=False
                is_filter_visible = not getattr(self, 'is_filter_collapsed', False)
                self.filter_action.blockSignals(True)
                self.filter_action.setChecked(is_filter_visible)
                self.filter_action.blockSignals(False)

            # 3.7 热点语音播报状态 (恢复)
            if 'hotlist_voice_paused' in window_config:
                is_paused = bool(window_config.get('hotlist_voice_paused', False))
                # 暂存状态
                self._pending_hotlist_voice_paused = is_paused
                
                if hasattr(self, 'hotlist_panel'):
                    self.hotlist_panel._voice_paused = is_paused
                
                # Update UI
                if hasattr(self, 'voice_action'):
                    if is_paused:
                        self.voice_action.setText("🔇 热点播报: 关(Alt+V)")
                    else:
                        self.voice_action.setText("🔊 热点播报: 开(Alt+V)")
                
                logger.info(f"StartUp: Loaded Voice Config. Paused={is_paused}")


            logger.debug(f"[Config] Loaded: splitter={sizes}, filter={filter_config}, shortcuts={self.global_shortcuts_enabled}")
            
        except Exception as e:
            logger.warning(f"Failed to load visualizer config: {e}")
            # 使用默认值
            self.main_splitter.setSizes([200, 800, 200])

    def _apply_pending_filter_index(self):
        """应用待定的过滤规则索引 (在 filter_combo 加载完成后调用)"""
        if hasattr(self, '_pending_filter_query_index'):
            idx = self._pending_filter_query_index
            if hasattr(self, 'filter_combo') and 0 <= idx < self.filter_combo.count():
                self.filter_combo.setCurrentIndex(idx)
            delattr(self, '_pending_filter_query_index')


    def save_splitter_state(self):
        """保存分割器状态 (兼容旧版调用)"""
        self._save_visualizer_config()

    def _save_visualizer_config(self):
        """
        统一保存可视化器配置 (支持未来扩展)
        配置文件: visualizer_layout.json
        """
        try:
            # config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
            # config_file = cct.get_resource_file("visualizer_layout.json")
            config_file = visualizer_config

            # --- 读取现有配置 (保留未知字段以支持向前兼容) ---
            old_config = {}
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        old_config = json.load(f)
                except Exception:
                    old_config = {}

            # --- 1. 分割器尺寸 ---
            sizes = self.main_splitter.sizes()
            fixed_sizes = list(sizes)

            # 🛡️ 安全上限：防止过滤器面板过宽导致渲染异常 (修复 1110)
            FILTER_INDEX = 2
            FILTER_MAX = 400 
            if hasattr(self, '_filter_closed_sizes'):
                _filter_size = self._filter_closed_sizes[2]
            if fixed_sizes[FILTER_INDEX] > FILTER_MAX:
                fixed_sizes[FILTER_INDEX] = min(_filter_size,FILTER_MAX)
                logger.warning(f"[SaveConfig] Detected huge filter width {fixed_sizes[FILTER_INDEX]}, capping to {FILTER_MAX} _filter_size:{_filter_size}")
            logger.debug('fixed_sizes: {fixed_sizes}')
            # --- 2. Filter 配置 ---
            filter_config = old_config.get('filter', {})
            
            # 2.1 历史文件选择
            if hasattr(self, 'history_selector'):
                filter_config['history_index'] = self.history_selector.currentIndex()
            
            # 2.2 上次使用的查询规则索引
            if hasattr(self, 'filter_combo'):
                filter_config['last_query_index'] = self.filter_combo.currentIndex()

            # --- 3. 窗口配置 ---
            window_config = old_config.get('window', {})
            
            # 3.1 主题
            if hasattr(self, 'qt_theme'):
                window_config['theme'] = self.qt_theme
            if hasattr(self, 'custom_bg_app'):
                window_config['custom_bg_app'] = self.custom_bg_app
            if hasattr(self, 'custom_bg_chart'):
                window_config['custom_bg_chart'] = self.custom_bg_chart

            # 3.2 全局快捷键开关
            if hasattr(self, 'global_shortcuts_enabled'):
                window_config['global_shortcuts_enabled'] = self.global_shortcuts_enabled
            # 3.3 模拟信号开关
            if hasattr(self, 'show_strategy_simulation'):
                window_config['show_strategy_simulation'] = self.show_strategy_simulation
            
            # 3.4 TDX 联动开关
            if hasattr(self, 'tdx_enabled'):
                window_config['tdx_enabled'] = self.tdx_enabled
            
            # 3.4.1 THS 联动开关
            if hasattr(self, 'ths_enabled'):
                window_config['ths_enabled'] = self.ths_enabled
            
            if hasattr(self, 'show_td_sequential'):
                window_config['show_td_sequential'] = self.show_td_sequential
            
            # 3.8 热点语音播报状态
            if hasattr(self, 'hotlist_panel'):
                window_config['hotlist_voice_paused'] = self.hotlist_panel._voice_paused
                
            # --- 4. 列宽配置 ---
            col_widths = old_config.get('column_widths', {})
            
            # 4.1 主表宽度 (以表头显示文本为 Key 以保持语义一致性)
            stock_widths = {}
            for col in range(self.stock_table.columnCount()):
                h_item = self.stock_table.horizontalHeaderItem(col)
                if h_item:
                    stock_widths[h_item.text()] = self.stock_table.columnWidth(col)
            col_widths['stock_table'] = stock_widths

            # 4.2 筛选树宽度
            if hasattr(self, 'filter_tree'):
                tree_widths = {}
                h_item = self.filter_tree.headerItem()
                for col in range(self.filter_tree.columnCount()):
                    tree_widths[h_item.text(col)] = self.filter_tree.columnWidth(col)
                col_widths['filter_tree'] = tree_widths

            # ⭐ [FIX] 保存时同步更新运行时的内存缓存
            self.saved_col_widths = col_widths

            # --- 构建最终配置 ---
            config = {
                'splitter_sizes': fixed_sizes,
                'layout_presets': getattr(self, 'layout_presets', {}),
                'filter': filter_config,
                'window': window_config,
                # 未来扩展：直接添加新的顶级键即可
            }
                # 'column_widths': col_widths,

            # --- 保存 ---
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.debug(f'[Config] Saved: {config}')

        except Exception as e:
            logger.exception("Failed to save visualizer config")

    def _save_h_scroll_state(self, widget):
        """保存水平滚动状态：记录最左侧可见列及其像素偏移"""
        if not widget: return None
        try:
            h_bar = widget.horizontalScrollBar()
            if not h_bar: return None
            
            left_pos = h_bar.value()
            first_col = widget.columnAt(0)
            if first_col < 0: return None
            
            # 检查是否有 header 对象
            header = getattr(widget, 'header', None)
            if callable(header): header = header()
            if not header: return None
            
            col_pos = header.sectionPosition(first_col)
            offset = left_pos - col_pos
            return (first_col, offset)
        except:
            return None

    def _restore_h_scroll_state(self, widget, state):
        """恢复水平滚动状态：滚动到指定列并应用偏移 (防止视图跳动)"""
        if not widget or not state: return
        try:
            first_col, offset = state
            if first_col < 0 or first_col >= widget.columnCount(): return
            
            # 使用针对性方法
            if hasattr(widget, 'scrollToColumn'):
                widget.scrollToColumn(first_col)
            
            # header 对象获取
            header = getattr(widget, 'header', None)
            if callable(header): header = header()
            if not header: return

            # 延时一点等待渲染完成
            QTimer.singleShot(10, lambda: widget.horizontalScrollBar().setValue(
                header.sectionPosition(first_col) + offset
            ))
        except:
            pass

    def _resize_columns_tightly(self, widget):
        """
        紧凑型自适应：
        1. 执行标准自适应
        2. 手动收缩 15px 去除 Qt 默认宽边距
        3. 强制限制最大宽度 380px，防止长文本霸屏
        """
        if not widget: return
        h_state = self._save_h_scroll_state(widget)
        
        # 关键：暂时关闭列宽变动的信号捕获，防止触发配置保存覆盖用户手动微调
        header = getattr(widget, 'header', None)
        if callable(header): header = header()
        if header: header.blockSignals(True)
        
        try:
            for col in range(widget.columnCount()):
                widget.resizeColumnToContents(col)
                w = widget.columnWidth(col)
                # 策略: 原始宽度 - 15px (更紧凑), 但最小保留 35px, 最大限制 380px
                new_w = min(max(w - 15, 35), 380)
                widget.setColumnWidth(col, new_w)
        finally:
            if header: header.blockSignals(False)
            
        self._restore_h_scroll_state(widget, h_state)

    def _apply_saved_column_widths(self, widget, widths_dict):
        """应用保存过的列宽配置"""
        if not widget or not widths_dict: return
        header = getattr(widget, 'header', None)
        if callable(header): header = header()
        if not header: return
        
        # 阻塞信号，防止恢复过程触发冗余保存
        header.blockSignals(True)
        try:
            is_table = isinstance(widget, QTableWidget)
            for col in range(widget.columnCount()):
                col_name = ""
                if is_table:
                    h_item = widget.horizontalHeaderItem(col)
                    if h_item: col_name = h_item.text()
                else: # QTreeWidget
                    col_name = widget.headerItem().text(col)
                    
                if col_name in widths_dict:
                    widget.setColumnWidth(col, widths_dict[col_name])
                    # 显式设为 Interactive 模式，防止后续被 ResizeToContents 覆盖
                    header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        finally:
            header.blockSignals(False)

    def _open_auto_size(self, delay=True):
        if delay:
            # 延迟到下一轮事件循环，避免影响 splitter / layout
            QTimer.singleShot(1, lambda: self._open_auto_size(delay=False))
            return

        if hasattr(self, 'stock_table'):
            header = self.stock_table.horizontalHeader()
            for c in range(header.count()):
                header.setSectionResizeMode(
                    c, QHeaderView.ResizeMode.ResizeToContents
                )
            self.stock_table.resizeColumnsToContents()

        if hasattr(self, 'filter_tree'):
            header = self.filter_tree.header()
            for c in range(header.count()):
                header.setSectionResizeMode(
                    c, QHeaderView.ResizeMode.ResizeToContents
                )
            self.filter_tree.resizeColumnToContents(0)
            # self.stock_table.resizeColumnsToContents()

    def _close_auto_size(self):
        if hasattr(self, 'stock_table'):
            header = self.stock_table.horizontalHeader()
            for c in range(header.count()):
                header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)

        if hasattr(self, 'filter_tree'):
            header = self.filter_tree.header()
            for c in range(header.count()):
                header.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)


    def load_layout_preset(self, index):
        """从预设加载布局 (1-3) 并重新校准视角"""
        try:
            if hasattr(self, 'layout_presets'):
                preset = self.layout_presets.get(str(index))

                if preset:
                    # 兼容旧版本 (以前是 list，现在是 dict)
                    theme_changed = False
                    if isinstance(preset, list):
                        sizes = preset
                    else:
                        sizes = preset.get('sizes')
                        # 恢复主题设置
                        if 'bg_app' in preset:
                            self.custom_bg_app = preset['bg_app']
                            theme_changed = True
                        if 'bg_chart' in preset:
                            self.custom_bg_chart = preset['bg_chart']
                            theme_changed = True
                        if 'theme' in preset:
                            self.qt_theme = preset['theme']
                            theme_changed = True
                    
                    if sizes:
                        # ⭐ [FIX] 强制切换列宽模式为 Interactive，防止 ResizeToContents 撑大布局
                        # 左侧 Stock Table
                        self._close_auto_size()
                        # self.filter_panel.setVisible(True)
                        logger.debug(f'load_layout_preset sizes: {sizes} (Auto-resize disabled)')
                        self.main_splitter.setSizes(sizes)
                        self._open_auto_size()

                        # is_visible = not getattr(self, 'is_filter_collapsed', False)
                        # if is_visible:
                        #     self.toggle_filter_panel(True)
                        #     logger.debug(f'load_layout_preset toggle_filter_panel open')
                    
                    if theme_changed:
                        self.apply_qt_theme()
                        
                    # ⭐ 核心修复：布局切换后强制执行一次“智能重置”，校准 X 轴优先级至右侧
                    # 传入 target_width=sizes[1]，确保即使 Splitter 尚未物理调整，也按预设宽度计算可见 K 线
                    target_chart_width = sizes[1] if (sizes and len(sizes) >= 2) else None
                    if not self.day_df.empty:
                        self._reset_kline_view(target_width=target_chart_width)
                    logger.info(f"Layout preset {index} loaded. Theme changed: {theme_changed}")

                    # self._init_filter_state()

                else:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "加载失败", f"尚未保存布局预设 {index}。")

        except Exception as e:
            logger.error(f"Failed to load layout preset {index}: {e}")


    def closeEvent(self, event):
        """窗口关闭统一退出清理"""
        self._closing = True

        # 0.15️⃣ 停止 SBC 自动刷新 Timer
        if hasattr(self, "_sbc_timer") and self._sbc_timer:
            try:
                self._sbc_timer.stop()
                self._sbc_timer.deleteLater()
            except:
                pass
            self._sbc_timer = None

        # 0.16️⃣ 停止所有 SBC 线程
        if hasattr(self, "_sbc_windows"):
            for win, state in list(self._sbc_windows.items()):
                thread = state.get('thread')
                if thread and thread.isRunning():
                    thread.quit()
                    thread.wait(500)
            self._sbc_windows.clear()
        
        if hasattr(self, "_sbc_req_thread") and self._sbc_req_thread and self._sbc_req_thread.isRunning():
            self._sbc_req_thread.quit()
            self._sbc_req_thread.wait(500)

        # 0.25️⃣ 停止所有 Qt Timer
        for attr in dir(self):
            obj = getattr(self, attr)
            if isinstance(obj, QTimer):
                try:
                    obj.stop()
                except:
                    pass

        # 0.1️⃣ 清理打开的 SBC 回放窗口
        if hasattr(self, '_sbc_test_windows'):
            for win in self._sbc_test_windows:
                try:
                    if win.isVisible():
                        win.close()
                except:
                    pass
            self._sbc_test_windows.clear()

        # 0.️⃣ 立即停止语音进程 (防止退出过程中继续播报噪音)

        if hasattr(self, 'voice_thread') and self.voice_thread:
            logger.info("Closing Voice Broadcast system...")
            try:
                self.voice_thread.stop()
            except Exception as e:
                logger.error(f"Error stopping voice_thread: {e}")

        # [User Request] 退出时清理 History Manager
        if hasattr(self, 'history_manager_process') and self.history_manager_process and self.history_manager_process.is_alive():
            try:
                self.history_manager_process.terminate()
                self.history_manager_process.join(timeout=1)
                logger.info("History Manager process terminated on exit.")
            except Exception as e:
                logger.error(f"Error closing History Manager: {e}")
                
        # 保存分割器状态
        self.save_splitter_state()
        
        try:
            self.save_window_position_qt_visual(self, "trade_visualizer")
        except Exception as e:
            logger.error(f"Failed to save window position: {e}")

        # 1️⃣ 停止实时数据进程
        if hasattr(self, 'stop_flag'):
            self.stop_flag.value = False
        logger.info(f'stop_flag.value: {self.stop_flag.value}')

        # 2️⃣ 停止并关闭独立面板 (关键：防止 QThread Destroyed)
        if hasattr(self, 'hotlist_panel') and self.hotlist_panel:
            logger.debug("Closing HotlistPanel...")
            try:
                # 先停止工作线程
                if hasattr(self.hotlist_panel, 'data_worker') and self.hotlist_panel.data_worker:
                    if self.hotlist_panel.data_worker.isRunning():
                        logger.debug("Stopping HotlistPanel data_worker...")
                        self.hotlist_panel.data_worker.stop()
                        # 确保线程完全停止
                        if not self.hotlist_panel.data_worker.wait(3000):
                            logger.warning("HotlistPanel data_worker did not stop, terminating...")
                            self.hotlist_panel.data_worker.terminate()
                            self.hotlist_panel.data_worker.wait(500)
                # 然后关闭面板
                self.hotlist_panel.close()
            except Exception as e:
                logger.warning(f"Error closing hotlist_panel: {e}")

        if hasattr(self, 'signal_log_panel') and self.signal_log_panel:
            logger.debug("Closing SignalLogPanel...")
            try:
                self.signal_log_panel.close()
            except Exception as e:
                logger.warning(f"Error closing signal_log_panel: {e}")

        # 0.2️⃣ 停止所有定时器
        if hasattr(self, 'realtime_timer') and self.realtime_timer:
            self.realtime_timer.stop()
        if hasattr(self, 'command_timer') and self.command_timer:
            self.command_timer.stop()

        # [FIX] 通知 Monitor 进程已退出，以便重置句柄
        try:
            from data_utils import send_code_via_pipe, PIPE_NAME_TK
            # 使用 send_code_via_pipe 发送字典指令
            send_code_via_pipe({"cmd": "VIZ_EXIT"}, logger=logger, pipe_name=PIPE_NAME_TK)
            logger.info("Sent VIZ_EXIT to Monitor.")
        except Exception as e:
            logger.warning(f"Failed to send VIZ_EXIT to Monitor: {e}")
        self._stop_realtime_process()
        if hasattr(self, 'refresh_flag'):
            self.refresh_flag.value = False

        # 2️⃣ 停止 realtime_process
        # if getattr(self, 'realtime_process', None):
        #     if self.realtime_process.is_alive():
        #         self.realtime_process.join(timeout=3) # ⬅️ [FIX] 增加等待时间
        #         if self.realtime_process.is_alive():
        #             logger.info("realtime_process 强制终止")
        #             self.realtime_process.terminate()
        #             self.realtime_process.join(timeout=1)
        #     self.realtime_process = None
        if getattr(self, 'realtime_process', None):
            if self.realtime_process.is_alive():
                self.realtime_process.join(timeout=2)
                if self.realtime_process.is_alive():
                    logger.warning("realtime_process force terminate")
                    self.realtime_process.terminate()
                    self.realtime_process.join(timeout=1)
                    if self.realtime_process.is_alive():
                        logger.error("realtime_process still alive after terminate")
            self.realtime_process = None

        # 3️⃣ 停止 DataLoaderThread (避免 QThread Destroyed 崩溃)
        # 先清理垃圾回收站中的线程
        if hasattr(self, 'garbage_threads'):
            logger.debug(f"Cleaning up {len(self.garbage_threads)} garbage threads...")
            for thread in self.garbage_threads:
                if thread and thread.isRunning():
                    thread.stop()
                    if not thread.wait(1000):
                        thread.terminate()
                        thread.wait(500)
            self.garbage_threads.clear()
        
        # 然后停止主 loader
        if hasattr(self, 'loader') and self.loader:
            logger.debug("Stopping main DataLoaderThread...")
            self.loader.stop()          # 通知线程退出
            self.loader.wait()          # ⬅️ 阻塞直到 run() 结束（关键）
            self.loader.deleteLater()   # 交给 Qt 事件循环安全释放
            self.loader = None
        
        # 3.4️⃣ 停止 CommandListenerThread (1110)
        if hasattr(self, 'command_listener_thread') and self.command_listener_thread:
            logger.debug("Stopping CommandListenerThread...")
            self.command_listener_thread.stop()
            self.command_listener_thread.wait()   # ⬅️ 同样必须等待
            self.command_listener_thread.deleteLater()
            self.command_listener_thread = None
            
        # 3.5️⃣ 清理回收站中的线程
        if hasattr(self, 'garbage_threads'):
            while self.garbage_threads:
                t = self.garbage_threads.pop()
                if t.isRunning():
                    logger.debug(f"Stopping scavenger thread: {id(t)}")
                    try:
                        if hasattr(t, 'stop'):
                            t.stop()
                        else:
                            t.quit()
                        t.wait()   # ⬅️ 必须等待线程结束
                    except Exception as e:
                        logger.warning(f"Error stopping thread {id(t)}: {e}")
                t.deleteLater()

        # 当 GUI 关闭时，触发 stop_event
        stop_event.set()

        # 3.6️⃣ 停止日志，防止 BrokenPipeError (放在最后一步)
        try:
            from JohnsonUtil.LoggerFactory import stopLogger
            stopLogger()
        except:
            pass

        print(f'closeEvent: OK')
        # Accept the event to close
        event.accept()
        # 6️⃣ 调用父类 closeEvent
        super().closeEvent(event)

    # # ================== 热点自选面板回调 ==================
    # def _toggle_hotlist_panel(self):
    #     """Alt+H: 切换热点面板显示/隐藏"""
    #     if hasattr(self, 'hotlist_panel'):
    #         if self.hotlist_panel.isVisible():
    #             self.hotlist_panel.hide()
    #             logger.info("隐藏热点面板")
    #         else:
    #             self.hotlist_panel.show()
    #             self.hotlist_panel.raise_()  # 确保在最前面
    #             logger.info("显示热点面板")

    def _add_to_hotlist(self):
        """快捷键H: 添加当前股票到热点列表"""
        if not self.current_code:
            logger.info("无当前股票，无法添加热点")
            return
        
        code = self.current_code
        name = self.code_name_map.get(code, "")
        
        # 获取当前价格
        price = 0.0
        if not self.df_all.empty and code in self.df_all.index:
            row = self.df_all.loc[code]
            price = row.get('close', row.get('price', 0))
        elif not self.day_df.empty:
            price = self.day_df['close'].iloc[-1] if 'close' in self.day_df.columns else 0
        
        if hasattr(self, 'hotlist_panel'):
            if self.hotlist_panel.contains(code):
                logger.info(f"热点已存在: {code} {name}")
            else:
                success = self.hotlist_panel.add_stock(code, name, float(price), "手动添加")
                if success:
                    logger.info(f"🔥 添加热点: {code} {name} @ {float(price):.2f}")
                    # 如果面板隐藏，自动显示
                    if not self.hotlist_panel.isVisible():
                        self.hotlist_panel.show()

    def _on_hotlist_stock_selected(self, code: str, name: str):
        """热点列表单击: 切换到该股票"""
        if code and code != self.current_code:
            self.load_stock_by_code(code, name)
    
    def _on_hotlist_voice_alert(self, code: str, msg: str):
        """热点面板语音通知 - 同时更新信号日志面板"""
        try:
            # 1. 过滤逻辑：买卖、低开走高、强势
            is_valid = any(kw in msg for kw in ['买入', '卖出', '低开走高', '强势'])
            if not is_valid:
                return

            # ⚡ [NEW] 细化过滤：低开走高模型 只要 早盘最低点即开盘点 的个股
            # if '低开走高' in msg and not any(kw in msg for kw in ['强势', '买入', '卖出']):
            #     if hasattr(self, 'df_all') and not self.df_all.empty and code in self.df_all.index:
            #         row = self.df_all.loc[code]
            #         o = row.get('open', 0)
            #         l = row.get('low', 0)
            #         if o > l > 0:
            #             return

            is_muted = hasattr(self, 'hotlist_panel') and self.hotlist_panel._voice_paused
            
            # 2. 更新信号日志面板 (详尽信息模式)
            if hasattr(self, 'signal_log_panel'):
                from datetime import datetime
                timestamp = datetime.now().strftime('%H:%M:%S')
                name = self.code_name_map.get(code, code)
                pattern = 'ALERT'
                if '状态变更' in msg:
                    pattern = 'STATUS'
                
                full_detail = f"[{timestamp}] {name}({code}) {msg}"
                
                if not self.signal_log_panel.isVisible():
                    self.signal_log_panel.show()
                    self.signal_log_panel.raise_()
                self.signal_log_panel.append_log(code, name, pattern, full_detail, is_high_priority=False)
            
            # 3. 播放语音
            # ⚡ [REMOVED] 已重构，由 signal_log_panel.log_added 信号统一触发同步播报
            # if hasattr(self, 'voice_thread') and self.voice_thread:
            #     if not is_muted:
            #         self.voice_thread.speak(f"{msg}")
            else:
                logger.debug(f"Voice thread not available, skipping: {msg}")
        except Exception as e:
            logger.error(f"Hotlist voice alert error: {e}")


    def _on_hotlist_double_click(self, code: str, name: str, add_price: float):
        """热点列表双击: 打开详情弹窗"""
        logger.info(f"打开热点详情: {code} {name} (加入价: {add_price:.2f})")
        
        # 先加载该股票数据（确保K线预览可用）
        if code and code != self.current_code:
            self.load_stock_by_code(code, name)
        
        # [FIX] Extract clean code for popup if it contains metadata
        clean_code = code.split('|')[0] if '|' in code else code
        popup = HotSpotPopup(clean_code, name, add_price, self)
        
        # 连接弹窗信号
        popup.group_changed.connect(lambda c, g: self._on_popup_group_changed(c, g))
        popup.stop_loss_set.connect(lambda c, sl: self._on_popup_stop_loss(c, sl))
        popup.item_removed.connect(lambda c: self._on_popup_remove(c))
        
        # 更新弹窗中的当前价格
        if not self.df_all.empty and code in self.df_all.index:
            row = self.df_all.loc[code]
            current_price = float(row.get('close', row.get('price', add_price)))
            popup.update_price(current_price)
        
        popup.exec()

    def _on_popup_group_changed(self, code: str, new_group: str):
        """弹窗分组变更回调"""
        if hasattr(self, 'hotlist_panel'):
            self.hotlist_panel._set_group(code, new_group)
            logger.info(f"更新分组: {code} -> {new_group}")

    def _on_popup_stop_loss(self, code: str, stop_loss: float):
        """弹窗止损设置回调"""
        # TODO: 将止损写入数据库并在实时监控中使用
        logger.info(f"设置止损: {code} @ {stop_loss:.2f}")

    def _on_popup_remove(self, code: str):
        """弹窗移除回调"""
        if hasattr(self, 'hotlist_panel'):
            self.hotlist_panel.remove_stock(code)
            logger.info(f"从热点移除: {code}")


def run_visualizer(initial_code=None, df_all=None):
    """
    启动 Visualizer GUI。
    - initial_code: optional str, 首次加载的股票 code
    - df_all: optional pd.DataFrame, 用于主程序同步数据
    """
    app = QApplication(sys.argv)
    window = MainWindow()
    
    # 如果有 df_all, 直接更新
    if df_all is not None:
        window.update_df_all(df_all)
    
    # Load initial code
    if initial_code:
        if len(initial_code) == 6 or len(initial_code) == 8:
            window.load_stock_by_code(initial_code)
    
    window.show()
    sys.exit(app.exec())

def main(initial_code='000002', stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
    import pyqtgraph as pg
    pg.setConfigOptions(antialias=True)
    # ⭐ 启用底层故障捕捉，以便锁定 QThread Destroyed 等 C++ 报错
    try:
        import faulthandler
        faulthandler.enable()
    except Exception:
        pass

    # ------------------ 1. Logger ------------------
    if log_level is not None:
        logger.setLevel(log_level.value)

    # ------------------ 2. Primary/Secondary ------------------
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Windows 下不要开启 SO_REUSEADDR 否则可以重复绑定
    stop_flag = stop_flag if stop_flag else mp.Value('b', True)
    # import ipdb;ipdb.set_trace()
    
    try:
        server_socket.bind((IPC_HOST, IPC_PORT))
        server_socket.listen(5)  # backlog > 1
        is_primary_instance = True
        print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    except OSError:
        is_primary_instance = False
        print(f"Listening 被占用 {IPC_HOST}:{IPC_PORT}")

    # ------------------ 3. Secondary ------------------
    if not is_primary_instance:
        code_to_send = initial_code if initial_code else (sys.argv[1] if len(sys.argv) > 1 else None)
        if code_to_send:
            # 尝试多次连接，保证 Primary 还没完全 accept 也能发
            for _ in range(5):
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_socket.connect((IPC_HOST, IPC_PORT))
                    client_socket.send(code_to_send.encode("utf-8"))
                    client_socket.close()
                    break
                except Exception:
                    time.sleep(0.05)
            else:
                print(f"Failed to send command: {code_to_send}")
        sys.exit(0)

    # ------------------ 4. Primary: 启动 GUI ------------------
    ret = 1
    try:
        app = QApplication(sys.argv)
        window = MainWindow(stop_flag, log_level, debug_realtime, command_queue=command_queue)
        
        # ⭐ [Refactor] 将 ListenerThread 移入 window 内部管理，确保统一清理
        window.command_listener_thread = CommandListenerThread(server_socket)
        # ⭐ [FIX] 使用 process_ipc_command 处理所有 IPC 指令 (含 SIGNAL)
        window.command_listener_thread.command_received.connect(window.process_ipc_command)
        window.command_listener_thread.dataframe_received.connect(window.on_dataframe_received)
        window.command_listener_thread.start()

        start_code = initial_code

        # ------------------ 5. 显示 GUI ------------------
        window.show()
        if start_code is not None:
            window.load_stock_by_code(start_code)
        elif len(sys.argv) > 1:
            start_code = sys.argv[1]
            if len(start_code) in (6, 8):
                window.load_stock_by_code(start_code)

        # [FIX] Connect aboutToQuit to ensure cleanup happens while event loop is still running
        app.aboutToQuit.connect(window.close)

        ret = app.exec()  # 阻塞 Qt 主循环

    except Exception as e:
        logger.error(f"Error during GUI initialization or execution: {e}")
        import traceback
        traceback.print_exc()
        if stop_flag:
            stop_flag.value = False
        sys.exit(1)
    finally:
        if stop_flag:
            stop_flag.value = False
        sys.exit(ret)


def main_src(initial_code='000002', stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
    # ⭐ 启用底层故障捕捉
    try:
        import faulthandler
        faulthandler.enable()
        import signal
        # Handle Ctrl+C (SIGINT) for clean exit
        signal.signal(signal.SIGINT, signal.SIG_DFL) 
    except Exception:
        pass

    # --- 1. 尝试成为 Primary Instance ---
        # logger = LoggerFactory.getLogger()
    if log_level is not None:
        logger.setLevel(log_level.value)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    stop_flag = stop_flag if stop_flag else mp.Value('b', True)   # 出厂运行
    try:
        server_socket.bind((IPC_HOST, IPC_PORT))
        server_socket.listen(1)
        is_primary_instance = True
        print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    except OSError:
        is_primary_instance = False
        print(f"Listening 被占用 {IPC_HOST}:{IPC_PORT}")

    # --- 2. Secondary Instance: 发送 code 给 Primary Instance 后退出 ---
    if not is_primary_instance:
        if len(sys.argv) > 1 or initial_code is not None:
            code_to_send = initial_code if initial_code is not None else sys.argv[1]
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.connect((IPC_HOST, IPC_PORT))
                client_socket.send(code_to_send.encode('utf-8'))
                client_socket.close()
                # print(f"Sent command: {code_to_send}")
            except Exception as e:
                print(f"Failed to send command: {e}")
        sys.exit(0)

    # --- 3. Primary Instance: 启动 GUI ---
    app = QApplication(sys.argv)
    window = MainWindow(stop_flag, log_level, debug_realtime, command_queue=command_queue)
    start_code = initial_code
    # 启动监听线程，处理 socket 消息
    listener = CommandListenerThread(server_socket)
    # ⭐ [FIX] 使用 process_ipc_command 分发指令
    listener.command_received.connect(window.process_ipc_command)
    # listener.dataframe_received.connect(window.update_df_all)
    listener.dataframe_received.connect(window.on_dataframe_received)
    # listener.command_received.connect(lambda: window.raise_())
    # listener.command_received.connect(lambda: window.activateWindow())
    listener.start()

    window.show()
    # 如果 exe 启动时带了参数
    if start_code is not None:
        window.load_stock_by_code(start_code)
    elif len(sys.argv) > 1:
        start_code = sys.argv[1]
        if len(start_code) in (6, 8):
            window.load_stock_by_code(start_code)
    ret = app.exec()  # 阻塞 Qt 主循环
    # 确保所有后台进程被杀
    stop_flag.value = False
    window.close()  # 触发 closeEvent
    sys.exit(ret)




                
if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    # logger.setLevel(LoggerFactory.INFO)
    import argparse
    LOG_LEVEL_MAP = {
        "debug": LoggerFactory.DEBUG,
        "info": LoggerFactory.INFO,
        "warning": LoggerFactory.WARNING,
        "error": LoggerFactory.ERROR,
    }

    def parse_args():
        parser = argparse.ArgumentParser(description="Realtime Stock Visualizer")

        parser.add_argument(
            "-log",
            "--log-level",
            default="debug",
            choices=LOG_LEVEL_MAP.keys(),
            help="Log level: debug / info / warning / error"
        )

        parser.add_argument(
            "-realtime",
            action="store_true",
            help="Force realtime mode even outside trading hours"
        )

        parser.add_argument(
            "-code",
            default="000002",
            help="Initial stock code"
        )

        return parser.parse_args()


    args = parse_args()

    # logger 本身
    logger.setLevel(LOG_LEVEL_MAP[args.log_level])

    # multiprocessing 共享变量
    stop_flag = mp.Value('b', True)
    log_level = mp.Value('i', LOG_LEVEL_MAP[args.log_level])

    realtime = args.realtime
    initial_code = args.code

    logger.info(
        f"Starting app | code={initial_code} "
        f"log={args.log_level} debug_realtime={realtime}"
    )

    try:
        main(
            initial_code=initial_code,
            stop_flag=stop_flag,
            log_level=log_level,
            debug_realtime=realtime,
            command_queue=None  # CLI 启动模式下暂无外部队列
        )
    except KeyboardInterrupt:
        logger.info("Application terminated by user (Ctrl+C).")
        if stop_flag:
            stop_flag.value = False
        sys.exit(0)
    except Exception as e:
        logger.error(f"Critical error in main: {e}")
        import traceback
        traceback.print_exc()
        if stop_flag:
            stop_flag.value = False
        sys.exit(1)

    # logger.setLevel(LoggerFactory.DEBUG)
    # stop_flag =  mp.Value('b', True)   # 出厂运行
    # log_level = mp.Value('i', LoggerFactory.DEBUG)  # 'i' 表示整数
    # debug_realtime = False
    # main(initial_code='000002',stop_flag=stop_flag,log_level=log_level,debug_realtime=debug_realtime)



    # # 1. Try to become the Primary Instance
    # logger.setLevel(LoggerFactory.DEBUG)
    # server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # try:
    #     server_socket.bind((IPC_HOST, IPC_PORT))
    #     server_socket.listen(1)
    #     print(f"Listening on {IPC_HOST}:{IPC_PORT}")
    #     is_primary_instance = True
    # except OSError:
    #     # Port already in use -> Secondary Instance
    #     is_primary_instance = False
    
    # # 2. Secondary Instance Logic: Send args and exit
    # if not is_primary_instance:
    #     if len(sys.argv) > 1:
    #         code_to_send = sys.argv[1]
    #         try:
    #             client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #             client_socket.connect((IPC_HOST, IPC_PORT))
    #             client_socket.send(code_to_send.encode('utf-8'))
    #             client_socket.close()
    #             print(f"Sent command: {code_to_send}")
    #         except Exception as e:
    #             print(f"Failed to send command: {e}")
    #     else:
    #         print("Visualizer is already running.")
    #         # Bring to front? context dependent.
        
    #     sys.exit(0)

    # # 3. Primary Instance Logic: Start GUI
    # app = QApplication(sys.argv)
    # window = MainWindow()
    
    # # Start Listener
    # listener = CommandListenerThread(server_socket)
    # listener.command_received.connect(window.load_stock_by_code)
    # listener.dataframe_received.connect(window.update_df_all)  # Handle df_all updates
    # listener.command_received.connect(lambda: window.raise_()) # Bring to front
    # listener.command_received.connect(lambda: window.activateWindow())
    # listener.start()

    # window.show()
    
    # # Check CLI args for initial load
    # if len(sys.argv) > 1:
    #     start_code = sys.argv[1]
    #     if len(start_code) == 6 or len(start_code) == 8:
    #          window.load_stock_by_code(start_code)

    # sys.exit(app.exec())


    # import socket

    # # 判断是否有参数
    # code_arg = sys.argv[1] if len(sys.argv) > 1 else None

    # # 单实例逻辑
    # server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # try:
    #     server_socket.bind((IPC_HOST, IPC_PORT))
    #     server_socket.listen(1)
    #     is_primary_instance = True
    # except OSError:
    #     is_primary_instance = False

    # if not is_primary_instance:
    #     if code_arg:
    #         try:
    #             client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #             client_socket.connect((IPC_HOST, IPC_PORT))
    #             client_socket.send(code_arg.encode('utf-8'))
    #             client_socket.close()
    #             print(f"Sent command: {code_arg}")
    #         except Exception as e:
    #             print(f"Failed to send command: {e}")
    #     sys.exit(0)

    # # Primary Instance
    # open_visualizer(code=code_arg)
