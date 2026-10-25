# -*- coding: utf-8 -*-
"""ats/fusion/session_ctx.py — 每日实盘后的上下文沉淀与自动交接。

用户原话（本轮架构纠正，三点合起来才是完整设计）：
    "需要更新的是每日实盘后的数据上下文能力，之前没有每日的实盘的上下文，
      每日自动持久化之前的上下文才可以更好的优化结构；
      数据底层基座就是在上下文缺失后使用上面的数据基座和 5 日分时数据构建最近的上下文；
      每日自动迭代交接才是正确的架构设计。"
    "何况还有各种的数据库信号、记录都是构建最新上下文的基础，
      最近的热点板块、轮动、资金情况、市场温度等等都是上下文一部分，
      每次自动更新迭代交接，才能反复验证有效性。"

所以关键**不是把分时数据叠得更长**（日线基座 + 最近 5 日分时已经够用），
而是每天收盘后把当日上下文固化成一份快照，次日自动接着用：

    1) 沉淀 close_day()：温度曲线、宽度、阶段路径、资金量能、热点板块/轮动、
       先锋存活、入局与可下单计数、饥饿度 → logs/fusion_state/session_ctx/<day>.json
    2) 重建 rebuild_day()：快照缺失时，用日线基座（DailyContext / tdx 日线宽表）
       + 5 日分时代理重建，并标注 source="rebuilt"；取不到就留空并记 missing，
       **绝不用猜测值冒充实测**。
    3) 交接 handoff()：给次日盘前/回放一份"最近 N 日上下文"摘要——
       连续冰点天数、饥饿度、上一阶段、热点板块、资金趋势。

落盘契约（与 tracker/market_ctx 一致）：
    - 单日一个文件 + tmp + os.replace 原子替换，异常恢复不留半截文件；
    - 只保留最近 keep_days 天，避免无限膨胀；
    - 所有数值缺失时写 None 并进 missing 列表，调用方必须能看出"这是缺的"。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "fusion_state", "session_ctx",
)
TEMP_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "market_temp_history.json",
)
KEEP_DAYS = 120


def _f(v: Any, default: Optional[float] = None) -> Optional[float]:
    """安全取浮点：None/NaN/不可解析都返回 default（不把脏数据当 0）。"""
    if v is None or v == "":
        return default
    try:
        x = float(v)
        return default if x != x else x
    except (TypeError, ValueError):
        return default


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None else round(float(x), nd)


@dataclass
class SessionContext:
    """一日上下文快照。字段分七组，缺哪组看 missing。"""

    day: str = ""
    source: str = "live"            # live=实盘沉淀 / rebuilt=缺失后重建
    saved_at: float = 0.0

    temp: Dict[str, Optional[float]] = field(default_factory=dict)     # open/min/max/close
    breadth: Dict[str, Optional[float]] = field(default_factory=dict)  # open/close
    updown: Dict[str, Optional[int]] = field(default_factory=dict)     # up/down（收盘）
    capital: Dict[str, Optional[float]] = field(default_factory=dict)  # amount_wan/ratio_close/min/max
    phase_path: List[Dict[str, Any]] = field(default_factory=list)     # [{time, phase, note}]
    themes: List[Dict[str, Any]] = field(default_factory=list)         # 热点板块 top N
    rotation: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)  # 相对上一日轮动
    vanguard: Dict[str, Optional[float]] = field(default_factory=dict)  # alive/total/survival
    signals: Dict[str, Optional[int]] = field(default_factory=dict)     # entries/deploy/evicted/t1
    ctx: Dict[str, Any] = field(default_factory=dict)                   # ice_days/hunger/label...
    missing: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionContext":
        known = {k: v for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def label(self) -> str:
        t = self.temp.get("close")
        b = self.breadth.get("close")
        cap = self.capital.get("ratio_close")
        ph = self.phase_path[-1]["phase"] if self.phase_path else "?"
        return "{}｜{}｜温度{}｜宽度{}｜量能{}｜热点{}".format(
            self.day, ph,
            "{:.0f}℃".format(t) if t is not None else "—",
            "{:.0%}".format(b) if b is not None else "—",
            "{:.2f}".format(cap) if cap is not None else "—",
            (self.themes[0].get("theme") if self.themes else "—") or "—",
        )


class SessionContextStore:
    """每日上下文的落盘、重建与交接。所有方法都不抛异常（调用方在实盘路径上）。"""

    def __init__(self, root: Optional[str] = None, keep_days: int = KEEP_DAYS):
        self.root = root or DEFAULT_ROOT
        self.keep_days = int(keep_days)
        self._cache: Dict[str, SessionContext] = {}

    # -- 路径 ---------------------------------------------------------------
    def path(self, day: str) -> str:
        return os.path.join(self.root, "{}.json".format(day))

    def days(self) -> List[str]:
        if not os.path.isdir(self.root):
            return []
        out = []
        for fn in os.listdir(self.root):
            if fn.endswith(".json") and len(fn) == 15:
                out.append(fn[:-5])
        return sorted(out)

    # -- 读写 ---------------------------------------------------------------
    def save(self, ctx: SessionContext) -> bool:
        """原子落盘；成功后才更新内存缓存。失败返回 False，不影响调用方。"""
        try:
            os.makedirs(self.root, exist_ok=True)
            ctx.saved_at = time.time()
            tmp = self.path(ctx.day) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(ctx.to_dict(), f, ensure_ascii=False)
            os.replace(tmp, self.path(ctx.day))
            self._cache[ctx.day] = ctx
            self._prune()
            return True
        except Exception:
            return False

    # -- 多写入方合并 --------------------------------------------------------
    # 同一天的上下文可能由三方先后写：回放沉淀（带温度/存活率/账本，最富）、
    # live_bridge 收盘沉淀（带帧/主题/资金）、UI 定时巡检（最薄，只有 phase_path）。
    # 直接覆盖会让"最薄的写"抹掉"最富的写"，所以按组合并：新值非空才覆盖，
    # 空值保留旧值；source 优先保留 live（实测胜过重建）。
    _DICT_FIELDS = ("temp", "breadth", "updown", "capital", "vanguard", "signals", "ctx")
    _LIST_FIELDS = ("phase_path", "themes")
    # missing  key -> 能把它填上的字段（支持点号子键）。合并后按这个表自愈：
    # 薄写入方留下的缺失标记，不能因为"曾经缺过"就永久粘在快照上。
    # 注意 amount 与 capital_ratio 同属 capital，但子键不同——不能一个补齐另一个就算了。
    _MISSING_FILLED_BY = {
        "temp": "temp.close",
        "breadth": "breadth.close",
        "capital_ratio": "capital.ratio_close",
        "amount": "capital.amount_wan",
        "phase_path": "phase_path",
        "themes": "themes",
        "tracker": "signals.states",
        "vanguard_survival": "vanguard.alive",
        "mkt_hist": "ctx.ice_days",
    }

    @staticmethod
    def _filled(ctx: SessionContext, path: str) -> bool:
        cur: Any = ctx
        for part in path.split("."):
            cur = getattr(cur, part, None) if not isinstance(cur, dict) else cur.get(part)
            if cur in (None, "", [], {}):
                return False
        return True

    def _merge(self, base: Optional[SessionContext], new: SessionContext) -> SessionContext:
        if base is None or base.day != new.day:
            return new
        for k in self._DICT_FIELDS:
            b = getattr(base, k) or {}
            n = getattr(new, k) or {}
            filled = {kk: vv for kk, vv in n.items() if vv not in (None, {}, [], "")}
            if filled or b:
                setattr(new, k, {**b, **filled})
        for k in self._LIST_FIELDS:
            if not getattr(new, k) and getattr(base, k):
                setattr(new, k, getattr(base, k))
        if not new.rotation and base.rotation:
            new.rotation = base.rotation
        if base.source == "live" and new.source != "live":
            new.source = "live"
        # 自愈：字段现在有值的，从 missing 里去掉（否则一次薄写会永久留下缺失标记）
        healed = {k for k, p in self._MISSING_FILLED_BY.items() if self._filled(new, p)}
        new.missing = sorted((set(base.missing) | set(new.missing)) - healed)
        return new

    def load(self, day: str) -> Optional[SessionContext]:
        if day in self._cache:
            return self._cache[day]
        p = self.path(day)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                ctx = SessionContext.from_dict(json.load(f))
            self._cache[day] = ctx
            return ctx
        except Exception:
            return None

    def recent(self, n: int = 5, before: str = "") -> List[SessionContext]:
        days = self.days()
        if before:
            days = [d for d in days if d < before]
        out = []
        for d in days[-max(1, int(n)):]:
            c = self.load(d)
            if c is not None:
                out.append(c)
        return out

    def _prune(self) -> None:
        try:
            days = self.days()
            for d in days[:-self.keep_days] if self.keep_days > 0 else []:
                os.remove(self.path(d))
                self._cache.pop(d, None)
        except Exception:
            pass

    # -- 沉淀 ---------------------------------------------------------------
    def close_day(
        self,
        day: str,
        *,
        temp_records: Optional[List[Dict[str, Any]]] = None,
        frame: Any = None,
        tracker: Any = None,
        mkt_hist: Any = None,
        theme_map: Any = None,
        phase_path: Optional[List[Dict[str, Any]]] = None,
        capital_ratio: Optional[float] = None,
        amount_wan: Optional[float] = None,
        vanguard_survival: Optional[float] = None,
        vanguard_n: int = 0,
        ledger: Optional[Dict[str, Any]] = None,
    ) -> SessionContext:
        """把一日上下文固化成快照。任何输入缺失都记 missing，不编数。"""
        ctx = SessionContext(day=day, source="live")
        miss: List[str] = []

        # 1) 温度：优先实盘温度历史（主应用写入），退回日线上下文，再退回帧宽度代理
        temps = [r for r in (temp_records or []) if _f(r.get("temp")) is not None]
        if temps:
            vals = [_f(r.get("temp")) for r in temps]
            ctx.temp = {
                "open": _r(vals[0]), "close": _r(vals[-1]),
                "min": _r(min(vals)), "max": _r(max(vals)),
            }
            ups = [_f(r.get("up")) for r in temps if _f(r.get("up")) is not None]
            dns = [_f(r.get("down")) for r in temps if _f(r.get("down")) is not None]
            if ups and dns:
                ctx.updown = {"up": int(ups[-1]), "down": int(dns[-1])}
                tot = max(1.0, ups[-1] + dns[-1])
                ctx.breadth = {"open": _r(ups[0] / max(1.0, ups[0] + dns[0]), 3),
                               "close": _r(ups[-1] / tot, 3)}

        if mkt_hist is not None:
            try:
                dc = mkt_hist.context_for(day)
                if dc is not None:
                    ctx.ctx = {
                        "ice_days": int(getattr(dc, "ice_days", 0) or 0),
                        "cold_days": int(getattr(dc, "cold_days", 0) or 0),
                        "hot_days": int(getattr(dc, "hot_days", 0) or 0),
                        "hunger": _r(getattr(dc, "hunger", 1.0), 3),
                        "label": str(getattr(dc, "label", lambda: "")() or ""),
                    }
                    if not ctx.breadth.get("close") and getattr(dc, "breadth", 0) > 0:
                        ctx.breadth = {"close": _r(dc.breadth, 3)}
                    if not ctx.temp.get("close") and getattr(dc, "temp_close", 0) > 0:
                        ctx.temp = {"close": _r(dc.temp_close, 1)}
            except Exception:
                miss.append("mkt_hist")

        # 温度/宽度都取不到才记 missing（日线基座补上来的不算缺）
        if not ctx.temp.get("close"):
            miss.append("temp")
        if not ctx.breadth.get("close"):
            miss.append("breadth")

        # 2) 资金：近5根/前5根量能比 + 当日成交额
        # 注意：capital_ratio 恰为 1.0 一律按"没有数据"处理——多个写入方（UI 巡检）
        # 会用 1.0 当占位符，而真实量能比恰好等于 1.000 的概率可忽略；
        # 把它当实测值会覆盖掉回放算出的真实比值。
        cr = _f(capital_ratio)
        if cr is not None and abs(cr - 1.0) < 1e-9:
            cr = None
        if cr is not None:
            ctx.capital["ratio_close"] = _r(cr, 3)
        else:
            miss.append("capital_ratio")
        if _f(amount_wan) is not None:
            ctx.capital["amount_wan"] = _r(amount_wan, 1)
        else:
            miss.append("amount")

        # 3) 阶段路径（实盘由 lifecycle 采集，回放由 DayReplay 采集）
        ctx.phase_path = list(phase_path or [])
        if not ctx.phase_path:
            miss.append("phase_path")

        # 4) 热点板块 / 轮动：帧或主题图谱 + 涨幅
        try:
            if frame is not None and theme_map is not None:
                ctx.themes = self._theme_heat(frame, theme_map)
            if not ctx.themes:
                miss.append("themes")
        except Exception:
            miss.append("themes")

        # 5) 先锋存活 + 信号计数
        # vanguard 只放**真实**先锋存活率（回放由 VanguardWatch 算；实盘侧没有维护名册，
        # 所以留空并记 missing，绝不用"入局事件数"冒充存活率）。
        if _f(vanguard_survival) is not None:
            ctx.vanguard = {"alive": _r(vanguard_survival, 3), "total": float(vanguard_n)}
        else:
            miss.append("vanguard_survival")
        if tracker is not None:
            try:
                sts = tracker.states()
                ctx.signals = {
                    "entries": int(sum(1 for s in sts if getattr(s, "stage", "") == "入局")),
                    "holding": int(sum(1 for s in sts if getattr(s, "stage", "") in ("入局", "持有"))),
                    "evicted": int(sum(1 for s in sts if getattr(s, "stage", "") == "剔除")),
                    "states": len(sts),
                }
            except Exception:
                miss.append("tracker")
        else:
            miss.append("tracker")

        if ledger:
            ctx.signals.update({k: v for k, v in ledger.items() if isinstance(v, int)})

        # 6) 轮动：与上一快照比较热点板块进出
        prev = None
        for d in reversed(self.days()):
            if d < day:
                prev = self.load(d)
                break
        if prev is not None and prev.themes and ctx.themes:
            old = {t.get("theme") for t in prev.themes}
            new = {t.get("theme") for t in ctx.themes}
            ctx.rotation = {
                "new_in": [t for t in ctx.themes if t.get("theme") in (new - old)],
                "dropped": [t for t in prev.themes if t.get("theme") in (old - new)],
            }

        ctx.missing = miss
        ctx = self._merge(self.load(day), ctx)
        self.save(ctx)
        return ctx

    @staticmethod
    def _theme_heat(frame: Any, theme_map: Any, top: int = 8) -> List[Dict[str, Any]]:
        """从一帧全量行情算热点板块（成员平均涨幅 + 上涨占比）。"""
        import numpy as np

        codes = [str(c).split(".")[0].zfill(6) for c in frame.index]
        if "percent" in [str(c).lower() for c in frame.columns]:
            col = next(c for c in frame.columns if str(c).lower() == "percent")
            pcts = frame[col].astype(float).to_numpy()
        else:
            pcts = np.zeros(len(codes))
        buckets: Dict[str, List[float]] = {}
        for c, p in zip(codes, pcts):
            if p != p:
                continue
            for t in (theme_map.get(c) or []):
                buckets.setdefault(t, []).append(float(p))
        rows = []
        for t, vals in buckets.items():
            if len(vals) < 5:
                continue
            rows.append({
                "theme": t, "n": len(vals),
                "avg_pct": _r(sum(vals) / len(vals)),
                "breadth": _r(sum(1 for v in vals if v > 0) / len(vals), 3),
            })
        rows.sort(key=lambda r: -(r["avg_pct"] or 0.0))
        return rows[:top]

    # -- 重建 ---------------------------------------------------------------
    def rebuild_day(self, day: str) -> Optional[SessionContext]:
        """快照缺失时，用日线基座 + 5 日分时重建最近的上下文。

        返回 None 表示连基座都没有（那就老实没有，不编）。
        """
        from ats.fusion.market_ctx import MarketHistory

        ctx = SessionContext(day=day, source="rebuilt")
        miss: List[str] = []
        try:
            mh = MarketHistory()
            if len(mh.days) < 5:
                mh.seed_from_daily()
            dc = mh.context_for(day)
        except Exception:
            dc = None
        if dc is None:
            return None
        ctx.ctx = {
            "ice_days": int(getattr(dc, "ice_days", 0) or 0),
            "cold_days": int(getattr(dc, "cold_days", 0) or 0),
            "hot_days": int(getattr(dc, "hot_days", 0) or 0),
            "hunger": _r(getattr(dc, "hunger", 1.0), 3),
            "label": str(getattr(dc, "label", lambda: "")() or ""),
        }
        if getattr(dc, "breadth", 0) > 0:
            ctx.breadth = {"close": _r(dc.breadth, 3)}
        else:
            miss.append("breadth")
        if getattr(dc, "temp_close", 0) > 0:
            ctx.temp = {"close": _r(dc.temp_close, 1)}
        else:
            miss.append("temp")
        ctx.capital["ratio_close"] = None
        miss.append("capital_ratio")
        miss.append("phase_path")
        miss.append("themes")
        miss.append("tracker")
        ctx.missing = miss
        self.save(ctx)
        return ctx

    def ensure(self, day: str) -> Optional[SessionContext]:
        """取某日上下文：有快照用快照，没有就重建。"""
        c = self.load(day)
        if c is not None:
            return c
        return self.rebuild_day(day)

    # -- 交接 ---------------------------------------------------------------
    def handoff(self, day: str, n: int = 5) -> Dict[str, Any]:
        """给次日/回放的"最近 N 日上下文"摘要。"""
        recent = self.recent(n, before=day)
        if not recent:
            return {"day": day, "days": 0, "note": "无历史上下文（首日或已清理）"}
        last = recent[-1]
        ices = [int((c.ctx or {}).get("ice_days") or 0) for c in recent]
        themes: Dict[str, int] = {}
        for c in recent:
            for t in (c.themes or [])[:3]:
                themes[t.get("theme") or ""] = themes.get(t.get("theme") or "", 0) + 1
        hot = sorted(themes.items(), key=lambda x: -x[1])[:5]
        return {
            "day": day,
            "days": len(recent),
            "from": recent[0].day,
            "to": last.day,
            "ice_days": int((last.ctx or {}).get("ice_days") or 0),
            "ice_days_max": max(ices) if ices else 0,
            "hunger": (last.ctx or {}).get("hunger"),
            "last_phase": (last.phase_path[-1]["phase"] if last.phase_path else None),
            "last_breadth": last.breadth.get("close"),
            "last_temp": last.temp.get("close"),
            "last_capital": last.capital.get("ratio_close"),
            "hot_themes": [{"theme": k, "days": v} for k, v in hot if k],
            "sources": {c.day: c.source for c in recent},
        }

    def render_handoff(self, day: str, n: int = 5) -> str:
        h = self.handoff(day, n)
        if not h.get("days"):
            return "## 上下文交接 {}｜{}\n".format(day, h.get("note", ""))
        lines = ["## 上下文交接 {}（近 {} 日，{}→{}）".format(day, h["days"], h["from"], h["to"]), ""]
        lines.append("- 连续冰点 **{} 日**（区间最大 {}）｜饥饿度 {}｜上一阶段 **{}**".format(
            h["ice_days"], h["ice_days_max"], h.get("hunger"), h.get("last_phase") or "—"))
        lines.append("- 上一日：宽度 {}｜温度 {}｜量能 {}".format(
            "{:.0%}".format(h["last_breadth"]) if h.get("last_breadth") is not None else "—",
            "{:.0f}℃".format(h["last_temp"]) if h.get("last_temp") is not None else "—",
            "{:.2f}".format(h["last_capital"]) if h.get("last_capital") is not None else "—"))
        if h.get("hot_themes"):
            lines.append("- 反复出现的板块：{}".format(
                "、".join("{}（{}日）".format(t["theme"], t["days"]) for t in h["hot_themes"])))
        rebuilt = [d for d, s in (h.get("sources") or {}).items() if s == "rebuilt"]
        if rebuilt:
            lines.append("- 其中重建（非实盘沉淀）：{}".format("、".join(rebuilt)))
        lines.append("")
        return "\n".join(lines)


def default_store() -> SessionContextStore:
    return SessionContextStore()


def ledger_summary(day: str, root: Optional[str] = None) -> Dict[str, int]:
    """读主应用的信号账本（logs/signal_snapshots/signal_ledger_latest.json.gz），
    汇总成当日信号计数——"各种数据库信号、记录都是构建最新上下文的基础"。

    账本日期与目标日不一致（它是"最新一天"的快照）时返回空，不张冠李戴。
    """
    import gzip

    base = root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "logs", "signal_snapshots",
    )
    path = os.path.join(base, "signal_ledger_latest.json.gz")
    if not os.path.exists(path):
        return {}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    if str(payload.get("date") or "") != str(day):
        return {}
    out: Dict[str, int] = {}
    total = payload.get("total_signals")
    if isinstance(total, int):
        out["ledger_total"] = total
    for k, v in (payload.get("tier_counts") or {}).items():
        if isinstance(v, int):
            out["ledger_" + str(k)] = v
    entries = payload.get("entries") or []
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        from collections import Counter

        for key, cnt in Counter(str(e.get("action") or "?") for e in entries).most_common(8):
            out["ledger_act_" + key] = int(cnt)
    return out
