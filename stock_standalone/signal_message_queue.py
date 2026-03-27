import sqlite3
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from queue import PriorityQueue
from typing import List, Optional, Dict, Any
from threading import Lock
import os
from trading_logger import TradingLogger
from db_utils import SQLiteConnectionManager

logger = logging.getLogger(__name__)

DB_FILE = "signal_strategy.db"

@dataclass(order=True)
class SignalMessage:
    """
    信号消息数据类
    order=True 使得 PriorityQueue 可以根据 priority 排序 (默认第一个字段)
    """
    priority: int  # 优先级 (数值越小优先级越高, e.g. 1=Top1, 100=Low)
    timestamp: str = field(compare=False)
    code: str = field(compare=False)
    name: str = field(compare=False)
    signal_type: str = field(compare=False)  # HOT_WATCH / USER_SELECT / STRATEGY / ALERT / CONSOLIDATION
    source: str = field(compare=False)       # HOT_LIST / SELECTOR / DECISION_ENGINE / VOICE
    reason: str = field(compare=False)
    score: float = field(compare=False)
    evaluated: bool = field(default=False, compare=False)
    followed: bool = field(default=False, compare=False)
    count: int = field(default=1, compare=False)  # 当日触发计数（热度）
    consecutive_days: int = field(default=1, compare=False)  # 连续天数
    rank: int = field(default=0, compare=False) # [NEW] 当时排名
    grade: str = field(default='', compare=False) # [NEW] 走势评级 (S/A/B/C)
    # 扩展字段，不参与比较
    extra: Dict[str, Any] = field(default_factory=dict, compare=False)

    def to_dict(self):
        return asdict(self)

