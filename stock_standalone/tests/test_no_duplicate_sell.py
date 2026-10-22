# -*- coding: utf-8 -*-
"""回归测试：当日已卖出标的不得被「内核反哺」回灌，避免 15 秒重复卖出死循环。

对应缺陷：sync_with_legacy_gateway 第 1 步无条件把内核持仓写回老网关，
而老网关在止损卖出后已把该标的加入 _today_sold_codes。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from trading_kernel.kernel_service import TradingKernelService  # noqa: E402
from trading_kernel.execution.paper_adapter import Position as PaperPosition  # noqa: E402
from trade_gateway import Position as LegacyPosition  # noqa: E402


class _Account:
    def __init__(self, positions):
        import threading
        self.positions = positions
        self.cash = 1_000_000.0
        self.initial_capital = 1_000_000.0
        self._lock = threading.RLock()


class _Adapter:
    def __init__(self, positions):
        self.account = _Account(positions)
        self.initial_capital = 1_000_000.0

    def _save_state(self):
        pass


class _Risk:
    total_capital = 1_000_000.0


class _Gateway:
    def __init__(self, positions, sold_codes):
        import threading
        self._positions = positions
        self._today_sold_codes = set(sold_codes)
        self._lock = threading.RLock()
        self.risk_manager = _Risk()

    def get_positions(self):
        return [
            {"code": c, "shares": p.shares, "entry_price": p.entry_price,
             "current_price": p.current_price}
            for c, p in self._positions.items()
        ]


def _paper_pos(code, price=20.0, vol=100, entry_time="2026-10-20 10:00:00"):
    return PaperPosition(code=code, entry_price=price, volume=vol,
                         current_price=price, entry_time=entry_time)


def _legacy_pos(code, price=20.0, vol=100):
    from datetime import datetime
    return LegacyPosition(code=code, name=code, sector="", entry_price=price,
                          entry_time=datetime(2026, 10, 20, 10, 0, 0), shares=vol,
                          position_value=price * vol, strategy_tag="t",
                          stop_loss=price * 0.98, current_price=price,
                          pnl_pct=0.0, pnl_value=0.0, day_high=price)


def _service(kernel_positions):
    svc = TradingKernelService.__new__(TradingKernelService)
    svc.paper_adapter = _Adapter(kernel_positions)
    return svc


def test_sold_today_is_not_restored_to_gateway():
    """300540 今日已卖出，且是昨日建立的陈旧持仓：不得回灌老网关。"""
    svc = _service({"300540": _paper_pos("300540", entry_time="2026-10-20 10:00:00")})
    gw = _Gateway({}, ["300540"])

    result = svc.sync_with_legacy_gateway(trade_gw=gw)

    assert "300540" not in gw._positions, "已卖出标的被反哺回老网关，会触发重复卖出"
    assert result["sold_today_skipped"] == 1
    # 第 3 步应把它从内核账本清掉，两侧收敛
    assert "300540" not in svc.paper_adapter.account.positions


def test_same_day_rebuy_is_restored():
    """当日卖出后又合法回补的新仓（entry_time 为今日）必须放行反哺，并解除当日卖出标记。"""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    svc = _service({"300540": _paper_pos("300540", entry_time="%s 14:05:00" % today)})
    gw = _Gateway({}, ["300540"])

    result = svc.sync_with_legacy_gateway(trade_gw=gw)

    assert "300540" in gw._positions, "当日回补的新仓被误判为陈旧持仓，反哺被阻断"
    assert result["sold_today_skipped"] == 0
    assert "300540" in svc.paper_adapter.account.positions, "新仓不应被第 3 步清掉"
    assert "300540" not in gw._today_sold_codes, "回补后仍带当日卖出标记，止损会被永久拒绝"
    assert result["rebuy_unlocked"] == 1


def test_unknown_entry_time_is_restored():
    """entry_time 无法解析时按保守方向放行，避免误删真实持仓。"""
    svc = _service({"300540": _paper_pos("300540", entry_time="")})
    gw = _Gateway({}, ["300540"])

    result = svc.sync_with_legacy_gateway(trade_gw=gw)

    assert "300540" in gw._positions
    assert result["sold_today_skipped"] == 0


def test_untouched_position_is_still_restored():
    """未卖出的标的仍应正常自愈反哺，不能把功能改坏。"""
    svc = _service({"600000": _paper_pos("600000")})
    gw = _Gateway({}, [])

    result = svc.sync_with_legacy_gateway(trade_gw=gw)

    assert "600000" in gw._positions, "正常持仓必须仍能反哺自愈"
    assert result["restored_to_gw"] == 1
    assert result["sold_today_skipped"] == 0


def test_gateway_holding_wins_without_duplicate():
    """老网关已有该持仓时，不应重复写入。"""
    svc = _service({"600000": _paper_pos("600000")})
    gw = _Gateway({"600000": _legacy_pos("600000")}, [])

    result = svc.sync_with_legacy_gateway(trade_gw=gw)

    assert result["restored_to_gw"] == 0
    assert len(gw._positions) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("  PASS  %s" % fn.__name__)
        except AssertionError as exc:
            failed += 1
            print("  FAIL  %s -> %s" % (fn.__name__, exc))
    print("\n  %d/%d 通过" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
