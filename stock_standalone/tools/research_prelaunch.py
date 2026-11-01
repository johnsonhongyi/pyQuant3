# -*- coding: utf-8 -*-
"""只读逐时快照，检验启动前观察条件；不生成交易指令。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ats.fusion.context import _find_daily_path
from ats.fusion.liquidity_history import DailyLiquidityHistory
from ats.fusion.sector import get_sector_map
from tools.research_quote_panel import _quotes


def build_panel(store, daily, day, at, sectors, liquidity_by_code=None):
    moment = pd.Timestamp(day + " " + at)
    def snapshot(minutes):
        end = moment - pd.Timedelta(minutes=minutes)
        return _quotes(store, day, (end - pd.Timedelta(minutes=3)).strftime("%H:%M:%S"), end.strftime("%H:%M:%S"))
    now = snapshot(0)
    empty = pd.DataFrame(columns=["close", "volume"], index=pd.Index([], name="code"))
    # 集合竞价不可与连续竞价混用：缺少足够盘中历史时，速度/量能保持未知。
    prior = snapshot(10) if moment - pd.Timedelta(minutes=10) >= pd.Timestamp(day + " 09:30") else empty
    prior2 = snapshot(20) if moment - pd.Timedelta(minutes=20) >= pd.Timestamp(day + " 09:30") else empty
    if now.empty:
        return pd.DataFrame()
    past_days = sorted(daily.loc[daily["date"] < pd.Timestamp(day), "date"].unique())
    if not past_days:
        return pd.DataFrame()
    previous = daily[daily["date"] == past_days[-1]].set_index("code")[["close"]].rename(columns={"close": "prev_close"})
    panel = now.join(previous, how="inner")
    panel = panel.join(prior[["close", "volume"]].rename(columns={"close": "price_10m", "volume": "volume_10m"}), how="left")
    panel = panel.join(prior2[["volume"]].rename(columns={"volume": "volume_20m"}), how="left")
    panel = panel[(panel[["close", "prev_close", "high", "low"]] > 0).all(axis=1)
                  & (panel["low"] <= panel["close"]) & (panel["close"] <= panel["high"])].copy()
    panel["pct"] = (panel["close"] / panel["prev_close"] - 1) * 100
    panel["ret10"] = (panel["close"] / panel["price_10m"] - 1) * 100
    previous_volume = panel["volume_10m"] - panel["volume_20m"]
    panel["volume_accel"] = (panel["volume"] - panel["volume_10m"]) / previous_volume.where(previous_volume > 0)
    panel["near_high"] = panel["close"] / panel["high"]
    panel["sector"] = [sectors.get(c) for c in panel.index]
    panel["sector_n"] = panel.groupby("sector")["pct"].transform("count")
    panel["sector_pct"] = panel.groupby("sector")["pct"].transform("median")
    if liquidity_by_code:
        history = pd.DataFrame.from_dict(liquidity_by_code, orient="index")
        panel = panel.join(history[["turnover_pct", "volume_ratio", "date"]].rename(
            columns={"turnover_pct": "archived_turnover", "volume_ratio": "archived_volume_ratio", "date": "archive_date"}), how="left")
    market_median = float(panel["pct"].median())
    future_end = moment + pd.Timedelta(minutes=30)
    ticks = store.select("/all_30", where=[f'ticktime > Timestamp("{moment}")',
                                           f'ticktime <= Timestamp("{future_end}")'],
                         columns=["close"]).reset_index()
    ticks["code"] = ticks["code"].astype(str).str.zfill(6)
    ticks = ticks[(ticks["close"] > 0) & ticks["code"].isin(panel.index)]
    future = ticks.groupby("code").agg(future_high=("close", "max"), future_low=("close", "min"),
                                       future_last=("ticktime", "max"))
    # 少于 24 分钟的后续轨迹不作负样本。
    future = future[future["future_last"] >= moment + pd.Timedelta(minutes=24)]
    panel = panel.join(future, how="inner")
    panel["mfe30"] = (panel["future_high"] / panel["close"] - 1) * 100
    panel["mae30"] = (panel["future_low"] / panel["close"] - 1) * 100
    panel.attrs["market_median"] = market_median
    return panel


def analyze(panel):
    market = panel.attrs.get("market_median")
    relative = (panel["sector_n"] >= 3) & (panel["sector"] != "未分类") & (panel["sector_pct"] >= market + 0.5)
    restrained = panel["pct"].between(0, 3) & panel["ret10"].between(0, 1) & (panel["near_high"] >= 0.985)
    masks = {"all": pd.Series(True, index=panel.index), "sector_relative": relative,
             "restrained_rise": restrained, "combined_observation": relative & restrained,
             "sector_pullback_observation": relative & panel["pct"].between(-1, 1.5)
             & panel["ret10"].between(-1.5, 0) & (panel["near_high"] >= 0.98)}
    if "archived_turnover" in panel:
        masks["archived_turnover_10_to_30"] = panel["archived_turnover"].between(10, 30)
        masks["archived_volume_ratio_ge_1_2"] = panel["archived_volume_ratio"] >= 1.2
    out = {"market_median_pct": round(market, 2), "groups": {}}
    for name, mask in masks.items():
        sub = panel[mask]
        positives = int((sub["mfe30"] >= 1.5).sum())
        out["groups"][name] = {"n": len(sub), "rise_1_5pct_30m": positives,
                                "rate": round(positives / len(sub), 4) if len(sub) else None,
                                "down_1pct_30m": round(float((sub["mae30"] <= -1).mean()), 4) if len(sub) else None}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", default=r"G:\sina_MultiIndex_data.h5")
    parser.add_argument("--daily", default=None)
    parser.add_argument("--days", nargs="+", default=["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"])
    parser.add_argument("--times", nargs="+", default=["09:38", "10:00", "10:30", "14:00"])
    parser.add_argument("--output", default=None, help="可选的独立 JSON 报告路径")
    args = parser.parse_args()
    daily_path = args.daily or _find_daily_path()
    daily = pd.read_hdf(daily_path, key="/all_300")
    if daily[daily.index.duplicated(keep=False)].groupby(level=[0, 1]).nunique(dropna=False).gt(1).any(axis=None):
        raise ValueError("日线存在冲突重复记录")
    daily = daily[~daily.index.duplicated(keep="last")].reset_index()
    daily["code"] = daily["code"].astype(str).str.zfill(6)
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    sectors = get_sector_map()
    if not sectors.ok:
        raise ValueError("没有可用板块分类，不计算板块分组")
    liquidity = DailyLiquidityHistory()
    results = {"method": "当时快照和前 20 分钟数据；之后 30 分钟仅用于标签；非交易指令",
               "warning": "候选组合未经独立交易日验证，仅供研究，不得作为买入或预言启动的依据",
               "snapshots_source": args.snapshots, "daily_source": daily_path,
               "sector_source": sectors.path, "sector_limitation": "分类是当前快照，历史分类可能不同",
               "liquidity_archive": {"status": liquidity.status, "source": liquidity.path, "error": liquidity.error,
                                     "limitation": "仅取当日前归档；写入时间未知，量比可能含默认或推算值"}, "days": {}}
    with pd.HDFStore(args.snapshots, "r") as store:
        for day in args.days:
            print("研究 {}：{} 个时点".format(day, len(args.times)), file=sys.stderr, flush=True)
            results["days"][day] = {}
            liquidity_by_code = {}
            if liquidity.status == "ready":
                for code in liquidity._rows:
                    earlier = liquidity.asof(code, day, limit=1)["history"]
                    if earlier:
                        liquidity_by_code[code] = earlier[0]
            for at in args.times:
                panel = build_panel(store, daily, day, at, sectors, liquidity_by_code)
                if panel.empty:
                    results["days"][day][at] = {"status": "insufficient"}
                    continue
                report = analyze(panel)
                report["examples"] = {}
                for code in ("000568", "600809", "000995"):
                    if code in panel.index:
                        row = panel.loc[code]
                        report["examples"][code] = {k: round(float(row[k]), 3) if pd.notna(row[k]) else None
                                                     for k in ("close", "pct", "ret10", "volume_accel", "sector_pct", "mfe30", "mae30")}
                        if "archive_date" in row:
                            report["examples"][code]["archive_date"] = row.get("archive_date") if pd.notna(row.get("archive_date")) else None
                            for key in ("archived_turnover", "archived_volume_ratio"):
                                report["examples"][code][key] = round(float(row[key]), 2) if pd.notna(row.get(key)) else None
                results["days"][day][at] = report
    rendered = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        print("报告：{}".format(path))
    else:
        print(rendered)


if __name__ == "__main__":
    main()
