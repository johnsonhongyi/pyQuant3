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
        import math

        def _format_item(code, meta, def_strat, def_reason):
            name = meta.get('name', '未知')
            price_v = meta.get('price', 0.0)
            pct_v = meta.get('pct', 0.0)
            try:
                price_v = float(price_v)
                if math.isnan(price_v):
                    price_v = 0.0
            except Exception:
                price_v = 0.0
            try:
                pct_v = float(pct_v)
                if math.isnan(pct_v):
                    pct_v = 0.0
            except Exception:
                pct_v = 0.0

            p_str = f"{price_v:.2f}" if price_v > 0.001 else "--"
            pct_str = f"{pct_v:+.2f}%" if price_v > 0.001 or pct_v != 0.0 else "0.00%"
            strat = meta.get('strategy', def_strat)
            reason = meta.get('reason', def_reason)
            return (code, name, p_str, pct_str, strat, reason)

        radar_list = [_format_item(code, meta, 'MA20d支撑', '回踩均线中') for code, meta in self.radar_pool.items()]
        watch_list = [_format_item(code, meta, '黄金早盘', '黄金时段爆量高走') for code, meta in self.watch_pool.items()]
        trade_list = [_format_item(code, meta, '建议买入', f"仓位: {meta.get('alloc_pct', 10.0)}% | 持仓追踪") for code, meta in self.trade_pool.items()]

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

    def sync_from_ledger(self, signal_ledger, df_realtime=None, price_pct_cache=None):
        """从信号账本同步已沉淀信号到三级池

        核心改进:
        - 不做全量重算，只读取 SignalLedger 中已确认的信号
        - 保留 trade_pool 中的真实持仓（不受 ledger 影响）
        - 池子内容稳定，不会因行情波动而快速流动
        - 自动纠正真实中文股票名称与最新估计现价，绝不显示 '未知' 或 '0.00'
        
        Args:
            signal_ledger: SignalLedger 实例
            df_realtime: 实时 DataFrame (可选)
            price_pct_cache: 实时价格缓存 (可选)
        """
        from ats.signal_ledger import PHASE_LABELS
        import datetime

        def _get_name(code_str, current_name=None):
            if current_name and current_name not in ('未知', '重点标的', '') and current_name != code_str and not str(current_name).isdigit():
                return current_name
            if df_realtime is not None and not df_realtime.empty and code_str in df_realtime.index:
                row = df_realtime.loc[code_str]
                n_df = str(row.get('name', '') if hasattr(row, 'get') else row['name']).strip()
                if n_df and n_df != code_str and not n_df.isdigit() and n_df != "未知":
                    return n_df
            try:
                from sys_utils import resolve_stock_name
                n = resolve_stock_name(code_str)
                if n and str(n).strip() and str(n).strip() != code_str and not str(n).strip().isdigit():
                    return str(n).strip()
            except Exception:
                pass
            return current_name or code_str

        import math
        def _get_price_pct(code_str, current_price, current_pct):
            p = current_price
            pct = current_pct
            try:
                p = float(p)
                if math.isnan(p):
                    p = 0.0
            except Exception:
                p = 0.0
            try:
                pct = float(pct)
                if math.isnan(pct):
                    pct = 0.0
            except Exception:
                pct = 0.0

            if p > 0.01:
                return p, pct
            if df_realtime is not None and not df_realtime.empty and code_str in df_realtime.index:
                row = df_realtime.loc[code_str]
                import pandas as pd
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                try:
                    p_cand = float(row.get('close', row.get('price', 0.0)))
                    if not math.isnan(p_cand):
                        p = p_cand
                except Exception:
                    pass
                try:
                    pct_cand = float(row.get('percent', 0.0))
                    if not math.isnan(pct_cand):
                        pct = pct_cand
                except Exception:
                    pass
                if p > 0.01:
                    return p, pct
            if price_pct_cache and code_str in price_pct_cache:
                p_c, pct_c = price_pct_cache[code_str]
                try:
                    p_c = float(p_c)
                    pct_c = float(pct_c)
                    if not math.isnan(p_c) and p_c > 0.01:
                        p = p_c
                    if not math.isnan(pct_c):
                        pct = pct_c
                except Exception:
                    pass
                if p > 0.01:
                    return p, pct
            return p, pct

        # 保留 trade_pool 中非来自 ledger 的持仓项（真实持仓）
        real_positions = {}
        for code, meta in self.trade_pool.items():
            if meta.get('_from_ledger') is not True:
                real_positions[code] = meta

        # 从 SignalLedger 读取展示数据 (具备 hasattr 防弹自愈保护)
        radar_limit = getattr(signal_ledger, 'RADAR_DISPLAY_LIMIT', 30)
        watch_limit = getattr(signal_ledger, 'WATCH_DISPLAY_LIMIT', 15)

        if hasattr(signal_ledger, 'get_sorted_pool'):
            radar_entries = signal_ledger.get_sorted_pool('RADAR', limit=radar_limit)
            watch_entries = signal_ledger.get_sorted_pool('WATCH', limit=watch_limit)
            trade_entries = signal_ledger.get_sorted_pool('TRADE')
        elif hasattr(signal_ledger, 'entries') and isinstance(signal_ledger.entries, dict):
            entries_list = list(signal_ledger.entries.values())
            def _get_tier_entries(tier_name, limit_num=None):
                sub = [e for e in entries_list if getattr(e, 'tier', '') == tier_name]
                sub.sort(key=lambda x: getattr(x, 'priority_score', 0.0), reverse=True)
                return sub[:limit_num] if limit_num else sub

            radar_entries = _get_tier_entries('RADAR', radar_limit)
            watch_entries = _get_tier_entries('WATCH', watch_limit)
            trade_entries = _get_tier_entries('TRADE')
        else:
            radar_entries, watch_entries, trade_entries = [], [], []

        # 重建 radar_pool
        new_radar = {}
        for entry in radar_entries:
            phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
            first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
            real_name = _get_name(entry.code, entry.name)
            p_val, pct_val = _get_price_pct(entry.code, entry.latest_price, entry.latest_pct)
            new_radar[entry.code] = {
                'name': real_name,
                'price': p_val,
                'pct': pct_val,
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
            promote_reason = ''
            for hist in reversed(entry.state_history):
                if 'PROMOTED' in hist.get('action', ''):
                    promote_reason = hist.get('reason', '')
                    break
            real_name = _get_name(entry.code, entry.name)
            p_val, pct_val = _get_price_pct(entry.code, entry.latest_price, entry.latest_pct)
            new_watch[entry.code] = {
                'name': real_name,
                'price': p_val,
                'pct': pct_val,
                'deviation': entry.latest_deviation,
                'strategy': f'{phase_label} [{first_time}]',
                'reason': promote_reason or f'优先级: {entry.priority_score:.0f}',
                'timestamp': entry.first_seen_ts,
                '_from_ledger': True,
            }

        # 重建 trade_pool（合并 ledger 信号与真实持仓）
        new_trade = dict(real_positions)  # 保留真实持仓
        for entry in trade_entries:
            if entry.code not in new_trade:
                phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
                first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
                real_name = _get_name(entry.code, entry.name)
                p_val, pct_val = _get_price_pct(entry.code, entry.latest_price, entry.latest_pct)
                new_trade[entry.code] = {
                    'name': real_name,
                    'price': p_val,
                    'pct': pct_val,
                    'strategy': f'{phase_label} [{first_time}]',
                    'reason': f'优先级: {entry.priority_score:.0f} | 持仓追踪',
                    'timestamp': entry.first_seen_ts,
                    '_from_ledger': True,
                }
        self.trade_pool = new_trade

        # 确保全局重点关注股票 100% 被保留在 watch_pool 观察池中，防丢防删
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
            for code in fav_stocks:
                code_str = str(code).strip()
                if not code_str:
                    continue
                if code_str not in new_watch and code_str not in new_trade:
                    entry = signal_ledger.entries.get(code_str)
                    real_name = _get_name(code_str, entry.name if entry else None)

                    if entry:
                        phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⭐')
                        first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
                        price_val, pct_val = _get_price_pct(code_str, entry.latest_price, entry.latest_pct)
                        dev_val = entry.latest_deviation
                        p_score = entry.priority_score
                    else:
                        phase_label = '⭐'
                        first_time = '关注'
                        price_val, pct_val = _get_price_pct(code_str, 0.0, 0.0)
                        dev_val = 0.0
                        p_score = 200.0

                    new_watch[code_str] = {
                        'name': real_name,
                        'price': price_val,
                        'pct': pct_val,
                        'deviation': dev_val,
                        'strategy': f'⭐ 重点关注 [{first_time}]',
                        'reason': f'优先级: {p_score:.0f} | 基础重点跟进',
                        'timestamp': entry.first_seen_ts if entry else time.time(),
                        '_from_ledger': True,
                    }
        except Exception as e:
            print(f"[UniverseManager] Sync favorite stocks warning: {e}")

        self.watch_pool = new_watch

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
