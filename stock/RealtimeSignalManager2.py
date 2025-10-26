import pandas as pd
import numpy as np
import time
import cct

class RealtimeSignalManager:
    def __init__(self, get_df_func, refresh_interval=10):
        self.get_df_func = get_df_func
        self.refresh_interval = refresh_interval
        self.stop_event = None
        self.df_cache = pd.DataFrame()
        self.global_data = {}   # 🔹 每个 code 的历史数据存放这里

    # ========== 个股信号计算 ==========
    def detect_single(self, df: pd.DataFrame) -> dict:
        """输入单支股票的历史数据 df，输出最后一行信号信息"""
        if len(df) < 30:
            return {}

        # --- 均线与支撑压力 ---
        df["EMA10"] = df["close"].ewm(span=10, adjust=False).mean()
        df["EMA20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["SWL"] = (df["EMA10"] * 7 + df["EMA20"] * 3) / 10

        vol5 = df["volume"].rolling(5).sum()
        df["CAPITAL"] = df.get("CAPITAL", vol5.rolling(20).mean())
        factor = np.maximum(1, 100 * (vol5 / (3 * df["CAPITAL"])))
        df["SWS"] = df["EMA20"].ewm(span=factor.clip(1, 200)).mean()

        # --- 明日价位 ---
        E = (df["high"] + df["low"] + df["open"] + 2 * df["close"]) / 5
        df["resist_next"] = 2 * E - df["low"]
        df["support_next"] = 2 * E - df["high"]

        # --- 简易量化评分 ---
        X1 = np.where(df["close"].rolling(5).mean() > df["close"].rolling(10).mean(), 20, 0)
        X2 = np.where(df["close"].rolling(20).mean() > df["close"].rolling(60).mean(), 10, 0)
        df["score"] = X1 + X2

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # --- 信号逻辑 ---
        signal = ""
        if last["close"] < last["SWS"] and last["score"] >= 30:
            signal = "BUY_SWS↑"
        elif last["close"] > last["SWL"] and last["score"] < 20:
            signal = "SELL_SWL↓"

        return {
            "code": last["code"],
            "name": last.get("name", ""),
            "close": last["close"],
            "score": last["score"],
            "signal": signal,
            "emotion": "乐观" if last["volume"] > df["volume"].rolling(20).mean().iloc[-1] else "悲观"
        }

    # ========== 全局更新 ==========
    def detect_signals(self, snapshot_df: pd.DataFrame) -> pd.DataFrame:
        """
        snapshot_df: 每次实时更新的截面数据（多只股票当前状态）
        自动合并进 global_data，并为每支个股计算信号
        """
        result_rows = []
        for _, row in snapshot_df.iterrows():
            code = str(row["code"])
            new_row = {
                "code": code,
                "name": row.get("name", ""),
                "open": row.get("open", np.nan),
                "high": row.get("high", np.nan),
                "low": row.get("low", np.nan),
                "close": row.get("now", np.nan),
                "volume": row.get("volume", np.nan)
            }

            # --- 合并到全局 df ---
            if code not in self.global_data:
                self.global_data[code] = pd.DataFrame([new_row])
            else:
                gdf = self.global_data[code]
                # 避免重复 append 相同时间点
                if gdf.iloc[-1]["close"] != new_row["close"]:
                    self.global_data[code] = pd.concat([gdf, pd.DataFrame([new_row])]).tail(300)

            # --- 个股信号检测 ---
            try:
                info = self.detect_single(self.global_data[code])
                if info:
                    result_rows.append(info)
            except Exception as e:
                print(f"[{code}] detect error:", e)

        return pd.DataFrame(result_rows)
