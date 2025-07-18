# -*- coding:utf-8 -*-
# 缠论K线图展示完整版
import logging
import sys
stdout = sys.stdout
sys.path.append("..")
import JSONData.tdx_data_Day as tdd
import JSONData.tdx_hdf5_api as h5a
from JohnsonUtil import commonTips as cct
import JohnsonUtil.johnson_cons as ct
from JohnsonUtil import zoompan
from JSONData import stockFilter as stf
import my_chan2 as chan
import matplotlib as mat
import numpy as np
import datetime
import pandas as pd
# import matplotlib.pyplot as plt

from pylab import plt, mpl
if cct.isMac():
    mpl.rcParams['font.sans-serif'] = ['SimHei']
    # mpl.rcParams['font.sans-serif'] = ['STHeiti']
    mpl.rcParams['axes.unicode_minus'] = False
else:
    mpl.rcParams['font.sans-serif'] = ['SimHei']
    mpl.rcParams['axes.unicode_minus'] = False

# import matplotlib
# matplotlib.use('Qt4Agg')
from JohnsonUtil import LoggerFactory
log = LoggerFactory.log
# log = LoggerFactory.getLogger('chan',show_detail=False)
# log.setLevel(LoggerFactory.DEBUG)
# log.setLevel(LoggerFactory.INFO)
# log.setLevel(LoggerFactory.WARNING)
# log.setLevel(LoggerFactory.ERROR)
# plt.rc('font', family='SimHei', size=13)
# from IPython.core.pylabtools import figsize
# figsize(8, 5)
# bokeh.plotting
import time
from numpy import nan
from bokeh.models import ColumnDataSource, Rect, HoverTool, Range1d, LinearAxis, WheelZoomTool, PanTool, ResetTool
# ================需要修改的参数==============


'''
stock_code = '603058'  # 股票代码
# stock_code = '002176' # 股票代码
start_date = '2017-09-05'
# start_date = None
# end_date = '2017-10-12 15:00:00'  # 最后生成k线日期
end_date = None
stock_days = 60  # 看几天/分钟前的k线
resample = 'd'
# resample = 'w'
x_jizhun = 3  # window 周期 x轴展示的时间距离  5：日，40:30分钟， 48： 5分钟
least_khl_num = get_least_khl_num(resample)
# stock_frequency = '5m' # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟
stock_frequency = resample  # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟 w:week
chanK_flag = False  # True 看缠论K线， False 看k线
# chanK_flag = True  # True 看缠论K线， False 看k线
show_mpl = True
# show_mpl = False
# ============结束==================
'''

'''
以下代码拷贝自https://www.joinquant.com/post/1756
感谢alpha-smart-dog
'''
# dt.datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")-dt.timedelta(days=5)
# quotes = get_price(stock_code, datetime.datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")-datetime.timedelta(days=stock_days) , end_date,\
#                    frequency=stock_frequency,skip_paused=False,fq='pre')



def search_ths_data(code):
    fpath = r'../JohnsonUtil\wencai\同花顺板块行业.xlsx'.replace('\\',cct.get_os_path_sep())
    df = pd.read_excel(fpath)
    # df = df.reset_index().set_index('股票代码')
    df = df.set_index('股票代码')
    # df = df.iloc[:,[1,2,4,5,6,7,8,9]]
    df = df.iloc[:,[4,5,6,7,8]]
    # return (df[df.index == cct.code_to_symbol_ths(code)])
    data = df[df.index == cct.code_to_symbol_ths(code)]
    # table, widths=cct.format_for_print(data, widths=True)
    # table=cct.format_for_print2(data).get_string(header=False)
    table =cct.format_for_print(data,header=False)
    return table

def LIS(X):
    N = len(X)
    P = [0] * N
    M = [0] * (N + 1)
    L = 0
    for i in range(N):
        lo = 1
        hi = L
        while lo <= hi:
            mid = (lo + hi) // 2
            if (X[M[mid]] < X[i]):
                lo = mid + 1
            else:
                hi = mid - 1
        newL = lo
        P[i] = M[newL - 1]
        M[newL] = i
        if (newL > L):
            L = newL
    S = []
    pos = []
    k = M[L]
    for i in range(L - 1, -1, -1):
        S.append(X[k])
        pos.append(k)
        k = P[k]
    return S[::-1], pos[::-1]

from itertools import groupby


