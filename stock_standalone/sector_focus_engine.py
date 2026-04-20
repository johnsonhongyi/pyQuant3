# -*- coding: utf-8 -*-
"""
SectorFocusEngine — 盘中实时交易决策引擎  v2
==============================================
核心能力：
  1. SectorFocusMap   — 实时板块热力计算（竞价->盘中）
  2. StarFollowEngine — 龙头识别 + 同板块跟进股（每板块最多3只）
  3. IntradayPullbackDetector — 回踩买点检测（四种形态）
  4. DecisionQueue    — 交易决策优先级队列

v2 改进：
  - inject_from_detector() — 直接从 BiddingMomentumDetector 注入完整
    板块+个股数据（score/pct/pct_diff/dff/klines/vwap），彻底打通数据链
  - SectorFocusMap 新增 inject_detector_sectors() 优先采用 detector 已
    计算好的板块图，权重 W_BIDDING 改由板块 board_score 驱动
  - _scan_one 使用真实 kline 序列提取最近5分钟价格，替代伪数据
  - comparison_interval 默认 60 分钟（与面板用户习惯对齐）
  - 兼容旧接口：inject_bidding / inject_realtime / inject_ext_data 全保留

设计原则：
  - 后台线程全量计算，UI 只读结果
  - 不破坏现有任何接口
  - 无任何 raise Exception（降级返回空结果）
  - Windows 多进程/多线程友好
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Any

import json
import os

import pandas as pd
from JohnsonUtil import commonTips as cct
try:
    from JSONData import tdx_data_Day as tdd
except ImportError:
    tdd = None

from logger_utils import LoggerFactory
logger = LoggerFactory.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# §0  常量与枚举
# ─────────────────────────────────────────────────────────────────────────────

MAX_FOLLOWERS_PER_SECTOR = 3   # 每板块最多跟进3只
MAX_POSITIONS            = 10  # 最大持仓数

# 离场触发条件（位掩码，便于组合）
class ExitReason(IntEnum):
    NONE               = 0
    LEADER_CRASH       = 1   # 龙头杀跌（日内跌幅超阈值）
    NO_NEW_DAY_HIGH    = 2   # 个股14:00后未创日新高
    VWAP_BREAK_CLOSE   = 4   # 尾盘（14:30后）破分时均线（VWAP）
    DAILY_LOSS_LIMIT   = 8   # 日亏损上限触发全场止损
    MANUAL             = 16  # 手动触发

# 决策信号类型
class SignalType(IntEnum):
    PULLBACK_BUY       = 1   # 回踩买点
    VWAP_SUPPORT       = 2   # 均价线支撑
    SECTOR_BREAKOUT    = 3   # 板块共振突破
    HOT_FOLLOW         = 4   # 龙头确认后跟进


# 龙头状态机（四级）
class DragonStatus(IntEnum):
    CANDIDATE  = 0   # StarFollow 刚确认，候选观察中
    DRAGON     = 1   # 连续多日新高，真龙头
    WARNING    = 2   # 出现预警信号（创新低/失去地位）
    ELIMINATED = 3   # 已淘汰，从跟踪名单清除


# ─────────────────────────────────────────────────────────────────────────────
# §1  数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SectorHeat:
    """板块热力快照"""
    name: str
    heat_score: float          # 综合热力评分 0~100
    bidding_score: float       # 竞价综合评分 (board_score from detector)
    zt_count: int              # 今日涨停家数
    zhuli_ratio: float         # 主力净占比均值
    volume_ratio: float        # 板块成交量比
    leader_code: str           # 龙头股代码
    leader_name: str           # 龙头股名称
    leader_change_pct: float   # 龙头当前涨幅
    follower_codes: List[str]  # 跟进股列表（最多3只）
    # v2: 丰富信息
    leader_pct_diff: float     = 0.0  # 龙头周期内涨幅变动
    leader_dff: float          = 0.0  # 龙头 dff（量价信号）
    leader_vwap: float         = 0.0  # 龙头均价线
    leader_klines: List[dict]  = field(default_factory=list)  # 龙头分时K线
    score_diff: float          = 0.0  # 板块强度周期内变化
    follow_ratio: float        = 0.0  # 板块跟涨比例
    sector_type: str           = ""   # 🔥强攻/♨️蓄势/🔄反转/📈跟随
    tags: str                  = ""   # 标签串
    follower_detail: List[dict] = field(default_factory=list)  # 跟进股明细
    race_candidates: List[dict] = field(default_factory=list)  # [NEW] 龙头竞赛选手列表
    updated_at: datetime       = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        # [MOD] 跟风明细格式化为易读的字符串，缩减 UI 展示压力
        details = []
        for f in self.follower_detail:
            name = f.get('name', '未知')
            pct  = f.get('pct', 0.0)
            details.append(f"{name}({pct:+.1f}%)")
        detail_str = " ".join(details) if details else "无"

        return {
            'name': self.name,
            'heat_score': round(self.heat_score, 1),
            'bidding_score': round(self.bidding_score, 2),
            'zt_count': self.zt_count,
            'zhuli_ratio': round(self.zhuli_ratio, 3),
            'volume_ratio': round(self.volume_ratio, 2),
            'leader_code': self.leader_code,
            'leader_name': self.leader_name,
            'leader_change_pct': round(self.leader_change_pct, 2),
            'leader_pct_diff': round(self.leader_pct_diff, 2),
            'leader_dff': round(self.leader_dff, 2),
            'leader_vwap': round(self.leader_vwap, 3),
            'score_diff': round(self.score_diff, 2),
            'follow_ratio': round(self.follow_ratio, 2),
            'sector_type': self.sector_type or "📈 跟随", # [MOD] 提供默认类型
            'tags': self.tags,
            'follower_codes': self.follower_codes,
            'follower_detail': detail_str, # [MOD] 使用格式化后的字符串
            'race_candidates': self.race_candidates, # [NEW] 竞赛明细
            'updated_at': self.updated_at.strftime('%H:%M:%S'),
        }


@dataclass
class DecisionSignal:
    """单个交易决策信号"""
    code: str
    name: str
    sector: str
    signal_type: SignalType
    priority: int              # 优先级 1～100（越大越优先）
    suggest_price: float       # 建议入场价
    current_price: float       # 当前价
    change_pct: float          # 当前涨幅%
    sector_heat: float         # 所属板块热度
    reason: str                # 人类可读的理由
    leader_code: str           # 所属板块龙头
    is_leader: bool            # 该股是否本身就是龙头
    # v2: 额外上下文
    pct_diff: float            = 0.0   # 周期内涨幅变化
    dff: float                 = 0.0   # 量价信号
    sector_type: str           = ""    # 板块类型
    created_at: datetime       = field(default_factory=datetime.now)
    status: str                = "待处理"   # 待处理/已忽略/已提交/已成交
    hits: int                  = 1         # 触发次数

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'signal_type': self.signal_type.name if hasattr(self.signal_type, 'name') else str(self.signal_type),
            'priority': self.priority,
            'suggest_price': round(self.suggest_price, 3),
            'current_price': round(self.current_price, 3),
            'change_pct': round(self.change_pct, 2),
            'pct_diff': round(self.pct_diff, 2),
            'dff': round(self.dff, 2),
            'sector_heat': round(self.sector_heat, 1),
            'sector_type': self.sector_type,
            'reason': self.reason,
            'leader_code': self.leader_code,
            'is_leader': self.is_leader,
            'created_at': self.created_at.strftime('%H:%M:%S') if getattr(self, 'created_at', None) else "",
            'status': self.status,
            'hits': getattr(self, 'hits', 1)
        }

@dataclass
class DragonRecord:
    """单只龙头的跨日追踪记录（可持久化）"""
    # ── 跨日持久化字段（无默认值）
    code: str
    name: str
    sector: str
    status: DragonStatus
    confirmed_date: str        # 首次确认日期 YYYYMMDD
    tracked_days: int          # 已跟踪交易日数
    consecutive_new_highs: int # 连续创新高天数
    prev_day_high: float       # 昨日日内最高
    prev_day_low: float        # 昨日日内最低
    prev_day_close: float      # 昨日收盘
    today_high: float          # 今日已知最高
    today_low: float           # 今日已知最低
    cum_pct_from_entry: float = 0.0  # 从首次确认累计涨幅%
    entry_price: float = 0.0         # 首次确认入场参考价
    warning_days: int = 0          # 连续预警天数
    last_update: str = ""           # datetime isoformat
    tags: List[str] = field(default_factory=list)            # 状态标签
    # ── 盘中瞬态字段（有默认值，不持久化）
    current_price: float = 0.0
    current_pct: float   = 0.0
    vwap: float          = 0.0
    dff: float           = 0.0
    below_vwap_count: int = field(default=0, repr=False)

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'status': self.status.name,
            'status_label': ['候选🌱', '真龙🐉', '预警⚠️', '淘汰❌'][int(self.status)],
            'confirmed_date': self.confirmed_date,
            'tracked_days': self.tracked_days,
            'consecutive_new_highs': self.consecutive_new_highs,
            'prev_day_high': round(self.prev_day_high, 3),
            'prev_day_low': round(self.prev_day_low, 3),
            'today_high': round(self.today_high, 3),
            'today_low': round(self.today_low, 3),
            'cum_pct': round(self.cum_pct_from_entry, 2),
            'entry_price': round(self.entry_price, 3),
            'warning_days': self.warning_days,
            'tags': ' '.join(self.tags[-4:]),
            'current_price': round(self.current_price, 3),
            'current_pct': round(self.current_pct, 2),
            'vwap': round(self.vwap, 3),
            'dff': round(self.dff, 2),
            'last_update': self.last_update,
        }

    def to_persist_dict(self) -> dict:
        """仅保留跨日必要字段"""
        return {
            'code': self.code, 'name': self.name, 'sector': self.sector,
            'status': int(self.status),
            'confirmed_date': self.confirmed_date,
            'tracked_days': self.tracked_days,
            'consecutive_new_highs': self.consecutive_new_highs,
            'prev_day_high': self.prev_day_high,
            'prev_day_low': self.prev_day_low,
            'prev_day_close': self.prev_day_close,
            'today_high': self.today_high,
            'today_low': self.today_low,
            'cum_pct_from_entry': self.cum_pct_from_entry,
            'entry_price': self.entry_price,
            'warning_days': self.warning_days,
            'last_update': self.last_update,
            'tags': self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'DragonRecord':
        return cls(
            code=d['code'], name=d.get('name', d['code']),
            sector=d.get('sector', ''),
            status=DragonStatus(int(d.get('status', 0))),
            confirmed_date=d.get('confirmed_date', ''),
            tracked_days=int(d.get('tracked_days', 1)),
            consecutive_new_highs=int(d.get('consecutive_new_highs', 0)),
            prev_day_high=float(d.get('prev_day_high', 0.0)),
            prev_day_low=float(d.get('prev_day_low', 0.0)),
            prev_day_close=float(d.get('prev_day_close', 0.0)),
            today_high=float(d.get('today_high', 0.0)),
            today_low=float(d.get('today_low', 0.0)),
            cum_pct_from_entry=float(d.get('cum_pct_from_entry', 0.0)),
            entry_price=float(d.get('entry_price', 0.0)),
            warning_days=int(d.get('warning_days', 0)),
            last_update=d.get('last_update', datetime.now().isoformat()),
            tags=list(d.get('tags', [])),
        )


# ─────────────────────────────────────────────────────────────────────────────
# §2  板块热力实时计算（SectorFocusMap）
# ─────────────────────────────────────────────────────────────────────────────

class SectorFocusMap:
    """
    实时板块热力计算
    ─────────────────
    数据策略（v2 双通道）：
      A. 优先通道：inject_detector_sectors() — 直接使用 BiddingMomentumDetector 已算好的
         board_score、龙头、跟随股、pct_diff、klines，完整度最高
      B. 降级通道：update(df_realtime) — 从 df_all 聚合，适合 detector 无数据时兜底

    inject_bidding_scores() 和 inject_ext_data() 保留兼容旧接口
    """

    # 热力计算权重（降级通道用）
    W_BIDDING = 0.35
    W_ZT      = 0.25
    W_ZHULI   = 0.20
    W_VOL     = 0.20

    def __init__(self):
        self._lock = threading.Lock()
        # {sector_name: SectorHeat}
        self._sector_map: Dict[str, SectorHeat] = {}
        # {code: sector_name} 快速反查
        self._code_sector: Dict[str, str] = {}
        # {code: bidding_score}（旧接口兼容用）
        self._bidding_scores: Dict[str, float] = {}
        # 55188 ext_data DataFrame
        self._ext_df: Optional[pd.DataFrame] = None
        self._zhuli_rank_map: Dict[str, int] = {}
        self._hot_rank_map: Dict[str, int] = {}
        self._last_update: Optional[datetime] = None
        # v2: 来自 detector 的完整个股快照 {code: snap_dict}
        self._detector_stock_snap: Dict[str, dict] = {}

    # ── 旧接口兼容 ────────────────────────────────────────────────────────────

    def inject_bidding_scores(self, scores: Dict[str, float]):
        """注入竞价评分 {code: score}（旧接口，兼容保留）"""
        with self._lock:
            self._bidding_scores.update(scores)

    def load_55188_cache(self):
        """[NEW] 从 scraper_55188 自动加载人气与主力排名缓存"""
        try:
            from scraper_55188 import load_cache
            df = load_cache()
            if df is not None and not df.empty:
                self.inject_ext_data(df)
                logger.debug(f"[SectorFocusMap] 55188 cache loaded: {len(df)} rows")
        except Exception as e:
            logger.debug(f"load_55188_cache failed: {e}")

    def inject_ext_data(self, df: pd.DataFrame):
        """注入 55188 综合数据 (主力排名/人气排名)"""
        with self._lock:
            self._ext_df = df
            # 预处理排名映射提升查询效率
            if not df.empty and 'code' in df.columns:
                self._zhuli_rank_map = df.set_index('code')['zhuli_rank'].to_dict() if 'zhuli_rank' in df.columns else {}
                self._hot_rank_map = df.set_index('code')['hot_rank'].to_dict() if 'hot_rank' in df.columns else {}
            else:
                self._zhuli_rank_map = {}
                self._hot_rank_map = {}

    # ── v2 核心注入：直接从 detector 灌入板块图 ──────────────────────────────

    def _clean_sector_name(self, name: str) -> str:
        """[FIX] 精准清洗：特赦 '0' (新股)，清扫其他垃圾符号"""
        if name is None: return ""
        name = str(name).strip('; ').strip()
        
        # 1. 特赦：'0' 代表新股或无板块个股，属于重要信号，必须保留
        if name == '0':
            return '0'
            
        # 2. 拦截：纯占位符或无效垃圾数据
        if name in (';', '--', '-', '.', 'nan', 'None', ''):
            return ""
            
        # 3. 长度保护：过长的垃圾堆叠字符（通常为解析错误）
        if len(name) > 100: # 放宽到100，确保复合板块不被截断
            return ""
            
        return name



    def inject_detector_sectors(
        self,
        active_sectors: List[dict],
        stock_snap: Dict[str, dict],
    ):
        """
        [v2] 直接摄入 BiddingMomentumDetector 已计算的板块图与个股快照。

        active_sectors: detector.get_active_sectors() 返回的 list[dict]
        stock_snap    : detector._global_snap_cache  {code: snap_dict}
                        snap_dict 含 score/pct/pct_diff/price_diff/dff/klines/
                                      last_close/high_day/pattern_hint 等
        """
        if not active_sectors:
            return
        try:
            new_map: Dict[str, SectorHeat] = {}
            new_code_sector: Dict[str, str] = {}

            for sec in active_sectors:
                # [FIX] 对板块名称进行清洗和过滤
                sname = self._clean_sector_name(sec.get('sector', ''))
                if not sname:
                    continue

                board_score    = float(sec.get('score', 0.0))
                score_diff     = float(sec.get('score_diff', 0.0))
                follow_ratio   = float(sec.get('follow_ratio', 0.0))
                leader_code    = str(sec.get('leader', ''))
                leader_name    = str(sec.get('leader_name', leader_code))
                leader_pct     = float(sec.get('leader_pct', 0.0))
                leader_pct_diff = float(sec.get('leader_pct_diff', 0.0))
                leader_dff     = float(sec.get('leader_dff', 0.0))
                leader_klines  = sec.get('leader_klines', [])
                leader_last_close = float(sec.get('leader_last_close', 0.0))
                tags           = str(sec.get('tags', ''))
                sector_type    = ''

                # 从 tag 中提取板块类型标记
                for marker in ['🔥 强攻', '♨️ 蓄势', '🔄 反转', '📈 跟随']:
                    if marker in tags:
                        sector_type = marker
                        break

                # [FIX] 遵循 SSOT 原则，直接从探测器预计算好的快照中提取 VWAP，不再本地重复计算
                leader_vwap = float(sec.get('leader_vwap', 0.0))

                # [NEW] 赛马模式：获得跟随股列表 (Move up to fix NameError)
                followers = sec.get('followers', [])
                follower_codes = [str(f.get('code', '')) for f in followers if f.get('code')][:MAX_FOLLOWERS_PER_SECTOR]

                # [NEW] 赛马模式：板块共振加成 (Resonace Bonus)
                # 如果板块内有股处于“赛马”状态，说明该板块具备时序稳定性，给予显著加分
                resonance_bonus = 0.0
                has_racing_winner = False
                for f in followers:
                    p_hint = str(f.get('pattern_hint', ''))
                    # 使用灵活的子串匹配，支持 [赛马...], ★赛马... 等各种格式
                    if '赛马' in p_hint:
                        has_racing_winner = True
                        if '强力确认' in p_hint or '30m' in p_hint:
                            resonance_bonus = max(resonance_bonus, 20.0)
                        elif '退潮优胜' in p_hint or '15m' in p_hint:
                            resonance_bonus = max(resonance_bonus, 12.0)
                        elif '分化确认' in p_hint or '10m' in p_hint:
                            resonance_bonus = max(resonance_bonus, 5.0)
                        else:
                            resonance_bonus = max(resonance_bonus, 3.0) # 初始观察期

                # [A] heat_score = board_score 基础分 + 趋势动量加成
                
                # score_diff>0: 60m内强度上升；follow_ratio>0.5: 多数个股跟涨；leader_pct_diff>0: 龙头处于上升通道
                momentum_bonus = (
                    min(score_diff * 3.0, 15.0) +          # 强度上升趋势，最多+15
                    (follow_ratio - 0.5) * 20.0 +           # 跟涨扩散度，±10
                    min(leader_pct_diff * 2.0, 10.0) +      # 龙头60m内涨幅，最多+10
                    resonance_bonus                        # [NEW] 赛马共振加成
                )
                heat_score = min(100.0, board_score * 3.0 + max(0.0, momentum_bonus))
                
                # 如果有赛马胜出，强制将板块类型标记为“🔥 强攻”
                if has_racing_winner and '🔥 强攻' not in tags:
                    tags = f"🔥 强攻 | {tags}" if tags else "🔥 强攻"
                    sector_type = "🔥 强攻"

                # 跟随股明细（含 pct_diff/dff）
                follower_detail = []
                for f in followers[:MAX_FOLLOWERS_PER_SECTOR]:
                    follower_detail.append({
                        'code': str(f.get('code', '')),
                        'name': str(f.get('name', '')),
                        'pct': float(f.get('pct', 0.0)),
                        'pct_diff': float(f.get('pct_diff', 0.0)),
                        'dff': float(f.get('dff', 0.0)),
                        'price': float(f.get('price', 0.0)),
                        'klines': f.get('klines', []),
                        'last_close': float(f.get('last_close', 0.0)),
                        'pattern_hint': str(f.get('pattern_hint', '')),
                    })

                # 涨停家数（从 top0 统计）
                zt_count = sum(1 for f in followers if f.get('is_untradable') is False
                               and float(f.get('pct', 0)) >= 9.5)
                if leader_pct >= 9.5:
                    zt_count += 1

                # 合并 ext_df 的主力数据
                zhuli_ratio = 0.0
                vol_ratio = 1.0
                with self._lock:
                    ext_df = self._ext_df
                if ext_df is not None and not ext_df.empty and 'code' in ext_df.columns:
                    try:
                        zhuli_map = ext_df.set_index('code').get('net_ratio', pd.Series())
                        zhuli_ratio = float(zhuli_map.get(leader_code, 0.0) or 0.0)
                    except Exception:
                        pass

                sh = SectorHeat(
                    name=sname,
                    heat_score=heat_score,
                    bidding_score=board_score,
                    zt_count=zt_count,
                    zhuli_ratio=zhuli_ratio,
                    volume_ratio=vol_ratio,
                    leader_code=leader_code,
                    leader_name=leader_name,
                    leader_change_pct=leader_pct,
                    follower_codes=follower_codes,
                    leader_pct_diff=leader_pct_diff,
                    leader_dff=leader_dff,
                    leader_vwap=leader_vwap,
                    leader_klines=leader_klines,
                    score_diff=score_diff,
                    follow_ratio=follow_ratio,
                    sector_type=sector_type,
                    tags=tags,
                    follower_detail=follower_detail,
                    race_candidates=sec.get('race_candidates', []), # 从 detector 获取竞赛选手
                    updated_at=datetime.now(),
                )
                new_map[sname] = sh
                new_code_sector[leader_code] = sname
                for fc in follower_codes:
                    if fc:
                        new_code_sector[fc] = sname

            with self._lock:
                self._sector_map.update(new_map)
                self._code_sector.update(new_code_sector)
                self._detector_stock_snap.update(stock_snap)
                self._last_update = datetime.now()

            logger.debug(f"[SectorFocusMap] inject_detector_sectors: {len(new_map)} sectors from detector")
        except Exception as e:
            logger.warning(f"[SectorFocusMap] inject_detector_sectors failed: {e}")

    # ── 降级通道：从 df_realtime 聚合（detector 无数据时用）──────────────────

    def update(self, df_realtime: Optional[pd.DataFrame]) -> List[SectorHeat]:
        """全量更新板块热力（降级通道，在后台线程中调用）"""
        if df_realtime is None or df_realtime.empty:
            return []
        try:
            return self._compute(df_realtime)
        except Exception as e:
            logger.warning(f"[SectorFocusMap] update failed: {e}")
            return []

    def _compute(self, df: pd.DataFrame) -> List[SectorHeat]:
        """内部计算逻辑（降级通道，无锁，由 update 包裹执行）"""
        with self._lock:
            bidding = dict(self._bidding_scores)
            det_snap = dict(self._detector_stock_snap)
            ext_df = self._ext_df.copy() if self._ext_df is not None and not self._ext_df.empty else pd.DataFrame()

        # 1. 确保必要字段存在
        needed = ['category', 'percent', 'code', 'name']
        for c in needed:
            if c not in df.columns:
                logger.debug(f"[SectorFocusMap] missing column: {c}")
                return []

        # 2. 构建板块聚合
        df = df.copy()
        # 优先用 detector snap 里的 score 作为竞价强度
        df['_bid_score'] = df['code'].map(
            {c: s.get('score', 0.0) for c, s in det_snap.items()}
        ).fillna(df['code'].map(bidding).fillna(0.0))
        df['_is_zt'] = df['percent'] >= 9.5
        df['_vol_ratio'] = df.get('ratio', pd.Series(1.0, index=df.index)).fillna(1.0)

        # 主力净占比
        if not ext_df.empty and 'net_ratio' in ext_df.columns and 'code' in ext_df.columns:
            zhuli_map = ext_df.set_index('code')['net_ratio'].to_dict()
        else:
            zhuli_map = {}
        df['_zhuli'] = df['code'].map(zhuli_map).fillna(0.0)

        # [FIX] 预处理板块名：过滤首尾空格及特殊分号，确保聚合不重叠
        df['category'] = df['category'].astype(str).str.strip('; ').str.strip()

        # 按板块聚合
        # [NEW] 集成 55188 排名数据：计算人气密度
        hot_map   = self._hot_rank_map
        zhuli_map_rank = self._zhuli_rank_map
        
        # 将排名映射回主表
        df['_hot_rank']   = df['code'].map(hot_map).fillna(9999)
        df['_zhuli_rank'] = df['code'].map(zhuli_map_rank).fillna(9999)
        
        # 计算进入 Top 300 的密度 (用于板块热度提权)
        df['_is_popular'] = df['_hot_rank'] <= 300
        
        g = df.groupby('category', sort=False)
        sectors_raw = g.agg(
            _bid_mean=('_bid_score', 'mean'),
            _zt_sum=('_is_zt', 'sum'),
            _vol_mean=('_vol_ratio', 'mean'),
            _zhuli_mean=('_zhuli', 'mean'),
            _avg_pct=('percent', 'mean'),
            _pop_count=('_is_popular', 'sum'), # [NEW] 人气股数量
            _count=('code', 'count'),
        ).reset_index()

        # [NEW] 计算红盘占比 & 均线之上占比 (结构健康度)
        df['_is_above_vwap'] = df['percent'] > 0 # 简单模拟
        pos_df = df[df['percent'] > 0].groupby('category', sort=False).size().reset_index(name='_pos_count')
        sectors_raw = pd.merge(sectors_raw, pos_df, on='category', how='left').fillna(0)
        sectors_raw['_pos_ratio'] = sectors_raw['_pos_count'] / sectors_raw['_count']
        sectors_raw['_pop_density'] = sectors_raw['_pop_count'] / sectors_raw['_count']

        sectors_raw.rename(columns={'category': 'name'}, inplace=True)

        sectors_raw = sectors_raw[sectors_raw['_count'] >= 3]
        if sectors_raw.empty:
            return []

        # [NEW] 结构性提权与降速：全面考虑人气与结构
        sectors_raw['_struct_bonus'] = 1.0
        # 阴跌降权：平均跌幅>0.5% 且红盘占比<40% 或 人气全无
        dead_mask = (sectors_raw['_avg_pct'] < -0.5) & (sectors_raw['_pos_ratio'] < 0.4)
        sectors_raw.loc[dead_mask, '_struct_bonus'] = 0.05 
        
        # 起步/强攻提权：平均涨幅为正且红盘占比>60% 且有人气股扎堆
        start_mask = (sectors_raw['_avg_pct'] > 0.0) & (sectors_raw['_pos_ratio'] > 0.6) & (sectors_raw['_pop_count'] >= 1)
        sectors_raw.loc[start_mask, '_struct_bonus'] = 1.8 # 提高提权系数

        # 3. 标准化各分量 → 0~1
        def _norm(s: pd.Series) -> pd.Series:
            mn, mx = s.min(), s.max()
            if mx == mn:
                return pd.Series(0.5, index=s.index)
            return (s - mn) / (mx - mn)

        sectors_raw['_n_bid'] = _norm(sectors_raw['_bid_mean'])
        sectors_raw['_n_zt']  = _norm(sectors_raw['_zt_sum'])
        sectors_raw['_n_vol'] = _norm(sectors_raw['_vol_mean'])
        sectors_raw['_n_zhl'] = _norm(sectors_raw['_zhuli_mean'])

        sectors_raw['heat_score'] = (
            (sectors_raw['_n_bid'] * self.W_BIDDING +
             sectors_raw['_n_zt']  * self.W_ZT +
             sectors_raw['_n_zhl'] * self.W_ZHULI +
             sectors_raw['_n_vol'] * self.W_VOL) * 100
        ) * sectors_raw['_struct_bonus'] # [CORE] 结构性修正

        result: List[SectorHeat] = []
        # [ROLLBACK] 恢复最初的执行广度：恢复到 head(20)
        for _, row in sectors_raw.sort_values('heat_score', ascending=False).head(20).iterrows():
            # [FIX] 对降级路径的板块名称进行清洗
            sname = self._clean_sector_name(row['name'])
            if not sname:
                continue
            
            sec_df = df[df['category'] == row['name']].copy() # 注意聚合还是用原始 key
            if sec_df.empty:
                continue
            leader_code, leader_name, leader_pct, followers, race_candidates = self._identify_leader(sec_df, bidding, det_snap)
            
            # [FIX] 在 fallback 降级聚合路径中同步补充 follower_detail 逻辑，防丢失明细
            follower_detail = []
            for f_code in followers[:MAX_FOLLOWERS_PER_SECTOR]:
                if not f_code: continue
                # 提取基本信息
                f_pct = 0.0
                if f_code in det_snap:
                    f_pct = float(det_snap[f_code].get('pct', 0.0))
                else:
                    try:
                        f_pct = float(sec_df.loc[sec_df['code'] == f_code, 'percent'].iloc[0])
                    except: pass
                
                f_name = f_code
                try:
                    f_name = str(sec_df.loc[sec_df['code'] == f_code, 'name'].iloc[0])
                except: pass
                
                follower_detail.append({
                    'code': str(f_code),
                    'name': str(f_name),
                    'pct': float(f_pct)
                })

            heat = SectorHeat(
                name=sname,
                heat_score=float(row['heat_score']),
                bidding_score=float(row['_bid_mean']),
                zt_count=int(row['_zt_sum']),
                zhuli_ratio=float(row['_zhuli_mean']),
                volume_ratio=float(row['_vol_mean']),
                leader_code=leader_code,
                leader_name=leader_name,
                leader_change_pct=leader_pct,
                leader_pct_diff=0.0,
                leader_dff=0.0,
                leader_vwap=0.0,
                score_diff=0.0,
                follow_ratio=0.0,
                sector_type="",
                tags="",
                follower_codes=followers,
                follower_detail=follower_detail,
                race_candidates=race_candidates, # [NEW] 注入竞赛选手
                updated_at=datetime.now(),
            )
            result.append(heat)

        with self._lock:
            # [FIX] 允许覆盖更新：确保手动执行时，计算出的新热度、新龙头能实时刷新到 map 中
            for h in result:
                self._sector_map[h.name] = h
            for h in result:
                self._code_sector[h.leader_code] = h.name
                for fc in h.follower_codes:
                    self._code_sector[fc] = h.name
            self._last_update = datetime.now()

        return result

    def _identify_leader(
        self,
        sec_df: pd.DataFrame,
        bidding: Dict[str, float],
        det_snap: Dict[str, dict],
    ) -> Tuple[str, str, float, List[str], List[dict]]:
        sec_df = sec_df.copy()
        # 优先用 detector score，否则用 bidding_scores
        sec_df['_bid'] = sec_df['code'].map(
            {c: s.get('score', 0.0) for c, s in det_snap.items()}
        ).fillna(sec_df['code'].map(bidding).fillna(0.0))
        sec_df['_zt'] = sec_df['percent'] >= 9.5

        # [D] dff 主力资金流向（正值=主力净流入，优先识别悄悄建仓的潜力股）
        sec_df['_dff'] = sec_df['code'].map(
            {c: float(s.get('dff', 0.0)) for c, s in det_snap.items()}
        ).fillna(0.0)

        # [NEW] 在龙头识别中深度集成 55188 人气排名
        hot_map = self._hot_rank_map
        sec_df['_hot_rank'] = sec_df['code'].map(hot_map).fillna(9999)
        # 人气越高分数越多，Top 10: 25分, Top 100: 15分, Top 300: 10分
        def _rank_score(r):
            if r <= 10: return 25.0
            if r <= 100: return 15.0
            if r <= 300: return 10.0
            return 0.0
        sec_df['_rank_points'] = sec_df['_hot_rank'].apply(_rank_score)

        sec_df['_leader_score'] = (
            sec_df['_zt'].astype(float) * 40 +
            sec_df['_bid'] * 4 +
            sec_df['percent'].clip(0, 10) * 1 +
            sec_df['_rank_points'] * 1 +           # 人气排名加分
            sec_df['_dff'].clip(0, 20) * 2         # [D] dff 主力资金加权（最多+40分）
        )
        sorted_df = sec_df.sort_values('_leader_score', ascending=False).reset_index(drop=True)
        if sorted_df.empty:
            return '', '', 0.0, []
        leader = sorted_df.iloc[0]
        leader_code = str(leader.get('code', ''))
        leader_name = str(leader.get('name', ''))
        leader_pct  = float(leader.get('percent', 0.0))
        # [FIX] 撤销 bid 限制
        followers_df = sorted_df.iloc[1:MAX_FOLLOWERS_PER_SECTOR + 1]
        follower_codes = [str(r['code']) for _, r in followers_df.iterrows()]
        
        # [NEW] 龙头竞赛选手识别：涨幅 > 基准 且 人力 > 0
        temp = self.get_market_temperature()
        entry_pct = 3.0
        if temp >= 70: entry_pct = 3.5
        elif temp < 35: entry_pct = 2.5
        
        candidates_df = sorted_df[sorted_df['percent'] >= entry_pct].head(5)
        race_candidates = []
        for _, r in candidates_df.iterrows():
            pct = float(r.get('percent', 0.0))
            status = "参赛🌱"
            if pct >= 9.0: status = "确核🐲"
            elif pct >= 6.0: status = "晋级🌟"
            
            race_candidates.append({
                'code': str(r.get('code', '')),
                'name': str(r.get('name', '')),
                'pct': round(pct, 2),
                'status': status,
                'score': round(float(r.get('_leader_score', 0.0)), 1)
            })

        return leader_code, leader_name, leader_pct, follower_codes, race_candidates

    def get_market_temperature(self) -> float:
        """[NEW] 计算当前市场整体温度：基于热点板块的平均 heat_score"""
        with self._lock:
            if not self._sector_map:
                return 50.0
            top_sectors = sorted(self._sector_map.values(), key=lambda s: s.heat_score, reverse=True)[:5]
            if not top_sectors:
                return 50.0
            avg_heat = sum(s.heat_score for s in top_sectors) / len(top_sectors)
            return avg_heat

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    def get_hot_sectors(self, top_n: int = 10) -> List[SectorHeat]:
        with self._lock:
            sectors = sorted(self._sector_map.values(), key=lambda s: s.heat_score, reverse=True)
        return sectors[:top_n]

    def get_sector_of_code(self, code: str) -> Optional[str]:
        with self._lock:
            return self._code_sector.get(code)

    def get_sector_heat(self, sector_name: str) -> Optional[SectorHeat]:
        with self._lock:
            return self._sector_map.get(sector_name)

    def get_leader_of_sector(self, sector_name: str) -> Optional[str]:
        sh = self.get_sector_heat(sector_name)
        return sh.leader_code if sh else None

    def get_stock_snap(self, code: str) -> Optional[dict]:
        """获取 detector 快照中的个股数据（含 klines/pct_diff/dff）"""
        with self._lock:
            return self._detector_stock_snap.get(code)

    def get_stock_ranks(self, code: str) -> Tuple[int, int]:
        """获取 55188 排名 (主力排名, 人气排名)"""
        with self._lock:
            return self._zhuli_rank_map.get(code, 9999), self._hot_rank_map.get(code, 9999)


# ─────────────────────────────────────────────────────────────────────────────
# §3  龙头跟进识别（StarFollowEngine）
# ─────────────────────────────────────────────────────────────────────────────

class StarFollowEngine:
    """
    龙头确认 + 同板块跟进股生成
    ─────────────────────────────
    v2：确认条件增加对 detector board_score 的直接引用
    """

    LEADER_MIN_ZT_OR_PCT  = 7.5    # [MOD] 下调门槛 (从 9.0 -> 7.5)，捕获更多强势启动个股
    LEADER_MIN_BID_SCORE  = 5.0    
    LEADER_HOT_RANK_MAX   = 150    # [MOD] 扩大范围 (从 100 -> 150)，包含更多热点个股

    def __init__(self, sector_map: SectorFocusMap):
        self._sector_map = sector_map
        self._confirmed_leaders: Dict[str, datetime] = {}
        self._leader_baselines: Dict[str, float] = {}   # [B] 确认时涨幅基准
        self._leader_weakened: set = set()               # [B] 已弱化龙头集合
        self._race_peaks: Dict[str, float] = {}          # [NEW] 记录竞赛选手的盘中最高涨幅
        self._lock = threading.Lock()

    def confirm_leaders(
        self,
        df_realtime: pd.DataFrame,
        bidding_scores: Dict[str, float],
        hot_rank_map: Optional[Dict[str, int]] = None,
    ) -> List[str]:
        hot_sectors = self._sector_map.get_hot_sectors(top_n=15)
        new_leaders = []

        for sh in hot_sectors:
            # 1. 处理确核逻辑 (Winner)
            code = sh.leader_code
            if not code:
                continue
            pct    = sh.leader_change_pct
            bid    = sh.bidding_score
            h_rank = (hot_rank_map or {}).get(code, 9999)

            ok_pct = pct >= self.LEADER_MIN_ZT_OR_PCT
            ok_bid = bid >= self.LEADER_MIN_BID_SCORE
            ok_hot = h_rank <= self.LEADER_HOT_RANK_MAX

            if ok_pct and (ok_bid or ok_hot):
                with self._lock:
                    if code not in self._confirmed_leaders:
                        self._confirmed_leaders[code] = datetime.now()
                        self._leader_baselines[code] = pct
                        new_leaders.append(code)
                        logger.info(f"[Competition] 🏆 胜出确核: {code}({sh.leader_name}) 板块={sh.name}")

            # 2. [NEW] 竞赛选手状态维护与淘汰 (Competition & Pruning)
            self._prune_candidates(sh)
            
            # 3. 同步衰减状态
            self._update_weakened_state(code, pct)
        return new_leaders

    def _prune_candidates(self, sh: SectorHeat):
        """[NEW] 去弱留强逻辑：实时剔除掉队选手"""
        if not sh.race_candidates:
            return
            
        with self._lock:
            # 更新峰值并标记淘汰
            survivors = []
            leader_pct = sh.leader_change_pct
            
            for c in sh.race_candidates:
                code = c['code']
                pct = c['pct']
                peak = max(self._race_peaks.get(code, 0.0), pct)
                self._race_peaks[code] = peak
                
                # 淘汰条件1：从高位回落超过 2.5% (洗盘太狠或抛压大)
                is_fallback = (pct < peak - 2.5)
                # 淘汰条件2：落后领头羊超过 5.0% (被甩开一个身位)
                is_lagging  = (pct < leader_pct - 5.0) and (pct < 6.0) # 6%以上属于晋级区，容忍度略高
                
                if is_fallback or is_lagging:
                    reason = "回落" if is_fallback else "掉队"
                    # logger.debug(f"[Competition] 淘汰选手: {code} 原因={reason} 当前={pct}% 最高={peak}%")
                    continue # 不加入幸存者名单
                
                survivors.append(c)
            
            # 更新 SectorHeat 对象
            sh.race_candidates = survivors[:5] # 严格限制 3-5 个名额

    def get_follow_candidates(self, sector_name: str) -> List[str]:
        sh = self._sector_map.get_sector_heat(sector_name)
        if not sh:
            return []
        return sh.follower_codes[:MAX_FOLLOWERS_PER_SECTOR]

    def is_leader_confirmed(self, code: str) -> bool:
        with self._lock:
            return code in self._confirmed_leaders

    def get_confirmed_leaders(self) -> Dict[str, datetime]:
        with self._lock:
            return dict(self._confirmed_leaders)

    def _update_weakened_state(self, code: str, current_pct: float):
        """[B] 实时同步龙头强弱状态（每次 confirm_leaders 调用时自动触发）"""
        with self._lock:
            if code not in self._confirmed_leaders:
                return
            baseline = self._leader_baselines.get(code, current_pct)
            # 真正的龙头极少大幅回落，如果从确认的高点（如涨停）回落超过 3.5%，视为爆量烂板或被洗弱
            if current_pct < baseline - 3.5:     
                if code not in self._leader_weakened:
                    self._leader_weakened.add(code)
                    logger.info(f"[StarFollow] 龙头弱化(破位洗盘): {code} 当前={current_pct:.1f}% 基准={baseline:.1f}%")
            elif current_pct >= baseline - 1.5:  # 反弹修复，取消弱化
                self._leader_weakened.discard(code)

    def is_leader_strong(self, code: str) -> bool:
        """[B] 强势确认：已确认 且 未弱化（双重条件，减少弱势龙头产生的跟随信号）"""
        with self._lock:
            return code in self._confirmed_leaders and code not in self._leader_weakened

    def reset_day(self):
        with self._lock:
            self._confirmed_leaders.clear()
            self._leader_baselines.clear()   # [B]
            self._leader_weakened.clear()    # [B]
            self._race_peaks.clear()         # [NEW] 清除盘中竞赛峰值数据


# ─────────────────────────────────────────────────────────────────────────────
# §3.5  龙头持续追踪器（DragonLeaderTracker）— 跨日资金轮转核心
# ─────────────────────────────────────────────────────────────────────────────

_DRAGON_PERSIST_PATH = "snapshots/dragon_tracker.json"


class DragonLeaderTracker:
    """
    龙头持续追踪器 — 周而复始自动挖掘 + 自动清理
    ─────────────────────────────────────────────
    工作链路：
      1. add_candidate()              — StarFollow 确认后入库候选
      2. intraday_update()            — 每 tick：盘中新高不新低 ➜ 初级认可
      3. daily_close_snapshot()       — 收盘固化日高低，自动升降级/淘汰垃圾
      4. auto_next_day_validate_all() — 次日开盘批量初始化新一日基准
      5. get_dragon_signal()          — 为真龙/盘中新高候选生成高优先级信号
      6. JSON 持久化                  — 程序重启不丢跨日跟踪状态

    升级：CANDIDATE ➜ DRAGON
      - 连续 DRAGON_UPGRADE_DAYS(=2) 个交易日创新高，且未创新低
    淘汰：WARNING ➜ ELIMINATED（自动从名单清除）
      - 盘中跌破昨日最低价
      - 连续 WARNING_ELIM_DAYS(=2) 日预警未修复
    """

    DRAGON_UPGRADE_DAYS  = 2    # 连续N日新高升级为真龙头
    WARNING_ELIM_DAYS    = 2    # 连续N日预警则淘汰
    INTRADAY_VWAP_LIMIT  = 3    # 盘中连续N次跌穿VWAP触发预警
    MIN_SECTOR_HEAT      = 20.0 # 候选入库最低板块热度

    def __init__(self, persist_path: Optional[str] = None):
        self._records: Dict[str, DragonRecord] = {}
        self._lock = threading.Lock()
        self._persist_path = persist_path or _DRAGON_PERSIST_PATH
        self._today_str: str = datetime.now().strftime('%Y%m%d')
        self._next_day_done: bool = False
        self.breakdown_details: List[str] = []  # [NEW] 破位聚合记录
        self.dragon_details: List[str] = []     # [NEW] 龙头信号聚合记录
        self._load_persist()

    # ── 持久化 ────────────────────────────────────────────────────────────────

    def _load_persist(self):
        """启动时加载跨日龙头数据（跳过 ELIMINATED）"""
        try:
            if not os.path.exists(self._persist_path):
                return
            with open(self._persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            n = 0
            for item in data.get('records', []):
                try:
                    rec = DragonRecord.from_dict(item)
                    if rec.status != DragonStatus.ELIMINATED:
                        self._records[rec.code] = rec
                        n += 1
                except Exception as e:
                    logger.debug(f"[DragonTracker] load record err: {e}")
            logger.info(f"[DragonTracker] 加载持久化龙头: {n} 只 (日期={data.get('date','')})")
        except Exception as e:
            logger.warning(f"[DragonTracker] 加载持久化失败: {e}")

    def _save_persist(self):
        """原子写入持久化 JSON"""
        try:
            d = os.path.dirname(self._persist_path)
            if d:
                os.makedirs(d, exist_ok=True)
            with self._lock:
                items = [r.to_persist_dict() for r in self._records.values()
                         if r.status != DragonStatus.ELIMINATED]
            tmp = self._persist_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'saved_at': datetime.now().isoformat(),
                           'date': self._today_str,
                           'records': items}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._persist_path)
            logger.debug(f"[DragonTracker] 持久化保存: {len(items)} 条")
        except Exception as e:
            logger.warning(f"[DragonTracker] 持久化保存失败: {e}")

    # ── 候选加入 ──────────────────────────────────────────────────────────────

    def add_candidate(self, code: str, name: str, sector: str,
                      current_price: float, sector_heat: float = 0.0):
        """StarFollowEngine 确认后调用，将个股加入候选名单（已存在则跳过）"""
        if sector_heat < self.MIN_SECTOR_HEAT:
            return
        with self._lock:
            if code in self._records:
                return
            rec = DragonRecord(
                code=code, name=name, sector=sector,
                status=DragonStatus.CANDIDATE,
                confirmed_date=self._today_str,
                tracked_days=1, consecutive_new_highs=0,
                prev_day_high=0.0, prev_day_low=0.0, prev_day_close=0.0,
                today_high=current_price, today_low=current_price,
                cum_pct_from_entry=0.0, entry_price=current_price,
                warning_days=0, last_update=datetime.now().isoformat(),
                tags=['新候选'],
            )
            self._records[code] = rec
        logger.info(f"[DragonTracker] 🌱 候选入库: {code}({name}) 板块={sector} 入场价={current_price:.3f}")

    # ── 盘中实时更新 ──────────────────────────────────────────────────────────

    def intraday_update(self, code: str, current_price: float,
                        day_high: float, day_low: float,
                        vwap: float, dff: float, current_pct: float,
                        sector_heat: float = 0.0):
        """每 tick 调用：新高不新低 ➜ 初级认可；跌破昨低 ➜ 立即 WARNING"""
        with self._lock:
            rec = self._records.get(code)
            if rec is None or rec.status == DragonStatus.ELIMINATED:
                return

            # 更新今日高低
            if day_high > rec.today_high:
                rec.today_high = day_high
            if day_low > 0 and (rec.today_low <= 0 or day_low < rec.today_low):
                rec.today_low = day_low

            # 实时字段
            rec.current_price = current_price
            rec.current_pct   = current_pct
            rec.vwap          = vwap
            rec.dff           = dff
            rec.last_update   = datetime.now().isoformat()
            if rec.entry_price > 0:
                rec.cum_pct_from_entry = (current_price / rec.entry_price - 1) * 100

            # ① 启动价保护原则：盘中只要跌破“启动阳线收盘价”(prev_day_close) ➜ 立即判定失败
            if rec.prev_day_close > 0 and current_price < rec.prev_day_close * 0.998:
                if rec.status != DragonStatus.WARNING:
                    rec.status = DragonStatus.WARNING
                    rec.warning_days = max(rec.warning_days, 1)
                if '破启动收盘价' not in rec.tags:
                    rec.tags.append('破启动收盘价')
                
                # [MOD] 采用聚合日志，避免刷屏
                info_entry = f"{code:<7} {rec.name:<8} | 核心预警: 跌破启动位 {rec.prev_day_close:.2f}"
                self.breakdown_details.append(info_entry)

            # ② 盘中跌破昨日最低 ➜ 加重预警
            if rec.prev_day_low > 0 and current_price < rec.prev_day_low * 0.995:
                # [MOD] 采用聚合日志，避免刷屏
                info_entry = f"{code:<7} {rec.name:<8} | ⚠️破昨低: 当前{current_price:.2f} 昨低{rec.prev_day_low:.2f}"
                self.breakdown_details.append(info_entry)
                return

            # ② 盘中新高不新低 ➜ 去掉破位标记，WARNING 给一次修复机会
            if rec.prev_day_high > 0:
                is_new_hi = rec.today_high > rec.prev_day_high
                is_ok_low = rec.today_low  >= rec.prev_day_low * 0.998
                
                # [NEW] 识别冲高回落：如果创了新高但目前涨幅回吐严重
                is_fallback = is_new_hi and current_price < rec.today_high * 0.97
                
                if is_new_hi and is_ok_low:
                    if '盘中新高' not in rec.tags:
                        rec.tags.append('盘中新高')
                    
                    if is_fallback:
                        if '冲高回落' not in rec.tags: rec.tags.append('冲高回落')
                    else:
                        rec.tags = [t for t in rec.tags if t != '冲高回落']
                        
                    rec.tags = [t for t in rec.tags if t != '盘中破昨低']
                    if rec.status == DragonStatus.WARNING and rec.today_high > rec.prev_day_high * 1.002:
                        rec.warning_days = max(0, rec.warning_days - 1)
                        if rec.warning_days == 0:
                            rec.status = DragonStatus.CANDIDATE
                            logger.info(f"[DragonTracker] ↑ 盘中修复: {code}")

            # ③ 连续跌穿 VWAP 次数统计
            if vwap > 0 and current_price < vwap * 0.998:
                rec.below_vwap_count += 1
                if rec.below_vwap_count >= self.INTRADAY_VWAP_LIMIT:
                    if '跌破均线' not in rec.tags:
                        rec.tags.append('跌破均线')
            else:
                rec.below_vwap_count = 0
                rec.tags = [t for t in rec.tags if t != '跌破均线']

    # ── 收盘快照（每日 ~15:00 调用）────────────────────────────────────────────

    def daily_close_snapshot(self) -> dict:
        """
        收盘后调用：
        - 固化今日高低 ➜ prev_day；清零今日字段
        - 连续N日新高 ➜ 升级 DRAGON
        - 创新低 / 连续N日 WARNING ➜ ELIMINATED 淘汰
        - 保存 JSON
        """
        self._today_str = datetime.now().strftime('%Y%m%d')
        upgraded, eliminated = [], []

        with self._lock:
            for code, rec in list(self._records.items()):
                # [MOD] 新高天判定逻辑加固：需满足新高且收盘具备一定强度
                # 1. 物理新高
                physical_new_high = rec.today_high > rec.prev_day_high
                # 2. 趋势强度 (收盈上涨 或 收盘价维持在昨日高点 99.5% 以上)
                is_strong_close = (rec.current_price >= rec.prev_day_close * 1.002) or (rec.current_price > rec.prev_day_high * 0.995)
                # 3. 破位判定 (跌破昨低 或 当日跌幅过大)
                made_new_low  = rec.today_low  < rec.prev_day_low * 0.998 if rec.prev_day_low > 0 else False
                is_fatal_drop = (rec.current_pct < -3.5) # 核心保护：跌幅过大强制 Reset

                if physical_new_high and is_strong_close and not made_new_low and not is_fatal_drop:
                    rec.consecutive_new_highs += 1
                    if '连续新高' not in rec.tags:
                        rec.tags.append('连续新高')
                else:
                    # [MOD] 柔软化归零逻辑：仅在明显跌破昨低或发生 3.5% 以上大跌时重置
                    # 若只是盘整（未创新高但也未破位），保留原有计数不增加，确保护航持续性
                    if is_fatal_drop or made_new_low:
                        rec.consecutive_new_highs = 0
                        rec.tags = [t for t in rec.tags if t != '连续新高']
                        if is_fatal_drop:
                            if '大跌重置' not in rec.tags: rec.tags.append('大跌重置')

                if made_new_low:
                    if rec.status != DragonStatus.WARNING:
                        rec.status = DragonStatus.WARNING
                    rec.warning_days += 1
                    if '创新低' not in rec.tags:
                        rec.tags.append('创新低')
                else:
                    rec.tags = [t for t in rec.tags if t != '创新低']
                    if rec.status == DragonStatus.WARNING:
                        rec.warning_days = max(0, rec.warning_days - 1)
                        if rec.warning_days == 0:
                            rec.status = DragonStatus.CANDIDATE

                # 淘汰：连续预警超阈值
                if rec.warning_days >= self.WARNING_ELIM_DAYS:
                    rec.status = DragonStatus.ELIMINATED
                    eliminated.append(code)
                    logger.info(f"[DragonTracker] ❌ 淘汰: {code}({rec.name}) 连续{rec.warning_days}日预警")
                    continue

                # 升级：连续新高达标
                if (rec.status == DragonStatus.CANDIDATE
                        and rec.consecutive_new_highs >= self.DRAGON_UPGRADE_DAYS):
                    rec.status = DragonStatus.DRAGON
                    upgraded.append(code)
                    logger.info(f"[DragonTracker] 🐉 升级真龙头: {code}({rec.name}) 连续{rec.consecutive_new_highs}日新高")

                # 固化：今日 ➜ 昨日
                rec.prev_day_high  = rec.today_high  if rec.today_high  > 0 else rec.prev_day_high
                rec.prev_day_low   = rec.today_low   if rec.today_low   > 0 else rec.prev_day_low
                rec.prev_day_close = rec.current_price if rec.current_price > 0 else rec.prev_day_close
                # 清零今日盘中字段
                rec.today_high = 0.0
                rec.today_low  = 0.0
                rec.below_vwap_count = 0
                rec.tags = [t for t in rec.tags if t not in ('盘中新高', '盘中破昨低', '新候选')]
                rec.tracked_days += 1
                rec.last_update = datetime.now().isoformat()

            # 删除已淘汰
            for code in eliminated:
                self._records.pop(code, None)

        self._next_day_done = False
        self._save_persist()
        logger.info(f"[DragonTracker] 收盘快照完成: 升级={upgraded} 淘汰={eliminated} 存活={len(self._records)}")
        return {'upgraded': upgraded, 'eliminated': eliminated}

    # ── 次日批量初始化 ────────────────────────────────────────────────────────

    def auto_next_day_validate_all(self, stock_snaps: Dict[str, dict]):
        """次日开盘后检测到日期变更时调用一次，用开盘价初始化今日高低"""
        if self._next_day_done:
            return
        with self._lock:
            codes = list(self._records.keys())
        for code in codes:
            snap = stock_snaps.get(code, {})
            price = float(snap.get('price', 0.0))
            if price <= 0:
                continue
            prev_close = float(snap.get('last_close', 0.0))
            with self._lock:
                rec = self._records.get(code)
                if rec and rec.today_high <= 0:
                    rec.today_high = price
                    rec.today_low  = price
                    if prev_close > 0 and rec.prev_day_close <= 0:
                        rec.prev_day_close = prev_close
        self._next_day_done = True
        logger.info(f"[DragonTracker] 次日批量初始化: {len(codes)} 只")

    def get_dragon_records(self, min_status=DragonStatus.CANDIDATE) -> List[dict]:
        """[NEW] 公开接口：获取当前符合条件的龙头个股数据列表"""
        with self._lock:
            # ⭐ 核心修复：在 Record 对象层面进行 Enum 比较，防止 dict 转换后的类型冲突
            recs = [r.to_dict() for r in self._records.values() 
                    if r.status != DragonStatus.ELIMINATED and (min_status is None or r.status >= min_status)]
            # 按连续新高排序 (降序)
            recs.sort(key=lambda x: (int(x['status']), x['consecutive_new_highs'], x['cum_pct_from_entry']), reverse=True)
            return recs

    def get_dragons(self, min_status=DragonStatus.CANDIDATE) -> List[DragonRecord]:
        """内部/外部：直接返回 Record 对象列表"""
        with self._lock:
            res = [r for r in self._records.values() if r.status != DragonStatus.ELIMINATED]
            if min_status is not None:
                res = [r for r in res if r.status >= min_status]
            return res

    # ── 生成龙头专属决策信号 ──────────────────────────────────────────────────

    def get_dragon_signal(self, code: str, sector_heat: float = 50.0) -> Optional[DecisionSignal]:
        """为 DRAGON / 盘中新高候选 生成高优先级决策信号"""
        with self._lock:
            rec = self._records.get(code)
        if rec is None or rec.status in (DragonStatus.ELIMINATED, DragonStatus.WARNING):
            return None
        # [MOD] 信号触发放宽：物理新高 或 涨幅保持在 5% 以上且今日不弱(dff>0)
        is_physical_new_hi = rec.today_high > rec.prev_day_high
        is_dynamic_strong  = rec.current_pct >= 5.0 and rec.dff > 0.5
        
        if rec.prev_day_high > 0 and not is_physical_new_hi and not is_dynamic_strong:
            return None
        if rec.current_price <= 0:
            return None

        base = 85 if rec.status == DragonStatus.DRAGON else 75
        priority = int(
            base
            + min(rec.consecutive_new_highs, 3) * 3   # 最多 +9
            + min(max(rec.cum_pct_from_entry, 0), 20) / 2  # 最多 +10
            + sector_heat * 0.10
            + max(0, rec.dff) * 1.5
        )
        priority = min(100, priority)

        tag = "🐉 真龙头" if rec.status == DragonStatus.DRAGON else "🌱 候选龙"
        reason = (
            f"{tag} 连续{rec.consecutive_new_highs}日新高 "
            f"累计{rec.cum_pct_from_entry:+.1f}% "
            f"跟踪{rec.tracked_days}日 dff={rec.dff:+.2f} "
            f"[{' '.join(rec.tags[-3:])}]"
        )
        suggest = round(rec.vwap * 1.001, 3) if rec.vwap > 0 else rec.current_price
        return DecisionSignal(
            code=code, name=rec.name, sector=rec.sector,
            signal_type=SignalType.HOT_FOLLOW,
            priority=priority,
            suggest_price=suggest,
            current_price=rec.current_price,
            change_pct=rec.current_pct,
            sector_heat=sector_heat,
            reason=reason,
            leader_code=code,
            is_leader=True,
            pct_diff=rec.cum_pct_from_entry,
            dff=rec.dff,
            sector_type="🐉 龙头持续",
        )

    # ── 查询接口 ──────────────────────────────────────────────────────────────

    def get_dragons(self, min_status: DragonStatus = DragonStatus.CANDIDATE) -> List[DragonRecord]:
        """获取当前龙头列表，按状态+连续新高天数排序"""
        with self._lock:
            recs = [r for r in self._records.values()
                    if r.status != DragonStatus.ELIMINATED and r.status >= min_status]
        return sorted(recs,
                      key=lambda r: (int(r.status), r.consecutive_new_highs, r.cum_pct_from_entry),
                      reverse=True)

    def get_count(self) -> dict:
        with self._lock:
            c = {'candidate': 0, 'dragon': 0, 'warning': 0}
            for r in self._records.values():
                if r.status == DragonStatus.CANDIDATE:   c['candidate'] += 1
                elif r.status == DragonStatus.DRAGON:    c['dragon']    += 1
                elif r.status == DragonStatus.WARNING:   c['warning']   += 1
        c['total'] = sum(c.values())
        return c

    def reset_day(self):
        """每日开盘前：清除已淘汰记录，为新交易日做准备（不清除跨日状态）"""
        with self._lock:
            elim = [c for c, r in self._records.items() if r.status == DragonStatus.ELIMINATED]
            for c in elim:
                del self._records[c]
        logger.info(f"[DragonTracker] 日重置: 移除淘汰={len(elim)} 存活={len(self._records)}")

    def sync_names(self, mapping: Dict[str, str]):
        """
        [NEW] 名称同步：修复内存中名称等于代码的记录
        由 Controller 定期或在数据注入时调用。
        """
        if not mapping:
            return
        with self._lock:
            updated = 0
            for code, rec in self._records.items():
                if rec.name == code or not rec.name:
                    new_name = mapping.get(code)
                    if new_name and new_name != code:
                        rec.name = new_name
                        updated += 1
            if updated > 0:
                logger.info(f"[DragonTracker] 成功修合同步 {updated} 只龙头的名称")

    # ── 历史深度挖掘 ──────────────────────────────────────────────────────────

    def mine_history_dragons(self, codes: List[str], days: int = 7, name_mapping: Optional[Dict[str, str]] = None):
        """
        [NEW] 核心逻辑：自动通过历史 K 线回溯挖掘龙头
        用于：手动执行引擎时的“自动补位”或“初始化回溯”
        """
        if tdd is None or not codes:
            return
        
        name_mapping = name_mapping or {}
        logger.info(f"🔍 [DragonTracker] 开始 7 日深度挖掘扫描 (池大小={len(codes)})...")
        found_new = 0
        
        for code in codes:
            # 1. 过滤已存在的活跃记录
            with self._lock:
                if code in self._records and self._records[code].status != DragonStatus.ELIMINATED:
                    continue
            
            try:
                # 2. 获取历史日线 (TDX)
                df = tdd.get_tdx_Exp_day_to_df(code, dl=days + 1, resample='d', fastohlc=True)
                if df is None or len(df) < 2:
                    continue
                
                # 3. 状态回溯重构 (State Reconstruction)
                consecutive_highs = 0
                cum_pct = 0.0
                first_low = -1.0
                has_fatal_break = False
                
                # 倒数第2根开始是昨日，最后1根是今日（或最近一交易日）
                # 我们按顺序模拟过去 3-5 天的表现
                for i in range(1, len(df)):
                    prev = df.iloc[i-1]
                    curr = df.iloc[i]
                    
                    c_high, c_low, c_close = float(curr['high']), float(curr['low']), float(curr['close'])
                    p_high, p_low, p_close = float(prev['high']), float(prev['low']), float(prev['close'])
                    
                    # 核心判定逻辑：显著尝试突破或维持高位 (需满足日高且收盘价相对稳定)
                    # [FIX] 增加收盘强度校验，并修复计数器不归零的逻辑缺陷
                    if c_high >= p_high and c_close >= p_close * 0.995: 
                        consecutive_highs += 1
                        if consecutive_highs == 1:
                            entry_p = p_close
                        # 累计涨幅基于入场点
                        cum_pct = (c_close / entry_p - 1) * 100 if entry_p > 0 else 0.0
                        entry_p = min(entry_p, p_close) if entry_p > 0 else entry_p
                    else:
                        # [FIX] 未创新高或收盈严重不及预期，计数归零
                        consecutive_highs = 0
                        if c_low < p_low * 0.970: # 严重破位 (3%)
                            has_fatal_break = True
                
                # 4. 判定入库条件
                # 显著降低冷启动门槛：只要有过 1 次新高，且没有发生恶性破位，就作为候选
                if consecutive_highs >= 1 and not has_fatal_break:
                    status = DragonStatus.DRAGON if consecutive_highs >= self.DRAGON_UPGRADE_DAYS else DragonStatus.CANDIDATE
                    
                    last_row = df.iloc[-1]
                    prev_row = df.iloc[-2] if len(df) > 1 else last_row
                    
                    with self._lock:
                        # 计算入场价 (首个新高日的前一日收盘)
                        e_idx = max(0, len(df)-1-consecutive_highs)
                        entry_price = float(df.iloc[e_idx]['close'])
                        current_price = float(last_row['close'])
                        cum_pct = (current_price / entry_price - 1) * 100 if entry_price > 0 else 0.0
                        
                        name = name_mapping.get(code) or str(last_row.get('name', code))
                        
                        rec = DragonRecord(
                            code=code,
                            name=name,
                            sector="", 
                            status=status,
                            confirmed_date=datetime.now().strftime('%Y%m%d'),
                            tracked_days=consecutive_highs + 1,
                            consecutive_new_highs=consecutive_highs,
                            prev_day_high=float(prev_row['high']),
                            prev_day_low=float(prev_row['low']),
                            prev_day_close=float(prev_row['close']),
                            today_high=float(last_row['high']),
                            today_low=float(last_row['low']),
                            entry_price=entry_price,
                            current_price=current_price,
                            cum_pct_from_entry=cum_pct, # ⭐ 补全必填参数
                            warning_days=0,            # ⭐ 补全必填参数
                            last_update=datetime.now().isoformat(),
                            tags=['历史回溯', f'{consecutive_highs}日新高'],
                        )
                        self._records[code] = rec
                        found_new += 1
            except Exception as e:
                logger.error(f"❌ [DragonMine] {code} error: {e}", exc_info=True)

        if found_new > 0:
            logger.info(f"✅ [DragonTracker] 历史挖掘完成: 发现 {found_new} 只存量龙头/候选")
            self._save_persist()

    def force_save(self):
        """外部强制持久化（可在面板关闭时调用）"""
        self._save_persist()


# ─────────────────────────────────────────────────────────────────────────────
# §4  盘中回踩买点检测（IntradayPullbackDetector）
# ─────────────────────────────────────────────────────────────────────────────

class IntradayPullbackDetector:
    """
    四种回踩买点形态检测（v2 使用真实 kline 序列）
    """

    MIN_DROP_FROM_HIGH   = -0.012    # [MOD] 回落容忍度收窄，强者恒强不深调
    MAX_DROP_FROM_VWAP   = -0.003    # [MOD] 必须贴身均线
    MAX_VOL_RATIO_DURING = 0.8       # [MOD] 缩量要求更严格
    MIN_SECTOR_HEAT      = 35.0      # [MOD] 门槛适度下调至 30.0，以增强弱势修复市场的灵敏度

    def __init__(self, sector_map: SectorFocusMap, star_engine: StarFollowEngine):
        self._sector_map = sector_map
        self._star_engine = star_engine
        self._triggered: Dict[str, datetime] = {}
        self._cooldown_sec = 1800
        self._lock = threading.Lock()

    def scan(
        self,
        code: str,
        name: str,
        current_price: float,
        day_high: float,
        vwap: float,
        vol_ratio: float,
        prev_close: float,
        last_5min_prices: List[float],
        sector_name: str,
        pct_diff: float = 0.0,
        dff: float = 0.0,
        index_pct: float = 0.0,  # [NEW] 指数涨跌幅
        ranks: Tuple[int, int] = (9999, 9999), # [NEW] (主力排名, 人气排名)
        ignore_cooldown: bool = False, # [NEW] 手动触发时绕过冷却时间
    ) -> Optional[DecisionSignal]:
        try:
            return self._check(
                code, name, current_price, day_high, vwap,
                vol_ratio, prev_close, last_5min_prices, sector_name,
                pct_diff, dff, index_pct, ranks, ignore_cooldown
            )
        except Exception as e:
            logger.debug(f"[Pullback] scan error {code}: {e}")
            return None

    def _check(
        self,
        code: str,
        name: str,
        price: float,
        day_high: float,
        vwap: float,
        vol_ratio: float,
        prev_close: float,
        prices5: List[float],
        sector: str,
        pct_diff: float,
        dff: float,
        index_pct: float = 0.0,
        ranks: Tuple[int, int] = (9999, 9999),
        ignore_cooldown: bool = False,
    ) -> Optional[DecisionSignal]:
        with self._lock:
            last = self._triggered.get(code)
        
        # [MOD] 手动强制执行模式忽略冷却时间
        if not ignore_cooldown and last and (datetime.now() - last).seconds < self._cooldown_sec:
            return None

        if price <= 0 or day_high <= 0:
            return None
        if vwap <= 0:
            vwap = price

        change_pct = (price / prev_close - 1) * 100 if prev_close > 0 else 0.0

        sh = self._sector_map.get_sector_heat(sector)
        sector_heat = sh.heat_score if sh else 0.0
        leader_code = sh.leader_code if sh else ''
        sector_type = sh.sector_type if sh else ''

        if sector_heat < self.MIN_SECTOR_HEAT:
            logger.debug(f"[Pullback] {code} 被拦截: 板块热度({sector_heat:.1f}) < 阈值({self.MIN_SECTOR_HEAT})")
            return None

        drop_from_high = (price - day_high) / day_high if day_high > 0 else 0.0
        diff_from_vwap = (price - vwap) / vwap if vwap > 0 else 0.0

        # ── [C] 强势前置条件：硬性剔除弱势股与结构破坏的个股 ──────────────────
        # ── [C] 强势前置条件：必须是启动中的“蛟龙” ──────────────────
        # 1. 启动阳线收盘价不破原则：如果跌破昨日收盘（启动点），直接宣告死亡
        if price < prev_close:
            logger.debug(f"[Pullback] {code} 被拦截: 价格({price}) < 昨收({prev_close})")
            return None
        
        # 2. 涨幅门槛：非极端强势不入场 (启动点通常在 3%~5% 以上)
        if change_pct < 2.0:           # [MOD] 门槛下调至 2.0%
            logger.debug(f"[Pullback] {code} 被拦截: 涨幅({change_pct:.2f}%) < 2.0%")
            return None
        
        # 3. 分时结构：必须在均价线之上运行 (VWAP 是多空生死线)
        if diff_from_vwap < -0.005:    
            logger.debug(f"[Pullback] {code} 被拦截: 破均线({diff_from_vwap*100:.2f}%)")
            return None
        
        # [NEW] 开盘 10 分钟加权：09:30-09:40 是黄金狙击时段
        now_time = datetime.now()
        is_morning_rush = (now_time.hour == 9 and 30 <= now_time.minute <= 40)
        morning_bonus = 20 if is_morning_rush else 0

        signal_type = None
        reason = ""
        priority = 0

        # 形态1：飞刀接落 — 回踩≥1.5% + 贴近VWAP + 缩量
        if (drop_from_high <= self.MIN_DROP_FROM_HIGH and
                self.MAX_DROP_FROM_VWAP <= diff_from_vwap <= 0.005 and
                vol_ratio <= self.MAX_VOL_RATIO_DURING):
            signal_type = SignalType.PULLBACK_BUY
            reason = (f"飞刀接落: 回落{drop_from_high*100:.1f}% "
                      f"贴近均价{diff_from_vwap*100:.2f}% 缩量{vol_ratio:.2f} "
                      f"周期涨幅{pct_diff:+.2f}%")
            # dff 正值（主力流入）加分
            priority = int(60 + sector_heat * 0.3 + max(0, dff) * 2)

        # 形态2：VWAP支撑 — 当前价在VWAP附近±0.3%，量放大，龙头强势确认（未弱化）
        elif (abs(diff_from_vwap) <= 0.003 and
              vol_ratio >= 1.0 and
              self._star_engine.is_leader_strong(leader_code)):  # [C] 用 is_leader_strong 替代 is_leader_confirmed
            signal_type = SignalType.VWAP_SUPPORT
            reason = (f"均线支撑: 均价差{diff_from_vwap*100:.2f}% "
                      f"龙头{leader_code}强势确认 dff={dff:+.2f}")
            priority = int(55 + sector_heat * 0.25 + max(0, dff) * 1.5)

        # 形态3：板块共振点 — 龙头强势确认，附近上翘，且周期内有明显涨幅
        elif (self._star_engine.is_leader_strong(leader_code) and  # [C] 用 is_leader_strong
              len(prices5) >= 3 and
              prices5[-1] > prices5[-3] and
              diff_from_vwap >= -0.008 and
              pct_diff >= 0.3):   # [C] 从 0.1% 提升到 0.3%，过滤微弱震荡
            signal_type = SignalType.SECTOR_BREAKOUT
            reason = (f"板块共振: 龙头{leader_code}强势确认 "
                      f"跟进股上翘 均价差{diff_from_vwap*100:.2f}% "
                      f"周期涨幅{pct_diff:+.2f}%")
            priority = int(70 + sector_heat * 0.3 + pct_diff * 2)

        # 形态4：强势蓄势突破 — 板块类型为蓄势/强攻，且 dff 为正
        elif ('蓄势' in sector_type or '强攻' in sector_type):
            if pct_diff >= 0.5 and dff > 0 and diff_from_vwap >= -0.005:
                signal_type = SignalType.HOT_FOLLOW
                reason = (f"强势蓄势: 周期涨幅{pct_diff:+.2f}% dff={dff:+.2f} 站稳均线")
                priority = int(65 + sector_heat * 0.25 + pct_diff * 4 + dff)

        # 形态5：[NEW] 中阳起步确认 — 擒贼擒王，紧跟启动
        # 判断标准：周期内涨幅 > 5% (必须是大阳穿透)，主力流入，且处于均线上方
        if signal_type is None:
            trigger_pct = 5.0
            if pct_diff >= trigger_pct and dff > 0 and diff_from_vwap >= 0:
                signal_type = SignalType.HOT_FOLLOW
                is_king = (code == leader_code)
                is_breakout = pct_diff >= 7.0 # [NEW] 7% 以上视为穿透上轨的大阳
                tag = "🚀 龙头突破" if (is_king and is_breakout) else ("👑 龙头起步" if is_king else "👥 跟随共振")
                reason = (f"{tag}: 启动幅度{pct_diff:+.1f}% 资金dff={dff:+.2f} 站稳启动均线上方")
                priority = int(80 + sector_heat * 0.2 + pct_diff * 4 + morning_bonus)

        if signal_type is None:
            return None

        with self._lock:
            self._triggered[code] = datetime.now()

        # ─────────────────────────────────────────────────────────
        # §D  [NEW] 外部提权与大盘逆势策略逻辑
        # ─────────────────────────────────────────────────────────
        zhuli_rank, hot_rank = ranks
        priority_bonus = 0
        extra_reason = []

        # 1. 55188 人气/主力提权
        if zhuli_rank <= 100:
            priority_bonus += 15
            extra_reason.append(f"[主力榜{zhuli_rank}]")
        elif zhuli_rank <= 300:
            priority_bonus += 5
            
        if hot_rank <= 50:
            priority_bonus += 12
            extra_reason.append(f"[人气榜{hot_rank}]")
        elif hot_rank <= 150:
            priority_bonus += 5

        # 2. 大盘逆势差异性策略 (Divergence / Relative Strength)
        # 策略定义：大盘不给力时个股显露真金 (Alpha 挖掘)
        if index_pct < -0.3 and pct_diff > 0.5:
            # 大盘跌，个股逆势涨超过0.5% (强力逆势)
            priority_bonus += 15
            extra_reason.append("📈 逆势领涨")
        elif index_pct < 0.2 and pct_diff > 2.0:
            # 大盘平或微涨，个股暴力拉升 (独立强攻)
            priority_bonus += 10
            extra_reason.append("🛡️ 独立强攻")
        elif index_pct > 0.8 and pct_diff < 0.2:
            # 大盘大涨，个股滞涨 (弱于大盘，减分)
            priority_bonus -= 10
        
        # 应用提权
        priority = min(100, int(priority + priority_bonus))
        if extra_reason:
            reason = " ".join(extra_reason) + " " + reason

        return DecisionSignal(
            code=code,
            name=name,
            sector=sector,
            signal_type=signal_type,
            priority=priority,
            suggest_price=round(vwap * 1.001, 3),
            current_price=price,
            change_pct=change_pct,
            sector_heat=sector_heat,
            reason=reason,
            leader_code=leader_code,
            is_leader=(code == leader_code),
            pct_diff=pct_diff,
            dff=dff,
            sector_type=sector_type,
        )

    def reset_day(self):
        with self._lock:
            self._triggered.clear()


# ─────────────────────────────────────────────────────────────────────────────
# §5  交易决策队列（DecisionQueue）
# ─────────────────────────────────────────────────────────────────────────────

class DecisionQueue:
    """实时交易决策优先级队列"""

    MAX_QUEUE_SIZE = 50

    def __init__(self):
        self._signals: Dict[str, DecisionSignal] = {}
        self._lock = threading.Lock()

    def push(self, signal: DecisionSignal):
        with self._lock:
            existing = self._signals.get(signal.code)
            if existing:
                signal.hits = getattr(existing, 'hits', 1) + 1
                if signal.priority < existing.priority:
                    signal.priority = existing.priority  # 保留高优先级
            self._signals[signal.code] = signal
            
            if len(self._signals) > self.MAX_QUEUE_SIZE:
                self._evict_lowest()

    def _evict_lowest(self):
        if not self._signals:
            return
        min_code = min(self._signals, key=lambda c: self._signals[c].priority)
        del self._signals[min_code]

    def get_sorted(self, status_filter: Optional[str] = "待处理") -> List[DecisionSignal]:
        with self._lock:
            signals = list(self._signals.values())
        if status_filter and status_filter != "ALL":
            signals = [s for s in signals if s.status == status_filter]
        return sorted(signals, key=lambda s: s.priority, reverse=True)

    def update_status(self, code: str, status: str):
        with self._lock:
            if code in self._signals:
                self._signals[code].status = status

    def remove(self, code: str):
        with self._lock:
            self._signals.pop(code, None)

    def clear_non_pending(self):
        with self._lock:
            done = [c for c, s in self._signals.items() if s.status in ('已忽略', '已成交')]
            for c in done:
                del self._signals[c]

    def size(self) -> int:
        with self._lock:
            return len(self._signals)

    def reset_day(self):
        with self._lock:
            self._signals.clear()


# ─────────────────────────────────────────────────────────────────────────────
# §6  离场条件监控（ExitMonitor）
# ─────────────────────────────────────────────────────────────────────────────

class ExitMonitor:
    """持仓离场条件监控（v2 使用 detector 快照精确计算龙头跌幅）"""

    LEADER_CRASH_THRESHOLD  = -2.0
    NO_HIGH_CHECK_HOUR      = 14
    VWAP_BREAK_HOUR         = 14
    VWAP_BREAK_MINUTE       = 30

    def __init__(self, sector_map: SectorFocusMap):
        self._sector_map = sector_map
        self._position_highs: Dict[str, float] = {}
        self._lock = threading.Lock()

    def update_position_high(self, code: str, current_price: float):
        with self._lock:
            if current_price > self._position_highs.get(code, 0.0):
                self._position_highs[code] = current_price

    def check(
        self,
        code: str,
        name: str,
        sector: str,
        current_price: float,
        vwap: float,
        leader_change_from_high_pct: float,
    ) -> ExitReason:
        exit_mask = ExitReason.NONE
        now = datetime.now()

        if leader_change_from_high_pct <= self.LEADER_CRASH_THRESHOLD:
            exit_mask |= ExitReason.LEADER_CRASH
            logger.info(f"[ExitMonitor] {code} 触发-龙头杀跌 "
                        f"龙头跌幅={leader_change_from_high_pct:.2f}%")

        if now.hour >= self.NO_HIGH_CHECK_HOUR:
            with self._lock:
                day_high = self._position_highs.get(code, current_price)
            if current_price < day_high * 0.998:
                exit_mask |= ExitReason.NO_NEW_DAY_HIGH
                logger.info(f"[ExitMonitor] {code} 触发-未创新高 "
                            f"当前={current_price:.3f} 日高={day_high:.3f}")

        if (now.hour >= self.VWAP_BREAK_HOUR and
                now.minute >= self.VWAP_BREAK_MINUTE and
                vwap > 0 and current_price < vwap * 0.998):
            exit_mask |= ExitReason.VWAP_BREAK_CLOSE
            logger.info(f"[ExitMonitor] {code} 触发-尾盘破均价 "
                        f"价={current_price:.3f} 均={vwap:.3f}")

        return exit_mask

    def remove_position(self, code: str):
        with self._lock:
            self._position_highs.pop(code, None)

    def reset_day(self):
        with self._lock:
            self._position_highs.clear()


# ─────────────────────────────────────────────────────────────────────────────
# §7  外观门面（SectorFocusController）— 整合所有引擎
# ─────────────────────────────────────────────────────────────────────────────

class SectorFocusController:
    """
    盘中交易决策总控制器  v2
    ──────────────────────────
    新增 inject_from_detector() — 直接从 BiddingMomentumDetector 实例注入
    完整的板块图和个股快照，彻底打通竞价面板 → 决策引擎数据链。
    """

    def __init__(self):
        self.sector_map        = SectorFocusMap()
        self.star_engine       = StarFollowEngine(self.sector_map)
        self.pullback_detector = IntradayPullbackDetector(self.sector_map, self.star_engine)
        self.decision_queue    = DecisionQueue()
        self.exit_monitor      = ExitMonitor(self.sector_map)
        self.dragon_tracker    = DragonLeaderTracker()  # [Dragon] 龙头跨日持续跟踪器

        self._lock = threading.Lock()
        self._bidding_scores: Dict[str, float] = {}
        self._hot_rank_map: Dict[str, int] = {}
        self._df_realtime: Optional[pd.DataFrame] = None
        self._index_pct_diff: float = 0.0          # [NEW] 指数基准涨幅
        self._last_55188_sync: float = 0.0        # [NEW] 55188 同步节拍
        self.decision_buy_details: List[str] = [] # [NEW] 买点信号聚合记录

        self._last_full_update: float = 0.0
        self._full_update_interval = float(getattr(cct.CFG, 'duration_sleep_time', 60.0)) #30.0   # 全量计算30秒一次
        self._last_snapshot_date = ""      # [Dragon] 记录今日是否执行过收盘快照
        self._last_30m_slot = -1           # [Dragon] 记录上一个 30 分钟同步槽位 (9:30 offset=0)
        self._name_cache: Dict[str, str] = {}  # [NEW] 代码 -> 名称映射缓存

    def _get_stock_name(self, code: str, default: Optional[str] = None) -> str:
        """获取股票名称，优先从缓存获取，或从实时数据动态补全"""
        name = self._name_cache.get(code)
        if name and name != code:
            return name
        
        # 尝试通过实时数据补全
        with self._lock:
            if self._df_realtime is not None and code in self._df_realtime.index:
                name = str(self._df_realtime.loc[code, 'name'])
                if name and name != code:
                    self._name_cache[code] = name
                    return name
        
        return default if default else code

    def update_name_cache(self, mapping: Dict[str, str]):
        """外部注入名称映射"""
        with self._lock:
            self._name_cache.update(mapping)


    # ── 数据注入（可从多个线程调用）────────────────────────────────────────

    def inject_realtime(self, df: pd.DataFrame):
        """注入实时行情 DataFrame"""
        with self._lock:
            self._df_realtime = df
            if df is not None and not df.empty and 'name' in df.columns:
                # 增量更新名称缓存
                names = df['name'].dropna().to_dict()
                self._name_cache.update(names)
                # 同步修复已经追踪的龙头名称
                self.dragon_tracker.sync_names(names)


    def inject_bidding(self, scores: Dict[str, float]):
        """注入竞价评分 {code: score}（旧接口兼容保留）"""
        with self._lock:
            self._bidding_scores = scores
        self.sector_map.inject_bidding_scores(scores)

    def inject_ext_data(self, df: pd.DataFrame):
        """注入 55188 数据"""
        self.sector_map.inject_ext_data(df)
        if not df.empty and 'hot_rank' in df.columns and 'code' in df.columns:
            with self._lock:
                self._hot_rank_map = df.set_index('code')['hot_rank'].dropna().to_dict()

    def inject_from_detector(self, detector) -> bool:
        """
        [v2 核心接口] 直接从 BiddingMomentumDetector 实例注入完整数据。

        注入内容：
          1. 板块图（active_sectors）→ SectorFocusMap.inject_detector_sectors()
          2. 个股评分快照（_global_snap_cache）
          3. 竞价评分（TickSeries.score）→ inject_bidding_scores()
          4. 更新 comparison_interval 为 60 分钟（若当前是默认值）

        返回：True=成功注入，False=detector 无数据跳过
        """
        try:
            if detector is None:
                return False

            # 1. 确保 comparison_interval 为 60 分钟
            if hasattr(detector, 'comparison_interval'):
                if detector.comparison_interval < 3600:
                    detector.comparison_interval = 3600
                    logger.info("[SectorFocusController] comparison_interval 已更新为 60 分钟")

            # 2. 获取板块数据
            active_sectors = detector.get_active_sectors()
            if not active_sectors:
                return False

            # 3. 获取个股快照（_global_snap_cache 内含完整 pct_diff/dff/klines）
            with detector._lock:
                stock_snap = dict(detector._global_snap_cache)
            
            # [NEW] 补全名称缓存
            if stock_snap:
                names = {c: str(s.get('name', c)) for c, s in stock_snap.items() if s.get('name')}
                if names:
                    with self._lock:
                        self._name_cache.update(names)
                    self.dragon_tracker.sync_names(names)

            # 4. 注入板块图（优先通道）

            self.sector_map.inject_detector_sectors(active_sectors, stock_snap)

            # 5. 同步竞价评分 {code: score}（兼容旧通道）
            bid_scores = {}
            with detector._lock:
                for code, ts in detector._tick_series.items():
                    if ts.score > 0:
                        bid_scores[code] = ts.score
            if bid_scores:
                self.sector_map.inject_bidding_scores(bid_scores)
                with self._lock:
                    self._bidding_scores = bid_scores

            logger.debug(
                f"[SectorFocusController] inject_from_detector: "
                f"{len(active_sectors)} sectors, {len(stock_snap)} stocks"
            )
            return True

        except Exception as e:
            logger.warning(f"[SectorFocusController] inject_from_detector failed: {e}")
            return False

    def inject_market_indices(self, indices: Dict[str, Any]):
        """注入大盘指数数据，用于计算逆势差异性 [NEW]"""
        try:
            # 优先采用 创业板(深) 或 上证 作为基准
            sh_pct = float(indices.get('sh000001', 0.0) or 0.0)
            cyb_pct = float(indices.get('sz399006', 0.0) or 0.0)
            
            with self._lock:
                # 选取波幅较大的指数作为日内基准
                self._index_pct_diff = cyb_pct if abs(cyb_pct) > abs(sh_pct) else sh_pct
        except Exception:
            pass

    # ── 主循环 Tick（在后台线程中周期性调用）────────────────────────────────

    def tick(self, force: bool = False):
        """
        单次行情 Tick 处理
        - 决策队列与板块热力的核心驱动泵
        """
        if force:
            logger.info("🛠️ [Controller] 引擎手动触发执行 (Manual Run Triggered)")
        
        now = time.time()
        # [MOD] 手动或周期同步 55188 缓存数据
        if force or (now - self._last_55188_sync > 300):
            self.sector_map.load_55188_cache()
            with self._lock:
                self._last_55188_sync = now
        
        # ... (数据准备)
        df = None
        with self._lock:
            df = self._df_realtime
            bidding = dict(self._bidding_scores)
            hot_rank = dict(self._hot_rank_map)

        # [MOD] 强制模式下直接进入板块热力计算，不查 30s 节流；且在 force=True 时必然执行降级聚合计算以确保 UI 响应
        today_date = datetime.now().strftime('%Y%m%d')
        
        # [Dragon] 自动收盘快照检测 (每天 15:00 - 15:10 之间触发一次)
        now_dt = datetime.now()
        if now_dt.hour == 15 and 0 <= now_dt.minute <= 10:
            if self._last_snapshot_date != today_date:
                logger.info(f"🕒 [Controller] 检测到收盘时间，自动触发龙头归档快照: {today_date}")
                self.run_daily_close_snapshot()
                self._last_snapshot_date = today_date

        # [Dragon] 30 分钟整点强制扫描检测 (9:30, 10:00, 10:30, 11:00, 13:30, 14:00, 14:30)
        # 计算 09:30 开始的分钟偏移量
        m_offset = (now_dt.hour * 60 + now_dt.minute) - 570  # 9:30 = 570min
        if 0 <= m_offset <= 330: # 交易时间内 (9:30 - 15:00)
            slot = m_offset // 30
            if slot != self._last_30m_slot:
                logger.info(f"⏰ [Controller] 到达 30 分钟同步节点 (Offset={m_offset}m, Slot={slot}), 触发全量引擎对齐")
                force = True # 强制执行下方全量计算逻辑
                self._last_30m_slot = slot
                # 执行一次龙头状态固化，确保持久化最新
                self.dragon_tracker._save_persist()

        if force or (now - self._last_full_update >= self._full_update_interval):
            try:
                if df is not None and not df.empty:
                    with self.sector_map._lock:
                        has_detector_data = bool(self.sector_map._sector_map)

                    # [FIX] 如果是手动强制运行 (force=True)，则必须重新聚合计算一遍本地数据，否则 UI 点击 [引擎执行] 没反应
                    if force or not has_detector_data:
                        self.sector_map.update(df)

                    new_leaders = self.star_engine.confirm_leaders(df, bidding, hot_rank)

                    # [Dragon] 将新确认的龙头导入候选名单
                    for ldr_code in new_leaders:
                        try:
                            sec_name = self.sector_map.get_sector_of_code(ldr_code) or ''
                            ldr_sh   = self.sector_map.get_sector_heat(sec_name)
                            ldr_snap = self.sector_map.get_stock_snap(ldr_code)
                            if ldr_snap:
                                name = self._get_stock_name(ldr_code, str(ldr_snap.get('name', ldr_code)))
                                self.dragon_tracker.add_candidate(
                                    code=ldr_code,
                                    name=name,
                                    sector=sec_name,
                                    current_price=float(ldr_snap.get('price', 0.0)),
                                    sector_heat=ldr_sh.heat_score if ldr_sh else 0.0,
                                )
                        except Exception:
                            pass

                    # [Dragon] 自动检测日期变更，触发次日批量初始化
                    today_str = datetime.now().strftime('%Y%m%d')
                    if today_str != self.dragon_tracker._today_str:
                        with self.sector_map._lock:
                            all_snaps = dict(self.sector_map._detector_stock_snap)
                        self.dragon_tracker.auto_next_day_validate_all(all_snaps)

                self._last_full_update = now
            except Exception as e:
                logger.warning(f"[Controller] full update failed: {e}")


        # 实时扫描回踩买点
        if df is not None and not df.empty:
            self._scan_pullbacks(df, force=force)
        else:
            if force:
                logger.warning("⚠️ [Controller] 引擎扫描跳过: _df_realtime 为空")

    def _scan_pullbacks(self, df: pd.DataFrame, force: bool = False):
        """扫描所有板块跟进股的回踩买点（v2：使用 kline 计算真实 prices5）"""
        # [MOD] 扩大扫描宽度 (从 8 -> 15)，覆盖更广泛的轮动板块
        hot_sectors = self.sector_map.get_hot_sectors(top_n=15)

        for sh in hot_sectors:
            # 龙头自身 + 跟进股
            target_codes = [sh.leader_code] + list(sh.follower_codes[:MAX_FOLLOWERS_PER_SECTOR])

            for code in target_codes:
                if not code:
                    continue
                try:
                    idx_pct = getattr(self, '_index_pct_diff', 0.0)
                    ranks = self.sector_map.get_stock_ranks(code)
                    self._scan_one_v2(code, sh, index_pct=idx_pct, ranks=ranks, force=force)
                except Exception as e:
                    logger.debug(f"[scan_pullbacks] {code}: {e}")

        # [Dragon] 龙头持续跟踪信号扫描（priority 75+，重点标记）
        try:
            dragons = self.dragon_tracker.get_dragons(min_status=DragonStatus.CANDIDATE)
            for rec in dragons:
                snap = self.sector_map.get_stock_snap(rec.code)
                
                # --- [FIX] 增加从 df_realtime 回退提取逻辑，防止因 snap 缺失导致数据为 0 ---
                price, vwap, dff, pct, day_high, day_low = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
                
                
                if df is not None and not df.empty:
                    # 降级：从主行情表匹配
                    try:
                        row = df.loc[rec.code] if rec.code in df.index else df[df['code'] == rec.code].iloc[0]
                        price      = float(row.get('trade', row.get('price', 0)) or 0)
                        day_high   = float(row.get('high', price) or price)
                        day_low    = float(row.get('low', price) or price)
                        vwap       = float(row.get('nclose', row.get('lastp1d', price)) or price)
                        pct        = float(row.get('percent', 0.0))
                        dff        = float(row.get('dff', 0.0))
                    except (KeyError, IndexError):
                        continue # 两边都找不到，跳过
                elif snap:
                    price      = float(snap.get('price', 0.0))
                    day_high   = float(snap.get('high_day', 0.0))
                    day_low    = float(snap.get('low_day', snap.get('price', 0.0)))
                    vwap       = float(snap.get('vwap', snap.get('price', 0.0)))
                    dff        = float(snap.get('dff', 0.0))
                    pct        = float(snap.get('pct', 0.0))
                else:
                    continue # 无数据源，跳过
                # ----------------------------------------------------------------------

                try:
                    sec_name = rec.sector or self.sector_map.get_sector_of_code(rec.code) or ''
                    ldr_sh   = self.sector_map.get_sector_heat(sec_name)
                    s_heat   = ldr_sh.heat_score if ldr_sh else 50.0
                    
                    # 更新盘中实时状态
                    self.dragon_tracker.intraday_update(
                        code=rec.code,
                        current_price=price,
                        day_high=day_high,
                        day_low=day_low,
                        vwap=vwap,
                        dff=dff,
                        current_pct=pct,
                        sector_heat=s_heat,
                    )
                    # 生成龙头专属决策信号
                    dragon_sig = self.dragon_tracker.get_dragon_signal(rec.code, s_heat)
                    if dragon_sig:
                        self.decision_queue.push(dragon_sig)
                        # [MOD] 采用聚合日志，避免刷屏
                        self.dragon_tracker.dragon_details.append(
                            f"🐉 {rec.code}({rec.name}) priority={dragon_sig.priority} {dragon_sig.reason}"
                        )
                except Exception as e:
                    logger.debug(f"[Dragon] scan {rec.code}: {e}")
            
            # [NEW] 集中打印破位报警，防止刷屏
            if self.dragon_tracker.breakdown_details:
                count = len(self.dragon_tracker.breakdown_details)
                if count > cct.loop_counter_limit:
                    summary = "\n".join(self.dragon_tracker.breakdown_details[:cct.loop_counter_limit])
                    logger.warning(f"⚠️ [Dragon-Breakdown] 集中破位(共{count}只):\n{summary}\n...等其它{count-cct.loop_counter_limit}只")
                else:
                    summary = "\n".join(self.dragon_tracker.breakdown_details)
                    logger.warning(f"⚠️ [Dragon-Breakdown] 发现破位:\n{summary}")
                self.dragon_tracker.breakdown_details.clear()
            
            # [NEW] 集中打印龙头信号，防止刷屏
            if self.dragon_tracker.dragon_details:
                count = len(self.dragon_tracker.dragon_details)
                if count > cct.loop_counter_limit:
                    summary = "\n".join(self.dragon_tracker.dragon_details[:cct.loop_counter_limit])
                    logger.warning(f"🚀 [Dragon-Signals] 发现强势信号(共{count}只):\n{summary}\n...等其它{count-cct.loop_counter_limit}只")
                else:
                    summary = "\n".join(self.dragon_tracker.dragon_details)
                    logger.warning(f"🚀 [Dragon-Signals] 触发信号:\n{summary}")
                self.dragon_tracker.dragon_details.clear()
                
            # [NEW] 集中打印买点信号，防止刷屏
            if self.decision_buy_details:
                count = len(self.decision_buy_details)
                if count > cct.loop_counter_limit:
                    summary = "\n".join(self.decision_buy_details[:cct.loop_counter_limit])
                    logger.warning(f"✅ [Decision-Buy] 发现买点(共{count}只):\n{summary}\n...等其它{count-cct.loop_counter_limit}只")
                else:
                    summary = "\n".join(self.decision_buy_details)
                    logger.warning(f"✅ [Decision-Buy] 触发买点:\n{summary}")
                self.decision_buy_details.clear()

        except Exception as e:
            logger.debug(f"[Dragon] dragon scan failed: {e}")

    def manual_run(self):
        """[NEW] 手动强制执行引擎全链路逻辑（用于 UI 触发/调试测试）"""
        logger.info("⚡ [SectorFocusController] 手动强制触发全链路重算...")
        
        # 1. 深度回溯扫描：尝试从现有的板块龙头中挖掘历史存量
        try:
            potential_codes = []
            hot_sectors = self.sector_map.get_hot_sectors(top_n=20)
            for sh in hot_sectors:
                if sh.leader_code: potential_codes.append(sh.leader_code)
                potential_codes.extend(sh.follower_codes[:2])
            
            if potential_codes:
                # 自动挖掘过去 7 天，传入当前已有的名称映射
                self.dragon_tracker.mine_history_dragons(
                    list(set(potential_codes)), 
                    days=7, 
                    name_mapping=self._name_cache
                )
                
                # 补全板块名称 (刚才挖掘时没带板块)
                with self.dragon_tracker._lock:
                    for code, r in self.dragon_tracker._records.items():
                        if not r.sector:
                            r.sector = self.sector_map.get_sector_of_code(code) or ''
        except Exception as e:
            logger.warning(f"[ManualRun] History mining failed: {e}")

        # 2. 正常全链路刷新
        # 强制下发 force=True 以绕过内部所有节流
        self.tick(force=True)
        logger.info("✅ [SectorFocusController] 手动全链路刷新完成")

    def _scan_one_v2(self, code: str, sh: SectorHeat, index_pct: float = 0.0, ranks: Tuple[int, int] = (9999, 9999), force: bool = False):
        """
        [v2] 对单只股扫描买点，优先使用 detector 快照数据（含真实 klines）
        """
        # 优先从 detector 快照获取丰富数据
        snap = self.sector_map.get_stock_snap(code)

        # 从 detector 快照提取
        if snap:
            price      = float(snap.get('price', 0.0))
            day_high   = float(snap.get('high_day', price))
            prev_close = float(snap.get('last_close', 0.0))
            name       = self._get_stock_name(code, str(snap.get('name', code)))

            pct_diff   = float(snap.get('pct_diff', 0.0))
            dff        = float(snap.get('dff', 0.0))
            vwap       = float(snap.get('vwap', snap.get('price', price)))
            klines     = snap.get('klines', [])

            # [MOD] 移除本地冗余计算，直接信任探测器快照提供的量比数据
            vol_ratio = float(snap.get('vol_ratio', 1.0))

            # 真实 prices5：最近5根 kline 的收盘价
            prices5 = [float(k.get('close', price)) for k in klines[-5:]] if klines else [price]

        else:
            # 降级：从 df_realtime 取基础数据
            with self._lock:
                df = self._df_realtime
            if df is None or df.empty:
                return
            try:
                row = df.loc[code] if code in df.index else df[df['code'] == code].iloc[0]
            except (KeyError, IndexError):
                return

            price      = float(row.get('trade', row.get('price', 0)) or 0)
            day_high   = float(row.get('high', price) or price)
            vwap       = float(row.get('vwap', row.get('average', price)) or price)
            vol_ratio  = float(row.get('ratio', 1.0) or 1.0)
            prev_close = float(row.get('lastp1d', row.get('prev_close', 0)) or 0)
            name       = self._get_stock_name(code, str(row.get('name', code)))
            # [FIX] 关键修复：从实时表取当前涨幅作为对比基准，不再由于硬编码为 0 导致过滤失效
            pct_diff   = float(row.get('percent', 0.0)) 
            dff        = float(row.get('dff', 0.0) or 0.0)
            prices5    = [price]

        if price <= 0 or prev_close <= 0:
            return

        signal = self.pullback_detector.scan(
            code=code,
            name=name,
            current_price=price,
            day_high=day_high,
            vwap=vwap,
            vol_ratio=vol_ratio,
            prev_close=prev_close,
            last_5min_prices=prices5,
            sector_name=sh.name,
            pct_diff=pct_diff,
            dff=dff,
            index_pct=index_pct,
            ranks=ranks,
            ignore_cooldown=force, # [MOD] 透传强制扫描标志，忽略冷却周期
        )

        if signal:
            self.decision_queue.push(signal)
            # [MOD] 采用聚合日志，避免刷屏
            self.decision_buy_details.append(
                f"✅ {code}({name}) priority={signal.priority} type={signal.signal_type.name} "
                f"pct={pct_diff:+.2f}% dff={dff:+.2f} {signal.reason}"
            )

    # ── 对外查询接口 ─────────────────────────────────────────────────────────

    def get_hot_sectors(self, top_n: int = 10) -> List[dict]:
        return [s.to_dict() for s in self.sector_map.get_hot_sectors(top_n)]

    def get_decision_queue(self) -> List[dict]:
        # [MOD] 默认返回全部活跃信号，防止因状态过滤导致界面看起来没数据
        return [s.to_dict() for s in self.decision_queue.get_sorted(status_filter="ALL")]

    def check_exit(
        self,
        code: str,
        name: str,
        current_price: float,
        vwap: float,
    ) -> ExitReason:
        sector = self.sector_map.get_sector_of_code(code) or ''
        sh = self.sector_map.get_sector_heat(sector)

        # v2：从 detector 快照精确计算龙头从日高的跌幅
        leader_from_high = 0.0
        if sh and sh.leader_code:
            l_snap = self.sector_map.get_stock_snap(sh.leader_code)
            if l_snap:
                l_price = float(l_snap.get('price', 0.0))
                l_high  = float(l_snap.get('high_day', l_price))
                if l_high > 0 and l_price > 0:
                    leader_from_high = (l_price - l_high) / l_high * 100.0
            else:
                # 粗估
                leader_from_high = sh.leader_change_pct - 10.0

        self.exit_monitor.update_position_high(code, current_price)
        return self.exit_monitor.check(
            code=code,
            name=name,
            sector=sector,
            current_price=current_price,
            vwap=vwap,
            leader_change_from_high_pct=leader_from_high,
        )

    def reset_day(self):
        """每日重置（开盘前调用）"""
        self.star_engine.reset_day()
        self.pullback_detector.reset_day()
        self.decision_queue.reset_day()
        self.exit_monitor.reset_day()
        self.dragon_tracker.reset_day()  # [Dragon] 清理已淘汰，保留跨日状态
        logger.info("[Controller] 每日重置完成")

    # [Dragon] 龙头追踪对外接口 ─────────────────────────────────────────────

    def get_dragon_leaders(
        self, min_status: DragonStatus = DragonStatus.CANDIDATE
    ) -> List[dict]:
        """获取龙头追踪列表（UI 消费接口）"""
        # [NEW] 在返回前最后一次同步修复名称，防止冷启动或快照导致的代码显示
        if self._name_cache:
            self.dragon_tracker.sync_names(self._name_cache)
        return [r.to_dict() for r in self.dragon_tracker.get_dragons(min_status)]

    def get_dragon_count(self) -> dict:
        """获取龙头数量统计 {'candidate': N, 'dragon': N, 'warning': N, 'total': N}"""
        return self.dragon_tracker.get_count()

    def run_daily_close_snapshot(self) -> dict:
        """
        收盘后（~15:00）手动调用：
        固化日高低，自动升级/淘汰，保存 JSON。
        返回 {'upgraded': [...], 'eliminated': [...]}
        """
        result = self.dragon_tracker.daily_close_snapshot()
        logger.info(f"[Controller] 龙头日收盘快照: {result}")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# §8  全局单例
# ─────────────────────────────────────────────────────────────────────────────

_controller_instance: Optional[SectorFocusController] = None
_controller_lock = threading.Lock()


def get_focus_controller() -> SectorFocusController:
    """获取全局 SectorFocusController 单例"""
    global _controller_instance
    with _controller_lock:
        if _controller_instance is None:
            _controller_instance = SectorFocusController()
    return _controller_instance
