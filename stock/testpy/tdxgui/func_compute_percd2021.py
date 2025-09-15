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

def func_compute_percd2021_src(open, close, high, low, last_open, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, high4, max5, hmax, lastdu4, code, idate=None):
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

def process_stock_data_with_score(code,df=None):
    """
    使用 list(map) 计算每ikik一天的得分，并将其存储在 'optimized_score' 列中。
    
    Args:
        code (str): 股票代码。
        
    Returns:
        pd.DataFrame: 包含得分的 DataFrame。
    """

    if df is None:
        df = tdd.get_tdx_Exp_day_to_df(code, dl=ct.duration_date_day, resample='d')

    if df is None or df.empty or len(df) < 20:
        print("数据不足，无法计算布林带或获取数据。")
        return pd.DataFrame()

    # 重命名列以匹配函数参数
    # df.rename(columns={'vol': 'volume'}, inplace=True)
    
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
    df['score'] = list(map(
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
        df['vol'],
        df['vol'].shift(1),
        df['upper'],
        df['high4'],
        df['max5'],
        df['hmax'],
        df['lastdu4'],
        df['code'],
        df.index ,
    ))
    
    # 填充 NaN 值
    df['score'].fillna(0, inplace=True)
    
    return df

def process_stock_data_with_score_src(code,df=None):
    """
    使用 list(map) 计算每一天的得分，并将其存储在 'optimized_score' 列中。
    
    Args:
        code (str): 股票代码。
        
    Returns:
        pd.DataFrame: 包含得分的 DataFrame。
    """

    if df is None:
        df = tdd.get_tdx_Exp_day_to_df(code, dl=ct.duration_date_day, resample='d')

    if df is None or df.empty or len(df) < 20:
        print("数据不足，无法计算布林带或获取数据。")
        return pd.DataFrame()

    df = compute_score_batch(df)
    # 填充 NaN 值
    df['score'].fillna(0, inplace=True)
    
    return df




def func_compute_percd2021_debug_v3(open, close, high, low,
                                    last_open, last_close, last_high, last_low,
                                    ma5, ma10, now_vol, last_vol,
                                    upper, high4, max5, hmax,
                                    lastdu4, code, idate=None,
                                    prev_scores=None):
    init_c = 0.0

    # 无效数据直接返回
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        print(f"{code} {idate} - 无效数据，返回0")
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    print(f"\n{code} {idate} - 基础数据: open={open}, close={close}, high={high}, low={low}, last_close={last_close}, percent_change={percent_change:.2f}, vol_ratio={vol_ratio:.2f}")

    # ====================
    # 1️⃣ 潜在启动股（低波动区间启动）
    # ====================
    if high > high4 and 3 <= percent_change <= 8 and last_close < high4:
        init_c += 15
        print("✔ 潜在启动股（低波动区间） +15")

    # ====================
    # 2️⃣ 初期启动叠加（开盘快速拉升）
    # ====================
    if close >= high*0.995 and percent_change > 5 and vol_ratio > 1.2:
        print("✔ 初期启动叠加条件命中")
        if str(code).startswith('6') or str(code).startswith('0'):
            init_c += 25
        elif str(code).startswith('3'):
            init_c += 20
        elif str(code).startswith('688') or str(code).startswith('8'):
            init_c += 30
        else:
            init_c += 15
        print(f"   初期启动加分: {init_c}")

    # ====================
    # 3️⃣ 前几日得分叠加（prev_scores）
    # ====================
    if prev_scores is not None:
        prev_total = sum(prev_scores)
        prev_weight = min(prev_total * 0.1, 20)  # 前几日分值10%加权，最多加20分
        init_c += prev_weight
        print(f"✔ 前几日得分叠加: {prev_scores}, 加权 +{prev_weight}")

    # ====================
    # 4️⃣ 连续高位递减/巨量减分
    # ====================
    if high >= hmax:
        init_c += 20
        print("✔ 历史高点突破 +20")
        if vol_ratio > 3:
            init_c -= 15
            print("✖ 高位巨量风险 -15")

    if low > last_high:
        init_c += 20
        print("✔ 跳空高开高走 +20")
        if close > open:
            init_c += 5
            print("   收盘高于开盘 +5")

    # ====================
    # 5️⃣ 成交量温和变化加权
    # ====================
    if 1.0 < vol_ratio <= 2.0:
        init_c += 2
        print("✔ 成交量温和上涨 +2")
    elif vol_ratio > 2:
        init_c += 5
        print("✔ 成交量放量 >2倍 +5")

    # ====================
    # 6️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1
        print("✔ 收盘价高于昨日 +1")
    if high > last_high:
        init_c += 1
        print("✔ 最高价高于昨日 +1")
    if close >= high*0.998:
        init_c += 5
        print("✔ 收盘接近最高价 +5")
    if low > last_low:
        init_c += 1
        print("✔ 最低价高于昨日 +1")
    if last_close <= upper and close > upper:
        init_c += 10
        print("✔ 突破布林上轨 +10")
        if open > last_high and close > open:
            init_c += 10
            print("   高开高走突破 +10")
    elif close >= upper:
        init_c += 5
        print("✔ 收盘位于布林上轨之上 +5")

    # ====================
    # 7️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1
        print("✖ 收盘低于昨日 -1")
    if low < last_low:
        init_c -= 3
        print("✖ 创新低 -3")
    if close < last_close and now_vol > last_vol:
        init_c -= 8
        print("✖ 放量下跌 -8")
    if last_close >= ma5 and close < ma5:
        init_c -= 5
        print("✖ 下破MA5 -5")
    if last_close >= ma10 and close < ma10:
        init_c -= 8
        print("✖ 下破MA10 -8")
    if open > close:
        init_c -= 5
        print("✖ 高开低走 -5")
        if close < ma5 or close < ma10:
            init_c -= 5
            print("   低于MA5/MA10再减5")
    if open == high:
        init_c -= 10
        print("✖ 开盘即最高价 -10")
    if percent_change < -5:
        init_c -= 8
        print("✖ 大幅下跌 <-5% -8")

    # ====================
    # 8️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
            print("✔ lastdu4 <=1.12 +10")
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8
            print("✔ 1.12<lastdu4<=1.21 +8")
    # ---------------------------
    # 新增：潜在启动因子
    # ---------------------------
    # 最近区间压缩：用 high4 和最近低点估算波动范围
    # if last_low:
    #     recent_range = (high4 / min(last_low, last_close) - 1) * 100
    # else:
    #     recent_range = None
    recent_range = lastdu4
    print(f'lastdu4: {recent_range}')
    if recent_range is not None and recent_range < 8:  # 波动压缩
        if close > high4 and 3 <= percent_change <= 8:
            init_c += 20
            print(f"{idate} ✔ 潜在启动因子（低波动后首次突破） +20")
            if vol_ratio > 1.5:
                init_c += 5
                print(f"{idate}   放量突破 +5")

    print(f"总得分: {init_c}\n")
    return init_c


