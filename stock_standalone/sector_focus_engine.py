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
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Dict, List, Optional, Tuple, Any

import pandas as pd

logger = logging.getLogger(__name__)

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
    updated_at: datetime       = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
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
            'sector_type': self.sector_type,
            'tags': self.tags,
            'follower_codes': self.follower_codes,
            'follower_detail': self.follower_detail,
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

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'name': self.name,
            'sector': self.sector,
            'signal_type': self.signal_type.name,
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
            'created_at': self.created_at.strftime('%H:%M:%S'),
            'status': self.status,
        }


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
        self._last_update: Optional[datetime] = None
        # v2: 来自 detector 的完整个股快照 {code: snap_dict}
        self._detector_stock_snap: Dict[str, dict] = {}

    # ── 旧接口兼容 ────────────────────────────────────────────────────────────

    def inject_bidding_scores(self, scores: Dict[str, float]):
        """注入竞价评分 {code: score}（旧接口，兼容保留）"""
        with self._lock:
            self._bidding_scores.update(scores)

    def inject_ext_data(self, df: pd.DataFrame):
        """注入 55188 综合数据"""
        with self._lock:
            self._ext_df = df

    # ── v2 核心注入：直接从 detector 灌入板块图 ──────────────────────────────

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
                sname = sec.get('sector', '')
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

                # 计算龙头 VWAP（用 klines 均价）
                leader_vwap = 0.0
                if leader_klines:
                    vol_sum = sum(float(k.get('volume', 0)) for k in leader_klines)
                    amt_sum = sum(
                        float(k.get('volume', 0)) * float(k.get('close', 0))
                        for k in leader_klines
                    )
                    if vol_sum > 0:
                        leader_vwap = amt_sum / vol_sum

                # heat_score：直接用 board_score 归一化到 0~100
                # 后续可与其他板块相对标准化；现在先直接 *10（board_score 通常 5~30）
                heat_score = min(100.0, board_score * 3.5)

                # 跟随股代码列表
                followers = sec.get('followers', [])
                follower_codes = [str(f.get('code', '')) for f in followers if f.get('code')][:MAX_FOLLOWERS_PER_SECTOR]
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

        # 按板块聚合
        g = df.groupby('category', sort=False)
        sectors_raw = g.agg(
            _bid_mean=('_bid_score', 'mean'),
            _zt_sum=('_is_zt', 'sum'),
            _vol_mean=('_vol_ratio', 'mean'),
            _zhuli_mean=('_zhuli', 'mean'),
            _count=('code', 'count'),
        ).reset_index()
        sectors_raw.rename(columns={'category': 'name'}, inplace=True)

        sectors_raw = sectors_raw[sectors_raw['_count'] >= 3]
        if sectors_raw.empty:
            return []

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
            sectors_raw['_n_bid'] * self.W_BIDDING +
            sectors_raw['_n_zt']  * self.W_ZT +
            sectors_raw['_n_zhl'] * self.W_ZHULI +
            sectors_raw['_n_vol'] * self.W_VOL
        ) * 100

        result: List[SectorHeat] = []
        for _, row in sectors_raw.sort_values('heat_score', ascending=False).head(20).iterrows():
            sname = row['name']
            sec_df = df[df['category'] == sname].copy()
            if sec_df.empty:
                continue
            leader_code, leader_name, leader_pct, followers = self._identify_leader(sec_df, bidding, det_snap)
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
                follower_codes=followers,
                updated_at=datetime.now(),
            )
            result.append(heat)

        with self._lock:
            for h in result:
                if h.name not in self._sector_map:
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
    ) -> Tuple[str, str, float, List[str]]:
        sec_df = sec_df.copy()
        # 优先用 detector score，否则用 bidding_scores
        sec_df['_bid'] = sec_df['code'].map(
            {c: s.get('score', 0.0) for c, s in det_snap.items()}
        ).fillna(sec_df['code'].map(bidding).fillna(0.0))
        sec_df['_zt'] = sec_df['percent'] >= 9.5
        sec_df['_leader_score'] = (
            sec_df['_zt'].astype(float) * 50 +
            sec_df['_bid'] * 5 +
            sec_df['percent'].clip(0, 10) * 1
        )
        sorted_df = sec_df.sort_values('_leader_score', ascending=False).reset_index(drop=True)
        if sorted_df.empty:
            return '', '', 0.0, []
        leader = sorted_df.iloc[0]
        leader_code = str(leader.get('code', ''))
        leader_name = str(leader.get('name', ''))
        leader_pct  = float(leader.get('percent', 0.0))
        followers_df = sorted_df.iloc[1:MAX_FOLLOWERS_PER_SECTOR + 1]
        follower_codes = [str(r['code']) for _, r in followers_df.iterrows() if r['_bid'] > 0]
        return leader_code, leader_name, leader_pct, follower_codes

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


