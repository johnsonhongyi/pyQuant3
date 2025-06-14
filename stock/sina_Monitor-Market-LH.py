# -*- coding:utf-8 -*-
#!/usr/bin/env python
# import gc
# import random
import re
import sys
import time
import urllib.request, urllib.error, urllib.parse

import pandas as pd
# from bs4 import BeautifulSoup
# from pandas import DataFrame
# import sys
# print sys.path

from JohnsonUtil import johnson_cons as ct
import singleAnalyseUtil as sl
from JSONData import powerCompute as pct
from JSONData import stockFilter as stf
from JSONData import tdx_data_Day as tdd
from JSONData import LineHistogram as lhg
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import commonTips as cct

# from logbook import Logger,StreamHandler,SyslogHandler
# from logbook import StderrHandler


def downloadpage(url):
    fp = urllib.request.urlopen(url)
    data = fp.read()
    fp.close()
    return data


def parsehtml(data):
    soup = BeautifulSoup(data)
    for x in soup.findAll('a'):
        print(x.attrs['href'])


def html_clean_content(soup):
    [script.extract() for script in soup.findAll('script')]
    [style.extract() for style in soup.findAll('style')]
    soup.prettify()
    reg1 = re.compile("<[^>]*>")  # 剔除空行空格
    content = reg1.sub('', soup.prettify())
    print(content)


def get_sina_url(vol='0', type='0', pageCount='100'):
    # if len(pageCount) >=1:
    url = ct.SINA_DD_VRatio_All % (ct.P_TYPE['http'], ct.DOMAINS['vsf'], ct.PAGES[
                                   'sinadd_all'], pageCount, ct.DD_VOL_List[vol], type)
    # print url
    return url


def evalcmd(dir_mo):
    end = True
    import readline
    # import rlcompleter
    # readline.set_completer(cct.MyCompleter(dir_mo).complete)
    readline.parse_and_bind('tab:complete')
    while end:
        # cmd = (cct.cct_raw_input(" ".join(dir_mo)+": "))
        cmd = (cct.cct_raw_input(": "))
        # cmd = (cct.cct_raw_input(dir_mo.append(":")))
        # if cmd == 'e' or cmd == 'q' or len(cmd) == 0:
        if cmd == 'e' or cmd == 'q':
            break
        elif len(cmd) == 0:
            continue
        else:
            try:
                if not cmd.find(' =') < 0:
                    exec(cmd)
                else:
                    print(eval(cmd))
                print('')
            except Exception as e:
                print(e)
                # evalcmd(dir_mo)
                # break


