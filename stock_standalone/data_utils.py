# -*- coding:utf-8 -*-
import time
import gc
import pandas as pd
import numpy as np
from typing import Any, Optional, Union, Dict, List
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JohnsonUtil import LoggerFactory
from JSONData import tdx_data_Day as tdd
from JSONData import stockFilter as stf
from tdx_utils import clean_bad_columns, sanitize, clean_expired_tdx_file
from db_utils import get_indb_df

START_INIT = 0
PIPE_NAME = r"\\.\pipe\my_named_pipe"

def calc_compute_volume(top_all: pd.DataFrame, logger: Any, resample: str = 'd', virtual: bool = True) -> pd.Series:
    """计算成交量（虚拟量或原始量）"""
    ratio_t = cct.get_work_time_ratio(resample=resample)
    logger.info(f'ratio_t: {round(ratio_t, 2)}')

    if virtual:
        # 虚拟量 = volume / last6vol / ratio_t
        volumes = top_all['volume'] / top_all['last6vol'] / ratio_t
        return volumes.round(1)
    else:
        # 原始量 = 虚拟量 * last6vol * ratio_t
        volumes = top_all['volume'] * top_all['last6vol'] * ratio_t
        return volumes.round(1)

def calc_indicators(top_all: pd.DataFrame, logger: Any, resample: str) -> pd.DataFrame:
    """指标计算"""
    top_all['volume'] = calc_compute_volume(top_all, logger, resample=resample, virtual=True)

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

    # 2. 条件判定 (基于实时 Tick)
    cond_trend_start = (curr_c > upper_1d) and (close_1d <= upper_1d) and (curr_a > amount_1d * 1.1)
    cond_trend_continue = (curr_c > upper_1d) and (close_1d > upper_1d)
    cond_pullback = (curr_c < close_1d) and (curr_l >= ma10d_curr) and (curr_a < amount_1d)
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
    

def generate_df_vect_daily_features(df, lastdays=5):
    """
    df: 多股票 DataFrame，index 为 (code, date)，多列 open/close/high/low/vol/ma/upper/eval/signal
    lastdays: 提取最近 N 天特征
    返回: 每只股票一行字典，字段格式 lasto1d,lastp1d,...,eval1d,signal1d,...，并带 'code' 字段
    """
    features_list = []
    cols_map = {
        'open': 'lasto',
        'high': 'lasth',
        'low': 'lastl',
        'close': 'lastp',
        'vol': 'lastv',
        'upper': 'upper',
        'ma5d': 'ma5',
        'ma20d': 'ma20',
        'ma60d': 'ma60',
        'perlastp': 'perc',
        'perd': 'per'
    }

    for code, df_stock in df.groupby(level=0):
        feat = {'code': code}  # 添加股票 code
        df_stock = df_stock.sort_index(level=1)
        n_rows = len(df_stock)

        for da in range(1, lastdays + 1):
            for col, prefix in cols_map.items():
                if col in df_stock.columns and da <= n_rows:
                    feat[f'{prefix}{da}d'] = df_stock[col].iloc[-da]
                else:
                    feat[f'{prefix}{da}d'] = 0

            # eval / signal
            for suffix in ['eval', 'signal']:
                colname = f'{suffix}{da}d'
                if colname in df_stock.columns and da <= n_rows:
                    feat[colname] = df_stock[colname].iloc[-da]
                else:
                    feat[colname] = 0
        features_list.append(feat)
    return features_list

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
    # 1. 提取核心变量
    curr_c = df['now']
    curr_o = df['open']
    curr_l = df['low']
    curr_a = df['volume']
    
    # 历史参考值
    upper_1d = df['upper']
    close_1d = df['lastp1d']
    amount_1d = df['lastv1d']
    eval_1d = df['EVAL_STATE'].astype(int)
    ma_ref = df['ma5d'] # 假设 ma5d 是你的生命线

    # 2. 判定条件 (矢量化)
    cond_trend_start = (curr_c > upper_1d) & (close_1d <= upper_1d) & (curr_a > amount_1d * 1.1)
    cond_trend_continue = (curr_c > upper_1d) & (close_1d > upper_1d)
    cond_pullback = (curr_c < close_1d) & (curr_l >= ma_ref) & (curr_a < amount_1d)
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


