# -*- coding:utf-8 -*-
# !/usr/bin/env python
import gc
import random
import re
import sys
import time

import pandas as pd

from JohnsonUtil import johnson_cons as ct
import singleAnalyseUtil as sl
from JSONData import stockFilter as stf

from JSONData import tdx_data_Day as tdd
from JohnsonUtil import LoggerFactory as LoggerFactory
from JohnsonUtil import commonTips as cct


if __name__ == "__main__":

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
        width, height = 163, 22
        cct.set_console(width, height)
    else:
        width, height = 163, 22
        cct.set_console(width, height)
    status = False
    vol = ct.json_countVol
    type = ct.json_countType
    cut_num = 1000000
    success = 0
    top_all = pd.DataFrame()
    time_s = time.time()
    delay_time = cct.get_delay_time()
    blkname = '063.blk'
    block_path = tdd.get_tdx_dir_blocknew() + blkname
    lastpTDX_DF = pd.DataFrame()
    indf = pd.DataFrame()
    parserDuraton = cct.DurationArgmain()
    st_key_sort = '1'
    duration_date = ct.duration_date_day
    du_date = duration_date
    cct.GlobalValues().setkey('resample','d')

    market_sort_value, market_sort_value_key = ct.get_market_sort_value_key(
        st_key_sort)
    instocklastDays = 10
    st = None
    while 1:
        try:
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
                else:
                    top_all = cct.combine_dataFrame(
                        top_all, top_now, col='couts', compare='dff')
                top_bak = top_all.copy()
                if cct.get_trade_date_status() == 'True':
                    for co in ['boll','df2']:
                        top_all[co] = list(map(lambda x, y,m , z: (z + (1 if ( x > y ) else 0 )), top_all.close.values,top_all.upper.values, top_all.llastp.values,top_all[co].values))

                top_all = top_all[ (top_all.df2 > 0) & (top_all.boll > 0)]

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
                    top_temp = top_all.copy()
                elif cct.get_now_time_int() > 935 and cct.get_now_time_int() <= 1450:
                    
                    if 'nlow' in top_all.columns:

                        # if st_key_sort == '4':
                        if st_key_sort.split()[0]  in st_key_sort_status :
                            top_temp = top_all.copy()

                        else:
                            top_temp = top_all.copy()
                    else:
                        top_temp = top_all.copy()

                else:
                    top_temp=top_all.copy() 

                if st_key_sort.split()[0] == 'x':
                    top_temp = top_temp[top_temp.topR != 0]
                
                if st_key_sort.split()[0] in ['1','7']:
                    if 'lastbuy' in top_all.columns:
                        top_all['dff'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                              top_all['buy'].values, top_all['lastbuy'].values)))
                        top_all['dff2'] = (list(map(lambda x, y: round((x - y) / y * 100, 1),
                                               top_all['buy'].values, top_all['lastp'].values)))

                    _top_all = top_all[top_all.close > 10]
                    if len(_top_all) > 0 and _top_all.lastp1d[0] == _top_all.close[0] and _top_all.lastp1d[-1] == _top_all.close[-1]:
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
                table, widths=cct.format_for_print(
                    top_dd.loc[[col for col in top_dd[:10].index if col in top_temp[:10].index]], widths=True)

                print(table)
                cct.counterCategory(top_temp)
                print(cct.format_for_print(top_dd[-4:], header=False, widths=widths))
                if status:
                    for code in top_all[:10].index:
                        code=re.findall('(\d+)', code)
                        if len(code) > 0:
                            code=code[0]
                            kind=sl.get_multiday_ave_compare_silent(code)
                top_all=top_bak
                del top_bak
                gc.collect()
            else:
                print("no data")
            int_time=cct.get_now_time_int()
            if cct.get_work_time():
                if int_time < ct.open_time:
                    top_all=pd.DataFrame()
                    cct.sleep(ct.sleep_time)
                elif int_time < 930:
                    cct.sleep((930 - int_time) * 52)
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
                        cct.sleeprandom(60)
                        time_s=time.time()
                        print(".")
                        break
            else:
                raise KeyboardInterrupt("StopTime")

        except (KeyboardInterrupt) as e:
            print("KeyboardInterrupt:", e)
            st=cct.cct_raw_input(ct.RawMenuArgmain() % (market_sort_value))

            if len(st) == 0:
                status=False
            elif len(cct.re_find_chinese(st)) > 0:
                cct.GlobalValues().setkey('search_key', st.strip())
            elif st == 'None' or st.lower() == 'no' :
                cct.GlobalValues().setkey('search_key', None)
            elif (len(st.split()[0]) == 1 and st.split()[0].isdigit()) or st.split()[0].startswith('x'):
                st_l=st.split()
                st_k=st_l[0]
                if st_k in list(ct.Market_sort_idx.keys()) and len(top_all) > 0:
                    st_key_sort=st
                    market_sort_value, market_sort_value_key=ct.get_market_sort_value_key(
                        st_key_sort, top_all=top_all)
                    if st_k not in ['1','7']:
                        top_all=pd.DataFrame()
                else:
                    log.error("market_sort key error:%s" % (st))
                    cct.sleeprandom(5)

            elif st.lower() == 'g' or st.lower() == 'go':
                status=True
            elif st.lower() == 'clear' or st.lower() == 'c':
                top_all=pd.DataFrame()
                cct.GlobalValues().setkey('lastbuylogtime', 1)
                status=False
            elif st.startswith('in') or st.startswith('i'):
                days = st.split()[1] if len(st.split()) > 1 else None
                if days is not None and days.isdigit():
                    top_all = pd.DataFrame()
                    indf = top_all = pd.DataFrame()
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
                    top_all = pd.DataFrame()
                    time_s = time.time()
                    status = False
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
                args=cct.writeArgmain().parse_args(st.split())
                codew=stf.WriteCountFilter(top_temp, writecount=args.dl)
                if args.code == 'a':
                    cct.write_to_blocknew(block_path, codew)
                else:
                    cct.write_to_blocknew(block_path, codew, False)
                print("wri ok:%s" % block_path)
                cct.sleeprandom(ct.duration_sleep_time / 2)
            elif st.lower() == 'r':
                dir_mo=eval(cct.eval_rule)
                if len(top_temp) > 0 and top_temp.lastp1d[0] == top_temp.close[0]:
                    cct.evalcmd(dir_mo,workstatus=False,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,resample=resample)
                else:
                    cct.evalcmd(dir_mo,Market_Values=ct_MonitorMarket_Values,top_temp=top_temp,block_path=block_path,top_all=top_all,resample=resample)
            elif st.lower() == 'rr':
                print(f"defaultRule: top_all.query{cct.read_ini(inifile='filter.ini',setrule='default',category='instock')}")
                rule = cct.cct_raw_input("filter_rule:")
                if len(rule.split()) > 1:
                    filterkey = rule.split()[-1]
                    query_rule = rule.replace(rule.split()[-1],'') if len(rule) > 0 else None
                else:
                    if rule.find('top_all') > 0:
                        filterkey = 'filter_rule'
                        query_rule = rule if len(rule) > 0 else None
                    else:
                        filterkey = rule.strip()
                set_query = cct.GlobalValues().getkey(filterkey)
                
                if rule.lower().startswith('w') and  query_rule is not None and set_query is not None:
                    cct.read_ini(inifile='filter.ini',setrule=f'top_all.query{set_query}',category='instock',filterkey=filterkey)
                else:
                    if rule.find('top_all') >= 0 or rule.find('top_temp') >= 0:
                        if query_rule is not None:
                            rule_query = query_rule.replace('top_all.query','').replace('top_temp.query','')
                        else:
                            rule_query = rule.replace('top_all.query','').replace('top_temp.query','')
                        cct.GlobalValues().setkey(filterkey,rule_query)
                        print(f'filterkey : {filterkey} set rule:{rule}')
                    else:
                        print(f"defaultRule: top_all.query{cct.read_ini(inifile='filter.ini',setrule='default',category='instock',filterkey=filterkey)}")
            elif st.startswith('q') or st.startswith('e'):
                print("exit:%s" % (st))
                sys.exit(0)
            else:
                print("input error:%s" % (st))
        except (IOError, EOFError) as e:
            print("IOError,EOFError", e)
            cct.sleeprandom(ct.duration_sleep_time / 2)
        except Exception as e:
            print("other Error", e)
            import traceback
            traceback.print_exc()
            cct.sleeprandom(ct.duration_sleep_time / 2)




