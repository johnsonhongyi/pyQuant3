#!/usr/local/bin/python
# -*- coding: utf-8 -*-

from datetime import datetime
import numpy as np
import talib as tl
from instock.core.strategy import enter

__author__ = 'myh '
__date__ = '2023/3/10 '


# 平台突破策略
# 1. 60日内某日收盘价>=60日均线>开盘价
# 2. 且【1】放量上涨 (enter.check_volume)
# 3. 且【1】之前时间，任意一天收盘价与60日均线偏离在-5%~20%之间。

def check(code_name, data, date=None, threshold=60):
    if data is None or data.empty:
        return False

    origin_data = data
    if date is None:
        end_date = code_name[0]
    else:
        end_date = str(date)[:10]

    if end_date is not None:
        # 如果末尾已经是指定日期以内，避免全表复制
        last_d = str(data['date'].iloc[-1])[:10]
        if last_d > end_date:
            mask = (data['date'] <= end_date)
            data = data.loc[mask]

    n_rows = len(data)
    if n_rows < threshold:
        return False

    close_all = np.ascontiguousarray(data['close'].values, dtype=np.float64)
    open_all = np.ascontiguousarray(data['open'].values, dtype=np.float64)
    vol_all = np.ascontiguousarray(data['volume'].values, dtype=np.float64)
    date_all = data['date'].values

    ma60_all = tl.MA(close_all, timeperiod=60)
    ma60_all[np.isnan(ma60_all)] = 0.0

    # 取最近 60 日窗口进行突破检测
    c60 = close_all[-threshold:]
    o60 = open_all[-threshold:]
    v60 = vol_all[-threshold:]
    d60 = date_all[-threshold:]
    m60 = ma60_all[-threshold:]

    # 向量化定位穿过 60 日线的候选突破日: open < ma60 <= close
    candidates = np.where((o60 < m60) & (m60 <= c60))[0]
    if len(candidates) == 0:
        return False

    for idx in candidates:
        # 1. 快速短路剪枝: check_volume 硬门槛成交额不低于2亿
        if c60[idx] * v60[idx] < 200000000.0:
            continue

        # 2. 快速短路剪枝: 突破日必须为阳线 (close > open)
        if c60[idx] <= o60[idx]:
            continue

        # 3. 前置平台偏离度校验: 突破日前所有交易日收盘价与 60 日均线偏离必须在 -5% 到 20% 之间
        if idx > 0:
            m_front = m60[:idx]
            valid_m = m_front > 0
            if np.any(valid_m):
                dev = (m_front[valid_m] - c60[:idx][valid_m]) / m_front[valid_m]
                if not np.all((-0.05 < dev) & (dev < 0.2)):
                    continue

        # 4. 仅在全部轻量前置条件满足时，调用完整的 enter.check_volume
        cand_date_str = str(d60[idx])[:10]
        try:
            d_obj = datetime.strptime(cand_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue

        if enter.check_volume(code_name, origin_data, date=d_obj, threshold=threshold):
            return True

    return False