# ─────────────────────────────────────────────────────────────────────────────
# §3  龙头跟进识别（StarFollowEngine）
# ─────────────────────────────────────────────────────────────────────────────

class StarFollowEngine:
    """
    龙头确认 + 同板块跟进股生成
    ─────────────────────────────
    v2：确认条件增加对 detector board_score 的直接引用
    """

    LEADER_MIN_ZT_OR_PCT  = 5.0    # 龙头涨幅≥5%（降低门槛捕捉更多机会）
    LEADER_MIN_BID_SCORE  = 3.0    # 竞价/detector score≥3.0
    LEADER_HOT_RANK_MAX   = 200    # 55188 人气排名≤200

    def __init__(self, sector_map: SectorFocusMap):
        self._sector_map = sector_map
        self._confirmed_leaders: Dict[str, datetime] = {}
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
            code = sh.leader_code
            if not code:
                continue
            pct    = sh.leader_change_pct
            # v2: 优先用 heat_score 来判断板块强度（已含 board_score）
            bid    = sh.bidding_score  # 直接用板块 board_score
            h_rank = (hot_rank_map or {}).get(code, 9999)

            ok_pct = pct >= self.LEADER_MIN_ZT_OR_PCT
            ok_bid = bid >= self.LEADER_MIN_BID_SCORE
            ok_hot = h_rank <= self.LEADER_HOT_RANK_MAX

            if ok_pct and (ok_bid or ok_hot):
                with self._lock:
                    if code not in self._confirmed_leaders:
                        self._confirmed_leaders[code] = datetime.now()
                        new_leaders.append(code)
                        logger.info(
                            f"[StarFollow] 龙头确认: {code}({sh.leader_name}) "
                            f"板块={sh.name} 涨幅={pct:.1f}% 板块强度={bid:.1f} "
                            f"人气={h_rank} 类型={sh.sector_type}"
                        )
        return new_leaders

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

    def reset_day(self):
        with self._lock:
            self._confirmed_leaders.clear()


# ─────────────────────────────────────────────────────────────────────────────
# §4  盘中回踩买点检测（IntradayPullbackDetector）
# ─────────────────────────────────────────────────────────────────────────────