def strong_momentum_today_plus_history_sum_opt(df, max_days=9):
    """
    向量化优化版本
    - 严格连续 2~max_days 天高低收盘升高
    - sum_percent = 今天 high - lastl{window-1}d 的百分比
    - 避免 low=0，自动替代为当天 low
    """
    result_dict = {}

    for window in range(2, max_days+1):
        df_window = df.copy()
        mask = pd.Series(True, index=df.index)

        # 严格连续升高判断
        for d in range(1, window):
            today_high = df_window['high'] if d == 1 else df_window[f'lasth{d-1}d']
            today_close = df_window['close'] if d == 1 else df_window[f'lastp{d-1}d']
            today_low = df_window['low'] if d == 1 else df_window[f'lastl{d-1}d']

            prev_high = df_window[f'lasth{d}d']
            prev_close = df_window[f'lastp{d}d']
            prev_low = df_window[f'lastl{d}d']

            # 避免缺失或0
            mask &= (today_high > prev_high) & (today_close > prev_close) & (today_low > prev_low) & (prev_low > 0)

        df_window = df_window[mask]
        if df_window.empty:
            continue

        # 计算 sum_percent
        compare_low = df_window.get(f'lastl{window-1}d', df_window['low']).copy()
        mask_zero = compare_low == 0
        compare_low.loc[mask_zero] = df_window.loc[mask_zero, 'low']

        sum_percent = ((df_window['high'] - compare_low) / compare_low * 100).round(2)
        df_window['sum_perc'] = sum_percent

        df_window = df_window.sort_values('sum_perc', ascending=False)
        result_dict[window] = df_window

    return result_dict

# def merge_strong_momentum_results(results, min_days=2, columns=['name','lastp1d','lasth1d','lastl1d','sum_percent']):
def merge_strong_momentum_results(results, min_days=2, columns=['sum_perc']):
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
    
    # 对齐 sum_percent 和 window
    df_copy['sum_perc'] = merged_df['sum_perc'].reindex(df_copy.index).fillna(0)
    df_copy['win'] = merged_df['win'].reindex(df_copy.index).replace([np.inf, -np.inf], 0).fillna(0).astype(int)
    
    return df_copy

