# -*- coding: utf-8 -*-
"""ats/fusion/config.py — 融合层配置加载。

设计要点：
    - 缺文件、坏 JSON、字段缺失都必须退化为默认值，绝不抛异常打断主循环；
    - 权重/阈值/温度矩阵/先手表全部外置，便于按历史分位重标定（见设计文档 §11）；
    - 配置按 mtime 缓存，热改不需要重启。
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "shadow_only": True,
    "log_dir": "logs/fusion_shadow",
    "max_records_per_day": 200000,
    "sample_interval_s": 3.0,
    "weights": {"position": 0.30, "support": 0.25, "intent": 0.25, "regime": 0.20},
    "tier_cuts": {"l4": 82.0, "l3": 72.0, "l2": 62.0, "l1": 50.0},
    "max_single_size_pct": 35.0,
    "veto": {"stale_seconds": 20.0, "max_bias_pct": 7.0, "min_amount_wan": 3000.0},
    "penalty": {
        "chase_start_pct": 3.0,
        "chase_per_pct": 6.0,
        "chase_cap": 30.0,
        "overheat_penalty": 20.0,
        "crowd_vol_ratio": 4.5,
        "crowd_penalty": 10.0,
        "illiquid_penalty": 15.0,
        "cap": 60.0,
    },
    "temp_matrix": {
        "ICE_COLD": [2, 0.50],
        "COLD_WEAK": [3, 0.70],
        "WARMING": [4, 1.00],
        "OVERHEATED": [2, 0.60],
        "COOLING_EBB": [1, 0.30],
    },
    "age_table": [[10.0, 4, 1.00], [25.0, 3, 0.85], [45.0, 2, 0.70], [70.0, 1, 0.50]],
    "portfolio": {"max_l4": 2, "max_total_pct": 85.0},
    "state_temp_map": {
        "PANIC": 25.0,
        "COOLDOWN": 30.0,
        "NEUTRAL": 50.0,
        "REPAIR": 55.0,
        "REVERSAL": 58.0,
        "FOMO": 68.0,
    },
}

_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, Any]] = None
_CACHE_KEY: Any = None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def default_config_path() -> str:
    try:
        from sys_utils import get_app_root  # type: ignore

        root = get_app_root()
    except Exception:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "config", "fusion_ladder.json")


def load_config(path: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
    """读取配置；任何异常都退化为 DEFAULTS。"""
    path = path or default_config_path()

    try:
        mtime = os.path.getmtime(path)
        size = os.path.getsize(path)
    except OSError:
        return copy.deepcopy(DEFAULTS)

    key = (path, mtime, size)
    if use_cache:
        with _LOCK:
            if _CACHE is not None and _CACHE_KEY == key:
                return copy.deepcopy(_CACHE)

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("config root is not a dict")
        merged = _deep_merge(DEFAULTS, raw)
    except Exception as exc:
        logger.warning("[fusion] 配置加载失败，使用默认值: %s", exc)
        return copy.deepcopy(DEFAULTS)

    with _LOCK:
        globals()["_CACHE"] = copy.deepcopy(merged)
        globals()["_CACHE_KEY"] = key
    return merged


def is_enabled(cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get("enabled", True))


def engine_params(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """抽出引擎关心的字段，避免把 IO 配置传进纯计算层。"""
    cfg = cfg or load_config()
    cuts = cfg.get("tier_cuts") or {}
    return {
        "weights": cfg.get("weights") or {},
        "tier_cuts": cuts,
        "veto": cfg.get("veto") or {},
        "penalty": cfg.get("penalty") or {},
        "temp_matrix": cfg.get("temp_matrix") or {},
        "age_table": cfg.get("age_table") or [],
        "max_single_size_pct": cfg.get("max_single_size_pct", 35.0),
    }
