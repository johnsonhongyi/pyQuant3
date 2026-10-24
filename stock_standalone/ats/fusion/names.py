# -*- coding: utf-8 -*-
"""ats/fusion/names.py — 本地股票名称表（code <-> name）。

数据源：`datacsv/stock_name_cache.json.gz`（5849 只，覆盖全市场）。
之前用 trading_signals.db 去查名称，只覆盖 7/50——那是查错了源，不是数据缺失。
"""

from __future__ import annotations

import gzip
import json
import os
from typing import Dict, List, Optional

_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "datacsv", "stock_name_cache.json.gz"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "datacsv", "stock_name_cache.json"),
)

_CACHE: Optional[Dict[str, str]] = None


def load_names() -> Dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    for p in _CANDIDATES:
        if not os.path.exists(p):
            continue
        try:
            if p.endswith(".gz"):
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
            _CACHE = {str(k).zfill(6): str(v) for k, v in data.items()}
            return _CACHE
        except Exception:
            continue
    _CACHE = {}
    return _CACHE


def code_of(name: str) -> Optional[str]:
    name = str(name or "").strip()
    for c, n in load_names().items():
        if n == name:
            return c
    return None


def name_of(code: str) -> str:
    return load_names().get(str(code).zfill(6), "")


def codes_for(names: List[str]) -> Dict[str, str]:
    out = {}
    for n in names:
        c = code_of(n)
        if c:
            out[n] = c
    return out
