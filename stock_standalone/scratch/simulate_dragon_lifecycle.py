# -*- coding: utf-8 -*-
"""
Simulate Dragon Stock Full Lifecycle (神工股份/三生国健/汇成真空/扬杰科技/广生堂)

模拟这 5 只龙头强势股从 06-29 突破买入日，到后续冲高见顶，再到跌破离场的完整生命周期!
验证现在的决策系统能否:
1. 在 06-29 准确挖掘并买入
2. 在冲高顶部或跌破5日线时敏锐平仓离场，锁定收益，避开后续暴跌
"""

import sys
import json
import sqlite3
import pandas as pd
from pathlib import Path

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from trading_kernel.engine.deep_stock_mining_engine import DeepStockMiningEngine
from trading_kernel.engine import decision_engine
from trading_kernel.core.signal import StrategySignal

# 构建这 5 只龙头股在 06-29 买入日及后续见顶/破位日的真实走势轨迹
stocks_lifecycle = {
    "688233 (神工股份)": [
        # (日期, 阶段, 价格, pct_diff, dff, ma5, ma10, vol_ratio, is_breakout, remark)
        ("2026-06-29", "06-29启动日", 194.33, 20.0, 4.5, 170.0, 160.0, 2.2, True, "大阳线涨停突破箱体"),
        ("2026-06-30", "冲高主升期", 220.00, 13.2, 3.8, 195.0, 175.0, 1.8, True, "顺势主升飙升"),
        ("2026-07-02", "247.0触顶日", 247.00, 12.2, 1.2, 220.0, 190.0, 2.5, True, "触及历史高点247天花板"),
        ("2026-07-03", "破5日线见顶", 225.00, -8.9, -2.5, 230.0, 205.0, 2.0, False, "高位跌破5日线大长阴"),
        ("2026-07-10", "暴跌下跌区", 150.00, -15.0, -5.0, 180.0, 200.0, 1.5, False, "一路阴跌砸盘至150"),
    ],
    "688336 (三生国健)": [
        ("2026-06-29", "06-29启动日", 49.75, 20.0, 4.8, 43.0, 41.0, 2.2, True, "20%涨停放量突破"),
        ("2026-07-01", "冲高主升期", 58.00, 16.5, 3.2, 52.0, 45.0, 1.6, True, "主升浪狂飙"),
        ("2026-07-03", "64.32触顶日", 64.32, 10.8, 0.5, 59.0, 50.0, 2.4, True, "冲高见顶64.32"),
        ("2026-07-06", "破位离场日", 56.00, -12.9, -3.8, 59.5, 53.0, 1.9, False, "阴线放量跌破5日线"),
        ("2026-07-15", "暴跌回到原点", 42.70, -8.0, -4.0, 48.0, 52.0, 1.0, False, "暴跌砸穿起涨点至42.7"),
    ],
    "301392 (汇成真空)": [
        ("2026-06-29", "06-29启动日", 261.12, 12.5, 3.9, 230.0, 215.0, 1.9, True, "放量大阳大放量突破"),
        ("2026-07-01", "295.0触顶日", 295.00, 12.9, 1.5, 275.0, 240.0, 2.1, True, "高位冲击295见顶"),
        ("2026-07-02", "破位离场日", 270.00, -8.4, -3.2, 278.0, 250.0, 1.8, False, "高位天花板反转杀跌"),
        ("2026-07-15", "崩盘下跌区", 159.01, -12.0, -6.0, 190.0, 220.0, 1.2, False, "断崖杀跌至159.01"),
    ],
    "300373 (扬杰科技)": [
        ("2026-06-29", "06-29启动日", 149.95, 10.4, 3.2, 140.0, 130.0, 1.5, True, "突破箱体天花板"),
        ("2026-07-01", "162.0触顶日", 162.00, 8.0, 1.0, 154.0, 142.0, 1.3, True, "冲高至162见顶"),
        ("2026-07-02", "破位离场日", 152.00, -6.1, -2.8, 155.0, 146.0, 1.5, False, "冲高回落跌破5日线"),
        ("2026-07-15", "阴跌砸盘区", 90.60, -10.0, -4.5, 110.0, 130.0, 1.0, False, "阴跌一路砸到90.60"),
    ],
    "300436 (广生堂)": [
        ("2026-06-29", "06-29启动日", 108.00, 9.5, 2.8, 95.0, 90.0, 1.4, True, "底部大阳放量拉升"),
        ("2026-07-01", "122.5触顶日", 122.58, 13.5, 0.8, 112.0, 98.0, 1.6, True, "脉冲冲高至122.58"),
        ("2026-07-02", "破位离场日", 112.00, -8.6, -3.1, 115.0, 102.0, 1.7, False, "脉冲结束急速下杀"),
        ("2026-07-15", "阴跌回到原点", 86.33, -5.0, -3.0, 92.0, 100.0, 1.0, False, "阴跌回到底部86.33"),
    ]
}

