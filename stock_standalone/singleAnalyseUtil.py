# -*- coding: UTF-8 -*-
import datetime
import random
import os
import sys
import time
import types

import pandas as pd
import tushare as ts
# print sys.path
from JSONData import fundflowUtil as ffu
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct
from JSONData import realdatajson as rd
from JSONData import powerCompute as pct
from JSONData import get_macd_kdj_rsi as getab
from JSONData import tdx_data_Day as tdd
from JSONData import sina_data
# from JohnsonUtil import emacount as ema
from JohnsonUtil import LoggerFactory
log = LoggerFactory.getLogger("SingleSAU")
from JSONData import stockFilter as stf

try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib.request import urlopen, Request


# def get_today():
#     TODAY = datetime.date.today()
#     today = TODAY.strftime('%Y-%m-%d')
#     return today

global fibcount, except_count, dfcfw_Except_time, last_rzrq_fetch_time, width, height
fibcount = 0
except_count = 0
dfcfw_Except_time = 0
last_rzrq_fetch_time = 0
width, height = 108, 15


def time_sleep(timemin):
    # time1 = time.time()
    time.sleep(timemin)
    return True


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
                print(eval(cmd))
                print('')
            except Exception as e:
                print(e)
                evalcmd(dir_mo)
                break


def get_all_toplist():
    # gold = {}
    # goldl = []
    df = ts.get_today_all()
    top = df[df['changepercent'] > 6]
    top = top[top['changepercent'] < 10]
    list = top.index
    print(len(list))
    return list


def _write_to_csv(df, filename, indexCode='code'):
    TODAY = datetime.date.today()
    CURRENTDAY = TODAY.strftime('%Y-%m-%d')
    #     reload(sys)
    #     sys.setdefaultencoding( "gbk" )
    df = df.drop_duplicates(indexCode)
    df = df.set_index(indexCode)
    from sys_utils import get_app_root
    output_path = os.path.join(get_app_root(), CURRENTDAY + '-' + filename + '.csv')
    df.to_csv(output_path,
              encoding='gbk', index=False)  # 选择保存
    print("write csv")

    # df.to_csv(filename, encoding='gbk', index=False)


def get_multiday_ave_compare(code, dayl='10'):
    pass
#     dtick = ts.get_today_ticks(code)
#     d_hist = ema.getdata_ema_trend(code, dayl, 'd')
#     # print d_hist
#     day_t = ema.get_today()
#     if d_hist is not None:
#         if day_t in d_hist.index:
#             dl = d_hist.drop(day_t).index
#         else:
#             dl = d_hist.index
#     else:
#         return 0
#     # print dl
#     # print dl
#     ep_list = []
#     for da in dl.values:
#         # print da
#         td = ts.get_tick_data(code, da)
#         # print td
#         if not type(td) == type(None):
#             ep = td['amount'].sum() / td['volume'].sum()
#             ep_list.append(ep)
#             print(("D: %s P: %s" % (da[-5:], ep)))

#     ave = ema.less_average(ep_list)
#     if len(dtick.index) > 0:
#         ep = dtick['amount'].sum() / dtick['volume'].sum()
#         p_now = dtick['price'].values[0] * 100
#         if p_now > ave and ep > ave:
#             print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
#                   (code, ep, p_now, ave, cct.get_now_time())))
#         elif p_now > ave and ep < ave:
#             print(("gold:%s ep:%s UP:%s! A:%s %s !" %
#                   (code, ep, p_now, ave, cct.get_now_time())))
#         elif p_now < ave and ep > ave:
#             print(("down:%s ep:%s Dow:%s? A:%s %s ?" %
#                   (code, ep, p_now, ave, cct.get_now_time())))
#         else:
#             print(("DOWN:%s ep:%s now:%s??? A:%s %s ???" %
#                   (code, ep, p_now, ave, cct.get_now_time())))
#     return ave


def get_multiday_ave_compare_silent(code, dayl='10'):
    pass
    # dtick = ts.get_today_ticks(code)
    # d_hist = ema.getdata_ema_trend_silent(code, dayl, 'd')
    # # print d_hist
    # day_t = ema.get_today()
    # if day_t in d_hist.index:
    #     dl = d_hist.drop(day_t).index
    # else:
    #     dl = d_hist.index
    # # print dl
    # # print dl
    # ep_list = []
    # for da in dl.values:
    #     # print code,da
    #     td = ts.get_tick_data(code, da)
    #     # print td
    #     if not type(td) == type(None):
    #         ep = td['amount'].sum() / td['volume'].sum()
    #         ep_list.append(ep)
    #         # print ("D: %s P: %s" % (da[-5:], ep))
    # ave = ema.less_average(ep_list)
    # if len(dtick.index) > 0:
    #     ep = dtick['amount'].sum() / dtick['volume'].sum()
    #     p_now = dtick['price'].values[0] * 100
    #     if p_now > ave or ep > ave:
    #         print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
    #               (code, ep, p_now, ave, get_now_time())))
    #         # elif p_now > ave and ep < ave:
    #         #     print ("gold:%s ep:%s UP:%s! A:%s %s !" % (code, ep, p_now, ave, get_now_time()))
    #         # elif p_now < ave and ep > ave:
    #         #     print ("down:%s ep:%s Dow:%s? A:%s %s ?" % (code, ep, p_now, ave, get_now_time()))
    #         return True
    #     else:
    #         if p_now < ave and ep < ave:
    #             print(("DOWN:%s ep:%s now:%s??? A:%s %s ???" %
    #                   (code, ep, p_now, ave, get_now_time())))
    #         return False


