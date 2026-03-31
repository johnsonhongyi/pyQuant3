# -*- coding:utf-8 -*-
"""
Market Pulse Database Layer
Responsible for persisting daily market reports and hot stock details.
File: market_pulse_db.py
"""
import sqlite3
import json
import traceback
from datetime import datetime
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger("MarketPulseDB")
DB_PATH = "./market_pulse.db"

def init_pulse_db():
    """Initialize the Market Pulse database tables."""
    try:
        conn = sqlite3.connect(DB_PATH)
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
        conn.close()
        logger.info("[DB] Market Pulse tables initialized.")
    except Exception as e:
        logger.error(f"[DB Init Error] {e}")
        traceback.print_exc()

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
    init_pulse_db()
    conn = sqlite3.connect(DB_PATH)
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
        
    except Exception as e:
        logger.error(f"[DB Save Error] {e}")
        traceback.print_exc()
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
