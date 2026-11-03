# -*- coding: utf-8 -*-
"""tests/test_fusion_evaluate_p2.py — ATS 梯度 P2 阶段：撮合重构与评估闭环专项单测。

覆盖验收重点：
1. 限价单在 high < lo 时绝不捏造 lo 穿价高价成交，而是按 min(hi, open) 成交；
2. 同一天早盘 bar 先达止盈、下午 bar 才破止损时，逐 bar 推进准确判定为"止盈"；
   同根 bar 内同时双触才判"止损(双触保守)"；
3. T+0 收盘破 VWAP 在 T+1 首根 bar 开盘优先退出，不被盘中后续止盈覆盖；
4. 一字跌停无法卖出时生成 pending_exit，在后续首个可卖出的 bar 立即按 open 恢复退出；
5. 半日残缺数据（最后 bar < 14:57 且开启 require_full_day_close）标记为 IMMATURE_OPEN，不以半日收盘价结案；
6. 净收益换算、五类互斥分母、resolved_net_expectancy 公式、label_available_ts 防泄漏截断、Day-Block Bootstrap 检验与准入门槛。
"""

import time
import unittest
import numpy as np

from ats.fusion.trade_sim import T1Simulator, Order, Trade
from ats.fusion.evaluate import (
    ROUND_TRIP_COST_PCT,
    STATUS_FILLED_MATURE,
    STATUS_UNFILLED_EXPIRED,
    STATUS_UNFILLED_LIMIT_LOCKED,
    STATUS_IMMATURE_OPEN,
    STATUS_DATA_INVALID,
    gross_target_from_net,
    gross_stop_from_net,
    calc_resolved_net_expectancy,
    filter_mature_for_training,
    evaluate_signals,
    day_block_bootstrap_test,
    check_oos_admission_gate,
)

_DTYPE = [
    ("time", "<i8"),
    ("open", "<f4"),
    ("high", "<f4"),
    ("low", "<f4"),
    ("close", "<f4"),
    ("volume", "<f4"),
    ("cum_vol_start", "<f4"),
]

_D1 = "2026-10-20"
_D2 = "2026-10-21"
_D3 = "2026-10-22"


def _make_bars(day, o, h, l, c, v=None, start_h=9, start_m=30, step_s=180):
    n = len(c)
    arr = np.zeros(n, dtype=_DTYPE)
    base = int(time.mktime(time.strptime("{} {:02d}:{:02d}".format(day, start_h, start_m), "%Y-%m-%d %H:%M")))
    if v is None:
        v = [10000.0] * n
    for i in range(n):
        arr[i] = (base + i * step_s, o[i], h[i], l[i], c[i], v[i], 0.0)
    return arr


def _day_ts(day, h=9, m=30):
    return int(time.mktime(time.strptime("{} {:02d}:{:02d}".format(day, h, m), "%Y-%m-%d %H:%M")))


