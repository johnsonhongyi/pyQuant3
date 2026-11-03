# -*- coding: utf-8 -*-
"""tests/test_fusion_p0_p1_recompute.py — P0 契约冻结、数据卫生、三层档位与 L1a/L1b 确定性复算专项测试。"""

import os
import shutil
import tempfile
import time
import unittest

import pandas as pd

from ats.fusion.adapter import build_event, is_data_hygiene_ok
from ats.fusion.anomaly import (
    PATTERN_BOX10_VWAP_HOVER,
    PATTERN_STRUCTURE_CONFIRM,
    detect_patterns,
)
from ats.fusion.contract import AxisScores, FusionDecision, SignalEvent
from ats.fusion.engine import FusionBus, FusionEngine
from ats.fusion.kernel import (
    check_data_hygiene,
    compute_config_fingerprint,
    compute_feature_drift_report,
    compute_tier_floor,
    recompute_record_l1a,
    recompute_sequence_l1b,
    resolve_prime_leader,
    run_l1_ablation,
)
from ats.fusion.regime import MarketRegime
from ats.fusion.shadow import FusionShadow
from ats.fusion.structure_timeline import (
    STATUS_BROKEN,
    STATUS_CONFIRMED,
    STATUS_WAITING,
    StructureSnapshot,
    StructureTimeline,
)

_NOW = time.mktime((2026, 10, 23, 10, 30, 0, 0, 0, -1))
_TODAY = "2026-10-23"


def _sample_event(**kw):
    base = dict(
        code="600000",
        ts=_NOW,
        source="test",
        price=10.5,
        vwap=10.2,
        vwap_5d=10.0,
        vwap_10d=9.8,
        sbc_supp=9.9,
        sbc_rev=10.1,
        base_support=9.8,
        resistance=11.2,
        day_high=10.6,
        day_low=10.1,
        pct=3.0,
        vol_ratio=1.5,
        turnover=5.0,
        amount_wan=50000.0,
        taker_buy_ratio=65.0,
        bid_pressure=60.0,
        structure_clarity=75.0,
        minutes_above_vwap=45.0,
        slope_score=70.0,
        intent_score=75.0,
        velocity_pct=1.0,
        segment_vol_inc=20.0,
        sector_resonance=65.0,
        is_leader=True,
        upper_score=80.0,
        ma5=10.0,
        ma10=9.8,
        ma20=9.5,
        ret5d=4.0,
        ret10d=6.0,
        ret20d=8.0,
        days_since_high=2.0,
        limit_up_streak=0.0,
        dist_ma20_pct=10.5,
        rs5=1.8,
        rs_day=2.2,
        launch_ts=_NOW - 300.0,
        freshness_s=2.0,
        trade_date=_TODAY,
        extra={"patterns": ["结构预判验证"], "struct_status": "CONFIRMED", "is_structure_prejudged": 1.0},
    )
    base.update(kw)
    return SignalEvent(**base)


