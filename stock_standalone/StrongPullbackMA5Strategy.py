import numpy as np
import pandas as pd

class StrongPullbackMA5Strategy:

    STRATEGY_ID = "STRONG_PULLBACK_MA5"

    def __init__(self,
                 min_score=60,
                 use_macd=True,
                 use_rsi=True):
        self.min_score = min_score
        self.use_macd = use_macd
        self.use_rsi = use_rsi

    # ================= Score Core =================
    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = df.copy()

        # ---------- Trend ----------
        _df["trend_score"] = 0
        _df.loc[_df.ma5d > _df.ma10d, "trend_score"] += 10
        _df.loc[_df.ma10d > _df.ma20d, "trend_score"] += 10
        _df.loc[_df.ma20d > _df.ma60d, "trend_score"] += 10
        
        # [新增] MA60 突破加分
        _df.loc[_df.close > _df.ma60d, "trend_score"] += 10
        # [新增] 红柱延续加分 (Red > 5)
        if 'red' in _df.columns:
            _df.loc[_df.red >= 5, "trend_score"] += 15
            
        _df.loc[
            (_df.lastp1d > _df.lastp2d) & (_df.lastp2d > _df.lastp3d),
            "trend_score"
        ] += 10

        # ---------- Pullback ----------
        _df["pullback_score"] = 0
        pb = (_df.close - _df.ma5d).abs() / _df.ma5d

        _df.loc[pb <= 0.005, "pullback_score"] += 20
        _df.loc[(pb > 0.005) & (pb <= 0.01), "pullback_score"] += 15
        _df.loc[(pb > 0.01) & (pb <= 0.02), "pullback_score"] += 10

        _df.loc[_df.close > _df.ma5d, "pullback_score"] += 10
        _df.loc[_df.close > _df.ma10d, "pullback_score"] += 10

        # ---------- Volume ----------
        _df["volume_score"] = 0
        vr = _df.lastv1d / _df.lastv2d.replace(0, np.nan)

        _df.loc[vr >= 1.0, "volume_score"] += 20
        _df.loc[(vr >= 0.7) & (vr < 1.0), "volume_score"] += 15
        _df.loc[(vr >= 0.5) & (vr < 0.7), "volume_score"] += 10

        # ---------- MACD ----------
        if self.use_macd:
            _df["macd_score"] = 0
            _df.loc[_df.macddif > _df.macddea, "macd_score"] += 10
            _df.loc[_df.macd > 0, "macd_score"] += 5
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

        _df["entry_low"] = _df.ma5d * 0.99
        _df["entry_high"] = _df.ma5d * 1.01
        _df["sl"] = _df.ma10d * 0.98
        _df["tp"] = _df.upper

        return _df

    # ================= Main =================
    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        _df = self.score(df)
        _df = _df[_df.strong_score >= self.min_score]
        _df = self.classify_risk(_df)
        _df = self.suggest_entry(_df)

        _df["strategy_id"] = self.STRATEGY_ID
        _df = _df.sort_values("strong_score", ascending=False)

        return _df

if __name__ == '__main__':
    strategy = StrongPullbackMA5Strategy(
        min_score=65,
        use_macd=True,
        use_rsi=True
    )

    df_signal = strategy.run(top_signal)

    df_signal[
        ["name", "close", "strong_score",
         "trend_score", "pullback_score",
         "volume_score", "macd_score", "rsi_score",
         "entry_low", "entry_high", "sl", "tp",
         "risk_level"]
    ].head(15)


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