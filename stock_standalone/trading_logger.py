import sqlite3
import json
import logging
from datetime import datetime
from typing import Any, Optional, Union

# 处理 override 装饰器 (Python 3.12+ 才有)
try:
    from typing import override # type: ignore
except ImportError:
    def override(func):
        return func

import numpy as np
from JohnsonUtil import LoggerFactory

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
                    buy_reason TEXT, -- 买入理由
                    sell_date TEXT,
                    sell_price REAL,
                    sell_reason TEXT, -- 卖出理由
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
                    ratio REAL,
                    volume REAL,
                    amount REAL,
                    reason TEXT,
                    status TEXT,
                    ma5 REAL,
                    ma10 REAL,
                    category TEXT,
                    PRIMARY KEY (date, code)
                )
            """)

            # 4. 语音预警配置表
            cur.execute("""
                CREATE TABLE IF NOT EXISTS voice_alerts (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    rules TEXT, -- JSON
                    last_alert REAL,
                    created_time TEXT,
                    tags TEXT,
                    added_date TEXT,
                    rule_type_tag TEXT
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
                "ma5": "REAL",
                "ma10": "REAL",
                "category": "TEXT"
            }
            
            for col_name, col_type in check_cols.items():
                if col_name not in existing_cols:
                    logger.error(f"DB Migration: Adding missing column '{col_name}' to selection_history")
            # Migration for trade_records
            cur.execute("PRAGMA table_info(trade_records)")
            existing_trade_cols = [col[1] for col in cur.fetchall()]
            if "buy_reason" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN buy_reason TEXT")
            if "sell_reason" not in existing_trade_cols:
                cur.execute("ALTER TABLE trade_records ADD COLUMN sell_reason TEXT")

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
                INSERT OR REPLACE INTO selection_history (date, code, name, score, price, percent, ratio, volume, amount, reason, status, ma5, ma10, category)
                VALUES (:date, :code, :name, :score, :price, :percent, :ratio, :volume, :amount, :reason, :status, :ma5, :ma10, :category)
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

    def record_trade(self, code: str, name: str, action: str, price: float, amount: float, fee_rate: float = 0.0003, reason: str = "") -> None:
        """
        记录买卖操作并计算单笔盈利
        fee_rate: 手续费率（默认万3）
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            
            # --- [新增] 非交易日拦截 ---
            try:
                from JohnsonUtil import commonTips as cct
                if not cct.get_trade_date_status():
                    logger.warning(f"TradeLogger: 非交易日，拒绝记录交易 ({code} {action})")
                    return
            except Exception as check_e:
                logger.debug(f"TradeLogger: 交易日检查失败 (fallback to allow): {check_e}")

            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 检查是否已有持仓
            cur.execute("SELECT id, buy_price, buy_amount, fee FROM trade_records WHERE code=? AND status='OPEN' ORDER BY buy_date DESC LIMIT 1", (code,))
            existing_trade = cur.fetchone()

            if action == "买入":
                if existing_trade:
                    logger.warning(f"TradeLogger: {code} ({name}) already has an OPEN position. Skipping duplicate '买入'.")
                    conn.close()
                    return
                # 开启新仓
                fee = price * amount * fee_rate
                cur.execute("""
                    INSERT INTO trade_records (code, name, buy_date, buy_price, buy_amount, buy_reason, fee, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
                """, (code, name, now_str, price, amount, reason, fee))
            
            elif action == "ADD":
                if not existing_trade:
                    logger.warning(f"TradeLogger: {code} ({name}) No OPEN position to ADD to. Converting to '买入'.")
                    # 如果没有持仓，退化为买入
                    fee = price * amount * fee_rate
                    cur.execute("""
                        INSERT INTO trade_records (code, name, buy_date, buy_price, buy_amount, buy_reason, fee, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN')
                    """, (code, name, now_str, price, amount, reason, fee))
                else:
                    # 加仓：更新均价和股数，并追加理由
                    t_id, old_price, old_amount, old_fee = existing_trade
                    # 尝试读取旧理由
                    cur.execute("SELECT buy_reason FROM trade_records WHERE id=?", (t_id,))
                    res = cur.fetchone()
                    old_reason = res[0] if res and res[0] else ""
                    new_reason = f"{old_reason} | [ADD] {reason}" if old_reason else f"[ADD] {reason}"
                    
                    new_amount = old_amount + amount
                    new_fee = old_fee + (price * amount * fee_rate)
                    # 计算加权均价
                    new_avg_price = (old_price * old_amount + price * amount) / new_amount
                    
                    cur.execute("""
                        UPDATE trade_records 
                        SET buy_price=?, buy_amount=?, buy_reason=?, fee=?
                        WHERE id=?
                    """, (new_avg_price, new_amount, new_reason, new_fee, t_id))
                    logger.info(f"TradeLogger: {code} ({name}) 加仓成功. 新均价: {new_avg_price:.2f}, 原因: {reason}")

            elif action == "卖出" or "止" in action:
                if existing_trade:
                    t_id, b_price, b_amount, old_fee = existing_trade
                    sell_fee = price * b_amount * fee_rate # 假设卖出股数等于当前全部持仓
                    total_fee = old_fee + sell_fee
                    gross_profit = (price - b_price) * b_amount
                    net_profit = gross_profit - total_fee
                    pnl_pct = net_profit / (b_price * b_amount) if b_price > 0 else 0
                    
                    cur.execute("""
                        UPDATE trade_records 
                        SET sell_date=?, sell_price=?, sell_reason=?, fee=?, profit=?, pnl_pct=?, status='CLOSED'
                        WHERE id=?
                    """, (now_str, price, reason, total_fee, net_profit, pnl_pct, t_id))
                    logger.info(f"TradeLogger: {code} ({name}) 平仓成功. 盈亏: {net_profit:.2f} ({pnl_pct:.2%})")
                else:
                    logger.info(f"TradeLogger: {code} ({name}) Signal 'CLOSE' ignored (No OPEN position).")
            
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

    def get_signal_history_df(self, start_date: Optional[str] = None, end_date: Optional[str] = None):
        """获取信号历史并作为 DataFrame 返回"""
        try:
            import pandas as pd
        except ImportError:
            return None
            
        conn = sqlite3.connect(self.db_path)
        query = "SELECT * FROM signal_history WHERE 1=1"
        params = []
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
            
        query += " ORDER BY date DESC"
        
        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"get_signal_history_df error: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()
        
        return df

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

    def get_consecutive_losses(self, code: str, days: int = 10) -> int:
        """
        获取某只股票最近连续亏损的次数 (用于“记仇”机制)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            # 获取最近N天的已平仓记录，按时间倒序
            cur.execute("""
                SELECT profit, buy_date FROM trade_records 
                WHERE code=? AND status='CLOSED' AND date(buy_date) >= date('now', ?)
                ORDER BY sell_date DESC
            """, (code, f'-{days} days'))
            rows = cur.fetchall()
            conn.close()
            
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

    def get_market_sentiment(self, days: int = 5) -> float:
        """
        获取最近 N 天的全市场交易胜率 (用于感知市场环境)
        Returns: 0.0 - 1.0
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT profit FROM trade_records 
                WHERE status='CLOSED' AND date(sell_date) >= date('now', ?)
            """, (f'-{days} days',))
            rows = cur.fetchall()
            conn.close()
            
            if not rows:
                return 0.5 # 无记录默认中性
            
            wins = sum(1 for r in rows if r[0] > 0)
            return wins / len(rows)
        except Exception as e:
            logger.error(f"get_market_sentiment error: {e}")
            return 0.5


if __name__ == '__main__':
    from trading_analyzer import TradingAnalyzer
    
    logger = TradingLogger("./trading_signals.db")
    
    # 简单的查看器
    def view_records(limit=20):
        try:
            import pandas as pd
        except ImportError:
            print("Pandas not found.")
            return

        print(f"\n=== 最近 {limit} 笔交易记录 ===")
        trades = logger.get_trades()
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
