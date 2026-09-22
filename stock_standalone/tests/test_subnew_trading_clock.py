"""tests/test_subnew_trading_clock.py

Unit tests for subnew_trading_clock module.
Verifies all requirements and Definition of Done for Task 020:
- 09:30/10:00/11:30/13:00/13:12/15:00 boundary tests
- 11:27 -> 13:00 = 3 minutes
- 11:27 -> 13:12 = 15 minutes and expired with TTL_TRADING_15M
- 09:30 -> 10:00 = 30 minutes
- Cross-day explicitly expired
- Pre-market / post-market clipping, no negative minutes
- Zero business state mutation
"""

import datetime
import pytest

from ats.strategy.subnew_trading_clock import (
    DEFAULT_TTL_MINUTES,
    REASON_TTL_CROSS_DAY,
    REASON_TTL_TRADING_15M,
    TTL_CROSS_DAY,
    TTL_TRADING_15M,
    TradePlanTTLResult,
    evaluate_trade_plan_ttl,
    is_trading_time,
    remaining_trading_minutes_in_day,
    trading_minutes_elapsed,
)


class TestTradingClockBoundaries:
    """Test trading clock boundary points and standard session transitions."""

    def test_boundary_0930_market_open(self):
        # Exact open to exact open: 0 minutes
        assert trading_minutes_elapsed("09:30:00", "09:30:00") == 0.0
        # Pre-market to exact open: clipped to 0 minutes
        assert trading_minutes_elapsed("09:00:00", "09:30:00") == 0.0
        assert trading_minutes_elapsed("09:15:00", "09:30:00") == 0.0
        # Pre-market to open + 5m: clipped start to 09:30 -> 5 minutes
        assert trading_minutes_elapsed("09:15:00", "09:35:00") == 5.0

    def test_boundary_1000(self):
        # 09:30 -> 10:00: 30 minutes
        assert trading_minutes_elapsed("09:30:00", "10:00:00") == 30.0
        assert trading_minutes_elapsed("10:00:00", "10:00:00") == 0.0

    def test_boundary_1130_morning_close(self):
        # 09:30 -> 11:30: full morning session 120 minutes
        assert trading_minutes_elapsed("09:30:00", "11:30:00") == 120.0
        # 11:27 -> 11:30: 3 minutes
        assert trading_minutes_elapsed("11:27:00", "11:30:00") == 3.0
        # Exact close to exact close: 0 minutes
        assert trading_minutes_elapsed("11:30:00", "11:30:00") == 0.0

    def test_boundary_1130_to_1300_lunch_break(self):
        # Lunch break does not accumulate trading minutes
        assert trading_minutes_elapsed("11:30:00", "13:00:00") == 0.0
        assert trading_minutes_elapsed("11:45:00", "12:30:00") == 0.0
        assert trading_minutes_elapsed("12:00:00", "13:00:00") == 0.0
        # DoD requirement: 11:27 -> 13:00 = 3 minutes
        assert trading_minutes_elapsed("11:27:00", "13:00:00") == 3.0
        assert trading_minutes_elapsed("11:27", "13:00") == 3.0

    def test_boundary_1300_afternoon_open(self):
        assert trading_minutes_elapsed("13:00:00", "13:00:00") == 0.0
        # Lunch start to afternoon session
        assert trading_minutes_elapsed("12:15:00", "13:05:00") == 5.0

    def test_boundary_1312_15m_ttl(self):
        # DoD requirement: 11:27 -> 13:12 = 15 minutes
        assert trading_minutes_elapsed("11:27:00", "13:12:00") == 15.0
        assert trading_minutes_elapsed("11:27", "13:12") == 15.0
        # Afternoon open to 13:12: 12 minutes
        assert trading_minutes_elapsed("13:00:00", "13:12:00") == 12.0

    def test_boundary_1500_market_close(self):
        # Afternoon full session: 13:00 -> 15:00 = 120 minutes
        assert trading_minutes_elapsed("13:00:00", "15:00:00") == 120.0
        # Full trading day: 09:30 -> 15:00 = 240 minutes
        assert trading_minutes_elapsed("09:30:00", "15:00:00") == 240.0
        # 14:50 -> 15:00 = 10 minutes
        assert trading_minutes_elapsed("14:50:00", "15:00:00") == 10.0
        # Post-market: 15:00 -> 15:30 = 0 minutes
        assert trading_minutes_elapsed("15:00:00", "15:30:00") == 0.0
        # 14:50 -> 15:30 clipped to 15:00 = 10 minutes
        assert trading_minutes_elapsed("14:50:00", "15:30:00") == 10.0


