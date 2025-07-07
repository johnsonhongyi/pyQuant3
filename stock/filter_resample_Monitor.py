# -*- coding:utf-8 -*-
# !/usr/bin/env python

# import sys
# reload(sys)
# sys.setdefaultencoding('gbk')

#
# reload(sys)
#
# sys.setdefaultencoding('utf-8')
# url_s = "http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=0&type=1"
# url_b = "http://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill_all.php?num=100&page=1&sort=ticktime&asc=0&volume=100000&type=0"
# # status_dict = {u"???": "normal", u"??": "up", u"??": "down"}
# status_dict = {"mid": "normal", "buy": "up", "sell": "down"}
# url_real_sina = "http://finance.sina.com.cn/realstock/"
# url_real_sina_top = "http://vip.stock.finance.sina.com.cn/mkt/#stock_sh_up"
# url_real_east = "http://quote.eastmoney.com/sz000004.html"
import random
import re
import sys
import time

from pandas import DataFrame 
# from bs4 import BeautifulSoup
# from pandas import DataFrame

from JohnsonUtil import johnson_cons as ct
from JSONData import stockFilter as stf

from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import commonTips as cct
# cct.set_ctrl_handler()





if __name__ == "__main__":
    # parsehtml(downloadpage(url_s))
    # log = LoggerFactory.getLogger('SinaMarket')
    # log.setLevel(LoggerFactory.DEBUG)

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

    if cct.isMac():
        width, height = 166, 25
        cct.set_console(width, height)
    else:
        width, height = 166, 25
        cct.set_console(width, height)
        # cct.terminal_positionKey_triton

    # cct.set_console(width, height)
    # if cct.isMac():
    #     cct.set_console(108, 16)
    # else:
    #     cct.set_console(100, 16)
    status = False
    vol = ct.json_countVol
    type = ct.json_countType
    cut_num = 1000000
    success = 0
    top_all = DataFrame()
    time_s = time.time()
    # delay_time = 7200
    delay_time = cct.get_delay_time()
    # base_path = tdd.get_tdx_dir()
    # block_path = tdd.get_tdx_dir_blocknew() + '064.blk'
    blkname = '063.blk'
    block_path = tdd.get_tdx_dir_blocknew() + blkname

    # from JohnsonUtil import inStockDb as inDb
    # indf = inDb.showcount(inDb.selectlastDays(0))

    # indf = inDb.showcount(inDb.selectlastDays(2),sort_date=True)
    # if len(indf) == 0:
    #     indf = inDb.showcount(inDb.selectlastDays(3),sort_date=True)

    # if len(indf) > 0 and cct.creation_date_duration(block_path) > 1:
    #     cct.write_to_blocknew(block_path, indf.code.tolist(),append=False,doubleFile=False,keep_last=0,dfcf=False)
    # else:
    #     if cct.creation_date_duration(block_path) > 1:
    #         log.error("indb last1days is None")
               
    lastpTDX_DF = DataFrame()
    indf = DataFrame()
    parserDuraton = cct.DurationArgmain()
    # The above code is a comment in Python. It is not doing anything in terms of code execution. It
    # is used to provide information or explanations about the code to other developers or to remind
    # oneself about the purpose of the code.

    # duration_date = ct.duration_date_day
    # du_date = duration_date
    # resample = 'd'

    # if len(str(duration_date)) < 4:
    #     # duration_date = tdd.get_duration_price_date('999999', dl=duration_date, end=end_date, ptype='dutype')
    #     du_date = tdd.get_duration_Index_date('999999', dl=duration_date)
    #     if cct.get_today_duration(du_date) <= 3:
    #         duration_date = 5
    #         print(("duaration: %s duration_date:%s" %
    #               (cct.get_today_duration(du_date), duration_date)))
    #     log.info("duaration: %s duration_date:%s" %
    #              (cct.get_today_duration(du_date), duration_date))


    # st_key_sort = '4'
    st_key_sort = '1'
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
    while 1:
        try:
            resample = cct.GlobalValues().getkey('resample')

            if st is None and st_key_sort in ['2', '3']:
                st_key_sort = '%s %s' % (
                    st_key_sort.split()[0], cct.get_index_fibl())
            time_Rt = time.time()
            
            # if len(indf) == 0:
            #     indf = inDb.showcount(inDb.selectlastDays(instocklastDays),sort_date=True)
            
            # if len(indf) == 0:
            #     indf = inDb.showcount(inDb.selectlastDays(instocklastDays + 2),sort_date=True)
                
            # if len(indf) > 0 and cct.creation_date_duration(block_path) > 1:
            #     cct.write_to_blocknew(block_path, indf.code.tolist(),append=False,doubleFile=False,keep_last=0,dfcf=False)
            # else:
            #     if cct.creation_date_duration(block_path) > 1:
            #         log.error("indb last1days is None")

            # if len(indf) > 0 and cct.creation_date_duration(block_path) > 1:
            #     cct.write_to_blocknew(block_path, indf.code.tolist(),append=False,doubleFile=False,keep_last=0,dfcf=False)
            # else:
            #     if cct.creation_date_duration(block_path) > 1:
            #         log.error("indb last1days is None")

            market_blk = 'all'
            # market_blk = 'bj'
            # top_now = tdd.getSinaAlldf(market=f'{indf.code.tolist()}+{market_blk}', vol=ct.json_countVol, vtype=ct.json_countType)
            top_now = tdd.getSinaAlldf(market=f'{market_blk}', vol=ct.json_countVol, vtype=ct.json_countType)

            time_d = time.time()
            if time_d - time_s > delay_time:
                status_change = True
                time_s = time.time()
                top_all = DataFrame()

            else:
                status_change = False

            if len(top_now) > 1 and len(top_now.columns) > 4:

                if len(top_all) == 0 and len(lastpTDX_DF) == 0:
                    cct.get_terminal_Position(position=sys.argv[0])
                    time_Rt = time.time()
                    top_all_d, lastpTDX_DF_d = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['d'],resample='d')
                    top_all_3d, lastpTDX_DF_3d = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['3d'],resample='3d')
                    top_all_w, lastpTDX_DF_w = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['w'],resample='w')
                    top_all_m, lastpTDX_DF_m = tdd.get_append_lastp_to_df(top_now, dl=ct.Resample_LABELS_Days['m'],resample='m')
                elif len(top_all) == 0 and len(lastpTDX_DF) > 0:
                    time_Rt = time.time()
                    top_all_d = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF_d)
                    top_all_3d = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF_3d)
                    top_all_w = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF_w)
                    top_all_m = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF_m)
                    # dd=dd.fillna(0)
                else:
                    top_all_d = cct.combine_dataFrame(top_all_d, top_now, col='couts', compare='dff')
                    top_all_3d = cct.combine_dataFrame(top_all_3d, top_now, col='couts', compare='dff')
                    top_all_w = cct.combine_dataFrame(top_all_w, top_now, col='couts', compare='dff')
                    top_all_m = cct.combine_dataFrame(top_all_m, top_now, col='couts', compare='dff')

                top_all = top_all_d


                if cct.get_trade_date_status() == 'True':
                    for co in ['boll','df2']:
                         # df['dff'] = list(map(lambda x, y, z: round((x + (y if z > 20 else 3 * y)), 1), df.dff.values, df.volume.values, df.ratio.values))
                        top_all[co] = list(map(lambda x, y,m , z: (z + (1 if ( x > y ) else 0 )), top_all.close.values,top_all.upper.values, top_all.llastp.values,top_all[co].values))
                    # top_bak[top_all.boll != top_bak.boll].boll   top_all[top_all.boll != top_bak.boll].boll

                codelist = top_all.index.tolist()
                if len(codelist) > 0:
                    ratio_t = cct.get_work_time_ratio(resample=resample)
                    log.debug("Second:vol/vol/:%s" % ratio_t)
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
                top_all = top_all.sort_values(
                    by=['dff', 'percent', 'volume','ratio' ,'couts'], ascending=[0, 0, 0, 1,1])

                cct.set_console(width, height, title=[du_date,
                                'G:%s' % len(top_all), 'zxg: %s' % (blkname+'-'+market_blk+' resample:'+resample)])



                st_key_sort_status=['4','x2','3'] 


                if st_key_sort.split()[0] not in st_key_sort_status:
                    top_temp=top_all.copy()

                elif cct.get_now_time_int() > 830 and cct.get_now_time_int() <= 935:
                    # top_temp = top_all[(top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
                    #lastp1d TopR 1
                    # top_temp = top_all[(top_all.low > top_all.lasth1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
                    
                    # 
                    # top_temp = top_all[ (top_all.lastdu > 3 ) & (((top_all.low > top_all.lasth1d) & (top_all.close > top_all.lastp1d)) | ((top_all.low > top_all.lasth2d) & (top_all.close > top_all.lastp2d))) & (top_all.close >= top_all.hmax)]
                    #20231221
                    top_temp = top_all.copy()
                    # top_temp = top_all[ (top_all.close >= top_all.lastp2d) ]
                    # top_now.loc['002761'].    
                    # top_temp =  top_all[( ((top_all.top10 >0) | (top_all.boll >0)) & (top_all.lastp1d > top_all.ma5d) & (top_all.close > top_all.lastp1d))]
                    # top_temp =  top_all[((top_all.lastp1d < top_all.ma5d) & (top_all.close > top_all.lastp1d))]
                    # top_temp =  top_all[((top_all.topR < 2) & (top_all.close > top_all.upper) & (top_all.close > top_all.lastp1d))]
                    # top_temp =  top_all[((top_all.topR >0) & (top_all.top10 >1) &   (top_all.close > top_all.upper) & (top_all.close > top_all.ma5d))]
                    # top_temp =  top_all[((top_all.boll >0) & (top_all.close > top_all.lastp1d))]

                    # top_all[(top_all.low >= top_all.nlow)& (top_all.high > top_all.nhigh)]
                elif cct.get_now_time_int() > 935 and cct.get_now_time_int() <= 1450:

                    # top_temp =  top_all[ ( (top_all.lastp1d > top_all.lastp2d) &(top_all.close >top_all.lastp1d )) | ((top_all.low >= top_all.nlow)) & ((top_all.lastp1d > top_all.ma5d)  & (top_all.close > top_all.ma5d) &(top_all.close > top_all.lastp1d))]

                    # top_temp =  top_all[ ((top_all.top10 >0) | (top_all.boll >0))  & (top_all.lastp1d > top_all.ma5d)  & ((top_all.low > top_all.lastl1d) | (top_all.low == top_all.open))]
                    # top_temp =  top_all[ ( (top_all.lastp1d > top_all.ma5d) ) ]
                    # top_temp =  top_all[(top_all.topR < 2)  & (top_all.close > top_all.upper) & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                    # top_temp =  top_all[((top_all.topR >0) & (top_all.top10 >1) &   (top_all.close > top_all.upper) & (top_all.low > top_all.lastl1d) & (top_all.close > top_all.ma5d) )]
                    # top_temp =  top_all[(top_all.boll >0)  & ((top_all.low > top_all.upper) | (top_all.low == top_all.open))]
                    # top_temp =  top_all[(top_all.boll >0)  & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                    # top_temp =  top_all[(top_all.topR < 2) & (top_all.close >= top_all.nhigh) & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                    
                    if 'nlow' in top_all.columns:

                        # if st_key_sort == '4':
                        if st_key_sort.split()[0]  in st_key_sort_status :
                            # top_temp = top_all[ (top_all.topR > 0) & ((top_all.close >= top_all.nclose)) & ((top_all.open > top_all.lastp1d)) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.open >= top_all.nlow) ]

                            # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) & (top_all.ma5d > top_all.ma10d)) & ((top_all.close >= top_all.nclose)) & ((top_all.open > top_all.lastp1d)) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.open >= top_all.nlow) ]

                            # 3?ma5?ģ?ma5d>ma10d,open???
                            # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                                # & (top_all.ma5d > top_all.ma10d)) & (top_all.open >= top_all.nlow) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene)) ]

                            # max5>hmax,low>last1d,per1d,2d,3d>-1,per1d >ma51d...

                            # top_temp = top_all[((top_all.max5 > top_all.hmax) & (top_all.ma5d > top_all.ma10d)) & (top_all.low > top_all.lastl1d)
                            #                    & (top_all.low > top_all.lastl1d) & ( ((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma51d)) \
                            #                     & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma52d)) \
                            #                     & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma53d)) )]

                            # max5 < top_all.hmax ,??ת???
                            # top_temp = top_all[((top_all.max5 < top_all.hmax) & ((top_all.close > top_all.hmax) | (top_all.close > top_all.max5)) )]
                            # top_temp = top_all[ (top_all.max5 < top_all.hmax) & ((top_all.close > top_all.hmax) | (top_all.close > top_all.max5))
                            #             & (top_all.low > top_all.ma51d) 
                            #             & (((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma10d))
                            #             & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma10d))
                            #             & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma10d)))]

                            #topR and nlow > lastp1d
                            # top_temp = top_all[(top_all.low >= top_all.lasth1d) & (top_all.nlow > top_all.lastp1d) & (top_all.close > top_all.nclose) ]
                            
                           
                            # top_temp = top_all[(top_all.close / top_all.hmax > 1.1) & (top_all.close / top_all.hmax < 1.5)] 
                            # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene) & (top_all.low > top_all.lastl1d)] 
                            # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene)] 
                            

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
                            # top_temp = top_all[ (top_all.close >= top_all.lastp2d) ]

                            # top_temp = top_all[ ((top_all.close >= top_all.lastp1d) | ((top_all.low > top_all.lasth2d) & (top_all.close > top_all.lastp2d))) & (top_all.close >= top_all.hmax)]

                            # & (top_all.close >= top_all.hmax) & (top_all.hmax >= top_all.max5) 
                            #主升浪
                            # top_temp = top_all[(top_all.topU > 0) & ( (top_all.close > top_all.max5) | (top_all.close > top_all.hmax) ) & (top_all.topR > 0)] 
                            # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]
                            # top_temp = top_temp[ (~top_temp.index.str.contains('688'))]
                            # top_temp[ (top_temp.index.str.contains('688'))][:1]
                            # top_all[ (~top_all.index.str.contains('688'))  &(top_all.topU > 0)]  

                            # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                            # & (top_all.ma5d > top_all.ma10d)) & (top_all.open >= top_all.nlow) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene)) ]

                        else:
                            #
                            # top_temp = top_all[ ((top_all.close >= top_all.ene)) & (top_all.close >= top_all.upper) & (top_all.topR > 0) & (top_all.top10 >= 0) ]

                            # 3?ma5?ģ?ma5d>ma10d,close > ene,lastp1d>ene
                            # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) & (top_all.ma5d > top_all.ma10d)) & ((top_all.close >= top_all.ene)) & (top_all.close >= top_all.upper) & (top_all.topR > 0) & (top_all.top10 >= 0) ]
                            # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                                # & (top_all.ma5d > top_all.ma10d)) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene))  & (top_all.topR > 0) & (top_all.top10 > 0) ]

                            # max5 > hmax(30)???
                            # top_temp = top_all[((top_all.max5 > top_all.hmax) & ( top_all.open >= top_all.nlow) &( top_all.close > top_all.lastp1d)) ]
                            # top_temp = top_all[((top_all.max5 > top_all.hmax))]

                            # max5>hmax,low>last1d,per1d,2d,3d>-1,per1d >ma51d...
                            # top_temp=top_all[((top_all.max5 > top_all.hmax) & (top_all.ma5d > top_all.ma10d)) & (top_all.low > top_all.ma51d)
                            #                     & (((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma10d))
                            #                     & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma10d))
                            #                     & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma10d)))]

                            #topR and 
                            # top_temp = top_all[(top_all.low > top_all.lasth1d) & (top_all.close > top_all.lastp1d) & (top_all.close > top_all.ma10d)]
                            # top_temp = top_temp[~top_temp.name.str.contains('ST')]
                            # top_temp = top_all[(top_all.topU > 0) & (top_all.close > top_all.ene) & (top_all.lastp1d > top_all.ene) & (top_all.topR > 0)] 
                           
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

                        # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]
                        # top_temp = top_temp[ (~top_temp.index.str.contains('688'))]
                        # top_temp = top_all[  (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.998) & (top_all.open <= top_all.nlow*1.002)) ]
                        # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
                else:

                    # if st_key_sort.split()[0] == '4':  #20210323   跳空缺口,max5 大于 hmax 或者 max5上轨
                    #     # top_temp = top_all[(top_all.topR > 0) & ( (top_all.max5 > top_all.hmax) | (top_all.max5 > top_all.upper) )] 
                    #     top_temp = top_all[ ( (top_all.topR > 0) ) |  ((top_all.close > top_all.ma20d) & (top_all.close >= top_all.ene))]

                    # else:

                    #     top_temp=top_all.copy()
                    top_temp=top_all.copy() 
                    # top_temp = top_temp[ (~top_temp.index.str.contains('688')) & (~top_temp.name.str.contains('ST'))]

                tm_code = top_all_m.query('lasth1d > lasth2d')
                tw_code = top_all_w.query('lasth1d > lasth2d')
                t3d_code = top_all_3d.query('lasth1d > lasth2d')
                td_code = top_all_d.query('lasth1d > lasth2d')
                #clean 688 and st
                # if len(top_temp) > 0:                
                code_f =  list(set(tm_code.index) & set(tw_code.index) & set(t3d_code.index)  & set(td_code.index))
                #     top_temp = top_temp[ (~top_temp.index.str.contains('688')) ]
                print(f'code_f:{len(code_f)},code_d:{len(td_code)}, code_3d:{len(t3d_code)}, code_w:{len(tw_code)}, code_w:{len(tm_code)}')
                    
                if st_key_sort.split()[0] == 'x':
                    top_temp = top_temp[top_temp.topR != 0]


                if len(code_f) > 10:
                    top_temp = top_all.loc[code_f]
                # '''

                # if cct.get_now_time_int() > 830 and cct.get_now_time_int() <= 935:
                #     top_temp = top_all[ ((top_all.topU > 0 ) | (top_all.top10 > 0) | (top_all.topR > 0) | (top_all.top0 > 0)) & (top_all.lastl1d > top_all.ma5d)]
                # elif cct.get_now_time_int() > 935 and cct.get_now_time_int() <= 1100:
                #     if 'nlow' in top_all.columns:
                #         top_temp = top_all[ ((top_all.topU > 0 ) | (top_all.top10 > 0) | (top_all.topR > 0) | (top_all.top0 > 0)) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d) & (top_all.low >= top_all.nlow))]
                #     else:
                #          top_temp = top_all[ ((top_all.topU > 0 ) | (top_all.top10 > 0) | (top_all.topR > 0) | (top_all.top0 > 0)) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d))]
                #         # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d))]
                # else:
                #     # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d))]
                #     if 'nlow' in top_all.columns:
                #         top_temp = top_all[ ((top_all.topU > 0 ) | (top_all.top10 > 0) | (top_all.topR > 0) | (top_all.top0 > 0)) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d) & (top_all.low >= top_all.nlow))]
                #     else:
                #          top_temp = top_all[ ((top_all.topU > 0 ) | (top_all.top10 > 0) | (top_all.topR > 0) | (top_all.top0 > 0)) & ((top_all.lastl1d > top_all.ma5d) &  (top_all.low >= top_all.ma5d))]

                # dd =top_all[(top_all.boll >0) &(top_all.df2 >0) &(top_all.low >= top_all.ma20d) &(top_all.low <= top_all.ma20d *1.05)]

                # if cct.get_now_time_int() > 925 and cct.get_now_time_int() <= 1450:
                #     if 'nlow' in top_temp.columns:                #                           top_all['buy'].values, top_all['lastp'].values))
                #         # top_temp = top_temp[(top_temp.open > top_temp.lastp1d) & ((top_temp.low >= top_temp.nlow) | (top_temp.low > top_temp.lastl1d))]
                #         # top_temp = top_temp[(top_temp.low > top_temp.lastl1d) & ((top_temp.low >= top_temp.nlow) | (top_temp.low > top_temp.lastp1d))]
                #         top_temp = top_temp[(top_temp.low > top_temp.lastl1d) & (top_temp.low >= top_temp.nlow) & (top_temp.top10 > 0)]
                #     else:
                #         if cct.get_now_time_int() > 915 and cct.get_now_time_int() <= 925:
                #             # top_temp = top_temp[(top_temp.close > top_temp.lastp1d) & (top_temp.low > top_temp.lastl1d)]
                #             # top_temp = top_temp[(top_temp.close > top_temp.lastp1d) & (top_temp.close > top_temp.lastl1d)]
                #             top_temp = top_temp[(top_temp.low > top_temp.lastl1d)  & (top_temp.top10 > 0)]
                #         else:
                #             # top_temp = top_temp[(top_temp.close > top_temp.lastp1d) & (top_temp.low > top_temp.lastl1d)]
                #             top_temp = top_temp[(top_temp.low > top_temp.lastl1d) & (top_temp.low >= top_temp.nlow) & (top_temp.top10 > 0)]

                # top_temp = stf.filterPowerCount(top_temp,ct.PowerCount,down=True)

                top_end=top_all[-int((ct.PowerCount) / 10):].copy()
                # top_temp=pct.powerCompute_df(top_temp, dl=ct.PowerCountdl)
                # top_end=pct.powerCompute_df(top_end, dl=ct.PowerCountdl)
                goldstock=len(top_all[(
                    top_all.buy >= top_all.lhigh * 0.99) & (top_all.buy >= top_all.llastp * 0.99)])

                top_all=tdd.get_powerdf_to_all(top_all, top_temp)

                # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl, filter=False)
                # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl, filter=False, ma5d=False, dl=14, percent=False, resample='d')
                # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl, filter=True, ma5d=True, dl=14, percent=False, resample=resample)
                
                top_temp=stf.getBollFilter(
                    df=top_temp, resample=resample, down=True)
                top_end=stf.getBollFilter(
                    df=top_end, resample=resample, down=True)

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
                
                # ct_MonitorMarket_Values2=ct.get_Duration_format_Values(
                #     ct.Monitor_format_trade, market_sort_value2[:2])

                top_temp2=top_end.sort_values(
                    by=(market_sort_value2), ascending=market_sort_value_key2)

                ct_MonitorMarket_Values=ct.get_Duration_format_Values(
                    ct_MonitorMarket_Values, replace='b1_v', dest='volume')
                # ct_MonitorMarket_Values=ct.get_Duration_format_Values(
                #     ct_MonitorMarket_Values, replace='fibl', dest='top10')

                # ct_MonitorMarket_Values2=ct.get_Duration_format_Values(
                #     ct_MonitorMarket_Values2, replace='b1_v', dest='volume')
                # ct_MonitorMarket_Values2=ct.get_Duration_format_Values(
                #     ct_MonitorMarket_Values2, replace='fibl', dest='top10')



                # if 'nhigh' in top_all.columns:
                #     ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                #         ct_MonitorMarket_Values, replace='df2', dest='nhigh')
                # else:
                #     ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                #         ct_MonitorMarket_Values, replace='df2', dest='high')


                # loc ral
                # top_temp[:5].loc[:,['name','ral']


                # if st_key_sort == '1' or st_key_sort == '7':
                # if st_key_sort == '1':
                #     top_temp=top_temp[top_temp.per1d < 8]

                top_dd=cct.combine_dataFrame(
                    top_temp.loc[:, ct_MonitorMarket_Values][:10], top_temp2.loc[:, ct_MonitorMarket_Values][:5], append=True, clean=True)
                # print cct.format_for_print(top_dd)

                # table,widths = cct.format_for_print(top_dd[:10],widths=True)
                table, widths=cct.format_for_print(
                    top_dd.loc[[col for col in top_dd[:9].index if col in top_temp[:10].index]], widths=True)

                print(table)
                cct.counterCategory(top_temp)
                print(cct.format_for_print(top_dd[-4:], header=False, widths=widths))

                # print cct.format_for_print(top_temp.loc[:, ct_MonitorMarket_Values][:10])
                # print cct.format_for_print(top_temp2.loc[:, ct_MonitorMarket_Values2][:3])
                # print cct.format_for_print(top_temp.loc[:, ct.Sina_Monitor_format][:10])

                # print cct.format_for_print(top_all[:10])
                # print "staus",status
                # if status:
                #     for code in top_all[:10].index:
                #         code=re.findall('(\d+)', code)
                #         if len(code) > 0:
                #             code=code[0]
                #             kind=sl.get_multiday_ave_compare_silent(code)

            else:
                print("no data")

            int_time=cct.get_now_time_int()
            if cct.get_work_time():
                if int_time < ct.open_time:
                    top_all=DataFrame()
                    cct.sleep(ct.sleep_time)
                elif int_time < 930:
                    cct.sleep((930 - int_time) * 55)
                    time_s=time.time()
                else:
                    cct.sleep(ct.duration_sleep_time)
            elif cct.get_work_duration():
                while 1:
                    cct.sleep(ct.duration_sleep_time)
                    if cct.get_work_duration():
                        print(".", end=' ')
                        cct.sleep(ct.duration_sleep_time)
                    else:
                        # top_all = DataFrame()
                        cct.sleeprandom(60)
                        time_s=time.time()
                        print(".")
                        break
            # old while
            # int_time = cct.get_now_time_int()
            # if cct.get_work_time():
            #     if int_time < 930:
            #         while 1:
            #             cct.sleep(60)
            #             if cct.get_now_time_int() < 930:
            #                 cct.sleep(60)
            #                 print ".",
            #             else:
            #                 top_all = DataFrame()
            #                 time_s = time.time()
            #                 print "."
            #                 break
            #     else:
            #         cct.sleep(60)
            # elif cct.get_work_duration():
            #     while 1:
            #         cct.sleep(60)
            #         if cct.get_work_duration():
            #             print ".",
            #             cct.sleep(60)
            #         else:
            #             print "."
            #             cct.sleeprandom(60)
            #             top_all = DataFrame()
            #             time_s = time.time()
            #             break
            else:
                raise KeyboardInterrupt("StopTime")

        except (KeyboardInterrupt) as e:
            # print "key"
            print("KeyboardInterrupt:", e)
            # cct.sleep(1)
            # if success > 3:
            #     raw_input("Except")
            # st=raw_input("status:[go(g),clear(c),quit(q,e)]:")
            st=cct.cct_raw_input(ct.RawMenuArgmain() % (market_sort_value))

            if len(st) == 0:
                status=False
            elif (len(st.split()[0]) == 1 and st.split()[0].isdigit()) or st.split()[0].startswith('x'):
                st_l=st.split()
                st_k=st_l[0]
                
                if st_k in list(ct.Market_sort_idx.keys()) and len(top_all) > 0:
                    st_key_sort=st
                    market_sort_value, market_sort_value_key=ct.get_market_sort_value_key(
                        st_key_sort, top_all=top_all)
                else:
                    log.error("market_sort key error:%s" % (st))
                    cct.sleeprandom(5)

            elif st.lower() == 'g' or st.lower() == 'go':
                status=True
            elif st.lower() == 'clear' or st.lower() == 'c':
                top_all=DataFrame()
                cct.GlobalValues().setkey('lastbuylogtime', 1)
                # cct.set_clear_logtime()
                status=False
            elif st.startswith('in') or st.startswith('i'):
                days = st.split()[1] if len(st.split()) > 1 else None
                if days is not None and days.isdigit():
                    top_all = DataFrame()
                    indf = top_all = DataFrame()
                    instocklastDays = days
                else:
                    log.error(f'{st} not find digit days')
            elif st.startswith('dd') or st.startswith('dt'):
                args = parserDuraton.parse_args(st.split()[1:])
                if len(str(args.start)) > 0:
                    if args.end:
                        end_date = args.end
                    duration_date = args.start.strip()
                    if len(str(duration_date)) < 4:
                        du_date = tdd.get_duration_Index_date(
                            '999999', dl=int(duration_date))
                        ct.PowerCountdl = int(duration_date)
                    # set_duration_console(du_date)
                    top_all = DataFrame()
                    time_s = time.time()
                    status = False
                    lastpTDX_DF = DataFrame()

            elif st.startswith('3d') or st.startswith('d') or st.startswith('5d'):
                if st.startswith('3d'):
                    cct.GlobalValues().setkey('resample','3d')
                    top_all = DataFrame()
                    lastpTDX_DF = DataFrame()
                elif st.startswith('d'):
                    cct.GlobalValues().setkey('resample','d')
                    top_all = DataFrame()
                    lastpTDX_DF = DataFrame()
                elif st.startswith('5d'):
                    cct.GlobalValues().setkey('resample','w')
                    top_all = DataFrame()
                    lastpTDX_DF = DataFrame()

            elif st.startswith('w') or st.startswith('a'):
                args=cct.writeArgmain().parse_args(st.split())
                codew=stf.WriteCountFilter(top_temp, writecount=args.dl)
                if args.code == 'a':
                    cct.write_to_blocknew(block_path, codew)
                    # cct.write_to_blocknew(all_diffpath,codew)
                else:
                    cct.write_to_blocknew(block_path, codew, False)
                    # cct.write_to_blocknew(all_diffpath,codew,False)
                print("wri ok:%s" % block_path)
                cct.sleeprandom(ct.duration_sleep_time / 2)
                # cct.sleep(5)
            elif st.lower() == 'r':
                dir_mo=eval(cct.eval_rule)
                if len(top_temp) > 0 and top_temp.lastp1d[0] == top_temp.close[0]:
                    cct.evalcmd(dir_mo,workstatus=False,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,top_all_3d=top_all_3d,top_all_w=top_all_w,top_all_m=top_all_m)
                else:
                    cct.evalcmd(dir_mo,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,top_all_3d=top_all_3d,top_all_w=top_all_w,top_all_m=top_all_m)


            elif st.startswith('q') or st.startswith('e'):
                print("exit:%s" % (st))
                sys.exit(0)
            else:
                print("input error:%s" % (st))
        except (IOError, EOFError) as e:
            print("IOError,EOFError", e)
            cct.sleeprandom(ct.duration_sleep_time / 2)
            # raw_input("Except")
        except Exception as e:
            print("other Error", e)
            import traceback
            traceback.print_exc()
            cct.sleeprandom(ct.duration_sleep_time / 2)
            # sl.get_code_search_loop()
            # print data.describe()
            # while 1:
            #     intput=raw_input("code")
            #     print
            # pd = DataFrame(data)
            # print pd
            # parsehtml("""
            # <a href="www.google.com"> google.com</a>
            # <A Href="www.pythonclub.org"> PythonClub </a>
            # <A HREF = "www.sina.com.cn"> Sina </a>
            # """)


