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

# --- [UI IMPORTS] ---
try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QThread, pyqtSignal
    from bidding_racing_panel import BiddingRacingRhythmPanel
    UI_AVAILABLE = True
except ImportError:
    UI_AVAILABLE = False

# [NEW] Import real data fetching logic moved to local scopes to avoid circular import with MonitorTK

from JohnsonUtil import LoggerFactory
# [SILENT-MODE] 使用统一日志工厂，UI模式下默认级别仅 WARNING
logger = LoggerFactory.getLogger()
HDF5_FILE = r"g:\sina_MultiIndex_data.h5"
KEY = "all_30"

def analyze_data_integrity(detector, stop_time):
    """
    [NEW] 深度分析当前探测器内部状态的连贯性
    """
    print(f"\n🔍 [Data Integrity Report @ {stop_time}]")
    print("-" * 50)
    
    # 1. 检查基准时间
    elapsed_min = (time.time() - detector.baseline_time) / 60
    print(f"? 观测窗口已持续: {elapsed_min:.1f} min (预设间隔: {detector.comparison_interval/60:.1f} min)")
    
    # 2. 采样个股锚点状态
    all_ts = list(detector._tick_series.values())
    if all_ts:
        active_ts = [ts for ts in all_ts if ts.now_price > 0]
        reset_ts = [ts for ts in active_ts if ts.price_anchor == ts.now_price]
        valid_diff = [ts for ts in active_ts if ts.pct_diff != 0]
        
        print(f"📈 个股统计: 总计={len(all_ts)}, 活跃={len(active_ts)}, 锚点重置={len(reset_ts)}, 有效涨跌={len(valid_diff)}")
        
        # 采样前 3 名有变动的票
        valid_ts = sorted(valid_diff, key=lambda x: abs(x.pct_diff), reverse=True)
        for ts in valid_ts[:3]:
            print(f"   [Sample] {ts.code}: 现价={ts.now_price:.2f}, 锚点={ts.price_anchor:.2f}, 涨跌={ts.pct_diff:+.2f}%")
    
    # 3. 采样板块锚点状态
    if detector.sector_anchors:
        sec_samples = sorted(detector.sector_anchors.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"🗂? 板块锚点: 已记录={len(detector.sector_anchors)} 个")
        for name, anchor in sec_samples:
            print(f"   [Sample] {name}: 基准分={anchor:.1f}")
    
    print("-" * 50)


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
    # 600108/600703/600875 ? 电网工程
    if c in ('600108', '600703', '600875', '600468'):
        return f'{market};电网工程;特高压;电力设备'
    # 600545 ? 光伏设备
    if c in ('600545', '603773'):
        return f'{market};光伏设备;新能源'
    # 002235/002429/002339/002355 ? 消费电子
    if c in ('002235', '002429', '002339', '002355'):
        return f'{market};消费电子;半导体'
    # 300x 创业板概念
    if c.startswith('30'):
        return f'{market};医药生物;创新药'
    # 688x 科创板概念
    if c.startswith('68'):
        return f'{market};半导体;芯片'
    return market

    print("-" * 50)


