# -*- coding: utf-8 -*-
"""
ats/strategy/subnew_executable_gate.py
-------------------------------------
S5 次新次级买点准入判定纯函数引擎 (S5 Executable Gate)

本模块作为 S4 交易计划向 S5 执行态跃迁的纯函数准入门禁：
1. 仅允许 strategy_tag="CHANNEL_SECONDARY_BUY" 且 signal_level="S4" 的计划；
2. 形态质量等级 quality_grade 仅允许 A/S/SS（剔除 B/C 级形态）；
3. 校验 Higher-Low 结构有效性（structural_stop > 0, structural_target > structural_stop, trigger/buy zone 合法）；
4. 现价必须严格落在 [buy_zone_min, buy_zone_max] 买入区间；超过上沿稳定拒绝 PRICE_ABOVE_BUY_ZONE；
5. 调用 Task 021 calculate_rr_now 动态计算盈亏比，必须 >= 2.5；
6. 调用 Task 022 evaluate_trade_plan_ttl 动态计算交易时间 TTL，>= 15 交易分钟稳定拒绝 TTL_TRADING_15M；
7. market_allowed=False 稳定拒绝 MARKET_BLOCKED；
8. 零业务状态修改，严格保持入参 plan 的不可变性。
"""

import math
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, Tuple, Union

from JohnsonUtil import LoggerFactory
from ats.strategy.channel_secondary_buy_strategy import (
    IPOTradePlan,
    TAG_CHANNEL_SECONDARY_BUY,
    calculate_rr_now,
)
from ats.strategy.subnew_trading_clock import (
    evaluate_trade_plan_ttl,
    TradePlanTTLResult,
    REASON_TTL_TRADING_15M,
    TTL_TRADING_15M,
    REASON_TTL_CROSS_DAY,
    TTL_CROSS_DAY,
)

logger = LoggerFactory.getLogger("SubnewExecutableGate")

# ==============================================================================
# 稳定拒绝代码常量定义 (Stable Reject Codes)
# ==============================================================================

REJECT_MARKET_BLOCKED = "MARKET_BLOCKED"
REJECT_PLAN_NONE = "PLAN_NONE"
REJECT_INVALID_STRATEGY = "INVALID_STRATEGY_TAG"
REJECT_INVALID_SIGNAL_LEVEL = "INVALID_SIGNAL_LEVEL"
REJECT_INVALID_QUALITY_GRADE = "INVALID_QUALITY_GRADE"
REJECT_STRUCTURAL_INVALID = "STRUCTURAL_INVALID"
REJECT_PRICE_INVALID = "PRICE_INVALID"
REJECT_PRICE_ABOVE_BUY_ZONE = "PRICE_ABOVE_BUY_ZONE"
REJECT_PRICE_BELOW_BUY_ZONE = "PRICE_BELOW_BUY_ZONE"
REJECT_RR_BELOW_THRESHOLD = "RR_BELOW_THRESHOLD"
REJECT_TTL_TRADING_15M = TTL_TRADING_15M
REJECT_TTL_CROSS_DAY = TTL_CROSS_DAY

ALLOWED_QUALITY_GRADES = ("A", "S", "SS")
MIN_RR_THRESHOLD = 2.5
DEFAULT_TTL_MINUTES = 15.0


