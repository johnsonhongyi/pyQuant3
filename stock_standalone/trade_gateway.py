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
from logger_utils import LoggerFactory
_GATEWAY_LOG_COOLDOWN = {}

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = LoggerFactory.getLogger(__name__)

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

        # 动态加载并持久化风控参数，提供自愈与首创默认值
        try:
            from JohnsonUtil import commonTips as cct
            self.MAX_POSITIONS = cct.CFG.get_with_writeback("general", "risk_max_positions", fallback=10, value_type="int")
            self.MAX_POS_PCT = cct.CFG.get_with_writeback("general", "risk_max_pos_pct", fallback=0.05, value_type="float")
            self.MAX_DAILY_LOSS = cct.CFG.get_with_writeback("general", "risk_max_daily_loss", fallback=0.02, value_type="float")
            self.STOP_LOSS_PCT = cct.CFG.get_with_writeback("general", "risk_stop_loss_pct", fallback=0.02, value_type="float")
        except Exception as e:
            logger.warning(f"[RiskManager] Failed to load parameters from config, fallback to default: {e}")
            self.MAX_POSITIONS = 10
            self.MAX_POS_PCT = 0.05
            self.MAX_DAILY_LOSS = 0.02
            self.STOP_LOSS_PCT = 0.02

    def update_params(self, max_positions: int, max_pos_pct: float, max_daily_loss: float, stop_loss_pct: float):
        """即时更新风控参数并进行物理持久化写入 global.ini"""
        with self._lock:
            self.MAX_POSITIONS = max_positions
            self.MAX_POS_PCT = max_pos_pct
            self.MAX_DAILY_LOSS = max_daily_loss
            self.STOP_LOSS_PCT = stop_loss_pct

            try:
                from JohnsonUtil import commonTips as cct
                cct.CFG.set_value("general", "risk_max_positions", max_positions)
                cct.CFG.set_value("general", "risk_max_pos_pct", max_pos_pct)
                cct.CFG.set_value("general", "risk_max_daily_loss", max_daily_loss)
                cct.CFG.set_value("general", "risk_stop_loss_pct", stop_loss_pct)
                cct.CFG.save()
                logger.info(
                    f"[RiskManager] 风控参数已即时调整并持久化: "
                    f"MAX_POSITIONS={max_positions}, MAX_POS_PCT={max_pos_pct*100:.1f}%, "
                    f"MAX_DAILY_LOSS={max_daily_loss*100:.1f}%, STOP_LOSS_PCT={stop_loss_pct*100:.1f}%"
                )
            except Exception as e:
                logger.error(f"[RiskManager] Failed to persist adjusted parameters: {e}")

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
        # 在非交易时间，如果既不是单元测试，也不是回测模拟，则不记录亏损与锁仓，防止冷启动或晚上打开时发生状态污染
        import sys
        try:
            from signal_grading_hub import get_signal_grading_hub
            is_simulation = get_signal_grading_hub()._simulation_mode
        except Exception:
            is_simulation = False

        is_test = 'pytest' in sys.modules or any('pytest' in arg.lower() for arg in sys.argv)

        import sys_utils
        if not sys_utils.is_active_trading_hours(bypass=is_test or is_simulation):
            return

        with self._lock:
            if loss_amount > 0:
                self._daily_realized_loss += loss_amount
                loss_pct = self._daily_realized_loss / self.total_capital
                if loss_pct >= self.MAX_DAILY_LOSS:
                    if not self._locked:
                        self._locked = True
                        logger.warning(
                            f"⚠️ [RiskManager] 日亏损已达 {loss_pct*100:.2f}%，"
                            f"触发全场锁仓（上限{self.MAX_DAILY_LOSS*100:.0f}%）"
                        )
                    else:
                        logger.debug(
                            f"[RiskManager] 日亏损已达 {loss_pct*100:.2f}%，"
                            f"已处于锁仓状态"
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
        self._non_trade_notified_stop_loss = set()   # 非交易时段已提示止损标的（防高频刷屏）
        self._today_sold_codes = set()
        self.enforce_cooldown_in_test = False
        self._lock = threading.Lock()
        self._init_db()
        # 从本地数据库恢复今日已卖出的股票，保证跨会话冷却状态不丢失
        try:
            from db_utils import SQLiteConnectionManager
            mgr = SQLiteConnectionManager.get_instance(DB_FILE)
            conn = mgr.get_connection()
            c = conn.cursor()
            today_str = datetime.now().strftime("%Y-%m-%d")
            c.execute(
                "SELECT code FROM mock_trade_log WHERE date = ? AND action = 'SELL'",
                (today_str,)
            )
            rows = c.fetchall()
            for r in rows:
                self._today_sold_codes.add(str(r[0]).zfill(6))
            c.close()
        except Exception as e:
            logger.warning(f"[TradeGateway] Failed to restore today sold codes: {e}")

    @property
    def _log_cooldown(self) -> dict[str, float]:
        return _GATEWAY_LOG_COOLDOWN



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
        import sys
        is_test = 'pytest' in sys.modules or any('pytest' in arg.lower() for arg in sys.argv)
        try:
            from signal_grading_hub import get_signal_grading_hub
            is_simulation = get_signal_grading_hub()._simulation_mode
        except Exception:
            is_simulation = False

        import sys_utils
        import time
        if not sys_utils.is_active_trading_hours(bypass=is_test or is_simulation):
            msg = "当前时间不在连续交易时段（09:30-11:30, 13:00-15:00），禁止买入交易"
            now = time.time()
            cooldown_key = f"buy_refuse_hours_{code}"
            if now - _GATEWAY_LOG_COOLDOWN.get(cooldown_key, 0) >= 300:
                logger.warning(f"[TradeGateway] 买入拒绝 {code}: {msg}")
                _GATEWAY_LOG_COOLDOWN[cooldown_key] = now
            return False, msg

        # 今日卖出冷却拦截（测试和回放模拟模式除外，除非显式设定 enforce_cooldown_in_test）
        if self.enforce_cooldown_in_test or not (is_test or is_simulation):
            with self._lock:
                if code in self._today_sold_codes:
                    msg = f"{code} 触发今日卖出冷却拦截：今日已平仓卖出，触发日内再次买入冷却"
                    now = time.time()
                    cooldown_key = f"buy_refuse_sold_{code}"
                    if now - _GATEWAY_LOG_COOLDOWN.get(cooldown_key, 0) >= 300:
                        logger.warning(f"[TradeGateway] 买入拒绝 {code}: {msg}")
                        _GATEWAY_LOG_COOLDOWN[cooldown_key] = now
                    return False, msg

        # 风控检查
        with self._lock:
            pos_count_in_sector = sum(
                1 for p in self._positions.values() if p.sector == sector
            )
            ok, msg = self.risk_manager.can_buy(
                code, price, self._positions, pos_count_in_sector
            )

        if not ok:
            now = time.time()
            cooldown_key = f"buy_refuse_risk_{code}_{msg}"
            if now - _GATEWAY_LOG_COOLDOWN.get(cooldown_key, 0) >= 300:
                logger.warning(f"[TradeGateway] 买入拒绝 {code}: {msg}")
                _GATEWAY_LOG_COOLDOWN[cooldown_key] = now
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
        import sys
        is_test = 'pytest' in sys.modules or any('pytest' in arg.lower() for arg in sys.argv)
        try:
            from signal_grading_hub import get_signal_grading_hub
            is_simulation = get_signal_grading_hub()._simulation_mode
        except Exception:
            is_simulation = False

        import sys_utils
        if not sys_utils.is_active_trading_hours(bypass=is_test or is_simulation):
            msg = "当前时间不在连续交易时段（09:30-11:30, 13:00-15:00），禁止卖出交易"
            logger.warning(f"[TradeGateway] 卖出拒绝 {code}: {msg}")
            return False, msg

        with self._lock:
            pos = self._positions.get(code)
            if pos is None:
                return False, f"{code} 不在持仓中"
            
            # 校验 T+1 规则：当日买不能当日卖（开仓日期不能为今天，测试和回测模拟模式除外）
            if not (is_test or is_simulation):
                if pos.entry_time:
                    entry_date = pos.entry_time.date() if hasattr(pos.entry_time, 'date') else None
                    if not entry_date:
                        try:
                            entry_date = datetime.strptime(str(pos.entry_time).split(" ")[0], "%Y-%m-%d").date()
                        except Exception:
                            pass
                    if entry_date == datetime.now().date():
                        msg = f"{code} 触发 T+1 规则拦截：开仓时间为 {pos.entry_time}，当日买入不能当日平仓"
                        logger.warning(f"[T+1 Rule Gate] {msg}")
                        return False, msg

            pos.update_price(price)
            pnl_pct = pos.pnl_pct
            pnl_val = pos.pnl_value
            shares = pos.shares
            name = pos.name
            sector = pos.sector
            strategy_tag = pos.strategy_tag
            pos.status = "已平仓"
            del self._positions[code]
            self._today_sold_codes.add(code)

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
        import sys
        try:
            from signal_grading_hub import get_signal_grading_hub
            is_simulation = get_signal_grading_hub()._simulation_mode
        except Exception:
            is_simulation = False

        if is_simulation:
            # 赛马回测模拟模式不用走这个流程，直接短路返回
            return

        is_test = 'pytest' in sys.modules or any('pytest' in arg.lower() for arg in sys.argv)

        # 判断当前是否在交易时间内
        import sys_utils
        is_trading_hour = sys_utils.is_active_trading_hours(bypass=False)

        to_sell = []
        with self._lock:
            for code, pos in self._positions.items():
                if pos.current_price > 0 and pos.current_price <= pos.stop_loss:
                    # 校验 T+1 规则：如果当日买入则不能当日止损（测试和回测模拟模式除外）
                    if not (is_test or is_simulation):
                        if pos.entry_time:
                            entry_date = pos.entry_time.date() if hasattr(pos.entry_time, 'date') else None
                            if not entry_date:
                                try:
                                    entry_date = datetime.strptime(str(pos.entry_time).split(" ")[0], "%Y-%m-%d").date()
                                except Exception:
                                    pass
                            if entry_date == datetime.now().date():
                                continue

                    # 如果是非交易时间，且非测试、非回测模拟，则仅提示/执行流程一次，防高频刷屏
                    if not is_trading_hour and not is_test and not is_simulation:
                        if code not in self._non_trade_notified_stop_loss:
                            self._non_trade_notified_stop_loss.add(code)
                            to_sell.append((code, pos.current_price, "触发止损线", pos.name, pos.sector, pos.strategy_tag))
                    else:
                        to_sell.append((code, pos.current_price, "触发止损线", pos.name, pos.sector, pos.strategy_tag))

        for code, price, reason, name, sector, strategy_tag in to_sell:
            # 如果是非交易时间，直接进入拦截提示与流程展示逻辑，不真正提交订单，也不写入决策大表
            if not is_trading_hour and not is_test and not is_simulation:
                pnl_pct = 0.0
                pnl_val = 0.0
                with self._lock:
                    pos = self._positions.get(code)
                    if pos:
                        pnl_pct = pos.pnl_pct
                        pnl_val = pos.pnl_value
                logger.info(
                    f"📉 [模拟卖出] {code}({name}) 价={price:.3f} 盈亏={pnl_pct:+.2f}% ({pnl_val:+.2f}元) | {reason}(非交易时段拦截)"
                )
                logger.warning(f"[Trade Gate] Rejected SELL order for {code} because current time is not within trading hours.")
                continue

            # 正常交易时间或回测模拟时，提交物理订单
            ok, msg = self.submit_sell(code, price, reason)
            if ok:
                # 构造虚拟 SELL 信号，物理写入交易流水，并同步让新交易内核 paper_adapter 执行平仓！
                sig_sell = {
                    "code": code,
                    "name": name,
                    "signal_type": "止损出场",
                    "action": "SELL",
                    "price": price,
                    "current_price": price,
                    "suggest_price": price,
                    "reason": reason,
                    "journal_ts": datetime.now().isoformat(),
                    "created_at": datetime.now().isoformat(),
                }
                try:
                    from trading_kernel.kernel_service import enrich_decision_item
                    enrich_decision_item(sig_sell, write_journal=True)
                except Exception as e_journal:
                    logger.warning(f"Error enriching stop-loss sell journal: {e_journal}")

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
            self._non_trade_notified_stop_loss.clear()
            self._today_sold_codes.clear()
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
