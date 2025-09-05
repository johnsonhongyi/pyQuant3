import ctypes
from ctypes import wintypes
import requests
import tkinter as tk
from tkinter import messagebox, ttk
import threading
from datetime import datetime

# 定义所需的Windows API函数和类型
user32 = ctypes.windll.user32

# 定义回调函数类型
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_void_p)

# 定义所需的Windows API函数
EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
EnumWindows.restype = ctypes.c_bool

GetWindowTextW = user32.GetWindowTextW
GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetWindowTextW.restype = ctypes.c_int

GetClassNameW = user32.GetClassNameW
GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GetClassNameW.restype = ctypes.c_int

PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
PostMessageW.restype = ctypes.c_int

RegisterWindowMessageW = user32.RegisterWindowMessageW
RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
RegisterWindowMessageW.restype = ctypes.c_uint

# 全局变量，用于存储通达信窗口句柄
tdx_window_handle = 0

# 获取当前日期
current_date = datetime.now().strftime('%Y-%m-%d')
current_filter = 8000000

# -*- coding:utf-8 -*-
# !/usr/bin/env python

# import sys
# reload(sys)
# sys.setdefaultencoding('gbk')

#
# reload(sys)
#
# sys.setdefaultencoding('utf-8')
url_s = "http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=0&type=1"
url_b = "http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=100000&type=0"
# status_dict = {u"???": "normal", u"??": "up", u"??": "down"}
status_dict = {"mid": "normal", "buy": "up", "sell": "down"}
url_real_sina = "http://finance.sina.com.cn/realstock/"
url_real_sina_top = "http://vip.stock.finance.sina.com.cn/mkt/#stock_sh_up"
url_real_east = "http://quote.eastmoney.com/sz000004.html"
import gc
import random
import re
import sys
import time

import pandas as pd
# from pandas import DataFrame

from JohnsonUtil import johnson_cons as ct
import singleAnalyseUtil as sl
from JSONData import stockFilter as stf

from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import commonTips as cct

from docopt import docopt
log = LoggerFactory.log
args = docopt(cct.sina_doc, version='SinaMarket')

if args['-d'] == 'debug':
    log_level = LoggerFactory.DEBUG
elif args['-d'] == 'info':
    log_level = LoggerFactory.INFO
else:
    log_level = LoggerFactory.ERROR
log.setLevel(log_level)

