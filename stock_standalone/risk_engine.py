# -*- coding: utf-8 -*-
"""
风险引擎 - 增强版
支持持续风险监控、信号聚合、交易冷却控制、报警消息生成
"""
import time
import logging
from typing import Dict, List, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class RiskEngine:
    """
    风险引擎 v2
    
    功能：
    - 持续风险监控（连续低于均价/昨收检测）
    - 信号聚合与优先级排序
    - 交易冷却控制
    - 仓位调整
    - 报警消息生成
    
    配置参数（可通过 __init__ 传入）：
    - max_single_stock_ratio: 单只股票最大仓位（默认 0.3）
    - min_ratio: 最小仓位比例（默认 0.05）
    - alert_cooldown: 报警冷却时间秒（默认 300）
    - risk_duration_threshold: 风险持续时间阈值秒（默认 300）
    - below_nclose_trigger: 连续低于均价触发次数（默认 3）
    - below_last_close_trigger: 连续低于昨收触发次数（默认 2）
    """
    
    # 信号优先级定义（数字越小优先级越高）
    SIGNAL_PRIORITY = {
        "止损": 0,
        "止盈": 1,
        "RISK": 2,
        "卖出": 3,
        "RULE": 4,
        "减仓": 5,
        "POSITION": 6,
        "买入": 7,
        "持仓": 8
    }
    
    def __init__(self, 
                 max_single_stock_ratio: float = 0.3,
                 min_ratio: float = 0.05,
                 alert_cooldown: float = 300,
                 risk_duration_threshold: float = 300,
                 below_nclose_trigger: int = 3,
                 below_last_close_trigger: int = 2):
        """
        初始化风险引擎
        
        Args:
            max_single_stock_ratio: 单只股票最大仓位比例（0~1）
            min_ratio: 最小仓位比例，低于此比例视为清仓
            alert_cooldown: 报警冷却时间（秒）
            risk_duration_threshold: 风险持续时间阈值（秒）
            below_nclose_trigger: 连续低于均价触发次数
            below_last_close_trigger: 连续低于昨收触发次数
        """
        self.max_single_stock_ratio = max_single_stock_ratio
        self.min_ratio = min_ratio
        self.alert_cooldown = alert_cooldown
        self.risk_duration_threshold = risk_duration_threshold
        self.below_nclose_trigger = below_nclose_trigger
        self.below_last_close_trigger = below_last_close_trigger
        
        # 报警记录 {code: last_alert_time}
        self._alert_records: Dict[str, float] = {}
        
        # 风险状态跟踪 {code: {counter_name: value}}
        self._risk_states: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"RiskEngine 初始化: max_pos={max_single_stock_ratio:.1%}, "
                   f"min_ratio={min_ratio:.1%}, cooldown={alert_cooldown}s, "
                   f"risk_duration={risk_duration_threshold}s")

    # ==================== 核心方法 ====================
    
    def check_continuous_risk(self, code: str, name: str, price: float, 
                               nclose: float, last_close: float, 
                               last_percent: Optional[float]) -> List[Tuple[str, str]]:
        """
        检测持续风险（连续低于均价/昨收）
        
        Args:
            code: 股票代码
            name: 股票名称
            price: 当前价格
            nclose: 今日均价
            last_close: 昨日收盘价
            last_percent: 昨日涨幅
        
        Returns:
            [(signal_type, message), ...]
        """
        now = time.time()
        signals: List[Tuple[str, str]] = []
        
        # 初始化风险状态
        if code not in self._risk_states:
            self._risk_states[code] = {
                'below_nclose_count': 0,
                'below_nclose_start': 0,
                'below_last_close_count': 0,
                'below_last_close_start': 0
            }
        
        state = self._risk_states[code]
        
        # 计算最大正常回撤阈值
        max_normal_pullback = (last_percent / 5 / 100 if last_percent and -100 < last_percent < 100 else 0.01)
        
        # ---------- 今日均价风控 ----------
        if price > 0 and nclose > 0:
            deviation = (nclose - price) / nclose
            if deviation > max_normal_pullback + 0.0005:
                if state['below_nclose_start'] == 0:
                    state['below_nclose_start'] = now
                if now - state['below_nclose_start'] >= self.risk_duration_threshold:
                    state['below_nclose_count'] += 1
                    state['below_nclose_start'] = now  # 重置计时
            else:
                state['below_nclose_start'] = 0
                state['below_nclose_count'] = 0
            
            if state['below_nclose_count'] >= self.below_nclose_trigger:
                signals.append(("RISK", f"卖出 {name} 连续低于今日均价 {nclose:.2f} (当前 {price:.2f})"))
                state['below_nclose_count'] = 0  # 触发后重置
        
        # ---------- 昨日收盘风控 ----------
        if last_close > 0:
            deviation_last = (last_close - price) / last_close
            if deviation_last > max_normal_pullback + 0.0005:
                if state['below_last_close_start'] == 0:
                    state['below_last_close_start'] = now
                if now - state['below_last_close_start'] >= self.risk_duration_threshold:
                    state['below_last_close_count'] += 1
                    state['below_last_close_start'] = now  # 重置计时
            else:
                state['below_last_close_start'] = 0
                state['below_last_close_count'] = 0
            
            if state['below_last_close_count'] >= self.below_last_close_trigger:
                signals.append(("RISK", f"减仓 {name} 连续低于昨日收盘 {last_close:.2f} (当前 {price:.2f})"))
                state['below_last_close_count'] = 0  # 触发后重置
        
        return signals

    def adjust_position(self, stock_data: Dict[str, Any], 
                        suggested_action: str, 
                        suggested_ratio: float) -> Tuple[str, float]:
        """
        根据风险因素调整仓位
        
        Args:
            stock_data: 包含当前行情及历史指标的字典
            suggested_action: 初步仓位动作（买入/卖出/持仓等）
            suggested_ratio: 初步建议仓位比例（0~1）
        
        Returns:
            (final_action, final_ratio)
        """
        try:
            price = float(stock_data.get('trade', 0))
            nclose = float(stock_data.get('nclose', 0))
            last_close = float(stock_data.get('last_close', 0))
            ma5 = float(stock_data.get('ma5d', 0))
            ma10 = float(stock_data.get('ma10d', 0))
            ma20 = float(stock_data.get('ma20d', 0))
            ma60 = float(stock_data.get('ma60d', 0))
            high5 = float(stock_data.get('max5', 0))
            high_today = float(stock_data.get('high', 0))
            volume = float(stock_data.get('volume', 0))
            ratio = float(stock_data.get('ratio', 0))
            macd = float(stock_data.get('macd', 0))
            kdj_j = float(stock_data.get('kdj_j', 0))
            upper = float(stock_data.get('upper', 0))
            lower = float(stock_data.get('lower', 0))
            name = stock_data.get('name', '')

            # ---------- 核心仓位决策 ----------
            final_ratio = suggested_ratio
            final_action = suggested_action

            # 防止单只股票仓位过大
            if final_ratio > self.max_single_stock_ratio:
                final_ratio = self.max_single_stock_ratio
                logger.debug(f"{name} 超过最大仓位限制，调整为 {final_ratio:.2f}")

            # ---------- MA5/MA10 冲高回落检测 ----------
            if ma5 > 0:
                if price > ma5 and (price - ma5) / ma5 > 0.02:
                    final_ratio *= 0.8
                    logger.debug(f"{name} 高出 MA5 过多，仓位削弱 20%")
                if price < ma5 and suggested_action == '买入':
                    final_ratio *= 0.5
                    logger.debug(f"{name} 低于 MA5，买入谨慎，仓位减半")

            # ---------- 昨日收盘 / 当日均价 校验 ----------
            if last_close > 0 and price < last_close * 0.95:
                final_ratio *= 0.7
                logger.debug(f"{name} 跌破昨日收盘 5%，仓位削弱 30%")
            if nclose > 0 and price < nclose * 0.98:
                final_ratio *= 0.8
                logger.debug(f"{name} 跌破今日均价 2%，仓位削弱 20%")

            # ---------- 极端指标过滤 ----------
            if macd < 0 and kdj_j > 80:
                final_ratio *= 0.5
                logger.debug(f"{name} 高位死叉，仓位减半")
            if upper > 0 and price > upper:
                final_ratio = min(final_ratio, 0.1)
                logger.debug(f"{name} 超布林上轨，极端减仓")
            if lower > 0 and price < lower:
                final_ratio *= 0.6
                logger.debug(f"{name} 跌破布林下轨，仓位削弱 40%")

            # ---------- 均线空头排列 ----------
            if ma5 > 0 and ma10 > 0 and ma20 > 0:
                if price < ma5 < ma10 < ma20:
                    final_ratio *= 0.3
                    logger.debug(f"{name} 均线空头排列，仓位削弱 70%")

            # ---------- 换手率异常 ----------
            if ratio > 20:
                final_ratio *= 0.7
                logger.debug(f"{name} 换手率过高 {ratio}%，仓位削弱 30%")

            # 保证最小仓位限制
            if final_ratio < self.min_ratio:
                final_ratio = 0
                if final_action not in ('卖出', '止损', '止盈'):
                    final_action = '持仓'

            return final_action, max(0, min(1, final_ratio))

        except Exception as e:
            logger.error(f"RiskEngine adjust_position error: {e}")
            return '持仓', 0

    def aggregate_signals(self, signals: List[Tuple[str, str]]) -> Tuple[str, str]:
        """
        聚合并排序多个信号
        
        Args:
            signals: [(signal_type, message), ...]
        
        Returns:
            (highest_priority_action, combined_message)
        """
        if not signals:
            return ('持仓', '')
        
        # 去重
        unique_signals: Dict[str, str] = {}
        for sig_type, msg in signals:
            if msg not in unique_signals:
                unique_signals[msg] = sig_type
            else:
                # 保留优先级更高的类型
                existing_priority = self.SIGNAL_PRIORITY.get(unique_signals[msg], 99)
                new_priority = self.SIGNAL_PRIORITY.get(sig_type, 99)
                if new_priority < existing_priority:
                    unique_signals[msg] = sig_type
        
        # 按优先级排序
        sorted_msgs = sorted(
            unique_signals.items(),
            key=lambda x: self.SIGNAL_PRIORITY.get(x[1], 99)
        )
        
        # 合并消息
        combined = "\n".join([msg for msg, _ in sorted_msgs])
        
        # 确定最高优先级动作
        if sorted_msgs:
            highest_type = sorted_msgs[0][1]
            # 映射类型到动作
            if highest_type in ('止损', '止盈', '卖出', '买入', '持仓', '减仓'):
                action = highest_type
            elif highest_type == 'RISK':
                action = '卖出'
            elif highest_type == 'RULE':
                action = '买入'
            elif highest_type == 'POSITION':
                action = '持仓'
            else:
                action = '持仓'
        else:
            action = '持仓'
        
        return (action, combined)

    def can_alert(self, code: str) -> bool:
        """
        检查是否可以触发报警（冷却时间检查）
        
        Args:
            code: 股票代码
        
        Returns:
            True 如果可以报警，False 如果在冷却中
        """
        now = time.time()
        last_alert = self._alert_records.get(code, 0)
        return now - last_alert >= self.alert_cooldown

    def record_alert(self, code: str):
        """
        记录报警时间
        
        Args:
            code: 股票代码
        """
        self._alert_records[code] = time.time()

    def reset_risk_state(self, code: str):
        """
        重置指定股票的风险状态（通常在报警触发后调用）
        
        Args:
            code: 股票代码
        """
        if code in self._risk_states:
            self._risk_states[code] = {
                'below_nclose_count': 0,
                'below_nclose_start': 0,
                'below_last_close_count': 0,
                'below_last_close_start': 0
            }

    def format_alert_message(self, name: str, action: str, price: float,
                              ratio: float, reason: str) -> str:
        """
        格式化报警消息
        
        Args:
            name: 股票名称
            action: 操作动作
            price: 当前价格
            ratio: 建议仓位
            reason: 原因
        
        Returns:
            格式化的消息字符串
        """
        ratio_str = f"{ratio * 100:.0f}%" if ratio > 0 else "清仓"
        return f"{name} {action} 当前价 {price:.2f} 建议仓位 {ratio_str} | {reason}"

    def get_risk_state(self, code: str) -> Dict[str, Any]:
        """
        获取指定股票的风险状态
        
        Args:
            code: 股票代码
        
        Returns:
            风险状态字典
        """
        return self._risk_states.get(code, {})



