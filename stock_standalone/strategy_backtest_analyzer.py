# -*- coding: utf-8 -*-
"""
策略自动化回测与自我修正工具 (Strategy Backtest Analyzer)
功能: 每日收盘后评估实时信号的准确性，识别误报/漏报并生成优化建议。
"""
import os
import sys
import json
import logging
import pandas as pd
from datetime import datetime, timedelta

# 增加项目路径
sys.path.append(os.getcwd())

from JSONData import tdx_data_Day as tdd
from intraday_pattern_detector import IntradayPatternDetector
from trading_logger import TradingLogger, NumpyEncoder
from JohnsonUtil import LoggerFactory, commonTips as cct

logger = LoggerFactory.getLogger()

class StrategyBacktestAnalyzer:
    def __init__(self, db_path: str = "./trading_signals.db"):
        self.db_path = db_path
        self.trader_log = TradingLogger(db_path)
        self.detector = IntradayPatternDetector(cooldown=0)
        self.correction_log_path = "./strategy_self_correction.log"

    def run_daily_analysis(self, target_date: str = None):
        """
        执行每日复盘分析
        target_date: 格式 'YYYY-MM-DD'，默认为今天
        """
        if target_date is None:
            target_date = datetime.now().strftime('%Y-%m-%d')
            
        logger.info(f"Starting Strategy Analysis for {target_date}...")
        
        # 1. 获取当日所有实时信号
        signals_df = self.trader_log.get_live_signal_history_df(date=target_date)
        if signals_df.empty:
            logger.info(f"No signals found for {target_date}. Skipping.")
            return

        # 2. 按代码聚合信号，获取需要复盘的股票清单
        codes = signals_df['code'].unique().tolist()
        logger.info(f"Analyzing {len(codes)} stocks with signals...")

        results = []
        for code in codes:
            try:
                stock_signals = signals_df[signals_df['code'] == code]
                name = stock_signals['name'].iloc[0]
                
                # 获取该股的全天真实行情 (tdd)
                # dl=5 确保有足够数据计算前两日高点等指标
                df_daily = tdd.get_tdx_append_now_df_api(code, dl=5)
                if df_daily is None or df_daily.empty:
                    continue
                
                # 显式排序索引（日期），防止不同股票返回顺序不一致（如 603056 返回降序）
                df_daily = df_daily.sort_index(ascending=True)

                # [FIX] tdd 返回的数据通常是按日期升序排列，最新的在最后一行 (iloc[-1])
                # 兼容性处理：提取最新日期并转换为字符串比较
                df_daily.index = df_daily.index.astype(str)
                day_row = df_daily.iloc[-1]
                yest_row = df_daily.iloc[-2] if len(df_daily) > 1 else day_row
                
                last_date_str = str(day_row.name).split(' ')[0] # 适配可能存在的 HH:MM:SS
                if last_date_str != target_date:
                    # 如果数据还未更新到目标日期，记录并跳过
                    logger.warning(f"Data for {code} on {target_date} not ready yet (Last in DF: {last_date_str})")
                    continue
                
                # 执行复盘评估
                analysis = self._analyze_stock_performance(code, name, stock_signals, day_row, yest_row)
                if analysis:
                    results.append(analysis)
                    
            except Exception as e:
                logger.error(f"Error analyzing {code}: {e}")

        # 3. 生成总结日志与建议
        self._generate_correction_report(target_date, results)

    def _analyze_stock_performance(self, code: str, name: str, signals, day_row, yest_row):
        """
        评估单只股票的信号表现
        """
        # 全天关键价位
        high_p = float(day_row['high'])
        low_p = float(day_row['low'])
        close_p = float(day_row['close'])
        open_p = float(day_row['open'])
        prev_close = float(yest_row['close'])
        
        analysis_data = {
            'code': code,
            'name': name,
            'signals': [],
            'outcome': 'NEUTRAL',
            'suggested_fix': None
        }

        for _, sig in signals.iterrows():
            pattern = sig['action']
            trigger_price = sig['price']
            
            # --- 核心逻辑验证 ---
            
            # 1. 验证 诱多跑路 (bull_trap_exit)
            if pattern == 'bull_trap_exit':
                # 如果收盘收高（涨幅 > 1%）且收在触发价之上，说明是误报（假摔）
                if close_p > trigger_price and close_p > prev_close * 1.01:
                    status = "FALSE_ALARM (Strong Recovery)"
                    # 检查是否符合“底部分数抬高”
                    lastl1d = float(yest_row['low'])
                    if low_p >= lastl1d * 0.998:
                        suggested_fix = "上升趋势+低点抬高时，应进一步调高破位阈值或抑制信号"
                    else:
                        suggested_fix = "考虑结合大盘情绪过滤此类深 V 反转"
                else:
                    status = "SUCCESS (Correct Exit)"
                    suggested_fix = None
                
            # 2. 验证 诱空反转 (bear_trap_reversal)
            elif pattern == 'bear_trap_reversal':
                # 如果收盘确实能稳在日内高位（回落 < 0.5%），则是成功的反转
                if close_p >= high_p * 0.995:
                    status = "SUCCESS (Strong Reversal)"
                    suggested_fix = None
                else:
                    status = "WEAK (Faded after breakout)"
                    suggested_fix = "可能需要二次突破确认，或成交量配合不足"
            
            else:
                status = "LOGGED"
                suggested_fix = None

            analysis_data['signals'].append({
                'time': sig['timestamp'],
                'pattern': pattern,
                'price': trigger_price,
                'status': status,
                'suggestion': suggested_fix
            })

        return analysis_data

    def _generate_correction_report(self, date_str, results):
        """生成并追加自我修正日志"""
        report_lines = [f"\n{'='*50}", f"Strategy Self-Correction Report: {date_str}", f"{'='*50}"]
        
        total_signals = 0
        success_signals = 0
        false_alarms = []

        for res in results:
            for sig in res['signals']:
                total_signals += 1
                line = f"[{sig['time']}] {res['code']}({res['name']}) -> {sig['pattern']} @ {sig['price']} | Status: {sig['status']}"
                report_lines.append(line)
                
                if "SUCCESS" in sig['status']:
                    success_signals += 1
                elif "FALSE_ALARM" in sig['status']:
                    false_alarms.append(f"{res['code']} {sig['pattern']}: {sig['suggestion']}")

        win_rate = (success_signals / total_signals * 100) if total_signals > 0 else 0
        report_lines.insert(3, f"Summary: Total {total_signals}, Successful {success_signals}, Accuracy {win_rate:.1f}%")

        if false_alarms:
            report_lines.append("\n[Core Recommendations]")
            # 去重建议
            for adj in set(false_alarms):
                report_lines.append(f" - {adj}")

        # 写入文件
        with open(self.correction_log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(report_lines) + "\n")
            
        logger.info(f"Analysis completed. Report saved to {self.correction_log_path}")

if __name__ == "__main__":
    analyzer = StrategyBacktestAnalyzer()
    # 模拟运行
    analyzer.run_daily_analysis()
