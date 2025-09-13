import numpy as np
import pandas as pd
import talib
import random
from datetime import datetime, timedelta
import sys
sys.path.append("../../")
# print(sys.path)
import JSONData.tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct
# 假设 GlobalValues 是一个用于存储全局数据的类
class GlobalValues:
    def getkey(self, key):
        if key == 'percdf':
            return pd.DataFrame({
                'code': ['920445'],
                'lasth1d': [10.0],
                'lasth2d': [11.0],
                'lasth3d_test': [12.0],
                'lasth4d': [13.0],
                'lasth5d': [14.0],
                'lasth6d': [15.0],
                'ma51d': [10.5]
            }).set_index('code')
        return None



import numpy as np

def func_compute_percd2021(open, close, high, low, last_open, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, high4, max5, hmax, lastdu4, code, idate=None):
    """
    根据一系列股票交易行为计算综合得分。

    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_open (float): 昨日开盘价 (虽然未使用，但参数保留以匹配顺序)
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        hmax (float): 历史最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
        idate (str): 日期 (可选)

    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）
    if close == high:
        init_c += 5.0
        if vol_ratio > 2: # 配合放量涨停给更高分
            init_c += 5.0

    # 最低价大于前日最低价
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
        
    # 成交量温和上涨
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破
    if hmax is not None and high >= hmax:
        init_c += 20.0 # 突破历史高点给最高分

    # 每日高开高走，无价格重叠 (low > last_high)
    if low > last_high:
        init_c += 20.0 # 强势跳空，权重最高
        if close > open:
            init_c += 5.0
            
    # 开盘价就是最低价 (open == low) 加分
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0 # 低开高走且开盘在 ma5 之上，强启动
        elif close > open:
            init_c += 8.0 # 只要是开盘即最低的上涨，都加分
        if vol_ratio > 2: # 配合放量再加分
            init_c += 5.0
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 8.0
    
    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）
    if low < last_low:
        init_c -= 3.0
        
    # 放量下跌（下跌且成交量大于昨日）
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0 # 权重更高
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0

    # 高开低走 (open > close) 减分
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
            
    # 开盘价就是最高价 (open == high) 减分
    if open == high:
        init_c -= 10.0 # 当天走势疲弱，最高分时减分
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 原始代码中关于 lastdu4 的逻辑 (保持不变)
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c



def func_compute_percd2021_optimized4(open, close, high, low, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, hmax, high4, max5, lastdu4, code):
    """
    根据一系列股票交易行为计算综合得分。
    
    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        hmax (float): 历史最高价
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
    
    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价加分
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价加分
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）加分
    if close == high:
        init_c += 2.0
        
    # 最低价大于前日最低价加分
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨加分
    if last_close <= upper and close > upper:
        init_c += 8.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 3.0
        
    # 成交量温和上涨加分
    vol_ratio = now_vol / last_vol
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破加分
    if hmax is not None and high >= hmax:
        init_c += 15.0

    # 每日高开高走，无价格重叠 (low > last_high)
    if low > last_high:
        init_c += 15.0
        if open > last_high and close > open:
            init_c += 5.0
            
    # 新增：开盘价就是最低价 (open == low) 加分
    if open == low:
        # 特别是低开高走且开盘在 ma5 之上
        if open < last_close and open >= ma5 and close > open:
            init_c += 12.0 # 给予高分，代表主力意图明显
        elif close > open: # 只要是开盘即最低的上涨，都加分
            init_c += 5.0
    
    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价减分
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）减分
    if low < last_low:
        init_c -= 2.0
        
    # 放量下跌（下跌且成交量大于昨日）减分
    if close < last_close and now_vol > last_vol:
        init_c -= 3.0
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 4.0
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 5.0

    # 高开低走 (open > close) 减分
    if open > close:
        init_c -= 3.0
        if close < ma5 or close < ma10:
            init_c -= 2.0
            
    # 新增：开盘价就是最高价 (open == high) 减分
    if open == high:
        init_c -= 5.0 # 当天走势疲弱，直接给出负分
    
    # ====================
    # 大幅涨跌幅的分值权重
    # ====================
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 5.0
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 5.0

    # ====================
    # 原始代码中关于 lastdu4 的逻辑
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c


