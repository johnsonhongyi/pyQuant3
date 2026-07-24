# -*- coding: utf-8 -*-
"""
Verification Script for Deep Stock Mining Engine & Decision Refactor

验证牛股深度挖掘引擎、诱多一票否决与策略自进化闭环的效果
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

BASE_DIR = Path(r"D:\JohnsonProgram\instockMonitorTK")
TRACE_FILE = BASE_DIR / "logs" / "trading_kernel_trace.jsonl"

from trading_kernel.engine.deep_stock_mining_engine import DeepStockMiningEngine
from trading_kernel.engine.strategy_self_evolution import StrategySelfEvolution
from trading_kernel.core.signal import StrategySignal
from trading_kernel.engine import decision_engine

print("=================== 1. TEST DeepStockMiningEngine DIRECTLY ===================")
sample_ctx_good = {
    "price": 25.5,
    "ma20d": 24.2,
    "ma60d": 23.0,
    "profit_ratio": 88.5,
    "sector_heat": 85.0,
    "is_leader": True,
    "priority": 90.0,
    "sector_rank": 1,
    "ptop": 25.0,
    "breakout": True,
    "vol_ratio": 1.6,
    "dff": 4.5,
    "dff_positive": True,
    "pct_diff": 3.8,
    "price_above_vwap": True
}
is_mined, score, details = DeepStockMiningEngine.evaluate_stock_mining(sample_ctx_good)
print(f"Good Bull Stock Sample -> Mined: {is_mined}, Score: {score}")

sample_ctx_bad = {
    "price": 10.2,
    "ma20d": 11.5,
    "ma60d": 12.8,
    "profit_ratio": 15.0,
    "sector_heat": 15.0,
    "is_leader": False,
    "priority": 40.0,
    "ptop": 14.0,
    "breakout": False,
    "vol_ratio": 0.8,
    "dff": -1.2,
    "dff_positive": False,
    "pct_diff": -2.5,
    "price_above_vwap": False
}
is_mined_bad, score_bad, details_bad = DeepStockMiningEngine.evaluate_stock_mining(sample_ctx_bad)
print(f"Oversold Weak Stock Sample -> Mined: {is_mined_bad}, Score: {score_bad}")

print("\n=================== 2. TEST StrategySelfEvolution DIRECTLY ===================")
evolution = StrategySelfEvolution()
stats = evolution.evaluate_strategy_win_rates()
print("Strategy Win-Rate Summary:", stats)

print("\n=================== 3. REPLAY HISTORICAL TRACES WITH NEW DECISION ENGINE ===================")
if TRACE_FILE.exists():
    traces = []
    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    traces.append(json.loads(line))
                except Exception:
                    pass

    df_t = pd.DataFrame(traces)
    buys = [t for t in traces if isinstance(t.get('intent'), dict) and t.get('intent').get('action') == 'BUY']
    print(f"Replaying {len(buys)} BUY signals from trading_kernel_trace.jsonl...")

    actions_new = []
    setups_new = []
    reasons_new = []

    for item in buys:
        intent = item.get('intent', {})
        reason = intent.get('reason', {})
        code = intent.get('code', '600000')
        ts = item.get('timestamp', '2026-07-24 10:00:00')
        confidence = intent.get('confidence', 0.6)
        
        features = {
            "action": "BUY",
            "priority": reason.get("priority", 50.0) if isinstance(reason, dict) else 50.0,
            "sector_heat": reason.get("sector_heat", 50.0) if isinstance(reason, dict) else 50.0,
            "pct_diff": reason.get("pct_diff", 0.0) if isinstance(reason, dict) else 0.0,
            "dff": reason.get("dff", 0.0) if isinstance(reason, dict) else 0.0,
            "is_leader": reason.get("is_leader", False) if isinstance(reason, dict) else False,
            "setup": reason.get("setup", "SWS_COLLECT_PULLBACK") if isinstance(reason, dict) else "SWS_COLLECT_PULLBACK",
            "volume_ratio": reason.get("volume_ratio", 1.0) if isinstance(reason, dict) else 1.0,
            "ma20d": 20.0,
            "ma20d_prev5": 20.2, # 模拟微幅下倾
            "price": 19.5, # 模拟价格在MA20下方(超跌/弱反弹)
        }

        sig = StrategySignal(
            code=code,
            name="测试个股",
            signal_type="PULLBACK_BUY",
            price=features["price"],
            source="SBC",
            ts=ts,
            features=features
        )

        res_intent = decision_engine.decide(sig, state="FLAT")
        actions_new.append(res_intent.action)
        setups_new.append(res_intent.reason.setup)

    df_res = pd.DataFrame({"action": actions_new, "setup": setups_new})
    print("\nNew Decision Engine Output Summary:")
    print(df_res['action'].value_counts())
    print("\nNew Setup Distribution:")
    print(df_res['setup'].value_counts())

    hold_count = (df_res['action'] == 'HOLD').sum()
    print(f"\nFiltered out / Converted to HOLD: {hold_count} / {len(buys)} ({hold_count/len(buys)*100:.1f}%)")
