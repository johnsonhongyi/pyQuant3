# -*- coding: utf-8 -*-
"""
scratch/verify_sbc_render_600108.py — 离线渲染 600108 多周期回测在 SBC 走势图上的买卖标记与点击收益图元
"""

import os
import sys
import pandas as pd
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPainter, QImage

_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_CUR_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ats.multi_period_channel_backtester import MultiPeriodChannelBacktester
from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    app = QApplication.instance() or QApplication([])

    target_code = "600108"
    bt = MultiPeriodChannelBacktester()
    print("⏳ 正在运行 600108 回测...")
    report = bt.run_backtest_by_code(target_code, dl=250, name="亚盛集团")
    trades_df = report.get("trades_df")
    print(f"✅ 回测完成，共 {len(trades_df)} 笔交易，总收益: {report.get('total_return_pct', 0.0):+.2f}%")

    dlg = SBCIntradayChartDialog(code=target_code)
    dlg.resize(1100, 680)

    # 注入回测交易数据
    dlg.set_custom_backtest_trades(trades_df, df_kline=report.get("df_kline"))

    # 1. 选中第 10 笔主升浪起爆交易 (trade_id=9: 2026-03-02~2026-03-05, +14.65%)
    dlg.canvas.selected_trade_id = 9
    dlg.canvas.update()

    out_dir = r"C:\Users\Johnson\.gemini\antigravity\brain\5ed72bed-8c1e-4ca6-8fbf-71a2230413fd"
    os.makedirs(out_dir, exist_ok=True)
    out_path_1 = os.path.join(out_dir, "sbc_backtest_trade_10.png")

    img1 = QImage(dlg.size(), QImage.Format.Format_ARGB32)
    dlg.render(img1)
    img1.save(out_path_1)
    print(f"📸 已渲染交易 #10 (+14.65%) 收益图: {out_path_1}")

    # 2. 轮巡切换到第 12 笔主升浪顶峰交易 (trade_id=11: 2026-03-10~2026-03-13, +19.92%)
    dlg.canvas.selected_trade_id = 11
    dlg.canvas.update()
    out_path_2 = os.path.join(out_dir, "sbc_backtest_trade_12.png")

    img2 = QImage(dlg.size(), QImage.Format.Format_ARGB32)
    dlg.render(img2)
    img2.save(out_path_2)
    print(f"📸 已渲染交易 #12 (+19.92%) 收益图: {out_path_2}")

    dlg.close()
    print("🎉 渲染验证完成！")


if __name__ == "__main__":
    main()
