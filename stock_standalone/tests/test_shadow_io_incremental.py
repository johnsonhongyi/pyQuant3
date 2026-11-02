# -*- coding: utf-8 -*-
"""tests/test_shadow_io_incremental.py — 影子日志增量读取不变量。

背景：影子分片在交易时段持续追加，看板每 2 秒刷新一次。旧实现每次刷新都把
整份分片重新解析（当日 220MB 实测 12.6 秒），单核长期打满、UI 线程被阻塞。
本测试锁定增量读取必须满足的六条不变量，避免退回全量重读。
"""

import gzip
import json
import os
import unittest

from ats.fusion.shadow_io import DayLogCursor, read_paths, record_key


def _rec(code="300001", ts=1000.0, source="live_strategy", **extra):
    row = {"code": code, "ts": ts, "source": source, "hit": False, "pct": 1.5}
    row.update(extra)
    return row


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append(path, rows):
    with open(path, "a", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


class ReadPathsDedupTest(unittest.TestCase):
    def test_identical_bytes_are_deduplicated(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-11-02.jsonl")
            rows = [_rec(ts=1.0), _rec(ts=2.0)]
            _write(path, rows + rows)          # 字节完全一致的副本
            out, errors = read_paths([path])
            self.assertEqual([], errors)
            self.assertEqual(2, len(out))

    def test_reserialized_copy_shares_semantic_key(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.jsonl")
            b = os.path.join(tmp, "b.jsonl")
            _write(a, [_rec(ts=5.0)])
            # UI 收盘副本：补全名称、加来源标记，字节不同但仍是同一条观测
            _write(b, [_rec(ts=5.0, name="测试", _source_ui=True)])
            out, _ = read_paths([a, b])
            self.assertEqual(1, len(out))

    def test_distinct_records_survive(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "2026-11-02.jsonl")
            _write(path, [_rec(ts=1.0), _rec(ts=1.001), _rec(code="600000", ts=1.0)])
            out, _ = read_paths([path])
            self.assertEqual(3, len(out))

    def test_record_key_is_stable_across_extra_fields(self):
        self.assertEqual(record_key(_rec(ts=3.0)), record_key(_rec(ts=3.0, name="x", extra=1)))


class DayLogCursorTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "2026-11-02_1234.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_read_matches_full_read(self):
        rows = [_rec(ts=float(i)) for i in range(50)]
        _write(self.path, rows)
        cursor = DayLogCursor(max_records=1000)
        cursor.refresh([self.path])
        self.assertEqual(len(read_paths([self.path])[0]), len(cursor.rows()))

    def test_steady_state_is_noop(self):
        _write(self.path, [_rec(ts=1.0)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        version = cursor.version
        cursor.refresh([self.path])
        self.assertEqual(version, cursor.version, "文件未变时不应产生新版本")
        self.assertEqual(1, len(cursor.rows()))

    def test_append_only_parses_new_lines(self):
        _write(self.path, [_rec(ts=1.0)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        _append(self.path, [_rec(ts=2.0), _rec(ts=3.0)])
        self.assertTrue(cursor.refresh([self.path]))
        self.assertEqual(3, len(cursor.rows()))

    def test_partial_line_waits_for_completion(self):
        _write(self.path, [_rec(ts=1.0)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        payload = json.dumps(_rec(ts=2.0), ensure_ascii=False).encode("utf-8")
        with open(self.path, "ab") as stream:
            stream.write(b"\n" + payload[:20])
        cursor.refresh([self.path])
        self.assertEqual(1, len(cursor.rows()), "半行不应被解析")
        with open(self.path, "ab") as stream:
            stream.write(payload[20:] + b"\n")
        cursor.refresh([self.path])
        self.assertEqual(2, len(cursor.rows()), "补齐后应落地")

    def test_line_across_read_chunks_keeps_hydration_offset(self):
        from ats.fusion.shadow_io import hydrate

        payload = "x" * (1024 * 1024 + 100)
        _write(self.path, [_rec(ts=1.0, observation_evidence={"pad": payload})])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        self.assertEqual(1, len(cursor.rows()))
        self.assertEqual(payload, hydrate(cursor.rows()[0])["observation_evidence"]["pad"])

    def test_truncation_rebuilds_dataset(self):
        _write(self.path, [_rec(ts=float(i)) for i in range(10)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        _write(self.path, [_rec(ts=99.0)])
        cursor.refresh([self.path])
        self.assertEqual(1, len(cursor.rows()))

    def test_same_size_rewrite_rebuilds_dataset(self):
        _write(self.path, [_rec(ts=1.0)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        _write(self.path, [_rec(ts=2.0)])
        cursor.refresh([self.path])
        self.assertEqual([2.0], [row["ts"] for row in cursor.rows()])

    def test_max_records_keeps_newest_tail(self):
        _write(self.path, [_rec(ts=float(i)) for i in range(30)])
        cursor = DayLogCursor(max_records=10)
        cursor.refresh([self.path])
        rows = cursor.rows()
        self.assertEqual(10, len(rows))
        self.assertEqual(29.0, rows[-1]["ts"])

    def test_gzip_shard_is_supported(self):
        gz = self.path + ".gz"
        with gzip.open(gz, "wt", encoding="utf-8") as stream:
            for i in range(5):
                stream.write(json.dumps(_rec(ts=float(i)), ensure_ascii=False) + "\n")
        cursor = DayLogCursor()
        cursor.refresh([gz])
        self.assertEqual(5, len(cursor.rows()))
        cursor.refresh([gz])
        self.assertEqual(5, len(cursor.rows()), "压缩档未变时不重复累加")

    def test_corrupt_line_does_not_break_cursor(self):
        _write(self.path, [_rec(ts=1.0)])
        with open(self.path, "a", encoding="utf-8") as stream:
            stream.write("{not json}\n")
        _append(self.path, [_rec(ts=2.0)])
        cursor = DayLogCursor()
        cursor.refresh([self.path])
        self.assertEqual(2, len(cursor.rows()))
        self.assertTrue(cursor.errors)


class CompactRecordTest(unittest.TestCase):
    """常驻记录结构：冷字段剥离 + 按偏移水合。"""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "2026-11-02_1234.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def _row(self, ts=1.0, **extra):
        row = _rec(ts=ts)
        row.update({
            "fusion": {"tier": 3, "rar": 88.5, "sources": ["live_strategy"]},
            "struct": {"status": "CONFIRMED", "confirm_n": 2},
            "observation_evidence": {
                "role": "observation_only", "freshness": "same_day",
                "early_signals": {"sig_launch": {"value": 1, "freshness": "same_day"}},
                "vwap": {"ordered_1_3_5_10": True,
                         "above_previous_session": {"1": True, "3": True, "5": True, "10": True}},
            },
            "track": {"stage": "跟踪中", "enter_ts": ts, "enter_price": 12.5, "enter_pct": 3.2},
            "reclaim_detail": {"vwap3": 1.0, "vwap5": 2.0},
            "legacy": {"old": 1},
        })
        row.update(extra)
        return row

    def test_cold_fields_stripped_hot_fields_kept(self):
        from ats.fusion.shadow_io import COLD_FIELDS

        _write(self.path, [self._row()])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        rec = cursor.rows()[0]
        for key in COLD_FIELDS:
            self.assertNotIn(key, rec)
        self.assertEqual(3, rec["fusion"]["tier"])
        self.assertEqual("CONFIRMED", rec["struct"]["status"])
        self.assertIsNotNone(rec.get("_raw_ref"))

    def test_hydrate_restores_byte_exact_cold_fields(self):
        from ats.fusion.shadow_io import hydrate

        original = self._row()
        _write(self.path, [original])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        rec = cursor.rows()[0]
        self.assertNotIn("observation_evidence", rec)
        hydrate(rec)
        for key in ("observation_evidence", "track", "reclaim_detail", "legacy"):
            self.assertEqual(original[key], rec[key], key)
        self.assertNotIn("_raw_ref", rec, "水合后应释放回读位置")

    def test_derived_values_survive_stripping(self):
        _write(self.path, [self._row()])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        rec = cursor.rows()[0]
        self.assertEqual("跟踪中", rec.get("_track_stage"))
        self.assertEqual("早盘策略观察", rec.get("_evidence_reason"))

    def test_hydrate_is_noop_without_ref(self):
        from ats.fusion.shadow_io import hydrate

        plain = {"code": "300001", "ts": 1.0}
        self.assertIs(plain, hydrate(plain))

    def test_hydrate_survives_missing_file(self):
        from ats.fusion.shadow_io import hydrate

        _write(self.path, [self._row()])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        rec = cursor.rows()[0]
        os.remove(self.path)
        hydrate(rec)                      # 不应抛异常
        self.assertNotIn("observation_evidence", rec)

    def test_hydrate_rejects_replaced_line(self):
        from ats.fusion.shadow_io import hydrate

        _write(self.path, [self._row(ts=1.0)])
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        rec = cursor.rows()[0]
        _write(self.path, [self._row(ts=2.0)])
        hydrate(rec)
        self.assertNotIn("observation_evidence", rec)

    def test_plain_mode_keeps_full_records(self):
        _write(self.path, [self._row()])
        cursor = DayLogCursor(compact=False)
        cursor.refresh([self.path])
        self.assertIn("observation_evidence", cursor.rows()[0])

    def test_cross_day_hydrates_only_latest_evidence(self):
        import time
        from unittest.mock import patch
        from ats.fusion.cross_day import build_cross_day
        from ats.fusion.shadow_io import hydrate

        day = "2026-11-02"
        ts = time.mktime((2026, 11, 2, 10, 0, 0, 0, 0, -1))
        rows = [self._row(ts=ts + i, price=12.5 + i, day=day, trade_date=day)
                for i in range(2)]
        _write(self.path, rows)
        cursor = DayLogCursor(compact=True)
        cursor.refresh([self.path])
        with patch("ats.fusion.shadow_io.hydrate", wraps=hydrate) as read_cold:
            result = build_cross_day({day: {"300001": cursor.rows()}}, day)
        self.assertEqual(1, read_cold.call_count)
        self.assertEqual(rows[-1]["observation_evidence"], result[0]["timeline"][0]["observation_evidence"])
        self.assertNotIn("observation_evidence", cursor.rows()[-1])


if __name__ == "__main__":
    unittest.main()
