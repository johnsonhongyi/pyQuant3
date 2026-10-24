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
from typing import Dict, List, Optional

import numpy as np

_CANDIDATES = (
    r"G:/tdx_last_df.h5",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "JSONData", "tdx_last_df.h5"),
)


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
        self.path = path or next((p for p in _CANDIDATES if os.path.exists(p)), None)
        self.code2sector: Dict[str, str] = {}
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
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


_SMAP: Optional[SectorMap] = None


def get_sector_map() -> SectorMap:
    global _SMAP
    if _SMAP is None:
        _SMAP = SectorMap()
    return _SMAP