class ReplayWorker(QThread):
    """
    异步回放执行器，用于在不阻塞主 UI 线程的情况下运行回放逻辑。
    """
    progress_update = pyqtSignal(str, name='progress_update') 
    finished = pyqtSignal()

    def __init__(self, kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.is_running = True

    def run(self):
        def ui_callback(t_str):
            if t_str is not None:
                try:
                    self.progress_update.emit(str(t_str))
                except Exception as e:
                    logger.debug(f"Signal emit failed: {e}")
            return self.is_running

        self.kwargs['ui_callback'] = ui_callback
        run_replay(**self.kwargs)
        self.finished.emit()

    def stop(self):
        self.is_running = False


class LiveWorker(QThread):
    """
    实盘数据拉取工作线程。
    周期性调用 tdd.getSinaAlldf 获取全量 OHLC 切片行情，
    推送至 DataPublisher ? BiddingMomentumDetector 驱动 UI 更新。
    
    数据流:
        tdd.getSinaAlldf(market='all') ? publisher.update_batch(df)
        ? detector.update_scores(active_codes) ? Panel.update_visuals() (via QTimer)
    """
    progress_update = pyqtSignal(str, name='progress_update')   # 当前时间 HH:MM:SS
    status_update = pyqtSignal(str)     # 状态文本 (等待中/拉取中/错误)
    finished = pyqtSignal()

    def __init__(self, detector, publisher, real_df_all, 
                 resample=None, fetch_interval=5, log_level=None):
        super().__init__()
        self.detector = detector
        self.publisher = publisher
        self.real_df_all = real_df_all
        self.resample = resample
        self.fetch_interval = max(3, fetch_interval)  # 最小 3 秒
        self.log_level = log_level
        self.is_running = True
        self._fetch_count = 0
        self._last_fetch_ts = 0

    def _recover_intraday_history(self):
        """
        [BRIDGE] ⚡ 实盘恢复桥接：
        如果系统是在盘中启动（如 09:30 以后），尝试从 g:\sina_MultiIndex_data.h5 
        获取今日已发生的历史切片并补齐到 detector 和 publisher。
        """
        from JSONData import tdx_data_Day as tdd
        now_dt = datetime.now()
        # 如果是 9:15 以前，没必要恢复，直接从零开始
        if now_dt.hour < 9 or (now_dt.hour == 9 and now_dt.minute < 15):
            return

        h5_path = r"g:\sina_MultiIndex_data.h5"
        if not os.path.exists(h5_path):
            logger.warning(f"⚠️ [Recovery] HDF5 recovery file not found: {h5_path}")
            return

        try:
            logger.info(f"🔄 [Recovery] Attempting to recover intraday history from {h5_path}...")
            # 1. 加载今日数据
            # [FIX] sina_MultiIndex_data.h5 使用 'll_YYYYMMDD' 格式存储，而非 'all'
            today_key = f"ll_{now_dt.strftime('%Y%m%d')}"
            try:
                # 使用读取模式，避免锁竞争
                df_hist = pd.read_hdf(h5_path, key=today_key)
            except KeyError:
                # 兼容旧格式或特殊情况
                try:
                    df_hist = pd.read_hdf(h5_path, key='all')
                except Exception as e2:
                    # [🚀 鲁棒提示] 如果数据确实不存在，给出清晰的业务提示
                    logger.warning(f"ℹ️ [Recovery] 数据源未就绪: HDF5 文件中尚未包含 '{today_key}' 或 'all' 详情表。")
                    return
            except Exception as e:
                logger.error(f"❌ [Recovery] Failed to read HDF5: {e}")
                return

            if df_hist is None or df_hist.empty:
                logger.info("ℹ️ [Recovery] No historical data found in HDF5 for today.")
                return

            # 2. 时间过滤：仅保留今日数据
            today_prefix = now_dt.strftime('%Y-%m-%d')
            if isinstance(df_hist.index, pd.MultiIndex):
                times = df_hist.index.get_level_values('ticktime')
                if pd.api.types.is_datetime64_any_dtype(times):
                    mask = (times.date == now_dt.date())
                else:
                    mask = times.astype(str).str.contains(today_prefix)
                df_today = df_hist[mask].copy()
            else:
                if 'ticktime' in df_hist.columns:
                    mask = df_hist['ticktime'].astype(str).str.contains(today_prefix)
                    df_today = df_hist[mask].copy()
                else:
                    df_today = pd.DataFrame()

            if df_today.empty:
                logger.info(f"ℹ️ [Recovery] No historical snapshots found for date {today_prefix}")
                return

            # 3. 按时间顺序重放注入
            logger.info(f"🚀 [Recovery] Replaying {len(df_today)} historical rows for {len(df_today.index.get_level_values('code').unique()) if isinstance(df_today.index, pd.MultiIndex) else 'N/A'} codes...")
            
            if 'ticktime' not in df_today.columns:
                df_today = df_today.reset_index()
            
            time_groups = df_today.groupby('ticktime')
            sorted_times = sorted(time_groups.groups.keys())
            
            for t in sorted_times:
                snap = time_groups.get_group(t).copy()
                # 统一映射
                if 'trade' not in snap.columns and 'close' in snap.columns:
                    snap.rename(columns={'close': 'trade'}, inplace=True)
                
                # 基础注入
                self.publisher.update_batch(snap)
                self.detector.register_codes(snap)
            
            logger.info(f"✅ [Recovery] Successfully replayed {len(sorted_times)} time snapshots.")

        except Exception as e:
            logger.exception(f"❌ [Recovery] Critical error during history recovery: {e}")

    def run(self):
        """实盘主循环：等待开盘 ? 周期拉取 ? 收盘停止"""
        from JSONData import tdx_data_Day as tdd
        from JohnsonUtil import johnson_cons as ct

        logger.info("🔴 [LiveWorker] 实盘模式正在热启动...")

        # Step 0: [ALIGNED] 执行每日状态重置 (对齐回放初始化)
        self.detector._reset_daily_state(datetime.now())
        
        # Step 1: 注册基线
        self.publisher.register_names(self.real_df_all)
        self.detector.register_codes(self.real_df_all)
        
        if hasattr(self.publisher, 'emotion_baseline'):
            self.publisher.emotion_baseline.calculate_baseline(self.real_df_all)

        # Step 2: [NEW] 尝试从 HDF5 恢复今日历史
        self._recover_intraday_history()
        
        logger.info(f"✅ [LiveWorker] 初始化与恢复完成: {len(self.detector._tick_series)} 只个股")

        # ========================================
        # 实盘循环拉取
        # ========================================
        logger.info("🚀 [LiveWorker] 进入实盘循环监测...")
        consecutive_errors = 0

        while self.is_running:
            now_dt = datetime.now()
            
            # 1. 盘外休息时段
            if not cct.get_work_time_duration():
                self.status_update.emit(f"⏳ 非交易时间等待... 当前 {now_dt.strftime('%H:%M:%S')}")
                self.progress_update.emit(now_dt.strftime('%m-%d %H:%M:%S'))
                time.sleep(30)
                continue
            
            # 2. 午休时段
            if not cct.get_work_time():
                self.status_update.emit("💤 午休中...")
                self.progress_update.emit(now_dt.strftime('%H:%M:%S'))
                time.sleep(30)
                continue

            try:
                t0 = time.time()

                # ── 1. Fetch ────────────────────────────────────────────────
                top_now = tdd.getSinaAlldf(
                    market='all',
                    vol=ct.json_countVol,
                    vtype=ct.json_countType
                )

                if top_now is None or top_now.empty:
                    consecutive_errors += 1
                    time.sleep(self.fetch_interval)
                    continue

                consecutive_errors = 0
                self._fetch_count += 1
                batch_df = top_now.copy()

                # ── 2. Normalize ─────────────────────────────────────────────
                if 'code' not in batch_df.columns:
                    batch_df = batch_df.reset_index()
                batch_df['code'] = batch_df['code'].astype(str).str.zfill(6)
                
                rename_map = {}
                if 'trade' not in batch_df.columns:
                    for col in ['close', 'price', 'now', 'open']:
                        if col in batch_df.columns:
                            rename_map[col] = 'trade'
                            break
                if 'settlement' not in batch_df.columns and 'llastp' in batch_df.columns:
                    rename_map['llastp'] = 'settlement'
                if rename_map:
                    batch_df.rename(columns=rename_map, inplace=True)

                # 强制数值化
                for col in ['trade', 'settlement', 'open', 'high', 'low']:
                    if col in batch_df.columns:
                        batch_df[col] = pd.to_numeric(batch_df[col], errors='coerce').fillna(0.0)

                # ── 3. [FIXED] 统一数据源：使用 TickSeries 昨收 ─────────────────
                batch_df['settlement'] = batch_df['code'].map(
                    lambda x: getattr(self.detector._tick_series.get(x), 'last_close', 0)
                )

                # ── 4. [FIXED] 同步到 TickSeries (手动赋值) ─────────────────────
                with self.detector._lock:
                    for row_t in batch_df.itertuples(index=False):
                        r_dict = row_t._asdict()
                        c = r_dict.get('code')
                        if c in self.detector._tick_series:
                            ts = self.detector._tick_series[c]
                            price = r_dict.get('trade', 0)
                            settlement = r_dict.get('settlement', 0)
                            
                            if price > 0:
                                ts.now_price = price
                                if ts.last_close <= 0 and settlement > 0:
                                    ts.last_close = settlement
                                
                                if price > ts.high_day: ts.high_day = price
                                if price < ts.low_day or ts.low_day == 0: ts.low_day = price
                                
                                if ts.open_price <= 0 and r_dict.get('open', 0) > 0:
                                    ts.open_price = r_dict['open']

                # ── 5. [FIXED] 计算 Percent & 同步 High/Low ─────────────────────
                # 强制使用最新的 settlement 算涨幅
                batch_df['percent'] = ((batch_df['trade'] - batch_df['settlement']) / 
                                      batch_df['settlement'].mask(batch_df['settlement'] == 0, 1) * 100).round(2)
                
                # 强制同步价格，防止 detector 使用 sina 历史脏数据
                batch_df['high'] = batch_df['trade']
                batch_df['low'] = batch_df['trade']

                # ── 6. [FIXED] 时间戳使用系统时间 ────────────────────────────────
                t_str = now_dt.strftime('%H:%M:%S')
                batch_df['timestamp'] = now_dt.strftime('%Y-%m-%d %H:%M:%S')

                # ── 7. 每开盘首笔数据清理 ─────────────────────────────────────
                if self._fetch_count == 1:
                    with self.detector._lock:
                        self.detector.active_sectors.clear()
                        self.detector.daily_watchlist.clear()

                # ── 8. Downstream Flow ──────────────────────────────────────
                self.publisher.update_batch(batch_df)
                self.detector.update_scores() 

                dt = time.time() - t0
                self.status_update.emit(f"🔴 实盘中 (耗时:{dt:.2f}s) | 计数:{self._fetch_count}")
                self.progress_update.emit(t_str)

                time.sleep(max(0.1, self.fetch_interval - dt))

            except Exception as e:
                logger.exception(f"❌ [LiveWorker] 循环异常: {e}")
                time.sleep(self.fetch_interval)

        logger.info(f"🔴 [LiveWorker] 实盘结束. 共拉取 {self._fetch_count} 次.")
        self.finished.emit()

    def stop(self):
        self.is_running = False


def run_replay(start_time_str="09:25:00", end_time_str="15:00:00", playback_speed=0.0, stops=None, concise=True, resample=None, codes=None, replay_date=None, ui_callback=None, detector=None, publisher=None, real_df_all=None, panel=None):
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
    # [CIRCULAR-FIX] 局部导入以避免与 MonitorTK 产生循环引用
    from instock_MonitorTK import test_single_thread
    
    if stops is None:
        stops = []
        
    is_ui_mode = (ui_callback is not None)
    if not is_ui_mode:
        logger.info(f"Loading data from {HDF5_FILE} (key={KEY})...")
    
    if not os.path.exists(HDF5_FILE):
        logger.error(f"Cannot find HDF5 file: {HDF5_FILE}")
        return
        
    # 读取全天所有个股 tick 的快照
    # 适配 MultiIndex (code, ticktime) 或普通 Index
    df = pd.read_hdf(HDF5_FILE, KEY)
    
    logger.info(f"Loaded {len(df)} total records from HDF5.")

    # 1. 展开索引并统一列名
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()
    elif df.index.name in ('ticktime', 'time'):
        df = df.reset_index()
        
    # 统一时间列名为 ticktime
    if 'ticktime' not in df.columns and 'time' in df.columns:
        df.rename(columns={'time': 'ticktime'}, inplace=True)
            
    # 2. 转换为 Datetime 并剔除无效时间戳
    if not df.empty:
        df['ticktime'] = pd.to_datetime(df['ticktime'], errors='coerce')
        df = df.dropna(subset=['ticktime']).copy()
    prev_len = len(df)
    df = df.dropna(subset=['ticktime'])
    if len(df) < prev_len:
        logger.warning(f"Dropped {prev_len - len(df)} records with invalid timestamps (NaT).")

    # 3. 日期过滤检测 (YYYY-MM-DD)
    if df.empty:
        logger.error("Dataframe is empty after datetime conversion.")
        return

    if replay_date:
        target_date = pd.to_datetime(replay_date).date()
        df = df[df['ticktime'].dt.date == target_date].copy()
        if df.empty:
            logger.error(f"No data found for date: {replay_date}")
            return
        logger.info(f"Filtered for date: {replay_date}. Rows: {len(df)}")
    else:
        # [FIX] 健壮提取最新日期，避免 .dt.date.max() 触发 AttributeError
        try:
            latest_dt = df['ticktime'].max()
            if pd.isna(latest_dt): 
                logger.error("No valid timestamps found to determine date.")
                return
            latest_date = latest_dt.date()
            df = df[df['ticktime'].dt.date == latest_date].copy()
            logger.info(f"Auto-selected latest recording date: {latest_date}. Rows: {len(df)}")
        except Exception as e:
            logger.error(f"Failed to infer latest date: {e}")
            return

    # 4. 严格交易时段过滤 (09:25:00 - 15:00:00)
    # 剔除无效的非交易时段 tick，防止干扰 detector 锚点
    df['_hms'] = df['ticktime'].dt.strftime('%H:%M:%S')
    start_f = start_time_str if start_time_str else "09:25:00"
    end_f = end_time_str if end_time_str else "15:00:00"
    
    df = df[(df['_hms'] >= start_f) & (df['_hms'] <= end_f)].copy()
    
    # 优先使用 run_replay 传入的参数，如果没有传入则使用默认值
    start_time_filter = start_time_str if start_time_str else "09:25:00"
    end_time_filter = end_time_str if end_time_str else "15:00:00"
    
    df = df[(df['_hms'] >= start_time_filter) & (df['_hms'] <= end_time_filter)].copy()
    
    # 过滤指定的代码
    if codes:
        if isinstance(codes, str):
            codes = [c.strip() for c in codes.split(',')]
        df = df[df['code'].astype(str).str.zfill(6).isin(codes)]
        logger.info(f"Filtered playback data for {len(codes)} stocks: {codes}")

    # 按照实际 ticktime 进行排序
    df.sort_values(by='ticktime', inplace=True)
    
    # 恢复老的 ticktime 格式 (HH:MM:SS 字符串) 兼容后续逻辑
    df['ticktime'] = df['_hms']
    df.drop(columns=['_hms'], inplace=True)
    
    logger.info(f"Final slice range: {start_time_filter} - {end_time_filter}. Total ticks: {len(df)}")
    
    # --- [REAL DATA MODE] ---
    if real_df_all is None:
        logger.info(f"Fetching REAL production data (resample={resample}) for baseline registry...")
        real_df_all = test_single_thread(single=True, resample=resample, log_level=LoggerFactory.ERROR)
    else:
        logger.info(f"🚀 [OPTIMIZED] Using injected real_df_all (count={len(real_df_all)}) from parent process.")
        
    if real_df_all is None or real_df_all.empty:
        logger.error("Failed to fetch real data from production environment.")
        return

    # [NEW] Verify Metadata Columns (Including Base Volume for Ratio Calculation)
    required_cols = ['category', 'lastp1d', 'ma20d', 'lastdu4', 'ral', 'top0', 'top15']
    if 'lastv1d' not in real_df_all.columns and 'last6vol' not in real_df_all.columns:
        logger.warning("⚠️ Real data missing volume baseline (lastv1d/last6vol). Ratio calc may fallback.")
    
    # [INDEX-STANDARDIZATION] 强制将 real_df_all 索引标准化为 6 位字符串代码
    if 'code' in real_df_all.columns:
        real_df_all['code'] = real_df_all['code'].astype(str).str.zfill(6)
        real_df_all.set_index('code', inplace=True)
    else:
        real_df_all.index = real_df_all.index.astype(str).str.zfill(6)
        real_df_all.index.name = 'code'
        
    logger.info(f"Successfully fetched {len(real_df_all)} real stock records (Index Standardized).")
    
    # [DATA INTEGRITY] Reset real-time columns to ensure we don't leak "future" 
    # final percentages into early simulation stages.
    leakage_cols = ['percent', 'ratio', 'now', 'price', 'trade', 'high', 'low', 'volume', 'amount', 'per1d']
    for col in leakage_cols:
        if col in real_df_all.columns:
            real_df_all[col] = 0.0
            
    # [NEW] Filter the registry/baseline data if specific codes are targeted
    
    if codes:
        if isinstance(codes, str):
            codes = [c.strip().zfill(6) for c in codes.split(',')]
        real_df_all = real_df_all[real_df_all.index.isin(codes)]
        logger.info(f"Filtered baseline registry for {len(codes)} stocks.")

    # [Phase 4] 注册代码名称对应关系
    if publisher is None:
        publisher = DataPublisher(high_performance=True, scraper_interval=99999, enable_backup=False, 
                                   simulation_mode=True, verbose=not concise)
    publisher.register_names(real_df_all)
    pd.options.mode.chained_assignment = None # 避免测试时出现 SettingWithCopyWarning
    
    # 屏蔽不必要的外部数据抓取和干扰
    cct.get_work_time_duration = lambda: True # 强制算作开盘交易日
    cct.get_trade_date_status = lambda: True
    # 我们不需要真实时间自动备份和抓取外部
    publisher.set_paused(True) 
    
    if detector is None:
        detector = BiddingMomentumDetector(realtime_service=publisher, simulation_mode=True)
    else:
        # [NEW] 重用传入的 detector，绑定 publisher
        detector.realtime_service = publisher
    
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

    # [SIM-DATE] 提前确定模拟日期，用于量比计算与时间戳生成
    sim_date = replay_date if replay_date else datetime.now().strftime('%Y-%m-%d')

    _last_emitted_t_str = ""
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
                    if wait_time > 2.0: wait_time = 0.5 # 遇到长空档压缩等待
                        
                    elapsed = time.time() - last_real_time
                    remaining_wait = wait_time - elapsed
                    
                    while remaining_wait > 0:
                        # [THROTTLE] 只有时间真实改变才触发 UI 回调，防止高频空转信号导致界面跳动
                        if ui_callback:
                            if t_str != _last_emitted_t_str:
                                if not ui_callback(t_str): return
                                _last_emitted_t_str = t_str
                            else:
                                # 仅检查运行状态，不发射信号
                                if not ui_callback(None): return 
                        
                        sleep_step = min(remaining_wait, 0.05)
                        time.sleep(sleep_step)
                        remaining_wait -= sleep_step
                        
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
            
            # [PERF] 利用 Vectorized 方式同步 Tick 级别价格数据到 Detector 中
            # 避免使用 5000 次 itertuples(), 直接通过 Series.map 或 dict 批量注入
            batch_prices = batch_df.set_index('code')['trade'].to_dict()
            batch_settlements = batch_df.set_index('code')['settlement'].to_dict() if 'settlement' in batch_df.columns else {}
            
            with detector._lock:
                for c, price in batch_prices.items():
                    c_str = str(c).zfill(6)
                    if c_str in detector._tick_series:
                        ts = detector._tick_series[c_str]
                        p_val = float(price)
                        if p_val > 0:
                            ts.now_price = p_val
                            if ts.last_close <= 0:
                                s_val = float(batch_settlements.get(c, 0))
                                if s_val > 0: ts.last_close = s_val
                                
                            if p_val > ts.high_day: ts.high_day = p_val
                            if p_val < ts.low_day or ts.low_day == 0: ts.low_day = p_val
            
            # [DATA LEAKAGE PROTECTION] 强制重新计算涨幅，防止 HDF5 中自带的 EOD 涨幅干扰回测
            if 'trade' in batch_df.columns:
                # 寻找昨收：优先用 settlement (llastp), 否则用 real_df_all 中的 lastp1d
                if 'settlement' not in batch_df.columns or (batch_df['settlement'] == 0).all():
                    # 尝试从 registry 补全昨收
                    batch_df['settlement'] = batch_df['code'].map(lambda x: getattr(detector._tick_series.get(x), 'last_close', 0))
                
                # [FIX] 确保 settlement 有效，否则 percent 计算会变成 inf 或 0
                has_valid_settle = (batch_df['settlement'] > 0).any()
                if not has_valid_settle:
                    # 极限兜底：从 df 本身找 (如果是 MultiIndex 可能会有)
                    pass 

                # 强制覆盖 percent
                batch_df['percent'] = (batch_df['trade'] - batch_df['settlement']) / batch_df['settlement'] * 100
                batch_df.loc[batch_df['settlement'] <= 0, 'percent'] = 0.0
                
                # [FIX] 强制覆盖 high/low 为当前价，防止 Detector 从 row 获取到 EOD 高低点
                batch_df['high'] = batch_df['trade']
                batch_df['low'] = batch_df['trade']
                
            # [Task] 基于上一日成交量与日内进度的动态量比校准 (仿真模式核心逻辑)
            # 我们需要对比 (当前时刻成交量) / (上一日总成交量 * 时间比例)
            if 'volume' in batch_df.columns:
                # 1. 对齐生产列名：将 HDF5 原始成交量重命名为 'vol' (Original Volume)
                # 腾出 'volume' 位置给量比计算结果 (Ratio)
                batch_df.rename(columns={'volume': 'vol'}, inplace=True)
                
                # 2. 映射基座成交量 (优先 lastv1d, 否则 last6vol)
                base_v_series = real_df_all['lastv1d'] if 'lastv1d' in real_df_all.columns else real_df_all.get('last6vol', pd.Series(0, index=real_df_all.index))
                
                # 3. 计算物理时刻比例与基座
                sim_dt = datetime.strptime(f"{sim_date} {t_str}", '%Y-%m-%d %H:%M:%S')
                time_ratio = cct.get_work_time_ratio_sbc(now_time=sim_dt)
                batch_df['base_vol'] = batch_df['code'].map(base_v_series)
                
                # 4. 矢量化计算量比写入 'volume' (对齐 strategy_config.py 中的 "量比" 定义)
                batch_df['volume'] = (batch_df['vol'] / (batch_df['base_vol'] * time_ratio)).round(2)
                
                # 5. 边界处理与占位符填充
                batch_df.loc[(batch_df['base_vol'] <= 0) | (pd.isna(batch_df['volume'])), 'volume'] = 1.0
                batch_df['ratio'] = batch_df['volume'] # 双保险备份
                batch_df.drop(columns=['base_vol'], inplace=True)
            else:
                 batch_df['volume'] = 1.0
                 batch_df['ratio'] = 1.0
                 
            # 结合内置的规则模拟 metadata (保证能被 BiddingMomentumDetector 按概念切分)
            if 'code' in batch_df.columns:
                # batch_df['code'] 可能为文本类型，确保是 6 位
                batch_df['code'] = batch_df['code'].astype(str).str.zfill(6)
                # Metadata is now handled by the publisher's df_all seeded with real_df_all
                 
            # [核心]: 送入数据泵
            # 注入模拟时间戳，确保 detector 的日期判定逻辑与回放日期一致
            batch_df['timestamp'] = f"{sim_date} {t_str}" 
            
            # 向核心系统泵入 (这里它会自动处理分钟K线切割、情绪计算)
            t0 = time.time()
            publisher.update_batch(batch_df)
            t1 = time.time()
            
            # 实时让探测器跑分 (使用 skip_evaluate=True，因为前面的 update_batch 已通过回调执行过 _evaluate_code)
            active_codes = [str(c).zfill(6) for c in batch_df['code'].tolist()]
            detector.update_scores(active_codes=active_codes, skip_evaluate=True)
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
                
                # 速度评价 (使用 ASCII 兼容 Windows GBK 终端)
                if speed_x > 50: speed_label = ">>>>>"
                elif speed_x > 20: speed_label = ">>>>"
                elif speed_x > 5: speed_label = ">>>"
                elif speed_x > 1: speed_label = ">>"
                else: speed_label = ">"
                
                if concise:
                    sys.stdout.write(f"\r[Playback] {speed_label} {t_str} | {speed_x:.1f}x ({tps:.0f} tps) | Total: {len(publisher.kline_cache.cache)}      ")
                else:
                    sys.stdout.write(f"\r[Playback] {speed_label} Progress: {t_str} | Speed: {speed_x:.1f}x ({tps:.0f} tps) | Pub: {cost_pub:.1f}ms | Det: {cost_det:.1f}ms | Total: {len(publisher.kline_cache.cache)}      ")
                sys.stdout.flush()
            
            # [UI MODE OPTIMIZATION] 释放一点 CPU 给 UI 线程
            if is_ui_mode:
                time.sleep(0.001)

            # [UI CALLBACK]
            if ui_callback:
                if not ui_callback(t_str):
                    logger.info("Playback stopped by UI request.")
                    break
    
            # 检查是否到达切片观察点 (UI 模式下不再控制台停顿)
            if not is_ui_mode and next_stop_idx < len(stops) and str(t_str) >= str(stops[next_stop_idx]):
                stop_time = stops[next_stop_idx]
                sys.stdout.write("\n\n")
                logger.info(f"=== ⏰ 触发时间切片停顿观测点: {stop_time} ===")
                
                # [NEW] 调用深度自检分析
                analyze_data_integrity(detector, stop_time)
                
                # [NEW] 打印当前个股前 10 评分，排查为何板块为空
                all_ts = sorted(detector._tick_series.values(), key=lambda x: x.score, reverse=True)
                print(f"\n🚀 [{stop_time}] 当下个股评分排行 (Top 5):")
                # 获取 EmotionTracker 的当前分数
                emotion_scores = publisher.emotion_tracker.scores
                for ts in all_ts[:5]:
                    e_score = emotion_scores.get(ts.code, 0.0)
                    c_stage = getattr(ts, 'cycle_stage', 2)
                    print(f"  {ts.code} ({getattr(ts, 'name', 'N/A')}) - 结构: {ts.score:.1f}, 周期: {c_stage}, 热度: {e_score:.1f}, \033[94m涨跌: {ts.pct_diff:+.2f}%\033[0m")
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
                    
                    if hasattr(publisher, 'emotion_tracker'):
                        # leader_emotion = publisher.emotion_tracker.scores.get(sec_info['leader'], 0.0)
                        pass

                    
                    leader_pattern = sec_info.get('pattern_hint', '')
                    leader_time = pd.Timestamp.fromtimestamp(sec_info['leader_first_ts']).strftime('%H:%M:%S') if sec_info['leader_first_ts']>0 else 'N/A'
                    
                    # [NEW] 打印龙头的涨跌与分差
                    l_pct_diff = sec_info.get('leader_pct_diff', 0.0)
                    l_score_diff = sec_info.get('leader_score_diff', 0.0)
                    
                    print(f"     -> 领涨龙头: {leader_info} [强度: {sec_info['score']:.1f} | 涨跌: {l_pct_diff:+.2f}% | 分差: {l_score_diff:+.1f}] [首异: {leader_time}]")
                    if leader_pattern:
                        print(f"        [形态: {leader_pattern}]")
                    
                    # 获取该板块下的所有跟风股，并打印更多细节（涨跌、分差）
                    f_parts = []
                    for f in sec_info.get("followers", [])[:8]:
                        f_code = f['code']
                        f_em = 0.0
                        if hasattr(publisher, 'emotion_tracker'):
                            f_em = publisher.emotion_tracker.scores.get(f_code, 0.0)
                        
                        f_ts = f.get('first_ts', 0)
                        f_time = pd.Timestamp.fromtimestamp(f_ts).strftime('%H:%M:%S') if f_ts > 0 else '?'
                        
                        # [NEW] 提取 pct_diff (涨跌) 和 score_diff
                        f_pct_diff = f.get('pct_diff', 0.0)
                        f_score_diff = f.get('score_diff', 0.0)
                        
                        # 格式化输出：代码(名称) [现涨 变动涨跌/分差]
                        diff_str = f"{f_pct_diff:+.2f}%/{f_score_diff:+.1f}"
                        f_parts.append(f"{f.get('name', 'N/A')} ({f_code}) [\033[92m{f.get('pct', 0.0):+.1f}%\033[0m 变:{diff_str}]")
                    
                    if f_parts:
                        print(f"     -> 跟风股详情: {', '.join(f_parts)}")
                    
                    # [DATA INTEGRITY CHECK] 验证个股涨跌是否为 0
                    if all(f.get('pct_diff', 0.0) == 0.0 for f in sec_info.get("followers", [])) and sec_info.get("followers"):
                        print(f"     ❌ \033[91m[DATA ERROR]\033[0m 所有个股涨跌均为 0，请检查锚点逻辑！")
                    else:
                        print(f"     ✅ [DATA OK] 个股异动数据已成功记录")
                    
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

def main(args=None, df_all_target=None):
    """
    [REFACTORED] 赛马回测入口，支持通过 mp.Process 直接透传 df_all 数据。
    """
    if args is None:
        import argparse
        from datetime import datetime
        today_str = datetime.now().strftime('%Y-%m-%d')
        parser = argparse.ArgumentParser(
            description="Sector Bidding Slice Backtest/Replay Tool",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"""
Usage Examples:
  1. High-speed Replay (UI Mode):
     python test_bidding_replay.py --ui --speed 100.0 --verbose --start 09:30:00 --log WARNING
  2. Live Trading Monitor (UI Mode):
     python test_bidding_replay.py --ui --live
  3. Specific Date Debug (UI Mode):
     python test_bidding_replay.py --ui --speed 20.0 --verbose --start 09:25:00 --log DEBUG --date {today_str}
"""
        )
        parser.add_argument("--speed", type=float, default=0.0, help="Playback speed multiplier (e.g. 1.0, 10.0). 0.0 means full speed.")
        parser.add_argument("--observation", type=str, action="append", help="Observation timestamps (HH:MM:SS) to pause and inspect. Can be specified multiple times.")
        parser.add_argument("--start", type=str, default="09:25:00", help="Simulation start time (HH:MM:SS)")
        parser.add_argument("--end", type=str, default="15:00:00", help="Simulation end time (HH:MM:SS)")
        parser.add_argument("--verbose", action="store_true", help="Show detailed price/performance logs (not concise).")
        parser.add_argument("--resample", type=str, default=None, choices=['d', '2d', '3d', 'w', 'm'], help="Data resample period for baseline registry (d: daily, w: weekly, m: monthly, etc.)")
        parser.add_argument("--codes", type=str, default=None, help="Stock codes for targeted testing (comma-separated, e.g., 688787,002536)")
        parser.add_argument("--date", type=str, default=None, help="Replay specific date (YYYY-MM-DD)")
        parser.add_argument("--today", action="store_true", help="Automatically replay today's data")
        parser.add_argument("--ui", action="store_true", help="Launch High-Performance Bidding Racing UI")
        parser.add_argument("--live", action="store_true", help="Enable Live Trading Mode")
        parser.add_argument("--interval", type=int, default=30, help="Data fetch interval in seconds for live mode (default: 30)")
        parser.add_argument("--log", type=lambda s: s.upper(), default="WARNING", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Console log level")
        args = parser.parse_args()

    # --- [LOG-CONTROL] 解析日志级别映射 ---
    log_level_map = {
        'DEBUG': LoggerFactory.DEBUG,
        'INFO': LoggerFactory.INFO,
        'WARNING': LoggerFactory.WARNING,
        'ERROR': LoggerFactory.ERROR
    }
    # 如果 args.log 是字符串（来自 CLI），则转换；如果是 int（来自 mp.Process 注入），则直接使用
    if isinstance(args.log, str):
        user_log_level = log_level_map.get(args.log.upper(), LoggerFactory.WARNING)
    else:
        user_log_level = args.log if args.log is not None else LoggerFactory.WARNING

    logger.info("Initializing Sector Bidding Slice Backtest Tool...")
    # 默认观测点
    slice_stops = []
    if hasattr(args, 'observation') and args.observation:
        for s in args.observation:
            slice_stops.extend([x.strip() for x in s.split(',')])
    else:
        slice_stops = ["09:45:00", "10:00:00", "10:30:00", "11:00:00", "13:30:00", "14:00:00", "14:30:00", "14:45:00"]
    
    # 日期逻辑处理
    replay_date = args.date
    if hasattr(args, 'today') and args.today:
        replay_date = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Today mode enabled. Targeting date: {replay_date}")

    replay_kwargs = dict(
        start_time_str=args.start, 
        end_time_str=args.end, 
        playback_speed=args.speed, 
        stops=slice_stops,
        concise=not getattr(args, 'verbose', False),
        resample=args.resample,
        codes=args.codes,
        replay_date=replay_date
    )
    
    # --- [REAL DATA MODE] --- 获取基准行情时透传日志级别
    real_df_all = None
    if not args.codes:
        resample = args.resample
        # 🚀 [OPTIMIZED] 如果外部注入了 df_all，直接使用，杜绝重复计算
        if df_all_target is not None and not df_all_target.empty:
            logger.info(f"✅ Receiving injected df_all (count={len(df_all_target)}) from parent process.")
            real_df_all = df_all_target
        else:
            logger.info(f"Fetching REAL production data (resample={resample}) for baseline registry...")
            from instock_MonitorTK import test_single_thread
            real_df_all = test_single_thread(single=True, resample=resample, log_level=user_log_level)
            
        if real_df_all is None or real_df_all.empty:
            logger.error("Failed to fetch real data from production environment.")
        else:
            # from bidding_momentum_detector import BiddingMomentumDetector
            pass

    if args.ui and UI_AVAILABLE:
        # 在子进程中创建 QApplication 时，需要确保 sys.argv 有效
        app = QApplication(sys.argv if sys.argv else ['test_bidding_replay.py'])
        
        # --- [SILENT-MODE] 强力压制全局单例 Logger ---
        try:
            global_logger = LoggerFactory.getLogger()
            global_logger.setLevel(user_log_level)
            import logging
            logging.getLogger().setLevel(logging.WARNING)
            if user_log_level >= LoggerFactory.WARNING:
                print(f"🤫 静默模式：当前后台日志级别已设为 {str(args.log).upper()}")
        except Exception as e:
            logger.exception(f"Log conversion failed: {e}")

        # [LINKAGE] 初始化联动发送器
        from JohnsonUtil.stock_sender import StockSender
        sender = StockSender(tdx_var=True, ths_var=False, dfcf_var=False)
        
        from bidding_momentum_detector import BiddingMomentumDetector
        from realtime_data_service import DataPublisher
        
        if args.live:
            # ========================================
            # 实盘模式 (Live Mode)
            # ========================================
            logger.info("🔴 Starting LIVE Trading Mode...")
            
            # Step 1: 获取基准数据
            resample = args.resample
            live_df_all = real_df_all
            if live_df_all is None or live_df_all.empty:
                live_df_all = test_single_thread(single=True, resample=resample, log_level=user_log_level)
            if live_df_all is None or live_df_all.empty:
                print("❌ 基线数据获取失败，无法启动实盘模式。")
                return # In main context, return is safer than sys.exit
            
            # Step 2: 创建 Publisher 和 Detector
            publisher = DataPublisher(
                high_performance=True, 
                scraper_interval=99999,
                enable_backup=False,
                simulation_mode=False,
                verbose=args.verbose
            )
            detector = BiddingMomentumDetector(
                realtime_service=publisher, 
                simulation_mode=False
            )
            
            # Step 3: 创建 Panel
            panel = BiddingRacingRhythmPanel(sender=sender)
            panel.detector = detector
            panel.setWindowTitle("🏁 竞价赛马 🔴 实盘监控")
            
            # Step 4: 创建 LiveWorker
            worker = LiveWorker(
                detector=detector,
                publisher=publisher,
                real_df_all=live_df_all,
                resample=resample,
                fetch_interval=args.interval,
                log_level=user_log_level
            )
            
            def on_live_progress(t_str):
                from PyQt6.sip import isdeleted
                if isdeleted(panel): return
                # [🚀 状态锁] 优先设置前缀，然后调用 set_time 时传入该前缀
                prefix = "🔴 实盘监控"
                if hasattr(panel, 'set_status_prefix'):
                    panel.set_status_prefix(prefix)
                panel.timeline.set_time(t_str, prefix=prefix)
            
            def on_live_status(status_text):
                if hasattr(panel, 'set_status_prefix'):
                    panel.set_status_prefix(status_text)
                else:
                    panel.timeline.label.setText(status_text)
            
            def on_panel_closed():
                worker.stop()
                worker.wait()
                
                # [NEW] 显式停止核心组件，释放线程与句柄
                try:
                    publisher.stop()
                except: pass
                try:
                    if hasattr(detector, 'stop'):
                        detector.stop()
                except: pass
                try:
                    if hasattr(sender, 'close'):
                        sender.close()
                except: pass

                # [EXIT-GUARD] 强制退出主进程前，先清理所有活跃的子进程 (包含 DNA 审计、数据 Publisher 等)
                import os
                import multiprocessing as mp
                try:
                    for p in mp.active_children():
                        if p.is_alive():
                            logger.info(f"🔪 Cleaning up background child process: {p.pid}")
                            p.terminate()
                            p.join(timeout=0.5)
                except: pass
                
                logger.info("👋 Replay App exiting via app.quit()...")
                QApplication.instance().quit()
            
            panel.closed.connect(on_panel_closed)
            worker.progress_update.connect(on_live_progress)
            worker.status_update.connect(on_live_status)
            worker.start()
            
            panel.show()
            app.exec()
        else:
            # ========================================
            # 回放模式 (Replay Mode)
            # ========================================
            logger.info("Starting UI-based Racing Replay...")
            
            # 创建仿真 Publisher (从 HDF5 读取)
            # 注意：此处必须使用本地导入以防多进程冲突
            from realtime_data_service import DataPublisher
            from bidding_momentum_detector import BiddingMomentumDetector
            
            publisher = DataPublisher(
                high_performance=True,
                scraper_interval=99999,
                enable_backup=False,
                simulation_mode=True,  # 仿真读取模式
                verbose=args.verbose
            )
            
            detector = BiddingMomentumDetector(
                realtime_service=publisher,
                simulation_mode=True
            )
            
            # 初始化 Panel (必须在 detector 创建后，以便传入引用)
            panel = BiddingRacingRhythmPanel(sender=sender, detector=detector)
            panel.setWindowTitle(f"🏁 竞价赛马回放 : {replay_date or 'ALL'}")
            
            replay_kwargs['detector'] = detector
            replay_kwargs['publisher'] = publisher
            replay_kwargs['real_df_all'] = real_df_all
            replay_kwargs['panel'] = panel
            
            # 开启后台回放线程
            worker = ReplayWorker(replay_kwargs)
            
            def on_progress(t_str):
                from PyQt6.sip import isdeleted
                if isdeleted(panel): return
                # [🚀 状态锁] 优先设置前缀，然后调用 set_time 时传入该前缀
                prefix = f"🎥 录像回放中 ({int(args.speed)}x)"
                if hasattr(panel, 'set_status_prefix'):
                    panel.set_status_prefix(prefix)
                panel.timeline.set_time(t_str, prefix=prefix)

            def on_panel_closed():
                worker.stop()
                worker.wait()
                
                # [NEW] 显式停止核心组件，释放线程与句柄
                try:
                    publisher.stop()
                except: pass
                try:
                    if hasattr(detector, 'stop'):
                        detector.stop()
                except: pass
                try:
                    if hasattr(sender, 'close'):
                        sender.close()
                except: pass

                # [EXIT-GUARD] 强制退出主进程前，先清理所有活跃的子进程 (包含 DNA 审计、数据 Publisher 等)
                import os
                import multiprocessing as mp
                try:
                    for p in mp.active_children():
                        if p.is_alive():
                            logger.info(f"🔪 Cleaning up background child process: {p.pid}")
                            p.terminate()
                            p.join(timeout=0.5)
                except: pass

                logger.info("👋 Replay App exiting via app.quit()...")
                QApplication.instance().quit()
            
            panel.closed.connect(on_panel_closed)
            worker.progress_update.connect(on_progress)
            panel.show()
            worker.start()
            
            app.exec() # 等待 UI 退出
            
            # [EXIT-GUARD] 确保退出时回收线程
            worker.stop()
            worker.wait(1000)
    else:
        # 无 UI 命令行模式
        run_replay(**replay_kwargs)

if __name__ == "__main__":
    import multiprocessing as mp
    mp.freeze_support()
    main()