def grouby_list(lst, div=None):
    l = []
    if (max(lst) + min(lst)) / 2 > 10:
        if div is None:
            div = (max(lst) - min(lst)) / 2
        for k, g in groupby((lst), key=lambda x: float(x) // div):
            glist = list(g)
            if len(glist) > 0:
                l.append(glist)
            # print(Dk,'{}-{}: {} : {}'.format(k*div, (k+1)*div-1, len(list(g)),list(g))),
        # print ''
    else:
        for k, g in groupby((lst), key=lambda x: round(x)):
            glist = list(g)
            if len(glist) > 0:
                l.append(glist)
            # print("Rk:%s len:%s g:%s "%(k, len(glist),glist)),
        # print ''
    return l
# global dm
# dm = []
# no show mpl

# code='300706'
# # dfm = spp.all_10
# # df_freq = cct.get_limit_multiIndex_freq(dfm)
# log = LoggerFactory.log
# log.setLevel(LoggerFactory.DEBUG)
# h5_fname = 'sina_MultiIndex_data'
# h5_table = 'all_10'
# h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
# # h5[:1]
# df_freq = cct.get_limit_multiIndex_freq(h5, col='all', end=None,code=code)
# # df_freq['volume'] = df_freq['volume'] - df_freq['volume'].shift(1)
# print df_freq[-10:],df_freq.shape
# sys.exit(0)

def get_least_khl_num(resample, idx=0, init_num=3):
    # init = 3
    if init_num - idx > 0:
        initw = init_num - idx
    else:
        initw = 0
    return init_num if resample == 'd' else initw if resample == 'w' else init_num - idx - 1 if init_num - idx - 1 > 0 else 0\
            if resample == 'm' else 5
def get_resample_ciji(stock_frequency):
    # init = 3
    # cur_ji= 1 if resample == '1m' else \
    #     2 if stock_frequency == '5m' else \
    #     3 if stock_frequency == '10m' else \
    #     4 if stock_frequency == '15m' else \
    #     5 if stock_frequency == '30m' else \
    #     6 if stock_frequency == '60m' else \
    #     7 if stock_frequency == 'd' else \
    #     8 if stock_frequency == 'w' else \
    #     9 if stock_frequency == 'm' else 0

    cur_ji= 1 if stock_frequency == '1T' else \
        '1T' if stock_frequency == '5T' else \
        '5T' if stock_frequency == '15T' else \
        '15T' if stock_frequency == '30T' else \
        '30T' if stock_frequency == '60T' else \
        'd' if stock_frequency == 'd' else \
        'd' if stock_frequency == 'w' else \
        'w' if stock_frequency == 'm' else 1
    return cur_ji

def show_chan_mpl_tdx(code, start_date=None, end_date=None, stock_days=60, resample='d', show_mpl=True, least_init=2, chanK_flag=False, windows=20, power=True, fb_show=0,df=None):

    stock_code = code  # 股票代码
    stock_frequency = '%sm'%resample if resample.isdigit() else resample
    resample = '%sT'%resample if resample.isdigit() else resample
    # log.info('resample:%s'%(resample))

    x_jizhun = 3  # window 周期 x轴展示的时间距离  5：日，40:30分钟， 48： 5分钟
    least_khl_num = get_least_khl_num(resample, init_num=least_init)
    # stock_frequency = resample  # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟 w:week
    # chanK_flag = chanK  # True 看缠论K线， False 看k线
    show_mpl = show_mpl
    start_dt=''
    def con2Cxianduan(stock, k_data, chanK, frsBiType, biIdx, end_date, cur_ji=1, recursion=False, dl=None, chanK_flag=False, least_init=3,resample='d'):
        max_k_num = 4
        if cur_ji >= 6 or len(biIdx) == 0 or recursion:
            return biIdx
        idx = biIdx[len(biIdx) - 1]
        k_data_dts = list(k_data.index)
        st_data = chanK['enddate'][idx]
        if st_data not in k_data_dts:
            return biIdx
        # 重构次级别线段的点到本级别的chanK中

        def refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji):
            new_biIdx = []
            biIdxB = biIdx[len(biIdx) - 1] if len(biIdx) > 0 else 0
            for xdIdxcn in xdIdxc:
                for chanKidx in range(len(chanK.index))[biIdxB:]:
                    if judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
                        new_biIdx.append(chanKidx)
                        break
            return new_biIdx
        # 判断次级别日期是否被包含

        def judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
            _end_date = chanK['enddate'][chanKidx] + datetime.timedelta(hours=15) if cur_ji == 1 else chanK['enddate'][chanKidx]
            _start_date = chanK.index[chanKidx] if chanKidx == 0\
                else chanK['enddate'][chanKidx - 1] + datetime.timedelta(minutes=1)
            return _start_date <= chanKc.index[xdIdxcn] <= _end_date
        # cur_ji = 1 #当前级别
        # 符合k线根数大于4根 1日级别， 2 30分钟， 3 5分钟， 4 一分钟
        least_khl_num = get_least_khl_num(get_resample_ciji(resample), 1, init_num=least_init)
        print('ths:')
        print((search_ths_data(code)))
        log.info ("次级:%s %s st_data:%s k_data_dts:%s least_khl_num:%s" % (resample,len(k_data_dts) - k_data_dts.index(st_data), str(st_data)[:10], len(k_data_dts), least_khl_num))
        start_dt =str(st_data)[:10]
        if not recursion:
            # resample = 'd' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else \
            #     'd' if cur_ji + 1 == 5 else 'w' if cur_ji + 1 == 6 else 'd'
            resample = get_resample_ciji(resample)


        if resample != 1 and cur_ji + 1 != 2 and len(k_data_dts) - k_data_dts.index(st_data) >= least_khl_num + 1:
            frequency = '30m' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else '1m'
            # else:
                # frequency = 'd' if cur_ji+1==2 else '5m' if cur_ji+1==3 else \
                #                 'd' if cur_ji+1==5 else 'w' if cur_ji+1==6 else 'd'

            start_lastday = str(chanK.index[biIdx[-1]])[0:10]
            print(("次级别为:%s cur_ji:%s %s" % (resample, cur_ji, start_lastday)))
            # print [chanK.index[x] for x in biIdx]
            k_data_c, cname = get_quotes_tdx(stock, start=start_lastday, end=end_date, dl=dl, resample=resample)
            # print k_data_c.index[0],k_data_c.index[-1]
            chanKc = chan.parse2ChanK(k_data_c, k_data_c.values) if chanK_flag else k_data_c
            fenTypesc, fenIdxc = chan.parse2ChanFen(chanKc, recursion=True)
            if len(fenTypesc) == 0:
                return biIdx
            biIdxc, frsBiTypec = chan.parse2ChanBi(fenTypesc, fenIdxc, chanKc, least_khl_num=least_khl_num - 1)
            if len(biIdxc) == 0:
                return biIdx
            # print "biIdxc:", [round(k_data_c.high[x], 2) for x in biIdxc], [str(k_data_c.index[x])[:10] for x in biIdxc]
            xdIdxc, xdTypec = chan.parse2Xianduan(biIdxc, chanKc, least_windows=1 if least_khl_num > 0 else 0)
            biIdxc = con2Cxianduan(stock, k_data_c, chanKc, frsBiTypec, biIdxc, end_date, cur_ji + 1, recursion=True,resample=resample)
            # print "xdIdxc:%s xdTypec:%s biIdxc:%s" % (xdIdxc, xdTypec, biIdxc)
            if len(xdIdxc) == 0:
                return biIdx
            # 连接线段位为上级别的bi
            lastBiType = frsBiType if len(biIdx) % 2 == 0 else -frsBiType
            if len(biIdx) == 0:
                return refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            lastbi = biIdx.pop()
            firstbic = xdIdxc.pop(0)
            # 同向连接
            if lastBiType == xdTypec:
                biIdx = biIdx + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # 逆向连接
            else:
                #             print '开始逆向连接'
                _mid = [lastbi] if (lastBiType == -1 and chanK['low'][lastbi] <= chanKc['low'][firstbic])\
                    or (lastBiType == 1 and chanK['high'][lastbi] >= chanKc['high'][firstbic]) else\
                    [chanKidx for chanKidx in range(len(chanK.index))[biIdx[len(biIdx) - 1]:]
                     if judge_day_bao(chanK, chanKidx, chanKc, firstbic, cur_ji)]
                biIdx = biIdx + [_mid[0]] + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # print "次级:",len(biIdx),biIdx,[str(k_data_c.index[x])[:10] for x in biIdx]
        return biIdx

    def get_quotes_tdx2(code, start=None, end=None, dl=120, resample='d', show_name=True,df=None):

        if df is None:

            if resample in ct.Resample_LABELS:
                quotes = tdd.get_tdx_append_now_df_api(code=code, start=start, end=end, dl=dl).sort_index(ascending=True)
            else:
                h5_fname = 'sina_MultiIndex_data'
                h5_table = 'all_10'
                time_s = time.time()
                h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
                quotes = cct.get_limit_multiIndex_freq(h5, freq=resample.upper(), col='all', start=start, end=end, code=code)
                quotes = quotes.reset_index().set_index('ticktime')
                # period_stock_data['close'] = stock_data['close'].resample(period_type, how='last')
                if 'volume' in quotes.columns:
                    quotes.rename(columns={'volume': 'vol'}, inplace=True)
                    quotes['amount'] = (list(map(lambda x, y: round((x * y), 1), quotes.close.values, quotes.vol.values)))            
        else:
            quotes = df
            if 'volume' in quotes.columns:
                quotes.rename(columns={'volume': 'vol'}, inplace=True)
                # quotes['amount'] = (map(lambda x, y: round((x * y), 1), quotes.close.values, quotes.vol.values))            
                
        if not resample == 'd' and resample in tdd.resample_dtype:
            quotes = tdd.get_tdx_stock_period_to_type(quotes, period_day=resample)
        if str(quotes.index.dtype) != 'datetime64[ns]':
            quotes.index = quotes.index.astype('datetime64')        

        if show_name:
            if 'name' in quotes.columns:
                cname = quotes.name[0]
                # cname_g =cname
            else:
                # dm = tdd.get_sina_data_df(code)
                cname = tdd.get_sina_data_code(code)
                # if 'name' in dm.columns:
                #     cname = dm.name[0]
                # else:
                #     cname = '-'
        else:
            cname = '-'
        if quotes is not None and len(quotes) > 0:
            quotes = quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount']]
        else:
            # log.error("quotes is None check:%s"%(code))
            raise Exception("Code:%s error, df is None%s" % (code))
        return quotes, cname

    time_s = time.time()
    quotes, cname = get_quotes_tdx2(stock_code, start_date, end_date, dl=stock_days, resample=resample, show_name=show_mpl,df=df)
    # 缠论k线
    #         open  close   high    low    volume      money
    # 2017-05-03  15.69  15.66  15.73  15.53  10557743  165075887
    quotes = chan.parse2ChanK(quotes, quotes.values) if chanK_flag else quotes
    quotes[quotes['vol'] == 0] = np.nan
    quotes = quotes.dropna()
    Close = quotes['close']
    Open = quotes['open']
    High = quotes['high']
    Low = quotes['low']
    T0 = quotes.index.values
    # T0 =  mdates.date2num(T0)
    length = len(Close)

    initial_trend = "down"
    cur_ji = 1 if stock_frequency == 'd' else \
        2 if stock_frequency == '30m' else \
        3 if stock_frequency == '5m' else \
        4 if stock_frequency == 'w' else \
        5 if stock_frequency == 'm' else 6

    log.debug('======笔形成最后一段未完成段判断是否是次级别的走势形成笔=======:%s %s' % (stock_frequency, cur_ji))

    x_date_list = quotes.index.values.tolist()
    k_data = quotes
    k_values = k_data.values
    # 缠论k线
    chanK = quotes if chanK_flag else chan.parse2ChanK(k_data, k_values, chan_kdf=chanK_flag)

    fenTypes, fenIdx = chan.parse2ChanFen(chanK)
    # log.debug("code:%s fenTypes:%s fenIdx:%s k_data:%s" % (stock_code,fenTypes, fenIdx, len(k_data)))
    biIdx, frsBiType = chan.parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
    # log.debug("biIdx1:%s chanK:%s" % (biIdx, len(chanK)))
    if len(biIdx) > 0:
        log.debug("biIdx1:%s %s chanK:%s" % (biIdx, str(chanK.index.values[biIdx[-1]])[:10], len(chanK)))
    
    biIdx = con2Cxianduan(stock_code, k_data, chanK, frsBiType, biIdx, end_date, cur_ji, least_init=least_init,resample=resample)
    # log.debug("biIdx2:%s chanK:%s" % (biIdx, len(biIdx)))
    
    chanKIdx = [(chanK.index[x]) for x in biIdx]

    if len(biIdx) == 0 and len(chanKIdx) == 0:
        log.error("BiIdx is None and chanKidx is None:%s" % (code))
        return None

    log.debug("con2Cxianduan:%s chanK:%s %s" % (biIdx, len(chanK), chanKIdx[-1] if len(chanKIdx) > 0 else None))
    # print '股票代码', get_security_info(stock_code).display_name
    # print '股票代码', (stock_code), resample, least_khl_num
    #  3.得到分笔结果，计算坐标显示

    def plot_fenbi_seq(biIdx, frsBiType, plt=None, color=None, fb_show=0):
        x_fenbi_seq = []
        y_fenbi_seq = []
        for i in range(len(biIdx)):
            if biIdx[i] is not None:
                fenType = -frsBiType if i % 2 == 0 else frsBiType
        #         dt = chanK['enddate'][biIdx[i]]
                # 缠论k线
                dt = chanK.index[biIdx[i]] if chanK_flag else chanK['enddate'][biIdx[i]]
                # print i,k_data['high'][dt], k_data['low'][dt]
                time_long = int(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
                # print x_date_list.index(time_long) if time_long in x_date_list else 0
                if fenType == 1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha='left', fontsize=12)
                        elif fb_show:
                            col_v = color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha='left', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['high'][dt])
                if fenType == -1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va='bottom', fontsize=12)
                        elif fb_show:
                            col_v = color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va='bottom', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['low'][dt])
    #             bottom_time = None
    #             for k_line_dto in m_line_dto.member_list[::-1]:
    #                 if k_line_dto.low == m_line_dto.low:
    #                     # get_price返回的日期，默认时间是08:00:00
    #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
    #                     break
    #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
    #             y_fenbi_seq.append(m_line_dto.low)
        return x_fenbi_seq, y_fenbi_seq

    # print  T0[-len(T0):].astype(dt.date)
    T1 = T0[-len(T0):].astype(datetime.date) / 1000000000
    Ti = []
    if len(T0) / x_jizhun > 12:
        x_jizhun = len(T0) / 12
    for i in range(len(T0) / x_jizhun):
        # print "len(T0)/x_jizhun:",len(T0)/x_jizhun

        a = int(i * x_jizhun)
        d = datetime.date.fromtimestamp(T1[a])
        # print d
        T2 = d.strftime('$%Y-%m-%d$')
        Ti.append(T2)
        # print tab
    d1 = datetime.date.fromtimestamp(T1[len(T0) - 1])
    d2 = (d1 + datetime.timedelta(days=1)).strftime('$%Y-%m-%d$')
    Ti.append(d2)

    ll = Low.min() * 0.97
    hh = High.max() * 1.03

    # ht = HoverTool(tooltips=[
    #             ("date", "@date"),
    #             ("open", "@open"),
    #             ("close", "@close"),
    #             ("high", "@high"),
    #             ("low", "@low"),
    #             ("volume", "@volume"),
    #             ("money", "@money"),])
    # TOOLS = [ht, WheelZoomTool(dimensions=['width']),\
    #          ResizeTool(), ResetTool(),\
    #          PanTool(dimensions=['width']), PreviewSaveTool()]
    if show_mpl:
        # fig = plt.figure(figsize=(10, 6))
        fig = plt.figure(figsize=(12, 8))
        ax1 = plt.subplot2grid((10, 1), (0, 0), rowspan=8, colspan=1)
        # ax1 = fig.add_subplot(2,1,1)
        # fig = plt.figure()
        # ax1 = plt.axes([0,0,3,2])

        X = np.array(list(range(0, length)))
        pad_nan = X + nan

        # 计算上 下影线
        max_clop = Close.copy()
        max_clop[Close < Open] = Open[Close < Open]
        min_clop = Close.copy()
        min_clop[Close > Open] = Open[Close > Open]

        # 上影线
        line_up = np.array([High, max_clop, pad_nan])
        line_up = np.ravel(line_up, 'F')
        # 下影线
        line_down = np.array([Low, min_clop, pad_nan])
        line_down = np.ravel(line_down, 'F')

        # 计算上下影线对应的X坐标
        pad_nan = nan + X
        pad_X = np.array([X, X, X])
        pad_X = np.ravel(pad_X, 'F')

        # 画出实体部分,先画收盘价在上的部分
        up_cl = Close.copy()
        up_cl[Close <= Open] = nan
        up_op = Open.copy()
        up_op[Close <= Open] = nan

        down_cl = Close.copy()
        down_cl[Open <= Close] = nan
        down_op = Open.copy()
        down_op[Open <= Close] = nan

        even = Close.copy()
        even[Close != Open] = nan

        # 画出收红的实体部分
        pad_box_up = np.array([up_op, up_op, up_cl, up_cl, pad_nan])
        pad_box_up = np.ravel(pad_box_up, 'F')
        pad_box_down = np.array([down_cl, down_cl, down_op, down_op, pad_nan])
        pad_box_down = np.ravel(pad_box_down, 'F')
        pad_box_even = np.array([even, even, even, even, pad_nan])
        pad_box_even = np.ravel(pad_box_even, 'F')

        # X的nan可以不用与y一一对应
        X_left = X - 0.25
        X_right = X + 0.25
        box_X = np.array([X_left, X_right, X_right, X_left, pad_nan])
        # print box_X
        box_X = np.ravel(box_X, 'F')
        # print box_X
        # Close_handle=plt.plot(pad_X,line_up,color='k')

        vertices_up = np.array([box_X, pad_box_up]).T
        vertices_down = np.array([box_X, pad_box_down]).T
        vertices_even = np.array([box_X, pad_box_even]).T

        vertices_ma = np.array([box_X, pad_box_up]).T

        handle_box_up = mat.patches.Polygon(vertices_up, color='r', zorder=1)
        handle_box_down = mat.patches.Polygon(vertices_down, color='g', zorder=1)
        handle_box_even = mat.patches.Polygon(vertices_even, color='k', zorder=1)

        ax1.add_patch(handle_box_up)
        ax1.add_patch(handle_box_down)
        ax1.add_patch(handle_box_even)

        handle_line_up = mat.lines.Line2D(pad_X, line_up, color='k', linestyle='solid', zorder=0)
        handle_line_down = mat.lines.Line2D(pad_X, line_down, color='k', linestyle='solid', zorder=0)

        ax1.add_line(handle_line_up)
        ax1.add_line(handle_line_down)

        v = [0, length, Open.min() - 0.5, Open.max() + 0.5]
        plt.axis(v)

        ax1.set_xticks(np.linspace(-2, len(Close) + 2, len(Ti)))

        ax1.set_ylim(ll, hh)

        ax1.set_xticklabels(Ti)

        plt.grid(True)
        plt.setp(plt.gca().get_xticklabels(), rotation=30, horizontalalignment='right')

    '''
    以上代码拷贝自https://www.joinquant.com/post/1756
    感谢alpha-smart-dog

    K线图绘制完毕
    '''

    # print "biIdx:%s chankIdx:%s"%(biIdx,str(chanKIdx[-1])[:10])
    if show_mpl:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt)
        # plot_fenbi_seq(fenIdx,fenTypes[0], plt,color=['red','green'])
        plot_fenbi_seq(fenIdx, frsBiType, plt, color=['red', 'green'], fb_show=fb_show)
    else:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt=None)
        plot_fenbi_seq(fenIdx, frsBiType, plt=None, color=['red', 'green'], fb_show=fb_show)
    #  在原图基础上添加分笔蓝线
    inx_value = chanK.high.values
    inx_va = [round(inx_value[x], 2) for x in biIdx]
    log.debug("inx_va:%s count:%s" % (inx_va, len(quotes.high)))
    log.debug("yfenbi:%s count:%s" % ([round(y, 2) for y in y_fenbi_seq], len(chanK)))
    j_BiType = [-frsBiType if i % 2 == 0 else frsBiType for i in range(len(biIdx))]
    BiType_s = j_BiType[-1] if len(j_BiType) > 0 else -2
    # bi_price = [str(chanK.low[idx]) if i % 2 == 0 else str(chanK.high[idx])  for i,idx in enumerate(biIdx)]
    # print ("笔     :%s %s"%(biIdx,bi_price))
    # fen_dt = [str(chanK.index[fenIdx[i]])[:10] if chanK_flag else str(chanK['enddate'][fenIdx[i]])[:10]for i in range(len(fenIdx))]
    fen_dt = [(chanK.index[fenIdx[i]]) if chanK_flag else (chanK['enddate'][fenIdx[i]]) for i in range(len(fenIdx))]
    if len(fenTypes) > 0:
        if fenTypes[0] == -1:
            # fen_price = [str(k_data.low[idx]) if i % 2 == 0 else str(k_data.high[idx])  for i,idx in enumerate(fen_dt)]
            low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        else:
            # fen_price = [str(k_data.high[idx]) if i % 2 == 0 else str(k_data.low[idx])  for i,idx in enumerate(fen_dt)]
            high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        # fen_duration =[fenIdx[i] - fenIdx[i -1 ] if i >0 else 0 for i,idx in enumerate(fenIdx)]
    else:
        # fen_price = fenTypes
        # fen_duration = fenTypes
        low_fen = []
        high_fen = []
    # fen_dt = [str(k_data.index[idx])[:10] for i,idx in enumerate(fenIdx)]
    # print low_fen,high_fen

    def dataframe_mode_round(df):
        roundlist = [1, 0]
        df_mode = []
        for i in roundlist:
            df_mode = df.apply(lambda x: round(x, i)).mode()
            if len(df_mode) > 0:
                break
        return df_mode

    kdl = k_data.loc[low_fen].low
    kdl_mode = dataframe_mode_round(kdl)
    kdh = k_data.loc[high_fen].high
    kdh_mode = dataframe_mode_round(kdh)

    # print ("kdl:%s"%(kdl.values))
    # print ("kdh:%s"%(kdh.values))
    # log.debug("kdl_mode:%s kdh_mode%s chanKidx:%s" % (kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10]))
    log.info("time:%0.2f kdl_mode:%s kdh_mode%s chanKidx:%s" % (time.time()-time_s ,kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10]))
    print((kdl_mode.values,np.median(kdl_mode.values), kdh_mode.values,np.median(kdh_modekdh_mode.values), str(chanKIdx[-1])[:10],start_dt))
    # lkdl, lkdlidx = LIS(kdl)
    # lkdh, lkdhidx = LIS(kdh)
    # log.debug("Lkdl:%s Lkdh:%s" % (len(kdl) - len(lkdl), len(kdh) - len(lkdh)))
    # # print ("Gkdl:%s Gkdh:%s"%(grouby_list(kdl.values),grouby_list(kdh.values)))
    # # import ipdb;ipdb.set_trace()
    # # if power:
    #     # return BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10], len(keydf)
    
    # lastdf = k_data[k_data.index >= chanKIdx[-1]]
    
    # if BiType_s == -1:
    #     keydf = lastdf[((lastdf.close >= kdl_mode.max()) & (lastdf.low >= kdl_mode.max()))]
    # elif BiType_s == 1:
    #     keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min()))]
    # else:
    #     keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min())) |
    #                     ((lastdf.close <= kdl_mode.min()) & (lastdf.low <= kdl_mode.min()))]
    # log.debug("BiType_s:%s keydf:%s key:%s" % (BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10], len(keydf)))


    # log.debug("Fentype:%s " % (fenTypes))
    # log.debug("fenIdx:%s " % (fenIdx))
    # # print ("fen_duration:%s "%(fen_duration))
    # # print ("fen_price:%s "%(fen_price))
    # # print ("fendt:%s "%(fen_dt))

    # log.debug("BiType :%s frsBiType:%s" % (j_BiType, frsBiType))

    # if len(j_BiType) > 0:
    #     if j_BiType[0] == -1:
    #         tb_price = [str(quotes.low[idx]) if i % 2 == 0 else str(quotes.high[idx]) for i, idx in enumerate(x_fenbi_seq)]
    #     else:
    #         tb_price = [str(quotes.high[idx]) if i % 2 == 0 else str(quotes.low[idx]) for i, idx in enumerate(x_fenbi_seq)]
    #     tb_duration = [x_fenbi_seq[i] - x_fenbi_seq[i - 1] if i > 0 else 0 for i, idx in enumerate(x_fenbi_seq)]

    # else:
    #     tb_price = j_BiType
    #     tb_duration = j_BiType
    # log.debug("图笔 :%s" % x_fenbi_seq, tb_price)
    # log.debug("图笔dura :%s" % tb_duration)

    # # 线段画到笔上
    # xdIdxs, xfenTypes = chan.parse2ChanXD(frsBiType, biIdx, chanK)
    # log.debug('线段%s ,fenT:%s' % (xdIdxs, xfenTypes))
    # x_xd_seq = []
    # y_xd_seq = []
    # for i in range(len(xdIdxs)):
    #     if xdIdxs[i] is not None:
    #         fenType = xfenTypes[i]
    # #         dt = chanK['enddate'][biIdx[i]]
    #         # 缠论k线
    #         dt = chanK.index[xdIdxs[i]] if chanK_flag else chanK['enddate'][xdIdxs[i]]
    # #         print k_data['high'][dt], k_data['low'][dt]
    #         time_long = long(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
    # #         print x_date_list.index(time_long) if time_long in x_date_list else 0
    #         if fenType == 1:
    #             x_xd_seq.append(x_date_list.index(time_long))
    #             y_xd_seq.append(k_data['high'][dt])
    #         if fenType == -1:
    #             x_xd_seq.append(x_date_list.index(time_long))
    #             y_xd_seq.append(k_data['low'][dt])
    # #  在原图基础上添加分笔蓝线
    # log.debug("线段   :%s" % (x_xd_seq[:-2]))
    # log.debug("笔值  :%s" % ([str(x) for x in (y_xd_seq)][:-2]))
    # # Y_hat = X * b + a
def get_quotes_tdx(code, start=None, end=None, dl=120, resample='d', show_name=True,df=None):

    if df is None:
        if resample in ct.Resample_LABELS:
            quotes = tdd.get_tdx_append_now_df_api(code=code, start=start, end=end, dl=dl).sort_index(ascending=True)
        else:
            h5_fname = 'sina_MultiIndex_data'
            h5_table = 'all_10'
            time_s = time.time()
            h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
            quotes = cct.get_limit_multiIndex_freq(h5, freq=resample.upper(), col='all', start=start, end=end, code=code)
            quotes = quotes.reset_index().set_index('ticktime')
            # period_stock_data['close'] = stock_data['close'].resample(period_type, how='last')
            if 'volume' in quotes.columns:
                quotes.rename(columns={'volume': 'vol'}, inplace=True)
                quotes['amount'] = (list(map(lambda x, y: round((x * y), 1), quotes.close.values, quotes.vol.values)))            
    else:
        quotes = df
        if 'volume' in quotes.columns:
            quotes.rename(columns={'volume': 'vol'}, inplace=True)
            # quotes['amount'] = (map(lambda x, y: round((x * y), 1), quotes.close.values, quotes.vol.values))            
            
    if not resample == 'd' and resample in tdd.resample_dtype:
        quotes = tdd.get_tdx_stock_period_to_type(quotes, period_day=resample)
    if str(quotes.index.dtype) != 'datetime64[ns]':
        quotes.index = quotes.index.astype('datetime64[ns]')        

    if show_name:
        if 'name' in quotes.columns:
            cname = quotes.name[0]
            # cname_g =cname
        else:
            cname = tdd.get_sina_data_code(code)
            # if 'name' in dm.columns:
            #     cname = dm.name[0]
            # else:
            #     cname = '-'
    else:
        cname = '-'
    if quotes is not None and len(quotes) > 0:
        quotes = quotes.loc[:, ['open', 'close', 'high', 'low', 'vol','amount']]
        # quotes = quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', ,'ma20d','upper','lower']]
    else:
        # log.error("quotes is None check:%s"%(code))
        raise Exception("Code:%s error, df is None%s" % (code))
    return quotes, cname