class TestTradeSimP2(unittest.TestCase):
    """验证 trade_sim.py 的 5 大物理撮合与时序退出修复。"""

    def test_limit_order_no_fabricated_lo_fill_price(self):
        """1. 限价单买入：当 open < lo 时绝不捏造 lo 抬高成交价，而是以 min(hi, open) 成交。"""
        # 买入区间为 [9.8, 10.0]，即 lo=9.8, hi=10.0
        # 第0根为信号bar，第1根为挂单后首根bar：open=9.6, high=9.7, low=9.5, close=9.6
        # 整根 bar 最高 9.7 < lo 9.8，但满足 low 9.5 <= hi 10.0
        o1 = [10.0, 9.6]
        h1 = [10.1, 9.7]
        l1 = [9.9, 9.5]
        c1 = [10.0, 9.6]
        bars1 = _make_bars(_D1, o1, h1, l1, c1)
        # 次日平盘
        bars2 = _make_bars(_D2, [9.6, 9.6], [9.7, 9.7], [9.5, 9.5], [9.6, 9.6])
        cache = {"000001": np.concatenate([bars1, bars2])}

        sim = T1Simulator(cache, [_D1, _D2])
        dec = {
            "code": "000001",
            "ts": bars1["time"][0], # 信号在第0根
            "tier": 3,
            "entry": {"price_lo": 9.8, "price_hi": 10.0},
            "stop": 9.0,
        }
        orders, trades = sim.simulate([dec])
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].status, "FILLED")
        # 核心断言：成交价等于第1根的 open 9.6，绝不被捏造成 lo 9.8！
        self.assertAlmostEqual(orders[0].fill_price, 9.6, places=2)
        self.assertAlmostEqual(trades[0].entry_price, 9.6, places=2)

    def test_chronological_bars_exit_distinguishes_profit_before_stop(self):
        """2. 逐 bar 推进：早盘先达止盈、下午才破止损，准确判定为止盈，而非同日双触止损。"""
        # T+0 买入
        bars1 = _make_bars(_D1, [10.0, 10.0], [10.1, 10.1], [9.9, 9.9], [10.0, 10.0])
        # T+1 日分两根 bar：
        # 第0根（早盘 09:30）：冲高到 10.7（>= target1 10.6），low 9.9 未破止损（stop 9.5）
        # 第1根（下午 14:00）：跳水到 low 9.2（破止损 9.5）
        b2_o = [10.0, 10.0]
        b2_h = [10.7, 10.0] # 早盘触达止盈
        b2_l = [9.9, 9.2]   # 下午破止损
        b2_c = [10.6, 9.3]
        bars2 = _make_bars(_D2, b2_o, b2_h, b2_l, b2_c)
        cache = {"000002": np.concatenate([bars1, bars2])}

        sim = T1Simulator(cache, [_D1, _D2])
        dec = {
            "code": "000002",
            "ts": bars1["time"][0],
            "tier": 3,
            "entry": {"price_lo": 9.9, "price_hi": 10.1},
            "stop": 9.5,
        }
        orders, trades = sim.simulate([dec], target_pct=6.0)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        # 核心断言：必须准确判定为"止盈+6%"，绝不能因为下午才破的止损而误判为双触或止损！
        self.assertEqual(t.exit_reason, "止盈+6%")
        self.assertAlmostEqual(t.exit_price, 10.0 * 1.06, places=2)

    def test_same_bar_dual_touch_conservative_stop(self):
        """2b. 仅当同一根 bar 内同时双触时，保守判定为止损(双触保守)。"""
        bars1 = _make_bars(_D1, [10.0, 10.0], [10.1, 10.1], [9.9, 9.9], [10.0, 10.0])
        # 次日第0根 bar 巨大振幅：high 10.8 (触及止盈), low 9.2 (触及止损)
        bars2 = _make_bars(_D2, [10.0], [10.8], [9.2], [10.0])
        cache = {"000003": np.concatenate([bars1, bars2])}

        sim = T1Simulator(cache, [_D1, _D2])
        dec = {
            "code": "000003",
            "ts": bars1["time"][0],
            "tier": 3,
            "entry": {"price_lo": 9.9, "price_hi": 10.1},
            "stop": 9.5,
        }
        orders, trades = sim.simulate([dec], target_pct=6.0)
        t = trades[0]
        self.assertEqual(t.exit_reason, "止损(双触保守)")
        self.assertAlmostEqual(t.exit_price, 9.5, places=2)

    def test_t0_vwap_break_exits_at_t1_open_prior_to_intraday_target(self):
        """3. T+0 破 VWAP 在 T+1 首根 bar 开盘优先平仓，不被盘中后续止盈覆盖。"""
        # 买入日 T+0：第0根开盘10.0买入，第1根收盘跳水到9.2，大幅低于 VWAP
        bars1 = _make_bars(_D1, [10.0, 9.8], [10.1, 9.8], [9.9, 9.1], [10.0, 9.2])
        # 次日 T+1：开盘 9.2，盘中暴力拉升到 11.0（触及止盈）
        bars2 = _make_bars(_D2, [9.2], [11.0], [9.2], [10.8])
        cache = {"000004": np.concatenate([bars1, bars2])}

        sim = T1Simulator(cache, [_D1, _D2])
        dec = {
            "code": "000004",
            "ts": bars1["time"][0],
            "tier": 3,
            "entry": {"price_lo": 9.9, "price_hi": 10.1},
            "stop": 8.0,
        }
        orders, trades = sim.simulate([dec], target_pct=6.0)
        t = trades[0]
        # 核心断言：首根开盘优先执行 VWAP 破位退出，退出价为次日开盘 9.2，不被盘中 11.0 覆盖！
        self.assertEqual(t.exit_reason, "VWAP破位次日开盘出")
        self.assertAlmostEqual(t.exit_price, 9.2, places=2)

    def test_limit_down_locked_generates_pending_exit_and_recovers_at_open(self):
        """4. 次日一字跌停无法卖出生成 pending_exit，在第三日开板首根 bar 立即按 open 恢复退出。"""
        # T+0 买入，收盘 10.0
        bars1 = _make_bars(_D1, [10.0, 10.0], [10.1, 10.0], [9.9, 10.0], [10.0, 10.0])
        # T+1 一字跌停锁死：开高低收均为 9.0（较 10.0 跌 10%），触及止损 9.5 但无法卖出
        bars2 = _make_bars(_D2, [9.0, 9.0], [9.0, 9.0], [9.0, 9.0], [9.0, 9.0])
        # T+2 开板：首根开盘 9.1，随后拉升到 9.8（此时已脱离 <= 9.0 跌停且价格高于止损 9.5）
        bars3 = _make_bars(_D3, [9.1, 9.5], [9.8, 9.8], [9.1, 9.4], [9.7, 9.6])
        cache = {"000005": np.concatenate([bars1, bars2, bars3])}

        sim = T1Simulator(cache, [_D1, _D2, _D3])
        dec = {
            "code": "000005",
            "ts": bars1["time"][0],
            "tier": 3,
            "entry": {"price_lo": 9.9, "price_hi": 10.1},
            "stop": 9.5,
        }
        # 允许持有至第3天以观察恢复
        orders, trades = sim.simulate([dec], hold_days=3)
        t = trades[0]
        # 核心断言：在 T+2 开板首根 bar 立即按开盘价 9.1 成交退出
        self.assertIn("受阻顺延", t.exit_reason)
        self.assertAlmostEqual(t.exit_price, 9.1, places=2)
        self.assertEqual(t.resolution_status, STATUS_FILLED_MATURE)

    def test_incomplete_intraday_bars_marked_immature_open(self):
        """5. 半日残缺数据（末根 bar 时间 < 14:57 且开启 require_full_day_close）标记 IMMATURE_OPEN。"""
        # 仅有上午半日数据（09:30 到 11:30），最后一根时间为 11:30 (远早于 14:57)
        # 构造两根 180s 的 bar：09:30 和 09:33
        bars1 = _make_bars(_D1, [10.0, 10.0], [10.1, 10.1], [9.9, 9.9], [10.0, 10.0], start_h=9, start_m=30)
        cache = {"000006": bars1}

        # 仅有买入日，无后续日
        sim = T1Simulator(cache, [_D1])
        dec = {
            "code": "000006",
            "ts": bars1["time"][0],
            "tier": 3,
            "entry": {"price_lo": 9.9, "price_hi": 10.1},
            "stop": 9.5,
        }
        orders, trades = sim.simulate([dec], require_full_day_close=True)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        # 核心断言：半日残缺数据绝不当作收盘结案，必须标记 IMMATURE_OPEN
        self.assertEqual(t.exit_reason, "IMMATURE_INCOMPLETE_BARS")
        self.assertEqual(t.resolution_status, STATUS_IMMATURE_OPEN)
        self.assertEqual(t.exit_price, 0.0)