class SignalMessageQueue:
    """
    全局信号消息队列 (线程安全单例)
    - 内存中保持 Top N 条高优先级信号
    - 所有信号持久化到 SQLite
    """
    _instance = None
    _lock = Lock()
    
    MAX_SIZE = 120 # [OPTIMIZED] 提升缓存容量，防止高频行情下信号在 UI 列表中被过快挤掉
    FOLLOW_LIMIT = 5

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self._queue = PriorityQueue()
        # 内存缓存，用于快速 UI 展示 (已排序列表)
        self._cached_top: List[SignalMessage] = []
        
        # 使用统一的 DB Manager
        self.db_manager = SQLiteConnectionManager.get_instance(DB_FILE)
        
        self._init_db()
        
        self._init_db()
        self._load_from_db() # 启动时从 DB 加载最近的数据
        
        self.trading_logger = TradingLogger() # [NEW] 用于全量历史记录
        
        self._initialized = True
        logger.info("SignalMessageQueue initialized.")

    def _init_db(self):
        """初始化独立数据库"""
        try:
            conn = self.db_manager.get_connection()
            c = conn.cursor()
            
            # 信号消息表
            c.execute("""
                CREATE TABLE IF NOT EXISTS signal_message (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT,
                    signal_type TEXT NOT NULL,
                    source TEXT,
                    priority INTEGER DEFAULT 50,
                    score REAL,
                    reason TEXT,
                    evaluated INTEGER DEFAULT 0,
                    created_date TEXT,
                    count INTEGER DEFAULT 1,
                    consecutive_days INTEGER DEFAULT 1,
                    rank INTEGER DEFAULT 0,
                    grade TEXT
                )
            """)
            
            # 跟单记录表
            c.execute("""
                CREATE TABLE IF NOT EXISTS follow_record (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    code TEXT NOT NULL,
                    name TEXT,
                    follow_date TEXT,
                    follow_price REAL,
                    stop_loss REAL,
                    status TEXT DEFAULT 'ACTIVE',
                    exit_date TEXT,
                    exit_price REAL,
                    pnl_pct REAL,
                    feedback TEXT,
                    FOREIGN KEY (signal_id) REFERENCES signal_message(id)
                )
            """)
            
            # 索引
            c.execute("CREATE INDEX IF NOT EXISTS idx_signal_date ON signal_message (created_date)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_signal_code ON signal_message (code)")
            
            # Migration checks
            try:
                c.execute("ALTER TABLE signal_message ADD COLUMN count INTEGER DEFAULT 1")
            except sqlite3.OperationalError: pass
            
            try:
                c.execute("ALTER TABLE signal_message ADD COLUMN consecutive_days INTEGER DEFAULT 1")
            except sqlite3.OperationalError: pass

            try:
                c.execute("ALTER TABLE signal_message ADD COLUMN rank INTEGER DEFAULT 0")
            except sqlite3.OperationalError: pass
            
            try:
                c.execute("ALTER TABLE signal_message ADD COLUMN grade TEXT")
            except sqlite3.OperationalError: pass
            
            conn.commit()
            # Cursor closed by connection reuse or garbage collection, but explicit close is better if not using context manager everywhere
            c.close()

        except Exception as e:
            logger.error(f"Failed to init signal_strategy.db: {e}")

    def _load_from_db(self):
        """从数据库加载最近的未评估信号到内存"""
        try:
            conn = self.db_manager.get_connection()
            # conn.row_factory = sqlite3.Row # This might affect other threads if not careful, but manager uses thread-local
            # To be safe, we can use a context manager or just set it temporarily if needed, 
            # OR just assume standard tuple and map manually, OR use dict_factory.
            # Let's use the execute_query context manager which returns a cursor.
            
            old_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
            
            c = conn.cursor()
            c.execute("SELECT * FROM signal_message ORDER BY id DESC LIMIT 50")
            rows = c.fetchall()
            c.close()
            
            conn.row_factory = old_factory
                
            for row in rows:
                msg = SignalMessage(
                    priority=row['priority'],
                    timestamp=row['timestamp'],
                    code=row['code'],
                    name=row['name'],
                    signal_type=row['signal_type'],
                    source=row['source'],
                    reason=row['reason'],
                    score=row['score'],
                    evaluated=bool(row['evaluated']),
                    count=row['count'] if 'count' in row.keys() else 1,
                    consecutive_days=row['consecutive_days'] if 'consecutive_days' in row.keys() else 1,
                    rank=row['rank'] if 'rank' in row.keys() else 0,
                    grade=row['grade'] if 'grade' in row.keys() else ''
                )
                # 放入队列
                self._queue.put(msg) 
                
            self._update_cache()
                
        except Exception as e:
            logger.error(f"Failed to load form db: {e}")

    def push(self, msg: SignalMessage) -> None:
        """推送新信号 (严格去重: 同股票+同策略只保留一条)"""
        # [NEW] 记录到全量历史 (DB)
        try:
            self.trading_logger.log_live_signal(
                msg.code, msg.name, 
                price=msg.extra.get('price', 0.0), 
                action=msg.signal_type, 
                reason=msg.reason,
                indicators=msg.extra
            )
        except Exception as e:
            logger.error(f"Failed to log live history in push: {e}")

        with self._lock:
            # 1. 提取当前所有 items
            items = []
            while not self._queue.empty():
                items.append(self._queue.get())
            
            # 2. 检查重复 (同代码、同策略，不限日期)
            # msg.timestamp 格式: "YYYY-MM-DD HH:MM:SS"
            msg_date = msg.timestamp.split(" ")[0]
            found_idx = -1
            
            for i, item in enumerate(items):
                if (item.code == msg.code and 
                    item.signal_type == msg.signal_type):
                    found_idx = i
                    break
            
            if found_idx >= 0:
                # 已存在该股票的信号
                existing = items[found_idx]
                existing_date = existing.timestamp.split(" ")[0]
                
                if existing_date == msg_date:
                    # 同一天: 增加热度计数
                    existing.count += 1
                    existing.timestamp = msg.timestamp # 更新时间到最新 (置顶)
                    existing.score = msg.score         # 更新分数
                    existing.reason = msg.reason       # 更新理由
                    existing.priority = min(existing.priority, msg.priority)
                    existing.rank = msg.rank           # [NEW] 更新排名
                else:
                    # 次日触发: 增加连续天数，重置当日计数
                    existing.consecutive_days += 1
                    existing.count = 1  # 重置为1（新的一天第一次触发）
                    existing.timestamp = msg.timestamp
                    existing.score = msg.score
                    existing.reason = msg.reason
                    existing.priority = min(existing.priority, msg.priority)
                    existing.rank = msg.rank           # [NEW] 更新排名
                
                # DB Update
                self._update_db_signal(existing)
            else:
                # 新增
                msg.count = 1
                msg.consecutive_days = 1
                items.append(msg)
                
                # DB Insert
                self._persist_signal(msg)
            
            # 3. 排序 (Priority ASC, Timestamp DESC)
            # 这里的排序为了 _update_cache 的正确性
            # 使用辅助函数 pk_timestamp_desc
            items.sort(key=lambda x: (x.priority, pk_timestamp_desc(x.timestamp)))
            
            # Re-enqueue all (we will truncate in _update_cache via get_top logic if needed, 
            # but actually PriorityQueue just needs to hold them. 
            # The cache handles the truncation only for display)
            # Wait, PriorityQueue length IS limited? No, logic says MAX_SIZE is for cache?
            # Original code truncated items in _update_cache before putting back.
            # So we should truncate here too to keep memory small?
            # Yes, let's keep MAX_SIZE items.
            
            # 此时 items 已经排好序 (Top is index 0)
            kept_items = items[:self.MAX_SIZE]
            
            for item in kept_items:
                self._queue.put(item)
            
            self._cached_top = kept_items

    def _update_cache(self):
        """
        更新内存缓存列表
        注意: push() 中已经维护了 cache 和 queue 的一致性。
        这个方法主要用于 load_from_db 后的初始化，或者其他非 push 的更新(如 mark_evaluated)
        """
        items = []
        while not self._queue.empty():
            items.append(self._queue.get())
            
        # Sort
        items.sort(key=lambda x: (x.priority, pk_timestamp_desc(x.timestamp)))
        
        kept_items = items[:self.MAX_SIZE]
        
        for item in kept_items:
            self._queue.put(item)
            
        self._cached_top = kept_items

    def _persist_signal(self, msg: SignalMessage):
        """持久化到数据库 (Insert)"""
        try:
            # --- [交易日和交易时段检查] ---
            try:
                from JohnsonUtil import commonTips as cct
                is_trade_day = cct.get_trade_date_status()
                now_time_int = cct.get_now_time_int()
                is_trading_time = (930 <= now_time_int <= 1130) or (1300 <= now_time_int <= 1500)
                if not is_trade_day or not is_trading_time:
                    return
            except Exception:
                pass  # 检查失败则允许写入
            
            created_date = msg.timestamp.split(" ")[0] if " " in msg.timestamp else msg.timestamp
            self.db_manager.execute_update("""
                INSERT INTO signal_message (
                    timestamp, code, name, signal_type, source, 
                    priority, score, reason, evaluated, count, consecutive_days, rank, grade, created_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.timestamp, msg.code, msg.name, msg.signal_type, msg.source,
                msg.priority, msg.score, msg.reason, int(msg.evaluated), msg.count, msg.consecutive_days, msg.rank, msg.grade, created_date
            ))
        except Exception as e:
            logger.error(f"Failed to persist signal: {e}")

    def _update_db_signal(self, msg: SignalMessage):
        """更新数据库中的信号 (Count, Timestamp等)"""
        try:
            # --- [交易日和交易时段检查] ---
            try:
                from JohnsonUtil import commonTips as cct
                is_trade_day = cct.get_trade_date_status()
                now_time_int = cct.get_now_time_int()
                is_trading_time = (930 <= now_time_int <= 1130) or (1300 <= now_time_int <= 1500)
                if not is_trade_day or not is_trading_time:
                    return
            except Exception:
                pass  # 检查失败则允许写入
            
            created_date = msg.timestamp.split(" ")[0] if " " in msg.timestamp else msg.timestamp
            self.db_manager.execute_update("""
                UPDATE signal_message
                SET timestamp = ?, score = ?, reason = ?, priority = ?, count = ?, consecutive_days = ?, rank = ?, grade = ?, created_date = ?
                WHERE code = ? AND signal_type = ?
            """, (
                msg.timestamp, msg.score, msg.reason, msg.priority, msg.count, msg.consecutive_days, msg.rank, msg.grade, created_date,
                msg.code, msg.signal_type
            ))
        except Exception as e:
            logger.error(f"Failed to update db signal: {e}")

    def update_signal_rank(self, code: str, signal_type: str, rank: int):
        """更新信号的 Rank (用于补全)"""
        updated = False
        with self._lock:
            # 1. 更新内存缓存 (Queue 里的很难改，只能改 cache，或者全部重载? 
            # PriorityQueue 里的 item 是 mutable dataclass，只要引用还在就可以改。
            # 但从 Queue 里取出来的难度较大。
            # 我们主要更新 _cached_top，这是 get_top() 的来源，用于 UI 显示)
            for item in self._cached_top:
                if item.code == code and item.signal_type == signal_type:
                    item.rank = rank
                    updated = True
                    # 注意：如果 Queue 里存的是同一个对象引用，那么 Queue 里的也变了。
                    # 通常是的。
        
        if updated:
            # 2. 更新数据库
            try:
                self.db_manager.execute_update("""
                    UPDATE signal_message 
                    SET rank = ? 
                    WHERE code = ? AND signal_type = ?
                """, (rank, code, signal_type))
            except Exception as e:
                logger.error(f"Failed to update signal rank: {e}")

    def get_top(self) -> List[SignalMessage]:
        """获取展示用的 Top 列表"""
        return self._cached_top

    def mark_evaluated(self, code: str, signal_type: str = None):
        """标记已评估"""
        updated = False
        for msg in self._cached_top:
            if msg.code == code and (signal_type is None or msg.signal_type == signal_type):
                msg.evaluated = True
                updated = True
        
        if updated:
            # 更新数据库状态
            try:
                self.db_manager.execute_update("""
                    UPDATE signal_message 
                    SET evaluated = 1 
                    WHERE code = ? AND id = (SELECT max(id) FROM signal_message WHERE code = ?)
                """, (code, code))
            except Exception as e:
                logger.error(f"Failed to update evaluated status: {e}")

    def add_follow(self, msg: SignalMessage, price: float, stop_loss: float):
        """添加到跟单 (DB only, 内存可根据需要扩展)"""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = self.db_manager.get_connection()
            c = conn.cursor()
            
            # 查找对应的 signal id
            c.execute("SELECT max(id) FROM signal_message WHERE code = ?", (msg.code,))
            row = c.fetchone()
            sig_id = row[0] if row else None
            
            c.execute("""
                INSERT INTO follow_record (
                    signal_id, code, name, follow_date, follow_price, stop_loss, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE')
            """, (sig_id, msg.code, msg.name, now, price, stop_loss))
            conn.commit()
            c.close()
            msg.followed = True
        except Exception as e:
            logger.error(f"Failed to add follow record: {e}")

    def get_active_follows(self) -> List[Dict]:
        """获取当前活跃跟单"""
        results = []
        try:
            conn = self.db_manager.get_connection()
            # Temporary set row factory
            old_factory = conn.row_factory
            conn.row_factory = sqlite3.Row
            
            c = conn.cursor()
            c.execute("SELECT * FROM follow_record WHERE status = 'ACTIVE' ORDER BY id DESC")
            rows = c.fetchall()
            c.close()
            
            conn.row_factory = old_factory
            
            for r in rows:
                results.append(dict(r))
        except Exception as e:
            logger.error(f"Failed to get active follows: {e}")
        return results

    def clean_duplicates_in_db(self) -> int:
        """
        清理数据库中的重复信号 (同代码+同类型 全局只保留最后一条)
        Uses SQLiteConnectionManager for thread-safe access.
        """
        deleted_count = 0
        try:
            conn = self.db_manager.get_connection()
            c = conn.cursor()
            
            # 1. 查找所有应该保留的 ID
            c.execute("""
                SELECT MAX(id) as keep_id
                FROM signal_message
                GROUP BY code, signal_type
            """)
            keep_ids = [row[0] for row in c.fetchall() if row[0] is not None]
            
            if keep_ids:
                # 2. 删除不在保留列表中的记录
                placeholders = ','.join(['?' for _ in keep_ids])
                c.execute(f"""
                    DELETE FROM signal_message
                    WHERE id NOT IN ({placeholders})
                """, keep_ids)
                deleted_count = c.rowcount
                conn.commit()
            
            c.close()
            
            if deleted_count > 0:
                logger.info(f"[SignalQueue] 清理了 {deleted_count} 条重复信号")
                # 重新加载缓存
                self._queue = PriorityQueue()
                self._cached_top = []
                self._load_from_db()

        except Exception as e:
            logger.error(f"[SignalQueue] 清理重复信号失败: {e}")
            
        return deleted_count

    def log_live_signal_direct(self, code: str, name: str, pattern: str, score: float, msg: str, is_high_priority: bool):
        """
        直接记录实时信号到数据库，绕过队列 (供 stock_live_strategy 使用以减少延迟和锁)
        自动处理更新计数逻辑
        """
        try:
            # --- [交易日和交易时段检查] ---
            try:
                from JohnsonUtil import commonTips as cct
                is_trade_day = cct.get_trade_date_status()
                now_time_int = cct.get_now_time_int()
                # 交易时段: 09:30-11:30 (930-1130) 和 13:00-15:00 (1300-1500)
                is_trading_time = (930 <= now_time_int <= 1130) or (1300 <= now_time_int <= 1500)
                
                if not is_trade_day or not is_trading_time:
                    # logger.debug(f"SignalQueue: 非交易日或非交易时段(trade_day={is_trade_day}, time={now_time_int}),跳过记录 {code} {pattern}")
                    return
            except Exception as check_e:
                logger.debug(f"SignalQueue: 交易日/时段检查失败 (fallback to allow): {check_e}")
            
            
            now_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            now_date = datetime.now().strftime('%Y-%m-%d')
            priority_value = 100 if is_high_priority else 50
            
            conn = self.db_manager.get_connection()
            c = conn.cursor()
            
            # 检查是否已存在同日同股同信号类型
            c.execute("""
                SELECT id, count FROM signal_message 
                WHERE code = ? AND signal_type = ? AND source = 'live_strategy' AND created_date = ?
                LIMIT 1
            """, (code, pattern, now_date))
            existing = c.fetchone()
            
            if existing:
                # 已存在：更新计数和时间戳
                new_count = existing[1] + 1
                c.execute("""
                    UPDATE signal_message 
                    SET timestamp = ?, count = ?, priority = ?, reason = ?
                    WHERE id = ?
                """, (now_timestamp, new_count, priority_value, msg, existing[0]))
                # logger.debug(f"✅ Live signal updated in DB: {code} - {pattern} (count={new_count})")
            else:
                # 不存在：插入新记录
                c.execute("""
                    INSERT INTO signal_message (timestamp, code, name, signal_type, source, priority, score, reason, evaluated, created_date, count, consecutive_days, grade)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (now_timestamp, code, name, pattern, 'live_strategy', priority_value, score, msg, 0, now_date, 1, 1, ''))
                # logger.debug(f"✅ Live signal saved to DB: {code} - {pattern}")
            
            conn.commit()
            c.close()

        except Exception as db_err:
            logger.error(f"Failed to log_live_signal_direct to DB: {db_err}")

def pk_timestamp_desc(ts):
    """辅助排序 Key: 将 timestamp 字符串反转以实现 DESC 排序效果(针对 sort ASC)"""
    try:
        dt = datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
        return -dt.timestamp()
    except:
        return 0