@dataclass(frozen=True)
class S5ExecutableGateResult:
    """S5 准入执行判定不可变结果容器"""

    allowed: bool
    signal_level: Optional[str] = None
    reject_code: Optional[str] = None
    reject_reason: Optional[str] = None
    rr_now: Optional[float] = None
    elapsed_trading_minutes: Optional[float] = None
    plan_id: Optional[str] = None
    code: Optional[str] = None
    extra_info: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为标准字典"""
        return {
            "allowed": self.allowed,
            "signal_level": self.signal_level,
            "reject_code": self.reject_code,
            "reject_reason": self.reject_reason,
            "rr_now": self.rr_now,
            "elapsed_trading_minutes": self.elapsed_trading_minutes,
            "plan_id": self.plan_id,
            "code": self.code,
            "extra_info": dict(self.extra_info) if self.extra_info else {},
        }

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(f"S5ExecutableGateResult has no key: {item!r}")

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __bool__(self) -> bool:
        return self.allowed


def _extract_numeric(val: Any) -> Optional[float]:
    """安全提取数值，排除 bool、None、NaN、Inf"""
    if val is None or isinstance(val, bool):
        return None
    try:
        v = float(val)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


def _get_plan_field(plan: Any, key: str, default: Any = None) -> Any:
    """从 plan 对象或字典安全提取字段"""
    if plan is None:
        return default
    if isinstance(plan, dict):
        return plan.get(key, default)
    if hasattr(plan, key):
        return getattr(plan, key, default)
    if hasattr(plan, "get") and callable(getattr(plan, "get")):
        try:
            val = plan.get(key, default)
            if val is not None:
                return val
        except Exception:
            pass
    return default


def _get_structural_stop(plan: Any) -> Optional[float]:
    """提取结构止损位锚点"""
    val = _get_plan_field(plan, "structural_stop", None)
    if val is None or val == 0.0:
        val = _get_plan_field(plan, "higher_low_stop", None)
    return _extract_numeric(val)


def _get_structural_target(plan: Any) -> Optional[float]:
    """提取结构止盈目标锚点"""
    val = _get_plan_field(plan, "structural_target", None)
    if val is None or val == 0.0:
        val = _get_plan_field(plan, "target_1_channel_mid", None)
    return _extract_numeric(val)


def _extract_created_time_from_plan_id(plan_id: Any) -> Optional[str]:
    """若 plan 自身未记录 created_time，尝试从 plan_id (TP_CODE_YYYYMMDD_HHMMSS) 解析"""
    if not plan_id or not isinstance(plan_id, str):
        return None
    m = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", plan_id)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}:{m.group(6)}"
    return None


def _ensure_plan_for_rr(plan: Any) -> Any:
    """如果入参为字典，构建符合 calculate_rr_now 要求的只读兼容对象"""
    if isinstance(plan, dict):
        fields = getattr(IPOTradePlan, "__dataclass_fields__", {})
        valid_keys = set(fields.keys())
        kwargs = {}
        for k, v in plan.items():
            if k in valid_keys:
                kwargs[k] = v
        if "higher_low_stop" not in kwargs and "structural_stop" in plan:
            kwargs["higher_low_stop"] = plan["structural_stop"]
        if "target_1_channel_mid" not in kwargs and "structural_target" in plan:
            kwargs["target_1_channel_mid"] = plan["structural_target"]
        try:
            return IPOTradePlan(**kwargs)
        except Exception:
            return plan
    return plan


def _compute_rr_now(price: float, plan: Any) -> Optional[float]:
    """调用 Task 021 的 calculate_rr_now 计算当前价格下的盈亏比"""
    # 优先调用 plan 自带方法
    if hasattr(plan, "calculate_rr_now") and callable(getattr(plan, "calculate_rr_now")):
        try:
            rr = plan.calculate_rr_now(price)
            if rr is not None:
                return round(float(rr), 4)
        except Exception:
            pass
    # 其次调用外部纯函数
    try:
        adapted = _ensure_plan_for_rr(plan)
        rr = calculate_rr_now(price, adapted)
        if rr is not None:
            return round(float(rr), 4)
    except Exception:
        pass
    # 底层契约兜底计算: (target - price) / (price - stop)
    stop = _get_structural_stop(plan)
    target = _get_structural_target(plan)
    if stop is not None and target is not None and target > stop:
        if price > stop and target > price:
            return round((target - price) / (price - stop), 4)
    return None


def evaluate_s5_executable(
    plan: Any,
    price: Any,
    now: Any,
    market_allowed: bool = True,
) -> S5ExecutableGateResult:
    """
    S5 可执行准入门禁核心纯函数。

    参数：
        plan: S4 IPOTradePlan 或等价只读字典
        price: 实时撮合/现价
        now: 当前判定时间 (datetime, str, float)
        market_allowed: 全局市场/风控执行许可，默认为 True

    返回：
        S5ExecutableGateResult: 包含 allowed, signal_level, rr_now, elapsed_trading_minutes 等字段
    """
    plan_id = _get_plan_field(plan, "plan_id")
    code = _get_plan_field(plan, "code")

    # 1. 市场风控硬阻断判定 (零状态修改，直接拒绝)
    if not market_allowed:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_MARKET_BLOCKED,
            reject_reason="Market execution is blocked / market_allowed is False",
            plan_id=plan_id,
            code=code,
        )

    # 2. plan 存在性判定
    if plan is None:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_PLAN_NONE,
            reject_reason="Trade plan is None",
            plan_id=None,
            code=None,
        )

    # 3. 策略正交标签必须为 CHANNEL_SECONDARY_BUY
    strategy_tag = _get_plan_field(plan, "strategy_tag")
    if strategy_tag != TAG_CHANNEL_SECONDARY_BUY:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_INVALID_STRATEGY,
            reject_reason=f"Strategy tag '{strategy_tag}' is not '{TAG_CHANNEL_SECONDARY_BUY}'",
            plan_id=plan_id,
            code=code,
        )

    # 4. 生命周期层级必须为 S4
    signal_level = _get_plan_field(plan, "signal_level")
    signal_stage = _get_plan_field(plan, "signal_stage")
    effective_level = signal_level
    if signal_stage is not None and signal_stage != "S4":
        effective_level = signal_stage
    elif effective_level is None or effective_level == "":
        effective_level = signal_stage

    if effective_level != "S4":
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_INVALID_SIGNAL_LEVEL,
            reject_reason=f"Signal level '{effective_level}' is not 'S4'",
            plan_id=plan_id,
            code=code,
        )

    # 5. 形态质量等级仅允许 A/S/SS (拒绝 B/C)
    quality_grade = _get_plan_field(plan, "quality_grade")
    if quality_grade not in ALLOWED_QUALITY_GRADES:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_INVALID_QUALITY_GRADE,
            reject_reason=f"Quality grade '{quality_grade}' is not in allowed {ALLOWED_QUALITY_GRADES}",
            plan_id=plan_id,
            code=code,
        )

    # 6. Higher-Low 结构有效性校验
    structural_stop = _get_structural_stop(plan)
    structural_target = _get_structural_target(plan)
    trigger_price = _extract_numeric(_get_plan_field(plan, "trigger_price"))
    buy_zone_min = _extract_numeric(_get_plan_field(plan, "buy_zone_min"))
    buy_zone_max = _extract_numeric(_get_plan_field(plan, "buy_zone_max"))

    if structural_stop is None or structural_stop <= 0:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"structural_stop must be positive, got {structural_stop}",
            plan_id=plan_id,
            code=code,
        )

    if structural_target is None or structural_target <= structural_stop:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"structural_target ({structural_target}) must be > structural_stop ({structural_stop})",
            plan_id=plan_id,
            code=code,
        )

    if trigger_price is None or trigger_price <= 0:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"trigger_price must be positive, got {trigger_price}",
            plan_id=plan_id,
            code=code,
        )

    if buy_zone_min is None or buy_zone_min <= 0:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"buy_zone_min must be positive, got {buy_zone_min}",
            plan_id=plan_id,
            code=code,
        )

    if buy_zone_max is None or buy_zone_max < buy_zone_min:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"buy_zone_max ({buy_zone_max}) must be >= buy_zone_min ({buy_zone_min})",
            plan_id=plan_id,
            code=code,
        )

    if structural_stop >= buy_zone_min:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"structural_stop ({structural_stop}) must be strictly < buy_zone_min ({buy_zone_min})",
            plan_id=plan_id,
            code=code,
        )

    if structural_target <= buy_zone_max:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason=f"structural_target ({structural_target}) must be strictly > buy_zone_max ({buy_zone_max})",
            plan_id=plan_id,
            code=code,
        )

    # 7. 现价买入区间校验 (buy_zone_min ~ buy_zone_max)
    p = _extract_numeric(price)
    if p is None:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_PRICE_INVALID,
            reject_reason=f"Price is invalid: {price!r}",
            plan_id=plan_id,
            code=code,
        )

    if p > buy_zone_max:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_PRICE_ABOVE_BUY_ZONE,
            reject_reason=f"Price {p} is above buy_zone_max {buy_zone_max}",
            plan_id=plan_id,
            code=code,
        )

    if p < buy_zone_min:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_PRICE_BELOW_BUY_ZONE,
            reject_reason=f"Price {p} is below buy_zone_min {buy_zone_min}",
            plan_id=plan_id,
            code=code,
        )

    # 8. TTL 时间衰减校验 (Task 022 契约)
    created_time = _get_plan_field(plan, "created_time")
    if not created_time:
        created_time = _extract_created_time_from_plan_id(plan_id)

    if not created_time:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_STRUCTURAL_INVALID,
            reject_reason="Plan created_time is missing and cannot be inferred from plan_id",
            plan_id=plan_id,
            code=code,
        )

    ttl_res: TradePlanTTLResult = evaluate_trade_plan_ttl(
        created_time,
        now,
        ttl_minutes=DEFAULT_TTL_MINUTES,
    )
    elapsed_trading_mins = ttl_res.elapsed_trading_minutes

    if ttl_res.is_expired:
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=ttl_res.expired_reason or REJECT_TTL_TRADING_15M,
            reject_reason=f"TTL expired with reason: {ttl_res.expired_reason}",
            elapsed_trading_minutes=elapsed_trading_mins,
            plan_id=plan_id,
            code=code,
        )

    # 9. 动态盈亏比 RR 校验 (Task 021 契约: 必须 >= 2.5)
    rr_now = _compute_rr_now(p, plan)
    if rr_now is not None:
        rr_now = round(rr_now, 4)
    if rr_now is None or (rr_now < MIN_RR_THRESHOLD - 1e-5):
        return S5ExecutableGateResult(
            allowed=False,
            signal_level=None,
            reject_code=REJECT_RR_BELOW_THRESHOLD,
            reject_reason=f"Dynamic RR {rr_now} is below required threshold {MIN_RR_THRESHOLD}",
            rr_now=rr_now,
            elapsed_trading_minutes=elapsed_trading_mins,
            plan_id=plan_id,
            code=code,
        )

    # 10. 全绿通过：准入跃迁为 S5
    return S5ExecutableGateResult(
        allowed=True,
        signal_level="S5",
        reject_code=None,
        reject_reason=None,
        rr_now=rr_now,
        elapsed_trading_minutes=elapsed_trading_mins,
        plan_id=plan_id,
        code=code,
    )