def show_chan_mpl_power(code, start_date=None, end_date=None, stock_days=60, resample='d', show_mpl=True, least_init=2, chanK_flag=False, windows=20, power=True, fb_show=0,df=None,roll_mean_days=20):

    stock_code = code  # 股票代码
    stock_frequency = '%sm'%resample if resample.isdigit() else resample
    resample = '%sT'%resample if resample.isdigit() else resample
    # log.info('resample:%s'%(resample))

    x_jizhun = 3  # window 周期 x轴展示的时间距离  5：日，40:30分钟， 48： 5分钟
    least_khl_num = get_least_khl_num(resample, init_num=least_init)
    # stock_frequency = resample  # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟 w:week
    # chanK_flag = chanK  # True 看缠论K线， False 看k线
    show_mpl = show_mpl

    def con2Cxianduan(stock, k_data, chanK, frsBiType, biIdx, end_date, cur_ji=1, recursion=False, dl=None, chanK_flag=False, least_init=3,resample='d'):
        max_k_num = 4
        if cur_ji >= 6 or len(biIdx) == 0 or recursion:
            return biIdx
        idx = biIdx[len(biIdx) - 1]
        k_data_dts = list(k_data.index)
        st_data = chanK['enddate'][idx]
        if st_data not in k_data_dts:
            return biIdx
        # 重构次级别线段的点到本级别的chanK中

        def refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji):
            new_biIdx = []
            biIdxB = biIdx[len(biIdx) - 1] if len(biIdx) > 0 else 0
            for xdIdxcn in xdIdxc:
                for chanKidx in range(len(chanK.index))[biIdxB:]:
                    if judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
                        new_biIdx.append(chanKidx)
                        break
            return new_biIdx
        # 判断次级别日期是否被包含

        def judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
            _end_date = chanK['enddate'][chanKidx] + datetime.timedelta(hours=15) if cur_ji == 1 else chanK['enddate'][chanKidx]
            _start_date = chanK.index[chanKidx] if chanKidx == 0\
                else chanK['enddate'][chanKidx - 1] + datetime.timedelta(minutes=1)
            return _start_date <= chanKc.index[xdIdxcn] <= _end_date
        # cur_ji = 1 #当前级别
        # 符合k线根数大于4根 1日级别， 2 30分钟， 3 5分钟， 4 一分钟
        least_khl_num = get_least_khl_num(get_resample_ciji(resample), 1, init_num=least_init)

        print('ths:')
        print((search_ths_data(code)))
        print(("次级:%s %s st_data:%s k_data_dts:%s least_khl_num:%s" % (resample,len(k_data_dts) - k_data_dts.index(st_data), str(st_data)[:10], len(k_data_dts), least_khl_num)))
        
        if not recursion:
            # resample = 'd' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else \
            #     'd' if cur_ji + 1 == 5 else 'w' if cur_ji + 1 == 6 else 'd'
            resample = get_resample_ciji(resample)


        if resample != 1 and cur_ji + 1 != 2 and len(k_data_dts) - k_data_dts.index(st_data) >= least_khl_num + 1:
            frequency = '30m' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else '1m'
            # else:
                # frequency = 'd' if cur_ji+1==2 else '5m' if cur_ji+1==3 else \
                #                 'd' if cur_ji+1==5 else 'w' if cur_ji+1==6 else 'd'

            start_lastday = str(chanK.index[biIdx[-1]])[0:10]
            print(("次级别为:%s cur_ji:%s %s" % (resample, cur_ji, start_lastday)))
            # print [chanK.index[x] for x in biIdx]
            k_data_c, cname = get_quotes_tdx(stock, start=start_lastday, end=end_date, dl=dl, resample=resample)
            # print k_data_c.index[0],k_data_c.index[-1]
            chanKc = chan.parse2ChanK(k_data_c, k_data_c.values) if chanK_flag else k_data_c
            fenTypesc, fenIdxc = chan.parse2ChanFen(chanKc, recursion=True)
            if len(fenTypesc) == 0:
                return biIdx
            biIdxc, frsBiTypec = chan.parse2ChanBi(fenTypesc, fenIdxc, chanKc, least_khl_num=least_khl_num - 1)
            if len(biIdxc) == 0:
                return biIdx
            # print "biIdxc:", [round(k_data_c.high[x], 2) for x in biIdxc], [str(k_data_c.index[x])[:10] for x in biIdxc]
            xdIdxc, xdTypec = chan.parse2Xianduan(biIdxc, chanKc, least_windows=1 if least_khl_num > 0 else 0)
            biIdxc = con2Cxianduan(stock, k_data_c, chanKc, frsBiTypec, biIdxc, end_date, cur_ji + 1, recursion=True,resample=resample)
            # print "xdIdxc:%s xdTypec:%s biIdxc:%s" % (xdIdxc, xdTypec, biIdxc)
            if len(xdIdxc) == 0:
                return biIdx
            # 连接线段位为上级别的bi
            lastBiType = frsBiType if len(biIdx) % 2 == 0 else -frsBiType
            if len(biIdx) == 0:
                return refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            lastbi = biIdx.pop()
            firstbic = xdIdxc.pop(0)
            # 同向连接
            if lastBiType == xdTypec:
                biIdx = biIdx + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # 逆向连接
            else:
                #             print '开始逆向连接'
                _mid = [lastbi] if (lastBiType == -1 and chanK['low'][lastbi] <= chanKc['low'][firstbic])\
                    or (lastBiType == 1 and chanK['high'][lastbi] >= chanKc['high'][firstbic]) else\
                    [chanKidx for chanKidx in range(len(chanK.index))[biIdx[len(biIdx) - 1]:]
                     if judge_day_bao(chanK, chanKidx, chanKc, firstbic, cur_ji)]
                biIdx = biIdx + [_mid[0]] + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # print "次级:",len(biIdx),biIdx,[str(k_data_c.index[x])[:10] for x in biIdx]
        return biIdx


    time_s = time.time()
    quotes, cname = get_quotes_tdx(stock_code, start_date, end_date, dl=stock_days, resample=resample, show_name=show_mpl,df=df)
    # 缠论k线
    #         open  close   high    low    volume      money
    # 2017-05-03  15.69  15.66  15.73  15.53  10557743  165075887
    quotes = chan.parse2ChanK(quotes, quotes.values) if chanK_flag else quotes
    quotes[quotes['vol'] == 0] = np.nan
    quotes = quotes.dropna()
    Close = quotes['close']
    Open = quotes['open']
    High = quotes['high']
    Low = quotes['low']
    T0 = quotes.index.values
    # T0 =  mdates.date2num(T0)
    length = len(Close)

    initial_trend = "down"
    cur_ji = 1 if stock_frequency == 'd' else \
        2 if stock_frequency == '30m' else \
        3 if stock_frequency == '5m' else \
        4 if stock_frequency == 'w' else \
        5 if stock_frequency == 'm' else 6

    log.debug('======笔形成最后一段未完成段判断是否是次级别的走势形成笔=======:%s %s' % (stock_frequency, cur_ji))

    x_date_list = quotes.index.values.tolist()
    k_data = quotes
    k_values = k_data.values
    # 缠论k线
    chanK = quotes if chanK_flag else chan.parse2ChanK(k_data, k_values, chan_kdf=chanK_flag)

    fenTypes, fenIdx = chan.parse2ChanFen(chanK)
    # log.debug("code:%s fenTypes:%s fenIdx:%s k_data:%s" % (stock_code,fenTypes, fenIdx, len(k_data)))
    biIdx, frsBiType = chan.parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
    # log.debug("biIdx1:%s chanK:%s" % (biIdx, len(chanK)))
    if len(biIdx) > 0:
        log.debug("biIdx1:%s %s chanK:%s" % (biIdx, str(chanK.index.values[biIdx[-1]])[:10], len(chanK)))
    
    biIdx = con2Cxianduan(stock_code, k_data, chanK, frsBiType, biIdx, end_date, cur_ji, least_init=least_init,resample=resample)
    # log.debug("biIdx2:%s chanK:%s" % (biIdx, len(biIdx)))
    
    chanKIdx = [(chanK.index[x]) for x in biIdx]

    if len(biIdx) == 0 and len(chanKIdx) == 0:
        log.error("BiIdx is None and chanKidx is None:%s" % (code))
        return None

    log.debug("con2Cxianduan:%s chanK:%s %s" % (biIdx, len(chanK), chanKIdx[-1] if len(chanKIdx) > 0 else None))
    # print '股票代码', get_security_info(stock_code).display_name
    # print '股票代码', (stock_code), resample, least_khl_num
    #  3.得到分笔结果，计算坐标显示

    def plot_fenbi_seq(biIdx, frsBiType, plt=None, color=None, fb_show=0):
        x_fenbi_seq = []
        y_fenbi_seq = []
        for i in range(len(biIdx)):
            if biIdx[i] is not None:
                fenType = -frsBiType if i % 2 == 0 else frsBiType
        #         dt = chanK['enddate'][biIdx[i]]
                # 缠论k线
                dt = chanK.index[biIdx[i]] if chanK_flag else chanK['enddate'][biIdx[i]]
                # print i,k_data['high'][dt], k_data['low'][dt]
                time_long = int(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
                # print x_date_list.index(time_long) if time_long in x_date_list else 0
                if fenType == 1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha='left', fontsize=12)
                        elif fb_show:
                            col_v = color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha='left', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['high'][dt])
                if fenType == -1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va='bottom', fontsize=12)
                        elif fb_show:
                            col_v = color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va='bottom', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['low'][dt])
    #             bottom_time = None
    #             for k_line_dto in m_line_dto.member_list[::-1]:
    #                 if k_line_dto.low == m_line_dto.low:
    #                     # get_price返回的日期，默认时间是08:00:00
    #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
    #                     break
    #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
    #             y_fenbi_seq.append(m_line_dto.low)
        return x_fenbi_seq, y_fenbi_seq


    # print  T0[-len(T0):].astype(dt.date)
    T1 = T0[-len(T0):].astype(datetime.date) / 1000000000
    Ti = []
    if len(T0) / x_jizhun > 12:
        x_jizhun = len(T0) / 12
    for i in range(int(len(T0) / x_jizhun)):
        # print "len(T0)/x_jizhun:",len(T0)/x_jizhun

        a = int(i * x_jizhun)
        d = datetime.date.fromtimestamp(T1[a])
        # print d
        T2 = d.strftime('$%Y-%m-%d$')
        Ti.append(T2)
        # print tab
    d1 = datetime.date.fromtimestamp(T1[len(T0) - 1])
    d2 = (d1 + datetime.timedelta(days=1)).strftime('$%Y-%m-%d$')
    Ti.append(d2)

    ll = Low.min() * 0.97
    hh = High.max() * 1.03

    # ht = HoverTool(tooltips=[
    #             ("date", "@date"),
    #             ("open", "@open"),
    #             ("close", "@close"),
    #             ("high", "@high"),
    #             ("low", "@low"),
    #             ("volume", "@volume"),
    #             ("money", "@money"),])
    # TOOLS = [ht, WheelZoomTool(dimensions=['width']),\
    #          ResizeTool(), ResetTool(),\
    #          PanTool(dimensions=['width']), PreviewSaveTool()]
    if show_mpl:
        # fig = plt.figure(figsize=(10, 6))
        fig = plt.figure(figsize=(12, 8))
        ax1 = plt.subplot2grid((10, 1), (0, 0), rowspan=8, colspan=1)
        # ax1 = fig.add_subplot(2,1,1)
        # fig = plt.figure()
        # ax1 = plt.axes([0,0,3,2])

        X = np.array(list(range(0, length)))
        pad_nan = X + nan

        # 计算上 下影线
        max_clop = Close.copy()
        max_clop[Close < Open] = Open[Close < Open]
        min_clop = Close.copy()
        min_clop[Close > Open] = Open[Close > Open]

        # 上影线
        line_up = np.array([High, max_clop, pad_nan])
        line_up = np.ravel(line_up, 'F')
        # 下影线
        line_down = np.array([Low, min_clop, pad_nan])
        line_down = np.ravel(line_down, 'F')

        # 计算上下影线对应的X坐标
        pad_nan = nan + X
        pad_X = np.array([X, X, X])
        pad_X = np.ravel(pad_X, 'F')

        # 画出实体部分,先画收盘价在上的部分
        up_cl = Close.copy()
        up_cl[Close <= Open] = nan
        up_op = Open.copy()
        up_op[Close <= Open] = nan

        down_cl = Close.copy()
        down_cl[Open <= Close] = nan
        down_op = Open.copy()
        down_op[Open <= Close] = nan

        even = Close.copy()
        even[Close != Open] = nan

        # 画出收红的实体部分
        pad_box_up = np.array([up_op, up_op, up_cl, up_cl, pad_nan])
        pad_box_up = np.ravel(pad_box_up, 'F')
        pad_box_down = np.array([down_cl, down_cl, down_op, down_op, pad_nan])
        pad_box_down = np.ravel(pad_box_down, 'F')
        pad_box_even = np.array([even, even, even, even, pad_nan])
        pad_box_even = np.ravel(pad_box_even, 'F')

        # X的nan可以不用与y一一对应
        X_left = X - 0.25
        X_right = X + 0.25
        box_X = np.array([X_left, X_right, X_right, X_left, pad_nan])
        # print box_X
        box_X = np.ravel(box_X, 'F')
        # print box_X
        # Close_handle=plt.plot(pad_X,line_up,color='k')

        vertices_up = np.array([box_X, pad_box_up]).T
        vertices_down = np.array([box_X, pad_box_down]).T
        vertices_even = np.array([box_X, pad_box_even]).T

        handle_box_up = mat.patches.Polygon(vertices_up, color='r', zorder=1)
        handle_box_down = mat.patches.Polygon(vertices_down, color='g', zorder=1)
        handle_box_even = mat.patches.Polygon(vertices_even, color='k', zorder=1)

        ax1.add_patch(handle_box_up)
        ax1.add_patch(handle_box_down)
        ax1.add_patch(handle_box_even)

        handle_line_up = mat.lines.Line2D(pad_X, line_up, color='k', linestyle='solid', zorder=0)
        handle_line_down = mat.lines.Line2D(pad_X, line_down, color='k', linestyle='solid', zorder=0)

        ax1.add_line(handle_line_up)
        ax1.add_line(handle_line_down)

        v = [0, length, Open.min() - 0.5, Open.max() + 0.5]
        plt.axis(v)

        ax1.set_xticks(np.linspace(-2, len(Close) + 2, len(Ti)))

        ax1.set_ylim(ll, hh)

        ax1.set_xticklabels(Ti)

        plt.grid(True)
        plt.setp(plt.gca().get_xticklabels(), rotation=30, horizontalalignment='right')

    '''
    以上代码拷贝自https://www.joinquant.com/post/1756
    感谢alpha-smart-dog

    K线图绘制完毕
    '''

    # print "biIdx:%s chankIdx:%s"%(biIdx,str(chanKIdx[-1])[:10])
    if show_mpl:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt)
        # plot_fenbi_seq(fenIdx,fenTypes[0], plt,color=['red','green'])
        plot_fenbi_seq(fenIdx, frsBiType, plt, color=['red', 'green'], fb_show=fb_show)
    else:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt=None)
        plot_fenbi_seq(fenIdx, frsBiType, plt=None, color=['red', 'green'], fb_show=fb_show)
    #  在原图基础上添加分笔蓝线
    inx_value = chanK.high.values
    inx_va = [round(inx_value[x], 2) for x in biIdx]
    log.debug("inx_va:%s count:%s" % (inx_va, len(quotes.high)))
    log.debug("yfenbi:%s count:%s" % ([round(y, 2) for y in y_fenbi_seq], len(chanK)))
    j_BiType = [-frsBiType if i % 2 == 0 else frsBiType for i in range(len(biIdx))]
    BiType_s = j_BiType[-1] if len(j_BiType) > 0 else -2
    # bi_price = [str(chanK.low[idx]) if i % 2 == 0 else str(chanK.high[idx])  for i,idx in enumerate(biIdx)]
    # print ("笔     :%s %s"%(biIdx,bi_price))
    # fen_dt = [str(chanK.index[fenIdx[i]])[:10] if chanK_flag else str(chanK['enddate'][fenIdx[i]])[:10]for i in range(len(fenIdx))]
    fen_dt = [(chanK.index[fenIdx[i]]) if chanK_flag else (chanK['enddate'][fenIdx[i]]) for i in range(len(fenIdx))]
    if len(fenTypes) > 0:
        if fenTypes[0] == -1:
            # fen_price = [str(k_data.low[idx]) if i % 2 == 0 else str(k_data.high[idx])  for i,idx in enumerate(fen_dt)]
            low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        else:
            # fen_price = [str(k_data.high[idx]) if i % 2 == 0 else str(k_data.low[idx])  for i,idx in enumerate(fen_dt)]
            high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        # fen_duration =[fenIdx[i] - fenIdx[i -1 ] if i >0 else 0 for i,idx in enumerate(fenIdx)]
    else:
        # fen_price = fenTypes
        # fen_duration = fenTypes
        low_fen = []
        high_fen = []
    # fen_dt = [str(k_data.index[idx])[:10] for i,idx in enumerate(fenIdx)]
    # print low_fen,high_fen

    def dataframe_mode_round(df):
        roundlist = [1, 0]
        df_mode = []
        for i in roundlist:
            df_mode = df.apply(lambda x: round(x, i)).mode()
            if len(df_mode) > 0:
                break
        return df_mode

    kdl = k_data.loc[low_fen].low
    kdl_mode = dataframe_mode_round(kdl)
    kdh = k_data.loc[high_fen].high
    kdh_mode = dataframe_mode_round(kdh)

    # print ("kdl:%s"%(kdl.values))
    # print ("kdh:%s"%(kdh.values))
    # log.debug("kdl_mode:%s kdh_mode%s chanKidx:%s" % (kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10]))
    print(("time:%0.2f kdl_mode:%s kdh_mode%s chanKidx:%s" % (time.time()-time_s ,kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10])))

    lkdl, lkdlidx = LIS(kdl)
    lkdh, lkdhidx = LIS(kdh)
    log.debug("Lkdl:%s Lkdh:%s" % (len(kdl) - len(lkdl), len(kdh) - len(lkdh)))
    # print ("Gkdl:%s Gkdh:%s"%(grouby_list(kdl.values),grouby_list(kdh.values)))
    # import ipdb;ipdb.set_trace()
    # if power:
        # return BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10], len(keydf)
    
    lastdf = k_data[k_data.index >= chanKIdx[-1]]
    
    if BiType_s == -1:
        keydf = lastdf[((lastdf.close >= kdl_mode.max()) & (lastdf.low >= kdl_mode.max()))]
    elif BiType_s == 1:
        keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min()))]
    else:
        keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min())) |
                        ((lastdf.close <= kdl_mode.min()) & (lastdf.low <= kdl_mode.min()))]
    log.debug("BiType_s:%s keydf:%s key:%s" % (BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10], len(keydf)))


    log.debug("Fentype:%s " % (fenTypes))
    log.debug("fenIdx:%s " % (fenIdx))
    # print ("fen_duration:%s "%(fen_duration))
    # print ("fen_price:%s "%(fen_price))
    # print ("fendt:%s "%(fen_dt))

    log.debug("BiType :%s frsBiType:%s" % (j_BiType, frsBiType))

    if len(j_BiType) > 0:
        if j_BiType[0] == -1:
            tb_price = [str(quotes.low[idx]) if i % 2 == 0 else str(quotes.high[idx]) for i, idx in enumerate(x_fenbi_seq)]
        else:
            tb_price = [str(quotes.high[idx]) if i % 2 == 0 else str(quotes.low[idx]) for i, idx in enumerate(x_fenbi_seq)]
        tb_duration = [x_fenbi_seq[i] - x_fenbi_seq[i - 1] if i > 0 else 0 for i, idx in enumerate(x_fenbi_seq)]

    else:
        tb_price = j_BiType
        tb_duration = j_BiType
    log.debug("图笔 :%s" % x_fenbi_seq, tb_price)
    log.debug("图笔dura :%s" % tb_duration)

    # 线段画到笔上
    xdIdxs, xfenTypes = chan.parse2ChanXD(frsBiType, biIdx, chanK)
    log.debug('线段%s ,fenT:%s' % (xdIdxs, xfenTypes))
    x_xd_seq = []
    y_xd_seq = []
    for i in range(len(xdIdxs)):
        if xdIdxs[i] is not None:
            fenType = xfenTypes[i]
    #         dt = chanK['enddate'][biIdx[i]]
            # 缠论k线
            dt = chanK.index[xdIdxs[i]] if chanK_flag else chanK['enddate'][xdIdxs[i]]
    #         print k_data['high'][dt], k_data['low'][dt]
            time_long = int(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
    #         print x_date_list.index(time_long) if time_long in x_date_list else 0
            if fenType == 1:
                x_xd_seq.append(x_date_list.index(time_long))
                y_xd_seq.append(k_data['high'][dt])
            if fenType == -1:
                x_xd_seq.append(x_date_list.index(time_long))
                y_xd_seq.append(k_data['low'][dt])
    #  在原图基础上添加分笔蓝线
    log.debug("线段   :%s" % (x_xd_seq[:-2]))
    log.debug("笔值  :%s" % ([str(x) for x in (y_xd_seq)][:-2]))
    # Y_hat = X * b + a

    if len(x_xd_seq) == 0 or resample not in ct.Resample_LABELS:
        if resample in ct.Resample_LABELS:
            st_data=str(chanK['enddate'][biIdx[len(biIdx) - 1]])[:10]
        else:
            st_data=str(chanK['enddate'][biIdx[len(biIdx) - 1]])

        print(("stdate:%s" % (st_data)))

    if power:
        return BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10], len(keydf)
    
    if show_mpl:

        plt.plot(x_fenbi_seq, y_fenbi_seq)
        # quotes = quotes.round(2)
        # plt.legend([stock_code,cname], loc=0)
        plt.legend([stock_code, cname, "Now:%s" % (quotes.close[-1]), 'kdl:%s' % (kdl_mode.values[:4]), 'kdh:%s' % (kdh_mode.values[:4]),'ma:%s'%(roll_mean_days)], fontsize=12, loc=0)
        if len(kdl_mode) > 0:
            plt.axhline(y=np.median(kdl_mode.values), linewidth=2, color='green', linestyle="--")
        if len(kdh_mode) > 0:
            plt.axhline(y=np.median(kdh_mode.values), linewidth=2, color='red', linestyle="--")
        plt.title(stock_code + " | " + cname + " | " + str(quotes.index[-1])[:10], fontsize=14)

        plt.plot(x_xd_seq, y_xd_seq)
        #plt roll_mean windows  default 20
        zp = zoompan.ZoomPan()
        figZoom = zp.zoom_factory(ax1, base_scale=1.1)
        figPan = zp.pan_factory(ax1)

        # same sharex
        plt.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.00)
        plt.setp(ax1.get_xticklabels(), visible=False)
        yl = ax1.get_ylim()
        # ax2 = plt.subplot(212, sharex=ax1)
        ax2 = plt.subplot2grid((10, 1), (8, 0), rowspan=2, colspan=1, sharex=ax1)
        # ax2.set_position(mat.transforms.Bbox([[0.125,0.1],[0.9,0.32]]))
        # amount is not full data
        # volume = np.asarray(quotes.amount) 
        volume = np.asarray(quotes.vol)
        pos = quotes['open'] - quotes['close'] < 0
        neg = quotes['open'] - quotes['close'] >= 0
        idx = quotes.reset_index().index
        ax2.bar(idx[pos.values], volume[pos.values], color='red', width=1, align='center')
        ax2.bar(idx[neg.values], volume[neg.values], color='green', width=1, align='center')
        yticks = ax2.get_yticks()
        ax2.set_yticks(yticks[::3])
        # plt.tight_layout()
        # plt.subplots_adjust(hspace=0.00, bottom=0.08)
        plt.xticks(rotation=15, horizontalalignment='center')
        # plt.bar(x_date_list,quotes.vol, label="Volume", color='b')

        # quotes['vol'].plot(kind='bar', ax=ax2, color='g', alpha=0.1)
        # ax2.set_ylim([0, ax2.get_ylim()[1] * 2])
        # plt.gcf().subplots_adjust(bottom=0.15)
        # fig.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.25)
        # scale the x-axis tight
        # ax2.set_xlim(min(x_date_list),max(x_date_list))
        # the y-ticks for the bar were too dense, keep only every third one
        # plt.grid(True)
        # plt.xticks(rotation=30, horizontalalignment='center')
        # plt.setp( axs[1].xaxis.get_majorticklabels(), rotation=70 )
        # plt.legend()
        # plt.tight_layout()
        # plt.draw()
        plt.show()
        # plt.show(block=False)
    #


