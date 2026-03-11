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
from bidding_momentum_detector import BiddingMomentumDetector
from JohnsonUtil import commonTips as cct

# [NEW] Import real data fetching logic
from instock_MonitorTK import test_single_thread

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

def run_replay(start_time_str="13:11:00", end_time_str="15:00:00", playback_speed=0.0, stops=None, concise=True, resample=None, codes=None):
    """
    基于 HDF5 本地 Tick 数据，按时间线回回放并推入 DataPublisher/BiddingMomentumDetector。
    
    playback_speed:
      1.0 = 与真实时间流逝一致
      10.0 = 10倍速回放 (1分钟数据6秒跑完)
      0.0 或 None = 全速回放 (无须等待)，仅适用于测逻辑不测界面的情况
      
    stops: List[str]
      特定时间节点的切片停顿点 (例如 ["09:20:00", "09:30:00", "09:45:00"])，到达后会打印状态并要求按回车继续。

    resample: str
      指定回测 baseline 的周期 (e.g., 'd', '2d', '3d', 'w', 'm')
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
            
    # [NEW] Filter by stock codes if specified
    if codes:
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(',')]
        
        # Robust check for 'code' in column or index
        if 'code' in df.columns:
            df = df[df['code'].astype(str).str.zfill(6).isin(codes)]
        else:
            df = df[df.index.get_level_values('code').astype(str).str.zfill(6).isin(codes)] if isinstance(df.index, pd.MultiIndex) else df[df.index.astype(str).str.zfill(6).isin(codes)]
        logger.info(f"Filtered playback data for {len(codes)} stocks: {codes}")

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
    
    # --- [REAL DATA MODE] ---
    logger.info(f"Fetching REAL production data (resample={resample}) for baseline registry...")
    real_df_all = test_single_thread(single=True, resample=resample)
    if real_df_all is None or real_df_all.empty:
        logger.error("Failed to fetch real data from production environment.")
        return

    # [NEW] Verify Metadata Columns
    required_cols = ['category', 'lastp1d', 'ma20', 'lastdu4', 'ral', 'top0', 'top15']
    missing = [c for c in required_cols if c not in real_df_all.columns]
    if missing:
        logger.warning(f"⚠️ Real data missing critical metadata columns: {missing}")
    else:
        logger.info("✅ Real data contains all required metadata columns.")
    
    # [DATA INTEGRITY] Reset real-time columns to ensure we don't leak "future" 
    # final percentages into early simulation stages.
    leakage_cols = ['percent', 'ratio', 'now', 'price', 'trade', 'high', 'low', 'volume', 'amount', 'per1d']
    for col in leakage_cols:
        if col in real_df_all.columns:
            real_df_all[col] = 0.0
            
    # [NEW] Filter the registry/baseline data if specific codes are targeted
    if codes:
        if 'code' in real_df_all.columns:
            real_df_all = real_df_all[real_df_all['code'].astype(str).str.zfill(6).isin(codes)]
        else:
            real_df_all = real_df_all[real_df_all.index.astype(str).str.zfill(6).isin(codes)]
        
    logger.info(f"Successfully fetched {len(real_df_all)} real stock records (Data Leakage Protection Active).")

    # [Phase 4] 注册代码名称对应关系
    publisher = DataPublisher(high_performance=True, scraper_interval=99999, enable_backup=False, 
                               simulation_mode=True, verbose=not concise)
    publisher.register_names(real_df_all)
    pd.options.mode.chained_assignment = None # 避免测试时出现 SettingWithCopyWarning
    
    # 屏蔽不必要的外部数据抓取和干扰
    cct.get_work_time_duration = lambda: True # 强制算作开盘交易日
    cct.get_trade_date_status = lambda: True
    # 我们不需要真实时间自动备份和抓取外部
    publisher.set_paused(True) 
    
    detector = BiddingMomentumDetector(realtime_service=publisher, simulation_mode=True)
    
    # --- [阈值放宽]: 测试环境下，我们希望看到即便只有 0.1% 的异动也会上榜 ---
    detector.strategies['pct_change']['min'] = -10.0
    detector.strategies['amplitude']['min'] = 0.0
    detector.strategies['surge_vol']['min_ratio'] = 0.1
    
    # 使用新增的类属性配置门槛
    detector.score_threshold = 0.1
    detector.sector_min_score = 0.1
    
    # --- [REAL DATA REGISTRY REUSE] ---
    global _cached_detector_state
    if '_cached_detector_state' not in globals():
        _cached_detector_state = None

    if _cached_detector_state and len(_cached_detector_state['_tick_series']) == len(real_df_all):
        logger.info("♻️ Reusing cached detector metadata/registry...")
        with detector._lock:
            detector._tick_series = _cached_detector_state['_tick_series']
            detector.sector_map = _cached_detector_state['sector_map']
            # 注意：不能直接复用 _subscribed，因为 publisher 是新的，必须重新订阅
            detector._subscribed = set() 
            
    logger.info("Syncing stock registry and subscriptions...")
    detector.register_codes(real_df_all)
    
    # 存入/更新缓存
    _cached_detector_state = {
        '_tick_series': detector._tick_series,
        'sector_map': detector.sector_map
    }
    
    # --- [阈值调整 - 基于真实数据] ---
    detector.score_threshold = 1.0        # 调低以便看到更多个股异动
    detector.sector_min_score = 1.0       # 对应 _aggregate_sectors 中的 high_score_stocks 门槛
    detector.sector_score_threshold = 1.0 # 全局板块显示门槛 (注意：之前误写为 board_score_threshold)
    
    # --- [New] 初始化情绪基准 ---
    if hasattr(publisher, 'emotion_baseline'):
        logger.info("Initializing Daily Emotion Baseline with Real Production Data...")
        publisher.emotion_baseline.calculate_baseline(real_df_all)
    
    # 屏蔽 DataPublisher 自动保存以防报错
    publisher.cache_slot.save_df = lambda *args, **kwargs: True
    # 屏蔽分钟 K 线自动清理 (使用 _max_len)
    publisher.kline_cache._max_len = 999999
    
    # 准备测试数据 (我们需要将逐笔数据打包成 DataPublisher 需要的快照格式)
    # 因为 DataPublisher 的 update_batch 预期输入是带有当前 state 的 DataFrame
    # 为简单起见，按秒/或分钟将其切片，组合成全市场切片
    
    # 取所有的 tick 唯一时间
    all_unique_times = sorted(df['ticktime'].unique())
    # 转换为字符串列表以便过滤 (支持 numpy.datetime64 或 str)
    def to_time_str(t):
        if isinstance(t, np.datetime64):
            return pd.to_datetime(t).strftime('%H:%M:%S')
        return str(t)

    unique_times = [t for t in all_unique_times if start_time_str <= to_time_str(t) <= end_time_str]
    
    # Reset breakout timestamps for a fresh simulation run
    for ts in detector._tick_series.values():
        ts.first_breakout_ts = 0

    if not unique_times:
        logger.error(f"No data found between {start_time_str} and {end_time_str}")
        return

    logger.info(f"Starting playback: {to_time_str(unique_times[0])} -> {to_time_str(unique_times[-1])} at speed {playback_speed}x...")
    
    # 模拟最新行情的字典 (累加器)
    market_snapshot = pd.DataFrame()
    
    last_real_time = time.time()
    
    # 将 hh:mm:ss 转换为自今天 0点起多少秒方便计算间隔
    def time_str_to_seconds(t_str):
        parts = str(t_str).split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
        return 0
        
    last_tick_seconds = -1
    start_time_real = time.time()
    
    # [OPTIMIZED] 预处理 stops, 过滤掉早于回放开始时间点的数据
    first_tick_str = to_time_str(unique_times[0])
    stops = [s for s in stops if s >= first_tick_str]
    next_stop_idx = 0
    stops.sort()

    initial_sim_seconds = time_str_to_seconds(first_tick_str)
    total_ticks_processed = 0

    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # [OPTIMIZED] 预分组数据，极大提升回放时的切片速度
    logger.info("Pre-grouping tick data by time (this takes a few seconds)...")
    df_grouped = {t: group for t, group in df.groupby('ticktime')}

    try:
        for idx, t_str in enumerate(unique_times):
            # 取出这一时刻所有改动的 tick
            tick_slice = df_grouped.get(t_str)
            if tick_slice is None: continue 
                
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
            
            # [FIX] 显式清理缓存，防止由于 RegisterRegistry 缓存导致的实盘数据干扰
            if idx == 0:
                detector.active_sectors.clear()
                detector.daily_watchlist.clear()
                if hasattr(detector, '_sector_active_stocks_persistent'):
                    detector._sector_active_stocks_persistent.clear()

            batch_df = tick_slice.copy()
            
            # 改名映射（适应我们的系统需求）
            rename_map = {}
            if 'close' in batch_df.columns: rename_map['close'] = 'trade'
            elif 'price' in batch_df.columns: rename_map['price'] = 'trade'
            if 'llastp' in batch_df.columns: rename_map['llastp'] = 'settlement'
            
            batch_df.rename(columns=rename_map, inplace=True)
            
            # [FIX] 同步 Tick 级别价格数据到 Detector 的 TickSeries 中
            # 这样 detector.update_scores 才能基于最新 Tick 价格计算现价涨幅和异动
            with detector._lock:
                for row_t in batch_df.itertuples():
                    c = str(row_t.code).zfill(6)
                    if c in detector._tick_series:
                        ts = detector._tick_series[c]
                        price = float(getattr(row_t, 'trade', 0))
                        if price > 0:
                            ts.now_price = price
                            if price > ts.high_day: ts.high_day = price
                            if price < ts.low_day or ts.low_day == 0: ts.low_day = price
            
            # [DATA LEAKAGE PROTECTION] 强制重新计算涨幅，防止 HDF5 中自带的 EOD 涨幅干扰回测
            if 'trade' in batch_df.columns:
                # 寻找昨收：优先用 settlement (llastp), 否则用 real_df_all 中的 lastp1d
                if 'settlement' not in batch_df.columns or (batch_df['settlement'] == 0).all():
                    # 尝试从 registry 补全昨收
                    batch_df['settlement'] = batch_df['code'].map(lambda x: getattr(detector._tick_series.get(x), 'last_close', 0))
                
                # 强制覆盖 percent
                batch_df['percent'] = (batch_df['trade'] - batch_df['settlement']) / batch_df['settlement'] * 100
                batch_df.loc[batch_df['settlement'] <= 0, 'percent'] = 0.0
                
                # [FIX] 强制覆盖 high/low 为当前价，防止 Detector 从 row 获取到 EOD 高低点
                batch_df['high'] = batch_df['trade']
                batch_df['low'] = batch_df['trade']
                
            if 'ratio' not in batch_df.columns:
                 batch_df['ratio'] = 1.0 # 占位量比
                 
            # 结合内置的规则模拟 metadata (保证能被 BiddingMomentumDetector 按概念切分)
            if 'code' in batch_df.columns:
                # batch_df['code'] 可能为文本类型，确保是 6 位
                batch_df['code'] = batch_df['code'].astype(str).str.zfill(6)
                # Metadata is now handled by the publisher's df_all seeded with real_df_all
                 
            # [核心]: 送入数据泵
            # 为了模拟 DataPublisher 中的逻辑，必须添加 time 或 timestamp 字段
            today_str = datetime.now().strftime('%Y-%m-%d')
            batch_df['timestamp'] = f"{today_str} {t_str}" 
            
            # 向核心系统泵入 (这里它会自动处理分钟K线切割、情绪计算)
            t0 = time.time()
            publisher.update_batch(batch_df)
            t1 = time.time()
            
            # 实时让探测器跑分 (使用优化后的 active_codes)
            detector.update_scores(active_codes=batch_df['code'].tolist())
            t2 = time.time()
            
            total_ticks_processed += len(tick_slice)
            
            if idx % 1 == 0:
                cost_pub = (t1 - t0) * 1000
                cost_det = (t2 - t1) * 1000
                
                # 计算速度指标
                real_elapsed = time.time() - start_time_real
                sim_elapsed = curr_seconds - initial_sim_seconds
                
                tps = total_ticks_processed / max(0.001, real_elapsed)
                speed_x = sim_elapsed / max(0.001, real_elapsed)
                
                # 速度评价
                if speed_x > 50: speed_label = "🚀"
                elif speed_x > 20: speed_label = "⚡"
                elif speed_x > 5: speed_label = "🚅"
                elif speed_x > 1: speed_label = "🚗"
                else: speed_label = "🚶"
                
                if concise:
                    sys.stdout.write(f"\r[Playback] {speed_label} {t_str} | {speed_x:.1f}x ({tps:.0f} tps) | Total: {len(publisher.kline_cache.cache)}      ")
                else:
                    sys.stdout.write(f"\r[Playback] {speed_label} Progress: {t_str} | Speed: {speed_x:.1f}x ({tps:.0f} tps) | Pub: {cost_pub:.1f}ms | Det: {cost_det:.1f}ms | Total: {len(publisher.kline_cache.cache)}      ")
                sys.stdout.flush()
    
            # 检查是否到达切片观察点
            if next_stop_idx < len(stops) and str(t_str) >= str(stops[next_stop_idx]):
                stop_time = stops[next_stop_idx]
                sys.stdout.write("\n\n")
                logger.info(f"=== ⏰ 触发时间切片停顿观测点: {stop_time} ===")
                
                # [NEW] 打印当前个股前 10 评分，排查为何板块为空
                all_ts = sorted(detector._tick_series.values(), key=lambda x: x.score, reverse=True)
                print("-" * 60)
                print(f"[{stop_time}] 当下个股评分排行 (Top 5):")
                # 获取 EmotionTracker 的当前分数
                emotion_scores = publisher.emotion_tracker.scores
                for ts in all_ts[:5]:
                    e_score = emotion_scores.get(ts.code, 0.0)
                    print(f"  {ts.code} ({getattr(ts, 'name', 'N/A')}) - 热度: {e_score:.1f}, 结构: {ts.score:.1f}, 涨幅: {ts.current_pct:+.1f}%")
                print("-" * 60)
    
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
                    
                    # 获取龙头的 Emotion 评分 (如果是 DataPublisher 模式)
                    leader_emotion = 0.0
                    if hasattr(publisher, 'emotion_tracker'):
                        leader_emotion = publisher.emotion_tracker.scores.get(sec_info['leader'], 0.0)
                    
                    pattern = sec_info.get('pattern_hint', '')
                    time_str = pd.Timestamp.fromtimestamp(sec_info['leader_first_ts']).strftime('%H:%M:%S') if sec_info['leader_first_ts']>0 else 'N/A'
                    print(f"     -> 领涨龙头: {leader_info} [强度: {sec_info['score']:.1f} | 热度: {leader_emotion:.1f}] [首异: {time_str}]")
                    if pattern:
                        print(f"        [形态: {pattern}]")
                    
                    # 跟风小弟: 显示分数和涨幅
                    f_parts = []
                    for f in sec_info.get("followers", [])[:5]:
                        f_code = f['code']
                        f_em = 0.0
                        if hasattr(publisher, 'emotion_tracker'):
                            f_em = publisher.emotion_tracker.scores.get(f_code, 0.0)
                        
                        f_ts = f.get('first_ts', 0)
                        f_time = pd.Timestamp.fromtimestamp(f_ts).strftime('%H:%M:%S') if f_ts > 0 else '?'
                        f_parts.append(f"{f.get('name', 'N/A')} ({f_code}) [\033[92m{f.get('pct', 0.0):+.1f}%\033[0m 强:{f.get('score', 0.0):.1f}/热:{f_em:.1f}]")
                    if f_parts:
                        print(f"     -> 跟风小弟: {', '.join(f_parts)}")
                    
                    # [FULL-CHAIN] 跟单与操作建议 (跟单建议)
                    print(f"     ✅ 【跟单建议】: ", end="")
                    score = sec_info['score']
                    ratio = sec_info.get('follow_ratio', 0)
                    if score > 60 and ratio > 0.4:
                        print("💎 核心强势板块，龙头稳健，建议积极关注跟单机会。")
                    elif score > 40 and ratio > 0.3:
                        print("📈 板块能量聚拢中，建议轻仓博弈跟随品种。")
                    elif score > 40:
                        print("⚠️ 龙头单兵作战，板块协同性尚可，注意回调风险。")
                    elif any(tag in sec_info.get('tags', '') for tag in ['蓄势', '低开高走']):
                        print("♨️ 形态优美，属于低位启动/蓄势，适合潜伏。")
                    else:
                        print("👀 观望，强度不足以支撑日内确定性。")

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
    except Exception as e:
        import traceback
        logger.error(f"Simulation crashed with error: {e}")
        traceback.print_exc()

    sys.stdout.write("\n")
    end_time_real = time.time()
    logger.info(f"\n✅ Playback complete! Total real time elapsed: {end_time_real - start_time_real:.2f}s")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sector Bidding Slice Backtest/Replay Tool")
    parser.add_argument("--speed", type=float, default=0.0, help="Playback speed multiplier (e.g. 1.0, 10.0). 0.0 means full speed.")
    parser.add_argument("--observation", type=str, action="append", help="Observation timestamps (HH:MM:SS) to pause and inspect. Can be specified multiple times.")
    parser.add_argument("--start", type=str, default="09:30:00", help="Simulation start time (HH:MM:SS)")
    parser.add_argument("--end", type=str, default="15:00:00", help="Simulation end time (HH:MM:SS)")
    parser.add_argument("--verbose", action="store_true", help="Show detailed price/performance logs (not concise).")
    parser.add_argument("--resample", type=str, default=None, choices=['d', '2d', '3d', 'w', 'm'], help="Data resample period for baseline registry (d: daily, w: weekly, m: monthly, etc.)")
    parser.add_argument("--codes", type=str, default=None, help="Stock codes for targeted testing (comma-separated, e.g., 688787,002536)")
    
    args = parser.parse_args()
    
    logger.info("Initializing Sector Bidding Slice Backtest Tool...")
    # 默认观测点
    slice_stops = []
    if args.observation:
        for s in args.observation:
            slice_stops.extend([x.strip() for x in s.split(',')])
    else:
        slice_stops = ["09:45:00", "10:00:00", "10:30:00", "11:00:00", "13:30:00", "14:00:00", "14:30:00", "14:45:00"]
    
    run_replay(
        start_time_str=args.start, 
        end_time_str=args.end, 
        playback_speed=args.speed, 
        stops=slice_stops,
        concise=not args.verbose,
        resample=args.resample,
        codes=args.codes
    )