# def get_yestoday_tick_status(code, ave=None):
#     try:
#         dn = get_realtime_quotes(code)

#         dtick = ts.get_today_ticks(code)
#         # try:
#         if len(dtick.index) > 0:
#             p_now = dtick['price'].values[0] * 100
#             ep = dtick['amount'].sum() / dtick['volume'].sum()
#             if not ave == None:
#                 if p_now > ave and ep > ave:
#                     print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
#                           (code, ep, p_now, ave, get_now_time())))
#                 elif p_now > ave and ep < ave:
#                     print(("gold:%s ep:%s UP:%s! A:%s %s !" %
#                           (code, ep, p_now, ave, get_now_time())))
#                 elif p_now < ave and ep > ave:
#                     print(("down:%s ep:%s Dow:%s? A:%s %s ?" %
#                           (code, ep, p_now, ave, get_now_time())))
#                 else:
#                     print(("DOWN:%s ep:%s now:%s??? A:%s %s ???" %
#                           (code, ep, p_now, ave, get_now_time())))
#             else:
#                 if ep > ave:
#                     print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
#                           (code, ep, p_now, ave, get_now_time())))
#                 else:
#                     print(("down:%s ep:%s now:%s??? A:%s %s ?" %
#                           (code, ep, p_now, ave, get_now_time())))

#         else:
#             df = ts.get_realtime_quotes(code)
#             print("name:%s op:%s  price:%s" % (df['name'].values[0], df['open'].values[0], df['price'].values[0]))
#     except (IOError, EOFError, KeyboardInterrupt) as e:
#         print(("Except:%s" % (e)))
#         # print "IOError"


def get_today_tick_ave(code, ave=None):
    try:
        dtick = ts.get_today_ticks(code)
        df = dtick
        if len(dtick.index) > 0:
            p_now = dtick['price'].values[0] * 100
            ep = dtick['amount'].sum() / dtick['volume'].sum()
            if not ave == None:
                if p_now > ave and ep > ave:
                    print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
                          (code, ep, p_now, ave, get_now_time())))
                elif p_now > ave and ep < ave:
                    print(("gold:%s ep:%s UP:%s! A:%s %s !" %
                          (code, ep, p_now, ave, get_now_time())))
                elif p_now < ave and ep > ave:
                    print(("down:%s ep:%s Dow:%s? A:%s %s ?" %
                          (code, ep, p_now, ave, get_now_time())))
                else:
                    print(("DOWN:%s ep:%s now:%s??? A:%s %s ???" %
                          (code, ep, p_now, ave, get_now_time())))
            else:
                if ep > ave:
                    print(("GOLD:%s ep:%s UP:%s!!! A:%s %s !!!" %
                          (code, ep, p_now, ave, get_now_time())))
                else:
                    print(("down:%s ep:%s now:%s??? A:%s %s ?" %
                          (code, ep, p_now, ave, get_now_time())))

        else:
            df = ts.get_realtime_quotes(code)
            print("name:%s op:%s  price:%s" % (df['name'].values[0], df['open'].values[0], df['price'].values[0]))
        # print df
        return df
    except (IOError, EOFError, KeyboardInterrupt) as e:
        print(("Except:%s" % (e)))
        # print "IOError"


def f_print(lens, datastr, color=None):
    # if lens < len(str(datastr)):
        # log.warn("str:%s f_print:%s %s"%(datastr,lens,len(str(datastr))))
    lenf = '{0:>%s}' % (lens)
    data = lenf.format(datastr)
    # print("\033[1;31;40m您输入的帐号或密码错误！\033[0m")
    # \033[5;31;42m
    # https://www.cnblogs.com/hellojesson/p/5961570.html
    """数值表示的参数含义：
    # 显示方式: 0（默认值）、1（高亮）、22（非粗体）、4（下划线）、24（非下划线）、 5（闪烁）、25（非闪烁）、7（反显）、27（非反显）
    # 前景色: 30（黑色）、31（红色）、32（绿色）、 33（黄色）、34（蓝色）、35（洋 红）、36（青色）、37（白色）
    # 背景色: 40（黑色）、41（红色）、42（绿色）、 43（黄色）、44（蓝色）、45（洋 红）、46（青色）、47（白色）

    # 常见开头格式：
    # \033[0m            默认字体正常显示，不高亮
    # \033[32;0m       红色字体正常显示
    # \033[1;32;40m  显示方式: 高亮    字体前景色：绿色  背景色：黑色
    # \033[0;31;46m  显示方式: 正常    字体前景色：红色  背景色：青色
    """
    # data = "\033[1;31;40m%s\033[0m"%(data)
    # color_dic = {31:'47',32:'40'}
    color_dic = {31: '47', 32: '47', 35: '47'}
    if color is not None:
        if color != 31:
            # if color == 32:
                # color = 35
            flash = 5
        else:
            flash = 1
        data = "\033[%s;%s;%sm%s\033[0m" % (
            flash, color, color_dic[color], data)
    return data


