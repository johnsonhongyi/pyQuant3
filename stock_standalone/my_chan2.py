# coding=utf-8
import pandas as pd
import numpy as np
import datetime
from JohnsonUtil import LoggerFactory
log = LoggerFactory.log
import numba as nb
import time

@nb.jit(nopython=True)
def fast_chan_inclusion(high, low, vol, amount):
    """
    Numba accelerated Chan inclusion processing
    """
    n = len(high)
    if n == 0:
        return (np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0), 
                np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))

    res_high = np.zeros(n)
    res_low = np.zeros(n)
    res_vol = np.zeros(n)
    res_amount = np.zeros(n)
    res_idx = np.zeros(n, dtype=np.int64)
    res_end_idx = np.zeros(n, dtype=np.int64)

    res_high[0] = high[0]
    res_low[0] = low[0]
    res_vol[0] = vol[0]
    res_amount[0] = amount[0]
    res_idx[0] = 0
    res_end_idx[0] = 0
    
    count = 1
    up_direction = True 

    for i in range(1, n):
        cur_h, cur_l = high[i], low[i]
        last_h, last_l = res_high[count-1], res_low[count-1]
        
        if count >= 2:
            prev_h = res_high[count-2]
            if last_h > prev_h: up_direction = True
            elif last_h < prev_h: up_direction = False
        
        if (cur_h >= last_h and cur_l <= last_l) or (cur_h <= last_h and cur_l >= last_l):
            if up_direction:
                res_high[count-1] = max(cur_h, last_h)
                res_low[count-1] = max(cur_l, last_l)
            else:
                res_high[count-1] = min(cur_h, last_h)
                res_low[count-1] = min(cur_l, last_l)
            res_vol[count-1] += vol[i]
            res_amount[count-1] += amount[i]
            res_end_idx[count-1] = i
        else:
            res_high[count] = cur_h
            res_low[count] = cur_l
            res_vol[count] = vol[i]
            res_amount[count] = amount[i]
            res_idx[count] = i
            res_end_idx[count] = i
            count += 1
            
    return (res_high[:count], res_low[:count], res_vol[:count], res_amount[:count], 
            res_idx[:count], res_end_idx[:count])

def parse2ChanK(k_data, k_values=None, chan_kdf=True):
    if not chan_kdf:
        if 'enddate' not in k_data.columns:
            k_data = k_data.copy()
            k_data['enddate'] = k_data.index
        return k_data
    h, l, v, a, s_idx, e_idx = fast_chan_inclusion(
        k_data['high'].values, k_data['low'].values, 
        k_data['vol'].values, k_data['amount'].values
    )
    chanK = pd.DataFrame({
        'high': h, 'low': l, 'vol': v, 'amount': a,
        'enddate': k_data.index[e_idx],
        'open': k_data['open'].values[s_idx],
        'close': k_data['close'].values[e_idx]
    }, index=k_data.index[s_idx])
    return chanK

@nb.njit
def fast_identify_fractograms(high, low, close):
    """
    Numba accelerated fractogram identification
    """
    n = len(high)
    fen_types = np.zeros(n, dtype=np.int8)
    fen_indices = np.zeros(n, dtype=np.int64)
    count = 0

    for i in range(1, n - 1):
        if high[i] > high[i-1] and high[i] > high[i+1]:
            if count > 0 and fen_types[count-1] == 1:
                if high[i] > high[fen_indices[count-1]]:
                    fen_indices[count-1] = i
            else:
                fen_types[count] = 1
                fen_indices[count] = i
                count += 1
        elif low[i] < low[i-1] and low[i] < low[i+1]:
            if count > 0 and fen_types[count-1] == -1:
                if low[i] < low[fen_indices[count-1]]:
                    fen_indices[count-1] = i
            else:
                fen_types[count] = -1
                fen_indices[count] = i
                count += 1
    
    return fen_types[:count], fen_indices[:count]

def parse2ChanFen(chanK, recursion=False):
    f_types, f_idx = fast_identify_fractograms(
        chanK['high'].values, chanK['low'].values, chanK['close'].values
    )
    return list(f_types), list(f_idx)

@nb.njit
def fast_identify_strokes(f_types, f_indices, high, low, least_khl_num):
    """
    Numba accelerated stroke identification
    """
    n_fen = len(f_types)
    bi_idx = np.zeros(n_fen, dtype=np.int64)
    count = 0
    if n_fen < 2: return bi_idx[:0], 0
    
    i = 0
    while i < n_fen:
        curr_f_idx = f_indices[i]
        curr_f_type = f_types[i]
        if count == 0:
            bi_idx[count] = curr_f_idx
            count += 1
            i += 1
            continue
            
        last_f_idx = bi_idx[count-1]
        # Type of the point we're looking for (opposite of the last point)
        # Assuming f_types are [1, -1, 1, -1...]
        target_indices = np.where(f_indices == last_f_idx)[0]
        if len(target_indices) == 0: break
        last_f_type = f_types[target_indices[0]]
        target_type = -last_f_type
        
        found = False
        for j in range(i, n_fen):
            if f_types[j] == target_type and (f_indices[j] - last_f_idx) >= least_khl_num:
                bi_idx[count] = f_indices[j]
                count += 1
                i = j + 1
                found = True
                break
        if not found: break
            
    first_bi_type = 0
    if count >= 2:
        first_bi_type = 1 if high[bi_idx[1]] > high[bi_idx[0]] else -1
    return bi_idx[:count], first_bi_type

def parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=3):
    f_types = np.array(fenTypes, dtype=np.int8)
    f_idx = np.array(fenIdx, dtype=np.int64)
    b_idx, f_type = fast_identify_strokes(
        f_types, f_idx, chanK['high'].values, chanK['low'].values, least_khl_num
    )
    return list(b_idx), f_type

def parse2Xianduan(biIdx, chanK, least_windows=3):
    """
    Improved Segment (Xianduan) identification using local trend detection.
    Sequentially identifies segments to ensure no early trends are missed.
    """
    xdIdx = []
    if len(biIdx) < 4: return xdIdx, 0, []

    # 1. 寻找初始线段 (由前几笔确定方向)
    curr_i = 0
    # 记录端点索引
    xdIdx.append(biIdx[0])
    
    # 简单趋势追踪
    n_bi = len(biIdx)
    last_xd_val = chanK['high'].iloc[biIdx[0]] if chanK['high'].iloc[biIdx[0]] > chanK['low'].iloc[biIdx[1]] else chanK['low'].iloc[biIdx[0]]
    
    # 初始方向判定 (看前3笔)
    h0, l0 = chanK['high'].iloc[biIdx[0]], chanK['low'].iloc[biIdx[0]]
    h1, l1 = chanK['high'].iloc[biIdx[1]], chanK['low'].iloc[biIdx[1]]
    
    xdType = 1 if h1 > h0 else -1
    
    curr_ptr = 0
    while curr_ptr < n_bi - 2:
        found_turn = False
        # 寻找转折：如果当前是向上段，寻找一个显著的顶，且其后有一笔不创新高
        if xdType == 1:
            # 寻找更高点
            best_h = -1e10
            best_idx = -1
            for j in range(curr_ptr + 1, n_bi):
                val = chanK['high'].iloc[biIdx[j]]
                if val >= best_h:
                    best_h = val
                    best_idx = biIdx[j]
                    # 如果后续笔转为向下且跌破了某个关键支撑(这里简化为距离)
                    if j - curr_ptr >= least_windows:
                        # 检查是否有回撤
                        if j + 1 < n_bi and chanK['low'].iloc[biIdx[j+1]] < chanK['low'].iloc[biIdx[j-1]]:
                            found_turn = True
                            xdIdx.append(best_idx)
                            curr_ptr = j
                            xdType = -1
                            break
            if not found_turn: break
        else:
            # 寻找更低点
            best_l = 1e10
            best_idx = -1
            for j in range(curr_ptr + 1, n_bi):
                val = chanK['low'].iloc[biIdx[j]]
                if val <= best_l:
                    best_l = val
                    best_idx = biIdx[j]
                    if j - curr_ptr >= least_windows:
                        if j + 1 < n_bi and chanK['high'].iloc[biIdx[j+1]] > chanK['high'].iloc[biIdx[j-1]]:
                            found_turn = True
                            xdIdx.append(best_idx)
                            curr_ptr = j
                            xdType = 1
                            break
            if not found_turn: break

    # 兜底：如果最后一段没闭合，添加最后一个笔点作为结束
    if xdIdx[-1] != biIdx[-1]:
        xdIdx.append(biIdx[-1])

    # 构造 xfenTypes: 根据端点交替
    xfenTypes = []
    if len(xdIdx) > 0:
        # 第一个点的类型由第一段方向决定
        # 如果第一段向上(xdType在循环中被反转了，所以要看初值)，起点是底(-1)
        # 简化：直接根据高低值判定
        for i in range(len(xdIdx)):
            idx = xdIdx[i]
            if i + 1 < len(xdIdx):
                 curr_t = 1 if chanK['high'].iloc[xdIdx[i+1]] < chanK['high'].iloc[idx] else -1
                 xfenTypes.append(curr_t)
            else:
                 xfenTypes.append(-xfenTypes[-1] if len(xfenTypes)>0 else -1)
                 
    # 确定整体 xdType (第一段的方向)
    final_xdType = 1 if len(xdIdx) >= 2 and chanK['high'].iloc[xdIdx[1]] > chanK['high'].iloc[xdIdx[0]] else -1
    
    return xdIdx, final_xdType, xfenTypes

