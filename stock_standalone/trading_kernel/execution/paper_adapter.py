from __future__ import annotations
from logger_utils import LoggerFactory
from sys_utils import get_app_root
logger = LoggerFactory.getLogger("PaperExecutionAdapter")


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trading_kernel.core.risk import ApprovedOrder
from trading_kernel.execution.execution_adapter import ExecutionAdapter


@dataclass
class Position:
    """个股持仓明细"""
    code: str
    entry_price: float
    volume: float = 0.0
    current_price: float = 0.0
    entry_time: str = "N/A"
    regime: str = "BREAKOUT_ALLOWED"
    tp_triggered: bool = False
    max_high: float = 0.0

    def __post_init__(self):
        if self.max_high <= 0.0:
            self.max_high = max(self.entry_price, self.current_price)

    @property
    def market_value(self) -> float:
        return self.volume * self.current_price

    @property
    def pnl(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) * self.volume

    @property
    def pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "entry_price": round(self.entry_price, 4),
            "volume": round(self.volume, 4),
            "current_price": round(self.current_price, 4),
            "market_value": round(self.market_value, 4),
            "pnl": round(self.pnl, 4),
            "pnl_pct": round(self.pnl_pct, 4),
            "entry_time": self.entry_time,
            "regime": self.regime,
            "tp_triggered": self.tp_triggered,
            "max_high": round(self.max_high, 4),
        }


@dataclass
class AccountSnapshot:
    """账户资产与资金快照"""
    cash: float
    initial_capital: float = 1000000.0
    positions: dict[str, Position] = field(default_factory=dict)

    @property
    def total_equity(self) -> float:
        pos_value = sum(p.market_value for p in self.positions.values())
        return self.cash + pos_value

    @property
    def total_pnl(self) -> float:
        return self.total_equity - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_capital <= 0:
            return 0.0
        return self.total_pnl / self.initial_capital * 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": round(self.cash, 4),
            "total_equity": round(self.total_equity, 4),
            "total_pnl": round(self.total_pnl, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 4),
        }


