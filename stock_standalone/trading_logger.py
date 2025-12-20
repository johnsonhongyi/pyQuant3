import sqlite3
import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

class TradingLogger:
    """
    交易记录与信号持久化类
    使用 SQLite 存储每日决策、执行记录及收益统计
    """
    def __init__(self, db_path: str = "./trading_signals.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
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

    def log_signal(self, code: str, name: str, price: float, decision_dict: dict[str, Any]) -> None:
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

    def record_trade(self, code: str, name: str, action: str, price: float, amount: float, fee_rate: float = 0.0003) -> None:
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

    def get_summary(self) -> Optional[tuple[float, float, int]]:
        """获取盈亏概览"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT SUM(profit), AVG(pnl_pct), COUNT(*) FROM trade_records WHERE status='CLOSED'")
        res = cur.fetchone()
        conn.close()
        return res # (总利润, 平均收益率, 总笔数)

    def get_trades(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict[str, Any]]:
        """获取交易记录（包含持仓中和已平仓）"""
        conn = sqlite3.connect(self.db_path)
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
            
        query += " ORDER BY CASE WHEN status='CLOSED' THEN sell_date ELSE buy_date END DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        
        # 转换为列表字典
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        conn.close()
        return results

    def delete_trade(self, trade_id: int) -> bool:
        """删除交易记录"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("DELETE FROM trade_records WHERE id=?", (trade_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"delete_trade error: {e}")
            return False

    def manual_update_trade(self, trade_id: int, buy_p: float, buy_a: float, sell_p: Optional[float] = None, fee_rate: float = 0.0003) -> bool:
        """手动更新交易数据并重算盈亏"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # 先获取现有状态
            cur.execute("SELECT status FROM trade_records WHERE id=?", (trade_id,))
            row = cur.fetchone()
            if not row: return False
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
                pnl_pct = net_profit / (buy_p * buy_a) if buy_p > 0 else 0
                cur.execute("""
                    UPDATE trade_records SET buy_price=?, buy_amount=?, sell_price=?, fee=?, profit=?, pnl_pct=?
                    WHERE id=?
                """, (buy_p, buy_a, effective_sell_p, total_fee, net_profit, pnl_pct, trade_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"manual_update_trade error: {e}")
            return False

    def update_trade_feedback(self, trade_id: int, feedback: str) -> bool:
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

    def get_db_summary(self, days: int = 30) -> list[tuple[Any, ...]]:
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
