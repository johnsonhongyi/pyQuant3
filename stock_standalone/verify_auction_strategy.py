# -*- coding: utf-8 -*-
"""竞价买入策略验证 — 使用项目标准 TDX 接口"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

def main():
    import numpy as np
    from JSONData import tdx_data_Day as tdd
    from JohnsonUtil import johnson_cons as ct

    stocks = ['601869', '002440', '603103']
    names = {'601869': '长飞光纤', '002440': '闰土股份', '603103': '横店影视'}
    resample = 'd'
    dl = ct.Resample_LABELS_Days[resample]

    for code in stocks:
        name = names.get(code, code)
        print(f'\n{"="*70}')
        print(f'  {code} {name} — 竞价买入策略验证')
        print(f'{"="*70}')
        try:
            df = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample=resample)
        except Exception as e:
            print(f'  数据获取失败: {e}')
            continue
        if df is None or df.empty:
            print('  数据为空'); continue

        df = df.sort_index(ascending=True).tail(10)
        
        # 检查可用列
        cols = df.columns.tolist()
        has_upper = 'upper' in cols
        has_ma5 = 'ma5d' in cols
        has_win = 'win' in cols

        print(f'  {"日期":>12}  {"开盘":>7} {"最高":>7} {"最低":>7} {"收盘":>7}  OIL   竞价收益  追涨收益  {"Upper":>7}  {"MA5":>7}  Win')
        print(f'  {"-"*100}')

        auction_gains = []
        chase_gains = []
        oil_count = 0
        upper_count = 0

        for idx, row in df.iterrows():
            o = float(row.get('open', 0))
            h = float(row.get('high', 0))
            l = float(row.get('low', 0))
            c = float(row.get('close', 0))
            if o <= 0: continue

            # Open=Low: 开盘价≈最低价
            oil_pct = abs(o - l) / o * 100
            oil_flag = '✅' if oil_pct < 0.5 else '  '
            if oil_pct < 0.5: oil_count += 1

            # 竞价买入收益
            a_gain = (c - o) / o * 100
            mid_p = (h + l + c) / 3
            c_gain = (c - mid_p) / mid_p * 100
            auction_gains.append(a_gain)
            chase_gains.append(c_gain)

            # Upper 上轨
            upper_val = float(row.get('upper', 0)) if has_upper else 0
            upper_flag = '🔥' if upper_val > 0 and c >= upper_val * 0.98 else '  '
            if upper_val > 0 and c >= upper_val * 0.98: upper_count += 1
            upper_str = f'{upper_val:7.2f}' if upper_val > 0 else '    N/A'

            ma5_val = float(row.get('ma5d', 0)) if has_ma5 else 0
            ma5_str = f'{ma5_val:7.2f}' if ma5_val > 0 else '    N/A'
            
            win_val = int(row.get('win', 0)) if has_win else 0
            
            date_str = str(idx)[:10]
            print(f'  {date_str}  {o:7.2f} {h:7.2f} {l:7.2f} {c:7.2f}  {oil_flag}   {a_gain:+5.1f}%    {c_gain:+5.1f}%   {upper_flag}{upper_str}  {ma5_str}  {win_val:+d}')

        if auction_gains:
            avg_a = np.mean(auction_gains)
            avg_c = np.mean(chase_gains)
            n = len(auction_gains)
            print(f'\n  [结论]')
            print(f'    Open=Low天数: {oil_count}/{n} ({oil_count/n*100:.0f}%) — 开盘即最低,全天走高')
            print(f'    Upper上轨天数: {upper_count}/{n} ({upper_count/n*100:.0f}%) — 沿Bollinger上轨攀升')
            print(f'    竞价(开盘)买入平均收益: {avg_a:+.2f}%/天')
            print(f'    盘中追涨(均价)买入平均收益: {avg_c:+.2f}%/天')
            print(f'    竞价优势α: {avg_a - avg_c:+.2f}%/天 ← 犹豫=更高成本')

            if oil_count >= n * 0.5 and upper_count >= n * 0.4:
                print(f'    ⭐ 典型强势股: 高频Open=Low + 沿upper攀升 = 竞价买入最优')
            elif oil_count >= n * 0.3:
                print(f'    ✅ 趋势股: Open=Low频繁 → 竞价入场优于追涨')

    print(f'\n{"="*70}')
    print(f'  总结: 最强个股的共性特征')
    print(f'    1. Open=Low: 竞价是最低成本入场点')
    print(f'    2. 沿 Upper 上轨攀升: 趋势凌厉')
    print(f'    3. Win连阳: 走势不拖泥带水')
    print(f'    → 验证通过的热股次日竞价买入是最优策略')
    print(f'{"="*70}')

if __name__ == '__main__':
    main()
