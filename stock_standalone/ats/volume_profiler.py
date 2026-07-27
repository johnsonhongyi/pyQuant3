# -*- coding: utf-8 -*-
"""
ATS Volume Profiler
量能画像器 — 后台静默积累每只关注股票的量能时序画像

核心功能:
1. 统计个股连续缩量天数 (基于 lastv1d..lastv9d)
2. 记录当日首次放量突破的时间点
3. 计算盘中量能密度分布
4. 大盘量能环境感知 (连续缩量后反弹识别)
5. 综合量能评分
"""

import time


class MarketVolumeContext:
    """大盘量能环境上下文 — 判断当前是否处于缩量后反弹的关键时点"""
    
    def __init__(self):
        self.consecutive_market_shrink_days = 0  # 大盘连续缩量天数
        self.market_volume_ratio = 1.0           # 大盘当日量比
        self.is_rebound_from_shrink = False       # 是否处于缩量后反弹
        self.rebound_quality = 0.0                # 反弹质量评分 (0-100)
        self._last_update_date = None
    
    def update(self, df_all):
        """从全市场 DataFrame 更新大盘量能环境
        
        Args:
            df_all: 全市场实时行情 DataFrame, index=code
        """
        import datetime
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        
        # 避免同一天重复计算历史缩量天数
        if self._last_update_date == today_str:
            # 仅更新当日量比
            self._update_intraday_ratio(df_all)
            return
        
        self._last_update_date = today_str
        
        # 从上证指数行情中提取大盘量能数据
        sh_row = None
        for idx_code in ['sh000001', '1.000001', '000001.SH']:
            if idx_code in df_all.index:
                sh_row = df_all.loc[idx_code]
                break
        
        if sh_row is None:
            return
        
        # 计算连续缩量天数 (利用 lastv1d..lastv9d)
        shrink_days = 0
        prev_vol = None
        for i in range(1, 10):
            col = f'lastv{i}d'
            try:
                vol = float(sh_row.get(col, 0))
            except (TypeError, ValueError):
                break
            if vol <= 0:
                break
            if prev_vol is not None and vol > prev_vol:
                # vol at day i (older) > vol at day i-1 (newer) means newer day was smaller
                shrink_days += 1
            elif prev_vol is not None:
                break  # 量能没有持续缩小，中断
            prev_vol = vol
        
        self.consecutive_market_shrink_days = shrink_days
        self._update_intraday_ratio(df_all)
        
        # 判断是否处于缩量后反弹
        self.is_rebound_from_shrink = (
            self.consecutive_market_shrink_days >= 2 and 
            self.market_volume_ratio > 1.0
        )
        
        # 反弹质量评分
        if self.is_rebound_from_shrink:
            sh_pct = 0.0
            try:
                sh_pct = float(sh_row.get('percent', 0.0))
            except (TypeError, ValueError):
                pass
            self.rebound_quality = min(100.0, max(0.0,
                self.consecutive_market_shrink_days * 15 +  # 连续缩量天数越多越好
                max(0, sh_pct) * 10 +                       # 大盘涨幅越大越好
                max(0, self.market_volume_ratio - 1.0) * 30  # 放量幅度越大越好
            ))
        else:
            self.rebound_quality = 0.0
    
    def _update_intraday_ratio(self, df_all):
        """更新大盘当日量比"""
        for idx_code in ['sh000001', '1.000001', '000001.SH']:
            if idx_code in df_all.index:
                try:
                    self.market_volume_ratio = float(df_all.loc[idx_code].get('volume_ratio', 
                                                     df_all.loc[idx_code].get('vol_ratio', 1.0)))
                except (TypeError, ValueError):
                    pass
                break


class StockVolumeProfile:
    """单只股票的量能画像"""
    
    def __init__(self, code):
        self.code = code
        self.consecutive_shrink_days = 0    # 连续缩量天数
        self.first_surge_ts = None           # 当日首次放量突破时间戳
        self.first_surge_vol_ratio = 0.0     # 首次放量时的量比
        self.intraday_vol_snapshots = []     # 盘中量能快照 [(timestamp, vol_ratio)]
        self.volume_score = 0.0              # 综合量能评分
        self._last_calc_date = None
    
    def to_dict(self):
        return {
            'code': self.code,
            'consecutive_shrink_days': self.consecutive_shrink_days,
            'first_surge_ts': self.first_surge_ts,
            'first_surge_vol_ratio': self.first_surge_vol_ratio,
            'volume_score': self.volume_score,
        }


