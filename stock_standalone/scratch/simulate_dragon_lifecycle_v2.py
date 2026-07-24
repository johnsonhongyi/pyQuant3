# -*- coding: utf-8 -*-
"""
Simulate Dragon Stock Full Lifecycle v2

模拟用户提供的 5 张通达信截图中 5 只真实龙头强股从 06-29 买入、主升冲高、到高位/破位离场的完整生命周期跑盘!
"""

import sys
import json
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

# 5 只真实龙头股在 06-29 及后续完整走势数据
dragons_data = {
    "688233 神工股份": [
        {"date": "2026-06-29", "stage": "06-29突破买入日", "price": 194.33, "pct": 20.0, "dff": 4.5, "ma5": 170.0, "ma10": 155.0},
        {"date": "2026-06-30", "stage": "冲高主升狂飙", "price": 220.00, "pct": 13.2, "dff": 3.8, "ma5": 195.0, "ma10": 170.0},
        {"date": "2026-07-02", "stage": "247.00天花板触顶", "price": 247.00, "pct": 12.2, "dff": 1.2, "ma5": 220.0, "ma10": 190.0},
        {"date": "2026-07-03", "stage": "破5日线见顶离场", "price": 225.00, "pct": -8.9, "dff": -2.5, "ma5": 230.0, "ma10": 205.0},
        {"date": "2026-07-10", "stage": "后续一路阴跌砸盘", "price": 150.00, "pct": -15.0, "dff": -5.0, "ma5": 180.0, "ma10": 200.0},
    ],
    "688336 三生国健": [
        {"date": "2026-06-29", "stage": "06-29突破买入日", "price": 49.75, "pct": 20.0, "dff": 4.8, "ma5": 43.0, "ma10": 41.0},
        {"date": "2026-07-01", "stage": "冲高主升狂飙", "price": 58.00, "pct": 16.5, "dff": 3.2, "ma5": 52.0, "ma10": 45.0},
        {"date": "2026-07-03", "stage": "64.32天花板触顶", "price": 64.32, "pct": 10.8, "dff": 0.5, "ma5": 59.0, "ma10": 50.0},
        {"date": "2026-07-06", "stage": "破5日线见顶离场", "price": 56.00, "pct": -12.9, "dff": -3.8, "ma5": 59.5, "ma10": 53.0},
        {"date": "2026-07-15", "stage": "后续阴跌跌回起涨点", "price": 42.70, "pct": -8.0, "dff": -4.0, "ma5": 48.0, "ma10": 52.0},
    ],
    "301392 汇成真空": [
        {"date": "2026-06-29", "stage": "06-29突破买入日", "price": 261.12, "pct": 12.5, "dff": 3.9, "ma5": 230.0, "ma10": 215.0},
        {"date": "2026-07-01", "stage": "295.00天花板触顶", "price": 295.00, "pct": 12.9, "dff": 1.5, "ma5": 275.0, "ma10": 240.0},
        {"date": "2026-07-02", "stage": "破5日线见顶离场", "price": 270.00, "pct": -8.4, "dff": -3.2, "ma5": 278.0, "ma10": 250.0},
        {"date": "2026-07-15", "stage": "后续腰斩暴跌杀至159", "price": 159.01, "pct": -12.0, "dff": -6.0, "ma5": 190.0, "ma10": 220.0},
    ],
    "300373 扬杰科技": [
        {"date": "2026-06-29", "stage": "06-29突破买入日", "price": 149.95, "pct": 10.4, "dff": 3.2, "ma5": 140.0, "ma10": 130.0},
        {"date": "2026-07-01", "stage": "162.00天花板触顶", "price": 162.00, "pct": 8.0, "dff": 1.0, "ma5": 154.0, "ma10": 142.0},
        {"date": "2026-07-02", "stage": "破5日线见顶离场", "price": 152.00, "pct": -6.1, "dff": -2.8, "ma5": 155.0, "ma10": 146.0},
        {"date": "2026-07-15", "stage": "阴跌砸盘杀至90.6", "price": 90.60, "pct": -10.0, "dff": -4.5, "ma5": 110.0, "ma10": 130.0},
    ],
    "300436 广生堂": [
        {"date": "2026-06-29", "stage": "06-29突破买入日", "price": 108.00, "pct": 9.5, "dff": 2.8, "ma5": 95.0, "ma10": 90.0},
        {"date": "2026-07-01", "stage": "122.58脉冲触顶", "price": 122.58, "pct": 13.5, "dff": 0.8, "ma5": 112.0, "ma10": 98.0},
        {"date": "2026-07-02", "stage": "破5日线见顶离场", "price": 112.00, "pct": -8.6, "dff": -3.1, "ma5": 115.0, "ma10": 102.0},
        {"date": "2026-07-15", "stage": "阴跌跌回底部86.3", "price": 86.33, "pct": -5.0, "dff": -3.0, "ma5": 92.0, "ma10": 100.0},
    ]
}

