# -*- coding: utf-8 -*-
"""
统一交易数据中心 (TradingHub)

整合所有碎片化数据：
- signal_strategy.db: 信号、跟踪记录
- trading_signals.db: 交易、选股历史

提供统一的数据访问接口，支持：
1. 待跟单队列管理
2. 持仓跟踪
3. 策略绩效统计
4. 每日盈亏分析

Created: 2026-01-23
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import pandas as pd

from JohnsonUtil import LoggerFactory
logger: logging.Logger = LoggerFactory.getLogger()


class FollowStatus(Enum):
    """跟单状态枚举"""
    TRACKING = "TRACKING"      # 跟踪中，等待入场时机
    READY = "READY"            # 入场时机出现
    ENTERED = "ENTERED"        # 已入场
    EXITED = "EXITED"          # 已离场
    CANCELLED = "CANCELLED"    # 已取消


class EntryStrategy(Enum):
    """入场策略枚举"""
    AUCTION = "竞价买入"        # 集合竞价买入
    PULLBACK_MA5 = "回踩MA5"    # 盘中回踩5日线
    PULLBACK_MA10 = "回踩MA10"  # 盘中回踩10日线
    BREAKOUT = "突破买入"       # 放量突破买入
    MANUAL = "手动入场"         # 手动决策


@dataclass
class TrackedSignal:
    """待跟单信号"""
    code: str
    name: str
    signal_type: str           # 信号类型(突破/低开走高/连阳等)
    detected_date: str         # 首次扫到日期
    detected_price: float      # 扫到时价格
    entry_strategy: str = "竞价买入"  # 入场策略
    target_price_low: float = 0.0    # 目标入场价下限
    target_price_high: float = 0.0   # 目标入场价上限
    stop_loss: float = 0.0           # 止损价
    status: str = "TRACKING"         # 状态
    priority: int = 5                # 优先级(1-10)
    source: str = ""                 # 来源策略
    notes: str = ""                  # 备注
    id: Optional[int] = None


@dataclass
class Position:
    """持仓记录"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    quantity: int = 0
    current_price: float = 0.0
    pnl_percent: float = 0.0
    status: str = "HOLDING"          # HOLDING/CLOSED
    strategy: str = ""               # 入场策略
    notes: str = ""
    id: Optional[int] = None