def fetch_and_process(shared_dict: Dict[str, Any], queue: Any, blkname: str = "boll", 
                      flag: Any = None, log_level: Any = None, detect_calc_support_var: Any = None,
                      marketInit: str = "all", marketblk: str = "boll",
                      duration_sleep_time: int = 120, ramdisk_dir: str = cct.get_ramdisk_dir()) -> None:
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
    logger.info(f"init resample: {resample} flag: {flag.value if flag else 'None'} detect_calc_support: {detect_calc_support_val}")
    
    while True:
        try:
            time_s = time.time()
            if not flag.value:   # 停止刷新
                   for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                   # logger.info(f'flag.value : {flag.value} 停止更新')
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
            elif START_INIT > 0 and 830 <= cct.get_now_time_int() <= 915:
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
                    resamples = ['d','3d', 'w', 'm']
                else:
                    resamples = ['3d']

                for res_m in resamples:
                    time_init_m = time.time()
                    if res_m != g_values.getkey("resample"):
                        now_time = cct.get_now_time_int()
                        if now_time <= 905:
                            logger.info(f"start init_tdx resample: {res_m}")
                            tdd.get_append_lastp_to_df(
                                top_now,
                                dl=ct.Resample_LABELS_Days[res_m],
                                resample=res_m)
                        else:
                            logger.info(f'resample:{res_m} now_time:{now_time} > 905 终止初始化 init_tdx 用时:{time.time()-time_init_m:.2f}')
                            break
                        logger.info(f'resample:{res_m} init_tdx 用时:{time.time()-time_init_m:.2f}')
                
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
                    # logger.info(f'not worktime and work_duration')
                    for _ in range(5):
                        if not flag.value: break
                        time.sleep(1)
                    continue
            else:
                logger.info(f'start work : {cct.get_now_time()} get_work_time: {cct.get_work_time()} , START_INIT :{START_INIT} ')

            resample = g_values.getkey("resample") or "d"
            market = g_values.getkey("market", marketInit)        # all / sh / cyb / kcb / bj
            blkname = g_values.getkey("blkname", marketblk)  # 对应的 blk 文件
            st_key_sort = g_values.getkey("st_key_sort", st_key_sort)  # 对应的 blk 文件
            logger.info(f"resample Main  market : {market} resample: {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")

            if market == 'indb':
                indf = get_indb_df()
                stock_code_list = indf.code.tolist()
                top_now = tdd.getSinaAlldf(market=stock_code_list,vol=ct.json_countVol, vtype=ct.json_countType)
            else:
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
                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days[resample], 
                                                                   resample=resample, detect_calc_support=detect_val)
                else:
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF, detect_calc_support=detect_val)
            else:
                top_all = cct.combine_dataFrame(top_all, top_now, col="couts", compare="dff")


            top_all = process_merged_sina_with_history(top_all)
            time_sum = time.time()
            result_opt = strong_momentum_today_plus_history_sum_opt(top_all,max_days=cct.compute_lastdays)
            clean_sum = merge_strong_momentum_results(result_opt,min_days=2)
            top_all = align_sum_percent(top_all,clean_sum)
            logger.info(f'clean_sum: {time.time() - time_sum:.2f}')

            top_all = calc_indicators(top_all, logger, resample)
            logger.info(f"resample Main  top_all:{len(top_all)} market : {market}  resample: {resample} flag.value : {flag.value} blkname :{blkname} st_key_sort:{st_key_sort}")
            # top_all = calc_indicators(top_all, resample)

            if top_all is not None and not top_all.empty:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort,top_all)
            else:
                sort_cols, sort_keys = ct.get_market_sort_value_key(st_key_sort)

            logger.info(f'sort_cols : {sort_cols[:3]} sort_keys : {sort_keys[:3]}  st_key_sort : {st_key_sort[:3]}')
            top_temp = top_all.copy()
            top_temp=stf.getBollFilter(df=top_temp, resample=resample, down=False)
            top_temp = top_temp.sort_values(by=sort_cols, ascending=sort_keys)
            logger.info(f'resample: {resample} top_temp :  {top_temp.loc[:,["name"] + sort_cols[:7]][:10]} shape : {top_temp.shape} detect_calc_support:{detect_val}')
            df_all = clean_bad_columns(top_temp)
            df_all = sanitize(df_all)
            # df_all = process_merged_sina_signal(df_all)  #single 
            queue.put(df_all)
            gc.collect()
            logger.info(f'process now: {cct.get_now_time_int()} resample Main:{len(df_all)} sleep_time:{duration_sleep_time}  用时: {round(time.time() - time_s,1)/(len(df_all)+1):.2f} elapsed time: {round(time.time() - time_s,1)}s  START_INIT : {cct.get_now_time()} {START_INIT} fetch_and_process sleep:{duration_sleep_time} resample:{resample}')
            if cct.get_now_time_int() < 945:
                sleep_step = 0.5
            else:
                sleep_step = 1
            # cout_time = 0
            for _ in range(duration_sleep_time):
                if not flag.value:
                    break
                elif g_values.getkey("resample") and  g_values.getkey("resample") !=  resample:
                    break
                elif g_values.getkey("market") and  g_values.getkey("market") !=  market:
                    # logger.info(f'market : new : {g_values.getkey("market")} last : {market} ')
                    break
                elif g_values.getkey("st_key_sort") and  g_values.getkey("st_key_sort") !=  st_key_sort:
                    break
                time.sleep(sleep_step)
                # cout_time +=sleep_step
                # logger.info(f'cout_time:{cout_time} duration_sleep_time:{duration_sleep_time} sleep_step:{sleep_step}')
            START_INIT = 1

        except Exception as e:
            logger.error(f"resample: {resample} Error in background process: {e}", exc_info=True)
            time.sleep(duration_sleep_time)