def func_compute_percd2021(open, close, high, low,
                           last_open, last_close, last_high, last_low,
                           ma5, ma10, now_vol, last_vol,
                           upper, high4, max5, hmax,
                           lastdu4, code, idate=None):
    init_c = 0.0
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    if high > high4 and percent_change > 5 and last_close < high4:
        if high >= open > last_close and close > last_close and close >= high*0.99 and (high < hmax or last_high < hmax):
            if str(code).startswith(('6','0')):
                if percent_change >= 5:
                    init_c += 25.0
                else:
                    init_c += 20.0
            elif str(code).startswith('3'):
                if percent_change >= 6:
                    init_c += 35.0
                else:
                    init_c += 20.0
            elif str(code).startswith(('688','8')):
                if percent_change >= 5:
                    init_c += 35.0
                else:
                    init_c += 20.0
            else:
                init_c += 15.0
            if vol_ratio < 2:
                init_c += 15.0
            else:
                init_c += 2.0
        else:
            init_c += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1.0
    if high > last_high:
        init_c += 1.0
    if close >= high*0.998:
        init_c += 5.0
        if vol_ratio > 2:
            init_c += 5.0
    if low > last_low:
        init_c += 1.0
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    if high > high4:
        init_c += 3.0
    if percent_change > 3 and close >= high * 0.95 and high > max5 and high > high4:
        init_c += 5.0
    if hmax is not None and high >= hmax:
        init_c += 20.0
    if low > last_high:
        init_c += 20.0
        if close > open:
            init_c += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0
        if close > open:
            init_c += 8.0
        if vol_ratio > 2:
            init_c += 5.0
    if percent_change > 5:
        init_c += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1.0
    if low < last_low:
        init_c -= 3.0
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
    if open == high:
        init_c -= 10.0
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 15:
            init_c += 30
        elif 15 < lastdu4 <=40:
            init_c += 18

    return init_c


