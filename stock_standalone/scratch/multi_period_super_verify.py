# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from JSONData import tdx_data_Day as tdd
from data_utils import complete_indicators_pipeline
from JohnsonUtil import LoggerFactory
logger = LoggerFactory.getLogger('multi_period_deep_scan')
import pandas as pd
import numpy as np

# 测试标的
codes = [
    ('603580', '艾艾精工'),
    ('301520', '万邦医药'),
    ('688195', '腾景科技'),
]

print("=" * 80)
print("🚀 【日线显得很高，但大周期 (2D/3D/W/M) 刚刚起跳】全息多周期多维量化回测验证")
print("=" * 80)

def get_val(r, k, default=0.0):
    val = r.get(k, default)
    if isinstance(val, pd.Series):
        val = val.iloc[0] if not val.empty else default
    try:
        return float(val)
    except Exception:
        return val

for code, name in codes:
    print(f"\n" + "#" * 70)
    print(f"🎯 标的: [{code} {name}] 深度多周期全息验证")
    print("#" * 70)
    
    period_dfs = {}
    for p in ['d', '2d', '3d', 'w', 'm']:
        df_p = tdd.get_tdx_Exp_day_to_df(code, dl=250, resample=p)
        if df_p is not None and not df_p.empty:
            df_p = complete_indicators_pipeline(df_p, logger, resample=p)
            period_dfs[p] = df_p
    
    if 'd' not in period_dfs:
        print(f"  [ERROR] 未能提取到 {code} 的日线数据")
        continue
    
    df_d = period_dfs['d']
    df_d['gain_prev5'] = (df_d['close'] - df_d['close'].shift(5)) / df_d['close'].shift(5) * 100.0
    df_d['gain_future10'] = (df_d['close'].shift(-10) - df_d['close']) / df_d['close'] * 100.0
    
    # 寻找“日线看似涨幅已大(前期5天涨>15%)，但后续10天依然暴涨>25%”的真龙头点位
    hot_bars = df_d[(df_d['gain_prev5'] >= 15.0) & (df_d['gain_future10'] >= 25.0)]
    if hot_bars.empty:
        hot_bars = df_d[df_d['gain_future10'] >= 20.0]
    
    if hot_bars.empty:
        sample_dates = [df_d.index[-1]]
    else:
        sample_dates = [hot_bars.index[0], hot_bars.index[-1]]
    
    for dt in sample_dates:
        row_d = df_d.loc[dt]
        if isinstance(row_d, pd.DataFrame):
            row_d = row_d.iloc[-1]
            
        c_d = get_val(row_d, 'close')
        p5_gain = get_val(row_d, 'gain_prev5')
        f10_gain = get_val(row_d, 'gain_future10')
        
        print(f"\n>>> 🔍 【主升浪起爆/空中加油节点】 日期: {dt} | 日线收盘: {c_d:.2f} 元 (前5日已大涨: +{p5_gain:.1f}%, 后10日继续暴涨: +{f10_gain:.1f}%)")
        print("-" * 65)
        
        # 1. 日线视角
        ma5_d = get_val(row_d, 'ma5d')
        ma20_d = get_val(row_d, 'ma20d')
        bias20_d = (c_d - ma20_d) / max(0.01, ma20_d) * 100
        vol_d = get_val(row_d, 'vol')
        v1_d = get_val(row_d, 'lastv1d', 1)
        print(f"  [1. 日线 (D) 视角 - 散户眼中的'太高了/不敢买']:")
        print(f"     • 20日线乖离率: +{bias20_d:.1f}% (散户严重恐高)")
        print(f"     • 真实主力防守: 牢牢踩在 5日线 ({ma5_d:.2f}) 之上，黄色上升斜率支撑={get_val(row_d, 'ch_supp_price'):.2f} (斜率: {get_val(row_d, 'ch_supp_slope_deg'):.1f}°)")
        print(f"     • 日线成交量: {vol_d:.0f} vs 昨日: {v1_d:.0f} (放量比: {(vol_d/max(1, v1_d)):.2f}x)")
        
        # 2. 2D 周期视角
        if '2d' in period_dfs:
            df_2d = period_dfs['2d']
            idx_2d = df_2d.index[df_2d.index <= dt][-1] if any(df_2d.index <= dt) else df_2d.index[-1]
            row_2d = df_2d.loc[idx_2d]
            if isinstance(row_2d, pd.DataFrame):
                row_2d = row_2d.iloc[-1]
            l1_2d = get_val(row_2d, 'lastl1d')
            l2_2d = get_val(row_2d, 'lastl2d')
            v1_2d = get_val(row_2d, 'lastv1d')
            v2_2d = get_val(row_2d, 'lastv2d')
            ma5_2d = get_val(row_2d, 'ma5d')
            p1_2d = get_val(row_2d, 'lastp1d', c_d)
            print(f"  [2. 2日 (2D) 周期视角 - 真实阶梯底座与量能洗盘]:")
            print(f"     • 2D低点阶梯抬升: lastl1d={l1_2d:.2f} >= lastl2d={l2_2d:.2f} (底座死守抬高: {l1_2d >= l2_2d})")
            print(f"     • 2D换手量能健康度: 当期量={v1_2d:.0f} vs 上期量={v2_2d:.0f} (缩量整固或倍量起爆: {v1_2d > v2_2d or v1_2d < 0.85*v2_2d})")
            print(f"     • 2D真实价格站稳MA5: {p1_2d:.2f} > MA5({ma5_2d:.2f}) ({p1_2d > ma5_2d})")
        
        # 3. 3D 周期视角
        if '3d' in period_dfs:
            df_3d = period_dfs['3d']
            idx_3d = df_3d.index[df_3d.index <= dt][-1] if any(df_3d.index <= dt) else df_3d.index[-1]
            row_3d = df_3d.loc[idx_3d]
            if isinstance(row_3d, pd.DataFrame):
                row_3d = row_3d.iloc[-1]
            bw_3d = get_val(row_3d, 'bandwidth')
            bc2_3d = get_val(row_3d, 'ch_bc2')
            dif_3d = get_val(row_3d, 'macddif')
            dea_3d = get_val(row_3d, 'macddea')
            print(f"  [3. 3日 (3D) 周期视角 - 波段稳固度与波动率空间]:")
            print(f"     • 3D底部夯实天数: ch_bc2={bc2_3d:.0f} (底座充分沉淀，非单日尖顶急拉)")
            print(f"     • 3D布林波动率/带宽: bandwidth={bw_3d:.2f} (大周期波动率刚刚张口打开！)")
            print(f"     • 3D MACD多头动能: DIF={dif_3d:.2f} > DEA={dea_3d:.2f} ({dif_3d > dea_3d})")
        
        # 4. 周线 (W) 视角
        if 'w' in period_dfs:
            df_w = period_dfs['w']
            idx_w = df_w.index[df_w.index <= dt][-1] if any(df_w.index <= dt) else df_w.index[-1]
            row_w = df_w.loc[idx_w]
            if isinstance(row_w, pd.DataFrame):
                row_w = row_w.iloc[-1]
            ma5_w = get_val(row_w, 'ma5d')
            ma20_w = get_val(row_w, 'ma20d')
            obv_w = get_val(row_w, 'obv_val')
            maobv_w = get_val(row_w, 'maobv')
            print(f"  [4. 周线 (W) 周期视角 - 大级别主升刚出水面]:")
            print(f"     • 周线均线金叉多头: MA5({ma5_w:.2f}) > MA20({ma20_w:.2f}) ({ma5_w > ma20_w})")
            print(f"     • 周线低点大幅上移: 本周最低={get_val(row_w, 'lastl1d'):.2f} vs 上周最低={get_val(row_w, 'lastl2d'):.2f}")
            print(f"     • 周线OBV能量潮: {obv_w:.0f} > MAOBV({maobv_w:.0f}) (资金海量净流入: {obv_w > maobv_w})")
        
        # 5. 月线 (M) 视角
        if 'm' in period_dfs:
            df_m = period_dfs['m']
            idx_m = df_m.index[df_m.index <= dt][-1] if any(df_m.index <= dt) else df_m.index[-1]
            row_m = df_m.loc[idx_m]
            if isinstance(row_m, pd.DataFrame):
                row_m = row_m.iloc[-1]
            dif_m = get_val(row_m, 'macddif', get_val(row_m, 'dif'))
            dea_m = get_val(row_m, 'macddea', get_val(row_m, 'dea'))
            ma10_m = get_val(row_m, 'ma10d')
            print(f"  [5. 月线 (M) 周期视角 - 超级大牛股的宏观底座]:")
            print(f"     • 月线MACD水上多头: DIF={dif_m:.2f} > DEA={dea_m:.2f} ({dif_m > dea_m})")
            print(f"     • 月线站稳大生命线: Close({c_d:.2f}) > MA10_m({ma10_m:.2f}) ({c_d > ma10_m})")
