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
from ats.fusion.ranking import score_entry
from ats.fusion.session_ctx import SessionContextStore, TEMP_HISTORY_PATH
from ats.fusion.lifecycle import MarketLifecycle

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
        session_store=None,
    ):
        self.tracker = tracker or RaceTracker(config or TrackConfig())
        self.state_path = state_path
        self.vwap10_provider = vwap10_provider
        self._last_save = 0.0
        self._alerts: List[Dict[str, Any]] = []
        self.stats = {"signals": 0, "entries": 0, "deployable": 0, "errors": 0}
        # 每日实盘后的上下文沉淀（收盘自动 + 显式 close_session）
        self.session_store = session_store if session_store is not None else SessionContextStore()
        self._closed_days: set = set()
        self._capital_hist: List[float] = []      # 每帧全市场成交额（万元），算资金冲锋号
        self._phase_path: List[Dict[str, Any]] = []
        self._last_phase = ""
        self._temp_cache: Dict[str, Any] = {"day": "", "mtime": 0.0, "records": []}
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

    # -- 每日实盘后的上下文沉淀 ---------------------------------------------
    def _temp_records(self, day: str) -> List[Dict[str, Any]]:
        """读主应用写的温度历史（logs/market_temp_history.json），按 mtime 缓存。

        取不到就返回空——close_day 会把 temp 记进 missing，不用猜测值冒充。
        """
        try:
            if not os.path.exists(TEMP_HISTORY_PATH):
                return []
            mt = os.path.getmtime(TEMP_HISTORY_PATH)
            if self._temp_cache.get("mtime") != mt:
                with open(TEMP_HISTORY_PATH, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                recs = [r for r in (payload.get("records") or []) if isinstance(r, dict)]
                self._temp_cache = {"day": str(payload.get("date") or ""),
                                    "mtime": mt, "records": recs}
            if self._temp_cache.get("day") != day:
                return []
            return list(self._temp_cache.get("records") or [])
        except Exception:
            return []

    def _update_phase(self, day: str, ts: float, breadth: float, capital_ratio: float) -> None:
        """用当帧宽度 + 资金量能推进战役阶段，记录阶段路径。

        局限（必须说清，否则 snapshot 会骗人）：实盘侧没有维护先锋名册，
        所以这里 survival 恒为 1.0、survival_n=0 —— **"先锋阵亡/按存活率退守"
        这两个分支在实盘阶段路径里不会出现**，只覆盖 冰点/反攻/攻城略地/量能退避。
        没有温度历史时整段跳过（不猜温度）。
        """
        recs = self._temp_records(day)
        if not recs:
            return
        temp = float(recs[-1].get("temp") or 0.0)
        try:
            st = MarketLifecycle().update(temp=temp, breadth=breadth, survival=1.0,
                                          survival_n=0, capital=capital_ratio)
        except Exception:
            return
        if st.phase and st.phase != self._last_phase:
            self._last_phase = st.phase
            self._phase_path.append({
                "time": time.strftime("%H:%M", time.localtime(int(ts))),
                "phase": st.phase, "note": st.note,
            })
            if len(self._phase_path) > 40:
                self._phase_path = self._phase_path[-40:]

    def close_session(self, day: str, frame: Any = None) -> Optional[Dict[str, Any]]:
        """收盘沉淀当日上下文。返回快照 dict；失败返回 None（绝不抛异常）。"""
        if day in self._closed_days:
            return None
        try:
            from ats.fusion.market_ctx import MarketHistory
            from ats.fusion.sector import get_theme_map
            from ats.fusion.session_ctx import ledger_summary

            capital_ratio = None
            if len(self._capital_hist) >= 10:
                w = 5
                recent = sum(self._capital_hist[-w:]) / w
                prev = sum(self._capital_hist[-2 * w:-w]) / w
                capital_ratio = recent / prev if prev > 0 else None
            ctx = self.session_store.close_day(
                day,
                temp_records=self._temp_records(day),
                frame=frame,
                tracker=self.tracker,
                mkt_hist=MarketHistory(),
                theme_map=get_theme_map() if frame is not None else None,
                phase_path=self._phase_path,
                capital_ratio=capital_ratio,
                # 快照里的 amount_wan 单位是万元；_capital_hist 存的是元，这里换算
                amount_wan=(self._capital_hist[-1] / 1e4 if self._capital_hist else None),
                ledger=ledger_summary(day),
            )
            self._closed_days.add(day)
            self.stats["sessions_closed"] = self.stats.get("sessions_closed", 0) + 1
            return ctx.to_dict() if ctx is not None else None
        except Exception:
            return None

    def handoff(self, day: str = "", n: int = 5) -> str:
        """次日盘前/回放用的上下文交接摘要（markdown）。"""
        try:
            return self.session_store.render_handoff(day or time.strftime("%Y-%m-%d"), n)
        except Exception:
            return ""

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
            from ats.fusion.trap import cross_day_risk, detect_traps

            # get_daily_context 是进程内单例；不要再每帧 new MarketHistory() 读一次盘
            # （它只被历史回放用，on_df 里构造出来也没人用，纯浪费一次 JSON 读盘）。
            dctx = get_daily_context()
        except Exception:
            detect_patterns = None

        # 市场宽度（用于趋同度）
        try:
            pcts = df[c_pct].astype(float) if c_pct is not None else None
            breadth = float((pcts > 0).mean()) if pcts is not None else 0.5
            crowd = float((pcts > 1.0).mean()) if pcts is not None else 0.5
        except Exception:
            breadth = crowd = 0.5

        # 全市场成交额：资金冲锋号的原料；行情 amount 单位是"元"，存快照时换算成万元。
        # 没有 amount 列就跳过，不编。
        try:
            c_amt = next((c for c in df.columns if str(c).lower() in ("amount", "amount_wan", "成交额")), None)
            if c_amt is not None:
                amt = float(df[c_amt].astype(float).sum())
                if amt == amt and amt > 0:
                    self._capital_hist.append(amt)
                    if len(self._capital_hist) > 21:
                        self._capital_hist = self._capital_hist[-21:]
        except Exception:
            pass

        # 战役阶段推进（有温度历史才算；没有就只记宽度/资金，不猜温度）
        try:
            cap_ratio = 1.0
            if len(self._capital_hist) >= 10:
                w = 5
                cap_ratio = (sum(self._capital_hist[-w:]) / w) / max(1e-9, sum(self._capital_hist[-2 * w:-w]) / w)
            self._update_phase(day, ts, breadth, cap_ratio)
        except Exception:
            pass

        # 列优先取成 numpy：iterrows 每行建一个 Series，全市场 5000+ 行要占掉 40% 耗时
        # （实测 0.91s → 0.55s）。取值口径与原来完全一致，只是不再逐行构造 Series。
        def col_arr(name):
            if name is None:
                return None
            try:
                arr = df[name].to_numpy()
                return arr.astype(float) if arr.dtype == object else arr
            except Exception:
                try:
                    return df[name].to_numpy(dtype=float)
                except Exception:
                    return None

        a_price = col_arr(c_price)
        a_pct = col_arr(c_pct)
        a_open = col_arr(c_open)
        a_high = col_arr(c_high)
        a_pre = col_arr(c_pre)
        a_vr = col_arr(c_vr)
        a_vwap = col_arr(c_vwap)
        names = [str(x) for x in (df[c_name].tolist() if c_name is not None else df.index)]

        def _f(arr, i, default):
            if arr is None:
                return default
            try:
                v = float(arr[i])
                return v if v == v else default   # NaN 走默认，不用 0 冒充有效值
            except Exception:
                return default

        for i in range(len(df)):
            try:
                cd = str(df.index[i]).split(".")[0].zfill(6)
                price = _f(a_price, i, 0.0)
                if price <= 0:
                    continue
                pct = _f(a_pct, i, 0.0)
                day_open = _f(a_open, i, price)
                day_high = _f(a_high, i, price)
                pre = _f(a_pre, i, 0.0)
                vr = _f(a_vr, i, 1.0)
                vw = _f(a_vwap, i, (day_high + price) / 2.0)

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
                    d["name"] = names[i] if c_name is not None else str(df.index[i])
                    d["deploy_path"] = deploy_path(d)
                    d["rank_score"] = score_entry(d)["score"]
                    self._alerts.append(d)
                n += 1
            except Exception:
                self.stats["errors"] += 1
                continue

        # -- 收盘沉淀：帧时间 >= 15:00 且当日未沉淀过 -> 固化当日上下文 --
        # 这就是"每日实盘后的数据上下文能力"：不依赖任何人记得去存，
        # 行情帧自己走到收盘点就把上下文交接给明天。
        try:
            lt = time.localtime(int(ts))
            if lt.tm_hour >= 15 and day not in self._closed_days:
                self.close_session(day, frame=df)
        except Exception:
            pass
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
            d["rank_score"] = score_entry(d)["score"]
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
            d["rank_score"] = score_entry(d)["score"]
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
