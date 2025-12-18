import time
import logging

logger = logging.getLogger(__name__)

import logging

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self, max_single_stock_ratio=1.0, min_ratio=0.0):
        """
        max_single_stock_ratio: 单只股票最大仓位比例（0~1）
        min_ratio: 最小仓位比例，低于此比例视为清仓
        """
        self.max_single_stock_ratio = max_single_stock_ratio
        self.min_ratio = min_ratio

    def adjust_position(self, stock_data, suggested_action, suggested_ratio):
        """
        stock_data: dict, 包含当前行情及历史指标
        suggested_action: str, 初步仓位动作 BUY / SELL / HOLD
        suggested_ratio: float, 初步建议仓位比例 0~1

        return: (final_action:str, final_ratio:float)
        """
        try:
            price = stock_data.get('trade', 0)
            nclose = stock_data.get('nclose', 0)
            last_close = stock_data.get('last_close', 0)
            ma5 = stock_data.get('ma5d', 0)
            ma10 = stock_data.get('ma10d', 0)
            ma20 = stock_data.get('ma20d', 0)
            ma60 = stock_data.get('ma60d', 0)
            high5 = stock_data.get('max5', 0)
            high_today = stock_data.get('high', 0)
            volume = stock_data.get('volume', 0)
            ratio = stock_data.get('ratio', 0)
            last_vols = [stock_data.get(f'lastv{i}d', 0) for i in range(1, 6)]
            macd = stock_data.get('macd', 0)
            kdj_j = stock_data.get('kdj_j', 0)
            upper = stock_data.get('upper', 0)
            lower = stock_data.get('lower', 0)

            # ---------- 核心仓位决策 ----------
            final_ratio = suggested_ratio
            final_action = suggested_action

            # 防止单只股票仓位过大
            if final_ratio > self.max_single_stock_ratio:
                final_ratio = self.max_single_stock_ratio
                logger.debug(f"{stock_data.get('name')} 超过最大仓位限制，调整为 {final_ratio:.2f}")

            # ---------- MA5/MA10 冲高回落检测 ----------
            if price > ma5 and price - ma5 > 0.02 * ma5:  # 高出 MA5 超过 2%
                final_ratio *= 0.8  # 减仓 20%
                logger.debug(f"{stock_data.get('name')} 高出 MA5 过多，仓位削弱 20%")
            if price < ma5 and suggested_action == 'BUY':
                final_ratio *= 0.5  # MA5 下方买入谨慎
                logger.debug(f"{stock_data.get('name')} 低于 MA5，买入谨慎，仓位减半")

            # ---------- 昨日收盘 / 当日均价 校验 ----------
            if last_close and price < last_close * 0.95:
                final_ratio *= 0.7  # 跌破昨日收盘，减仓
                logger.debug(f"{stock_data.get('name')} 跌破昨日收盘 5%，仓位削弱 30%")
            if nclose and price < nclose * 0.98:
                final_ratio *= 0.8  # 跌破当日均价，轻微减仓
                logger.debug(f"{stock_data.get('name')} 跌破今日均价 2%，仓位削弱 20%")

            # ---------- 极端指标过滤 ----------
            if macd < 0 and kdj_j > 80:  # 高位死叉
                final_ratio *= 0.5
                logger.debug(f"{stock_data.get('name')} 高位死叉，仓位减半")
            if upper and price > upper:
                final_ratio = min(final_ratio, 0.1)  # 触布林上轨极端减仓
                logger.debug(f"{stock_data.get('name')} 超布林上轨，极端减仓")

            # 保证最小仓位限制
            if final_ratio < self.min_ratio:
                final_ratio = 0
                final_action = 'HOLD'

            return final_action, final_ratio

        except Exception as e:
            logger.error(f"RiskEngine adjust_position error: {e}")
            return 'HOLD', 0


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
