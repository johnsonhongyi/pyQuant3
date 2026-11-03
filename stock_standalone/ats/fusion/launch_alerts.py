# -*- coding: utf-8 -*-
"""ATS 主线程读取新增融合梯度记录并借用原有 AlertNotifier 提醒。

不依赖梯度窗口是否打开；默认跳过启动前旧记录、回放、过期和被否决信号。
只输出人工确认提示，不调用交易网关。
"""
from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

from ats.fusion.adapter import in_trading_session, today_str
from ats.fusion.config import load_config
from ats.fusion.source_identity import is_replay_record


def eligible_launch_alert(record, now: float) -> bool:
    """只允许可信、最新、正式实盘来源的人工确认提示。"""
    launch = record.get("launch_signal") or {}
    fusion = record.get("fusion") or {}
    age = now - float(record.get("ts") or 0)
    return bool(
        launch.get("permission") == "MANUAL_CONFIRM"
        and launch.get("status") == "CONFIRMED"
        and record.get("day") == today_str(now)
        and record.get("trade_date") == today_str(now)
        and record.get("source") in ("live_strategy", "strategy_observation", "vanguard_funnel")
        and not is_replay_record(record)
        and 0 <= age <= 20
        and record.get("pct") is not None
        and not {"pct", "vwap"} & set(record.get("missing") or ())
        and int(fusion.get("tier") or 0) >= 2
        and not fusion.get("veto_reason")
        and float(fusion.get("coverage") or 0) >= 0.70
        and not bool(fusion.get("provisional"))
        and not bool((record.get("legacy") or {}).get("vetoed"))
    )


class LaunchAlertPoller:
    """增量读取本地 JSONL，有限 IO，单股同类每日一次，不回补过去报警。"""

    def __init__(self, sink: Callable[[dict], None], log_dir: Optional[str] = None):
        self._sink = sink
        self._log_dir = log_dir
        self._offsets = {}
        self._day = ""
        self._seen = set()

    def _paths(self, day):
        if self._log_dir is not None:
            directories = [self._log_dir]
        else:
            from sys_utils import get_app_root
            from ats.fusion.shadow_io import log_directories
            cfg = load_config()
            root = os.path.join(get_app_root(), cfg.get("log_dir", "logs/fusion_shadow"))
            directories = log_directories(root)
        from ats.fusion.shadow_io import day_paths
        # 按进程真实分片读取；RAMDisk 与本地镜像选择较新副本，压缩归档从不报警。
        return [p for p in day_paths(directories, day) if p.endswith(".jsonl")]

    def poll(self, now: Optional[float] = None) -> int:
        now = float(time.time() if now is None else now)
        if not in_trading_session(now):
            return 0
        day = today_str(now)
        if day != self._day:
            self._day, self._seen, self._offsets = day, set(), {}
        return sum(self._poll_file(path, day, now) for path in self._paths(day))

    def _poll_file(self, path: str, day: str, now: float) -> int:
        try:
            size = os.path.getsize(path)
            if path not in self._offsets:
                # 有限回看，仍由 20 秒新鲜度闸门禁止补报历史。
                self._offsets[path] = max(0, size - 262144)
            if size < self._offsets[path]:
                self._offsets[path] = 0
            with open(path, "rb") as f:
                f.seek(self._offsets[path])
                blob = f.read(262144)
                end = f.tell()
            if not blob:
                return 0
            complete = blob.rfind(b"\n")
            if complete < 0:
                return 0
            self._offsets[path] = end - (len(blob) - complete - 1)
        except OSError:
            return 0

        count = 0
        for line in blob[:complete].splitlines():
            try:
                record = json.loads(line)
                if not eligible_launch_alert(record, now):
                    continue
                launch = record["launch_signal"]
                key = (day, str(record.get("code") or ""), str(launch.get("type") or ""))
                if key in self._seen:
                    continue
                self._sink(record)
                self._seen.add(key)
                count += 1
            except (ValueError, TypeError, KeyError):
                continue
        return count
