import sys
import os
sys.path.append(os.getcwd())

from stock_selector import StockSelector
import datetime

print("正在手动初始化 StockSelector 并关联到 dist 数据库...")
selector = StockSelector()
if selector.db_logger:
    selector.db_logger.db_path = "dist/trading_signals.db"
    print(f"成功将数据库关联路径重定向至: {selector.db_logger.db_path}")

target_date = "2026-05-08"
print(f"正在强行计算今日（{target_date}）的收盘选股数据，并执行持久化落库...")

# 强制重新计算，即便无缓存也重新运行
df = selector.get_candidates_df(force=True, logical_date=target_date)

if df.empty:
    print(f"Warning: Today ({target_date}) filtered results are empty!")
else:
    print(f"Success: Today filtered out {len(df)} candidates.")
    print("Available columns in df:")
    print(df.columns.tolist())
    # Try to print whatever columns are available
    show_cols = [c for c in ['date', 'code', 'name', 'rank', 'Rank', 'per1d', 'yesterday_pct', 'sum_perc', 'win'] if c in df.columns]
    print(df[show_cols].head(10).to_string(index=False))
