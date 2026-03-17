
import os
import sys
import pandas as pd
import numpy as np

sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

def analyze_source_composition():
    source_h5 = r'G:\sina_MultiIndex_data.h5'
    print(f"Loading {source_h5} for composition analysis...")
    
    try:
        with pd.HDFStore(source_h5, mode='r') as store:
            key = store.keys()[0].lstrip('/')
            # 我们分块读取或仅读索引以提高速度
            index = store.select_column(key, 'code')
            unique_codes = index.unique()
            print(f"Total Unique Codes in file: {len(unique_codes)}")
            
            # 再看看 ticktime 的分布
            times = store.select_column(key, 'ticktime')
            unique_times = times.unique()
            print(f"Total Unique Timestamps: {len(unique_times)}")
            
            # 抽样前 5 个时间点的样本量
            sorted_times = sorted(unique_times)
            for t in sorted_times[:5]:
                # 这种查询在 HDFStore 中如果不加数据列索引可能慢，我们改用 get 并过滤
                pass
            
            # 统计每个 ticktime 的分布 (用 value_counts 更快)
            time_counts = times.value_counts().sort_index()
            print("\nFirst 10 Timestamps data distribution:")
            print(time_counts.head(10))
            
            print("\nLast 10 Timestamps data distribution:")
            print(time_counts.tail(10))
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_source_composition()
