import sqlite3
import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

import numpy as np

class NumpyEncoder(json.JSONEncoder):
    """
    专门用于处理 Numpy 数据类型的 JSON Encoder
    """
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
    def __init__(self, db_path: str = "./trading_signals.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        try:
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
            # 3. 每日选股记录表 (StockSelector 结果)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS selection_history (
                    date TEXT,
                    code TEXT,
                    name TEXT,
                    score REAL,
                    price REAL,
                    percent REAL,
                    volume REAL,
                    reason TEXT,
                    ma5 REAL,
                    ma10 REAL,
                    category TEXT,
                    PRIMARY KEY (date, code)
                )
            """)
            conn.commit()
            conn.close()
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
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # 使用事务批量插入
            cur.executemany("""
                INSERT OR REPLACE INTO selection_history (date, code, name, score, price, percent, volume, reason, ma5, ma10, category)
                VALUES (:date, :code, :name, :score, :price, :percent, :volume, :reason, :ma5, :ma10, :category)
            """, records)
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging selections: {e}")

    def get_selections_df(self, date: Optional[str] = None) -> Any:
        """
        获取选股历史，返回 DataFrame (为了解耦不强制在此文件 import pandas，返回 list[dict] 或由调用方转 df)
        但考虑到便利性，这里如果环境有 pandas 则返回 df，否则返回 list
        """
        try:
            import pandas as pd
        except ImportError:
            pd = None

        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM selection_history WHERE 1=1"
        params = []
        if date:
            query += " AND date = ?"
            params.append(date)
        
        # 按分数倒序
        query += " ORDER BY date DESC, score DESC"
        
        try:
            if pd:
                df = pd.read_sql_query(query, conn, params=params)
                conn.close()
                return df
            else:
                cur = conn.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
                results = [dict(zip(cols, row)) for row in rows]
                conn.close()
                return results
        except Exception as e:
            logger.error(f"Error getting selections: {e}")
            return pd.DataFrame() if pd else []

    def log_signal(self, code: str, name: str, price: float, decision_dict: dict[str, Any], row_data: Optional[dict[str, Any]] = None) -> None:
        """
        记录每日决策信号
        decision_dict 格式参考 IntradayDecisionEngine.evaluate 的输出
        row_data: 可选的行情数据字典，包含 ma5d, ma10d, ratio, volume 等指标
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
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

    def get_signals(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> list[dict[str, Any]]:
        """获取记录的信号"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        query = "SELECT * FROM signal_history WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        
        query += " ORDER BY date DESC"
        cur.execute(query, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        results = [dict(zip(cols, row)) for row in rows]
        conn.close()
        return results

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


if __name__ == '__main__':
    from trading_analyzer import TradingAnalyzer
    
    logger = TradingLogger("./trading_signals.db")
    analyzer = TradingAnalyzer(logger)

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
