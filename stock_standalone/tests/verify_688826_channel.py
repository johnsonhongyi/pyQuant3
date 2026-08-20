# -*- coding: utf-8 -*-
"""
验证通达信 688826 5分钟 K 线自动通道与支撑线计算结果
"""
import sys
import os
import pandas as pd

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from JSONData.tdx_data_Day import calc_trend_channel

def test_688826_channel_values():
    fetcher = TDXRealtimeFetcher.get_instance()
    df = fetcher.fetch_kline_bars("688826", category="5m", count=150)
    if df.empty:
        print("未获取到 688826 5分钟 K 线数据（可能未连接行情服务器）")
        return

    print("=" * 60)
    print(f"688826 5分钟 K 线 (最新 {len(df)} 根):")
    last_row = df.iloc[-1]
    print(f"最新价: {last_row['close']:.2f}")
    if 'ch_upper' in df.columns:
        print(f"自动通道上轨 (ch_upper): {last_row['ch_upper']:.2f}")
        print(f"自动通道中轨 (ch_mid):   {last_row['ch_mid']:.2f}")
        print(f"自动通道下轨 (ch_lower): {last_row['ch_lower']:.2f}")
        print(f"通道斜率 (ch_slope_deg): {last_row['ch_slope_deg']:.2f}°")
        print(f"通道位置 (ch_pos):       {last_row['ch_pos']:.2f}%")
        print(f"上涨支撑 (ch_supp_price):{last_row['ch_supp_price']:.2f} 元 (支撑天数: {last_row['ch_supp_days']} 根)")
        print(f"翻转线   (reversal_line):{last_row['reversal_line']:.2f} 元")
        print(f"Fibonacci 50% (fib_50):  {last_row['fib_50']:.2f}")
    print("=" * 60)

def test_688313_day_channel():
    fetcher = TDXRealtimeFetcher.get_instance()
    df = fetcher.fetch_kline_bars("688313", category="day", count=200)
    if df.empty:
        print("未获取到 688313 日K 线数据")
        return
    print("=" * 60)
    print(f"688313 仕佳光子 日K 线 (共 {len(df)} 根):")
    last_row = df.iloc[-1]
    tc2 = int(last_row.get('ch_tc2', 1))
    bc2 = int(last_row.get('ch_bc2', 1))
    chan_len = max(tc2, bc2)
    chan_start = max(0, len(df) - chan_len)
    print(f"最新收盘价: {last_row['close']:.2f} 元")
    print(f"波段高点周期 (tc2): {tc2} 根, 波段低点周期 (bc2): {bc2} 根")
    print(f"通道有效起始索引: {chan_start} (仅在最新 {chan_len} 根 K 棒绘制通道，历史左侧前 {chan_start} 根截断不画)")
    print(f"通道上轨: {last_row['ch_upper']:.2f}, 下轨: {last_row['ch_lower']:.2f}")
    print(f"神奇九转 (TD) 上涨计数: {last_row.get('td_sell_count', 0)}, 下跌计数: {last_row.get('td_buy_count', 0)}")
    print("=" * 60)

def test_688313_60m_channel():
    fetcher = TDXRealtimeFetcher.get_instance()
    df = fetcher.fetch_kline_bars("688313", category="60m", count=200)
    if df.empty:
        print("未获取到 688313 60分K 线数据")
        return
    print("=" * 60)
    print(f"688313 仕佳光子 60分钟K 线 (共 {len(df)} 根):")
    last_row = df.iloc[-1]
    td_sell_arr = df['td_sell_count'].values if 'td_sell_count' in df.columns else []
    td_buy_arr = df['td_buy_count'].values if 'td_buy_count' in df.columns else []
    print(f"最新价: {last_row['close']:.2f} 元")
    print(f"最新 60分K 神奇九转 上涨计数: {last_row.get('td_sell_count', 0)}, 下跌计数: {last_row.get('td_buy_count', 0)}")
    print(f"历史触发 9 转次数: 上涨 9 转 = {sum(1 for x in td_sell_arr if x == 9)} 次, 下跌 9 转 = {sum(1 for x in td_buy_arr if x == 9)} 次")
    print("=" * 60)

if __name__ == "__main__":
    test_688826_channel_values()
    test_688313_day_channel()
    test_688313_60m_channel()
