# -*- coding: utf-8 -*-
"""ats/fusion/context.py — 跨日上下文（日线级）。

为什么必须补：
    原来的回放把每个交易日当成孤立的一天，看不到"昨天在哪、前几天怎么走、
    这是第几个板、离 20 日高点多远"。于是所有"启动"看起来都一样，
    分不清"第一根放量"和"第五根加速"。

数据源：`G:/tdx_all_df_300.h5` 的 `/all_300`（日线 OHLCV，实测 36 个交易日，
2026-08-27 ~ 2026-10-23，全市场）。只读，不参与实盘。
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from JSONData.tdx_hdf5_api import _HDF_GLOBAL_LOCK
    _H5_LOCK = _HDF_GLOBAL_LOCK
except Exception:
    _H5_LOCK = threading.RLock()

_DAILY_CANDIDATES = (
    r"G:/tdx_all_df_300.h5",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "JSONData", "tdx_all_df_300.h5"),
)


def _find_daily_path() -> Optional[str]:
    try:
        from JohnsonUtil import commonTips as cct  # type: ignore
        p = cct.get_run_path_tdx_Path("tdx_all_df_300")
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    for p in _DAILY_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


STRUCTURE_FIELDS = (
    "vwap3", "vwap5", "vwap10", "vwap_observed_days",
    "vwap_prev2_value", "vwap_prev2_volume", "vwap_prev4_value", "vwap_prev4_volume",
    "hi_10d", "lo_10d", "hi_pre1", "lo_pre1", "close_pre1",
    "amp_10d", "vwap_disp", "is_box10_ready",
    "vwap10_touch_count", "vwap10_hold_days",
    "close_over_vwap10", "close_over_vwap3", "vwap_multi_cycle_ready",
    "underwater_depth_pct", "is_structure_prejudged", "wash_quality",
    "is_underwater_weak", "prev_strong_vwap", "prev_pct",
    "vol_ratio_5d", "vol_dry",
)


class DailyContext:
    """按 (code, 交易日) 提供"截至昨日"的多日结构。

    刻意只用 **昨日及以前** 的数据，避免把当天收盘信息泄漏进当天决策。
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or _find_daily_path()
        self._by_code: Dict[str, Dict[str, np.ndarray]] = {}
        self._cache: Dict[tuple, Dict[str, float]] = {}
        self._box10_pool_cache: Dict[str, set[str]] = {}
        self._structure_pool_cache: Dict[str, set[str]] = {}
        self._pool_lock = threading.Lock()
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
        with _H5_LOCK:
            try:
                import pandas as pd

                df = pd.read_hdf(self.path, key="/all_300")
                # 该表每个 (code, date) 有重复行，必须去重，否则均线与多日收益全部错位
                df = df[~df.index.duplicated(keep="last")]
                codes = df.index.get_level_values(0).astype(str)
                dates = pd.to_datetime(df.index.get_level_values(1), errors="coerce")
                close = df["close"].to_numpy(dtype="float64")
                high = df["high"].to_numpy(dtype="float64")
                low = df["low"].to_numpy(dtype="float64")
                vol = df["vol"].to_numpy(dtype="float64")
                amount = df["amount"].to_numpy(dtype="float64") if "amount" in df.columns else np.zeros_like(vol)

                order = np.lexsort((dates.to_numpy(), codes.to_numpy()))
                codes_s = codes.to_numpy()[order]
                dates_s = dates.to_numpy()[order]
                close, high, low, vol = close[order], high[order], low[order], vol[order]
                amount = amount[order]

                uniq, starts = np.unique(codes_s, return_index=True)
                ends = np.append(starts[1:], len(codes_s))
                for code, s, e in zip(uniq, starts, ends):
                    self._by_code[str(code).zfill(6)] = {
                        "dates": dates_s[s:e],
                        "close": close[s:e],
                        "high": high[s:e],
                        "low": low[s:e],
                        "vol": vol[s:e],
                        "amount": amount[s:e],
                    }
                self.ok = bool(self._by_code)
            except Exception:
                self.ok = False

    def days(self) -> List[str]:
        seen = set()
        for v in self._by_code.values():
            for d in v["dates"]:
                try:
                    seen.add(np.datetime64(d, "D").astype(str))
                except Exception:
                    pass
        return sorted(seen)

    def asof(self, code: str, day: str) -> Dict[str, float]:
        """返回截至 day 前一日（不含 day）的结构指标；缺数据返回全 0。"""
        key = (code, day)
        if key in self._cache:
            return self._cache[key]

        out = {
            "ma5": 0.0, "ma10": 0.0, "ma20": 0.0,
            "ret5d": 0.0, "ret10d": 0.0, "ret20d": 0.0,
            "days_since_high": 0.0, "limit_up_streak": 0.0,
            "dist_ma20_pct": 0.0, "vol_ratio_5d": 1.0,
            "ret_std20": 0.0, "vol_mean20": 0.0, "vol_std20": 0.0,
            "vwap3": 0.0, "vwap5": 0.0, "vwap10": 0.0,
            "vol_ma5": 0.0, "vol_ma20": 0.0, "vol_dry": 1.0,
            "prev_pct": 0.0, "above_vwap10_days": 0,
            # 昨日形态：用于"前一日大涨、第二日急速杀跌"的风险预判
            "prev_amp": 0.0, "prev_close_pos": 0.5, "prev_upper_shadow": 0.0,
            # 10日VWAP结构预判指标 (尾盘/昨日确立，今日早盘验证)
            "vwap10_touch_count": 0, "vwap10_hold_days": 0,
            "close_over_vwap10": 0.0, "close_over_vwap3": 0.0, "vwap_multi_cycle_ready": 0.0, "underwater_depth_pct": 0.0, "is_structure_prejudged": 0.0, "prev_strong_vwap": 0.0, "wash_quality": 0.0, "is_underwater_weak": 0.0,
        }
        v = self._by_code.get(str(code).zfill(6))
        if v is None:
            self._cache[key] = out
            return out

        try:
            target = np.datetime64(day, "D")
            idx = np.searchsorted(v["dates"].astype("datetime64[D]"), target, side="left") - 1
        except Exception:
            idx = -1
        if idx < 0:
            self._cache[key] = out
            return out

        c = v["close"][: idx + 1]
        h = v["high"][: idx + 1]
        vol = v["vol"][: idx + 1]
        n = len(c)
        last = float(c[-1])

        for w, name in ((5, "ma5"), (10, "ma10"), (20, "ma20")):
            if n >= w:
                out[name] = float(np.mean(c[-w:]))
        for w, name in ((5, "ret5d"), (10, "ret10d"), (20, "ret20d")):
            if n > w and c[-w - 1] > 0:
                out[name] = (last / float(c[-w - 1]) - 1.0) * 100.0

        if n >= 20:
            win = h[-20:]
            hi = float(np.max(win))
            if hi > 0:
                # 注意：是"窗口内最后一天到最高点"的距离，不能用全局索引相减
                out["days_since_high"] = float(len(win) - 1 - int(np.argmax(win)))
        if out["ma20"] > 0:
            out["dist_ma20_pct"] = (last / out["ma20"] - 1.0) * 100.0

        # 连板：从最近一天往前数，单日涨幅 >= 9.7% 的连续天数
        streak = 0
        for i in range(n - 1, 0, -1):
            if c[i - 1] > 0 and (c[i] / c[i - 1] - 1.0) * 100.0 >= 9.7:
                streak += 1
            else:
                break
        out["limit_up_streak"] = float(streak)

        # 10 日 / 5 日 / 3 日累计均价（VWAP）与 10 日箱体标量 (V2 规范：量纲自校准 + 标量预计算)
        amt = v["amount"][: idx + 1]
        out["vwap_observed_days"] = float(sum(
            1 for a, volume in zip(amt[-5:], vol[-5:]) if a > 0 and volume > 0
        ))
        # 单日均价量纲自校准门禁 (防止 amount(千元)/vol(手) 引发 10x/100x 偏差)
        def _calibrated_vwap_day(a_val, v_val, h_val, l_val, c_val):
            if l_val <= 0 or h_val <= 0:
                return max(0.0, float(c_val))
            tp = (h_val + l_val + 2.0 * c_val) / 4.0
            if a_val <= 0 or v_val <= 0:
                return float(tp)
            raw = a_val / v_val
            if l_val * 0.95 <= raw <= h_val * 1.05:
                return float(raw)
            if l_val * 0.95 <= raw / 10.0 <= h_val * 1.05:
                return float(raw / 10.0)
            if l_val * 0.95 <= raw / 100.0 <= h_val * 1.05:
                return float(raw / 100.0)
            if l_val * 0.95 <= raw * 10.0 <= h_val * 1.05:
                return float(raw * 10.0)
            return float(tp)

        # 预计算最近 10 根单日校准均价与真实成交量
        win_10 = min(10, n)
        if win_10 >= 3:
            vwaps_10 = []
            vols_10 = []
            lows_arr = v["low"][: idx + 1]
            for k in range(n - win_10, n):
                ck = float(c[k])
                hk = float(h[k])
                lk = float(lows_arr[k])
                ak = float(amt[k])
                vk = float(vol[k])
                vw = _calibrated_vwap_day(ak, vk, hk, lk, ck)
                vwaps_10.append(vw)
                vols_10.append(max(1.0, vk))

            vwaps_arr = np.array(vwaps_10)
            vols_arr = np.array(vols_10)

            # 跨日锚点只含历史日；盘中再合并当日累计成交。
            for count in (2, 4):
                if win_10 >= count and all(
                    amt[k] > 0 and vol[k] > 0
                    and lows_arr[k] * 0.95 <= amt[k] / vol[k] <= h[k] * 1.05
                    for k in range(n - count, n)
                ):
                    out["vwap_prev{}_value".format(count)] = float(np.sum(vwaps_arr[-count:] * vols_arr[-count:]))
                    out["vwap_prev{}_volume".format(count)] = float(np.sum(vols_arr[-count:]))

            # 计算 V3, V5, V10
            sv3 = np.sum(vols_arr[-3:])
            v3 = float(np.sum(vwaps_arr[-3:] * vols_arr[-3:]) / sv3) if sv3 > 0 else float(vwaps_arr[-1])
            sv5 = np.sum(vols_arr[-min(5, win_10):])
            v5 = float(np.sum(vwaps_arr[-min(5, win_10):] * vols_arr[-min(5, win_10):]) / sv5) if sv5 > 0 else v3
            sv10 = np.sum(vols_arr)
            v10 = float(np.sum(vwaps_arr * vols_arr) / sv10) if sv10 > 0 else v5

            out["vwap3"] = round(v3, 3)
            out["vwap5"] = round(v5, 3)
            out["vwap10"] = round(v10, 3)

            # 10 日箱顶、箱底与昨日高点 (严格锚定截至昨日收盘，盘中绝不动态覆盖)
            hi_10d = float(np.max(h[-win_10:]))
            lo_10d = float(np.min(lows_arr[-win_10:]))
            hi_pre1 = float(h[-1])
            lo_pre1 = float(lows_arr[-1])
            close_pre1 = float(c[-1])

            out["hi_10d"] = round(hi_10d, 3)
            out["lo_10d"] = round(lo_10d, 3)
            out["hi_pre1"] = round(hi_pre1, 3)
            out["lo_pre1"] = round(lo_pre1, 3)
            out["close_pre1"] = round(close_pre1, 3)

            amp_10d = ((hi_10d - lo_10d) / lo_10d * 100.0) if lo_10d > 0 else 0.0
            # 近 6 日触底筑底平台振幅 (包容触底后蓄势企稳结构，如 300806 斯迪克)
            hi_6d = float(np.max(h[-min(6, win_10):]))
            lo_6d = float(np.min(lows_arr[-min(6, win_10):]))
            amp_6d = ((hi_6d - lo_6d) / lo_6d * 100.0) if lo_6d > 0 else amp_10d
            eff_amp = min(amp_10d, amp_6d)
            out["amp_10d"] = round(amp_10d, 2)
            out["amp_6d"] = round(amp_6d, 2)

            max_v = max(v3, v5, v10)
            min_v = min(v3, v5, v10)
            # V2 规范：分母对齐 v10 均价基准
            vwap_disp = ((max_v - min_v) / v10 * 100.0) if v10 > 0 else 0.0
            out["vwap_disp"] = round(vwap_disp, 2)

            # 分板块弹性门禁：主板 <= 18%, 20cm 双创 <= 24%
            c_str = str(code).zfill(6)
            is_growth = c_str.startswith(("300", "301", "688"))
            max_amp = 24.0 if is_growth else 18.0
            max_disp = 4.5 if is_growth else 3.0
            v3_v5_disp = (abs(v3 - v5) / v5 * 100.0) if v5 > 0 else 0.0
            is_box_ready = (
                (eff_amp <= max_amp)
                and (vwap_disp <= max_disp or v3_v5_disp <= 2.5)
                and (v3 >= v10 * 0.95 if is_growth else v3 >= v10 * 0.985)
                and (close_pre1 >= v10 * 0.95 if is_growth else close_pre1 >= v10 * 0.98)
            )
            out["is_box10_ready"] = 1.0 if is_box_ready else 0.0

            # -------------------------------------------------------------
            # 成交量与缩量特征提前计算 (因：成交量是一切，量在价先)
            # -------------------------------------------------------------
            if n >= 21:
                vma5 = float(np.mean(vol[-5:]))
                vma20 = float(np.mean(vol[-20:]))
                out["vol_ma5"] = vma5
                out["vol_ma20"] = vma20
                if vma20 > 0:
                    out["vol_dry"] = round(vma5 / vma20, 3)
            if n >= 6 and np.mean(vol[-6:-1]) > 0:
                out["vol_ratio_5d"] = float(vol[-1] / np.mean(vol[-6:-1]))

            # -------------------------------------------------------------
            # 10日VWAP结构机会预判模型 (因)：尾盘收盘站稳 10 日 VWAP 结构
            # -------------------------------------------------------------
            highs_win = h[-win_10:]
            closes_win = c[-win_10:]
            # 统计过去 10 日中，单日最高价触及或上冲 10 日均线 (High_k >= v10 * 0.995) 的天数 (主力反复试盘上冲)
            touch_mask = (highs_win >= v10 * 0.995)
            vwap10_touch_count = int(np.sum(touch_mask))
            hold_mask = (closes_win >= v10 * 0.995)
            vwap10_hold_days = int(np.sum(hold_mask))

            out["vwap10_touch_count"] = vwap10_touch_count
            out["vwap10_hold_days"] = vwap10_hold_days

            # 操盘手多周期 VWAP 核心：连 3 日 VWAP 都没站上，何况 10 日 VWAP！(光迅科技 002281 惨痛教训)
            close_over_vwap10 = bool(close_pre1 >= (v10 * 0.985 if is_growth else v10 * 0.992))
            close_over_vwap3 = bool(close_pre1 >= v3 * 0.995)
            vwap_multi_cycle_ready = bool(close_over_vwap3 and close_over_vwap10)
            underwater_depth_pct = round(((v10 - close_pre1) / v10 * 100.0), 2) if (v10 > 0 and close_pre1 < v10) else 0.0

            out["close_over_vwap10"] = 1.0 if close_over_vwap10 else 0.0
            out["close_over_vwap3"] = 1.0 if close_over_vwap3 else 0.0
            out["vwap_multi_cycle_ready"] = 1.0 if vwap_multi_cycle_ready else 0.0
            out["underwater_depth_pct"] = underwater_depth_pct

            # 综合判定结构预判资格：
            # 1. 昨收必须同时站上 3 日均价与 10 日均价 (连 3 日线都没站上的一律否决，杜绝深套)；
            # 2. 过去 10 日有反复上冲/测试 10 日均线结构 (touch_count >= 2)；
            # 3. 均线粘合收敛 (vwap_disp <= max_disp 或 v3_v5_disp <= 2.5)；
            # 4. 箱体振幅未失控破位 (eff_amp <= max_amp)；
            # 5. 昨收远离 10 日低点企稳 (close_pre1 >= lo_10d * 1.01)。
            is_struct_ready = bool(
                vwap_multi_cycle_ready
                and (vwap10_touch_count >= 2)
                and (vwap_disp <= max_disp or v3_v5_disp <= 2.5)
                and (eff_amp <= max_amp)
                and (close_pre1 >= lo_10d * 1.01 or win_10 < 5)
            )
            out["is_structure_prejudged"] = 1.0 if is_struct_ready else 0.0

            # 结构强度深化：反复大幅度震荡洗盘蓄势 (钧达股份 002865 典型特征)
            wash_quality = bool(is_struct_ready and vwap10_touch_count >= 3)
            out["wash_quality"] = 1.0 if wash_quality else 0.0

            # 走弱标的判定 (迈为股份、航天机电、拉普拉斯：昨收深处 10 日均线水下，反弹到 VWAP 压力区是止损点)
            is_underwater_weak = bool(v10 > 0 and close_pre1 < v10 * 0.96)
            out["is_underwater_weak"] = 1.0 if is_underwater_weak else 0.0
        else:
            out["vwap3"] = last
            out["vwap5"] = last
            out["vwap10"] = last
            out["hi_10d"] = last
            out["lo_10d"] = last
            out["hi_pre1"] = last
            out["lo_pre1"] = last
            out["close_pre1"] = last
            out["amp_10d"] = 0.0
            out["vwap_disp"] = 0.0
            out["is_box10_ready"] = 0.0
            out["vwap10_touch_count"] = 0
            out["vwap10_hold_days"] = 0
            out["close_over_vwap10"] = 0.0
            out["is_structure_prejudged"] = 0.0
            out["wash_quality"] = 0.0
            out["is_underwater_weak"] = 0.0

        # 昨日涨幅（用于"两阳加速"）
        if n >= 2 and c[-2] > 0:
            out["prev_pct"] = (last / float(c[-2]) - 1.0) * 100.0

        # 单日强势 VWAP 结构突破 (电科蓝天 688818 典型特征：昨日率先放量大涨站上 10 日 VWAP，带动全板块启动)
        prev_strong = False
        v10_v = float(out.get("vwap10") or 0.0)
        c_str = str(code).zfill(6)
        is_growth_code = c_str.startswith(("300", "301", "688"))
        min_lead_pct = 7.0 if is_growth_code else 5.0
        # 操盘手铁律：成交量是一切，总龙头昨日突破必须伴随放量倍量柱 (vol_ratio_5d >= 1.5)
        vol_r5 = float(out.get("vol_ratio_5d") or 1.0)
        if v10_v > 0 and out.get("prev_pct", 0.0) >= min_lead_pct and vol_r5 >= 1.5:
            if float(out.get("close_pre1") or 0.0) >= v10_v * 1.005:
                prev_strong = True
        out["prev_strong_vwap"] = 1.0 if prev_strong else 0.0

        # 昨日形态：振幅、收盘在日内位置、上影线占振幅比
        if n >= 1:
            ph, pl, pc = float(h[-1]), float(v["low"][idx]), float(c[-1])
            if pl > 0:
                out["prev_amp"] = (ph - pl) / pl * 100.0
            rng = ph - pl
            if rng > 0:
                out["prev_close_pos"] = max(0.0, min(1.0, (pc - pl) / rng))
                out["prev_upper_shadow"] = max(0.0, min(1.0, (ph - pc) / rng))

        # 连续多少个交易日收在 VWAP10 上方（多日验证："一天可以骗人，多日骗不了"）
        if n >= 11:
            cnt = 0
            for k in range(1, min(11, n) + 1):
                seg_v = float(np.sum(vol[-10 * k: len(vol) - 10 * (k - 1)])) if len(vol) >= 10 * k else 0.0
                seg_a = float(np.sum(amt[-10 * k: len(amt) - 10 * (k - 1)])) if len(amt) >= 10 * k else 0.0
                if seg_v <= 0 or seg_a <= 0:
                    break
                vw = seg_a / seg_v
                if c[-k] > vw:
                    cnt += 1
                else:
                    break
            out["above_vwap10_days"] = cnt

        # 缩量程度：5 日均量 / 20 日均量。越小说明越"干"，是放量的前提
        if n >= 21:
            vma5 = float(np.mean(vol[-5:]))
            vma20 = float(np.mean(vol[-20:]))
            out["vol_ma5"] = vma5
            out["vol_ma20"] = vma20
            if vma20 > 0:
                out["vol_dry"] = round(vma5 / vma20, 3)

        if n >= 6 and np.mean(vol[-6:-1]) > 0:
            out["vol_ratio_5d"] = float(vol[-1] / np.mean(vol[-6:-1]))

        # 自身历史波动：用于判断"超出自身走势"的异常
        if n >= 21:
            rets = np.diff(c[-21:]) / np.maximum(c[-21:-1], 1e-9) * 100.0
            out["ret_std20"] = float(np.std(rets)) if len(rets) else 0.0
            v20 = vol[-20:]
            out["vol_mean20"] = float(np.mean(v20))
            out["vol_std20"] = float(np.std(v20)) if len(v20) else 0.0

        self._cache[key] = out
        return out

    def box10_pool(self, day: str = "") -> set[str]:
        """返回截至指定交易日 (默认为当天) 全市场符合 10 日箱体洗盘蓄势 (is_box10_ready=1.0) 的代码集合。"""
        if not day:
            import time
            day = time.strftime("%Y-%m-%d")
        cache_key = f"box10_pool_{day}"
        if hasattr(self, "_box10_pool_cache") and cache_key in self._box10_pool_cache:
            return self._box10_pool_cache[cache_key]
        if not hasattr(self, "_pool_lock"):
            self._pool_lock = threading.Lock()
        with self._pool_lock:
            if not hasattr(self, "_box10_pool_cache"):
                self._box10_pool_cache = {}
            if cache_key in self._box10_pool_cache:
                return self._box10_pool_cache[cache_key]
            pool: set[str] = set()
            for cd in self._by_code.keys():
                m = self.asof(cd, day)
                if m.get("is_box10_ready") == 1.0:
                    pool.add(cd)
            self._box10_pool_cache[cache_key] = pool
            return pool

    def structure_pool(self, day: str = "") -> set[str]:
        """返回截至指定交易日 (默认为当天) 全市场符合 10 日 VWAP 结构机会预判 (is_structure_prejudged=1.0) 的代码集合。"""
        if not day:
            import time
            day = time.strftime("%Y-%m-%d")
        cache_key = f"structure_pool_{day}"
        if hasattr(self, "_structure_pool_cache") and cache_key in self._structure_pool_cache:
            return self._structure_pool_cache[cache_key]
        if not hasattr(self, "_pool_lock"):
            self._pool_lock = threading.Lock()
        with self._pool_lock:
            if not hasattr(self, "_structure_pool_cache"):
                self._structure_pool_cache = {}
            if cache_key in self._structure_pool_cache:
                return self._structure_pool_cache[cache_key]
            pool: set[str] = set()
            for cd in self._by_code.keys():
                m = self.asof(cd, day)
                if m.get("is_structure_prejudged") == 1.0:
                    pool.add(cd)
            self._structure_pool_cache[cache_key] = pool
            return pool


_CTX: Optional[DailyContext] = None
_CTX_LOCK = threading.Lock()


def get_daily_context() -> DailyContext:
    global _CTX
    if _CTX is None:
        with _CTX_LOCK:
            if _CTX is None:
                _CTX = DailyContext()
    return _CTX
