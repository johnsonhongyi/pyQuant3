# -*- coding:utf-8 -*-
import time
import gc
import pandas as pd
import numpy as np
from typing import Any, Optional, Union, Dict, List, Callable
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JohnsonUtil.commonTips import timed_ctx
from JohnsonUtil import LoggerFactory
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from tdx_utils import clean_bad_columns, sanitize, clean_expired_tdx_file
from db_utils import get_indb_df

winlimit = cct.winlimit
START_INIT = 0
PIPE_NAME = r"\\.\pipe\my_named_pipe"
logger = LoggerFactory.getLogger()

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

    if 'vol' not in top_all.columns or (top_all['volume'] > 500).any():
        top_all['vol'] = top_all['volume'] 
        
    top_all['amount'] = top_all['vol'] * top_all['close']
    # 这里的 volume 将被更新为虚拟量比信号强度
    top_all['volume'] = calc_compute_volume(top_all, logger, resample=resample, virtual=True)
    # 同步到 ratio 列，确保兼容性 是换手率,不能同步Volume
    # top_all['ratio'] = top_all['volume']

    now_time = cct.get_now_time_int()
    if cct.get_trade_date_status():
        logger.info(f'lastbuy :{"lastbuy" in top_all.columns}')
        if 'lastbuy' in top_all.columns:
            if 915 < now_time < 930:
                top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            elif 926 < now_time < 1455:
                top_all['dff'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
            else:
                top_all['dff'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
                top_all['dff2'] = ((top_all['buy'] - top_all['lastbuy']) / top_all['lastbuy'] * 100).round(1)
        else:
            top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
            top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
    else:
        top_all['dff'] = ((top_all['buy'] - top_all['llastp']) / top_all['llastp'] * 100).round(1)
        top_all['dff2'] = ((top_all['buy'] - top_all['lastp']) / top_all['lastp'] * 100).round(1)
        
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
    upper_1d = daily_feat['upper1d']
    close_1d = daily_feat['lastp1d']
    amount_1d = daily_feat['lastv1d']
    eval_1d = int(daily_feat['eval1d'])
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
    eval_1d = df['EVAL_STATE'].astype(int)
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
    eval_1d   = df['eval1d'].astype(int)   # 昨天状态
    eval_2d   = df['eval2d'].astype(int)   # 前天状态
    signal_1d = df['signal1d'].astype(int) # 昨天产生的信号
    ma_ref    = df['ma51d']                # 支撑位
    
    # 3. 核心条件判定
    # 启动：价格突围 + 放量
    cond_trend_start = (curr_c > upper_1d) & (close_1d <= upper_1d) & (curr_a > amount_1d * 1.1)
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

# 使用示例：
# df = pd.DataFrame(vect_daily_t)
# check_real_time(df, ['688239', '601360'])

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


def strong_momentum_today_plus_history_sum_opt(df, max_days=cct.compute_lastdays, winlimit=winlimit,debug=False):
    """
    完全向量化版本，用 NumPy 计算严格连续上涨和 sum_percent 25ms
    """
    result_dict = {}

    # ===== 0️⃣ 判断今天状态，只做一次 =====
    is_trade_day = cct.get_trade_date_status()
    in_market_hours = 915 < cct.get_now_time_int() < 1500
    real_time_mode = is_trade_day and in_market_hours

    ohlc_same_as_last1d = (
        (df['open'] == df.get('lasto1d', df['open'])) &
        (df['low'] == df.get('lastl1d', df['low'])) &
        (df['high'] == df.get('lasth1d', df['high'])) &
        (df['close'] == df.get('lastp1d', df['close']))
    )
    use_real_ohlc = real_time_mode & (~ohlc_same_as_last1d)

    # ===== 1️⃣ 今天数据列 =====
    today_open  = df['open'].where(use_real_ohlc, df['lasto1d']).to_numpy()
    today_high  = df['high'].where(use_real_ohlc, df['lasth1d']).to_numpy()
    today_low   = df['low'].where(use_real_ohlc, df['lastl1d']).to_numpy()
    today_close = df['close'].where(use_real_ohlc, df['lastp1d']).to_numpy()
    # today_vol = df['volume'].where(use_real_ohlc, df['lastv1d']).to_numpy()

    codes = df.index.to_numpy()

    # ===== 2️⃣ 历史收盘/高/低 =====
    # 构建 N x max_days 的 NumPy array
    lastp = np.zeros((len(df), max_days))
    lasth = np.zeros((len(df), max_days))
    lastl = np.zeros((len(df), max_days))
    lastv = np.zeros((len(df), max_days))

    for i in range(1, max_days+1):
        lastp[:, i-1] = df.get(f'lastp{i}d', 0).to_numpy()
        lasth[:, i-1] = df.get(f'lasth{i}d', 0).to_numpy()
        lastl[:, i-1] = df.get(f'lastl{i}d', 0).to_numpy()
        lastv[:, i-1] = df.get(f'lastv{i}d', 0).to_numpy()

    # ===== 3️⃣ 遍历窗口 =====
    start_window = winlimit

    # 盘后：today == last1d，window=1 没有策略意义
    if not use_real_ohlc.any():
        start_window = max(2, winlimit)

    # ===== 3️⃣ 遍历窗口 =====
    for window in range(start_window, max_days+1):
        if window == 1:
            # window=1 特殊处理
            # mask = (today_high > lastp[:, 0]) & (today_close > lastp[:, 0])
            # window=1 特殊处理：实时 vs 收盘后
            mask = np.where(
                use_real_ohlc.to_numpy(),
                (today_high > lastp[:, 0]) & (today_close > lastp[:, 0]),  # 实时 vs 昨天
                (lastp[:, 0] > df.get('lastp2d', lastp[:, 0]).to_numpy()) &
                (lasth[:, 0] > df.get('lasth2d', lasth[:, 0]).to_numpy())  # 收盘后 vs 前天
            )
            if debug:
                # logger.debug(f"use_real_ohlc: {use_real_ohlc.all()} window={window}, mask_close={mask}")
                print(f"use_real_ohlc: {use_real_ohlc.all()} window={window}, mask_close={mask}")

        else:
            # 严格连续上涨
            # lastp[:, 0:window-1] > lastp[:, 1:window] for close
            mask_close = np.all(lastp[:, :window-1] > lastp[:, 1:window], axis=1)
            mask_high  = np.all(lasth[:, :window-1] > lasth[:, 1:window], axis=1)
            # mask_low   = np.all(lastl[:, :window-1] > lastl[:, 1:window], axis=1)
            cond_low = lastl[:, :window-1] > lastl[:, 1:window]
            cond_vol = lastv[:, :window-1] > lastv[:, 1:window]
            mask_low_or_vol = np.all(cond_low | cond_vol, axis=1)
            mask = mask_close & mask_high & mask_low_or_vol
            if debug:
                # logger.debug(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol} cond_low:{np.all(cond_low)} cond_vol:{np.all(cond_vol)}")
                # print(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol} cond_low:{cond_low[0, i]} cond_vol:{cond_vol[0, i]}")
                print(f"use_real_ohlc: {use_real_ohlc.all()} 对比{window-1} vs {window} window={window}, mask_close={mask_close},mask_high={mask_high}, mask_low={mask_low_or_vol}")

        if not mask.any():
            continue

        # ===== 4️⃣ sum_percent =====
        compare_low = lastl[:, window-1].copy()
        compare_low[compare_low==0] = today_low[compare_low==0]  # 避免0
        sum_percent = ((today_high - compare_low) / compare_low * 100).round(2)
        sum_percent = sum_percent[mask]

        # ===== 5️⃣ 构建 df 矩阵 =====
        df_window = df.iloc[mask].copy()
        df_window['sum_perc'] = sum_percent
        df_window = df_window.sort_values('sum_perc', ascending=False)
        # result_dict[window] = df_window
        # ===== 修正 window 输出 =====
        effective_window = window - (0 if use_real_ohlc.any() else 1)
        result_dict[effective_window] = df_window

    return result_dict

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
        for _ in range(5):
            if flag.value:
                break
            time.sleep(1)
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

        resamples = ['d', '3d', 'w', 'm'] if now_time <= 900 else ['3d']

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

    import ipdb;ipdb.set_trace()


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
        queue.put(df_out)

    return top_all, lastpTDX_DF

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
            logger.error("background error", exc_info=True)
            time.sleep(duration_sleep_time)

def wait_or_break(seconds, stop_conditions):
    """
    每秒检查 stop_conditions 列表中任意条件是否为 True，如果为 True 则提前退出循环
    """
    for _ in range(seconds):
        for cond in stop_conditions:
            try:
                if cond():
                    return  # 条件触发，提前退出等待
            except Exception as e:
                logger.warning(f"stop_condition error: {e}")
        time.sleep(1)

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


# ---------- while True 循环 ----------
# # ---------- 停止刷新 ----------
# if not flag.value:
#     # 手动停止，5秒轮询检查是否恢复
#     wait_or_break(5, [lambda: flag.value])
#     continue

# # ---------- 非工作时间暂停 ----------
# if START_INIT > 0 and not cct.get_work_time():
#     # 每秒检查 flag 或工作时间恢复
#     wait_or_break(5, [lambda: flag.value, lambda: cct.get_work_time()])
#     continue

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

    while True:
        try:
            time_s = time.time()
            # status = status_callback.value  # 获取最新状态
            if not flag.value:   # 停止刷新
                   # for _ in range(5):
                   #      if not flag.value: break
                   #      time.sleep(1)
                   wait_or_break(5, [
                       lambda: not flag.value,          # 外部手动停止
                   ])
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
            elif cct.get_trade_date_status() and START_INIT > 0 and 830 <= cct.get_now_time_int() <= 915:
                today = cct.get_today()
                # 0️⃣ init 今天已经完成 → 直接跳过

                # 1️⃣ 清理（未完成 → 不允许 init）
                # if not clean_expired_tdx_file(logger, g_values):
                if not clean_expired_tdx_file(logger, g_values, cct.get_trade_date_status, cct.get_today, cct.get_now_time_int, cct.get_ramdisk_path, ramdisk_dir):
                    logger.info(f"{today} 清理尚未完成，跳过 init_tdx")
                    # 5️⃣ 节流
                    for _ in range(30):
                        if not flag.value:
                            break
                        time.sleep(1)
                    continue

                if (
                    g_values.getkey("tdx.init.done") is True
                    and g_values.getkey("tdx.init.date") == today
                ):
                    continue

                # 2️⃣ 再次确认时间（防止跨 09:15）
                now_time = cct.get_now_time_int()
                if now_time > 915:
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

                if now_time <= 900:
                    resamples = ['3d', 'w', 'm','d']
                else:
                    resamples = ['3d','d']

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

            elif get_status(status_callback) != last_status:
                last_status = get_status(status_callback)

            elif START_INIT > 0 and (not cct.get_work_time()):
                    # logger.info(f'not worktime and work_duration')
                    # for _ in range(5):
                    #     if not flag.value or status_callback.value != last_status:
                    #         break
                    #     time.sleep(1)
                    wait_or_break(5, [
                        lambda: not flag.value,          # 外部手动停止
                        lambda: get_status(status_callback) != last_status,
                    ])
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
            with timed_ctx("sina_with_history", warn_ms=1000):
                top_all = process_merged_sina_with_history(top_all)
            time_sum = time.time()
            with timed_ctx("calc_indicators", warn_ms=1000):
                top_all = calc_indicators(top_all, logger, resample)
            logger.info(f"resample Main  top_all:{len(top_all)} market : {market}  resample: {resample}  status_callback: {get_status(status_callback)} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            # top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            # test_opt(top_all,resample)

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
            with timed_ctx("getBollFilter", warn_ms=800):
                top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            
            df_all = clean_bad_columns(top_temp)
            df_all = sanitize(df_all)
            
            # 🛡️ 动态列裁剪 (Dynamic Column Trimming)
            keep_all = shared_dict.get('keep_all_columns', False)
            if not keep_all:
                required_cols = shared_dict.get('required_cols', [])
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
            queue.put(df_all)
            gc.collect()
            cct.print_timing_summary()
            cct.df_memory_usage(df_all)
            extra_cols = ['win','sum_perc', 'slope', 'vol_ratio', 'power_idx']
            df_show = top_temp.loc[:, ["name"] + sort_cols[:7] + extra_cols].head(10)
            if logger.level <= LoggerFactory.INFO:
                logger.debug(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
                logger.info(f'resample: {resample} top_temp :  {df_show.to_string()} shape : {top_temp.shape} detect_calc_support:{detect_val}')
                logger.info(f'process now: {cct.get_now_time_int()} resample Main:{len(df_all)} sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            else:
                print(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
                # print(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape} detect_calc_support:{detect_val}')
                print(
                    f"resample: {resample}\n"
                    f"top_temp:\n{df_show.to_string()}\n"
                    f"shape: {top_temp.shape}\n"
                    f"detect_calc_support: {detect_val}"
                )
                print(f'process now: {cct.get_now_time_int()} resample Main:{len(df_all)} sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            # --- 智能频率自适应 (Intelligent Frequency Adaptation) ---
            # 1. 动态获取配置
            sina_limit_val = g_values.getkey("sina_limit_time")
            if sina_limit_val is None:
                sina_limit_val = cct.sina_limit_time if hasattr(cct, 'sina_limit_time') else 30
            sina_limit = int(sina_limit_val)

            cfg_sleep_val = g_values.getkey("duration_sleep_time")
            if cfg_sleep_val is None:
                cfg_sleep_val = duration_sleep_time
            cfg_sleep = int(cfg_sleep_val)

            # 2. 判断是否为交易时段 (9:15 - 15:00)
            now_int = cct.get_now_time_int()
            is_trading_time = cct.get_trade_date_status() and (915 <= now_int <= 1500)

            # 3. 动态决定 Loop Sleep Time
            if is_trading_time:
                # 交易时段：优先满足数据源频率 (sina_limit)，确保高颗粒度
                # 取 min(sina_limit, cfg_sleep)，防止配置过大导致漏数据
                loop_sleep_time = min(sina_limit, cfg_sleep)
                if loop_sleep_time < 5: 
                    loop_sleep_time = 5 # 最小保护
                
                # 开盘前夕 (9:15-9:25) 加速刷新 (可选优化)
                if 915 <= now_int < 925:
                   loop_sleep_time = min(loop_sleep_time, 15)
            else:
                # 非交易时段：使用低频刷新，降低资源消耗
                loop_sleep_time = cfg_sleep

            if logger.level <= LoggerFactory.INFO:
               logger.info(f"[FreqAdapt] Trading:{is_trading_time} SinaLimit:{sina_limit}s CfgSleep:{cfg_sleep}s -> ActualSleep:{loop_sleep_time}s")

            # 4. 执行分段 Sleep (保持灵敏度)
            if cct.get_now_time_int() < 945:
                sleep_step = 0.5
            else:
                sleep_step = 1

            stop_conditions = [
                lambda: not flag.value,
                lambda: get_status(status_callback) != last_status,
                lambda: g_values.getkey("resample") and g_values.getkey("resample") != resample,
                lambda: g_values.getkey("market") and g_values.getkey("market") != market,
                lambda: g_values.getkey("st_key_sort") and g_values.getkey("st_key_sort") != st_key_sort
            ]

            for _ in range(int(loop_sleep_time / sleep_step)):
                # if not flag.value:
                #     break
                # elif status_callback.value != last_status:
                #     break
                # elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                #     break
                # elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                #     break
                # elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                #     break
                
                if any(cond() for cond in stop_conditions):
                    break
                # wait_or_break(5, stop_conditions)
                time.sleep(sleep_step)
            START_INIT = 1

        except Exception as e:
            logger.error(f"resample: {resample} Error in background process: {e}", exc_info=True)
            time.sleep(duration_sleep_time)