class VolumeProfiler:
    """量能画像器 — 后台静默积累股票量能时序统计"""
    
    SURGE_THRESHOLD = 1.3   # 量比超过此值视为放量
    MAX_SNAPSHOTS = 240     # 最多保留 240 个分钟级快照 (4小时交易时间)
    
    def __init__(self):
        self.profiles = {}  # {code: StockVolumeProfile}
        self.market_context = MarketVolumeContext()
    
    def update_market_context(self, df_all):
        """更新大盘量能环境上下文"""
        if df_all is not None and not df_all.empty:
            self.market_context.update(df_all)
    
    def update_profile(self, code, row):
        """更新单只股票的量能画像
        
        Args:
            code: 股票代码
            row: 行情数据行 (pandas Series or dict-like)
        """
        import datetime
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        
        if code not in self.profiles:
            self.profiles[code] = StockVolumeProfile(code)
        
        profile = self.profiles[code]
        now = time.time()
        
        # 每日首次更新时重新计算连续缩量天数
        if profile._last_calc_date != today_str:
            profile._last_calc_date = today_str
            profile.first_surge_ts = None
            profile.first_surge_vol_ratio = 0.0
            profile.intraday_vol_snapshots = []
            
            # 计算连续缩量天数
            profile.consecutive_shrink_days = self._calc_consecutive_shrink_days(row)
        
        # 获取当前量比
        vol_ratio = 1.0
        try:
            vol_ratio = float(row.get('volume_ratio', row.get('vol_ratio', 1.0)))
        except (TypeError, ValueError):
            pass
        
        # 记录首次放量时间点
        if profile.first_surge_ts is None and vol_ratio >= self.SURGE_THRESHOLD:
            profile.first_surge_ts = now
            profile.first_surge_vol_ratio = vol_ratio
        
        # 追加盘中量能快照 (限制总数)
        if len(profile.intraday_vol_snapshots) < self.MAX_SNAPSHOTS:
            # 避免过于频繁的快照 (至少间隔 30 秒)
            if not profile.intraday_vol_snapshots or (now - profile.intraday_vol_snapshots[-1][0]) >= 30:
                profile.intraday_vol_snapshots.append((now, vol_ratio))
        
        # 计算综合量能评分
        profile.volume_score = self._compute_volume_score(profile, vol_ratio)
    
    def _calc_consecutive_shrink_days(self, row):
        """计算连续缩量天数 (基于 lastv1d..lastv9d)
        
        lastv1d = 昨日成交量, lastv2d = 前日成交量, ...
        如果 lastv1d < lastv2d < lastv3d, 则连续缩量 2 天
        """
        volumes = []
        for i in range(1, 10):
            col = f'lastv{i}d'
            try:
                v = float(row.get(col, 0))
            except (TypeError, ValueError):
                break
            if v <= 0:
                break
            volumes.append(v)
        
        if len(volumes) < 2:
            return 0
        
        shrink_count = 0
        for i in range(len(volumes) - 1):
            if volumes[i] < volumes[i + 1]:  # 较近日 < 较远日 = 缩量
                shrink_count += 1
            else:
                break
        
        return shrink_count
    
    def _compute_volume_score(self, profile, current_vol_ratio):
        """综合量能评分 (0-100)
        
        评分因子:
        1. 连续缩量天数越多，说明洗盘越充分 → 高分
        2. 当日首次放量越早 → 高分 (早盘放量优于午后放量)
        3. 放量幅度越大 → 高分
        4. 大盘环境加成 (缩量后反弹)
        """
        score = 0.0
        
        # 因子 1: 连续缩量天数 (最多贡献 40 分)
        score += min(40.0, profile.consecutive_shrink_days * 10.0)
        
        # 因子 2: 首次放量时间 (最多贡献 25 分)
        if profile.first_surge_ts:
            import datetime
            surge_time = datetime.datetime.fromtimestamp(profile.first_surge_ts)
            hour, minute = surge_time.hour, surge_time.minute
            time_minutes = hour * 60 + minute  # 转为分钟
            
            if time_minutes <= 570:    # 09:30 之前 (竞价)
                score += 25.0
            elif time_minutes <= 600:  # 09:30-10:00 (黄金半小时)
                score += 25.0 - (time_minutes - 570) * 0.5
            elif time_minutes <= 690:  # 10:00-11:30
                score += 10.0 - (time_minutes - 600) * 0.1
            else:                      # 午后
                score += 5.0
        
        # 因子 3: 放量幅度 (最多贡献 20 分)
        surge_ratio = max(current_vol_ratio, profile.first_surge_vol_ratio)
        if surge_ratio > 1.0:
            score += min(20.0, (surge_ratio - 1.0) * 15.0)
        
        # 因子 4: 大盘环境加成 (最多贡献 15 分)
        if self.market_context.is_rebound_from_shrink:
            score += min(15.0, self.market_context.rebound_quality * 0.15)
        
        return min(100.0, max(0.0, score))
    
    def get_profile(self, code):
        """获取股票量能画像"""
        return self.profiles.get(code)
    
    def get_consecutive_shrink_days(self, code):
        """获取连续缩量天数"""
        p = self.profiles.get(code)
        return p.consecutive_shrink_days if p else 0
    
    def get_first_surge_time(self, code):
        """获取当日首次放量突破时间戳"""
        p = self.profiles.get(code)
        return p.first_surge_ts if p else None
    
    def get_volume_score(self, code):
        """获取综合量能评分"""
        p = self.profiles.get(code)
        return p.volume_score if p else 0.0
    
    def cleanup_stale(self, active_codes):
        """清理不再关注的股票画像，释放内存"""
        active_set = set(active_codes)
        stale = [c for c in self.profiles if c not in active_set]
        for c in stale:
            del self.profiles[c]
