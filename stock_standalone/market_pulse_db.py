# -*- coding:utf-8 -*-
"""
Market Pulse Database Layer
Responsible for persisting daily market reports and hot stock details.
File: market_pulse_db.py
"""
import sqlite3
import json
import math
import traceback
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger("MarketPulseDB")
DB_PATH = "./market_pulse.db"
DAILY_SENTIMENT_SOURCE_ID = "market_sentiment_fsm.daily_snapshot"
DAILY_SENTIMENT_SOURCE_VERSION = "daily_sentiment.v1.1"
DAILY_SENTIMENT_SOURCE_TIMEZONE = "Asia/Shanghai"

def migrate_market_pulse_db(db_path: str = DB_PATH) -> None:
    """Apply the idempotent sentiment schema migration before service readiness."""
    conn = sqlite3.connect(db_path, timeout=15.0)
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_sentiment (
                date TEXT PRIMARY KEY, index_pct REAL, breadth_ratio REAL,
                up_count INTEGER, down_count INTEGER, limit_up INTEGER,
                limit_down INTEGER, temperature REAL, worst_sectors_json TEXT,
                top_sectors_json TEXT, indices_json TEXT, source_version TEXT,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS current_sentiment_state (
                session_date TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL,
                as_of_time_utc TEXT NOT NULL,
                available_at_utc TEXT NOT NULL
            )
        """)
        cur.execute("PRAGMA table_info(daily_sentiment)")
        existing = {row[1] for row in cur.fetchall()}
        additions = {
            "lrrm_state": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "ipo_regime_state": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
            "source_version": "TEXT DEFAULT 'daily_sentiment.v1.1'",
            "source_id": "TEXT NOT NULL DEFAULT 'market_sentiment_fsm.daily_snapshot'",
            "source_timezone": "TEXT NOT NULL DEFAULT 'Asia/Shanghai'",
            "as_of_time_utc": "TEXT",
            "available_at_utc": "TEXT",
        }
        for column, definition in additions.items():
            if column not in existing:
                cur.execute(f"ALTER TABLE daily_sentiment ADD COLUMN {column} {definition}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_pulse_db():
    """Initialize the Market Pulse database tables."""
    conn = None
    try:
        migrate_market_pulse_db(DB_PATH)
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        cur = conn.cursor()
        
        # 1. Daily Reports Table: High-level market summary
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                date TEXT PRIMARY KEY,
                market_temperature REAL,
                summary_text TEXT,
                hot_sectors_json TEXT,  -- JSON list of top sectors
                user_notes TEXT,
                created_at TEXT,
                breadth_json TEXT,      -- JSON dict of breadth stats
                indices_json TEXT       -- JSON list of index performance
            )
        """)
        
        # Schema Migration: Add breadth_json and indices_json if not exists
        cur.execute("PRAGMA table_info(daily_reports)")
        columns = [col[1] for col in cur.fetchall()]
        if "breadth_json" not in columns:
            cur.execute("ALTER TABLE daily_reports ADD COLUMN breadth_json TEXT")
            logger.info("[DB] Added column breadth_json to daily_reports.")
        if "indices_json" not in columns:
            cur.execute("ALTER TABLE daily_reports ADD COLUMN indices_json TEXT")
            logger.info("[DB] Added column indices_json to daily_reports.")
        
        # 2. Daily Stocks Table: Individual stock details
        # Compound Primary Key: date + code
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_stocks (
                date TEXT,
                code TEXT,
                name TEXT,
                sector TEXT,
                reason TEXT,            -- Tags: 5连阳, 龙头 etc.
                score REAL,
                action_plan TEXT,       -- Generated advice: "Buy on pullback..."
                status_json TEXT,       -- Extra stats: {open, close, vol_ratio...}
                PRIMARY KEY (date, code)
            )
        """)
        
        conn.commit()
        logger.info("[DB] Market Pulse tables initialized.")
        return True
    except Exception as e:
        logger.error(f"[DB Init Error] {e}")
        if conn is not None:
            conn.rollback()
        return False
    finally:
        if conn is not None:
            conn.close()

def _convert_to_serializable(obj):
    """
    Recursively convert numpy types to native Python types for JSON serialization.
    """
    import numpy as np
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_serializable(i) for i in obj]
    return obj

def save_daily_pulse(date_str, summary_data, stock_list):
    """
    Save the full daily report and stock list to DB.
    
    :param date_str: "YYYY-MM-DD"
    :param summary_data: dict {temperature, summary, hot_sectors, notes}
    :param stock_list: list of dicts [{code, name, sector, reason, score, plan, status...}]
    """
    if init_pulse_db() is not True:
        return False
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    cur = conn.cursor()
    
    try:
        # 1. Save Summary
        # Clean numpy types from summary_data
        clean_hot_sectors = _convert_to_serializable(summary_data.get('hot_sectors', []))
        hot_sectors_json = json.dumps(clean_hot_sectors, ensure_ascii=False)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute("""
            INSERT INTO daily_reports (date, market_temperature, summary_text, hot_sectors_json, user_notes, created_at, breadth_json, indices_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                market_temperature=excluded.market_temperature,
                summary_text=excluded.summary_text,
                hot_sectors_json=excluded.hot_sectors_json,
                breadth_json=excluded.breadth_json,
                indices_json=excluded.indices_json,
                created_at=excluded.created_at
        """, (
            date_str,
            float(summary_data.get('temperature', 0.0)),
            summary_data.get('summary', ''),
            hot_sectors_json,
            summary_data.get('notes', ''),
            created_at,
            json.dumps(summary_data.get('breadth', {}), ensure_ascii=False),
            json.dumps(summary_data.get('indices', []), ensure_ascii=False)
        ))
        
        # 2. Save Stocks (Batch Insert)
        # First, delete existing stocks for this date to ensure clean update (optional, but safer for re-runs)
        cur.execute("DELETE FROM daily_stocks WHERE date=?", (date_str,))
        
        stock_tuples = []
        for s in stock_list:
            # Clean numpy types from status dict
            clean_status = _convert_to_serializable(s.get('status', {}))
            
            stock_tuples.append((
                date_str,
                s.get('code', ''),
                s.get('name', ''),
                s.get('sector', ''),
                s.get('reason', ''),
                float(s.get('score', 0.0)), # Ensure float
                s.get('action_plan', ''),
                json.dumps(clean_status, ensure_ascii=False)
            ))
            
        if stock_tuples:
            cur.executemany("""
                INSERT INTO daily_stocks (date, code, name, sector, reason, score, action_plan, status_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, stock_tuples)
            
        conn.commit()
        logger.info(f"[DB] Saved report for {date_str}: {len(stock_tuples)} stocks.")
        return True
        
    except Exception as e:
        logger.error(f"[DB Save Error] {e}")
        conn.rollback()
        traceback.print_exc()
        return False
    finally:
        conn.close()

def get_report_by_date(date_str):
    """Retrieve full report (summary + stocks) for a given date."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    result = {'summary': {}, 'stocks': []}
    
    try:
        # Get Summary
        cur.execute("SELECT * FROM daily_reports WHERE date=?", (date_str,))
        row = cur.fetchone()
        if row:
            result['summary'] = {
                'date': row[0],
                'temperature': row[1],
                'summary_text': row[2],
                'hot_sectors': json.loads(row[3]) if row[3] else [],
                'user_notes': row[4],
                'created_at': row[5],
                'breadth': json.loads(row[6]) if len(row) > 6 and row[6] else {},
                'indices': json.loads(row[7]) if len(row) > 7 and row[7] else []
            }
        
        # Get Stocks
        cur.execute("SELECT code, name, sector, reason, score, action_plan, status_json FROM daily_stocks WHERE date=?", (date_str,))
        rows = cur.fetchall()
        for r in rows:
            result['stocks'].append({
                'code': r[0],
                'name': r[1],
                'sector': r[2],
                'reason': r[3],
                'score': r[4],
                'action_plan': r[5],
                'status': json.loads(r[6]) if r[6] else {}
            })
            
    except Exception as e:
        logger.error(f"[DB Load Error] {e}")
    finally:
        conn.close()
        
    return result

def update_user_notes(date_str, notes):
    """Update user notes for a specific date."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE daily_reports SET user_notes=? WHERE date=?", (notes, date_str))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"[DB Note Update Error] {e}")
        return False

