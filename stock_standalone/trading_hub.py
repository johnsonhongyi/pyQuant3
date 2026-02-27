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
import pandas as pd
from datetime import datetime, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum

from JohnsonUtil import LoggerFactory
from db_utils import SQLiteConnectionManager

logger: logging.Logger = LoggerFactory.getLogger()


class FollowStatus(Enum):
    """跟单状态枚举"""
    WATCHING = "WATCHING"      # 观察中（热股跨日验证）
    VALIDATED = "VALIDATED"    # 验证通过，待晋升跟单
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
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
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
        
        # 热股观察表 — 跨日验证 (P0核心)
        c.execute("""
            CREATE TABLE IF NOT EXISTS hot_stock_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                name TEXT,
                sector TEXT,
                discover_date TEXT,
                discover_price REAL,
                latest_price REAL,
                trend_score REAL DEFAULT 0,
                volume_score REAL DEFAULT 0,
                new_high_flag INTEGER DEFAULT 0,
                consecutive_strong INTEGER DEFAULT 0,
                validation_status TEXT DEFAULT 'WATCHING',
                daily_patterns TEXT,      -- [NEW] 记录日线形态描述
                pattern_score REAL DEFAULT 0, -- [NEW] 形态打分
                source TEXT,              -- [NEW] 来源标识
                drop_reason TEXT,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(code, discover_date)
            )
        """)
        
        # --- [NEW] 热迁移：为 hot_stock_watchlist 增加形态支撑字段 ---
        try:
            c.execute("PRAGMA table_info(hot_stock_watchlist)")
            columns = [col[1] for col in c.fetchall()]
            if 'daily_patterns' not in columns:
                c.execute("ALTER TABLE hot_stock_watchlist ADD COLUMN daily_patterns TEXT")
            if 'pattern_score' not in columns:
                c.execute("ALTER TABLE hot_stock_watchlist ADD COLUMN pattern_score REAL DEFAULT 0")
            if 'source' not in columns:
                c.execute("ALTER TABLE hot_stock_watchlist ADD COLUMN source TEXT")
            conn.commit()
        except: pass
        
        # 创建索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_fq_status ON follow_queue(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_fq_code ON follow_queue(code)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hw_status ON hot_stock_watchlist(validation_status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hw_code ON hot_stock_watchlist(code)")
        
        conn.commit()
        logger.info("[TradingHub] Tables initialized")
    
    # =========== 待跟单队列管理 ===========
    
    def add_to_follow_queue(self, signal: TrackedSignal) -> bool:
        """添加信号到待跟单队列"""
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
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
            logger.info(f"[TradingHub] Added to follow queue: {signal.code} {signal.name}")
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Add to follow queue error: {e}")
            return False
    
    def delete_from_follow_queue(self, code: str) -> bool:
        """从跟单队列中物理删除"""
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM follow_queue WHERE code = ?", (code,))
            rows_affected = c.rowcount
            conn.commit()
            
            if rows_affected > 0:
                logger.info(f"[TradingHub] Deleted from follow queue: {code}")
                return True
            return False
        except Exception as e:
            logger.error(f"[TradingHub] Delete from follow queue error: {e}")
            return False

    def get_follow_queue(self, status: str = None) -> list[TrackedSignal]:
        """获取待跟单队列"""
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        c = conn.cursor()
        
        # [FIX] 显式列名查询，防止 SELECT * 导致的索引偏移 (could not convert string to float: 'TRACKING')
        fields = [
            "id", "code", "name", "signal_type", "detected_date", "detected_price",
            "entry_strategy", "entry_price", "exit_price", "target_price_low",
            "target_price_high", "stop_loss", "status", "priority", "source", "notes"
        ]
        query_cols = ", ".join(fields)
        
        if status:
            if isinstance(status, (list, tuple)):
                placeholders = ", ".join(["?"] * len(status))
                c.execute(f"SELECT {query_cols} FROM follow_queue WHERE status IN ({placeholders}) ORDER BY priority DESC, detected_date", tuple(status))
            else:
                c.execute(f"SELECT {query_cols} FROM follow_queue WHERE status = ? ORDER BY priority DESC, detected_date", (status,))
        else:
            c.execute(f"SELECT {query_cols} FROM follow_queue WHERE status != 'EXITED' AND status != 'CANCELLED' ORDER BY priority DESC, detected_date")
        
        rows = c.fetchall()
        
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
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
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
                return True
            
            # 执行更新
            sql = f"UPDATE follow_queue SET {', '.join(update_fields)} WHERE code = ?"
            update_values.append(code)
            c.execute(sql, tuple(update_values))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update follow status error: {e}")
            return False
    
    def get_follow_queue_df(self) -> pd.DataFrame:
        """获取待跟单队列(DataFrame格式) - 去重版本
        
        去重规则:
        1. 同一股票(code)只保留一条记录
        2. 优先级: 优先级高 > 时间新 > 价格高
        3. 合并多个入场理由到 notes 字段
        """
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        
        # 使用窗口函数去重,保留每个股票的最优记录
        query = """
        WITH ranked_queue AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY code
                       ORDER BY priority DESC, detected_date DESC, detected_price DESC
                   ) as rn
            FROM follow_queue
            WHERE status NOT IN ('EXITED', 'CANCELLED')
        ),
        distinct_notes AS (
            SELECT DISTINCT code, notes, signal_type
            FROM follow_queue
            WHERE status NOT IN ('EXITED', 'CANCELLED')
              AND (notes IS NOT NULL AND notes != '')
        ),
        merged_notes AS (
            SELECT 
                code,
                GROUP_CONCAT(notes, '; ') as all_notes,
                GROUP_CONCAT(signal_type, ', ') as all_signal_types
            FROM distinct_notes
            GROUP BY code
        )
        SELECT 
            rq.*,
            COALESCE(mn.all_notes, rq.notes) as merged_notes,
            COALESCE(mn.all_signal_types, rq.signal_type) as merged_signal_types
        FROM ranked_queue rq
        LEFT JOIN merged_notes mn ON rq.code = mn.code
        WHERE rq.rn = 1
        ORDER BY rq.priority DESC, rq.detected_date DESC
        """
        
        df = pd.read_sql_query(query, conn)
        
        # 用合并后的理由替换原理由
        if not df.empty and 'merged_notes' in df.columns:
            df['notes'] = df['merged_notes']
            df['signal_type'] = df['merged_signal_types']
            df = df.drop(columns=['merged_notes', 'merged_signal_types', 'rn'], errors='ignore')
        
        return df

    def get_watchlist_df(self, status: str = None) -> pd.DataFrame:
        """获取热股观察池(DataFrame格式) - 去重版本
        
        去重规则:
        1. 同一股票(code)只保留一条记录
        2. 优先级: 趋势分数高 > 日期新 > 形态分数高
        3. 合并多个发现理由到 daily_patterns 字段
        """
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)
            conn = mgr.get_connection()
            
            # [FIX] 支持状态过滤
            status_filter = ""
            params = []
            if status:
                status_filter = "AND validation_status = ?"
                params.append(status)
            else:
                status_filter = "AND validation_status != 'DROPPED'"
                
            query = f"""
            WITH ranked_watchlist AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY code
                           ORDER BY trend_score DESC, discover_date DESC, pattern_score DESC
                       ) as rn
                FROM hot_stock_watchlist
                WHERE 1=1 {status_filter}
            ),
            distinct_patterns AS (
                SELECT DISTINCT code, daily_patterns
                FROM hot_stock_watchlist
                WHERE 1=1 {status_filter}
                  AND (daily_patterns IS NOT NULL AND daily_patterns != '')
            ),
            merged_patterns AS (
                SELECT 
                    code,
                    GROUP_CONCAT(daily_patterns, '; ') as all_patterns
                FROM distinct_patterns
                GROUP BY code
            )
            SELECT 
                rw.*,
                COALESCE(mp.all_patterns, rw.daily_patterns) as merged_patterns
            FROM ranked_watchlist rw
            LEFT JOIN merged_patterns mp ON rw.code = mp.code
            WHERE rw.rn = 1
            ORDER BY rw.discover_date DESC, rw.trend_score DESC
            LIMIT 200
            """
            
            df = pd.read_sql_query(query, conn, params=params)
            
            # 用合并后的形态描述替换原描述
            if not df.empty and 'merged_patterns' in df.columns:
                df['daily_patterns'] = df['merged_patterns']
                df = df.drop(columns=['merged_patterns', 'rn'], errors='ignore')
            
            return df
        except Exception as e:
            logger.error(f"[TradingHub] get_watchlist_df error: {e}")
            return pd.DataFrame()
    
    def cleanup_stale_signals(self, max_days: int = 2, current_prices: dict[str, float] = None, check_breakout: bool = False) -> dict[str, list[str]]:
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
            dict[str, list[str]]: 清理详情 {status: [name(code), ...]}
        """
        results = {"CANCEL_SIGNAL": [], "STALE_SIGNAL": [], "CANCEL_HOTLIST": [], "PURGED_WATCHLIST": 0}
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
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

            # 2. 队列容量压缩 (限额 100 只)
            # 获取当前队列中非 EXITED/CANCELLED 的总数
            c.execute("SELECT id, code, name, status, priority, detected_date FROM follow_queue WHERE status NOT IN ('EXITED', 'CANCELLED')")
            active_queue = c.fetchall()
            
            MAX_QUEUE_SIZE = 100
            if len(active_queue) > MAX_QUEUE_SIZE:
                # 排序优先级：
                # 1. 状态权重：STALE(1) > TRACKING(2) > READY(3) > ENTERED(4) -> 优先清理 STALE
                # 2. 业务优先级：priority 越低越优先清理
                # 3. 时间：时间越早越优先清理
                status_weight = {'STALE': 1, 'TRACKING': 2, 'READY': 3, 'ENTERED': 4}
                def sort_key(row):
                    # row: (id, code, name, status, priority, detected_date)
                    s_weight = status_weight.get(row[3], 99)
                    prio = row[4] or 5
                    # 转换时间为可以用作比较的格式
                    d_date = row[5] or "1970-01-01"
                    return (s_weight, prio, d_date)

                # 按权重从小到大排序，前面的是最该删除的
                sorted_queue = sorted(active_queue, key=sort_key)
                to_remove_count = len(active_queue) - MAX_QUEUE_SIZE
                to_remove = sorted_queue[:to_remove_count]
                
                for r_row in to_remove:
                    r_id, r_code, r_name, r_status, r_prio, r_date = r_row
                    reason = "队列扩容清理(限额100)"
                    c.execute("UPDATE follow_queue SET status='CANCELLED', notes=COALESCE(notes,'')||' | '||?, updated_at=? WHERE id=?",
                             (reason, now.strftime('%Y-%m-%d %H:%M:%S'), r_id))
                    results["CANCEL_SIGNAL"].append(f"{r_name}({r_code}) - {reason} [{r_status}]")
                    logger.info(f"[TradingHub] Queue Limit Cleanup: {r_code} {r_name} CANCELLED")

            # 4. [NEW] 清理 hot_stock_watchlist (观察池)
            # 物理删除: 已淘汰(DROPPED)或已入场(PROMOTED/EXITED) 超过3天的记录，以及长时间无进展的记录
            purge_date_3d = (now - timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
            purge_date_7d = (now - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
            
            # --- 物理清理冗余状态 ---
            c.execute("""
                DELETE FROM hot_stock_watchlist 
                WHERE (validation_status IN ('DROPPED', 'PROMOTED', 'EXITED', 'CANCELLED') AND updated_at < ?)
                   OR (validation_status = 'WATCHING' AND updated_at < ?)
            """, (purge_date_3d, purge_date_7d))
            
            purged_count = c.rowcount
            if purged_count > 0:
                logger.info(f"[TradingHub] Watchlist Purge: Deleted {purged_count} stale/dropped records.")
                results["PURGED_WATCHLIST"] = purged_count

            conn.commit()
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
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result[0] == 'ok'
        except Exception as e:
            logger.error(f"[TradingHub] DB integrity check failed: {e}")
            return False
    
    # =========== 持仓管理 ===========
    
    def add_position(self, position: Position) -> bool:
        """添加持仓记录"""
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
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
            logger.info(f"[TradingHub] Added position: {position.code}")
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Add position error: {e}")
            return False
    
    def get_positions(self, status: str = "HOLDING") -> list[Position]:
        """获取持仓列表"""
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        c = conn.cursor()
        
        # [FIX] 显式列名查询，防止索引偏移
        fields = [
            "id", "code", "name", "entry_date", "entry_price", "quantity", 
            "current_price", "pnl_percent", "status", "strategy", "notes"
        ]
        query_cols = ", ".join(fields)
        
        c.execute(f"SELECT {query_cols} FROM positions WHERE status = ? ORDER BY entry_date DESC", (status,))
        rows = c.fetchall()
        
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
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            
            # 获取入场价
            c.execute("SELECT entry_price FROM positions WHERE code = ? AND status = 'HOLDING'", (code,))
            row = c.fetchone()
            if not row:
                return False
            
            entry_price = row[0]
            pnl_pct = (current_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            c.execute("""
                UPDATE positions SET current_price = ?, pnl_percent = ?, updated_at = ?
                WHERE code = ? AND status = 'HOLDING'
            """, (current_price, pnl_pct, now, code))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update position price error: {e}")
            return False
    
    # =========== 绩效统计 ===========
    
    def get_strategy_performance(self, strategy_name: str = None, days: int = 30) -> pd.DataFrame:
        """获取策略绩效统计"""
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        
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
        
        return df
    
    def update_strategy_stats(self, strategy_name: str, date: str, 
                              signals: int, entered: int, wins: int, losses: int, pnl: float):
        """更新策略绩效"""
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            
            total = wins + losses
            win_rate = wins / total if total > 0 else 0
            
            c.execute("""
                INSERT OR REPLACE INTO strategy_stats 
                (strategy_name, date, total_signals, entered, win_count, loss_count, total_pnl, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (strategy_name, date, signals, entered, wins, losses, pnl, win_rate))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"[TradingHub] Update strategy stats error: {e}")
            return False
    
    def get_daily_pnl(self, days: int = 30) -> pd.DataFrame:
        """获取每日盈亏统计"""
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM daily_pnl WHERE date >= ? ORDER BY date DESC",
            conn, params=(start_date,)
        )
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
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
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
    
    def get_slippage_summary(self, days: int = 30) -> dict[str, Any]:
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
        mgr = SQLiteConnectionManager.get_instance(self.trading_db)

        conn = mgr.get_connection()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM trade_records WHERE buy_date >= ? ORDER BY buy_date DESC",
            conn, params=(start_date,)
        )
        return df
    
    def get_signal_history(self, days: int = 7) -> pd.DataFrame:
        """从 signal_strategy.db 获取信号历史"""
        mgr = SQLiteConnectionManager.get_instance(self.signal_db)

        conn = mgr.get_connection()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        df = pd.read_sql_query(
            "SELECT * FROM signal_message WHERE created_date >= ? ORDER BY created_date DESC, priority DESC",
            conn, params=(start_date,)
        )
        return df
    
    
    def get_unified_dashboard(self) -> dict[str, Any]:
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
            mgr_legacy = SQLiteConnectionManager.get_instance(self.trading_db)
            conn_legacy = mgr_legacy.get_connection()
            legacy_df = pd.read_sql_query("SELECT * FROM trade_records WHERE status='OPEN'", conn_legacy)
            conn_legacy.close()
            
            if legacy_df.empty:
                return 0
                
            # 2. Upsert into Hub DB
            mgr_hub = SQLiteConnectionManager.get_instance(self.signal_db)
            conn_hub = mgr_hub.get_connection()
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

    # =========== 热股观察队列管理 (P0: 跨日验证引擎) ===========

    def add_to_watchlist(self, code: str, name: str, sector: str, price: float,
                         source: str = "", daily_patterns: str = "", pattern_score: float = 0) -> bool:
        """
        全量归集：将各路选股结果写入观察队列（不直接跟单）
        """
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')

            # [REFACTOR] 智能去重：只要该股票在观察中（WATCHING/VALIDATED），就合并形态评分而不是新增行
            # 这样可以防止同一个股票因为多日被选中而在数据库中堆积多行记录
            c.execute("""
                SELECT id, daily_patterns, pattern_score FROM hot_stock_watchlist 
                WHERE code=? AND validation_status IN ('WATCHING', 'VALIDATED')
                ORDER BY discover_date DESC LIMIT 1
            """, (code,))
            row = c.fetchone()
            
            if row:
                # 如果已在队列中，更新其形态描述和评分（取最大值），更新活跃时间
                wid, old_patterns, old_score = row
                new_pts = old_patterns
                if daily_patterns and daily_patterns not in str(old_patterns):
                    new_pts = f"{old_patterns};{daily_patterns}" if old_patterns else daily_patterns
                
                new_score = max(old_score or 0, pattern_score)
                c.execute("""
                    UPDATE hot_stock_watchlist 
                    SET daily_patterns=?, pattern_score=?, latest_price=?, updated_at=?, sector=COALESCE(NULLIF(sector, ''), ?)
                    WHERE id=?
                """, (new_pts, new_score, price, now.strftime('%Y-%m-%d %H:%M:%S'), sector, wid))
                conn.commit()
                # logger.debug(f"[TradingHub] Watchlist Update: {code} {name} merged patterns.")
                return True

            c.execute("""
                INSERT INTO hot_stock_watchlist
                (code, name, sector, discover_date, discover_price, latest_price,
                 validation_status, daily_patterns, pattern_score, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'WATCHING', ?, ?, ?, ?, ?)
            """, (code, name, sector, today_str, price, price,
                  daily_patterns, pattern_score, source,
                  now.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')))

            conn.commit()
            logger.info(f"[TradingHub] Watchlist+: {code} {name} @{price:.2f} [{daily_patterns}] Score={pattern_score}")
            return True
        except Exception as e:
            logger.error(f"[TradingHub] add_to_watchlist error: {e}")
            return False

    def validate_watchlist(self, ohlc_data: dict[str, dict] = None) -> dict[str, list]:
        """
        跨日验证观察队列中的热股（收盘后调用）

        ohlc_data 格式: {
            'code': {
                'close': float, 'high': float, 'low': float, 'open': float,
                'ma5': float, 'ma10': float,
                'upper': float,   # Bollinger上轨
                'high4': float,   # 4日高点
                'volume_ratio': float,  # 量比
                'win': int,       # 连阳天数
            }
        }

        验证规则（对应实盘验证的强势股特征）:
        - 趋势确认: close > MA5 且 MA5 > MA10 → trend_score +0.3
        - Upper上轨: close >= upper * 0.98 → trend_score +0.3
        - 新高判断: close > high4 → new_high_flag = 1, +0.2
        - 量能: volume_ratio > 1.2 → volume_score = 0.2
        - 连阳: win >= 2 → +0.1
        
        验证通过: trend_score >= 0.5 AND consecutive_strong >= 1
        淘汰: 跌破MA10 或 跌破发现价*0.93

        Returns:
            {'validated': [...], 'dropped': [...], 'watching': [...]}
        """
        results = {'validated': [], 'dropped': [], 'watching': []}
        if not ohlc_data:
            return results

        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 获取所有 WATCHING 状态的热股
            c.execute("""
                SELECT id, code, name, sector, discover_price, trend_score,
                       volume_score, new_high_flag, consecutive_strong,
                       pattern_score, daily_patterns
                FROM hot_stock_watchlist
                WHERE validation_status = 'WATCHING'
            """)
            rows = c.fetchall()

            for row in rows:
                wid, code, name, sector, disc_price, prev_trend, prev_vol, prev_nh, prev_cs, pat_score, pat_desc = row

                data = ohlc_data.get(code)
                if not data:
                    continue

                close = float(data.get('close', 0))
                ma5 = float(data.get('ma5', 0))
                ma10 = float(data.get('ma10', 0))
                upper = float(data.get('upper', 0))
                high4 = float(data.get('high4', 0))
                vol_ratio = float(data.get('volume_ratio', 0))
                win = int(data.get('win', 0))

                if close <= 0:
                    continue

                # ======= 评分计算 (统一特征权重) =======
                trend_score = 0.0
                volume_score = 0.0
                new_high = 0

                # 1. 核心特征: 上轨攀升 (Upper Climb) - 权重置顶 0.4
                is_upper_climb = (upper > 0 and close >= upper * 0.98)
                if is_upper_climb:
                    trend_score += 0.4

                # 2. 核心特征: 新高判断 (New High) - 权重 0.3
                if high4 > 0 and close > high4:
                    new_high = 1
                    trend_score += 0.3

                # 3. 基础特征: MA5/MA10 趋势 (0.2)
                if ma5 > 0 and ma10 > 0 and close > ma5 and ma5 > ma10:
                    trend_score += 0.2

                # 4. 形态特征: 日线形态评分折算 (0-100 -> 0-0.3)
                if pat_score > 0:
                    trend_score += (pat_score / 333.0)  # max +0.3

                # 5. 量能验证 (0.1)
                if vol_ratio > 1.2:
                    volume_score = 0.1

                # 6. 连阳补充 (0.1)
                if win >= 3:
                    trend_score += 0.1

                total_score = trend_score + volume_score
                
                # [STRICT GATE] 强势股特征校验：如果没有上轨攀升且没有新高，且分值平平，由直接踢出或降级
                # 用于排除 600000 这种慢爬升但无溢价的大盘股
                is_high_momentum = is_upper_climb or new_high or (total_score >= 0.8)
                
                # ======= 淘汰检测 =======
                should_drop = False
                drop_reason = ""

                # 跌破 MA10 或 长期无动能
                if ma10 > 0 and close < ma10:
                    should_drop = True
                    drop_reason = f"跌破MA10({ma10:.2f})"
                elif not is_high_momentum and total_score < 0.5:
                    should_drop = True
                    drop_reason = "动能匮乏(无新高/非上轨)"
                elif disc_price > 0 and close < disc_price * 0.92:
                    should_drop = True
                    drop_reason = f"跌破入池价8%({disc_price:.2f}→{close:.2f})"

                if should_drop:
                    c.execute("""
                        UPDATE hot_stock_watchlist
                        SET validation_status='DROPPED', drop_reason=?,
                            latest_price=?, trend_score=?, volume_score=?,
                            new_high_flag=?, consecutive_strong=?, updated_at=?
                        WHERE id=?
                    """, (drop_reason, close, trend_score, volume_score,
                          new_high, prev_cs, now_str, wid))
                    results['dropped'].append(f"{name}({code}) - {drop_reason}")
                    logger.info(f"[TradingHub] Watchlist DROP: {code} {name} - {drop_reason}")

                elif total_score >= 0.7:  # [NEW GATE] 晋升门槛提高至 0.7
                    # 验证通过
                    c.execute("""
                        UPDATE hot_stock_watchlist
                        SET validation_status='VALIDATED',
                            latest_price=?, trend_score=?, volume_score=?,
                            new_high_flag=?, consecutive_strong=?, updated_at=?
                        WHERE id=?
                    """, (close, trend_score, volume_score,
                          new_high, prev_cs + 1, now_str, wid))
                    results['validated'].append(f"{name}({code}) Score={total_score:.2f}")
                    logger.info(f"[TradingHub] Watchlist VALIDATED: {code} {name} Score={total_score:.2f}")
                else:
                    # 继续观察
                    c.execute("""
                        UPDATE hot_stock_watchlist
                        SET latest_price=?, trend_score=?, volume_score=?,
                            new_high_flag=0, consecutive_strong=0, updated_at=?
                        WHERE id=?
                    """, (close, trend_score, volume_score, now_str, wid))
                    results['watching'].append(f"{name}({code}) Score={total_score:.2f}")

            conn.commit()
            logger.info(f"[TradingHub] Watchlist validation: "
                        f"validated={len(results['validated'])}, "
                        f"dropped={len(results['dropped'])}, "
                        f"watching={len(results['watching'])}")
        except Exception as e:
            logger.error(f"[TradingHub] validate_watchlist error: {e}")

        return results

    def promote_validated_stocks(self) -> list[str]:
        """
        将验证通过的热股晋升到跟单队列 (follow_queue)
        入场策略默认为"竞价买入" — 对应实盘验证的最优入场策略

        Returns:
            List of promoted stock codes
        """
        promoted = []
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            now = datetime.now()
            now_str = now.strftime('%Y-%m-%d %H:%M:%S')
            today_str = now.strftime('%Y-%m-%d')

            # 获取验证通过的热股
            c.execute("""
                SELECT id, code, name, sector, latest_price, trend_score,
                       new_high_flag, consecutive_strong, daily_patterns, source
                FROM hot_stock_watchlist
                WHERE validation_status = 'VALIDATED'
            """)
            rows = c.fetchall()

            for row in rows:
                wid, code, name, sector, price, trend_score, new_high, cs, patterns, orig_source = row

                # 检查 follow_queue 是否已存在（防重复）
                c.execute("SELECT id FROM follow_queue WHERE code=? AND status IN ('TRACKING','READY','ENTERED')",
                          (code,))
                if c.fetchone():
                    # 已在跟单队列，标记为 PROMOTED 避免重复处理
                    c.execute("UPDATE hot_stock_watchlist SET validation_status='PROMOTED', updated_at=? WHERE id=?",
                              (now_str, wid))
                    continue

                # 计算优先级（基于验证评分）
                priority = 5
                if trend_score >= 0.8:
                    priority = 12
                elif trend_score >= 0.5:
                    priority = 8
                if new_high:
                    priority += 2
                if cs >= 2:
                    priority += 1

                # 止损设定: 发现价 * 0.95
                stop_loss = price * 0.95

                # 组装详细备注 (P3 状态机核心：保留足迹)
                detail_notes = f"Score={trend_score:.2f} cs={cs} nh={new_high}"
                if patterns:
                    detail_notes += f" | 形态:{patterns}"
                if orig_source:
                    detail_notes += f" | 来源:{orig_source}"

                # 写入 follow_queue
                signal_type = f"验证晋升({sector})" if sector else "验证晋升"
                c.execute("""
                    INSERT INTO follow_queue
                    (code, name, signal_type, detected_date, detected_price,
                     entry_strategy, stop_loss, status, priority, source, notes,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, '竞价买入', ?, 'VALIDATED', ?, '热股验证', ?, ?, ?)
                """, (code, name, signal_type, today_str, price,
                      stop_loss, priority,
                      detail_notes,
                      now_str, now_str))

                # 更新 watchlist 状态
                c.execute("UPDATE hot_stock_watchlist SET validation_status='PROMOTED', updated_at=? WHERE id=?",
                          (now_str, wid))

                promoted.append(code)
                logger.info(f"[TradingHub] PROMOTED → follow_queue: {code} {name} "
                            f"priority={priority} strategy=竞价买入")

            conn.commit()
        except Exception as e:
            logger.error(f"[TradingHub] promote_validated_stocks error: {e}")

        return promoted

    def evaluate_holding_strength(self, ohlc_data: dict[str, dict] = None) -> dict[str, list]:
        """
        评估持仓股的强弱（收盘后调用，留强去弱）

        ohlc_data 格式同 validate_watchlist
        
        评估规则:
        - 站稳 MA5 + upper附近 → STRONG，持有
        - 跌破 MA5 + 缩量 → WARNING，次日观察
        - 跌破 MA10 或 冲高回落(最高涨>5%但收阴) → WEAK，降级/建议卖出

        Returns:
            {'strong': [...], 'warning': [...], 'weak': [...]}
        """
        results = {'strong': [], 'warning': [], 'weak': []}
        if not ohlc_data:
            return results

        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 获取持仓中的跟单 (ENTERED 状态)
            c.execute("""
                SELECT id, code, name, detected_price, entry_price, notes
                FROM follow_queue
                WHERE status = 'ENTERED'
            """)
            holdings = c.fetchall()

            for hold in holdings:
                fid, code, name, det_price, entry_price, notes = hold

                data = ohlc_data.get(code)
                if not data:
                    continue

                close = float(data.get('close', 0))
                high = float(data.get('high', 0))
                openp = float(data.get('open', 0))
                ma5 = float(data.get('ma5', 0))
                ma10 = float(data.get('ma10', 0))
                upper = float(data.get('upper', 0))
                vol_ratio = float(data.get('volume_ratio', 0))

                if close <= 0:
                    continue

                ref_price = entry_price if entry_price > 0 else det_price
                pnl_pct = ((close - ref_price) / ref_price * 100) if ref_price > 0 else 0

                # 冲高回落检测: 最高涨幅>5% 但收阴 (close < open)
                high_pct = ((high - openp) / openp * 100) if openp > 0 else 0
                is_pump_dump = high_pct > 5.0 and close < openp

                # ==== 弱势判断 ====
                if is_pump_dump:
                    reason = f"冲高回落(高点+{high_pct:.1f}%但收阴)"
                    results['weak'].append(f"{name}({code}) {reason} pnl={pnl_pct:+.1f}%")
                    # 更新 notes 记录降级原因
                    new_notes = f"{notes or ''} | 弱势:{reason}"
                    c.execute("UPDATE follow_queue SET notes=?, updated_at=? WHERE id=?",
                              (new_notes, now_str, fid))
                    logger.warning(f"[TradingHub] WEAK: {code} {name} - {reason}")

                elif ma10 > 0 and close < ma10:
                    reason = f"跌破MA10({ma10:.2f})"
                    results['weak'].append(f"{name}({code}) {reason} pnl={pnl_pct:+.1f}%")
                    new_notes = f"{notes or ''} | 弱势:{reason}"
                    c.execute("UPDATE follow_queue SET notes=?, updated_at=? WHERE id=?",
                              (new_notes, now_str, fid))
                    logger.warning(f"[TradingHub] WEAK: {code} {name} - {reason}")

                # ==== 警告 ====
                elif ma5 > 0 and close < ma5 and vol_ratio < 1.0:
                    reason = f"跌破MA5+缩量(量比={vol_ratio:.1f})"
                    results['warning'].append(f"{name}({code}) {reason} pnl={pnl_pct:+.1f}%")
                    logger.info(f"[TradingHub] WARNING: {code} {name} - {reason}")

                # ==== 强势 ====
                else:
                    flags = []
                    if ma5 > 0 and close > ma5:
                        flags.append("站稳MA5")
                    if upper > 0 and close >= upper * 0.98:
                        flags.append("Upper上轨")
                    reason = "+".join(flags) if flags else "趋势正常"
                    results['strong'].append(f"{name}({code}) {reason} pnl={pnl_pct:+.1f}%")

            conn.commit()
            logger.info(f"[TradingHub] Holding evaluation: "
                        f"strong={len(results['strong'])}, "
                        f"warning={len(results['warning'])}, "
                        f"weak={len(results['weak'])}")
        except Exception as e:
            logger.error(f"[TradingHub] evaluate_holding_strength error: {e}")

        return results

    def get_watchlist_summary(self) -> dict[str, Any]:
        """获取观察队列统计（供UI展示）"""
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            c.execute("""
                SELECT validation_status, COUNT(*) 
                FROM hot_stock_watchlist
                GROUP BY validation_status
            """)
            status_counts = dict(c.fetchall())

            # 最近验证通过的
            c.execute("""
                SELECT code, name, sector, trend_score, consecutive_strong
                FROM hot_stock_watchlist
                WHERE validation_status = 'VALIDATED'
                ORDER BY trend_score DESC
                LIMIT 10
            """)
            validated_top = [{
                'code': r[0], 'name': r[1], 'sector': r[2],
                'score': r[3], 'cs': r[4]
            } for r in c.fetchall()]

            return {
                'status_counts': status_counts,
                'validated_top': validated_top,
                'total': sum(status_counts.values())
            }
        except Exception as e:
            logger.error(f"[TradingHub] get_watchlist_summary error: {e}")
            return {'status_counts': {}, 'validated_top': [], 'total': 0}

    
    def batch_update_watchlist_sectors(self, df_all: pd.DataFrame) -> int:
        """
        批量更新 watchlist 中的板块信息
        
        Args:
            df_all: 主数据框,包含 category 字段
            
        Returns:
            更新的记录数
        """
        try:
            mgr = SQLiteConnectionManager.get_instance(self.signal_db)

            conn = mgr.get_connection()
            c = conn.cursor()
            
            # 获取所有需要更新板块信息的记录
            c.execute("""
                SELECT code FROM hot_stock_watchlist 
                WHERE validation_status != 'DROPPED'
                AND (sector IS NULL OR sector = '')
            """)
            codes_to_update = [row[0] for row in c.fetchall()]
            
            if not codes_to_update:
                return 0
            
            updated_count = 0
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            for code in codes_to_update:
                # 从 df_all 中获取板块信息
                if code in df_all.index:
                    row = df_all.loc[code]
                    category = str(row.get('category', ''))
                    
                    if category:
                        # 取第一个板块作为主板块
                        sectors = category.split(';')
                        main_sector = sectors[0] if sectors else ''
                        
                        if main_sector:
                            c.execute("""
                                UPDATE hot_stock_watchlist 
                                SET sector = ?, updated_at = ?
                                WHERE code = ?
                            """, (main_sector, now, code))
                            updated_count += 1
            
            conn.commit()
            
            if updated_count > 0:
                logger.info(f"[TradingHub] Batch updated {updated_count} watchlist sectors")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"[TradingHub] batch_update_watchlist_sectors error: {e}")
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