def fibonacciCount(code, dl=60, start=None, days=0):
    fibl = []
    if not isinstance(code, list):
        codes = [code]
    else:
        codes = code
    for code in codes:
        df = tdd.get_tdx_append_now_df_api(code, dl=dl)
        for ptype in ['low', 'high']:
            if ptype == 'low':
                op, ra, st, daysData = pct.get_linear_model_status(
                    code, df=df, filter='y', dl=dl, ptype=ptype, days=days)
                dd, boll = getab.Get_BBANDS(df, days=days)
            else:
                # df = tdd.get_tdx_append_now_df_api(code,dl=dl)
                op, ra, st, daysData = pct.get_linear_model_status(
                    code, df=df, filter='y', dl=dl, ptype=ptype, days=days)
            if daysData is not None and len(daysData) > 0:
                d_val = daysData[0]
                if len(daysData) > 1 and hasattr(daysData[1], 'ma5d') and len(daysData[1].ma5d) > 0:
                    ma5_val = int(daysData[1].ma5d[0]) if daysData[1].ma5d[0] else 0
                else:
                    ma5_val = 0
            else:
                d_val = 0
                ma5_val = 0
            fib = cct.getFibonacci(300, d_val)
            st = cct.parse_date_safe(st) if st else ''
            fibl.append(
                [code, op, ra, [d_val, ma5_val], fib, st])
    return fibl


# global cumin_index
# cumin_index = {}
top_Ten_Dropcxg = []


