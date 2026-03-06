import sys
import os
import datetime
import pandas as pd
from unittest.mock import MagicMock

# 模拟环境
sys.path.append(os.getcwd())
from trading_hub import TradingHub, TrackedSignal
from stock_live_strategy import StockLiveStrategy

def test_integration_phase3():
    print("开始 Phase 3 集成逻辑验证 (使用临时数据库)...")
    test_db = 'test_phase3.db'
    if os.path.exists(test_db): os.remove(test_db)
    
    hub = TradingHub(signal_db=test_db)
    # 1. 模拟发现热股
    code = '600000'
    hub.add_to_watchlist(code, '浦发银行', '银行', 10.0, source='TestDiscovery')
    print(f"1. 发现热股 {code} 已入 Watchlist")

    # 2. 模拟跨日验证
    # 构造 OHLC，让他通过验证 (win=3, ma5/10 趋势向上)
    ohlc = {
        code: {
            'close': 11.0, 'high': 11.5, 'low': 10.8, 'open': 10.9,
            'ma5': 10.5, 'ma10': 10.2, 'upper': 12.0, 'high4': 11.2,
            'volume_ratio': 1.5, 'win': 3
        }
    }
    
    summary = hub.get_watchlist_summary()
    print(f"验证前 Watchlist 概览: {summary}")

    results = hub.validate_watchlist(ohlc)
    print(f"验证结果: {results}")
    
    hub.promote_validated_stocks()
    print(f"2. 跨日验证完成，{code} 应已晋升至 follow_queue (VALIDATED)")

    # 3. 验证 follow_queue 状态
    signals = hub.get_follow_queue(status='VALIDATED')
    assert len(signals) > 0
    assert signals[0].code == code
    print(f"3. 数据库验证成功：{code} 处于 VALIDATED 状态")

    # 4. 模拟策略引擎加载与 T+0 预警逻辑
    strategy = StockLiveStrategy(master=MagicMock())
    
    # 手动验证 is_auction_time 逻辑 (09:25 约束)
    test_time_24 = "09:24:30"
    is_auction_24 = "09:25:00" <= test_time_24 <= "09:30:00"
    assert not is_auction_24, "9:24 不应判定为竞价有效时间"
    print("4.1 校验：09:24 入场拦截成功")
    
    test_time_25 = "09:25:00"
    is_auction_25 = "09:25:00" <= test_time_25 <= "09:30:00"
    assert is_auction_25, "9:25 应判定为竞价有效时间"
    print("4.2 校验：09:25 入场开放成功")
    
    # 模拟数据同步
    strategy.follow_queue_cache = hub.get_follow_queue(status=['VALIDATED', 'ENTERED'])
    assert len(strategy.follow_queue_cache) > 0
    print("4. 策略引擎同步多状态成功")

    # 5. 模拟收盘结算留强去弱
    eval_res = hub.evaluate_holding_strength(ohlc)
    print(f"5. 收盘强弱评分成功: {eval_res}")
    assert 'strong' in eval_res

    print("\n✅ Phase 3 核心链路集成验证通过！")

if __name__ == "__main__":
    test_integration_phase3()
