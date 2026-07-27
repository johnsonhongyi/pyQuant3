# -*- coding: utf-8 -*-
"""
ATS Signal Ledger
信号账本 — 增量写入、时间锚定、优先级评分的核心信号管理器

核心理念: "快一步步步快"
- 信号一旦发现即锁定，不因行情波动被冲掉
- 首次发现时间戳决定优先级（竞价 > 黄金半小时 > 盘中 > 午后）
- 三级池子（RADAR/WATCH/TRADE）稳定展示，不快速流动

替代原有 UniverseManager.run_pipeline_filtering() 的全量重算逻辑
"""

import time
import datetime


# ======================================================================
# 时段常量与优先级映射
# ======================================================================

PHASE_AUCTION    = 'AUCTION'    # 09:15-09:30 集合竞价
PHASE_GOLDEN     = 'GOLDEN'     # 09:30-10:00 黄金半小时
PHASE_MORNING    = 'MORNING'    # 10:00-11:30 上午盘中
PHASE_AFTERNOON  = 'AFTERNOON'  # 13:00-15:00 午后
PHASE_PREMARKET  = 'PREMARKET'  # 其他时段

# 时段标签（UI 展示用）
PHASE_LABELS = {
    PHASE_AUCTION:   '🔔 竞价先手',
    PHASE_GOLDEN:    '🥇 黄金早盘',
    PHASE_MORNING:   '🥈 盘中跟进',
    PHASE_AFTERNOON: '📋 午后补充',
    PHASE_PREMARKET: '⏳ 盘前预备',
}


def _detect_phase(ts=None):
    """根据时间戳判断当前交易时段

    Args:
        ts: Unix 时间戳，None 则使用当前时间

    Returns:
        str: 时段常量
    """
    if ts is None:
        ts = time.time()

    dt = datetime.datetime.fromtimestamp(ts)
    hhmm = dt.hour * 100 + dt.minute

    if 915 <= hhmm < 930:
        return PHASE_AUCTION
    elif 930 <= hhmm < 1000:
        return PHASE_GOLDEN
    elif 1000 <= hhmm < 1130:
        return PHASE_MORNING
    elif 1300 <= hhmm < 1500:
        return PHASE_AFTERNOON
    else:
        return PHASE_PREMARKET


def _compute_time_score(phase, ts=None):
    """计算时间优先级基础分

    Args:
        phase: 时段标识
        ts: 首次发现时间戳

    Returns:
        float: 时间评分 (0-100)
    """
    if phase == PHASE_AUCTION:
        return 100.0

    if ts is None:
        ts = time.time()

    dt = datetime.datetime.fromtimestamp(ts)
    minutes_of_day = dt.hour * 60 + dt.minute

    if phase == PHASE_GOLDEN:
        # 09:30 = 570 分钟, 10:00 = 600 分钟
        elapsed = max(0, minutes_of_day - 570)
        return max(70.0, 95.0 - elapsed * 0.83)  # 95 → 70 over 30 minutes

    elif phase == PHASE_MORNING:
        elapsed = max(0, minutes_of_day - 600)
        return max(30.0, 60.0 - elapsed * 0.33)

    elif phase == PHASE_AFTERNOON:
        elapsed = max(0, minutes_of_day - 780)  # 13:00 = 780
        return max(10.0, 40.0 - elapsed * 0.25)

    return 20.0  # PREMARKET default


# ======================================================================
# SignalEntry — 单只股票的信号条目
# ======================================================================

