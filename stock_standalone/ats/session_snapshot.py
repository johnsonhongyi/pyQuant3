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
        self._last_snapshot_hash = None
        self._last_summary_hash = None

    def _normalize_data_for_hash(self, obj):
        """深度递归规范化数据结构，忽略时间戳与微小浮点扰动，聚焦核心交易决策数据
        
        过滤与规范化项:
        1. 时间与时间戳 key: ('timestamp', 'time', 'first_seen_ts', 'first_seen_time', 'ts', 'date', 'pct_change_since_found')
        2. 所有浮点数: 统一精确保留 2 位小数 (round(v, 2))，彻底消灭浮点二进制微小误差
        3. 优先分与量能分: 统一 5 分打桶规整 (如 257.17 和 254.13 -> 255.0)
        4. 动态标签: 剥离括号内包含的实时涨跌幅数值 (如 '🌐 大宗商品共振 (+2.4%)' -> '🌐 大宗商品共振')
        """
        import re
        if isinstance(obj, dict):
            clean_d = {}
            for k, v in obj.items():
                if k in ('timestamp', 'time', 'first_seen_ts', 'first_seen_time', 'ts', 'date', 'pct_change_since_found'):
                    continue
                if k == 'signal_tag' and isinstance(v, str):
                    v = re.sub(r'\s*\([\+\-]?\d+(\.\d+)?%\)', '', v)
                if k in ('priority_score', 'volume_score') and isinstance(v, (int, float)):
                    # 优先分与量能分按 5 分为一档打桶规整 (如 257.17 和 254.13 -> 255.0)
                    v = round(float(v) / 5.0) * 5.0
                elif isinstance(v, float):
                    v = round(v, 2)
                clean_d[k] = self._normalize_data_for_hash(v)
            return clean_d
        elif isinstance(obj, list):
            return [self._normalize_data_for_hash(item) for item in obj]
        elif isinstance(obj, float):
            return round(obj, 2)
        else:
            return obj

    def _compute_dict_hash(self, data: dict) -> str:
        """计算字典结构化数据的哈希签名 (深度忽略动态毫秒时间戳与微浮点变动，仅比对核心业务信号)"""
        try:
            import hashlib
            normalized = self._normalize_data_for_hash(data)
            raw_bytes = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode('utf-8')
            return hashlib.md5(raw_bytes).hexdigest()
        except Exception:
            return ""

    def should_snapshot(self, force=False):
        """判断是否满足备份条件：收盘后(15:00后)定时备份 OR 程序退出关闭时强制备份"""
        if force:
            return True
        now = datetime.datetime.now()
        # 仅在 15:00 收盘后允许定时写盘 (且满足间隔控制)
        if now.hour >= 15:
            return (time.time() - self._last_snapshot_ts) >= self.SNAPSHOT_INTERVAL_SEC
        return False

    def save_snapshot(self, signal_ledger, force=False):
        """保存最新信号账本快照 (仅覆盖写入唯一的 signal_ledger_latest.json，绝不刷屏生成散落文件)
        
        Args:
            signal_ledger: SignalLedger 实例
            force: 是否强制保存 (如程序退出关闭时)
        """
        if not self.should_snapshot(force=force):
            return False
        
        try:
            now = datetime.datetime.now()
            # 统一使用固定唯一的 filename，不随时间生成新的 timestamp 散落文件
            filename = "signal_ledger_latest.json"
            filepath = os.path.join(self.log_dir, filename)
            
            # 【🛡️ 冷启动磁盘 Hash 预载入】若内存 Hash 为空但磁盘已有快照文件，预读磁盘 Hash 避免重启写盘
            if self._last_snapshot_hash is None and os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f_exist:
                        exist_data = json.load(f_exist)
                    self._last_snapshot_hash = self._compute_dict_hash(exist_data)
                except Exception:
                    pass

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
            
            # 数据变动智能比对: 数据完全未变时跳过写盘，避免无谓磁盘读写与 IO 开销
            current_hash = self._compute_dict_hash(snapshot_data)
            if not force and current_hash and current_hash == self._last_snapshot_hash:
                return True

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, indent=2)
            
            self._last_snapshot_hash = current_hash
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
            filename = f"daily_summary_{today_str}.json"
            filepath = os.path.join(self.log_dir, filename)

            # 【🛡️ 冷启动磁盘总结预载入】若内存锁为空但磁盘已存在今日总结报告，瞬间载入其 Hash 与日期锁
            if self._last_summary_date is None and os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f_exist:
                        exist_data = json.load(f_exist)
                    self._last_summary_hash = self._compute_dict_hash(exist_data)
                    self._last_summary_date = today_str
                except Exception:
                    pass

            # 【🛡️ 终盘总结单日独占锁】同一交易日盘后总结报告若已保存过 (且无 force 强行指定)，则 0ms 跳过
            if not force and self._last_summary_date == today_str:
                return True
            
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
            
            # 智能数据变动比对：如果与上次写盘内容完全一致（且非 force 强制），则零写盘零刷屏
            current_hash = self._compute_dict_hash(summary)
            if not force and current_hash and current_hash == self._last_summary_hash:
                return True

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)

            self._last_summary_hash = current_hash
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
        """清理旧有的废弃 timestamp 快照与超过 MAX_HISTORY_DAYS 天的历史总结"""
        today = datetime.date.today()
        cutoff = today - datetime.timedelta(days=self.MAX_HISTORY_DAYS)
        cutoff_str = cutoff.strftime('%Y%m%d')
        
        try:
            # 1. 彻底清扫散落的旧 signal_ledger_*.json 带有 HHMM 时间戳的垃圾备份
            for filepath in glob.glob(os.path.join(self.log_dir, 'signal_ledger_*.json')):
                basename = os.path.basename(filepath)
                if basename == 'signal_ledger_latest.json':
                    continue
                # 删除带有时间戳的旧散落备份
                try:
                    os.remove(filepath)
                    print(f"[SessionSnapshot] 自动清理废弃时间戳备份: {basename}")
                except Exception:
                    pass

            # 2. 清理超过 5 天的每日总结历史 daily_summary_*.json
            for filepath in glob.glob(os.path.join(self.log_dir, 'daily_summary_*.json')):
                basename = os.path.basename(filepath)
                parts = basename.replace('.json', '').split('_')
                for part in parts:
                    if len(part) == 8 and part.isdigit():
                        if part < cutoff_str:
                            try:
                                os.remove(filepath)
                                print(f"[SessionSnapshot] 清理过期总结文件: {basename}")
                            except Exception:
                                pass
                        break
        except Exception as e:
            print(f"[SessionSnapshot] Error cleaning old snapshots: {e}")