def func_compute_percd2021_debug(open, close, high, low,
                                 last_open, last_close, last_high, last_low,
                                 ma5, ma10, now_vol, last_vol,
                                 upper, high4, max5, hmax,
                                 lastdu4, code, idate=None):
    init_c = 0.0
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        print(f"{code} {idate} - 无效数据，返回0")
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    print(f"\n{code} {idate} - 基础数据: open={open}, close={close}, high={high}, low={low}, last_close={last_close}, percent_change={percent_change:.2f}, vol_ratio={vol_ratio:.2f}")

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    if high > high4 and percent_change > 5 and last_close < high4:
        if high >= open > last_close and close > last_close and close >= high*0.99 and (high < hmax or last_high < hmax):
            print("✔ 刚启动强势股条件命中")
            if str(code).startswith(('6','0')):
                if percent_change >= 5:
                    init_c += 25.0
                    print("   大盘/主板 >=5% 加25分")
                else:
                    init_c += 20.0
                    print("   大盘/主板 <5% 加20分")
            elif str(code).startswith('3'):
                if percent_change >= 6:
                    init_c += 35.0
                    print("   创业板 >=6% 加25分")
                else:
                    init_c += 20.0
                    print("   创业板 <6% 加15分")
            elif str(code).startswith(('688','8')):
                if percent_change >= 5:
                    init_c += 35.0
                    print("   科创板 >=5% 加35分")
                else:
                    init_c += 20.0
                    print("   科创板 <5% 加20分")
            else:
                init_c += 15.0
                print("   其他市场 加15分")
            if vol_ratio < 2:
                init_c += 15.0
                print("   安全放量加5分")
            else:
                init_c += 2.0
                print("   放量略大加2分")
        else:
            init_c += 15.0
            print("非高开高走其他市场 加15分")

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1.0
        print("✔ 收盘价高于昨日 +1")
    if high > last_high:
        init_c += 1.0
        print("✔ 最高价高于昨日 +1")
    if close >= high*0.998:
        init_c += 5.0
        print("✔ 收盘等于最高价 +5")
        if vol_ratio > 2:
            init_c += 5.0
            print("   放量 >2倍 +5")
    if low > last_low:
        init_c += 1.0
        print("✔ 最低价高于昨日 +1")
    if last_close <= upper and close > upper:
        init_c += 10.0
        print("✔ 突破布林上轨 +10")
        if open > last_high and close > open:
            init_c += 10.0
            print("   高开高走突破 +10")
    elif close >= upper:
        init_c += 5.0
        print("✔ 收盘位于布林上轨之上 +5")
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
        print("✔ 成交量温和上涨 +2")
    if high > high4:
        init_c += 3.0
        print("✔ 高于最近4日最高 +3")
    if percent_change > 3 and close >= high * 0.95 and high > max5 and high > high4:
        init_c += 5.0
        print("✔ 大阳线超过前几日 +5")
    if hmax is not None and high >= hmax:
        init_c += 20.0
        print("✔ 历史高点突破 +20")
    if low > last_high:
        init_c += 20.0
        print("✔ 每日高开高走跳空 +20")
        if close > open:
            init_c += 5.0
            print("   收盘高于开盘 +5")
    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0
            print("✔ 低开高走在MA5之上 +15")
        if close > open:
            init_c += 8.0
            print("✔ 低开高走 +8")
        if vol_ratio > 2:
            init_c += 5.0
            print("   配合放量 +5")
    if percent_change > 5:
        init_c += 8.0
        print("✔ 大幅上涨 >5% +8")

    # ====================
    # 3️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1.0
        print("✖ 收盘低于昨日 -1")
    if low < last_low:
        init_c -= 3.0
        print("✖ 创新低 -3")
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0
        print("✖ 放量下跌 -8")
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
        print("✖ 下破MA5 -5")
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0
        print("✖ 下破MA10 -8")
    if open > close:
        init_c -= 5.0
        print("✖ 高开低走 -5")
        if close < ma5 or close < ma10:
            init_c -= 5.0
            print("   低于MA5/MA10再减5")
    if open == high:
        init_c -= 10.0
        print("✖ 开盘即最高价 -10")
    if percent_change < -5:
        init_c -= 8.0
        print("✖ 大幅下跌 <-5% -8")

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 15:
            init_c += 30
            print("✔ lastdu4 <=15 +10")
        elif 15 < lastdu4 <=40:
            init_c += 18
            print("✔ 15 < lastdu4 <= 40 +8")

    print(f"总得分: {init_c}\n")
    return init_c


