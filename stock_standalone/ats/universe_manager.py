# -*- coding: utf-8 -*-
"""
ATS Universe Manager (Refactored)
从「全量重算」改为「从 SignalLedger 同步」的三级股票池管理器。

原有逻辑 (已废除):
    每 3 秒 run_pipeline_filtering() 全量扫描 5000+ 只股票 → 池子快速流动

新逻辑:
    从 SignalLedger 读取已沉淀信号 → 三级池稳定展示，不快速流动
    信号一旦写入账本即锁定，不因行情波动被冲掉

三级池:
    1. Radar Pool (🌌 候选雷达池): SignalLedger 中 tier=RADAR 的信号
    2. Watchlist Pool (📌 精选观察池): SignalLedger 中 tier=WATCH 的信号
    3. Trading Pool (💰 实盘交易池): SignalLedger 中 tier=TRADE 的信号 + 真实持仓
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

    # ==================================================================
    # 新增: 从 SignalLedger 同步数据（替代全量重算）
    # ==================================================================

    def sync_from_ledger(self, signal_ledger):
        """从信号账本同步已沉淀信号到三级池

        核心改进:
        - 不做全量重算，只读取 SignalLedger 中已确认的信号
        - 保留 trade_pool 中的真实持仓（不受 ledger 影响）
        - 池子内容稳定，不会因行情波动而快速流动
        
        Args:
            signal_ledger: SignalLedger 实例
        """
        from ats.signal_ledger import PHASE_LABELS
        import datetime

        # 保留 trade_pool 中非来自 ledger 的持仓项（真实持仓）
        real_positions = {}
        for code, meta in self.trade_pool.items():
            if meta.get('_from_ledger') is not True:
                real_positions[code] = meta

        # 从 SignalLedger 读取展示数据
        radar_entries = signal_ledger.get_sorted_pool('RADAR', limit=signal_ledger.RADAR_DISPLAY_LIMIT)
        watch_entries = signal_ledger.get_sorted_pool('WATCH', limit=signal_ledger.WATCH_DISPLAY_LIMIT)
        trade_entries = signal_ledger.get_sorted_pool('TRADE')

        # 重建 radar_pool
        new_radar = {}
        for entry in radar_entries:
            phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
            first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
            new_radar[entry.code] = {
                'name': entry.name or '未知',
                'price': entry.latest_price,
                'pct': entry.latest_pct,
                'deviation': entry.latest_deviation,
                'strategy': f'{phase_label} [{first_time}]',
                'reason': f'优先级: {entry.priority_score:.0f} | 偏离: {entry.latest_deviation:+.1f}%',
                'timestamp': entry.first_seen_ts,
                '_from_ledger': True,
            }
        self.radar_pool = new_radar

        # 重建 watch_pool
        new_watch = {}
        for entry in watch_entries:
            phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
            first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
            # 获取晋级原因
            promote_reason = ''
            for hist in reversed(entry.state_history):
                if 'PROMOTED' in hist.get('action', ''):
                    promote_reason = hist.get('reason', '')
                    break
            new_watch[entry.code] = {
                'name': entry.name or '未知',
                'price': entry.latest_price,
                'pct': entry.latest_pct,
                'deviation': entry.latest_deviation,
                'strategy': f'{phase_label} [{first_time}]',
                'reason': promote_reason or f'优先级: {entry.priority_score:.0f}',
                'timestamp': entry.first_seen_ts,
                '_from_ledger': True,
            }
        self.watch_pool = new_watch

        # 重建 trade_pool（合并 ledger 信号与真实持仓）
        new_trade = dict(real_positions)  # 保留真实持仓
        for entry in trade_entries:
            if entry.code not in new_trade:
                phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
                first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
                new_trade[entry.code] = {
                    'name': entry.name or '未知',
                    'price': entry.latest_price,
                    'pct': entry.latest_pct,
                    'strategy': f'{phase_label} [{first_time}]',
                    'reason': f'优先级: {entry.priority_score:.0f} | 持仓追踪',
                    'timestamp': entry.first_seen_ts,
                    '_from_ledger': True,
                }
        self.trade_pool = new_trade

    # ==================================================================
    # 原有全量重算逻辑（保留兼容，已不推荐使用）
    # ==================================================================

    def run_pipeline_filtering(self, df_all, ma20_series=None):
        """
        [DEPRECATED] 全量重算管道 — 已被 sync_from_ledger() 替代。
        保留此方法以兼容旧调用路径，但内部不再执行全量扫描。
        实际过滤逻辑已转移至 SignalLedger.record_signal()。
        """
        pass  # 不再执行全量重算，由 SignalLedger 增量处理
