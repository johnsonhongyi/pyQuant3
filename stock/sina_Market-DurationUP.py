# -*- coding:utf-8 -*-
# !/usr/bin/env python

# import gc
# import random
import re
import sys
import time

import pandas as pd

from JohnsonUtil import johnson_cons as ct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import commonTips as cct
# from logbook import Logger,StreamHandler,SyslogHandler
# from logbook import StderrHandler
# from JohnsonUtil import inStockDb as inDb

# def parseArgmain():
# import argparse
# parser = argparse.ArgumentParser()
# parser.add_argument('dt', type=str, nargs='?', help='20150612')
# return parser




if __name__ == "__main__":
    # parsehtml(downloadpage(url_s))
    # StreamHandler(sys.stdout).push_application()
    # log = LoggerFactory.getLogger('sina_Market-DurationSZ')
    from docopt import docopt
    log = LoggerFactory.log
    args = docopt(cct.sina_doc, version='sina_cxdn')
    # print args,args['-d']
    if args['-d'] == 'debug':
        log_level = LoggerFactory.DEBUG
    elif args['-d'] == 'info':
        log_level = LoggerFactory.INFO
    else:
        log_level = LoggerFactory.ERROR
    # log_level = LoggerFactory.DEBUG if args['-d']  else LoggerFactory.ERROR
    log.setLevel(log_level)

    # log.setLevel(LoggerFactory.DEBUG)
    # handler=StderrHandler(format_string='{record.channel}: {record.message) [{record.extra[cwd]}]')
    # log.level = log.debug
    # error_handler = SyslogHandler('Sina-M-Log', level='ERROR')
    width, height = 166,30

    def set_duration_console(du_date):
        if cct.isMac():
            cct.set_console(width, height)
        else:
            cct.set_console(width, height, title=str(du_date))
    status = False
    vol = ct.json_countVol
    type = ct.json_countType
    success = 0
    top_all = pd.DataFrame()
    time_s = time.time()
    delay_time = 720000
    # delay_time = cct.get_delay_time()
    First = True
    blkname = '062.blk'
    # global block_path
    block_path = tdd.get_tdx_dir_blocknew() + blkname
    status_change = False
    lastpTDX_DF = pd.DataFrame()
    # dl=30
    ptype = 'low'
    # op, ra, duration_date, days = pct.get_linear_model_status('999999', filter='y', dl=dl, ptype=ptype, days=1)
    # duration_date = int(ct.duration_date * 1.5)
    # duration_date = ct.duration_date_up
    # duration_date = ct.duration_date_day
    # duration_date = 10
    duration_date = ct.duration_date_week
    # ct.duration_date_week -> 200
    
    # duration_date = 300
    du_date = duration_date
    # resample = ct.resample_dtype
    cct.GlobalValues().setkey('resample','w')
    # resample = 'w'
    # resample = 'd'
    end_date = None
    ptype = 'low'
    filter = 'y'
    percent_status = 'n'
    if len(str(duration_date)) < 4:
        # duration_date = tdd.get_duration_price_date('999999', dl=duration_date, end=end_date, ptype='dutype')
        du_date = tdd.get_duration_Index_date('999999', dl=duration_date)
        if cct.get_today_duration(du_date) <= 3:
            duration_date = 5
            print(("duaration: %s duration_date:%s" %
                  (cct.get_today_duration(du_date), duration_date)))
        log.info("duaration: %s duration_date:%s" %
                 (cct.get_today_duration(du_date), duration_date))
    set_duration_console(du_date)
    # all_diffpath = tdd.get_tdx_dir_blocknew() + '062.blk'
    parser = cct.MoniterArgmain()
    parserDuraton = cct.DurationArgmain()
    # market_sort_value, market_sort_value_key = ct.get_market_sort_value_key('x1 d f')
    # market_sort_value, market_sort_value_key = ct.get_market_sort_value_key('3 2')
    # market_sort_value, market_sort_value_key = ct.get_market_sort_value_key('1')
    # st_key_sort = ct.sort_value_key_perd23
    st_key_sort = '1'
    # st_key_sort = '3 1'
    # st_key_sort = '3 1'
    # st_key_sort = 'x1 1.1'
    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(st_key_sort)
    st = None
    top_list = []
    while 1:
        try:
            # df = sina_data.Sina().all
            time_Rt = time.time()
            resample = cct.GlobalValues().getkey('resample')
            if st is None:
                st_key_sort = '%s %s' % (
                    st_key_sort.split()[0], cct.get_index_fibl())
            # top_now = tdd.getSinaAlldf(market='060.blk', vol=ct.json_countVol, vtype=ct.json_countType)
            # market_blk = '次新股'
            # market_blk = 'all'
            market_blk = 'all'
            # market_blk = 'indb'

            # market_blk = 'cyb'
            # market_blk = '060'
            # top_now = tdd.getSinaAlldf(market=market_blk, filename='cxg', vol=ct.json_countVol, vtype=ct.json_countType)
            
            top_now = tdd.getSinaAlldf(market=market_blk, vol=ct.json_countVol, vtype=ct.json_countType)
            now_count = len(top_now)
            radio_t = cct.get_work_time_ratio(resample=resample)
            # top_now = top_now[top_now.buy > 0]
            time_d = time.time()
            if time_d - time_s > delay_time:
                status_change = True
                time_s = time.time()
                top_all = pd.DataFrame()
            else:
                status_change = False

            if len(top_now) > 1 or cct.get_work_time():
                # time_Rt = time.time()
                if len(top_all) == 0 and len(lastpTDX_DF) == 0:
                    cct.get_terminal_Position(position=sys.argv[0])

                    top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
                        top_now, lastpTDX_DF=None, dl=duration_date, end=end_date, ptype=ptype, filter=filter, power=ct.lastPower, lastp=False, resample=resample)
                    log.debug("len:%s" % (len(top_all)))
                    top_list = tdd.compute_jump_du_count(top_all,resample=resample)

                elif len(top_all) == 0 and len(lastpTDX_DF) > 0:
                    top_all = top_now
                    top_all = top_all.merge(
                        lastpTDX_DF, left_index=True, right_index=True, how='left')
                    log.info('Top-merge_now:%s' % (top_all[:1]))
                    top_all = top_all[top_all['llow'] > 0]

                else:
                    log.info("start symbol code :%0.2f" %
                             (cct.get_now_time_int()))
                    log.info("diff co:%s" %
                             (set(top_all.columns) - set(top_now.columns)))
                    if 'couts' in top_now.columns.values:
                        if not 'couts' in top_all.columns.values:
                            top_all['couts'] = 0
                            top_all['prev_p'] = 0
                    # for symbol in top_now.index:
                    #     if 'couts' in top_now.columns.values:
                    #         top_all.loc[symbol, ct.columns_now] = top_now.loc[symbol, ct.columns_now]
                    #     else:
                    #         top_all.loc[symbol, ct.columns_now] = top_now.loc[symbol, ct.columns_now]

                    # no_index = top_all.drop([inx for inx in top_all.index  if inx not in top_now.index], axis=0)
                    # no_index.drop([col for col in no_index.columns if col in top_now.columns], axis=1,inplace=True)
                    # no_index = no_index.merge(top_now, left_index=True, right_index=True, how='left')
                    # top_all = top_all.drop([inx for inx in top_all.index  if inx in top_now.index], axis=0)
                    # top_all = pd.concat([top_all, no_index],axis=0)
                    # log.info("for loc code :%0.2f"%(time.time()-time_Rt))
                    #
                    top_all = cct.combine_dataFrame(top_all, top_now)

                # # top_list = tdd.compute_jump_du_count(top_all)
                # if len(top_list) > 0:
                #     top_all = top_all.loc[top_list]
                # else:
                #     top_all = top_all[(top_all.top10 < 3)]

                # top_all = top_all[(top_all.lastdu < 15) & ((top_all.fib > 1) | (top_all.fibl >5)) &( (top_all.vcall < 80) ) &(top_all.top10 < 2)]
                # top_all = top_all[(top_all.top10 < 1)]

                # top_all = top_all.copy()

                if 'trade' in top_all.columns:
                    top_all['buy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                          top_all['buy'].values, top_all['trade'].values)))

                # 判断主升
                # log.debug('top_all:%s'%(len(top_all)))
                if ct.checkfilter and cct.get_now_time_int() > 915 and cct.get_now_time_int() < ct.checkfilter_end_timeDu:
                    top_all = top_all[top_all.low >
                                      top_all.llow * ct.changeRatio]
                    # top_all = top_all[top_all.buy >= top_all.lhigh * ct.changeRatio]
                    log.debug('top_all:%s' % (len(top_all)))

                if cct.get_now_time_int() > 915:
                    top_all = top_all[top_all.buy > 0]

                # log.debug('top_all:%s' % (len(top_all)))
                if st_key_sort.split()[0] == '4' and 926 < cct.get_now_time_int() < 1455  and 'lastbuy' in top_all.columns:
                    top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                          top_all['buy'].values, top_all['lastbuy'].values)))
                    top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                           top_all['buy'].values, top_all['lastp'].values)))
                else:
                    top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                          top_all['buy'].values, top_all['lastp'].values)))
                    if 'lastbuy' in top_all.columns:
                        top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                               top_all['buy'].values, top_all['lastbuy'].values)))
                # top_all['dff'] = (
                #     map(lambda x, y: round((x - y) / y * 100, 1), top_all['buy'].values, top_all['lastp'].values))
                # print top_all.loc['600610',:]
                # top_all = top_all[top_all.trade > 0]
                # if cct.get_now_time_int() >< 932:

                # top_all = top_all[top_all.low > 0]
                # log.debug("top_all.low > 0:%s" % (len(top_all)))
                # top_all.loc['600610','volume':'lvol']
                top_all['volume'] = (
                    list(map(lambda x, y: round(x / y / radio_t, 1), top_all.volume.values, top_all.lvol.values)))

                # if 'op' in top_all.columns:
                #     top_all=top_all[top_all.op >12]
                #     print "op:",len(top_all),

                # top_all = top_all[top_all.volume < 100]
                # print top_all.loc['002504',:]

                # if filter == 'y':
                #     top_all = top_all[top_all.date >= cct.day8_to_day10(duration_date)]

                # log.info('dif1-filter:%s' % len(top_all))
                # print top_all.loc['600533',:]
                # log.info(top_all[:1])
                # top_all = top_all[top_all.buy > top_all.llastp]
                # top_all = top_all[top_all.buy > top_all.lhigh]
                # log.debug('dif2:%s' % len(top_all))
                # top_all['volume'] = top_all['volume'].apply(lambda x: round(x / radio_t, 1))
                # log.debug("top_allf:vol")
                #
                if len(top_all) == 0:
                    print("No G,DataFrame is Empty!!!!!!")
                else:
                    log.debug('dif6 vol:%s' % (top_all[:1].volume))
                    log.debug('dif6 vol>lvol:%s' % len(top_all))

                    # top_all = top_all[top_all.buy >= top_all.open*0.99]
                    # log.debug('dif5 buy>open:%s'%len(top_all))
                    # top_all = top_all[top_all.trade >= top_all.buy]
                    # df['volume']= df['volume'].apply(lambda x:x/100)

                    # goldstock = len(top_all[top_all.buy >= top_all.lhigh * 0.99])
                    goldstock = len(top_all[(top_all.buy >= top_all.lhigh * 0.99)
                                            & (top_all.buy >= top_all.llastp * 0.99)])
                    ## goldstock=len(top_all[top_all.buy >(top_all.high-top_all.low)/2])
                    if resample == 'd':
                        
                        if ptype == 'low':
                            top_all = top_all[top_all.lvol > ct.LvolumeSize]
                            if cct.get_now_time_int() > 1100 and cct.get_now_time_int() < 1330:
                                # if cct.get_now_time_int() > 931 and cct.get_work_time():
                                top_all = top_all[(top_all.volume > ct.VolumeMinR) & (
                                    top_all.volume < ct.VolumeMaxR)]
                            # top_all = top_all[top_all.lvol > 12000]
                            if 'couts' in top_all.columns.values:
                                top_all = top_all.sort_values(by=['dff', 'percent', 'volume', 'couts', 'fibl'],
                                                              ascending=[0, 0, 0, 1, 1])
                            else:
                                top_all = top_all.sort_values(
                                    by=['dff', 'percent', 'ratio'], ascending=[0, 0, 1])
                        else:
                            # top_all['dff'] = top_all['dff'].apply(lambda x: x * 2 if x > 0 else x)
                            top_all = top_all[top_all.lvol > ct.LvolumeSize]
                            top_all['dff'] = top_all['dff'].apply(
                                lambda x: x * 2 if x < 0 else x)
                            if 'couts' in top_all.columns.values:
                                top_all = top_all.sort_values(by=['dff', 'percent', 'volume', 'couts', 'fibl'],
                                                              ascending=[1, 0, 0, 1, 1])
                            else:
                                top_all = top_all.sort_values(
                                    by=['dff', 'percent', 'ratio'], ascending=[1, 0, 1])

                    # top_all=top_all.sort_values(by=['percent','dff','couts','ratio'],ascending=[0,0,1,1])
                    # print cct.format_for_print(top_all[:10])
                    # top_dd = pd.concat([top_all[:5],top_temp[:3],top_all[-3:],top_temp[-3:]], axis=0)

                    if len(top_all) > 0 and top_all.lastp1d[0] == top_all.close[0]:

                        if 915 < cct.get_now_time_int() < 1445:
                            # top_temp = top_all.query('(lasth1d > upper and lasto1d*0.996 < lastp1d < lasto1d*1.003 and lastl1d <ma201d*1.1 and low > lastp1d*0.999 and close > upper) or (b1_v < 1 and lastp1d > high4  and open > lasth1d and lasth1d > upper1 and lasth2d > upper2 and close > upper and close >lastp1d and not name.str.contains("ST"))')
                            # top_temp = top_all.query('open > high4 and (low > open*0.99 or low > lasth2d) and open > lasth2d and a1_v > 0')
                        #     top_temp =  top_all.query('(low >= open and close > lastp2d and (per1d > 5 or per2d >5) and 3 < bandwidth < 10 and a1_v > 0) or  open > high4 and (low > open*0.999 or low > lasth2d) and open > lasth2d and a1_v > 0')
                        # else:
                        #     top_temp = top_all.query('open > high4 and (low > open*0.99 or low > lasth2d) and open > lasth2d')
                            top_temp = top_all.query('open > high4 and (low > open*0.999 or low > lasth2d) and open > lastp2d and close > lasth2d and (high > upper or boll > 1) and close > open*1.01')
                        else:
                            # top_temp = top_all.query('(low >= open*0.99 and close > lasth1d and (per1d > 5 or per2d >5) ) or  open > high4 and (low > open*0.999 or low > lasth1d) and open > lasth1d ')
                            top_temp = top_all.query('open > high4 and (low > open*0.999 or low > lasth2d) and open > lastp2d and close > lasth2d and (high > upper or boll > 1) and close > open*1.01')

                    else:
                        if 915 <= cct.get_now_time_int() < 1445:
                        #     top_temp =   top_all.query('close > upper1 and close > df2 and close > high4 and close > lasth1d and close > lasth2d and close > lasth3d and close > upper1 and  ((close-lastp1d)/lastp1d*100) > maxp and 3 < bandwidth < 10 and close > hmax*0.99 and close > max5 ')
                        # elif 945 <= cct.get_now_time_int() < 1445:
                            # top_temp = top_all.query('(low >= open*0.99 and close > lasth1d and (per1d > 5 or per2d >5) and 3 < bandwidth < 10 and a1_v > 0 ) or  open > high4 and (low > open*0.999 or low > lasth1d) and open > lasth1d and a1_v > 0')
                            top_temp = top_all.query('open > high4 and (low > open*0.999 or low > lasth1d) and open > lastp1d and close > lasth1d and (high > upper or boll > 1) and close > open*1.01 and a1_v > 0')
                        else:
                            # top_temp = top_all.query('(low >= open*0.99 and close > lasth1d and (per1d > 5 or per2d >5) ) or  open > high4 and (low > open*0.999 or low > lasth1d) and open > lasth1d ')
                            top_temp = top_all.query('open > high4 and (low > open*0.999 or low > lasth1d) and open > lastp1d and close > lasth1d and (high > upper or boll > 1) and close > open*1.01')

                    top_end = top_temp[-5:].copy()
                    # top_temp = pct.powerCompute_df(
                    #     top_temp, dl=ct.PowerCountdl, talib=True)
                    # top_end = pct.powerCompute_df(
                    #     top_end, dl=ct.PowerCountdl, talib=True)
                    
                    # if percent_status == 'y' and (
                    #         cct.get_now_time_int() > 915 and cct.get_now_time_int() < 1505) and ptype == 'low':
                    #     # top_all = top_all[top_all.percent >= 0]
                    #     # # top_temp = stf.filterPowerCount(top_all,ct.PowerCount)
                    #     # top_temp = top_all


                    #     #   topU: #high >= df.upper 'eneU': #close >= df.ene
                    #     # 多头排列,topR 跳空,回踩在中轨上.
                    #     #top_all[(top_all.close >top_all.ma20d *0.98) & (top_all.close < top_all.ma20d *1.05) ][:10]
                    #     #close 回调指20W附近

                    #     # top_temp = top_all[(top_all.topU > 0) & (top_all.eneU > 0)] 
                    #     top_temp = top_all.copy() 
                    #     # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]

                        
                    #     top_end = top_all[-5:].copy()
                    #     top_temp = pct.powerCompute_df(
                    #         top_temp, dl=ct.PowerCountdl, talib=True)
                    #     top_end = pct.powerCompute_df(
                    #         top_end, dl=ct.PowerCountdl, talib=True)
                    # # elif percent_status == 'y' and cct.get_now_time_int() > 935 and ptype == 'high' :
                    # elif ptype == 'low':

                    #     # top_temp = top_all[top_all.topR >= 1]
                    #     # top_temp = top_all.copy()
                    #     # top_temp = top_all[(top_all.topU > 0) & (top_all.eneU > 0)] 
                    #     # top_temp = top_all.copy() 
                    #     top_temp = top_all[(top_all.lastl1d >= top_all.lastl2d)   & (top_all.close >= top_all.ma51d)  & (top_all.ma51d >= top_all.ma52d) & (top_all.ma52d >= top_all.ma53d)] 
                    #     # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]

                    #     # top_all = top_all[top_all.percent >= 0]
                    #     # top_temp = stf.filterPowerCount(top_all,ct.PowerCount)
                    #     # top_temp = top_all[ ((top_all.lastp0d >=9.8)  & (top_all.lastp1d < 9) & (top_all.lastp2d < 9) & (top_all.lastp3d < 9) )  | ((top_all.lastp0d <9)  & (top_all.lastp1d < 9) & (top_all.lastp2d < 9) & (top_all.lastp3d < 9)) ][:100]
                    #     # top_temp = top_all[ ((top_all.per1d >=9.8)  & (top_all.per2d < 9) & (top_all.per3d < 9) & (top_all.per4d < 9) )  | ((top_all.per1d <9)  & (top_all.per2d < 9) & (top_all.per3d < 9) & (top_all.per4d < 9)) ][:100]
                    #     # top_temp = top_all[ ((top_all.per1d >=9.8)  & (top_all.per2d < 8) & (top_all.per3d < 8)  ) ][:100]
                    #     # top_temp = top_all[ ((top_all.per1d >=9.8)  & (top_all.per2d < 8) & (top_all.per3d < 8)) | ((top_all.vcra > 8) & (top_all.vchange > 100)) ]
                    #     # top_temp = top_all[ ((top_all.per1d < 8 )  & (top_all.per2d < 5) & (top_all.per3d < 4)) & ((top_all.vcra >= top_all.vcra.mean()) & (top_all.vchange < 220) & (top_all.vchange > 100)) ]

                    #     # 近5天没有涨停记录,次日放量1倍
                    #     # top_temp = top_all[ ( (top_all.top10 < 3) & (top_all.close >= top_all.max5 ) & (top_all.per5d < 9 ) & (top_all.per4d < 9 )  & (top_all.per2d < 9) & (top_all.per3d < 9)) & ((top_all.vcra >= top_all.vcra.std()) & (top_all.vchange < 220) & (top_all.vchange > 50)) ]

                    #     # if cct.get_now_time_int() > 935 and 'nlow' in top_all.columns:
                    #     #     # top_temp = top_all[ (top_all.close  <= top_all.upper * 1.1) & (top_all.open  >= top_all.nlow) & (top_all.close  >= top_all.max5) & (top_all.top10 < 4) & (top_all.top10 >= 0) ]
                    #     #     top_temp = top_all[ (top_all.open  >= top_all.nlow) & (top_all.low  >= top_all.max5) & (top_all.top10 < 3) & (top_all.top10 > 0) ]
                    #     # else:
                    #     #     # top_temp = top_all[ (top_all.close  <= top_all.upper * 1.1) & (top_all.open  >= top_all.low) & (top_all.close  >= top_all.max5) & (top_all.top10 < 4) & (top_all.top10 >= 0) ]
                    #     #     top_temp = top_all[ (top_all.open  >= top_all.low) & (top_all.low  >= top_all.max5) & (top_all.top10 < 3) & (top_all.top10 > 0) ]

                    #     # top_temp = top_all[ (top_all.close >= top_all.hvhigh) &  (top_all.lastp1d >= top_all.upper) & (top_all.low >= top_all.upper)]

                    #     # top_temp = top_all[ ( (top_all.close >= top_all.max5 ) & (top_all.per5d < 8 ) & (top_all.per4d < 8 )  & (top_all.per2d < 5) & (top_all.per3d < 4)) & ((top_all.vcra >= top_all.vcra.mean()) & (top_all.vchange < 150) & (top_all.vchange > 50)) ]
                    #     # 昨日大于upper,今日low大于upper
                    #     # top_temp = top_all[(top_all.lastp1d > top_all.upper) & (top_all.low > top_all.upper) & (top_all.ma5d > top_all.ma10d) & (top_all.close > top_all.max5 ) & (top_all.per5d < 8 ) & (top_all.per4d < 8 )  & (top_all.per2d < 5) & (top_all.per3d < 4) & ((top_all.vcra >= top_all.vcra.mean()) & (top_all.vchange < 150) & (top_all.vchange > 50))]
                    #     # top_temp = top_all[ (top_all.vcra > 70)]
                    #     top_end = top_all[-5:].copy()
                    #     top_temp = pct.powerCompute_df(
                    #         top_temp, dl=ct.PowerCountdl, talib=True)
                    #     # top_temp = top_temp[(top_temp.fib < 2)] if len(top_temp[(top_temp.fib < 2)]) > 0 else top_temp[(top_temp.fib < 3)]
                    #     top_end = pct.powerCompute_df(
                    #         top_end, dl=ct.PowerCountdl, talib=True)
                    # else:
                    #     # top_all = top_all[top_all.percent >= 0]
                    #     top_end = top_all[:5].copy()
                    #     # top_temp = top_all[-ct.PowerCount:].copy()
                    #     top_temp = top_all.copy()
                    #     top_temp = pct.powerCompute_df(
                    #         top_temp, dl=ct.PowerCountdl, talib=True)
                    #     top_end = pct.powerCompute_df(
                    #         top_end, dl=ct.PowerCountdl, talib=True)

                    cct.set_console(width, height,
                                    title=[du_date, 'dT:%s' % cct.get_time_to_date(time_s), 'G:%s' % goldstock,
                                           'zxg: %s' % (blkname + '-' + market_blk+' resample:'+resample)])

                    top_all = tdd.get_powerdf_to_all(top_all, top_temp)
                    top_all = tdd.get_powerdf_to_all(top_all, top_end)
                    
                    # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl,resample=resample)
                    top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl,
                                                 filter=False, ma5d=False, dl=14, percent=False, resample=resample, ene=False, top10=False)

                    
                    #20210816 filter ma5d ma10d
                    # top_temp = top_temp[ (top_temp.close > top_temp.ma5d) & ((top_temp.close > top_temp.hmax))]
                    top_temp = top_temp[ (top_temp.close > top_temp.ma5d) ]


                    print(("N:%s K:%s %s G:%s" % (
                        now_count, len(top_all[top_all['buy'] > 0]),
                        len(top_now[top_now['volume'] <= 0]), goldstock)), end=' ')
                    print("Rt:%0.1f dT:%s N:%s T:%s %s%%" % (float(time.time() - time_Rt), cct.get_time_to_date(time_s), cct.get_now_time(), len(top_temp), round(len(top_temp) / float(ct.PowerCount) * 100, 1)))
                    # top_end = stf.getBollFilter(df=top_end, boll=ct.bollFilter,duration=ct.PowerCountdl)
                    


                    if 'op' in top_temp.columns:
                        if cct.get_now_time_int() > ct.checkfilter_end_timeDu and (int(duration_date) > int(ct.duration_date_sort) or int(duration_date) < 6):
                            top_temp = top_temp.sort_values(by=(market_sort_value),
                                                            ascending=market_sort_value_key)
                        else:
                            top_temp = top_temp.sort_values(by=(market_sort_value),
                                                            ascending=market_sort_value_key)
                            # top_temp = top_temp.sort_values(by=ct.Duration_percentdn_ra,
                            # ascending=ct.Duration_percentdn_ra_key)

                    if st_key_sort.split()[0] == 'x':
                        top_temp = top_temp[top_temp.topR != 0]

                    if cct.get_now_time_int() > 915 and cct.get_now_time_int() < 935:
                        # top_temp = top_temp[ (top_temp['ma5d'] > top_temp['ma10d']) & (top_temp['buy'] > top_temp['ma10d']) ][:10]

                        top_dd = cct.combine_dataFrame(
                            top_temp[:ct.format_limit], top_end, append=True, clean=True)
                        # top_dd = top_dd.drop_duplicates()
                        ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                            ct.Duration_format_buy, market_sort_value[:])
                    else:
                        # top_temp = top_temp[ (top_temp['ma5d'] > top_temp['ma10d']) & (top_temp['trade'] > top_temp['ma10d']) ][:10]
                        # top_temp = top_temp[top_temp['trade'] > top_temp['ma10d']]

                        top_dd = cct.combine_dataFrame(
                            top_temp[:ct.format_limit], top_end, append=True, clean=True)
                        # top_dd = top_dd.drop_duplicates()
                        ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                            ct.Duration_format_trade, market_sort_value[:])

                    ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                        ct_MonitorMarket_Values, replace='b1_v', dest='volume')
                    # ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                    #     ct_MonitorMarket_Values, replace='fibl', dest='top10')
                    # ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                    #     ct_MonitorMarket_Values, replace='perc1d', dest='perc3d')


                    # if 'nhigh' in top_all.columns:
                    #     ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                    #         ct_MonitorMarket_Values, replace='df2', dest='nhigh')
                    # else:
                    #     ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                    #         ct_MonitorMarket_Values, replace='df2', dest='high')




                    
                    top_dd = top_dd.loc[:, ct_MonitorMarket_Values]
                    # print cct.format_for_print(top_dd)
                    # table,widths = cct.format_for_print(top_dd[:9],widths=True)
                    table, widths = cct.format_for_print(
                        top_dd.loc[[col for col in top_dd[:ct.format_limit].index if col in top_temp[:ct.format_limit].index]], widths=True)

                    print(table)
                    cct.counterCategory(top_temp)
                    print(cct.format_for_print(top_dd[-4:], header=False, widths=widths))
                # if cct.get_now_time_int() < 930 or cct.get_now_time_int() > 1505 or (cct.get_now_time_int() > 1125 and cct.get_now_time_int() < 1505):
                # print cct.format_for_print(top_all[-10:])
                # print top_all.loc['000025',:]
                # print "staus",status

                # if status:
                #     for code in top_dd[:10].index:
                #         code = re.findall('(\d+)', code)
                #         if len(code) > 0:
                #             code = code[0]
                #             kind = sl.get_multiday_ave_compare_silent(code)
                            # print top_all[top_all.low.values==0]

                            # else:
                            #     print "\t No RealTime Data"
            else:
                print("\tNo Data")
            int_time = cct.get_now_time_int()
            if cct.get_work_time():
                if int_time < ct.open_time:
                    cct.sleep(ct.sleep_time)
                elif int_time < 930:
                    cct.sleep((930 - int_time) * 55)
                    # top_all = pd.DataFrame()
                    time_s = time.time()
                else:
                    cct.sleep(ct.duration_sleep_time)
            elif cct.get_work_duration():
                while 1:
                    cct.sleep(ct.duration_sleep_time)
                    if cct.get_work_duration():
                        print(".", end=' ')
                        cct.sleep(ct.duration_sleep_time)
                    else:
                        # top_all = pd.DataFrame()
                        cct.sleeprandom(60)
                        time_s = time.time()
                        print(".")
                        break
            else:
                raise KeyboardInterrupt("StopTime")
        except (KeyboardInterrupt) as e:
            st = cct.cct_raw_input(ct.RawMenuArgmain() % (market_sort_value))

            if len(st) == 0:
                status = False
            elif (len(st.split()[0]) == 1 and st.split()[0].isdigit()) or st.split()[0].startswith('x'):
                st_l = st.split()
                st_k = st_l[0]
                # if st_k in list(ct.Market_sort_idx.keys()) and len(top_all) > 0:
                if st_k in list(ct.Market_sort_idx.keys()):
                    st_key_sort = st
                    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(
                        st_key_sort, top_all=top_all)
                else:
                    log.error("market_sort key error:%s" % (st))
                    cct.sleeprandom(5)

            elif st.lower() == 'r':
                dir_mo=eval(cct.eval_rule)
                if len(top_temp) > 0 and top_temp.lastp1d[0] == top_temp.close[0]:
                    cct.evalcmd(dir_mo,workstatus=False,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,resample=resample)
                else:
                    cct.evalcmd(dir_mo,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,resample=resample)

            # elif st.lower() == 'g' or st.lower() == 'go':
            #     status = True
            #     for code in top_dd[:10].index:
            #         code = re.findall('(\d+)', code)
            #         if len(code) > 0:
            #             code = code[0]
            #             kind = sl.get_multiday_ave_compare_silent(code)
            elif st.lower() == 'clear' or st.lower() == 'c':
                top_all = pd.DataFrame()
                time_s = time.time()
                status = False
            elif st.startswith('dd') or st.startswith('dt'):
                # dl = st.split()
                args = parserDuraton.parse_args(st.split()[1:])
                if len(str(args.start)) > 0:
                    end_date = args.end
                    duration_date = args.start
                    if len(str(duration_date)) < 4:
                        du_date = tdd.get_duration_Index_date(
                            '999999', dl=int(duration_date))
                        # print duration_date
                        ct.PowerCountdl = duration_date
                    set_duration_console(du_date)
                    time_s = time.time()
                    status = False
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()

            elif st.startswith('3d') or st.startswith('d') or st.startswith('5d') or st.startswith('m'):
                if st.startswith('3d'):
                    cct.GlobalValues().setkey('resample','3d')
                    duration_date = ct.Resample_LABELS_Days[cct.GlobalValues().getkey('resample')]
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()
                elif st.startswith('d'):
                    cct.GlobalValues().setkey('resample','d')
                    duration_date = ct.Resample_LABELS_Days[cct.GlobalValues().getkey('resample')]
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()
                elif st.startswith('5d'):
                    cct.GlobalValues().setkey('resample','w')
                    duration_date = ct.Resample_LABELS_Days[cct.GlobalValues().getkey('resample')]
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()
                elif st.startswith('m'):
                    cct.GlobalValues().setkey('resample','m')
                    duration_date = ct.Resample_LABELS_Days[cct.GlobalValues().getkey('resample')]
                    top_all = pd.DataFrame()
                    lastpTDX_DF = pd.DataFrame()

            elif st.startswith('w') or st.startswith('a'):
                args = cct.writeArgmain().parse_args(st.split())
                codew = stf.WriteCountFilter(
                    top_temp, 'ra', writecount=args.dl)
                if args.code == 'a':
                    cct.write_to_blocknew(block_path, codew)
                    # sl.write_to_blocknew(all_diffpath, codew)
                else:
                    # codew = stf.WriteCountFilter(top_temp)
                    cct.write_to_blocknew(block_path, codew, False)
                    # sl.write_to_blocknew(all_diffpath, codew, False)
                print("wri ok:%s" % block_path)
                cct.sleeprandom(ct.duration_sleep_time / 2)
            elif st.startswith('sh'):
                while 1:
                    input = input("code:")
                    if len(input) >= 6:
                        args = parser.parse_args(input.split())
                        if len(str(args.code)) == 6:
                            # print args.code
                            if args.code in top_temp.index.values:
                                lhg.get_linear_model_histogram(args.code, start=top_temp.loc[args.code, 'date'],
                                                               end=args.end, vtype=args.vtype,
                                                               filter=args.filter)
                    elif input.startswith('q'):
                        break
                    else:
                        pass
            elif st.startswith('q') or st.startswith('e'):
                print("exit:%s" % (st))
                sys.exit(0)
            else:
                print("input error:%s" % (st))
        except (IOError, EOFError, Exception) as e:
            print("Error", e)
            import traceback
            traceback.print_exc()
            cct.sleeprandom(ct.duration_sleep_time / 2)

'''
{symbol:"sz000001",code:"000001",name:"平安银行",trade:"0.00",pricechange:"0.000",changepercent:"0.000",buy:"12.36",sell:"12.36",settlement:"12.34",open:"0.00",high:"0.00",low:"0",volume:0,amount:0,ticktime:"09:17:55",per:7.133,pb:1.124,mktcap:17656906.355526,nmc:14566203.350486,turnoverratio:0},
{symbol:"sz000002",code:"000002",name:"万  科Ａ",trade:"0.00",pricechange:"0.000",changepercent:"0.000",buy:"0.00",sell:"0.00",settlement:"24.43",open:"0.00",high:"0.00",low:"0",volume:0,amount:0,ticktime:"09:17:55",per:17.084,pb:3.035,mktcap:26996432.575,nmc:23746405.928119,turnoverratio:0},

python -m cProfile -s cumulative timing_functions.py
http://www.jb51.net/article/63244.htm

'''
