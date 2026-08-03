# -*- coding: utf-8 -*-
"""
ATS Session Snapshot
盘中快照持久化 — 定时序列化信号账本，支持收盘后复盘分析

核心功能:
1. 每 10 分钟自动序列化 SignalLedger 至 JSON 文件
2. 收盘后自动生成当日信号总结报告
3. 支持跨日信号追踪 (昨日 WATCH → 今日是否继续走强)
4. 自动清理超过 5 天的历史快照
"""

import os
import json
import time
import datetime
import glob


class SessionSnapshot:
    """盘中快照管理器"""
    
    SNAPSHOT_INTERVAL_SEC = 600   # 10 分钟快照间隔
    MAX_HISTORY_DAYS = 5          # 保留最近 5 天的快照
    SIGNAL_RETAIN_DAYS = 3        # 信号保留 3 个交易日
    
    def __init__(self, log_dir=None):
        if log_dir is None:
            try:
                from sys_utils import get_app_root
                log_dir = os.path.join(get_app_root(), 'logs', 'signal_snapshots')
            except Exception:
                log_dir = os.path.join('.', 'logs', 'signal_snapshots')
        
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        
        self._last_snapshot_ts = 0
        self._last_cleanup_date = None
        self._last_summary_date = None
    
    def should_snapshot(self):
        """判断是否到了快照时间"""
        return (time.time() - self._last_snapshot_ts) >= self.SNAPSHOT_INTERVAL_SEC
    
    def save_snapshot(self, signal_ledger):
        """保存信号账本快照
        
        Args:
            signal_ledger: SignalLedger 实例
        """
        if not self.should_snapshot():
            return False
        
        try:
            now = datetime.datetime.now()
            filename = f"signal_ledger_{now.strftime('%Y%m%d_%H%M')}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            snapshot_data = {
                'timestamp': now.isoformat(),
                'date': now.strftime('%Y-%m-%d'),
                'time': now.strftime('%H:%M:%S'),
                'total_signals': len(signal_ledger.entries),
                'tier_counts': {
                    'RADAR': sum(1 for e in signal_ledger.entries.values() if e.tier == 'RADAR'),
                    'WATCH': sum(1 for e in signal_ledger.entries.values() if e.tier == 'WATCH'),
                    'TRADE': sum(1 for e in signal_ledger.entries.values() if e.tier == 'TRADE'),
                    'INACTIVE': sum(1 for e in signal_ledger.entries.values() if e.tier == 'INACTIVE'),
                },
                'entries': {
                    code: entry.to_dict() 
                    for code, entry in signal_ledger.entries.items()
                }
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
            
            self._last_snapshot_ts = time.time()
            return True
            
        except Exception as e:
            print(f"[SessionSnapshot] Error saving snapshot: {e}")
            return False
    
    def save_daily_summary(self, signal_ledger, force=False):
        """生成当日信号总结报告 (收盘后调用，自动覆盖更新为最新终盘总结)
        
        Args:
            signal_ledger: SignalLedger 实例
            force: 是否强制覆盖重新生成
        """
        try:
            # 非交易日拒绝触发（除非 force 强行指定）
            if not force:
                try:
                    import JohnsonUtil.commonTips as cct
                    if not cct.get_trade_date_status():
                        return False
                except Exception:
                    pass

            now = datetime.datetime.now()
            today_str = now.strftime('%Y%m%d')
            
            # 单日防重复无谓写磁盘与刷屏 Log
            if not force and getattr(self, '_last_summary_date', None) == today_str:
                return True

            filename = f"daily_summary_{today_str}.json"
            filepath = os.path.join(self.log_dir, filename)
            
            # 按时段分组统计
            phase_groups = {}
            for code, entry in signal_ledger.entries.items():
                phase = entry.first_seen_phase
                if phase not in phase_groups:
                    phase_groups[phase] = []
                phase_groups[phase].append({
                    'code': code,
                    'name': entry.name,
                    'first_seen_price': entry.first_seen_price,
                    'first_seen_pct': entry.first_seen_pct,
                    'latest_pct': entry.latest_pct,
                    'priority_score': entry.priority_score,
                    'tier': entry.tier,
                    'volume_score': entry.volume_score,
                    'pct_change_since_found': entry.latest_pct - entry.first_seen_pct if entry.first_seen_pct else 0,
                })
            
            # 按优先级排序
            for phase in phase_groups:
                phase_groups[phase].sort(key=lambda x: x['priority_score'], reverse=True)
            
            summary = {
                'date': now.strftime('%Y-%m-%d'),
                'total_signals': len(signal_ledger.entries),
                'phase_distribution': {k: len(v) for k, v in phase_groups.items()},
                'top_10_by_priority': sorted(
                    [e.to_dict() for e in signal_ledger.entries.values()],
                    key=lambda x: x.get('priority_score', 0),
                    reverse=True
                )[:10],
                'phase_details': phase_groups,
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            self._last_summary_date = today_str
            print(f"[SessionSnapshot] Daily summary saved to {filepath} ({len(summary.get('watchlist', []))} watch, {len(summary.get('tradelist', []))} trade)")
            
            try:
                from global_favorites import GlobalFavoriteManager
                GlobalFavoriteManager().backup_to_archives()
            except Exception as e:
                print(f"[SessionSnapshot] Auto archive backup error: {e}")

            return True
            
        except Exception as e:
            print(f"[SessionSnapshot] Error saving daily summary: {e}")
            return False
    
    def load_previous_day_signals(self):
        """加载前一交易日的信号快照 (用于跨日追踪)
        
        Returns:
            dict: {code: entry_dict} 或空字典
        """
        try:
            # 查找最近的 daily_summary 文件
            pattern = os.path.join(self.log_dir, 'daily_summary_*.json')
            files = sorted(glob.glob(pattern), reverse=True)
            
            today_str = datetime.date.today().strftime('%Y%m%d')
            
            for f in files:
                basename = os.path.basename(f)
                # 跳过今天的
                if today_str in basename:
                    continue
                
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                
                # 提取 WATCH 和 TRADE 级别的信号用于跨日追踪
                result = {}
                for phase, entries in data.get('phase_details', {}).items():
                    for entry in entries:
                        if entry.get('tier') in ('WATCH', 'TRADE'):
                            result[entry['code']] = entry
                
                return result
            
        except Exception as e:
            print(f"[SessionSnapshot] Error loading previous day signals: {e}")
        
        return {}
    
    def cleanup_old_snapshots(self):
        """清理超过 MAX_HISTORY_DAYS 天的历史快照"""
        today = datetime.date.today()
        
        # 每天只清理一次
        if self._last_cleanup_date == today:
            return
        self._last_cleanup_date = today
        
        cutoff = today - datetime.timedelta(days=self.MAX_HISTORY_DAYS)
        cutoff_str = cutoff.strftime('%Y%m%d')
        
        try:
            for pattern in ['signal_ledger_*.json', 'daily_summary_*.json']:
                for filepath in glob.glob(os.path.join(self.log_dir, pattern)):
                    basename = os.path.basename(filepath)
                    # 提取日期部分
                    parts = basename.replace('.json', '').split('_')
                    for part in parts:
                        if len(part) == 8 and part.isdigit():
                            if part < cutoff_str:
                                try:
                                    os.remove(filepath)
                                    print(f"[SessionSnapshot] Cleaned old snapshot: {basename}")
                                except Exception:
                                    pass
                            break
        except Exception as e:
            print(f"[SessionSnapshot] Error cleaning old snapshots: {e}")