def get_hot_countNew(changepercent, rzrq, fibl=None, fibc=10):
    global fibcount, dfcfw_Except_time
    INDEX_LIST_TDX = {'999999': 'sh', '399001': 'sz', '399006': 'cyb'}
    # {v: k for k, v in m.items()}
    # >>> zip(m.values(), m.keys())
    # mi = dict(zip(m.values(), m.keys()))
    if fibcount == 0 or fibcount >= fibc:
        if fibcount >= fibc:
            fibcount = 1
        else:
            fibcount += 1
        if fibl is not None:
            int = 0
            
            for f in fibl:
                code, op, ra, daysData, fib, st = f[
                    0], f[1], f[2], f[3], f[4], f[5]
                # cumin_index[INDEX_LIST_TDX[code]]=cumin
                int += 1
                if int % 2 != 0:
                    print("%s op:%s ra:%s d:%s fib:%s m5:%s  %s" % (code, f_print(3, op), f_print(5, ra), f_print(2, daysData[0]), f_print(3, fib), f_print(4, daysData[1]), st), end=' ')
                else:
                    print("%s op:%s ra:%s d:%s fib:%s m5:%s " % (st, f_print(3, op), f_print(5, ra), f_print(2, daysData[0]), f_print(3, fib), f_print(4, daysData[1])))

    else:
        fibcount += 1
    allTop = pd.DataFrame()
    indexKeys = ['sh', 'sz', 'cyb']
    # ffindex = ffu.get_dfcfw_fund_flow('all')
    ffindex = ffu.get_dfcfw_fund_flow2020('all')

    ffall = {}
    topTen_all = 0
    topTen_all_st = 0
    crashTen_all = 0
    crashTen_all_st = 0
    ffall['zlr'] = 0
    ffall['zzb'] = 0
    sina = sina_data.Sina(readonly=True)
    sina.all
    for market in indexKeys:
        # market = ct.SINA_Market_KEY()
        #        df = rd.get_sina_Market_json(market, False)
        df = sina.market(market)
        # count=len(df.index)
        # log.info("market:%s" % df[:1])
        df = df.dropna(how='all')
        df = df[df.close > 0]
        if 'percent' not in df.columns:
            df['percent'] = list(map(lambda x, y: round(
                (x - y) / y * 100, 1), df.close.values, df.llastp.values))

        if 'percent' in df.columns.values:
            # and len(df[:20][df[:20]['percent']>0])>3:
            # if 'code' in df.columns:
            #     top = df[df['percent'] > changepercent]
            #     topTen = df[df['percent'] > 9.9]
            #     crashTen = df[df['percent'] < -9.8]
            #     crash = df[df['percent'] < -changepercent]
            # else:
            cyb = df[df.index.str.startswith('30')]
            kcb = df[df.index.str.startswith('68')]
            top = df[df['percent'] > changepercent]
            st = df[df.name.str.contains('ST')]

            # 按市场规则独立计算涨跌停：创业板(30)/科创板(68) ±20%，主板/ST ±10%
            if market == 'cyb':
                # 创业板整体 ±20%（含300/301开头），科创板(68开头)同规则
                # cyb数据源包含创业板全体，科创板在sz市场内，此处仅创业板市场
                topTen = df.query('b1_v > a1_v and b1_v > 0 and percent > 19')
                crashTen = df.query('b1_v < a1_v and a1_v > 0 and percent < -19')
            else:
                # sh/sz 主板：区分科创板(68开头)用20%，普通主板用10%
                kcb_mask = df.index.str.startswith('68')
                normal_mask = ~kcb_mask
                # 科创板涨停
                topTen_kcb = df[kcb_mask].query('b1_v > a1_v and b1_v > 0 and percent > 19') if kcb_mask.any() else df.iloc[0:0]
                # 普通主板涨停
                topTen_normal = df[normal_mask].query('b1_v > a1_v and b1_v > 0 and percent > 9') if normal_mask.any() else df.iloc[0:0]
                topTen = pd.concat([topTen_kcb, topTen_normal])
                # 科创板跌停
                crashTen_kcb = df[kcb_mask].query('b1_v < a1_v and a1_v > 0 and percent < -19') if kcb_mask.any() else df.iloc[0:0]
                # 普通主板跌停
                crashTen_normal = df[normal_mask].query('b1_v < a1_v and a1_v > 0 and percent < -9') if normal_mask.any() else df.iloc[0:0]
                crashTen = pd.concat([crashTen_kcb, crashTen_normal])

            # ST股新规：涨跌停改为±10%（与主板一致），废弃旧无量法
            if market == 'cyb':
                # cyb市场ST股仍为±10%（非创业板±20%），需单独用percent±9%抓取
                topTen_st = st.query('b1_v > a1_v and b1_v > 0 and percent > 9') if len(st) > 0 else df.iloc[0:0]
                crashTen_st = st.query('b1_v < a1_v and a1_v > 0 and percent < -9') if len(st) > 0 else df.iloc[0:0]
            else:
                # sh/sz市场：ST股±10%已被normal_mask的 percent>9/<-9 规则捕获，置空避免重复计数
                topTen_st = df.iloc[0:0]
                crashTen_st = df.iloc[0:0]
            crash = df[df['percent'] < -changepercent]
        else:
            log.info("market No Percent:%s" % df[:1])
            top = '0'
            topTen = '0'
            topTen_st = '0'
            crashTen = '0'
            crash = '0'
            crashTen_st = '0'
        topTen_all += len(topTen)
        topTen_all_st += len(topTen_st)
        crashTen_all += len(crashTen)
        crashTen_all_st += len(crashTen_st)
        # top=df[ df['changepercent'] <6]
        # print("\033[1;31;40m您输入的帐号或密码错误！\033[0m")
        print((
            "%s topT: %s top>%s: %s" % (
                f_print(4, market), f_print(3, len(topTen)+len(topTen_st)), changepercent, f_print(4, len(top)))), end=' ')
        print(("crashT:%s crash<-%s:%s" %
              (f_print(4, len(crashTen)+len(crashTen_st)), changepercent, f_print(4, len(crash)))), end=' ')
        # print(u"-5:%s" %
        #       (f_print(4, len(crash[crash < -5])))),
        ff = ffindex[market]
        if len(ff) > 0:
            zlr = float(ff['zlr'])
            zzb = float(ff['zzb'])
            ffall['zlr'] = ffall['zlr'] + zlr
            ffall['zzb'] = ffall['zzb'] + zzb
            # zt=str(ff['time'])
            # modfprint=lambda x:f_print(4,x) if x>0 else "-%s"%(f_print(4,str(x).replace('-','')))
            # print modfprint(zlr)
            # print (u"流入: %s亿 比: %s%%" % (modfprint(zlr), modfprint(zzb))),
            print(("流入: %s亿 比: %s%% " %
                  (f_print(6, zlr, 32), f_print(4, zzb, 32))), end=' ')
            if 'close' in list(ff.keys()):
                if ff['close'] == 0:
                    _percent = 0
                else:
                    _percent = round(
                        (ff['close'] - ff['lastp']) * 100 / ff['close'], 2)
            else:
                _percent = 0
                ff['close'] = 0.0
                ff['open'] = 0.0
                ff['lastp'] = 0.0
            # print (u" %s"%(f_print(2,cumin_index[market],31))),
            print(("%s %s%% %s%s" % (f_print(7, ff['close']), f_print(4, _percent, 31), f_print(1, '!' if ff['open'] > ff[
                'lastp'] else '?'), f_print(2, '!!' if ff['close'] > ff['lastp'] else '??', 32))))
        allTop = pd.concat([allTop,df.reset_index()], ignore_index=True)
        allTop = allTop.drop_duplicates()
    df = allTop
    df = tdd.get_single_df_lastp_to_df(
        df.set_index('code'), resample='d')
    count = len(df.index)
    top = df[df['percent'] > changepercent]

    topTen = df[df['percent'] >= 9.9]
    if 'max5' in df.columns:
        top_Max = (df[(df.close >= df.hmax) & (df.close >= df.max5)])

        # top_low = len(df[df.low < df.min5])
        top_min = (df[(df.close <= df.lmin) & (df.close <= df.min5)])
        cct.GlobalValues().setkey('top_max', top_Max)
        cct.GlobalValues().setkey('top_min', top_min)

    else:
        top_Max = pd.DataFrame()
        top_low = 0
        top_min = pd.DataFrame()
        cct.GlobalValues().setkey('top_max', top_Max)
        cct.GlobalValues().setkey('top_min', top_min)

    # topTen = str(len(topTen)) +'('+str(len(top_Ten_Dropcxg))+')' +'(H:'+str(len(top_Max))+')'
    topTen = str(topTen_all+topTen_all_st) + '(' + str(len(topTen)) + ')' + \
        '(H:' + str(len(top_Max)) + ')'
    # print "top_Ten_Dropcxg:%s",top_Ten_Dropcxg
    # crashTen = df[df['percent'] < -9.8]
    crashTen = str(crashTen_all+crashTen_all_st) + '(L:' + str(len(top_min)) + ')'

    crash = df[df['percent'] < -changepercent]

    print((
        "AL:%s topT:%s top>%s:%s" % (
            f_print(4, count), f_print(3, (topTen), 31), changepercent, f_print(4, len(top), 31))), end=' ')
    print(("crashT:%s crash<-%s:%s" %
          (f_print(3, (crashTen), 32), changepercent, f_print(4, len(crash), 31))), end=' ')
    print(("-5:%s" %
          (f_print(4, len(crash[crash.percent < -5]), 32))), end=' ')
    # ff = ffu.get_dfcfw_fund_flow(ct.DFCFW_FUND_FLOW_ALL)
    ffall['time'] = ff['time']
    ff = ffall
    zzb = 0
    if len(ff) > 0:
        zlr = round(float(ff['zlr']), 1)
        zzb = round(float(ff['zzb']) / 3, 1)
        zt = str(ff['time'])
        print(("流入: %s亿 占比: %s%% %s" %
              (f_print(4, zlr, 31), f_print(4, zzb, 31), f_print(4, zt))))
    ff = {}
    hgt = {}
    szt = {}
    dfcfw_Except = cct.GlobalValues().getkey('dfcfw_Except')
    global dfcfw_Except_time
    if not dfcfw_Except and dfcfw_Except_time == 0:
        try:
            ff = ffu.get_dfcfw_fund_SHSZ()
            hgt = ffu.get_dfcfw_fund_HGSZ2021('bei')
            szt = ffu.get_dfcfw_fund_HGSZ2021('nan')
        except Exception as e:
            print(f'get_dfcfw_fund_SHSZ Exception: {e}')
            cct.GlobalValues().setkey('dfcfw_Except', True)
            dfcfw_Except_time = time.time()
            # raise e
    else:
        duration_dfcfw_Except_time = time.time() - dfcfw_Except_time
        if duration_dfcfw_Except_time > 60:
            dfcfw_Except_time = 0
            cct.GlobalValues().setkey('dfcfw_Except', False)
    log.debug("shzs:%s hgt:%s" % (ff, hgt))
    # if len(ff) > 0:
    #     print ("\tSH: %s u:%s vo: %s sz: %s u:%s vo: %s" % (
    #         f_print(4, ff['scent']), f_print(4, ff['sup']), f_print(5, ff['svol']), f_print(4, ff['zcent']),
    #         f_print(4, ff['zup']),
    #         f_print(5, ff['zvol']))),
    bigcount = rd.getconfigBigCount(count=None, write=True)

    if ff:
        print(("\tSh: %s Vr:%s Sz: %s Vr:%s " % (
            f_print(4, ff.get('scent', 0)),
            f_print(5, ff.get('svol', 0), 31),
            f_print(4, ff.get('zcent', 0)),
            f_print(5, ff.get('zvol', 0), 31)
        )), end=' ')
        print(('B:%s-%s V:%s' % (
            bigcount[0], bigcount[2], f_print(4, bigcount[1])
        )))
    else:
        print(("\tSh: \t%s Vr:  \t%s Sz: \t%s Vr: \t%s ") % (0, 0, 0, 0), end=' ')
        print(('B:%s-%s V:%s' % (
            bigcount[0], bigcount[2], f_print(4, bigcount[1])
        )))

    if hgt:
        print(("\tSgt: %s Gst: %s Hgt: %s Ggt: %s SSVol:%s" % (
            hgt.get('ggt', 0),
            szt.get('ggt', 0),
            hgt.get('hgt', 0),
            szt.get('hgt', 0),
            f_print(10, ff.get('allvol', 0), 32)
        )))
    else:
        print(("\t%s Sgt: %s Gst: %s \tHgt: \t%s Ggt: " % (0, 0, 0, 0)))

    if len(rzrq) > 0 and isinstance(rzrq, dict):
        try:
            sh_val = float(rzrq.get('sh', 0) or 0)
            sz_val = float(rzrq.get('sz', 0) or 0)
            all_val = float(rzrq.get('all', 0) or 0)
            shrz_val = float(rzrq.get('shrz', 0) or 0)
            szrz_val = float(rzrq.get('szrz', 0) or 0)
            dff_val = float(rzrq.get('dff', 0) or 0)
            is_partial = rzrq.get('is_partial', False)

            shpcent = round((shrz_val / sh_val * 100), 1) if sh_val > 0 else '?'
            szpcent = round((szrz_val / sz_val * 100), 1) if (sz_val > 0 and not is_partial) else ('?*' if is_partial else '?')
            print(("\tSh: %s rz:%s :%s%% sz: %s rz:%s :%s%% All: %s diff: %s亿" % (
                f_print(5, sh_val), f_print(4, shrz_val), shpcent,
                f_print(5, sz_val), f_print(4, szrz_val), szpcent,
                f_print(4, all_val, 31), f_print(5, dff_val, 31))))
        except Exception as e_rz:
            log.warning("print rzrq exception: %s" % e_rz)
    # print "bigcount:",bigcount

    cct.set_console(width, height,
                    title=['B:%s-%s V:%s' % (bigcount[0], bigcount[2], bigcount[1]), 'ZL: %s' % (zlr if len(ff) > 0 else 0),
                           'To:%s' % len(topTen), 'D:%s' % len(
                        crash), 'Sh: %s ' % ff['scent'] if len(ff) > 0 else '?', 'Vr:%s%% ' % ff['svol'] if len(ff) > 0 else '?',
                        'MR: %s' % zzb, 'ZL: %s' % (zlr if len(ff) > 0 else '?')], closeTerminal=True)

    log.debug("set_console:bigcount[0]%s  bigcount[2]:%s" % (
        bigcount[0], bigcount[2]))

    return allTop