@nb.njit
def fast_identify_central_areas(bi_idx, high, low):
    """
    Numba accelerated central area identification
    """
    n_bi = len(bi_idx)
    zs_starts = np.zeros(n_bi, dtype=np.int64)
    zs_ends = np.zeros(n_bi, dtype=np.int64)
    zs_zd = np.zeros(n_bi)
    zs_zg = np.zeros(n_bi)
    count = 0
    if n_bi < 4: return zs_starts[:0], zs_ends[:0], zs_zd[:0], zs_zg[:0]

    i = 0
    while i <= n_bi - 4:
        l1 = min(low[bi_idx[i]], low[bi_idx[i+1]])
        h1 = max(high[bi_idx[i]], high[bi_idx[i+1]])
        l2 = min(low[bi_idx[i+1]], low[bi_idx[i+2]])
        h2 = max(high[bi_idx[i+1]], high[bi_idx[i+2]])
        l3 = min(low[bi_idx[i+2]], low[bi_idx[i+3]])
        h3 = max(high[bi_idx[i+2]], high[bi_idx[i+3]])
        zd = max(l1, l2, l3)
        zg = min(h1, h2, h3)
        if zd < zg:
            zs_starts[count] = bi_idx[i]
            zs_ends[count] = bi_idx[i+3]
            zs_zd[count] = zd
            zs_zg[count] = zg
            j = i + 4
            while j < n_bi:
                lj = min(low[bi_idx[j-1]], low[bi_idx[j]])
                hj = max(high[bi_idx[j-1]], high[bi_idx[j]])
                if max(zd, lj) < min(zg, hj):
                    zs_ends[count] = bi_idx[j]
                    j += 1
                else: break
            count += 1
            i = j - 1
        else: i += 1
    return zs_starts[:count], zs_ends[:count], zs_zd[:count], zs_zg[:count]

def get_chan_analysis(k_data, least_khl_num=3, chanK_flag=True):
    chanK = parse2ChanK(k_data, chan_kdf=chanK_flag)
    fenTypes, fenIdx = parse2ChanFen(chanK)
    biIdx, frsBiType = parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
    xdIdxs, xdType, xfenTypes = parse2Xianduan(biIdx, chanK, least_windows=2)
    b_idx_np = np.array(biIdx, dtype=np.int64)
    zs_s, zs_e, zs_zd, zs_zg = fast_identify_central_areas(b_idx_np, chanK['high'].values, chanK['low'].values)
    zs_list = []
    for i in range(len(zs_s)):
        zs_list.append({'start': zs_s[i], 'end': zs_e[i], 'zd': zs_zd[i], 'zg': zs_zg[i]})
    results = {
        'biIdx': biIdx, 'frsBiType': frsBiType, 'zs_list': zs_list,
        'fenIdx': fenIdx, 'fenTypes': fenTypes, 
        'xdIdxs': xdIdxs, 'xdType': xdType, 'xfenTypes': xfenTypes
    }
    return chanK, results

def get_chan_analysis_fast(k_data, least_khl_num=3, chanK_flag=True):
    if not chanK_flag: return get_chan_analysis(k_data, least_khl_num, False)
    h, l, v, a, s_idx, e_idx = fast_chan_inclusion(
        k_data['high'].values, k_data['low'].values, 
        k_data['vol'].values, k_data['amount'].values
    )
    c = k_data['close'].values[e_idx]
    f_types, f_indices = fast_identify_fractograms(h, l, c)
    bi_idx, first_bi_type = fast_identify_strokes(f_types, f_indices, h, l, least_khl_num)
    zs_s, zs_e, zs_zd, zs_zg = fast_identify_central_areas(bi_idx, h, l)
    chanK = pd.DataFrame({
        'high': h, 'low': l, 'vol': v, 'amount': a,
        'enddate': k_data.index[e_idx],
        'open': k_data['open'].values[s_idx],
        'close': c
    }, index=k_data.index[s_idx])
    xd_idxs, xd_type, xfen_types = parse2Xianduan(list(bi_idx), chanK)
    zs_list = []
    for i in range(len(zs_s)):
        zs_list.append({'start': zs_s[i], 'end': zs_e[i], 'zd': zs_zd[i], 'zg': zs_zg[i]})
    results = {
        'biIdx': list(bi_idx), 'frsBiType': first_bi_type, 'zs_list': zs_list,
        'fenIdx': list(f_indices), 'fenTypes': list(f_types),
        'xdIdxs': list(xd_idxs), 'xdType': xd_type, 'xfenTypes': xfen_types
    }
    return chanK, results

class ChanAnalyzer:
    def __init__(self, least_khl_num=3, chanK_flag=True, fast_mode=True):
        self.least_khl_num = least_khl_num
        self.chanK_flag = chanK_flag
        self.fast_mode = fast_mode
    def analyze(self, k_data):
        if self.fast_mode: return get_chan_analysis_fast(k_data, self.least_khl_num, self.chanK_flag)
        return get_chan_analysis(k_data, self.least_khl_num, self.chanK_flag)
