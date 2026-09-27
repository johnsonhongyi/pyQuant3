"""Nonblocking in-memory bridge from validated IPO observations to Gate 0."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ats.strategy.ipo_data_contracts import IPODecisionConfigSnapshot
from ats.strategy.ipo_source_orchestrator import SOURCE_DB_RELATIVE_PATH


DEFAULT_ROOT = Path(__file__).resolve().parents[2]


class IPOGateContextProvider:
    """Serve a validated, immutable data snapshot without I/O on the Gate path."""

    def __init__(self, root: str | Path = DEFAULT_ROOT) -> None:
        self._root = Path(root).resolve()
        self._lock = threading.RLock()
        self._config_fields: Dict[str, Any] = {}
        self._observations_by_ticker: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._last_refresh_at = ""
        self._last_refresh_ok = False
        self._last_refresh_error = "尚未刷新"
        self._refresh_stop = threading.Event()
        self._refresh_thread: Optional[threading.Thread] = None
        self._store_file_present = False
        self._stored_observation_count = 0
        self._stored_observed_count = 0

    def invalidate(self) -> None:
        with self._lock:
            self._config_fields = {}
            self._observations_by_ticker = {}
            self._stored_observation_count = 0
            self._stored_observed_count = 0

    def refresh(self, config: Optional[IPODecisionConfigSnapshot] = None) -> bool:
        """Load config-bound observations outside the order decision path."""
        try:
            if config is None:
                config = IPODecisionConfigSnapshot.from_yaml(
                    str(self._root / "config" / "ipo_sentiment.yaml")
                )
            config_fields = config.gate_context_fields()
            observations = self._read_observations(config)
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
        with self._lock:
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return True
            self._refresh_stop.clear()

            def refresh_loop() -> None:
                while not self._refresh_stop.is_set():
                    self.refresh()
                    if self._refresh_stop.wait(float(interval_seconds)):
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
                "typed_gate_contexts_ready": False,
                "runtime_authorized": False,
                "transport": "SQLite只读快照",
            }

    def _publish_status(self) -> None:
        path = self._root / "data" / "ipo_learning" / "gate_context_provider.latest.json"
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(self.status_snapshot(), ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError:
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
            global_rows = connection.execute(
                "SELECT ticker, field_id, status, value_json, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc, configuration_hash, "
                "data_contract_hash FROM field_observations WHERE ticker='000000'"
            ).fetchall()
            ticker_rows = connection.execute(
                "SELECT ticker, field_id, status, value_json, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc, configuration_hash, "
                "data_contract_hash FROM field_observations WHERE ticker<>'000000' "
                "ORDER BY updated_at_utc DESC LIMIT 10000"
            ).fetchall()

        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in global_rows + ticker_rows:
            ticker, field_id = str(row[0]), str(row[1])
            if field_id not in config.data_contract.required_fields:
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
            }
            result.setdefault(ticker, {})[field_id] = observation
        return result

    def __call__(self, directive: Any) -> Mapping[str, Any]:
        code = str(getattr(directive, "code", "") or "").strip().zfill(6)
        with self._lock:
            config_fields = dict(self._config_fields)
            observations_by_ticker = self._observations_by_ticker
            observations = dict(observations_by_ticker.get("000000", {}))
            observations.update(observations_by_ticker.get(code, {}))

        decision_config = config_fields.get("decision_config", {})
        freshness = decision_config.get("vwap_freshness", {}) if isinstance(decision_config, Mapping) else {}
        max_vwap_stale = freshness.get("max_stale_seconds", 0) if isinstance(freshness, Mapping) else 0
        issue_observation = observations.get("issue_price", {})
        issue_price = issue_observation.get("value") if issue_observation.get("status") == "OBSERVED" else None
        context = dict(config_fields)
        context.update({
            "lrrm": None,
            "ipo_regime": None,
            "t1_carry": None,
            "listing_anchors": None,
            "vwap": None,
            "intraday_low": 0.0,
            "listing_age_sessions": 0,
            "market_as_of_time": datetime.now(timezone.utc),
            "max_vwap_stale_seconds": max_vwap_stale,
            "risk_context": None,
            "issue_price": issue_price,
            "data_observations": observations,
            "gate_context_sync": self.status_snapshot(),
        })
        return context


_PROVIDERS: Dict[str, IPOGateContextProvider] = {}
_PROVIDERS_LOCK = threading.RLock()


def get_default_ipo_gate_context_provider(
    root: str | Path = DEFAULT_ROOT,
) -> IPOGateContextProvider:
    resolved = str(Path(root).resolve())
    with _PROVIDERS_LOCK:
        provider = _PROVIDERS.get(resolved)
        if provider is None:
            provider = IPOGateContextProvider(resolved)
            _PROVIDERS[resolved] = provider
        return provider