class TestEvaluateTradePlanTTL:
    """Test TTL evaluation logic, reasons, and edge cases."""

    def test_dod_1127_to_1312_expires_at_15m(self):
        # DoD: 11:27 -> 13:12 = 15 且过期
        res = evaluate_trade_plan_ttl("11:27:00", "13:12:00")
        assert res.elapsed_trading_minutes == 15.0
        assert res.is_expired is True
        assert res.expired_reason == TTL_TRADING_15M
        assert res.expired_reason == REASON_TTL_TRADING_15M

    def test_dod_1127_to_1300_not_expired(self):
        # 11:27 -> 13:00 = 3 < 15, not expired
        res = evaluate_trade_plan_ttl("11:27:00", "13:00:00")
        assert res.elapsed_trading_minutes == 3.0
        assert res.is_expired is False
        assert res.expired_reason is None

    def test_before_15m_boundary(self):
        # 11:27:00 to 13:11:59: 14.9833 minutes, not expired
        res = evaluate_trade_plan_ttl("11:27:00", "13:11:59")
        assert res.elapsed_trading_minutes < 15.0
        assert res.is_expired is False
        assert res.expired_reason is None

    def test_past_15m_boundary(self):
        # 11:27:00 to 13:13:00: 16.0 minutes, expired
        res = evaluate_trade_plan_ttl("11:27:00", "13:13:00")
        assert res.elapsed_trading_minutes == 16.0
        assert res.is_expired is True
        assert res.expired_reason == TTL_TRADING_15M

    def test_cross_day_explicitly_expired(self):
        # DoD: 跨日明确过期
        d1 = "2026-09-20 14:55:00"
        d2 = "2026-09-21 09:35:00"
        res = evaluate_trade_plan_ttl(d1, d2)
        assert res.is_expired is True
        assert res.expired_reason == TTL_CROSS_DAY
        assert res.expired_reason == REASON_TTL_CROSS_DAY
        # 5m on day 1 + 5m on day 2 = 10m elapsed
        assert res.elapsed_trading_minutes == 10.0

    def test_cross_day_small_elapsed_still_expired(self):
        # Created near close yesterday, checked near open today: strictly expired
        d1 = datetime.datetime(2026, 9, 21, 14, 59, 0)
        d2 = datetime.datetime(2026, 9, 22, 9, 31, 0)
        res = evaluate_trade_plan_ttl(d1, d2)
        assert res.is_expired is True
        assert res.expired_reason == TTL_CROSS_DAY
        assert res.elapsed_trading_minutes == 2.0

    def test_custom_ttl_minutes(self):
        # Custom 10m TTL
        res_not_exp = evaluate_trade_plan_ttl("09:30:00", "09:39:00", ttl_minutes=10)
        assert res_not_exp.elapsed_trading_minutes == 9.0
        assert res_not_exp.is_expired is False

        res_exp = evaluate_trade_plan_ttl("09:30:00", "09:40:00", ttl_minutes=10)
        assert res_exp.elapsed_trading_minutes == 10.0
        assert res_exp.is_expired is True
        assert res_exp.expired_reason == TTL_TRADING_15M