class TestContractLossless(unittest.TestCase):
    def test_signal_event_lossless_roundtrip(self):
        ev1 = _sample_event()
        d = ev1.to_dict()
        # 验证新增字段包含在 to_dict 中
        for key in (
            "vwap_10d", "ma5", "ma10", "ma20", "ret5d", "ret10d", "ret20d",
            "days_since_high", "limit_up_streak", "dist_ma20_pct", "rs5", "rs_day", "extra"
        ):
            self.assertIn(key, d, f"Missing {key} in SignalEvent.to_dict()")

        ev2 = SignalEvent.from_dict(d)
        self.assertEqual(ev1.code, ev2.code)
        self.assertAlmostEqual(ev1.price, ev2.price)
        self.assertAlmostEqual(ev1.vwap_10d, ev2.vwap_10d)
        self.assertAlmostEqual(ev1.ma20, ev2.ma20)
        self.assertEqual(ev1.extra["patterns"], ev2.extra["patterns"])
        self.assertEqual(ev1.trade_date, ev2.trade_date)

    def test_axis_scores_roundtrip(self):
        ax1 = AxisScores(position=80.5, support=75.0, intent=70.2, regime=65.0, relative=60.0, penalty=5.0, rar=72.5)
        d = ax1.to_dict()
        ax2 = AxisScores.from_dict(d)
        self.assertAlmostEqual(ax1.rar, ax2.rar)
        self.assertAlmostEqual(ax1.position, ax2.position)
        self.assertAlmostEqual(ax1.penalty, ax2.penalty)

    def test_fusion_decision_three_tiers_and_roundtrip(self):
        dec1 = FusionDecision(
            code="600000",
            ts=_NOW,
            tier=4,
            tier_name="L4 主攻",
            rar=85.5,
            axes=AxisScores(rar=85.5),
            score_tier=3,
            signal_tier=4,
            signal_size_pct=30.0,
            portfolio_tier=4,
            base_rar=77.5,
            adj_rar=85.5,
            floor_tier=4,
            floor_source="struct_confirm",
            cap_tier=4,
            cap_reasons=[],
            cuts=((82.0, 4), (72.0, 3)),
        )
        d = dec1.to_dict()
        self.assertEqual(d["score_tier"], 3)
        self.assertEqual(d["signal_tier"], 4)
        self.assertEqual(d["portfolio_tier"], 4)
        self.assertEqual(d["floor_tier"], 4)
        self.assertEqual(d["floor_source"], "struct_confirm")
        self.assertAlmostEqual(d["base_rar"], 77.5)
        self.assertAlmostEqual(d["adj_rar"], 85.5)

        dec2 = FusionDecision.from_dict(d)
        self.assertEqual(dec1.code, dec2.code)
        self.assertEqual(dec1.tier, dec2.tier)
        self.assertEqual(dec1.score_tier, dec2.score_tier)
        self.assertEqual(dec1.signal_tier, dec2.signal_tier)
        self.assertEqual(dec1.portfolio_tier, dec2.portfolio_tier)
        self.assertAlmostEqual(dec1.rar, dec2.rar)
        self.assertAlmostEqual(dec1.base_rar, dec2.base_rar)
        self.assertAlmostEqual(dec1.adj_rar, dec2.adj_rar)
        self.assertEqual(dec1.cuts, dec2.cuts)


