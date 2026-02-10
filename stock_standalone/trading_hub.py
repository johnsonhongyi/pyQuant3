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
    entry_price: float = 0.0         # 实际成交价
    exit_price: float = 0.0          # 实际离场价
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
                entry_price REAL DEFAULT 0.0,
                exit_price REAL DEFAULT 0.0,
                target_price_low REAL,
                target_price_high REAL,
                stop_loss REAL,
                status TEXT DEFAULT 'TRACKING',
                priority INTEGER DEFAULT 5,
                source TEXT,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # --- [FIX] 自动热迁移：检查 follow_queue 缺失字段 ---
        try:
            c.execute("PRAGMA table_info(follow_queue)")
            columns = [col[1] for col in c.fetchall()]
            if 'entry_price' not in columns:
                logger.info("[TradingHub] Migrating follow_queue: adding entry_price")
                c.execute("ALTER TABLE follow_queue ADD COLUMN entry_price REAL DEFAULT 0.0")
            if 'exit_price' not in columns:
                logger.info("[TradingHub] Migrating follow_queue: adding exit_price")
                c.execute("ALTER TABLE follow_queue ADD COLUMN exit_price REAL DEFAULT 0.0")
        except Exception as e:
            logger.error(f"[TradingHub] Migration error for follow_queue: {e}")

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
        
        # 持仓记录表 (同样建议检查此表)
        try:
            c.execute("PRAGMA table_info(positions)")
            columns = [col[1] for col in c.fetchall()]
            if 'strategy' not in columns:
                 c.execute("ALTER TABLE positions ADD COLUMN strategy TEXT")
        except: pass
        
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
        
        # [FIX] 显式列名查询，防止 SELECT * 导致的索引偏移 (could not convert string to float: 'TRACKING')
        fields = [
            "id", "code", "name", "signal_type", "detected_date", "detected_price",
            "entry_strategy", "entry_price", "exit_price", "target_price_low",
            "target_price_high", "stop_loss", "status", "priority", "source", "notes"
        ]
        query_cols = ", ".join(fields)
        
        if status:
            c.execute(f"SELECT {query_cols} FROM follow_queue WHERE status = ? ORDER BY priority DESC, detected_date", (status,))
        else:
            c.execute(f"SELECT {query_cols} FROM follow_queue WHERE status != 'EXITED' AND status != 'CANCELLED' ORDER BY priority DESC, detected_date")
        
        rows = c.fetchall()
        conn.close()
        
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        signals = []
        for row in rows:
            try:
                # 显式索引绑定 (0-15)
                signals.append(TrackedSignal(
                    id=row[0], 
                    code=str(row[1]), 
                    name=str(row[2]) if row[2] else "", 
                    signal_type=str(row[3]) if row[3] else "",
                    detected_date=str(row[4]) if row[4] else "", 
                    detected_price=safe_float(row[5]), 
                    entry_strategy=str(row[6]) if row[6] else "竞价买入",
                    entry_price=safe_float(row[7]), 
                    exit_price=safe_float(row[8]),
                    target_price_low=safe_float(row[9]), 
                    target_price_high=safe_float(row[10]), 
                    stop_loss=safe_float(row[11]),
                    status=str(row[12]) if row[12] else "TRACKING", 
                    priority=int(row[13] or 5), 
                    source=str(row[14]) if row[14] else "", 
                    notes=str(row[15]) if row[15] else ""
                ))
            except Exception as e:
                logger.error(f"[TradingHub] Error parsing follow queue row {row[0] if len(row)>0 else 'unknown'}: {e}")
                continue
        return signals
    
    def update_follow_status(self, code: str, new_status: str = None, notes: str = None, 
                            exit_price: float = None, exit_date: str = None) -> bool:
        """
        更新跟单状态
        
        Args:
            code: 股票代码
            new_status: 新状态 (TRACKING/READY/ENTERED/EXITED/CANCELLED)
            notes: 备注信息
            exit_price: 离场价格 (仅在 EXITED 状态时使用)
            exit_date: 离场日期 (仅在 EXITED 状态时使用,格式: YYYY-MM-DD HH:MM:SS)
        """
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 构建动态 SQL
            update_fields = []
            update_values = []
            
            if new_status:
                update_fields.append("status = ?")
                update_values.append(new_status)
            
            if notes:
                update_fields.append("notes = ?")
                update_values.append(notes)
            
            if exit_price is not None:
                update_fields.append("exit_price = ?")
                update_values.append(exit_price)
            
            # [NEW] 支持离场日期记录
            if exit_date:
                # 检查表中是否有 exit_date 列,如果没有则添加
                try:
                    c.execute("SELECT exit_date FROM follow_queue LIMIT 1")
                except sqlite3.OperationalError:
                    # 列不存在,添加它
                    c.execute("ALTER TABLE follow_queue ADD COLUMN exit_date TEXT")
                    conn.commit()
                
                update_fields.append("exit_date = ?")
                update_values.append(exit_date)
            
            # 总是更新 updated_at
            update_fields.append("updated_at = ?")
            update_values.append(now)
            
            if not update_fields:
                # Nothing to update
                conn.close()
                return True
            
            # 执行更新
            sql = f"UPDATE follow_queue SET {', '.join(update_fields)} WHERE code = ?"
            update_values.append(code)
            c.execute(sql, tuple(update_values))
            
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
    
    def cleanup_stale_signals(self, max_days: int = 2, current_prices: Dict[str, float] = None, check_breakout: bool = False) -> Dict[str, List[str]]:
        """
        清理过期的跟单信号与热点跟踪，支持价格波动清理(不及预期/破位)
        
        规则:
        1. TRACKING/READY 状态超过 max_days 天未入场 → CANCELLED
        2. [NEW] TRACKING/READY 状态如果当前价 < detected_price * 0.93 (跌超7%破位) → CANCELLED
        3. [OPTIONAL] check_breakout=True 时，3天内无中阳启动突破 → CANCELLED
        4. ENTERED 状态超过 max_days*2 天未更新 → STALE
        5. Hotlist (follow_record) 中 ACTIVE 状态超过 max_days 天 → CANCELLED
        6. [NEW] Hotlist 状态如果当前价 < follow_price * 0.93 或跌破 stop_loss → CANCELLED
        
        Args:
            max_days: 最大等待天数
            current_prices: {code: price} 或 {code: {price, percent, volume, high4}} 实时行情字典
            check_breakout: 是否检查"3天内无中阳突破"（手动清理选项）
            
        Returns:
            Dict[str, List[str]]: 清理详情 {status: [name(code), ...]}
        """
        results = {"CANCEL_SIGNAL": [], "STALE_SIGNAL": [], "CANCEL_HOTLIST": []}
        try:
            conn = sqlite3.connect(self.signal_db)
            c = conn.cursor()
            now = datetime.now()
            
            # 1. 整理 follow_queue (跟单队列)
            c.execute("""
                SELECT id, code, name, detected_date, detected_price, status, stop_loss
                FROM follow_queue 
                WHERE status IN ('TRACKING', 'READY', 'ENTERED')
            """)
            queue_rows = c.fetchall()
            
            for row in queue_rows:
                q_id, code, name, det_date_str, det_price, status, stop_loss = row
                curr_price = current_prices.get(code) if current_prices else None
                
                # --- 时间清理 ---
                days_elapsed = -1
                if det_date_str:
                    try:
                        dt = datetime.strptime(det_date_str, '%Y-%m-%d %H:%M:%S') if ' ' in det_date_str else datetime.strptime(det_date_str, '%Y-%m-%d')
                        days_elapsed = (now - dt).days
                    except: pass

                should_cleanup = False
                reason = ""

                if status in ('TRACKING', 'READY'):
                    # [OPTIONAL] 3天内无中阳突破强制清理（仅手动触发）
                    if check_breakout and days_elapsed >= 3:
                        if curr_price:
                            # 检查是否有中阳启动迹象
                            if isinstance(curr_price, dict):
                                stock_info = curr_price
                                pct = stock_info.get('percent', 0)
                                vol = stock_info.get('volume', 0)
                                high4 = stock_info.get('high4', 0)
                                price = stock_info.get('price', 0)
                                
                                # 中阳启动定义：涨幅>=4% 且 放量>=1.3 且 突破high4
                                has_breakout = (pct >= 4.0 and vol >= 1.3 and price > high4 > 0)
                                
                                if not has_breakout:
                                    should_cleanup = True
                                    reason = "3天内无中阳启动突破"
                            else:
                                # 兼容旧价格格式：由于手动选择了强制清理，且已超3天且非字典格式（无法判断启动），保守清理
                                should_cleanup = True
                                reason = "3天内无启动(数据源受限)"
                        else:
                            # 如果手动强制清理且没有实时价格（说明已掉出活跃榜），且已超3天，视为不活跃信号直接清理
                            should_cleanup = True
                            reason = "3天内无启动(已掉出活跃榜)"
                    
                    # 时间清理（如果未被3天规则触发）
                    if not should_cleanup and days_elapsed > max_days:
                        should_cleanup = True
                        reason = f"时间超{max_days}d"
                    
                    # 破位清理
                    if not should_cleanup and curr_price:
                        price_val = curr_price if isinstance(curr_price, (int, float)) else curr_price.get('price', 0) if isinstance(curr_price, dict) else 0
                        if price_val > 0:
                            # 破位逻辑: 跌超 7% 或 跌破止损
                            if det_price > 0 and price_val < det_price * 0.93:
                                should_cleanup = True
                                reason = "不及预期(跌>7%)"
                            elif stop_loss and stop_loss > 0 and price_val < stop_loss:
                                should_cleanup = True
                                reason = "破位止损"

                    if should_cleanup:
                        c.execute("UPDATE follow_queue SET status='CANCELLED', notes=COALESCE(notes,'')||' | 自动清理:'||?, updated_at=? WHERE id=?",
                                 (reason, now.strftime('%Y-%m-%d %H:%M:%S'), q_id))
                        results["CANCEL_SIGNAL"].append(f"{name}({code}) - {reason}")
                        logger.info(f"[TradingHub] Auto-cleanup Signal: {code} {name} CANCELLED ({reason})")

                elif status == 'ENTERED':
                    stale_limit = max_days * 2
                    if days_elapsed > stale_limit:
                        c.execute("UPDATE follow_queue SET status='STALE', notes=COALESCE(notes,'')||' | 自动清理:过期', updated_at=? WHERE id=?",
                                 (now.strftime('%Y-%m-%d %H:%M:%S'), q_id))
                        results["STALE_SIGNAL"].append(f"{name}({code}) - 过期")
                        logger.info(f"[TradingHub] Auto-cleanup Signal: {code} {name} STALE (>2d)")


            conn.commit()
            conn.close()
            return results
            
        except Exception as e:
            logger.error(f"[TradingHub] Cleanup error: {e}")
            return results


    
    def check_db_integrity(self) -> bool:
        """
        检查数据库完整性
        
        Returns:
            True: 数据库正常
            False: 数据库损坏
        """
        try:
            conn = sqlite3.connect(self.signal_db, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result[0] == 'ok'
        except Exception as e:
            logger.error(f"[TradingHub] DB integrity check failed: {e}")
            return False
    
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
        
        # [FIX] 显式列名查询，防止索引偏移
        fields = [
            "id", "code", "name", "entry_date", "entry_price", "quantity", 
            "current_price", "pnl_percent", "status", "strategy", "notes"
        ]
        query_cols = ", ".join(fields)
        
        c.execute(f"SELECT {query_cols} FROM positions WHERE status = ? ORDER BY entry_date DESC", (status,))
        rows = c.fetchall()
        conn.close()
        
        def safe_float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        positions = []
        for row in rows:
            positions.append(Position(
                id=row[0], 
                code=str(row[1]), 
                name=str(row[2]) if row[2] else "", 
                entry_date=str(row[3]) if row[3] else "",
                entry_price=safe_float(row[4]), 
                quantity=int(row[5] or 0), 
                current_price=safe_float(row[6]),
                pnl_percent=safe_float(row[7]), 
                status=str(row[8]) if row[8] else "HOLDING", 
                strategy=str(row[9]) if row[9] else "", 
                notes=str(row[10]) if row[10] else ""
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
    
    def get_slippage_analysis(self, days: int = 30) -> pd.DataFrame:
        """
        计算入场滑点分析 (detected_price vs entry_price)
        
        Returns:
            DataFrame with columns:
            - code, name, signal_type
            - detected_price: 信号触发价格
            - entry_price: 实际买入价格
            - slippage_pct: 滑点百分比 ((entry - detected) / detected * 100)
            - slippage_direction: '追高' or '低吸' or '准确'
        """
        conn = sqlite3.connect(self.signal_db)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Join follow_queue and positions on code
        query = """
            SELECT 
                fq.code, fq.name, fq.signal_type,
                fq.detected_price, fq.detected_date,
                p.entry_price, p.entry_date, p.pnl_percent, p.status
            FROM follow_queue fq
            INNER JOIN positions p ON fq.code = p.code
            WHERE fq.detected_date >= ?
              AND p.entry_price > 0
              AND fq.detected_price > 0
            ORDER BY fq.detected_date DESC
        """
        
        df = pd.read_sql_query(query, conn, params=(start_date,))
        conn.close()
        
        if df.empty:
            return df
        
        # Calculate slippage
        df['slippage_pct'] = (df['entry_price'] - df['detected_price']) / df['detected_price'] * 100
        
        # Classify slippage direction
        def classify_slippage(pct):
            if pct > 1.0:
                return '追高'
            elif pct < -1.0:
                return '低吸'
            else:
                return '准确'
        
        df['slippage_direction'] = df['slippage_pct'].apply(classify_slippage)
        
        return df
    
    def get_slippage_summary(self, days: int = 30) -> Dict[str, Any]:
        """获取滑点统计摘要"""
        df = self.get_slippage_analysis(days)
        
        if df.empty:
            return {
                'total_entries': 0,
                'avg_slippage_pct': 0.0,
                'chase_high_count': 0,
                'accurate_count': 0,
                'catch_low_count': 0,
                'by_signal_type': {}
            }
        
        summary = {
            'total_entries': len(df),
            'avg_slippage_pct': float(df['slippage_pct'].mean()),
            'chase_high_count': len(df[df['slippage_direction'] == '追高']),
            'accurate_count': len(df[df['slippage_direction'] == '准确']),
            'catch_low_count': len(df[df['slippage_direction'] == '低吸']),
        }
        
        # By signal type
        by_signal = df.groupby('signal_type').agg({
            'slippage_pct': 'mean',
            'code': 'count'
        }).rename(columns={'code': 'count'}).to_dict('index')
        
        summary['by_signal_type'] = by_signal
        
        return summary
    
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