# class RiskEngine:
#     def __init__(self, alert_cooldown=300):
#         """
#         alert_cooldown: 报警冷却时间，单位秒
#         _monitored_stocks: dict, 每只股票结构如下
#         {
#             'name': str,
#             'rules': list,
#             'last_alert': float,
#             'snapshot': dict,
#             'below_nclose_count': int,
#             'below_nclose_start': float,
#             'below_last_close_count': int,
#             'below_last_close_start': float
#         }
#         """
#         self._monitored_stocks = {}
#         self._alert_cooldown = alert_cooldown

#     def add_stock(self, code, name, snapshot=None):
#         """添加监控股票"""
#         self._monitored_stocks[code] = {
#             'name': name,
#             'rules': [],
#             'last_alert': 0,
#             'snapshot': snapshot or {},
#             'below_nclose_count': 0,
#             'below_nclose_start': 0,
#             'below_last_close_count': 0,
#             'below_last_close_start': 0
#         }

#     def _trigger_alert(self, code, name, msg):
#         """触发报警"""
#         logger.info(f"ALERT: {msg}")
#         # 可以拓展成声音报警、UI 弹窗、邮件等

#     def _calculate_position(self, stock, current_price, current_nclose, last_close, last_percent, last_nclose):
#         """根据今日/昨日数据计算动态仓位与操作"""
#         position_ratio = 1.0
#         action = "HOLD"

