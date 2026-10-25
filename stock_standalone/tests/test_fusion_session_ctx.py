# -*- coding: utf-8 -*-
"""tests/test_fusion_session_ctx.py — 每日实盘上下文沉淀 / 重建 / 交接。

要锁死四条契约：
    1. 收盘沉淀：温度、宽度、资金、阶段、信号计数都落到快照，缺失项进 missing（不编数）；
    2. 原子落盘：tmp + os.replace，不留半截文件；
    3. 缺失重建：没有快照时用日线基座重建，且 source="rebuilt" 可区分；
    4. 交接：给次日的摘要带冰点天数、饥饿度、上一阶段、热点板块，重建日会被标注。
"""

import json
import os
import shutil
import tempfile
import unittest

from ats.fusion.session_ctx import SessionContext, SessionContextStore


class _Frame:
    """最小帧替身：index=代码，带 percent 列。"""

    def __init__(self, rows):
        self.index = list(rows)
        self.columns = ["percent"]
        self._rows = rows

    @property
    def percent(self):
        return self


class _FakeTracker:
    """最小 tracker 替身：只提供 states()。"""

    def states(self):
        return [type("S", (), {"stage": "入局"})(),
                type("S", (), {"stage": "剔除"})(),
                type("S", (), {"stage": "观察"})()]


class _ThemeMap:
    def __init__(self, m):
        self._m = m

    def get(self, code):
        return self._m.get(code) or []