class TestInputFormatsAndPurity:
    """Test various input formats, types, and purity of functions."""

    def test_various_input_types(self):
        # datetime objects
        dt1 = datetime.datetime(2026, 9, 21, 9, 30, 0)
        dt2 = datetime.datetime(2026, 9, 21, 10, 0, 0)
        assert trading_minutes_elapsed(dt1, dt2) == 30.0

        # time objects
        t1 = datetime.time(9, 30, 0)
        t2 = datetime.time(10, 0, 0)
        assert trading_minutes_elapsed(t1, t2) == 30.0

        # float timestamps
        ts1 = dt1.timestamp()
        ts2 = dt2.timestamp()
        assert trading_minutes_elapsed(ts1, ts2) == 30.0

        # ISO strings
        assert trading_minutes_elapsed("2026-09-21T09:30:00", "2026-09-21T10:00:00") == 30.0

    def test_pre_market_and_negative_clipping(self):
        # Pre-market to pre-market
        assert trading_minutes_elapsed("09:00:00", "09:15:00") == 0.0
        # Backward time on same day (no negative minutes)
        assert trading_minutes_elapsed("10:00:00", "09:30:00") == 0.0
        # Backward date
        d1 = datetime.datetime(2026, 9, 22, 10, 0, 0)
        d2 = datetime.datetime(2026, 9, 21, 10, 0, 0)
        assert trading_minutes_elapsed(d1, d2) == 0.0

        res_backward = evaluate_trade_plan_ttl(d1, d2)
        assert res_backward.elapsed_trading_minutes == 0.0
        assert res_backward.is_expired is False
        assert res_backward.expired_reason is None

    def test_result_structure_compatibility(self):
        res = evaluate_trade_plan_ttl("11:27", "13:12")
        # 1. NamedTuple attribute access
        assert res.elapsed_trading_minutes == 15.0
        assert res.is_expired is True
        assert res.expired_reason == "TTL_TRADING_15M"

        # 2. Tuple unpacking
        elapsed, expired, reason = res
        assert elapsed == 15.0
        assert expired is True
        assert reason == "TTL_TRADING_15M"

        # 3. Tuple index access
        assert res[0] == 15.0
        assert res[1] is True
        assert res[2] == "TTL_TRADING_15M"

        # 4. Dict key access
        assert res["elapsed_trading_minutes"] == 15.0
        assert res["is_expired"] is True
        assert res["expired_reason"] == "TTL_TRADING_15M"
        assert res["elapsed"] == 15.0
        assert res["reason"] == "TTL_TRADING_15M"

        # 5. Dict get and to_dict
        assert res.get("is_expired") is True
        assert res.get("unknown_key", "default_val") == "default_val"
        d = res.to_dict()
        assert d == {
            "elapsed_trading_minutes": 15.0,
            "is_expired": True,
            "expired_reason": "TTL_TRADING_15M",
        }

    def test_pure_function_zero_state_mutation(self):
        # Verify function purity and idempotency
        t1 = "11:27"
        t2 = "13:00"
        for _ in range(5):
            res = evaluate_trade_plan_ttl(t1, t2)
            assert res.elapsed_trading_minutes == 3.0
            assert res.is_expired is False

    def test_helpers(self):
        # is_trading_time
        assert is_trading_time("09:29:59") is False
        assert is_trading_time("09:30:00") is True
        assert is_trading_time("10:30:00") is True
        assert is_trading_time("11:30:00") is True
        assert is_trading_time("11:30:01") is False
        assert is_trading_time("12:30:00") is False
        assert is_trading_time("13:00:00") is True
        assert is_trading_time("14:30:00") is True
        assert is_trading_time("15:00:00") is True
        assert is_trading_time("15:00:01") is False

        # remaining_trading_minutes_in_day
        assert remaining_trading_minutes_in_day("09:30:00") == 240.0
        assert remaining_trading_minutes_in_day("11:30:00") == 120.0
        assert remaining_trading_minutes_in_day("12:00:00") == 120.0
        assert remaining_trading_minutes_in_day("13:00:00") == 120.0
        assert remaining_trading_minutes_in_day("15:00:00") == 0.0
        assert remaining_trading_minutes_in_day("16:00:00") == 0.0