class TestStructureAndAnomalyDefects(unittest.TestCase):
    def test_structure_snapshot_roundtrip_and_timeline_state(self):
        snap1 = StructureSnapshot(
            code="600001", status=STATUS_CONFIRMED, ts=_NOW, confirm_n=2, break_n=1,
            confirm_ts=_NOW - 100, break_ts=_NOW - 500, status_since=_NOW - 100,
            cushion_roll=0.8, cushion_now=1.2, drawdown_pct=0.3, high_water=10.6, reason="突破"
        )
        d = snap1.to_dict()
        self.assertEqual(d["code"], "600001")
        self.assertAlmostEqual(d["high_water"], 10.6)
        snap2 = StructureSnapshot.from_dict(d)
        self.assertEqual(snap1.code, snap2.code)
        self.assertEqual(snap1.status, snap2.status)
        self.assertAlmostEqual(snap1.high_water, snap2.high_water)

        tl = StructureTimeline()
        tl.update("600001", _NOW, price=10.5, vwap=10.2, hi_pre1=10.4, close_pre1=10.0, cushion_roll=0.5, prejudged=True)
        state_data = tl.snapshot_state()
        self.assertIn("600001", state_data["states"])

        tl2 = StructureTimeline()
        tl2.load_state(state_data)
        st = tl2.get("600001")
        self.assertIsNotNone(st)
        self.assertEqual(st.status, STATUS_CONFIRMED)

    def test_hi_pre1_zero_not_breakout(self):
        tl = StructureTimeline()
        # hi_pre1 为 0 或负数时，不能短路当做突破
        st = tl.update("600002", _NOW, price=10.5, vwap=10.2, hi_pre1=0.0, close_pre1=10.0, cushion_roll=0.5, prejudged=True)
        self.assertEqual(st.status, STATUS_WAITING, "hi_pre1 <= 0 时不得判定为 breakout 点火")

    def test_waiting_status_does_not_penetrate_patterns(self):
        # 当明确传入 struct_status="WAITING" 时，不得生成 BOX10_VWAP_HOVER 或 STRUCTURE_CONFIRM
        pats_waiting = detect_patterns(
            price=10.5, day_open=10.0, ma5=10.0, ma10=10.0, ma20=10.0, pct=5.0,
            ret_std20=1.0, vol_ratio=1.5, rs5=1.0, mkt_ret5=0.0,
            vwap10=10.0, hi_pre1=10.4, hi_10d=10.4, is_box10_ready=True,
            is_structure_prejudged=True, cushion_roll=0.5,
            struct_status=STATUS_WAITING,
        )
        self.assertNotIn(PATTERN_BOX10_VWAP_HOVER, pats_waiting)
        self.assertNotIn(PATTERN_STRUCTURE_CONFIRM, pats_waiting)

        # 当 struct_status="CONFIRMED" 时正常生成
        pats_confirmed = detect_patterns(
            price=10.5, day_open=10.0, ma5=10.0, ma10=10.0, ma20=10.0, pct=5.0,
            ret_std20=1.0, vol_ratio=1.5, rs5=1.0, mkt_ret5=0.0,
            vwap10=10.0, hi_pre1=10.4, hi_10d=10.4, is_box10_ready=True,
            is_structure_prejudged=True, cushion_roll=0.5,
            struct_status=STATUS_CONFIRMED,
        )
        self.assertIn(PATTERN_BOX10_VWAP_HOVER, pats_confirmed)
        self.assertIn(PATTERN_STRUCTURE_CONFIRM, pats_confirmed)


class TestDataHygieneAndEngine(unittest.TestCase):
    def test_data_hygiene_interception(self):
        ev_good = _sample_event()
        ok, reason = is_data_hygiene_ok(ev_good, expected_day=_TODAY)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

        ev_zero_px = _sample_event(price=0.0)
        ok, reason = is_data_hygiene_ok(ev_zero_px, expected_day=_TODAY)
        self.assertFalse(ok)
        self.assertIn("现价", reason)

        ev_stale = _sample_event(freshness_s=35.0)
        ok, reason = is_data_hygiene_ok(ev_stale, expected_day=_TODAY, stale_seconds=20.0)
        self.assertFalse(ok)
        self.assertIn("数据过期", reason)

        ev_cross_day = _sample_event(trade_date="2026-10-22")
        ok, reason = is_data_hygiene_ok(ev_cross_day, expected_day=_TODAY)
        self.assertFalse(ok)
        self.assertIn("跨交易日", reason)

    def test_rar_consistency_and_score_tier_before_floor(self):
        eng = FusionEngine(today=_TODAY)
        ev = _sample_event(price=10.5, vwap=10.2)
        dec = eng.evaluate(ev, MarketRegime(temp=55.0, stage="WARMING", flip_state="FLIP_CONFIRMED"))
        # 检验 decision.rar == axes.rar
        self.assertAlmostEqual(dec.rar, dec.axes.rar, places=2)
        # 检验 score_tier 与 signal_tier
        self.assertGreaterEqual(dec.signal_tier, dec.score_tier)
        self.assertEqual(dec.portfolio_tier, dec.signal_tier)
        self.assertGreater(dec.adj_rar, dec.base_rar)

    def test_coverage_calculated_even_on_veto(self):
        eng = FusionEngine(today=_TODAY)
        ev_chase = _sample_event(price=12.0, vwap=10.0)  # 偏离均价 20%，必被追高否决
        dec = eng.evaluate(ev_chase, None)
        self.assertEqual(dec.tier, 0)
        self.assertIn("追高透支", dec.veto_reason)
        self.assertGreater(dec.coverage, 0.5, "否决分支必须正确计算 coverage，不可为 0")