def func_compute_percd2021_optimized(open, close, high, low, last_open, last_close, last_high, last_low, ma5, ma10, now_vol, last_vol, upper, high4, max5, hmax, lastdu4, code, idate=None):
    init_c = 0.0
    if np.isnan(last_close) or last_close == 0 or np.isnan(last_vol) or last_vol == 0:
        return 0

    percent_change = (close - last_close) / last_close * 100
    vol_ratio = now_vol / last_vol

    # ====================
    # 1️⃣ 刚启动强势股
    # ====================
    if high > open > last_close and close > last_close:
        if str(code).startswith('6') or str(code).startswith('0'):
            if percent_change >= 10:
                init_c += 30.0
            else:
                init_c += 10.0
        elif str(code).startswith('3'):
            if percent_change >= 10:
                init_c += 20.0
            else:
                init_c += 8.0
        elif str(code).startswith('688'):
            if percent_change >= 10:
                init_c += 15.0
            else:
                init_c += 5.0
        else:
            init_c += 5.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    if close > last_close:
        init_c += 1.0
    if high > last_high:
        init_c += 1.0
    if close == high:
        init_c += 5.0
        if vol_ratio > 2:
            init_c += 5.0
    if low > last_low:
        init_c += 1.0
    if last_close <= upper and close > upper:
        init_c += 10.0
        if open > last_high and close > open:
            init_c += 10.0
    elif close >= upper:
        init_c += 5.0
    if 1.0 < vol_ratio < 2.0:
        init_c += 2.0
    if high > high4:
        init_c += 3.0
    if percent_change > 3 and close >= high * 0.95 and high > max5 and high > high4:
        init_c += 5.0
    if hmax is not None and high >= hmax:
        init_c += 20.0
    if low > last_high:
        init_c += 20.0
        if close > open:
            init_c += 5.0
    if open == low:
        if open < last_close and open >= ma5 and close > open:
            init_c += 15.0
        elif close > open:
            init_c += 8.0
        if vol_ratio > 2:
            init_c += 5.0
    if percent_change > 5:
        init_c += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    if close < last_close:
        init_c -= 1.0
    if low < last_low:
        init_c -= 3.0
    if close < last_close and now_vol > last_vol:
        init_c -= 8.0
    if last_close >= ma5 and close < ma5:
        init_c -= 5.0
    if last_close >= ma10 and close < ma10:
        init_c -= 8.0
    if open > close:
        init_c -= 5.0
        if close < ma5 or close < ma10:
            init_c -= 5.0
    if open == high:
        init_c -= 10.0
    if percent_change < -5:
        init_c -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    if high > high4 and lastdu4 is not None:
        if lastdu4 <= 1.12:
            init_c += 10
        elif 1.12 < lastdu4 <= 1.21:
            init_c += 8

    return init_c

    
# 示例运行函数
def run_example(code='600000',df_scored=None):
    """
    运行示例，展示如何使用 process_stock_data_with_score 函数。
    """

    df_scored = process_stock_data_with_score(code,df=df_scored)
    # df_scored_src = process_stock_data_with_score_src(code,df=None)
    
    if not df_scored.empty:
        print(f"股票 {code} 的每日综合得分:")
        df_scored['vol_ratio'] = df_scored['vol'] / df_scored['vol'].shift(1)
        print(df_scored[['open', 'close','vol_ratio','lastdu4', 'score']].tail(30))
        # print(df_scored_src[['open', 'close', 'score']].tail(30))
    return df_scored



import pandas as pd
import numpy as np

import pandas as pd
import numpy as np