class TestSessionContextStore(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.store = SessionContextStore(root=self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _close(self, day, **kw):
        base = dict(
            temp_records=[{"temp": 40.0, "up": 800, "down": 4000},
                          {"temp": 52.0, "up": 1800, "down": 3000}],
            phase_path=[{"time": "09:35", "phase": "反攻", "note": "冲锋号"}],
            capital_ratio=1.26,
            amount_wan=12345.6,
        )
        base.update(kw)
        return self.store.close_day(day, **base)

    def test_close_day_persists_core_fields(self):
        ctx = self._close("2026-10-24")
        self.assertEqual(ctx.temp["close"], 52.0)
        self.assertEqual(ctx.temp["min"], 40.0)
        self.assertEqual(ctx.breadth["close"], 1800 / 4800)
        self.assertEqual(ctx.updown, {"up": 1800, "down": 3000})
        self.assertEqual(ctx.capital["ratio_close"], 1.26)
        self.assertEqual(ctx.capital["amount_wan"], 12345.6)
        self.assertEqual(ctx.phase_path[-1]["phase"], "反攻")
        # 落盘后可读回
        back = SessionContextStore(root=self.root).load("2026-10-24")
        self.assertIsNotNone(back)
        self.assertEqual(back.temp["close"], 52.0)
        self.assertEqual(back.source, "live")

    def test_missing_fields_are_declared_not_faked(self):
        ctx = self._close("2026-10-24", temp_records=None, capital_ratio=None, amount_wan=None,
                          phase_path=None)
        self.assertIn("temp", ctx.missing)
        self.assertIn("capital_ratio", ctx.missing)
        self.assertIn("phase_path", ctx.missing)
        self.assertIsNone(ctx.temp.get("close"))
        self.assertIsNone(ctx.capital.get("ratio_close"))

    def test_atomic_write_leaves_no_tmp(self):
        self._close("2026-10-24")
        files = os.listdir(self.root)
        self.assertIn("2026-10-24.json", files)
        self.assertFalse([f for f in files if f.endswith(".tmp")], "原子替换后不应留 tmp")

    def test_theme_heat_from_frame(self):
        import pandas as pd

        rows = {str(600000 + i): 3.0 + i * 0.1 for i in range(10)}
        rows.update({str(0): -2.0})
        df = pd.DataFrame([{"percent": v} for v in rows.values()], index=list(rows))
        tm = _ThemeMap({c: ["测试板块"] for c in rows})
        ctx = self.store.close_day("2026-10-24", frame=df, theme_map=tm)
        self.assertTrue(ctx.themes, "应算出热点板块")
        self.assertEqual(ctx.themes[0]["theme"], "测试板块")
        self.assertGreater(ctx.themes[0]["avg_pct"], 0)
        self.assertNotIn("themes", ctx.missing)

    def test_rotation_against_previous_day(self):
        import pandas as pd

        rows_a = {str(600000 + i): 3.0 for i in range(6)}
        rows_b = {str(600000 + i): 3.0 for i in range(6)}
        df_a = pd.DataFrame([{"percent": v} for v in rows_a.values()], index=list(rows_a))
        df_b = pd.DataFrame([{"percent": v} for v in rows_b.values()], index=list(rows_b))
        tm_a = _ThemeMap({c: ["旧板块"] for c in rows_a})
        tm_b = _ThemeMap({c: ["新板块"] for c in rows_b})
        self.store.close_day("2026-10-23", frame=df_a, theme_map=tm_a)
        ctx = self.store.close_day("2026-10-24", frame=df_b, theme_map=tm_b)
        new_in = [t["theme"] for t in (ctx.rotation.get("new_in") or [])]
        dropped = [t["theme"] for t in (ctx.rotation.get("dropped") or [])]
        self.assertIn("新板块", new_in)
        self.assertIn("旧板块", dropped)

    def test_rebuild_marks_source(self):
        ctx = self.store.rebuild_day("2026-10-23")
        if ctx is None:
            self.skipTest("本机无日线基座（G:/tdx_*.h5），跳过重建断言")
        self.assertEqual(ctx.source, "rebuilt")
        self.assertIn("capital_ratio", ctx.missing)
        self.assertTrue(self.store.load("2026-10-23") is not None)

    def test_ensure_prefers_snapshot(self):
        self._close("2026-10-24")
        got = self.store.ensure("2026-10-24")
        self.assertEqual(got.source, "live")

    def test_handoff_summary(self):
        self._close("2026-10-22", phase_path=[{"time": "14:00", "phase": "攻城略地", "note": ""}])
        self._close("2026-10-23", phase_path=[{"time": "14:00", "phase": "先锋阵亡", "note": ""}])
        h = self.store.handoff("2026-10-24", n=5)
        self.assertEqual(h["days"], 2)
        self.assertEqual(h["last_phase"], "先锋阵亡")
        self.assertEqual(h["from"], "2026-10-22")
        md = self.store.render_handoff("2026-10-24")
        self.assertIn("上下文交接", md)
        self.assertIn("先锋阵亡", md)

    def test_thin_write_does_not_erase_rich_snapshot(self):
        """多写入方合并：UI 定时巡检的薄快照不能抹掉回放写出的富快照。"""
        rich = self._close("2026-10-23", capital_ratio=1.26, amount_wan=9999.0)
        self.assertEqual(rich.capital["ratio_close"], 1.26)
        # 第二个写入方只带 phase_path（模拟 UI 收盘巡检）
        thin = self.store.close_day(
            "2026-10-23",
            phase_path=[{"time": "15:00", "phase": "收盘完成", "note": "巡检"}],
            capital_ratio=1.0,
        )
        self.assertEqual(thin.capital["ratio_close"], 1.26, "富快照的资金数据必须保留")
        self.assertTrue(thin.phase_path, "新写入的阶段路径要生效")
        back = self.store.load("2026-10-23")
        self.assertEqual(back.capital["amount_wan"], 9999.0)
        self.assertEqual(back.source, "live")

    def test_missing_marks_self_heal(self):
        """缺失标记必须自愈：薄写入留下的 tracker 缺失，富写入补齐后要消失。"""
        thin = self.store.close_day("2026-10-23", phase_path=[])   # 无 tracker -> 记 missing
        self.assertIn("tracker", thin.missing)
        rich = self.store.close_day("2026-10-23", tracker=_FakeTracker(), phase_path=[])
        self.assertNotIn("tracker", rich.missing, "补齐后缺失标记必须自愈")
        self.assertTrue(rich.signals.get("states"))

    def test_amount_missing_survives_capital_ratio_fill(self):
        """amount 与 capital_ratio 同属 capital 但子键不同：补了量能比不能算补了成交额。"""
        ctx = self.store.close_day("2026-10-23", phase_path=[], capital_ratio=1.26)
        self.assertEqual(ctx.capital.get("ratio_close"), 1.26)
        self.assertIn("amount", ctx.missing, "成交额仍缺，不能因为量能比有了就抹掉")

    def test_prune_keeps_bounded(self):
        store = SessionContextStore(root=self.root, keep_days=2)
        for d in ("2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"):
            store.close_day(d, phase_path=[], capital_ratio=1.0)
        self.assertEqual(store.days(), ["2026-10-22", "2026-10-23"])

    def test_corrupt_file_is_ignored(self):
        """坏文件不能让读取方炸：load 返回 None，recent/handoff 自动跳过它。"""
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, "2026-10-24.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        self._close("2026-10-23")
        self.assertIsNone(self.store.load("2026-10-24"))
        recent = self.store.recent(5)
        self.assertEqual([c.day for c in recent], ["2026-10-23"], "坏快照不应进交接")
        h = self.store.handoff("2026-10-25")
        self.assertEqual(h["days"], 1)


class TestLedgerSummary(unittest.TestCase):
    """信号账本（数据库信号/记录）是上下文的一部分，但要防张冠李戴。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, date, total, tiers):
        import gzip

        payload = {"date": date, "total_signals": total, "tier_counts": tiers,
                   "entries": [{"action": "RADAR"}] * total}
        path = os.path.join(self.dir, "signal_ledger_latest.json.gz")
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

    def test_matching_day_returns_counts(self):
        from ats.fusion.session_ctx import ledger_summary

        self._write("2026-10-22", 1141, {"RADAR": 1140, "WATCH": 1})
        out = ledger_summary("2026-10-22", root=self.dir)
        self.assertEqual(out.get("ledger_total"), 1141)
        self.assertEqual(out.get("ledger_RADAR"), 1140)

    def test_other_day_returns_empty(self):
        """账本是"最新一天"快照：日期不符必须返回空，不能把 10/22 的账记到 10/23 上。"""
        from ats.fusion.session_ctx import ledger_summary

        self._write("2026-10-22", 1141, {"RADAR": 1140})
        self.assertEqual(ledger_summary("2026-10-23", root=self.dir), {})

    def test_missing_file_returns_empty(self):
        from ats.fusion.session_ctx import ledger_summary

        self.assertEqual(ledger_summary("2026-10-22", root=self.dir), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