def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)


# signal.signal(signal.SIGINT, signal_handler)
# print 'Press Ctrl+C'
# signal.pause()
def handle_ctrl_c(signal, frame):
    print("Got ctrl+c, going down!")
    sys.exit(0)


def get_hot_loop(timedelay, percent=3):
    if get_now_time():
        df = get_hot_count(percent)
        # _write_to_csv(df,'tick-data')
        # print ""
    time.sleep(timedelay)


def get_code_search_loop(num_input, code='', timed=60, dayl='10', ave=None):
    # if not status:
    #
    if cct.get_work_time():
        if code == num_input:
            get_today_tick_ave(code, ave)
        else:
            ave = get_multiday_ave_compare(num_input, dayl)
    time.sleep(timed)
    return ave


if __name__ == '__main__':
    # get_multiday_ave_compare('601198')
    from docopt import docopt
    # log = LoggerFactory.log
    log = LoggerFactory.getLogger()
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

#    log.setLevel(LoggerFactory.DEBUG)
    # print len(sys.argv)
    if cct.isMac():
        width, height = 108, 15
        cct.set_console(width, height)
    else:
        width, height = 108, 15
        cct.set_console(width, height)

    if len(sys.argv) == 2:
        status = True
        num_input = sys.argv[1]
        # print num_input
    elif (len(sys.argv) > 2):
        pass
    else:
        status = False
        num_input = ''

    status = False
    code = ''
    ave = None
    days = '10'
    success = 0
    # rzrq = ffu.get_dfcfw_rzrq_SHSZ2()
    rzrq = ffu.get_dfcfw_rzrq_SHSZ()
    last_rzrq_fetch_time = time.time()
    rzrq_date = cct.get_today()
    today_str = cct.get_today()
    dl = 60
    fibc = 3
    fibl = fibonacciCount(['999999', '399001', '399006'], dl=dl)
    percentDuration = 0.1
    cct.get_terminal_Position(position=sys.argv[0])
    cct.GlobalValues().setkey('dfcfw_Except', False)
    dfcfw_Except_time = 0
    blkname = '061.blk'
    block_path = tdd.get_tdx_dir_blocknew() + blkname

    # 读取持久化收盘状态
    try:
        conf_ini = cct.get_conf_path('global.ini')
        CFG = cct.GlobalConfig(conf_ini)
        write_all_day_date = CFG.write_all_day_date
    except Exception as e_init_cfg:
        log.warning("GlobalConfig init warning: %s" % e_init_cfg)
        CFG = None
        write_all_day_date = ''

    # 首次启动必须完整走完并显示一次市场资金强弱流程
    first_run = True

    while 1:
        try:
            current_today = cct.get_today()
            # 跨天检测：次日自动重新初始化
            if current_today != today_str:
                log.info("Trading day changed from %s to %s. Auto-reinitializing for 24x7 running..." % (today_str, current_today))
                today_str = current_today
                rzrq = ffu.get_dfcfw_rzrq_SHSZ()
                last_rzrq_fetch_time = time.time()
                rzrq_date = today_str
                fibcount = 0
                fibl = fibonacciCount(['999999', '399001', '399006'], dl=dl)
                cct.GlobalValues().setkey('top_max', None)
                cct.GlobalValues().setkey('dfcfw_Except', False)
                dfcfw_Except_time = 0
                status = False
                num_input = ''
                ave = None
                code = ''
                except_count = 0
                first_run = True  # 次日跨天后也允许首次运行完整显示一次
            elif today_str != rzrq_date and (time.time() - last_rzrq_fetch_time > 180):
                log.info("rzrq_date changed from %s to %s. Auto-initializing rzrq..." % (rzrq_date, today_str))
                rzrq = ffu.get_dfcfw_rzrq_SHSZ()
                last_rzrq_fetch_time = time.time()
                rzrq_date = today_str

            int_time = cct.get_now_time_int()
            is_work_time = cct.get_work_time()
            is_work_duration = cct.get_work_duration()

            # 1. 首次启动初始化，或 盘中工作时间 (9:15-11:30, 13:00-15:05)，或 手动个股查询模式
            if first_run or is_work_time or status:
                if not status:
                    if len(fibl) == 0 or fibcount >= fibc:
                        fibcount = 0
                        fibl = fibonacciCount(
                            ['999999', '399001', '399006'], dl=dl)
                        
                    # 防 ban 冷却与必要更新检查：严禁每秒请求，最小冷却 300 秒 (5分钟)
                    need_fetch_rzrq = False
                    if len(rzrq) == 0 or rzrq.get('all', 0) == 0 or rzrq.get('sh', 0) == 0:
                        need_fetch_rzrq = True
                    elif rzrq.get('is_partial', False) and (930 <= int_time <= 1505):
                        # 深市数据若早盘缺失，盘中每 5 分钟尝试补全一次
                        need_fetch_rzrq = True

                    if need_fetch_rzrq and (time.time() - last_rzrq_fetch_time > 300):
                        log.info("Intraday refreshing rzrq data (cooldown passed)...")
                        new_rz = ffu.get_dfcfw_rzrq_SHSZ()
                        last_rzrq_fetch_time = time.time()
                        if new_rz and new_rz.get('all', 0) > 0:
                            rzrq = new_rz
                            rzrq_date = today_str

                    log.info('start get_hot_count')
                    get_hot_countNew(percentDuration, rzrq, fibl, fibc)
                    fibcount += 1
                else:
                    if not num_input:
                        num_input = input("please input code:")
                        if num_input == 'ex' or num_input == 'qu' \
                                or num_input == 'q' or num_input == "e":
                            sys.exit()
                        elif not num_input or not len(num_input) == 6:
                            print("Please input 6 code:or exit")
                            num_input = ''
                    if num_input:
                        if ave is None:
                            ave = get_code_search_loop(num_input, code, dayl=days)
                        else:
                            ave = get_code_search_loop(
                                num_input, code, dayl=days, ave=ave)
                        code = num_input

                # 首次运行走完后打印状态并切换标记
                if first_run:
                    first_run = False
                    if not is_work_time and not is_work_duration:
                        if write_all_day_date == today_str:
                            print("\n[INIT] 检测到今日 (%s) 盘后收盘数据已处理完毕并持久化记忆 (write_all_day_date=%s)。" % (today_str, write_all_day_date))
                            print("[INIT] 当前处于非交易时段，进入 24*7 自动等待状态 (每 5 分钟呼吸打点)...", flush=True)
                        elif not cct.get_trade_date_status():
                            print("\n[INIT] 今日 (%s) 为非交易日/休市日，无需执行盘后数据处理。" % today_str)
                            print("[INIT] 进入 24*7 自动等待状态 (每 5 分钟呼吸打点)...", flush=True)

                # 盘中休眠控制
                if is_work_time:
                    log.debug('into get_work_time:%s' % (int_time))
                    if 920 < int_time < 926:
                        cct.sleeprandom(cct.duration_sleep_time)
                    elif 926 < int_time < 930:
                        while 1:
                            cct.sleep(cct.duration_sleep_time)
                            if cct.get_now_time_int() < 931:
                                cct.sleep(cct.duration_sleep_time)
                                print(".", end='', flush=True)
                            else:
                                fibcount = 0
                                break
                    else:
                        cct.sleep(ct.single_duration_sleep_time)
                    
            # 2. 盘前准备或午间休市 (7:00-9:15, 11:30-13:00)
            elif is_work_duration:
                log.debug('into work_duration:%s' % (int_time))
                # 盘前准备阶段 (8:40 ~ 9:15)：若为交易日且深市未全或距上次抓取超 10 分钟，尝试刷新一次
                if 840 <= int_time < 915 and (time.time() - last_rzrq_fetch_time > 180):
                    if rzrq.get('is_partial', False) or (time.time() - last_rzrq_fetch_time > 600):
                        log.info("Pre-market auto-refreshing rzrq data...")
                        new_rz = ffu.get_dfcfw_rzrq_SHSZ()
                        last_rzrq_fetch_time = time.time()
                        if new_rz and new_rz.get('all', 0) > 0:
                            rzrq = new_rz
                            rzrq_date = today_str

                while 1:
                    if cct.get_work_duration():
                        print(".", end='', flush=True)
                        cct.sleep(ct.single_duration_sleep_time)
                    else:
                        print("#")
                        cct.sleep(random.randint(0, 30))
                        fibcount = 0
                        break

            # 3. 盘后及非交易时间 (clean_duration / 夜间 / 周末 / 节假日)
            else:
                log.debug('into clean_duration:%s' % (int_time))
                
                # 检查是否需要执行盘后收盘写入与备份（仅交易日收盘 15:01 之后且当天未处理过时触发）
                need_write = False
                if cct.get_trade_date_status() and int_time > 1501:
                    if write_all_day_date != today_str:
                        need_write = True

                if need_write:
                    # 如果在 15:01-15:05 之间，稍作等待收盘数据齐全
                    if 1501 < int_time < 1505:
                        print(".", end='', flush=True)
                        cct.sleep(cct.duration_sleep_time)
                    else:
                        print("\nwrite dm to file")
                        tdd.Write_market_all_day_mp('all')
                        top_temp = cct.GlobalValues().getkey('top_max')
                        codew = stf.WriteCountFilter(top_temp, writecount='all')
                        
                        # 执行 RamDisk 备份
                        if cct.isMac():
                            ramdisk_h5 = '/Users/Johnson/Downloads/Temp/Ramdisk/sina_MultiIndex_data.h5'
                            if os.path.exists(ramdisk_h5):
                                os.system('/bin/sh /Users/Johnson/saveRamdisk.sh')
                                time.sleep(1)
                                print("saveRamdisk is OK")
                        else:
                            ramdisk_h5 = 'D:\\Ramdisk\\sina_MultiIndex_data.h5'
                            if os.path.exists(ramdisk_h5):
                                os.system('cmd /c start C:\\Users\\Johnson\\Documents\\1-ramdisk_back.bat')
                                time.sleep(1)
                                print("1-ramdisk_back is OK")
                        
                        # 记录并持久化收盘数据已完成
                        write_all_day_date = today_str
                        try:
                            if CFG is not None:
                                CFG.set_and_save("general", "write_all_day_date", today_str)
                            else:
                                conf_ini = cct.get_conf_path('global.ini')
                                CFG = cct.GlobalConfig(conf_ini)
                                CFG.set_and_save("general", "write_all_day_date", today_str)
                        except Exception as e_cfg:
                            log.error("Save write_all_day_date error: %s" % (e_cfg))
                        print("All is ok. EOD task finished for %s. Entering auto-waiting state..." % today_str)
                else:
                    # 当天收盘已做完或处于非交易等待状态：5分钟输出一次呼吸打点，绝不频繁刷屏
                    print(".", end='', flush=True)
                    # 休眠 300 秒 (5分钟)，每 15 秒检查一次是否跨天或到达开盘/盘前时段
                    for _ in range(20):
                        time.sleep(15)
                        if cct.get_today() != today_str or cct.get_work_time() or cct.get_work_duration():
                            break

        except (KeyboardInterrupt) as e:
            print("\nKeyboardInterrupt:", e)
            st = cct.cct_raw_input("status:[go(g),clear(c),quit(q,e),wri(w)]:")
            today_str = cct.get_today()
            if len(st) == 0:
                status = False
            elif st.lower() == 'g' or st.lower() == 'go':
                status = True
                num_input = ''
                ave = None
                code = ''
            elif st.lower() == 'c' or st.lower() == 'C':
                log.info("Manually re-fetching rzrq data...")
                rzrq = ffu.get_dfcfw_rzrq_SHSZ()
                last_rzrq_fetch_time = time.time()
                rzrq_date = cct.get_today()
            elif st.startswith('w') or st.lower() == 'w':
                print("Manual trigger write dm to file...")
                tdd.Write_market_all_day_mp('all')
                top_temp = cct.GlobalValues().getkey('top_max')
                codew = stf.WriteCountFilter(top_temp, writecount='all')
                if cct.isMac():
                    ramdisk_h5 = '/Users/Johnson/Downloads/Temp/Ramdisk/sina_MultiIndex_data.h5'
                    if os.path.exists(ramdisk_h5):
                        os.system('/bin/sh /Users/Johnson/saveRamdisk.sh')
                        time.sleep(1)
                        print("saveRamdisk is OK")
                else:
                    ramdisk_h5 = 'D:\\Ramdisk\\sina_MultiIndex_data.h5'
                    if os.path.exists(ramdisk_h5):
                        os.system('cmd /c start C:\\Users\\Johnson\\Documents\\1-ramdisk_back.bat')
                        time.sleep(1)
                        print("1-ramdisk_back is OK")
                write_all_day_date = today_str
                try:
                    if CFG is not None:
                        CFG.set_and_save("general", "write_all_day_date", today_str)
                    else:
                        conf_ini = cct.get_conf_path('global.ini')
                        CFG = cct.GlobalConfig(conf_ini)
                        CFG.set_and_save("general", "write_all_day_date", today_str)
                except Exception as e_cfg:
                    log.error("Save write_all_day_date error: %s" % (e_cfg))
            elif len(st) == 6 and st.isdigit():
                status = True
                num_input = st
                ave = None
                code = ''
            elif st.lower() == 'r':
                dir_mo = eval(cct.eval_rule)
                evalcmd(dir_mo)
            elif st.startswith('q') or st.startswith('e'):
                print("exit:%s" % (st))
                sys.exit(0)
            else:
                print("input error:%s" % (st))
                cct.sleep(2)

        except (IOError, EOFError) as e:
            print("SingleError", e)
            cct.sleeprandom(30)
        except Exception as e:
            log.error("Error Exception:%s" % (e))
            import traceback
            traceback.print_exc()
            except_count += 1
            if except_count < 3:
                cct.sleeprandom(ct.duration_sleep_time / 2)
            else:
                print("except_count >3")
                cct.sleeprandom(ct.duration_sleep_time * 2)