def compute_score_vectorized(df):
    """
    向量化计算股票综合评分，逻辑对应 func_compute_percd2021
    假设 df 中包含以下列：
    ['open', 'close', 'high', 'low', 'last_open', 'last_close', 'last_high', 'last_low',
     'ma5d', 'ma10d', 'vol', 'last_vol', 'upper', 'high4', 'max5', 'hmax', 'lastdu4', 'code']
    """
    score = pd.Series(0.0, index=df.index)

    # 基础数据
    percent_change = (df['close'] - df['last_close']) / df['last_close'] * 100
    vol_ratio = df['vol'] / df['last_vol']
    valid_mask = (~df['last_close'].isna()) & (df['last_close'] != 0) & (~df['last_vol'].isna()) & (df['last_vol'] != 0)
    score.loc[~valid_mask] = 0.0

    # ====================
    # 1️⃣ 刚启动强势股（安全拉升）
    # ====================
    mask_outer = valid_mask & (df['high'] > df['high4']) & (percent_change > 5) & (df['last_close'] < df['high4'])
    mask_inner = mask_outer & (df['high'] >= df['open']) & (df['open'] > df['last_close']) & \
                 (df['close'] > df['last_close']) & (df['close'] >= df['high']*0.99) & \
                 ((df['high'] < df['hmax']) | (df['last_high'] < df['hmax']))

    # 市场前缀加分
    for prefix, high_score, low_score in [('6',25,20), ('0',25,20), ('3',35,20), ('688',35,18), ('8',35,18)]:
        mask = mask_inner & df['code'].astype(str).str.startswith(prefix)
        score.loc[mask & (percent_change >= 5)] += high_score
        score.loc[mask & (percent_change < 5)] += low_score

    mask_other = mask_inner & ~(df['code'].astype(str).str.startswith(('6','0','3','688','8')))
    score.loc[mask_other] += 15.0

    # 外层非高开高走安全启动加分
    score.loc[mask_outer] += 15.0

    # ====================
    # 2️⃣ 收盘价突破与高点
    # ====================
    score.loc[valid_mask & (df['close'] > df['last_close'])] += 1.0
    score.loc[valid_mask & (df['high'] > df['last_high'])] += 1.0
    score.loc[valid_mask & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (vol_ratio > 2) & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (df['low'] > df['last_low'])] += 1.0
    score.loc[valid_mask & (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['open'] > df['last_high']) & (df['close'] > df['open']) &
              (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['close'] >= df['upper'])] += 5.0
    score.loc[valid_mask & (1.0 < vol_ratio) & (vol_ratio < 2.0)] += 2.0
    score.loc[valid_mask & (df['high'] > df['high4'])] += 3.0
    score.loc[valid_mask & (percent_change > 3) & (df['close'] >= df['high']*0.95) &
              (df['high'] > df['max5']) & (df['high'] > df['high4'])] += 5.0
    score.loc[valid_mask & (df['hmax'].notna()) & (df['high'] >= df['hmax'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high']) & (df['close'] > df['open'])] += 5.0

    # ====================
    # 低开高走 & 放量 & MA5
    # ====================
    mask_low_open = valid_mask & (df['open'] == df['low'])
    score.loc[mask_low_open & (df['open'] < df['last_close']) & (df['open'] >= df['ma5d']) & (df['close'] > df['open'])] += 15.0
    score.loc[mask_low_open & (df['close'] > df['open'])] += 8.0
    score.loc[mask_low_open & (vol_ratio > 2)] += 5.0
    score.loc[valid_mask & (percent_change > 5)] += 8.0

    # ====================
    # 3️⃣ 减分项
    # ====================
    score.loc[valid_mask & (df['close'] < df['last_close'])] -= 1.0
    score.loc[valid_mask & (df['low'] < df['last_low'])] -= 3.0
    score.loc[valid_mask & (df['close'] < df['last_close']) & (df['vol'] > df['last_vol'])] -= 8.0
    score.loc[valid_mask & (df['last_close'] >= df['ma5d']) & (df['close'] < df['ma5d'])] -= 5.0
    score.loc[valid_mask & (df['last_close'] >= df['ma10d']) & (df['close'] < df['ma10d'])] -= 8.0
    score.loc[valid_mask & (df['open'] > df['close'])] -= 5.0
    score.loc[valid_mask & (df['open'] > df['close']) & ((df['close'] < df['ma5d']) | (df['close'] < df['ma10d']))] -= 5.0
    score.loc[valid_mask & (df['open'] == df['high'])] -= 10.0
    score.loc[valid_mask & (percent_change < -5)] -= 8.0

    # ====================
    # 4️⃣ lastdu4 波动幅度辅助加分
    # ====================
    mask_du4_1 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] <= 15)
    mask_du4_2 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] > 15) & (df['lastdu4'] <= 40)
    score.loc[mask_du4_1] += 30
    score.loc[mask_du4_2] += 18

    return score


