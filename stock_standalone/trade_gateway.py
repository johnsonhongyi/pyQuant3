# -*- coding: utf-8 -*-
"""
TradeGateway — 模拟交易网关 + 风控管理
========================================
核心能力：
  1. MockTradeGateway  — 模拟下单（打印委托指令，不接真实行情）
  2. RiskManager       — 风控约束（单笔5%、日亏损2%、最多10持仓）
  3. PositionTracker   — 持仓盈亏实时追踪
  4. TradeLog          — 今日交易流水记录（内存 + SQLite持久化）

约束参数（已由用户确认）：
  MAX_POSITIONS    = 10          # 最多同时持有10只
  MAX_POS_PCT      = 0.05        # 每只单笔仓位≤总资金5%
  MAX_DAILY_LOSS   = 0.02        # 日亏损上限2%（超出后锁仓）
  MAX_FOLLOWERS    = 3           # 每板块跟进股≤3只（由 sector_focus_engine 控制）

设计原则：
  - 不破坏现有接口，以外挂形式运行
  - 模拟模式下只记录「应该下单」的指令，不真实下单
  - 所有数据写入 SQLite（signal_strategy.db复用DB_FILE）
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# DB 文件复用 hotlist_panel 中同一个库
DB_FILE = "signal_strategy.db"


# ─────────────────────────────────────────────────────────────────────────────
# §1  数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Position:
    """单笔持仓"""
    code: str
    name: str
    sector: str
    entry_price: float           # 入场价
    entry_time: datetime         # 入场时间
    shares: int                  # 持有股数
    position_value: float        # 入场市值（entry_price * shares）
    strategy_tag: str            # 入场策略标签
    stop_loss: float             # 止损价（入场后-2%）
    current_price: float  = 0.0
    pnl_pct: float        = 0.0  # 当前盈亏%
    pnl_value: float      = 0.0  # 当前盈亏金额
    day_high: float       = 0.0  # 日内最高价（用于离场判断）
    status: str           = "持有"  # 持有/止盈/止损/手动平仓

    def update_price(self, price: float):
        if price > 0:
            self.current_price = price
            self.pnl_pct = (price - self.entry_price) / self.entry_price * 100
            self.pnl_value = (price - self.entry_price) * self.shares
            if price > self.day_high:
                self.day_high = price

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'entry_price': round(self.entry_price, 3),
            'entry_time': self.entry_time.strftime('%H:%M:%S'),
            'shares': self.shares,
            'position_value': round(self.position_value, 2),
            'strategy_tag': self.strategy_tag,
            'stop_loss': round(self.stop_loss, 3),
            'current_price': round(self.current_price, 3),
            'pnl_pct': round(self.pnl_pct, 2),
            'pnl_value': round(self.pnl_value, 2),
            'day_high': round(self.day_high, 3),
            'status': self.status,
        }


@dataclass
class TradeRecord:
    """交易流水记录"""
    id: int                 = 0
    date: str               = ""
    time: str               = ""
    code: str               = ""
    name: str               = ""
    sector: str             = ""
    action: str             = ""    # BUY / SELL
    price: float            = 0.0
    shares: int             = 0
    amount: float           = 0.0
    reason: str             = ""
    strategy_tag: str       = ""
    pnl_pct: float          = 0.0   # 卖出时填入
    is_simulated: bool      = True  # 是否模拟单


# ─────────────────────────────────────────────────────────────────────────────
# §2  风控管理器（RiskManager）
# ─────────────────────────────────────────────────────────────────────────────

class RiskManager:
    """
    风控约束检查
    ─────────────
    在任何买入操作前调用 can_buy() 以确保不违反风控规则。
    """

    MAX_POSITIONS  = 10     # 最大持仓数
    MAX_POS_PCT    = 0.05   # 单笔仓位不超过总资金5%
    MAX_DAILY_LOSS = 0.02   # 日亏损上限2%（超出后锁仓、禁止新建）
    STOP_LOSS_PCT  = 0.02   # 入场后止损线-2%

    def __init__(self, total_capital: float = 100_000.0):
        self.total_capital    = total_capital   # 总资金（默认10万，可配置）
        self._daily_realized_loss: float = 0.0  # 今日已实现亏损额
        self._lock = threading.Lock()
        self._locked = False  # 日亏损上限触发时全局锁仓

    # ── 买入前检查 ────────────────────────────────────────────────────────────

    def can_buy(
        self,
        code: str,
        price: float,
        current_positions: Dict[str, Position],
        current_sector_positions: int = 0,  # 当前该板块已有几只
    ) -> tuple[bool, str]:
        """
        返回 (可以买入, 拒绝原因)
        """
        with self._lock:
            # 1. 全局锁仓（日亏损超限）
            if self._locked:
                return False, f"日亏损上限已触发（≥{self.MAX_DAILY_LOSS*100:.0f}%），全场停止新建"

            # 2. 持仓数量上限
            if len(current_positions) >= self.MAX_POSITIONS:
                return False, f"持仓已达上限 {self.MAX_POSITIONS} 只，无法新建"

            # 3. 重复持仓
            if code in current_positions:
                return False, f"已持有 {code}，不重复加仓（如需加仓请手动操作）"

            # 4. 仓位大小
            position_amount = price * self._calc_shares(price)
            if position_amount > self.total_capital * self.MAX_POS_PCT * 1.1:
                return False, f"单笔仓位超过资金{self.MAX_POS_PCT*100:.0f}%上限"

        return True, ""

    def calc_buy_shares(self, price: float) -> int:
        """计算该笔建议股数（不超过5%仓位，按100手取整）"""
        return self._calc_shares(price)

    def _calc_shares(self, price: float) -> int:
        if price <= 0:
            return 0
        max_amount = self.total_capital * self.MAX_POS_PCT
        raw_shares = int(max_amount / price)
        # 取整到100股
        shares = max(100, (raw_shares // 100) * 100)
        return shares

    def calc_stop_loss(self, entry_price: float) -> float:
        """计算止损价（入场价 × (1 - 2%)）"""
        return round(entry_price * (1 - self.STOP_LOSS_PCT), 3)

    # ── 日内亏损追踪 ──────────────────────────────────────────────────────────

    def record_realized_loss(self, loss_amount: float):
        """卖出后记录实现的亏损（正数为亏损金额）"""
        with self._lock:
            if loss_amount > 0:
                self._daily_realized_loss += loss_amount
                loss_pct = self._daily_realized_loss / self.total_capital
                if loss_pct >= self.MAX_DAILY_LOSS:
                    self._locked = True
                    logger.warning(
                        f"⚠️ [RiskManager] 日亏损已达 {loss_pct*100:.2f}%，"
                        f"触发全场锁仓（上限{self.MAX_DAILY_LOSS*100:.0f}%）"
                    )

    def reset_day(self):
        """每日开盘前重置"""
        with self._lock:
            self._daily_realized_loss = 0.0
            self._locked = False

    @property
    def daily_loss_pct(self) -> float:
        with self._lock:
            return self._daily_realized_loss / self.total_capital if self.total_capital > 0 else 0.0

    @property
    def is_locked(self) -> bool:
        with self._lock:
            return self._locked


# ─────────────────────────────────────────────────────────────────────────────
# §3  模拟交易网关（MockTradeGateway）
# ─────────────────────────────────────────────────────────────────────────────

class MockTradeGateway:
    """
    模拟交易执行（不接真实账户）
    ──────────────────────────────
    - 记录「应该下单」的委托指令到日志 + SQLite
    - 维护模拟持仓状态
    - 提供 UI 展示接口
    """

    def __init__(self, total_capital: float = 100_000.0):
        self.risk_manager = RiskManager(total_capital=total_capital)
        self._positions: Dict[str, Position] = {}   # {code: Position}
        self._trade_log: List[TradeRecord] = []      # 今日流水（内存）
        self._lock = threading.Lock()
        self._init_db()

    # ── DB 初始化 ──────────────────────────────────────────────────────────────

    def _init_db(self):
        """确保交易流水表存在"""
        try:
            from db_utils import SQLiteConnectionManager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS mock_trade_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT NOT NULL,
                    time        TEXT NOT NULL,
                    code        TEXT NOT NULL,
                    name        TEXT,
                    sector      TEXT,
                    action      TEXT NOT NULL,
                    price       REAL,
                    shares      INTEGER,
                    amount      REAL,
                    reason      TEXT,
                    strategy_tag TEXT,
                    pnl_pct     REAL,
                    is_simulated INTEGER DEFAULT 1
                )
            """)
            conn.commit()
            c.close()
        except Exception as e:
            logger.warning(f"[TradeGateway] DB init failed: {e}")

    # ── 模拟买入 ──────────────────────────────────────────────────────────────

    def submit_buy(
        self,
        code: str,
        name: str,
        sector: str,
        price: float,
        strategy_tag: str = "",
        reason: str = "",
    ) -> tuple[bool, str]:
        """
        提交模拟买入委托

        Returns:
            (success, message)
        """
        # 风控检查
        with self._lock:
            pos_count_in_sector = sum(
                1 for p in self._positions.values() if p.sector == sector
            )
            ok, msg = self.risk_manager.can_buy(
                code, price, self._positions, pos_count_in_sector
            )

        if not ok:
            logger.warning(f"[TradeGateway] 买入拒绝 {code}: {msg}")
            return False, msg

        shares = self.risk_manager.calc_buy_shares(price)
        if shares <= 0:
            return False, "计算股数为0，价格异常"

        stop_loss = self.risk_manager.calc_stop_loss(price)
        amount = price * shares

        position = Position(
            code=code,
            name=name,
            sector=sector,
            entry_price=price,
            entry_time=datetime.now(),
            shares=shares,
            position_value=amount,
            strategy_tag=strategy_tag,
            stop_loss=stop_loss,
            current_price=price,
            day_high=price,
        )

        with self._lock:
            self._positions[code] = position

        # 记录流水
        record = TradeRecord(
            date=datetime.now().strftime('%Y-%m-%d'),
            time=datetime.now().strftime('%H:%M:%S'),
            code=code, name=name, sector=sector,
            action="BUY", price=price, shares=shares,
            amount=amount, reason=reason,
            strategy_tag=strategy_tag,
        )
        self._append_log(record)

        logger.info(
            f"📈 [模拟买入] {code}({name}) "
            f"价={price:.3f} 股数={shares} 金额={amount:.2f} "
            f"止损={stop_loss:.3f} 板块={sector} | {reason}"
        )
        return True, f"模拟买入成功: {code} × {shares}股 @ {price:.3f} (止损{stop_loss:.3f})"

    # ── 模拟卖出 ──────────────────────────────────────────────────────────────

    def submit_sell(
        self,
        code: str,
        price: float,
        reason: str = "",
    ) -> tuple[bool, str]:
        """提交模拟卖出委托"""
        with self._lock:
            pos = self._positions.get(code)
            if pos is None:
                return False, f"{code} 不在持仓中"
            pos.update_price(price)
            pnl_pct = pos.pnl_pct
            pnl_val = pos.pnl_value
            shares = pos.shares
            name = pos.name
            sector = pos.sector
            strategy_tag = pos.strategy_tag
            pos.status = "已平仓"
            del self._positions[code]

        # 记录实现亏损（用于风控监控）
        if pnl_val < 0:
            self.risk_manager.record_realized_loss(-pnl_val)

        record = TradeRecord(
            date=datetime.now().strftime('%Y-%m-%d'),
            time=datetime.now().strftime('%H:%M:%S'),
            code=code, name=name, sector=sector,
            action="SELL", price=price, shares=shares,
            amount=price * shares, reason=reason,
            strategy_tag=strategy_tag, pnl_pct=pnl_pct,
        )
        self._append_log(record)

        emoji = "📈" if pnl_pct >= 0 else "📉"
        logger.info(
            f"{emoji} [模拟卖出] {code}({name}) "
            f"价={price:.3f} 盈亏={pnl_pct:+.2f}% ({pnl_val:+.2f}元) | {reason}"
        )
        return True, f"模拟卖出: {code} 盈亏={pnl_pct:+.2f}% | {reason}"

    # ── 持仓价格更新 ──────────────────────────────────────────────────────────

    def update_prices(self, price_map: Dict[str, float]):
        """批量更新持仓市价（由实时行情推送调用）"""
        with self._lock:
            for code, pos in self._positions.items():
                p = price_map.get(code)
                if p and p > 0:
                    pos.update_price(p)

    def check_stop_loss(self):
        """检查是否触发止损，触发则自动平仓"""
        to_sell = []
        with self._lock:
            for code, pos in self._positions.items():
                if pos.current_price > 0 and pos.current_price <= pos.stop_loss:
                    to_sell.append((code, pos.current_price, "触发止损线"))

        for code, price, reason in to_sell:
            self.submit_sell(code, price, reason)

    # ── 流水记录持久化 ────────────────────────────────────────────────────────

    def _append_log(self, record: TradeRecord):
        """写入内存 + SQLite"""
        with self._lock:
            self._trade_log.append(record)

        try:
            from db_utils import SQLiteConnectionManager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO mock_trade_log
                (date, time, code, name, sector, action, price, shares,
                 amount, reason, strategy_tag, pnl_pct, is_simulated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.date, record.time, record.code, record.name, record.sector,
                record.action, record.price, record.shares, record.amount,
                record.reason, record.strategy_tag, record.pnl_pct, int(record.is_simulated)
            ))
            conn.commit()
            c.close()
        except Exception as e:
            logger.warning(f"[TradeGateway] DB write failed: {e}")

    # ── 对外查询接口 ──────────────────────────────────────────────────────────

    def get_positions(self) -> List[dict]:
        """获取当前持仓（UI展示用）"""
        with self._lock:
            return [p.to_dict() for p in self._positions.values()]

    def get_positions_count(self) -> int:
        with self._lock:
            return len(self._positions)

    def get_sector_positions_count(self, sector: str) -> int:
        with self._lock:
            return sum(1 for p in self._positions.values() if p.sector == sector)

    def get_today_log(self) -> List[dict]:
        """获取今日交易流水（UI展示用）"""
        with self._lock:
            return [
                {
                    'time': r.time, 'code': r.code, 'name': r.name,
                    'action': r.action, 'price': r.price,
                    'shares': r.shares, 'amount': round(r.amount, 2),
                    'reason': r.reason, 'pnl_pct': round(r.pnl_pct, 2),
                }
                for r in self._trade_log
            ]

    def get_summary(self) -> dict:
        """今日汇总统计"""
        with self._lock:
            total_pnl = sum(p.pnl_value for p in self._positions.values())
            realized = sum(r.pnl_pct * r.amount / 100 for r in self._trade_log if r.action == "SELL")
            buy_count = sum(1 for r in self._trade_log if r.action == "BUY")
            sell_count = sum(1 for r in self._trade_log if r.action == "SELL")

        return {
            'position_count': len(self._positions),
            'total_unrealized_pnl': round(total_pnl, 2),
            'total_realized_pnl': round(realized, 2),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'daily_loss_pct': round(self.risk_manager.daily_loss_pct * 100, 2),
            'is_locked': self.risk_manager.is_locked,
        }

    def reset_day(self):
        """每日重置（保留持仓，重置日内流水和风控计数器）"""
        with self._lock:
            self._trade_log.clear()
        self.risk_manager.reset_day()
        logger.info("[TradeGateway] 每日重置完成")


# ─────────────────────────────────────────────────────────────────────────────
# §4  全局单例
# ─────────────────────────────────────────────────────────────────────────────

_gateway_instance: Optional[MockTradeGateway] = None
_gateway_lock = threading.Lock()


def get_trade_gateway(total_capital: float = 100_000.0) -> MockTradeGateway:
    """获取全局 MockTradeGateway 单例"""
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is None:
            _gateway_instance = MockTradeGateway(total_capital=total_capital)
    return _gateway_instance
