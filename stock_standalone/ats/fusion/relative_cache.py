# -*- coding: utf-8 -*-
"""ats/fusion/relative_cache.py — 5 日相对强度（rs5）批量缓存。

数据源：`tdx_all_df_300.h5` 的 `/all_300`（index=(code, date)，含 close），
路径**不写死**，统一走 `JohnsonUtil.commonTips`（cct）的 ramdisk 解析：
`cct.get_run_path_tdx_Path("tdx_all_df_300")` → `<RamDisk>\tdx_all_df_300.h5`，
ramdisk 不可用时自动退到 app_root 同目录。

一次读全市场日线收盘，向量化算出每只票的 5 日涨幅与全池中位涨幅，
供融合层 relative 轴使用。**不发起任何网络请求**，也不依赖逐票 K 线缓存。

口径：
    ret5   = 最新收盘 / 5 个交易日前收盘 - 1
    mkt_ret5 = 全池 ret5 的中位数（大盘基准）
    rs5    = ret5 - mkt_ret5
若文件里今天还没有收盘行（盘中未更新），则自然退化为"截至上一交易日"的 5 日强度，
这是稳定口径，不会引入未收盘的伪数据。
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 数据源候选（文件名 → HDF5 key）。按顺序取第一个存在的。
SOURCE_CANDIDATES = (
    ("tdx_all_df_300", "/all_300"),
    ("tdx_all_df_900", "/all_900"),
)


def _resolve_candidates() -> List[Tuple[str, str]]:
    """通过 cct 解析每个候选文件的实际路径（ramdisk 优先），只保留存在的。"""
    out: List[Tuple[str, str]] = []
    try:
        from JohnsonUtil import commonTips as cct  # type: ignore
    except Exception as exc:
        logger.debug("[fusion] cct 不可用，rs5 数据源解析失败: %s", exc)
        return out

    for name, key in SOURCE_CANDIDATES:
        path = ""
        try:
            path = cct.get_run_path_tdx_Path(name) or ""
        except Exception as exc:
            logger.debug("[fusion] 解析 %s 路径失败: %s", name, exc)
        if not path:
            try:
                ramdisk = cct.get_ramdisk_dir()
                if ramdisk:
                    path = os.path.join(ramdisk, "{}.h5".format(name))
            except Exception:
                path = ""
        if path and os.path.exists(path):
            out.append((path, key))
    return out


def _pick_source(path: Optional[str], key: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if path and os.path.exists(path):
        return path, (key or "/all_300")
    candidates = _resolve_candidates()
    if candidates:
        return candidates[0]
    return None, None


def load_rs5_map(
    path: Optional[str] = None,
    key: Optional[str] = None,
    lookback: int = 5,
) -> Tuple[Dict[str, float], float]:
    """返回 ({code: rs5}, mkt_ret5)。任何异常都返回空结果，绝不阻塞调用方。"""
    src, h5key = _pick_source(path, key)
    if not src:
        return {}, 0.0
    try:
        import pandas as pd

        with pd.HDFStore(src, "r") as store:
            keys = list(store.keys())
            use_key = h5key if h5key in keys else (keys[0] if keys else None)
            if not use_key:
                return {}, 0.0
            df = store.select(use_key, columns=["close"])
        if df is None or df.empty or "close" not in df.columns:
            return {}, 0.0

        # (code, date) 偶有重复行（多次抓取叠加），保留最后一条再透视
        if df.index.has_duplicates:
            df = df[~df.index.duplicated(keep="last")]
        wide = df["close"].unstack(level=0).sort_index()
        if len(wide) < lookback + 1:
            return {}, 0.0
        last = wide.iloc[-1]
        base = wide.iloc[-lookback - 1]
        ret5 = (last / base - 1.0) * 100.0
        ret5 = ret5.replace([float("inf"), float("-inf")], pd.NA).dropna()
        ret5 = ret5[(base > 0) & (last > 0)]
        if ret5.empty:
            return {}, 0.0

        mkt = float(ret5.median())
        rs_map = {
            str(code).split(".")[0].zfill(6): round(float(v) - mkt, 3)
            for code, v in ret5.items()
        }
        logger.debug("[fusion] rs5 源=%s key=%s 覆盖=%d 中位=%+.2f%%", src, use_key, len(rs_map), mkt)
        return rs_map, round(mkt, 3)
    except Exception as exc:
        logger.debug("[fusion] rs5 批量缓存加载失败: %s", exc)
        return {}, 0.0