def compute_score_vectorized_good(df):
    """
    向量化计算股票综合评分，使用 df['ma5d']、df['ma10d'] 替换 ma5/ma10
    """
    # 初始化得分
    score = pd.Series(0.0, index=df.index)

    # 基础数据
    percent_change = (df['close'] - df['last_close']) / df['last_close'] * 100
    vol_ratio = df['vol'] / df['last_vol']
    valid_mask = (~df['last_close'].isna()) & (df['last_close'] != 0) & (~df['last_vol'].isna()) & (df['last_vol'] != 0)
    score.loc[~valid_mask] = 0.0

    # 1️⃣ 刚启动强势股
    mask_outer = valid_mask & (df['high'] > df['high4']) & (percent_change > 5) & (df['last_close'] < df['high4'])
    mask_inner = mask_outer & (df['high'] >= df['open']) & (df['open'] > df['last_close']) & \
                 (df['close'] > df['last_close']) & (df['close'] >= df['high']*0.99) & \
                 ((df['high'] < df['hmax']) | (df['last_high'] < df['hmax']))

    # 刚启动强势股 - 不同市场加分
    for prefix, high_score, low_score in [('6',25,20), ('0',25,20), ('3',25,15), ('688',35,20), ('8',35,20)]:
        mask = mask_inner & df['code'].astype(str).str.startswith(prefix)
        score.loc[mask & (percent_change >= 5)] += high_score
        score.loc[mask & (percent_change < 5)] += low_score

    mask_other = mask_inner & ~(df['code'].astype(str).str.startswith(('6','0','3','688','8')))
    score.loc[mask_other] += 15.0

    score.loc[mask_outer] += 15.0

    # 2️⃣ 收盘价突破与高点
    score.loc[valid_mask & (df['close'] > df['last_close'])] += 1.0
    score.loc[valid_mask & (df['high'] > df['last_high'])] += 1.0
    score.loc[valid_mask & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (vol_ratio > 2) & (df['close'] >= df['high']*0.998)] += 5.0
    score.loc[valid_mask & (df['low'] > df['last_low'])] += 1.0
    score.loc[valid_mask & (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['open'] > df['last_high']) & (df['close'] > df['open']) & 
              (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])] += 10.0
    score.loc[valid_mask & (df['close'] >= df['upper'])] += 5.0
    score.loc[valid_mask & (1.0 < vol_ratio) & (vol_ratio < 2.0)] += 2.0
    score.loc[valid_mask & (df['high'] > df['high4'])] += 3.0
    score.loc[valid_mask & (percent_change > 3) & (df['close'] >= df['high']*0.95) & 
              (df['high'] > df['max5']) & (df['high'] > df['high4'])] += 5.0
    score.loc[valid_mask & (df['hmax'].notna()) & (df['high'] >= df['hmax'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high'])] += 20.0
    score.loc[valid_mask & (df['low'] > df['last_high']) & (df['close'] > df['open'])] += 5.0
    score.loc[valid_mask & (df['open'] == df['low']) & (df['open'] < df['last_close']) & 
              (df['open'] >= df['ma5d']) & (df['close'] > df['open'])] += 15.0
    score.loc[valid_mask & (df['open'] == df['low']) & (df['close'] > df['open'])] += 8.0
    score.loc[valid_mask & (df['open'] == df['low']) & (vol_ratio > 2)] += 5.0
    score.loc[valid_mask & (percent_change > 5)] += 8.0

    # 3️⃣ 减分项
    score.loc[valid_mask & (df['close'] < df['last_close'])] -= 1.0
    score.loc[valid_mask & (df['low'] < df['last_low'])] -= 3.0
    score.loc[valid_mask & (df['close'] < df['last_close']) & (df['vol'] > df['last_vol'])] -= 8.0
    score.loc[valid_mask & (df['last_close'] >= df['ma5d']) & (df['close'] < df['ma5d'])] -= 5.0
    score.loc[valid_mask & (df['last_close'] >= df['ma10d']) & (df['close'] < df['ma10d'])] -= 8.0
    score.loc[valid_mask & (df['open'] > df['close'])] -= 5.0
    score.loc[valid_mask & (df['open'] > df['close']) & ((df['close'] < df['ma5d']) | (df['close'] < df['ma10d']))] -= 5.0
    score.loc[valid_mask & (df['open'] == df['high'])] -= 10.0
    score.loc[valid_mask & (percent_change < -5)] -= 8.0

    # 4️⃣ lastdu4
    mask_du4_1 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] <= 1.12)
    mask_du4_2 = valid_mask & (df['high'] > df['high4']) & (df['lastdu4'] > 1.12) & (df['lastdu4'] <= 1.21)
    score.loc[mask_du4_1] += 10
    score.loc[mask_du4_2] += 8

    return score



def compute_score_vectorized1(df):
    """
    向量化计算综合得分，返回一个 Series。
    df 列表要求包含：
    ['open', 'close', 'high', 'low', 'last_open', 'last_close', 'last_high', 'last_low',
     'ma5', 'ma10', 'vol', 'last_vol', 'upper', 'high4', 'max5', 'hmax', 'lastdu4', 'code']
    """
    
    # 参数有效性检查
    mask_valid = (df['last_close'].notna() & (df['last_close'] != 0) &
                  df['last_vol'].notna() & (df['last_vol'] != 0))
    
    score = pd.Series(0.0, index=df.index)
    if not mask_valid.any():
        return score
    
    # 基本计算
    percent_change = (df['close'] - df['last_close']) / df['last_close'] * 100
    vol_ratio = df['vol'] / df['last_vol']
    
    # ====================
    # 加分项
    # ====================
    
    score += (df['close'] > df['last_close']).astype(float) * 1.0
    score += (df['high'] > df['last_high']).astype(float) * 1.0
    score += (df['close'] == df['high']).astype(float) * 5.0
    score += ((df['close'] == df['high']) & (vol_ratio > 2)).astype(float) * 5.0
    score += (df['low'] > df['last_low']).astype(float) * 1.0
    
    # 突破布林上轨
    mask_upper_break = (df['last_close'] <= df['upper']) & (df['close'] > df['upper'])
    score += mask_upper_break.astype(float) * 10.0
    mask_upper_extra = mask_upper_break & (df['open'] > df['last_high']) & (df['close'] > df['open'])
    score += mask_upper_extra.astype(float) * 10.0
    score += ((df['close'] >= df['upper']) & (~mask_upper_break)).astype(float) * 5.0
    
    # 成交量温和上涨
    score += ((vol_ratio > 1.0) & (vol_ratio < 2.0)).astype(float) * 2.0
    
    # 高于 high4
    score += (df['high'] > df['high4']).astype(float) * 3.0
    
    # 大阳线加分
    mask_big_up = (percent_change > 3) & (df['close'] >= df['high'] * 0.95) & (df['high'] > df['max5']) & (df['high'] > df['high4'])
    score += mask_big_up.astype(float) * 5.0
    
    # 历史高点突破
    mask_hmax = df['hmax'].notna() & (df['high'] >= df['hmax'])
    score += mask_hmax.astype(float) * 20.0
    
    # 高开高走
    mask_gap_up = df['low'] > df['last_high']
    score += mask_gap_up.astype(float) * 20.0
    mask_gap_up_extra = mask_gap_up & (df['close'] > df['open'])
    score += mask_gap_up_extra.astype(float) * 5.0
    
    # 开盘价就是最低价
    mask_open_low = df['open'] == df['low']
    score += (mask_open_low & (df['open'] < df['last_close']) & (df['open'] >= df['ma5d']) & (df['close'] > df['open'])).astype(float) * 15.0
    score += (mask_open_low & (df['close'] > df['open'])).astype(float) * 8.0
    score += (mask_open_low & (vol_ratio > 2)).astype(float) * 5.0
    
    # 大幅上涨
    score += (percent_change > 5).astype(float) * 8.0
    
    # ====================
    # 减分项
    # ====================
    
    score -= (df['close'] < df['last_close']).astype(float) * 1.0
    score -= (df['low'] < df['last_low']).astype(float) * 3.0
    score -= ((df['close'] < df['last_close']) & (df['vol'] > df['last_vol'])).astype(float) * 8.0
    score -= ((df['last_close'] >= df['ma5d']) & (df['close'] < df['ma5d'])).astype(float) * 5.0
    score -= ((df['last_close'] >= df['ma10d']) & (df['close'] < df['ma10d'])).astype(float) * 8.0
    mask_open_high = df['open'] > df['close']
    score -= mask_open_high.astype(float) * 5.0
    score -= (mask_open_high & ((df['close'] < df['ma5d']) | (df['close'] < df['ma10d']))).astype(float) * 5.0
    score -= (df['open'] == df['high']).astype(float) * 10.0
    score -= (percent_change < -5).astype(float) * 8.0
    
    # ====================
    # lastdu4逻辑
    # ====================
    mask_du4 = (df['high'] > df['high4']) & (df['lastdu4'].notna())
    score += ((mask_du4 & (df['lastdu4'] <= 1.12))).astype(float) * 10
    score += ((mask_du4 & (df['lastdu4'] > 1.12) & (df['lastdu4'] <= 1.21))).astype(float) * 8
    
    # 只保留有效行
    score[~mask_valid] = 0
    return score


def compute_score_batch(df):
    """
    对整个DataFrame批量计算综合得分

    df要求包含以下列：
    ['open', 'close', 'high', 'low', 'last_open', 'last_close', 'last_high', 'last_low',
     'ma5', 'ma10', 'now_vol', 'last_vol', 'upper', 'high4', 'max5', 'hmax', 'lastdu4', 'code']

    返回一个新的Series，表示每行的综合得分
    """
    # 先在整个DataFrame上生成上一日数据列
    df['last_open']  = df['open'].shift(1)
    df['last_close'] = df['close'].shift(1)
    df['last_high']  = df['high'].shift(1)
    df['last_low']   = df['low'].shift(1)
    df['last_vol']   = df['vol'].shift(1)
    # print('vol' in df.columns,df['vol'][:5])
    # def row_score(row):
    #     return func_compute_percd2021_optimized(
    #         row['open'], row['close'], row['high'], row['low'],
    #         row['last_open'], row['last_close'], row['last_high'], row['last_low'],
    #         row['ma5d'], row['ma10d'], row['vol'], row['last_vol'],
    #         row['upper'], row['high4'], row['max5'], row['hmax'],
    #         row['lastdu4'], row['code'], row.get('idate', None)
    #     )

    # df['score'] = compute_score_vectorized(df)
    df['score'] = compute_score_vectorized(df)
    return df


if __name__ == "__main__":
    # code = '603301'
    stock_code = '600601'
    stock_code = '600785'
    stock_code = '600376'
    stock_code = '837174'
    stock_code = '834407'
    stock_code = '688981'
    # stock_code = '600007'
    # stock_code = '600863'
    df = tdd.get_tdx_Exp_day_to_df(stock_code, dl=ct.duration_date_day, resample='d')

    # import ipdb;ipdb.set_trace()
    # df = tdd.get_tdx_Exp_day_to_df(stock_code, dl=60, resample='d')
    df = compute_score_batch(df)
    # print(df[-30:])
    import pandas as pd

    # 假设 df 是你的行情数据，包含 open, close, high, low, ma5d, ma10d, vol, upper, high4, max5, hmax, lastdu4, code
    # 初始化一个空的分值列表
    # scores = []
    # prev_scores = []
    # # 先生成前一日的列
    # df['open_prev']  = df['open'].shift(1)
    # df['close_prev'] = df['close'].shift(1)
    # df['high_prev']  = df['high'].shift(1)
    # df['low_prev']   = df['low'].shift(1)
    # df['vol_prev']   = df['vol'].shift(1)

    # for idx, row in df.iterrows():
    #     score = func_compute_percd2021_debug_v3(
    #         open=row['open'],
    #         close=row['close'],
    #         high=row['high'],
    #         low=row['low'],
    #         last_open=row['open_prev'],
    #         last_close=row['close_prev'],
    #         last_high=row['high_prev'],
    #         last_low=row['low_prev'],
    #         ma5=row['ma5d'],
    #         ma10=row['ma10d'],
    #         now_vol=row['vol'],
    #         last_vol=row['vol_prev'],
    #         upper=row['upper'],
    #         high4=row['high4'],
    #         max5=row['max5'],
    #         hmax=row['hmax'],
    #         lastdu4=row['lastdu4'],
    #         code=row['code'],
    #         idate=row.name,          # 用 index 作为日期标识
    #         prev_scores=prev_scores  # 传入前几日得分
    #     )
    #     scores.append(score)
    #     # 更新 prev_scores，只保留最近 2 天
    #     prev_scores.append(score)
    #     if len(prev_scores) > 2:
    #         prev_scores.pop(0)
    # df['score'] = scores
    print(f"scores:{df[['open', 'close', 'lastdu4','score']].tail(30)}")

    df = run_example(stock_code,df)
    # import matplotlib.pyplot as plt
    # plt.hist(df['score'], bins=20)
    # plt.show()
# 这是计算涨跌情况的代码,给ohlc进行涨跌赋值的代码,需要进行调优.目前是对上涨逻辑进行加分来判断强弱,需要优化为刚刚启动时出现high > open > last_close ,close > last_close,()close - last_close)/last_close*100 (10涨停,最强势,30开头的code 20涨停,688 30涨停),第一个大涨赋分尽量强


# 2025-08-28  20.25  20.50   -2.000000
# 2025-08-29  20.60  22.04  104.004878
# 2025-09-01  21.88  28.66   68.014519
# 2025-09-02  30.59  37.25   96.000000
# 2025-09-03  38.38  48.41   56.000000
# 2025-09-04  48.00  62.94   56.000000
# 2025-09-05  62.00  60.31   24.000000
# 2025-09-08  58.00  48.06  -37.000000
# 2025-09-09  45.00  41.00  -22.000000
# 2025-09-10  40.34  40.69  -12.000000
# 2025-09-11  39.44  39.38  -14.000000
# 2025-09-12  38.66  38.66    0.000000 
# 增加了5分,0901,0902的权重应该增加到稍微弱于0829, 0829可以在增加些提高表示度,可以也增加小规模放量拉升启动信号更安全一些,后面安全些低,但是标志性高.0903,0904就是连续拉升后放巨量反而安全度下降了.0905出现高位十字星的逃命信号这里需要巨量套利要急速降低权重,后几天的数据很清晰的表面了