# show mpl
# def show_chan_mpl(code, start_date, end_date, stock_days, resample, show_mpl=True, least_init=3, chanK_flag=False, windows=20, fb_show=0):
#     def get_least_khl_num(resample, idx=0, init_num=3):
#         # init = 3
#         if init_num - idx > 0:
#             initw = init_num - idx
#         else:
#             initw = 0
#         return init_num if resample == 'd' else initw if resample == 'w' else init_num - idx - 1 if init_num - idx - 1 > 0 else 0\
#                 if resample == 'm' else 5
#     stock_code = code  # 股票代码
#     # stock_code = '002176' # 股票代码
#     # start_date = '2017-09-05'
#     # start_date = None
#     # end_date = '2017-10-12 15:00:00'  # 最后生成k线日期
#     # end_date = None
#     # stock_days = 60  # 看几天/分钟前的k线
#     # resample = 'd'
#     # resample = 'w'
#     x_jizhun = 3  # window 周期 x轴展示的时间距离  5：日，40:30分钟， 48： 5分钟
#     least_khl_num = get_least_khl_num(resample, init_num=least_init)
#     # stock_frequency = '5m' # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟
#     stock_frequency = resample  # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟 w:week
#     # chanK_flag = chanK  # True 看缠论K线， False 看k线
#     # chanK_flag = True  # True 看缠论K线， False 看k线
#     show_mpl = show_mpl

#     def con2Cxianduan(stock, k_data, chanK, frsBiType, biIdx, end_date, cur_ji=1, recursion=False, dl=None, chanK_flag=False, least_init=3):
#         max_k_num = 4
#         if cur_ji >= 6 or len(biIdx) == 0 or recursion:
#             return biIdx
#         idx = biIdx[len(biIdx) - 1]
#         k_data_dts = list(k_data.index)
#         st_data = chanK['enddate'][idx]
#         if st_data not in k_data_dts:
#             return biIdx
#         # 重构次级别线段的点到本级别的chanK中

#         def refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji):
#             new_biIdx = []
#             biIdxB = biIdx[len(biIdx) - 1] if len(biIdx) > 0 else 0
#             for xdIdxcn in xdIdxc:
#                 for chanKidx in range(len(chanK.index))[biIdxB:]:
#                     if judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
#                         new_biIdx.append(chanKidx)
#                         break
#             return new_biIdx
#         # 判断次级别日期是否被包含

#         def judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
#             _end_date = chanK['enddate'][chanKidx] + datetime.timedelta(hours=15) if cur_ji == 1 else chanK['enddate'][chanKidx]
#             _start_date = chanK.index[chanKidx] if chanKidx == 0\
#                 else chanK['enddate'][chanKidx - 1] + datetime.timedelta(minutes=1)
#             return _start_date <= chanKc.index[xdIdxcn] <= _end_date
#         # cur_ji = 1 #当前级别
#         # 符合k线根数大于4根 1日级别， 2 30分钟， 3 5分钟， 4 一分钟
#         if not recursion:
#             resample = 'd' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else \
#                 'd' if cur_ji + 1 == 5 else 'w' if cur_ji + 1 == 6 else 'd'
#         least_khl_num = get_least_khl_num(resample, 1, init_num=least_init)
#         print "次级:%s st_data:%s k_data_dts:%s least_khl_num:%s" % (len(k_data_dts) - k_data_dts.index(st_data), str(st_data)[:10], len(k_data_dts), least_khl_num)
#         if cur_ji + 1 != 2 and len(k_data_dts) - k_data_dts.index(st_data) >= least_khl_num + 1:
#             frequency = '30m' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else '1m'
#             # else:
#                 # frequency = 'd' if cur_ji+1==2 else '5m' if cur_ji+1==3 else \
#                 #                 'd' if cur_ji+1==5 else 'w' if cur_ji+1==6 else 'd'

#             start_lastday = str(chanK.index[biIdx[-1]])[0:10]
#             print "次级别为:%s cur_ji:%s %s" % (resample, cur_ji, start_lastday)
#             # print [chanK.index[x] for x in biIdx]
#             k_data_c, cname = get_quotes_tdx(stock, start=start_lastday, end=end_date, dl=dl, resample=resample)
#             print k_data_c.index[0], k_data_c.index[-1]
#             chanKc = chan.parse2ChanK(k_data_c, k_data_c.values) if chanK_flag else k_data_c
#             fenTypesc, fenIdxc = chan.parse2ChanFen(chanKc, recursion=True)
#             if len(fenTypesc) == 0:
#                 return biIdx
#             biIdxc, frsBiTypec = chan.parse2ChanBi(fenTypesc, fenIdxc, chanKc, least_khl_num=least_khl_num - 1)
#             if len(biIdxc) == 0:
#                 return biIdx
#             # print "biIdxc:", [round(k_data_c.high[x], 2) for x in biIdxc], [str(k_data_c.index[x])[:10] for x in biIdxc]
#             xdIdxc, xdTypec = chan.parse2Xianduan(biIdxc, chanKc, least_windows=1 if least_khl_num > 0 else 0)
#             biIdxc = con2Cxianduan(stock, k_data_c, chanKc, frsBiTypec, biIdxc, end_date, cur_ji + 1, recursion=True)
#             # print "xdIdxc:%s xdTypec:%s biIdxc:%s" % (xdIdxc, xdTypec, biIdxc)
#             if len(xdIdxc) == 0:
#                 return biIdx
#             # 连接线段位为上级别的bi
#             lastBiType = frsBiType if len(biIdx) % 2 == 0 else -frsBiType
#             if len(biIdx) == 0:
#                 return refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
#             lastbi = biIdx.pop()
#             firstbic = xdIdxc.pop(0)
#             # 同向连接
#             if lastBiType == xdTypec:
#                 biIdx = biIdx + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
#             # 逆向连接
#             else:
#                 #             print '开始逆向连接'
#                 _mid = [lastbi] if (lastBiType == -1 and chanK['low'][lastbi] <= chanKc['low'][firstbic])\
#                     or (lastBiType == 1 and chanK['high'][lastbi] >= chanKc['high'][firstbic]) else\
#                     [chanKidx for chanKidx in range(len(chanK.index))[biIdx[len(biIdx) - 1]:]
#                      if judge_day_bao(chanK, chanKidx, chanKc, firstbic, cur_ji)]
#                 biIdx = biIdx + [_mid[0]] + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
#             # print "次级:",len(biIdx),biIdx,[str(k_data_c.index[x])[:10] for x in biIdx]
#         return biIdx

#     def get_quotes_tdx(code, start=None, end=None, dl=120, resample='d', show_name=True):

#         quotes = tdd.get_tdx_append_now_df_api(code=stock_code, start=start, end=end, dl=dl).sort_index(ascending=True)
#         if not resample == 'd' and resample in tdd.resample_dtype:
#             quotes = tdd.get_tdx_stock_period_to_type(quotes, period_day=resample)
#         quotes.index = quotes.index.astype('datetime64')
#         if show_name:
#             if 'name' in quotes.columns:
#                 cname = quotes.name[0]
#                 # cname_g =cname
#             else:
#                 dm = tdd.get_sina_data_df(code)
#                 if 'name' in dm.columns:
#                     cname = dm.name[0]
#                 else:
#                     cname = '-'
#         else:
#             cname = '-'
#         if quotes is not None and len(quotes) > 0:
#             quotes = quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount']]
#         else:
#             # log.error("quotes is None check:%s"%(code))
#             raise Exception("Code:%s error, df is None%s" % (code))
#         return quotes, cname

#     quotes, cname = get_quotes_tdx(stock_code, start_date, end_date, dl=stock_days, resample=resample, show_name=show_mpl)
#     # quotes.rename(columns={'amount': 'money'}, inplace=True)
#     # quotes.rename(columns={'vol': 'vol'}, inplace=True)
#     # print quotes[-2:]
#     # print quotes[:1]
#     # 缠论k线
#     #         open  close   high    low    volume      money
#     # 2017-05-03  15.69  15.66  15.73  15.53  10557743  165075887
#     # 2017-05-04  15.66  15.63  15.70  15.52   8343270  130330396
#     # 2017-05-05  15.56  15.65  15.68  15.41  18384031  285966842
#     # 2017-05-08  15.62  15.75  15.76  15.54  12598891  197310688
#     quotes = chan.parse2ChanK(quotes, quotes.values) if chanK_flag else quotes
#     # print quotes[:1].index
#     # print quotes[-1:].index

