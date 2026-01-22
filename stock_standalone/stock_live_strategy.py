# -*- coding: utf-8 -*-
"""
Stock Live Strategy & Alert System
高性能实时股票跟踪与语音报警模块
"""
from __future__ import annotations
import threading
import time
import os
import winsound
from datetime import datetime, timedelta
import multiprocessing as mp
import pandas as pd
from queue import Empty
from typing import Any, Optional, Callable, Dict, List, Union
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from intraday_decision_engine import IntradayDecisionEngine
from risk_engine import RiskEngine
from trading_logger import TradingLogger
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory

import logging
logger: logging.Logger = LoggerFactory.getLogger(name="stock_live_strategy")
MAX_DAILY_ADDITIONS = cct.MAX_DAILY_ADDITIONS
# Optional imports
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    logger.warning("pyttsx3 not found, voice disabled.")

try:
    from stock_selector import StockSelector
except ImportError:
    StockSelector = None
    logger.warning("StockSelector not found.")

from sector_risk_monitor import SectorRiskMonitor

# 日内形态检测器
try:
    from intraday_pattern_detector import IntradayPatternDetector, PatternEvent
    HAS_PATTERN_DETECTOR = True
except ImportError:
    HAS_PATTERN_DETECTOR = False
    logger.warning("IntradayPatternDetector not found.")

try:
    import pythoncom
except ImportError:
    pythoncom = None

import re

def normalize_speech_text(text: str) -> str:
    """
    将数值符号转换为适合中文语音播报的表达
    """
    # 百分号
    text = text.replace('%', '百分之')

    # 负数（-10, -3.5）
    text = re.sub(
        r'(?<!\d)-(\d+(\.\d+)?)',
        r'负\1',
        text
    )

    # 正号（可选）
    text = re.sub(
        r'(?<!\d)\+(\d+(\.\d+)?)',
        r'正\1',
        text
    )

    # 小数点
    text = re.sub(r'(\d+)\.(\d+)', r'\1点\2', text)

    return text

def _voice_process_target(queue: mp.Queue, stop_event: mp.Event):
    """
    语音播报外部进程目标函数
    """
    engine = None
    try:
        if pythoncom:
            pythoncom.CoInitialize()
        
        if pyttsx3:
            try:
                engine = pyttsx3.init()
                # 设置语速
                rate = engine.getProperty('rate')
                if isinstance(rate, (int, float)):
                    engine.setProperty('rate', rate + 20)
                else:
                    engine.setProperty('rate', 200)
            except Exception as e:
                logger.error(f"Voice Process TTS Init Error: {e}")
                pyttsx3_available = False
            else:
                pyttsx3_available = True
        else:
            pyttsx3_available = False

        while not stop_event.is_set():
            try:
                # 获取任务
                data = queue.get(timeout=0.5)
                text = data.get('text')
                
                if text:
                    speech_text = normalize_speech_text(text)
                    logger.info(f"📢 [VoiceProcess] 播报: {speech_text}")
                    
                    # 每次循环初始化，确保最大限度的兼容性和 COM 状态正确
                    engine = None
                    try:
                        if pythoncom:
                            pythoncom.CoInitialize()
                        
                        if pyttsx3:
                            engine = pyttsx3.init()
                            # 设置语速
                            rate = engine.getProperty('rate')
                            if isinstance(rate, (int, float)):
                                engine.setProperty('rate', rate + 20)
                            else:
                                engine.setProperty('rate', 200)
                            
                            engine.say(speech_text)
                            engine.runAndWait()
                            
                    except Exception as e:
                        logger.error(f"TTS Speak Error in VoiceProcess: {e}")
                    finally:
                        if engine:
                            try:
                                engine.stop()
                                del engine
                            except: pass
                        if pythoncom:
                            pythoncom.CoUninitialize()
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"VoiceProcess Loop Error: {e}")
                time.sleep(1)

    finally:
        logger.info("VoiceProcess loop terminated.")


class VoiceAnnouncer:
    """独立的语音播报引擎 (多进程版)"""
    queue: mp.Queue
    on_speak_start: Optional[Callable[[Optional[str]], None]]
    on_speak_end: Optional[Callable[[Optional[str]], None]]
    _stop_event: Any # mp.synchronize.Event
    current_code: Optional[str]
    _process: Optional[mp.Process]

    def __init__(self) -> None:
        self.queue = mp.Queue()
        self.on_speak_start = None # 回调函数: func(code)
        self.on_speak_end = None   # 回调函数: func(code)
        self._stop_event = mp.Event()
        self._pause_event = threading.Event()  # 本地控制暂停 (仍保留用于逻辑兼容)
        self._pause_event.set()
        self.current_code = None
        self._is_stopped = False  # 停止标志
        self._pending_timers: list[threading.Timer] = []  # 跟踪待处理的 Timer
        self._timer_lock = threading.Lock()  # 保护 Timer 列表
        
        if pyttsx3:
            # 开启独立进程
            self._process = mp.Process(target=_voice_process_target, args=(self.queue, self._stop_event), daemon=True)
            self._process.start()
            logger.info("VoiceAnnouncer: 多进程播报引擎已启动")
        else:
            self._process = None

    def pause(self) -> None:
        """暂停语音播报"""
        self._pause_event.clear()
        logger.debug("VoiceAnnouncer: 已暂停 (本地队列仍会接收但不发送)")
    
    def resume(self) -> None:
        """恢复语音播报意识"""
        self._pause_event.set()
        logger.debug("VoiceAnnouncer: 已恢复")
    
    @property
    def is_speaking(self) -> bool:
        """多进程下准确状态检测较难，暂且通过队列判定"""
        return not self.queue.empty()
    
    def wait_for_safe(self, timeout: float = 3.0) -> bool:
        """等待队列清空"""
        start = time.time()
        while self.is_speaking:
            if time.time() - start > timeout:
                return False
            time.sleep(0.1)
        return True

    def say(self, text: str, code: Optional[str] = None) -> None:
        if self._is_stopped:
            return
        if self._process and self._process.is_alive():
            if not self._pause_event.is_set():
                 logger.debug(f"Voice (Paused): {text}")
                 return
            
            # 触发主进程回调
            if self.on_speak_start:
                try: self.on_speak_start(code)
                except: pass
            
            try:
                self.queue.put({'text': text, 'code': code}, block=False)
            except Exception as e:
                logger.error(f"Failed to put to voice queue: {e}")
                return
            
            # 由于是异步进程，我们无法精准得知结束时间
            # 使用跟踪的 Timer，便于退出时取消
            if self.on_speak_end:
                duration = len(text) * 0.3 + 1.0
                
                def _on_timer_done(target_code: Optional[str]):
                    # 检查是否已停止
                    if self._is_stopped:
                        return
                    if self.on_speak_end:
                        try:
                            self.on_speak_end(target_code)
                        except Exception:
                            pass
                
                timer = threading.Timer(duration, lambda: _on_timer_done(code))
                timer.daemon = True  # 设为守护线程
                with self._timer_lock:
                    # 清理已完成的 Timer
                    self._pending_timers = [t for t in self._pending_timers if t.is_alive()]
                    self._pending_timers.append(timer)
                timer.start()
        else:
            logger.info(f"Voice (Disabled/Dead): {text}")

    def cancel_for_code(self, target_code: str):
        """停止指定代码 (多进程下只能清空待播报项)"""
        # 由于跨进程控制 engine.stop() 较难，主要清理队列
        temp_list = []
        try:
            while True:
                item = self.queue.get_nowait()
                if item.get('code') != target_code:
                    temp_list.append(item)
        except Empty:
            pass
        
        for item in temp_list:
            self.queue.put(item)

    def stop(self):
        """停止语音播报引擎"""
        self._is_stopped = True
        
        # 取消所有待处理的 Timer
        with self._timer_lock:
            for timer in self._pending_timers:
                try:
                    timer.cancel()
                except Exception:
                    pass
            self._pending_timers.clear()
        
        # 清空队列，防止阻塞
        try:
            while True:
                self.queue.get_nowait()
        except Empty:
            pass
        
        self._stop_event.set()
        
        if self._process and self._process.is_alive():
            # 给进程短暂时间自行退出
            self._process.join(timeout=0.5)
            # 如果还没退出，强制终止
            if self._process.is_alive():
                try:
                    self._process.terminate()
                    self._process.join(timeout=0.3)
                except Exception:
                    pass
            # 最后手段：杀死进程
            if self._process.is_alive():
                try:
                    self._process.kill()
                except Exception:
                    pass


class StrategySupervisor:
    """
    策略监理机制 (Strategy Supervision Mechanism)
    负责从盈利角度对信号进行最终审核，拦截无效或高风险交易（如追涨）。
    具备从日志和历史数据自升级的能力。
    """
    # 定义约束字典的精确类型以消除 Pylance 歧义
    constraints: dict[str, float | int | list[str]]

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        self.logger = logger_instance
        self.constraints = {
            'anti_chase_threshold': 0.05,  # 距分时均价偏离度上限
            'min_market_win_rate': 0.35,  # 最低市场胜率门槛
            'max_loss_streak': 2,         # 最大允许连亏次数 (15天内)
            'ignore_concepts': ['ST', '退市']  # 规避概念
        }
        self._load_dynamic_constraints()

    def _load_dynamic_constraints(self):
        """从外部 JSON 加载由 TradingAnalyzer 生成的优化参数"""
        try:
            config_path = os.path.join(cct.get_base_path(), "config", "supervisor_constraints.json")
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    dynamic_data: dict[str, Any] = json.load(f)
                    self.constraints.update(dynamic_data)
                    logger.info(f"🛡️ 策略监理已载入动态/自升级约束: {dynamic_data}")
        except Exception as e:
            logger.debug(f"No dynamic constraints found or load failed: {e}")

    def veto(self, code: str, decision: dict[str, Any], row: pd.Series[Any], snap: dict[str, Any]) -> tuple[bool, str]:
        """
        审核决策。返回: (是否否决, 否决理由)
        """
        # 仅对买入/加仓信号进行监理
        action = decision.get("action", "")
        if action not in ("买入", "加仓", "BUY", "ADD"):
            return False, ""

        # 1. 规避板块/名称
        name = str(snap.get('name', ''))
        ignore_concepts = self.constraints.get('ignore_concepts', [])
        if isinstance(ignore_concepts, list):
            for bad in ignore_concepts:
                if isinstance(bad, str) and bad in name:
                    return True, f"命中规避概念: {bad}"

        # 2. 防追涨拦截 (Anti-Chase) - 距日内均价(VWAP)偏离度
        current_price = float(row.get('trade', 0.0)) # type: ignore
        # 优先使用实时服务提供的分时均价，否则从 row 转换
        amount = float(row.get('amount', 0.0)) # type: ignore
        volume = float(row.get('volume', 0.0)) # type: ignore
        vwap = (amount / volume) if volume > 0 else 0.0
        
        if vwap > 0:
            bias = (current_price - vwap) / vwap
            threshold = self.constraints.get('anti_chase_threshold', 0.05)
            if isinstance(threshold, (int, float)) and bias > float(threshold):
                return True, f"偏离均价过高({bias:.1%})，防止追涨"

        # 3. 情绪冰点拦截 (Sentiment Veto)
        market_win_rate = float(snap.get('market_win_rate', 1.0))
        min_win_rate = self.constraints.get('min_market_win_rate', 0.35)
        if isinstance(min_win_rate, (int, float)) and market_win_rate < float(min_win_rate):
            return True, f"全场胜率过低({market_win_rate:.1%})，提高防御"

        # 4. 霉运/个股冷宫机制 (Failure Filter)
        loss_streak = int(snap.get('loss_streak', 0))
        max_loss = self.constraints.get('max_loss_streak', 2)
        if isinstance(max_loss, (int, float)) and loss_streak >= int(max_loss):
            return True, f"个股近期连亏{loss_streak}次，强行降温"

        return False, ""