def get_tdx_data(load_block_data=None):
    status = False
    vol = ct.json_countVol
    type = ct.json_countType
    cut_num = 1000000
    success = 0
    top_all = pd.DataFrame()
    time_s = time.time()
    # delay_time = 7200
    delay_time = cct.get_delay_time()
    # base_path = tdd.get_tdx_dir()
    # block_path = tdd.get_tdx_dir_blocknew() + '064.blk'
    blkname = '063.blk'
    block_path = tdd.get_tdx_dir_blocknew() + blkname
    lastpTDX_DF = pd.DataFrame()
    indf = pd.DataFrame()
    parserDuraton = cct.DurationArgmain()

    st_key_sort = '7'
    # st_key_sort = '3 2'
    # st_key_sort = 'x 1.1'
    # st_key_sort = 'x2'
    # st_key_sort = '8'
    
    # duration_date = ct.duration_date_week
    duration_date = ct.duration_date_day
    # ct.duration_date_week ->200
    du_date = duration_date
    # resample = 'w'
    # resample = '3d'
    cct.GlobalValues().setkey('resample','d')

    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(
        st_key_sort)
    # st_key_sort = '9'
    # st_key_sort = '7'
    # st_key_sort = ct.sort_value_key_perd23
    instocklastDays = 10
    st = None
    resample = cct.GlobalValues().getkey('resample')

    if st is None and st_key_sort in ['2', '3']:
        st_key_sort = '%s %s' % (
            st_key_sort.split()[0], cct.get_index_fibl())
    time_Rt = time.time()
    market_blk = 'bj'
    top_now = tdd.getSinaAlldf(market=f'{market_blk}', vol=ct.json_countVol, vtype=ct.json_countType)

    time_d = time.time()
    if time_d - time_s > delay_time:
        status_change = True
        time_s = time.time()
        top_all = pd.DataFrame()

    else:
        status_change = False

    if len(top_now) > 1 and len(top_now.columns) > 4:
        if len(top_all) == 0 and len(lastpTDX_DF) == 0:
            cct.get_terminal_Position(position=sys.argv[0])
            time_Rt = time.time()
            top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
                top_now, dl=duration_date,resample=resample)
        elif len(top_all) == 0 and len(lastpTDX_DF) > 0:
            time_Rt = time.time()
            top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)
            # dd=dd.fillna(0)
        else:
            top_all = cct.combine_dataFrame(
                top_all, top_now, col='couts', compare='dff')

        if len(top_all)/len(top_now) > 1.5:
            import ipdb;ipdb.set_trace()
             
        # time_Rt = time.time()
        top_bak = top_all.copy()
        if cct.get_trade_date_status() == 'True':
            for co in ['boll','df2']:
                 # df['dff'] = list(map(lambda x, y, z: round((x + (y if z > 20 else 3 * y)), 1), df.dff.values, df.volume.values, df.ratio.values))
                top_all[co] = list(map(lambda x, y,m , z: (z + (1 if ( x > y ) else 0 )), top_all.close.values,top_all.upper.values, top_all.llastp.values,top_all[co].values))
            # top_bak[top_all.boll != top_bak.boll].boll   top_all[top_all.boll != top_bak.boll].boll

        top_all = top_all[ (top_all.df2 > 0) & (top_all.boll > 0)]

        codelist = top_all.index.tolist()
        if len(codelist) > 0:
            ratio_t = cct.get_work_time_ratio(resample=resample)
            log.debug("Second:vol/vol/:%s" % ratio_t)
            # top_dif['volume'] = top_dif['volume'].apply(lambda x: round(x / ratio_t, 1))
            log.debug("top_diff:vol")
            top_all['volume'] = (
                list(map(lambda x, y: round(x / y / ratio_t, 1), top_all['volume'].values, top_all.last6vol.values)))
            

            
        if st_key_sort.split()[0] in ['4','9'] and 915 < cct.get_now_time_int() < 930:
        # if  915 < cct.get_now_time_int() < 930:
            top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                  top_all['buy'].values, top_all['llastp'].values)))
            top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                   top_all['buy'].values, top_all['lastp'].values)))
       
        elif st_key_sort.split()[0] in ['4','9'] and 926 < cct.get_now_time_int() < 1455 and 'lastbuy' in top_all.columns:
        # elif 926 < cct.get_now_time_int() < 1455 and 'lastbuy' in top_all.columns:

            top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                  top_all['buy'].values, top_all['lastbuy'].values)))
            top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                   top_all['buy'].values, top_all['lastp'].values)))
            #     print top_all.loc['600313'].lastbuy,top_all.loc['600313'].buy,top_all.loc['600313'].lastp
        else:
            top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                  top_all['buy'].values, top_all['lastp'].values)))
            if 'lastbuy' in top_all.columns:
                top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                       top_all['buy'].values, top_all['lastbuy'].values)))
        top_all = top_all.sort_values(
            by=['dff', 'percent', 'volume','ratio' ,'couts'], ascending=[0, 0, 0, 1,1])


        # cct.set_console(width, height, title=[du_date,
        #                 'G:%s' % len(top_all), 'zxg: %s' % (blkname+'-'+market_blk+' resample:'+resample)])


        st_key_sort_status=['4','x2','3'] 

        if st_key_sort.split()[0] not in st_key_sort_status:
            top_temp=top_all.copy()

        elif cct.get_now_time_int() > 830 and cct.get_now_time_int() <= 935:
            #lastl1d
            # top_temp = top_all[(top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
            #lastp1d TopR 1
            # top_temp = top_all[(top_all.low > top_all.lasth1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
            
            # 
            # top_temp = top_all[ (top_all.lastdu > 3 ) & (((top_all.low > top_all.lasth1d) & (top_all.close > top_all.lastp1d)) | ((top_all.low > top_all.lasth2d) & (top_all.close > top_all.lastp2d))) & (top_all.close >= top_all.hmax)]
            #20231221
            top_temp = top_all.copy()
        elif cct.get_now_time_int() > 935 and cct.get_now_time_int() <= 1450:

            # top_temp =  top_all[ ( (top_all.lastp1d > top_all.lastp2d) &(top_all.close >top_all.lastp1d )) | ((top_all.low >= top_all.nlow)) & ((top_all.lastp1d > top_all.ma5d)  & (top_all.close > top_all.ma5d) &(top_all.close > top_all.lastp1d))]

            
            if 'nlow' in top_all.columns:

                if st_key_sort.split()[0]  in st_key_sort_status :
                    

                    #TopR跳空
                    # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene)  & (top_all.topR > 0)]   #20210323
                    
                    # top_temp = top_all[ (top_all.topR > 0)] 
                    # 20210803 mod ral
                    # top_temp = top_all[top_all.close > top_all.ma20d]
                    # top_temp = top_all[(top_all.close > top_all.ma20d) & (top_all.close > top_all.max5)]
                    # top_temp = top_all[(top_all.close > top_all.ma20d) & (top_all.close >= top_all.ene)]
                    
                    #221018change
                    # top_temp = top_all[(top_all.close > top_all.ma10d) & ((top_all.close >= top_all.hmax) | (top_all.up5 > 2) | (top_all.perc3d > 3)) ]
                    #221018 振幅大于6 or 跳空 or 连涨 or upper or 大于hmax or 大于max5
                    # top_temp = top_all[ ((top_all.lastdu > 6 ) & (top_all.perc3d > 2)) | (top_all.topU > 0) | (top_all.topR > 0) | (top_all.close > top_all.hmax) | (top_all.close > top_all.max5)]
                    #20221229  当日跳空高开 or 前11日有跳空 or 当前价大于upper  
                    # top_temp = top_all[  ( (( top_all.open > top_all.lasth1d ) & ( top_all.low > top_all.lasth1d)) | (top_all.topR > 0) ) | ( (top_all.close > top_all.upper) ) & (((top_all.lastdu > 3 ) & (top_all.low <= top_all.ma5d * 1.03) & (top_all.low >= top_all.ma5d *0.98))  | ((top_all.topR > 0) & (top_all.close > top_all.hmax)) )  ]
                    # top_temp = top_all[ ((top_all.lastdu > 3 ) & (top_all.low <= top_all.ma5d * 1.03) & (top_all.low >= top_all.ma5d *0.98))  | (top_all.topR > 0) | (top_all.close > top_all.hmax)  ]

                    #20231221
                    top_temp = top_all.copy()

                else:
                    #TopU > upper
                    # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene)]   #20210323
                    # top_temp = top_all[ (top_all.topR > 0)] 
                    
                    #221018
                    # MA5 > ene and topU > upper
                    # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene) & (top_all.ma5d > top_all.ene)  ] 
                    #20221116 
                    # top_temp = top_all[ ( (( top_all.open > top_all.lasth1d ) & ( top_all.low > top_all.lasth1d)) | (top_all.topR > 0) ) | ( (top_all.close > top_all.upper) )  & (((top_all.lastdu > 3 ) & (top_all.low <= top_all.ma5d * 1.03) & (top_all.low >= top_all.ma5d *0.98))  | ((top_all.topR > 0) & (top_all.close > top_all.hmax)) )  ]
                    
                    #20231221
                    top_temp = top_all.copy()
                    # top_temp = top_temp[ (~top_temp.index.str.contains('688'))]

                    #221018 振幅大于6 or 跳空 or 连涨 or upper or 大于hmax or 大于max5
                    # top_temp = top_all[ ((top_all.lastdu > 6 ) & (top_all.perc3d > 2)) | (top_all.topU > 0) | (top_all.topR > 0) | (top_all.close > top_all.hmax) | (top_all.close > top_all.max5)]

                    #主升浪
                    # top_temp = top_all[(top_all.topU > 0) & ( (top_all.close > top_all.max5) | (top_all.close > top_all.hmax) )] 

                    # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]

                    # ???ne??죬???Ϲ죬һ????գ?һ???ͣ
                # top_temp = top_all[  (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.998) & (top_all.open <= top_all.nlow*1.002)) ]
                # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.99) & (top_all.open <= top_all.nlow*1.01)) ]
            else:
                # top_temp=top_all[((top_all.close > top_all.ma51d)) & (
                #     top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d)]
            
                #TopR跳空
                # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene)  & (top_all.topR > 0)] 
                # top_temp = top_all[ (top_all.topR > 0)] 

                # MA5 > ene and topU > upper
                # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene) & (top_all.ma5d > top_all.ene)  ] # & (top_all.topR > 0)] 

                #20231221
                top_temp = top_all.copy()

        else:

            top_temp=top_all.copy() 

        #clean 688 and st
        # if len(top_temp) > 0:                
        #     top_temp = top_temp[ (~top_temp.index.str.contains('688')) ]


            
        if st_key_sort.split()[0] == 'x':
            top_temp = top_temp[top_temp.topR != 0]



        if st_key_sort.split()[0] in ['1','7']:
            if 'lastbuy' in top_all.columns:
                top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                      top_all['buy'].values, top_all['lastbuy'].values)))
                top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                       top_all['buy'].values, top_all['lastp'].values)))

            if len(top_all) > 0 and top_all.lastp1d[0] == top_all.close[0] and top_all.lastp1d[-1] == top_all.close[-1]:
                print('initf_false ',end='')
                if cct.GlobalValues().getkey('initfilter_false') is None:
                    initfilter_false = cct.read_ini(inifile='filter.ini',category='instock',filterkey='initfilter_false')
                else:
                    initfilter_false = cct.GlobalValues().getkey('initfilter_false')
                if initfilter_false is  None:
                    top_temp = top_all.query('lasto2d > lasto3d > lasto4d and lastp2d > lastp3d >lastp4d and close > lastp2d and lastp2d > ma52d and red > 2 and low > ma52d')
                else:
                    top_temp = eval(f'top_all.query{initfilter_false}')


            else:
                print('initf ',end='')
                if cct.GlobalValues().getkey('initfilter') is None:
                    initfilter = cct.read_ini(inifile='filter.ini',category='instock',filterkey='initfilter')
                else:
                    initfilter = cct.GlobalValues().getkey('initfilter')
                if initfilter is  None:
                    top_temp = top_all.query('lasto1d > lasto2d > lasto3d and lastp1d > lastp2d >lastp3d and close > lastp1d and lastp1d > ma51d and red > 2 and low > ma51d')
                else:
                    top_temp = eval(f'top_all.query{initfilter}')


                # if 915 < cct.get_now_time_int() < 1100:
                #     # top_temp = top_all.query('(lasth1d > upper and lasto1d*0.996 < lastp1d < lasto1d*1.003 and lastl1d <ma201d*1.1 and low > lastp1d*0.999 and close > upper) or (b1_v < 1 and lastp1d > high4  and open > lasth1d and lasth1d > upper1 and lasth2d > upper2 and close > upper and close >lastp1d and not name.str.contains("ST"))')
                #     # top_temp = top_all.query('open > high4 and (low > open*0.99 or low > lasth1d) and open > lasth1d and a1_v > 0')
                #     # top_temp =   top_all.query('close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1 and  ((close-lastp1d)/lastp1d*100) > maxp')
                #     # top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1 and  ((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10 and close > hmax*0.99 and close > max5 and volume > 5')
                    
                #     #高开高走
                #     # top_temp = top_all.query('close >= high4 and (low >= close*0.995 or low >= lasth1d*0.998) and close >= lasth1d*0.998')
                #     # top_temp = top_all.query('lasth1d > upper1 and (lasth2d > upper2*0.998 or (high > upper1 and lasth1d > lasth2d)) and open > lastp1d*0.998 and low >= open*0.998 and a1_v > 0')
                #     top_temp = top_all.query('(lasth1d > upper1 or (open > high4 and lasth1d < high4 and lasth2d < high4)) and (lasth2d > upper2*0.998 or (high > upper1 and lasth1d > lasth2d)) and open > lastp1d*0.998 and low >= open*0.998 and a1_v > 0')

                #     # top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and close > max5*0.99 and close > high4 and volume > 3 and ((((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10) )')
                #     #高开高走,前日大涨高开,开盘最低价 
                #     # top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and close > hmax*0.99 and close > max5 and volume > 4.5 and ((((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10) or (per1d > 8 and open > lasth1d and close >= open and low >open*0.999))')
                #         # top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and open > hmax*0.99 and open > max5 and volume > 5 and ((((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10) or (per1d > 8))')
                #     # top_temp = top_all.query('(low >= open and close > lastp1d and (per1d > 5 or per2d >5) ) or  open > high4 and (low > open*0.99 or low > lasth1d) and open > lasth1d ')
                # elif 1100 <= cct.get_now_time_int() < 1500:
                #     #高开高走,前日大涨高开,回踩前日低点 
                #     # top_temp = top_all.query('open >= high4 and (low >= open*0.995 or low >= lasth1d*0.998) and open >= lasth1d*0.998 and a1_v > 0')
                #     top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and close > max5*0.99 and close > high4 and volume > 1 and ((((close-lastp1d)/lastp1d*100) > maxp) or (per1d > 3 and close > lasth1d  and low >lasth1d))')
                #     # top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and close > max5*0.99 and close > high4 and volume > 1 and per1d > 3 and close > lasth1d  and low >lasth1d')

                #     # top_temp = top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1    and close > max5*0.99 and close > high4 and volume > 3 and ((((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10) or (per1d > 8 and close > lasth1d  and low >lasth1d))')

                #     # top_temp =   top_all.query('close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1 and  ((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10 and a1_v > 0 and close > hmax*0.99 and close > max5 and volume > 3')
                    
                # # elif 1301 <= cct.get_now_time_int() < 1430 :
                # #     # top_temp = top_all.query('(lasto1d*0.996 < lastp1d < lasto1d*1.003 and  lastl1d <ma201d*1.1 and low > lastp1d*0.999) or (b1_v < 1 and per1d > 5 and low >= lastp1d and not name.str.contains("ST"))')
                # #     # top_temp = top_all.query('(ral > 2 and fib > 1 and lasto1d*0.99 < lastp1d < lasto1d*1.1 and  lastl1d <ma201d*1.1 and low > lasth1d) or ((open > lastp1d*1.03 or per1d > 5 or open > hmax) and low >= lastp1d*0.998 and not name.str.contains("ST"))')
                # #     # top_temp = top_all.query('((lasth1d > hmax and lasth2d < hmax ) or(lasth2d > upper and close >upper ) ) and lastl1d < upper and high >upper and percent > 1')
                # #     # top_temp = top_all.query('open > high4 and (low > open*0.99 or low > lasth1d) and open > lasth2d and a1_v > 0')
                # #     # top_temp = top_all.query('(close > df2 and low >= open and close > lastp1d and (per1d > 5 or per2d >5)  and a1_v > 0) or  open > high4 and (low > open*0.99 or low > lasth1d) and open > lasth1d and a1_v > 0')
                # #     top_temp = top_all.query('(close > df2 and low >= open and close > lastp1d and (per1d > 5 or per2d >5) and 3 < bandwidth < 10 ) or  (open > high4 and (low > open*0.999 or low > lasth1d and low > upper) and open > lasth1d) and a1_v > 0')
                # else:
                #     # top_temp = top_all.query('open > high4 and (low > open*0.99 or low > lasth1d) and open > lasth1d')
                #     # top_temp = top_all.query('(low >= open and close > lastp1d and (per1d > 5 or per2d >5) ) or  open > high4 and (low > open*0.999 or low > lasth1d) and open > lasth1d ')
                #     # top_temp = top_all.query('(close > df2 and low >= open and close > lastp1d and (per1d > 5 or per2d >5) and 3 < bandwidth < 10 ) or  (open > high4 and (low > open*0.999 or low > lasth1d and low > upper) and open > lasth1d) and a1_v > 0')
                #     top_temp = top_all.query('lasth1d > upper1 and (lasth2d > upper2*0.998 or (high > upper1 and lasth1d > lasth2d)) and open > lastp1d*0.998 and low >= open*0.998')

        top_end=top_all[-int((ct.PowerCount) / 10):].copy()

        goldstock=len(top_all[(
            top_all.buy >= top_all.lhigh * 0.99) & (top_all.buy >= top_all.llastp * 0.99)])

        top_all=tdd.get_powerdf_to_all(top_all, top_temp)


        
        top_temp=stf.getBollFilter(
            df=top_temp, resample=resample, down=True)
        top_end=stf.getBollFilter(
            df=top_end, resample=resample, down=True)

        search_key = cct.GlobalValues().getkey('search_key')
        if search_key is None:  
            search_key = cct.read_ini(inifile='filter.ini',category='instock')
        if search_key is not None:
            search_query = f'category.str.contains("{search_key}")'
            top_temp = top_temp.query(f"{search_query}")
            
        nhigh = top_temp[top_temp.close > top_temp.nhigh] if 'nhigh'  in top_temp.columns else []
        nlow = top_temp[top_temp.close > top_temp.nlow] if 'nhigh'  in top_temp.columns else []
        print("G:%s Rt:%0.1f dT:%s N:%s T:%s nh:%s nlow:%s" % (goldstock, float(time.time() - time_Rt), cct.get_time_to_date(time_s), cct.get_now_time(), len(top_temp),len(nhigh),len(nlow)))
        top_temp=top_temp.sort_values(by=(market_sort_value),
                                        ascending=market_sort_value_key)
        ct_MonitorMarket_Values=ct.get_Duration_format_Values(
            ct.Monitor_format_trade, market_sort_value[:2])

        if len(st_key_sort.split()) < 2:
            f_sort=(st_key_sort.split()[0] + ' f ')
        else:
            if st_key_sort.find('f') > 0:
                f_sort=st_key_sort
            else:
                f_sort=' '.join(x for x in st_key_sort.split()[
                                  :2]) + ' f ' + ' '.join(x for x in st_key_sort.split()[2:])

        market_sort_value2, market_sort_value_key2=ct.get_market_sort_value_key(
            f_sort, top_all=top_all)


        top_temp2=top_end.sort_values(
            by=(market_sort_value2), ascending=market_sort_value_key2)

        ct_MonitorMarket_Values=ct.get_Duration_format_Values(
            ct_MonitorMarket_Values, replace='b1_v', dest='volume')


        top_dd=cct.combine_dataFrame(
            top_temp.loc[:, ct_MonitorMarket_Values][:10], top_temp2.loc[:, ct_MonitorMarket_Values][:5], append=True, clean=True)
        # print cct.format_for_print(top_dd)

        # table,widths = cct.format_for_print(top_dd[:10],widths=True)
        table, widths=cct.format_for_print(
            top_dd.loc[[col for col in top_dd[:10].index if col in top_temp[:10].index]], widths=True)

    return top_dd



