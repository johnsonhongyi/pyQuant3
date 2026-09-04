# -*- coding: utf-8 -*-
"""
scratch/run_600108_backtest.py — 针对 600108 (亚盛集团) 执行多周期通道支撑线上量化策略回测
"""

import os
import sys

# 设定编码与路径
sys.stdout.reconfigure(encoding='utf-8')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from JSONData import tdx_data_Day as tdd
from ats.multi_period_channel_backtester import MultiPeriodChannelBacktester


def main():
    code = "600108"
    print(f"================================================================")
    print(f"🚀 开始执行【多周期通道支撑线上量化策略】实战回测: [{code}] 亚盛集团")
    print(f"   周期涵盖: d (日线), 2d (2日线), 3d (3日线), w (周线), m (月线)")
    print(f"================================================================")

    # 读取通达信长周期日 K 线数据
    df = tdd.get_tdx_append_now_df_api(code, dl=250)
    if df is None or df.empty:
        df = tdd.get_tdx_Exp_day_to_df(code)

    if df is None or df.empty:
        print("❌ 未能读取到股票日线数据")
        return

    print(f"✅ 成功加载 [{code}] 历史日线数据: 共 {len(df)} 个交易日 ({df.index[0]} ~ {df.index[-1]})")

    # 初始化回测执行器
    backtester = MultiPeriodChannelBacktester(
        initial_capital=100000.0,
        position_pct=1.0,
        commission_rate=0.0003,
        tax_rate=0.0005,
        slippage=0.001,
        stop_loss_pct=0.04,
        trailing_stop_activation=0.08,
        trailing_stop_drawdown=0.035,
        max_holding_days=20,
        warmup_bars=35,
        min_signal_score=80.0
    )

    # 运行逐日时序切片回测 (防未来函数)
    report = backtester.run_backtest_on_df(df, code=code, name="亚盛集团")

    # 生成 Markdown 回测报告
    md_content = backtester.format_report_markdown(report)
    print("\n" + md_content)

    # 将报告写入文件
    out_path = os.path.join(PROJECT_ROOT, "multi_period_channel_backtest_report_600108.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"\n💾 回测报告已成功落盘保存至: {out_path}")


if __name__ == "__main__":
    main()
