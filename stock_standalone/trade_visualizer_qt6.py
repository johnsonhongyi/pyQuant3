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

import pandas as pd
import numpy as np
import pyqtgraph as pg

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
    QActionGroup, QShortcut, QKeySequence
)
from PyQt6 import sip

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
from data_utils import (
    calc_compute_volume, calc_indicators, fetch_and_process, send_code_via_pipe)

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

# Configuration for pyqtgraph
pg.setConfigOptions(antialias=True)
# pg.setConfigOption('background', 'w')
# pg.setConfigOption('foreground', 'k')


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


class VoiceThread(QThread):
    """语音播报线程 (完全后台运行，不阻塞主线程)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue = Queue()
        self.running = True
        self.engine = None

    def run(self):
        """语音线程主循环"""
        logger.info("✅ 语音播报线程已启动")
        
        while self.running:
            try:
                # 批量获取队列中的所有消息
                messages = []
                try:
                    # 获取第一条消息（阻塞等待 1s）
                    text = self.queue.get(timeout=1)
                    messages.append(text)
                    
                    # 获取队列中剩余的所有消息（非阻塞）
                    while not self.queue.empty():
                        try:
                            text = self.queue.get_nowait()
                            messages.append(text)
                        except Empty:
                            break
                except Empty:
                    continue
                
                # 依次播报所有消息
                logger.info(f"🔊 开始播报 {len(messages)} 条消息")
                for i, msg in enumerate(messages, 1):
                    if not self.running:
                        break
                    
                    # 对每一条消息采用独立的初始化和清理流程，确保 SAPI5 稳定
                    self._speak_one(msg, i, len(messages))
                
                logger.info(f"✅ 播报处理完成")
                    
            except Exception as e:
                logger.warning(f"Voice thread loop error: {e}")

    def _speak_one(self, text: str, index: int, total: int):
        """
        单次播报逻辑，包含完整的初始化和清理。
        Windows SAPI5 在多线程环境下，长时间持有 Engine 或频繁调用 runAndWait 容易出现状态同步问题。
        采用“一报一初始化”模式虽然稍慢，但最稳定。
        """
        import pyttsx3
        import time
        engine = None
        try:
            if pythoncom:
                pythoncom.CoInitialize()
            
            engine = pyttsx3.init()
            self.engine = engine # 暴露给 stop() 使用
            
            # 语速调整
            rate = engine.getProperty('rate')
            if isinstance(rate, (int, float)):
                engine.setProperty('rate', rate + 40)  # 加速
            
            # 规范化文本
            speech_text = normalize_speech_text(text)
            logger.debug(f"  正在播报 [{index}/{total}]: {speech_text}")
            
            engine.say(speech_text)
            # runAndWait 在当前线程阻塞，直到该段语音播报完毕
            engine.runAndWait()
            
            logger.debug(f"  ✅ 播报完成 [{index}/{total}]")
            
            # 增加短暂停顿，给系统语音组件喘息机会
            time.sleep(0.1)
            
        except Exception as e:
            logger.warning(f"  ⚠️ 播报错误 [{index}/{total}]: {e}")
        finally:
            if engine:
                try:
                    engine.stop()
                    del engine
                except:
                    pass
            self.engine = None
            if pythoncom:
                try:
                    pythoncom.CoUninitialize()
                except:
                    pass

    def speak(self, text):
        """添加文本到播报队列"""
        if self.running:
            self.queue.put(text)

    def stop(self):
        """停止语音线程"""
        self.running = False
        # 清空队列
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Empty:
                break
        self.wait(2000)  # 等待最备2秒


class CandlestickItem(pg.GraphicsObject):
    def __init__(self, data, theme='light'):
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

        self.text_items = []

    def clear(self):
        """清理所有信号标记"""
        self.kline_scatter.clear()
        self.tick_scatter.clear()
        for item in self.text_items:
            # 尝试从两个图中移除，忽略错误
            if item.scene():
                item.scene().removeItem(item)
        self.text_items.clear()

    def update_signals(self, signals: list[SignalPoint], target='kline'):
        """
        更新信号显示
        :param signals: SignalPoint 列表
        :param target: 'kline' 或 'tick'
        """
        plot = self.kline_plot if target == 'kline' else self.tick_plot
        scatter = self.kline_scatter if target == 'kline' else self.tick_scatter

        if not signals:
            scatter.clear()
            return

        xs, ys, brushes, symbols, sizes, data = [], [], [], [], [], []

        for sig in signals:
            xs.append(sig.bar_index)
            ys.append(sig.price)
            brushes.append(pg.mkBrush(sig.color))
            symbols.append(sig.symbol)
            sizes.append(sig.size)
            # data 存储 meta 信息供点击回调使用
            data.append(sig.to_visual_hit()['meta'])

            # 添加价格文字标签
            is_buy = sig.signal_type in (SignalType.BUY, SignalType.ADD)
            anchor = (0.5, 1.2) if is_buy else (0.5, -0.2)
            # 颜色适配主题
            text_color = (255, 120, 120) if is_buy else (120, 255, 120)

            txt = pg.TextItem(text=f"{sig.price:.2f}", anchor=anchor, color=text_color)
            txt.setPos(sig.bar_index, sig.price)
            plot.addItem(txt)
            self.text_items.append(txt)

        scatter.setData(x=xs, y=ys, brush=brushes, symbol=symbols, size=sizes, data=data)

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
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
        self.wait(1000)

    def run(self):
        while self.running:
            try:
                # accept 阻塞，直到有客户端连接
                client_socket: socket.socket
                client_socket, _ = self.server_socket.accept()
                client_socket.settimeout(3.0)

                try:
                    # 前4字节协议判断
                    prefix = client_socket.recv(4)
                    if not prefix:
                        client_socket.close()
                        continue

                    if prefix == b"DATA":
                        try:
                            header = client_socket.recv(4)
                            if not header:
                                client_socket.close()
                                continue
                            size = struct.unpack("!I", header)[0]
                            payload: bytes = b""
                            while len(payload) < size:
                                chunk: bytes = client_socket.recv(size - len(payload))
                                if not chunk:
                                    break
                                payload += chunk
                            if payload:
                                # ⭐ 兼容旧格式 (tuple) 和新格式 (dict package)
                                raw_data = pickle.loads(payload)
                                if isinstance(raw_data, tuple) and len(raw_data) == 2:
                                    msg_type, df = raw_data
                                    if msg_type == 'UPDATE_DF_DATA' and isinstance(df, dict):
                                        # 新版字典协议：{'type': '...', 'data': df, 'ver': 123}
                                        self.dataframe_received.emit(df, 'UPDATE_DF_DATA')
                                    else:
                                        # 旧版元组协议：('UPDATE_DF_ALL', df)
                                        self.dataframe_received.emit(df, msg_type)
                        except Exception as e:
                            print(f"[IPC] Drop DATA packet: {e}")

                    else:
                        try:
                            rest = client_socket.recv(4096)
                            text = (prefix + rest).decode("utf-8", errors="ignore").strip()
                            if text.startswith("CODE|"):
                                code = text[5:].strip()
                                if code:
                                    self.command_received.emit(code)
                            elif text:
                                self.command_received.emit(text)
                        except Exception as e:
                            print(f"[IPC] Drop CODE packet: {e}")
                finally:
                    try:
                        client_socket.close()
                    except Exception:
                        pass

            except Exception as e:
                if self.running:
                    print(f"[IPC] Listener Loop Error: {e}")
                else:
                    break
        print("[IPC] CommandListenerThread exited cleanly")



duration_date_day = 120
duration_date_up = 250      #
# duration_date_up = 190
# duration_date_up = 120
duration_date_week = 500    #3-ma60d
# duration_date_month = 300
duration_date_month = 1000    #3-ma20d
#m : 510 ma26

Resample_LABELS_Days = {'d':duration_date_day,'3d':duration_date_up,
                      'w':duration_date_week,'m':duration_date_month}

class DataLoaderThread(QThread):
    data_loaded: pyqtSignal = pyqtSignal(object, object, object) # code, day_df, tick_df
    code: str
    resample: str
    mutex_lock: QMutex
    _search_code: Optional[str]
    _resample: Optional[str]

    def __init__(self, code: str, mutex_lock: QMutex, resample: str = 'd') -> None:
        super().__init__()
        self.code = code
        self.resample = resample
        self.mutex_lock = mutex_lock # 存储锁对象
        self._search_code = None
        self._resample = None

    def run(self) -> None:
            try:
                # 使用 QMutexLocker 自动管理锁定和解锁
                if self._search_code == self.code and self._resample == self.resample:
                    return  # 数据已经加载过，不重复
                with QMutexLocker(self.mutex_lock):
                    # 1. Fetch Daily Data (Historical)
                    # tdd.get_tdx_Exp_day_to_df 内部调用 HDF5 API，必须在锁内执行
                    with timed_ctx("get_tdx_Exp_day_to_df", warn_ms=800):
                       day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True)
                       # day_df = tdd.get_tdx_Exp_day_to_df(self.code, dl=ct.Resample_LABELS_Days[self.resample],resample=self.resample,fastohlc=True)

                    # 2. Fetch Realtime/Tick Data (Intraday)
                    # 假设此操作不涉及 HDF5，可以在锁外执行
                    with timed_ctx("get_real_time_tick", warn_ms=800):
                       tick_df = sina_data.Sina().get_real_time_tick(self.code)

                self._search_code = self.code
                self._resample = self.resample
                with timed_ctx("emit", warn_ms=800):
                       self.data_loaded.emit(self.code, day_df, tick_df)
            except Exception as e:
                print(f"Error loading data for {self.code}: {e}")
                # 确保即使发生错误，信号也能发出
                import traceback
                traceback.print_exc()
                self.data_loaded.emit(self.code, pd.DataFrame(), pd.DataFrame())



def tick_to_daily_bar(tick_df: pd.DataFrame) -> pd.DataFrame:
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

    # today = pd.Timestamp.today().normalize()
    # df = df[df['_date'] == today]
    # 获取今天的日期（不带时间）
    today = pd.Timestamp.today().normalize()

    # 筛选今天的数据
    df = df[df['_date'] == today]

    # # 将 dt 和 ticktime 拼接成完整时间字符串，再转 datetime
    # df['ticktime'] = pd.to_datetime(
    #     df['dt'].astype(str) + ' ' + df['ticktime'].astype(str),
    #     format='%Y-%m-%d'
    # )
    today = pd.Timestamp.today().normalize().strftime('%Y-%m-%d')

    if df.empty:
        return pd.DataFrame()

    # === 2. 价格列统一 ===
    # 你的真实价格列是 close
    price_col = 'close'

    bar = pd.DataFrame(
        {
            'open':   [df[price_col].iloc[0]],
            'high':   [df[price_col].max()],
            'low':    [df[price_col].min()],
            'close':  [df[price_col].iloc[-1]],
            'volume': [df['volume'].iloc[-1]],  # 注意：你的 volume 是累计量
        },
        index=[today],
    )
    logger.debug(f'bar: {bar} df:{df.high.max()}')
    return bar

def realtime_worker_process(code, queue, stop_flag,log_level=None,debug_realtime=False,interval=cct.sina_limit_time):
    """多进程拉取实时数据"""
    # if log_level:
    #     logger = LoggerFactory.getLogger()
    #     if log_level is not None:
    #         logger.setLevel(log_level.value)
    s = sina_data.Sina()
    # while True:
    count_debug = 0
    while  stop_flag.value:   # 👈 关键
        try:
            # if cct.get_trade_date_status() and cct.get_now_time_int() > 920 or not cct.get_trade_date_status():
            if (cct.get_work_time() and cct.get_now_time_int() > 923) or debug_realtime:
                with timed_ctx("realtime_worker_process", warn_ms=800):
                    tick_df = s.get_real_time_tick(code)
                    # 这里可以生成今天的 day_bar
                    # if log_level and tick_df is None or tick_df.empty:
                    #     logger.warning(
                    #         f"[RT] tick_df EMPTY | code={code} | "
                    #         f"trade={cct.get_trade_date_status()} "
                    #         f"time={cct.get_now_time_int()}"
                    #     )
                    #     time.sleep(interval)
                    #     continue
                with timed_ctx("realtime_worker_tick_to_daily_bar", warn_ms=800):
                    today_bar = tick_to_daily_bar(tick_df)
                    # if log_level and today_bar is None or today_bar.empty:
                    #     logger.warning(
                    #         f"[RT] today_bar EMPTY | code={code} | "
                    #         f"today_bar_rows={len(today_bar)} | "
                    #         f"today_bar_cols={list(today_bar.columns)}"
                    #     )
                    #     time.sleep(interval)
                    #     continue
                    try:
                        # # queue.put((code, tick_df, today_bar))
                        # if log_level and count_debug == 0 and debug_realtime:
                        #     logger.debug(
                        #             f"[RT] tick_df | code={code} | "
                        #             f"tick_rows={len(tick_df)} | "
                        #             f"tick_cols={list(tick_df.columns)}"
                        #             f"tick={(tick_df[-3:])}"
                        #         )
                        #     # dump_path = cct.get_ramdisk_path(f"{code}_tick_{int(time.time())}.pkl")
                        #     # tick_df.to_pickle(dump_path)
                        #     logger.debug(
                        #             f"[RT] today_bar | code={code} | "
                        #             f"today_barrows={len(today_bar)} | "
                        #             f"today_bar_cols={list(today_bar.columns)}"
                        #             f"today_bar=\n{(today_bar)}"
                        #         )
                        #     # dump_path = cct.get_ramdisk_path(f"{code}_today_{int(time.time())}.pkl")
                        #     # today_bar.to_pickle(dump_path)
                        #     # count_debug += 1
                        queue.put_nowait((code, tick_df, today_bar))
                    except queue.Full:
                        pass  # 队列满了就跳过，避免卡住
        except Exception as e:
            import traceback
            traceback.print_exc()
            time.sleep(interval)  # 避免无限抛异常占用 CPU
        if stop_flag.value:
            for _ in range(interval):
                if not stop_flag.value:
                    break
                time.sleep(1)
    # print(f'stop_flag: {stop_flag.value}')

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
try:
    from signal_message_queue import SignalMessageQueue, SignalMessage
    SIGNAL_QUEUE_AVAILABLE = True
except ImportError:
    SIGNAL_QUEUE_AVAILABLE = False
    class SignalMessage: pass

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
        btn_refresh = QtWidgets.QPushButton("🔄 刷新")
        btn_refresh.clicked.connect(self.refresh)
        top_layout.addWidget(btn_refresh)
        layout.addLayout(top_layout)

        # 2. 分类标签页
        self.tabs = QtWidgets.QTabWidget()

        # 创建各分类表格
        self.tables['all'] = self._create_table()
        self.tables['main'] = self._create_table()
        self.tables['startup'] = self._create_table()
        self.tables['sudden'] = self._create_table()

        self.tabs.addTab(self.tables['all'], "全部 (All)")
        self.tabs.addTab(self.tables['main'], "🔥 主升浪 (Hot)")
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
        cols = ["时间", "代码", "名称", "类型", "理由", "评分", "热度", "天数", "操作"]
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        # 热度和天数列宽度固定
        table.setColumnWidth(6, 40)  # 热度
        table.setColumnWidth(7, 40)  # 天数
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.doubleClicked.connect(self._on_table_double_clicked)
        # ⭐ 启用列排序功能
        table.setSortingEnabled(True)
        return table

    def refresh(self):
        if not self._queue_mgr:
            self.status_label.setText("信号队列服务不可用")
            return

        signals = self._queue_mgr.get_top()
        self.status_label.setText(f"总信号: {len(signals)} 条")

        # ⭐ 暂时禁用排序，加快数据填充
        for t in self.tables.values():
            t.setSortingEnabled(False)

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

            # 3. 启动蓄势 (Conso)
            elif msg.signal_type == 'CONSOLIDATION':
                self._add_row(self.tables['startup'], msg)

            # 4. 突发 (Sudden / Alert)
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
        table.setItem(row_idx, 3, type_item)

        # 4. 理由
        table.setItem(row_idx, 4, QtWidgets.QTableWidgetItem(msg.reason))

        # 5. 评分
        score_item = QtWidgets.QTableWidgetItem(f"{msg.score:.2f}")
        table.setItem(row_idx, 5, score_item)

        # 6. 热度 (count)
        count = getattr(msg, 'count', 1)
        count_item = QtWidgets.QTableWidgetItem(str(count))
        count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 6, count_item)
        
        # 7. 连续天数 (consecutive_days)
        consecutive_days = getattr(msg, 'consecutive_days', 1)
        days_item = QtWidgets.QTableWidgetItem(str(consecutive_days))
        days_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row_idx, 7, days_item)

        # 热度染色逻辑 (基于 self.heat_spin.value())
        # 如果 now - msg.timestamp > heat_period, 则视为冷却 (变灰)
        try:
            heat_min = self.heat_spin.value()
            msg_time = datetime.strptime(msg.timestamp, "%Y-%m-%d %H:%M:%S")
            diff_min = (datetime.now() - msg_time).total_seconds() / 60
            
            is_cool = diff_min > heat_min
            
            if is_cool:
                # 冷却样式: 全行灰色/斜体
                for c in range(8): # Adjusted for new column
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

        # 8. 操作 (跟单 checkbox)
        follow_widget = QtWidgets.QWidget()
        follow_layout = QtWidgets.QHBoxLayout(follow_widget)
        follow_layout.setContentsMargins(0, 0, 0, 0)
        follow_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        follow_cb = QtWidgets.QCheckBox("跟单")
        followed = getattr(msg, 'followed', False)
        follow_cb.setChecked(followed)
        follow_cb.stateChanged.connect(lambda checked, m=msg: self._on_follow_toggled(m, checked))
        follow_layout.addWidget(follow_cb)
        table.setCellWidget(row_idx, 8, follow_widget)
        
        # 9. 已评估标记 (灰化)
        evaluated = getattr(msg, 'evaluated', False)
        if evaluated:
            for c in range(9):  # Updated to 9 columns
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

            price, ok = QtWidgets.QInputDialog.getDouble(self, "跟单确认",
                                                       f"确认跟踪 {msg.name}({msg.code})?\n输入当前价格:",
                                                       value=0.0, decimals=2)
            if ok:
                stop_loss, ok2 = QtWidgets.QInputDialog.getDouble(self, "设置止损",
                                                                "输入止损价格:",
                                                                value=price*0.95, decimals=2)
                if ok2:
                    self._queue_mgr.add_follow(msg, price, stop_loss)
                    self.refresh()
            else:
                self.refresh()

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
        self.label.setTextFormat(Qt.TextFormat.RichText)
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

    def eventFilter(self, obj, event):
        # 检查主窗口是否还存在
        if not hasattr(self, 'main_window') or sip.isdeleted(self.main_window):
            return False

        # App-wide 模式: 不检查窗口激活状态，只要应用程序有焦点即可
        # 注意: Qt 不支持真正的系统级快捷键，这是应用程序级别的最大范围

        # 鼠标按键
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.XButton1:  # 前进键
                self.main_window.switch_resample_prev()
                return True
            elif event.button() == Qt.MouseButton.XButton2:  # 后退键
                self.main_window.switch_resample_next()
                return True

        # 键盘按键
        elif event.type() == QtCore.QEvent.Type.KeyPress:
            # ⭐ 避开组合键(Alt/Ctrl)，交给 QShortcut 或系统处理，防止重复响应
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ControlModifier):
                return False
                
            key = event.key()
            # --- 通达信模式: 上下左右导航 ---
            if key == Qt.Key.Key_Up:
                # 1.1: 如果左侧列表有焦点，交给列表处理翻页
                if self.main_window.stock_table.hasFocus():
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
                if self.main_window.stock_table.hasFocus():
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
            elif key == Qt.Key.Key_1:
                self.main_window.on_resample_changed('d')
                return True
            elif key == Qt.Key.Key_2:
                self.main_window.on_resample_changed('3d')
                return True
            elif key == Qt.Key.Key_3:
                self.main_window.on_resample_changed('w')
                return True
            elif key == Qt.Key.Key_4:
                self.main_window.on_resample_changed('m')
                return True
            elif key == Qt.Key.Key_Space:
                self.main_window.show_comprehensive_briefing()
                return True
            elif key == Qt.Key.Key_R:
                self.main_window._reset_kline_view()
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
                tick_df = self._sina.get_real_time_tick(self._code)
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
        
        # 统一快捷键注册
        self._init_global_shortcuts()

        # 1. 窗口基本设置
        self.setWindowTitle("PyQuant Stock Visualizer (Qt6 + PyQtGraph)")
        self.sender = StockSender(callback=None)
        self.command_queue = command_queue  # ⭐ 新增：内部指令队列
        # WindowMixin requirement: scale_factor
        self._debug_realtime = debug_realtime   # 临时调试用
        self.scale_factor = get_windows_dpi_scale_factor()
        self.hdf5_mutex = QMutex()
        self.stop_flag = stop_flag
        self.log_level = log_level
        self.resample = 'd'
        self.qt_theme = 'dark'  # 默认使用黑色主题
        self.show_bollinger = True
        self.tdx_enabled = False  # 默认开启
        self.realtime = True  # 默认开启
        # 缓存 df_all
        self.df_cache = pd.DataFrame()
        # self.realtime_worker = None
        self.last_initialized_trade_day = None  # 记录最后一次初始化的交易日
        self._closing = False
        self.realtime_queue = Queue()
        self.realtime_process = None

        # 定时检查队列
        self.realtime_timer = QTimer()
        self.realtime_timer.timeout.connect(self._poll_realtime_queue)
        self.realtime_timer.start(5000)  # 每5秒检查一次队列

        # ⭐ 新增：指令队列轮询 (处理来自 MonitorTK 的直连指令)
        if self.command_queue:
            self.command_timer = QTimer()
            self.command_timer.timeout.connect(self._poll_command_queue)
            self.command_timer.start(200)  # 200ms 轮询一次，保证响应速度

        self.day_df = pd.DataFrame()
        self.df_all = pd.DataFrame()

        # ---- resample state ----
        self.resample_keys = ['d', '3d', 'w', 'm']

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
        self.decision_engine = IntradayDecisionEngine() # ⭐ 内部决策引擎
        self.pullback_strat = StrongPullbackMA5Strategy(min_score=60) # ⭐ 强力回撤策略
        self.strategy_controller = StrategyController(self) # ⭐ 新增：统一策略控制器

        # 策略模拟开关
        self.show_strategy_simulation = True

        # --- 1. 创建工具栏 ---
        self._init_toolbar()
        self._init_resample_toolbar()
        self._init_theme_selector()
        self._init_tdx()
        self._init_real_time()

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

        # Main Layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Create a horizontal splitter for the main layout
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- Decision Panel (Phase 7) ---
        self.decision_panel = QFrame()
        self.decision_panel.setFixedHeight(40)
        self.decision_panel.setObjectName("DecisionPanel")
        self.decision_panel.setStyleSheet("""
            #DecisionPanel {
                background-color: #1a1a1a;
                border-top: 1px solid #333;
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

        self.decision_layout.addStretch()

        # 💓 Heartbeat Label (Strategy Alive Indicator)
        self.hb_label = QLabel("💓")
        self.decision_layout.addWidget(self.hb_label)

        main_layout.addWidget(self.decision_panel)


        # 1. Left Sidebar: Stock Table
        self.stock_table = QTableWidget()
        # Removed fixed maximum width to allow splitter resizing
        # self.stock_table.setMaximumWidth(300)

        # self.stock_table.setStyleSheet("""

        # QTableWidget {
        #     background-color: transparent;
        # }

        # /* 只作用在 table 内部 */
        # QTableWidget QScrollBar:vertical {
        #     width: 6px;
        #     background: transparent;
        #     margin: 0px;
        # }

        # QTableWidget QScrollBar::handle:vertical {
        #     background: rgba(180, 180, 180, 120);
        #     min-height: 30px;
        #     border-radius: 3px;
        # }

        # QTableWidget QScrollBar::handle:vertical:hover {
        #     background: rgba(220, 220, 220, 180);
        # }

        # QTableWidget QScrollBar::add-line:vertical,
        # QTableWidget QScrollBar::sub-line:vertical {
        #     height: 0px;
        # }

        # QTableWidget QScrollBar::add-page:vertical,
        # QTableWidget QScrollBar::sub-page:vertical {
        #     background: transparent;
        # }
        # """)

        # self.stock_table.setStyleSheet(self.stock_table.styleSheet() + """
        # QTableWidget::item:hover {
        #     background: rgba(255, 255, 255, 30);
        # }
        # QTableWidget::item:selected {
        #     background: rgba(255, 215, 0, 80);
        #     color: black;
        # }
        # """)

        # self.stock_table.verticalScrollBar().setFixedWidth(6)


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
                color: black;
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
        # 列名中英文映射
        self.column_map = {
            'code': '代码', 'name': '名称', 'percent': '涨幅%', 'Rank': '排名',
            'dff': 'DFF', 'win': '连阳', 'slope': '斜率', 'volume': '虚拟量', 'power_idx': '爆发力',
            'last_action': '策略动作', 'last_reason': '决策理由', 'shadow_info': '影子比对',
            'market_win_rate': '全场胜率', 'loss_streak': '连亏次数', 'vwap_bias': '均价偏离'
        }

        real_time_cols = list(cct.real_time_cols)
        strategy_cols = ['last_action', 'last_reason', 'shadow_info', 'market_win_rate', 'loss_streak', 'vwap_bias']

        # 🛡️ 整合可视化所需的核心列，确保 'dff', 'Rank' 等字段始终出现在表头
        visualizer_core_cols = ['code', 'name', 'percent', 'dff', 'Rank', 'win', 'slope', 'volume', 'power_idx']

        # 使用去重的方式合并列
        combined_header_cols = []
        source_cols = real_time_cols if len(real_time_cols) > 4 and 'percent' in real_time_cols else visualizer_core_cols
        for c in (source_cols + visualizer_core_cols + strategy_cols):
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
        # 所有列自动根据内容调整宽度
        for col in range(len(headers)):
            headers.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        # 在 MainWindow.__init__ 中修改
        self.stock_table.cellClicked.connect(self.on_table_cell_clicked) # 保留点击
        self.stock_table.currentItemChanged.connect(self.on_current_item_changed) # 新增键盘支持
        # 排序后自动滚动到顶部
        self.stock_table.horizontalHeader().sectionClicked.connect(self.on_header_section_clicked)

        # 1️⃣ 启用自定义上下文菜单
        self.stock_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stock_table.customContextMenuRequested.connect(self.on_table_right_click)

        self.stock_table.verticalHeader().setVisible(False)
        self.main_splitter.addWidget(self.stock_table)

        # 2. Right Area: Splitter (Day K-Line + Intraday)
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(right_splitter)

        # Set initial sizes for the main splitter (left table: 200, right charts: remaining)
        self.main_splitter.setSizes([200, 900])
        self.main_splitter.setCollapsible(0, False) # Prevent table from being completely hidden


        # -- Top Chart: Day K-Line
        self.kline_widget = pg.GraphicsLayoutWidget()
        self.kline_plot = self.kline_widget.addPlot(title="Daily K-Line")
        self.kline_plot.showGrid(x=True, y=True)
        self.kline_plot.setLabel('bottom', 'Date Index')
        self.kline_plot.setLabel('left', 'Price')
        # ⭐ 禁用自动范围，防止鼠标悬停时视图跳动
        self.kline_plot.disableAutoRange()
        right_splitter.addWidget(self.kline_widget)

        # --- 添加重置按钮 (只添加一次) ---
        # self._add_reset_button()

        # -- Bottom Chart: Intraday
        self.tick_widget = pg.GraphicsLayoutWidget()
        self.tick_plot = self.tick_widget.addPlot(title="Real-time / Intraday")
        self.tick_plot.showGrid(x=True, y=True)
        # ⭐ 禁用自动范围，防止鼠标悬停时视图跳动
        self.tick_plot.disableAutoRange()
        right_splitter.addWidget(self.tick_widget)

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

        # Set splitter sizes (70% top, 30% bottom)
        right_splitter.setSizes([500, 200])

        # 3. Filter Panel (Initially Hidden)
        self.filter_panel = QWidget()
        filter_layout = QVBoxLayout(self.filter_panel)
        filter_layout.setContentsMargins(0, 0, 0, 0)

        # Top Controls - 按钮行
        button_row = QHBoxLayout()

        # ⭐ 新增 History Selector ComboBox
        self.history_selector = QComboBox()
        self.history_selector.addItems(["history1", "history2", "history3", "history4"])
        self.history_selector.setCurrentIndex(3)  # 默认选 history4
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
        # from stock_feature_marker import StockFeatureMarker
        # self._filter_columns = ['code', 'name', 'rank', 'percent']  # 显示列
        # self.feature_marker = StockFeatureMarker(self.filter_tree, enable_colors=True)

        self.filter_tree.setHeaderLabels(["Filtered Results"])
        self.filter_tree.setColumnCount(1)
        self.filter_tree.itemClicked.connect(self.on_filter_tree_item_clicked)
        # 添加键盘导航支持
        self.filter_tree.currentItemChanged.connect(self.on_filter_tree_current_changed)
        
        # ⭐ 确保点击 filter_tree 任意位置都能获得键盘焦点
        self.filter_tree.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.filter_tree.viewport().installEventFilter(self)

        # 应用窄边滚动条样式，与左侧列表一致
        scrollbar_style = """
            QScrollBar:vertical {
                border: none;
                background: #2b2b2b;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #555555;
                min-height: 20px;
                border-radius: 4px;
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
        """
        self.filter_tree.setStyleSheet(scrollbar_style)
        filter_layout.addWidget(self.filter_tree)

        self.filter_panel.setVisible(False)
        self.main_splitter.addWidget(self.filter_panel)

        # 设置默认分割比例（不加载保存的设置）
        # 股票列表:过滤面板:图表区域 = 400:200:800
        self.main_splitter.setSizes([400, 200, 800])

        # 安装全局事件过滤器
        # 安装全局事件过滤器 (安装到 QApplication 以便支持 App 级全局)
        self.input_filter = GlobalInputFilter(self)
        QApplication.instance().installEventFilter(self.input_filter)
        # self.installEventFilter(self.input_filter)
        # Apply initial theme
        self.apply_qt_theme()

        # Load Stock List
        self.load_stock_list()

        # ⭐ Load saved window position (Restores size and location)
        self._window_pos_loaded = False   # ⭐ 必须加
        # self.load_window_position_qt(self, "trade_visualizer", default_width=1400, default_height=900)
        self.load_splitter_state()

    def showEvent(self, event):
        super().showEvent(event)

        if not self._window_pos_loaded:
            self._window_pos_loaded = True
            self.load_window_position_qt(
                self,
                "trade_visualizer",
                default_width=1400,
                default_height=900
            )


    def _init_global_shortcuts(self):
        """统一注册全局快捷键"""
        self.shortcuts = {}
        
        # 帮助信息配置 (Key, Desc, Handler)
        self.shortcut_map = [
            ("Alt+T", "显示/隐藏信号盒子 / 切换模拟信号(T)", self._show_signal_box),
            ("Ctrl+/", "显示快捷键帮助 (此弹窗)", self.show_shortcut_help),
            ("Space", "显示综合研报 / 弹窗详情 (K线图内生效)", None),
            ("R", "重置 K 线视图 (全览模式)", None),
            ("S", "显示策略监理 & 风控详情", None),
            ("1 / 2 / 3", "切换周期: 日线 / 3日 / 周线", None),
            ("4", "切换周期: 月线", None),
        ]
        
        # 注册非事件捕获型快捷键
        for key_seq, desc, handler in self.shortcut_map:
            if handler and key_seq != "Space": # Space in keyPressEvent
                sc = QShortcut(QKeySequence(key_seq), self)
                # 所有组合键默认为 App-wide（应用程序级别）
                # 即使子窗口（信号盒子、帮助窗口）激活时也能响应
                if "+" in key_seq:  # 检测组合键 (Alt+T, Ctrl+/ 等)
                    sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(handler)
                self.shortcuts[key_seq] = sc

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
        self.toolbar.addSeparator()

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

    def on_toggle_simulation(self, checked):
        self.show_strategy_simulation = checked
        if self.current_code:
            self.render_charts(self.current_code, self.day_df, getattr(self, 'tick_df', pd.DataFrame()))

    def on_toggle_global_keys(self, checked):
        """切换系统级全局快捷键"""
        self.global_shortcuts_enabled = checked
        if checked:
            self._register_system_hotkeys()
        else:
            self._unregister_system_hotkeys()
            
        # ⭐ 动态启用/禁用冲突的 QShortcut
        # 当开启系统全局键时，禁用 App 内的 QShortcut，防止重复响应，且确保系统键优先
        conflict_keys = ["Alt+T", "Ctrl+/"]
        if hasattr(self, 'shortcuts'):
            for key in conflict_keys:
                if key in self.shortcuts:
                    self.shortcuts[key].setEnabled(not checked)

        state = "全局模式 (System Wide)" if checked else "窗口模式 (App Wide)"
        logger.info(f"Shortcut mode changed to: {state}")
        
    def _register_system_hotkeys(self):
        """注册系统级全局快捷键 (使用 keyboard 库)"""
        if not KEYBOARD_AVAILABLE or self.system_hotkeys_registered:
            return
        
        try:
            # 定义回调函数 (必须在主线程执行)
            def _on_hotkey_show_signal_box():
                # ⭐ 已在 on_toggle_global_keys 中禁用了 QShortcut，这里直接触发即可
                QTimer.singleShot(0, self._show_signal_box)
            
            def _on_hotkey_show_help():
                # ⭐ 已在 on_toggle_global_keys 中禁用了 QShortcut，这里直接触发即可
                QTimer.singleShot(0, self.show_shortcut_help)
            
            # 注册系统全局快捷键
            keyboard.add_hotkey('alt+t', _on_hotkey_show_signal_box)
            keyboard.add_hotkey('ctrl+/', _on_hotkey_show_help)
            
            self.system_hotkeys_registered = True
            logger.info("✅ 系统级全局快捷键已注册 (Alt+T, Ctrl+/)")
        except Exception as e:
            logger.error(f"❌ 系统快捷键注册失败: {e}")
            self.global_shortcuts_enabled = False
    
    def _unregister_system_hotkeys(self):
        """注销系统级全局快捷键"""
        if not KEYBOARD_AVAILABLE or not self.system_hotkeys_registered:
            return
        
        try:
            keyboard.remove_hotkey('alt+t')
            keyboard.remove_hotkey('ctrl+/')
            self.system_hotkeys_registered = False
            logger.info("✅ 系统级全局快捷键已注销")
        except Exception as e:
            logger.warning(f"⚠️ 系统快捷键注销失败: {e}")

    def _reset_kline_view(self, df=None):
        """重置 K 线图视图：实现真正的“出厂设置”全览模式，两头留白不遮挡"""
        # 注意：如果被信号直接调用，df 可能是 bool (checked)，需排除
        if not isinstance(df, pd.DataFrame):
            df = getattr(self, 'day_df', pd.DataFrame())

        if not hasattr(self, 'kline_plot') or df.empty:
            return

        vb = self.kline_plot.getViewBox()
        n = len(df)

        # 1. 暂时启用全局自动缩放，让 pyqtgraph 找到数据边界
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        vb.autoRange()

        # 2. 手动微调 X 轴：开启“固定模式”，设置完美的全览范围
        # 左侧留 1 根，右侧留 3 根（给信号箭头和最新 ghost 留位置）
        vb.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
        x_min, x_max = -1.5, n + 2.5
        vb.setRange(xRange=(x_min, x_max), padding=0)

        # 3. Y 轴维持自适应（基于当前的 X 范围）
        vb.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
        vb.setAutoVisible(y=True)

        # 4. 强制刷新 Y 轴到当前可见最佳高度 (由于 X 已在锁定期，autoRange 只会计算 Y)
        vb.autoRange()

        # logger.debug(f"[VIEW] Reset to FullView: 0-{n} (Range: {x_min}-{x_max})")

    def _init_resample_toolbar(self):
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Resample:"))

        self.resample_group = QActionGroup(self)
        self.resample_group.setExclusive(True)

        self.resample_actions = {}

        label_map = {
            'd': '1D',
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
        """Initialize TDX / code link toggle"""
        self.tdx_cb = QCheckBox("Enable TDX Link")
        self.tdx_cb.setChecked(self.tdx_enabled)  # 默认联动
        self.tdx_cb.stateChanged.connect(self.on_tdx_toggled)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.tdx_cb)

    def on_tdx_toggled(self, state):
        """Enable or disable code sending via sender"""
        self.tdx_enabled = bool(state)
        logger.info(f'tdx_enabled: {self.tdx_enabled}')

    def _init_real_time(self):
        """Initialize TDX / code link toggle"""
        self.real_time_cb = QCheckBox("实时")
        self.real_time_cb.setChecked(self.realtime)  # 默认联动
        self.real_time_cb.stateChanged.connect(self.on_real_time_toggled)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.real_time_cb)

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

    def _update_signal_badge(self):
        if hasattr(self, 'signal_box_dialog') and self.signal_box_dialog._queue_mgr:
            signals = self.signal_box_dialog._queue_mgr.get_top()
            count = len(signals)
            self.signal_badge_action.setText(f"📬 信号({count})")

            # 检查是否有新信号并播报 (语音播报逻辑)
            if not signals: return

            latest = signals[0] # PriorityQueue top 可能是最新的或优先级最高的
            # Queue get_top() 是排序后的列表 (Prio ASC, Timestamp DESC)
            # 所以 0 号元素是优先级最高且最新的

            # 简单去重: 仅当 timestamp 不同于上次时播报
            if latest.timestamp > self.last_voice_ts:
                self.last_voice_ts = latest.timestamp

                # 播放 Top 5 信息
                # 逻辑: 播报前5条高优先级信号
                
                count_spoken = 0
                for msg in signals[:5]: # 前5条
                    # 仅播报 High Priority (<100)
                    if msg.priority < 100: # 放宽限制
                        strategy_name = msg.signal_type
                        if strategy_name == "HOT_WATCH": strategy_name = "热点"
                        elif strategy_name == "CONSOLIDATION": strategy_name = "蓄势"
                        elif strategy_name == "SUDDEN_LAUNCH": strategy_name = "突发"
                        
                        # 简短播报
                        text = f"{msg.name}, {strategy_name}"
                        self.voice_thread.speak(text)
                        
                        count_spoken += 1
                
                if count_spoken > 0:
                    logger.info(f"Voice broadcast {count_spoken} signals")

    def _on_strategy_changed(self, index: int) -> None:
        """
        处理策略选择器变更

        策略组合:
        - 0: 回调MA5策略
        - 1: 决策引擎
        - 2: 全策略(含监理)
        """
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
        <h4>🔎 最近信号详情</h4>
        <p><b>动作:</b> {data.get('last_action', 'N/A')}</p>
        <p><b>原因:</b> {data.get('last_reason', 'N/A')}</p>
        <p><b>诊断:</b> {data.get('shadow_info', 'N/A')}</p>
        """

        msg = QMessageBox(self)
        msg.setWindowTitle(f"监理详情 - {self.current_code}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(content)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def show_comprehensive_briefing(self):
        """[⭐极限弹窗] 一键显示综合研报信息"""
        if not self.current_code: return

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

        dlg = ScrollableMsgBox(f"📈 综合简报 - {self.current_code}", briefing, self)
        dlg.exec()

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
        # ✅ 优雅停止旧进程
        self._stop_realtime_process()

        # 重置 stop_flag
        self.stop_flag.value = True

        # 启动新进程
        self.realtime_process = Process(
            target=realtime_worker_process,
            args=(code, self.realtime_queue, self.stop_flag, self.log_level, self._debug_realtime),
            daemon=False
        )
        self.realtime_process.start()


    def _stop_realtime_process(self):
        if self.realtime_process:
            # 先停止循环
            self.stop_flag.value = False
            # 等待进程结束，最多 5 秒
            self.realtime_process.join(timeout=5)
            if self.realtime_process.is_alive():
                self.realtime_process.terminate()
            self.realtime_process = None

    def _poll_realtime_queue(self):
        if not hasattr(self, "_closing") or getattr(self, "_closing", False):
            logger.debug(f'self._closing :{getattr(self, "_closing", False)}')
            return  # 窗口正在关闭，不再处理队列
        # latest_updates = {}  # key: code, value: (tick_df, today_bar)
        while True:
            try:
                code, tick_df, today_bar = self.realtime_queue.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError):
                logger.warning("Realtime queue closed unexpectedly")
                break
            except Exception as e:
                logger.exception("Unexpected error in realtime queue")
                break

            try:
                # GUI 更新加保护
                if self.isVisible():  # 确保窗口未关闭
                    self.on_realtime_update(code, tick_df, today_bar)
                    logger.debug(f'on_realtime_update today_bar:\n {today_bar}')
            except RuntimeError as e:
                logger.warning(f"GUI update skipped: {e}")
            except Exception:
                logger.exception("Error in on_realtime_update")

    def apply_df_diff(self, df_diff):
        for col in df_diff.columns:
            mask = df_diff[col].notna()
            self.df_all.loc[mask, col] = df_diff.loc[mask, col]
        # self.render_table_or_charts()
        # 用 update_df_all 来刷新界面
        self.update_df_all(self.df_all)

    def _poll_command_queue(self):
        """轮询内部指令队列 (消费所有积压，只取最新数据)"""
        if not self.command_queue:
            return
        try:
            latest_full_df = None
            df_diffs = []

            while not self.command_queue.empty():
                cmd_data = self.command_queue.get_nowait()
                if isinstance(cmd_data, tuple) and len(cmd_data) == 2:
                    cmd, val = cmd_data
                    if cmd == 'SWITCH_CODE':
                        if isinstance(val, dict):
                            logger.info(f"Queue CMD: Switching to {val.get('code')} with params {val}")
                            self.load_stock_by_code(val.get('code'), **val)
                        else:
                            logger.info(f"Queue CMD: Switching to {val}")
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
                        elif m_type == 'UPDATE_DF_DIFF':
                            if ver == self.expected_sync_version + 1:
                                self.expected_sync_version = ver
                                df_diffs.append(payload)
                            else:
                                logger.warning(f"[Queue] Version mismatch! Got {ver}, expected {self.expected_sync_version+1}. Requesting full sync.")
                                self._request_full_sync()
                                # 终止本轮增量应用，等待全量同步
                                df_diffs.clear()
                                break

            # --- 处理最新全量数据 ---
            if latest_full_df is not None:
                logger.debug(f"[Queue] Instant sync full df_all ({len(latest_full_df)} rows)")
                self.update_df_all(latest_full_df)

            # --- 处理增量数据 ---
            for diff_df in df_diffs:
                logger.debug(f"[Queue] Instant apply df diff ({len(diff_df)} rows)")
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
        # 即使这是旧的加载结果,也要清除 Loading 状态,避免标题卡住
        if not day_df.empty:
            # 调用完整的标题更新逻辑,显示所有信息 (Rank、percent、win、slope、volume)
            self._update_plot_title(code, day_df, tick_df)

        # 检查是否是当前请求的代码,如果不是则忽略(防止旧数据覆盖新数据)
        if code != self.current_code:
            logger.debug(f"[Rapid Browse] Discarding outdated result for {code}, current is {self.current_code}")
            return

        # ⚡ 过滤掉今天的数据，只保留过去的日 K
        today_str = pd.Timestamp.today().strftime('%Y-%m-%d')
        is_intraday = (
            self.realtime
            and cct.get_work_time_duration()
        )

        if is_intraday or self._debug_realtime:
            day_df = day_df[day_df.index < today_str]

        datetime_index = pd.to_datetime(day_df.index)
        day_df.index = datetime_index.strftime('%Y-%m-%d')
        self.day_df = day_df.copy()
        # render_charts 时只传历史日 K，tick_df 用于 intraday 图，不绘制今天 K
        with timed_ctx("render_charts", warn_ms=50):
            self.render_charts(code, self.day_df, tick_df)

        # 启动 realtime
        if self.realtime and cct.get_work_time_duration() or self._debug_realtime:
            self._start_realtime_process(code)


    def on_realtime_update(self, code, tick_df, today_bar):
        if today_bar is None or today_bar.empty:
            return

        if not self._debug_realtime and (not self.realtime or code != self.current_code or not cct.get_work_time_duration()):
            return

        datetime_index = pd.to_datetime(today_bar.index)
        today_bar.index = datetime_index.strftime('%Y-%m-%d')
        self.day_df
        today_idx = today_bar.index[0]
        # 获取 day_df 最后一天日期
        last_day = self.day_df.index[-1] if not self.day_df.empty else None

        # 计算交易日间隔
        trade_gap = cct.get_trade_day_distance(last_day, today_idx) if last_day else None
        logger.debug(f'trade_gap: {trade_gap}')
        # 第二天开盘（交易日不同），自动初始化 today_bar
        # if last_day is None or (trade_gap is not None and trade_gap > 1):
        #     self._on_initial_loaded()
        #     print(f"[INFO] New trading day detected: {today_idx}, today_bar appended trade_gap:{trade_gap}")
        #     return
        # elif last_day == today_idx:
        if last_day == today_idx:
            # 当天更新最后一行
            # 先按 day_df 列对齐 today_bar
            # 直接重命名列
            # today_bar = today_bar.rename(columns={'volume': 'vol'})
            # today_bar_renamed
            today_bar['vol'] = today_bar['volume']
            cols_match = ['open', 'high', 'low', 'close', 'vol', 'volume','amount', 'code']
            # 先从 today_bar 里取需要的列（不存在的填 NaN）
            today_row = today_bar.iloc[0].reindex(cols_match)
            today_row['code'] = code

            # 如果 amount 列存在但为空，用 (high+low)/2 * volume 填充
            if 'amount' in today_row:
                if pd.isna(today_row['amount']):
                    if 'vol' in today_row and not pd.isna(today_row['vol']):
                        today_row['amount'] = round((today_row['high'] + today_row['low']) / 2 * today_row['vol'], 1)

            # code 列保持原样（如果 day_df 有默认值或 NaN 就不动）
            # 数值列精度处理
            num_cols = ['open', 'high', 'low', 'close']
            for col in num_cols:
                if col in today_row:
                    today_row[col] = round(pd.to_numeric(today_row[col], errors='coerce'), 2)
            # 更新最后一行
            today_row_new = today_row[self.day_df.columns]  # 强制顺序和 day_df 对齐

            # ⭐ 双轨制补全：从 df_all 中提取由 Tkinter 实时计算好的指标 (Rank, win, ma5d 等)
            if not self.df_all.empty:
                stock_row = pd.DataFrame()
                if code in self.df_all.index:
                    stock_row = self.df_all.loc[[code]]
                elif 'code' in self.df_all.columns:
                    stock_row = self.df_all[self.df_all['code'] == code]

                if not stock_row.empty:
                    # 补充指标到这一行，如果 day_df 没这些列也没关系(iloc 会跳过)
                    # 确保 today_row_new 包含这些潜在列
                    for col in ['ma5d', 'ma10d', 'ma20d', 'ma60d', 'Rank', 'win', 'slope', 'macddif', 'macddea', 'macd']:
                        if col not in self.day_df.columns:
                            self.day_df[col] = np.nan
                        if col in stock_row.columns:
                            val = stock_row[col].iloc[0]
                            if pd.notnull(val):
                                self.day_df.loc[self.day_df.index[-1], col] = val

            logger.debug(f' today_row\n: {today_row} today_row_new:{today_row_new}')
            self.day_df.iloc[-1] = today_row_new
            # self.day_df.iloc[-1] = today_bar.iloc[0]
        else:
            self.day_df = pd.concat([self.day_df, today_bar])

        # 渲染图表
        self.render_charts(code, self.day_df, tick_df)




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
        """Apply theme to a single plot"""
        # 获取 PlotItem 的 ViewBox
        vb = plot.getViewBox()

        # 背景颜色和边框颜色
        if self.qt_theme == 'dark':
            vb.setBackgroundColor('#1e1e1e')
            axis_color = '#cccccc'
            border_color = '#555555'  # 深灰色边框
            title_color = '#e6e6e6'   # 浅灰色标题
        else:
            vb.setBackgroundColor('w')
            axis_color = '#000000'
            border_color = '#cccccc'  # 浅灰色边框
            title_color = '#000000'   # 黑色标题

        # 设置边框颜色
        vb.setBorder(pg.mkPen(border_color, width=1))

        # 设置坐标轴颜色（包括所有四个边）
        for ax_name in ('left', 'bottom', 'right', 'top'):
            ax = plot.getAxis(ax_name)
            if ax is not None:
                ax.setPen(pg.mkPen(axis_color, width=1))
                ax.setTextPen(pg.mkPen(axis_color))

        # 设置标题颜色 - 使用正确的方法
        if hasattr(plot, 'titleLabel'):
            plot.titleLabel.item.setDefaultTextColor(QColor(title_color))

        # 网格
        plot.showGrid(x=True, y=True, alpha=0.3)

    def _apply_widget_theme(self, widget):
        """Apply theme to GraphicsLayoutWidget"""
        if self.qt_theme == 'dark':
            widget.setBackground('#1e1e1e')
            # 设置widget边框
            widget.setStyleSheet("""
                QGraphicsView {
                    border: 1px solid #555555;
                    background-color: #1e1e1e;
                }
            """)
        else:
            widget.setBackground('w')
            widget.setStyleSheet("""
                QGraphicsView {
                    border: 1px solid #cccccc;
                    background-color: white;
                }
            """)



    def apply_qt_theme(self):
        """Apply Qt theme / color scheme"""
        if self.qt_theme == 'dark':
            self.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    color: #e6e6e6;
                }
                QTableWidget {
                    background-color: #2b2b2b;
                    gridline-color: #444444;
                }
                QHeaderView::section {
                    background-color: #3a3a3a;
                    color: #f0f0f0;
                    padding: 4px;
                    border: 1px solid #555555;
                }
                QTableWidget::item:selected {
                    background-color: #505050;
                }
            """)
            pg.setConfigOption('background', 'k')
            pg.setConfigOption('foreground', 'w')

        else:
            # 默认 light
            self.setStyleSheet("")
            pg.setConfigOption('background', 'w')
            pg.setConfigOption('foreground', 'k')

        # 应用到 GraphicsLayoutWidget
        self._apply_widget_theme(self.kline_widget)
        self._apply_widget_theme(self.tick_widget)

        # 调用统一函数设置 pg 主题
        self._apply_pg_theme_to_plot(self.kline_plot)
        self._apply_pg_theme_to_plot(self.tick_plot)

        # 如果有 volume_plot，也应用主题
        if hasattr(self, 'volume_plot'):
            self._apply_pg_theme_to_plot(self.volume_plot)

        # 重新渲染当前股票（如果有）以更新蜡烛图颜色
        if self.current_code:
            self.load_stock_by_code(self.current_code)

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

    def update_stock_table(self, df):
        """Update table with df_all data (增量更新优化版 - 参考TK性能优化)"""
        import time
        start_time = time.time()
        
        if df.empty:
            self.stock_table.setRowCount(0)
            self._table_item_map = {}  # 重置映射
            return
        
        # ⚡ 初始化映射表（首次或重置后）
        if not hasattr(self, '_table_item_map'):
            self._table_item_map = {}  # code -> row_idx 映射
        if not hasattr(self, '_table_update_count'):
            self._table_update_count = 0
        
        self._table_update_count += 1
        
        # ⚡ 每50次增量更新后强制全量刷新，防止累积误差
        force_full = self._table_update_count >= 50
        if force_full:
            self._table_update_count = 0
            self._table_item_map = {}
        
        # ⚡ 性能优化: 禁用信号和排序
        self.stock_table.blockSignals(True)
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setUpdatesEnabled(False)
        
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
                self.stock_table.setRowCount(n_rows)
                self._table_item_map = {}
                
                for row_idx in range(n_rows):
                    stock_code = str(codes[row_idx])
                    stock_name = str(names[row_idx]) if pd.notnull(names[row_idx]) else ''
                    
                    self._set_table_row(row_idx, stock_code, stock_name, 
                                       optional_cols_real, optional_data, no_edit_flag)
                    self._table_item_map[stock_code] = row_idx
            else:
                # === 增量更新 ===
                # 1. 删除不存在的行 (从后往前删除避免索引错乱)
                if codes_to_delete:
                    rows_to_delete = sorted([self._table_item_map[c] for c in codes_to_delete], reverse=True)
                    for row_idx in rows_to_delete:
                        self.stock_table.removeRow(row_idx)
                    # 更新映射
                    for code in codes_to_delete:
                        del self._table_item_map[code]
                    # 重新计算剩余行的索引
                    self._rebuild_item_map_from_table()
                
                # 2. 更新已存在的行
                for row_idx in range(n_rows):
                    stock_code = str(codes[row_idx])
                    
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
        
        finally:
            # ⚡ 恢复信号和更新
            self.stock_table.setUpdatesEnabled(True)
            self.stock_table.blockSignals(False)
            self.stock_table.setSortingEnabled(True)
            
            # ⚡ 性能日志
            duration = time.time() - start_time
            n_rows = len(df) if not df.empty else 0
            if duration > 0.5:  # 超过500ms警告
                logger.warning(f"[TableUpdate] {update_type}: {n_rows}行, 耗时{duration:.3f}s ⚠️")
            else:
                logger.info(f"[TableUpdate] {update_type}: {n_rows}行, 耗时{duration:.3f}s")
    
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
            if col_name in ('percent', 'dff') and pd.notnull(val):
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
                    if col_name in ('percent', 'dff') and pd.notnull(val):
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
        """从表格重建 item_map（删除行后使用）"""
        self._table_item_map = {}
        for row_idx in range(self.stock_table.rowCount()):
            item = self.stock_table.item(row_idx, 0)
            if item:
                code = item.data(Qt.ItemDataRole.UserRole)
                if code:
                    self._table_item_map[str(code)] = row_idx

    # 2️⃣ 处理右键事件
    def on_table_right_click(self, pos):
        item = self.stock_table.itemAt(pos)
        if not item:
            return

        stock_code = item.data(Qt.ItemDataRole.UserRole)
        if not stock_code or self.df_all.empty:
            return

        # 发送逻辑
        success = self.push_stock_info(stock_code, self.df_all.loc[stock_code])
        if success:
            self.statusBar().showMessage(f"发送成功: {stock_code}")
        else:
            self.statusBar().showMessage(f"发送失败: {stock_code}")

    def on_header_section_clicked(self, _logicalIndex):
        """排序后自动滚动到顶部，延时确保排序完成"""
        QTimer.singleShot(50, self.stock_table.scrollToTop)

    def on_table_cell_clicked(self, row, column):
        code_item = self.stock_table.item(row, 0)
        if code_item:
            code = code_item.data(Qt.ItemDataRole.UserRole)
            if code:
                self._clicked_change = True
                if code == self.current_code: 
                    # 如果 code 没变，说明 currentItemChanged 不会触发，手动同步一次 TDX (强制同步)
                    if self.tdx_enabled:
                        try:
                            self.sender.send(code)
                        except Exception:
                            pass
                # 如果 code 变了，currentItemChanged 会处理加载和同步

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
                    if self.tdx_enabled:
                        try:
                            self.sender.send(code)
                        except Exception as e:
                            print(f"Error sending stock code: {e}")
                    
                    # 消费掉点击标记
                    if getattr(self, "_clicked_change", False):
                        self._clicked_change = False

    def on_dataframe_received(self, df, msg_type):
        """接收 DataFrame 更新 (优化: 避免阻塞主线程)"""
        if msg_type == 'UPDATE_DF_DATA' and isinstance(df, dict):
            # 新版字典协议
            m_type = df.get('type')
            payload = df.get('data')
            ver = df.get('ver', 0)
            
            # 版本校验逻辑
            if m_type == 'UPDATE_DF_ALL':
                self.expected_sync_version = ver
                logger.debug(f"[IPC] Sync version reset to {ver}")
                QtCore.QTimer.singleShot(0, lambda: self._process_df_all_update(payload))
            elif m_type == 'UPDATE_DF_DIFF':
                if ver == self.expected_sync_version + 1:
                    self.expected_sync_version = ver
                    QtCore.QTimer.singleShot(0, lambda: self.apply_df_diff(payload))
                else:
                    logger.warning(f"[IPC] Version mismatch! Got {ver}, expected {self.expected_sync_version + 1}. Requesting full sync.")
                    self._request_full_sync()
            return

        if msg_type == "UPDATE_DF_ALL":
            # 使用 QTimer 延迟处理，避免阻塞主线程
            QtCore.QTimer.singleShot(0, lambda: self._process_df_all_update(df))
        elif msg_type == "UPDATE_DF_DIFF":
            # diff 更新通常较小，可以直接处理
            QtCore.QTimer.singleShot(0, lambda: self.apply_df_diff(df))
        else:
            logger.warning(f"Unknown msg_type: {msg_type}")
    
    def _process_df_all_update(self, df):
        """处理完整 DataFrame 更新 (优化: 分块处理避免 UI 冻结)"""
        try:
            # ⚡ 快速更新缓存 (不触发 UI)
            if df is not None:
                self.df_cache = df.copy() if not df.empty else pd.DataFrame()
                self.df_all = self.df_cache
            
            # ⚡ 更新表格 (已优化)
            with timed_ctx("update_stock_table_only", warn_ms=500):
                self.update_stock_table(self.df_all)
            
            # ⚡ 处理事件，让 UI 响应
            QApplication.processEvents()
            
            # ⚡ 刷新监理看板
            if getattr(self, 'current_code', None) and hasattr(self, 'kline_plot'):
                self._refresh_sensing_bar(self.current_code)
            
            # ⚡ 处理热榜信号 (轻量操作)
            if SIGNAL_QUEUE_AVAILABLE:
                self._process_hot_signals(df if df is not None else self.df_all)
                
        except Exception as e:
            logger.error(f"Error processing df_all update: {e}")

    def _request_full_sync(self):
        """向 Monitor 发送全量同步请求"""
        try:
            success = send_code_via_pipe({"cmd": "REQ_FULL_SYNC"}, logger=logger)
            if success:
                logger.info("[Sync] Requested full sync via Pipe")
                # 暂时将版本设为无效，防止在收到全量包前继续处理碎片增量
                self.expected_sync_version = -1
            else:
                logger.warning("[Sync] Failed to send sync request via Pipe")
        except Exception as e:
            logger.error(f"[Sync] Request full sync error: {e}")

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

    def update_df_all(self, df=None):
        """
        更新 df_all 并刷新表格 (简化版 - 仅更新表格)
        注意: 缓存和监理看板刷新已由 _process_df_all_update 处理
        """
        if df is not None:
            # 更新缓存
            self.df_cache = df.copy() if not df.empty else pd.DataFrame()
            self.df_all = self.df_cache
        # ⚡ 直接更新表格，不再重复处理
        self.update_stock_table(self.df_all)

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


    def load_stock_by_code(self, code, name=None, **kwargs):
        """
        加载股票数据并渲染。支持可扩展参数模式：
        1. 字符串模式: "CODE|代码|key1=val1|key2=val2" (来自 IPC)
        2. 字典模式: 通过 **kwargs 传入 (来自 Queue)
        """
        self._capture_view_state()

        # --- 解析可扩展参数 ---
        params = kwargs.copy()
        if code and "|" in str(code):
            parts = str(code).split("|")
            code = parts[0]
            for p in parts[1:]:
                if "=" in p:
                    try:
                        k, v = p.split("=", 1)
                        params[k] = v
                    except ValueError:
                        pass

        # --- 处理周期同步 (resample) ---
        target_resample = params.get('resample')
        if target_resample and target_resample in self.resample_keys:
            if target_resample != self.resample:
                logger.info(f"Syncing resample to {target_resample}")
                # 调用 on_resample_changed 会触发递归调用 load_stock_by_code，
                # 但内部有相同 code/resample 的拦截逻辑
                self.on_resample_changed(target_resample)

        if self.current_code == code and self.select_resample == self.resample:
            return
        
        # ⭐ 清理交互状态，防止数据残留 (1.2/1.3)
        self.current_code = code
        self.select_resample = self.resample
        self.tick_prices = np.array([])
        self.tick_avg_prices = np.array([])
        self.tick_times = []
        self.current_kline_signals = []
        self.current_tick_crosshair_idx = -1
        self._hide_crosshair()
        self._hide_tick_crosshair()

        if self.stock_table.rowCount() == 0:
            return

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

        self.kline_plot.setTitle(f"Loading {code}...")

        # ⭐ 快速浏览优化：直接丢弃旧的 DataLoaderThread，不等待完成

        # ⭐ 清理旧的 DataLoaderThread，防止 QThread: Destroyed while thread is still running
        # 快速浏览时不等待，直接丢弃旧线程
        if hasattr(self, 'loader') and self.loader is not None:
            if self.loader.isRunning():
                logger.debug("[DataLoaderThread] Discarding previous loader (rapid browsing)")
                try:
                    self.loader.data_loaded.disconnect()  # 断开信号，防止旧数据干扰
                except TypeError:
                    pass  # 信号可能已断开
                # 不等待旧线程，让它在后台完成或被 GC
                self.loader = None

        # ② 加载历史
        with timed_ctx("DataLoaderThread", warn_ms=800):
            self.loader = DataLoaderThread(
                code,
                self.hdf5_mutex,
                resample=self.resample
            )
        with timed_ctx("data_loaded", warn_ms=50):
            self.loader.data_loaded.connect(self._on_initial_loaded)
        with timed_ctx("start", warn_ms=800):
            self.loader.start()

        # ---- 3. 如果开启 realtime，再启动 realtime worker ----
        with timed_ctx("start_realtime_worker", warn_ms=800):
            if self.realtime and cct.get_work_time_duration() or self._debug_realtime:
                self._start_realtime_process(code)
        if logger.level == LoggerFactory.DEBUG:
            print_timing_summary(top_n=6)


    # def render_charts_opt(self, code, day_df, tick_df):
    def render_charts(self, code, day_df, tick_df):
        """
        Render full charts:
          - Daily K-line + MA5/10/20 + Bollinger + Signals
          - Volume + Volume MA5
          - Realtime ghost candle
          - Intraday Tick plot + avg line + pre_close
          - Theme aware
          - Signals arrows on top
        """
        if day_df.empty:
            self.kline_plot.setTitle(f"{code} - No Data")
            self.tick_plot.setTitle("No Tick Data")
            # 清理旧图形，防止切股后还有残留
            self.kline_plot.clear()
            self.tick_plot.clear()
            if hasattr(self, 'volume_plot'):
                self.volume_plot.clear()
            # 清除缓存的 Items
            for attr in ['candle_item', 'date_axis', 'vol_up_item', 'vol_down_item',
                        'ma5_curve', 'ma10_curve', 'ma20_curve', 'upper_curve', 'lower_curve',
                        'vol_ma5_curve', 'signal_scatter', 'tick_curve', 'avg_curve', 'pre_close_line', 'ghost_candle']:
                if hasattr(self, attr):
                    delattr(self, attr)
            return

        # --- 标题 (含监理看板) ---
        self._update_plot_title(code, day_df, tick_df)

        # --- 主题颜色 ---
        if self.qt_theme == 'dark':
            ma_colors = {'ma5':'b','ma10':'orange','ma20':QColor(255,255,0)}
            bollinger_colors = {'upper':QColor(139,0,0),'lower':QColor(0,128,0)}
            vol_ma_color = QColor(255,255,0)
            tick_curve_color = 'w'
            tick_avg_color = QColor(255,255,0)
            pre_close_color = 'b'
        else:
            ma_colors = {'ma5':'b','ma10':'orange','ma20':QColor(255,140,0)}
            bollinger_colors = {'upper':QColor(139,0,0),'lower':QColor(0,128,0)}
            vol_ma_color = QColor(255,140,0)
            tick_curve_color = 'k'
            tick_avg_color = QColor(255,140,0)
            pre_close_color = 'b'

        day_df = _normalize_dataframe(day_df)

        if 'date' in day_df.columns:
            day_df = day_df.set_index('date')
        logger.debug(f'day_df.index:\n {day_df.index[-3:]}')
        day_df = day_df.sort_index()
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

        # --- MA5/10/20 ---
        ma5 = day_df['close'].rolling(5).mean().values
        ma10 = day_df['close'].rolling(10).mean().values
        ma20 = day_df['close'].rolling(20).mean().values

        for attr, series, color in zip(['ma5_curve','ma10_curve','ma20_curve'],
                                       [ma5,ma10,ma20],
                                       [ma_colors['ma5'], ma_colors['ma10'], ma_colors['ma20']]):
            if not hasattr(self, attr) or getattr(self, attr) not in self.kline_plot.items:
                setattr(self, attr, self.kline_plot.plot(x_axis, series, pen=pg.mkPen(color, width=1)))
            else:
                getattr(self, attr).setData(x_axis, series)
                getattr(self, attr).setPen(pg.mkPen(color, width=1))

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

        # ----------------- 绘制 Volume -----------------
        if 'amount' in day_df.columns:
            if not hasattr(self, 'volume_plot'):
                self.volume_plot = self.kline_widget.addPlot(row=1, col=0)
                self.volume_plot.setXLink(self.kline_plot)
                self.volume_plot.setMaximumHeight(120)
                self.volume_plot.setLabel('left', 'Volume')
                self.volume_plot.showGrid(x=True, y=True)
                self.volume_plot.setMenuEnabled(False)

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

        # --- [UPGRADE] 信号标记渲染 ---
        self.signal_overlay.clear()
        kline_signals = []

        # 1. 历史模拟信号
        if self.show_strategy_simulation:
            kline_signals.extend(self._run_strategy_simulation(code, day_df))

        # 2. 实盘日志历史信号 (CSV)
        hist_df = self.logger.get_signal_history_df()
        if not hist_df.empty:
            hist_df['code'] = hist_df['code'].astype(str)
            stock_signals = hist_df[hist_df['code'] == str(code)]
            date_map = {d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i for i, d in enumerate(dates)}
            for _, row in stock_signals.iterrows():
                sig_date = str(row['date']).split()[0]
                if sig_date in date_map:
                    idx = date_map[sig_date]
                    y_p = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
                    action = str(row['action'])
                    reason = str(row['reason'])

                    # 识别信号类型 (BUY/SELL/VETO)
                    is_buy = 'Buy' in action or '买' in action or 'ADD' in action
                    stype = SignalType.BUY if is_buy else SignalType.SELL
                    if "VETO" in action: stype = SignalType.VETO

                    # 识别信号来源 (STRATEGY/SHADOW)
                    source = SignalSource.SHADOW_ENGINE if "SHADOW" in action else SignalSource.STRATEGY_ENGINE

                    kline_signals.append(SignalPoint(
                        code=code, timestamp=sig_date, bar_index=idx, price=y_p,
                        signal_type=stype, source=source, reason=reason,
                        debug_info=row.get('indicators', {})
                    ))

        # 3. 实时影子信号 (K线占位图标)
        is_realtime_active = self.realtime and not tick_df.empty and (cct.get_work_time_duration() or self._debug_realtime)
        if is_realtime_active:
            shadow_decision = self._run_realtime_strategy(code, day_df, tick_df)
            if shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                y_p = float(tick_df['price'].iloc[-1])
                # 当前 K 线索引是 dates 长度（即下一根未收盘的 K 线）
                kline_signals.append(SignalPoint(
                    code=code, timestamp="REALTIME", bar_index=len(dates), price=y_p,
                    signal_type=SignalType.BUY if '买' in shadow_decision['action'] or 'ADD' in shadow_decision['action'] else SignalType.SELL,
                    source=SignalSource.SHADOW_ENGINE,
                    reason=shadow_decision['reason'],
                    debug_info=shadow_decision.get('debug', {})
                ))
                self.last_shadow_decision = shadow_decision # 存储供简报使用

        # 执行 K 线绘图
        self.current_kline_signals = kline_signals # ⭐ 保存信号供十字光标显示 (1.3)
        self.signal_overlay.update_signals(kline_signals, target='kline')

        # -------------------------
        # 移除此处的 sensing_bar 设置，改到 intraday 内容设置之后
        # -------------------------

        # --- Ghost Candle (实时占位) ---
        is_realtime_active = self.realtime and not tick_df.empty and (cct.get_work_time_duration() or self._debug_realtime)
        if is_realtime_active:
            current_price = float(tick_df['close'].iloc[-1])
            last_hist_date = str(day_df.index[-1]).split()[0]
            today_str = pd.Timestamp.now().strftime('%Y-%m-%d')

            if today_str > last_hist_date:
                new_x = len(day_df)
                open_p = tick_df['open'][tick_df['open'] > 0].iloc[-1] if 'open' in tick_df.columns else current_price
                low_p  = tick_df['low'][tick_df['low'] > 0].min() if 'low' in tick_df.columns else current_price
                high_p = tick_df['high'][tick_df['high'] > 0].max() if 'high' in tick_df.columns else current_price

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
        if not tick_df.empty:
            prices = tick_df['close'].values
            x_ticks = np.arange(len(prices))
            pre_close = tick_df['llastp'].iloc[-1] if 'llastp' in tick_df.columns else tick_df['pre_close'].iloc[-1] if 'pre_close' in tick_df.columns else prices[0]

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

            # pre_close 虚线
            if not hasattr(self, 'pre_close_line') or self.pre_close_line not in self.tick_plot.items:
                self.pre_close_line = self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))
            else:
                self.pre_close_line.setValue(pre_close)
                self.pre_close_line.setPen(pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))

            pct_change = (prices[-1]-pre_close)/pre_close*100 if pre_close!=0 else 0

            # ⭐ 绘制完成后一次性调整视图范围，确保数据可见 (由于 disableAutoRange)
            self.tick_plot.autoRange()

            # ⭐ 构建分时图标题（包含监理看板）
            tick_title = f"Intraday: {prices[-1]:.2f} ({pct_change:.2f}%)"

            # 追加监理看板信息
            if not self.df_all.empty:
                # Debug: print df_all columns
                # print(f"[DEBUG] df_all columns: {self.df_all.columns.tolist()}")
                # print(f"[DEBUG] Looking for code: {code}, df_all index: {self.df_all.index.tolist()[:5]}")

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

            self.tick_plot.setTitle(tick_title)
            self.tick_plot.showGrid(x=False, y=True, alpha=0.5)

            # --- [UPGRADE] Intraday Tick Signals (Shadow/Realtime) ---
            # 直接在分时图上标记影子信号
            if is_realtime_active and self.show_strategy_simulation:
                # 复用刚才计算好的实时影子决策
                if 'shadow_decision' in locals() and shadow_decision and shadow_decision.get('action') in ("买入", "卖出", "止损", "止盈", "ADD"):
                    y_p = float(tick_df['price'].iloc[-1])
                    idx = len(tick_df) - 1

                    tick_point = SignalPoint(
                        code=code, timestamp="TICK_LIVE", bar_index=idx, price=y_p,
                        signal_type=SignalType.BUY if '买' in shadow_decision['action'] or 'ADD' in shadow_decision['action'] else SignalType.SELL,
                        source=SignalSource.SHADOW_ENGINE,
                        reason=shadow_decision['reason'],
                        debug_info=shadow_decision.get('debug', {})
                    )
                    self.signal_overlay.update_signals([tick_point], target='tick')

        # ----------------- 5. 数据同步与视角处理 -----------------
        # 同步归一化后的数据到 self.day_df
        self.day_df = day_df

        is_new_stock = not hasattr(self, '_last_rendered_code') or self._last_rendered_code != code
        self._last_rendered_code = code

        last_resample = getattr(self, "_last_resample", None)
        is_resample_change = (last_resample is not None and last_resample != self.resample)
        self._last_resample = self.resample

        # 复合视角恢复标志
        has_captured_state = hasattr(self, '_prev_dist_left') and getattr(self, '_prev_y_zoom', None) is not None
        was_full_view = getattr(self, '_prev_is_full_view', False)

        if is_new_stock or is_resample_change or has_captured_state:
            vb = self.kline_plot.getViewBox()

            # 如果之前是“全览”状态，或者根本没有捕获状态，则执行 Reset (全览)
            if was_full_view or not has_captured_state:
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



    # def render_charts_old(self, code, day_df, tick_df):
    #     if day_df.empty:
    #         self.kline_plot.setTitle(f"{code} - No Data")
    #         return

    #     self.kline_plot.clear()
    #     self.tick_plot.clear()

    #     info = self.code_info_map.get(code, {})

    #     name = info.get("name", "")
    #     rank = info.get("Rank", None)
    #     percent = info.get("percent", None)
    #     win = info.get("win", None)
    #     slope = info.get("slope", None)
    #     volume = info.get("volume", None)

    #     title_parts = [code]
    #     if name:
    #         title_parts.append(name)

    #     if rank is not None:
    #         title_parts.append(f"Rank: {int(rank)}")

    #     if percent is not None:
    #         pct_str = f"{percent:+.2f}%"
    #         title_parts.append(pct_str)

    #     if win is not None:
    #         title_parts.append(f"win: {int(win)}")
    #     if slope is not None:
    #         slope_str = f"{slope:.1f}%"
    #         title_parts.append(f"slope: {slope:.1f}%")
    #     if volume is not None:
    #         title_parts.append(f"vol: {volume:.1f}")

    #     title_text = " | ".join(title_parts)

    #     self.kline_plot.setTitle(title_text)


    #     # --- A. Render Daily K-Line ---
    #     day_df = day_df.sort_index()
    #     dates = day_df.index
    #     # Convert date index to integers 0..N
    #     x_axis = np.arange(len(day_df))

    #     # Create OHLC Data for CandlestickItem
    #     # ohlc_data = []
    #     # for i, (idx, row) in enumerate(day_df.iterrows()):
    #     #     ohlc_data.append((i, row['open'], row['close'], row['low'], row['high']))

    #     x_axis = np.arange(len(day_df))
    #     ohlc_data = np.column_stack((
    #         x_axis,
    #         day_df['open'].values,
    #         day_df['close'].values,
    #         day_df['low'].values,
    #         day_df['high'].values
    #     ))

    #     # # Draw Candles
    #     # candle_item = CandlestickItem(ohlc_data)
    #     # self.kline_plot.addItem(candle_item)
    #     candle_item = CandlestickItem(
    #         ohlc_data,
    #         theme=self.qt_theme
    #     )
    #     self.kline_plot.addItem(candle_item)

    #     # Draw Signals (Arrows)
    #     signals = self.logger.get_signal_history_df()
    #     if not signals.empty:
    #         stock_signals = signals[signals['code'] == code]
    #         if not stock_signals.empty:
    #             arrow_x = []
    #             arrow_y = []
    #             brushes = []

    #             # Align signals to x-axis indices
    #             date_map = {
    #                 d if isinstance(d, str) else d.strftime('%Y-%m-%d'): i
    #                 for i, d in enumerate(dates)
    #             }
    #             for _, row in stock_signals.iterrows():
    #                 sig_date_str = str(row['date']).split()[0]
    #                 if sig_date_str in date_map:
    #                     idx = date_map[sig_date_str]
    #                     arrow_x.append(idx)

    #                     action = row['action']
    #                     price = row['price'] if pd.notnull(row['price']) else day_df.iloc[idx]['close']
    #                     arrow_y.append(price)

    #                     if 'Buy' in action or '买' in action:
    #                         brushes.append(pg.mkBrush('r')) # Red for Buy
    #                     else:
    #                         brushes.append(pg.mkBrush('g')) # Green for Sell

    #             if arrow_x:
    #                 scatter = pg.ScatterPlotItem(x=arrow_x, y=arrow_y, size=15,
    #                                              pen=pg.mkPen('k'), brush=brushes, symbol='t1')
    #                 self.kline_plot.addItem(scatter)

    #     if 'close' in day_df.columns:
    #         # --- MA5 / MA10 ---
    #         ma5 = day_df['close'].rolling(5).mean()
    #         ma10 = day_df['close'].rolling(10).mean()
    #         self.kline_plot.plot(x_axis, ma5.values, pen=pg.mkPen('b', width=1), name="MA5")
    #         self.kline_plot.plot(x_axis, ma10.values, pen=pg.mkPen('orange', width=1), name="MA10")

    #         # --- Bollinger Bands ---
    #         ma20 = day_df['close'].rolling(20).mean()
    #         std20 = day_df['close'].rolling(20).std()
    #         upper_band = ma20 + 2 * std20
    #         lower_band = ma20 - 2 * std20

    #         # self.kline_plot.plot(x_axis, ma20.values, pen=pg.mkPen('purple', width=1, style=Qt.PenStyle.DotLine))
    #         # self.kline_plot.plot(x_axis, upper_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))
    #         # self.kline_plot.plot(x_axis, lower_band.values, pen=pg.mkPen('grey', width=1, style=Qt.PenStyle.DashLine))

    #         # 中轨颜色根据主题调整
    #         if self.qt_theme == 'dark':
    #             ma20_color = QColor(255, 255, 0)  # 黄色
    #         else:
    #             ma20_color = QColor(255, 140, 0)  # 深橙色 (DarkOrange)

    #         self.kline_plot.plot(x_axis, ma20.values,
    #                              pen=pg.mkPen(ma20_color, width=2))

    #         # 上轨 深红色加粗
    #         self.kline_plot.plot(x_axis, upper_band.values,
    #                              pen=pg.mkPen(QColor(139, 0, 0), width=2))  # DarkRed

    #         # 下轨 深绿色加粗
    #         self.kline_plot.plot(x_axis, lower_band.values,
    #                              pen=pg.mkPen(QColor(0, 128, 0), width=2))  # DarkGreen

    #         # --- 自动居中显示 ---
    #         self.kline_plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
    #         self.kline_plot.autoRange()


    #     # --- volume plot ---
    #     if 'amount' in day_df.columns:
    #         # 创建 volume 子图
    #         if not hasattr(self, 'volume_plot'):
    #             self.volume_plot = self.kline_widget.addPlot(row=1, col=0)
    #             self.volume_plot.showGrid(x=True, y=True)
    #             self.volume_plot.setMaximumHeight(120)
    #             self.volume_plot.setLabel('left', 'Volume')
    #             self.volume_plot.setXLink(self.kline_plot)  # x 轴同步主图
    #             self.volume_plot.setMenuEnabled(False)
    #         else:
    #             # 清空之前的数据，防止重叠
    #             self.volume_plot.clear()
    #
    #         x_axis = np.arange(len(day_df))
    #         amounts = day_df['amount'].values
    #
    #         # 涨的柱子
    #         up_idx = day_df['close'] >= day_df['open']
    #         if up_idx.any():
    #             bg_up = pg.BarGraphItem(
    #                 x=x_axis[up_idx],
    #                 height=amounts[up_idx],
    #                 width=0.6,
    #                 brush='r'
    #             )
    #             self.volume_plot.addItem(bg_up)
    #
    #         # 跌的柱子
    #         down_idx = day_df['close'] < day_df['open']
    #         if down_idx.any():
    #             bg_down = pg.BarGraphItem(
    #                 x=x_axis[down_idx],
    #                 height=amounts[down_idx],
    #                 width=0.6,
    #                 brush='g'
    #             )
    #             self.volume_plot.addItem(bg_down)
    #
    #         # 添加5日均量线
    #         ma5_volume = pd.Series(amounts).rolling(5).mean()
    #         if self.qt_theme == 'dark':
    #             vol_ma_color = QColor(255, 255, 0)  # 黄色
    #         else:
    #             vol_ma_color = QColor(255, 140, 0)  # 深橙色
    #
    #         self.volume_plot.plot(x_axis, ma5_volume.values,
    #                              pen=pg.mkPen(vol_ma_color, width=1.5),
    #                              name='MA5')
    #
    #     # --- B. Render Intraday Trick ---
    #     if not tick_df.empty:
    #         try:
    #             # 1. Prepare Data
    #             df_ticks = tick_df.copy()
    #
    #             # Handle MultiIndex: code, ticktime
    #             if isinstance(df_ticks.index, pd.MultiIndex):
    #                 # Sort by ticktime just in case
    #                 df_ticks = df_ticks.sort_index(level='ticktime')
    #                 prices = df_ticks['close'].values
    #             else:
    #                 prices = df_ticks['close'].values
    #
    #             # Get Params
    #             current_price = prices[-1]
    #
    #             # Attempt to get pre_close (llastp)
    #             if 'llastp' in df_ticks.columns:
    #                 pre_close = float(df_ticks['llastp'].iloc[-1])
    #             elif 'pre_close' in df_ticks.columns:
    #                 pre_close = float(df_ticks['pre_close'].iloc[-1])
    #             else:
    #                 pre_close = prices[0]
    #
    #             open_p = 0
    #             if 'open' in df_ticks.columns:
    #                 # Avoid 0 values if possible
    #                 opens = df_ticks['open'][df_ticks['open'] > 0]
    #                 if not opens.empty:
    #                     open_p = opens.iloc[-1]
    #                 else:
    #                     open_p = prices[0]
    #             else:
    #                 open_p = prices[0]
    #
    #             low_p = prices.min()
    #             if 'low' in df_ticks.columns:
    #                 mins = df_ticks['low'][df_ticks['low'] > 0]
    #                 if not mins.empty:
    #                     l_val = mins.min()
    #                     if l_val < low_p: low_p = l_val
    #
    #             high_p = prices.max()
    #             if 'high' in df_ticks.columns:
    #                 maxs = df_ticks['high'][df_ticks['high'] > 0]
    #                 if not maxs.empty:
    #                     h_val = maxs.max()
    #                     if h_val > high_p: high_p = h_val
    #
    #             # 2. Update Ghost Candle on Day Chart
    #             day_dates = day_df.index
    #             last_hist_date_str = ""
    #             if not day_dates.empty:
    #                 last_hist_date_str = str(day_dates[-1]).split()[0]
    #
    #             today_str = pd.Timestamp.now().strftime('%Y-%m-%d')
    #
    #             if self.realtime and cct.get_work_time_duration() and today_str > last_hist_date_str or self._debug_realtime:
    #                 new_x = len(day_df)
    #                 ghost_data = [(new_x, open_p, current_price, low_p, high_p)]
    #                 ghost_candle = CandlestickItem(ghost_data)
    #                 self.kline_plot.addItem(ghost_candle)
    #
    #                 text = pg.TextItem(f"{current_price}", anchor=(0, 1),
    #                                    color='r' if current_price>pre_close else 'g')
    #                 text.setPos(new_x, high_p)
    #                 self.kline_plot.addItem(text)
    #
    #
    #             # 3. Render Tick Plot (Curve)
    #             pct_change = ((current_price - pre_close) / pre_close * 100) if pre_close != 0 else 0
    #             self.tick_plot.setTitle(f"Intraday: {current_price:.2f} ({pct_change:.2f}%)")
    #
    #             # X-axis: 0 to N
    #             x_ticks = np.arange(len(prices))
    #
    #             # Draw Pre-close (Dash Blue)
    #             self.tick_plot.addLine(y=pre_close, pen=pg.mkPen('b', style=Qt.PenStyle.DashLine, width=1))
    #
    #             # # Draw Price Curve
    #             if self.qt_theme == 'dark':
    #                 curve_color = 'w'  # 白色线条
    #                 pre_close_color = 'b'
    #                 avg_color = QColor(255, 255, 0)  # 黄色均价线
    #             else:
    #                 curve_color = 'k'
    #                 pre_close_color = 'b'
    #                 avg_color = QColor(255, 140, 0)  # 深橙色均价线 (DarkOrange)
    #
    #             curve_pen = pg.mkPen(curve_color, width=2)
    #             self.tick_plot.plot(x_ticks, prices, pen=curve_pen, name='Price')
    #             self.tick_plot.addLine(y=pre_close, pen=pg.mkPen(pre_close_color, style=Qt.PenStyle.DashLine))
    #
    #             # 计算并绘制分时均价线
    #             # 分时均价 = 累计成交金额 / 累计成交量
    #             if 'amount' in df_ticks.columns and 'volume' in df_ticks.columns:
    #                 # 使用 amount 和 volume 计算均价
    #                 cum_amount = df_ticks['amount'].cumsum()
    #                 cum_volume = df_ticks['volume'].cumsum()
    #                 # 避免除以零
    #                 avg_prices = np.where(cum_volume > 0, cum_amount / cum_volume, prices)
    #             elif 'close' in df_ticks.columns:
    #                 # 如果没有成交量数据，使用价格的累计平均
    #                 avg_prices = pd.Series(prices).expanding().mean().values
    #             else:
    #                 avg_prices = None
    #
    #             if avg_prices is not None:
    #                 avg_pen = pg.mkPen(avg_color, width=1.5, style=Qt.PenStyle.SolidLine)
    #                 self.tick_plot.plot(x_ticks, avg_prices, pen=avg_pen, name='Avg Price')
    #
    #             # Add Grid
    #             self.tick_plot.showGrid(x=False, y=True, alpha=0.5)
    #
    #         except Exception as e:
    #             print(f"Error rendering tick data: {e}")
    #             import traceback
    #             traceback.print_exc()

    def _update_plot_title(self, code, day_df, tick_df):
        """仅更新 K 线图基础信息（代码、名称、排名等），不再包含监理看板以防干扰视图"""
        if not hasattr(self, 'kline_plot'):
            return

        # 尝试从 code_info_map 获取基础信息 (增加模糊匹配)
        info = self.code_info_map.get(code)
        if info is None and len(code) > 6:
            info = self.code_info_map.get(code[-6:])
        if info is None:
            info = {}

        title_parts = [code]
        for k, fmt in [('name', '{}'), ('Rank', 'Rank: {}'), ('percent', '{:+.2f}%'),
                       ('win', 'win: {}'), ('slope', 'slope: {:.1f}%'), ('volume', 'vol: {:.1f}')]:
            v = info.get(k)
            if v is not None:
                title_parts.append(fmt.format(v))

        main_title = " | ".join(title_parts)
        # 只有标题内容变化时才调用 setTitle
        if getattr(self, "_last_main_title", "") != main_title:
            self.kline_plot.setTitle(main_title)
            self._last_main_title = main_title

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

        if sensing_parts:
            sensing_html = " ".join(sensing_parts)
            new_title = f"{base_title}  |  <span style='color: #FFD700; font-weight: bold;'>{sensing_html}</span>"
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
                        current_price = tick['price'].iloc[-1]
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
            row = {
                'code': code,
                'trade': float(last_tick.get('price', 0)),
                'high': float(tick_df['price'].max()),
                'low': float(tick_df['price'].min()),
                'open': float(tick_df['price'].iloc[0]),
                'ratio': float(last_tick.get('ratio', 0)),
                'volume': float(last_tick.get('volume', 0)),
                'amount': float(last_tick.get('amount', 0)),
                'ma5d': float(day_df['close'].rolling(5).mean().iloc[-1]),
                'ma10d': float(day_df['close'].rolling(10).mean().iloc[-1]),
                'ma20d': float(day_df['close'].rolling(20).mean().iloc[-1]),
                'nclose': float((tick_df['amount'].sum() / tick_df['volume'].sum()) if tick_df['volume'].sum() > 0 else 0)
            }

            # 2. 准备快照 (snapshot)
            snapshot = {
                'last_close': float(day_df['close'].iloc[-2] if len(day_df) > 1 else day_df['close'].iloc[-1]),
                'market_win_rate': float(self.logger.get_market_sentiment(days=5)),
                'loss_streak': int(self.logger.get_consecutive_losses(code, days=10)),
                'highest_today': float(tick_df['price'].max())
            }

            # 3. 运行控制器评估
            decision = self.strategy_controller.get_realtime_decision(code, row, snapshot)
            return decision

        except Exception as e:
            logger.error(f"Realtime strategy evaluation failed: {e}")
            return None




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
                    target_cols = ['ma5d', 'ma10d', 'ma20d', 'ma60d', 'lastp1d', 'lastv1d', 'macddif', 'macddea', 'macd', 'rsi', 'upper']
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

    def toggle_filter_panel(self, checked):
        self.filter_panel.setVisible(checked)
        if checked:
            self.load_history_filters()

    def open_history_manager(self):
        import subprocess
        try:
            # 假设 history_manager.py 在同一目录下
            base_dir = os.path.dirname(os.path.abspath(__file__))
            script_path = os.path.join(base_dir, "history_manager.py")
            if os.path.exists(script_path):
                subprocess.Popen(["python", script_path], cwd=base_dir)
            else:
                QMessageBox.warning(self, "Error", f"history_manager.py not found at {script_path}")
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
        self.filter_tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)

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
            feature_cols = ['percent', 'volume', 'category', 'price', 'trade', 'high4',
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
                    price_val = fd['price'][i] if fd['price'] else 0
                    if price_val == 0 and fd['trade']:
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
        import os, json

        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()

        history_path = SEARCH_HISTORY_FILE

        if not os.path.exists(history_path):
            self.filter_combo.addItem("History file not found")
            self.filter_combo.blockSignals(False)
            return

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ⭐ 根据选择的 history 载入
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

        # ⭐ 应用配置中保存的查询规则索引，或默认加载第一项
        if hasattr(self, '_pending_filter_query_index'):
            self._apply_pending_filter_index()
        elif self.filter_combo.count() > 0:
            self.on_filter_combo_changed(0)

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
            matches = df_to_search.query(final_query)
            if matches.empty:
                self.statusBar().showMessage("Results: 0")
                return

            # # 调用高速填充
            # self.populate_tree_from_df(matches)

            # --- 3. 设置列头 ---
            self.filter_tree.setColumnCount(4)
            self.filter_tree.setHeaderLabels(['Code', 'Name', 'Rank', 'Percent'])
            self.filter_tree.setSortingEnabled(True)
            self.filter_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.filter_tree.setHorizontalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
            self.filter_tree.setSizeAdjustPolicy(QTreeWidget.SizeAdjustPolicy.AdjustToContents)

            # --- 4. 填充数据 ---
            for idx, row in matches.iterrows():
                code = str(row['code'])
                name = str(row.get('name', ''))
                rank = row.get('Rank', 0)
                pct = row.get('percent', 0)

                # 安全转换数值
                try:
                    rank_val = float(rank) if rank not in ('', None, 'nan') else float('inf')
                except (ValueError, TypeError):
                    rank_val = float('inf')
                try:
                    pct_val = float(pct) if pct not in ('', None, 'nan') else 0.0
                except (ValueError, TypeError):
                    pct_val = 0.0

                child = NumericTreeWidgetItem(self.filter_tree)
                child.setText(0, code)
                child.setText(1, name)
                child.setText(2, str(rank) if rank not in ('', None) else '')
                child.setText(3, f"{pct_val:.2f}%")
                child.setData(0, Qt.ItemDataRole.UserRole, code)

                # ⭐ 关键修复：使用UserRole+1存储数值用于排序
                child.setData(2, Qt.ItemDataRole.UserRole, rank_val)  # Rank列数值
                child.setData(3, Qt.ItemDataRole.UserRole, pct_val)    # Percent列数值

                # 左对齐
                for col in range(4):
                    child.setTextAlignment(col, Qt.AlignmentFlag.AlignLeft)

                # 百分比上色
                if pct_val > 0:
                    child.setForeground(3, QBrush(QColor("red")))
                elif pct_val < 0:
                    child.setForeground(3, QBrush(QColor("green")))

            # --- 5. 调整列宽，尽量紧凑 ---
            header = self.filter_tree.header()
            for col in range(self.filter_tree.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(False)  # 不拉伸最后一列

            # ⭐ 默认按Rank升序排序
            self.filter_tree.sortItems(2, Qt.SortOrder.AscendingOrder)


            self.statusBar().showMessage(f"Results: {len(matches)}")

        except Exception as e:
            err_item = QTreeWidgetItem(self.filter_tree)
            err_item.setText(0, f"Error: {e}")


    def on_filter_tree_item_clicked(self, item, column):
        # ⭐ 无论如何先确保 filter_tree 获得键盘焦点
        self.filter_tree.setFocus()
        
        code = item.data(0, Qt.ItemDataRole.UserRole)
        if code:
            # 1. 触发图表加载
            self.load_stock_by_code(code)
            # 2. 联动左侧列表选中
            self._select_stock_in_main_table(code)

    def on_filter_tree_current_changed(self, current, previous):
        """处理键盘导航（上下键）"""
        if current:
            code = current.data(0, Qt.ItemDataRole.UserRole)
            if code:
                # 触发图表加载
                self.load_stock_by_code(code)
                # 联动左侧列表选中
                self._select_stock_in_main_table(code)

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
            config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")
            config = {}
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # --- 1. 分割器尺寸 ---
            sizes = config.get('splitter_sizes', [])
            if sizes and len(sizes) == 3:
                self.main_splitter.setSizes(sizes)
            else:
                # 默认分割比例：股票列表:过滤面板:图表区域 = 1:1:4
                self.main_splitter.setSizes([200, 200, 800])
            
            # --- 2. Filter 配置 ---
            filter_config = config.get('filter', {})
            
            # 2.1 历史文件选择 (history1-4)
            history_index = filter_config.get('history_index', 3)  # 默认 history4
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
                # 仅记录，不强制覆盖（让用户可以手动切换）
                pass
            
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


            logger.debug(f"[Config] Loaded: splitter={sizes}, filter={filter_config}, shortcuts={self.global_shortcuts_enabled}")
            
        except Exception as e:
            logger.warning(f"Failed to load visualizer config: {e}")
            # 使用默认值
            self.main_splitter.setSizes([200, 200, 800])

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
            config_file = os.path.join(os.path.dirname(__file__), "visualizer_layout.json")

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

            # 过滤隐藏面板的 0 值
            FILTER_INDEX = 2
            FILTER_DEFAULT = 100
            FILTER_MIN = 60

            old_sizes = old_config.get('splitter_sizes', [])
            if fixed_sizes[FILTER_INDEX] <= 0:
                if len(old_sizes) > FILTER_INDEX and old_sizes[FILTER_INDEX] > 0:
                    fixed_sizes[FILTER_INDEX] = old_sizes[FILTER_INDEX]
                else:
                    fixed_sizes[FILTER_INDEX] = max(FILTER_DEFAULT, FILTER_MIN)

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

            # 3.2 全局快捷键开关
            if hasattr(self, 'global_shortcuts_enabled'):
                window_config['global_shortcuts_enabled'] = self.global_shortcuts_enabled
            # 3.3 模拟信号开关
            if hasattr(self, 'show_strategy_simulation'):
                window_config['show_strategy_simulation'] = self.show_strategy_simulation
            # --- 构建最终配置 ---
            config = {
                'splitter_sizes': fixed_sizes,
                'filter': filter_config,
                'window': window_config,
                # 未来扩展：直接添加新的顶级键即可
            }

            # --- 保存 ---
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.debug(f'[Config] Saved: {config}')

        except Exception as e:
            logger.exception("Failed to save visualizer config")


    def closeEvent(self, event):
       """窗口关闭统一退出清理"""
       self._closing = True
       """窗口关闭事件"""
       # 保存分割器状态
       self.save_splitter_state()
       """Override close event to save window position"""
       try:
           self.save_window_position_qt_visual(self, "trade_visualizer")
           # self.save_window_position_qt(self, "trade_visualizer")
       except Exception as e:
           logger.error(f"Failed to save window position: {e}")

       # 1️⃣ 停止实时数据进程
       # 1️⃣ 通知子进程退出
       if hasattr(self, 'stop_flag'):
           self.stop_flag.value = False
       logger.info(f'stop_flag.value: {self.stop_flag.value}')
       self._stop_realtime_process()
       if hasattr(self, 'refresh_flag'):
           self.refresh_flag.value = False

       # 2️⃣ 停止 realtime_process
       if getattr(self, 'realtime_process', None):
           if self.realtime_process.is_alive():
               self.realtime_process.join(timeout=1)
               if self.realtime_process.is_alive():
                   logger.info("realtime_process 强制终止")
                   self.realtime_process.terminate()
                   self.realtime_process.join()
           self.realtime_process = None

       # 3️⃣ 停止 DataLoaderThread (避免 QThread Destroyed 崩溃)
       if hasattr(self, 'loader') and self.loader:
           if self.loader.isRunning():
               logger.info("Stopping DataLoaderThread...")
               self.loader.quit()
               if not self.loader.wait(1000): # 等待 1 秒
                   logger.warning("DataLoaderThread did not stop, terminating...")
                   self.loader.terminate()
                   self.loader.wait()
           self.loader = None
       # 当 GUI 关闭时，触发 stop_event
       stop_event.set()

       print(f'closeEvent: OK')
       # Accept the event to close
       if hasattr(self, 'voice_thread'):
           self.voice_thread.stop()
       event.accept()
       # 6️⃣ 调用父类 closeEvent
       super().closeEvent(event)


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
    # ------------------ 1. Logger ------------------
    if log_level is not None:
        logger.setLevel(log_level.value)

    # ------------------ 2. Primary/Secondary ------------------
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    stop_flag = stop_flag if stop_flag else mp.Value('b', True)

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
    app = QApplication(sys.argv)
    window = MainWindow(stop_flag, log_level, debug_realtime, command_queue=command_queue)
    start_code = initial_code

    # 启动 ListenerThread
    listener = CommandListenerThread(server_socket)
    listener.command_received.connect(window.load_stock_by_code)
    listener.dataframe_received.connect(window.on_dataframe_received)
    listener.start()

    # 确保 listener 已经准备好接收连接
    time.sleep(0.05)

    # ------------------ 5. 显示 GUI ------------------
    window.show()
    if start_code is not None:
        window.load_stock_by_code(start_code)
    elif len(sys.argv) > 1:
        start_code = sys.argv[1]
        if len(start_code) in (6, 8):
            window.load_stock_by_code(start_code)

    ret = app.exec()  # 阻塞 Qt 主循环

    # ------------------ 6. 清理 ------------------
    stop_flag.value = False
    try:
        listener.stop()
    except Exception:
        pass
    window.close()
    sys.exit(ret)


def main_src(initial_code='000002', stop_flag=None, log_level=None, debug_realtime=False, command_queue=None):
    # --- 1. 尝试成为 Primary Instance ---
        # logger = LoggerFactory.getLogger()
    if log_level is not None:
        logger.setLevel(log_level.value)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
    listener.command_received.connect(window.load_stock_by_code)
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
            default="info",
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

    main(
        initial_code=initial_code,
        stop_flag=stop_flag,
        log_level=log_level,
        debug_realtime=realtime
    )

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
