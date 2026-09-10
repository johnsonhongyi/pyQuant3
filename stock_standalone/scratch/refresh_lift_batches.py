import os
import sys
import json

# 加入当前目录到 sys.path
sys.path.insert(0, os.path.abspath("."))

from ats.new_stock_fetcher import NewStockFetcher

fetcher = NewStockFetcher.get_instance()
df = fetcher.get_combined_new_stocks(force_refresh=True)
print("Updated DataFrame rows:", len(df))
sample = df[["code", "name", "lift_date", "lift_stage", "lift_batch_desc", "lift_ratio"]].dropna().head(10)
print(sample)
