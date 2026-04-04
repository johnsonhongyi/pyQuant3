# -*- coding: utf-8 -*-
"""
Stock Live Strategy & Alert System
高性能实时股票跟踪与语音报警模块
"""
from __future__ import annotations
import threading
import time
import os
import json
import datetime
import multiprocessing as mp
import pandas as pd
import numpy as np
from collections import deque
import re
import socket
import queue
from queue import Queue, Empty, Full
from typing import Any, Optional, Callable, Dict, List, Union
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from JohnsonUtil.commonTips import timed_ctx, print_timing_summary
from intraday_decision_engine import IntradayDecisionEngine
from risk_engine import RiskEngine
from trading_logger import TradingLogger, NumpyEncoder
from JSONData import sina_data
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
from signal_bus import SignalBus, get_signal_bus, BusEvent
from market_pulse_engine import DailyPulseEngine
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory
from logger_utils import  with_log_level
from trading_hub import get_trading_hub, TrackedSignal  # [NEW] Import TradingHub
from alert_manager import get_alert_manager # [NEW] Import AlertManager
from signal_message_queue import SignalMessageQueue, SignalMessage # [NEW] Shadow Engine Support
from td_sequence import calculate_td_sequence
from signal_bus import get_signal_bus, SignalBus, publish_standard_signal
from signal_standard import StandardSignal

import logging
logger: logging.Logger = LoggerFactory.getLogger(name="stock_live_strategy")
MAX_DAILY_ADDITIONS = cct.MAX_DAILY_ADDITIONS
# pyttsx3 import removed - delegated to VoiceAnnouncer/AlertManager
ipc_queue = Queue(maxsize=1000)  # ⭐ [NEW] IPC 异步发送队列 (Resolved mp.Queue GIL Crash)
_ipc_sender_thread: Optional[threading.Thread] = None
_ipc_sender_stop = threading.Event()

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

# [NEW] 仓位状态机
try:
    from position_phase_engine import PositionPhaseEngine, TradePhase
    HAS_PHASE_ENGINE = True
except ImportError:
    HAS_PHASE_ENGINE = False
    logger.warning("PositionPhaseEngine not found.")

# [NEW] T+1 交易策略引擎
try:
    from t1_strategy_engine import T1StrategyEngine
    HAS_T1_ENGINE = True
except ImportError:
    HAS_T1_ENGINE = False
    logger.warning("T1StrategyEngine not found.")

# pythoncom import removed - usage localized or delegated


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


def _ipc_sender_worker():
    """ dedicada worker thread for sending IPC signals to the visualizer """
    IPC_HOST = '127.0.0.1'
    IPC_PORT = 26668
    logger.info(f"🚀 IPC Sender worker started (Target: {IPC_HOST}:{IPC_PORT})")
    
    while not _ipc_sender_stop.is_set():
        try:
            # 阻塞获取任务，带超时以便检查 _ipc_sender_stop
            data = ipc_queue.get(timeout=1.0)
            if data == "__STOP__":
                break
            
            json_str = json.dumps(data)
            msg = f"|SIGNAL|{json_str}"
            
            # 建立连接并发送
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5) # 稍微放宽一点连接超时
                try:
                    s.connect((IPC_HOST, IPC_PORT))
                    s.sendall(b"CODE")
                    s.sendall(msg.encode('utf-8'))
                except (socket.timeout, ConnectionRefusedError):
                    # 如果 Visualizer 没开，默默丢弃或简单记录
                    # logger.debug("Visualizer IPC offline, signal dropped.")
                    pass
                except Exception as e:
                    logger.debug(f"IPC Send Error: {e}")
            
            ipc_queue.task_done()
            
        except Empty:
            continue
        except Exception as e:
            logger.error(f"IPC Worker Error: {e}")
            time.sleep(1)

    logger.info("IPC Sender worker exited.")

def send_signal_to_visualizer_ipc(data: dict):
    """ Standardized signals for IPC and SignalBus """
    global _ipc_sender_thread

    # ⭐ [THROTTLE] 内部节流：防止同一秒内对同一只股票发送过多重复的 IPC 信号 (震荡导致)
    now = time.time()
    code = data.get('code')
    if code:
        if not hasattr(send_signal_to_visualizer_ipc, '_last_t'):
            send_signal_to_visualizer_ipc._last_t = {}
        
        last_t_map = send_signal_to_visualizer_ipc._last_t
        if now - last_t_map.get(code, 0) < 0.5: # 0.5秒冷却
            return
        last_t_map[code] = now

    try:
        # 1. Start IPC sender thread if not already running
        if _ipc_sender_thread is None or not _ipc_sender_thread.is_alive():
            _ipc_sender_thread = threading.Thread(target=_ipc_sender_worker, daemon=True, name="IPCSenderWorker")
            _ipc_sender_thread.start()

        # 2. ---------- SignalBus (Main process only) ----------
        sig_type = data.get('pattern', 'ALERT')
        try:
            from signal_bus import SignalBus, StandardSignal, publish_standard_signal
            std_sig = StandardSignal(
                code=data.get('code', ''),
                name=data.get('name', ''),
                type=SignalBus.EVENT_PATTERN if sig_type != 'ALERT' else SignalBus.EVENT_ALERT,
                subtype=sig_type,
                price=data.get('price', 0.0),
                timestamp=data.get('timestamp', datetime.datetime.now().strftime("%H:%M:%S")),
                detail=data.get('message', ''),
                source="LiveStrategy",
                is_high_priority=data.get('is_high_priority', False),
                score=float(data.get('score', 0.0)),
                grade=data.get('grade', '')
            )
            publish_standard_signal(std_sig)
        except Exception as e:
            logger.debug(f"SignalBus publish failed: {e}")

        # 3. ---------- IPC (Queue it for Async worker) ----------
        if ipc_queue:
            ipc_queue.put(data, block=False) # Non-blocking put
    except queue.Full:
        pass
    except Exception as e:
        logger.debug(f"send_signal_to_visualizer_ipc error: {e}")
        

# _voice_process_target removed (moved to alert_manager.py)

class VoiceAnnouncer:
    """独立的语音播报引擎 (代理 AlertManager)"""
    def __init__(self) -> None:
        self.manager = get_alert_manager()
        self.manager.start()
        # Initialize manager callbacks to empty if needed, or rely on properties
    
    @property
    def on_speak_start(self):
        return self.manager.on_speak_start
    
    @on_speak_start.setter
    def on_speak_start(self, callback):
        self.manager.on_speak_start = callback

    @property
    def on_speak_end(self):
        return self.manager.on_speak_end
    
    @on_speak_end.setter
    def on_speak_end(self, callback):
        self.manager.on_speak_end = callback

    def pause(self) -> None:
        """暂停语音播报"""
        self.manager.voice_enabled = False
        logger.debug("VoiceAnnouncer: 已暂停 (AlertManager Voice Disabled)")
    
    def resume(self) -> None:
        """恢复语音播报"""
        self.manager.resume_voice()
        logger.debug("VoiceAnnouncer: 已恢复")
    
    @property
    def is_speaking(self) -> bool:
        return not self.manager.voice_queue.empty()
    
    def wait_for_safe(self, timeout: float = 3.0) -> bool:
        start = time.time()
        while self.is_speaking:
            if time.time() - start > timeout:
                return False
            time.sleep(0.1)
        return True

    def say(self, text: str, code: Optional[str] = None) -> None:
        """兼容旧接口"""
        self.announce(text, code)

    def announce(self, text: str, code: Optional[str] = None) -> None:
        """发送报警"""
        # 触发回调 (Legacy support)
        if self.on_speak_start:
            try:
                self.on_speak_start(code)
            except Exception:
                pass
            
        # 提升优先级
        p = 2
        if any(kw in text for kw in ["注意", "卖出", "风险", "警告"]):
            p = 1
            
        self.manager.send_alert(text, priority=p, key=code)
        
        # Fake timer for on_speak_end (Legacy)
        if self.on_speak_end:
            threading.Timer(1.0, lambda: self._safe_callback(self.on_speak_end, code)).start()

    def stop(self) -> None:
        """停止所有当前正在播放的语音"""
        self.manager.stop_current_speech()

    def stop_current_speech(self, key: Optional[str] = None) -> None:
        """[Proxy] 委派给 AlertManager 的中断接口，兼容 MonitorTK 调用习惯"""
        self.manager.stop_current_speech(key=key)

    def cancel_for_code(self, code: str) -> None:
        """针对特定品种取消语音播报（精准中断）"""
        self.manager.stop_current_speech(key=code)

    def shutdown(self):
        """完全关闭语音引擎"""
        self.manager.stop()

    def _safe_callback(self, cb, arg):
        try:
            cb(arg)
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
        ls_val = snap.get('loss_streak', 0)
        loss_streak = int(ls_val) if not pd.isna(ls_val) else 0
        max_loss = self.constraints.get('max_loss_streak', 2)
        if isinstance(max_loss, (int, float)) and loss_streak >= int(max_loss):
            return True, f"个股近期连亏{loss_streak}次，强行降温"

        return False, ""

