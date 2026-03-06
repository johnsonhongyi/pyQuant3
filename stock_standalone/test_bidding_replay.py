import os
import sys
import time
import pandas as pd
from datetime import datetime, time as datetime_time
import sqlite3
import numpy as np
from collections import deque

# 确保能找到 stock_standalone 模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from realtime_data_service import DataPublisher, IntradayEmotionTracker, DailyEmotionBaseline
from realtime_data_service import DataPublisher
from bidding_momentum_detector import BiddingMomentumDetector
from JohnsonUtil import commonTips as cct

# 设置日志
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

HDF5_FILE = r"g:\sina_MultiIndex_data.h5"
KEY = "all_30"

def get_mock_cat(code):
    """
    返回模拟的板块分类（分号分隔，与 df_all.category 格式一致）
    包含市场板块 + 概念板块，用于 sector_map 中概念级联动分析的 Mock 测试
    """
    c = str(code).zfill(6)
    # 市场板块
    if c.startswith('30'): market = '创业板'
    elif c.startswith('68'): market = '科创板'
    elif c.startswith('60'): market = '沪主板'
    elif c.startswith('00'): market = '深主板'
    elif c.startswith('92'): market = '其他'
    else: market = '其他'
    
    # 模拟概念板块（用于测试联动分析，每组股票共享相同概念）
    # 600108/600703/600875 → 电网工程
    if c in ('600108', '600703', '600875', '600468'):
        return f'{market};电网工程;特高压;电力设备'
    # 600545 → 光伏设备
    if c in ('600545', '603773'):
        return f'{market};光伏设备;新能源'
    # 002235/002429/002339/002355 → 消费电子
    if c in ('002235', '002429', '002339', '002355'):
        return f'{market};消费电子;半导体'
    # 300x 创业板概念
    if c.startswith('30'):
        return f'{market};医药生物;创新药'
    # 688x 科创板概念
    if c.startswith('68'):
        return f'{market};半导体;芯片'
    return market

