# market_sentiment_fsm.py
# -*- coding: utf-8 -*-
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Any, List, Tuple, Dict, Optional
import math
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import market_pulse_db
from market_pulse_db import (
    DAILY_SENTIMENT_SOURCE_ID,
    DAILY_SENTIMENT_SOURCE_TIMEZONE,
    DAILY_SENTIMENT_SOURCE_VERSION,
)
from JohnsonUtil import LoggerFactory
from JohnsonUtil import commonTips as cct

logger = LoggerFactory.getLogger("MarketSentimentFSM")
LIMIT_CHANGE_THRESHOLD = 9.8


def normalize_sector_name(name: Any) -> str:
    """Normalize whitespace/case while keeping sector matching exact."""
    return "".join(str(name or "").split()).casefold()

class SentimentState(Enum):
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"
    REPAIR = "REPAIR"
    REVERSAL = "REVERSAL"
    FOMO = "FOMO"
    COOLDOWN = "COOLDOWN"

@dataclass(frozen=True)
class SectorRecord:
    name: str
    avg_pct: float
    leader_code: str = ""
    leader_name: str = ""
    leader_pct: float = 0.0
    board_score: float = 0.0

@dataclass(frozen=True)
class MarketSnapshot:
    date: str
    index_pct: float
    up_count: int
    down_count: int
    limit_up: int
    limit_down: int
    temperature: float
    breadth_ratio: float
    top_sectors: tuple[SectorRecord, ...]
    worst_sectors: tuple[SectorRecord, ...]
    source_version: str = DAILY_SENTIMENT_SOURCE_VERSION
    source_id: str = DAILY_SENTIMENT_SOURCE_ID
    source_timezone: str = DAILY_SENTIMENT_SOURCE_TIMEZONE
    as_of_time: str = ""

@dataclass(frozen=True)
class BiddingSnapshot:
    date: str
    generated_at: str
    up_count: int
    down_count: int
    limit_up: int
    limit_down: int
    active_sectors: tuple[SectorRecord, ...]
    stock_snap: Mapping[str, Mapping[str, Any]]


