import os
import time
import gc
import traceback
from typing import Any, Optional, Union, Dict, List, Callable
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
pd = cct.LazyModule('pandas')
np = cct.LazyModule('numpy')
from JohnsonUtil.commonTips import timed_ctx
from JohnsonUtil import LoggerFactory
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from tdx_utils import clean_bad_columns, sanitize, clean_expired_tdx_file
from db_utils import get_indb_df
import re
winlimit = cct.winlimit
loop_counter_limit = cct.loop_counter_limit
START_INIT = 0
PIPE_NAME = r"\\.\pipe\my_named_pipe"
PIPE_NAME_TK = r"\\.\pipe\instock_tk_pipe"
logger = LoggerFactory.getLogger()

def calc_cycle_stage_vect(df: pd.DataFrame) -> pd.Series:
    """
    矢量化计算个股所处的周期阶段 (增强版)
    1: 筑底/启动 (Bottom/Start) - 站上中长线，初次走强
    2: 主升/健康 (Rising/Healthy) - 均线顺排，斜率向上，量能配合
    3: 脉冲/扩张 (Exhaustion/Overextended) - 乖离过大或破上轨 (风险区)
    4: 见顶/回落 (Top/Falling) - 均线死叉或价格走弱 (减仓/退出区)
    """
    n = len(df)
    if n == 0: return pd.Series([], dtype=int)

    # 提取必要数据
    close = df['close'].values.astype('float32')
    ma5 = df['ma5d'].values.astype('float32') if 'ma5d' in df.columns else np.zeros(n)
    ma10 = df['ma10d'].values.astype('float32') if 'ma10d' in df.columns else np.zeros(n)
    ma20 = df['ma20d'].values.astype('float32') if 'ma20d' in df.columns else np.zeros(n)
    ma60 = df['ma60d'].values.astype('float32') if 'ma60d' in df.columns else np.zeros(n)
    upper = df['upper1'].values.astype('float32') if 'upper1' in df.columns else np.zeros(n)
    
    # [NEW] 引入量能确认与多日趋势 (cct.compute_lastdays)
    lookback = getattr(cct, 'compute_lastdays', 5)
    
    # [FIX] 优先使用原始成交量 vol，因为 volume 可能会被转换为虚拟量比信号
    volume = df['vol'].values.astype('float32') if 'vol' in df.columns else df['volume'].values.astype('float32')
    
    # 计算多日成交量均值 (如果 df 是历史序列)
    # [OPTIMIZE] 如果 df 中已经有 last6vol (或类似预计算列)，则直接使用
    if 'last6vol' in df.columns:
        vol_ma = df['last6vol'].values.astype('float32')
        vol_ratio = volume / np.where(vol_ma > 0, vol_ma, 1)
    elif n >= lookback:
        vol_ma = pd.Series(volume).rolling(window=lookback, min_periods=1).mean().values
        vol_ratio = volume / np.where(vol_ma > 0, vol_ma, 1)
    elif 'lastv1d' in df.columns:
        # [WIDE-FORMAT] 处理单行数据，包含历史量列 lastv1d, lastv2d...
        # 尝试计算多日均量
        vol_cols = [f'lastv{i}d' for i in range(1, lookback + 1) if f'lastv{i}d' in df.columns]
        if vol_cols:
            vol_ma = df[vol_cols].mean(axis=1).values.astype('float32')
            vol_ratio = volume / np.where(vol_ma > 0, vol_ma, 1)
        else:
            lastv1 = df['lastv1d'].values.astype('float32')
            vol_ratio = volume / np.where(lastv1 > 0, lastv1, 1)
    else:
        vol_ratio = np.ones(n)

    # 计算 MA20 斜率
    ma20_slope = np.zeros(n)
    if n >= lookback:
        ma20_series = pd.Series(ma20)
        ma20_slope = (ma20_series - ma20_series.shift(lookback)).replace(np.nan, 0).values
    elif f'ma20{lookback}d' in df.columns:
        # [WIDE-FORMAT] 使用历史 MA20 列计算斜率
        ma20_slope = (ma20 - df[f'ma20{lookback}d'].values.astype('float32'))
    elif 'ma201d' in df.columns:
        ma20_slope = (ma20 - df['ma201d'].values.astype('float32'))

    stages = np.full(n, 2, dtype=int) # 默认设为 Stage 2

    # 1. Stage 3: 脉冲扩张 (最高优先级 - 风险拦截)
    bias5 = (close - ma5) / np.where(ma5 > 0, ma5, 1)
    mask_stage3 = (upper > 0) & (close > upper * 1.005) # 突破布林上轨
    mask_stage3 |= (bias5 > 0.08) # 5日乖离率 > 8%
    stages[mask_stage3] = 3

    # 2. Stage 4: 见顶回落 (次高优先级)
    # 条件：跌破 MA5 且 MA5 下降，或 破 MA10
    mask_stage4 = (ma5 > 0) & (close < ma5 * 0.992)
    mask_stage4 |= (ma10 > 0) & (close < ma10 * 0.985)
    # 如果 MA20 斜率为负且价格在 MA20 下方，也是 Stage 4
    mask_stage4 |= (ma20 > 0) & (ma20_slope < 0) & (close < ma20)
    stages[mask_stage4] = 4

    # 3. Stage 1: 筑底启动
    # 条件：靠近 MA60 且 站上 MA20，且成交量有放大迹象 (vol_ratio > 1.1)
    is_near_ma60 = (ma60 > 0) & (np.abs(close - ma60) / ma60 < 0.03)
    is_initial_cross = (ma20 > 0) & (close > ma20) & (ma5 < ma20 * 1.02)
    mask_stage1 = (is_near_ma60 | is_initial_cross) & (vol_ratio > 1.1) & (stages != 4) & (stages != 3)
    stages[mask_stage1] = 1

    # 额外检查：空头排列
    # 如果均线系统整体向下，即使价格暂时没破位也要警惕
    mask_short_trend = (ma5 > 0) & (ma10 > ma5) & (ma20 > ma10)
    stages[mask_short_trend & (stages != 3)] = 4

    return pd.Series(stages, index=df.index)

def calc_compute_volume(top_all: pd.DataFrame, logger: Any, resample: str = 'd', virtual: bool = True) -> pd.Series:
    """计算成交量（量比或原始量）"""
    # 逻辑置换：优先使用 'vol'(镜像原始量) 进行计算。

    vol_data = top_all['vol'] if 'vol' in top_all.columns else top_all['volume']
    
    ratio_t = cct.get_work_time_ratio(resample=resample)
    # logger.info(f'ratio_t: {round(ratio_t, 2)}')

    if virtual:
        # 为了防止盘后数据 (vol == lastv1d) 在开盘初期由于 ratio_t 极小而导致虚拟成交量暴涨
        # 对 stale 数据不应用 ratio_t 除法
        l6vol = top_all['last6vol'].replace(0, np.nan)
        v_ratio = vol_data / l6vol
        
        if 'lastv1d' in top_all.columns and ratio_t < 1.0:
            # 只有当 vol 不同于昨日全天量时，才认定为今日有实时变动的数据
            mask_active = (vol_data != top_all['lastv1d']) & (vol_data > 0)
            
            # 使用 pandas 矢量化操作，避免 np.where 转换成 ndarray
            v_ratio = v_ratio.copy()
            # 活跃股票进行虚拟量比放大
            v_ratio[mask_active] = v_ratio[mask_active] / ratio_t
        else:
            # 盘后或缺少对比列时，按照当前时间比例正常缩放
            v_ratio = v_ratio / (ratio_t if ratio_t > 0 else 1.0)
            
        return v_ratio.fillna(0).round(1)
    else:
        # 原始量还原 = 虚拟量比 * last6vol * ratio_t
        return (top_all['volume'] * top_all.get('last6vol', 1) * ratio_t).round(1)


def build_hma_and_trendscore(
    df,
    close_col='close',
    ma_map=None,
    strong_cols=None,
    win_col='win',
    max_days=cct.compute_lastdays,          # 最近多少天成交量参与
    lastv_prefix='lastv',# 成交量列前缀，如 lastv1d,lastv2d...
    invalid_val=-101.0,
    status_callback=None
    ):
    """
    极限向量化生成：
    - Hma5/10/20/60
    - TrendS (0~100)
    - Volume factor from last N days (max_days)
    - Rank 排序，避免一堆满分100
    """

    # ---------- 1️⃣ 读取状态 ----------
    # status = None
    # if callable(status_callback):
    #     try:
    #         status = status_callback()
    #     except Exception as e:
    #         logger.warning(f"status_callback error: {e}")

    n = len(df)

    if ma_map is None:
        ma_map = {5:'ma5d',10:'ma10d',20:'ma20d',60:'ma60d'}
    if strong_cols is None:
        strong_cols = ['sum_perc','slope','vol_ratio','power_idx']

    # ---------- 1️⃣ HMA & TrendS ----------
    close = df[close_col].values.astype('float32')
    score = np.zeros(n, dtype='float32')
    weight_sum = 0.0
    weights = {5:0.35,10:0.30,20:0.20,60:0.15}

    for period, ma_col in ma_map.items():
        hma_col = f'Hma{period}d'
        if ma_col not in df.columns:
            df[hma_col] = invalid_val
            continue

        ma = df[ma_col].values.astype('float32')
        valid = ma > 0
        hma = np.full(n, invalid_val, dtype='float32')
        hma[valid] = (close[valid] - ma[valid]) / (ma[valid]+0.01) * 100
        df[hma_col] = np.round(hma, 1)

        w = weights.get(period, 0)
        if w > 0:
            score[valid] += np.clip(hma[valid], -10, 10) * w
            weight_sum += w

    if weight_sum > 0:
        trend = (score / weight_sum + 10) * 5
        df['TrendS'] = np.clip(trend, 0, 100).round(1)
    else:
        df['TrendS'] = 0.0

    # ---------- 2️⃣ 强势因子 ----------
    strong_score = np.zeros(n, dtype='float32')
    for col in strong_cols:
        if col in df.columns:
            arr = df[col].fillna(0).values.astype('float32')
            arr = (arr - arr.min()) / (arr.ptp() + 1e-6)
            strong_score += arr
    strong_score /= max(1, len([c for c in strong_cols if c in df.columns]))

    # ---------- 3️⃣ 连阳加权 ----------
    if win_col in df.columns:
        win_vals = df[win_col].fillna(0).astype('float32')
    else:
        win_vals = np.zeros(n, dtype='float32')


    if get_status(status_callback):
        # ---------- 4️⃣ 最近 N 天成交量因子 ----------
        vol_cols = [f'{lastv_prefix}{i}d' for i in range(1, max_days+1)]
        vol_cols = [c for c in vol_cols if c in df.columns]

        if vol_cols:
            vol_arr = df[vol_cols].fillna(0).values.astype('float32')
            # 绝对量级压缩
            vol_max = np.log1p(vol_arr.max(axis=1))
            # 相对放量
            vol_mean = vol_arr.mean(axis=1)
            vol_ratio = np.clip(vol_arr[:,0] / (vol_mean+1e-6), 0.5, 5.0)
            # 连续放量天数占比
            vol_continuity = (vol_arr > vol_mean[:,None]).sum(axis=1) / vol_arr.shape[1]
            volume_factor = vol_max * vol_ratio * (1 + vol_continuity)
        else:
            volume_factor = np.zeros(n, dtype='float32')

    # ---------- 5️⃣ 最终排序 Rank ----------
        sort_score = df['TrendS'].values * 1000 + strong_score*10 + win_vals*1.0 + volume_factor*50
    else:
        sort_score = df['TrendS'].values * 1000 + strong_score*10 + win_vals*1.0

    df['Rank'] = (-sort_score).argsort().argsort() + 1

    # ---------- 6️⃣ 最后统一格式化 .1f ----------
    # for col in [f'Hma{p}d' for p in ma_map.keys()] + ['TrendS']:
    #     if col in df.columns:
    #         df[col] = np.round(df[col].values, 1)
    for col in ['Hma5d','Hma10d','Hma20d','Hma60d','TrendS']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.1f}")

    return df


def build_hma_and_trendscore_noVol(
    df,
    close_col='close',
    ma_map=None,
    invalid_val=-101.0,
    strong_cols=None,
    win_col='win',
):
    """
    极限向量化生成：
    - Hma5/10/20/60
    - TrendS (0~100)
    - Rank 排队，避免一堆满分100

    df 已包含 close 和 maXd
    最终输出列统一保留 .1f 字符串格式
    """

    if ma_map is None:
        ma_map = {5:'ma5d',10:'ma10d',20:'ma20d',60:'ma60d'}
    if strong_cols is None:
        strong_cols = ['sum_perc','slope','vol_ratio','power_idx']

    weights = {5:0.35,10:0.30,20:0.20,60:0.15}
    n = len(df)
    close = df[close_col].values.astype('float32')
    score = np.zeros(n, dtype='float32')
    weight_sum = 0.0

    # -------------------------
    # 1️⃣ 计算 Hma 并累加 TrendS
    # -------------------------
    for period, ma_col in ma_map.items():
        hma_col = f'Hma{period}d'
        if ma_col not in df.columns:
            df[hma_col] = invalid_val
            continue

        ma = df[ma_col].values.astype('float32')
        valid = ma > 0
        hma = np.full(n, invalid_val, dtype='float32')
        hma[valid] = (close[valid] - ma[valid]) / (ma[valid] + 0.01) * 100

        # 不转字符串，保持浮点
        df[hma_col] = np.round(hma, 1)

        # TrendScore 累加
        w = weights.get(period)
        if w is not None:
            score[valid] += np.clip(hma[valid], -10, 10) * w
            weight_sum += w

    # -------------------------
    # 2️⃣ TrendS归一化
    # -------------------------
    if weight_sum > 0:
        trend = (score / weight_sum + 10) * 5
        df['TrendS'] = np.clip(trend, 0, 100)
    else:
        df['TrendS'] = 0.0

    # -------------------------
    # 3️⃣ 强势因子辅助打散满分
    # -------------------------
    strong_score = np.zeros(n, dtype='float32')
    valid_cols = [c for c in strong_cols if c in df.columns]
    for col in valid_cols:
        arr = df[col].fillna(0).values.astype('float32')
        arr = (arr - arr.min()) / (arr.ptp() + 1e-6)
        strong_score += arr
    if valid_cols:
        strong_score /= len(valid_cols)

    # -------------------------
    # 4️⃣ 连阳加权
    # -------------------------
    if win_col in df.columns:
        win_vals = df[win_col].fillna(0).astype('float32')
    else:
        win_vals = np.zeros(n, dtype='float32')

    # -------------------------
    # 5️⃣ 排序 Rank（整数/浮点，保持性能）
    # -------------------------
    sort_score = df['TrendS'].values * 1000 + strong_score*10 + win_vals*1.0
    df['Rank'] = (-sort_score).argsort().argsort() + 1

    # -------------------------
    # 6️⃣ 最终输出格式化 .1f（展示用）
    # -------------------------
    for col in ['Hma5d','Hma10d','Hma20d','Hma60d','TrendS']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.1f}")

    return df

def format_floats(df):
    # 找出 float 列
    float_cols = df.select_dtypes(include='float').columns
    # 仅对 float 列 apply 格式化，其他列保持不变
    df_copy = df.copy()
    # df_copy[float_cols] = df_copy[float_cols].applymap(lambda x: f"{x:.2f}")
    df_copy[float_cols] = df_copy[float_cols].round(2)
    return df_copy

# for col, dtype in top_all.dtypes.items():print(col, dtype)
# formatted_rows = format_floats(top_all).astype(str)
# for row in formatted_rows.head(5).itertuples(index=False):
#     print(", ".join(row))

