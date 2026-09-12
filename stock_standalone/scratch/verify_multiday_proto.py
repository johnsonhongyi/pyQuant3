# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r"d:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone")
import numpy as np
import pandas as pd
import JohnsonUtil.commonTips as cct
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df, calc_trend_channel
from JSONData.tdx_channel_factory import TDXChannelFactory

def verify():
    df = get_tdx_Exp_day_to_df('002384')
    max_days = int(getattr(cct, 'compute_lastdays', 9))
    print(f"compute_lastdays: {max_days}")
    
    ch_res = TDXChannelFactory.calculate(df)
    n = len(df)
    upper = ch_res.upper
    upper_price = ch_res.upper_price
    supp_price_last = ch_res.supp_price
    supp_slope = ch_res.supp_slope
    
    print(f"supp_price_last: {supp_price_last}, supp_slope: {supp_slope}")
    
    for da in range(1, max_days + 1):
        u_val = float(upper[-da]) if n >= da and pd.notna(upper[-da]) else float(upper_price)
        s_val = float(supp_price_last - supp_slope * (da - 1))
        print(f"Day {da}: ch_upper{da}={u_val:.3f}, ch_supp{da}={s_val:.3f}")

if __name__ == '__main__':
    verify()