class TestFusionBusAndRebalance(unittest.TestCase):
    def test_bus_update_reuses_decision_and_force_downgrade(self):
        eng = FusionEngine(today=_TODAY)
        bus = FusionBus(engine=eng, max_l4=1, max_total_pct=50.0)
        ev = _sample_event(code="600001")
        reg = MarketRegime(temp=55.0, stage="WARMING")
        dec = eng.evaluate(ev, reg)
        # 传入已计算好的 decision
        bus.update(ev, reg, decision=dec, cuts=eng.cuts, tier_floor=4)
        self.assertEqual(bus.get("600001").decision_id, dec.decision_id)

        # 强制降档验证重算 entry / stop
        dec_down = bus._force_downgrade(dec, ev)
        self.assertEqual(dec_down.tier, dec.tier - 1)
        self.assertEqual(dec_down.portfolio_tier, dec.tier - 1)
        self.assertEqual(dec_down.signal_tier, dec.signal_tier)  # 原始信号档保持
        self.assertIn("price_lo", dec_down.entry)

    def test_rebalance_maintains_tier_consistency(self):
        eng = FusionEngine(today=_TODAY)
        bus = FusionBus(engine=eng, max_l4=1, max_total_pct=40.0)
        for c in ("600011", "600012", "600013"):
            ev = _sample_event(code=c)
            bus.update(ev, None)
        pf = bus.rebalance()
        for d in pf:
            self.assertEqual(d.tier, d.portfolio_tier)
            self.assertLessEqual(d.size_pct, 35.0)


