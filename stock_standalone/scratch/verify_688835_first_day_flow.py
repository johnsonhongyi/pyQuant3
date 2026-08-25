# -*- coding: utf-8 -*-
import sys
import os
import io

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher

engine = IntradayStrategyEngine.get_instance()
engine.load_config()

code = "688835"
is_first = engine.is_stock_first_listing_day(code)
print(f"1. 【首日判定】标的 {code} 上市首日判定结果: {is_first}")

strat = engine.auto_select_strategy(open_price=209.0, code=code)
print(f"2. 【策略匹配】标的 {code} 匹配到的策略: ID={strat.get('id')} | 名称={strat.get('name')}")

spec = engine.get_stock_ladder_spec(code)
issue_p = float(spec.get("issue_price", 61.36))
open_price = 209.0
gain_pct = ((open_price - issue_p) / issue_p * 100.0)
print(f"3. 【开盘基准】发行价={issue_p:.2f}元 | 今开={open_price:.2f}元 | 首日高开溢价率={gain_pct:+.2f}%")

print("4. 【策略阶段与规则列表】:")
for p in strat.get("phases", []):
    print(f"   阶段 {p.get('phase_id')}: {p.get('name')} (规则数={len(p.get('rules', []))})")
    for r in p.get("rules", []):
        print(f"      - {r.get('name')}: 条件={r.get('trigger_expr')} | 卖出比例={r.get('sell_ratio', 0)*100:.0f}%")
