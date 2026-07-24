# -*- coding: utf-8 -*-
"""
Strategy Self Evolution Engine (策略自适应自我进化引擎)

1. 在线与离线闭环追溯买入信号的 T+1、T+3 实际表现绩效
2. 自动评估策略 Setup 近期胜率 (Win Rate) 与盈亏比 (Profit-Loss Ratio)
3. 实施动态权重调优与线上自动熔断/降级 (Auto Throttling & Blacklisting)
4. 防止失灵策略重复盲买
"""

from __future__ import annotations

import os
import sqlite3
import pandas as pd
from typing import Dict, Any, Tuple, List
from pathlib import Path
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("StrategySelfEvolution")

DEFAULT_DB_PATH = Path(r"D:\JohnsonProgram\instockMonitorTK\trading_signals.db")


class StrategySelfEvolution:
    """策略自适应与绩效闭环追踪器"""

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            db_path = DEFAULT_DB_PATH
        self.db_path = Path(db_path)
        self._ensure_table_exists()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_table_exists(self) -> None:
        """确保 signal_performance_journal 绩效追踪表存在"""
        try:
            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS signal_performance_journal (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        code TEXT NOT NULL,
                        name TEXT,
                        setup TEXT NOT NULL,
                        mining_score REAL DEFAULT 0.0,
                        entry_price REAL NOT NULL,
                        t1_high_price REAL,
                        t1_close_price REAL,
                        t3_high_price REAL,
                        t3_close_price REAL,
                        t1_max_pnl_pct REAL,
                        t1_close_pnl_pct REAL,
                        t3_max_pnl_pct REAL,
                        t3_close_pnl_pct REAL,
                        is_win INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'PENDING',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"初始化 signal_performance_journal 数据表失败: {e}")

    def record_signal(
        self,
        timestamp: str,
        code: str,
        name: str,
        setup: str,
        entry_price: float,
        mining_score: float = 0.0
    ) -> bool:
        """记录产生的买入信号以便后续追溯绩效"""
        if entry_price <= 0:
            return False
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO signal_performance_journal (
                        timestamp, code, name, setup, mining_score, entry_price, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                """, (timestamp, code, name, setup, mining_score, entry_price))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"记录信号失败 ({code}/{setup}): {e}")
            return False

    def update_performance(
        self,
        record_id: int,
        t1_high: float,
        t1_close: float,
        t3_high: float = 0.0,
        t3_close: float = 0.0
    ) -> bool:
        """更新信号的真实 T+1 / T+3 价格绩效"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT entry_price FROM signal_performance_journal WHERE id = ?", (record_id,))
                row = cursor.fetchone()
                if not row or row[0] <= 0:
                    return False
                
                entry_price = float(row[0])
                t1_max_pnl = round(((t1_high - entry_price) / entry_price) * 100.0, 2)
                t1_close_pnl = round(((t1_close - entry_price) / entry_price) * 100.0, 2)
                
                t3_max_pnl = round(((t3_high - entry_price) / entry_price) * 100.0, 2) if t3_high > 0 else 0.0
                t3_close_pnl = round(((t3_close - entry_price) / entry_price) * 100.0, 2) if t3_close > 0 else 0.0

                is_win = 1 if (t1_max_pnl >= 2.0 or t1_close_pnl > 0.0) else 0

                cursor.execute("""
                    UPDATE signal_performance_journal SET
                        t1_high_price = ?,
                        t1_close_price = ?,
                        t3_high_price = ?,
                        t3_close_price = ?,
                        t1_max_pnl_pct = ?,
                        t1_close_pnl_pct = ?,
                        t3_max_pnl_pct = ?,
                        t3_close_pnl_pct = ?,
                        is_win = ?,
                        status = 'EVALUATED'
                    WHERE id = ?
                """, (t1_high, t1_close, t3_high, t3_close, t1_max_pnl, t1_close_pnl, t3_max_pnl, t3_close_pnl, is_win, record_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新绩效失败 ID={record_id}: {e}")
            return False

    def evaluate_strategy_win_rates(self, sample_size: int = 50) -> Dict[str, Dict[str, Any]]:
        """
        按策略 Setup 评估近期的实际胜率与收益期望
        """
        result = {}
        try:
            with self._get_connection() as conn:
                query = f"""
                    SELECT setup, COUNT(*) as total_count,
                           SUM(is_win) as win_count,
                           AVG(t1_close_pnl_pct) as avg_pnl
                    FROM (
                        SELECT * FROM signal_performance_journal
                        WHERE status = 'EVALUATED'
                        ORDER BY id DESC LIMIT {sample_size}
                    )
                    GROUP BY setup
                """
                df = pd.read_sql_query(query, conn)
                for _, row in df.iterrows():
                    setup = str(row['setup'])
                    total = int(row['total_count'])
                    wins = int(row['win_count']) if pd.notnull(row['win_count']) else 0
                    avg_pnl = float(row['avg_pnl']) if pd.notnull(row['avg_pnl']) else 0.0
                    win_rate = round(wins / total, 4) if total > 0 else 0.5
                    
                    result[setup] = {
                        "total_count": total,
                        "win_count": wins,
                        "win_rate": win_rate,
                        "avg_pnl_pct": round(avg_pnl, 2),
                        "is_blacklisted": win_rate < 0.25 and total >= 5,
                        "threshold_adjustment": 0.15 if (win_rate < 0.40 and total >= 5) else 0.0
                    }
        except Exception as e:
            logger.error(f"评估策略胜率异常: {e}")

        return result

    def is_strategy_blacklisted(self, setup: str) -> Tuple[bool, str]:
        """
        判断某个策略 Setup 是否因近期胜率过低而触发线上熔断黑名单
        """
        stats = self.evaluate_strategy_win_rates(sample_size=30)
        if setup in stats:
            info = stats[setup]
            if info.get("is_blacklisted", False):
                reason = f"⚠️ [策略自动熔断] Setup={setup} 近期胜率仅 {info['win_rate']:.1%} (样本{info['total_count']}次), 触发黑名单禁买"
                return True, reason
        return False, ""
