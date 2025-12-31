# -*- coding: utf-8 -*-
"""
Stock Live Strategy & Alert System
高性能实时股票跟踪与语音报警模块
"""
import threading
import queue
import time
import os
import winsound
from datetime import datetime
from typing import Optional, Callable, Dict, Any, Union, List
import pandas as pd
from JohnsonUtil import LoggerFactory
from concurrent.futures import ThreadPoolExecutor
from intraday_decision_engine import IntradayDecisionEngine
from risk_engine import RiskEngine
from trading_logger import TradingLogger
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger()

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

try:
    import pythoncom
except ImportError:
    pythoncom = None

class VoiceAnnouncer:
    """独立的语音播报引擎"""
    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()
        self.on_speak_start: Optional[Callable[[str], None]] = None # 回调函数: func(code)
        self.on_speak_end: Optional[Callable[[str], None]] = None   # 回调函数: func(code)
        self._stop_event = threading.Event()
        self.current_code = None
        self.current_engine = None
        
        # 仅当 pyttsx3 可用时启动线程
        if pyttsx3:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._thread = None

    def _speak_one(self, text):
        """单次播报，每次重新初始化以避免 COM 状态问题"""
        engine = None
        try:
            if pythoncom:
                pythoncom.CoInitialize()
            
            engine = pyttsx3.init()
            self.current_engine = engine
            
            # 设置语速
            rate = engine.getProperty('rate')
            engine.setProperty('rate', rate + 20)
            
            logger.info(f"📢 语音播报: {text}")
            engine.say(text)
            engine.runAndWait()
            
        except Exception as e:
            logger.error(f"TTS Play Error: {e}")
        finally:
            self.current_engine = None
            # 尝试清理
            if engine:
                try:
                    engine.stop()
                    del engine
                except:
                    pass
            if pythoncom:
                pythoncom.CoUninitialize()

    def _run_loop(self):
        """后台语音线程"""
        if not pyttsx3:
            return
            
        while not self._stop_event.is_set():
            try:
                data = self.queue.get(timeout=1)
                text = data.get('text')
                code = data.get('code')
                
                self.current_code = code
                
                if text:
                    if self.on_speak_start:
                        try:
                            self.on_speak_start(code)
                        except: pass
                    
                    self._speak_one(text)
                    
                    if self.on_speak_end:
                        try:
                            self.on_speak_end(code)
                        except: pass
                
                self.current_code = None
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Voice Loop Error: {e}")
                self.current_code = None
                time.sleep(1) # 防止死循环刷屏

    def say(self, text: str, code: Optional[str] = None) -> None:
        if self._thread and self._thread.is_alive():
            if self.queue.qsize() < 10: # 稍微放宽堆积限制
                self.queue.put({'text': text, 'code': code})
        else:
            logger.info(f"Voice (Disabled): {text}")

    def cancel_for_code(self, target_code: str):
        """停止指定代码的语音播报并清除队列中相关项"""
        # 1. 如果当前正在播报该代码，尝试停止
        if self.current_code == target_code and self.current_engine:
            try:
                logger.info(f"🛑 Stopping voice for {target_code}")
                self.current_engine.stop()
            except Exception as e:
                logger.error(f"Failed to stop engine: {e}")
        
        # 2. 清除队列中的等待项
        temp_list = []
        try:
            while True:
                item = self.queue.get_nowait()
                if item.get('code') != target_code:
                    temp_list.append(item)
                else:
                    logger.info(f"🗑️ Removed pending voice for {target_code}")
        except queue.Empty:
            pass
        
        for item in temp_list:
            self.queue.put(item)

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)


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
                 alert_cooldown: float = 60,
                 stop_loss_pct: float = 0.05,
                 take_profit_pct: float = 0.10,
                 trailing_stop_pct: float = 0.03,
                 max_single_stock_ratio: float = 0.3,
                 min_position_ratio: float = 0.05,
                 risk_duration_threshold: float = 300,
                 voice_enabled: bool = True):
        self._voice = VoiceAnnouncer()
        self.voice_enabled = voice_enabled      # ★ 新增状态
        self._monitored_stocks = {} 
        self._last_process_time = 0
        self._alert_cooldown = alert_cooldown
        logger.info(f'StockLiveStrategy 初始化: alert_cooldown={alert_cooldown}s, '
                   f'stop_loss={stop_loss_pct:.1%}, take_profit={take_profit_pct:.1%}')
        self.enabled = True
        
        # 使用 max_workers=1 避免并发资源竞争，本身计算量很小
        self.executor = ThreadPoolExecutor(max_workers=1)
        
        self.config_file = "voice_alert_config.json"
        self._load_monitors()
        self.alert_callback = None
        self.df = None
        # 初始化决策引擎（带止损止盈配置）
        self.decision_engine = IntradayDecisionEngine(
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            max_position=max_single_stock_ratio
        )
        
        # 初始化记录器
        self.trading_logger = TradingLogger()
        
        # 初始化风控引擎
        self._risk_engine = RiskEngine(
            max_single_stock_ratio=max_single_stock_ratio,
            min_ratio=min_position_ratio,
            alert_cooldown=alert_cooldown,
            risk_duration_threshold=risk_duration_threshold
        )
        self._last_import_logical_date: Optional[str] = None
        self._last_settlement_date: Optional[str] = None # 用于防止重复结算

        # --- Automatic Trading Loop State ---
        self.auto_loop_enabled = False
        self.batch_state = "IDLE"  # IDLE, WAITING_ENTRY, IN_PROGRESS
        self.current_batch: List[str] = []
        self.batch_start_time = 0
        self.batch_last_check = 0


    # ------------------------------------------------------------------
    # Alert Cooldown 控制
    # ------------------------------------------------------------------
    def set_alert_cooldown(self, cooldown: float):
        """
        动态设置告警冷却时间（秒）
        可在运行中安全调用
        """
        if cooldown is None:
            raise ValueError("alert_cooldown cannot be None")

        cooldown = float(cooldown)
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

                # ✅ 结构迁移 / 补齐
                for code, stock in self._monitored_stocks.items():
                    stock.setdefault('rules', [])
                    stock.setdefault('last_alert', 0)
                    stock.setdefault('created_time', datetime.now().strftime("%Y-%m-%d %H"))
                    stock.setdefault('tags', "")
                    stock.setdefault('snapshot', {})  # 快照信息

                    # ✅ 重建 rule_keys（不从文件读取）
                    rule_keys = set()
                    for r in stock['rules']:
                        try:
                            key = self._rule_key(r['type'], r['value'])
                            rule_keys.add(key)
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

                self.stock_count = len(self._monitored_stocks) 
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
            
            candidates = df_candidates['code'].tolist()
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
                            "trade": row.get('price', 0),
                            "percent": row.get('percent', 0),
                            "ratio": row.get('ratio', 0),
                            "amount_desc": row.get('amount', 0),
                            "status": row.get('status', ''),
                            "score": row.get('score', 0),
                            "reason": row.get('reason', '')
                        }
                    }
                    added_count += 1
                else:
                    # 如果已存在，更新其 snapshot
                    self._monitored_stocks[code]['snapshot'].update({
                        "status": row.get('status', self._monitored_stocks[code]['snapshot'].get('status', '')),
                        "score": row.get('score', self._monitored_stocks[code]['snapshot'].get('score', 0)),
                        "reason": row.get('reason', self._monitored_stocks[code]['snapshot'].get('reason', ''))
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

            for code, stock in self._monitored_stocks.items():
                # --- 构建基础数据 ---
                record = {
                    'name': stock.get('name'),
                    'rules': stock.get('rules', []),
                    'last_alert': stock.get('last_alert', 0),
                    'created_time': stock.get('created_time', datetime.now().strftime("%Y-%m-%d %H")),
                    'tags': stock.get('tags', "")
                }

                # --- 可选：添加行情快照 ---
                if hasattr(self, 'df') and self.df is not None and not self.df.empty:
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

                data[code] = record

            # --- 保存到 JSON ---
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Failed to save voice monitors: {e}")

    def _rule_key(self, rule_type, value):
        return f"{rule_type}:{value:.4f}"

    def add_monitor(self, code, name, rule_type, value, tags=None):
        value = float(value)

        if code not in self._monitored_stocks:
            self._monitored_stocks[code] = {
                'name': name,
                'rules': [],
                'last_alert': 0,
                'created_time': datetime.now().strftime("%Y-%m-%d %H"),
                'tags': tags or ""
            }
        
        stock = self._monitored_stocks[code]
        # 如果提供了 tags 且不为空，则更新（覆盖旧的或空的）
        if tags:
            stock['tags'] = tags
        
        # 确保 created_time 存在 (对于旧数据)
        if 'created_time' not in stock:
            stock['created_time'] = datetime.now().strftime("%Y-%m-%d %H")

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
        logger.info(
            f"Monitor added: {name}({code}) {rule_type} > {value}"
        )
        return "added"

    def process_data(self, df_all: pd.DataFrame) -> None:
        """
        处理每一帧的行情数据
        """
        if not self.enabled or df_all is None or df_all.empty:
            return

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

        # --- Auto Loop Check ---
        if self.auto_loop_enabled:
             self.executor.submit(self._process_auto_loop, df_all)

        self.executor.submit(self._check_strategies, self.df)

    def _check_strategies(self, df):
        try:
            now = time.time()
            # 从数据库同步实时持仓信息
            open_trades = {t['code']: t for t in self.trading_logger.get_trades() if t['status'] == 'OPEN'}
            
            valid_codes = [c for c in self._monitored_stocks.keys() if c in df.index]

            for code in valid_codes:
                data = self._monitored_stocks[code]
                last_alert = data.get('last_alert', 0)
                logger.debug(f"{code} data:{data}")

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
                    current_high = float(row.get('high', 0))
                except (ValueError, TypeError) as e:
                    logger.warning(f"{code} 行情数据异常: {e}")
                    continue

                # ---------- 历史 snapshot 与 持仓同步 ----------
                snap = data.get('snapshot', {})
                if code in open_trades:
                    trade = open_trades[code]
                    snap['cost_price'] = trade.get('buy_price', 0)
                    snap['buy_date'] = trade.get('buy_date', '')
                    # 追踪买入后最高价 (用于移动止盈)
                    if current_price > snap.get('highest_since_buy', 0):
                        snap['highest_since_buy'] = current_price
                
                # 注入加速连阳与五日线强度数据
                snap['win'] = row.get('win', snap.get('win', 0)) #加速连阳
                snap['sum_perc'] = row.get('sum_perc', snap.get('sum_perc', 0)) #加速连阳涨幅
                snap['red'] = row.get('red', snap.get('red', 0)) #五日线上数据
                snap['gren'] = row.get('gren', snap.get('gren', 0)) #弱势绿柱数据

                # --- 策略进化：注入反馈记忆 (Feedback Injection) ---
                # 1. 记仇机制：查询该股最近连续亏损次数
                if 'loss_streak' not in snap: # 避免每秒查库，简单缓存(实际应有过期机制，这里简化)
                     # 只有当 snapshot 里没有或者是新的一天时才查(略复杂，这里暂且每次循环查，因为 execute 轻量)
                     # 为了性能考虑，其实应该每分钟只更新一次。这里暂且假设 sqlite 够快。
                     # Better: 在外层定时更新 self.blacklist_cache
                     pass
                
                # 实时查询 (耗时较小，Sqlite PK查询极快)
                snap['loss_streak'] = self.trading_logger.get_consecutive_losses(code, days=15)
                
                # 2. 环境感知：查询最近市场胜率 (可用类变量缓存，每分钟更新一次)
                if not hasattr(self, '_market_win_rate_cache') or now - getattr(self, '_market_win_rate_ts', 0) > 300:
                    self._market_win_rate_cache = self.trading_logger.get_market_sentiment(days=3)
                    self._market_win_rate_ts = now
                snap['market_win_rate'] = self._market_win_rate_cache


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
                last_nclose = snap.get('nclose', 0)

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

                # ---------- 决策引擎 ----------
                decision = self.decision_engine.evaluate(row, snap)
                logger.debug(f"Strategy: {code} ({data['name']}) Engine Result: {decision['action']} Score: {decision['debug'].get('实时买入分', 0)} Reason: {decision['reason']}")
                
                # --- 状态记忆持久化 (New) ---
                if decision["action"] == "买入":
                    snap["last_buy_score"] = decision["debug"].get("实时买入分", 0)
                    snap["buy_triggered_today"] = True
                elif decision["action"] == "卖出":
                    snap["sell_triggered_today"] = True
                
                # 记录最高分作为今日目标追踪
                snap["max_score_today"] = max(snap.get("max_score_today", 0), decision["debug"].get("实时买入分", 0))

                # 记录信号历史 (增强版：传递完整行情数据以便后续分析)
                row_data = {
                    'ma5d': float(row.get('ma5d', 0)),
                    'ma10d': float(row.get('ma10d', 0)),
                    'ma20d': float(row.get('ma20d', 0)),
                    'ma60d': float(row.get('ma60d', 0)),
                    'ratio': float(row.get('ratio', 0)),
                    'volume': float(row.get('volume', 0)),
                    'nclose': current_nclose,
                    'high': current_high,
                    'low': float(row.get('low', 0)),
                    'open': float(row.get('open', 0)),
                    'percent': current_change,
                    'turnover': float(row.get('turnover', 0)),
                    'win': snap.get('win', 0),
                    'red': snap.get('red', 0),
                    'gren': snap.get('gren', 0),
                    'sum_perc': snap.get('sum_perc', 0),
                    'low10': snap.get('low10', 0),
                    'lower': snap.get('lower', 0),
                    'highest_today': snap.get('highest_today', current_high),
                    'pump_height': snap.get('pump_height', 0),
                    'pullback_depth': snap.get('pullback_depth', 0),
                }
                self.trading_logger.log_signal(code, data['name'], current_price, decision, row_data=row_data)

                if decision["action"] != "持仓":
                    messages.append(("POSITION", f'{data["name"]} {decision["action"]} 仓位{int(decision["position"]*100)}% {decision["reason"]}'))

                # ---------- 风控调整仓位 ----------
                action, ratio = self._risk_engine.adjust_position(data, decision["action"], decision["position"])
                if action and (action != "持仓"):
                    messages.append(("POSITION", f'{data["name"]} {action} 当前价 {current_price} 建议仓位 {ratio*100:.0f}%'))

                # ---------- 调试输出 ----------
                logger.debug(f"{code} 调试: price={current_price} nclose={current_nclose} last_close={last_close} below_nclose_count={data['below_nclose_count']} below_last_close_count={data['below_last_close_count']} max_normal_pullback={max_normal_pullback:.4f}")

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
                    logger.info(f"Strategy ALERT: {code} ({data['name']}) Triggered. Action: {action} Msg: {log_msg}")
                    self._trigger_alert(code, data['name'], combined_msgs, action=action, price=current_price)
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
                logger.debug(
                    f"{code} 调试: price={current_price} nclose={current_nclose} "
                    f"last_close={last_close} below_nclose_count={data['below_nclose_count']} "
                    f"below_last_close_count={data['below_last_close_count']} "
                    f"max_normal_pullback={max_normal_pullback:.4f}"
                )

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

                    # ---------- 调试输出 ----------
                    logger.debug(f"{code} 合并前 messages={messages}")
                    logger.debug(f"{code} 去重后 unique_msgs={unique_msgs}")
                    # logger.info(f"{code} combined_msg:\n{combined_msg}")

                    # ---------- 单次触发 ----------
                    self._trigger_alert(
                        code,
                        data['name'],
                        combined_msg,
                        action=action
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

    def remove_monitor(self, code):
        """移除指定股票的所有监控"""
        if code in self._monitored_stocks:
            del self._monitored_stocks[code]
            self._save_monitors()
            logger.info(f"Removed monitor for {code}")

    def update_rule(self, code, rule_index, new_type, new_value):
        """更新指定规则"""
        if code in self._monitored_stocks:
            rules = self._monitored_stocks[code]['rules']
            if 0 <= rule_index < len(rules):
                rules[rule_index]['type'] = new_type
                rules[rule_index]['value'] = float(new_value)
                self._save_monitors()
                logger.info(f"Updated rule for {code} index {rule_index}: {new_type} {new_value}")

    def remove_rule(self, code, rule_index):
        if code in self._monitored_stocks:
            stock = self._monitored_stocks[code]
            rules = stock['rules']

            if 0 <= rule_index < len(rules):
                rule = rules.pop(rule_index)

                if 'rule_keys' in stock:
                    stock['rule_keys'].discard(
                        self._rule_key(rule['type'], rule['value'])
                    )

                if not rules:
                    del self._monitored_stocks[code]

                self._save_monitors()
    def test_alert(self, text="这是一个测试报警"):
        """测试报警功能"""
        self._trigger_alert("TEST", "测试股票", text)

    def test_alert_specific(self, code, name, msg):
        """测试特定报警"""
        self._trigger_alert(code, name, msg)

    def snooze_alert(self, code, cycles=10):
        """
        暂停报警一段时间
        :param code: 股票代码
        :param cycles: 暂停的周期数 (总时长 = cycles * alert_cooldown)
        """
        if code in self._monitored_stocks:
            # 逻辑: last_alert 设为未来时间，使得 now - last_alert < cooldown 持续成立
            # 想要暂停 N 个周期，即 N * cooldown 时间
            # 在 t = now + N * cooldown 时，恢复报警 => (now + N*cooldown) - last_alert >= cooldown
            # => last_alert <= now + (N-1)*cooldown
            future_offset = (cycles - 1) * self._alert_cooldown
            self._monitored_stocks[code]['last_alert'] = time.time() + future_offset
            dt_str = datetime.fromtimestamp(self._monitored_stocks[code]['last_alert']).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"😴 Snoozed alert for {code}  in {cycles} cycles ({cycles * self._alert_cooldown}s alert_cooldown: {self._alert_cooldown}s next_alert_time:{dt_str})")

    def _trigger_alert(self, code: str, name: str, message: str, action: str = '持仓', price: float = 0.0) -> None:
        """触发报警"""
        logger.warning(f"🔔 ALERT: {message}")
        
        # 1. 声音
        self._play_sound_async()
        
        # # 2. 语音播报
        # speak_text = f"注意{action}，{code} ，{message}"
        # self._voice.say(speak_text, code=code)
        # 2. 语音播报（★ 受控）
        if self.voice_enabled:
            speak_text = f"注意{action}，{code} ，{message}"
            self._voice.say(speak_text, code=code)
        else:
            logger.debug(f"Voice muted for {code}")
        
        # 3. 回调
        if self.alert_callback:
            try:
                self.alert_callback(code, name, message)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        # 4. 记录交易执行 (用于回测优化和收益计算)
        if action in ("买入", "卖出") or "止" in action:
            # 记录交易并计算单笔收益
            self.trading_logger.record_trade(code, name, action, price, 100) 

    def _play_sound_async(self):
        try:
             winsound.Beep(1000, 200) 
        except:
            pass

    def stop(self):
        self.enabled = False
        self._voice.stop()
        self.executor.shutdown(wait=False)

    def start_auto_trading_loop(self):
        """开启自动循环优选交易"""
        self.auto_loop_enabled = True
        self.batch_state = "IDLE"
        self._voice.say("自动循环交易模式已启动")
        logger.info("Auto Trading Loop STARTED")
        # 立即触发一次检查
        if hasattr(self, 'df'):
            self.executor.submit(self._process_auto_loop, self.df)

    def stop_auto_trading_loop(self):
        """停止自动循环"""
        self.auto_loop_enabled = False
        self.batch_state = "IDLE"
        self._voice.say("自动循环交易已停止")
        logger.info("Auto Trading Loop STOPPED")

    def _process_auto_loop(self, df):
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
                msg = self._import_hotspot_candidates()
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

    def _import_hotspot_candidates(self) -> str:
        """
        专用的自动选股方法：
        优选“今日热点”中评分最高的5只
        """
        if not StockSelector:
            return "StockSelector不可用"

        try:
           selector = StockSelector()
           date_str = cct.get_today()
           # 获取全部候选
           df = selector.get_candidates_df(logical_date=date_str)
           
           if df.empty:
               return "无标的"
           
           # 筛选 Top 5: 
           # 1. 优先包含 '热点' 字样的理由
           # 2. 按分数排序
           
           # 识别热点股 (确保 reason 列存在且为 str)
           if 'reason' in df.columns:
                df['is_hot'] = df['reason'].fillna('').astype(str).apply(lambda x: 1 if '热点' in x else 0)
           else:
                df['is_hot'] = 0

           # 排序：热点优先 -> 分数 -> 成交额
           df_sorted = df.sort_values(by=['is_hot', 'score', 'amount'], ascending=[False, False, False])
           
           # 取 Top 5
           top5 = df_sorted.head(5)
           self.current_batch = top5['code'].apply(lambda x: str(x).zfill(6)).tolist()
           
           # 导入监控列表
           added_count = 0
           for _, row in top5.iterrows():
                code = str(row['code']).zfill(6)
                name = row['name']
                # Add to monitor
                self._monitored_stocks[code] = {
                    "name": name,
                    "rules": [], # 默认规则
                    "last_alert": 0,
                    "created_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "tags": "auto_hotspot_loop",
                    "snapshot": {
                        "score": row.get('score', 0),
                        "reason": row.get('reason', ''),
                        "category": row.get('category', '')
                    }
                }
                added_count += 1
           
           if added_count > 0:
               self._save_monitors()
               names = ",".join(top5['name'].tolist())
               logger.info(f"Auto Loop: Selected 5 Hotspots: {names}")
               return f"成功导入 {added_count} 只 (Hotspots)"
           return "无新标的导入"

        except Exception as e:
            logger.error(f"Auto Import Error: {e}")
            import traceback
            # logger.error(traceback.format_exc())
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
            # 注意：此时获取的应是今日收盘后的数据 (T日数据)
            msg = self.import_daily_candidates()
            
            # 4. 语音播报
            settle_msg = f"今日交易结束，收盘结算完成。{msg}。已准备好次日交易。"
            self._voice.say(settle_msg)
            logger.info(f"Daily Settlement Done. {msg}")

        except Exception as e:
            logger.error(f"Daily Settlement Error: {e}")