def load_block_data():
    top_all = get_tdx_data()
    # 过滤数据
    filtered_data = [item for item in data['List'] if float(item[5]) >= current_filter and float(item[9]) < 120e8]
    stock_df = [(item[0], item[1], item[2], item[5], item[7], item[6], item[3], item[9], item[10]) for item in filtered_data]
        # [('603257', '中国瑞林', 66.53, 22869810, -6038547, 5.65, 10, 1623342844, '金属钴、基础建设'), ('603500', '祥和实业', 11.64, 17593689, -3234289, 8.98, 5.63, 1998050270, '高铁、轨道交通'), ('001267', '汇绿生态', 15.68, 39016206, 2307337, 4.03, -1.38, 5705049281, '光模块、基础建设')]        
    import ipdb;ipdb.set_trace()
    
    return stock_df
    # try:
    #     is_history = current_date != datetime.now().strftime('%Y-%m-%d')
    #     if is_history:
    #         url = f'https://apphis.longhuvip.com/w1/api/index.php?Index=0&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJ&apiv=w35&c=StockBidYiDong&st=20&Day={current_date.replace("-", "")}'
    #     else:
    #         url = 'https://apphq.longhuvip.com/w1/api/index.php?Index=0&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJ&apiv=w35&c=StockBidYiDong&st=20'

    #     response = requests.get(url)
    #     if is_history:
    #         data = response.json()
    #     else:
    #         data = response.json()

    #     # 过滤数据
    #     filtered_data = [item for item in data['List'] if float(item[2]) > 5 and float(item[3]) > 1e8]
    #     block_df = [(item[0], item[1], item[2], item[3], item[4]) for item in filtered_data]
    #     return block_df
    # except Exception as e:
    #     print(f'加载板块数据失败: {e}')
    #     return []