#         valid_yesterday = (last_close > 0) and (last_percent is not None and -100 < last_percent < 100) and (last_nclose > 0)
#         valid_today = (current_price > 0) and (current_nclose > 0)

#         # 今日均价偏离
#         if valid_today:
#             deviation_today = (current_nclose - current_price) / current_nclose
#             max_normal_pullback = (last_percent / 5 / 100 if valid_yesterday else 0.01)
#             if deviation_today > max_normal_pullback + 0.0005:
#                 position_ratio *= 0.7
#                 action = "REDUCE"

#         # 昨日收盘偏离
#         if valid_yesterday:
#             deviation_last = (last_close - current_price) / last_close
#             max_normal_pullback = last_percent / 5 / 100
#             if deviation_last > max_normal_pullback + 0.0005:
#                 position_ratio *= 0.5
#                 action = "SELL"

#         # 趋势加仓
#         if valid_today and current_price > current_nclose:
#             position_ratio = min(1.0, position_ratio + 0.2)
#             if action == "HOLD":
#                 action = "ADD"

#         position_ratio = max(0.0, min(1.0, position_ratio))
#         return action, position_ratio

#     def check_stocks(self, df):
#         """
#         df: pandas DataFrame, index为股票code
#         包含列: trade, nclose, percent, volume, ratio
#         """
#         now = time.time()
#         for code, stock in self._monitored_stocks.items():
#             if code not in df.index:
#                 continue
#             row = df.loc[code]