'''
import logging
import numpy as np
import talib as tl
import pandas as pd
import datetime
import time


__author__ = 'myh '
__date__ = '2023/3/10 '


# 量比大于2
# 例如：
#   2017-09-26 2019-02-11 京东方A
#   2019-03-22 浙江龙盛
#   2019-02-13 汇顶科技
#   2019-01-29 新城控股
#   2017-11-16 保利地产
# 在项目运行时，临时将项目路径添加到环境变量
import os.path
import sys
# cpath_current = os.path.dirname(os.path.dirname(__file__))
# cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
cpath_current = '/data/InStock/instock/'
sys.path.append(cpath_current)
log_path = os.path.join(cpath_current, 'log')
if not os.path.exists(log_path):
    os.makedirs(log_path)
logging.basicConfig(format='%(asctime)s %(message)s', filename=os.path.join(log_path, 'stock_enter_job.log'))
handler = logging.StreamHandler()
ch_formatter = logging.Formatter("[%(asctime)s] %(levelname)s:%(filename)s(%(funcName)s:%(lineno)s): %(message)s");
handler.setFormatter(ch_formatter)
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)

def get_work_day_status():
    today = datetime.datetime.today().date()
    day_n = int(today.strftime("%w"))
    if day_n > 0 and day_n < 6:
        return True
    else:
        return False
    
def get_now_time_int():
    return int(datetime.datetime.now().strftime("%H%M"))

# def get_now_time_int():
#     now_t = datetime.datetime.now().strftime("%H%M")
#     return int(now_t)

def get_work_time_duration():
    # return True
    now_t = get_now_time_int()
    if not get_work_day_status():
        return False
    # if (now_t > 1132 and now_t < 1300) or now_t < 915 or now_t > 1502:
    if now_t < 930 or now_t > 1500:
        
        return False
        # return True
    else:
        # if now_t > 1300 and now_t <1302:
            # sleep(random.randint(5, 120))
        return True
    
def get_work_time_ratio():
    initx = 6.5
    stepx = 0.5
    init = 0
    initAll = 10
    now = time.localtime()
    ymd = time.strftime("%Y:%m:%d:", now)
    hm1 = '09:30'
    hm2 = '13:00'
    all_work_time = 14400
    d1 = datetime.datetime.now()
    now_t = get_now_time_int()
    # d2 = datetime.datetime.strptime('201510111011','%Y%M%d%H%M')
    if now_t >= 1500 or now_t < 930:
        return 1.0
    elif now_t > 915 and now_t <= 930:
        d2 = datetime.datetime.strptime(ymd + '09:29', '%Y:%m:%d:%H:%M')
        d1 = datetime.datetime.strptime(ymd + '09:30', '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 930 and now_t <= 1000:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 1
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1000 and now_t <= 1030:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 2
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1030 and now_t <= 1100:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 3
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1100 and now_t <= 1130:
        d2 = datetime.datetime.strptime(ymd + hm1, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 4
        return round(ds / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1130 and now_t < 1300:
        init += 4
        return 0.5 / (initx + init * stepx) * initAll

    elif now_t > 1300 and now_t <= 1330:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 5
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1330 and now_t <= 1400:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 6
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    elif now_t > 1400 and now_t <= 1430:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        init += 7
        return round((ds + 7200) / all_work_time / (initx + init * stepx) * initAll, 3)
    else:
        d2 = datetime.datetime.strptime(ymd + hm2, '%Y:%m:%d:%H:%M')
        ds = float((d1 - d2).seconds)
        return round((ds + 7200) / all_work_time, 3)

def get_today_duration(startday, endday=None):
    if startday is not None and len(startday) > 6:
        if endday:
            today = datetime.datetime.strptime((endday), '%Y-%m-%d').date()
        else:
            today = datetime.date.today()
        # if get_os_system() == 'mac':
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        # else:
        #     # last_day = datetime.datetime.strptime(datastr, '%Y/%m/%d').date()
        #     last_day = datetime.datetime.strptime(datastr, '%Y-%m-%d').date()
        last_day = datetime.datetime.strptime(startday, '%Y-%m-%d').date()
        
        duration_day = int((today - last_day).days)
    else:
        duration_day = None
    return (duration_day)


def get_tdx_stock_period_to_type(df, period_day='W-FRI', periods=5, ncol=None, ratiodays=True):
    """_周期转换周K,月K_

    Returns:
        _type_: _description_
    """
    #快速日期处理
    #https://www.likecs.com/show-204682607.html
    stock_data = df.copy()
    period_type = period_day
    if 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
    stock_data['date'] = stock_data.index
    lastday = str(stock_data.date.values[-1])[:10]
    lastday2 = str(stock_data.date.values[-2])[:10]
    # duration_day = get_today_duration(lastday2,lastday)
    # print("duration:%s"%(duration_day))
    
    # if duration_day > 3:
    #     if 'date' in stock_data.columns:
    #         stock_data = stock_data.drop(['date'], axis=1)
    #     return stock_data.reset_index()
    
    # indextype = True if stock_data.index.dtype == 'datetime64[ns]' else False
    # if cct.get_work_day_status() and 915 < cct.get_now_time_int() < 1500:
    #     stock_data = stock_data[stock_data.index < cct.get_today()]

    if stock_data.index.name == 'date':
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    elif 'date' in stock_data.columns:
        stock_data.set_index('date', inplace=True)
        stock_data.sort_index(ascending=True, inplace=True)
        stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    # else:
    #     log.error("index.name not date,pls check:%s" % (stock_data[:1]))

    period_stock_data = stock_data.resample(period_type).last()
    # period_stock_data['percent']=stock_data['percent'].resample(period_type,how=lambda x:(x+1.0).prod()-1.0)
    # print stock_data.index[0],stock_data.index[-1]
    # period_stock_data.index =
    # pd.DatetimeIndex(start=stock_data.index.values[0],end=stock_data.index.values[-1],freq='BM')
    
    period_stock_data['open'] = stock_data[
        'open'].resample(period_type).first()
    period_stock_data['high'] = stock_data[
        'high'].resample(period_type).max()
    period_stock_data['low'] = stock_data[
        'low'].resample(period_type).min()

    lastWeek1 = str(period_stock_data['open'].index.values[-1])[:10]
    lastweek2 = str(period_stock_data['open'].index.values[-2])[:10]
    if ratiodays:
        if period_day == 'W-FRI':
            # print(lastWeek1,lastweek2,lastday,lastday2)
            duratio = int(str(datetime.datetime.strptime(lastWeek1, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[0])
            ratio_d =(5-(duratio%5))/5
            # print("ratio_d:%s %s"%(ratio_d,lastday))
        elif period_day.find('W') >= 0:
            # print(lastWeek1,lastweek2,lastday,lastday2)
            duratio = int(str(datetime.datetime.strptime(lastday, '%Y-%m-%d').date() - datetime.datetime.strptime(lastweek2, '%Y-%m-%d').date())[0])
            ratio_d =(duratio)/5
            # print("ratio_d:%s %s"%(ratio_d,lastday))
        elif period_day == 'BM':
            # daynow = '2023-04-26'
            # lastday = '2023-04-23'
            # print(lastWeek1,lastweek2,lastday,lastday2)
            # print((str(datetime.datetime.strptime(lastWeek1, '%Y-%m-%d').date() - datetime.datetime.strptime(lastday, '%Y-%m-%d').date())[:2]))
            duratio = int(str(datetime.datetime.strptime(lastday, '%Y-%m-%d').date() - datetime.datetime.strptime(lastweek2, '%Y-%m-%d').date())[:2])
            ratio_d =(30-(duratio%30))/30
            # print("ratio_d:%s %s dura:%s"%(ratio_d,lastday,duratio))
        elif period_day.find('M') >= 0:
            ratio_d = 1
            
    else:
        ratio_d = 1
        print(ratio_d)
        
    if ncol is not None:
        for co in ncol:
            period_stock_data[co] = stock_data[co].resample(period_type).sum()
            if ratiodays:
                period_stock_data[co] = period_stock_data[co].apply(lambda x: round(x / ratio_d, 1))
                
    # else:
    period_stock_data['amount'] = stock_data[
        'amount'].resample(period_type).sum()
    period_stock_data['volume'] = stock_data[
        'volume'].resample(period_type).sum()
    if ratiodays:
        period_stock_data['amount'] = period_stock_data['amount'].apply(lambda x: round(x / ratio_d, 1))
        period_stock_data['volume'] = period_stock_data['volume'].apply(lambda x: round(x / ratio_d, 1))
                
    # period_stock_data['turnover']=period_stock_data['vol']/(period_stock_data['traded_market_value'])/period_stock_data['close']
    period_stock_data.index = stock_data['date'].resample(period_type).last().index
    # print period_stock_data.index[:1]
    if 'code' in period_stock_data.columns:
        period_stock_data = period_stock_data[period_stock_data['code'].notnull()]
    period_stock_data = period_stock_data.dropna()
    # period_stock_data.reset_index(inplace=True)
    # period_stock_data.set_index('date',inplace=True)
    # print period_stock_data.columns,period_stock_data.index.name
    # and period_stock_data.index.dtype != 'datetime64[ns]')
    
    # if not indextype and period_stock_data.index.name == 'date':
    #     # stock_data.index = pd.to_datetime(stock_data.index, format='%Y-%m-%d')
    #     period_stock_data.index = [str(x)[:10] for x in period_stock_data.index]
    #     period_stock_data.index.name = 'date'
    # else:
    #     if 'date' in period_stock_data.columns:
    #         period_stock_data = period_stock_data.drop(['date'], axis=1)
    
    if 'date' in period_stock_data.columns:
            period_stock_data = period_stock_data.drop(['date'], axis=1)
    return period_stock_data.reset_index()

def check_rsi_status(df,threshold=60,period_day=False):
    # macd
    data = df.copy()
    # cci 计算方法和结果和stockstats不同，stockstats典型价采用均价(总额/成交量)计算
    data.loc[:, 'cci'] = tl.CCI(data['high'].values, data['low'].values, data['close'].values, timeperiod=14)
    data['cci'].values[np.isnan(data['cci'].values)] = 0.0
    # data.loc[:, 'cci_84'] = tl.CCI(data['high'].values, data['low'].values, data['close'].values, timeperiod=84)
    # data['cci_84'].values[np.isnan(data['cci_84'].values)] = 0.0
    rsilast5 = data.iloc[-6:-1]['cci']
    rsilast5max = rsilast5.max()
    rsilast = data.iloc[-1]['cci']

    #周K滞后可以<0 日线节奏回踩多
    if period_day:
        return(rsilast5max < 0 and rsilast > rsilast5max and rsilast5.iloc[-1] < rsilast5max)
    else:
        return(rsilast > rsilast5max and rsilast5.iloc[-1] < rsilast5max)
        
    
def check_macd_status(df,threshold=60,period_day=False):
    # macd
    data = df.copy()
    data.loc[:, 'diff'], data.loc[:, 'dea'], data.loc[:, 'macd'] = tl.MACD(
        data['close'].values, fastperiod=5, slowperiod=34, signalperiod=5)
        # data['close'].values, fastperiod=12, slowperiod=26, signalperiod=9)
    
    data['diff'].values[np.isnan(data['diff'].values)] = 0.0
    data['dea'].values[np.isnan(data['dea'].values)] = 0.0
    data['macd'].values[np.isnan(data['macd'].values)] = 0.0
    # diff_max =  data.iloc[-threshold:]['diff'].max()
    p_diff =  data.iloc[-1]['diff']
    p_dea =  data.iloc[-1]['dea']
    p_macd = data.iloc[-1]['macd']
    last_macd = data.iloc[-1]['macd']
    last2_macd = data.iloc[-2]['macd']
    last3_macd = data.iloc[-3]['macd']
    p_last_close = data.iloc[-1]['close']
    p_close_max5 = data.iloc[-6:-1]['close'].max()
    p_close_min5 = data.iloc[-6:-1]['close'].min()
    p_percent = round((p_close_max5 - p_close_min5)/p_close_min5*100,1)
    if period_day:
        #Week and month
        # if last_macd > last2_macd and p_diff > 0 and p_dea > 0 and p_macd > 0 and p_diff > p_dea:
        #week 回踩零轴后 英可瑞 20230508
        # if  p_diff >0 and p_diff >= p_dea * 0.98 and p_diff <= p_dea * 1.02 and ((last_macd >= last2_macd or last2_macd >= last3_macd ) or (p_diff >= 0 and p_dea >= 0)) :            
        if  ((p_percent < 5 and p_percent > -5 and p_last_close >=p_close_max5) or p_diff >0) and p_diff >= p_dea * 0.98 and ((last_macd >= last2_macd or last2_macd >= last3_macd ) or (p_diff >= 0 and p_dea >= 0)) :            
            return True
        else:
            return False
        
    # elif ((p_diff > 0 and p_dea > 0 ) or  p_macd >= 0 ) and last_macd > last2_macd and p_diff > p_dea*0.99 :
    elif p_diff >= p_dea*0.98 and p_diff <= p_dea * 1.02 and ((last_macd > last2_macd or last2_macd > last3_macd)  or  p_macd >= 0 ):
         
        return True
    else:
        return False
    
def check_volume(code_name, data, date=None, threshold=60):
    # pr_value['date'] = pd.to_datetime(pr_value.date, format='%Y-%m-%d')
    data['date'] = pd.to_datetime(data.date, format='%Y-%m-%d')
    if date is None:
        end_date = code_name[0]
    else:
        end_date = date.strftime("%Y-%m-%d")
    if end_date is not None:
        mask = (data['date'] <= end_date)
        data = data.loc[mask].copy()
    if len(data.index) < threshold:
        return False

    now_time = datetime.datetime.now()
    run_date = now_time.date()
    n_time = now_time.time()
    realtime = False
    if str(run_date) == str(data.date.values[-1])[:10]:
        if n_time >= datetime.time(9, 30, 0) and n_time <= datetime.time(15, 00, 0):
            realtime = True
            v_ratio = get_work_time_ratio()
            data.loc[ data.date == str(run_date),'volume'] = data[ data.date == str(run_date)]['volume'].apply(lambda x: round(x / v_ratio, 1))
            data.loc[ data.date == str(run_date),'amount'] = data[ data.date == str(run_date)]['amount'].apply(lambda x: round(x / v_ratio, 1))
    
    p_change = data.iloc[-1]['p_change']

    last_close = data.iloc[-1]['close']
    # 最后一天成交量
    last_vol = data.iloc[-1]['volume']

    amount = last_close * last_vol

    # 成交额不低于2亿
    if amount < 200000000:
        return False

    
            
    #日K
    
    # p_rsi_status = check_rsi_status(data)
    
    # if not p_rsi_status:
    #     return False
    # else:
    #     logging.info(f"code:{code_name} 日,RSI OK")
    
    p_macd_status = check_macd_status(data)
    if not p_macd_status:
        return False
    
    #转换月K数据
    dataM = get_tdx_stock_period_to_type(data, period_day='BM', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    #check Month
    p_macd_status_m = check_macd_status(dataM)
    if not p_macd_status_m:
        return False

    #转换周K数据
    dataW = get_tdx_stock_period_to_type(data, period_day='W-FRI', ncol=['turnover', 'amplitude', 'quote_change'],ratiodays=True)

    #check Week
    # if not check_macd_status(dataW):
    p_macd_status_w = check_macd_status(dataW,period_day=True)
    if not p_macd_status_w:
        return False
    else:
        logging.info(f"code:{code_name} 日,周,月K OK")
    #re ta ma5 at W
    dataW.loc[:, 'ma5'] = tl.MA(dataW['close'].values, timeperiod=5)
    dataW['ma5'].values[np.isnan(dataW['ma5'].values)] = 0.0
    
    dataW.loc[:, 'ma20'] = tl.MA(dataW['close'].values, timeperiod=26)
    dataW['ma20'].values[np.isnan(dataW['ma20'].values)] = 0.0
    pw_ma5 = dataW.iloc[-1]['ma5']
    pw_ma20 = dataW.iloc[-1]['ma20']
    
    pw_close = dataW.iloc[-1]['close']
    
    pw_low = dataW.iloc[-1]['low']
    pw_open = data.iloc[-1]['open']
    pw_high = data.iloc[-1]['high']
    
    
    pw_ma52 = dataW.iloc[-2]['ma5']
    pw_ma53 = dataW.iloc[-3]['ma5']
    pw_close2 = dataW.iloc[-2]['close']
    pw_close3 = dataW.iloc[-3]['close']
    pw_close_max3 = dataW.iloc[-4:-1]['close'].max()
    

    #日K
    data.loc[:, 'ma5'] = tl.MA(data['close'].values, timeperiod=5)
    data['ma5'].values[np.isnan(data['ma5'].values)] = 0.0
    data.loc[:, 'ma20'] = tl.MA(data['close'].values, timeperiod=26)
    data['ma20'].values[np.isnan(data['ma20'].values)] = 0.0
    p_ma5 = data.iloc[-1]['ma5']
    p_close = data.iloc[-1]['close']
    p_close2 = data.iloc[-2]['close']
    
    p_open = data.iloc[-1]['open']
    p_high = data.iloc[-1]['high']
    
    p2_high = data.iloc[-2]['high']
    p_low = data.iloc[-1]['low']
    p2_low = data.iloc[-2]['low']
    p_ma20 = data.iloc[-1]['ma20']



    #boll
    data.loc[:, 'boll_ub'], data.loc[:, 'boll'], data.loc[:, 'boll_lb'] = tl.BBANDS \
        (data['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    data['boll_ub'].values[np.isnan(data['boll_ub'].values)] = 0.0
    data['boll'].values[np.isnan(data['boll'].values)] = 0.0
    data['boll_lb'].values[np.isnan(data['boll_lb'].values)] = 0.0

    bollub_close = data.iloc[-1]['boll_ub']
    boll_close = data.iloc[-1]['boll']
    bolllb_close = data.iloc[-1]['boll_lb']



    if p_ma5 < p_ma20 or p_close < p_ma20 or p_change < 2 or data.iloc[-1]['close'] < data.iloc[-1]['open'] or p_close < boll_close :
        return False

    # data = data.tail(n=threshold + 1)
    # if len(data) < threshold + 1:
    #     return False

    data.loc[:, 'vol_ma5'] = tl.MA(data['volume'].values, timeperiod=6)
    data['vol_ma5'].values[np.isnan(data['vol_ma5'].values)] = 0.0
    mean_vol = data.iloc[-1]['vol_ma5']
    last_vol = data.iloc[-1]['volume']
    last_vol2 = data.iloc[-2]['volume']
    vol_ratio = last_vol / mean_vol
    vol_ratio2 = last_vol / last_vol2
    vol_ratio_diff = vol_ratio2 - vol_ratio

     #bollW
    dataW.loc[:, 'boll_ub'], dataW.loc[:, 'boll'], dataW.loc[:, 'boll_lb'] = tl.BBANDS \
        (dataW['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    dataW['boll_ub'].values[np.isnan(dataW['boll_ub'].values)] = 0.0
    dataW['boll'].values[np.isnan(dataW['boll'].values)] = 0.0
    dataW['boll_lb'].values[np.isnan(dataW['boll_lb'].values)] = 0.0      

    bollub_closew = dataW.iloc[-1]['boll_ub']
    bollub_closew2 = dataW.iloc[-2]['boll_ub']
    boll_closew = dataW.iloc[-1]['boll']
    bolllb_closew = dataW.iloc[-1]['boll_lb']
    
    dataW.loc[:, 'vol_ma5'] = tl.MA(dataW['volume'].values, timeperiod=6)
    dataW['vol_ma5'].values[np.isnan(dataW['vol_ma5'].values)] = 0.0
    mean_volw = dataW.iloc[-1]['vol_ma5']
    last_volw = dataW.iloc[-1]['volume']
    last_volw2 = dataW.iloc[-2]['volume']
    
    vol_ratiow = last_volw / mean_volw
    vol_ratiow2 = last_volw / last_volw2
    vol_ratiow_diff = vol_ratiow2 - vol_ratiow
    # data = data.tail(n=threshold + 1)
    # data = data.head(n=threshold)



    # if vol_ratio < 1.5 and (
    #     pw_close < pw_close_max3 * 0.98 or pw_close2 < pw_ma52 * 0.99
    # ):
    #     return False
    # if  vol_ratiow2 > 1.2 and pw_ma5 >= pw_ma52 and ((pw_low > pw_ma5*0.98 and pw_low < pw_ma5*1.05 and pw_close > pw_ma5) or (pw_close > bollub_closew and pw_close2 <= bollub_closew2)) :
   
    # if  pw_close > pw_ma20 and pw_close2 < pw_ma20 and  pw_ma5 >= pw_ma52 and ((pw_low > pw_ma5*0.98 and pw_low < pw_ma5*1.05 and pw_close > pw_ma5) or (pw_close > bollub_closew and pw_close2 <= bollub_closew2)) :
    #     # print(vol_ratiow  , pw_close , pw_ma5 , pw_close , bollub_closew , pw_close2 , bollub_closew2 , bollub_closew , bollub_closew)
    #     logging.info(f"codeW: pw_close:{pw_close} pw_ma20: {pw_ma20} pw_close2:{pw_close2}pw_ma20:{pw_ma20} codeW:{code_name} {round(vol_ratiow,2)} pw2: {round(pw_close2,2)} upp2: {round(bollub_closew2,2)}")
    #     return True
    # if p_open > p_low*0.98 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.3   and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.05) or (p_close > p2_high and p_high > bollub_close  and p_close < bollub_close)):
    # if p_open > p_low*0.95 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.5  and vol_ratio < 3 and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.2) or (p_close > p2_high and p_high > bollub_close)):
    if p_open > p_low*0.95 and (p_close > p_open or p_close > p_close2)  and vol_ratio > 1.1  and vol_ratio < 5 and pw_close2 >= bollub_closew2 * 0.97 and ((pw_close > pw_ma5*0.98  and p_ma5 > boll_close ) or (p_close > p2_high and p_high > bollub_close)):
    
        # print(vol_ratio ,pw_close , pw_ma5 , p_ma5 , boll_close , pw_close2 , bollub_closew2 * 1.08 , p_close , p2_high , p_high , bollub_close , p_close ,bollub_close )
        logging.info(f"codeD:{code_name} Select volD:{round(vol_ratio,2)} pclose: {round(p_close,2)} upp: {round(bollub_close,2)}")
        return True
    else:
        return False

    # if (vol_ratiow2 > 1.5 and pw_close > pw_ma5 and pw_close > bollub_closew and pw_close2 <= bollub_closew2 and bollub_closew >= bollub_closew):
    #     # print(vol_ratiow  , pw_close , pw_ma5 , pw_close , bollub_closew , pw_close2 , bollub_closew2 , bollub_closew , bollub_closew)
    #     logging.info(f"codeW:{code_name} Select volW:{round(vol_ratiow,2)} pw2: {round(pw_close2,2)} upp2: {round(bollub_closew2,2)}")
    #     return True
    # elif vol_ratio2 > 1.5  and ((pw_close > pw_ma5 and p_ma5 > boll_close and pw_close2 <= bollub_closew2 * 1.08) or (p_close > p2_high and p_high > bollub_close  and p_close < bollub_close)):
    #     # print(vol_ratio ,pw_close , pw_ma5 , p_ma5 , boll_close , pw_close2 , bollub_closew2 * 1.08 , p_close , p2_high , p_high , bollub_close , p_close ,bollub_close )
    #     logging.info(f"codeD:{code_name} Select volW:{round(vol_ratio,2)} pclose: {round(p_close,2)} upp: {round(bollub_close,2)}")
    #     return True
    # else:
    #     return False
'''

