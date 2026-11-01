# -*- coding: utf-8 -*-
"""按事件可见时间读取生产梯度与账本快照，不将回放回补当作实盘事实。"""
from __future__ import annotations

import gzip
import json
import os
import zlib
from datetime import datetime

from ats.fusion.adapter import today_str
from ats.fusion.source_identity import is_replay_record


class HistoricalEvents:
    def __init__(self, root, day):
        self.day = day
        self.events = []
        self.latest = {}
        self.cursor = 0
        from ats.fusion.shadow_io import day_paths, log_directories
        paths = day_paths(log_directories(os.path.join(root, "logs", "fusion_shadow")), day)
        self.stats = {"gradient": 0, "ledger": 0, "gradient_file_present": bool(paths),
                      "ledger_snapshot_for_day": False, "excluded_backfill": 0, "invalid": 0, "errors": []}
        for path in paths:
            self._gradient(path)
        self._ledger(os.path.join(root, "logs", "signal_snapshots"))
        self.events.sort(key=lambda event: event[0])

    def _add(self, ts, code, kind, data):
        try:
            ts = float(ts)
            code = str(code or "").split(".")[0].zfill(6)
            if ts <= 0 or len(code) != 6 or not code.isdigit() or today_str(ts) != self.day:
                raise ValueError("invalid event identity or trade date")
            self.events.append((ts, code, kind, data))
            self.stats[kind] += 1
        except (ValueError, TypeError, OverflowError, OSError):
            self.stats["invalid"] += 1

    def _gradient(self, path):
        if not os.path.isfile(path):
            return
        initial_count = len(self.events)
        initial_gradient = self.stats["gradient"]
        try:
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("invalid record")
                        if row.get("trade_date") and str(row["trade_date"])[:10] != self.day:
                            raise ValueError("cross-day record")
                        if is_replay_record(row):
                            self.stats["excluded_backfill"] += 1
                            continue
                        fusion = row.get("fusion") or {}
                        self._add(row.get("ts"), row.get("code"), "gradient", {
                            "tier": int(fusion.get("tier") or 0),
                            "rar": float(fusion.get("rar") or 0),
                            "veto": str(fusion.get("veto_reason") or ""),
                            "patterns": list(row.get("patterns") or []),
                            "source": str(row.get("source") or ""),
                            "coverage": row.get("coverage"),
                        })
                    except (ValueError, TypeError, OverflowError, AttributeError, json.JSONDecodeError):
                        self.stats["invalid"] += 1
        except (OSError, EOFError, UnicodeError, zlib.error) as exc:
            # 压缩流末尾损坏时，不能把前半段当作完整历史。
            del self.events[initial_count:]
            self.stats["gradient"] = initial_gradient
            self.stats["errors"].append("gradient: {}".format(exc))

    def _ledger(self, directory):
        # 固定文件是一次快照：其字段最早只能在快照时刻使用。
        for name in ("signal_ledger_latest.json.gz", "signal_ledger_latest.json"):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            try:
                opener = gzip.open if name.endswith(".gz") else open
                with opener(path, "rt", encoding="utf-8") as stream:
                    snapshot = json.load(stream)
                if snapshot.get("date") != self.day:
                    continue
                self.stats["ledger_snapshot_for_day"] = True
                ts = datetime.fromisoformat(snapshot["timestamp"]).timestamp()
                entries = snapshot.get("entries") or {}
                rows = entries.items() if isinstance(entries, dict) else ((x.get("code"), x) for x in entries)
                for code, row in rows:
                    if isinstance(row, dict):
                        self._add(ts, code, "ledger", {
                            "tier": str(row.get("tier") or ""),
                            "signal_source": str(row.get("signal_source") or ""),
                            "signal_tag": str(row.get("signal_tag") or ""),
                            "first_seen_ts": row.get("first_seen_ts"),
                        })
                break
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                self.stats["errors"].append("ledger: {}".format(exc))

    def advance(self, ts):
        """消费不晚于 ts 的事件，返回本次新增事件；无效日数据不跨日携带。"""
        added = []
        while self.cursor < len(self.events) and self.events[self.cursor][0] <= ts:
            event_ts, code, kind, data = self.events[self.cursor]
            self.cursor += 1
            self.latest.setdefault(code, {})[kind] = dict(data, observed_ts=event_ts)
            added.append((code, kind, data))
        return added
