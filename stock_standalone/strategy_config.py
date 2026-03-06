"""
策略配置字段对照表 (Strategy Data Mapping Configuration)
用户可以直接编辑此文件来调整策略中使用的列名对照关系。
"""

# 基础数据对照映射
COLUMN_MAPPING = {
    # 1. 日线指标 (TDD / Daily Indicators)
    'DAILY': {
        'ma5d': 'ma5',          # 5日均线映射源
        'ma20d': 'ma20',        # 20日均线映射源
        'ma60d': 'ma60',        # 60日均线映射源
        'lasth1d': 'last_high',  # 昨日最高价
        'lasth2d': 'high2',      # 前日最高价 (high.shift(2))
        'lastp1d': 'last_close', # 昨日收盘价
        'lastp2d': 'close2',     # 前日收盘价 (close.shift(2))
        'last_low': 'last_low',  # 昨日最低价
    },
    
    # 2. 实时分时字段 (Intraday Real-time)
    'REALTIME': {
        'trade': 'trade',        # 当前成交价
        'avg_price': 'avg_price', # 盘中均价 (VWAP)
        'amount': 'amount',      # 当日累计成交额
        'volume': 'volume',      # 当日累计成交量比 (修订后的量比)
        'vol': 'vol',            # 当日累计成交量 (原始成交量)
        'percent': 'percent',    # 当日涨跌幅
    }
}

# 结构判定阈值逻辑 (判定标准)
STRUCTURAL_THRESHOLD = {
    'SBC_RISING': {
        'price_rising': True,    # 要求 lastp1d > lastp2d
        'high_rising': True,     # 要求 lasth1d > lasth2d
        'vwap_support': 1.002,   # 站稳均价线比例 (1.002 = 0.2%)
    }
}
