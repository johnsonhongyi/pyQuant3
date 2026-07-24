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

    def add_to_radar(self, code, name, price, pct, deviation=0.0, strategy="MA20支撑", reason="大级别支撑偏离度低"):
        """
        Adds a stock to the Radar Pool.
        """
        self.radar_pool[code] = {
            "name": name,
            "price": price,
            "pct": pct,
            "deviation": deviation,
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
        stocks into the respective pools based on criteria. Also performs eviction
        of broken/out-of-range stocks for dynamic universe rotation.
        """
        if df_all is None or df_all.empty:
            return

        # 1. Adaptively locate real MA20 column name ('ma20d', 'ma20', 'MA20')
        ma20_col = None
        for col_name in ['ma20d', 'ma20', 'MA20', 'ma20_series']:
            if col_name in df_all.columns:
                ma20_col = col_name
                break

        # Get currently tracked codes
        tracked_codes = set(self.radar_pool.keys()) | set(self.watch_pool.keys()) | set(self.trade_pool.keys())
        
        # 2. Select target dataframe for evaluation
        if ma20_col:
            close_s = df_all['close'] if 'close' in df_all.columns else df_all.get('price', df_all.iloc[:, 0])
            safe_ma20 = df_all[ma20_col].replace(0, float('nan'))
            dev_series = (close_s - safe_ma20) / safe_ma20 * 100.0
            
            # Select stocks that are either near MA20 (-1.5% to +2.5%) OR currently in tracked pools
            valid_mask = ((dev_series >= -1.5) & (dev_series <= 2.5)) | df_all.index.isin(tracked_codes)
            target_df = df_all[valid_mask]
        else:
            common_codes = [c for c in tracked_codes if c in df_all.index]
            target_df = df_all.loc[common_codes]

        # 3. Iterating through target dataframe to update state & promote
        for code, row in target_df.iterrows():
            code_str = str(code).strip()
            name = row.get('name', '个股')
            price = float(row.get('close', row.get('price', 0.0)))
            pct = float(row.get('percent', 0.0))
            
            # Compute MA20 deviation
            ma20_val = price * 0.99
            if ma20_col and ma20_col in row.index:
                try:
                    v = float(row[ma20_col])
                    if v > 0:
                        ma20_val = v
                except Exception:
                    pass
                    
            if price > 0 and ma20_val > 0:
                deviation = (price - ma20_val) / ma20_val * 100.0
            else:
                deviation = 0.0

            # --- Eviction / Degradation Check ---
            # If stock drops sharply below MA20 (< -5.0%) or skyrockets far above (> 15.0%),
            # evict it from Radar and Watch pools to allow fresh pool rotation.
            if code_str not in self.trade_pool:
                if deviation < -5.0 or deviation > 15.0:
                    self.evict(code_str)
                    continue

            # --- Funnel Condition 1: Radar (deviation within -1.5% and +2.5%) ---
            if -1.5 <= deviation <= 2.5:
                if code_str not in self.radar_pool and code_str not in self.watch_pool and code_str not in self.trade_pool:
                    self.add_to_radar(code_str, name, price, pct, deviation=deviation, reason=f"偏离MA20度: {deviation:+.2f}%")

            # --- Funnel Condition 2: Watchlist (if it's in Radar, volume surge or positive momentum) ---
            if code_str in self.radar_pool:
                vol_ratio = float(row.get('volume_ratio', row.get('vol_ratio', 1.0)))
                dff_val = float(row.get('dff', 0.0))
                if (vol_ratio >= 1.2 and pct >= -1.0) or (pct >= 1.5 and dff_val > 1.0):
                    self.promote_to_watch(code_str, reason=f"量比: {vol_ratio:.1f} | 涨幅: {pct:+.2f}%")

            # --- Funnel Condition 3: Trade (if it's in Watch, price above VWAP & strong momentum) ---
            if code_str in self.watch_pool:
                vwap = float(row.get('vwap', row.get('avg_price', price * 0.99)))
                if price >= vwap and pct >= 1.0:
                    self.promote_to_trade(code_str, alloc_pct=15.0, reason="突破均线且量能持续放量")

        # 4. Limit Radar Pool size to Top 50 to maintain UI responsiveness and high entropy
        if len(self.radar_pool) > 50:
            def _safe_get_dev(meta):
                if 'deviation' in meta:
                    try:
                        return abs(float(meta['deviation']))
                    except Exception:
                        pass
                reason_str = str(meta.get('reason', ''))
                if '偏离MA20度:' in reason_str:
                    try:
                        return abs(float(reason_str.split('偏离MA20度:')[-1].replace('%', '').strip()))
                    except Exception:
                        pass
                return 0.0

            # Keep trade/watch pools untouched, trim radar_pool by absolute deviation closeness
            sorted_radar = sorted(
                self.radar_pool.items(),
                key=lambda x: (
                    _safe_get_dev(x[1]),
                    -x[1].get('timestamp', 0)
                )
            )
            self.radar_pool = dict(sorted_radar[:50])