def run_replay(start_time_str="09:15:00", end_time_str="15:00:00", playback_speed=0.0, stops=None):
    """
    基于 HDF5 本地 Tick 数据，按时间线回放并推入 DataPublisher/BiddingMomentumDetector。
    
    playback_speed:
      1.0 = 与真实时间流逝一致
      10.0 = 10倍速回放 (1分钟数据6秒跑完)
      0.0 或 None = 全速回放 (无须等待)，仅适用于测逻辑不测界面的情况
      
    stops: List[str]
      特定时间节点的切片停顿点 (例如 ["09:20:00", "09:30:00", "09:45:00"])，到达后会打印状态并要求按回车继续。
    """
    if stops is None:
        stops = []
        
    logger.info(f"Loading data from {HDF5_FILE} (key={KEY})...")
    
    if not os.path.exists(HDF5_FILE):
        logger.error(f"Cannot find HDF5 file: {HDF5_FILE}")
        return
        
    # 读取全天所有个股 tick 的快照 (仅作演示，实际可能非常耗内存，可用 chunk 或预选)
    # df 结构: MultiIndex(code, ticktime), columns=[price, volume, amount, type...]
    df = pd.read_hdf(HDF5_FILE, KEY)
    
    logger.info(f"Loaded {len(df)} ticks. Restructuring data for playback...")

    # 展开索引，使其可以被时间排序
    df = df.reset_index()
    
    # ticktime 可能只是 "09:25:03" 形式的文本
    if 'ticktime' not in df.columns:
        if 'time' in df.columns:
            df.rename(columns={'time': 'ticktime'}, inplace=True)
            
    # 按照实际 ticktime 进行排序
    df.sort_values(by='ticktime', inplace=True)
    
    # 分析 ticktime 的实际格式，统一提取 HH:MM:SS 用于时间过滤
    sample = df['ticktime'].iloc[0] if len(df) > 0 else None
    logger.info(f"Sample ticktime type={type(sample)} value={sample!r}")
    
    # 将 ticktime 统一转换为纯时间字符串 "HH:MM:SS" 用于过滤
    if sample is not None:
        if isinstance(sample, (pd.Timestamp, np.datetime64)) or hasattr(sample, 'hour'):
            # datetime64/Timestamp 类型：直接提取时间部分
            df['_hms'] = pd.to_datetime(df['ticktime']).dt.strftime('%H:%M:%S')
        elif isinstance(sample, str) and len(sample) > 8:
            # 完整 datetime 字符串如 "2024-03-01 09:25:00"
            df['_hms'] = df['ticktime'].str[-8:]  # 取最后8位
        else:
            # 已经是纯时间字符串
            df['_hms'] = df['ticktime'].astype(str).str[:8]
    else:
        df['_hms'] = df['ticktime'].astype(str).str[:8]
    
    # 用提取的时间列进行过滤
    df = df[(df['_hms'] >= start_time_str) & (df['_hms'] <= end_time_str)].copy()
    # 用提取的纯时间列替换 ticktime，确保后续 t_str 比较一致
    df['ticktime'] = df['_hms']
    df.drop(columns=['_hms'], inplace=True)
    
    logger.info(f"Filtered to time range {start_time_str} - {end_time_str}. Total ticks: {len(df)}")
    
    if len(df) == 0:
         logger.warning("No data found in the specified time range. Check time format.")
         return

    # 初始化测试环境核心模块
    pd.options.mode.chained_assignment = None # 避免测试时出现 SettingWithCopyWarning
    
    # 屏蔽不必要的外部数据抓取和干扰
    cct.get_work_time_duration = lambda: True # 强制算作开盘交易日
    cct.get_trade_date_status = lambda: True
    cct.get_ramdisk_path = lambda x: None # 屏蔽加载实盘缓存，确保测试环境隔离
    
    publisher = DataPublisher(high_performance=True, scraper_interval=99999, enable_backup=False)
    # 我们不需要真实时间自动备份和抓取外部
    publisher.set_paused(False) 
    
    detector = BiddingMomentumDetector(realtime_service=publisher)
    
    # --- [阈值放宽]: 测试环境下，我们希望看到即便只有 0.1% 的异动也会上榜 ---
    detector.strategies['pct_change']['min'] = -10.0
    detector.strategies['amplitude']['min'] = 0.0
    detector.strategies['surge_vol']['min_ratio'] = 0.1
    
    # 使用新增的类属性配置门槛
    detector.score_threshold = 0.1
    detector.sector_min_score = 0.1
    
    # --- [关键修复]: 首先全量注册所有股票，否则探测器不认数据 ---
    logger.info("Registering stocks to detector...")
    # 构造一个包含所有 code 的假全量表用于冷启，并尽量带上昨收价
    all_codes = df['code'].unique()
    
    # 尝试从大表中提取每个 code 的第一个 llastp 作为昨收
    if 'llastp' in df.columns:
        last_close_map = df.groupby('code')['llastp'].first().to_dict()
    else:
        last_close_map = {}

    init_df = pd.DataFrame({'code': all_codes})
    init_df['code'] = init_df['code'].astype(str).str.zfill(6)
    init_df['name'] = "T_" + init_df['code']
    init_df['category'] = init_df['code'].map(get_mock_cat)
    init_df['lastp1d'] = init_df['code'].map(lambda x: last_close_map.get(x, 0.0) or last_close_map.get(int(x) if x.isdigit() else x, 0.0))
    # 给一些默认的 ma 数据避免报错，或者模拟特定形态
    init_df['ma20'] = init_df['lastp1d'] * 0.98  # 默认在 ma20 上方一点
    init_df['ma60'] = init_df['lastp1d'] * 0.95  # 默认在 ma60 上方一点
    init_df['win'] = 1.0
    init_df['dist_h_l'] = 2.0
    
    # --- [Mocking Patterns for Verification] ---
    # 600108: 模拟 V反突破
    # 逻辑: dist_h_l > 4.0 且 price >= last_close
    init_df.loc[init_df['code'] == '600108', 'dist_h_l'] = 5.0
    init_df.loc[init_df['code'] == '600108', 'win'] = 3.0
    
    # 600545: 模拟 MA60反转
    # 逻辑: last_close < ma60 且 price > ma60
    init_df.loc[init_df['code'] == '600545', 'ma60'] = init_df['lastp1d'] * 1.01
    init_df.loc[init_df['code'] == '600545', 'trade'] = init_df['lastp1d'] * 1.02 # 让其此时就触发
    
    # 002235: 模拟 MA20反转
    # 逻辑: last_close < ma20 且 price > ma20
    init_df.loc[init_df['code'] == '002235', 'ma20'] = init_df['lastp1d'] * 1.005
    init_df.loc[init_df['code'] == '002235', 'trade'] = init_df['lastp1d'] * 1.01 # 让其此时就触发
    
    init_df['last_high'] = init_df['lastp1d']
    init_df['last_low'] = init_df['lastp1d'] * (1 - init_df['dist_h_l']/100)
    init_df['last_close'] = init_df['lastp1d']
    # 默认 trade 与 lastp1d 对齐，除非上面特殊设置
    init_df['trade'] = init_df.apply(lambda row: row['trade'] if 'trade' in row and row['trade'] > 0 else row['lastp1d'], axis=1)

    detector.register_codes(init_df)
    
    # --- [New] 初始化情绪基准 ---
    if hasattr(publisher, 'emotion_baseline'):
        logger.info("Initializing Daily Emotion Baseline with Mocked Patterns...")
        publisher.emotion_baseline.calculate_baseline(init_df)
    
    # 屏蔽 DataPublisher 自动保存以防报错
    publisher.cache_slot.save_df = lambda *args, **kwargs: True
    # 屏蔽分钟 K 线自动清理 (使用 _max_len)
    publisher.kline_cache._max_len = 999999
    
    # 准备测试数据 (我们需要将逐笔数据打包成 DataPublisher 需要的快照格式)
    # 因为 DataPublisher 的 update_batch 预期输入是带有当前 state 的 DataFrame
    # 为简单起见，按秒/或分钟将其切片，组合成全市场切片
    
    # 取所有的 tick 唯一时间
    unique_times = df['ticktime'].unique()
    
    logger.info(f"Starting playback at speed {playback_speed}x...")
    
    # 模拟最新行情的字典 (累加器)
    market_snapshot = pd.DataFrame()
    
    last_real_time = time.time()
    
    # 将 hh:mm:ss 转换为自今天 0点起多少秒方便计算间隔
    def time_str_to_seconds(t_str):
        parts = t_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
        return 0
        
    last_tick_seconds = -1
    start_time_real = time.time()
    next_stop_idx = 0
    stops.sort()

    for idx, t_str in enumerate(unique_times):
        # 取出这一时刻所有改动的 tick
        tick_slice = df[df['ticktime'] == t_str]
        
        # 处理 numpy.datetime64 类型
        if isinstance(t_str, np.datetime64):
            t_str = pd.to_datetime(t_str).strftime('%H:%M:%S')
        elif not isinstance(t_str, str):
            t_str = str(t_str)
            
        curr_seconds = time_str_to_seconds(t_str)
        
        # 处理播放速度 (延时控制)
        if playback_speed > 0 and last_tick_seconds != -1:
            diff_sec = curr_seconds - last_tick_seconds
            if diff_sec > 0:
                wait_time = diff_sec / playback_speed
                # 扣除脚本运行耗时 
                elapsed = time.time() - last_real_time
                actual_wait = max(0, wait_time - elapsed)
                if actual_wait > 0:
                    time.sleep(actual_wait)
                    
        last_real_time = time.time()
        last_tick_seconds = curr_seconds
        
        # 把该时间点发生过交易的 tick 数据合并进当前最新行情快照里
        # DataPublisher 需要的是含有 trade, code, volume 的 DataFrame
        # 注意：这里需要模拟构建市场最新状况
        
        # 简单处理：我们只推送发生改变的票给 update_batch，
        # 为了配合 BiddingMomentumDetector，需要尽量模拟标准格式
        # e.g.: code, trade, percent, highest, lowest, open, volume
        # (真实中，DataPublisher 接收的是最新行情)
        
        batch_df = tick_slice.copy()
        
        # 改名映射（适应我们的系统需求）
        rename_map = {}
        if 'close' in batch_df.columns: rename_map['close'] = 'trade'
        elif 'price' in batch_df.columns: rename_map['price'] = 'trade'
        if 'llastp' in batch_df.columns: rename_map['llastp'] = 'settlement'
        
        batch_df.rename(columns=rename_map, inplace=True)
        
        # 补充确实依赖的基础字段
        if 'percent' not in batch_df.columns and 'trade' in batch_df.columns and 'settlement' in batch_df.columns:
            # 简化：因为历史 tick 没有 percent，我们假装 percent = (trade - pre_close)/pre_close
            batch_df['percent'] = (batch_df['trade'] - batch_df['settlement']) / batch_df['settlement'] * 100
            batch_df.loc[batch_df['settlement'] == 0, 'percent'] = 0.0 # 避免除0
            
        if 'ratio' not in batch_df.columns:
             batch_df['ratio'] = 1.0 # 占位量比
             
        # 结合内置的规则模拟 metadata (保证能被 BiddingMomentumDetector 按概念切分)
        if 'code' in batch_df.columns:
            # batch_df['code'] 可能为文本类型，确保是 6 位
            batch_df['code'] = batch_df['code'].astype(str).str.zfill(6)
            batch_df['name'] = "T_" + batch_df['code'].astype(str)
            batch_df['category'] = batch_df['code'].map(get_mock_cat)
             
        # [核心]: 送入数据泵
        # 为了模拟 DataPublisher 中的逻辑，必须添加 time 或 timestamp 字段
        batch_df['timestamp'] = f"2026-03-05 {t_str}" 
        
        # 向核心系统泵入 (这里它会自动处理分钟K线切割、情绪计算)
        publisher.update_batch(batch_df)
        
        # 实时让探测器跑分
        detector.update_scores()
        
        if idx % 50 == 0:
            sys.stdout.write(f"\r[Playback] Progress: {t_str} | Market Ticks: {len(tick_slice)} | Total Cached Stocks: {len(publisher.kline_cache.cache)}      ")
            sys.stdout.flush()

        # 检查是否到达切片观察点
        if next_stop_idx < len(stops) and t_str >= stops[next_stop_idx]:
            stop_time = stops[next_stop_idx]
            sys.stdout.write("\n\n")
            logger.info(f"=== ⏰ 触发时间切片停顿观测点: {stop_time} ===")
            
            # --- 测试/观察打印：我们在终端中打印最强的 3 个概念板块 ---
            all_sectors = detector.get_active_sectors()
            top_sectors = all_sectors[:5] # 多看几个
            print("-" * 60)
            print(f"[{stop_time}] 当下全市场最强板块 (Top {len(top_sectors)}):")
            if not top_sectors:
                 print("  <暂无达到评分门槛的活跃板块>")
            for i, sec_info in enumerate(top_sectors):
                tags_str = f" [{sec_info['tags']}]" if sec_info.get('tags') else ""
                print(f"  {i+1}. {sec_info['sector']} - 强度得分: {sec_info['score']:.1f}{tags_str}")
                leader_info = f"{sec_info['leader_name']} ({sec_info['leader']})"
                if sec_info.get('is_untradable'):
                    leader_info += " [🚫一字]"
                # 简化输出便于联动，形态信息作为可选后缀
                pattern = sec_info.get('pattern_hint', '')
                time_str = pd.Timestamp.fromtimestamp(sec_info['leader_first_ts']).strftime('%H:%M:%S') if sec_info['leader_first_ts']>0 else 'N/A'
                print(f"     -> 领涨龙头: {leader_info} [首异时间: {time_str}]")
                if pattern:
                    print(f"        [形态: {pattern}]")
                
                # 跟风小弟带首异时间
                if sec_info['followers']:
                    f_parts = []
                    for f in sec_info["followers"][:5]:
                        f_ts = f.get('first_breakout_ts', 0)
                        f_time = pd.Timestamp.fromtimestamp(f_ts).strftime('%H:%M:%S') if f_ts > 0 else '?'
                        f_parts.append(f"{f['name']} ({f['code']}) [{f_time}]")
                    print(f"     -> 跟风小弟: {', '.join(f_parts)},")
                
                # 关联板块联动分析（类 get_following_concepts_by_correlation）
                linked = sec_info.get('linked_concepts', [])
                if linked:
                    concept_strs = [f"{c['concept']}(跟{c['follow_ratio']:.0%}/均{c['avg_pct']:+.1f}%)" for c in linked[:3]]
                    print(f"        [联动板块]: {' | '.join(concept_strs)}")
            print("-" * 60)
            
            # --- 当日重点表（涨停/溢出观察列）---
            watchlist = detector.get_daily_watchlist()
            if watchlist:
                print(f"📋 当日重点表 ({len(watchlist)} 只):")
                for w in watchlist:
                    # 获取第一个非市场标签的概念板块
                    market_tags = ['科创板', '创业板', '主板', '中小板', '北证']
                    all_cats = w['sector'].split(';')
                    cats = [c for c in all_cats if c not in market_tags]
                    sector_short = cats[0] if cats else all_cats[0]
                    
                    reason_tag = f"[{w['reason']}]" if w.get('reason') else ''
                    print(f"   {w['name']} ({w['code']}) {reason_tag} {w['pct']:+.1f}% 首涨停: {w['time_str']} 板块: {sector_short}")
                print("-" * 60)
            
            print() # 不阻塞，直接继续
            next_stop_idx += 1
            last_real_time = time.time() # 防止计算出巨大的暂停补偿

    sys.stdout.write("\n")
    end_time_real = time.time()
    logger.info(f"\n✅ Playback complete! Total real time elapsed: {end_time_real - start_time_real:.2f}s")

if __name__ == "__main__":
    logger.info("Initializing Sector Bidding Slice Backtest Tool...")
    # 全天关键时间切片，覆盖竞价、早盘、午盘和尾盘
    slice_stops = [
        "09:20:00",  # 竞价形成
        "09:25:00",  # 竞价结束
        "09:45:00",  # 开盘强化期
        "10:00:00",  # 板块联动稳定
        "10:30:00",  # 早盘持续
        "11:00:00",  # 午盘前
        "11:30:00",  # 收盘午前
        "13:30:00",  # 下午开盘
        "14:00:00",  # 下午持续
        "14:30:00",  # 尾盘
        "15:00:00",  # 收盘
    ]
    run_replay(start_time_str="09:15:00", end_time_str="15:00:00", playback_speed=0.0, stops=slice_stops)