#             # 安全获取数据
#             try:
#                 current_price = float(row.get('trade', 0))
#                 current_nclose = float(row.get('nclose', 0))
#                 current_change = float(row.get('percent', 0))
#                 volume_change = float(row.get('volume', 0))
#                 ratio_change = float(row.get('ratio', 0))
#             except (ValueError, TypeError):
#                 continue

#             snap = stock.get('snapshot', {})
#             last_close = snap.get('last_close', 0)
#             last_percent = snap.get('percent', None)
#             last_nclose = snap.get('nclose', 0)

#             # ---------- 今日均价计数 ----------
#             if current_price > 0 and current_nclose > 0:
#                 deviation_today = (current_nclose - current_price) / current_nclose
#                 max_normal_pullback = (last_percent / 5 / 100 if last_close > 0 else 0.01)
#                 if deviation_today > max_normal_pullback + 0.0005:
#                     if stock['below_nclose_start'] == 0:
#                         stock['below_nclose_start'] = now
#                     if now - stock['below_nclose_start'] >= 300:
#                         stock['below_nclose_count'] += 1
#                         logger.debug(f"{code} below_nclose_count={stock['below_nclose_count']}")
#                 else:
#                     stock['below_nclose_start'] = 0
#                     stock['below_nclose_count'] = 0
#             else:
#                 stock['below_nclose_start'] = 0
#                 stock['below_nclose_count'] = 0