def load_stock_data(block_code):
    # try:
    #     is_history = current_date != datetime.now().strftime('%Y-%m-%d')
    #     if is_history:
    #         url = f'https://apphis.longhuvip.com/w1/api/index.php?Index=0&IsLB=0&IsZT=0&Isst=1&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJBL&apiv=w35&c=StockBidYiDong&st=60&filter=1&StockID={block_code}&Day={current_date.replace("-", "")}'
    #     else:
    #         url = f'https://apphq.longhuvip.com/w1/api/index.php?Index=0&IsLB=0&IsZT=0&Isst=1&Order=1&PhoneOSNew=2&Token=3463abf8cad359085e58d02b44189e4d&Type=1&UserID=2183031&VerSion=5.13.0.9&a=GetBKJJBL&apiv=w35&c=StockBidYiDong&st=60&filter=1&StockID={block_code}'

    #     response = requests.get(url)
    #     if is_history:
    #         data = response.json()
    #     else:
    #         data = response.json()
    top_all = get_tdx_data(block_code)
    # 过滤数据
    filtered_data = [item for item in data['List'] if float(item[5]) >= current_filter and float(item[9]) < 120e8]
    stock_df = [(item[0], item[1], item[2], item[5], item[7], item[6], item[3], item[9], item[10]) for item in filtered_data]
        # [('603257', '中国瑞林', 66.53, 22869810, -6038547, 5.65, 10, 1623342844, '金属钴、基础建设'), ('603500', '祥和实业', 11.64, 17593689, -3234289, 8.98, 5.63, 1998050270, '高铁、轨道交通'), ('001267', '汇绿生态', 15.68, 39016206, 2307337, 4.03, -1.38, 5705049281, '光模块、基础建设')]        
    return stock_df
    # except Exception as e:
    #     print(f'加载股票数据失败: {e}')
    #     return []