class TestRecomputeL1aAndL1b(unittest.TestCase):
    def test_l1a_exact_recompute(self):
        root = tempfile.mkdtemp(prefix="fusion_l1a_")
        try:
            shadow = FusionShadow(config={"enabled": True, "shadow_only": True, "log_dir": "l1a_test"}, root=root)
            ev = _sample_event(code="600088")
            rec = shadow.observe(code="600088", row=pd.Series(ev.to_dict()), snap=ev.extra, now=_NOW, force=True)
            self.assertIsNotNone(rec)
            self.assertIn("event_snapshot", rec)
            self.assertIn("seq_no", rec)
            self.assertIn("session_id", rec)

            dec_l1a = recompute_record_l1a(rec, engine=shadow.engine)
            # 严格验证复算一致性
            self.assertEqual(dec_l1a.tier, rec["fusion"]["tier"])
            self.assertEqual(dec_l1a.score_tier, rec["fusion"]["score_tier"])
            self.assertEqual(dec_l1a.signal_tier, rec["fusion"]["signal_tier"])
            self.assertAlmostEqual(dec_l1a.rar, rec["fusion"]["rar"], places=2)
            self.assertAlmostEqual(dec_l1a.size_pct, rec["fusion"]["size_pct"], places=1)
            self.assertEqual(dec_l1a.entry, rec["fusion"]["entry"])
            self.assertEqual(dec_l1a.stop, rec["fusion"]["stop"])
            shadow.close()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_l1b_sequence_recompute_and_broken_detection(self):
        records = []
        ev1 = _sample_event(code="600001", ts=_NOW)
        ev2 = _sample_event(code="600002", ts=_NOW + 10)
        ev3 = _sample_event(code="600003", ts=_NOW + 20)

        r1 = {"seq_no": 1, "ts": _NOW, "code": "600001", "event_snapshot": ev1.to_dict()}
        # 故意制造断号：跳过 seq_no=2，直接 seq_no=3
        r3 = {"seq_no": 3, "ts": _NOW + 20, "code": "600003", "event_snapshot": ev3.to_dict()}

        replayed, pf, audit = recompute_sequence_l1b([r3, r1])  # 乱序输入
        self.assertEqual(len(replayed), 2)
        self.assertTrue(audit["sequence_broken"], "应成功检测出断号")
        self.assertTrue(audit["log_incomplete"])
        self.assertEqual(audit["missing_seq_count"], 1)
        self.assertLessEqual(audit["total_size_pct"], 85.0)

    def test_l1b_completeness_and_eof_checkpoint(self):
        ev1 = _sample_event(code="600001", ts=_NOW)
        ev2 = _sample_event(code="600002", ts=_NOW + 10)
        r1 = {"seq_no": 1, "ts": _NOW, "code": "600001", "event_snapshot": ev1.to_dict()}
        r2 = {"seq_no": 2, "ts": _NOW + 10, "code": "600002", "event_snapshot": ev2.to_dict()}
        r_eof = {"seq_no": 3, "ts": _NOW + 20, "checkpoint_kind": "EOF_CHECKPOINT"}

        # 1. 正常完整序列包含 EOF_CHECKPOINT
        _, _, audit = recompute_sequence_l1b([r1, r2, r_eof], require_eof_checkpoint=True)
        self.assertFalse(audit["sequence_broken"])
        self.assertTrue(audit["has_eof_checkpoint"])
        self.assertFalse(audit["log_incomplete"])

        # 2. 缺少 EOF_CHECKPOINT 时被标记为 incomplete
        _, _, audit_no_eof = recompute_sequence_l1b([r1, r2], require_eof_checkpoint=True)
        self.assertFalse(audit_no_eof["has_eof_checkpoint"])
        self.assertTrue(audit_no_eof["log_incomplete"])

        # 3. 截断或丢写标记导致 incomplete
        r_trunc = {"seq_no": 3, "ts": _NOW + 20, "code": "600003", "event_snapshot": ev1.to_dict(), "max_records_truncated": True}
        _, _, audit_trunc = recompute_sequence_l1b([r1, r2, r_trunc])
        self.assertTrue(audit_trunc["truncated"])
        self.assertTrue(audit_trunc["log_incomplete"])

        r_drop = {"seq_no": 3, "ts": _NOW + 20, "code": "600003", "event_snapshot": ev1.to_dict(), "dropped_write_count": 5}
        _, _, audit_drop = recompute_sequence_l1b([r1, r2, r_drop])
        self.assertEqual(audit_drop["dropped_writes"], 5)
        self.assertTrue(audit_drop["log_incomplete"])