#     quotes[quotes['vol'] == 0] = np.nan
#     quotes = quotes.dropna()
#     Close = quotes['close']
#     Open = quotes['open']
#     High = quotes['high']
#     Low = quotes['low']
#     T0 = quotes.index.values
#     # T0 =  mdates.date2num(T0)
#     length = len(Close)

#     initial_trend = "down"
#     cur_ji = 1 if stock_frequency == 'd' else \
#         2 if stock_frequency == '30m' else \
#         3 if stock_frequency == '5m' else \
#         4 if stock_frequency == 'w' else \
#         5 if stock_frequency == 'm' else 6

#     log.debug('======笔形成最后一段未完成段判断是否是次级别的走势形成笔=======:%s %s' % (stock_frequency, cur_ji))

#     x_date_list = quotes.index.values.tolist()
#     # for x_date in x_date_list:
#     #     d = datetime.datetime.fromtimestamp(x_date/1000000000)
#     #     print d.strftime("%Y-%m-%d %H:%M:%S.%f")
#     # print x_date_list
#     k_data = quotes
#     k_values = k_data.values
#     # 缠论k线
#     chanK = quotes if chanK_flag else chan.parse2ChanK(k_data, k_values, chan_kdf=chanK_flag)

#     fenTypes, fenIdx = chan.parse2ChanFen(chanK)
#     # log.debug("code:%s fenTypes:%s fenIdx:%s k_data:%s" % (stock_code,fenTypes, fenIdx, len(k_data)))
#     biIdx, frsBiType = chan.parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
#     # log.debug("biIdx1:%s chanK:%s" % (biIdx, len(chanK)))
#     # print ("biIdx1:%s %s chanK:%s" % (biIdx, str(chanK.index.values[biIdx[-1]])[:10],len(chanK)))

#     biIdx = con2Cxianduan(stock_code, k_data, chanK, frsBiType, biIdx, end_date, cur_ji, least_init=least_init)
#     # log.debug("biIdx2:%s chanK:%s" % (biIdx, len(biIdx)))
#     chanKIdx = [(chanK.index[x]) for x in biIdx]

#     if len(biIdx) == 0 and len(chanKIdx) == 0:
#         # print "BiIdx is None and chanKidx is None:%s"%(code)
#         return None

#     log.debug("con2Cxianduan:%s chanK:%s %s" % (biIdx, len(chanK), chanKIdx[-1] if len(chanKIdx) > 0 else None))
#     # print quotes['close'].apply(lambda x:round(x,2))

#     # print '股票代码', get_security_info(stock_code).display_name
#     # print '股票代码', (stock_code), resample, least_khl_num
#     #  3.得到分笔结果，计算坐标显示

#     def plot_fenbi_seq(biIdx, frsBiType, plt=None, color=None, fb_show=0):
#         x_fenbi_seq = []
#         y_fenbi_seq = []
#         for i in range(len(biIdx)):
#             if biIdx[i] is not None:
#                 fenType = -frsBiType if i % 2 == 0 else frsBiType
#         #         dt = chanK['enddate'][biIdx[i]]
#                 # 缠论k线
#                 dt = chanK.index[biIdx[i]] if chanK_flag else chanK['enddate'][biIdx[i]]
#                 # print i,k_data['high'][dt], k_data['low'][dt]
#                 time_long = long(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
#                 # print x_date_list.index(time_long) if time_long in x_date_list else 0
#                 if fenType == 1:
#                     if plt is not None:
#                         if color is None:
#                             plt.text(x_date_list.index(time_long), k_data['high'][dt],
#                                      str(k_data['high'][dt]), ha='left', fontsize=12)
#                         elif fb_show:
#                             col_v = color[0] if fenType > 0 else color[1]
#                             plt.text(x_date_list.index(time_long), k_data['high'][dt],
#                                      str(k_data['high'][dt]), ha='left', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

#                     x_fenbi_seq.append(x_date_list.index(time_long))
#                     y_fenbi_seq.append(k_data['high'][dt])
#                 if fenType == -1:
#                     if plt is not None:
#                         if color is None:
#                             plt.text(x_date_list.index(time_long), k_data['low'][dt],
#                                      str(k_data['low'][dt]), va='bottom', fontsize=12)
#                         elif fb_show:
#                             col_v = color[0] if fenType > 0 else color[1]
#                             plt.text(x_date_list.index(time_long), k_data['low'][dt],
#                                      str(k_data['low'][dt]), va='bottom', fontsize=12, bbox=dict(facecolor=col_v, alpha=0.5))

#                     x_fenbi_seq.append(x_date_list.index(time_long))
#                     y_fenbi_seq.append(k_data['low'][dt])
#     #             bottom_time = None
#     #             for k_line_dto in m_line_dto.member_list[::-1]:
#     #                 if k_line_dto.low == m_line_dto.low:
#     #                     # get_price返回的日期，默认时间是08:00:00
#     #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
#     #                     break
#     #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
#     #             y_fenbi_seq.append(m_line_dto.low)
#         return x_fenbi_seq, y_fenbi_seq

#     # print  T0[-len(T0):].astype(dt.date)
#     T1 = T0[-len(T0):].astype(datetime.date) / 1000000000
#     Ti = []
#     if len(T0) / x_jizhun > 12:
#         x_jizhun = len(T0) / 12
#     for i in range(len(T0) / x_jizhun):
#         # print "len(T0)/x_jizhun:",len(T0)/x_jizhun
#         a = i * x_jizhun
#         d = datetime.date.fromtimestamp(T1[a])
#         # print d
#         T2 = d.strftime('$%Y-%m-%d$')
#         Ti.append(T2)
#         # print tab
#     d1 = datetime.date.fromtimestamp(T1[len(T0) - 1])
#     d2 = (d1 + datetime.timedelta(days=1)).strftime('$%Y-%m-%d$')
#     Ti.append(d2)

#     ll = Low.min() * 0.97
#     hh = High.max() * 1.03

#     # ht = HoverTool(tooltips=[
#     #             ("date", "@date"),
#     #             ("open", "@open"),
#     #             ("close", "@close"),
#     #             ("high", "@high"),
#     #             ("low", "@low"),
#     #             ("volume", "@volume"),
#     #             ("money", "@money"),])
#     # TOOLS = [ht, WheelZoomTool(dimensions=['width']),\
#     #          ResizeTool(), ResetTool(),\
#     #          PanTool(dimensions=['width']), PreviewSaveTool()]
#     if show_mpl:
#         fig = plt.figure(figsize=(10, 6))
#         ax1 = plt.subplot2grid((10, 1), (0, 0), rowspan=8, colspan=1)
#         # ax1 = fig.add_subplot(2,1,1)
#         # fig = plt.figure()
#         # ax1 = plt.axes([0,0,3,2])

#         X = np.array(range(0, length))
#         pad_nan = X + nan

#         # 计算上 下影线
#         max_clop = Close.copy()
#         max_clop[Close < Open] = Open[Close < Open]
#         min_clop = Close.copy()
#         min_clop[Close > Open] = Open[Close > Open]

#         # 上影线
#         line_up = np.array([High, max_clop, pad_nan])
#         line_up = np.ravel(line_up, 'F')
#         # 下影线
#         line_down = np.array([Low, min_clop, pad_nan])
#         line_down = np.ravel(line_down, 'F')

#         # 计算上下影线对应的X坐标
#         pad_nan = nan + X
#         pad_X = np.array([X, X, X])
#         pad_X = np.ravel(pad_X, 'F')

#         # 画出实体部分,先画收盘价在上的部分
#         up_cl = Close.copy()
#         up_cl[Close <= Open] = nan
#         up_op = Open.copy()
#         up_op[Close <= Open] = nan

#         down_cl = Close.copy()
#         down_cl[Open <= Close] = nan
#         down_op = Open.copy()
#         down_op[Open <= Close] = nan

#         even = Close.copy()
#         even[Close != Open] = nan

#         # 画出收红的实体部分
#         pad_box_up = np.array([up_op, up_op, up_cl, up_cl, pad_nan])
#         pad_box_up = np.ravel(pad_box_up, 'F')
#         pad_box_down = np.array([down_cl, down_cl, down_op, down_op, pad_nan])
#         pad_box_down = np.ravel(pad_box_down, 'F')
#         pad_box_even = np.array([even, even, even, even, pad_nan])
#         pad_box_even = np.ravel(pad_box_even, 'F')

#         # X的nan可以不用与y一一对应
#         X_left = X - 0.25
#         X_right = X + 0.25
#         box_X = np.array([X_left, X_right, X_right, X_left, pad_nan])
#         # print box_X
#         box_X = np.ravel(box_X, 'F')
#         # print box_X
#         # Close_handle=plt.plot(pad_X,line_up,color='k')

#         vertices_up = np.array([box_X, pad_box_up]).T
#         vertices_down = np.array([box_X, pad_box_down]).T
#         vertices_even = np.array([box_X, pad_box_even]).T

#         handle_box_up = mat.patches.Polygon(vertices_up, color='r', zorder=1)
#         handle_box_down = mat.patches.Polygon(vertices_down, color='g', zorder=1)
#         handle_box_even = mat.patches.Polygon(vertices_even, color='k', zorder=1)

#         ax1.add_patch(handle_box_up)
#         ax1.add_patch(handle_box_down)
#         ax1.add_patch(handle_box_even)

#         handle_line_up = mat.lines.Line2D(pad_X, line_up, color='k', linestyle='solid', zorder=0)
#         handle_line_down = mat.lines.Line2D(pad_X, line_down, color='k', linestyle='solid', zorder=0)

#         ax1.add_line(handle_line_up)
#         ax1.add_line(handle_line_down)

#         v = [0, length, Open.min() - 0.5, Open.max() + 0.5]
#         plt.axis(v)

#         ax1.set_xticks(np.linspace(-2, len(Close) + 2, len(Ti)))

#         ax1.set_ylim(ll, hh)

#         ax1.set_xticklabels(Ti)

#         assvol = quotes['vol']
#         # assvol = assvol.apply(lambda x: round(x / assvol[:1]*quotes.close[:1], 2))
#         assvol = assvol.apply(lambda x: round(x / assvol[:1] + quotes.close[:1], 2))
#         ax1.plot(assvol, '-g', linewidth=0.5)

#         plt.grid(True)
#         plt.setp(plt.gca().get_xticklabels(), rotation=30, horizontalalignment='right')

#     '''
#     以上代码拷贝自https://www.joinquant.com/post/1756
#     感谢alpha-smart-dog

#     K线图绘制完毕
#     '''

#     # print "biIdx:%s chankIdx:%s"%(biIdx,str(chanKIdx[-1])[:10])
#     if show_mpl:
#         x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt)
#         # plot_fenbi_seq(fenIdx,fenTypes[0], plt,color=['red','green'])
#         plot_fenbi_seq(fenIdx, frsBiType, plt, color=['red', 'green'], fb_show=fb_show)
#     else:
#         x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt=None)
#         plot_fenbi_seq(fenIdx, frsBiType, plt=None, color=['red', 'green'], fb_show=fb_show)
#     #  在原图基础上添加分笔蓝线
#     inx_value = chanK.high.values
#     inx_va = [round(inx_value[x], 2) for x in biIdx]
#     log.info("inx_va:%s count:%s" % (inx_va, len(quotes.high)))
#     log.info("yfenbi:%s count:%s" % ([round(y, 2) for y in y_fenbi_seq], len(chanK)))
#     j_BiType = [-frsBiType if i % 2 == 0 else frsBiType for i in range(len(biIdx))]
#     BiType_s = j_BiType[-1] if len(j_BiType) > 0 else -2
#     # bi_price = [str(chanK.low[idx]) if i % 2 == 0 else str(chanK.high[idx])  for i,idx in enumerate(biIdx)]
#     # print ("笔     :%s %s"%(biIdx,bi_price))
#     # fen_dt = [str(chanK.index[fenIdx[i]])[:10] if chanK_flag else str(chanK['enddate'][fenIdx[i]])[:10]for i in range(len(fenIdx))]
#     fen_dt = [(chanK.index[fenIdx[i]]) if chanK_flag else (chanK['enddate'][fenIdx[i]]) for i in range(len(fenIdx))]
#     if len(fenTypes) > 0:
#         if fenTypes[0] == -1:
#             # fen_price = [str(k_data.low[idx]) if i % 2 == 0 else str(k_data.high[idx])  for i,idx in enumerate(fen_dt)]
#             low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
#             high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 <> 0]
#         else:
#             # fen_price = [str(k_data.high[idx]) if i % 2 == 0 else str(k_data.low[idx])  for i,idx in enumerate(fen_dt)]
#             high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
#             low_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 <> 0]
#         # fen_duration =[fenIdx[i] - fenIdx[i -1 ] if i >0 else 0 for i,idx in enumerate(fenIdx)]
#     else:
#         # fen_price = fenTypes
#         # fen_duration = fenTypes
#         low_fen = []
#         high_fen = []
#     # fen_dt = [str(k_data.index[idx])[:10] for i,idx in enumerate(fenIdx)]
#     # print low_fen,high_fen

#     def dataframe_mode_round(df):
#         roundlist = [1, 0]
#         df_mode = []
#         for i in roundlist:
#             df_mode = df.apply(lambda x: round(x, i)).mode()
#             if len(df_mode) > 0:
#                 break
#         return df_mode

#     kdl = k_data.loc[low_fen].low
#     kdl_mode = dataframe_mode_round(kdl)
#     kdh = k_data.loc[high_fen].high
#     kdh_mode = dataframe_mode_round(kdh)

#     log.info("kdl:%s" % (kdl.values))
#     log.info("kdh:%s" % (kdh.values))
#     print("kdl_modeX1:%s kdh_mode%s chanKidx:%s" % (kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10]))

#     lkdl, lkdlidx = LIS(kdl)
#     lkdh, lkdhidx = LIS(kdh)
#     l_status = len(kdl) - len(lkdl)
#     h_status = len(kdh) - len(lkdh)
#     print("LkdlX2:%s Lkdh:%s UP:%s fb:%s" % (l_status, h_status, h_status - l_status, len(kdl) - len(kdh)))

#     # print ("Gkdl:%s Gkdh:%s"%(grouby_list(kdl.values)[:2],grouby_list(kdh.values)[:2]))

#     lastdf = k_data[k_data.index >= chanKIdx[-1]]
#     if BiType_s == -1:
#         keydf = lastdf[((lastdf.close >= kdl_mode.max()) & (lastdf.low >= kdl_mode.max()))]
#     elif BiType_s == 1:
#         keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min()))]
#     else:
#         keydf = lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min())) |
#                         ((lastdf.close <= kdl_mode.min()) & (lastdf.low <= kdl_mode.min()))]
#     # print ("BiType_sX3:%s keydf:%s key:%s"%(BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10],len(keydf)))

#     # return BiType_s,None if len(keydf) == 0 else str(keydf.index.values[0])[:10],len(keydf)
#     # import ipdb;ipdb.set_trace()

#     log.debug("Fentype:%s " % (fenTypes))
#     log.debug("fenIdx:%s " % (fenIdx))
#     # print ("fen_duration:%s "%(fen_duration))
#     # print ("fen_price:%s "%(fen_price))
#     # print ("fendt:%s "%(fen_dt))

#     # print ("BiType :%s frsBiType:%s"%(j_BiType,frsBiType))

#     if len(j_BiType) > 0:
#         if j_BiType[0] == -1:
#             tb_price = [str(quotes.low[idx]) if i % 2 == 0 else str(quotes.high[idx]) for i, idx in enumerate(x_fenbi_seq)]
#         else:
#             tb_price = [str(quotes.high[idx]) if i % 2 == 0 else str(quotes.low[idx]) for i, idx in enumerate(x_fenbi_seq)]
#         tb_duration = [x_fenbi_seq[i] - x_fenbi_seq[i - 1] if i > 0 else 0 for i, idx in enumerate(x_fenbi_seq)]

#     else:
#         tb_price = j_BiType
#         tb_duration = j_BiType
#     # print "图笔 :", x_fenbi_seq,tb_price
#     # print "图笔dura :", tb_duration