def populate_listbox():
    block_data = load_block_data()
    for item in block_data:
        block_listbox.insert(tk.END, item[1])


def populate_table(event):
    selected_index = block_listbox.curselection()
    if selected_index:
        block_data = load_block_data()
        selected_block = block_data[selected_index[0]]
        block_code = selected_block[0]
        stock_data = load_stock_data(block_code)

        # 清空表格
        for i in stock_tree.get_children():
            stock_tree.delete(i)

        # 填充表格
        for item in stock_data:
            stock_tree.insert('', tk.END, values=item)


def find_tdx_window():
    """查找通达信窗口"""
    global tdx_window_handle

    def enum_windows_callback(hwnd, lparam):
        global tdx_window_handle

        # 获取窗口标题
        title_buffer = ctypes.create_unicode_buffer(256)
        GetWindowTextW(hwnd, title_buffer, 255)
        window_title = title_buffer.value

        # 获取窗口类名
        class_buffer = ctypes.create_unicode_buffer(256)
        GetClassNameW(hwnd, class_buffer, 255)
        window_class = class_buffer.value

        # 查找通达信窗口类名
        if "TdxW_MainFrame_Class" in window_class:
            tdx_window_handle = hwnd
            return False  # 找到后停止枚举

        return True

    # 将Python函数转换为C回调函数
    enum_proc = WNDENUMPROC(enum_windows_callback)

    # 重置通达信窗口句柄
    tdx_window_handle = 0

    # 枚举所有窗口
    EnumWindows(enum_proc, 0)

    if tdx_window_handle != 0:
        status = f"已找到通达信窗口，句柄: {tdx_window_handle}"
    else:
        status = "未找到通达信窗口，请确保通达信已打开"
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - {status}")