class TestEvaluateP2(unittest.TestCase):
    """验证 evaluate.py 的净期望收益、五类互斥分母、防泄漏截断与统计检验。"""

    def test_gross_target_and_stop_conversion(self):
        """6a. 毛净目标与止损换算。"""
        # 基准净目标 +3.00% 对应毛涨幅 +3.15% (3.00 + 0.15)
        self.assertEqual(gross_target_from_net(3.0, 0.15), 3.15)
        # 基准净止损 -2.00% 对应毛跌幅 -1.85% (-2.00 + 0.15)
        self.assertEqual(gross_stop_from_net(-2.0, 0.15), -1.85)

    def test_five_mutually_exclusive_categories_and_resolved_expectancy(self):
        """6b. 五类互斥分母分类与 E_resolved[R_net] 精确计算。"""
        records = [
            # 2笔 FILLED_MATURE: net_pnl 分别为 +5.0%, -2.0%
            {"status": STATUS_FILLED_MATURE, "eval_tier": 4, "net_pnl_pct": 5.0, "gross_pnl_pct": 5.15},
            {"status": STATUS_FILLED_MATURE, "eval_tier": 4, "net_pnl_pct": -2.0, "gross_pnl_pct": -1.85},
            # 1笔 UNFILLED_EXPIRED (实现净收益计为 0.0%)
            {"status": STATUS_UNFILLED_EXPIRED, "eval_tier": 4, "net_pnl_pct": 0.0, "gross_pnl_pct": 0.0},
            # 1笔 UNFILLED_LIMIT_LOCKED (实现净收益计为 0.0%)
            {"status": STATUS_UNFILLED_LIMIT_LOCKED, "eval_tier": 4, "net_pnl_pct": 0.0, "gross_pnl_pct": 0.0},
            # 1笔 IMMATURE_OPEN (未终结，不计入 S_resolved 分母)
            {"status": STATUS_IMMATURE_OPEN, "eval_tier": 4, "net_pnl_pct": 0.0, "gross_pnl_pct": 0.0},
            # 1笔 DATA_INVALID (无效数据，不计入 S_resolved 分母)
            {"status": STATUS_DATA_INVALID, "eval_tier": 4, "net_pnl_pct": 0.0, "gross_pnl_pct": 0.0},
        ]
        res = calc_resolved_net_expectancy(records)
        # S_resolved = 2 (FILLED_MATURE) + 1 (UNFILLED_EXPIRED) + 1 (UNFILLED_LIMIT_LOCKED) = 4
        self.assertEqual(res["resolved_count"], 4)
        self.assertEqual(res["filled_mature_count"], 2)
        self.assertEqual(res["unfilled_expired_count"], 1)
        self.assertEqual(res["unfilled_limit_locked_count"], 1)
        self.assertEqual(res["immature_open_count"], 1)
        self.assertEqual(res["data_invalid_count"], 1)

        # 净期望收益 = (5.0 + (-2.0) + 0 + 0) / 4 = 3.0 / 4 = 0.75%
        self.assertAlmostEqual(res["resolved_net_expectancy"], 0.75, places=4)
        # 填充率 = 2 / 4 = 50.0%
        self.assertAlmostEqual(res["fill_rate_resolved"], 0.50, places=4)
        # 成交样本平均净收益 = 3.0 / 2 = 1.5%
        self.assertAlmostEqual(res["mean_net_pnl_mature"], 1.50, places=4)
        # 期望收益公式自洽：E = fill_rate * mean_net = 0.50 * 1.50 = 0.75%
        self.assertAlmostEqual(res["resolved_net_expectancy"], res["fill_rate_resolved"] * res["mean_net_pnl_mature"], places=4)
        # 存在 immature 样本，批次标记为 BATCH_PENDING
        self.assertEqual(res["batch_status"], "BATCH_PENDING")

    def test_filter_mature_for_training_leakage_prevention(self):
        """6c. 防泄漏截断：仅保留 label_available_ts < cutoff_ts 且属于 S_resolved 的样本。"""
        records = [
            # 样本 1：已在 cutoff 前可用 (成熟) -> 保留
            {"status": STATUS_FILLED_MATURE, "label_available_ts": 1000.0, "code": "A"},
            # 样本 2：在 cutoff 之后才可用 (存在未来泄漏) -> 剔除
            {"status": STATUS_FILLED_MATURE, "label_available_ts": 3000.0, "code": "B"},
            # 样本 3：未终结样本即便 timestamp 较早 -> 剔除
            {"status": STATUS_IMMATURE_OPEN, "label_available_ts": 1000.0, "code": "C"},
            # 样本 4：超时未成交，已在 cutoff 前终结 -> 保留
            {"status": STATUS_UNFILLED_EXPIRED, "label_available_ts": 1200.0, "code": "D"},
        ]
        filtered = filter_mature_for_training(records, cutoff_ts=2000.0)
        retained_codes = [r["code"] for r in filtered]
        self.assertEqual(retained_codes, ["A", "D"])

    def test_evaluate_signals_pipeline_and_peak_tier_diagnosis(self):
        """6d. 评估管线：以首达档位为主分组，Peak Tier 仅作盘后诊断。"""
        order = Order(code="600001", signal_ts=100.0, order_ts=103.0, status="FILLED", fill_price=10.0, tier=2)
        trade = Trade(
            code="600001", tier=2, entry_ts=103.0, entry_price=10.0, size_pct=10.0, stop=9.5,
            sellable_date="2026-10-21", exit_ts=200.0, exit_price=10.5, resolution_status=STATUS_FILLED_MATURE
        )
        trade.gross_pnl_pct = 5.0
        trade.net_pnl_pct = 4.85
        trade.label_available_ts = 380.0

        decisions = [
            {"code": "600001", "ts": 100.0, "signal_tier": 2, "tier": 2}, # 首次达标 L2
            {"code": "600001", "ts": 150.0, "signal_tier": 4, "tier": 4}, # 盘中拉升至 L4 (Peak Tier)
        ]

        res = evaluate_signals([order], [trade], decisions, tier_field="signal_tier")
        rec = res["records"][0]
        # 核心断言：主评估档位为首次达标时的 L2，最高档位记录为 L4 仅供诊断
        self.assertEqual(rec["eval_tier"], 2)
        self.assertEqual(rec["diagnostic_peak_tier"], 4)
        self.assertEqual(rec["status"], STATUS_FILLED_MATURE)

    def test_day_block_bootstrap_test(self):
        """6e. 按交易日块自助法显著性检验。"""
        # 构造跨越多个交易日的样本
        records = []
        days = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05"]
        for d in days:
            # L4 样本净收益较优
            records.append({"trade_date": d, "eval_tier": 4, "status": STATUS_FILLED_MATURE, "net_pnl_pct": 3.0})
            records.append({"trade_date": d, "eval_tier": 4, "status": STATUS_FILLED_MATURE, "net_pnl_pct": 2.0})
            # L2 样本净收益较低
            records.append({"trade_date": d, "eval_tier": 2, "status": STATUS_FILLED_MATURE, "net_pnl_pct": -1.0})
            records.append({"trade_date": d, "eval_tier": 2, "status": STATUS_FILLED_MATURE, "net_pnl_pct": 0.0})

        bs = day_block_bootstrap_test(records, n_bootstraps=200, random_seed=42)
        self.assertIn("l4_minus_l2_ci_90_lower", bs)
        self.assertGreater(bs["l4_minus_l2_mean"], 0)
        self.assertTrue(bs["l4_minus_l2_passed"])

    def test_check_oos_admission_gate(self):
        """6f. 样本外上线准入门槛检查。"""
        # 样本不足（仅5日，L2/L3/L4 各仅 5 笔）
        sample_records = []
        for i in range(5):
            d = "2026-10-{:02d}".format(i + 1)
            for t in (2, 3, 4):
                sample_records.append({
                    "trade_date": d, "market_temp_regime": "WARM", "status": STATUS_FILLED_MATURE, "eval_tier": t
                })
        gate_res = check_oos_admission_gate(sample_records)
        self.assertFalse(gate_res["passed"])
        self.assertIn("交易日不足15日", gate_res["unmet_reasons"][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