#     # 线段画到笔上
#     xdIdxs, xfenTypes = chan.parse2ChanXD(frsBiType, biIdx, chanK)
#     # print '线段', xdIdxs, xfenTypes
#     x_xd_seq = []
#     y_xd_seq = []
#     for i in range(len(xdIdxs)):
#         if xdIdxs[i] is not None:
#             fenType = xfenTypes[i]
#     #         dt = chanK['enddate'][biIdx[i]]
#             # 缠论k线
#             dt = chanK.index[xdIdxs[i]] if chanK_flag else chanK['enddate'][xdIdxs[i]]
#     #         print k_data['high'][dt], k_data['low'][dt]
#             time_long = long(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
#     #         print x_date_list.index(time_long) if time_long in x_date_list else 0
#             if fenType == 1:
#                 x_xd_seq.append(x_date_list.index(time_long))
#                 y_xd_seq.append(k_data['high'][dt])
#             if fenType == -1:
#                 x_xd_seq.append(x_date_list.index(time_long))
#                 y_xd_seq.append(k_data['low'][dt])
#     #             bottom_time = None
#     #             for k_line_dto in m_line_dto.member_list[::-1]:
#     #                 if k_line_dto.low == m_line_dto.low:
#     #                     # get_price返回的日期，默认时间是08:00:00
#     #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
#     #                     break
#     #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
#     #             y_fenbi_seq.append(m_line_dto.low)

#     #  在原图基础上添加分笔蓝线

#     print("线段   :%s type:%s" % (x_xd_seq, [str(quotes.index[x])[:10] for x in x_xd_seq]))
#     print("笔值  :%s" % ([str(x) for x in (y_xd_seq)]))
#     if len(x_xd_seq) == 0:
#         st_data = str(chanK['enddate'][biIdx[len(biIdx) - 1]])[:10]
#         print("stdate:%s" % (st_data))
#     # Y_hat = X * b + a

#     if show_mpl:
#         plt.plot(x_fenbi_seq, y_fenbi_seq)
#         # plt.legend([stock_code,cname], loc=0)
#         plt.legend([stock_code, cname, "Now:%s" % quotes.close[-1], 'kdl:%s' % (kdl_mode.values), 'kdh:%s' % (kdh_mode.values)], fontsize=12, loc=0)
#         if len(kdl_mode) > 0:
#             plt.axhline(y=np.median(kdl_mode.values), linewidth=2, color='red', linestyle="--")
#         if len(kdh_mode) > 0:
#             plt.axhline(y=np.median(kdh_mode.values), linewidth=2, color='green', linestyle="--")
#         plt.title(stock_code + " | " + cname + " | " + str(quotes.index[-1])[:10], fontsize=14)
#         plt.plot(x_xd_seq, y_xd_seq)
#         if len(quotes) > windows:
#             roll_mean = pd.rolling_mean(quotes.close, window=windows)
#             plt.plot(roll_mean, 'r')
#         zp = zoompan.ZoomPan()
#         figZoom = zp.zoom_factory(ax1, base_scale=1.1)
#         figPan = zp.pan_factory(ax1)
#         '''#subplot2 bar
#         ax2 = plt.subplot2grid((10, 1), (8, 0), rowspan=2, colspan=1)
#         # ax2.plot(quotes.vol)
#         # ax2.set_xticks(np.linspace(-2, len(quotes) + 2, len(Ti)))
#         ll = min(quotes.vol.values.tolist()) * 0.97
#         hh = max(quotes.vol.values.tolist()) * 1.03
#         ax2.set_ylim(ll, hh)
#         # ax2.set_xticklabels(Ti)
#         # plt.hist(quotes.vol, histtype='bar', rwidth=0.8)
#         plt.bar(x_date_list,quotes.vol, label="Volume", color='b')
#         '''

#         # 画Volume no tight_layout()
#         '''
#         pad = 0.25
#         yl = ax1.get_ylim()
#         ax1.set_ylim(yl[0]-(yl[1]-yl[0])*pad,yl[1])
#         ax2 = ax1.twinx()
#         ax2.set_position(mat.transforms.Bbox([[0.125,0.1],[0.9,0.32]]))
#         volume = np.asarray(quotes.amount)
#         pos = quotes['open']-quotes['close']<0
#         neg = quotes['open']-quotes['close']>=0
#         idx = quotes.reset_index().index
#         ax2.bar(idx[pos],volume[pos],color='red',width=1,align='center')
#         ax2.bar(idx[neg],volume[neg],color='green',width=1,align='center')
#         yticks = ax2.get_yticks()
#         ax2.set_yticks(yticks[::3])
#         '''

#         # same sharex
#         plt.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.00)
#         plt.setp(ax1.get_xticklabels(), visible=False)
#         yl = ax1.get_ylim()
#         # ax2 = plt.subplot(212, sharex=ax1)
#         ax2 = plt.subplot2grid((10, 1), (8, 0), rowspan=2, colspan=1, sharex=ax1)
#         # ax2.set_position(mat.transforms.Bbox([[0.125,0.1],[0.9,0.32]]))
#         volume = np.asarray(quotes.amount)
#         pos = quotes['open'] - quotes['close'] < 0
#         neg = quotes['open'] - quotes['close'] >= 0
#         idx = quotes.reset_index().index
#         ax2.bar(idx[pos], volume[pos], color='red', width=1, align='center')
#         ax2.bar(idx[neg], volume[neg], color='green', width=1, align='center')
#         yticks = ax2.get_yticks()
#         ax2.set_yticks(yticks[::3])
#         # plt.tight_layout()
#         # plt.subplots_adjust(hspace=0.00, bottom=0.08)
#         plt.xticks(rotation=15, horizontalalignment='center')
#         # plt.bar(x_date_list,quotes.vol, label="Volume", color='b')

#         # quotes['vol'].plot(kind='bar', ax=ax2, color='g', alpha=0.1)
#         # ax2.set_ylim([0, ax2.get_ylim()[1] * 2])
#         # plt.gcf().subplots_adjust(bottom=0.15)
#         # fig.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.25)
#         # scale the x-axis tight
#         # ax2.set_xlim(min(x_date_list),max(x_date_list))
#         # the y-ticks for the bar were too dense, keep only every third one
#         # plt.grid(True)
#         # plt.xticks(rotation=30, horizontalalignment='center')
#         # plt.setp( axs[1].xaxis.get_majorticklabels(), rotation=70 )
#         # plt.legend()
#         # plt.tight_layout()
#         # plt.draw()
#         # plt.show()
#         plt.show(block=False)


