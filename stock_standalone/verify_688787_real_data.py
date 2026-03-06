import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# 环境配置
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'stock_standalone'))
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import johnson_cons as ct
from realtime_data_service import IntradayEmotionTracker, DailyEmotionBaseline
from stock_visual_utils import show_chart_with_signals, SignalPoint, SignalType

def verify_with_real_data(code='688787'):
    print(f"🚀 [实战验证] 正在使用实盘数据验证 {code} 的 SBC 策略...")
    
    # 1. 加载日线基准数据 (TDD)
    try:
        resample = 'd'
        # 获取足够的历史数据来确保计算出 ma60d
        day_df = tdd.get_tdx_Exp_day_to_df(code, dl=ct.Resample_LABELS_Days[resample], resample=resample)
        if day_df is None or day_df.empty:
            print(f"❌ 无法获取 {code} 的日线基准数据")
            return
            
        # 转换列名以匹配 DailyEmotionBaseline 的期望
        recent_df = day_df.copy()
        # 实盘数据源通常提供 ma20, ma60，探测器期望 ma20d, ma60d
        recent_df['ma60d'] = recent_df['ma60'] if 'ma60' in recent_df.columns else (recent_df['ma60d'] if 'ma60d' in recent_df.columns else recent_df['close'])
        recent_df['ma20d'] = recent_df['ma20'] if 'ma20' in recent_df.columns else (recent_df['ma20d'] if 'ma20d' in recent_df.columns else recent_df['close'])
        recent_df['ma5d'] = recent_df['ma5'] if 'ma5' in recent_df.columns else (recent_df['ma5d'] if 'ma5d' in recent_df.columns else recent_df['close'])
        
        # 提取昨日和前日数据供结构判断
        recent_df['lasth1d'] = recent_df['high'].shift(1)
        recent_df['lasth2d'] = recent_df['high'].shift(2)
        recent_df['lastp1d'] = recent_df['close'].shift(1)
        recent_df['lastp2d'] = recent_df['close'].shift(2)
        recent_df['last_low'] = recent_df['low'].shift(1)
        # 兼容旧代码字段
        recent_df['last_close'] = recent_df['lastp1d']
        recent_df['last_high'] = recent_df['lasth1d']
        
        # 填充 NaN (前两行由于 shift 会产生空值)
        recent_df = recent_df.ffill().bfill()
        
        baseline = DailyEmotionBaseline()
        # 传入最后一行 (包含前面 shift 出来的历史数据)
        baseline.calculate_baseline(recent_df.tail(1)) 
        
        anchors = baseline.get_anchor(code)
        if not anchors:
            print(f"❌ 未能为 {code} 生成结构锚点")
            return
            
        print(f"✅ 日线基准加载完成. MA60: {anchors.get('ma60', 0):.2f}, 昨日收盘: {anchors.get('last_close', 0):.2f}")
        print(f"📊 结构突破阈值 (yesterday_high/prev_high): {anchors.get('yesterday_high', 0):.2f} / {anchors.get('prev_high', 0):.2f}")
        print(f"📈 结构趋势 (p1 > p2): {anchors.get('last_close', 0):.2f} > {anchors.get('last_close_p2', 0):.2f} ? {anchors.get('is_rising_struct', False)}")
    except Exception as e:
        print(f"❌ 加载日线数据失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 加载实盘分钟线缓存 (Pickle)
    cache_path = r"G:\minute_kline_cache.pkl"
    if not os.path.exists(cache_path):
        print(f"❌ 未找到缓存文件: {cache_path}")
        return
        
    try:
        full_cache_df = pd.read_pickle(cache_path)
        stock_df = full_cache_df[full_cache_df['code'] == code].copy()
        if stock_df.empty:
            print(f"❌ 缓存中未找到 {code} 的分钟数据")
            return
            
        stock_df = stock_df.sort_values('time')
        print(f"✅ 成功加载 {len(stock_df)} 条分钟线数据.")
        print(f"💰 今日价格区间: {stock_df['low'].min():.2f} - {stock_df['high'].max():.2f}")
    except Exception as e:
        print(f"❌ 读取缓存失败: {e}")
        return

    # 3. 逐分钟模拟回放
    tracker = IntradayEmotionTracker()
    tracker._last_sbc_status = {} # 明确重置
    signals = []
    
    def format_time(ts):
        if ts > 1000000000: # Unix Timestamp
            dt = datetime.fromtimestamp(ts)
            return dt.strftime("%m-%d %H:%M")
        s = str(ts).zfill(4)
        return f"{s[:2]}:{s[2:]}"

    times = stock_df['time'].tolist()
    time_labels = [format_time(t) for t in times]
    
    print("\nProcessing ticks...")
    cum_vol = 0
    cum_amt = 0
    for i, row in enumerate(stock_df.itertuples()):
        v = row.volume
        a = getattr(row, 'amount', row.volume * row.close)
        cum_vol += v
        cum_amt += a
        
        tick_data = pd.DataFrame([{
            'code': code,
            'trade': row.close,
            'high': row.high,
            'low': row.low,
            'vol': cum_vol,    # 传入原始成交量用于 VWAP 计算
            'volume': row.volume_ratio if hasattr(row, 'volume_ratio') else 1.0, # 模拟量比
            'amount': cum_amt,
            'percent': (row.close - anchors['last_close']) / anchors['last_close'] * 100 if anchors.get('last_close') else 0
        }])
        
        tracker.update_batch(tick_data, baseline)
        
        status = tick_data['sbc_status'].iloc[0]
        if status and "🚀" in status:
            t_str = format_time(row.time)
            print(f"[{t_str}] 🎯 SBC Entry Triggered: {status} at {row.close:.2f}")
            signals.append(SignalPoint(code, row.time, i, row.close, SignalType.FOLLOW, reason=status))

    # 4. 可视化
    print(f"\n✅ 回放完成. 共捕捉到 {len(signals)} 个有效买点.")
    
    stock_df['cum_vol'] = stock_df['volume'].cumsum()
    amount_col = 'amount' if 'amount' in stock_df.columns else None
    if amount_col:
        stock_df['cum_amt'] = stock_df['amount'].cumsum()
    else:
        stock_df['cum_amt'] = (stock_df['volume'] * stock_df['close']).cumsum()
        
    vwap_series = (stock_df['cum_amt'] / stock_df['cum_vol']).tolist()
    viz_df = stock_df[['open', 'high', 'low', 'close', 'volume']].copy()
    
    show_chart_with_signals(
        viz_df, 
        signals, 
        f"Real Market: {code} SBC Strategy Backtest", 
        avg_series=vwap_series,
        time_labels=time_labels
    )

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else '688787'
    verify_with_real_data(target)