def generate_stock_code(stock_code):
    """根据股票代码的第一位数字生成对应的代码"""
    if not stock_code:
        return None

    first_char = stock_code[0]

    if first_char == '6':
        return f"7{stock_code}"
    else:
        return f"6{stock_code}"


def send_to_tdx(stock_code):
    """发送股票代码到通达信"""
    if not stock_code or len(stock_code) != 6 or not stock_code.isdigit():
        messagebox.showerror("错误", "请输入有效的6位股票代码")
        return

    # 生成股票代码
    generated_code = generate_stock_code(stock_code)

    # 更新状态
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - 正在发送...")

    # 在新线程中执行发送操作，避免UI卡顿
    threading.Thread(target=_send_to_tdx_thread, args=(stock_code, generated_code)).start()


def _send_to_tdx_thread(stock_code, generated_code):
    """在线程中执行发送操作"""
    global tdx_window_handle

    try:
        # 获取通达信注册消息代码
        UWM_STOCK = RegisterWindowMessageW("Stock")

        # 发送消息
        if tdx_window_handle != 0:
            # 尝试将生成的代码转换为整数
            try:
                message_code = int(generated_code)
            except ValueError:
                message_code = 0

            # 发送消息
            PostMessageW(tdx_window_handle, UWM_STOCK, message_code, 2)

            # 更新状态
            status = "发送成功"
        else:
            status = "未找到通达信窗口，请确保通达信已打开"

    except Exception as e:
        status = f"发送失败: {str(e)}"

    # 在主线程中更新UI
    root.after(0, _update_ui_after_send, status)


