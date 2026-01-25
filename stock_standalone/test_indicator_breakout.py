# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
import time
import logging
from stock_live_strategy import StockLiveStrategy
from JohnsonUtil import LoggerFactory

# 配置日志
logger = LoggerFactory.getLogger()
logger.setLevel(logging.INFO)

def simulate_breakout_star():
    print("===== 开始仿真：起跳新星报警测试 =====")
    
    # 1. 构造模拟数据 (DataFrame)
    # 模拟一个已经存在的 monitored_stocks 环境
    code = '000001'
    name = '平安银行'
    
    # 手动构造一个符合条件的 Row
    # win_upper1 从 0 变为 1
    # volume > 1.2
    # gem_score > 15
    data_row = {
        'code': code,
        'name': name,
        'trade': 10.5,
        'nclose': 10.45,
        'percent': 2.5,
        'volume': 1.5,      # 满足量能配合
        'ratio': 3.0,
        'gem_score': 18.0,  # 满足形态基因
        'upper1': 10.4,
        'win_upper1': 1,    # 当前为 1 (站稳)
        'win_upper2': 0,
        'ma5d': 10.3,
        'ma10d': 10.2,
        'high': 10.6,
        'open': 10.1,
    }
    df = pd.DataFrame([data_row]).set_index('code')
    
    # 2. 初始化策略引擎
    class MockMaster:
        def __init__(self):
            self.df_all = df
            self.voice_var = type('obj', (object,), {'get': lambda self: False})()
            self.realtime_service = None
        def after(self, ms, func, *args):
            pass # 仿真中不需要延迟调用

    strategy = StockLiveStrategy(
        MockMaster(),
        alert_cooldown=0,  # 关闭冷却，方便立即看到结果
        voice_enabled=False # 测试环境不播语音，只看日志
    )
    
    # 3. 模拟监控列表
    strategy._monitored_stocks[f'{code}_d'] = {
        'code': code,
        'name': name,
        'resample': 'd',
        'snapshot': {},
        'prev_win_upper1': 0  # 核心：上一次记录为 0
    }
    
    print(f"模拟股票: {code} {name}")
    print(f"预期行为: 触发 [起跳新星] 报警，因为 prev_win_upper1=0 且 curr_win_upper1=1")
    
    # 4. 执行检查
    strategy._check_strategies(df, resample='d')
    
    print("\n===== 再次执行 (应进入冷却或因状态未变不报警) =====")
    # 更新 snapshot 后再次检查，不应再次触发“起跳新星”
    strategy._check_strategies(df, resample='d')

if __name__ == "__main__":
    simulate_breakout_star()
