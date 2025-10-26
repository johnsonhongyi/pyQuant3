import pandas as pd
import numpy as np
import time
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory, commonTips as cct
from threading import Event

eval_cols = [
    'lower','upper','ene','bandwidth','bollpect',
    'macddif','macddea','macd','macdlast1','macdlast2','macdlast3','macdlast4','macdlast5','macdlast6',
    'rsi','kdj_k','kdj_d','kdj_j',
    'EMA10','EMA20','SWL','SWS',
    'resist_next','support_next','break_next','reverse_next','resist_today','support_today',
    'score','ZSH','ZSL'
]
class RealtimeSignalManager:
    def __init__(self, get_df_func, refresh_interval=10):
        self.get_df_func = get_df_func
        self.refresh_interval = refresh_interval
        self.stop_event = Event()
        self.df_cache = pd.DataFrame()

    # # ========== 信号检测核心 ==========
    # def detect_signals(self, df: pd.DataFrame) -> pd.DataFrame:
    #     df = df.copy()
    #     if df.empty:
    #         return df

    #     # ========== 均线与基础指标 ==========
    #     df["EMA10"] = df["close"].ewm(span=10, adjust=False).mean()
    #     df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()

    #     # 支撑/压力带 (SWL / SWS)
    #     df["SWL"] = (df["EMA10"] * 7 + df["EMA20"] * 3) / 10
    #     vol5 = df["volume"].rolling(5).sum()
    #     df["CAPITAL"] = df.get("CAPITAL", vol5.rolling(20).mean())
    #     factor = np.maximum(1, 100 * (vol5 / (3 * df["CAPITAL"])))
    #     df["SWS"] = df["EMA20"].ewm(span=factor.clip(1, 200)).mean()

    #     # ========== 明日价位系统 ==========
    #     E = (df["high"] + df["low"] + df["open"] + 2 * df["close"]) / 5
    #     df["resist_next"] = 2 * E - df["low"]
    #     df["support_next"] = 2 * E - df["high"]
    #     df["break_next"] = E + (df["high"] - df["low"])
    #     df["reverse_next"] = E - (df["high"] - df["low"])

    #     df["resist_today"] = df["resist_next"].shift(1)
    #     df["support_today"] = df["support_next"].shift(1)

    #     # ========== 量化评分系统 ==========
    #     X1 = np.where(df["close"].rolling(5).mean() > df["close"].rolling(10).mean(), 20, 0)
    #     X2 = np.where(df["close"].rolling(20).mean() > df["close"].rolling(60).mean(), 10, 0)

    #     # 简易 KDJ
    #     low_min = df["low"].rolling(9).min()
    #     high_max = df["high"].rolling(9).max()
    #     rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    #     df["K"] = rsv.ewm(span=3, adjust=False).mean()
    #     df["D"] = df["K"].ewm(span=3, adjust=False).mean()
    #     df["J"] = 3 * df["K"] - 2 * df["D"]

    #     X3 = np.where(df["J"] > df["K"], 10, 0)

    #     # MACD
    #     ema12 = df["close"].ewm(span=12, adjust=False).mean()
    #     ema26 = df["close"].ewm(span=26, adjust=False).mean()
    #     df["DIF"] = ema12 - ema26
    #     df["DEA"] = df["DIF"].ewm(span=9, adjust=False).mean()
    #     df["MACD"] = (df["DIF"] - df["DEA"]) * 2

    #     X4 = np.where(df["DIF"] > df["DEA"], 10, 0)
    #     X5 = np.where(df["MACD"] > 0, 10, 0)
    #     X6 = np.where(df["volume"] > df["volume"].rolling(60).mean(), 10, 0)
    #     X7 = np.where(
    #         (df["close"] - df["low"].rolling(60).min()) /
    #         (df["high"].rolling(60).max() - df["low"].rolling(60).min()) > 0.5, 10, 0
    #     )
    #     X8 = np.where(df["close"] / df["close"].shift(1) > 1.03, 10, 0)

    #     df["score"] = X1 + X2 + X3 + X4 + X5 + X6 + X7 + X8

    #     # ========== 信号与情绪 ==========
    #     df["signal"] = ""
    #     df.loc[(df["close"] < df["SWS"]) & (df["score"] >= 40), "signal"] = "BUY_SWS↑"
    #     df.loc[(df["close"] > df["SWL"]) & (df["score"] < 30), "signal"] = "SELL_SWL↓"

    #     df["emotion"] = "中性"
    #     mean_vol = df["volume"].rolling(20).mean()
    #     df.loc[df["volume"] > 1.2 * mean_vol, "emotion"] = "乐观"
    #     df.loc[df["volume"] < 0.8 * mean_vol, "emotion"] = "悲观"

    #     return df
    # ============================================
    # ============   信号检测模块   ===============
    # ============================================

    def detect_signals(df: pd.DataFrame) -> pd.DataFrame:
        """
        使用 get_tdx_macd() 已经计算好的列来生成信号与情绪
        """
        if df.empty:
            return df

        df["signal"] = ""
        df.loc[(df["close"] < df["SWS"]) & (df["score"] >= 40), "signal"] = "BUY_SWS↑"
        df.loc[(df["close"] > df["SWL"]) & (df["score"] < 30), "signal"] = "SELL_SWL↓"

        df["emotion"] = "中性"
        mean_vol = df["volume"].rolling(20).mean()
        df.loc[df["volume"] > 1.2 * mean_vol, "emotion"] = "乐观"
        df.loc[df["volume"] < 0.8 * mean_vol, "emotion"] = "悲观"

        return df

    # ========== 刷新循环 ==========
    def refresh_loop(self):
        first_run = True
        while not self.stop_event.is_set():
            try:
                df = self.get_df_func()
                if df is not None and not df.empty:
                    # 第一次启动：不论时间都运行一次
                    if first_run or cct.get_work_time():
                        df = self.detect_signals(df)
                        self.df_cache = df.copy()
                        self.after(0, self.apply_filters)
                        first_run = False
                else:
                    print("[Monitor] 无数据")
            except Exception as e:
                print("[Monitor] 更新错误:", e)
            time.sleep(self.refresh_interval)

    def apply_filters(self):
        # 示例：可以在这里打印/显示当前信号结果
        if not self.df_cache.empty:
            active = self.df_cache[self.df_cache["signal"] != ""]
            if not active.empty:
                print(active[["name", "close", "score", "signal", "emotion"]].tail(5))