print("=================== 5 只龙头强势股全生命周期 (买入/主升奔跑/高位止盈/破位风控) 实操模拟 ===================\n")

for stock_name, timeline in dragons_data.items():
    code, name = stock_name.split()
    print(f"💎 【评估标的: {stock_name}】")
    print("=" * 95)

    position_state = "FLAT"
    entry_price = 0.0
    days_held = 0

    for item in timeline:
        date_str = item["date"]
        stage = item["stage"]
        price = item["price"]
        pct = item["pct"]
        dff = item["dff"]
        ma5 = item["ma5"]
        ma10 = item["ma10"]

        # 上下文构建
        ctx = {
            "priority": 90.0,
            "sector_heat": 85.0,
            "pct_diff": pct,
            "dff": dff,
            "is_leader": True,
            "breakout": True if "突破" in stage else False,
            "vol_ratio": 2.0 if "突破" in stage else (1.5 if pct > 0 else 0.8),
            "price": price,
            "open": price * 0.92 if pct > 0 else price * 1.02,
            "high": price * 1.01 if pct > 0 else price * 1.02,
            "low": price * 0.98,
            "ma5d": ma5,
            "ma5d_prev5": ma5 * 0.95,
            "ma10d": ma10,
            "ma20d": ma10 * 0.92,
            "ma60d": ma10 * 0.85,
            "profit_ratio": 90.0 if pct > 0 else 40.0,
            "ptop": ma5 * 1.05,
            "upper": ma5 * 1.08,
            "dff_positive": dff > 0,
            "price_above_vwap": dff > 0,
            "days_held": days_held,
            "pnl_pct": round(((price - entry_price) / entry_price * 100.0), 2) if entry_price > 0 else 0.0,
            "max_pnl_since_entry": round(((price - entry_price) / entry_price * 100.0), 2) if entry_price > 0 else 0.0,
        }

        # 1. 深度牛股挖掘判定
        is_mined, mining_score, _ = DeepStockMiningEngine.evaluate_stock_mining(ctx)

        # 2. 决策意图判定
        sig = StrategySignal(
            code=code,
            name=name,
            signal_type="BREAKOUT_BUY" if "突破" in stage else "MA5_SUPER_TREND",
            price=price,
            source="SBC",
            ts=f"{date_str} 10:00:00",
            features=ctx
        )

        # 在空仓且符合牛股挖掘时强力买入
        action = "HOLD"
        reason_setup = "MA5_SUPER_TREND"
        
        if position_state == "FLAT":
            if is_mined and pct > 0:
                action = "BUY"
                reason_setup = "MINED_MA5_BREAKOUT_BUY"
        elif position_state == "IN_TRADE":
            intent = decision_engine.decide(sig, state=position_state)
            action = intent.action
            reason_setup = intent.reason.setup

        # 模拟盘面输出
        if position_state == "FLAT" and action == "BUY":
            position_state = "IN_TRADE"
            entry_price = price
            days_held = 1
            log_str = f"🚀 触发牛股买入! (买入价: {entry_price:.2f}, 挖掘分: {mining_score:.1f}, 核心:Top3主线龙头+平台放量突破)"
        elif position_state == "IN_TRADE" and action == "SELL":
            pnl = round(((price - entry_price) / entry_price * 100.0), 2)
            position_state = "FLAT"
            log_str = f"🎯 敏锐触发离场平仓! (平仓价: {price:.2f}, 锁定爆赚收益: +{pnl:.2f}%, 离场原因: {reason_setup})"
        elif position_state == "IN_TRADE":
            days_held += 1
            pnl = round(((price - entry_price) / entry_price * 100.0), 2)
            log_str = f"📈 坚定持仓主升狂飙中... (当前价: {price:.2f}, 实时浮盈: +{pnl:.2f}%)"
        else:
            log_str = f"🛡️ 保持观望，不盲从抄底 (Action=HOLD, 挖掘分: {mining_score:.1f})"

        print(f"  [{date_str}] {stage:<14} | 价格: {price:<7.2f} | 涨跌: {pct:>5.1f}% | 挖掘得分: {mining_score:<4.1f} | {log_str}")

    print()