print("=================== 龙头强势股全生命周期 (买入/主升/见顶平仓) 模拟评估 ===================")

for name, lifecycle in stocks_lifecycle.items():
    print(f"\n📌 评估标的: {name}")
    print("-" * 85)

    current_state = "FLAT" # 初始空仓
    days_held = 0
    entry_price = 0.0

    for date_str, stage, price, pct_diff, dff, ma5, ma10, vol_ratio, is_breakout, remark in lifecycle:
        ctx = {
            "priority": 90.0,
            "sector_heat": 85.0,
            "pct_diff": pct_diff,
            "dff": dff,
            "is_leader": True,
            "breakout": is_breakout,
            "vol_ratio": vol_ratio,
            "price": price,
            "open": price * 0.92 if pct_diff > 0 else price * 1.02, # 真实突破强阳线开盘价
            "high": price * 1.01 if pct_diff > 0 else price * 1.02,
            "low": price * 0.98,
            "ma5d": ma5,
            "ma5d_prev5": ma5 * 0.95, # 5日线陡升
            "ma10d": ma10,
            "ma20d": ma10 * 0.95,
            "ma60d": ma10 * 0.90,
            "profit_ratio": 90.0 if is_breakout else 40.0,
            "ptop": ma5 * 1.05 if not is_breakout else price * 0.98,
            "upper": ma5 * 1.08,
            "dff_positive": dff > 0,
            "price_above_vwap": dff > 0,
            "days_held": days_held,
            "pnl_pct": round(((price - entry_price) / entry_price * 100.0), 2) if entry_price > 0 else 0.0,
            "max_pnl_since_entry": round(((price - entry_price) / entry_price * 100.0), 2) if entry_price > 0 else 0.0,
            "high_price": price * 1.03 if pct_diff > 0 else price * 1.01,
            "low_price": price * 0.97 if pct_diff < 0 else price * 0.99,
        }

        # 1. 牛股挖掘得分
        is_mined, mining_score, _ = DeepStockMiningEngine.evaluate_stock_mining(ctx)

        # 2. 决策引擎判断
        features = ctx.copy()
        features["setup"] = "MA5_SUPER_TREND" if current_state == "IN_TRADE" else "MA5_SUPER_TREND"
        sig = StrategySignal(
            code=name.split()[0],
            name=name.split()[1].strip("()"),
            signal_type="PULLBACK_BUY" if not is_breakout else "BREAKOUT_BUY",
            price=price,
            source="SBC",
            ts=f"{date_str} 10:00:00",
            features=features
        )

        intent = decision_engine.decide(sig, state=current_state)
        action = intent.action
        setup_result = intent.reason.setup
        routed_branch = getattr(intent.reason, "routed_branch", "Unknown")

        # 状态流转模拟
        status_str = ""
        if current_state == "FLAT":
            if action in {"BUY", "ADD"}:
                current_state = "IN_TRADE"
                entry_price = price
                days_held = 1
                status_str = f"🚀 触发买入! (买入价: {entry_price:.2f}, 挖掘分: {mining_score:.1f})"
            else:
                status_str = f"👀 观望 (Action={action})"
        elif current_state == "IN_TRADE":
            days_held += 1
            pnl = ctx["pnl_pct"]
            if action == "SELL":
                current_state = "FLAT"
                status_str = f"🎯 触发止盈/平仓离场! (平仓价: {price:.2f}, 最终收益: +{pnl:.2f}%, Setup={setup_result})"
            else:
                status_str = f"📈 坚定持仓奔跑中... (当前价: {price:.2f}, 浮盈: +{pnl:.2f}%)"

        print(f"  [{date_str}] 阶段: {stage:<12} | 价格: {price:<7.2f} | 涨幅: {pct_diff:>5.1f}% | Branch: {routed_branch:<20} | 挖掘分: {mining_score:<4.1f} | {status_str}")
