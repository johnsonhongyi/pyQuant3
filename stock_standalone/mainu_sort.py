# -*- coding: utf-8 -*-
"""
MainU 极限性能排序算法模块
基于 64 状态的静态字典查找表 (LUT)，避免运行时的 split/join/正则与 GC 压力。
"""
import pandas as pd

def _compute_score(nums: list[int]) -> int:
    """
    计算 MainU 序列的排序分数（越大越优）。
    排序规则优先级：
    1. has_day1 (是否包含最近第一天) - 绝对优先
    2. start (连续起始天编号，越小越近越优)
    3. leading_run (首段连续阳新高天数，越多越优)
    4. total (总阳新高天数，越多越优)
    5. consec_pairs (总连续对数，连续越密越优)
    6. tail_proximity (尾部紧凑度，非连续元素越靠前越优)
    """
    if not nums:
        return 0
        
    # 1. 绝对优先：是否包含 day 1
    has_day1 = 1 if 1 in nums else 0
    
    # 2. 起始天编号
    start = nums[0]
    
    # 3. 首段连续长度
    leading_run = 1
    for j in range(1, len(nums)):
        if nums[j] == nums[j-1] + 1:
            leading_run += 1
        else:
            break
            
    # 4. 总匹配天数
    total = len(nums)
    
    # 5. 总连续对数
    consec_pairs = sum(1 for j in range(1, len(nums)) if nums[j] == nums[j-1] + 1)
    
    # 6. 尾部紧凑度（以 21 作为满分基准，21 = 1+2+3+4+5+6）
    remaining = nums[leading_run:]
    tail_proximity = 21 - sum(remaining)
    
    # 精密拼装复合分数
    score = (
        has_day1       * 10_000_000 +
        (7 - start)    *  1_000_000 +
        leading_run    *    100_000 +
        total          *     10_000 +
        consec_pairs   *      1_000 +
        tail_proximity *         10
    )
    return score

# 模块加载时，一次性预构建 64 状态查找表 (LUT)
_MAINU_STR_TO_SCORE = {}

for mask in range(64):
    nums = [i for i in range(1, 7) if (mask & (1 << (i - 1)))]
    if not nums:
        s = "0"
    else:
        s = ",".join(map(str, nums))
    _MAINU_STR_TO_SCORE[s] = _compute_score(nums)

# 补齐异常与默认回退的键值，确保极致鲁棒性
_MAINU_STR_TO_SCORE[""] = 0
_MAINU_STR_TO_SCORE["0"] = 0
_MAINU_STR_TO_SCORE["nan"] = 0
_MAINU_STR_TO_SCORE["None"] = 0

def mainu_sort_score(s: str) -> int:
    """
    单值 O(1) 静态查表打分 (供 Treeview 逐行排序使用)
    """
    if not s:
        return 0
    return _MAINU_STR_TO_SCORE.get(s.strip(), 0)

def compute_mainu_sort_column(series: pd.Series) -> pd.Series:
    """
    批量 O(N) 矢量化查表打分 (供 pandas DataFrame.sort_values 快速打分使用)
    """
    # 采用 C 底层哈希映射，完全杜绝运行时字符串拆分与 GC
    return series.fillna("0").astype(str).str.strip().map(_MAINU_STR_TO_SCORE).fillna(0).astype(int)