class SignalEntry:
    """单只股票的完整信号记录"""

    __slots__ = [
        'code', 'name',
        'first_seen_ts', 'first_seen_price', 'first_seen_pct', 'first_seen_phase',
        'latest_price', 'latest_pct', 'latest_deviation',
        'volume_score', 'priority_score',
        'tier', 'is_locked',
        'state_history',
        '_date_str',
    ]

    def __init__(self, code, name, price, pct, deviation, phase, ts=None):
        self.code = code
        self.name = name

        # 首次发现 — 锁定后不变
        self.first_seen_ts = ts or time.time()
        self.first_seen_price = price
        self.first_seen_pct = pct
        self.first_seen_phase = phase

        # 最新状态 — 实时更新
        self.latest_price = price
        self.latest_pct = pct
        self.latest_deviation = deviation

        # 评分
        self.volume_score = 0.0
        self.priority_score = 0.0

        # 层级与锁定
        self.tier = 'RADAR'       # RADAR / WATCH / TRADE / INACTIVE
        self.is_locked = False

        # 状态变更历史
        self.state_history = [{
            'ts': self.first_seen_ts,
            'action': 'DISCOVERED',
            'phase': phase,
            'price': price,
            'pct': pct,
        }]

        self._date_str = datetime.date.today().strftime('%Y-%m-%d')

    def update_latest(self, price, pct, deviation):
        """更新最新实时数据（不改变首次发现时间和层级）"""
        self.latest_price = price
        self.latest_pct = pct
        self.latest_deviation = deviation

    def promote(self, new_tier, reason=''):
        """晋级到更高层级

        只升不降原则（除非手动降级或 INACTIVE）
        """
        tier_rank = {'INACTIVE': 0, 'RADAR': 1, 'WATCH': 2, 'TRADE': 3}
        current_rank = tier_rank.get(self.tier, 0)
        new_rank = tier_rank.get(new_tier, 0)

        if new_rank > current_rank or new_tier == 'INACTIVE':
            old_tier = self.tier
            self.tier = new_tier
            self.state_history.append({
                'ts': time.time(),
                'action': f'PROMOTED_{old_tier}_TO_{new_tier}',
                'reason': reason,
                'price': self.latest_price,
                'pct': self.latest_pct,
            })

    def to_dict(self):
        """序列化为字典（用于快照持久化）"""
        return {
            'code': self.code,
            'name': self.name,
            'first_seen_ts': self.first_seen_ts,
            'first_seen_price': self.first_seen_price,
            'first_seen_pct': self.first_seen_pct,
            'first_seen_phase': self.first_seen_phase,
            'first_seen_time': datetime.datetime.fromtimestamp(self.first_seen_ts).strftime('%H:%M:%S'),
            'latest_price': self.latest_price,
            'latest_pct': self.latest_pct,
            'latest_deviation': self.latest_deviation,
            'volume_score': self.volume_score,
            'priority_score': self.priority_score,
            'tier': self.tier,
            'is_locked': self.is_locked,
            'date': self._date_str,
        }


# ======================================================================
# SignalLedger — 信号账本主体
# ======================================================================