def show_chan_mpl_fb(code, start_date, end_date, stock_days, resample, show_mpl=True, least_init=2, chanK_flag=False, windows=20, fb_show=0,roll_mean_days=20):
   
    stock_code = code  # 股票代码
    stock_frequency = '%sm'%resample if resample.isdigit() else resample
    resample = '%sT'%resample if resample.isdigit() else resample
    log.info('resample:%s'%(resample))
    # stock_code = '002176' # 股票代码
    # start_date = '2017-09-05'
    # start_date = None
    # end_date = '2017-10-12 15:00:00'  # 最后生成k线日期
    # end_date = None
    # stock_days = 60  # 看几天/分钟前的k线
    # resample = 'd'
    # resample = 'w'
    x_jizhun = 3  # window 周期 x轴展示的时间距离  5：日，40:30分钟， 48： 5分钟
    least_khl_num = get_least_khl_num(resample, init_num=least_init)
    # stock_frequency = '5m' # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟
    # stock_frequency = resample  # 1d日线， 30m 30分钟， 5m 5分钟，1m 1分钟 w:week
    # chanK_flag = chanK  # True 看缠论K线， False 看k线
    # chanK_flag = True  # True 看缠论K线， False 看k线
    show_mpl = show_mpl

    def con2Cxianduan(stock, k_data, chanK, frsBiType, biIdx, end_date, cur_ji=1, recursion=False, dl=None, chanK_flag=False, least_init=3,resample=resample):
        max_k_num = 4
        if cur_ji >= 6 or len(biIdx) == 0 or recursion:
            return biIdx
        idx = biIdx[len(biIdx) - 1]
        k_data_dts = list(k_data.index)
        st_data = chanK['enddate'][idx]
        if st_data not in k_data_dts:
            return biIdx
        # 重构次级别线段的点到本级别的chanK中

        def refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji):
            new_biIdx = []
            biIdxB = biIdx[len(biIdx) - 1] if len(biIdx) > 0 else 0
            for xdIdxcn in xdIdxc:
                for chanKidx in range(len(chanK.index))[biIdxB:]:
                    if judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
                        new_biIdx.append(chanKidx)
                        break
            return new_biIdx
        # 判断次级别日期是否被包含

        def judge_day_bao(chanK, chanKidx, chanKc, xdIdxcn, cur_ji):
            _end_date = chanK['enddate'][chanKidx] + datetime.timedelta(hours=15) if cur_ji == 1 else chanK['enddate'][chanKidx]
            _start_date = chanK.index[chanKidx] if chanKidx == 0\
                else chanK['enddate'][chanKidx - 1] + datetime.timedelta(minutes=1)
            return _start_date <= chanKc.index[xdIdxcn] <= _end_date
        # cur_ji = 1 #当前级别
        # 符合k线根数大于4根 1日级别， 2 30分钟， 3 5分钟， 4 一分钟
        least_khl_num = get_least_khl_num(get_resample_ciji(resample), 1, init_num=least_init)

        print('ths:')
        print((search_ths_data(code)))
        print(("次级:%s %s st_data:%s k_data_dts:%s least_khl_num:%s" % (resample,len(k_data_dts) - k_data_dts.index(st_data), str(st_data)[:10], len(k_data_dts), least_khl_num)))
       
        if not recursion:
            # resample = 'd' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else \
            #     'd' if cur_ji + 1 == 5 else 'w' if cur_ji + 1 == 6 else 'd'
            resample = get_resample_ciji(resample)

        if get_resample_ciji(resample) != 1 and  cur_ji + 1 != 2 and len(k_data_dts) - k_data_dts.index(st_data) >= least_khl_num + 1:
            frequency = '30m' if cur_ji + 1 == 2 else '5m' if cur_ji + 1 == 3 else '1m'
            # else:
                # frequency = 'd' if cur_ji+1==2 else '5m' if cur_ji+1==3 else \
                #                 'd' if cur_ji+1==5 else 'w' if cur_ji+1==6 else 'd'

            if resample in ct.Resample_LABELS:    
                start_lastday = str(chanK.index[biIdx[-1]])[0:10]
            else:
                start_lastday = str(chanK.index[biIdx[-1]])
            print(("次级别为:%s cur_ji:%s %s" % (resample, cur_ji, start_lastday)))
            # print [chanK.index[x] for x in biIdx]

            k_data_c, cname = get_quotes_tdx(stock, start=start_lastday, end=end_date, dl=dl, resample=resample)
            print(("kdata:%s  %s"%(k_data_c.index[0], k_data_c.index[-1])))
            chanKc = chan.parse2ChanK(k_data_c, k_data_c.values) if chanK_flag else k_data_c
            fenTypesc, fenIdxc = chan.parse2ChanFen(chanKc, recursion=True)
            if len(fenTypesc) == 0:
                return biIdx
            biIdxc, frsBiTypec = chan.parse2ChanBi(fenTypesc, fenIdxc, chanKc, least_khl_num=least_khl_num - 1)
            if len(biIdxc) == 0:
                return biIdx
            # print "biIdxc:", [round(k_data_c.high[x], 2) for x in biIdxc], [str(k_data_c.index[x])[:10] for x in biIdxc]
            xdIdxc, xdTypec = chan.parse2Xianduan(biIdxc, chanKc, least_windows=1 if least_khl_num > 0 else 0)
            biIdxc = con2Cxianduan(stock, k_data_c, chanKc, frsBiTypec, biIdxc, end_date, cur_ji + 1, recursion=True)
            # print "xdIdxc:%s xdTypec:%s biIdxc:%s" % (xdIdxc, xdTypec, biIdxc)
            if len(xdIdxc) == 0:
                return biIdx
            # 连接线段位为上级别的bi
            lastBiType = frsBiType if len(biIdx) % 2 == 0 else -frsBiType
            if len(biIdx) == 0:
                return refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            lastbi = biIdx.pop()
            firstbic = xdIdxc.pop(0)
            # 同向连接
            if lastBiType == xdTypec:
                biIdx = biIdx + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # 逆向连接
            else:
                #             print '开始逆向连接'
                _mid = [lastbi] if (lastBiType == -1 and chanK['low'][lastbi] <= chanKc['low'][firstbic])\
                    or (lastBiType == 1 and chanK['high'][lastbi] >= chanKc['high'][firstbic]) else\
                    [chanKidx for chanKidx in range(len(chanK.index))[biIdx[len(biIdx) - 1]:]
                     if judge_day_bao(chanK, chanKidx, chanKc, firstbic, cur_ji)]
                biIdx = biIdx + [_mid[0]] + refactorXd(biIdx, xdIdxc, chanK, chanKc, cur_ji)
            # print "次级:",len(biIdx),biIdx,[str(k_data_c.index[x])[:10] for x in biIdx]
        return biIdx

    # def get_quotes_tdx(code, start=None, end=None, dl=120, resample='d', show_name=True):

    #     if resample in ['d', 'w', 'm']:
    #         quotes = tdd.get_tdx_append_now_df_api(code=code, start=start, end=end, dl=dl).sort_index(ascending=True)
    #     else:
    #         h5_fname = 'sina_MultiIndex_data'
    #         h5_table = 'all_10'
    #         time_s = time.time()
    #         h5 = h5a.load_hdf_db(h5_fname, table=h5_table, code_l=None, timelimit=False, dratio_limit=0.12)
    #         quotes = cct.get_limit_multiIndex_freq(h5, freq=resample.upper(), col='all', start=start, end=end, code=code)
    #         quotes = quotes.reset_index().set_index('ticktime')
    #         # period_stock_data['close'] = stock_data['close'].resample(period_type, how='last')
    #         if 'volume' in quotes.columns:
    #             quotes.rename(columns={'volume': 'vol'}, inplace=True)
    #             quotes['amount'] = (map(lambda x, y: round((x * y), 1), quotes.close.values, quotes.vol.values))            
        
    #     if not resample == 'd' and resample in tdd.resample_dtype:
    #         quotes = tdd.get_tdx_stock_period_to_type(quotes, period_day=resample)
    #     if str(quotes.index.dtype) <> 'datetime64[ns]':
    #         quotes.index = quotes.index.astype('datetime64')

    #     if show_name:
    #         if 'name' in quotes.columns:
    #             cname = quotes.name[0]
    #             # cname_g =cname
    #         else:
    #             dm = tdd.get_sina_data_df(code)
    #             if 'name' in dm.columns:
    #                 cname = dm.name[0]
    #             else:
    #                 cname = '-'
    #     else:
    #         cname = '-'
    #     if quotes is not None and len(quotes) > 0:
    #         quotes= quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount']]
    #     else:
    #         # log.error("quotes is None check:%s"%(code))
    #         raise Exception("Code:%s error, df is None" % (code))
    #     return quotes, cname


    quotes, cname= get_quotes_tdx(stock_code, start_date, end_date, dl=stock_days, resample=resample, show_name=show_mpl)
    # quotes.rename(columns={'amount': 'money'}, inplace=True)
    # quotes.rename(columns={'vol': 'vol'}, inplace=True)
    # print quotes[-2:]
    # print quotes[:1]
    # 缠论k线
    #         open  close   high    low    volume      money
    # 2017-05-03  15.69  15.66  15.73  15.53  10557743  165075887
    # 2017-05-04  15.66  15.63  15.70  15.52   8343270  130330396
    # 2017-05-05  15.56  15.65  15.68  15.41  18384031  285966842
    # 2017-05-08  15.62  15.75  15.76  15.54  12598891  197310688
    quotes=quotes.round(2)

    quotes= chan.parse2ChanK(quotes, quotes.values) if chanK_flag else quotes
    # print quotes[:1].index
    # print quotes[-1:].index

    quotes[quotes['vol'] == 0]= np.nan
    quotes= quotes.dropna()
    Close= quotes['close']
    Open= quotes['open']
    High= quotes['high']
    Low= quotes['low']
    T0= quotes.index.values
    # T0 =  mdates.date2num(T0)
    length= len(Close)


    initial_trend= "down"
    cur_ji= 1 if stock_frequency == 'd' else \
        2 if stock_frequency == '30m' else \
        3 if stock_frequency == '5m' else \
        4 if stock_frequency == '1m' else \
        5 if stock_frequency == 'w' else \
        6 if stock_frequency == 'm' else 7

    log.debug('======笔形成最后一段未完成段判断是否是次级别的走势形成笔=======:%s %s' % (stock_frequency, cur_ji))

    x_date_list= quotes.index.values.tolist()
    # for x_date in x_date_list:
    #     d = datetime.datetime.fromtimestamp(x_date/1000000000)
    #     print d.strftime("%Y-%m-%d %H:%M:%S.%f")
    # print x_date_list
    # quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount','ma20d','upper','lower']]
    # quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount']]
    k_data= quotes.loc[:, ['open', 'close', 'high', 'low', 'vol', 'amount']]
    k_values= k_data.values
    # 缠论k线

    chanK = quotes if chanK_flag else chan.parse2ChanK(k_data, k_values, chan_kdf=chanK_flag)
    
    # chanK = cct.combine_dataFrame(chanK,quotes.loc[chanK.index,['ma20d','upper','lower']])

    fenTypes, fenIdx= chan.parse2ChanFen(chanK)
    # log.debug("code:%s fenTypes:%s fenIdx:%s k_data:%s" % (stock_code,fenTypes, fenIdx, len(k_data)))
    biIdx, frsBiType= chan.parse2ChanBi(fenTypes, fenIdx, chanK, least_khl_num=least_khl_num)
    # log.debug("biIdx1:%s chanK:%s" % (biIdx, len(chanK)))
    # print ("biIdx1:%s %s chanK:%s" % (biIdx, str(chanK.index.values[biIdx[-1]])[:10],len(chanK)))

    biIdx = con2Cxianduan(stock_code, k_data, chanK, frsBiType, biIdx, end_date, cur_ji, least_init=least_init,resample=resample)
    # log.debug("biIdx2:%s chanK:%s" % (biIdx, len(biIdx)))
    chanKIdx= [(chanK.index[x]) for x in biIdx]

    if len(biIdx) == 0 and len(chanKIdx) == 0:
        # print "BiIdx is None and chanKidx is None:%s"%(code)
        # return None
        log.error("biIdx is None")

    log.debug("con2Cxianduan:%s chanK:%s %s" % (biIdx, len(chanK), chanKIdx[-1] if len(chanKIdx) > 0 else None))
    # print quotes['close'].apply(lambda x:round(x,2))

    # print '股票代码', get_security_info(stock_code).display_name
    # print '股票代码', (stock_code), resample, least_khl_num
    #  3.得到分笔结果，计算坐标显示

    def plot_fenbi_seq(biIdx, frsBiType, plt=None, color=None, fb_show=0):
        x_fenbi_seq= []
        y_fenbi_seq= []
        for i in range(len(biIdx)):
            if biIdx[i] is not None:
                fenType= -frsBiType if i % 2 == 0 else frsBiType
        #         dt = chanK['enddate'][biIdx[i]]
                # 缠论k线
                dt= chanK.index[biIdx[i]] if chanK_flag else chanK['enddate'][biIdx[i]]
                # print i,k_data['high'][dt], k_data['low'][dt]
                time_long= int(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
                # print x_date_list.index(time_long) if time_long in x_date_list else 0
                if fenType == 1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha = 'left', fontsize = 12)
                        elif fb_show:
                            col_v=color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['high'][dt],
                                     str(k_data['high'][dt]), ha = 'left', fontsize = 12, bbox = dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['high'][dt])
                if fenType == -1:
                    if plt is not None:
                        if color is None:
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va = 'bottom', fontsize = 12)
                        elif fb_show:
                            col_v=color[0] if fenType > 0 else color[1]
                            plt.text(x_date_list.index(time_long), k_data['low'][dt],
                                     str(k_data['low'][dt]), va = 'bottom', fontsize = 12, bbox = dict(facecolor=col_v, alpha=0.5))

                    x_fenbi_seq.append(x_date_list.index(time_long))
                    y_fenbi_seq.append(k_data['low'][dt])
    #             bottom_time = None
    #             for k_line_dto in m_line_dto.member_list[::-1]:
    #                 if k_line_dto.low == m_line_dto.low:
    #                     # get_price返回的日期，默认时间是08:00:00
    #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
    #                     break
    #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
    #             y_fenbi_seq.append(m_line_dto.low)
        return x_fenbi_seq, y_fenbi_seq

    # print  T0[-len(T0):].astype(dt.date)
    if resample in ct.Resample_LABELS:
        T1=T0[-len(T0):].astype(datetime.date) / 1000000000
        Ti=[]
        if len(T0) / x_jizhun > 12:
            x_jizhun=len(T0) / 12
        for i in range(int(len(T0) / x_jizhun)):
            # print "len(T0)/x_jizhun:",len(T0)/x_jizhun
            a1=i * x_jizhun
            d=datetime.date.fromtimestamp(int(T1[int(a1)]))
            # print d
            T2=d.strftime('$%Y-%m-%d$')
            Ti.append(T2)
            # print tab

        d1=datetime.date.fromtimestamp(T1[len(T0) - 1])
        d2=(d1 + datetime.timedelta(days=1)).strftime('$%Y-%m-%d$')
        Ti.append(d2)
    else:
        # T1=T0[-len(T0):].astype(datetime.date) / 1000000000
        T1=T0
        Ti=[]
        if len(T0) / x_jizhun > 12:
            x_jizhun=len(T0) / 12
        for i in range(int(len(T0) / x_jizhun)):
            # print "len(T0)/x_jizhun:",len(T0)/x_jizhun
            a0=i * x_jizhun

            d=str(T0[a0])[11:16]
            # print d
            # T2=d.strftime('$%Y-%m-%d$')
            Ti.append(d)
            # print tab

        # d1=datetime.date.fromtimestamp(T1[len(T0) - 1])
        # d2=(d1 + datetime.timedelta(days=1)).strftime('$%H-%M-%S$')
        # Ti.append(d2)


    ll=Low.min() * 0.97
    hh=High.max() * 1.03

    # ht = HoverTool(tooltips=[
    #             ("date", "@date"),
    #             ("open", "@open"),
    #             ("close", "@close"),
    #             ("high", "@high"),
    #             ("low", "@low"),
    #             ("volume", "@volume"),
    #             ("money", "@money"),])
    # TOOLS = [ht, WheelZoomTool(dimensions=['width']),\
    #          ResizeTool(), ResetTool(),\
    #          PanTool(dimensions=['width']), PreviewSaveTool()]
    if show_mpl:
        # fig=plt.figure(figsize = (10, 6))
        fig=plt.figure(figsize = (12, 8))
        ax1=plt.subplot2grid((10, 1), (0, 0), rowspan = 8, colspan = 1)
        # ax1 = fig.add_subplot(2,1,1)
        # fig = plt.figure()
        # ax1 = plt.axes([0,0,3,2])

        X=np.array(list(range(0, length)))
        pad_nan=X + nan

        # 计算上 下影线
        max_clop=Close.copy()
        max_clop[Close < Open]=Open[Close < Open]
        min_clop=Close.copy()
        min_clop[Close > Open]=Open[Close > Open]

        # 上影线
        line_up=np.array([High, max_clop, pad_nan])
        line_up=np.ravel(line_up, 'F')
        # 下影线
        line_down=np.array([Low, min_clop, pad_nan])
        line_down=np.ravel(line_down, 'F')

        # 计算上下影线对应的X坐标
        pad_nan=nan + X
        pad_X=np.array([X, X, X])
        pad_X=np.ravel(pad_X, 'F')

        # 画出实体部分,先画收盘价在上的部分
        up_cl=Close.copy()
        up_cl[Close <= Open]=nan
        up_op=Open.copy()
        up_op[Close <= Open]=nan

        down_cl=Close.copy()
        down_cl[Open <= Close]=nan
        down_op=Open.copy()
        down_op[Open <= Close]=nan

        even=Close.copy()
        even[Close != Open]=nan

        # 画出收红的实体部分
        pad_box_up=np.array([up_op, up_op, up_cl, up_cl, pad_nan])
        pad_box_up=np.ravel(pad_box_up, 'F')
        pad_box_down=np.array([down_cl, down_cl, down_op, down_op, pad_nan])
        pad_box_down=np.ravel(pad_box_down, 'F')
        pad_box_even=np.array([even, even, even, even, pad_nan])
        pad_box_even=np.ravel(pad_box_even, 'F')

        # X的nan可以不用与y一一对应
        X_left=X - 0.25
        X_right=X + 0.25
        box_X=np.array([X_left, X_right, X_right, X_left, pad_nan])
        # print box_X
        box_X=np.ravel(box_X, 'F')
        # print box_X
        # Close_handle=plt.plot(pad_X,line_up,color='k')

        vertices_up=np.array([box_X, pad_box_up]).T
        vertices_down=np.array([box_X, pad_box_down]).T
        vertices_even=np.array([box_X, pad_box_even]).T

        handle_box_up=mat.patches.Polygon(vertices_up, color = 'r', zorder = 1)
        handle_box_down=mat.patches.Polygon(vertices_down, color = 'g', zorder = 1)
        handle_box_even=mat.patches.Polygon(vertices_even, color = 'k', zorder = 1)

        ax1.add_patch(handle_box_up)
        ax1.add_patch(handle_box_down)
        ax1.add_patch(handle_box_even)

        handle_line_up=mat.lines.Line2D(pad_X, line_up, color = 'k', linestyle = 'solid', zorder = 0)
        handle_line_down=mat.lines.Line2D(pad_X, line_down, color = 'k', linestyle = 'solid', zorder = 0)

                # handle_box_ma = mat.patches.Polygon(vertices_up, color='r', zorder=1)
        # handle_box_ma = mat.lines.Line2D(pad_X,quotes['ma20d'].values, color = 'g', alpha=1, zorder=1)
        # ax2.bar(quotes['ma20d'], 'b',linewidth=0.1)
        # ax2.bar(quotes[quotes.upper > 0].upper, 'g')
        # ax2.bar(quotes[quotes.lower > 0].lower, 'r')

        ax1.add_line(handle_line_up)
        ax1.add_line(handle_line_down)
        # ax1.add_line(handle_box_ma)
        
        # import ipdb;ipdb.set_trace()
        # line1 = ax1.plot(quotes['close'], 'b',linewidth=10)
        # print(len(line1))
        # ax1.add_line(line1[0])

        v=[0, length, Open.min() - 0.5, Open.max() + 0.5]
        plt.axis(v)

        ax1.set_xticks(np.linspace(-2, len(Close) + 2, len(Ti)))

        ax1.set_ylim(ll, hh)

        ax1.set_xticklabels(Ti)

        # assvol=quotes['vol']
        # assvol = assvol.apply(lambda x: round(x / assvol[:1]*quotes.close[:1], 2))
        # ax1.plot(assvol, '-g', linewidth=5)
        # ax1.legend()

        plt.grid(True)
        plt.setp(plt.gca().get_xticklabels(), rotation=30, horizontalalignment='right')

    '''
    以上代码拷贝自https://www.joinquant.com/post/1756
    感谢alpha-smart-dog

    K线图绘制完毕
    '''

    # print "biIdx:%s chankIdx:%s"%(biIdx,str(chanKIdx[-1])[:10])
    if show_mpl:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt)
        # plot_fenbi_seq(fenIdx,fenTypes[0], plt,color=['red','green'])
        plot_fenbi_seq(fenIdx, frsBiType, plt, color=['red', 'green'], fb_show=fb_show)
    else:
        x_fenbi_seq, y_fenbi_seq = plot_fenbi_seq(biIdx, frsBiType, plt=None)
        plot_fenbi_seq(fenIdx, frsBiType, plt=None, color=['red', 'green'], fb_show=fb_show)
    #  在原图基础上添加分笔蓝线
    inx_value= chanK.high.values
    inx_va= [round(inx_value[x], 2) for x in biIdx]
    log.info("inx_va:%s count:%s" % (inx_va, len(quotes.high)))
    log.info("yfenbi:%s count:%s" % ([round(y, 2) for y in y_fenbi_seq], len(chanK)))
    j_BiType= [-frsBiType if i % 2 == 0 else frsBiType for i in range(len(biIdx))]
    BiType_s = j_BiType[-1] if len(j_BiType) > 0 else -2
    # bi_price = [str(chanK.low[idx]) if i % 2 == 0 else str(chanK.high[idx])  for i,idx in enumerate(biIdx)]
    # print ("笔     :%s %s"%(biIdx,bi_price))
    # fen_dt = [str(chanK.index[fenIdx[i]])[:10] if chanK_flag else str(chanK['enddate'][fenIdx[i]])[:10]for i in range(len(fenIdx))]
    fen_dt= [(chanK.index[fenIdx[i]]) if chanK_flag else (chanK['enddate'][fenIdx[i]]) for i in range(len(fenIdx))]
    if len(fenTypes) > 0:
        if fenTypes[0] == -1:
            # fen_price = [str(k_data.low[idx]) if i % 2 == 0 else str(k_data.high[idx])  for i,idx in enumerate(fen_dt)]
            low_fen= [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            high_fen= [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        else:
            # fen_price = [str(k_data.high[idx]) if i % 2 == 0 else str(k_data.low[idx])  for i,idx in enumerate(fen_dt)]
            high_fen = [idx for i, idx in enumerate(fen_dt) if i % 2 == 0]
            low_fen= [idx for i, idx in enumerate(fen_dt) if i % 2 != 0]
        # fen_duration =[fenIdx[i] - fenIdx[i -1 ] if i >0 else 0 for i,idx in enumerate(fenIdx)]
    else:
        # fen_price = fenTypes
        # fen_duration = fenTypes
        low_fen= []
        high_fen= []
    # fen_dt = [str(k_data.index[idx])[:10] for i,idx in enumerate(fenIdx)]
    # print low_fen,high_fen
    def dataframe_mode_round(df):
        roundlist = [1, 0]
        df_mode= []
        for i in roundlist:
            df_mode= df.apply(lambda x: round(x, i)).mode()
            if len(df_mode) > 0:
                break
        return df_mode

    kdl=k_data.loc[low_fen].low
    kdl_mode=dataframe_mode_round(kdl)
    kdh=k_data.loc[high_fen].high
    kdh_mode=dataframe_mode_round(kdh)

    log.info("kdl:%s" % (kdl.values))
    log.info("kdh:%s" % (kdh.values))
    if len(kdl_mode) >0:
        print(("kdl_modeX1:%s kdh_mode%s chanKidx:%s" % (kdl_mode.values, kdh_mode.values, str(chanKIdx[-1])[:10])))

    lkdl, lkdlidx=LIS(kdl)
    lkdh, lkdhidx=LIS(kdh)
    l_status=len(kdl) - len(lkdl)
    h_status=len(kdh) - len(lkdh)
    print(("LkdlX2:%s Lkdh:%s UP:%s fb:%s" % (l_status, h_status, h_status - l_status, len(kdl) - len(kdh))))

    # print ("Gkdl:%s Gkdh:%s"%(grouby_list(kdl.values)[:2],grouby_list(kdh.values)[:2]))

    if len(chanKIdx) > 0:
        lastdf=k_data[k_data.index >= chanKIdx[-1]]
        if BiType_s == -1:
            keydf=lastdf[((lastdf.close >= kdl_mode.max()) & (lastdf.low >= kdl_mode.max()))]
        elif BiType_s == 1:
            keydf=lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min()))]
        else:
            keydf=lastdf[((lastdf.close >= kdh_mode.max()) & (lastdf.high >= kdh_mode.min())) | ((lastdf.close <= kdl_mode.min()) & (lastdf.low <= kdl_mode.min()))]
    # print ("BiType_sX3:%s keydf:%s key:%s"%(BiType_s, None if len(keydf) == 0 else str(keydf.index.values[0])[:10],len(keydf)))

    # return BiType_s,None if len(keydf) == 0 else str(keydf.index.values[0])[:10],len(keydf)
    # import ipdb;ipdb.set_trace()

    log.debug("Fentype:%s " % (fenTypes))
    log.debug("fenIdx:%s " % (fenIdx))
    # print ("fen_duration:%s "%(fen_duration))
    # print ("fen_price:%s "%(fen_price))
    # print ("fendt:%s "%(fen_dt))

    # print ("BiType :%s frsBiType:%s"%(j_BiType,frsBiType))

    if len(j_BiType) > 0:
        if j_BiType[0] == -1:
            tb_price=[str(quotes.low[idx]) if i % 2 == 0 else str(quotes.high[idx]) for i, idx in enumerate(x_fenbi_seq)]
        else:
            tb_price=[str(quotes.high[idx]) if i % 2 == 0 else str(quotes.low[idx]) for i, idx in enumerate(x_fenbi_seq)]
        tb_duration=[x_fenbi_seq[i] - x_fenbi_seq[i - 1] if i > 0 else 0 for i, idx in enumerate(x_fenbi_seq)]

    else:
        tb_price=j_BiType
        tb_duration=j_BiType
    # print "图笔 :", x_fenbi_seq,tb_price
    # print "图笔dura :", tb_duration


    # 线段画到笔上
    xdIdxs, xfenTypes=chan.parse2ChanXD(frsBiType, biIdx, chanK)
    # print '线段', xdIdxs, xfenTypes
    x_xd_seq=[]
    y_xd_seq=[]
    for i in range(len(xdIdxs)):
        if xdIdxs[i] is not None:
            fenType=xfenTypes[i]
    #         dt = chanK['enddate'][biIdx[i]]
            # 缠论k线
            dt=chanK.index[xdIdxs[i]] if chanK_flag else chanK['enddate'][xdIdxs[i]]
    #         print k_data['high'][dt], k_data['low'][dt]
            time_long=int(time.mktime((dt + datetime.timedelta(hours=8)).timetuple()) * 1000000000)
    #         print x_date_list.index(time_long) if time_long in x_date_list else 0
            if fenType == 1:
                x_xd_seq.append(x_date_list.index(time_long))
                y_xd_seq.append(k_data['high'][dt])
            if fenType == -1:
                x_xd_seq.append(x_date_list.index(time_long))
                y_xd_seq.append(k_data['low'][dt])
    #             bottom_time = None
    #             for k_line_dto in m_line_dto.member_list[::-1]:
    #                 if k_line_dto.low == m_line_dto.low:
    #                     # get_price返回的日期，默认时间是08:00:00
    #                     bottom_time = k_line_dto.begin_time.strftime('%Y-%m-%d') +' 08:00:00'
    #                     break
    #             x_fenbi_seq.append(x_date_list.index(long(time.mktime(datetime.strptime(bottom_time, "%Y-%m-%d %H:%M:%S").timetuple())*1000000000)))
    #             y_fenbi_seq.append(m_line_dto.low)

    #  在原图基础上添加分笔蓝线
    if resample in ct.Resample_LABELS:
        print(("线段   :%s x_xd:%s" % (x_xd_seq, [str(quotes.index[x])[:10] for x in x_xd_seq])))
    else:
        if len(x_xd_seq) > 0:
            print(("线段   :%s x_xd:%s" % (x_xd_seq, [str(quotes.index[x]) for x in x_xd_seq][-1])))
    
    print(("笔值  :%s" % ([str(x) for x in (y_xd_seq)][:-2])))

    if len(biIdx) > 0 and (len(x_xd_seq) == 0 or resample not in ct.Resample_LABELS):
        if resample in ct.Resample_LABELS:
            st_data=str(chanK['enddate'][biIdx[len(biIdx) - 1]])[:10]
        else:
            st_data=str(chanK['enddate'][biIdx[len(biIdx) - 1]])

        print(("stdate:%s" % (st_data)))
    # Y_hat = X * b + a


    if show_mpl:
        plt.plot(x_fenbi_seq, y_fenbi_seq)
        # import ipdb;ipdb.set_trace()
        # quotes = quotes.apply(pd.Series.round)
        # quotes = quotes.round(2)

        # plt.legend([stock_code,cname], loc=0)
        plt.legend([stock_code, cname, "Now:%s" % quotes.close[-1], 'kdl:%s' % (kdl_mode.values[:4]), 'kdh:%s' % (kdh_mode.values[:4]),'ma:%s'%(roll_mean_days)], fontsize=12, loc=0)
        if len(kdl_mode) > 0:
            plt.axhline(y=np.median(kdl_mode.values), linewidth=2, color='red', linestyle="--")
        if len(kdh_mode) > 0:
            plt.axhline(y=np.median(kdh_mode.values), linewidth=2, color='green', linestyle="--")
        plt.title(stock_code + " | " + str(cname) + " | " + str(quotes.index[-1])[:10], fontsize=14)
        plt.plot(x_xd_seq, y_xd_seq)
        # ma20d=quotes['ma20d'].apply(lambda x: round(x / quotes['ma20d'][:1] + quotes.close[:1], 2))


        zp=zoompan.ZoomPan()
        figZoom=zp.zoom_factory(ax1, base_scale=1.1)
        figPan=zp.pan_factory(ax1)
        '''#subplot2 bar
        ax2 = plt.subplot2grid((10, 1), (8, 0), rowspan=2, colspan=1)
        # ax2.plot(quotes.vol)
        # ax2.set_xticks(np.linspace(-2, len(quotes) + 2, len(Ti)))
        ll = min(quotes.vol.values.tolist()) * 0.97
        hh = max(quotes.vol.values.tolist()) * 1.03
        ax2.set_ylim(ll, hh)
        # ax2.set_xticklabels(Ti)
        # plt.hist(quotes.vol, histtype='bar', rwidth=0.8)
        plt.bar(x_date_list,quotes.vol, label="Volume", color='b')
        '''

        # 画Volume no tight_layout()
        '''
        pad = 0.25
        yl = ax1.get_ylim()
        ax1.set_ylim(yl[0]-(yl[1]-yl[0])*pad,yl[1])
        ax2 = ax1.twinx()
        ax2.set_position(mat.transforms.Bbox([[0.125,0.1],[0.9,0.32]]))
        volume = np.asarray(quotes.amount)
        pos = quotes['open']-quotes['close']<0
        neg = quotes['open']-quotes['close']>=0
        idx = quotes.reset_index().index
        ax2.bar(idx[pos],volume[pos],color='red',width=1,align='center')
        ax2.bar(idx[neg],volume[neg],color='green',width=1,align='center')
        yticks = ax2.get_yticks()
        ax2.set_yticks(yticks[::3])
        '''


        # same sharex
        plt.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.00)
        plt.setp(ax1.get_xticklabels(), visible=False)
        yl=ax1.get_ylim()
        # ax2 = plt.subplot(212, sharex=ax1)
        ax2=plt.subplot2grid((10, 1), (8, 0), rowspan=2, colspan=1, sharex=ax1)
        # ax2.set_position(mat.transforms.Bbox([[0.125,0.1],[0.9,0.32]]))
        # volume=np.asarray(quotes.amount)
        volume=np.asarray(quotes.vol)
        pos=quotes['open'] - quotes['close'] < 0
        neg=quotes['open'] - quotes['close'] >= 0
        idx=quotes.reset_index().index

        ax2.bar(idx[pos.values], volume[pos.values], color='red', width=1, align='center')
        ax2.bar(idx[neg.values], volume[neg.values], color='green', width=1, align='center')

        yticks=ax2.get_yticks()
        ax2.set_yticks(yticks[::3])
        # plt.tight_layout()
        # plt.subplots_adjust(hspace=0.00, bottom=0.08)
        plt.xticks(rotation=15, horizontalalignment='center')
        # plt.bar(x_date_list,quotes.vol, label="Volume", color='b')

        # quotes['vol'].plot(kind='bar', ax=ax2, color='g', alpha=0.1)
        # ax2.set_ylim([0, ax2.get_ylim()[1] * 2])
        # plt.gcf().subplots_adjust(bottom=0.15)
        # fig.subplots_adjust(left=0.05, bottom=0.08, right=0.95, top=0.95, wspace=0.15, hspace=0.25)
        # scale the x-axis tight
        # ax2.set_xlim(min(x_date_list),max(x_date_list))
        # the y-ticks for the bar were too dense, keep only every third one
        # plt.grid(True)
        # plt.xticks(rotation=30, horizontalalignment='center')
        # plt.setp( axs[1].xaxis.get_majorticklabels(), rotation=70 )
        # plt.legend()
        # plt.tight_layout()
        # plt.draw()
        plt.show()
        # plt.show(block=False)

