"""Read-only source readiness and provenance store for the IPO data contract.

This module never fills unavailable indicators with estimates. Verified Eastmoney
IPO facts, market quotes and minute bars are published with provenance; fields
without a tested source stay UNREADY.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo

from ats.strategy.ipo_data_contracts import (
    IPO_REQUIRED_FIELDS,
    IPODecisionConfigSnapshot,
)


SOURCE_DB_RELATIVE_PATH = Path("data") / "ipo_learning" / "source_observations.sqlite"
_ROUTES: Dict[str, Dict[str, str]] = {
    "issue_price": {"source": "Eastmoney IPO 发行日历", "route": "RPTA_APP_IPOAPPLY.ISSUE_PRICE", "action": "已接入发行日历；强制刷新成功后写入带时区与TTL的观测"},
    "float_shares_wan": {"source": "TDX证券财务信息", "route": "liutongguben/10000，按 updated_date 标注来源时点", "action": "30天静态股本TTL；缺更新日或股本无效时不入库"},
    "pe_ratio": {"source": "东方财富IPO发行数据", "route": "RPTA_APP_IPOAPPLY.AFTER_ISSUE_PE", "action": "已接入发行市盈率；按UP_DATE校验时效"},
    "industry_pe_median": {"source": "东方财富全市场行情", "route": "按IPO行业匹配A股动态市盈率中位数", "action": "至少5家有效同行样本且源行情新鲜才入库"},
    "online_sub_multiple": {"source": "东方财富IPO发行数据", "route": "RPTA_APP_IPOAPPLY.ONLINE_ES_MULTIPLE", "action": "已接入网上超额认购倍数；空值保持未就绪"},
    "winning_rate_pct": {"source": "东方财富IPO发行数据", "route": "100/ONLINE_ES_MULTIPLE", "action": "由网上超额认购倍数确定性换算；无倍数不生成"},
    "scarcity_rank": {"source": "本地新股横截面", "route": "按冻结口径对同批次流通股本排名", "action": "先实现横截面定义与同批次样本完整性校验"},
    "hot_themes": {"source": "公告/行业主题", "route": "公告抽取加人工词典确认", "action": "需要来源链接、发布时间与主题置信度证据"},
    "ret_pct": {"source": "腾讯/TDX行情", "route": "腾讯时间戳快照；TDX连续竞价备源", "action": "校验代码、来源身份及30秒TTL；TDX须同时验证最新分钟线"},
    "turnover_pct": {"source": "腾讯/TDX行情", "route": "快照换手率；TDX以成交量/可信流通股本计算", "action": "缺可信流通股本时保持未就绪并校验报价时效"},
    "price_vwap_dist_pct": {"source": "腾讯/TDX行情", "route": "成交额/成交量推导VWAP后计算现价偏离", "action": "成交量或成交额无效时保持未就绪；TDX须通过分钟时效校验"},
    "open_premium_pct": {"source": "腾讯/TDX行情+东方财富发行数据", "route": "现价/发行价-1", "action": "两个输入均须通过来源和时效校验"},
    "slope_deg": {"source": "TDX 1分钟行情", "route": "固定窗口对数价格回归斜率", "action": "需冻结回归窗口、最少样本与量纲"},
    "session_high": {"source": "腾讯/TDX行情", "route": "带时间戳快照当日最高字段", "action": "校验来源身份、时效；TDX须处于连续竞价并有新分钟线"},
    "session_low": {"source": "腾讯/TDX行情", "route": "带时间戳快照当日最低字段", "action": "校验来源身份、时效；TDX须处于连续竞价并有新分钟线"},
    "current_price": {"source": "腾讯/TDX行情", "route": "时间戳现价；TDX连续竞价快照备源", "action": "校验六位代码、来源身份及30秒TTL"},
    "turnover_climb_speed": {"source": "TDX行情+流通股本", "route": "换手率固定窗口差分", "action": "需要完整分时量与可信股本"},
    "minutes_above_vwap_ratio": {"source": "东方财富/TDX 1分钟行情", "route": "分钟收盘高于截至该分钟累计VWAP的比例", "action": "仅统计当日有效成交分钟；TDX备源须有当日最新分钟线"},
    "pullback_from_peak_pct": {"source": "腾讯/TDX行情", "route": "现价相对当日最高点回撤", "action": "现价与最高点使用同一报价时间并校验TTL"},
    "halt_count": {"source": "交易所停复牌公告", "route": "临时停牌/复牌事件流", "action": "分钟缺口只能提示，不可直接当作停牌证据"},
    "volume_percentile_20d": {"source": "TDX沪深指数日线", "route": "沪深成交额求和后计算20日分位", "action": "两市场共同有效日线不足60天或超TTL时保持未就绪"},
    "volume_percentile_60d": {"source": "TDX沪深指数日线", "route": "沪深成交额求和后计算60日分位", "action": "要求60个共同有效交易日并校验两指数日期对齐"},
    "advance_decline_ratio": {"source": "东方财富A股/TDX全市场快照", "route": "上涨家数/(上涨+下跌家数)", "action": "仅接受来源时间覆盖≥95%、报价≤120秒且横截面跨度≤180秒的快照"},
    "index_relative_strength": {"source": "TDX沪深指数日线", "route": "20交易日上证综指收益减深证成指收益，单位百分点", "action": "要求至少21个共同收盘日、两指数同日对齐且最新日期通过TTL"},
    "limit_down_count": {"source": "TDX全A股快照", "route": "按板块及ST涨跌幅规则计跌停；剔除上市前5个交易日", "action": "快照覆盖及时效门槛不满足时不写入"},
    "financing_balance_change": {"source": "东方财富两融汇总", "route": "RPTA_RZRQ_LSHJ 的最新有效 RZYE 日变动", "action": "最新两日有效记录；来源时区 Asia/Shanghai；24 小时 TTL"},
    "limit_up_break_rate": {"source": "东方财富涨停池/炸板池", "route": "炸板池家数/(涨停池家数+炸板池家数)", "action": "要求两个池日期等于当前交易日、行数一致且无重叠；仅后台采集"},
    "high_volatility_amount_share": {"source": "TDX/东方财富全A股快照", "route": "绝对涨跌幅≥5%的个股成交额/全市场成交额", "action": "要求至少3000个有效成交额样本并通过来源时间TTL"},
    "ipo_amount_share": {"source": "TDX/东方财富全A股快照+IPO日历", "route": "上市日期距采集日不超过30个自然日的新股成交额/全市场成交额", "action": "IPO日历完整且新股报价覆盖≥95%才写入"},
    "theme_concentration": {"source": "东方财富A股行业分类与行情", "route": "行业成交额HHI（0至10000）", "action": "至少5个行业且行业成交额分类覆盖≥95%才写入"},
    "listing_supply_pace": {"source": "东方财富IPO发行日历", "route": "近20日已公告上市家数", "action": "只计具备上市日期与来源更新时间的不同股票代码"},
    "d1_positive_rate": {"source": "IPO上市队列历史", "route": "D1正收益样本占比", "action": "需成熟标签队列和历史全样本"},
    "d1_top_rate": {"source": "IPO上市队列历史", "route": "D1高收益分位占比", "action": "需冻结top阈值与停牌处理"},
    "d2_positive_rate": {"source": "IPO上市队列历史", "route": "D2正收益样本占比", "action": "需成熟D2标签和上市日历对齐"},
    "d3_positive_rate": {"source": "IPO上市队列历史", "route": "D3正收益样本占比", "action": "需成熟D3标签和上市日历对齐"},
    "d1_d2_max_drawdown": {"source": "IPO上市队列历史", "route": "D1-D2最大回撤分布", "action": "需冻结回撤基准价、日内低点与停牌口径"},
    "limit_down_rate": {"source": "IPO上市队列历史", "route": "新股跌停样本比例", "action": "按板块涨跌幅制度及无涨跌幅日区分"},
    "new_stock_relative_strength": {"source": "IPO与宽基行情", "route": "IPO队列收益减宽基收益", "action": "需同一时点、同一日龄的收益配对"},
    "close_position": {"source": "IPO上市队列历史", "route": "收盘在日内高低区间的位置", "action": "需校验零振幅、停牌及首日无涨跌幅规则"},
    "new_stock_turnover_median": {"source": "IPO分钟/日行情", "route": "新股队列换手率中位数", "action": "需可信流通股本和固定新股日龄区间"},
    "new_stock_innovation_high_rate": {"source": "IPO上市队列历史", "route": "新股创新高样本比例", "action": "需冻结历史高点回看窗和幸存样本口径"},
}


def source_route(field_id: str) -> Dict[str, str]:
    route = _ROUTES.get(field_id)
    return dict(route) if route else {
        "source": "未登记", "route": "无", "action": "补充字段级数据来源与计算口径",
    }


def _database_path(root: str | Path) -> Path:
    return Path(root).resolve() / SOURCE_DB_RELATIVE_PATH


def _observation_fingerprint(
    ticker: str,
    field_id: str,
    value_json: str,
    source_id: str,
    source_version: str,
    source_timezone: str,
    as_of_time_utc: str,
    available_at_utc: str,
    configuration_hash: str,
    data_contract_hash: str,
    sample_count: Optional[int],
    cohort_id: Optional[str],
) -> str:
    payload = {
        "ticker": ticker, "field_id": field_id, "status": "OBSERVED",
        "value_json": value_json, "source_id": source_id,
        "source_version": source_version, "source_timezone": source_timezone,
        "as_of_time_utc": as_of_time_utc, "available_at_utc": available_at_utc,
        "configuration_hash": configuration_hash,
        "data_contract_hash": data_contract_hash,
        "sample_count": sample_count, "cohort_id": cohort_id,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def store_observation(
    root: str | Path,
    *,
    ticker: str,
    field_id: str,
    observation: Mapping[str, Any],
    config: IPODecisionConfigSnapshot,
) -> bool:
    """Persist one provenance-complete observation after validating its contract."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        return False
    if field_id not in config.data_contract.required_fields:
        return False
    now = datetime.now(timezone.utc)
    check = config.data_contract.validate_observation(field_id, observation, now)
    if not check.usable or check.status != "OBSERVED":
        return False
    contract = config.data_contract.fields[field_id]
    value = observation.get(contract.value_key)
    as_of = observation.get(contract.as_of_key)
    available_at = observation.get(contract.available_at_key)
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        as_of_text = _utc_text(as_of, contract.source_timezone)
        available_text = _utc_text(available_at, contract.source_timezone)
    except (TypeError, ValueError, OverflowError):
        return False
    sample_count = observation.get("sample_count")
    if sample_count is not None and (
        isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1
    ):
        return False
    cohort_id = observation.get("cohort_id")
    if cohort_id is not None and (
        not isinstance(cohort_id, str) or not cohort_id.strip() or len(cohort_id) > 160
        or any(not (char.isalnum() or char in "._:-") for char in cohort_id)
    ):
        return False
    path = _database_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=2.0) as connection:
            connection.execute("PRAGMA busy_timeout=2000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS field_observations (
                    ticker TEXT NOT NULL, field_id TEXT NOT NULL, status TEXT NOT NULL,
                    value_json TEXT, source_id TEXT NOT NULL, source_version TEXT NOT NULL,
                    source_timezone TEXT NOT NULL, as_of_time_utc TEXT NOT NULL,
                    available_at_utc TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                    data_contract_hash TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
                    sample_count INTEGER, cohort_id TEXT,
                    PRIMARY KEY (ticker, field_id)
                )"""
            )
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(field_observations)"
                ).fetchall()
            }
            if "sample_count" not in columns:
                connection.execute(
                    "ALTER TABLE field_observations ADD COLUMN sample_count INTEGER"
                )
            if "cohort_id" not in columns:
                connection.execute(
                    "ALTER TABLE field_observations ADD COLUMN cohort_id TEXT"
                )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS field_observation_history (
                    observation_hash TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL, field_id TEXT NOT NULL, status TEXT NOT NULL,
                    value_json TEXT NOT NULL, source_id TEXT NOT NULL,
                    source_version TEXT NOT NULL, source_timezone TEXT NOT NULL,
                    as_of_time_utc TEXT NOT NULL, available_at_utc TEXT NOT NULL,
                    configuration_hash TEXT NOT NULL, data_contract_hash TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL, sample_count INTEGER, cohort_id TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_field_observation_history_lookup "
                "ON field_observation_history(ticker, field_id, available_at_utc)"
            )
            source_id = str(observation.get("source_id") or "")
            source_version = str(observation.get("source_version") or "")
            configuration_hash = config.config_hash
            data_contract_hash = config.data_contract.config_hash
            fingerprint = _observation_fingerprint(
                ticker, field_id, encoded, source_id, source_version,
                contract.source_timezone, as_of_text, available_text,
                configuration_hash, data_contract_hash, sample_count, cohort_id,
            )
            recorded_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            connection.execute(
                """INSERT OR IGNORE INTO field_observation_history (
                       observation_hash, ticker, field_id, status, value_json,
                       source_id, source_version, source_timezone, as_of_time_utc,
                       available_at_utc, configuration_hash, data_contract_hash,
                       recorded_at_utc, sample_count, cohort_id
                   ) VALUES (?, ?, ?, 'OBSERVED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fingerprint, ticker, field_id, encoded, source_id, source_version,
                    contract.source_timezone, as_of_text, available_text,
                    configuration_hash, data_contract_hash, recorded_at,
                    sample_count, cohort_id,
                ),
            )
            connection.execute(
                """INSERT INTO field_observations (
                       ticker, field_id, status, value_json, source_id, source_version,
                       source_timezone, as_of_time_utc, available_at_utc,
                       configuration_hash, data_contract_hash, updated_at_utc,
                       sample_count, cohort_id
                   ) VALUES (?, ?, 'OBSERVED', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, field_id) DO UPDATE SET
                     status=excluded.status, value_json=excluded.value_json,
                     source_id=excluded.source_id, source_version=excluded.source_version,
                     source_timezone=excluded.source_timezone, as_of_time_utc=excluded.as_of_time_utc,
                     available_at_utc=excluded.available_at_utc,
                     configuration_hash=excluded.configuration_hash,
                     data_contract_hash=excluded.data_contract_hash, updated_at_utc=excluded.updated_at_utc,
                     sample_count=excluded.sample_count, cohort_id=excluded.cohort_id
                """,
                (
                    ticker, field_id, encoded, source_id, source_version,
                    contract.source_timezone, as_of_text, available_text,
                    configuration_hash, data_contract_hash, recorded_at,
                    sample_count, cohort_id,
                ),
            )
        return True
    except (OSError, sqlite3.Error):
        return False