def get_all_recorded_dates():
    """Retrieve a list of all dates that have a record in the daily_reports table."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    dates = []
    try:
        cur.execute("SELECT date FROM daily_reports")
        dates = [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"[DB Date Query Error] {e}")
    finally:
        conn.close()
    return dates

def save_daily_sentiment(date_str: str, snapshot: dict) -> bool:
    if init_pulse_db() is not True:
        return False
    if not isinstance(snapshot, dict):
        return False
    source_id = snapshot.get('source_id', DAILY_SENTIMENT_SOURCE_ID)
    source_version = snapshot.get('source_version', DAILY_SENTIMENT_SOURCE_VERSION)
    source_timezone = snapshot.get('source_timezone', DAILY_SENTIMENT_SOURCE_TIMEZONE)
    if not isinstance(source_id, str) or not source_id.strip():
        logger.error("[DB Save Daily Sentiment Error] source_id is required")
        return False
    if not isinstance(source_version, str) or not source_version.strip():
        logger.error("[DB Save Daily Sentiment Error] source_version is required")
        return False
    if not isinstance(source_timezone, str) or not source_timezone.strip():
        logger.error("[DB Save Daily Sentiment Error] source_timezone is required")
        return False
    source_id = source_id.strip()
    source_version = source_version.strip()
    source_timezone = source_timezone.strip()
    try:
        ZoneInfo(source_timezone)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        logger.error("[DB Save Daily Sentiment Error] invalid source_timezone")
        return False
    raw_as_of = snapshot.get('as_of_time')
    as_of_utc = None
    if raw_as_of is not None:
        try:
            if isinstance(raw_as_of, str):
                raw_as_of = raw_as_of.strip()
                if raw_as_of.endswith('Z'):
                    raw_as_of = raw_as_of[:-1] + '+00:00'
                raw_as_of = datetime.fromisoformat(raw_as_of)
            if not isinstance(raw_as_of, datetime) or raw_as_of.tzinfo is None or raw_as_of.utcoffset() is None:
                raise ValueError("as_of_time must have a valid UTC offset")
            as_of_utc = raw_as_of.astimezone(timezone.utc)
        except (OverflowError, TypeError, ValueError):
            logger.error("[DB Save Daily Sentiment Error] invalid or naive as_of_time")
            return False
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    cur = conn.cursor()
    try:
        clean_worst = _convert_to_serializable(snapshot.get('worst_sectors', []))
        clean_top = _convert_to_serializable(snapshot.get('top_sectors', []))
        clean_indices = _convert_to_serializable(snapshot.get('indices', []))
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        available_at_utc = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        as_of_time_utc = as_of_utc.isoformat(timespec="microseconds") if as_of_utc else None
        if as_of_utc and as_of_utc > datetime.fromisoformat(available_at_utc):
            logger.error("[DB Save Daily Sentiment Error] as_of_time is after available_at")
            return False
        lrrm_value = snapshot.get('lrrm_state')
        lrrm_state = (
            lrrm_value if snapshot.get('lrrm_data_ready') is True
            and isinstance(lrrm_value, str)
            and lrrm_value in {'LOOSE', 'NORMAL', 'TIGHT', 'SHOCK'} else 'UNKNOWN'
        )
        regime_value = snapshot.get('ipo_regime_state')
        ipo_regime_state = (
            regime_value if snapshot.get('ipo_regime_data_ready') is True
            and isinstance(regime_value, str)
            and regime_value in {'DISTRIBUTION', 'REPAIR', 'CONTINUATION', 'MANIA', 'EXHAUSTION'}
            else 'UNKNOWN'
        )
        
        cur.execute("""
            INSERT INTO daily_sentiment (
                date, index_pct, breadth_ratio, up_count, down_count,
                limit_up, limit_down, temperature, worst_sectors_json,
                top_sectors_json, indices_json, source_version, created_at,
                lrrm_state, ipo_regime_state, source_id, source_timezone,
                as_of_time_utc, available_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                index_pct=excluded.index_pct,
                breadth_ratio=excluded.breadth_ratio,
                up_count=excluded.up_count,
                down_count=excluded.down_count,
                limit_up=excluded.limit_up,
                limit_down=excluded.limit_down,
                temperature=excluded.temperature,
                worst_sectors_json=excluded.worst_sectors_json,
                top_sectors_json=excluded.top_sectors_json,
                indices_json=excluded.indices_json,
                source_version=excluded.source_version,
                created_at=excluded.created_at,
                lrrm_state=excluded.lrrm_state,
                ipo_regime_state=excluded.ipo_regime_state,
                source_id=excluded.source_id,
                source_timezone=excluded.source_timezone,
                as_of_time_utc=excluded.as_of_time_utc,
                available_at_utc=excluded.available_at_utc
        """, (
            date_str,
            float(snapshot.get('index_pct', 0.0)),
            float(snapshot.get('breadth_ratio', 0.0)),
            int(snapshot.get('up_count', 0)),
            int(snapshot.get('down_count', 0)),
            int(snapshot.get('limit_up', 0)),
            int(snapshot.get('limit_down', 0)),
            float(snapshot.get('temperature', 0.0)),
            json.dumps(clean_worst, ensure_ascii=False),
            json.dumps(clean_top, ensure_ascii=False),
            json.dumps(clean_indices, ensure_ascii=False),
            source_version,
            created_at,
            lrrm_state,
            ipo_regime_state,
            source_id,
            source_timezone,
            as_of_time_utc,
            available_at_utc,
        ))
        conn.commit()
        logger.info(f"[DB] Saved daily sentiment for {date_str}.")
        return True
    except Exception as e:
        logger.error(f"[DB Save Daily Sentiment Error] {e}")
        traceback.print_exc()
        return False
    finally:
        conn.close()

from typing import Optional

def save_current_sentiment_state(
    session_date: str, state: str, reason: str = "", as_of_time: Any = None,
) -> bool:
    """Publish the auction classification for same-session Guardian consumers."""
    allowed = {"NEUTRAL", "PANIC", "REPAIR", "REVERSAL", "FOMO", "COOLDOWN"}
    if state not in allowed or not isinstance(session_date, str):
        return False
    try:
        datetime.strptime(session_date, "%Y-%m-%d")
        if as_of_time is None:
            as_of_time = datetime.now(timezone.utc)
        elif isinstance(as_of_time, str):
            value = as_of_time[:-1] + "+00:00" if as_of_time.endswith("Z") else as_of_time
            as_of_time = datetime.fromisoformat(value)
        if not isinstance(as_of_time, datetime) or as_of_time.tzinfo is None:
            return False
        if as_of_time.utcoffset() is None:
            return False
        as_of_utc = as_of_time.astimezone(timezone.utc)
        available_at = datetime.now(timezone.utc)
        if (
            as_of_utc > available_at
            or as_of_utc.astimezone(ZoneInfo(DAILY_SENTIMENT_SOURCE_TIMEZONE)).strftime("%Y-%m-%d")
            != session_date
        ):
            return False
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        try:
            conn.execute(
                """INSERT INTO current_sentiment_state (
                    session_date, state, reason, source_id, as_of_time_utc, available_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_date) DO UPDATE SET
                    state=excluded.state, reason=excluded.reason,
                    source_id=excluded.source_id, as_of_time_utc=excluded.as_of_time_utc,
                    available_at_utc=excluded.available_at_utc""",
                (
                    session_date, state, str(reason)[:240], DAILY_SENTIMENT_SOURCE_ID,
                    as_of_utc.isoformat(timespec="microseconds"),
                    available_at.isoformat(timespec="microseconds"),
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
        logger.exception("[DB] Failed to publish current sentiment state")
        return False


def get_current_sentiment_state(
    session_date: str, max_age_seconds: float = 28800.0,
) -> Optional[dict]:
    """Read only a same-session, fresh state; missing/stale state is unavailable."""
    if (
        not isinstance(session_date, str)
        or isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, (int, float))
        or not math.isfinite(max_age_seconds)
        or max_age_seconds <= 0
    ):
        return None
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=0.5)
        row = conn.execute(
            "SELECT state, reason, source_id, as_of_time_utc, available_at_utc "
            "FROM current_sentiment_state WHERE session_date=?",
            (session_date,),
        ).fetchone()
        if not row or row[2] != DAILY_SENTIMENT_SOURCE_ID:
            return None
        available = datetime.fromisoformat(str(row[4]).replace("Z", "+00:00"))
        as_of = datetime.fromisoformat(str(row[3]).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if (
            available.tzinfo is None or available.utcoffset() is None
            or as_of.tzinfo is None or as_of.utcoffset() is None
        ):
            return None
        available_utc = available.astimezone(timezone.utc)
        as_of_utc = as_of.astimezone(timezone.utc)
        if (
            (now - available_utc).total_seconds() < 0
            or (now - available_utc).total_seconds() > max_age_seconds
            or (now - as_of_utc).total_seconds() < 0
            or (now - as_of_utc).total_seconds() > max_age_seconds
            or as_of_utc.astimezone(ZoneInfo(DAILY_SENTIMENT_SOURCE_TIMEZONE)).strftime("%Y-%m-%d")
            != session_date
            or row[0] not in {"NEUTRAL", "PANIC", "REPAIR", "REVERSAL", "FOMO", "COOLDOWN"}
        ):
            return None
        return {
            "state": str(row[0]), "reason": str(row[1]),
            "source_id": str(row[2]), "as_of_time": str(row[3]),
            "available_at": str(row[4]),
        }
    except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
        logger.exception("[DB] Failed to read current sentiment state")
        return None
    finally:
        if conn is not None:
            conn.close()


def get_daily_sentiment(date_str: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT date, index_pct, breadth_ratio, up_count, down_count, limit_up, "
            "limit_down, temperature, worst_sectors_json, top_sectors_json, indices_json, "
            "source_version, created_at, lrrm_state, ipo_regime_state, source_id, "
            "source_timezone, as_of_time_utc, available_at_utc "
            "FROM daily_sentiment WHERE date=?",
            (date_str,),
        )
        row = cur.fetchone()
        if row:
            return {
                'date': row[0],
                'index_pct': row[1],
                'breadth_ratio': row[2],
                'up_count': row[3],
                'down_count': row[4],
                'limit_up': row[5],
                'limit_down': row[6],
                'temperature': row[7],
                'worst_sectors': json.loads(row[8]) if row[8] else [],
                'top_sectors': json.loads(row[9]) if row[9] else [],
                'indices': json.loads(row[10]) if row[10] else [],
                'source_version': row[11],
                'created_at': row[12],
                'lrrm_state': row[13] or 'UNKNOWN',
                'ipo_regime_state': row[14] or 'UNKNOWN',
                'lrrm_data_ready': bool(row[13] and row[13] != 'UNKNOWN'),
                'ipo_regime_data_ready': bool(row[14] and row[14] != 'UNKNOWN'),
                'data_ready': bool(row[13] and row[13] != 'UNKNOWN' and row[14] and row[14] != 'UNKNOWN'),
                'source_id': row[15],
                'source_timezone': row[16],
                'as_of_time': row[17],
                'available_at': row[18],
            }
    except Exception as e:
        logger.error(f"[DB Get Daily Sentiment Error] {e}")
    finally:
        conn.close()
    return None

def get_latest_sentiment_before(date_str: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT date, index_pct, breadth_ratio, up_count, down_count, limit_up, "
            "limit_down, temperature, worst_sectors_json, top_sectors_json, indices_json, "
            "source_version, created_at, lrrm_state, ipo_regime_state, source_id, "
            "source_timezone, as_of_time_utc, available_at_utc "
            "FROM daily_sentiment WHERE date < ? ORDER BY date DESC LIMIT 1",
            (date_str,),
        )
        row = cur.fetchone()
        if row:
            return {
                'date': row[0],
                'index_pct': row[1],
                'breadth_ratio': row[2],
                'up_count': row[3],
                'down_count': row[4],
                'limit_up': row[5],
                'limit_down': row[6],
                'temperature': row[7],
                'worst_sectors': json.loads(row[8]) if row[8] else [],
                'top_sectors': json.loads(row[9]) if row[9] else [],
                'indices': json.loads(row[10]) if row[10] else [],
                'source_version': row[11],
                'created_at': row[12],
                'lrrm_state': row[13] or 'UNKNOWN',
                'ipo_regime_state': row[14] or 'UNKNOWN',
                'lrrm_data_ready': bool(row[13] and row[13] != 'UNKNOWN'),
                'ipo_regime_data_ready': bool(row[14] and row[14] != 'UNKNOWN'),
                'data_ready': bool(row[13] and row[13] != 'UNKNOWN' and row[14] and row[14] != 'UNKNOWN'),
                'source_id': row[15],
                'source_timezone': row[16],
                'as_of_time': row[17],
                'available_at': row[18],
            }
    except Exception as e:
        logger.error(f"[DB Get Latest Sentiment Before Error] {e}")
    finally:
        conn.close()
    return None


def get_latest_sentiment_as_of(cutoff_time: Any) -> Optional[dict]:
    """Return only a sentiment snapshot both observed and available by cutoff."""
    try:
        if isinstance(cutoff_time, str):
            value = cutoff_time.strip()
            if value.endswith('Z'):
                value = value[:-1] + '+00:00'
            cutoff_time = datetime.fromisoformat(value)
        if not isinstance(cutoff_time, datetime) or cutoff_time.tzinfo is None or cutoff_time.utcoffset() is None:
            return None
        cutoff_utc = cutoff_time.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except (OverflowError, TypeError, ValueError):
        return None

    conn = sqlite3.connect(DB_PATH, timeout=1.0)
    try:
        row = conn.execute(
            "SELECT date, index_pct, breadth_ratio, up_count, down_count, limit_up, "
            "limit_down, temperature, worst_sectors_json, top_sectors_json, indices_json, "
            "source_version, created_at, source_id, source_timezone, as_of_time_utc, "
            "available_at_utc, lrrm_state, ipo_regime_state "
            "FROM daily_sentiment "
            "WHERE as_of_time_utc IS NOT NULL AND available_at_utc IS NOT NULL "
            "AND as_of_time_utc <= ? AND available_at_utc <= ? "
            "ORDER BY available_at_utc DESC, date DESC LIMIT 1",
            (cutoff_utc, cutoff_utc),
        ).fetchone()
        if not row:
            return None
        ZoneInfo(row[14])
        return {
            'date': row[0], 'index_pct': row[1], 'breadth_ratio': row[2],
            'up_count': row[3], 'down_count': row[4], 'limit_up': row[5],
            'limit_down': row[6], 'temperature': row[7],
            'worst_sectors': json.loads(row[8]) if row[8] else [],
            'top_sectors': json.loads(row[9]) if row[9] else [],
            'indices': json.loads(row[10]) if row[10] else [],
            'source_version': row[11], 'created_at': row[12],
            'source_id': row[13], 'source_timezone': row[14],
            'as_of_time': row[15], 'available_at': row[16],
            'lrrm_state': row[17] or 'UNKNOWN',
            'ipo_regime_state': row[18] or 'UNKNOWN',
            'lrrm_data_ready': bool(row[17] and row[17] != 'UNKNOWN'),
            'ipo_regime_data_ready': bool(row[18] and row[18] != 'UNKNOWN'),
            'data_ready': bool(row[17] and row[17] != 'UNKNOWN' and row[18] and row[18] != 'UNKNOWN'),
        }
    except (sqlite3.Error, TypeError, ValueError, ZoneInfoNotFoundError) as exc:
        logger.error(f"[DB Get Daily Sentiment As-Of Error] {exc}")
        return None
    finally:
        conn.close()

def get_sentiment_dates(limit: int = 120) -> list[str]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    dates = []
    try:
        cur.execute("SELECT date FROM daily_sentiment ORDER BY date DESC LIMIT ?", (limit,))
        dates = [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"[DB Sentiment Dates Query Error] {e}")
    finally:
        conn.close()
    return dates

