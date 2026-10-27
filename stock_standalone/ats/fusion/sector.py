# -*- coding: utf-8 -*-
"""ats/fusion/sector.py — 赛道（板块）层。

用户的原话：**"个股分类是蓄势，板块才是赛道。赛马了半天忘记赛道了。"**

所以这里把"赛道"做成一等公民：
    - 行业取自盘前宽表 `hangye`（三级行业名，取二级作为赛道，避免过碎）；
    - 每根 bar 用全池数据算每个赛道的**实时强度**（成员平均涨幅、上涨占比）；
    - 再把赛道强度映射回个股：`sector_pct / sector_rank / sector_breadth / sector_resonance`。

只读，纯计算，不依赖外部接口。
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

_CANDIDATES = (
    r"G:/tdx_last_df.h5",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "JSONData", "tdx_last_df.h5"),
)


def _find_last_df_path() -> Optional[str]:
    try:
        from JohnsonUtil import commonTips as cct  # type: ignore
        p = cct.get_run_path_tdx_Path("tdx_last_df")
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    return next((p for p in _CANDIDATES if os.path.exists(p)), None)


def _level2(name: str) -> str:
    """'计算机-IT服务-IT服务Ⅲ' -> '计算机-IT服务'；异常值归到 '未分类'。"""
    s = str(name or "").strip()
    if not s or s in ("0", "--", "nan", "None"):
        return "未分类"
    parts = s.split("-")
    if len(parts) >= 2:
        return parts[0] + "-" + parts[1]
    return s


class SectorMap:
    """code -> 赛道，以及赛道成员索引。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _find_last_df_path()
        self.code2sector: Dict[str, str] = {}
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
        with _H5_LOCK:
            try:
                import pandas as pd

                df = pd.read_hdf(self.path, key="/low_d_120_y_all", columns=["hangye"])
                for code, row in df.iterrows():
                    self.code2sector[str(code).zfill(6)] = _level2(row.get("hangye"))
                self.ok = bool(self.code2sector)
            except Exception:
                self.ok = False

    def get(self, code: str) -> str:
        return self.code2sector.get(str(code).zfill(6), "未分类")

    def build_index(self, codes: List[str]) -> Dict[str, np.ndarray]:
        """返回 {赛道: 成员在 codes 中的下标数组}。"""
        buckets: Dict[str, List[int]] = {}
        for i, c in enumerate(codes):
            buckets.setdefault(self.get(c), []).append(i)
        return {k: np.asarray(v, dtype="int64") for k, v in buckets.items()}


def sector_strength(
    pct: np.ndarray,
    valid: np.ndarray,
    index: Dict[str, np.ndarray],
) -> Dict[str, float]:
    """单个时点的赛道强度：成员平均涨幅。"""
    out: Dict[str, float] = {}
    for name, idx in index.items():
        m = valid[idx]
        if m.sum() < 3:
            continue
        out[name] = float(np.nanmean(pct[idx][m]))
    return out


class ThemeMap:
    """code -> 概念标签（本地 category 字段，388 个标签，含机器人概念/人形机器人等）。

    本地概念是"第一手"的：盘中就能算强度，不必等外部热榜更新；
    外部热榜（同花顺/东财/淘股吧）作为"马已经跑起来"的确认，见 load_external_heat。
    """

    # 过于宽泛的标签不参与"赛道"判断（几乎全市场都有）
    BROAD = {"深股通", "沪股通", "国企改革", "融资融券", "转融券标的", "MSCI概念", "标普道琼斯A股"}

    def __init__(self, path: Optional[str] = None):
        self.path = path or _find_last_df_path()
        self.code2tags: Dict[str, List[str]] = {}
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
        with _H5_LOCK:
            try:
                import pandas as pd

                df = pd.read_hdf(self.path, key="/low_d_120_y_all", columns=["category"])
                for code, row in df.iterrows():
                    raw = str(row.get("category") or "")
                    tags = [
                        t.strip() for t in raw.split(";")
                        if t.strip() and t.strip() not in self.BROAD and t.strip() not in ("0", "--", "nan", "None")
                    ]
                    if tags:
                        self.code2tags[str(code).zfill(6)] = tags
                self.ok = bool(self.code2tags)
            except Exception:
                self.ok = False

    def get(self, code: str) -> List[str]:
        return self.code2tags.get(str(code).zfill(6), [])

    def build_index(self, codes: List[str], min_members: int = 10) -> Dict[str, np.ndarray]:
        buckets: Dict[str, List[int]] = {}
        for i, c in enumerate(codes):
            for t in self.get(c):
                buckets.setdefault(t, []).append(i)
        return {k: np.asarray(v, dtype="int64") for k, v in buckets.items() if len(v) >= min_members}


_TMAP: Optional[ThemeMap] = None


def get_theme_map() -> ThemeMap:
    global _TMAP
    if _TMAP is None:
        _TMAP = ThemeMap()
    return _TMAP


def load_external_heat(day: str, root: Optional[str] = None) -> Dict[str, int]:
    """读取外部热榜（同花顺/东财/淘股吧）当日报表，格式：
        {"themes": [{"name": "机器人", "rank": 1, "pct": 5.2}, ...]}
    文件不存在则返回空——不联网、不阻塞。
    """
    import json

    base = root or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs", "heat_boards")
    path = os.path.join(base, "{}.json".format(day))
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for item in (data.get("themes") or []):
            name = str(item.get("name") or "").strip()
            if name:
                out[name] = int(item.get("rank") or 99)
        return out
    except Exception:
        return {}


def verify_heat(
    local_theme_rank: Dict[str, float],
    external_heat: Dict[str, int],
    top_n: int = 20,
) -> Dict[str, Any]:
    """热榜对答案：本地概念强度排名 vs 外部热榜排名。

    热榜不参与打分——它是"收盘后核对答案"用的：
        hit     我们本地排前 N、热榜也排前 N  -> 本地挖掘有效
        missed  热榜前 N，我们没进前 N        -> 本地漏了（板块不够细/启动更早）
        noise   我们前 N，热榜没有            -> 本地多报（可能是伪热点）
    """
    if not local_theme_rank or not external_heat:
        return {"ok": False, "reason": "缺少本地或外部热榜数据"}

    local_sorted = [k for k, _ in sorted(local_theme_rank.items(), key=lambda x: -x[1])][:top_n]
    heat_sorted = [k for k, _ in sorted(external_heat.items(), key=lambda x: x[1])][:top_n]
    lset, hset = set(local_sorted), set(heat_sorted)
    return {
        "ok": True,
        "hit": sorted(lset & hset),
        "missed": sorted(hset - lset),
        "noise": sorted(lset - hset),
        "recall": round(len(lset & hset) / max(1, len(hset)), 3),
    }


_SMAP: Optional[SectorMap] = None


def get_sector_map() -> SectorMap:
    global _SMAP
    if _SMAP is None:
        _SMAP = SectorMap()
    return _SMAP