def calc_indicators(top_all: pd.DataFrame, logger: Any, resample: str) -> pd.DataFrame:
    """指标计算"""
    # 确保 vol 列镜像原始成交量。
    # 判定准则：如果 vol 列不存在，或者 volume 列显示出明显的原始成交量特征（通常远大于100）

    if 'vol' not in top_all.columns or (top_all['volume'] > 5000).any():
        top_all['vol'] = top_all['volume'] 
        
    top_all['amount'] = top_all['vol'] * top_all['close']
    # 这里的 volume 将被更新为虚拟量比信号强度
    top_all['volume'] = calc_compute_volume(top_all, logger, resample=resample, virtual=True)
    
    # --- [NEW] 注入 win_upper 实时指标 (针对压力位1和2) ---
    max_days = cct.compute_lastdays
    N_count = len(top_all)
    
    # 初始化默认值，避免后续引用报 KeyError
    if 'win_upper1' not in top_all.columns:
        top_all['win_upper1'] = 0
    if 'win_upper2' not in top_all.columns:
        top_all['win_upper2'] = 0
    
    # --- [NEW] 注入 cycle_stage (周期阶段) ---
    try:
        top_all['cycle_stage'] = calc_cycle_stage_vect(top_all)
    except Exception as e:
        logger.warning(f"calc_cycle_stage_vect failed: {e}")

    if N_count > 0:
        try:
            # 这里的 ma51d, high41 已经在 process_merged_sina_with_history 后存在
            if 'upper1' in top_all.columns:
                top_all = strong_momentum_large_cycle_vect_consecutive_above(
                    top_all, 'close', 'upper1', 'ma51d', 'high41', max_days
                )
            if 'upper2' in top_all.columns:
                top_all = strong_momentum_large_cycle_vect_consecutive_above(
                    top_all, 'close', 'upper2', 'ma51d', 'high41', max_days
                )
        except Exception as e:
            logger.warning(f"calc_indicators win_upper failed: {e}")

    # 同步到 ratio 列，确保兼容性 是换手率,不能同步Volume
    # top_all['ratio'] = top_all['volume']
    now_time = cct.get_now_time_int()
    lastbuy_safe = top_all['lastbuy'].mask(top_all['lastbuy'] == 0, top_all['llastp'])
    
    if cct.get_trade_date_status():
        logger.info(f'lastbuy :{"lastbuy" in top_all.columns}')
        if 'lastbuy' in top_all.columns:
            if 915 < now_time < 930:
                top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)

            elif 926 < now_time < 1455:
                # top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)

                top_all['dff'] = ((top_all['buy'] - lastbuy_safe) / lastbuy_safe * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            else:
                # top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                # top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)

                # top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                top_all['dff'] = ((top_all['buy'] - lastbuy_safe) / lastbuy_safe * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
        else:
            top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
            top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    else:
        top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
        top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    
    top_all['dff'].replace([np.inf, -np.inf], np.nan, inplace=True)
    top_all['dff'].fillna(0, inplace=True)

    return top_all.sort_values(by=['dff','percent','volume','ratio','couts'], ascending=[0,0,0,1,1])

def evaluate_realtime_signal_tick(rt_tick, daily_feat, mode='A'):
    """
    实时计算单个标的的交易信号
    :param rt_tick: 字典，包含当前实时行情 {'open', 'close', 'high', 'low', 'amount'}
    :param daily_feat: 字典，generate_df_vect_daily_features 返回的 1d 特征 (list中的第一个元素)
    :param mode: 'A' 强势优先, 'B' 风控优先
    :return: (current_state, trade_signal)
    """
        
    """
    自适应版本：自动处理数据类型
    """
    # --- 1. 类型自适应处理 ---
    # 如果 rt_tick 是 DataFrame 或 Series，提取标量值
    def get_val(obj, key):
        val = obj[key]
        # 如果是 Series 或数组，取第一个值 (.item() 或 .iloc[0])
        return val.iloc[0] if hasattr(val, 'iloc') else val

    # 映射字段（适配你的 sina 结构）
    curr_o = float(get_val(rt_tick, 'open'))
    curr_c = float(get_val(rt_tick, 'now'))   # 对应你 sina 里的 now
    curr_l = float(get_val(rt_tick, 'low'))
    # 优先取 amount，没有则取 volume
    curr_a = float(get_val(rt_tick, 'volume'))


    # 1. 数据映射 (实时数据与历史特征)

    # curr_o = rt_tick['open']
    # curr_c = rt_tick['close']
    # curr_l = rt_tick['low']
    # curr_a = rt_tick['volume']
    
    # 历史特征 (1d 代表昨天)
    upper_1d = daily_feat['upper1']
    close_1d = daily_feat['lastp1d']
    amount_1d = daily_feat['lastv1d']
    eval_val = daily_feat['eval1d']
    eval_1d = int(eval_val) if not pd.isna(eval_val) else 9
    ma10d_curr = daily_feat['ma51d'] # 假设实时判断的生命线使用昨日MA5作为参考

    if upper_1d <= 0:
        return 9, 5

    # 计算虚拟估算成交量 (将当前累积量映射到全天)
    ratio_t = cct.get_work_time_ratio()
    virtual_a = curr_a / ratio_t if ratio_t > 0 else curr_a

    # 2. 条件判定 (基于实时 Tick)
    # 使用估算的全天成交量与昨日全天量进行对比
    cond_trend_start = (curr_c > upper_1d) and (close_1d <= upper_1d) and (virtual_a > amount_1d * 1.1)
    cond_trend_continue = (curr_c > upper_1d) and (close_1d > upper_1d)
    cond_pullback = (curr_c < close_1d) and (curr_l >= ma10d_curr) and (virtual_a < amount_1d)
    cond_bear = (curr_c < ma10d_curr)

    # 3. 状态转移逻辑 (EVAL_STATE)
    curr_state = 9 # 默认值
    
    if mode == 'A': # 强势优先逻辑
        if cond_trend_start:
            curr_state = 1
        elif cond_bear:
            curr_state = 9
        elif cond_trend_continue:
            curr_state = 2
        elif cond_pullback and eval_1d in [2, 3]:
            curr_state = 3
        elif eval_1d == 3 and curr_l >= ma10d_curr:
            curr_state = 2
        else:
            curr_state = eval_1d # 维持昨日状态
            
    elif mode == 'B': # 风控优先逻辑
        if cond_bear:
            curr_state = 9
        elif cond_trend_start:
            curr_state = 1
        elif cond_trend_continue:
            curr_state = 2
        elif cond_pullback and eval_1d in [2, 3]:
            curr_state = 3
        elif eval_1d == 3 and curr_l >= ma10d_curr:
            curr_state = 2
        else:
            curr_state = eval_1d

    # 4. 交易信号推演 (trade_signal)
    # EVAL_STATE: 9=空头, 1=启动, 2=主升, 3=回撤
    # trade_signal: 5=HOLD, 1=买一, 2=买二, -1=卖出
    trade_signal = 5
    
    # 买一：从启动(1)确认转入主升(2)，且开盘未大幅跳空
    if eval_1d == 1 and curr_state == 2 and curr_o <= close_1d * 1.03:
        trade_signal = 1
    # 买二：从主升(2)进入缩量回撤(3)
    elif eval_1d == 2 and curr_state == 3:
        trade_signal = 2
    # 卖出：持有状态(1,2,3)下触发破位(9)
    elif eval_1d in [1, 2, 3] and curr_state == 9:
        trade_signal = -1

    return curr_state, trade_signal

def generate_simple_vect_features(df):
    """
    极简矢量化版本
    仅提取最新日的: open, close, high, low, nlow, nhigh 和 过去6日均量 last6vol
    """
    # 确保索引排序正确
    df = df.sort_index(level=[0, 1])
    
    # 1. 提取最新一行的原始数据
    # last() 会自动按第一个索引(code)分组并取每个代码的最后一行
    feat_df = df.groupby(level=0)[['open', 'close', 'high', 'low', 'nlow', 'nhigh']].last()
    # 2. 计算过去6日均量 (包含当日)
    # rolling(6) 计算滚动均值，然后再取最后一行
    vol_col = 'vol' if 'vol' in df.columns else 'volume'
    last6vol = df.groupby(level=0)[vol_col].rolling(window=6, min_periods=1).mean()
    
    # 因为 rolling 会增加一层索引，我们需要对齐后提取最后一行
    feat_df['last6vol'] = last6vol.groupby(level=0).last()

    # 3. 转换为你需要的字典列表格式
    # reset_index() 将 code 变成一列，to_dict('records') 转为字典列表
    return feat_df.reset_index().to_dict('records')
    


def send_code_via_pipe(code: Union[str, Dict[str, Any]], logger: Any,pipe_name: str=PIPE_NAME) -> bool:
    """通过命名管道发送股票代码"""
    import win32file
    import json
    if isinstance(code, dict):
        code = json.dumps(code, ensure_ascii=False)
    try:
        handle = win32file.CreateFile(
            pipe_name, win32file.GENERIC_WRITE, 0, None,
            win32file.OPEN_EXISTING, 0, None
        )
        win32file.WriteFile(handle, code.encode("utf-8"))
        win32file.CloseHandle(handle)
        return True
    except Exception as e:
        logger.info(f"发送数据到管道失败: {e}")
    return False


def process_merged_sina_signal_eval(df, mode='A'):
    """
    直接处理已经合并了历史特征和实时行情的 DataFrame
    df 包含: 
      实时列: open, now, high, low, volume
      历史列: upper, lastp1d (昨日收), lastv1d (昨日量), ma5d (或ma10d), EVAL_STATE (昨日状态)
    """
    # 逻辑置换：vol 是累积原始成交量，volume 此时可能是已经计算好的量比
    curr_vol_raw = df['vol'] if 'vol' in df.columns else df['volume']
    ratio_t = cct.get_work_time_ratio()
    virtual_a = curr_vol_raw / ratio_t if ratio_t > 0 else curr_vol_raw
    
    # 历史参考值
    upper_1d = df['upper']
    close_1d = df['lastp1d']
    amount_1d = df['lastv1d']
    eval_1d = df['EVAL_STATE'].fillna(9).astype(int)
    # 1. 提取当前价格
    curr_c = df['now'] if 'now' in df.columns else df['trade']
    curr_l = df['low']
    curr_o = df['open']
    ma_ref = df['ma5d'] # 假设 ma5d 是你的生命线

    # 2. 判定条件 (矢量化)
    cond_trend_start = (curr_c > upper_1d) & (close_1d <= upper_1d) & (virtual_a > amount_1d * 1.1)
    cond_trend_continue = (curr_c > upper_1d) & (close_1d > upper_1d)
    cond_pullback = (curr_c < close_1d) & (curr_l >= ma_ref) & (virtual_a < amount_1d)
    cond_bear = (curr_c < ma_ref)

    # 3. 状态转移逻辑 (EVAL_STATE)
    curr_state = eval_1d.copy()

    if mode == 'A':
        # 强势优先：先判启动，再判趋势，最后判破位
        curr_state = np.where(cond_trend_start, 1, curr_state)
        curr_state = np.where((curr_state != 1) & cond_trend_continue, 2, curr_state)
        
        # 回撤逻辑：昨日是2或3，且今日缩量回调不破位
        mask_pb = (eval_1d.isin([2, 3])) & cond_pullback
        curr_state = np.where(mask_pb, 3, curr_state)
        
        # 修复逻辑：昨日是3，今日回升不破位
        mask_fix = (eval_1d == 3) & (curr_l >= ma_ref) & (~cond_pullback)
        curr_state = np.where(mask_fix, 2, curr_state)
        
        # 破位逻辑：最后判定，具有最高优先级（风控）
        curr_state = np.where(cond_bear, 9, curr_state)

    # 4. 交易信号推演 (trade_signal)
    df['trade_signal'] = 5  # 默认 HOLD
    
    # 买一：启动转主升 (1 -> 2)
    df.loc[(eval_1d == 1) & (curr_state == 2) & (curr_o <= close_1d * 1.03), 'trade_signal'] = 1
    # 买二：主升转回撤 (2 -> 3)
    df.loc[(eval_1d == 2) & (curr_state == 3), 'trade_signal'] = 2
    # 卖出：持仓转空头 (1,2,3 -> 9)
    df.loc[(eval_1d.isin([1, 2, 3])) & (curr_state == 9), 'trade_signal'] = -1

    df['curr_eval'] = curr_state
    
    return df
    # return df[['name', 'now', 'curr_eval', 'trade_signal']]


def process_merged_sina_with_history(df, mode='A'):
    """
    结合多日历史背景（eval1d, eval2d, signal1d等）给出精准实时信号
    """
    # 1. 提取基础数据
    curr_c = df['now']
    curr_o = df['open']
    curr_l = df['low']
    curr_a = df['volume']
    
    # 2. 提取历史特征 (来自 all_features 合并进来的列)
    upper_1d = df['upper1']
    close_1d = df['lastp1d']
    amount_1d = df['lastv1d']
    eval_1d   = df['eval1d'].fillna(9).astype(int)   # 昨天状态
    eval_2d   = df['eval2d'].fillna(9).astype(int)   # 前天状态
    signal_1d = df['signal1d'].fillna(5).astype(int) # 昨天产生的信号
    ma_ref    = df['ma51d']                # 支撑位

    # 3. 核心条件判定
    # 启动：价格突围 + 放量
    cond_trend_start = (curr_c > upper_1d) & (close_1d <= upper_1d) & (curr_a > 1.1)
    # 持续：维持在压力位上方
    cond_trend_continue = (curr_c > upper_1d) & (close_1d > upper_1d)
    # 回撤：缩量且守住均线
    cond_pullback = (curr_c < close_1d) & (curr_l >= ma_ref) & (curr_a < amount_1d)
    # 破位：跌破均线
    cond_bear = (curr_c < ma_ref)

    # 4. 实时状态推演 (EVAL_STATE)
    curr_eval = eval_1d.copy()
    
    # 状态更新逻辑
    curr_eval = np.where(cond_trend_start, 1, curr_eval)
    curr_eval = np.where((curr_eval != 1) & cond_trend_continue, 2, curr_eval)
    curr_eval = np.where((eval_1d.isin([2, 3])) & cond_pullback, 3, curr_eval)
    # 修复：昨日回撤，今日企稳
    curr_eval = np.where((eval_1d == 3) & (curr_l >= ma_ref) & (curr_c >= close_1d), 2, curr_eval)
    # 风控破位
    curr_eval = np.where(cond_bear, 9, curr_eval)

    # 5. 结合历史深度给出交易信号 (trade_signal)
    # 5=HOLD, 1=买一, 2=买二, -1=卖出
    df['trade_signal'] = 5 

    # --- 买一逻辑：昨日启动(1) + 今日确认主升(2) + 过滤高开 ---
    mask_buy1 = (eval_1d == 1) & (curr_eval == 2) & (curr_o <= close_1d * 1.03)
    df.loc[mask_buy1, 'trade_signal'] = 1

    # --- 买二逻辑：昨日主升(2) + 今日初次缩量回撤(3) ---
    # 结合 eval2d 确保不是连续下跌，而是主升后的首次回撤
    mask_buy2 = (eval_1d == 2) & (curr_eval == 3) & (eval_2d == 2)
    df.loc[mask_buy2, 'trade_signal'] = 2

    # --- 卖出逻辑：有持仓(1,2,3) + 今日转空头(9) ---
    mask_sell = (eval_1d.isin([1, 2, 3])) & (curr_eval == 9)
    df.loc[mask_sell, 'trade_signal'] = -1
    
    # --- 修正：如果昨天已经是买一信号，且今天状态依然健康，则维持 HOLD ---
    # 避免重复发出买入指令
    mask_already_in = (signal_1d == 1) & (curr_eval == 2)
    df.loc[mask_already_in, 'trade_signal'] = 5

    df['curr_eval'] = curr_eval
    return df
    # return df[['name', 'now', 'curr_eval', 'trade_signal']]

def is_strict_consecutive_up(row, window):
    for i in range(1, window):
        if not (
            row[f'lastp{i}d'] > row[f'lastp{i+1}d'] and
            row[f'lasth{i}d'] > row[f'lasth{i+1}d'] and
            row[f'lastl{i}d'] > row[f'lastl{i+1}d']
        ):
            return False
    return True


def check_real_time(df, codes):
    """
    df: vect_daily_t 转成 DataFrame
    codes: 要检查的股票列表
    """
    df_check = df.loc[df['code'].isin(codes)].copy()
    
    for _, row in df_check.iterrows():
        ohlc_same_as_last1d = (
            row['open'] == row.get('lasto1d', row['open']) and
            row['low'] == row.get('lastl1d', row['low']) and
            row['high'] == row.get('lasth1d', row['high']) and
            row['close'] == row.get('lastp1d', row['close'])
        )
        logger.debug(f"{row['code']} - 实盘模式: {not ohlc_same_as_last1d}, ohlc_same_as_last1d={ohlc_same_as_last1d}")




def scoring_momentum_pullback_system_top(df: pd.DataFrame, max_days: int = 9):
    N = len(df)
    if N == 0: return df

    def get_mat(prefix):
        if prefix in ['upper', 'high4', 'ma5', 'ma10']:
            cols = [f"{prefix}{i}" for i in range(0, max_days + 1)]
        else:
            cols = [f"{prefix}{i}d" for i in range(0, max_days + 1)]
        mat = np.zeros((N, max_days + 1))
        for idx, col in enumerate(cols):
            if col in df.columns:
                mat[:, idx] = df[col].values
        return mat

    C, O, L, H, U = get_mat('lastp'), get_mat('lasto'), get_mat('lastl'), get_mat('lasth'), get_mat('upper')
    P, M5, M10, H4 = get_mat('per'), get_mat('ma5'), get_mat('ma10'), get_mat('high4')

    scores = np.zeros(N)

    # --- 1. 大阳动力衰减 (拉开天数梯度) ---
    is_big_up = P[:, 1:9] >= 5.0
    # 衰减权重：1d=1.0, 2d=0.88, 3d=0.76... 逐级减少
    decay_weights = np.linspace(1.0, 0.2, 8) 
    
    big_up_bonus = np.zeros(N)
    for i in range(1, 9):
        has_big_up = is_big_up[:, i-1]
        support_price = C[:, i]
        is_stable = np.min(C[:, 0:i], axis=1) >= support_price
        
        # 基础分随天数递减
        base_val = 40 * decay_weights[i-1]
        
        # 2. 增加【强度梯度】：站上 Upper 多少？
        # 站上 1% 给 2分，最高 10分
        upper_dist = (C[:, 0] - U[:, 0]) / U[:, 0] * 100
        upper_linear_bonus = np.clip(upper_dist * 2, 0, 10)
        
        day_score = np.where(has_big_up & is_stable, base_val + upper_linear_bonus, 0)
        big_up_bonus = np.maximum(big_up_bonus, day_score)

    scores += big_up_bonus

    # --- 3. 维度三：形态连续化 (不再是 0/1) ---
    # (1) Open==Low 的精准度：差值越小分越高
    ol_dist = np.abs(O[:, 0] - L[:, 0]) / O[:, 0] * 100
    ol_bonus = np.where((ol_dist < 0.2) & (C[:, 0] > O[:, 0]), 15 * (1 - ol_dist*5), 0)
    scores += ol_bonus

    # (2) 均线回踩精准度 (越贴合 MA 分越高)
    dist_ma5 = np.abs(C[:, 0] - M5[:, 0]) / M5[:, 0] * 100
    ma_bonus = np.where(dist_ma5 < 1.5, 10 * (1 - dist_ma5/1.5), 0)
    scores += ma_bonus

    # (3) 实时涨幅线性分 (每涨 1% 给 1.5分)
    scores += np.clip(P[:, 0] * 1.5, -5, 12)

    # (4) 突破 High4 的厚度
    h4_dist = (C[:, 0] - H4[:, 0]) / H4[:, 0] * 100
    scores += np.where(h4_dist > 0, 8 + np.clip(h4_dist, 0, 5), 0)

    # --- 4. 动力枯竭与负反馈 ---
    # 冲高回落惩罚：高位回落每 1% 扣 5分
    retreat = (H[:, 0] - C[:, 0]) / H[:, 0] * 100
    scores -= np.clip(retreat * 5, 0, 30)

    # --- 5. 结果输出 ---
    res = df.copy()
    res['gem_tops'] = np.round(scores, 2)
    return res.sort_values(by='gem_tops', ascending=False)



# def scoring_momentum_pullback_system_last(df: pd.DataFrame, max_days: int = 9):
#     N = len(df)
#     if N == 0: return df

#     def get_mat(prefix, suffix='d'):
#         if prefix in ['upper', 'high4']:
#             cols = [f"{prefix}{i}" for i in range(1, max_days + 1)]
#         else:
#             cols = [f"{prefix}{i}{suffix}" for i in range(1, max_days + 1)]
#         valid = [c for c in cols if c in df.columns]
#         mat = np.zeros((N, max_days))
#         if valid:
#             mat[:, :len(valid)] = df[valid].values
#         return mat

#     # --- 1. 构建基础矩阵 ---
#     C = get_mat('lastp')   # Close (0=今日, 1=昨日...)
#     O = get_mat('lasto')   # Open
#     L = get_mat('lastl')   # Low
#     H = get_mat('lasth')   # High
#     U = get_mat('upper')   # Upper Band
#     M5 = get_mat('ma5')
#     M10 = get_mat('ma10')
#     H4 = get_mat('high4')
#     P = get_mat('per')     # 涨跌幅

#     # 初始化总分
#     scores = np.zeros(N)

#     # --- 2. 【核心维度】大阳启动与不破支撑 (权重最高: 40+) ---
#     # 定义大阳线标准：涨幅 > 5%
#     BIG_UP_THRESHOLD = 5.0
#     is_big_up = P[:, 1:9] >= BIG_UP_THRESHOLD  # 过去8天的大阳线位置
    
#     big_up_bonus = np.zeros(N)
#     for i in range(1, 8):  # 回溯 1-7 天
#         # 条件 A: i天前是大阳线
#         has_big_up = is_big_up[:, i-1]
        
#         # 条件 B: 从今天到大阳线之后，所有收盘价 >= 大阳线收盘价 (不破收盘)
#         # support_price 是 i 天前的收盘价
#         support_price = C[:, i:i+1] 
#         is_stable = np.all(C[:, 0:i] >= support_price, axis=1)
        
#         # 条件 C: 今日站上 Upper 线 (代表启动强度)
#         above_upper = C[:, 0] > U[:, 0]
        
#         # 基础分：只要有大阳支撑且不破，给 25 分
#         # 增强分：如果同时站上 Upper，再加 20 分
#         # 衰减：距离越近，权重略高 (1.0 -> 0.8)
#         decay = (1.0 - (i * 0.03))
#         round_score = np.where(has_big_up & is_stable, 25 * decay, 0)
#         round_score += np.where(has_big_up & is_stable & above_upper, 20, 0)
        
#         # 取回溯周期内最强的一次信号
#         big_up_bonus = np.maximum(big_up_bonus, round_score)

#     scores += big_up_bonus

#     # --- 3. 维度二：前期强势基因 (权重: 15) ---
#     # 之前 30 分过高，现降低以突出大阳启动
#     early_strong = np.any(C[:, 6:9] > U[:, 6:9], axis=1)
#     scores += np.where(early_strong, 15, 0)

#     # --- 4. 维度三：回踩均线企稳 (权重: 15) ---
#     near_ma = (np.abs(C[:, 0:2] - M10[:, 0:2]) / M10[:, 0:2] < 0.015) | \
#               (np.abs(C[:, 0:2] - M5[:, 0:2]) / M5[:, 0:2] < 0.015)
#     scores += np.where(np.any(near_ma, axis=1), 15, 0)

#     # --- 5. 维度四：形态细节突破 ---
#     # (1) Open == Low 且收阳 (权重: 15)
#     open_eq_low = (O[:, 0] == L[:, 0]) & (C[:, 0] > O[:, 0])
#     scores += np.where(open_eq_low, 15, 0)

#     # (2) High4 突破奖励 (基础10 + 溢出)
#     break_ratio = (C[:, 0] - H4[:, 0]) / H4[:, 0]
#     breaking_out = (C[:, 0] >= H4[:, 0])
#     break_bonus = np.clip(break_ratio * 100 * 0.5, 0, 5)
#     scores += np.where(breaking_out, 10 + break_bonus, 0)

#     # (3) 最近两日重心 (Micro-Rhythm)
#     rhythm_score = np.where(C[:, 0] > C[:, 1], 2, 0) + \
#                    np.where(L[:, 0] > L[:, 1], 1, 0)
#     scores += rhythm_score

#     # --- 6. 异常风险扣分 (大幅扣分确保排队顺序) ---
#     # 3日累计跌幅过大
#     three_day_ret = np.sum(P[:, 0:3], axis=1)
#     scores += np.where(three_day_ret < -15, -60, 0)
    
#     # 破位扣分：如果今日收盘跌破 5日线 且 跌幅 > 3%
#     drop_below_ma5 = (C[:, 0] < M5[:, 0]) & (P[:, 0] < -3)
#     scores += np.where(drop_below_ma5, -30, 0)

#     # --- 7. 结果输出 ---
#     res = df.copy()
#     res['gem_score'] = np.round(scores, 2)
#     # 按高分排队，确保大阳启动且站稳 Upper 的排在最前面
#     return res.sort_values(by='gem_score', ascending=False)



def scoring_momentum_pullback_system_base_realtime(df: pd.DataFrame, max_days: int = 9):
    N = len(df)
    if N == 0: return df

    # --- 0. 升级 get_mat 以支持 0d 数据 ---
    def get_mat(prefix):
        # 实时数据注入后，potential_cols 包含 0d/0
        if prefix in ['upper', 'high4', 'ma5', 'ma10']:
            cols = [f"{prefix}{i}" for i in range(0, max_days + 1)]
        else:
            cols = [f"{prefix}{i}d" for i in range(0, max_days + 1)]
        
        mat = np.zeros((N, max_days + 1))
        for idx, col in enumerate(cols):
            if col in df.columns:
                mat[:, idx] = df[col].values
        return mat

    # --- 1. 构建基础矩阵 (索引 0 为今日实时) ---
    C = get_mat('lastp')   # Close
    O = get_mat('lasto')   # Open
    L = get_mat('lastl')   # Low
    H = get_mat('lasth')   # High
    U = get_mat('upper')   # Upper Band
    M5 = get_mat('ma5')
    M10 = get_mat('ma10')
    H4 = get_mat('high4')
    P = get_mat('per')     # 涨跌幅

    scores = np.zeros(N)

    # --- 2. 维度一：前期强势基因 (逻辑保持不变，回溯 6-9 日) ---
    early_strong = np.any(C[:, 6:9] > U[:, 6:9], axis=1)
    scores += np.where(early_strong, 30, 0)

    # --- 3. 维度二：回踩企稳判定 (逻辑保持不变，覆盖今日 0d 和昨日 1d) ---
    # 使用 0:2 包含今日实时和昨日数据
    near_ma = (np.abs(C[:, 0:2] - M10[:, 0:2]) / M10[:, 0:2] < 0.015) | \
              (np.abs(C[:, 0:2] - M5[:, 0:2]) / M5[:, 0:2] < 0.015)
    scores += np.where(np.any(near_ma, axis=1), 20, 0)

    # --- 4. 维度三：K线形态与突破细化 (逻辑保持不变) ---
    # (1) Open == Low 信号 (今日 0d)
    open_eq_low = (O[:, 0] == L[:, 0]) & (C[:, 0] > O[:, 0])
    scores += np.where(open_eq_low, 25, 0)

    # (2) High4 突破精度优化 (今日 0d)
    break_ratio = (C[:, 0] - H4[:, 0]) / H4[:, 0]
    breaking_out = (C[:, 0] >= H4[:, 0])
    break_bonus = np.clip(break_ratio * 100 * 0.5, 0, 3)
    scores += np.where(breaking_out, 15 + break_bonus, 0)

    # (3) 最近两日走势节奏 (今日 0d vs 昨日 1d)
    rhythm_score = np.where(C[:, 0] > C[:, 1], 1.2, 0) + \
                   np.where(L[:, 0] > L[:, 1], 0.8, 0)
    scores += rhythm_score

    # (4) 十字星企稳 (今日 0d)
    body_pct = np.abs(C[:, 0] - O[:, 0]) / O[:, 0]
    doji = (body_pct < 0.005) & (H[:, 0] > L[:, 0])
    scores += np.where(doji, 10, 0)

    # --- 5. 维度四：异常风险扣分 (包含今日 0d 在内的 3 日累计) ---
    three_day_ret = np.sum(P[:, 0:3], axis=1)
    scores += np.where(three_day_ret < -15, -50, 0)

    # --- 6. 结果输出 ---
    res = df.copy()
    res['gem_score'] = np.round(scores, 2)
    return res.sort_values(by='gem_score', ascending=False)

def buy_sell_score_momentum_vect(df: pd.DataFrame, max_days: int = 9):
    """
    急速矢量化评分系统 (buy_sell_score_momentum_vect)
    ---------------------------------------------
    集成趋势加速、OHLC 结构演变与趋势评分加权。
    旨在捕捉从下跌/盘整结构到上涨结构的演变，并给出趋势加速分。
    同步支持 0d 迭代行情与历史回溯判定。
    """
    N = len(df)
    if N == 0: return df

    # --- 0. 升级内部 get_mat 以支持 0d 动态迭代 ---
    def get_mat(prefix):
        # 实时数据注入后，potential_cols 包含 0d/0
        if prefix in ['upper', 'high4', 'ma5', 'ma10']:
            cols = [f"{prefix}{i}" for i in range(0, max_days + 1)]
        else:
            cols = [f"{prefix}{i}d" for i in range(0, max_days + 1)]
        
        mat = np.zeros((N, max_days + 1))
        for idx, col in enumerate(cols):
            if col in df.columns:
                mat[:, idx] = df[col].values
            elif idx > 0:
                # 填充缺失值，确保矢量计算不因为 NaN 崩掉
                mat[:, idx] = mat[:, idx-1]
        return mat

    # --- 1. 构建基础矩阵 ---
    C = get_mat('lastp')   # Close (0=今日现价, 1=昨日...)
    O = get_mat('lasto')   # Open
    L = get_mat('lastl')   # Low
    H = get_mat('lasth')   # High
    U = get_mat('upper')   # Upper Band (压力位)
    M5 = get_mat('ma5')    # 5日线
    M10 = get_mat('ma10')  # 10日线
    M20 = get_mat('ma20')  # 20日线
    H4 = get_mat('high4')  # 前高
    P = get_mat('per')     # 涨跌幅

    # --- [NEW] 1.5 结构与活跃度预处理 (Base Score) ---
    # 活跃度基础分 (Base Activity)
    power = df['power_idx'].values if 'power_idx' in df.columns else np.zeros(N)
    win_days = df['win'].values if 'win' in df.columns else np.zeros(N)
    
    # 活跃度底分起步 40，最高加到 70 左右
    base_activity = 40.0 + np.clip(power * 2.0, 0, 20) + np.clip(win_days * 3.0, 0, 15)
    
    # 结构性突破分 (Structural Breakouts)
    # 1. 突破2日高点
    break_2d_high = (C[:, 0] > np.maximum(H[:, 1], H[:, 2])).astype(float) * 10.0
    
    # 2. 一阳穿多线 (破 M5, M10, M20)
    # 收盘站上3条线，且昨日（或今日开盘）在至少一条线之下
    break_multi_ma = (C[:, 0] > M5[:, 0]) & (C[:, 0] > M10[:, 0]) & (C[:, 0] > M20[:, 0]) & \
                     ((C[:, 1] < M5[:, 1]) | (C[:, 1] < M10[:, 1]) | (C[:, 1] < M20[:, 1]))
    break_ma_bonus = break_multi_ma.astype(float) * 20.0
    
    # 3. 突破 hmax (前期60日新高或特定大周期新高)
    hmax_val = df['hmax'].values if 'hmax' in df.columns else np.full(N, 1e9)
    # 排除 hmax <= 0 的情况
    break_hmax = ((C[:, 0] >= hmax_val) & (hmax_val > 0)).astype(float) * 15.0
    
    # 4. 连续小阴，高点下移惩罚 (Continuous small yin, lowering highs)
    lowering_highs = (H[:, 1] < H[:, 2]) & (H[:, 2] < H[:, 3]) & (C[:, 1] <= O[:, 1]) & (C[:, 2] <= O[:, 2])
    lowering_penalty = lowering_highs.astype(float) * -15.0
    
    # 综合结构底分 (Structure Base Score，供盘中引擎和基线使用)
    structure_base_score = np.clip(
        base_activity + break_2d_high + break_ma_bonus + break_hmax + lowering_penalty,
        10, 100
    )

    # --- 2. 核心量化指标：动量 (Momentum) 与 加速度 (Acceleration) ---
    # 动量：当前价格相对于昨日的斜率百分比
    mom0 = (C[:, 0] - C[:, 1]) / np.maximum(C[:, 1], 1e-9) * 100
    # 动量：昨日相对于前日的斜率
    mom1 = (C[:, 1] - C[:, 2]) / np.maximum(C[:, 2], 1e-9) * 100
    # 加速度：斜率的变化率 (动力是否在加强)
    accel = mom0 - mom1

    # --- 3. 结构化演变：从下跌/横盘 转为 上涨 ---
    # 结构一：上穿关键均线 (由空转多)
    was_bear = (C[:, 1] < M5[:, 1]) | (C[:, 1] < M10[:, 1])
    is_bull = (C[:, 0] >= M5[:, 0]) & (C[:, 0] >= M10[:, 0])
    pivot_reverse = (was_bear & is_bull).astype(float) * 20.0
    
    # 结构二：突围关键压力 (Upper / High4)
    out_upper = (C[:, 0] > U[:, 0]) & (C[:, 1] <= U[:, 1])
    out_h4 = (C[:, 0] > H4[:, 0]) & (C[:, 1] <= H4[:, 1])
    break_bonus = (out_upper.astype(float) * 15.0) + (out_h4.astype(float) * 10.0)

    # --- 4. 实时 K 线形态形态评分 (OHLC 每日走势叠加) ---
    # 计算日内强度位置：收盘价在日内高低点中的相对位置
    day_range = np.maximum(H[:, 0] - L[:, 0], 1e-9)
    day_pos = (C[:, 0] - L[:, 0]) / day_range
    # 收盘靠近最高点，给予额外走势分
    ohlc_shape_score = day_pos * 12.0
    
    # 开报低走 vs 低开高走
    low_start = (O[:, 0] <= L[:, 0] * 1.002).astype(float) * 8.0 

    # --- 5. 综合买卖评分计算 ---
    # 买入分 (buyscore)：动量爆发 + 加速溢价 + 结构反转 + 形态承接 + [NEW]结构底分溢价权重
    # 将结构底分中超出 50 的部分转化为附加动量
    structure_momentum_bonus = np.maximum(structure_base_score - 50.0, 0.0) * 0.4
    
    buy_scores = (
        np.clip(mom0 * 3.5, -10, 30) +   # 基础爆发力
        np.clip(accel * 5.0, -15, 25) +  # 趋势加速强度 (核心权重)
        pivot_reverse +                   # 结构性转折奖励
        break_bonus +                     # 压力突破奖励
        ohlc_shape_score +                # 形态走势对齐
        low_start +                       # 底部开盘承接
        structure_momentum_bonus          # 结合结构基底分
    )
    
    # 趋势保持权重：如果 5/10/20 多头排列，给一个 10 分的基础护航分
    strong_trend = (M5[:, 0] > M10[:, 0]) & (C[:, 0] > M5[:, 0])
    buy_scores += strong_trend.astype(float) * 10.0

    # 卖出分 (sellscore)：冲高回落 + 加速衰减 + 破位结构
    # 冲高回落幅度
    retreat = (H[:, 0] - C[:, 0]) / np.maximum(H[:, 0], 1e-9) * 100
    sell_scores = (
        np.clip(retreat * 6.0, 0, 40) +    # 冲高回落权重最高
        np.clip(-accel * 4.0, 0, 20) +     # 动力衰减权重
        ((C[:, 0] < M5[:, 0]) & (C[:, 1] >= M5[:, 1])).astype(float) * 30.0 # 瞬间破位
    )

    # --- 6. 结果注入与性能自检 ---
    res = df.copy()
    res['buyscore'] = np.round(np.clip(buy_scores, 0, 100), 2)
    res['sellscore'] = np.round(np.clip(sell_scores, 0, 100), 2)
    res['structure_base_score'] = np.round(structure_base_score, 2)  # [NEW] 输出供后续决策引擎使用
    
    # 统计信息用于自检
    if N > 0:
        avg_buy = res['buyscore'].mean()
        max_buy = res['buyscore'].max()
        logger.debug(f"[QuantScore-Vect] N={N}, AvgBuy={avg_buy:.2f}, MaxBuy={max_buy:.2f}, Transitions={pivot_reverse.sum()}")

    return res
    
def scoring_momentum_pullback_system_base(df: pd.DataFrame, max_days: int = 9):
    N = len(df)
    if N == 0: return df

    def get_mat(prefix, suffix='d'):
        if prefix in ['upper', 'high4']:
            cols = [f"{prefix}{i}" for i in range(1, max_days + 1)]
        else:
            cols = [f"{prefix}{i}{suffix}" for i in range(1, max_days + 1)]
        valid = [c for c in cols if c in df.columns]
        mat = np.zeros((N, max_days))
        if valid:
            mat[:, :len(valid)] = df[valid].values
        return mat

    # --- 1. 构建基础矩阵 ---
    C = get_mat('lastp')   # Close (0=今日, 1=昨日...)
    O = get_mat('lasto')   # Open
    L = get_mat('lastl')   # Low
    H = get_mat('lasth')   # High
    U = get_mat('upper')   # Upper Band
    M5 = get_mat('ma5')
    M10 = get_mat('ma10')
    H4 = get_mat('high4')
    P = get_mat('per')     # 涨跌幅

    scores = np.zeros(N)

    # --- 2. 维度一：前期强势基因 (权重: 30) ---
    early_strong = np.any(C[:, 6:9] > U[:, 6:9], axis=1)
    scores += np.where(early_strong, 30, 0)

    # --- 3. 维度二：回踩企稳判定 (权重: 20) ---
    near_ma = (np.abs(C[:, 0:2] - M10[:, 0:2]) / M10[:, 0:2] < 0.015) | \
              (np.abs(C[:, 0:2] - M5[:, 0:2]) / M5[:, 0:2] < 0.015)
    scores += np.where(np.any(near_ma, axis=1), 20, 0)

    # --- 4. 维度三：K线形态与突破细化 ---
    # (1) Open == Low 信号 (权重: 25)
    open_eq_low = (O[:, 0] == L[:, 0]) & (C[:, 0] > O[:, 0])
    scores += np.where(open_eq_low, 25, 0)

    # (2) High4 突破精度优化 (基础15 + 溢出奖励)
    # 计算今日收盘超过 High4 的百分比
    break_ratio = (C[:, 0] - H4[:, 0]) / H4[:, 0]
    breaking_out = (C[:, 0] >= H4[:, 0])
    # 溢出分：每超过 1% 加 0.5 分，最高封顶 3 分 (即超过 6% 就不再额外加分)
    break_bonus = np.clip(break_ratio * 100 * 0.5, 0, 3)
    scores += np.where(breaking_out, 15 + break_bonus, 0)

    # (3) 最近两日走势节奏 (Micro-Rhythm)
    # 节奏 A: 今日重心抬高 (收盘价 > 昨日收盘) -> 加 1.2 分
    # 节奏 B: 今日承接力强 (最低价 > 昨日最低) -> 加 0.8 分
    rhythm_score = np.where(C[:, 0] > C[:, 1], 1.2, 0) + \
                   np.where(L[:, 0] > L[:, 1], 0.8, 0)
    scores += rhythm_score

    # (4) 十字星企稳 (权重: 10)
    body_pct = np.abs(C[:, 0] - O[:, 0]) / O[:, 0]
    doji = (body_pct < 0.005) & (H[:, 0] > L[:, 0])
    scores += np.where(doji, 10, 0)

    # --- 5. 维度四：异常风险扣分 ---
    three_day_ret = np.sum(P[:, 0:3], axis=1)
    scores += np.where(three_day_ret < -15, -50, 0)

    # --- 6. 结果输出 ---
    res = df.copy()
    res['gem_score'] = np.round(scores, 2) # 保留两位小数拉开区分度
    return res.sort_values(by='gem_score', ascending=False)



# def scoring_momentum_pullback_system_first(df: pd.DataFrame, max_days: int = 9):
#     N = len(df)
#     if N == 0: return df

#     def get_mat(prefix, suffix='d'):
#         # 兼容不同列名格式
#         if prefix in ['upper', 'high4']:
#             cols = [f"{prefix}{i}" for i in range(1, max_days + 1)]
#         else:
#             cols = [f"{prefix}{i}{suffix}" for i in range(1, max_days + 1)]
#         valid = [c for c in cols if c in df.columns]
#         mat = np.zeros((N, max_days))
#         if valid:
#             mat[:, :len(valid)] = df[valid].values
#         return mat

#     # --- 1. 构建基础矩阵 (0=1d, 1=2d, ..., 8=9d) ---
#     C = get_mat('lastp')   # Close
#     O = get_mat('lasto')   # Open
#     L = get_mat('lastl')   # Low
#     H = get_mat('lasth')   # High
#     U = get_mat('upper')   # Upper Band
#     M5 = get_mat('ma5')
#     M10 = get_mat('ma10')
#     H4 = get_mat('high4')
#     P = get_mat('per')     # 涨跌幅

#     scores = np.zeros(N)

#     # --- 2. 维度一：前期强势基因 (7-9日前上过轨) ---
#     # 检查 7d, 8d, 9d 是否有 P > U
#     early_strong = np.any(C[:, 6:9] > U[:, 6:9], axis=1)
#     scores += np.where(early_strong, 30, 0)

#     # --- 3. 维度二：回踩企稳判定 (最近1-3天) ---
#     # 最近 1-2 天收盘价在 MA5 或 MA10 附近 (波动率 < 1.5%)
#     near_ma = (np.abs(C[:, 0:2] - M10[:, 0:2]) / M10[:, 0:2] < 0.015) | \
#               (np.abs(C[:, 0:2] - M5[:, 0:2]) / M5[:, 0:2] < 0.015)
#     scores += np.where(np.any(near_ma, axis=1), 20, 0)

#     # --- 4. 维度三：K线形态打分 (1d/今天) ---
#     # (1) Open == Low 信号
#     open_eq_low = (O[:, 0] == L[:, 0]) & (C[:, 0] > O[:, 0])
#     scores += np.where(open_eq_low, 25, 0)

#     # (2) Close > High4 蓄势信号
#     breaking_out = (C[:, 0] >= H4[:, 0])
#     scores += np.where(breaking_out, 15, 0)

#     # (3) 十字星企稳 (实体长度 < 0.5% 且 有上下影线)
#     body_pct = np.abs(C[:, 0] - O[:, 0]) / O[:, 0]
#     doji = (body_pct < 0.005) & (H[:, 0] > L[:, 0])
#     scores += np.where(doji, 10, 0)

#     # --- 5. 维度四：涨跌幅扣分/加分 (防止阴跌) ---
#     # 如果最近3天跌幅过大 (<-15%)，判定为走坏，大幅扣分
#     three_day_ret = np.sum(P[:, 0:3], axis=1)
#     scores += np.where(three_day_ret < -15, -50, 0)

#     # --- 6. 结果输出 ---
#     res = df.copy()
#     res['gem_score'] = scores
#     # 过滤出有基本得分的个股并排序
#     return res.sort_values(by='gem_score', ascending=False)

# 调用示例
# top_potential = scoring_momentum_pullback_system(top_all)

def get_vect_col(upper='upper',max_days=cct.compute_lastdays):
    cols = []
    # 构建 lastp, lasth, lastl, lastv 等列
    for prefix in ['lastp', 'lasth', 'lasto','lastl', 'lastv', upper, 'high4', 'ma5']:
        for i in range(1, max_days + 1):
            cols.append(f"{prefix}{i}d" if prefix not in ['upper', 'high4'] else f"{prefix}{i}")

    # 最终再加上计算列 win_upper
    cols.append('win_upper')
    return cols


def strong_momentum_large_cycle_vect_consecutive_above(
    df: pd.DataFrame,
    price_col: str = 'lastp',
    upper_col: str = 'upper',
    ma_col: str = 'ma5',
    high4_col: str = 'high4',
    max_days: int = 9
):
    N = len(df)
    if N == 0:
        return df.assign(**{f'win_{upper_col}': np.zeros(N, dtype=int)})

    # ---------- 构建矩阵 (0轴代表行, 1轴代表天数 0d, 1d, 2d... ) ----------
    def get_mat(prefix):
        # 统一输出形状为 (N, max_days + 1)
        mat = np.zeros((N, max_days + 1))
        
        if prefix in ['upper', 'high4']:
            potential_cols = [f"{prefix}{i}" for i in range(0, max_days + 1)]
        else:
            potential_cols = [f"{prefix}{i}d" for i in range(0, max_days + 1)]
        
        valid = [c for c in potential_cols if c in df.columns]
        
        if valid:
            def extra_num(s):
                m = re.search(r'\d+', s)
                return int(m.group()) if m else 99
            
            # 按天数排序并填充到矩阵对应位置
            for c in valid:
                day_idx = extra_num(c)
                if day_idx <= max_days:
                    mat[:, day_idx] = df[c].values
            return mat, max_days + 1
        else:
            # 兼容性回退
            if prefix == 'lasto': use_col = 'open'
            elif prefix == 'lastp': use_col = 'close'
            elif prefix == 'lasth': use_col = 'high'
            elif prefix == 'lastl': use_col = 'low'
            elif prefix == 'lastv': use_col = 'volume'
            else: use_col = prefix
            
            if use_col in df.columns:
                mat = np.tile(df[[use_col]].values, (1, max_days + 1))
            return mat, max_days + 1

    P, plen = get_mat(price_col)
    U, ulen = get_mat(upper_col)
    L, _    = get_mat('lastl')
    Ma, _   = get_mat(ma_col)
    H4, _   = get_mat(high4_col)

    usable = min(plen, ulen)
    win_upper = np.zeros(N, dtype=int)

    # ---------- 核心计算 ----------
    # start_cond[i, j] 表示第 i 行第 j+1 天是否满足启动条件
    start_cond = (L[:, :usable] <= Ma[:, :usable]) & (P[:, :usable] > H4[:, :usable])
    # above_upper[i, j] 表示第 i 行第 j+1 天是否站稳压力位
    above_upper = (P[:, :usable] > U[:, :usable])

    for i in range(N):
        # 找到最近的启动点索引 (1d=0, 2d=1...)
        # 使用 np.where 找到所有启动点，取第一个 [0] 即为最近的启动点
        hits = np.where(start_cond[i])[0]
        if len(hits) == 0:
            continue
        
        start_idx = hits[0] 
        
        # 启动当天必须满足 P > U 才能开始计天数
        if not above_upper[i, start_idx]:
            win_upper[i] = 0
            continue
        
        # 从启动点开始向“现在”(索引减小的方向) 检查连续性
        # 例如 start_idx = 2 (3d), 检查顺序为 2 -> 1 -> 0
        count = 0
        for j in range(start_idx, -1, -1):
            if above_upper[i, j]:
                count += 1
            else:
                break # 一旦断掉就停止
        
        win_upper[i] = count

    res = df.copy()
    res[f'win_{upper_col}'] = win_upper
    return res



def strong_momentum_large_cycle_vect_consecutive_above_m5(
    df: pd.DataFrame,
    price_col: str = 'lastp',
    upper_col: str = 'upper',
    ma_col: str = 'ma5',
    max_days: int = 20,
):
    """
    修正版逻辑：
    1. 找到离现在最近的一个满足 L <= Ma 的交易日作为“启动点”。
    2. 启动点当天计 1 天。
    3. 从启动点向“现在”的方向（即 1d 方向）检查，如果连续满足 P > U 且 C > O，则累加天数。
    """
    N = len(df)
    if N == 0:
        return df.assign(**{f'wm5_{upper_col}': np.zeros(N, dtype=int)})

    # ---------- 构建矩阵 (0d 在 index 0, 1d 在 index 1...) ----------
    def get_mat(prefix, use_col=None):
        mat = np.zeros((N, max_days + 1))
        if prefix == upper_col:
            potential_cols = [f"{prefix}{i}" for i in range(0, max_days+1)]
        else:
            potential_cols = [f"{prefix}{i}d" for i in range(0, max_days+1)]
        
        valid = [c for c in potential_cols if c in df.columns]
        if valid:
            def extra_num(s):
                m = re.search(r'\d+', s)
                return int(m.group()) if m else 99
            
            for c in valid:
                day_idx = extra_num(c)
                if day_idx <= max_days:
                    mat[:, day_idx] = df[c].values
            return mat
        else:
            # 兼容性处理：若无滚动列则重复当前列
            if use_col is None:
                if prefix == 'lasto': use_col = 'open'
                elif prefix == 'lastp': use_col = 'close'
                elif prefix == 'lasth': use_col = 'high'
                elif prefix == 'lastl': use_col = 'low'
                elif prefix == 'lastv': use_col = 'volume'
                else: use_col = prefix
            
            if use_col in df.columns:
                return np.tile(df[[use_col]].values, (1, max_days + 1))
            else:
                return mat

    P  = get_mat(price_col)
    U  = get_mat(upper_col)
    L  = get_mat('lastl')
    Ma = get_mat(ma_col)
    O  = get_mat('lasto')
    C  = P  # 阳线判断通常使用收盘价/现价

    win_upper = np.zeros(N, dtype=int)
    has_0d = f'{price_col}0d' in df.columns or f'{upper_col}0' in df.columns
    stop_idx = 0 if has_0d else 1

    # ---------- 条件矩阵 ----------
    # 注意：矩阵的列索引 0=0d, 1=1d, 2=2d...
    cond_touch = (L <= Ma)
    cond_strong = (P > U) & (C > O)

    # ---------- 遍历每行计算 ----------
    for i in range(N):
        # 1. 找到最近的一次启动点 (即最小的列索引)
        idxs = np.where(cond_touch[i])[0]
        # 过滤 0d 屏蔽位
        idxs = [idx for idx in idxs if idx >= stop_idx]
        
        if len(idxs) == 0:
            continue
        
        start_idx = idxs[0]
        length = 1
        
        # 3. 从启动点向“现在”方向遍历 (索引减小的方向)
        for j in range(start_idx - 1, stop_idx - 1, -1):
            if cond_strong[i, j]:
                length += 1
            else:
                break
        
        win_upper[i] = length

    res = df.copy()
    res[f'wm5_{upper_col}'] = win_upper
    return res

def strong_momentum_large_cycle_vect_consecutive_above_single(
    df: pd.DataFrame,
    price_col: str = 'lastp',     # 'lastp' or 'lasth'
    upper_col: str = 'upper',     # 'upper', 'ma5', 'ma10', ...
    max_days: int = 20,
):
    """
    统计从 1d 开始向过去方向，price_col > upper_col 连续成立的天数。
    如果 1d 就不满足，则返回 0。
    """
    N = len(df)
    if N == 0:
        return df

    # ---------- 构建矩阵 (0d=idx 0, 1d=idx 1...) ----------
    def get_val_matrix(prefix):
        if prefix == 'upper':
            potential_cols = [f"{prefix}{i}" for i in range(0, max_days + 1)]
        else:
            potential_cols = [f"{prefix}{i}d" for i in range(0, max_days + 1)]
        
        valid_cols = [c for c in potential_cols if c in df.columns]
        if not valid_cols:
            return None, 0
            
        def extra_num(s):
            m = re.search(r'\d+', s)
            return int(m.group()) if m else 99
        valid_cols = sorted(valid_cols, key=extra_num)
        
        return df[valid_cols].values, len(valid_cols)

    P, p_len = get_val_matrix(price_col)
    U, u_len = get_val_matrix(upper_col)

    usable_days = min(p_len, u_len)
    if usable_days == 0:
        df[f'w_{upper_col}'] = 0
        return df

    # 判定是否存在 0d 实时数据
    has_0d = f'{price_col}0d' in df.columns or f'{upper_col}0' in df.columns
    start_offset = 0 if has_0d else 1

    # ---------- 核心向量化逻辑 ----------
    # cond 矩阵: True 代表 P > U
    # 截取有效范围，跳过可能的 0d 占位符
    effective_cond = P[:, start_offset:usable_days] > U[:, start_offset:usable_days]
    
    # 寻找每一行第一个出现 False 的位置
    first_false = np.argmax(~effective_cond, axis=1)

    # 特殊情况处理
    all_true = np.all(effective_cond, axis=1)
    win_upper = np.where(all_true, usable_days - start_offset, first_false)

    # ---------- 输出 ----------
    res_df = df.copy()
    res_df[f'w_{upper_col}'] = win_upper

    return res_df

# def strong_momentum_large_cycle_vect_other_noapp(
#     df,
#     max_days=10,
#     winlimit=1,
#     upper_prefix='upper',          # e.g. 'upper', 'ma10', 'ma20'
#     upper_mode='P',             # 'P' | 'PH' | 'custom'
#     debug=False
# ):
#     N = len(df)
#     if N == 0:
#         return {}

#     # ========= 1. 构建矩阵 =========
#     def get_val_matrix_other(prefix):
#         if prefix == 'upper':
#             cols = [f"{prefix}{i}" for i in range(1, max_days + 2)]
#         else:
#             cols = [f"{prefix}{i}d" for i in range(1, max_days + 2)]
#         valid_cols = [c for c in cols if c in df.columns]
#         mat = np.zeros((N, max_days + 2))
#         if valid_cols:
#             mat[:, 1:len(valid_cols) + 1] = df[valid_cols].values
#         return mat

#     P = get_val_matrix_other('lastp')
#     H = get_val_matrix_other('lasth')
#     L = get_val_matrix_other('lastl')
#     V = get_val_matrix_other('lastv')

#     U = None
#     if upper_prefix is not None:
#         U = get_val_matrix_other(upper_prefix)

#     # ========= 2. 趋势判定 =========
#     yesterday_up = P[:, 1] > P[:, 2]
#     max_win = np.zeros(N, dtype=int)

#     for w in range(2, max_days):
#         c_a, p_a = np.arange(1, w), np.arange(2, w + 1)
#         c_b, p_b = np.arange(2, w + 1), np.arange(3, w + 2)

#         # ---------- 原始结构 ----------
#         m_a = (
#             np.all(P[:, c_a] >= P[:, p_a], axis=1) &
#             np.all(H[:, c_a] >= P[:, c_a], axis=1) &
#             np.all((L[:, c_a] >= L[:, p_a]) | (V[:, c_a] >= V[:, p_a]), axis=1)
#         )

#         m_b = (
#             np.all(P[:, c_b] >= P[:, p_b], axis=1) &
#             np.all(H[:, c_b] >= H[:, p_b], axis=1) &
#             np.all((L[:, c_b] >= L[:, p_b]) | (V[:, c_b] >= V[:, p_b]), axis=1)
#         )

#         # ---------- upper / MA 结构约束 ----------
#         if U is not None:
#             if upper_mode == 'P':
#                 m_a &= np.all(P[:, c_a] > U[:, c_a], axis=1)
#                 m_b &= np.all(P[:, c_b] > U[:, c_b], axis=1)

#             elif upper_mode == 'PH':
#                 m_a &= (
#                     np.all(P[:, c_a] > U[:, c_a], axis=1) &
#                     np.all(H[:, c_a] > U[:, c_a], axis=1)
#                 )
#                 m_b &= (
#                     np.all(P[:, c_b] > U[:, c_b], axis=1) &
#                     np.all(H[:, c_b] > U[:, c_b], axis=1)
#                 )

#             elif upper_mode == 'custom':
#                 # 预留：你可以在这里插入更复杂的逻辑
#                 pass

#         combined = (yesterday_up & m_a) | (~yesterday_up & m_b)
#         if not np.any(combined):
#             break

#         max_win[combined] = w

#     # ========= 3. 筛选 =========
#     keep_idx = np.where(max_win >= winlimit)[0]
#     if len(keep_idx) == 0:
#         return {}

#     # ========= 4. 斜率 =========
#     start_d = np.where(yesterday_up[keep_idx], 1, 2)
#     end_d = start_d + max_win[keep_idx] - 1

#     p_start = P[keep_idx, start_d]
#     p_end = P[keep_idx, end_d]

#     slopes = (p_start - p_end) / p_end / (max_win[keep_idx] - 1) * 100

#     # ========= 5. 爆发力 =========
#     v_sub = V[keep_idx].copy()
#     col_range = np.arange(V.shape[1])
#     mask = (col_range >= start_d[:, None]) & (col_range <= end_d[:, None])
#     v_sub[~mask] = 0

#     avg_vols = np.sum(v_sub, axis=1) / max_win[keep_idx]
#     vol_ratio = V[keep_idx, 1] / (avg_vols + 1e-9)

#     power_idx = slopes * vol_ratio

#     # ========= 6. 输出 =========
#     res_df = df.iloc[keep_idx].copy()
#     res_df['max_win'] = max_win[keep_idx]
#     res_df['slope'] = np.round(slopes, 2)
#     res_df['vol_ratio'] = np.round(vol_ratio, 2)
#     res_df['power_idx'] = np.round(power_idx, 2)
#     res_df['sum_perc'] = np.round((p_start - p_end) / p_end * 100, 2)

#     return {
#         int(w): g.sort_values('power_idx', ascending=False)
#         for w, g in res_df.groupby('max_win')
#     }

# 使用示例：
# df = pd.DataFrame(vect_daily_t)
# check_real_time(df, ['688239', '601360'])

def strong_momentum_large_cycle_vect_new(df, max_days=10, winlimit=6, debug=False):
    N = len(df)
    if N == 0:
        return {}

    import numpy as np

    # === 1. 构造价格/量能矩阵 ===
    def get_val_matrix(prefix):
        cols = [f"{prefix}{i}d" for i in range(1, max_days + 2)]
        valid_cols = [c for c in cols if c in df.columns]
        mat = np.zeros((N, max_days + 2))
        if valid_cols:
            mat[:, 1:len(valid_cols)+1] = df[valid_cols].values
        return mat

    P = get_val_matrix('lastp')
    H = get_val_matrix('lasth')
    L = get_val_matrix('lastl')
    V = get_val_matrix('lastv')

    # === 2. 主升结构窗口识别 ===
    max_win = np.zeros(N, dtype=int)

    for w in range(2, max_days + 1):

        c = np.arange(1, w)
        p = np.arange(2, w + 1)

        # ① 高点不破趋势
        cond_high = np.all(H[:, c] >= H[:, p], axis=1)

        # ② 低点整体抬高（允许2%噪音）
        cond_low = np.all(L[:, 1:w] >= L[:, 2:w+1] * 0.98, axis=1)

        # ③ 整体上涨
        cond_trend = P[:, 1] > P[:, w]

        # ④ 阳线占多数（避免阴跌结构误判）
        up_days = np.sum(P[:, 1:w+1] > P[:, 2:w+2], axis=1)
        cond_bull = up_days >= (w // 2)

        combined = cond_high & cond_low & cond_trend & cond_bull

        if not np.any(combined):
            break

        max_win[combined] = w

    # === 3. 过滤有效窗口 ===
    keep_idx = np.where(max_win >= winlimit)[0]
    if len(keep_idx) == 0:
        return {}

    # === 4. 结构斜率（每日平均涨幅 %）===
    start_d = 1
    end_d = max_win[keep_idx]

    p_start = P[keep_idx, start_d]
    p_end = P[keep_idx, end_d]

    slopes = (p_start - p_end) / p_end / (max_win[keep_idx] - 1) * 100

    # === 5. 量能爆发系数 ===
    v_sub = V[keep_idx].copy()
    col_range = np.arange(V.shape[1])

    range_mask = (col_range >= 1) & (col_range <= end_d[:, None])
    v_sub[~range_mask] = 0

    avg_vols = np.sum(v_sub, axis=1) / max_win[keep_idx]
    vol_ratio = V[keep_idx, 1] / (avg_vols + 1e-9)

    power_idx = slopes * vol_ratio

    # === 6. 结果整理 ===
    res_df = df.iloc[keep_idx].copy()
    res_df['max_win'] = max_win[keep_idx]
    res_df['slope'] = np.round(slopes, 2)
    res_df['vol_ratio'] = np.round(vol_ratio, 2)
    res_df['power_idx'] = np.round(power_idx, 2)
    res_df['sum_perc'] = np.round((p_start - p_end) / p_end * 100, 2)

    return {
        int(w): group.sort_values('power_idx', ascending=False)
        for w, group in res_df.groupby('max_win')
    }


def strong_momentum_large_cycle_vect(df, max_days=10, winlimit=2,debug=False):
    N = len(df)
    if N == 0: return {}

    # 1. 快速提取矩阵 (P, H, L, V)
    def get_val_matrix(prefix):
        cols = [f"{prefix}{i}d" for i in range(1, max_days + 2)]
        valid_cols = [c for c in cols if c in df.columns]
        mat = np.zeros((N, max_days + 2))
        if valid_cols:
            mat[:, 1:len(valid_cols)+1] = df[valid_cols].values
        return mat

    P = get_val_matrix('lastp')
    H = get_val_matrix('lasth')
    L = get_val_matrix('lastl')
    V = get_val_matrix('lastv')
    
    # 2. 趋势判定逻辑 (保持你的双轨制)
    yesterday_up = P[:, 1] > P[:, 2]
    max_win = np.zeros(N, dtype=int)

    for w in range(2, max_days):
        c_a, p_a = np.arange(1, w), np.arange(2, w + 1)
        # 加速态优化：H1d 只要不低于 P1d 且收盘创新高即可
        m_a = np.all(P[:, c_a] >= P[:, p_a], axis=1) & \
              np.all(H[:, c_a] >= P[:, c_a], axis=1) & \
              np.all((L[:, c_a] >= L[:, p_a]) | (V[:, c_a] >= V[:, p_a]), axis=1)
        
        c_b, p_b = np.arange(2, w + 1), np.arange(3, w + 2)
        m_b = np.all(P[:, c_b] >= P[:, p_b], axis=1) & \
              np.all(H[:, c_b] >= H[:, p_b], axis=1) & \
              np.all((L[:, c_b] >= L[:, p_b]) | (V[:, c_b] >= V[:, p_b]), axis=1)

        combined = (yesterday_up & m_a) | (~yesterday_up & m_b)
        if not np.any(combined): break
        max_win[combined] = w

    # 3. 结果筛选
    keep_idx = np.where(max_win >= winlimit)[0]
    if len(keep_idx) == 0: return {}

    # 4. 矢量化斜率计算 (Slope)
    # 计算公式: (P1d - Pwd) / (w-1) / Pwd * 100 (百分比斜率)
    # 我们需要根据每只票的 max_win 找到对应的起始价格 Pwd
    row_idx = np.arange(len(keep_idx))
    start_d = np.where(yesterday_up[keep_idx], 1, 2)
    end_d = start_offset = start_d + max_win[keep_idx] - 1
    
    # 获取周期起点价格 (Pwd)
    p_start = P[keep_idx, start_d]
    p_end = np.zeros(len(keep_idx))
    for i, idx_in_keep in enumerate(keep_idx):
        p_end[i] = P[idx_in_keep, end_d[i]]
    
    # 标准化斜率: 每日平均涨幅百分比
    slopes = (p_start - p_end) / p_end / (max_win[keep_idx] - 1) * 100
    
    # 5. 爆发力评分 (Power Index)
    # 逻辑: 斜率 * (1d量 / 周期平均量)
    v_sub = V[keep_idx].copy()
    # 动态掩码算平均量
    col_range = np.arange(V.shape[1])
    range_mask = (col_range >= start_d[:, None]) & (col_range <= end_d[:, None])
    v_sub[~range_mask] = 0
    avg_vols = np.sum(v_sub, axis=1) / max_win[keep_idx]
    vol_ratio = V[keep_idx, 1] / (avg_vols + 1e-9)
    
    power_idx= slopes * vol_ratio

    # 6. 组装输出
    res_df = df.iloc[keep_idx].copy()
    res_df['max_win'] = max_win[keep_idx]
    res_df['slope'] = np.round(slopes, 2)
    res_df['vol_ratio'] = np.round(vol_ratio, 2)
    res_df['power_idx'] = np.round(power_idx, 2)
    res_df['sum_perc'] = np.round((p_start - p_end) / p_end * 100, 2)

    return {int(w): group.sort_values('power_idx', ascending=False) 
            for w, group in res_df.groupby('max_win')}


# def strong_momentum_today_plus_history_sum_opt(df, max_days=cct.compute_lastdays, winlimit=winlimit,debug=False):
#     """
#     完全向量化版本，用 NumPy 计算严格连续上涨和 sum_percent 25ms
#     """
#     result_dict = {}

#     # ===== 0️⃣ 判断今天状态，只做一次 =====
#     is_trade_day = cct.get_trade_date_status()
#     in_market_hours = 915 < cct.get_now_time_int() < 1500
#     real_time_mode = is_trade_day and in_market_hours

#     ohlc_same_as_last1d = (
#         (df['open'] == df.get('lasto1d', df['open'])) &
#         (df['low'] == df.get('lastl1d', df['low'])) &
#         (df['high'] == df.get('lasth1d', df['high'])) &
#         (df['close'] == df.get('lastp1d', df['close']))
#     )
#     use_real_ohlc = real_time_mode & (~ohlc_same_as_last1d)

#     # ===== 1️⃣ 今天数据列 =====
#     today_open  = df['open'].where(use_real_ohlc, df['lasto1d']).to_numpy()
#     today_high  = df['high'].where(use_real_ohlc, df['lasth1d']).to_numpy()
#     today_low   = df['low'].where(use_real_ohlc, df['lastl1d']).to_numpy()
#     today_close = df['close'].where(use_real_ohlc, df['lastp1d']).to_numpy()
#     # today_vol = df['volume'].where(use_real_ohlc, df['lastv1d']).to_numpy()

#     codes = df.index.to_numpy()

#     # ===== 2️⃣ 历史收盘/高/低 =====
#     # 构建 N x max_days 的 NumPy array
#     lastp = np.zeros((len(df), max_days))
#     lasth = np.zeros((len(df), max_days))
#     lastl = np.zeros((len(df), max_days))
#     lastv = np.zeros((len(df), max_days))

#     for i in range(1, max_days+1):
#         lastp[:, i-1] = df.get(f'lastp{i}d', 0).to_numpy()
#         lasth[:, i-1] = df.get(f'lasth{i}d', 0).to_numpy()
#         lastl[:, i-1] = df.get(f'lastl{i}d', 0).to_numpy()
#         lastv[:, i-1] = df.get(f'lastv{i}d', 0).to_numpy()

#     # ===== 3️⃣ 遍历窗口 =====
#     start_window = winlimit

#     # 盘后：today == last1d，window=1 没有策略意义
#     if not use_real_ohlc.any():
#         start_window = max(2, winlimit)

#     # ===== 3️⃣ 遍历窗口 =====
#     for window in range(start_window, max_days+1):
#         if window == 1:
#             # window=1 特殊处理
#             # mask = (today_high > lastp[:, 0]) & (today_close > lastp[:, 0])
#             # window=1 特殊处理：实时 vs 收盘后
#             mask = np.where(
#                 use_real_ohlc.to_numpy(),
#                 (today_high > lastp[:, 0]) & (today_close > lastp[:, 0]),  # 实时 vs 昨天
#                 (lastp[:, 0] > df.get('lastp2d', lastp[:, 0]).to_numpy()) &
#                 (lasth[:, 0] > df.get('lasth2d', lasth[:, 0]).to_numpy())  # 收盘后 vs 前天
#             )
#             if debug:
#                 # logger.debug(f"use_real_ohlc: {use_real_ohlc.all()} window={window}, mask_close={mask}")
#                 print(f"use_real_ohlc: {use_real_ohlc.all()} window={window}, mask_close={mask}")

#         else:
#             # 严格连续上涨
#             # lastp[:, 0:window-1] > lastp[:, 1:window] for close
#             mask_close = np.all(lastp[:, :window-1] > lastp[:, 1:window], axis=1)
#             mask_high  = np.all(lasth[:, :window-1] > lasth[:, 1:window], axis=1)
#             # mask_low   = np.all(lastl[:, :window-1] > lastl[:, 1:window], axis=1)
#             cond_low = lastl[:, :window-1] > lastl[:, 1:window]
#             cond_vol = lastv[:, :window-1] > lastv[:, 1:window]
#             mask_low_or_vol = np.all(cond_low | cond_vol, axis=1)
#             mask = mask_close & mask_high & mask_low_or_vol
#             if debug:
#                 # logger.debug(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol} cond_low:{np.all(cond_low)} cond_vol:{np.all(cond_vol)}")
#                 # print(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol} cond_low:{cond_low[0, i]} cond_vol:{cond_vol[0, i]}")
#                 print(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol}")

#         if not mask.any():
#             continue

#         # ===== 4️⃣ sum_percent =====
#         compare_low = lastl[:, window-1].copy()
#         compare_low[compare_low==0] = today_low[compare_low==0]  # 避免0
#         sum_percent = ((today_high - compare_low) / compare_low * 100).round(2)
#         sum_percent = sum_percent[mask]

#         # ===== 5️⃣ 构建 df 矩阵 =====
#         df_window = df.iloc[mask].copy()
#         df_window['sum_perc'] = sum_percent
#         df_window = df_window.sort_values('sum_perc', ascending=False)
#         # result_dict[window] = df_window
#         # ===== 修正 window 输出 =====
#         effective_window = window - (0 if use_real_ohlc.any() else 1)
#         result_dict[effective_window] = df_window

#     return result_dict

# def merge_strong_momentum_results(results, min_days=2, columns=['name','lastp1d','lasth1d','lastl1d','sum_percent']):
def merge_strong_momentum_results(results, min_days=winlimit, columns=['sum_perc','slope','vol_ratio','power_idx']):
    """
    将 strong_momentum_strict_single_percent 的结果合并为一个 DataFrame
    - 只保留连续天数 >= min_days
    - 添加一列 'window' 表示连续天数
    - 按 window 从大到小去重，避免重复显示
    """
    merged_list = []
    seen = set()  # 已加入的股票 name

    for window in sorted(results.keys(), reverse=True):  # 大到小
        if window < min_days:
            continue
        df_window = results[window].copy()
        # 过滤已经出现过的股票
        df_window = df_window[~df_window['name'].isin(seen)]
        if df_window.empty:
            continue
        df_window['win'] = window
        merged_list.append(df_window)
        seen.update(df_window['name'].tolist())

    if merged_list:
        merged_df = pd.concat(merged_list, ignore_index=False)
        merged_df = merged_df.sort_values(['win','sum_perc'], ascending=[False, False])
        return merged_df[columns + ['win']]
    else:
        return pd.DataFrame(columns=columns + ['win'])

def get_top_20(top_all):
    # 精选 Top 20
    top_20 = top_all.query('power_idx > 1.5 and win_upper >= 1').copy()
    top_20['final_score'] = top_20['TrendS'].astype(float) * 0.4 + top_20['power_idx'] * 30 + top_20['gem_score'] * 0.3
    top_20 = top_20.sort_values('final_score', ascending=False).head(20)
    return top_20
    
def save_top_all_to_hdf(top_all, file_path=r'g:\top_all.h5'):
    # 如果 top_all 是字典，先合并成一个大的 DataFrame，或者逐个处理
    if isinstance(top_all, dict):
        # 推荐：先合并，方便后续统一管理
        df_to_save = pd.concat(top_all.values(), keys=top_all.keys())
    else:
        df_to_save = top_all.copy()

    # --- 核心修复逻辑 ---
    # 找到所有 object 类型的列（包括那个报错的 'kind'）
    for col in df_to_save.select_dtypes(include=['object']).columns:
        # 强制转换为字符串，并将 NaN 填充为空字符串，确保类型纯净
        df_to_save[col] = df_to_save[col].astype(str).replace('nan', '')

    try:
        # 使用 blosc 压缩可以大幅减小体积，complevel=9 是最高压缩率
        df_to_save.to_hdf(file_path, key='top_all', mode='w', format='table', complib='blosc', complevel=9)
        print(f"Successfully saved to {file_path} 读取: pd.read_hdf(r'g:\top_all.h5', 'top_all')")
    except Exception as e:
        print(f"Table format failed: {e}. Trying fixed format... 读取: pd.read_hdf(r'g:\top_all.h5', 'top_all') ")
        # 如果 table 格式依然报错，使用 fixed 格式（兼容性最强，但不开启搜索索引）
        df_to_save.to_hdf(file_path, key='top_all', mode='w', format='fixed')

def align_sum_percent(df, merged_df):
    """
    将 merged_df 的 sum_percent 和 window 对齐到原始 df
    - df: 原始 DataFrame，index 为 code 或包含 'code' 列
    - merged_df: merged strong momentum DataFrame，index 为 code
    - 对缺失的 sum_percent 填 0，window 填 NaN
    """
    df_copy = df.copy()
    
    # 如果 df 没有 code 作为索引，则设为索引
    if 'code' in df_copy.columns and df_copy.index.name != 'code':
        df_copy = df_copy.set_index('code')

    # # 对齐 sum_percent 和 window
    # df_copy['sum_perc'] = merged_df['sum_perc'].reindex(df_copy.index).fillna(0)
    # df_copy['win'] = merged_df['win'].reindex(df_copy.index).replace([np.inf, -np.inf], 0).fillna(0).astype(int)
    # 需要对齐的列
    cols_to_align = ['sum_perc', 'slope', 'vol_ratio', 'power_idx', 'win']

    if not merged_df.index.is_unique:
        # dup = merged_df.index[merged_df.index.duplicated()]
        # merged_df = (
        #         merged_df
        #         .sort_values(['win', 'sum_perc'], ascending=[True, False])
        #         .drop_duplicates(subset='code', keep='first')
        #     )
        merged_df = merged_df.sort_values(['win', 'sum_perc'], ascending=[False, False])
        merged_df = merged_df[~merged_df.index.duplicated(keep='first')]
        logger.warning(
            f"align_sum_percent: merged_df duplicate code detected: "
            f"{merged_df[:3]} ..."
        )

    for col in cols_to_align:
        if col in merged_df.columns:
            df_copy[col] = merged_df[col].reindex(df_copy.index) \
                                        .replace([np.inf, -np.inf], 0) \
                                        .fillna(0)
            if col == 'win':
                df_copy[col] = df_copy[col].astype(int)  # win 需要整数
            else:
                df_copy[col] = df_copy[col].round(2)    # 其他列保留两位小数
    
    return df_copy

def _prepare_runtime_state(
    logger, g_values, flag,
    resample, market, st_key_sort,
    marketInit, marketblk
):
    if not flag.value:
        # Check if we should wait or exit
        for _ in range(3): # Reduced from 5 to 3 for faster response
            if flag.value:
                break
            time.sleep(1)
        
        if not flag.value:
            # If still False after wait, return EXIT to break the main loop
            return None, None, None, "EXIT"
        return None, None, None, "PAUSE"

    new_resample = g_values.getkey("resample") or "d"
    new_market = g_values.getkey("market", marketInit)
    new_sort = g_values.getkey("st_key_sort", st_key_sort)

    if new_resample != resample or new_market != market:
        logger.info(
            f"runtime changed reset: market {market}->{new_market}, "
            f"resample {resample}->{new_resample}"
        )
        return new_resample, new_market, new_sort, "RESET"

    if new_sort != st_key_sort:
        return resample, market, new_sort, "SORT_ONLY"

    return resample, market, st_key_sort, "RUN"

def _handle_init_tdx(
    logger, g_values, market, resample,
    flag, duration_sleep_time, ramdisk_dir
):
    today = cct.get_today()
    now_time = cct.get_now_time_int()

    if (
        g_values.getkey("tdx.init.done") is True
        and g_values.getkey("tdx.init.date") == today
    ):
        return False

    if not clean_expired_tdx_file(
        logger, g_values,
        cct.get_trade_date_status,
        cct.get_today,
        cct.get_now_time_int,
        cct.get_ramdisk_path,
        ramdisk_dir
    ):
        logger.info(f"{today} 清理未完成，跳过 init_tdx")
        for _ in range(30):
            if not flag.value:
                break
            time.sleep(1)
        return False

    with timed_ctx("init_tdx_total", warn_ms=1000):

        top_now = tdd.getSinaAlldf(
            market=market,
            vol=ct.json_countVol,
            vtype=ct.json_countType
        )

        resamples = ['d','2d', '3d', 'w', 'm'] if now_time <= 900 else ['3d']

        for res_m in resamples:
            if res_m == resample:
                continue
            if cct.get_now_time_int() > 905:
                break
            with timed_ctx(f"init_tdx_{res_m}", warn_ms=1000):
                tdd.get_append_lastp_to_df(
                    top_now,
                    dl=ct.Resample_LABELS_Days[res_m],
                    resample=res_m
                )

    g_values.setkey("tdx.init.done", True)
    g_values.setkey("tdx.init.date", today)
    logger.info(f"{today} init_tdx 完成")

    for _ in range(duration_sleep_time):
        if not flag.value:
            break
        time.sleep(1)

    return True

def print_strong_stocks_by_window(results, columns=['name','lastp1d','lasth1d','lastl1d','sum_perc'], top_n=None):
    """
    按连续天数从大到小去重显示股票，避免重复显示
    
    参数：
    - results: dict, key=连续天数, value=对应DataFrame
    - columns: list, 要显示的列
    - top_n: int 或 None, 每个窗口显示前 N 条股票，None 显示全部
    """

    logger = LoggerFactory.getLogger()
    seen = set()  # 已加入的股票

    for window in sorted(results.keys(), reverse=True):  # 从大到小
        df_window = results[window].copy()
        # 过滤已经出现过的股票
        df_window = df_window[~df_window['name'].isin(seen)]
        if df_window.empty:
            continue
        total_count = len(df_window)
        logger.info(f"\n连续 {window} 天高低收盘升高的股票，总数：{total_count}")
        if top_n is not None:
            logger.info(df_window[columns].head(top_n))
        else:
            logger.info(df_window[columns])

        # 添加到已见集合，避免重复
        seen.update(df_window['name'].tolist())
    return seen

def check_code_vect_sum_opt(code,top_all,resample='d'):
    if not isinstance(code,list):
        code_list = [code]
    else:
        code_list = code

    # for co in code_list:
    #     # data_tw = get_vect_daily_data(top_all,code_list)
    #     print(f'code: {co}  ---------------------------')
    # 
    #     vect_daily_t = tdd.generate_df_vect_daily_features(top_all.loc[[co]])
    #     data_tw  = pd.DataFrame(vect_daily_t)
    #     print(f'dump_vect_daily_ohlcv: {tdd.dump_vect_daily_ohlcv(vect_daily_t, max_days=cct.compute_lastdays)}')
    #     # data_tw = get_vect_daily_data(top_all,[co])
    #     if resample == 'd':
    #         results_tw = strong_momentum_today_plus_history_sum_opt(data_tw, max_days=cct.compute_lastdays,debug=True)
    #     else:
    #         # results_tw = strong_momentum_large_cycle(data_tw, max_days=cct.compute_lastdays,debug=True)
    #         results_tw = strong_momentum_large_cycle_vect(data_tw, max_days=cct.compute_lastdays,debug=True)
    #     print_strong_stocks_by_window(results_tw, top_n=10)
    #     print(f'data: resample: {resample} \n')
    #     print(f'code: {co}  ---------------------------')

    print(f'code: {code_list}  ---------------------------')

    vect_daily_t = tdd.generate_df_vect_daily_features(top_all.loc[code_list])
    data_tw  = pd.DataFrame(vect_daily_t)
    print(f'dump_vect_daily_ohlcv: {tdd.dump_vect_daily_ohlcv(vect_daily_t, max_days=cct.compute_lastdays)}')
    # data_tw = get_vect_daily_data(top_all,[co])
    if resample == 'd':
        results_tw = strong_momentum_today_plus_history_sum_opt(data_tw, max_days=cct.compute_lastdays,debug=True)
    else:
        # results_tw = strong_momentum_large_cycle(data_tw, max_days=cct.compute_lastdays,debug=True)
        results_tw = strong_momentum_large_cycle_vect(data_tw, max_days=cct.compute_lastdays,debug=True)
    print_strong_stocks_by_window(results_tw, top_n=10)
    print(f'data: resample: {resample} \n')
    print(f'code: {code_list}  ---------------------------')

    # import ipdb;ipdb.set_trace()


def get_vect_daily_data(top_all,code_list):

    vect_daily_t = tdd.generate_df_vect_daily_features(top_all.loc[code_list])
    data_tw  = pd.DataFrame(vect_daily_t)
    return  data_tw

def test_opt(top_all,resample='d',code=None):
    # code_list = ['002151','601360']
    # code_list = ['002151']
    if code is None:
        code_list = ['002151','002796']
    else:
        code_list = [code]
    print(f'resample: {resample} check_code_vect_sum_opt({code_list},top_all,"d")')
    check_code_vect_sum_opt(code_list,top_all,resample)
    # import ipdb;ipdb.set_trace()
    print(f'resample: {resample} ------------------------')
    # data_tw = get_vect_daily_data(top_all,code_list)

    vect_daily_t = tdd.generate_df_vect_daily_features(top_all.loc[code_list])
    # data_t = top_all.loc[code_list]
    data_tw  = pd.DataFrame(vect_daily_t)
    if resample == 'd':
        result_opt = strong_momentum_today_plus_history_sum_opt(data_tw, max_days=cct.compute_lastdays,debug=True)
    else:
        result_opt = strong_momentum_large_cycle_vect(data_tw, max_days=cct.compute_lastdays,debug=True)
    print_strong_stocks_by_window(result_opt, top_n=10)

    print(f'data:\n {tdd.dump_vect_daily_ohlcv(vect_daily_t, max_days=cct.compute_lastdays)}')
    with timed_ctx("plus_history_sum_opt", warn_ms=3000):
        results_t = strong_momentum_today_plus_history_sum_opt(top_all, max_days=cct.compute_lastdays)
    print_strong_stocks_by_window(results_t, top_n=10)

def _run_main_pipeline(
    logger, g_values, queue,
    market, resample, st_key_sort,
    lastpTDX_DF, top_all,
    detect_calc_support_var
):
    with timed_ctx("fetch_market", warn_ms=800):
    
        if market == 'indb':
            indf = get_indb_df()
            top_now = tdd.getSinaAlldf(
                market=indf.code.tolist(),
                vol=ct.json_countVol,
                vtype=ct.json_countType
            )
        else:
            top_now = tdd.getSinaAlldf(
                market=market,
                vol=ct.json_countVol,
                vtype=ct.json_countType
            )

    if top_now.empty:
        return top_all, lastpTDX_DF

    detect_val = (
        detect_calc_support_var.value
        if hasattr(detect_calc_support_var, "value")
        else False
    )

    if top_all.empty:
        if lastpTDX_DF.empty:
            with timed_ctx("get_append_lastp_to_df empty", warn_ms=1000):
                top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
                    top_now,
                    dl=ct.Resample_LABELS_Days[resample],
                    resample=resample,
                    detect_calc_support=detect_val
                )
        else:
            with timed_ctx("get_append_lastp_to_df", warn_ms=1000):
                top_all = tdd.get_append_lastp_to_df(
                    top_now,
                    lastpTDX_DF,
                    detect_calc_support=detect_val
                )
    else:
        with timed_ctx("get_append combine_dataFrame", warn_ms=1000):
            top_all = cct.combine_dataFrame(
                top_all, top_now, col="couts", compare="dff"
            )

    with timed_ctx("calc_pipeline", warn_ms=1000):
        top_all = process_merged_sina_with_history(top_all)

        with timed_ctx("plus_history_sum_opt", warn_ms=3000):
            if resample == 'd':
                # result_opt = strong_momentum_today_plus_history_sum_opt(top_all,max_days=cct.compute_lastdays)
                result_opt = strong_momentum_large_cycle_vect(top_all, max_days=cct.compute_lastdays)
            else:
                result_opt = strong_momentum_large_cycle_vect(top_all,max_days=cct.compute_lastdays)
        clean_sum = merge_strong_momentum_results(result_opt, min_days=winlimit)
        top_all = align_sum_percent(top_all, clean_sum)
        top_all = calc_indicators(top_all, logger, resample)

    sort_cols, sort_keys = ct.get_market_sort_value_key(
        st_key_sort, top_all
    )

    with timed_ctx("getBollFilter", warn_ms=800):
        df_out = (
            stf.getBollFilter(top_all.copy(), resample=resample, down=False)
            .sort_values(by=sort_cols, ascending=sort_keys)
        )
    with timed_ctx("sanitize", warn_ms=800):

        df_out = sanitize(clean_bad_columns(df_out))
        try:
            queue.put(df_out, block=True, timeout=10)
        except Exception as e:
            logger.warning(f"Queue put failed: {e}")

    return top_all, lastpTDX_DF

def get_all_fetch_df(market = 'all', resample= 'd',detect_val = False,status_callback: Callable[[], Any] = None):
    with timed_ctx(f"fetch_market:{market} {resample}", warn_ms=800):
    
        top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)

        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
                                                   resample=resample, detect_calc_support=detect_val)

    with timed_ctx("sina_with_history", warn_ms=1000):
        top_all = process_merged_sina_with_history(top_all)
    time_sum = time.time()
    with timed_ctx("calc_indicators", warn_ms=1000):
        top_all = calc_indicators(top_all, logger, resample)
    with timed_ctx("plus_history_sum_opt", warn_ms=1000):
        if resample == 'd':
            # result_opt = strong_momentum_today_plus_history_sum_opt(top_all,max_days=cct.compute_lastdays)
            result_opt = strong_momentum_large_cycle_vect(top_all,max_days=cct.compute_lastdays)
        else:
            result_opt = strong_momentum_large_cycle_vect(top_all,max_days=cct.compute_lastdays)
    with timed_ctx("merge_strong_momentum_results_opt", warn_ms=1000):
        clean_sum = merge_strong_momentum_results(result_opt,min_days=winlimit)
        top_all = align_sum_percent(top_all,clean_sum)
    logger.info(f'clean_sum: {time.time() - time_sum:.2f}')
    with timed_ctx("build_hma_and_trendscore", warn_ms=1000):
        top_all = build_hma_and_trendscore(top_all,status_callback=status_callback)
    top_temp = top_all.copy()
    df_all = clean_bad_columns(top_temp)
    df_all = sanitize(df_all)

    # inside update_tree() to eliminate cross-process proxy overhead.
    with timed_ctx("format_floats", warn_ms=800):
        df_all = format_floats(df_all)
    return df_all
    
