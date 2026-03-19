import os
import sqlite3
import json
import logging
from datetime import datetime
from typing import Any, Optional
import pandas as pd
# 处理 override 装饰器 (Python 3.12+ 才有)
try:
    from typing import override # type: ignore
except ImportError:
    def override(func):
        return func

import numpy as np
from JohnsonUtil import LoggerFactory
from db_utils import SQLiteConnectionManager
from logger_utils import  with_log_level
# LoggerFactory.getLogger() 返回的类型通过注解明确
logger: logging.Logger = LoggerFactory.getLogger()

class NumpyEncoder(json.JSONEncoder):
    """
    专门用于处理 Numpy 数据类型的 JSON Encoder
    """
    @override
    def default(self, o):
        if isinstance(o, np.integer):
            return int(o)
        elif isinstance(o, np.floating):
            return float(o)
        elif isinstance(o, np.ndarray):
            return o.tolist()
        return super(NumpyEncoder, self).default(o)

class TradingLogger:
    """
    交易记录与信号持久化类
    使用 SQLite 存储每日决策、执行记录及收益统计
    """
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            from JohnsonUtil import commonTips as cct
            db_path = os.path.join(cct.get_base_path(), "trading_signals.db")
        self.db_path = db_path
        self._signal_cache = {} # (code, action) -> timestamp
        # Unified DB Manager
        self.db_manager = SQLiteConnectionManager.get_instance(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            
            
            # 1. 信号记录表 (每日每只票的决策快照)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signal_history (
                    date TEXT,
                    code TEXT,
                    name TEXT,
                    price REAL,
                    action TEXT,
                    position REAL,
                    reason TEXT,
                    indicators TEXT, -- JSON 格式存储当时的 MA, MACD, Structure 等指标
                    resample TEXT DEFAULT 'd', -- 周期标识: 'd', '3d', 'w', 'm'
                    PRIMARY KEY (date, code, resample)
                )
            """)
            
            # 2. 交易执行与持仓统计表 (用于计算盈利)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT,
                    name TEXT,
                    buy_date TEXT,
                    buy_price REAL,
                    buy_amount REAL, -- 股数
                    buy_reason TEXT, -- 买入理由
                    sell_date TEXT,
                    sell_price REAL,
                    sell_reason TEXT, -- 卖出理由
                    fee REAL,        -- 手续费累计
                    profit REAL,     -- 净利润
                    pnl_pct REAL,    -- 盈亏比例
                    status TEXT,     -- 'OPEN' or 'CLOSED'
                    feedback TEXT,   -- 策略反馈 (用户点评)
                    resample TEXT DEFAULT 'd', -- 周期标识
                    action TEXT      -- [新增] 交易动作类型 (买入, ADD, 卖出等)
                )
            """)
            conn.commit()
            # 3. 每日选股记录表 (StockSelector 结果)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS selection_history (
                    date TEXT,
                    code TEXT,
                    name TEXT,
                    score REAL,
                    price REAL,
                    percent REAL,
                    ratio REAL,
                    volume REAL,
                    amount REAL,
                    reason TEXT,
                    status TEXT,
                    grade TEXT, -- 新增分级 (S, A, B, C)
                    tqi REAL,   -- 新增趋势质量分
                    ma5 REAL,
                    ma10 REAL,
                    category TEXT,
                    resample TEXT DEFAULT 'd', -- 周期标识
                    PRIMARY KEY (date, code, resample)
                )
            """)

            # 4. 语音预警配置表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS voice_alerts (
                    code TEXT,
                    resample TEXT DEFAULT 'd', -- 周期标识
                    name TEXT,
                    rules TEXT, -- JSON
                    last_alert REAL,
                    created_time TEXT,
                    tags TEXT,
                    added_date TEXT,
                    rule_type_tag TEXT,
                    PRIMARY KEY (code, resample)
                )
            """)

            # 5. 实时信号全量历史追踪表 (记录日内每一个探测到的信号轨迹)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS live_signal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    code TEXT,
                    name TEXT,
                    price REAL,
                    action TEXT,
                    reason TEXT,
                    indicators TEXT, -- JSON 存储当时的环境快照
                    resample TEXT DEFAULT 'd',
                    highest_after REAL DEFAULT 0.0, -- 触发后的最高价 (供后续分析)
                    lowest_after REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'NEW'
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_live_sig_date ON live_signal_history (timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_live_sig_code ON live_signal_history (code)")
            
            # 6. 黑名单与忽略报警统计表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS live_blacklist (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    added_date TEXT,
                    reason TEXT,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            
            # --- Schema Evolution/Migration (New) ---
            # 检查字段是否缺失 (针对已存在数据库升级)
            cur.execute("PRAGMA table_info(selection_history)")
            existing_cols = [col[1] for col in cur.fetchall()]
            
            check_cols = {
                "score": "REAL",
                "reason": "TEXT",
                "ratio": "REAL",
                "amount": "REAL",
                "status": "TEXT",
                "grade": "TEXT",  # ✅ [新增] 2024-03-19 分级支持
                "tqi": "REAL",    # ✅ [新增] 2024-03-19 质量分支持
                "ma5": "REAL",
                "ma10": "REAL",
                "category": "TEXT"
            }
            
            for col_name, col_type in check_cols.items():
                if col_name not in existing_cols:
                    logger.error(f"DB Migration: Adding missing column '{col_name}' to selection_history")
                    try:
                        cur.execute(f"ALTER TABLE selection_history ADD COLUMN {col_name} {col_type}")
                        logger.info(f"✅ DB Migration: Successfully added {col_name} to selection_history")
                    except Exception as alt_e:
                        logger.warning(f"⚠️ DB Migration failed for {col_name}: {alt_e}")
            # Migration for trade_records
            cur.execute("PRAGMA table_info(trade_records)")
            existing_trade_cols = [col[1] for col in cur.fetchall()]
            if "buy_reason" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN buy_reason TEXT")
            if "sell_reason" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN sell_reason TEXT")
            if "resample" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN resample TEXT DEFAULT 'd'")
                logger.info("DB Migration: Added 'resample' column to trade_records")
            if "action" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN action TEXT")
                logger.info("DB Migration: Added 'action' column to trade_records")
            
            # Migration for signal_history
            cur.execute("PRAGMA table_info(signal_history)")
            existing_signal_cols = [col[1] for col in cur.fetchall()]
            if "resample" not in existing_signal_cols:
                cur.execute("ALTER TABLE signal_history ADD COLUMN resample TEXT DEFAULT 'd'")
                logger.info("DB Migration: Added 'resample' column to signal_history")
            
            # Migration for selection_history
            if "resample" not in existing_cols:
                cur.execute("ALTER TABLE selection_history ADD COLUMN resample TEXT DEFAULT 'd'")
                logger.info("DB Migration: Added 'resample' column to selection_history")

            # Migration for voice_alerts (Upgrade PK to include resample)
            cur.execute("PRAGMA table_info(voice_alerts)")
            voice_cols = [col[1] for col in cur.fetchall()]
            if "resample" not in voice_cols:
                logger.info("DB Migration: Upgrading voice_alerts PK for multi-period support")
                # SQLite doesn't support ALTER TABLE DROP/ADD PRIMARY KEY
                # We must use a temporary table
                cur.execute("CREATE TABLE voice_alerts_backup AS SELECT * FROM voice_alerts")
                cur.execute("DROP TABLE voice_alerts")
                cur.execute("""
                    CREATE TABLE voice_alerts (
                        code TEXT,
                        resample TEXT DEFAULT 'd',
                        name TEXT,
                        rules TEXT,
                        last_alert REAL,
                        created_time TEXT,
                        tags TEXT,
                        added_date TEXT,
                        rule_type_tag TEXT,
                        PRIMARY KEY (code, resample)
                    )
                """)
                # Insert data from backup, defaulting resample to 'd'
                cur.execute("""
                    INSERT INTO voice_alerts (code, name, rules, last_alert, created_time, tags, added_date, rule_type_tag, resample, create_price)
                    SELECT code, name, rules, last_alert, created_time, tags, added_date, rule_type_tag, 'd', 0.0 FROM voice_alerts_backup
                """)
                cur.execute("DROP TABLE voice_alerts_backup")
                logger.info("DB Migration: voice_alerts upgrade completed")
            
            # 另起一个 Migration: 专门检查最近新增的 create_price 字段 (如果已有 resample 之后又升级的情况)
            cur.execute("PRAGMA table_info(voice_alerts)")
            voice_cols = [col[1] for col in cur.fetchall()]
            if "create_price" not in voice_cols:
                logger.info("DB Migration: Adding create_price to voice_alerts")
                cur.execute("ALTER TABLE voice_alerts ADD COLUMN create_price REAL DEFAULT 0.0")

            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"DB Init Error: {e}")

    def log_selection(self, records: list[dict[str, Any]]) -> None:
        """
        批量记录选股结果
        records: 包含 date, code, name, score, price, percent, volume, reason, ma5, ma10, category 的字典列表
        """
        if not records:
            return
            
        try:
            from JohnsonUtil import commonTips as cct
            if not cct.get_work_time():
                # logger.debug("TradeLogger: 非交易时间，拒绝记录选股结果。")
                return
        except Exception as check_e:
            pass
            
        try:
            self.db_manager.executemany("""
                INSERT OR REPLACE INTO selection_history (date, code, name, score, price, percent, ratio, volume, amount, reason, status, grade, tqi, ma5, ma10, category, resample)
                VALUES (:date, :code, :name, :score, :price, :percent, :ratio, :volume, :amount, :reason, :status, :grade, :tqi, :ma5, :ma10, :category, :resample)
            """, records)
        except Exception as e:
            logger.error(f"Error logging selections: {e}")

    def get_selections_df(self, date: Optional[str] = None, resample: Optional[str] = None) -> Any:
        """获取选股历史记录"""
        conn = self.db_manager.get_connection()
        query = "SELECT * FROM selection_history WHERE 1=1"
        params: list = []
        
        if date:
            query += " AND date = ?"
            params.append(date)
        if resample:
            query += " AND resample = ?"
            params.append(resample)
        
        # 按分数倒序
        query += " ORDER BY date DESC, score DESC"
        
        try:
            if pd:
                # pandas read_sql_query uses connection object
                df = pd.read_sql_query(query, conn, params=params)
                return df
            else:
                with self.db_manager.execute_query(query, tuple(params)) as cur:
                    rows = cur.fetchall()
                    cols = [d[0] for d in cur.description]
                    results = [dict(zip(cols, row)) for row in rows]
                return results
        except Exception as e:
            logger.error(f"Error getting selections: {e}")
            return pd.DataFrame() if pd else []

    def log_signal(self, code: str, name: str, price: float, decision_dict: dict[str, Any], row_data: Optional[dict[str, Any]] = None, resample: str = 'd') -> None:
        """
        记录每日决策信号
        decision_dict 格式参考 IntradayDecisionEngine.evaluate 的输出
        row_data: 可选的行情数据字典，包含 ma5d, ma10d, ratio, volume 等指标
        resample: 周期标识 ('d', '3d', 'w', 'm')
        """
        try:
            try:
                from JohnsonUtil import commonTips as cct
                if not cct.get_work_time():
                    return
            except Exception as check_e:
                pass
                
            date_str = datetime.now().strftime('%Y-%m-%d')
            
            # 合并 debug 信息和行情数据以供后续 AI 分析优化
            indicators = decision_dict.get('debug', {}).copy()
            if row_data:
                # 将行情数据合并进来，便于分析时直接使用
                for key, value in row_data.items():
                    if key not in indicators:  # 避免覆盖 debug 中已有的字段
                        indicators[key] = value
            
            # 使用自定义 Encoder 处理 Numpy 类型
            indicators_json = json.dumps(indicators, ensure_ascii=False, cls=NumpyEncoder)
            
            self.db_manager.execute_update("""
                INSERT OR REPLACE INTO signal_history (date, code, name, price, action, position, reason, indicators, resample)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date_str, 
                code, 
                name, 
                price, 
                decision_dict.get('action'), 
                decision_dict.get('position'), 
                decision_dict.get('reason'),
                indicators_json,
                resample
            ))
        except Exception as e:
            logger.error(f"Error logging signal: {e}")

    def log_live_signal(self, code: str, name: str, price: float, action: str, reason: str, indicators: Optional[dict[str, Any]] = None, resample: str = 'd') -> None:
        """
        全量记录实时发现的每一个信号轨迹（不进行去重）
        用于盘后精细化分析
        """
        try:
            # --- [交易日和交易时段检查] ---
            try:
                from JohnsonUtil import commonTips as cct
                if not cct.get_work_time():
                    return
            except Exception as check_e:
                logger.debug(f"LiveSignal: 交易日/时段检查失败 (fallback to allow): {check_e}")
            
            # --- [Deduplication] ---
            import time
            now_ts = time.time()
            cache_key = (code, action)
            
            # 清理过期的 cache (简单起见，每次随机清理或按阈值清理，这里每次检查当前key即可，另加定期清理)
            # 简单清理：如果有 1000 个缓存，清除超过 600s 的 (因为最大窗口变为了 600s)
            if len(self._signal_cache) > 1000:
                self._signal_cache = {k: v for k, v in self._signal_cache.items() if now_ts - v[0] < 600}
            
            last_ts, last_price = self._signal_cache.get(cache_key, (0, 0.0))
            
            dt = now_ts - last_ts
            # 计算价格变动幅度
            price_change_pct = abs(price - last_price) / last_price if last_price > 0 else 1.0
            
            # 策略 A: 极速冷却 (60秒内，无论价格怎么变都屏蔽，防止高频刷屏)
            if dt < 60:
                return

            # 策略 B: 滞涨冷却 (10分钟内，如果价格变动小于 0.5%，则视为无价值重复信号)
            # 只有当价格出现显著波动 (>=0.5%) 或时间超过 10分钟，才记录下一次
            if dt < 600 and price_change_pct < 0.005: 
                return

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 处理指标快照
            indicators_json = "{}"
            if indicators:
                indicators_json = json.dumps(indicators, ensure_ascii=False, cls=NumpyEncoder)
            
            self.db_manager.execute_update("""
                INSERT INTO live_signal_history (timestamp, code, name, price, action, reason, indicators, resample)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (now_str, code, name, price, action, reason, indicators_json, resample))
            
            # 更新缓存: (时间, 价格)
            self._signal_cache[cache_key] = (now_ts, price)
            # logger.debug(f"LiveSignal: Recorded {code} {action} at {price}")
        except Exception as e:
            logger.error(f"Error in log_live_signal: {e}")

    def get_live_signal_history_df(self, date: Optional[str] = None, code: Optional[str] = None, action: Optional[str] = None, limit: int = 1000):
        """获取实时信号历史供 UI 展示"""
        try:
            conn = self.db_manager.get_connection()
            query = "SELECT * FROM live_signal_history WHERE 1=1"
            params = []
            if date:
                # 假设 timestamp 格式为 YYYY-MM-DD HH:MM:SS
                query += " AND timestamp LIKE ?"
                params.append(f"{date}%")
            if code:
                query += " AND code = ?"
                params.append(code)
            if action and action != "全部":
                # 支持模糊匹配，例如 "买入" 匹配 "挂单买入", "自动买入"
                query += " AND action LIKE ?"
                params.append(f"%{action}%")
            
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            # Use connection from manager
            conn = self.db_manager.get_connection()
            df = pd.read_sql_query(query, conn, params=params)
            return df
        except Exception as e:
            logger.error(f"Error get_live_signal_history_df: {e}")
            return pd.DataFrame()

    def record_trade(self, code: str, name: str, action: str, price: float, amount: float, fee_rate: float = 0.0003, reason: str = "", resample: str = 'd') -> None:
        """
        记录买卖操作并计算单笔盈利
        fee_rate: 手续费率（默认万3）
        resample: 周期标识 ('d', '3d', 'w', 'm')
        """
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            
            # --- [新增] 非交易日拦截 ---
            try:
                from JohnsonUtil import commonTips as cct
                if not cct.get_work_time():
                    logger.warning(f"TradeLogger: 非交易时间，拒绝记录交易 ({code} {action})")
                    return
            except Exception as check_e:
                logger.debug(f"TradeLogger: 交易日检查失败 (fallback to allow): {check_e}")

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 检查是否已有持仓
            cur.execute("SELECT id, buy_price, buy_amount, fee, action FROM trade_records WHERE code=? AND resample=? AND status='OPEN' ORDER BY buy_date DESC LIMIT 1", (code, resample))
            existing_trade = cur.fetchone()

            if action == "买入":
                if existing_trade:
                    logger.warning(f"TradeLogger: {code} ({name}) already has an OPEN position. Skipping duplicate '买入'.")
                    logger.warning(f"TradeLogger: {code} ({name}) already has an OPEN position. Skipping duplicate '买入'.")
                    cur.close()
                    return
                if amount <= 0:
                    # 当买入量为 0 时（通常为模拟或追踪模式），记录为日内全量信号，不再静默跳过
                    logger.warning(f"TradeLogger: {code} ({name}) '买入' amount is 0. Recording as discovery signal.")
                    cur.close()
                    self.log_live_signal(code, name, price, action, f"[OBSERVE] {reason}", resample=resample)
                    return
                # 开启新仓
                fee = price * amount * fee_rate
                cur.execute("""
                    INSERT INTO trade_records (code, name, buy_date, buy_price, buy_amount, buy_reason, fee, status, resample, action)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """, (code, name, now_str, price, amount, reason, fee, resample, action))
            
            elif action == "ADD":
                if not existing_trade:
                    logger.warning(f"TradeLogger: {code} ({name}) No OPEN position to ADD to. Converting to '买入'.")
                    # 如果没有持仓，退化为买入
                    fee = price * amount * fee_rate
                    cur.execute("""
                        INSERT INTO trade_records (code, name, buy_date, buy_price, buy_amount, buy_reason, fee, status, resample, action)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                    """, (code, name, now_str, price, amount, reason, fee, resample, action))
                else:
                    # 加仓：更新均价和股数，并追加理由
                    t_id, old_price, old_amount, old_fee, last_action = existing_trade
                    # 尝试读取旧理由
                    cur.execute("SELECT buy_reason FROM trade_records WHERE id=?", (t_id,))
                    res = cur.fetchone()
                    old_reason = res[0] if res and res[0] else ""
                    new_reason = f"{old_reason} | [ADD] {reason}" if old_reason else f"[ADD] {reason}"
                    
                    new_amount = old_amount + amount
                    new_fee = old_fee + (price * amount * fee_rate)
                    if new_amount <= 0:
                        new_avg_price = old_price
                    else:
                        # 计算加权均价
                        new_avg_price = (old_price * old_amount + price * amount) / new_amount
                    
                    cur.execute("""
                        UPDATE trade_records 
                        SET buy_price=?, buy_amount=?, buy_reason=?, fee=?, action=?
                        WHERE id=?
                    """, (new_avg_price, new_amount, new_reason, new_fee, action, t_id))
                    logger.warning(f"TradeLogger: {code} ({name}) 加仓成功. 新均价: {new_avg_price:.2f}, 动作: {action}, 原因: {reason}")

            elif action == "卖出" or "止" in action:
                if existing_trade:
                    t_id, b_price, b_amount, old_fee, last_action = existing_trade
                    sell_fee = price * b_amount * fee_rate # 假设卖出股数等于当前全部持仓
                    total_fee = old_fee + sell_fee
                    gross_profit = (price - b_price) * b_amount
                    net_profit = gross_profit - total_fee
                    pnl_pct = net_profit / (b_price * b_amount) if (b_price > 0 and b_amount > 0) else 0
                    
                    cur.execute("""
                        UPDATE trade_records 
                        SET sell_date=?, sell_price=?, sell_reason=?, fee=?, profit=?, pnl_pct=?, status='CLOSED', action=?
                        WHERE id=?
                    """, (now_str, price, reason, total_fee, net_profit, pnl_pct, action, t_id))
                    logger.warning(f"TradeLogger: {code} ({name}) 平仓成功. 盈亏: {net_profit:.2f} ({pnl_pct:.2%})")
                else:
                    logger.warning(f"TradeLogger: {code} ({name}) Signal 'CLOSE' ignored (No OPEN position).")
            
            
            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Error recording trade: {e}")

    def close_trade(self, code: str, sell_price: float, sell_reason: str, sell_amount: float = 0, resample: str = 'd') -> bool:
        """
        强制平仓指定代码的持仓记录 (用于手动干预或状态同步)
        """
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            
            # 找到最新的 OPEN 持仓
            cur.execute("""
                SELECT id, buy_price, buy_amount, fee FROM trade_records 
                WHERE code=? AND status='OPEN' AND resample=? 
                ORDER BY buy_date DESC LIMIT 1
            """, (code, resample))
            existing_trade = cur.fetchone()
            
            if not existing_trade:
                logger.warning(f"DB: Trade {code} not found or already closed.")
                cur.close()
                return False
                
            t_id, b_price, b_amount, old_fee = existing_trade
            
            if sell_amount <= 0:
                sell_amount = b_amount # 默认全部平仓
                
            # 简单计算
            fee_rate = 0.001
            total_fee = old_fee + (sell_price * sell_amount * fee_rate)
            gross_profit = (sell_price - b_price) * sell_amount
            net_profit = gross_profit - total_fee
            pnl_pct = net_profit / (b_price * b_amount) if (b_price > 0 and b_amount > 0) else 0.0
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cur.execute("""
                UPDATE trade_records 
                SET sell_date=?, sell_price=?, sell_reason=?, fee=?, profit=?, pnl_pct=?, status='CLOSED'
                WHERE id=?
            """, (now_str, sell_price, sell_reason, total_fee, net_profit, pnl_pct, t_id))
            
            conn.commit()
            cur.close()
            logger.info(f"DB: Closed trade {code}. Reason: {sell_reason}")
            return True
        except Exception as e:
            logger.error(f"Error closing trade {code}: {e}")
            return False

    def get_summary(self, resample: Optional[str] = None) -> Optional[tuple[float, float, int]]:
        """获取盈亏概览"""
    def get_summary(self, resample: Optional[str] = None) -> Optional[tuple[float, float, int]]:
        """获取盈亏概览"""
        conn = self.db_manager.get_connection()
        cur = conn.cursor()
        query = "SELECT SUM(profit), AVG(pnl_pct), COUNT(*) FROM trade_records WHERE status='CLOSED'"
        params = []
        if resample:
            query += " AND resample = ?"
            params.append(resample)
            
        cur.execute(query, params)
        res = cur.fetchone()
        cur.close()
        return res # (总利润, 平均收益率, 总笔数)

    def get_signals(self, start_date: Optional[str] = None, end_date: Optional[str] = None, resample: Optional[str] = None, code: Optional[str] = None) -> list[dict[str, Any]]:
        """获取记录的信号"""
        conn = self.db_manager.get_connection()
        cur = conn.cursor()
        query = "SELECT * FROM signal_history WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if resample:
            query += " AND resample = ?"
            params.append(resample)
        if code:
            query += " AND code = ?"
            params.append(code)
        
        query += " ORDER BY date DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        cur.close()
        return results

    def get_signal_history_df_bug(self, start_date=None, end_date=None, resample=None, code=None, limit=None):
        import pandas as pd
        conn = self.db_manager.get_connection()
        
        cols = ["date", "code", "resample", "price", "signal"]
        query = f"SELECT {', '.join(cols)} FROM signal_history WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if resample:
            query += " AND resample = ?"
            params.append(resample)
        if code:
            query += " AND code = ?"
            params.append(code)
        
        query += " ORDER BY date DESC"
        if limit:
            query += f" LIMIT {limit}"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"get_signal_history_df error: {e}")
            df = pd.DataFrame()
        
        return df

    def get_signal_history_df(self, start_date: Optional[str] = None, end_date: Optional[str] = None, resample: Optional[str] = None, code: Optional[str] = None):
        """获取信号历史并作为 DataFrame 返回"""
        try:
            import pandas as pd
        except ImportError:
            return None
            
            return None
            
        conn = self.db_manager.get_connection()
        query = "SELECT * FROM signal_history WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if resample:
            query += " AND resample = ?"
            params.append(resample)
        if code:
            query += " AND code = ?"
            params.append(code)
            
        query += " ORDER BY date DESC"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"get_signal_history_df error: {e}")
            df = pd.DataFrame()
        
        return df

    def get_today_trades(self, resample: Optional[str] = None) -> list[dict[str, Any]]:
        """获取今天的交易记录"""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.get_trades(start_date=today, resample=resample)

    def get_trades(self, start_date: Optional[str] = None, end_date: Optional[str] = None, resample: Optional[str] = None) -> list[dict[str, Any]]:
        """获取交易记录（包含持仓中和已平仓）"""
        conn = self.db_manager.get_connection()
        cur = conn.cursor()
        # 获取所有记录，优先按卖出日期（已平仓）或买入日期（持仓）排序
        query = "SELECT * FROM trade_records WHERE 1=1"
        params = []
        if start_date:
            # 这里的逻辑：如果是已平仓且有 sell_date，则按 sell_date 过滤；如果是持仓，则按 buy_date 过滤
            query += " AND ( (status='CLOSED' AND date(sell_date) >= ?) OR (status='OPEN' AND date(buy_date) >= ?) )"
            params.extend([start_date, start_date])
        if end_date:
            query += " AND ( (status='CLOSED' AND date(sell_date) <= ?) OR (status='OPEN' AND date(buy_date) <= ?) )"
            params.extend([end_date, end_date])
        if resample:
            query += " AND resample = ?"
            params.append(resample)
            
        query += " ORDER BY CASE WHEN status='CLOSED' THEN sell_date ELSE buy_date END DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # 转换为列表字典
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        # 转换为列表字典
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        cur.close()
        return results

    def delete_trade(self, trade_id: int) -> bool:
        """删除交易记录"""
        try:
            self.db_manager.execute_update("DELETE FROM trade_records WHERE id=?", (trade_id,))
            return True
        except Exception as e:
            logger.error(f"delete_trade error: {e}")
            return False

    def manual_update_trade(self, trade_id: int, buy_p: float, buy_a: float, sell_p: Optional[float] = None, fee_rate: float = 0.0003) -> bool:
        """手动更新交易数据并重算盈亏"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            
            # 先获取现有状态
            cur.execute("SELECT status FROM trade_records WHERE id=?", (trade_id,))
            row = cur.fetchone()
            if not row: 
                cur.close()
                return False
            status = row[0]

            if status == 'OPEN':
                fee = buy_p * buy_a * fee_rate
                cur.execute("""
                    UPDATE trade_records SET buy_price=?, buy_amount=?, fee=? WHERE id=?
                """, (buy_p, buy_a, fee, trade_id))
            else:
                # CLOSED 状态需要重算全过程
                if sell_p is None:
                    # 如果状态是 CLOSED 但没有提供 sell_p，尝试从数据库获取现有 sell_price
                    cur.execute("SELECT sell_price FROM trade_records WHERE id=?", (trade_id,))
                    row_sell = cur.fetchone()
                    sell_p = row_sell[0] if row_sell else 0.0
                
                # 确保 sell_p 不为 None (兜底)
                effective_sell_p = sell_p if sell_p is not None else 0.0
                
                total_fee = (buy_p * buy_a * fee_rate) + (effective_sell_p * buy_a * fee_rate)
                net_profit = (effective_sell_p - buy_p) * buy_a - total_fee
                pnl_pct = net_profit / (buy_p * buy_a) if (buy_p > 0 and buy_a > 0) else 0
                cur.execute("""
                    UPDATE trade_records SET buy_price=?, buy_amount=?, sell_price=?, fee=?, profit=?, pnl_pct=?
                    WHERE id=?
                """, (buy_p, buy_a, effective_sell_p, total_fee, net_profit, pnl_pct, trade_id))
            
            conn.commit()
            cur.close()
            return True
        except Exception as e:
            logger.error(f"manual_update_trade error: {e}")
            return False

    def update_trade_feedback(self, trade_id: int, feedback: str) -> bool:
        """更新交易反馈，用于策略优化告知问题"""
        try:
            self.db_manager.execute_update("UPDATE trade_records SET feedback=? WHERE id=?", (feedback, trade_id))
            return True
        except Exception as e:
            logger.error(f"update_trade_feedback error: {e}")
            return False

    def get_db_summary(self, days: int = 30, resample: Optional[str] = None) -> list[tuple[Any, ...]]:
        """按天统计多日收益"""
    def get_db_summary(self, days: int = 30, resample: Optional[str] = None) -> list[tuple[Any, ...]]:
        """按天统计多日收益"""
        conn = self.db_manager.get_connection()
        cur = conn.cursor()
        # 截取日期部分进行 group by
        query = """
            SELECT substr(sell_date, 1, 10) as day, SUM(profit) as daily_profit, COUNT(*) as count 
            FROM trade_records 
            WHERE status='CLOSED' 
        """
        params = []
        if resample:
            query += " AND resample = ?"
            params.append(resample)
        
        query += """
            GROUP BY day 
            ORDER BY day DESC 
            LIMIT ?
        """
        params.append(days)
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        return rows

    def remove_voice_alert_config(self, code: str, resample: Optional[str] = None):
        """从数据库物理删除语音预警配置"""
        try:
            if resample is None:
                self.db_manager.execute_update("DELETE FROM voice_alerts WHERE code = ?", (code,))
                logger.info(f"DB: Removed ALL voice alert configs for {code}")
            else:
                self.db_manager.execute_update("DELETE FROM voice_alerts WHERE code = ? AND resample = ?", (code, resample))
                logger.info(f"DB: Removed voice alert config for {code}_{resample}")
        except Exception as e:
            logger.error(f"Failed to remove voice alert config: {e}")

    def log_voice_alert_config(self, code: str, resample: str, name: str, rules: str, last_alert: float, tags: str = "", rule_type_tag: str = "", create_price: float = 0.0, created_time: str = ""):
        """记录或更新语音预警配置"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            added_date = datetime.now().strftime('%Y-%m-%d')
            
            # --- [关键保护] 保护已有的“加入价”和“创建时间”不被 0.0 或当前时间误覆盖 ---
            cur.execute("SELECT create_price, created_time FROM voice_alerts WHERE code=? AND resample=?", (code, resample))
            existing = cur.fetchone()
            if existing:
                if create_price <= 0 and existing[0] and existing[0] > 0:
                    create_price = float(existing[0])
                if not created_time and existing[1]:
                    created_time = str(existing[1])
            
            if not created_time:
                created_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            cur.execute("""
                INSERT OR REPLACE INTO voice_alerts 
                (code, resample, name, rules, last_alert, created_time, tags, added_date, rule_type_tag, create_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (code, resample, name, rules, last_alert, created_time, tags, added_date, rule_type_tag, create_price))
            
            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Failed to log voice alert config: {e}")

    def get_voice_alerts(self, resample: Optional[str] = None) -> list[dict[str, Any]]:
        """获取所有或特定周期的语音预警配置"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            query = "SELECT * FROM voice_alerts"
            params = []
            if resample:
                query += " WHERE resample = ?"
                params.append(resample)
            
            cur.execute(query, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            results = [dict(zip(cols, row)) for row in rows]
            cur.close()
            return results
        except Exception as e:
            logger.error(f"Failed to get voice alerts: {e}")
            return []

    # --- 黑名单扩展方法 ---
    def add_to_blacklist(self, code: str, name: str, reason: str = "manual_del") -> None:
        """将股票加入黑名单"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            self.db_manager.execute_update("""
                INSERT OR REPLACE INTO live_blacklist (code, name, added_date, reason, hit_count)
                VALUES (?, ?, ?, ?, COALESCE((SELECT hit_count FROM live_blacklist WHERE code=?), 0))
            """, (code, name, today, reason, code))
        except Exception as e:
            logger.error(f"DB Error add_to_blacklist: {e}")

    def remove_from_blacklist(self, code: str) -> bool:
        """从黑名单移除"""
        try:
            self.db_manager.execute_update("DELETE FROM live_blacklist WHERE code=?", (code,))
            return True
        except Exception as e:
            logger.error(f"DB Error remove_from_blacklist: {e}")
            return False

    def get_blacklist_data(self, date: Optional[str] = None) -> dict[str, dict[str, Any]]:
        """获取黑名单数据 (可选日期筛选)"""
        try:
            conn = self.db_manager.get_connection()
            query = "SELECT * FROM live_blacklist"
            params = []
            if date and date != "全部":
                query += " WHERE added_date = ?"
                params.append(date)
            
            df = pd.read_sql_query(query, conn, params=params)
            # 转为 dict 方便缓存同步 {code: {name, date, reason, hit_count}}
            res = {}
            for _, row in df.iterrows():
                res[row['code']] = {
                    "name": row['name'],
                    "date": row['added_date'],
                    "reason": row['reason'],
                    "hit_count": row['hit_count']
                }
            return res
        except Exception as e:
            logger.error(f"DB Error get_blacklist_data: {e}")
            return {}

    def get_blacklist_dates(self) -> list[str]:
        """获取黑名单中存在的所有不同日期"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT added_date FROM live_blacklist ORDER BY added_date DESC")
            dates = [row[0] for row in cur.fetchall() if row[0]]
            cur.close()
            return dates
        except Exception as e:
            logger.error(f"DB Error get_blacklist_dates: {e}")
            return []

    def increment_blacklist_hit(self, code: str) -> None:
        """增加黑名单触发次数统计"""
        try:
            self.db_manager.execute_update(
                "UPDATE live_blacklist SET hit_count = hit_count + 1 WHERE code = ?", 
                (code,)
            )
        except Exception as e:
            logger.error(f"DB Error increment_blacklist_hit for {code}: {e}")

    def clear_daily_blacklist(self) -> None:
        """清空今日黑名单 (如果需求是每日重置，则调用此方法)"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            self.db_manager.execute_update("DELETE FROM live_blacklist WHERE added_date = ?", (today,))
        except Exception as e:
            logger.error(f"DB Error clear_daily_blacklist: {e}")

    def get_consecutive_losses(self, code: str, days: int = 10, resample: str = 'd') -> int:
        """
        获取某只股票最近连续亏损的次数 (用于“记仇”机制)
        """
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            # 获取最近N天的已平仓记录，按时间倒序
            cur.execute("""
                SELECT profit, buy_date FROM trade_records 
                WHERE code=? AND resample=? AND status='CLOSED' AND date(buy_date) >= date('now', ?)
                ORDER BY sell_date DESC
            """, (code, resample, f'-{days} days'))
            rows = cur.fetchall()
            cur.close()
            
            loss_count = 0
            for profit, _ in rows:
                if profit < 0:
                    loss_count += 1
                else:
                    # 一旦遇到盈利，连续亏损中断
                    break
            return loss_count
        except Exception as e:
            logger.error(f"get_consecutive_losses error: {e}")
            return 0

    def get_market_sentiment(self, days: int = 5, resample: Optional[str] = None) -> float:
        """
        获取最近 N 天的全市场交易胜率 (用于感知市场环境)
        Returns: 0.0 - 1.0
        """
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            query = "SELECT profit FROM trade_records WHERE status='CLOSED' AND date(sell_date) >= date('now', ?)"
            params = [f'-{days} days']
            if resample:
                query += " AND resample = ?"
                params.append(resample)
                
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            
            if not rows:
                return 0.5 # 无记录默认中性
            
            wins = sum(1 for r in rows if r[0] > 0)
            return wins / len(rows)
        except Exception as e:
            logger.error(f"get_market_sentiment error: {e}")
            return 0.5


class DBInspector:
    """
    通用数据库诊断工具 mixin
    """
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_table_info(self) -> dict[str, list[dict[str, str]]]:
        """获取所有表结构信息"""
        info = {}
        try:
            # Use local connection via manager if possible, but DBInspector is generic
            # Only use manager if we are sure self.db_path is managed
            # Here we just use standard connect for metadata inspect or use manager if we want WAL safety
            # Safest is to use manager
            mgr = SQLiteConnectionManager.get_instance(self.db_path)
            conn = mgr.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            
            for table in tables:
                cur.execute(f"PRAGMA table_info({table})")
                columns = []
                for col in cur.fetchall():
                    # cid, name, type, notnull, dflt_value, pk
                    columns.append({
                        "cid": col[0],
                        "name": col[1],
                        "type": col[2],
                        "notnull": bool(col[3]),
                        "pk": bool(col[5])
                    })
                info[table] = columns
            cur.close()
        except Exception as e:
            logger.error(f"DBInspector get_table_info error: {e}")
        return info

    def get_db_stats(self) -> dict[str, Any]:
        """获取数据库基本统计"""
        stats = {}
        try:
            mgr = SQLiteConnectionManager.get_instance(self.db_path)
            conn = mgr.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            
            table_stats = {}
            for table in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    table_stats[table] = count
                except:
                    table_stats[table] = -1
            
            
            stats['tables'] = table_stats
            cur.close()
        except Exception as e:
            logger.error(f"DBInspector get_db_stats error: {e}")
        return stats

    def run_health_check(self) -> list[str]:
        """运行数据库健康检查"""
        issues = []
        try:
            mgr = SQLiteConnectionManager.get_instance(self.db_path)
            conn = mgr.get_connection()
            cur = conn.cursor()
            
            # Check 1: 检查 schema 是否可读
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            if not tables:
                issues.append("Warning: Database has no tables or is empty.")
            
            # Check 2: 关键表是否为空 (示例)
            # 这里做一些通用的检查，具体业务检查在子类实现
            
            cur.close()
        except Exception as e:
            issues.append(f"Critical: Database connection failed: {e}")
        return issues


class SignalStrategyLogger(DBInspector):
    """
    负责读取 signal_strategy.db 的日志类
    该数据库存储实时产生的形态信号、报警等
    """
    def __init__(self, db_path: str = "./signal_strategy.db"):
        super().__init__(db_path)
        self.db_path = db_path
        self.db_manager = SQLiteConnectionManager.get_instance(db_path)
        # 确保 DB 存在（通常由产生信号的进程创建，这里主要是读取）

    def get_signal_messages(self, start_date: Optional[str] = None, end_date: Optional[str] = None, 
                            limit: int = 2000) -> list[dict[str, Any]]:
        """获取信号消息流"""
        try:
            conn = self.db_manager.get_connection()
            # row_factory 设为 Row 但我们习惯转 dict
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            query = "SELECT * FROM signal_message WHERE 1=1"
            params = []
            
            if start_date:
                # signal_message 表有 created_date (YYYY-MM-DD)
                query += " AND created_date >= ?"
                params.append(start_date)
            if end_date:
                query += " AND created_date <= ?"
                params.append(end_date)
                
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            
            cur.execute(query, params)
            rows = cur.fetchall()
            results = [dict(row) for row in rows]
            cur.close()
            return results
        except Exception as e:
            logger.error(f"get_signal_messages error: {e}")
            return []

    def get_signal_counts_by_type(self, date: Optional[str] = None) -> list[tuple[str, int]]:
        """按类型统计信号数量"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            query = "SELECT signal_type, COUNT(*) as c FROM signal_message WHERE 1=1"
            params = []
            if date:
                query += " AND created_date = ?"
                params.append(date)
            query += " GROUP BY signal_type ORDER BY c DESC"
            
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_signal_counts_by_type error: {e}")
            return []
            
    def get_top_signal_stocks(self, date: Optional[str] = None, limit: int = 20) -> list[tuple[str, str, int]]:
        """获取产生信号最多的股票"""
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            query = "SELECT code, name, COUNT(*) as c FROM signal_message WHERE 1=1"
            params = []
            if date:
                query += " AND created_date = ?"
                params.append(date)
            query += " GROUP BY code, name ORDER BY c DESC LIMIT ?"
            params.append(limit)
            
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            return rows
        except Exception as e:
            logger.error(f"get_top_signal_stocks error: {e}")
            return []

    def get_daily_signal_counts(self, date: Optional[str] = None) -> list[dict[str, Any]]:
        """
        获取每日信号计数 (从 signal_counts 表)
        返回: [{code, pattern, count, last_trigger, date}, ...]
        """
        try:
            conn = self.db_manager.get_connection()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # 优先查询 signal_counts 表
            # 检查表是否存在
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='signal_counts'")
            if not cur.fetchone():
                cur.close()
                return []
                
            query = "SELECT * FROM signal_counts WHERE 1=1"
            params = []
            if date:
                query += " AND date = ?"
                params.append(date)
            
            query += " ORDER BY count DESC"
            cur.execute(query, params)
            rows = cur.fetchall()
            results = [dict(row) for row in rows]
            cur.close()
            return results
        except Exception as e:
            logger.error(f"get_daily_signal_counts error: {e}")
            return []

    @override
    def run_health_check(self) -> list[str]:
        """覆盖基类的检查，增加业务相关"""
        issues = super().run_health_check()
        try:
            conn = self.db_manager.get_connection()
            cur = conn.cursor()
            
            # Check: 是否有无效的时间戳
            try:
                cur.execute("SELECT COUNT(*) FROM signal_message WHERE timestamp IS NULL OR timestamp = ''")
                invalid_ts = cur.fetchone()[0]
                if invalid_ts > 0:
                    issues.append(f"Data Quality: Found {invalid_ts} rows with invalid timestamp in signal_message.")
            except:
                pass # 表可能不存在

            cur.close()
        except Exception as e:
            issues.append(f"DB Error during check: {e}")
        return issues



if __name__ == '__main__':
    from trading_analyzer import TradingAnalyzer
    
    logger_instance = TradingLogger("./trading_signals.db")
    
    # 简单的查看器
    def view_records(limit=20):
        try:
            import pandas as pd
        except ImportError:
            print("Pandas not found.")
            return

        print(f"\n=== 最近 {limit} 笔交易记录 ===")
        trades = logger_instance.get_trades()
        if not trades:
            print("无记录")
            return
        
        df = pd.DataFrame(trades)
        # 简单格式化
        cols = ['code', 'name', 'buy_date', 'buy_price', 'sell_date', 'sell_price', 'profit', 'pnl_pct', 'status']
        # 仅显示存在的列
        show_cols = [c for c in cols if c in df.columns]
        print(df[show_cols].head(limit).to_string(index=False))

    view_records()
    
    analyzer = TradingAnalyzer(logger_instance)

    print("--- 股票汇总 ---")
    print(analyzer.summarize_by_stock().head())

    print("\n--- 每日策略统计 ---")
    print(analyzer.daily_summary().head())

    print("\n--- 信号探测历史 ---")
    print(analyzer.get_signal_history_df().head())

    print("\n--- 顶级笔录分析 ---")
    df_combined = analyzer.get_trades_with_signals()
    if not df_combined.empty:
        print(f"成功获取 {len(df_combined)} 笔关联信号的交易记录")
        print(df_combined.head())
