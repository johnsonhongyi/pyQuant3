# -*- coding: utf-8 -*-
"""Desktop synchronization for shared market context and source-aware favorites."""

import ipaddress
import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import sqlite3
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from linkage_storage import (runtime_database, database_access,
                             configure as configure_linkage_database, trim as trim_linkage_database)
from sys_utils import get_app_root
from system_linkage_gateway import _resolve_key_file

logger = logging.getLogger("system_linkage_context")
_MAX_CONTEXT_BYTES = 8 * 1024 * 1024
_MAX_EVIDENCE_BYTES = 512 * 1024
_PUBLISHABLE_SOURCE_IDS = {"tk.auction", "tk.anomaly", "ats.leader", "ats.ipo", "instock.candidates"}
_TK_ANOMALY_EVENT_TYPES = {"pattern", "risk", "sector_alert"}


def _normalize_linkage_trade_date(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        value = value.strftime("%Y-%m-%d")
    text = str(value).strip()[:10].replace("/", "-")
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if not text or text.lower() in {"nan", "nat", "none", "<na>"}:
        return ""
    try:
        return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def classify_linkage_quote_status(price, source_date, latest_trade_date, market_active, frame_age_seconds):
    """Classify a quote only when its observed trade date and in-session age are trustworthy."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return "pending_fetch"
    if not math.isfinite(value) or value <= 0:
        return "pending_fetch"

    source_date = _normalize_linkage_trade_date(source_date)
    latest_trade_date = _normalize_linkage_trade_date(latest_trade_date)
    if not source_date or not latest_trade_date:
        return "unknown"
    if source_date != latest_trade_date:
        return "stale"
    if not market_active:
        return "market_closed"
    try:
        age = float(frame_age_seconds)
    except (TypeError, ValueError):
        return "stale"
    return "ready" if 0.0 <= age <= 15.0 else "stale"


def build_ipo_linkage_evidence(records, monitored_count):
    """Build a dated, read-only event snapshot from ATS IPO detector observations."""
    from zoneinfo import ZoneInfo

    observations = []
    observed_signal_ids = set()
    for record in records if isinstance(records, (list, tuple)) else ():
        if not isinstance(record, dict):
            continue
        symbol = _normalize_symbol(record.get("symbol", ""))
        signal_type = str(record.get("signal_type", "") or "").strip().upper()
        source_bar_as_of = str(record.get("source_bar_as_of", "") or "").strip()
        if not symbol or not source_bar_as_of or signal_type in ("", "WATCH", "UNKNOWN"):
            continue
        try:
            observed_at = datetime.fromisoformat(source_bar_as_of.replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        except (TypeError, ValueError):
            continue
        score = record.get("horse_race_score")
        try:
            score = float(score)
            if not math.isfinite(score):
                score = None
            elif score.is_integer():
                score = int(score)
        except (TypeError, ValueError):
            score = None
        try:
            rank = max(0, int(record.get("horse_race_rank", 0) or 0))
        except (TypeError, ValueError):
            rank = 0
        item = {
            "symbol": symbol,
            "name": str(record.get("name", "") or "")[:64],
            "signal_type": signal_type[:48],
            "signal_tier": str(record.get("signal_tier", "") or "")[:32],
            "horse_race_score": score,
            "horse_race_rank": rank,
            "is_ipo_first_day": bool(record.get("is_ipo_first_day", False)),
            "source_bar_as_of": observed_at.astimezone(timezone.utc).isoformat(),
        }
        identity = {
            "symbol": symbol, "signal_type": signal_type[:48],
            "is_ipo_first_day": item["is_ipo_first_day"], "source_bar_as_of": item["source_bar_as_of"],
        }
        material = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        item["signal_id"] = hashlib.sha256(material).hexdigest()
        if item["signal_id"] in observed_signal_ids:
            continue
        observed_signal_ids.add(item["signal_id"])
        observations.append((observed_at, item))
    if not observations:
        return None
    latest_at = max(observed_at for observed_at, _item in observations)
    shanghai = ZoneInfo("Asia/Shanghai")
    latest_date = latest_at.astimezone(shanghai).date().isoformat()
    latest_items = [item for observed_at, item in observations
                    if observed_at.astimezone(shanghai).date().isoformat() == latest_date]
    latest_items.sort(key=lambda item: (item["symbol"], item["signal_type"], item["signal_id"]))
    payload = {
        "schema_version": 1,
        "source_id": "ats.ipo",
        "session_phase": "intraday",
        "monitored_count": max(0, int(monitored_count or 0)),
        "signal_count": len(latest_items),
        "signals_complete": len(latest_items) <= 100,
        "signals": latest_items[:100],
        "coverage": {
            "scope": "ats_ipo_signal_observations",
            "observed_count": min(len(latest_items), 100),
            "complete": False,
            "is_sample": True,
            "source": "ats.ipo",
        },
    }
    return latest_date, latest_at.astimezone(timezone.utc).isoformat(), payload


def build_ats_leader_evidence(report, now=None):
    """Build a dated, sampled read-only snapshot of ATS role candidates."""
    from zoneinfo import ZoneInfo

    if not isinstance(report, dict):
        return None
    try:
        source_timestamp = float(report.get("timestamp"))
        if not math.isfinite(source_timestamp) or source_timestamp <= 0:
            return None
        observed_at = datetime.fromtimestamp(source_timestamp, timezone.utc)
        if now is None:
            now_at = datetime.now(timezone.utc)
        elif isinstance(now, datetime):
            now_at = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            now_at = now_at.astimezone(timezone.utc)
        else:
            now_at = datetime.fromtimestamp(float(now), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None

    age_seconds = now_at.timestamp() - source_timestamp
    source_freshness = "fresh" if -30 <= age_seconds <= 90 else "stale"
    # A 30-second source-time bucket keeps repeated worker refreshes idempotent.
    as_of = datetime.fromtimestamp(int(source_timestamp // 30) * 30, timezone.utc).isoformat()
    trade_date = observed_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()

    records = report.get("dragon_records_all")
    if not isinstance(records, (list, tuple)):
        records = report.get("dragon_records", ())
    candidates = {}
    for record in records if isinstance(records, (list, tuple)) else ():
        if not isinstance(record, dict) or record.get("is_index"):
            continue
        if str(record.get("sector", "") or "").strip() == "综合指数/ETF":
            continue
        symbol = _normalize_symbol(record.get("code") or record.get("symbol", ""))
        if not symbol:
            continue
        code = symbol[:6]
        if symbol.endswith(".SH") and not code.startswith(("600", "601", "603", "605", "688", "689")):
            continue
        if symbol.endswith(".SZ") and not code.startswith(("000", "001", "002", "003", "300", "301")):
            continue
        role = str(record.get("role", "") or "").strip()
        if not role:
            continue
        try:
            priority = int(record.get("priority", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            priority = 0
        item = {
            "symbol": symbol,
            "name": str(record.get("name", "") or "")[:64],
            "role": role[:64],
            "sector": str(record.get("sector", "") or "")[:64],
            "priority": priority,
            "classification": "ats_role_candidate",
        }
        previous = candidates.get(symbol)
        if previous is None or item["priority"] > previous["priority"]:
            candidates[symbol] = item

    roles = sorted(candidates.values(), key=lambda item: (-item["priority"], item["symbol"]))[:100]
    payload = {
        "schema_version": 1,
        "source_id": "ats.leader",
        "source_freshness": source_freshness,
        "candidate_count": len(candidates),
        "candidate_codes": [item["symbol"] for item in roles],
        "roles": roles,
        "coverage": {
            "scope": "ats_capital_dragon_role_candidates",
            "observed_count": len(roles),
            "complete": False,
            "is_sample": True,
            "source": "ats.leader",
        },
    }
    return trade_date, as_of, payload


def publish_ats_leader_evidence(report, client, now=None):
    if client is None:
        return False
    evidence = build_ats_leader_evidence(report, now=now)
    if evidence is None:
        return False
    trade_date, as_of, payload = evidence
    return client.publish_source_snapshot("ats.leader", trade_date, as_of, payload)


def build_instock_candidate_evidence(frame, trade_date, now=None, limit=100):
    """Build a dated sample of configured StockSelector results, never a market-wide claim."""
    from zoneinfo import ZoneInfo

    try:
        trade_date = str(trade_date or "").strip()
        if datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y-%m-%d") != trade_date:
            return None
        if now is None:
            now_at = datetime.now(timezone.utc)
        elif isinstance(now, datetime):
            now_at = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
            now_at = now_at.astimezone(timezone.utc)
        else:
            now_at = datetime.fromtimestamp(float(now), timezone.utc)
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError, OverflowError, OSError):
        return None

    if hasattr(frame, "iterrows"):
        records = frame.iterrows()
    elif isinstance(frame, (list, tuple)):
        records = enumerate(frame)
    else:
        return None

    candidates = []
    seen = set()
    for index, record in records:
        if not isinstance(record, dict) and not hasattr(record, "get"):
            continue
        raw_code = record.get("code")
        if raw_code is None or str(raw_code).strip().lower() in ("", "nan", "none", "<na>"):
            raw_code = index
        raw_code = str(raw_code).strip()
        if raw_code.endswith(".0") and raw_code[:-2].isdigit():
            raw_code = raw_code[:-2]
        symbol = _normalize_symbol(raw_code)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        name_value = record.get("name")
        name = "" if name_value is None else str(name_value).strip()
        if name.lower() in ("nan", "none", "<na>"):
            name = ""
        item = {"symbol": symbol, "name": name[:64],
                "classification": "configured_selector_candidate"}
        for field, output, cap in (("grade", "grade", 8), ("reason", "reason", 160),
                                   ("category", "themes", 160), ("stage", "stage", 48)):
            value = record.get(field)
            if value is not None:
                text_value = str(value).strip()
                if text_value and text_value.lower() not in ("nan", "none", "<na>"):
                    item[output] = text_value[:cap]
        try:
            score = float(record.get("score"))
            if math.isfinite(score):
                item["score"] = int(score) if score.is_integer() else score
        except (TypeError, ValueError, OverflowError):
            pass
        candidates.append(item)

    sample = candidates[:limit]
    complete = len(sample) == len(candidates)
    local_date = now_at.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    payload = {
        "schema_version": 1,
        "source_id": "instock.candidates",
        "source_freshness": "fresh" if local_date == trade_date else "stale",
        "session_phase": "close",
        "candidate_count": len(candidates),
        "candidate_codes": [item["symbol"] for item in sample],
        "candidate_codes_complete": complete,
        "candidates": sample,
        "coverage": {
            "scope": "configured_selector_output",
            "observed_count": len(sample),
            "total_count": len(candidates),
            "complete": complete,
            "is_sample": not complete,
            "source": "instock.stock_selector",
        },
    }
    return trade_date, now_at.isoformat(), payload


def publish_instock_candidate_evidence(frame, client, trade_date, now=None, limit=100):
    if client is None:
        return False
    evidence = build_instock_candidate_evidence(frame, trade_date, now=now, limit=limit)
    if evidence is None:
        return False
    evidence_date, as_of, payload = evidence
    return client.publish_source_snapshot("instock.candidates", evidence_date, as_of, payload)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SystemLinkageContextClient:
    """Poll and cache read-only context without touching strategy or execution state."""

    def __init__(self, config, callback=None, database_path=None, poll_interval=60):
        self.config = config
        self.callback = callback
        self.database_path = database_path or runtime_database(os.path.join(get_app_root(), "system_linkage.sqlite3"))
        self.poll_interval = max(60, min(int(poll_interval), 300))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._snapshot = None
        self._snapshot_digest = None
        self._status = {"state": "stopped", "error": ""}
        self._events = []
        self._base_url = ""
        self._token = ""
        self._key = b""
        self._workspace_id = ""
        self._node_id = ""
        self._attention_enabled = False
        self._attention_status = "disabled"
        self._publisher_status = "disabled"
        self._source_event_queue = deque()
        self._source_event_queue_lock = threading.Lock()
        self._source_queue_flush_lock = threading.Lock()
        self._outbox_flush_lock = threading.Lock()
        self._favorite_manager = None
        self._favorite_listener = None
        self._attention_wakeup = threading.Event()
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _connect(self, read_only=False):
        connection = sqlite3.connect(self.database_path, timeout=4.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=4000")
        if read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            configure_linkage_database(connection)
        return connection

    @contextmanager
    def _connection(self, read_only=False):
        operation = 'context.' + sys._getframe(2).f_code.co_name
        with database_access(self.database_path, operation, read_only=read_only):
            connection = self._connect(read_only=read_only)
            try:
                yield connection
                if not read_only:
                    connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def _init_store(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.database_path)), exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("""CREATE TABLE IF NOT EXISTS linkage_context_snapshots (
                snapshot_id TEXT PRIMARY KEY, trade_date TEXT NOT NULL DEFAULT '',
                received_at TEXT NOT NULL, stored_at TEXT NOT NULL, payload BLOB NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_linkage_context_local_time ON linkage_context_snapshots(stored_at DESC)")
            connection.execute("""CREATE TABLE IF NOT EXISTS linkage_context_events (
                event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, occurred_at TEXT NOT NULL,
                payload BLOB NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS linkage_context_cursor (
                cursor_key TEXT PRIMARY KEY, cursor_value TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS linkage_context_outbox (
                evidence_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, trade_date TEXT NOT NULL,
                as_of TEXT NOT NULL, payload BLOB NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL)""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_linkage_context_outbox_due ON linkage_context_outbox(next_attempt,created_at)")
            connection.execute("""CREATE TABLE IF NOT EXISTS linkage_context_dedup (
                kind TEXT NOT NULL, digest TEXT NOT NULL, repeat_count INTEGER NOT NULL DEFAULT 1,
                last_seen TEXT NOT NULL, PRIMARY KEY(kind,digest))""")
        with self._connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT digest FROM linkage_context_dedup WHERE kind='snapshot'"
            ).fetchone()
        self._snapshot_digest = row['digest'] if row else None
        with self._connection(read_only=True) as connection:
            row = connection.execute("SELECT payload FROM linkage_context_snapshots ORDER BY stored_at DESC LIMIT 1").fetchone()
        if row:
            try:
                self._snapshot = json.loads(bytes(row["payload"]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                logger.warning("Cached system-linkage context is invalid and will be replaced")
        with self._connection(read_only=True) as connection:
            rows = connection.execute("SELECT payload FROM linkage_context_events ORDER BY occurred_at DESC,event_id DESC LIMIT 100").fetchall()
        events = []
        for row in rows:
            try:
                event = json.loads(bytes(row["payload"]).decode("utf-8"))
                if isinstance(event, dict):
                    events.append(event)
            except (ValueError, UnicodeDecodeError):
                logger.debug("Ignoring invalid cached linkage event")
        self._events = events

    def _resolve_config(self):
        if not bool(getattr(self.config, "linkage_enabled", False)):
            raise ValueError("linkage_disabled")
        raw_url = str(getattr(self.config, "stock_strategy_base_url", "") or "").strip()
        parsed = urlsplit(raw_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
            raise ValueError("invalid_stock_strategy_base_url")
        _require_private_host(parsed.hostname)
        base = urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
        key_path = str(getattr(self.config, "ipc_key_file", "") or "").strip()
        key = b""
        if key_path:
            with open(_resolve_key_file(self.config, key_path), "rb") as file_obj:
                raw_key = file_obj.read(4096).strip()
            try:
                key_text = raw_key.decode("ascii")
                key = bytes.fromhex(key_text) if len(key_text) == 64 else raw_key
            except (UnicodeDecodeError, ValueError):
                key = raw_key
            if len(key) < 32:
                raise ValueError("ipc_key_file_must_contain_at_least_32_bytes")
        token = str(os.environ.get("A_STOCK_TOKEN", "") or "").strip()
        token_path = str(getattr(self.config, "stock_strategy_token_file", "") or "").strip()
        if not token and not key and token_path:
            with open(os.path.expandvars(os.path.expanduser(token_path)), "r", encoding="utf-8") as file_obj:
                token = file_obj.read(4096).strip()
        if not token and not key:
            raise ValueError("linkage_peer_auth_not_configured")
        self._base_url = base
        self._token = token
        self._key = key
        self._workspace_id = str(getattr(self.config, "ipc_workspace_id", "") or "").strip()
        self._node_id = str(getattr(self.config, "ipc_node_id", "") or "").strip()
        self._attention_enabled = bool(
            self._workspace_id and self._node_id
            and len(self._workspace_id) <= 96 and len(self._node_id) <= 96
            and all((char.isascii() and char.isalnum()) or char in "_.-"
                    for char in self._workspace_id + self._node_id)
        )
        self._attention_status = "pending" if self._attention_enabled else "identity_not_configured"
        self._publisher_status = "pending" if self._attention_enabled else "identity_not_configured"

    def prepare_source_publisher(self):
        """Initialize durable source outbox without starting context or attention workers."""
        self._resolve_config()
        self._init_store()
        return self._attention_enabled

    def flush_pending_source_evidence(self):
        """Persist queued observations and attempt one bounded outbox delivery pass."""
        self._resolve_config()
        self._init_store()
        self._drain_source_events()
        self._flush_source_outbox(limit=1)
        with self._connection(read_only=True) as connection:
            return connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0] == 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return not self._stop.is_set()
        try:
            self._resolve_config()
            self._init_store()
        except Exception as error:
            with self._lock:
                self._status = {"state": "unavailable", "error": str(error)}
            logger.info("System-linkage context consumer is unavailable: %s", error)
            return False
        if self._attention_enabled:
            try:
                from global_favorites import GlobalFavoriteManager
                self._favorite_manager = GlobalFavoriteManager()
                self._favorite_listener = self._favorite_manager.add_change_listener(self._on_favorites_changed)
            except Exception as error:
                self._attention_status = "unavailable: " + str(error)
                logger.warning("System-linkage attention sync is unavailable: %s", error)
        self._stop.clear()
        self._attention_wakeup.set()
        self._thread = threading.Thread(target=self._run, name="LinkageContextPoller", daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        self._attention_wakeup.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        if thread is None or not thread.is_alive():
            self._thread = None
        self._drain_source_events()
        if self._favorite_manager is not None and self._favorite_listener is not None:
            try:
                self._favorite_manager.remove_change_listener(self._favorite_listener)
            except Exception:
                logger.debug("Could not unregister favorites listener", exc_info=True)
        self._favorite_listener = None

    def latest(self):
        with self._lock:
            snapshot = dict(self._snapshot) if isinstance(self._snapshot, dict) else None
            status = dict(self._status)
        return snapshot, status

    def summary_for_symbol(self, symbol):
        snapshot, status = self.latest()
        if not snapshot:
            return {"state": status.get("state", "unavailable"), "error": status.get("error", "")}
        normalized = _normalize_symbol(symbol)
        linked_themes = [theme for theme in snapshot.get("themes", [])
                         if any(member.get("symbol") == normalized for member in theme.get("members", []))]
        themes = [theme.get("name", "") for theme in linked_themes]
        theme_heat = [{key: theme[key] for key in (
            "theme_id", "name", "change_percent", "trend_score", "daily_strength_score",
            "five_day_strength_score", "active_days", "trend_stage", "trade_date",
        ) if key in theme} for theme in linked_themes]
        stock = next((item for item in snapshot.get("heat", {}).get("stocks", [])
                      if item.get("symbol") == normalized), {})
        leader = None
        for evidence in snapshot.get("evidence", []):
            if evidence.get("source_id") != "ats.leader":
                continue
            payload = evidence.get("payload", {})
            if not isinstance(payload, dict):
                continue
            candidate = next((item for item in payload.get("roles", [])
                              if isinstance(item, dict) and _normalize_symbol(
                                  item.get("symbol") or item.get("code", "")) == normalized), None)
            evidence_trade_date = evidence.get("trade_date", "")
            evidence_freshness = evidence.get("freshness", "unknown")
            if payload.get("source_freshness") == "stale" or evidence_trade_date != snapshot.get("trade_date"):
                evidence_freshness = "stale"
            leader = {
                "role": candidate.get("role", "") if candidate else "",
                "sector": candidate.get("sector", "") if candidate else "",
                "classification": "ATS 候选角色" if candidate else "ATS 当前样本未列入",
                "candidate": candidate is not None,
                "trade_date": evidence_trade_date,
                "freshness": evidence_freshness,
                "candidate_count": payload.get("candidate_count", 0),
                "coverage": payload.get("coverage", {}),
            }
            break
        auction = None
        for evidence in snapshot.get("evidence", []):
            if evidence.get("source_id") != "tk.auction":
                continue
            payload = evidence.get("payload", {})
            if not isinstance(payload, dict):
                continue
            candidate_codes = {_normalize_symbol(value) for value in payload.get("candidate_codes", [])
                               if isinstance(value, str)}
            stock_evidence = next((item for item in payload.get("stocks", [])
                                   if isinstance(item, dict) and _normalize_symbol(
                                       item.get("symbol") or item.get("code", "")) == normalized), {})
            if normalized in candidate_codes or stock_evidence:
                evidence_trade_date = evidence.get("trade_date", "")
                auction = {
                    "state": payload.get("state", "unknown"),
                    "trade_date": evidence_trade_date,
                    "as_of": evidence.get("as_of", ""),
                    "freshness": _auction_evidence_freshness(
                        evidence_trade_date, evidence.get("as_of", ""), snapshot.get("trade_date", ""),
                        source_freshness=evidence.get("freshness", "unknown"),
                        payload_freshness=payload.get("source_freshness", ""),
                    ),
                    "candidate": normalized in candidate_codes,
                    "stock": stock_evidence,
                }
            break
        instock_candidate = None
        for evidence in snapshot.get("evidence", []):
            if evidence.get("source_id") != "instock.candidates":
                continue
            payload = evidence.get("payload", {})
            if not isinstance(payload, dict):
                continue
            candidates = payload.get("candidates", [])
            if not isinstance(candidates, (list, tuple)):
                candidates = []
            candidate = next((item for item in candidates
                              if isinstance(item, dict) and _normalize_symbol(
                                  item.get("symbol") or item.get("code", "")) == normalized), None)
            candidate_codes = payload.get("candidate_codes", [])
            if not isinstance(candidate_codes, (list, tuple)):
                candidate_codes = []
            if candidate is None and normalized in {
                    _normalize_symbol(value) for value in candidate_codes if isinstance(value, str)}:
                candidate = {"symbol": normalized}
            evidence_trade_date = evidence.get("trade_date", "")
            evidence_freshness = evidence.get("freshness", "unknown")
            if payload.get("source_freshness") == "stale" or evidence_trade_date != snapshot.get("trade_date"):
                evidence_freshness = "stale"
            coverage = payload.get("coverage", {})
            if not isinstance(coverage, dict):
                coverage = {}
            complete = payload.get("candidate_codes_complete")
            if not isinstance(complete, bool):
                complete = coverage.get("complete") is True
            if candidate:
                classification = ("历史候选" if evidence_freshness == "stale" else
                                  "当前候选" if evidence_freshness == "fresh" else "候选状态待确认")
            elif evidence_freshness == "stale":
                classification = "历史样本未列入" if not complete else "历史 selector 未列入"
            elif evidence_freshness == "fresh":
                classification = "当前样本未列入" if not complete else "当前 selector 未列入"
            else:
                classification = "候选状态待确认"
            instock_candidate = {
                "candidate": candidate is not None,
                "classification": classification,
                "trade_date": evidence_trade_date,
                "freshness": evidence_freshness,
                "candidate_count": payload.get("candidate_count", 0),
                "grade": candidate.get("grade", "") if candidate else "",
                "score": candidate.get("score") if candidate else None,
                "coverage": coverage,
            }
            break
        ladder = None
        for level in snapshot.get("ladder", {}).get("current", {}).get("levels", []):
            found = next((item for item in level.get("stocks", []) if item.get("symbol") == normalized), None)
            if found:
                ladder = {"label": level.get("label", ""), "streak": found.get("streak")}
                break
        freshness = snapshot.get("freshness", "unknown")
        expires = _parse_time(snapshot.get("expires_at"))
        if expires is None or expires.timestamp() <= time.time():
            freshness = "stale"
        return {
            "state": freshness,
            "trade_date": snapshot.get("trade_date", ""),
            "themes": list(dict.fromkeys(name for name in themes if name))[:4],
            "theme_heat": theme_heat[:4],
            "ranks": dict(stock.get("ranks", {})),
            "ladder": ladder,
            "leader": leader,
            "auction": auction,
            "instock_candidate": instock_candidate,
            "coverage": snapshot.get("coverage", []),
            "errors": snapshot.get("errors", []),
            "event_summary": self._event_summary(normalized, snapshot),
        }

    def _event_summary(self, symbol, snapshot):
        theme_ids = {theme.get("theme_id") for theme in snapshot.get("themes", [])
                     if any(member.get("symbol") == symbol for member in theme.get("members", []))}
        with self._lock:
            events = list(self._events)
        for event in events:
            payload = event.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except ValueError:
                    payload = {}
            if not isinstance(payload, dict):
                continue
            auction_candidates = {_normalize_symbol(value) for value in payload.get("candidate_codes", [])
                                  if isinstance(value, str)}
            if (payload.get("symbol") != symbol and payload.get("theme_id") not in theme_ids
                    and symbol not in auction_candidates):
                continue
            old_value = payload.get("from")
            new_value = payload.get("to")
            if "from_rank" in payload or "to_rank" in payload:
                old_value = payload.get("from_rank")
                new_value = payload.get("to_rank")
            transition = ""
            if old_value is not None or new_value is not None:
                transition = f" {old_value if old_value is not None else '无'}→{new_value if new_value is not None else '无'}"
            if payload.get("signal_type"):
                transition += " " + str(payload["signal_type"])
            return str(event.get("event_type", "事件")) + transition
        return ""

    def _run(self):
        while not self._stop.is_set():
            # A self-wakeup on revision conflict must not become a busy retry loop.
            delay = getattr(self, '_next_attention_poll', 0.0) - time.monotonic()
            if delay > 0 and self._stop.wait(delay):
                break
            self._next_attention_poll = time.monotonic() + 5.0
            try:
                self._drain_source_events()
                try:
                    # One slow upload must not be multiplied by ten before
                    # attention reconciliation gets its next turn.
                    self._flush_source_outbox(limit=1)
                except Exception as error:
                    self._publisher_status = "stale: " + str(error)
                    logger.debug("System-linkage evidence publish failed: %s", error)
                if self._attention_enabled and self._favorite_manager is not None:
                    try:
                        self._sync_attention()
                    except Exception as error:
                        self._attention_status = "stale: " + str(error)
                        if str(error) in ("attention_revision_conflict", "favorites_revision_conflict"):
                            self._attention_wakeup.set()
                        logger.debug("System-linkage attention sync failed: %s", error)
                with self._lock:
                    sync_status = {"attention": self._attention_status, "publish": self._publisher_status}
                    sync_changed = any(self._status.get(key) != value for key, value in sync_status.items())
                    self._status.update(sync_status)
                if sync_changed:
                    self._notify()
                next_context_poll = getattr(self, '_next_context_poll', 0.0)
                if time.monotonic() < next_context_poll:
                    self._wait_for_next_poll()
                    self._attention_wakeup.clear()
                    continue
                self._next_context_poll = time.monotonic() + self.poll_interval
                snapshot = self._fetch_json("/api/v1/linkage/context")
                if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or not snapshot.get("snapshot_id"):
                    raise ValueError("invalid_context_snapshot")
                self._store_snapshot(snapshot)
                self._sync_events()
                with self._lock:
                    self._snapshot = snapshot
                    self._status = {"state": "online", "error": "", "snapshot_id": snapshot["snapshot_id"],
                                    "attention": self._attention_status, "publish": self._publisher_status}
                self._notify()
            except Exception as error:
                with self._lock:
                    self._status = {"state": "stale" if self._snapshot else "unavailable", "error": str(error),
                                    "attention": self._attention_status, "publish": self._publisher_status}
                logger.debug("System-linkage context poll failed: %s", error)
                self._notify()
            self._wait_for_next_poll()
            self._attention_wakeup.clear()

    def _wait_for_next_poll(self):
        now = time.monotonic()
        deadline = getattr(self, '_next_context_poll', now + self.poll_interval)
        if self._attention_enabled:
            deadline = min(deadline, getattr(self, '_next_attention_poll', now + 5.0))
        self._attention_wakeup.wait(max(0.0, min(self.poll_interval, deadline - now)))

    def _on_favorites_changed(self, event):
        if not isinstance(event, dict) or event.get("origin") == "remote_sync":
            return
        self._attention_wakeup.set()

    def _fetch_json(self, path):
        status, result = self._request_json("GET", path)
        if status != 200:
            raise ValueError("linkage_context_http_" + str(status))
        return result

    def _request_json(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        if self._key:
            timestamp = str(int(time.time()))
            nonce = secrets.token_hex(24)
            canonical = "\n".join((method, path, hashlib.sha256(body or b"").hexdigest(),
                                   timestamp, nonce, self._node_id, self._workspace_id)).encode("utf-8")
            signature = hmac.new(self._key, canonical, hashlib.sha256).hexdigest()
            headers.update({
                "X-Linkage-Node-ID": self._node_id,
                "X-Linkage-Workspace-ID": self._workspace_id,
                "X-Linkage-Timestamp": timestamp,
                "X-Linkage-Nonce": nonce,
                "X-Linkage-Signature": signature,
            })
        elif self._token:
            headers["Authorization"] = "Bearer " + self._token
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self._base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=8.0) as response:
                status = response.status
                data = response.read(_MAX_CONTEXT_BYTES + 1)
        except HTTPError as error:
            status = error.code
            data = error.read(_MAX_CONTEXT_BYTES + 1)
            error.close()
        if len(data) > _MAX_CONTEXT_BYTES:
            raise ValueError("linkage_context_too_large")
        try:
            result = json.loads(data.decode("utf-8")) if data else {}
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("invalid_linkage_response") from error
        return status, result

    def _store_snapshot(self, snapshot):
        payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > _MAX_CONTEXT_BYTES:
            raise ValueError("linkage_context_too_large")
        significant = {key: value for key, value in snapshot.items()
                       if key not in ('snapshot_id', 'received_at', 'stored_at', 'as_of', 'generated_at')}
        digest = hashlib.sha256(json.dumps(significant, ensure_ascii=False, sort_keys=True,
                                           separators=(',', ':')).encode('utf-8')).hexdigest()
        if self._snapshot_digest == digest:
            return
        # The remote context is polled periodically, but most polls return the
        # same semantic snapshot. The in-memory digest avoids opening SQLite
        # and taking the shared writer gate for unchanged cache contents.
        with self._connection() as connection:
            now = datetime.now(timezone.utc).isoformat()
            previous = connection.execute("SELECT digest FROM linkage_context_dedup WHERE kind='snapshot'").fetchone()
            if not previous or previous['digest'] != digest:
                connection.execute("DELETE FROM linkage_context_dedup WHERE kind='snapshot'")
                connection.execute("INSERT INTO linkage_context_dedup(kind,digest,last_seen) VALUES('snapshot',?,?)", (digest, now))
                connection.execute("DELETE FROM linkage_context_snapshots")
                connection.execute("INSERT INTO linkage_context_snapshots(snapshot_id,trade_date,received_at,stored_at,payload) VALUES(?,?,?,?,?)",
                                   (snapshot["snapshot_id"], snapshot.get("trade_date", ""), snapshot.get("received_at", ""), now, payload))
            # Snapshot history was already reduced to one row above. Full trim
            # also scans/parses the event table; keep that work out of this
            # frequently shared snapshot transaction.
        self._snapshot_digest = digest

    def _sync_events(self):
        with self._connection(read_only=True) as connection:
            row = connection.execute("SELECT cursor_value FROM linkage_context_cursor WHERE cursor_key='events'").fetchone()
        after = row["cursor_value"] if row else ""
        query = "?limit=200" + ("&after=" + after if after else "")
        result = self._fetch_json("/api/v1/linkage/events" + query)
        events = result.get("events", []) if isinstance(result, dict) else []
        if not isinstance(events, list):
            raise ValueError("invalid_linkage_events")
        if not events:
            return
        with self._connection() as connection:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            for event in events[:200]:
                if (not isinstance(event, dict) or not event.get("event_id")
                        or not event.get('event_type') or not event.get('occurred_at')):
                    continue
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                if len(payload) > 64 * 1024:
                    logger.warning('Oversized linkage event skipped: %s', event.get('event_type'))
                    continue
                significant = {key: value for key, value in event.items()
                               if key not in ('event_id', 'occurred_at', 'received_at', 'as_of')}
                digest = hashlib.sha256(json.dumps(significant, ensure_ascii=False, sort_keys=True,
                                                   separators=(',', ':')).encode('utf-8')).hexdigest()
                dedup_id = 'content:' + digest
                previous = connection.execute("SELECT payload FROM linkage_context_events WHERE event_id=?", (dedup_id,)).fetchone()
                if previous:
                    retained = json.loads(bytes(previous['payload']).decode('utf-8'))
                    if retained.get('_last_event_id', retained.get('event_id')) == event['event_id']:
                        continue
                    retained['_last_event_id'] = event['event_id']
                    retained['repeat_count'] = int(retained.get('repeat_count', 1)) + 1
                    retained['last_seen'] = event.get('occurred_at', '')
                    payload = json.dumps(retained, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                    connection.execute("UPDATE linkage_context_events SET payload=?,occurred_at=? WHERE event_id=?",
                                       (payload, event.get('occurred_at', ''), dedup_id))
                else:
                    connection.execute("INSERT INTO linkage_context_events(event_id,event_type,occurred_at,payload) VALUES(?,?,?,?)",
                                       (dedup_id, event.get("event_type", ""), event.get("occurred_at", ""), payload))
            cursor = str(events[min(len(events), 200) - 1].get("event_id", ""))
            if cursor:
                connection.execute("INSERT INTO linkage_context_cursor(cursor_key,cursor_value) VALUES('events',?) ON CONFLICT(cursor_key) DO UPDATE SET cursor_value=excluded.cursor_value",
                                   (cursor,))
            connection.execute("DELETE FROM linkage_context_events WHERE occurred_at < ?", (cutoff,))
            trim_linkage_database(connection)
            rows = connection.execute("SELECT payload FROM linkage_context_events ORDER BY occurred_at DESC,event_id DESC LIMIT 100").fetchall()
        events_cache = []
        for row in rows:
            try:
                event = json.loads(bytes(row["payload"]).decode("utf-8"))
                if isinstance(event, dict):
                    events_cache.append(event)
            except (ValueError, UnicodeDecodeError):
                continue
        with self._lock:
            self._events = events_cache

    def publish_source_snapshot(self, source_id, trade_date, as_of, payload):
        source_id = str(source_id or "").strip()
        trade_date = str(trade_date or "").strip()
        if source_id not in _PUBLISHABLE_SOURCE_IDS or not self._attention_enabled:
            raise ValueError("linkage_source_publisher_not_configured")
        try:
            if datetime.strptime(trade_date, "%Y-%m-%d").strftime("%Y-%m-%d") != trade_date:
                raise ValueError("invalid_trade_date")
            parsed_as_of = datetime.fromisoformat(str(as_of or "").replace("Z", "+00:00"))
            if parsed_as_of.tzinfo is None:
                raise ValueError("as_of_timezone_required")
        except (TypeError, ValueError) as error:
            raise ValueError("invalid_context_evidence_time") from error
        if (not isinstance(payload, dict) or payload.get("schema_version") != 1
                or payload.get("source_id") != source_id):
            raise ValueError("invalid_context_evidence_payload")
        as_of = parsed_as_of.astimezone(timezone.utc).isoformat()
        envelope = {
            "workspace_id": self._workspace_id, "node_id": self._node_id,
            "source_id": source_id, "trade_date": trade_date, "as_of": as_of,
            "payload": payload,
        }
        payload_bytes = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload_bytes) > _MAX_EVIDENCE_BYTES:
            raise ValueError("context_evidence_too_large")
        evidence_id = hashlib.sha256(payload_bytes).hexdigest()
        envelope["snapshot_id"] = evidence_id
        payload_bytes = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self._connection() as connection:
            exists = connection.execute("SELECT 1 FROM linkage_context_outbox WHERE evidence_id=?", (evidence_id,)).fetchone()
            count = connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0]
            if not exists and count >= 2000:
                raise ValueError("linkage_context_outbox_full")
            connection.execute("INSERT OR IGNORE INTO linkage_context_outbox(evidence_id,source_id,trade_date,as_of,payload,created_at) VALUES(?,?,?,?,?,?)",
                               (evidence_id, source_id, trade_date, as_of, payload_bytes, datetime.now(timezone.utc).isoformat()))
        with self._lock:
            self._publisher_status = "queued"
        self._attention_wakeup.set()
        return evidence_id

    def queue_source_event(self, source_id, trade_date, as_of, event):
        """Accept a small observation without disk or network I/O on the signal bus."""
        if (not isinstance(event, dict) or source_id != "tk.anomaly"
                or event.get("event_type") not in _TK_ANOMALY_EVENT_TYPES or not self._attention_enabled):
            return False
        try:
            if datetime.strptime(str(trade_date), "%Y-%m-%d").strftime("%Y-%m-%d") != str(trade_date):
                raise ValueError("invalid_trade_date")
            parsed_as_of = datetime.fromisoformat(str(as_of or "").replace("Z", "+00:00"))
            if parsed_as_of.tzinfo is None:
                raise ValueError("as_of_timezone_required")
            packed = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(packed) > 4096:
                return False
            event = json.loads(packed.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            with self._lock:
                self._publisher_status = "stale: anomaly_queue_full_or_invalid"
            return False
        with self._source_event_queue_lock:
            if len(self._source_event_queue) >= 256:
                with self._lock:
                    self._publisher_status = "stale: anomaly_queue_full_or_invalid"
                return False
            self._source_event_queue.append((source_id, str(trade_date), str(as_of), event))
        self._attention_wakeup.set()
        return True

    def _drain_source_events(self):
        if not self._attention_enabled or not self._source_queue_flush_lock.acquire(blocking=False):
            return
        try:
            with self._source_event_queue_lock:
                pending = list(self._source_event_queue)
            offset = 0
            while offset < len(pending):
                source_id, trade_date, _as_of, _event = pending[offset]
                end = offset
                while (end < len(pending) and end - offset < 100
                       and pending[end][0] == source_id and pending[end][1] == trade_date):
                    end += 1
                batch = pending[offset:end]
                payload = {"schema_version": 1, "source_id": source_id,
                           "events": [event for _source, _date, _as_of, event in batch]}
                try:
                    self.publish_source_snapshot(source_id, trade_date, batch[-1][2], payload)
                except Exception as error:
                    with self._lock:
                        self._publisher_status = "stale: " + str(error)
                    logger.warning("Could not persist queued TK anomaly evidence: %s", error)
                    return
                with self._source_event_queue_lock:
                    for _ in batch:
                        self._source_event_queue.popleft()
                offset = end
        finally:
            self._source_queue_flush_lock.release()

    def _flush_source_outbox(self, limit=10):
        if not self._attention_enabled or not self._outbox_flush_lock.acquire(blocking=False):
            return
        try:
            limit = max(1, min(int(limit), 10))
            with self._connection(read_only=True) as connection:
                rows = connection.execute("SELECT evidence_id,payload,attempts FROM linkage_context_outbox WHERE next_attempt<=? ORDER BY created_at,evidence_id LIMIT ?",
                                          (time.time(), limit)).fetchall()
            for row in rows:
                try:
                    payload = json.loads(bytes(row["payload"]).decode("utf-8"))
                    status, result = self._request_json("POST", "/api/v1/linkage/context/evidence", payload)
                    if status not in (200, 201) or not isinstance(result, dict) or result.get("status") != "stored":
                        code = result.get("code", "error") if isinstance(result, dict) else "invalid_response"
                        raise ValueError("context_evidence_http_" + str(status) + ":" + str(code))
                    with self._connection() as connection:
                        connection.execute("DELETE FROM linkage_context_outbox WHERE evidence_id=?", (row["evidence_id"],))
                except Exception as error:
                    attempts = int(row["attempts"] or 0) + 1
                    retry_after = time.time() + min(300, 2 ** min(attempts, 8))
                    with self._connection() as connection:
                        connection.execute("UPDATE linkage_context_outbox SET attempts=?,next_attempt=? WHERE evidence_id=?",
                                           (attempts, retry_after, row["evidence_id"]))
                    with self._lock:
                        self._publisher_status = "stale: " + str(error)
                    return
            with self._connection(read_only=True) as connection:
                pending = connection.execute("SELECT COUNT(*) FROM linkage_context_outbox").fetchone()[0]
            with self._lock:
                if pending and not self._publisher_status.startswith("stale:"):
                    self._publisher_status = "queued"
                elif not pending and (self._publisher_status == "queued" or self._publisher_status.startswith("stale:")):
                    self._publisher_status = "synced"
        finally:
            self._outbox_flush_lock.release()

    def _sync_attention(self):
        manager = self._favorite_manager
        state = manager.get_persistent_favorite_attention_state()
        baseline_favorites_revision = int(state.get("favorites_revision", 0) or 0)
        snapshot = self._get_attention_snapshot()
        local_tombstones = state.get("tombstones", {})
        remote_tombstones = {item.get("symbol"): item for item in snapshot.get("tombstones", [])
                             if isinstance(item, dict)}
        remote_sources = {(item.get("symbol"), _normalize_local_attention_source(item.get("source"))): item
                          for item in snapshot.get("sources", []) if isinstance(item, dict)}

        # A workspace-global change observed after this desk's cursor wins over
        # an offline edit for the same symbol; the newer state is projected below.
        conflicts = 0
        pending = []
        for code, tombstone in sorted(local_tombstones.items()):
            symbol = _normalize_symbol(code)
            if not symbol:
                continue
            operation_id = str(tombstone.get("operation_id", ""))
            current = remote_tombstones.get(symbol)
            if current and current.get("intent_id") == operation_id:
                continue
            remote_change_is_newer = bool(
                (current and int(current.get("revision", 0) or 0) > int(state.get("attention_revision", 0) or 0))
                or any(row_symbol == symbol and int((row or {}).get("revision", 0) or 0) > int(
                    state.get("attention_revision", 0) or 0) for (row_symbol, _source), row in remote_sources.items())
            )
            if remote_change_is_newer:
                conflicts += 1
                continue
            intent_id = operation_id if operation_id and len(operation_id) <= 128 else _attention_intent_id(
                self._workspace_id, self._node_id, symbol, "manual", "remove_all", state["favorites_revision"], operation_id)
            pending.append({
                "intent_id": intent_id, "symbol": symbol, "source": "manual", "action": "remove_all",
            })
        snapshot = self._apply_attention_batch(snapshot, pending, baseline_favorites_revision)
        remote_tombstones = {item.get("symbol"): item for item in snapshot.get("tombstones", [])
                             if isinstance(item, dict)}

        state = manager.get_persistent_favorite_attention_state()
        remote_sources = {(item.get("symbol"), _normalize_local_attention_source(item.get("source"))): item
                          for item in snapshot.get("sources", []) if isinstance(item, dict)}
        pending = []
        for code, removed_sources in sorted(state.get("source_tombstones", {}).items()):
            symbol = _normalize_symbol(code)
            if not symbol or symbol in remote_tombstones:
                continue
            for source, removal in sorted(removed_sources.items()):
                current = remote_sources.get((symbol, source))
                if current and not current.get("active"):
                    continue
                if current and int(current.get("revision", 0) or 0) > int(state.get("attention_revision", 0) or 0):
                    conflicts += 1
                    continue
                operation_id = str((removal or {}).get("operation_id", ""))
                intent_id = operation_id if operation_id and len(operation_id) <= 128 else _attention_intent_id(
                    self._workspace_id, self._node_id, symbol, source, "remove_source",
                    state["favorites_revision"], operation_id,
                )
                pending.append({
                    "intent_id": intent_id, "symbol": symbol,
                    "source": _normalize_workspace_attention_source(source), "action": "remove_source",
                })
        snapshot = self._apply_attention_batch(snapshot, pending, baseline_favorites_revision)

        state = manager.get_persistent_favorite_attention_state()
        remote_sources = {(item.get("symbol"), _normalize_local_attention_source(item.get("source"))): item
                          for item in snapshot.get("sources", []) if isinstance(item, dict)}
        pending = []
        for code, sources in sorted(state.get("sources", {}).items()):
            symbol = _normalize_symbol(code)
            if not symbol:
                continue
            for source, metadata in sorted(sources.items()):
                current = remote_sources.get((symbol, source))
                if current and current.get("active"):
                    continue
                # A newer central tombstone or source state suppresses this local
                # replica until the newer workspace state has been projected.
                tombstone = remote_tombstones.get(symbol)
                if tombstone and int(tombstone.get("revision", 0) or 0) > int(state.get("attention_revision", 0) or 0):
                    conflicts += 1
                    continue
                if current and int(current.get("revision", 0) or 0) > int(state.get("attention_revision", 0) or 0):
                    conflicts += 1
                    continue
                validator = getattr(manager, "validate_stock_code", None)
                if callable(validator):
                    try:
                        validator(code)
                    except ValueError as error:
                        if str(error) in ("unsupported_stock_code", "stock_directory_unavailable", "delisted_stock"):
                            conflicts += 1
                            continue
                        raise
                intent_id = _attention_intent_id(self._workspace_id, self._node_id, symbol, source, "add",
                                                 (metadata or {}).get("local_revision", state["favorites_revision"]),
                                                 (metadata or {}).get("operation_id", ""))
                pending.append({
                    "intent_id": intent_id, "symbol": symbol,
                    "source": _normalize_workspace_attention_source(source), "action": "add",
                })
        snapshot = self._apply_attention_batch(snapshot, pending, baseline_favorites_revision)

        # Refresh after local writes, then apply central removals/additions under the file lock.
        snapshot = self._get_attention_snapshot()
        remote_tombstones = {item.get("symbol"): item for item in snapshot.get("tombstones", [])
                             if isinstance(item, dict)}
        remote_sources = {(item.get("symbol"), _normalize_local_attention_source(item.get("source"))): item
                          for item in snapshot.get("sources", []) if isinstance(item, dict)}
        local = manager.get_persistent_favorite_attention_state()
        if int(local.get("favorites_revision", 0) or 0) != baseline_favorites_revision:
            self._attention_status = "retrying: local_favorites_changed"
            self._attention_wakeup.set()
            return
        local_revision = baseline_favorites_revision
        for symbol, tombstone in remote_tombstones.items():
            if not symbol or not tombstone.get("intent_id"):
                continue
            result = manager.apply_favorite_source_intent(
                symbol[:6], "manual", "remove_all", tombstone["intent_id"], origin="remote_sync",
                expected_revision=local_revision,
            )
            local_revision = int(result.get("favorites_revision", local_revision) or local_revision)
        local = manager.get_persistent_favorite_attention_state()
        local_revision = int(local.get("favorites_revision", local_revision) or local_revision)
        for (symbol, source), remote in remote_sources.items():
            code = str(symbol or "")[:6]
            if len(code) != 6 or not code.isdigit() or symbol in remote_tombstones:
                continue
            present = source in local.get("sources", {}).get(code, {})
            if remote.get("active") and not present:
                try:
                    result = manager.apply_favorite_source_intent(
                        code, source, "add", remote.get("intent_id"), origin="remote_sync",
                        expected_revision=local_revision,
                    )
                except ValueError as error:
                    if str(error) in ("unsupported_stock_code", "stock_directory_unavailable", "delisted_stock"):
                        conflicts += 1
                        continue
                    raise
                local_revision = int(result.get("favorites_revision", local_revision) or local_revision)
            elif not remote.get("active") and present:
                result = manager.apply_favorite_source_intent(
                    code, source, "remove_source", remote.get("intent_id"), origin="remote_sync",
                    expected_revision=local_revision,
                )
                local_revision = int(result.get("favorites_revision", local_revision) or local_revision)
            if remote.get("active") and present or not remote.get("active") and not present:
                continue
            local = manager.get_persistent_favorite_attention_state()
        local = manager.get_persistent_favorite_attention_state()
        manager.set_attention_sync_revision(
            int(snapshot.get("revision", 0) or 0), int(local.get("favorites_revision", 0) or 0),
        )
        self._attention_status = "synced_with_conflicts:" + str(conflicts) if conflicts else "synced"

    def _get_attention_snapshot(self):
        query = urlencode({"workspace_id": self._workspace_id, "node_id": self._node_id})
        result = self._fetch_json("/api/v1/linkage/attention?" + query)
        if (not isinstance(result, dict) or result.get("schema_version") != 1
                or not isinstance(result.get("revision"), int)):
            raise ValueError("invalid_attention_snapshot")
        return result

    def _apply_attention_intent(self, snapshot, intent):
        state = self._favorite_manager.get_favorite_attention_state()
        return self._apply_attention_batch(snapshot, [intent], int(state.get("favorites_revision", 0) or 0))

    def _apply_attention_batch(self, snapshot, intents, baseline_favorites_revision):
        if not intents:
            return snapshot
        for offset in range(0, len(intents), 500):
            payload = {
                "workspace_id": self._workspace_id,
                "node_id": self._node_id,
                "base_revision": int(snapshot.get("revision", 0) or 0),
                "intents": intents[offset:offset + 500],
            }
            status, result = self._request_json("POST", "/api/v1/linkage/attention/intents/batch", payload)
            if status == 409 and isinstance(result, dict) and result.get("code") == "attention_revision_conflict":
                # The new remote revision has not been projected locally yet.
                # Keep the consumed cursor so the next pass reconciles tombstones.
                raise ValueError("attention_revision_conflict")
            if status != 200 or not isinstance(result, dict) or not isinstance(result.get("revision"), int):
                code = result.get("code", "error") if isinstance(result, dict) else "invalid_response"
                raise ValueError("attention_batch_http_" + str(status) + ":" + str(code))
            errors = result.get("errors", [])
            if errors:
                raise ValueError("attention_batch_rejected:" + str(errors[0].get("code", "error")))
            snapshot = {**snapshot, "revision": result["revision"]}
        return self._get_attention_snapshot()

    def _notify(self):
        if not self.callback:
            return
        snapshot, status = self.latest()
        try:
            self.callback(snapshot, status)
        except Exception:
            logger.exception("System-linkage context callback failed")


def _require_private_host(host):
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        import socket
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
    if not addresses or any(not (address.is_private or address.is_loopback) for address in addresses):
        raise ValueError("stock_strategy_base_url_must_resolve_to_private_addresses")


def _normalize_symbol(symbol):
    value = str(symbol or "").strip().upper()
    if len(value) == 9 and value[:6].isdigit() and value.endswith((".SH", ".SZ")):
        return value
    if len(value) == 6 and value.isdigit():
        exchange = "SH" if value.startswith(("600", "601", "603", "605", "688", "689")) else "SZ"
        return value + "." + exchange
    return ""


def _normalize_local_attention_source(source):
    value = str(source or "").strip()[:96]
    if value.startswith("stock-strategy."):
        return "stock-strategy:" + value[len("stock-strategy."):]
    return value


def _normalize_workspace_attention_source(source):
    value = str(source or "").strip()[:96]
    if value.startswith("stock-strategy:"):
        return "stock-strategy." + value[len("stock-strategy:"):]
    return value


def _attention_intent_id(workspace_id, node_id, symbol, source, action, local_revision, operation_id=""):
    raw = "|".join((str(workspace_id), str(node_id), str(symbol), str(source), str(action),
                    str(local_revision), str(operation_id)))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]
    return "attn-" + digest


def _auction_evidence_freshness(
        trade_date, as_of, snapshot_trade_date, now=None, source_freshness="fresh", payload_freshness=""):
    """Keep opening-auction evidence historical after the opening session ends."""
    from zoneinfo import ZoneInfo

    if not trade_date or not snapshot_trade_date:
        return "unknown"
    if trade_date != snapshot_trade_date:
        return "stale"
    if source_freshness == "stale" or payload_freshness == "stale":
        return "stale"
    if source_freshness == "unknown":
        return "unknown"
    if source_freshness == "historical":
        return "historical"
    if source_freshness != "fresh":
        return "unknown"
    observed_at = _parse_time(as_of)
    if observed_at is None:
        return "unknown"
    try:
        shanghai = ZoneInfo("Asia/Shanghai")
        if now is None:
            now_at = datetime.now(timezone.utc)
        elif isinstance(now, datetime):
            now_at = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        else:
            return "unknown"
        local_now = now_at.astimezone(shanghai)
        if observed_at.tzinfo is None:
            return "unknown"
        local_observed = observed_at.astimezone(shanghai)
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if local_now.date().isoformat() != trade_date or local_observed.date().isoformat() != trade_date:
        return "stale"
    if local_observed.hour != 9 or not 15 <= local_observed.minute < 30:
        return "unknown"
    if local_now.hour > 9 or local_now.hour == 9 and local_now.minute >= 30:
        return "historical"
    age_seconds = (local_now - local_observed).total_seconds()
    if age_seconds > 300 or age_seconds < -30:
        return "stale"
    return "fresh"


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