class MarketSentimentFSM:
    def __init__(self):
        self.database_ready = False
        try:
            self.database_ready = market_pulse_db.init_pulse_db() is True
            if not self.database_ready:
                logger.error("[FSM] Pulse database migration did not report success; FSM remains unavailable")
        except Exception as e:
            logger.error(f"[FSM] Failed to init pulse db: {e}")
        self.current_state: SentimentState = SentimentState.NEUTRAL
        self.yesterday_snapshot: Optional[MarketSnapshot] = None
        self._yesterday_worst_sectors: set[str] = set()
        self._yesterday_top_sectors: set[str] = set()
        self._sector_record_by_name: dict[str, SectorRecord] = {}
        self._last_explained_data: dict = {}

    def load_latest_snapshot(self, trade_date: Optional[str] = None) -> Optional[MarketSnapshot]:
        """
        加载最近交易日（或者是指定交易日之前最近的一天）的情感数据。
        日期格式：YYYY-MM-DD
        """
        def clear_snapshot(reason: str) -> None:
            self.yesterday_snapshot = None
            self._yesterday_worst_sectors.clear()
            self._yesterday_top_sectors.clear()
            self._sector_record_by_name.clear()
            logger.warning("[FSM] Prior snapshot unavailable: %s", reason)

        if not self.database_ready:
            clear_snapshot("PULSE_DATABASE_NOT_READY")
            logger.error("[FSM] Snapshot load blocked because pulse database is not ready")
            return None
        try:
            if trade_date:
                # 获取指定日期之前最近的一天
                raw = market_pulse_db.get_latest_sentiment_before(trade_date)
            else:
                # 获取今天之前最近的一天
                today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
                raw = market_pulse_db.get_latest_sentiment_before(today)
                
            if not raw:
                clear_snapshot("NO_PRIOR_DAILY_SNAPSHOT")
                return None

            snapshot_date = datetime.strptime(str(raw.get("date", "")), "%Y-%m-%d").date()
            reference_date = datetime.strptime(
                trade_date or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d"),
                "%Y-%m-%d",
            ).date()
            if snapshot_date >= reference_date:
                clear_snapshot("SNAPSHOT_NOT_PRIOR_TO_REFERENCE_DATE")
                return None
            if raw.get("source_id") and raw["source_id"] != DAILY_SENTIMENT_SOURCE_ID:
                clear_snapshot("SNAPSHOT_SOURCE_ID_MISMATCH")
                return None
            if raw.get("source_timezone"):
                ZoneInfo(raw["source_timezone"])
            try:
                trade_days = cct.get_trade_days(
                    snapshot_date.strftime("%Y-%m-%d"), reference_date.strftime("%Y-%m-%d")
                )
                age_sessions = sum(
                    snapshot_date.strftime("%Y-%m-%d") < str(day)[:10]
                    <= reference_date.strftime("%Y-%m-%d")
                    for day in (trade_days or [])
                )
            except Exception:
                age_sessions = 0
            if age_sessions == 0:
                age_days = (reference_date - snapshot_date).days
                if age_days > 4:
                    clear_snapshot("SNAPSHOT_EXPIRED_CALENDAR_UNAVAILABLE")
                    return None
            elif age_sessions > 2:
                clear_snapshot(f"SNAPSHOT_EXPIRED_{age_sessions}_SESSIONS")
                return None
                
            # 解析最强/最弱板块
            worst_list = []
            for r in raw.get('worst_sectors', []):
                worst_list.append(SectorRecord(
                    name=r.get('name', ''),
                    avg_pct=r.get('avg_pct', 0.0),
                    leader_code=r.get('leader_code', ''),
                    leader_name=r.get('leader_name', ''),
                    leader_pct=r.get('leader_pct', 0.0),
                    board_score=r.get('board_score', 0.0)
                ))
            
            top_list = []
            for r in raw.get('top_sectors', []):
                top_list.append(SectorRecord(
                    name=r.get('name', ''),
                    avg_pct=r.get('avg_pct', 0.0),
                    leader_code=r.get('leader_code', ''),
                    leader_name=r.get('leader_name', ''),
                    leader_pct=r.get('leader_pct', 0.0),
                    board_score=r.get('board_score', 0.0)
                ))
                
            snap = MarketSnapshot(
                date=raw.get('date', ''),
                index_pct=raw.get('index_pct', 0.0),
                up_count=raw.get('up_count', 0),
                down_count=raw.get('down_count', 0),
                limit_up=raw.get('limit_up', 0),
                limit_down=raw.get('limit_down', 0),
                temperature=raw.get('temperature', 0.0),
                breadth_ratio=raw.get('breadth_ratio', 0.0),
                top_sectors=tuple(top_list),
                worst_sectors=tuple(worst_list),
                source_version=raw.get('source_version', 'daily_sentiment.v1'),
                source_id=raw.get("source_id", DAILY_SENTIMENT_SOURCE_ID),
                source_timezone=raw.get("source_timezone", DAILY_SENTIMENT_SOURCE_TIMEZONE),
                as_of_time=raw.get("as_of_time", ""),
            )
            
            self.yesterday_snapshot = snap
            self._yesterday_worst_sectors = {s.name for s in snap.worst_sectors if s.name}
            self._yesterday_top_sectors = {s.name for s in snap.top_sectors if s.name}
            self._sector_record_by_name = {s.name: s for s in snap.worst_sectors}
            self._sector_record_by_name.update({s.name: s for s in snap.top_sectors})
            
            logger.info(f"[FSM] Loaded reference daily sentiment for {snap.date}. State transitions primed.")
            return snap
        except Exception as e:
            clear_snapshot(type(e).__name__)
            logger.error(f"[FSM Load Error] {e}")
        return None

    def build_bidding_snapshot(self, detector) -> BiddingSnapshot:
        """
        从 BiddingMomentumDetector 内部结构组装竞价瞬时快照。
        为防阻塞，在 detector 锁内仅执行极速浅拷贝。
        """
        import time
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        date_str = now.strftime("%Y-%m-%d")
        if not self.database_ready:
            return BiddingSnapshot(
                date=date_str,
                generated_at=now.strftime("%H:%M:%S"),
                up_count=0,
                down_count=0,
                limit_up=0,
                limit_down=0,
                active_sectors=(),
                stock_snap={},
            )
        
        # 1. 抓取板块数据
        active_sectors_list = detector.get_active_sectors()  # 内部已安全使用锁
        
        # 2. 抓取个股缓存 (浅拷贝)
        with detector._lock:
            stock_snap = dict(detector._global_snap_cache)
            # 获取大盘上涨/下跌家数（如果 detector 有这个字段，或者通过 cct 拿）
            # 兼容处理：如果没有，退避为 0
            limit_up = 0
            limit_down = 0
            up_count = 0
            down_count = 0
            for code, s in stock_snap.items():
                pct = s.get('pct', 0.0)
                if pct >= LIMIT_CHANGE_THRESHOLD:
                    limit_up += 1
                elif pct <= -LIMIT_CHANGE_THRESHOLD:
                    limit_down += 1
                if pct > 0:
                    up_count += 1
                elif pct < 0:
                    down_count += 1
                    
        # 构建 SectorRecord 元组
        sectors = []
        for s in active_sectors_list:
            sectors.append(SectorRecord(
                name=s.get('sector', ''),
                avg_pct=s.get('avg_pct', 0.0),
                leader_code=s.get('leader', ''),
                leader_name=s.get('leader_name', ''),
                leader_pct=s.get('leader_pct', 0.0),
                board_score=s.get('score', 0.0)
            ))
            
        return BiddingSnapshot(
            date=date_str,
            generated_at=now.strftime("%H:%M:%S"),
            up_count=up_count,
            down_count=down_count,
            limit_up=limit_up,
            limit_down=limit_down,
            active_sectors=tuple(sectors),
            stock_snap=stock_snap
        )

    def classify(self, bidding: BiddingSnapshot) -> SentimentState:
        """
        执行情绪状态判定
        """
        matched_rules = []
        blocked_reasons = []
        repaired_worst_sectors = []

        if not self.database_ready:
            self.current_state = SentimentState.NEUTRAL
            self._last_explained_data = {
                "state": self.current_state.value,
                "confidence": 0.0,
                "matched_rules": [],
                "repaired_worst_sectors": [],
                "blocked_reasons": ["PULSE_DATABASE_NOT_READY"],
            }
            return self.current_state
        
        yesterday = self.yesterday_snapshot
        
        # 0. 基础过滤：如果没有昨天的情绪快照参考，默认中性
        if not yesterday:
            self.current_state = SentimentState.NEUTRAL
            self._last_explained_data = {
                "state": self.current_state.value,
                "confidence": 0.50,
                "matched_rules": ["NO_YESTERDAY_SNAPSHOT"],
                "repaired_worst_sectors": [],
                "blocked_reasons": ["Missing yesterday market memory"]
            }
            return self.current_state
            
        # 计算竞价上涨家数比
        total_active = bidding.up_count + bidding.down_count
        today_bidding_up_ratio = bidding.up_count / total_active if total_active > 0 else 0.5
        
        # 1. 确定昨日情绪基调：昨日是否属于恐慌 (PANIC)
        is_yesterday_panic = False
        if yesterday.index_pct <= -1.0:
            is_yesterday_panic = True
            matched_rules.append("YESTERDAY_INDEX_DROP_EXCEED_1PCT")
        if yesterday.breadth_ratio <= 0.35:
            is_yesterday_panic = True
            matched_rules.append("YESTERDAY_BREADTH_PANIC")
        # 2. 对比昨日跌幅最大的板块，看今日竞价是否有修复
        # 遍历昨日最弱板块，看今日 avg_pct >= -0.3
        bidding_sector_pcts = {
            normalize_sector_name(s.name): s.avg_pct
            for s in bidding.active_sectors if normalize_sector_name(s.name)
        }
        repaired_count = 0
        for name in self._yesterday_worst_sectors:
            normalized_name = normalize_sector_name(name)
            if normalized_name in bidding_sector_pcts:
                avg_pct = bidding_sector_pcts[normalized_name]
                if avg_pct >= -0.3:
                    repaired_count += 1
                    repaired_worst_sectors.append(name)
        has_worst_sector_match = any(
            normalize_sector_name(name) in bidding_sector_pcts
            for name in self._yesterday_worst_sectors
        )
        if self._yesterday_worst_sectors and not has_worst_sector_match:
            blocked_reasons.append("NO_YESTERDAY_WORST_SECTOR_NAME_MATCH")
                    
        # 3. 检查是否有龙头或者昨日超跌板块的个股高开抢筹 (在竞价前 30 名或前 20%)
        # 提取竞价前 30 只高分股
        top_bidding_stocks = sorted(bidding.stock_snap.values(), key=lambda x: x.get('score', 0.0), reverse=True)[:30]
        top_codes = {s.get('code') for s in top_bidding_stocks}
        
        has_reversal_leader = False
        for name in self._yesterday_worst_sectors:
            sec_rec = self._sector_record_by_name.get(name)
            if sec_rec and sec_rec.leader_code and sec_rec.leader_code in top_codes:
                has_reversal_leader = True
                matched_rules.append(f"REVERSAL_LEADER_CONFIRMED_{sec_rec.leader_name}")
                break
                
        # 4. 执行状态转移
        next_state = SentimentState.NEUTRAL
        confidence = 0.50
        
        # PANIC 状态
        if is_yesterday_panic:
            next_state = SentimentState.PANIC
            confidence = 0.70

            if 0.35 <= today_bidding_up_ratio < 0.45 and repaired_count < 2:
                next_state = SentimentState.COOLDOWN
                confidence = 0.65
                matched_rules.append("PANIC_TO_COOLDOWN_PARTIAL_REPAIR")
            
            # REPAIR: 跌透之后的初步竞价修复
            if today_bidding_up_ratio >= 0.45 and repaired_count >= 2:
                next_state = SentimentState.REPAIR
                confidence = 0.75
                matched_rules.append("PANIC_TO_REPAIR_UP_RATIO_OK")
                
            # REVERSAL: 翻转，具备强反弹开仓条件
            if today_bidding_up_ratio >= 0.45 and repaired_count >= 3 and has_reversal_leader:
                # 额外防线：今天竞价跌停板数没有扩散 (不超过昨天的 1.2 倍 + 3)
                if bidding.limit_down <= yesterday.limit_down * 1.2 + 3:
                    next_state = SentimentState.REVERSAL
                    confidence = 0.85
                    matched_rules.append("PANIC_TO_REVERSAL_CONFIRMED")
                else:
                    blocked_reasons.append(f"Limit down count expanded: {bidding.limit_down} vs {yesterday.limit_down}")
                    
        # FOMO 状态检测 (开盘情绪过热)
        # 如果大量个股高开超过 4% 且大盘明显高开，或者前天昨天连涨高潮
        high_open_candidates = [s for s in bidding.stock_snap.values() if s.get('pct', 0.0) >= 4.0]
        if (next_state == SentimentState.NEUTRAL
                and len(high_open_candidates) >= 15 and today_bidding_up_ratio >= 0.75):
            next_state = SentimentState.FOMO
            confidence = 0.90
            matched_rules.append("FOMO_HIGH_OPEN_CANDIDATES")
            
        self.current_state = next_state
        self._last_explained_data = {
            "state": next_state.value,
            "confidence": confidence,
            "matched_rules": matched_rules,
            "repaired_worst_sectors": repaired_worst_sectors,
            "blocked_reasons": blocked_reasons,
            "missing_worst_sectors": len(self._yesterday_worst_sectors) == 0,
            "unmatched_worst_sector_count": (
                len(self._yesterday_worst_sectors) if self._yesterday_worst_sectors
                and not has_worst_sector_match else 0
            ),
        }
        
        return next_state

    def explain_state(self) -> dict:
        return self._last_explained_data

    def save_daily_snapshot(self, detector, df_all, index_pct: float, date_str: Optional[str] = None) -> Optional[MarketSnapshot]:
        """
        收盘时生成当天的情感快照并持久化。
        """
        try:
            exchange_tz = ZoneInfo("Asia/Shanghai")
            today = date_str or datetime.now(exchange_tz).strftime("%Y-%m-%d")
            index_pct = float(index_pct)
            if not math.isfinite(index_pct):
                raise ValueError("index_pct must be finite")
            if df_all is None or getattr(df_all, "empty", True) or "percent" not in df_all.columns:
                raise ValueError("a non-empty market dataframe with percent is required")
            if detector is None or not callable(getattr(detector, "get_active_sectors", None)):
                raise ValueError("a ready sector detector is required")
            
            # 计算大盘上涨/下跌家数
            up_count = 0
            down_count = 0
            limit_up = 0
            limit_down = 0
            
            if df_all is not None and not df_all.empty:
                def finite_percent(value: Any) -> float:
                    try:
                        converted = float(value)
                    except (TypeError, ValueError, OverflowError):
                        return math.nan
                    return converted if math.isfinite(converted) else math.nan

                percent = df_all["percent"].map(
                    finite_percent
                )
                finite_mask = percent.map(math.isfinite)
                valid_df = df_all.loc[finite_mask].copy()
                valid_df["percent"] = percent.loc[finite_mask]
                if valid_df.empty:
                    raise ValueError("market dataframe has no finite percent values")
                up_count = int((valid_df['percent'] > 0).sum())
                down_count = int((valid_df['percent'] < 0).sum())
                flat_count = int((valid_df['percent'] == 0).sum())
                total = up_count + down_count + flat_count
                breadth_ratio = up_count / total if total > 0 else 0.5
                
                limit_up = int((valid_df['percent'] >= LIMIT_CHANGE_THRESHOLD).sum())
                limit_down = int((valid_df['percent'] <= -LIMIT_CHANGE_THRESHOLD).sum())
                
            # 市场温度：暂时用 breadth_ratio * 100 兜底
            # Legacy persisted presentation alias; classification uses breadth_ratio directly.
            temperature = breadth_ratio * 100
            
            # 抓取板块
            active_sectors_list = detector.get_active_sectors()
            if not isinstance(active_sectors_list, (list, tuple)) or not active_sectors_list:
                raise ValueError("sector detector produced no active-sector snapshot")
            
            # 构造 top 和 worst 板块
            top_sectors_raw = sorted(active_sectors_list, key=lambda x: x.get('score', 0.0), reverse=True)[:5]
            worst_sectors_raw = sorted(active_sectors_list, key=lambda x: x.get('avg_pct', 0.0))[:5]
            
            top_sectors = []
            for s in top_sectors_raw:
                top_sectors.append({
                    'name': s.get('sector', ''),
                    'avg_pct': s.get('avg_pct', 0.0),
                    'leader_code': s.get('leader', ''),
                    'leader_name': s.get('leader_name', ''),
                    'leader_pct': s.get('leader_pct', 0.0),
                    'board_score': s.get('score', 0.0)
                })
                
            worst_sectors = []
            for s in worst_sectors_raw:
                # 仅保留真实的下跌板块，防止强行判定
                if s.get('avg_pct', 0.0) < 0:
                    worst_sectors.append({
                        'name': s.get('sector', ''),
                        'avg_pct': s.get('avg_pct', 0.0),
                        'leader_code': s.get('leader', ''),
                        'leader_name': s.get('leader_name', ''),
                        'leader_pct': s.get('leader_pct', 0.0),
                        'board_score': s.get('score', 0.0)
                    })
            
            as_of_time = datetime.now(exchange_tz).isoformat()
            db_snap = {
                'index_pct': index_pct,
                'breadth_ratio': breadth_ratio,
                'up_count': up_count,
                'down_count': down_count,
                'limit_up': limit_up,
                'limit_down': limit_down,
                'temperature': temperature,
                'worst_sectors': worst_sectors,
                'top_sectors': top_sectors,
                'indices': [],
                'source_id': DAILY_SENTIMENT_SOURCE_ID,
                'source_version': DAILY_SENTIMENT_SOURCE_VERSION,
                'source_timezone': DAILY_SENTIMENT_SOURCE_TIMEZONE,
                'as_of_time': as_of_time,
            }
            
            if market_pulse_db.save_daily_sentiment(today, db_snap) is not True:
                raise RuntimeError("market_pulse_db rejected the daily sentiment snapshot")
            
            # 同时转换为对象返回
            worst_recs = [SectorRecord(**w) for w in worst_sectors]
            top_recs = [SectorRecord(**t) for t in top_sectors]
            
            snap = MarketSnapshot(
                date=today,
                index_pct=index_pct,
                up_count=up_count,
                down_count=down_count,
                limit_up=limit_up,
                limit_down=limit_down,
                temperature=temperature,
                breadth_ratio=breadth_ratio,
                top_sectors=tuple(top_recs),
                worst_sectors=tuple(worst_recs),
                source_version=DAILY_SENTIMENT_SOURCE_VERSION,
                source_id=DAILY_SENTIMENT_SOURCE_ID,
                source_timezone=DAILY_SENTIMENT_SOURCE_TIMEZONE,
                as_of_time=as_of_time,
            )
            logger.info(f"[FSM] Daily sentiment snapshot stored for {today}.")
            return snap
        except Exception as e:
            logger.error(f"[FSM Save Daily Snapshot Error] {e}")
            import traceback
            traceback.print_exc()
        return None
