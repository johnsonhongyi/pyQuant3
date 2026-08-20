# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from JSONData import tdx_data_Day as tdd
from data_utils import complete_indicators_pipeline
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger('deep_scan')
import pandas as pd
import numpy as np

codes = ['603580', '301520']
for code in codes:
    df = tdd.get_tdx_Exp_day_to_df(code, dl=250, resample='d')
    if df is None or df.empty:
        print(f"Failed to load data for {code}")
        continue
    df = complete_indicators_pipeline(df, logger, resample='d')
    print("=" * 60)
    print(f"📊 深度指标全息解构: [{code}] 数据总行数: {len(df)}")
    print("=" * 60)
    
    # 计算未来 10 日最高涨幅
    df['future_max_10d'] = df['close'].rolling(10).max().shift(-10)
    df['future_gain_10d'] = (df['future_max_10d'] - df['close']) / df['close'] * 100.0
    
    # 筛选出未来10天爆发涨幅 >= 30% 的主升浪起爆点
    blast_points = df[df['future_gain_10d'] >= 30.0]
    print(f"🔥 捕捉到未来10天涨幅 >= 30% 的主升起爆点数量: {len(blast_points)} 个")
    
    if not blast_points.empty:
        # 取爆发初期的 3 个典型 K 棒 (第一波启动、高位空中加油再突破)
        sample_indices = [0, len(blast_points)//2, len(blast_points)-1]
        sample_dates = [blast_points.index[i] for i in sample_indices if i < len(blast_points)]
        
        for dt in sample_dates:
            row = df.loc[dt]
            close_p = row['close']
            gain_10d = row.get('future_gain_10d', 0)
            print("-" * 55)
            print(f">>> 🌟 起爆节点解剖 [日期: {dt}] 收盘价: {close_p:.2f} 元 (未来10日涨幅: +{gain_10d:.1f}%)")
            
            ma5 = row.get('ma5d', 0)
            ma10 = row.get('ma10d', 0)
            ma20 = row.get('ma20d', 0)
            ma60 = row.get('ma60d', 0)
            print(f"  1. 均线与趋势结构:")
            print(f"     - 均线数值: MA5={ma5:.2f} | MA10={ma10:.2f} | MA20={ma20:.2f} | MA60={ma60:.2f}")
            print(f"     - 均线多头极强发散 (MA5 > MA10 > MA20): {ma5 > ma10 > ma20}")
            print(f"     - 收盘价站稳5日均线 (Close >= MA5): {close_p >= ma5}")
            print(f"     - 距离20日生命线乖离率: {((close_p - ma20)/max(0.01, ma20)*100):.1f}%")
            
            ch_pos = row.get('ch_pos', 0)
            ch_slope_deg = row.get('ch_slope_deg', 0)
            ch_supp_p = row.get('ch_supp_price', 0)
            ch_supp_deg = row.get('ch_supp_slope_deg', 0)
            ch_supp_days = row.get('ch_supp_days', 0)
            ch_up = row.get('ch_upper', 0)
            print(f"  2. 通道与支撑几何结构:")
            print(f"     - 通道位置 ch_pos: {ch_pos:.1f}% | 通道斜率: {ch_slope_deg:.1f}°")
            print(f"     - 上升斜率支撑线价格: {ch_supp_p:.2f} | 支撑斜率: {ch_supp_deg:.1f}° | 持续天数: {ch_supp_days}")
            print(f"     - 是否突破通道上轨: {close_p > ch_up} (Close={close_p:.2f} vs Upper={ch_up:.2f})")
            
            l1 = row.get('lastl1d', 0)
            l2 = row.get('lastl2d', 0)
            bc2 = row.get('ch_bc2', 0)
            print(f"  3. 阶梯底座与低点防线 (主力锁仓):")
            print(f"     - 昨日最低 lastl1d: {l1:.2f} vs 前日最低 lastl2d: {l2:.2f} (底座抬升: {l1 >= l2})")
            print(f"     - 底点距今天数: {bc2} 天 | 锚定底价: {row.get('ch_anchor_low_price', 0):.2f}")
            
            vol = row.get('vol', 0)
            v1 = row.get('lastv1d', 1)
            v2 = row.get('lastv2d', 1)
            obv = row.get('obv_val', 0)
            maobv = row.get('maobv', 0)
            print(f"  4. 成交量与能量潮 (资金持续性):")
            print(f"     - 成交量放量倍数 (Vol / LastV1): {(vol / max(1, v1)):.2f}x (今日量={vol:.0f}, 昨量={v1:.0f})")
            print(f"     - 前期缩量洗盘特征 (LastV1 < LastV2): {v1 < v2}")
            print(f"     - OBV能量潮多头 (OBV > MAOBV): {obv > maobv} (OBV={obv:.0f} vs MAOBV={maobv:.0f})")
            
            dif = row.get('macddif', 0)
            dea = row.get('macddea', 0)
            macd = row.get('macd', 0)
            macdlast1 = row.get('macdlast1', 0)
            print(f"  5. 动能爆发与MACD状态:")
            print(f"     - MACD DIF={dif:.2f} | DEA={dea:.2f} | 柱值={macd:.2f} (前值={macdlast1:.2f})")
            print(f"     - 水上金叉/红柱发散 (DIF > 0 且 DIF > DEA): {dif > 0 and dif > dea}")
            print(f"     - 动能二次抬头 (MACD > MACDLast1): {macd > macdlast1}")