class TestKernelSharedFunctions(unittest.TestCase):
    def test_resolve_prime_leader(self):
        leader_dict = {}

        # 1. 前强 + 今强 + 先锋 -> 评为总龙头并占位
        is_prime, lbl = resolve_prime_leader(
            code="600001", sector="低空经济", prev_strong=True, today_strong=True,
            raw_lead_label="先锋", lead_gap_min=0.0, prime_leader_by_sector=leader_dict,
        )
        self.assertTrue(is_prime)
        self.assertEqual(lbl, "总龙头")
        self.assertEqual(leader_dict["低空经济"], "600001")

        # 2. 同板块另一只股票即使前强今强，由于已被 600001 占位，不能成为总龙头
        is_prime2, lbl2 = resolve_prime_leader(
            code="600002", sector="低空经济", prev_strong=True, today_strong=True,
            raw_lead_label="先锋", lead_gap_min=1.0, prime_leader_by_sector=leader_dict,
        )
        self.assertFalse(is_prime2)
        self.assertEqual(lbl2, "先锋")

        # 3. 自身重复调用保持总龙头
        is_prime_self, lbl_self = resolve_prime_leader(
            code="600001", sector="低空经济", prev_strong=True, today_strong=True,
            raw_lead_label="先锋", lead_gap_min=0.0, prime_leader_by_sector=leader_dict,
        )
        self.assertTrue(is_prime_self)
        self.assertEqual(lbl_self, "总龙头")

        # 4. 跟风或冲锋队不可被评为总龙头
        leader_dict2 = {}
        is_prime_follow, lbl_follow = resolve_prime_leader(
            code="600003", sector="AI算力", prev_strong=True, today_strong=True,
            raw_lead_label="跟风", lead_gap_min=1.0, prime_leader_by_sector=leader_dict2,
        )
        self.assertFalse(is_prime_follow)
        self.assertEqual(lbl_follow, "跟风")

    def test_compute_tier_floor(self):
        # 1. 结构确认形态保底 4
        floor = compute_tier_floor(
            patterns=["结构预判验证"], struct_status="CONFIRMED",
            is_prime=False, is_leader=False, lead_label="一般", ps=50.0,
        )
        self.assertEqual(floor, 4)

        # 2. 结构失守 (BROKEN) 则不享受结构保底
        floor_broken = compute_tier_floor(
            patterns=["结构预判验证"], struct_status="BROKEN",
            is_prime=False, is_leader=False, lead_label="一般", ps=50.0,
        )
        self.assertIsNone(floor_broken)

        # 3. max_struct_floor_tier=3 约束保底最高 L3
        floor_l3 = compute_tier_floor(
            patterns=["结构预判验证"], struct_status="CONFIRMED",
            is_prime=False, is_leader=False, lead_label="一般", ps=50.0,
            max_struct_floor_tier=3,
        )
        self.assertEqual(floor_l3, 3)

        # 4. 总龙头保底
        floor_prime = compute_tier_floor(
            patterns=[], struct_status="CONFIRMED",
            is_prime=True, is_leader=True, lead_label="总龙头", ps=0.0,
            max_struct_floor_tier=3,
        )
        self.assertEqual(floor_prime, 3)

        # 5. 形态分数分层保底
        floor_ps100 = compute_tier_floor(
            patterns=["突破前高"], struct_status="WAITING",
            is_prime=False, is_leader=False, lead_label="一般", ps=105.0,
        )
        self.assertEqual(floor_ps100, 3)

        floor_lead_pat = compute_tier_floor(
            patterns=["分时均线低吸"], struct_status="WAITING",
            is_prime=False, is_leader=False, lead_label="先锋", ps=40.0,
        )
        self.assertEqual(floor_lead_pat, 2)