def _update_ui_after_send(status):
    """在发送操作完成后更新UI"""
    # 更新状态
    root.title(f"开盘啦竞价板块观察1.0 + 通达信联动 - {status}")


# def on_table_select(event):
#     """表格行选中事件处理函数"""
#     selected_item = stock_tree.selection()
#     if selected_item:
#         values = stock_tree.item(selected_item, "values")
#         stock_code = values[0]
#         send_to_tdx(stock_code)

def on_table_select(event):
    """Handles table selection and prints the selected item values."""
    item = stock_tree.selection()[0]
    values = stock_tree.item(item, "values")
    print("Selected Item Values:", values)

def sort_column(col):
    """Sorts the table by the specified column."""
    items = [(stock_tree.set(item, col), item) for item in stock_tree.get_children("")]
    # Convert numerical columns to float for proper sorting
    if col in ('现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值'):
        try:
            items = [(float(val), item) for val, item in items]
        except ValueError:
            # Handle cases where value cannot be converted to float (e.g. empty)
            pass
    items.sort()
    for index, (val, item) in enumerate(items):
        stock_tree.move(item, "", index)

# 创建主窗口
root = tk.Tk()
root.title("开盘啦竞价板块观察1.0 + 通达信联动")

# 创建列表框
block_listbox = tk.Listbox(root, width=12)
block_listbox.pack(side=tk.LEFT, fill=tk.Y)
block_listbox.bind("<<ListboxSelect>>", populate_table)

# 创建表格
columns = ('代码', '简称', '现价', '竞价金额', '竞价净额', '竞价涨幅', '实时涨幅', '流通市值', '板块')
stock_tree = ttk.Treeview(root, columns=columns, show='headings')
for col in columns:
    stock_tree.heading(col, text=col)
    # 设置列宽度为100，数据居中对齐
    stock_tree.column(col, width=88, anchor=tk.CENTER)
stock_tree.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
stock_tree.bind("<<TreeviewSelect>>", on_table_select)

# 填充列表框
populate_listbox()

# 查找通达信窗口
find_tdx_window()

# 运行主循环
root.mainloop()
