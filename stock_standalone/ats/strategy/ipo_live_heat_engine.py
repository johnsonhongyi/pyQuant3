"""Intraday IPO heat scoring and turnover-rate production primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import math
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo


_EXCHANGE_TZ = ZoneInfo("Asia/Shanghai")


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class IPOLiveHeatSnapshot:
    code: str
    heat_score: float = 0.0
    overheat_score: float = 0.0
    exhaustion_risk: float = 0.0
    nonlinear_zone: str = "UNKNOWN"
    intraday_velocity: float = 0.0
    halt_count: int = 0
    turnover_pct: Optional[float] = None
    turnover_climb_speed: Optional[float] = None
    price_vwap_dist_pct: float = 0.0
    close_location: float = 0.0
    minutes_above_vwap_ratio: Optional[float] = None
    pullback_from_peak_pct: Optional[float] = None
    is_overheated_veto: bool = False
    data_ready: bool = False
    veto_reason: Optional[str] = None


class IPOLiveHeatEngine:
    @staticmethod
    def calc_return_nonlinear(ret_pct: float) -> Tuple[float, float]:
        if not _finite(ret_pct):
            raise ValueError("ret_pct 必须为有限数值")
        if ret_pct <= 0:
            return 0.0, 0.0
        if ret_pct <= 20.0:
            return ret_pct / 20.0 * 15.0, 0.0
        if ret_pct <= 50.0:
            return 15.0 + (ret_pct - 20.0) / 30.0 * 3.0, 0.0
        if ret_pct <= 80.0:
            penalty = (ret_pct - 50.0) / 30.0 * 15.0
            return max(0.0, 18.0 - penalty), penalty
        return -15.0, min(30.0, 15.0 + (ret_pct - 80.0) * 0.2)

    @staticmethod
    def calc_turnover_nonlinear(turnover_pct: float) -> Tuple[float, float]:
        if not _finite(turnover_pct) or turnover_pct < 0:
            raise ValueError("turnover_pct 必须为非负有限数值")
        if turnover_pct <= 35.0:
            return turnover_pct / 35.0 * 15.0, 0.0
        if turnover_pct <= 65.0:
            return 15.0, 0.0
        if turnover_pct <= 75.0:
            ratio = (turnover_pct - 65.0) / 10.0
            return 15.0 - ratio * 10.0, ratio * 15.0
        return -20.0, min(35.0, 15.0 + (turnover_pct - 75.0) * 1.5)

    @staticmethod
    def calc_vwap_distance_nonlinear(dist_pct: float) -> Tuple[float, float]:
        if not _finite(dist_pct):
            raise ValueError("dist_pct 必须为有限数值")
        if -0.5 <= dist_pct <= 2.5:
            return 15.0, 0.0
        if 2.5 < dist_pct <= 6.0:
            return 10.0, 0.0
        if 6.0 < dist_pct <= 10.0:
            return 5.0, 10.0
        if dist_pct > 10.0:
            return -15.0, 25.0
        return -10.0, 0.0

    @staticmethod
    def calc_opening_premium_nonlinear(open_premium_pct: float) -> Tuple[float, float]:
        if not _finite(open_premium_pct):
            raise ValueError("open_premium_pct 必须为有限数值")
        if open_premium_pct <= 15.0:
            return 10.0, 0.0
        if open_premium_pct <= 35.0:
            return 12.0, 0.0
        if open_premium_pct <= 60.0:
            return 5.0, 12.0
        return -15.0, 25.0

    @staticmethod
    def calc_intraday_velocity_nonlinear(slope_deg: float, now_hm: str) -> float:
        if not _finite(slope_deg) or not isinstance(now_hm, str):
            raise ValueError("斜率或盘中时刻无效")
        try:
            parsed_time = time(int(now_hm[:2]), int(now_hm[2:]))
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("now_hm 必须为 HHMM") from exc
        if len(now_hm) != 4 or parsed_time.strftime("%H%M") != now_hm:
            raise ValueError("now_hm 必须为 HHMM")
        weight = 1.0 if now_hm <= "0945" else (0.75 if now_hm <= "1000" else 0.40)
        return max(0.0, min(15.0, slope_deg / 60.0 * 15.0 * weight))

    @staticmethod
    def calc_close_location_nonlinear(
        high_p: float, low_p: float, curr_p: float
    ) -> Tuple[float, float]:
        if (
            any(not _finite(value) for value in (high_p, low_p, curr_p))
            or low_p <= 0 or high_p < low_p or curr_p < low_p or curr_p > high_p
        ):
            raise ValueError("高低/现价必须为有限且一致的价格")
        span = max(high_p - low_p, 0.001)
        close_location = (curr_p - low_p) / span
        if close_location >= 0.85:
            return 15.0, 0.0
        if close_location >= 0.60:
            return 5.0, 5.0
        if close_location >= 0.45:
            return -5.0, 15.0
        return -20.0, 35.0

    def evaluate(
        self,
        code: str,
        ret_pct: float,
        turnover_pct: float,
        price_vwap_dist_pct: float,
        open_premium_pct: float,
        slope_deg: float,
        high_p: float,
        low_p: float,
        curr_p: float,
        turnover_climb_speed: Optional[float] = None,
        minutes_above_vwap_ratio: Optional[float] = None,
        pullback_from_peak_pct: Optional[float] = None,
        halt_count: int = 0,
        now_hm: str = "1000",
    ) -> IPOLiveHeatSnapshot:
        def unready(reason: str) -> IPOLiveHeatSnapshot:
            return IPOLiveHeatSnapshot(
                code=code if isinstance(code, str) else "",
                veto_reason=reason,
            )

        if not isinstance(code, str) or not code.strip():
            return unready("code_missing")
        if (
            isinstance(halt_count, bool) or not isinstance(halt_count, int) or halt_count < 0
        ):
            return unready("halt_count_invalid")
        if (
            turnover_climb_speed is not None
            and (not _finite(turnover_climb_speed) or turnover_climb_speed < 0)
        ):
            return unready("turnover_climb_speed_invalid")
        if (
            minutes_above_vwap_ratio is not None
            and (not _finite(minutes_above_vwap_ratio) or not 0 <= minutes_above_vwap_ratio <= 1)
        ):
            return unready("minutes_above_vwap_ratio_invalid")
        if (
            pullback_from_peak_pct is not None
            and (not _finite(pullback_from_peak_pct) or pullback_from_peak_pct < 0)
        ):
            return unready("pullback_from_peak_pct_invalid")
        try:
            s_ret, p_ret = self.calc_return_nonlinear(ret_pct)
            s_to, p_to = self.calc_turnover_nonlinear(turnover_pct)
            s_vwap, p_vwap = self.calc_vwap_distance_nonlinear(price_vwap_dist_pct)
            s_prem, p_prem = self.calc_opening_premium_nonlinear(open_premium_pct)
            s_vel = self.calc_intraday_velocity_nonlinear(slope_deg, now_hm)
            s_close, p_close = self.calc_close_location_nonlinear(high_p, low_p, curr_p)
        except (TypeError, ValueError, OverflowError):
            return unready("required_live_heat_input_invalid")

        raw_heat = max(0.0, min(100.0, 20.0 + s_ret + s_to + s_vwap + s_prem + s_vel + s_close))
        total_overheat = min(50.0, p_ret + p_to + p_vwap + p_prem)
        exhaustion_risk = min(100.0, p_close + (15.0 if halt_count >= 2 else 0.0) + p_to * 0.8)
        if total_overheat >= 35.0 or exhaustion_risk >= 45.0 or p_close >= 30.0:
            zone, veto = "EXTREME", True
        elif total_overheat >= 15.0 or raw_heat >= 75.0:
            zone, veto = "HOT", False
        else:
            zone, veto = "NORMAL", False

        close_location = (curr_p - low_p) / max(high_p - low_p, 0.001)
        return IPOLiveHeatSnapshot(
            code=code,
            heat_score=round(raw_heat, 1),
            overheat_score=round(total_overheat, 1),
            exhaustion_risk=round(exhaustion_risk, 1),
            nonlinear_zone=zone,
            intraday_velocity=round(slope_deg, 1),
            halt_count=halt_count,
            turnover_pct=round(turnover_pct, 2),
            turnover_climb_speed=turnover_climb_speed,
            price_vwap_dist_pct=round(price_vwap_dist_pct, 2),
            close_location=round(close_location, 3),
            minutes_above_vwap_ratio=(
                round(minutes_above_vwap_ratio, 2)
                if minutes_above_vwap_ratio is not None else None
            ),
            pullback_from_peak_pct=(
                round(pullback_from_peak_pct, 2)
                if pullback_from_peak_pct is not None else None
            ),
            is_overheated_veto=veto,
            data_ready=True,
        )


@dataclass(frozen=True)
class _TurnoverPoint:
    observed_at: datetime
    cumulative_pct: float


class TurnoverClimbTracker:
    """Calculate cumulative turnover percentage points per active trading minute."""

    def __init__(self, lunch_start: time, lunch_end: time, max_sample_gap_minutes: float) -> None:
        if (
            not isinstance(lunch_start, time) or not isinstance(lunch_end, time)
            or lunch_start.tzinfo is not None or lunch_end.tzinfo is not None
            or lunch_start >= lunch_end or not _finite(max_sample_gap_minutes)
            or max_sample_gap_minutes <= 0
        ):
            raise ValueError("换手差分交易时段/最大采样间隔配置无效")
        self.lunch_start = lunch_start
        self.lunch_end = lunch_end
        self.max_sample_gap_minutes = float(max_sample_gap_minutes)
        self._last: Dict[Tuple[str, str], _TurnoverPoint] = {}

    def update(
        self,
        code: str,
        trading_date: str,
        cumulative_pct: float,
        observed_at: datetime,
    ) -> Optional[float]:
        if not isinstance(code, str) or not code.strip() or not isinstance(trading_date, str):
            return None
        try:
            expected_date = date.fromisoformat(trading_date)
        except (TypeError, ValueError):
            return None
        key = (code, trading_date)
        if (
            not _finite(cumulative_pct) or cumulative_pct < 0
            or not isinstance(observed_at, datetime) or observed_at.tzinfo is None
        ):
            self._last.pop(key, None)
            return None
        try:
            if observed_at.utcoffset() is None:
                self._last.pop(key, None)
                return None
            observed_local = observed_at.astimezone(_EXCHANGE_TZ)
        except (OverflowError, OSError, TypeError, ValueError):
            self._last.pop(key, None)
            return None
        if observed_local.date() != expected_date:
            self._last.pop(key, None)
            return None
        previous = self._last.get(key)
        if previous is None:
            self._last[key] = _TurnoverPoint(observed_local, float(cumulative_pct))
            return None
        previous_local = previous.observed_at.astimezone(_EXCHANGE_TZ)
        if observed_local <= previous_local:
            self._last[key] = _TurnoverPoint(observed_local, float(cumulative_pct))
            return None

        elapsed = (observed_local - previous_local).total_seconds() / 60.0
        lunch_start = datetime.combine(previous_local.date(), self.lunch_start, tzinfo=_EXCHANGE_TZ)
        lunch_end = datetime.combine(previous_local.date(), self.lunch_end, tzinfo=_EXCHANGE_TZ)
        overlap_start = max(previous_local, lunch_start)
        overlap_end = min(observed_local, lunch_end)
        lunch_minutes = max(0.0, (overlap_end - overlap_start).total_seconds() / 60.0)
        active_minutes = elapsed - lunch_minutes
        delta = float(cumulative_pct) - previous.cumulative_pct
        self._last[key] = _TurnoverPoint(observed_local, float(cumulative_pct))
        if delta < 0 or active_minutes <= 0 or active_minutes > self.max_sample_gap_minutes:
            return None
        return delta / active_minutes
