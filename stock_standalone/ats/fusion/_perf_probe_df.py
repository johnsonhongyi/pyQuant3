# -*- coding: utf-8 -*-
"""live_bridge.on_df 全量行情帧的性能画像（有界，不联网、不下单）。

回答两个问题：
    1. 一帧全市场行情（5576 只）喂进 on_df 要多久？能不能塞进 3 秒推送间隔？
    2. 连续跑 N 帧，内存会不会涨（跟踪器状态是否只增不减）？
"""

import gc
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ats.fusion.live_bridge import FusionLiveBridge
from ats.fusion.replay import load_minute_cache


def build_frame(day: str = "2026-10-23") -> pd.DataFrame:
    """从真实分钟线缓存取当日最后一根，构造一帧全量行情（字段与实盘一致）。"""
    cache = load_minute_cache()
    rows = {}
    for code, arr in cache.items():
        if not len(arr):
            continue
        ts = arr["time"].astype("int64")
        day_ts = int(pd.Timestamp(day).timestamp())
        m = (ts >= day_ts) & (ts < day_ts + 86400)
        if not m.any():
            continue
        sub = arr[m]
        last = sub[-1]
        pre = float(sub["close"][0])
        close = float(last["close"])
        vol = np.asarray(sub["volume"], dtype=float)
        v0 = float(np.mean(vol[:5])) if len(vol) >= 5 else float(np.mean(vol))
        rows[code] = {
            "trade": close,
            "percent": (close / pre - 1.0) * 100.0 if pre > 0 else 0.0,
            "open": float(sub["open"][0]),
            "high": float(np.max(sub["high"])),
            "low": float(np.min(sub["low"])),
            "pre_close": pre,
            "vol_ratio": float(np.mean(vol) / max(1e-9, v0)),
            "vwap": float(np.sum(sub["close"] * vol) / max(1e-9, float(np.sum(vol)))),
            "name": code,
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index = [str(c).zfill(6) for c in df.index]
    return df


def rss_mb() -> float:
    try:
        import psutil

        return psutil.Process().memory_info().rss / 1024.0 / 1024.0
    except Exception:
        return -1.0


def main() -> int:
    df = build_frame()
    print("帧大小 {} 只 × {} 列".format(len(df), len(df.columns)))
    bridge = FusionLiveBridge(state_path=os.path.join("logs", "fusion_state", "_perf_probe.json"))
    ts = time.time()

    # 1) 冷启动一帧
    gc.collect()
    r0 = rss_mb()
    t0 = time.time()
    n = bridge.on_df(df, now=ts)
    t_cold = time.time() - t0
    r1 = rss_mb()
    print("冷启帧：{} 只，{:.2f}s，RSS {:.0f}→{:.0f} MB（+{:.0f}）".format(n, t_cold, r0, r1, r1 - r0))

    # 2) 连续 10 帧（模拟 3 秒推送间隔）
    gc.collect()
    times = []
    for i in range(10):
        t0 = time.time()
        bridge.on_df(df, now=ts + 3 * (i + 1))
        times.append(time.time() - t0)
    r2 = rss_mb()
    print("连续帧：最快 {:.2f}s / 最慢 {:.2f}s / 均值 {:.2f}s｜RSS {:.0f}→{:.0f} MB".format(
        min(times), max(times), float(np.mean(times)), r1, r2))

    # 3) 跟踪器规模
    sts = bridge.tracker.states()
    print("跟踪器状态 {} 条｜入局 {}｜错误 {}".format(
        len(sts), bridge.stats.get("entries", 0), bridge.stats.get("errors", 0)))

    # 4) 落盘耗时（每日收盘一次，但要看量级）
    t0 = time.time()
    bridge.save()
    print("save() {:.2f}s".format(time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