import argparse
def parseArgmain():
    try:
        parser=argparse.ArgumentParser()
        parser.add_argument('code', type=str, nargs='?', help='999999')
        parser.add_argument('start', nargs='?', type=str, help='20150612')
        parser.add_argument('end', nargs='?', type=str, help='20160101')
        parser.add_argument('-d', action="store", dest="dtype", type=str, nargs='?', choices=['5','30','60', 'd', '3d','w', 'm'], default='d', help='DateType')
        parser.add_argument('-v', action="store", dest="vtype", type=str, choices=['f', 'b'], default='f', help='Price Forward or back')
        parser.add_argument('-p', action="store", dest="ptype", type=str, choices=['high', 'low', 'close'], default='low', help='price type')
        parser.add_argument('-f', action="store", dest="filter", type=str, choices=['y', 'n'], default='y', help='find duration low')
        parser.add_argument('-l', action="store", dest="dl", type=int, default=ct.linePowerCountdl, help='dl default=%s'%(ct.linePowerCountdl))
        parser.add_argument('-da', action="store", dest="days", type=int, default=ct.Power_last_da, help='shift days')
        parser.add_argument('-m', action="store", dest="mpl", type=str, default='y', help='mpl show')
        parser.add_argument('-i', action="store", dest="line", type=str, choices=['y', 'n'], default='y', help='LineHis show')
        parser.add_argument('-w', action="store", dest="wencai", type=str, choices=['y', 'n'], default='n', help='WenCai Search')
        parser.add_argument('-c', action="store", dest="chanK_flag", type=int, choices=[1, 0], default=0, help='chanK_flag')
        parser.add_argument('-le', action="store", dest="least", type=int, default=1, help='least_init 2')
        parser.add_argument('-fb', action="store", dest="fb", type=int, choices=[1, 0], default=1, help='fb show')
        return parser
    except Exception as e:
        # print 'Eerror:',e
        pass
        # raise "Error"
    else:
        # print 'Eerror:'
        pass
    finally:
        # print 'Eerror:'
        pass


def maintest(code, start=None, type='m', filter='y'):
    import timeit
    run=1
    strip_tx=timeit.timeit(lambda: get_linear_model_status(
        code, start=start, type=type, filter=filter), number=run)
    print(("ex Read:", strip_tx))


if __name__ == "__main__":
    # print get_linear_model_status('600671', filter='y', dl=10, ptype='low')
    # print get_linear_model_status('600671', filter='y', dl=10, ptype='high')
    # print get_linear_model_status('600671', filter='y', start='20160329', ptype='low')
    # print get_linear_model_status('600671', filter='y', start='20160329', ptype='high')
    # print get_linear_model_status('999999', filter='y', dl=30, ptype='high')
    # print get_linear_model_status('999999', filter='y', dl=30, ptype='low')
    # print powerCompute_df(['300134','002171'], dtype='d',end=None, dl=10, filter='y')
    # # print powerCompute_df(['601198', '002791', '000503'], dtype='d', end=None, dl=30, filter='y')
    # print get_linear_model_status('999999', filter='y', dl=34, ptype='low', days=1)
    # print get_linear_model_status('399006', filter='y', dl=34, ptype='low', days=1)
    # sys.exit()
    # import re
    if cct.isMac():
        cct.set_console(80, 19)
    else:
        cct.set_console(80, 19)
    # code='600604'
    # show_chan_mpl_tdx(code, start_date=None, end_date=None, stock_days=60, resample='d', show_mpl=True, least_init=2, chanK_flag=False, windows=20, power=True, fb_show=0, df=None)
    # code = raw_input("code:")

    # show_chan_mpl_power('300255', None, None, 60, 'd',show_mpl = False)
    # import ipdb;ipdb.set_trace()
    # show_chan_mpl_fb('300255', None, None, 60, 'd',show_mpl = False)

    
    parser=parseArgmain()
    parser.print_help()
    # show_chan_mpl('999999', None, None, 60, 'd', show_mpl=True)
    import re
    while 1:
        try:
            # log.setLevel(LoggerFactory.INFO)
            # log.setLevel(LoggerFactory.ERROR)
            # log.setLevel(LoggerFactory.DEBUG)
            # if cct.get_os_system().find('win') >= 0:
            #     import win_unicode_console
            #     win_unicode_console.disable()
            code=str(input("code:"))
            # code=str(code)
            # if cct.get_os_system().find('win') >= 0:
            #     # import win_unicode_console
            #     win_unicode_console.enable()
            # code == '000830'
            if len(code) == 0:
                code = '999999' 
            args=parser.parse_args(code.split())

            # print args
            # print str(args.days)

            if str(args.code) != 'q' and str(args.code) != 'e' and not str(args.code) == 'None' and (re.match('[a-zA-Z]+',code) is not None  or re.match('[ \\u4e00 -\\u9fa5]+',code) == None ):
                args.code = tdd.get_sina_data_cname(args.code)

                # print "code:%s %s"%(code,args.code)
            if len(str(args.code)) == 6:
                if args.start is not None and len(args.start) <= 4:
                    args.dl=int(args.start)
                    args.start=None
                if args.dtype in ['m']:
                    args.dl = ct.duration_date_month * 2

                elif args.dtype in ['w']:
                    args.dl = ct.duration_date_week

                start=cct.day8_to_day10(args.start)
                end=cct.day8_to_day10(args.end)
                # print "chank:%s"%(args.chanK_flag)
                if args.mpl == 'y':
                    show_chan_mpl_fb(args.code, args.start, args.end, args.dl, args.dtype, show_mpl=True,
                                     least_init = args.least, chanK_flag = args.chanK_flag, fb_show = args.fb)
                    # show_chan_mpl_power(args.code, args.start, args.end, args.dl, args.dtype, show_mpl=True,least_init=args.least,chanK_flag=args.chanK_flag)
                else:
                    show_chan_mpl_power(args.code, args.start, args.end, args.dl, args.dtype, show_mpl = False,
                                        least_init = args.least, chanK_flag = args.chanK_flag, fb_show = args.fb)
                cct.sleep(0.1)
                # print ''
                # ts=time.time()
                # time.sleep(5)
                # print "%0.5f"%(time.time()-ts)
            elif code.startswith('w') or code.startswith('a'):
                blkname = '077.blk'
                block_path = tdd.get_tdx_dir_blocknew() + blkname
                args=cct.writeArgmain().parse_args(code.split())
                codew=stf.WriteCountFilter(pd.DataFrame(), writecount=args.dl)
                if args.code == 'a':
                    cct.write_to_blocknew(block_path, codew)
                    # cct.write_to_blocknew(all_diffpath,codew)
                # else:
                #     cct.write_to_blocknew(block_path, codew, False)
                    # cct.write_to_blocknew(all_diffpath,codew,False)
                    print(("wri ok:%s" % block_path))

            elif code == 'q':
                sys.exit(0)

            elif code == 'h' or code == 'help':
                parser.print_help()
            else:
                pass
        except (KeyboardInterrupt) as e:
            # print "key"
            print(("KeyboardInterrupt:", e))
        except (IOError, EOFError, Exception) as e:
            # print "Error", e
            import traceback
            traceback.print_exc()

'''
# old chan
def label_k_func(df):
    # 进行K线的包含关系处理，再原dataframe数据表中增加label列进行是否有效的标记，增加两列记录合并K线后的最值
    h = df['high'].values
    l = df['low'].values
    df['t'] = pd.Series(range(len(df)), index=df.index)
    t = df['t'].values
    label = [1]
    h_jizhi, l_jizhi = h[0], l[0]
    high_new = [h[0]]
    low_new = [l[0]]
    # 标记Ｋ线的有效性，上升Ｋ线为１，下降为－１，无效为０
    for i in t[1:]:
        # 缠论上升K线的定义
        if h[i] > h_jizhi and l[i] > l_jizhi:
            label.append(1)
            h_jizhi = max(h[i], h[i - 1])
            l_jizhi = max(l[i], l[i - 1])
        # 缠论下降K线的定义
        elif h[i] < h_jizhi and l[i] < l_jizhi:
            label.append(-1)
            h_jizhi = min(h[i], h[i - 1])
            l_jizhi = min(l[i], l[i - 1])
        # 包涵K线的处理
        else:
            label.append(0)
            # 下面的内容主要是进行极值的更新
            for j in label[::-1]:
                if j != 0:
                    a = j
                    break
            if a == 1:
                h_jizhi = max(h[i], h_jizhi)
                l_jizhi = max(l[i], l_jizhi)
            else:
                h_jizhi = min(h[i], h_jizhi)
                l_jizhi = min(l[i], l_jizhi)
        high_new.append(h_jizhi)
        low_new.append(l_jizhi)
    # 把结果添加到df
    df['label_k'] = pd.Series(label, index=df.index)
    df['high_k'] = pd.Series(high_new, index=df.index)
    df['low_k'] = pd.Series(low_new, index=df.index)
    return df
'''
#  在原图基础上添加分笔蓝线
# plt.plot(x_fenbi_seq,y_fenbi_seq)

# plt.show()
