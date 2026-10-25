# -*- coding: utf-8 -*-
"""ats/fusion/live_bridge.py — 把赛马跟踪层接到**现有的 IPC 数据管道**上。

⚠ 重要事实（用户指出）：
    `ats/ipc_bridge.py` 推的是 **df 全量行情**（UPDATE_DF_ALL / UPDATE_DF_DIFF），
    **不是**异动信号；异动信号是交易中心那边另行接入的。
    所以本桥的主入口是 `on_df(df)`：自己从全量行情里算形态、算陷阱、算趋同，
    再喂给 RaceTracker。`on_signal()` 保留给交易中心的信号（若有）。



刻意不新开一套系统：
    系统已经在 `ats/ipc_bridge.py` 里把实时行情、异动信号、检测结果通过
    `start_realtime_listener(port, data_callback, signal_callback, linkage_callback)`
    推出来。本模块只是**订阅者**——注册一个 `signal_callback`，
    把已经流过的信号喂进同一个 RaceTracker，形成"带历史"的判断。

职责边界：
    - 不改 IPC 协议、不改上游模块、不新增进程；
    - 回调里任何异常都必须吞掉，绝不能影响行情线程；
    - 只产出"观察/入局/可下单/减半/清仓"的结论，不下单。

信号字段容错：
    上游不同模块的信号字段名不统一（code/secid/stock_code、price/last/now、
    pct/change_pct/涨幅…），这里用候选键逐个取，取不到就走默认值。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from ats.fusion.tracker import (
    RaceTracker,
    TrackConfig,
    STAGE_ENTER,
    STAGE_EVICT,
    STAGE_HOLD,
    STAGE_WATCH,
    deploy_path,
)

DEFAULT_STATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "fusion_state", "tracker_state.json",
)


def _num(payload: Dict[str, Any], keys, default: float = 0.0) -> float:
    for k in keys:
        v = payload.get(k)
        if v is None:
            continue
        try:
            f = float(v)
            if f == f:  # 排除 NaN
                return f
        except (TypeError, ValueError):
            continue
    return default


def _code(payload: Dict[str, Any]) -> str:
    for k in ("code", "secid", "stock_code", "symbol", "ts_code"):
        v = payload.get(k)
        if v:
            s = str(v).strip()
            if s.isdigit():
                return s.zfill(6)
            if "." in s:  # 600000.SH
                return s.split(".")[0].zfill(6)
    return ""


def _patterns(payload: Dict[str, Any]) -> List[str]:
    v = payload.get("patterns") or payload.get("pattern") or payload.get("tags")
    if isinstance(v, str):
        return [x.strip() for x in v.replace("|", ",").split(",") if x.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x]
    return []


class FusionLiveBridge:
    """订阅现有 IPC 信号，维护一只票一条状态的连续判断。"""

    def __init__(
        self,
        tracker: Optional[RaceTracker] = None,
        state_path: str = DEFAULT_STATE,
        config: Optional[TrackConfig] = None,
        vwap10_provider=None,
    ):
        self.tracker = tracker or RaceTracker(config or TrackConfig())
        self.state_path = state_path
        self.vwap10_provider = vwap10_provider
        self._last_save = 0.0
        self._alerts: List[Dict[str, Any]] = []
        self.stats = {"signals": 0, "entries": 0, "deployable": 0, "errors": 0}
        self._load()

    # -- 生命周期 -----------------------------------------------------------
    def _load(self) -> None:
        try:
            n = self.tracker.load(self.state_path)
            if n:
                self.stats["restored"] = n
        except Exception:
            pass

    def save(self) -> int:
        try:
            n = self.tracker.save(self.state_path)
            self._last_save = time.time()
            return n
        except Exception:
            return 0

    # -- 接现有 IPC ---------------------------------------------------------
    def attach(self, ipc_bridge) -> bool:
        """把本桥注册为现有 IPC 管道的信号订阅者。

        调用方式与系统一致：
            bridge.start_realtime_listener(port, data_callback, signal_callback)
        这里只替换 signal_callback，其余保持原样由调用方决定。
        """
        try:
            ipc_bridge.signal_callback = self.on_signal  # 若桥支持属性注入
            return True
        except Exception:
            return False

    def make_callback(self):
        """返回可直接传给 start_realtime_listener(signal_callback=...) 的函数。"""

        def _cb(body):
            try:
                if isinstance(body, list):
                    for item in body:
                        self.on_signal(item)
                else:
                    self.on_signal(body)
            except Exception:
                self.stats["errors"] += 1

        return _cb

    # -- df 全量行情（主入口）----------------------------------------------
    def on_df(self, df, now: Optional[float] = None, day: Optional[str] = None) -> int:
        """吃一帧全量行情（DataFrame，index=代码），逐票更新跟踪器。

        需要的列（有就用，没有就退化）：
            trade/price/last/now  现价
            percent/pct/涨幅      当日涨幅
            open/high/low         开盘/最高/最低
            pre_close/prev_close  昨收
            volume/vol、amount    量、额
            vol_ratio             量比
            vwap                  均价
            name                  名称
        返回本帧处理的票数。任何异常都吞掉，绝不影响行情线程。
        """
        try:
            import numpy as np
            import pandas as pd
        except Exception:
            return 0
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return 0

        ts = float(now or time.time())
        day = day or time.strftime("%Y-%m-%d", time.localtime(ts))
        n = 0
        try:
            cols = {str(c).lower(): c for c in df.columns}
        except Exception:
            return 0

        def col(*names):
            for nm in names:
                if nm in cols:
                    return cols[nm]
            return None

        c_price = col("trade", "price", "last", "now", "lastp")
        c_pct = col("percent", "pct", "change_pct", "pct_chg")
        c_open = col("open", "today_open")
        c_high = col("high")
        c_low = col("low")
        c_pre = col("pre_close", "prev_close", "preclose", "yclose")
        c_vr = col("vol_ratio", "volume_ratio")
        c_vwap = col("vwap", "avg_price")
        c_name = col("name", "stock_name")

        if c_price is None:
            return 0

        try:
            from ats.fusion.anomaly import detect_patterns
            from ats.fusion.context import get_daily_context
            from ats.fusion.market_ctx import MarketHistory
            from ats.fusion.trap import cross_day_risk, detect_traps

            dctx = get_daily_context()
            mkt = MarketHistory()
        except Exception:
            detect_patterns = None

        # 市场宽度（用于趋同度）
        try:
            pcts = df[c_pct].astype(float) if c_pct is not None else None
            breadth = float((pcts > 0).mean()) if pcts is not None else 0.5
            crowd = float((pcts > 1.0).mean()) if pcts is not None else 0.5
        except Exception:
            breadth = crowd = 0.5

        for code, row in df.iterrows():
            try:
                cd = str(code).split(".")[0].zfill(6)
                price = float(row[c_price])
                if price <= 0:
                    continue
                pct = float(row[c_pct]) if c_pct is not None else 0.0
                day_open = float(row[c_open]) if c_open is not None else price
                day_high = float(row[c_high]) if c_high is not None else price
                pre = float(row[c_pre]) if c_pre is not None else 0.0
                vr = float(row[c_vr]) if c_vr is not None else 1.0
                vw = float(row[c_vwap]) if c_vwap is not None else (day_high + price) / 2.0

                dc = dctx.asof(cd, day) if detect_patterns is not None and dctx.ok else {}
                vw10 = float(dc.get("vwap10") or 0.0)
                if vw10 <= 0 and self.vwap10_provider is not None:
                    vw10 = float(self.vwap10_provider(cd) or 0.0)

                pats = []
                traps = []
                grisk = 0.0
                if detect_patterns is not None and dc:
                    pats = detect_patterns(
                        price=price, day_open=day_open,
                        ma5=float(dc.get("ma5") or 0), ma10=float(dc.get("ma10") or 0),
                        ma20=float(dc.get("ma20") or 0), pct=pct,
                        ret_std20=float(dc.get("ret_std20") or 0), vol_ratio=vr,
                        rs5=float(dc.get("ret5d") or 0) - 0.0,
                        mkt_ret5=0.0, vwap10=vw10,
                        vol_dry=float(dc.get("vol_dry") or 1.0),
                        prev_pct=float(dc.get("prev_pct") or 0),
                    )
                    traps = detect_traps(price=price, prev_close=pre or (price / (1 + pct / 100.0)),
                                         day_open=day_open, day_high=day_high, vwap=vw,
                                         pct=pct, prev_pct=float(dc.get("prev_pct") or 0),
                                         vol_ratio=vr)
                    grisk, _ = cross_day_risk(
                        prev_pct=float(dc.get("prev_pct") or 0),
                        prev_close_pos=float(dc.get("prev_close_pos") or 0.5),
                        prev_upper_shadow=float(dc.get("prev_upper_shadow") or 0),
                        ret5d=float(dc.get("ret5d") or 0),
                        prev_amp=float(dc.get("prev_amp") or 0),
                    )

                consensus = 0.5 * breadth + 0.2 * crowd + 0.3 * 0.5
                self.stats["signals"] += 1
                prev_st = self.tracker.get(cd)
                prev_stage = prev_st.stage if prev_st is not None else ""
                st = self.tracker.update(
                    code=cd, ts=ts, price=price, pct=pct, vwap10=vw10, vwap=vw,
                    vol_ratio=vr, tier=0, rar=0.0, patterns=pats, day=day,
                    # 盘中无引擎打分，用"放量上行"作为首异动触发（>=1% 且量比>=1.5）
                    anomaly=bool(pats) or (pct >= 1.0 and vr >= 1.5),
                    traps=traps, gap_risk=grisk,
                    consensus=consensus, temp=0.0,
                )
                if st.stage == STAGE_ENTER and prev_stage != STAGE_ENTER:
                    self.stats["entries"] += 1
                    d = st.to_dict()
                    d["name"] = str(row[c_name]) if c_name is not None else ""
                    d["deploy_path"] = deploy_path(d)
                    self._alerts.append(d)
                n += 1
            except Exception:
                self.stats["errors"] += 1
                continue
        return n

    def make_df_callback(self, day: Optional[str] = None):
        """返回可直接传给 start_realtime_listener(data_callback=...) 的函数。"""

        def _cb(df, *args, **kwargs):
            try:
                self.on_df(df, day=day)
            except Exception:
                self.stats["errors"] += 1

        return _cb

    # -- 单条信号（交易中心）------------------------------------------------
    def on_signal(self, payload: Dict[str, Any], now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """处理一条上游信号。永不抛异常（IPC 线程安全优先）。"""
        try:
            if not isinstance(payload, dict):
                return None
            code = _code(payload)
            if not code:
                return None
            ts = float(payload.get("ts") or payload.get("time") or (now or time.time()))
            price = _num(payload, ("price", "last", "now", "lastp", "trade"), 0.0)
            pct = _num(payload, ("pct", "change_pct", "percent", "pct_chg", "涨幅"), 0.0)
            vol_ratio = _num(payload, ("vol_ratio", "volume_ratio", "量比"), 1.0)
            vwap = _num(payload, ("vwap", "avg_price", "均价"), 0.0)
            vwap10 = _num(payload, ("vwap10", "vwap_10d", "ma10dcum"), 0.0)
            if vwap10 <= 0 and self.vwap10_provider is not None:
                try:
                    vwap10 = float(self.vwap10_provider(code) or 0.0)
                except Exception:
                    vwap10 = 0.0
            tier = int(_num(payload, ("tier", "level", "grade"), 0.0))
            rar = _num(payload, ("rar", "score", "alpha"), 0.0)
            gap_risk = _num(payload, ("gap_risk", "cross_day_risk"), 0.0)
            traps = payload.get("traps") or []
            if isinstance(traps, str):
                traps = [traps]
            pats = _patterns(payload)

            self.stats["signals"] += 1
            prev = self.tracker.get(code)
            prev_stage = prev.stage if prev is not None else ""
            st = self.tracker.update(
                code=code, ts=ts, price=price or st_price(payload), pct=pct,
                vwap10=vwap10, vwap=vwap, vol_ratio=vol_ratio,
                tier=tier, rar=rar, patterns=pats,
                day=payload.get("trade_date") or time.strftime("%Y-%m-%d", time.localtime(ts)),
                anomaly=bool(pats) or tier >= 2,
                traps=list(traps), gap_risk=gap_risk,
            )
            d = st.to_dict()
            d["name"] = payload.get("name") or payload.get("stock_name") or ""
            d["deploy_path"] = deploy_path(d)
            if st.stage == STAGE_ENTER and prev_stage != STAGE_ENTER:
                self.stats["entries"] += 1
                self._alerts.append(d)
            if d["deploy_path"]:
                self.stats["deployable"] += 1
            return d
        except Exception:
            self.stats["errors"] += 1
            return None

    # -- 快照 ---------------------------------------------------------------
    def snapshot(self, limit: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        """当前状态：可下单 / 持仓（入局持有） / 走弱剔除。"""
        out = {"deploy": [], "holding": [], "watch": [], "evicted": []}
        for st in self.tracker.states():
            d = st.to_dict()
            d["deploy_path"] = deploy_path(d)
            if d["deploy_path"]:
                out["deploy"].append(d)
            elif st.stage in (STAGE_ENTER, STAGE_HOLD):
                out["holding"].append(d)
            elif st.stage == STAGE_EVICT:
                out["evicted"].append(d)
            else:
                out["watch"].append(d)
        for k in out:
            out[k].sort(key=lambda x: -float(x.get("persist") or 0.0))
            out[k] = out[k][:limit]
        return out

    def status_text(self) -> str:
        snap = self.snapshot()
        lines = [
            "赛马跟踪｜信号 {}｜入局 {}｜可下单 {}｜错误 {}".format(
                self.stats.get("signals", 0), self.stats.get("entries", 0),
                self.stats.get("deployable", 0), self.stats.get("errors", 0),
            )
        ]
        if snap["deploy"]:
            lines.append("可下单：")
            for d in snap["deploy"]:
                lines.append("  {} {} 涨{:+.1f}% 持续{} {}｜{}".format(
                    d["code"], d["enter_time"], float(d["enter_pct"] or 0),
                    d["persist"], d["deploy_path"], d["chain"][:40]))
        if snap["holding"]:
            lines.append("持仓：")
            for d in snap["holding"]:
                lines.append("  {} 入局{} 持续{} 回撤{:.1f}%".format(
                    d["code"], d["enter_time"], d["persist"], float(d["drawdown"] or 0)))
        return "\n".join(lines)


def st_price(payload: Dict[str, Any]) -> float:
    return _num(payload, ("open", "prev_close", "pre_close"), 0.0)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="赛马跟踪层 · 现有 IPC 信号订阅")
    ap.add_argument("--state", default=DEFAULT_STATE, help="状态落盘路径")
    ap.add_argument("--status", action="store_true", help="打印当前状态")
    ap.add_argument("--save", action="store_true", help="落盘当前状态")
    args = ap.parse_args(argv)

    bridge = FusionLiveBridge(state_path=args.state)
    if args.status:
        print(bridge.status_text())
    if args.save:
        print("saved:", bridge.save(), "->", args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