if __name__ == "__main__":
    # parsehtml(downloadpage(url_s))
    # StreamHandler(sys.stdout).push_application()
    # log = LoggerFactory.getLogger('SinaMarket')
    # pd.options.mode.chained_assignment = None
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

    # log=LoggerFactory.JohnsonLoger('SinaMarket').setLevel(LoggerFactory.DEBUG)
    # log.setLevel(LoggerFactory.DEBUG)
    if cct.isMac():
        width, height = 174, 20
        cct.set_console(width, height)
    else:
        width, height = 174, 20
        cct.set_console(width, height)
    status = False
    vol = ct.json_countVol
    type = ct.json_countType
    # cut_num=10000
    success = 0
    top_all = pd.DataFrame()
    time_s = time.time()
    # delay_time = 3600
    delay_time = cct.get_delay_time()
    First = True
    # base_path = tdd.get_tdx_dir()
    # block_path = tdd.get_tdx_dir_blocknew() + '067.blk'
    # blkname = '067.blk'
    blkname = '066.blk'
    block_path = tdd.get_tdx_dir_blocknew() + blkname
    lastpTDX_DF = pd.DataFrame()
    parserDuraton = cct.DurationArgmain()
    duration_date = ct.duration_date_day
    du_date = duration_date
    resample = ct.resample_dtype
    end_date = cct.last_tddate(days=3)
    
    # from JohnsonUtil import inStockDb as inDb
    # # indf = inDb.showcount(inDb.selectlastDays(0))
    # indf = inDb.show_stock_pattern()

    # if len(indf) > 0 and cct.creation_date_duration(block_path) > 0:
    #     if cct.creation_date_duration(block_path) > 10:
    #         cct.write_to_blocknew(block_path, indf.code.tolist(),append=False,doubleFile=False,keep_last=0,dfcf=False)
    #     else:
    #         cct.write_to_blocknew(block_path, indf.code.tolist(),append=True,doubleFile=False,keep_last=0,dfcf=False)
    # else:
    #     if cct.creation_date_duration(block_path) > 0:
    #         log.error("indb last1days is None")   

    # all_diffpath = tdd.get_tdx_dir_blocknew() + '062.blk'

    if len(str(duration_date)) < 4:
        # duration_date = tdd.get_duration_price_date('999999', dl=duration_date, end=end_date, ptype='dutype')
        du_date = tdd.get_duration_Index_date('999999', dl=duration_date)
        if cct.get_today_duration(du_date) <= 3:
            duration_date = 5
            print(("duaration: %s duration_date:%s" %
                  (cct.get_today_duration(du_date), duration_date)))
        log.info("duaration: %s duration_date:%s" %
                 (cct.get_today_duration(du_date), duration_date))

    # market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(ct.sort_value_key_perd)
    # st_key_sort = '2'
    # st_key_sort = '7'
    # st_key_sort = '4'
    st_key_sort = '3 1'
    st = None
    # st_key_sort = ct.sort_value_key_perd
    while 1:
        try:
            # top_now = tdd.getSinaAlldf(market='sh', vol=ct.json_countVol, vtype=ct.json_countType)
            time_Rt = time.time()
            if st is None and st_key_sort in ['2', '3']:
                st_key_sort = '%s %s' % (
                    st_key_sort.split()[0], cct.get_index_fibl())

            # top_now = tdd.getSinaAlldf(market='次新股',filename='cxg', vol=ct.json_countVol, vtype=ct.json_countType)
            # market_blk = 'cyb'
            
            # market_blk = '077'
            # top_now = tdd.getSinaAlldf(market=market_blk, filename='cxg', vol=ct.json_countVol, vtype=ct.json_countType,trend=False)
            
            # market_blk = '近期异动'
            # tdxbkdict={'近期新高':'880865','近期异动':'880884'}
            market_blk = '066'

            top_now = tdd.getSinaAlldf(market=market_blk, vol=ct.json_countVol, vtype=ct.json_countType)

            
            # market_blk = '央企'
            # top_now = tdd.getSinaAlldf(market='央企',filename='yqbk', vol=ct.json_countVol, vtype=ct.json_countType,trend=False)

            # top_now = tdd.getSinaAlldf(
                # market=market_blk, filename=None, vol=ct.json_countVol, vtype=ct.json_countType, trend=False)
                # market=market_blk, filename=None, vol=ct.json_countVol, vtype=ct.json_countType, trend=True)

            # top_now = tdd.getSinaAlldf(market='次新股,cyb', filename='cxg', vol=ct.json_countVol, vtype=ct.json_countType,trend=False)

            # top_now = tdd.getSinaAlldf(market='次新股,zxb',filename='cxg', vol=ct.json_countVol, vtype=ct.json_countType)

            # print top_now.loc['300208','name']
            df_count = len(top_now)
            now_count = len(top_now)
            radio_t = cct.get_work_time_ratio()
            time_d = time.time()
            if time_d - time_s > delay_time:
                status_change = True
                log.info("chane clear top")
                time_s = time.time()
                top_all = pd.DataFrame()

            else:
                status_change = False
            # print ("Buy>0:%s"%len(top_now[top_now['buy'] > 0])),
            # log.info("top_now['buy']:%s" % (top_now[:2]['buy']))
            # log.info("top_now.buy[:30]>0:%s" %len(top_now[:30][top_now[:30]['buy'] > 0]))
            if len(top_now) > 1 or cct.get_work_time():
                # if len(top_now) > 10 or len(top_now[:10][top_now[:10]['buy'] > 0]) > 3:
                # if len(top_now) > 10 and not top_now[:1].buy.values == 0:
                #     top_now=top_now[top_now['percent']>=0]
                if 'trade' in top_now.columns:
                    top_now['buy'] = (list(map(lambda x, y: y if int(x) == 0 else x,
                                          top_now['buy'].values, top_now['trade'].values)))

                if len(top_all) == 0 and len(lastpTDX_DF) == 0:
                    terminal_count = cct.get_terminal_Position(
                        position=sys.argv[0])
                    print("term:%s" % (terminal_count), end=' ')
                    if terminal_count > 1:
                        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
                            top_now, lastpTDX_DF=None, dl=duration_date, resample=resample)
                    else:
                        top_all, lastpTDX_DF = tdd.get_append_lastp_to_df(
                            top_now, lastpTDX_DF=None, dl=duration_date, checknew=True, resample=resample)
                    # time_Rt = time.time()
                    # top_all,lastpTDX_DF = tdd.get_append_lastp_to_df(top_now,end=end_date,dl=duration_date)
                elif len(top_all) == 0 and len(lastpTDX_DF) > 0:
                    # time_Rt = time.time()
                    top_all = tdd.get_append_lastp_to_df(top_now, lastpTDX_DF)

                else:
                    if 'couts' in top_now.columns.values:
                        if not 'couts' in top_all.columns.values:
                            top_all['couts'] = 0
                            top_all['prev_p'] = 0
                    # for symbol in top_now.index:
                    #     if symbol in top_all.index and top_now.loc[symbol, 'buy'] <> 0:
                    #         if 'couts' in top_now.columns.values:
                    #             top_all.loc[symbol, 'buy':'prev_p'] = top_now.loc[
                    #                 symbol, 'buy':'prev_p']
                    #         else:
                    #             top_all.loc[symbol, 'buy':'low'] = top_now.loc[
                    #                 symbol, 'buy':'low']
                    top_all = cct.combine_dataFrame(top_all, top_now, col=None)
                top_dif = top_all.copy()
                market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(
                    st_key_sort, top_all=top_all)

                top_dif = top_dif[top_dif.lvol > ct.LvolumeSize]
                # if top_dif[:1].llow.values <> 0:
                # if not (cct.get_now_time_int() > 915 and cct.get_now_time_int() <= 925):
                if len(top_dif[:5][top_dif[:5]['buy'] > 0]) > 3:
                    log.debug('diff2-0-buy>0')
                    if cct.get_now_time_int() > 915 and cct.get_now_time_int() < ct.checkfilter_end_time:
                        top_dif = top_dif[top_dif.low >
                                          top_dif.llow * ct.changeRatio]
                    log.debug('dif4 open>low0.99:%s' % len(top_dif))
                    # top_dif['buy'] = (map(lambda x, y: y if int(x) == 0 else x, top_dif['buy'].values, top_dif['trade'].values))
                    # if 'volumn' in top_dif.columns and 'lvol' in top_dif.columns:
                top_dif['volume'] = (list(map(lambda x, y: round(
                    x / y / radio_t, 1), top_dif['volume'], top_dif['lvol'])))

                # top_dif['dff'] = map(lambda x, y: round((x - y) / y * 100, 1),
                #                      top_dif['buy'].values, top_dif['lastp'].values)
               

                if st_key_sort.split()[0] in ['4','9'] and 926 < cct.get_now_time_int() < 1455 and 'lastbuy' in top_dif.columns:
                # if  926 < cct.get_now_time_int() < 1455 and 'lastbuy' in top_dif.columns:
                    top_dif['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                          top_dif['buy'].values, top_dif['lastbuy'].values)))
                    top_dif['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                           top_dif['buy'].values, top_dif['lastp'].values)))
                else:
                    top_dif['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                          top_dif['buy'].values, top_dif['lastp'].values)))
                    if 'lastbuy' in top_dif.columns:
                        top_dif['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                               top_dif['buy'].values, top_dif['lastbuy'].values)))

                if len(top_dif) == 0:
                    print("No G,DataFrame is Empty!!!!!!")
                else:
                    # top_dif = top_dif[top_dif.buy >= top_dif.open*0.99]
                    # log.debug('dif5 buy>open:%s'%len(top_dif))
                    # top_dif = top_dif[top_dif.trade >= top_dif.buy]

                    # df['volume']= df['volume'].apply(lambda x:x/100)

                    # if cct.get_now_time_int() > 915 and cct.get_now_time_int() <= 926:
                        # top_dif['percent']= (map(lambda x, y: round((x-y)/y*100,1) if int(y) > 0 else 0, top_dif.buy, top_dif.llastp))

                    if 'couts' in top_dif.columns.values:
                        top_dif = top_dif.sort_values(
                            by=ct.Monitor_sort_count, ascending=[0, 0, 0, 1, 0])
                    else:
                        # print "Good Morning!!!"
                        top_dif = top_dif.sort_values(
                            by=['dff', 'percent', 'ratio'], ascending=[0, 0, 1])

                    # top_all=top_all.sort_values(by=['percent','dff','couts','ratio'],ascending=[0,0,1,1])

                    top_all = top_dif.copy()


                    if st_key_sort != '4':

                        top_temp=top_all.copy()

                    elif cct.get_now_time_int() > 830 and cct.get_now_time_int() <= 935:
                        top_temp = top_all[(top_all.low >= top_all.lastl1d) & (
                            top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
                        # top_temp =  top_all[( ((top_all.top10 >0) | (top_all.boll >0)) & (top_all.lastp1d > top_all.ma5d) & (top_all.close > top_all.lastp1d))]
                        # top_temp =  top_all[((top_all.lastp1d < top_all.ma5d) & (top_all.close > top_all.lastp1d))]
                        # top_temp =  top_all[((top_all.topR < 2) & (top_all.close > top_all.upper) & (top_all.close > top_all.lastp1d))]
                        # top_temp =  top_all[((top_all.topR >0) & (top_all.top10 >1) &   (top_all.close > top_all.upper) & (top_all.close > top_all.ma5d))]
                        # top_temp =  top_all[((top_all.boll >0) & (top_all.close > top_all.lastp1d))]

                        # top_all[(top_all.low >= top_all.nlow)& (top_all.high > top_all.nhigh)]
                    elif cct.get_now_time_int() > 935 and cct.get_now_time_int() <= 1550:

                        # top_temp =  top_all[ ( (top_all.lastp1d > top_all.lastp2d) &(top_all.close >top_all.lastp1d )) | ((top_all.low >= top_all.nlow)) & ((top_all.lastp1d > top_all.ma5d)  & (top_all.close > top_all.ma5d) &(top_all.close > top_all.lastp1d))]

                        # top_temp =  top_all[ ((top_all.top10 >0) | (top_all.boll >0))  & (top_all.lastp1d > top_all.ma5d)  & ((top_all.low > top_all.lastl1d) | (top_all.low == top_all.open))]
                        # top_temp =  top_all[ ( (top_all.lastp1d > top_all.ma5d) ) ]
                        # top_temp =  top_all[(top_all.topR < 2)  & (top_all.close > top_all.upper) & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                        # top_temp =  top_all[((top_all.topR >0) & (top_all.top10 >1) &   (top_all.close > top_all.upper) & (top_all.low > top_all.lastl1d) & (top_all.close > top_all.ma5d) )]
                        # top_temp =  top_all[(top_all.boll >0)  & ((top_all.low > top_all.upper) | (top_all.low == top_all.open))]
                        # top_temp =  top_all[(top_all.boll >0)  & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                        # top_temp =  top_all[(top_all.topR < 2) & (top_all.close >= top_all.nhigh) & ((top_all.low > top_all.lastp1d) | (top_all.low == top_all.open))]
                        
                        if 'nlow' in top_all.columns:

                            if st_key_sort == '4':
                                # 跳空
                                # top_temp = top_all[ (top_all.topR > 0) & ((top_all.close >= top_all.nclose)) & ((top_all.open > top_all.lastp1d)) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.open >= top_all.nlow) ]

                                # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) & (top_all.ma5d > top_all.ma10d)) & ((top_all.close >= top_all.nclose)) & ((top_all.open > top_all.lastp1d)) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.open >= top_all.nlow) ]

                                # 3日ma5的，ma5d>ma10d,open最低
                                # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                                    # & (top_all.ma5d > top_all.ma10d)) & (top_all.open >= top_all.nlow) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene)) ]

                                # max5>hmax,low>last1d,per1d,2d,3d>-1,per1d >ma51d...

                                # top_temp = top_all[((top_all.max5 > top_all.hmax) & (top_all.ma5d > top_all.ma10d)) & (top_all.low > top_all.lastl1d)
                                #                    & (top_all.low > top_all.lastl1d) & ( ((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma51d)) \
                                #                     & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma52d)) \
                                #                     & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma53d)) )]

                                # max5 < top_all.hmax ,反转新高
                                # top_temp = top_all[((top_all.max5 < top_all.hmax) & ((top_all.close > top_all.hmax) | (top_all.close > top_all.max5)) )]
                                # top_temp = top_all[(top_all.max5 < top_all.hmax) & ((top_all.close > top_all.hmax) | (top_all.close > top_all.max5))
                                #                    & (top_all.low > top_all.ma51d) & (((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma10d))
                                #                                                       & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma10d))
                                #                                                       & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma10d)))]
                                #1122 mod
                                # top_temp = top_all.copy()
                                top_temp = top_all[ ((top_all.open >= top_all.nlow) | (top_all.open >= top_all.lastp1d)) &  ((top_all.close >= top_all.open) |  (top_all.close >= top_all.hmax)) ] 
                                
                                # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                                # & (top_all.ma5d > top_all.ma10d)) & (top_all.open >= top_all.nlow) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene)) ]

                            else:
                                #
                                # top_temp = top_all[ ((top_all.close >= top_all.ene)) & (top_all.close >= top_all.upper) & (top_all.topR > 0) & (top_all.top10 >= 0) ]

                                # 3日ma5的，ma5d>ma10d,close > ene,lastp1d>ene
                                # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) & (top_all.ma5d > top_all.ma10d)) & ((top_all.close >= top_all.ene)) & (top_all.close >= top_all.upper) & (top_all.topR > 0) & (top_all.top10 >= 0) ]
                                # top_temp = top_all[ ((top_all.lastp1d > top_all.ma5d) & (top_all.lastp2d > top_all.ma5d) & (top_all.close > top_all.ma5d) \
                                    # & (top_all.ma5d > top_all.ma10d)) & ((top_all.lastp1d > top_all.ene) & (top_all.close >= top_all.ene))  & (top_all.topR > 0) & (top_all.top10 > 0) ]

                                # max5 > hmax(30)新高
                                # top_temp = top_all[((top_all.max5 > top_all.hmax) & ( top_all.open >= top_all.nlow) &( top_all.close > top_all.lastp1d)) ]
                                # top_temp = top_all[((top_all.max5 > top_all.hmax))]

                                # max5>hmax,low>last1d,per1d,2d,3d>-1,per1d >ma51d...
                                # top_temp = top_all[((top_all.max5 > top_all.hmax) & (top_all.ma5d > top_all.ma10d)) & (top_all.low > top_all.ma51d)
                                #                    & (((top_all.per1d > 0) | (top_all.lastp1d > top_all.ma10d))
                                #                       & ((top_all.per2d > 0) | (top_all.lastp2d > top_all.ma10d))
                                #                       & ((top_all.per3d > 0) | (top_all.lastp3d > top_all.ma10d)))]

                                #1122 mod
                                # top_temp = top_all.copy()
                                top_temp = top_all[ ( ((top_all.open >= top_all.lastp1d)) &  ((top_all.close >= top_all.open) |  (top_all.close >= top_all.hmax)) )| ((top_all.open >= top_all.lastp1d * 0.97) & (top_all.open <= top_all.close)) ] 
                                # 大于ene中轨，大于上轨，一个跳空，一个涨停
                            # top_temp = top_all[  (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.998) & (top_all.open <= top_all.nlow*1.002)) ]
                            # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.99) & (top_all.open <= top_all.nlow*1.01)) ]
                        else:
                            # top_temp = top_all[((top_all.close > top_all.ma51d)) & (
                            #     top_all.low >= top_all.ma51d) & (top_all.lasth1d > top_all.lasth2d)]
                            #1122 mod
                            # top_temp = top_all.copy()
                            # top_temp = top_all[(top_all.open >= top_all.lastp1d * 0.97) & (top_all.open <= top_all.close)]
                            top_temp = top_all[ ( ((top_all.open >= top_all.lastp1d)) &  ((top_all.close >= top_all.open) |  (top_all.close >= top_all.hmax)) )| ((top_all.open >= top_all.lastp1d * 0.97) & (top_all.open <= top_all.close)) ] 


                            # top_temp = top_all[((top_all.open > top_all.lastp1d)) & (
                                # top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d)]
                            # top_temp = top_all[  (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.low >= top_all.nlow) & ((top_all.open >= top_all.nlow *0.998) & (top_all.open <= top_all.nlow*1.002)) ]
                            # top_temp = top_all[ (top_all.volume >= 1.2 ) & (top_all.low >= top_all.lastl1d) & (top_all.lasth1d > top_all.lasth2d) & (top_all.close > top_all.lastp1d)]
                    else:
                        top_temp = top_all.copy()

                    # if st_key_sort != '4':
                    #     top_temp = stf.filterPowerCount(top_temp, ct.PowerCount)

                    top_end = top_all[-int((ct.PowerCount) / 10):].copy()

                    top_temp = pct.powerCompute_df(
                        top_temp, dl=ct.PowerCountdl, talib=True)
                    top_end = pct.powerCompute_df(top_end, dl=ct.PowerCountdl)

                    goldstock = len(top_dif[(top_dif.buy >= top_dif.lhigh * 0.99)
                                            & (top_dif.buy >= top_dif.llastp * 0.99)])

                    cct.set_console(width, height,
                                    title=[du_date,'dT:%s' % cct.get_time_to_date(time_s), 'G:%s' % len(top_dif), 'zxg: %s' % (blkname+'-'+market_blk+' resample:'+resample)])

                    top_all = tdd.get_powerdf_to_all(top_all, top_temp)
                    # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter,duration=ct.PowerCountdl)
                    # top_temp = stf.getBollFilter(df=top_temp, boll=-10, duration=ct.PowerCountdl,resample=resample)
                    
                    # top_temp = stf.getBollFilter(df=top_temp, boll=ct.bollFilter, duration=ct.PowerCountdl,
                    #                              filter=False, ma5d=False, dl=14, percent=False, resample='d', ene=True)
                    # top_end = stf.getBollFilter(df=top_end, down=True)


                    top_temp=stf.getBollFilter(
                        df=top_temp, resample=resample, down=True)
                    top_end=stf.getBollFilter(
                        df=top_end, resample=resample, down=True)


                    print(("A:%s N:%s K:%s %s G:%s" % (
                        df_count, now_count, len(top_all[top_all['buy'] > 0]),
                        len(top_now[top_now['volume'] <= 0]), goldstock)), end=' ')
                    # print "Rt:%0.3f" % (float(time.time() - time_Rt))

                    nhigh = top_temp[top_temp.close > top_temp.nhigh] if 'nhigh'  in top_temp.columns else []
                    nlow = top_temp[top_temp.close > top_temp.nlow] if 'nhigh'  in top_temp.columns else []

                    print("Rt:%0.1f dT:%s N:%s T:%s %s%% nh:%s nlow:%s" % (float(time.time() - time_Rt), cct.get_time_to_date(time_s), cct.get_now_time(), len(top_temp), round(len(top_temp) / float(ct.PowerCount) * 100, 1),len(nhigh),len(nlow)))
                    if 'op' in top_temp.columns:

                        if duration_date > ct.duration_date_sort:
                            top_temp = top_temp.sort_values(by=(market_sort_value),
                                                            ascending=market_sort_value_key)
                        else:
                            top_temp = top_temp.sort_values(by=(market_sort_value),
                                                            ascending=market_sort_value_key)
                    
                    if st_key_sort.split()[0] == 'x':
                        top_temp = top_temp[top_temp.topR != 0]
                        
                    # if cct.get_now_time_int() > 915 and cct.get_now_time_int() < 935:
                    #     # top_temp = top_temp[ (top_temp['ma5d'] > top_temp['ma10d']) & (top_temp['buy'] > top_temp['ma10d']) ]
                    #     top_temp = top_temp.loc[:,ct.MonitorMarket_format_buy]
                    # else:
                    #     # top_temp = top_temp[ (top_temp['ma5d'] > top_temp['ma10d']) & (top_temp['buy'] > top_temp['ma10d']) ]
                    #     top_temp = top_temp.loc[:,ct.MonitorMarket_format_buy]
                    # import ipdb;ipdb.set_trace()

                    ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                        ct.MonitorMarket_format_buy, market_sort_value[:2])
                    # ' '.join(x for x in '3 2 3'.split()[1:])
                    if len(st_key_sort.split()) < 2:
                        f_sort = (st_key_sort.split()[0] + ' f ')
                    else:
                        if st_key_sort.find('f') > 0:
                            f_sort = st_key_sort
                        else:
                            f_sort = ' '.join(x for x in st_key_sort.split()[
                                              :2]) + ' f ' + ' '.join(x for x in st_key_sort.split()[2:])

                    market_sort_value2, market_sort_value_key2 = ct.get_market_sort_value_key(
                        f_sort, top_all=top_all)
                    ct_MonitorMarket_Values2 = ct.get_Duration_format_Values(
                        ct.MonitorMarket_format_buy, market_sort_value2[:2])
                    top_temp2 = top_end.sort_values(
                        by=(market_sort_value2), ascending=market_sort_value_key2)

                    ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                        ct_MonitorMarket_Values, replace='b1_v', dest='volume')
                    # ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                    #     ct_MonitorMarket_Values, replace='fibl', dest='top10')
                    ct_MonitorMarket_Values2 = ct.get_Duration_format_Values(
                        ct_MonitorMarket_Values2, replace='b1_v', dest='volume')
                    # ct_MonitorMarket_Values2 = ct.get_Duration_format_Values(
                    #     ct_MonitorMarket_Values2, replace='fibl', dest='top10')
                    if 'nhigh' in top_all.columns:
                        ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                            ct_MonitorMarket_Values, replace='df2', dest='nhigh')
                        ct_MonitorMarket_Values2 = ct.get_Duration_format_Values(
                                    ct_MonitorMarket_Values2, replace='df2', dest='nhigh')
                    else:
                        ct_MonitorMarket_Values = ct.get_Duration_format_Values(
                            ct_MonitorMarket_Values, replace='df2', dest='high')

                        ct_MonitorMarket_Values2 = ct.get_Duration_format_Values(
                                    ct_MonitorMarket_Values2, replace='df2', dest='high')
                    # if st_key_sort == '1' or st_key_sort == '7':
                    if st_key_sort == '1':
                        top_temp = top_temp[top_temp.per1d < 8]

                    top_dd = cct.combine_dataFrame(
                        top_temp.loc[:, ct_MonitorMarket_Values][:9], top_temp2.loc[:, ct_MonitorMarket_Values2][:4], append=False, clean=False)

                    # top_dd = pd.concat([top_temp.loc[:, ct_MonitorMarket_Values][:9], top_temp.loc[:, ct_MonitorMarket_Values][-4:]], axis=0)

                    # print cct.format_for_print(topdd)
                    # table,widths = cct.format_for_print(top_dd[:9],widths=True)
                    table, widths = cct.format_for_print(
                        top_dd.loc[[col for col in top_dd[:9].index if col in top_temp[:10].index]], widths=True)

                    print(table)
                    cct.counterCategory(top_temp)
                    print(cct.format_for_print(top_dd[-4:], header=False, widths=widths))
                    # print cct.format_for_print(top_dd)

                # print cct.format_for_print(top_dif[:10])
                # print top_all.loc['000025',:]
                # print "staus",status

                if status:
                    for code in top_dif[:10].index:
                        code = re.findall('(\d+)', code)
                        if len(code) > 0:
                            code = code[0]
                            kind = sl.get_multiday_ave_compare_silent(code)
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
                    top_all = pd.DataFrame()
                    time_s = time.time()
                else:
                    cct.sleep(60)
            elif cct.get_work_duration():
                while 1:
                    cct.sleep(60)
                    if cct.get_work_duration():
                        print(".", end=' ')
                        cct.sleep(60)
                    else:
                        cct.sleeprandom(60)
                        top_all = pd.DataFrame()
                        time_s = time.time()
                        print(".")
                        break
            else:
                #                import sys
                #                sys.exit(0)
                raise KeyboardInterrupt("Stop")
        except (KeyboardInterrupt) as e:
            # print "key"
            print("KeyboardInterrupt:", e)
            # cct.sleep(1)
            # if success > 3:
            #     raw_input("Except")
            #     sys.exit(0)
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
                dir_mo = eval(cct.eval_rule)
                evalcmd(dir_mo)
            elif st.lower() == 'g' or st.lower() == 'go':
                status = True
                for code in top_dif[:10].index:
                    code = re.findall('(\d+)', code)
                    if len(code) > 0:
                        code = code[0]
                        kind = sl.get_multiday_ave_compare_silent(code)
            elif st.lower() == 'clear' or st.lower() == 'c':
                top_all = pd.DataFrame()
                cct.set_clear_logtime()
                status = False
            elif st.startswith('d') or st.startswith('dt'):
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
                    top_all = pd.DataFrame()
                    time_s = time.time()
                    status = False
                    lastpTDX_DF = pd.DataFrame()

            elif st.startswith('w') or st.startswith('a'):
                args = cct.writeArgmain().parse_args(st.split())
                # args = cct.writeArgmainParser(st.split())
                codew = stf.WriteCountFilter(top_temp, writecount=args.dl)
                if args.code == 'a':
                    # cct.write_to_blocknew(block_path, codew[:ct.writeCount])
                    cct.write_to_blocknew(block_path, codew)
                    # cct.write_to_blocknew(all_diffpath, codew)
                else:
                    # cct.write_to_blocknew(block_path, codew[:ct.writeCount], False)
                    cct.write_to_blocknew(block_path, codew, False)
                    # cct.write_to_blocknew(all_diffpath, codew, False)
                print("wri ok:%s" % block_path)
                cct.sleeprandom(ct.duration_sleep_time / 2)

                # cct.sleep(2)
            elif st.startswith('q') or st.startswith('e'):
                print("exit:%s" % (st))
                sys.exit(0)
            else:
                print("input error:%s" % (st))
        except (IOError, EOFError, Exception) as e:
            print("Error::", e)
            import traceback
            traceback.print_exc()
            cct.sleeprandom(ct.duration_sleep_time / 2)
            # raw_input("Except")

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
{symbol:"sz000001",code:"000001",name:"平安银行",trade:"0.00",pricechange:"0.000",changepercent:"0.000",buy:"12.36",sell:"12.36",settlement:"12.34",open:"0.00",high:"0.00",low:"0",volume:0,amount:0,ticktime:"09:17:55",per:7.133,pb:1.124,mktcap:17656906.355526,nmc:14566203.350486,turnoverratio:0},
{symbol:"sz000002",code:"000002",name:"万  科Ａ",trade:"0.00",pricechange:"0.000",changepercent:"0.000",buy:"0.00",sell:"0.00",settlement:"24.43",open:"0.00",high:"0.00",low:"0",volume:0,amount:0,ticktime:"09:17:55",per:17.084,pb:3.035,mktcap:26996432.575,nmc:23746405.928119,turnoverratio:0},

python -m cProfile -s cumulative timing_functions.py
http://www.jb51.net/article/63244.htm

'''
