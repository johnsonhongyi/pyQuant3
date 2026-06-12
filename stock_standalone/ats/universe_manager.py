# -*- coding: utf-8 -*-
"""
ATS Universe Manager
Implements the 3-tier stock universe filtering funnel:
1. Radar Pool (🌌 候选雷达池): Pullback candidates near MA20d.
2. Watchlist Pool (📌 精选观察池): Active breakout or volume surge candidates.
3. Trading Pool (💰 实盘交易池): Formally recommended/active trading targets.
"""

import time
import pandas as pd

class UniverseManager:
    def __init__(self):
        # Store items as dictionaries mapping code -> metadata dict
        self.radar_pool = {}
        self.watch_pool = {}
        self.trade_pool = {}

    def get_pools(self):
        """
        Returns lists of tuples formatted for UniverseTreeWidget.
        """
        radar_list = []
        for code, meta in self.radar_pool.items():
            radar_list.append((
                code,
                meta.get('name', '未知'),
                f"{meta.get('price', 0.0):.2f}",
                f"{meta.get('pct', 0.0):+.2f}%",
                meta.get('strategy', 'MA20d支撑'),
                meta.get('reason', '回踩均线中')
            ))
            
        watch_list = []
        for code, meta in self.watch_pool.items():
            watch_list.append((
                code,
                meta.get('name', '未知'),
                f"{meta.get('price', 0.0):.2f}",
                f"{meta.get('pct', 0.0):+.2f}%",
                meta.get('strategy', '黄金早盘'),
                meta.get('reason', '黄金时段爆量高走')
            ))

        trade_list = []
        for code, meta in self.trade_pool.items():
            trade_list.append((
                code,
                meta.get('name', '未知'),
                f"{meta.get('price', 0.0):.2f}",
                f"{meta.get('pct', 0.0):+.2f}%",
                meta.get('strategy', '建议买入'),
                meta.get('reason', f"仓位: {meta.get('alloc_pct', 10.0)}% | 持仓追踪")
            ))

        return radar_list, watch_list, trade_list

    def add_to_radar(self, code, name, price, pct, strategy="MA20支撑", reason="大级别支撑偏离度低"):
        """
        Adds a stock to the Radar Pool.
        """
        self.radar_pool[code] = {
            "name": name,
            "price": price,
            "pct": pct,
            "strategy": strategy,
            "reason": reason,
            "timestamp": time.time()
        }
        # If it was promoted, evict it from lower levels to avoid duplications
        self.watch_pool.pop(code, None)
        self.trade_pool.pop(code, None)

    def promote_to_watch(self, code, reason="黄金早盘爆量"):
        """
        Promotes a stock from Radar to Watchlist.
        """
        if code in self.radar_pool:
            meta = self.radar_pool.pop(code)
            meta["reason"] = reason
            meta["strategy"] = "早盘拉升"
            meta["timestamp"] = time.time()
            self.watch_pool[code] = meta
            return True
        return False

    def promote_to_trade(self, code, alloc_pct=10.0, reason="符合所有买入判定及风控"):
        """
        Promotes a stock from Watchlist to Trade pool.
        """
        if code in self.watch_pool:
            meta = self.watch_pool.pop(code)
            meta["reason"] = reason
            meta["strategy"] = "持仓中"
            meta["alloc_pct"] = alloc_pct
            meta["timestamp"] = time.time()
            self.trade_pool[code] = meta
            return True
        return False

    def evict(self, code):
        """
        Removes stock from all pools (e.g. exit/stop loss triggered).
        """
        self.radar_pool.pop(code, None)
        self.watch_pool.pop(code, None)
        self.trade_pool.pop(code, None)

    def run_pipeline_filtering(self, df_all, ma20_series=None):
        """
        Evaluates df_all (real-time/historical snapshot) and automatically funnels
        stocks into the respective pools based on criteria.
        """
        if df_all is None or df_all.empty:
            return

        # Get currently tracked codes
        tracked_codes = set(self.radar_pool.keys()) | set(self.watch_pool.keys()) | set(self.trade_pool.keys())
        
        # Only evaluate tracked codes or pre-filtered data with real ma20 column to avoid mock flooding
        if 'ma20' in df_all.columns:
            dev = (df_all['close'] - df_all['ma20']) / df_all['ma20'] * 100
            valid_mask = (dev >= -1.0) & (dev <= 2.0)
            target_df = df_all[valid_mask | df_all.index.isin(tracked_codes)]
        else:
            common_codes = [c for c in tracked_codes if c in df_all.index]
            target_df = df_all.loc[common_codes]

        # Iterating through target dataframe
        for code, row in target_df.iterrows():
            name = row.get('name', '个股')
            price = row.get('close', row.get('price', 0.0))
            pct = row.get('percent', 0.0)
            
            # Use real ma20 if present in row, otherwise default to slightly below price for tracked codes
            ma20 = row.get('ma20', price * 0.99)
            deviation = (price - ma20) / ma20 * 100
            
            # Funnel Condition 1: Radar (deviation within -1% and +2%)
            if -1.0 <= deviation <= 2.0:
                if code not in self.radar_pool and code not in self.watch_pool and code not in self.trade_pool:
                    self.add_to_radar(code, name, price, pct, reason=f"偏离MA20度: {deviation:.2f}%")
            
            # Funnel Condition 2: Watchlist (if it's in Radar, and volume ratio is high)
            if code in self.radar_pool:
                vol_ratio = row.get('volume_ratio', 1.0)
                if vol_ratio >= 1.2 and pct >= -1.0:
                    self.promote_to_watch(code, reason=f"量比: {vol_ratio:.1f} | 涨幅: {pct:.2f}%")
                    
            # Funnel Condition 3: Trade (if it is in Watch, and price is above VWAP)
            if code in self.watch_pool:
                vwap = row.get('vwap', price * 0.99)
                if price >= vwap and pct >= 1.0:
                    self.promote_to_trade(code, alloc_pct=15.0, reason="突破均线且量能持续放量")