def fetch_and_process_timed_ctx(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
# def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
                      flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
                      marketInit: str = "all", marketblk: str = "boll",
                      duration_sleep_time: int = 120, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
    logger = LoggerFactory.getLogger()
    if log_level:
        logger.setLevel(log_level.value)

    g_values = cct.GlobalValues(shared_dict)
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", marketInit)
    st_key_sort = g_values.getkey("st_key_sort", "3 0")

    top_all = pd.DataFrame()
    lastpTDX_DF = pd.DataFrame()
    START_INIT = 0

    while True:
        try:
            time_s = time.time()

            resample, market, st_key_sort, state = _prepare_runtime_state(
                logger, g_values, flag,
                resample, market, st_key_sort,
                marketInit, marketblk
            )

            if state == "EXIT":
                logger.info("Background Process: EXIT signal received, stopping loop.")
                break

            if state in ("PAUSE", "RESET"):
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                START_INIT = 0
                continue

            if (
                cct.get_trade_date_status()
                and START_INIT > 0
                and 830 <= cct.get_now_time_int() <= 915
            ):
                if _handle_init_tdx(
                    logger, g_values, market, resample,
                    flag, duration_sleep_time, ramdisk_dir
                ):
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()
                    START_INIT = 0
                continue

            if START_INIT > 0 and not cct.get_work_time():
                time.sleep(5)
                continue

            top_all, lastpTDX_DF = _run_main_pipeline(
                logger, g_values, queue,
                market, resample, st_key_sort,
                lastpTDX_DF, top_all,
                detect_calc_support_var
            )

            START_INIT = 1
            cct.print_timing_summary()
            cct.df_memory_usage(top_all)
            logger.info(
                    f"init_tdx 总用时: {time.time() - time_s:.2f}s tdx.init.done:{g_values.getkey('tdx.init.done')} tdx.init.date:{g_values.getkey('tdx.init.date')} "
                )
            time.sleep(1)

        except Exception as e:
            logger.error(f"[fetch_and_process:init_loop] 初始化阶段异常: {type(e).__name__}: {e}")
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            time.sleep(duration_sleep_time)

def get_status(status_callback):
    """
    统一读取 status：
    - None        → 0
    - mp.Value    → value
    - callable    → callable()
    - 其他        → bool 转 int
    """
    if status_callback is None:
        return 0

    # multiprocessing.Value / Manager.Value
    if hasattr(status_callback, "value"):
        return int(status_callback.value)

    # callable（不推荐，但兼容）
    if callable(status_callback):
        try:
            return int(status_callback())
        except Exception:
            return 0

    return int(bool(status_callback))



# def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
#                       flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
#                       marketInit: str = "all", marketblk: str = "boll",
#                       duration_sleep_time: int = 120, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
def fetch_and_process(
    shared_dict: Dict[str, Any],
    queue: Any,
    blkname: str = "boll", 
    flag: Any = None,
    log_level: Any = None,
    detect_calc_support_var: Any = None,
    marketInit: str = "all",
    marketblk: str = "boll",
    duration_sleep_time: int = 120,
    ramdisk_dir: str = cct.get_ramdisk_dir(),
    status_callback: Callable[[], Any] = None,  # 新增回调参数
    single = False
) -> None:
    """
    fetch_and_process 任务函数

    status_callback: 可选函数，返回状态信息，例如 self.tip_var.get()
    """
    """后台数据获取与处理进程"""
    logger = LoggerFactory.getLogger()
    if log_level is not None:
        logger.setLevel(log_level.value)
    
    logger.info(f"子进程开始，日志等级: {log_level.value if hasattr(log_level, 'value') else log_level} duration_sleep_time:{duration_sleep_time}")
    print(f'single:{single}')
    START_INIT = 0
    g_values = cct.GlobalValues(shared_dict)
    resample = g_values.getkey("resample") or "d"
    market = g_values.getkey("market", marketInit)
    blkname = g_values.getkey("blkname", marketblk)
    st_key_sort = g_values.getkey("st_key_sort", "3 0")
    logger.info(f"当前选择市场: {market}, blkname={blkname} st_key_sort:{st_key_sort}")
    
    lastpTDX_DF, top_all = pd.DataFrame(), pd.DataFrame()
    detect_calc_support_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False
    
    # RealtimeDataService is now handled by the Main UI process to save memory
    logger.info("ℹ️ fetch_and_process running in data-only mode (IPC via Queue)")

    logger.info(f"init resample: {resample} flag: {flag.value if flag else 'None'} detect_calc_support: {detect_calc_support_val}")
    last_status = get_status(status_callback)
    loop_counter = 0  # 循环计数
    df_all = None
    while True:
        try:
            time_s = time.time()
            if not flag.value:   # 停止刷新
                if g_values.getkey('state') == 'EXIT':
                    logger.info("Background Process: EXIT state detected, breaking loop.")
                    break
                for _ in range(5):
                    if not flag.value: break
                    time.sleep(1)
                continue
            elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                top_now = pd.DataFrame()
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(f'resample : new resample : {g_values.getkey("resample")} last resample : {resample} top_now:{len(top_now)} top_all:{len(top_all)} lastpTDX_DF:{len(lastpTDX_DF)}')
            elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                # logger.info(f'market : new : {g_values.getkey("market")} last : {market} ')
                top_now = pd.DataFrame()
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(f'market : new resample: {g_values.getkey("market")} last resample: {resample} top_now:{len(top_now)} top_all:{len(top_all)} lastpTDX_DF:{len(lastpTDX_DF)}')
            elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                # logger.info(f'st_key_sort : new : {g_values.getkey("st_key_sort")} last : {st_key_sort} ')
                st_key_sort = g_values.getkey("st_key_sort")
            elif get_status(status_callback) != last_status:
                last_status = get_status(status_callback)
            elif cct.get_trade_date_status() and START_INIT > 0 and cct.start_init_tdx_time <= cct.get_now_time_int() <= 900:
                today = cct.get_today()
                # 0️⃣ init 今天已经完成 → 直接跳过
                # 1️⃣ 清理（未完成 → 不允许 init）
                # if not clean_expired_tdx_file(logger, g_values):
                if not clean_expired_tdx_file(logger, g_values, cct.get_trade_date_status, cct.get_today, cct.get_now_time_int, cct.get_ramdisk_path, ramdisk_dir):
                    logger.info(f"{today} 清理尚未完成，跳过 init_tdx")
                    # 5️⃣ 节流
                    for _ in range(duration_sleep_time):
                        if not flag.value:
                            break
                        time.sleep(1)
                    continue
                else:
                    logger.debug(f"{today} 清理已完成，进入init_tdx")
                    time.sleep(5)
                    
                if (
                    g_values.getkey("tdx.init.done") is True
                    and g_values.getkey("tdx.init.date") == today
                ):
                    continue

                # 2️⃣ 再次确认时间（防止跨 09:15）
                now_time = cct.get_now_time_int()
                if now_time > 900:
                    logger.info(
                        f"{today} 已超过初始化截止时间 {now_time}"
                    )
                    continue

                # 3️⃣ 正式 init（只会执行一次）
                time_init = time.time()
                START_INIT = 0

                top_now = tdd.getSinaAlldf(
                    market=market,
                    vol=ct.json_countVol,
                    vtype=ct.json_countType
                )

                if now_time <= 835:
                    resamples = ['2d','3d', 'w', 'm','d']
                else:
                    resamples = ['2d','3d','d']

                init_res_m = resample
                for res_m in resamples:
                    time_init_m = time.time()
                    # if res_m != g_values.getkey("resample"):
                    now_time = cct.get_now_time_int()
                    if now_time <= 905:
                        init_res_m = resample
                        logger.info(f"start init_tdx resample: {res_m}")
                        tdd.get_append_lastp_to_df(
                            top_now,
                            dl=ct.Resample_LABELS_Days[res_m],
                            resample=res_m)
                    else:
                        init_res_m = resample
                        logger.info(f'resample:{res_m} now_time:{now_time} > 905 终止初始化 init_tdx 用时:{time.time()-time_init_m:.2f}')
                        break
                    logger.info(f'resample:{res_m} init_tdx 用时:{time.time()-time_init_m:.2f}')
                #还原最后的初始化的init_res_m
                resample = init_res_m
                # 4️⃣ 关键：标记 init 已完成（跨循环）
                g_values.setkey("tdx.init.done", True)
                g_values.setkey("tdx.init.date", today)
                top_all = pd.DataFrame()
                lastpTDX_DF = pd.DataFrame()
                logger.info(
                    f"init_tdx 总用时: {time.time() - time_init:.2f}s tdx.init.done:{g_values.getkey('tdx.init.done')} tdx.init.date:{g_values.getkey('tdx.init.date')} "
                )

                # 5️⃣ 节流
                for _ in range(duration_sleep_time):
                    if not flag.value:
                        break
                    time.sleep(1)
                continue

            elif START_INIT > 0 and (not cct.get_work_time()):
                for _ in range(5):
                    if not flag.value or get_status(status_callback) != last_status:
                        break
                    time.sleep(1)
                print(".", end=' ')
                continue
            else:
                logger.info(f'start work : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')

            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", marketInit)        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", marketblk)  # 对应的 blk 文件
            st_key_sort = g_values.getkey("st_key_sort", st_key_sort)  # 对应的 blk 文件
            logger.info(f"resample Main  market : {market} resample: {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            if market == 'indb':
                with timed_ctx(f"fetch_market:{market} {resample}", warn_ms=800):
                    indf = get_indb_df()
                    stock_code_list = indf.code.tolist()
                
                    top_now = tdd.getSinaAlldf(market=stock_code_list,vol=ct.json_countVol, vtype=ct.json_countType)
            else:
                with timed_ctx(f"fetch_market:{market} {resample}", warn_ms=800):
                
                    top_now = tdd.getSinaAlldf(market=market,vol=ct.json_countVol, vtype=ct.json_countType)
            if top_now.empty:
                logger.info("top_now.empty no data fetched")
                time.sleep(duration_sleep_time)
                continue
            logger.info(f"resample Main  top_now:{len(top_now)} market : {market}  resample: {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            # 合并与计算
            detect_val = detect_calc_support_var.value if hasattr(detect_calc_support_var, 'value') else False

            if top_all.empty:
                if lastpTDX_DF.empty:
                    with timed_ctx("get_append_lastp_to_df empty", warn_ms=1000):
                        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
                                                                   resample=resample, detect_calc_support=detect_val)
                else:
                    with timed_ctx("get_append combine_dataFrame", warn_ms=1000):
                        top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF, detect_calc_support=detect_val)
            else:
                with timed_ctx("get_append combine_dataFrame", warn_ms=1000):
                    top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")

            time_sum = time.time()
            with timed_ctx("calc_indicators", warn_ms=1000):
                top_all = calc_indicators(top_all, logger, resample)
            #step volume
            with timed_ctx("sina_with_history", warn_ms=1000):
                top_all = process_merged_sina_with_history(top_all)
            logger.info(f"resample Main  top_all:{len(top_all)} market : {market}  resample: {resample}  status_callback: {get_status(status_callback)} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            # top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                # --- [新增] 注入 0d 数据列，使 consecutive_above 生效 ---
                # 只有在盘中且有实时行情时注入
                if 'now' in top_all.columns:
                    top_all['lastp0d'] = top_all['now']
                    top_all['lasth0d'] = top_all['high']
                    top_all['lastl0d'] = top_all['low']
                    top_all['lasto0d'] = top_all['open']
                    top_all['lastv0d'] = top_all['vol'] if 'vol' in top_all.columns else top_all['volume']
                    # 为压力位注入 0d (复用昨日压力位作为今日参考线)
                    if 'upper1' in top_all.columns: top_all['upper0'] = top_all['upper1']
                    if 'ma51d' in top_all.columns: top_all['ma50d'] = top_all['ma51d']
                    if 'high41' in top_all.columns: top_all['high40'] = top_all['high41']

                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            # test_opt(top_all,resample)
            
            with timed_ctx("plus_history_sum_opt", warn_ms=1000):
                if resample == 'd':
                    # result_opt = strong_momentum_today_plus_history_sum_opt(top_all,max_days=cct.compute_lastdays)
                    result_opt = strong_momentum_large_cycle_vect(top_all,max_days=cct.compute_lastdays,winlimit=1)
                else:
                    # result_opt = strong_momentum_large_cycle_vect(top_all,max_days=cct.compute_lastdays,winlimit=1)
                    result_opt = strong_momentum_large_cycle_vect_new(top_all,max_days=cct.compute_lastdays,winlimit=1)
            with timed_ctx("merge_strong_momentum_results_opt", warn_ms=1000):
                # print(get_vect_daily_data(top_all,['002455']).T.to_string())
                clean_sum = merge_strong_momentum_results(result_opt,min_days=winlimit)
                top_all = align_sum_percent(top_all,clean_sum)

            with timed_ctx("consecutive_above_win_upper", warn_ms=1000):
                top_all = strong_momentum_large_cycle_vect_consecutive_above(top_all, price_col='lastp', upper_col='upper',max_days=cct.compute_lastdays)
            
            with timed_ctx("consecutive_above_single_w_upper", warn_ms=1000):
                top_all = strong_momentum_large_cycle_vect_consecutive_above_single(top_all, price_col='lastp', upper_col='upper',max_days=cct.compute_lastdays)
            with timed_ctx("consecutive_above_wm5_upper", warn_ms=1000):
                top_all = strong_momentum_large_cycle_vect_consecutive_above_m5(top_all, price_col='lastp', upper_col='upper',max_days=cct.compute_lastdays)
            with timed_ctx("scoring_momentum_pullback_system_base", warn_ms=1000):
                top_all = scoring_momentum_pullback_system_base(top_all,max_days=cct.compute_lastdays)
            # with timed_ctx("scoring_momentum_pullback_system_base_realtime", warn_ms=1000):
                # top_all = scoring_momentum_pullback_system_base_realtime(top_all,max_days=cct.compute_lastdays)
            with timed_ctx("scoring_momentum_pullback_system_top", warn_ms=1000):
                top_all = scoring_momentum_pullback_system_top(top_all,max_days=cct.compute_lastdays)
            with timed_ctx("buy_sell_score_momentum_vect", warn_ms=1000):
                top_all = buy_sell_score_momentum_vect(top_all,max_days=cct.compute_lastdays)
            # print(top_all.loc['920427', get_vect_col(upper='upper',max_days=cct.compute_lastdays)].T.to_string())
            # cct.print_timing_summary()
          
            logger.info(f'clean_sum: {time.time() - time_sum:.2f}')
            with timed_ctx("build_hma_and_trendscore", warn_ms=1000):
                top_all = build_hma_and_trendscore(top_all,status_callback=status_callback)

            top_temp = top_all.copy()
            with timed_ctx("getBollFilter", warn_ms=800):
                top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            
            df_all = clean_bad_columns(top_temp)
            df_all = sanitize(df_all)
            
            # 🛡️ 动态列裁剪 (Dynamic Column Trimming)
            # 使用 try-except 包装，防止 Manager 失效时崩溃
            try:
                # keep_all = shared_dict.get('keep_all_columns')
                keep_all = shared_dict.get('keep_all_columns', True)
            except (BrokenPipeError, EOFError, OSError, AttributeError) as e:
                logger.error(f"shared_dict.get('keep_all_columns') 失败: {type(e).__name__}: {e}")
                keep_all = True  # Manager 失效时使用默认值
                
            if not keep_all:
                try:
                    required_cols = shared_dict.get('required_cols', [])
                except (BrokenPipeError, EOFError, OSError, AttributeError) as e:
                    logger.error(f"[data_utils:1537] shared_dict.get('required_cols') 失败: {type(e).__name__}: {e}")
                    required_cols = []  # Manager 失效时使用默认空列表
                    
                if required_cols:
                    # 获取 df_all 中存在的列
                    actual_keep = [c for c in required_cols if c in df_all.columns]
                    # 如果结果集包含基本的 'name' 列，确保裁剪是安全的
                    if 'name' in actual_keep or 'code' in actual_keep:
                        df_all = df_all[actual_keep]
                    else:
                        logger.debug("Dynamic Trimming: required_cols missing core columns, skipping trim.")
            else:
                logger.debug("Dynamic Trimming: 'keep_all_columns' active, skipping trim.")

            # 🔌 RealtimeDataService updates are now handled by the Main process
            # inside update_tree() to eliminate cross-process proxy overhead.
            with timed_ctx("format_floats", warn_ms=800):
                df_all = format_floats(df_all)
            # 🔌 [REFINED] Send dual snapshots (Full for Cache, Filtered for UI)
            # This ensures MinuteKlineCache stays up-to-date for ALL stocks
            # while the UI remains responsive and filtered.
            data_packet = {
                'full_snapshot': top_all,
                'filtered_ui_data': df_all
            }
            try:
                queue.put(data_packet, block=True, timeout=10)
            except Exception as e:
                logger.warning(f"Queue put failed: {e}")
            gc.collect(0)
            # cct.print_timing_summary()
            cct.df_memory_usage(df_all)

            logger.debug(f"code: 920427 : {top_all.loc['920427',['win_upper','win_upper1','win_upper2','w_upper','wm5_upper','gem_score','gem_tops','w_upper']]}")
            logger.info(f"gem_score: {top_all.sort_values(by='gem_score', ascending=False).loc[:,['name','gem_tops','gem_score','w_upper']][:5]}")
            logger.info(f"gem_tops: {top_all.sort_values(by='gem_tops', ascending=False).loc[:,['name','gem_tops','gem_score','w_upper']][:5]}")

            extra_cols = ['win','sum_perc', 'slope', 'vol_ratio', 'power_idx']
            df_show = top_temp.loc[:, ["name"] + sort_cols[:7] + extra_cols].head(10)
         
            # --- 智能频率自适应 (Intelligent Frequency Adaptation) ---
            # 1. 动态获取配置
            sina_limit_val = g_values.getkey("sina_limit_time")
            if sina_limit_val is None:
                sina_limit_val = cct.sina_limit_time if hasattr(cct, 'sina_limit_time') else 30
            sina_limit = int(sina_limit_val) if not pd.isna(sina_limit_val) else 30

            cfg_sleep_val = g_values.getkey("duration_sleep_time")
            if cfg_sleep_val is None:
                cfg_sleep_val = duration_sleep_time
            cfg_sleep = int(cfg_sleep_val) if not pd.isna(cfg_sleep_val) else 120

            # 2. 判断是否为交易时段 (9:15 - 15:00)
            now_int = cct.get_now_time_int()
            is_trading_time = cct.get_trade_date_status() and (915 <= now_int <= 1505)


            loop_sleep_time = cfg_sleep

            if logger.level <= LoggerFactory.INFO:
               logger.info(f"[FreqAdapt] Trading:{is_trading_time} SinaLimit:{sina_limit}s CfgSleep:{cfg_sleep}s -> ActualSleep:{loop_sleep_time}s")

            # 4. 执行分段 Sleep (保持灵敏度)
            if 915 < cct.get_now_time_int() < 945:
                loop_sleep_time = 30
                sleep_step = 0.5
            else:
                sleep_step = 1
            # print(f'loop_sleep_time: {loop_sleep_time} sleep_step:{sleep_step} looptime: {loop_sleep_time / sleep_step}')
            stop_conditions = [
                lambda: not flag.value,
                lambda: not cct.get_work_time(),
                lambda: get_status(status_callback) != last_status,
                lambda: g_values.getkey("resample") and g_values.getkey("resample") != resample,
                lambda: g_values.getkey("market") and g_values.getkey("market") != market,
                lambda: g_values.getkey("st_key_sort") and g_values.getkey("st_key_sort") != st_key_sort
            ]

            # 周期性心跳日志 - 每 10 秒输出一次状态
            heartbeat_interval = 10  # 秒
            sleep_elapsed = 0
            START_INIT = 1

            if logger.level <= LoggerFactory.INFO:
                logger.debug(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
                logger.info(f'resample: {resample} top_temp :  {df_show.to_string()} shape : {top_temp.shape} detect_calc_support:{detect_val}')
                logger.info(f'process now: {cct.get_now_time_int()} resample:{resample} Main:{len(df_all)} looptime: {loop_sleep_time / sleep_step} keep_all:{keep_all}  sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {START_INIT} {cct.get_now_time()} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            else:
                print(f"gem_score: {top_all.sort_values(by='gem_score', ascending=False).loc[:,['name','gem_tops','gem_score','w_upper']][:5]}")
                print(f"gem_tops: {top_all.sort_values(by='gem_tops', ascending=False).loc[:,['name','gem_tops','gem_score','w_upper']][:5]}")
                print(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
                # print(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape} detect_calc_support:{detect_val}')
                print(
                    f"resample: {resample}\n"
                    f"top_temp:\n{df_show.to_string()}\n"
                    f"shape: {top_temp.shape}\n"
                    f"detect_calc_support: {detect_val}"
                )
                print(f'process now: {cct.get_now_time_int()} resample:{resample} Main:{len(df_all)} looptime: {loop_sleep_time / sleep_step} keep_all:{keep_all} sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {START_INIT} {cct.get_now_time()} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')

            if single:
                cct.print_timing_summary()
                break   

            for _ in range(int(loop_sleep_time / sleep_step)):
                if any(cond() for cond in stop_conditions):
                    break
                time.sleep(sleep_step)
                sleep_elapsed += sleep_step
                # 每 heartbeat_interval 秒输出一次心跳
                if sleep_elapsed % heartbeat_interval == 0:
                    print("*", end=' ')
                    logger.debug(f"[心跳] resample={resample} 等待中... {sleep_elapsed}/{int(loop_sleep_time)}s flag={flag.value}")
        except Exception as e:
            logger.error(f"[fetch_and_process:main_loop] resample={resample} 主循环异常: {type(e).__name__}: {e}")
            logger.error(f"完整堆栈:\n{traceback.format_exc()}")
            time.sleep(duration_sleep_time)

    return df_all