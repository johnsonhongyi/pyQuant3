# -*- coding: utf-8 -*-
"""诊断 ATS 推荐理由显示"历史数据不足"的根本原因"""
import pandas as pd
import os

path = r'g:\sina_MultiIndex_data.h5'
print('文件存在:', os.path.exists(path))

with pd.HDFStore(path, mode='r') as store:
    print('所有 key:', store.keys())
    key = '/all_30'
    if key not in store.keys():
        print('!!! /all_30 不存在!')
    else:
        info = store.get_storer(key)
        print(f'总行数: {info.nrows}')
        df_sample = store.select(key, start=0, stop=5)
        print('index.names:', df_sample.index.names)
        print('columns:', list(df_sample.columns[:10]))
        print(df_sample.head(3))

        # 取第一个 code 做查询测试
        test_code = str(df_sample.index.get_level_values('code')[0])
        print(f'\n测试 code: {test_code}')

        try:
            df1 = store.select(key, where="code == '%s'" % test_code)
            print(f'  where code==  行数: {len(df1)}')
        except Exception as e:
            print(f'  where code==  错误: {e}')

        try:
            df2 = store.select(key, where="code in ['%s']" % test_code)
            print(f"  where code in ['..'] 行数: {len(df2)}")
        except Exception as e:
            print(f"  where code in ['..'] 错误: {e}")

        # 检查今日数据是否存在
        import datetime
        today = datetime.date.today().strftime('%Y-%m-%d')
        print(f'\n今日日期: {today}')
        try:
            df_today = store.select(key, where="ticktime >= '%s'" % today)
            print(f'  今日数据行数: {len(df_today)}')
            if not df_today.empty:
                codes_today = df_today.index.get_level_values('code').unique()
                print(f'  今日有数据的 code 数: {len(codes_today)}')
        except Exception as e:
            print(f'  今日数据查询错误: {e}')
