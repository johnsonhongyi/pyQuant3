# -*- coding: utf-8 -*-
"""ats/fusion/premarket.py — 盘前预处理宽表（tdx_last_df.h5）读取。

为什么用它：
    这份表是每天盘前算好的，385 列指标现成可用，比在回放里自己重算更稳，
    也避免"回放口径与实盘口径不一致"。本模块只取与融合层相关的少数列：

        ma5dcum / ma10dcum   累计均价（10 日 VWAP），用于判断"压力区"
        ma5d/ma10d/ma20d     日线均线
        supp_price / upper_price  SBC 支撑/压力
        vol_ratio            昨日量比
        category / hangye    板块与行业（后续做板块共振用）

只读，不写，不影响盘前流程。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

_COLS = [
    "lastp", "ma5d", "ma10d", "ma20d", "ma60d",
    "ma5dcum", "ma10dcum",
    "supp_price", "upper_price", "vol_ratio",
    "sig_launch", "sig_escape", "category", "hangye",
]

_CANDIDATES = (
    r"G:/tdx_last_df.h5",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "JSONData", "tdx_last_df.h5"),
)


class PremarketFeatures:
    """按 code 提供盘前指标；缺失时返回空字典，绝不抛异常。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or next((p for p in _CANDIDATES if os.path.exists(p)), None)
        self._data: Dict[str, Dict[str, float]] = {}
        self.ok = False
        if self.path:
            self._load()

    def _load(self) -> None:
        try:
            import pandas as pd

            df = pd.read_hdf(self.path, key="/low_d_120_y_all")
            keep = [c for c in _COLS if c in df.columns]
            df = df[keep]
            for code, row in df.iterrows():
                self._data[str(code).zfill(6)] = {
                    k: float(v) if isinstance(v, (int, float)) and v == v else 0.0
                    for k, v in row.items()
                    if k not in ("hangye",)
                }
                try:
                    self._data[str(code).zfill(6)]["hangye"] = float(row.get("hangye", 0) or 0)
                except Exception:
                    pass
            self.ok = bool(self._data)
        except Exception:
            self.ok = False

    def get(self, code: str) -> Dict[str, float]:
        return self._data.get(str(code).zfill(6), {})

    def vwap10(self, code: str) -> float:
        return float(self.get(code).get("ma10dcum", 0.0) or 0.0)

    def vwap5(self, code: str) -> float:
        return float(self.get(code).get("ma5dcum", 0.0) or 0.0)


_FEAT: Optional[PremarketFeatures] = None


def get_premarket() -> PremarketFeatures:
    global _FEAT
    if _FEAT is None:
        _FEAT = PremarketFeatures()
    return _FEAT