class IntradayPullbackDetector:
    """
    四种回踩买点形态检测（v2 使用真实 kline 序列）
    """

    MIN_DROP_FROM_HIGH   = -0.015
    MAX_DROP_FROM_VWAP   = -0.005
    MAX_VOL_RATIO_DURING = 0.85
    MIN_SECTOR_HEAT      = 25.0    # 从 40 降到 25，更早捕捉

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
    ) -> Optional[DecisionSignal]:
        try:
            return self._check(
                code, name, current_price, day_high, vwap,
                vol_ratio, prev_close, last_5min_prices, sector_name,
                pct_diff, dff,
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
    ) -> Optional[DecisionSignal]:
        with self._lock:
            last = self._triggered.get(code)
        if last and (datetime.now() - last).seconds < self._cooldown_sec:
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
            return None

        drop_from_high = (price - day_high) / day_high if day_high > 0 else 0.0
        diff_from_vwap = (price - vwap) / vwap if vwap > 0 else 0.0

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

        # 形态2：VWAP支撑 — 当前价在VWAP附近±0.3%，量放大，龙头已确认
        elif (abs(diff_from_vwap) <= 0.003 and
              vol_ratio >= 1.0 and
              self._star_engine.is_leader_confirmed(leader_code)):
            signal_type = SignalType.VWAP_SUPPORT
            reason = (f"均线支撑: 均价差{diff_from_vwap*100:.2f}% "
                      f"龙头{leader_code}已确认 dff={dff:+.2f}")
            priority = int(55 + sector_heat * 0.25 + max(0, dff) * 1.5)

        # 形态3：板块共振点 — 龙头确认，附近上翘，且周期内有涨幅
        elif (self._star_engine.is_leader_confirmed(leader_code) and
              len(prices5) >= 3 and
              prices5[-1] > prices5[-3] and
              diff_from_vwap >= -0.008 and
              pct_diff >= 0.1):   # v2: 要求周期内有正向变动
            signal_type = SignalType.SECTOR_BREAKOUT
            reason = (f"板块共振: 龙头{leader_code}已确认 "
                      f"跟进股上翘 均价差{diff_from_vwap*100:.2f}% "
                      f"周期涨幅{pct_diff:+.2f}%")
            priority = int(70 + sector_heat * 0.3 + pct_diff * 2)

        # 形态4：强势蓄势突破 — 板块类型为蓄势/强攻，且 dff 为正
        elif ('蓄势' in sector_type or '强攻' in sector_type):
            if pct_diff >= 0.3 and dff > 0 and diff_from_vwap >= -0.01:
                signal_type = SignalType.HOT_FOLLOW
                reason = (f"强势跟进({sector_type}): "
                          f"周期涨幅{pct_diff:+.2f}% dff={dff:+.2f} "
                          f"均价差{diff_from_vwap*100:.2f}%")
                priority = int(65 + sector_heat * 0.25 + pct_diff * 3 + dff)

        if signal_type is None:
            return None

        with self._lock:
            self._triggered[code] = datetime.now()

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
            if existing is None or signal.priority >= existing.priority:
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
        if status_filter:
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

        self._lock = threading.Lock()
        self._bidding_scores: Dict[str, float] = {}
        self._hot_rank_map: Dict[str, int] = {}
        self._df_realtime: Optional[pd.DataFrame] = None

        self._last_full_update: float = 0.0
        self._full_update_interval = 30.0   # 全量计算30秒一次

    # ── 数据注入（可从多个线程调用）────────────────────────────────────────

    def inject_realtime(self, df: pd.DataFrame):
        """注入实时行情 DataFrame"""
        with self._lock:
            self._df_realtime = df

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

    # ── 主循环 Tick（在后台线程中周期性调用）────────────────────────────────

    def tick(self):
        """
        单次行情 Tick 处理
        - 节流30秒做全量板块热力计算（降级通道）
        - 实时扫描回踩买点并推入决策队列
        """
        now = time.time()
        df = None
        with self._lock:
            df = self._df_realtime
            bidding = dict(self._bidding_scores)
            hot_rank = dict(self._hot_rank_map)

        # 全量板块热力（30秒节流，仅在 sector_map 中没有 detector 数据时启用降级通道）
        if now - self._last_full_update >= self._full_update_interval:
            try:
                if df is not None and not df.empty:
                    with self.sector_map._lock:
                        has_detector_data = bool(self.sector_map._sector_map)
                    if not has_detector_data:
                        # 降级：从 df_realtime 聚合
                        self.sector_map.update(df)
                    self.star_engine.confirm_leaders(df, bidding, hot_rank)
                self._last_full_update = now
            except Exception as e:
                logger.warning(f"[Controller] full update failed: {e}")

        # 实时扫描回踩买点
        if df is not None and not df.empty:
            self._scan_pullbacks(df)

    def _scan_pullbacks(self, df: pd.DataFrame):
        """扫描所有板块跟进股的回踩买点（v2：使用 kline 计算真实 prices5）"""
        hot_sectors = self.sector_map.get_hot_sectors(top_n=8)

        for sh in hot_sectors:
            # 龙头自身 + 跟进股
            target_codes = [sh.leader_code] + list(sh.follower_codes[:MAX_FOLLOWERS_PER_SECTOR])

            for code in target_codes:
                if not code:
                    continue
                try:
                    self._scan_one_v2(code, sh)
                except Exception as e:
                    logger.debug(f"[scan_pullbacks] {code}: {e}")

    def _scan_one_v2(self, code: str, sh: SectorHeat):
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
            name       = str(snap.get('name', code))
            pct_diff   = float(snap.get('pct_diff', 0.0))
            dff        = float(snap.get('dff', 0.0))
            klines     = snap.get('klines', [])

            # 计算 VWAP（来自真实 kline）
            vol_sum = sum(float(k.get('volume', 0)) for k in klines)
            amt_sum = sum(float(k.get('volume', 0)) * float(k.get('close', 0)) for k in klines)
            vwap = amt_sum / vol_sum if vol_sum > 0 else price

            # 量比（用最近 kline 均量）
            if len(klines) >= 3:
                recent_vol = float(klines[-1].get('volume', 0))
                avg_vol = sum(float(k.get('volume', 0)) for k in klines[-5:]) / min(5, len(klines))
                vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
            else:
                vol_ratio = 1.0

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
            name       = str(row.get('name', code))
            pct_diff   = 0.0
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
        )

        if signal:
            self.decision_queue.push(signal)
            logger.info(
                f"[Decision] 买点信号 {code}({name}) "
                f"优先级={signal.priority} 类型={signal.signal_type.name} "
                f"pct_diff={pct_diff:+.2f}% dff={dff:+.2f} "
                f"原因: {signal.reason}"
            )

    # ── 对外查询接口 ─────────────────────────────────────────────────────────

    def get_hot_sectors(self, top_n: int = 10) -> List[dict]:
        return [s.to_dict() for s in self.sector_map.get_hot_sectors(top_n)]

    def get_decision_queue(self) -> List[dict]:
        return [s.to_dict() for s in self.decision_queue.get_sorted()]

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
        logger.info("[Controller] 每日重置完成")


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
