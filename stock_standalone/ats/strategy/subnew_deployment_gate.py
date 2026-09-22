"""
ats/strategy/subnew_deployment_gate.py
GO/NO-GO deployment gate core for subnew stock strategy.

Provides deterministic, clock-injectable GO/NO-GO gate evaluations for:
- Gate 1 (09:15): Preliminary sanity checks (build_identity, account_reconciliation,
  T+1/sellable initialization, pending directives boot empty).
- Gate 2 (09:25): Fixed 8-item ALL-GREEN check:
  1. build_identity
  2. market_data_fresh
  3. account_reconciliation
  4. sellable_qty_reconciliation
  5. pending_directives_empty_at_boot
  6. duplicate_plan_check
  7. EXIT_BUY_contract
  8. risk_execution_path

Key safety rules:
- ALL GREEN required for Gate 2 CONFIRM.
- Any single failure causes immediate downgrade to MONITOR_ONLY with clear reject codes.
- Once downgraded to MONITOR_ONLY on a trading day, the state is latched: it will NEVER
  automatically upgrade back to CONFIRM on the same trading day, even if all checks recover.
- Only an explicit reset_for_trading_day(new_date) or new day initialization can release the latch.
- Market data freshness evaluation supports <=3s freshness window without direct broker/market fetching.
- Pure logic: no direct broker access, credentials, or order execution.
- Fully serializable results for UI/logging.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class GateStatus(str, Enum):
    """Gate decision status."""
    CONFIRM = "CONFIRM"
    MONITOR_ONLY = "MONITOR_ONLY"


# Gate 1 minimum checks
GATE1_REQUIRED_CHECKS: Tuple[str, ...] = (
    "build_identity",
    "account_reconciliation",
    "sellable_init",
    "pending_directives_empty_at_boot",
)

# Gate 2 fixed 8 checks
GATE2_REQUIRED_CHECKS: Tuple[str, ...] = (
    "build_identity",
    "market_data_fresh",
    "account_reconciliation",
    "sellable_qty_reconciliation",
    "pending_directives_empty_at_boot",
    "duplicate_plan_check",
    "EXIT_BUY_contract",
    "risk_execution_path",
)

# Aliases mapping for user convenience and compatibility
GATE1_ALIASES: Dict[str, str] = {
    "sellable_qty_initialization": "sellable_init",
    "sellable_initialization": "sellable_init",
    "t1_sellable_init": "sellable_init",
    "t1_sellable_initialization": "sellable_init",
    "T+1/sellable 初始化": "sellable_init",
    "t+1/sellable 初始化": "sellable_init",
    "pending_directives 启动为空": "pending_directives_empty_at_boot",
    "pending_directives_boot_empty": "pending_directives_empty_at_boot",
}

GATE2_ALIASES: Dict[str, str] = {
    "exit_buy_contract": "EXIT_BUY_contract",
    "Exit_Buy_Contract": "EXIT_BUY_contract",
    "EXIT_BUY_CONTRACT": "EXIT_BUY_contract",
    "exit_buy": "EXIT_BUY_contract",
    "account_recon": "account_reconciliation",
    "sellable_recon": "sellable_qty_reconciliation",
}


def _to_timestamp_and_iso(
    val: Union[int, float, str, datetime]
) -> Tuple[float, str]:
    """Convert timestamp/datetime/ISO string to (float_seconds, iso_string)."""
    if val is None:
        raise ValueError("Timestamp value cannot be None")

    if isinstance(val, (int, float)):
        ts = float(val)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return ts, dt.isoformat()

    if isinstance(val, datetime):
        if val.tzinfo is None:
            # Naive datetime: assume UTC
            ts = val.replace(tzinfo=timezone.utc).timestamp()
            iso_str = val.replace(tzinfo=timezone.utc).isoformat()
        else:
            ts = val.timestamp()
            iso_str = val.isoformat()
        return ts, iso_str

    if isinstance(val, str):
        val_clean = val.strip()
        # Try numeric string
        try:
            ts = float(val_clean)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return ts, dt.isoformat()
        except ValueError:
            pass

        # Try ISO string
        iso_norm = val_clean.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_norm)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp(), dt.isoformat()

    raise ValueError(f"Unsupported timestamp format: {type(val)} ({val})")


@dataclass
class MarketFreshnessResult:
    """Evaluation result for market data freshness."""
    is_fresh: bool
    staleness_seconds: float
    market_time: str
    current_time: str
    max_staleness_seconds: float = 3.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_fresh": self.is_fresh,
            "staleness_seconds": round(self.staleness_seconds, 6),
            "market_time": self.market_time,
            "current_time": self.current_time,
            "max_staleness_seconds": self.max_staleness_seconds,
            "reason": self.reason,
        }


def check_market_data_fresh(
    market_time: Union[int, float, str, datetime],
    current_time: Optional[Union[int, float, str, datetime]] = None,
    max_staleness_seconds: float = 3.0,
    clock: Optional[Callable[[], Union[int, float, str, datetime]]] = None,
) -> MarketFreshnessResult:
    """
    Check if market data timestamp is fresh (<= max_staleness_seconds, default 3.0s).
    Pure logic: does not fetch market quotes or connect to network.
    """
    if current_time is None:
        if clock is not None:
            current_time = clock()
        else:
            current_time = datetime.now(timezone.utc)

    try:
        m_ts, m_iso = _to_timestamp_and_iso(market_time)
        c_ts, c_iso = _to_timestamp_and_iso(current_time)
    except Exception as exc:
        return MarketFreshnessResult(
            is_fresh=False,
            staleness_seconds=float("inf"),
            market_time=str(market_time),
            current_time=str(current_time),
            max_staleness_seconds=max_staleness_seconds,
            reason=f"Invalid timestamp format: {exc}",
        )

    staleness = c_ts - m_ts

    # Allow slight future skew (e.g. up to 0.5s network/clock jitter) but reject significant future skew
    if staleness < -0.5:
        return MarketFreshnessResult(
            is_fresh=False,
            staleness_seconds=staleness,
            market_time=m_iso,
            current_time=c_iso,
            max_staleness_seconds=max_staleness_seconds,
            reason=f"Market time is in future: skew {abs(staleness):.3f}s exceeds 0.5s tolerance",
        )

    # <= 3.0s requirement (boundary: 3.0s is fresh, >3.0s is stale)
    if staleness <= max_staleness_seconds:
        return MarketFreshnessResult(
            is_fresh=True,
            staleness_seconds=max(0.0, staleness),
            market_time=m_iso,
            current_time=c_iso,
            max_staleness_seconds=max_staleness_seconds,
            reason="Market data within freshness threshold",
        )

    return MarketFreshnessResult(
        is_fresh=False,
        staleness_seconds=staleness,
        market_time=m_iso,
        current_time=c_iso,
        max_staleness_seconds=max_staleness_seconds,
        reason=f"Market data stale: {staleness:.3f}s > {max_staleness_seconds:.3f}s",
    )


@dataclass
class GateResult:
    """Deployment gate evaluation result."""
    gate_name: str
    trading_day: str
    status: GateStatus
    passed: bool
    evaluated_at: str
    checks: Dict[str, bool]
    failed_checks: List[str]
    reject_codes: List[str]
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to a dictionary for UI and logging."""
        return {
            "gate_name": self.gate_name,
            "trading_day": self.trading_day,
            "status": self.status.value if isinstance(self.status, GateStatus) else str(self.status),
            "passed": self.passed,
            "evaluated_at": self.evaluated_at,
            "checks": dict(self.checks),
            "failed_checks": list(self.failed_checks),
            "reject_codes": list(self.reject_codes),
            "details": dict(self.details),
        }