class TradingHub:
    """统一交易数据中心"""
    
    # 数据库路径
    SIGNAL_DB = "signal_strategy.db"
    TRADING_DB = "trading_signals.db"
    
    def __init__(self, signal_db: str = None, trading_db: str = None):
        self.signal_db = signal_db or self.SIGNAL_DB
        self.trading_db = trading_db or self.TRADING_DB
        self._init_tables()
    
    def _init_tables(self):
        """初始化新增表结构"""
        conn = sqlite3.connect(self.signal_db)
        c = conn.cursor()
        
        # 待跟单队列表
        c.execute("""
            CREATE TABLE IF NOT EXISTS follow_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT,
                signal_type TEXT,
                detected_date TEXT,
                detected_price REAL,
                entry_strategy TEXT DEFAULT '竞价买入',
                target_price_low REAL,
                target_price_high REAL,
                stop_loss REAL,
                status TEXT DEFAULT 'TRACKING',
                priority INTEGER DEFAULT 5,
                source TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(code, detected_date)
            )
        """)
        
        # 持仓记录表
        c.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT,
                entry_date TEXT,
                entry_price REAL,
                quantity INTEGER DEFAULT 0,
                current_price REAL,
                pnl_percent REAL,
                status TEXT DEFAULT 'HOLDING',
                strategy TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 每日盈亏统计表
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_pnl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                total_pnl REAL DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                notes TEXT
            )
        """)
        
        # 策略绩效统计表
        c.execute("""
            CREATE TABLE IF NOT EXISTS strategy_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                date TEXT NOT NULL,
                total_signals INTEGER DEFAULT 0,
                entered INTEGER DEFAULT 0,
                win_count INTEGER DEFAULT 0,
                loss_count INTEGER DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                win_rate REAL DEFAULT 0,
                avg_profit REAL DEFAULT 0,
                avg_loss REAL DEFAULT 0,
                UNIQUE(strategy_name, date)
            )
        """)
        
        # 创建索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_fq_status ON follow_queue(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_fq_code ON follow_queue(code)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status)")
        
        conn.commit()
        conn.close()
        logger.info("[TradingHub] Tables initialized")
    
    # =========== 待跟单队列管理 ===========
    
    def add_to_follow_queue(self, signal: TrackedSignal) -> bool:
        """添加信号到待跟单队列"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # [FIX] Truncate time to minute or check existence to prevent second-level duplicates
            # Policy: One signal per code per day? Or per minute?
            # Let's align with unique constraint: We should reuse the same row for the same day unless it's a diff signal.
            # But the UNIQUE index is (code, detected_date). If detected_date has seconds, it's useless for dedup.
            
            # Use Day string for dedup check
            day_str = datetime.now().strftime("%Y-%m-%d")
            
            # Check if exists for today
            c.execute("SELECT id FROM follow_queue WHERE code=? AND detected_date LIKE ?", (signal.code, f"{day_str}%"))
            row = c.fetchone()
            
            if row:
                # Update existing
                c.execute("""
                    UPDATE follow_queue 
                    SET signal_type=?, detected_price=?, status=?, updated_at=?, notes=?
                    WHERE id=?
                """, (signal.signal_type, signal.detected_price, signal.status, now, signal.notes, row[0]))
            else:
                # Insert new
                c.execute("""
                    INSERT INTO follow_queue 
                    (code, name, signal_type, detected_date, detected_price,
                     entry_strategy, target_price_low, target_price_high, stop_loss,
                     status, priority, source, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    signal.code, signal.name, signal.signal_type,
                    now, signal.detected_price,
                    signal.entry_strategy, signal.target_price_low, signal.target_price_high,
                    signal.stop_loss, signal.status, signal.priority,
                    signal.source, signal.notes, now, now
                ))
            
            conn.commit()
            conn.close()
            logger.info(f"[TradingHub] Added to follow queue: {signal.code} {signal.name}")
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Add to follow queue error: {e}")
            return False
    
    def delete_from_follow_queue(self, code: str) -> bool:
        """从跟单队列中物理删除"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            c.execute("DELETE FROM follow_queue WHERE code = ?", (code,))
            rows_affected = c.rowcount
            conn.commit()
            conn.close()
            
            if rows_affected > 0:
                logger.info(f"[TradingHub] Deleted from follow queue: {code}")
                return True
            return False
        except Exception as e:
            logger.error(f"[TradingHub] Delete from follow queue error: {e}")
            return False

    def get_follow_queue(self, status: str = None) -> List[TrackedSignal]:
        """获取待跟单队列"""
        conn = sqlite3.connect(self.signal_db)
        c = conn.cursor()
        
        if status:
            c.execute("SELECT * FROM follow_queue WHERE status = ? ORDER BY priority DESC, detected_date", (status,))
        else:
            c.execute("SELECT * FROM follow_queue WHERE status != 'EXITED' AND status != 'CANCELLED' ORDER BY priority DESC, detected_date")
        
        rows = c.fetchall()
        conn.close()
        
        signals = []
        for row in rows:
            signals.append(TrackedSignal(
                id=row[0], code=row[1], name=row[2], signal_type=row[3],
                detected_date=row[4], detected_price=row[5], entry_strategy=row[6],
                target_price_low=row[7], target_price_high=row[8], stop_loss=row[9],
                status=row[10], priority=row[11], source=row[12], notes=row[13]
            ))
        return signals
    
    def update_follow_status(self, code: str, new_status: str = None, notes: str = None) -> bool:
        """更新跟单状态"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if new_status and notes:
                c.execute("UPDATE follow_queue SET status = ?, notes = ?, updated_at = ? WHERE code = ?",
                         (new_status, notes, now, code))
            elif new_status:
                c.execute("UPDATE follow_queue SET status = ?, updated_at = ? WHERE code = ?",
                         (new_status, now, code))
            elif notes:
                c.execute("UPDATE follow_queue SET notes = ?, updated_at = ? WHERE code = ?",
                         (notes, now, code))
            else:
                # Nothing to update
                conn.close()
                return True
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update follow status error: {e}")
            return False
    
    def get_follow_queue_df(self) -> pd.DataFrame:
        """获取待跟单队列(DataFrame格式)"""
        conn = sqlite3.connect(self.signal_db)
        df = pd.read_sql_query(
            "SELECT * FROM follow_queue WHERE status NOT IN ('EXITED', 'CANCELLED') ORDER BY priority DESC",
            conn
        )
        conn.close()
        return df
    
    # =========== 持仓管理 ===========
    
    def add_position(self, position: Position) -> bool:
        """添加持仓记录"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            c.execute("""
                INSERT INTO positions 
                (code, name, entry_date, entry_price, quantity, current_price,
                 pnl_percent, status, strategy, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.code, position.name, position.entry_date, position.entry_price,
                position.quantity, position.current_price, position.pnl_percent,
                position.status, position.strategy, position.notes, now, now
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"[TradingHub] Added position: {position.code}")
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Add position error: {e}")
            return False
    
    def get_positions(self, status: str = "HOLDING") -> List[Position]:
        """获取持仓列表"""
        conn = sqlite3.connect(self.signal_db)
        c = conn.cursor()
        c.execute("SELECT * FROM positions WHERE status = ? ORDER BY entry_date DESC", (status,))
        rows = c.fetchall()
        conn.close()
        
        positions = []
        for row in rows:
            positions.append(Position(
                id=row[0], code=row[1], name=row[2], entry_date=row[3],
                entry_price=row[4], quantity=row[5], current_price=row[6],
                pnl_percent=row[7], status=row[8], strategy=row[9], notes=row[10]
            ))
        return positions
    
    def update_position_price(self, code: str, current_price: float) -> bool:
        """更新持仓现价和盈亏"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            
            # 获取入场价
            c.execute("SELECT entry_price FROM positions WHERE code = ? AND status = 'HOLDING'", (code,))
            row = c.fetchone()
            if not row:
                conn.close()
                return False
            
            entry_price = row[0]
            pnl_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            c.execute("""
                UPDATE positions SET current_price = ?, pnl_percent = ?, updated_at = ?
                WHERE code = ? AND status = 'HOLDING'
            """, (current_price, pnl_pct, now, code))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update position price error: {e}")
            return False
    
    # =========== 绩效统计 ===========
    
    def get_strategy_performance(self, strategy_name: str = None, days: int = 30) -> pd.DataFrame:
        """获取策略绩效统计"""
        conn = sqlite3.connect(self.signal_db)
        
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        if strategy_name:
            df = pd.read_sql_query(
                "SELECT * FROM strategy_stats WHERE strategy_name = ? AND date >= ? ORDER BY date DESC",
                conn, params=(strategy_name, start_date)
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM strategy_stats WHERE date >= ? ORDER BY date DESC",
                conn, params=(start_date,)
            )
        
        conn.close()
        return df
    
    def update_strategy_stats(self, strategy_name: str, date: str, 
                              signals: int, entered: int, wins: int, losses: int, pnl: float):
        """更新策略绩效"""
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            
            total = wins + losses
            win_rate = wins / total if total > 0 else 0
            
            c.execute("""
                INSERT OR REPLACE INTO strategy_stats 
                (strategy_name, date, total_signals, entered, win_count, loss_count, total_pnl, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (strategy_name, date, signals, entered, wins, losses, pnl, win_rate))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update strategy stats error: {e}")
            return False
    
    def get_daily_pnl(self, days: int = 30) -> pd.DataFrame:
        """获取每日盈亏统计"""
        conn = sqlite3.connect(self.signal_db)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM daily_pnl WHERE date >= ? ORDER BY date DESC",
            conn, params=(start_date,)
        )
        conn.close()
        return df
    
    # =========== 跨库数据访问 ===========
    
    def get_trading_history(self, days: int = 30) -> pd.DataFrame:
        """从 trading_signals.db 获取交易历史"""
        conn = sqlite3.connect(self.trading_db)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM trade_records WHERE buy_date >= ? ORDER BY buy_date DESC",
            conn, params=(start_date,)
        )
        conn.close()
        return df
    
    def get_signal_history(self, days: int = 7) -> pd.DataFrame:
        """从 signal_strategy.db 获取信号历史"""
        conn = sqlite3.connect(self.signal_db)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM signal_message WHERE created_date >= ? ORDER BY created_date DESC, priority DESC",
            conn, params=(start_date,)
        )
        conn.close()
        return df
    
    
    def get_unified_dashboard(self) -> Dict[str, Any]:
        """获取统一仪表盘数据"""
        return {
            "follow_queue_count": len(self.get_follow_queue()),
            "tracking_count": len(self.get_follow_queue(status="TRACKING")),
            "ready_count": len(self.get_follow_queue(status="READY")),
            "positions_count": len(self.get_positions()),
            "today_signals": len(self.get_signal_history(days=1)),
        }
        
    def sync_from_logger(self) -> int:
        """
        [Sync] 从 legacy trading_logger 同步持仓状态
        返回同步的持仓数量
        """
        try:
            # 1. Read from Legacy DB
            conn_legacy = sqlite3.connect(self.trading_db)
            legacy_df = pd.read_sql_query("SELECT * FROM trade_records WHERE status='OPEN'", conn_legacy)
            conn_legacy.close()
            
            if legacy_df.empty:
                return 0
                
            # 2. Upsert into Hub DB
            conn_hub = sqlite3.connect(self.signal_db)
            c = conn_hub.cursor()
            
            synced_count = 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for _, row in legacy_df.iterrows():
                code = row['code']
                # Check if exists
                c.execute("SELECT id FROM positions WHERE code=? AND status='HOLDING'", (code,))
                exists = c.fetchone()
                
                if not exists:
                    # Insert
                    c.execute("""
                        INSERT INTO positions 
                        (code, name, entry_date, entry_price, quantity, current_price, pnl_percent, status, strategy, notes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        code, row['name'], row['buy_date'], row['buy_price'], 
                        row['buy_amount'], row['buy_price'], 0.0, 
                        'HOLDING', row.get('buy_reason', ''), 'Synced from Logger',
                        now, now
                    ))
                    synced_count += 1
                else:
                    # Optional: Update fields if needed
                    pass
            
            conn_hub.commit()
            conn_hub.close()
            logger.info(f"[TradingHub] Synced {synced_count} positions from Logger.")
            return synced_count
            
        except Exception as e:
            logger.error(f"[TradingHub] Sync error: {e}")
            return 0


# 单例模式
_hub_instance: Optional[TradingHub] = None

def get_trading_hub() -> TradingHub:
    """获取 TradingHub 单例"""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = TradingHub()
    return _hub_instance


if __name__ == "__main__":
    # 测试
    hub = get_trading_hub()
    
    # 测试添加跟单
    signal = TrackedSignal(
        code="601212",
        name="白银有色",
        signal_type="连阳加速",
        detected_date="2026-01-06",
        detected_price=12.50,
        entry_strategy="竞价买入",
        target_price_low=12.30,
        target_price_high=12.80,
        stop_loss=11.80,
        priority=8,
        source="热点面板"
    )
    hub.add_to_follow_queue(signal)
    
    # 查看队列
    queue = hub.get_follow_queue()
    print(f"跟单队列: {len(queue)} 条")
    for s in queue:
        print(f"  - {s.code} {s.name} [{s.status}] {s.entry_strategy}")
    
    # 仪表盘
    dashboard = hub.get_unified_dashboard()
    print(f"\n仪表盘: {dashboard}")