def _utc_text(value: Any, source_timezone: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    else:
        raise ValueError("invalid timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(source_timezone))
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _utc_bound_text(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    else:
        raise ValueError("history bounds must be aware datetimes")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("history bounds must include a UTC offset")
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")


def load_observations(
    root: str | Path,
    ticker: str,
    config: Optional[IPODecisionConfigSnapshot] = None,
) -> Dict[str, Dict[str, Any]]:
    """Read stored observations only; a missing/unreadable store means no data."""
    if config is not None and (
        not isinstance(config, IPODecisionConfigSnapshot) or not config.verify_integrity()
    ):
        return {}
    path = _database_path(root)
    if not path.is_file():
        return {}
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as connection:
            columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(field_observations)"
                ).fetchall()
            }
            if config is not None and not {
                "configuration_hash", "data_contract_hash",
            }.issubset(columns):
                return {}
            hash_columns = ", configuration_hash, data_contract_hash" if config else ""
            hash_filter = (
                " AND configuration_hash=? AND data_contract_hash=?" if config else ""
            )
            params: Tuple[Any, ...] = (ticker,)
            if config is not None:
                params += (config.config_hash, config.data_contract.config_hash)
            rows = connection.execute(
                "SELECT field_id, status, value_json, source_id, source_version, source_timezone, "
                "as_of_time_utc, available_at_utc" + hash_columns +
                " FROM field_observations WHERE ticker=?" + hash_filter,
                params,
            ).fetchall()
        observations: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            try:
                observations[row[0]] = {
                    "status": row[1], "value": json.loads(row[2]) if row[2] is not None else None,
                    "source_id": row[3], "source_version": row[4],
                    "source_timezone": row[5], "as_of_time": row[6], "available_at": row[7],
                }
            except (TypeError, ValueError):
                continue
        return observations
    except (OSError, sqlite3.Error):
        return {}


def load_observation_history(
    root: str | Path,
    ticker: str,
    config: IPODecisionConfigSnapshot,
    start_time: Optional[Any] = None,
    end_time: Optional[Any] = None,
) -> list[Dict[str, Any]]:
    """Load append-only, contract-bound observations for cut-off replay."""
    if (
        not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit()
        or not isinstance(config, IPODecisionConfigSnapshot)
        or not config.verify_integrity()
    ):
        return []
    try:
        start_utc = _utc_bound_text(start_time) if start_time is not None else None
        end_utc = _utc_bound_text(end_time) if end_time is not None else None
        if start_utc is not None and end_utc is not None and start_utc > end_utc:
            return []
    except (TypeError, ValueError, OverflowError):
        return []
    path = _database_path(root)
    if not path.is_file():
        return []
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.25) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                ("field_observation_history",),
            ).fetchone()
            if table is None:
                return []
            clauses = [
                "ticker=?", "configuration_hash=?", "data_contract_hash=?",
                "status='OBSERVED'",
            ]
            params: list[Any] = [
                ticker, config.config_hash, config.data_contract.config_hash,
            ]
            if start_utc is not None:
                clauses.append("available_at_utc>=?")
                params.append(start_utc)
            if end_utc is not None:
                clauses.append("available_at_utc<=?")
                params.append(end_utc)
            rows = connection.execute(
                "SELECT observation_hash, ticker, field_id, value_json, source_id, "
                "source_version, source_timezone, as_of_time_utc, available_at_utc, "
                "configuration_hash, data_contract_hash, sample_count, cohort_id "
                "FROM field_observation_history WHERE " + " AND ".join(clauses) +
                " ORDER BY available_at_utc, field_id, observation_hash",
                tuple(params),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return []

    result: list[Dict[str, Any]] = []
    for row in rows:
        (
            fingerprint, stored_ticker, field_id, value_json, source_id,
            source_version, source_timezone, as_of_time, available_at,
            configuration_hash, data_contract_hash, sample_count, cohort_id,
        ) = row
        contract = config.data_contract.fields.get(field_id)
        if (
            contract is None or source_id != contract.source_id
            or source_version != contract.source_version
            or source_timezone != contract.source_timezone
        ):
            continue
        try:
            value = json.loads(value_json)
            expected_hash = _observation_fingerprint(
                stored_ticker, field_id, value_json, source_id, source_version,
                source_timezone, as_of_time, available_at, configuration_hash,
                data_contract_hash, sample_count, cohort_id,
            )
        except (TypeError, ValueError, OverflowError):
            continue
        if fingerprint != expected_hash:
            continue
        result.append({
            "observation_hash": fingerprint,
            "ticker": stored_ticker,
            "field_id": field_id,
            "status": "OBSERVED",
            "value": value,
            "source_id": source_id,
            "source_version": source_version,
            "source_timezone": source_timezone,
            "as_of_time": as_of_time,
            "available_at": available_at,
            "configuration_hash": configuration_hash,
            "data_contract_hash": data_contract_hash,
            "sample_count": sample_count,
            "cohort_id": cohort_id,
        })
    return result


def load_latest_valid_observations(
    root: str | Path,
    config: IPODecisionConfigSnapshot,
    evaluation_time: Optional[datetime] = None,
) -> Dict[str, Dict[str, Any]]:
    """Read newest field observations bound to the currently loaded contract hashes."""
    now = evaluation_time or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        return {}
    path = _database_path(root)
    if not path.is_file():
        return {}
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as connection:
            rows = connection.execute(
                "SELECT field_id, ticker, status, value_json, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc, configuration_hash, "
                "data_contract_hash FROM field_observations "
                "WHERE status='OBSERVED' ORDER BY available_at_utc DESC LIMIT 1000"
            ).fetchall()
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            field_id, ticker = str(row[0]), str(row[1])
            if field_id in result or row[9] != config.config_hash or row[10] != config.data_contract.config_hash:
                continue
            try:
                value = json.loads(row[3])
            except (TypeError, ValueError):
                continue
            observation = {
                "status": row[2], "value": value, "source_id": row[4],
                "source_version": row[5], "source_timezone": row[6],
                "as_of_time": row[7], "available_at": row[8], "ticker": ticker,
            }
            check = config.data_contract.validate_observation(field_id, observation, now)
            if check.usable and check.status == "OBSERVED":
                result[field_id] = observation
        return result
    except (OSError, sqlite3.Error):
        return {}


def collect_source_readiness(
    root: str | Path,
    ticker: str,
    config: Optional[IPODecisionConfigSnapshot],
    evaluation_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build a field-by-field UI/preflight report without network or writes."""
    now = evaluation_time or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    observations = load_observations(root, ticker, config)
    for field_id, observation in load_observations(root, "000000", config).items():
        observations.setdefault(field_id, observation)
    rows = []
    for field_id in IPO_REQUIRED_FIELDS:
        route = source_route(field_id)
        contract = config.data_contract.fields.get(field_id) if config else None
        observation = observations.get(field_id)
        check = (
            config.data_contract.validate_observation(field_id, observation, now)
            if config is not None and observation is not None
            else None
        )
        usable = bool(check and check.usable and check.status == "OBSERVED")
        rows.append({
            "field_id": field_id,
            "domain": _domain(field_id),
            "status": "READY" if usable else "UNREADY",
            "reason": "已通过来源/时区/TTL校验" if usable else (
                check.reason_code if check and check.reason_code else
                "缺少版本化契约" if contract is None else "暂无可核验观测"
            ),
            "value": observation.get("value") if usable and observation else None,
            "source": route["source"],
            "route": route["route"],
            "action": route["action"],
            "source_id": observation.get("source_id", contract.source_id) if contract and observation else (contract.source_id if contract else ""),
            "source_version": observation.get("source_version", contract.source_version) if contract and observation else (contract.source_version if contract else ""),
            "source_timezone": contract.source_timezone if contract else "",
            "max_age_seconds": contract.max_age_seconds if contract else None,
            "as_of_time": observation.get("as_of_time", "") if observation else "",
            "available_at": observation.get("available_at", "") if observation else "",
        })
    ready = sum(row["status"] == "READY" for row in rows)
    return {
        "ticker": ticker,
        "status": "READY" if ready == len(rows) else "UNREADY",
        "ready_count": ready,
        "required_count": len(rows),
        "configuration_hash": config.config_hash if config else "",
        "data_contract_hash": config.data_contract.config_hash if config else "",
        "observations": rows,
        "next_actions": [row for row in rows if row["status"] != "READY"],
    }


def _domain(field_id: str) -> str:
    if field_id in {"issue_price", "float_shares_wan", "pe_ratio", "industry_pe_median", "online_sub_multiple", "winning_rate_pct", "scarcity_rank", "hot_themes"}:
        return "PreHeat"
    if field_id in {"ret_pct", "turnover_pct", "price_vwap_dist_pct", "open_premium_pct", "slope_deg", "session_high", "session_low", "current_price", "turnover_climb_speed", "minutes_above_vwap_ratio", "pullback_from_peak_pct", "halt_count"}:
        return "LiveHeat"
    if field_id in {"volume_percentile_20d", "volume_percentile_60d", "advance_decline_ratio", "limit_down_count", "financing_balance_change", "limit_up_break_rate", "high_volatility_amount_share", "index_relative_strength", "ipo_amount_share", "theme_concentration", "listing_supply_pace"}:
        return "LRRM"
    return "IPORegime"


def collect_issue_prices_from_eastmoney(root: str | Path) -> Dict[str, Any]:
    """Refresh the IPO calendar once and persist every confirmed issue price."""
    config_path = Path(root).resolve() / "config" / "ipo_sentiment.yaml"
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        from ats.strategy.ipo_eastmoney_sources import _observation, _source_time, fetch_issue_calendar_rows

        rows = fetch_issue_calendar_rows()
        saved_codes = []
        rejected_count = 0
        for row in rows:
            ticker = str(row.get("SECURITY_CODE") or "").strip().zfill(6)
            if len(ticker) != 6 or not ticker.isdigit():
                rejected_count += 1
                continue
            issue_price = row.get("ISSUE_PRICE")
            as_of = _source_time(row.get("UP_DATE"))
            if not isinstance(issue_price, (int, float)) or isinstance(issue_price, bool) or issue_price <= 0 or not as_of:
                rejected_count += 1
                continue
            observation = _observation(float(issue_price),
                "eastmoney.datacenter-web.RPTA_APP_IPOAPPLY", "ipo_calendar.v1", as_of)
            if store_observation(
                root, ticker=ticker, field_id="issue_price", observation=observation, config=config
            ):
                saved_codes.append(ticker)
            else:
                rejected_count += 1
        return {
            "status": "READY" if saved_codes else "UNREADY", "field_id": "issue_price",
            "saved_count": len(saved_codes), "rejected_count": rejected_count,
            "tickers": saved_codes[:100],
            "reason": "已存入带来源与时区的本地观测库" if saved_codes else "本轮刷新未产生可验证的发行价观测",
            "configuration_hash": config.config_hash,
            "data_contract_hash": config.data_contract.config_hash,
        }
    except Exception as exc:
        return {"status": "UNREADY", "field_id": "issue_price", "saved_count": 0, "reason": f"发行日历采集异常: {type(exc).__name__}"}


def collect_issue_prices_from_ats_cache(root: str | Path, ticker: str | None = None) -> Dict[str, Any]:
    """Reuse ATS's persisted IPO calendar when its per-price provenance is valid."""
    path = Path(root).resolve() / "config" / "new_stock_ipo_calendar.json"
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("ATS 日历超过读取上限")
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, dict):
            raise ValueError("ATS 日历结构无效")
        config = IPODecisionConfigSnapshot.from_yaml(
            str(Path(root).resolve() / "config" / "ipo_sentiment.yaml")
        )
        saved = []
        for code, row in items.items():
            if ticker is not None and code != ticker:
                continue
            if not isinstance(row, dict) or not isinstance(code, str):
                continue
            price = row.get("issue_price")
            source = row.get("issue_price_source")
            if not isinstance(source, dict) or not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 0:
                continue
            observation = {
                "status": "OBSERVED", "value": float(price),
                "source_id": source.get("source_id"),
                "source_version": source.get("source_version"),
                "source_timezone": source.get("source_timezone"),
                "as_of_time": source.get("as_of_time"),
                "available_at": source.get("available_at"),
            }
            if store_observation(root, ticker=code, field_id="issue_price", observation=observation, config=config):
                saved.append(code)
        return {
            "status": "READY" if saved else "UNREADY", "field_id": "issue_price",
            "saved_count": len(saved), "tickers": saved,
            "source": "ATS persisted IPO calendar",
            "reason": "ATS 日历发行价已通过逐笔来源与时效校验" if saved else "ATS 日历无可核验且新鲜的发行价",
        }
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "UNREADY", "field_id": "issue_price", "saved_count": 0,
                "reason": f"ATS 日历不可用: {type(exc).__name__}"}