class SubnewDeploymentGate:
    """
    Deterministic deployment gate core for subnew stock strategy.

    Enforces:
    - Gate 1 (09:15) check requirements
    - Gate 2 (09:25) fixed 8-item ALL GREEN requirement
    - One-way safety latch: once downgraded to MONITOR_ONLY on a trading day,
      never automatically upgrades back to CONFIRM on that day.
    - Explicit reset_for_trading_day(new_date) to clear previous day latch.
    - Clock injection for deterministic testing.
    """

    def __init__(
        self,
        trading_day: str = "2026-09-22",
        clock: Optional[Callable[[], Union[int, float, str, datetime]]] = None,
    ) -> None:
        self.trading_day: str = str(trading_day)
        self._clock: Callable[[], Union[int, float, str, datetime]] = (
            clock if clock is not None else (lambda: datetime.now(timezone.utc))
        )
        self._latched_monitor_only: bool = False
        self._latch_reason: Optional[str] = None
        self._latch_time: Optional[str] = None
        self._history: List[GateResult] = []

    @property
    def latched_monitor_only(self) -> bool:
        """True if the gate is latched in MONITOR_ONLY state for the current trading day."""
        return self._latched_monitor_only

    @property
    def latch_reason(self) -> Optional[str]:
        return self._latch_reason

    @property
    def latch_time(self) -> Optional[str]:
        return self._latch_time

    def is_latched(self) -> bool:
        """Check if one-way safety latch is engaged."""
        return self._latched_monitor_only

    def current_status(self) -> GateStatus:
        """Return current effective status based on latch state."""
        if self._latched_monitor_only:
            return GateStatus.MONITOR_ONLY
        return GateStatus.CONFIRM

    def get_history(self) -> List[GateResult]:
        """Return all evaluated gate results."""
        return list(self._history)

    def reset_for_trading_day(self, new_trading_day: str) -> None:
        """
        Explicitly reset the gate for a new trading day, releasing any previous day NO-GO latch.
        """
        self.trading_day = str(new_trading_day)
        self._latched_monitor_only = False
        self._latch_reason = None
        self._latch_time = None

    def _get_current_time(
        self,
        override_time: Optional[Union[int, float, str, datetime]] = None,
    ) -> Tuple[float, str]:
        """Obtain current timestamp and formatted ISO string."""
        if override_time is not None:
            return _to_timestamp_and_iso(override_time)
        return _to_timestamp_and_iso(self._clock())

    def verify_market_data_fresh(
        self,
        market_time: Union[int, float, str, datetime],
        current_time: Optional[Union[int, float, str, datetime]] = None,
        max_staleness_seconds: float = 3.0,
    ) -> MarketFreshnessResult:
        """Verify market data freshness using configured clock."""
        return check_market_data_fresh(
            market_time=market_time,
            current_time=current_time,
            max_staleness_seconds=max_staleness_seconds,
            clock=self._clock,
        )

    def evaluate_gate1(
        self,
        checks: Optional[Dict[str, bool]] = None,
        *,
        details: Optional[Dict[str, Any]] = None,
        current_time: Optional[Union[int, float, str, datetime]] = None,
        **kwargs: Any,
    ) -> GateResult:
        """
        Evaluate Gate 1 (09:15).
        Requires at least:
        - build_identity
        - account_reconciliation
        - sellable_init (or T+1/sellable aliases)
        - pending_directives_empty_at_boot
        """
        merged_checks: Dict[str, bool] = {}
        if checks:
            merged_checks.update(checks)
        for k, v in kwargs.items():
            if isinstance(v, bool):
                merged_checks[k] = v

        # Normalize aliases
        normalized_checks: Dict[str, bool] = {}
        for k, v in merged_checks.items():
            norm_key = GATE1_ALIASES.get(k, k)
            normalized_checks[norm_key] = bool(v)

        return self._evaluate(
            gate_name="GATE1",
            required_checks=GATE1_REQUIRED_CHECKS,
            provided_checks=normalized_checks,
            details=details,
            current_time=current_time,
        )

    def evaluate_gate2(
        self,
        checks: Optional[Dict[str, bool]] = None,
        *,
        market_time: Optional[Union[int, float, str, datetime]] = None,
        max_staleness_seconds: float = 3.0,
        details: Optional[Dict[str, Any]] = None,
        current_time: Optional[Union[int, float, str, datetime]] = None,
        **kwargs: Any,
    ) -> GateResult:
        """
        Evaluate Gate 2 (09:25).
        Requires all fixed 8 items to be True:
        1. build_identity
        2. market_data_fresh
        3. account_reconciliation
        4. sellable_qty_reconciliation
        5. pending_directives_empty_at_boot
        6. duplicate_plan_check
        7. EXIT_BUY_contract
        8. risk_execution_path
        """
        merged_checks: Dict[str, bool] = {}
        if checks:
            merged_checks.update(checks)
        for k, v in kwargs.items():
            if isinstance(v, bool):
                merged_checks[k] = v

        # Normalize aliases
        normalized_checks: Dict[str, bool] = {}
        for k, v in merged_checks.items():
            norm_key = GATE2_ALIASES.get(k, k)
            normalized_checks[norm_key] = bool(v)

        eval_details = dict(details) if details else {}

        # If market_data_fresh is not explicitly provided but market_time is given, compute freshness
        if "market_data_fresh" not in normalized_checks and market_time is not None:
            freshness_result = self.verify_market_data_fresh(
                market_time=market_time,
                current_time=current_time,
                max_staleness_seconds=max_staleness_seconds,
            )
            normalized_checks["market_data_fresh"] = freshness_result.is_fresh
            eval_details["market_freshness"] = freshness_result.to_dict()

        # If EXIT_BUY_contract is not explicitly provided but directives is given, evaluate contract
        if "EXIT_BUY_contract" not in normalized_checks and "directives" in kwargs:
            from ats.strategy.signal_convergence import check_exit_buy_contract
            contract_ok, violations = check_exit_buy_contract(kwargs["directives"])
            normalized_checks["EXIT_BUY_contract"] = contract_ok
            if not contract_ok:
                eval_details["exit_buy_contract_violations"] = violations

        # Frozen replay/release gate is a hard veto on the execution path.
        # It never upgrades a RED gate; it can only force risk/build checks false.
        replay_result = kwargs.get("replay_release_result")
        if replay_result is not None:
            replay_dict = (
                replay_result.to_dict()
                if callable(getattr(replay_result, "to_dict", None))
                else dict(replay_result) if isinstance(replay_result, dict) else {}
            )
            replay_passed = bool(replay_dict.get("passed", False))
            replay_checks = dict(replay_dict.get("checks") or {})
            normalized_checks["risk_execution_path"] = (
                bool(normalized_checks.get("risk_execution_path", True))
                and replay_passed
            )
            if "build_identity" in replay_checks:
                normalized_checks["build_identity"] = (
                    bool(normalized_checks.get("build_identity", True))
                    and bool(replay_checks.get("build_identity"))
                )
            eval_details["replay_release_gate"] = replay_dict

        # If trading_center is provided, auto-inspect state for missing checks
        tc = kwargs.get("trading_center")
        if tc is not None:
            if "EXIT_BUY_contract" not in normalized_checks:
                from ats.strategy.signal_convergence import check_exit_buy_contract
                contract_ok, violations = check_exit_buy_contract(tc.get_pending_directives())
                normalized_checks["EXIT_BUY_contract"] = contract_ok
                if not contract_ok:
                    eval_details["exit_buy_contract_violations"] = violations
            if "account_reconciliation" not in normalized_checks:
                mismatches = getattr(tc, "get_reconciliation_mismatches", lambda: {})()
                normalized_checks["account_reconciliation"] = (len(mismatches) == 0)
                if mismatches:
                    eval_details["reconciliation_mismatches"] = mismatches
            if "sellable_qty_reconciliation" not in normalized_checks:
                mismatches = getattr(tc, "get_reconciliation_mismatches", lambda: {})()
                has_sellable_mismatch = any(
                    m.get("sellable_diff", 0) != 0 for m in mismatches.values()
                )
                normalized_checks["sellable_qty_reconciliation"] = (not has_sellable_mismatch)

        return self._evaluate(
            gate_name="GATE2",
            required_checks=GATE2_REQUIRED_CHECKS,
            provided_checks=normalized_checks,
            details=eval_details,
            current_time=current_time,
        )

    def evaluate(
        self,
        gate_name: str,
        checks: Optional[Dict[str, bool]] = None,
        *,
        details: Optional[Dict[str, Any]] = None,
        current_time: Optional[Union[int, float, str, datetime]] = None,
        **kwargs: Any,
    ) -> GateResult:
        """Generic evaluate dispatcher for GATE1 or GATE2."""
        gn = gate_name.upper()
        if gn in ("GATE1", "GATE_1", "1"):
            return self.evaluate_gate1(checks, details=details, current_time=current_time, **kwargs)
        elif gn in ("GATE2", "GATE_2", "2"):
            return self.evaluate_gate2(checks, details=details, current_time=current_time, **kwargs)
        raise ValueError(f"Unknown gate name: {gate_name}. Expected 'GATE1' or 'GATE2'.")

    def _evaluate(
        self,
        gate_name: str,
        required_checks: Tuple[str, ...],
        provided_checks: Dict[str, bool],
        details: Optional[Dict[str, Any]] = None,
        current_time: Optional[Union[int, float, str, datetime]] = None,
    ) -> GateResult:
        """Internal evaluation engine with one-way safety latch."""
        _, eval_iso = self._get_current_time(current_time)
        res_details = dict(details) if details else {}

        evaluated_checks: Dict[str, bool] = {}
        failed_checks: List[str] = []
        reject_codes: List[str] = []

        # Evaluate all required items
        for req in required_checks:
            if req in provided_checks:
                passed = bool(provided_checks[req])
                evaluated_checks[req] = passed
                if not passed:
                    failed_checks.append(req)
                    reject_codes.append(f"REJECT_{req.upper()}")
            else:
                # Missing check treated as failure
                evaluated_checks[req] = False
                failed_checks.append(req)
                reject_codes.append(f"MISSING_{req.upper()}")

        # Record any extra checks provided
        for k, v in provided_checks.items():
            if k not in evaluated_checks:
                evaluated_checks[k] = bool(v)
                if not bool(v):
                    failed_checks.append(k)
                    reject_codes.append(f"REJECT_{k.upper()}")

        all_green = len(failed_checks) == 0

        if not all_green:
            # Downgrade and engage one-way safety latch
            if not self._latched_monitor_only:
                self._latched_monitor_only = True
                self._latch_reason = f"Failed checks in {gate_name}: {', '.join(failed_checks)}"
                self._latch_time = eval_iso

            status = GateStatus.MONITOR_ONLY
            is_passed = False
        else:
            # All checks evaluated green, but check if already latched on this day
            if self._latched_monitor_only:
                status = GateStatus.MONITOR_ONLY
                is_passed = False
                latch_code = "DAY_LATCHED_MONITOR_ONLY"
                failed_checks.append(latch_code)
                reject_codes.append(latch_code)
                res_details["latch_info"] = {
                    "reason": self._latch_reason,
                    "latched_at": self._latch_time,
                }
            else:
                status = GateStatus.CONFIRM
                is_passed = True

        result = GateResult(
            gate_name=gate_name,
            trading_day=self.trading_day,
            status=status,
            passed=is_passed,
            evaluated_at=eval_iso,
            checks=evaluated_checks,
            failed_checks=failed_checks,
            reject_codes=reject_codes,
            details=res_details,
        )

        self._history.append(result)
        return result
