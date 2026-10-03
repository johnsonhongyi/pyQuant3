"""Nonblocking in-memory bridge from validated IPO observations to Gate 0."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from zoneinfo import ZoneInfo

from ats.strategy.ipo_data_contracts import (
    LRRM_REQUIRED_FIELDS,
    REGIME_REQUIRED_FIELDS,
    LIVE_HEAT_REQUIRED_FIELDS,
    PREHEAT_REQUIRED_FIELDS,
    IPODecisionConfigSnapshot,
)
from ats.strategy.ipo_regime_fsm import IPORegimeFSM, IPORegimeSnapshot
from ats.strategy.lrrm_engine import LRRMEngine, LRRMSnapshot
from ats.strategy.ipo_live_heat_engine import IPOLiveHeatEngine, IPOLiveHeatSnapshot
from ats.strategy.ipo_preheat_engine import IPOPreHeatEngine, IPOPreHeatSnapshot, PreHeatConfig
from ats.strategy.t1_carry_evaluator import T1CarryEvaluator, T1CarryResult
from ats.strategy.listing_anchor_store import ListingAnchorStore
from ats.strategy.ipo_source_orchestrator import SOURCE_DB_RELATIVE_PATH


def _resolve_project_root() -> Path:
    """
    在打包（PyInstaller onefile）与开发环境下均正确定位项目根目录。
    - 打包模式：__file__ 在 _MEIPASS 临时目录，parents[2] = _MEIPASS，
      必须使用 sys_utils.get_app_root() 获取 EXE 所在物理目录的 config/。
    - 开发模式：fallback 到 parents[2]（工程源码根）。
    """
    try:
        from sys_utils import get_app_root, is_packaged_env, safe_resolve_path
        if is_packaged_env():
            return safe_resolve_path(get_app_root())
    except Exception:
        pass
    try:
        return Path(__file__).resolve().parents[2]
    except OSError:
        return Path(__file__).absolute().parents[2]


DEFAULT_ROOT = _resolve_project_root()
_TICKER_FIELDS = frozenset(PREHEAT_REQUIRED_FIELDS + LIVE_HEAT_REQUIRED_FIELDS)


def _ensure_yaml_config(yaml_path: Path) -> Path:
    """
    Lazy 自愈守卫：读取 yaml 前检查物理文件是否存在。
    - 存在（开发/已释放）→ 直接返回，不做任何操作，不会覆盖。
    - 缺失（新打包首运行/文件意外丢失）→ 通过 get_conf_path() 触发自愈引擎从 bundle 释放。
    确保访问路径与自愈路径完全一致，彻底闭合 lazy 恢复闭环。
    """
    if yaml_path.exists():
        return yaml_path   # 文件存在：开发环境/已释放，直接返回，绝不覆盖
    try:
        from sys_utils import get_conf_path
        released = get_conf_path(str(yaml_path))
        if released:
            return Path(released)
    except Exception:
        pass
    return yaml_path   # 兜底：返回原路径，由调用方决定如何处理


def _is_market_session_active() -> bool:
    try:
        from ats.tdx_realtime_fetcher import is_trading_time

        return bool(is_trading_time()[0])
    except Exception:
        return False


class IPOGateContextProvider:
    """Serve a validated, immutable data snapshot without I/O on the Gate path."""

    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self._root = Path(root).resolve()
        self._lock = threading.RLock()
        self._config_fields: Dict[str, Any] = {}
        self._observations_by_ticker: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._vwap_snapshots: Dict[str, Any] = {}
        self._listing_anchors_by_ticker: Dict[str, Any] = {}
        self._listing_anchor_store_state = "UNREADY"
        self._preheat_engine: Optional[IPOPreHeatEngine] = None
        self._last_refresh_at = ""
        self._last_refresh_ok = False
        self._last_refresh_error = "尚未刷新"
        self._refresh_stop = threading.Event()
        self._refresh_thread: Optional[threading.Thread] = None
        self._store_file_present = False
        self._stored_observation_count = 0
        self._stored_observed_count = 0
        self._latest_context_readiness: Dict[str, Any] = {}

    def invalidate(self) -> None:
        with self._lock:
            self._config_fields = {}
            self._observations_by_ticker = {}
            self._vwap_snapshots = {}
            self._listing_anchors_by_ticker = {}
            self._listing_anchor_store_state = "UNREADY"
            self._preheat_engine = None
            self._latest_context_readiness = {}
            self._stored_observation_count = 0
            self._stored_observed_count = 0

    def refresh(self, config: Optional[IPODecisionConfigSnapshot] = None) -> bool:
        """Load config-bound observations outside the order decision path."""
        try:
            if config is None:
                _yaml_path = _ensure_yaml_config(self._root / "config" / "ipo_sentiment.yaml")
                config = IPODecisionConfigSnapshot.from_yaml(str(_yaml_path))
            config_fields = config.gate_context_fields()
            preheat_section = config.decision_config.get("ipo_preheat")
            preheat_engine = IPOPreHeatEngine(PreHeatConfig.from_mapping(preheat_section))
            observations = self._read_observations(config)
            vwap_snapshots = {
                ticker: snapshot
                for ticker in observations if ticker != "000000"
                if observations[ticker].get("current_price", {}).get("status") == "OBSERVED"
                if (snapshot := self._read_vwap_snapshot(ticker)) is not None
            }
            anchor_path = self._root / "config" / "listing_anchors.json"
            listing_anchor_store_state = "READY" if anchor_path.is_file() else "MISSING"
            try:
                raw_anchors = ListingAnchorStore(anchor_path).latest_by_code()
            except (OSError, ValueError):
                raw_anchors = {}
                listing_anchor_store_state = "INVALID"
            listing_anchors = {
                ticker: anchor
                for ticker, anchor in raw_anchors.items()
                if anchor.matches_contract(config.config_hash, config.data_contract.config_hash)
            }
            all_observations = [
                observation
                for ticker_rows in observations.values()
                for observation in ticker_rows.values()
            ]
            stored_observation_count = len(all_observations)
            stored_observed_count = sum(
                observation.get("status") == "OBSERVED" for observation in all_observations
            )
            store_file_present = (self._root / SOURCE_DB_RELATIVE_PATH).is_file()
        except Exception as exc:
            self.invalidate()
            with self._lock:
                self._last_refresh_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                self._last_refresh_ok = False
                self._last_refresh_error = type(exc).__name__
            self._publish_status()
            return False
        with self._lock:
            self._config_fields = config_fields
            self._observations_by_ticker = observations
            self._vwap_snapshots = vwap_snapshots
            self._listing_anchors_by_ticker = listing_anchors
            self._listing_anchor_store_state = listing_anchor_store_state
            self._preheat_engine = preheat_engine
            self._stored_observation_count = stored_observation_count
            self._stored_observed_count = stored_observed_count
            self._store_file_present = store_file_present
            self._last_refresh_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._last_refresh_ok = True
            self._last_refresh_error = ""
        self._publish_status()
        return True

    def start_auto_refresh(self, interval_seconds: float = 5.0) -> bool:
        """Refresh the SQLite bridge in the ATS process, away from the order path."""
        if (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, (int, float))
            or not 1.0 <= float(interval_seconds) <= 300.0
        ):
            return False
        try:
            from JohnsonUtil import commonTips as cct
            enabled = getattr(cct, 'ipo_learning_console',
                              getattr(getattr(cct, 'CFG', None), 'ipo_learning_console', False))
            if str(enabled).strip().lower() not in {'true', '1', 'yes', 'on'}:
                return False
        except Exception:
            return False
        with self._lock:
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return True
            self._refresh_stop.clear()

            def refresh_loop() -> None:
                while not self._refresh_stop.is_set():
                    if _is_market_session_active():
                        self.refresh()
                        wait_seconds = float(interval_seconds)
                    else:
                        self._publish_status()
                        wait_seconds = 60.0
                    if self._refresh_stop.wait(wait_seconds):
                        break

            self._refresh_thread = threading.Thread(
                target=refresh_loop, name="ipo-gate-context-refresh", daemon=True
            )
            self._refresh_thread.start()
        return True

    def stop_auto_refresh(self, timeout_seconds: float = 1.0) -> None:
        self._refresh_stop.set()
        thread = self._refresh_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(max(0.0, min(float(timeout_seconds), 5.0)))

    def status_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            readiness = dict(self._latest_context_readiness)
            remaining = readiness.get("remaining_contexts", {})
            typed_contexts_ready = bool(remaining) and all(
                isinstance(value, str) and value.startswith(("READY", "AVAILABLE"))
                for value in remaining.values()
            )
            state = (
                "UNREADY" if not self._last_refresh_ok else
                "STORE_MISSING" if not self._store_file_present else
                "EMPTY" if not self._stored_observation_count else "SYNCED"
            )
            return {
                "state": state,
                "updated_at": self._last_refresh_at,
                "reader_process_id": os.getpid(),
                "store_file_present": self._store_file_present,
                "stored_observation_count": self._stored_observation_count,
                "stored_observed_count": self._stored_observed_count,
                "refresh_error": self._last_refresh_error,
                "typed_gate_contexts_ready": typed_contexts_ready,
                "latest_context_readiness": readiness,
                "runtime_authorized": False,
                "transport": "SQLite只读快照",
            }

    def _publish_status(self) -> None:
        path = self._root / "data" / "ipo_learning" / "gate_context_provider.latest.json"
        try:
            from JohnsonUtil import commonTips as cct
            enabled = getattr(cct, 'ipo_learning_console',
                              getattr(getattr(cct, 'CFG', None), 'ipo_learning_console', False))
            if str(enabled).strip().lower() not in {'true', '1', 'yes', 'on'}:
                return
            status = self.status_snapshot()
            from ats.bounded_evaluation_store import evaluation_store
            from ats.storage_archive import write_json_gzip
            evaluation_store.put(str(path), status, write_json_gzip)
        except Exception:
            return

    def _read_observations(
        self, config: IPODecisionConfigSnapshot
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        path = self._root / SOURCE_DB_RELATIVE_PATH
        if not path.is_file():
            return {}
        uri = path.as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.5) as connection:
            connection.execute("PRAGMA query_only=ON")
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(field_observations)"
                ).fetchall()
            }
            sample_count_column = "sample_count" if "sample_count" in columns else "NULL"
            cohort_id_column = "cohort_id" if "cohort_id" in columns else "NULL"
            sample_metadata = f", {sample_count_column}, {cohort_id_column}"
            global_rows = connection.execute(
                "SELECT ticker, field_id, status, value_json, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc, configuration_hash, "
                "data_contract_hash" + sample_metadata + " FROM field_observations WHERE ticker='000000'"
            ).fetchall()
            ticker_rows = connection.execute(
                "SELECT ticker, field_id, status, value_json, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc, configuration_hash, "
                "data_contract_hash" + sample_metadata + " FROM field_observations WHERE ticker<>'000000' "
                "ORDER BY updated_at_utc DESC LIMIT 10000"
            ).fetchall()

        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in global_rows + ticker_rows:
            ticker, field_id = str(row[0]), str(row[1])
            if field_id not in config.data_contract.required_fields:
                continue
            if ticker == "000000" and field_id in _TICKER_FIELDS:
                continue
            try:
                value = json.loads(row[3]) if row[3] is not None else None
            except (TypeError, ValueError):
                value = None
                status = "UNREADY_INVALID_VALUE"
            else:
                status = str(row[2])
            if (
                row[9] != config.config_hash
                or row[10] != config.data_contract.config_hash
            ):
                status = "UNREADY_CONTRACT_HASH_MISMATCH"
            observation = {
                "status": status,
                "value": value,
                "source_id": row[4],
                "source_version": row[5],
                "source_timezone": row[6],
                "as_of_time": row[7],
                "available_at": row[8],
                "sample_count": row[11],
                "cohort_id": row[12],
            }
            result.setdefault(ticker, {})[field_id] = observation
        return result

    def __call__(self, directive: Any) -> Mapping[str, Any]:
        raw_code = str(getattr(directive, "code", "") or "").strip()
        code = raw_code.zfill(6) if raw_code.isdigit() and len(raw_code) <= 6 else ""
        with self._lock:
            config_fields = dict(self._config_fields)
            observations_by_ticker = self._observations_by_ticker
            vwap_snapshots = self._vwap_snapshots
            listing_anchors_by_ticker = self._listing_anchors_by_ticker
            preheat_engine = self._preheat_engine
            observations = {
                key: dict(value)
                for key, value in observations_by_ticker.get("000000", {}).items()
            }
            ticker_observations = {
                key: dict(value)
                for key, value in (observations_by_ticker.get(code, {}) if code else {}).items()
            }
            observations.update(ticker_observations)

        now = datetime.now(timezone.utc)
        data_contract = config_fields.get("data_contract")
        observation_checks: Dict[str, str] = {}
        observation_usable: Dict[str, bool] = {}
        if data_contract is not None:
            for field_id, observation in observations.items():
                stored_status = observation.get("status")
                if isinstance(stored_status, str) and stored_status.startswith("UNREADY_"):
                    observation_checks[field_id] = stored_status
                    observation_usable[field_id] = False
                    observation["status"] = "UNREADY"
                    observation["value"] = None
                    observation["reason_code"] = stored_status
                    continue
                check = data_contract.validate_observation(field_id, observation, now)
                observation_checks[field_id] = check.reason_code or check.status
                observation_usable[field_id] = check.usable
                observation["status"] = check.status if check.usable else "UNREADY"
                observation["value"] = check.value if check.usable else None
                observation["reason_code"] = check.reason_code or ""

        validated_ticker_observations = {
            field_id: observations[field_id]
            for field_id in ticker_observations if field_id in observations
        }
        live_heat = self._build_live_heat(code, validated_ticker_observations)
        preheat = self._build_preheat(
            directive, code, observations, preheat_engine, now
        )
        vwap = vwap_snapshots.get(code)
        listing_anchors = listing_anchors_by_ticker.get(code)
        lrrm_metrics = {
            field_id: self._observed_value(observations, field_id)
            for field_id in LRRM_REQUIRED_FIELDS
        }
        lrrm = LRRMEngine(LRRM_REQUIRED_FIELDS).evaluate_contract_metrics(
            lrrm_metrics,
            {field_id: observation_usable.get(field_id, False) for field_id in LRRM_REQUIRED_FIELDS},
            as_of=now,
        )
        regime_metrics = {
            field_id: self._observed_value(observations, field_id)
            for field_id in REGIME_REQUIRED_FIELDS
        }
        regime_rows = [observations.get(field_id, {}) for field_id in REGIME_REQUIRED_FIELDS]
        sample_counts = [row.get("sample_count") for row in regime_rows]
        cohort_ids = {row.get("cohort_id") for row in regime_rows}
        regime_sample_count = (
            sample_counts[0]
            if sample_counts and all(
                isinstance(count, int) and not isinstance(count, bool)
                and count == sample_counts[0] for count in sample_counts
            ) else 0
        )
        regime_cohort_id = (
            next(iter(cohort_ids))
            if len(cohort_ids) == 1 and all(isinstance(value, str) for value in cohort_ids)
            else ""
        )
        decision_config = config_fields.get("decision_config", {})
        ipo_regime_config = decision_config.get("ipo_regime", {}) if isinstance(decision_config, Mapping) else {}
        regime_thresholds = (
            ipo_regime_config.get("transition_thresholds", {})
            if isinstance(ipo_regime_config, Mapping) else {}
        )
        ipo_regime = IPORegimeFSM(REGIME_REQUIRED_FIELDS).update_from_contract_metrics(
            regime_metrics,
            {field_id: observation_usable.get(field_id, False) for field_id in REGIME_REQUIRED_FIELDS},
            regime_sample_count,
            regime_cohort_id,
            regime_thresholds,
            lrrm=lrrm,
            as_of=now,
        )
        carry_config = decision_config.get("t1_carry", {}) if isinstance(decision_config, Mapping) else {}
        try:
            t1_carry = T1CarryEvaluator(carry_config).evaluate(code, live_heat, ipo_regime, lrrm)
        except (TypeError, ValueError):
            t1_carry = T1CarryResult(veto_reason="T1_CARRY_CONFIG_INVALID")
        listing_age_sessions = self._listing_age_sessions(listing_anchors, now)
        context_readiness = {
            "ticker": code,
            "preheat_state": "READY" if preheat.data_status == "READY" else "UNREADY",
            "preheat_reason": preheat.unready_reason_code or "",
            "live_heat_state": "READY" if live_heat.data_ready else "UNREADY",
            "live_heat_reason": live_heat.veto_reason or "",
            "vwap_state": "AVAILABLE" if vwap is not None else "UNREADY",
            "listing_anchors_state": "READY" if listing_anchors is not None else self._listing_anchor_store_state,
            "remaining_contexts": {
                "lrrm": "READY" if lrrm.data_ready else "UNREADY:" + lrrm.transition_reason[:160],
                "ipo_regime": "READY" if ipo_regime.data_ready else "UNREADY:" + ";".join(ipo_regime.missing_metrics)[:160],
                "t1_carry": "READY" if t1_carry.data_ready else "UNREADY:" + t1_carry.veto_reason,
                "listing_anchors": "READY:配置哈希/数据字典哈希/来源时区匹配" if listing_anchors is not None else f"UNREADY:{self._listing_anchor_store_state}",
                "vwap": "AVAILABLE:来自ATS进程内VWAPFactory" if vwap is not None else "UNREADY:尚未接入有效VWAP快照",
                "listing_age_sessions": "READY" if listing_age_sessions is not None else "UNREADY:可信交易日历不可用",
                "risk_context": "UNREADY:运行时RiskGate账户态未接入",
            },
            "validated_field_count": sum(
                observation_usable.values()
            ),
            "unready_field_count": sum(
                not usable for usable in observation_usable.values()
            ),
            "missing_required_field_count": (
                len(set(data_contract.required_fields) - set(observations))
                if data_contract is not None else 0
            ),
        }
        with self._lock:
            self._latest_context_readiness = context_readiness
        freshness = decision_config.get("vwap_freshness", {}) if isinstance(decision_config, Mapping) else {}
        max_vwap_stale = freshness.get("max_stale_seconds", 0) if isinstance(freshness, Mapping) else 0
        issue_observation = observations.get("issue_price", {})
        issue_price = issue_observation.get("value") if issue_observation.get("status") == "OBSERVED" else None
        context = dict(config_fields)
        context.update({
            "lrrm": lrrm,
            "ipo_regime": ipo_regime,
            "t1_carry": t1_carry,
            "preheat": preheat,
            "listing_anchors": listing_anchors,
            "vwap": vwap,
            "live_heat": live_heat,
            "intraday_low": self._observed_value(observations, "session_low"),
            "listing_age_sessions": listing_age_sessions,
            "d0_listing_open_price": listing_anchors.listing_open if listing_anchors else None,
            "market_as_of_time": now,
            "max_vwap_stale_seconds": max_vwap_stale,
            "risk_context": None,
            "issue_price": issue_price,
            "data_observations": observations,
            "observation_checks": observation_checks,
            "gate_context_readiness": context_readiness,
            "gate_context_sync": self.status_snapshot(),
        })
        return context

    @staticmethod
    def _listing_age_sessions(listing_anchors: Any, evaluation_time: datetime) -> Optional[int]:
        if listing_anchors is None or not isinstance(evaluation_time, datetime):
            return None
        listing_date = str(getattr(listing_anchors, "listing_date", "") or "")[:10]
        try:
            first = datetime.strptime(listing_date, "%Y-%m-%d").date()
            last = evaluation_time.astimezone(ZoneInfo("Asia/Shanghai")).date()
            if first > last:
                return None
            from JohnsonUtil import commonTips as cct

            sessions = cct.get_trade_days(first.isoformat(), last.isoformat())
            normalized = {str(day)[:10] for day in (sessions or [])}
            if first.isoformat() not in normalized or last.isoformat() not in normalized:
                return None
            age = sum(first.isoformat() <= day <= last.isoformat() for day in normalized)
            return age if age >= 1 else None
        except Exception:
            return None

    @staticmethod
    def _observed_value(observations: Mapping[str, Mapping[str, Any]], field_id: str) -> Any:
        item = observations.get(field_id, {})
        return item.get("value") if item.get("status") == "OBSERVED" else None

    @staticmethod
    def _build_live_heat(
        code: str, observations: Mapping[str, Mapping[str, Any]]
    ) -> IPOLiveHeatSnapshot:
        missing = [
            field_id for field_id in LIVE_HEAT_REQUIRED_FIELDS
            if IPOGateContextProvider._observed_value(observations, field_id) is None
        ]
        if not code or missing:
            return IPOLiveHeatSnapshot(
                code=code,
                veto_reason=("缺少实时字段: " + ",".join(missing)) if missing else "股票代码无效",
            )
        values = {
            field_id: IPOGateContextProvider._observed_value(observations, field_id)
            for field_id in LIVE_HEAT_REQUIRED_FIELDS
        }
        try:
            observed_at = datetime.fromisoformat(
                str(observations["current_price"]["as_of_time"]).replace("Z", "+00:00")
            ).astimezone(ZoneInfo("Asia/Shanghai"))
            return IPOLiveHeatEngine().evaluate(
                code=code,
                ret_pct=values["ret_pct"],
                turnover_pct=values["turnover_pct"],
                price_vwap_dist_pct=values["price_vwap_dist_pct"],
                open_premium_pct=values["open_premium_pct"],
                slope_deg=values["slope_deg"],
                high_p=values["session_high"],
                low_p=values["session_low"],
                curr_p=values["current_price"],
                turnover_climb_speed=values["turnover_climb_speed"],
                minutes_above_vwap_ratio=values["minutes_above_vwap_ratio"],
                pullback_from_peak_pct=values["pullback_from_peak_pct"],
                halt_count=values["halt_count"],
                now_hm=observed_at.strftime("%H%M"),
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return IPOLiveHeatSnapshot(code=code, veto_reason="实时热度字段或来源时间无效")

    @staticmethod
    def _build_preheat(
        directive: Any,
        code: str,
        observations: Mapping[str, Mapping[str, Any]],
        engine: Optional[IPOPreHeatEngine],
        evaluation_time: datetime,
    ) -> IPOPreHeatSnapshot:
        name = str(getattr(directive, "name", "") or "").strip()
        if engine is None:
            return IPOPreHeatSnapshot(code=code, name=name, unready_reason_code="PREHEAT_CONFIG_UNREADY")
        missing = [
            field_id for field_id in PREHEAT_REQUIRED_FIELDS
            if observations.get(field_id, {}).get("status") not in {"OBSERVED", "MISSING_CONFIRMED"}
        ]
        if not code or missing:
            return IPOPreHeatSnapshot(
                code=code,
                name=name,
                unready_reason_code=("MISSING_PREHEAT_FIELDS:" + ",".join(missing))
                if missing else "IDENTITY_MISSING",
            )
        source_times: Dict[str, datetime] = {}
        try:
            for field_id in PREHEAT_REQUIRED_FIELDS:
                raw_time = observations[field_id].get("as_of_time")
                source_times[field_id] = datetime.fromisoformat(
                    str(raw_time).replace("Z", "+00:00")
                )
            pe_observation = observations["pe_ratio"]
            pe_status = pe_observation["status"]
            return engine.evaluate(
                code=code,
                name=name,
                issue_price=observations["issue_price"]["value"],
                float_shares_wan=observations["float_shares_wan"]["value"],
                pe_ratio=pe_observation["value"] if pe_status == "OBSERVED" else None,
                pe_status=pe_status,
                industry_pe_median=observations["industry_pe_median"]["value"],
                online_sub_multiple=observations["online_sub_multiple"]["value"],
                winning_rate_pct=observations["winning_rate_pct"]["value"],
                scarcity_rank=observations["scarcity_rank"]["value"],
                hot_themes=observations["hot_themes"]["value"],
                as_of_date=evaluation_time.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
                source_as_of=source_times,
                evaluation_time=evaluation_time,
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return IPOPreHeatSnapshot(
                code=code, name=name, unready_reason_code="INVALID_PREHEAT_SOURCE_DATA"
            )

    @staticmethod
    def _read_vwap_snapshot(code: str) -> Any:
        if not code:
            return None
        try:
            from ats.vwap_factory import VWAPFactory

            return VWAPFactory.get_instance().peek_snapshot(code)
        except Exception:
            return None


_PROVIDERS: Dict[str, IPOGateContextProvider] = {}
_PROVIDERS_LOCK = threading.RLock()


def get_default_ipo_gate_context_provider(
    root: str | Path = DEFAULT_ROOT,
) -> IPOGateContextProvider:
    from sys_utils import safe_resolve_path
    resolved = str(safe_resolve_path(root))
    with _PROVIDERS_LOCK:
        provider = _PROVIDERS.get(resolved)
        if provider is None:
            provider = IPOGateContextProvider(resolved)
            _PROVIDERS[resolved] = provider
        return provider