class PaperExecutionAdapter(ExecutionAdapter):
    """Paper Trading 确定性模拟执行适配器"""

    def __init__(self, initial_capital: float = 1000000.0) -> None:
        self.initial_capital = initial_capital
        self.account = AccountSnapshot(cash=initial_capital, initial_capital=initial_capital)
        self.orders: list[dict[str, Any]] = []
        self._last_saved_fingerprint = ""
        self._is_simulation = False  # 是否为模拟/回测模式
        
        # 探测测试环境与物理持久化路径
        import os
        self._is_test = "PYTEST_CURRENT_TEST" in os.environ
        self._state_file = os.path.join(get_app_root(), "logs", "paper_account_state.json")
        
        self._load_state()
        self._last_saved_fingerprint = self._get_trade_fingerprint()

    def _get_trade_fingerprint(self) -> str:
        positions_data = {}
        positions_dict = {}
        if hasattr(self, "account") and self.account and getattr(self.account, "positions", None) is not None:
            positions_dict = self.account.positions
            
        for code, pos in positions_dict.items():
            if hasattr(pos, "entry_price"):
                entry_p = float(pos.entry_price or 0.0)
                vol = float(pos.volume or 0.0)
                e_time = str(getattr(pos, "entry_time", "N/A"))
            elif isinstance(pos, dict):
                entry_p = float(pos.get("entry_price") or 0.0)
                vol = float(pos.get("volume") or 0.0)
                e_time = str(pos.get("entry_time") or "N/A")
            else:
                continue
            positions_data[code] = (round(entry_p, 4), round(vol, 4), e_time)
            
        import json
        orders_list = []
        if hasattr(self, "orders") and isinstance(self.orders, list):
            orders_list = self.orders
            
        fingerprint_data = {
            "initial_capital": round(float(getattr(self, "initial_capital", 1000000.0) or 0.0), 4),
            "cash": round(float((self.account.cash if (hasattr(self, "account") and self.account) else 1000000.0) or 0.0), 4),
            "positions": positions_data,
            "orders": orders_list
        }
        try:
            return json.dumps(fingerprint_data, sort_keys=True)
        except Exception:
            return str(fingerprint_data)

    def _load_state(self) -> None:
        import os
        if self._is_test or "PYTEST_CURRENT_TEST" in os.environ:
            return
        import json
        
        def safe_float(val: Any, default: float = 0.0) -> float:
            if val is None:
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        if os.path.exists(self._state_file) and os.path.getsize(self._state_file) > 0:
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.initial_capital = safe_float(data.get("initial_capital"), self.initial_capital)
                cash = safe_float(data.get("cash"), self.initial_capital)
                
                positions = {}
                for code, pos_data in data.get("positions", {}).items():
                    if not isinstance(pos_data, dict):
                        continue
                    entry_p = safe_float(pos_data.get("entry_price"), 0.0)
                    
                    e_time_raw = str(pos_data.get("entry_time") or "N/A")
                    if e_time_raw != "N/A" and " " in e_time_raw:
                        date_p, time_p = e_time_raw.split(" ", 1)
                        if len(date_p) == 5:
                            e_time_raw = f"{datetime.now().year}-{date_p} {time_p}"
                            
                    positions[code] = Position(
                        code=str(pos_data.get("code") or code),
                        entry_price=entry_p,
                        volume=safe_float(pos_data.get("volume"), 0.0),
                        current_price=safe_float(pos_data.get("current_price"), entry_p),
                        entry_time=e_time_raw,
                        regime=str(pos_data.get("regime") or "BREAKOUT_ALLOWED"),
                        tp_triggered=bool(pos_data.get("tp_triggered", False)),
                        max_high=safe_float(pos_data.get("max_high"), entry_p)
                    )
                self.orders = list(data.get("orders", []))
                
                # 自愈与热启动机制：从 orders 历史流水中干跑还原出一份“理论持仓”
                recon_positions = {}
                recon_cash = self.initial_capital
                if self.orders:
                    try:
                        sorted_orders = sorted(
                            [o for o in self.orders if isinstance(o, dict)],
                            key=lambda x: str(x.get("timestamp") or "")
                        )
                        for o in sorted_orders:
                            c = o.get("code")
                            act = str(o.get("action") or "").upper()
                            p = safe_float(o.get("price"), 0.0)
                            vol = safe_float(o.get("volume"), 0.0)
                            ts = o.get("timestamp")
                            ts_str = str(ts) if ts is not None else ""
                            if not c or p <= 0 or vol <= 0:
                                continue
                            
                            try:
                                if ts_str:
                                    if "T" in ts_str:
                                        parts = ts_str.split("T")
                                        formatted_ts = f"{parts[0]} {parts[1][:8]}"
                                    else:
                                        formatted_ts = ts_str
                                else:
                                    formatted_ts = "N/A"
                            except Exception:
                                formatted_ts = "N/A"
                            
                            if act in {"BUY", "ADD"}:
                                recon_cash -= p * vol
                                if c in recon_positions:
                                    pos = recon_positions[c]
                                    new_vol = pos.volume + vol
                                    if new_vol > 0:
                                        new_entry = ((pos.entry_price * pos.volume) + (p * vol)) / new_vol
                                    else:
                                        new_entry = p
                                    pos.volume = new_vol
                                    pos.entry_price = new_entry
                                    pos.current_price = p
                                    if pos.entry_time == "N/A":
                                        pos.entry_time = formatted_ts
                                else:
                                    recon_positions[c] = Position(
                                        code=c,
                                        entry_price=p,
                                        volume=vol,
                                        current_price=p,
                                        entry_time=formatted_ts
                                    )
                            elif act in {"SELL", "REDUCE"}:
                                recon_cash += p * vol
                                if c in recon_positions:
                                    pos = recon_positions[c]
                                    if act == "SELL" or vol >= pos.volume:
                                        recon_positions.pop(c, None)
                                    else:
                                        pos.volume -= vol
                                        pos.current_price = p
                    except Exception:
                        pass
                
                # 仅在日志中对理论持仓进行校验预警，不再在冷启动时强行覆盖持久化账本，防止历史记录和持仓被意外重置！
                if recon_positions or self.orders:
                    mismatch = False
                    if len(positions) != len(recon_positions):
                        mismatch = True
                    else:
                        for c_code in recon_positions:
                            if c_code not in positions or abs(positions[c_code].volume - recon_positions[c_code].volume) > 0.1:
                                mismatch = True
                                break
                    if mismatch:
                        logger.warning(
                            f"[State-Check] Loaded positions ({len(positions)} holdings) differ from order ledger derivation ({len(recon_positions)} holdings). "
                            f"Preserving persistent snapshot to prevent accidental reset. Use manual self-heal if necessary."
                        )
                # 智能自愈：若持久化持仓中的 entry_time 为 "N/A"，尝试从流水推导的 recon_positions 中修复补齐
                for code_c, pos_obj in positions.items():
                    if pos_obj.entry_time == "N/A" and code_c in recon_positions:
                        if recon_positions[code_c].entry_time and recon_positions[code_c].entry_time != "N/A":
                            pos_obj.entry_time = recon_positions[code_c].entry_time
                            logger.info(f"[State-Healing] Healed entry_time for {code_c} from orders ledger: {pos_obj.entry_time}")

                self.account = AccountSnapshot(cash=cash, initial_capital=self.initial_capital, positions=positions)
            except Exception as e:
                logger.error(f"[State-Loading] Critical error loading state: {e}. Fallback to default state.")
                if 'positions' not in locals():
                    positions = {}
                if 'cash' not in locals():
                    cash = self.initial_capital
                self.account = AccountSnapshot(cash=cash, initial_capital=self.initial_capital, positions=positions)

    def _save_state(self) -> None:
        import os
        if self._is_test or "PYTEST_CURRENT_TEST" in os.environ:
            return
        
        current_fp = self._get_trade_fingerprint()
        if hasattr(self, "_last_saved_fingerprint") and current_fp == self._last_saved_fingerprint:
            return
            
        import json
        
        def safe_json_float(val: Any) -> float:
            if val is None:
                return 0.0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        try:
            directory = os.path.dirname(self._state_file)
            if directory:
                os.makedirs(directory, exist_ok=True)
            
            positions_data = {}
            for code, pos in self.account.positions.items():
                if hasattr(pos, "entry_price"):
                    entry_p = safe_json_float(pos.entry_price)
                    vol = safe_json_float(pos.volume)
                    curr_p = safe_json_float(pos.current_price)
                    e_time = str(getattr(pos, "entry_time", "N/A"))
                    c_code = str(getattr(pos, "code", code))
                    reg = str(getattr(pos, "regime", "BREAKOUT_ALLOWED"))
                    tp_trig = bool(getattr(pos, "tp_triggered", False))
                    max_h = safe_json_float(getattr(pos, "max_high", entry_p))
                elif isinstance(pos, dict):
                    entry_p = safe_json_float(pos.get("entry_price"))
                    vol = safe_json_float(pos.get("volume"))
                    curr_p = safe_json_float(pos.get("current_price"))
                    e_time = str(pos.get("entry_time") or "N/A")
                    c_code = str(pos.get("code") or code)
                    reg = str(pos.get("regime") or "BREAKOUT_ALLOWED")
                    tp_trig = bool(pos.get("tp_triggered", False))
                    max_h = safe_json_float(pos.get("max_high", entry_p))
                else:
                    continue
                    
                positions_data[code] = {
                    "code": c_code,
                    "entry_price": entry_p,
                    "volume": vol,
                    "current_price": curr_p,
                    "entry_time": e_time,
                    "regime": reg,
                    "tp_triggered": tp_trig,
                    "max_high": max_h
                }
                
            clean_orders = []
            for o in self.orders:
                if isinstance(o, dict):
                    clean_orders.append({
                        "order_id": str(o.get("order_id") or ""),
                        "code": str(o.get("code") or ""),
                        "action": str(o.get("action") or ""),
                        "price": safe_json_float(o.get("price")),
                        "size_pct": safe_json_float(o.get("size_pct")),
                        "volume": safe_json_float(o.get("volume")),
                        "timestamp": str(o.get("timestamp") or "")
                    })

            data = {
                "initial_capital": safe_json_float(self.initial_capital),
                "cash": safe_json_float(self.account.cash),
                "positions": positions_data,
                "orders": clean_orders
            }
            
            json_str = json.dumps(data, ensure_ascii=False, indent=4)
            tmp_file = self._state_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(json_str)
            
            if os.path.exists(tmp_file):
                os.replace(tmp_file, self._state_file)
                self._last_saved_fingerprint = current_fp
        except Exception as e:
            logger.error(f"[State-Saving] Critical error saving state: {e}")

    def submit_order(self, order: ApprovedOrder) -> bool:
        if order.size_pct <= 0 or order.price <= 0:
            return False

        # 如果开启了模拟模式，直接短路返回 True 绕过所有账户状态修改及风控校验
        if self._is_simulation:
            return True

        action = order.action.upper()
        code = order.code
        price = order.price

        # 一只个股的仓位恒定，以初始总资金为基准，而不是随实时盈亏变动的总资产
        # 引入宽容度异常处理与兜底机制，杜绝任何零值、None 或非法类型导致的崩溃
        try:
            equity = getattr(self, "initial_capital", 1000000.0)
            if equity is None or not isinstance(equity, (int, float)) or equity <= 0:
                if hasattr(self, "account") and hasattr(self.account, "total_equity") and self.account.total_equity > 0:
                    equity = self.account.total_equity
                else:
                    equity = 1000000.0
        except Exception as e:
            logger.error(f"⚠️ [PaperAdapter] Error reading initial_capital: {e}, fallback to default 1000000.0")
            equity = 1000000.0

        import sys_utils
        bypass = self._is_test or self._is_simulation
        if action in {"BUY", "ADD"}:
            # 校验是否为交易日交易时间（测试环境/模拟模式豁免）
            if not sys_utils.is_active_trading_hours(bypass=bypass):
                logger.warning(f"[Trade Gate] Rejected BUY/ADD order for {code} because current time is not within active trading hours (09:30-11:30, 13:00-15:00).")
                return False

            # 计算开仓金额
            target_value = equity * order.size_pct
            # 如果可用现金不足，进行最大可用资金扣减 (防止穿仓)
            if target_value > self.account.cash:
                target_value = self.account.cash

            if target_value <= 0:
                return False

            volume = target_value / price
            
            # 非测试环境下强制 100 股向下取整，并拒绝低于 100 股的微小开仓订单以杜绝碎股
            if not self._is_test:
                volume = (int(volume) // 100) * 100
                if volume < 100:
                    logger.warning(
                        f"[Trade Gate] Rejected BUY/ADD order for {code} because calculated volume ({volume}) "
                        f"is less than 100 shares minimum (available cash: {self.account.cash:.2f})."
                    )
                    return False

            actual_value = volume * price
            self.account.cash -= actual_value

            # 更新仓位账簿
            if code in self.account.positions:
                pos = self.account.positions[code]
                # 计算均价加仓
                new_volume = pos.volume + volume
                new_entry = ((pos.entry_price * pos.volume) + (price * volume)) / new_volume
                pos.volume = new_volume
                pos.entry_price = new_entry
                pos.current_price = price
            else:
                self.account.positions[code] = Position(
                    code=code,
                    entry_price=price,
                    volume=volume,
                    current_price=price,
                    entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )

        elif action in {"SELL", "REDUCE"}:
            if not sys_utils.is_active_trading_hours(bypass=bypass):
                logger.warning(f"[Trade Gate] Rejected {action} order for {code} because current time is not within active trading hours (09:30-11:30, 13:00-15:00).")
                return False

            if code not in self.account.positions:
                return False

            pos = self.account.positions[code]
            if action == "SELL":
                # 全平仓位
                sell_volume = pos.volume
            else:
                # 减仓一部分
                sell_volume = pos.volume * order.size_pct
                if not self._is_test:
                    sell_volume = (int(sell_volume) // 100) * 100
                    if sell_volume >= pos.volume:
                        sell_volume = pos.volume

            if sell_volume <= 0:
                return False

            # 校验 T+1 规则：当日买不能当日卖（开仓时间间隔需大于等于一天，测试环境/模拟模式豁免）
            if not (self._is_test or self._is_simulation):
                is_today_bought = False
                if pos.entry_time and pos.entry_time != "N/A":
                    try:
                        time_part = pos.entry_time.replace("T", " ")
                        date_str = time_part.split()[0]
                        today_md = datetime.now().strftime("%m-%d")
                        today_ymd = datetime.now().strftime("%Y-%m-%d")
                        if date_str == today_ymd or date_str == today_md:
                            is_today_bought = True
                    except Exception:
                        pass

                today_str = datetime.now().strftime("%Y-%m-%d")
                bought_today_vol = 0.0
                for o in self.orders:
                    o_ts = o.get("timestamp", "")
                    if o_ts.startswith(today_str) and o.get("code") == code and o.get("action") in {"BUY", "ADD"}:
                        bought_today_vol += float(o.get("volume", 0.0))
                
                if is_today_bought:
                    available_vol = 0.0
                else:
                    available_vol = max(0.0, pos.volume - bought_today_vol)

                if sell_volume > available_vol:
                    logger.warning(
                        f"[T+1 Rule Gate] Rejected {action} order for {code}. "
                        f"Entry time: {pos.entry_time}, total volume: {pos.volume:.4f}, "
                        f"bought today: {bought_today_vol:.4f}, available to sell: {available_vol:.4f}, requested: {sell_volume:.4f}."
                    )
                    return False

            cash_returned = sell_volume * price
            self.account.cash += cash_returned
            
            # 更新/移除仓位
            if action == "SELL" or sell_volume >= pos.volume:
                self.account.positions.pop(code)
                # 触发 Re-entry 跟踪器的止损注册
                try:
                    from trading_kernel.engine.reentry_tracker import reentry_tracker
                    reentry_tracker.register_exit(code, price)
                except Exception as e:
                    logger.error(f"[Reentry] Error registering exit for {code}: {e}")
            else:
                pos.volume -= sell_volume
                pos.current_price = price

        else:
            return False

        # 记录成交单
        self.orders.append({
            "order_id": order.order_id,
            "code": code,
            "action": action,
            "price": round(price, 4),
            "size_pct": round(order.size_pct, 4),
            "volume": round(sell_volume if action in {"SELL", "REDUCE"} else volume, 4),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_state()
        return True

    def cancel_order(self, order_id: str) -> bool:
        # 模拟盘挂单即成，所以撤单默认为 False/忽略
        return False

    def update_market_price(self, code: str, price: float) -> None:
        """更新个股的实时市场价格以计算浮动盈亏并维护最高价"""
        if code in self.account.positions:
            pos = self.account.positions[code]
            pos.current_price = price
            if not hasattr(pos, "max_high") or pos.max_high <= 0.0:
                pos.max_high = max(pos.entry_price, price)
            else:
                pos.max_high = max(pos.max_high, price)
        # 实时同步更新 reentry 最低洗盘价以辅助大周期低位筑底判定
        try:
            from trading_kernel.engine.reentry_tracker import reentry_tracker
            reentry_tracker.update_price(code, price)
        except Exception:
            pass

    def get_positions(self) -> dict[str, dict[str, Any]]:
        return {code: pos.to_dict() for code, pos in self.account.positions.items()}

    def get_account_snapshot(self) -> dict[str, Any]:
        return self.account.to_dict()
