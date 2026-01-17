import numpy as np
import pandas as pd

class StrongPullbackMA5Strategy:

    STRATEGY_ID: str = "StrongPullbackMA5"
    REQUIRED_COLUMNS: list[str] = [
        "close", "ma5d", "ma10d", "ma20d", "ma60d",
        "lastp1d", "lastp2d", "lastp3d",
        "lastv1d", "lastv2d"
    ]

    def __init__(self,
                 min_score: float = 80,
                 use_macd: bool = True,
                 use_rsi: bool = True):
        self.min_score: float = min_score
        self.use_macd: bool = use_macd
        self.use_rsi: bool = use_rsi

    def validate_df(self, df: pd.DataFrame) -> tuple[bool, str]:
        """检查 DataFrame 是否包含核心列"""
        if df.empty:
            return False, "DataFrame is empty"
        
        # 核心列必须存在，否则无法进行后续计算
        if "close" not in df.columns:
            return False, "Missing core column: close"
            
        # 记录缺失但可兜底的列（仅用于调试或记录，不阻塞运行）
        # self.REQUIRED_COLUMNS 中定义的其他列如果缺失，score() 会尝试自动计算
        return True, ""

    # ================= Score Core =================
    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = df.copy()

        # 如果缺失指标列，尝试通过 close 计算
        if 'ma5d' not in _df.columns and 'close' in _df.columns:
            _df['ma5d'] = _df['close'].rolling(5).mean()
        if 'ma10d' not in _df.columns and 'close' in _df.columns:
            _df['ma10d'] = _df['close'].rolling(10).mean()
        if 'ma20d' not in _df.columns and 'close' in _df.columns:
            _df['ma20d'] = _df['close'].rolling(20).mean()
        if 'ma60d' not in _df.columns and 'close' in _df.columns:
            _df['ma60d'] = _df['close'].rolling(60).mean()
        
        # 历史数据偏移兜底 (lastp1d, lastv1d 等)
        if 'lastp1d' not in _df.columns and 'close' in _df.columns:
            _df['lastp1d'] = _df['close'].shift(1)
        if 'lastp2d' not in _df.columns and 'close' in _df.columns:
            _df['lastp2d'] = _df['close'].shift(2)
        if 'lastp3d' not in _df.columns and 'close' in _df.columns:
            _df['lastp3d'] = _df['close'].shift(3)
        
        # 成交量偏移兜底
        vol_col = 'volume' if 'volume' in _df.columns else ('vol' if 'vol' in _df.columns else None)
        if vol_col:
            if 'lastv1d' not in _df.columns:
                _df['lastv1d'] = _df[vol_col].shift(1)
            if 'lastv2d' not in _df.columns:
                _df['lastv2d'] = _df[vol_col].shift(2)
        else:
            # 彻底没有成交量列时的极端处理
            if 'lastv1d' not in _df.columns: _df['lastv1d'] = 1.0
            if 'lastv2d' not in _df.columns: _df['lastv2d'] = 1.0

        # MACD 兜底
        if self.use_macd and 'macddif' not in _df.columns and 'close' in _df.columns:
            ema12 = _df['close'].ewm(span=12, adjust=False).mean()
            ema26 = _df['close'].ewm(span=26, adjust=False).mean()
            _df['macddif'] = ema12 - ema26
            _df['macddea'] = _df['macddif'].ewm(span=9, adjust=False).mean()
            _df['macd'] = (_df['macddif'] - _df['macddea']) * 2
        
        # RSI 兜底
        if self.use_rsi and 'rsi' not in _df.columns and 'close' in _df.columns:
            diff = _df['close'].diff()
            gain = (diff.where(diff > 0, 0)).rolling(window=14).mean()
            loss = (-diff.where(diff < 0, 0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, np.nan)
            _df['rsi'] = 100 - (100 / (1 + rs))

        # 补全 suggest_entry 需要的 upper (简单布林带上轨模拟)
        if 'upper' not in _df.columns and 'close' in _df.columns:
            std = _df['close'].rolling(20).std()
            _df['upper'] = _df['ma20d'] + 2 * std
            
        # 确保 ma5d 等即使计算后也不是全空 (例如数据点太少)
        _df = _df.ffill().bfill().fillna(0) # type: ignore

        # ---------- Trend ----------
        _df["trend_score"] = 0
        _df.loc[_df['ma5d'] > _df['ma10d'], "trend_score"] += 10
        _df.loc[_df['ma10d'] > _df['ma20d'], "trend_score"] += 10
        _df.loc[_df['ma20d'] > _df['ma60d'], "trend_score"] += 10
        
        # [新增] MA60 突破加分
        _df.loc[_df['close'] > _df['ma60d'], "trend_score"] += 10
        # [新增] 红柱延续加分 (Red > 5)
        if 'red' in _df.columns:
            _df.loc[_df['red'] >= 5, "trend_score"] += 15
            
        _df.loc[
            (_df['lastp1d'] > _df['lastp2d']) & (_df['lastp2d'] > _df['lastp3d']),
            "trend_score"
        ] += 10

        # [新增] 趋势存续分
        _df.loc[_df['close'] > _df['ma5d'], "trend_score"] += 10
        _df.loc[_df['close'] > _df['ma10d'], "trend_score"] += 10

        # ---------- Pullback (核心：靠近均线) ----------
        _df["pullback_score"] = 0
        pb = (_df['close'] - _df['ma5d']).abs() / _df['ma5d']

        _df.loc[pb <= 0.005, "pullback_score"] += 25
        _df.loc[(pb > 0.005) & (pb <= 0.01), "pullback_score"] += 15
        _df.loc[(pb > 0.01) & (pb <= 0.015), "pullback_score"] += 5

        # ---------- Volume ----------
        _df["volume_score"] = 0
        vr = _df.lastv1d / _df.lastv2d.replace(0, np.nan)

        _df.loc[vr >= 1.0, "volume_score"] += 20
        _df.loc[(vr >= 0.7) & (vr < 1.0), "volume_score"] += 15
        _df.loc[(vr >= 0.5) & (vr < 0.7), "volume_score"] += 10

        # ---------- MACD ----------
        if self.use_macd:
            _df["macd_score"] = 0
            _df.loc[_df['macddif'] > _df['macddea'], "macd_score"] += 10
            _df.loc[_df['macd'] > 0, "macd_score"] += 5
        else:
            _df["macd_score"] = 0

        # ---------- RSI ----------
        if self.use_rsi:
            _df["rsi_score"] = 0
            _df.loc[_df.rsi.between(45, 70), "rsi_score"] += 10
        else:
            _df["rsi_score"] = 0

        # ---------- Total ----------
        _df["strong_score"] = (
            _df.trend_score +
            _df.pullback_score +
            _df.volume_score +
            _df.macd_score +
            _df.rsi_score
        )

        return _df

    # ================= Risk =================
    def classify_risk(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = df.copy()
        _df["risk_level"] = "HIGH"

        _df.loc[_df.strong_score >= 80, "risk_level"] = "LOW"
        _df.loc[
            (_df.strong_score >= 70) & (_df.strong_score < 80),
            "risk_level"
        ] = "MEDIUM"

        return _df

    # ================= Entry =================
    def suggest_entry(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = df.copy()

        _df["entry_low"] = _df['ma5d'] * 0.99
        _df["entry_high"] = _df['ma5d'] * 1.01
        _df["sl"] = _df['ma10d'] * 0.98
        _df["tp"] = _df['upper']

        return _df

    # ================= Main =================
    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = self.score(df)
        
        # 信号触发逻辑：分值达标 且 是第一个达标点（过滤连续买入）
        _df["is_above_threshold"] = _df.strong_score >= self.min_score
        _df["buy_signal"] = _df["is_above_threshold"] & (~_df["is_above_threshold"].shift(1).fillna(False))
        
        # 仅保留买入信号触发的行
        result_df = _df[_df.buy_signal].copy()
        
        if not result_df.empty:
            result_df = self.classify_risk(result_df)
            result_df = self.suggest_entry(result_df)
            result_df["strategy_id"] = self.STRATEGY_ID
            result_df = result_df.sort_values("strong_score", ascending=False)

        return result_df

if __name__ == '__main__':
    strategy = StrongPullbackMA5Strategy(
        min_score=65,
        use_macd=True,
        use_rsi=True
    )

    top_signal = pd.DataFrame({
        'close': [10.5, 10.6, 10.7, 10.8, 10.9],
        'ma5d': [10.4, 10.5, 10.6, 10.7, 10.8],
        'ma10d': [10.3, 10.4, 10.5, 10.6, 10.7],
        'ma20d': [10.0, 10.1, 10.2, 10.3, 10.4],
        'ma60d': [9.0, 9.1, 9.2, 9.3, 9.4],
        'lastp1d': [10.4, 10.5, 10.6, 10.7, 10.8],
        'lastp2d': [10.3, 10.4, 10.5, 10.6, 10.7],
        'lastp3d': [10.2, 10.3, 10.4, 10.5, 10.6],
        'lastv1d': [1000, 1100, 1200, 1300, 1400],
        'lastv2d': [900, 1000, 1100, 1200, 1300],
        'upper': [11.0, 11.1, 11.2, 11.3, 11.4],
        'name': ['Test'] * 5
    })
    
    df_signal = strategy.run(top_signal)

    if not df_signal.empty:
        print(df_signal[
            ["name", "close", "strong_score",
             "trend_score", "pullback_score",
             "volume_score", "risk_level"]
        ].head(15))


# 如何接入你现有系统（非常顺）
# 1️⃣ trade_signal
# df_signal["trade_signal"] = 1

# 2️⃣ EVAL_STATE
# df_signal["EVAL_STATE"] = df_signal["strategy_id"]

# 3️⃣ 实盘告警（示例）
# alert_df = df_signal[df_signal.risk_level == "LOW"]

# 五、你现在这套的级别

# ✔ 可解释
# ✔ 可调参
# ✔ 可回测
# ✔ 可实盘
# ✔ 可扩展

# 已经不是“筛选脚本”，而是策略模块

# 下一步我可以直接帮你做（任选）

# 历史回测（胜率 / 最大回撤 / 收益曲线）

# 多策略并行评分 + 冲突解决

# 盘中 Tick 触发版（分钟级）

# 策略注册器（StrategyRegistry）