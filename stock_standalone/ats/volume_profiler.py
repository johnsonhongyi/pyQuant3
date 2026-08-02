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
    """单只股票的量能与形态画像"""
    
    def __init__(self, code):
        self.code = code
        self.consecutive_shrink_days = 0    # 连续缩量天数
        self.first_surge_ts = None           # 当日首次放量突破时间戳
        self.first_surge_vol_ratio = 0.0     # 首次放量时的量比
        self.intraday_vol_snapshots = []     # 盘中量能快照 [(timestamp, vol_ratio)]
        self.volume_score = 0.0              # 综合量能评分
        self._last_calc_date = None
        
        # 连涨与板块联动新增属性
        self.recent_up_days_3d = 0           # 近3日收涨天数 (前三天连阳度)
        self.consecutive_up_days = 0         # 连涨天数
        self.sector = None                  # 所属主板块
        self.is_sector_leader = False        # 是否是板块领涨龙头
        self.is_sector_follower = False      # 是否是板块跟风者
        self.sector_leader_code = None       # 板块龙头股票代码
        
        # 多日阶梯底座与生命周期演进 (1-2日底座企稳 -> 3-4日分时主升加速)
        self.has_staircase_base = False      # 是否具备阶梯底座
        self.staircase_days = 0              # 阶梯抬升天数
        self.lifecycle_phase = 'NORMAL'      # '1-2D_BASE' / '3-4D_LAUNCH' / 'NORMAL'
        self.vwap_slope = 0.0                # 分时均价线上移倾角
        self.is_sector_resonance = False     # 是否处于板块同向微异动共振中
    
    def to_dict(self):
        return {
            'code': self.code,
            'consecutive_shrink_days': self.consecutive_shrink_days,
            'first_surge_ts': self.first_surge_ts,
            'first_surge_vol_ratio': self.first_surge_vol_ratio,
            'volume_score': self.volume_score,
            'recent_up_days_3d': self.recent_up_days_3d,
            'consecutive_up_days': self.consecutive_up_days,
            'sector': self.sector,
            'is_sector_leader': self.is_sector_leader,
            'is_sector_follower': self.is_sector_follower,
            'sector_leader_code': self.sector_leader_code,
            'has_staircase_base': self.has_staircase_base,
            'staircase_days': self.staircase_days,
            'lifecycle_phase': self.lifecycle_phase,
            'vwap_slope': self.vwap_slope,
            'is_sector_resonance': self.is_sector_resonance,
        }


class SectorMomentum:
    """板块动能画像 — 维护板块龙头与跟风联动的状态"""
    
    def __init__(self, name):
        self.name = name
        self.leader_code = None            # 板块内的带队龙头代码
        self.leader_score = 0.0            # 龙头的量能评分
        self.leader_first_seen_ts = None   # 龙头首次放量突破时间
        self.active_count = 0              # 板块当日活跃的信号标的数