def func_compute_percd2021_optimized3(open, close, high, low, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, hmax, high4, max5, lastdu4, code):
    """
    根据一系列股票交易行为计算综合得分。
    
    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        hmax (float): 历史最高价
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
    
    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价加分
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价加分
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）加分
    if close == high:
        init_c += 2.0  # 权重加高
        
    # 最低价大于前日最低价加分
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨加分
    # 特别处理首次突破 upper 的情况
    if last_close <= upper and close > upper:
        init_c += 8.0 # 突破给更高分
        # 跳空高开高走且突破布林线上轨，启动信号明显
        if open > last_high and close > open:
            init_c += 10.0 # 极强的启动信号
    elif close >= upper:
        init_c += 3.0 # 站上布林线上轨
        
    # 成交量温和上涨加分
    vol_ratio = now_vol / last_vol
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破加分
    if hmax is not None and high >= hmax:
        init_c += 15.0 # 突破历史高点给最高分

    # ====================
    # 新增权重：每日高开高走，无价格重叠 (low > last_high)
    # ====================
    if low > last_high: # 今日最低价高于昨日最高价
        init_c += 15.0 # 强势跳空，权重非常高
        # 如果是跳空高开高走并且收盘价也高于开盘价
        if open > last_high and close > open:
            init_c += 5.0 # 额外加分，表明当天持续强势

    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价减分
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）减分
    if low < last_low:
        init_c -= 2.0  # 创新低给更多负分
        
    # 放量下跌（下跌且成交量大于昨日）减分
    if close < last_close and now_vol > last_vol:
        init_c -= 3.0  # 放量下跌给更多负分
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 4.0  # 跌破关键均线给更多负分
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 5.0  # 跌破更长周期均线给更多负分

    # ====================
    # 新增权重：高开低走 (open > close) 减分
    # ====================
    if open > close: # 开盘价高于收盘价
        init_c -= 3.0 # 当天走势疲软，降低分数
        # 如果高开低走同时跌破了ma5或ma10，则进一步降低分数
        if close < ma5 or close < ma10:
            init_c -= 2.0 # 破位下跌，更差

    # ====================
    # 大幅涨跌幅的分值权重
    # ====================
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 5.0  # 超出一定涨幅额外加分
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 5.0  # 超出一定跌幅额外减分

    # ====================
    # 原始代码中关于 lastdu4 的逻辑 (保持不变)
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c




def func_compute_percd2021_optimized2(open, close, high, low, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, hmax, high4, max5, lastdu4, code):
    """
    根据一系列股票交易行为计算综合得分。
    
    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        hmax (float): 历史最高价
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
    
    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    
    # ====================
    # 加分项（积极信号）
    # ====================
    
    # 收盘价大于前日收盘价加分
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价加分
    if high > last_high:
        init_c += 1.0
        
    # 收最高价（收盘价等于最高价）加分
    if close == high:
        init_c += 2.0  # 权重加高
        
    # 最低价大于前日最低价加分
    if low > last_low:
        init_c += 1.0

    # 收盘价突破布林线上轨加分
    if last_close <= upper and close > upper:
        init_c += 8.0 # 突破给更高分
    elif close >= upper:
        init_c += 3.0 # 站上布林线上轨
        
    # 成交量温和上涨加分
    vol_ratio = now_vol / last_vol
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # 历史高点突破加分
    if hmax is not None and high >= hmax:
        init_c += 15.0 # 突破历史高点给最高分

    # ====================
    # 减分项（消极信号）
    # ====================

    # 收盘价小于前日收盘价减分
    if close < last_close:
        init_c -= 1.0
        
    # 最低价小于前日最低价（创新低）减分
    if low < last_low:
        init_c -= 2.0  # 创新低给更多负分
        
    # 放量下跌（下跌且成交量大于昨日）减分
    if close < last_close and now_vol > last_vol:
        init_c -= 3.0  # 放量下跌给更多负分
    
    # 下破 ma5 减分
    if last_close >= ma5 and close < ma5:
        init_c -= 4.0  # 跌破关键均线给更多负分
    
    # 下破 ma10 减分
    if last_close >= ma10 and close < ma10:
        init_c -= 5.0  # 跌破更长周期均线给更多负分

    # ====================
    # 大幅涨跌幅的分值权重
    # ====================
    
    # 大幅上涨（加分权重）
    if percent_change > 5:
        init_c += 5.0  # 超出一定涨幅额外加分
    
    # 大幅下跌（减分权重）
    if percent_change < -5:
        init_c -= 5.0  # 超出一定跌幅额外减分

    # ====================
    # 原始代码中关于 lastdu4 的逻辑
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c

