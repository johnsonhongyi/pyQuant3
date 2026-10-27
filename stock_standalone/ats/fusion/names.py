# -*- coding: utf-8 -*-
"""ats/fusion/names.py — 本地股票名称表（code <-> name）。

数据源：`datacsv/stock_name_cache.json.gz`（5849 只，覆盖全市场）。
支持全渠道自愈兜底与多环境候选路径探测（开发模式、PyInstaller/Nuitka 打包、独立工作目录）。
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from typing import Dict, List, Optional


def _get_candidate_paths() -> List[str]:
    """多环境自适应收集 stock_name_cache 候选路径（兼容源码、打包环境与独立工作目录）。"""
    roots: List[str] = []
    # 1. 尝试从 sys_utils.get_app_root 获取权威程序物理根目录
    try:
        from sys_utils import get_app_root
        ar = get_app_root()
        if ar and ar not in roots:
            roots.append(ar)
    except Exception:
        pass

    # 2. 源码开发环境目录（基于 __file__ 向上三级）
    src_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if src_root and src_root not in roots:
        roots.append(src_root)

    # 3. 打包环境（可执行文件物理所在目录）
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable or ""))
        if exe_dir and exe_dir not in roots:
            roots.append(exe_dir)

    # 4. 当前工作目录
    cwd = os.getcwd()
    if cwd and cwd not in roots:
        roots.append(cwd)

    candidates: List[str] = []
    for r in roots:
        candidates.append(os.path.join(r, "datacsv", "stock_name_cache.json.gz"))
        candidates.append(os.path.join(r, "datacsv", "stock_name_cache.json"))
    return candidates


_CANDIDATES = tuple(_get_candidate_paths())

_CACHE: Optional[Dict[str, str]] = None


def load_names() -> Dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    _CACHE = {}
    for p in _get_candidate_paths():
        if not os.path.exists(p):
            continue
        try:
            if p.endswith(".gz"):
                with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
            else:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    k_str = str(k).strip().split(".")[0].zfill(6)
                    v_str = str(v).strip()
                    if v_str and not v_str.isdigit() and v_str != k_str:
                        _CACHE[k_str] = v_str
            if len(_CACHE) > 500:
                return _CACHE
        except Exception:
            continue
    return _CACHE


def code_of(name: str) -> Optional[str]:
    name = str(name or "").strip()
    for c, n in load_names().items():
        if n == name:
            return c
    return None


def name_of(code: str) -> str:
    cd = str(code or "").strip().split(".")[0]
    clean_code = "".join(c for c in cd if c.isdigit()).zfill(6) if any(c.isdigit() for c in cd) else cd
    if not clean_code:
        return ""
    # 1. 优先从内存字典获取
    nm = load_names().get(clean_code, "")
    if nm and nm != clean_code and not nm.isdigit() and not nm.startswith("个股_") and nm != "未知":
        return nm

    # 2. 二级兜底：调起全系统权威解析器 sys_utils.resolve_stock_name
    try:
        from sys_utils import resolve_stock_name
        res_nm = resolve_stock_name(clean_code, cached_only=True)
        if res_nm and res_nm != clean_code and not res_nm.isdigit() and not res_nm.startswith("个股_") and res_nm != "未知":
            if _CACHE is not None:
                _CACHE[clean_code] = res_nm
            return res_nm
    except Exception:
        pass

    return nm or ""


def codes_for(names: List[str]) -> Dict[str, str]:
    out = {}
    for n in names:
        c = code_of(n)
        if c:
            out[n] = c
    return out