class VolumeProfiler:
    """量能画像器 — 后台静默积累股票量能时序与板块联动统计"""
    
    SURGE_THRESHOLD = 1.3   # 量比超过此值视为放量
    MAX_SNAPSHOTS = 240     # 最多保留 240 个分钟级快照 (4小时交易时间)
    
    def __init__(self):
        self.profiles = {}  # {code: StockVolumeProfile}
        self.market_context = MarketVolumeContext()
        self.sectors = {}   # {sector_name: SectorMomentum}
    
    def update_market_context(self, df_all):
        """更新大盘量能环境上下文"""
        if df_all is not None and not df_all.empty:
            self.market_context.update(df_all)
    
    def update_profile(self, code, row):
        """更新单只股票的量能与历史形态画像
        
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
        
        # 1. 提取板块名称 (解析 category 列，如 "国防军工;地面兵装;..." -> "国防军工")
        sector_name = None
        category = row.get('category', row.get('hy', row.get('sector')))
        if category and isinstance(category, str) and category.strip():
            sector_name = category.split(';')[0].split('-')[0].strip()
        profile.sector = sector_name
        
        # 2. 每日首次更新时计算多天历史形态
        if profile._last_calc_date != today_str:
            profile._last_calc_date = today_str
            profile.first_surge_ts = None
            profile.first_surge_vol_ratio = 0.0
            profile.intraday_vol_snapshots = []
            
            # 计算连续缩量天数
            profile.consecutive_shrink_days = self._calc_consecutive_shrink_days(row)
            
            # 计算前三天连阳收涨度与连涨天数
            profile.recent_up_days_3d = self._calc_recent_up_days_3d(row)
            profile.consecutive_up_days = self._calc_consecutive_up_days(row)

            # 计算多日阶梯底座与生命周期阶段 (1-2日企稳 -> 3-4日分时主升)
            has_base, days, phase = self._calc_staircase_base(row)
            profile.has_staircase_base = has_base
            profile.staircase_days = days
            profile.lifecycle_phase = phase
        
        # 3. 获取当前量比
        vol_ratio = 1.0
        v_val = row.get('volume_ratio') if 'volume_ratio' in row else row.get('vol_ratio')
        if v_val is not None:
            try:
                vol_ratio = float(v_val)
            except (TypeError, ValueError):
                pass
        
        # 4. 记录首次放量时间点
        if profile.first_surge_ts is None and vol_ratio >= self.SURGE_THRESHOLD:
            profile.first_surge_ts = now
            profile.first_surge_vol_ratio = vol_ratio
        
        # 追加盘中量能快照 (限制总数)
        if len(profile.intraday_vol_snapshots) < self.MAX_SNAPSHOTS:
            # 避免过于频繁的快照 (至少间隔 30 秒)
            if not profile.intraday_vol_snapshots or (now - profile.intraday_vol_snapshots[-1][0]) >= 30:
                profile.intraday_vol_snapshots.append((now, vol_ratio))
        
        # 5. 计算综合量能评分 (后面再进行板块分析修正)
        profile.volume_score = self._compute_volume_score(profile, vol_ratio)
    
    def _calc_consecutive_shrink_days(self, row):
        """计算连续缩量天数 (基于 lastv1d..lastv9d)"""
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

    def _calc_recent_up_days_3d(self, row):
        """计算前 3 个交易日中收阳（收涨）的天数 (连阳度)"""
        prices = []
        for i in range(1, 5):
            col = f'lastp{i}d'
            try:
                p = float(row.get(col, 0))
                if p > 0:
                    prices.append(p)
            except (TypeError, ValueError):
                break
        if len(prices) < 2:
            return 0
        
        up_count = 0
        if prices[0] > prices[1]: up_count += 1
        if len(prices) >= 3 and prices[1] > prices[2]: up_count += 1
        if len(prices) >= 4 and prices[2] > prices[3]: up_count += 1
        return up_count

    def _calc_consecutive_up_days(self, row):
        """计算连涨天数"""
        prices = []
        for i in range(1, 10):
            col = f'lastp{i}d'
            try:
                p = float(row.get(col, 0))
                if p > 0:
                    prices.append(p)
            except (TypeError, ValueError):
                break
        if not prices:
            return 0
        
        yesterday_ups = 0
        for i in range(len(prices) - 1):
            if prices[i] > prices[i+1]:
                yesterday_ups += 1
            else:
                break
                
        # 结合今日当前涨幅 (当前价是否大于昨天收盘价)
        try:
            current_close = float(row.get('close', row.get('price', 0.0)))
            if current_close > prices[0]:
                return yesterday_ups + 1
        except:
            pass
        return yesterday_ups

    def _calc_staircase_base(self, row):
        """计算多日阶梯抬升底座与生命周期演进阶段 (1-2日底座企稳 -> 3-4日分时主升加速)"""
        try:
            l1 = float(row.get('lastl1d', 0))
            l2 = float(row.get('lastl2d', 0))
            l3 = float(row.get('lastl3d', 0))
            h1 = float(row.get('lasth1d', 0))
            h2 = float(row.get('lasth2d', 0))
            p1 = float(row.get('lastp1d', 0))
            p2 = float(row.get('lastp2d', 0))
            v1 = float(row.get('lastv1d', 0))
            v2 = float(row.get('lastv2d', 0))
            
            staircase_days = 0
            if l1 > 0 and l2 > 0 and l1 >= 0.98 * l2:
                staircase_days += 1
                if l3 > 0 and l2 >= 0.98 * l3:
                    staircase_days += 1

            has_base = (
                staircase_days >= 1 and
                (h1 >= 0.985 * h2 or p1 >= 0.985 * p2) and
                (v1 <= 1.20 * v2 if (v1 > 0 and v2 > 0) else True)
            )

            phase = 'NORMAL'
            if has_base:
                if staircase_days <= 2:
                    phase = '1-2D_BASE'
                else:
                    phase = '3-4D_LAUNCH'

            return has_base, staircase_days, phase
        except Exception:
            return False, 0, 'NORMAL'
    
    def analyze_sector_resonance(self, active_codes=None):
        """核心重构: 板块联动分析，标记龙头与跟风关系"""
        self.sectors.clear()
        
        # 1. 聚合个股到板块
        for code, profile in self.profiles.items():
            if active_codes is not None and code not in active_codes:
                continue
            sec = profile.sector
            if not sec:
                continue
                
            if sec not in self.sectors:
                self.sectors[sec] = SectorMomentum(sec)
            
            sec_momentum = self.sectors[sec]
            sec_momentum.active_count += 1
            
            # 认领板块内首发最强（首次放量最早且量能分最高）的股票为带队龙头
            vol_score = profile.volume_score
            t_self = profile.first_surge_ts
            
            if sec_momentum.leader_code is None:
                sec_momentum.leader_code = code
                sec_momentum.leader_score = vol_score
                sec_momentum.leader_first_seen_ts = t_self
            else:
                t_leader = sec_momentum.leader_first_seen_ts
                is_better = False
                
                if t_self is not None and t_leader is not None:
                    if t_self < t_leader - 30:  # 提前 30 秒以上启动为优
                        is_better = True
                    elif abs(t_self - t_leader) <= 120 and vol_score > sec_momentum.leader_score:
                        # 2分钟内同时启动，看量能分强弱
                        is_better = True
                elif t_self is not None:
                    is_better = True
                    
                if is_better:
                    sec_momentum.leader_code = code
                    sec_momentum.leader_score = vol_score
                    sec_momentum.leader_first_seen_ts = t_self
                    
        # 2. 标记跟风与龙头的加权关系
        for code, profile in self.profiles.items():
            sec = profile.sector
            if not sec or sec not in self.sectors:
                profile.is_sector_leader = False
                profile.is_sector_follower = False
                profile.sector_leader_code = None
                continue
                
            sec_momentum = self.sectors[sec]
            profile.sector_leader_code = sec_momentum.leader_code
            
            if sec_momentum.leader_code == code:
                profile.is_sector_leader = True
                profile.is_sector_follower = False
            else:
                profile.is_sector_leader = False
                # 如果板块有龙头已经率先启动，且此股票自己也启动了，启动时间在大哥之后，视为跟风者
                if (sec_momentum.active_count > 1 and 
                    sec_momentum.leader_first_seen_ts is not None and 
                    profile.first_surge_ts is not None and 
                    profile.first_surge_ts > sec_momentum.leader_first_seen_ts + 5):  # 滞后5秒以上启动为跟风
                    profile.is_sector_follower = True
                else:
                    profile.is_sector_follower = False
                    
            # 标记板块同向微异动共振 (同板块内有>=2只标的活跃)
            if sec_momentum.active_count >= 2:
                profile.is_sector_resonance = True
            else:
                profile.is_sector_resonance = False

            # 重新计算经过板块加权修正的量能评分
            profile.volume_score = self._compute_volume_score(profile, profile.first_surge_vol_ratio or 1.0)
    
    def _compute_volume_score(self, profile, current_vol_ratio):
        """综合量能评分 (0-100)"""
        score = 0.0
        
        # 因子 1: 连续缩量天数 (最多贡献 35 分)
        score += min(35.0, profile.consecutive_shrink_days * 8.0)
        
        # 因子 2: 首次放量时间 (最多贡献 20 分)
        if profile.first_surge_ts:
            import datetime
            surge_time = datetime.datetime.fromtimestamp(profile.first_surge_ts)
            hour, minute = surge_time.hour, surge_time.minute
            time_minutes = hour * 60 + minute
            
            if time_minutes <= 570:    # 09:30 前
                score += 20.0
            elif time_minutes <= 600:  # 09:30-10:00 (黄金半小时)
                score += 20.0 - (time_minutes - 570) * 0.4
            elif time_minutes <= 690:  # 10:00-11:30
                score += 8.0 - (time_minutes - 600) * 0.08
            else:
                score += 4.0
        
        # 因子 3: 放量幅度 (最多贡献 15 分)
        surge_ratio = max(current_vol_ratio, profile.first_surge_vol_ratio)
        if surge_ratio > 1.0:
            score += min(15.0, (surge_ratio - 1.0) * 10.0)
        
        # 因子 4: 大盘量能环境加成 (最多贡献 10 分)
        if self.market_context.is_rebound_from_shrink:
            score += min(10.0, self.market_context.rebound_quality * 0.10)
            
        # ==============================================================
        # 核心新增: 板块联动共振加成、多日阶梯底座与生命周期演进加分
        # ==============================================================
        
        # 阶梯底座与生命周期加分 (1-2日底座企稳 + 3-4日分时主升): 贡献最多 15 分
        if getattr(profile, 'has_staircase_base', False):
            score += 10.0
        if getattr(profile, 'lifecycle_phase', '') == '3-4D_LAUNCH':
            score += 5.0

        # 板块微异动共振加分 (同板块>=2只标的步调一致): 额外加 8 分
        if getattr(profile, 'is_sector_resonance', False):
            score += 8.0

        # 连阳抗跌加分 (长城军工启动前连阳抗跌多阳): 3连阳/多日收涨 贡献最多 10 分
        score += min(10.0, profile.recent_up_days_3d * 3.3)
        if profile.consecutive_up_days >= 3:
            score += 2.0  # 3天以上连涨额外加分
            
        # 板块联动提权
        if profile.is_sector_leader:
            # 领涨龙头且板块有多个成员活跃 (带队龙头): 额外加 10 分
            if self.sectors.get(profile.sector) and self.sectors[profile.sector].active_count > 1:
                score += 10.0
        elif profile.is_sector_follower:
            # 小弟被大哥带队加速跟风启动: 额外加 8 分共振分，防止小弟在池中因微弱分差滑落
            score += 8.0
        
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


class MarketContextGuard:
    """大盘整体安全度大闸引擎
    
    实时感知全市场温度、涨跌家数比与大盘均线状态，划分大盘三阶状态:
    - FREEZING (冰点杀跌期): 大盘极度下挫, 跌家数 > 3200 或大盘大幅下杀
    - REBOUND  (企稳反弹期): 大盘企稳或平稳震荡
    - BULL     (顺风多头期): 大盘大涨放量
    """
    
    STAGE_FREEZING = 'FREEZING'
    STAGE_REBOUND  = 'REBOUND'
    STAGE_BULL     = 'BULL'
    
    def __init__(self):
        self.stage = self.STAGE_REBOUND
        self.market_temperature = 50.0
        self.up_ratio = 0.5
        self.guard_factor = 1.0
        
    def update_context(self, df_all):
        if df_all is None or df_all.empty:
            return
            
        up_count = 0
        total_count = len(df_all)
        if 'percent' in df_all.columns:
            up_count = (df_all['percent'] > 0).sum()
            self.up_ratio = up_count / max(1, total_count)
            
        sh_pct = 0.0
        for idx_code in ['sh000001', '1.000001', '000001.SH']:
            if idx_code in df_all.index:
                try:
                    sh_pct = float(df_all.loc[idx_code, 'percent'])
                except (TypeError, ValueError):
                    pass
                break
                
        # 判定大盘阶段
        if self.up_ratio < 0.28 or sh_pct < -1.2:
            self.stage = self.STAGE_FREEZING
            self.guard_factor = 0.0  # 硬性拦截
        elif self.up_ratio > 0.65 or sh_pct > 1.0:
            self.stage = self.STAGE_BULL
            self.guard_factor = 1.25 # 提权放行
        else:
            self.stage = self.STAGE_REBOUND
            self.guard_factor = 0.90
            
        self.market_temperature = round(self.up_ratio * 100.0, 1)

    def allow_trade(self, specialty_score=0.0, is_fav=False):
        """判断是否允许交易买入信号"""
        if is_fav:
            return True
        if self.stage == self.STAGE_FREEZING:
            # 冰点杀跌期只允许特异性打分极其优异 (>= 85 分) 的顶级标的
            return specialty_score >= 85.0
        return True