class StockLiveStrategy:
    """
    高性能实时行情监控策略类
    
    支持配置参数：
    - alert_cooldown: 报警冷却时间(秒)
    - stop_loss_pct: 止损百分比
    - take_profit_pct: 止盈百分比
    - trailing_stop_pct: 移动止盈回撤百分比
    - max_single_stock_ratio: 单只股票最大仓位
    - min_position_ratio: 最小仓位比例
    - risk_duration_threshold: 风险持续时间阈值
    """
    def __init__(self,
                 master: Any = None, 
                 alert_cooldown: float = 60,
                 stop_loss_pct: float = 0.05,
                 take_profit_pct: float = 0.10,
                 trailing_stop_pct: float = 0.03,
                 max_single_stock_ratio: float = 0.3,
                 min_position_ratio: float = 0.05,
                 risk_duration_threshold: float = 300,
                 voice_enabled: bool = True,
                 realtime_service: Any = None):
        # --- 实例属性注解 (PEP 526) ---
        self.master: Any = master
        self._voice: VoiceAnnouncer
        self.voice_enabled: bool
        self._monitored_stocks: dict[str, Any]
        self._last_process_time: float
        self._alert_cooldown: float
        self.enabled: bool
        self.executor: ThreadPoolExecutor
        self.config_file: str
        self.alert_callback: Optional[Callable[[str, str, str], None]]
        self.decision_engine: IntradayDecisionEngine
        self.trading_logger: TradingLogger
        self._risk_engine: RiskEngine
        self.realtime_service: Any # RealtimeDataService
        self.auto_loop_enabled: bool
        self.batch_state: str
        self.current_batch: list[str]
        self._settlement_prep_done: bool
        self._last_settlement_date: Optional[str]
        self._market_win_rate_cache: float
        self._market_win_rate_ts: float
        self.scan_hot_concepts_status: bool
        self.shadow_engine: IntradayDecisionEngine

        self._voice = VoiceAnnouncer()
        self.voice_enabled = voice_enabled
        self._monitored_stocks = {} 
        self._last_process_time = 0.0
        
        # 初始化板块监控
        self.sector_monitor = SectorRiskMonitor()
        self._last_sector_status: dict[str, Any] = {}

        self.signal_history: deque[dict[str, Any]] = deque(maxlen=200)
        self._alert_cooldown = alert_cooldown
        self.enabled = True
        self._is_stopping: bool = False

        self.config_file = "voice_alert_config.json"
        self.alert_callback = None
        self.realtime_service = realtime_service
        self.scan_hot_concepts_status = True
        
        # --- 外部数据缓存 (55188.cn) ---
        self.ext_data_55188: pd.DataFrame = pd.DataFrame()
        self.last_ext_update_ts: float = 0
        
        # --- 自动交易相关状态初始化 ---
        self.auto_loop_enabled = False
        self.batch_state = "IDLE"
        self.current_batch = []
        self.batch_last_check: float = 0.0
        self._settlement_prep_done = False
        self._last_settlement_date = None
        self._market_win_rate_cache = 0.5
        self._market_win_rate_ts = 0.0

        logger.info(f'StockLiveStrategy 初始化: alert_cooldown={alert_cooldown}s, '
                   f'stop_loss={stop_loss_pct:.1%}, take_profit={take_profit_pct:.1%}')
        
        # 使用 max_workers=1 避免并发资源竞争，本身计算量很小
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        # --- 初始化记录器 (必须在 _load_monitors 之前) ---
        self.trading_logger = TradingLogger()
        self.supervisor = StrategySupervisor(self.trading_logger) # type: ignore # ⭐ 注入盈利监理器

        self._load_monitors()
        self.df: Optional[pd.DataFrame] = None

        # 初始化决策引擎（带止损止盈配置）
        self.decision_engine = IntradayDecisionEngine(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            max_position=max_single_stock_ratio
        )

        # --- ⭐ 影子策略引擎 (用于参数比对与自优化) ---
        self.shadow_engine = IntradayDecisionEngine(
            stop_loss_pct=stop_loss_pct * 0.8, # 更严苛的止损
            take_profit_pct=take_profit_pct * 1.2, # 更高的止盈期待
            trailing_stop_pct=trailing_stop_pct,
            max_position=max_single_stock_ratio
        )
        
        # 初始化风控引擎
        self._risk_engine = RiskEngine(
            max_single_stock_ratio=max_single_stock_ratio,
            min_ratio=min_position_ratio,
            alert_cooldown=alert_cooldown,
            risk_duration_threshold=risk_duration_threshold
        )
        self._last_import_logical_date: Optional[str] = None

        # --- ⭐ 日内形态检测器 ---
        if HAS_PATTERN_DETECTOR:
            self.pattern_detector = IntradayPatternDetector(
                cooldown=120,           # 同一形态同一股票 2 分钟冷却
                publish_to_bus=True     # 自动发布到信号总线
            )
            self.pattern_detector.on_pattern = self._on_pattern_detected
            logger.info("IntradayPatternDetector initialized.")

        # --- Automatic Trading Loop State ---
        # self.auto_loop_enabled = False (已经在上方初始化)
        # self.batch_state = "IDLE"
        self.batch_start_time: float = 0.0
        self.batch_last_check: float = 0.0

    def stop(self):
        """停止策略引擎并关闭后台线程"""
        if self._is_stopping:
             return
        self._is_stopping = True
        logger.info("Stopping StockLiveStrategy...")
        
        # 1. 停止语音播报
        if hasattr(self, "_voice") and self._voice:
            try:
                self._voice.stop()
            except Exception as e:
                logger.error(f"Error stopping VoiceAnnouncer: {e}")
                
        # 2. 停止线程池 (不再接收新任务，不等待)
        if hasattr(self, "executor") and self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # Python 3.8 不支持 cancel_futures
                self.executor.shutdown(wait=False)
            except Exception as e:
                logger.error(f"Error shutting down executor: {e}")

        logger.info("StockLiveStrategy stopped.")



    # ------------------------------------------------------------------
    # Alert Cooldown 控制
    # ------------------------------------------------------------------
    def set_alert_cooldown(self, cooldown: float | None):
        """
        动态设置告警冷却时间（秒）
        可在运行中安全调用
        """
        if cooldown is None:
            return

        self._alert_cooldown = float(cooldown)
        if cooldown < 0:
            raise ValueError("alert_cooldown must be >= 0")

        # with self._lock:
        self._alert_cooldown = cooldown
        logger.info(f"set_alert_cooldown : {self._alert_cooldown}")

    def get_alert_cooldown(self) -> float:
        """读取当前告警冷却时间"""
        return self._alert_cooldown
        
    def set_voice_enabled(self, enabled: bool):
        """运行时开启/关闭语音播报"""
        self.voice_enabled = bool(enabled)
        logger.info(f"Voice announcer enabled = {self.voice_enabled}")

    def set_alert_callback(self, callback: Callable[[str, str, str], None]) -> None:
        """设置报警回调函数"""
        self.alert_callback = callback

    def set_realtime_service(self, service):
        """注入实时数据服务"""
        self.realtime_service = service

    def set_scan_hot_concepts(self, status=True):
        """注入实时数据服务"""
        self.scan_hot_concepts_status = status

    def _calculate_position(self, stock: dict, current_price: float, current_nclose: float, last_close: float, last_percent: Optional[float], last_nclose: float) -> tuple[str, float]:
        """根据今日/昨日数据计算动态仓位与操作"""
        position_ratio = round(1.0/self.stock_count,1)
        logger.debug(f'仓位分配:position_ratio:{position_ratio}')
        action = "持仓"

        valid_yesterday = (last_close > 0) and (last_percent is not None and -100 < last_percent < 100) and (last_nclose > 0)
        valid_today = (current_price > 0) and (current_nclose > 0)

        # 今日均价偏离
        if valid_today:
            deviation_today = (current_nclose - current_price) / current_nclose
            max_normal_pullback = (last_percent / 5 / 100 if valid_yesterday else 0.01)
            if deviation_today > max_normal_pullback + 0.0005:
                position_ratio *= 0.7
                action = "减仓"

        # 昨日收盘偏离
        if valid_yesterday:
            deviation_last = (last_close - current_price) / last_close
            max_normal_pullback = last_percent / 5 / 100
            if deviation_last > max_normal_pullback + 0.0005:
                position_ratio *= 0.5
                action = "卖出"

        # 趋势加仓
        if valid_today and current_price > current_nclose:
            position_ratio = min(1.0, position_ratio + 0.2)
            if action == "持仓":
                action = "买入"

        position_ratio = max(0.0, min(1.0, position_ratio))
        return action, position_ratio

    def _load_monitors(self):
        """加载配置并进行结构修复，同时恢复行情快照"""
        self._monitored_stocks = {}

        try:
            import json
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._monitored_stocks = json.load(f)

            # --- [新增] 从数据库恢复持仓股监控，防止重启后丢失卖点 ---
            if hasattr(self, 'trading_logger'):
                try:
                    trades = self.trading_logger.get_trades()
                    open_trades = [t for t in trades if t['status'] == 'OPEN']
                    recovered_count = 0
                    for t in open_trades:
                        code = str(t['code']).zfill(6)
                        resample = t.get('resample', 'd')
                        # 兼容逻辑：为了支持多周期，理想情况下 key 应该是 (code, resample)
                        # 但为了最少破坏现有结构，如果已经存在同 code 但不同周期的，我们可能需要特殊处理
                        # 暂且遵循 "目前代码库习惯"，如果不存在则添加
                        if code not in self._monitored_stocks:
                            self._monitored_stocks[code] = {
                                'name': t['name'],
                                'rules': [{'type': 'price_up', 'value': float(t['buy_price'])}],
                                'last_alert': 0,
                                'resample': resample,
                                'created_time': t['buy_date'][:13] if t.get('buy_date') else datetime.now().strftime("%Y-%m-%d %H"),
                                'tags': "recovered_holding",
                                'snapshot': {
                                    'cost_price': float(t['buy_price']),
                                    'buy_date': t.get('buy_date', '')
                                }
                            }
                            recovered_count += 1
                    if recovered_count > 0:
                        logger.info(f"♻️ 监控恢复: 从数据库自动载入 {recovered_count} 只活跃持仓股")
                except Exception as db_e:
                    logger.error(f"恢复持仓监控失败: {db_e}")

            # ✅ 结构迁移 / 补齐
            for key, stock in self._monitored_stocks.items():
                stock.setdefault('rules', [])
                stock.setdefault('last_alert', 0)
                stock.setdefault('resample', 'd') # 默认日线
                stock.setdefault('created_time', datetime.now().strftime("%Y-%m-%d %H"))
                stock.setdefault('tags', "")
                stock.setdefault('snapshot', {})  # 快照信息

                # 确保 code 字段存在 (从 key 补齐)
                if 'code' not in stock:
                    stock['code'] = key.split('_')[0]
                
                # 确保 resample 字段存在
                if 'resample' not in stock:
                    stock['resample'] = 'd'
                
                # 保持使用 code 作为 key（不再迁移到 code_resample 格式）
                # 旧逻辑已移除：不再将 000561 改为 000561_d

            # --- [新增] 从数据库恢复持仓股监控，防止重启后丢失卖点 ---
            if hasattr(self, 'trading_logger'):
                try:
                    trades = self.trading_logger.get_trades()
                    open_trades = [t for t in trades if t['status'] == 'OPEN']
                    recovered_count = 0
                    for t in open_trades:
                        code = str(t['code']).zfill(6)
                        resample = t.get('resample', 'd')
                        key = code  # 使用纯 code 作为 key，不再加 _resample 后缀
                        
                        if key not in self._monitored_stocks:
                            self._monitored_stocks[key] = {
                                'code': code,
                                'name': t['name'],
                                'rules': [{'type': 'price_up', 'value': float(t['buy_price'])}],
                                'last_alert': 0,
                                'resample': resample,
                                'created_time': t['buy_date'][:19] if t.get('buy_date') else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                'tags': "recovered_holding",
                                'snapshot': {
                                    'cost_price': float(t['buy_price']),
                                    'buy_date': t.get('buy_date', '')
                                }
                            }
                            recovered_count += 1
                    if recovered_count > 0:
                        logger.info(f"♻️ 监控恢复: 从数据库自动载入 {recovered_count} 只活跃持仓股")
                        self._save_monitors() # 保存恢复后的状态
                except Exception as db_e:
                    logger.error(f"恢复持仓监控失败: {db_e}")

                # ✅ 重建 rule_keys（不从文件读取）
                rule_keys = set()
                code = stock['code']
                for r in stock['rules']:
                    try:
                        r_key = self._rule_key(r['type'], r['value'])
                        rule_keys.add(r_key)
                    except Exception:
                        logger.warning(f"Invalid rule skipped for {code}: {r}")

                stock['rule_keys'] = rule_keys

                # ✅ 可选：加载 snapshot 到运行时对象
                snap = stock.get('snapshot', {})
                stock['trade'] = snap.get('trade', 0)
                stock['percent'] = snap.get('percent', 0)
                stock['volume'] = snap.get('volume', 0)
                stock['ratio'] = snap.get('ratio', 0)
                stock['nclose'] = snap.get('nclose', 0)
                stock['last_close'] = snap.get('last_close', 0)
                stock['ma5d'] = snap.get('ma5d', 0)
                stock['ma10d'] = snap.get('ma10d', 0)

            self.stock_count: int = len(self._monitored_stocks) 
            logger.info(
                f"Loaded voice monitors from {self.config_file}, "
                f"总计持仓stocks={len(self._monitored_stocks)}"
            )

        except Exception as e:
            logger.error(f"Failed to load voice monitors: {e}")

    def import_daily_candidates(self) -> str:
        """
        调用 StockSelector 筛选强势股，并合并到当前监控列表
        报警中选股需要根据实际判断是重复筛选还是有效筛选
        """
        if not StockSelector:
            return "StockSelector 模块不可用"
        
        try:
            # 确定逻辑日期
            is_trading = cct.get_work_time_duration()
            # 如果是非交易期，通常获取前一交易日数据
            logical_date = cct.get_today() if is_trading else cct.get_last_trade_date()
            
            # 记录最后一次成功导入的逻辑日期，避免重复筛选
            if hasattr(self, '_last_import_logical_date') and self._last_import_logical_date == logical_date:
                # 如果是交易期间且强制刷新，可以在这里增加 force 参数支持，目前暂定跳过
                if not is_trading:
                    return f"非交易时段：逻辑日期 {logical_date} 已在监控列表，无需重复筛选"
                else:
                    logger.info(f"交易时段：逻辑日期 {logical_date} 已有记录，尝试更新行情...")

            selector = StockSelector()
            # 传入逻辑日期 (需要修改 selector.get_candidates_df 支持 date 参数)
            df_candidates = selector.get_candidates_df(logical_date=logical_date)
            
            if df_candidates.empty:
                return f"筛选器未返回逻辑日期 {logical_date} 的任何标的"
            

            added_count = 0
            existing_codes = set(self._monitored_stocks.keys())
            
            for _, row in df_candidates.iterrows():
                code = row['code']
                name = row.get('name', '')
                if code not in existing_codes:
                    self._monitored_stocks[code] = {
                        "name": name,
                        "rules": [],
                        "last_alert": 0,
                        "created_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "tags": f"auto_{logical_date}",
                        "snapshot": {
                            "trade": float(row.get('price', 0.0)),
                            "percent": float(row.get('percent', 0.0)),
                            "ratio": float(row.get('ratio', 0.0)),
                            "amount_desc": row.get('amount', 0),
                            "status": str(row.get('status', '')),
                            "score": float(row.get('score', 0.0)),
                            "reason": str(row.get('reason', ''))
                        }
                    }
                    added_count += 1
                else:
                    # 如果已存在，更新其 snapshot
                    snap = self._monitored_stocks[code]['snapshot']
                    snap.update({
                        "status": str(row.get('status', snap.get('status', ''))),
                        "score": float(row.get('score', snap.get('score', 0.0))),
                        "reason": str(row.get('reason', snap.get('reason', '')))
                    })
            
            self._last_import_logical_date = logical_date
            
            if added_count > 0:
                self._save_monitors()
                logger.info(f"逻辑日期 {logical_date}: 已导入 {added_count} 只强势股")
                return f"成功导入 {added_count} 只标的 (日期:{logical_date})"
            else:
                return f"逻辑日期 {logical_date}: 标的已在监控列表中"
                
        except Exception as e:
            logger.error(f"导入筛选股失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"导入失败: {e}"



    def _save_monitors(self):
        """保存配置（不包含派生字段，同时增加即时行情信息）"""
        try:
            import json
            data = {}

            for key, stock in self._monitored_stocks.items():
                # --- 构建基础数据 ---
                record = {
                    'name': stock.get('name'),
                    'rules': stock.get('rules', []),
                    'last_alert': stock.get('last_alert', 0),
                    'resample': stock.get('resample', 'd'), # 保存周期信息
                    'created_time': stock.get('created_time', datetime.now().strftime("%Y-%m-%d %H")),
                    'tags': stock.get('tags', ""),
                    'added_date': stock.get('added_date', ""),
                    'rule_type_tag': stock.get('rule_type_tag', "")
                }

                # --- 可选：添加行情快照 ---
                if hasattr(self, 'df') and self.df is not None and not self.df.empty:
                    # 从 key 中提取原始 code
                    code = stock.get('code', key.split('_')[0])
                    if code in self.df.index:
                        row = self.df.loc[code]
                        try:
                            record['snapshot'] = {
                                'trade': float(row.get('trade', 0)),
                                'percent': float(row.get('percent', 0)),
                                'volume': float(row.get('volume', 0)),
                                'ratio': float(row.get('ratio', 0)),
                                'nclose': float(row.get('nclose', 0)),
                                'last_close': float(row.get('lastp1d', 0)),
                                'ma5d': float(row.get('ma5d', 0)),
                                'ma10d': float(row.get('ma10d', 0))
                            }
                        except (ValueError, TypeError):
                            # 如果数据异常，不存 snapshot
                            pass

                data[key] = record

            # --- 保存到 JSON ---
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # --- [新增] 同步到数据库，支持跨终端状态一致性 ---
            if hasattr(self, 'trading_logger'):
                for key, stock in self._monitored_stocks.items():
                    code_from_key = key.split('_')[0]
                    resample_from_key = stock.get('resample', 'd')
                    self.trading_logger.log_voice_alert_config(
                        code=code_from_key,
                        resample=resample_from_key,
                        name=stock.get('name', ''),
                        rules=json.dumps(stock.get('rules', [])),
                        last_alert=stock.get('last_alert', 0),
                        tags=stock.get('tags', ''),
                        rule_type_tag=stock.get('rule_type_tag', '')
                    )

        except Exception as e:
            logger.error(f"Failed to save voice monitors: {e}")

    def _rule_key(self, rule_type, value):
        return f"{rule_type}:{value:.2f}"

    def add_monitor(self, code, name, rule_type, value, tags=None, resample='d'):
        value = float(value)
        # 使用纯 code 作为 key（不再使用复合 key）
        key = code

        if key not in self._monitored_stocks:
            self._monitored_stocks[key] = {
                'code': code, # 保存原始代码以供查询
                'name': name,
                'rules': [],
                'last_alert': 0,
                'resample': resample,
                'created_time': datetime.now().strftime("%Y-%m-%d %H"),
                'added_date': datetime.now().strftime('%Y-%m-%d'), # [新增] 用于已添加数量统计
                'tags': tags or ""
            }
        
        stock = self._monitored_stocks[key]
        # 如果提供了 tags 且不为空，则更新（覆盖旧的或空的）
        if tags:
            stock['tags'] = tags
        
        # 记录触发加入的规则类型
        stock['rule_type_tag'] = rule_type
        
        # 确保 created_time 和 added_date 存在 (对于旧数据)
        if 'created_time' not in stock:
            stock['created_time'] = datetime.now().strftime("%Y-%m-%d %H")
        if 'added_date' not in stock:
            stock['added_date'] = datetime.now().strftime('%Y-%m-%d')

        # 确保派生字段存在
        stock.setdefault('rule_keys', set())

        # ✅ 查找是否已存在同 type 规则
        for r in stock['rules']:
            if r['type'] == rule_type:
                old_value = r['value']
                r['value'] = value

                # 更新 rule_keys
                old_key = self._rule_key(rule_type, old_value)
                new_key = self._rule_key(rule_type, value)
                stock['rule_keys'].discard(old_key)
                stock['rule_keys'].add(new_key)

                self._save_monitors()
                logger.info(
                    f"Monitor updated: {name}({code}) {rule_type} {old_value} → {value}"
                )
                return "updated"

        # ✅ 不存在才新增
        rule_key = self._rule_key(rule_type, value)

        stock['rules'].append({
            'type': rule_type,
            'value': value
        })
        stock['rule_keys'].add(rule_key)

        self._save_monitors()
        
        # 记录到历史以便前端查询
        self.signal_history.appendleft({
            'time': datetime.now().strftime("%H:%M:%S"),
            'code': code,
            'name': name,
            'type': rule_type,
            'value': value,
            'msg': f"Added monitor: {rule_type} > {value}"
        })
        
        logger.info(
            f"Monitor added: {name}({code}) {rule_type} > {value}"
        )
        return "added"

    def process_data(self, df_all: pd.DataFrame, concept_top5: list = None, resample: str = 'd') -> None:
        """
        处理每一帧的行情数据
        """
        if not self.enabled or df_all is None or df_all.empty:
            return

        # 标记当前处理的周期
        self.current_resample = resample 
        
        # --- 1. 热点题材领涨股发现 (Algorithm Expansion) ---
        if 925 <= cct.get_now_time_int() <= 1505:
             self.executor.submit(self._scan_hot_concepts, df_all, concept_top5, resample=resample)
        
        # 2. 规则引擎监控 (Existing rules)
        # self._check_risk_control(df_all)
        
        # 3. 策略判定
        self._check_strategies(df_all, resample=resample)
        # 1. 交易期间判断: 0915 至 1502
        is_trading = cct.get_work_time_duration()
        today_str = datetime.now().strftime('%Y-%m-%d')
        now_time_str = datetime.now().strftime('%H:%M')

        # --- 自动启动判断 (Auto Start) ---
        # 交易时段 + 未启用 + 今日未结算过
        if is_trading and not self.auto_loop_enabled:
            if self._last_settlement_date != today_str:
                self.start_auto_trading_loop()

        # --- 自动收盘结算判断 (Auto Settlement) ---
        if not is_trading:
             # 判断是否收盘 (15:00 以后) 且今日未结算
             # 注意：需排除中午休市 (11:30-13:00)
             if now_time_str >= "15:00":
                 if self._last_settlement_date != today_str:
                     self._perform_daily_settlement()
             
             # 非交易时间停止策略计算
             return

        # 限制频率: 至少间隔 1s 处理一次，避免 UI 线程密集调用导致积压
        now = time.time()
        if now - self._last_process_time < 2.0:
            return
        
        self._last_process_time = now
        
        # 异步执行
        self.df = df_all.copy()
        logger.info(f"Strategy: Processing cycle for {len(self._monitored_stocks)} monitored stocks")

        if self.auto_loop_enabled:
             self.executor.submit(self._process_auto_loop, df_all, concept_top5)

        # --- [新增] 板块风险监控 (Sector Risk Monitoring) ---
        if concept_top5 and cct.get_now_time_int() > 916:
            try:
                sector_status = self.sector_monitor.update(df_all, concept_top5)
                self._last_sector_status = sector_status
            except Exception as e:
                logger.error(f"Sector Monitor Check Failed: {e}")

        # --- [关键] 异步触发策略判定 ---
        self.executor.submit(self._check_strategies, self.df, resample=resample)

        # --- ⭐ 数据反馈与回显 (Enrich df_all for UI) ---
        # 将各股的最新决策与监理感知指标写回 df_all，以便前端实时显示
        for key, stock in self._monitored_stocks.items():
            code = stock.get('code', key.split('_')[0])
            if code in df_all.index:
                snap = stock.get('snapshot', {})
                df_all.at[code, 'last_action'] = snap.get('last_action', '')
                df_all.at[code, 'last_reason'] = snap.get('last_reason', '')
                df_all.at[code, 'shadow_info'] = snap.get('shadow_info', '')
                df_all.at[code, 'market_win_rate'] = snap.get('market_win_rate', 0.5)
                df_all.at[code, 'loss_streak'] = snap.get('loss_streak', 0)
                df_all.at[code, 'vwap_bias'] = snap.get('vwap_bias', 0.0)
            elif 'code' in df_all.columns:
                # 兼容 code 也在列里的情况
                mask = df_all['code'] == code
                if mask.any():
                    snap = stock.get('snapshot', {})
                    df_all.loc[mask, 'last_action'] = snap.get('last_action', '')
                    df_all.loc[mask, 'last_reason'] = snap.get('last_reason', '')
                    df_all.loc[mask, 'shadow_info'] = snap.get('shadow_info', '')
                    df_all.loc[mask, 'market_win_rate'] = snap.get('market_win_rate', 0.5)
                    df_all.loc[mask, 'loss_streak'] = snap.get('loss_streak', 0)
                    df_all.loc[mask, 'vwap_bias'] = snap.get('vwap_bias', 0.0)


    def _scan_hot_concepts(self, df: pd.DataFrame | None, concept_top5: list[Any], resample: str = 'd'):
        """
        扫描五大热点板块，识别龙头（增强版）
        """

        global MAX_DAILY_ADDITIONS
        if not self.scan_hot_concepts_status:
            return
        
        try:
            if df is None:
                if hasattr(self, 'master') and self.master:
                    df = getattr(self.master, 'df_all', None)
            
            if df is None or df.empty or not concept_top5:
                return

            # 此时 df 已确定为 pd.DataFrame
            target_df: pd.DataFrame = df

            # Extract concept names
            top_concepts = set()
            for item in concept_top5:
                if isinstance(item, (list, tuple)):
                    top_concepts.add(str(item[0]))
                else:
                    top_concepts.add(str(item))
            
            if not top_concepts:
                return

            # ------------------------------------------------------------------
            # 策略优化：基于统计的热点龙头筛选
            # 每日限量 5 只，避免监控列表爆炸
            # ------------------------------------------------------------------
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            # 检查今日已添加的热点股数量 (限制在当前周期下)
            added_today_count = sum(1 for k, d in self._monitored_stocks.items() 
                                    if d.get('added_date', '') == today_str and d.get('rule_type_tag') == 'hot_concept' and d.get('resample', 'd') == resample)
            # logger.debug(f'added_today_count: {type(added_today_count)} MAX_DAILY_ADDITIONS: {type(MAX_DAILY_ADDITIONS)}')
            if added_today_count >= MAX_DAILY_ADDITIONS:
                # logger.info("Daily hot concept limit reached.")
                return

            if 'percent' not in target_df.columns:
                return

            # 先进行基础过滤，找出"像样"的股票
            cond_trend = (
                (target_df['close'] > target_df['high4']) &
                (target_df['close'] > target_df['ma5d']) & 
                (target_df['close'] > target_df['hmax']) 
            )
            # cond_strength 变量未直接用于过滤，若需要则应加入 strong_df 过滤条件中
            _ = (target_df['red'] > 5) | (target_df['top10'] > 0)
            cond_volume = target_df['volume'] > 1.2
            cond_percent =  ((target_df['close'] > target_df['lastp1d']) | (target_df['close'] > target_df['lastp2d']))
            cond_win = target_df['win'] > 0
            
            strong_df = target_df[cond_trend & cond_volume & cond_percent & cond_win].copy()
            
            if strong_df.empty:
                return
            logger.info(f'strong_df: {strong_df.shape}')
            # 计算候选股综合评分
            candidates = []
            
            for code, row in strong_df.iterrows():
                # Avoid re-adding
                if code in self._monitored_stocks:
                    continue

                raw_cats = str(row.get('category', ''))
                if not raw_cats: 
                    continue
                
                stock_cats = set(raw_cats.split(';'))
                # stock_ma5d, stock_close 等变量被识别为未使用，若仅用于调试打印可移除或改用 _
                _ = row.get('ma5d')
                _ = row.get('close')
                _ = row.get('Hma20d')
                _ = row.get('Hma60d')

                # logger.debug(f"code: {code} name: {row.get('name')} percent: {row.get('percent')}")
                matched_concepts = stock_cats.intersection(top_concepts)
                if matched_concepts:
                    concept_name: str = list(matched_concepts)[0]
                    stock_name: str = str(row.get('name', code))
                    
                    # --- 定量评分系统 ---
                    score = 0.0
                    
                    # 1. 涨幅贡献 (0 - 0.3)
                    pct = float(row.get('percent', 0.0)) # type: ignore
                    score += min(pct / 10, 0.3) if pct > 3 else min(pct / 10, 0.3) * 0.5
                    
                    # 2. 量能贡献 (0 - 0.2)
                    vol = float(row.get('volume', 0.0)) # type: ignore
                    if 1.2 <= vol <= 2.5:
                        score += 0.2
                    elif vol > 2.5:
                        score += 0.1 # 天量减分
                    elif vol < 0.8:
                        score -= 0.1 # 地量减分
                    
                    # 3. 趋势强度 (0 - 0.3)
                    win_count = int(row.get('win', 0)) # type: ignore
                    if win_count >= 3:
                        score += 0.2
                    
                    # 4. 价格稳定性 (0 - 0.2)
                    hmax = float(row.get('hmax', 0.0)) # type: ignore
                    curr = float(row.get('close', 0.0)) # type: ignore
                    
                    hma5d = float(row.get('ma5d', 0.0)) # type: ignore
                    hma10d = float(row.get('ma10d', 0.0)) # type: ignore
                    trendS = float(row.get('win', 0.0)) # type: ignore
                    if hmax > 0 and curr > hmax:
                        score += 0.2
                    
                    # 4. 技术位贡献 (0 - 0.2)
                    hmax = float(row.get('hmax', float('inf'))) # type: ignore
                    if float(row.get('close', 0)) > hmax: # type: ignore
                        score += 0.2 # 突破新高
                    # select_code ={
                    #     'code': code,
                    #     'name': row.get('name', code),
                    #     'score': score,
                    #     'concept': concept_name,
                    #     'pct': pct
                    # }
                    # logger.debug(f"candidates append:{select_code}")
                    logger.info(f"code: {code} name: {stock_name} percent: {row.get('percent')} 背离ma5d: {hma5d} 背离ma10d: {hma10d} 评估: {score} 综合趋势分: {trendS} per2d: {row.get('per2d')} per3d: {row.get('per3d')}")
                    # 添加到候选列表
                    candidates.append({
                        'code': code,
                        'name': row.get('name', code),
                        'score': round(score,1),
                        'concept': concept_name,
                        'pct': pct
                    })
            
            # 按分数从高到低排序
            candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # 选取前 N 名进行添加
            slots_remaining = MAX_DAILY_ADDITIONS - added_today_count
            
            for cand in candidates[:slots_remaining]:
                # 只有评分 > 0.4 才配得上进入监控
                if cand['score'] >= 0.4:
                    self.add_monitor(
                        code=str(cand['code']),
                        name=cand['name'],
                        rule_type='hot_concept',
                        value=cand['score'],
                        tags=f"Hot:{cand['concept']}|Sc:{cand['score']:.2f}",
                        resample=resample
                    )

                    logger.info(f"🔥 Found Hot Leader (Score={cand['score']:.2f}): {cand['name']}({cand['code']}) in {cand['concept']}")

            # --- 板块整体拉升跟单 (Sector Rally Following) ---
            sector_status = getattr(self, '_last_sector_status', {})
            rally_signals = sector_status.get('rally_signals', [])
            
            for sector, avg_pct, leader_code in rally_signals:
                if leader_code not in self._monitored_stocks:
                    # 板块整体拉升,自动跟踪龙头
                    leader_row = df.loc[leader_code] if leader_code in df.index else None
                    if leader_row is not None:
                         # 检查是否已有高分候选人是同一只股票
                        is_duplicate = False
                        for cand in candidates:
                             if str(cand['code']) == str(leader_code):
                                 is_duplicate = True
                                 break
                        
                        if not is_duplicate:
                            self.add_monitor(
                                code=str(leader_code),
                                name=leader_row.get('name', leader_code),
                                rule_type='sector_rally',
                                value=avg_pct,
                                tags=f"Rally:{sector}|Avg:{avg_pct:.1%}"
                            )
                            logger.info(f"🚀 板块拉升跟单: {sector} 龙头 {leader_code} (AvgPct: {avg_pct:.1%})")




        except Exception as e:
            logger.error(f"Error in scan_hot_concepts: {e}", exc_info=True)
            pass

    def _check_strategies(self, df, resample='d'):
        try:
            # --- [新增] 全局交易日判断：非交易日不执行策略逻辑 ---
            # if not cct.get_trade_date_status():
            #     return

            # 从数据库同步实时持仓信息 (按 代码+周期 映射以支持多周期持仓隔离)
            trades_info = self.trading_logger.get_trades()
            open_trades = {(t['code'], t.get('resample', 'd')): t for t in trades_info if t['status'] == 'OPEN'}

            # --- [新增] 确保 DataFrame 包含监理与策略状态列 (供前端 Visualizer 使用) ---
            for col in ['market_win_rate', 'loss_streak', 'vwap_bias', 'last_action', 'last_reason', 'shadow_info']:
                if col not in df.columns:
                    # 数值型默认为 0，字符串型默认为空
                    if col in ['last_action', 'last_reason', 'shadow_info']:
                        df[col] = ""
                    else:
                        df[col] = 0.0
            
            # --- [优化] 同步 55188 全量数据：移出循环，每批次仅执行一次 ---
            if self.realtime_service:
                try:
                    ext_status = self.realtime_service.get_55188_data() # 不传 code 获取全量字典
                    if isinstance(ext_status, dict):
                        df_ext = ext_status.get('df')
                        if df_ext is not None and not df_ext.empty:
                            self.ext_data_55188 = df_ext
                            self.last_ext_update_ts = ext_status.get('last_update', time.time())
                except Exception as e:
                    logger.debug(f"Sync full 55188 data failed: {e}")

            # 过滤对应周期的监控项
            monitored_keys = self._monitored_stocks.keys()
            filtered_keys = [k for k in monitored_keys if self._monitored_stocks[k].get('resample', 'd') == resample]
            
            valid_keys = [k for k in filtered_keys if k.split('_')[0] in df.index]
            now = time.time()  # 使用时间戳，与 last_alert 等保持类型一致
            for key in valid_keys:
                data = self._monitored_stocks[key]
                code = data.get('code', key.split('_')[0])
                last_alert = data.get('last_alert', 0)
                # logger.debug(f"{code} data:{data}")

                # ---------- 冷却判断 ----------
                if now - last_alert < self._alert_cooldown:
                    logger.debug(f"{code} 冷却中，跳过检查")
                    continue

                row = df.loc[code]

                # ---------- 安全获取行情数据 ----------
                try:
                    current_price = float(row.get('trade', 0.0)) # type: ignore
                    current_nclose = float(row.get('nclose', 0.0)) # type: ignore
                    current_change = float(row.get('percent', 0.0)) # type: ignore
                    volume_change = float(row.get('volume', 0.0)) # type: ignore
                    ratio_change = float(row.get('ratio', 0.0)) # type: ignore
                    # ma5d_change, ma10d_change 仅获取确保存在，但不直接使用
                    _ = float(row.get('ma5d', 0.0)) # type: ignore
                    _ = float(row.get('ma10d', 0.0)) # type: ignore
                    current_high = float(row.get('high', 0.0)) # type: ignore
                except (ValueError, TypeError) as e:
                    logger.warning(f"{code} 行情数据异常: {e}")
                    continue

                # ---------- 历史 snapshot 与 持仓同步 ----------
                snap = data.get('snapshot', {})
                trade_key = (code, resample)
                if trade_key in open_trades:
                    trade = open_trades[trade_key]
                    snap['cost_price'] = trade.get('buy_price', 0)
                    snap['buy_date'] = trade.get('buy_date', '')
                    snap['buy_reason'] = trade.get('buy_reason', '')
                    # 追踪买入后最高价 (用于移动止盈)
                    if current_price > float(snap.get('highest_since_buy', 0.0)): # type: ignore
                        snap['highest_since_buy'] = current_price
                
                # 注入加速连阳与五日线强度数据
                snap['win'] = row.get('win', snap.get('win', 0)) #加速连阳
                snap['sum_perc'] = row.get('sum_perc', snap.get('sum_perc', 0)) #加速连阳涨幅
                snap['red'] = row.get('red', snap.get('red', 0)) #五日线上数据
                snap['gren'] = row.get('gren', snap.get('gren', 0)) #弱势绿柱数据

                # --- 实时情绪与形态注入 (Realtime Signal Injection) ---
                if self.realtime_service:
                    # 55188 全量数据已在循环外同步 (self.ext_data_55188)
                    
                    try:
                        # 1. 注入实时情绪 (0-100)
                        rt_emotion = self.realtime_service.get_emotion_score(code)
                        snap['rt_emotion'] = rt_emotion
                        
                        # 2. 注入 V 型反转信号 (True/False)
                        v_shape = self.realtime_service.get_v_shape_signal(code)
                        snap['v_shape_signal'] = v_shape
                        if v_shape:
                             logger.debug(f"⚡ {code} 触发 V 型反转信号")
                        
                        # 3. 注入 55188 外部数据 (人气、主力、题材)
                        ext_55188 = self.realtime_service.get_55188_data(code)
                        if ext_55188:
                            snap['hot_rank'] = ext_55188.get('hot_rank', 999)
                            snap['zhuli_rank'] = ext_55188.get('zhuli_rank', 999)
                            snap['net_ratio_ext'] = ext_55188.get('net_ratio', 0)
                            snap['hot_tag'] = ext_55188.get('hot_tag', "")
                            # 新增题材与板块持续性
                            snap['theme_name'] = ext_55188.get('theme_name', "")
                            snap['theme_logic'] = ext_55188.get('theme_logic', "")
                            snap['sector_score'] = ext_55188.get('sector_score', 0.0)
                        else:
                            snap['hot_rank'] = 999
                            snap['zhuli_rank'] = 999
                            snap['net_ratio_ext'] = 0
                            snap['sector_score'] = 0.0
                            
                    except Exception as e:
                        logger.error(f"Realtime Service Injection Error: {e}")

                # --- ⭐ 日内形态检测 ---
                if hasattr(self, 'pattern_detector'):
                    try:
                        prev_close = float(row.get('lastp1d', 0))
                        self.pattern_detector.update(
                            code=code,
                            name=data.get('name', ''),
                            tick_df=None,   # 暂无分时数据，使用 day_row 即可
                            day_row=row,
                            prev_close=prev_close
                        )
                    except Exception as e:
                        logger.debug(f"Pattern detect error for {code}: {e}")

                # --- 注入板块与系统风险状态 ---
                # 从 _last_sector_status 中获取
                sector_status = getattr(self, '_last_sector_status', {})
                pullback_alerts = sector_status.get('pullback_alerts', [])
                snap['systemic_risk'] = sector_status.get('risk_level', 0)
                
                # 获取该股票所属板块的风险
                stock_sector = snap.get('theme_name', '')
                if not stock_sector and 'category' in row:
                     cats = str(row['category']).split(';')
                     if cats: stock_sector = cats[0]

                for p_sector, p_code, p_drop in pullback_alerts:
                    # check if self is leader
                    if str(p_code) == str(code):
                        snap['sector_leader_pullback'] = p_drop
                    # check if sector leader is pulling back (follow-on risk)
                    if stock_sector and p_sector == stock_sector:
                        snap['sector_leader_pullback'] = p_drop
                
                # --- 注入日线中轴趋势数据 (Daily Midline Trend) ---
                # Midline = (High + Low) / 2
                # 计算过去 2 天的中轴线趋势
                try:
                    # 获取昨日和前日数据 (需要有 last_high, last_low 等数据列，或者从 row 中获取如果存在)
                    # 假设 df 中有 last_high, last_low, last2_high, last2_low
                    # 如果没有，尝试用 nclose 近似或跳过
                    
                    # 昨中轴
                    last_h = float(row.get('last_high', 0))
                    last_l = float(row.get('last_low', 0))
                    if last_h > 0 and last_l > 0:
                        snap['yesterday_midline'] = (last_h + last_l) / 2
                    else:
                        snap['yesterday_midline'] = float(row.get('last_close', 0)) # fallback

                    # 前中轴
                    last2_h = float(row.get('last2_high', 0))
                    last2_l = float(row.get('last2_low', 0))
                    if last2_h > 0 and last2_l > 0:
                        snap['day_before_midline'] = (last2_h + last2_l) / 2
                    else:
                         snap['day_before_midline'] = snap['yesterday_midline'] # fallback

                    # 今日实施中轴 (动态)
                    if current_high > 0:
                         # 注意: low 只有在收盘确定，盘中 low 可能不准，这里用 当前价作为临时低点参考? 
                         # 不，盘中 low 也是实时更新的
                         current_low = float(row.get('low', 0))
                         if current_low > 0:
                             snap['today_midline'] = (current_high + current_low) / 2
                    
                    # 简单的趋势判断标记
                    if snap['yesterday_midline'] < snap['day_before_midline']:
                        snap['midline_falling'] = True
                    else:
                        snap['midline_falling'] = False
                        
                    if snap['yesterday_midline'] > snap['day_before_midline']:
                        snap['midline_rising'] = True
                    else:
                         snap['midline_rising'] = False

                except Exception as e:
                    logger.debug(f"Midline calc error for {code}: {e}")


                    # 默认值
                    snap['rt_emotion'] = 50
                    snap['v_shape_signal'] = False
                    snap['hot_rank'] = 999
                    snap['zhuli_rank'] = 999
                    snap['net_ratio_ext'] = 0

                # --- 策略进化：注入反馈记忆 (Feedback Injection) ---
                # 1. 记仇机制：查询该股最近连续亏损次数
                if 'loss_streak' not in snap: # 避免每秒查库，简单缓存(实际应有过期机制，这里简化)
                     # 只有当 snapshot 里没有或者是新的一天时才查(略复杂，这里暂且每次循环查，因为 execute 轻量)
                     # 为了性能考虑，其实应该每分钟只更新一次。这里暂且假设 sqlite 够快。
                     # Better: 在外层定时更新 self.blacklist_cache
                     pass
                
                # 实时查询 (耗时较小，Sqlite PK查询极快)
                snap['loss_streak'] = self.trading_logger.get_consecutive_losses(code, days=15, resample=resample)
                
                # 2. 环境感知：查询最近市场胜率 (分周期缓存)
                if not hasattr(self, '_sentiments'):
                    self._sentiments = {}
                
                sent_data = self._sentiments.get(resample, {'value': 0.5, 'ts': 0})
                if now - sent_data['ts'] > 300:
                    val = self.trading_logger.get_market_sentiment(days=3, resample=resample)
                    self._sentiments[resample] = {'value': val, 'ts': now}
                    sent_data = self._sentiments[resample]
                    
                snap['market_win_rate'] = sent_data['value']


                # 【新增】日内实时追踪字段（用于冲高回落检测和盈利最大化）
                open_price = float(row.get('open', 0))
                # 追踪日内最高价
                if current_high > snap.get('highest_today', 0):
                    snap['highest_today'] = current_high
                # 追踪日内最大泵高幅度 (相对于开盘价)
                if open_price > 0:
                    pump_height = (snap.get('highest_today', current_high) - open_price) / open_price
                    snap['pump_height'] = max(snap.get('pump_height', 0), pump_height)
                # 计算从日高回撤深度
                highest_today = snap.get('highest_today', current_high)
                if highest_today > 0:
                    snap['pullback_depth'] = (highest_today - current_price) / highest_today

                last_close = snap.get('last_close', 0)
                last_percent = snap.get('percent', None)

                # ---------- 初始化计数器 ----------
                data.setdefault('below_nclose_count', 0)
                data.setdefault('below_nclose_start', 0)
                data.setdefault('below_last_close_count', 0)
                data.setdefault('below_last_close_start', 0)

                # ---------- T+1 状态感知 ----------
                is_t1_restricted = False
                if snap.get('buy_date'):
                    today_str = datetime.now().strftime('%Y-%m-%d')
                    if snap['buy_date'].startswith(today_str):
                        is_t1_restricted = True

                messages = []

                # ---------- 今日均价风控 ----------
                max_normal_pullback = (last_percent / 5 / 100 if last_percent else 0.01)
                if not is_t1_restricted and current_price > 0 and current_nclose > 0:
                    deviation = (current_nclose - current_price) / current_nclose
                    if deviation > max_normal_pullback + 0.0005:
                        if data['below_nclose_start'] == 0:
                            data['below_nclose_start'] = now
                        if now - data['below_nclose_start'] >= 300:
                            data['below_nclose_count'] += 1
                    else:
                        data['below_nclose_start'] = 0
                        data['below_nclose_count'] = 0
                    if data['below_nclose_count'] >= 3:
                        messages.append(("RISK", f"卖出 {data['name']} 价格连续低于今日均价 {current_nclose} ({current_price})"))

                # ---------- 昨日收盘风控 ----------
                if not is_t1_restricted and last_close > 0:
                    deviation_last = (last_close - current_price) / last_close
                    if deviation_last > max_normal_pullback + 0.0005:
                        if data['below_last_close_start'] == 0:
                            data['below_last_close_start'] = now
                        if now - data['below_last_close_start'] >= 300:
                            data['below_last_close_count'] += 1
                    else:
                        data['below_last_close_start'] = 0
                        data['below_last_close_count'] = 0
                    if data['below_last_close_count'] >= 2:
                        messages.append(("RISK", f"减仓 {data['name']} 价格连续低于昨日收盘 {last_close} ({current_price})"))

                # ---------- 普通规则 ----------
                for rule in data.get('rules', []):
                    rtype, rval = rule['type'], rule['value']
                    if (rtype == 'price_up' and current_price >= rval) or (rtype == 'price_down' and current_price <= rval) or (rtype == 'change_up' and current_change >= rval):
                        msg = f"{data['name']} {('价格突破' if rtype=='price_up' else '价格跌破' if rtype=='price_down' else '涨幅达到')} {current_price} 涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                        messages.append(("RULE", msg))

                # --- 3. 实时情绪感知 & K线形态 (Realtime Analysis) ---
                if self.realtime_service:
                    try:
                        # --- 3.1 读取实时情绪 ---
                        rt_emotion = self.realtime_service.get_emotion_score(code)
                        snap['rt_emotion'] = snap.get('rt_emotion', 0) + rt_emotion

                        # --- 3.2 V-Shape K线形态 ---
                        klines = self.realtime_service.get_minute_klines(code, n=30)
                        if len(klines) >= 15:
                            lows = [k['low'] for k in klines]
                            closes = [k['close'] for k in klines]
                            p_curr = closes[-1]
                            p_low = min(lows)
                            p_start = closes[0]

                            if p_start > 0 and p_low > 0:
                                drop = (p_low - p_start) / p_start
                                rebound = (p_curr - p_low) / p_low

                                # --- 防重复触发 ---
                                if 'v_shape_triggered' not in snap:
                                    snap['v_shape_triggered'] = False

                                if drop < -0.02 and rebound > 0.015 and not snap['v_shape_triggered']:
                                    snap['v_shape_signal'] = True
                                    snap['rt_emotion'] += 15  # 加分
                                    snap['v_shape_triggered'] = True
                                    logger.info(f"V-Shape Detected {code}: Drop {drop:.1%} Rebound {rebound:.1%}")

                    except Exception as e:
                        logger.debug(f"Realtime service fetch error: {e}")

                # ---------- 决策引擎 ----------
                decision = self.decision_engine.evaluate(row, snap)

                # --- ⭐ 影子策略并行运行 (Dual Strategy Optimization) ---
                shadow_decision = self.shadow_engine.evaluate(row, snap)
                
                # --- ⭐ 盈利监理重磅拦截 (Supervision Veto) ---
                is_vetoed, veto_reason = self.supervisor.veto(code, decision, row, snap)

                # 记录影子差异 (Inject into debug info for later analysis)
                if shadow_decision["action"] in ("买入", "加仓", "BUY", "ADD"):
                    # 如果影子有买入意向而主策略没有（或者主策略被拦截了）
                    decision["debug"]["shadow_action"] = shadow_decision["action"]
                    decision["debug"]["shadow_reason"] = shadow_decision["reason"]
                    if decision["action"] == "HOLD" or is_vetoed:
                        logger.info(f"🧪 [影子策略] {code} {snap.get('name')} 发现比对机会: {shadow_decision['reason']}")

                if is_vetoed:
                    # 如果被监理拦截，修改 action 为 VETO 并记录原因
                    decision["original_action"] = decision["action"] # 保留原意图用于分析
                    decision["action"] = "VETO" 
                    decision["reason"] = f"🛡️ [监理拦截] {veto_reason} | 原理由: {decision['reason']}"
                    logger.warning(f"🛡️ {code} {snap.get('name')} 信号被监理拦截: {veto_reason}")

                # --- 3.3 冷却机制：避免短时重复触发 ---
                cooldown_minutes = 5
                now_ts = datetime.now()
                if 'last_trigger_time' not in snap:
                    snap['last_trigger_time'] = now_ts - timedelta(minutes=cooldown_minutes)
                    # logger.info(f'timedelta(minutes=cooldown_minutes): {timedelta(minutes=cooldown_minutes)}')
                time_since_last = (now_ts - snap['last_trigger_time']).total_seconds() / 60
                if time_since_last >= cooldown_minutes:
                    # [防重复开仓] 核心防御逻辑
                    if decision["action"] == "买入" and code in open_trades:
                        logger.info(f"🛡️ 拒绝重复开仓 {code} {data['name']}: 当前已持仓")
                        # 可以选择不触发，或者转为持仓
                        # decision["action"] = "持仓" 
                        # 但为了保持逻辑纯洁，我们直接在这里不进入下面的分支，或者在这里做标记
                        
                        # 为了不破坏后续可能的逻辑（比如记录高分），我们简单地把它打回"持仓"或跳过 action 处理
                        # 最安全的做法是：直接 continue，但后面还有日志记录...
                        # 让我们修改 decision action 为持仓，这样就不会触发下面的交易逻辑
                        decision["action"] = "持仓"
                        decision["reason"] += " [已持仓防重复]"

                    if decision["action"] in ("买入", "ADD", "加仓"):
                        # 记录加仓分数和触发历史
                        snap["last_buy_score"] = decision["debug"].get("实时买入分", 0)
                        snap["buy_triggered_today"] = True
                        snap['last_trigger_time'] = now_ts
                        # 特殊冷却：加仓后增加冷却时间，防止短时连续加仓
                        if decision["action"] in ("ADD", "加仓"):
                             snap['last_trigger_time'] = now_ts + timedelta(minutes=10) 
                    elif decision["action"] == "卖出":
                        snap["sell_triggered_today"] = True
                        snap["sell_reason"] = decision["reason"]
                        snap['last_trigger_time'] = now_ts

                # --- 3.4 记录最大分数 ---
                snap["max_score_today"] = max(snap.get("max_score_today", 0), decision["debug"].get("实时买入分", 0))

                # --- 3.5 构建 row_data（顺序优化 + 日线周期增强） ---
                row_data = {
                    # --- 日线周期指标 ---
                    'ma5d': float(row.get('ma5d', 0)),
                    'ma10d': float(row.get('ma10d', 0)),
                    'ma20d': float(row.get('ma20d', 0)),
                    'ma60d': float(row.get('ma60d', 0)),
                    'low10': snap.get('low10', 0),
                    'highest_today': snap.get('highest_today', row.get('high', 0)),
                    'lower': snap.get('lower', 0),
                    'pump_height': snap.get('pump_height', 0),
                    'pump_height': snap.get('pump_height', 0),
                    'pullback_depth': snap.get('pullback_depth', 0),

                    # --- 日K中轴线趋势数据 ---
                    'lasthigh': float(row.get('lasthigh', 0)),
                    'lastlow': float(row.get('lastlow', 0)),
                    'midline_2d': float(row.get('midline_2d', 0)), # 对应 day_before_midline

                    # --- 分时指标 ---
                    'ratio': float(row.get('ratio', 0)),
                    'volume': float(row.get('volume', 0)),
                    'turnover': float(row.get('turnover', 0)),
                    'nclose': row.get('nclose', 0),
                    'open': float(row.get('open', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'percent': row.get('percent', 0),

                    # --- 额外状态 ---
                    'win': snap.get('win', 0),
                    'red': snap.get('red', 0),
                    'gren': snap.get('gren', 0),
                    'sum_perc': snap.get('sum_perc', 0),
                    # --- 关键新增: 情绪基准与实时分 ---
                    'emotion_baseline': float(row.get('emotion_baseline', 50.0)),
                    'rt_emotion': float(row.get('rt_emotion', 50.0)),
                    'rt_emotion': float(row.get('rt_emotion', 50.0)),
                    'emotion_status': str(row.get('emotion_status', '')),
                }

                # --- 补充中轴线数据到 snapshot 供下次使用 (或本次 checking) ---
                # 注意：_check_strategies 里的 snap 是引用 self._monitored_stocks[code]['snapshot']
                # 所以这里修改 snap 会保留。
                lasthigh = float(row.get('lasthigh', 0))
                lastlow = float(row.get('lastlow', 0))
                if lasthigh > 0 and lastlow > 0:
                    snap['yesterday_midline'] = (lasthigh + lastlow) / 2
                snap['day_before_midline'] = float(row.get('midline_2d', 0))
                
                # 计算趋势方向
                current_mid = (float(row.get('high', 0)) + float(row.get('low', 0))) / 2
                snap['midline_rising'] = current_mid > snap.get('yesterday_midline', 0) > snap.get('day_before_midline', -1) if snap.get('yesterday_midline', 0) > 0 else False
                snap['midline_falling'] = current_mid < snap.get('yesterday_midline', 9999) < snap.get('day_before_midline', 9999) if snap.get('yesterday_midline', 0) > 0 else False

                # --- 3.6 记录信号日志 ---
                self.trading_logger.log_signal(code, data['name'], current_price, decision, row_data=row_data)

                # --- ⭐ 将决策与监理感知回写至 snap (供 UI 同步使用) ---
                snap['last_action'] = decision.get('action', 'HOLD')
                snap['last_reason'] = decision.get('reason', '')
                
                # 修正：market_win_rate 和 loss_streak 已在上文注入 snap，此处无需重复赋值且避免 NameError
                vwap = current_nclose
                if vwap > 0:
                    snap['vwap_bias'] = (current_price - vwap) / vwap
                else:
                    snap['vwap_bias'] = 0.0
                
                # 影子策略信息
                if shadow_decision["action"] in ("买入", "加仓", "BUY", "ADD"):
                    snap['shadow_info'] = f"🧪 {shadow_decision['action']}: {shadow_decision['reason']}"
                else:
                    snap['shadow_info'] = ""

                # --- [新增] 将 SNAP 中的关键策略状态同步回 DataFrame ---
                # 这是因为 Monitor 和 Visualizer 通常从 self.df_all (即这里的 df) 读取数据
                try:
                    df.at[code, 'market_win_rate'] = snap.get('market_win_rate', 0.0)
                    df.at[code, 'loss_streak'] = snap.get('loss_streak', 0)
                    df.at[code, 'vwap_bias'] = snap.get('vwap_bias', 0.0)
                    df.at[code, 'last_action'] = snap.get('last_action', '')
                    df.at[code, 'last_reason'] = snap.get('last_reason', '')
                    df.at[code, 'shadow_info'] = snap.get('shadow_info', '')
                except Exception as e:
                    pass

                # # --- 3. 实时情绪感知 & K线形态 (Realtime Analysis) ---
                # if self.realtime_service:
                #     try:
                #         # Emotion Score
                #         rt_emotion = self.realtime_service.get_emotion_score(code)
                #         snap['rt_emotion'] = rt_emotion

                #         # K-Line Pattern (V-Shape Reversal)
                #         klines = self.realtime_service.get_minute_klines(code, n=30)
                #         if len(klines) >= 15:
                #             lows = [k['low'] for k in klines]
                #             closes = [k['close'] for k in klines]
                #             p_curr = closes[-1]
                #             p_low = min(lows)
                            
                #             # Logic: Deep drop from start of window (>2%) + Significant Rebound (>1.5%)
                #             p_start = closes[0]
                #             if p_start > 0 and p_low > 0:
                #                 drop = (p_low - p_start) / p_start
                #                 rebound = (p_curr - p_low) / p_low
                                
                #                 if drop < -0.02 and rebound > 0.015:
                #                     snap['v_shape_signal'] = True
                #                     snap['rt_emotion'] += 15 # Bonus for reversal
                #                     logger.info(f"V-Shape Detected {code}: Drop {drop:.1%} Rebound {rebound:.1%}")

                #     except Exception as e:
                #         logger.debug(f"Realtime service fetch error: {e}")

                # # ---------- 决策引擎 ----------
                # decision = self.decision_engine.evaluate(row, snap)
                # logger.debug(f"Strategy: {code} ({data['name']}) Engine Result: {decision['action']} Score: {decision['debug'].get('实时买入分', 0)} Reason: {decision['reason']}")
                
                # # --- 状态记忆持久化 (New) ---
                # if decision["action"] == "买入":
                #     snap["last_buy_score"] = decision["debug"].get("实时买入分", 0)
                #     snap["buy_triggered_today"] = True
                # elif decision["action"] == "卖出":
                #     snap["sell_triggered_today"] = True
                
                # # 记录最高分作为今日目标追踪
                # snap["max_score_today"] = max(snap.get("max_score_today", 0), decision["debug"].get("实时买入分", 0))

                # # 记录信号历史 (增强版：传递完整行情数据以便后续分析)
                # row_data = {
                #     'ma5d': float(row.get('ma5d', 0)),
                #     'ma10d': float(row.get('ma10d', 0)),
                #     'ma20d': float(row.get('ma20d', 0)),
                #     'ma60d': float(row.get('ma60d', 0)),
                #     'ratio': float(row.get('ratio', 0)),
                #     'volume': float(row.get('volume', 0)),
                #     'nclose': current_nclose,
                #     'high': current_high,
                #     'low': float(row.get('low', 0)),
                #     'open': float(row.get('open', 0)),
                #     'percent': current_change,
                #     'turnover': float(row.get('turnover', 0)),
                #     'win': snap.get('win', 0),
                #     'red': snap.get('red', 0),
                #     'gren': snap.get('gren', 0),
                #     'sum_perc': snap.get('sum_perc', 0),
                #     'low10': snap.get('low10', 0),
                #     'lower': snap.get('lower', 0),
                #     'highest_today': snap.get('highest_today', current_high),
                #     'pump_height': snap.get('pump_height', 0),
                #     'pullback_depth': snap.get('pullback_depth', 0),
                # }
                # self.trading_logger.log_signal(code, data['name'], current_price, decision, row_data=row_data)

                if decision["action"] != "持仓":
                    pos_val = decision.get("position", 0)
                    # 防止 NaN 转换为整数失败
                    if pd.isna(pos_val):
                        pos_val = 0
                    messages.append(("POSITION", f'{data["name"]} {decision["action"]} 仓位{int(pos_val*100)}% {decision["reason"]}'))

                # ---------- 风控调整仓位 ----------
                action, ratio = self._risk_engine.adjust_position(data, decision["action"], decision["position"])
                if action and (action != "持仓"):
                    # 防止 NaN 转换失败
                    if pd.isna(ratio):
                        ratio = 0
                    messages.append(("POSITION", f'{data["name"]} {action} 当前价 {current_price} 建议仓位 {ratio*100:.0f}%'))

                # ---------- 调试输出 ----------
                # logger.debug(f"{code} DEBUG: price={current_price} nclose={current_nclose} last_close={last_close} below_nclose_count={data['below_nclose_count']} below_last_close_count={data['below_last_close_count']} max_normal_pullback={max_normal_pullback:.2f}")

                if messages:
                    # ---------- 去重 & 合并 ----------
                    priority_order = ["RISK", "RULE", "POSITION"]
                    priority_rank = {k:i for i,k in enumerate(priority_order)}
                    unique_msgs = {}
                    last_duplicate = {}
                    for mtype, msg in messages:
                        if msg not in unique_msgs:
                            unique_msgs[msg] = mtype
                        else:
                            last_duplicate[msg] = mtype  # 保留重复在最后
                    t1_prefix = "[T+1限制] " if is_t1_restricted else ""
                    combined_msgs = t1_prefix + "\n".join(list(unique_msgs.keys()) + list(last_duplicate.keys()))

                    log_msg = combined_msgs.replace('\n', ' | ')
                    logger.debug(f"Strategy ALERT: {code} ({data['name']}) Triggered. Action: {action} Msg: {log_msg}")
                    self._trigger_alert(code, data['name'], combined_msgs, action=action, price=current_price, resample=resample)
                    data['last_alert'] = now

                    data['below_nclose_count'] = 0
                    data['below_nclose_start'] = 0
                    data['below_last_close_count'] = 0
                    data['below_last_close_start'] = 0
                else:
                    logger.debug(f"{code} data: {messages}")
        except Exception as e:
            logger.error(f"Strategy Check Error: {e}")

    def _check_strategies_simple(self, df):
        try:
            now = time.time()
            valid_codes = [c for c in self._monitored_stocks.keys() if c in df.index]

            for code in valid_codes:
                data = self._monitored_stocks[code]
                last_alert = data.get('last_alert', 0)

                # ---------- 冷却判断 ----------
                if now - last_alert < self._alert_cooldown:
                    logger.debug(f"{code} 冷却中，跳过检查")
                    continue

                row = df.loc[code]

                # ---------- 安全获取行情数据 ----------
                try:
                    current_price = float(row.get('trade', 0))
                    current_nclose = float(row.get('nclose', 0))
                    current_change = float(row.get('percent', 0))
                    volume_change = float(row.get('volume', 0))
                    ratio_change = float(row.get('ratio', 0))
                    ma5d_change = float(row.get('ma5d', 0))
                    ma10d_change = float(row.get('ma10d', 0))   
                    current_high= float(row.get('high', 0))

                except (ValueError, TypeError) as e:
                    logger.warning(f"{code} 行情数据异常: {e}")
                    continue

                # ---------- 历史 snapshot ----------
                snap = data.get('snapshot', {})
                last_close = snap.get('last_close', 0)
                last_percent = snap.get('percent', None)
                last_nclose = snap.get('nclose', 0)

                # ---------- 初始化计数器 ----------
                data.setdefault('below_nclose_count', 0)
                data.setdefault('below_nclose_start', 0)
                data.setdefault('below_last_close_count', 0)
                data.setdefault('below_last_close_start', 0)

                # ---------- 消息收集 ----------
                messages = []

                # ---------- 今日均价风控 ----------
                max_normal_pullback = (last_percent / 5 / 100 if last_percent else 0.01)
                if current_price > 0 and current_nclose > 0:
                    deviation = (current_nclose - current_price) / current_nclose
                    if deviation > max_normal_pullback + 0.0005:
                        if data['below_nclose_start'] == 0:
                            data['below_nclose_start'] = now
                        if now - data['below_nclose_start'] >= 300:
                            data['below_nclose_count'] += 1
                    else:
                        data['below_nclose_start'] = 0
                        data['below_nclose_count'] = 0

                    if data['below_nclose_count'] >= 3:
                        msg = (
                            f"卖出 {data['name']} 价格连续低于今日均价 {current_nclose} 卖出 ({current_price}) "
                        )
                        messages.append(("RISK", msg))
                            # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"

                # ---------- 昨日收盘风控 ----------
                if last_close > 0:
                    deviation_last = (last_close - current_price) / last_close
                    if deviation_last > max_normal_pullback + 0.0005:
                        if data['below_last_close_start'] == 0:
                            data['below_last_close_start'] = now
                        if now - data['below_last_close_start'] >= 300:
                            data['below_last_close_count'] += 1
                    else:
                        data['below_last_close_start'] = 0
                        data['below_last_close_count'] = 0

                    if data['below_last_close_count'] >= 2:
                        msg = (
                            f"减仓 {data['name']} 价格连续低于昨日收盘 {last_close} ({current_price}) "
                        )
                            # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                        messages.append(("RISK", msg))

                # ---------- 普通规则 ----------
                for rule in data.get('rules', []):
                    rtype = rule['type']
                    rval = rule['value']
                    rule_triggered = False
                    msg = ""
                    msg = ""
                    if rtype == 'price_up' and current_price >= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 价格突破 {current_price} 涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    elif rtype == 'price_down' and current_price <= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 价格跌破 {current_price} 涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    elif rtype == 'change_up' and current_change >= rval:
                        rule_triggered = True
                        msg = f"{data['name']} 涨幅达到 {current_change:.1f}% 价格 {current_price} 量能 {volume_change} 换手 {ratio_change}"

                    if rule_triggered:
                        messages.append(("RULE", msg))

                # ---------- 动态仓位建议 ----------
                action, ratio = self._calculate_position(
                    data, current_price, current_nclose, last_close, last_percent, last_nclose
                )
                # if action != "持仓":
                if action:
                    msg = (
                        f"{data['name']} {action} 当前价 {current_price} "
                        f"建议仓位 {ratio*100:.0f}% "
                    )
                        # f"今日均价 {current_nclose} 昨日收盘 {last_close} "
                        # f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
                    messages.append(("POSITION", msg))

                # ---------- 调试信息 ----------
                # logger.debug(
                #     f"{code} DEBUG: price={current_price} nclose={current_nclose} "
                #     f"last_close={last_close} below_nclose_count={data['below_nclose_count']} "
                #     f"below_last_close_count={data['below_last_close_count']} "
                #     f"max_normal_pullback={max_normal_pullback:.2f}"
                # )

                if messages:
                    # ---------- 优先级定义 ----------
                    priority_order = ["RISK", "RULE", "POSITION"]
                    priority_rank = {k: i for i, k in enumerate(priority_order)}

                    # ---------- 去重（按文本） ----------
                    unique_msgs = {}
                    for mtype, msg in messages:
                        if msg not in unique_msgs:
                            unique_msgs[msg] = mtype
                        else:
                            # 同一 msg，保留更高优先级
                            if priority_rank[mtype] < priority_rank[unique_msgs[msg]]:
                                unique_msgs[msg] = mtype

                    # ---------- 按优先级排序 ----------
                    sorted_msgs = sorted(
                        unique_msgs.items(),
                        key=lambda x: priority_rank[x[1]]
                    )

                    # ---------- 合并文本 ----------
                    combined_msg = "\n".join([msg for msg, _ in sorted_msgs])

                    # ---------- 计算最终 action ----------
                    # if any(t == "RISK" for t in unique_msgs.values()):
                    #     final_action = "RISK"
                    # elif any(t == "RULE" for t in unique_msgs.values()):
                    #     final_action = "RULE"
                    # elif any(t == "POSITION" for t in unique_msgs.values()):
                    #     final_action = action  # 来自仓位模型
                    # else:
                    #     final_action = "HOLD"

                    # # ---------- 调试输出 ----------
                    # logger.debug(f"{code} 合并前 messages={messages}")
                    # logger.debug(f"{code} 去重后 unique_msgs={unique_msgs}")
                    # # logger.info(f"{code} combined_msg:\n{combined_msg}")

                    # ---------- 单次触发 ----------
                    self._trigger_alert(
                        code,
                        data['name'],
                        combined_msg,
                        action=action,
                        price=current_price,
                        resample=data.get('resample', 'd')
                    )
                        # action=final_action

                    data['last_alert'] = now

                    # ---------- 重置计数器 ----------
                    data['below_nclose_count'] = 0
                    data['below_nclose_start'] = 0
                    data['below_last_close_count'] = 0
                    data['below_last_close_start'] = 0

        except Exception as e:
            logger.error(f"Strategy Check Error: {e}")

    def get_monitors(self):
        """获取所有监控数据"""
        return self._monitored_stocks

    def remove_monitor(self, code, resample=None):
        """移除指定代码的监控"""
        # 使用纯 code 作为 key
        key = code
        if key in self._monitored_stocks:
            del self._monitored_stocks[key]
            logger.info(f"Removed monitor {key}")
        
        self._save_monitors()


    def close_position_if_any(self, code: str, price: float, name: Optional[str] = None) -> bool:
        """
        检查并平掉指定代码的持仓
        :param code: 股票代码
        :param price: 平仓价格
        :param name: 股票名称 (可选)
        :return: 是否执行了平仓操作
        """
        if not hasattr(self, 'trading_logger'):
            return False
            
        try:
            trades = self.trading_logger.get_trades()
            open_trades = [t for t in trades if str(t['code']).zfill(6) == str(code).zfill(6) and t['status'] == 'OPEN']
            
            if open_trades:
                stock_name = name or open_trades[0].get('name', 'Unknown')
                # 执行卖出记录
                self.trading_logger.record_trade(code, stock_name, "卖出", price, 0, reason="Manual/Auto Close")
                logger.info(f"Auto-closed position for {code} ({stock_name}) at {price}")
                return True
        except Exception as e:
            logger.error(f"Error in close_position_if_any for {code}: {e}")
            
        return False

    def update_rule(self, code, rule_index, new_type, new_value):
        """更新指定规则"""
        # 假设更新总是针对默认周期 'd'
        key = f"{code}_d"
        if key in self._monitored_stocks:
            rules = self._monitored_stocks[key]['rules']
            if 0 <= rule_index < len(rules):
                rules[rule_index]['type'] = new_type
                rules[rule_index]['value'] = float(new_value)
                self._save_monitors()
                logger.info(f"Updated rule for {key} index {rule_index}: {new_type} {new_value}")

    def remove_rule(self, code, rule_index):
        # 假设移除总是针对默认周期 'd'
        key = f"{code}_d"
        if key in self._monitored_stocks:
            stock = self._monitored_stocks[key]
            rules = stock['rules']

            if 0 <= rule_index < len(rules):
                rule = rules.pop(rule_index)

                if 'rule_keys' in stock:
                    stock['rule_keys'].discard(
                        self._rule_key(rule['type'], rule['value'])
                    )

                if not rules:
                    del self._monitored_stocks[key]

                self._save_monitors()
    def test_alert(self, text="这是一个测试报警"):
        """测试报警功能 (强制绕过全局开关以验证引擎)"""
        logger.info(f"🔔 Forced Test Alert: {text}")
        self._play_sound_async()
        speak_text = f"测试报警，{text}"
        self._voice.say(speak_text, code="TEST")
        if self.alert_callback:
            try:
                self.alert_callback("TEST", "测试股票", text)
            except Exception as e:
                logger.error(f"Test alert callback error: {e}")

    def test_alert_specific(self, code, name, msg):
        """测试特定报警 (强制绕过全局开关以验证引擎)"""
        logger.info(f"🔔 Forced Specific Test Alert: {code} {name} {msg}")
        self._play_sound_async()
        speak_text = f"注意，{code} ，{msg}"
        self._voice.say(speak_text, code=code)
        if self.alert_callback:
            try:
                self.alert_callback(code, name, msg)
            except Exception as e:
                logger.error(f"Test alert specific callback error: {e}")

    def snooze_alert(self, code, cycles=10):
        """
        暂停报警一段时间
        :param code: 股票代码
        :param cycles: 暂停的周期数 (总时长 = cycles * alert_cooldown)
        """
        # 假设暂停总是针对默认周期 'd'
        key = f"{code}_d"
        if key in self._monitored_stocks:
            # 逻辑: last_alert 设为未来时间，使得 now - last_alert < cooldown 持续成立
            # 想要暂停 N 个周期，即 N * cooldown 时间
            # 在 t = now + N * cooldown 时，恢复报警 => (now + N*cooldown) - last_alert >= cooldown
            # => last_alert <= now + (N-1)*cooldown
            future_offset = (cycles - 1) * self._alert_cooldown
            self._monitored_stocks[key]['last_alert'] = time.time() + future_offset
            dt_str = datetime.fromtimestamp(self._monitored_stocks[key]['last_alert']).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"😴 Snoozed alert for {key}  in {cycles} cycles ({cycles * self._alert_cooldown}s alert_cooldown: {self._alert_cooldown}s next_alert_time:{dt_str})")

    def _on_pattern_detected(self, event: 'PatternEvent') -> None:
        """形态检测回调 - 触发语音播报 (带计数和高优先级检测)"""
        try:
            pattern_cn = IntradayPatternDetector.PATTERN_NAMES.get(event.pattern, event.pattern)
            
            # 区分买点信号 vs 卖点信号
            action = "风险" if event.pattern in ('high_drop', 'top_signal') else "形态"
            
            # === 高优先级信号检测 ===
            is_high_priority = False
            high_priority_reason = ""
            
            if event.pattern in ('low_open_high_walk', 'pullback_upper'):
                # 尝试从实时数据中获取当前行情 (如果可用)
                try:
                    ratio = 0.0
                    if hasattr(self, 'df') and self.df is not None and not self.df.empty and event.code in self.df.index:
                        row = self.df.loc[event.code]
                        ratio = float(row.get('ratio', 0))  # 换手率
                    
                    # 使用 detector 生成的 detail 判断起点位置
                    # detail 格式如: "低开-2.1%@MA10走高至4日高" 或 "低开-3.0%@日低走高至..."
                    detail = event.detail or ""
                    start_at_ma = "@MA" in detail or "@日低" in detail
                    has_volume = ratio > 3.0
                    
                    # 高优先级条件：从重要位置启动 或 换手>3%
                    if start_at_ma and has_volume:
                        is_high_priority = True
                        ma_level = "MA级别" if "@MA" in detail else "日低"
                        high_priority_reason = f"[HIGH] 起点{ma_level}，换手{ratio:.1f}%"
                        event.is_high_priority = True
                        logger.info(f"🔥 高优先级信号: {event.code} {event.name} - {high_priority_reason}")
                    elif start_at_ma:
                        # 从 MA 附近启动但换手不足，仍标记为较高优先级
                        is_high_priority = True
                        high_priority_reason = f"[HIGH] 起点{detail.split('走高')[0].split('@')[1] if '@' in detail else 'MA'}"
                        event.is_high_priority = True
                        logger.info(f"🔥 高优先级信号: {event.code} {event.name} - {high_priority_reason}")
                except Exception as e:
                    logger.debug(f"High priority check failed: {e}")
            
            # === 构建消息 (使用 detector 生成的 detail) ===
            count_suffix = f" (第{event.count}次)" if event.count > 1 else ""
            # 优先使用 event.detail，它包含分级信息 (如 "低开-2.1%@MA10走高至4日高")
            detail_msg = event.detail if event.detail else pattern_cn
            msg = f"{event.name} {detail_msg}{count_suffix}"
            if high_priority_reason:
                msg = f"{msg} {high_priority_reason}"
            
            # === 日志记录 ===
            priority_tag = "🔥" if is_high_priority else "🔔"
            logger.info(f"{priority_tag} 形态信号: {event.code} {event.name} - {detail_msg} @ {event.price:.2f}{count_suffix}")
            
            # === 语音播报控制 ===
            # 1. 第一次触发：完整播报
            # 2. 第2-4次触发：静默（不播报）
            # 3. 每5次触发：聚合播报 "xxx 低开走高 已触发5次"
            # 4. 高优先级信号：始终播报
            should_voice = False
            if is_high_priority:
                should_voice = True
                msg = f"注意高优先级，{msg}"
            elif event.count == 1:
                should_voice = True
            elif event.count % 5 == 0:
                should_voice = True
                msg = f"{event.name} {pattern_cn} 已触发{event.count}次"
            
            if should_voice:
                self._trigger_alert(event.code, event.name, msg, action=action, price=event.price)
            else:
                # 静默模式：只记录日志，不播报
                logger.debug(f"Signal muted (count={event.count}): {event.code} {pattern_cn}")
            
            # === 高优先级信号触发闪屏 ===
            if is_high_priority and hasattr(self, 'on_high_priority_signal'):
                try:
                    self.on_high_priority_signal(event)
                except Exception as e:
                    logger.debug(f"High priority callback failed: {e}")
            
            # === 直接写入数据库 (Live 信号独立记录, 同日同股同信号只更新计数) ===
            try:
                import sqlite3
                from datetime import datetime
                
                conn = sqlite3.connect("signal_strategy.db", timeout=10)
                c = conn.cursor()
                
                now_time = datetime.now().strftime('%H:%M:%S')
                now_date = datetime.now().strftime('%Y-%m-%d')
                priority_value = 100 if is_high_priority else 50
                
                # 检查是否已存在同日同股同信号类型
                c.execute("""
                    SELECT id, count FROM signal_message 
                    WHERE code = ? AND signal_type = ? AND source = 'live_strategy' AND created_date = ?
                    LIMIT 1
                """, (event.code, event.pattern, now_date))
                existing = c.fetchone()
                
                if existing:
                    # 已存在：更新计数和时间戳
                    new_count = existing[1] + 1
                    c.execute("""
                        UPDATE signal_message 
                        SET timestamp = ?, count = ?, priority = ?, reason = ?
                        WHERE id = ?
                    """, (now_time, new_count, priority_value, msg, existing[0]))
                    logger.debug(f"✅ Live signal updated in DB: {event.code} - {event.pattern} (count={new_count})")
                else:
                    # 不存在：插入新记录
                    c.execute("""
                        INSERT INTO signal_message (timestamp, code, name, signal_type, source, priority, score, reason, evaluated, created_date, count, consecutive_days)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (now_time, event.code, event.name, event.pattern, 'live_strategy', priority_value, event.score, msg, 0, now_date, 1, 1))
                    logger.debug(f"✅ Live signal saved to DB: {event.code} - {event.pattern}")
                
                conn.commit()
                conn.close()
            except Exception as db_err:
                logger.error(f"Failed to save live signal to DB: {db_err}")
                    
        except Exception as e:
            logger.error(f"Pattern callback error: {e}")

    def _trigger_alert(self, code: str, name: str, message: str, action: str = '持仓', price: float = 0.0, resample: str = 'd') -> None:
        """触发报警"""
        logger.debug(f"🔔 ALERT [{resample}]: {message}")
        
        # # 2. 语音播报
        # speak_text = f"注意{action}，{code} ，{message}"
        # self._voice.say(speak_text, code=code)
        # 2. 语音播报（★ 受控）
        if self.voice_enabled:
            # 1. 声音
            self._play_sound_async()
            speak_text = f"注意{action}，{code} ，{message}"
            self._voice.say(speak_text, code=code)
        # else:
        #     logger.debug(f"Voice muted for {code}")
        
        # 3. 回调
        if self.alert_callback:
            try:
                self.alert_callback(code, name, message)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        # 4. 记录交易执行 (用于回测优化和收益计算)
        if action in ("买入", "卖出", "ADD", "加仓") or "止" in action:
            # 记录交易并计算单笔收益
            self.trading_logger.record_trade(code, name, action, price, 100, reason=message, resample=resample) 

    def _play_sound_async(self):
        try:
            # 使用 MessageBeep 替代 PlaySound，更可靠且原生异步
            # MB_ICONEXCLAMATION (0x00000030L) 是一个清晰的提示音
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            logger.debug(f"MessageBeep failed: {e}")
            try:
                 # 兜底：如果 API 失败，尝试在线程中 Beep
                 threading.Thread(target=lambda: winsound.Beep(1000, 200), daemon=True).start()
            except:
                 pass


    def start_auto_trading_loop(self, force: bool = False, concept_top5: Optional[list[Any]] = None):
        """开启自动循环优选交易 (支持断点恢复/自动补作业/强制启动)"""
        self.auto_loop_enabled = True
        now_time = datetime.now()
        today_str = now_time.strftime('%Y-%m-%d')
        is_after_close = now_time.strftime('%H:%M') >= "15:00"

        # --- 0. 手动/强制启动逻辑 (与每日自动循环独立) ---
        if force:
            # 手动触发不再重置自动循环的状态，而是作为独立的批次导入
            self._voice.say("手动热点选股强制启动")
            logger.info("Manual Hotspot Selection Triggered (Independent Batch)")
            if hasattr(self, 'df'):
                self._import_hotspot_candidates(concept_top5=concept_top5, is_manual=True)
                self._voice.say(f"手动执行热点筛选{MAX_DAILY_ADDITIONS}只")
                # 确保 concept_top5 不为 None
                if concept_top5 is not None:
                    self._scan_hot_concepts(self.df, concept_top5=concept_top5)
            # 如果是盘后强制启动，标记今日已结算，防止后续 tick 再次触发 Settlement
            if is_after_close:
                self._last_settlement_date = today_str
            return True

        # --- 1. 恢复与找回逻辑 ---
        trades = self.trading_logger.get_trades()
        holding_codes = set([t['code'] for t in trades if t['status'] == 'OPEN'])
        
        restored_batch_held = []   # 已持仓的 auto 股
        restored_batch_today = []  # 今日选出但未持仓的 auto 股
        
        for code, data in self._monitored_stocks.items():
            tags = str(data.get('tags', ''))
            # 只有自动化/手动循环标签的个股且满足条件才进入 current_batch 进行状态管理
            if tags.startswith('auto_'):
                if code in holding_codes:
                    restored_batch_held.append(code)
                elif str(data.get('created_time', '')).startswith(today_str):
                    restored_batch_today.append(code)
                # 特殊逻辑：如果是昨日盘后手动选的(15:00后)，也视为今日待建仓任务进行找回
                elif tags == 'auto_manual_hotspot':
                    created_time = str(data.get('created_time', ''))
                    try:
                        if " " in created_time:
                            hour = int(created_time.split(" ")[1].split(":")[0])
                            if hour >= 15:
                                restored_batch_today.append(code)
                                logger.info(f"找回昨日收盘后手动选股: {code}")
                    except: pass

        # --- 2. 状态恢复决策 ---
        if restored_batch_held:
            # 优先恢复持仓状态
            self.batch_state = "IN_PROGRESS"
            self.current_batch = restored_batch_held
            msg = f"恢复自动交易：检测到 {len(restored_batch_held)} 只持仓股，继续监控"
            logger.info(msg)
            self._voice.say(msg)
        elif restored_batch_today:
            # 其次找回今日观察名单 (Survival after restart)
            self.batch_state = "WAITING_ENTRY"
            self.current_batch = restored_batch_today
            msg = f"找回自动交易：记录到今日选出的 {len(restored_batch_today)} 只观察股"
            logger.info(msg)
            self._voice.say(msg)
        else:
            # 确实没作业，重头开始
            self.batch_state = "IDLE"
            self.current_batch = []
            self._cleanup_auto_monitors(force_all=True, tag_filter="auto_hotspot_loop")

        # --- 3. 盘后补救逻辑 ---
        if is_after_close:
            # 如果是盘后启动，无论是否找回，都要确保 Settlement 标志位，防止被主循环重置
            if self._last_settlement_date != today_str:
                logger.info("Auto Loop: Startup after close. Marking settlement for today.")
                self._last_settlement_date = today_str
                if not restored_batch_held and not restored_batch_today:
                    self._voice.say("自动交易：今日已收盘，等待次日自动选股")
        else:
            if not restored_batch_held and not restored_batch_today:
                self._voice.say("自动循环交易模式已启动")
                logger.info("Auto Trading Loop STARTED (New Batch)")
            
            if hasattr(self, 'df'):
                self._process_auto_loop(self.df)

    def stop_auto_trading_loop(self):
        """停止自动循环"""
        self.auto_loop_enabled = False
        self.batch_state = "IDLE"
        self._voice.say("自动循环交易已停止")
        logger.info("Auto Trading Loop STOPPED")

    def _process_auto_loop(self, df, concept_top5=None):
        """
        自动循环核心逻辑：
        IDLE -> 选股(Wait Entry) -> 持仓(In Progress) -> 清仓(Cleared) -> IDLE
        """
        try:
            now = time.time()
            if now - self.batch_last_check < 5: # 5秒检查一次
                return
            self.batch_last_check = now

            # 1. State: IDLE - 需要选股
            if self.batch_state == "IDLE":
                msg = self._import_hotspot_candidates(concept_top5=concept_top5)
                if "成功导入" in msg:
                    self.batch_state = "WAITING_ENTRY"
                    self.batch_start_time = now
                    self._voice.say(f"新一轮五只优选股已就位")
                elif "StockSelector不可用" in msg:
                    pass
                else:
                    logger.info(f"Auto Loop: Import failed/skipped: {msg}")

            # 2. State: WAITING_ENTRY - 等待建仓
            elif self.batch_state == "WAITING_ENTRY":
                # 检查是否已买入
                open_counts = self._get_batch_open_count()
                if open_counts > 0:
                    self.batch_state = "IN_PROGRESS"
                    self._voice.say("目标股已建仓，进入持仓监控模式")
                    logger.info(f"Auto Loop: State -> IN_PROGRESS. Holding {open_counts}")
                else:
                    # 超时检查 (例如 60分钟无建仓，且非盘中休息)
                    # 简化：如果不买，一直监控，直到人工干预或第二天重置
                    pass

            # 3. State: IN_PROGRESS - 持仓中
            elif self.batch_state == "IN_PROGRESS":
                open_counts = self._get_batch_open_count()
                if open_counts == 0:
                     # 全部清仓
                     self.batch_state = "IDLE"
                     self._voice.say("本轮目标全部清仓，正在优化下一批策略")
                     logger.info("Auto Loop: All cleared. State -> IDLE")
                     # 可以在这里增加一个短暂冷却，避免瞬间重选
                     # self.batch_last_check = now + 60 
                     
        except Exception as e:
            logger.error(f"Auto Loop Error: {e}")

    def _get_batch_open_count(self) -> int:
        """检查当前 Batch 中有多少只处于持仓状态"""
        if not self.current_batch:
            return 0
        trades = self.trading_logger.get_trades()
        # 过滤出 status='OPEN' 且 code 在 self.current_batch 中的
        holding = [t for t in trades if t['status'] == 'OPEN' and str(t.get('code')).zfill(6) in self.current_batch]
        return len(holding)

    def _import_hotspot_candidates(self, concept_top5: Optional[list[Any]] = None, is_manual: bool = False) -> str:
        """
        专用的自动选股方法：
        优选“今日热点”中评分最高的5只标的
        策略：5个重点板块，每个板块挑选1只最强的个股 (权衡分数、量能、联动)
        
        :param is_manual: 是否为手动触发。手动触发使用独立标签，不占用/重置每日自动循环的 current_batch。
        """
        if not StockSelector:
            return "StockSelector不可用"
        
        # 1. 标签与清理策略
        if is_manual:
            tag = "auto_manual_hotspot"
            # 手动触发时，清理之前的“非持仓手动股”，但不碰自动循环的标签
            self._cleanup_auto_monitors(force_all=True, tag_filter="auto_manual_hotspot")
        else:
            tag = "auto_hotspot_loop"
            # 自动循环触发时，只清理自动标签的“非持仓股”
            self._cleanup_auto_monitors(force_all=True, tag_filter="auto_hotspot_loop")

        try:
            selector = StockSelector()
            date_str = cct.get_today()
            # 获取全部候选
            df = selector.get_candidates_df(logical_date=date_str)
            
            if df.empty:
                return "无标的"
            
            # 识别热点股 (确保 reason 列存在)
            if 'reason' in df.columns:
                df['is_hot'] = df['reason'].fillna('').astype(str).apply(lambda x: 1 if '热点' in x else 0)
            else:
                df['is_hot'] = 0

            selected_codes = []
            final_top5_df = pd.DataFrame()

            # --- 策略演进：一个板块一只股 ---
            if concept_top5 and len(concept_top5) > 0:
                logger.info(f"Auto Loop: Picking 1 stock per sector from {len(concept_top5)} concepts")
                for sector_info in concept_top5[:5]:
                    sector_name = sector_info[0]
                    # 匹配板块
                    sub_df = df[df['category'].fillna('').str.contains(sector_name)].copy()
                    
                    if not sub_df.empty:
                        # 权衡选择逻辑: 
                        # 1. 情绪价值 (score) 
                        # 2. 量能 (amount)
                        # 3. 联动强度 (is_hot)
                        # 排序权重: is_hot > score > amount
                        sub_df = sub_df.sort_values(by=['is_hot', 'score', 'amount'], ascending=[False, False, False])
                        pick = sub_df.head(1)
                        if pick['code'].values[0] not in selected_codes:
                            final_top5_df = pd.concat([final_top5_df, pick])
                            selected_codes.append(pick['code'].values[0])
                
                # 如果板块覆盖不足5个，用全局 Top 补充
                if len(final_top5_df) < 5:
                    global_top = df.sort_values(by=['is_hot', 'score', 'amount'], ascending=[False, False, False])
                    for _, row in global_top.iterrows():
                        if row['code'] not in selected_codes:
                            final_top5_df = pd.concat([final_top5_df, pd.DataFrame([row])])
                            selected_codes.append(row['code'])
                            if len(final_top5_df) >= 5: break
            else:
                # 降级：无板块信息则直接全局 Top 5
                final_top5_df = df.sort_values(by=['is_hot', 'score', 'amount'], ascending=[False, False, False]).head(5)

            # 最终取 Top 5
            final_top5_df = final_top5_df.head(5)
            
            # 手动执行不干扰自动化状态机的 Batch 限制
            if not is_manual:
                self.current_batch = final_top5_df['code'].apply(lambda x: str(x).zfill(6)).tolist()
            
            # 导入监控列表
            added_count = 0
            for _, row in final_top5_df.iterrows():
                code = str(row['code']).zfill(6)
                name = row['name']
                # Add to monitor
                self._monitored_stocks[code] = {
                    "name": name,
                    "rules": [{'type': 'price_up', 'value': float(row.get('price', 0))}], 
                    "last_alert": 0,
                    "created_time": datetime.now().strftime("%Y-%m-%d %H"),
                    "tags": tag,
                    "snapshot": {
                        "score": row.get('score', 0),
                        "reason": row.get('reason', ''),
                        "category": row.get('category', '')
                    }
                }
                added_count += 1
           
            if added_count > 0:
                self._save_monitors()
                names = ",".join(final_top5_df['name'].tolist())
                mode_str = "Manual" if is_manual else "Auto"
                logger.info(f"{mode_str} Hotspots: Selected {added_count} Stocks: {names}")
                return f"成功导入 {added_count} 只 ({mode_str})"
            return "无新标的导入"

        except Exception as e:
            logger.error(f"Auto Import Error: {e}")
            return f"Error: {e}"

    def _perform_daily_settlement(self):
        """执行每日收盘结算与准备"""
        try:
            logger.info("Starting Daily Settlement & Preparation...")
            
            # 1. 停止自动交易
            if self.auto_loop_enabled:
                self.stop_auto_trading_loop()
            
            # 2. 标记今日已结算
            self._last_settlement_date = datetime.now().strftime('%Y-%m-%d')
            
            # 3. 运行选股逻辑，为次日准备
            # 修正：收盘结算只清理自动循环逻辑中的监控
            self._cleanup_auto_monitors(force_all=True, tag_filter="auto_hotspot_loop") # 清理未持仓的自动股，为明天腾空间
            msg = "清理完成，等待次日自动选股"
            
            # 4. 语音播报
            settle_msg = f"今日交易结束，收盘结算完成。{msg}。已准备好次日交易。"
            self._voice.say(settle_msg)
            logger.info(f"Daily Settlement Done. {msg}")

        except Exception as e:
            logger.error(f"Daily Settlement Error: {e}")

    def _cleanup_auto_monitors(self, force_all: bool = False, tag_filter: str = "auto_"):
        """
        清理自动/手动添加的监控标的
        :param force_all: 是否强力清理 (不考虑今日创建时间)
        :param tag_filter: 标签过滤前缀，默认清理所有 auto_ 开头的
        """
        try:
            # 获取当前持仓代码
            trades = self.trading_logger.get_trades()
            holding_codes = set([t['code'] for t in trades if t['status'] == 'OPEN'])
            
            to_remove = []
            
            today_str = datetime.now().strftime('%Y-%m-%d')
            for code, data in self._monitored_stocks.items():
                tags = str(data.get('tags', ''))
                # 识别标签
                if tags.startswith(tag_filter):
                    if code in holding_codes:
                        continue
                    # 如果不是强制清理（如盘中维护），且是今天刚添加的，则保留
                    if not force_all:
                        created_time = str(data.get('created_time', ''))
                        if created_time.startswith(today_str):
                            continue
                    to_remove.append(code)
            
            if to_remove:
                for key in to_remove:
                    del self._monitored_stocks[key]
                
                self._save_monitors()
                logger.info(f"Auto Loop Cleanup: Removed {len(to_remove)} unheld stocks: {to_remove}")
            else:
                logger.info("Auto Loop Cleanup: No unheld auto-stocks found.")
                
        except Exception as e:
            logger.error(f"Cleanup Error: {e}")


def test_check_strategies_params():
    """
    测试 _check_strategies 参数类型一致性。
    验证 now, last_alert, sent_data['ts'] 等时间戳类型。
    """
    import time
    from datetime import datetime
    
    print("===== 测试参数类型一致性 =====")
    
    # 模拟 now 变量（应为 float）
    now = time.time()
    print(f"now = time.time() -> type: {type(now).__name__}, value: {now}")
    
    # 模拟 last_alert（应为 float，初始值为 0）
    last_alert = 0
    print(f"last_alert -> type: {type(last_alert).__name__}, value: {last_alert}")
    
    # 测试 now - last_alert（应正常工作）
    try:
        diff = now - last_alert
        print(f"✅ now - last_alert = {diff:.2f} (正常)")
    except TypeError as e:
        print(f"❌ now - last_alert 失败: {e}")
    
    # 模拟 sent_data['ts']（应为 float）
    sent_data = {'value': 0.5, 'ts': 0}
    print(f"sent_data['ts'] -> type: {type(sent_data['ts']).__name__}, value: {sent_data['ts']}")
    
    # 测试 now - sent_data['ts']（应正常工作）
    try:
        diff = now - sent_data['ts']
        print(f"✅ now - sent_data['ts'] = {diff:.2f} (正常)")
    except TypeError as e:
        print(f"❌ now - sent_data['ts'] 失败: {e}")
    
    # 模拟错误情况：now 为 datetime 对象
    now_datetime = datetime.now()
    print(f"\n模拟错误情况: now = datetime.now() -> type: {type(now_datetime).__name__}")
    
    try:
        diff = now_datetime - last_alert
        print(f"⚠️ datetime - int 意外成功: {diff}")
    except TypeError as e:
        print(f"✅ 正确捕获类型错误: {e}")
    
    try:
        diff = now_datetime - sent_data['ts']
        print(f"⚠️ datetime - float 意外成功: {diff}")
    except TypeError as e:
        print(f"✅ 正确捕获类型错误: {e}")
    
    print("\n===== 测试完成 =====")
    return True


if __name__ == "__main__":
    test_check_strategies_params()