def func_compute_percd2021_optimized1(open, close, high, low, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, hmax, high4, max5, lastdu4, code):
    """
    根据一系列股票交易行为计算综合得分。
    
    Args:
        open (float): 今日开盘价
        close (float): 今日收盘价
        high (float): 今日最高价
        low (float): 今日最低价
        last_close (float): 昨日收盘价
        last_high (float): 昨日最高价
        last_low (float): 昨日最低价
        ma5 (float): 5日移动平均线
        ma10 (float): 10日移动平均线
        now_vol (float): 今日成交量
        last_vol (float): 昨日成交量
        upper (float): 布林线上轨值
        hmax (float): 历史最高价
        high4 (float): 4日前的最高价
        max5 (float): 5日前的最高价
        lastdu4 (float): 前4日的涨幅
        code (str): 股票代码
    
    Returns:
        float: 综合得分
    """
    init_c = 0.0
    
    # 参数有效性检查
    if np.isnan(last_close) or last_close == 0:
        return 0
    if np.isnan(last_vol) or last_vol == 0:
        return 0

    # === 基本得分项 ===
    # 收盘价大于前日收盘价加分
    if close > last_close:
        init_c += 1.0
    
    # 最高价大于前日最高价加分
    if high > last_high:
        init_c += 1.0
        
    # 收最高价加分
    if close == high:
        init_c += 1.0
        
    # 最低价大于前日最低价加分
    if low > last_low:
        init_c += 1.0

    # === 进阶得分项 ===
    # 收盘价突破布林线上轨加分
    if last_close <= upper and close > upper:
        init_c += 5.0 # 突破给高分
    elif close >= upper:
        init_c += 2.0 # 站上布林线上轨
        
    # 成交量温和上涨加分
    vol_ratio = now_vol / last_vol
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    
    # 大于high4加权重分
    if high > high4:
        init_c += 3.0
    
    # 一个大阳线，大于前几日
    percent_change = (close - last_close) / last_close * 100
    if percent_change > 3 and close >= high * 0.95:
        if high > max5 and high > high4:
            init_c += 5.0
            
    # === 历史高点突破加分 ===
    if hmax is not None and high >= hmax:
        init_c += 10.0 # 突破历史高点给大分

    # === 修正后的原代码逻辑（简化和重构） ===
    # 原始代码中的大涨判定
    if percent_change > 2 and low > last_low and (close > ma5 or now_vol > last_vol * 1.2):
        init_c += 1.0

    # 原始代码中的上影线判定
    if high > last_high and low > last_low and close > ma5:
        init_c += 1.0
        
    # 原始代码中关于 lastdu4 的逻辑
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8
    
    return init_c

def process_stock_data_with_score(code):
    """
    使用 list(map) 计算每一天的得分，并将其存储在 'optimized_score' 列中。
    
    Args:
        code (str): 股票代码。
        
    Returns:
        pd.DataFrame: 包含得分的 DataFrame。
    """
    df = tdd.get_tdx_Exp_day_to_df(code, dl=ct.duration_date_day, resample='d')

    if df is None or df.empty or len(df) < 20:
        print("数据不足，无法计算布林带或获取数据。")
        return pd.DataFrame()

    # 重命名列以匹配函数参数
    df.rename(columns={'vol': 'volume'}, inplace=True)
    
    # 计算技术指标
    # df['ma5'] = talib.SMA(df['close'], timeperiod=5)
    # df['ma10'] = talib.SMA(df['close'], timeperiod=10)
    # df['upper'], _, _ = talib.BBANDS(df['close'], timeperiod=20)
    # df['hmax'] = df['high'].cummax() # 累计最高价
    # df['high4'] = df['high'].shift(4)
    # df['max5'] = df['high'].shift(5)
    
    # # 避免除以0或NaN
    # df['lastdu4'] = (df['high'].shift(1) - df['low'].shift(4)) / df['low'].shift(4).replace(0, np.nan) + 1

    # 使用 list(map) 调用 func_compute_percd2021
    df['optimized_score'] = list(map(
        func_compute_percd2021,
        df['open'],
        df['close'],
        df['high'],
        df['low'],
        df['open'].shift(1), # last_open
        df['close'].shift(1), # last_close
        df['high'].shift(1), # last_high
        df['low'].shift(1), # last_low
        df['ma5d'],
        df['ma10d'],
        df['volume'],
        df['volume'].shift(1),
        df['upper'],
        df['high4'],
        df['max5'],
        df['hmax'],
        df['lastdu4'],
        pd.Series([code]*len(df)) # code
    ))
    
    # 填充 NaN 值
    df['optimized_score'].fillna(0, inplace=True)
    
    return df
    
# 示例运行函数
def run_example(code='600000'):
    """
    运行示例，展示如何使用 process_stock_data_with_score 函数。
    """
    df_scored = process_stock_data_with_score(code)
    
    if not df_scored.empty:
        print(f"股票 {code} 的每日综合得分:")
        print(df_scored[['open', 'close', 'optimized_score']].tail(30))



if __name__ == "__main__":
    # code = '603301'
    stock_code = '600601'
    stock_code = '600785'
    stock_code = '600376'
    stock_code = '837174'
    stock_code = '600007'
    stock_code = '600863'
    run_example(stock_code)