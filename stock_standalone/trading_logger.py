
import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TradingLogger:
    """
    交易记录与信号持久化类
    使用 SQLite 存储每日决策、执行记录及收益统计
    """
    def __init__(self, db_path="./trading_signals.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
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
                PRIMARY KEY (date, code)
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
                sell_date TEXT,
                sell_price REAL,
                fee REAL,        -- 手续费累计
                profit REAL,     -- 净利润
                pnl_pct REAL,    -- 盈亏比例
                status TEXT,     -- 'OPEN' or 'CLOSED'
                feedback TEXT    -- 策略反馈 (用户点评)
            )
        """)
        conn.commit()
        conn.close()

    def log_signal(self, code, name, price, decision_dict):
        """
        记录每日决策信号
        decision_dict 格式参考 IntradayDecisionEngine.evaluate 的输出
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            date_str = datetime.now().strftime('%Y-%m-%d')
            
            # 序列化指标数据以供后续 AI 分析优化
            indicators_json = json.dumps(decision_dict.get('debug', {}), ensure_ascii=False)
            
            cur.execute("""
                INSERT OR REPLACE INTO signal_history (date, code, name, price, action, position, reason, indicators)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                date_str, 
                code, 
                name, 
                price, 
                decision_dict.get('action'), 
                decision_dict.get('position'), 
                decision_dict.get('reason'),
                indicators_json
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging signal: {e}")

    def record_trade(self, code, name, action, price, amount, fee_rate=0.0003):
        """
        记录买卖操作并计算单笔盈利
        fee_rate: 手续费率（默认万3）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if action == "买入":
                # 开启新仓
                fee = price * amount * fee_rate
                cur.execute("""
                    INSERT INTO trade_records (code, name, buy_date, buy_price, buy_amount, fee, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'OPEN')
                """, (code, name, now_str, price, amount, fee))
            
            elif action == "卖出" or "止" in action:
                # 寻找最近的未平仓记录
                cur.execute("SELECT id, buy_price, buy_amount, fee FROM trade_records WHERE code=? AND status='OPEN' ORDER BY buy_date DESC LIMIT 1", (code,))
                row = cur.fetchone()
                if row:
                    t_id, b_price, b_amount, old_fee = row
                    sell_fee = price * b_amount * fee_rate # 假设卖出股数等于买入
                    total_fee = old_fee + sell_fee
                    gross_profit = (price - b_price) * b_amount
                    net_profit = gross_profit - total_fee
                    pnl_pct = net_profit / (b_price * b_amount) if b_price > 0 else 0
                    
                    cur.execute("""
                        UPDATE trade_records 
                        SET sell_date=?, sell_price=?, fee=?, profit=?, pnl_pct=?, status='CLOSED'
                        WHERE id=?
                    """, (now_str, price, total_fee, net_profit, pnl_pct, t_id))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error recording trade: {e}")

    def get_summary(self):
        """获取盈亏概览"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT SUM(profit), AVG(pnl_pct), COUNT(*) FROM trade_records WHERE status='CLOSED'")
        res = cur.fetchone()
        conn.close()
        return res # (总利润, 平均收益率, 总笔数)

    def get_closed_trades(self, start_date=None, end_date=None):
        """获取已平仓交易记录"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        query = "SELECT * FROM trade_records WHERE status='CLOSED'"
        params = []
        if start_date:
            query += " AND sell_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND sell_date <= ?"
            params.append(end_date)
        query += " ORDER BY sell_date DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # 转换为列表字典
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        conn.close()
        return results

    def update_trade_feedback(self, trade_id, feedback):
        """更新交易反馈，用于策略优化告知问题"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("UPDATE trade_records SET feedback=? WHERE id=?", (feedback, trade_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"update_trade_feedback error: {e}")
            return False

    def get_db_summary(self, days=30):
        """按天统计多日收益"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # 截取日期部分进行 group by
        cur.execute("""
            SELECT substr(sell_date, 1, 10) as day, SUM(profit) as daily_profit, COUNT(*) as count 
            FROM trade_records 
            WHERE status='CLOSED' 
            GROUP BY day 
            ORDER BY day DESC 
            LIMIT ?
        """, (days,))
        rows = cur.fetchall()
        conn.close()
        return rows