def collect_issue_price_from_eastmoney(root: str | Path, ticker: str) -> Dict[str, Any]:
    """Compatibility wrapper for one ticker; performs one shared calendar refresh."""
    if not isinstance(ticker, str) or len(ticker) != 6 or not ticker.isdigit():
        return {"status": "UNREADY", "field_id": "issue_price", "reason": "股票代码必须为六位数字"}
    result = collect_issue_prices_from_eastmoney(root)
    ready = ticker in result.get("tickers", [])
    return {
        "status": "READY" if ready else "UNREADY", "field_id": "issue_price",
        "reason": "已存入带来源与时区的本地观测库" if ready else result.get("reason", "发行价未通过来源/时效校验"),
        "configuration_hash": result.get("configuration_hash", ""),
        "data_contract_hash": result.get("data_contract_hash", ""),
    }


def collect_market_pulse_fields(root: str | Path) -> Dict[str, Any]:
    """Promote two persisted daily breadth metrics after exact provenance/TTL checks."""
    config_path = Path(root).resolve() / "config" / "ipo_sentiment.yaml"
    database_path = Path(root).resolve() / "market_pulse.db"
    try:
        config = IPODecisionConfigSnapshot.from_yaml(str(config_path))
        if not database_path.is_file():
            return {"status": "UNREADY", "saved_fields": [], "reason": "market_pulse.db 不存在"}
        with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True, timeout=0.1) as connection:
            rows = connection.execute(
                "SELECT date, up_count, down_count, limit_down, source_id, source_version, "
                "source_timezone, as_of_time_utc, available_at_utc "
                "FROM daily_sentiment ORDER BY date DESC LIMIT 64"
            ).fetchall()
        now = datetime.now(timezone.utc)
        for row in rows:
            _day, up_count, down_count, limit_down, source_id, source_version, source_timezone, as_of, available_at = row
            if (
                not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                        for value in (up_count, down_count, limit_down))
                or up_count + down_count <= 0
            ):
                continue
            metadata = {
                "status": "OBSERVED", "source_id": source_id,
                "source_version": source_version, "source_timezone": source_timezone,
                "as_of_time": as_of, "available_at": available_at,
            }
            observations = {
                "advance_decline_ratio": {**metadata, "value": up_count / (up_count + down_count)},
                "limit_down_count": {**metadata, "value": limit_down},
            }
            saved = []
            for field_id, observation in observations.items():
                if store_observation(
                    root, ticker="000000", field_id=field_id,
                    observation=observation, config=config,
                ):
                    saved.append(field_id)
            if saved:
                return {"status": "READY", "saved_fields": saved, "as_of_time": as_of}
        return {"status": "UNREADY", "saved_fields": [], "reason": "最近 64 条记录无来源完整且新鲜的市场广度数据"}
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        return {"status": "UNREADY", "saved_fields": [], "reason": f"市场情绪采集异常: {type(exc).__name__}"}