#             # ---------- 昨日收盘计数 ----------
#             valid_yesterday = (last_close > 0) and (last_percent is not None and -100 < last_percent < 100)
#             if valid_yesterday and current_price < last_close:
#                 deviation_last = (last_close - current_price) / last_close
#                 max_normal_pullback = last_percent / 5 / 100
#                 if deviation_last > max_normal_pullback + 0.0005:
#                     if stock['below_last_close_start'] == 0:
#                         stock['below_last_close_start'] = now
#                     if now - stock['below_last_close_start'] >= 300:
#                         stock['below_last_close_count'] += 1
#                         logger.debug(f"{code} below_last_close_count={stock['below_last_close_count']}")
#                 else:
#                     stock['below_last_close_start'] = 0
#                     stock['below_last_close_count'] = 0
#             else:
#                 stock['below_last_close_start'] = 0
#                 stock['below_last_close_count'] = 0

#             # ---------- 决策触发 ----------
#             triggered = False
#             if stock['below_nclose_count'] >= 3:
#                 msg = (
#                     f"卖出 {stock['name']} 价格连续低于今日均价 {current_nclose} ({current_price}) "
#                     f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
#                 )
#                 triggered = True
#             elif valid_yesterday and stock['below_last_close_count'] >= 2:
#                 msg = (
#                     f"减仓 {stock['name']} 价格连续低于昨日收盘 {last_close} ({current_price}) "
#                     f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
#                 )
#                 triggered = True

#             if triggered and now - stock.get('last_alert', 0) >= self._alert_cooldown:
#                 self._trigger_alert(code, stock['name'], msg)
#                 stock['last_alert'] = now
#                 stock['below_nclose_count'] = 0
#                 stock['below_nclose_start'] = 0
#                 stock['below_last_close_count'] = 0
#                 stock['below_last_close_start'] = 0

#             # ---------- 动态仓位计算 ----------
#             action, ratio = self._calculate_position(stock, current_price, current_nclose, last_close, last_percent, last_nclose)
#             if action != "HOLD":
#                 msg = (
#                     f"{action} {stock['name']} 当前价 {current_price} "
#                     f"今日均价 {current_nclose} 昨日收盘 {last_close} "
#                     f"建议仓位 {ratio*100:.0f}% "
#                     f"涨幅 {current_change} 量能 {volume_change} 换手 {ratio_change}"
#                 )
#                 self._trigger_alert(code, stock['name'], msg)