class StockLiveStrategy:
    # 💎 [STATIC PERSISTENCE] 类级别静态存储，确保 D/2D/3D 等不同周期的扫描池和游标互不干扰
    _kline_rr_cursors_static: Dict[str, int] = {}
    _kline_rr_pools_static: Dict[str, List[str]] = {}
    
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
        self.strategy_callback: Optional[Callable[[pd.DataFrame], None]] = None # [NEW] Callback after check finishes
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
        self._sina_data = sina_data.Sina()
        self._voice = VoiceAnnouncer()
        self.voice_announcer = self._voice # Alias for backward compatibility
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
        self._needs_monitor_save: bool = False # [NEW] Flag for batch saving

        self.config_file = "voice_alert_config.json"
        
        # 🚀 [NEW] K线抓取配置与状态 (Stable v2)
        self.max_fetch_kline = cct.live_MAX_FETCH     #30  每轮最大抓取数量
        self._kline_rr_pool: List[str] = []
        # 使用静态变量防止由于 UI 对象重置导致的游标归零 (由 StockLiveStrategy._kline_rr_cursor_static 托管)
        
        
        # --- [NEW] 黑名单管理 (Blacklist Management) ---
        self._blacklist_data = {} # {code: {name, date, reason, hit_count}}
        # Note: 此时 trading_logger 可能还没初始化，会在后续加载

        self.alert_callback = None
        self.realtime_service = realtime_service
        
        # [P3 Fix] Store config as instance attributes
        self._stop_loss_pct = stop_loss_pct
        self._take_profit_pct = take_profit_pct
        self._trailing_stop_pct = trailing_stop_pct
        self._max_single_stock_ratio = max_single_stock_ratio
        
        self.scan_hot_concepts_status = True
        
        # --- 外部数据缓存 (55188.cn) ---
        self.ext_data_55188: pd.DataFrame = pd.DataFrame()
        self.last_ext_update_ts: float = 0
        
        # --- [NEW] 跟单队列缓存 (Follow Queue Cache) ---
        self.follow_queue_cache: List[TrackedSignal] = []
        self.last_follow_sync_ts: float = 0
        
        # --- [NEW] T+0 动作冷却 ---
        self._t0_cooldowns: dict[str, float] = {}
        
        # --- 自动交易相关状态初始化 ---
        self.auto_loop_enabled = False
        self.batch_state = "IDLE"
        self.current_batch = []
        self.batch_last_check: float = 0.0
        self._settlement_prep_done = False
        self._last_settlement_date = None
        self._market_win_rate_cache = 0.5
        self._market_win_rate_ts = 0.0
        
        # --- [NEW] 状态机与验证引擎标记 ---
        self._watchlist_validated_today: bool = False
        self._last_validation_date: str = ""
        self._last_rank_scan_date: str = ""
        self._pending_hist_fetches: set = set() # [NEW] Track async history fetches
        self._df_lock: Optional[threading.Lock] = None # 🛡️ [NEW] From master app
        self._lock = threading.Lock() # 🛡️ [NEW] 内部列表锁，保护 _monitored_stocks 和属性竞态

        logger.info(f'StockLiveStrategy 初始化: alert_cooldown={alert_cooldown}s, '
                   f'stop_loss={stop_loss_pct:.1%}, take_profit={take_profit_pct:.1%}')
        
        # 🛡️ [OPTIMIZATION] 统一使用主 Master 的线程池 (由用户明确要求，防止资源失控)
        if hasattr(self.master, 'executor') and self.master.executor:
            self.executor = self.master.executor
            self._using_shared_executor = True
            logger.info("✅ StockLiveStrategy: 已连接主 Master 共享线程池")
        else:
            self.executor = ThreadPoolExecutor(max_workers=cct.livestrategy_max_workers)
            self._using_shared_executor = False
            logger.debug(f"ℹ️ StockLiveStrategy: 独立创建私有线程池 (Workers: {cct.livestrategy_max_workers})")
        
        self._is_checking_resamples: set[str] = set() # [NEW] 并行运行状态锁，按 resample 隔离防止并发冲突
        self._last_process_time = 0.0 # 🛡️ Ensure init 
        
        # 初始化记录器 (必须在 _load_monitors 之前)
        # [OPTIMIZE] Delay TradingLogger and TradingHub init to background to avoid startup hang
        self.trading_logger = None 
        self.supervisor = None

        # ⭐ [FIX] 将耗时的监控加载逻辑异步化，防止阻塞主界面启动 (Stuck Issue)
        self.executor.submit(self.load_monitors)
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

        # --- ⭐ 日线形态检测器 ---
        try:
            from daily_pattern_detector import DailyPatternDetector
            self.daily_pattern_detector = DailyPatternDetector()
            self.daily_pattern_detector.on_pattern = self._on_daily_pattern_detected
            # 历史数据缓存 {code: df_history}
            self.daily_history_cache = {}
            self.last_daily_history_refresh = 0
            logger.info("DailyPatternDetector initialized with history cache.")
        except Exception as e:
            logger.error(f"Failed to initialize DailyPatternDetector: {e}")
            self.daily_pattern_detector = None

        # --- [NEW] 仓位状态机引擎 ---
        if HAS_PHASE_ENGINE:
            self.phase_engine = PositionPhaseEngine()
            logger.info("PositionPhaseEngine initialized.")
        else:
            self.phase_engine = None

        # --- [NEW] T+1 交易策略引擎 ---
        if HAS_T1_ENGINE:
            self.t1_engine = T1StrategyEngine()
            logger.info("T1StrategyEngine initialized.")
        else:
            self.t1_engine = None

        # --- Automatic Trading Loop State ---
        # self.auto_loop_enabled = False (已经在上方初始化)
        # self.batch_state = "IDLE"
        self.batch_start_time: float = 0.0
        self.batch_last_check: float = 0.0

        # --- [NEW] 数据异常监测计数器与容器 (10轮一报) ---
        self._data_exceptions: dict[str, str] = {} # {code: reason}
        self._data_exception_lock = threading.Lock()
        self._data_check_rounds: int = 0

    def stop(self):
        """停止策略引擎并关闭后台线程"""
        if self._is_stopping:
             return
        self._is_stopping = True
        logger.info("Stopping StockLiveStrategy...")
        
        # 1. 停止语音播报 (彻底关闭后台进程)
        if hasattr(self, "_voice") and self._voice:
            try:
                # ⭐ [FIX] 使用 shutdown 彻底终止 AlertManager 进程，解决退出卡住问题
                self._voice.shutdown() 
            except Exception as e:
                logger.error(f"Error shutting down VoiceAnnouncer: {e}")
                
        # 2. 停止线程池 (只有在非共享模式下才执行 shutdown，防止误关全局池)
        if hasattr(self, "executor") and self.executor and not getattr(self, "_using_shared_executor", False):
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
                logger.info("StockLiveStrategy: Private executor shutdown.")
            except (TypeError, Exception):
                # Python 3.8 不支持 cancel_futures
                try:
                    self.executor.shutdown(wait=False)
                except: pass

        # 3. ⭐ [NEW] 停止 IPC 发送线程
        try:
            global _ipc_sender_stop, _ipc_sender_thread
            if '_ipc_sender_stop' in globals():
                _ipc_sender_stop.set()
                _ipc_queue.put("__STOP__") # 唤醒并终止
        except Exception as e:
            logger.debug(f"Error stopping IPC sender: {e}")

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
        
        # ⭐ [FIX] 同步到底层 VoiceAnnouncer/AlertManager 状态
        if hasattr(self, '_voice') and self._voice:
            if self.voice_enabled:
                self._voice.resume()
        logger.info(f"Voice announcer enabled = {self.voice_enabled} (Synced to VoiceAnnouncer)")

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

    def load_monitors(self):
        """[OPTIMIZED] 从 JSON 和数据库后台加载监控列表 (Background Thread)"""
        import json
        try:
            # 1. 首先在后台初始化记录器与监理器 (涉及数据库 I/O)
            if self.trading_logger is None:
                self.trading_logger = TradingLogger()
                self.supervisor = StrategySupervisor(self.trading_logger) # type: ignore
                logger.info("✅ TradingLogger & StrategySupervisor initialized in background.")
            
            # 2. 预热 TradingHub (触发数据库表创建与 WAL 设置)
            hub = get_trading_hub()
            logger.info("✅ TradingHub initialized in background.")
            
            with self._lock:
                self._monitored_stocks = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                
                # [Fix] Enforce Unique Code: Merge duplicates into single entry keyed by pure code
                for key, data in raw_data.items():
                    # Extract pure code
                    pure_code = data.get('code') or key.split('_')[0]
                    # Canonical Key is pure code
                    c_key = pure_code
                    
                    if c_key not in self._monitored_stocks:
                        self._monitored_stocks[c_key] = data
                        self._monitored_stocks[c_key]['code'] = pure_code # Ensure code field
                    else:
                        # Merge into existing
                        target = self._monitored_stocks[c_key]
                        
                        # 1. Merge Rules (Avoid duplicates)
                        existing_rules = set()
                        for r in target.get('rules', []):
                            # (type, value) tuple for hashing
                            r_val = float(r['value']) if isinstance(r['value'], (int, float, str)) else 0
                            existing_rules.add((r['type'], f"{r_val:.4f}"))
                            
                        metrics_added = 0
                        for r in data.get('rules', []):
                            r_val = float(r['value']) if isinstance(r['value'], (int, float, str)) else 0
                            sig = (r['type'], f"{r_val:.4f}")
                            if sig not in existing_rules:
                                target['rules'].append(r)
                                existing_rules.add(sig)
                                metrics_added += 1
                        
                        if metrics_added > 0:
                            logger.info(f"Merged {metrics_added} rules from duplicate key '{key}' into '{c_key}'")

            # --- [新增] 从 voice_alerts 数据表加载备补数据 ---
            if hasattr(self, 'trading_logger'):
                try:
                    db_alerts = self.trading_logger.get_voice_alerts()
                    for alert in db_alerts:
                        code = alert['code']
                        resample = alert.get('resample', 'd')
                        # 确定 key (兼容逻辑: 优先匹配 JSON 已有的 key)
                        key = code if code in self._monitored_stocks else (f"{code}_{resample}" if f"{code}_{resample}" in self._monitored_stocks else code)
                        
                        if key not in self._monitored_stocks:
                             # 如果 JSON 里没有，则从 DB 恢复
                             self._monitored_stocks[key] = {
                                 'code': code,
                                 'name': alert['name'],
                                 'rules': json.loads(alert['rules']) if isinstance(alert['rules'], str) else alert['rules'],
                                 'last_alert': alert.get('last_alert', 0),
                                 'resample': resample,
                                 'created_time': alert.get('created_time', ''),
                                 'create_price': alert.get('create_price', 0.0),
                                 'tags': alert.get('tags', ''),
                                 'added_date': alert.get('added_date', ''),
                                 'rule_type_tag': alert.get('rule_type_tag', '')
                             }
                        else:
                             # 如果 JSON 里已有，但 create_price 为 0，而 DB 有值，则覆盖
                             stock = self._monitored_stocks[key]
                             if stock.get('create_price', 0) == 0 and alert.get('create_price', 0) > 0:
                                 stock['create_price'] = alert['create_price']
                             # 同样补齐可能缺失的字段
                             if not stock.get('created_time') and alert.get('created_time'):
                                 stock['created_time'] = alert['created_time']
                except Exception as e:
                    logger.error(f"Failed to sync from voice_alerts DB: {e}")

            # --- [核心同步] 从数据库同步持仓股监控 ---
            open_codes = set()
            if hasattr(self, 'trading_logger'):
                try:
                    trades = self.trading_logger.get_trades()
                    open_trades = [t for t in trades if t['status'] == 'OPEN']
                    
                    recovered_count = 0
                    for t in open_trades:
                        code = str(t['code']).zfill(6)
                        resample = t.get('resample', 'd')
                        open_codes.add(code)
                        
                        # 1. 强制校准逻辑：即使已存在，如果是 recovered_holding，也要校准时间与价格
                        b_date = str(t.get('buy_date', '') or '')
                        real_created_time = b_date[:19] if len(b_date) >= 10 else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        b_price = float(t['buy_price'])

                        # 如果已在监控中
                        if code in self._monitored_stocks:
                            exist_stock = self._monitored_stocks[code]
                            if exist_stock.get('tags') == "recovered_holding":
                                # 强制覆盖为 DB 的真实数据
                                exist_stock['created_time'] = real_created_time
                                exist_stock['create_price'] = b_price
                                if 'snapshot' not in exist_stock:
                                    exist_stock['snapshot'] = {}
                                exist_stock['snapshot']['cost_price'] = b_price
                                exist_stock['snapshot']['buy_date'] = b_date
                        
                        # 2. 如果完全不存在，则全新恢复
                        if code not in self._monitored_stocks:
                            # b_date 等变量已在上面定义
                            # 如果数据库里没有有效的 buy_date，才被迫使用当前时间
                            real_created_time = b_date[:19] if len(b_date) >= 10 else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            b_price = float(t['buy_price'])
                            
                            self._monitored_stocks[code] = {
                                'code': code,
                                'name': t['name'],
                                'rules': [{'type': 'price_up', 'value': b_price}],
                                'last_alert': 0,
                                'resample': resample,
                                'created_time': real_created_time,
                                'create_price': b_price, # ✅ 恢复时同步设置加入价 = 成本价
                                'tags': "recovered_holding",
                                'snapshot': {
                                    'cost_price': b_price,
                                    'buy_date': b_date
                                }
                            }
                            recovered_count += 1
                            logger.info(f"Recovered {code} with date {real_created_time} and cost {b_price}")
                    
                    if recovered_count > 0:
                        logger.info(f"♻️ 监控恢复: 从数据库载入 {recovered_count} 只活跃持仓股")
                        self._save_monitors()
                        
                    # --- [关键清理] 如果监控项标记为 recovered_holding 但外部(数据库)已平仓，则自动移除 ---
                    to_remove = []
                    for key, stock in list(self._monitored_stocks.items()):
                        if stock.get('tags') == "recovered_holding":
                            # 提取 code (兼容 key 为 code_resample 的老格式)
                            s_code = stock.get('code') or key.split('_')[0]
                            if s_code not in open_codes:
                                to_remove.append(key)
                    
                    if to_remove:
                        with self._lock:
                            for k in to_remove:
                                if k in self._monitored_stocks:
                                    del self._monitored_stocks[k]
                        logger.info(f"🧹 自动清理: 已移出 {len(to_remove)} 只已平仓的持仓股监控")
                        self._save_monitors()

                except Exception as db_e:
                    logger.error(f"同步数据库持仓状态失败: {db_e}")

            # ✅ 结构迁移 / 补齐 / 运行时属性填充 (作用于所有 stock)
            for key, stock in self._monitored_stocks.items():
                stock.setdefault('rules', [])
                stock.setdefault('last_alert', 0)
                stock.setdefault('resample', 'd')
                stock.setdefault('create_price', 0.0)
                stock.setdefault('snapshot', {}) # 🛡️ [FIX] 确保存在 snapshot 字典，防止 KeyError
                if 'code' not in stock:
                    stock['code'] = key.split('_')[0]

                # ✅ 修补缺失的价格 (从快照或当前行情尝试恢复)
                if stock.get('create_price', 0) == 0:
                    snap_price = stock.get('snapshot', {}).get('trade', 0)
                    if snap_price > 0:
                        stock['create_price'] = snap_price
                    elif hasattr(self, 'df') and self.df is not None:
                         # 尝试从最近一次行情中获取
                         s_code = stock['code']
                         if s_code in self.df.index:
                             stock['create_price'] = float(self.df.loc[s_code].get('trade', 0))

                # ✅ 重建 rule_keys
                rule_keys = set()
                for r in stock['rules']:
                    try:
                        r_key = self._rule_key(r['type'], r['value'])
                        rule_keys.add(r_key)
                    except Exception:
                        pass
                stock['rule_keys'] = rule_keys

                # ✅ 加载 snapshot 里的关键行情数据到顶层，方便 UI 显示
                snap = stock.get('snapshot', {})
                for attr in ['trade', 'percent', 'volume', 'ratio', 'nclose', 'last_close', 'ma5d', 'ma10d']:
                    stock[attr] = snap.get(attr, 0)

            self.stock_count: int = len(self._monitored_stocks)
            self._save_monitors() # ✅ 持久化修补后的价格到 JSON 和数据库
            self._sync_grades_to_detectors() # [NEW] 同步评级数据到检测器
            logger.info(f"Loaded {self.stock_count} voice monitors (File: {self.config_file})")

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
            

            with self._lock:
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
                            "created_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "tags": f"auto_{logical_date}",
                            "create_price": float(row.get('price', 0.0)),
                            "snapshot": {
                                "trade": float(row.get('price', 0.0)),
                                "percent": float(row.get('percent', 0.0)),
                                "ratio": float(row.get('ratio', 0.0)),
                                "amount_desc": row.get('amount', 0),
                                "status": str(row.get('status', '')),
                                "score": float(row.get('score', 0.0)),
                                "grade": str(row.get('grade', '')),  # [NEW] 存入等级
                                "reason": str(row.get('reason', ''))
                            }
                        }
                        added_count += 1
                    else:
                        # 如果已存在，更新其 snapshot
                        snap = self._monitored_stocks[code].setdefault('snapshot', {})
                        snap.update({
                            "status": str(row.get('status', snap.get('status', ''))),
                            "score": float(row.get('score', snap.get('score', 0.0))),
                            "grade": str(row.get('grade', snap.get('grade', ''))), # [NEW] 更新等级
                            "reason": str(row.get('reason', snap.get('reason', '')))
                        })
                
                self._last_import_logical_date = logical_date
            
            if added_count > 0:
                self._save_monitors()
                self._sync_grades_to_detectors() # [NEW] 同步到检测器
                logger.info(f"逻辑日期 {logical_date}: 已导入 {added_count} 只强势股")
                return f"成功导入 {added_count} 只标的 (日期:{logical_date})"
            else:
                return f"逻辑日期 {logical_date}: 标的已在监控列表中"
                
        except Exception as e:
            logger.error(f"导入筛选股失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"导入失败: {e}"



    def _sync_grades_to_detectors(self):
        """将当前监控股票的评级数据同步到形态检测器中"""
        if not self._monitored_stocks:
            return
            
        grades = {}
        for key, stock in self._monitored_stocks.items():
            code = stock.get('code', key.split('_')[0])
            grade = stock.get('grade') or stock.get('snapshot', {}).get('grade', '')
            if grade:
                grades[code] = grade
        
        if getattr(self, 'pattern_detector', None):
            self.pattern_detector.set_stock_grades(grades)
            
        if getattr(self, 'daily_pattern_detector', None):
            self.daily_pattern_detector.set_stock_grades(grades)
            
        logger.debug(f"Synced {len(grades)} stock grades to detectors.")

    def _save_monitors(self):
        """保存配置（不包含派生字段，同时增加即时行情信息）"""
        try:
            import json
            data = {}

            for key, stock in list(self._monitored_stocks.items()):
                # --- 构建基础数据 ---
                record = {
                    'name': stock.get('name'),
                    'rules': stock.get('rules', []),
                    'last_alert': stock.get('last_alert', 0),
                    'resample': stock.get('resample', 'd'), # 保存周期信息
                    'created_time': stock.get('created_time', datetime.datetime.now().strftime("%Y-%m-%d %H")),
                    'create_price': stock.get('create_price', 0.0),
                    'tags': stock.get('tags', ""),
                    'added_date': stock.get('added_date', ""),
                    'rule_type_tag': stock.get('rule_type_tag', ""),
                    'grade': stock.get('grade', stock.get('snapshot', {}).get('grade', "")) # [NEW] 持久化等级
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
                for key, stock in list(self._monitored_stocks.items()):
                    code_from_key = key.split('_')[0]
                    resample_from_key = stock.get('resample', 'd')
                    self.trading_logger.log_voice_alert_config(
                        code=code_from_key,
                        resample=resample_from_key,
                        name=stock.get('name', ''),
                        rules=json.dumps(stock.get('rules', [])),
                        last_alert=stock.get('last_alert', 0),
                        tags=stock.get('tags', ''),
                        rule_type_tag=stock.get('rule_type_tag', ''),
                        create_price=stock.get('create_price', 0.0),
                        created_time=stock.get('created_time', '')
                    )

        except Exception as e:
            logger.error(f"Failed to save voice monitors: {e}")

    def _rule_key(self, rule_type, value):
        return f"{rule_type}:{value:.2f}"

    def add_monitor(self, code, name, rule_type, value, tags=None, resample='d', create_price=0.0):
        value = float(value)
        # 使用纯 code 作为 key（不再使用复合 key）
        key = code

        with self._lock:
            if key not in self._monitored_stocks:
                self._monitored_stocks[key] = {
                    'code': code, # 保存原始代码以供查询
                    'name': name,
                    'rules': [],
                    'last_alert': 0,
                    'resample': resample,
                    'created_time': datetime.datetime.now().strftime("%Y-%m-%d %H"),
                    'added_date': datetime.datetime.now().strftime('%Y-%m-%d'), # [新增] 用于已添加数量统计
                    'create_price': create_price,
                    'tags': tags or ""
                }
            
            stock = self._monitored_stocks[key]
            # 如果提供了 tags 且不为空，则更新（覆盖旧的或空的）
            if tags:
                stock['tags'] = tags
            
            # 记录触发加入的规则类型
            stock['rule_type_tag'] = rule_type
            
            # 确保 created_time 和 added_date 存在 (对于旧数据)
            # import removed
            if 'created_time' not in stock:
                stock['created_time'] = datetime.datetime.now().strftime("%Y-%m-%d %H")
            if 'added_date' not in stock:
                stock['added_date'] = datetime.datetime.now().strftime('%Y-%m-%d')
    
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
        # import removed
        self.signal_history.appendleft({
            'time': datetime.datetime.now().strftime("%H:%M:%S"),
            'code': code,
            'name': name,
            'type': rule_type,
            'value': value,
            'create_price': create_price,
            'msg': f"Added monitor: {rule_type} > {value} (Price: {create_price:.2f})"
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
            
        # ----------------- Throttling -----------------
        now = time.time()
        # 🛡️ 快速检查锁状态 (按周期隔离保护)，防止并发重入
        if resample in self._is_checking_resamples:
            return
            
        if now - getattr(self, '_last_process_time', 0.0) < 1.0: # 稍微提高频率到 1s
            return
        self._last_process_time = now

        # 🛡️ [FIX] 优先从 master 获取锁
        if self._df_lock is None and self.master:
            self._df_lock = getattr(self.master, '_df_lock', None)

        # 标记当前处理的周期
        self.current_resample = resample 
        
        # [CRITICAL] 严格限制仅在交易时间段触发信号 (09:15 - 15:05)
        now_dt = datetime.datetime.now()
        today_str = now_dt.strftime('%Y-%m-%d')
        now_time_int = int(now_dt.strftime('%H%M'))
        now_time_str = now_dt.strftime('%H:%M')
        is_trading_active = (915 <= now_time_int <= 1505)

        # 🛡️ [OPTIMIZE] 避免全量 copy()，仅在需要异步修改时再进行子集或完整拷贝
        # 改为延迟到扫描和策略逻辑内。
        df_internal = df_all # Alias
        self.df = df_internal # Alias for back-filling
        
        # 🔍 [DIAGNOSTIC] 深层数据结构探针
        tc_sample = list(self._monitored_stocks.keys())[:5]
        idx_sample = list(df_internal.index[:5])
        idx_dtype = df_internal.index.dtype
        logger.info(f"🔍 [DF_PROBE] TradingActive={is_trading_active} Monitors={len(self._monitored_stocks)} Samples={tc_sample} Index={idx_sample} Dtype={idx_dtype}")

        # --- 1. 热点题材领涨股发现 (Algorithm Expansion) ---
        if is_trading_active and (925 <= now_time_int <= 1505):
             # [OPTIMIZE] 后台扫描只需要局部快照
             self.executor.submit(self._scan_hot_concepts, df_internal.copy(), concept_top5, resample=resample)

        # --- 1.2 [NEW] 每日热股跨日验证 (9:15-9:30 处理昨天入队的标的) ---
        if 915 <= now_time_int <= 930:
            if getattr(self, '_last_validation_date', '') != today_str:
                self.executor.submit(self._daily_watchlist_validation, df_internal)
                self._last_validation_date = today_str

        # --- 1.5 Rank 强势股自动入队跟单 (每日 9:35-10:30 扫描一次) ---
        # 1. 开盘自动全扫描 (每日只需运行一次，不限时间，启动即扫)
        if not getattr(self, '_rank_scan_done_today', False):
            # 只有在非休市时间且有数据时才扫描
            if not df_internal.empty and cct.get_trade_date_status(): # 确保是交易日
                 self.executor.submit(self._scan_rank_for_follow, df_internal, concept_top5, top_n=100)
                 self._rank_scan_done_today = True
                 logger.info(f"🚀 [Startup] Triggered daily rank scan. (Time: {now_time_int})")
            else:
                 logger.debug(f"⏳ [Startup] Rank scan skipped (Empty DF or Non-trading day)")
        
        # 每日重置扫描标记 (移到下方以利用 today_str)
        if getattr(self, '_last_rank_scan_date', '') != today_str:
            self._rank_scan_done_today = False
            self._last_rank_scan_date = today_str
        
        # 2. 规则引擎监控 (Existing rules)
        # self._check_risk_control(df_internal)
        
        # --- ⭐ [关键] 异步触发策略判定 (增加原子锁保护，支持多周期并行) ---
        can_submit = False
        with self._lock:
            if resample not in self._is_checking_resamples:
                # 🛡️ 按 resample 颗粒度加锁，允许 日/周/月 线同时并行扫描
                self._is_checking_resamples.add(resample)
                can_submit = True
                
        if can_submit:
             # [OPTIMIZE] 核心性能优化：仅过滤受监控股票的子集进行策略检查
             with self._lock:
                 target_codes = list(self._monitored_stocks.keys())
                 
             if target_codes:
                 # 🛡️ [PERF OPTIMIZE] 延迟到 _check_strategies 内部进行 index 转换和 intersection
                 # 这里只提交任务，最大限度减少主线程/刷新线程的停顿
                 self.executor.submit(self._check_strategies, df_internal, target_codes, resample=resample)
             else:
                 with self._lock:
                     if resample in self._is_checking_resamples:
                         self._is_checking_resamples.remove(resample)

        # 1. 交易期间判断: 0915 至 1502
        is_trading = cct.get_work_time_duration()

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

        # --- ⭐ 数据反馈与回显 (Enrich df_all for UI) ---
        # 🛡️ [OPTIMIZE] 批量收集更新，最小化锁持有时间，防止 UI 线程在 acquire 时卡住
        updates_data = []
        with self._lock:
            monitored_list = list(self._monitored_stocks.items())
        
        # 1. 锁外收集数据
        for key, stock in monitored_list:
            code = stock.get('code', key.split('_')[0])
            if code in df_all.index:
                snap = stock.get('snapshot', {})
                # 收集非空核心字段
                updates_data.append((code, {
                    'last_action': snap.get('last_action', ''),
                    'last_reason': snap.get('last_reason', ''),
                    'shadow_info': snap.get('shadow_info', ''),
                    'market_win_rate': snap.get('market_win_rate', 0.5),
                    'loss_streak': snap.get('loss_streak', 0),
                    'vwap_bias': snap.get('vwap_bias', 0.0)
                }))

        # 2. 锁内极速批量回填
        if updates_data:
            try:
                if self._df_lock:
                     self._df_lock.acquire()
                
                # [OPTIMIZE] 批量更新列 (比循环 .at 快 10x)
                # 使用 .loc[indexes, column] = values 实现向量化回填
                for col in ['last_action', 'last_reason', 'shadow_info', 'market_win_rate', 'loss_streak', 'vwap_bias']:
                    vals_dict = {code: fields.get(col) for code, fields in updates_data if col in fields}
                    if vals_dict:
                        df_all.loc[list(vals_dict.keys()), col] = list(vals_dict.values())

            finally:
                if self._df_lock:
                     self._df_lock.release()

        # [REMOVED] DataHubService publish logic
        pass

    def _scan_hot_concepts(self, df: pd.DataFrame | None, concept_top5: list[Any], resample: str = 'd'):
        """
        扫描五大热点板块，识别龙头（增强版）
        """
        # import removed
        global MAX_DAILY_ADDITIONS
        if not self.scan_hot_concepts_status:
            return
        
        try:
            if df is None:
                if hasattr(self, 'master') and self.master:
                    df = getattr(self.master, 'df_all', None)
            
            if df is None or df.empty or not concept_top5:
                return

            # --- [NEW] 每日黑名单自动重置逻辑 (由于 is_blacklisted 已经处理了日期，这里只需确保不爆炸) ---
            # 如果需要显示所有窗口记录，则只需在 add_to_blacklist 时记录日期即可。

            # 此时 df 已确定为 pd.DataFrame
            target_df: pd.DataFrame = df

            # Extract concept names - [OPTIMIZATION] 严格限制在前 5 个核心热点板块
            top_concepts = set()
            for item in concept_top5[:5]:  # 👈 严格限制前5
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
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            
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
                
                # --- [NEW] 黑名单拦截 ---
                if self.is_blacklisted(code):
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
                    
                    # --- 定量评分系统 (Enhanced: 10日波动 + 回踩优先) ---
                    score = 0.0
                    score_reasons = []
                    
                    # 1. 涨幅贡献 (0 - 0.2)
                    pct = float(row.get('percent', 0.0)) # type: ignore
                    if pct > 3:
                        score += min(pct / 15, 0.2)
                        score_reasons.append(f"涨{pct:.1f}%")
                    
                    # 2. 量能贡献 (0 - 0.15)
                    vol = float(row.get('volume', 0.0)) # type: ignore
                    if 1.5 <= vol <= 3.0:
                        score += 0.15
                        score_reasons.append(f"量{vol:.1f}")
                    elif 1.2 <= vol < 1.5:
                        score += 0.08
                    elif vol > 3.0:
                        score += 0.05 # 天量减分
                    elif vol < 0.8:
                        score -= 0.1 # 地量减分
                    
                    # 3. ⭐ 10日波动评估 (0 - 0.3) - 重点关注大幅波动个股
                    try:
                        high_10d = float(row.get('high10', row.get('hmax', 0)))
                        low_10d = float(row.get('low10', row.get('lmin', 0)))
                        if high_10d > 0 and low_10d > 0:
                            amplitude_10d = (high_10d - low_10d) / low_10d
                            if amplitude_10d > 0.25:  # 振幅>25%
                                score += 0.3
                                score_reasons.append(f"振{amplitude_10d:.0%}")
                            elif amplitude_10d > 0.15:  # 振幅>15%
                                score += 0.2
                                score_reasons.append(f"振{amplitude_10d:.0%}")
                            elif amplitude_10d > 0.10:  # 振幅>10%
                                score += 0.1
                    except: pass
                    
                    # 4. ⭐ 回踩形态评估 (0 - 0.25) - 回踩更有价值
                    try:
                        curr = float(row.get('trade', row.get('close', 0)))  # 使用实时价格
                        ma5 = float(row.get('ma5d', 0))
                        ma10 = float(row.get('ma10d', 0))
                        ma20 = float(row.get('ma20d', 0))
                        low_today = float(row.get('low', curr))
                        high_today = float(row.get('high', curr))
                        open_price = float(row.get('open', curr))
                        
                        if curr > 0 and ma5 > 0:
                            # 回踩MA5后反弹 (低点触及MA5附近，收盘站上)
                            ma5_touch = abs(low_today - ma5) / ma5 < 0.02  # 低点在MA5±2%
                            ma5_recover = curr > ma5  # 收盘站上MA5
                            if ma5_touch and ma5_recover:
                                score += 0.25
                                score_reasons.append("踩MA5")
                            
                            # 回踩MA10后反弹
                            elif ma10 > 0:
                                ma10_touch = abs(low_today - ma10) / ma10 < 0.02
                                ma10_recover = curr > ma10
                                if ma10_touch and ma10_recover:
                                    score += 0.2
                                    score_reasons.append("踩MA10")
                            
                            # 回踩MA20后反弹
                            elif ma20 > 0:
                                ma20_touch = abs(low_today - ma20) / ma20 < 0.03
                                ma20_recover = curr > ma20
                                if ma20_touch and ma20_recover:
                                    score += 0.15
                                    score_reasons.append("踩MA20")
                    except: pass
                    
                    # 5. ⭐ 早盘低点反弹评估 (0 - 0.3) - 新增
                    try:
                        # import removed
                        now_time = datetime.datetime.now().time()
                        morning_session = datetime.time(9, 30) <= now_time <= datetime.time(11, 30)
                        
                        curr = float(row.get('trade', row.get('close', 0)))
                        low_today = float(row.get('low', curr))
                        high_today = float(row.get('high', curr))
                        open_price = float(row.get('open', curr))
                        
                        if curr > 0 and low_today > 0 and high_today > low_today:
                            # 计算当前价格在今日区间的位置
                            day_range = high_today - low_today
                            if day_range > 0:
                                position_ratio = (curr - low_today) / day_range
                                
                                # 早盘低点反弹：低点接近开盘价下方，当前价格已反弹
                                if morning_session:
                                    # 判断是否早盘探底
                                    low_below_open = low_today < open_price * 0.98  # 低点比开盘低2%+
                                    bounced_from_low = position_ratio > 0.5  # 已从低点反弹50%+
                                    
                                    if low_below_open and bounced_from_low:
                                        score += 0.3
                                        score_reasons.append(f"早盘低点反弹{position_ratio:.0%}")
                                    elif bounced_from_low:
                                        score += 0.15
                                        score_reasons.append(f"反弹{position_ratio:.0%}")
                                
                                # 全天判断：接近低点但开始反弹
                                else:
                                    near_low = position_ratio < 0.3  # 在低位30%区间
                                    starting_bounce = curr > low_today * 1.01  # 已离开最低点1%+
                                    
                                    if near_low and starting_bounce:
                                        score += 0.2
                                        score_reasons.append(f"低位{position_ratio:.0%}")
                    except: pass
                    
                    # 6. 连阳趋势加分 (0 - 0.1)
                    wc_val = row.get('win', 0)
                    win_count = int(wc_val) if not pd.isna(wc_val) else 0
                    if win_count >= 3:
                        score += 0.1
                        score_reasons.append(f"连阳{win_count}")
                    
                    # 7. 突破新高加分 (0 - 0.1)
                    hmax = float(row.get('hmax', 0)) # type: ignore
                    curr = float(row.get('close', 0)) # type: ignore
                    if hmax > 0 and curr > hmax:
                        score += 0.1
                        score_reasons.append("破高")
                    
                    # ⭐ 动态门槛：早盘适当放宽
                    # import removed
                    now_time = datetime.datetime.now().time()
                    is_morning = datetime.time(9, 30) <= now_time <= datetime.time(10, 30)
                    threshold = 0.5 if is_morning else 0.6
                    
                    # 过滤低分候选
                    if score < threshold:
                        continue
                    
                    hma5d = float(row.get('ma5d', 0.0)) # type: ignore
                    hma10d = float(row.get('ma10d', 0.0)) # type: ignore
                    logger.info(f"HotScan: {code} {stock_name} score={score:.2f} [{','.join(score_reasons)}] ma5={hma5d:.2f}")
                    
                    start_price = float(row.get('trade', row.get('close', 0.0)))
                    # 添加到候选列表
                    candidates.append({
                        'code': code,
                        'name': row.get('name', code),
                        'score': round(score, 2),
                        'concept': concept_name,
                        'pct': pct,
                        'price': start_price,
                        'reasons': '|'.join(score_reasons)
                    })
            
            # 按分数从高到低排序
            candidates.sort(key=lambda x: x['score'], reverse=True)
            
            # 选取前 N 名进行添加 (每策略最多5只)
            slots_remaining = min(5, MAX_DAILY_ADDITIONS - added_today_count)
            
            for cand in candidates[:slots_remaining]:
                # ⭐ 提高门槛: 评分 >= 0.6 才进入监控
                if cand['score'] >= 0.6:
                    self.add_monitor(
                        code=str(cand['code']),
                        name=cand['name'],
                        rule_type='hot_concept',
                        value=cand['score'],
                        tags=f"Hot:{cand['concept']}|Sc:{cand['score']:.2f}",
                        resample=resample,
                        create_price=cand['price'] # ✅ 修复：正确传入加入时的价格
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

    def _has_anomaly_pattern(self, row: Any) -> tuple[bool, str]:
        """
        检测是否具有异动特征 (Restore from 9ce1a1d)
        
        异动特征包括：
        1. 低开高走：开盘 < 昨收 且 收盘 > 开盘 且 涨幅 > 1%
        2. 高开高走：开盘 > 昨收+1% 且 收盘接近最高 且 涨幅 > 2%
        3. 冲高回落收新高：最高 > 昨收+3% 且 收盘 < 最高 但 收盘价 > 昨收+1%
        4. 多日十字星缩量：连阳后回踩 + 十字星形态 + 缩量
        
        Returns:
            (has_anomaly, anomaly_type): 是否有异动特征及类型
        """
        try:
            price = float(row.get('trade', row.get('close', 0)))
            open_p = float(row.get('open', 0))
            high = float(row.get('high', 0))
            # low = float(row.get('low', 0))
            lastp1d = float(row.get('lastp1d', 0))
            p_val = float(row.get('percent', 0))
            volume = float(row.get('volume', 0)) # volume ratio or normalized volume
            w_val = row.get('win', 0)
            win = int(w_val) if not pd.isna(w_val) else 0
            
            if price <= 0 or lastp1d <= 0:
                return False, ""
            
            # 1. 低开高走：开盘 < 昨收 * 0.99 且 收盘 > 开盘 且 涨幅 > 1.0
            is_low_open_high_close = (open_p < lastp1d * 0.99) and (price > open_p) and (p_val > 1.0)
            if is_low_open_high_close:
                return True, "低开高走"
            
            # 2. 高开高走：开盘 > 昨收 * 1.01 且 收盘 > 开盘 * 0.98 且 涨幅 > 2.0
            is_high_open_high_close = (open_p > lastp1d * 1.01) and (price > open_p * 0.98) and (p_val > 2.0)
            if is_high_open_high_close:
                return True, "高开高走"
            
            # 3. 冲高回落收新高：最高 > 昨收 * 1.03 且 收盘 < 最高 * 0.98 且 涨幅 > 1.0
            surge_ratio = (high - lastp1d) / lastp1d if lastp1d > 0 else 0
            is_surge_pullback_new_high = (surge_ratio > 0.03) and (price < high * 0.98) and (p_val > 1.0)
            if is_surge_pullback_new_high:
                return True, "冲高回落收新高"
            
            # 4. 多日回踩收十字星缩量：连阳后回踩 + 十字星形态 + 缩量
            body_ratio = abs(price - open_p) / price if price > 0 else 1
            is_doji = body_ratio < 0.01  # 十字星：实体<1%
            is_shrink_volume = volume < 0.8  # 缩量 (Assumption: 'volume' is volume ratio)
            is_after_rally = win >= 2  # 此前连阳
            if is_doji and is_shrink_volume and is_after_rally:
                return True, "多日十字星缩量"
            
            return False, ""
        except Exception as e:
            logger.debug(f"Anomaly pattern check error: {e}")
            return False, ""

            # --- 2. 低开高走 ---
            # 逻辑：开盘杀跌跌破昨收，但随后收复并大幅走高 (阳线实体大)
            is_low_open_high_close = (open_p < lastp1d * 0.995) and (price > open_p) and (p_val >= 1.0)
            if is_low_open_high_close:
                return True, "低开高走"
            
            # --- 3. 高开高走 ---
            # 逻辑：开盘即在昨收1%以上，且价格始终维持在高位 (不补缺口或不深踩)
            is_high_open_high_close = (open_p > lastp1d * 1.01) and (price > high * 0.98) and (p_val >= 2.0)
            if is_high_open_high_close:
                return True, "高开高走"
            
            # --- 4. 冲高回落强势维持 (归集之前策略) ---
            # 逻辑：最高涨幅一度很大(>=3%)，虽小幅回吐但仍维持在强势区间(>=1.0%)
            surge_ratio = (high - lastp1d) / lastp1d if lastp1d > 0 else 0
            if surge_ratio >= 0.03 and price > high * 0.97 and p_val >= 1.0:
                return True, "强势维持"
            
            # --- 5. 多日缩量窄幅形态 (蓄势模式) ---
            # 逻辑：此前有温和放量连阳(win>=2)，当前实体极小(<1%)且量能极度萎缩(<0.8)
            body_ratio = abs(price - open_p) / price if price > 0 else 1
            if win >= 2 and body_ratio < 0.01 and volume < 0.8:
                return True, "蓄势窄幅缩量"

            return False, ""
        except Exception as e:
            logger.debug(f"Anomaly pattern hub error: {e}")
            return False, ""

    @with_log_level(LoggerFactory.INFO)
    def _scan_rank_for_follow(self, df: pd.DataFrame, concept_top5: list = None, top_n: int = 100) -> None:
        """
        扫描板块联动强势突破股，筛选可跟单标的加入队列 (Restore from 9ce1a1d)
        
        核心筛选逻辑:
        1. 板块联动: 属于当日热点板块 (concept_top5) 的龙头股
        2. 连阳加速: win > 2 表示连续阳线，形态处于加速启动阶段
        3. 回踩启动: 价格回踩 MA5/MA10 后反弹启动
        4. 强势突破: 突破 hmax (历史高点) 或 high4 (4日高点)
        """
        if df is None or df.empty:
            return
        
        try:
            hub = get_trading_hub()
            # import removed
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            
            # 获取今日已入队的股票代码
            existing_queue = hub.get_follow_queue_df()
            queued_today = set()
            if not existing_queue.empty:
                queued_today = set(existing_queue[existing_queue['detected_date'] == today_str]['code'])
            
            # 获取热点板块集合
            top_concepts = set()
            if concept_top5:
                for item in concept_top5:
                    if isinstance(item, (list, tuple)):
                        top_concepts.add(str(item[0]))
                    else:
                        top_concepts.add(str(item))
            
            candidates = []
            
            for code, row in df.iterrows():
                code_str = str(code).zfill(6)
                
                # 跳过今日已入队 / 已在监控的
                if code_str in queued_today or code_str in self._monitored_stocks:
                    continue
                
                # 获取所属板块
                category = str(row.get('category', ''))
                stock_cats = set(category.split(';')) if category else set()
                matched_concepts = stock_cats.intersection(top_concepts)
                
                # --- [CORE] 严格过滤：仅处理热门板块个股 ---
                if not matched_concepts:
                    continue
                
                sector_match = list(matched_concepts)[0]
                
                # 获取关键指标
                price = float(row.get('close', row.get('trade', 0)))
                high = float(row.get('high', 0))
                low = float(row.get('low', 0))
                open_p = float(row.get('open', 0))
                lastp1d = float(row.get('lastp1d', 0))
                
                ma5 = float(row.get('ma5d', 0))
                ma10 = float(row.get('ma10d', 0))
                percent = float(row.get('percent', 0))
                win_val = row.get('win', 0)
                win = int(win_val) if win_val is not None and not pd.isna(win_val) else 0
                volume = float(row.get('volume', 0)) # volume ratio or normalized volume
                
                if price <= 0 or open_p <= 0 or lastp1d <= 0:
                    continue
                
                # ========== 信号判定 (逻辑组合) ==========
                signal_type = ""
                priority = 0
                
                # 1. 异动模式专项检测
                has_anomaly, anomaly_type = self._has_anomaly_pattern(row)
                if has_anomaly:
                    signal_type = anomaly_type
                    priority = 10
                
                # 2. 回踩均线启动 (均线支撑 + 放量)
                # 逻辑: 最低价曾触及 MA5/MA10 且 现价站稳上方 且 涨幅 > 2%
                is_ma5_bounce = (low <= ma5 * 1.01) and (price > ma5) and (percent > 2.0)
                is_ma10_bounce = (low <= ma10 * 1.01) and (price > ma10) and (percent > 2.0)
                has_volume = (volume > 1.2) # 量比 > 1.2
                
                if not signal_type:
                    if is_ma5_bounce and has_volume:
                        signal_type = "回踩MA5启动"
                        priority = 7
                    elif is_ma10_bounce and has_volume:
                        signal_type = "回踩MA10启动"
                        priority = 6
                
                if not signal_type:
                    continue
                
                # --- [NEW] 无大幅回撤结构检测 ---
                # 逻辑：现价必须在今日波动区间的 80% 以上，即回撤不能超过振幅的 20%
                day_range = high - low
                if day_range > 0:
                    pullback_ratio = (high - price) / day_range
                    if pullback_ratio > 0.2:
                        continue # 回撤过大，不符合“强势跟随”模式

                # 连阳加分
                if win >= 2:
                    priority += 2
                
                # 构造候选者信息
                candidates.append({
                    'code': code_str,
                    'name': str(row.get('name', code_str)),
                    'signal_type': signal_type,
                    'priority': priority,
                    'price': price,
                    'sector': sector_match,
                    'source': f"HotSectorFollow", 
                    'daily_patterns': f"{signal_type}|Win:{win}"
                })

            # 按优先级排序
            candidates.sort(key=lambda x: x['priority'], reverse=True)
            
            added_count = 0
            for cand in candidates[:10]:  # 每批最多加 10 只
                # ⭐ [NEW] Fast-Track 机制：如果属于极致强势的异动信号 (priority >= 10) 且有热点支持，允许盘中直接跟单！
                if cand['priority'] >= 10:
                    try:
                        # 对于超强信号，尝试模拟构造一个 TrackingSignal 进行直接突击，如果 Hub 支持会写入 DB
                        # 兼容老版直接 push
                        sig = dict(
                            code=cand['code'],
                            name=cand['name'],
                            signal_type=cand['daily_patterns'], # 形态透传
                            detected_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            detected_price=cand['price'],
                            entry_strategy="日内动能突袭", # 标识特殊来源
                            status="TRACKING",
                            priority=cand['priority'],
                            source=cand['source'],
                            notes="Fast-Track 日内强势直通"
                        )
                        
                        # 尝试通过 HUB 标准 TrackedSignal 格式增加
                        from trading_hub import TrackedSignal
                        track_sig = TrackedSignal(**sig)
                        hub.add_to_follow_queue(track_sig)
                        
                        # 🚀 [NEW] 同时触发总线报警，确保信号看板实时可见
                        # 使用明确的 action 和包含 "突破" 的 message 以触发正确的分类
                        self._trigger_alert(
                            code=cand['code'], 
                            name=cand['name'], 
                            message=f"🚀 [Fast-Track] 极强异动突破, 直通实盘跟单: {cand['daily_patterns']}",
                            action="突破/跟单",
                            price=cand['price'],
                            score=float(cand['priority'])
                        )
                        
                        logger.info(f"🚀 [Fast-Track] 盘中极强信号直接进入实盘跟单队列: {cand['code']} {cand['name']}")
                    except Exception as e:
                        logger.error(f"Failed to fast-track {cand['code']}: {e}")
                else:
                    # ⭐ 改造：常规信号进入 watchlist 进行跨日验证
                    try:
                        if hub.add_to_watchlist(
                            code=cand['code'],
                            name=cand['name'],
                            sector=cand['sector'],
                            price=cand['price'],
                            source=cand['source'],
                            daily_patterns=cand['daily_patterns']
                        ):
                            added_count += 1
                            logger.info(f"📋 写入热股观察队列: {cand['code']} {cand['name']} [{cand['signal_type']}]")
                    except Exception as e:
                        logger.error(f"Failed to add watchlist item {cand['code']}: {e}")

            if added_count > 0:
                logger.info(f"✅ 今日自动写入 {added_count} 只热点观察股，等待跨日验证")
        
        except ImportError:
            logger.debug("TradingHub not available, skip sector follow scan")
        except Exception as e:
            logger.error(f"Error in _scan_rank_for_follow: {e}")

    def _daily_watchlist_validation(self, df: pd.DataFrame):
        """
        [Phase 3] 每日热股跨日验证调度
        """
        try:
            hub = get_trading_hub()
            # 1. 构造验证所需的 OHLC 数据字典
            ohlc_data = {}
            for code, row in df.iterrows():
                code_str = str(code).zfill(6)
                ohlc_data[code_str] = {
                    'close': float(row.get('close', 0)),
                    'high': float(row.get('high', 0)),
                    'low': float(row.get('low', 0)),
                    'open': float(row.get('open', 0)),
                    'ma5': float(row.get('ma5d', 0)),
                    'ma10': float(row.get('ma10d', 0)),
                    'upper': float(row.get('upper', 0)),
                    'high4': float(row.get('high4', 0)),
                    'volume_ratio': float(row.get('volume', 0)) if float(row.get('volume', 0)) <= 500 else 1.0,  # >500为原始成交量,非量比
                    'win': int(row.get('win', 0)),
                }
            
            # 2. 调用验证引擎
            results = hub.validate_watchlist(ohlc_data)
            
            # 3. 产生语音播报
            if results['validated']:
                self.voice_announcer.announce(f"热股跨日验证完成，{len(results['validated'])}只标的通过验证，已晋升跟单。")
            
            # 4. 执行晋升（写入 follow_queue）
            hub.promote_validated_stocks()
            self._watchlist_validated_today = True
            
        except Exception as e:
            logger.error(f"Error in _daily_watchlist_validation: {e}")


    @with_log_level(LoggerFactory.INFO)
    def _process_follow_queue(self, df: pd.DataFrame, resample='d'):
        """
        [Phase 2] 处理跟单队列：支持竞价、回踩、突破等多种策略
        """
        if not self.follow_queue_cache:
            return

        # 仅在日线周期检查
        if resample != 'd':
            return
            
        from JohnsonUtil import commonTips as cct
        is_work_day = cct.get_day_istrade_date() # Check if today is a trading day
        now_time = datetime.datetime.now()
        current_time_str = now_time.strftime("%H:%M:%S")
        
        # 严格校验：必须是交易日 + 指定时段
        is_auction_time = is_work_day and ("09:25:00" <= current_time_str <= "09:30:00")
        is_trading_time = is_work_day and (("09:30:05" <= current_time_str <= "11:30:00") or \
                           ("13:00:00" <= current_time_str <= "14:57:00"))
            
        for signal in list(self.follow_queue_cache): # Iterate copy to allow removal
            code = signal.code
            if code not in df.index:
                continue
            
            try:
                row = df.loc[code]
                current_price = float(row.get('trade', 0.0))
                if current_price <= 0: continue
                
                entry_strategy = str(signal.entry_strategy)
                status = str(signal.status)
                triggered = False
                trigger_msg = ""
                
                # --- [NEW] D. 持仓 T+交易监控 (ENTERED 状态) ---
                if status == 'ENTERED' and is_trading_time:
                    high = float(row.get('high', 0.0))
                    pre_close = float(row.get('lastp1d', 0.0))
                    if current_price > 0 and pre_close > 0:
                        high_pct = (high - pre_close) / pre_close * 100
                        current_pct = (current_price - pre_close) / pre_close * 100
                        
                        # 冲高回落检测：曾涨 > 5% 且回落在 2% 以下
                        if high_pct > 5.0 and current_pct < 2.0:
                            msg = "冲高回落，建议反向做T减仓。"
                            self._trigger_alert(code, signal.name, msg, action="卖出", price=current_price)
                            logger.info(f"⚠️ [HoldingWarn] {code} {signal.name} 冲高回落: high={high_pct:.1f}% curr={current_pct:.1f}%")
                        
                        # 趋势走弱检测：跌破 MA5
                        ma5 = float(row.get('ma5d', 0.0))
                        if ma5 > 0 and current_price < ma5:
                            msg = "跌破5日线，建议止盈或控制仓位。"
                            self._trigger_alert(code, signal.name, msg, action="止盈", price=current_price)
                            logger.info(f"⚠️ [HoldingWarn] {code} {signal.name} 跌破MA5: curr={current_price:.2f} ma5={ma5:.2f}")

                # [NEW] 交由 T1 引擎进行自动化 T+0 加减仓策略审核 (去弱留强 / 震荡高抛低吸)
                if hasattr(self, 't1_engine') and self.t1_engine and is_trading_time: # Only evaluate T+0 during trading hours
                    cost_price = signal.entry_price if hasattr(signal, 'entry_price') and signal.entry_price > 0 else current_price
                    pos_info = {'entry_price': cost_price}
                    
                    # [NEW] 定义 snap 为 T1 引擎所需，优先从监控快照中获取，否则从当前行构造
                    snap = {}
                    monitored = self._monitored_stocks.get(code)
                    if monitored and 'snapshot' in monitored:
                        snap = monitored['snapshot']
                    else:
                        # 兜底：从 row 构造
                        snap = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
                        if 'lastp1d' in snap: snap['last_close'] = snap['lastp1d']
                        if hasattr(signal, 'entry_price'): snap['cost_price'] = signal.entry_price

                    t1_action, t1_reason, t1_target = self.t1_engine.evaluate_t0_signal(
                        code, row, snap, pos_info
                    )
                    if t1_action != 'HOLD':
                        # [NEW] 针对 T+1 做 T+0 的单日次级防线：同向交易每日限一次 (重点卡死 ADD)
                        allow_trade = True
                        act_name = "加仓(T0买)" if t1_action == 'ADD' else "去弱留强减仓(T0卖)"
                        
                        if t1_action == 'ADD':
                            # 查重：今天是否已经做过多单加仓？
                            trades_today = self.trading_logger.get_today_trades()
                            for t in trades_today:
                                if t['code'] == code and t.get('action') and "加仓" in t['action']:
                                    allow_trade = False
                                    logger.debug(f"⚠️ [T+1 Guard] {code} 今日已触发过加仓，受限单日锁，忽略本次 ADD 信号: {t1_reason}")
                                    break
                                    
                        if allow_trade:
                            # 防止同一股票反复触发同一类型的自动交易，使用专用缓存机制冷却
                            import time
                            sig_key = f"{code}_T0_{t1_action}"
                            last_ts = self._t0_cooldowns.get(sig_key, 0.0)
                            now_ts = time.time()
                            
                            if now_ts - last_ts > 1800: # 半小时冷却
                                self._trigger_alert(code, signal.name, t1_reason, action=t1_action, price=current_price)
                                logger.info(f"🔄 [T+1 Auto] {code} {signal.name} 触发 {t1_action}: {t1_reason}")
                                
                                # 全自动化执行日志切分
                                self._execute_t0_trade(code, signal.name, act_name, current_price, t1_reason)
                                self._t0_cooldowns[sig_key] = now_ts
                
                if status == 'ENTERED': # Original continue for ENTERED status, now after T+0 logic
                    continue # 持仓股已处理完监控，跳过买入触发逻辑

                # --- [NEW] 针对 VALIDATED 股票的属性注入与增强 ---
                is_validated = (status == 'VALIDATED')
                # 跨日验证通过的个股，如果是竞价买入策略且早盘，放宽部分过滤条件（或保留最高优先级）
                
                # --- A. 竞价策略 ---
                if "竞价" in entry_strategy and is_auction_time:
                    # VALIDATED 股票具备更高的 Alpha 加持
                    triggered, trigger_msg = self._check_auction_conditions(code, row)
                    if not triggered and is_validated:
                        # 如果没触发但具备强验证，可以考虑微调逻辑（此处保持同步）
                        pass
                
                # --- B. 盘中策略 (回踩/突破/形态) ---
                elif is_trading_time:
                    # [Logic remains similar but with status awareness]
                    if "回踩" in entry_strategy:
                        triggered, trigger_msg = self._check_pullback_conditions(code, row)
                    elif "突破" in entry_strategy or "平台" in entry_strategy:
                        triggered, trigger_msg = self._check_breakout_conditions(code, row, signal)
                    elif "V型" in entry_strategy:
                        triggered, trigger_msg = True, "V型反转确认"
                    elif "蓄势" in entry_strategy:
                        open_p = float(row.get('open', 0))
                        if current_price > open_p:
                            triggered, trigger_msg = True, f"蓄势启动确认 (现价 > 开盘)"
                
                # --- C. 通用目标价突破 ---
                target_high = float(getattr(signal, 'target_price_high', 0.0) or 0.0)
                if not triggered and target_high > 0 and current_price >= target_high:
                    triggered = True
                    trigger_msg = f"突破目标价 {target_high}"

                if triggered:
                    if is_validated: trigger_msg = f"[强体验证] {trigger_msg}"
                    # 执行跟单交易逻辑 (增加最大持仓限制: 5只)
                    trades_info = self.trading_logger.get_trades()
                    open_trades = [t for t in trades_info if t['status'] == 'OPEN']
                    if len(open_trades) < 5:
                        self._execute_follow_trade(signal, current_price, trigger_msg, resample)
                    else:
                        limit_msg = f"跟单触发，但持仓已满({len(open_trades)}/5)，跳过买入。"
                        logger.warning(f"⚠️ [Capacity Full] {code} {signal.name} {trigger_msg} - {limit_msg}")
                        # self.voice_announcer.announce(f"{signal.name} {limit_msg}", code=code)
            
            except Exception as e:
                logger.error(f"Process follow queue error {code}: {e}")

    def _check_auction_conditions(self, code: str, row: Any) -> tuple[bool, str]:
        """
        标准化竞价检查逻辑
        """
        current_price = float(row.get('trade', 0.0))
        pre_close = float(row.get('lastp1d', 0.0))
        volume = float(row.get('volume', 0.0))
        
        pct = (current_price - pre_close) / pre_close * 100 if pre_close > 0 else 0
        
        # [Strategy Tuning] 竞价高开 0.5% ~ 7.5%，且要求一定的成交额
        if not (0.5 <= pct <= 7.5 and volume >= 200):
            return False, ""

        # --- [NEW] 强力竞价核心过滤：高开标的必须带有“强结构” (Open=Low) ---
        if hasattr(self, 'pattern_detector') and pct >= 2.0:
            # 这里的 row 是当前行情快照
            patterns = self.pattern_detector.update(
                code=code, name=str(row.get('name','')), tick_df=None, 
                day_row=row, prev_close=pre_close
            )
            has_strong = any(p.pattern == 'strong_auction_open' for p in patterns)
            
            vol_val = volume
            vol_int = int(vol_val) if not pd.isna(vol_val) else 0
            if not has_strong:
                msg = f"竞价高开{pct:.1f}%但缺乏强结构支撑 (需Open≈Low且TrendS>60)"
                logger.debug(f"Reject follow entry for {code}: {msg}")
                return False, msg
            
            return True, f"强力竞价确认: 高开{pct:.2f}% 量{vol_int} (具备强结构)"

        
            
        # Shadow Engine record for near misses
        if 0 <= pct <= 10.0:
            try:
                # import removed
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                SignalMessageQueue().push(SignalMessage(
                    priority=99, timestamp=now_str, code=code, name=str(row.get('name', '')),
                    signal_type="SHADOW_AUCTION", source="Live",
                    reason=f"Gap:{pct:.1f}% Vol:{int(volume) if not pd.isna(volume) else 0}", score=pct
                ))
            except: pass
            
        return False, ""

    def _check_pullback_conditions(self, code: str, row: Any) -> tuple[bool, str]:
        """
        标准化回踩检查逻辑 (MA5/MA10)
        """
        current_price = float(row.get('trade', 0.0))
        ma5 = float(row.get('ma5d', 0.0))
        if ma5 <= 0: return False, ""
        
        bias = (current_price - ma5) / ma5
        if -0.012 <= bias <= 0.012: # 偏离度在 1.2% 以内
            return True, f"成功回踩MA5 (P={current_price:.2f}, MA5={ma5:.2f})"
        return False, ""

    def _check_breakout_conditions(self, code: str, row: Any, signal: Any) -> tuple[bool, str]:
        """
        标准化突破检查逻辑
        """
        current_price = float(row.get('trade', 0.0))
        name = str(row.get('name', ''))
        
        # 1. 突破信号设定的具体目标价
        target_high = float(getattr(signal, 'target_price_high', 0.0) or 0.0)
        if target_high > 0:
            if current_price >= target_high:
                msg = f"突破目标上限 {target_high}"
                # [P7] 突破确认高优先级播报
                self.voice_announcer.announce(f"{name}({code}) 突破确认", code=code)
                return True, msg
            
        # 2. 突破今日高点 (如果当前就是高点且涨幅够)
        high = float(row.get('high', 0.0))
        pct = float(row.get('percent', 0.0))
        if current_price >= high and pct > 3.0:
            msg = f"日内新高突破 ({pct:.1f}%)"
            # [P7] 突破确认高优先级播报
            self.voice_announcer.announce(f"{name}({code}) 强势突破", code=code)
            return True, msg
            
        return False, ""


    def _execute_follow_trade(self, signal: 'TrackedSignal', price: float, reason: str, resample: str = 'd'):
        """
        [P3] 执行跟单交易: 记录+上监控+报警
        """
        code = signal.code
        name = signal.name
        
        try:
            # 1. 记录交易 (模拟成交流程)
            # 默认仓位 10% (可后续优化为动态计算)
            # 如果是 "竞价买入"，通常是开盘价，但此时 price 可能是昨收或虚拟开盘价
            # 真实交易中应等待 9:30 确认，但为了不错过，我们记录意向
            
            # 使用 PhaseEngine 计算初始仓位 (如有)
            initial_pos_ratio = 0.1 
            
            self.trading_logger.record_trade(
                code, name, "买入", price, 0, # amount=0 (indicates simulator/tracker)
                reason=f"[{signal.entry_strategy}] {reason}",
                resample=resample
            )
            
            # 2. 更新 Hub 状态
            hub = get_trading_hub()
            hub.update_follow_status(code, "ENTERED", notes=f"Executed at {price}: {reason}")
            
            # 3. 加入实时监控 (Hotspot Injection Logic)
            # 构造监控数据结构
            # import removed
            monitor_data = {
                "name": name,
                "code": code,
                "resample": resample,
                "last_alert": 0,
                "created_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tags": f"auto_followed_{signal.entry_strategy}",
                "snapshot": {
                    "score": 99, # High score for followed signal
                    "reason": reason,
                    "buy_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                    "cost_price": price,
                    "highest_since_buy": price,
                    # Initialize Phase
                    "trade_phase": "ACCUMULATE" if "回踩" in signal.entry_strategy else "LAUNCH"
                },
                "rules": [
                    # 默认止损规则
                    {"type": "price_down", "value": price * (1 - self._stop_loss_pct)}
                ]
            }
            
            with self._lock:
                self._monitored_stocks[key] = monitor_data
            self._save_monitors()
            
            # 4. 移除待跟单队列缓存
            if signal in self.follow_queue_cache:
                self.follow_queue_cache.remove(signal)
                
            # 5. 报警联动
            action_text = "自动买入"
            # msg = f"{action_text}: {name} ({code}) 价格:{price} 理由:{reason}"
            self._trigger_alert(code, name, f"{action_text} 理由:{reason}", action=action_text, price=price)
            logger.info(f"✅ [Trade Executed] {name} ({code}) 价格:{price} 理由:{reason}")
            
        except Exception as e:
            logger.error(f"Execute trade failed {code}: {e}")

    def _publish_market_heartbeat(self, df: pd.DataFrame):
        """
        📊 基于 DailyPulseEngine 的专业算法发布实时全场统计心跳
        """
        try:
            # 1. 实例缓存与延迟加载
            if not hasattr(self, '_pulse_engine'):
                # 注意：DailyPulseEngine 的参数是 stock_selector
                self._pulse_engine = DailyPulseEngine(getattr(self, 'selector', None))
            
            engine = self._pulse_engine
            
            # 2. 实时热度提取 (全场向量化统计)
            if df.empty: return
            
            up_count = len(df[df['percent'] > 0])
            down_count = len(df[df['percent'] < 0])
            breadth = {'up_ratio': up_count / max(1, up_count + down_count)}
            
            # --- [PRO] 情感指标实时提取 ---
            # 强势个股占比 (涨幅 > 5%)。如果没有 score 列，则以此作为 Sentiment 的代理。
            if 'score' in df.columns:
                ready_pct = (len(df[df['score'] > 80]) / len(df) * 100)
            else:
                ready_pct = (len(df[df['percent'] > 4.5]) / len(df) * 100)
            
            # --- [PRO] 板块指标实时提取 ---
            # 提取涨幅前列的板块强度均值
            sector_heat = 0.0
            if 'category' in df.columns:
                 # 获取涨幅前 100 标的所属板块的估算热度
                 top_sectors = df.sort_values(by='percent', ascending=False).head(100)['category'].dropna().tolist()
                 # 简单逻辑：如果前 100 个股中有 30% 属于某一热门群落，则 heat 显著增加 (这里简化为 top 股票平均涨幅)
                 sector_heat = df.sort_values(by='percent', ascending=False).head(50)['percent'].mean()
            
            # 3. 调用 Engine 专业计算 (逻辑共享)
            indices = engine._get_index_status()
            temp_val, status_str = engine.calculate_professional_temperature(
                ready_pct=ready_pct, sector_heat=sector_heat, breadth=breadth, indices=indices
            )
            summary = engine.get_summary_text_by_temp(temp_val)
            
            stats = {
                "up": up_count, 
                "down": down_count, 
                "flat": len(df) - up_count - down_count,
                "temperature": round(temp_val, 1),
                "summary": summary, 
                "indices": indices,
                "ready_count": int(ready_pct * len(df) / 100)
            }
            # 4. 发布到总线
            bus = get_signal_bus()
            bus.publish(BusEvent.EVENT_HEARTBEAT, "market_stats", stats)
            
        except Exception as e:
            logger.debug(f"Professional Heartbeat error: {e}")

    def _execute_t0_trade(self, code: str, name: str, action: str, price: float, reason: str, resample: str = 'd'):
        """
        [NEW] 执行 T+0 加减仓: 仅记录交易信号流日志，并不直接平仓整个头寸
        """
        try:
            self.trading_logger.record_trade(
                code, name, action, price, 0,
                reason=f"[T+1系统] {reason}",
                resample=resample
            )
            # Notify observer/UI
            logger.info(f"✅ [T+0 Executed] {name} ({code}) {action} 价格:{price} 理由:{reason}")
            # Optional: Add specific marker to SQLite target DB if necessary
            
            # [FIX] 仅当 UI 开启了可视化开关时才发送 IPC，避免无效消耗与 GIL 线程冲突
            if self.master and getattr(self.master, "_vis_enabled_cache", False):
                if action == '加仓(T0买)':
                    sig_type = "T0_BUY"
                else:
                    sig_type = "T0_SELL"
                msg_data = {"code": code, "name": name, "price": price, "pattern": sig_type, "msg": reason, "time": datetime.datetime.now().strftime("%H:%M:%S")}
                send_signal_to_visualizer_ipc(msg_data)
        except Exception as e:
            logger.error(f"Execute T+0 trade failed {code}: {e}")

    # =========================
    # ✅ 主函数（最终稳定版）
    # =========================
    def _check_strategies(self, df_all_data: pd.DataFrame, target_codes: list, resample: str = 'd') -> None:
        """
        [CORE] 核心多线程策略扫描引擎 (并行化重构 v2.3)
        """
        # 🛡️ 状态位已在 process_data 锁内提前设置，此处无需再次检查
        try:
            # --- 🛡️ [HEAVY PREP MOVED HERE] ---
            # 在子线程内进行耗时的索引转换和过滤，释放调用者/UI 线程
            if df_all_data.index.dtype != object:
                # 只在必要时 copy 和转换
                df_all_data = df_all_data.copy()
                df_all_data.index = df_all_data.index.astype(str)
            
            # 使用传入的监控代码进行交集过滤
            matched_idx = df_all_data.index.intersection(target_codes)
            df = df_all_data.loc[matched_idx]
            
            if df.empty:
                logger.debug(f"[_check_strategies] resample={resample} No matched codes found in current DF.")
                return

            start_loop_timer = time.perf_counter()
            # 1. 环境准备与归一化快照
            now, now_ts_str = time.time(), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._lock:
                monitored_snapshot = dict(self._monitored_stocks)
            valid_keys = [k for k in monitored_snapshot.keys() if monitored_snapshot[k].get('resample', 'd') == resample]
            
            logger.info(f"🎯 [ENGINE] _check_strategies started. Monitors={len(monitored_snapshot)} Matched={len(df)} Resample={resample}")
            
            # 2. RR 轮换分发逻辑 (Full-Dimensional Static Memory Fix)
            if not hasattr(StockLiveStrategy, "_kline_rr_cursors_static"):
                StockLiveStrategy._kline_rr_cursors_static = {} # {resample: cursor}
            if not hasattr(StockLiveStrategy, "_kline_rr_pools_static"):
                StockLiveStrategy._kline_rr_pools_static = {}   # {resample: list}
            
            # 获取当前周期的独立池子与游标
            res_pool = StockLiveStrategy._kline_rr_pools_static.get(resample, [])
            res_cursor = StockLiveStrategy._kline_rr_cursors_static.get(resample, 0)
            
            # 池子同步判定 (按周期独立)
            if len(res_pool) != len(valid_keys):
                res_pool = list(valid_keys)
                StockLiveStrategy._kline_rr_pools_static[resample] = res_pool
                res_cursor %= max(len(res_pool), 1) # 对齐尺寸
                logger.info(f"🔄 [RR Sync] resample={resample}, pool size={len(res_pool)}, cursor={res_cursor}")
            
            pool, pool_size = res_pool, len(res_pool)
            if pool_size > 0:
                start = res_cursor
                max_fetch = getattr(self, 'max_fetch_kline', 30)
                end = start + max_fetch
                fetch_list = (pool[start:end] if end <= pool_size else pool[start:] + pool[:(end - pool_size)])
                
                # 存回当前周期的独立游标
                StockLiveStrategy._kline_rr_cursors_static[resample] = end % pool_size
                logger.info(f"🔍 [RR_STATUS] PoolSize({resample})={pool_size} Cursor={start} FetchCount={len(fetch_list)}")
            else:
                fetch_list = []

            # 3. 批量环境数据抓取 (全量预取以消除 Worker 阻塞)
            all_emotion_scores, all_klines, all_loss_streaks, open_trades = {}, {}, {}, {}
            if fetch_list:
                try:
                    # 🚀 [OPTIMIZATION] 移除串行更新历史缓存，将其移至 Worker 并行执行
                    # if hasattr(self, '_update_daily_history_cache'):
                    #    for key in fetch_list:
                    #        code_idx = key.split('_')[0]
                    #        self._update_daily_history_cache(code_idx, resample)
                    
                    # 🚀 [PERF] 同步 55188 全量数据: 移出循环，每批次仅执行一次
                    all_55188 = {}
                    if self.realtime_service:
                        try:
                            ext_status = self.realtime_service.get_55188_data() # 获取全量字典
                            if isinstance(ext_status, dict):
                                df_ext = ext_status.get('df')
                                if df_ext is not None and not df_ext.empty:
                                    all_55188 = df_ext.to_dict(orient='index')
                        except Exception: pass

                    if self.realtime_service:
                        all_emotion_scores = self.realtime_service.get_emotion_scores(fetch_list)
                        if hasattr(self.realtime_service, 'get_batch_minute_klines'):
                            all_klines = self.realtime_service.get_batch_minute_klines(fetch_list, n=30)
                            
                    db_codes = [str(k.split('_')[0]) for k in fetch_list]
                    all_loss_streaks = self.trading_logger.get_batch_consecutive_losses(db_codes, resample=resample)
                    hub = get_trading_hub()
                    trades_info = hub.get_open_trades(resample=resample)
                    open_trades = {(str(t['code']), t.get('resample', 'd')): t for t in trades_info}
                except Exception as e_prep:
                    logger.debug(f"📊 [PREP_ERROR] Data sync partially failed: {e_prep}")

            # 4. 并发任务分发
            signal_batch, status_batch, alert_items = [], [], []
            import concurrent.futures
            futures, submitted_count = {}, 0
            for key in fetch_list:
                try:
                    code_idx = key.split('_')[0]
                    if code_idx in df.index:
                        futures[self.executor.submit(
                            self._detect_signals_single_stock, 
                            key, df.loc[code_idx].to_dict(), monitored_snapshot[key],
                            all_emotion_scores, all_klines, all_loss_streaks, 
                            open_trades, all_55188, resample, now, now_ts_str
                        )] = key
                        submitted_count += 1
                except Exception as e_dispatch:
                    logger.debug(f"Task submission error for {key}: {e_dispatch}")
            
            logger.info(f"🚀 [DISPATCH] Submitted {submitted_count} / Goal {len(fetch_list)}")

            # 5. 结果收集与同步 (并发结果落地)
            if futures:
                try:
                    import concurrent.futures
                    for future in concurrent.futures.as_completed(futures, timeout=25):
                        try:
                            res = future.result()
                            if not res: continue
                            key, code = res['key'], res['code']
                            
                            # 更新内存快照
                            with self._lock:
                                if key in self._monitored_stocks:
                                     # 🛡️ [FIX] 安全更新 snapshot，确保 key['snapshot'] 存在
                                     target_stock = self._monitored_stocks[key]
                                     if 'snapshot' not in target_stock:
                                         target_stock['snapshot'] = {}
                                     
                                     if res.get('snapshot_updates'):
                                         target_stock['snapshot'].update(res['snapshot_updates'])
                                     
                                     if 'last_alert' in res:
                                         target_stock['last_alert'] = res['last_alert']
                            
                            # 🚀 [NEW] 集中的结果归集与状态更新 (同步 UI 视图子集)
                            if res.get('df_updates'):
                                try:
                                    for col, val in res['df_updates'].items():
                                        df.at[code, col] = val
                                except Exception: pass

                            if res.get('signal_item'): signal_batch.append(res['signal_item'])
                            if res.get('status_item'): status_batch.append(res['status_item'])
                            
                            # 🚀 [NEW] 处理 DB 异步同步 (主线程非阻塞执行)
                            if res.get('db_sync_note'):
                                 try:
                                     hub_sync = get_trading_hub()
                                     hub_sync.update_follow_status(res['code'], notes=res['db_sync_note'])
                                 except: pass

                        except Exception as e_res:
                            logger.error(f"Future result processing failed: {e_res}")

                except concurrent.futures.TimeoutError:
                    unfinished_keys = [futures[f] for f in futures if not f.done()]
                    logger.error(f"❌ [ENGINE_TIMEOUT] _check_strategies TIMEOUT: {len(unfinished_keys)} (of {len(futures)}) futures unfinished. Suspects: {unfinished_keys[:10]}...")
                    for f in futures: 
                        if not f.done(): f.cancel()
                except Exception as e_outer:
                    logger.error(f"❌ [ENGINE_COLLECT] Collection loop error: {e_outer}")

            # 6. 原子写入与同步报警 (性能指标结算)
            cost_loop_ms = (time.perf_counter() - start_loop_timer) * 1000
            if cost_loop_ms > 1000:
                logger.warning(f"🚀 [OPTIMIZED] loop_total_execution cost={cost_loop_ms/1000:.2f} s for {len(valid_keys)} stocks (submitted={submitted_count})")

            if signal_batch: self.trading_logger.log_signal_batch(signal_batch)
            if status_batch: self.trading_logger.log_status_batch(status_batch)

        except Exception as e:
            logger.error(f"🚨 [ENGINE_CRITICAL] _check_strategies failed: {e}")
        finally:
            # 🛡️ 最终任务结束，释放并行状态位
            with self._lock:
                if resample in self._is_checking_resamples:
                    self._is_checking_resamples.remove(resample)
            
            # --- [NEW] 10轮一报汇总逻辑 (Performance Optimized) ---
            self._data_check_rounds += 1
            if self._data_check_rounds >= 10:
                with self._data_exception_lock:
                    if self._data_exceptions:
                        exc_items = list(self._data_exceptions.items())
                        count = len(exc_items)
                        if count > 5:
                            summary = "\n".join([f"• {code}: {reason}" for code, reason in exc_items[:5]])
                            logger.warning(f"⚠️ [Data-Exception] 集中数据异常(共{count}只):\n{summary}\n...等其它{count-5}只数据缺失")
                        else:
                            summary = "\n".join([f"• {code}: {reason}" for code, reason in exc_items])
                            logger.warning(f"⚠️ [Data-Exception] 发现数据异常:\n{summary}")
                        self._data_exceptions.clear()
                self._data_check_rounds = 0






    # =========================
    # 🚨 单股处理（核心）
    # =========================
    def _detect_signals_single_stock(self, key, row, data, all_emotion_scores, all_klines, all_loss_streaks, open_trades, all_55188, resample, now, now_ts_str):

        code = data.get('code', key.split('_')[0])
        if row is None:
            return None


        # ---------- 历史 snapshot 与 持仓同步 ----------
        snap = data.get('snapshot', {})

        # [FIX] 提前初始化 res 字典，防止状态机逻辑 (Phase Engine) 提前引用报错 (res referenced before assignment)
        res = {
            'key': key,
            'code': code,
            'snapshot_updates': snap,
            'alert_payload': None,
            'messages': [],
            'last_alert': data.get('last_alert', 0),
            'signal_item': None,
            'status_item': None,
            'db_sync_note': None  # 🚀 预留数据库同步备注
        }

        

        # =========================
        # 🔥 messages链（关键）
        # =========================
        # messages = []
        messages = []  # [Fix] 提前初始化 messages，供日/日内形态检测使用
        
        # =========================
        # ✅ 批量注入（必须）
        # =========================
        snap['loss_streak'] = all_loss_streaks.get(code, 0)
        snap['rt_emotion'] = all_emotion_scores.get(code, 50)
    
        # ---------- 安全获取行情数据 ----------
        try:
            current_price = float(row.get('trade', 0.0))
            current_nclose = float(row.get('nclose', 0.0))
            current_change = float(row.get('percent', 0.0))
            volume_change = float(row.get('volume', 0.0))
            if volume_change > 1000: volume_change = 1.0 # 防御处理
            ratio_change = float(row.get('ratio', 0.0))
            current_high = float(row.get('high', 0.0))
            
            # --- [NEW] 数据异常检测: 行情无效 ---
            if current_price == 0 or current_nclose == 0:
                with self._data_exception_lock:
                    self._data_exceptions[code] = "行情无效(Price=0)"
        except (ValueError, TypeError) as e:
            with self._data_exception_lock:
                self._data_exceptions[code] = f"行情异常({str(e)})"
            return
        
        trade_key = (code, resample)
        if trade_key in open_trades:
            trade = open_trades[trade_key]
            snap['cost_price'] = trade.get('buy_price', 0)
            snap['buy_date'] = trade.get('buy_date', '')
            snap['buy_reason'] = trade.get('buy_reason', '')
            if current_price > float(snap.get('highest_since_buy', 0.0)): # type: ignore
                snap['highest_since_buy'] = current_price

        # 注入加速连阳与五日线强度数据
        snap['win'] = row.get('win', snap.get('win', 0)) #加速连阳
        snap['sum_perc'] = row.get('sum_perc', snap.get('sum_perc', 0)) #加速连阳涨幅
        snap['red'] = row.get('red', snap.get('red', 0)) #五日线上数据
        snap['gren'] = row.get('gren', snap.get('gren', 0)) #弱势绿柱数据
        
        # --- [NEW] 注入 win_upper 状态用于起跳探测 ---
        snap['win_upper1'] = row.get('win_upper1', snap.get('win_upper1', 0))
        snap['win_upper2'] = row.get('win_upper2', snap.get('win_upper2', 0))
        

        # --- 实时情绪与形态注入 (Realtime Signal Injection) ---
        # 使用预取的批量情绪分
        rt_emotion = all_emotion_scores.get(code, 0)
        snap['rt_emotion'] = rt_emotion
        
        if self.realtime_service:
            try:
                # 2. 注入 V 型反转信号 (保持单条，因为检测逻辑较重且目前无批量接口)
                v_shape = self.realtime_service.get_v_shape_signal(code)
                snap['v_shape_signal'] = v_shape
                if v_shape:
                    logger.debug(f"⚡ {code} 触发 V 型反转信号")
                    
                # 3. 注入 55188 外部数据 (人气、主力、题材)
                ext_55188 = all_55188.get(code)
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
                    # --- [NEW] 数据异常检测: 外部实时数据缺失 ---
                    with self._data_exception_lock:
                        existing = self._data_exceptions.get(code, "")
                        self._data_exceptions[code] = f"{existing}, 55188缺失" if existing else "55188缺失"
                    snap['hot_rank'] = 999
                    snap['zhuli_rank'] = 999
                    snap['net_ratio_ext'] = 0
                    snap['sector_score'] = 0.0
            except Exception as e:
                logger.error(f"Realtime Service Injection Error for {code}: {e}")

        # --- ⭐ 日内形态检测 ---
        if hasattr(self, 'pattern_detector'):
            try:
                prev_close = float(row.get('lastp1d', 0))
                self.pattern_detector.update(
                    code=code,
                    name=data.get('name', ''),
                    tick_df=None, # [FIX] 显式传递 None 满足签名要求
                    # tick_df 为 None 时，内部通常会尝试 from day_row 获取必要字段
                    day_row=row,
                    prev_close=prev_close
                )
            except Exception as e:
                logger.debug(f"Pattern detect error for {code}: {e}")

        # --- 📅 日线形态检测 ---
        if hasattr(self, 'daily_pattern_detector'):
            try:
                self._update_daily_history_cache(code,resample) # 尝试刷新全量缓存
                prev_rows = self.daily_history_cache.get(f'{code}_{resample}')
                
                # --- [NEW] 数据异常检测: 历史K线缓存缺失 ---
                if prev_rows is None or prev_rows.empty:
                    with self._data_exception_lock:
                        existing = self._data_exceptions.get(code, "")
                        self._data_exceptions[code] = f"{existing}, 历史缓存缺失" if existing else "历史缓存缺失"
                
                snap['day_df'] = prev_rows # [NEW] 供决策引擎进行顶部检测
                det_events = self.daily_pattern_detector.update(
                    code=code,
                    name=data.get('name', ''),
                    current_row=row,
                    prev_rows=prev_rows
                )
                
                if det_events:
                    for ev in det_events:
                        # 构造 "PATTERN" 类型的消息，放入 messages 以便最后统一去重播报
                        # 格式: (type, content)
                        msg_content = f"[日线]: {ev.detail}"
                        messages.append(("PATTERN", msg_content))
                        
                        # 同时确保 trading_hub 更新 (虽然 callback 里也有，但双重保险无害，或者考虑移除 callback 中的 update)
                        try:
                            hub = get_trading_hub()
                            hub.update_follow_status(ev.code, notes=f"[{ev.pattern}] {ev.detail}")
                        except: pass

            except Exception as e:
                logger.debug(f"Daily pattern detect error for {code}: {e}")

        # --- 注入板块与系统风险状态 ---
        # 从 _last_sector_status 中获取
        sector_status = getattr(self, '_last_sector_status', {})
        pullback_alerts = sector_status.get('pullback_alerts', [])
        snap['systemic_risk'] = sector_status.get('risk_level', 0)
        
        # 获取该股票所属板块的风险
        stock_sector = snap.get('theme_name', '')
        if not stock_sector and 'category' in row:
                cats = str(row['category']).split(';')
                if cats: 
                    stock_sector = cats[0]
                else:
                    # --- [NEW] 数据异常检测: 板块识别失败 ---
                    with self._data_exception_lock:
                        existing = self._data_exceptions.get(code, "")
                        self._data_exceptions[code] = f"{existing}, 板块数据缺失" if existing else "板块数据缺失"

        for p_sector, p_code, p_drop in pullback_alerts:
            # check if self is leader
            if str(p_code) == str(code):
                snap['sector_leader_pullback'] = p_drop
            # check if sector leader is pulling back (follow-on risk)
            if stock_sector and p_sector == stock_sector:
                snap['sector_leader_pullback'] = p_drop
        
        # --- 注入日线中轴趋势数据 (Daily Midline Trend) ---
        try:
            # 昨中轴
            last_h = float(row.get('last_high', 0))
            last_l = float(row.get('last_low', 0))
            if last_h > 0 and last_l > 0:
                snap['yesterday_midline'] = (last_h + last_l) / 2
            else:
                # --- [NEW] 数据异常检测: 历史高低价缺失 ---
                with self._data_exception_lock:
                    existing = self._data_exceptions.get(code, "")
                    self._data_exceptions[code] = f"{existing}, 昨高低缺失" if existing else "昨高低缺失"
                snap['yesterday_midline'] = float(row.get('last_close', 0)) # fallback

            # 前中轴
            last2_h = float(row.get('last2_high', 0))
            last2_l = float(row.get('last2_low', 0))
            if last2_h > 0 and last2_l > 0:
                snap['day_before_midline'] = (last2_h + last2_l) / 2
            else:
                # --- [NEW] 数据异常检测: 前日高低价缺失 ---
                with self._data_exception_lock:
                    existing = self._data_exceptions.get(code, "")
                    self._data_exceptions[code] = f"{existing}, 前高低缺失" if existing else "前高低缺失"
                snap['day_before_midline'] = snap['yesterday_midline'] # fallback

            # 今日实施中轴 (动态)
            if current_high > 0:
                    current_low = float(row.get('low', 0))
                    if current_low > 0:
                        snap['today_midline'] = (current_high + current_low) / 2
            
            # 简单的趋势判断标记
            if snap.get('yesterday_midline', 0) < snap.get('day_before_midline', 0):
                snap['midline_falling'] = True
            else:
                snap['midline_falling'] = False
                
            if snap.get('yesterday_midline', 0) > snap.get('day_before_midline', 0):
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
        # 1. 记仇机制：使用预取的亏损次数 (O(1))
        snap['loss_streak'] = all_loss_streaks.get(code, 0)
        
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

        # --- 🛸 批量注入全量 K 线数据 (分钟级别) ---
        snap['klines'] = all_klines.get(key, [])

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
            # import removed
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            if snap['buy_date'].startswith(today_str):
                is_t1_restricted = True

        # messages = [] # Moved to top of loop

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
                messages.append(("RISK", f"卖出 价格连续低于今日均价 {current_nclose} ({current_price})"))

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
                messages.append(("RISK", f"减仓 价格连续低于昨日收盘 {last_close} ({current_price})"))

        # ---------- 上下文趋势分析 (Context Analysis) ----------
        open_p = float(row.get('open', 0.0))
        trend_prefix = ""
        trend_suffix = ""
        
        if last_close > 0 and open_p > 0:
            open_ratio = (open_p - last_close) / last_close
            # 1. 低开走高 (价值形态)
            if open_ratio <= -0.01 and current_price > open_p:
                if current_nclose > 0 and current_price > current_nclose:
                    trend_prefix = "【低开走高】"
                else:
                    trend_prefix = "【低开反弹】"
            # 2. 高开低走 (风险形态)
            elif open_ratio >= 0.01 and current_price < open_p:
                trend_prefix = "【高开低走】"
        
        # 3. 均线状态
        if current_nclose > 0:
                if current_price < current_nclose:
                    trend_suffix += " | 均线压制"
                else:
                    trend_suffix += " | 站稳均线"

        # 4. 昨高突破 (关键多头信号)
        lasthigh = float(row.get('lasthigh', 0.0))
        if lasthigh > 0:
            if current_price > lasthigh:
                trend_suffix += " | 🚀突破昨高"
            elif (lasthigh - current_price) / lasthigh < 0.01:
                trend_suffix += " | 逼近昨高"

        # ---------- 普通规则 ----------
        for rule in data.get('rules', []):
            rtype, rval = rule['type'], rule['value']
            if (rtype == 'price_up' and current_price >= rval) or (rtype == 'price_down' and current_price <= rval) or (rtype == 'change_up' and current_change >= rval):
                # [Optimization] 动态修正动作描述
                action_str = "价格突破"
                if rtype == 'price_up':
                    if current_change < -9.5:
                        action_str = "触及跌停" # 修正跌停附近的向上波动
                    elif current_change < -2.0:
                        action_str = "弱势反抽" # 修正深跌中的反弹
                    else:
                        action_str = "价格突破"
                elif rtype == 'price_down':
                    action_str = "价格跌破"
                elif rtype == 'change_up':
                    action_str = "涨幅达到"
                
                msg = f"{trend_prefix}{action_str} {current_price} 涨幅 {current_change}% 量能 {volume_change} 换手 {ratio_change}{trend_suffix}"
                messages.append(("RULE", msg))

        # ---------- [NEW] 起跳新星探测逻辑 (win_upper 0 -> 1) ----------
        # 优化逻辑 (符合用户设计的起跳模式)：
        # 1. 结构确认: win_upper1 >= 1 (开始站稳压力位)
        # 2. 形态确认: 高开(>1%) 或 开盘即最低(影线<0.2%)
        # 3. 趋势确认: 相比开盘价不回落 (高走)
        # 4. 量能确认: 虚拟量比 > 1.2
        w_u1_val = row.get('win_upper1', 0)
        curr_win_u1 = int(w_u1_val) if not pd.isna(w_u1_val) else 0
        
        # 初始化单日触发标记 (snap 会随监控项持久化)
        if 'star_triggered_date' not in snap:
            snap['star_triggered_date'] = ""
        
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # 核心判定：必须要结构性起跳，且今日未在该周期触发过
        if curr_win_u1 >= 1 and snap['star_triggered_date'] != today_str:
            prev_close = float(row.get('lastp1d', 0.0))
            open_price = float(row.get('open', 0.0))
            low_price = float(row.get('low', 0.0))
            
            if prev_close > 0 and open_price > 0:
                # 指标 1: 高开高走 (高开1%以上且当前不低于开盘)
                is_high_open_walk = open_price > prev_close * 1.01 and current_price >= open_price
                
                # 指标 2: 最低价即开盘价 (影线极短 < 0.2% 视为“早盘最低高走”)
                is_open_is_low = (open_price - low_price) / open_price < 0.002 and current_price >= open_price
                
                # 形态评分辅助 (gem_score)
                gem_score = float(row.get('gem_score', row.get('gem_tops', 15.0)))
                
                # 综合触发条件: (高开高走 OR 开盘最低) 且 满足量能与基本基因分
                # 优化 [量能扩张结构]: 
                # 1. 虚拟量比 > 1.5 (基准门槛)
                # 2. 换手率 > 0.3% (防止微量启动)
                # 3. 量能趋势: 当前量比 > 前值 (扩量) 或 处于极端放量区 (>2.5)
                curr_vol_ratio = volume_change
                prev_vol_ratio = snap.get('last_star_vol', 0.0)
                snap['last_star_vol'] = curr_vol_ratio # 记录供下次比对
                
                is_vol_expanding = curr_vol_ratio > prev_vol_ratio or curr_vol_ratio > 2.5
                is_ratio_ok = ratio_change > 0.3
                
                if (is_high_open_walk or is_open_is_low) and curr_vol_ratio > 1.5 and is_vol_expanding and is_ratio_ok and gem_score > 12:
                    reason_star = "高开高走" if is_high_open_walk else "起跳最低点"
                    if curr_win_u1 == 1: reason_star = "首日" + reason_star
                    
                    msg_star = f"🌟 [起跳新星]: {reason_star}站稳压力位! 量能 {curr_vol_ratio:.1f} 基因 {gem_score:.1f}"
                    messages.append(("PATTERN", msg_star))
                    snap['star_triggered_date'] = today_str # 锁定记录，防轰炸
                    # ⭐ [FIX] 将频繁触发的日志降级为 DEBUG
                    logger.debug(f"🚀 BREAKOUT_STAR triggered: {code} {data['name']} | reason:{reason_star} vol:{curr_vol_ratio:.1f} (prev:{prev_vol_ratio:.1f}) ratio:{ratio_change} score:{gem_score:.1f}")
        
        # 维持原有状态链同步
        data['prev_win_upper1'] = curr_win_u1

        # --- 3. 实时情绪感知 & K线形态 (Realtime Analysis) ---
        if self.realtime_service:
            try:
                # --- 3.1 读取实时情绪 (来自批量脉冲缓存) ---
                rt_emotion = all_emotion_scores.get(code, 0)
                snap['rt_emotion'] = snap.get('rt_emotion', 0) + rt_emotion
            except Exception as e:
                logger.debug(f"rt_emotion fetch error: {e}")

            try:
                # 🚀 [PARALLEL] 在 Worker 内并行更新历史 K 线缓存 (不再串行排队)
                if hasattr(self, '_update_daily_history_cache'):
                    self._update_daily_history_cache(code_idx, resample)

                # --- 3.2 V-Shape K线形态 (来自批量脉冲缓存) ---
                klines = all_klines.get(code, [])
                
                # --- [NEW] 数据异常检测: K线缺失 ---
                if not klines:
                    with self._data_exception_lock:
                        existing = self._data_exceptions.get(code, "")
                        self._data_exceptions[code] = f"{existing}, K线缺失" if existing else "K线缺失"
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
                            
                            # [NEW] V_SHAPE 入队需配合异动特征
                            try:
                                # 检查是否有异动特征
                                has_anomaly, anomaly_type = self._has_anomaly_pattern(row)
                                if has_anomaly:
                                    hub = get_trading_hub()
                                    # import removed
                                    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
                                    ts = TrackedSignal(
                                        code=code, 
                                        name=data.get('name', ''),
                                        signal_type=f'V_SHAPE({anomaly_type})',
                                        detected_date=today_str,
                                        detected_price=p_curr,
                                        entry_strategy='回踩MA5',
                                        status='TRACKING',
                                        priority=9,
                                        source='RealTime',
                                        notes=f"V-Shape Drop:{drop:.1%} Rebound:{rebound:.1%} | {anomaly_type}"
                                    )
                                    hub.add_to_follow_queue(ts)
                                    logger.info(f"📋 V-Shape+异动入队: {code} ({anomaly_type})")
                                else:
                                    logger.debug(f"V-Shape {code} skipped: no anomaly pattern")
                            except Exception as e:
                                logger.error(f"Failed to add V-Shape to queue: {e}")
            except Exception as e:
                logger.debug(f"v_shape_check error: {e}")

        # 定义默认 shadow_decision，防止后续引用报错
        shadow_decision = {"action": "HOLD", "reason": "", "debug": {}}
        
        # ---------- 决策引擎 ----------
        # ---------- 决策引擎 ----------
        # --- [NEW] 数据异常检测: 决策输入合法性 ---
        required_cols = ['trade', 'percent', 'volume']
        missing_decision_data = [col for col in required_cols if pd.isna(row.get(col)) or row.get(col) == 0]
        if missing_decision_data:
            with self._data_exception_lock:
                existing = self._data_exceptions.get(code, "")
                self._data_exceptions[code] = f"{existing}, 决策数据缺失({','.join(missing_decision_data)})" if existing else f"决策数据缺失({','.join(missing_decision_data)})"

        decision = self.decision_engine.evaluate(row, snap)

        # --- [NEW] P0.6 仓位状态机逻辑 ---
        if self.phase_engine:
            try:
                # 1. 获取当前状态 (从 snap 恢复)
                # --- [NEW] 数据异常检测: 状态机数据真实性 ---
                if 'trade_phase' not in snap:
                    with self._data_exception_lock:
                        existing = self._data_exceptions.get(code, "")
                        self._data_exceptions[code] = f"{existing}, 状态机缺失" if existing else "状态机缺失"
                
                curr_phase_str = snap.get('trade_phase', 'IDLE')
                try:
                    curr_phase = TradePhase(curr_phase_str)
                except ValueError:
                    curr_phase = TradePhase.IDLE
                    
                # 2. 评估新状态
                new_phase, phase_reason = self.phase_engine.evaluate_phase(code, row, snap, curr_phase)
                
                # 3. 状态变更处理
                if new_phase != curr_phase:
                    # ⭐ [FIX] 状态变更日志降级为 DEBUG，减少终端干扰
                    logger.debug(f"🔄 [Phase Change] {code} {curr_phase.value} -> {new_phase.value} ({phase_reason})")
                    snap['trade_phase'] = new_phase.value
                    snap['phase_reason'] = phase_reason
                    
                    # Log change
                    messages.append(("RULE", f"状态变更: {curr_phase.value}->{new_phase.value} {phase_reason}"))
                    
                    # ⭐ [High Performance] 移除 Worker 内子线程，通过 res 返回同步指令
                    new_note = f"[{new_phase.value}] 状态变更"
                    res['db_sync_note'] = new_note
                    snap['phase_synced_ts'] = now
                    
                    # 如果是 EXIT，强制叠加卖出信号
                    if new_phase == TradePhase.EXIT:
                        decision['action'] = "卖出"
                        decision['reason'] = f"状态机离场: {phase_reason}"
                        decision['position'] = 0.0
                else:
                    # Periodic Sync (Heartbeat for Phase Visualization)
                    last_sync = snap.get('phase_synced_ts', 0)
                    if time.time() - last_sync > 60: # Every 60s
                        try:
                            hub = get_trading_hub()
                            new_note = f"[{new_phase.value}] 持仓续航"
                            hub.update_follow_status(code, notes=new_note)
                            snap['phase_synced_ts'] = time.time()
                        except Exception: pass

                # 4. 根据状态获取目标仓位
                target_pos_ratio = self.phase_engine.get_target_position(new_phase)
                snap['phase_target_pos'] = target_pos_ratio

            except Exception as e:
                logger.exception(f"Phase engine error {code}: {e}")
        
        # if decision['action'] != "HOLD":
        #    messages.append(("RULE", f"决策引擎建议 {decision['action']}: {decision['reason']}"))
            
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
        # import removed
        now_ts = datetime.datetime.now()
        if snap.get('last_trigger_time') is None:
            snap['last_trigger_time'] = now_ts - datetime.timedelta(minutes=cooldown_minutes)
            # logger.info(f'timedelta(minutes=cooldown_minutes): {datetime.timedelta(minutes=cooldown_minutes)}')
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
                        snap['last_trigger_time'] = now_ts + datetime.timedelta(minutes=10) 
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

        # --- 3.6 记录信号日志 (已通过 signal_batch 统一回写，此处仅保留逻辑意向) ---
        # self.trading_logger.log_signal(code, data.get('name', ''), current_price, decision, row_data=row_data)

        # --- ⭐ 将决策与监理感知回写至 snap (供 UI 同步使用) ---
        action = decision.get('action', 'HOLD')
        snap['last_action'] = action
        snap['last_reason'] = decision.get('reason', '')
        
        # [NEW] 信号持久化：如果是明确的买卖，固化为 last_signal 供跨日做T
        if action in ("买入", "BUY", "加仓", "ADD"):
            snap['last_signal'] = "BUY"
            snap['last_signal_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        elif action in ("卖出", "SELL", "止损", "止盈", "减仓"):
            snap['last_signal'] = "SELL"
            snap['last_signal_date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # [NEW] 记录结构分类到底层存储
        snap['structure_base_score'] = float(row.get('structure_base_score', 50.0))
        
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

        # --- [新增] 将 SNAP 中的关键策略状态同步 (由主线程统一处理或已包含在 snapshot_updates 中) ---
        # 注意: 此处 row 是 dict 拷贝，无法直接回写 df
        snap['df_updates'] = {
            'market_win_rate': snap.get('market_win_rate', 0.0),
            'loss_streak': snap.get('loss_streak', 0),
            'vwap_bias': snap.get('vwap_bias', 0.0),
            'last_action': snap.get('last_action', ''),
            'last_reason': snap.get('last_reason', ''),
            'shadow_info': snap.get('shadow_info', ''),
            'last_signal': snap.get('last_signal', 'HOLD'),
            'last_signal_date': snap.get('last_signal_date', ''),
            'structure_base_score': snap.get('structure_base_score', 50.0)
        }

        if decision["action"] not in ("持仓", "观望"):
            pos_val = decision.get("position", 0)
            # 防止 NaN 转换为整数失败
            if pd.isna(pos_val):
                pos_val = 0
            messages.append(("POSITION", f'{decision["action"]} 仓位{int(pos_val*100)}% {decision["reason"]}'))

        # 💥 [NEW] 提取指标并增强报警消息
        td_setup = decision["debug"].get("td_setup", 0)
        top_score = decision["debug"].get("top_score", 0.0)
        if td_setup >= 8:
            messages.append(("RULE", f"[Signal] TD序列: 已达到 {td_setup} (接近见顶风险)"))
        if top_score > 0.6:
            messages.append(("RISK", f"[Signal] 顶部风险评分: {top_score:.2f} (高位建议减仓)"))

        # ---------- 风控调整仓位 ----------
        action, ratio = self._risk_engine.adjust_position(data, decision["action"], decision["position"])
        if action and action not in ("持仓", "观望"):
            # 防止 NaN 转换失败
            if pd.isna(ratio):
                ratio = 0
            messages.append(("POSITION", f'[Risk] {action} 当前价 {current_price} 建议仓位 {ratio*100:.0f}%'))

        

        if messages:
            priority_order = ["RISK","RULE","POSITION","PATTERN"]
            # 🚀 [NEW] 按优先级级别排序 (RISK 优先于 RULE 优先于 POSITION 优先于 PATTERN)
            try:
                messages.sort(key=lambda x: priority_order.index(x[0]) if x[0] in priority_order else 99)
            except Exception: pass

            unique_msgs = []
            seen = set()
            for mtype,msg in messages:
                if isinstance(msg,pd.Series):
                    msg = msg.iloc[0] if not msg.empty else ""
                msg = str(msg)
                if msg not in seen:
                    seen.add(msg)
                    unique_msgs.append(msg)
            t1_prefix = "[T+1限制] " if is_t1_restricted else ""
            
            # 🚀 [NEW] 报警单独分发：确保每个信号在 UI 侧有独立的染色 sig_type
            # 此处直接循环触发，不再聚合为 combined_msgs 以修复颜色显示问题
            if isinstance(action,pd.Series):
                action = action.iloc[0] if not action.empty else "HOLD"
            
            for mtype, msg in messages:
                # 再次快速去重判定 (unique_msgs 已处理内容，此处直接过滤重复内容)
                if str(msg) in unique_msgs:
                    self._trigger_alert(
                        code,
                        data.get('name', ''),
                        f"{t1_prefix}{msg}",
                        action=str(action),
                        price=current_price,
                        resample=resample,
                        score=snap.get('score', snap.get('max_score_today', 0.0)),
                        grade=snap.get('grade', '')
                    )
            
            # 设置 signal_item 用于主引擎批量存储
            res['signal_item'] = {
                'code': code,
                'name': data.get('name', ''),
                'price': current_price,
                'decision': decision,
                'row_data': row_data,
                'resample': resample
            }
            # logger.info(f'{decision["action"]}')
            if decision["action"]  in ("VETO", "买入",'卖出'):
                # ⭐ [FIX] 移除或完全屏蔽此处的控制台输出，统一走 logging 管理
                # 如果需要查看，请在 logging 配置中开启 DEBUG
                pass
            data['last_alert'] = now
            # ⭐ [FIX] 不在单股循环内保存文件，改为设置标记
            self._needs_monitor_save = True
            data['below_nclose_count'] = 0
            data['below_nclose_start'] = 0
            data['below_last_close_count'] = 0

             # [Optimization] 完善结果返回给主引擎
            res.update({
                'snapshot_updates': snap,
                'last_alert': data.get('last_alert', 0),
                'db_sync_note': res.get('db_sync_note') # 保持状态机可能已注入的 note
            })
            
        return res


        # if not messages:
        #     logger.debug(f"{code} data: {messages}")
        # # ==========================================================
        # # 🚨🚨🚨【这里开始：粘贴你原来的全部策略逻辑】🚨🚨🚨
        # # ==========================================================
        # #
        # # 从你原来的：
        # #
        # #   current_price = float(row.get('trade', 0.0))
        # #
        # # 一直到：
        # #
        # #   self._trigger_alert(...)
        # #
        # # 👉 一行不删，全部粘进来
        # #
        # # 包括：
        # # - 风控计数
        # # - pattern detector
        # # - 中轴线
        # # - breakout
        # # - phase
        # # - decision_engine
        # # - shadow_engine
        # # - supervisor
        # # - messages.append(...)
        # #
        # # ==========================================================

        # # 示例占位（防止空逻辑报错，可删除）
        # decision = {"action": "HOLD", "reason": ""}

        # try:
        #     decision = self.decision_engine.evaluate(row, snap)
        # except Exception as e:
        #     logger.error(f"Decision error {code}: {e}")

        # try:
        #     is_vetoed, veto_reason = self.supervisor.veto(code, decision, row, snap)
        #     if is_vetoed:
        #         decision["action"] = "VETO"
        #         decision["reason"] = f"🛡️ {veto_reason}"
        # except Exception:
        #     pass

        # # =========================
        # # ✅ 冷却（必须在最后）
        # # =========================
        # if decision.get("action") != "HOLD" or messages:

        #     if now - data.get('last_alert', 0) < getattr(self, "_alert_cooldown", 0):
        #         return

        #     try:
        #         self._finalize_and_trigger_alerts(
        #             code,
        #             data,
        #             messages,
        #             decision,
        #             current_price,
        #             resample,
        #             snap
        #         )
        #     except Exception as e:
        #         logger.error(f"Alert error {code}: {e}")

        #     data['last_alert'] = now
        #     self._needs_monitor_save = True

        # # =========================
        # # ✅ UI同步（防丢显示）
        # # =========================
        # try:
        #     self._sync_to_df(code, snap)
        # except Exception:
        #     pass

    def _check_strategies_simple(self, df: pd.DataFrame) -> None:
        """ [DEPRECATED] 备份单线程扫描引擎 """
        try:
            now = time.time()
            for code, data in self._monitored_stocks.items():
                if code in df.index:
                    row = df.loc[code]
                    decision = self.decision_engine.evaluate(row, data.get('snapshot', {}))
                    if decision['action'] != 'HOLD':
                        self._trigger_alert(code, data.get('name', ''), decision['reason'])
        except Exception as e:
            logger.error(f"Simple scan engine failed: {e}")

    def get_monitors(self):
        """获取所有监控数据"""
        return self._monitored_stocks

    def sync_and_repair_monitors(self) -> dict:
        """
        同步监控列表到数据库,并修复缺失的价格信息。
        返回修复统计信息。
        """
        repair_count = 0
        sync_count = 0
        errors = []
        
        try:

            for key, data in self._monitored_stocks.items():
                code = data.get('code') or key.split('_')[0]
                resample = data.get('resample', 'd')
                name = data.get('name', '')
                create_price = data.get('create_price', 0)
                created_time_str = data.get('created_time', '')

                # 1. 尝试修复价格
                is_hot_concept = (data.get('rule_type_tag') == 'hot_concept') or ('Hot:' in data.get('tags', ''))
                
                # 策略：如果价格缺失、过低(可能为涨幅)或者是热点股，强制验证
                needs_check = (not create_price or create_price <= 0) or (create_price < 35) or is_hot_concept
                
                if needs_check and created_time_str:
                    try:
                        dt_obj = None
                        date_formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H', '%Y-%m-%d']
                        for fmt in date_formats:
                            try:
                                dt_obj = datetime.datetime.strptime(created_time_str, fmt)
                                break
                            except ValueError:
                                continue
                        
                        if dt_obj:
                            target_date = dt_obj.strftime('%Y-%m-%d')
                            dl = ct.Resample_LABELS_Days.get(resample, 200)
                            df_hist = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample=resample, fastohlc=True)
                            
                            if df_hist is not None and not df_hist.empty:
                                found_price = 0.0
                                if target_date in df_hist.index:
                                    row = df_hist.loc[target_date]
                                    if isinstance(row, pd.DataFrame): row = row.iloc[0]
                                    found_price = float(row.get('close', 0))
                                else:
                                    past_df = df_hist[df_hist.index <= target_date]
                                    if not past_df.empty:
                                        found_price = float(past_df.iloc[-1].get('close', 0))
                                    else:
                                        found_price = float(df_hist.iloc[0].get('open', 0))
                                
                                if found_price > 0:
                                    # 检测偏差：如果已有价格与历史价格偏差 > 10%，判定为错误并修复
                                    deviation = abs(create_price - found_price) / found_price if create_price > 0 else 1.0
                                    
                                    if create_price <= 0 or deviation > 0.1 or is_hot_concept:
                                        data['create_price'] = found_price
                                        create_price = found_price
                                        repair_count += 1
                                        logger.debug(f"Fixed price for {code}: {create_price} (Original: {data.get('create_price', 0)}, Dev: {deviation:.2%})")
                    except Exception as e:
                        errors.append(f"{code} repair error: {e}")

                # 2. 同步到数据库
                if hasattr(self, 'trading_logger'):
                    try:
                        self.trading_logger.log_voice_alert_config(
                            code=code,
                            resample=resample,
                            name=name,
                            rules=json.dumps(data.get('rules', [])),
                            last_alert=data.get('last_alert', 0),
                            tags=data.get('tags', ''),
                            rule_type_tag=data.get('rule_type_tag', ''),
                            create_price=create_price,
                            created_time=created_time_str
                        )
                        sync_count += 1
                    except Exception as e:
                        errors.append(f"{code} sync error: {e}")

            # 保存修复后的结果到配置文件
            self._save_monitors()
            
            return {
                "repair_count": repair_count,
                "sync_count": sync_count,
                "total": len(self._monitored_stocks),
                "errors": errors
            }
        except Exception as e:
            logger.error(f"Failed to sync and repair monitors: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"error": str(e)}

    def _resolve_stock_key(self, code: str) -> Optional[str]:
        """
        内部辅助：解析传入的代码/Key，返回存在于 _monitored_stocks 中的真实 Key。
        支持：纯代码 ("000001")、带周期的 Key ("000001_d")。
        """
        if code in self._monitored_stocks:
            return code
        
        # 尝试拆分
        parts = code.split('_')
        pure_code = parts[0]
        if pure_code in self._monitored_stocks:
            return pure_code
            
        # 尝试常用后缀 (兼容旧数据)
        for suffix in ['d', 'w', 'm', '3d', '5', '15', '30', '60']:
            alias = f"{pure_code}_{suffix}"
            if alias in self._monitored_stocks:
                return alias
        
        return None

    # ---------- 黑名单管理相关方法 ----------
    def _load_blacklist(self, date=None):
        """从数据库加载黑名单 (支持日期过滤)"""
        try:
            if hasattr(self, 'trading_logger'):
                data = self.trading_logger.get_blacklist_data(date=date)
                if date is None:
                    self._blacklist_data = data # 仅在全量加载时更新缓存
                return data
        except Exception as e:
            logger.error(f"Failed to load blacklist from DB: {e}")
            if date is None: self._blacklist_data = {}
        return {}

    def add_to_blacklist(self, code, name="", reason="manual_del"):
        """将代码加入黑名单"""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        # 1. 保存到数据库
        if hasattr(self, 'trading_logger'):
            self.trading_logger.add_to_blacklist(code, name, reason)
        
        # 2. 同步内存缓存
        if code in self._blacklist_data:
            hit_count = self._blacklist_data[code].get('hit_count', 0)
        else:
            hit_count = 0
            
        self._blacklist_data[code] = {
            "name": name,
            "date": today,
            "reason": reason,
            "hit_count": hit_count
        }
        
        logger.info(f"🚫 Added {name}({code}) to blacklist. Reason: {reason}")
        # 如果当前在监控中，顺便移除
        self.remove_monitor(code)

    def is_blacklisted(self, code):
        """检查代码是否在黑名单中 (当日有效)"""
        # 为了效率，优先检查内存
        if code not in self._blacklist_data:
            return False
        
        info = self._blacklist_data[code]
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        return info.get("date") == today

    def get_blacklist(self, date=None):
        """获取完整黑名单数据 (支持可选日期过滤)"""
        # 如果提供了日期，直接从 DB 查，不影响全局缓存
        if date and date != "全部":
            return self._load_blacklist(date=date)
            
        # 默认刷新并返回全量缓存
        self._load_blacklist() 
        return self._blacklist_data

    def remove_from_blacklist(self, code):
        """从黑名单移除 (恢复报警)"""
        found_in_memory = False
        if code in self._blacklist_data:
            del self._blacklist_data[code]
            found_in_memory = True
            
        success_in_db = False
        if hasattr(self, 'trading_logger'):
            success_in_db = self.trading_logger.remove_from_blacklist(code)
            
        if found_in_memory or success_in_db:
            logger.info(f"✅ Removed {code} from blacklist. Alerts restored.")
            return True
        return False

    def remove_monitor(self, code, resample=None):
        """移除指定代码的监控"""
        key = self._resolve_stock_key(code)
        if key:
            pure_code = key.split('_')[0]
            stock_resample = self._monitored_stocks[key].get('resample', 'd')
            
            # 1. 从内存移除
            with self._lock:
                if key in self._monitored_stocks:
                    del self._monitored_stocks[key]
            logger.info(f"Removed monitor {key} from memory")
            
            # 2. 从数据库物理删除
            if hasattr(self, 'trading_logger'):
                self.trading_logger.remove_voice_alert_config(pure_code, stock_resample)
                # 💥 [New] 如果是持仓股，还需要将交易状态标记为 CLOSED (或手动移除状态)，防止 load_monitors 自动恢复
                # 检查是否有 OPEN 状态的交易
                try:
                    trades = self.trading_logger.get_trades()
                    open_trades = [t for t in trades if t['code'] == pure_code and t['status'] == 'OPEN']
                    if open_trades:
                        for trade in open_trades:
                            # 这里我们不真正卖出，而是标记为 CLOSED (或者引入新的状态 MANUAL_REMOVED)
                            # 为了打断循环，我们调用 update_trade_status (需要 logger 支持，或者直接 close)
                            # 既然是移除监控，意味着不再关注，视为结束跟踪
                            self.trading_logger.close_trade(
                                code=pure_code, 
                                sell_price=0, 
                                sell_reason="手动移除监控(不再跟踪)",
                                sell_amount=0, # 0 表示仅修改状态
                                resample=trade.get('resample', 'd') # 👈 注入正确的周期，确保数据库更新生效
                            )
                        logger.info(f"Closed {len(open_trades)} trade records for {pure_code} to prevent auto-recovery")
                except Exception as e:
                    logger.error(f"Failed to close trade for {pure_code}: {e}")
            
            # 3. 中断当前及排队中的语音
            if hasattr(self, '_voice'):
                self._voice.cancel_for_code(pure_code)
                
            # 4. 从信号历史中移除相关品种 (可选优化：保持界面整洁)
            # self.signal_history = deque([s for s in self.signal_history if s.get('code') != pure_code], maxlen=200)

            self._save_monitors()
            return True
        else:
            logger.warning(f"Failed to remove monitor: {code} not found")
            return False


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
            open_trades = [t for t in trades if str(t['code']).zfill(6) == str(code).zfill(6) and t['status'] == 'OPEN' and t.get('buy_amount', 0) > 0]
            
            if open_trades:
                for t in open_trades:
                    t_resample = t.get('resample', 'd')
                    stock_name = name or t.get('name', 'Unknown')
                    # 执行卖出记录，使用对应的周期
                    self.trading_logger.record_trade(code, stock_name, "卖出", price, 0, reason="Manual/Auto Close", resample=t_resample)
                    logger.info(f"Auto-closed position for {code} ({stock_name}) at {price} [Resample: {t_resample}]")
                return True
        except Exception as e:
            logger.error(f"Error in close_position_if_any for {code}: {e}")
            
        return False

    def update_rule(self, code, rule_index, new_type, new_value):
        """更新指定规则"""
        key = self._resolve_stock_key(code)
        if key:
            rules = self._monitored_stocks[key]['rules']
            if 0 <= rule_index < len(rules):
                rules[rule_index]['type'] = new_type
                rules[rule_index]['value'] = float(new_value)
                self._save_monitors()
                logger.info(f"Updated rule for {key} index {rule_index}: {new_type} {new_value}")
                return True
        else:
            logger.warning(f"Failed to update rule: {code} not found")
        return False

    def remove_rule(self, code, rule_index):
        """移除指定规则"""
        key = self._resolve_stock_key(code)
        if key:
            stock = self._monitored_stocks[key]
            rules = stock['rules']

            if 0 <= rule_index < len(rules):
                rule = rules.pop(rule_index)
                pure_code = key.split('_')[0]
                stock_resample = stock.get('resample', 'd')

                if 'rule_keys' in stock:
                    stock['rule_keys'].discard(
                        self._rule_key(rule['type'], rule['value'])
                    )

                if not rules:
                    # 如果没规则了，整个监控项物理删除
                    del self._monitored_stocks[key]
                    if hasattr(self, 'trading_logger'):
                        self.trading_logger.remove_voice_alert_config(pure_code, stock_resample)
                    if hasattr(self, '_voice'):
                        self._voice.cancel_for_code(pure_code)
                    logger.info(f"Monitor {key} fully removed because no rules left")
                else:
                    logger.info(f"Removed rule {rule_index} for {key}")

                self._save_monitors()
                return True
        else:
            logger.warning(f"Failed to remove rule: {code} not found")
        return False


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
            dt_str = datetime.datetime.fromtimestamp(self._monitored_stocks[key]['last_alert']).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"😴 Snoozed alert for {key}  in {cycles} cycles ({cycles * self._alert_cooldown}s alert_cooldown: {self._alert_cooldown}s next_alert_time:{dt_str})")

    def _on_pattern_detected(self, event: 'PatternEvent') -> None:
        """形态检测回调 - 触发语音播报 (带计数和高优先级检测)"""
        # [CRITICAL] 严格限制仅在交易时间段触发 (09:15 - 15:05)
        now_int = cct.get_now_time_int()
        if not (915 <= now_int <= 1505):
            return

        try:
            # === 获取标准化信号信息 (增强扩展性) ===
            sig = getattr(event, 'signal', None)
            pattern_key = sig.subtype if sig else event.pattern
            pattern_cn = IntradayPatternDetector.PATTERN_NAMES.get(pattern_key, pattern_key)
            
            # 区分买点信号 vs 卖点信号
            action = "风险" if pattern_key in ('high_drop', 'top_signal', 'bull_trap_exit', 'momentum_failure') else "形态"
            
            # === 高优先级信号检测 (增强版) ===
            is_high_priority = event.is_high_priority
            high_priority_reason = ""
            
            # [NEW] 核心形态精选：低开高走、回踩上攻等必须满足严格条件
            ELITE_PATTERNS = {'low_open_high_walk', 'pullback_upper', 'open_is_low_volume', 'nlow_is_low_volume'}
            
            if pattern_key in ELITE_PATTERNS:
                # 尝试从实时数据中获取当前行情 (如果可用)
                try:
                    ratio = 0.0
                    if hasattr(self, 'df') and self.df is not None and not self.df.empty and event.code in self.df.index:
                        row = self.df.loc[event.code]
                        ratio = float(row.get('ratio', 0))  # 换手率
                    
                    # 使用 detector 生成的 detail 判断起点位置
                    detail = event.detail or ""
                    start_at_ma = "@MA" in detail or "@日低" in detail
                    has_volume = ratio > 3.0
                    
                    # [CRITICAL] 精选条件：必须同时满足起点+放量
                    if start_at_ma and has_volume:
                        is_high_priority = True
                        ma_level = "MA级别" if "@MA" in detail else "日低"
                        high_priority_reason = f"[HIGH] 起点{ma_level}，换手{ratio:.1f}%"
                        event.is_high_priority = True
                        # 仅对高优先级保留 INFO
                        logger.info(f"🔥 高优先级信号: {event.code} {event.name} - {high_priority_reason}")
                    elif start_at_ma:
                        # 从 MA 附近启动但换手不足，标记为中等优先级（仅语音，不弹窗）
                        is_high_priority = False  # [FIX] 不触发UI弹窗
                        high_priority_reason = f"[MID] 起点{detail.split('走高')[0].split('@')[1] if '@' in detail else 'MA'}，换手不足"
                        # 中等优先级降级为 DEBUG
                        logger.debug(f"⚠️ 中等优先级信号（仅语音）: {event.code} {event.name} - {high_priority_reason}")
                    else:
                        # 起点不佳，静默丢弃UI弹窗
                        is_high_priority = False
                        logger.debug(f"低质量信号（静默）: {event.code} {pattern_cn} - 起点不佳或换手不足")
                except Exception as e:
                    logger.debug(f"High priority check failed: {e}")
            
            # === 构建消息 (使用 detector 生成的 detail) ===
            count_suffix = f" (第{event.count}次)" if event.count > 1 else ""
            detail_msg = event.detail if event.detail else (sig.detail if sig else pattern_cn)
            msg = f"{event.name} {detail_msg}{count_suffix}"
            if high_priority_reason:
                msg = f"{msg} {high_priority_reason}"
            
            # === 日志记录 ===
            priority_tag = "🔥" if is_high_priority else "🔔"
            # [REDUCED] 统一通过 debug 记录，不再干扰 INFO 控制台
            logger.info(f"{priority_tag} 形态信号: {event.code} {event.name} - {detail_msg} @ {event.price:.2f}{count_suffix}")
            
            # === 语音播报控制 (增强版) ===
            # 策略调整:
            # 1. 所有信号都通过 _trigger_alert 处理 (确保DB记录+IPC推送)
            # 2. _trigger_alert 内部根据信号质量决定是否触发UI弹窗
            # 3. 语音播报由 _trigger_alert 统一处理
            
            should_voice = False
            
            if is_high_priority:
                should_voice = True
                msg = f"注意高优先级，{msg}"
            elif event.count == 1:
                should_voice = True
            elif event.count % 5 == 0:
                should_voice = True
                msg = f"{event.name} {pattern_cn} 已触发{event.count}次"
            
            # [FIX] 所有信号都通过 _trigger_alert 处理，确保仪表盘可见
            # 只有满足 should_voice 条件的才触发语音/弹窗，其余仅静默发布到总线
            self._trigger_alert(
                event.code, event.name, msg, 
                action=action, price=event.price, 
                score=getattr(event, 'score', 0.0),
                grade=getattr(event, 'grade', ''),
                silent=not should_voice  # [NEW] 非播报信号设为静默
            )


            
            # === [P7] 仓位状态机联动 ===
            if self.phase_engine:
                try:
                    # 🛡️ 此时仍在子线程，安全起见从 master 的锁保护下访问 df
                    # 或从 local 缓存抓取
                    row = pd.Series()
                    if hasattr(self, 'df') and self.df is not None:
                         # 🛡️ 尝试获取主数据引用
                         target_df = self.df
                         if event.code in target_df.index:
                             row = target_df.loc[event.code]
                    
                    if not row.empty:
                        # 触发状态机评估
                        new_phase = self.phase_engine.evaluate_phase(event.code, row, {"pattern": event.pattern})
                        
                        # 如果标记为 TOP_WATCH / EXIT，强化语音警报
                        if new_phase in (TradePhase.TOP_WATCH, TradePhase.EXIT):
                            msg = f"注意顶部风险: {event.name} ({event.code}) 阶段:{new_phase.value}"
                            self.voice_announcer.announce(f"{event.name}({event.code}) 顶部信号，分批离场", code=event.code)
                            logger.warning(f"🚨 [Phase Alert] {event.code} {event.name} -> {new_phase.value}")
                except Exception as e:
                    logger.debug(f"Phase engine link failed: {e}")
                # 静默模式：只记录日志，不播报
                logger.debug(f"Signal muted (count={event.count}): {event.code} {pattern_cn}")
            
            # === [NEW] 极速打板/早盘抢筹自动执行逻辑 ===
            if pattern_key == 'early_momentum_buy':
                try:
                    trades_info = self.trading_logger.get_trades()
                    open_trades = [t for t in trades_info if t['status'] == 'OPEN']
                    act_count = len(open_trades)
                    
                    if act_count < 5:
                        from trading_hub import TrackedSignal
                        new_signal = TrackedSignal(
                            code=event.code,
                            name=event.name,
                            signal_type='early_momentum_buy',
                            detected_date=datetime.datetime.now().strftime("%Y-%m-%d"),
                            detected_price=event.price,
                            entry_strategy='早盘抢筹',
                            status='VALIDATED',
                            priority=30,
                            source='LiveStrategy'
                        )
                        msg = f"强势早盘抢筹触发自动买入，当前持仓数: {act_count}/5"
                        logger.info(f"🚀 [Auto Entry] {event.code} {event.name} execute early_momentum_buy")
                        self._execute_follow_trade(new_signal, event.price, msg, 'd')
                    else:
                        msg = f"早盘抢筹触发，但持仓数已达上限({act_count}/5)，放弃买入。"
                        logger.warning(f"⚠️ [Capacity Full] {event.code} {event.name} early_momentum_buy skipped. Limit 5 reached.")
                        self.voice_announcer.announce(msg, code=event.code)
                except Exception as eval_err:
                    logger.error(f"Early momentum auto-buy failed: {eval_err}")

            # === 高优先级信号触发闪屏 ===
            if is_high_priority and hasattr(self, 'on_high_priority_signal'):
                try:
                    self.on_high_priority_signal(event)
                except Exception as e:
                    logger.debug(f"High priority callback failed: {e}")
            
            # === 直接写入数据库 (Live 信号独立记录, 同日同股同信号只更新计数) ===
            # === 直接写入数据库 (Live 信号独立记录, 同日同股同信号只更新计数) ===
            try:
                # [Optimization] Use centralized manager via SignalMessageQueue
                SignalMessageQueue().log_live_signal_direct(
                    code=event.code, 
                    name=event.name, 
                    pattern=event.pattern, 
                    score=event.score, 
                    msg=msg, 
                    is_high_priority=is_high_priority
                )
            except Exception as db_err:
                logger.error(f"Failed to save live signal to DB: {db_err}")

            # === [FIX] 自动同步到热股观察池 (Watchlist) ===
            try:
                hub = get_trading_hub()
                # 提取 sector，如果有的话
                sector = ""
                if hasattr(self, '_monitored_stocks') and event.code in self._monitored_stocks:
                   sector = self._monitored_stocks[event.code].get('industry', '')
                
                # 写入 Watchlist
                hub.add_to_watchlist(
                    code=event.code,
                    name=event.name,
                    sector=sector,
                    price=event.price,
                    source="日线形态", 
                    daily_patterns=f"{event.name} {pattern_cn}", 
                    pattern_score=event.score
                )
            except Exception as w_err:
                logger.error(f"Failed to add to watchlist: {w_err}")

            # === [NEW] 自动纠偏逻辑：针对 Follow Queue 的标的，触发风险信号时执行“跑路”通报 ===
            if event.pattern in ('bull_trap_exit', 'momentum_failure'):
                key = event.code
                if key in self._monitored_stocks:
                    data = self._monitored_stocks[key]
                    tags = data.get('tags', '')
                    if 'auto_followed' in tags:
                        # 标记为危险，强化报警
                        e_name = getattr(event, 'name', event.code)
                        e_code = getattr(event, 'code', key)
                        if e_name == e_code:
                            f_msg = f"警告！{e_code} 诱多破位，建议跑路"
                        else:
                            f_msg = f"警告！{e_name}({e_code}) 诱多破位，建议跑路"
                        self.voice_announcer.announce(f_msg, code=e_code)

                        # ⭐ 关键保护：确保 snapshot 存在
                        if 'snapshot' not in data or not isinstance(data['snapshot'], dict):
                            data['snapshot'] = {}

                        # 更新备注，便于 Visualizer 展示
                        data['snapshot']['last_reason'] = f"【跑路信号】{getattr(event, 'detail', '')}"
                        data['snapshot']['trade_phase'] = "EXIT"

                        logger.warning(
                            f"🚩 [Auto-Exit Signal] {event.code} {getattr(event,'name','')} "
                            f"triggered {getattr(event,'pattern','')}. Detail: {getattr(event,'detail','')}"
                        )

                        # ⚡ [FIX] 推送给 Visualizer 信号日志 + 语音 (需要开启 vis_var 且 master 允许)
                        try:
                            if self.master and getattr(self.master, "_vis_enabled_cache", False):
                                ipc_data = {
                                    "code": event.code,
                                    "name": getattr(event, 'name', event.code),
                                    "pattern": "EXIT",  # 统一归类为离场信号
                                    "message": f"【跑路信号】{getattr(event, 'detail', '')}，建议止盈离场",
                                    "is_high_priority": True,
                                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "priority": 100
                                }
                                send_signal_to_visualizer_ipc(ipc_data)
                        except Exception as ipc_e:
                            logger.error(f"Failed to send EXIT signal to visualizer: {ipc_e}")

                    
        except Exception as e:
            logger.error(f"Pattern callback error: {e}")

    def _update_daily_history_cache(self,code=None,resample='d'):
        """
        批量更新监控股票的日线历史缓存
        """
        if not hasattr(self, 'daily_pattern_detector'):
            return
        
        codes = []
        now = time.time()
        if not hasattr(self, '_daily_hist_cache_status'):
            self._daily_hist_cache_status = True
            # # 每 10 分钟更新一次
            # if now - self.last_daily_history_refresh < 600:
            #     return
            codes = list(self._monitored_stocks.keys())
            # 过滤掉带采样的 key (e.g., '000001_5')
            codes = [c for c in codes if '_' not in c]

        if f'{code}_{resample}' not in list(self.daily_history_cache.keys()):
            codes.append(code)
        else:
            # logger.debug(f'code in hist_cache')
            return

        if not codes:
            return
            
        try:
            # ⭐ [FIX] 异步抓取逻辑：如果不在缓存且未在抓取中，则投递到并行线程池
            for c in codes:
                cache_key = f"{c}_{resample}"
                if cache_key in self._pending_hist_fetches:
                    continue
                
                self._pending_hist_fetches.add(cache_key)
                self.executor.submit(self._async_fetch_history, c, resample)
                
            self.last_daily_history_refresh = now
            # logger.debug(f"Daily history cache task submitted for {len(codes)} stocks.")
        except Exception as e:
            logger.error(f"Failed to submit daily history cache tasks: {e}")

    def _async_fetch_history(self, code, resample):
        """异步抓取单只股票历史数据"""
        cache_key = f"{code}_{resample}"
        try:
            # 还原为稳健的 dl 获取方式
            dl = 70
            if resample in ct.Resample_LABELS_Days:
                dl = ct.Resample_LABELS_Days[resample]
                
            df_hist = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample=resample, fastohlc=True)
            if df_hist is not None and not df_hist.empty:
                df_hist.rename(columns={"vol": "volume"}, inplace=True)
                # [NEW] Calculate TD Sequence
                try:
                    from td_sequence import calculate_td_sequence
                    df_hist = calculate_td_sequence(df_hist)
                except Exception as e:
                    logger.debug(f"TD Sequence calculation error for {code}: {e}")
                
                self.daily_history_cache[cache_key] = df_hist
                # logger.debug(f"✅ History cache updated: {cache_key}")
        except Exception as e:
            logger.debug(f"Failed to fetch history for {code}: {e}")
        finally:
            if cache_key in self._pending_hist_fetches:
                self._pending_hist_fetches.remove(cache_key)

    @with_log_level(LoggerFactory.INFO)
    def _on_daily_pattern_detected(self, event: 'DailyPatternEvent') -> None:
        """日线形态检测回调 - 标准化报警处理"""
        try:
            pattern_cn = self.daily_pattern_detector.PATTERN_NAMES.get(event.pattern, event.pattern)
            action = "日线形态"
            
            # 使用 detail 增强消息
            msg = f"[日线] {event.name} ({event.code}) {event.detail}"
            
            # 存储至 snapshot 以供决策引擎使用
            if event.code in self._monitored_stocks:
                stock_info = self._monitored_stocks[event.code]
                if 'snapshot' not in stock_info:
                    stock_info['snapshot'] = {}
                stock_info['snapshot']['pattern'] = event.pattern
                stock_info['snapshot']['pattern_detail'] = event.detail
            
            # 触发报警
            logger.debug(f"📅 日线形态: {event.code} {event.name} - {event.detail} Score={event.score}")
            self._trigger_alert(
                event.code, event.name, msg, 
                action=action, price=event.price, 
                score=event.score, 
                grade=event.grade  # [NEW] 显式传入评级
            )
            
            # 📅 [UNIFIED PIPELINE] 集成至统一观察池
            # 只有分值 >= 50 的形态才具备“金子”潜力，送入跨日验证闸门
            if event.score >= 50:
                try:
                    hub = get_trading_hub()
                    hub.add_to_watchlist(
                        code=event.code,
                        name=event.name,
                        sector="", # 实时行情 row 里才有 sector，这里暂缺或后期补齐
                        price=event.price,
                        source=f"DailyPattern|{event.pattern}",
                        daily_patterns=event.detail,
                        pattern_score=event.score
                    )
                    logger.debug(f"✨ [归集] 发现高价值形态: {event.code} {event.name} ({event.detail}) -> Watchlist")
                except Exception as ex:
                    logger.debug(f"Failed to sync daily pattern to watchlist: {ex}")

        except Exception as e:
            logger.error(f"Daily pattern callback failed: {e}")

    def _trigger_alert(self, code: str, name: str, message: str, action: str = '持仓', price: float = 0.0, resample: str = 'd', score: float = 0.0, grade: str = "", silent: bool = False) -> None:
        """触发报警 (异步分发器)
        Args:
            silent: 若为 True, 则仅记录和发送至总线/IPC，不触发 UI 弹窗和语音播报
        """
        # --- 1. 快速过滤 (同步执行，必须极快) ---
        if self.is_blacklisted(code):
            if hasattr(self, 'trading_logger'):
                self.trading_logger.increment_blacklist_hit(code)
            if code in self._blacklist_data:
                self._blacklist_data[code]['hit_count'] = self._blacklist_data[code].get('hit_count', 0) + 1
            logger.debug(f"🔇 Blacklist Blocked: {name}({code})")
            return

        # --- 2. 状态识别 (同步) ---
        is_priority = any(kw in message for kw in [
            "连阳", "主升", "突破", "热点", "核心", "TD序列", "顶部风险", "卖出", "跌破", "风险", "SELL", "EXIT",
            "起跳新星", "🌟", "PATTERN", "形态", "V_SHAPE", "RULE", "POSITION",
            "买入", "加仓", "BUY", "ADD", "突破中心", "异动", "强势", "涨停", "封板" # [ADDED] 补充买入与核心强势词汇
        ])
        now_ts = time.time()
        
        # --- 3. UI 节流判定 (同步) ---
        should_skip_ui = False
        if self.alert_callback:
            if not hasattr(self, '_ui_callback_throttle'): 
                self._ui_callback_throttle = {'last_t': 0, 'count': 0}
            
            if now_ts - self._ui_callback_throttle['last_t'] < 1.0:
                self._ui_callback_throttle['count'] += 1
            else:
                self._ui_callback_throttle['last_t'] = now_ts
                self._ui_callback_throttle['count'] = 1
            
            # ⭐ [OPTIMIZE] 显著放宽非优先信号的节流阈值 (10 -> 30)，由于 UI 队列已扩容，此处可以投递更多任务进行缓冲
            # 这样在 148 条并发下，核心信号 100% 弹出，普通信号也能保留大量采样
            should_skip_ui = (self._ui_callback_throttle['count'] > 30 and not is_priority)

        # --- 4. 投递异步任务 (线程池) ---
        # 获取股票等级 (从监控列表)
        # 获取股票等级 (从监控列表)
        monitor_grade = ""
        if code in self._monitored_stocks:
            monitor_grade = self._monitored_stocks[code].get('grade', '')

        # 打包上下文数据，防止主线程随后的循环修改局部变量（虽然这里是传参，但保险起见快照化关键信息）
        alert_ctx = {
            'code': code, 'name': name, 'message': message, 
            'action': action, 'price': price, 'resample': resample,
            'is_priority': is_priority, 'should_skip_ui': should_skip_ui,
            'grade': grade or monitor_grade,
            'score': score,
            'timestamp_str': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            # 优先使用内部线程池
            if hasattr(self, 'executor') and self.executor:
                if not getattr(self, '_is_stopping', False):
                    self.executor.submit(self._async_alert_worker, alert_ctx)
                else:
                    logger.debug(f"Skip alert submission during shutdown for {code}")
            else:
                # 兜底方案
                t = threading.Thread(target=self._async_alert_worker, args=(alert_ctx,), daemon=True)
                t.start()
        except Exception as e:
            logger.error(f"Failed to submit alert task: {e}")

    def _async_alert_worker(self, ctx: dict) -> None:
        """异步报警执行者 (后台线程运行)"""
        try:
            code, name, message = ctx['code'], ctx['name'], ctx['message']
            action, price, resample = ctx['action'], ctx['price'], ctx['resample']
            is_priority, should_skip_ui = ctx['is_priority'], ctx['should_skip_ui']
            grade, now_str = ctx.get('grade', ''), ctx['timestamp_str']
            score = ctx.get('score', 0.0)
            silent = ctx.get('silent', False) # [NEW] 获取静默标志

            # --- A. 信号持久化 (Log/DB/Queue) ---
            try:
                from signal_message_queue import SignalMessageQueue, SignalMessage
                sig_type = "ALERT"
                if "起跳新星" in message: sig_type = "BREAKOUT_STAR"
                elif "形态" in message or "PATTERN" in message: sig_type = "PATTERN"
                elif is_priority: sig_type = "MOMENTUM"

                # 写入策略数据库 (SQLite 同步写在大并发下耗时显著)
                SignalMessageQueue().push(SignalMessage(
                    priority=10 if is_priority else (30 if sig_type == "BREAKOUT_STAR" else 50),
                    timestamp=now_str, code=code, name=name, signal_type=sig_type,
                    source="live_strategy", reason=message, score=score,
                    grade=grade
                ))
                # 写入交易日志库
                self.trading_logger.log_live_signal(
                    code=code, name=name, price=price, action=sig_type, reason=message, resample=resample
                )
            except Exception as e:
                logger.debug(f"Async DB persistence failed: {e}")

            # --- B. IPC 实时推送 ---
            try:
                # [FIX] 仅当 UI 开启了可视化开关时才发送 IPC，避免无效消耗与 GIL 线程冲突
                if self.master and getattr(self.master, "_vis_enabled_cache", False):
                    ipc_data = {
                        "code": code, "name": name, "pattern": sig_type if 'sig_type' in locals() else "ALERT",
                        "message": message, "is_high_priority": is_priority, "timestamp": now_str, 
                        "priority": 100 if is_priority else 50,
                        "grade": grade,
                        "score": score
                    }
                    send_signal_to_visualizer_ipc(ipc_data)
            except Exception: pass

            # --- C. UI 回调 (执行外部注册函数) ---
            if self.alert_callback and not should_skip_ui and not silent:
                try:
                    self.alert_callback(code, name, message)
                except Exception as e:
                    logger.error(f"Async Alert callback error: {e}")

            # --- D. 语音播报 ---
            if self.voice_enabled and not silent:
                # 语义清理
                clean_msg = message.replace(name, "").replace(code, "").replace("\n", " ").strip()
                import re
                raw_parts = re.split(r'[，。！| \s]+', clean_msg)
                seen = set()
                unique_parts = [p.strip() for p in raw_parts if p.strip() and p.strip() not in seen and not seen.add(p.strip())] # type: ignore
                concise_msg = "，".join(unique_parts[:3])
                
                leading_tag = ""
                if "连阳" in message: leading_tag = "强势连阳，"
                elif "热点" in message: leading_tag = "热点龙头，"
                elif "主升" in message: leading_tag = "主升启动，"
                elif "顶部风险" in message: leading_tag = "顶部预警，"

                speak_text = f"注意{action}，{leading_tag}{name} {code} ，{concise_msg}"
                try:
                    # 即使是异步，也保留 200ms 小间隔让 UI 窗口先创建（如果是新出的信号）
                    time.sleep(0.2)
                    self._voice.announce(speak_text, code=code)
                except Exception as e:
                    logger.debug(f"Async announce error: {e}")

            # --- E. 交易记录执行 (DB 写) ---
            if action in ("买入", "卖出", "ADD", "加仓") or "止" in action:
                self.trading_logger.record_trade(code, name, action, price, 100, reason=message, resample=resample) 

            # --- F. 跟单队列同步 (DB 写/IPC) ---
            if action in ("卖出", "止损", "止盈", "清仓"):
                try:
                    from trading_hub import get_trading_hub
                    hub = get_trading_hub()
                    hub.update_follow_status(code, "EXITED", exit_price=price, exit_date=now_str, notes=f"Auto closed by {action}: {message[:50]}")
                except Exception: pass

        except Exception as outer_e:
            logger.error(f"Critical error in _async_alert_worker: {outer_e}")
    def _play_sound_async(self):
        # 💥 已移除 winsound 报警，统一使用 VoiceAnnouncer
        pass


    def start_auto_trading_loop(self, force: bool = False, concept_top5: Optional[list[Any]] = None):
        """开启自动循环优选交易 (支持断点恢复/自动补作业/强制启动)"""
        self.auto_loop_enabled = True
        now_time = datetime.datetime.now()
        today_str = now_time.strftime('%Y-%m-%d')
        is_after_close = now_time.strftime('%H:%M') >= "15:00"

        # --- 0. 手动/强制启动逻辑 (与每日自动循环独立) ---
        if force:
            # 手动触发不再重置自动循环的状态，而是作为独立的批次导入
            self._voice.say("手动热点选股强制启动")
            logger.info("Manual Hotspot Selection Triggered (Independent Batch)")
            if hasattr(self, 'df'):
                self.executor.submit(self._import_hotspot_candidates_async, concept_top5=concept_top5, is_manual=True)
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
                if getattr(self, '_is_importing_hotspot', False):
                    # Already importing, wait
                    return
                
                self._is_importing_hotspot = True
                self.executor.submit(self._import_hotspot_candidates_async, concept_top5=concept_top5)
                # the async method will update the state to WAITING_ENTRY on success

            # 2. State: WAITING_ENTRY - 等待建仓
            elif self.batch_state == "WAITING_ENTRY":
                # 检查是否已买入
                open_counts = self._get_batch_open_count()
                if open_counts > 0:
                    self.batch_state = "IN_PROGRESS"
                    self._voice.say("目标股已建仓，进入持仓监控模式")
                    logger.debug(f"Auto Loop: State -> IN_PROGRESS. Holding {open_counts}")
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
                     logger.debug("Auto Loop: All cleared. State -> IDLE")
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

    def _import_hotspot_candidates_async(self, concept_top5: Optional[list[Any]] = None, is_manual: bool = False):
        try:
            msg = self._import_hotspot_candidates(concept_top5=concept_top5, is_manual=is_manual)
            now = time.time()
            if "成功导入" in msg:
                if not is_manual:
                    self.batch_state = "WAITING_ENTRY"
                    self.batch_start_time = now
                self._voice.say(f"新一轮优选股已就位")
            elif "StockSelector不可用" in msg:
                pass
            else:
                logger.debug(f"Auto Loop: Import failed/skipped: {msg}")
        except Exception as e:
            logger.error(f"Async hotspot import failed: {e}")
        finally:
            self._is_importing_hotspot = False

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
            # [FIX] 传入 self.df (即实时行情 df_all)，确保板块 category 信息可获取
            selector = StockSelector(df=getattr(self, 'df', None))
            date_str = cct.get_today()
            # 获取全部候选
            df = selector.get_candidates_df(logical_date=date_str)
            logger.info(f"StockSelector: Found {len(df)} candidates for {date_str}")
            
            if df.empty:
                logger.warning(f"StockSelector returned empty candidates for {date_str}")
                return "无标的"
            
            # --- [STRENGTHEN] 黑名单与已忽略标的强效过滤 ---
            initial_count = len(df)
            df = df[~df['code'].apply(lambda x: self.is_blacklisted(str(x).zfill(6)))]
            if len(df) < initial_count:
                logger.info(f"🚫 Blacklist Filter: Removed {initial_count - len(df)} ignored stocks from candidates.")

            # [NEW] 精选条件：低开高走强势放量上攻
            # 1. 低开：open < pre_close * 0.98
            # 2. 高走：当前涨幅 > 2%
            # 3. 强势放量：量比 > 1.5 或 换手 > 3%
            elite_df = df.copy()
            
            # 应用精选过滤条件（如果列存在）
            if 'open' in elite_df.columns and 'pre_close' in elite_df.columns:
                elite_df = elite_df[elite_df['open'] < elite_df['pre_close'] * 0.98]
                logger.info(f"低开筛选后剩余: {len(elite_df)} 只")
            
            if 'change' in elite_df.columns:
                elite_df = elite_df[elite_df['change'] > 2.0]
                logger.info(f"高走筛选后剩余: {len(elite_df)} 只")
            
            # 放量条件：量比或换手满足其一
            if 'volume_ratio' in elite_df.columns or 'turnover_rate' in elite_df.columns:
                volume_filter = pd.Series([False] * len(elite_df), index=elite_df.index)
                if 'volume_ratio' in elite_df.columns:
                    volume_filter |= (elite_df['volume_ratio'] > 1.5)
                if 'turnover_rate' in elite_df.columns:
                    volume_filter |= (elite_df['turnover_rate'] > 3.0)
                elite_df = elite_df[volume_filter]
                logger.info(f"放量筛选后剩余: {len(elite_df)} 只（精选标的）")
            
            # 如果精选标的不足5只，用原始候选补充
            if len(elite_df) < 5:
                logger.warning(f"精选标的不足5只，用原始候选补充")
                df = df  # 使用原始候选
            else:
                df = elite_df  # 使用精选标的
                logger.info(f"✅ 使用精选标的: {len(df)} 只")
            
            # --- [DELETED] 冗余的二次过滤 ---
            # df = selector.filter_strong_stocks(df) 
            # 前面的 get_candidates_df 内部已调用过 filter_strong_stocks，且 elite_df 是其子集，不需要再次过滤。
            
            # 识别热点股 (确保 reason 列存在)
            if 'reason' in df.columns:
                df['is_hot'] = df['reason'].fillna('').astype(str).apply(lambda x: 1 if '热点' in x else 0)
            else:
                df['is_hot'] = 0

            selected_codes = []
            final_top5_df = pd.DataFrame()
            
            # [FIX] 防御性检查：确保 df 不为空且包含 category 列
            if df.empty:
                logger.warning("Auto Loop: No candidates left after elite filtering.")
                return "无标的"
            
            if 'category' not in df.columns:
                logger.warning("Auto Loop: 'category' column missing in candidates. Adding empty column.")
                df['category'] = ''
            
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
            added_names = []
            skipped_names = []
            repaired_names = []
            
            for _, row in final_top5_df.iterrows():
                code = str(row['code']).zfill(6)
                name = row['name']
                current_price = float(row.get('price', 0))
                
            with self._lock:
                if code in self._monitored_stocks:
                    stock_data = self._monitored_stocks[code]
                    # [Fix]: 如果已有条目，必须更新标签以确认为今日热点，防止"跟丢"
                    was_updated = False
                    if stock_data.get('create_price', 0) <= 0:
                        stock_data['create_price'] = current_price
                        was_updated = True
                    
                    # 更新标签为最新热点标签 (除非是手动股，不覆盖手动标)
                    # 这样依然保留原来的 rules，但刷新了身份
                    current_tag = str(stock_data.get('tags', ''))
                    if 'manual' not in current_tag and tag not in current_tag:
                         stock_data['tags'] = tag  # 更新为最新的 auto_hotspot_loop
                         was_updated = True
                    
                    # 更新 snapshot 中的 reason (最新的热点理由)
                    if 'snapshot' not in stock_data: stock_data['snapshot'] = {}
                    stock_data['snapshot']['reason'] = row.get('reason', '')
                    stock_data['snapshot']['score'] = row.get('score', 0)
                         
                    if was_updated:
                        repaired_names.append(name)
                    else:
                        skipped_names.append(name)
                else:
                    added_names.append(name)
                    self._monitored_stocks[code] = {
                        "name": name,
                        "rules": [{'type': 'price_up', 'value': current_price}], 
                        "last_alert": 0,
                        "created_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "create_price": current_price,
                        "tags": tag,
                        "grade": row.get('grade', ''),
                        "snapshot": {
                            "score": row.get('score', 0),
                            "reason": row.get('reason', ''),
                            "category": row.get('category', ''),
                            "tqi": row.get('tqi_score', 0)
                        }
                    }
                
                # 同步到数据库
                if hasattr(self, 'trading_logger'):
                    data = self._monitored_stocks[code]
                    self.trading_logger.log_voice_alert_config(
                        code=code,
                        resample=data.get('resample', 'd'),
                        name=name,
                        rules=json.dumps(data.get('rules', [])),
                        last_alert=data.get('last_alert', 0),
                        tags=data.get('tags', ''),
                        rule_type_tag=data.get('rule_type_tag', ''),
                        create_price=data.get('create_price', 0.0),
                        created_time=data.get('created_time', '')
                    )
           
            added_count = len(added_names)
            repaired_count = len(repaired_names)
            skipped_count = len(skipped_names)

            if added_count > 0 or repaired_count > 0:
                self._save_monitors()
                mode_str = "Manual" if is_manual else "Auto"
                
                # 构建详细日志
                log_detail = f"{mode_str} Hotspots Report:"
                if added_names: log_detail += f" [Added: {','.join(added_names)}]"
                if repaired_names: log_detail += f" [Repaired: {','.join(repaired_names)}]"
                if skipped_names: log_detail += f" [Skipped: {','.join(skipped_names)}]"
                logger.info(log_detail)

                return f"成功添加 {added_count} 只, 修补 {repaired_count} 只 ({mode_str})"
            
            return f"已存在重复标的，跳过 {skipped_count} 只 ({','.join(skipped_names)})"

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
            self._last_settlement_date = datetime.datetime.now().strftime('%Y-%m-%d')
            
            # 3. 运行选股逻辑，为次日准备
            # 修正：收盘结算只清理自动循环逻辑中的监控
            self._cleanup_auto_monitors(force_all=True, tag_filter="auto_hotspot_loop") # 清理未持仓的自动股，为明天腾空间
            msg = "清理完成，等待次日自动选股"
            
            # 4. [NEW] 持仓留强去弱评估
            try:
                hub = get_trading_hub()
                # 构造收盘 OHLC 字典
                if self.df is not None and not self.df.empty:
                    ohlc_data = {}
                    for code, row in self.df.iterrows():
                        ohlc_data[str(code).zfill(6)] = {
                            'close': float(row.get('close', 0)),
                            'high': float(row.get('high', 0)),
                            'low': float(row.get('low', 0)),
                            'open': float(row.get('open', 0)),
                            'ma5': float(row.get('ma5d', 0)),
                            'ma10': float(row.get('ma10d', 0)),
                            'upper': float(row.get('upper', 0)),
                            'volume_ratio': float(row.get('volume', 0)) if float(row.get('volume', 0)) <= 500 else 1.0,  # >500为原始成交量,非量比
                            'win': int(row.get('win', 0)) if not pd.isna(row.get('win', 0)) else 0,
                        }
                    eval_res = hub.evaluate_holding_strength(ohlc_data)
                    logger.info(f"Daily Holding Strength Eval: {eval_res}")
            except Exception as e:
                logger.error(f"Holding strength eval failed: {e}")

            # 5. 语音播报
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
            
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
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
    # import datetime # handled at top
    
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
    now_datetime = datetime.datetime.now()
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
