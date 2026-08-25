# -*- coding: utf-8 -*-
import sys
import os
import io

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.new_stock_strategy_generator import NewStockStrategyGenerator

engine = IntradayStrategyEngine.get_instance()
fetcher = TDXRealtimeFetcher.get_instance()
gen = NewStockStrategyGenerator.get_instance()

# 1. 边界测试：空值、非法代码、未知标的
print("=== 1. 边界与异常入参测试 ===")
for bad_code in [None, "", "000000", "999999", "INVALID", 123]:
    is_f = engine.is_stock_first_listing_day(bad_code)
    st = engine.auto_select_strategy(0.0, code=bad_code)
    y_o = fetcher.get_yesterday_ohlc(str(bad_code) if bad_code else "")
    assert isinstance(is_f, bool)
    assert isinstance(st, dict)
    assert isinstance(y_o, dict)
print("[PASS] 空值与非法输入测试全部安全通过！")

# 2. 状态切换测试：连续在不同类型的股票间切换
print("=== 2. 标的切换连贯性测试 ===")
codes = ["688835", "600519", "688826", "000001", "688836", "920059"]
for c in codes:
    is_f = engine.is_stock_first_listing_day(c)
    st = engine.auto_select_strategy(200.0, code=c)
    spec = engine.get_stock_ladder_spec(c)
    assert st is not None
    assert "id" in st
    print(f"标的: {c} | 首日: {is_f} | 匹配策略: {st.get('id')} | 发行价: {spec.get('issue_price')}")
print("[PASS] 标的切换连贯性测试全部通过！")

# 3. 动态生成策略热重载测试
print("=== 3. 动态生成策略与规则完整性测试 ===")
test_strat = gen.generate_strategy({"code": "999888", "name": "N测试股", "issue_price": 30.0, "price": 90.0})
assert len(test_strat["phases"]) == 6
assert len(test_strat["phases"][1]["rules"]) == 2
print("[PASS] 策略自动生成器与 rules 完整性测试通过！")