class SignalLedger:
    """信号账本 — 增量写入、只增不删的信号管理核心

    核心规则:
    1. record_signal(): 新信号写入，已存在仅更新最新价格
    2. 信号一旦写入，永不物理删除（仅标记 INACTIVE）
    3. 优先级由 first_seen_ts（首次发现时间）主导
    4. 三级池子（RADAR/WATCH/TRADE）从账本读取，稳定展示
    """

    # 偏离度筛选范围
    DEVIATION_MIN = -2.5    # MA20 偏离度下限
    DEVIATION_MAX = 4.0     # MA20 偏离度上限
    DEVIATION_EVICT = -6.0  # 跌破此值标记为 INACTIVE

    # 池子展示上限
    RADAR_DISPLAY_LIMIT = 30
    WATCH_DISPLAY_LIMIT = 15

    # 自动晋级阈值
    WATCH_VOL_RATIO_MIN = 1.2
    WATCH_PCT_MIN_WITH_VOL = -1.0
    WATCH_PCT_DIRECT = 1.5
    WATCH_DFF_DIRECT = 1.0

    def __init__(self):
        self.entries = {}       # {code: SignalEntry}
        self._today_str = None
        self._signal_count = 0  # 当日发现信号总数

    def _ensure_daily_reset(self):
        """每日自动重置（保留 WATCH 和 TRADE 信号用于跨日追踪）"""
        today = datetime.date.today().strftime('%Y-%m-%d')
        if self._today_str == today:
            return

        self._today_str = today
        old_count = len(self.entries)

        # 保留 WATCH 和 TRADE 层级的跨日信号，RADAR 和 INACTIVE 清除
        preserved = {}
        for code, entry in self.entries.items():
            if entry.tier in ('WATCH', 'TRADE'):
                # 降级为 RADAR 重新观察
                entry.tier = 'RADAR'
                entry.state_history.append({
                    'ts': time.time(),
                    'action': 'DAILY_RESET_DEMOTED',
                    'reason': '跨日降级至RADAR重新观察',
                })
                preserved[code] = entry

        self.entries = preserved
        self._signal_count = 0

        if old_count > 0:
            print(f"[SignalLedger] 每日重置: {old_count} → {len(preserved)} (保留 WATCH/TRADE 跨日追踪)")

    def load_previous_signals(self, prev_signals_dict):
        """从昨日盘中快照/总结载入历史信号 (用于跨日恢复与追踪)

        Args:
            prev_signals_dict: {code: entry_dict} 来自 SessionSnapshot
        """
        self._ensure_daily_reset()
        if not prev_signals_dict:
            return

        loaded_count = 0
        now = time.time()
        for code, data in prev_signals_dict.items():
            if code in self.entries:
                continue

            name = data.get('name', '未知')
            price = float(data.get('latest_price', data.get('first_seen_price', 0.0)))
            pct = float(data.get('latest_pct', data.get('first_seen_pct', 0.0)))
            deviation = float(data.get('latest_deviation', 0.0))

            # 跨日继承载入为 RADAR 层级重新观察，时间戳重置为当前盘前时间
            entry = SignalEntry(
                code=code,
                name=name,
                price=price,
                pct=pct,
                deviation=deviation,
                phase=PHASE_PREMARKET,
                ts=now
            )
            entry.tier = 'RADAR'
            entry.state_history.append({
                'ts': now,
                'action': 'RESTORED_FROM_PREVIOUS_DAY',
                'reason': f"从昨日快照继承 ({data.get('tier', 'WATCH')}级别)",
            })
            entry.priority_score = self._compute_priority(entry)
            self.entries[code] = entry
            loaded_count += 1

        if loaded_count > 0:
            print(f"[SignalLedger] 跨日继承: 成功恢复 {loaded_count} 只昨日 WATCH/TRADE 精选标的")

    def record_signal(self, code, name, price, pct, deviation, row=None, volume_score=0.0):
        """发现新信号或更新已有信号

        核心逻辑:
        - 新信号 → 写入账本，锁定首次发现时间
        - 已有信号 → 仅更新最新价格/涨幅，不改变首次发现时间

        Args:
            code: 股票代码
            name: 股票名称
            price: 当前价格
            pct: 当前涨跌幅
            deviation: MA20 偏离度
            row: 行情数据行（可选，用于提取量比等数据）
            volume_score: 量能评分（由 VolumeProfiler 计算）

        Returns:
            SignalEntry or None
        """
        self._ensure_daily_reset()

        # 获取重点关注集合
        fav_stocks = set()
        try:
            from global_favorites import GlobalFavoriteManager
            fav_stocks = GlobalFavoriteManager().get_favorite_stocks()
        except Exception:
            pass
        is_fav = str(code).strip() in fav_stocks

        if not name or name in ('未知', '重点标的', ''):
            try:
                from JohnsonUtil import commonTips as cct
                n_str = cct.get_stock_name(code)
                if n_str and str(n_str).strip() and str(n_str).strip() != str(code):
                    name = str(n_str).strip()
            except Exception:
                pass

        # 偏离度筛选（重点关注股票不受此限制，防止消失）
        if not is_fav and (deviation < self.DEVIATION_MIN or deviation > self.DEVIATION_MAX):
            # 已存在的非关注信号如果严重破位，标记为 INACTIVE
            if code in self.entries and deviation < self.DEVIATION_EVICT:
                entry = self.entries[code]
                if entry.tier not in ('TRADE',):  # TRADE 级别不自动降级
                    entry.promote('INACTIVE', reason=f'偏离度 {deviation:.2f}% 严重破位')
            return None

        if code in self.entries:
            # 已存在 → 仅更新最新数据，不改变首次发现时间和层级
            entry = self.entries[code]
            entry.update_latest(price, pct, deviation)
            entry.volume_score = volume_score

            # 如果之前是 INACTIVE 但现在回到范围内，或被设为重点关注，恢复为 RADAR/WATCH
            if entry.tier == 'INACTIVE':
                entry.tier = 'WATCH' if is_fav else 'RADAR'
                entry.state_history.append({
                    'ts': time.time(),
                    'action': 'REACTIVATED',
                    'reason': f'重点关注或偏离度回到范围: {deviation:.2f}%',
                })
            elif is_fav and entry.tier == 'RADAR':
                entry.promote('WATCH', reason='⭐ 设为重点关注自动晋级')

            # 重新计算优先级评分（使用首次发现时间，确保早期信号优先级不变）
            entry.priority_score = self._compute_priority(entry)

            # 检查自动晋级
            if entry.tier == 'RADAR':
                self._check_auto_promote(entry, row)

            return entry
        else:
            # 新信号 → 写入账本
            phase = _detect_phase()
            entry = SignalEntry(code, name, price, pct, deviation, phase)
            if is_fav:
                entry.tier = 'WATCH'
            entry.volume_score = volume_score
            entry.priority_score = self._compute_priority(entry)

            self.entries[code] = entry
            self._signal_count += 1

            # 检查自动晋级
            if row is not None and entry.tier == 'RADAR':
                self._check_auto_promote(entry, row)

            return entry

    def _compute_priority(self, entry):
        """计算综合优先级评分

        priority = time_score × 0.45 + volume_score × 0.30
                 + deviation_score × 0.15 + momentum_score × 0.10
                 + (is_fav ? 200.0 : 0.0)

        Returns:
            float: 优先级评分 (重点关注股票可突破 100)
        """
        # 时间分 (0-100)
        time_score = _compute_time_score(entry.first_seen_phase, entry.first_seen_ts)

        # 量能分 (0-100, 由 VolumeProfiler 外部提供)
        vol_score = min(100.0, entry.volume_score)

        # 偏离度分 (越贴近 MA20 越高)
        dev_abs = abs(entry.latest_deviation) if entry.latest_deviation is not None else 5.0
        deviation_score = max(0.0, 100.0 - dev_abs * 20.0)

        # 动量分 (涨幅与逆势强度)
        pct = entry.latest_pct if entry.latest_pct else 0.0
        momentum_score = min(100.0, max(0.0, pct * 15.0))

        # 重点关注置顶加权
        fav_boost = 0.0
        try:
            from global_favorites import GlobalFavoriteManager
            if str(entry.code).strip() in GlobalFavoriteManager().get_favorite_stocks():
                fav_boost = 200.0
        except Exception:
            pass

        # 加权求和
        priority = (
            time_score * 0.45 +
            vol_score * 0.30 +
            deviation_score * 0.15 +
            momentum_score * 0.10 +
            fav_boost
        )

        return round(priority, 2)

    def _check_auto_promote(self, entry, row):
        """检查是否满足从 RADAR 自动晋级到 WATCH 的条件

        晋级条件（满足任一）:
        1. 量比 >= 1.2 且涨幅 >= -1.0%
        2. 涨幅 >= 1.5% 且 DFF > 1.0
        3. 竞价/黄金时段信号且涨幅 > 0（时段加分）
        """
        if entry.tier != 'RADAR' or row is None:
            return

        vol_ratio = 1.0
        dff_val = 0.0

        if row is not None:
            v_val = row.get('volume_ratio') if 'volume_ratio' in row else row.get('vol_ratio')
            if v_val is not None:
                try:
                    vol_ratio = float(v_val)
                except (TypeError, ValueError):
                    pass

            d_val = row.get('dff')
            if d_val is not None:
                try:
                    dff_val = float(d_val)
                except (TypeError, ValueError):
                    pass

        pct = entry.latest_pct

        should_promote = False
        reason = ''

        # 条件 1: 放量异动
        if vol_ratio >= self.WATCH_VOL_RATIO_MIN and pct >= self.WATCH_PCT_MIN_WITH_VOL:
            should_promote = True
            reason = f'量比 {vol_ratio:.1f} 放量异动 | 涨幅 {pct:+.2f}%'

        # 条件 2: 强势动量
        elif pct >= self.WATCH_PCT_DIRECT and dff_val > self.WATCH_DFF_DIRECT:
            should_promote = True
            reason = f'涨幅 {pct:+.2f}% 强势 | DFF {dff_val:.2f}'

        # 条件 3: 竞价/黄金时段 + 正涨幅
        elif entry.first_seen_phase in (PHASE_AUCTION, PHASE_GOLDEN) and pct > 0.5:
            should_promote = True
            reason = f'{PHASE_LABELS[entry.first_seen_phase]} 首批信号 | 涨幅 {pct:+.2f}%'

        if should_promote:
            entry.promote('WATCH', reason=reason)

    def get_sorted_pool(self, tier, limit=None):
        """获取指定层级的信号列表（按优先级降序排列）

        Args:
            tier: 'RADAR', 'WATCH', 'TRADE', 'INACTIVE'
            limit: 最大返回数量

        Returns:
            list[SignalEntry]: 按优先级排序的信号列表
        """
        pool = [e for e in self.entries.values() if e.tier == tier]
        pool.sort(key=lambda e: e.priority_score, reverse=True)

        if limit is not None:
            pool = pool[:limit]

        return pool

    def get_display_pools(self):
        """获取三级池的展示数据（用于 UI 渲染）

        Returns:
            tuple: (radar_list, watch_list, trade_list)
            每个列表的元素为 tuple: (code, name, price_str, pct_str, strategy, reason)
        """
        def _format_entry(entry):
            phase_label = PHASE_LABELS.get(entry.first_seen_phase, '⏳')
            first_time = datetime.datetime.fromtimestamp(entry.first_seen_ts).strftime('%H:%M')
            return (
                entry.code,
                entry.name or '未知',
                f"{entry.latest_price:.2f}",
                f"{entry.latest_pct:+.2f}%",
                f"{phase_label} [{first_time}]",
                f"优先级: {entry.priority_score:.0f} | 偏离: {entry.latest_deviation:+.1f}%"
            )

        radar_entries = self.get_sorted_pool('RADAR', limit=self.RADAR_DISPLAY_LIMIT)
        watch_entries = self.get_sorted_pool('WATCH', limit=self.WATCH_DISPLAY_LIMIT)
        trade_entries = self.get_sorted_pool('TRADE')

        radar_list = [_format_entry(e) for e in radar_entries]
        watch_list = [_format_entry(e) for e in watch_entries]
        trade_list = [_format_entry(e) for e in trade_entries]

        return radar_list, watch_list, trade_list

    def get_all_tracked_codes(self):
        """获取所有被追踪的股票代码（活跃状态）"""
        return [code for code, entry in self.entries.items()
                if entry.tier in ('RADAR', 'WATCH', 'TRADE')]

    def get_stats(self):
        """获取统计信息"""
        self._ensure_daily_reset()
        tier_counts = {}
        phase_counts = {}
        for entry in self.entries.values():
            tier_counts[entry.tier] = tier_counts.get(entry.tier, 0) + 1
            phase_counts[entry.first_seen_phase] = phase_counts.get(entry.first_seen_phase, 0) + 1

        return {
            'total': len(self.entries),
            'today_new': self._signal_count,
            'tiers': tier_counts,
            'phases': phase_counts,
        }
