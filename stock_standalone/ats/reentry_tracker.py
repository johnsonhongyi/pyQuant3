# -*- coding: utf-8 -*-
"""
ats/reentry_tracker.py — ATS 割肉/止损/已平仓标的主升确认回补雷达 (Re-entry & Buy-back Tracker)
职责：
1. 自动从 trading_signals.db / signal_strategy.db 的 trade_records 中加载用户近期平仓/止损标的；
2. 动态监控已割肉标的的技术底座：
   - 跌势终止企稳：在低位筑底不再破前低；
   - 支撑确认：缩量回踩 MA20 / 通道下轨 / 前期颈线不破；
   - 突破反转确认：突破反转阻力位或竞价弱转强高开，确认展开主升结构；
3. 触发【💎 割肉反转回补】买点，彻底根除“建仓早割肉后，股票走出主升浪却无法跟踪回补”的实战痛点。
"""

import os
import sys
import time
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple, Any

from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("ReentryTracker")


class ReentryTracker:
    """割肉/止损标的主升确认回补雷达 (单例模式)"""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ReentryTracker, cls).__new__(cls)
            cls._instance._init_tracker()
        return cls._instance

    def _init_tracker(self):
        # 缓存字典: code -> {buy_date, buy_price, sell_date, sell_price, pnl_pct, min_seen_price, is_stoploss}
        self._closed_trades: Dict[str, Dict[str, Any]] = {}
        self._last_db_load_time: float = 0.0
        self._db_load_interval: float = 60.0  # 每 60 秒轮询一次交易数据库
        self.reload_closed_trades()

    def reload_closed_trades(self):
        """从 SQLite 中加载所有已平仓标的"""
        now = time.time()
        self._last_db_load_time = now
        
        # 常见数据库路径探测
        db_candidates = [
            "trading_signals.db",
            "signal_strategy.db",
            "stock_trade.db",
            os.path.join(os.path.dirname(__file__), "..", "trading_signals.db"),
            os.path.join(os.path.dirname(__file__), "..", "signal_strategy.db"),
        ]

        found_trades = {}
        for db_path in db_candidates:
            if not os.path.exists(db_path):
                continue
            try:
                conn = sqlite3.connect(db_path, timeout=1.0)
                cursor = conn.cursor()
                # 检查是否存在 trade_records 表
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_records'")
                if cursor.fetchone():
                    # 提取 CLOSED 状态或近期卖出记录
                    query = """
                        SELECT code, name, buy_date, buy_price, sell_date, sell_price, profit, pnl_pct, status 
                        FROM trade_records 
                        WHERE status = 'CLOSED' OR sell_date IS NOT NULL
                        ORDER BY id DESC
                    """
                    for row in cursor.execute(query).fetchall():
                        code = str(row[0]).strip().zfill(6)
                        if code not in found_trades:
                            buy_p = float(row[3] or 0.0)
                            sell_p = float(row[5] or 0.0)
                            pnl = float(row[7] or 0.0)
                            sell_dt = str(row[4] or "")
                            
                            # 判定是否为止损/割肉单 (亏损离场，或卖出价比买入价低)
                            is_cut_loss = (pnl < 0.0) or (sell_p > 0 and buy_p > 0 and sell_p < buy_p)
                            
                            found_trades[code] = {
                                "code": code,
                                "name": str(row[1] or ""),
                                "buy_date": str(row[2] or ""),
                                "buy_price": buy_p,
                                "sell_date": sell_dt,
                                "sell_price": sell_p,
                                "pnl_pct": pnl,
                                "is_cut_loss": is_cut_loss,
                                "reentry_active": True
                            }
                conn.close()
            except Exception as ex:
                logger.debug(f"Scan DB {db_path} for closed trades ignored: {ex}")

        # 增量融合更新
        for c, data in found_trades.items():
            if c not in self._closed_trades:
                self._closed_trades[c] = data
            else:
                self._closed_trades[c].update(data)

    def register_manual_track(self, code: str, name: str = "", sell_price: float = 0.0, note: str = ""):
        """支持主观手动录入/关注需要回补跟踪的标的"""
        code_clean = str(code).strip().zfill(6)
        self._closed_trades[code_clean] = {
            "code": code_clean,
            "name": name,
            "buy_date": "",
            "buy_price": 0.0,
            "sell_date": "手动标记",
            "sell_price": sell_price,
            "pnl_pct": -5.0,
            "is_cut_loss": True,
            "reentry_active": True,
            "note": note
        }

    def add_tracked_trade(self, code: str, buy_price: float = 0.0, sell_price: float = 0.0, buy_date: str = "", sell_date: str = "", name: str = "", note: str = ""):
        """支持录入/添加跟踪交易（包含买入价与止损卖出价）"""
        code_clean = str(code).strip().zfill(6)
        pnl = round((sell_price - buy_price) / max(0.01, buy_price) * 100, 2) if buy_price > 0 else -5.0
        self._closed_trades[code_clean] = {
            "code": code_clean,
            "name": name or code_clean,
            "buy_date": buy_date,
            "buy_price": buy_price,
            "sell_date": sell_date or "手动录入",
            "sell_price": sell_price,
            "pnl_pct": pnl,
            "is_cut_loss": True,
            "reentry_active": True,
            "note": note
        }

    def remove_tracked_code(self, code: str):
        """移出跟踪池"""
        code_clean = str(code).strip().zfill(6)
        if code_clean in self._closed_trades:
            self._closed_trades.pop(code_clean, None)

    def check_reentry_signal(
        self,
        code: str,
        current_price: float,
        last_close: float = 0.0,
        ma20: float = 0.0,
        ch_supp: float = 0.0,
        high_2d: float = 0.0,
        pct: float = 0.0,
        is_bidding: bool = False
    ) -> Dict[str, Any]:
        """
        检查指定标的是否触发【割肉反转回补】主升确认买点
        """
        # 定时刷新数据库
        if time.time() - self._last_db_load_time > self._db_load_interval:
            self.reload_closed_trades()

        code_clean = str(code).strip().zfill(6)
        trade_info = self._closed_trades.get(code_clean)
        
        # 默认无回补
        default_res = {
            "is_reentry": False,
            "buy_type": "",
            "reason": "",
            "buy_zone": "--",
            "stop_loss": 0.0,
            "type_priority": 0
        }

        if not trade_info or not trade_info.get("reentry_active", True):
            return default_res

        sell_p = float(trade_info.get("sell_price", 0.0))
        buy_p = float(trade_info.get("buy_price", 0.0))
        sell_dt = str(trade_info.get("sell_date", ""))
        is_cut = trade_info.get("is_cut_loss", True)

        # 核心判定条件：
        # 1. 曾经建仓并割肉/止损出局 (或被列入重点回补池)；
        # 2. 支撑确认：回踩 MA20 或 通道支撑线 ch_supp 未破 (现价站上支撑线)；
        # 3. 反转突破结构：现价开始弱转强高开，或者已突破反转阻力位 (重新站上 MA20 且突破近2日高点，或突破原割肉价)；
        
        has_support_confirmation = False
        if ma20 > 0 and current_price >= ma20 * 0.985:
            has_support_confirmation = True
        elif ch_supp > 0 and current_price >= ch_supp * 0.985:
            has_support_confirmation = True

        # 反转阻力位基准 (通常为割肉价、或前2日高点、或MA20)
        reversal_level = max(sell_p, high_2d) if (sell_p > 0 and high_2d > 0) else (high_2d if high_2d > 0 else sell_p)
        
        # 触发反转回补启动情形：
        # A. 竞价期弱转强：曾割肉，今天竞价高开站稳支撑 (pct >= 0.5% 且站上 MA20)
        # B. 盘中突破主升：站稳支撑且突破反转阻力位 (current_price >= reversal_level * 0.995 且 pct >= 2.0%)
        triggered = False
        trigger_mode = ""

        if has_support_confirmation:
            if is_bidding and pct >= 0.3:
                triggered = True
                trigger_mode = "竞价弱转强确认回补"
            elif (current_price >= reversal_level * 0.995 or current_price > ma20 * 1.01) and (pct >= 2.0 or current_price >= sell_p):
                triggered = True
                trigger_mode = "突破反转位主升确认"

        if triggered:
            stop_price = round(max(ma20 * 0.97, ch_supp * 0.97, current_price * 0.95), 2)
            buy_zone = f"{round(current_price * 0.995, 2)} ~ {round(current_price * 1.01, 2)}"
            
            sell_info_str = f"曾于{sell_dt[:10]}在{sell_p:.2f}元止损" if sell_p > 0 else "曾建仓止损离场"
            reason = (
                f"{sell_info_str}, 现于支撑位企稳并{trigger_mode}(突破{reversal_level:.2f}元), "
                f"主升结构确立, 触发反转回补!"
            )
            return {
                "is_reentry": True,
                "buy_type": "💎 割肉反转回补",
                "buy_tag": "RE_ENTRY_BUY",
                "reason": reason,
                "buy_zone": buy_zone,
                "stop_loss": stop_price,
                "type_priority": 97
            }

        return default_res


_GLOBAL_REENTRY_TRACKER = None

def get_reentry_tracker() -> ReentryTracker:
    """全局获取割肉回补雷达实例"""
    global _GLOBAL_REENTRY_TRACKER
    if _GLOBAL_REENTRY_TRACKER is None:
        _GLOBAL_REENTRY_TRACKER = ReentryTracker()
    return _GLOBAL_REENTRY_TRACKER