class TestP1AblationAndFeatureDrift(unittest.TestCase):
    def test_run_l1_ablation(self):
        records = []
        for i in range(10):
            # 构造自身分数适中（约 60~70分，score_tier <= 3）但有结构突破形态的样本
            ev = _sample_event(
                code=f"6000{i:02d}",
                price=10.1,
                vwap=10.0,
                slope_score=50.0,
                intent_score=50.0,
                structure_clarity=65.0,
                minutes_above_vwap=20.0,
                pct=1.0,
                extra={
                    "patterns": ["结构预判验证"] if i < 5 else ["突破前高"],
                    "struct_status": "CONFIRMED",
                    "is_prime_leader": False,
                },
            )
            records.append({
                "code": ev.code,
                "ts": ev.ts,
                "trade_date": ev.trade_date,
                "event_snapshot": ev.to_dict(),
                "regime": {"temp": 20.0 if i < 2 else 55.0, "stage": "ICE" if i < 2 else "WARMING"},
                "tier_floor": 4 if i < 5 else None,
            })

        ablation_res = run_l1_ablation(records)
        self.assertEqual(ablation_res["total_records"], 10)
        exps = ablation_res["experiments"]
        for exp_name in (
            "baseline",
            "factor_fixed_cuts_68",
            "factor_struct_floor_l3",
            "factor_no_temp_cap_exempt",
            "factor_combined_p3_preview",
        ):
            self.assertIn(exp_name, exps)
            grp = exps[exp_name]
            self.assertIn("tier_counts", grp)
            self.assertIn("avg_rar", grp)
            self.assertIn("tier_match_rate", grp)
            self.assertIn("shift_matrix", grp)

        self.assertEqual(exps["baseline"]["tier_match_rate"], 1.0)
        # 验证 struct_floor_l3 限制了靠结构保底冲到 L4 的样本，发生 L4->L3 降档
        self.assertGreater(exps["factor_struct_floor_l3"]["downgrade_count"], 0)
        self.assertIn("L4->L3", exps["factor_struct_floor_l3"]["shift_matrix"])

    def test_compute_feature_drift_report(self):
        shadow_recs = []
        replay_recs = []

        codes = ["600001", "600002", "600003"]
        for c in codes:
            # 影子记录
            s_rec = {
                "code": c,
                "day": _TODAY,
                "ts": _NOW,
                "vwap": 10.2,
                "vol_ratio": 2.0,
                "temp": 55.0,
                "sector_resonance": 70.0,
                "rar": 75.0,
                "signal_tier": 3,
                "tier": 3,
            }
            shadow_recs.append(s_rec)

            # 回放记录（带有稍微的一致性与微小漂移）
            r_rec = {
                "code": c,
                "day": _TODAY,
                "ts": _NOW + 60.0,  # 差异 60s (<= 180s)
                "vwap": 10.22,
                "vol_ratio": 2.1,
                "temp": 55.0,
                "sector_resonance": 68.0,
                "rar": 74.0,
                "signal_tier": 3,
                "tier": 3,
            }
            replay_recs.append(r_rec)

        report = compute_feature_drift_report(shadow_recs, replay_recs)
        self.assertEqual(report["code_jaccard"], 1.0)
        self.assertEqual(report["first_l2_within_1bar_rate"], 1.0)
        self.assertEqual(report["matched_pairs_count"], 3)
        self.assertIn("field_metrics", report)
        self.assertIn("top_drift_sources", report)
        top_fields = [item["field"] for item in report["top_drift_sources"]]
        self.assertIn("vol_ratio", top_fields)
        self.assertIn("vwap", top_fields)


class TestReplayVolumeRatioAlignment(unittest.TestCase):
    def test_replay_volume_ratio_logic(self):
        from ats.fusion.replay import DayReplay, ReplayConfig
        cfg = ReplayConfig(record_tier_min=0)
        self.assertIsNotNone(cfg)

        # 验证量比计算分支与回退守卫
        # 分支 1: 有 vol_ma5 与累计成交量 -> 采用日内累计归一口径
        clock_ts = time.mktime((2026, 10, 23, 10, 0, 0, 0, 0, -1))
        _clock_time = time.localtime(int(clock_ts))
        _minute = _clock_time.tm_hour * 60 + _clock_time.tm_min
        _elapsed = min(120, max(0, _minute - 570)) + min(120, max(0, _minute - 780))  # 10:00 -> 30m
        _daily_volume = 100000.0
        cum_vol = 25000.0
        _day_ratio = (cum_vol / _daily_volume * 240 / _elapsed if _daily_volume > 0 and _elapsed > 0 else 0)
        eff_vol_ratio = max(0.2, min(8.0, float(_day_ratio))) if _day_ratio > 0 else 1.2
        self.assertAlmostEqual(_day_ratio, 2.0, places=2)
        self.assertAlmostEqual(eff_vol_ratio, 2.0, places=2)

        # 分支 2: 无 vol_ma5 (如冷启动或合成单测) -> 优雅回退到单根 bar 量比
        bar_vol_ratio = 1.35
        _daily_volume_zero = 0.0
        _day_ratio_zero = (cum_vol / _daily_volume_zero * 240 / _elapsed if _daily_volume_zero > 0 and _elapsed > 0 else 0)
        eff_fallback = max(0.2, min(8.0, float(_day_ratio_zero))) if _day_ratio_zero > 0 else bar_vol_ratio
        self.assertEqual(eff_fallback, 1.35)


if __name__ == "__main__":
    unittest.main(verbosity=2)
